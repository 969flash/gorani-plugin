"""원격 설정 — 깔린 플러그인이 켤 때 받아 쓰는 '값'(도면 색·범례·분류 구간·코드표·높이 파라미터·링크·번역 사전). 코드는 그대로, 값만 바뀐다.

원본은 코드다 — constants.py의 REMOTE_KEYS 이름들과 i18n.json. `dev_deploy.py notices`가 build()로 config.json을 만들어 HF 매니페스트 옆에 올린다.
플러그인은 켤 때(cmd_site._init) 받아 HOME_DIR/data/config.json에 캐시하고(ETag로 안 바뀌면 안 받는다), 못 받으면 캐시, 그것도 없으면 내장값으로 돈다.
apply()가 constants 모듈 속성과 i18n 사전을 덮는다 — 이름이 REMOTE_KEYS에 있고, 꼴(dict·list·str·수)이 내장값과 같고, dict는 내장 키를 다 가질 때만.
상수의 '꼴'을 바꾸는 판을 낼 때는 COMPAT_MIN을 그 판으로 올린다 — 옛 설치본은 compat_min보다 낮으면 원격 설정을 받지 않고 내장값으로 돈다.
표준 라이브러리만(Rhino·Blender·SketchUp·python3 공통). 2026-10-23 — 도면 색 하나 고치려고 판을 올리던 것을 끝내려고.
"""

import json
import os
import re
import types
import urllib.error
import urllib.parse
import urllib.request

import constants
import data_pack
import i18n

CONFIG_FILE_NAME = "config.json"
CONFIG_VERSION = 1            # config.json 꼴 — 키가 늘기만 하면 올리지 않는다
COMPAT_MIN = "0.3.5"          # 이 판 미만 설치본은 원격 설정을 받지 않는다. REMOTE_KEYS 상수의 꼴(칸 수·중첩)을 바꾸면 그 판으로 올린다
PLACEHOLDER = re.compile(r"\{\d+(?::[^{}]*)?\}")
UNSAFE = '"&<>'               # 패널이 번역문을 HTML에 그대로 넣는다 — 원문에 없는 글자는 받지 않는다(tests/test_i18n.py와 같은 규칙)
# 원격으로 덮을 수 있는 상수 — 그리는 코드가 아니라 '값'. 모듈 import 때 파생되는 것(SHEET_CATALOG → SHEET_IDS, SHEET_LABEL_SKIP_PATTERN → re.compile)은 넣지 않는다
REMOTE_KEYS = (
    # 도면 스타일·틀
    "STYLE_PRESETS", "SHEET_LEGENDS", "SHEET_LINE_MM", "SHEET_FONT_MM", "SHEET_TEMPLATE_MM", "SHEET_LEGEND_ROW_MM", "SHEET_SCALE_BAR_M",
    "SHEET_FADE_TO_PAPER", "SHEET_HATCH", "SHEET_TRANSIT_RADII_M", "SHEET_TRANSIT_COLOR", "SHEET_WALK_MINUTES", "SHEET_WALK_COLORS",
    "SHEET_WALK_SPEED_M_PER_MIN", "BM_LAYERS",
    # 분류 구간·코드표
    "SHEET_LOT_SIZE_BREAKS", "SHEET_DENSITY_BREAKS", "SHEET_BLOCK_MIN_AREA", "SHEET_FLOOR_BANDS_FIXED", "SHEET_ROAD_WIDTH_BREAKS", "AGE_BANDS_YEARS",
    "SHEET_PRICE_QUANTILES", "SHEET_LAND_USE_KEYS", "SHEET_LAND_CATEGORY_KEYS", "SHEET_ZONE_KEYS", "SHEET_FACILITY_KEYS", "SHEET_USE_KEYS",
    "SHEET_PUBLIC_USE", "SHEET_PUBLIC_NGII", "SHEET_PUBLIC_FACILITY", "SHEET_HEIGHT_SRC_LABELS", "HEIGHT_SRC_KIND_LABELS", "PLATEAU_USE", "OSM_BUILDING_USE",
    # 높이·범위 파라미터, OSM 질의·도로폭
    "FLOOR_HEIGHT_MODEL", "FLOOR_HEIGHT_DEFAULT", "FLOOR_HEIGHT_CLAMP", "DEFAULT_BUILDING_HEIGHT_M", "CONTEXT_RADIUS",
    "OSM_ROAD_WIDTHS", "OSM_ROAD_NO_SURFACE_TAGS", "OSM_OVERPASS_QUERY", "OSM_OVERPASS_BUILDING_QUERY", "OSM_OVERPASS_BUILDINGS",
    # 링크
    "PANEL_LINKS",
)


def get_config_url():
    # type: () -> str
    """한국 매니페스트 옆 config.json."""
    return urllib.parse.urljoin(constants.DATA_MANIFEST_URL, CONFIG_FILE_NAME)


def _version_tuple(text):
    # type: (str) -> tuple
    try:
        return tuple(int(part) for part in str(text).split("."))
    except ValueError:
        return ()


# ── 만들기(개발 쪽) ────────────────────────────────────────

def build(source=None, texts=None, version=None):
    # type: (object, dict, str) -> dict
    """constants(REMOTE_KEYS) + i18n 사전 → config.json 내용. dev_deploy.py notices가 올린다."""
    source = source or constants
    return {"config_version": CONFIG_VERSION, "compat_min": COMPAT_MIN, "built_for": version or constants.PANEL_VERSION,
            "constants": {name: getattr(source, name) for name in REMOTE_KEYS if hasattr(source, name)},
            "i18n": texts if texts is not None else i18n.get_texts()}


# ── 덮기 ──────────────────────────────────────────────────

def _mirror(builtin, value):
    # type: (object, object) -> object
    """JSON으로 온 value를 내장값의 꼴에 맞춘다 — 내장이 tuple이면 tuple로, dict 키가 int면 int로(JSON은 문자열 키뿐).
    꼴이 다르면(dict↔list, 수↔문자열, 내장 dict 키가 빠짐) ValueError."""
    if isinstance(builtin, bool) or isinstance(value, bool):
        if isinstance(builtin, bool) and isinstance(value, bool):
            return value
        raise ValueError("bool")
    if value is None and not isinstance(builtin, (dict, list, tuple)):   # 스칼라 칸의 None(BM_LAYERS 투명도 칸 등) — JSON null
        return None
    if isinstance(builtin, (int, float)):
        if isinstance(value, (int, float)):
            return value
        raise ValueError("number")
    if isinstance(builtin, str):
        if isinstance(value, str):
            return value
        raise ValueError("str")
    if builtin is None:
        if value is None or isinstance(value, (int, float, str)):
            return value
        raise ValueError("scalar")
    if isinstance(builtin, dict):
        if not isinstance(value, dict):
            raise ValueError("dict")
        key_type = type(next(iter(builtin))) if builtin else str
        sample = next(iter(builtin.values())) if builtin else None
        result = {}
        for key, item in value.items():
            key = key_type(key) if key_type is not str else key
            template = builtin.get(key, sample)
            result[key] = _mirror(template, item) if builtin else item
        missing = [key for key in builtin if key not in result]
        if missing:
            raise ValueError("내장 키 빠짐 %s" % missing[:3])
        return result
    if isinstance(builtin, (list, tuple)):
        if not isinstance(value, (list, tuple)):
            raise ValueError("list")
        items = []
        for index, item in enumerate(value):
            template = builtin[index] if index < len(builtin) else (builtin[-1] if builtin else None)
            items.append(_mirror(template, item) if builtin else item)
        return tuple(items) if isinstance(builtin, tuple) else items
    raise ValueError("모르는 꼴 %s" % type(builtin).__name__)


def _is_safe_text(key, text):
    # type: (str, str) -> bool
    """번역문 규칙(tests/test_i18n.py와 같다): 자리표시 {0}…이 원문과 같고, 원문에 없는 \" & < >가 없다."""
    return (set(PLACEHOLDER.findall(text)) == set(PLACEHOLDER.findall(key))
            and all(ch not in text or ch in key for ch in UNSAFE))


def apply(config, target=None, texts=None, version=None):
    # type: (dict, object, dict, str) -> dict
    """config.json 내용을 constants 모듈(target)과 i18n 사전(texts)에 덮는다. 틀린 항목은 그 항목만 건너뛴다.
    출력: {"applied": [이름], "rejected": {이름: 이유}, "i18n": 덮은 문구 수, "skipped": 이유 또는 ""}."""
    target = target or constants
    report = {"applied": [], "rejected": {}, "i18n": 0, "skipped": ""}
    if not isinstance(config, dict):
        report["skipped"] = "없음"
        return report
    compat = _version_tuple(config.get("compat_min") or "0")
    if _version_tuple(version or constants.PANEL_VERSION) < compat:
        report["skipped"] = "compat_min %s" % config.get("compat_min")   # 상수 꼴이 바뀐 뒤의 설정 — 이 판은 내장값으로
        return report
    values, entries = config.get("constants"), config.get("i18n")
    for name, value in (values if isinstance(values, dict) else {}).items():
        if name not in REMOTE_KEYS or not hasattr(target, name):
            continue
        try:
            setattr(target, name, _mirror(getattr(target, name), value))
            report["applied"].append(name)
        except ValueError as error:
            report["rejected"][name] = str(error)
    texts = i18n.get_texts() if texts is None else texts
    for key, entry in (entries if isinstance(entries, dict) else {}).items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            continue
        clean = {lang: text for lang, text in entry.items()
                 if lang in constants.LANGS and lang != "ko" and isinstance(text, str) and text and _is_safe_text(key, text)}
        if clean:
            texts.setdefault(key, {}).update(clean)
            report["i18n"] += 1
    return report


# ── 받기·캐시 ─────────────────────────────────────────────

def _cache_paths(data_dir=None):
    # type: (str) -> tuple
    data_dir = data_dir or data_pack.get_data_dir()
    return os.path.join(data_dir, CONFIG_FILE_NAME), os.path.join(data_dir, CONFIG_FILE_NAME + ".etag")


def load_cached(data_dir=None):
    # type: (str) -> dict
    """캐시된 config.json(없거나 깨졌으면 None)."""
    path, _etag = _cache_paths(data_dir)
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def fetch(timeout=None, url=None, data_dir=None):
    # type: (float, str, str) -> dict
    """config.json을 받아 캐시한다(ETag — 안 바뀌었으면 304, 캐시를 쓴다). 실패하면 캐시(없으면 None). 예외를 밖으로 내지 않는다."""
    path, etag_path = _cache_paths(data_dir)
    headers = {"User-Agent": constants.OSM_USER_AGENT}
    try:
        with open(etag_path, encoding="utf-8") as f:
            etag = f.read().strip()
        if etag and os.path.exists(path):
            headers["If-None-Match"] = etag
    except OSError:
        pass
    try:
        with urllib.request.urlopen(urllib.request.Request(url or get_config_url(), headers=headers), timeout=timeout or constants.DATA_TIMEOUT_SECONDS) as response:
            body = response.read()
            etag = response.headers.get("ETag") or ""
    except urllib.error.HTTPError as error:
        if error.code == 304:
            return load_cached(data_dir)
        return load_cached(data_dir)
    except Exception:
        return load_cached(data_dir)
    try:
        config = json.loads(body.decode("utf-8"))
    except ValueError:
        return load_cached(data_dir)
    if isinstance(config, dict):
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(config, f, ensure_ascii=False)
            os.replace(path + ".tmp", path)
            with open(etag_path, "w", encoding="utf-8") as f:
                f.write(etag)
        except OSError:
            pass
    return config if isinstance(config, dict) else load_cached(data_dir)


def refresh(timeout=None):
    # type: (float) -> dict
    """받아서(또는 캐시) 덮는다 — 패널 init이 부른다. apply 보고서를 돌려준다."""
    return apply(fetch(timeout))


def get_snapshot(source=None):
    # type: (object) -> object
    """테스트·자가 점검용 — REMOTE_KEYS 값만 복사한 네임스페이스(원본 constants를 건드리지 않고 apply 해 본다)."""
    source = source or constants
    return types.SimpleNamespace(**{name: getattr(source, name) for name in REMOTE_KEYS if hasattr(source, name)})
