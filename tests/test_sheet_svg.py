"""sheet_svg — 프레임 수학·스타일 해석·템플릿·16장 생성·빈 시트. 표준 라이브러리만, Rhino 없음."""

import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants
import sheet_svg

SVG = "{http://www.w3.org/2000/svg}"
FAKE_TILE = b"\xff\xd8\xff\xe0fake"
_NO_NETWORK = patch.object(sheet_svg, "_fetch_tile", lambda url: FAKE_TILE)   # 테스트는 영상 타일을 받지 않는다(항공사진 시트)


def setUpModule():
    _NO_NETWORK.start()   # 모듈 import 때 바꾸면 test_loader의 reload가 되돌린다 — 이 모듈 테스트 직전에 건다


def tearDownModule():
    _NO_NETWORK.stop()
CENTER = (204764.0, 549052.0)   # 성수동2가 333-139 중심
ID = constants.SHEET_IDS


def _square(cx, cy, half):
    return {"type": "Polygon", "coordinates": [[[cx - half, cy - half], [cx + half, cy - half], [cx + half, cy + half], [cx - half, cy + half], [cx - half, cy - half]]]}


def _point(x, y):
    return {"type": "Point", "coordinates": [x, y]}


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


def _groups(root):
    return [g.get("id") for g in root.iter(SVG + "g") if g.get("id")]


def _group(root, group_id):
    return [g for g in root.iter(SVG + "g") if g.get("id") == group_id][0]


def _theme_paths(path):
    return list(_group(ET.parse(path).getroot(), "theme").iter(SVG + "path"))


def _texts(root, group_id=None):
    node = _group(root, group_id) if group_id else root
    return [t.text for t in node.iter(SVG + "text")]


def make_data(**options):
    """필지 2·건물 3·삼각형 4·역 1 + 바탕 피처 조금."""
    cx, cy = CENTER
    lots = [_lot("1120011500103330139", cx, cy), _lot("1120011500103330140", cx + 40, cy, land_use_status="상업용", land_category="도로",
                                                       zone_name="제2종일반주거지역", land_price_won=9000000.0, road_contact="맹지")]
    buildings = [_building(1, cx, cy), _building(2, cx + 40, cy, usability="14000", grnd_flr=15, use_apr_day="2015-01-01"),
                 _building(3, cx - 40, cy, usability="", grnd_flr=0, use_apr_day="")]
    features = [_feature("water", "river", _square(cx, cy + 300, 50)), _feature("road", "surface", _square(cx, cy - 100, 30)),
                _feature("road", "centerline", {"type": "LineString", "coordinates": [[cx - 200, cy - 100], [cx + 200, cy - 100]]}, value=12.0),
                _feature("rail", "line", {"type": "LineString", "coordinates": [[cx - 600, cy + 200], [cx + 600, cy + 200]]}),
                _feature("transit", "station", _point(cx + 100, cy + 200), name="성수역"),
                _feature("label", "place", _point(cx - 150, cy + 50), name="(성수1가1동)"),
                _feature("label", "place", _point(cx + 150, cy - 50), name="성수동오피스신축공사(24년01월예정)")]
    overlays = [SimpleNamespace(theme="district", kind="개발진흥지구", name="산업개발진흥지구", geometry=_square(cx, cy, 120)),
                SimpleNamespace(theme="facility", kind="공원", name="소공원", geometry=_square(cx + 200, cy + 200, 30))]
    tris = [_tri(cx, cy, 10, 10, 10), _tri(cx + 20, cy, 12, 14, 30), _tri(cx, cy + 20, 45, 46, 47), _tri(cx + 20, cy + 20, 0, 0, 0, "outside")]
    extent = [(cx - 500, cy - 500), (cx + 500, cy - 500), (cx + 500, cy + 500), (cx - 500, cy + 500)]
    base_options = {"radius": 500, "shape": "circle", "floor_breaks": [12, 20], "elev_preset": "20m", "today_year": 2026}
    base_options.update(options)
    return sheet_svg.SheetData(paper_mm=(420.0, 297.0), scales=[5000], center=CENTER, target_lots=lots[:1], near_lots=lots, buildings=buildings,
                               features=features, overlays=overlays, extent_ring=extent, terrain_tris=tris,
                               meta_lines=["자료기준 — 테스트", "출처: 테스트", "좌표계 EPSG:5186", "정합 테스트", "경고 없음"],
                               options=base_options, stats={"height_src": {"height": 0.5, "grnd_flr": 0.5}}, lot_name="성수동2가_333-139")


class FrameTest(unittest.TestCase):
    def test_a1_3000_world_size(self):
        frame = sheet_svg.Frame((841, 594), 3000, CENTER)
        self.assertAlmostEqual(frame.width_m, 2523.0)
        self.assertAlmostEqual(frame.height_m, 1782.0)
        ring = [(CENTER[0] - 1000, CENTER[1] - 800), (CENTER[0] + 1000, CENTER[1] + 800)]
        self.assertEqual(sheet_svg.get_frame_for_ring((841, 594), [1000, 3000, 5000], CENTER, ring).scale, 3000)
        self.assertEqual(sheet_svg.get_frame_for_ring((841, 594), [1000], CENTER, ring).scale, 1000)

    def test_to_paper_orientation_and_roundtrip(self):
        frame = sheet_svg.Frame((273, 273), 5000, CENTER)
        self.assertEqual(frame.to_paper(*CENTER), (136.5, 136.5))
        x, y = frame.to_paper(CENTER[0] + 100, CENTER[1] + 100)   # 북동 → 오른쪽 위
        self.assertAlmostEqual(x, 156.5)
        self.assertAlmostEqual(y, 116.5)
        self.assertEqual(tuple(round(v, 6) for v in frame.to_world(x, y)), (CENTER[0] + 100, CENTER[1] + 100))


class RangeLabelTest(unittest.TestCase):
    def test_rect_reads_side_length(self):
        """사각형 범위(기본)는 한 변으로 적는다 — radius 250을 '반경 250 m'로 적어 500 m 사각형과 어긋났다."""
        label = lambda **options: sheet_svg._get_range_label(SimpleNamespace(options=options))
        self.assertEqual(label(shape="rect", radius=850), "사각형 한 변 1,700 m")
        self.assertEqual(label(shape="circle", radius=250), "반경 250 m")


class TemplateStyleTest(unittest.TestCase):
    def test_map_box_per_layout(self):
        self.assertEqual(sheet_svg.get_map_box((420, 297), "side"), (12.0, 12.0, 273.0, 273.0))   # A3 = 정사각 지도 칸
        self.assertEqual(sheet_svg.get_map_box((420, 297), "map"), (0.0, 0.0, 420.0, 297.0))
        x, y, w, h = sheet_svg.get_map_box((420, 297), "bottom")
        self.assertEqual((x, y, w), (12.0, 12.0, 396.0))
        self.assertAlmostEqual(h, 297 - 24 - 12 - 50)
        self.assertAlmostEqual(sheet_svg.get_map_box((841, 594), "side")[2], 273.0 * 2 + (841 - 840) * 1.0, delta=1.5)   # A1 ≈ 2배

    def test_sheet_scale_steps_up_when_extent_does_not_fit(self):
        ring = [(CENTER[0] - 200, CENTER[1] - 200), (CENTER[0] + 200, CENTER[1] - 200), (CENTER[0] + 200, CENTER[1] + 200), (CENTER[0] - 200, CENTER[1] + 200)]
        self.assertEqual(sheet_svg.get_sheet_scales([1000]), [1000, 3000, 5000])
        data = sheet_svg.SheetData(paper_mm=(420.0, 297.0), scales=[1000], center=CENTER, extent_ring=ring)
        self.assertEqual(data.get_frame("side").scale, 3000)   # A3 1:1000 지도 칸 273 m < 범위 400 m
        bounds = sheet_svg.get_sheet_query_bounds((420.0, 297.0), [1000], CENTER, ring)
        self.assertAlmostEqual(bounds[2] - bounds[0], 1260.0)   # 그 축척의 용지 전체를 질의한다

    def test_style_resolves_preset_and_user_values(self):
        style = sheet_svg.get_style({})
        self.assertEqual(style["preset"], "std")
        self.assertEqual(style["site"], constants.STYLE_PRESETS["std"]["site"])
        self.assertEqual(style["layout"], "side")
        style = sheet_svg.get_style({"style": {"preset": "dark", "building": "#abcdef", "road": "red", "line_scale": 9,
                                               "layout": "bottom", "font": "comic", "labels": 0, "unknown": 1, "project": "  성수 재생  "}})
        self.assertEqual(style["paper"], constants.STYLE_PRESETS["dark"]["paper"])
        self.assertEqual(style["building"], "#ABCDEF")                                   # 사용자 색
        self.assertEqual(style["road"], constants.STYLE_PRESETS["dark"]["road"])          # 형식이 틀린 색은 버린다
        self.assertEqual(style["line_scale"], constants.STYLE_RANGES["line_scale"][1])    # 범위로 자른다
        self.assertEqual((style["layout"], style["font"], style["labels"]), ("bottom", "sans", False))
        self.assertEqual(style["project"], "성수 재생")
        self.assertNotIn("unknown", style)
        self.assertEqual(sheet_svg.get_style({"style": {"preset": "없는것"}})["preset"], constants.STYLE_DEFAULT_PRESET)

    def test_ramp_interpolates_and_reverses_on_dark_paper(self):
        light = sheet_svg.get_style({})
        ramp = sheet_svg.get_ramp(light, 7)
        self.assertEqual(len(ramp), 7)
        self.assertEqual((ramp[0], ramp[-1]), constants.STYLE_RAMPS["warm"][::5])
        dark = sheet_svg.get_style({"style": {"preset": "dark"}})
        self.assertEqual(sheet_svg.get_ramp(dark, 6), list(reversed(constants.STYLE_RAMPS[dark["ramp"]])))
        self.assertEqual(sheet_svg.get_mixed_color("#000000", "#FFFFFF", 0.5), "#808080")

    def test_flat_terrain_gets_finer_elevation_steps(self):
        data = make_data()
        cx, cy = CENTER
        data.terrain_tris = [_tri(cx + i * 20, cy, 10.6 + i * 0.5, 11.0 + i * 0.5, 11.2 + i * 0.5) for i in range(8)]   # 10.6~14.7 m (성수 실측과 비슷)
        root = ET.parse(sheet_svg.write_sheets(data, tempfile.mkdtemp(), [ID["elev"]])[0]["path"]).getroot()
        legend = [t for t in _texts(root, "legend") if t and t.endswith("m")]
        self.assertGreaterEqual(len(legend), constants.ELEV_MIN_BANDS, legend)   # 20 m 한 단계 → 1 m 단계로
        self.assertIn("단계 1 m (평탄지라 자동으로 줄임)", _texts(root, "card"))

    def test_wrapped_lines_fit(self):
        lines = sheet_svg.get_wrapped_lines("자료기준 — 필지 토지특성정보 2026-05-13 · 건물 GIS건물통합정보 2026-10-06", 40.0, 2.0)
        self.assertGreater(len(lines), 1)
        self.assertTrue(all(sheet_svg.get_text_width_em(line) * 2.0 <= 40.0 for line in lines))


class SvgTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        cls.data = make_data()
        cls.results = {r["id"]: r for r in sheet_svg.write_sheets(cls.data, cls.tmp)}

    def root(self, key):
        return ET.parse(self.results[ID[key]]["path"]).getroot()

    def test_all_sheets_written(self):
        self.assertEqual(sorted(self.results), list(range(len(constants.SHEET_CATALOG))))
        for result in self.results.values():
            self.assertTrue(os.path.exists(result["path"]), result)

            self.assertTrue(result["thumb"].startswith("data:image/svg+xml;base64," if result["id"] == ID["aerial"] else "data:image/png;base64,"))    # 패널 도면 칸 썸네일
            self.assertEqual(result["name"], sheet_svg.SHEET_NAMES[result["id"]])
        self.assertTrue(self.results[0]["path"].endswith("00_베이스맵.svg"))
        self.assertEqual({r["id"] for r in self.results.values() if r["empty"]}, {ID["density"], ID["public"]})   # 시험 데이터에 도로 도넛·공공 용도가 없다

    def test_template_structure(self):
        root = self.root("land_use")
        self.assertEqual(root.get("viewBox"), "0 0 420.00 297.00")
        self.assertEqual(root.get("width"), "420.00mm")
        ids = _groups(root)
        order = ["map", "base_road", "base_water", "base_green", "base_rail", "base_buildings", "theme", "base_parcels", "extent", "site",
                 "labels", "info", "legend", "card", "meta", "scale_north"]
        self.assertEqual([i for i in ids if i in order], order)
        self.assertEqual(_group(root, "map").get("transform"), "translate(12.00 12.00)")   # 지도 칸 = 정보 열 왼쪽 정사각
        theme = _group(root, "theme")
        self.assertEqual([g.get("id") for g in theme], ["theme_detached", "theme_commercial"])   # 범례 키별 하위 그룹, 범례 순서
        self.assertEqual(len(list(_group(root, "base_parcels"))), 0)   # 필지 주제 → 지적선은 주제가 맡는다
        self.assertEqual(len(root.findall(".//" + SVG + "clipPath")), 1)
        texts = _texts(root)
        self.assertIn("자료기준 — 테스트", texts)
        self.assertIn("%02d" % ID["land_use"], texts)
        self.assertIn("토지이용현황", texts)
        self.assertTrue(any(t and t.startswith("단독주택") for t in _texts(root, "legend")))
        self.assertIsNotNone(root.find(".//*[@id='mask']"))   # 범위 밖 흐리기
        self.assertIsNotNone(root.find(".//*[@id='map_frame']"))

    def test_theme_counts_per_sheet(self):
        def count(key):
            return len(_theme_paths(self.results[ID[key]]["path"]))
        self.assertEqual(count("base"), 1)       # 대상지 1
        self.assertEqual(count("figure"), 3)     # 건물 3
        self.assertEqual(count("use"), 3)
        self.assertEqual(count("road"), 2)       # 중로 1 + 맹지 1
        self.assertEqual(count("elev"), 3)       # outside 제외 삼각형 3
        self.assertEqual(count("slope"), 3)
        self.assertEqual(count("district"), 1)
        self.assertEqual(count("green"), 2)      # 수면 1 + 공원 시설 1
        transit = self.root("transit")
        self.assertEqual(len(list(_group(transit, "theme_catch1"))), 1)   # 역 1 → 원 1
        self.assertEqual(len(list(_group(transit, "stations").iter(SVG + "circle"))), 1)
        terrain = self.root("elev")   # 지형 주제는 바탕(건물) 아래
        ids = [g.get("id") for g in _group(terrain, "map")]
        self.assertLess(ids.index("theme"), ids.index("base_buildings"))
        use = self.root("use")   # 건물 주제 → base_buildings 비움
        self.assertEqual(len(list(_group(use, "base_buildings"))), 0)
        road = self.root("road")
        self.assertEqual(_group(road, "theme_landlocked").get("fill"), "url(#hatch_landlocked)")
        self.assertEqual(len(road.findall(".//" + SVG + "pattern")), len(constants.SHEET_HATCH))
        self.assertIsNone(self.root("base").find(".//*[@id='mask']"))   # 베이스맵은 흐리지 않는다

    def test_cards_and_dynamic_legends(self):
        floor = self.root("floor")
        texts = _texts(floor, "legend")
        self.assertIn("7~12층", texts)
        self.assertIn("21층 이상", texts)
        self.assertIn("높이 출처 대장 높이 50 % · 대장 층수 50 %", _texts(floor, "card"))
        self.assertTrue(any("만원/㎡" in (t or "") for t in _texts(self.root("price"), "legend")))
        transit = _texts(self.root("transit"), "card")
        self.assertIn("가장 가까운 역 성수역 224 m", transit)
        figure = _texts(self.root("figure"), "card")
        self.assertIn("범위 안 건물 3동", figure)
        self.assertIn("건물 바닥면적 비율 0.0 %", figure)   # 432 ㎡ / 1,000,000 ㎡
        self.assertIn("평균 바닥면적 144 ㎡", figure)
        self.assertIn("1", _texts(self.root("base"), "legend"))   # 항목이 하나면 비율 없이 개수만

    def test_labels_filter_construction_names(self):
        texts = _texts(self.root("base"), "labels")
        self.assertIn("성수1가1동", texts)
        self.assertIn("성수역", texts)
        self.assertIn("0139", texts)   # 대상지 지번
        self.assertFalse(any("공사" in (t or "") for t in texts))

    def test_style_colors_and_layouts(self):
        data = make_data(style={"preset": "mono", "site": "#0057FF", "layout": "bottom", "labels": False})
        result = sheet_svg.write_sheets(data, tempfile.mkdtemp(), [ID["base"]])[0]
        root = ET.parse(result["path"]).getroot()
        self.assertEqual(root.find(".//*[@id='paper']").get("fill"), constants.STYLE_PRESETS["mono"]["paper"])
        self.assertEqual(_group(root, "site").get("stroke"), "#0057FF")
        self.assertEqual(root.find(".//*[@id='sheet_number']").get("fill"), "#0057FF")
        self.assertNotIn("stations", _groups(root))   # 라벨 끔
        self.assertEqual(float(_group(root, "map").get("transform").split()[1].rstrip(")")), 12.0)
        data = make_data(style={"layout": "map"})
        root = ET.parse(sheet_svg.write_sheets(data, tempfile.mkdtemp(), [ID["floor"]])[0]["path"]).getroot()
        self.assertIsNone(root.find(".//*[@id='map_frame']"))
        self.assertIn("scale_north", _groups(root))   # 지도만이어도 축척·출처는 남긴다
        self.assertTrue(any("출처" in (t or "") for t in _texts(root, "info")))

    def test_empty_sheets_report_reason(self):
        data = make_data()
        data.terrain_tris = []
        data.overlays = []
        results = {r["id"]: r for r in sheet_svg.write_sheets(data, tempfile.mkdtemp(), [ID["district"], ID["elev"], ID["slope"], ID["land_use"]])}
        self.assertEqual((results[ID["elev"]]["empty"], results[ID["elev"]]["reason"]), (True, "지형 없음"))
        self.assertEqual((results[ID["slope"]]["empty"], results[ID["slope"]]["reason"]), (True, "지형 없음"))
        self.assertEqual((results[ID["district"]]["empty"], results[ID["district"]]["reason"]), (True, "데이터 없음"))
        self.assertEqual((results[ID["land_use"]]["empty"], results[ID["land_use"]]["reason"]), (False, ""))
        self.assertTrue(os.path.exists(results[ID["elev"]]["path"]))

    def test_frame_follows_layout(self):
        side = self.data.get_frame("side")
        self.assertEqual(side.paper_mm, (273.0, 273.0))
        bottom = self.data.get_frame("bottom")
        self.assertEqual(bottom.paper_mm[0], 396.0)
        self.assertEqual(self.data.path_cache, {})   # 칸이 바뀌면 path 캐시를 비운다


class AnalysisSheetTest(unittest.TestCase):
    """2단계 분석도(필지 규모·블록 밀도·보행권·공공시설)·틀·레이어 .ai·썸네일."""

    def test_blocks_from_road_parcel_holes(self):
        cx, cy = CENTER
        donut = {"type": "Polygon", "coordinates": [_square(cx, cy, 200)["coordinates"][0], _square(cx, cy, 100)["coordinates"][0]]}
        data = make_data()
        data.near_lots = [_lot("road", cx, cy, land_category="도로", geometry=donut)]
        data.target_lots = []
        data.buildings = [_building(1, cx, cy, grnd_flr=4)]   # 12×12 m · 4층 → 576 ㎡ / 40,000 ㎡
        blocks = sheet_svg.get_blocks(data)
        self.assertEqual(len(blocks), 1)
        self.assertAlmostEqual(blocks[0].area, 40000.0)
        self.assertAlmostEqual(blocks[0].far, 100.0 * 576 / 40000)
        self.assertEqual(sheet_svg.classify_density(blocks[0], {}), "d0")

    def test_walk_network_bands_and_station(self):
        cx, cy = CENTER
        data = make_data()
        line = {"type": "LineString", "coordinates": [[cx + x, cy] for x in range(0, 1300, 100)]}   # 동쪽으로 1.2 km
        data.features = [_feature("road", "centerline", line), _feature("transit", "station", _point(cx + 600, cy + 20), name="동쪽역")]
        walk = sheet_svg.get_walk(data)
        self.assertEqual(sorted({e.band for e in walk["edges"]}), [0, 1, 2])
        self.assertAlmostEqual(walk["lengths"][0], 400.0)
        self.assertAlmostEqual(walk["stations"][0][0], 620.0 / constants.SHEET_WALK_SPEED_M_PER_MIN)

    def test_lot_size_and_public_classes(self):
        self.assertEqual(sheet_svg.classify_lot_size(_lot("1", 0, 0, registered_area=60.0), {}), "a0")      # 과소필지
        self.assertEqual(sheet_svg.classify_lot_size(_lot("1", 0, 0, registered_area=5000.0), {}), "a5")
        self.assertIsNone(sheet_svg.classify_lot_size(_lot("1", 0, 0, land_category="도로"), {}))
        self.assertEqual(sheet_svg.classify_public(_building(1, 0, 0, usability="10000"), {}), "education")
        self.assertEqual(sheet_svg.classify_public(_building(1, 0, 0, usability="", ngii_use="의료시설"), {}), "welfare")
        self.assertEqual(sheet_svg.classify_public(_lot("1", 0, 0, land_category="학교용지"), {}), "school_lot")
        self.assertEqual(sheet_svg.classify_public(SimpleNamespace(theme="facility", kind="광장"), {}), "plaza")

    def test_template_sheet_has_empty_layers_in_ai(self):
        import re
        result = sheet_svg.write_sheets(make_data(), tempfile.mkdtemp(), [ID["image"]])[0]
        self.assertFalse(result["empty"])   # 틀은 빈 시트가 아니다
        root = ET.parse(result["path"]).getroot()
        self.assertEqual([g.get("id") for g in _group(root, "theme")], ["theme_path", "theme_edge", "theme_district", "theme_node", "theme_landmark"])
        ai_path = sheet_svg.get_sheet_ai(result["path"])   # 누를 때 만든다
        self.assertEqual(sheet_svg.get_sheet_ai(result["path"]), ai_path)   # 두 번째는 있는 것을 쓴다
        text = open(ai_path, encoding="ascii").read()
        layers = re.findall(r"^\(([a-z_0-9]+)[^\n]*\) Ln$", text, re.M)
        self.assertTrue({"theme_path", "theme_landmark", "base_buildings", "info"} <= set(layers), layers)   # 빈 레이어도 남는다
        self.assertNotIn("mask", layers)   # 투명도(범위 밖 흐리기)는 레거시 .ai에 없어 뺀다

    def test_thumbnail_png_is_valid(self):
        import base64
        uri = sheet_svg.render_thumbnail(ID["floor"], make_data())
        png = base64.b64decode(uri.split(",", 1)[1])
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        self.assertEqual(int.from_bytes(png[16:20], "big"), constants.SHEET_THUMB_PX)


class PathTest(unittest.TestCase):
    """path d — 지도 칸 사각형 클립·정점 솎기·상대좌표."""

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
        half = self.frame.width_m   # 칸보다 큰 사각형 → 칸 + 여유 2 mm로 잘린다
        d = sheet_svg.get_path_d(_square(cx, cy, half), self.frame)
        self.assertEqual(d, "M-2.00 -2.00l0.00 598.00 845.00 0.00 0.00 -598.00Z")
        self.assertEqual(sheet_svg.get_path_d(_square(cx + 5000.0, cy, 15.0), self.frame), "")   # 칸 밖 → 빈 문자열
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

    def test_lot_building_road_green_keys(self):
        self.assertEqual(sheet_svg.classify_zone(_lot("1", 0, 0, zone_name="제3종일반주거지역"), {}), "r3")
        self.assertEqual(sheet_svg.classify_land_category(_lot("1", 0, 0, land_category="구거"), {}), "water")
        self.assertEqual(sheet_svg.classify_use(_building(1, 0, 0, usability="04000"), {}), "neighborhood")
        self.assertEqual(sheet_svg.classify_age(_building(1, 0, 0, use_apr_day="1990-01-01"), {"year": 2026}), "age3")
        self.assertEqual(sheet_svg.classify_road(_feature("road", "centerline", {}, value=45.0), {}), "w_grand")
        self.assertEqual(sheet_svg.classify_road(_feature("road", "centerline", {}, value=None), {}), "w_unknown")
        self.assertEqual(sheet_svg.classify_floor(_building(1, 0, 0, grnd_flr=13), {"floor_breaks": (1, 3, 4, 6, 12, 20)}), "f5")
        self.assertEqual(sheet_svg.classify_green(_lot("1", 0, 0, land_category="공원"), {}), "park")
        self.assertEqual(sheet_svg.classify_green(_lot("1", 0, 0, land_category="임야"), {}), "green")
        self.assertEqual(sheet_svg.classify_green(_lot("1", 0, 0, land_category="하천"), {}), "water")
        self.assertIsNone(sheet_svg.classify_green(_lot("1", 0, 0), {}))
        self.assertEqual(sheet_svg.classify_green(_feature("water", "river", {}), {}), "water")
        self.assertEqual(sheet_svg.classify_green(SimpleNamespace(theme="facility", kind="녹지"), {}), "green")

    def test_catalog_tables_agree(self):
        keys = [key for _id, key, *_ in constants.SHEET_CATALOG]
        self.assertEqual([sheet_id for sheet_id, *_ in constants.SHEET_CATALOG], list(range(len(constants.SHEET_CATALOG))))
        self.assertEqual(set(keys), set(sheet_svg.SHEETS))
        self.assertEqual(set(keys), set(constants.SHEET_LEGENDS))
        for key, (subject, _entries) in constants.SHEET_LEGENDS.items():
            self.assertIn(subject, ("target_lot", "lot", "overlay", "building", "road", "terrain", "station", "green", "block", "walk", "public", "none"), key)


class AerialSheetTest(unittest.TestCase):
    """항공사진 — 타일 줌·배치(웹 메르카토르 → TM 아핀), 소스 폴백, 캐시, 빈 시트."""

    def test_zoom_and_tile_placement(self):
        frame = sheet_svg.Frame((273.0, 273.0), 5000, CENTER)
        zoom, tiles, m_per_px = sheet_svg.get_aerial_tiles(frame, (0.0, 0.0, 273.0, 273.0), constants.AERIAL_DPI / 25.4)
        self.assertEqual(zoom, 18)   # 1:5000 · 150 dpi = 0.85 m/px → 줌 18 (0.47 m/px, 위도 37.5°)
        self.assertAlmostEqual(m_per_px, 0.474, places=2)
        self.assertTrue(100 < len(tiles) <= constants.AERIAL_MAX_TILES)
        data = make_data()
        lines, _attribution, _m = sheet_svg._get_aerial_images(data, frame, (0.0, 0.0, 273.0, 273.0), constants.AERIAL_DPI / 25.4)
        self.assertEqual(len(lines), len(tiles))
        a, b, c, d = (float(v) for v in lines[0].split('matrix(')[1].split(")")[0].split()[:4])
        tile_mm = 256 * m_per_px * 1000.0 / 5000
        self.assertAlmostEqual(a, tile_mm, delta=tile_mm * 0.01)   # 타일 한 변 = 지상 길이 / 축척
        self.assertAlmostEqual(d, tile_mm, delta=tile_mm * 0.01)
        self.assertLess(abs(b) / a, 0.01)   # 서울(127° 근처) 자오선수차는 1/100 rad 아래
        self.assertLess(abs(c) / d, 0.01)

    def test_sheet_images_card_and_cache(self):
        data = make_data()
        calls = []
        with patch.object(sheet_svg, "_fetch_tile", lambda url: calls.append(url) or FAKE_TILE):
            result = sheet_svg.write_sheets(data, tempfile.mkdtemp(), [ID["aerial"]])[0]
            first = len(calls)
            sheet_svg.write_sheets(data, tempfile.mkdtemp(), [ID["aerial"]])
        self.assertEqual(len(calls), first)   # 다시 그려도(스타일 적용) 받은 타일을 쓴다
        self.assertFalse(result["empty"])
        root = ET.parse(result["path"]).getroot()
        self.assertEqual(len(list(root.iter(SVG + "image"))), len([u for u in calls if "/18/" in u]))
        self.assertTrue(any(t.startswith("영상 ") for t in _texts(root, "card")))
        self.assertIsNone(root.find(".//*[@id='mask']"))   # 범위 밖을 흐리지 않는다
        self.assertIsNotNone(root.find(".//*[@id='extent_halo']"))
        self.assertEqual(sheet_svg.get_sheet_ai(result["path"]), result["path"])   # 레거시 .ai는 영상을 못 담는다 — SVG 그대로

    def test_vworld_falls_back_to_esri_and_offline_is_empty(self):
        import review_map
        calls = []
        with patch.dict(os.environ, {"VWORLD_API_KEY": "TESTKEY"}), \
                patch.object(sheet_svg, "_fetch_tile", lambda url: calls.append(url) or (b"" if "vworld" in url else FAKE_TILE)):
            result = sheet_svg.write_sheets(make_data(), tempfile.mkdtemp(), [ID["aerial"]])[0]
        self.assertFalse(result["empty"])
        self.assertTrue(any("vworld" in u for u in calls) and any("arcgisonline" in u for u in calls))
        self.assertIn("Esri", open(result["path"], encoding="utf-8").read())   # 카드 출처도 받은 소스
        with patch.object(sheet_svg, "_fetch_tile", lambda url: b""):
            result = sheet_svg.write_sheets(make_data(), tempfile.mkdtemp(), [ID["aerial"]])[0]
        self.assertEqual((result["empty"], result["reason"]), (True, "영상 못 받음"))
        calls = []
        with patch.object(sheet_svg, "_fetch_tile", lambda url: calls.append(url) or b""):
            sheet_svg.write_sheets(make_data(), tempfile.mkdtemp(), [ID["aerial"]])
        self.assertLessEqual(len(calls), 2)   # 막힌 망 — 소스마다 한 장만 시도하고(시트·썸네일 공통) 타일마다 시간 초과를 기다리지 않는다
        self.assertIn(review_map.ESRI_AERIAL_URL.split("/")[2], review_map.get_tile_config()["abroad_aerial_url"])


class AxoSheetTest(unittest.TestCase):
    """입체 매스도 — 시점 축, 볼록 자르기, 벽 보임·그리는 순서, 시트·썸네일."""

    def test_axes_are_orthonormal_and_se_camera_is_southeast(self):
        right, up, toward = sheet_svg.get_axo_axes("se")
        dot = lambda a, b: sum(x * y for x, y in zip(a, b))
        for a, b in ((right, up), (right, toward), (up, toward)):
            self.assertAlmostEqual(dot(a, b), 0.0)
        for v in (right, up, toward):
            self.assertAlmostEqual(dot(v, v), 1.0)
        self.assertTrue(toward[0] > 0 > toward[1])   # 카메라가 남동쪽에서 북서쪽을 본다
        self.assertTrue(right[0] > 0 and right[1] > 0)   # 화면 오른쪽 = 북동

    def test_convex_clip(self):
        square = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        clipped = sheet_svg.get_convex_clipped_ring([(5.0, 5.0), (20.0, 5.0), (20.0, 8.0), (5.0, 8.0)], square)
        self.assertAlmostEqual(max(p[0] for p in clipped), 10.0)
        self.assertAlmostEqual(sheet_svg.get_ring_area(clipped), 15.0)
        self.assertEqual(sheet_svg.get_convex_clipped_ring([(20.0, 20.0), (30.0, 20.0), (30.0, 30.0)], square), [])

    def test_scene_walls_roof_and_painter_order(self):
        cx, cy = CENTER
        data = make_data()
        data.features, data.overlays, data.near_lots = [], [], []
        data.buildings = [_building(1, cx, cy - 100, height_m=10.0), _building(2, cx, cy + 100, height_m=20.0)]   # 남동 시점에서 북쪽(2)이 멀다
        scene = sheet_svg.get_axo_scene(data, "se", (273.0, 273.0))
        kinds = [kind for kind, _rings, _site in scene["faces"]]
        self.assertEqual((kinds[2], kinds[5], len(kinds)), ("roof", "roof", 6))   # 동마다 보이는 벽 둘(남·동) → 지붕
        self.assertEqual(set(kinds[:2]), {"wall_a", "wall_b"})   # 화면 오른쪽·왼쪽을 향한 벽은 다른 색
        far_roof, near_roof = scene["faces"][2][1][0], scene["faces"][5][1][0]
        self.assertLess(max(p[1] for p in far_roof), min(p[1] for p in near_roof))   # 먼(북쪽) 동을 먼저 — 종이에서 위
        self.assertEqual((scene["count"], sorted(scene["heights"])), (2, [10.0, 20.0]))
        self.assertTrue(scene["north"][0] > 0 > scene["north"][1])   # 남동 시점의 북쪽 = 화면 오른쪽 위

    def test_sheet_render_views_and_thumbnail(self):
        result = sheet_svg.write_sheets(make_data(style={"axo_view": "nw"}), tempfile.mkdtemp(), [ID["axo"]])[0]
        self.assertFalse(result["empty"])
        root = ET.parse(result["path"]).getroot()
        ids = _groups(root)
        self.assertTrue({"axo_ground", "theme", "labels", "scale_north"} <= set(ids), ids)
        self.assertNotIn("base_parcels", ids)   # 평면 지적·범위 밖 흐리기는 그리지 않는다
        self.assertIsNone(root.find(".//*[@id='mask']"))
        self.assertIn("평행 투상(축척 없음) · A3 · EPSG:5186", _texts(root, "info"))
        self.assertTrue(any(t.startswith("북서 등각 시점") for t in _texts(root, "card")))
        self.assertTrue(result["thumb"].startswith("data:image/png;base64,"))
        se_svg = sheet_svg.render_sheet(ID["axo"], make_data(style={"axo_view": "se"}))[0]
        self.assertNotEqual(open(result["path"], encoding="utf-8").read(), se_svg)   # 시점(도면 스타일)이 그림을 바꾼다


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


@unittest.skipUnless((FIXTURE_DIR / "seongsu_site.db").exists() and (FIXTURE_DIR / "seongsu_context.db").exists(), "fixture DB 없음")
class FixtureTest(unittest.TestCase):
    """context_builder.prepare(fixture) → SheetData → 16장. 지형은 합성 격자(Rhino 없음)."""

    def test_all_sheets_from_prepare(self):
        import context_builder
        request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": str(FIXTURE_DIR / "seongsu_site.db"),
                   "context_db": str(FIXTURE_DIR / "seongsu_context.db"), "options": {"radius": 500, "make_sheets": True}}
        prepared = context_builder.prepare(request)
        cx, cy = prepared.target_lots[0].min_x, prepared.target_lots[0].min_y
        tris = [_tri(cx + i * 50, cy + j * 50, 10 + i, 12 + j, 11) for i in range(-3, 3) for j in range(-3, 3)]
        data = sheet_svg.SheetData.from_prepared(prepared, tris)
        self.assertEqual(data.paper_mm, (420.0, 297.0))
        self.assertEqual(data.get_frame("side").scale, 5000)
        self.assertEqual(len(data.meta_lines), 5)
        results = sheet_svg.write_sheets(data, tempfile.mkdtemp())
        self.assertEqual(len(results), len(constants.SHEET_CATALOG))
        self.assertEqual([r["id"] for r in results if r["empty"]], [])
        for r in results:
            ET.parse(r["path"])   # 16장 전부 XML로 열린다
            self.assertLess(os.path.getsize(r["path"]), 3 * 1024 * 1024, r["name"])
        root = ET.parse(results[ID["floor"]]["path"]).getroot()
        self.assertTrue(any(t.startswith("높이 출처 대장 높이") for t in _texts(root, "card")))
        self.assertGreater(len(_theme_paths(results[ID["use"]]["path"])), 2000)   # 도면 안 건물 수천 동
        self.assertTrue(any((t or "").endswith("역") for t in _texts(ET.parse(results[ID["transit"]]["path"]).getroot(), "labels")))


if __name__ == "__main__":
    unittest.main()
