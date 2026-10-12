"""cmd_site 조립 함수가 만든 init_state·lot_state·preflight_result·progress·done 샘플이 docs/panel_ui.md 키 집합을 갖는지. fixture DB 2개로 Rhino 없이 돈다."""

import datetime
import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants   # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
HAS_FIXTURES = os.path.exists(SITE_DB) and os.path.exists(CONTEXT_DB)
TODAY = datetime.date(2026, 10, 7)
HOLE_PNU = "1120011400100130219"   # 성수동1가 13-219 — 구멍 3개(test_context_builder와 같은 필지)

# docs/panel_ui.md 푸시 정의의 키 집합
INIT_KEYS = {"type", "version", "blocked", "paths", "generator", "can_download", "sources", "warnings", "tile", "map", "options", "modes", "recent", "sheet_catalog"}
SOURCE_KEYS = {"id", "label", "name", "date", "age_months", "level", "newer_date", "text"}
SEARCH_KEYS = {"type", "query", "seq", "matches", "message"}
MATCH_KEYS = {"pnu", "address", "jibun", "land_category", "area", "center"}
LOT_STATE_KEYS = {"type", "lots", "total_area", "lot_name", "center", "target_geojson", "warnings"}
LOT_KEYS = {"pnu", "address", "jibun", "land_category", "area", "warn"}
PREFLIGHT_KEYS = {"type", "seq", "sources", "extent_geojson", "estimate", "empty_sheets", "warnings"}
ESTIMATE_KEYS = {"buildings", "lots", "topo_have", "topo_total", "seconds", "mb"}
PROGRESS_KEYS = {"type", "state", "phase", "phase_status", "phase_detail", "percent"}
DONE_KEYS = {"type", "dir", "lot_name", "elapsed_s", "options", "context", "basemap", "sheets", "tables", "files", "warnings", "quality", "qa_geojson"}
CONTEXT_KEYS = {"path", "layers", "buildings", "lots", "demolished", "tin_points", "origin", "imported", "import_text"}
WARNING_KEYS = {"level", "code", "text", "detail", "action", "center"}


def _load_cmd_site():
    # Rhino 모듈이 없으니 import 가드로 조립 함수만 올라오고 패널은 뜨지 않는다
    spec = importlib.util.spec_from_file_location("cmd_site_under_test", SCRIPTS_DIR / "cmd_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cmd_site = _load_cmd_site()


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다")
class InitStateTest(unittest.TestCase):
    def test_keys_and_fixed_values(self):
        state = cmd_site.get_init_state(SITE_DB, CONTEXT_DB, TODAY)
        self.assertEqual(set(state), INIT_KEYS)
        self.assertFalse(state["blocked"])
        self.assertEqual(state["generator"], {"ok": True, "python": "Rhino CPython", "text": "Rhino 내장"})
        self.assertEqual([s["id"] for s in state["sources"]], ["lot", "building", "terrain", "api"])
        for source in state["sources"]:
            self.assertTrue(SOURCE_KEYS <= set(source), source)
        self.assertIn("keys", state["sources"][3])
        self.assertEqual(set(state["paths"]), {"root", "lot_db", "context_db", "env", "install_doc"})
        self.assertEqual(set(state["options"]), set(constants.PANEL_DEFAULT_OPTIONS))
        self.assertEqual([c["id"] for c in state["sheet_catalog"]], list(range(1, 14)))
        self.assertEqual(state["sheet_catalog"][11]["needs"], "terrain")
        self.assertEqual(set(state["tile"]), {"url", "fallback_url", "attribution"})
        for warning in state["warnings"]:
            self.assertEqual(set(warning), WARNING_KEYS)

    def test_blocked_when_lot_db_missing(self):
        state = cmd_site.get_init_state("/nonexistent/seoul_site.db", CONTEXT_DB, TODAY)
        self.assertTrue(state["blocked"])
        self.assertEqual(state["sources"][0]["level"], "missing")


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다")
class SearchAndLotStateTest(unittest.TestCase):
    def test_search_result_keys(self):
        result = cmd_site.get_search_result("성수동2가 333-139", SITE_DB)
        self.assertEqual(set(result), SEARCH_KEYS)
        self.assertEqual(len(result["matches"]), 1)
        match = result["matches"][0]
        self.assertEqual(set(match), MATCH_KEYS)
        self.assertEqual(match["pnu"], constants.TEST_CONTEXT_PNU)
        self.assertEqual(match["jibun"], "333-139")
        self.assertEqual(len(match["center"]), 2)

    def test_search_no_match_message(self):
        result = cmd_site.get_search_result("없는동 9999-9999", SITE_DB)
        self.assertEqual(result["matches"], [])
        self.assertIn("찾지 못했습니다", result["message"])

    def test_lot_state_single(self):
        state = cmd_site.get_lot_state([constants.TEST_CONTEXT_PNU], SITE_DB)
        self.assertEqual(set(state), LOT_STATE_KEYS)
        self.assertEqual(set(state["lots"][0]), LOT_KEYS)
        self.assertIsNone(state["lots"][0]["warn"])
        self.assertEqual(state["lot_name"], "성수동2가_333-139")
        self.assertAlmostEqual(state["total_area"], 5586.0, delta=1.0)
        roles = [f["properties"]["role"] for f in state["target_geojson"]["features"]]
        self.assertEqual(roles, ["lot", "target"])
        self.assertEqual(state["target_geojson"]["features"][0]["properties"]["jibun"], "333-139")
        self.assertEqual(state["target_geojson"]["features"][1]["geometry"]["type"], "MultiPolygon")
        lng, lat = state["center"]
        self.assertTrue(127.0 < lng < 127.1 and 37.5 < lat < 37.6, state["center"])

    def test_lot_state_merged_hole_warning_and_empty(self):
        state = cmd_site.get_lot_state([constants.TEST_CONTEXT_PNU, HOLE_PNU], SITE_DB)
        self.assertEqual(state["lot_name"], "성수동2가_333-139외1")
        self.assertEqual([l["warn"] for l in state["lots"]], [None, "hole"])
        self.assertEqual([w["code"] for w in state["warnings"]], ["multipart"])
        self.assertEqual(set(state["warnings"][0]), WARNING_KEYS)
        self.assertEqual(len(state["target_geojson"]["features"]), 3)
        empty = cmd_site.get_lot_state([], SITE_DB)
        self.assertEqual(set(empty), LOT_STATE_KEYS)
        self.assertEqual((empty["lots"], empty["total_area"], empty["target_geojson"]["features"]), ([], 0.0, []))

    def test_map_lots_echoes_seq(self):
        state = cmd_site.get_map_lots([127.054, 37.543, 127.056, 37.545], 17, SITE_DB)
        self.assertEqual(set(state), {"type", "seq", "geojson", "truncated"})
        self.assertEqual(state["seq"], 17)
        self.assertGreater(len(state["geojson"]["features"]), 0)


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다")
class PreflightResultTest(unittest.TestCase):
    MSG = {"pnus": [constants.TEST_CONTEXT_PNU], "radius": 500, "shape": "buffer", "paper": "A1", "paper_mm": [841, 594], "scales": [3000], "seq": 5}

    def test_keys_and_seq(self):
        result = cmd_site.get_preflight_result(self.MSG, SITE_DB, CONTEXT_DB, TODAY)
        self.assertTrue(PREFLIGHT_KEYS <= set(result))
        self.assertEqual((result["type"], result["seq"]), ("preflight_result", 5))
        self.assertTrue(ESTIMATE_KEYS <= set(result["estimate"]))
        self.assertIn("coverage", result["sources"][2])
        roles = {f["properties"]["role"] for f in result["extent_geojson"]["features"]}
        self.assertEqual(roles, {"extent", "topo_sheet", "frame"})

    def test_memo_key_includes_paper_mm_and_scales(self):
        key = cmd_site.get_preflight_key(self.MSG)
        self.assertEqual(key, ('{"mode": "lots", "pnus": ["%s"]}' % constants.TEST_CONTEXT_PNU, 500, "buffer", "A1", (841, 594), (3000,)))
        self.assertNotEqual(key, cmd_site.get_preflight_key(dict(self.MSG, paper_mm=[594, 841])))
        self.assertNotEqual(key, cmd_site.get_preflight_key(dict(self.MSG, scales=[1000, 3000])))
        self.assertEqual(key, cmd_site.get_preflight_key(dict(self.MSG, seq=99)))   # seq는 키가 아니다


class ProgressTest(unittest.TestCase):
    def test_skipped_details_and_running_message(self):
        import context_builder
        skipped, details = cmd_site.get_skipped_details({"make_basemap": False})
        self.assertEqual(skipped, {"refresh", "import", "basemap"})
        self.assertEqual(details["import"], "건너뜀 — 베이크로 대체")
        self.assertEqual(details["refresh"], "건너뜀 — v1 미구현")
        self.assertEqual(details["basemap"], "건너뜀 — 옵션")
        self.assertNotIn("basemap", cmd_site.get_skipped_details({})[0])
        message = context_builder.get_progress_message("terrain", 0.5, "TIN", skipped, details)
        self.assertEqual(set(message), PROGRESS_KEYS)
        self.assertEqual(message["phase_status"]["import"], "skipped")
        self.assertEqual(message["phase_detail"]["import"], "건너뜀 — 베이크로 대체")
        self.assertEqual(set(message["phase_status"]), set(constants.PHASES))

    def test_failed_and_cancelled_messages(self):
        skipped, details = cmd_site.get_skipped_details({})
        failed = cmd_site.get_failed_progress({"ok": False, "cancelled": False, "error": {"code": "no_lots", "title": "필지 없음", "detail": "x"}},
                                              "query", skipped, details)
        self.assertEqual(set(failed), PROGRESS_KEYS | {"error"})
        self.assertEqual((failed["state"], failed["phase_status"]["query"], failed["error"]["code"]), ("failed", "failed", "no_lots"))
        cancelled = cmd_site.get_failed_progress({"ok": False, "cancelled": True, "error": {"code": "cancelled", "title": "취소됨", "detail": ""}},
                                                 "write_3dm", skipped, details)
        self.assertEqual((cancelled["state"], cancelled["phase_status"]["terrain"]), ("cancelled", "done"))


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다")
class DoneMessageTest(unittest.TestCase):
    def test_done_keys_from_engine_response(self):
        # Rhino 없이 run → prepare 뒤 Rhino import에서 ok=false로 끝나지만 응답 키 집합은 전부 — done은 type만 붙인다
        import context_builder
        with tempfile.TemporaryDirectory() as tmp:
            response = context_builder.run({"pnus": [constants.TEST_CONTEXT_PNU], "site_db": SITE_DB, "context_db": CONTEXT_DB,
                                            "result_root": tmp, "options": {"radius": 300, "scales": [3000]}}, None, doc=None)
        done = cmd_site.get_done_message(response)
        self.assertTrue(DONE_KEYS <= set(done))
        self.assertEqual(done["type"], "done")
        self.assertTrue(CONTEXT_KEYS <= set(done["context"]))
        self.assertTrue({"ready", "paper", "layers", "exported"} <= set(done["basemap"]))
        self.assertIn("scales", done["options"])
        self.assertEqual(set(done["quality"]), {"height_src", "align", "skipped", "mismatch_count", "dates"})
        for warning in done["warnings"]:
            self.assertEqual(set(warning), WARNING_KEYS)


class OpenPathTest(unittest.TestCase):
    def test_env_template_relative_and_rejections(self):
        with tempfile.TemporaryDirectory() as tmp:
            env_path = cmd_site.resolve_open_path(".env", root=tmp)
            self.assertEqual(env_path, os.path.join(tmp, ".env"))
            with open(env_path, encoding="utf-8") as f:
                self.assertEqual(f.read(), "VWORLD_API_KEY=\nDATA_GO_KR_KEY=\n")
            self.assertEqual(cmd_site.resolve_open_path(tmp, root=tmp), tmp)
            with self.assertRaises(ValueError):
                cmd_site.resolve_open_path("https://example.com", root=tmp)
            with self.assertRaises(ValueError):
                cmd_site.resolve_open_path("없는폴더/파일.txt", root=tmp)


if __name__ == "__main__":
    unittest.main()
