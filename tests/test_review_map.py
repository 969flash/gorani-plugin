import io
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
        self.assertIn("/osm/{z}/{x}/{y}.png", config["fallback_url"])   # OSM은 중계로(Referer 없는 웹뷰는 막힌다)
        self.assertIn("TESTKEY/Satellite", config["aerial_url"])   # 위성 배경·항공사진 시트
        self.assertIn("arcgisonline", config["abroad_aerial_url"])   # 해외·VWorld 영상 폴백

    def test_without_vworld_key(self):
        # 개발 PC의 .env를 안 보도록 pnu_loader.HOME_DIR을 빈 임시 폴더로 바꾼다
        # (.env 파서는 pnu_loader.get_local_env_value 하나를 같이 쓴다)
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(os.environ, {}, clear=True), patch.object(
                pnu_loader, "HOME_DIR", Path(temp_dir)
            ):
                config = review_map.get_tile_config()
        self.assertIn("/osm/{z}/{x}/{y}.png", config["url"])
        self.assertEqual(config["url"], config["fallback_url"])
        self.assertIn("arcgisonline", config["aerial_url"])   # 키 없으면 영상은 Esri


class OsmProxyTest(unittest.TestCase):
    def test_rhino_proxy_serves_tile(self):
        # Rhino 중계 서버가 OSM 주소로 앱 User-Agent를 붙여 받고 PNG를 돌려준다(네트워크는 가짜)
        import urllib.request as request_module
        real_urlopen = request_module.urlopen
        seen = []

        def fake_urlopen(request, timeout=None):
            if not isinstance(request, request_module.Request):
                return real_urlopen(request, timeout=timeout)   # 테스트가 중계 서버를 부르는 길
            seen.append((request.full_url, request.get_header("User-agent")))
            response = io.BytesIO(b"PNG")
            response.headers = {}
            return response

        with patch.object(request_module, "urlopen", fake_urlopen):
            url = review_map.get_osm_url().format(z=16, x=55880, y=25360)
            with real_urlopen(url, timeout=5) as response:
                self.assertEqual(response.read(), b"PNG")
                self.assertIn("max-age", response.headers["Cache-Control"])
        self.assertEqual(seen[0][0], "https://tile.openstreetmap.org/16/55880/25360.png")
        self.assertIn("Gorani", seen[0][1])


class ForeignOriginTest(unittest.TestCase):
    def test_korea_map_after_foreign_point(self):
        # 해외 위치를 찍은 뒤에도 서울 지도 필지가 보이고, 해외 원점은 그대로 남는다(2026-10-23 도쿄 → 서울 필지 0)
        fixture = Path(__file__).resolve().parent / "fixtures" / "seongsu_site.db"
        bbox = [127.050, 37.540, 127.060, 37.548]
        before = len(review_map.get_parcels_in_bbox(bbox, database_path=fixture)["geojson"]["features"])
        try:
            non_rhino_utils.set_projection(139.70, 35.66)
            after = len(review_map.get_parcels_in_bbox(bbox, database_path=fixture)["geojson"]["features"])
            self.assertTrue(non_rhino_utils.is_local_projection())
        finally:
            non_rhino_utils.set_projection()
        self.assertGreater(before, 0)
        self.assertEqual(before, after)


class MapInitTest(unittest.TestCase):
    def test_ip_center(self):
        # ipinfo.io의 loc은 "위도,경도" — 지도에는 [lng, lat]로 뒤집어 도시 배율로 연다
        with patch("urllib.request.urlopen", return_value=io.BytesIO(b'{"city": "Paris", "loc": "48.8534,2.3488"}')):
            center = review_map.get_ip_center()
        self.assertEqual(center, [2.3488, 48.8534])
        self.assertEqual(review_map.get_map_init(center)["zoom"], review_map.IP_MAP_ZOOM)

    def test_ip_center_fallback(self):
        # 오프라인·loc 없음(사설 IP)·nan이면 짐작하지 않고 서울시청
        for effect in (OSError("offline"), [io.BytesIO(b'{"bogon": true}')], [io.BytesIO(b'{"loc": "nan,nan"}')]):
            with patch("urllib.request.urlopen", side_effect=effect):
                self.assertIsNone(review_map.get_ip_center())
        self.assertEqual(review_map.get_map_init(None)["center"], review_map.MAP_CENTER)
        self.assertEqual(review_map.get_map_init(None)["zoom"], review_map.MAP_ZOOM)
        self.assertEqual(review_map.get_map_init(None)["korea_cut"], list(review_map.non_rhino_utils.KOREA_JAPAN_CORNER))   # 패널 isAbroad가 같은 모서리를 뺀다


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
