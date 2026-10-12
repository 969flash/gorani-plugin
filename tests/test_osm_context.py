"""osm_context — 네트워크 없이: 투영 전환 왕복, PNG(terrarium) 디코더, 관계 링 잇기, 태그 → 높이·종류, Overpass 응답 → ContextData."""

import os
import struct
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
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
        finally:
            non_rhino_utils.set_projection()


if __name__ == "__main__":
    unittest.main()
