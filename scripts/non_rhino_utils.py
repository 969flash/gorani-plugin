"""Rhino에 의존하지 않는 범용 유틸을 제공한다.

좌표·GeoJSON 연산처럼 Rhino 없이 계산할 수 있는 것을 모은다.
이 모듈은 Python 딕셔너리·목록·숫자만 다루며 Rhino를 import하지 않는다.
Rhino 커브·벡터·Brep을 다루는 연산은 ``utils.py``에 둔다.
좌표 단위를 임의로 변환하지 않으며 프로젝트 내부 좌표는 m로 유지한다.
"""

import bisect
import contextlib
import math
import re
import os

import constants
from i18n import get_texts, tr



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
    """도면 이름 — ko는 SHEET_CATALOG 이름, 다른 언어는 그 이름을 키로 i18n.json에서(없으면 영어). 파일 이름·도면 제목·부제가 같이 쓴다."""
    row = next((r for r in constants.SHEET_CATALOG if r[1] == sheet_key), None)
    if row is None:
        return sheet_key
    if lang == "ko":
        return row[2]
    entry = get_texts().get(row[2]) or {}
    return entry.get(lang) or entry.get("en") or row[2]


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


def get_signed_area(ring):
    # type: (list) -> float
    """링의 부호 있는 면적 — 반시계면 양수, 시계면 음수(get_ring_area의 부호판)."""
    doubled_area = 0.0
    previous = ring[-1] if ring else None
    for point in ring:
        doubled_area += float(previous[0]) * float(point[1]) - float(point[0]) * float(previous[1])
        previous = point
    return doubled_area * 0.5


def get_edge_chains(edges, closed):
    # type: (list, bool) -> list
    """방향 없는 변 [(a, b)] → 이은 정점 번호 줄 목록. closed=True면 고리(첫 점을 되풀이하지 않는다), False면 열린 줄 —
    가지 친 점(이웃이 2개가 아닌 점)에서 끊는다. 남은 고리도 줄로 돌려준다. 입력은 바꾸지 않는다."""
    neighbors = {}
    for a, b in edges:
        neighbors.setdefault(a, []).append(b)
        neighbors.setdefault(b, []).append(a)
    unused = {(min(a, b), max(a, b)) for a, b in edges}

    def walk(start, nxt):
        chain = [start]
        previous, current = start, nxt
        while True:
            unused.discard((min(previous, current), max(previous, current)))
            if current == start:
                return chain
            chain.append(current)
            if not closed and len(neighbors[current]) != 2:
                return chain
            options = [n for n in neighbors[current] if (min(current, n), max(current, n)) in unused]
            if not options:
                return chain
            previous, current = current, options[0]

    chains = []
    starts = [v for v, ns in neighbors.items() if len(ns) != 2] if not closed else []
    for start in starts + list(neighbors):
        for n in list(neighbors[start]):
            if (min(start, n), max(start, n)) in unused:
                chains.append(walk(start, n))
    return [c for c in chains if len(c) >= (3 if closed else 2)]


# ═════════════════════════════════════════════════════════
# EPSG:5186 ↔ WGS84 좌표 변환
# ═════════════════════════════════════════════════════════
# EPSG:5186 (Korea 2000 / Central Belt 2010): GRS80 타원체, 원점 위도 38·경도
# 127, 축척 1. 횡메르카토르 Karney 급수(6차) 구현 — 왕복 오차 1e-14도 수준.
A_GRS80 = 6378137.0  # GRS80 장반경 m
F_GRS80 = 1.0 / 298.257222101  # GRS80 편평률
KOREA_TM = (38.0, 127.0, 200000.0, 600000.0)   # EPSG:5186 원점 위도·경도, 가산치 E·N
KOREA_LNGLAT_BOUNDS = (124.0, 33.0, 132.0, 39.0)  # 한국 판정 경위도 사각형(서·남·동·북) — 제주·울릉 포함, 북한 일부도 들어간다
# 사각형 안의 일본(후쿠오카·기타큐슈·사가·사세보·야마구치·쓰시마 — PLATEAU 도시) = 이 경도 동쪽·위도 남쪽. 그 안에 한국 땅은 없다
# (부산 태종대 북위 35.05°·동경 129.08°, 쓰시마 서해안 동경 129.17°). 2026-10-21 — 후쿠오카를 한국으로 보고 국가 DB로 만들려 했다
KOREA_JAPAN_CORNER = (129.1, 35.0)
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
    """경위도가 한국(국내 DB·EPSG:5186 범위) 안인지. 대략의 경위도 사각형에서 남동쪽 일본 모서리(KOREA_JAPAN_CORNER)를 뺀다."""
    west, south, east, north = KOREA_LNGLAT_BOUNDS
    corner_lng, corner_lat = KOREA_JAPAN_CORNER
    return west <= lng <= east and south <= lat <= north and not (lng > corner_lng and lat < corner_lat)


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


@contextlib.contextmanager
def korea_projection():
    # type: () -> object
    """잠깐 EPSG:5186으로 — 지도 필지·팩 조회가 해외 대상지 원점(프로세스 전역)을 지우지 않게 하고, 끝나면 되돌린다.
    2026-10-23: 도쿄를 한 번 찍으면 서울 지도의 필지(1132 → 0)와 [받기] 칩이 사라졌다."""
    saved = os.environ.get(PROJECTION_ENV)
    set_projection()
    try:
        yield
    finally:
        if saved:
            os.environ[PROJECTION_ENV] = saved
        _apply_projection()


def get_lnglat_in_crs(points, crs):
    # type: (list, str) -> list
    """저장된 결과(context.json crs)의 평면좌표 → 경위도. crs는 'EPSG:5186' 또는 get_crs_label의 지역 횡메르카토르
    (원점이 0.01° 반올림이라 라벨 두 자리가 곧 원점이다 — set_projection). 지금 원점(프로세스 전역)은 끝나면 되돌린다.
    출력: [[lng, lat]] — crs를 못 읽으면 빈 목록."""
    match = re.match(r"^\+proj=tmerc \+lat_0=(-?[\d.]+) \+lon_0=(-?[\d.]+) ", crs or "")
    if crs != "EPSG:5186" and not match:
        return []
    saved = os.environ.get(PROJECTION_ENV)
    if match:
        os.environ[PROJECTION_ENV] = "%s,%s" % (match.group(2), match.group(1))
    else:
        os.environ.pop(PROJECTION_ENV, None)
    _apply_projection()
    try:
        return [list(get_wgs84_from_tm(float(x), float(y))) for x, y in points]
    finally:
        if saved:
            os.environ[PROJECTION_ENV] = saved
        else:
            os.environ.pop(PROJECTION_ENV, None)
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


def get_noded_segments(rings, tol=1e-3, cell=10.0):
    # type: (list, float, float) -> list
    """닫힌 링들 → 교차점·겹친 구간에서 나눈, 서로 겹치지 않는 선분 ``[((x, y), (x, y))]``(좌표는 tol 격자로 맞춤, 중복 없음).
    분류 경계(도로·하천·녹지·대상지)는 같은 선을 겹쳐 지나고 서로 걸친다 — 그대로 Rhino BrepFace.Split·제약 삼각분할에 넣으면 실패한다
    (서울 팩 청계천·창릉천 R=500, 2026-11-07). 이렇게 노딩한 선분은 Mesh.CreateFromTessellation 제약선으로 그대로 쓴다."""
    def snap(v):
        return round(v / tol) * tol

    segs = []
    for ring in rings:
        n = len(ring)
        for k in range(n):
            a = (snap(ring[k][0]), snap(ring[k][1]))
            b = (snap(ring[(k + 1) % n][0]), snap(ring[(k + 1) % n][1]))
            if a != b:
                segs.append((a, b))
    grid = {}
    for i, (a, b) in enumerate(segs):
        for gx in range(int(math.floor(min(a[0], b[0]) / cell)), int(math.floor(max(a[0], b[0]) / cell)) + 1):
            for gy in range(int(math.floor(min(a[1], b[1]) / cell)), int(math.floor(max(a[1], b[1]) / cell)) + 1):
                grid.setdefault((gx, gy), []).append(i)
    cuts = [set() for _ in segs]

    def param_on(p, a, b):
        """p가 선분 a-b 안쪽(끝 제외) tol 안이면 매개변수 t, 아니면 None."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        t = ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)
        if 0.0 < t < 1.0 and math.hypot(a[0] + dx * t - p[0], a[1] + dy * t - p[1]) <= tol:
            return t
        return None

    done = set()
    for ids in grid.values():
        for x in range(len(ids)):
            for y in range(x + 1, len(ids)):
                i, j = ids[x], ids[y]
                if (i, j) in done:
                    continue
                done.add((i, j))
                (a, b), (c, d) = segs[i], segs[j]
                for p, (s0, s1), k in ((c, segs[i], i), (d, segs[i], i), (a, segs[j], j), (b, segs[j], j)):   # 끝점이 다른 선분 위(T자·겹침)
                    t = param_on(p, s0, s1)
                    if t is not None:
                        cuts[k].add(t)
                r, q = (b[0] - a[0], b[1] - a[1]), (d[0] - c[0], d[1] - c[1])
                den = r[0] * q[1] - r[1] * q[0]
                if abs(den) < 1e-12:
                    continue
                t = ((c[0] - a[0]) * q[1] - (c[1] - a[1]) * q[0]) / den
                u = ((c[0] - a[0]) * r[1] - (c[1] - a[1]) * r[0]) / den
                if 0.0 < t < 1.0 and 0.0 < u < 1.0:   # 십자 교차
                    cuts[i].add(t)
                    cuts[j].add(u)
    out = set()
    for (a, b), ts in zip(segs, cuts):
        pts = [a] + [(snap(a[0] + (b[0] - a[0]) * t), snap(a[1] + (b[1] - a[1]) * t)) for t in sorted(ts)] + [b]
        for p1, p2 in zip(pts, pts[1:]):
            if p1 != p2:
                out.add((p1, p2) if p1 < p2 else (p2, p1))
    return sorted(out)


def get_split_triangles(verts, faces, segments, tol=1e-3):
    # type: (list, list, list, float) -> list
    """삼각형 메시를 제약 선분으로 나뉜 영역마다 묶는다 — 선분을 건너지 않고 이웃한 삼각형끼리(BrepFace.Split의 면에 해당).
    입력: verts ``[(x, y, …)]``, faces ``[(a, b, c)]``, segments = get_noded_segments 결과. 출력: 영역마다 면 번호 목록."""
    def key(v):
        return (round(v[0] / tol), round(v[1] / tol))

    barrier = {frozenset((key(a), key(b))) for a, b in segments}
    by_edge = {}
    for f, face in enumerate(faces):
        for k in range(len(face)):
            e = frozenset((key(verts[face[k]]), key(verts[face[(k + 1) % len(face)]])))
            by_edge.setdefault(e, []).append(f)
    region = [-1] * len(faces)
    groups = []
    for start in range(len(faces)):
        if region[start] >= 0:
            continue
        region[start] = len(groups)
        stack, members = [start], []
        while stack:
            f = stack.pop()
            members.append(f)
            face = faces[f]
            for k in range(len(face)):
                e = frozenset((key(verts[face[k]]), key(verts[face[(k + 1) % len(face)]])))
                if e in barrier:
                    continue
                for g in by_edge.get(e, ()):
                    if region[g] < 0:
                        region[g] = len(groups)
                        stack.append(g)
        groups.append(members)
    return groups


class PolygonIndex(object):
    """폴리곤 여럿(각각 [외곽, 구멍…])의 점 포함 판정 — y 띠마다 걸친 변만 보는 홀짝 반직선. 점 수만 개 × 정점 수천 개(OSM 호수)에서도 빠르다."""

    def __init__(self, polygons, band=5.0):
        # type: (list, float) -> None
        self.band, self.bands, self.edges, self._near = float(band), {}, [], None
        for pid, rings in enumerate(polygons):
            for ring in rings:
                for k in range(len(ring)):
                    (x1, y1), (x2, y2) = ring[k][:2], ring[(k + 1) % len(ring)][:2]
                    self.edges.append((x1, y1, x2, y2))
                    if y1 == y2:
                        continue
                    for b in range(int(math.floor(min(y1, y2) / self.band)), int(math.floor(max(y1, y2) / self.band)) + 1):
                        self.bands.setdefault(b, []).append((x1, y1, x2, y2, pid))

    def is_near(self, x, y, dist):
        # type: (float, float, float) -> bool
        """(x, y)에서 dist 안에 폴리곤 변이 있는지(안팎 무관)."""
        if self._near is None or self._near[0] != dist:
            grid = {}
            for x1, y1, x2, y2 in self.edges:
                for i in range(int(math.floor((min(x1, x2) - dist) / dist)), int(math.floor((max(x1, x2) + dist) / dist)) + 1):
                    for j in range(int(math.floor((min(y1, y2) - dist) / dist)), int(math.floor((max(y1, y2) + dist) / dist)) + 1):
                        grid.setdefault((i, j), []).append((x1, y1, x2 - x1, y2 - y1))
            self._near = (dist, grid)
        for ax, ay, dx, dy in self._near[1].get((int(math.floor(x / dist)), int(math.floor(y / dist))), ()):
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
            if math.hypot(x - ax - dx * t, y - ay - dy * t) <= dist:
                return True
        return False

    def contains(self, x, y):
        # type: (float, float) -> bool
        odd = set()
        for x1, y1, x2, y2, pid in self.bands.get(int(math.floor(y / self.band)), ()):
            if (y1 > y) != (y2 > y) and x1 + (y - y1) * (x2 - x1) / (y2 - y1) > x:
                odd ^= {pid}
        return bool(odd)


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


def get_buffered_line_ring(line, width, arc_segments=3):
    # type: (list, float, int) -> list
    """선 ``[(x, y)]``를 폭 width(m)로 두껍게 한 닫힌 링 — OSM 도로 중심선 → 도로면.

    입력:
        line: 2점 이상(연속 중복점은 뺀다). width: 전체 폭 m. arc_segments: 호 90°당 분할 수.
    처리:
        왼쪽 오프셋을 앞으로, 끝 반원, 오른쪽 오프셋(뒤집은 선의 왼쪽)을 뒤로, 시작 반원. 바깥 꺾임은 호, 안쪽 꺾임은 두 오프셋 선의 교점
        (교점이 폭의 OSM_ROAD_MITER_LIMIT배보다 멀면 두 점 그대로). 짧은 변에서 안쪽 오프셋이 서로 넘어가 작은 고리가 생길 수 있다 —
        면 분류(점 포함 판정)·채우기에는 무시할 수준(ponytail: 정밀 합집합이 필요하면 호스트 Boolean으로).
    출력:
        ``[(x, y)]`` 첫 점 = 끝 점(GeoJSON 링). 점이 1개 이하이거나 width ≤ 0이면 None.
    """
    pts = []
    for p in line:
        q = (float(p[0]), float(p[1]))
        if not pts or abs(q[0] - pts[-1][0]) > 1e-6 or abs(q[1] - pts[-1][1]) > 1e-6:
            pts.append(q)
    if len(pts) < 2 or width <= 0:
        return None
    h = width / 2.0

    def arc(center, a0, a1):   # 시계 방향 a0 → a1 중간점(끝점 제외)
        sweep = a0 - a1
        while sweep <= 1e-9:
            sweep += 2 * math.pi
        steps = max(1, int(math.ceil(sweep / (math.pi / 2) * arc_segments)))
        return [(center[0] + h * math.cos(a0 - sweep * k / steps), center[1] + h * math.sin(a0 - sweep * k / steps)) for k in range(1, steps)]

    def left_chain(points):
        dirs = []
        for a, b in zip(points, points[1:]):
            length = math.hypot(b[0] - a[0], b[1] - a[1])
            dirs.append(((b[0] - a[0]) / length, (b[1] - a[1]) / length))
        normals = [(-d[1], d[0]) for d in dirs]
        chain = [(points[0][0] + h * normals[0][0], points[0][1] + h * normals[0][1])]
        for k in range(1, len(points) - 1):
            c, d0, d1, n0, n1 = points[k], dirs[k - 1], dirs[k], normals[k - 1], normals[k]
            cross = d0[0] * d1[1] - d0[1] * d1[0]
            p0 = (c[0] + h * n0[0], c[1] + h * n0[1])
            p1 = (c[0] + h * n1[0], c[1] + h * n1[1])
            if cross < -1e-9:        # 오른쪽 꺾임 — 왼쪽이 바깥: 호
                chain += [p0] + arc(c, math.atan2(n0[1], n0[0]), math.atan2(n1[1], n1[0])) + [p1]
            elif cross > 1e-9:       # 왼쪽 꺾임 — 왼쪽이 안쪽: 두 오프셋 선의 교점
                t = ((p1[0] - p0[0]) * d1[1] - (p1[1] - p0[1]) * d1[0]) / cross
                x = (p0[0] + t * d0[0], p0[1] + t * d0[1])
                chain += [x] if math.hypot(x[0] - c[0], x[1] - c[1]) <= constants.OSM_ROAD_MITER_LIMIT * h else [p0, p1]
            else:
                chain.append(p1)
        chain.append((points[-1][0] + h * normals[-1][0], points[-1][1] + h * normals[-1][1]))
        return chain, normals[0], normals[-1]

    forward, n_start, n_end = left_chain(pts)
    backward, _n0, _n1 = left_chain(pts[::-1])
    a_end = math.atan2(n_end[1], n_end[0])
    a_start = math.atan2(-n_start[1], -n_start[0])
    ring = forward + arc(pts[-1], a_end, a_end - math.pi) + backward + arc(pts[0], a_start, a_start - math.pi)
    if is_ring_self_intersecting(ring):   # 급한 꺾임·짧은 변 — 변마다 캡슐을 만들어 합친다(느리지만 자기교차 없음)
        capsules = [[get_buffered_line_ring([a, b], width, arc_segments)[:-1]] for a, b in zip(pts, pts[1:])]
        outers, _holes = get_merged_rings(capsules, min(width, 1.0) * 0.01)
        if outers:
            ring = max(outers, key=lambda r: abs(get_ring_area(r)))
    return ring + [ring[0]]


def is_ring_self_intersecting(ring):
    # type: (list) -> bool
    """링의 변끼리(이웃 변 제외) 교차하면 True. O(n²) — 도로면 버퍼(수십 점) 검사용."""
    pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
    n = len(pts)

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    for i in range(n):
        p, q = pts[i], pts[(i + 1) % n]
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            a, b = pts[j], pts[(j + 1) % n]
            if cross(p, q, a) * cross(p, q, b) < 0 and cross(a, b, p) * cross(a, b, q) < 0:
                return True
    return False


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
        return tr("꼭짓점이 3개 이상인 닫힌 도형이어야 합니다")
    if len(ring) > constants.AREA_MAX_VERTICES:
        return tr("꼭짓점이 너무 많습니다({0}개 > {1}). 커브를 단순하게 다시 그리세요", len(ring), constants.AREA_MAX_VERTICES)
    min_x, min_y, max_x, max_y = get_bbox(ring)
    if max(max_x - min_x, max_y - min_y) > constants.AREA_MAX_SPAN:
        return tr("구역이 너무 큽니다(긴 변 {0:.1f} km > {1:.1f} km)", max(max_x - min_x, max_y - min_y) / 1000.0, constants.AREA_MAX_SPAN / 1000.0)
    if has_self_intersection(ring):
        return tr("변끼리 꼬여 있습니다(자기교차). 꼬이지 않은 닫힌 도형으로 그리세요")
    area = get_ring_area(ring)
    if area < constants.AREA_MIN:
        return tr("구역이 너무 작습니다({0:.0f} ㎡ < {1:.0f} ㎡). 단위나 축척을 확인하세요", area, constants.AREA_MIN)
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


class TinProfile(object):
    """TIN 위 평면 선분의 높이 단면 — 계단 지형 단 경계 교차점을 메시 변 선형 보간 대신 TIN에서 찾는다(get_stepped_mesh·get_stepped_edges tin=).

    등고선 TIN은 같은 등고선 점끼리 이은 평평한 삼각형이 많다(서대문 안산 R=250: TIN 21,267면 중 14,022면). 그 위 3 m 격자 정점은
    단 높이에 정확히 놓여(정점 37 %), 선형 보간하면 교차점이 격자 정점에 붙어 단 테두리가 격자를 따라 톱니가 됐다(죽림리 301-3 구역, 2026-11-08).
    TIN 단면은 평평한 삼각형이 끝나는 자리(= 실제 등고선)를 준다. 입력은 verts ``[(x, y, z)]``, faces 3·4각형, 색인 칸 cell(m).
    """

    def __init__(self, verts, faces, cell):
        # type: (list, list, float) -> None
        self.cell = float(cell)
        self._cells = {}
        self._tris = []
        for face in faces:
            for a, b, c in ((face[0], face[k], face[k + 1]) for k in range(1, len(face) - 1)):
                p, q, r = verts[a], verts[b], verts[c]
                det = (q[0] - p[0]) * (r[1] - p[1]) - (r[0] - p[0]) * (q[1] - p[1])
                if abs(det) < 1e-9:   # 평면에서 넓이 0
                    continue
                if det < 0:
                    q, r, det = r, q, -det
                # z = z0 + gx·(x − x0) + gy·(y − y0)
                gx = ((q[2] - p[2]) * (r[1] - p[1]) - (r[2] - p[2]) * (q[1] - p[1])) / det
                gy = ((r[2] - p[2]) * (q[0] - p[0]) - (q[2] - p[2]) * (r[0] - p[0])) / det
                index = len(self._tris)
                sides = tuple((u[0], u[1], v[0] - u[0], v[1] - u[1], 1e-9 * math.hypot(v[0] - u[0], v[1] - u[1])) for u, v in ((p, q), (q, r), (r, p)))
                self._tris.append((p, gx, gy, min(p[0], q[0], r[0]), min(p[1], q[1], r[1]), max(p[0], q[0], r[0]), max(p[1], q[1], r[1]), sides))
                for i in range(int(math.floor(min(p[0], q[0], r[0]) / self.cell)), int(math.floor(max(p[0], q[0], r[0]) / self.cell)) + 1):
                    for j in range(int(math.floor(min(p[1], q[1], r[1]) / self.cell)), int(math.floor(max(p[1], q[1], r[1]) / self.cell)) + 1):
                        self._cells.setdefault((i, j), []).append(index)

    def get_pieces(self, a, b):
        # type: (tuple, tuple) -> list
        """선분 a → b ``(x, y)``의 단면 ``[(t0, t1, z0, z1)]``(t 오름차순, 삼각형 하나 안에서는 z가 t에 선형). [0, 1]을 다 덮지 못하면 None."""
        dx, dy = b[0] - a[0], b[1] - a[1]
        bx0, by0, bx1, by1 = min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1])
        seen, pieces = set(), []
        for i in range(int(math.floor(min(a[0], b[0]) / self.cell)), int(math.floor(max(a[0], b[0]) / self.cell)) + 1):
            for j in range(int(math.floor(min(a[1], b[1]) / self.cell)), int(math.floor(max(a[1], b[1]) / self.cell)) + 1):
                for index in self._cells.get((i, j), ()):
                    if index in seen:
                        continue
                    seen.add(index)
                    p, gx, gy, x0, y0, x1, y1, sides = self._tris[index]
                    if x0 > bx1 or x1 < bx0 or y0 > by1 or y1 < by0:
                        continue
                    t0, t1 = 0.0, 1.0
                    for ux, uy, ex, ey, eps in sides:   # 반시계 삼각형 — 변 왼쪽(cross ≥ 0)이 안
                        c0 = ex * (a[1] - uy) - ey * (a[0] - ux)
                        dc = ex * dy - ey * dx
                        if abs(dc) < 1e-15:
                            if c0 < -eps:
                                t0 = 2.0
                            continue
                        t = (-eps - c0) / dc
                        if dc > 0:
                            t0 = max(t0, t)
                        else:
                            t1 = min(t1, t)
                    if t1 - t0 > 1e-9:
                        z0 = p[2] + gx * (a[0] + dx * t0 - p[0]) + gy * (a[1] + dy * t0 - p[1])
                        z1 = p[2] + gx * (a[0] + dx * t1 - p[0]) + gy * (a[1] + dy * t1 - p[1])
                        pieces.append((t0, t1, z0, z1))
        pieces.sort()
        reach = 0.0
        for t0, t1, _z0, _z1 in pieces:
            if t0 > reach + 1e-6:
                return None
            reach = max(reach, t1)
        return pieces if reach >= 1.0 - 1e-6 else None

    def get_cross_ts(self, low, high, levels):
        # type: (tuple, tuple, list) -> list
        """아래 단 점 low → 위 단 점 high ``(x, y, z)``가 높이 levels(오름차순)를 마지막으로 넘는 자리 t 목록(= 단면이 그 높이 아래인 마지막 자리).
        단면 = TIN 높이 + 양 끝 정점과의 차를 t로 선형 보간한 값(물가 비탈처럼 TIN 뒤에 바뀐 정점도 끝이 맞는다).
        levels가 오르면 t도 오른다(단 다각형이 꼬이지 않는다). 단면이 TIN 밖으로 끊기면 None."""
        pieces = self.get_pieces(low, high)
        if not pieces:
            return None
        ca, cb = low[2] - pieces[0][2], high[2] - pieces[-1][3]
        pieces = [(t0, t1, z0 + ca + (cb - ca) * t0, z1 + ca + (cb - ca) * t1) for t0, t1, z0, z1 in pieces]
        out = []
        for level in levels:
            t = None
            for t0, t1, z0, z1 in reversed(pieces):
                if z1 < level:
                    t = t1
                    break
                if z0 < level:
                    t = t0 + (level - z0) / (z1 - z0) * (t1 - t0)
                    break
            if t is None:
                return None
            out.append(t)
        return out


def _get_edge_crosses(low, low_z, high, high_z, j0, j1, step, tin):
    # type: (tuple, float, tuple, float, int, int, float, object) -> list
    """아래 단 점 low → 위 단 점 high 변이 단 경계 j0..j1을 지나는 자리 ``[(x, y, 위 점인가)]``. 늘 아래 → 위 순서로 구해
    이웃 면·대상지 벽이 같은 변에서 같은 값을 얻는다. tin(TinProfile)이 있으면 TIN 단면, 없거나 못 구하면 정점 높이 선형 보간(위 점이 경계 위면 그 점)."""
    levels = [j * step for j in range(j0, j1 + 1)]
    ts = tin.get_cross_ts((low[0], low[1], low_z), (high[0], high[1], high_z), [level - constants.TERRAIN_STEP_SNAP for level in levels]) if tin is not None else None
    out = []
    for k, level in enumerate(levels):
        if ts is None:
            t = 1.0 if high_z == level else (level - low_z) / (high_z - low_z)
        else:
            t = ts[k]
        if t >= 1.0 - 1e-6 and high_z == level:
            out.append((high[0], high[1], True))
        else:
            out.append((low[0] + (high[0] - low[0]) * t, low[1] + (high[1] - low[1]) * t, False))
    return out


def get_stepped_mesh(verts, faces, step, tin=None):
    # type: (list, list, float, object) -> tuple
    """매끈한 지형 메시 → 계단형 지형(등고 모형) 메시.

    입력: verts ``[(x, y, z)]``, faces ``[(a, b, c)]`` 또는 ``(a, b, c, d)`` — 공유 정점 번호. step = 단 간격 m(> 0).
          tin = TinProfile(메시를 TIN에 입힌 경우 — Rhino 3 m 격자). 없으면 정점 높이 선형 보간(메시 정점이 곧 TIN 점인 mesh_geometry).
    처리: 정점 단 = floor(z / step). 한 단 안의 면은 그 단 높이로 내린다. 여러 단에 걸친 면은 삼각형으로 나눠
          둘레(원래 정점 + 변 위 단 경계 교차점)를 돌며 단마다 다각형을 뽑고, 단 경계선마다 높이 step 수직 벽(아래 단 쪽을 본다).
          교차점(_get_edge_crosses)은 변마다 한 번 구해 이웃 면과 공유한다. 벽 정점은 단 면과 따로 둔다(공유하면 모서리 음영이 뭉개진다).
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

    crosses = {}

    def cross(a, b, j):
        """변 a-b × 단 경계 j → (묶음 키, x, y). 교차점이 위 정점이면 키 = 그 정점."""
        if bands[a] > bands[b]:
            a, b = b, a
        if (a, b) not in crosses:
            crosses[(a, b)] = _get_edge_crosses(verts[a], zs[a], verts[b], zs[b], bands[a] + 1, bands[b], step, tin)
        x, y, at_high = crosses[(a, b)][j - bands[a] - 1]
        return (b if at_high else (a, b, j)), x, y

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


def get_stepped_edges(a, b, step, tin=None):
    # type: (tuple, tuple, float, object) -> list
    """자연 지반 변 a → b ``(x, y, z)``를 계단 지형 위 토막 ``[(p, q)]``로 — 토막 두 끝 z = 그 토막의 단 높이.
    get_stepped_mesh와 같은 교차점(같은 tin)이라 대상지 경계 벽 윗선이 주변 계단 지형과 맞는다. step <= 0이면 ``[(a, b)]`` 그대로."""
    if step <= 0:
        return [(a, b)]
    (za, ka), (zb, kb) = _get_step_band(a[2], step), _get_step_band(b[2], step)
    up = ka < kb
    if up:
        crosses = _get_edge_crosses(a, za, b, zb, ka + 1, kb, step, tin)
    else:
        crosses = _get_edge_crosses(b, zb, a, za, kb + 1, ka, step, tin)[::-1]
    pts = [(a[0], a[1])] + [(x, y) for x, y, _at_high in crosses] + [(b[0], b[1])]
    out = []
    for k in range(len(pts) - 1):
        z = (ka + (k if up else -k)) * step
        if pts[k] != pts[k + 1]:
            out.append(((pts[k][0], pts[k][1], z), (pts[k + 1][0], pts[k + 1][1], z)))
    return out


def _get_segment_distances(points, segments, cell):
    # type: (list, list, float) -> list
    """점마다 선분 묶음까지 최단 거리. 칸 색인 + 고리 넓히기(고리 r까지 본 최단이 r × cell 이하면 확정)."""
    grid = {}
    for k, ((ax, ay), (bx, by)) in enumerate(segments):
        for i in range(int(math.floor(min(ax, bx) / cell)), int(math.floor(max(ax, bx) / cell)) + 1):
            for j in range(int(math.floor(min(ay, by) / cell)), int(math.floor(max(ay, by) / cell)) + 1):
                grid.setdefault((i, j), []).append(k)
    out = []
    for x, y in points:
        ci, cj = int(math.floor(x / cell)), int(math.floor(y / cell))
        best, r, seen = None, 0, set()
        while r < 1000:
            for i in range(ci - r, ci + r + 1):
                for j in ((cj - r, cj + r) if abs(i - ci) != r else range(cj - r, cj + r + 1)):
                    for k in grid.get((i, j), ()):
                        if k in seen:
                            continue
                        seen.add(k)
                        (ax, ay), (bx, by) = segments[k]
                        dx, dy = bx - ax, by - ay
                        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
                        d = math.hypot(x - ax - dx * t, y - ay - dy * t)
                        if best is None or d < best:
                            best = d
            if best is not None and best <= r * cell:
                break
            r += 1
        out.append(best or 0.0)
    return out


def get_flat_fill_points(verts, faces, levels):
    # type: (list, list, list) -> list
    """등고선 TIN의 평평한 삼각형 자리(같은 높이 등고선끼리 이어 메워진 골짜기 바닥·꼭대기)에 넣을 점 ``[(x, y, z)]``.

    입력: TIN verts ``[(x, y, z)]``, faces ``[(a, b, c)]``, levels = 원본 등고선 높이들(이 높이의 덩어리만 — 격자 지형·표고점의 진짜 평지는 그대로. 없으면 [] 반환).
    처리: 세 정점 높이가 같은 삼각형을 변으로 이어 덩어리(높이 L)로 묶는다. 덩어리 테두리 너머 이웃 삼각형의 남은 정점이 변 길이로
          TERRAIN_FLAT_SIDE_SHARE 이상 높으면 골짜기(안쪽을 낮춘다), 1 − 그 비율 이하면 꼭대기(올린다), 그 사이는 그대로 둔다(등고선이 꺾인 자리의 조각).
          깊이 = min(이웃 높이 차 중앙값 × TERRAIN_FLAT_DEPTH_RATIO, 이웃 경사 중앙값 × 덩어리 안 테두리까지 최대 거리).
          덩어리의 삼각형마다 무게중심 하나, 높이 = L ∓ 깊이 × (테두리까지 거리 / 최대 거리) — 테두리(원본 등고선)는 L 그대로, 가운데가 가장 깊다.
          덩어리 안 표고점은 이미 TIN 정점이라 그 둘레 삼각형은 평평하지 않다(덩어리에 들지 않는다).
    출력: 더할 점 목록. 이 점을 넣고 TIN을 다시 만든다.
    """
    edges = {}
    for f, face in enumerate(faces):
        for k in range(3):
            a, b = face[k], face[(k + 1) % 3]
            edges.setdefault((a, b) if a < b else (b, a), []).append(f)
    flat = [abs(verts[a][2] - verts[b][2]) < 1e-6 and abs(verts[b][2] - verts[c][2]) < 1e-6 for a, b, c in faces]
    parent = list(range(len(faces)))

    def find(f):
        while parent[f] != f:
            parent[f] = parent[parent[f]]
            f = parent[f]
        return f

    for owners in edges.values():
        if len(owners) == 2 and flat[owners[0]] and flat[owners[1]]:
            parent[find(owners[0])] = find(owners[1])
    groups = {}
    for f in range(len(faces)):
        if flat[f]:
            groups.setdefault(find(f), []).append(f)
    out = []
    levels = set(levels)
    for group in groups.values():
        level = verts[faces[group[0]][0]][2]
        if level not in levels:
            continue
        members = set(group)
        up = down = 0.0
        diffs, slopes, boundary = [], [], []
        for f in group:
            face = faces[f]
            for k in range(3):
                a, b = face[k], face[(k + 1) % 3]
                owners = edges[(a, b) if a < b else (b, a)]
                other = [g for g in owners if g not in members]
                if len(owners) == 2 and not other:
                    continue   # 덩어리 안쪽 변
                pa, pb = verts[a], verts[b]
                boundary.append(((pa[0], pa[1]), (pb[0], pb[1])))
                if not other:
                    continue   # TIN 가장자리
                v = next(i for i in faces[other[0]] if i != a and i != b)
                dz = verts[v][2] - level
                length = math.hypot(pb[0] - pa[0], pb[1] - pa[1])
                if abs(dz) < 1e-6 or length < 1e-9:
                    continue
                dist = abs((pb[0] - pa[0]) * (verts[v][1] - pa[1]) - (pb[1] - pa[1]) * (verts[v][0] - pa[0])) / length
                if dz > 0:
                    up += length
                else:
                    down += length
                diffs.append(abs(dz))
                slopes.append(abs(dz) / dist if dist > 1e-9 else 0.0)
        total = up + down
        if not total or not boundary:
            continue
        if up >= constants.TERRAIN_FLAT_SIDE_SHARE * total:
            sign = -1.0
        elif up <= (1.0 - constants.TERRAIN_FLAT_SIDE_SHARE) * total:
            sign = 1.0
        else:
            continue
        centers = []
        for f in group:
            a, b, c = (verts[i] for i in faces[f])
            centers.append(((a[0] + b[0] + c[0]) / 3.0, (a[1] + b[1] + c[1]) / 3.0))
        dists = _get_segment_distances(centers, boundary, 10.0)
        far = max(dists)
        if far < 1e-6:
            continue
        diffs.sort()
        slopes.sort()
        depth = min(diffs[len(diffs) // 2] * constants.TERRAIN_FLAT_DEPTH_RATIO, slopes[len(slopes) // 2] * far)
        out.extend((x, y, level + sign * depth * d / far) for (x, y), d in zip(centers, dists))
    return out


def get_smoothed_z(zs, neighbors, fixed, levels, iterations):
    # type: (list, list, list, list, int) -> list
    """격자 정점 높이 다듬기(등고선 고정) — TIN 삼각형 면의 꺾임을 편다.

    입력: zs 정점 높이, neighbors 정점마다 이웃 정점 번호 목록, fixed 정점마다 고정 여부, levels 원본 등고선 높이(오름차순), 반복 횟수.
    처리: 고정이 아닌 정점을 이웃 평균으로 iterations번 바꾼다(제자리 — 가우스-자이델). 높이는 처음 높이를 품은 등고선 두 높이 사이로 가둔다 —
          등고선 높이를 넘나들지 않으니 그 높이의 단 테두리가 원본 등고선에서 움직이지 않는다. 처음부터 등고선 높이에 정확히 있는 정점은 그대로.
    출력: 새 높이 목록. 입력은 바꾸지 않는다.
    """
    out = list(zs)
    bands = []
    for z in zs:
        k = bisect.bisect_right(levels, z)
        lo = levels[k - 1] if k else -1e18
        hi = levels[k] if k < len(levels) else 1e18
        bands.append((z, z) if lo == z else (lo, hi))
    free = [i for i in range(len(zs)) if not fixed[i] and neighbors[i] and bands[i][0] != bands[i][1]]
    for _ in range(iterations):
        for i in free:
            nb = neighbors[i]
            v = sum(out[j] for j in nb) / len(nb)
            lo, hi = bands[i]
            out[i] = lo if v < lo else hi if v > hi else v
    return out


# ═════════════════════════════════════════════════════════
# 범위 링으로 자르기(늘)·지형 덩어리(옆면·바닥, options.terrain_block·style.axo_ground). 3D(Rhino·Blender·SketchUp)와 입체 매스도가 같이 쓴다
# ═════════════════════════════════════════════════════════

def get_convex_ring(ring):
    # type: (list) -> list
    """범위 링 → 볼록이면 반시계·닫힘 점 없는 (x, y) 링, 오목하면 None. 패널 범위(원·사각형)는 늘 볼록이다."""
    pts = [(float(p[0]), float(p[1])) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    if len(pts) < 3:
        return None
    if get_ring_orientation(pts) < 0:
        pts.reverse()
    n = len(pts)
    for i in range(n):
        (ax, ay), (bx, by), (cx, cy) = pts[i - 1], pts[i], pts[(i + 1) % n]
        if (bx - ax) * (cy - by) - (by - ay) * (cx - bx) < -1e-6:
            return None
    return pts


def get_convex_clipped_ring(ring, clip):
    # type: (list, list) -> list
    """링을 볼록 링 clip(반시계, 닫힘 점 없음)으로 자른다 — Sutherland–Hodgman. 출력: 새 링(비면 []).
    ponytail: 분석 범위가 원·사각형(볼록)이라는 가정. 필지 버퍼처럼 오목한 범위는 오목한 쪽이 조금 덜 잘린다 — 문제가 되면 다각형 불리언으로."""
    output = [tuple(p[:2]) for p in ring]
    for (ax, ay), (bx, by) in zip(clip, clip[1:] + clip[:1]):
        if not output:
            break
        inputs, output = output, []
        side = lambda p: (bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax)   # ≥ 0 = 변의 왼쪽(안쪽)
        prev = inputs[-1]
        prev_side = side(prev)
        for cur in inputs:
            cur_side = side(cur)
            if (cur_side >= 0) != (prev_side >= 0):
                t = prev_side / (prev_side - cur_side)
                output.append((prev[0] + (cur[0] - prev[0]) * t, prev[1] + (cur[1] - prev[1]) * t))
            if cur_side >= 0:
                output.append(cur)
            prev, prev_side = cur, cur_side
    return output


def get_clipped_lines(line, clip):
    # type: (list, list) -> list
    """열린 폴리라인 ``[(x, y)]``을 볼록 링 clip(반시계)으로 자른다 — 변마다 Cyrus–Beck.
    출력: 안쪽 토막 폴리라인 목록(이어지는 변은 한 토막). 다 밖이면 []."""
    edges = list(zip(clip, clip[1:] + clip[:1]))
    pieces, current = [], []
    for a, b in zip(line, line[1:]):
        dx, dy = b[0] - a[0], b[1] - a[1]
        t0, t1 = 0.0, 1.0
        for (ax, ay), (bx, by) in edges:
            ex, ey = bx - ax, by - ay
            side = ex * (a[1] - ay) - ey * (a[0] - ax)   # t = 0에서 ≥ 0 = 안쪽
            rate = ex * dy - ey * dx
            if rate == 0:
                if side < 0:
                    t0, t1 = 1.0, 0.0
                    break
                continue
            if rate > 0:
                t0 = max(t0, -side / rate)
            else:
                t1 = min(t1, -side / rate)
            if t0 > t1:
                break
        if t0 > t1:
            if current:
                pieces.append(current)
            current = []
            continue
        p, q = (a[0] + dx * t0, a[1] + dy * t0), (a[0] + dx * t1, a[1] + dy * t1)
        if not (current and t0 == 0.0):
            if current:
                pieces.append(current)
            current = [p]
        current.append(q)
        if t1 < 1.0:
            pieces.append(current)
            current = []
    if current:
        pieces.append(current)
    return [piece for piece in pieces if len(piece) >= 2]


def get_clipped_parts(parts, clip):
    # type: (list, list) -> list
    """건물 파트 ``[[외곽, 구멍…]]``을 볼록 링 clip으로 자른다. 다 안이면 그대로, 걸치면 외곽만 잘라 안에 다 든 구멍만 남긴다, 다 밖이면 뺀다.
    ponytail: 잘린 외곽에 걸친 구멍(중정)은 버린다 — 범위 경계의 중정 건물은 드물다."""
    def inside(ring):
        return all(is_point_in_ring(p[0], p[1], clip) for p in ring)

    out = []
    for part in parts:
        if not part:
            continue
        if inside(part[0]):
            out.append(part)
            continue
        outer = get_convex_clipped_ring(part[0], clip)
        if len(outer) >= 3 and get_ring_area(outer) > 0.01:
            out.append([outer] + [hole for hole in part[1:] if inside(hole)])
    return out


def get_block_base(min_z, ring):
    # type: (float, list) -> float
    """지형 덩어리 바닥 높이 = 범위 안 최저 지반 − 두께, BLOCK_BASE_SNAP m 단위로 내림.
    두께 = max(BLOCK_MIN_DEPTH, 범위 짧은 변 × BLOCK_DEPTH_RATIO) — 모형 받침처럼 범위 크기에 비례(500 m 사각형 15 m).
    해발 0 m를 바닥으로 하면 두께가 대상지 표고에 끌려간다(서울 평지 20 m, 산지 수백 m, 네덜란드 간척지는 음수)."""
    min_x, min_y, max_x, max_y = get_bbox(ring)
    depth = max(constants.BLOCK_MIN_DEPTH, min(max_x - min_x, max_y - min_y) * constants.BLOCK_DEPTH_RATIO)
    snap = constants.BLOCK_BASE_SNAP
    return math.floor((min_z - depth) / snap) * snap


def get_block_skirt(meshes, ring, base_z, tol=1e-3):
    # type: (list, list, float, float) -> tuple
    """지형 윗면 메시들의 범위 경계 → 옆면(바닥까지 수직 벽) + 바닥면. 지형이 모형처럼 닫힌 덩어리가 된다.

    입력: meshes ``[(verts, faces)]`` — 범위 링으로 잘린 지형 윗면(분류별, 로컬 m). ring = 같은 좌표의 볼록 링(반시계). base_z = 바닥 높이.
    처리: 메시마다 한 면에만 속한 변 중 두 끝·가운데가 범위 링 위(tol 안)이고 다른 메시와 겹치지 않는 변 → 그 변에서 base_z까지 4각형(바깥을 본다).
          윗선 = 윗면 경계 정점 그대로라 틈이 없다. 계단 지형의 수직 변(평면 길이 0)은 건너뛴다.
          바닥 = 벽 아랫점을 링 중심 둘레 각도순으로 늘어놓은 부채꼴(아래를 본다) — 벽 아랫선과 정점이 같다.
    출력: ``(verts, faces)`` — 면은 3·4각형. 경계 변이 없으면 ([], []).
    """
    n = len(ring)
    cx, cy = sum(p[0] for p in ring) / n, sum(p[1] for p in ring) / n
    segments = [(ring[i], ring[(i + 1) % n]) for i in range(n)]
    inner = min(abs((b[0] - a[0]) * (cy - a[1]) - (b[1] - a[1]) * (cx - a[0])) / (math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0) for a, b in segments)
    on_ring = {}

    def is_on_ring(x, y):
        key = (round(x, 6), round(y, 6))
        hit = on_ring.get(key)
        if hit is None:
            hit = False
            if math.hypot(x - cx, y - cy) > inner - tol:   # 내접원 안은 경계에서 멀다 — 원 범위는 거의 다 여기서 걸러진다
                for (ax, ay), (bx, by) in segments:
                    dx, dy = bx - ax, by - ay
                    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
                    if math.hypot(x - ax - dx * t, y - ay - dy * t) <= tol:
                        hit = True
                        break
            on_ring[key] = hit
        return hit

    verts, faces, index, bottom = [], [], {}, {}

    def vertex(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in index:
            index[key] = len(verts)
            verts.append((x, y, z))
        return index[key]

    candidates = []   # 메시마다 한 면에만 속한 변 중 범위 링 위인 것
    for mesh_verts, mesh_faces in meshes:
        edges = {}
        for face in mesh_faces:
            for k in range(len(face)):
                a, b = face[k], face[(k + 1) % len(face)]
                if a != b:
                    edges[(min(a, b), max(a, b))] = edges.get((min(a, b), max(a, b)), 0) + 1
        for (a, b), count in edges.items():
            p, q = mesh_verts[a], mesh_verts[b]
            if count == 1 and math.hypot(q[0] - p[0], q[1] - p[1]) >= 1e-6 and is_on_ring(p[0], p[1]) and is_on_ring(q[0], q[1]) \
                    and is_on_ring((p[0] + q[0]) * 0.5, (p[1] + q[1]) * 0.5):
                candidates.append((p, q))
    # 두 메시(지형·도로)가 같이 가진 평면 변은 경계 근처 안쪽 변이다 — 둘 다 벽을 세우면 겹친다(성수 R=300 사각형, 길이 2 mm 변 3개)
    xy_key = lambda p, q: frozenset(((round(p[0], 4), round(p[1], 4)), (round(q[0], 4), round(q[1], 4))))
    shared = {}
    for p, q in candidates:
        shared[xy_key(p, q)] = shared.get(xy_key(p, q), 0) + 1
    for p, q in candidates:
        if shared[xy_key(p, q)] > 1:
            continue
        if (q[1] - p[1]) * ((p[0] + q[0]) * 0.5 - cx) - (q[0] - p[0]) * ((p[1] + q[1]) * 0.5 - cy) < 0:
            p, q = q, p   # 진행 방향 오른쪽 = 바깥
        faces.append((vertex(p[0], p[1], base_z), vertex(q[0], q[1], base_z), vertex(q[0], q[1], q[2]), vertex(p[0], p[1], p[2])))
        for x, y in (p[:2], q[:2]):
            bottom[(round(x, 6), round(y, 6))] = (x, y)
    if len(bottom) >= 3:
        center = vertex(cx, cy, base_z)
        rim = sorted(bottom.values(), key=lambda p: math.atan2(p[1] - cy, p[0] - cx))
        ids = [vertex(x, y, base_z) for x, y in rim]
        faces += [(center, ids[(k + 1) % len(ids)], ids[k]) for k in range(len(ids))]
    return verts, faces


def get_boundary_loops(faces):
    # type: (list) -> list
    """면 묶음(정점 번호 3·4각형, 같은 방향으로 돈다)의 경계 고리 ``[[정점 번호]]`` — 바깥 테두리와 구멍 모두, 면 돌림 방향 그대로.
    경계가 한 정점에서 갈리면(두 고리가 점으로 맞닿음) None — 고리를 하나로 정할 수 없다."""
    count = {}
    for face in faces:
        for k in range(len(face)):
            a, b = face[k], face[(k + 1) % len(face)]
            key = (a, b) if a < b else (b, a)
            count[key] = count.get(key, 0) + 1
    nxt = {}
    for face in faces:
        for k in range(len(face)):
            a, b = face[k], face[(k + 1) % len(face)]
            if a != b and count[(a, b) if a < b else (b, a)] == 1:
                if a in nxt:
                    return None
                nxt[a] = b
    loops = []
    while nxt:
        start = v = next(iter(nxt))
        loop = []
        while True:
            loop.append(v)
            v = nxt.pop(v, None)
            if v is None:
                return None
            if v == start:
                break
        if len(loop) >= 3:
            loops.append(loop)
    return loops


def get_planar_faces(verts, faces, groups, tol):
    # type: (list, list, list, float) -> tuple
    """메시 → Brep 평면 면 목록(context_geometry.get_mesh_brep이 이어 붙이기 없이 Brep을 조립한다).

    입력: verts ``[(x, y, z)]``, faces 3·4각형, groups = 같은 평면으로 묶인 면 번호 목록들(Mesh.MergeAllCoplanarFaces의 n-gon), tol(m).
    처리: 묶음마다 경계 고리(get_boundary_loops — 바깥 + 구멍) 하나의 면, 묶음에 없는 면은 그 면 하나(평면이 아닌 4각형은 삼각형 둘).
          정점은 좌표로 묶어(계단 지형은 벽·단 면 정점을 따로 둔다) 이웃 면이 같은 정점·변을 쓰게 한다. 고리를 못 정하는 묶음(점으로 맞닿음)과
          고리 넓이가 면 넓이 합과 다른 묶음(돌림 방향이 엇갈린 면 — 평탄면 높이를 가로지르는 대상지 경계 벽 띠, 성수 333-139 134.6 → 113.3 ㎡)은 면마다 따로.
    출력: ``(points, planes)`` — points ``[(x, y, z)]``, planes ``[(origin, x_axis, y_axis, loops)]``, loops ``[[(점 번호, u, v)]]``는
          바깥 고리 먼저(uv 반시계), 구멍은 시계. 넓이 0인 면은 뺀다.
    """
    keys, points = {}, []

    def point(i):
        p = verts[i]
        key = (round(p[0], 6), round(p[1], 6), round(p[2], 6))
        k = keys.get(key)
        if k is None:
            k = keys[key] = len(points)
            points.append(p)
        return k

    def newell(loops):
        """고리들(점 번호)의 뉴웰 벡터 = 넓이 × 2 × 법선(바깥 고리 반시계 쪽)."""
        nx = ny = nz = 0.0
        for loop in loops:
            for k in range(len(loop)):
                a, b = points[loop[k - 1]], points[loop[k]]
                nx += (a[1] - b[1]) * (a[2] + b[2])
                ny += (a[2] - b[2]) * (a[0] + b[0])
                nz += (a[0] - b[0]) * (a[1] + b[1])
        return nx, ny, nz

    def plane(loops):
        """고리들(점 번호) → (origin, x, y, uv 고리) 또는 None."""
        nx, ny, nz = newell(loops)
        size = math.sqrt(nx * nx + ny * ny + nz * nz)
        if size < 1e-9:
            return None
        z = (nx / size, ny / size, nz / size)
        ref = (1.0, 0.0, 0.0) if abs(z[0]) < 0.9 else (0.0, 1.0, 0.0)
        d = ref[0] * z[0] + ref[1] * z[1] + ref[2] * z[2]
        x = (ref[0] - d * z[0], ref[1] - d * z[1], ref[2] - d * z[2])
        lx = math.sqrt(x[0] * x[0] + x[1] * x[1] + x[2] * x[2])
        x = (x[0] / lx, x[1] / lx, x[2] / lx)
        y = (z[1] * x[2] - z[2] * x[1], z[2] * x[0] - z[0] * x[2], z[0] * x[1] - z[1] * x[0])
        o = points[loops[0][0]]
        uv_loops = []
        for loop in loops:
            uv = []
            for k in loop:
                p = points[k]
                dx, dy, dz = p[0] - o[0], p[1] - o[1], p[2] - o[2]
                if abs(dx * z[0] + dy * z[1] + dz * z[2]) > tol:
                    return None   # 평면이 아니다
                uv.append((k, dx * x[0] + dy * x[1] + dz * x[2], dx * y[0] + dy * y[1] + dz * y[2]))
            uv_loops.append(uv)
        areas = [get_ring_area([q[1:] for q in uv]) * get_ring_orientation([q[1:] for q in uv]) for uv in uv_loops]
        if sum(1 for a in areas if a > 0) != 1:
            return None
        outer = areas.index(max(areas))
        return o, x, y, [uv_loops[outer]] + [uv for k, uv in enumerate(uv_loops) if k != outer]

    def clean(loop):
        out = [k for n, k in enumerate(loop) if k != loop[n - 1]]
        return out if len(out) >= 3 else None

    planes, grouped = [], set()
    for group in groups:
        loops = get_boundary_loops([faces[f] for f in group]) if len(group) > 1 else None
        loops = [clean([point(i) for i in loop]) for loop in loops] if loops else None
        made = plane([loop for loop in loops if loop]) if loops and loops[0] else None
        if made:
            face_area = sum(0.5 * math.sqrt(sum(c * c for c in newell([[point(i) for i in faces[f]]]))) for f in group)
            loop_area = sum(get_ring_area([q[1:] for q in uv]) * get_ring_orientation([q[1:] for q in uv]) for uv in made[3])
            if abs(loop_area - face_area) > 1e-6 * face_area + 1e-6:
                made = None
        if made:
            planes.append(made)
            grouped.update(group)
    for f, face in enumerate(faces):
        if f in grouped:
            continue
        loop = clean([point(i) for i in face])
        if not loop:
            continue
        made = plane([loop])
        if made is None and len(loop) == 4:   # 평면이 아닌 4각형
            for tri in ((loop[0], loop[1], loop[2]), (loop[0], loop[2], loop[3])):
                made_tri = plane([list(tri)])
                if made_tri:
                    planes.append(made_tri)
        elif made:
            planes.append(made)
    return points, planes


def _get_boundary_edges(verts, faces):
    # type: (list, list) -> list
    """메시의 경계 변 ``[(p, q)]`` — 한 면에만 속한 변, 면이 위를 볼 때의 진행 방향(왼쪽 = 면 안쪽).
    정점은 좌표로 묶는다(이어 붙이기만 하고 용접하지 않은 Rhino 영역 메시의 이음매를 경계로 세지 않는다). 수직 면(평면 넓이 0)은 건너뛴다."""
    edges = {}
    for face in faces:
        pts = [verts[i] for i in face]
        area = sum(pts[k][0] * pts[(k + 1) % len(pts)][1] - pts[(k + 1) % len(pts)][0] * pts[k][1] for k in range(len(pts)))
        if abs(area) < 1e-9:
            continue
        if area < 0:
            pts.reverse()
        for k in range(len(pts)):
            p, q = pts[k], pts[(k + 1) % len(pts)]
            kp, kq = (round(p[0], 4), round(p[1], 4), round(p[2], 4)), (round(q[0], 4), round(q[1], 4), round(q[2], 4))
            if kp == kq:
                continue
            key = (kp, kq) if kp < kq else (kq, kp)
            edges[key] = None if key in edges else (p, q)
    return [edge for edge in edges.values() if edge]


class WaterShore(object):
    """수면 경계 색인 — (x, y)가 수면 경계(물가선) 위면 그 자리 수면 높이. 수면 = 판 여러 개를 이어 붙인 메시(로컬 m, 기울어도 된다)."""

    def __init__(self, water, tol=1e-3, cell=5.0):
        # type: (tuple, float, float) -> None
        self.tol, self.cell, self.grid = tol, float(cell), {}
        for p, q in _get_boundary_edges(*water):
            for i in range(int(math.floor((min(p[0], q[0]) - tol) / cell)), int(math.floor((max(p[0], q[0]) + tol) / cell)) + 1):
                for j in range(int(math.floor((min(p[1], q[1]) - tol) / cell)), int(math.floor((max(p[1], q[1]) + tol) / cell)) + 1):
                    self.grid.setdefault((i, j), []).append((p[0], p[1], q[0] - p[0], q[1] - p[1], p[2], q[2]))

    def get_hits(self, x, y):
        # type: (float, float) -> list
        """(x, y)를 지나는 수면 경계 변들의 그 자리 수면 높이(mm 반올림, 중복 없이 오름차순). 물가가 아니면 []."""
        hits = set()
        for ax, ay, dx, dy, za, zb in self.grid.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))), ()):
            t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
            if math.hypot(x - ax - dx * t, y - ay - dy * t) <= self.tol:
                hits.add(round(za + (zb - za) * t, 3))
        return sorted(hits)

    def get_z(self, x, y):
        # type: (float, float) -> object
        """물가선 위면 그 자리 수면 높이(여럿이면 낮은 것), 아니면 None."""
        hits = self.get_hits(x, y)
        return hits[0] if hits else None

    def get_near(self, x, y, reach):
        # type: (float, float, float) -> object
        """reach 안 가장 가까운 물가선 점 → (거리, 그 자리 수면 높이), 없으면 None. 물가 비탈(get_shore_fitted)용 — 칸 = reach 색인을 처음 부를 때 만든다."""
        if getattr(self, "_reach", None) != reach:
            self._reach, self._near = reach, {}
            for edges in self.grid.values():
                for edge in edges:
                    ax, ay, dx, dy = edge[:4]
                    for i in range(int(math.floor(min(ax, ax + dx) / reach)), int(math.floor(max(ax, ax + dx) / reach)) + 1):
                        for j in range(int(math.floor(min(ay, ay + dy) / reach)), int(math.floor(max(ay, ay + dy) / reach)) + 1):
                            self._near.setdefault((i, j), set()).add(edge)
        ci, cj = int(math.floor(x / reach)), int(math.floor(y / reach))
        best = None
        for i in (ci - 1, ci, ci + 1):
            for j in (cj - 1, cj, cj + 1):
                for ax, ay, dx, dy, za, zb in self._near.get((i, j), ()):
                    t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
                    d = math.hypot(x - ax - dx * t, y - ay - dy * t)
                    if d <= reach and (best is None or d < best[0]):
                        best = (d, za + (zb - za) * t)
        return best


def get_shore_fitted(verts, shore, reach=None):
    # type: (list, WaterShore, float) -> list
    """물가선 위 정점의 Z를 수면 높이로 맞추고, reach(기본 WATER_SHORE_FALLOFF) 안 정점은 수면 쪽으로 부드럽게 내린 새 정점 목록(하이드로 플래트닝 — 물가선 = 수위).
    물가 정점이 TIN의 '가장 가까운 입력점' 높이(둑 꼭대기 등고선 등)를 받아 수면과 수 m 떨어지던 것을 지형이 물가에서 비탈로 오르게 바꾼다.
    물가선 정점만 내리면 바로 안쪽 정점은 둑 높이 그대로라 한 면 폭에 수 m가 떨어져 물가가 톱니로 보였다(2026-11-08 사용자, 죽림리 301-3 구역 —
    매끈 지형에 수직면 330개·최대 6 m). 그래서 reach 안은 smoothstep으로 이어 내린다(수면보다 낮은 정점은 그대로)."""
    reach = constants.WATER_SHORE_FALLOFF if reach is None else reach
    out = []
    for x, y, z in verts:
        shore_z = shore.get_z(x, y)
        if shore_z is None and reach > 0:
            near = shore.get_near(x, y, reach)
            if near is not None and z > near[1]:
                t = near[0] / reach
                z = near[1] + (z - near[1]) * t * t * (3.0 - 2.0 * t)
        out.append((x, y, z if shore_z is None else shore_z))
    return out


def _is_on_ring(x, y, ring, tol):
    # type: (float, float, list, float) -> bool
    for k in range(len(ring)):
        (ax, ay), (bx, by) = ring[k][:2], ring[(k + 1) % len(ring)][:2]
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1.0)))
        if math.hypot(x - ax - dx * t, y - ay - dy * t) <= tol:
            return True
    return False


def get_water_surface(bodies, still, ring, window, grade, cell, tol=1e-3):
    # type: (list, list, list, float, float, float, float) -> tuple
    """수면 판마다 정점 높이(하이드로 플래트닝). 고인 물은 평평하게, 흐르는 물은 물가를 따라 하류로 매끄럽게 기운다.

    입력: bodies = 수면 폴리곤마다 지형(TIN)에 얹은 메시 ``[(verts, faces)]``(로컬 m). still = 판마다 고인 물인지.
          ring = 범위 링(로컬) — 범위에 잘린 수면 가장자리는 물가가 아니다. window = 물가 최저 창(m), grade = 수면 최대 기울기, cell = 안쪽 채움 격자(m).
    처리: ① 고인 물 = 물가 높이 하위 10 % 평면.
          ② 흐르는 물 — 물가 = 흐르는 판 전체의 바깥 경계(도엽 이음매는 두 판이 같이 가져 빠진다, 범위 링 위도 뺀다), 고인 물과 맞닿은 물가는
             그 수위 이하(강이 호수 높이로 들어간다). 물가 높이를 5 m 칸으로 솎아 창 안 최저(둑 꼭대기 등고선 같은 튀는 값을 버린다 —
             창 = max(window, 강폭 × 2), 강폭 ≈ 2 × 넓이 / 둘레라 넓은 강일수록 평평하다)
             → 기울기 grade 이하로 낮추는 하한 포락(등고선 5 m 간격 계단을 경사로로) → 격자 칸에 가장 가까운 물가 값을 채우고 몇 번 다듬어
             쌍선형 보간 — 단면은 양안 사이로 이어지고, 도엽으로 잘린 판도 자리의 함수라 저절로 이어진다.
    출력: ``(new_verts_list, levels)`` — 판마다 새 정점 목록(WATER_LIFT 전), levels = 판마다 (최저, 최고) Z.
    """
    out = [list(verts) for verts, _faces in bodies]
    for i, (verts, faces) in enumerate(bodies):
        if still[i] and verts:
            shore = sorted(q[2] for edge in _get_boundary_edges(verts, faces) for q in edge if not _is_on_ring(q[0], q[1], ring, 0.01))
            level = shore[len(shore) // 10] if shore else min(v[2] for v in verts)   # 물가 하위 10 % — 최저 한 점에 끌리지 않게(취리히 호수 최저 403.8·하위 10 % 405.8, 실제 약 406 m)
            out[i] = [(x, y, level) for x, y, _z in verts]
    flowing = [i for i in range(len(bodies)) if not still[i] and bodies[i][0]]
    if flowing:
        count, ends, owner = {}, {}, {}
        for i in flowing:
            verts, faces = bodies[i]
            for face in faces:
                for k in range(len(face)):
                    a, b = verts[face[k]], verts[face[(k + 1) % len(face)]]
                    ka, kb = (round(a[0], 3), round(a[1], 3)), (round(b[0], 3), round(b[1], 3))
                    if ka == kb:
                        continue
                    key = (ka, kb) if ka < kb else (kb, ka)
                    count[key] = count.get(key, 0) + 1
                    owner.setdefault(key, set()).add(i)
                    ends[ka], ends[kb] = a, b
        # 이어진 흐르는 물(도엽 이음매·본류에 붙은 곁가지)은 한 강 — 강폭과 창을 묶음 전체로 잰다(곁가지 폭 7 m가 창을 잡아
        # 성수 한강 옆 조각이 7.9 m에 남고 그 값이 한강 안쪽으로 번졌다). 강폭 ≈ 2 × 넓이 / 물가 둘레, 창 = max(window, 강폭 × 2)
        parent = {i: i for i in flowing}

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for ids in owner.values():
            first = next(iter(ids))
            for j in ids:
                parent[find(j)] = find(first)
        area, perimeter = {}, {}
        for i in flowing:
            verts, faces = bodies[i]
            area[find(i)] = area.get(find(i), 0.0) + sum(abs(get_ring_area([verts[v][:2] for v in face])) for face in faces)
        for key, n in count.items():
            d = math.hypot(key[1][0] - key[0][0], key[1][1] - key[0][1])
            if n == 1 and d <= 30.0:   # 물가는 수 m 간격 — 범위에 잘린 변·범위 모서리 가는 삼각형 변(성수 R=1000 650~1,200 m)은 30 m보다 길다
                root = find(next(iter(owner[key])))
                perimeter[root] = perimeter.get(root, 0.0) + d
        win_of = {i: max(window, 4.0 * area[find(i)] / perimeter[find(i)] if perimeter.get(find(i)) else window) for i in flowing}
        span = {}
        for key, ids in owner.items():
            for k_ in key:
                span[k_] = max([span.get(k_, 0.0)] + [win_of[i] for i in ids])
        still_bodies = [(out[i], bodies[i][1]) for i in range(len(bodies)) if still[i] and bodies[i][0]]
        still_shore = WaterShore(_join_meshes(still_bodies), tol) if still_bodies else None
        thin = {}   # 5 m 칸마다 가장 낮은 물가 점
        for key in {k for edge, n in count.items() if n == 1 for k in edge}:
            x, y, z = ends[key]
            if _is_on_ring(x, y, ring, 0.01):
                continue
            if still_shore is not None:
                lake_z = still_shore.get_z(x, y)
                if lake_z is not None:
                    z = min(z, lake_z)
            ck = (int(math.floor(x / 5.0)), int(math.floor(y / 5.0)))
            if ck not in thin or z < thin[ck][2]:
                thin[ck] = (x, y, z, max(span[key], thin[ck][3] if ck in thin else 0.0))
        samples = list(thin.values())
        if samples:
            out_levels = _get_shore_levels(samples, grade)
            raster = _ShoreRaster([(s_[0], s_[1], z) for s_, z in zip(samples, out_levels)], cell)
            for i in flowing:
                out[i] = [(x, y, raster.get_z(x, y)) for x, y, _z in bodies[i][0]]
    levels = [(min(v[2] for v in verts), max(v[2] for v in verts)) if verts else (0.0, 0.0) for verts in out]
    return out, levels


def _join_meshes(meshes):
    # type: (list) -> tuple
    verts, faces = [], []
    for mesh_verts, mesh_faces in meshes:
        start = len(verts)
        verts.extend(mesh_verts)
        faces.extend(tuple(start + i for i in face) for face in mesh_faces)
    return verts, faces


def _get_shore_levels(samples, grade):
    # type: (list, float) -> list
    """물가 점 ``[(x, y, z, window)]`` → 수위. 점마다 window 안 최저 → 기울기 grade 하한 포락(다익스트라, 이웃 = 15 m 안)."""
    import heapq
    cell = 50.0
    grid = {}
    for k, s_ in enumerate(samples):
        grid.setdefault((int(math.floor(s_[0] / cell)), int(math.floor(s_[1] / cell))), []).append(k)
    low = []
    for x, y, z, win in samples:
        i, j, reach = int(math.floor(x / cell)), int(math.floor(y / cell)), int(math.ceil(win / cell))
        best = z
        for di in range(-reach, reach + 1):
            for dj in range(-reach, reach + 1):
                for k in grid.get((i + di, j + dj), ()):
                    sx, sy, sz = samples[k][:3]
                    if sz < best and math.hypot(sx - x, sy - y) <= win:
                        best = sz
        low.append(best)
    link = 15.0
    near = {}
    for k, (x, y, _z, _w) in enumerate(samples):
        near.setdefault((int(math.floor(x / link)), int(math.floor(y / link))), []).append(k)
    level = list(low)
    heap = [(z, k) for k, z in enumerate(level)]
    heapq.heapify(heap)
    while heap:
        z, k = heapq.heappop(heap)
        if z > level[k]:
            continue
        x, y = samples[k][:2]
        i, j = int(math.floor(x / link)), int(math.floor(y / link))
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for m in near.get((i + di, j + dj), ()):
                    cand = z + grade * math.hypot(samples[m][0] - x, samples[m][1] - y)
                    if cand < level[m] - 1e-9:
                        level[m] = cand
                        heapq.heappush(heap, (cand, m))
    return level


class _ShoreRaster(object):
    """물가 수위를 격자에 채운 높이장 — 칸마다 가장 가까운 물가 값(다익스트라) → 물가가 없는 칸만 몇 번 이웃 평균(접힘 다듬기) → 쌍선형 보간."""

    def __init__(self, samples, cell, max_cells=40000, smooth=10):
        # type: (list, float, int, int) -> None
        import heapq
        xs, ys = [s[0] for s in samples], [s[1] for s in samples]
        pad = 2 * cell
        self.x0, self.y0 = min(xs) - pad, min(ys) - pad
        span = max(max(xs) - self.x0 + pad, max(ys) - self.y0 + pad)
        self.cell = max(float(cell), span / math.sqrt(max_cells))
        self.nx = int(math.ceil((max(xs) + pad - self.x0) / self.cell)) + 1
        self.ny = int(math.ceil((max(ys) + pad - self.y0) / self.cell)) + 1
        n = self.nx * self.ny
        dist, value, seed = [float("inf")] * n, [0.0] * n, [False] * n
        heap = []
        for x, y, z in samples:
            i, j = int(round((x - self.x0) / self.cell)), int(round((y - self.y0) / self.cell))
            k = j * self.nx + i
            d = math.hypot(x - (self.x0 + i * self.cell), y - (self.y0 + j * self.cell))
            if d < dist[k] or (d == dist[k] and z < value[k]):
                dist[k], value[k], seed[k] = d, z, True
        for k in range(n):
            if seed[k]:
                heap.append((dist[k], k))
        heapq.heapify(heap)
        steps = [(di, dj, math.hypot(di, dj) * self.cell) for di in (-1, 0, 1) for dj in (-1, 0, 1) if di or dj]
        while heap:
            d, k = heapq.heappop(heap)
            if d > dist[k]:
                continue
            i, j = k % self.nx, k // self.nx
            for di, dj, w in steps:
                a, b = i + di, j + dj
                if 0 <= a < self.nx and 0 <= b < self.ny:
                    m = b * self.nx + a
                    if d + w < dist[m]:
                        dist[m], value[m] = d + w, value[k]
                        heapq.heappush(heap, (d + w, m))
        for _ in range(smooth):
            nxt = list(value)
            for k in range(n):
                if seed[k]:
                    continue
                i, j = k % self.nx, k // self.nx
                total, cnt = 0.0, 0
                for a, b in ((i - 1, j), (i + 1, j), (i, j - 1), (i, j + 1)):
                    if 0 <= a < self.nx and 0 <= b < self.ny:
                        total += value[b * self.nx + a]
                        cnt += 1
                nxt[k] = total / cnt
            value = nxt
        self.value = value

    def get_z(self, x, y):
        # type: (float, float) -> float
        fx, fy = (x - self.x0) / self.cell, (y - self.y0) / self.cell
        i, j = max(0, min(self.nx - 2, int(math.floor(fx)))), max(0, min(self.ny - 2, int(math.floor(fy))))
        tx, ty = min(1.0, max(0.0, fx - i)), min(1.0, max(0.0, fy - j))
        v = self.value
        a, b = v[j * self.nx + i], v[j * self.nx + i + 1]
        c, d = v[(j + 1) * self.nx + i], v[(j + 1) * self.nx + i + 1]
        return (a * (1 - tx) + b * tx) * (1 - ty) + (c * (1 - tx) + d * tx) * ty


def get_water_walls(water, neighbors, tol=1e-3):
    # type: (tuple, list, float) -> tuple
    """수면 둘레에 남은 단차를 막는 세로 벽 — 물가는 get_shore_fitted로 수위에 맞추므로, 남는 것은 고인 물과 흐르는 물이
    다른 높이로 만나는 곳(댐·보)과 평탄화한 대상지 정도다. 막지 않으면 틈으로 뒤가 비친다.

    입력: water = 수면 메시 (verts, faces) — 판 여러 개(로컬 m, 기울어도 된다). neighbors = 둘레 메시들 ``[(verts, faces)]``.
    처리: 이웃 메시와 수면 자신의 경계 변 p→q마다 p·q·가운데가 모두 물가선 위이고 그 자리 수면이 변 끝보다 낮으면
          → 끝마다 바로 아래 수면 높이까지 벽(수면 쪽을 본다). 한 끝만 낮으면 3각형.
    출력: ``(verts, faces)`` — 면은 3·4각형. 벽이 없으면 ([], []).
    """
    shore = WaterShore(water, tol)
    verts, faces, index = [], [], {}

    def vertex(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in index:
            index[key] = len(verts)
            verts.append((x, y, z))
        return index[key]

    for mesh in [water] + list(neighbors):
        for p, q in _get_boundary_edges(*mesh):
            if math.hypot(q[0] - p[0], q[1] - p[1]) < tol:
                continue
            mid = shore.get_hits((p[0] + q[0]) * 0.5, (p[1] + q[1]) * 0.5)
            if not [h for h in mid if h < (p[2] + q[2]) * 0.5 - tol]:   # 변 가운데 아래에 수면이 없으면 막을 틈이 아니다
                continue
            ends = []
            for end in (p, q):   # 끝마다 바로 아래 수면, 없으면 그 끝이 수면 높이일 때만(벽이 거기서 0으로 줄어든다)
                hits = shore.get_hits(end[0], end[1])
                below = [h for h in hits if h < end[2] - tol]
                ends.append(max(below) if below else end[2] if any(abs(h - end[2]) <= tol for h in hits) else None)
            if None in ends:
                continue
            zp, zq = ends
            ring = [vertex(p[0], p[1], p[2])]   # p → (p 아래) → (q 아래) → q: 이웃 면 진행 방향 오른쪽 = 수면 쪽을 본다
            if p[2] > zp + tol:
                ring.append(vertex(p[0], p[1], zp))
            ring.append(vertex(q[0], q[1], zq))
            if q[2] > zq + tol:
                ring.append(vertex(q[0], q[1], q[2]))
            if len(ring) >= 3:
                faces.append(tuple(ring))
    return verts, faces


class TriangleZ(object):
    """세계좌표 삼각형 ``[((x,y,z)×3, …)]``의 높이 조회 — 격자 칸에 걸친 삼각형의 무게중심 보간(겹치면 높은 면). 입체 매스도 지형이 쓴다."""

    def __init__(self, tris, cell=20.0):
        # type: (list, float) -> None
        self.cell = float(cell)
        self.cells = {}
        self.min_z = min((p[2] for tri in tris for p in tri[:3]), default=0.0)
        for tri in tris:
            (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = tri[0], tri[1], tri[2]
            det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
            if abs(det) < 1e-9:
                continue
            item = (x0, y0, z0, x1 - x0, y1 - y0, x2 - x0, y2 - y0, 1.0 / det, z1 - z0, z2 - z0)
            for i in range(int(math.floor(min(x0, x1, x2) / self.cell)), int(math.floor(max(x0, x1, x2) / self.cell)) + 1):
                for j in range(int(math.floor(min(y0, y1, y2) / self.cell)), int(math.floor(max(y0, y1, y2) / self.cell)) + 1):
                    self.cells.setdefault((i, j), []).append(item)

    def get_z(self, x, y):
        # type: (float, float) -> float
        """수직 투영 Z. 빗나가면(삼각형 밖) 전체 최저 Z — TIN이 범위보다 넓어 범위 안에서는 거의 없다."""
        best = None
        for x0, y0, z0, e1x, e1y, e2x, e2y, inv, dz1, dz2 in self.cells.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))), ()):
            dx, dy = x - x0, y - y0
            u = (dx * e2y - dy * e2x) * inv
            v = (e1x * dy - e1y * dx) * inv
            if u >= -1e-9 and v >= -1e-9 and u + v <= 1.0 + 1e-9:
                z = z0 + u * dz1 + v * dz2
                if best is None or z > best:
                    best = z
        return self.min_z if best is None else best


def get_contour_segments(tris, step):
    # type: (list, float) -> list
    """삼각형 ``[((x,y,z)×3, …)]`` → 등고선 토막 ``[((x,y,z), (x,y,z))]`` (step m 간격, 삼각형마다 높이 하나에 토막 하나).
    정점 z = 높이면 위쪽으로 친다 — 변마다 교차가 0개 또는 2개라 토막이 끊기지 않는다."""
    out = []
    for tri in tris:
        pts = tri[:3]
        zs = [p[2] for p in pts]
        for k in range(int(math.floor(min(zs) / step)) + 1, int(math.floor(max(zs) / step)) + 1):
            level = k * step
            hits = []
            for i in range(3):
                a, b = pts[i], pts[(i + 1) % 3]
                if (a[2] >= level) != (b[2] >= level):
                    t = (level - a[2]) / (b[2] - a[2])
                    hits.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, level))
            if len(hits) == 2:
                out.append((hits[0], hits[1]))
    return out
