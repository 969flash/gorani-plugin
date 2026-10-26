"""dev_ch — 네트워크·GDAL 없이: 높이 등급(GESAMTHOEHE → DACH_MAX − 지반 → 기본값), Floor 삼각형 → 바닥 외곽, 팩 이름·나라 판정."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import constants  # noqa: E402
import data_pack  # noqa: E402
import dev_ch  # noqa: E402
import osm_context  # noqa: E402


class HeightTest(unittest.TestCase):
    def test_height_fallbacks(self):
        self.assertEqual(dev_ch.get_height({"total_height": 12.3, "roof_max": 560.0, "ground": 550.0}), (12.3, "swisstopo_height", "B"))
        self.assertEqual(dev_ch.get_height({"total_height": None, "roof_max": 560.5, "ground": 550.0}), (10.5, "swisstopo_roof", "B"))
        self.assertEqual(dev_ch.get_height({"total_height": None, "roof_max": None, "ground": 550.0}), (constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"))
        self.assertEqual(dev_ch.get_height({"total_height": 0.2, "roof_max": 550.3, "ground": 550.0}), (constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"))


class FootprintTest(unittest.TestCase):
    def test_triangles_to_outline(self):
        """LV95 m 정사각형 10 m를 삼각형 둘로 → 외곽 하나(닫힘 점 포함 5점), 경위도, 면적 ≈ 100 ㎡."""
        import pyproj
        tr = pyproj.Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
        a, b, c, d = (2690000.0, 1190000.0), (2690010.0, 1190000.0), (2690010.0, 1190010.0), (2690000.0, 1190010.0)
        geometry = dev_ch.get_footprint([[a, b, c, a], [a, c, d, a]], tr)
        self.assertEqual(geometry["type"], "Polygon")
        self.assertEqual(len(geometry["coordinates"][0]), 5)
        import dev_plateau
        self.assertAlmostEqual(dev_plateau.get_ring_area(geometry["coordinates"][0]), 100.0, delta=1.0)
        self.assertIsNone(dev_ch.get_footprint([], tr))


class CountryTest(unittest.TestCase):
    def test_pack_names_and_country(self):
        self.assertEqual(data_pack.get_pack_country("ch1172_context.db"), "ch")
        self.assertEqual(osm_context.get_country(8.6416, 46.8807), "ch")   # 알트도르프
        self.assertEqual(osm_context.get_country(9.5215, 47.1410), "ch")   # 파두츠(리히텐슈타인)
        self.assertEqual(data_pack.get_pack_source_ids()["swisstopo"], "ch")


if __name__ == "__main__":
    unittest.main()
