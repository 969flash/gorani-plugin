import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lot_db
import non_rhino_utils
import pnu_loader
import review_map

DATABASE_PATH = Path(__file__).resolve().parents[1] / "data" / "seoul_site.db"

# 서울시청 (WGS84 → EPSG:5186 검증값은 docs/panel_ui.md)
CITY_HALL_LNG_LAT = (126.9784, 37.5665)
CITY_HALL_TM = (198091.71, 551885.02)


class CoordinateConversionTest(unittest.TestCase):
    def test_round_trip_seoul(self):
        # 서울 3점 왕복 — 오차 1e-9도 미만
        for lng, lat in [CITY_HALL_LNG_LAT, (127.05, 37.65), (126.90, 37.48)]:
            x, y = non_rhino_utils.get_tm_from_wgs84(lng, lat)
            lng_back, lat_back = non_rhino_utils.get_wgs84_from_tm(x, y)
            self.assertLess(abs(lng_back - lng), 1e-9)
            self.assertLess(abs(lat_back - lat), 1e-9)

    def test_city_hall_reference(self):
        x, y = non_rhino_utils.get_tm_from_wgs84(*CITY_HALL_LNG_LAT)
        self.assertLess(abs(x - CITY_HALL_TM[0]), 0.5)
        self.assertLess(abs(y - CITY_HALL_TM[1]), 0.5)


class TileConfigTest(unittest.TestCase):
    def test_with_vworld_key(self):
        with patch.dict(os.environ, {"VWORLD_API_KEY": "TESTKEY"}):
            config = review_map.get_tile_config()
        self.assertIn("api.vworld.kr", config["url"])
        self.assertIn("TESTKEY", config["url"])
        self.assertIn("openstreetmap", config["fallback_url"])

    def test_without_vworld_key(self):
        # 개발 PC의 .env를 안 보도록 pnu_loader.ROOT_DIR을 빈 임시 폴더로 바꾼다
        # (.env 파서는 pnu_loader.get_local_env_value 하나를 같이 쓴다)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {}, clear=True), patch.object(
                pnu_loader, "ROOT_DIR", Path(temp_dir)
            ):
                config = review_map.get_tile_config()
        self.assertIn("openstreetmap", config["url"])
        self.assertEqual(config["url"], config["fallback_url"])


class GeojsonConversionTest(unittest.TestCase):
    def test_parcels_in_bbox_conversion(self):
        x, y = non_rhino_utils.get_tm_from_wgs84(*CITY_HALL_LNG_LAT)
        fake_lot = SimpleNamespace(
            pnu="1114010300100310000",
            address="서울특별시 중구 태평로1가 31",
            land_category="대",
            area=100.0,
            geometry={
                "type": "Polygon",
                "coordinates": [[[x, y], [x + 10, y], [x + 10, y + 10], [x, y]]],
            },
        )
        with patch.object(
            lot_db, "load_parcels_in_bounds", return_value=([fake_lot], False)
        ):
            result = review_map.get_parcels_in_bbox([126.97, 37.56, 126.99, 37.57])

        self.assertFalse(result["truncated"])
        feature = result["geojson"]["features"][0]
        self.assertEqual(feature["geometry"]["type"], "Polygon")
        first_point = feature["geometry"]["coordinates"][0][0]
        # 변환 결과가 원래 WGS84 좌표로 돌아오고 소수 7자리로 반올림돼 있다
        self.assertEqual(first_point, [round(v, 7) for v in first_point])
        self.assertLess(abs(first_point[0] - CITY_HALL_LNG_LAT[0]), 1e-6)
        self.assertLess(abs(first_point[1] - CITY_HALL_LNG_LAT[1]), 1e-6)
        properties = feature["properties"]
        self.assertEqual(properties["pnu"], fake_lot.pnu)
        self.assertEqual(properties["jibun"], "태평로1가 31")
        self.assertEqual(properties["land_category"], "대")
        self.assertEqual(properties["area"], 100.0)


class LoadParcelsInBoundsTest(unittest.TestCase):
    def test_city_hall_bbox(self):
        if not DATABASE_PATH.exists():
            self.skipTest("로컬 DB가 없습니다: %s" % DATABASE_PATH)
        x, y = non_rhino_utils.get_tm_from_wgs84(*CITY_HALL_LNG_LAT)
        lots, truncated = lot_db.load_parcels_in_bounds(
            x - 100, y - 100, x + 100, y + 100, limit=5, database_path=DATABASE_PATH
        )
        self.assertEqual(len(lots), 5)
        self.assertTrue(truncated)
        self.assertIsInstance(lots[0], lot_db.LotInfo)


if __name__ == "__main__":
    unittest.main()
