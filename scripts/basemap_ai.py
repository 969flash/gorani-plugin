"""베이스맵 .ai 작성기 — Rhino를 거치지 않고 Illustrator 레거시(AI3/AI5) PostScript를 직접 쓴다 (deliverables §B).

왜 직접 쓰나(2026-10-08 실측):
  - Rhino 경로는 BM 객체 3.7만 개를 문서에 굽고(≈9 s) .ai로 내보내야(≈10 s) 했고, 3dm이 58 MB로 커졌다.
  - Rhino .ai는 아트보드가 1920×1080 기본값, 문서 원점에서 먼 대상지는 좌표가 수천 pt 밀려 나왔고, 한글 라벨은 UTF-8 + Helvetica로 써서 깨졌다.
  - 이 모듈은 Rhino가 쓰는 것과 같은 연산자(%AI5_BeginLayer · m/L · f/s/b · *u/*U · Tx)를 쓰되 %AI5_ArtSize로 아트보드를 용지에 맞추고,
    좌표를 프레임 왼쪽 아래 = (0, 0) pt로 쓰고, 한글은 CP949 + KSCms-UHC-H CMap 글꼴로 쓴다 — Illustrator 2026에서 레이어·아트보드·한글 확인.

표준 라이브러리만 쓴다(Rhino 안·밖 공통). 입력은 context_builder.Prepared(세계좌표 m).
레이어는 constants.BM_LAYERS 순서로 쓴다 — 파일 뒤쪽 레이어가 Illustrator 맨 위다(00 프레임이 맨 아래, 13 격자가 맨 위).
"""

import math
import os

import constants
import non_rhino_utils
import sheet_svg

MM_TO_PT = 72.0 / 25.4
MIN_SEGMENT_MM = 0.05   # 종이에서 이보다 가까운 연속 정점은 버린다(SHEET_MIN_VERTEX_MM와 같은 값)


# ── 순수 기하 헬퍼 ───────────────────────────────────────────

def _get_parts(geometry):
    # type: (dict) -> list
    """Polygon·MultiPolygon → ``[[outer, hole, ...], ...]`` 세계좌표(닫힘 중복점 제거). 다른 타입은 빈 목록."""
    if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        return []
    parts = []
    for part in non_rhino_utils.get_polygon_parts_from_geojson(geometry):
        rings = []
        for ring in part:
            pts = [(float(p[0]), float(p[1])) for p in ring]
            if len(pts) > 1 and pts[0] == pts[-1]:
                pts.pop()
            if len(pts) >= 3:
                rings.append(pts)
        if rings:
            parts.append(rings)
    return parts


def _hits(obj, bbox):
    # type: (object, tuple) -> bool
    """min_x/max_x/min_y/max_y를 가진 DB 객체가 bbox와 겹치는가."""
    return obj.min_x <= bbox[2] and obj.max_x >= bbox[0] and obj.min_y <= bbox[3] and obj.max_y >= bbox[1]


def get_parts_in_frame(parts, bbox):
    # type: (list, tuple) -> list
    """세계좌표 parts를 bbox로 자른다(sheet_svg.get_clipped_ring). 구멍은 BM_CLIP_INSET만큼 안쪽 사각형으로 — 바깥 링과 변이 겹치지 않게.
    bbox 안에 통째로 있으면 그대로, 전혀 안 겹치면 뺀다."""
    inset = constants.BM_CLIP_INSET
    hole_rect = (bbox[0] + inset, bbox[1] + inset, bbox[2] - inset, bbox[3] - inset)
    out = []
    for part in parts:
        rings = []
        for i, ring in enumerate(part):
            rect = bbox if i == 0 else hole_rect
            rb = non_rhino_utils.get_bbox(ring)
            if rb[2] < rect[0] or rb[0] > rect[2] or rb[3] < rect[1] or rb[1] > rect[3]:
                ring = []
            elif not (rb[0] >= rect[0] and rb[1] >= rect[1] and rb[2] <= rect[2] and rb[3] <= rect[3]):
                ring = sheet_svg.get_clipped_ring(ring, rect)
            if i == 0 and len(ring) < 3:
                break
            if len(ring) >= 3:
                rings.append(ring)
        if rings:
            out.append(rings)
    return out


def get_clipped_lines(pts, bbox):
    # type: (list, tuple) -> list
    """열린 점열 ``[(x, y)]``을 bbox로 자른다(Liang–Barsky, 변마다). 출력: 안쪽 조각 목록(점 2개 이상). 밖이면 []."""
    min_x, min_y, max_x, max_y = bbox
    pieces, cur = [], []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        dx, dy = x1 - x0, y1 - y0
        t0, t1 = 0.0, 1.0
        for p, q in ((-dx, x0 - min_x), (dx, max_x - x0), (-dy, y0 - min_y), (dy, max_y - y0)):
            if p == 0.0:
                if q < 0.0:
                    t0 = 2.0   # 변과 평행하면서 밖
                    break
            elif p < 0.0:
                t0 = max(t0, q / p)
            else:
                t1 = min(t1, q / p)
        if t0 > t1:
            if cur:
                pieces.append(cur)
            cur = []
            continue
        if not cur or t0 > 0.0:
            if cur:
                pieces.append(cur)
            cur = [(x0 + dx * t0, y0 + dy * t0)]
        cur.append((x0 + dx * t1, y0 + dy * t1))
        if t1 < 1.0:
            pieces.append(cur)
            cur = []
    if cur:
        pieces.append(cur)
    return [piece for piece in pieces if len(piece) >= 2]


def get_ring_centroid(ring):
    # type: (list) -> tuple
    """닫힌 링 ``[(x, y)]``의 면적 중심(신발끈). 면적 0이면 bbox 중심."""
    area2, cx, cy = 0.0, 0.0, 0.0
    prev = ring[-1]
    for cur in ring:
        cross = prev[0] * cur[1] - cur[0] * prev[1]
        area2 += cross
        cx += (prev[0] + cur[0]) * cross
        cy += (prev[1] + cur[1]) * cross
        prev = cur
    if abs(area2) < 1e-9:
        b = non_rhino_utils.get_bbox(ring)
        return ((b[0] + b[2]) * 0.5, (b[1] + b[3]) * 0.5)
    return (cx / (3.0 * area2), cy / (3.0 * area2))


def get_building_band(grnd_flr):
    # type: (int) -> str
    low, mid, high = constants.BM_FLOOR_BREAKS
    floors = int(grnd_flr or 0)
    return "07_bldg_low" if floors <= low else ("07_bldg_mid" if floors <= mid else ("07_bldg_high" if floors <= high else "07_bldg_tower"))


def get_basemap_layers(options, scale):
    # type: (dict, int) -> set
    """이 축척 .ai에 넣을 BM 레이어 이름 집합 — 기본 off(BASEMAP_DEFAULT_OFF_LAYERS)는 options.basemap_layers_on에 있을 때만,
    축척별 토글(BASEMAP_SCALE_LAYERS)이 False면 뺀다."""
    layers_on = set((options or {}).get("basemap_layers_on") or [])
    toggles = constants.BASEMAP_SCALE_LAYERS.get(int(scale), {})
    wanted = set()
    for name, _label, _fill, _line, _width in constants.BM_LAYERS:
        if name in constants.BASEMAP_DEFAULT_OFF_LAYERS and name not in layers_on:
            continue
        if toggles.get(name) is False:
            continue
        wanted.add(name)
    return wanted


def get_line_width_mm(name, scale):
    # type: (str, int) -> float
    """BM_LAYERS 선두께 (1:5000, 1:1000) 중 축척에 맞는 값 mm. 1:1000 이하·1:5000 이상은 끝값, 사이는 평균."""
    for layer_name, _label, _fill, _line, (w5000, w1000) in constants.BM_LAYERS:
        if layer_name == name:
            return w1000 if scale <= 1000 else (w5000 if scale >= 5000 else (w5000 + w1000) * 0.5)
    return 0.0


# ── .ai 작성 ─────────────────────────────────────────────────

def _ps_string(text):
    # type: (str) -> str
    """PostScript 문자열 리터럴. 한글은 CP949 바이트를 8진 이스케이프로(파일은 ASCII만 남는다). CP949에 없는 글자는 '?'."""
    out = ["("]
    for byte in text.encode("cp949", errors="replace"):
        if byte in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(byte))
        elif 32 <= byte < 127:
            out.append(chr(byte))
        else:
            out.append("\\%03o" % byte)
    out.append(")")
    return "".join(out)


def _text_width_em(text):
    # type: (str) -> float
    """글자 폭 어림(em) — 한글·한자 1.0, 그 밖 0.55. 가운데 정렬용."""
    return sum(1.0 if ord(ch) > 0x2000 else 0.55 for ch in text)


class AiWriter(object):
    """레이어별 PostScript 조각을 모아 .ai 한 장을 쓴다. 좌표는 세계 m → 종이 pt(프레임 왼쪽 아래 = 0, 0)."""

    def __init__(self, frame_bounds, scale, paper_mm):
        # type: (tuple, int, list) -> None
        self.x0, self.y0 = frame_bounds[0], frame_bounds[1]
        self.scale = float(scale)
        self.paper_pt = (paper_mm[0] * MM_TO_PT, paper_mm[1] * MM_TO_PT)
        self.k = 1000.0 / self.scale * MM_TO_PT          # 세계 m → pt
        self.min_seg = MIN_SEGMENT_MM * MM_TO_PT
        self.layers = {}                                  # 이름 → [조각]
        self.counts = {}

    def _pt(self, x, y):
        return (x - self.x0) * self.k, (y - self.y0) * self.k

    def _path(self, ring, closed):
        # type: (list, bool) -> list
        """세계 점열 → 'x y m' + 'x y L' 줄. 종이에서 MIN_SEGMENT_MM보다 가까운 점은 버린다. 점이 모자라면 []."""
        lines, last = [], None
        for x, y in ring:
            px, py = self._pt(x, y)
            if last is not None and abs(px - last[0]) < self.min_seg and abs(py - last[1]) < self.min_seg:
                continue
            lines.append("%.2f %.2f %s" % (px, py, "L" if lines else "m"))
            last = (px, py)
        if len(lines) < (3 if closed else 2):
            return []
        if closed:
            lines.append(lines[0].replace(" m", " L"))
        return lines

    def _add(self, layer, chunk):
        self.layers.setdefault(layer, []).append(chunk)
        self.counts[layer] = self.counts.get(layer, 0) + 1

    @staticmethod
    def _style(fill_k, line_k, width_pt):
        # type: (float, float, float) -> str
        """CMYK K만 쓰는 칠·선 상태(Rhino .ai와 같은 연산자). K는 0~100."""
        fill = (fill_k if fill_k is not None else 0) / 100.0
        line = (line_k if line_k is not None else 0) / 100.0
        return "0 0 0 %.4f K\n0 0 0 %.4f k\n0 i 1 J 1 j %.3f w 4 M []0 d\n0 D\n" % (line, fill, width_pt)

    def polygon(self, layer, rings, fill_k, line_k, width_mm):
        # type: (str, list, float, float, float) -> None
        """외곽 + 구멍 링(세계좌표). fill_k만 있으면 칠(f), line_k만 있으면 선(s), 둘 다면 b. 구멍이 있으면 compound path(*u … *U).
        외곽은 반시계, 구멍은 시계로 맞춰 칠 규칙과 무관하게 구멍이 뚫린다."""
        op = "b" if fill_k is not None and line_k is not None else ("f" if fill_k is not None else "s")
        oriented = []
        for i, ring in enumerate(rings):
            ccw = non_rhino_utils.get_ring_orientation(ring) >= 0
            if (i == 0) != ccw:
                ring = list(reversed(ring))
            path = self._path(ring, True)
            if path:
                oriented.append(path)
            elif i == 0:
                return
        if not oriented:
            return
        style = self._style(fill_k, line_k, width_mm * MM_TO_PT)
        if len(oriented) == 1:
            self._add(layer, style + "\n".join(oriented[0]) + "\n" + op + "\n")
        else:
            body = "".join("\n".join(path) + "\n" + op + "\n" for path in oriented)
            self._add(layer, style + "*u\n" + body + "*U\n")

    def line(self, layer, pts, line_k, width_mm):
        # type: (str, list, float, float) -> None
        path = self._path(pts, False)
        if path:
            self._add(layer, self._style(None, line_k, width_mm * MM_TO_PT) + "\n".join(path) + "\nS\n")

    def text(self, layer, content, x, y, size_mm, k=100.0):
        # type: (str, str, float, float, float, float) -> None
        """가운데 정렬 점 텍스트. 글꼴은 한글 CMap(AI_FONT_CMAP) — 레거시 텍스트로 열리고, 편집하려면 Illustrator '레거시 텍스트 업데이트'."""
        size_pt = size_mm * MM_TO_PT / constants.AI_CAP_HEIGHT_RATIO
        px, py = self._pt(x, y)
        px -= _text_width_em(content) * size_pt * 0.5
        py -= size_mm * MM_TO_PT * 0.5
        self._add(layer, "0 0 0 %.4f k\n0 i 1 J 1 j 1 w 4 M []0 d\n0 D\nu\n0 To\n1 0 0 1 %.2f %.2f 0 Tp\nTP\n0 Tr\n/_%s %.2f Tf\n%s Tx\nTO\nU\n"
                  % (k / 100.0, px, py, constants.AI_FONT_CMAP, size_pt, _ps_string(content)))

    def write(self, path, title):
        # type: (str, str) -> int
        """레이어를 BM_LAYERS 순서로 써서 파일 하나. 반환: 쓴 레이어 수."""
        w, h = int(round(self.paper_pt[0])), int(round(self.paper_pt[1]))
        font = constants.AI_FONT_CMAP
        names = [name for name, *_ in constants.BM_LAYERS if self.layers.get(name)]
        out = [
            "%!PS-Adobe-3.0", "%%Creator: " + constants.TOOL_NAME, "%%Title: " + _ps_string(title),
            "%%%%BoundingBox: 0 0 %d %d" % (w, h), "%%%%HiResBoundingBox: 0 0 %.4f %.4f" % self.paper_pt,
            "%%DocumentProcessColors: Black", "%%DocumentFonts: " + font,
            "%%DocumentNeededResources: procset Adobe_packedarray 2.0 0", "%%+ procset Adobe_cmykcolor 1.1 0", "%%+ procset Adobe_cshow 1.1 0",
            "%%+ procset Adobe_customcolor 1.0 0", "%%+ procset Adobe_typography_AI3 1.0 0", "%%+ procset Adobe_IllustratorA_AI3 1.0 0",
            "%AI3_ColorUsage: Color", "%%AI3_TemplateBox: %d %d %d %d" % (w // 2, h // 2, w // 2, h // 2), "%%AI3_TileBox: 0 0 %d %d" % (w, h),
            "%AI3_DocumentPreview: None", "%%AI5_ArtSize: %d %d" % (w, h), "%AI5_RulerUnits: 1", "%%AI5_NumLayers: %d" % len(names),
            "%%PageOrigin:0 0", "%%EndComments", "%%BeginProlog",
            "%%IncludeResource: procset Adobe_packedarray 2.0 0", "Adobe_packedarray /initialize get exec",
            "%%IncludeResource: procset Adobe_cmykcolor 1.1 0", "%%IncludeResource: procset Adobe_cshow 1.1 0",
            "%%IncludeResource: procset Adobe_customcolor 1.0 0", "%%IncludeResource: procset Adobe_typography_AI3 1.0 0",
            "%%IncludeResource: procset Adobe_IllustratorA_AI3 1.0 0", "%%EndProlog", "%%BeginSetup", "%%IncludeFont: " + font,
            "Adobe_cmykcolor /initialize get exec", "Adobe_cshow /initialize get exec", "Adobe_customcolor /initialize get exec",
            "Adobe_typography_AI3 /initialize get exec", "Adobe_IllustratorA_AI3 /initialize get exec", "%%EndSetup",
        ]
        parts = ["\n".join(out) + "\n"]
        labels = {name: label for name, label, *_ in constants.BM_LAYERS}
        for name in names:
            gray = 255 - int(round(255 * self._layer_k(name) / 100.0))
            parts.append("%%AI5_BeginLayer\n1 1 1 1 0 0 -1 %d %d %d Lb\n%s Ln\n0 A\n0 R\n" % (gray, gray, gray, _ps_string("%s %s" % (name, labels[name]))))
            parts.append("".join(self.layers[name]))
            parts.append("LB\n%AI5_EndLayer--\n")
        parts.append("%%PageTrailer\ngsave annotatepage grestore showpage\n%%Trailer\n"
                     "Adobe_IllustratorA_AI3 /terminate get exec\nAdobe_typography_AI3 /terminate get exec\nAdobe_customcolor /terminate get exec\n"
                     "Adobe_cshow /terminate get exec\nAdobe_cmykcolor /terminate get exec\nAdobe_packedarray /terminate get exec\n%%EOF\n")
        # Illustrator 레거시 .ai는 CRLF(Rhino 출력과 같게). 내용은 ASCII뿐(한글은 8진 이스케이프)
        with open(path, "w", encoding="ascii", newline="\r\n") as handle:
            handle.write("".join(parts))
        return len(names)

    @staticmethod
    def _layer_k(name):
        for layer_name, _label, fill_k, line_k, _width in constants.BM_LAYERS:
            if layer_name == name:
                return fill_k if fill_k is not None else (line_k or 0)
        return 0


class ShapeRecorder(object):
    """AiWriter와 같은 polygon·line·text를 받아 (layer, kind, data) 목록으로 모은다 — 3dm BM:: 2D 레이어용(context_geometry.build_basemap_2d).
    좌표는 세계 m 그대로. 칠·선 톤은 버린다(Rhino에서는 레이어 색이 대신한다)."""

    def __init__(self):
        self.shapes = []
        self.counts = {}

    def _add(self, layer, kind, data):
        self.shapes.append((layer, kind, data))
        self.counts[layer] = self.counts.get(layer, 0) + 1

    def polygon(self, layer, rings, fill_k, line_k, width_mm):
        self._add(layer, "polygon", rings)

    def line(self, layer, pts, line_k, width_mm):
        self._add(layer, "line", pts)

    def text(self, layer, content, x, y, size_mm, k=100.0):
        self._add(layer, "text", (content, x, y, size_mm))


def _layer_style(name):
    # type: (str) -> tuple
    """BM_LAYERS → (fill_k, line_k)."""
    for layer_name, _label, fill_k, line_k, _width in constants.BM_LAYERS:
        if layer_name == name:
            return fill_k, line_k
    return None, None


def build_ai(prepared, scale, writer=None):
    # type: (object, int, object) -> AiWriter
    """Prepared 한 축척의 베이스맵을 writer(기본 AiWriter, 3dm용은 ShapeRecorder)에 담는다(파일은 안 쓴다). 레이어 내용은 deliverables §B.2 —
    00 프레임 / 01 수면·지목 수계 / 02 지목 공원·임야·시설 공원·녹지·경지 / 02b 토지이용(기본 off) / 03 도로면·지목 도로 + 04 도로면 외곽 /
    05 도로중심선(기본 off) / 06 철도 / 07 건물 층수 4구간(칠+외곽) / 08 지적선 + 08b 지번(1:1000) / 09 등고선(계곡선은 진하게) /
    10 대상지·범위 / 11 용도지역·지구단위(기본 off) / 12 지명·도로명 / 13 500 m 격자. 객체는 프레임 bbox로 자른다."""
    scale = int(scale)
    options = prepared.request["options"]
    bbox = prepared.frame_bounds[scale]
    writer = writer if writer is not None else AiWriter(bbox, scale, options["paper_mm"])
    wanted = get_basemap_layers(options, scale)

    def polygon(fill_layer, edge_layer, geometry):
        fill_layer = fill_layer if fill_layer in wanted else None
        edge_layer = edge_layer if edge_layer in wanted else None
        if not fill_layer and not edge_layer:
            return
        layer = fill_layer or edge_layer
        fill_k = _layer_style(fill_layer)[0] if fill_layer else None
        line_k = _layer_style(edge_layer)[1] if edge_layer else None
        width = get_line_width_mm(edge_layer, scale) if edge_layer else 0.0
        if fill_layer and edge_layer and fill_layer != edge_layer:
            # 칠과 외곽이 다른 레이어(도로면 03 + 도로경계 04, 토지이용 02b + 지적선 08) — 따로 쓴다
            for rings in get_parts_in_frame(_get_parts(geometry), bbox):
                writer.polygon(fill_layer, rings, fill_k, None, 0.0)
                writer.polygon(edge_layer, rings, None, line_k, width)
            return
        for rings in get_parts_in_frame(_get_parts(geometry), bbox):
            writer.polygon(layer, rings, fill_k, line_k, width)

    def lines(layer, geometry, line_k=None):
        if layer not in wanted:
            return
        kind = geometry.get("type")
        parts = [geometry["coordinates"]] if kind == "LineString" else (geometry["coordinates"] if kind == "MultiLineString" else [])
        k = line_k if line_k is not None else _layer_style(layer)[1]
        for coords in parts:
            for piece in get_clipped_lines([(float(p[0]), float(p[1])) for p in coords], bbox):
                writer.line(layer, piece, k, get_line_width_mm(layer, scale))

    def text(layer, content, x, y):
        content = (content or "").strip()
        if not content or layer not in wanted or not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            return
        mm, ref_scale = constants.BM_TEXT_MM[layer]
        writer.text(layer, content, x, y, mm * ref_scale / float(scale), _layer_style(layer)[1] or 100.0)

    # 00 프레임
    frame = [(bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[2], bbox[3]), (bbox[0], bbox[3])]
    writer.polygon("00_frame_scale", [frame], None, _layer_style("00_frame_scale")[1], get_line_width_mm("00_frame_scale", scale))
    # 수치지형도 피처
    for f in prepared.features:
        if not _hits(f, bbox):
            continue
        if f.theme == "water" and f.kind in constants.WATER_SURFACE_KINDS:
            polygon("01_water", None, f.geometry)
        elif f.theme == "green":
            polygon("02_green", None, f.geometry)
        elif f.theme == "road" and f.kind == "surface":
            polygon("03_road_surface", "04_road_edge", f.geometry)
        elif f.theme == "road" and f.kind == "centerline":
            lines("05_road_center", f.geometry)
        elif f.theme == "rail" and f.kind in ("line", "centerline"):
            lines("06_rail", f.geometry)
        elif f.theme == "rail" and f.kind == "surface":
            polygon(None, "06_rail", f.geometry)
        elif f.theme == "terrain" and f.kind == "contour":
            index = str((f.attrs or {}).get("구분") or "") == "계곡선"
            lines("09_contour", f.geometry, constants.BM_CONTOUR_INDEX_K if index else None)
    # 필지
    site_rings = list(getattr(prepared, "site_rings", None) or [])
    targets = set() if site_rings else {lot.pnu for lot in prepared.target_lots}   # 예전 Prepared(경계 없음)만 필지 외곽으로
    for lot in list(prepared.target_lots) + list(prepared.near_lots):
        if not _hits(lot, bbox):
            continue
        if lot.land_category in constants.LAND_CATEGORIES_WATER:
            polygon("01_water", None, lot.geometry)
        elif constants.SHEET_LAND_CATEGORY_KEYS.get(lot.land_category) in ("park", "forest"):
            polygon("02_green", None, lot.geometry)
        elif lot.land_category == constants.LAND_CATEGORY_ROAD:
            polygon("03_road_surface", None, lot.geometry)
        polygon("02b_landuse", "08_parcel", lot.geometry)
        parts = _get_parts(lot.geometry)
        if not parts:
            continue
        outer = max((part[0] for part in parts), key=non_rhino_utils.get_ring_area)
        if lot.lot_number:
            cx, cy = get_ring_centroid(outer)
            text("08b_parcel_no", lot.lot_number, cx, cy)
        if lot.pnu in targets:
            polygon(None, "10_site", {"type": "Polygon", "coordinates": [outer]})
    for ring in site_rings:
        polygon(None, "10_site", {"type": "Polygon", "coordinates": [ring]})
    polygon(None, "10_site", {"type": "Polygon", "coordinates": [prepared.extent_ring]})
    # 건물 — 층수 구간마다 칠 + 외곽
    for bld in prepared.buildings:
        if _hits(bld, bbox):
            band = get_building_band(bld.grnd_flr)
            polygon(band, band, bld.geometry)
    # 오버레이 — 공원·녹지 시설 → 02, 용도지역·지구단위 → 11
    for o in prepared.overlays:
        if o.theme == constants.OVERLAY_THEME_FACILITY and o.kind in constants.BM_GREEN_FACILITY_KINDS:
            polygon("02_green", None, o.geometry)
        elif o.theme in (constants.OVERLAY_THEME_ZONE, constants.OVERLAY_THEME_PLAN):
            polygon(None, "11_zoning", o.geometry)
    # 12 주기 — 지명(점)·도로명(중심선 가운데 정점). 같은 이름은 1회
    seen = set()
    for f in prepared.features:
        name = (f.name or "").strip()
        if not name or name in seen or not _hits(f, bbox):
            continue
        if f.theme == "label" and f.kind == "place" and f.geometry.get("type") == "Point":
            x, y = float(f.geometry["coordinates"][0]), float(f.geometry["coordinates"][1])
        elif f.theme == "road" and f.kind == "centerline" and f.geometry.get("type") == "LineString":
            mid = f.geometry["coordinates"][len(f.geometry["coordinates"]) // 2]
            x, y = float(mid[0]), float(mid[1])
        else:
            continue
        seen.add(name)
        text("12_labels", name, x, y)
    # 13 격자 — 세계좌표 BM_GRID_STEP 배수
    step = constants.BM_GRID_STEP
    for axis in (0, 1):
        v = math.ceil(bbox[axis] / step) * step
        while v <= bbox[axis + 2]:
            pts = [(v, bbox[1]), (v, bbox[3])] if axis == 0 else [(bbox[0], v), (bbox[2], v)]
            lines("13_grid", {"type": "LineString", "coordinates": pts})
            v += step
    return writer


def write_basemap(prepared, scale, out_dir):
    # type: (object, int, str) -> dict
    """basemap_<축척>.ai 한 장. 반환 {ok, path, layers, counts, bytes}."""
    writer = build_ai(prepared, scale)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, constants.BASEMAP_FILE_FORMAT % int(scale))
    layers = writer.write(path, "%s 1:%d" % (prepared.lot_name, int(scale)))
    return {"ok": True, "path": path, "layers": layers, "counts": dict(writer.counts), "bytes": os.path.getsize(path)}
