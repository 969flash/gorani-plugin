"""현황도·분석도 SVG 작성기 — 공통 템플릿 + 사용자 도면 스타일. docs/deliverables.md §B·§C, docs/panel_ui.md(style).

Rhino 금지. origin을 모른다 — 입력은 전부 EPSG:5186 세계좌표 m이고 Frame이 지도 칸 mm로 바꾼다.
템플릿: 용지(A3 가로 기준, 다른 용지는 비례 확대) = 지도 칸 + 정보 열(side) | 정보 띠(bottom) | 지도만(map).
지도 칸 크기와 축척이 Frame이다(레이아웃이 바뀌면 SheetData.get_frame이 다시 계산).
스타일: get_style(options) — STYLE_PRESETS 위에 options['style']을 덮는다. 색은 도면 요소별, 선·글자·흐리기·레이아웃은 전 도면 공통.
Seoungsu make_basemap_L.py의 path_of/geom_paths/save_svg를 geopandas 없이 이식했다.

    SheetData.from_prepared(prepared, terrain_tris_world) → write_sheets(data, out_dir, sheet_ids, options)
    → [{id, name, path, empty, reason}]
    render_sheet(sheet_id, data) → (svg, empty, reason)   — 패널 '도면 스타일' 미리보기도 이것
"""

import base64
import datetime
import heapq
import math
import os
import re
import statistics
import struct
import zlib
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

import constants
from non_rhino_utils import get_polygon_parts_from_geojson, get_ring_area, get_text_width_em, is_point_in_ring

SHEET_NAMES = {sheet_id: name for sheet_id, _key, name, _en, _needs in constants.SHEET_CATALOG}
SHEET_KEYS = {sheet_id: key for sheet_id, key, _name, _en, _needs in constants.SHEET_CATALOG}
SHEET_SUBTITLES = {sheet_id: en for sheet_id, _key, _name, en, _needs in constants.SHEET_CATALOG}
_HEX = re.compile(r"#[0-9A-Fa-f]{6}$")
_LABEL_SKIP = re.compile(constants.SHEET_LABEL_SKIP_PATTERN)


class Frame:
    """지도 칸 한 장 ↔ 세계좌표. 종이 원점은 칸 좌상단, y는 아래로 (SVG 규약)."""

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
        """세계 m → 종이 mm. (E − E0)/S × 1000 을 칸 중심 기준으로 둔다."""
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
        """(min_x, min_y, max_x, max_y) — 칸이 덮는 세계좌표 범위."""
        half_w, half_h = self.width_m * 0.5, self.height_m * 0.5
        return (self.center[0] - half_w, self.center[1] - half_h, self.center[0] + half_w, self.center[1] + half_h)


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
# 스타일·색·템플릿
# ─────────────────────────────────────────────

def get_style(options):
    # type: (dict) -> dict
    """options['style'](사용자가 바꾼 값) → 완전한 스타일 dict.

    입력: 패널 옵션 dict(없어도 된다). 처리: STYLE_DEFAULTS ← STYLE_PRESETS[preset] ← 사용자 값(형식이 맞는 것만 — 색 #RRGGBB,
    선택지 안의 값, 범위 안의 수). 출력: STYLE_COLOR_KEYS 10색 + ramp + STYLE_DEFAULTS 키 + preset·name.
    """
    user = dict((options or {}).get("style") or {})
    preset = user.get("preset") if user.get("preset") in constants.STYLE_PRESETS else constants.STYLE_DEFAULT_PRESET
    style = dict(constants.STYLE_DEFAULTS)
    style.update(constants.STYLE_PRESETS[preset])
    style["preset"] = preset
    for key, value in user.items():
        if key in constants.STYLE_COLOR_KEYS:
            if isinstance(value, str) and _HEX.match(value):
                style[key] = value.upper()
        elif key in constants.STYLE_CHOICES:
            if value in constants.STYLE_CHOICES[key]:
                style[key] = value
        elif key in constants.STYLE_RANGES:
            low, high = constants.STYLE_RANGES[key]
            try:
                style[key] = min(high, max(low, float(value)))
            except (TypeError, ValueError):
                pass
        elif key in ("labels", "subtitle_en"):
            style[key] = bool(value)
        elif key in ("project", "name"):
            style[key] = str(value or "").strip()[:constants.STYLE_PROJECT_MAX]
    return style


def _get_rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def get_mixed_color(color_a, color_b, t):
    # type: (str, str, float) -> str
    """#RRGGBB 두 색을 t(0 = a, 1 = b)로 섞는다."""
    a, b = _get_rgb(color_a), _get_rgb(color_b)
    return "#%02X%02X%02X" % tuple(int(round(x + (y - x) * t)) for x, y in zip(a, b))


def is_dark(color):
    # type: (str) -> bool
    r, g, b = _get_rgb(color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0 < 0.4


def get_ramp(style, n):
    # type: (dict, int) -> list
    """스타일 단계색 6단 → n단(선형 보간). 종이가 어두우면 뒤집는다 — 어두운 바탕에서는 밝을수록 높은 값."""
    stops = list(constants.STYLE_RAMPS[style["ramp"]])
    if is_dark(style["paper"]):
        stops.reverse()
    if n <= 1:
        return stops[1:2] * max(n, 0)   # 한 단계뿐이면 옅은 쪽 — 진한 한 색이 도면을 덮지 않게
    colors = []
    for i in range(n):
        position = i * (len(stops) - 1) / float(n - 1)
        low = int(math.floor(position))
        high = min(low + 1, len(stops) - 1)
        colors.append(get_mixed_color(stops[low], stops[high], position - low))
    return colors


def get_sheet_scales(scales):
    # type: (list) -> list
    """도면 축척 후보 — 베이스맵 축척(options.scales)과 표준 축척(BASEMAP_SCALES) 합집합, 오름차순.
    .ai 용지 프레임보다 도면 지도 칸이 작아(A3 정사각 273 mm) 범위가 안 들어가면 한 단계 큰 축척으로 간다."""
    return sorted(set(int(s) for s in scales or []) | set(constants.BASEMAP_SCALES))


def get_sheet_query_bounds(paper_mm, scales, center, ring):
    # type: (tuple, list, tuple, list) -> tuple
    """도면이 쓸 가장 큰 축척(side·bottom 레이아웃 중)의 용지 전체 범위 — prepare가 DB 질의 범위에 합친다(지도 칸 가장자리가 비지 않게)."""
    scale = max(get_frame_for_ring(get_map_box(paper_mm, layout)[2:], get_sheet_scales(scales), center, ring).scale for layout in ("side", "bottom"))
    return Frame(paper_mm, scale, center).world_bounds()


def get_template_scale(paper_mm):
    # type: (tuple) -> float
    """A3 가로(420×297) 기준 템플릿 치수의 배율."""
    return min(float(paper_mm[0]) / 420.0, float(paper_mm[1]) / 297.0)


def get_map_box(paper_mm, layout):
    # type: (tuple, str) -> tuple
    """용지 위 지도 칸 (x, y, w, h) mm. side = 오른쪽 정보 열, bottom = 아래 정보 띠, map = 용지 전체."""
    width, height = float(paper_mm[0]), float(paper_mm[1])
    k, t = get_template_scale(paper_mm), constants.SHEET_TEMPLATE_MM
    margin, gap = t["margin"] * k, t["gap"] * k
    if layout == "map":
        return (0.0, 0.0, width, height)
    if layout == "bottom":
        return (margin, margin, width - 2 * margin, height - 2 * margin - gap - t["strip"] * k)
    return (margin, margin, width - 2 * margin - gap - t["column"] * k, height - 2 * margin)


@dataclass
class SheetData:
    """시트 작성기 입력. 좌표는 전부 세계좌표 m. lot은 lot_db.LotInfo, building·feature는 context_db 데이터클래스.

    terrain_tris: [((x, y, z), (x, y, z), (x, y, z), class_name)] — context_geometry.build_terrain이 세계좌표로 되돌린 것.
    meta_lines: 여백 5줄(context_report.get_meta_lines). sources: DataSource 목록(출처 1줄). options: 패널 옵션(style 포함).
    """

    paper_mm: tuple = (420.0, 297.0)
    scales: list = field(default_factory=lambda: [5000])
    center: tuple = (0.0, 0.0)
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
    frame: object = None                               # 마지막으로 계산한 지도 칸 Frame
    path_cache: dict = field(default_factory=dict, repr=False)   # id(geometry) → path d. 16장이 같은 필지·건물·도로를 다시 그리지 않게(2026-10-08: 5.1 s의 80 %)
    frame_key: tuple = field(default=None, repr=False)
    cache: dict = field(default_factory=dict, repr=False)     # 시트 사이에 나눠 쓰는 계산(블록·보행망·썸네일 격자)

    def get_frame(self, layout):
        # type: (str) -> Frame
        """레이아웃의 지도 칸 Frame. 칸 크기가 바뀌면 축척을 다시 고르고 path 캐시를 비운다."""
        box = get_map_box(self.paper_mm, layout)
        key = (round(box[2], 3), round(box[3], 3))
        if key != self.frame_key:
            self.frame = get_frame_for_ring((box[2], box[3]), get_sheet_scales(self.scales), self.center, self.extent_ring)
            self.path_cache = {}
            self.frame_key = key
        return self.frame

    @classmethod
    def from_prepared(cls, prepared, terrain_tris_world=None):
        # type: (object, list) -> SheetData
        """context_builder.Prepared → SheetData. 지도 중심은 대상지 중심(prepared.center), 축척은 범위 링이 들어가는 가장 작은 축척(없으면 최대)."""
        options = prepared.request.get("options") or {}
        center = getattr(prepared, "center", None)
        if center is None:   # 예전 Prepared(필지만) — 대상 필지 bbox 중심
            lots_bounds = [_get_item_bounds(lot) for lot in prepared.target_lots]
            center = ((min(b[0] for b in lots_bounds) + max(b[2] for b in lots_bounds)) * 0.5,
                      (min(b[1] for b in lots_bounds) + max(b[3] for b in lots_bounds)) * 0.5)
        paper_mm = options.get("paper_mm") or constants.PAPER_SIZES_MM[options.get("paper", "A3")]
        return cls(
            paper_mm=tuple(float(v) for v in paper_mm), scales=sorted(prepared.scales or [max(constants.BASEMAP_SCALES)]), center=tuple(center),
            target_lots=list(prepared.target_lots), near_lots=list(prepared.near_lots),
            buildings=list(prepared.buildings), features=list(prepared.features), overlays=list(prepared.overlays),
            extent_ring=list(prepared.extent_ring), terrain_tris=list(terrain_tris_world or []),
            meta_lines=list((prepared.meta or {}).get("meta_lines") or []), sources=list(prepared.sources),
            options=dict(options), stats=dict(prepared.stats or {}), lot_name=prepared.lot_name,
            mode=getattr(prepared, "mode", "lots"), site_rings=[list(r) for r in getattr(prepared, "site_rings", None) or []],
        )


# ─────────────────────────────────────────────
# 분류 함수 — 항목 하나 → 범례 키(None이면 그리지 않음). ctx는 options·데이터 의존 구간을 담는 dict
# ─────────────────────────────────────────────

def classify_target(lot, ctx):
    # type: (object, dict) -> str
    return "target"


def classify_figure(building, ctx):
    # type: (object, dict) -> str
    return "bld"


def classify_station(feature, ctx):
    # type: (object, dict) -> str
    return "station"


def classify_green(item, ctx):
    # type: (object, dict) -> str
    """필지(지목 공원·체육·유원지 = 공원, 임야 = 녹지, 하천·구거·유지 = 수계), 도시계획시설(공원·녹지), 수치지형도(녹지·수면)."""
    category = getattr(item, "land_category", None)
    if category is not None:
        if category in constants.LAND_CATEGORIES_WATER:
            return "water"
        if constants.SHEET_LAND_CATEGORY_KEYS.get(category) == "park":
            return "park"
        return "green" if category == "임야" else None
    theme, kind = getattr(item, "theme", ""), getattr(item, "kind", "")
    if theme == constants.OVERLAY_THEME_FACILITY:
        return "park" if kind == "공원" else ("green" if kind == "녹지" else None)
    if theme == "green":
        return "green"
    if theme == "water" and kind in constants.WATER_SURFACE_KINDS:
        return "water"
    return None


def get_lot_area(lot):
    # type: (object) -> float
    """대장 면적(registered_area), 없으면 형상 면적."""
    return float(getattr(lot, "registered_area", 0) or 0) or _get_geometry_measure(lot.geometry)


def classify_lot_size(lot, ctx):
    # type: (object, dict) -> str
    """필지 면적 구간. 도로·하천 필지는 조직(그레인)이 아니라 뺀다."""
    if lot.land_category == constants.LAND_CATEGORY_ROAD or lot.land_category in constants.LAND_CATEGORIES_WATER:
        return None
    area = get_lot_area(lot)
    for index, upper in enumerate(constants.SHEET_LOT_SIZE_BREAKS):
        if area < upper:
            return "a%d" % index
    return "a%d" % len(constants.SHEET_LOT_SIZE_BREAKS)


def classify_density(block, ctx):
    # type: (object, dict) -> str
    for index, upper in enumerate(constants.SHEET_DENSITY_BREAKS):
        if block.far < upper:
            return "d%d" % index
    return "d%d" % len(constants.SHEET_DENSITY_BREAKS)


def classify_walk(edge, ctx):
    # type: (object, dict) -> str
    return "m%d" % edge.band


def classify_public(item, ctx):
    # type: (object, dict) -> str
    """건물(대장 용도 → 수치지형도 용도) · 필지(학교용지) · UPIS 시설(광장·공공공지·정류장)."""
    if hasattr(item, "usability"):
        return constants.SHEET_PUBLIC_USE.get((item.usability or "")[:2]) or constants.SHEET_PUBLIC_NGII.get(getattr(item, "ngii_use", "") or "")
    if hasattr(item, "land_category"):
        return "school_lot" if item.land_category == "학교용지" else None
    if getattr(item, "theme", "") == constants.OVERLAY_THEME_FACILITY:
        return constants.SHEET_PUBLIC_FACILITY.get(item.kind or "")
    return None


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


# 시트 키 → (분류 함수, 바탕 방식). 바탕 full = 스타일 색 그대로, faded = 종이 쪽으로 흐림, figure = 종이 + 옅은 수계만. 틀은 분류 없음
SHEETS = {
    "base": (classify_target, "full"), "figure": (classify_figure, "figure"), "transit": (classify_station, "faded"),
    "lot_size": (classify_lot_size, "faded"), "density": (classify_density, "faded"), "walk": (classify_walk, "faded"),
    "public": (classify_public, "faded"), "view": (None, "faded"), "image": (None, "faded"), "synthesis": (None, "faded"),
    "green": (classify_green, "faded"), "road": (classify_road, "faded"), "land_use": (classify_land_use, "faded"),
    "land_category": (classify_land_category, "faded"), "zone": (classify_zone, "faded"), "district": (classify_district, "faded"),
    "facility": (classify_facility, "faded"), "use": (classify_use, "faded"), "floor": (classify_floor, "faded"),
    "age": (classify_age, "faded"), "price": (classify_price, "faded"), "elev": (classify_elev, "faded"), "slope": (classify_slope, "faded"),
}


# ─────────────────────────────────────────────
# 블록·보행망 — 시트 사이에 나눠 쓰는 계산(SheetData.cache)
# ─────────────────────────────────────────────

class Block(object):
    """가구(블록) 하나 — 도로 필지 구멍 링. far·bcr은 안쪽 건물(bbox 중심) 연면적·바닥면적 합 / 블록 면적 %."""

    def __init__(self, ring, area, footprint, floor_area, count):
        self.geometry = {"type": "Polygon", "coordinates": [ring]}
        self.area, self.footprint, self.floor_area, self.count = area, footprint, floor_area, count
        self.far = 100.0 * floor_area / area if area else 0.0
        self.bcr = 100.0 * footprint / area if area else 0.0


class WalkEdge(object):
    """보행망 한 조각(같은 시간대가 이어진 중심선 구간). band = SHEET_WALK_MINUTES 순번."""

    def __init__(self, coords, band, length):
        self.geometry = {"type": "LineString", "coordinates": coords}
        self.band, self.length = band, length


def _get_cells(bounds, size):
    for gx in range(int(math.floor(bounds[0] / size)), int(math.floor(bounds[2] / size)) + 1):
        for gy in range(int(math.floor(bounds[1] / size)), int(math.floor(bounds[3] / size)) + 1):
            yield gx, gy


def get_blocks(data):
    # type: (SheetData) -> list
    """도로 필지(가로망이 한 필지인 도넛)의 구멍 = 블록. 블록마다 안쪽 건물의 바닥면적·연면적 합.

    처리: 구멍 링 중 SHEET_BLOCK_MIN_AREA 이상 → 100 m 격자 버킷 → 건물 bbox 중심이 든 블록(첫 하나)에 더한다.
    연면적이 비면(0) 바닥면적 × 지상층수로 어림. 출력: [Block] (캐시)."""
    if "blocks" in data.cache:
        return data.cache["blocks"]
    rings = []
    for lot in _get_subject_items("lot", data):
        if lot.land_category != constants.LAND_CATEGORY_ROAD:
            continue
        for part in get_polygon_parts_from_geojson(lot.geometry):
            rings += [[(float(p[0]), float(p[1])) for p in hole] for hole in part[1:] if get_ring_area(hole) >= constants.SHEET_BLOCK_MIN_AREA]
    buckets, size = {}, 100.0
    for index, ring in enumerate(rings):
        for cell in _get_cells(_get_ring_bounds(ring), size):
            buckets.setdefault(cell, []).append(index)
    sums = [[0.0, 0.0, 0] for _ in rings]
    for building in data.buildings:
        x, y = _get_item_center(building)
        for index in buckets.get((int(math.floor(x / size)), int(math.floor(y / size))), ()):
            if is_point_in_ring(x, y, rings[index]):
                footprint = float(getattr(building, "footprint_area", 0) or 0) or _get_geometry_measure(building.geometry)
                floor_area = float(getattr(building, "total_area", 0) or 0) or footprint * max(1, int(building.grnd_flr or 0))
                sums[index][0] += footprint
                sums[index][1] += floor_area
                sums[index][2] += 1
                break
    data.cache["blocks"] = [Block(ring, get_ring_area(ring), *total) for ring, total in zip(rings, sums)]
    return data.cache["blocks"]


def get_walk(data):
    # type: (SheetData) -> dict
    """대상지 중심에서 도로 중심선 네트워크를 따라 걷는 거리(Dijkstra, 표준 라이브러리 heapq).

    처리: 중심선 정점을 SHEET_WALK_SNAP_M 격자로 맞춰 그래프 → 중심 SHEET_WALK_START_M 안 정점(없으면 가장 가까운 정점)에서 출발,
    출발 거리 = 직선 거리 → 15분 거리까지 → 중심선마다 같은 시간대 구간을 이어 WalkEdge. 역은 가장 가까운 정점(100 m 안)의 거리.
    출력: {edges: [WalkEdge], lengths: {band: m}, stations: [(분, 이름)]} (캐시)."""
    if "walk" in data.cache:
        return data.cache["walk"]
    snap, speed = constants.SHEET_WALK_SNAP_M, constants.SHEET_WALK_SPEED_M_PER_MIN
    limit = max(constants.SHEET_WALK_MINUTES) * speed
    key = lambda p: (int(round(p[0] / snap)), int(round(p[1] / snap)))
    lines, graph = [], {}
    for f in data.features:
        if f.theme != "road" or f.kind != "centerline":
            continue
        kind, coords = f.geometry.get("type"), f.geometry.get("coordinates") or []
        for line in ([coords] if kind == "LineString" else coords if kind == "MultiLineString" else []):
            pts = [(float(p[0]), float(p[1])) for p in line]
            lines.append(pts)
            for a, b in zip(pts, pts[1:]):
                length = math.hypot(b[0] - a[0], b[1] - a[1])
                graph.setdefault(key(a), []).append((key(b), length))
                graph.setdefault(key(b), []).append((key(a), length))
    cx, cy = data.center
    nodes = {node: math.hypot(node[0] * snap - cx, node[1] * snap - cy) for node in graph}
    starts = {node: d for node, d in nodes.items() if d <= constants.SHEET_WALK_START_M}
    if not starts and nodes:
        node = min(nodes, key=nodes.get)
        starts = {node: nodes[node]}
    dist, heap = dict(starts), [(d, node) for node, d in starts.items()]
    heapq.heapify(heap)
    while heap:
        d, node = heapq.heappop(heap)
        if d > dist.get(node, float("inf")) or d > limit:
            continue
        for other, length in graph[node]:
            nd = d + length
            if nd < dist.get(other, float("inf")):
                dist[other] = nd
                heapq.heappush(heap, (nd, other))

    def band_of(distance):
        for index, minutes in enumerate(constants.SHEET_WALK_MINUTES):
            if distance <= minutes * speed:
                return index
        return None

    edges, lengths = [], {}
    for pts in lines:
        run, run_band = [], None
        for a, b in zip(pts, pts[1:]):
            da, db = dist.get(key(a)), dist.get(key(b))
            band = band_of(max(da, db)) if da is not None and db is not None else None
            if band != run_band:
                if run_band is not None and len(run) > 1:
                    edges.append(WalkEdge(run, run_band, _get_geometry_measure({"type": "LineString", "coordinates": run})))
                run, run_band = [a], band
            if band is not None:
                run.append(b)
                lengths[band] = lengths.get(band, 0.0) + math.hypot(b[0] - a[0], b[1] - a[1])
        if run_band is not None and len(run) > 1:
            edges.append(WalkEdge(run, run_band, _get_geometry_measure({"type": "LineString", "coordinates": run})))
    stations = []
    for station in _get_stations(data):
        sx, sy = station.geometry["coordinates"][:2]
        near = [(math.hypot(n[0] * snap - sx, n[1] * snap - sy), n) for n in dist]
        if near:
            gap, node = min(near)
            if gap <= 100.0:
                stations.append(((dist[node] + gap) / speed, station.name))
    data.cache["walk"] = {"edges": edges, "lengths": lengths, "stations": sorted(stations)}
    return data.cache["walk"]


# ─────────────────────────────────────────────
# 좌표·형상 유틸 (GeoJSON dict → SVG path d)
# ─────────────────────────────────────────────

def _fmt(value):
    return "%.2f" % value


def _get_clip_rect(frame):
    # type: (Frame) -> tuple
    """지도 칸 + 여유(SHEET_CLIP_MARGIN_MM) 사각형 (min_x, min_y, max_x, max_y) mm."""
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
    """세계좌표 점열 → path d. 면은 지도 칸 사각형으로 자르고, 0.01 mm 정수로 반올림한 뒤 상대좌표(l)로 쓴다 — 누적 오차 없음.

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
    """GeoJSON Polygon·MultiPolygon·LineString·MultiLineString → path d(한 path에 링 전부, evenodd). 그 외·칸 밖은 ""."""
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


def _circle_d(cx, cy, r):
    # type: (float, float, float) -> str
    """종이 mm 원 → path d(호 두 개)."""
    return "M%s %sa%s %s 0 1 0 %s 0a%s %s 0 1 0 %s 0Z" % (_fmt(cx - r), _fmt(cy), _fmt(r), _fmt(r), _fmt(2 * r), _fmt(r), _fmt(r), _fmt(-2 * r))


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


def _get_item_center(item):
    b = _get_item_bounds(item)
    return ((b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5)


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
    return '<text x="%s" y="%s" font-size="%s"%s>%s</text>' % (_fmt(x), _fmt(y), _fmt(size), _attrs(extra), escape(str(content)))


def get_wrapped_lines(text, width_mm, size_mm):
    # type: (str, float, float) -> list
    """글자 폭 어림(get_text_width_em)으로 width_mm 안에 들어가게 줄을 나눈다. 공백에서 먼저, 긴 낱말은 글자 단위로."""
    max_em = width_mm / size_mm
    lines, current = [], ""
    for word in str(text).split(" "):
        candidate = word if not current else current + " " + word
        if get_text_width_em(candidate) <= max_em:
            current = candidate
            continue
        if current:
            lines.append(current)
        while get_text_width_em(word) > max_em and len(word) > 1:
            cut = len(word)
            while cut > 1 and get_text_width_em(word[:cut]) > max_em:
                cut -= 1
            lines.append(word[:cut])
            word = word[cut:]
        current = word
    if current:
        lines.append(current)
    return lines


# ─────────────────────────────────────────────
# 범례(동적 시트)와 분류 컨텍스트
# ─────────────────────────────────────────────

def _won(value):
    return "{:,}".format(int(round(value / 10000.0)))


def _get_sheet_context(key, data, style, items):
    # type: (str, SheetData, dict, list) -> tuple
    """(ctx, entries, extras). entries = 분류 키 범례(개수·비율을 단다), extras = 바탕 요소 범례(개수 없음) [(라벨, 견본 스타일)].
    고정 범례 시트는 constants 표 그대로, 나머지는 스타일 색·단계색·데이터로 만든다."""
    _subject, entries = constants.SHEET_LEGENDS[key]
    ctx = {"options": data.options, "year": int(data.options.get("today_year") or datetime.date.today().year)}
    muted = get_mixed_color(style["ink"], style["paper"], 0.45)
    unknown = ("unknown", "미상", {"fill": style["paper"], "stroke": muted})
    site = {"fill": "none", "stroke": style["site"], "stroke-width": constants.SHEET_LINE_MM["site"]}
    extent = {"fill": "none", "stroke": style["extent"], "stroke-width": constants.SHEET_LINE_MM["extent"], "stroke-dasharray": "2 1.2"}
    extras = []
    if key == "base":
        entries = [("target", "대상지", {"fill": style["site"], "fill-opacity": "0.3", "stroke": style["site"]})]
        extras = [("분석 범위", extent), ("건축물", {"fill": style["building"], "stroke": get_mixed_color(style["building"], style["ink"], 0.3)}),
                  ("도로", {"fill": style["road"], "stroke": muted}), ("녹지·공원", {"fill": style["green"]}), ("수계", {"fill": style["water"]}),
                  ("철도", {"fill": "none", "stroke": style["rail"], "stroke-width": constants.SHEET_LINE_MM["rail"]})]
    elif key == "figure":
        entries = [("bld", "건축물", {"fill": style["ink"]})]
        extras = [("외부공간", {"fill": style["paper"], "stroke": muted}), ("대상지", site), ("분석 범위", extent)]
    elif key == "transit":
        color = constants.SHEET_TRANSIT_COLOR
        entries = [("station", "지하철역", {"shape": "circle", "fill": style["paper"], "stroke": style["ink"], "stroke-width": constants.SHEET_LINE_MM["station"]})]
        r1, r2 = constants.SHEET_TRANSIT_RADII_M
        extras = [("철도 노선", {"fill": "none", "stroke": color, "stroke-width": 0.7}),
                  ("1차 역세권 (%d m)" % r1, {"fill": color, "fill-opacity": "0.16", "stroke": color, "stroke-width": 0.3}),
                  ("2차 역세권 (%d m)" % r2, {"fill": "none", "stroke": color, "stroke-width": 0.3, "stroke-dasharray": "1.5 1"}),
                  ("대상지", site)]
    elif key in ("lot_size", "density"):
        breaks = constants.SHEET_LOT_SIZE_BREAKS if key == "lot_size" else constants.SHEET_DENSITY_BREAKS
        unit, prefix = ("㎡", "a") if key == "lot_size" else ("%", "d")
        labels = ["%s %s 미만" % ("{:,.0f}".format(breaks[0]), unit)] + \
                 ["%s~%s %s" % ("{:,.0f}".format(breaks[i - 1]), "{:,.0f}".format(breaks[i]), unit) for i in range(1, len(breaks))] + \
                 ["%s %s 이상" % ("{:,.0f}".format(breaks[-1]), unit)]
        if key == "lot_size":
            labels[0] += " (과소필지)"
        ramp = get_ramp(style, len(labels))
        entries = [("%s%d" % (prefix, i), label, {"fill": ramp[i]}) for i, label in enumerate(labels)]
    elif key == "walk":
        speed = constants.SHEET_WALK_SPEED_M_PER_MIN
        entries = [("m%d" % i, "%d분 (%s m)" % (minutes, "{:,.0f}".format(minutes * speed)),
                    {"fill": "none", "stroke": constants.SHEET_WALK_COLORS[i], "stroke-width": _fmt(1.0 - 0.2 * i), "stroke-linecap": "round"})
                   for i, minutes in enumerate(constants.SHEET_WALK_MINUTES)]
        extras = [("대상지", site)]
    elif key == "floor":
        breaks = tuple(constants.SHEET_FLOOR_BANDS_FIXED) + tuple(data.options.get("floor_breaks") or constants.FLOOR_BREAKS_DEFAULT)
        ctx["floor_breaks"] = breaks
        labels, lower = [], 1
        for upper in breaks:
            labels.append("%d층" % upper if upper == lower else "%d~%d층" % (lower, upper))
            lower = upper + 1
        labels.append("%d층 이상" % lower)
        ramp = get_ramp(style, len(labels))
        entries = [("f%d" % i, label, {"fill": ramp[i]}) for i, label in enumerate(labels)] + [unknown]
    elif key == "age":
        bands = constants.AGE_BANDS_YEARS
        labels = ["%d년 미만" % bands[0]] + ["%d~%d년" % (bands[i - 1], bands[i] - 1) for i in range(1, len(bands))] + ["%d년 이상" % bands[-1]]
        ramp = get_ramp(style, len(labels))
        entries = [("age%d" % i, label, {"fill": ramp[i]}) for i, label in enumerate(labels)] + [("unknown", "연도 미상", unknown[2])]
    elif key == "price":
        prices = sorted(float(lot.land_price_won) for lot in items if lot.land_price_won and float(lot.land_price_won) > 0)
        breaks = statistics.quantiles(prices, n=constants.SHEET_PRICE_QUANTILES) if len(prices) >= 2 else []
        ctx["price_breaks"] = breaks
        edges = [prices[0] if prices else 0.0] + list(breaks) + [prices[-1] if prices else 0.0]
        ramp = get_ramp(style, len(breaks) + 1)
        entries = [("p%d" % i, "%s~%s 만원/㎡" % (_won(edges[i]), _won(edges[i + 1])), {"fill": ramp[i]}) for i in range(len(breaks) + 1)] + [unknown]
    elif key == "elev":
        step = constants.ELEV_PRESETS.get(data.options.get("elev_preset"), list(constants.ELEV_PRESETS.values())[0])
        zs = [p[2] for tri in items for p in tri[:3]]
        if zs:
            bands = lambda size: int(math.floor(max(zs) / size)) - int(math.floor(min(zs) / size)) + 1
            if bands(step) < constants.ELEV_MIN_BANDS:   # 평탄지(성수 10.6~14.1 m)는 20 m 한 단계라 읽을 게 없다 — 단계를 줄인다
                step = next((size for size in constants.ELEV_FINE_STEPS if bands(size) >= constants.ELEV_MIN_BANDS), constants.ELEV_FINE_STEPS[-1])
                ctx["elev_auto"] = True
            low, high = int(math.floor(min(zs) / step)), int(math.floor(max(zs) / step))
            ramp = get_ramp(style, high - low + 1)
            entries = [("e%d" % k, "%g~%g m" % (k * step, (k + 1) * step), {"fill": ramp[k - low], "stroke": ramp[k - low], "stroke-width": "0.15"})
                       for k in range(low, high + 1)]
        ctx["elev_step"] = step
    return ctx, entries, extras


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
    if subject == "station":
        return _get_stations(data)
    if subject == "green":
        return list(data.features) + _get_subject_items("lot", data) + list(data.overlays)
    if subject == "block":
        return get_blocks(data)
    if subject == "walk":
        return get_walk(data)["edges"]
    if subject == "public":
        return _get_subject_items("lot", data) + list(data.overlays) + list(data.buildings)
    return []


def _get_stations(data):
    return [f for f in data.features if f.theme == "transit" and f.kind == "station" and (f.geometry or {}).get("type") == "Point"]


# ─────────────────────────────────────────────
# 그리기 — 지도 칸
# ─────────────────────────────────────────────

def _get_cached_path_d(geometry, frame, cache):
    # type: (dict, Frame, dict) -> str
    """get_path_d를 SheetData.path_cache로 한 번만 계산한다(같은 Frame 안에서만 쓴다)."""
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


def _get_base_colors(style, base_mode):
    # type: (dict, str) -> dict
    """바탕 방식별 실제 색 — faded는 종이 쪽으로 SHEET_FADE_TO_PAPER만큼, figure는 종이 + 옅은 수계."""
    paper = style["paper"]
    colors = {key: style[key] for key in ("block", "road", "green", "water", "building", "rail")}
    if base_mode == "faded":
        colors = {key: get_mixed_color(value, paper, constants.SHEET_FADE_TO_PAPER) for key, value in colors.items()}
    elif base_mode == "figure":
        colors = {"block": paper, "road": paper, "green": paper, "water": get_mixed_color(style["water"], paper, 0.5), "building": paper, "rail": paper}
    colors["building_stroke"] = get_mixed_color(colors["building"], style["ink"], 0.3)
    return colors


def _draw_base(data, style, base_mode, frame, frame_bounds, skip_buildings):
    # type: (SheetData, dict, str, Frame, tuple, bool) -> list
    """바탕(배경 사각형 다음): 도로면 → 수계 → 녹지 → 철도 → 건물. 도로면은 지목 도로 필지 ∪ 수치지형도 도로면.
    건물이 주제면 base_buildings는 빈 그룹 — 주제 path가 윤곽선까지 맡는다."""
    colors = _get_base_colors(style, base_mode)
    lots = _get_subject_items("lot", data)
    water = [f for f in data.features if f.theme == "water" and f.kind in constants.WATER_SURFACE_KINDS] + \
            [lot for lot in lots if lot.land_category in constants.LAND_CATEGORIES_WATER]
    road = [f for f in data.features if f.theme == "road" and f.kind == "surface"] + [lot for lot in lots if lot.land_category == constants.LAND_CATEGORY_ROAD]
    green, rail = [], []
    if base_mode != "figure":
        green = [f for f in data.features if f.theme == "green"] + \
                [lot for lot in lots if constants.SHEET_LAND_CATEGORY_KEYS.get(lot.land_category) in ("park", "forest")] + \
                [o for o in data.overlays if o.theme == constants.OVERLAY_THEME_FACILITY and o.kind in constants.BM_GREEN_FACILITY_KINDS]
        rail = [f for f in data.features if f.theme == "rail" and f.kind in ("line", "centerline")]
    ls, cache = style["line_scale"], data.path_cache
    lines = []
    lines += _draw_items([] if base_mode == "figure" else road, frame, {"fill": colors["road"], "fill-rule": "evenodd"}, "base_road", frame_bounds, cache)
    lines += _draw_items(water, frame, {"fill": colors["water"], "fill-rule": "evenodd"}, "base_water", frame_bounds, cache)
    lines += _draw_items(green, frame, {"fill": colors["green"], "fill-rule": "evenodd"}, "base_green", frame_bounds, cache)
    lines += _draw_items(rail, frame, {"fill": "none", "stroke": colors["rail"], "stroke-width": _fmt(constants.SHEET_LINE_MM["rail"] * ls)}, "base_rail", frame_bounds, cache)
    lines += _draw_items([] if skip_buildings or base_mode == "figure" else data.buildings, frame,
                         {"fill": colors["building"], "stroke": colors["building_stroke"], "stroke-width": _fmt(constants.SHEET_LINE_MM["building"] * ls),
                          "fill-rule": "evenodd"}, "base_buildings", frame_bounds, cache)
    return lines


def _get_subject_outline(subject, style):
    # type: (str, dict) -> dict
    """주제 path의 기본 윤곽선 — 바탕에서 뺀 지적선·건물선을 여기서 대신 그린다."""
    ls, ink, paper = style["line_scale"], style["ink"], style["paper"]
    if subject == "lot":
        return {"stroke": get_mixed_color(ink, paper, 0.55), "stroke-width": _fmt(constants.SHEET_LINE_MM["parcel"] * ls)}
    if subject == "building":
        return {"stroke": get_mixed_color(ink, paper, 0.6), "stroke-width": _fmt(constants.SHEET_LINE_MM["building"] * ls)}
    return {}


def _draw_theme(key, subject, classify_fn, entries, items, data, style, frame, frame_bounds):
    # type: (str, str, object, list, list, SheetData, dict, Frame, tuple) -> tuple
    """주제 레이어 1개 — 범례 키마다 <g id="theme_<키>">(Illustrator에서 분류별 그룹). 반환 (svg 줄, 키별 수, 키별 면적·길이, 라벨 목록)."""
    styles = {entry_key: entry_style for entry_key, _, entry_style in entries}
    counts = {entry_key: 0 for entry_key in styles}
    measures = {entry_key: 0.0 for entry_key in styles}
    paths = {entry_key: [] for entry_key in styles}
    labels = []
    ctx = data.options.get("_ctx") or {}
    for item in items:
        entry_key = classify_fn(item, ctx) if classify_fn else None
        if entry_key is None or entry_key not in styles:
            continue
        if subject == "terrain":
            ring = [(p[0], p[1]) for p in item[:3]]
            bounds = _get_ring_bounds(ring)
            measure, d = get_ring_area(ring), _ring_d(ring, frame, True)
        else:
            bounds = _get_item_bounds(item)
            measure, d = _get_geometry_measure(item.geometry), _get_cached_path_d(item.geometry, frame, data.path_cache)
        if not _intersects(bounds, frame_bounds):
            continue
        counts[entry_key] += 1
        measures[entry_key] += measure
        if not d:
            continue
        paths[entry_key].append('<path d="%s"/>' % d)
        if key == "district" and getattr(item, "name", ""):
            labels.append(((bounds[0] + bounds[2]) * 0.5, (bounds[1] + bounds[3]) * 0.5, item.name))
    outline = {} if key == "figure" else _get_subject_outline(subject, style)
    lines = ['<g id="theme" fill-rule="evenodd"%s>' % _attrs(outline)]
    for entry_key, _, entry_style in entries:
        if paths[entry_key]:
            lines.append('<g id="theme_%s"%s>' % (entry_key, _attrs(entry_style)))
            lines += paths[entry_key]
            lines.append("</g>")
    lines.append("</g>")
    return lines, counts, measures, labels


def _draw_transit(key, subject, classify_fn, entries, items, data, style, frame, frame_bounds):
    # type: (str, str, object, list, list, SheetData, dict, Frame, tuple) -> tuple
    """역세권 — 역마다 2차(파선)·1차(옅은 칠) 원, 철도 노선 강조. 역 표시는 라벨 층이 맡는다(라벨을 꺼도 이 시트는 그린다)."""
    color, ls = constants.SHEET_TRANSIT_COLOR, style["line_scale"]
    r1, r2 = constants.SHEET_TRANSIT_RADII_M
    near = (frame_bounds[0] - r2, frame_bounds[1] - r2, frame_bounds[2] + r2, frame_bounds[3] + r2)
    stations = [s for s in items if _intersects(_get_item_bounds(s), near)]
    in_frame = [s for s in stations if _intersects(_get_item_bounds(s), frame_bounds)]

    def circles(radius):
        r_mm = radius * 1000.0 / frame.scale
        return ['<path d="%s"/>' % _circle_d(*(frame.to_paper(*s.geometry["coordinates"][:2]) + (r_mm,))) for s in stations]

    rail = [f for f in data.features if f.theme == "rail" and f.kind in ("line", "centerline")]
    lines = ['<g id="theme">',
             '<g id="theme_catch2" fill="none" stroke="%s" stroke-width="%s" stroke-dasharray="1.5 1">' % (color, _fmt(0.3 * ls))] + circles(r2) + ["</g>",
             '<g id="theme_catch1" fill="%s" fill-opacity="0.16" stroke="%s" stroke-width="%s">' % (color, color, _fmt(0.3 * ls))] + circles(r1) + ["</g>"]
    lines += _draw_items(rail, frame, {"fill": "none", "stroke": color, "stroke-width": _fmt(0.7 * ls)}, "theme_rail", frame_bounds, data.path_cache)
    lines.append("</g>")
    return lines, {"station": len(in_frame)}, {"station": float(len(in_frame))}, []


def _draw_template(key, subject, classify_fn, entries, items, data, style, frame, frame_bounds):
    # type: (str, str, object, list, list, SheetData, dict, Frame, tuple) -> tuple
    """직접 그리는 틀 — 범례 키마다 빈 <g id="theme_<키>">(Illustrator·.ai에서 빈 레이어). 개수는 0."""
    lines = ['<g id="theme">'] + ['<g id="theme_%s"%s></g>' % (k, _attrs({a: v for a, v in s.items() if a != "shape"})) for k, _, s in entries] + ["</g>"]
    return lines, {k: 0 for k, _, _ in entries}, {k: 0.0 for k, _, _ in entries}, []


THEME_DRAWERS = {"transit": _draw_transit, "view": _draw_template, "image": _draw_template, "synthesis": _draw_template}


def _draw_mask(frame, extent_ring, style):
    # type: (Frame, list, dict) -> list
    """분석 범위 밖을 종이색으로 덮어(투명도 fade_outside) 범위 안에 시선이 가게 한다."""
    if not extent_ring or style["fade_outside"] <= 0:
        return []
    w, h, m = frame.paper_mm[0], frame.paper_mm[1], constants.SHEET_CLIP_MARGIN_MM
    outer = "M%s %sH%sV%sH%sZ" % (_fmt(-m), _fmt(-m), _fmt(w + m), _fmt(h + m), _fmt(-m))
    return ['<path id="mask" fill="%s" fill-opacity="%s" fill-rule="evenodd" d="%s%s"/>'
            % (style["paper"], _fmt(style["fade_outside"]), outer, _ring_d(extent_ring, frame, True))]


def _get_range_label(data):
    # type: (SheetData) -> str
    shape = data.options.get("shape", "")
    if shape == "frame":
        return "용지 프레임"
    if shape == "site":
        return "그린 경계"
    return "반경 %s m" % data.options.get("radius", "")


def _draw_overlay_lines(data, style, frame, frame_bounds, subject, key, k):
    # type: (SheetData, dict, Frame, tuple, str, str, float) -> list
    """지적선(1:3000 이하 도면, 필지 주제가 아닐 때) · 범위 링 + 라벨 · 대상지 경계."""
    ls, ink, paper = style["line_scale"], style["ink"], style["paper"]
    lines = []
    show_parcels = frame.scale <= constants.SHEET_PARCEL_MAX_SCALE and subject != "lot"
    lines += _draw_items(data.near_lots if show_parcels else [], frame,
                         {"fill": "none", "stroke": get_mixed_color(ink, paper, 0.6), "stroke-width": _fmt(constants.SHEET_LINE_MM["parcel"] * ls)},
                         "base_parcels", frame_bounds, data.path_cache)
    lines.append('<g id="extent" fill="none" stroke="%s" stroke-width="%s" stroke-dasharray="2 1.2">'
                 % (style["extent"], _fmt(constants.SHEET_LINE_MM["extent"] * ls)))
    if data.extent_ring:
        lines.append('<path d="%s"/>' % _ring_d(data.extent_ring, frame, True))
    lines.append("</g>")
    if data.extent_ring and data.options.get("shape") != "frame":
        top = max(data.extent_ring, key=lambda p: p[1])
        x, y = frame.to_paper(top[0], top[1])
        if 0 < y < frame.paper_mm[1]:
            lines.append(_text(x, y - 1.5 * k, _get_range_label(data), constants.SHEET_FONT_MM["small"] * k * style["text_scale"],
                               fill=style["extent"], **{"text-anchor": "middle", "font-weight": "600", "id": "extent_label"}))
    site_style = {"fill": "none", "stroke": style["site"], "stroke-width": _fmt(constants.SHEET_LINE_MM["site"] * ls), "stroke-linejoin": "round"}
    if data.site_rings:   # 대상지 경계(구역·필지 외곽). 예전 데이터(경계 없음)는 대상 필지 형상
        lines.append('<g id="site"%s>' % _attrs(site_style))
        lines += ['<path d="%s"/>' % _ring_d(ring, frame, True) for ring in data.site_rings]
        lines.append("</g>")
    else:
        lines += _draw_items(data.target_lots, frame, site_style, "site", frame_bounds, data.path_cache)
    return lines


def _draw_labels(data, style, frame, labels, key, k):
    # type: (SheetData, dict, Frame, list, str, float) -> list
    """지명·역명(스타일 labels), 역 표시(역세권 시트는 항상), 대상지 지번(필지 방식), 주제 라벨(용도지구명)."""
    ts, ink, paper = style["text_scale"], style["ink"], style["paper"]
    muted = get_mixed_color(ink, paper, 0.45)
    size = constants.SHEET_FONT_MM["label"] * k * ts
    halo = {"paint-order": "stroke", "stroke": paper, "stroke-width": _fmt(0.5 * k), "stroke-linejoin": "round"}
    w, h = frame.paper_mm
    lines = ['<g id="labels" text-anchor="middle">']
    if style["labels"]:
        seen = set()
        for f in data.features:
            if f.theme != "label" or f.kind != "place" or not f.name or (f.geometry or {}).get("type") != "Point" or _LABEL_SKIP.search(f.name):
                continue
            name = f.name.strip().strip("()")
            if name in seen:
                continue
            seen.add(name)
            x, y = frame.to_paper(*f.geometry["coordinates"][:2])
            if 3 * k < x < w - 3 * k and 3 * k < y < h - 3 * k:
                lines.append(_text(x, y, name, size, fill=muted, **dict(halo, **{"font-weight": "500"})))
    if style["labels"] or key == "transit":
        radius = 1.5 * k
        lines.append('<g id="stations" fill="%s" stroke="%s" stroke-width="%s">' % (paper, ink, _fmt(constants.SHEET_LINE_MM["station"] * style["line_scale"])))
        names = []
        for s in _get_stations(data):
            x, y = frame.to_paper(*s.geometry["coordinates"][:2])
            if -radius < x < w + radius and -radius < y < h + radius:
                lines.append('<circle cx="%s" cy="%s" r="%s"/>' % (_fmt(x), _fmt(y), _fmt(radius)))
                if style["labels"] or key == "transit":
                    names.append(_text(x + radius + 1.0 * k, y + size * 0.35, s.name, size, fill=ink,
                                       **dict(halo, **{"font-weight": "700", "text-anchor": "start"})))
        lines.append("</g>")
        lines += names
    for lot in data.target_lots if data.mode == "lots" else []:   # 구역 방식은 필지가 많아 지번을 달지 않는다
        x, y = frame.to_paper(*_get_item_center(lot))
        lines.append(_text(x, y, lot.lot_number, size, fill=ink, **dict(halo, **{"font-weight": "700"})))
    for x, y, text in labels:
        mm_x, mm_y = frame.to_paper(x, y)
        lines.append(_text(mm_x, mm_y, text, size, fill=ink, **dict(halo, **{"font-weight": "700"})))
    lines.append("</g>")
    return lines


# ─────────────────────────────────────────────
# 수치 카드
# ─────────────────────────────────────────────

def _get_inside(items, ring):
    # type: (list, list) -> list
    """bbox 중심이 링 안에 있는 항목 — 범위 안 집계용(형상 교차보다 싸고, 반경 수백 m에서 차이가 작다)."""
    if not ring:
        return list(items)
    bounds = _get_ring_bounds(ring)
    inside = []
    for item in items:
        x, y = _get_item_center(item)
        if bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3] and is_point_in_ring(x, y, ring):
            inside.append(item)
    return inside


def _get_card_lines(key, data, items, counts, measures, ctx=None):
    # type: (str, SheetData, list, dict, dict, dict) -> list
    """수치 카드 — 시트마다 쓸모 있는 요약 몇 줄. 비율은 분류된 항목 기준."""
    total_count = sum(counts.values())
    total_measure = sum(measures.values())
    ctx = ctx or {}
    fmt0 = "{:,.0f}".format
    lines = []
    if key == "base":
        lot_area = sum(_get_geometry_measure(lot.geometry) for lot in data.target_lots)
        if data.mode == "area":
            lines = ["구역 %s ㎡ · 안의 필지 %d" % (fmt0(sum(get_ring_area(r) for r in data.site_rings)), len(data.target_lots))]
        elif data.mode == "point":
            lines = ["위치 중심 범위(대상지 경계 없음)"]
        else:
            lines = ["대상지 %d필지 · %s ㎡" % (len(data.target_lots), "{:,.1f}".format(lot_area))]
        lines += ["범위 %s · %s ㎡" % (_get_range_label(data), fmt0(get_ring_area(data.extent_ring) if data.extent_ring else 0.0)),
                  "범위 안 건물 %s동" % fmt0(len(_get_inside(data.buildings, data.extent_ring)))]
    elif key == "figure":
        inside = _get_inside(data.buildings, data.extent_ring)
        footprint = sum(_get_geometry_measure(b.geometry) for b in inside)
        area = get_ring_area(data.extent_ring) if data.extent_ring else 0.0
        lines = ["범위 안 건물 %s동" % fmt0(len(inside))]
        if area:
            lines.append("건물 바닥면적 비율 %.1f %%" % (100.0 * footprint / area))
        if inside:
            lines.append("평균 바닥면적 %s ㎡" % fmt0(footprint / len(inside)))
    elif key == "transit":
        cx, cy = data.center
        distances = sorted((math.hypot(s.geometry["coordinates"][0] - cx, s.geometry["coordinates"][1] - cy), s.name) for s in items)
        r1, r2 = constants.SHEET_TRANSIT_RADII_M
        if distances:
            lines = ["가장 가까운 역 %s %s m" % (distances[0][1], fmt0(distances[0][0])),
                     "%d m 안 역 %d · %d m 안 역 %d" % (r1, sum(1 for d, _ in distances if d <= r1), r2, sum(1 for d, _ in distances if d <= r2))]
        else:
            lines = ["도면 안 지하철역 없음"]
        lines.append("대상지 중심 기준 직선거리")
    elif key == "green":
        lines = ["도면 안 공원 %d · 녹지 %d · 수계 %d" % (counts.get("park", 0), counts.get("green", 0), counts.get("water", 0))]
        area = get_ring_area(data.extent_ring) if data.extent_ring else 0.0
        if area:
            green = [item for item in _get_inside(items, data.extent_ring) if classify_green(item, {}) in ("park", "green")]
            green_area = sum(_get_geometry_measure(item.geometry) for item in green)
            lines.append("범위 안 공원·녹지 %s ㎡ (%.1f %%, 중심점 기준)" % (fmt0(green_area), 100.0 * green_area / area))
    elif key == "lot_size":
        areas = sorted(get_lot_area(lot) for lot in items if classify_lot_size(lot, {}) is not None and _intersects(_get_item_bounds(lot), data.frame.world_bounds()))
        small = counts.get("a0", 0)
        lines = ["필지 %d · 과소필지(90 ㎡ 미만) %d (%d %%)" % (total_count, small, round(100.0 * small / total_count) if total_count else 0)]
        if areas:
            lines.append("면적 중앙값 %s ㎡ · 평균 %s ㎡" % (fmt0(statistics.median(areas)), fmt0(sum(areas) / len(areas))))
        lines.append("도로·하천 필지 제외, 대장 면적 기준")
    elif key == "density":
        inside = _get_inside(items, data.extent_ring)
        area = sum(b.area for b in inside)
        if area:
            lines = ["범위 안 블록 %d · 평균 용적률 %d %% · 건폐율 %d %%" % (len(inside), round(100.0 * sum(b.floor_area for b in inside) / area),
                                                                 round(100.0 * sum(b.footprint for b in inside) / area))]
        else:
            lines = ["블록 경계 없음 — 도로 필지에 구멍(가구)이 없다"]
        lines.append("블록 = 도로 필지 구멍 · 건물 = 대장 연면적(없으면 바닥면적×층수)")
    elif key == "walk":
        walk = get_walk(data)
        speed = constants.SHEET_WALK_SPEED_M_PER_MIN
        lines = [" · ".join("%d분 %.1f km" % (minutes, measures.get("m%d" % i, 0.0) / 1000.0) for i, minutes in enumerate(constants.SHEET_WALK_MINUTES)) + " (도면 안 도로)"]
        if walk["stations"]:
            minutes, name = walk["stations"][0]
            lines.append("가장 가까운 역 %s 보행 %d분" % (name, int(math.ceil(minutes))))
        lines.append("대상지 중심 %d m 안 도로에서 출발 · %d m/분" % (constants.SHEET_WALK_START_M, speed))
    elif key == "public":
        lines = ["교육 %d · 의료·노유자 %d · 문화·체육 %d동" % (counts.get("education", 0), counts.get("welfare", 0), counts.get("culture", 0)),
                 "학교 부지 %d · 광장·공공공지 %d" % (counts.get("school_lot", 0), counts.get("plaza", 0)),
                 "건축물대장 용도 기준 — 공공청사는 업무시설과 섞여 따로 구분하지 않는다"]
    elif key in constants.SHEET_TEMPLATE_KEYS:
        lines = ["직접 그리는 틀 — 범례 레이어마다 Illustrator에서 그린다",
                 {"view": "조망점: 근경 250 m · 중경 500 m · 원경, 눈높이 1.5 m", "image": "케빈 린치 도시 이미지 5요소",
                  "synthesis": "현황도를 겹쳐 제약과 기회를 나눠 적는다"}[key]]
    elif key in ("land_use", "land_category", "zone", "price"):
        lines = ["필지 %d · %s ㎡" % (total_count, fmt0(total_measure))]
        if key == "price":
            prices = [float(lot.land_price_won) for lot in items if lot.land_price_won and float(lot.land_price_won) > 0]
            if prices:
                lines += ["최고 %s · 최저 %s 만원/㎡" % (_won(max(prices)), _won(min(prices))), "평균 %s 만원/㎡" % _won(sum(prices) / len(prices))]
    elif key in ("district", "facility"):
        lines = ["구역·시설 %d건" % total_count]
    elif key in ("use", "floor", "age"):
        lines = ["건물 %d동 · 바닥면적 %s ㎡" % (total_count, fmt0(total_measure))]
        if key == "floor":
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
        if key == "age" and total_count:
            known = total_count - counts.get("unknown", 0)
            old20 = counts.get("age2", 0) + counts.get("age3", 0)
            lines.append("20년 이상 %d동 (%d %%) · 30년 이상 %d동 (%d %%)"
                         % (old20, round(100.0 * old20 / known) if known else 0, counts.get("age3", 0), round(100.0 * counts.get("age3", 0) / known) if known else 0))
            lines.append("연도 미상 %d동" % counts.get("unknown", 0))
    elif key == "road":
        lots = _get_subject_items("lot", data)
        lot_area = sum(_get_geometry_measure(lot.geometry) for lot in lots)
        road_area = sum(_get_geometry_measure(lot.geometry) for lot in lots if (lot.land_category or "") == "도로")
        road_length = sum(v for k, v in measures.items() if k.startswith("w_"))
        lines = ["도로율 %.1f %% (지목 도로 %s ㎡ / 필지 %s ㎡)" % (100.0 * road_area / lot_area if lot_area else 0.0, fmt0(road_area), fmt0(lot_area)),
                 "중심선 %.1f km · 맹지 %d필지" % (road_length / 1000.0, counts.get("landlocked", 0))]
    elif key in ("elev", "slope"):
        zs = [p[2] for tri in items for p in tri[:3]]
        lines = ["삼각형 %d · %s ㎡" % (total_count, fmt0(total_measure))]
        if zs:
            lines.append("표고 %.1f~%.1f m · 평균 %.1f m" % (min(zs), max(zs), sum(zs) / len(zs)))
        if key == "elev" and ctx.get("elev_step"):
            lines.append("단계 %g m%s" % (ctx["elev_step"], " (평탄지라 자동으로 줄임)" if ctx.get("elev_auto") else ""))
        if key == "slope" and items:
            slopes = [get_slope_deg(tri) for tri in items]
            lines.append("평균 경사 %.1f° · 최대 %.1f°" % (sum(slopes) / len(slopes), max(slopes)))
    return lines


# ─────────────────────────────────────────────
# 그리기 — 정보 열·띠
# ─────────────────────────────────────────────

def _draw_swatch(x, y, w, h, swatch):
    # type: (float, float, float, float, dict) -> str
    """범례 견본 — shape circle이면 원(역), 칠이 없는 선 스타일이면 가로선, 아니면 사각형."""
    if swatch.get("shape") == "circle":
        circle = {k: v for k, v in swatch.items() if k != "shape"}
        return '<circle cx="%s" cy="%s" r="%s"%s/>' % (_fmt(x + w * 0.5), _fmt(y + h * 0.5), _fmt(h * 0.45), _attrs(circle))
    if swatch.get("fill") == "none" and "stroke" in swatch:
        line = {k: v for k, v in swatch.items() if k != "fill"}
        return '<line x1="%s" y1="%s" x2="%s" y2="%s"%s/>' % (_fmt(x), _fmt(y + h * 0.5), _fmt(x + w), _fmt(y + h * 0.5), _attrs(line))
    rect = dict({"stroke": "none"}, **swatch)
    rect.setdefault("stroke-width", 0.25)
    return '<rect x="%s" y="%s" width="%s" height="%s"%s/>' % (_fmt(x), _fmt(y), _fmt(w), _fmt(h), _attrs(rect))


def _draw_scale_north(x, y, frame, style, k):
    # type: (float, float, Frame, dict, float) -> list
    """축척 막대(0·¼·½·1, 3칸) + 방위표. (x, y) = 막대 왼쪽 위."""
    ink, paper, ts = style["ink"], style["paper"], style["text_scale"]
    bar_m = constants.SHEET_SCALE_BAR_M.get(int(frame.scale), round(frame.scale / 10.0, -1))
    unit = bar_m * 1000.0 / frame.scale
    size = 2.0 * k * ts
    lines = ['<g id="scale_north" fill="%s">' % ink]
    for i, (a, b) in enumerate(((0.0, 0.25), (0.25, 0.5), (0.5, 1.0))):
        lines.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s" stroke="%s" stroke-width="0.2"/>'
                     % (_fmt(x + a * unit), _fmt(y), _fmt((b - a) * unit), _fmt(1.4 * k), ink if i % 2 == 0 else paper, ink))
    for t in (0.0, 0.25, 0.5, 1.0):
        lines.append(_text(x + t * unit, y - 1.2 * k, "%g" % (bar_m * t), size, **{"text-anchor": "middle"}))
    lines.append(_text(x + unit + 2.0 * k, y + 1.4 * k, "m", size))
    nx, ny = x + unit + 12.0 * k, y - 3.0 * k
    lines.append('<path d="M%s %sL%s %sL%s %sL%s %sZ"/>' % (_fmt(nx), _fmt(ny - 5 * k), _fmt(nx + 2.6 * k), _fmt(ny + 3 * k),
                                                           _fmt(nx), _fmt(ny + 1.6 * k), _fmt(nx - 2.6 * k), _fmt(ny + 3 * k)))
    lines.append(_text(nx, ny - 6.3 * k, "N", size * 1.2, **{"text-anchor": "middle", "font-weight": "700"}))
    lines.append("</g>")
    return lines


def _get_meta_lines(data):
    # type: (SheetData) -> list
    """여백 줄(context_report.get_meta_lines — 자료기준·출처·좌표계·정합·경고). 출처 줄은 끌 수 없다."""
    return list(data.meta_lines) or ["자료기준 — (meta_lines 없음)"]


def _get_paper_label(paper_mm):
    for name, size in constants.PAPER_SIZES_MM.items():
        if (round(paper_mm[0]), round(paper_mm[1])) == tuple(size):
            return name
    return "%d×%d mm" % (round(paper_mm[0]), round(paper_mm[1]))


def _get_legend_rows(entries, extras, counts, measures):
    # type: (list, list, dict, dict) -> list
    """[(견본, 라벨, 값)] — 분류 키는 '개수 · 비율 %', 바탕 요소는 값 없음."""
    total_measure = sum(measures.values())
    rows = []
    for entry_key, label, swatch in entries:
        share = (100.0 * measures[entry_key] / total_measure) if total_measure else 0.0
        count = "{:,}".format(counts[entry_key])
        rows.append((swatch, label, count if len(entries) == 1 else "%s · %.0f %%" % (count, share)))
    rows += [(swatch, label, "") for label, swatch in extras]
    return rows


def _draw_head(x, y, sheet_id, name, style, k, avail_w):
    # type: (float, float, int, str, dict, float, float) -> tuple
    """번호 + 영문 부제 + 제목. 반환 (svg 줄, 제목 아래 y)."""
    ts, ink, muted = style["text_scale"], style["ink"], get_mixed_color(style["ink"], style["paper"], 0.45)
    fonts = constants.SHEET_FONT_MM
    number_size = fonts["number"] * k * ts
    number = "%02d" % sheet_id
    offset = get_text_width_em(number) * number_size * 1.05 + 3.0 * k
    title_size = fonts["title"] * k * ts
    room = avail_w - offset
    if get_text_width_em(name) * title_size > room:
        title_size = room / max(get_text_width_em(name), 1.0)
    lines = [_text(x, y + number_size * 0.82, number, number_size, fill=style["site"], **{"font-weight": "800", "id": "sheet_number"})]
    if style["subtitle_en"]:
        lines.append(_text(x + offset, y + number_size * 0.82 - title_size * 1.15, SHEET_SUBTITLES[sheet_id].upper(), fonts["subtitle"] * k * ts,
                           fill=muted, **{"font-weight": "600", "letter-spacing": _fmt(0.25 * k)}))
    lines.append(_text(x + offset, y + number_size * 0.82, name, title_size, fill=ink, **{"font-weight": "800", "id": "sheet_title"}))
    return lines, y + number_size + 2.0 * k


def _draw_info_side(data, style, sheet_id, name, frame, box, legend_rows, card_rows):
    # type: (SheetData, dict, int, str, Frame, tuple, list, list) -> list
    """오른쪽 정보 열: 제목 → 대상지·프로젝트 → 범례 → 주요 수치 / 아래부터 출처·자료기준 → 축척·방위."""
    k = get_template_scale(data.paper_mm)
    t, fonts, ts = constants.SHEET_TEMPLATE_MM, constants.SHEET_FONT_MM, style["text_scale"]
    ink, muted = style["ink"], get_mixed_color(style["ink"], style["paper"], 0.45)
    x = box[0] + box[2] + t["gap"] * k
    w = data.paper_mm[0] - t["margin"] * k - x
    y = t["margin"] * k
    lines = ['<g id="info" fill="%s">' % ink]
    head, y = _draw_head(x, y, sheet_id, name, style, k, w)
    lines += head
    lines.append('<rect x="%s" y="%s" width="%s" height="%s" fill="%s"/>' % (_fmt(x), _fmt(y), _fmt(w), _fmt(0.35 * k), ink))
    body, head_size, row = fonts["body"] * k * ts, fonts["head"] * k * ts, constants.SHEET_LEGEND_ROW_MM * k * ts
    y += 6.0 * k * ts
    lines.append(_text(x, y, "%s · %s" % ((data.lot_name or "").replace("_", " "), _get_range_label(data)), body, **{"font-weight": "600"}))
    if style["project"]:
        y += row * 0.9
        lines.append(_text(x, y, style["project"], body, fill=muted))
    y += row * 1.8
    lines.append('<g id="legend">')
    lines.append(_text(x, y, "범례", head_size, **{"font-weight": "700"}))
    y += 2.0 * k
    lines.append('<rect x="%s" y="%s" width="%s" height="0.2" fill="%s"/>' % (_fmt(x), _fmt(y), _fmt(w), muted))
    y += row * 0.9
    for swatch, label, value in legend_rows:
        lines.append(_draw_swatch(x, y - 2.7 * k * ts, 7.0 * k, 3.4 * k * ts, swatch))
        lines.append(_text(x + 10.0 * k, y, label, body))
        if value:
            lines.append(_text(x + w, y, value, fonts["small"] * k * ts, fill=muted, **{"text-anchor": "end"}))
        y += row
    lines.append("</g>")
    if card_rows:
        y += row * 0.8
        lines.append('<g id="card">')
        lines.append(_text(x, y, "주요 수치", head_size, **{"font-weight": "700"}))
        y += 2.0 * k
        lines.append('<rect x="%s" y="%s" width="%s" height="0.2" fill="%s"/>' % (_fmt(x), _fmt(y), _fmt(w), muted))
        y += row * 0.9
        for card in card_rows:
            for piece in get_wrapped_lines(card, w, body):
                lines.append(_text(x, y, piece, body))
                y += row * 0.85
        lines.append("</g>")
    # 아래부터 — 맨 아래 도구 줄, 그 위 자료기준·출처, 그 위 축척 줄, 축척 막대
    meta_size = fonts["meta"] * k * ts
    meta = []
    for text in _get_meta_lines(data):
        meta += get_wrapped_lines(text, w, meta_size)
    meta.append("%s · 정보제공용, 법적 효력 없음" % constants.TOOL_NAME)
    yy = data.paper_mm[1] - t["margin"] * k
    lines.append('<g id="meta" fill="%s">' % muted)
    for text in reversed(meta):
        lines.append(_text(x, yy, text, meta_size))
        yy -= meta_size * 1.45
    lines.append("</g>")
    yy -= 2.0 * k
    lines.append(_text(x, yy, "1:%s · %s · EPSG:5186" % ("{:,}".format(int(frame.scale)), _get_paper_label(data.paper_mm)),
                       fonts["small"] * k * ts, **{"font-weight": "600", "id": "scale_text"}))
    lines += _draw_scale_north(x + 1.0 * k, yy - 9.0 * k, frame, style, k)
    lines.append("</g>")
    return lines


def _draw_info_bottom(data, style, sheet_id, name, frame, box, legend_rows, card_rows):
    # type: (SheetData, dict, int, str, Frame, tuple, list, list) -> list
    """아래 정보 띠: [제목·대상지] [범례 여러 열] [수치·축척·출처]."""
    k = get_template_scale(data.paper_mm)
    t, fonts, ts = constants.SHEET_TEMPLATE_MM, constants.SHEET_FONT_MM, style["text_scale"]
    ink, muted = style["ink"], get_mixed_color(style["ink"], style["paper"], 0.45)
    left, top = t["margin"] * k, box[1] + box[3] + t["gap"] * k
    right = data.paper_mm[0] - t["margin"] * k
    strip_h = data.paper_mm[1] - t["margin"] * k - top
    title_w, side_w, gap = 100.0 * k, 118.0 * k, 8.0 * k
    lines = ['<g id="info" fill="%s">' % ink]
    head, y = _draw_head(left, top, sheet_id, name, style, k, title_w)
    lines += head
    body = fonts["body"] * k * ts
    lines.append(_text(left, y + body, "%s · %s" % ((data.lot_name or "").replace("_", " "), _get_range_label(data)), body, **{"font-weight": "600"}))
    if style["project"]:
        lines.append(_text(left, y + body * 2.4, style["project"], body, fill=muted))
    # 범례 — 칸 수는 남는 폭, 행 수는 띠 높이에 맞춘다
    legend_x, legend_w = left + title_w + gap, right - side_w - gap - (left + title_w + gap)
    columns = max(1, int(legend_w // (56.0 * k)))
    per_column = max(1, int(math.ceil(len(legend_rows) / float(columns))))
    row = min(4.6 * k * ts, (strip_h - 2.0 * k) / per_column)
    size = min(body, row * 0.62)
    lines.append('<g id="legend">')
    for i, (swatch, label, value) in enumerate(legend_rows):
        cx = legend_x + (i // per_column) * (legend_w / columns)
        cy = top + row * (i % per_column) + row * 0.75
        lines.append(_draw_swatch(cx, cy - size * 0.95, 6.0 * k, size * 1.2, swatch))
        lines.append(_text(cx + 8.0 * k, cy, label + ("  " + value if value else ""), size))
    lines.append("</g>")
    side_x = right - side_w
    yy = top + body
    lines.append('<g id="card">')
    for card in card_rows[:3]:
        for piece in get_wrapped_lines(card, side_w, fonts["small"] * k * ts)[:1]:
            lines.append(_text(side_x, yy, piece, fonts["small"] * k * ts))
            yy += fonts["small"] * k * ts * 1.5
    lines.append("</g>")
    meta_size = fonts["meta"] * k * ts
    meta = []
    for text in _get_meta_lines(data)[:2]:
        meta += get_wrapped_lines(text, side_w, meta_size)
    meta.append("%s · 정보제공용, 법적 효력 없음 · 1:%s %s" % (constants.TOOL_NAME, "{:,}".format(int(frame.scale)), _get_paper_label(data.paper_mm)))
    yb = data.paper_mm[1] - t["margin"] * k
    lines.append('<g id="meta" fill="%s">' % muted)
    for text in reversed(meta[-4:]):
        lines.append(_text(side_x, yb, text, meta_size))
        yb -= meta_size * 1.45
    lines.append("</g>")
    lines += _draw_scale_north(side_x + 1.0 * k, yb - 3.0 * k, frame, style, k)
    lines.append("</g>")
    return lines


def _draw_info_map_only(data, style, frame):
    # type: (SheetData, dict, Frame) -> list
    """지도만: 왼쪽 아래 작은 띠 — 축척·방위와 출처 한 줄(출처 표기는 끌 수 없다)."""
    k = get_template_scale(data.paper_mm)
    meta_size = constants.SHEET_FONT_MM["meta"] * k * style["text_scale"]
    source = (_get_meta_lines(data)[1:2] or _get_meta_lines(data))[0]
    text = get_wrapped_lines("%s · %s · 1:%s" % (source, constants.TOOL_NAME, "{:,}".format(int(frame.scale))), 150.0 * k, meta_size)[:2]
    band_h = 14.0 * k + meta_size * 1.45 * len(text)
    x, y = 4.0 * k, data.paper_mm[1] - 4.0 * k - band_h
    lines = ['<g id="info" fill="%s">' % style["ink"],
             '<rect x="%s" y="%s" width="%s" height="%s" fill="%s" fill-opacity="0.92"/>' % (_fmt(x), _fmt(y), _fmt(158.0 * k), _fmt(band_h), style["paper"])]
    lines += _draw_scale_north(x + 4.0 * k, y + 8.0 * k, frame, style, k)
    yy = y + 14.0 * k
    for piece in text:
        lines.append(_text(x + 4.0 * k, yy, piece, meta_size, fill=get_mixed_color(style["ink"], style["paper"], 0.45)))
        yy += meta_size * 1.45
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


# ─────────────────────────────────────────────
# 한 장 · 여러 장
# ─────────────────────────────────────────────

def render_sheet(sheet_id, data):
    # type: (int, SheetData) -> tuple
    """시트 한 장의 SVG 문자열과 (empty, reason). 데이터 없는 시트도 바탕만으로 그린다. 스타일은 data.options['style']."""
    key, name = SHEET_KEYS[sheet_id], SHEET_NAMES[sheet_id]
    style = get_style(data.options)
    k = get_template_scale(data.paper_mm)
    width, height = data.paper_mm
    box = get_map_box(data.paper_mm, style["layout"])
    frame = data.get_frame(style["layout"])
    frame_bounds = frame.world_bounds()
    classify_fn, base_mode = SHEETS[key]
    subject = constants.SHEET_LEGENDS[key][0]
    items = _get_subject_items(subject, data)
    ctx, entries, extras = _get_sheet_context(key, data, style, items)
    drawer = THEME_DRAWERS.get(key, _draw_theme)
    data.options["_ctx"] = ctx
    try:
        theme_lines, counts, measures, labels = drawer(key, subject, classify_fn, entries, items, data, style, frame, frame_bounds)
    finally:
        data.options.pop("_ctx", None)
    empty = sum(counts.values()) == 0 and not (key == "base" and data.mode == "point") and key not in constants.SHEET_TEMPLATE_KEYS   # 위치 방식 베이스맵은 범위만으로 쓴다
    reason = ("지형 없음" if subject == "terrain" else "데이터 없음") if empty else ""

    background = style["paper"] if base_mode == "figure" else _get_base_colors(style, base_mode)["block"]
    base_lines = _draw_base(data, style, base_mode, frame, frame_bounds, skip_buildings=subject == "building")
    body = ['<svg xmlns="http://www.w3.org/2000/svg" width="%smm" height="%smm" viewBox="0 0 %s %s" font-family="%s">'
            % (_fmt(width), _fmt(height), _fmt(width), _fmt(height), escape(constants.STYLE_FONTS[style["font"]], {'"': "&quot;"})),
            "<!-- %02d %s | 1:%d | center E %.1f N %.1f | EPSG:5186 | style %s -->" % (sheet_id, name, frame.scale, frame.center[0], frame.center[1], style["preset"]),
            '<defs><clipPath id="map_clip"><rect x="0" y="0" width="%s" height="%s"/></clipPath>%s</defs>' % (_fmt(box[2]), _fmt(box[3]), _hatch_defs()),
            '<rect id="paper" x="0" y="0" width="%s" height="%s" fill="%s"/>' % (_fmt(width), _fmt(height), style["paper"]),
            '<g id="map" transform="translate(%s %s)" clip-path="url(#map_clip)">' % (_fmt(box[0]), _fmt(box[1])),
            '<rect id="map_background" x="0" y="0" width="%s" height="%s" fill="%s"/>' % (_fmt(box[2]), _fmt(box[3]), background)]
    body += (theme_lines + base_lines) if subject in ("terrain", "block") else (base_lines + theme_lines)   # 지형·블록 채색은 도로·건물 아래
    if key not in constants.SHEET_NO_MASK:
        body += _draw_mask(frame, data.extent_ring, style)
    body += _draw_overlay_lines(data, style, frame, frame_bounds, subject, key, k)
    body += _draw_labels(data, style, frame, labels, key, k)
    body.append("</g>")
    legend_rows = _get_legend_rows(entries, extras, counts, measures)
    card_rows = _get_card_lines(key, data, items, counts, measures, ctx)
    if style["layout"] == "side":
        body += _draw_info_side(data, style, sheet_id, name, frame, box, legend_rows, card_rows)
    elif style["layout"] == "bottom":
        body += _draw_info_bottom(data, style, sheet_id, name, frame, box, legend_rows, card_rows)
    else:
        body += _draw_info_map_only(data, style, frame)
    if style["layout"] != "map":
        body.append('<rect id="map_frame" x="%s" y="%s" width="%s" height="%s" fill="none" stroke="%s" stroke-width="%s"/>'
                    % (_fmt(box[0]), _fmt(box[1]), _fmt(box[2]), _fmt(box[3]), style["ink"], _fmt(constants.SHEET_LINE_MM["frame"] * style["line_scale"])))
    body.append("</svg>")
    return "\n".join(body), empty, reason


# ─────────────────────────────────────────────
# 썸네일 — 패널 도면 칸용 작은 PNG(표준 라이브러리: 스캔라인 채우기 + zlib)
# ─────────────────────────────────────────────

def _get_item_geometry(item):
    if isinstance(item, tuple):   # 지형 삼각형
        return {"type": "Polygon", "coordinates": [[(p[0], p[1]) for p in item[:3]]]}
    return item.geometry


def _rasterize(items, frame, rect, px):
    # type: (list, Frame, tuple, int) -> list
    """세계좌표 항목(형상) → px×px 격자(지도 칸 안 정사각 rect = (x0, y0, 한 변) mm)에 항목 번호, 비면 -1. 나중 항목이 위.
    면은 칸 중심 스캔라인(짝홀 규칙 — 구멍 포함), 선은 반 칸 간격 점 찍기. 점은 건너뛴다. 격자 밖 항목은 bbox로 먼저 거른다."""
    grid = [-1] * (px * px)
    x0, y0, size = rect
    cell = size / float(px)
    f = 1000.0 / (frame.scale * cell)                                  # 세계 m → 격자 칸
    ox = (frame.paper_mm[0] * 0.5 - x0) / cell - frame.center[0] * f
    oy = (frame.paper_mm[1] * 0.5 - y0) / cell + frame.center[1] * f
    span = px / f                                                      # 격자 한 변의 세계 길이
    wx0, wy1 = (0 - ox) / f, oy / f
    world = (wx0, wy1 - span, wx0 + span, wy1)
    for index, item in enumerate(items):
        if not isinstance(item, tuple) and not _intersects(_get_item_bounds(item), world):
            continue
        geometry = _get_item_geometry(item)
        kind = (geometry or {}).get("type")
        if kind in ("Polygon", "MultiPolygon"):
            rings = [[(p[0] * f + ox, oy - p[1] * f) for p in ring] for part in get_polygon_parts_from_geojson(geometry) for ring in part]
            rings = [ring for ring in rings if len(ring) >= 3]
            if not rings:
                continue
            ys = [p[1] for ring in rings for p in ring]
            row0, row1 = max(0, int(math.floor(min(ys) - 0.5)) + 1), min(px - 1, int(math.floor(max(ys) - 0.5)))
            if row0 > row1:
                continue
            rows = {}   # 행마다 걸치는 변만 — 도로 필지 도넛은 변이 수천 개라 행마다 전부 보면 느리다
            for ring in rings:
                for a, b in zip(ring[-1:] + ring[:-1], ring):
                    if a[1] == b[1]:
                        continue
                    low, high = (a[1], b[1]) if a[1] < b[1] else (b[1], a[1])
                    for row in range(max(row0, int(math.ceil(low - 0.5))), min(row1, int(math.ceil(high - 0.5)) - 1) + 1):
                        rows.setdefault(row, []).append((a, b))
            for row, edges in rows.items():
                yc = row + 0.5
                xs = sorted(a[0] + (yc - a[1]) * (b[0] - a[0]) / (b[1] - a[1]) for a, b in edges)
                base = row * px
                for xa, xb in zip(xs[0::2], xs[1::2]):
                    for col in range(max(0, int(math.ceil(xa - 0.5))), min(px, int(math.floor(xb - 0.5)) + 1)):
                        grid[base + col] = index
        elif kind in ("LineString", "MultiLineString"):
            lines = [geometry["coordinates"]] if kind == "LineString" else geometry["coordinates"]
            for line in lines:
                pts = [(p[0] * f + ox, oy - p[1] * f) for p in line]
                for (ax, ay), (bx, by) in zip(pts, pts[1:]):
                    steps = max(1, int(math.hypot(bx - ax, by - ay) * 2))
                    for i in range(steps + 1):
                        col, row = int(ax + (bx - ax) * i / steps), int(ay + (by - ay) * i / steps)
                        if 0 <= col < px and 0 <= row < px:
                            grid[row * px + col] = index
    return grid


def _get_png_uri(pixels, size):
    # type: (list, int) -> str
    """[(r, g, b)] size×size → data:image/png;base64 (8비트 RGB, 필터 0)."""
    raw = b"".join(b"\x00" + bytes(c for rgb in pixels[row * size:(row + 1) * size] for c in rgb) for row in range(size))

    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def render_thumbnail(sheet_id, data):
    # type: (int, SheetData) -> str
    """도면 한 장의 썸네일 PNG data URI — 지도 칸 가운데 정사각, SHEET_THUMB_PX. 바탕(도로·수계·녹지·건물) + 주제 색 + 범위 밖 흐림 + 범위·대상지 선.
    같은 형상 격자는 data.cache에 두고 시트마다 색만 바꾼다(23장 ≈ 1~2 s)."""
    key = SHEET_KEYS[sheet_id]
    style = get_style(data.options)
    frame = data.get_frame(style["layout"])
    w, h = frame.paper_mm
    size, px = min(w, h), constants.SHEET_THUMB_PX
    rect = ((w - size) * 0.5, (h - size) * 0.5, size)
    frame_bounds = frame.world_bounds()
    classify_fn, base_mode = SHEETS[key]
    subject = constants.SHEET_LEGENDS[key][0]
    items = _get_subject_items(subject, data)
    ctx, entries, _extras = _get_sheet_context(key, data, style, items)

    def raster(name, getter):
        cache_key = ("thumb", name, frame.scale, frame.paper_mm)
        if cache_key not in data.cache:
            data.cache[cache_key] = _rasterize(list(getter()), frame, rect, px)
        return data.cache[cache_key]

    lots = lambda: _get_subject_items("lot", data)
    colors = _get_base_colors(style, base_mode)
    rgb_memo = {}

    def rgb(color):
        value = rgb_memo.get(color)
        if value is None:
            value = rgb_memo[color] = _get_rgb(color)
        return value
    pixels = [rgb(style["paper"] if base_mode == "figure" else colors["block"])] * (px * px)

    def paint(grid, color_of):
        memo = {}
        for i, index in enumerate(grid):
            if index >= 0:
                value = memo.get(index)
                if value is None:
                    color = color_of(index)
                    value = memo[index] = rgb(color) if color else False
                if value:
                    pixels[i] = value

    if base_mode != "figure":
        paint(raster("road", lambda: [f for f in data.features if f.theme == "road" and f.kind == "surface"] + [l for l in lots() if l.land_category == constants.LAND_CATEGORY_ROAD]), lambda i: colors["road"])
        paint(raster("green", lambda: [f for f in data.features if f.theme == "green"]), lambda i: colors["green"])
    paint(raster("water", lambda: [f for f in data.features if f.theme == "water" and f.kind in constants.WATER_SURFACE_KINDS]), lambda i: colors["water"])
    if subject not in ("terrain", "block") and base_mode != "figure" and subject != "building":
        paint(raster("buildings", lambda: data.buildings), lambda i: colors["building"])
    styles = {k: v for k, _, v in entries}

    def theme_color(index):
        return _entry_color(styles.get(classify_fn(items[index], ctx))) if classify_fn else None

    if classify_fn and key != "transit":
        if subject in ("green", "public", "overlay"):   # 이 시트만 쓰는 대상 — 분류되는 것만 격자로(피처·필지 전부를 칠하지 않게)
            drawn = [item for item in items if classify_fn(item, ctx) in styles]
            paint(raster("subject_" + key, lambda: drawn), lambda i: _entry_color(styles.get(classify_fn(drawn[i], ctx))))
        else:
            paint(raster("subject_" + subject, lambda: items), theme_color)
    if subject in ("terrain", "block"):
        paint(raster("buildings", lambda: data.buildings), lambda i: colors["building"])
    if key == "transit":
        cell = size / float(px) * frame.scale / 1000.0
        stations = [frame.to_paper(*st.geometry["coordinates"][:2]) for st in items]
        r1 = constants.SHEET_TRANSIT_RADII_M[0] / cell
        tint = rgb(constants.SHEET_TRANSIT_COLOR)
        centers = [((sx - rect[0]) / size * px, (sy - rect[1]) / size * px) for sx, sy in stations]
        for i in range(px * px):
            row, col = divmod(i, px)
            if any(math.hypot(col + 0.5 - cx, row + 0.5 - cy) <= r1 for cx, cy in centers):
                pixels[i] = tuple(int(round(c + (t - c) * 0.35)) for c, t in zip(pixels[i], tint))
    if data.extent_ring and key not in constants.SHEET_NO_MASK and style["fade_outside"] > 0:
        inside = raster("extent_fill", lambda: [SimpleShape({"type": "Polygon", "coordinates": [data.extent_ring]})])
        paper = rgb(style["paper"])
        fade = style["fade_outside"]
        pixels = [p if inside[i] >= 0 else tuple(int(round(c + (q - c) * fade)) for c, q in zip(p, paper)) for i, p in enumerate(pixels)]
    for name, ring_color, rings in (("extent_line", style["extent"], [data.extent_ring] if data.extent_ring else []),
                                    ("site_line", style["site"], data.site_rings or [part[0] for lot in data.target_lots for part in get_polygon_parts_from_geojson(lot.geometry)])):
        paint(raster(name, lambda rings=rings: [SimpleShape({"type": "LineString", "coordinates": list(r) + [r[0]]}) for r in rings]), lambda i, c=ring_color: c)
    return _get_png_uri(pixels, px)


def _entry_color(entry):
    # type: (dict) -> str
    """범례 스타일 → 썸네일 한 색(칠, 없으면 선; 해치는 해치 선 색)."""
    if not entry:
        return None
    color = entry.get("fill") if entry.get("fill") not in (None, "none") else entry.get("stroke")
    return constants.SHEET_HATCH["landlocked"]["stroke"] if str(color).startswith("url(") else color


class SimpleShape(object):
    def __init__(self, geometry):
        self.geometry = geometry


def get_sheet_ai(svg_path):
    # type: (str) -> str
    """도면 SVG 옆 레이어 .ai 경로 — 없거나 SVG보다 오래됐으면(스타일 적용 뒤) basemap_ai.write_svg_ai로 새로 쓴다."""
    import basemap_ai   # basemap_ai가 이 모듈을 import한다 — 순환을 피해 여기서
    ai_path = os.path.splitext(svg_path)[0] + ".ai"
    if not os.path.exists(ai_path) or os.path.getmtime(ai_path) < os.path.getmtime(svg_path):
        with open(svg_path, encoding="utf-8") as handle:
            basemap_ai.write_svg_ai(handle.read(), ai_path, os.path.splitext(os.path.basename(svg_path))[0])
    return ai_path


def get_sheet_file_name(sheet_id, name):
    # type: (int, str) -> str
    return "%02d_%s.svg" % (sheet_id, re.sub(r"[^0-9A-Za-z가-힣]", "", name))


def write_sheets(data, out_dir, sheet_ids=None, options=None):
    # type: (SheetData, str, list, dict) -> list
    """시트들을 out_dir에 쓴다 — 장마다 .svg + 썸네일 PNG data URI. 레이어 .ai는 패널이 누를 때 만든다(get_sheet_ai — 23장 다 쓰면 Rhino에서 10 s+).
    반환 [{id, name, path(svg), thumb, empty, reason}] (panel_ui.md done.sheets 모양)."""
    if options:
        data.options = dict(data.options, **options)
    wanted = set(int(v) for v in (sheet_ids if sheet_ids is not None else SHEET_NAMES))
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for sheet_id, _key, name, _en, _needs in constants.SHEET_CATALOG:
        if sheet_id not in wanted:
            continue
        svg, empty, reason = render_sheet(sheet_id, data)
        path = os.path.join(out_dir, get_sheet_file_name(sheet_id, name))
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(svg)
        results.append({"id": sheet_id, "name": name, "path": path, "thumb": render_thumbnail(sheet_id, data), "empty": empty, "reason": reason})
    return results
