"""solar(태양 위치·그림자 스윕·등치선·하늘 가림·바람장미)와 도면 25~28, 패널 set_sun 상태. 표준 라이브러리만, Rhino 없음."""

import json
import math
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants   # noqa: E402
import context_builder   # noqa: E402
import non_rhino_utils   # noqa: E402
import sheet_svg   # noqa: E402
import solar   # noqa: E402

os.environ[constants.LANG_ENV] = "ko"
SEOUL = (37.5665, 126.978)   # 서울시청
SVG = "{http://www.w3.org/2000/svg}"


class SunPositionTest(unittest.TestCase):
    def test_solstice_declination_and_noon_altitude(self):
        lat, lng = SEOUL
        winter = solar.get_season_sun("winter", lat, lng, 2026)
        summer = solar.get_season_sun("summer", lat, lng, 2026)
        self.assertAlmostEqual(winter["decl"], -23.44, delta=0.05)
        self.assertAlmostEqual(summer["decl"], 23.44, delta=0.05)
        azimuth, altitude = solar.get_sun_position(lat, winter["decl"], 720.0)
        self.assertAlmostEqual(azimuth, 180.0, delta=0.01)
        self.assertAlmostEqual(altitude, 90.0 - lat + winter["decl"], delta=0.1)   # 남중 고도 ≈ 29.0°(굴절 0.03°)

    def test_equation_of_time(self):
        self.assertAlmostEqual(solar.get_solar_day(2026, 2, 11, 0.0)[1], -14.2, delta=0.3)   # 2월 중순 최저
        self.assertAlmostEqual(solar.get_solar_day(2026, 11, 3, 0.0)[1], 16.4, delta=0.3)    # 11월 초 최고

    def test_seoul_day_length_matches_kasi(self):
        """한국천문연구원 서울 동지 낮 9:34·하지 14:46 — 굴절 −0.833° 기준이면 ±3분."""
        lat, lng = SEOUL
        for season, minutes in (("winter", 9 * 60 + 34), ("summer", 14 * 60 + 46)):
            rise, set_ = solar.get_season_sun(season, lat, lng, 2026)["daylight"]
            self.assertAlmostEqual(set_ - rise, minutes, delta=3)

    def test_kst_solar_noon(self):
        """서울 진태양시 정오 = KST 12:32 − 균시차(11월 중순 +15분 → 12:16)."""
        _decl, eot = solar.get_solar_day(2026, 11, 14, SEOUL[1])
        self.assertEqual(solar.get_format_minutes(solar.get_clock_minutes(720.0, SEOUL[1], 9.0, eot)), "12:16")

    def test_morning_afternoon_mirror(self):
        decl = solar.get_season_sun("equinox", SEOUL[0], SEOUL[1], 2026)["decl"]
        am, pm = solar.get_sun_position(SEOUL[0], decl, 9 * 60), solar.get_sun_position(SEOUL[0], decl, 15 * 60)
        self.assertAlmostEqual(am[0], 360.0 - pm[0], places=6)
        self.assertAlmostEqual(am[1], pm[1], places=6)
        self.assertLess(am[0], 180.0)   # 오전 해는 동쪽

    def test_southern_hemisphere_swaps_solstices(self):
        self.assertEqual(solar.get_season_date("winter", -33.9, 2026), (2026, 6, 21))   # 시드니 동지는 6월
        self.assertEqual(solar.get_season_date("winter", 37.5, 2026), (2026, 12, 22))

    def test_vector_points_to_sun(self):
        x, y, z = solar.get_sun_vector(90.0, 30.0)
        self.assertAlmostEqual(x, 0.866, places=3)
        self.assertAlmostEqual(y, 0.0, places=6)
        self.assertAlmostEqual(z, 0.5, places=6)


def _box(cx, cy, half):
    return [[(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half)]]


class ShadowGridTest(unittest.TestCase):
    def setUp(self):
        # 100 m 평지, 가운데 10×10 m · 높이 10 m 상자
        self.grid = solar.HeightGrid((0.0, 0.0, 100.0, 100.0), 1.0, lambda x, y: 0.0, [(_box(50.0, 50.0, 5.0)[0:1], 10.0)])

    def _at(self, shadow, x, y):
        return shadow[int(y) * self.grid.nx + int(x)]

    def test_south_sun_casts_north(self):
        shadow = self.grid.get_shadow(180.0, 45.0)   # 남쪽 해, 고도 45° → 북쪽으로 10 m
        self.assertTrue(self._at(shadow, 50, 58))
        self.assertFalse(self._at(shadow, 50, 70))
        self.assertFalse(self._at(shadow, 50, 40))
        self.assertFalse(self._at(shadow, 40, 58))

    def test_east_sun_casts_west(self):
        shadow = self.grid.get_shadow(90.0, 26.57)   # tan = 0.5 → 서쪽으로 20 m
        self.assertTrue(self._at(shadow, 30, 50))
        self.assertFalse(self._at(shadow, 25, 50) and self._at(shadow, 20, 50))
        self.assertFalse(self._at(shadow, 60, 50))

    def test_diagonal_shadow_area(self):
        """그림자 면적 = 발자국을 그림자 벡터로 쓸고 간 넓이 − 발자국(10 × 10 m 상자, 길이 10 m) — 대각선 방향도 칸 오차 8 % 안(45°는 브레즌햄 계단으로 6 % 작다)."""
        for azimuth in (135.0, 225.0, 300.0):
            dx, dy = abs(math.sin(math.radians(azimuth))), abs(math.cos(math.radians(azimuth)))
            expected = 10.0 * (10.0 * dx + 10.0 * dy)
            self.assertAlmostEqual(sum(self.grid.get_shadow(azimuth, 45.0)), expected, delta=expected * 0.08, msg=azimuth)

    def test_terrain_slope_shades_lee_side(self):
        """동쪽으로 깎아지른 언덕(서쪽 높음) — 해가 낮은 동쪽이면 언덕 서쪽 기슭이 그늘."""
        ridge = solar.HeightGrid((0.0, 0.0, 100.0, 20.0), 1.0, lambda x, y: max(0.0, 30.0 - abs(x - 50.0) * 2.0), [])
        shadow = ridge.get_shadow(90.0, 10.0)
        self.assertTrue(shadow[10 * ridge.nx + 40])    # 등성이 서쪽
        self.assertFalse(shadow[10 * ridge.nx + 60])   # 해 쪽 비탈

    def test_missing_ground_filled_from_neighbors(self):
        grid = solar.HeightGrid((0.0, 0.0, 10.0, 4.0), 1.0, lambda x, y: None if x > 6 else 5.0, [])
        self.assertTrue(all(v == 5.0 for v in grid.ground))

    def test_counts_and_hours(self):
        sun = solar.get_season_sun("winter", SEOUL[0], SEOUL[1], 2026)
        counts, positions = solar.get_shadow_counts(self.grid, SEOUL[0], sun, constants.SUN_SHADOW_HOURS)
        self.assertEqual(len(positions), len(constants.SUN_SHADOW_HOURS))
        self.assertEqual(max(counts), len(constants.SUN_SHADOW_HOURS))   # 상자 바로 북쪽은 종일 그늘
        hours = solar.get_sun_hours(self.grid, SEOUL[0], sun, step_min=30)
        open_hours = hours[5 * self.grid.nx + 50]   # 상자 남쪽 — 막힘 없음
        rise, set_ = sun["daylight"]
        self.assertAlmostEqual(open_hours, min(set_, 960) / 60.0 - max(rise, 480) / 60.0, delta=0.5)
        self.assertLess(hours[57 * self.grid.nx + 50], 1.0)


class ContourTest(unittest.TestCase):
    def test_square_block_ring(self):
        values = [0.0] * 100
        for j in range(3, 7):
            for i in range(3, 7):
                values[j * 10 + i] = 5.0
        rings = solar.get_contour_rings(values, 10, 10, 2.5, 0.0, 0.0, 1.0)
        self.assertEqual(len(rings), 1)
        self.assertAlmostEqual(non_rhino_utils.get_ring_area(rings[0]), 16.0, delta=2.0)   # 칸 4×4 = 16 ㎡(경계 보간 ±)

    def test_hole_gives_two_rings(self):
        values = [5.0] * 100
        values[55] = 0.0
        rings = solar.get_contour_rings(values, 10, 10, 2.5, 0.0, 0.0, 1.0)
        self.assertEqual(len(rings), 2)   # 바깥 테두리 + 구멍 — 짝홀 규칙으로 칠한다

    def test_simplify_keeps_corners(self):
        ring = [(float(x), 0.0) for x in range(11)] + [(10.0, float(y)) for y in range(1, 11)] + [(float(x), 10.0) for x in range(9, -1, -1)] + [(0.0, float(y)) for y in range(9, 0, -1)]
        simple = solar.get_simplified_ring(ring, 0.1)
        self.assertEqual(len(simple), 4)


class HorizonTest(unittest.TestCase):
    def test_building_horizon(self):
        alts = solar.get_building_horizon((0.0, 0.0, 0.0), [(_box(0.0, 20.0, 5.0), 15.0)])
        self.assertAlmostEqual(alts[0], 45.0, delta=1.0)   # 북쪽 15 m 앞 벽, 높이 15 m
        self.assertEqual(alts[180], 0.0)

    def test_terrain_horizon_and_visible_sun(self):
        lat = SEOUL[0]
        wall = lambda x, y: 1000.0 if y < -500.0 else 0.0   # 남쪽 500 m에 높은 벽 → 동지 해가 하루 종일 가려진다
        alts = solar.get_terrain_horizon((0.0, 0.0, 0.0), wall, 2000.0)
        self.assertGreater(alts[180], 60.0)
        sun = solar.get_season_sun("winter", lat, SEOUL[1], 2026)
        self.assertEqual(solar.get_visible_minutes(lat, sun, alts), 0.0)
        self.assertGreater(solar.get_visible_minutes(lat, sun, [0.0] * 360), 9 * 60)


def _payload():
    speeds, directions = {}, {}
    for day in range(1, 11):
        for hour in range(24):
            stamp = "202401%02d%02d" % (day, hour)
            speeds[stamp], directions[stamp] = (0.2, 0.0) if hour == 0 else (4.0, 315.0)   # 1월: 정온 1/24, 나머지 북서 3.4~5.5
            stamp = "202407%02d%02d" % (day, hour)
            speeds[stamp], directions[stamp] = 2.0, 225.0                                   # 7월: 남서
    return {"header": {"fill_value": -999.0, "sources": ["MERRA2"], "api": {"version": "v2.10.4"}}, "geometry": {"coordinates": [127.0, 37.5, 50.0]},
            "properties": {"parameter": {"WS10M": speeds, "WD10M": directions}}}


class WindTest(unittest.TestCase):
    def test_table_and_rose(self):
        params = _payload()["properties"]["parameter"]
        table = solar.get_wind_table(params["WS10M"], params["WD10M"])
        winter = solar.get_wind_rose(table, (12, 1, 2))
        self.assertEqual(sheet_svg.WIND_NAMES[winter["top"]], "NW")
        self.assertAlmostEqual(winter["calm"], 100.0 / 24, places=3)
        self.assertAlmostEqual(winter["freq"][14][2], 100.0 * 23 / 24, places=3)   # 3.4~5.5 m/s 등급
        summer = solar.get_wind_rose(table, (6, 7, 8))
        self.assertEqual(summer["top"], 10)   # SW
        self.assertAlmostEqual(summer["mean"], 2.0)
        year = solar.get_wind_rose(table, tuple(range(1, 13)))
        self.assertEqual(year["total"], 480)

    def test_records_cached(self):
        calls = []

        def fetch(url):
            calls.append(url)
            return _payload()
        with tempfile.TemporaryDirectory() as tmp:
            first = solar.get_wind_records(37.5, 127.0, cache_dir=tmp, fetch=fetch)
            second = solar.get_wind_records(37.5, 127.0, cache_dir=tmp, fetch=fetch)
        self.assertEqual(len(calls), 1)
        self.assertIn("WS10M,WD10M", calls[0])
        self.assertEqual(first["months"], second["months"])
        self.assertEqual(first["api"], "v2.10.4")

    def test_southern_seasons(self):
        self.assertEqual(solar.get_wind_seasons(-33.9)[1], ("가을", (3, 4, 5)))


def _building(building_id, cx, cy, height):
    ring = [[cx - 6, cy - 6], [cx + 6, cy - 6], [cx + 6, cy + 6], [cx - 6, cy + 6], [cx - 6, cy - 6]]
    return SimpleNamespace(building_id=building_id, geometry={"type": "Polygon", "coordinates": [ring]}, height_m=height,
                           min_x=cx - 6, max_x=cx + 6, min_y=cy - 6, max_y=cy + 6)


class SheetTest(unittest.TestCase):
    def setUp(self):
        for patcher in (patch.object(sheet_svg, "_get_far_height", lambda data, lat, lng: None),   # 먼 산 지형 타일을 받지 않는다
                        patch.object(constants, "SUN_GRID_MAX_CELLS", 20000)):                   # 시험은 거친 격자로
            patcher.start()
            self.addCleanup(patcher.stop)
        cx, cy = 198000.0, 552000.0   # 서울 도심(EPSG:5186)
        half = 150.0
        ring = [(cx - half, cy - half), (cx + half, cy - half), (cx + half, cy + half), (cx - half, cy + half), (cx - half, cy - half)]
        tris = []
        for i in range(-10, 10):
            for j in range(-10, 10):
                x, y = cx + i * 30.0, cy + j * 30.0
                z = lambda px, py: 20.0 + (py - cy) * 0.05
                tris.append(((x, y, z(x, y)), (x + 30, y, z(x + 30, y)), (x, y + 30, z(x, y + 30)), "terrain"))
                tris.append(((x + 30, y, z(x + 30, y)), (x + 30, y + 30, z(x + 30, y + 30)), (x, y + 30, z(x, y + 30)), "terrain"))
        buildings = [_building(n, cx + dx, cy + dy, h) for n, (dx, dy, h) in enumerate([(0, 40, 30), (-60, -50, 12), (70, -20, 45), (20, -90, 8)])]
        self.data = sheet_svg.SheetData(center=(cx, cy), extent_ring=ring, buildings=buildings, terrain_tris=tris, scales=[3000],
                                        site_rings=[[(cx - 20, cy - 20), (cx + 20, cy - 20), (cx + 20, cy + 20), (cx - 20, cy + 20)]],
                                        options={"radius": 150, "shape": "rect", "today_year": 2026}, lot_name="시험")

    def test_shadow_and_sun_hours_sheets(self):
        for key in ("shadow", "sun_hours", "sun_path"):
            svg, empty, reason = sheet_svg.render_sheet(constants.SHEET_IDS[key], self.data)
            self.assertFalse(empty, key)
            root = ET.fromstring(svg)
            ids = [g.get("id") for g in root.iter(SVG + "g")]
            self.assertIn("info", ids)
            self.assertIn(constants.SUN_METHOD_LINE[:10], svg)   # 자료기준 아래 방법 줄
        svg, _empty, _reason = sheet_svg.render_sheet(constants.SHEET_IDS["shadow"], self.data)
        self.assertIn('id="panel_winter"', svg)
        self.assertIn('id="sun_table"', svg)
        self.assertTrue(self.data.cache[("sun_shadow", "winter")]["counts"])

    def test_wind_sheet_with_and_without_data(self):
        with patch.object(solar, "get_wind_records", lambda lat, lng: dict(solar.get_wind_table(_payload()["properties"]["parameter"]["WS10M"],
                                                                                              _payload()["properties"]["parameter"]["WD10M"]),
                                                                           start=2016, end=2025, api="v2", grid=[127.0, 37.5])):
            svg, empty, _reason = sheet_svg.render_sheet(constants.SHEET_IDS["wind"], self.data)
        self.assertFalse(empty)
        self.assertIn("NASA POWER", svg)
        self.data.cache.pop("wind")
        with patch.object(solar, "get_wind_records", side_effect=OSError("offline")):
            svg, empty, reason = sheet_svg.render_sheet(constants.SHEET_IDS["wind"], self.data)
        self.assertTrue(empty)
        self.assertEqual(reason, "바람 자료 못 받음")

    def test_thumbnails(self):
        for key in ("shadow", "sun_hours", "sun_path"):
            self.assertTrue(sheet_svg.render_thumbnail(constants.SHEET_IDS[key], self.data).startswith("data:image/png;base64,"))


class SunStateTest(unittest.TestCase):
    def test_state_from_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            x, y = non_rhino_utils.get_tm_from_wgs84(SEOUL[1], SEOUL[0])
            with open(os.path.join(tmp, constants.CONTEXT_META_FILE_NAME), "w", encoding="utf-8") as handle:
                json.dump({"center": [x, y], "crs": "EPSG:5186"}, handle)
            state = context_builder.get_sun_state(tmp, {"season": "winter", "minutes": 720, "seq": 3})
            self.assertEqual((state["month"], state["day"]), (12, 22))
            self.assertAlmostEqual(state["altitude"], 29.0, delta=0.2)
            self.assertTrue(state["korea"])
            self.assertEqual(state["local"][3:], [12, 30])   # 동지 진태양시 정오 = KST 12:30.5(경도 차 +32.1분, 균시차 +1.6분)
            self.assertEqual(state["seq"], 3)
            other = context_builder.get_sun_state(tmp, {"month": 6, "day": 21, "minutes": 9 * 60, "on": False})
            self.assertFalse(other["on"])
            self.assertLess(other["azimuth"], 180.0)
            with self.assertRaises(ValueError):
                context_builder.get_sun_state(tmp, {"month": 2, "day": 30})


if __name__ == "__main__":
    unittest.main()
