"""배포 빌더 — Yak 패키지와 데이터 팩을 만든다 (Rhino 밖 전용, macOS).

    python3 scripts/dev_deploy.py            # 둘 다
    python3 scripts/dev_deploy.py yak        # build/Gorani-<버전>-rh8_0-any.yak
    python3 scripts/dev_deploy.py blender    # build/blender_repo/gorani-<버전>.zip + index.json(정적 확장 저장소)
    python3 scripts/dev_deploy.py sketchup   # build/bsh_gorani-<버전>.rbz (Extension Warehouse·확장 관리자 설치)
    python3 scripts/dev_deploy.py web        # build/web/ (정적 파일 — 웹사이트 app/에 올린다)
    python3 scripts/dev_deploy.py packs      # build/packs/*.db.xz + manifest.json
    python3 scripts/dev_deploy.py packs --sido 43 --drop   # 시도 하나만 압축하고 원본 DB를 지운다(전국 빌드 흐름)
    python3 scripts/dev_deploy.py repack     # 시도 팩 압축본을 풀어 (줄이고) 시군구 팩으로 나눠 다시 압축
    python3 scripts/dev_deploy.py rebounds   # 매니페스트의 팩 범위만 다시 잰다(시군구 필지 중심점 핵심 범위 — constants.PACK_BOUNDS_*)
    python3 scripts/dev_deploy.py upload     # 필지 팩 + 매니페스트는 Hugging Face(hf auth login 먼저), 컨텍스트·등고선 팩은 국내 버킷(~/.oci/config 먼저)
    python3 scripts/dev_deploy.py notices    # docs/notices.json(업데이트·공지)만 Hugging Face 매니페스트에 넣어 올린다 — 팩은 그대로

yak: 진입 명령 Gorani 하나짜리 .rhp를 rhinocode로 빌드하고(떠 있는 Rhino 8 필요), 그 옆에 scripts/(평문 진입 스크립트 +
     로직 .pyc + 패널 HTML·vendor)를 두고 yak CLI로 묶는다. rhinocode의 Shared 리소스는 폴더 구조를 펴 버려서 쓰지 않는다
     (2026-10-12 실측: scripts/vendor/b.txt → shared/b.txt). Gorani는 .rhp 옆 scripts/cmd_site.py를 그대로 실행한다.
blender: Blender 확장(4.2+) — gorani/__init__.py(scripts/cmd_blender.py로 넘김) + blender_manifest.toml + scripts/ 원본 .py·UI 에셋을
     Blender CLI(extension build)로 zip, 그 폴더에 server-generate로 index.json·index.html. 로직은 .pyc가 아니라 원본이다 — Blender 4.2~4.5는
     파이썬 3.11, 5.x는 3.13이라 .pyc 하나로 못 덮고, Blender 확장은 GPL이다. Rhino 전용(panel_host·cmd_install)과 dev_·server_는 뺀다.
sketchup: SketchUp 확장(.rbz = zip) — 뿌리 bsh_gorani.rb(등록) + bsh_gorani/main.rb(scripts/sketchup_ext.rb) + scripts/(평문 진입 스크립트
     + 로직 .pyc + 패널 HTML·vendor) + python/<플랫폼>/(python-build-standalone 3.12 + numpy·shapely, 플랫폼 셋: mac-arm64·mac-x64·win-x64).
     SketchUp에는 파이썬이 없어 확장이 번들 파이썬으로 사이드카(cmd_sketchup)를 띄운다. 런타임 tar는 build/cache/에 받아 둔다.
     .pyc는 번들 파이썬(3.12)으로 컴파일한다(unchecked-hash — zip이 수정 시각을 2초 단위로 줄여도 다시 컴파일하지 않는다).
web: 브라우저판 정적 파일 — index.html(scripts/web_app.html) + panel.html(site_ui.html에 vendor 주입, panel_server.get_html) + web_worker.js
     + scripts.zip(로직 원본 .py — 워커가 Pyodide 가상 파일계에 푼다). Pyodide·numpy·shapely·three.js는 CDN에서 받는다(web_worker.js·web_app.html 맨 위).
packs: data/의 시도별 `<시도>_site.db`·`<시도>_context.db`마다 필지(rtree 제거)·컨텍스트(등고선 제외)·등고선 팩을
       xz로 압축하고 sha256·범위를 매니페스트에 적는다. 컨텍스트·등고선 팩은 국내 서버에 올린다(constants.DATA_DOMESTIC_BASE_URL 주석).

`.pyc`는 Python 마이너 버전에 묶이므로 Rhino 8의 CPython과 같은 3.9로 실행해야 한다. macOS 기본 /usr/bin/python3가 3.9다.
"""

import argparse
import datetime
import hashlib
import json
import os
import py_compile
import re
import shutil
import sqlite3
import statistics
import subprocess
import sys

import shapely

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402

BUILD_DIR = os.path.join(ROOT_DIR, "build")
NOTICES_PATH = os.path.join(ROOT_DIR, "docs", "notices.json")   # 매니페스트 update·notices 원본 — 칸은 docs/panel_ui.md '업데이트·공지'
RHINO_BIN_DIR = "/Applications/Rhino 8.app/Contents/Resources/bin"
BRAND_DIR = os.path.join(ROOT_DIR, "docs", "brand")      # 로고 원본 SVG(currentColor)와 크기별 PNG — docs/brand/logo.html
TOOLBAR_ICON_COLORS = {"light": "#111418", "dark": "#E8ECF2"}   # Rhino 도구 막대 라이트·다크 아이콘 색 = DESIGN.md 잉크·다크 잉크

PACKAGE_NAME = constants.TOOL_NAME
PACKAGE_VERSION = constants.PANEL_VERSION                  # 올릴 때마다 constants.PANEL_VERSION을 올린다 — yak은 같은 버전을 다시 받지 않는다
PLUGIN_ID = "8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a10"         # 바꾸지 말 것 — Gorani가 이 id로 자기 폴더를 찾는다
COMMAND_ID = "8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a11"
COMMAND_NAME = "Gorani"
PUBLISHER = {"name": "sanghoon", "email": "bsh969flash@gmail.com"}
WEBSITE_URL = "https://969flash.github.io/gorani/"
# yak manifest — rhinocode가 쓰는 manifest.yml은 url·검색어가 비고 버전에 +빌드번호가 붙는다. PackageManager 목록·검색에 보일 내용으로 갈아 쓴다.
# PackageManager 검색은 이름·설명·검색어를 다 본다(2026-10-19 yak search 실측 — 'terrain'·'roads'가 설명만으로 걸림). 설명은 쉬운 말로, 사람들이 찾을 낱말을 넣는다.
# guid: 검색어는 지우지 말 것 — Rhino가 이 플러그인 id로 패키지를 찾는다. 검색어는 영문·숫자·-·_만(공백이면 yak push가 400).
YAK_MANIFEST = '''name: %(name)s
version: %(version)s
authors:
- %(author)s
description: |-
  Free Rhino 8 plugin that models the city around your site.
  Pick a site on the map and press one button. The surrounding buildings, roads, terrain, water and green space come into your open document as 3D layers. Worldwide with OpenStreetMap; in Korea with nationwide parcel, zoning and contour data.

  How it works
  1. Restart Rhino after installing, then type Gorani.
  2. Pick a site: click parcels, draw an area or drop a point.
  3. Set the extent (100 m to 2 km) and press 3D.

  What you get
  - Building masses with heights, roads, terrain, water, green space and railways on separate layers
  - Optional 2D: layered Illustrator basemap, analysis maps (SVG, AI), CSV tables
  - No Grasshopper, no account, no API key

  한국어
  Gorani는 대지 주변 현황 모델을 자동으로 만들어 주는 무료 Rhino 8 플러그인입니다.
  지도에서 대상지를 고르고 버튼 하나를 누르면, 주변 건물·도로·지형·하천·녹지가 지금 열려 있는 문서에 레이어별 3D로 들어옵니다. 국내는 전국 필지·용도지역·등고선 데이터로, 해외는 OpenStreetMap으로 만듭니다.

  사용 방법
  1. 설치 후 라이노를 다시 켜고 명령창에 Gorani를 입력합니다.
  2. 대상지를 고릅니다. 필지 클릭, 구역 그리기, 위치 찍기 중 하나입니다.
  3. 범위(100 m~2 km)를 정하고 [3D 모델 만들기]를 누릅니다.

  결과물
  - 높이가 있는 건물 매스, 도로, 지형, 하천, 녹지, 철도 (레이어별)
  - 2D(필요할 때만): 일러스트레이터 베이스맵, 현황도·분석도(SVG·AI), 조서 CSV
  - 그래스호퍼, 회원가입, API 키는 필요 없습니다

  日本語
  Goraniは、敷地まわりの街を3Dでつくる無料のRhino 8プラグインです。
  地図で敷地を選んでボタンを押すと、周辺の建物・道路・地形・水系・緑地が、開いているドキュメントにレイヤー分けされた3Dで入ります。

  使い方
  1. インストール後にRhinoを再起動し、Goraniと入力します。
  2. 敷地を選びます。区画をクリック、範囲を描く、地点を打つのいずれかです。
  3. 範囲（100 m〜2 km）を決めて3Dを押します。
license: MIT
url: %(url)s
icon: icon.png
keywords:
- gorani
- urban-design
- site-model
- context-model
- city-model
- 3d-city
- buildings
- terrain
- topography
- contours
- openstreetmap
- osm
- gis
- basemap
- site-analysis
- korea
- cadastral
- zoning
- guid:%(plugin_id)s
'''

PLAIN_SCRIPT_NAMES = ("loader.py", "cmd_site.py")         # 입출력 연결뿐이라 감출 로직이 없다
UI_FILE_NAMES = ("site_ui.html",)
UI_DIR_NAMES = ("vendor",)
DOC_FILE_NAMES = ("docs/install.md",)
EXCLUDED_MODULE_PREFIXES = ("dev_", "cmd_", "probe_", "server_", "blender_", "sketchup_", "web_")     # 개발·실측 전용, 진입 스크립트, 국내 서버(VM) 전용, Blender·SketchUp·웹판
YAK_EXCLUDED_NAMES = ("mesh_geometry", "panel_server")      # Blender·SketchUp 공용(mathutils·shapely, 브라우저 패널) — Rhino는 안 쓴다

# Gorani 명령 본문 — rhinocode가 .rhp에 넣는다.
COMMAND_SOURCE = '''#! python 3
"""Gorani — 패널을 연다. Yak 설치 폴더(.rhp 옆)의 scripts/cmd_site.py를 그대로 실행한다."""
import os
import runpy

import Rhino
import System

folder = os.path.dirname(Rhino.PlugIns.PlugIn.PathFromId(System.Guid("%(plugin_id)s")))
runpy.run_path(os.path.join(folder, "scripts", "cmd_site.py"), run_name="__main__")
'''

BLENDER_APP = "/Applications/Blender.app/Contents/MacOS/Blender"
BLENDER_PACKAGE_ID = "gorani"
BLENDER_EXCLUDED_NAMES = ("panel_host.py", "cmd_install.py", "cmd_sketchup.py", "cmd_web.py")    # Rhino 전용(Eto·RhinoCommon), SketchUp 사이드카, 웹판
# 확장 약관 1.2 — 함께 넣는 글꼴·이미지는 CC0만. Pretendard(OFL)는 빼고 패널은 시스템 글꼴(Apple SD Gothic Neo·맑은 고딕)로 그린다
BLENDER_EXCLUDED_ASSETS = ("PretendardVariable.woff2", "LICENSE-pretendard.txt")
BLENDER_LICENSE_PATH = os.path.join(ROOT_DIR, "docs", "licenses", "GPL-3.0.txt")   # 확장 약관 1.1 — 애드온은 GPL-3.0-or-later
BLENDER_INIT_SOURCE = '''"""Gorani Blender 확장 — 본문은 scripts/cmd_blender.py(등록만 넘긴다)."""
from .scripts import cmd_blender


def register():
    cmd_blender.register()


def unregister():
    cmd_blender.unregister()
'''
# 확장 매니페스트 — 칸 규칙은 Blender 매뉴얼 Extensions > Getting started(tagline·permissions 사유 64자 이하, 끝 마침표 없음)
BLENDER_MANIFEST = '''schema_version = "1.0.0"
id = "%(id)s"
version = "%(version)s"
name = "%(name)s"
tagline = "Site context for urban design: buildings, roads, terrain"
maintainer = "%(maintainer)s"
type = "add-on"
website = "https://969flash.github.io/gorani/"
tags = ["Import-Export", "3D View"]
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later"]
copyright = ["2026 sanghoon", "2010-2023 Volodymyr Agafonkin (Leaflet)", "2010-2011 CloudMade (Leaflet)"]

[permissions]
network = "Map tiles, regional data packs and OpenStreetMap context"
files = "Write results and data packs to the Gorani home folder"
'''

PACK_KINDS = (   # (종류, 표시 이름 꼬리, 원본 DB 종류) — 등고선 팩은 컨텍스트 DB에서 terrain만 떼어 낸다
    ("site", "필지", "site"),
    ("context", "건물·도로·수계", "context"),
    ("terrain", "등고선", "context"),
)
REWRITE_CHUNK = 100000      # 도형 다시 쓰기 한 번에 읽는 id 구간
SPLIT_CELL = 200.0          # m — 시군구 나누기 격자. 필지 중심 다수결로 격자의 시군구를 정한다
SPLIT_SEARCH = 50           # 칸 — 필지 없는 곳(바다·큰 산)은 이 범위(10 km) 안 가장 가까운 격자의 시군구로
SLIM_PACK_ID = 0x55445431   # 'UDT1' — slim_pack_database를 거친 팩 표시(PRAGMA application_id)
BOUNDS_SQL = {   # 팩 범위(EPSG:5186) — data_pack이 대상지에 걸리는 시도 파일만 열 때 쓴다
    "site": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM parcels",
    "context": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM buildings",
    "terrain": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM features",
}


def get_core_bounds(points):
    # type: (list) -> tuple
    """점 [(x, y)]의 범위 — 핵심 범위(PACK_BOUNDS_CORE_QUANTILE~1-q)를 각 변마다 그 폭의 절반(최소 PACK_BOUNDS_EXTEND_MIN)까지 넓힌 창 안의
    점만으로 min/max를 재고 PACK_BOUNDS_MARGIN을 더한다. 창 밖 점(원천 좌표 오류)은 버린다. 점이 없으면 None."""
    if not points:
        return None
    window = []
    for axis in (0, 1):
        values = sorted(p[axis] for p in points)
        q = constants.PACK_BOUNDS_CORE_QUANTILE
        low, high = values[int(q * (len(values) - 1))], values[int((1 - q) * (len(values) - 1))]
        extend = max((high - low) * 0.5, constants.PACK_BOUNDS_EXTEND_MIN)
        window.append((low - extend, high + extend))
    kept = [p for p in points if window[0][0] <= p[0] <= window[0][1] and window[1][0] <= p[1] <= window[1][1]]
    margin = constants.PACK_BOUNDS_MARGIN
    return (min(p[0] for p in kept) - margin, min(p[1] for p in kept) - margin,
            max(p[0] for p in kept) + margin, max(p[1] for p in kept) + margin)


def get_site_pack_bounds(site_path):
    # type: (str) -> tuple
    """시군구 필지 팩의 범위(get_core_bounds — 필지 경계상자 중심). 같은 시군구의 컨텍스트·등고선 팩도 이 범위를 쓴다."""
    connection = sqlite3.connect(site_path)
    points = [((a + b) * 0.5, (c + d) * 0.5) for a, b, c, d in connection.execute("SELECT min_x, max_x, min_y, max_y FROM parcels")]
    connection.close()
    return get_core_bounds(points)


def get_deploy_module_names():
    # type: () -> list
    """.pyc로 컴파일해 배포할 로직 모듈 이름(정렬). 진입 스크립트·개발 전용·loader를 뺀다."""
    names = []
    for file_name in sorted(os.listdir(SCRIPTS_DIR)):
        if not file_name.endswith(".py") or file_name.startswith(EXCLUDED_MODULE_PREFIXES):
            continue
        name = file_name[:-3]
        if name != "loader" and name not in YAK_EXCLUDED_NAMES:
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
    """Gorani 명령 하나짜리 rhproj를 쓰고 rhinocode로 빌드한다. 빌드 결과 폴더(rhp·rui·manifest.yml)를 돌려준다."""
    os.makedirs(os.path.join(project_dir, "commands"))
    with open(os.path.join(project_dir, "commands", COMMAND_NAME + ".py"), "w", encoding="utf-8") as f:
        f.write(COMMAND_SOURCE % {"plugin_id": PLUGIN_ID})
    project = {
        # rhinocode가 host를 보고 8.11 미만에서 저장한 프로젝트로 판정하면 거부한다 — os·arch까지 있어야 통과(2026-10-12 실측)
        "host": {"name": "Rhino3D", "version": "8.35", "os": "macOS", "arch": "arm64"},
        "id": PLUGIN_ID,
        "identity": {
            "name": PACKAGE_NAME, "version": PACKAGE_VERSION, "publisher": PUBLISHER, "license": "MIT",
            "description": "도시설계 착수용 대지 컨텍스트(건물·도로·지형·수계 3D, 베이스맵, 현황도). 명령: Gorani",
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


def _get_mark_svg(file_name, color):
    # type: (str, str) -> str
    """docs/brand의 마크 SVG(currentColor)를 한 색으로 칠한 문자열."""
    with open(os.path.join(BRAND_DIR, file_name), encoding="utf-8") as f:
        return f.read().strip().replace("currentColor", color)


def _set_rui_icons(rui_path):
    # type: (str) -> None
    """rhinocode가 쓴 .rui의 명령 아이콘(기본 회색 상자 SVG)을 Gorani 마크로 바꾼다. .rhproj의 아이콘 칸은 빌드에 반영되지 않아
    (2026-10-19 실측 — identity·codes에 icon·image·imageSet을 원문·base64로 넣어도 .rui는 기본 아이콘) 빌드 뒤에 갈아 끼운다.
    도구 막대는 24 px 안팎이라 작은 판(gorani_mark_small.svg)을 쓴다."""
    with open(rui_path, encoding="utf-8") as f:
        text = f.read()
    for mode, color in TOOLBAR_ICON_COLORS.items():
        svg = _get_mark_svg("gorani_mark_small.svg", color)
        text, count = re.subn(r"<%s>.*?</%s>" % (mode, mode), lambda m: "<%s>%s</%s>" % (mode, svg, mode), text, flags=re.S)
        if not count:
            sys.exit(".rui에 <%s> 아이콘 자리가 없습니다 — rhinocode 출력 형식이 바뀌었는지 확인하세요: %s" % (mode, rui_path))
    with open(rui_path, "w", encoding="utf-8") as f:
        f.write(text)


def build_yak():
    # type: () -> str
    """build/yak/ 아래에서 스크립트를 모으고 플러그인을 빌드해 .yak 하나를 build/에 만든다. 경로를 돌려준다."""
    work_dir = os.path.join(BUILD_DIR, "yak")
    shutil.rmtree(work_dir, ignore_errors=True)
    package_dir = os.path.join(work_dir, "package")
    os.makedirs(package_dir)
    print("  로직 모듈 %d개 컴파일" % _stage_scripts(package_dir))
    plugin_dir = _build_plugin(os.path.join(work_dir, "project"))
    for file_name in (PACKAGE_NAME + ".rhp", PACKAGE_NAME + ".rui"):
        shutil.copyfile(os.path.join(plugin_dir, file_name), os.path.join(package_dir, file_name))
    _set_rui_icons(os.path.join(package_dir, PACKAGE_NAME + ".rui"))
    shutil.copyfile(os.path.join(BRAND_DIR, "png", "gorani_128.png"), os.path.join(package_dir, "icon.png"))   # PackageManager 목록 아이콘
    with open(os.path.join(package_dir, "manifest.yml"), "w", encoding="utf-8") as f:
        f.write(YAK_MANIFEST % {"name": PACKAGE_NAME, "version": PACKAGE_VERSION, "author": PUBLISHER["name"],
                                "url": WEBSITE_URL, "plugin_id": PLUGIN_ID})
    result = subprocess.run([os.path.join(RHINO_BIN_DIR, "yak"), "build", "--platform", "any"],
                            cwd=package_dir, capture_output=True, text=True)
    packages = [name for name in os.listdir(package_dir) if name.endswith(".yak")]
    if result.returncode != 0 or len(packages) != 1:
        sys.exit("yak build 실패\n%s%s" % (result.stdout, result.stderr))
    target = os.path.join(BUILD_DIR, packages[0])
    shutil.move(os.path.join(package_dir, packages[0]), target)
    return target


# ── blender ─────────────────────────────────────────────

def get_package_source(source, module_names):
    # type: (str, list) -> str
    """프로젝트 모듈 import를 패키지 상대 import로 바꾼 소스(`import constants` → `from . import constants`,
    `from context_builder import X` → `from .context_builder import X`). Blender 확장 정책이 최상위 모듈·sys.path 변경을 막는다 —
    Rhino판은 scripts/를 sys.path에 넣는 평범한 import 그대로 둔다."""
    pattern = re.compile(r"^(\s*)(import|from) (%s)\b" % "|".join(sorted(module_names, key=len, reverse=True)), re.M)
    return pattern.sub(lambda m: "%sfrom . import %s" % (m.group(1), m.group(3)) if m.group(2) == "import" else "%sfrom .%s" % (m.group(1), m.group(3)), source)


def _run_blender(*args):
    # type: (str) -> None
    result = subprocess.run([BLENDER_APP, "-b", "--factory-startup", "-c", "extension"] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("Blender %s 실패\n%s%s" % (args[0], result.stdout, result.stderr))


def build_blender():
    # type: () -> str
    """build/blender/gorani/에 확장 폴더를 모아 zip으로 묶고, build/blender_repo/에 zip과 정적 저장소 색인을 만든다. zip 경로를 돌려준다."""
    work_dir = os.path.join(BUILD_DIR, "blender")
    repo_dir = os.path.join(BUILD_DIR, "blender_repo")
    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(repo_dir, ignore_errors=True)
    package_dir = os.path.join(work_dir, BLENDER_PACKAGE_ID)
    target = os.path.join(package_dir, "scripts")
    os.makedirs(target)
    names = [n for n in sorted(os.listdir(SCRIPTS_DIR)) if n.endswith(".py") and n not in BLENDER_EXCLUDED_NAMES
             and not n.startswith(("dev_", "probe_", "server_", "sketchup_", "web_"))]
    for name in names:
        with open(os.path.join(SCRIPTS_DIR, name), encoding="utf-8") as f:
            source = get_package_source(f.read(), [n[:-3] for n in names])
        with open(os.path.join(target, name), "w", encoding="utf-8") as f:
            f.write(source)
    with open(os.path.join(target, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Gorani 로직 모듈 — Blender 확장에서는 하위 패키지."""\n')
    for name in UI_FILE_NAMES:
        shutil.copyfile(os.path.join(SCRIPTS_DIR, name), os.path.join(target, name))
    for dir_name in UI_DIR_NAMES:
        shutil.copytree(os.path.join(SCRIPTS_DIR, dir_name), os.path.join(target, dir_name), ignore=shutil.ignore_patterns(*BLENDER_EXCLUDED_ASSETS))
    for path in DOC_FILE_NAMES:
        os.makedirs(os.path.join(package_dir, os.path.dirname(path)), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT_DIR, path), os.path.join(package_dir, path))
    shutil.copyfile(BLENDER_LICENSE_PATH, os.path.join(package_dir, "LICENSE"))
    with open(os.path.join(package_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(BLENDER_INIT_SOURCE)
    with open(os.path.join(package_dir, "blender_manifest.toml"), "w", encoding="utf-8") as f:
        f.write(BLENDER_MANIFEST % {"id": BLENDER_PACKAGE_ID, "version": PACKAGE_VERSION, "name": PACKAGE_NAME,
                                    "maintainer": "%s <%s>" % (PUBLISHER["name"], PUBLISHER["email"])})
    print("  모듈 %d개" % len(names))
    os.makedirs(repo_dir)
    _run_blender("build", "--source-dir", package_dir, "--output-dir", repo_dir)
    _run_blender("server-generate", "--repo-dir", repo_dir, "--html")
    return os.path.join(repo_dir, "%s-%s.zip" % (BLENDER_PACKAGE_ID, PACKAGE_VERSION))


# ── sketchup ────────────────────────────────────────────

SKETCHUP_EXT_ID = "bsh_gorani"          # 뿌리 .rb·폴더 이름(Extension Warehouse 규칙 — 개발자 접두어 + 둘이 같은 이름)
SKETCHUP_PYTHON_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.12.15%%2B20261013-%s-install_only_stripped.tar.gz"
SKETCHUP_PYTHON_VERSION = "3.12"
SKETCHUP_PLATFORMS = {   # 폴더: (python-build-standalone 대상, pip 플랫폼 태그 — 앞이 우선, macOS 14 전용 Accelerate 휠은 넣지 않는다)
    "mac-arm64": ("aarch64-apple-darwin", ("macosx_11_0_arm64",)),
    "mac-x64": ("x86_64-apple-darwin", ("macosx_11_0_x86_64", "macosx_10_13_x86_64", "macosx_10_9_x86_64")),
    "win-x64": ("x86_64-pc-windows-msvc", ("win_amd64",)),
}
SKETCHUP_PIP_PACKAGES = ("numpy", "shapely>=2.1")   # shapely 2.1+ = constrained_delaunay_triangles(mesh_geometry 겹치기 CDT)
SKETCHUP_PLAIN_NAMES = ("loader.py", "cmd_site.py", "cmd_sketchup.py")
SKETCHUP_EXCLUDED_NAMES = ("panel_host", "cmd_install", "blender_baker")   # Rhino·Blender 전용
# 런타임에서 뺄 것(번들 크기) — 런타임 루트 기준 glob. 표준 라이브러리 lib/python3.12(맥)·Lib(윈도)는 {lib}로 쓴다
# 맥 실행 파일 python3.12는 정적 링크라 libpython dylib가 필요 없고, bin/python·python3 링크는 zip에서 18 MB 사본이 된다(2026-10-18 실측)
SKETCHUP_PYTHON_DROP = ("bin/2to3*", "bin/idle3*", "bin/pip*", "bin/pydoc3*", "bin/python3*-config", "bin/python", "bin/python3", "lib/libpython3*.dylib",
                        "include", "share", "lib/pkgconfig",
                        "lib/tcl*", "lib/tk*", "lib/itcl*", "lib/thread*", "lib/libtcl*", "lib/libtk*", "Scripts", "libs", "tcl",
                        "DLLs/_tkinter.pyd", "DLLs/tcl*.dll", "DLLs/tk*.dll", "{lib}/config-3.12-darwin", "{lib}/lib-dynload/_tkinter*",
                        "{lib}/idlelib", "{lib}/tkinter", "{lib}/turtledemo", "{lib}/test", "{lib}/ensurepip", "{lib}/lib2to3", "{lib}/pydoc_data",
                        "{lib}/site-packages/pip", "{lib}/site-packages/pip-*", "{lib}/site-packages/numpy/**/tests", "{lib}/site-packages/shapely/tests")
SKETCHUP_ROOT_SOURCE = '''# Gorani — 도시설계 착수용 대지 컨텍스트(주변 건물·도로·지형·수계 3D, 베이스맵, 현황도). 본문은 %(id)s/main.rb
require "sketchup.rb"
require "extensions.rb"

module BSH
  module Gorani
    unless file_loaded?(__FILE__)
      extension = SketchupExtension.new("Gorani", "%(id)s/main")
      extension.description = "필지·주소로 대상지를 고르면 주변 건물·도로·지형·수계를 3D로 만들고 베이스맵(.ai)·현황도(SVG)를 냅니다. " \\
                              "한국은 공공데이터, 해외는 OpenStreetMap. Extensions > Gorani"
      extension.version = "%(version)s"
      extension.creator = "%(creator)s"
      extension.copyright = "%(year)s %(creator)s"
      Sketchup.register_extension(extension, true)
      file_loaded(__FILE__)
    end
  end
end
'''


def _get_python_runtime(platform):
    # type: (str) -> str
    """python-build-standalone tar를 build/cache/에 받아 두고 경로를 돌려준다(있으면 다시 받지 않는다)."""
    url = SKETCHUP_PYTHON_URL % SKETCHUP_PLATFORMS[platform][0]
    path = os.path.join(BUILD_DIR, "cache", os.path.basename(url).replace("%2B", "+"))
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print("  받기 %s" % os.path.basename(path))
        subprocess.run(["curl", "-sSLf", "-o", path + ".part", url], check=True)
        os.replace(path + ".part", path)
    return path


def _get_site_packages(runtime_dir):
    # type: (str) -> str
    win = os.path.exists(os.path.join(runtime_dir, "python.exe"))
    return os.path.join(runtime_dir, "Lib" if win else os.path.join("lib", "python" + SKETCHUP_PYTHON_VERSION), "site-packages")


def _stage_python(python_dir):
    # type: (str) -> str
    """플랫폼마다 런타임을 풀고 numpy·shapely 휠을 깔고 줄인 뒤 .pyc(unchecked-hash)를 만든다. 이 Mac에서 돌릴 파이썬 경로를 돌려준다."""
    import glob
    import tarfile
    host_python = os.path.join(python_dir, "mac-arm64", "bin", "python3.12")
    for platform in SKETCHUP_PLATFORMS:   # mac-arm64가 처음 — 그 pip로 다른 플랫폼 휠도 받는다
        runtime_dir = os.path.join(python_dir, platform)
        with tarfile.open(_get_python_runtime(platform)) as tar:
            tar.extractall(python_dir)   # 공식 릴리스(HTTPS) — 이것을 그대로 배포한다
        os.rename(os.path.join(python_dir, "python"), runtime_dir)
        site = _get_site_packages(runtime_dir)
        platform_args = [arg for tag in SKETCHUP_PLATFORMS[platform][1] for arg in ("--platform", tag)]
        subprocess.run([host_python, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade", "--target", site,
                        "--only-binary=:all:", "--implementation", "cp", "--python-version", SKETCHUP_PYTHON_VERSION] + platform_args
                       + list(SKETCHUP_PIP_PACKAGES), check=True)
    for platform in SKETCHUP_PLATFORMS:
        runtime_dir = os.path.join(python_dir, platform)
        lib = os.path.relpath(os.path.dirname(_get_site_packages(runtime_dir)), runtime_dir)
        for pattern in SKETCHUP_PYTHON_DROP:
            for path in glob.glob(os.path.join(runtime_dir, pattern.format(lib=lib)), recursive=True):
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                elif os.path.lexists(path):
                    os.remove(path)
        shutil.rmtree(os.path.join(_get_site_packages(runtime_dir), "bin"), ignore_errors=True)
        subprocess.run([host_python, "-m", "compileall", "-q", "-f", "-j", "0", "--invalidation-mode", "unchecked-hash",
                        os.path.join(runtime_dir, lib)], check=True)
    return host_python


def build_sketchup():
    # type: () -> str
    """build/sketchup/에 확장 폴더를 모아 build/bsh_gorani-<버전>.rbz로 묶는다. rbz 경로를 돌려준다."""
    import zipfile
    work_dir = os.path.join(BUILD_DIR, "sketchup")
    shutil.rmtree(work_dir, ignore_errors=True)
    ext_dir = os.path.join(work_dir, SKETCHUP_EXT_ID)
    target = os.path.join(ext_dir, "scripts")
    os.makedirs(target)
    host_python = _stage_python(os.path.join(ext_dir, "python"))
    for name in SKETCHUP_PLAIN_NAMES + UI_FILE_NAMES:
        shutil.copyfile(os.path.join(SCRIPTS_DIR, name), os.path.join(target, name))
    for dir_name in UI_DIR_NAMES:
        shutil.copytree(os.path.join(SCRIPTS_DIR, dir_name), os.path.join(target, dir_name))
    names = [n[:-3] for n in sorted(os.listdir(SCRIPTS_DIR)) if n.endswith(".py") and n[:-3] not in SKETCHUP_EXCLUDED_NAMES
             and n[:-3] != "loader" and not n.startswith(("dev_", "cmd_", "probe_", "server_", "blender_", "web_"))]
    compile_source = ("import py_compile, sys\nsource, target = sys.argv[1:3]\n"
                      "for name in sys.argv[3:]:\n"
                      "    py_compile.compile(source + '/' + name + '.py', cfile=target + '/' + name + '.pyc', dfile=name + '.py', doraise=True, optimize=2)\n")
    subprocess.run([host_python, "-I", "-c", compile_source, SCRIPTS_DIR, target] + names, check=True)
    shutil.copyfile(os.path.join(SCRIPTS_DIR, "sketchup_ext.rb"), os.path.join(ext_dir, "main.rb"))
    os.makedirs(os.path.join(ext_dir, "icons"))
    # 도구 막대 아이콘 — Windows는 SVG, macOS는 PNG(SketchUp 맥은 SVG 대신 PDF를 받는다 — PNG는 48 px를 줄여 그린다)
    with open(os.path.join(ext_dir, "icons", "gorani.svg"), "w", encoding="utf-8") as f:
        f.write(_get_mark_svg("gorani_mark_small.svg", TOOLBAR_ICON_COLORS["light"]))
    shutil.copyfile(os.path.join(BRAND_DIR, "png", "gorani_48.png"), os.path.join(ext_dir, "icons", "gorani.png"))
    for path in DOC_FILE_NAMES:
        os.makedirs(os.path.join(ext_dir, os.path.dirname(path)), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT_DIR, path), os.path.join(ext_dir, path))
    with open(os.path.join(work_dir, SKETCHUP_EXT_ID + ".rb"), "w", encoding="utf-8") as f:
        f.write(SKETCHUP_ROOT_SOURCE % {"id": SKETCHUP_EXT_ID, "version": PACKAGE_VERSION, "creator": PUBLISHER["name"],
                                        "year": datetime.date.today().year})
    print("  로직 모듈 %d개 컴파일" % len(names))
    rbz = os.path.join(BUILD_DIR, "%s-%s.rbz" % (SKETCHUP_EXT_ID, PACKAGE_VERSION))
    with zipfile.ZipFile(rbz, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for folder, _dirs, files in os.walk(work_dir):
            for name in sorted(files):
                path = os.path.join(folder, name)
                zf.write(path, os.path.relpath(path, work_dir))   # 심볼릭 링크는 원본 내용으로(rbz를 푸는 SketchUp이 링크를 모른다)
    return rbz


# ── web ─────────────────────────────────────────────────

WEB_DIR = os.path.join(BUILD_DIR, "web")
WEB_EXCLUDED_PREFIXES = ("dev_", "probe_", "server_", "blender_", "sketchup_")
WEB_EXCLUDED_NAMES = ("panel_host", "panel_server", "cmd_install", "cmd_blender", "cmd_sketchup")   # Rhino·Blender·SketchUp 연결


def build_web():
    # type: () -> str
    """build/web/에 웹판 정적 파일을 모은다. 폴더 경로를 돌려준다."""
    import zipfile
    sys.path.insert(0, SCRIPTS_DIR)
    import panel_server
    shutil.rmtree(WEB_DIR, ignore_errors=True)
    os.makedirs(WEB_DIR)
    shutil.copyfile(os.path.join(SCRIPTS_DIR, "web_app.html"), os.path.join(WEB_DIR, "index.html"))
    shutil.copyfile(os.path.join(SCRIPTS_DIR, "web_worker.js"), os.path.join(WEB_DIR, "web_worker.js"))
    with open(os.path.join(WEB_DIR, "panel.html"), "w", encoding="utf-8") as f:
        f.write(panel_server.get_html())
    names = [n for n in sorted(os.listdir(SCRIPTS_DIR)) if n.endswith(".py") and not n.startswith(WEB_EXCLUDED_PREFIXES)
             and n[:-3] not in WEB_EXCLUDED_NAMES]
    with zipfile.ZipFile(os.path.join(WEB_DIR, "scripts.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in names:
            zf.write(os.path.join(SCRIPTS_DIR, name), name)
    print("  모듈 %d개 · scripts.zip %.0f KB · panel.html %.0f KB" % (len(names), os.path.getsize(os.path.join(WEB_DIR, "scripts.zip")) / 1e3,
                                                                  os.path.getsize(os.path.join(WEB_DIR, "panel.html")) / 1e3))
    return WEB_DIR


# ── packs ───────────────────────────────────────────────

def _get_rounded(value, digits):
    # type: (object, int) -> object
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [_get_rounded(v, digits) for v in value]
    return value


def _rewrite_geometries(connection, table, id_column, where, digits, tolerance=None):
    # type: (sqlite3.Connection, str, str, str, int, float) -> None
    """geometry_json을 digits 자리로 반올림(공백 없는 JSON)하고, tolerance가 있으면 그만큼 단순화한다(shapely — 개발 환경 전용).
    id 구간 REWRITE_CHUNK씩 나눠 읽는다 — 충북 컨텍스트(9.6 GB)를 한 번에 읽었더니 스왑으로 3시간 멈췄다(2026-10-13)."""
    low, high = connection.execute("SELECT MIN(%s), MAX(%s) FROM %s" % (id_column, id_column, table)).fetchone()
    if low is None:
        return
    condition = (where + " AND" if where else "WHERE") + " %s BETWEEN ? AND ?" % id_column
    for start in range(low, high + 1, REWRITE_CHUNK):
        rows = connection.execute("SELECT %s, geometry_json FROM %s %s" % (id_column, table, condition), (start, start + REWRITE_CHUNK - 1)).fetchall()
        _rewrite_rows(connection, table, id_column, rows, digits, tolerance)
        connection.commit()


def _rewrite_rows(connection, table, id_column, rows, digits, tolerance):
    # type: (sqlite3.Connection, str, str, list, int, float) -> None
    updates = []
    for row_id, text in rows:
        geometry = json.loads(text)
        if tolerance:
            simplified = shapely.from_geojson(text).simplify(tolerance, preserve_topology=geometry["type"].endswith("Polygon"))
            if not simplified.is_empty:
                geometry = json.loads(shapely.to_geojson(simplified))
        geometry["coordinates"] = _get_rounded(geometry["coordinates"], digits)
        updates.append((json.dumps(geometry, separators=(",", ":")), row_id))
    connection.executemany("UPDATE %s SET geometry_json = ? WHERE %s = ?" % (table, id_column), updates)


def _aggregate_align_samples(connection):
    # type: (sqlite3.Connection) -> int
    """정합 샘플 점(theme qa, kind align_sample — 서울만 134만 행)을 도엽별 요약 1행(kind align_sheet)으로 바꾼다.
    value = 거리 중앙값, attrs {n, p90, dx, dy}, 점 = 샘플 평균 위치. 런타임은 n 가중평균으로 합친다(context_builder._get_align_stats)."""
    groups = {}
    for sheet, value, attrs, geometry, source_id, reference_date in connection.execute(
            "SELECT sheet, value, attrs_json, geometry_json, source_id, reference_date FROM features WHERE theme = 'qa' AND kind = 'align_sample'"):
        attrs = json.loads(attrs or "{}")
        group = groups.setdefault(sheet, {"values": [], "dx": [], "dy": [], "xy": [], "source": (source_id, reference_date)})
        group["values"].append(float(value))
        group["dx"].append(float(attrs.get("dx", 0.0)))
        group["dy"].append(float(attrs.get("dy", 0.0)))
        group["xy"].append(json.loads(geometry)["coordinates"])
    rows = []
    for sheet, group in groups.items():
        values = group["values"]
        x = sum(p[0] for p in group["xy"]) / len(values)
        y = sum(p[1] for p in group["xy"]) / len(values)
        attrs = {"n": len(values), "p90": round(statistics.quantiles(values, n=10)[8] if len(values) >= 2 else values[0], 2),
                 "dx": round(statistics.median(group["dx"]), 2), "dy": round(statistics.median(group["dy"]), 2)}
        rows.append((group["source"][0], "qa", "align_sheet", round(statistics.median(values), 2), json.dumps(attrs), sheet,
                     json.dumps({"type": "Point", "coordinates": [round(x, 2), round(y, 2)]}), constants.DATABASE_CRS, group["source"][1], x, x, y, y))
    connection.execute("DELETE FROM features WHERE theme = 'qa' AND kind = 'align_sample'")
    connection.executemany("""INSERT INTO features (source_id, theme, kind, value, attrs_json, sheet, geometry_json, geometry_crs,
                                  reference_date, min_x, max_x, min_y, max_y) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    return len(rows)


def slim_pack_database(connection, kind):
    # type: (sqlite3.Connection, str) -> None
    """배포 팩 용량 줄이기 — 원천 정확도(수치지형도 ±1.5 m, 지적 ±0.36 m)에 맞춰 정밀도를 낮추고 런타임이 안 쓰는 것을 뺀다.

    공통: 좌표 cm(0.01 m)·공백 없는 JSON. 등고선: 0.3 m 단순화 + 0.1 m(서울 실측 163 → 67 MB). 계획 도형: 0.1 m 단순화.
    컨텍스트: 정합 샘플 → 도엽 요약, 피처 속성의 UFID(원천 식별자, 런타임 미사용 — 서울 약 45 MB) 삭제.
    필지: 파생 계획 도형의 필지 연결표(parcel_land_use와 같은 정보)·빌드용 지목 인덱스 삭제.
    처리한 팩은 PRAGMA application_id = SLIM_PACK_ID로 표시한다(repack이 두 번 줄이지 않게).
    """
    if kind == "site":
        connection.execute("DROP INDEX IF EXISTS idx_parcels_category")
        connection.execute("DELETE FROM parcel_overlays WHERE overlay_id IN (SELECT overlay_id FROM overlays WHERE source_id = 'molit_land_use')")
        _rewrite_geometries(connection, "parcels", "parcel_id", "", 2)
        _rewrite_geometries(connection, "overlays", "overlay_id", "", 2, 0.1)
    else:
        if kind == "context":
            _aggregate_align_samples(connection)
            _rewrite_geometries(connection, "buildings", "building_id", "", 2)
        _rewrite_geometries(connection, "features", "feature_id", "WHERE theme = 'terrain' AND kind = 'contour'", 1, 0.3)
        _rewrite_geometries(connection, "features", "feature_id", "WHERE NOT (theme = 'terrain' AND kind = 'contour')", 2)
        connection.execute("UPDATE features SET attrs_json = json_remove(attrs_json, '$.UFID') WHERE attrs_json LIKE '%\"UFID\"%'")
        connection.execute("UPDATE features SET attrs_json = NULL WHERE attrs_json = '{}'")
    connection.execute("PRAGMA application_id = %d" % SLIM_PACK_ID)
    connection.commit()


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
    slim_pack_database(connection, pack_name.rsplit("_", 1)[1][:-3])
    connection.execute("ANALYZE")
    connection.execute("VACUUM")
    connection.close()


class SggMap:
    """200 m 격자 → 시군구 코드(격자 안 필지 중심이 가장 많은 시군구). 필지 없는 격자는 가장 가까운 격자를 따른다."""

    def __init__(self, site_path):
        counts, names = {}, {}
        connection = sqlite3.connect(site_path)
        for sgg, x, y, address in connection.execute(
                "SELECT substr(pnu, 1, 5), (min_x + max_x) / 2, (min_y + max_y) / 2, address FROM parcels"):
            cell = (int(x // SPLIT_CELL), int(y // SPLIT_CELL))
            bucket = counts.setdefault(cell, {})
            bucket[sgg] = bucket.get(sgg, 0) + 1
            if sgg not in names:
                names[sgg] = _get_sgg_name(address)
        connection.close()
        self.cells = {cell: max(bucket.items(), key=lambda item: item[1])[0] for cell, bucket in counts.items()}
        self.names = names

    def get_sggs(self, min_x, min_y, max_x, max_y):
        # type: (float, float, float, float) -> set
        """경계상자가 걸치는 격자의 시군구들. 하나도 없으면 중심에서 가까운 격자(최대 SPLIT_SEARCH칸)의 시군구 하나."""
        x0, y0, x1, y1 = int(min_x // SPLIT_CELL), int(min_y // SPLIT_CELL), int(max_x // SPLIT_CELL), int(max_y // SPLIT_CELL)
        found = {self.cells[(x, y)] for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (x, y) in self.cells}
        if found:
            return found
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        for radius in range(1, SPLIT_SEARCH + 1):
            ring = [(cx + dx, cy + dy) for dx in range(-radius, radius + 1) for dy in (-radius, radius)]
            ring += [(cx + dx, cy + dy) for dx in (-radius, radius) for dy in range(-radius + 1, radius)]
            hits = [self.cells[c] for c in ring if c in self.cells]
            if hits:
                return {max(set(hits), key=hits.count)}
        return set()


def _get_sgg_name(address):
    # type: (str) -> str
    """'경기도 성남시 분당구 정자동 1' → '성남시 분당구', '서울특별시 성동구 성수동2가 1' → '성동구'."""
    parts = (address or "").split()
    if len(parts) >= 3 and parts[1].endswith("시") and parts[2].endswith("구"):
        return "%s %s" % (parts[1], parts[2])
    return parts[1] if len(parts) > 1 else ""


def _copy_rows(source_path, target_path, plan, user_version):
    # type: (str, str, dict, int) -> None
    """source의 테이블을 target에 같은 스키마로 만들고 plan대로 행을 옮긴다. plan = {테이블: None(전부) | (id 열, id 목록) | "pnu5:<코드>"}.
    인덱스는 행을 다 넣은 뒤 만든다(빠르다)."""
    connection = sqlite3.connect(target_path)
    connection.execute("ATTACH DATABASE ? AS source", (source_path,))
    schema = connection.execute("SELECT type, name, tbl_name, sql FROM source.sqlite_master WHERE sql IS NOT NULL").fetchall()
    plan = {table: rule for table, rule in plan.items() if any(kind == "table" and name == table for kind, name, _t, _s in schema)}
    for kind, name, table, sql in schema:
        if kind == "table" and table in plan:
            connection.execute(sql)
    connection.execute("CREATE TEMP TABLE keep (id INTEGER PRIMARY KEY)")
    for table, rule in plan.items():
        if rule is None:
            connection.execute('INSERT INTO "%s" SELECT * FROM source."%s"' % (table, table))
        elif isinstance(rule, str):
            connection.execute('INSERT INTO "%s" SELECT * FROM source."%s" WHERE substr(pnu, 1, 5) = ?' % (table, table), (rule[5:],))
        else:
            column, ids = rule
            connection.execute("DELETE FROM keep")
            connection.executemany("INSERT OR IGNORE INTO keep VALUES (?)", ((i,) for i in ids))
            connection.execute('INSERT INTO "%s" SELECT * FROM source."%s" WHERE %s IN (SELECT id FROM keep)' % (table, table, column))
    for kind, name, table, sql in schema:
        if kind == "index" and table in plan:
            connection.execute(sql)
    connection.execute("PRAGMA user_version = %d" % user_version)
    connection.execute("PRAGMA application_id = %d" % SLIM_PACK_ID)
    connection.commit()
    connection.execute("DETACH DATABASE source")
    connection.execute("ANALYZE")
    connection.close()


def _get_ids_by_sgg(path, table, id_column, sgg_map, pnu_column=None):
    # type: (str, str, str, SggMap, str) -> dict
    """테이블 행 → {시군구: [id]}. pnu_column이 있고 값이 있으면 그 시군구 하나, 아니면 경계상자가 걸치는 격자의 시군구 전부."""
    result = {}
    connection = sqlite3.connect(path)
    columns = "%s, min_x, min_y, max_x, max_y" % id_column + (", %s" % pnu_column if pnu_column else "")
    for row in connection.execute("SELECT %s FROM %s" % (columns, table)):
        pnu = row[5] if pnu_column else None
        sggs = {pnu[:5]} if pnu and len(pnu) == constants.PNU_LENGTH else sgg_map.get_sggs(*row[1:5])
        for sgg in sggs:
            result.setdefault(sgg, []).append(row[0])
    connection.close()
    return result


def split_sido_packs(slug, pack_dir):
    # type: (str, str) -> list
    """pack_dir의 <시도>_site·_context·_terrain.db(줄인 팩)를 시군구 팩 <코드>_<종류>.db로 나눈다. [(이름, 표시 이름, 경로)]. 시도 파일은 지운다.

    필지·토지이용계획·필지 연결표는 PNU 앞 5자리로, 계획 도형·건물(PNU 없는 보충 건물)·피처는 경계상자가 걸치는 200 m 격자의 시군구 전부로
    (경계 객체는 양쪽 팩에 들어간다 — 시군구 팩 하나만 받아도 그 지역은 빠짐없이 나온다. 런타임이 id로 중복을 걷어 낸다).
    """
    site = os.path.join(pack_dir, slug + "_site.db")
    sgg_map = SggMap(site)
    sido_name = next(name for name, s in constants.SIDO.values() if s == slug)
    version = {kind: sqlite3.connect(os.path.join(pack_dir, "%s_%s.db" % (slug, kind))).execute("PRAGMA user_version").fetchone()[0]
               for kind in ("site", "context", "terrain") if os.path.exists(os.path.join(pack_dir, "%s_%s.db" % (slug, kind)))}
    overlay_ids = _get_ids_by_sgg(site, "overlays", "overlay_id", sgg_map)
    out = []
    for sgg in sorted(sgg_map.names):
        target = os.path.join(pack_dir, "%s_site.db" % sgg)
        if os.path.exists(target):
            os.remove(target)
        _copy_rows(site, target, {"data_sources": None, "parcels": "pnu5:" + sgg, "parcel_land_use": "pnu5:" + sgg,
                                  "parcel_overlays": "pnu5:" + sgg, "overlays": ("overlay_id", overlay_ids.get(sgg, []))}, version["site"])
        out.append(("%s_site.db" % sgg, "%s %s 필지" % (sido_name, sgg_map.names[sgg]), target))
    for kind, label in (("context", "건물·도로·수계"), ("terrain", "등고선")):
        source = os.path.join(pack_dir, "%s_%s.db" % (slug, kind))
        if not os.path.exists(source):
            continue
        feature_ids = _get_ids_by_sgg(source, "features", "feature_id", sgg_map)
        building_ids = _get_ids_by_sgg(source, "buildings", "building_id", sgg_map, "pnu") if kind == "context" else {}
        for sgg in sorted(sgg_map.names):
            target = os.path.join(pack_dir, "%s_%s.db" % (sgg, kind))
            if os.path.exists(target):
                os.remove(target)
            plan = {"data_sources": None, "features": ("feature_id", feature_ids.get(sgg, []))}
            if kind == "context":
                plan.update({"source_files": None, "buildings": ("building_id", building_ids.get(sgg, []))})
            _copy_rows(source, target, plan, version[kind])
            out.append(("%s_%s.db" % (sgg, kind), "%s %s %s" % (sido_name, sgg_map.names[sgg], label), target))
    for kind in ("site", "context", "terrain"):
        path = os.path.join(pack_dir, "%s_%s.db" % (slug, kind))
        if os.path.exists(path):
            os.remove(path)
    return out


def _get_sha256(path):
    # type: (str) -> str
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _update_manifest(pack_dir, slug, entries):
    # type: (str, str, list) -> str
    """매니페스트에서 그 시도의 항목(시도 팩 <slug>_* 와 그 시도 시군구 팩)을 빼고 entries를 넣는다. 파일 잠금 — 시도 여러 개를 동시에 압축한다."""
    import fcntl
    manifest_path = os.path.join(pack_dir, "manifest.json")
    code = next(c for c, (_name, s) in constants.SIDO.items() if s == slug)
    with open(manifest_path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        packs = {}
        if os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as f:
                packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
        packs = {name: pack for name, pack in packs.items()
                 if not name.startswith(slug + "_") and not (name[:5].isdigit() and name[:2] == code)}
        packs.update({entry["name"]: entry for entry in entries})
        with open(manifest_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"version": datetime.date.today().isoformat(), "packs": sorted(packs.values(), key=lambda p: p["name"])},
                      f, ensure_ascii=False, indent=1)
        os.replace(manifest_path + ".tmp", manifest_path)
    return manifest_path


def _split_and_compress(slug, pack_dir):
    # type: (str, str) -> list
    """pack_dir의 시도 팩 DB(줄인 것) → 시군구 팩 → xz. 빈 팩은 버린다. 매니페스트 항목 목록."""
    entries, sgg_bounds = [], {}
    for name, label, path in split_sido_packs(slug, pack_dir):   # 필지 팩이 먼저 나온다
        kind = name.rsplit("_", 1)[1][:-3]
        connection = sqlite3.connect(path)
        bounds = connection.execute(BOUNDS_SQL[kind]).fetchone()
        if kind == "context" and bounds[0] is None:   # 건물 없는 시군구(섬 등) — 피처 범위로
            bounds = connection.execute(BOUNDS_SQL["terrain"]).fetchone()
        connection.close()
        if bounds[0] is None:
            os.remove(path)
            continue
        if kind == "site":
            sgg_bounds[name[:5]] = get_site_pack_bounds(path)
        bounds = sgg_bounds.get(name[:5]) or bounds
        size, sha256 = os.path.getsize(path), _get_sha256(path)
        subprocess.run(["xz", "-6", "-T0", "-f", path], check=True)
        entries.append({"name": name, "label": label, "url": name + ".xz", "size": size, "sha256": sha256,
                        "bounds": [round(v, 1) for v in bounds], "xz_size": os.path.getsize(path + ".xz")})
    print("  %s → 시군구 팩 %d개 (압축 %.2f GB)" % (slug, len(entries), sum(e["xz_size"] for e in entries) / 1024.0 ** 3), flush=True)
    return entries


def build_packs(sido_codes=None, drop=False):
    # type: (list, bool) -> str
    """data/의 시도 DB → 줄인 시도 팩 DB → 시군구 팩(<시군구코드>_<종류>.db.xz) + manifest.json. 매니페스트 경로를 돌려준다.

    사용자는 대상지에 걸리는 시군구 팩만 받는다(data_pack). sido_codes를 주면 그 시도만 만들고 다른 시도 항목은 그대로 둔다.
    drop이면 압축 뒤 원본 DB(data/<시도>_site.db·_context.db)를 지운다 — 서울은 개발용이라 남긴다. 전국 원본은 디스크에 다 못 둔다.
    """
    pack_dir = os.path.join(BUILD_DIR, "packs")
    os.makedirs(pack_dir, exist_ok=True)
    manifest_path = os.path.join(pack_dir, "manifest.json")
    data_dir = os.path.join(ROOT_DIR, "data")
    for code, (sido_name, slug) in sorted(constants.SIDO.items(), key=lambda item: item[1][1]):
        if sido_codes and code not in sido_codes:
            continue
        sources = set()
        for kind, _label, source_kind in PACK_KINDS:
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
        if not sources:
            continue
        manifest_path = _update_manifest(pack_dir, slug, _split_and_compress(slug, pack_dir))
        for kind in ("site", "context", "terrain"):   # 옛 시도 팩 압축본
            old = os.path.join(pack_dir, "%s_%s.db.xz" % (slug, kind))
            if os.path.exists(old):
                os.remove(old)
        if drop and code != "11":
            for source in sources:
                os.remove(source)
    return manifest_path


def repack():
    # type: () -> list
    """build/packs/의 시도 팩 압축본(<시도>_<종류>.db.xz)을 풀어 줄이고(slim 이전 팩이면) 시군구 팩으로 나눠 다시 압축한다. 처리한 시도 목록.
    원본 DB를 지운 시도도 팩에서 바로 다시 만들 수 있다."""
    pack_dir = os.path.join(BUILD_DIR, "packs")
    done = []
    for code, (_name, slug) in sorted(constants.SIDO.items(), key=lambda item: item[1][1]):
        archives = [os.path.join(pack_dir, "%s_%s.db.xz" % (slug, kind)) for kind in ("site", "context", "terrain")]
        if not os.path.exists(archives[0]):
            continue
        print("  %s 풀기..." % slug, flush=True)
        for archive in archives:
            if not os.path.exists(archive):
                continue
            subprocess.run(["xz", "-d", "-f", "-T0", archive], check=True)
            path = archive[:-3]
            connection = sqlite3.connect(path)
            if connection.execute("PRAGMA application_id").fetchone()[0] != SLIM_PACK_ID:
                slim_pack_database(connection, os.path.basename(path).rsplit("_", 1)[1][:-3])
                connection.execute("VACUUM")
            connection.close()
        _update_manifest(pack_dir, slug, _split_and_compress(slug, pack_dir))
        done.append(slug)
    _fill_manifest(pack_dir)
    return done


def _fill_manifest(pack_dir):
    # type: (str) -> list
    """매니페스트에 없는 시군구 팩 압축본을 풀어 크기·sha256·범위를 재고 항목을 채운다(동시 실행으로 항목이 덮어써진 경우, 2026-10-13 대전·서울)."""
    import fcntl
    manifest_path = os.path.join(pack_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        packs = json.load(f)["packs"]
    known = {pack["name"] for pack in packs}
    site_bounds = {pack["name"][:5]: pack["bounds"] for pack in packs if pack["name"].endswith("_site.db")}
    added = []
    for file_name in sorted(os.listdir(pack_dir), key=lambda n: (n[:5], not n.endswith("_site.db.xz"))):   # 필지 팩 먼저(이름)
        name = file_name[:-3]
        if not file_name.endswith(".db.xz") or not name[:5].isdigit() or name in known:
            continue
        path = os.path.join(pack_dir, name)
        subprocess.run(["xz", "-d", "-k", "-f", "-T0", path + ".xz"], check=True)
        kind = name.rsplit("_", 1)[1][:-3]
        connection = sqlite3.connect(path)
        bounds = connection.execute(BOUNDS_SQL[kind]).fetchone()
        if kind == "context" and bounds[0] is None:
            bounds = connection.execute(BOUNDS_SQL["terrain"]).fetchone()
        if kind == "site":
            bounds = get_site_pack_bounds(path) or bounds
        else:   # 같은 시군구 필지 팩 범위(이번에 채운 것 또는 매니페스트에 있는 것)
            bounds = next((p["bounds"] for p in added if p["name"] == name[:5] + "_site.db"), None) or site_bounds.get(name[:5]) or bounds
        sgg_name = ""
        if kind == "site":
            sgg_name = _get_sgg_name((connection.execute("SELECT address FROM parcels LIMIT 1").fetchone() or [""])[0])
        connection.close()
        if not sgg_name:   # 컨텍스트·등고선 팩 — 같은 시군구 필지 팩 항목의 이름을 따른다
            sgg_name = next((" ".join(p["label"].split()[1:-1]) for p in added if p["name"] == name[:5] + "_site.db"), "") or name[:5]
        code = name[:2]
        label = "%s %s %s" % (constants.SIDO[code][0], sgg_name, dict((k, l) for k, l, _s in PACK_KINDS)[kind])
        added.append({"name": name, "label": label, "url": file_name, "size": os.path.getsize(path), "sha256": _get_sha256(path),
                      "bounds": [round(v, 1) for v in bounds], "xz_size": os.path.getsize(path + ".xz")})
        os.remove(path)
    if added:
        with open(manifest_path + ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            manifest["packs"] = sorted(manifest["packs"] + added, key=lambda p: p["name"])
            with open(manifest_path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=1)
            os.replace(manifest_path + ".tmp", manifest_path)
    print("  매니페스트에 채운 팩 %d개" % len(added), flush=True)
    return added


DATASET_CARD = """---
license: other
license_name: kogl-type1-cc-by
pretty_name: Gorani 시군구 데이터 팩
language: [ko]
tags: [geospatial, korea, cadastral, buildings, rhino]
---
# Gorani 데이터 팩

Rhino 플러그인 Gorani가 대상지 주변만 받아 쓰는 시군구 단위 SQLite 팩(xz 압축). 좌표계 EPSG:5186.

- `<시군구코드>_site.db.xz` — 필지(토지특성정보 도형·속성), 토지이용계획 지정 현황, 계획 도형(서울 UPIS / 그 외 지정 코드로 필지를 합친 것)
- `manifest.json` — 팩 목록·sha256·범위. 플러그인이 읽는다.
- 건물·도로·수계·등고선 팩(`*_context`·`*_terrain`)은 여기 두지 않는다. 수치지형도(기본측량성과)에서 나온 자료라 국외 서버에 둘 수 없어
  (공간정보관리법 제16조) 국내 서버에 있고, 매니페스트에 그 주소가 적혀 있다.

## 출처·라이선스 (원천 그대로 — 가공: 재투영·병합·단순화·시군구 분할)
- 국토교통부 토지특성정보·토지이용계획정보 — 이용허락범위 제한 없음(공공데이터포털 15048121·15045900)
- 서울특별시 도시계획정보(UPIS) — 공공누리 제1유형
- 본 데이터는 정보제공 목적이며 법적 효력이 없다(국토교통부 국가중점데이터 안내).
"""


def upload():
    # type: () -> str
    """build/packs/의 시군구 팩을 올린다. 필지 팩 + 공개 매니페스트 + 설명은 Hugging Face 데이터셋(constants.DATA_REPO_ID, 공개),
    컨텍스트·등고선 팩은 국내 버킷(constants.DATA_DOMESTIC_BUCKET_URL)에 올리고 매니페스트에는 받기 주소(DATA_DOMESTIC_BASE_URL —
    문지기 서버 또는 버킷)로 적는다.

    `hf auth login`(쓰기 토큰)과 OCI CLI(`brew install oci-cli`, ~/.oci/config API 키)가 먼저 필요하다.
    둘 다 끊겨도 다시 실행하면 이어 올린다(upload_large_folder, oci sync는 크기가 다르거나 로컬이 더 새 파일만 올린다).
    """
    from huggingface_hub import HfApi
    pack_dir = os.path.join(BUILD_DIR, "packs")
    with open(os.path.join(pack_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    public = []
    for pack in manifest["packs"]:
        if not pack["name"][:5].isdigit():   # 옛 시도 팩
            continue
        if not pack["name"].endswith("_site.db"):
            pack = dict(pack, url=constants.DATA_DOMESTIC_BASE_URL + pack["url"])
        public.append(pack)
    # 주소 꼴: https://objectstorage.<리전>.oraclecloud.com/n/<namespace>/b/<bucket>/o/
    parts = constants.DATA_DOMESTIC_BUCKET_URL.rstrip("/").split("/")
    subprocess.run(["oci", "os", "object", "sync", "-ns", parts[-4], "-bn", parts[-2], "--src-dir", ".",
                    "--include", "[0-9]*_context.db.xz", "--include", "[0-9]*_terrain.db.xz"],
                   check=True, cwd=pack_dir, env=dict(os.environ, SUPPRESS_LABEL_WARNING="True"))   # --include는 현재 폴더 기준
    stage = os.path.join(BUILD_DIR, "hf_stage")
    os.makedirs(stage, exist_ok=True)
    with open(os.path.join(stage, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(dict(_read_notices(), version=manifest["version"], packs=public), f, ensure_ascii=False, indent=1)
    with open(os.path.join(stage, "README.md"), "w", encoding="utf-8") as f:
        f.write(DATASET_CARD)
    api = HfApi()
    api.create_repo(constants.DATA_REPO_ID, repo_type="dataset", private=False, exist_ok=True)
    api.upload_large_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=pack_dir,
                            allow_patterns=["[0-9][0-9][0-9][0-9][0-9]_site.db.xz"])
    api.upload_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=stage, commit_message="manifest·README")
    print("  올림: 팩 %d개 → https://huggingface.co/datasets/%s + %s" % (len(public), constants.DATA_REPO_ID,
                                                                        constants.DATA_DOMESTIC_BASE_URL), flush=True)
    return constants.DATA_MANIFEST_URL


def _read_notices():
    # type: () -> dict
    """docs/notices.json → {"update", "notices"}. 매니페스트를 올릴 때마다 넣어 팩을 다시 올려도 공지가 지워지지 않게 한다."""
    with open(NOTICES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    return {"update": data.get("update"), "notices": data.get("notices") or []}


def upload_notices():
    # type: () -> str
    """Hugging Face의 지금 매니페스트를 받아 update·notices만 docs/notices.json으로 바꿔 다시 올린다(팩·팩 목록은 그대로)."""
    import urllib.request
    from huggingface_hub import HfApi
    with urllib.request.urlopen(constants.DATA_MANIFEST_URL, timeout=constants.DATA_TIMEOUT_SECONDS) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    manifest.update(_read_notices())
    stage = os.path.join(BUILD_DIR, "hf_stage")
    os.makedirs(stage, exist_ok=True)
    path = os.path.join(stage, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    HfApi().upload_file(path_or_fileobj=path, path_in_repo="manifest.json", repo_id=constants.DATA_REPO_ID, repo_type="dataset",
                        commit_message="manifest: 업데이트·공지")
    print("  올림: update %s, 공지 %d개" % ("있음" if manifest["update"] else "없음", len(manifest["notices"])), flush=True)
    return constants.DATA_MANIFEST_URL


def rebounds():
    # type: () -> str
    """build/packs/의 시군구 필지 팩을 하나씩 풀어 범위(get_site_pack_bounds)를 다시 재고, 그 시군구 세 팩의 매니페스트 bounds를 바꾼다.
    팩 파일·sha256은 그대로라 올릴 때 매니페스트만 바뀐다(dev_deploy upload)."""
    import fcntl
    import tempfile
    pack_dir = os.path.join(BUILD_DIR, "packs")
    manifest_path = os.path.join(pack_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        sites = [pack["name"] for pack in json.load(f)["packs"] if pack["name"][:5].isdigit() and pack["name"].endswith("_site.db")]
    new_bounds = {}
    for index, name in enumerate(sites):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, name)
            with open(path, "wb") as out:
                subprocess.run(["xz", "-dc", "-T0", os.path.join(pack_dir, name + ".xz")], stdout=out, check=True)
            bounds = get_site_pack_bounds(path)
        if bounds:
            new_bounds[name[:5]] = [round(v, 1) for v in bounds]
        print("  %d/%d %s %s" % (index + 1, len(sites), name, new_bounds.get(name[:5])), flush=True)
    with open(manifest_path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        for pack in manifest["packs"]:
            if pack["name"][:5] in new_bounds:
                pack["bounds"] = new_bounds[pack["name"][:5]]
        with open(manifest_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        os.replace(manifest_path + ".tmp", manifest_path)
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description="Yak 패키지·Blender·SketchUp 확장·웹판·데이터 팩 빌드")
    parser.add_argument("what", nargs="?", default="all", choices=("all", "yak", "blender", "sketchup", "web", "packs", "repack", "upload", "notices", "rebounds"))
    parser.add_argument("--sido", help="packs: 쉼표로 구분한 시도 코드만 (기본 data/에 있는 전부)")
    parser.add_argument("--drop", action="store_true", help="packs: 압축 뒤 원본 시도 DB를 지운다(서울 제외)")
    args = parser.parse_args()
    if args.what in ("all", "yak") and sys.version_info[:2] != (3, 9):
        sys.exit("Rhino 8의 CPython(3.9)과 같은 Python 3.9로 실행해야 .pyc가 호환됩니다. 현재: %d.%d" % sys.version_info[:2])
    if args.what == "blender":
        print("blender: %s" % build_blender())
        print("  설치: Blender 4.2+ 환경 설정 > Get Extensions > Install from Disk, 또는 Blender -c extension install-file -r user_default -e <zip>")
        return
    if args.what == "sketchup":
        rbz = build_sketchup()
        print("sketchup: %s (%.0f MB)" % (rbz, os.path.getsize(rbz) / 1e6))
        print("  설치: SketchUp 2022+ 확장 > Extension Manager > Install Extension, 올리기: docs/sketchup_store.md")
        return
    if args.what == "web":
        print("web: %s" % build_web())
        print("  로컬 시험: python3 -m http.server -d build/web 8766 → http://127.0.0.1:8766/ (팩 주소는 ?manifest=)")
        return
    if args.what == "upload":
        print("manifest: %s" % upload())
        return
    if args.what == "notices":
        print("notices: %s" % upload_notices())
        return
    if args.what == "rebounds":
        print("rebounds: %s" % rebounds())
        return
    if args.what == "repack":
        print("repack: %s" % repack())
        return
    if args.what in ("all", "yak"):
        print("yak: %s" % build_yak())
    if args.what in ("all", "packs"):
        manifest_path = build_packs(args.sido.split(",") if args.sido else None, args.drop)
        print("packs: %s" % manifest_path)
        print("  올리기: python3 scripts/dev_deploy.py upload (필지 → Hugging Face, 컨텍스트·등고선 → 국내 버킷)")


if __name__ == "__main__":
    main()
