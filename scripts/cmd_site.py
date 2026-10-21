#! python 3
"""Gorani 패널 진입 스크립트 + 컨트롤러 — Rhino에서 직접 실행한다.

    ! _-ScriptEditor _Run "<저장소 경로>/scripts/cmd_site.py"

panel_host.PanelHost(Eto WebView)와 로직 모듈을 잇는다. JS 명령(dict)을 받아 로직 함수를 부르고 host.push()로
상태를 보낸다. 메시지 계약은 docs/panel_ui.md('아키텍처 정합' 절 우선). 생성은 context_builder.run을 UI 스레드에서
동기 호출하고, 진행률은 콜백 안에서 push + _pump(Rhino.RhinoApp.Wait)로 펌핑한다(서브프로세스 없음).

명령 → 로직 (22개)
    init            → get_init_state (DB 존재·원천 상태·타일·지도·prefs·recent·시트 카탈로그). 첫 init만 review_map.get_ip_center(지도 첫 위치). preflight 메모이즈 비움
    search          → get_search_result (pnu_loader.resolve_addresses + review_map.get_parcel_centers)
    map_lots        → review_map.get_parcels_in_bbox (seq 에코)
    select_lots     → get_lot_state (review_map.get_parcels_geojson + 대상 합집합 role target)
    set_area        → get_area_state (구역 링 → context_builder.resolve_target: 안전장치·안의 필지)
    set_point       → get_point_state (위치 → 이름)
    pick_curve      → Rhino 선택(또는 고르기) 커브 → context_geometry.get_curve_ring → curve_shape
    preflight       → context_builder.preflight (메모이즈, seq 에코)
    generate        → context_builder.run (콜백 = push + Wait + 취소 플래그) → done / progress{failed|cancelled}
    cancel          → 플래그만
    import_context  → context_baker.import_3dm (busy 푸시 사이)
    export_basemap  → context_builder.export_basemap (DB에서 basemap_ai로 다시 씀 · busy·exported)
    zoom_view       → context_baker.zoom_to_site
    open_path       → 폴더·파일·.env 템플릿을 OS로 연다
    open_eum        → PNU의 토지이음 토지이용계획 열람을 OS 브라우저로 연다(constants.EUM_LAND_USE_URL)
    save_prefs      → site_prefs.save_options
    style_preview   → context_builder.preview_sheet (스타일 바꾼 한 장 SVG 문자열 — 파일 안 씀, seq 에코)
    apply_style     → context_builder.apply_style (시트 전부 + 쓴 .ai 다시 쓰기, busy·style_applied)
    save_style      → site_prefs.save_style (HOME_DIR/styles/<이름>.json → styles)
    sheet_ai        → sheet_svg.get_sheet_ai (도면 SVG → 레이어 .ai, 누를 때 · all이면 결과 폴더 전부, busy·sheet_ai) → 하나면 OS로 연다
    stats_consent   → site_prefs.save_stats_consent (Blender — 사용 통계 동의/거절, 응답 없음)
    download_data   → data_pack (매니페스트 → 바뀐 팩만 받기, 콜백 = data_progress 푸시 + Wait + 취소 플래그) → init_state

조립 함수(get_*·resolve_open_path)는 Rhino 없이 돈다 — tests/test_site_ui_contract.py가 fixture DB로 키 집합을 확인한다.
Rhino 모듈이 없으면(python3·Blender) 패널을 띄우지 않는다. Blender판은 cmd_blender.py가 _SiteController를 상속해 호스트 연결(_get_doc·_pump·
_defer·_redraw·_get_host_stats)과 Rhino 전용 명령(pick_curve·import_context)만 바꿔 단다.
"""

import datetime
import importlib.util
import json
import os
import subprocess
import sys
import time
import traceback

try:
    import Rhino
    import scriptcontext
    import System
    import Eto.Forms as forms
except ImportError:   # python3 테스트 — 조립 함수만 쓴다
    Rhino = scriptcontext = System = forms = None

if __package__:   # Blender 확장 — scripts/가 패키지(최상위 모듈 금지 정책)
    from . import loader
else:   # cmd_install.py와 같은 방식 — 고유 모듈명으로 로더를 읽어 Rhino 공유 인터프리터의 이름 충돌을 막는다
    _spec = importlib.util.spec_from_file_location(
        "gorani_loader",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "loader.py"),
    )
    loader = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = loader
    _spec.loader.exec_module(loader)

ROOT_DIR = loader.ROOT_DIR
PANEL_STICKY_KEY = "gorani_site_panel"
ENV_TEMPLATE = "VWORLD_API_KEY=\n"
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


def get_init_state(site_db=None, context_db=None, today=None, manifest=None, map_center=None):
    # type: (str, str, datetime.date, dict, list) -> dict
    """init_state 페이로드(panel_ui.md).

    입력: DB 경로 override 2개(테스트가 fixture를 꽂는다. None = constants 경로), today(테스트용), manifest(테스트용. None = 이번 세션에 받은 것).
          map_center(지도 첫 위치 [lng, lat] — _init이 IP로 짐작. None = 서울시청).
    처리: 필지 DB 존재 → blocked, context_builder.get_sources/get_source_warnings, review_map 타일·지도, site_prefs 옵션·recent,
          SHEET_CATALOG, 매니페스트 업데이트·공지(data_pack.get_notice_state). 네트워크 접근 없음 — 매니페스트는 _init이 먼저 받아 둔다.
          generator는 항상 ok(서브프로세스 없음 — UI 호환 키).
    출력: {"type": "init_state", version, blocked, paths, generator, host, stats_consent, links, sources, warnings, tile, map, options, modes, recent, sheet_catalog,
          style_presets, style_defaults, style_ramps, styles, update, notices}.
    """
    constants = loader.load("constants")
    context_builder = loader.load("context_builder")
    review_map = loader.load("review_map")
    site_prefs = loader.load("site_prefs")
    has_lot_db = os.path.exists(site_db) if site_db else bool(loader.load("data_pack").get_local_paths("site"))
    sources = context_builder.mark_downloadable(context_builder.get_sources(site_db, context_db, today), not site_db)
    host = dict(constants.HOST_LABELS[context_builder.get_host()])
    host["ask_stats"] = host["ask_stats"] and loader.load("usage_stats").is_configured()   # 보낼 곳이 없으면 묻지 않는다
    return dict({
        "type": "init_state",
        "version": constants.PANEL_VERSION,
        "blocked": not has_lot_db,
        "paths": {"root": constants.HOME_DIR, "lot_db": constants.DATABASE_PATH, "context_db": constants.CONTEXT_DATABASE_PATH,
                  "env": ".env", "install_doc": constants.INSTALL_DOC},
        "generator": {"ok": True, "python": host["name"] + " Python", "text": host["name"] + " 내장"},
        "host": host,
        "stats_consent": site_prefs.get_stats_consent(),
        "links": dict(constants.PANEL_LINKS),   # 메뉴가 주소를 그대로 보여 준다. 여는 건 open_url{key}
        "can_download": bool(constants.DATA_MANIFEST_URL),
        "sources": sources,
        "warnings": context_builder.get_source_warnings(sources),
        "tile": review_map.get_tile_config(),
        "map": review_map.get_map_init(map_center),
        "options": site_prefs.get_options(),
        "modes": {"defaults": constants.MODE_DEFAULTS, "shapes": {k: list(v) for k, v in constants.SHAPES_BY_MODE.items()}},
        "recent": site_prefs.get_recent(),
        "sheet_catalog": [{"id": sheet_id, "key": key, "name": name, "subtitle": en, "needs": needs, "korea_only": key in constants.SHEET_KOREA_ONLY,
                           "group": constants.SHEET_GROUP.get(key, "base")}
                          for sheet_id, key, name, en, needs in constants.SHEET_CATALOG],
        "style_presets": {key: dict(preset) for key, preset in constants.STYLE_PRESETS.items()},
        "style_defaults": dict(constants.STYLE_DEFAULTS),
        "style_ramps": {key: list(ramp) for key, ramp in constants.STYLE_RAMPS.items()},
        "styles": site_prefs.list_styles(),
    }, **loader.load("data_pack").get_notice_state(manifest))


def get_search_result(query, site_db=None, region=None):
    # type: (str, str, str) -> dict
    """search_result 페이로드. 주소·지번·PNU 한 줄 → 후보 0~8건(+중심 좌표). VWorld 키가 있으면 보조 검색을 켠다.
    Global 모드는 필지 DB를 보지 않고 지명 검색(Nominatim)만."""
    constants = loader.load("constants")
    pnu_loader = loader.load("pnu_loader")
    review_map = loader.load("review_map")
    use_vworld = bool(pnu_loader.get_local_env_value(constants.VWORLD_API_KEY_ENV))
    try:
        matches = [] if region == "global" else pnu_loader.resolve_addresses([query], use_vworld, site_db)[0].matches[:SEARCH_MAX_MATCHES]
    except FileNotFoundError:   # 국내 필지 DB 없음 — 지명 검색으로
        matches = []
    if not matches:
        places = loader.load("osm_context").search_places(query, SEARCH_MAX_MATCHES)
        return {"type": "search_result", "query": query, "seq": None,
                "matches": [{"pnu": "", "address": p["name"], "jibun": "", "land_category": "", "area": None, "center": p["center"]} for p in places],
                "message": "지명 후보 %d건 (OpenStreetMap)" % len(places) if places else "찾지 못했습니다. 동 이름까지 적어 보세요"}
    centers = review_map.get_parcel_centers([m.pnu for m in matches], site_db) if matches else {}
    return {
        "type": "search_result", "query": query, "seq": None,
        "matches": [{"pnu": m.pnu, "address": m.address, "jibun": m.lot_number or _jibun(m.address), "land_category": m.land_category,
                     "area": m.geometry_area, "center": centers.get(m.pnu)} for m in matches],
        "message": "후보 %d건" % len(matches) if matches else "찾지 못했습니다. 동 이름까지 적어 보세요",
    }


def get_map_lots(bbox, seq, site_db=None):
    # type: (list, int, str) -> dict
    """map_lots 페이로드 — review_map.get_parcels_in_bbox 그대로 + seq 에코. 그 지역 필지 데이터가 아직 없으면 빈 지도
    (오류가 아니다 — area_packs가 받는 중이고, 다 받으면 패널이 다시 묻는다)."""
    review_map = loader.load("review_map")
    try:
        result = review_map.get_parcels_in_bbox(bbox, database_path=site_db)
    except FileNotFoundError:
        return {"type": "map_lots", "seq": seq, "geojson": _EMPTY_FC, "truncated": False}
    return {"type": "map_lots", "seq": seq, "geojson": result["geojson"], "truncated": result["truncated"]}


def get_lot_state(pnus, site_db=None):
    # type: (list, str) -> dict
    """lot_state 페이로드.

    입력: 현재 대상 PNU 전체(빈 목록 = 모두 지움).
    처리: lot_db.load → 필지별 Feature(role lot) + 대상 합집합 1개(role target — 합필 외곽 MultiPolygon, context_builder.get_target_rings),
          lot_name·중심(100 m 내림 전)·multipart 경고는 context_builder의 같은 규칙을 쓴다.
          필지 정보 = 용도지역(+법정 건폐·용적)·지역지구등(포함·저촉)·대장/도형 면적 차이·기준일.
    출력: {"type": "lot_state", lots[{pnu, address, jibun, land_category, area, warn, zones, designations, registered_area,
          geometry_area, area_gap, area_gap_flag, reference_date}], total_area, lot_name, center, target_geojson, warnings, land_use_date}.
    """
    pnus = [str(p) for p in (pnus or []) if str(p).strip()]
    if not pnus:
        return {"type": "lot_state", "lots": [], "total_area": 0.0, "lot_name": "", "center": None, "target_geojson": _EMPTY_FC, "warnings": [],
                "land_use_date": ""}
    constants = loader.load("constants")
    context_builder = loader.load("context_builder")
    lot_db = loader.load("lot_db")
    non_rhino_utils = loader.load("non_rhino_utils")
    review_map = loader.load("review_map")
    non_rhino_utils.set_projection()   # 필지는 국내뿐 — 해외 대상지 원점을 되돌린다
    lot_data = lot_db.load(pnus, site_db)
    lots = lot_data.lots
    rings, warnings = context_builder.get_target_rings(lots)
    geojson = review_map.get_parcels_geojson(pnus, "lot", site_db)
    rows = []
    for lot, feature in zip(lots, geojson["features"]):
        parts = non_rhino_utils.get_polygon_parts_from_geojson(lot.geometry)
        warn = "multipart" if len(parts) > 1 else ("hole" if any(len(part) > 1 for part in parts) else None)
        feature["properties"]["jibun"] = lot.lot_number or _jibun(lot.address)
        gap = lot_db.get_area_gap(lot)
        rows.append({"pnu": lot.pnu, "address": lot.address, "jibun": feature["properties"]["jibun"],
                     "land_category": lot.land_category, "area": lot.area, "warn": warn,
                     "zones": [{"name": name, "limits": lot_db.get_legal_limits(name)} for name in lot_db.get_zone_names(lot)],
                     "designations": [{"name": item.name, "conflict": item.conflict} for item in lot_db.get_lot_designations(lot, lot_data.designations)],
                     "registered_area": lot.registered_area, "geometry_area": round(lot.geometry_area, 1),
                     "area_gap": None if gap is None else round(gap, 1),
                     "area_gap_flag": gap is not None and abs(gap) >= constants.AREA_GAP_FLAG_RATIO * lot.registered_area,
                     "reference_date": lot.reference_date})
    target_coords = [[review_map.get_wgs84_ring(ring + [ring[0]])] for ring in rings]   # 닫힘 중복점을 붙여 GeoJSON 링으로
    geojson["features"].append({"type": "Feature", "properties": {"role": "target"},
                                "geometry": {"type": "MultiPolygon", "coordinates": target_coords}})
    center = review_map.get_wgs84_ring([context_builder.get_lots_center(lots)])[0]
    return {
        "type": "lot_state", "lots": rows, "total_area": round(sum(row["area"] for row in rows), 1),
        "lot_name": context_builder.get_lot_name(lots), "center": center, "target_geojson": geojson, "warnings": warnings,
        "land_use_date": next((src.reference_date or "" for src in lot_data.sources if src.source_id == constants.LAND_USE_SOURCE_ID), ""),
    }


def _empty_area_state(text=""):
    # type: (str) -> dict
    return {"type": "area_state", "ok": not text, "text": text, "ring_tm": [], "ring_lnglat": [], "center": None, "center_tm": None,
            "offsets": [], "area": 0.0, "lots": 0, "lots_area": 0.0, "lot_name": "", "target_geojson": _EMPTY_FC, "warnings": []}


def get_area_state(msg, site_db=None):
    # type: (dict, str) -> dict
    """area_state 페이로드 — 구역 링 하나를 정리·검사하고 안의 필지를 센다.

    입력: msg 중 하나 — ring_tm [[x, y]] EPSG:5186 / ring_lnglat [[lng, lat]](지도에 그린 것) / center [lng, lat] + offsets [[dx, dy]] m
          (Rhino 커브를 지도에서 옮겨 놓은 것 — 모양은 m로 그대로, 위치만 지도에서). 아무것도 없으면 빈 상태(지움).
    처리: context_builder.resolve_target(area) — 안전장치(get_ring_problem)·안의 필지(50 % 규칙)·이름.
    출력: {"type": "area_state", ok, text, ring_tm, ring_lnglat(닫힘), center, center_tm, offsets, area, lots, lots_area, lot_name,
          target_geojson(role area 1 + role target 필지), warnings}. 링 문제는 ok=false + text(사용자용 한 줄).
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
        request = context_builder.get_request_with_defaults({"target": {"mode": "area", "ring": points}, "site_db": site_db,
                                                             "options": {"region": msg.get("region")}})   # Global이면 안의 필지를 세지 않는다
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
        "target_geojson": geojson, "warnings": target.warnings,
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
    request = context_builder.get_request_with_defaults({"target": {"mode": "point", "center": [x, y]}, "site_db": site_db,
                                                         "options": {"region": msg.get("region")}})
    target = context_builder.resolve_target(request)
    return {"type": "point_state", "ok": True, "center": [round(lng, 7), round(lat, 7)], "center_tm": [round(x, 2), round(y, 2)],
            "lot_name": target.name}


def get_area_packs(bbox, seq=None, manifest=None):
    # type: (list, int, dict) -> dict
    """area_packs 페이로드 — 지도 화면(경위도 bbox)에 걸치는데 아직 없는 시군구 필지 팩. 해외·매니페스트 없음은 빈 목록.
    지도에서 필지를 고르려면 필지 팩만 있으면 된다. 건물·도로·지형 팩은 생성할 때 그 범위만 받는다(_generate).

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
        data_dir = data_pack.get_data_dir()
        # 시군구 필지 팩 중 파일이 없는 것만 — 새 판은 생성할 때 범위 안에서 받는다. 옛 시도 팩은 대상이 아니다
        missing = [pack for pack in data_pack.get_missing_packs(manifest or data_pack.get_manifest(), bounds=bounds)
                   if pack["name"][:5].isdigit() and pack["name"].endswith("_site.db")
                   and not os.path.exists(os.path.join(data_dir, pack["name"]))]
    except Exception:   # 오프라인 — 지도는 그대로 쓴다
        return empty
    labels = list(dict.fromkeys(get_region_name(pack) for pack in missing))
    total = sum(pack.get("xz_size", 0) for pack in missing) / 1048576.0
    return {"type": "area_packs", "seq": seq, "missing": [{"name": p["name"], "label": p["label"], "mb": round(p.get("xz_size", 0) / 1048576.0, 1)}
                                                          for p in missing],
            "mb": round(total), "labels": labels}


def get_region_name(pack):
    # type: (dict) -> str
    """팩 표시 이름 '서울특별시 종로구 필지' → '종로구'(시도 이름과 끝의 종류를 뗀다). 시도 하나뿐이면 그 이름."""
    words = pack["label"].split()[:-1]
    return " ".join(words[1:]) or " ".join(words)


def get_target_from_msg(msg):
    # type: (dict) -> dict
    """generate·preflight 메시지 → 요청 target. 예전 메시지(pnus만)는 필지 방식."""
    return dict(msg.get("target") or {"mode": "lots", "pnus": [str(p) for p in (msg.get("pnus") or [])]})


def get_preflight_key(msg):
    # type: (dict) -> tuple
    """메모이즈 키 (target json, radius, shape, paper, tuple(paper_mm), tuple(scales), region) — paper_mm이 빠지면 용지 '직접'이 안 바뀐다."""
    return (json.dumps(get_target_from_msg(msg), sort_keys=True), msg.get("radius"), msg.get("shape"), msg.get("paper"),
            tuple(msg.get("paper_mm") or ()), tuple(msg.get("scales") or ()), msg.get("region"))


def get_preflight_result(msg, site_db=None, context_db=None, today=None):
    # type: (dict, str, str, datetime.date) -> dict
    """preflight_result 페이로드 — context_builder.preflight + type·seq 에코. 옵션은 prefs(include_minor_buildings 포함) 위에 메시지 값을 덮는다 —
    preflight 건물 수와 generate 실제 수가 같은 옵션으로 나온다(context_db.count_in_bounds)."""
    context_builder = loader.load("context_builder")
    site_prefs = loader.load("site_prefs")
    options = dict(site_prefs.get_options())
    options.update({key: msg[key] for key in ("radius", "shape", "paper", "paper_mm", "scales", "region") if msg.get(key) is not None})
    result = context_builder.preflight({"target": get_target_from_msg(msg), "options": options, "site_db": site_db, "context_db": context_db}, today)
    result.update(type="preflight_result", seq=msg.get("seq"))
    return result


def get_skipped_details(options):
    # type: (dict) -> tuple
    """generate 시작 때의 (skipped phase 집합, phase_detail 초기값) — 옵션으로 끈 phase는 '건너뜀 — 옵션'."""
    context_builder = loader.load("context_builder")
    skipped = context_builder.get_skipped_phases(context_builder.get_request_with_defaults({"options": options})["options"])
    return skipped, {phase: SKIPPED_DETAILS.get(phase, SKIPPED_OPTION_DETAIL) for phase in skipped}


def get_skipped_details_2d(options):
    # type: (dict) -> tuple
    """make_2d 시작 때의 (skipped, phase_detail) — 3D phase(terrain·write_3dm)는 이미 끝난 일이라 건너뛰고, 끈 2D phase도 건너뛴다."""
    skipped, details = get_skipped_details(options)
    for phase in ("terrain", "write_3dm"):
        skipped.add(phase)
        details[phase] = "3D는 이미 만듦"
    return skipped, details


def get_error_log_text(error):
    # type: (dict) -> str
    """실패 응답의 error → 로그 한 덩어리. 상세가 제목과 같거나 비면 한 줄만(같은 문장이 두 번 찍혔다)."""
    error = error or {}
    head = "%s: %s" % (error.get("code") or "exception", error.get("title") or "")
    detail, title = error.get("detail") or "", error.get("title") or ""
    if title and detail.startswith(title):   # 상세 첫 줄이 제목과 같으면 나머지만
        detail = detail[len(title):].lstrip("\n")
    return head + "\n" + detail if detail else head


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


def get_curve_shape(ring, problem, doc_origin):
    # type: (list, str, tuple) -> dict
    """curve_shape 페이로드 — 문서 커브 링(문서 좌표 m) → 실제 위치면 located + ring_tm, 아니면 모양만(offsets).

    입력: ring [(x, y)] m 또는 None(problem = 사용자용 이유), doc_origin = 문서 원점(이 도구가 만든 문서) 또는 None.
    처리: 문서 원점이 있으면 링 + 원점이 세계좌표, 없으면 링 중심이 서울 EPSG:5186 범위면 링 그대로, 아니면 위치 없음
          — 패널이 지도 가운데에 얹고 사용자가 지도를 움직여 놓는다.
    출력: {"type": "curve_shape", ok, text, located, ring_tm, offsets, area, vertices}.
    """
    if ring is None:
        return {"type": "curve_shape", "ok": False, "text": problem}
    constants = loader.load("constants")
    non_rhino_utils = loader.load("non_rhino_utils")
    min_x, min_y, max_x, max_y = non_rhino_utils.get_bbox(ring)
    cx, cy = (min_x + max_x) * 0.5, (min_y + max_y) * 0.5
    b = constants.SEOUL_TM_BOUNDS
    if doc_origin is not None:
        world = [(x + doc_origin[0], y + doc_origin[1]) for x, y in ring]
    elif b[0] <= cx <= b[2] and b[1] <= cy <= b[3]:
        world = ring
    else:
        world = None
    return {"type": "curve_shape", "ok": True, "text": "", "located": world is not None,
            "ring_tm": [list(p) for p in world] if world else [],
            "offsets": [[round(x - cx, 3), round(y - cy, 3)] for x, y in ring],
            "area": round(non_rhino_utils.get_ring_area(ring), 1), "vertices": len(ring)}


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
        self._session_id = str(int(time.time()))   # 사용 통계 세션 = 패널 하나
        self._opened = False
        self._keep = {}                # 마지막 결과의 시트 데이터(지형 삼각형 포함) — 도면 스타일 미리보기·적용이 다시 쓴다
        self._map_center = None        # 첫 init에 IP로 짐작한 지도 첫 위치 [lng, lat] — 못 받으면 None(서울시청)

    def _send_stats(self, name, params):
        # type: (str, dict) -> None
        """사용 통계 이벤트 하나(usage_stats). 통계 준비 중 어떤 예외도 패널 흐름을 막지 않는다."""
        try:
            loader.load("usage_stats").send_event(name, dict(params, session_id=self._session_id))
        except Exception:
            pass

    def handle(self, msg):
        # type: (dict) -> None
        """JS 명령 하나를 라우팅한다. 호스트가 UI 스레드에서 부른다."""
        msg = msg or {}
        cmd = msg.get("cmd", "")
        handlers = {
            "init": self._init, "search": self._search, "map_lots": self._map_lots, "select_lots": self._select_lots,
            "set_area": self._set_area, "set_point": self._set_point, "pick_curve": self._pick_curve,
            "preflight": self._preflight, "generate": self._generate, "make_2d": self._make_2d, "cancel": self._cancel,
            "import_context": self._import_context, "export_basemap": self._export_basemap, "zoom_view": self._zoom_view,
            "open_path": self._open_path, "open_eum": self._open_eum, "open_url": self._open_url, "save_prefs": self._save_prefs, "download_data": self._download_data,
            "style_preview": self._style_preview, "apply_style": self._apply_style, "save_style": self._save_style, "sheet_ai": self._sheet_ai,
            "sheet_view": self._sheet_view, "area_packs": self._area_packs, "stats_consent": self._stats_consent,
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
            # 운영체제 파일 오류는 args[0]이 번호(2)라 str 전체로(2026-10-14: 설치본을 바꿔 깐 뒤 '2'만 떴다)
            text = str(error) if isinstance(error, OSError) else (str(error.args[0]) if error.args else str(error))
            self.push({"type": "error", "context": context, "text": text, "detail": ""})
        except Exception:
            self.push({"type": "error", "context": context, "text": "예상 밖 오류", "detail": traceback.format_exc()})
            self._send_stats("error", {"context": context, "error": type(sys.exc_info()[1]).__name__})

    # ── 호스트 연결 (Rhino) — cmd_blender가 같은 이름으로 바꿔 단다 ──

    def _get_doc(self):
        return Rhino.RhinoDoc.ActiveDoc

    def _pump(self):
        """긴 작업 중 UI 이벤트를 돌린다 — WebView 이벤트·cancel 명령이 여기서 처리된다."""
        Rhino.RhinoApp.Wait()

    def _defer(self, work):
        """작업을 UI 스레드 큐로 미룬다 — 먼저 보낸 busy가 그려진 뒤 돈다."""
        forms.Application.Instance.AsyncInvoke(System.Action(work))

    def _redraw(self, doc):
        doc.Views.Redraw()

    def _get_host_stats(self):
        # type: () -> dict
        """panel_open 통계의 호스트 버전 키."""
        return {"rhino": str(Rhino.RhinoApp.Version)}

    def _open(self, path):
        """파일·폴더·URL을 OS로 연다(웹판은 내려받기·새 탭)."""
        _open_with_os(path)

    def on_close(self):
        # type: () -> None
        """창 닫힘 — 생성 중이면 cancel과 같은 경로."""
        if self._running:
            self._cancel_requested = True

    # ── 명령 처리 ──

    def _init(self, msg):
        self._preflight_memo.clear()   # 키 유무·새 판은 메모 키에 없으므로 init마다 비운다
        try:   # 공지·업데이트 — 처음 한 번만 짧게 기다린다. 오프라인·서버 장애면 공지 없이 연다(사용자를 막지 않는다)
            loader.load("data_pack").get_manifest(timeout=loader.load("constants").NOTICE_TIMEOUT_SECONDS)
        except Exception:
            pass
        if not self._opened:   # 지도는 첫 init_state로만 만든다(JS initMap)
            self._map_center = loader.load("review_map").get_ip_center()
        state = get_init_state(map_center=self._map_center)
        self.push(state)
        if not self._opened:   # init은 배지 [다시 확인]에도 온다 — 패널 열기는 한 번만
            self._opened = True
            self._send_stats("panel_open", dict(self._get_host_stats(), version=state["version"], has_lot_db=not state["blocked"],
                                                packs=len(loader.load("data_pack").get_local_paths("site"))))

    def _search(self, msg):
        query = (msg.get("query") or "").strip()
        if not query:
            raise ValueError("주소 또는 PNU를 입력하세요")
        self.push(get_search_result(query, region=msg.get("region")))

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
        self.push(get_curve_shape(ring, problem, context_baker.get_doc_origin(doc)))

    def _preflight(self, msg):
        key = get_preflight_key(msg)
        result = self._preflight_memo.get(key)
        if result is None:
            result = self._preflight_memo[key] = get_preflight_result(msg)
        self.push(dict(result, seq=msg.get("seq")))

    def _progress(self, phase, fraction, text):
        # type: (str, float, str) -> bool
        """엔진 콜백 — push → _pump(WebView 이벤트·cancel 명령 펌핑) → 취소 플래그."""
        self._last_phase = phase
        self.push(self._context_builder.get_progress_message(phase, fraction, text, self._skipped, self._phase_detail))
        self._pump()
        return not self._cancel_requested

    def _generate(self, msg):
        """context_builder.run을 UI 스레드에서 동기 호출. 끝나면 done, 실패·취소면 progress{failed|cancelled}."""
        if self._running:
            self.push({"type": "error", "context": "generate", "text": "이미 생성 중입니다", "detail": ""})
            return
        context_builder = loader.load("context_builder")
        context_baker = context_builder.get_host_modules()[1]
        site_prefs = loader.load("site_prefs")
        lot_db = loader.load("lot_db")
        request = {"target": get_target_from_msg(msg), "options": dict(msg.get("options") or {})}
        self._context_builder = context_builder
        self._skipped, self._phase_detail = get_skipped_details(request["options"])
        self._last_phase = "query"
        self._running, self._cancel_requested = True, False
        doc = self._get_doc()
        try:
            self._download_for_generate(request)
            response = context_builder.run(request, self._progress, doc, self._keep)
        finally:
            self._running = False
        self._redraw(doc)
        target = request["target"]
        if not response["ok"]:
            self._send_build_stats(target, [], response)   # 실패는 필지 DB 자체가 원인일 수 있어 다시 읽지 않는다(PNU만)
            self.push({"type": "log", "level": "error", "text": get_error_log_text(response["error"])})
            self.push(get_failed_progress(response, self._last_phase, self._skipped, self._phase_detail))
            return
        self.push(self._context_builder.get_progress_message(self._last_phase, 1.0, "", self._skipped, self._phase_detail, state="done"))
        self.push(get_done_message(response))
        lots = lot_db.load(target["pnus"]).lots if target["mode"] == "lots" else []
        self._send_build_stats(target, lots, response)
        if lots:   # 최근 대상지는 필지 방식만(구역·위치는 다시 그리는 편이 빠르다)
            site_prefs.add_recent(target["pnus"], response["lot_name"].replace("_", " "), sum(lot.area for lot in lots), datetime.date.today().isoformat())
        if response["options"].get("zoom_after_import"):
            context_baker.zoom_to_site(doc, response["dir"])
        self.push(get_init_state())   # 생성 중 받은 지역 데이터로 헤더 배지 갱신

    def _make_2d(self, msg):
        """3D 결과 폴더에 2D 자료(베이스맵 .ai·도면·조서 CSV)를 더한다 — context_builder.make_2d를 UI 스레드에서 동기 호출.
        생성 전에 2D 범위(가장 큰 프레임)의 팩을 받는다. 진행은 progress, 끝(성공·실패·취소)은 made_2d 하나. 문서는 건드리지 않는다."""
        if self._running:
            self.push({"type": "error", "context": "generate", "text": "이미 만드는 중입니다", "detail": ""})
            return
        result_dir = self._get_result_dir(msg)
        context_builder = loader.load("context_builder")
        options = dict(msg.get("options") or {})
        self._context_builder = context_builder
        self._skipped, self._phase_detail = get_skipped_details_2d(options)
        self._last_phase = "query"
        self._running, self._cancel_requested = True, False
        try:
            self._download_for_generate(context_builder.get_2d_request(result_dir, options))
            response = context_builder.make_2d(result_dir, options, self._progress, self._keep)
        finally:
            self._running = False
        if response["error"] and not response["cancelled"]:
            self.push({"type": "log", "level": "error", "text": get_error_log_text(response["error"])})
        self.push(dict(response, type="made_2d"))

    def _send_build_stats(self, target, lots, response):
        # type: (dict, list, dict) -> None
        """생성 한 번 → build 이벤트(대상지 위치·규모, 범위 옵션, 결과·소요 시간)."""
        try:
            params = loader.load("usage_stats").get_target_params(target, lots)
        except Exception:
            params = {"mode": target.get("mode")}
        options = response.get("options") or {}
        params.update(result="ok" if response["ok"] else ("cancelled" if response.get("cancelled") else "failed"),
                      error=(response.get("error") or {}).get("code"), elapsed_s=response.get("elapsed_s"),
                      radius=options.get("radius"), shape=options.get("shape"), placement=options.get("placement"),
                      buildings=response["context"].get("buildings"))
        self._send_stats("build", params)

    def _area_packs(self, msg):
        self.push(get_area_packs(msg.get("bbox") or [], msg.get("seq")))

    def _cancel(self, msg):
        if self._running:
            self._cancel_requested = True   # 다음 콜백이 False를 돌려준다

    def _download_packs(self, packs, in_generate=False):
        # type: (list, bool) -> bool
        """팩을 차례로 받으며 data_progress{text, fraction}를 푸시한다(1 % 단위 — 조각마다 보내면 수천 번이다).
        끝에 data_progress{done, ok, text}. 다 받았으면 True, 멈추거나 실패하면 False(받은 팩은 남는다). 호출자가 _running을 관리한다."""
        data_pack = loader.load("data_pack")
        names = list(dict.fromkeys(get_region_name(pack) for pack in packs))
        region = names[0] + (" 외 %d곳" % (len(names) - 1) if len(names) > 1 else "")
        total_bytes = float(sum(pack.get("xz_size", 0) for pack in packs)) or 1.0
        client_id = loader.load("usage_stats").get_client_id()
        done, ok, offset, reason = [], True, 0.0, ""
        for pack in packs:
            last = [-1]

            def progress(read, total, pack=pack, offset=offset, last=last):
                # read·total은 압축 전 바이트 — 팩 크기 비율로 전체 진행률에 옮긴다
                fraction = (offset + pack.get("xz_size", 0) * read / max(total, 1)) / total_bytes
                if int(fraction * 100) != last[0]:
                    last[0] = int(fraction * 100)
                    self.push({"type": "data_progress", "text": "%s 지역 데이터 받는 중 %d%%" % (region, last[0]),
                               "fraction": round(fraction, 3), "in_generate": in_generate})
                self._pump()
                return not self._cancel_requested

            try:
                if not data_pack.download_pack(pack, progress=progress, client_id=client_id):
                    ok = False
                    break
            except Exception as exc:   # 오프라인·서버 오류 — 받은 데까지 쓴다
                self.push({"type": "log", "level": "warn", "text": "지역 데이터 받기 실패 %s: %s" % (pack["name"], exc)})
                ok, reason = False, str(exc) if isinstance(exc, ValueError) else ""   # 하루 한도·sha256 불일치는 그 문장을 그대로
                break
            done.append(pack["name"])
            offset += pack.get("xz_size", 0)
        text = "" if ok else ("받기를 멈췄습니다. 받은 지역은 남습니다" if self._cancel_requested
                              else reason or "지역 데이터를 다 받지 못했습니다. 인터넷 연결을 확인하세요")
        self.push({"type": "data_progress", "done": True, "ok": ok, "text": text, "in_generate": in_generate})
        self._send_stats("pack_download", {"packs": ",".join(dict.fromkeys(name.split("_")[0] for name in done)), "count": len(done),
                                           "requested": len(packs), "in_generate": in_generate})
        return ok

    def _download_data(self, msg):
        """지도에서 고른 시군구 팩(names, 없으면 바뀐 팩 전부)을 받는다. 끝나면 init_state."""
        if self._running:
            raise ValueError("다른 작업이 진행 중입니다")
        data_pack = loader.load("data_pack")
        packs = data_pack.get_missing_packs(data_pack.get_manifest())
        if msg.get("names"):
            packs = [pack for pack in packs if pack["name"] in set(msg["names"])]
        self._running, self._cancel_requested = True, False
        try:
            if packs:
                self._download_packs(packs)
        finally:
            self._running = False
        self.push(get_init_state())

    def _download_for_generate(self, request):
        # type: (dict) -> None
        """생성 범위에 걸치는데 없거나 새 판이 나온 시군구 팩(필지·건물도로·지형)을 받는다. 오프라인이면 있는 것으로 생성한다.
        여기서 멈추기를 누르면 _cancel_requested가 남아 이어지는 run이 곧바로 취소된다."""
        constants = loader.load("constants")
        if not constants.DATA_MANIFEST_URL:
            return
        data_pack = loader.load("data_pack")
        try:
            bounds = self._context_builder.get_query_bounds(request)
            packs = [pack for pack in data_pack.get_missing_packs(data_pack.get_manifest(), bounds=bounds)
                     if pack["name"][:5].isdigit()] if bounds else []
        except Exception:   # 대상지 오류는 run이 알린다, 오프라인은 있는 것으로
            return
        if packs:
            self._download_packs(packs, in_generate=True)

    def _run_busy(self, label, context, work):
        # type: (str, str, object) -> None
        """busy{on} 푸시 → _defer로 작업 예약(busy가 먼저 그려진다) → 작업 → busy{off}. Import·Export처럼 UI 스레드가 멈추는 짧은 작업용."""
        self.push({"type": "busy", "on": True, "label": label})

        def run_work():
            try:
                self._guard(context, work)
            finally:
                self.push({"type": "busy", "on": False, "label": ""})

        self._defer(run_work)

    def _import_context(self, msg):
        result_dir = str(msg.get("dir") or "")
        if not os.path.isdir(result_dir):
            raise ValueError("결과 폴더가 없습니다: %s" % result_dir)
        context_baker = loader.load("context_baker")
        site_prefs = loader.load("site_prefs")

        def work():
            doc = self._get_doc()
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
        context_baker = loader.load("context_builder").get_host_modules()[1]
        if not context_baker.zoom_to_site(self._get_doc(), str(msg.get("dir") or ""), msg.get("center")):
            raise ValueError("대상지 3D가 문서에 없습니다. 먼저 Rhino에 불러오세요")

    def _open_path(self, msg):
        self._open(resolve_open_path(msg.get("path")))

    def _open_eum(self, msg):
        # 임의 URL은 받지 않는다 — PNU만 받아 토지이음 주소를 여기서 만든다
        constants = loader.load("constants")
        pnu = str(msg.get("pnu") or "")
        if not (len(pnu) == constants.PNU_LENGTH and pnu.isdigit()):
            raise ValueError("PNU 형식이 아닙니다: %s" % pnu)
        self._open(constants.EUM_LAND_USE_URL % pnu)

    def _open_url(self, msg):
        # 임의 URL은 받지 않는다 — 키(constants.PANEL_LINKS)나 공지 id(매니페스트 notices)만 받아 정해진 주소를 연다
        if msg.get("notice"):
            self._open(loader.load("data_pack").get_notice_url(str(msg["notice"])))
            return
        url = loader.load("constants").PANEL_LINKS.get(str(msg.get("key") or ""))
        if not url:
            raise ValueError("알 수 없는 링크입니다: %s" % msg.get("key"))
        self._open(url)

    def _stats_consent(self, msg):
        loader.load("site_prefs").save_stats_consent(bool(msg.get("on")))

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
        sheets_dir = loader.load("context_builder").get_sheets_dir(result_dir)
        paths = sorted(os.path.join(sheets_dir, n) for n in os.listdir(sheets_dir) if n.endswith(".svg")) if msg.get("all") else [str(msg.get("path") or "")]
        if not all(p.startswith(sheets_dir) and os.path.exists(p) for p in paths):
            raise ValueError("도면 파일이 없습니다")

        def work():
            written = [sheet_svg.get_sheet_ai(p) for p in paths]
            self.push({"type": "sheet_ai", "ok": True, "dir": result_dir, "paths": written})
            if not msg.get("all"):
                self._open(written[0])

        self._run_busy("레이어 .ai 쓰는 중", "style", work)

    def _sheet_view(self, msg):
        """도면 SVG 한 장의 내용을 패널 보기 창으로 — OS로 열면 .svg가 Illustrator에 묶인 PC가 많다(2026-10-19 Rhino QA)."""
        sheets_dir = loader.load("context_builder").get_sheets_dir(self._get_result_dir(msg))
        path = str(msg.get("path") or "")
        if not (os.path.abspath(path).startswith(os.path.join(os.path.abspath(sheets_dir), "")) and path.endswith(".svg") and os.path.exists(path)):
            raise ValueError("도면 파일이 없습니다")
        with open(path, encoding="utf-8") as handle:
            self.push({"type": "sheet_view", "path": path, "svg": handle.read()})

    def _save_style(self, msg):
        styles = loader.load("site_prefs").save_style(msg.get("name"), msg.get("style") or {})
        self.push({"type": "styles", "styles": styles, "saved": msg.get("name"), "dir": loader.load("site_prefs").get_styles_dir()})


# error.context — JS가 표시 자리를 고른다(panel_ui.md 오류 규약)
_ERROR_CONTEXTS = {"select_lots": "select", "map_lots": "select", "set_area": "select", "set_point": "select", "pick_curve": "select",
                   "import_context": "import", "export_basemap": "export",
                   "zoom_view": "open", "open_path": "open", "open_eum": "open", "open_url": "open", "save_prefs": "init", "stats_consent": "init", "cancel": "generate", "make_2d": "generate", "download_data": "init",
                   "style_preview": "style", "apply_style": "style", "save_style": "style", "sheet_ai": "style", "sheet_view": "view"}


def _show_panel():
    """패널을 하나만 띄운다. 이미 떠 있으면 앞으로 가져온다."""
    existing = scriptcontext.sticky.get(PANEL_STICKY_KEY)
    if existing is not None:
        try:
            existing.bring_to_front()
            print("[Gorani] 이미 열린 패널을 앞으로 가져왔습니다")
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
