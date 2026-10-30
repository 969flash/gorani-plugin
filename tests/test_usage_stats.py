"""usage_stats — 요청 본문·대상지 매개변수·꺼짐 조건 (네트워크 없음)."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants   # noqa: E402
import non_rhino_utils   # noqa: E402
import usage_stats   # noqa: E402


class UsageStatsTest(unittest.TestCase):
    def test_payload_cleans_params(self):
        body = usage_stats.get_payload("build", {"a": None, "ok": True, "long": "x" * 300, "n": 1.5}, "cid")
        params = body["events"][0]["params"]
        self.assertEqual(body["client_id"], "cid")
        self.assertNotIn("a", params)
        self.assertEqual(params["ok"], 1)
        self.assertEqual(len(params["long"]), constants.GA_PARAM_VALUE_MAX)
        self.assertEqual(params["n"], 1.5)
        self.assertIn("engagement_time_msec", params)

    def test_dev_mark_only_on_admin_pc(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(constants, "ADMIN_DIR", tmp):
                self.assertEqual(usage_stats.get_payload("build", {}, "cid")["events"][0]["params"]["dev"], 1)
            with mock.patch.object(constants, "ADMIN_DIR", os.path.join(tmp, "none")):
                self.assertNotIn("dev", usage_stats.get_payload("build", {}, "cid")["events"][0]["params"])

    def test_lots_pnus_split(self):
        non_rhino_utils.set_projection()
        pnus = ["1120011500103330%03d" % i for i in range(12)]
        params = usage_stats.get_target_params({"mode": "lots", "pnus": pnus})
        self.assertEqual(params["lot_count"], 12)
        self.assertEqual(params["pnus"].split(",") + params["pnus_2"].split(",") + params["pnus_3"].split(","), pnus)
        self.assertTrue(all(len(params[k]) <= constants.GA_PARAM_VALUE_MAX for k in ("pnus", "pnus_2", "pnus_3")))

    def test_area_sends_center_and_size_only(self):
        non_rhino_utils.set_projection()
        x, y = non_rhino_utils.get_tm_from_wgs84(127.0557, 37.5444)   # 성수동
        ring = [(x, y), (x + 100, y), (x + 100, y + 50), (x, y + 50)]
        params = usage_stats.get_target_params({"mode": "area", "ring": ring})
        self.assertEqual((params["area"], params["width"], params["height"]), (5000.0, 100.0, 50.0))
        self.assertAlmostEqual(params["lat"], 37.5446, places=3)
        self.assertTrue(params["korea"])
        self.assertNotIn("ring", params)

    def test_disabled_without_ids(self):
        with mock.patch.object(constants, "GA_STREAMS", {"rhino": ("", "")}):
            self.assertFalse(usage_stats.send_event("panel_open", {}))

    def test_stream_per_host(self):   # Rhino·Blender 통계가 한 속성에 섞이지 않는다
        streams = {"rhino": ("G-R", "r"), "blender": ("G-B", "b")}
        with mock.patch.object(constants, "GA_STREAMS", streams), mock.patch.object(usage_stats.context_builder, "get_host", return_value="blender"):
            self.assertEqual(usage_stats.get_stream(), ("G-B", "b"))
        with mock.patch.object(constants, "GA_STREAMS", {"rhino": ("G-R", "r")}), mock.patch.object(usage_stats.context_builder, "get_host", return_value="blender"):
            self.assertFalse(usage_stats.is_enabled())

    def test_blender_needs_consent(self):   # Blender 확장 약관 4.5 — 동의한 사람만, Rhino는 묻지 않는다
        streams = {"rhino": ("G-R", "r"), "blender": ("G-B", "b")}
        with mock.patch.object(constants, "GA_STREAMS", streams), mock.patch.object(usage_stats.context_builder, "get_host", return_value="blender"):
            for consent, enabled in ((None, False), (False, False), (True, True)):
                with mock.patch.object(usage_stats.site_prefs, "get_stats_consent", return_value=consent):
                    self.assertEqual(usage_stats.is_enabled(), enabled)
        with mock.patch.object(constants, "GA_STREAMS", streams), mock.patch.object(usage_stats.site_prefs, "get_stats_consent", return_value=None):
            self.assertTrue(usage_stats.is_enabled())   # rhino

    def test_consent_saved(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prefs.json")
            self.assertIsNone(usage_stats.site_prefs.get_stats_consent(path))
            usage_stats.site_prefs.save_stats_consent(True, path)
            self.assertTrue(usage_stats.site_prefs.get_stats_consent(path))

    def test_client_id_persists(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "sub", "client_id")
            self.assertEqual(usage_stats.get_client_id(path), usage_stats.get_client_id(path))


if __name__ == "__main__":
    unittest.main()
