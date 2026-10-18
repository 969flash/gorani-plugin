#! python 3
"""Gorani 설치 — 새 PC에서 한 번만 실행한다.

폴더를 통째로 복사한 뒤 라이노에서 이 파일을 한 번 실행하면 끝이다.

    _-ScriptEditor _Run "<복사한 폴더>/scripts/cmd_install.py"

하는 일
    1. 지금 이 파일 위치로 프로젝트 루트를 알아낸다 (USB든 C:든 상관없음)
    2. 패널 진입 스크립트·필지 DB가 제자리에 있는지 확인한다
    3. 앨리어스 `Gorani`를 등록한다 — 폴더 절대경로는 여기에만 박힌다
    4. 툴바 파일(Gorani.rui)을 라이노에 올린다

이후 사용은 명령창에 `Gorani` 또는 툴바 버튼이다.
코드를 고쳐 배포할 때는 `scripts/` 폴더만 덮어쓰면 되고 다시 설치할 필요가 없다.
폴더를 다른 경로로 옮겼을 때만 이 파일을 다시 실행한다.
"""

import importlib.util
import os
import sys

import Rhino
import Rhino.UI

# cmd_site.py와 같은 방식 — 고유 모듈명으로 로더를 읽어 이름 충돌을 막는다
_spec = importlib.util.spec_from_file_location(
    "gorani_loader",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "loader.py"),
)
loader = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = loader
_spec.loader.exec_module(loader)

# 명령창 앨리어스
ALIAS_NAMES = ("Gorani",)
RUI_FILENAME = "Gorani.rui"
# rui의 tool_bar_group 이름과 같아야 한다 — 툴바를 이름으로 찾을 때 쓴다
TOOLBAR_GROUP_NAME = "Gorani"
ENTRY_SCRIPT_NAME = "cmd_site.py"


def _get_macro(root_dir):
    # type: (str) -> str
    """앨리어스에 넣을 매크로 문자열을 만든다.

    입력:
        root_dir: 프로젝트 루트 절대경로.
    처리:
        `!`로 진행 중인 명령을 취소하고 패널 진입 스크립트를 실행한다.
        경로에 공백이 있을 수 있어 따옴표로 감싼다.
    출력:
        매크로 문자열.
    """
    entry_path = os.path.join(root_dir, "scripts", ENTRY_SCRIPT_NAME)
    return '! _-ScriptEditor _Run "%s"' % entry_path


def _set_alias(name, macro):
    # type: (str, str) -> None
    """앨리어스를 등록하거나 이미 있으면 매크로를 갈아끼운다."""
    aliases = Rhino.ApplicationSettings.CommandAliasList
    if not aliases.Add(name, macro):
        aliases.SetMacro(name, macro)


def _load_toolbar(rui_path, lines):
    # type: (str, list) -> None
    """툴바 파일을 라이노에 올리고 화면에 띄운다.

    입력:
        rui_path: rui 파일 절대경로.
        lines: 설치 결과를 적을 줄 목록.
    처리:
        Open은 이미 열려 있으면 그 파일을 돌려준다. 적재는 ToolbarCount로
        확인한다 — GroupCount는 맥 라이노 8에서 언제나 0을 돌려주므로
        판정에 쓰면 안 된다. 실패해도 설치를 멈추지 않지만 사유는 그대로 남긴다.
    출력:
        없음.
    """
    if not os.path.exists(rui_path):
        lines.append("[건너뜀] 툴바 파일이 없습니다: %s" % rui_path)
        return

    try:
        toolbar_file = Rhino.RhinoApp.ToolbarFiles.Open(rui_path)
    except Exception as error:
        lines.append("[툴바] 자동 등록 실패: %s: %s" % (type(error).__name__, error))
        _append_manual_toolbar_guide(lines)
        return

    if toolbar_file is None:
        lines.append("[툴바] 라이노가 파일을 열지 못했습니다 (반환값 없음)")
        _append_manual_toolbar_guide(lines)
        return

    if toolbar_file.ToolbarCount < 1:
        lines.append("[툴바] 파일은 열렸지만 툴바가 없습니다 — rui 내용을 확인하세요")
        _append_manual_toolbar_guide(lines)
        return

    lines.append("툴바 파일 적재 완료 (툴바 %d개)" % toolbar_file.ToolbarCount)
    if not _show_toolbar_group(toolbar_file, lines):
        _append_manual_toolbar_guide(lines)


def _show_toolbar_group(toolbar_file, lines):
    # type: (object, list) -> bool
    """툴바 그룹을 찾아 화면에 띄운다. 띄웠으면 True."""
    for key in (TOOLBAR_GROUP_NAME, 0):
        try:
            group = toolbar_file.GetGroup(key)
        except Exception:
            continue
        if group is None:
            continue
        try:
            group.Visible = True
        except Exception as error:
            lines.append("[툴바] 켜지 못했습니다: %s: %s" % (type(error).__name__, error))
            return False
        lines.append("  툴바 '%s' 표시: %s" % (group.Name, group.Visible))
        return True
    lines.append("[툴바] 그룹을 코드로 찾지 못했습니다 (맥에서는 흔한 일입니다)")
    return False


def _append_manual_toolbar_guide(lines):
    # type: (list) -> None
    """툴바를 손으로 켜는 방법을 적는다. 앨리어스는 이미 등록됐으므로 도구는 쓸 수 있다."""
    lines.append("  툴바 없이도 명령창에 %s 를 치면 패널은 열립니다" % ALIAS_NAMES[0])
    lines.append("  버튼을 쓰려면 한 번만: 명령창에 ToolBar 입력 (맥 메뉴: 창 > 도구모음...)")
    lines.append("  목록에서 '%s'를 켜면 다음부터는 계속 떠 있습니다" % TOOLBAR_GROUP_NAME)


def _check_files(root_dir, lines):
    # type: (str, list) -> bool
    """패널 진입 스크립트와 DB 2개(필지·컨텍스트)가 제자리에 있는지 본다. 설치를 계속해도 되면 True."""
    entry_path = os.path.join(root_dir, "scripts", ENTRY_SCRIPT_NAME)
    if not os.path.exists(entry_path):
        lines.append("[멈춤] 패널 진입 스크립트를 찾지 못했습니다: %s" % entry_path)
        return False

    constants = loader.load("constants")
    database_path = os.path.join(root_dir, constants.DATABASE_PATH)
    if os.path.exists(database_path):
        size_gb = os.path.getsize(database_path) / (1024.0 ** 3)
        lines.append("필지 DB 확인 (%.1fGB)" % size_gb)
    else:
        lines.append("[주의] 필지 DB가 없습니다 — 아래 자리에 채워야 합니다")
        lines.append("  %s" % database_path)
    context_path = os.path.join(root_dir, constants.CONTEXT_DATABASE_PATH)
    lines.append("컨텍스트 DB 확인 (%.1fGB)" % (os.path.getsize(context_path) / (1024.0 ** 3)) if os.path.exists(context_path)
                 else "[주의] 컨텍스트 DB가 없습니다 — 필지·대상지만 생성됩니다: %s" % context_path)
    return True


def _install():
    # type: () -> None
    """설치 절차를 순서대로 실행하고 결과를 알린다."""
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lines = ["Gorani 설치 위치: %s" % root_dir]

    if not _check_files(root_dir, lines):
        _report(lines)
        return

    macro = _get_macro(root_dir)
    for name in ALIAS_NAMES:
        _set_alias(name, macro)
    lines.append("명령 등록 완료: %s" % ", ".join(ALIAS_NAMES))

    _load_toolbar(os.path.join(root_dir, RUI_FILENAME), lines)
    lines.append("")
    lines.append("이제 명령창에 %s 를 치면 패널이 열립니다." % ALIAS_NAMES[0])
    _report(lines)


def _report(lines):
    # type: (list) -> None
    """설치 결과를 명령창과 대화상자에 함께 보여준다."""
    text = "\n".join(lines)
    print("[Gorani 설치]\n%s" % text)
    Rhino.UI.Dialogs.ShowMessage(text, "Gorani 설치")


_install()
