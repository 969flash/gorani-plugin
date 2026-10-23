"""dev_us — Overture 미국 건물 팩 빌더의 순수 함수(높이 등급·용도·윤곽·행)와 나라 상자. S3·DuckDB 없이 돈다."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import constants  # noqa: E402
import dev_us  # noqa: E402


class DevUsTest(unittest.TestCase):
    def test_height_fallbacks(self):
        self.assertEqual(dev_us.get_height(12.3, 3), (12.3, "overture_height", "B"))
        self.assertEqual(dev_us.get_height(0.001, 3), (round(1.5 + 2.8 * 3, 2), "overture_levels", "C"))   # 콜로라도 최소 height 0.001 m — 범위 밖
        self.assertEqual(dev_us.get_height(None, None), (constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"))
        self.assertEqual(dev_us.get_height(900.0, 0), (constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"))

    def test_use(self):
        self.assertEqual(dev_us.get_use("residential", "house"), "01000")
        self.assertEqual(dev_us.get_use("residential", "apartments"), "02000")   # class 우선
        self.assertEqual(dev_us.get_use("commercial", "hotel"), "15000")
        self.assertEqual(dev_us.get_use("commercial", None), "04000")
        self.assertEqual(dev_us.get_use("outbuilding", "shed"), "")
        self.assertEqual(dev_us.get_use(None, None), "")

    def test_row(self):
        geojson = json.dumps({"type": "Polygon", "coordinates": [[[-118.25, 34.05], [-118.2499, 34.05], [-118.2499, 34.0501], [-118.25, 34.0501], [-118.25, 34.05]]]})
        record = ("08b2c0a1d9f1", geojson, -118.24995, 34.05005, "residential", "apartments", 25.4, 8, 1, "Some Tower", "Microsoft ML Buildings", False)
        row = dev_us.get_row(record, 6037 * 10 ** 7 + 1)
        self.assertEqual(len(row), 27)
        self.assertEqual(row[1], "overture:08b2c0a1d9f1")
        self.assertEqual((row[3], row[5], row[6], row[7]), ("02000", 8, 1, "overture"))
        self.assertEqual((row[8], row[9], row[10], row[11]), (25.4, "overture_height", "B", "msft"))
        self.assertEqual((row[14], row[15], row[16], row[21]), ("Some Tower", "residential", "apartments", "overture"))
        self.assertGreater(row[17], 50)   # 약 9 m × 11 m
        self.assertEqual((row[23], row[24], row[25], row[26]), (-118.25, -118.2499, 34.05, 34.0501))
        self.assertIsNone(dev_us.get_row(record[:-1] + (True,), 1))   # 지하
        self.assertIsNone(dev_us.get_row(("x", json.dumps({"type": "Point", "coordinates": [0, 0]})) + record[2:], 1))

    def test_bounds_and_country(self):
        """미국 상자 넷은 캐나다·멕시코 도시를 피하고 미국 도시는 담는다(countries.json에 넣기 전 확인)."""
        def inside(lng, lat):
            return any(w <= lng <= e and s <= lat <= n for w, s, e, n in constants.US_BOUNDS)
        for lng, lat in ((-118.2437, 34.0522), (-74.006, 40.7128), (-149.9003, 61.2181), (-157.8583, 21.3069), (-66.1057, 18.4655)):   # LA·뉴욕·앵커리지·호놀룰루·산후안
            self.assertTrue(inside(lng, lat), (lng, lat))
        for lng, lat in ((-99.1332, 19.4326), (-123.1207, 49.2827), (-79.3832, 43.6532), (-71.2080, 46.8139)):   # 멕시코시티·밴쿠버·토론토·퀘벡
            self.assertFalse(inside(lng, lat) and (lat < 24.3 or lat > 49.5), (lng, lat))   # 본토 상자 남북 밖 — 토론토는 상자 안(미국 북동부와 같은 위도)
        self.assertEqual(len(constants.US_BOUNDS), 4)


if __name__ == "__main__":
    unittest.main()
