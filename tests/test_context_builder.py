"""context_builder — prepare·run(취소·오류 경로·응답 스키마)·preflight·get_progress_message + 높이 규칙·도엽 경계·context_db 질의·정합 샘플. fixture DB 2개로 Rhino 없이 돈다."""

import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants
import context_builder
import context_db
import dev_context_builder as builder
import non_rhino_utils
import site_prefs

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
HAS_FIXTURES = os.path.exists(SITE_DB) and os.path.exists(CONTEXT_DB)
TODAY = datetime.date(2026, 10, 7)
CENTER = (204764.0, 549052.0)          # 성수동2가 333-139 중심 (implementation_plan §0)
HOLE_PNU = "1120011400100130219"       # 성수동1가 13-219 — fixture 안 구멍 3개 필지(multipart 경고용)
ALIGN_TEST_DB = "/tmp/udt_ctx_test.db"  # dev_context_builder.py --sheets 37705072,37705073,37705082,37705083 --out 결과 (정합 샘플 포함)


def _request(**overrides):
    request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": SITE_DB, "context_db": CONTEXT_DB, "options": {"radius": 500, "shape": "buffer"}}   # buffer는 패널에서 뺐지만 엔진은 받는다(실측값이 이 형태 기준)
    options = overrides.pop("options", None)
    if options:
        request["options"].update(options)
    request.update(overrides)
    return request


def _row(**overrides):
    row = {"usability": "01000", "grnd_flr": 0, "height_raw": 0.0, "arch_area_sqm": 0.0,
           "footprint_area_sqm": 100.0, "ngii_kind": "", "ngii_use": "", "ngii_floors": 0}
    row.update(overrides)
    return row


class HeightRuleTest(unittest.TestCase):
    """docs/deliverables.md §A.4 — 규칙 번호 순서대로 하나씩."""

    def test_rule1_registered_height_wins(self):
        decided = builder.decide_height(_row(grnd_flr=3, height_raw=9.1))
        self.assertEqual((decided["height_m"], decided["height_src"], decided["height_grade"]), (9.1, "height", "A"))
        self.assertEqual((decided["grnd_flr"], decided["flr_src"]), (3, "grnd_flr"))

    def test_rule1_rejects_implausible_height_per_floor(self):
        # 3층에 60 m → 층당 20 m라 대장 높이를 버리고 층수 모델로
        decided = builder.decide_height(_row(grnd_flr=3, height_raw=60.0))
        self.assertEqual(decided["height_src"], "grnd_flr")
        self.assertEqual(decided["height_m"], round(2.4 + 2.4 * 3, 2))

    def test_rule3_topo_apartment_floors_override(self):
        # 대장 2층·수치지형도 아파트 15층 → 수치지형도 층수, 공동주택 모델
        decided = builder.decide_height(_row(usability="02000", grnd_flr=2, ngii_kind="아파트", ngii_floors=15))
        self.assertEqual((decided["grnd_flr"], decided["flr_src"], decided["height_src"], decided["height_grade"]),
                         (15, "topo", "topo_flr", "B"))
        self.assertEqual(decided["height_m"], round(1.1 + 2.8 * 15, 2))

    def test_rule4_floor_model_by_use(self):
        decided = builder.decide_height(_row(usability="14000", grnd_flr=10))
        self.assertEqual(decided["height_m"], round(1.0 + 3.4 * 10, 2))
        self.assertEqual(decided["height_grade"], "B")

    def test_rule5_topo_floors_when_no_registry(self):
        decided = builder.decide_height(_row(usability="", grnd_flr=0, ngii_use="근린생활시설", ngii_floors=4))
        self.assertEqual((decided["grnd_flr"], decided["flr_src"], decided["height_src"], decided["height_grade"]),
                         (4, "topo", "topo_flr", "C"))
        self.assertEqual(decided["height_m"], round(0.7 + 3.1 * 4, 2))

    def test_rule6_default(self):
        decided = builder.decide_height(_row(usability="", grnd_flr=0))
        self.assertEqual((decided["height_m"], decided["height_src"], decided["height_grade"]),
                         (constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"))

    def test_rule0_distrust_registry_when_arch_area_too_small(self):
        # 건축면적 30 < 발자국 100 × 0.5 → 대장 높이·층수 불신, 수치지형도 층수로, '!' 표시
        decided = builder.decide_height(_row(grnd_flr=20, height_raw=60.0, arch_area_sqm=30.0, ngii_floors=5))
        self.assertEqual(decided["attr_flag"], "!")
        self.assertTrue(decided["height_src"].endswith("!"))
        self.assertEqual((decided["grnd_flr"], decided["flr_src"]), (5, "topo"))

    def test_rule0b_suspect_downgrades_grade(self):
        # 건축면적 300 > 발자국 100 × 2 → 값은 쓰되 등급 한 단계 강등
        decided = builder.decide_height(_row(grnd_flr=3, height_raw=9.0, arch_area_sqm=300.0))
        self.assertEqual((decided["height_src"], decided["height_grade"], decided["attr_flag"]), ("height?", "B", "?"))

    def test_clamp(self):
        # 종교(0 + 4.2n)·1층 → 4.2 는 층당 2.5~8 안. 극단 모델은 없지만 함수 자체를 확인
        self.assertEqual(builder._model_height("06", 1), 4.2)
        self.assertEqual(builder._model_height("zz", 2), 1.5 + 2.8 * 2)


class SheetCodeTest(unittest.TestCase):
    def test_seongsu_sheet_bounds(self):
        # Seoungsu/make_basemap_L.py 프레임(127.025–127.075, 37.525–37.575)과 일치해야 한다
        left, bottom, right, top = non_rhino_utils.get_topo_sheet_bounds("37705072")
        self.assertAlmostEqual(left, 127.025, 6)
        self.assertAlmostEqual(top, 37.575, 6)
        self.assertAlmostEqual(right - left, 0.025, 9)
        self.assertAlmostEqual(non_rhino_utils.get_topo_sheet_bounds("37705083")[1], 37.525, 6)


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class ContextDbTest(unittest.TestCase):
    def test_load_around_seongsu_station(self):
        x, y = non_rhino_utils.get_tm_from_wgs84(127.0558, 37.5445)
        data = context_db.load((x - 300, y - 300, x + 300, y + 300), database_path=CONTEXT_DB)
        self.assertGreater(len(data.buildings), 500)
        self.assertTrue(all(b.height_m > 0 for b in data.buildings))
        self.assertTrue(data.get_features("terrain", "spot"))
        self.assertTrue(data.get_features("road", "surface"))
        self.assertEqual({b.height_grade for b in data.buildings} - set(constants.HEIGHT_GRADES), set())
        self.assertEqual(data.buildings[0].geometry["type"], "Polygon")

    def test_struct_spots_are_separated(self):
        counts = context_db.get_counts(CONTEXT_DB)["features"]
        self.assertIn("terrain/spot_struct", counts)
        self.assertGreater(counts["terrain/spot"], counts["terrain/spot_struct"])

    def test_minor_filter_matches_between_load_and_count(self):
        bounds = (CENTER[0] - 500, CENTER[1] - 500, CENTER[0] + 500, CENTER[1] + 500)
        with_minor = context_db.load_buildings_in_bounds(bounds, CONTEXT_DB, include_minor=True)
        without = context_db.load_buildings_in_bounds(bounds, CONTEXT_DB, include_minor=False)
        self.assertGreater(len(with_minor), len(without))
        self.assertEqual(context_db.count_in_bounds(bounds, CONTEXT_DB)["buildings"], len(without))
        self.assertEqual(context_db.count_in_bounds(bounds, CONTEXT_DB, include_minor=True)["buildings"], len(with_minor))


class SourceHelperTest(unittest.TestCase):
    def test_level_yellow_needs_newer_version(self):
        self.assertEqual(context_builder._get_level(4.0, (3, 5), None), "ok")
        self.assertEqual(context_builder._get_level(4.0, (3, 5), "2026-09-09"), "warn")
        self.assertEqual(context_builder._get_level(6.0, (3, 5), None), "danger")
        self.assertEqual(context_builder._get_level(None, (3, 5), None), "ok")

    def test_months_since(self):
        self.assertEqual(context_builder._get_months_since("2026-05-13", TODAY), 4.8)
        self.assertEqual(context_builder._get_months_since("202602", TODAY), 8.2)
        self.assertIsNone(context_builder._get_months_since("", TODAY))

    def test_direction(self):
        self.assertEqual(context_builder._get_direction(10, 0), "동")
        self.assertEqual(context_builder._get_direction(0, 10), "북")
        self.assertEqual(context_builder._get_direction(-10, -10), "남서")

    def test_source_warnings_codes(self):
        sources = [{"id": "lot", "label": "필지", "name": "n", "date": "2025-01-01", "age_months": 20.0, "level": "danger", "newer_date": None},
                   {"id": "building", "label": "건물", "level": "missing"}, {"id": "terrain", "label": "지형", "level": "missing"},
                   {"id": "api", "level": "missing"}]
        codes = [w["code"] for w in context_builder.get_source_warnings(sources)]
        self.assertEqual(codes, ["stale_lot", "no_context_db"])   # 키는 선택 — 없어도 경고하지 않는다


class PrefsTest(unittest.TestCase):
    """site_prefs — test_site_preflight.py에서 옮김."""

    def test_options_and_recent_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prefs.json")
            options = site_prefs.get_options(path)
            self.assertEqual(options["radius"], constants.PANEL_DEFAULT_OPTIONS["radius"])
            saved = site_prefs.save_options({"radius": 300, "unknown_key": 1}, path)
            self.assertEqual(saved["radius"], 300)
            self.assertNotIn("unknown_key", saved)
            site_prefs.add_recent(["b", "a"], "라벨", 12.34, "2026-10-07", path)
            site_prefs.add_recent(["a", "b"], "라벨2", 12.34, "2026-10-08", path)   # 같은 묶음 → 하나
            recent = site_prefs.get_recent(path)
            self.assertEqual(len(recent), 1)
            self.assertEqual(recent[0]["label"], "라벨2")
            self.assertEqual(site_prefs.get_options(path)["radius"], 300)   # recent 추가가 옵션을 지우지 않는다
            with open(path, encoding="utf-8") as f:
                self.assertIn("options", json.load(f))

    def test_style_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(site_prefs.list_styles(tmp), [])
            styles = site_prefs.save_style("OO건축/표준", {"preset": "mono", "site": "#0057FF"}, tmp)   # 경로 문자는 지운다
            self.assertEqual([s["name"] for s in styles], ["OO건축표준"])
            self.assertEqual(styles[0]["style"]["site"], "#0057FF")
            with open(os.path.join(tmp, "broken.json"), "w") as handle:
                handle.write("{not json")
            self.assertEqual(len(site_prefs.list_styles(tmp)), 1)   # 깨진 파일은 건너뛴다
            with self.assertRaises(ValueError):
                site_prefs.save_style("  ", {}, tmp)


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class PrepareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls = []
        cls.prepared = context_builder.prepare(_request(), lambda phase, fraction, text: cls.calls.append((phase, fraction)) or True, today=TODAY)

    def test_origin_snapped_to_100m_and_center(self):
        p = self.prepared
        self.assertEqual(p.origin, (204700.0, 549000.0))
        self.assertFalse(p.origin_reused)
        cx, cy = context_builder.get_lots_center(p.target_lots)
        self.assertLess(abs(cx - CENTER[0]), 10.0)
        self.assertLess(abs(cy - CENTER[1]), 10.0)
        self.assertEqual(p.lot_name, "성수동2가_333-139")
        self.assertTrue(p.result_dir.endswith(os.path.join("20261007", "성수동2가_333-139")))

    def test_doc_origin_reused(self):
        p = context_builder.prepare(_request(doc_origin=[204000.0, 548500.0], options={"radius": 100}), today=TODAY)
        self.assertEqual(p.origin, (204000.0, 548500.0))
        self.assertTrue(p.origin_reused)
        self.assertIn("origin_reused", [w["code"] for w in p.warnings])

    def test_doc_origin_too_far_is_error(self):
        with self.assertRaises(ValueError):
            context_builder.prepare(_request(doc_origin=[204764.0 + 25000.0, 549052.0], options={"radius": 100}), today=TODAY)

    def test_validation_errors(self):
        with self.assertRaises(ValueError):
            context_builder.prepare(_request(options={"radius": 5}), today=TODAY)
        with self.assertRaises(ValueError):
            context_builder.prepare(_request(options={"scales": [2500]}), today=TODAY)
        with self.assertRaises(ValueError):
            context_builder.prepare(_request(options={"paper_mm": [0, 594]}), today=TODAY)
        with self.assertRaises(ValueError):
            context_builder.prepare(_request(pnus=["123"]), today=TODAY)

    def test_extent_shapes_and_bounds_order(self):
        for shape, expected in (("rect", 4), ("circle", constants.EXTENT_CIRCLE_SEGMENTS)):
            p = context_builder.prepare(_request(options={"radius": 300, "shape": shape, "scales": [1000]}), today=TODAY)
            self.assertEqual(len(p.extent_ring), expected, shape)
            self.assertEqual(p.shape, shape)
        p = self.prepared
        self.assertEqual(p.shape, "buffer")
        self.assertGreater(len(p.extent_ring), 4)
        self.assertLess(p.bounds[0], p.bounds[2])
        self.assertLess(p.bounds[1], p.bounds[3])
        # bounds = 범위 bbox ∪ 최대 프레임 bbox + 20 m (A3 1:5000 = 2,100×1,485 m가 반경 500 m 범위보다 크다)
        frame = p.frame_bounds[5000]
        self.assertAlmostEqual(p.bounds[0], frame[0] - constants.QUERY_MARGIN, 3)
        self.assertAlmostEqual(p.bounds[2], frame[2] + constants.QUERY_MARGIN, 3)
        self.assertAlmostEqual(frame[2] - frame[0], 2100.0, 3)
        extent = non_rhino_utils.get_bbox(p.extent_ring)
        self.assertTrue(p.bounds[0] <= extent[0] and p.bounds[2] >= extent[2])

    def test_near_lots_not_truncated_at_1km(self):
        p = context_builder.prepare(_request(options={"radius": 1000, "scales": [1000]}), today=TODAY)
        self.assertGreater(len(p.near_lots), 5000)
        self.assertFalse(p.lots_truncated)
        self.assertNotIn(constants.TEST_CONTEXT_PNU, {lot.pnu for lot in p.near_lots})

    def test_progress_callback_query_0_to_1(self):
        self.assertEqual(self.calls[0], ("query", 0.0))
        self.assertEqual(self.calls[-1], ("query", 1.0))
        self.assertTrue(all(phase == "query" for phase, _ in self.calls))

    def test_cancel_on_second_call(self):
        count = [0]

        def progress(phase, fraction, text):
            count[0] += 1
            return count[0] < 2

        with self.assertRaises(context_builder.Cancelled):
            context_builder.prepare(_request(), progress, today=TODAY)

    def test_prepared_keys_stats_and_meta(self):
        p = self.prepared
        for name in ("request", "lot_name", "target_lots", "near_lots", "origin", "origin_reused", "radius", "shape", "extent_ring",
                     "scales", "bounds", "frame_bounds", "context", "align_samples", "overlays", "sources", "meta", "stats", "warnings",
                     "skipped_phases", "result_dir"):
            self.assertTrue(hasattr(p, name), name)
        self.assertEqual(set(p.stats), {"height_src", "height_grade", "grade_ab", "buildings", "lots", "sheets", "sheets_needed", "align", "mismatch_count"})
        self.assertAlmostEqual(sum(p.stats["height_src"].values()), 1.0, 2)
        self.assertGreater(p.stats["buildings"], 3000)                      # 실측 ±520 m 3,539동(전체 DB) — fixture에서 보충 무벽 제외 3,454
        self.assertGreater(len(p.buildings), p.stats["buildings"])          # 프레임 bbox까지 읽었다
        self.assertEqual(p.stats["sheets"], ["37705082", "37705083"])
        # 2026-10-07 23:28 재빌드 fixture: 범위 안 정합 샘플 13,243점(서울 전체 중앙값 1.15 m·p90 3.78 m)
        self.assertGreater(p.stats["align"]["n"], 1000)
        self.assertFalse(p.stats["align"]["low_sample"])
        self.assertTrue(0.5 <= p.stats["align"]["median"] <= 2.5, p.stats["align"])
        self.assertTrue(2.0 <= p.stats["align"]["p90"] <= 6.0, p.stats["align"])
        self.assertEqual(len(p.meta["meta_lines"]), 5)
        self.assertIn("도엽 37705082 외 1", p.meta["meta_lines"][0])
        self.assertEqual(p.meta["dates"]["building"], "2026-09-06")
        self.assertEqual([s["id"] for s in p.sources], ["lot", "building", "terrain", "api", "upis"])
        self.assertEqual(p.skipped_phases, {"refresh", "import"})
        self.assertEqual(p.request["options"]["radius"], 500)
        self.assertEqual(p.request["options"]["paper"], "A3")
        for w in p.warnings:
            self.assertEqual(set(w), {"level", "code", "text", "detail", "action", "center"})

    def test_options_off_skip_phases_and_minor_buildings(self):
        p = context_builder.prepare(_request(options={"radius": 300, "scales": [1000], "make_basemap": False, "make_sheets": False,
                                                      "make_tables": False, "include_minor_buildings": True}), today=TODAY)
        self.assertEqual(p.skipped_phases, {"refresh", "import", "basemap", "sheets", "tables"})
        self.assertEqual(context_builder.get_skipped_phases(p.request["options"]), p.skipped_phases)
        self.assertEqual(context_builder.get_skipped_phases(constants.PANEL_DEFAULT_OPTIONS), {"refresh", "import"})
        q = context_builder.prepare(_request(options={"radius": 300, "scales": [1000]}), today=TODAY)
        self.assertGreater(len(p.buildings), len(q.buildings))

    def test_multipart_warning_for_hole_parcel(self):
        p = context_builder.prepare(_request(pnus=[HOLE_PNU], options={"radius": 100, "scales": [1000]}), today=TODAY)
        multipart = [w for w in p.warnings if w["code"] == "multipart"]
        self.assertEqual(len(multipart), 1)
        self.assertIn("구멍 3개", multipart[0]["text"])
        self.assertEqual(len(multipart[0]["center"]), 2)

    def test_merged_lots_name(self):
        p = context_builder.prepare(_request(pnus=[constants.TEST_CONTEXT_PNU_SMALL, "1120011500103140006"], options={"radius": 100, "scales": [1000]}), today=TODAY)
        self.assertEqual(p.lot_name, "성수동2가_315-1외1")
        self.assertEqual(len(p.target_lots), 2)

    def test_align_stats(self):
        from types import SimpleNamespace as NS
        samples = [NS(value=float(v), attrs={"dx": 0.5, "dy": -0.2}) for v in range(1, 11)]
        stats = context_builder._get_align_stats(samples)
        self.assertEqual((stats["median"], stats["n"], stats["low_sample"], stats["dx"]), (5.5, 10, True, 0.5))
        self.assertAlmostEqual(stats["p90"], 9.9, 1)


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class PreflightTest(unittest.TestCase):
    def test_keys_and_roles(self):
        result = context_builder.preflight(_request(options={"radius": 500, "scales": [3000]}), today=TODAY)
        self.assertEqual(set(result), {"sources", "extent_geojson", "estimate", "empty_sheets", "warnings", "bounds", "center"})
        self.assertEqual(set(result["estimate"]), {"buildings", "lots", "topo_have", "topo_total", "seconds", "mb", "note", "pending_mb"})
        self.assertGreater(result["estimate"]["buildings"], 1000)
        self.assertEqual(result["estimate"]["topo_total"], result["estimate"]["topo_have"] + len(
            next(s for s in result["sources"] if s["id"] == "terrain")["coverage"]["missing"]))
        roles = [f["properties"]["role"] for f in result["extent_geojson"]["features"]]
        self.assertEqual(roles.count("extent"), 1)
        self.assertEqual(roles.count("frame"), 1)
        self.assertIn("topo_sheet", roles)
        self.assertEqual([s["id"] for s in result["sources"]], ["lot", "building", "terrain", "api"])
        self.assertEqual(result["empty_sheets"], [])
        self.assertEqual(result["estimate"]["note"], "")
        for warning in result["warnings"]:
            self.assertIn(warning["level"], ("info", "warn", "danger"))
            self.assertTrue(warning["code"] and warning["text"])
        # 미리보기 범위 bbox = prepare의 범위 bbox (링 정의가 하나)
        prepared = context_builder.prepare(_request(options={"radius": 500, "scales": [3000]}), today=TODAY)
        for a, b in zip(result["bounds"], non_rhino_utils.get_bbox(prepared.extent_ring)):
            self.assertAlmostEqual(a, b, 6)
        self.assertEqual(result["estimate"]["buildings"], prepared.stats["buildings"])

    def test_rect_circle_and_5000_warning(self):
        rect = context_builder.preflight(_request(options={"radius": 300, "shape": "rect", "scales": [1000]}), today=TODAY)
        circle = context_builder.preflight(_request(options={"radius": 300, "shape": "circle", "scales": [1000, 5000]}), today=TODAY)
        self.assertEqual(len(rect["extent_geojson"]["features"][0]["geometry"]["coordinates"][0]), 5)
        self.assertGreater(len(circle["extent_geojson"]["features"][0]["geometry"]["coordinates"][0]), 60)
        self.assertEqual([f["properties"]["scale"] for f in circle["extent_geojson"]["features"] if f["properties"]["role"] == "frame"], [1000, 5000])
        self.assertIn("slow_frame", [w["code"] for w in circle["warnings"]])
        self.assertIn("수십 초", circle["estimate"]["note"])
        self.assertIn("frame_over", [w["code"] for w in circle["warnings"]])

    def test_radius_is_clamped_not_rejected(self):
        result = context_builder.preflight(_request(options={"radius": 5, "scales": [1000]}), today=TODAY)
        self.assertEqual(result["extent_geojson"]["features"][0]["properties"]["radius"], constants.RADIUS_MIN)


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class CancelTest(unittest.TestCase):
    """run — 2번째 콜백 False → prepare 안에서 Cancelled → ok=false·cancelled=true·error.code=cancelled. Rhino 없이 돈다(베이크 전 취소)."""

    def test_cancel_on_second_call(self):
        calls = []

        def progress(phase, fraction, text):
            calls.append((phase, fraction))
            return len(calls) < 2

        with tempfile.TemporaryDirectory() as tmp:
            response = context_builder.run(_request(result_root=tmp), progress, doc=None)
            self.assertEqual(set(response), set(context_builder.RESPONSE_KEYS))
            self.assertFalse(response["ok"])
            self.assertTrue(response["cancelled"])
            self.assertEqual(response["error"]["code"], "cancelled")
            self.assertIn("cancelled at query", response["error"]["detail"])
            self.assertEqual(calls, [("query", 0.0), ("query", 0.3)])
            self.assertEqual(response["dir"], "")                       # prepare가 끝나기 전이라 폴더 없음
            self.assertEqual(os.listdir(tmp), [])
            self.assertIsInstance(response["elapsed_s"], float)


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class ResponseSchemaTest(unittest.TestCase):
    """run 응답 dict 키 집합(code_map §4.3) — ok=false 경로도 키 전부. Rhino 없이는 prepare 뒤 Rhino import에서 exception으로 끝난다."""

    def test_keys_after_prepare_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            response = context_builder.run(_request(result_root=tmp), lambda *a: True, doc=None)
            self.assertEqual(set(response), set(context_builder.RESPONSE_KEYS))
            self.assertFalse(response["ok"])
            self.assertFalse(response["cancelled"])
            self.assertEqual(response["error"]["code"], "exception")           # Rhino 모듈 없음
            self.assertIn("Rhino", response["error"]["detail"])
            self.assertEqual(response["lot_name"], "성수동2가_333-139")
            self.assertTrue(response["dir"].startswith(tmp))
            self.assertEqual(set(response["context"]), {"path", "layers", "buildings", "lots", "demolished", "tin_points", "origin",
                                                        "origin_reused", "placement", "doc_origin", "model_unit", "imported", "import_text", "dwg"})
            self.assertEqual(set(response["basemap"]), {"ready", "paper", "layers", "scales", "exported"})
            self.assertEqual(set(response["quality"]), {"height_src", "align", "skipped", "mismatch_count", "dates"})
            self.assertAlmostEqual(sum(response["quality"]["height_src"].values()), 1.0, 2)
            self.assertEqual(response["quality"]["dates"]["building"], "2026-09-06")
            self.assertEqual(response["qa_geojson"], {"type": "FeatureCollection", "features": []})
            self.assertEqual(response["options"]["radius"], 500)
            self.assertEqual(response["options"]["paper"], "A3")
            for w in response["warnings"]:
                self.assertEqual(set(w), {"level", "code", "text", "detail", "action", "center"})
            # 결과 폴더 result/<날짜>/<lot_name>/ 가 생기고 log.txt에 오류가 남는다 → files 목록
            self.assertEqual([f["name"] for f in response["files"]], [constants.RESULT_LOG_FILE_NAME])
            with open(os.path.join(response["dir"], constants.RESULT_LOG_FILE_NAME), encoding="utf-8") as f:
                log = f.read()
            self.assertIn("FAILED 성수동2가_333-139", log)
            self.assertIn("오류 exception", log)
            self.assertFalse(os.path.exists(os.path.join(response["dir"], constants.CONTEXT_META_FILE_NAME)))   # 실패면 context.json 없음

    def test_domain_error_codes(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = context_builder.run(_request(result_root=tmp, pnus=["1120011500109999999"]), doc=None)
            self.assertEqual((r["ok"], r["error"]["code"]), (False, "no_lots"))
            r = context_builder.run(_request(result_root=tmp, context_db=os.path.join(tmp, "none.db")), doc=None)
            self.assertEqual(r["error"]["code"], "context_db_missing")
            r = context_builder.run(_request(result_root=tmp, doc_origin=[204764.0 + 25000.0, 549052.0]), doc=None)
            self.assertEqual(r["error"]["code"], "origin_mismatch")
            self.assertIn("다른 지역 문서", r["error"]["title"])
            r = context_builder.run(_request(result_root=tmp, options={"radius": 5}), doc=None)
            self.assertEqual(r["error"]["code"], "exception")                # 반경 검증은 코드 목록 밖 → exception + 한국어 메시지
            self.assertIn("반경", r["error"]["title"])
            self.assertEqual(os.listdir(tmp), [])                           # prepare 전 실패는 폴더를 만들지 않는다

    def test_reset_result_dir_keeps_ai_and_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("context.3dm", "context.json", "basemap_3000.ai", "log.txt"):
                open(os.path.join(tmp, name), "w").close()
            os.makedirs(os.path.join(tmp, "sheets"))
            os.makedirs(os.path.join(tmp, "tables"))
            context_builder._reset_result_dir(tmp)
            self.assertEqual(sorted(os.listdir(tmp)), ["basemap_3000.ai", "log.txt"])


class AlignTest(unittest.TestCase):
    """정합 샘플 — dev_context_builder.get_align_samples(합성) + 4도엽 부분 빌드 DB(/tmp/udt_ctx_test.db)의 통계."""

    def test_synthetic_offset_squares(self):
        import shapely
        cad, topo = [shapely.box(0, 0, 100, 100)], [shapely.box(1, 0, 101, 100)]   # topo가 동쪽으로 1 m
        samples = builder.get_align_samples(cad, topo)
        self.assertEqual(len(samples), 41)                                  # 둘레 400 m / 10 m + 1(닫힘)
        self.assertEqual(sorted({s[2] for s in samples}), [0.0, 1.0])        # 남북 변 위 점은 0, 동서 변 점은 1 m
        west = [s for s in samples if s[0] == 0.0 and 0 < s[1] < 100]
        self.assertTrue(west and all(s[3] == 1.0 and s[4] == 0.0 for s in west))   # dx·dy = cad → topo 벡터
        self.assertEqual(builder.get_align_samples(cad, topo, seam=shapely.box(-1, -1, 101, 101)), [])   # seam 안 점 제외
        self.assertEqual(builder.get_align_samples(cad, topo, max_dist=0.5), [s for s in samples if s[2] == 0.0])
        self.assertEqual(builder.get_align_samples([], topo), [])

    @unittest.skipUnless(HAS_FIXTURES and os.path.exists(ALIGN_TEST_DB), "%s 없음 (dev_context_builder.py --sheets … --out)" % ALIGN_TEST_DB)
    def test_seongsu_four_sheets_stats(self):
        import sqlite3
        with sqlite3.connect(ALIGN_TEST_DB) as con:
            rows = con.execute("SELECT sheet, COUNT(*), MIN(value), MAX(value) FROM features WHERE theme='qa' AND kind='align_sample' GROUP BY sheet").fetchall()
        self.assertEqual([r[0] for r in rows], ["37705072", "37705073", "37705082", "37705083"])
        self.assertTrue(all(r[1] > 1000 and 0.0 <= r[2] and r[3] <= constants.ALIGN_MAX_DIST for r in rows), rows)
        p = context_builder.prepare(_request(context_db=ALIGN_TEST_DB, options={"radius": 500, "scales": [3000]}), today=TODAY)
        align = p.stats["align"]
        self.assertGreater(align["n"], constants.ALIGN_LOW_SAMPLE)
        self.assertFalse(align["low_sample"])
        self.assertTrue(0.5 <= align["median"] <= 2.5, align)                 # 08정합 실측 중앙값 1.2 m
        self.assertTrue(align["median"] < align["p90"] <= 8.0, align)         # p90 3.9 m
        self.assertIn("정합 오차 중앙값", p.meta["meta_lines"][3])


class StyleRedrawTest(unittest.TestCase):
    """패널 '도면 스타일' — 미리보기(파일 안 씀)·적용(시트·.ai 다시 쓰기, context.json options.style)."""

    def test_sheet_ids_keep_catalog_order_and_drop_unknown(self):
        self.assertEqual(context_builder.get_sheet_ids({"sheet_ids": [11, 0, 99, "x"]}), [0, 11])
        self.assertEqual(context_builder.get_sheet_ids({}), [sheet_id for sheet_id, *_ in constants.SHEET_CATALOG])

    @unittest.skipUnless(HAS_FIXTURES, "fixture DB 없음")
    def test_preview_and_apply(self):
        import basemap_ai
        import context_report
        import sheet_svg
        with tempfile.TemporaryDirectory() as tmp:
            prepared = context_builder.prepare(_request(options={"radius": 300, "shape": "circle"}))
            data = sheet_svg.SheetData.from_prepared(prepared, [])
            ids = [0, constants.SHEET_IDS["floor"], constants.SHEET_IDS["elev"]]
            sheets = sheet_svg.write_sheets(data, os.path.join(tmp, constants.RESULT_SHEETS_DIRNAME), ids)
            basemap_ai.write_basemap(prepared, 5000, tmp)
            context_report.write_context_json(prepared, {"sheets": sheets}, tmp)
            keep = {"dir": tmp, "data": data, "prepared": prepared}
            preview = context_builder.preview_sheet(tmp, 0, {"preset": "mono"}, keep)
            self.assertIn('fill="%s"' % constants.STYLE_PRESETS["mono"]["site"], preview["svg"])
            self.assertNotIn(' id="map"', preview["svg"])   # 패널의 #map(Leaflet)과 겹치지 않는다
            self.assertIn('clip-path="url(#pv_map_clip)"', preview["svg"])
            before = open(sheets[0]["path"], encoding="utf-8").read()
            self.assertNotIn("style mono", before)   # 미리보기는 파일을 건드리지 않는다
            result = context_builder.apply_style(tmp, {"preset": "mono", "layout": "bottom"}, keep)
            self.assertEqual([s["id"] for s in result["sheets"]], ids)
            self.assertEqual(result["kept"], [constants.SHEET_IDS["elev"]])   # 지형 삼각형이 없으면 지형 시트는 그대로 둔다
            self.assertIn("style mono", open(sheets[0]["path"], encoding="utf-8").read())
            self.assertEqual(len(result["basemaps"]), 1)
            with open(os.path.join(tmp, constants.CONTEXT_META_FILE_NAME), encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["options"]["style"], {"preset": "mono", "layout": "bottom"})


class ProgressMessageTest(unittest.TestCase):
    def test_percent_with_skipped(self):
        skipped = {"refresh", "import"}                         # 분모 100 − 15 = 85
        msg = context_builder.get_progress_message("query", 1.0, "조회 끝", skipped)
        self.assertEqual(msg["percent"], 18)                    # 15/85
        self.assertEqual(msg["phase_status"]["refresh"], "skipped")
        self.assertEqual(msg["phase_detail"], {"query": "조회 끝"})
        msg = context_builder.get_progress_message("terrain", 0.5, "TIN", skipped, {"query": "조회 끝"})
        self.assertEqual(msg["percent"], 32)                    # (15 + 12.5)/85
        self.assertEqual(msg["phase_status"]["query"], "done")
        self.assertEqual(msg["phase_status"]["terrain"], "running")
        self.assertEqual(msg["phase_status"]["write_3dm"], "pending")
        self.assertEqual(msg["phase_detail"], {"query": "조회 끝", "terrain": "TIN"})

    def test_done_failed_and_bad_phase(self):
        done = context_builder.get_progress_message("tables", 1.0, "", {"import"}, state="done")
        self.assertEqual(done["percent"], 100)
        self.assertEqual(set(done["phase_status"].values()), {"done", "skipped"})
        failed = context_builder.get_progress_message("basemap", 0.2, "", (), state="failed", error={"code": "export_failed"})
        self.assertEqual(failed["phase_status"]["basemap"], "failed")
        self.assertEqual(failed["error"]["code"], "export_failed")
        self.assertEqual(context_builder.get_progress_message("query", None, "", ())["percent"], 0)
        with self.assertRaises(ValueError):
            context_builder.get_progress_message("bake", 0.0, "", ())


if __name__ == "__main__":
    unittest.main()
