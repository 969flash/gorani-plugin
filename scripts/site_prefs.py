"""패널 설정과 최근 대상지를 사용자 홈(~/.gorani/)에 읽고 쓴다.

WebView는 임시 파일 file:// 출처라 localStorage를 믿을 수 없어 Python이 저장한다(docs/panel_ui.md 설정 저장 위치).
표준 라이브러리만 쓴다. 파일이 깨져 있으면 기본값으로 돌아가고 덮어쓴다.
"""

import json
import os
import re
import tempfile
import uuid

import constants
from i18n import tr

PREFS_DIR = os.path.join(os.path.expanduser("~"), ".gorani")
PREFS_PATH = os.path.join(PREFS_DIR, "prefs.json")
CLIENT_ID_PATH = os.path.join(PREFS_DIR, "client_id")   # 설치 ID — 사용 통계(Rhino)와 국내 데이터 팩 서버 하루 한도(모든 판)
SOURCE_NEWS_PATH = os.path.join(PREFS_DIR, "source_news.json")
RECENT_MAX = 5
PREFS_VERSION = 2   # 2 = 범위 기본값을 사각형 한 변 500 m로 바꿨다(2026-10-19) — 그 전에 저장된 radius·shape는 한 번 버린다
_RESET_BEFORE_V2 = ("radius", "shape")



def get_client_id(path=CLIENT_ID_PATH):
    # type: (str) -> str
    """설치마다 한 번 만든 무작위 UUID. 파일이 없거나 비면 새로 만들어 쓴다."""
    try:
        with open(path, encoding="utf-8") as f:
            value = f.read().strip()
        if value:
            return value
    except OSError:
        pass
    value = str(uuid.uuid4())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(value)
    return value

def _read_json(path):
    # type: (str) -> dict
    try:
        with open(path, encoding="utf-8") as f:
            value = json.load(f)
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path, value):
    # type: (str, dict) -> None
    """임시 파일에 쓰고 os.replace — 읽는 쪽이 깨진 JSON을 보지 않게 한다."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=os.path.dirname(path))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def get_options(path=PREFS_PATH):
    # type: (str) -> dict
    """저장된 옵션을 기본값 위에 덮어 돌려준다. 모르는 키는 버린다."""
    options = dict(constants.PANEL_DEFAULT_OPTIONS)
    data = _read_json(path)
    saved = data.get("options") or {}
    old = int(data.get("version") or 1) < PREFS_VERSION
    for key in options:
        if key in saved and not (old and key in _RESET_BEFORE_V2):
            options[key] = saved[key]
    if saved and "lang" not in saved:   # 언어 고르기 전(0.3.0 전) 설치본 — 한국어 패널을 쓰던 사람이라 영어로 바꾸지 않는다
        options["lang"] = "ko"
    return options


def save_options(options, path=PREFS_PATH):
    # type: (dict, str) -> dict
    """옵션만 갱신한다(recent는 그대로). 돌려주는 값은 저장된 전체 옵션."""
    data = _read_json(path)
    merged = get_options(path)
    for key in merged:
        if key in (options or {}):
            merged[key] = options[key]
    data["options"] = merged
    data["version"] = PREFS_VERSION
    _write_json(path, data)
    return merged


def get_recent(path=PREFS_PATH):
    # type: (str) -> list
    recent = _read_json(path).get("recent") or []
    return [item for item in recent if isinstance(item, dict) and item.get("pnus")][:RECENT_MAX]


def add_recent(pnus, label, total_area, date, path=PREFS_PATH):
    # type: (list, str, float, str, str) -> list
    """최근 대상지 맨 앞에 넣는다. 같은 PNU 묶음은 하나만, 최대 RECENT_MAX."""
    key = tuple(sorted(pnus))
    data = _read_json(path)
    recent = [item for item in get_recent(path) if tuple(sorted(item.get("pnus") or [])) != key]
    recent.insert(0, {"pnus": list(pnus), "label": label, "total_area": round(float(total_area), 1), "date": date})
    data["recent"] = recent[:RECENT_MAX]
    _write_json(path, data)
    return data["recent"]


def remove_recent(pnus, path=PREFS_PATH):
    # type: (list, str) -> list
    """최근 대상지에서 같은 PNU 묶음을 지운다(패널 x). 돌려주는 값은 남은 목록."""
    key = tuple(sorted(pnus or []))
    data = _read_json(path)
    data["recent"] = [item for item in get_recent(path) if tuple(sorted(item.get("pnus") or [])) != key]
    _write_json(path, data)
    return data["recent"]


# [blender-cut] 사용 통계 동의 — Blender 확장 패키지에는 통계가 없다
def get_stats_consent(path=PREFS_PATH):
    # type: (str) -> object
    """사용 통계 동의 — True(보냄)·False(안 보냄)·None(아직 안 물음). 동의를 묻는 호스트(constants.HOST_LABELS ask_stats)만 쓴다."""
    value = _read_json(path).get("stats_consent")
    return value if isinstance(value, bool) else None


def save_stats_consent(on, path=PREFS_PATH):
    # type: (bool, str) -> bool
    data = _read_json(path)
    data["stats_consent"] = bool(on)
    _write_json(path, data)
    return data["stats_consent"]
# [/blender-cut]


def get_source_news(path=SOURCE_NEWS_PATH):
    # type: (str) -> dict
    """dev_check_sources.py가 남긴 '새 판' 캐시. 없으면 빈 dict."""
    return _read_json(path)


def get_styles_dir():
    # type: () -> str
    """도면 스타일 파일 폴더 — HOME_DIR/styles. 사용자가 열어 다른 사람과 파일로 주고받는다."""
    return os.path.join(constants.HOME_DIR, constants.STYLES_DIRNAME)


def list_styles(styles_dir=None):
    # type: (str) -> list
    """styles/*.json → [{name, style}] 이름순. 깨진 파일·dict가 아닌 파일은 건너뛴다(값 검사는 sheet_svg.get_style이 한다)."""
    styles_dir = styles_dir or get_styles_dir()
    if not os.path.isdir(styles_dir):
        return []
    styles = []
    for file_name in sorted(os.listdir(styles_dir)):
        if not file_name.endswith(".json"):
            continue
        style = _read_json(os.path.join(styles_dir, file_name))
        if style:
            styles.append({"name": file_name[:-5], "style": style})
    return styles


def save_style(name, style, styles_dir=None):
    # type: (str, dict, str) -> list
    """스타일 하나를 styles/<이름>.json으로 쓴다(같은 이름은 덮어쓴다). 이름의 경로 문자는 지운다. 반환 list_styles()."""
    clean = re.sub(r'[\\/:*?"<>|]', "", str(name or "")).strip()[:40].rstrip(". ")
    if not clean or clean.startswith("."):
        raise ValueError(tr("스타일 이름을 적어 주세요"))
    if re.fullmatch(r"(CON|PRN|AUX|NUL|COM\d|LPT\d)", clean.split(".")[0].upper()):   # 윈도 예약 이름 — CON은 조용히 사라지고 AUX는 오류(2026-10-23 감사)
        clean = "_" + clean
    styles_dir = styles_dir or get_styles_dir()
    _write_json(os.path.join(styles_dir, clean + ".json"), dict(style or {}, name=clean))
    return list_styles(styles_dir)
