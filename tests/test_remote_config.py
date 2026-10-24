"""remote_config — 원격 설정(도면 색·범례·구간·코드표·파라미터·번역)을 내장값 위에 덮는 규칙과 받기·캐시. 네트워크는 로컬 HTTP 서버."""

import functools
import http.server
import json
import os
import sys
import tempfile
import threading
import types
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import constants  # noqa: E402
import remote_config  # noqa: E402


class MirrorTest(unittest.TestCase):
    def test_shapes(self):
        m = remote_config._mirror
        self.assertEqual(m((1.0, 2.0), [3, 4, 5]), (3, 4, 5))                               # tuple 복원, 길이 달라도 됨
        self.assertEqual(m({1000: 100.0}, {"1000": 120.0, "3000": 300.0}), {1000: 120.0, 3000: 300.0})   # int 키 복원·키 추가
        self.assertEqual(m({"a": (1, 2)}, {"a": [3, 4], "b": [5, 6]}), {"a": (3, 4), "b": (5, 6)})       # 중첩 tuple, 새 키는 본보기 꼴
        self.assertEqual(m([("x", None, 1)], [["y", 2, None]]), [("y", 2, None)])             # None 칸·수 칸 서로 허용
        self.assertEqual(m({}, {"k": [1]}), {"k": [1]})                                        # 빈 내장 dict는 아무거나
        for builtin, value in (({"a": 1}, {"b": 1}), ({"a": 1}, [1]), ((1, 2), "x"), ("s", 3), (1.0, "1"), (True, 1), (1, True)):
            with self.assertRaises(ValueError, msg=(builtin, value)):
                m(builtin, value)


class ApplyTest(unittest.TestCase):
    def test_apply_constants_and_i18n(self):
        target = types.SimpleNamespace(SHEET_TRANSIT_COLOR="#000000", SHEET_WALK_MINUTES=(5, 10, 15), SHEET_SCALE_BAR_M={1000: 100.0},
                                       SHEET_ZONE_KEYS={"제1종일반주거": "r1"}, OTHER="keep")
        texts = {"저장": {"en": "Save"}}
        config = {"config_version": 1, "compat_min": "0.3.5", "constants": {
            "SHEET_TRANSIT_COLOR": "#123456", "SHEET_WALK_MINUTES": [5, 10, 15, 20], "SHEET_SCALE_BAR_M": {"1000": 100.0, "2000": 200.0},
            "SHEET_ZONE_KEYS": {"다른키": "x"},                      # 내장 키 빠짐 → 거부
            "OTHER": "hacked", "NOT_A_KEY": 1},                      # REMOTE_KEYS 밖 → 무시
            "i18n": {"저장": {"en": "Save!", "ja": "保存", "xx": "no", "es": ""}, "{0}동": {"en": "{0} bldgs", "ja": "건물"},   # ja는 자리표시 빠짐
                     "새 문구": {"en": "<b>bad</b>", "zh": "新"}, "잘못": "문자열"}}
        report = remote_config.apply(config, target=target, texts=texts, version="0.3.5")
        self.assertEqual(sorted(report["applied"]), ["SHEET_SCALE_BAR_M", "SHEET_TRANSIT_COLOR", "SHEET_WALK_MINUTES"])
        self.assertIn("SHEET_ZONE_KEYS", report["rejected"])
        self.assertEqual((target.SHEET_TRANSIT_COLOR, target.SHEET_WALK_MINUTES, target.SHEET_SCALE_BAR_M, target.OTHER),
                         ("#123456", (5, 10, 15, 20), {1000: 100.0, 2000: 200.0}, "keep"))
        self.assertEqual(texts, {"저장": {"en": "Save!", "ja": "保存"}, "{0}동": {"en": "{0} bldgs"}, "새 문구": {"zh": "新"}})
        self.assertEqual(report["i18n"], 3)

    def test_compat_min_and_garbage(self):
        target = types.SimpleNamespace(SHEET_TRANSIT_COLOR="#000000")
        report = remote_config.apply({"compat_min": "0.4.0", "constants": {"SHEET_TRANSIT_COLOR": "#111111"}}, target=target, texts={}, version="0.3.5")
        self.assertEqual((target.SHEET_TRANSIT_COLOR, report["applied"], report["skipped"]), ("#000000", [], "compat_min 0.4.0"))
        self.assertEqual(remote_config.apply(None, target=target, texts={})["skipped"], "없음")
        self.assertEqual(remote_config.apply({"constants": "x", "i18n": []}, target=target, texts={})["applied"], [])

    def test_build_round_trip(self):
        """빌드한 config.json(JSON 왕복)을 내장값 사본에 덮으면 전부 받아들여지고 값이 같다 — dev_deploy.build_config의 자가 점검과 같다."""
        config = json.loads(json.dumps(remote_config.build(), ensure_ascii=False))
        snapshot = remote_config.get_snapshot()
        report = remote_config.apply(config, target=snapshot, texts={}, version=remote_config.COMPAT_MIN)
        self.assertEqual(report["rejected"], {})
        self.assertEqual(len(report["applied"]), len(remote_config.REMOTE_KEYS))
        self.assertEqual([n for n in remote_config.REMOTE_KEYS if getattr(snapshot, n) != getattr(constants, n)], [])
        self.assertGreater(report["i18n"], 500)
        self.assertEqual(config["compat_min"], remote_config.COMPAT_MIN)


class _Handler(http.server.SimpleHTTPRequestHandler):
    hits = []

    def do_GET(self):
        _Handler.hits.append(self.headers.get("If-None-Match"))
        if self.headers.get("If-None-Match") == '"v1"':
            self.send_response(304)
            self.end_headers()
            return
        body = json.dumps({"config_version": 1, "compat_min": "0.0.1", "constants": {"SHEET_TRANSIT_COLOR": "#ABCDEF"}}).encode("utf-8")
        self.send_response(200)
        self.send_header("ETag", '"v1"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


class FetchTest(unittest.TestCase):
    def test_fetch_cache_304_offline(self):
        data_dir = tempfile.TemporaryDirectory()
        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = "http://127.0.0.1:%d/config.json" % server.server_port
        try:
            self.assertIsNone(remote_config.load_cached(data_dir.name))
            config = remote_config.fetch(timeout=5, url=url, data_dir=data_dir.name)
            self.assertEqual(config["constants"]["SHEET_TRANSIT_COLOR"], "#ABCDEF")
            self.assertTrue(os.path.exists(os.path.join(data_dir.name, "config.json")))
            again = remote_config.fetch(timeout=5, url=url, data_dir=data_dir.name)      # ETag → 304 → 캐시
            self.assertEqual(again, config)
            self.assertEqual(_Handler.hits[-1], '"v1"')
        finally:
            server.shutdown()
            server.server_close()
        offline = remote_config.fetch(timeout=2, url=url, data_dir=data_dir.name)         # 서버 죽음 → 캐시
        self.assertEqual(offline, config)
        self.assertIsNone(remote_config.fetch(timeout=2, url=url, data_dir=os.path.join(data_dir.name, "none")))   # 캐시도 없음
        data_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
