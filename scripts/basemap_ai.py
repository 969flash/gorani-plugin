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
import re
import unicodedata

import constants
import non_rhino_utils
import sheet_svg
from i18n import get_lang, tr

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
    return _ps_bytes(text.encode("cp949", errors="replace"))


def get_ai_text(text):
    # type: (str) -> tuple
    """텍스트 → (글꼴, 바이트). 패널 언어 → 한글 → 일본어 → 중국어 간체 순으로 글자를 다 담는 첫 글꼴. ASCII(지번·축척)와 한글·영어는 늘 CP949 그대로.
    CP949에 없는 대시·©는 바꾸고 라틴 악센트는 뗀다(Área → Area — 어느 CMap에도 다 없다). 그래도 못 담으면 한글 글꼴에 '?'."""
    chars = []
    for ch in text:
        try:
            ch.encode("cp949")
        except UnicodeEncodeError:
            plain = "".join(c for c in unicodedata.normalize("NFKD", ch) if not unicodedata.combining(c))
            ch = constants.AI_CHAR_SUBSTITUTES.get(ch) or (plain if plain.isascii() else ch)
        chars.append(ch)
    text = "".join(chars)
    for lang in ("ko",) if text.isascii() else (get_lang(), "ko", "ja", "zh"):
        if lang in constants.AI_FONTS:
            font, codec = constants.AI_FONTS[lang]
            try:
                return font, text.encode(codec)
            except UnicodeEncodeError:
                pass
    return constants.AI_FONT_CMAP, text.encode("cp949", errors="replace")


def _ps_bytes(data):
    # type: (bytes) -> str
    """바이트 → PostScript 문자열 리터럴. 괄호·역슬래시는 이스케이프, ASCII 밖은 8진 이스케이프."""
    out = ["("]
    for byte in data:
        if byte in (0x28, 0x29, 0x5C):
            out.append("\\" + chr(byte))
        elif 32 <= byte < 127:
            out.append(chr(byte))
        else:
            out.append("\\%03o" % byte)
    out.append(")")
    return "".join(out)


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
        self.hidden = set(constants.BM_HIDDEN_LAYERS)     # 꺼 둔 채 쓰는 레이어(SVG display="none" 그룹도 여기에)
        self.fonts = []                                   # 텍스트가 쓴 글꼴(get_ai_text) — 헤더 DocumentFonts·IncludeFont

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

    _style_cache = {}

    @classmethod
    def _style(cls, fill, line, width_pt, dash_pt=None):
        # type: (object, object, float, list) -> str
        """칠·선 상태(Rhino .ai와 같은 연산자). 색은 K 톤(0~100) 또는 스타일 색 #RRGGBB(→ CMYK). dash_pt = 파선 [칠, 틈] pt."""
        key = (fill, line, round(width_pt, 3), tuple(dash_pt or ()))
        text = cls._style_cache.get(key)
        if text is None:
            dash = "[%s]" % " ".join("%.2f" % v for v in dash_pt) if dash_pt else "[]"
            text = cls._style_cache[key] = "%.4f %.4f %.4f %.4f K\n%.4f %.4f %.4f %.4f k\n0 i 1 J 1 j %.3f w 4 M %s0 d\n0 D\n" % (get_cmyk(line) + get_cmyk(fill) + (width_pt, dash))
        return text

    def polygon(self, layer, rings, fill_k, line_k, width_mm, dash_mm=None, holes=None):
        # type: (str, list, object, object, float, list, list) -> None
        """외곽 + 구멍 링(세계좌표). fill_k만 있으면 칠(f), line_k만 있으면 선(s), 둘 다면 b. 구멍이 있으면 compound path(*u … *U).
        외곽은 반시계, 구멍은 시계로 맞춰 칠 규칙과 무관하게 구멍이 뚫린다."""
        op = "b" if fill_k is not None and line_k is not None else ("f" if fill_k is not None else "s")
        oriented = []
        for i, ring in enumerate(rings):
            ccw = non_rhino_utils.get_ring_orientation(ring) >= 0
            outer = (i == 0) if holes is None else not holes[i]   # holes = 링마다 구멍인가(짝홀 규칙 — 여러 조각 path)
            if outer != ccw:
                ring = list(reversed(ring))
            path = self._path(ring, True)
            if path:
                oriented.append(path)
            elif i == 0:
                return
        if not oriented:
            return
        style = self._style(fill_k, line_k, width_mm * MM_TO_PT, [v * MM_TO_PT for v in dash_mm] if dash_mm else None)
        if len(oriented) == 1:
            self._add(layer, style + "\n".join(oriented[0]) + "\n" + op + "\n")
        else:
            body = "".join("\n".join(path) + "\n" + op + "\n" for path in oriented)
            self._add(layer, style + "*u\n" + body + "*U\n")

    def line(self, layer, pts, line_k, width_mm, dash_mm=None):
        # type: (str, list, object, float, list) -> None
        path = self._path(pts, False)
        if path:
            self._add(layer, self._style(None, line_k, width_mm * MM_TO_PT, [v * MM_TO_PT for v in dash_mm] if dash_mm else None) + "\n".join(path) + "\nS\n")

    def text(self, layer, content, x, y, size_mm, k=100.0, anchor="middle", baseline=False):
        # type: (str, str, float, float, float, object, str, bool) -> None
        """가운데 정렬 점 텍스트. 글꼴은 CMap 글꼴(get_ai_text — 한글은 AI_FONT_CMAP) — 레거시 텍스트로 열리고, 편집하려면 Illustrator '레거시 텍스트 업데이트'."""
        size_pt = size_mm * MM_TO_PT / constants.AI_CAP_HEIGHT_RATIO
        px, py = self._pt(x, y)
        px -= non_rhino_utils.get_text_width_em(content) * size_pt * {"start": 0.0, "end": 1.0}.get(anchor, 0.5)
        if not baseline:
            py -= size_mm * MM_TO_PT * 0.5
        font, data = get_ai_text(content)
        if font not in self.fonts:
            self.fonts.append(font)
        self._add(layer, "%.4f %.4f %.4f %.4f k\n0 i 1 J 1 j 1 w 4 M []0 d\n0 D\nu\n0 To\n1 0 0 1 %.2f %.2f 0 Tp\nTP\n0 Tr\n/_%s %.2f Tf\n%s Tx\nTO\nU\n"
                  % (get_cmyk(k) + (px, py, font, size_pt, _ps_bytes(data))))

    def write(self, path, title, order=None):
        # type: (str, str, list) -> int
        """레이어를 순서대로 써서 파일 하나 — 기본 BM_LAYERS(빈 레이어는 뺀다), order = [(이름, 라벨)]면 그 순서(빈 레이어도 쓴다 — 틀 시트). 반환: 쓴 레이어 수."""
        w, h = int(round(self.paper_pt[0])), int(round(self.paper_pt[1]))
        fonts = self.fonts or [constants.AI_FONT_CMAP]
        if order is None:
            order = [(name, label) for name, label, *_ in constants.BM_LAYERS if self.layers.get(name)]
        names = [name for name, _label in order]
        out = [
            "%!PS-Adobe-3.0", "%%Creator: " + constants.TOOL_NAME, "%%Title: " + _ps_string(title),
            "%%%%BoundingBox: 0 0 %d %d" % (w, h), "%%%%HiResBoundingBox: 0 0 %.4f %.4f" % self.paper_pt,
            "%%DocumentProcessColors: Cyan Magenta Yellow Black", "%%DocumentFonts: " + " ".join(fonts),
            "%%DocumentNeededResources: procset Adobe_packedarray 2.0 0", "%%+ procset Adobe_cmykcolor 1.1 0", "%%+ procset Adobe_cshow 1.1 0",
            "%%+ procset Adobe_customcolor 1.0 0", "%%+ procset Adobe_typography_AI3 1.0 0", "%%+ procset Adobe_IllustratorA_AI3 1.0 0",
            "%AI3_ColorUsage: Color", "%%AI3_TemplateBox: %d %d %d %d" % (w // 2, h // 2, w // 2, h // 2), "%%AI3_TileBox: 0 0 %d %d" % (w, h),
            "%AI3_DocumentPreview: None", "%%AI5_ArtSize: %d %d" % (w, h), "%AI5_RulerUnits: 1", "%%AI5_NumLayers: %d" % len(names),
            "%%PageOrigin:0 0", "%%EndComments", "%%BeginProlog",
            "%%IncludeResource: procset Adobe_packedarray 2.0 0", "Adobe_packedarray /initialize get exec",
            "%%IncludeResource: procset Adobe_cmykcolor 1.1 0", "%%IncludeResource: procset Adobe_cshow 1.1 0",
            "%%IncludeResource: procset Adobe_customcolor 1.0 0", "%%IncludeResource: procset Adobe_typography_AI3 1.0 0",
            "%%IncludeResource: procset Adobe_IllustratorA_AI3 1.0 0", "%%EndProlog", "%%BeginSetup", "\n".join("%%IncludeFont: " + font for font in fonts),
            "Adobe_cmykcolor /initialize get exec", "Adobe_cshow /initialize get exec", "Adobe_customcolor /initialize get exec",
            "Adobe_typography_AI3 /initialize get exec", "Adobe_IllustratorA_AI3 /initialize get exec", "%%EndSetup",
        ]
        parts = ["\n".join(out) + "\n"]
        labels = dict(order)
        for name in names:
            gray = 255 - int(round(255 * self._layer_k(name) / 100.0))
            visible = 0 if name in self.hidden else 1   # Lb 첫 값 = 보이기
            parts.append("%%AI5_BeginLayer\n%d 1 1 1 0 0 -1 %d %d %d Lb\n%s Ln\n0 A\n0 R\n"
                         % (visible, gray, gray, gray, _ps_string(("%s %s" % (name, labels[name] if get_lang() == "ko" else "")).strip())))   # 한국어 설명은 한국어 패널만 — CP949라 다른 언어 Illustrator에서 깨져 보인다
            parts.append("".join(self.layers.get(name, [])))
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


def get_cmyk(value):
    # type: (object) -> tuple
    """K 톤(0~100) 또는 #RRGGBB → (C, M, Y, K) 0~1. 회색은 K만 남는다(흑백 스타일 = K 전용 .ai). None은 무색."""
    if value is None:
        return (0.0, 0.0, 0.0, 0.0)
    if isinstance(value, str):
        r, g, b = (int(value[i:i + 2], 16) / 255.0 for i in (1, 3, 5))
        k = 1.0 - max(r, g, b)
        if k >= 1.0:
            return (0.0, 0.0, 0.0, 1.0)
        return ((1.0 - r - k) / (1.0 - k), (1.0 - g - k) / (1.0 - k), (1.0 - b - k) / (1.0 - k), k)
    return (0.0, 0.0, 0.0, float(value) / 100.0)


def get_layer_paint(name, style):
    # type: (str, dict) -> tuple
    """BM 레이어 → (칠, 선). 도면 스타일 요소에 대응하는 레이어는 스타일 색, 나머지(지적·등고선·격자·도로경계 등)는 BM_LAYERS K톤.
    00 프레임은 가구(블록) 색으로 칠해 그 위 흰 도로면이 가로 패턴을 만든다. 건물 층수 4구간은 건물 색에서 글자색 쪽으로 진해진다."""
    fill_k, line_k = _layer_style(name)
    if style is None:
        return fill_k, line_k
    mix = sheet_svg.get_mixed_color
    paints = {"00_frame_scale": (style["block"], style["ink"]), "01_water": (style["water"], None), "02_green": (style["green"], None),
              "03_road_surface": (style["road"], None), "06_rail": (None, style["rail"]), "10_site": (None, style["site"]),
              "12_labels": (None, style["ink"])}
    edge = mix(style["building"], style["ink"], 0.3)
    for index, band in enumerate(("07_bldg_low", "07_bldg_mid", "07_bldg_high", "07_bldg_tower")):
        paints[band] = (mix(style["building"], style["ink"], 0.12 * index), edge)
    return paints.get(name, (fill_k, line_k))


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
    style = sheet_svg.get_style(options)

    def polygon(fill_layer, edge_layer, geometry):
        fill_layer = fill_layer if fill_layer in wanted else None
        edge_layer = edge_layer if edge_layer in wanted else None
        if not fill_layer and not edge_layer:
            return
        layer = fill_layer or edge_layer
        fill_k = get_layer_paint(fill_layer, style)[0] if fill_layer else None
        line_k = get_layer_paint(edge_layer, style)[1] if edge_layer else None
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
        k = line_k if line_k is not None else get_layer_paint(layer, style)[1]
        for coords in parts:
            for piece in get_clipped_lines([(float(p[0]), float(p[1])) for p in coords], bbox):
                writer.line(layer, piece, k, get_line_width_mm(layer, scale))

    def text(layer, content, x, y):
        content = (content or "").strip()
        if not content or layer not in wanted or not (bbox[0] <= x <= bbox[2] and bbox[1] <= y <= bbox[3]):
            return
        mm, ref_scale = constants.BM_TEXT_MM[layer]
        writer.text(layer, content, x, y, mm * ref_scale / float(scale), get_layer_paint(layer, style)[1] or 100.0)

    # 00 프레임
    frame = [(bbox[0], bbox[1]), (bbox[2], bbox[1]), (bbox[2], bbox[3]), (bbox[0], bbox[3])]
    frame_fill, frame_line = get_layer_paint("00_frame_scale", style)
    writer.polygon("00_frame_scale", [frame], frame_fill, frame_line, get_line_width_mm("00_frame_scale", scale))
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
    # 합필 — 대상 필지의 지적선·지번은 꺼 둔 10b(합필 전 필지)로. 합친 덩어리(site_rings)가 곧 필지다
    merged = {lot.pnu for lot in prepared.target_lots} if getattr(prepared, "mode", "lots") == "lots" and len(prepared.target_lots) > 1 else set()
    for lot in list(prepared.target_lots) + list(prepared.near_lots):
        if not _hits(lot, bbox):
            continue
        if lot.land_category in constants.LAND_CATEGORIES_WATER:
            polygon("01_water", None, lot.geometry)
        elif constants.SHEET_LAND_CATEGORY_KEYS.get(lot.land_category) in ("park", "forest"):
            polygon("02_green", None, lot.geometry)
        elif lot.land_category == constants.LAND_CATEGORY_ROAD:
            polygon("03_road_surface", None, lot.geometry)
        polygon("02b_landuse", "10b_site_lots" if lot.pnu in merged else "08_parcel", lot.geometry)
        parts = _get_parts(lot.geometry)
        if not parts:
            continue
        outer = max((part[0] for part in parts), key=non_rhino_utils.get_ring_area)
        if lot.lot_number:
            cx, cy = get_ring_centroid(outer)
            text("10b_site_lots" if lot.pnu in merged else "08b_parcel_no", lot.lot_number, cx, cy)
        if lot.pnu in targets:
            polygon(None, "10_site", {"type": "Polygon", "coordinates": [outer]})
    for ring in site_rings:
        polygon(None, "10_site", {"type": "Polygon", "coordinates": [ring]})
    if merged and len(site_rings) == 1:   # 합필 지번 — '333-139 외 1필지'(토지조서 관행)
        text("08b_parcel_no", tr("{0} 외 {1}필지", prepared.target_lots[0].lot_number, len(merged) - 1), *get_ring_centroid(site_rings[0]))
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


# ── 도면 SVG → 레이어 .ai (sheet_svg가 쓴 SVG만 읽는다) ──────────────────

_PATH_TOKEN = re.compile(r"[MLlHhVvZz]|-?\d*\.?\d+")
_CIRCLE_PATH = re.compile(r"M(-?[\d.]+) (-?[\d.]+)a([\d.]+)")
_INHERIT = ("fill", "stroke", "stroke-width", "fill-opacity", "stroke-dasharray", "font-size", "font-weight", "text-anchor")
SVG_NS = "{http://www.w3.org/2000/svg}"


def get_svg_path_rings(d):
    # type: (str) -> list
    """sheet_svg path d → [(점들, 닫힘)]. 쓰는 명령(M·L·l·H·V·Z)만, 원(_circle_d의 호 두 개)은 48각형."""
    circle = _CIRCLE_PATH.match(d)
    if circle and "a" in d:
        x, y, r = (float(v) for v in circle.groups())
        cx = x + r
        return [([(cx + r * math.cos(2 * math.pi * i / 48), y + r * math.sin(2 * math.pi * i / 48)) for i in range(48)], True)]
    rings, pts, cmd, x, y = [], None, "M", 0.0, 0.0
    tokens, i = _PATH_TOKEN.findall(d), 0
    while i < len(tokens):
        token = tokens[i]
        if token.isalpha():
            cmd = token
            i += 1
            if cmd in "Zz":
                if pts:
                    rings.append((pts, True))
                pts = None
            continue
        if cmd == "M":
            if pts:
                rings.append((pts, False))
            x, y = float(tokens[i]), float(tokens[i + 1])
            pts, i, cmd = [(x, y)], i + 2, "L"
            continue
        if cmd in "Ll":
            dx, dy = float(tokens[i]), float(tokens[i + 1])
            x, y = (x + dx, y + dy) if cmd == "l" else (dx, dy)
            i += 2
        elif cmd in "Hh":
            x = x + float(tokens[i]) if cmd == "h" else float(tokens[i])
            i += 1
        elif cmd in "Vv":
            y = y + float(tokens[i]) if cmd == "v" else float(tokens[i])
            i += 1
        else:
            i += 1
            continue
        if pts is None:
            pts = [(x, y)]
        else:
            pts.append((x, y))
    if pts:
        rings.append((pts, False))
    return rings


def _get_paint(value, opacity, paper):
    # type: (str, float, str) -> object
    """SVG 칠 값 → #RRGGBB 또는 None. 해치 패턴은 해치 선 색을 옅게, 반투명(레거시 .ai에 투명도 없음)은 0.5 미만이면 칠 없음·이상이면 종이와 섞는다."""
    if not value or value in ("none", "transparent"):
        return None
    if value.startswith("url("):
        value = sheet_svg.get_mixed_color(constants.SHEET_HATCH["landlocked"]["stroke"], paper, 0.7)
    if not value.startswith("#") or len(value) != 7:
        return None
    if opacity < 0.5:
        return None
    return value.upper() if opacity >= 0.999 else sheet_svg.get_mixed_color(value.upper(), paper, 1.0 - opacity)


def write_svg_ai(svg_text, path, title):
    # type: (str, str, str) -> int
    """sheet_svg 도면 한 장(SVG 문자열) → 레거시 .ai. 지도 칸 안 그룹(base_*·theme_<키>·extent·site·labels…)과 정보 열이 각각 레이어.

    지도 칸 밖으로 나간 면·선은 칸 사각형으로 자른다(SVG clipPath 대신). 범위 밖 흐리기(mask)는 투명도라 뺀다 — Illustrator에서 투명도로 다시 얹는다.
    빈 theme_<키> 그룹(틀 시트)은 빈 레이어로 남긴다. 반환: 쓴 레이어 수."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(svg_text)
    width, height = float(root.get("width").rstrip("m")), float(root.get("height").rstrip("m"))
    writer = AiWriter((0.0, 0.0, width, height), 1000, (width, height))   # 1 단위 = 1 mm, y는 뒤집어 넣는다
    paper = "#FFFFFF"
    clip_box, map_offset = None, (0.0, 0.0)
    for node in root.iter(SVG_NS + "rect"):
        if node.get("id") == "paper":
            paper = node.get("fill") or paper
    for node in root.iter(SVG_NS + "clipPath"):
        rect = node.find(SVG_NS + "rect")
        clip_box = (0.0, 0.0, float(rect.get("width")), float(rect.get("height")))
    order, seen, keep_alive = [], set(), []   # keep_alive: id() 캐시 키가 재사용되지 않게 스타일 dict를 붙잡아 둔다

    def layer_of(name):
        if name not in seen:
            seen.add(name)
            order.append((name, ""))
            writer.layers.setdefault(name, [])
        return name

    def to_ai(pt, offset):
        return (pt[0] + offset[0], height - (pt[1] + offset[1]))

    paints = {}   # id(스타일 dict) → (칠, 선, 굵기, 파선) — 같은 그룹 path들이 한 dict를 나눠 쓴다

    def emit(node, style, layer, offset, in_map):
        tag = node.tag.replace(SVG_NS, "")
        paint = paints.get(id(style))
        if paint is None:
            stroke = _get_paint(style.get("stroke"), 1.0, paper)
            paint = paints[id(style)] = (_get_paint(style.get("fill", "#000000"), float(style.get("fill-opacity", 1)), paper), stroke,
                                         float(style.get("stroke-width", 1) or 0) if stroke else 0.0,
                                         [float(v) for v in str(style.get("stroke-dasharray", "")).replace(",", " ").split()] or None)
        fill, stroke, width_mm, dash = paint
        rings = []
        if tag == "path":
            rings = get_svg_path_rings(node.get("d", ""))
        elif tag == "rect":
            x, y, w, h = (float(node.get(k, 0)) for k in ("x", "y", "width", "height"))
            rings = [([(x, y), (x + w, y), (x + w, y + h), (x, y + h)], True)]
        elif tag == "circle":
            cx, cy, r = (float(node.get(k)) for k in ("cx", "cy", "r"))
            rings = [([(cx + r * math.cos(2 * math.pi * i / 32), cy + r * math.sin(2 * math.pi * i / 32)) for i in range(32)], True)]
        elif tag == "line":
            rings = [([(float(node.get("x1")), float(node.get("y1"))), (float(node.get("x2")), float(node.get("y2")))], False)]
        elif tag == "text":
            x, y = float(node.get("x")), float(node.get("y"))
            if in_map and clip_box and not (clip_box[0] <= x <= clip_box[2] and clip_box[1] <= y <= clip_box[3]):
                return
            size = float(style.get("font-size", 2.4))
            writer.text(layer_of(layer), node.text or "", *to_ai((x, y), offset), size_mm=size * constants.AI_CAP_HEIGHT_RATIO,
                        k=fill or "#000000", anchor=style.get("text-anchor", "start"), baseline=True)
            return
        closed = [pts for pts, is_closed in rings if is_closed and len(pts) >= 3]
        opened = [pts for pts, is_closed in rings if not is_closed and len(pts) >= 2]
        if in_map and clip_box:   # 칸 안에 통째로 있으면 자르지 않는다(대부분 — 건물·필지)
            inside = lambda pts: all(clip_box[0] <= p[0] <= clip_box[2] and clip_box[1] <= p[1] <= clip_box[3] for p in pts)
            closed = [r for r in (r if inside(r) else sheet_svg.get_clipped_ring(r, clip_box) for r in closed) if len(r) >= 3]
            opened = [piece for pts in opened for piece in ([pts] if inside(pts) else get_clipped_lines(pts, clip_box))]
        if closed and (fill or stroke):
            ai_rings = [[to_ai(p, offset) for p in ring] for ring in closed]
            holes = [sum(1 for j, other in enumerate(ai_rings) if j != i and non_rhino_utils.is_point_in_ring(ring[0][0], ring[0][1], other)) % 2 == 1
                     for i, ring in enumerate(ai_rings)] if len(ai_rings) > 1 else None
            writer.polygon(layer_of(layer), ai_rings, fill, stroke, width_mm, dash, holes)
        for pts in opened:
            if stroke:
                writer.line(layer_of(layer), [to_ai(p, offset) for p in pts], stroke, width_mm, dash)

    def walk(node, style, layer, offset, in_map, depth):
        tag = node.tag.replace(SVG_NS, "")
        if tag in ("defs", "clipPath", "pattern"):
            return
        if tag != "path" or len(node.attrib) > 1:   # 칠·선을 새로 정하는 노드만 스타일을 새로 만든다
            style = dict(style, **{k: node.get(k) for k in _INHERIT if node.get(k) is not None})
            keep_alive.append(style)
        node_id = node.get("id") or ""
        if node_id == "mask":
            return
        if tag == "g":
            if node_id == "map":
                transform = re.match(r"translate\(([-\d.]+) ([-\d.]+)\)", node.get("transform", ""))
                offset = (float(transform.group(1)), float(transform.group(2))) if transform else offset
                in_map, child_layer = True, None
            elif in_map and (layer is None or node_id.startswith("theme_")):
                child_layer = node_id or layer
            else:
                child_layer = layer or node_id or "info"
            if node_id.startswith("theme_") and len(node) == 0:
                layer_of(node_id)   # 틀 시트 — 빈 레이어
            if node.get("display") == "none" and child_layer:
                writer.hidden.add(child_layer)   # 합필 전 필지(site_lots) — 꺼진 레이어
            for child in node:
                walk(child, style, child_layer, offset, in_map, depth + 1)
            return
        emit(node, style, layer or node_id or ("map" if in_map else "frame"), offset, in_map)

    for child in root:   # <svg> 바로 아래 — paper·map·info·map_frame이 각자 레이어
        walk(child, {k: root.get(k) for k in _INHERIT if root.get(k) is not None}, None, (0.0, 0.0), False, 0)
    return writer.write(path, title, order)
