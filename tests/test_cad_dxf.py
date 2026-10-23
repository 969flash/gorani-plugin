"""AutoCAD판 2D 현황도 DXF(cad_dxf) — 순수 도우미 + fixture DB로 파일 구조·단위·좌표·엔진 경로를 확인한다."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import cad_dxf
import constants
import context_builder

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
HAS_FIXTURES = os.path.exists(SITE_DB) and os.path.exists(CONTEXT_DB)


def _request(**options):
    return {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
            "options": dict({"radius": 500, "shape": "circle", "scales": [1000]}, **options)}


def _read_pairs(path):
    with open(path, encoding="cp949", newline="") as f:
        lines = f.read().split("\r\n")
    return [(int(code), value) for code, value in zip(lines[0::2], lines[1::2])]


def _entities(pairs):
    """ENTITIES 구간을 [(종류, {코드: [값 …]})]로."""
    start = pairs.index((2, "ENTITIES")) + 1
    out = []
    for code, value in pairs[start:]:
        if code == 0:
            if value == "ENDSEC":
                break
            out.append((value, {}))
        else:
            out[-1][1].setdefault(code, []).append(value)
    return out


class HelperTest(unittest.TestCase):
    def test_cad_pts_shift_and_unit(self):
        self.assertEqual(cad_dxf.get_cad_pts([(204710.0, 549002.5)], (204700.0, 549000.0), 1000.0), [(10000.0, 2500.0)])
        self.assertEqual(cad_dxf.get_cad_pts([(1.0, 2.0)], (0.0, 0.0), 1.0), [(1.0, 2.0)])

    def test_label_spot_is_mid_and_readable(self):
        x, y, angle, length = cad_dxf.get_label_spot([(10.0, 0.0), (0.0, 0.0)])   # 오른쪽 → 왼쪽 선도 글자는 바로 선다
        self.assertEqual((x, y, angle, length), (5.0, 0.0, 0.0, 10.0))
        self.assertAlmostEqual(cad_dxf.get_label_spot([(0.0, 10.0), (0.0, 0.0)])[2], 90.0)
        self.assertEqual(cad_dxf.get_label_spot([(0.0, 0.0), (4.0, 0.0), (4.0, 4.0)])[:2], (4.0, 0.0))

    def test_unit_and_scale_options(self):
        self.assertEqual(cad_dxf.get_cad_unit({"cad_unit": "m"}), "m")
        self.assertEqual(cad_dxf.get_cad_unit({"cad_unit": "ft"}), constants.CAD_DEFAULT_UNIT)
        self.assertEqual(cad_dxf.get_cad_scale({"cad_scale": "200"}), 200)
        self.assertEqual(cad_dxf.get_cad_scale({"cad_scale": 5000}), constants.CAD_DEFAULT_SCALE)   # 목록 밖


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.prepared = context_builder.prepare(_request())
        cls.tmp = tempfile.TemporaryDirectory()
        cls.result = cad_dxf.write_dxf(cls.prepared, cls.tmp.name)
        cls.pairs = _read_pairs(cls.result["path"])
        cls.entities = _entities(cls.pairs)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_r12_structure(self):
        self.assertEqual(self.pairs[:4], [(0, "SECTION"), (2, "HEADER"), (9, "$ACADVER"), (1, "AC1009")])
        self.assertEqual(self.pairs[-1], (0, "EOF"))
        self.assertEqual(self.result["entities"], sum(1 for kind, _ in self.entities if kind in ("POLYLINE", "TEXT", "POINT")))
        kinds = [kind for kind, _ in self.entities]
        self.assertEqual(kinds.count("POLYLINE"), kinds.count("SEQEND"))   # 폴리선마다 정점 뒤 SEQEND
        table_layers = {value for code, value in self.pairs[:self.pairs.index((2, "ENTITIES"))] if code == 2} & {n for n, *_ in constants.CAD_LAYERS}
        self.assertEqual(table_layers, set(self.result["counts"]))   # 쓴 레이어만 표에

    def test_tables_font_and_lot_numbers(self):
        tables = self.pairs[:self.pairs.index((2, "ENTITIES"))]
        style = tables[tables.index((2, "US-KOR")):]
        self.assertEqual((dict(style[:12])[3], dict(style[:12])[4]), constants.CAD_FONT)   # SHX + 한글 큰 글꼴
        layer_colors = {}
        for (code, value), (_c2, _v2), (_c3, _v3), (code4, color) in zip(tables, tables[1:], tables[2:], tables[3:]):
            if (code, value) == (0, "LAYER"):
                layer_colors[_v2] = int(color)
        self.assertLess(layer_colors["US-LOT-NO-ALL"], 0)   # 나머지 지번은 꺼진 레이어
        self.assertGreater(layer_colors["US-LOT-NO"], 0)
        self.assertLess(self.result["counts"]["US-LOT-NO"], self.result["counts"]["US-LOT-NO-ALL"] / 5)

    def test_content_layers(self):
        counts = self.result["counts"]
        for layer in ("US-SITE", "US-RANGE", "US-LOT", "US-LOT-NO", "US-BLDG", "US-BLDG-FL", "US-ROAD", "US-ROAD-CL", "US-SPOT", "US-REF"):
            self.assertGreater(counts.get(layer, 0), 0, layer)
        self.assertEqual(counts["US-SITE"], 1)
        self.assertGreater(self.result["buildings"], 500)

    def test_korean_text_and_units(self):
        texts = [attrs[1][0] for kind, attrs in self.entities if kind == "TEXT"]
        self.assertTrue(any("성수동2가" in t for t in texts))   # CP949로 읽혀 한글 그대로
        self.assertTrue(any(t.startswith("좌표 - 십자 기준점(0,0) = EPSG:5186 E 204700.000") for t in texts))
        self.assertTrue(any(t.endswith("F") and t[:-1].isdigit() for t in texts))   # 건물 층수
        # mm 도면 — 반경 500 m 범위 폭이 약 100만 단위, 원점 방식이라 0 둘레
        xs = [float(v) for kind, attrs in self.entities if kind == "VERTEX" for v in attrs[10]]
        self.assertGreater(max(xs) - min(xs), 9.0e5)
        self.assertLess(abs(min(xs) + max(xs)) * 0.5, 2.0e5)

    def test_world_placement_in_m(self):
        prepared = context_builder.prepare(_request(placement="world", cad_unit="m", radius=200))
        writer, setting = cad_dxf.build_cad(prepared)
        self.assertEqual((setting["unit"], setting["scale"], setting["ltscale"]), ("m", constants.CAD_DEFAULT_SCALE, constants.CAD_DEFAULT_SCALE / 1000.0))
        site = next(shape for shape in writer.shapes if shape[1] == "US-SITE")
        self.assertTrue(all(200000 < x < 210000 and 545000 < y < 555000 for x, y in site[2]))   # EPSG:5186 그대로

    def test_engine_runs_without_3d(self):
        os.environ[constants.HOST_ENV] = "autocad"
        try:
            with tempfile.TemporaryDirectory() as root:
                request = dict(_request(radius=150), result_root=root, options=dict(_request(radius=150)["options"], make_sheets=False, make_basemap=False))
                phases = []
                response = context_builder.run(request, lambda phase, fraction, text: phases.append(phase) or True)
                self.assertTrue(response["ok"], response["error"])
                self.assertTrue(response["context"]["path"].endswith(constants.CAD_FILE_FORMAT % constants.CAD_DEFAULT_SCALE))
                self.assertNotIn("terrain", phases)
                self.assertIn("terrain", context_builder.get_skipped_phases(response["options"]))
                self.assertFalse(any(f["name"].endswith(".3dm") for f in response["files"]))
        finally:
            os.environ.pop(constants.HOST_ENV, None)


if __name__ == "__main__":
    unittest.main()
