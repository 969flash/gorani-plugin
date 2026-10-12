"""배포 빌더 — Yak 패키지와 데이터 팩을 만든다 (Rhino 밖 전용, macOS).

    python3 scripts/dev_deploy.py            # 둘 다
    python3 scripts/dev_deploy.py yak        # build/UrbanDesignTool-<버전>-rh8_0-any.yak
    python3 scripts/dev_deploy.py packs      # build/packs/*.db.xz + manifest.json
    python3 scripts/dev_deploy.py packs --sido 43 --drop   # 시도 하나만 압축하고 원본 DB를 지운다(전국 빌드 흐름)

yak: 진입 명령 UrbanSite 하나짜리 .rhp를 rhinocode로 빌드하고(떠 있는 Rhino 8 필요), 그 옆에 scripts/(평문 진입 스크립트 +
     로직 .pyc + 패널 HTML·vendor)를 두고 yak CLI로 묶는다. rhinocode의 Shared 리소스는 폴더 구조를 펴 버려서 쓰지 않는다
     (2026-10-12 실측: scripts/vendor/b.txt → shared/b.txt). UrbanSite는 .rhp 옆 scripts/cmd_site.py를 그대로 실행한다.
packs: data/의 시도별 `<시도>_site.db`·`<시도>_context.db`마다 필지(rtree 제거)·컨텍스트(등고선 제외)·등고선 팩을
       xz로 압축하고 sha256·범위를 매니페스트에 적는다. 등고선 팩은 국내 서버에 올린다(constants.TERRAIN_DATABASE_NAME 주석).
       올린 뒤 매니페스트 주소를 constants.DATA_MANIFEST_URL에 넣는다.

`.pyc`는 Python 마이너 버전에 묶이므로 Rhino 8의 CPython과 같은 3.9로 실행해야 한다. macOS 기본 /usr/bin/python3가 3.9다.
"""

import argparse
import datetime
import hashlib
import json
import os
import py_compile
import shutil
import sqlite3
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402

BUILD_DIR = os.path.join(ROOT_DIR, "build")
RHINO_BIN_DIR = "/Applications/Rhino 8.app/Contents/Resources/bin"

PACKAGE_NAME = constants.TOOL_NAME
PACKAGE_VERSION = "0.1.0"                                  # 올릴 때마다 올린다 — yak은 같은 버전을 다시 받지 않는다
PLUGIN_ID = "8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a10"         # 바꾸지 말 것 — UrbanSite가 이 id로 자기 폴더를 찾는다
COMMAND_ID = "8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a11"
COMMAND_NAME = "UrbanSite"
PUBLISHER = {"name": "sanghoon", "email": "bsh969flash@gmail.com"}

PLAIN_SCRIPT_NAMES = ("loader.py", "cmd_site.py")         # 입출력 연결뿐이라 감출 로직이 없다
UI_FILE_NAMES = ("site_ui.html",)
UI_DIR_NAMES = ("vendor",)
DOC_FILE_NAMES = ("docs/install.md",)
EXCLUDED_MODULE_PREFIXES = ("dev_", "cmd_", "probe_")     # 개발·실측 전용과 진입 스크립트

# UrbanSite 명령 본문 — rhinocode가 .rhp에 넣는다. 한글 앨리어스는 명령 이름에 못 써서 처음 실행 때 등록한다.
COMMAND_SOURCE = '''#! python 3
"""UrbanSite — 대지검토 패널을 연다. Yak 설치 폴더(.rhp 옆)의 scripts/cmd_site.py를 그대로 실행한다."""
import os
import runpy

import Rhino
import System

folder = os.path.dirname(Rhino.PlugIns.PlugIn.PathFromId(System.Guid("%(plugin_id)s")))
aliases = Rhino.ApplicationSettings.CommandAliasList
if not aliases.IsAlias("%(alias)s"):
    aliases.Add("%(alias)s", "%(command)s")
runpy.run_path(os.path.join(folder, "scripts", "cmd_site.py"), run_name="__main__")
'''

PACK_KINDS = (   # (종류, 표시 이름 꼬리, 원본 DB 종류) — 등고선 팩은 컨텍스트 DB에서 terrain만 떼어 낸다
    ("site", "필지", "site"),
    ("context", "건물·도로·수계", "context"),
    ("terrain", "등고선", "context"),
)
BOUNDS_SQL = {   # 팩 범위(EPSG:5186) — data_pack이 대상지에 걸리는 시도 파일만 열 때 쓴다
    "site": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM parcels",
    "context": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM buildings",
    "terrain": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM features",
}


def get_deploy_module_names():
    # type: () -> list
    """.pyc로 컴파일해 배포할 로직 모듈 이름(정렬). 진입 스크립트·개발 전용·loader를 뺀다."""
    names = []
    for file_name in sorted(os.listdir(SCRIPTS_DIR)):
        if not file_name.endswith(".py") or file_name.startswith(EXCLUDED_MODULE_PREFIXES):
            continue
        name = file_name[:-3]
        if name != "loader":
            names.append(name)
    return names


def strip_spatial_index(database_path):
    # type: (str) -> int
    """DB 사본에서 rtree 가상테이블과 트리거를 지운다 — Rhino 8 Windows CPython의 SQLite에는 rtree 모듈이 없다."""
    connection = sqlite3.connect(database_path)
    trigger_names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND sql LIKE '%spatial_index%'")]
    table_names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE '%spatial_index'")]
    for name in trigger_names:
        connection.execute('DROP TRIGGER "%s"' % name)
    for name in table_names:
        connection.execute('DROP TABLE "%s"' % name)
    connection.commit()
    connection.close()
    return len(trigger_names) + len(table_names)


# ── yak ─────────────────────────────────────────────────

def _stage_scripts(package_dir):
    # type: (str) -> int
    """package_dir/scripts/ — 평문 진입 스크립트 + UI 에셋 + 로직 .pyc(optimize=2, 개발 PC 경로 제거)."""
    target = os.path.join(package_dir, "scripts")
    os.makedirs(target)
    for file_name in PLAIN_SCRIPT_NAMES + UI_FILE_NAMES:
        shutil.copyfile(os.path.join(SCRIPTS_DIR, file_name), os.path.join(target, file_name))
    for dir_name in UI_DIR_NAMES:
        shutil.copytree(os.path.join(SCRIPTS_DIR, dir_name), os.path.join(target, dir_name))
    names = get_deploy_module_names()
    for name in names:
        py_compile.compile(os.path.join(SCRIPTS_DIR, name + ".py"), cfile=os.path.join(target, name + ".pyc"),
                           dfile=name + ".py", doraise=True, optimize=2)
    for path in DOC_FILE_NAMES:
        os.makedirs(os.path.join(package_dir, os.path.dirname(path)), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT_DIR, path), os.path.join(package_dir, path))
    return len(names)


def _build_plugin(project_dir):
    # type: (str) -> str
    """UrbanSite 명령 하나짜리 rhproj를 쓰고 rhinocode로 빌드한다. 빌드 결과 폴더(rhp·rui·manifest.yml)를 돌려준다."""
    os.makedirs(os.path.join(project_dir, "commands"))
    with open(os.path.join(project_dir, "commands", COMMAND_NAME + ".py"), "w", encoding="utf-8") as f:
        f.write(COMMAND_SOURCE % {"plugin_id": PLUGIN_ID, "alias": constants.PANEL_CAPTION, "command": COMMAND_NAME})
    project = {
        # rhinocode가 host를 보고 8.11 미만에서 저장한 프로젝트로 판정하면 거부한다 — os·arch까지 있어야 통과(2026-10-12 실측)
        "host": {"name": "Rhino3D", "version": "8.35", "os": "macOS", "arch": "arm64"},
        "id": PLUGIN_ID,
        "identity": {
            "name": PACKAGE_NAME, "version": PACKAGE_VERSION, "publisher": PUBLISHER, "license": "MIT",
            "description": "도시설계 착수용 대지 컨텍스트(건물·도로·지형·수계 3D, 베이스맵, 현황도). 명령: UrbanSite / 대지검토",
        },
        "settings": {
            "buildPath": "build/",
            "buildTarget": {"host": {"name": "Rhino3D", "version": "8"}, "title": "Rhino3D (8.*)", "slug": "rh8"},
            "publishTarget": {"title": "McNeel Yak Server"},
        },
        "codes": [{"id": COMMAND_ID, "language": {"id": "*.*.python", "version": "3.*.*"},
                   "title": COMMAND_NAME, "uri": "commands/%s.py" % COMMAND_NAME}],
    }
    project_path = os.path.join(project_dir, PACKAGE_NAME + ".rhproj")
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)
    result = subprocess.run([os.path.join(RHINO_BIN_DIR, "rhinocode"), "project", "build", project_path],
                            capture_output=True, text=True)
    output_dir = os.path.join(project_dir, "build", "rh8")
    if result.returncode != 0 or not os.path.exists(os.path.join(output_dir, PACKAGE_NAME + ".rhp")):
        sys.exit("rhinocode 빌드 실패 — Rhino 8이 떠 있어야 합니다.\n%s%s" % (result.stdout, result.stderr))
    return output_dir


def build_yak():
    # type: () -> str
    """build/yak/ 아래에서 스크립트를 모으고 플러그인을 빌드해 .yak 하나를 build/에 만든다. 경로를 돌려준다."""
    work_dir = os.path.join(BUILD_DIR, "yak")
    shutil.rmtree(work_dir, ignore_errors=True)
    package_dir = os.path.join(work_dir, "package")
    os.makedirs(package_dir)
    print("  로직 모듈 %d개 컴파일" % _stage_scripts(package_dir))
    plugin_dir = _build_plugin(os.path.join(work_dir, "project"))
    for file_name in (PACKAGE_NAME + ".rhp", PACKAGE_NAME + ".rui", "manifest.yml"):
        shutil.copyfile(os.path.join(plugin_dir, file_name), os.path.join(package_dir, file_name))
    result = subprocess.run([os.path.join(RHINO_BIN_DIR, "yak"), "build", "--platform", "any"],
                            cwd=package_dir, capture_output=True, text=True)
    packages = [name for name in os.listdir(package_dir) if name.endswith(".yak")]
    if result.returncode != 0 or len(packages) != 1:
        sys.exit("yak build 실패\n%s%s" % (result.stdout, result.stderr))
    target = os.path.join(BUILD_DIR, packages[0])
    shutil.move(os.path.join(package_dir, packages[0]), target)
    return target


# ── packs ───────────────────────────────────────────────

def _make_pack_database(pack_name, source, target):
    # type: (str, str, str) -> None
    """팩 하나의 DB 파일. 필지 = 사본 + rtree 제거, 컨텍스트 = 사본 − 등고선, 등고선 = features 스키마 + terrain 행만."""
    if pack_name.endswith("_terrain.db"):
        connection = sqlite3.connect(target)
        connection.execute("ATTACH DATABASE ? AS source", (source,))
        for (sql,) in connection.execute("SELECT sql FROM source.sqlite_master WHERE tbl_name = 'features' AND sql IS NOT NULL").fetchall():
            connection.execute(sql)
        connection.execute("INSERT INTO features SELECT * FROM source.features WHERE theme = ?", (constants.TERRAIN_THEME,))
        connection.execute("PRAGMA user_version = %d" % connection.execute("PRAGMA source.user_version").fetchone()[0])
        connection.commit()
        connection.execute("DETACH DATABASE source")
    else:
        shutil.copyfile(source, target)
        connection = sqlite3.connect(target)
        if pack_name.endswith("_context.db"):
            connection.execute("DELETE FROM features WHERE theme = ?", (constants.TERRAIN_THEME,))
            connection.commit()
        connection.close()
        strip_spatial_index(target)
        connection = sqlite3.connect(target)
    connection.execute("ANALYZE")
    connection.execute("VACUUM")
    connection.close()


def _get_sha256(path):
    # type: (str) -> str
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_packs(sido_codes=None, drop=False):
    # type: (list, bool) -> str
    """build/packs/에 시도 팩 DB → xz(-T0 멀티스레드) + manifest.json. 매니페스트 경로를 돌려준다.

    sido_codes를 주면 그 시도만 만들고 매니페스트의 다른 시도 항목은 그대로 둔다(시도 하나씩 빌드·압축하며 디스크를 아끼는 흐름).
    drop이면 압축 뒤 원본 DB(data/<시도>_site.db·_context.db)를 지운다 — 서울은 개발용이라 남긴다. 전국 원본은 디스크에 다 못 둔다.
    """
    pack_dir = os.path.join(BUILD_DIR, "packs")
    os.makedirs(pack_dir, exist_ok=True)
    manifest_path = os.path.join(pack_dir, "manifest.json")
    packs = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
    data_dir = os.path.join(ROOT_DIR, "data")
    for code, (sido_name, slug) in sorted(constants.SIDO.items(), key=lambda item: item[1][1]):
        if sido_codes and code not in sido_codes:
            continue
        sources = set()
        for kind, label, source_kind in PACK_KINDS:
            source = os.path.join(data_dir, "%s_%s.db" % (slug, source_kind))
            if not os.path.exists(source):
                continue
            sources.add(source)
            pack_name = "%s_%s.db" % (slug, kind)
            target = os.path.join(pack_dir, pack_name)
            print("  %s 만드는 중..." % pack_name, flush=True)
            if os.path.exists(target):
                os.remove(target)
            _make_pack_database(pack_name, source, target)
            connection = sqlite3.connect(target)
            bounds = [round(v, 1) for v in connection.execute(BOUNDS_SQL[kind]).fetchone()]
            connection.close()
            size, sha256 = os.path.getsize(target), _get_sha256(target)
            print("  %s 압축 중... (%.2f GB)" % (pack_name, size / 1024.0 ** 3), flush=True)
            subprocess.run(["xz", "-6", "-T0", "-f", target], check=True)
            packs[pack_name] = {"name": pack_name, "label": "%s %s" % (sido_name, label), "url": pack_name + ".xz", "size": size,
                                "sha256": sha256, "bounds": bounds, "xz_size": os.path.getsize(target + ".xz")}
        if drop and code != "11":
            for source in sources:
                os.remove(source)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"version": datetime.date.today().isoformat(), "packs": sorted(packs.values(), key=lambda p: p["name"])},
                  f, ensure_ascii=False, indent=1)
    return manifest_path


def main():
    if sys.version_info[:2] != (3, 9):
        sys.exit("Rhino 8의 CPython(3.9)과 같은 Python 3.9로 실행해야 .pyc가 호환됩니다. 현재: %d.%d" % sys.version_info[:2])
    parser = argparse.ArgumentParser(description="Yak 패키지·데이터 팩 빌드")
    parser.add_argument("what", nargs="?", default="all", choices=("all", "yak", "packs"))
    parser.add_argument("--sido", help="packs: 쉼표로 구분한 시도 코드만 (기본 data/에 있는 전부)")
    parser.add_argument("--drop", action="store_true", help="packs: 압축 뒤 원본 시도 DB를 지운다(서울 제외)")
    args = parser.parse_args()
    if args.what in ("all", "yak"):
        print("yak: %s" % build_yak())
    if args.what in ("all", "packs"):
        manifest_path = build_packs(args.sido.split(",") if args.sido else None, args.drop)
        print("packs: %s" % manifest_path)
        print("  등고선 팩(*_terrain.db.xz)은 국내 서버에, 나머지는 매니페스트와 같은 곳에 올린다.")


if __name__ == "__main__":
    main()
