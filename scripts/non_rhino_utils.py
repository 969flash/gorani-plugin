"""Rhino에 의존하지 않는 범용 유틸을 제공한다.

좌표·GeoJSON 연산처럼 Rhino 없이 계산할 수 있는 것을 모은다.
이 모듈은 Python 딕셔너리·목록·숫자만 다루며 Rhino를 import하지 않는다.
Rhino 커브·벡터·Brep을 다루는 연산은 ``utils.py``에 둔다.
좌표 단위를 임의로 변환하지 않으며 프로젝트 내부 좌표는 m로 유지한다.
"""

import math
import os

import constants


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
        circle = 대상지 bbox 중심 원(EXTENT_CIRCLE_SEGMENTS각). rect = 대상지 bbox ± radius.
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
        return [(min_x - radius, min_y - radius), (max_x + radius, min_y - radius),
                (max_x + radius, max_y + radius), (min_x - radius, max_y + radius)]
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
        return "꼭짓점이 너무 많습니다(%d개 > %d) — 커브를 단순하게 다시 그리세요" % (len(ring), constants.AREA_MAX_VERTICES)
    min_x, min_y, max_x, max_y = get_bbox(ring)
    if max(max_x - min_x, max_y - min_y) > constants.AREA_MAX_SPAN:
        return "구역이 너무 큽니다(긴 변 %.1f km > %.1f km)" % (max(max_x - min_x, max_y - min_y) / 1000.0, constants.AREA_MAX_SPAN / 1000.0)
    if has_self_intersection(ring):
        return "변끼리 꼬여 있습니다(자기교차) — 꼬이지 않은 닫힌 도형이어야 합니다"
    area = get_ring_area(ring)
    if area < constants.AREA_MIN:
        return "구역이 너무 작습니다(%.0f ㎡ < %.0f ㎡) — 단위나 축척을 확인하세요" % (area, constants.AREA_MIN)
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
