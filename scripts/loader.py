"""진입 스크립트(cmd_*.py)가 로직 모듈을 불러올 때 쓰는 공통 로더.

Rhino 8은 여러 스크립트·플러그인이 파이썬 인터프리터 하나를 공유한다. 그래서
`constants`처럼 흔한 이름이 다른 플러그인 모듈과 겹칠 수 있고, 편집한 파일이
다음 계산에 반영되지 않을 수 있다. 두 문제를 이 파일 한 곳에서 처리한다.

진입 스크립트는 이 파일만 직접 읽고, 나머지 로직 모듈은 `load()`로 가져온다.
Blender 확장에서는 scripts/가 패키지의 하위 패키지다(확장 정책: 최상위 모듈·sys.path 변경 금지) — 그때는 패키지 이름을 붙여
불러오고 sys.path·외부 모듈은 건드리지 않는다. 로직 모듈의 `import constants`는 빌드가 상대 import로 바꿔 둔다(dev_deploy.py blender).
"""

import importlib
import os
import sys

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
_PREFIX = __package__ + "." if __package__ else ""   # Blender 확장 = 'bl_ext.<저장소>.urbansite.scripts.'


def load(module_name):
    # type: (str) -> object
    """scripts/ 안의 로직 모듈을 불러온다.

    입력:
        module_name: 확장자를 뺀 모듈 이름. 예: ``"lot_db"``.
    처리:
        scripts/를 sys.path 맨 앞에 두고, 같은 이름의 외부 모듈이 이미 올라와
        있으면 걷어낸다. 이전 계산에서 읽어둔 프로젝트 모듈만 다시 읽어
        편집 내용을 이번 계산에 반영한다. 이번에 처음 읽는 모듈은 이미 최신이다.
        reload 도중 다른 모듈이 sys.modules를 건드려 방금 읽은 것을 걷어낼 수
        있어(스테일 모듈을 이름으로 퍼지하는 러너) 사라졌으면 다시 읽는다.
    출력:
        불러온 모듈. 파일이 없으면 ImportError를 발생시킨다.
    """
    if not _PREFIX and SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    importlib.invalidate_caches()
    if not _PREFIX:
        _drop_foreign_modules()
    loaded_before = _get_project_modules()
    importlib.import_module(_PREFIX + module_name)
    for module in loaded_before if sys.platform != "emscripten" else ():   # 웹판(Pyodide) 파일은 실행 중에 바뀌지 않는다
        importlib.reload(module)
    module = sys.modules.get(_PREFIX + module_name)
    if module is None:
        module = importlib.import_module(_PREFIX + module_name)
    return module


def source_stamp():
    # type: () -> tuple
    """현재 올라온 프로젝트 모듈 파일들의 수정 시각을 모아 반환한다.

    입력:
        없음.
    처리:
        프로젝트 모듈의 경로와 mtime을 파일 경로 순으로 정렬한다.
    처리 결과는 계산 캐시의 서명에 넣어 코드를 고치면 캐시가 무효가 되게 한다.
    출력:
        ``((경로, mtime), ...)`` 튜플. 읽을 수 없는 파일은 건너뛴다.
    """
    stamps = []
    for module in _get_project_modules():
        path = getattr(module, "__file__", None)
        try:
            stamps.append((path, os.path.getmtime(path)))
        except OSError:
            continue
    return tuple(sorted(stamps))


def _is_project_module(module):
    # type: (object) -> bool
    """모듈이 scripts/ 안의 파일에서 온 것인지 확인한다.

    입력:
        module: 검사할 모듈 객체.
    처리:
        모듈 파일의 상위 폴더가 scripts/와 같은지 본다.
    출력:
        프로젝트 모듈이면 True, 아니면 False.
    """
    module_path = getattr(module, "__file__", None)
    if not module_path:
        return False
    return os.path.dirname(os.path.abspath(module_path)) == SCRIPTS_DIR


def _get_project_modules():
    # type: () -> list
    """sys.modules에 올라온 프로젝트 모듈을 import된 순서대로 모은다.

    입력:
        없음.
    처리:
        scripts/의 모듈 이름과 파일 위치가 모두 맞는 것만 고른다. 이름까지 보는
        이유는 진입 스크립트가 `__main__`으로 올라와 섞이는 것을 막기 위해서다.
        sys.modules는 삽입 순서를 유지하므로 결과 순서가 대체로
        의존 순서(constants가 먼저)와 같다.
    출력:
        모듈 목록.
    """
    names = {_PREFIX + name for name in _get_project_module_names()}
    return [
        module
        for name, module in list(sys.modules.items())
        if name in names and _is_project_module(module)
    ]


def _drop_foreign_modules():
    # type: () -> None
    """scripts/의 모듈 이름을 가로챈 외부 모듈을 sys.modules에서 걷어낸다.

    입력:
        없음.
    처리:
        scripts/*.py 이름만 대상으로 하고, scripts/ 밖에서 온 것만 지운다.
        `constants`처럼 전이로 import되는 이름까지 함께 봐야 하이재킹을 막는다.
    출력:
        없음.
    """
    for name in _get_project_module_names():
        module = sys.modules.get(name)
        if module is not None and not _is_project_module(module):
            del sys.modules[name]


def _get_project_module_names():
    # type: () -> list
    """scripts/ 안의 py·pyc 파일에서 모듈 이름을 모은다.

    입력:
        없음.
    처리:
        진입 스크립트(`cmd_*.py`)와 이 로더는 import 대상이 아니므로
        제외한다. 배포판은 로직 모듈이 `.pyc`뿐이라 확장자 둘 다 본다.
    출력:
        확장자를 뺀 모듈 이름 목록.
    """
    loader_name = os.path.basename(__file__)[:-3]
    names = []
    for file_name in os.listdir(SCRIPTS_DIR):
        if file_name.startswith("cmd_") or file_name.startswith("__init__"):
            continue
        if file_name.endswith(".py"):
            name = file_name[:-3]
        elif file_name.endswith(".pyc"):
            name = file_name[:-4]
        else:
            continue
        if name != loader_name and name not in names:
            names.append(name)
    return names


def reload_project_modules(exclude=()):
    # type: (tuple) -> None
    """이미 올라온 프로젝트 모듈을 모두 다시 읽어 고친 파일을 이번 실행에 반영한다.

    입력:
        exclude: 건너뛸 모듈 이름들 — 돌고 있는 서버 모듈처럼 본문을 다시 실행하면
            상태(_job·서버 핸들)가 초기화돼 깨지는 것.
    처리:
        reload는 같은 모듈 객체를 그대로 쓰므로 모듈을 참조하던 쪽은 그대로 동작한다.
        오래 떠 있는 프로세스(QA 서버)가 시작 시점 코드로 계속 돌던 것을 막는다 —
        2026-09-22 QA 페이지 실행이 서버가 뜰 때 읽은 옛 코드로 돌아 7층 상한·코어 겹침이
        그대로 나왔다.
    출력:
        없음.
    """
    if not _PREFIX and SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    importlib.invalidate_caches()
    for module in _get_project_modules():
        if module.__name__[len(_PREFIX):] in exclude:
            continue
        importlib.reload(module)
