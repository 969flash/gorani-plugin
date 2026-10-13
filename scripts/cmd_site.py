#! python 3
"""대지검토 패널 진입 스크립트 + 컨트롤러 — Rhino에서 직접 실행한다.

    ! _-ScriptEditor _Run "<저장소 경로>/scripts/cmd_site.py"

panel_host.PanelHost(Eto WebView)와 로직 모듈을 잇는다. JS 명령(dict)을 받아 로직 함수를 부르고 host.push()로
상태를 보낸다. 메시지 계약은 docs/panel_ui.md('아키텍처 정합' 절 우선). 생성은 context_builder.run을 UI 스레드에서
동기 호출하고, 진행률은 콜백 안에서 push + Rhino.RhinoApp.Wait()로 펌핑한다(서브프로세스 없음).

명령 → 로직 (21개)
    init            → get_init_state (DB 존재·원천 상태·타일·지도·prefs·recent·시트 카탈로그). preflight 메모이즈 비움
    search          → get_search_result (pnu_loader.resolve_addresses + review_map.get_parcel_centers)
    map_lots        → review_map.get_parcels_in_bbox (seq 에코)
    select_lots     → get_lot_state (review_map.get_parcels_geojson + 대상 합집합 role target)
    set_area        → get_area_state (구역 링 → context_builder.resolve_target: 안전장치·안의 필지)
    set_point       → get_point_state (위치 → 이름)
    pick_curve      → Rhino 선택(또는 고르기) 커브 → context_geometry.get_curve_ring → curve_shape
    snap_area       → 구역 안 필지 합집합(context_geometry.get_union_ring) → area_state
    preflight       → context_builder.preflight (메모이즈, seq 에코)
    generate        → context_builder.run (콜백 = push + Wait + 취소 플래그) → done / progress{failed|cancelled}
    cancel          → 플래그만
    import_context  → context_baker.import_3dm (busy 푸시 사이)
    export_basemap  → context_builder.export_basemap (DB에서 basemap_ai로 다시 씀 · busy·exported)
    zoom_view       → context_baker.zoom_to_site
    open_path       → 폴더·파일·.env 템플릿을 OS로 연다
    save_prefs      → site_prefs.save_options
    style_preview   → context_builder.preview_sheet (스타일 바꾼 한 장 SVG 문자열 — 파일 안 씀, seq 에코)
    apply_style     → context_builder.apply_style (시트 전부 + 쓴 .ai 다시 쓰기, busy·style_applied)
    save_style      → site_prefs.save_style (HOME_DIR/styles/<이름>.json → styles)
    sheet_ai        → sheet_svg.get_sheet_ai (도면 SVG → 레이어 .ai, 누를 때 · all이면 결과 폴더 전부, busy·sheet_ai) → 하나면 OS로 연다
    download_data   → data_pack (매니페스트 → 바뀐 팩만 받기, 콜백 = data_progress 푸시 + Wait + 취소 플래그) → init_state

조립 함수(get_*·resolve_open_path)는 Rhino 없이 돈다 — tests/test_site_ui_contract.py가 fixture DB로 키 집합을 확인한다.
Rhino 모듈이 없으면(python3) 패널을 띄우지 않는다.
"""

import datetime
import importlib.util
import json
import os
import subprocess
import sys
import traceback

try:
    import Rhino
    import scriptcontext
    import System
    import Eto.Forms as forms
except ImportError:   # python3 테스트 — 조립 함수만 쓴다
    Rhino = scriptcontext = System = forms = None

# cmd_install.py와 같은 방식 — 고유 모듈명으로 로더를 읽어 Rhino 공유 인터프리터의 이름 충돌을 막는다
_spec = importlib.util.spec_from_file_location(
    "urban_design_tool_loader",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "loader.py"),
)
loader = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = loader
_spec.loader.exec_module(loader)

ROOT_DIR = loader.ROOT_DIR
PANEL_STICKY_KEY = "urban_design_tool_site_panel"
ENV_TEMPLATE = "VWORLD_API_KEY=\nDATA_GO_KR_KEY=\n"
# 콜백이 오지 않는 phase의 행 오른쪽 글(panel_ui.md 진행률 규약)
SKIPPED_DETAILS = {"refresh": "건너뜀 — v1 미구현", "import": "건너뜀 — 베이크로 대체"}
SKIPPED_OPTION_DETAIL = "건너뜀 — 옵션"
SEARCH_MAX_MATCHES = 8
_EMPTY_FC = {"type": "FeatureCollection", "features": []}


# ── 조립 함수 (Rhino 없음) ─────────────────────────────────

def _jibun(address):
    # type: (str) -> str
    """주소 '서울특별시 성동구 성수동2가 333-139' → 지번 '333-139'."""
    parts = (address or "").split()
    return parts[-1] if parts else ""


def get_init_state(site_db=None, context_db=None, today=None):
    # type: (str, str, datetime.date) -> dict
    """init_state 페이로드(panel_ui.md).

    입력: DB 경로 override 2개(테스트가 fixture를 꽂는다. None = constants 경로), today(테스트용).
    처리: 필지 DB 존재 → blocked, context_builder.get_sources/get_source_warnings, review_map 타일·지도, site_prefs 옵션·recent,
          SHEET_CATALOG. 네트워크 접근 없음. generator는 항상 ok(서브프로세스 없음 — UI 호환 키).
    출력: {"type": "init_state", version, blocked, paths, generator, sources, warnings, tile, map, options, modes, recent, sheet_catalog,
          style_presets, style_defaults, style_ramps, styles}.
    """
    constants = loader.load("constants")
    context_builder = loader.load("context_builder")
    review_map = loader.load("review_map")
    site_prefs = loader.load("site_prefs")
    has_lot_db = os.path.exists(site_db) if site_db else bool(loader.load("data_pack").get_local_paths("site"))
    sources = context_builder.get_sources(site_db, context_db, today)
    return {
        "type": "init_state",
        "version": constants.PANEL_VERSION,
        "blocked": not has_lot_db,
        "paths": {"root": constants.HOME_DIR, "lot_db": constants.DATABASE_PATH, "context_db": constants.CONTEXT_DATABASE_PATH,
                  "env": ".env", "install_doc": constants.INSTALL_DOC},
        "generator": {"ok": True, "python": "Rhino CPython", "text": "Rhino 내장"},
        "can_download": bool(constants.DATA_MANIFEST_URL),
        "sources": sources,
        "warnings": context_builder.get_source_warnings(sources),
        "tile": review_map.get_tile_config(),
        "map": review_map.get_map_init(),
        "options": site_prefs.get_options(),
        "modes": {"defaults": constants.MODE_DEFAULTS, "shapes": {k: list(v) for k, v in constants.SHAPES_BY_MODE.items()}},
        "recent": site_prefs.get_recent(),
        "sheet_catalog": [{"id": sheet_id, "key": key, "name": name, "subtitle": en, "needs": needs} for sheet_id, key, name, en, needs in constants.SHEET_CATALOG],
        "style_presets": {key: dict(preset) for key, preset in constants.STYLE_PRESETS.items()},
        "style_defaults": dict(constants.STYLE_DEFAULTS),
        "style_ramps": {key: list(ramp) for key, ramp in constants.STYLE_RAMPS.items()},
        "styles": site_prefs.list_styles(),
    }


def get_search_result(query, site_db=None):
    # type: (str, str) -> dict
    """search_result 페이로드. 주소·지번·PNU 한 줄 → 후보 0~8건(+중심 좌표). VWorld 키가 있으면 보조 검색을 켠다."""
    constants = loader.load("constants")
    pnu_loader = loader.load("pnu_loader")
    review_map = loader.load("review_map")
    use_vworld = bool(pnu_loader.get_local_env_value(constants.VWORLD_API_KEY_ENV))
    try:
        matches = pnu_loader.resolve_addresses([query], use_vworld, site_db)[0].matches[:SEARCH_MAX_MATCHES]
    except FileNotFoundError:   # 국내 필지 DB 없음(해외만 쓰는 사용자) — 지명 검색으로
        matches = []
    if not matches:
        places = loader.load("osm_context").search_places(query, SEARCH_MAX_MATCHES)
        return {"type": "search_result", "query": query, "seq": None,
                "matches": [{"pnu": "", "address": p["name"], "jibun": "", "land_category": "", "area": None, "center": p["center"]} for p in places],
                "message": "지명 후보 %d건 (OpenStreetMap)" % len(places) if places else "찾지 못했습니다 — 동 이름까지 적어 보세요"}
    centers = review_map.get_parcel_centers([m.pnu for m in matches], site_db) if matches else {}
    return {
        "type": "search_result", "query": query, "seq": None,
        "matches": [{"pnu": m.pnu, "address": m.address, "jibun": m.lot_number or _jibun(m.address), "land_category": m.land_category,
                     "area": m.geometry_area, "center": centers.get(m.pnu)} for m in matches],
        "message": "후보 %d건" % len(matches) if matches else "찾지 못했습니다 — 동 이름까지 적어 보세요",
    }


def get_map_lots(bbox, seq, site_db=None):
    # type: (list, int, str) -> dict
    """map_lots 페이로드 — review_map.get_parcels_in_bbox 그대로 + seq 에코."""
    review_map = loader.load("review_map")
    result = review_map.get_parcels_in_bbox(bbox, database_path=site_db)
    return {"type": "map_lots", "seq": seq, "geojson": result["geojson"], "truncated": result["truncated"]}


def get_lot_state(pnus, site_db=None):
    # type: (list, str) -> dict
    """lot_state 페이로드.

    입력: 현재 대상 PNU 전체(빈 목록 = 모두 지움).
    처리: lot_db.load → 필지별 Feature(role lot) + 대상 합집합 1개(role target — 각 필지의 가장 넓은 외곽 링 MultiPolygon),
          lot_name·중심(100 m 내림 전)·multipart 경고는 context_builder의 같은 규칙을 쓴다.
    출력: {"type": "lot_state", lots[{pnu, address, jibun, land_category, area, warn}], total_area, lot_name, center, target_geojson, warnings}.
    """
    pnus = [str(p) for p in (pnus or []) if str(p).strip()]
    if not pnus:
        return {"type": "lot_state", "lots": [], "total_area": 0.0, "lot_name": "", "center": None, "target_geojson": _EMPTY_FC, "warnings": []}
    context_builder = loader.load("context_builder")
    lot_db = loader.load("lot_db")
    non_rhino_utils = loader.load("non_rhino_utils")
    review_map = loader.load("review_map")
    non_rhino_utils.set_projection()   # 필지는 국내뿐 — 해외 대상지 원점을 되돌린다
    lots = lot_db.load(pnus, site_db).lots
    rings, warnings = context_builder.get_target_rings(lots)
    geojson = review_map.get_parcels_geojson(pnus, "lot", site_db)
    rows = []
    for lot, feature in zip(lots, geojson["features"]):
        parts = non_rhino_utils.get_polygon_parts_from_geojson(lot.geometry)
        warn = "multipart" if len(parts) > 1 else ("hole" if any(len(part) > 1 for part in parts) else None)
        feature["properties"]["jibun"] = lot.lot_number or _jibun(lot.address)
        rows.append({"pnu": lot.pnu, "address": lot.address, "jibun": feature["properties"]["jibun"],
                     "land_category": lot.land_category, "area": lot.area, "warn": warn})
    target_coords = [[review_map.get_wgs84_ring(ring + [ring[0]])] for ring in rings]   # 닫힘 중복점을 붙여 GeoJSON 링으로
    geojson["features"].append({"type": "Feature", "properties": {"role": "target"},
                                "geometry": {"type": "MultiPolygon", "coordinates": target_coords}})
    center = review_map.get_wgs84_ring([context_builder.get_lots_center(lots)])[0]
    return {
        "type": "lot_state", "lots": rows, "total_area": round(sum(row["area"] for row in rows), 1),
        "lot_name": context_builder.get_lot_name(lots), "center": center, "target_geojson": geojson, "warnings": warnings,
    }


def _empty_area_state(text=""):
    # type: (str) -> dict
    return {"type": "area_state", "ok": not text, "text": text, "ring_tm": [], "ring_lnglat": [], "center": None, "center_tm": None,
            "offsets": [], "area": 0.0, "lots": 0, "lots_area": 0.0, "lot_name": "", "target_geojson": _EMPTY_FC, "warnings": [], "snapped": False}


def get_area_state(msg, site_db=None):
    # type: (dict, str) -> dict
    """area_state 페이로드 — 구역 링 하나를 정리·검사하고 안의 필지를 센다.

    입력: msg 중 하나 — ring_tm [[x, y]] EPSG:5186 / ring_lnglat [[lng, lat]](지도에 그린 것) / center [lng, lat] + offsets [[dx, dy]] m
          (Rhino 커브를 지도에서 옮겨 놓은 것 — 모양은 m로 그대로, 위치만 지도에서). 아무것도 없으면 빈 상태(지움).
    처리: context_builder.resolve_target(area) — 안전장치(get_ring_problem)·안의 필지(50 % 규칙)·이름.
    출력: {"type": "area_state", ok, text, ring_tm, ring_lnglat(닫힘), center, center_tm, offsets, area, lots, lots_area, lot_name,
          target_geojson(role area 1 + role target 필지), warnings, snapped}. 링 문제는 ok=false + text(사용자용 한 줄).
    """
    context_builder = loader.load("context_builder")
    non_rhino_utils = loader.load("non_rhino_utils")
    review_map = loader.load("review_map")
    if msg.get("ring_tm"):
        points = [(float(x), float(y)) for x, y in msg["ring_tm"]]
    elif msg.get("ring_lnglat"):
        lnglats = [(float(lng), float(lat)) for lng, lat in msg["ring_lnglat"]]
        non_rhino_utils.set_projection(sum(p[0] for p in lnglats) / len(lnglats), sum(p[1] for p in lnglats) / len(lnglats))   # 해외면 지역 원점
        points = [non_rhino_utils.get_tm_from_wgs84(lng, lat) for lng, lat in lnglats]
    elif msg.get("center") and msg.get("offsets"):
        non_rhino_utils.set_projection(float(msg["center"][0]), float(msg["center"][1]))
        cx, cy = non_rhino_utils.get_tm_from_wgs84(float(msg["center"][0]), float(msg["center"][1]))
        points = [(cx + float(dx), cy + float(dy)) for dx, dy in msg["offsets"]]
    else:
        return _empty_area_state()
    try:
        request = context_builder.get_request_with_defaults({"target": {"mode": "area", "ring": points}, "site_db": site_db})
        target = context_builder.resolve_target(request)
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as error:
        return _empty_area_state(str(error.args[0]) if error.args else str(error))
    ring = target.site_rings[0]
    cx, cy = target.center
    geojson = review_map.get_parcels_geojson([lot.pnu for lot in target.lots], "target", site_db) if target.lots else {"type": "FeatureCollection", "features": []}
    ring_lnglat = review_map.get_wgs84_ring(list(ring) + [ring[0]])
    geojson["features"].append({"type": "Feature", "properties": {"role": "area"}, "geometry": {"type": "Polygon", "coordinates": [ring_lnglat]}})
    return {
        "type": "area_state", "ok": True, "text": "", "ring_tm": [list(p) for p in ring], "ring_lnglat": ring_lnglat,
        "center": review_map.get_wgs84_ring([target.center])[0], "center_tm": [cx, cy],
        "offsets": [[round(x - cx, 3), round(y - cy, 3)] for x, y in ring], "area": round(non_rhino_utils.get_ring_area(ring), 1),
        "lots": len(target.lots), "lots_area": round(sum(lot.area for lot in target.lots), 1), "lot_name": target.name,
        "target_geojson": geojson, "warnings": target.warnings, "snapped": bool(msg.get("snapped")),
    }


def get_point_state(msg, site_db=None):
    # type: (dict, str) -> dict
    """point_state 페이로드 — 위치 하나(지도 클릭·검색 결과)의 이름. center [lng, lat]가 없으면 빈 상태(지움)."""
    if not msg.get("center"):
        return {"type": "point_state", "ok": True, "center": None, "center_tm": None, "lot_name": ""}
    context_builder = loader.load("context_builder")
    non_rhino_utils = loader.load("non_rhino_utils")
    lng, lat = float(msg["center"][0]), float(msg["center"][1])
    non_rhino_utils.set_projection(lng, lat)   # 해외면 지역 원점, 국내면 EPSG:5186
    x, y = non_rhino_utils.get_tm_from_wgs84(lng, lat)
    request = context_builder.get_request_with_defaults({"target": {"mode": "point", "center": [x, y]}, "site_db": site_db})
    target = context_builder.resolve_target(request)
    return {"type": "point_state", "ok": True, "center": [round(lng, 7), round(lat, 7)], "center_tm": [round(x, 2), round(y, 2)],
            "lot_name": target.name}


def get_area_packs(bbox, seq=None, manifest=None):
    # type: (list, int, dict) -> dict
    """area_packs 페이로드 — 지도 화면(경위도 bbox)에 걸치는데 아직 안 받은 시군구 팩. 해외·매니페스트 없음은 빈 목록.

    출력: {"type": "area_packs", seq, missing[{name, label, mb}], mb, labels(시군구 이름, 중복 없이)}.
    """
    empty = {"type": "area_packs", "seq": seq, "missing": [], "mb": 0, "labels": []}
    constants = loader.load("constants")
    non_rhino_utils = loader.load("non_rhino_utils")
    data_pack = loader.load("data_pack")
    if len(bbox) != 4 or not constants.DATA_MANIFEST_URL and manifest is None:
        return empty
    west, south, east, north = (float(v) for v in bbox)
    if not non_rhino_utils.is_korea((west + east) / 2.0, (south + north) / 2.0):
        return empty
    corners = [non_rhino_utils.get_tm_from_wgs84(x, y) for x in (west, east) for y in (south, north)] if not non_rhino_utils.is_local_projection() else []
    if not corners:
        return empty
    bounds = (min(c[0] for c in corners), min(c[1] for c in corners), max(c[0] for c in corners), max(c[1] for c in corners))
    try:
        missing = [pack for pack in data_pack.get_missing_packs(manifest or data_pack.get_manifest(), bounds=bounds)
                   if pack["name"][:5].isdigit()]   # 시군구 팩만 — 옛 시도 팩은 지역 받기 대상이 아니다
    except Exception:   # 오프라인 — 지도는 그대로 쓴다
        return empty
    labels = list(dict.fromkeys(" ".join(pack["label"].split()[:-1]) for pack in missing if pack["name"].endswith("_site.db")))
    total = sum(pack.get("xz_size", 0) for pack in missing) / 1048576.0
    # 받아 둔 팩의 새 판(매니페스트 sha256이 바뀜) — 칩이 '새 판 있음'으로 구분한다
    installed = set(os.listdir(data_pack.get_data_dir())) if os.path.isdir(data_pack.get_data_dir()) else set()
    return {"type": "area_packs", "seq": seq, "missing": [{"name": p["name"], "label": p["label"], "mb": round(p.get("xz_size", 0) / 1048576.0, 1),
                                                           "update": p["name"] in installed} for p in missing],
            "mb": round(total), "labels": labels}


def get_target_from_msg(msg):
    # type: (dict) -> dict
    """generate·preflight 메시지 → 요청 target. 예전 메시지(pnus만)는 필지 방식."""
    return dict(msg.get("target") or {"mode": "lots", "pnus": [str(p) for p in (msg.get("pnus") or [])]})


def get_preflight_key(msg):
    # type: (dict) -> tuple
    """메모이즈 키 (target json, radius, shape, paper, tuple(paper_mm), tuple(scales)) — paper_mm이 빠지면 용지 '직접'이 안 바뀐다."""
    return (json.dumps(get_target_from_msg(msg), sort_keys=True), msg.get("radius"), msg.get("shape"), msg.get("paper"),
            tuple(msg.get("paper_mm") or ()), tuple(msg.get("scales") or ()))


def get_preflight_result(msg, site_db=None, context_db=None, today=None):
    # type: (dict, str, str, datetime.date) -> dict
    """preflight_result 페이로드 — context_builder.preflight + type·seq 에코. 옵션은 prefs(include_minor_buildings 포함) 위에 메시지 값을 덮는다 —
    preflight 건물 수와 generate 실제 수가 같은 옵션으로 나온다(context_db.count_in_bounds)."""
    context_builder = loader.load("context_builder")
    site_prefs = loader.load("site_prefs")
    options = dict(site_prefs.get_options())
    options.update({key: msg[key] for key in ("radius", "shape", "paper", "paper_mm", "scales") if msg.get(key) is not None})
    result = context_builder.preflight({"target": get_target_from_msg(msg), "options": options, "site_db": site_db, "context_db": context_db}, today)
    result.update(type="preflight_result", seq=msg.get("seq"))
    return result


def get_skipped_details(options):
    # type: (dict) -> tuple
    """generate 시작 때의 (skipped phase 집합, phase_detail 초기값) — 옵션으로 끈 phase는 '건너뜀 — 옵션'."""
    context_builder = loader.load("context_builder")
    skipped = context_builder.get_skipped_phases(context_builder.get_request_with_defaults({"options": options})["options"])
    return skipped, {phase: SKIPPED_DETAILS.get(phase, SKIPPED_OPTION_DETAIL) for phase in skipped}


def get_done_message(response):
    # type: (dict) -> dict
    """context_builder.run 응답(ok=true) → done 푸시. 응답 dict 모양이 곧 done 페이로드라 type만 붙인다."""
    return dict(response, type="done")


def get_failed_progress(response, phase, skipped, details):
    # type: (dict, str, set, dict) -> dict
    """run 응답(ok=false) → progress{state: failed|cancelled, error}. phase는 마지막 콜백의 phase."""
    context_builder = loader.load("context_builder")
    state = "cancelled" if response.get("cancelled") else "failed"
    error = response.get("error") or {"code": "exception", "title": "생성 실패", "detail": ""}
    return context_builder.get_progress_message(phase, 1.0, "취소됨" if state == "cancelled" else error.get("title", ""),
                                                skipped, details, state=state, error=error)


def resolve_open_path(path, root=None):
    # type: (str, str) -> str
    """open_path 명령의 경로를 절대경로로 만든다. 외부 URL은 거부, 상대경로는 쓰기 자리(HOME_DIR) 기준이고 거기 없으면
    코드 루트(docs/ 등 배포 문서), .env가 없으면 두 줄 템플릿을 만든다. 없는 경로는 ValueError."""
    path = str(path or "").strip()
    if not path or "://" in path:
        raise ValueError("열 수 없는 경로입니다: %s" % (path or "빈 값"))
    root = root or loader.load("constants").HOME_DIR
    full = path if os.path.isabs(path) else os.path.join(root, path)
    if not os.path.exists(full) and not os.path.isabs(path) and path != ".env" and os.path.exists(os.path.join(ROOT_DIR, path)):
        full = os.path.join(ROOT_DIR, path)
    if os.path.basename(full) == "data":
        os.makedirs(full, exist_ok=True)
    if os.path.basename(full) == ".env" and not os.path.exists(full):
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(ENV_TEMPLATE)
    if not os.path.exists(full):
        raise ValueError("경로가 없습니다: %s" % full)
    return full


def _open_with_os(path):
    # type: (str) -> None
    """폴더는 탐색기, 파일은 OS 기본 앱으로 연다."""
    if sys.platform == "darwin":
        subprocess.Popen(["open", path])
    elif sys.platform.startswith("win"):
        os.startfile(path)   # noqa: attr-defined — Windows 전용
    else:
        subprocess.Popen(["xdg-open", path])


# ── 컨트롤러 (Rhino) ────────────────────────────────────────

class _SiteController:
    """패널 명령과 로직 모듈 사이를 잇는다. 상태는 running·cancel_requested 플래그와 preflight 메모이즈뿐 —
    마지막 결과 폴더는 기억하지 않는다(결과 명령은 JS가 dir을 붙인다)."""

    def __init__(self):
        self.push = lambda msg: None   # 호스트 생성 후 host.push로 바꿔 단다
        self._running = False
        self._cancel_requested = False
        self._preflight_memo = {}
        self._context_builder = None   # generate 동안 콜백이 쓴다 (콜백 안 loader.load는 전체 reload라 피한다)
        self._skipped = set()
        self._phase_detail = {}
        self._last_phase = "query"
        self._keep = {}                # 마지막 결과의 시트 데이터(지형 삼각형 포함) — 도면 스타일 미리보기·적용이 다시 쓴다

    def handle(self, msg):
        # type: (dict) -> None
        """JS 명령 하나를 라우팅한다. 호스트가 UI 스레드에서 부른다."""
        msg = msg or {}
        cmd = msg.get("cmd", "")
        handlers = {
            "init": self._init, "search": self._search, "map_lots": self._map_lots, "select_lots": self._select_lots,
            "set_area": self._set_area, "set_point": self._set_point, "pick_curve": self._pick_curve, "snap_area": self._snap_area,
            "preflight": self._preflight, "generate": self._generate, "cancel": self._cancel,
            "import_context": self._import_context, "export_basemap": self._export_basemap, "zoom_view": self._zoom_view,
            "open_path": self._open_path, "save_prefs": self._save_prefs, "download_data": self._download_data,
            "style_preview": self._style_preview, "apply_style": self._apply_style, "save_style": self._save_style, "sheet_ai": self._sheet_ai,
            "area_packs": self._area_packs,
        }
        handler = handlers.get(cmd)
        if handler is None:
            self.push({"type": "error", "context": "init", "text": "알 수 없는 명령입니다: %s" % cmd, "detail": ""})
            return
        self._guard(_ERROR_CONTEXTS.get(cmd, cmd), lambda: handler(msg))

    def _guard(self, context, action):
        # type: (str, object) -> None
        """명령 처리를 감싸 오류를 error 푸시로 보낸다 — 호스트 _run_command까지 예외가 새면 Rhino가 죽는다."""
        try:
            action()
        except (ValueError, KeyError, FileNotFoundError, RuntimeError) as error:
            text = str(error.args[0]) if error.args else str(error)
            self.push({"type": "error", "context": context, "text": text, "detail": ""})
        except Exception:
            self.push({"type": "error", "context": context, "text": "예상 밖 오류", "detail": traceback.format_exc()})

    def on_close(self):
        # type: () -> None
        """창 닫힘 — 생성 중이면 cancel과 같은 경로."""
        if self._running:
            self._cancel_requested = True

    # ── 명령 처리 ──

    def _init(self, msg):
        self._preflight_memo.clear()   # 키 유무·새 판은 메모 키에 없으므로 init마다 비운다
        self.push(get_init_state())

    def _search(self, msg):
        query = (msg.get("query") or "").strip()
        if not query:
            raise ValueError("주소 또는 PNU를 입력하세요")
        self.push(get_search_result(query))

    def _map_lots(self, msg):
        self.push(get_map_lots(msg.get("bbox") or [], msg.get("seq")))

    def _select_lots(self, msg):
        self.push(get_lot_state(msg.get("pnus") or []))

    def _set_area(self, msg):
        self.push(get_area_state(msg))

    def _set_point(self, msg):
        self.push(get_point_state(msg))

    def _pick_curve(self, msg):
        """Rhino에서 고른 닫힌 커브 하나 → curve_shape. 이미 선택된 커브가 하나면 그것, 없으면 고르기 프롬프트.
        커브 좌표가 실제 위치(이 도구가 만든 문서의 원점 기준, 또는 서울 EPSG:5186 범위)면 located=true + ring_tm,
        아니면 모양만(offsets) — 패널이 지도 가운데에 얹고 사용자가 지도를 움직여 놓는다."""
        context_geometry = loader.load("context_geometry")
        context_baker = loader.load("context_baker")
        constants = loader.load("constants")
        non_rhino_utils = loader.load("non_rhino_utils")
        doc = Rhino.RhinoDoc.ActiveDoc
        curve = None
        selected = [o for o in doc.Objects.GetSelectedObjects(False, False)]
        curves = [o for o in selected if isinstance(o.Geometry, Rhino.Geometry.Curve)]
        if len(curves) > 1:
            self.push({"type": "curve_shape", "ok": False, "text": "커브를 하나만 선택하세요(%d개 선택됨)" % len(curves)})
            return
        if curves:
            curve = curves[0].Geometry
        else:
            go = Rhino.Input.Custom.GetObject()
            go.SetCommandPrompt("대상지 구역 커브 선택 (닫힌 평면 커브 하나)")
            go.GeometryFilter = Rhino.DocObjects.ObjectType.Curve
            go.GeometryAttributeFilter = Rhino.Input.Custom.GeometryAttributeFilter.ClosedCurve
            go.SubObjectSelect = False
            if go.Get() != Rhino.Input.GetResult.Object:
                self.push({"type": "curve_shape", "ok": False, "text": "커브 선택을 취소했습니다"})
                return
            curve = go.Object(0).Curve()
            doc.Objects.UnselectAll()
            doc.Views.Redraw()
        unit_scale = 1.0 / context_baker.get_model_unit_scale(doc)   # 문서 단위 → m
        ring, problem = context_geometry.get_curve_ring(curve, unit_scale, doc.ModelAbsoluteTolerance)
        if ring is None:
            self.push({"type": "curve_shape", "ok": False, "text": problem})
            return
        min_x, min_y, max_x, max_y = non_rhino_utils.get_bbox(ring)
        cx, cy = (min_x + max_x) * 0.5, (min_y + max_y) * 0.5
        doc_origin = context_baker.get_doc_origin(doc)
        b = constants.SEOUL_TM_BOUNDS
        if doc_origin is not None:
            world = [(x + doc_origin[0], y + doc_origin[1]) for x, y in ring]
        elif b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
            world = ring
        else:
            world = None
        self.push({"type": "curve_shape", "ok": True, "text": "", "located": world is not None,
                   "ring_tm": [list(p) for p in world] if world else [],
                   "offsets": [[round(x - cx, 3), round(y - cy, 3)] for x, y in ring],
                   "area": round(non_rhino_utils.get_ring_area(ring), 1), "vertices": len(ring)})

    def _snap_area(self, msg):
        """구역계를 필지 경계에 맞춘다 — 걸친 일반 필지는 50 % 규칙대로 넣거나 빼고, 도로·하천은 그린 선대로 가로지른다."""
        context_builder = loader.load("context_builder")
        context_geometry = loader.load("context_geometry")
        constants = loader.load("constants")
        current = get_area_state({"ring_tm": msg.get("ring_tm")})
        if not current["ok"]:
            self.push(current)
            return
        add, cut = context_builder.get_snap_rings([tuple(p) for p in current["ring_tm"]])
        if not add and not cut:
            self.push(dict(current, ok=False, text="걸친 필지가 없어 맞출 게 없습니다"))
            return
        snapped = context_geometry.get_snapped_ring([tuple(p) for p in current["ring_tm"]], add, cut, constants.UNION_TOLERANCE)
        if not snapped:
            self.push(dict(current, ok=False, text="필지 경계에 맞추지 못했습니다 — 구역을 조금 다르게 그려 보세요"))
            return
        self.push(get_area_state({"ring_tm": snapped, "snapped": True}))

    def _preflight(self, msg):
        key = get_preflight_key(msg)
        result = self._preflight_memo.get(key)
        if result is None:
            result = self._preflight_memo[key] = get_preflight_result(msg)
        self.push(dict(result, seq=msg.get("seq")))

    def _progress(self, phase, fraction, text):
        # type: (str, float, str) -> bool
        """엔진 콜백 — push → RhinoApp.Wait()(WebView 이벤트·cancel 명령 펌핑) → 취소 플래그."""
        self._last_phase = phase
        self.push(self._context_builder.get_progress_message(phase, fraction, text, self._skipped, self._phase_detail))
        Rhino.RhinoApp.Wait()
        return not self._cancel_requested

    def _generate(self, msg):
        """context_builder.run을 UI 스레드에서 동기 호출. 끝나면 done, 실패·취소면 progress{failed|cancelled}."""
        if self._running:
            self.push({"type": "error", "context": "generate", "text": "이미 생성 중입니다", "detail": ""})
            return
        context_builder = loader.load("context_builder")
        context_baker = loader.load("context_baker")
        site_prefs = loader.load("site_prefs")
        lot_db = loader.load("lot_db")
        request = {"target": get_target_from_msg(msg), "options": dict(msg.get("options") or {})}
        self._context_builder = context_builder
        self._skipped, self._phase_detail = get_skipped_details(request["options"])
        self._last_phase = "query"
        self._running, self._cancel_requested = True, False
        doc = Rhino.RhinoDoc.ActiveDoc
        try:
            response = context_builder.run(request, self._progress, doc, self._keep)
        finally:
            self._running = False
        doc.Views.Redraw()
        if not response["ok"]:
            self.push({"type": "log", "level": "error", "text": "%s: %s\n%s" % (response["error"]["code"], response["error"]["title"], response["error"]["detail"])})
            self.push(get_failed_progress(response, self._last_phase, self._skipped, self._phase_detail))
            return
        self.push(self._context_builder.get_progress_message(self._last_phase, 1.0, "", self._skipped, self._phase_detail, state="done"))
        self.push(get_done_message(response))
        if request["target"]["mode"] == "lots":   # 최근 대상지는 필지 방식만(구역·위치는 다시 그리는 편이 빠르다)
            pnus = request["target"]["pnus"]
            total_area = sum(lot.area for lot in lot_db.load(pnus).lots)
            site_prefs.add_recent(pnus, response["lot_name"].replace("_", " "), total_area, datetime.date.today().isoformat())
        if response["options"].get("zoom_after_import"):
            context_baker.zoom_to_site(doc, response["dir"])

    def _area_packs(self, msg):
        self.push(get_area_packs(msg.get("bbox") or [], msg.get("seq")))

    def _cancel(self, msg):
        if self._running:
            self._cancel_requested = True   # 다음 콜백이 False를 돌려준다

    def _download_data(self, msg):
        """바뀐 팩만 차례로 받는다. 진행률은 1 % 단위로만 푸시한다(조각 1 MB마다 보내면 수천 번이다). 끝나면 init_state."""
        if self._running:
            raise ValueError("다른 작업이 진행 중입니다")
        data_pack = loader.load("data_pack")
        packs = data_pack.get_missing_packs(data_pack.get_manifest())
        if msg.get("names"):   # 지역 받기(area_packs가 알려 준 시군구 팩)
            packs = [pack for pack in packs if pack["name"] in set(msg["names"])]
        self._running, self._cancel_requested = True, False
        try:
            for index, pack in enumerate(packs):
                last = [-1]

                def progress(done, total, pack=pack, index=index, last=last):
                    percent = int(100 * done / max(total, 1))
                    if percent != last[0]:
                        last[0] = percent
                        self.push({"type": "data_progress", "text": "%s 받는 중 (%d/%d) %d%% · %.1f GB"
                                   % (pack["label"], index + 1, len(packs), percent, total / 1024.0 ** 3)})
                    Rhino.RhinoApp.Wait()
                    return not self._cancel_requested

                if not data_pack.download_pack(pack, progress=progress):
                    self.push({"type": "data_progress", "text": "받기를 멈췄습니다 — 다 받은 팩은 남고, 다시 누르면 나머지를 받습니다"})
                    break
        finally:
            self._running = False
        self.push(get_init_state())

    def _run_busy(self, label, context, work):
        # type: (str, str, object) -> None
        """busy{on} 푸시 → AsyncInvoke로 작업 예약(busy가 먼저 그려진다) → 작업 → busy{off}. Import·Export처럼 UI 스레드가 멈추는 짧은 작업용."""
        self.push({"type": "busy", "on": True, "label": label})

        def run_work():
            try:
                self._guard(context, work)
            finally:
                self.push({"type": "busy", "on": False, "label": ""})

        forms.Application.Instance.AsyncInvoke(System.Action(run_work))

    def _import_context(self, msg):
        result_dir = str(msg.get("dir") or "")
        if not os.path.isdir(result_dir):
            raise ValueError("결과 폴더가 없습니다: %s" % result_dir)
        context_baker = loader.load("context_baker")
        site_prefs = loader.load("site_prefs")

        def work():
            doc = Rhino.RhinoDoc.ActiveDoc
            result = context_baker.import_3dm(doc, result_dir)
            self.push({"type": "imported", "ok": result["ok"], "dir": result_dir, "layers": result["layers"], "objects": result["objects"],
                       "replaced": result["replaced"], "text": result["text"]})
            if result["ok"] and site_prefs.get_options().get("zoom_after_import"):
                context_baker.zoom_to_site(doc, result_dir)

        self._run_busy("문서에 넣는 중", "import", work)

    def _export_basemap(self, msg):
        result_dir = str(msg.get("dir") or "")
        scale = int(msg.get("scale") or 0)
        if not os.path.isdir(result_dir):
            raise ValueError("결과 폴더가 없습니다: %s" % result_dir)
        context_builder = loader.load("context_builder")

        def work():
            # 문서가 아니라 DB에서 다시 쓴다(context.json의 pnus·options) — 문서에서 객체를 지웠어도 된다
            try:
                result = context_builder.export_basemap(result_dir, scale)
                self.push({"type": "exported", "ok": True, "dir": result_dir, "scale": scale, "path": result["path"], "text": ""})
            except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
                self.push({"type": "exported", "ok": False, "dir": result_dir, "scale": scale, "path": "", "text": str(exc)})

        self._run_busy("내보내는 중", "export", work)

    def _zoom_view(self, msg):
        context_baker = loader.load("context_baker")
        if not context_baker.zoom_to_site(Rhino.RhinoDoc.ActiveDoc, str(msg.get("dir") or ""), msg.get("center")):
            raise ValueError("CTX::Site 객체가 없습니다 — 먼저 [문서에 넣기]")

    def _open_path(self, msg):
        _open_with_os(resolve_open_path(msg.get("path")))

    def _save_prefs(self, msg):
        loader.load("site_prefs").save_options(msg.get("options") or {})

    def _get_result_dir(self, msg):
        result_dir = str(msg.get("dir") or "")
        if not os.path.isdir(result_dir):
            raise ValueError("결과 폴더가 없습니다: %s" % result_dir)
        return result_dir

    def _style_preview(self, msg):
        """한 장을 스타일로 다시 그려 SVG 문자열을 보낸다(파일 안 씀). 결과 데이터는 _keep 캐시(없으면 context.json으로 한 번 prepare)."""
        result = loader.load("context_builder").preview_sheet(self._get_result_dir(msg), int(msg.get("sheet_id") or 0), msg.get("style") or {}, self._keep)
        self.push(dict(result, type="style_preview", seq=msg.get("seq"), sheet_id=int(msg.get("sheet_id") or 0)))

    def _apply_style(self, msg):
        result_dir = self._get_result_dir(msg)
        context_builder = loader.load("context_builder")
        style = msg.get("style") or {}

        def work():
            try:
                result = context_builder.apply_style(result_dir, style, self._keep)
                self.push(dict(result, type="style_applied", ok=True, dir=result_dir, text=""))
            except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
                self.push({"type": "style_applied", "ok": False, "dir": result_dir, "sheets": [], "basemaps": [], "kept": [], "text": str(exc)})

        self._run_busy("도면 다시 그리는 중", "style", work)

    def _sheet_ai(self, msg):
        """도면 한 장(path) 또는 결과 폴더 전부(all)를 레이어 .ai로 — 하나면 쓰고 바로 연다."""
        result_dir = self._get_result_dir(msg)
        sheet_svg = loader.load("sheet_svg")
        sheets_dir = os.path.join(result_dir, loader.load("constants").RESULT_SHEETS_DIRNAME)
        paths = sorted(os.path.join(sheets_dir, n) for n in os.listdir(sheets_dir) if n.endswith(".svg")) if msg.get("all") else [str(msg.get("path") or "")]
        if not all(p.startswith(sheets_dir) and os.path.exists(p) for p in paths):
            raise ValueError("도면 파일이 없습니다")

        def work():
            written = [sheet_svg.get_sheet_ai(p) for p in paths]
            self.push({"type": "sheet_ai", "ok": True, "dir": result_dir, "paths": written})
            if not msg.get("all"):
                _open_with_os(written[0])

        self._run_busy("레이어 .ai 쓰는 중", "style", work)

    def _save_style(self, msg):
        styles = loader.load("site_prefs").save_style(msg.get("name"), msg.get("style") or {})
        self.push({"type": "styles", "styles": styles, "saved": msg.get("name"), "dir": loader.load("site_prefs").get_styles_dir()})


# error.context — JS가 표시 자리를 고른다(panel_ui.md 오류 규약)
_ERROR_CONTEXTS = {"select_lots": "select", "map_lots": "select", "set_area": "select", "set_point": "select", "pick_curve": "select",
                   "snap_area": "select", "import_context": "import", "export_basemap": "export",
                   "zoom_view": "open", "open_path": "open", "save_prefs": "init", "cancel": "generate", "download_data": "init",
                   "style_preview": "style", "apply_style": "style", "save_style": "style", "sheet_ai": "style"}


def _show_panel():
    """패널을 하나만 띄운다. 이미 떠 있으면 앞으로 가져온다."""
    existing = scriptcontext.sticky.get(PANEL_STICKY_KEY)
    if existing is not None:
        try:
            existing.bring_to_front()
            print("[대지검토] 이미 열린 패널을 앞으로 가져왔습니다")
            return
        except Exception:
            scriptcontext.sticky.pop(PANEL_STICKY_KEY, None)   # 이미 닫혔거나 못 쓰는 패널 — 새로 연다

    panel_host = loader.load("panel_host")
    controller = _SiteController()
    host = panel_host.PanelHost(on_command=controller.handle)
    controller.push = host.push

    def on_closed():
        controller.on_close()
        scriptcontext.sticky.pop(PANEL_STICKY_KEY, None)

    host.on_closed = on_closed
    scriptcontext.sticky[PANEL_STICKY_KEY] = host
    host.show()


if Rhino is not None:
    _show_panel()
