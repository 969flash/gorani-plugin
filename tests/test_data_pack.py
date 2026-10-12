"""data_pack — 로컬 HTTP 서버에 xz 팩과 매니페스트를 두고 받기·검증·재받기 판정을 확인한다."""

import functools
import hashlib
import http.server
import json
import lzma
import os
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import data_pack  # noqa: E402


class DataPackTest(unittest.TestCase):
    def setUp(self):
        self.server_dir = tempfile.TemporaryDirectory()
        self.data_dir = tempfile.TemporaryDirectory()
        self.raw = os.urandom(3 * 1024 * 1024 + 17)   # 조각 여러 개
        with open(os.path.join(self.server_dir.name, "a.db.xz"), "wb") as f:
            f.write(lzma.compress(self.raw))
        self.pack = {"name": "a.db", "label": "시험", "url": "a.db.xz", "size": len(self.raw),
                     "sha256": hashlib.sha256(self.raw).hexdigest()}
        with open(os.path.join(self.server_dir.name, "manifest.json"), "w") as f:
            json.dump({"version": "t", "packs": [self.pack]}, f)
        handler = functools.partial(_QuietHandler, directory=self.server_dir.name)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = "http://127.0.0.1:%d/manifest.json" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.server_dir.cleanup()
        self.data_dir.cleanup()

    def test_download_then_up_to_date(self):
        manifest = data_pack.get_manifest(self.url)
        self.assertTrue(manifest["packs"][0]["url"].endswith("/a.db.xz"))
        missing = data_pack.get_missing_packs(manifest, self.data_dir.name)
        self.assertEqual([p["name"] for p in missing], ["a.db"])
        seen = []
        self.assertTrue(data_pack.download_pack(missing[0], self.data_dir.name, lambda done, total: seen.append(done)))
        with open(os.path.join(self.data_dir.name, "a.db"), "rb") as f:
            self.assertEqual(f.read(), self.raw)
        self.assertEqual(seen[-1], len(self.raw))
        self.assertEqual(data_pack.get_missing_packs(manifest, self.data_dir.name), [])

    def test_cancel_and_bad_hash_keep_nothing(self):
        pack = data_pack.get_manifest(self.url)["packs"][0]
        self.assertFalse(data_pack.download_pack(pack, self.data_dir.name, lambda done, total: False))
        pack["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            data_pack.download_pack(pack, self.data_dir.name)
        self.assertEqual(os.listdir(self.data_dir.name), [])


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    unittest.main()
