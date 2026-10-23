"""2D CAD 현황도 DXF 작성기 (AutoCAD판) — Prepared(세계좌표 m) → cad_<축척>.dxf 한 장. 표준 라이브러리만.

AutoCAD판은 3D를 내지 않는다(사무소는 AutoCAD로 3D를 하지 않는다). 대신 바로 바탕 도면으로 쓰는 2D:
  - 모형 공간 1:1, 단위 mm(기본)·m. 좌표는 원점 방식이면 대상지 중심(100 m 내림)이 (0,0), 실제 좌표면 EPSG:5186 그대로
  - 레이어 US-*(constants.CAD_LAYERS — 회색 바탕·대상지 빨강·선종류·선굵기·한글 설명). 해치 없음
  - 지번·건물 층수·도로명·현황 도로폭·용도지역 이름·등고선 표고·표고점 글자. 등고선은 2D 폴리선 + 고도(표고)
  - 생성 범위(extent_ring)의 bbox로 자른다. 범위 아래에 기준점 좌표·자료 출처·레이어 범례, 오른쪽 위 바깥에 방위표, 원점에 기준점 십자
DXF는 R12(AC1009) — 한글은 CP949($DWGCODEPAGE ANSI_949). 가장 오래된 공통 형식이라 AutoCAD·LT·ZWCAD·캐디안·BricsCAD가 모두 읽는다.
처음 쓴 R2000(핸들·OBJECTS 최소 구성)은 ezdxf 감사는 통과했지만 AutoCAD 2027 Mac이 열다 멈췄다(2026-10-18 '계속하려면 Enter') — R12로 바꿨다.
세계좌표 → 도면 좌표(원점 빼기·단위 곱하기)는 get_cad_pts 한 함수에서만 한다.
"""

import math
import os

import basemap_ai
import constants
import context_report
import non_rhino_utils


# ── DXF 작성기 ──────────────────────────────────────────────

# '?'가 되는 글자 — CP949에 없거나(—·⚠), CP949에는 있어도 한글 SHX(whgtxt)에 모양이 없는 기호(·±㎡→, 2026-10-23 AutoCAD 2027 Windows 화면).
# %%p·%%d는 AutoCAD 글자 제어 코드(±·°) — romans.shx가 그린다
CP949_FIX = str.maketrans({"—": "-", "–": "-", "⚠": "!", "\n": " ", "·": "/", "±": "%%p", "°": "%%d", "㎡": "m2", "²": "2", "→": "->", "×": "x"})

def _num(value):
    # type: (float) -> str
    text = ("%.4f" % value).rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class DxfWriter(object):
    """DXF R12 한 장 — 표(뷰·선종류·레이어·글꼴) + POLYLINE·TEXT·POINT. 좌표·높이는 도면 단위로 받는다."""

    def __init__(self, layers, linetypes, font):
        # type: (list, dict, tuple) -> None
        self.layers = layers          # constants.CAD_LAYERS 모양 — 쓴 레이어만 표에 넣는다
        self.linetypes = linetypes    # {이름: (설명, (길이 …))} — 종이 mm, $LTSCALE이 도면 단위로 늘린다
        self.font = font              # (주 글꼴, 한글 큰 글꼴) SHX
        self.shapes = []
        self.counts = {}
        self.box = [math.inf, math.inf, -math.inf, -math.inf]

    def _add(self, layer, shape, pts):
        self.shapes.append(shape)
        self.counts[layer] = self.counts.get(layer, 0) + 1
        for x, y in pts:
            self.box = [min(self.box[0], x), min(self.box[1], y), max(self.box[2], x), max(self.box[3], y)]

    def polyline(self, layer, pts, closed=False, elevation=0.0):
        # type: (str, list, bool, float) -> None
        if len(pts) >= 2:
            self._add(layer, ("POLYLINE", layer, list(pts), closed, elevation), pts)

    def text(self, layer, content, x, y, height, angle=0.0, left=False):
        # type: (str, str, float, float, float, float, bool) -> None
        """가운데 정렬(기본) 또는 왼쪽 아래 기준(left) 한 줄."""
        content = (content or "").strip()
        if content:
            self._add(layer, ("TEXT", layer, content, x, y, height, angle, left), [(x, y)])

    def point(self, layer, x, y, z):
        # type: (str, float, float, float) -> None
        self._add(layer, ("POINT", layer, x, y, z), [(x, y)])

    def write(self, path, ltscale, point_size):
        # type: (str, float, float) -> int
        """파일을 쓰고 객체 수를 돌려준다. ltscale = $LTSCALE, point_size = $PDSIZE(도면 단위). CP949에 없는 글자는 '?'."""
        body = []

        def put(*pairs):
            for code, value in pairs:
                body.append("%3d\r\n%s\r\n" % (code, _num(value) if isinstance(value, float) else value))

        used = [layer for layer in self.layers if layer[0] in self.counts]
        min_x, min_y, max_x, max_y = self.box if self.shapes else (0.0, 0.0, 1.0, 1.0)
        width, height = max(max_x - min_x, 1e-6), max(max_y - min_y, 1e-6)
        put((0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, "AC1009"), (9, "$DWGCODEPAGE"), (3, "ANSI_949"),
            (9, "$INSBASE"), (10, 0.0), (20, 0.0), (30, 0.0),
            (9, "$EXTMIN"), (10, float(min_x)), (20, float(min_y)), (30, 0.0), (9, "$EXTMAX"), (10, float(max_x)), (20, float(max_y)), (30, 0.0),
            (9, "$LTSCALE"), (40, float(ltscale)), (9, "$TEXTSTYLE"), (7, "US-KOR"), (9, "$CLAYER"), (8, "0"),
            (9, "$PDMODE"), (70, 3), (9, "$PDSIZE"), (40, float(point_size)), (0, "ENDSEC"))
        put((0, "SECTION"), (2, "TABLES"))
        # *ACTIVE 뷰 — 처음 열 때 도면 전체가 보이게(가로 16:10 창 기준)
        put((0, "TABLE"), (2, "VPORT"), (70, 1), (0, "VPORT"), (2, "*ACTIVE"), (70, 0), (10, 0.0), (20, 0.0), (11, 1.0), (21, 1.0),
            (12, (min_x + max_x) * 0.5), (22, (min_y + max_y) * 0.5), (13, 0.0), (23, 0.0), (14, 1.0), (24, 1.0), (15, 1.0), (25, 1.0),
            (16, 0.0), (26, 0.0), (36, 1.0), (17, 0.0), (27, 0.0), (37, 0.0), (40, max(height, width / 1.6) * 1.05), (41, 1.6), (42, 50.0),
            (43, 0.0), (44, 0.0), (50, 0.0), (51, 0.0), (71, 0), (72, 100), (73, 1), (74, 3), (75, 0), (76, 0), (77, 0), (78, 0), (0, "ENDTAB"))
        put((0, "TABLE"), (2, "LTYPE"), (70, 1 + len(self.linetypes)),
            (0, "LTYPE"), (2, "CONTINUOUS"), (70, 0), (3, "Solid line"), (72, 65), (73, 0), (40, 0.0))
        for name, (description, pattern) in sorted(self.linetypes.items()):
            put((0, "LTYPE"), (2, name), (70, 0), (3, description), (72, 65), (73, len(pattern)), (40, float(sum(abs(v) for v in pattern))))
            put(*[(49, float(v)) for v in pattern])
        put((0, "ENDTAB"), (0, "TABLE"), (2, "LAYER"), (70, 1 + len(used)), (0, "LAYER"), (2, "0"), (70, 0), (62, 7), (6, "CONTINUOUS"))
        for name, _description, color, linetype in used:   # 색이 음수면 꺼진 레이어
            put((0, "LAYER"), (2, name), (70, 0), (62, -color if name in constants.CAD_LAYERS_OFF else color), (6, linetype))
        put((0, "ENDTAB"), (0, "TABLE"), (2, "STYLE"), (70, 2),
            (0, "STYLE"), (2, "STANDARD"), (70, 0), (40, 0.0), (41, 1.0), (50, 0.0), (71, 0), (42, 2.5), (3, "txt"), (4, ""),
            (0, "STYLE"), (2, "US-KOR"), (70, 0), (40, 0.0), (41, 1.0), (50, 0.0), (71, 0), (42, 2.5), (3, self.font[0]), (4, self.font[1]),
            (0, "ENDTAB"), (0, "ENDSEC"), (0, "SECTION"), (2, "ENTITIES"))
        for shape in self.shapes:
            kind, layer = shape[0], shape[1]
            if kind == "POLYLINE":   # 2D 폴리선 — 고도는 머리 점의 Z(30)
                pts, closed, elevation = shape[2], shape[3], shape[4]
                put((0, "POLYLINE"), (8, layer), (66, 1), (10, 0.0), (20, 0.0), (30, float(elevation)), (70, 1 if closed else 0))
                for x, y in pts:
                    put((0, "VERTEX"), (8, layer), (10, float(x)), (20, float(y)), (70, 0))
                put((0, "SEQEND"), (8, layer))
            elif kind == "TEXT":
                content, x, y, size, angle, left = shape[2:]
                put((0, "TEXT"), (8, layer), (10, float(x)), (20, float(y)), (30, 0.0), (40, float(size)), (1, content.translate(CP949_FIX)))
                if angle:
                    put((50, float(angle)))
                put((7, "US-KOR"))
                if not left:   # 가운데 중간 — 맞춤점(11)이 기준이다
                    put((72, 1), (11, float(x)), (21, float(y)), (31, 0.0), (73, 2))
            else:
                x, y, z = shape[2:]
                put((0, "POINT"), (8, layer), (10, float(x)), (20, float(y)), (30, float(z)))
        put((0, "ENDSEC"), (0, "EOF"))
        with open(path, "w", encoding="cp949", errors="replace", newline="") as f:
            f.write("".join(body))
        return len(self.shapes)


# ── 도면 내용 ───────────────────────────────────────────────

def get_cad_pts(coords, shift, unit_scale):
    # type: (list, tuple, float) -> list
    """세계좌표 m → 도면 좌표. shift(원점 방식 = 계산 원점, 실제 좌표 = (0, 0))를 빼고 단위를 곱하는 유일한 자리."""
    sx, sy = float(shift[0]), float(shift[1])
    return [((float(p[0]) - sx) * unit_scale, (float(p[1]) - sy) * unit_scale) for p in coords]


def get_label_spot(pts):
    # type: (list) -> tuple
    """점열 길이의 가운데 점과 그 자리 선 방향(도 — 글자가 거꾸로 서지 않게 -90 초과 90 이하). 출력 (x, y, 각도, 전체 길이)."""
    lengths = [math.hypot(x1 - x0, y1 - y0) for (x0, y0), (x1, y1) in zip(pts, pts[1:])]
    total = sum(lengths)
    rest = total * 0.5
    for (x0, y0), (x1, y1), length in zip(pts, pts[1:], lengths):
        if rest <= length and length > 0.0:
            t = rest / length
            angle = math.degrees(math.atan2(y1 - y0, x1 - x0))
            angle = angle - 180.0 if angle > 90.0 else (angle + 180.0 if angle <= -90.0 else angle)
            return (x0 + (x1 - x0) * t, y0 + (y1 - y0) * t, angle, total)
        rest -= length
    return (pts[-1][0], pts[-1][1], 0.0, total)


def get_cad_scale(options):
    # type: (dict) -> int
    try:
        scale = int((options or {}).get("cad_scale") or 0)
    except (TypeError, ValueError):
        scale = 0
    return scale if scale in constants.CAD_SCALES else constants.CAD_DEFAULT_SCALE


def get_cad_unit(options):
    # type: (dict) -> str
    unit = (options or {}).get("cad_unit")
    return unit if unit in constants.CAD_UNITS else constants.CAD_DEFAULT_UNIT


def get_site_lines(target_lots):
    # type: (list) -> list
    """대상지 한 줄 — 소재지·지목·대장면적·용도지역(토지특성정보). 위치 방식(필지 없음)은 빈 목록."""
    lots = list(target_lots or [])
    if not lots:
        return []
    first = lots[0]
    where = first.address + ("" if len(lots) == 1 else " 외 %d필지" % (len(lots) - 1))
    area = sum(float(lot.registered_area or lot.geometry_area or 0.0) for lot in lots)
    categories = sorted({lot.land_category for lot in lots if lot.land_category})
    zones = sorted({name for lot in lots for name in (lot.zone_name, lot.zone_name_2) if name and name != "지정되지않음"})   # 용도지역2 빈칸 값(익선동 166-5)
    return ["대상지 — %s · 지목 %s · 대장면적 %s㎡ · 용도지역 %s (토지특성정보 %s)" % (
        where, "·".join(categories) or "-", "{:,.1f}".format(area), "·".join(zones) or "-", first.reference_date or "-")]


def build_cad(prepared):
    # type: (object) -> tuple
    """Prepared → 채운 DxfWriter와 쓰기 설정. 파일은 쓰지 않는다(write_dxf).

    입력: Prepared(세계좌표 m). options.cad_unit(mm|m)·cad_scale(글자 크기)·placement(origin|world).
    처리: 생성 범위 bbox로 자른 면 외곽·선 → POLYLINE, 이름·수치 → TEXT, 표고점 → POINT. 레이어는 constants.CAD_LAYERS.
    출력: (writer, {unit, unit_scale, scale, ltscale, point_size, buildings}).
    """
    options = prepared.request["options"]
    unit = get_cad_unit(options)
    unit_scale = constants.CAD_UNITS[unit]
    scale = get_cad_scale(options)
    paper = scale / 1000.0 * unit_scale   # 종이 1 mm → 도면 단위
    shift = (0.0, 0.0) if prepared.placement == "world" else tuple(prepared.origin)
    bbox = non_rhino_utils.get_bbox(prepared.extent_ring)
    writer = DxfWriter(constants.CAD_LAYERS, constants.CAD_LINETYPES, constants.CAD_FONT)

    def to_cad(coords):
        return get_cad_pts(coords, shift, unit_scale)

    def inside(x, y):
        return bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]

    def outline(layer, geometry):
        for rings in basemap_ai.get_parts_in_frame(basemap_ai.get_parts(geometry), bbox):
            for ring in rings:
                writer.polyline(layer, to_cad(ring), closed=True)

    def lines(layer, geometry, elevation=0.0):
        kind = geometry.get("type")
        parts = [geometry["coordinates"]] if kind == "LineString" else (geometry["coordinates"] if kind == "MultiLineString" else [])
        pieces = []
        for coords in parts:
            for piece in basemap_ai.get_clipped_lines([(float(p[0]), float(p[1])) for p in coords], bbox):
                writer.polyline(layer, to_cad(piece), elevation=elevation * unit_scale)
                pieces.append(piece)
        return pieces

    def text(layer, content, x, y, angle=0.0):
        if inside(x, y):
            px, py = to_cad([(x, y)])[0]
            writer.text(layer, content, px, py, constants.CAD_TEXT_MM[layer] * paper, angle)

    def get_text_box(layer, content, x, y):
        # 가운데 맞춤 글자의 세계좌표 상자(m) — 글자 폭 ≈ 높이 × 글자 수(한글·romans 평균)
        height = constants.CAD_TEXT_MM[layer] * scale / 1000.0
        half_width = 0.5 * height * len(content)
        return (x - half_width, y - height * 0.6, x + half_width, y + height * 0.6)

    def get_centroid(geometry):
        parts = basemap_ai.get_parts(geometry)
        if not parts:
            return None
        return basemap_ai.get_ring_centroid(max((part[0] for part in parts), key=non_rhino_utils.get_ring_area))

    def centroid_text(layer, content, geometry):
        spot = get_centroid(geometry)
        if spot and content:
            text(layer, content, *spot)

    # 수치지형도 피처 — 도로중심선은 조각마다 현황 폭, 이름은 처음 붙는 조각 하나에 같이. 등고선은 고도 = 표고
    road_names, place_names = set(), set()
    contour_spots, contour_gap = [], constants.CAD_TEXT_MM["US-CONT-TXT"] * scale / 1000.0 * constants.CAD_LABEL_GAP
    for f in prepared.features:
        if not basemap_ai.hits(f, bbox):
            continue
        geometry = f.geometry
        if f.theme == "water" and f.kind in constants.WATER_SURFACE_KINDS:
            outline("US-WATER", geometry)
        elif f.theme == "green":
            outline("US-GREEN", geometry)
        elif f.theme == "road" and f.kind == "surface":
            outline("US-ROAD", geometry)
        elif f.theme == "road" and f.kind == "centerline":
            name = (f.name or "").strip()
            for piece in lines("US-ROAD-CL", geometry):
                x, y, angle, length = get_label_spot(piece)
                if length < constants.CAD_LABEL_MIN_LEN or not (f.value or name):
                    continue
                label = "%gm" % f.value if f.value else ""
                if name and name not in road_names:
                    road_names.add(name)
                    label = (name + " " + label).strip()
                text("US-ROAD-TXT", label, x, y, angle)
        elif f.theme == "rail" and f.kind in ("line", "centerline"):
            lines("US-RAIL", geometry)
        elif f.theme == "rail" and f.kind == "surface":
            outline("US-RAIL", geometry)
        elif f.theme == "terrain" and f.kind == "contour":
            layer = "US-CONT-IDX" if str((f.attrs or {}).get("구분") or "") == "계곡선" else "US-CONT"
            for piece in lines(layer, geometry, f.value or 0.0):
                x, y, angle, length = get_label_spot(piece)
                if f.value is None or length < constants.CAD_LABEL_MIN_LEN:
                    continue
                if any(math.hypot(x - lx, y - ly) < contour_gap for lx, ly in contour_spots):
                    continue   # 이웃 등고선 표고와 한 자리에 겹친다(평창동 1-1 — 195·200)
                contour_spots.append((x, y))
                text("US-CONT-TXT", "%g" % f.value, x, y, angle)
        elif f.theme == "terrain" and f.kind in ("spot", "benchmark") and geometry.get("type") == "Point" and f.value is not None:
            x, y = float(geometry["coordinates"][0]), float(geometry["coordinates"][1])
            if inside(x, y):
                px, py = to_cad([(x, y)])[0]
                size = constants.CAD_TEXT_MM["US-SPOT"] * paper
                writer.point("US-SPOT", px, py, f.value * unit_scale)
                writer.text("US-SPOT", "%.1f" % f.value, px, py + size, size)
        elif f.theme == "label" and f.kind == "place" and geometry.get("type") == "Point" and (f.name or "").strip() not in place_names:
            place_names.add((f.name or "").strip())
            text("US-LABEL", f.name, float(geometry["coordinates"][0]), float(geometry["coordinates"][1]))
    # 필지 — 지적선 + 지번(가장 넓은 조각 면적 중심). 대상지·인접 필지만 켜진 레이어, 나머지는 꺼진 레이어
    site_rings = list(getattr(prepared, "site_rings", None) or [])
    if not site_rings:   # 예전 Prepared(경계 없음)는 대상 필지 외곽
        site_rings = [max((p[0] for p in basemap_ai.get_parts(lot.geometry)), key=non_rhino_utils.get_ring_area)
                      for lot in prepared.target_lots if basemap_ai.get_parts(lot.geometry)]
    near = None   # 대상지 bbox + CAD_NEAR_LOT_GAP — 위치 방식(경계 없음)은 인접 필지가 없다
    if site_rings:
        gap = constants.CAD_NEAR_LOT_GAP
        site_box = non_rhino_utils.get_bbox([pt for ring in site_rings for pt in ring])
        near = (site_box[0] - gap, site_box[1] - gap, site_box[2] + gap, site_box[3] + gap)
    lot_boxes = []   # 지번 글자 상자 — 건물 층수 글자가 피한다
    for lot in list(prepared.target_lots) + list(prepared.near_lots):
        if basemap_ai.hits(lot, bbox):
            outline("US-LOT", lot.geometry)
            layer = "US-LOT-NO" if near and basemap_ai.hits(lot, near) else "US-LOT-NO-ALL"
            spot = get_centroid(lot.geometry)
            if spot and lot.lot_number:
                text(layer, lot.lot_number, *spot)
                lot_boxes.append(get_text_box(layer, lot.lot_number, *spot))
    # 건물 — 외곽 + 지상층수. 건물이 필지를 거의 채우면 두 면적 중심이 겹친다 → 층수를 지번 아래로(익선동 166-5·137-6)
    buildings = 0
    for bld in prepared.buildings:
        if basemap_ai.hits(bld, bbox):
            buildings += 1
            outline("US-BLDG", bld.geometry)
            spot = get_centroid(bld.geometry)
            if spot and int(bld.grnd_flr or 0) > 0:
                label = "%dF" % int(bld.grnd_flr)
                x, y = spot
                for box in lot_boxes:
                    mine = get_text_box("US-BLDG-FL", label, x, y)
                    if mine[0] < box[2] and mine[2] > box[0] and mine[1] < box[3] and mine[3] > box[1]:
                        y = box[1] - (mine[3] - mine[1]) * 0.7
                text("US-BLDG-FL", label, x, y)
    # 계획 — 용도지역·지구단위계획구역(이름), 도시계획시설 도로(저촉 확인), 공원·녹지 시설
    for o in (prepared.overlays if options.get("include_zoning", True) else []):   # 패널 '용도지역 경계선'
        if o.theme in (constants.OVERLAY_THEME_ZONE, constants.OVERLAY_THEME_PLAN):
            outline("US-ZONE", o.geometry)
            centroid_text("US-ZONE-TXT", o.name or o.kind, o.geometry)
        elif o.theme == constants.OVERLAY_THEME_FACILITY and o.kind == "도로":
            outline("US-PLAN-ROAD", o.geometry)
        elif o.theme == constants.OVERLAY_THEME_FACILITY and o.kind in constants.BM_GREEN_FACILITY_KINDS:
            outline("US-GREEN", o.geometry)
    # 대상지·범위 — 자르지 않는다(대상지는 범위 안, 범위는 bbox 자체)
    for ring in site_rings:
        writer.polyline("US-SITE", to_cad(ring), closed=True)
    writer.polyline("US-RANGE", to_cad(prepared.extent_ring), closed=True)
    # 기준점 십자(원점) · 방위표(범위 오른쪽 위 바깥) · 출처·레이어 범례(범위 아래 바깥)
    mark = constants.CAD_MARK_MM * paper
    ox, oy = to_cad([prepared.origin])[0]
    writer.polyline("US-REF", [(ox - mark, oy), (ox + mark, oy)])
    writer.polyline("US-REF", [(ox, oy - mark), (ox, oy + mark)])
    (left, bottom), (right, top) = to_cad([(bbox[0], bbox[1]), (bbox[2], bbox[3])])
    nx, ny = right - mark, top + mark * 2.0
    writer.polyline("US-REF", [(nx, ny + mark * 2.0), (nx - mark * 0.6, ny - mark * 0.6), (nx, ny), (nx + mark * 0.6, ny - mark * 0.6)], closed=True)
    ref_size = constants.CAD_TEXT_MM["US-REF"] * paper
    writer.text("US-REF", "N", nx, ny + mark * 2.0 + ref_size, ref_size)
    if prepared.placement == "world":
        coord_line = "좌표 — EPSG:5186 실제 좌표(TM) · 단위 %s%s" % (unit, " (TM 좌표 × 1000)" if unit == "mm" else "")
    else:
        coord_line = "좌표 — 십자 기준점(0,0) = EPSG:5186 E %.3f N %.3f m · 단위 %s" % (prepared.origin[0], prepared.origin[1], unit)
    lines_text = ["%s 현황도 — %s · 글자 크기 1:%d 기준" % (constants.TOOL_NAME, prepared.lot_name.replace("_", " "), scale), coord_line]
    lines_text += get_site_lines(prepared.target_lots)
    lines_text += context_report.get_meta_lines(prepared)
    lines_text += ["%s  %s" % (name, description) for name, description, *_ in constants.CAD_LAYERS if name in writer.counts or name == "US-REF"]
    for n, line in enumerate(lines_text):
        writer.text("US-REF", line, left, bottom - ref_size * (2.0 + 1.8 * n), ref_size, left=True)
    ltscale = scale / 1000.0 * unit_scale
    return writer, {"unit": unit, "unit_scale": unit_scale, "scale": scale, "ltscale": ltscale, "point_size": paper, "buildings": buildings}


def write_dxf(prepared, out_dir):
    # type: (object, str) -> dict
    """cad_<축척>.dxf 한 장. 반환 {ok, path, unit, scale, layers, entities, buildings, counts, bytes}."""
    writer, setting = build_cad(prepared)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, constants.CAD_FILE_FORMAT % setting["scale"])
    entities = writer.write(path, setting["ltscale"], setting["point_size"])
    return {"ok": True, "path": path, "unit": setting["unit"], "scale": setting["scale"], "layers": len(writer.counts), "entities": entities,
            "buildings": setting["buildings"], "counts": dict(writer.counts), "bytes": os.path.getsize(path)}
