"""data_pack — 로컬 HTTP 서버에 xz 팩과 매니페스트를 두고 받기·검증·재받기 판정을 확인한다."""

import functools
import hashlib
import http.server
import json
import lzma
import os
import sqlite3
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

    def test_moved_url_rereads_manifest(self):
        # 국내 서버 주소가 바뀐 뒤(문지기 서버로 옮김·되돌림) 세션에 남은 옛 주소 — 404면 매니페스트를 새로 읽어 받는다
        pack = dict(data_pack.get_manifest(self.url)["packs"][0])
        pack["url"] = pack["url"].replace("a.db.xz", "gone.db.xz")
        self.assertTrue(data_pack.download_pack(pack, self.data_dir.name, client_id="x", manifest_url=self.url))
        with open(os.path.join(self.data_dir.name, "a.db"), "rb") as f:
            self.assertEqual(f.read(), self.raw)


class LocalPackTest(unittest.TestCase):
    def test_paths_filter_and_union(self):
        with tempfile.TemporaryDirectory() as data_dir:
            for name, rows in (("seoul_site.db", [(1, "11")]), ("gyeonggi_site.db", [(41000000001, "41")]), ("busan_site.db", [(26000000001, "26")])):
                connection = sqlite3.connect(os.path.join(data_dir, name))
                connection.execute("CREATE TABLE parcels (parcel_id INTEGER PRIMARY KEY, pnu TEXT)")
                connection.executemany("INSERT INTO parcels VALUES (?, ?)", rows)
                connection.commit()
                connection.close()
            with open(os.path.join(data_dir, "packs.json"), "w") as f:   # 부산은 멀리 떨어진 범위
                json.dump({"busan_site.db": {"sha256": "x", "bounds": [380000, 180000, 420000, 220000]}}, f)
            self.assertEqual(len(data_pack.get_local_paths("site", data_dir=data_dir)), 3)
            near_seoul = data_pack.get_local_paths("site", (190000, 540000, 210000, 560000), data_dir=data_dir)
            self.assertEqual([os.path.basename(p) for p in near_seoul], ["gyeonggi_site.db", "seoul_site.db"])
            by_pnu = data_pack.get_local_paths("site", sido_codes={"41"}, data_dir=data_dir)
            self.assertEqual([os.path.basename(p) for p in by_pnu], ["gyeonggi_site.db"])
            connection = data_pack.open_union(near_seoul)
            self.assertEqual(sorted(r["pnu"] for r in connection.execute("SELECT pnu FROM parcels")), ["11", "41"])
            connection.close()

    def test_group_without_table(self):
        """상한을 넘어 묶음으로 나뉠 때 테이블이 없는 묶음(등고선 팩만)은 건너뛴다. 어디에도 없으면 오류."""
        with tempfile.TemporaryDirectory() as data_dir:
            paths = []
            for n in range(data_pack.constants.DATA_MAX_OPEN_FILES + 1):
                path = os.path.join(data_dir, "%05d.db" % n)
                connection = sqlite3.connect(path)
                connection.execute("CREATE TABLE %s (v INTEGER)" % ("features" if n == data_pack.constants.DATA_MAX_OPEN_FILES else "buildings"))
                connection.execute("INSERT INTO %s VALUES (?)" % ("features" if n == data_pack.constants.DATA_MAX_OPEN_FILES else "buildings"), (n,))
                connection.commit()
                connection.close()
                paths.append(path)
            connection = data_pack.open_databases(paths)
            self.assertEqual(len(connection.execute("SELECT v FROM buildings").fetchall()), data_pack.constants.DATA_MAX_OPEN_FILES)
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("SELECT v FROM roads")
            connection.close()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


if __name__ == "__main__":
    unittest.main()
