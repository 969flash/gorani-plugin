"""배포판 빌더 — 건축사에게 넘길 폴더를 만든다 (Rhino 밖 전용).

실행하면 폴더 선택창이 뜨고, 고른 위치 아래에 `UrbanDesignTool/` 배포판을 만든다.
진입 스크립트(loader·cmd_install·cmd_site)만 평문으로 두고 로직 모듈은 `.pyc`로 컴파일해 소스가 나가지 않게 한다.
개발 전용(dev_*.py)·테스트·docs 조사 문서는 배포하지 않는다. 필지 DB·컨텍스트 DB 사본을 넣는다(≈3.6 GB).

    배포판_만들기.command 더블클릭          (macOS, 저장소 루트)
    배포판_만들기.bat 더블클릭              (Windows, 저장소 루트)
    python3 scripts/dev_deploy.py [대상 폴더]

`.pyc`는 Python 마이너 버전에 묶이므로 Rhino 8의 CPython과 같은 3.9로 실행해야 한다. macOS 기본 /usr/bin/python3가 3.9다.
"""

import base64
import os
import py_compile
import shutil
import sqlite3
import subprocess
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
DEPLOY_DIR_NAME = "UrbanDesignTool"

PLAIN_SCRIPT_NAMES = ("loader.py", "cmd_install.py", "cmd_site.py")   # 입출력 연결뿐이라 감출 로직이 없다
UI_FILE_NAMES = ("site_ui.html",)
UI_DIR_NAMES = ("vendor",)
ROOT_FILE_NAMES = ("UrbanDesignTool.rui", ".env.example")
DOC_FILE_NAMES = ("docs/install.md",)
DATABASE_NAMES = ("seoul_site.db", "seoul_context.db")
# 배포판에서 빼는 로직 모듈 — 개발·실측 전용
EXCLUDED_MODULE_PREFIXES = ("dev_", "cmd_", "probe_")


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
        try:
            connection.execute('DROP TABLE "%s"' % name)
        except sqlite3.OperationalError:
            connection.close()
            os.remove(database_path)
            sys.exit("이 PC의 SQLite로는 rtree 객체를 지울 수 없습니다 — 맥에서 배포판을 만드세요.")
    connection.commit()
    connection.close()
    dropped = len(trigger_names) + len(table_names)
    if dropped:
        print("  rtree 객체 %d개 제거, VACUUM 중... (몇 분)" % dropped, flush=True)
        connection = sqlite3.connect(database_path)
        connection.execute("VACUUM")
        connection.close()
    return dropped


def _run_applescript(script):
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else ""


def _run_powershell(script):
    full_script = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8\n" + script
    encoded = base64.b64encode(full_script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(["powershell", "-NoProfile", "-Sta", "-EncodedCommand", encoded], capture_output=True)
    return result.stdout.decode("utf-8", "replace").strip() if result.returncode == 0 else ""


def _pick_target_dir():
    # type: () -> str
    """배포판을 만들 위치를 OS 폴더 선택창으로 받는다. 취소하면 빈 문자열."""
    if sys.platform == "darwin":
        return _run_applescript('POSIX path of (choose folder with prompt "배포판을 만들 위치를 고르세요")')
    return _run_powershell(
        "Add-Type -AssemblyName System.Windows.Forms\n"
        "$dialog = New-Object System.Windows.Forms.FolderBrowserDialog\n"
        "$dialog.Description = '배포판을 만들 위치를 고르세요'\n"
        "if ($dialog.ShowDialog() -eq 'OK') { $dialog.SelectedPath }")


def _show_info(title, message):
    if sys.platform == "darwin":
        _run_applescript('display dialog "%s" with title "%s" buttons {"확인"} default button "확인"'
                         % (message.replace('"', "'").replace("\n", " "), title))
    else:
        _run_powershell("Add-Type -AssemblyName System.Windows.Forms\n[System.Windows.Forms.MessageBox]::Show('%s', '%s') | Out-Null"
                        % (message.replace("'", "''"), title))


def _build_scripts(deploy_root):
    # type: (str) -> int
    """scripts/를 새로 만든다 — 평문 진입 스크립트 + UI 에셋 + 로직 .pyc(optimize=2, 개발 PC 경로 제거)."""
    deploy_scripts_dir = os.path.join(deploy_root, "scripts")
    if os.path.isdir(deploy_scripts_dir):
        shutil.rmtree(deploy_scripts_dir)
    os.makedirs(deploy_scripts_dir)
    for file_name in PLAIN_SCRIPT_NAMES + UI_FILE_NAMES:
        shutil.copyfile(os.path.join(SCRIPTS_DIR, file_name), os.path.join(deploy_scripts_dir, file_name))
    for dir_name in UI_DIR_NAMES:
        shutil.copytree(os.path.join(SCRIPTS_DIR, dir_name), os.path.join(deploy_scripts_dir, dir_name))
    names = get_deploy_module_names()
    for name in names:
        py_compile.compile(os.path.join(SCRIPTS_DIR, name + ".py"), cfile=os.path.join(deploy_scripts_dir, name + ".pyc"),
                           dfile=name + ".py", doraise=True, optimize=2)
    return len(names)


def _build_data(deploy_root):
    # type: (str) -> None
    """data/에 DB 사본 2개. 이미 있으면 건너뛴다(다시 복사하려면 지우고 실행). 필지 DB 사본은 rtree를 지운다."""
    deploy_data_dir = os.path.join(deploy_root, "data")
    os.makedirs(deploy_data_dir, exist_ok=True)
    for name in DATABASE_NAMES:
        source = os.path.realpath(os.path.join(ROOT_DIR, "data", name))
        target = os.path.join(deploy_data_dir, name)
        if not os.path.exists(source):
            print("[주의] DB가 없어 건너뜀: %s" % source)
            continue
        if os.path.exists(target):
            print("  %s 이미 있음 — 건너뜀" % name)
            continue
        print("  %s 복사 중... (%.1f GB)" % (name, os.path.getsize(source) / 1024.0 ** 3), flush=True)
        shutil.copyfile(source, target)
        strip_spatial_index(target)


def _delete_appledouble(deploy_root):
    for dir_path, _dirs, file_names in os.walk(deploy_root):
        for file_name in file_names:
            if file_name.startswith("._"):
                os.remove(os.path.join(dir_path, file_name))


def main():
    if sys.version_info[:2] != (3, 9):
        sys.exit("Rhino 8의 CPython(3.9)과 같은 Python 3.9로 실행해야 .pyc가 호환됩니다. 현재: %d.%d" % sys.version_info[:2])
    interactive = len(sys.argv) < 2
    target_dir = _pick_target_dir() if interactive else sys.argv[1]
    if not target_dir:
        print("취소했습니다.")
        return
    deploy_root = os.path.join(os.path.abspath(target_dir), DEPLOY_DIR_NAME)
    os.makedirs(deploy_root, exist_ok=True)
    print("배포판 위치: %s" % deploy_root)
    count = _build_scripts(deploy_root)
    print("  로직 모듈 %d개 컴파일" % count)
    for name in ROOT_FILE_NAMES:
        shutil.copyfile(os.path.join(ROOT_DIR, name), os.path.join(deploy_root, name))
    os.makedirs(os.path.join(deploy_root, "docs"), exist_ok=True)
    for name in DOC_FILE_NAMES:
        shutil.copyfile(os.path.join(ROOT_DIR, name), os.path.join(deploy_root, name))
    os.makedirs(os.path.join(deploy_root, "result"), exist_ok=True)
    _build_data(deploy_root)
    _delete_appledouble(deploy_root)
    message = "배포판 완료: %s\n이 폴더를 복사해 docs/install.md 대로 설치합니다." % deploy_root
    print(message)
    if interactive:
        _show_info("UrbanDesignTool 배포판", message)


if __name__ == "__main__":
    main()
