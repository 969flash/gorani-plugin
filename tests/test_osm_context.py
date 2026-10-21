"""osm_context — 네트워크 없이: 투영 전환 왕복, PNG(terrarium) 디코더, 관계 링 잇기, 태그 → 높이·종류, Overpass 응답 → ContextData,
일본(지리원 표고 화소, PLATEAU 팩 읽기·중복 거르기, OSM 메우기, 일본 판정)."""

import json
import os
import sqlite3
import struct
import sys
import tempfile
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import constants  # noqa: E402
import dev_plateau  # noqa: E402
import non_rhino_utils  # noqa: E402
import osm_context  # noqa: E402


def _png(width, height, rows, filter_type=1):
    """8비트 RGB PNG bytes. rows = [[(r, g, b), ...], ...]. filter_type 1(Sub)로 인코딩해 디코더의 필터 복원까지 본다."""
    raw = b""
    for row in rows:
        line = bytes(v for pixel in row for v in pixel)
        if filter_type == 1:
            line = bytes((line[i] - (line[i - 3] if i >= 3 else 0)) & 255 for i in range(len(line)))
        raw += bytes([filter_type]) + line
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


class ProjectionTest(unittest.TestCase):
    def tearDown(self):
        non_rhino_utils.set_projection()

    def test_local_and_korea(self):
        non_rhino_utils.set_projection(-122.42, 37.79)
        self.assertTrue(non_rhino_utils.is_local_projection())
        x, y = non_rhino_utils.get_tm_from_wgs84(-122.4194, 37.7929)
        self.assertLess(abs(x), 1000)
        lng, lat = non_rhino_utils.get_wgs84_from_tm(x, y)
        self.assertAlmostEqual(lng, -122.4194, places=9)
        self.assertAlmostEqual(lat, 37.7929, places=9)
        non_rhino_utils.set_projection(127.05, 37.54)   # 한국 안이면 EPSG:5186
        self.assertFalse(non_rhino_utils.is_local_projection())
        self.assertEqual(non_rhino_utils.get_crs_label(), "EPSG:5186")


class ParseTest(unittest.TestCase):
    def test_png_terrarium(self):
        rows = [[(128, 0, 0), (128, 10, 128)], [(127, 255, 0), (130, 1, 0)]]
        width, height, channels, decoded = osm_context.decode_png(_png(2, 2, rows))
        self.assertEqual((width, height, channels), (2, 2, 3))
        r, g, b = decoded[0][3:6]
        self.assertAlmostEqual(r * 256 + g + b / 256 - 32768, 10.5)

    def test_ring_stitch(self):
        ways = [[(0, 0), (10, 0)], [(10, 10), (10, 0)], [(10, 10), (0, 10), (0, 0)]]   # 방향이 뒤집힌 조각 포함
        rings = osm_context._get_rings_from_ways(ways)
        self.assertEqual(len(rings), 1)
        self.assertEqual(rings[0][0], rings[0][-1])
        self.assertEqual(len(rings[0]), 5)

    def test_tags(self):
        self.assertEqual(osm_context.get_building_height({"height": "24 m"})[2:], ("osm_height", "B"))
        self.assertEqual(osm_context.get_building_height({"building:levels": "5"})[1:], (5, "osm_levels", "C"))
        self.assertEqual(osm_context.get_building_height({})[2:], ("default", "D"))
        self.assertEqual(osm_context.get_road_width({"highway": "residential", "lanes": "2"}), 6.6)
        self.assertEqual(osm_context.get_feature_kind({"natural": "water"}, True), ("water", "river"))
        self.assertEqual(osm_context.get_feature_kind({"highway": "primary"}, False), ("road", "centerline"))
        self.assertIsNone(osm_context.get_feature_kind({"amenity": "bench"}, False))
        self.assertEqual(osm_context.get_feature_kind({"amenity": "school"}, True), ("public", "school_lot"))
        self.assertEqual(osm_context.get_feature_kind({"place": "square"}, True), ("public", "plaza"))
        self.assertIsNone(osm_context.get_feature_kind({"amenity": "hospital"}, True))   # 병원 면은 그리지 않고 안 건물의 용도로만
        self.assertEqual(osm_context.get_building_use({"building": "yes", "amenity": "library"}), "10000")
        for value in constants.OSM_PUBLIC_USE:   # Overpass가 시설 면을 받아 와야 용도를 줄 수 있다
            self.assertIn(value, constants.OSM_OVERPASS_QUERY)

    def test_elements_to_context(self):
        non_rhino_utils.set_projection(2.29, 48.86)
        try:
            square = [{"lat": 48.8600, "lon": 2.2900}, {"lat": 48.8600, "lon": 2.2902}, {"lat": 48.8602, "lon": 2.2902},
                      {"lat": 48.8602, "lon": 2.2900}, {"lat": 48.8600, "lon": 2.2900}]
            elements = [
                {"type": "way", "id": 1, "tags": {"building": "apartments", "building:levels": "6"}, "geometry": square},
                {"type": "way", "id": 2, "tags": {"highway": "secondary"}, "geometry": square[:2]},
                {"type": "way", "id": 3, "tags": {"leisure": "park"}, "geometry": square},
            ]
            buildings = osm_context._get_buildings(elements, "2026-10-13")
            features = osm_context._get_features(elements, "2026-10-13")
            self.assertEqual(len(buildings), 1)
            self.assertEqual(buildings[0].usability, "02000")
            self.assertGreater(buildings[0].footprint_area, 300)   # 약 14.7 m × 22.2 m
            self.assertEqual(sorted((f.theme, f.kind) for f in features), [("green", "park"), ("road", "centerline")])
            # 역 점 · 학교 부지 면 · 병원 면 안 building=yes → 공공시설·역세권 도면
            far = [{"lat": p["lat"] + 0.001, "lon": p["lon"]} for p in square]
            elements += [
                {"type": "node", "id": 4, "lat": 48.8601, "lon": 2.2901, "tags": {"railway": "station", "name": "Gare"}},
                {"type": "node", "id": 5, "lat": 48.8601, "lon": 2.2901, "tags": {"railway": "station"}},   # 이름 없는 역은 뺀다
                {"type": "way", "id": 6, "tags": {"amenity": "school"}, "geometry": square},
                {"type": "way", "id": 7, "tags": {"amenity": "hospital"}, "geometry": far},
                {"type": "way", "id": 8, "tags": {"building": "yes"}, "geometry": far},
            ]
            features = osm_context._get_features(elements, "2026-10-13")
            stations = [f for f in features if f.theme == "transit"]
            self.assertEqual([(f.kind, f.name, f.geometry["type"]) for f in stations], [("station", "Gare", "Point")])
            self.assertIn(("public", "school_lot"), [(f.theme, f.kind) for f in features])
            buildings = osm_context._get_buildings(elements, "2026-10-13")
            self.assertEqual(osm_context._apply_public_use(buildings, elements), 1)
            self.assertEqual([b.usability for b in buildings], ["02000", "09000"])   # 아파트는 그대로, 병원 면 안 건물만
        finally:
            non_rhino_utils.set_projection()


def _write_jp_pack(data_dir, code, buildings, year):
    """dev_plateau 행 함수로 일본 건물 팩 하나를 만들고 packs.json에 경위도 범위를 적는다. buildings = [(gml:id, [(경도, 위도)…], 용도)]."""
    name = "jp%s_context.db" % code
    connection = sqlite3.connect(os.path.join(data_dir, name))
    connection.executescript(dev_plateau.SCHEMA_SQL)
    for n, (gml_id, ring, usage) in enumerate(buildings, start=1):
        row = dev_plateau.get_row({"id": gml_id, "polygons": [[dev_plateau.get_clean_ring(ring)]], "measuredHeight": "10", "usage": usage},
                                  int(code) * 10 ** 7 + n)
        connection.execute("INSERT INTO buildings VALUES (%s)" % ",".join("?" * len(row)), row)
    connection.execute("INSERT INTO data_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       ("plateau", "3D都市モデル（Project PLATEAU）市%s（%d年度）" % (code, year), "https://www.geospatial.jp/ckan/dataset/plateau-%s-x-%d" % (code, year),
                        "%d-03-31" % (year + 1), "2026-10-21T00:00:00", "", dev_plateau.LICENSE, ""))
    connection.commit()
    connection.close()
    state_path = os.path.join(data_dir, "packs.json")
    state = {}
    if os.path.exists(state_path):
        with open(state_path) as f:
            state = json.load(f)
    state[name] = {"sha256": "x", "bounds": [139.0, 35.0, 140.0, 36.0]}
    with open(state_path, "w") as f:
        json.dump(state, f)


def _square(lng, lat, size=0.0002):
    return [(lng, lat), (lng + size, lat), (lng + size, lat + size), (lng, lat + size), (lng, lat)]


class JapanTest(unittest.TestCase):
    def setUp(self):
        non_rhino_utils.set_projection(139.70, 35.69)

    def tearDown(self):
        non_rhino_utils.set_projection()

    def test_is_japan(self):
        self.assertTrue(osm_context.is_japan(139.70, 35.69))    # 신주쿠
        self.assertTrue(osm_context.is_japan(130.40, 33.59))    # 후쿠오카 — 한국 판정 상자 안
        self.assertFalse(osm_context.is_japan(129.07, 35.18))   # 부산
        self.assertFalse(osm_context.is_japan(126.98, 37.57))   # 서울
        self.assertFalse(osm_context.is_japan(2.35, 48.86))     # 파리

    def test_gsi_elevation(self):
        self.assertAlmostEqual(osm_context.get_elevation("gsi_dem", 0, 39, 16), 100.0)   # 10000 × 0.01 m
        self.assertIsNone(osm_context.get_elevation("gsi_dem", 128, 0, 0))               # 값 없음(수면)
        self.assertAlmostEqual(osm_context.get_elevation("gsi_dem", 255, 254, 12), -5.0)   # 2²⁴ − 500 → −5 m
        self.assertAlmostEqual(osm_context.get_elevation("aws_terrain", 128, 10, 128), 10.5)

    def test_plateau_packs(self):
        with tempfile.TemporaryDirectory() as data_dir:
            # 새 연도 팩(13104)과 옛 연도 팩(13113)이 같은 건물 하나(gml:id 같음)와 같은 자리 건물 하나(gml:id 다름)를 함께 담았다
            _write_jp_pack(data_dir, "13104", [("a", _square(139.700, 35.690), "412"), ("b", _square(139.701, 35.690), "401")], 2025)
            _write_jp_pack(data_dir, "13113", [("a", _square(139.700, 35.690), "412"), ("c", _square(139.70101, 35.69001, 0.00018), "461"),
                                               ("d", _square(139.703, 35.690), "411")], 2023)
            open(os.path.join(data_dir, "seoul_context.db"), "w").close()   # 한국 개발 DB는 일본 조회에 섞이지 않는다
            buildings, sources = osm_context.load_plateau_buildings((139.69, 35.68, 139.71, 35.70), data_dir)
            self.assertEqual(sorted(b.src_key for b in buildings), ["plateau:a", "plateau:b", "plateau:d"])
            by_key = {b.src_key: b for b in buildings}
            self.assertEqual((by_key["plateau:a"].usability, by_key["plateau:b"].usability), ("02000", "14000"))
            self.assertEqual(by_key["plateau:a"].reference_date, "2026-03-31")   # 새 연도 팩 것을 남긴다
            x, y = by_key["plateau:a"].geometry["coordinates"][0][0]
            self.assertLess(abs(x), 100)   # 지금 투영(신주쿠 원점) m
            self.assertGreater(by_key["plateau:a"].footprint_area, 300)
            self.assertEqual([s.source_id for s in sources], ["plateau"])
            self.assertIn("市13104（2025年度）・市13113（2023年度）", sources[0].name)
            self.assertEqual(sources[0].reference_date, "2024-03-31")   # 기준일은 가장 오래된 도시
            self.assertEqual(osm_context.load_plateau_buildings((130.0, 33.0, 130.1, 33.1), os.path.join(data_dir, "none")), ([], []))

    def test_overpass_down_keeps_plateau(self):
        """Overpass가 모두 막혀도 일본 팩이 있으면 PLATEAU 건물로 만든다(출처에 osm 없음). 팩이 없으면 그대로 실패."""
        def down(bounds):
            raise RuntimeError("Overpass down")
        saved = osm_context.get_overpass_elements, osm_context.get_terrain_spots, osm_context.data_pack.get_data_dir
        with tempfile.TemporaryDirectory() as data_dir:
            _write_jp_pack(data_dir, "13104", [("a", _square(139.700, 35.690), "412")], 2025)
            osm_context.get_overpass_elements, osm_context.get_terrain_spots = down, lambda bounds, today: ([], set())
            osm_context.data_pack.get_data_dir = lambda: data_dir
            try:
                x, y = non_rhino_utils.get_tm_from_wgs84(139.7001, 35.6901)
                context = osm_context.load((x - 50, y - 50, x + 50, y + 50), "2026-10-21")
                self.assertEqual([b.src_key for b in context.buildings], ["plateau:a"])
                self.assertEqual([s.source_id for s in context.sources], ["plateau"])
                x, y = non_rhino_utils.get_tm_from_wgs84(139.80, 35.60)   # 팩 범위 밖(packs.json 범위는 넓지만 건물 없음)
                with self.assertRaises(RuntimeError):
                    osm_context.load((x - 50, y - 50, x + 50, y + 50), "2026-10-21")
            finally:
                osm_context.get_overpass_elements, osm_context.get_terrain_spots, osm_context.data_pack.get_data_dir = saved

    def test_osm_fills_gaps(self):
        def building(ring, key):
            geometry = {"type": "Polygon", "coordinates": [[list(non_rhino_utils.get_tm_from_wgs84(*p)) for p in ring]]}
            min_x, max_x, min_y, max_y = osm_context._get_bounds(geometry)
            return osm_context.BuildingInfo(1, key, "", "", "", 0, 0, "", 10.0, "", "B", "", "", "active", "", "", "", 0.0, 0.0,
                                            geometry, "osm", "", min_x, max_x, min_y, max_y)
        plateau = [building(_square(139.700, 35.690), "p1"), building(_square(139.7005, 35.690), "p2")]
        osm = [building(_square(139.70001, 35.69001), "same"),                 # 같은 건물(살짝 어긋남)
               building(_square(139.6999, 35.6899, 0.0012), "block"),          # 두 동을 한 외곽으로 그린 OSM — PLATEAU 중심점을 품는다
               building(_square(139.705, 35.690), "new")]                      # PLATEAU에 없는 건물
        self.assertEqual([b.src_key for b in osm_context.get_buildings_apart(osm, plateau)], ["new"])
        self.assertEqual(len(osm_context.get_buildings_apart(osm, [])), 3)


if __name__ == "__main__":
    unittest.main()
