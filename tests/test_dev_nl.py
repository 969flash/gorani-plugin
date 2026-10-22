"""dev_nl — 네트워크·pyogrio 없이: 높이 등급(지붕 − 지반, 50 % → 70 % → 최고 → 기본값), 팩 이름·나라 판정(data_pack·osm_context)."""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import constants  # noqa: E402
import data_pack  # noqa: E402
import dev_nl  # noqa: E402
import osm_context  # noqa: E402


class HeightTest(unittest.TestCase):
    def test_height_fallbacks(self):
        self.assertEqual(dev_nl.get_height(2.0, 13.2, 14.0, 15.0), (11.2, "pdok_height", "B"))
        self.assertEqual(dev_nl.get_height(2.0, None, 14.0, 15.0), (12.0, "pdok_height", "B"))     # 50 % 없으면 70 %
        self.assertEqual(dev_nl.get_height(2.0, 2.5, None, 500.0), (2.5, "pdok_height_rel", "B"))   # 지붕 − 지반 0.5 m → 지붕 값(상대 높이로 봄)
        self.assertEqual(dev_nl.get_height(2.0, 0.5, None, 500.0), (constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"))   # 전부 범위 밖
        self.assertEqual(dev_nl.get_height(None, 13.2, 14.0, 15.0), (13.2, "pdok_height_rel", "B"))   # 지반 없음 → 지붕 값을 높이로
        self.assertEqual(dev_nl.get_height(5.95, 3.51, 4.0, 5.7), (3.51, "pdok_height_rel", "B"))     # AHN6 도엽 — 지붕 < 지반
        self.assertEqual(dev_nl.get_height(0.34, 10.82, 11.0, 12.0), (10.48, "pdok_height", "B"))     # AHN5 도엽 — NAP


class CountryPackTest(unittest.TestCase):
    def test_pack_names_and_country(self):
        self.assertEqual(data_pack.get_pack_country("nl25gn1_context.db"), "nl")
        self.assertEqual(data_pack.get_pack_country("jp13104_context.db"), "jp")
        self.assertEqual(data_pack.get_pack_country("jpn_context.db"), "")      # 한국 시도 슬러그 꼴
        self.assertEqual(data_pack.get_pack_country("nl25GN1_context.db"), "")  # 도엽은 소문자
        self.assertEqual(data_pack.get_pack_country("11110_context.db"), "")
        self.assertEqual(osm_context.get_country(4.8952, 52.3702), "nl")       # 암스테르담
        self.assertEqual(osm_context.get_country(139.7006, 35.6896), "jp")     # 신주쿠
        self.assertEqual(osm_context.get_country(2.2945, 48.8584), "fr")       # 파리
        self.assertEqual(osm_context.get_country(-73.9857, 40.7484), "")       # 뉴욕 — 팩 없음
        self.assertEqual(data_pack.get_pack_country("fr075_context.db"), "fr")
        self.assertEqual(data_pack.get_pack_country("fr02a_context.db"), "fr")
        self.assertEqual(constants.PACK_SOURCE_IDS["pdok"], "nl")


if __name__ == "__main__":
    unittest.main()
