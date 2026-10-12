"""현황도 시트 SVG 작성기와 프레임 수학 — docs/code_map.md §2·§5·§6, docs/deliverables.md §C 1~13.

Rhino 금지. origin을 모른다 — 입력은 전부 EPSG:5186 세계좌표 m이고 Frame이 종이 mm로 바꾼다.
Frame(paper_mm, scale, center)가 프레임 수학의 유일한 정의다(context_geometry·prepare의 frame_bounds도 이것).
Seoungsu make_basemap_L.py의 path_of/geom_paths/save_svg를 geopandas 없이 이식했다.

    SheetData.from_prepared(prepared, terrain_tris_world) → write_sheets(data, out_dir, sheet_ids, options)
    → [{id, name, path, empty, reason}]
"""

import datetime
import math
import os
import re
import statistics
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import constants
from non_rhino_utils import get_ring_area

SHEET_NAMES = {sheet_id: name for sheet_id, name, _ in constants.SHEET_CATALOG}


class Frame:
    """용지 한 장 ↔ 세계좌표. 종이 원점은 좌상단, y는 아래로 (SVG 규약)."""

    def __init__(self, paper_mm, scale, center):
        # type: (tuple, float, tuple) -> None
        self.paper_mm = (float(paper_mm[0]), float(paper_mm[1]))
        self.scale = float(scale)
        self.center = (float(center[0]), float(center[1]))

    @property
    def width_m(self):
        return self.paper_mm[0] * self.scale / 1000.0

    @property
    def height_m(self):
        return self.paper_mm[1] * self.scale / 1000.0

    def to_paper(self, x, y):
        # type: (float, float) -> tuple
        """세계 m → 종이 mm. (E − E0)/S × 1000 을 용지 중심 기준으로 둔다."""
        mm_x = (float(x) - self.center[0]) * 1000.0 / self.scale + self.paper_mm[0] * 0.5
        mm_y = self.paper_mm[1] * 0.5 - (float(y) - self.center[1]) * 1000.0 / self.scale
        return mm_x, mm_y

    def to_world(self, mm_x, mm_y):
        # type: (float, float) -> tuple
        """종이 mm → 세계 m (to_paper 역변환)."""
        x = (float(mm_x) - self.paper_mm[0] * 0.5) * self.scale / 1000.0 + self.center[0]
        y = (self.paper_mm[1] * 0.5 - float(mm_y)) * self.scale / 1000.0 + self.center[1]
        return x, y

    def world_bounds(self):
        # type: () -> tuple
        """(min_x, min_y, max_x, max_y) — 용지가 덮는 세계좌표 범위."""
        half_w, half_h = self.width_m * 0.5, self.height_m * 0.5
        return (self.center[0] - half_w, self.center[1] - half_h, self.center[0] + half_w, self.center[1] + half_h)


@dataclass
class SheetData:
    """시트 작성기 입력. 좌표는 전부 세계좌표 m. lot은 lot_db.LotInfo, building·feature는 context_db 데이터클래스.

    terrain_tris: [((x, y, z), (x, y, z), (x, y, z), class_name)] — context_geometry.build_terrain이 세계좌표로 되돌린 것.
    meta_lines: 여백 5줄(context_report.get_meta_lines). sources: DataSource 목록(출처 1줄).
    """

    frame: Frame
    target_lots: list = field(default_factory=list)
    near_lots: list = field(default_factory=list)
    buildings: list = field(default_factory=list)
    features: list = field(default_factory=list)
    overlays: list = field(default_factory=list)
    extent_ring: list = field(default_factory=list)
    terrain_tris: list = field(default_factory=list)
    meta_lines: list = field(default_factory=list)
    sources: list = field(default_factory=list)
    options: dict = field(default_factory=dict)
    stats: dict = field(default_factory=dict)
    lot_name: str = ""
    mode: str = "lots"                                 # 대상지 방식 — 라벨·카드 문구가 다르다
    site_rings: list = field(default_factory=list)     # 대상지 경계(세계좌표) — lots = 필지 외곽, area = 구역, point = 없음
    path_cache: dict = field(default_factory=dict, repr=False)   # id(geometry) → path d. 13장이 같은 필지·건물·도로를 다시 그리지 않게(2026-10-08: 5.1 s의 80 %)

    @classmethod
    def from_prepared(cls, prepared, terrain_tris_world=None):
        # type: (object, list) -> SheetData
        """context_builder.Prepared → SheetData. 프레임 중심은 대상지 중심(prepared.center), 축척은 범위 링이 들어가는 가장 작은 축척(없으면 최대)."""
        options = prepared.request.get("options") or {}
        center = getattr(prepared, "center", None)
        if center is None:   # 예전 Prepared(필지만) — 대상 필지 bbox 중심
            lots_bounds = [_get_item_bounds(lot) for lot in prepared.target_lots]
            center = ((min(b[0] for b in lots_bounds) + max(b[2] for b in lots_bounds)) * 0.5,
                      (min(b[1] for b in lots_bounds) + max(b[3] for b in lots_bounds)) * 0.5)
        paper_mm = options.get("paper_mm") or constants.PAPER_SIZES_MM[options.get("paper", "A1")]
        frame = get_frame_for_ring(paper_mm, sorted(prepared.scales or [max(constants.BASEMAP_SCALES)]), center,
                                   prepared.extent_ring)
        return cls(
            frame=frame, target_lots=list(prepared.target_lots), near_lots=list(prepared.near_lots),
            buildings=list(prepared.buildings), features=list(prepared.features), overlays=list(prepared.overlays),
            extent_ring=list(prepared.extent_ring), terrain_tris=list(terrain_tris_world or []),
            meta_lines=list((prepared.meta or {}).get("meta_lines") or []), sources=list(prepared.sources),
            options=dict(options), stats=dict(prepared.stats or {}), lot_name=prepared.lot_name,
            mode=getattr(prepared, "mode", "lots"), site_rings=[list(r) for r in getattr(prepared, "site_rings", None) or []],
        )


def get_frame_for_ring(paper_mm, scales, center, ring):
    # type: (tuple, list, tuple, list) -> Frame
    """축척 후보(오름차순) 중 링이 통째로 들어가는 첫 축척의 Frame. 어느 것도 못 담으면 마지막(가장 큰) 축척."""
    frame = None
    for scale in scales:
        frame = Frame(paper_mm, scale, center)
        if not ring or _contains(frame.world_bounds(), _get_ring_bounds(ring)):
            return frame
    return frame


# ─────────────────────────────────────────────
# 분류 함수 — 항목 하나 → 범례 키(None이면 그리지 않음). ctx는 options·데이터 의존 구간을 담는 dict
# ─────────────────────────────────────────────

def classify_target(lot, ctx):
    # type: (object, dict) -> str
    return "target"


def classify_land_use(lot, ctx):
    # type: (object, dict) -> str
    return constants.SHEET_LAND_USE_KEYS.get(lot.land_use_status or "", "etc")


def classify_land_category(lot, ctx):
    # type: (object, dict) -> str
    return constants.SHEET_LAND_CATEGORY_KEYS.get(lot.land_category or "", "etc")


def classify_zone(lot, ctx):
    # type: (object, dict) -> str
    name = lot.zone_name or ""
    for pattern, key in constants.SHEET_ZONE_KEYS.items():
        if pattern in name:
            return key
    return "etc"


def classify_district(overlay, ctx):
    # type: (object, dict) -> str
    return overlay.theme if overlay.theme in ("district", "area") else None


def classify_facility(overlay, ctx):
    # type: (object, dict) -> str
    if overlay.theme == "plan":
        return "plan"
    if overlay.theme == "facility":
        return constants.SHEET_FACILITY_KEYS.get(overlay.kind or "", "facility_etc")
    return None


def classify_use(building, ctx):
    # type: (object, dict) -> str
    code = (building.usability or "")[:2]
    if not code:
        return "unknown"
    return constants.SHEET_USE_KEYS.get(code, "etc")


def classify_floor(building, ctx):
    # type: (object, dict) -> str
    floors = int(building.grnd_flr or 0)
    if floors <= 0:
        return "unknown"
    for index, upper in enumerate(ctx["floor_breaks"]):
        if floors <= upper:
            return "f%d" % index
    return "f%d" % len(ctx["floor_breaks"])


def classify_age(building, ctx):
    # type: (object, dict) -> str
    year_text = (building.use_apr_day or "")[:4]
    if not year_text.isdigit() or int(year_text) < 1800:
        return "unknown"
    age = ctx["year"] - int(year_text)
    for index, upper in enumerate(constants.AGE_BANDS_YEARS):
        if age < upper:
            return "age%d" % index
    return "age%d" % len(constants.AGE_BANDS_YEARS)


def classify_road(item, ctx):
    # type: (object, dict) -> str
    """도로중심선 피처는 폭원 등급, 필지는 맹지만."""
    if hasattr(item, "road_contact"):
        return "landlocked" if (item.road_contact or "") == constants.SHEET_LANDLOCKED else None
    if item.theme != "road" or item.kind != "centerline":
        return None
    if item.value is None:
        return "w_unknown"
    for lower, key in constants.SHEET_ROAD_WIDTH_BREAKS:
        if float(item.value) >= lower:
            return key
    return "w_unknown"


def classify_price(lot, ctx):
    # type: (object, dict) -> str
    price = lot.land_price_won
    if price is None or float(price) <= 0:
        return "unknown"
    for index, upper in enumerate(ctx["price_breaks"]):
        if float(price) <= upper:
            return "p%d" % index
    return "p%d" % len(ctx["price_breaks"])


def classify_elev(tri, ctx):
    # type: (tuple, dict) -> str
    z = (tri[0][2] + tri[1][2] + tri[2][2]) / 3.0
    return "e%d" % int(math.floor(z / ctx["elev_step"]))


def classify_slope(tri, ctx):
    # type: (tuple, dict) -> str
    degrees = get_slope_deg(tri)
    for index, upper in enumerate(constants.SLOPE_BREAKS_DEG):
        if degrees < upper:
            return "s%d" % index
    return "s%d" % len(constants.SLOPE_BREAKS_DEG)


def get_slope_deg(tri):
    # type: (tuple) -> float
    """삼각형 세 꼭짓점 → 면 기울기(도). 법선의 수직 성분으로 계산, 퇴화 삼각형은 0."""
    (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri[0], tri[1], tri[2]
    ux, uy, uz = bx - ax, by - ay, bz - az
    vx, vy, vz = cx - ax, cy - ay, cz - az
    nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0.0:
        return 0.0
    return math.degrees(math.acos(max(-1.0, min(1.0, abs(nz) / length))))


# (id, name, classify_fn, legend) — legend = constants.SHEET_LEGENDS[id] = (대상, [(키, 라벨, 스타일)])
SHEETS = [
    (1, SHEET_NAMES[1], classify_target, constants.SHEET_LEGENDS[1]),
    (2, SHEET_NAMES[2], classify_land_use, constants.SHEET_LEGENDS[2]),
    (3, SHEET_NAMES[3], classify_land_category, constants.SHEET_LEGENDS[3]),
    (4, SHEET_NAMES[4], classify_zone, constants.SHEET_LEGENDS[4]),
    (5, SHEET_NAMES[5], classify_district, constants.SHEET_LEGENDS[5]),
    (6, SHEET_NAMES[6], classify_facility, constants.SHEET_LEGENDS[6]),
    (7, SHEET_NAMES[7], classify_use, constants.SHEET_LEGENDS[7]),
    (8, SHEET_NAMES[8], classify_floor, constants.SHEET_LEGENDS[8]),
    (9, SHEET_NAMES[9], classify_age, constants.SHEET_LEGENDS[9]),
    (10, SHEET_NAMES[10], classify_road, constants.SHEET_LEGENDS[10]),
    (11, SHEET_NAMES[11], classify_price, constants.SHEET_LEGENDS[11]),
    (12, SHEET_NAMES[12], classify_elev, constants.SHEET_LEGENDS[12]),
    (13, SHEET_NAMES[13], classify_slope, constants.SHEET_LEGENDS[13]),
]


# ─────────────────────────────────────────────
# 좌표·형상 유틸 (GeoJSON dict → SVG path d)
# ─────────────────────────────────────────────

def _fmt(value):
    return "%.2f" % value


def _get_clip_rect(frame):
    # type: (Frame) -> tuple
    """용지 + 여유(SHEET_CLIP_MARGIN_MM) 사각형 (min_x, min_y, max_x, max_y) mm."""
    margin = constants.SHEET_CLIP_MARGIN_MM
    return (-margin, -margin, frame.paper_mm[0] + margin, frame.paper_mm[1] + margin)


def get_clipped_ring(ring_mm, rect):
    # type: (list, tuple) -> list
    """닫힌 링(mm)을 사각형으로 자른다 — Sutherland–Hodgman. 구멍 링도 따로 잘라 evenodd로 채우면 결과가 맞는다.

    입력: ring_mm [(x, y)], rect (min_x, min_y, max_x, max_y). 처리: 변 4개에 차례로 잘라 교점을 넣는다. 출력: 새 링(비면 []).
    """
    min_x, min_y, max_x, max_y = rect
    edges = ((0, min_x, True), (0, max_x, False), (1, min_y, True), (1, max_y, False))   # (축, 경계값, 경계 이상이 안쪽인가)
    output = list(ring_mm)
    for axis, bound, keep_greater in edges:
        if not output:
            break
        inputs, output = output, []
        prev = inputs[-1]
        prev_in = (prev[axis] >= bound) if keep_greater else (prev[axis] <= bound)
        for cur in inputs:
            cur_in = (cur[axis] >= bound) if keep_greater else (cur[axis] <= bound)
            if cur_in != prev_in:
                t = (bound - prev[axis]) / (cur[axis] - prev[axis])
                output.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
            if cur_in:
                output.append(cur)
            prev, prev_in = cur, cur_in
    return output


def _ring_d(ring, frame, close):
    # type: (list, Frame, bool) -> str
    """세계좌표 점열 → path d. 면은 용지 사각형으로 자르고, 0.01 mm 정수로 반올림한 뒤 상대좌표(l)로 쓴다 — 누적 오차 없음.

    SHEET_MIN_VERTEX_MM보다 가까운 연속 정점은 버린다. 선은 자르지 않는다(clipPath가 가리고 바이트도 작다).
    """
    points = [frame.to_paper(p[0], p[1]) for p in ring]
    if close and points:
        rect = _get_clip_rect(frame)
        if not _contains(rect, _get_ring_bounds(points)):
            points = get_clipped_ring(points, rect)
    unit = int(round(constants.SHEET_MIN_VERTEX_MM * 100))
    kept = []
    for x, y in points:
        ix, iy = int(round(x * 100)), int(round(y * 100))
        if kept and abs(ix - kept[-1][0]) < unit and abs(iy - kept[-1][1]) < unit:
            continue
        kept.append((ix, iy))
    if close and len(kept) > 1 and abs(kept[0][0] - kept[-1][0]) < unit and abs(kept[0][1] - kept[-1][1]) < unit:
        kept.pop()
    if len(kept) < (3 if close else 2):
        return ""
    head = "M%s %s" % (_fmt(kept[0][0] / 100.0), _fmt(kept[0][1] / 100.0))
    deltas = " ".join("%s %s" % (_fmt((kept[i][0] - kept[i - 1][0]) / 100.0), _fmt((kept[i][1] - kept[i - 1][1]) / 100.0)) for i in range(1, len(kept)))
    return head + "l" + deltas + ("Z" if close else "")


def get_path_d(geometry, frame):
    # type: (dict, Frame) -> str
    """GeoJSON Polygon·MultiPolygon·LineString·MultiLineString → path d(한 path에 링 전부, evenodd). 그 외·용지 밖은 ""."""
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        parts = [_ring_d(ring, frame, True) for ring in coords]
    elif kind == "MultiPolygon":
        parts = [_ring_d(ring, frame, True) for polygon in coords for ring in polygon]
    elif kind == "LineString":
        parts = [_ring_d(coords, frame, False)]
    elif kind == "MultiLineString":
        parts = [_ring_d(line, frame, False) for line in coords]
    else:
        return ""
    return "".join(part for part in parts if part)


def _iter_points(geometry):
    coords = geometry.get("coordinates") or []
    kind = geometry.get("type")
    if kind == "Point":
        return [coords]
    if kind in ("LineString", "MultiPoint"):
        return coords
    if kind in ("Polygon", "MultiLineString"):
        return [p for ring in coords for p in ring]
    if kind == "MultiPolygon":
        return [p for polygon in coords for ring in polygon for p in ring]
    return []


def _get_ring_bounds(points):
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    return (min(xs), min(ys), max(xs), max(ys))


def _get_item_bounds(item):
    # type: (object) -> tuple
    """(min_x, min_y, max_x, max_y). DB 데이터클래스는 bbox 컬럼을, 그 외(overlay·합성 객체)는 형상에서."""
    if hasattr(item, "min_x"):
        return (float(item.min_x), float(item.min_y), float(item.max_x), float(item.max_y))
    points = _iter_points(item.geometry)
    return _get_ring_bounds(points) if points else (0.0, 0.0, 0.0, 0.0)


def _intersects(a, b):
    return a[0] <= b[2] and a[2] >= b[0] and a[1] <= b[3] and a[3] >= b[1]


def _contains(outer, inner):
    return outer[0] <= inner[0] and outer[1] <= inner[1] and outer[2] >= inner[2] and outer[3] >= inner[3]


def _get_geometry_measure(geometry):
    # type: (dict) -> float
    """면이면 ㎡(외곽 − 구멍), 선이면 m. 카드·범례 비율용."""
    kind = geometry.get("type")
    coords = geometry.get("coordinates") or []
    if kind == "Polygon":
        coords = [coords]
    if kind in ("Polygon", "MultiPolygon"):
        return sum(get_ring_area(polygon[0]) - sum(get_ring_area(hole) for hole in polygon[1:]) for polygon in coords if polygon)
    if kind == "LineString":
        coords = [coords]
    if kind in ("LineString", "MultiLineString"):
        return sum(math.hypot(line[i + 1][0] - line[i][0], line[i + 1][1] - line[i][1])
                   for line in coords for i in range(len(line) - 1))
    return 0.0


def _attrs(style):
    return "".join(' %s="%s"' % (key, value) for key, value in style.items())


def _text(x, y, content, size, **extra):
    return '<text x="%s" y="%s" font-size="%s"%s>%s</text>' % (_fmt(x), _fmt(y), size, _attrs(extra), escape(str(content)))


# ─────────────────────────────────────────────
# 시트별 동적 범례(#8 층수·#11 지가·#12 표고)와 분류 컨텍스트
# ─────────────────────────────────────────────

def _get_sheet_context(sheet_id, data, items):
    # type: (int, SheetData, list) -> tuple
    """(ctx, legend_entries). 고정 범례 시트는 constants 표 그대로, 동적 시트는 데이터로 구간·라벨·색을 만든다."""
    subject, entries = constants.SHEET_LEGENDS[sheet_id]
    ctx = {"options": data.options, "year": int(data.options.get("today_year") or datetime.date.today().year)}
    unknown = ("unknown", "미상", {"fill": "#FFFFFF", "stroke": constants.SHEET_BASE_STYLE["muted"]})
    if sheet_id == 8:
        breaks = tuple(constants.SHEET_FLOOR_BANDS_FIXED) + tuple(data.options.get("floor_breaks") or constants.FLOOR_BREAKS_DEFAULT)
        ctx["floor_breaks"] = breaks
        labels, lower = [], 1
        for upper in breaks:
            labels.append("%d층" % upper if upper == lower else "%d~%d층" % (lower, upper))
            lower = upper + 1
        labels.append("%d층 이상" % lower)
        entries = [("f%d" % i, label, {"fill": constants.SHEET_RAMPS["floor"][min(i, len(constants.SHEET_RAMPS["floor"]) - 1)]})
                   for i, label in enumerate(labels)] + [unknown]
    elif sheet_id == 11:
        prices = sorted(float(lot.land_price_won) for lot in items if lot.land_price_won and float(lot.land_price_won) > 0)
        n = constants.SHEET_PRICE_QUANTILES
        breaks = statistics.quantiles(prices, n=n) if len(prices) >= 2 else []
        ctx["price_breaks"] = breaks
        edges = [prices[0] if prices else 0.0] + list(breaks) + [prices[-1] if prices else 0.0]
        entries = [("p%d" % i, "%s~%s 만원/㎡" % (_won(edges[i]), _won(edges[i + 1])), {"fill": constants.SHEET_RAMPS["price"][min(i, n - 1)]})
                   for i in range(len(breaks) + 1)] + [unknown]
    elif sheet_id == 12:
        step = constants.ELEV_PRESETS.get(data.options.get("elev_preset"), list(constants.ELEV_PRESETS.values())[0])
        ctx["elev_step"] = step
        zs = [p[2] for tri in items for p in tri[:3]]
        if zs:
            low, high = int(math.floor(min(zs) / step)), int(math.floor(max(zs) / step))
            ramp = constants.SHEET_RAMPS["elev"]
            entries = [("e%d" % k, "%d~%d m" % (k * step, (k + 1) * step), {"fill": ramp[min(len(ramp) - 1, (k - low) * len(ramp) // max(1, high - low + 1))]})
                       for k in range(low, high + 1)]
    return ctx, entries


def _won(value):
    return "{:,}".format(int(round(value / 10000.0)))


def _get_subject_items(subject, data):
    # type: (str, SheetData) -> list
    if subject == "target_lot":
        return list(data.target_lots)
    if subject == "lot":
        seen, lots = set(), []
        for lot in list(data.target_lots) + list(data.near_lots):
            if lot.pnu not in seen:
                seen.add(lot.pnu)
                lots.append(lot)
        return lots
    if subject == "overlay":
        return list(data.overlays)
    if subject == "building":
        return list(data.buildings)
    if subject == "road":
        return [f for f in data.features if f.theme == "road" and f.kind == "centerline"] + _get_subject_items("lot", data)
    if subject == "terrain":
        return [tri for tri in data.terrain_tris if tri[3] != "outside"]
    return []


# ─────────────────────────────────────────────
# 그리기
# ─────────────────────────────────────────────

def _get_cached_path_d(geometry, frame, cache):
    # type: (dict, Frame, dict) -> str
    """get_path_d를 SheetData.path_cache로 한 번만 계산한다(같은 프레임 안에서만 쓴다)."""
    if cache is None:
        return get_path_d(geometry, frame)
    key = id(geometry)
    d = cache.get(key)
    if d is None:
        d = cache[key] = get_path_d(geometry, frame)
    return d


def _draw_items(items, frame, style, group_id, frame_bounds, cache=None):
    # type: (list, Frame, dict, str, tuple, dict) -> list
    lines = ['<g id="%s"%s>' % (group_id, _attrs(style))]
    for item in items:
        if not _intersects(_get_item_bounds(item), frame_bounds):
            continue
        d = _get_cached_path_d(item.geometry, frame, cache)
        if d:
            lines.append('<path d="%s"/>' % d)
    lines.append("</g>")
    return lines


def _draw_base(data, frame_bounds, subject):
    # type: (SheetData, tuple, str) -> list
    """모든 시트 공통 바탕: 수계·녹지·도로면·건물. 지적선·대상지·범위는 주제 위에 따로 얹는다.
    건물이 주제(subject building)면 base_buildings는 빈 그룹 — 주제 path가 윤곽선까지 맡는다(파일 1 MB 절약)."""
    frame, base = data.frame, constants.SHEET_BASE_STYLE
    water = [f for f in data.features if f.theme == "water" and f.kind in constants.WATER_SURFACE_KINDS]
    green = [f for f in data.features if f.theme == "green"]
    road = [f for f in data.features if f.theme == "road" and f.kind == "surface"]
    lines = []
    cache = data.path_cache
    lines += _draw_items(water, frame, dict(base["water"], **{"fill-rule": "evenodd"}), "base_water", frame_bounds, cache)
    lines += _draw_items(green, frame, dict(base["green"], **{"fill-rule": "evenodd"}), "base_green", frame_bounds, cache)
    lines += _draw_items(road, frame, dict(base["road"], **{"fill-rule": "evenodd"}), "base_road", frame_bounds, cache)
    lines += _draw_items([] if subject == "building" else data.buildings, frame,
                         dict(base["building"], **{"stroke-width": constants.SHEET_LINE_MM["building"], "fill-rule": "evenodd"}), "base_buildings", frame_bounds, cache)
    return lines


def _draw_overlay_lines(data, frame_bounds, subject):
    # type: (SheetData, tuple, str) -> list
    """지적선·대상지·범위 링. 필지가 주제(subject lot)면 base_parcels는 빈 그룹 — 주제 path가 지적선을 맡는다."""
    frame, base = data.frame, constants.SHEET_BASE_STYLE
    lines = _draw_items([] if subject == "lot" else data.near_lots, frame,
                        {"fill": "none", "stroke": base["parcel"]["stroke"], "stroke-width": constants.SHEET_LINE_MM["parcel"]}, "base_parcels", frame_bounds,
                        data.path_cache)
    if data.site_rings:   # 대상지 경계(구역·필지 외곽). 예전 데이터(경계 없음)는 대상 필지 형상
        lines.append('<g id="site" fill="none" stroke="%s" stroke-width="%s">' % (base["site"]["stroke"], constants.SHEET_LINE_MM["site"]))
        lines += ['<path d="%s"/>' % _ring_d(ring, frame, True) for ring in data.site_rings]
        lines.append("</g>")
    else:
        lines += _draw_items(data.target_lots, frame, {"fill": "none", "stroke": base["site"]["stroke"], "stroke-width": constants.SHEET_LINE_MM["site"]},
                             "site", frame_bounds, data.path_cache)
    lines.append('<g id="extent" fill="none" stroke="%s" stroke-width="%s" stroke-dasharray="%s">'
                 % (base["extent"]["stroke"], constants.SHEET_LINE_MM["extent"], base["extent"]["stroke-dasharray"]))
    if data.extent_ring:
        lines.append('<path d="%s"/>' % _ring_d(data.extent_ring, frame, True))
    lines.append("</g>")
    return lines


_SUBJECT_OUTLINE = {   # 주제 path의 기본 윤곽선 — 바탕에서 뺀 지적선·건물선을 여기서 대신 그린다
    "lot": {"stroke": constants.SHEET_BASE_STYLE["parcel"]["stroke"], "stroke-width": constants.SHEET_LINE_MM["parcel"]},
    "building": {"stroke": constants.SHEET_BASE_STYLE["building"]["stroke"], "stroke-width": constants.SHEET_LINE_MM["building"]},
}


def _draw_theme(sheet_id, subject, classify_fn, entries, items, data, ctx, frame_bounds):
    # type: (int, str, object, list, list, SheetData, dict, tuple) -> tuple
    """주제 레이어 1개 — 범례 키마다 <g id="theme_<키>">(Illustrator에서 분류별 그룹). 반환 (svg 줄, 키별 수, 키별 면적·길이, 라벨 목록)."""
    frame = data.frame
    styles = {key: style for key, _, style in entries}
    counts = {key: 0 for key in styles}
    measures = {key: 0.0 for key in styles}
    paths = {key: [] for key in styles}
    labels = []
    for item in items:
        key = classify_fn(item, ctx) if classify_fn else None
        if key is None or key not in styles:
            continue
        if sheet_id in (12, 13):
            ring = [(p[0], p[1]) for p in item[:3]]
            bounds = _get_ring_bounds(ring)
            measure, d = get_ring_area(ring), _ring_d(ring, frame, True)
        else:
            bounds = _get_item_bounds(item)
            measure, d = _get_geometry_measure(item.geometry), _get_cached_path_d(item.geometry, frame, data.path_cache)
        counts[key] += 1
        measures[key] += measure
        if not d or not _intersects(bounds, frame_bounds):
            continue
        paths[key].append('<path d="%s"/>' % d)
        if sheet_id == 5 and getattr(item, "name", ""):
            labels.append(((bounds[0] + bounds[2]) * 0.5, (bounds[1] + bounds[3]) * 0.5, item.name))
    lines = ['<g id="theme" fill-rule="evenodd"%s>' % _attrs(_SUBJECT_OUTLINE.get(subject, {}))]
    for key, _, style in entries:
        if paths[key]:
            lines.append('<g id="theme_%s"%s>' % (key, _attrs(style)))
            lines += paths[key]
            lines.append("</g>")
    lines.append("</g>")
    return lines, counts, measures, labels


def _draw_labels(data, labels, sheet_id):
    # type: (SheetData, list, int) -> list
    """대상지 지번 + 주제 라벨(#5 지구명). #1은 대상지가 K100 채움이라 글자를 흰색으로."""
    ink = "white" if sheet_id == 1 else constants.SHEET_BASE_STYLE["ink"]
    lines = ['<g id="labels" fill="%s" text-anchor="middle">' % ink]
    for lot in data.target_lots if data.mode == "lots" else []:   # 구역 방식은 필지가 많아 지번을 달지 않는다
        bounds = _get_item_bounds(lot)
        labels = [((bounds[0] + bounds[2]) * 0.5, (bounds[1] + bounds[3]) * 0.5, lot.lot_number)] + labels
    for x, y, text in labels:
        mm_x, mm_y = data.frame.to_paper(x, y)
        lines.append(_text(mm_x, mm_y, text, constants.SHEET_FONT_MM["label"], **{"font-weight": "700"}))
    lines.append("</g>")
    return lines


def _draw_box(group_id, x, y, width, title, rows, swatches=None):
    # type: (str, float, float, float, str, list, dict) -> list
    """흰 박스 + 제목 + 줄들. swatches = {행 번호: 스타일}이면 그 행 앞에 색 견본."""
    row_mm, font = constants.SHEET_LEGEND_ROW_MM, constants.SHEET_FONT_MM["legend"]
    height = row_mm * (len(rows) + 1) + 4.0
    lines = ['<g id="%s" font-size="%s" fill="%s">' % (group_id, font, constants.SHEET_BASE_STYLE["ink"]),
             '<rect x="%s" y="%s" width="%s" height="%s" fill="white" fill-opacity="0.9" stroke="%s" stroke-width="0.2"/>'
             % (_fmt(x), _fmt(y), _fmt(width), _fmt(height), constants.SHEET_BASE_STYLE["muted"]),
             _text(x + 3, y + row_mm, title, font, **{"font-weight": "700"})]
    for index, row in enumerate(rows):
        row_y = y + row_mm * (index + 2)
        text_x = x + 3
        if swatches and index in swatches:
            style = dict({"fill": "none", "stroke": "none"}, **swatches[index])
            lines.append('<rect x="%s" y="%s" width="7" height="3.2"%s/>' % (_fmt(x + 3), _fmt(row_y - 2.8), _attrs(style)))
            text_x = x + 12
        lines.append(_text(text_x, row_y, row, font))
    lines.append("</g>")
    return lines, height


def _get_card_lines(sheet_id, data, items, counts, measures):
    # type: (int, SheetData, list, dict, dict) -> list
    """수치 카드 — 시트마다 쓸모 있는 요약 몇 줄. 비율은 분류된 항목 기준."""
    total_count = sum(counts.values())
    total_measure = sum(measures.values())
    lines = []
    if sheet_id == 1:
        lot_area = sum(_get_geometry_measure(lot.geometry) for lot in data.target_lots)
        if data.mode == "area":
            lines = ["구역 %s ㎡ · 안의 필지 %d" % ("{:,.0f}".format(sum(get_ring_area(r) for r in data.site_rings)), len(data.target_lots))]
        elif data.mode == "point":
            lines = ["위치 중심 범위(대상지 경계 없음)"]
        else:
            lines = ["대상지 %d필지 · %s ㎡" % (len(data.target_lots), "{:,.1f}".format(lot_area))]
        lines += ["범위 %s" % ("용지 프레임" if data.options.get("shape") == "frame" else "반경 %s m · %s" % (data.options.get("radius", ""), data.options.get("shape", ""))),
                 "주변 필지 %d · 건물 %d동" % (len(data.near_lots), len(data.buildings))]
    elif sheet_id in (2, 3, 4, 11):
        lines = ["필지 %d · %s ㎡" % (total_count, "{:,.0f}".format(total_measure))]
        if sheet_id == 11:
            prices = [float(lot.land_price_won) for lot in items if lot.land_price_won and float(lot.land_price_won) > 0]
            if prices:
                lines += ["최고 %s · 최저 %s 만원/㎡" % (_won(max(prices)), _won(min(prices))), "평균 %s 만원/㎡" % _won(sum(prices) / len(prices))]
    elif sheet_id in (5, 6):
        lines = ["구역·시설 %d건" % total_count]
    elif sheet_id in (7, 8, 9):
        lines = ["건물 %d동 · 바닥면적 %s ㎡" % (total_count, "{:,.0f}".format(total_measure))]
        if sheet_id == 8:
            floors = [int(b.grnd_flr or 0) for b in items if int(b.grnd_flr or 0) > 0]
            if floors:
                lines.append("평균 %.1f층 · 최고 %d층" % (sum(floors) / float(len(floors)), max(floors)))
            src = data.stats.get("height_src") or {}
            if src:
                names = constants.SHEET_HEIGHT_SRC_LABELS
                lines.append("높이 출처 " + " · ".join("%s %d %%" % (names.get(k, k), round(v * 100))
                                                   for k, v in sorted(src.items(), key=lambda kv: -kv[1])))
            grade = data.stats.get("height_grade") or {}
            if grade:
                lines.append("높이 등급 " + " · ".join("%s %d %%" % (k, round(v * 100)) for k, v in sorted(grade.items())))
        if sheet_id == 9 and total_count:
            known = total_count - counts.get("unknown", 0)
            old20 = counts.get("age2", 0) + counts.get("age3", 0)
            lines.append("20년 이상 %d동 (%d %%) · 30년 이상 %d동 (%d %%)"
                         % (old20, round(100.0 * old20 / known) if known else 0, counts.get("age3", 0), round(100.0 * counts.get("age3", 0) / known) if known else 0))
            lines.append("연도 미상 %d동" % counts.get("unknown", 0))
    elif sheet_id == 10:
        lots = _get_subject_items("lot", data)
        lot_area = sum(_get_geometry_measure(lot.geometry) for lot in lots)
        road_area = sum(_get_geometry_measure(lot.geometry) for lot in lots if (lot.land_category or "") == "도로")
        road_length = sum(v for k, v in measures.items() if k.startswith("w_"))
        lines = ["도로율 %.1f %% (지목 도로 %s ㎡ / 필지 %s ㎡)" % (100.0 * road_area / lot_area if lot_area else 0.0, "{:,.0f}".format(road_area), "{:,.0f}".format(lot_area)),
                 "중심선 %.1f km · 맹지 %d필지" % (road_length / 1000.0, counts.get("landlocked", 0))]
    elif sheet_id in (12, 13):
        zs = [p[2] for tri in items for p in tri[:3]]
        lines = ["삼각형 %d · %s ㎡" % (total_count, "{:,.0f}".format(total_measure))]
        if zs:
            lines.append("표고 %.1f~%.1f m · 평균 %.1f m" % (min(zs), max(zs), sum(zs) / len(zs)))
        if sheet_id == 13 and items:
            slopes = [get_slope_deg(tri) for tri in items]
            lines.append("평균 경사 %.1f° · 최대 %.1f°" % (sum(slopes) / len(slopes), max(slopes)))
    return lines


def _draw_scale_and_north(frame):
    # type: (Frame) -> list
    width, _ = frame.paper_mm
    margin = constants.SHEET_MARGIN_MM
    bar_m = constants.SHEET_SCALE_BAR_M.get(int(frame.scale), constants.SHEET_SCALE_BAR_M[3000])
    bar_mm = bar_m * 1000.0 / frame.scale
    x1, y = width - margin - bar_mm, margin + 14.0
    ink = constants.SHEET_BASE_STYLE["ink"]
    lines = ['<g id="scale_north" fill="%s" font-size="%s">' % (ink, constants.SHEET_FONT_MM["legend"])]
    for k in range(4):
        lines.append('<rect x="%s" y="%s" width="%s" height="1.5" fill="%s" stroke="%s" stroke-width="0.2"/>'
                     % (_fmt(x1 + k * bar_mm / 4), _fmt(y), _fmt(bar_mm / 4), ink if k % 2 == 0 else "white", ink))
    lines.append(_text(x1, y - 1.5, "0", constants.SHEET_FONT_MM["legend"], **{"text-anchor": "middle"}))
    lines.append(_text(x1 + bar_mm, y - 1.5, "%g m" % bar_m, constants.SHEET_FONT_MM["legend"], **{"text-anchor": "middle"}))
    lines.append(_text(x1 - 8, y + 1.5, "1:%s" % "{:,}".format(int(frame.scale)), constants.SHEET_FONT_MM["legend"], **{"text-anchor": "end"}))
    nx, ny = width - margin - 4.0, margin + 2.0
    lines.append('<path d="M %s %s L %s %s L %s %s Z" fill="%s"/>' % (_fmt(nx), _fmt(ny), _fmt(nx - 2.5), _fmt(ny + 7), _fmt(nx + 2.5), _fmt(ny + 7), ink))
    lines.append(_text(nx, ny - 1.0, "N", constants.SHEET_FONT_MM["legend"], **{"text-anchor": "middle", "font-weight": "700"}))
    lines.append("</g>")
    return lines


def _draw_meta(data, sheet_id, name):
    # type: (SheetData, int, str) -> list
    """좌상단: 제목 + 여백 5줄(meta_lines) + 출처 1줄."""
    margin, muted = constants.SHEET_MARGIN_MM, constants.SHEET_BASE_STYLE["muted"]
    meta_lines = list(data.meta_lines) or ["자료기준 — (meta_lines 없음)"]
    sources = " · ".join("%s %s" % (getattr(s, "name", ""), getattr(s, "reference_date", "")) for s in data.sources)
    meta_lines.append("출처: " + (sources or "(없음)"))
    # 제목·메타가 지도 위에 바로 얹히면 읽기 어렵다 — 범례 박스와 같은 흰 띠를 깐다
    band_height = margin + 10.0 + (len(meta_lines) - 1) * 3.2 + 2.0
    lines = ['<g id="meta" fill="%s" font-size="%s">' % (constants.SHEET_BASE_STYLE["ink"], constants.SHEET_FONT_MM["meta"]),
             '<rect x="0" y="0" width="%.2f" height="%.2f" fill="white" fill-opacity="0.9" stroke="none"/>'
             % (constants.SHEET_META_BAND_WIDTH_MM, band_height),
             _text(margin, margin + 5.0, "%02d %s%s" % (sheet_id, name, " — " + data.lot_name if data.lot_name else ""),
                   constants.SHEET_FONT_MM["title"], **{"font-weight": "700"})]
    for index, line in enumerate(meta_lines):
        lines.append(_text(margin, margin + 10.0 + index * 3.2, line, constants.SHEET_FONT_MM["meta"], fill=muted))
    lines.append("</g>")
    return lines


def _hatch_defs():
    # type: () -> str
    """SHEET_HATCH → <pattern id="hatch_<키>"> 45° 사선(mm 단위, 모든 시트 공통 — 바이트 몇 백뿐)."""
    parts = []
    for key, spec in constants.SHEET_HATCH.items():
        step = spec["spacing_mm"]
        parts.append('<pattern id="hatch_%s" patternUnits="userSpaceOnUse" width="%s" height="%s">'
                     '<path d="M0 %sL%s 0" stroke="%s" stroke-width="%s"/></pattern>' % (key, step, step, step, step, spec["stroke"], spec["stroke-width"]))
    return "".join(parts)


def render_sheet(sheet_id, name, classify_fn, legend, data):
    # type: (int, str, object, tuple, SheetData) -> tuple
    """시트 한 장의 SVG 문자열과 (empty, reason). 데이터 없는 시트도 바탕만으로 그린다."""
    frame = data.frame
    width, height = frame.paper_mm
    frame_bounds = frame.world_bounds()
    subject = legend[0]
    items = _get_subject_items(subject, data)
    ctx, entries = _get_sheet_context(sheet_id, data, items)

    theme_lines, counts, measures, labels = _draw_theme(sheet_id, subject, classify_fn, entries, items, data, ctx, frame_bounds)
    empty = classify_fn is not None and sum(counts.values()) == 0 and not (subject == "target_lot" and data.mode == "point")   # 위치 방식 #1은 범위만으로 쓴다
    reason = ("지형 없음" if subject == "terrain" else "데이터 없음") if empty else ""

    body = ['<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" viewBox="0 0 %s %s" font-family="%s">'
            % (_fmt(width), _fmt(height), _fmt(width), _fmt(height), constants.SHEET_FONT_FAMILY),
            "<!-- %02d %s | 1:%d | center E %.1f N %.1f | EPSG:5186 -->" % (sheet_id, name, frame.scale, frame.center[0], frame.center[1]),
            '<defs><clipPath id="frame_clip"><rect x="0" y="0" width="%s" height="%s"/></clipPath>%s</defs>' % (_fmt(width), _fmt(height), _hatch_defs()),
            '<rect x="0" y="0" width="%s" height="%s" fill="white"/>' % (_fmt(width), _fmt(height)),
            '<g id="map" clip-path="url(#frame_clip)">']
    base_lines = _draw_base(data, frame_bounds, subject)
    body += (theme_lines + base_lines) if subject == "terrain" else (base_lines + theme_lines)   # 지형 채색은 건물·도로면 아래
    body += _draw_overlay_lines(data, frame_bounds, subject)
    body += _draw_labels(data, labels, sheet_id)
    body.append("</g>")

    margin, row_mm = constants.SHEET_MARGIN_MM, constants.SHEET_LEGEND_ROW_MM
    total = sum(counts.values())
    total_measure = sum(measures.values())
    rows, swatches = [], {}
    for index, (key, label, style) in enumerate(entries):
        share = (100.0 * measures[key] / total_measure) if total_measure else 0.0
        rows.append("%s  %d (%.0f %%)" % (label, counts[key], share))
        swatches[index] = style
    legend_width = constants.SHEET_BOX_WIDTH_MM["legend"]
    legend_height = row_mm * (len(rows) + 1) + 4.0
    body += _draw_box("legend", margin, height - margin - legend_height, legend_width, "범례 (%s %d)" % (name, total), rows, swatches)[0]
    card_rows = _get_card_lines(sheet_id, data, items, counts, measures)
    card_width = constants.SHEET_BOX_WIDTH_MM["card"]
    card_height = row_mm * (len(card_rows) + 1) + 4.0
    body += _draw_box("card", width - margin - card_width, height - margin - card_height, card_width, "수치", card_rows)[0]
    body += _draw_meta(data, sheet_id, name)
    body += _draw_scale_and_north(frame)
    body.append('<g id="frame"><rect x="0" y="0" width="%s" height="%s" fill="none" stroke="%s" stroke-width="%s"/></g>'
                % (_fmt(width), _fmt(height), constants.SHEET_BASE_STYLE["ink"], constants.SHEET_LINE_MM["frame"]))
    body.append("</svg>")
    return "\n".join(body), empty, reason


def get_sheet_file_name(sheet_id, name):
    # type: (int, str) -> str
    return "%02d_%s.svg" % (sheet_id, re.sub(r"[^0-9A-Za-z가-힣]", "", name))


def write_sheets(data, out_dir, sheet_ids=None, options=None):
    # type: (SheetData, str, list, dict) -> list
    """시트들을 out_dir에 쓴다. 반환 [{id, name, path, empty, reason}] (panel_ui.md done.sheets 모양)."""
    if options:
        data.options = dict(data.options, **options)
    wanted = set(int(v) for v in (sheet_ids or [sheet[0] for sheet in SHEETS]))
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for sheet_id, name, classify_fn, legend in SHEETS:
        if sheet_id not in wanted:
            continue
        svg, empty, reason = render_sheet(sheet_id, name, classify_fn, legend, data)
        path = os.path.join(out_dir, get_sheet_file_name(sheet_id, name))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        results.append({"id": sheet_id, "name": name, "path": path, "empty": empty, "reason": reason})
    return results
