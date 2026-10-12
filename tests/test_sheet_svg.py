"""sheet_svg — 프레임 수학·SVG 구조·13장 생성·빈 시트. 표준 라이브러리만, Rhino 없음."""

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants
import sheet_svg

SVG = "{http://www.w3.org/2000/svg}"
CENTER = (204764.0, 549052.0)   # 성수동2가 333-139 중심


def _square(cx, cy, half):
    return {"type": "Polygon", "coordinates": [[[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half], [cx - half, cy - half]]]}


def _lot(pnu, cx, cy, **attrs):
    base = dict(pnu=pnu, lot_number=pnu[-4:], land_use_status="단독", land_category="대", zone_name="준공업지역",
                land_price_won=5000000.0, road_contact="세로한면(가)", geometry=_square(cx, cy, 15.0))
    base.update(attrs)
    return SimpleNamespace(**base)


def _building(building_id, cx, cy, **attrs):
    base = dict(building_id=building_id, usability="01000", grnd_flr=3, use_apr_day="1995-05-01", geometry=_square(cx, cy, 6.0))
    base.update(attrs)
    return SimpleNamespace(**base)


def _feature(theme, kind, geometry, value=None, name=""):
    return SimpleNamespace(theme=theme, kind=kind, value=value, name=name, geometry=geometry)


def _tri(x, y, z0, z1, z2, class_name="terrain"):
    return ((x, y, z0), (x + 20.0, y, z1), (x, y + 20.0, z2), class_name)


def _group(root, group_id):
    return [g for g in root.iter(SVG + "g") if g.get("id") == group_id][0]


def _theme_paths(path):
    return list(_group(ET.parse(path).getroot(), "theme").iter(SVG + "path"))


def make_data():
    """필지 2·건물 3·삼각형 4 + 바탕 피처 조금."""
    cx, cy = CENTER
    frame = sheet_svg.Frame((841, 594), 3000, CENTER)
    lots = [_lot("1120011500103330139", cx, cy), _lot("1120011500103330140", cx + 40, cy, land_use_status="상업용", land_category="도로",
                                                       zone_name="제2종일반주거지역", land_price_won=9000000.0, road_contact="맹지")]
    buildings = [_building(1, cx, cy), _building(2, cx + 40, cy, usability="14000", grnd_flr=15, use_apr_day="2015-01-01"),
                 _building(3, cx - 40, cy, usability="", grnd_flr=0, use_apr_day="")]
    features = [_feature("water", "river", _square(cx, cy + 300, 50)), _feature("road", "surface", _square(cx, cy - 100, 30)),
                _feature("road", "centerline", {"type": "LineString", "coordinates": [[cx - 200, cy - 100], [cx + 200, cy - 100]]}, value=12.0)]
    overlays = [SimpleNamespace(theme="district", kind="개발진흥지구", name="산업개발진흥지구", geometry=_square(cx, cy, 120)),
                SimpleNamespace(theme="facility", kind="공원", name="소공원", geometry=_square(cx + 200, cy + 200, 30))]
    tris = [_tri(cx, cy, 10, 10, 10), _tri(cx + 20, cy, 12, 14, 30), _tri(cx, cy + 20, 45, 46, 47), _tri(cx + 20, cy + 20, 0, 0, 0, "outside")]
    extent = [(cx - 500, cy - 500), (cx + 500, cy - 500), (cx + 500, cy + 500), (cx - 500, cy + 500)]
    return sheet_svg.SheetData(frame=frame, target_lots=lots[:1], near_lots=lots, buildings=buildings, features=features, overlays=overlays,
                               extent_ring=extent, terrain_tris=tris, meta_lines=["자료기준 — 테스트", "출처 테스트", "좌표계 EPSG:5186", "정합 테스트", "경고 없음"],
                               sources=[SimpleNamespace(name="토지특성정보", reference_date="2026-05-13")],
                               options={"radius": 500, "shape": "buffer", "floor_breaks": [12, 20], "elev_preset": "20m", "today_year": 2026},
                               stats={"height_src": {"height": 0.5, "grnd_flr": 0.5}}, lot_name="성수동2가_333-139")


class FrameTest(unittest.TestCase):
    def test_a1_3000_world_size(self):
        frame = sheet_svg.Frame((841, 594), 3000, CENTER)
        self.assertAlmostEqual(frame.width_m, 2523.0)
        self.assertAlmostEqual(frame.height_m, 1782.0)
        min_x, min_y, max_x, max_y = frame.world_bounds()
        self.assertAlmostEqual(max_x - min_x, 2523.0)
        self.assertAlmostEqual(max_y - min_y, 1782.0)
        self.assertAlmostEqual((min_x + max_x) * 0.5, CENTER[0])

    def test_to_paper_orientation_and_roundtrip(self):
        frame = sheet_svg.Frame((841, 594), 3000, CENTER)
        self.assertEqual(frame.to_paper(*CENTER), (420.5, 297.0))
        mm_x, mm_y = frame.to_paper(CENTER[0] + 300.0, CENTER[1] + 300.0)   # 북동 300 m → 오른쪽 100 mm·위로 100 mm
        self.assertAlmostEqual(mm_x, 520.5)
        self.assertAlmostEqual(mm_y, 197.0)
        x, y = frame.to_world(mm_x, mm_y)
        self.assertAlmostEqual(x, CENTER[0] + 300.0)
        self.assertAlmostEqual(y, CENTER[1] + 300.0)
        corner = frame.to_paper(*frame.world_bounds()[:2])
        self.assertAlmostEqual(corner[0], 0.0)
        self.assertAlmostEqual(corner[1], 594.0)

    def test_frame_for_ring_picks_smallest_scale_that_fits(self):
        ring = [(CENTER[0] - 1000, CENTER[1] - 800), (CENTER[0] + 1000, CENTER[1] + 800)]
        self.assertEqual(sheet_svg.get_frame_for_ring((841, 594), [1000, 3000, 5000], CENTER, ring).scale, 3000)
        self.assertEqual(sheet_svg.get_frame_for_ring((841, 594), [1000], CENTER, ring).scale, 1000)


class SvgTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.data = make_data()
        self.results = sheet_svg.write_sheets(self.data, self.tmp, None, None)

    def test_13_sheets_written(self):
        self.assertEqual([r["id"] for r in self.results], list(range(1, 14)))
        for result in self.results:
            self.assertTrue(os.path.exists(result["path"]), result)
            self.assertEqual(result["name"], sheet_svg.SHEET_NAMES[result["id"]])
        self.assertTrue(self.results[0]["path"].endswith("01_위치범위도.svg"))

    def test_svg_structure(self):
        root = ET.parse(self.results[1]["path"]).getroot()   # #2 토지이용현황도
        self.assertEqual(root.get("viewBox"), "0 0 841.00 594.00")
        self.assertEqual(root.get("width"), "841.00mm")
        group_ids = [g.get("id") for g in root.iter(SVG + "g") if g.get("id") and not g.get("id").startswith("theme_")]
        expected = ["map", "base_water", "base_green", "base_road", "base_buildings", "theme", "base_parcels", "site", "extent", "labels",
                    "legend", "card", "meta", "scale_north", "frame"]
        self.assertEqual(group_ids, expected)
        self.assertEqual(len(root.findall(".//" + SVG + "clipPath")), 1)
        theme = _group(root, "theme")
        self.assertEqual([g.get("id") for g in theme], ["theme_detached", "theme_commercial"])   # 범례 키별 하위 그룹, 범례 순서
        self.assertEqual(len(list(theme.iter(SVG + "path"))), 2)   # 필지 2
        self.assertEqual(theme.get("stroke-width"), str(constants.SHEET_LINE_MM["parcel"]))   # 필지 주제 → 지적선은 주제가 맡는다
        self.assertEqual(len(list(_group(root, "base_parcels"))), 0)
        self.assertGreater(len(list(_group(root, "base_buildings"))), 0)
        texts = [t.text for t in root.iter(SVG + "text")]
        self.assertIn("자료기준 — 테스트", texts)
        self.assertIn("출처: 토지특성정보 2026-05-13", texts)
        self.assertTrue(any(t and t.startswith("단독주택") for t in texts))

    def test_theme_counts_per_sheet(self):
        def theme_paths(index):
            return _theme_paths(self.results[index]["path"])
        self.assertEqual(len(theme_paths(0)), 1)    # #1 대상지 K100 채움 1
        self.assertEqual(len(theme_paths(6)), 3)    # #7 건물 3
        self.assertEqual(len(theme_paths(9)), 2)    # #10 중로 1 + 맹지 1
        self.assertEqual(len(theme_paths(11)), 3)   # #12 outside 제외 삼각형 3
        self.assertEqual(len(theme_paths(12)), 3)   # #13
        root = ET.parse(self.results[12]["path"]).getroot()   # 지형 주제는 바탕(건물) 아래
        ids = [g.get("id") for g in _group(root, "map")]
        self.assertLess(ids.index("theme"), ids.index("base_buildings"))
        self.assertEqual(len(theme_paths(4)), 1)    # #5 용도지구 1
        self.assertFalse(any(r["empty"] for r in self.results))
        root = ET.parse(self.results[6]["path"]).getroot()   # #7 건물 주제 → base_buildings 비움, 지적선은 남김
        self.assertEqual(len(list(_group(root, "base_buildings"))), 0)
        self.assertEqual(len(list(_group(root, "base_parcels"))), 2)
        root = ET.parse(self.results[9]["path"]).getroot()   # #10 맹지 해치
        self.assertEqual(_group(root, "theme_landlocked").get("fill"), "url(#hatch_landlocked)")
        self.assertEqual(len(root.findall(".//" + SVG + "pattern")), len(constants.SHEET_HATCH))

    def test_height_card_korean_labels(self):
        root = ET.parse(self.results[7]["path"]).getroot()
        texts = [t.text for t in _group(root, "card").iter(SVG + "text")]
        self.assertIn("높이 출처 대장 높이 50 % · 대장 층수 50 %", texts)

    def test_floor_and_price_legends_are_dynamic(self):
        root = ET.parse(self.results[7]["path"]).getroot()
        texts = [t.text for t in root.iter(SVG + "text")]
        self.assertTrue(any(t.startswith("7~12층") for t in texts))
        self.assertTrue(any(t.startswith("21층 이상") for t in texts))
        self.assertTrue(any(t.startswith("미상  1") for t in texts))
        root = ET.parse(self.results[10]["path"]).getroot()
        texts = [t.text for t in root.iter(SVG + "text")]
        self.assertTrue(any("만원/㎡" in t for t in texts))

    def test_empty_sheets_report_reason(self):
        data = make_data()
        data.terrain_tris = []
        data.overlays = []
        results = {r["id"]: r for r in sheet_svg.write_sheets(data, self.tmp, [5, 12, 13, 2], None)}
        self.assertEqual((results[12]["empty"], results[12]["reason"]), (True, "지형 없음"))
        self.assertEqual((results[13]["empty"], results[13]["reason"]), (True, "지형 없음"))
        self.assertEqual((results[5]["empty"], results[5]["reason"]), (True, "데이터 없음"))
        self.assertEqual((results[2]["empty"], results[2]["reason"]), (False, ""))
        self.assertTrue(os.path.exists(results[12]["path"]))


class PathTest(unittest.TestCase):
    """path d — 용지 사각형 클립·정점 솎기·상대좌표."""

    def setUp(self):
        self.frame = sheet_svg.Frame((841, 594), 3000, CENTER)

    def test_clip_rect(self):
        rect = (0.0, 0.0, 10.0, 10.0)
        self.assertEqual(sheet_svg.get_clipped_ring([(2, 2), (8, 2), (8, 8), (2, 8)], rect), [(2, 2), (8, 2), (8, 8), (2, 8)])
        self.assertEqual(sheet_svg.get_clipped_ring([(20, 20), (30, 20), (30, 30)], rect), [])
        clipped = sheet_svg.get_clipped_ring([(-5, 2), (5, 2), (5, 8), (-5, 8)], rect)   # 왼쪽 반이 밖
        self.assertEqual(sorted(clipped), [(0.0, 2.0), (0.0, 8.0), (5, 2), (5, 8)])

    def test_path_d_relative_and_clipped(self):
        cx, cy = CENTER
        d = sheet_svg.get_path_d(_square(cx, cy, 15.0), self.frame)
        self.assertTrue(d.startswith("M415.50 302.00l") and d.endswith("Z"), d)
        self.assertEqual(d.count(" "), 6)   # "M x y" + "l dx dy" ×3 (닫힘 중복점 제거)
        half = self.frame.width_m   # 용지보다 큰 사각형 → 용지 + 여유 2 mm로 잘린다
        d = sheet_svg.get_path_d(_square(cx, cy, half), self.frame)
        self.assertEqual(d, "M-2.00 -2.00l0.00 598.00 845.00 0.00 0.00 -598.00Z")
        self.assertEqual(sheet_svg.get_path_d(_square(cx + 5000.0, cy, 15.0), self.frame), "")   # 용지 밖 → 빈 문자열
        self.assertEqual(sheet_svg.get_path_d(_square(cx, cy, 0.01), self.frame), "")   # 0.05 mm 미만 정점 → 퇴화

    def test_line_not_clipped(self):
        cx, cy = CENTER
        line = {"type": "LineString", "coordinates": [[cx - 3000.0, cy], [cx + 3000.0, cy]]}
        self.assertEqual(sheet_svg.get_path_d(line, self.frame), "M-579.50 297.00l2000.00 0.00")


class ClassifyTest(unittest.TestCase):
    def test_slope_and_elev(self):
        self.assertAlmostEqual(sheet_svg.get_slope_deg(_tri(0, 0, 0, 0, 0)), 0.0)
        self.assertAlmostEqual(sheet_svg.get_slope_deg(_tri(0, 0, 0, 20, 0)), 45.0)
        self.assertEqual(sheet_svg.classify_slope(_tri(0, 0, 0, 20, 0), {}), "s5")
        self.assertEqual(sheet_svg.classify_elev(_tri(0, 0, 45, 46, 47), {"elev_step": 20.0}), "e2")

    def test_lot_building_road_keys(self):
        self.assertEqual(sheet_svg.classify_zone(_lot("1", 0, 0, zone_name="제3종일반주거지역"), {}), "r3")
        self.assertEqual(sheet_svg.classify_land_category(_lot("1", 0, 0, land_category="구거"), {}), "water")
        self.assertEqual(sheet_svg.classify_use(_building(1, 0, 0, usability="04000"), {}), "neighborhood")
        self.assertEqual(sheet_svg.classify_age(_building(1, 0, 0, use_apr_day="1990-01-01"), {"year": 2026}), "age3")
        self.assertEqual(sheet_svg.classify_road(_feature("road", "centerline", {}, value=45.0), {}), "w_grand")
        self.assertEqual(sheet_svg.classify_road(_feature("road", "centerline", {}, value=None), {}), "w_unknown")
        self.assertEqual(sheet_svg.classify_floor(_building(1, 0, 0, grnd_flr=13), {"floor_breaks": (1, 3, 4, 6, 12, 20)}), "f5")
        for sheet_id, _, _, (subject, _) in sheet_svg.SHEETS:
            self.assertIn(subject, ("target_lot", "lot", "overlay", "building", "road", "terrain"), sheet_id)
        self.assertEqual(len(sheet_svg.SHEETS), 13)
        self.assertEqual(set(constants.SHEET_LEGENDS), set(range(1, 14)))


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@unittest.skipUnless((FIXTURE_DIR / "seongsu_site.db").exists() and (FIXTURE_DIR / "seongsu_context.db").exists(), "fixture DB 없음")
class FixtureTest(unittest.TestCase):
    """실제 lot_db·context_db 데이터클래스로 13장 — 반경 500 m bbox, 합성 지형 삼각형."""

    def test_13_sheets_from_fixture(self):
        import lot_db
        import context_db
        site_db, ctx_db = str(FIXTURE_DIR / "seongsu_site.db"), str(FIXTURE_DIR / "seongsu_context.db")
        lot_data = lot_db.load([constants.TEST_CONTEXT_PNU], database_path=site_db)
        target = lot_data.lots[0]
        cx, cy = (target.min_x + target.max_x) * 0.5, (target.min_y + target.max_y) * 0.5
        bounds = (cx - 500, cy - 500, cx + 500, cy + 500)
        near, _ = lot_db.load_parcels_in_bounds(*bounds, limit=None, database_path=site_db)
        context = context_db.load(bounds, database_path=ctx_db)
        tris = [_tri(cx + i * 50, cy + j * 50, 10 + i, 12 + j, 11) for i in range(-3, 3) for j in range(-3, 3)]
        prepared = SimpleNamespace(request={"options": dict(constants.PANEL_DEFAULT_OPTIONS)}, target_lots=lot_data.lots, near_lots=near,
                                   buildings=context.buildings, features=context.features, overlays=lot_data.overlays, scales=[3000],
                                   extent_ring=[(cx - 500, cy - 500), (cx + 500, cy - 500), (cx + 500, cy + 500), (cx - 500, cy + 500)],
                                   meta={"meta_lines": ["자료기준 — fixture"]}, sources=context.sources, stats={}, lot_name="성수동2가_333-139")
        data = sheet_svg.SheetData.from_prepared(prepared, tris)
        self.assertEqual(data.frame.scale, 3000)
        self.assertAlmostEqual(data.frame.center[0], cx)
        results = sheet_svg.write_sheets(data, tempfile.mkdtemp(), None, None)
        self.assertEqual(len(results), 13)
        self.assertEqual([r["id"] for r in results if r["empty"]], [5])   # 대상 필지에 용도지구·구역 없음 — fixture 실측
        self.assertGreater(len(_theme_paths(results[6]["path"])), 2000)   # ±500 m 건물 ≈2,800동
        for r in results:
            ET.parse(r["path"])   # 13장 전부 XML로 열린다
            self.assertLess(os.path.getsize(r["path"]), 3 * 1024 * 1024, r["name"])

    def test_13_sheets_from_prepare(self):
        """context_builder.prepare(fixture) → SheetData → 13장. 지형은 합성 격자(Rhino 없음)."""
        import context_builder
        request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": str(FIXTURE_DIR / "seongsu_site.db"),
                   "context_db": str(FIXTURE_DIR / "seongsu_context.db"), "options": {"radius": 500}}
        prepared = context_builder.prepare(request)
        cx, cy = prepared.target_lots[0].min_x, prepared.target_lots[0].min_y
        tris = [_tri(cx + i * 50, cy + j * 50, 10 + i, 12 + j, 11) for i in range(-3, 3) for j in range(-3, 3)]
        data = sheet_svg.SheetData.from_prepared(prepared, tris)
        self.assertEqual(data.frame.scale, 3000)
        self.assertEqual(len(data.meta_lines), 5)
        results = sheet_svg.write_sheets(data, tempfile.mkdtemp(), None, None)
        self.assertEqual([r["id"] for r in results if r["empty"]], [])
        for r in results:
            self.assertLess(os.path.getsize(r["path"]), 3 * 1024 * 1024, r["name"])   # 성수 fixture 실측 최대 2.1 MB(#6)
        root = ET.parse(results[7]["path"]).getroot()   # #8 높이 출처 카드
        texts = [t.text for t in _group(root, "card").iter(SVG + "text")]
        self.assertTrue(any(t.startswith("높이 출처 대장 높이") for t in texts), texts)
        root = ET.parse(results[0]["path"]).getroot()   # #1 대상지 K100
        self.assertEqual(len(_theme_paths(results[0]["path"])), 1)
        self.assertEqual(_group(root, "theme_target").get("fill"), "#1E1E1C")


if __name__ == "__main__":
    unittest.main()
