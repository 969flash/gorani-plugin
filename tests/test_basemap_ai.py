import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import basemap_ai
import sheet_svg
import constants
import context_builder

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


class HelperTest(unittest.TestCase):
    def test_clipped_lines(self):
        box = (0.0, 0.0, 10.0, 10.0)
        pieces = basemap_ai.get_clipped_lines([(-5.0, 5.0), (5.0, 5.0), (15.0, 5.0)], box)
        self.assertEqual(pieces, [[(0.0, 5.0), (5.0, 5.0), (10.0, 5.0)]])
        self.assertEqual(basemap_ai.get_clipped_lines([(20.0, 0.0), (30.0, 5.0)], box), [])

    def test_centroid_and_band(self):
        self.assertEqual(basemap_ai.get_ring_centroid([(0.0, 0.0), (4.0, 0.0), (4.0, 2.0), (0.0, 2.0)]), (2.0, 1.0))
        self.assertEqual([basemap_ai.get_building_band(n) for n in (0, 4, 5, 10, 20)],
                         ["07_bldg_low", "07_bldg_low", "07_bldg_mid", "07_bldg_high", "07_bldg_tower"])

    def test_layers_per_scale(self):
        self.assertNotIn("08b_parcel_no", basemap_ai.get_basemap_layers({}, 3000))
        self.assertIn("08b_parcel_no", basemap_ai.get_basemap_layers({}, 1000))
        self.assertNotIn("08_parcel", basemap_ai.get_basemap_layers({}, 5000))
        self.assertNotIn("02b_landuse", basemap_ai.get_basemap_layers({}, 3000))
        self.assertIn("02b_landuse", basemap_ai.get_basemap_layers({"basemap_layers_on": ["02b_landuse"]}, 3000))

    def test_korean_string_is_cp949_octal(self):
        # 한글은 CP949 8진 이스케이프 — Illustrator 2026에서 KSCms-UHC-H 글꼴로 정상 표시(2026-10-08 실측)
        self.assertEqual(basemap_ai._ps_string("성수(2)"), "(\\274\\272\\274\\366\\(2\\))")


class StylePaintTest(unittest.TestCase):
    def test_cmyk_and_layer_paint(self):
        self.assertEqual(basemap_ai.get_cmyk(None), (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(basemap_ai.get_cmyk(40), (0.0, 0.0, 0.0, 0.4))
        c, m, y, k = basemap_ai.get_cmyk("#808080")   # 회색은 K만
        self.assertEqual((c, m, y), (0.0, 0.0, 0.0))
        self.assertAlmostEqual(k, 1 - 128 / 255.0)
        self.assertEqual(basemap_ai.get_cmyk("#FF0000"), (0.0, 1.0, 1.0, 0.0))
        style = sheet_svg.get_style({"style": {"preset": "std", "water": "#112233"}})
        self.assertEqual(basemap_ai.get_layer_paint("01_water", style), ("#112233", None))
        self.assertEqual(basemap_ai.get_layer_paint("00_frame_scale", style)[0], style["block"])   # 가구 칠 위에 흰 도로면
        self.assertEqual(basemap_ai.get_layer_paint("09_contour", style), (None, 35))             # 스타일 밖 레이어는 K톤


@unittest.skipUnless((FIXTURE_DIR / "seongsu_context.db").exists(), "tests/fixtures/seongsu_context.db가 없다 (python3 scripts/dev_make_fixture.py)")
class WriteTest(unittest.TestCase):
    def test_fixture_basemap(self):
        request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": str(FIXTURE_DIR / "seongsu_site.db"),
                   "context_db": str(FIXTURE_DIR / "seongsu_context.db"), "options": {"radius": 500, "scales": [3000], "paper": "A1", "paper_mm": [841, 594]}}
        prepared = context_builder.prepare(request)
        with tempfile.TemporaryDirectory() as tmp:
            result = basemap_ai.write_basemap(prepared, 3000, tmp)
            with open(result["path"], "rb") as handle:
                raw = handle.read()
        text = raw.decode("ascii").replace("\r\n", "\n")   # ASCII뿐이어야 한다(한글은 이스케이프)
        self.assertIn(b"\r\n", raw)                      # 레거시 .ai는 CRLF
        self.assertIn("%%BoundingBox: 0 0 2384 1684", text)
        self.assertIn("%AI5_ArtSize: 2384 1684", text)
        layers = re.findall(r"^\((\d\d[a-z_0-9]+)[^\n]*\) Ln$", text, re.M)
        self.assertEqual(layers, [name for name, *_ in constants.BM_LAYERS if name in layers])   # 파일 뒤쪽이 Illustrator 위
        self.assertEqual(text.count("%AI5_BeginLayer"), result["layers"])
        self.assertGreater(result["counts"]["07_bldg_low"], 1000)
        self.assertNotIn("08b_parcel_no", result["counts"])   # 1:3000에는 지번 없음
        # 모든 좌표가 용지 안(프레임으로 잘랐다)
        coords = [tuple(map(float, m)) for m in re.findall(r"^(-?\d+\.\d+) (-?\d+\.\d+) [mL]$", text, re.M)]
        self.assertTrue(coords)
        self.assertTrue(all(-0.5 <= x <= 2384.5 and -0.5 <= y <= 1684.5 for x, y in coords))
        # 3dm 2D 레이어용 기록기 — .ai와 같은 도형을 받는다
        recorder = basemap_ai.build_ai(prepared, 3000, basemap_ai.ShapeRecorder())
        self.assertEqual(set(recorder.counts), set(result["counts"]))   # .ai는 종이에서 0.05 mm보다 작은 도형을 버려 수가 조금 적다
        self.assertTrue(all(recorder.counts[k] >= v for k, v in result["counts"].items()))
        self.assertEqual({kind for _layer, kind, _data in recorder.shapes}, {"polygon", "line", "text"})


if __name__ == "__main__":
    unittest.main()
