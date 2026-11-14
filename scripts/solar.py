"""태양·그림자·일조시간·하늘 가림·바람장미 — 순수 파이썬(표준 라이브러리). docs/deliverables.md D.1, docs/data_sources.md 'NASA POWER'.

호스트와 무관하다 — Rhino 8·Rhino 7·SketchUp·Blender가 같은 결과를 낸다(도면 25~28, 패널 '해와 그림자'의 태양 방향).
좌표는 세계좌표 m(EPSG:5186 또는 대상지 지역 TM), +Y = 북. 시각은 진태양시(남중 = 12:00) — 일조 분석 관행이고 시간대·서머타임이 끼지 않는다.

    get_solar_day(y, m, d, lng) → (적위°, 균시차 분)           NOAA Solar Calculator 식
    get_sun_position(lat, decl, minutes) → (방위각°, 고도각°)   방위 = 북 0° 시계, 고도 = 대기 굴절 포함
    HeightGrid(bounds, cell, ground_z, buildings) → get_shadow(az, alt) → 칸별 그림자 여부(높이장 스윕, 지형·건물 같이)
    get_contour_rings(values, nx, ny, level, …) → 값 ≥ level 영역 테두리 링(마칭 스퀘어)
    get_horizon(...) → 방위 1°마다 지형·건물 가림 고도각
    get_wind_rose(...) → 16방위 × 풍속 등급 빈도
"""

import datetime
import json
import math
import os
import urllib.request

import constants
from non_rhino_utils import get_edge_chains


# ── 태양 위치 (NOAA Solar Calculator 스프레드시트 식 — 주소는 docs/data_sources.md §6) ──

def get_julian_day(year, month, day, hours_utc=12.0):
    # type: (int, int, int, float) -> float
    """그레고리력 날짜·UTC 시각 → 율리우스일."""
    if month <= 2:
        year, month = year - 1, month + 12
    a = year // 100
    b = 2 - a + a // 4
    return int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + b - 1524.5 + hours_utc / 24.0


def get_solar_day(year, month, day, lng=0.0):
    # type: (int, int, int, float) -> tuple
    """날짜 → (적위 °, 균시차 분). 그 경도의 진태양시 정오(UTC 12시 − 경도/15) 값 — 하루 안 변화(적위 ±0.4°)는 그림자에서 무시한다."""
    t = (get_julian_day(year, month, day, 12.0 - lng / 15.0) - 2451545.0) / 36525.0
    l0 = math.radians((280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0)
    m = math.radians(357.52911 + t * (35999.05029 - 0.0001537 * t))
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    c = (math.sin(m) * (1.914602 - t * (0.004817 + 0.000014 * t)) + math.sin(2 * m) * (0.019993 - 0.000101 * t) + math.sin(3 * m) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * t)
    app_long = math.radians(math.degrees(l0) + c - 0.00569 - 0.00478 * math.sin(omega))
    eps0 = 23.0 + (26.0 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60.0) / 60.0
    eps = math.radians(eps0 + 0.00256 * math.cos(omega))
    decl = math.degrees(math.asin(math.sin(eps) * math.sin(app_long)))
    y = math.tan(eps / 2.0) ** 2
    eot = 4.0 * math.degrees(y * math.sin(2 * l0) - 2 * e * math.sin(m) + 4 * e * y * math.sin(m) * math.cos(2 * l0)
                             - 0.5 * y * y * math.sin(4 * l0) - 1.25 * e * e * math.sin(2 * m))
    return decl, eot


def get_refraction(altitude):
    # type: (float) -> float
    """기하 고도각 ° → 대기 굴절 보정 °(NOAA 근사)."""
    if altitude > 85.0:
        return 0.0
    te = math.tan(math.radians(altitude))
    if altitude > 5.0:
        seconds = 58.1 / te - 0.07 / te ** 3 + 0.000086 / te ** 5
    elif altitude > -0.575:
        seconds = 1735.0 + altitude * (-518.2 + altitude * (103.4 + altitude * (-12.79 + altitude * 0.711)))
    else:
        seconds = -20.772 / te
    return seconds / 3600.0


def get_sun_position(lat, decl, solar_minutes):
    # type: (float, float, float) -> tuple
    """위도 °·적위 °·진태양시(자정부터 분) → (방위각 °(북 0, 시계), 고도각 °(굴절 포함))."""
    phi, delta = math.radians(lat), math.radians(decl)
    hour_angle = math.radians(solar_minutes / 4.0 - 180.0)
    cos_zenith = max(-1.0, min(1.0, math.sin(phi) * math.sin(delta) + math.cos(phi) * math.cos(delta) * math.cos(hour_angle)))
    altitude = 90.0 - math.degrees(math.acos(cos_zenith))
    azimuth = math.degrees(math.atan2(math.sin(hour_angle), math.cos(hour_angle) * math.sin(phi) - math.tan(delta) * math.cos(phi))) + 180.0
    return azimuth % 360.0, altitude + get_refraction(altitude)


def get_sun_vector(azimuth, altitude):
    # type: (float, float) -> tuple
    """방위·고도 ° → 해 쪽 단위 벡터 (동, 북, 위)."""
    az, alt = math.radians(azimuth), math.radians(altitude)
    return (math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt))


def get_daylight(lat, decl):
    # type: (float, float) -> tuple
    """(해 뜨는, 지는 진태양시 분). 고도 −0.833°(굴절·해 반지름) 기준. 백야 (0, 1440), 극야 (720, 720)."""
    phi, delta = math.radians(lat), math.radians(decl)
    cos_h = (math.sin(math.radians(-0.833)) - math.sin(phi) * math.sin(delta)) / (math.cos(phi) * math.cos(delta) or 1e-12)
    if cos_h <= -1.0:
        return 0.0, 1440.0
    if cos_h >= 1.0:
        return 720.0, 720.0
    half = math.degrees(math.acos(cos_h)) * 4.0
    return 720.0 - half, 720.0 + half


def get_clock_minutes(solar_minutes, lng, tz_hours, eot):
    # type: (float, float, float, float) -> float
    """진태양시 → 표준시(그 시간대) 분. 서울(127°E, KST) 남중 ≈ 12:32 ± 균시차."""
    return solar_minutes - eot - 4.0 * (lng - 15.0 * tz_hours)


def get_season_date(season, lat, year):
    # type: (str, float, int) -> tuple
    """하지·춘추분·동지(SUN_SEASON_DATES, 북반구 날짜) → (년, 월, 일). 남반구는 하지·동지가 바뀐다(동지 = 해가 가장 낮은 날)."""
    if lat < 0 and season in ("summer", "winter"):
        season = "winter" if season == "summer" else "summer"
    month, day = constants.SUN_SEASON_DATES[season]
    return year, month, day


def get_season_sun(season, lat, lng, year):
    # type: (str, float, float, int) -> dict
    """계절 하나의 해 — {date(년, 월, 일), decl, eot, daylight(뜨는·지는 분)}."""
    date = get_season_date(season, lat, year)
    decl, eot = get_solar_day(date[0], date[1], date[2], lng)
    return {"date": date, "decl": decl, "eot": eot, "daylight": get_daylight(lat, decl)}


def get_format_minutes(minutes):
    # type: (float) -> str
    """분 → 'HH:MM'."""
    minutes = int(round(minutes)) % 1440
    return "%02d:%02d" % (minutes // 60, minutes % 60)


# ── 높이장 그림자 (지형 + 건물) ──────────────────────────

class HeightGrid(object):
    """분석 격자 — 칸 중심의 지반 높이(ground)와 표면 높이(surface = 지반 또는 건물 지붕). 행 j는 남 → 북, 열 i는 서 → 동.

    입력: bounds(min_x, min_y, max_x, max_y) m, cell m, ground_z(x, y) → z 또는 None(자료 밖 — 가까운 칸 값으로 메운다),
          buildings [(링들 — 외곽·구멍, 지붕 z)] (발자국 최저 지반 + 높이 — 3D와 같다).
    ponytail: 칸 중심 표본이라 칸보다 좁은 틈·건물은 뭉개진다. 칸은 SUN_GRID_MAX_CELLS로 정한다(500 m 범위 ≈ 2 m).
    """

    def __init__(self, bounds, cell, ground_z, buildings):
        self.cell = float(cell)
        self.x0, self.y0 = float(bounds[0]), float(bounds[1])
        self.nx = max(2, int(math.ceil((bounds[2] - bounds[0]) / self.cell)))
        self.ny = max(2, int(math.ceil((bounds[3] - bounds[1]) / self.cell)))
        self.ground = get_filled_rows([ground_z(self.x0 + (i + 0.5) * self.cell, self.y0 + (j + 0.5) * self.cell)
                                       for j in range(self.ny) for i in range(self.nx)], self.nx, self.ny)
        self.surface = list(self.ground)
        self.roof = [False] * (self.nx * self.ny)
        self.add_buildings(buildings)

    def add_buildings(self, buildings):
        # type: (list) -> None
        """[(링들, 지붕 z)]를 표면에 올린다(칸 중심이 발자국 안이면 지붕 z와 큰 쪽)."""
        for rings, top in buildings:
            for index in self.get_ring_cells(rings):
                if top > self.surface[index]:
                    self.surface[index] = top
                self.roof[index] = True

    def get_ground_at(self, x, y):
        # type: (float, float) -> float
        """가장 가까운 칸의 지반 높이(격자 밖은 가장자리 칸) — 지형 자료 밖 건물의 바닥."""
        i = min(self.nx - 1, max(0, int((x - self.x0) / self.cell)))
        j = min(self.ny - 1, max(0, int((y - self.y0) / self.cell)))
        return self.ground[j * self.nx + i]

    def get_ring_cells(self, rings):
        # type: (list) -> list
        """링들(짝홀 규칙 — 구멍 포함)이 덮는 칸 번호. 칸 중심 스캔라인."""
        cell, nx = self.cell, self.nx
        rows = {}
        ys = [p[1] for ring in rings for p in ring]
        if not ys:
            return []
        j0 = max(0, int(math.ceil((min(ys) - self.y0) / cell - 0.5)))
        j1 = min(self.ny - 1, int(math.floor((max(ys) - self.y0) / cell - 0.5)))
        for ring in rings:
            for a, b in zip(ring, ring[1:] + ring[:1]):
                if a[1] == b[1]:
                    continue
                low, high = (a, b) if a[1] < b[1] else (b, a)
                for j in range(max(j0, int(math.ceil((low[1] - self.y0) / cell - 0.5))), min(j1, int(math.ceil((high[1] - self.y0) / cell - 0.5)) - 1) + 1):
                    yc = self.y0 + (j + 0.5) * cell
                    rows.setdefault(j, []).append(low[0] + (yc - low[1]) * (high[0] - low[0]) / (high[1] - low[1]))
        out = []
        for j, xs in rows.items():
            xs.sort()
            for xa, xb in zip(xs[0::2], xs[1::2]):
                i0 = max(0, int(math.ceil((xa - self.x0) / cell - 0.5)))
                i1 = min(nx - 1, int(math.floor((xb - self.x0) / cell - 0.5)))
                out.extend(range(j * nx + i0, j * nx + i1 + 1))
        return out

    def get_shadow(self, azimuth, altitude):
        # type: (float, float) -> list
        """해 방위·고도 ° → 칸별 그림자 여부(bool 목록). 해가 지평선 아래면 전부 그림자.
        래스터 광선: 해 방향과 나란한 선들(브레즌햄 — 긴 축 한 칸마다 짧은 축은 반올림)이 칸을 하나씩 나눠 가져, 선마다 해 쪽에서부터
        '가림 높이 = max(앞 칸 표면, 앞 칸 가림 높이) − 한 걸음 × tan(고도)'를 이어 간다. 칸 하나에 O(1), 보간이 없어 그림자 가장자리가
        깎이지 않는다(선형 보간 스윕은 30° 방향 상자 그림자를 15 % 작게 냈다, 2026-11-14). 칸 표면보다 가림이 높으면 그림자.
        격자 밖은 가림이 없다고 본다(격자 = 범위 + SUN_SHADOW_REACH)."""
        nx, ny = self.nx, self.ny
        if altitude <= 0.0:
            return [True] * (nx * ny)
        surface = self.surface
        ux, uy = math.sin(math.radians(azimuth)), math.cos(math.radians(azimuth))   # 해 쪽 수평 방향(동, 북)
        tan_alt = math.tan(math.radians(altitude))
        low = -1e9
        occ = [low] * (nx * ny)
        x_major = abs(ux) >= abs(uy)
        long_n, short_n = (nx, ny) if x_major else (ny, nx)
        along = ux if x_major else uy
        slope = -(uy if x_major else ux) / abs(along)   # 해에서 멀어지며 긴 축 한 칸마다 짧은 축이 바뀌는 칸 수
        drop = self.cell * math.sqrt(1.0 + slope * slope) * tan_alt
        order = range(long_n - 1, -1, -1) if along > 0 else range(long_n)   # 해 쪽부터
        offsets = [int(math.floor(slope * c + 0.5)) for c in range(long_n)]
        base = max(offsets)   # 선 번호 k = 짧은 축 − 오프셋 + base ≥ 0
        run = [low] * (short_n + base - min(offsets) + 1)
        # 다음 칸 중심에 닿는 가림 = max(이 칸에서 시작하는 가림, 들어온 가림 − 한 걸음). 이 칸에서 시작하는 가림은 지형이면 칸 중심 높이 − 한 걸음,
        # 건물이면 지붕 − 반 걸음(건물은 칸 끝까지 선다 — 칸 중심에서 재면 그림자가 반 칸 짧았다). 지형까지 반 걸음으로 재니
        # tan(고도)/2보다 가파른 뒷비탈이 가짜 그늘로 점점이 찍혔다(성북동 하지, 2026-11-14)
        half = drop * 0.5
        start = [h - half if r else h - drop for h, r in zip(surface, self.roof)]
        for c, a in enumerate(order):
            shift = base - offsets[c]
            for b in range(short_n):
                index = b * nx + a if x_major else a * nx + b
                k = b + shift
                prev = run[k]
                occ[index] = prev
                h = start[index]
                prev -= drop
                run[k] = h if h > prev else prev
        eps = constants.SUN_SHADOW_EPS
        return [o > s_ + eps for o, s_ in zip(occ, surface)]

    def get_point(self, index):
        # type: (int) -> tuple
        """칸 번호 → 칸 중심 (x, y)."""
        j, i = divmod(index, self.nx)
        return self.x0 + (i + 0.5) * self.cell, self.y0 + (j + 0.5) * self.cell


def get_filled_rows(values, nx, ny):
    # type: (list, int, int) -> list
    """None(지형 자료 밖) 칸을 가까운 값으로 메운다 — 행 안에서 가까운 쪽, 빈 행은 가까운 행. 다 비면 0.
    지형 밖을 최저값으로 두면 구덩이가 되어 가장자리에 가짜 종일 그늘이 생겼다(성북동 R250 북쪽 띠, 2026-11-14)."""
    out = list(values)
    filled_rows = []
    for j in range(ny):
        row = out[j * nx:(j + 1) * nx]
        known = [i for i, v in enumerate(row) if v is not None]
        if known:
            filled_rows.append(j)
            for i in range(nx):
                if row[i] is None:
                    nearest = min(known, key=lambda k: abs(k - i))   # ponytail: 행마다 O(n·빈칸) — 빈칸은 가장자리 몇 줄뿐
                    row[i] = row[nearest]
            out[j * nx:(j + 1) * nx] = row
    for j in range(ny):
        if j not in filled_rows:
            src = min(filled_rows, key=lambda k: abs(k - j)) if filled_rows else None
            out[j * nx:(j + 1) * nx] = out[src * nx:(src + 1) * nx] if src is not None else [0.0] * nx
    return out


def get_grid_cell(bounds):
    # type: (tuple) -> float
    """격자 칸 m — 칸 수가 SUN_GRID_MAX_CELLS 이하가 되는 가장 작은 칸(SUN_GRID_MIN_CELL 이상, 0.5 m 단위 올림)."""
    area = max(1.0, (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]))
    cell = max(constants.SUN_GRID_MIN_CELL, math.sqrt(area / constants.SUN_GRID_MAX_CELLS))
    return math.ceil(cell * 2.0) / 2.0


def get_shadow_counts(grid, lat, sun, hours):
    # type: (HeightGrid, float, dict, list) -> tuple
    """시각들(진태양시 시)의 그림자를 겹친 칸별 횟수와 [(시, 방위, 고도)]. 해가 진 시각은 센다(종일 그림자 쪽)."""
    counts = [0] * (grid.nx * grid.ny)
    positions = []
    for hour in hours:
        azimuth, altitude = get_sun_position(lat, sun["decl"], hour * 60.0)
        positions.append((hour, azimuth, altitude))
        counts = [count + shadowed for count, shadowed in zip(counts, grid.get_shadow(azimuth, altitude))]
    return counts, positions


def get_sun_hours(grid, lat, sun, window=None, step_min=None):
    # type: (HeightGrid, float, dict, tuple, float) -> list
    """칸별 일조시간(시) — 창(진태양시 시, SUN_HOURS_WINDOW) 안을 step_min 간격 가운데 표본으로 센다. 해가 뜨기 전·진 뒤는 0."""
    window = window or constants.SUN_HOURS_WINDOW
    step = float(step_min or constants.SUN_HOURS_STEP_MIN)
    total = [0] * (grid.nx * grid.ny)
    minute = window[0] * 60.0 + step * 0.5
    while minute < window[1] * 60.0:
        azimuth, altitude = get_sun_position(lat, sun["decl"], minute)
        if altitude > 0.0:
            total = [count + (not shadowed) for count, shadowed in zip(total, grid.get_shadow(azimuth, altitude))]
        minute += step
    return [count * step / 60.0 for count in total]


# ── 마칭 스퀘어 — 칸 값 ≥ level 영역의 테두리 ─────────────

def get_contour_rings(values, nx, ny, level, x0, y0, cell):
    # type: (list, int, int, float, float, float, float) -> list
    """칸 중심 값(행 우선, j = 남 → 북) → level 등치선 링 [(x, y)…] 목록. 격자 밖은 level 아래로 보아 링이 늘 닫힌다.
    링 방향은 섞여 있다 — 짝홀 규칙(evenodd)으로 칠하면 영역이 된다. 안장(대각 두 칸만 위)은 네 칸 평균으로 가른다."""
    def value(i, j):
        return values[j * nx + i] if 0 <= i < nx and 0 <= j < ny else level - 1.0

    def point(key):
        kind, i, j = key   # h: (i, j)–(i+1, j) 사이, v: (i, j)–(i, j+1) 사이
        a = value(i, j)
        b = value(i + 1, j) if kind == "h" else value(i, j + 1)
        t = 0.5 if a == b else max(0.0, min(1.0, (level - a) / (b - a)))
        if kind == "h":
            return x0 + (i + 0.5 + t) * cell, y0 + (j + 0.5) * cell
        return x0 + (i + 0.5) * cell, y0 + (j + 0.5 + t) * cell

    edges = []
    for j in range(-1, ny):
        for i in range(-1, nx):
            a, b, c, d = value(i, j), value(i + 1, j), value(i + 1, j + 1), value(i, j + 1)   # 좌하·우하·우상·좌상
            code = (a >= level) | (b >= level) << 1 | (c >= level) << 2 | (d >= level) << 3
            if code in (0, 15):
                continue
            bottom, right, top, left = ("h", i, j), ("v", i + 1, j), ("h", i, j + 1), ("v", i, j)
            if code in (5, 10):   # 가운데가 높으면 낮은 두 모서리를, 낮으면 높은 두 모서리를 떼어 낸다
                cut_ac = (code == 5) != ((a + b + c + d) * 0.25 >= level)   # 좌하(a)·우상(c)을 떼어 낸다
                edges += [(left, bottom), (right, top)] if cut_ac else [(bottom, right), (left, top)]
                continue
            pair = _MARCHING_PAIRS[code]
            sides = {"b": bottom, "r": right, "t": top, "l": left}
            edges.append((sides[pair[0]], sides[pair[1]]))
    return [[point(key) for key in chain] for chain in get_edge_chains(edges, True)]


_MARCHING_PAIRS = {1: "lb", 2: "br", 3: "lr", 4: "rt", 6: "bt", 7: "lt", 8: "tl", 9: "bt", 11: "rt", 12: "lr", 13: "br", 14: "lb"}


def get_simplified_ring(ring, tolerance):
    # type: (list, float) -> list
    """닫힌 링을 더글러스-포이커로 줄인다(tolerance m). 점이 3개 미만이 되면 원래 링."""
    if len(ring) < 8:
        return ring

    def reduce(points):
        keep = [False] * len(points)
        keep[0] = keep[-1] = True
        stack = [(0, len(points) - 1)]
        while stack:
            s, e = stack.pop()
            ax, ay = points[s]
            bx, by = points[e]
            dx, dy = bx - ax, by - ay
            length = math.hypot(dx, dy) or 1e-12
            best, index = -1.0, -1
            for k in range(s + 1, e):
                px, py = points[k]
                dist = abs(dx * (ay - py) - dy * (ax - px)) / length
                if dist > best:
                    best, index = dist, k
            if index > 0 and best > tolerance:
                keep[index] = True
                stack += [(s, index), (index, e)]
        return [p for p, k in zip(points, keep) if k]

    far = max(range(len(ring)), key=lambda k: (ring[k][0] - ring[0][0]) ** 2 + (ring[k][1] - ring[0][1]) ** 2)
    out = reduce(ring[:far + 1])[:-1] + reduce(ring[far:] + ring[:1])[:-1]
    return out if len(out) >= 3 else ring


# ── 하늘 가림 (관측점에서 본 지형·건물 실루엣) ─────────────

def get_building_horizon(observer, buildings, step_deg=None):
    # type: (tuple, list, float) -> list
    """관측점 (x, y, z)에서 본 방위별 건물 가림 고도각 ° 목록(방위 0 = 북부터 step_deg 간격). 건물은 [(링들, 지붕 z)].
    지붕 테두리를 방위 0.5° 이하 간격으로 쪼개 칸마다 가장 높은 각을 남긴다(관측점에 가까운 테두리가 가장 높다)."""
    step = float(step_deg or constants.SUN_MASK_STEP_DEG)
    bins = int(round(360.0 / step))
    alts = [0.0] * bins
    ox, oy, oz = observer
    for rings, top in buildings:
        rise = top - oz
        if rise <= 0.0:
            continue
        for ring in rings:
            for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
                az_a = math.degrees(math.atan2(ax - ox, ay - oy))
                az_b = math.degrees(math.atan2(bx - ox, by - oy))
                span = abs((az_b - az_a + 180.0) % 360.0 - 180.0)
                n = max(1, int(math.ceil(span / (step * 0.5))))
                for k in range(n + 1):
                    x, y = ax + (bx - ax) * k / n, ay + (by - ay) * k / n
                    dist = math.hypot(x - ox, y - oy)
                    if dist < 0.5:
                        continue
                    alt = math.degrees(math.atan2(rise, dist))
                    index = int(((math.degrees(math.atan2(x - ox, y - oy)) % 360.0) + step * 0.5) / step) % bins
                    if alt > alts[index]:
                        alts[index] = alt
    return alts


def get_terrain_horizon(observer, height_at, max_dist, step_deg=None, step_m=None, start_m=None):
    # type: (tuple, object, float, float, float, float) -> list
    """관측점에서 방위마다 지형을 따라 걸으며 가장 높은 고도각 °(아래로 보이면 0). height_at(x, y) → z 또는 None(자료 밖 — 그 방위는 거기서 멈춘다).
    걸음은 가까이 step_m, 멀수록 넓힌다(거리 × SUN_MASK_STEP_GROWTH) — 먼 산은 각이 작게 변한다."""
    step = float(step_deg or constants.SUN_MASK_STEP_DEG)
    base_step = float(step_m or constants.SUN_MASK_TERRAIN_STEP)
    bins = int(round(360.0 / step))
    ox, oy, oz = observer
    alts = [0.0] * bins
    for index in range(bins):
        az = math.radians(index * step)
        dx, dy = math.sin(az), math.cos(az)
        dist = float(start_m or base_step)
        best = 0.0
        while dist <= max_dist:
            z = height_at(ox + dx * dist, oy + dy * dist)
            if z is not None:
                alt = math.degrees(math.atan2(z - oz, dist))
                if alt > best:
                    best = alt
            dist += max(base_step, dist * constants.SUN_MASK_STEP_GROWTH)
        alts[index] = best
    return alts


def get_visible_minutes(lat, sun, horizon, step_min=5.0):
    # type: (float, dict, list, float) -> float
    """하늘 가림(방위별 고도각 — 지형·건물 중 큰 값) 위로 해가 보이는 분 — 해 뜰 때부터 질 때까지 step_min 표본."""
    bins = len(horizon)
    rise, set_ = sun["daylight"]
    visible, minute = 0.0, rise + step_min * 0.5
    while minute < set_:
        azimuth, altitude = get_sun_position(lat, sun["decl"], minute)
        if altitude > 0.0 and altitude > horizon[int((azimuth + 180.0 / bins) / (360.0 / bins)) % bins]:
            visible += step_min
        minute += step_min
    return visible


# ── 바람장미 (NASA POWER 시간별 지상 10 m 풍향·풍속) ──────

def get_wind_url(lat, lng, start_year, end_year):
    # type: (float, float, int, int) -> str
    """NASA POWER Hourly API 주소 — 지방 태양시(LST) 기준 WS10M·WD10M, start_year 1월 1일 ~ end_year 12월 31일."""
    return constants.WIND_POWER_URL.format(lat=round(lat, 4), lng=round(lng, 4), start="%d0101" % start_year, end="%d1231" % end_year)


def get_wind_years(today=None):
    # type: (datetime.date) -> tuple
    """(첫 해, 끝 해) — 끝난 해 기준 최근 WIND_YEARS년. 올해는 자료가 늦게 들어와(근실시간) 뺀다."""
    end = (today or datetime.date.today()).year - 1
    return end - constants.WIND_YEARS + 1, end


def get_wind_records(lat, lng, today=None, cache_dir=None, fetch=None):
    # type: (float, float, datetime.date, str, object) -> dict
    """대상지 격자의 시간별 바람 → 집계표 {months: [12달 × 16방위 × 등급 수], calm: [12달], total: [12달], speed_sum: [12달], start, end, lat, lng}.
    월별로만 남겨 캐시한다(HOME_DIR/data/cache — 원자료 3 MB를 두지 않는다). 못 받으면 예외 — 도면이 '바람 자료 못 받음'으로 빈다."""
    if not constants.WIND_POWER_URL:   # Blender판 — 외부 기상 서비스를 부르지 않는다(dev_deploy.BLENDER_CONSTANT_PATCHES)
        raise RuntimeError("wind source disabled")
    start, end = get_wind_years(today)
    key = "wind_%.2f_%.2f_%d_%d.json" % (lat, lng, start, end)   # POWER 격자(0.5°×0.625°)보다 잘게 — 같은 동네는 같은 파일
    cache_dir = cache_dir or os.path.join(constants.HOME_DIR, "data", "cache")
    path = os.path.join(cache_dir, key)
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as handle:
                return json.load(handle)
        except (OSError, ValueError):
            pass
    if fetch is None:
        def fetch(url):
            request = urllib.request.Request(url, headers={"User-Agent": constants.OSM_USER_AGENT})
            with urllib.request.urlopen(request, timeout=constants.WIND_TIMEOUT_SECONDS) as response:
                return json.loads(response.read().decode("utf-8"))
    payload = fetch(get_wind_url(lat, lng, start, end))
    params = payload["properties"]["parameter"]
    fill = (payload.get("header") or {}).get("fill_value", -999.0)
    table = get_wind_table(params["WS10M"], params["WD10M"], fill)
    table.update(start=start, end=end, lat=lat, lng=lng, source=(payload.get("header") or {}).get("sources") or [],
                 api=((payload.get("header") or {}).get("api") or {}).get("version", ""), grid=(payload.get("geometry") or {}).get("coordinates"))
    try:
        os.makedirs(cache_dir, exist_ok=True)
        with open(path + ".tmp", "w", encoding="utf-8") as handle:
            json.dump(table, handle)
        os.replace(path + ".tmp", path)
    except OSError:
        pass
    return table


def get_wind_table(speeds, directions, fill=-999.0):
    # type: (dict, dict, float) -> dict
    """POWER 시간별 {YYYYMMDDHH: 값} 둘 → 월별 16방위 × 풍속 등급(WIND_SPEED_BREAKS) 횟수. 풍속 < 첫 경계 = 정온(방향 없음).
    풍향은 '불어오는' 쪽(기상 관례, 북 0° 시계)."""
    breaks = constants.WIND_SPEED_BREAKS
    sectors = constants.WIND_SECTORS
    width = 360.0 / sectors
    months = [[[0] * (len(breaks) - 1 + 1) for _ in range(sectors)] for _ in range(12)]
    calm, total, speed_sum = [0] * 12, [0] * 12, [0.0] * 12
    for stamp, speed in speeds.items():
        direction = directions.get(stamp)
        if speed is None or direction is None or speed <= fill or direction <= fill:
            continue
        month = int(stamp[4:6]) - 1
        total[month] += 1
        speed_sum[month] += speed
        if speed < breaks[0]:
            calm[month] += 1
            continue
        level = sum(1 for b in breaks[1:] if speed >= b)
        months[month][int(((direction % 360.0) + width * 0.5) / width) % sectors][level] += 1
    return {"months": months, "calm": calm, "total": total, "speed_sum": speed_sum}


def get_wind_rose(table, month_numbers):
    # type: (dict, tuple) -> dict
    """집계표 + 달(1~12) 묶음 → {freq: [방위][등급] %, calm %, total, mean m/s, top(최다 방위 번호), top_share %}."""
    sectors = constants.WIND_SECTORS
    levels = len(constants.WIND_SPEED_BREAKS)
    counts = [[0] * levels for _ in range(sectors)]
    calm = total = 0
    speed_sum = 0.0
    for month in month_numbers:
        m = month - 1
        for s in range(sectors):
            for k in range(levels):
                counts[s][k] += table["months"][m][s][k]
        calm += table["calm"][m]
        total += table["total"][m]
        speed_sum += table["speed_sum"][m]
    scale = 100.0 / total if total else 0.0
    freq = [[c * scale for c in row] for row in counts]
    shares = [sum(row) for row in freq]
    top = max(range(sectors), key=lambda s: shares[s]) if total else 0
    return {"freq": freq, "calm": calm * scale, "total": total, "mean": speed_sum / total if total else 0.0, "top": top, "top_share": shares[top] if total else 0.0}


def get_wind_seasons(lat):
    # type: (float) -> list
    """[(라벨 키, 달 묶음)] — 연간 + 계절 넷. 남반구는 계절 이름이 반대(3~5월 = 가을)."""
    north = lat >= 0
    return [("연간", tuple(range(1, 13))), ("봄" if north else "가을", (3, 4, 5)), ("여름" if north else "겨울", (6, 7, 8)),
            ("가을" if north else "봄", (9, 10, 11)), ("겨울" if north else "여름", (12, 1, 2))]
