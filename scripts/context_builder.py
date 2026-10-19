"""컨텍스트 생성 엔진 API — 패널이 아는 유일한 함수들 (docs/code_map.md §4).

    resolve_target(request)           Rhino 금지. 대상지 방식(lots·area·point) → 경계 링·안의 필지·중심·이름·키.
    prepare(request, progress)        Rhino 금지. 입력 검증 → 필지·컨텍스트 질의 → 원점·범위 → 통계·경고·메타.
    run(request, progress, doc)       Rhino·Blender 안. prepare → (호스트) 지오메트리.build → 베이커.bake/.. → 시트·조서.
    get_host_modules()                (지오메트리, 베이커) — Rhino는 context_*, Blender·SketchUp은 mesh_geometry + 호스트 베이커. 같은 함수 이름을 쓴다.
    preflight(request)                Rhino 금지, 100 ms급. COUNT 질의만으로 사전 점검(panel_ui.md preflight_result).
    get_sources / get_source_warnings 원천 상태 4건·stale_* 경고 — 패널 init_state도 쓴다.
    get_progress_message(...)         순수 함수. progress 페이로드 조립. skipped 집합은 get_skipped_phases(options).

이 파일은 Rhino·bpy를 모듈 수준에서 import하지 않는다. run()만 함수 안에서 호스트 모듈을 불러온다.
요청·응답 dict 모양은 docs/code_map.md §4.2·§4.3, 패널 메시지는 docs/panel_ui.md.
좌표는 전부 EPSG:5186 세계좌표 m — 원점은 여기서 정하기만 하고 적용은 context_geometry.get_local_pts가 한다.
"""

import datetime
import hashlib
import math
import json
import os
import re
import shutil
import statistics
import time
import traceback
import types
from dataclasses import dataclass, field
from pathlib import Path

import basemap_ai
import constants
import context_db
import data_pack
import context_report
import lot_db
import non_rhino_utils
import osm_context
import pnu_loader
import site_prefs
import sheet_svg
from sheet_svg import Frame



class Cancelled(Exception):
    """progress 콜백이 False를 돌려줘 생성을 중단했다."""


class DomainError(ValueError):
    """생성 중단 조건(code_map §4.5) — code를 싣고 올린다. run._get_error가 getattr(exc, "code")로 읽는다.
    code ∈ no_lots|site_db_missing|context_db_missing|no_terrain_points|doc_unit_invalid|origin_mismatch|placement_mismatch|area_invalid. context_geometry·context_baker도 이 클래스를 올린다."""

    def __init__(self, code, text):
        # type: (str, str) -> None
        super().__init__(text)
        self.code = code


@dataclass
class Prepared:
    """prepare()의 결과. 좌표는 전부 EPSG:5186 세계좌표 m — 원점은 아직 빼지 않았다.

    request: 기본값을 채운 요청 사본(options·target 포함). lot_name: 결과 폴더명. origin: (E, N) 계산 원점(형상의 로컬 기준, 100 m 내림 또는 문서 원점 재사용).
    doc_origin: 문서에 기록할 원점 — origin 방식이면 origin, world 방식이면 (0, 0)(베이커가 origin − doc_origin만큼 옮긴다).
    extent_ring: 범위 링 [(x, y)] (non_rhino_utils.get_extent_ring). bounds: (min_x, min_y, max_x, max_y) — 범위 bbox ∪ 최대 프레임 bbox.
    frame_bounds: {축척: (min_x, min_y, max_x, max_y)}. target_lots·near_lots: lot_db.LotInfo. context: context_db.ContextData.
    align_samples: features theme 'qa'. meta: 기준일·경과·레벨·meta_lines. stats: 높이 출처 비율 등. warnings: panel_ui.md 경고 dict 목록.
    """

    request: dict
    lot_name: str
    target_lots: list
    near_lots: list
    origin: tuple
    origin_reused: bool
    radius: float
    shape: str
    extent_ring: list
    scales: list
    bounds: tuple
    frame_bounds: dict
    context: object
    align_samples: list = field(default_factory=list)
    overlays: list = field(default_factory=list)
    designations: list = field(default_factory=list)   # 대상 필지의 지역지구등(lot_db.DesignationInfo) — parcels.csv
    sources: list = field(default_factory=list)
    meta: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    skipped_phases: set = field(default_factory=set)
    result_dir: str = ""
    lots_truncated: bool = False
    mode: str = "lots"              # 대상지 방식 lots|area|point
    site_rings: list = field(default_factory=list)   # 대상지 경계 링(lots = 필지 외곽들, area = 구역 링 1개, point = 없음)
    center: tuple = None            # 대상지 중심(세계좌표) — 프레임·원점의 기준
    target_key: str = ""            # UDT_LOT_KEY 값(resolve_target)
    placement: str = "origin"       # origin = 로컬(원점 이동), world = EPSG:5186 그대로
    doc_origin: tuple = None        # 문서 원점(세계 = 문서 좌표 + doc_origin). world면 (0, 0)

    @property
    def buildings(self):
        return self.context.buildings if self.context is not None else []

    @property
    def features(self):
        return self.context.features if self.context is not None else []


def get_request_with_defaults(request):
    # type: (dict) -> dict
    """요청 dict의 options에 constants.PANEL_DEFAULT_OPTIONS 기본값을 채운 사본. 모르는 키는 그대로 둔다."""
    request = dict(request or {})
    options = dict(constants.PANEL_DEFAULT_OPTIONS)
    options.update(request.get("options") or {})
    request["options"] = options
    request.setdefault("lot_name", None)
    request.setdefault("result_root", None)
    request.setdefault("site_db", None)
    request.setdefault("context_db", None)
    request.setdefault("doc_origin", None)
    target = dict(request.get("target") or {"mode": "lots", "pnus": list(request.get("pnus") or [])})
    if target.get("mode") not in constants.TARGET_MODES:
        raise ValueError("알 수 없는 대상지 방식: %s" % target.get("mode"))
    request["target"] = target
    if options.get("placement") not in constants.PLACEMENTS:
        raise ValueError("알 수 없는 결과 좌표 방식: %s" % options.get("placement"))
    return request


# ── 작은 헬퍼 ──────────────────────────────────────────────

def is_global(request):
    # type: (dict) -> bool
    """OSM·지형 타일로 만들지 — Global 모드이거나 대상지가 한국 밖(지역 TM 원점)이면. Korea 모드는 국가 DB만 쓴다.
    좌표계는 모드와 무관하게 위치로 정한다(한국 = EPSG:5186, 해외 = 지역 TM) — 한국에서 Global이어도 EPSG:5186."""
    return (request.get("options") or {}).get("region") == "global" or non_rhino_utils.is_local_projection()


def get_skipped_phases(options):
    # type: (dict) -> set
    """콜백이 오지 않는 phase 집합 — v1 refresh·import(항상) + 옵션으로 끈 basemap·sheets·tables. 컨트롤러가 get_progress_message(skipped=)에 그대로 준다."""
    options = options or {}
    return {"refresh", "import"} | {phase for phase, key in (("basemap", "make_basemap"), ("sheets", "make_sheets"), ("tables", "make_tables"))
                                    if not options.get(key)}


def has_2d(options):
    # type: (dict) -> bool
    """용지 프레임이 필요한 2D 산출물(베이스맵 .ai·도면·DWG)을 만드는가. 아니면(3D만) DB 조회 범위가 범위 bbox로 줄고
    3dm에 2D 선 도면(BM::)을 굽지 않는다 — 1:5000 A3 프레임(2.1×1.5 km)만큼 받고 읽지 않도록(2026-10-19 3D 먼저)."""
    options = options or {}
    return bool(options.get("make_basemap") or options.get("make_sheets") or options.get("make_dwg"))


def _warning(level, code, text, detail="", action=None, center=None):
    # type: (str, str, str, str, dict, list) -> dict
    """panel_ui.md 공통 경고 스키마 한 건."""
    return {"level": level, "code": code, "text": text, "detail": detail, "action": action, "center": center}


def _report(progress, phase, fraction, text):
    # type: (object, str, float, str) -> None
    """progress 콜백 호출. False를 돌려주면 Cancelled."""
    if progress is not None and progress(phase, fraction, text) is False:
        raise Cancelled("cancelled at %s" % phase)


def _lnglat(x, y):
    # type: (float, float) -> list
    return [round(v, 7) for v in non_rhino_utils.get_wgs84_from_tm(x, y)]


def _get_direction(dx, dy):
    # type: (float, float) -> str
    """벡터 → 8방위 한글(동·북동·…)."""
    angle = math.degrees(math.atan2(dy, dx)) % 360
    return constants.COMPASS_DIRECTIONS[int((angle + 22.5) // 45) % 8]


def _get_months_since(date_text, today):
    # type: (str, datetime.date) -> float
    """'2026-05-13'·'202605'·'2026' 같은 문자열 → 오늘까지 경과 개월(소수 1자리). 해석 불가면 None."""
    digits = "".join(ch for ch in (date_text or "") if ch.isdigit())[:8]
    if len(digits) < 6:
        return None
    try:
        date = datetime.date(int(digits[:4]), int(digits[4:6]), int(digits[6:8]) if len(digits) >= 8 else 1)
    except ValueError:
        return None
    return round((today - date).days / 30.4, 1)


def _get_level(age, thresholds, newer_date):
    # type: (float, tuple, str) -> str
    """data_sources §2.4 — danger = 빨강 임계 이상, warn = 노랑 임계 이상 AND 새 판 있음, 그 외 ok."""
    if age is None:
        return "ok"
    yellow, red = thresholds
    if age >= red:
        return "danger"
    if age >= yellow and newer_date:
        return "warn"
    return "ok"


def get_lot_name(lots):
    # type: (list) -> str
    """결과 폴더명 '성수동2가_333-139'(합필이면 '…외1'). 주소 끝에서 두 번째 토큰이 동이다."""
    first = lots[0]
    parts = (first.address or "").split()
    dong = parts[-2] if len(parts) >= 2 else ""
    name = "%s_%s" % (dong, first.lot_number or first.pnu) if dong else (first.lot_number or first.pnu)
    return name + ("외%d" % (len(lots) - 1) if len(lots) > 1 else "")


def get_target_rings(lots):
    # type: (list) -> tuple
    """대상 필지 → 외곽 링 목록 + multipart 경고. 조각이 여럿이면 가장 넓은 조각, 구멍은 버린다(CLAUDE.md '필지 하나는 닫힌 커브 하나').

    실측: 성수동1가 13-219(1120011400100130219)는 구멍 3개 — 도로 필지라 구멍을 버려도 대상지로는 무방하다.
    """
    rings, warnings = [], []
    for lot in lots:
        parts = non_rhino_utils.get_polygon_parts_from_geojson(lot.geometry)
        outer = max((part[0] for part in parts), key=non_rhino_utils.get_ring_area)
        holes = sum(len(part) - 1 for part in parts)
        if len(parts) > 1 or holes:
            what = " · ".join(s for s in (("조각 %d개" % len(parts)) if len(parts) > 1 else "", ("구멍 %d개" % holes) if holes else "") if s)
            warnings.append(_warning("warn", "multipart", "%s 필지 %s — 가장 넓은 조각 외곽선만 씁니다" % (lot.lot_number or lot.pnu, what),
                                     "대상 필지는 닫힌 커브 하나여야 합니다. 조각·구멍은 CTX::Site에서 빠지고 면적은 대장값을 그대로 씁니다.",
                                     center=_lnglat((lot.min_x + lot.max_x) * 0.5, (lot.min_y + lot.max_y) * 0.5)))
        rings.append([(float(p[0]), float(p[1])) for p in outer])
    return rings, warnings


def get_lots_center(lots):
    # type: (list) -> tuple
    """대상지(합필이면 합집합 bbox) 중심."""
    return ((min(l.min_x for l in lots) + max(l.max_x for l in lots)) * 0.5,
            (min(l.min_y for l in lots) + max(l.max_y for l in lots)) * 0.5)


def _get_origin(center, doc_origin):
    # type: (tuple, object) -> tuple
    """원점 결정(code_map §6). doc_origin이 있으면 재사용(20 km 초과면 DomainError origin_mismatch), 없으면 중심을 ORIGIN_SNAP 단위로 내림."""
    if doc_origin:
        origin = (float(doc_origin[0]), float(doc_origin[1]))
        if math.hypot(center[0] - origin[0], center[1] - origin[1]) > constants.ORIGIN_MAX_OFFSET:
            raise DomainError("origin_mismatch", "다른 지역 문서입니다 — 새 문서에서 생성하세요 (문서 원점과 대상지 중심 거리 %.0f m > %.0f m)"
                              % (math.hypot(center[0] - origin[0], center[1] - origin[1]), constants.ORIGIN_MAX_OFFSET))
        return origin, True
    snap = constants.ORIGIN_SNAP
    return (math.floor(center[0] / snap) * snap, math.floor(center[1] / snap) * snap), False


def _get_origins(center, doc_origin, placement):
    # type: (tuple, object, str) -> tuple
    """(계산 원점, 재사용 여부, 문서 원점). 문서 원점 (0, 0) = 실제 좌표 문서 — 방식이 다르면 DomainError(placement_mismatch).
    world는 형상을 대상지 근처 로컬로 만들고(단정밀도 메시 오차 방지) 베이커가 계산 원점만큼 옮긴다."""
    world_doc = doc_origin is not None and abs(float(doc_origin[0])) < 1e-6 and abs(float(doc_origin[1])) < 1e-6
    if doc_origin is not None and world_doc != (placement == "world"):
        doc_text, want_text = ("실제 좌표", "원점 이동") if world_doc else ("원점 이동", "실제 좌표")
        raise DomainError("placement_mismatch", "이 문서는 '%s' 방식으로 생성된 문서입니다 — '%s'로 바꾸거나 새 문서에서 생성하세요"
                          % (doc_text, want_text))
    if placement == "world":
        origin, _reused = _get_origin(center, None)
        return origin, False, (0.0, 0.0)
    origin, reused = _get_origin(center, doc_origin)
    return origin, reused, origin


# ── 대상지 방식 ────────────────────────────────────────────

@dataclass
class Target:
    """resolve_target 결과. 좌표는 세계좌표 m.

    mode lots|area|point. spec: 정규화한 요청 target(context.json·.ai 다시 쓰기가 그대로 재현한다). key: UDT_LOT_KEY.
    site_rings: 대상지 경계 링 목록. lots: 대상 필지(area = 구역 안 필지, point = 없음). lot_data: lot_db.LotData(필지가 있을 때).
    """

    mode: str
    spec: dict
    key: str
    name: str
    center: tuple
    site_rings: list
    lots: list
    lot_data: object = None
    warnings: list = field(default_factory=list)


def get_target_key(spec):
    # type: (dict) -> str
    """대상지 → sha1 앞 8자리(UDT_LOT_KEY). lots는 PNU 정렬 문자열이라 이전 결과(context_baker.get_lot_key)와 같은 값."""
    mode = spec.get("mode") or "lots"
    if mode == "lots":
        text = ",".join(sorted(str(p) for p in spec.get("pnus") or []))
    elif mode == "area":
        text = "area:" + ";".join("%.2f,%.2f" % (float(x), float(y)) for x, y in spec.get("ring") or [])
    else:
        text = "point:%.1f,%.1f" % tuple(float(v) for v in spec.get("center") or (0, 0))
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:8]


def get_area_ring(points):
    # type: (list) -> list
    """요청의 구역 링 → 정리한 링(get_clean_ring). 안전장치(get_ring_problem)에 걸리면 DomainError(area_invalid)."""
    ring = non_rhino_utils.get_clean_ring(points or [])
    problem = non_rhino_utils.get_ring_problem(ring)
    if problem:
        raise DomainError("area_invalid", problem)
    return ring


def get_area_lot_fractions(ring, site_db=None):
    # type: (list, str) -> list
    """구역 링과 겹치는 필지와 안쪽 비율 [(LotInfo, 0~1)] — 비율 0은 뺀다. bbox 질의 → get_inside_fraction."""
    bbox = non_rhino_utils.get_bbox(ring)
    try:
        candidates, _truncated = lot_db.load_parcels_in_bounds(*bbox, limit=None, database_path=site_db)
    except FileNotFoundError as exc:
        raise DomainError("site_db_missing", str(exc))
    result = []
    for lot in candidates:
        fraction = non_rhino_utils.get_inside_fraction(non_rhino_utils.get_polygon_parts_from_geojson(lot.geometry), ring, bbox)
        if fraction > 0.0:
            result.append((lot, fraction))
    return result


def get_area_lots(ring, site_db=None):
    # type: (list, str) -> list
    """구역 링 안 필지 — 필지 면적의 AREA_LOT_MIN_FRACTION 이상이 구역 안."""
    return [lot for lot, fraction in get_area_lot_fractions(ring, site_db) if fraction >= constants.AREA_LOT_MIN_FRACTION]


def get_snap_rings(ring, site_db=None):
    # type: (list, str) -> tuple
    """'필지 경계에 맞추기' 입력 — (더할 필지 외곽들, 뺄 필지 외곽들). 선형 지목(AREA_SNAP_LINEAR_CATEGORIES)은 둘 다 아니다
    (구역계가 도로·하천은 그린 선대로 가로지른다). 더할 = 50 % 이상 안, 뺄 = 걸쳤지만 50 % 미만."""
    add, cut = [], []
    for lot, fraction in get_area_lot_fractions(ring, site_db):
        if lot.land_category in constants.AREA_SNAP_LINEAR_CATEGORIES:
            continue
        outer = max((part[0] for part in non_rhino_utils.get_polygon_parts_from_geojson(lot.geometry) if part), key=non_rhino_utils.get_ring_area)
        (add if fraction >= constants.AREA_LOT_MIN_FRACTION else cut).append([(float(p[0]), float(p[1])) for p in outer])
    return add, cut


def get_place_name(center, site_db=None):
    # type: (tuple, str) -> tuple
    """중심점의 필지(없으면 가장 가까운 필지) → (동, 지번). 필지가 없으면 ('', '')."""
    x, y = center
    span = 60.0
    try:
        lots, _truncated = lot_db.load_parcels_in_bounds(x - span, y - span, x + span, y + span, limit=200, database_path=site_db)
    except FileNotFoundError:
        return "", ""
    if not lots:
        return "", ""
    inside = [lot for lot in lots if any(non_rhino_utils.is_point_in_polygon(x, y, part)
                                         for part in non_rhino_utils.get_polygon_parts_from_geojson(lot.geometry))]
    lot = inside[0] if inside else min(lots, key=lambda l: math.hypot((l.min_x + l.max_x) * 0.5 - x, (l.min_y + l.max_y) * 0.5 - y))
    parts = (lot.address or "").split()
    return (parts[-2] if len(parts) >= 2 else ""), (lot.lot_number or "")


def _get_place_label(center, suffix, site_db):
    # type: (tuple, str, str) -> str
    """'성수동2가_333-139_구역' — 결과 폴더명. 필지가 없으면 'E198100_N552000_<suffix>', 해외면 'N37.7929_W122.4194_<suffix>'."""
    if non_rhino_utils.is_local_projection():
        lng, lat = non_rhino_utils.get_wgs84_from_tm(*center)
        return "%s%.4f_%s%.4f_%s" % ("N" if lat >= 0 else "S", abs(lat), "E" if lng >= 0 else "W", abs(lng), suffix)
    dong, jibun = get_place_name(center, site_db)
    if not dong and not jibun:
        return "E%.0f_N%.0f_%s" % (center[0], center[1], suffix)
    return "_".join(v for v in (dong, jibun, suffix) if v)


def resolve_target(request, with_lots=True):
    # type: (dict, bool) -> Target
    """요청 target → Target. Rhino 금지.

    입력: get_request_with_defaults를 거친 요청(target{mode, pnus | ring | center}, site_db). with_lots=False면 area의 필지 판정과
          이름 짓기를 건너뛴다(preflight — 100 ms급).
    처리: lots = 필지 DB 조회(경계 = 필지 외곽, multipart 경고) / area = 링 안전장치 → 안의 필지(50 % 규칙) → 경계 = 구역 링 /
          point = 중심점만(경계·필지 없음). 중심은 lots·area는 경계 bbox 중심, point는 그 점.
    출력: Target. 필지 없음·DB 없음·링 문제는 DomainError.
    """
    spec = dict(request["target"])
    mode = spec["mode"]
    site_db = request.get("site_db")
    abroad = is_global(request)   # Global·해외 — 필지 DB를 보지 않는다(osm_context)
    if mode == "lots":
        non_rhino_utils.set_projection()   # 필지는 국내뿐 — 앞서 해외 대상지를 다뤘어도 EPSG:5186으로 되돌린다
        lot_data = _load_lots(spec.get("pnus"), site_db)
        spec["pnus"] = list(lot_data.pnus)
        rings, warnings = get_target_rings(lot_data.lots)
        return Target(mode, spec, get_target_key(spec), get_lot_name(lot_data.lots), get_lots_center(lot_data.lots), rings,
                      list(lot_data.lots), lot_data, warnings)
    if mode == "area":
        ring = get_area_ring(spec.get("ring"))
        spec["ring"] = [[round(x, 3), round(y, 3)] for x, y in ring]
        ring = [tuple(p) for p in spec["ring"]]
        min_x, min_y, max_x, max_y = non_rhino_utils.get_bbox(ring)
        center = ((min_x + max_x) * 0.5, (min_y + max_y) * 0.5)
        target = Target(mode, spec, get_target_key(spec), "", center, [ring], [])
        if with_lots and abroad:
            target.name = _get_place_label(center, "구역", site_db)
        elif with_lots:
            lots = get_area_lots(ring, site_db)
            target.lot_data = _load_lots([lot.pnu for lot in lots], site_db) if lots else None
            target.lots = list(target.lot_data.lots) if target.lot_data else []
            target.name = _get_place_label(center, "구역", site_db)
            if not lots:
                target.warnings.append(_warning("warn", "area_no_lots", "구역 안 필지 0 — 대상지 조서가 비어 나옵니다",
                                                "필지 면적의 %d %% 이상이 구역 안에 있어야 대상 필지로 셉니다." % round(constants.AREA_LOT_MIN_FRACTION * 100)))
        return target
    center = spec.get("center")
    if not center or len(center) != 2:
        raise ValueError("위치(중심점)가 없습니다")
    center = (float(center[0]), float(center[1]))
    spec["center"] = [round(center[0], 2), round(center[1], 2)]
    target = Target(mode, spec, get_target_key(spec), "", center, [], [])
    if with_lots:
        target.name = _get_place_label(center, "일대", site_db)
    return target


def get_target_extent_ring(target, radius, shape, paper_mm, scales):
    # type: (Target, float, str, tuple, list) -> list
    """범위 링 — frame = 가장 큰 축척 용지 프레임 사각형(위치 방식 기본), site = 대상지 경계 그대로(구역 방식 기본 — 그린 경계가 곧 범위,
    필지가 여럿이면 볼록껍질), 나머지는 get_extent_ring(경계 링, 없으면 중심점)."""
    if shape == "site":
        if not target.site_rings:
            raise ValueError("대상지 경계가 없어 '경계 그대로' 범위를 쓸 수 없습니다")
        if len(target.site_rings) == 1:
            return [tuple(p) for p in target.site_rings[0]]
        return non_rhino_utils.get_clean_ring(non_rhino_utils._get_convex_hull([p for ring in target.site_rings for p in ring]))
    if shape == "frame":
        min_x, min_y, max_x, max_y = Frame(paper_mm, max(scales), target.center).world_bounds()
        return [(min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)]
    return non_rhino_utils.get_extent_ring(target.site_rings or [[target.center]], radius, shape)


def _load_lots(pnus, site_db):
    # type: (list, str) -> object
    """lot_db.load에 중단 코드를 싣는다 — DB 파일 없음 site_db_missing, 형식 오류·DB에 없는 PNU no_lots."""
    try:
        return lot_db.load(pnus, site_db)
    except FileNotFoundError as exc:
        raise DomainError("site_db_missing", str(exc))
    except (KeyError, ValueError) as exc:
        raise DomainError("no_lots", str(exc.args[0]) if exc.args else str(exc))


def _load_context(bounds, context_db_path, include_minor):
    # type: (tuple, str, bool) -> object
    """context_db.load에 중단 코드를 싣는다 — DB 파일 없음 context_db_missing."""
    try:
        return context_db.load(bounds, database_path=context_db_path, include_minor=include_minor)
    except FileNotFoundError as exc:
        raise DomainError("context_db_missing", str(exc))


def _get_paper_and_scales(options):
    # type: (dict) -> tuple
    """options → (paper_mm, scales). 용지 mm 양수·scales ⊂ BASEMAP_SCALES 검증."""
    paper_mm = tuple(options.get("paper_mm") or constants.PAPER_SIZES_MM.get(options.get("paper"), constants.PAPER_SIZES_MM["A1"]))
    if len(paper_mm) != 2 or min(float(v) for v in paper_mm) <= 0:
        raise ValueError("용지 크기(mm)는 양수 두 개여야 합니다: %s" % (paper_mm,))
    scales = sorted({int(s) for s in (options.get("scales") or constants.PANEL_DEFAULT_OPTIONS["scales"])})
    bad = [s for s in scales if s not in constants.BASEMAP_SCALES]
    if bad:
        raise ValueError("지원하지 않는 축척 %s — 가능한 값 %s" % (bad, list(constants.BASEMAP_SCALES)))
    return (float(paper_mm[0]), float(paper_mm[1])), scales


def _get_sheet_coverage(bounds, have, center):
    # type: (tuple, dict, tuple) -> tuple
    """bounds(EPSG:5186)에 걸치는 1:5000 도엽 → (needed 코드 목록, missing [{topo_sheet, dir, center}])."""
    lng0, lat0 = non_rhino_utils.get_wgs84_from_tm(bounds[0], bounds[1])
    lng1, lat1 = non_rhino_utils.get_wgs84_from_tm(bounds[2], bounds[3])
    needed = non_rhino_utils.get_topo_sheet_codes_in_bounds(lng0, lat0, lng1, lat1)
    missing = []
    for code in needed:
        if code in have:
            continue
        left, bottom, right, top = non_rhino_utils.get_topo_sheet_bounds(code)
        sx, sy = non_rhino_utils.get_tm_from_wgs84((left + right) * 0.5, (bottom + top) * 0.5)
        missing.append({"topo_sheet": code, "dir": _get_direction(sx - center[0], sy - center[1]), "center": _lnglat(sx, sy)})
    return needed, missing


def _get_coverage_warning(needed, missing):
    # type: (list, list) -> dict
    where = ", ".join("%s(%s쪽)" % (m["topo_sheet"], m["dir"]) for m in missing[:4])
    return _warning("warn", "coverage", "도엽 %d/%d장 없음 — %s" % (len(missing), len(needed), where),
                    "그 구역은 지형·도로면·건물 층수 보완이 빠집니다. 브이월드에서 도엽을 받아 data/raw/수치지형도_5000/에 두고 dev_context_builder.py를 다시 돌리세요.",
                    {"label": "절차 열기", "path": "docs/data_sources.md"}, missing[0]["center"])


def _get_align_stats(samples):
    # type: (list) -> dict
    """features theme 'qa' kind 'align_sample'(value = 거리 m, attrs dx·dy) → {median, p90, n, low_sample, dx, dy}."""
    sheets = [s for s in samples if getattr(s, "kind", "") == "align_sheet"]   # 배포 팩은 도엽 요약(dev_deploy.slim_pack_database) — n 가중평균
    if sheets:
        weights = [int(s.attrs.get("n", 0)) for s in sheets]
        total = sum(weights)
        if total:
            mean = lambda key: round(sum(w * float(s.attrs.get(key, 0.0)) for w, s in zip(weights, sheets)) / total, 2)
            return {"median": round(sum(w * float(s.value) for w, s in zip(weights, sheets)) / total, 2), "p90": mean("p90"),
                    "n": total, "low_sample": total < constants.ALIGN_LOW_SAMPLE, "dx": mean("dx"), "dy": mean("dy")}
    values = [float(s.value) for s in samples if s.value is not None]
    n = len(values)
    if not n:
        return {"median": None, "p90": None, "n": 0, "low_sample": True, "dx": None, "dy": None}
    dxs = [float(s.attrs.get("dx")) for s in samples if (s.attrs or {}).get("dx") is not None]
    dys = [float(s.attrs.get("dy")) for s in samples if (s.attrs or {}).get("dy") is not None]
    return {"median": round(statistics.median(values), 2),
            "p90": round(statistics.quantiles(values, n=10)[8] if n >= 2 else values[0], 2),
            "n": n, "low_sample": n < constants.ALIGN_LOW_SAMPLE,
            "dx": round(statistics.median(dxs), 2) if dxs else None, "dy": round(statistics.median(dys), 2) if dys else None}


# ── 원천 상태 ──────────────────────────────────────────────

def get_abroad_sources(today=None):
    # type: (datetime.date) -> list
    """해외 대상지의 원천 상태 4건(lot·building·terrain·api) — 필지 없음, 건물·지형은 생성 때 OSM·지형 타일에서 받는다."""
    today = (today or datetime.date.today()).isoformat()
    def row(source_id, name, level, text):
        return {"id": source_id, "label": constants.SOURCE_LABELS[source_id], "name": name, "date": today if level == "ok" else "",
                "age_months": 0.0 if level == "ok" else None, "level": level, "newer_date": None, "text": text}
    return [row("lot", "해외 — 필지 자료 없음", "missing", "해외"), row("building", "OpenStreetMap", "ok", "생성 때 받음"),
            row("terrain", "Terrain Tiles (약 30 m DEM)", "ok", "생성 때 받음"), row("api", "필요 없음", "ok", "")]


def get_sources(lot_database_path=None, context_database_path=None, today=None):
    # type: (object, object, datetime.date) -> list
    """init_state·preflight_result가 쓰는 원천 상태 4건(lot·building·terrain·api, 순서 고정). coverage는 비워 둔다.

    입력: DB 경로 override 2개, today(테스트용). 처리: data_sources·source_files 기준일 → 경과 개월·레벨, .env 키 유무.
    출력: panel_ui.md `source` dict 목록. DB가 없으면 level 'missing'.
    """
    today = today or datetime.date.today()
    news = site_prefs.get_source_news()
    sources = []
    # 필지
    lot_date, lot_name = "", "토지특성정보"
    try:
        for src in lot_db.load_sources(lot_database_path):
            if src.source_id == "vworld_land_char":
                lot_date, lot_name = src.reference_date or "", src.name or lot_name
        lot_level = None
    except (FileNotFoundError, RuntimeError, KeyError):
        lot_level = "missing"
    age = _get_months_since(lot_date, today)
    newer = (news.get("lot") or {}).get("newer_date")
    sources.append({"id": "lot", "label": constants.SOURCE_LABELS["lot"], "name": lot_name, "date": lot_date, "age_months": age,
                    "level": lot_level or _get_level(age, constants.SOURCE_AGE_THRESHOLDS["lot"], newer), "newer_date": newer,
                    "text": "%.1f개월" % age if age is not None else ""})
    # 건물·지형 (컨텍스트 DB)
    building = {"id": "building", "label": constants.SOURCE_LABELS["building"], "name": "GIS건물통합정보", "date": "", "age_months": None,
                "level": "missing", "newer_date": None, "text": "DB 없음"}
    terrain = {"id": "terrain", "label": constants.SOURCE_LABELS["terrain"], "name": "수치지형도 1:5,000", "date": "", "age_months": None,
               "level": "missing", "newer_date": None, "text": "DB 없음"}
    try:
        for src in context_db.load_sources(context_database_path):
            if src.source_id == "vworld_building":
                age = _get_months_since(src.reference_date, today)
                newer = (news.get("building") or {}).get("newer_date")
                building.update({"date": src.reference_date or "", "age_months": age,
                                 "level": _get_level(age, constants.SOURCE_AGE_THRESHOLDS["building"], newer), "newer_date": newer,
                                 "text": "%.1f개월" % age if age is not None else ""})
            elif src.source_id == "ngii_topo_5000":
                sheets = context_db.load_sheet_codes(context_database_path)
                years = sorted({(d or "")[:4] for d in sheets.values() if (d or "")[:4].isdigit()})
                date = years[0] if len(years) == 1 else ("%s~%s" % (years[0], years[-1]) if years else "")
                age = _get_months_since(years[0] + "0101", today) if years else None
                terrain.update({"date": date, "age_months": age, "level": _get_level(age, constants.SOURCE_AGE_THRESHOLDS["terrain"], None),
                                "text": "도엽 %d장" % len(sheets)})
    except (FileNotFoundError, RuntimeError):
        pass
    sources += [building, terrain]
    # 키 — VWorld 하나(지도·위성 배경, 항공사진, 주소 보조 검색). 없으면 OSM 지도·Esri 영상·지명 검색으로 같은 일을 한다
    vworld = bool(pnu_loader.get_local_env_value(constants.VWORLD_API_KEY_ENV))
    sources.append({"id": "api", "label": constants.SOURCE_LABELS["api"], "name": "VWorld", "date": "", "age_months": None,
                    "level": "ok" if vworld else "missing", "newer_date": None, "keys": {"vworld": vworld}, "text": "있음" if vworld else "없음"})
    return sources


def _get_upis_source(lot_sources, today):
    # type: (list, datetime.date) -> dict
    """필지 DB data_sources의 seoul_zoning 기준일 → 'upis' 원천 상태(메타 ①줄·stale_upis용. 패널 4건에는 넣지 않는다)."""
    date = next((src.reference_date or "" for src in lot_sources if src.source_id == "seoul_zoning"), "")
    age = _get_months_since(date, today)
    newer = (site_prefs.get_source_news().get("upis") or {}).get("newer_date")
    return {"id": "upis", "label": "도시계획", "name": constants.META_SOURCE_NAMES["upis"], "date": date, "age_months": age,
            "level": _get_level(age, constants.SOURCE_AGE_THRESHOLDS["upis"], newer), "newer_date": newer,
            "text": "%.1f개월" % age if age is not None else ""}


def mark_downloadable(sources, pending=True):
    # type: (list, bool) -> list
    """건물·지형이 이 PC에 없어도 생성할 때 받을 수 있으면(매니페스트 있음·pending) 'DB 없음' 대신 '생성할 때 받음'(level ok). sources를 고친다."""
    if constants.DATA_MANIFEST_URL and pending:
        for src in sources:
            if src["id"] in ("building", "terrain") and src["level"] == "missing":
                src.update(level="ok", text="생성할 때 받음", pending=True)
    return sources


def get_pending_packs(bounds):
    # type: (tuple) -> list
    """범위(EPSG:5186)에 걸치는데 이 PC에 없거나 새 판인 시군구 팩 — 생성 직전에 받을 것. 매니페스트 없음·오프라인은 빈 목록."""
    if not constants.DATA_MANIFEST_URL:
        return []
    try:
        return [pack for pack in data_pack.get_missing_packs(data_pack.get_manifest(), bounds=bounds) if pack["name"][:5].isdigit()]
    except Exception:   # 오프라인 — 있는 것으로 판단한다
        return []


def get_source_warnings(sources):
    # type: (list) -> list
    """원천 상태 → 경고 목록(stale_*·no_api_key·no_context_db). deliverables §C ⑤ 문안."""
    warnings = []
    for src in sources:
        if src["id"] == "api":   # 키는 선택 — 없어도 OSM·Esri로 같은 일을 한다(사용자에게 묻지 않는다)
            continue
        if src["level"] == "missing" and src["id"] in ("building", "terrain"):
            if not any(w["code"] == "no_context_db" for w in warnings):
                warnings.append(_warning("danger", "no_context_db", "지형·건물 DB 없음 — 필지·대상지만 생성됩니다",
                                         "data/seoul_context.db가 없습니다. python3 scripts/dev_context_builder.py 로 만들거나 복사하세요. 시트 7~10·12·13이 비어 나옵니다.",
                                         {"label": "절차 열기", "path": "docs/data_sources.md"}))
            continue
        if src["level"] in ("warn", "danger"):
            age = src["age_months"]
            newer = src.get("newer_date")
            tail = ("브이월드에서 새 판(기준일 %s)이 확인됨 → docs/data_sources.md §0 절차로 교체하세요" % newer if newer
                    else "새 판 미확인(목록 조회 실패 또는 게시 지연)")
            warnings.append(_warning(src["level"], "stale_%s" % src["id"],
                                     "%s 자료 %.1f개월 경과%s" % (src["label"], age, " · 새 판 있음" if newer else ""),
                                     "⚠ %s 자료가 %.1f개월 지났습니다(%s %s). %s" % (src["label"], age, src["name"], src["date"], tail),
                                     {"label": "절차 열기", "path": "docs/data_sources.md"}))
    return warnings


# ── prepare ────────────────────────────────────────────────

def _get_query_extent(target, radius, shape, paper_mm, scales, frames=True):
    # type: (Target, float, str, tuple, list, bool) -> tuple
    """범위 링·그 bbox·축척별 프레임 bbox·DB 조회 bbox(범위 ∪ 최대 프레임 ∪ 시트 + QUERY_MARGIN). 세계좌표 m.
    frames=False(2D 없음, has_2d)면 조회 bbox = 범위 bbox + QUERY_MARGIN."""
    extent_ring = get_target_extent_ring(target, radius, shape, paper_mm, scales)
    extent_bounds = non_rhino_utils.get_bbox(extent_ring)
    frame_bounds = {scale: Frame(paper_mm, scale, target.center).world_bounds() for scale in scales}
    boxes = [extent_bounds]
    if frames:
        boxes += [frame_bounds[max(scales)], sheet_svg.get_sheet_query_bounds(paper_mm, scales, target.center, extent_ring)]
    margin = constants.QUERY_MARGIN
    bounds = (min(b[0] for b in boxes) - margin, min(b[1] for b in boxes) - margin,
              max(b[2] for b in boxes) + margin, max(b[3] for b in boxes) + margin)
    return extent_ring, extent_bounds, frame_bounds, bounds


def get_query_bounds(request):
    # type: (dict) -> tuple
    """생성이 DB를 조회할 범위(EPSG:5186 bbox) — prepare와 같은 계산. 해외 대상지는 None.
    cmd_site가 생성 직전에 이 범위의 지역 데이터(시군구 팩)를 받는 데 쓴다. 필지 방식은 고른 필지가 필지 DB에 있어야 한다."""
    request = get_request_with_defaults(request)
    options = request["options"]
    paper_mm, scales = _get_paper_and_scales(options)
    target = resolve_target(request, with_lots=False)
    if is_global(request):
        return None
    radius = float(options.get("radius") or constants.CONTEXT_RADIUS)
    return _get_query_extent(target, radius, options.get("shape") or "circle", paper_mm, scales, has_2d(options))[3]


def prepare(request, progress=None, today=None):
    # type: (dict, object, datetime.date) -> Prepared
    """Rhino 금지. 입력 검증 → 필지·컨텍스트 질의 → 원점·범위 → 통계·경고·meta. python3 unittest가 전부 덮는다.

    입력: code_map §4.2 요청 dict(site_db·context_db로 fixture 주입, doc_origin은 run이 채운다), progress(phase, fraction, text) -> bool.
    처리: lot_db.load → 범위 링(get_extent_ring) → bounds = 범위 bbox ∪ 최대 프레임 bbox + QUERY_MARGIN → near_lots(limit=None)·
          context_db.load(include_minor) → 통계·경고·meta_lines. phase는 'query' 하나.
    출력: Prepared(세계좌표 m). 검증 실패 ValueError, 중단 조건은 DomainError(code), 콜백 False → Cancelled.
    """
    request = get_request_with_defaults(request)
    options = request["options"]
    today = today or datetime.date.today()
    radius = float(options.get("radius") or constants.CONTEXT_RADIUS)
    if not constants.RADIUS_MIN <= radius <= constants.RADIUS_MAX:
        raise ValueError("반경은 %d~%d m여야 합니다: %s" % (constants.RADIUS_MIN, constants.RADIUS_MAX, radius))
    shape = options.get("shape") or "circle"
    paper_mm, scales = _get_paper_and_scales(options)
    placement = options.get("placement") or "origin"

    _report(progress, "query", 0.0, "대상지 조회")
    target = resolve_target(request)                   # 방식별 경계·필지 — DomainError(no_lots|site_db_missing|area_invalid)
    request["target"] = target.spec
    request["pnus"] = [lot.pnu for lot in target.lots]
    target_lots = target.lots
    lot_name = request.get("lot_name") or target.name
    warnings = list(target.warnings)
    center = target.center
    origin, origin_reused, doc_origin = _get_origins(center, request.get("doc_origin"), placement)
    if origin_reused:
        warnings.append(_warning("info", "origin_reused", "문서 원점 재사용 E %.0f / N %.0f" % origin,
                                 "같은 문서에 이미 생성된 대상지가 있어 그 원점을 씁니다. 새 문서에서 생성하면 대상지 중심으로 원점이 잡힙니다."))

    extent_ring, extent_bounds, frame_bounds, bounds = _get_query_extent(target, radius, shape, paper_mm, scales, has_2d(options))

    if is_global(request):
        return _prepare_abroad(request, options, today, target, lot_name, warnings, origin, origin_reused, doc_origin, radius, shape,
                               extent_ring, extent_bounds, scales, bounds, frame_bounds, center, placement, progress)

    _report(progress, "query", 0.3, "주변 필지 조회")
    target_pnus = {lot.pnu for lot in target_lots}
    near_lots, truncated = lot_db.load_parcels_in_bounds(*bounds, limit=None, database_path=request["site_db"])
    near_lots = [lot for lot in near_lots if lot.pnu not in target_pnus]
    if truncated:
        warnings.append(_warning("warn", "lots_truncated", "주변 필지가 잘렸습니다 — 범위를 줄이세요", ""))
    span = max(bounds[2] - center[0], center[0] - bounds[0], bounds[3] - center[1], center[1] - bounds[1])
    lot_data = target.lot_data
    overlays = list(lot_data.overlays) if lot_data else []
    seen = {o.overlay_id for o in overlays}
    # 필지가 없는 방식(point·빈 구역)은 중심점 bbox로 같은 질의를 한다 — load_near_overlays는 min_x·max_x·min_y·max_y만 본다
    anchors = target_lots or [types.SimpleNamespace(min_x=center[0], max_x=center[0], min_y=center[1], max_y=center[1])]
    overlays += [o for o in lot_db.load_near_overlays(anchors, span, database_path=request["site_db"]) if o.overlay_id not in seen]

    _report(progress, "query", 0.6, "건물·지형 조회")
    context = _load_context(bounds, request["context_db"], bool(options.get("include_minor_buildings")))
    align_samples = context.get_features("qa", "align_sample") + context.get_features("qa", "align_sheet")
    lot_sources = lot_data.sources if lot_data else lot_db.load_sources(request["site_db"])
    sources = get_sources(request["site_db"], request["context_db"], today) + [_get_upis_source(lot_sources, today)]
    warnings += get_source_warnings(sources)

    skipped = get_skipped_phases(options)
    result_root = request.get("result_root") or os.path.join(constants.HOME_DIR, constants.RESULT_DIRNAME)
    prepared = Prepared(
        request=request, lot_name=lot_name, target_lots=target_lots, near_lots=near_lots, origin=origin, origin_reused=origin_reused,
        radius=radius, shape=shape, extent_ring=extent_ring, scales=scales, bounds=bounds, frame_bounds=frame_bounds, context=context,
        align_samples=align_samples, overlays=overlays, designations=list(lot_data.designations) if lot_data else [],
        sources=sources, warnings=warnings, skipped_phases=skipped,
        result_dir=os.path.join(result_root, today.strftime(constants.RESULT_DATE_FORMAT), lot_name), lots_truncated=bool(truncated),
        mode=target.mode, site_rings=target.site_rings, center=center, target_key=target.key, placement=placement, doc_origin=doc_origin,
    )

    # 통계·경고 — 범위 bbox 안 객체만(code_map §3 규칙 2)
    height = context_report.get_height_src_stats(prepared)
    grade_ab = height["height_grade"].get("A", 0.0) + height["height_grade"].get("B", 0.0)
    needed, missing = _get_sheet_coverage(extent_bounds, context_db.load_sheet_codes(request["context_db"]), center)
    prepared.stats = {"height_src": height["height_src"], "height_grade": height["height_grade"], "grade_ab": round(grade_ab, 4),
                      "buildings": height["n"], "lots": len(context_report.get_lots_in_extent(prepared)),
                      "sheets": context_report.get_sheet_codes(prepared), "sheets_needed": needed,
                      "align": _get_align_stats(align_samples), "mismatch_count": 0}
    if height["n"] and grade_ab < constants.HEIGHT_GRADE_AB_MIN:
        warnings.append(_warning("warn", "height_estimate", "높이 추정 비중 큼 — 등급 A+B %d %%" % round(grade_ab * 100),
                                 "대장 높이·층수(A·B)가 %d %% 미만입니다. 나머지는 수치지형도 층수나 기본값으로 추정한 높이입니다." % round(constants.HEIGHT_GRADE_AB_MIN * 100)))
    if not height["n"]:
        warnings.append(_warning("warn", "empty_buildings", "범위 안 건물 0동 — 컨텍스트 DB 범위·반경 확인", ""))
    if missing:
        warnings.append(_get_coverage_warning(needed, missing))
    prepared.meta = {"built_at": datetime.datetime.now().isoformat(timespec="seconds"), "today": today.isoformat(),
                     "sources": context_report.get_sources_by_role(prepared), "dates": context_report.get_source_dates(prepared)}
    prepared.meta["meta_lines"] = context_report.get_meta_lines(prepared)
    _report(progress, "query", 1.0, "건물 %d동 · 필지 %d" % (height["n"], prepared.stats["lots"]))
    return prepared


def _prepare_abroad(request, options, today, target, lot_name, warnings, origin, origin_reused, doc_origin, radius, shape,
                    extent_ring, extent_bounds, scales, bounds, frame_bounds, center, placement, progress):
    # type: (...) -> Prepared
    """prepare의 해외 갈래 — 필지·계획 없이 OSM 건물·피처 + 지형 타일 표고점(osm_context). 인터넷이 안 되면 DomainError(osm_failed)."""
    _report(progress, "query", 0.3, "OpenStreetMap·지형 타일 받는 중")
    try:
        context = osm_context.load(bounds, today.isoformat())
    except RuntimeError as exc:
        raise DomainError("osm_failed", str(exc))
    # OSM에는 국내 '무벽·가건물' 구분이 없다 — include_minor_buildings와 무관하게 전부 넣는다
    skipped = get_skipped_phases(options)
    result_root = request.get("result_root") or os.path.join(constants.HOME_DIR, constants.RESULT_DIRNAME)
    prepared = Prepared(
        request=request, lot_name=lot_name, target_lots=[], near_lots=[], origin=origin, origin_reused=origin_reused,
        radius=radius, shape=shape, extent_ring=extent_ring, scales=scales, bounds=bounds, frame_bounds=frame_bounds, context=context,
        align_samples=[], overlays=[], sources=context.sources, warnings=warnings, skipped_phases=skipped,
        result_dir=os.path.join(result_root, today.strftime(constants.RESULT_DATE_FORMAT), lot_name), lots_truncated=False,
        mode=target.mode, site_rings=target.site_rings, center=center, target_key=target.key, placement=placement, doc_origin=doc_origin,
    )
    height = context_report.get_height_src_stats(prepared)
    grade_ab = height["height_grade"].get("A", 0.0) + height["height_grade"].get("B", 0.0)
    prepared.stats = {"height_src": height["height_src"], "height_grade": height["height_grade"], "grade_ab": round(grade_ab, 4),
                      "buildings": height["n"], "lots": 0, "sheets": [], "sheets_needed": [], "align": _get_align_stats([]), "mismatch_count": 0}
    warnings.append(_warning("info", "abroad", "Global — OpenStreetMap 건물 %d동·지형 타일" % height["n"],
                             "필지·용도지역 도면은 Korea 모드에만 있고, 높이 태그가 있는 건물은 %d %%입니다(나머지 %.1f m 또는 층수 추정)."
                             % (round(grade_ab * 100), constants.DEFAULT_BUILDING_HEIGHT_M)))
    if not height["n"]:
        warnings.append(_warning("warn", "empty_buildings", "범위 안 OSM 건물 0동 — 지도에 건물이 그려진 곳인지 확인", ""))
    prepared.meta = {"built_at": datetime.datetime.now().isoformat(timespec="seconds"), "today": today.isoformat(),
                     "sources": context_report.get_sources_by_role(prepared), "dates": context_report.get_source_dates(prepared)}
    prepared.meta["meta_lines"] = context_report.get_meta_lines(prepared)
    _report(progress, "query", 1.0, "건물 %d동 (OSM)" % height["n"])
    return prepared


# ── run ────────────────────────────────────────────────────

RESPONSE_KEYS = ("ok", "cancelled", "dir", "lot_name", "elapsed_s", "options", "context", "basemap", "sheets", "tables", "files",
                 "warnings", "quality", "qa_geojson", "error")
_RESET_NAMES = (constants.RESULT_SHEETS_DIRNAME, constants.RESULT_TABLES_DIRNAME, constants.CONTEXT_MODEL_FILE_NAME, constants.BLENDER_MODEL_FILE_NAME,
                constants.CONTEXT_META_FILE_NAME)


def _get_error(exc, detail=""):
    # type: (Exception, str) -> dict
    """예외 → {code, title, detail}. code는 예외가 실은 것(DomainError.code), 없으면 exception. 도메인 예외(ValueError·KeyError·
    FileNotFoundError·RuntimeError)는 한국어 메시지가 곧 title, 나머지는 타입명 + traceback."""
    text = str(exc.args[0]) if exc.args else str(exc)
    code = getattr(exc, "code", "exception")
    if isinstance(exc, (ValueError, KeyError, FileNotFoundError, RuntimeError)):
        return {"code": code, "title": text.splitlines()[0][:80], "detail": text}
    return {"code": "exception", "title": "%s: %s" % (type(exc).__name__, text), "detail": detail or text}


def _get_empty_response(options):
    # type: (dict) -> dict
    """code_map §4.3 응답 dict 뼈대(전부 기본값). run이 phase마다 채운다."""
    return {
        "ok": False, "cancelled": False, "dir": "", "lot_name": "", "elapsed_s": 0.0, "options": dict(options or {}),
        "context": {"path": "", "layers": 0, "buildings": 0, "lots": 0, "demolished": 0, "tin_points": 0, "origin": None,
                    "origin_reused": False, "placement": (options or {}).get("placement", "origin"), "doc_origin": None, "model_unit": "", "imported": False, "import_text": "", "dwg": ""},
        "basemap": {"ready": False, "paper": (options or {}).get("paper", ""), "layers": 0, "scales": [], "exported": [], "dwg": ""},
        "sheets": [], "tables": [], "files": [], "warnings": [],
        "quality": {"height_src": {}, "align": {}, "skipped": {"buildings": 0, "lots": 0}, "mismatch_count": 0, "dates": {}},
        "qa_geojson": {"type": "FeatureCollection", "features": []}, "error": None,
    }


def _reset_result_dir(result_dir):
    # type: (str) -> None
    """결과 폴더 준비(write_3dm 첫 베이크 직전) — sheets/·tables/·context.3dm·context.json은 지우고 새로, .ai·log.txt는 보존(panel_ui.md 폴더 규약)."""
    os.makedirs(result_dir, exist_ok=True)
    for name in _RESET_NAMES:
        path = os.path.join(result_dir, name)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
        elif os.path.exists(path):
            os.remove(path)


def _list_files(result_dir):
    # type: (str) -> list
    """결과 폴더 전체 → [{name(상대 경로), path, bytes}]."""
    files = []
    for root, _dirs, names in os.walk(result_dir):
        for name in sorted(names):
            path = os.path.join(root, name)
            files.append({"name": os.path.relpath(path, result_dir), "path": path, "bytes": os.path.getsize(path)})
    return files


def _phase_failed(response, phase, exc):
    # type: (dict, str, Exception) -> None
    """phase 단위 예외(panel_ui.md) — 경고 skipped(danger) 하나 남기고 다음 phase로 간다."""
    response["warnings"].append(_warning("danger", "skipped", "%s 실패 — %s" % (constants.PHASE_LABELS.get(phase, phase), str(exc)[:120]),
                                         traceback.format_exc()))


def get_sheet_ids(options):
    # type: (dict) -> list
    """options.sheet_ids → 카탈로그에 있는 id만 카탈로그 순서로(옛 prefs의 다른 번호가 섞여도 깨지지 않게). 비면 전부.
    Global 모드는 Korea 전용 도면(SHEET_KOREA_ONLY)을 뺀다."""
    korea_only = (options or {}).get("region") == "global"
    valid = [sheet_id for sheet_id, key, *_ in constants.SHEET_CATALOG if not (korea_only and key in constants.SHEET_KOREA_ONLY)]
    wanted = set()
    for value in (options or {}).get("sheet_ids") or []:
        try:
            wanted.add(int(value))
        except (TypeError, ValueError):
            continue
    return [sheet_id for sheet_id in valid if sheet_id in wanted] or valid


def get_host():
    # type: () -> str
    """지금 도는 프로그램 — SketchUp 사이드카·웹판 워커(cmd_sketchup·cmd_web이 환경변수를 둔다)면 'sketchup'·'web', Blender 안이면 'blender',
    아니면 'rhino'(python3 테스트 포함). constants.HOST_LABELS의 키."""
    if os.environ.get(constants.HOST_ENV) in ("sketchup", "web"):
        return os.environ[constants.HOST_ENV]
    try:
        import bpy  # noqa: F401
    except ImportError:
        return "rhino"
    return "blender"


def get_host_modules():
    # type: () -> tuple
    """(지오메트리, 베이커) 모듈. Rhino = context_geometry·context_baker, Blender = mesh_geometry·blender_baker,
    SketchUp = mesh_geometry·sketchup_baker(사이드카 → SketchUp 호출), 웹 = mesh_geometry·web_baker(context.glb). 베이커 함수(get_doc_origin·clear_previous·bake·write_ref_and_origin·
    save_copy·zoom_to_site)와 build·get_snapped_ring은 이름이 같다."""
    host = get_host()
    if host == "blender":
        import blender_baker
        import mesh_geometry
        return mesh_geometry, blender_baker
    if host == "sketchup":
        import mesh_geometry
        import sketchup_baker
        return mesh_geometry, sketchup_baker
    if host == "web":
        import mesh_geometry
        import web_baker
        return mesh_geometry, web_baker
    import context_baker
    import context_geometry
    return context_geometry, context_baker


def run(request, progress=None, doc=None, keep=None):
    # type: (dict, object, object, dict) -> dict
    """Rhino 안. prepare → context_geometry.build → context_baker.bake/write_ref_and_origin/save_copy → (basemap) basemap_ai.write_basemap
    → (sheets) sheet_svg.write_sheets → (tables) context_report.write_tables → context.json·log.txt → 응답 dict(code_map §4.3).

    입력: 요청 dict(§4.2), progress(phase, fraction, text) -> bool(False = 취소), doc(RhinoDoc·Blender 장면; None이면 문서 원점을 읽지 않는다 — python3 테스트),
          keep(dict, 선택 — 성공하면 {dir, data(시트를 썼을 때만), prepared, terrain_tris}를 담아 준다. 패널 '도면 스타일'·'2D 만들기'가 지형까지 그릴 때 쓴다).
    처리: phase는 constants.PHASES 순서(refresh·import는 항상 skipped, 옵션으로 끈 basemap·sheets·tables도 skipped — 콜백 없음).
          Cancelled → 이번 베이크 객체(UDT_LOT_KEY) 삭제 → ok=false·cancelled=true. 도메인 예외 → error{code,title,detail}, 그 외 → exception+traceback.
          basemap·시트 한 장·tables의 실패는 phase 단위 예외(ok=true + warnings[skipped]). Rhino 모듈은 prepare 뒤에 import한다.
    출력: 응답 dict — ok=false여도 키 집합은 RESPONSE_KEYS 전부.
    """
    started = time.time()
    request = get_request_with_defaults(request)
    if doc is not None and not request.get("doc_origin"):
        request["doc_origin"] = get_host_modules()[1].get_doc_origin(doc)
    response = _get_empty_response(request["options"])
    state = {"phase": "query", "prepared": None, "lot_key": None, "baked": False, "geo": None, "save_timing": {}}
    try:
        _run_phases(request, progress, doc, response, state)
        response["ok"] = True
    except Cancelled as exc:
        response["cancelled"] = True
        response["error"] = {"code": "cancelled", "title": "취소됨", "detail": str(exc)}
        if doc is not None and state["baked"]:
            get_host_modules()[1].clear_previous(doc, state["lot_key"])
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
        response["error"] = _get_error(exc)
    except Exception as exc:   # noqa: BLE001 — 패널에 traceback을 전한다
        response["error"] = _get_error(exc, traceback.format_exc())
    response["elapsed_s"] = round(time.time() - started, 1)
    prepared = state["prepared"]
    if keep is not None and response["ok"]:   # 3D만 만들어도 지형 삼각형을 남긴다 — 결과 화면 '2D 만들기'(make_2d)가 지형 도면에 쓴다
        keep.clear()
        keep.update(dir=prepared.result_dir, data=state.get("sheet_data"), prepared=prepared,
                    terrain_tris=state["geo"].terrain_tris_world if state.get("geo") is not None else [])
    if prepared is not None:
        if response["ok"]:
            context_report.write_context_json(prepared, {k: response[k] for k in ("context", "basemap", "sheets", "tables", "warnings", "elapsed_s")},
                                              prepared.result_dir)
        context_report.append_log(prepared.result_dir, _get_log_lines(response, state))
        response["files"] = _list_files(prepared.result_dir)
    return response


def _get_log_lines(response, state):
    # type: (dict, dict) -> list
    """log.txt 한 번 실행 요약 — 결과·소요·수·건너뛴 건물 id 전부·경고 코드·오류(또는 cancelled at <phase>)."""
    geo = state["geo"]
    lines = ["%s %s · %.1f s · 반경 %s m" % ("OK" if response["ok"] else ("CANCELLED" if response["cancelled"] else "FAILED"),
                                            response["lot_name"], response["elapsed_s"], response["options"].get("radius"))]
    if response["cancelled"]:
        lines.append("cancelled at %s" % state["phase"])
    if geo is not None:
        c = geo.counts
        lines.append("지형 점 %s · 면 %s · 건물 %s동(투영 폴백 %s · 건너뜀 %s · 압출 실패 %s) · 커브 %s" % (
            c.get("tin_points"), c.get("faces"), c.get("buildings"), c.get("fallback_nearest"), c.get("fallback_skipped"), c.get("extrude_failed"), c.get("curves")))
        lines += ["건너뜀: " + s for s in geo.skipped]
    if state.get("save_timing"):
        t = state["save_timing"]
        lines.append("%s 저장 — 선택 %s s · 쓰기 %s s · 객체 %s · %s bytes" % (os.path.basename(response["context"]["path"] or constants.CONTEXT_MODEL_FILE_NAME),
                                                                    t.get("select_s"), t.get("write_s"), t.get("objects"), t.get("bytes")))
    for scale, r in sorted((state.get("ai_results") or {}).items()):
        lines.append("basemap_%d.ai — 레이어 %d · %s bytes · %s" % (scale, r["layers"], r["bytes"], " ".join("%s=%d" % kv for kv in sorted(r["counts"].items()))))
    lines += ["경고 %s: %s" % (w["code"], w["text"]) for w in response["warnings"]]
    if response["error"]:
        lines.append("오류 %s: %s\n%s" % (response["error"]["code"], response["error"]["title"], response["error"]["detail"]))
    return lines


def _run_phases(request, progress, doc, response, state):
    # type: (dict, object, object, dict, dict) -> None
    """run의 본문 — phase 순서대로 response를 채운다. 예외는 run이 받는다."""
    options = request["options"]
    prepared = prepare(request, progress)
    state["prepared"] = prepared
    response.update(dir=prepared.result_dir, lot_name=prepared.lot_name, options=dict(prepared.request["options"]), warnings=list(prepared.warnings))
    response["quality"].update(height_src=prepared.stats["height_src"], align=prepared.stats["align"], dates=prepared.meta["dates"])
    skipped = prepared.skipped_phases

    context_geometry, context_baker = get_host_modules()   # 호스트 모듈은 여기서부터 (prepare까지는 python3로 돈다)
    import sheet_svg

    # terrain — TIN·분류·투영·압출·커브 전부 (문서 변경 없음)
    state["phase"] = "terrain"
    _report(progress, "terrain", 0.0, "지형 TIN · 건물 압출")
    geo = context_geometry.build(prepared)
    state["geo"] = geo
    response["warnings"] += geo.warnings
    response["quality"]["skipped"] = {"buildings": len(geo.skipped), "lots": 0}
    _report(progress, "terrain", 1.0, "면 %d · 건물 %d동" % (geo.counts["faces"], geo.counts["buildings"]))

    # write_3dm — 이전 베이크 정리 → CTX 베이크(청크마다 콜백) → Ref·원점 → context.3dm 사본(베이스맵은 문서에 굽지 않는다 — basemap_ai가 .ai를 직접 쓴다)
    state["phase"] = "write_3dm"
    lot_key = prepared.target_key
    state["lot_key"] = lot_key
    _report(progress, "write_3dm", 0.0, "이전 베이크 정리")
    _reset_result_dir(prepared.result_dir)   # 이전 산출물은 첫 베이크 직전에 지운다 — query·terrain 중 취소·실패는 이전 결과를 남긴다
    context_baker.clear_previous(doc, lot_key)
    state["baked"] = True
    ids, items, chunk = [], geo.items, constants.RUN_BAKE_CHUNK
    for start in range(0, len(items), chunk):
        ids += context_baker.bake(doc, items[start:start + chunk], prepared, lot_key)
        _report(progress, "write_3dm", 0.7 * min(1.0, (start + chunk) / float(len(items) or 1)), "베이크 %d/%d" % (min(start + chunk, len(items)), len(items)))
    ids += context_baker.write_ref_and_origin(doc, prepared, lot_key)
    if len(ids) < len(items) + 2:
        response["warnings"].append(_warning("warn", "skipped", "베이크 실패 %d건" % (len(items) + 2 - len(ids)), ""))
    layers = {item.layer for item in items} | {constants.CTX_ROOT_LAYER + "::Ref"}
    _report(progress, "write_3dm", 0.85, "%s 저장" % constants.HOST_LABELS[get_host()]["model"])
    state["save_timing"] = {}
    path = context_baker.save_copy(doc, os.path.join(prepared.result_dir, constants.CONTEXT_MODEL_FILE_NAME), ids, state["save_timing"])
    response["context"].update(path=path, layers=len(layers), buildings=geo.counts["buildings"], lots=prepared.stats["lots"],
                               demolished=geo.counts.get("demolished", 0), tin_points=geo.counts["tin_points"], origin=list(prepared.origin),
                               origin_reused=prepared.origin_reused, placement=prepared.placement, doc_origin=list(prepared.doc_origin),
                               model_unit=str(getattr(doc, "ModelUnitSystem", "Meters")), imported=True, import_text="")   # Blender 장면은 m 고정
    if options.get("make_dwg") and constants.DWG_EXPORT_ENABLED and hasattr(context_baker, "save_dwg_from_3dm"):   # DWG는 Rhino만   # 2D 도면(BM::)만 .dwg로 — 실패해도 3dm은 남긴다
        _report(progress, "write_3dm", 0.95, ".dwg 저장")
        try:   # 방금 쓴 3dm을 헤드리스로 열어 쓴다 — 활성 문서에서 쓰면 Mac에서 멈춘다(context_baker.save_dwg_from_3dm)
            dwg_path = os.path.join(prepared.result_dir, constants.DWG_FILE_FORMAT % min(prepared.scales))
            response["context"]["dwg"] = context_baker.save_dwg_from_3dm(path, dwg_path, constants.BM_ROOT_LAYER)
        except Exception as exc:   # noqa: BLE001
            _phase_failed(response, "write_3dm", exc)
    _report(progress, "write_3dm", 1.0, "객체 %d · 레이어 %d" % (len(ids), len(layers)))

    _run_2d_phases(prepared, options, geo.terrain_tris_world, progress, response, state)


def _write_dwg(prepared):
    # type: (object) -> str
    """make_2d의 DWG — 가장 상세한 축척의 2D 선 도면(BM::)을 헤드리스 문서에 구워 basemap_<축척>.dwg로(Rhino만, context_baker.save_dwg)."""
    context_geometry, context_baker = get_host_modules()
    if not hasattr(context_baker, "save_dwg"):
        raise RuntimeError("DWG는 Rhino에서만 저장할 수 있습니다")
    scale = min(prepared.scales)
    items = context_geometry.build_basemap_2d(prepared, scale)
    return context_baker.save_dwg(items, prepared, os.path.join(prepared.result_dir, constants.DWG_FILE_FORMAT % scale))


def _run_2d_phases(prepared, options, terrain_tris, progress, response, state, dwg=False):
    # type: (object, dict, list, object, dict, dict, bool) -> None
    """basemap → sheets → tables phase(옵션으로 끈 것은 prepared.skipped_phases). run과 make_2d가 같이 쓴다. 활성 문서는 건드리지 않는다.
    dwg=True(make_2d의 make_dwg)면 basemap phase 끝에 _write_dwg — 실패는 phase 단위 경고."""
    import sheet_svg
    skipped = prepared.skipped_phases

    # basemap — 요청 축척마다 basemap_ai가 .ai를 직접 쓴다(Rhino 문서·뷰 불필요, 축척당 ≈0.5 s). 한 축척의 실패는 phase 단위 경고
    if "basemap" not in skipped:
        state["phase"] = "basemap"
        exported, layer_count = [], 0
        for n, scale in enumerate(prepared.scales):
            _report(progress, "basemap", n / float(len(prepared.scales)), "1:%d .ai" % scale)
            try:
                result = basemap_ai.write_basemap(prepared, scale, prepared.result_dir)
                exported.append(result["path"])
                layer_count = max(layer_count, result["layers"])
                state.setdefault("ai_results", {})[scale] = result
            except Exception as exc:   # noqa: BLE001
                _phase_failed(response, "basemap", exc)
        response["basemap"].update(ready=len(exported) == len(prepared.scales), layers=layer_count, scales=list(prepared.scales), exported=exported)
        if dwg:
            _report(progress, "basemap", 0.95, ".dwg 저장")
            try:
                response["basemap"]["dwg"] = _write_dwg(prepared)
            except Exception as exc:   # noqa: BLE001 — .ai는 남긴다
                _phase_failed(response, "basemap", exc)
        _report(progress, "basemap", 1.0, ".ai %d장" % len(exported) + (" · .dwg" if response["basemap"].get("dwg") else ""))

    # sheets — 한 장마다 콜백, 한 장의 실패는 empty+reason '오류'
    if "sheets" not in skipped:
        state["phase"] = "sheets"
        sheet_ids = get_sheet_ids(options)
        names = {sheet_id: name for sheet_id, _key, name, _en, _needs in constants.SHEET_CATALOG}
        sheets_dir = os.path.join(prepared.result_dir, constants.RESULT_SHEETS_DIRNAME)
        try:
            data = sheet_svg.SheetData.from_prepared(prepared, terrain_tris)
            state["sheet_data"] = data
        except Exception as exc:   # noqa: BLE001
            _phase_failed(response, "sheets", exc)
            data = None
        for n, sheet_id in enumerate(sheet_ids):
            _report(progress, "sheets", n / float(len(sheet_ids)), "시트 %d %s" % (sheet_id, names.get(sheet_id, "")))
            try:
                if data is None:
                    raise RuntimeError("시트 데이터 준비 실패")
                response["sheets"] += sheet_svg.write_sheets(data, sheets_dir, [sheet_id])
            except Exception as exc:   # noqa: BLE001
                response["sheets"].append({"id": sheet_id, "name": names.get(sheet_id, ""), "path": None, "empty": True, "reason": "오류"})
                _phase_failed(response, "sheets", exc)
        _report(progress, "sheets", 1.0, "시트 %d장" % len(sheet_ids))

    # tables — CSV 5개
    if "tables" not in skipped:
        state["phase"] = "tables"
        _report(progress, "tables", 0.0, "조서 CSV")
        try:
            response["tables"] = context_report.write_tables(prepared, prepared.result_dir)
        except Exception as exc:   # noqa: BLE001
            _phase_failed(response, "tables", exc)
        _report(progress, "tables", 1.0, "CSV %d개" % len(response["tables"]))


# ── preflight ──────────────────────────────────────────────

def _get_abroad_preflight(sources, features, warnings, scales, paper_mm, paper, center, bounds):
    # type: (list, list, list, list, tuple, str, tuple, tuple) -> dict
    """해외 대상지 preflight — 범위·프레임만 그리고 필지가 필요한 시트는 빈 시트로 둔다."""
    for scale in scales:
        f_min_x, f_min_y, f_max_x, f_max_y = Frame(paper_mm, scale, center).world_bounds()
        features.append(_ring_feature([(f_min_x, f_min_y), (f_max_x, f_min_y), (f_max_x, f_max_y), (f_min_x, f_max_y)],
                                      {"role": "frame", "scale": scale, "paper": paper, "over": False}))
    warnings.append(_warning("info", "abroad", "Global — OpenStreetMap·지형 타일을 생성 때 받습니다",
                             "필지·용도지역 도면은 Korea 모드에만 있고, 건물 높이는 OSM 태그(없으면 %.1f m)입니다. 인터넷 연결이 필요합니다."
                             % constants.DEFAULT_BUILDING_HEIGHT_M))
    empty_sheets = [sheet_id for sheet_id, key, _name, _en, _needs in constants.SHEET_CATALOG if key in constants.SHEET_KOREA_ONLY]
    estimate = {"buildings": 0, "lots": 0, "topo_have": 0, "topo_total": 0, "seconds": int(constants.ESTIMATE_SECONDS_BASE) + 20,
                "mb": 1, "note": "건물 수는 OSM에서 받은 뒤 알 수 있습니다"}
    return {"sources": sources, "extent_geojson": {"type": "FeatureCollection", "features": features}, "estimate": estimate,
            "empty_sheets": empty_sheets, "warnings": warnings, "bounds": list(bounds), "center": list(center)}


def preflight(request, today=None):
    # type: (dict, datetime.date) -> dict
    """Rhino 금지, 100 ms급. COUNT 질의만으로 사전 점검 — panel_ui.md `preflight_result` 페이로드(seq 제외).

    입력: {target(또는 pnus), options{radius, shape, paper, paper_mm, scales}, site_db, context_db}. 반경은 RADIUS_MIN~MAX로 자른다.
    처리: 범위 링(get_extent_ring — 미리보기 = 실제 생성 범위) → 도엽 커버 → bbox COUNT → 예상 초·MB → 빈 시트 → 프레임.
    출력: {sources, extent_geojson(role extent|topo_sheet|frame), estimate, empty_sheets, warnings, bounds, center}. 필지 없으면 KeyError.
    """
    request = get_request_with_defaults(request)
    options = request["options"]
    radius = float(min(max(float(options.get("radius") or constants.CONTEXT_RADIUS), constants.RADIUS_MIN), constants.RADIUS_MAX))
    shape = options.get("shape") or "circle"
    paper = options.get("paper") or "A1"
    paper_mm, scales = _get_paper_and_scales(options)
    target = resolve_target(request, with_lots=False)
    warnings = list(target.warnings)
    ring = get_target_extent_ring(target, radius, shape, paper_mm, scales)
    min_x, min_y, max_x, max_y = non_rhino_utils.get_bbox(ring)
    center = target.center
    abroad = is_global(request)
    sources = get_abroad_sources(today) if abroad else get_sources(request["site_db"], request["context_db"], today)
    pending = []   # DB 파일을 지정한 요청(fixture·개발 DB)과 해외는 받지 않는다
    if not abroad and not request["context_db"]:
        bounds = _get_query_extent(target, radius, shape, paper_mm, scales, has_2d(options))[3]
        pending = [p for p in get_pending_packs(bounds) if not p["name"].endswith("_site.db")]
    if pending:   # 이 범위의 건물·지형은 생성할 때 받는다 — 지금 이 PC에 있는 것만으로 '없음'·도엽 부족을 말하지 않는다
        for src in sources:
            if src["id"] in ("building", "terrain"):
                src.update(level="ok", text="생성할 때 받음 (%.0f MB)" % (sum(p.get("xz_size", 0) for p in pending) / 1048576.0), pending=True)
    warnings += [] if abroad else get_source_warnings(sources)
    features = [_ring_feature(ring, {"role": "extent", "radius": radius, "shape": shape})]
    if abroad:   # 해외 — 도엽·DB 개수가 없다. 건물 수는 생성 때 OSM에서 받아야 안다
        return _get_abroad_preflight(sources, features, warnings, scales, paper_mm, paper, center, (min_x, min_y, max_x, max_y))

    # 도엽 커버
    try:
        have = context_db.load_sheet_codes(request["context_db"])
    except (FileNotFoundError, RuntimeError):
        have = {}
    needed, missing = _get_sheet_coverage((min_x, min_y, max_x, max_y), have, center)
    for code in needed:
        left, bottom, right, top = non_rhino_utils.get_topo_sheet_bounds(code)
        features.append({"type": "Feature",
                         "geometry": {"type": "Polygon", "coordinates": [[[left, bottom], [right, bottom], [right, top], [left, top], [left, bottom]]]},
                         "properties": {"role": "topo_sheet", "topo_sheet": code, "year": (have.get(code) or "")[:4], "have": code in have}})
    terrain = next(s for s in sources if s["id"] == "terrain")
    terrain["coverage"] = None if pending else {"have": len(needed) - len(missing), "total": len(needed), "missing": missing}
    if missing and terrain["level"] != "missing" and not pending:
        warnings.append(_get_coverage_warning(needed, missing))

    # 예상 규모·빈 시트
    try:
        counts = context_db.count_in_bounds((min_x, min_y, max_x, max_y), request["context_db"], bool(options.get("include_minor_buildings")))
    except (FileNotFoundError, RuntimeError):
        counts = {"buildings": 0, "themes": {}}
    lot_count = lot_db.count_parcels_in_bounds(min_x, min_y, max_x, max_y, request["site_db"])
    buildings = counts["buildings"]
    estimate = {"buildings": buildings, "lots": lot_count, "topo_have": len(needed) - len(missing), "topo_total": len(needed),
                "seconds": int(round(constants.ESTIMATE_SECONDS_BASE + buildings * constants.ESTIMATE_SECONDS_PER_BUILDING)),
                "mb": max(1, int(round(buildings * constants.ESTIMATE_MB_PER_BUILDING))), "note": "",
                "pending_mb": round(sum(p.get("xz_size", 0) for p in pending) / 1048576.0) if pending else 0}   # 받기 전 — 건물 수·도엽은 모른다
    available = {"lot": lot_count > 0, "building": buildings > 0 or bool(pending), "image": True,
                 "terrain": counts["themes"].get("terrain", 0) > 0 or bool(pending), "road": counts["themes"].get("road", 0) > 0 or bool(pending)}
    empty_sheets = [sheet_id for sheet_id, _key, _name, _en, needs in constants.SHEET_CATALOG if not available[needs]]

    # 베이스맵 프레임
    for scale in scales:
        frame = Frame(paper_mm, scale, center)
        f_min_x, f_min_y, f_max_x, f_max_y = frame.world_bounds()
        over = f_min_x < min_x or f_max_x > max_x or f_min_y < min_y or f_max_y > max_y
        features.append(_ring_feature([(f_min_x, f_min_y), (f_max_x, f_min_y), (f_max_x, f_max_y), (f_min_x, f_max_y)],
                                      {"role": "frame", "scale": scale, "paper": paper, "over": over}))
        if over:
            warnings.append(_warning("info", "frame_over",
                                     "1:%d %s 프레임(%.1f×%.1f km)이 범위를 넘음 — 가장자리 빈 곳" % (scale, paper, frame.width_m / 1000, frame.height_m / 1000),
                                     "반경을 키우거나 축척을 줄이면 프레임이 채워집니다."))
    if max(scales) >= max(constants.BASEMAP_SCALES):
        # 실측 외삽(code_map §5.8): 1:5000 A1 프레임은 건물 4만 동·필지 10만 급 → 수십 초
        estimate["note"] = "1:%d 프레임은 건물·필지가 수만 건이라 수십 초 걸립니다" % max(scales)
        warnings.append(_warning("info", "slow_frame", "1:%d 프레임 — 생성에 수십 초" % max(scales), estimate["note"]))
    if buildings == 0 and terrain["level"] != "missing" and not pending:   # 받기 전에는 0동으로 센다
        warnings.append(_warning("warn", "empty_buildings", "반경 안 건물 0동 — 컨텍스트 DB 범위·반경 확인", ""))
    return {"sources": sources, "extent_geojson": {"type": "FeatureCollection", "features": features},
            "estimate": estimate, "empty_sheets": empty_sheets, "warnings": warnings,
            "bounds": [min_x, min_y, max_x, max_y], "center": list(center)}


def _ring_feature(ring, properties):
    # type: (list, dict) -> dict
    """[(x, y)] EPSG:5186 링 → WGS84 Polygon Feature(닫힘)."""
    coords = [_lnglat(x, y) for x, y in ring]
    coords.append(coords[0])
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [coords]}, "properties": properties}


# ── 진행률 ─────────────────────────────────────────────────

def get_progress_message(phase, fraction, text, skipped=(), details=None, state="running", error=None):
    # type: (str, float, str, object, dict, str, dict) -> dict
    """constants.PHASES·PHASE_WEIGHTS로 phase_status·percent를 계산해 panel_ui.md `progress` 페이로드를 만든다.

    입력: phase ∈ PHASES, fraction 0~1(단계 안), text 사용자용 한 줄, skipped(분모에서 뺄 phase), details {phase: 마지막 text},
          state running|done|failed|cancelled, error {code, title, detail}.
    처리: phase 앞은 done, 현재는 state에 따라 running/done/failed, 뒤는 pending. percent = 가중 합 / (전체 − skipped).
    출력: {"type": "progress", state, phase, phase_status, phase_detail, percent[, error]}.
    """
    if phase not in constants.PHASES:
        raise ValueError("알 수 없는 phase: %s" % phase)
    skipped = set(skipped or ())
    details = dict(details or {})
    fraction = max(0.0, min(1.0, float(fraction or 0.0)))
    status = {}
    percent_done = 0.0
    total = 0.0
    reached = False
    for name in constants.PHASES:
        weight = float(constants.PHASE_WEIGHTS[name])
        if name in skipped:
            status[name] = "skipped"
            continue
        total += weight
        if name == phase:
            status[name] = "running" if state == "running" else ("done" if state == "done" else "failed")
            percent_done += weight * fraction
            reached = True
        elif not reached:
            status[name] = "done"
            percent_done += weight
        else:
            status[name] = "pending"
    if state == "done":
        status = {k: ("skipped" if v == "skipped" else "done") for k, v in status.items()}
        percent_done = total
    if text:
        details[phase] = text
    message = {
        "type": "progress",
        "state": state,
        "phase": phase,
        "phase_status": status,
        "phase_detail": details,
        "percent": int(round(100.0 * percent_done / total)) if total else 0,
    }
    if error:
        message["error"] = error
    return message


def _read_meta(result_dir):
    # type: (str) -> dict
    with open(os.path.join(result_dir, constants.CONTEXT_META_FILE_NAME), encoding="utf-8") as handle:
        return json.load(handle)


def _prepare_from_meta(result_dir, extra_scale=None, site_db=None, context_db=None):
    # type: (str, int, object, object) -> object
    """결과 폴더의 context.json(target·options)으로 prepare를 다시 돌린다 — 원점은 도면과 무관해 doc_origin 없이(좌표 방식 검사도 건너뜀)."""
    meta = _read_meta(result_dir)
    options = dict(meta.get("options") or {}, make_basemap=True)   # 2D용 — 3D만 만든 결과(has_2d 거짓)도 프레임까지 조회한다
    scales = set(int(v) for v in (options.get("scales") or []))
    if extra_scale:
        scales.add(int(extra_scale))
    options["scales"] = sorted(scales)
    request = {"target": meta.get("target") or {"mode": "lots", "pnus": meta["pnus"]}, "options": options, "site_db": site_db,
               "context_db": context_db, "lot_name": meta.get("lot_name"), "result_root": os.path.dirname(os.path.dirname(result_dir))}
    prepared = prepare(request)
    prepared.result_dir = result_dir   # prepare는 오늘 날짜 폴더를 고른다
    return prepared


def export_basemap(result_dir, scale, site_db=None, context_db=None):
    # type: (str, int, object, object) -> dict
    """결과 폴더의 context.json(pnus·options·원점·스타일)으로 prepare를 다시 돌려 basemap_<축척>.ai 한 장을 쓴다(패널 '.ai 내보내기').
    Rhino 문서를 쓰지 않는다 — 문서에서 객체를 지웠어도 된다. 반환 basemap_ai.write_basemap 결과."""
    prepared = _prepare_from_meta(result_dir, scale, site_db, context_db)
    return basemap_ai.write_basemap(prepared, int(scale), result_dir)


def get_sheet_data(result_dir, keep=None, site_db=None, context_db=None):
    # type: (str, dict, object, object) -> tuple
    """결과 폴더의 (SheetData, Prepared). 이번 세션에 만든 결과면 keep(지형 삼각형 포함), 아니면 context.json으로 다시 prepare
    (지형 삼각형은 Rhino 메시에서 나와 다시 만들지 않는다 — 지형 시트는 비어 있다). keep이 있으면 새로 만든 것을 담아 둔다."""
    import sheet_svg
    same = bool(keep) and keep.get("dir") == result_dir
    if same and keep.get("data") is not None:
        return keep["data"], keep["prepared"]
    terrain_tris = keep.get("terrain_tris") or [] if same else []   # 3D만 만든 이번 세션 결과 — 지형 삼각형은 남아 있다
    prepared = _prepare_from_meta(result_dir, None, site_db, context_db)
    data = sheet_svg.SheetData.from_prepared(prepared, terrain_tris)
    if keep is not None:
        keep.clear()
        keep.update(dir=result_dir, data=data, prepared=prepared, terrain_tris=terrain_tris)
    return data, prepared


_2D_OPTION_KEYS = ("make_basemap", "paper", "paper_mm", "scales", "basemap_layers_on", "make_dwg", "make_sheets", "sheet_ids", "floor_breaks",
                   "elev_preset", "make_tables", "style")


def get_2d_request(result_dir, options, site_db=None, context_db=None):
    # type: (str, dict, object, object) -> dict
    """3D 결과 폴더 + 2D 옵션 → make_2d 요청(context.json의 대상지·옵션 위에 2D 키만 덮는다). 컨트롤러가 받을 팩 범위(get_query_bounds)에도 쓴다."""
    meta = _read_meta(result_dir)
    merged = dict(meta.get("options") or {})
    merged.update({key: (options or {})[key] for key in _2D_OPTION_KEYS if key in (options or {})})
    merged["make_dwg"] = bool(merged.get("make_dwg") and merged.get("make_basemap"))   # DWG = 베이스맵의 선 도면 — 베이스맵과 함께만
    # 3D가 쓴 원점(문서 원점 재사용 포함)을 그대로 — DWG 좌표가 3dm과 겹친다. .ai·도면은 세계좌표라 원점과 무관
    return {"target": meta.get("target") or {"mode": "lots", "pnus": meta.get("pnus") or []}, "options": merged, "site_db": site_db,
            "context_db": context_db, "lot_name": meta.get("lot_name"), "result_root": os.path.dirname(os.path.dirname(result_dir)),
            "doc_origin": meta.get("doc_origin") or None}


def make_2d(result_dir, options, progress=None, keep=None, site_db=None, context_db=None):
    # type: (str, dict, object, dict, object, object) -> dict
    """3D 결과 폴더에 2D 자료(베이스맵 .ai·도면·조서 CSV)를 더한다 — 패널 결과 화면 '2D 만들기'(panel_ui.md make_2d, 2026-10-19).

    입력: result_dir(run이 만든 폴더 — context.json 필요), options(2D 키, _2D_OPTION_KEYS), progress(phase, fraction, text) -> bool,
          keep(run이 남긴 {dir, terrain_tris} — 지형 도면용. 다른 폴더면 지형 도면은 빈다).
    처리: get_2d_request → prepare(가장 큰 프레임까지 다시 조회, phase 'query') → 이번에 켠 것의 sheets/·tables/만 비우고 _run_2d_phases
          → context.json의 options·basemap·sheets·tables 갱신 + log.txt. Rhino 문서는 건드리지 않는다.
    출력: {ok, cancelled, dir, elapsed_s, options, basemap, sheets, tables, files, warnings, error}.
    """
    started = time.time()
    request = get_request_with_defaults(get_2d_request(result_dir, options, site_db, context_db))
    response = _get_empty_response(request["options"])
    response.update(dir=result_dir)
    state = {"phase": "query"}
    prepared = None
    try:
        if not has_2d(request["options"]) and not request["options"].get("make_tables"):
            raise ValueError("만들 2D 자료를 하나 이상 고르세요")
        prepared = prepare(request, progress)
        prepared.result_dir = result_dir   # prepare는 오늘 날짜 폴더를 고른다 — 어제 만든 3D 폴더에 더할 수 있게
        response.update(options=dict(prepared.request["options"]), warnings=list(prepared.warnings))
        for key, name in (("make_sheets", constants.RESULT_SHEETS_DIRNAME), ("make_tables", constants.RESULT_TABLES_DIRNAME)):
            if request["options"].get(key):   # 이전 2D의 다른 도면·CSV가 새것처럼 남지 않게
                shutil.rmtree(os.path.join(result_dir, name), ignore_errors=True)
        same = bool(keep) and keep.get("dir") == result_dir
        terrain_tris = (keep.get("terrain_tris") or []) if same else []
        _run_2d_phases(prepared, request["options"], terrain_tris, progress, response, state,
                       dwg=bool(request["options"].get("make_dwg")) and constants.DWG_EXPORT_ENABLED)
        response["ok"] = True
        if keep is not None:
            keep.clear()
            keep.update(dir=result_dir, data=state.get("sheet_data"), prepared=prepared, terrain_tris=terrain_tris)
    except Cancelled as exc:
        response["cancelled"] = True
        response["error"] = {"code": "cancelled", "title": "취소됨", "detail": str(exc)}
    except (ValueError, KeyError, FileNotFoundError, RuntimeError) as exc:
        response["error"] = _get_error(exc)
    except Exception as exc:   # noqa: BLE001 — 패널에 traceback을 전한다
        response["error"] = _get_error(exc, traceback.format_exc())
    response["elapsed_s"] = round(time.time() - started, 1)
    if response["ok"]:
        meta = _read_meta(result_dir)
        meta["options"] = dict(response["options"])
        for key in ("basemap", "sheets", "tables"):
            if response[key]:
                meta[key] = response[key]
        with open(os.path.join(result_dir, constants.CONTEXT_META_FILE_NAME), "w", encoding="utf-8") as handle:
            json.dump(meta, handle, ensure_ascii=False, indent=1, default=str)
    lines = ["2D %s · %.1f s · 베이스맵 %d · 도면 %d · CSV %d" % ("OK" if response["ok"] else ("CANCELLED" if response["cancelled"] else "FAILED"),
                                                          response["elapsed_s"], len(response["basemap"]["exported"]), len(response["sheets"]), len(response["tables"]))]
    lines += ["경고 %s: %s" % (w["code"], w["text"]) for w in response["warnings"]]
    if response["error"]:
        lines.append("오류 %s: %s\n%s" % (response["error"]["code"], response["error"]["title"], response["error"]["detail"]))
    context_report.append_log(result_dir, lines)
    response["files"] = _list_files(result_dir)
    return response


def preview_sheet(result_dir, sheet_id, style, keep=None):
    # type: (str, int, dict, dict) -> dict
    """스타일을 바꾼 한 장 — 파일은 쓰지 않는다(패널 미리보기). 반환 {svg, empty, reason}."""
    import sheet_svg
    data, _prepared = get_sheet_data(result_dir, keep)
    data.options["style"] = dict(style or {})
    data.options["_aerial_dpi"] = constants.AERIAL_PREVIEW_DPI
    try:
        svg, empty, reason = sheet_svg.render_sheet(int(sheet_id), data)
    finally:
        data.options.pop("_aerial_dpi", None)
    # 패널 DOM에 그대로 넣는다 — 시트 id(map·legend·info…)가 패널 id(#map = Leaflet)와 겹치지 않게 접두어
    svg = svg.replace(' id="', ' id="pv_').replace("url(#", "url(#pv_")
    return {"svg": svg, "empty": empty, "reason": reason}


def apply_style(result_dir, style, keep=None):
    # type: (str, dict, dict) -> dict
    """스타일로 결과 폴더의 시트 전부와 이미 쓴 basemap_<축척>.ai를 다시 쓰고, context.json options.style을 바꾼다.
    지형 삼각형이 없으면(다시 prepare한 결과) 지형 시트 파일은 그대로 둔다. 반환 {sheets, basemaps, kept}."""
    import sheet_svg
    data, prepared = get_sheet_data(result_dir, keep)
    style = dict(style or {})
    data.options["style"] = style
    prepared.request["options"]["style"] = style
    meta = _read_meta(result_dir)
    written = [s for s in (meta.get("sheets") or []) if isinstance(s, dict) and s.get("path")]
    ids = [int(s["id"]) for s in written] or get_sheet_ids(meta.get("options") or {})
    terrain_ids = {sheet_id for sheet_id, _key, _name, _en, needs in constants.SHEET_CATALOG if needs == "terrain"}
    kept = [sheet_id for sheet_id in ids if sheet_id in terrain_ids and not data.terrain_tris]
    sheets = sheet_svg.write_sheets(data, os.path.join(result_dir, constants.RESULT_SHEETS_DIRNAME), [i for i in ids if i not in kept])
    sheets += [s for s in written if int(s["id"]) in kept]
    sheets.sort(key=lambda s: int(s["id"]))
    basemaps = []
    for name in sorted(os.listdir(result_dir)):
        match = re.match(r"basemap_(\d+)\.ai$", name)
        if match and int(match.group(1)) in prepared.frame_bounds:
            basemaps.append(basemap_ai.write_basemap(prepared, int(match.group(1)), result_dir)["path"])
    meta.setdefault("options", {})["style"] = style
    meta["sheets"] = sheets
    with open(os.path.join(result_dir, constants.CONTEXT_META_FILE_NAME), "w", encoding="utf-8") as handle:
        json.dump(meta, handle, ensure_ascii=False, indent=2)
    return {"sheets": sheets, "basemaps": basemaps, "kept": kept}
