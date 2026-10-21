"""Rhino에 의존하지 않는 범용 유틸을 제공한다.

좌표·GeoJSON 연산처럼 Rhino 없이 계산할 수 있는 것을 모은다.
이 모듈은 Python 딕셔너리·목록·숫자만 다루며 Rhino를 import하지 않는다.
Rhino 커브·벡터·Brep을 다루는 연산은 ``utils.py``에 둔다.
좌표 단위를 임의로 변환하지 않으며 프로젝트 내부 좌표는 m로 유지한다.
"""

import math
import re
import os

import constants


def get_output_lang(options):
    # type: (dict) -> str
    """options.output_lang → 지원하는 언어 코드(constants.OUTPUT_LANGS), 아니면 기본."""
    lang = (options or {}).get("output_lang")
    return lang if lang in constants.OUTPUT_NAMES else constants.OUTPUT_LANG_DEFAULT


def get_output_name(key, lang, sub=None):
    # type: (str, str, str) -> str
    """결과물 이름 한 칸 — constants.OUTPUT_NAMES[lang][key](sub가 있으면 그 안의 sub). 그 언어에 없으면 영어, 영어에도 없으면 key."""
    for code in (lang, "en"):
        value = constants.OUTPUT_NAMES.get(code, {}).get(key)
        if sub is not None:
            value = (value or {}).get(sub) if isinstance(value, dict) else None
        if value:
            return value
    return sub or key


def get_sheet_label(sheet_key, lang):
    # type: (str, str) -> str
    """도면 이름 — ko는 SHEET_CATALOG 이름, en은 영문 부제, 다른 언어는 OUTPUT_NAMES[lang]['sheets'](없으면 영문)."""
    row = next((r for r in constants.SHEET_CATALOG if r[1] == sheet_key), None)
    if row is None:
        return sheet_key
    if lang == "ko":
        return row[2]
    named = (constants.OUTPUT_NAMES.get(lang, {}).get("sheets") or {}).get(sheet_key)
    return named or row[3]


def get_safe_file_part(text):
    # type: (str) -> str
    """파일·폴더 이름 한 조각 — OS가 막는 문자와 '·,()'를 지우고 빈칸은 '_'로. 한글·한자·가나·악센트 문자는 둔다."""
    text = re.sub(r'[\\/:*?"<>|·,()]+', "", str(text or ""))
    return re.sub(r"\s+", "_", text.strip())


def get_polygon_parts_from_geojson(geometry):
    # type: (dict) -> list
    """GeoJSON Polygon 또는 MultiPolygon을 다각형별 링 목록으로 나눈다.

    입력:
        geometry: ``type``과 ``coordinates``를 가진 GeoJSON 형상 딕셔너리.
    처리:
        Polygon은 한 다각형으로 감싸고 MultiPolygon은 기존 다각형 목록을 유지한다.
    출력:
        ``[polygon][ring][point]`` 구조의 다각형 목록.
        지원하지 않는 형식이면 ValueError를 발생시킨다.
    """
    geometry_type = geometry.get("type")
    coordinates = geometry.get("coordinates") or []
    if geometry_type == "Polygon":
        return [coordinates]
    if geometry_type == "MultiPolygon":
        return list(coordinates)
    raise ValueError("지원하지 않는 GeoJSON 형상: %s" % geometry_type)


def get_bounds_from_geojson(geometry):
    # type: (dict) -> tuple
    """GeoJSON 형상의 XY 경계값을 구한다.

    입력:
        geometry: Polygon 또는 MultiPolygon GeoJSON 형상 딕셔너리.
    처리:
        모든 링의 XY 좌표를 순회해 축별 최솟값과 최댓값을 찾는다.
    출력:
        ``(min_x, max_x, min_y, max_y)`` — **구 순서**(review_map 호환용). 새 코드는 ``get_bbox``를 쓴다.
        좌표가 없으면 ValueError를 발생시킨다.
    """
    xs = []
    ys = []
    for polygon in get_polygon_parts_from_geojson(geometry):
        for ring in polygon:
            for point in ring:
                xs.append(float(point[0]))
                ys.append(float(point[1]))
    if not xs:
        raise ValueError("GeoJSON 형상에 좌표가 없습니다")
    return min(xs), max(xs), min(ys), max(ys)


def get_merged_bounds(bounds_values):
    # type: (list) -> tuple
    """여러 XY 경계값을 하나로 합친다.

    입력:
        bounds_values: ``(min_x, max_x, min_y, max_y)`` 목록.
    처리:
        모든 경계의 축별 최솟값과 최댓값을 구한다.
    출력:
        전체를 포함하는 ``(min_x, max_x, min_y, max_y)``.
        입력이 비었으면 ValueError를 발생시킨다.
    """
    if not bounds_values:
        raise ValueError("합칠 경계값이 없습니다")
    return (
        min(float(bounds[0]) for bounds in bounds_values),
        max(float(bounds[1]) for bounds in bounds_values),
        min(float(bounds[2]) for bounds in bounds_values),
        max(float(bounds[3]) for bounds in bounds_values),
    )


def get_center_xy_from_bounds(bounds):
    # type: (tuple) -> tuple
    """XY 경계값의 중심점을 구한다.

    입력:
        bounds: ``(min_x, max_x, min_y, max_y)`` 경계값.
    처리:
        X축과 Y축의 최솟값·최댓값 평균을 계산한다.
    출력:
        ``(center_x, center_y)`` 중심 좌표.
    """
    min_x, max_x, min_y, max_y = bounds
    return (
        (float(min_x) + float(max_x)) * 0.5,
        (float(min_y) + float(max_y)) * 0.5,
    )


def get_text_width_em(text):
    # type: (str) -> float
    """글자 폭 어림(em) — 한글·한자 1.0, 그 밖 0.55. 가운데 정렬·줄바꿈용(basemap_ai·sheet_svg)."""
    return sum(1.0 if ord(ch) > 0x2000 else 0.55 for ch in text)


def get_ring_area(ring):
    # type: (list) -> float
    """좌표 링이 감싸는 면적을 구한다.

    입력:
        ring: ``[x, y]`` 좌표 목록. 첫 점과 끝 점이 같아도 되고 달라도 된다.
    처리:
        신발끈 공식으로 부호 있는 면적을 더한 뒤 절댓값을 취한다.
        링 방향(CW/CCW)에 상관없이 같은 값이 나온다.
    출력:
        면적. 점이 3개 미만이면 0.0.
    """
    if len(ring) < 3:
        return 0.0
    doubled_area = 0.0
    previous = ring[-1]
    for point in ring:
        doubled_area += (
            float(previous[0]) * float(point[1])
            - float(point[0]) * float(previous[1])
        )
        previous = point
    return abs(doubled_area) * 0.5


# ═════════════════════════════════════════════════════════
# EPSG:5186 ↔ WGS84 좌표 변환
# ═════════════════════════════════════════════════════════
# EPSG:5186 (Korea 2000 / Central Belt 2010): GRS80 타원체, 원점 위도 38·경도
# 127, 축척 1. 횡메르카토르 Karney 급수(6차) 구현 — 왕복 오차 1e-14도 수준.
A_GRS80 = 6378137.0  # GRS80 장반경 m
F_GRS80 = 1.0 / 298.257222101  # GRS80 편평률
KOREA_TM = (38.0, 127.0, 200000.0, 600000.0)   # EPSG:5186 원점 위도·경도, 가산치 E·N
KOREA_LNGLAT_BOUNDS = (124.0, 33.0, 132.0, 39.0)  # 한국 판정 경위도 사각형(서·남·동·북) — 제주·울릉 포함, 북한 일부도 들어간다
LAT0, LON0, FALSE_E, FALSE_N = KOREA_TM  # 지금 투영 원점 (도)·가산치 m — set_projection이 바꾼다
n = F_GRS80 / (2.0 - F_GRS80)  # 제3편평률
A_BAR = A_GRS80 / (1.0 + n) * (1.0 + n**2/4.0 + n**4/64.0 + n**6/256.0)
ALPHA = (  # 경위도 → 평면 급수 계수
    n/2 - 2*n**2/3 + 5*n**3/16 + 41*n**4/180 - 127*n**5/288 + 7891*n**6/37800,
    13*n**2/48 - 3*n**3/5 + 557*n**4/1440 + 281*n**5/630 - 1983433*n**6/1935360,
    61*n**3/240 - 103*n**4/140 + 15061*n**5/26880 + 167603*n**6/181440,
    49561*n**4/161280 - 179*n**5/168 + 6601661*n**6/7257600,
    34729*n**5/80640 - 3418889*n**6/1995840,
    212378941*n**6/319334400,
)
BETA = (  # 평면 → 경위도 역급수 계수
    n/2 - 2*n**2/3 + 37*n**3/96 - n**4/360 - 81*n**5/512 + 96199*n**6/604800,
    n**2/48 + n**3/15 - 437*n**4/1440 + 46*n**5/105 - 1118711*n**6/3870720,
    17*n**3/480 - 37*n**4/840 - 209*n**5/4480 + 5569*n**6/90720,
    4397*n**4/161280 - 11*n**5/504 - 830251*n**6/7257600,
    4583*n**5/161280 - 108847*n**6/3991680,
    20648693*n**6/638668800,
)
E2 = F_GRS80 * (2.0 - F_GRS80)  # 제1이심률 제곱
E_SQRT = math.sqrt(E2)


def _get_xi_eta(lat_rad, lon_rad):
    # type: (float, float) -> tuple
    """경위도(라디안)를 정규화 투영좌표로 바꾼다.

    입력:
        lat_rad, lon_rad: 위도·경도 (라디안).
    처리:
        등각위도로 바꾼 뒤 Karney 급수(ALPHA)로 보정한다.
    출력:
        ``(xi, eta)`` 정규화 투영좌표.
    """
    s = math.sin(lat_rad)
    t = math.sinh(math.atanh(s) - E_SQRT * math.atanh(E_SQRT * s))
    dlon = lon_rad - math.radians(LON0)
    xi_p = math.atan2(t, math.cos(dlon))
    eta_p = math.asinh(math.sin(dlon) / math.hypot(t, math.cos(dlon)))
    xi = xi_p + sum(a * math.sin(2*(j+1)*xi_p) * math.cosh(2*(j+1)*eta_p) for j, a in enumerate(ALPHA))
    eta = eta_p + sum(a * math.cos(2*(j+1)*xi_p) * math.sinh(2*(j+1)*eta_p) for j, a in enumerate(ALPHA))
    return xi, eta


XI0 = _get_xi_eta(math.radians(LAT0), math.radians(LON0))[0]  # 원점 위도의 xi
PROJECTION_ENV = "UDT_PROJECTION_ORIGIN"   # 해외 대상지 원점 "경도,위도" — set_projection 참고


def get_tm_from_wgs84(lng, lat):
    # type: (float, float) -> tuple
    """WGS84 경위도를 EPSG:5186 평면좌표로 변환한다.

    입력:
        lng, lat: WGS84 경도·위도 (도).
    처리:
        Karney 급수로 횡메르카토르 투영 후 가산치를 더한다.
    출력:
        ``(x, y)`` EPSG:5186 좌표 m.
    """
    xi, eta = _get_xi_eta(math.radians(lat), math.radians(lng))
    return FALSE_E + A_BAR * eta, FALSE_N + A_BAR * (xi - XI0)


def get_wgs84_from_tm(x, y):
    # type: (float, float) -> tuple
    """EPSG:5186 평면좌표를 WGS84 경위도로 변환한다.

    입력:
        x, y: EPSG:5186 좌표 m.
    처리:
        역급수로 정규화 좌표를 풀고 위도는 뉴턴 반복으로 수렴시킨다.
    출력:
        ``(lng, lat)`` WGS84 경도·위도 (도).
    """
    xi = (y - FALSE_N) / A_BAR + XI0
    eta = (x - FALSE_E) / A_BAR
    xi_p = xi - sum(b * math.sin(2*(j+1)*xi) * math.cosh(2*(j+1)*eta) for j, b in enumerate(BETA))
    eta_p = eta - sum(b * math.cos(2*(j+1)*xi) * math.sinh(2*(j+1)*eta) for j, b in enumerate(BETA))
    tau_p = math.tan(math.atan2(math.sin(xi_p), math.hypot(math.sinh(eta_p), math.cos(xi_p))))
    tau = tau_p
    for _ in range(10):
        s = tau / math.sqrt(1.0 + tau * tau)
        sig = math.sinh(E_SQRT * math.atanh(E_SQRT * s))
        taui = tau * math.sqrt(1.0 + sig * sig) - sig * math.sqrt(1.0 + tau * tau)
        dtau = (tau_p - taui) * (1.0 + (1.0 - E2) * tau * tau) / ((1.0 - E2) * math.sqrt((1.0 + taui * taui) * (1.0 + tau * tau)))
        tau += dtau
        if abs(dtau) < 1e-15:
            break
    lat_out = math.degrees(math.atan(tau))
    lng_out = LON0 + math.degrees(math.atan2(math.sinh(eta_p), math.cos(xi_p)))
    return lng_out, lat_out


def get_tile_xy(lng, lat, zoom):
    # type: (float, float, int) -> tuple
    """경위도 → 웹 메르카토르 타일 좌표(실수). 정수부가 타일 번호."""
    n = 2 ** zoom
    return (lng + 180.0) / 360.0 * n, (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 * n


def get_lnglat_from_tile(x, y, zoom):
    # type: (float, float, int) -> tuple
    """웹 메르카토르 타일 좌표(실수) → 경위도 (get_tile_xy 역변환)."""
    n = 2 ** zoom
    return x / n * 360.0 - 180.0, math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))


def get_tile_m_per_px(lat, zoom):
    # type: (float, int) -> float
    """위도 lat에서 줌 zoom 타일(256 px) 한 픽셀의 지상 길이 m. 웹 메르카토르 구 반지름 = WGS84 장반경(GRS80과 같은 값)."""
    return 2.0 * math.pi * A_GRS80 * math.cos(math.radians(lat)) / (256.0 * 2 ** zoom)


def is_korea(lng, lat):
    # type: (float, float) -> bool
    """경위도가 한국(국내 DB·EPSG:5186 범위) 안인지. 대략의 경위도 사각형으로만 본다."""
    west, south, east, north = KOREA_LNGLAT_BOUNDS
    return west <= lng <= east and south <= lat <= north


def set_projection(lng=None, lat=None):
    # type: (float, float) -> None
    """이후 get_tm_from_wgs84·get_wgs84_from_tm이 쓸 횡메르카토르 원점을 정한다.

    입력: 대상지 중심 경위도. None이거나 한국 안이면 EPSG:5186(국내 DB 좌표계).
    처리: 해외면 대상지 중심(0.01° 반올림 — 같은 대상지는 늘 같은 원점)을 원점으로, 가산치 0인 지역 횡메르카토르(GRS80, 축척 1).
          원점은 환경변수 PROJECTION_ENV에도 적는다 — loader가 모듈을 다시 읽어도(전역 초기화) 같은 Rhino 세션에서는 유지된다.
          ponytail: 프로세스 전역 상태다. 패널 한 개가 대상지 하나를 다루는 동안만 유효 — 동시에 두 대상지를 다루면 원점 인자로 바꿀 것.
    출력: 없음.
    """
    if lng is None or lat is None or is_korea(lng, lat):
        os.environ.pop(PROJECTION_ENV, None)
    else:
        os.environ[PROJECTION_ENV] = "%.2f,%.2f" % (float(lng), float(lat))
    _apply_projection()


def _apply_projection():
    # type: () -> None
    """환경변수의 원점(없으면 EPSG:5186)을 모듈 전역에 적용한다. import 때도 부른다."""
    global LAT0, LON0, FALSE_E, FALSE_N, XI0
    value = os.environ.get(PROJECTION_ENV)
    if value:
        lng, lat = (float(v) for v in value.split(","))
        LAT0, LON0, FALSE_E, FALSE_N = lat, lng, 0.0, 0.0
    else:
        LAT0, LON0, FALSE_E, FALSE_N = KOREA_TM
    XI0 = _get_xi_eta(math.radians(LAT0), math.radians(LON0))[0]


_apply_projection()


def is_local_projection():
    # type: () -> bool
    """지금 원점이 해외 지역 횡메르카토르인지(= 국내 DB 대신 OSM을 쓴다)."""
    return (LAT0, LON0, FALSE_E, FALSE_N) != KOREA_TM


def get_crs_label():
    # type: () -> str
    """문서·메타에 적을 좌표계 이름."""
    if not is_local_projection():
        return "EPSG:5186"
    return "+proj=tmerc +lat_0=%.2f +lon_0=%.2f +k=1 +x_0=0 +y_0=0 +ellps=GRS80 +units=m" % (LAT0, LON0)


# ═════════════════════════════════════════════════════════
# 수치지형도 도엽번호 ↔ 경위도 범위
# ═════════════════════════════════════════════════════════

def get_topo_sheet_bounds(code):
    # type: (str) -> tuple
    """1:5000 도엽번호 → (left, bottom, right, top) 경위도.

    입력:
        code: 8자리 도엽번호. 예 ``"37705072"``.
    처리:
        앞 2자리 위도 정수, 3번째 자리 경도 끝자리(12x), 4~5자리 1:50000 색인(15′, 4×4 NW부터 행우선),
        6~8자리 1:5000 색인(1′30″, 10×10 NW부터 행우선). 성수 4도엽 SHP 도곽으로 검증했다.
    출력:
        ``(left, bottom, right, top)`` 도.
    """
    lat_deg = int(code[0:2])
    lon_deg = 120 + int(code[2])
    idx50 = int(code[3:5])
    idx5 = int(code[5:8])
    row50, col50 = (idx50 - 1) // 4, (idx50 - 1) % 4
    top50 = lat_deg + 1 - row50 * 0.25
    left50 = lon_deg + col50 * 0.25
    row5, col5 = (idx5 - 1) // 10, (idx5 - 1) % 10
    top = top50 - row5 * 0.025
    left = left50 + col5 * 0.025
    return left, top - 0.025, left + 0.025, top


def get_topo_sheet_code(lng, lat):
    # type: (float, float) -> str
    """경위도 한 점이 속한 1:5000 도엽번호. get_topo_sheet_bounds의 역함수."""
    lat_deg = int(lat)
    lon_deg = int(lng)
    row50 = int((lat_deg + 1 - lat) // 0.25)
    col50 = int((lng - lon_deg) // 0.25)
    top50 = lat_deg + 1 - row50 * 0.25
    left50 = lon_deg + col50 * 0.25
    row5 = int((top50 - lat) // 0.025)
    col5 = int((lng - left50) // 0.025)
    return "%02d%d%02d%03d" % (lat_deg, lon_deg % 10, row50 * 4 + col50 + 1, row5 * 10 + col5 + 1)


def get_topo_sheet_codes_in_bounds(lng0, lat0, lng1, lat1):
    # type: (float, float, float, float) -> list
    """경위도 사각형과 겹치는 1:5000 도엽번호 목록(정렬)."""
    codes = []
    lat = (lat0 // 0.025) * 0.025
    while lat < lat1:
        lng = (lng0 // 0.025) * 0.025
        while lng < lng1:
            codes.append(get_topo_sheet_code(lng + 0.0125, lat + 0.0125))
            lng += 0.025
        lat += 0.025
    return sorted(set(codes))


# ═════════════════════════════════════════════════════════
# 순수 기하 — PIP·격자·리샘플·방향·bbox·범위 링 (docs/code_map.md §5.0·§5.3)
# ═════════════════════════════════════════════════════════

def is_point_in_ring(x, y, ring):
    # type: (float, float, list) -> bool
    """점이 링 안에 있는지 판정한다(ray casting).

    입력:
        x, y: 점 좌표. ring: ``[(x, y)]`` 링. 닫힘 중복점이 있어도 된다.
    처리:
        +X 방향 반직선이 링의 변과 홀수 번 만나면 안.
    출력:
        안이면 True. 경계 위는 변의 방향에 따라 어느 쪽이든 나올 수 있다(면 분류용이라 상관없다).
    """
    inside = False
    px, py = ring[-1][0], ring[-1][1]
    for point in ring:
        qx, qy = point[0], point[1]
        if (qy > y) != (py > y) and x < (px - qx) * (y - qy) / (py - qy) + qx:
            inside = not inside
        px, py = qx, qy
    return inside


def is_point_in_polygon(x, y, rings):
    # type: (float, float, list) -> bool
    """점이 다각형(외곽 + 구멍) 안에 있는지 판정한다.

    입력:
        x, y: 점 좌표. rings: GeoJSON Polygon coordinates — ``rings[0]`` 외곽, 나머지 구멍.
    처리:
        외곽 안 AND 모든 구멍 밖. 도로 필지(가로망 도넛)의 구멍 안은 False.
    출력:
        bool.
    """
    if not rings or not is_point_in_ring(x, y, rings[0]):
        return False
    return not any(is_point_in_ring(x, y, hole) for hole in rings[1:])


class GridIndex(object):
    """bbox 격자 색인. 셀 크기 cell(m) — 면 분류는 constants.CLASSIFY_GRID.

    add(bounds, item): ``(min_x, min_y, max_x, max_y)``가 걸치는 모든 셀에 item을 넣는다.
    query(x, y): 그 점의 셀에 든 item 목록(후보 — bbox가 점을 품는 item은 전부 포함, 아닌 것도 섞인다).
    """

    def __init__(self, cell):
        # type: (float) -> None
        self.cell = float(cell)
        self._cells = {}

    def _key(self, x, y):
        # type: (float, float) -> tuple
        return int(math.floor(x / self.cell)), int(math.floor(y / self.cell))

    def add(self, bounds, item):
        # type: (tuple, object) -> None
        ix0, iy0 = self._key(bounds[0], bounds[1])
        ix1, iy1 = self._key(bounds[2], bounds[3])
        for ix in range(ix0, ix1 + 1):
            for iy in range(iy0, iy1 + 1):
                self._cells.setdefault((ix, iy), []).append(item)

    def query(self, x, y):
        # type: (float, float) -> list
        return list(self._cells.get(self._key(x, y), ()))


def get_resampled_ring(ring, step, closed=True):
    # type: (list, float, bool) -> list
    """링(또는 열린 폴리라인)을 점 간격 ≤ step이 되게 선형보간으로 조밀화한다.

    입력:
        ring: ``[(x, y)]`` 또는 ``[(x, y, z)]`` — 뒤 성분도 같이 보간한다. 닫힘 중복점이 있어도 된다.
        step: 최대 점 간격 m (등고선은 constants.TERRAIN_RESAMPLE).
        closed: True면 끝 점→첫 점 변도 리샘플. 등고선 LineString은 False.
    처리:
        원래 정점은 전부 유지하고 변마다 ceil(길이/step)−1개를 끼워 넣는다.
    출력:
        새 목록 ``[(x, y, ...)]``. 닫힘 중복점 없음. 입력은 바꾸지 않는다.
    """
    pts = [tuple(float(v) for v in p) for p in ring]
    if closed and len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 2:
        return pts
    out = []
    edges = range(len(pts)) if closed else range(len(pts) - 1)
    for i in edges:
        a, b = pts[i], pts[(i + 1) % len(pts)]
        n = max(1, int(math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step)))
        for k in range(n):
            t = k / float(n)
            out.append(tuple(a[j] + (b[j] - a[j]) * t for j in range(len(a))))
    if not closed:
        out.append(pts[-1])
    return out


def get_ring_orientation(ring):
    # type: (list) -> int
    """링의 회전 방향. 신발끈 부호 — +1 반시계(CCW), −1 시계(CW), 0 퇴화."""
    doubled = 0.0
    previous = ring[-1]
    for point in ring:
        doubled += float(previous[0]) * float(point[1]) - float(point[0]) * float(previous[1])
        previous = point
    return (doubled > 0) - (doubled < 0)


def _iter_xy(coordinates):
    # type: (list) -> object
    """GeoJSON coordinates(어떤 깊이든)를 (x, y)로 평탄화하는 제너레이터."""
    if coordinates and isinstance(coordinates[0], (int, float)):
        yield float(coordinates[0]), float(coordinates[1])
        return
    for child in coordinates:
        for xy in _iter_xy(child):
            yield xy


def get_bbox(geometry):
    # type: (dict) -> tuple
    """GeoJSON 형상의 경계상자 — 새 코드의 bbox 순서는 이것 하나.

    입력:
        geometry: Point·LineString·Polygon·Multi* GeoJSON 형상 dict(또는 coordinates 목록만).
    처리:
        좌표를 전부 평탄화해 축별 최소·최대.
    출력:
        ``(min_x, min_y, max_x, max_y)`` — context_db.load·lot_db.load_parcels_in_bounds·Prepared.bounds와 같은 순서.
        좌표가 없으면 ValueError.
    """
    coordinates = geometry.get("coordinates") if isinstance(geometry, dict) else geometry
    xs, ys = [], []
    for x, y in _iter_xy(coordinates or []):
        xs.append(x)
        ys.append(y)
    if not xs:
        raise ValueError("GeoJSON 형상에 좌표가 없습니다")
    return min(xs), min(ys), max(xs), max(ys)


def _get_convex_hull(points):
    # type: (list) -> list
    """단조 사슬 볼록껍질. 입력 [(x, y)], 출력 반시계 링(끝점 중복 없음). 공선이면 양 끝 2점."""
    pts = sorted(set((float(x), float(y)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower, upper = [], []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


def _get_circle_ring(cx, cy, radius, segments):
    # type: (float, float, float, int) -> list
    """중심·반지름의 정다각형 링(반시계, 끝점 중복 없음)."""
    return [(cx + radius * math.cos(2 * math.pi * i / segments), cy + radius * math.sin(2 * math.pi * i / segments))
            for i in range(segments)]


def _get_rounded_buffer(hull, radius):
    # type: (list, float) -> list
    """반시계 볼록 링을 radius만큼 바깥 오프셋한 링. 변은 평행 이동, 꼭짓점은 외접 호(90°당 EXTENT_ARC_SEGMENTS분할).

    호 점을 radius/cos(Δ/2)로 띄운 외접 다각형이라 링의 모든 변이 원래 꼭짓점에서 ≥ radius다
    (내접이면 현이 radius 안쪽으로 들어온다 — 500 m·7.5°에서 1 m). 볼록 입력이라 자기교차 없음.
    """
    n = len(hull)
    if n < 2:
        return _get_circle_ring(hull[0][0], hull[0][1], radius, constants.EXTENT_CIRCLE_SEGMENTS)
    ring = []
    for i in range(n):
        p0, p1, p2 = hull[i - 1], hull[i], hull[(i + 1) % n]
        a_in = math.atan2(p1[1] - p0[1], p1[0] - p0[0]) - math.pi / 2    # 들어오는 변의 바깥 법선(반시계 링 → 오른쪽)
        a_out = math.atan2(p2[1] - p1[1], p2[0] - p1[0]) - math.pi / 2
        while a_out < a_in:
            a_out += 2 * math.pi
        steps = max(1, int(math.ceil((a_out - a_in) / (math.pi / 2) * constants.EXTENT_ARC_SEGMENTS)))
        delta = (a_out - a_in) / steps
        outer = radius / math.cos(delta / 2)
        ring.append((p1[0] + radius * math.cos(a_in), p1[1] + radius * math.sin(a_in)))
        for k in range(steps):
            t = a_in + delta * (k + 0.5)
            ring.append((p1[0] + outer * math.cos(t), p1[1] + outer * math.sin(t)))
        ring.append((p1[0] + radius * math.cos(a_out), p1[1] + radius * math.sin(a_out)))
    return ring


def get_extent_ring(lot_rings, radius, shape):
    # type: (list, float, str) -> list
    """대상지 링들 → 컨텍스트 범위 링. 범위 폴리곤의 유일한 정의(code_map §5.0).

    입력:
        lot_rings: 대상 필지 외곽 링 목록 ``[[(x, y)], ...]`` EPSG:5186 m. radius: m. shape: buffer | circle | rect.
    처리:
        buffer = 전체 정점 볼록껍질을 radius만큼 둥글게 바깥 오프셋(_get_rounded_buffer).
        circle = 대상지 bbox 중심 원(EXTENT_CIRCLE_SEGMENTS각). rect = 대상지 bbox 중심 ± radius 정사각형(한 변 2 × radius —
        패널 '사각형 한 변'과 같은 뜻, 2026-10-19. 예전 bbox ± radius는 한 변이 대상지 폭만큼 더 커서 혼란).
    출력:
        ``[(x, y)]`` 반시계, 닫힘 중복점 없음. 알 수 없는 shape은 ValueError.
    """
    points = [(float(p[0]), float(p[1])) for ring in lot_rings for p in ring]
    if not points:
        raise ValueError("대상지 링에 좌표가 없습니다")
    min_x, min_y, max_x, max_y = get_bbox(points)
    if shape == "circle":
        return _get_circle_ring((min_x + max_x) / 2.0, (min_y + max_y) / 2.0, radius, constants.EXTENT_CIRCLE_SEGMENTS)
    if shape == "rect":
        cx, cy = (min_x + max_x) / 2.0, (min_y + max_y) / 2.0
        return [(cx - radius, cy - radius), (cx + radius, cy - radius), (cx + radius, cy + radius), (cx - radius, cy + radius)]
    if shape == "buffer":
        return _get_rounded_buffer(_get_convex_hull(points), radius)
    raise ValueError("알 수 없는 범위 shape: %s" % shape)


# ── 구역(area) 링 ─────────────────────────────────────────

def get_clean_ring(points):
    # type: (list) -> list
    """구역 링 정리 — 입력을 바꾸지 않고 새 링을 돌려준다.

    입력: ``[(x, y)]`` 점 목록(닫힘 중복점 있어도 됨).
    처리: 1 mm 안 연속 중복점 제거 → 끝의 닫힘 중복점 제거 → 반시계(CCW)로 맞춤.
    출력: ``[(x, y)]`` 반시계, 닫힘 중복점 없음.
    """
    ring = []
    for point in points:
        x, y = float(point[0]), float(point[1])
        if not ring or abs(ring[-1][0] - x) > 1e-3 or abs(ring[-1][1] - y) > 1e-3:
            ring.append((x, y))
    while len(ring) > 1 and abs(ring[0][0] - ring[-1][0]) <= 1e-3 and abs(ring[0][1] - ring[-1][1]) <= 1e-3:
        ring.pop()
    if get_ring_orientation(ring) < 0:
        ring.reverse()
    return ring


def get_merged_rings(polygons, tolerance):
    # type: (list, float) -> tuple
    """맞닿은 필지들을 합친다(합필). 입력은 바꾸지 않는다.

    입력: polygons ``[[바깥 링, 구멍 링, ...]]`` 세계좌표 m(GeoJSON Polygon coordinates 꼴). tolerance: 같은 점·같은 변으로 볼 거리 m.
    처리: 공공 지적은 이웃 경계가 정점 단위로 맞지 않는다(T자 정점·수 cm 틈·겹침 — 서울 표본 1,500묶음 중 0.3 %가 0.1~150 ㎡ 겹침).
          서울 표본 2,800묶음(2~13필지)에서 shapely 합집합과 덩어리 수·면적이 모두 같았다(2026-10-21).
          ① tolerance 안 정점을 한 점으로 모은다 ② 다른 필지 정점이 변에서 tolerance 안이면 그 변에 끼우고, 변끼리 교차하면 교차점을 양쪽에 끼운다
          ③ 바깥은 반시계·구멍은 시계로 두고 변을 고른다 — 반대 방향 같은 변(공유 경계)과 다른 필지 안의 변(겹침)은 지운다
          ④ 남은 변을 잇는다(갈림점에서는 가장 왼쪽으로 꺾는다) ⑤ 폭이 2 × tolerance 이하인 가는 조각은 버린다.
    출력: (바깥 링 목록 넓은 순, 구멍 링 목록). 바깥은 반시계, 구멍은 시계, 닫힘 중복점 없음. 떨어진 덩어리는 바깥 링이 여럿.
    """
    pts, grid = [], {}

    def snap(x, y):
        ix, iy = int(math.floor(x / tolerance)), int(math.floor(y / tolerance))
        for key in ((ix + i, iy + j) for i in (-1, 0, 1) for j in (-1, 0, 1)):
            for k in grid.get(key, ()):
                if math.hypot(pts[k][0] - x, pts[k][1] - y) <= tolerance:
                    return k
        pts.append((x, y))
        grid.setdefault((ix, iy), []).append(len(pts) - 1)
        return len(pts) - 1

    def get_t(k, a, b):   # 정점 k가 변 ab 위(tolerance 안)면 변 위치 0~1, 아니면 None
        (ax, ay), (bx, by), (px, py) = pts[a], pts[b], pts[k]
        dx, dy = bx - ax, by - ay
        length2 = dx * dx + dy * dy
        t = ((px - ax) * dx + (py - ay) * dy) / length2
        if k in (a, b) or not 0.0 < t < 1.0 or abs((px - ax) * dy - (py - ay) * dx) > tolerance * math.sqrt(length2):
            return None
        return t

    rings, owners, shapes = [], [], {}   # 정점 번호 링(바깥 반시계·구멍 시계), 그 필지 번호, 필지 번호 → 겹침 판정용 좌표 링
    for owner, polygon in enumerate(polygons):
        for hole, ring in enumerate(polygon):
            ids = []
            for p in ring:
                k = snap(float(p[0]), float(p[1]))
                if not ids or ids[-1] != k:
                    ids.append(k)
            while len(ids) > 1 and ids[0] == ids[-1]:
                ids.pop()
            if len(ids) >= 3:
                ccw = get_ring_orientation([pts[k] for k in ids]) > 0
                rings.append(ids if ccw == (hole == 0) else ids[::-1])
                owners.append(owner)
                shapes.setdefault(owner, []).append([pts[k] for k in rings[-1]])
    boxes = [get_bbox([pts[k] for k in ids]) for ids in rings]
    shape_boxes = {owner: get_bbox(shape[0]) for owner, shape in shapes.items()}
    extra = [[[] for _ in ids] for ids in rings]   # 변마다 끼울 (t, 정점 번호)
    for r, s in ((r, s) for r in range(len(rings)) for s in range(r + 1, len(rings))):
        if owners[r] == owners[s] or boxes[r][0] > boxes[s][2] + tolerance or boxes[s][0] > boxes[r][2] + tolerance \
                or boxes[r][1] > boxes[s][3] + tolerance or boxes[s][1] > boxes[r][3] + tolerance:
            continue
        for i, a in enumerate(rings[r]):
            b = rings[r][(i + 1) % len(rings[r])]
            x0, x1 = min(pts[a][0], pts[b][0]) - tolerance, max(pts[a][0], pts[b][0]) + tolerance
            y0, y1 = min(pts[a][1], pts[b][1]) - tolerance, max(pts[a][1], pts[b][1]) + tolerance
            for j, c in enumerate(rings[s]):
                d = rings[s][(j + 1) % len(rings[s])]
                if max(pts[c][0], pts[d][0]) < x0 or min(pts[c][0], pts[d][0]) > x1 or max(pts[c][1], pts[d][1]) < y0 or min(pts[c][1], pts[d][1]) > y1:
                    continue
                t_c, t_a = get_t(c, a, b), get_t(a, c, d)   # 끝점 d·b는 다음 변의 시작점으로 확인된다
                if t_c is not None:
                    extra[r][i].append((t_c, c))
                if t_a is not None:
                    extra[s][j].append((t_a, a))
                if t_c is None and t_a is None and len({a, b, c, d}) == 4 and _segments_cross(pts[a], pts[b], pts[c], pts[d]):
                    (ax, ay), (bx, by), (cx, cy), (dx, dy) = pts[a], pts[b], pts[c], pts[d]
                    u = ((cx - ax) * (dy - cy) - (cy - ay) * (dx - cx)) / ((bx - ax) * (dy - cy) - (by - ay) * (dx - cx))
                    k = snap(ax + (bx - ax) * u, ay + (by - ay) * u)
                    for ring_index, edge_index, p, q in ((r, i, a, b), (s, j, c, d)):
                        t = get_t(k, p, q)
                        if t is not None:
                            extra[ring_index][edge_index].append((t, k))
    present = {}   # 방향 변 → [나온 수, 그 변을 가진 필지 번호들]
    for r, ids in enumerate(rings):
        walk = []
        for i, a in enumerate(ids):
            walk.append(a)
            inserted = {}
            for t, k in extra[r][i]:
                inserted.setdefault(k, t)
            walk += [k for k in sorted(inserted, key=inserted.get) if k != walk[-1]]
        for i, a in enumerate(walk):
            b = walk[(i + 1) % len(walk)]
            if a != b:
                entry = present.setdefault((a, b), [0, set()])
                entry[0] += 1
                entry[1].add(owners[r])
    out_edges = {}
    for (a, b), (n, own) in present.items():
        if n <= present.get((b, a), [0])[0]:
            continue   # 공유 경계(반대 방향 변과 짝). 남는 같은 방향 변은 하나만 — 접힌 경계(1174010500103710009 — 이웃 필지가 메운 쐐기)·겹침
        mx, my = (pts[a][0] + pts[b][0]) * 0.5, (pts[a][1] + pts[b][1]) * 0.5
        if any(owner not in own and box[0] <= mx <= box[2] and box[1] <= my <= box[3] and is_point_in_polygon(mx, my, shapes[owner])
               for owner, box in shape_boxes.items()):
            continue   # 다른 필지와 겹친 부분
        out_edges.setdefault(a, []).append(b)

    def turn(prev, cur, nxt):   # 들어온 방향 대비 꺾는 각(왼쪽 +). 되돌아가기는 맨 끝
        if nxt == prev:
            return -4.0
        (px, py), (cx, cy), (nx, ny) = pts[prev], pts[cur], pts[nxt]
        ux, uy, vx, vy = cx - px, cy - py, nx - cx, ny - cy
        return math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)

    outers, holes = [], []
    for start in list(out_edges):
        while out_edges[start]:
            ring, prev, cur = [start], start, out_edges[start].pop()
            while cur != start and out_edges.get(cur):
                ring.append(cur)
                nexts = out_edges[cur]
                prev, cur = cur, nexts.pop(max(range(len(nexts)), key=lambda j: turn(prev, cur, nexts[j])))
            coords = get_clean_ring([pts[k] for k in ring])
            perimeter = sum(math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in zip(coords, coords[1:] + coords[:1]))
            if cur == start and len(coords) >= 3 and get_ring_area(coords) > tolerance * perimeter:   # 가는 조각(틈·겹침 찌꺼기)은 버린다
                (outers if get_ring_orientation([pts[k] for k in ring]) > 0 else holes).append(coords)
    return sorted(outers, key=get_ring_area, reverse=True), [ring[::-1] for ring in holes]


def _segments_cross(a, b, c, d):
    # type: (tuple, tuple, tuple, tuple) -> bool
    """선분 ab와 cd가 서로의 내부에서 교차하는가(끝점 접촉·평행 겹침은 제외 — 이웃 변의 공유점 때문)."""
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2, d3, d4 = cross(c, d, a), cross(c, d, b), cross(a, b, c), cross(a, b, d)
    return ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 != 0 and d2 != 0 and d3 != 0 and d4 != 0


def has_self_intersection(ring):
    # type: (list) -> bool
    """닫힌 링(닫힘 중복점 없음)의 변끼리 교차가 있는가. n² — 꼭짓점 상한 AREA_MAX_VERTICES로 막는다."""
    n = len(ring)
    edges = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    boxes = [(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])) for a, b in edges]
    for i in range(n):
        bi = boxes[i]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:   # 첫 변과 끝 변은 이웃
                continue
            bj = boxes[j]
            if bi[0] > bj[2] or bj[0] > bi[2] or bi[1] > bj[3] or bj[1] > bi[3]:
                continue
            if _segments_cross(edges[i][0], edges[i][1], edges[j][0], edges[j][1]):
                return True
    return False


def get_ring_problem(ring):
    # type: (list) -> str
    """구역 링 안전장치 — 문제가 있으면 사용자용 한 줄, 없으면 ''. 입력은 get_clean_ring 결과."""
    if len(ring) < 3:
        return "꼭짓점이 3개 이상인 닫힌 도형이어야 합니다"
    if len(ring) > constants.AREA_MAX_VERTICES:
        return "꼭짓점이 너무 많습니다(%d개 > %d). 커브를 단순하게 다시 그리세요" % (len(ring), constants.AREA_MAX_VERTICES)
    min_x, min_y, max_x, max_y = get_bbox(ring)
    if max(max_x - min_x, max_y - min_y) > constants.AREA_MAX_SPAN:
        return "구역이 너무 큽니다(긴 변 %.1f km > %.1f km)" % (max(max_x - min_x, max_y - min_y) / 1000.0, constants.AREA_MAX_SPAN / 1000.0)
    if has_self_intersection(ring):
        return "변끼리 꼬여 있습니다(자기교차). 꼬이지 않은 닫힌 도형으로 그리세요"
    area = get_ring_area(ring)
    if area < constants.AREA_MIN:
        return "구역이 너무 작습니다(%.0f ㎡ < %.0f ㎡). 단위나 축척을 확인하세요" % (area, constants.AREA_MIN)
    return ""


def get_inside_fraction(parts, ring, ring_bbox=None):
    # type: (list, list, tuple) -> float
    """필지(GeoJSON Polygon parts)가 구역 링 안에 든 면적 비율 0~1.

    처리: 필지 bbox가 구역 bbox 밖이면 0. 외곽 정점이 전부 안이고 구역 정점이 필지 bbox 안에 없으면 1, 전부 밖이고 구역 정점도 없으면 0
          (구역 변이 필지를 파고들면 구역 정점이 필지 bbox 안에 있다). 나머지(경계에 걸친 필지)만 AREA_SAMPLE_GRID² 격자 점으로 잰다.
    출력: 비율. ponytail: 격자 근사 — 경계 필지 ±5 %, 정확한 면적 교차가 필요하면 다각형 클리핑으로.
    """
    ring_bbox = ring_bbox or get_bbox(ring)
    points = [p for part in parts if part for p in part[0]]
    if not points:
        return 0.0
    min_x, min_y, max_x, max_y = get_bbox(points)
    if max_x < ring_bbox[0] or min_x > ring_bbox[2] or max_y < ring_bbox[1] or min_y > ring_bbox[3]:
        return 0.0
    inside = [is_point_in_ring(p[0], p[1], ring) for p in points]
    ring_in_box = any(min_x <= p[0] <= max_x and min_y <= p[1] <= max_y for p in ring)
    if not ring_in_box and all(inside):
        return 1.0
    if not ring_in_box and not any(inside):
        return 0.0
    n = constants.AREA_SAMPLE_GRID
    hit = total = 0
    for i in range(n):
        x = min_x + (max_x - min_x) * (i + 0.5) / n
        for j in range(n):
            y = min_y + (max_y - min_y) * (j + 0.5) / n
            if any(is_point_in_polygon(x, y, part) for part in parts if part):
                total += 1
                hit += is_point_in_ring(x, y, ring)
    return hit / float(total) if total else 0.0


def _get_step_band(z, step):
    # type: (float, float) -> tuple
    """표고 z → (z, 단 번호 floor(z / step)). 단 경계 TERRAIN_STEP_SNAP 안이면 z를 경계에 붙이고 경계 위 단으로."""
    k = int(round(z / step))
    if abs(z - k * step) < constants.TERRAIN_STEP_SNAP:
        return k * step, k
    return z, int(math.floor(z / step))


def _get_cross_xy(low, low_z, high, high_z, level):
    # type: (tuple, float, tuple, float, float) -> tuple
    """아래 단 점 low → 위 단 점 high 변이 높이 level을 지나는 (x, y). 위 점이 경계 위면 그 점 그대로.
    늘 아래 → 위 순서로 보간해 이웃 면·대상지 벽이 같은 변에서 같은 값을 얻는다."""
    if high_z == level:
        return high[0], high[1]
    t = (level - low_z) / (high_z - low_z)
    return low[0] + (high[0] - low[0]) * t, low[1] + (high[1] - low[1]) * t


def get_stepped_mesh(verts, faces, step):
    # type: (list, list, float) -> tuple
    """매끈한 지형 메시 → 계단형 지형(등고 모형) 메시.

    입력: verts ``[(x, y, z)]``, faces ``[(a, b, c)]`` 또는 ``(a, b, c, d)`` — 공유 정점 번호. step = 단 간격 m(> 0).
    처리: 정점 단 = floor(z / step). 한 단 안의 면은 그 단 높이로 내린다. 여러 단에 걸친 면은 삼각형으로 나눠
          둘레(원래 정점 + 변 위 단 경계 교차점)를 돌며 단마다 다각형을 뽑고, 단 경계선마다 높이 step 수직 벽(아래 단 쪽을 본다).
          교차점은 정점 번호로 묶어 이웃 면과 공유한다. 벽 정점은 단 면과 따로 둔다(공유하면 모서리 음영이 뭉개진다).
    출력: ``(verts, faces)`` — 면은 3·4각형. 입력은 바꾸지 않는다.
    """
    zs, bands = zip(*[_get_step_band(v[2], step) for v in verts]) if verts else ((), ())
    out_verts, out_faces, index = [], [], {}

    def add(key, x, y, z):
        i = index.get(key)
        if i is None:
            i = index[key] = len(out_verts)
            out_verts.append((x, y, z))
        return i

    def vertex(i):
        return add(i, verts[i][0], verts[i][1], bands[i] * step)

    def cross(a, b, j):
        """변 a-b × 단 경계 j → (묶음 키, x, y). 위 정점이 경계 위면 키 = 그 정점."""
        if bands[a] > bands[b]:
            a, b = b, a
        x, y = _get_cross_xy(verts[a], zs[a], verts[b], zs[b], j * step)
        return (b if zs[b] == j * step else (a, b, j)), x, y

    def add_face(face):
        face = [i for k, i in enumerate(face) if i != face[k - 1]]
        if len(face) <= 4:
            if len(face) >= 3:
                out_faces.append(tuple(face))
            return
        out_faces.extend((face[0], face[k], face[k + 1]) for k in range(1, len(face) - 1))

    for face in faces:
        if min(bands[i] for i in face) == max(bands[i] for i in face):
            out_faces.append(tuple(vertex(i) for i in face))
            continue
        for tri in ([face] if len(face) == 3 else [(face[0], face[1], face[2]), (face[0], face[2], face[3])]):
            lo, hi = min(bands[i] for i in tri), max(bands[i] for i in tri)
            if lo == hi:
                out_faces.append(tuple(vertex(i) for i in tri))
                continue
            ring = []   # 둘레 순서 — 원래 정점 i 또는 교차점 (j, 키, x, y)
            for e in range(3):
                a, b = tri[e], tri[(e + 1) % 3]
                ring.append(a)
                levels = range(bands[a] + 1, bands[b] + 1) if bands[a] < bands[b] else range(bands[a], bands[b], -1)
                ring.extend((j,) + cross(a, b, j) for j in levels)
            for k in range(lo, hi + 1):   # 단 k 다각형 = 단 k 정점 + 경계 k·k+1 교차점, 높이 k × step
                poly = []
                for p in ring:
                    if not isinstance(p, tuple):
                        if bands[p] == k:
                            poly.append(vertex(p))
                    elif p[0] in (k, k + 1):
                        j, key, x, y = p
                        poly.append(vertex(key) if not isinstance(key, tuple) and bands[key] == k else add((key, k), x, y, k * step))
                add_face(poly)
            for j in range(lo + 1, hi + 1):   # 경계 j 벽 — 높이 (j−1)·step → j·step
                (_j, ka, xa, ya), (_j, kb, xb, yb) = [p for p in ring if isinstance(p, tuple) and p[0] == j]
                if (xa, ya) == (xb, yb):
                    continue
                low = next(i for i in tri if bands[i] < j)
                if (yb - ya) * (verts[low][0] - xa) - (xb - xa) * (verts[low][1] - ya) < 0:
                    (ka, xa, ya), (kb, xb, yb) = (kb, xb, yb), (ka, xa, ya)
                z0, z1 = (j - 1) * step, j * step
                out_faces.append((add(("w", ka, z0), xa, ya, z0), add(("w", kb, z0), xb, yb, z0),
                                  add(("w", kb, z1), xb, yb, z1), add(("w", ka, z1), xa, ya, z1)))
    return out_verts, out_faces


def get_stepped_edges(a, b, step):
    # type: (tuple, tuple, float) -> list
    """자연 지반 변 a → b ``(x, y, z)``를 계단 지형 위 토막 ``[(p, q)]``로 — 토막 두 끝 z = 그 토막의 단 높이.
    get_stepped_mesh와 같은 교차점이라 대상지 경계 벽 윗선이 주변 계단 지형과 맞는다. step <= 0이면 ``[(a, b)]`` 그대로."""
    if step <= 0:
        return [(a, b)]
    (za, ka), (zb, kb) = _get_step_band(a[2], step), _get_step_band(b[2], step)
    up = ka < kb
    pts = [(a[0], a[1])]
    for j in (range(ka + 1, kb + 1) if up else range(ka, kb, -1)):
        pts.append(_get_cross_xy(a, za, b, zb, j * step) if up else _get_cross_xy(b, zb, a, za, j * step))
    pts.append((b[0], b[1]))
    out = []
    for k in range(len(pts) - 1):
        z = (ka + (k if up else -k)) * step
        if pts[k] != pts[k + 1]:
            out.append(((pts[k][0], pts[k][1], z), (pts[k + 1][0], pts[k + 1][1], z)))
    return out
