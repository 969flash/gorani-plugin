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

    def test_jp_packs_apart(self):
        """일본 건물 팩(경위도)은 한국 조회에서 빠지고 일본 조회(경위도 범위)에서만 열린다. 일본 팩을 받을 때는 설치 ID를 보내지 않는다."""
        with tempfile.TemporaryDirectory() as data_dir:
            for name in ("11110_context.db", "jp13104_context.db", "jp27100_context.db", "jpn_context.db"):
                open(os.path.join(data_dir, name), "w").close()
            with open(os.path.join(data_dir, "packs.json"), "w") as f:
                json.dump({"jp13104_context.db": {"sha256": "x", "bounds": [139.66, 35.66, 139.75, 35.73]},
                           "jp27100_context.db": {"sha256": "x", "bounds": [135.39, 34.58, 135.58, 34.76]}}, f)
            self.assertEqual([os.path.basename(p) for p in data_pack.get_local_paths("context", data_dir=data_dir)],
                             ["11110_context.db", "jpn_context.db"])
            self.assertEqual([os.path.basename(p) for p in data_pack.get_jp_paths((139.69, 35.68, 139.71, 35.70), data_dir)], ["jp13104_context.db"])
        sent = {}

        def fake_urlopen(request, timeout=None):
            sent.update(request.headers)
            raise OSError("멈춤")
        original = data_pack.urllib.request.urlopen
        data_pack.urllib.request.urlopen = fake_urlopen
        try:
            for name in ("11110_context.db", "jp13104_context.db"):   # 국내 서버 팩은 보내고 일본 팩은 보내지 않는다
                sent.clear()
                with self.assertRaises(OSError):
                    data_pack._open_pack({"name": name, "url": "https://example.com/%s.xz" % name}, "install-id", None)
                self.assertEqual(sent.get("X-udt-client"), None if name.startswith("jp") else "install-id")
        finally:
            data_pack.urllib.request.urlopen = original

    def test_country_packs_from_manifest(self):
        """한국 매니페스트 countries[]가 내장 나라 목록을 덮는다 — 새 나라는 플러그인 판 없이. 틀린 항목은 그 나라만 건너뛰고 disabled는 뺀다."""
        import constants
        import osm_context
        saved = data_pack._MANIFEST.get(constants.DATA_MANIFEST_URL)
        data_pack._MANIFEST[constants.DATA_MANIFEST_URL] = {"version": "t", "packs": [], "countries": [
            {"code": "us", "label": "Overture", "source_id": "overture", "manifest": "us/manifest.json", "code_pattern": r"\d{5}",
             "bounds": [[-125, 24, -66, 50], [-170, 51, -129, 72]]},                                                 # 본토 + 알래스카(상자 여럿)
            {"code": "fr", "disabled": True},                                                                            # 원천 약관이 바뀌어 내렸다
            {"code": "xx", "label": "상자 3수", "source_id": "x", "manifest": "xx/manifest.json", "bounds": [1, 2, 3], "code_pattern": r"\d"},
            {"code": "yy", "label": "정규식 틀림", "source_id": "y", "manifest": "yy/manifest.json", "bounds": [1, 2, 3, 4], "code_pattern": "("},
            {"code": "zzz", "label": "코드 3자", "source_id": "z", "manifest": "zz/manifest.json", "bounds": [1, 2, 3, 4], "code_pattern": r"\d"},
            "문자열"]}
        try:
            packs = data_pack.get_country_packs()
            self.assertEqual(packs["us"]["manifest"], "https://huggingface.co/datasets/%s/resolve/main/us/manifest.json" % constants.DATA_REPO_ID)
            self.assertEqual(packs["us"]["bounds"], [(-125.0, 24.0, -66.0, 50.0), (-170.0, 51.0, -129.0, 72.0)])
            self.assertEqual(set(packs), {"jp", "nl", "ch", "us"})
            self.assertEqual(osm_context.get_country(-118.2437, 34.0522), "us")   # 로스앤젤레스
            self.assertEqual(osm_context.get_country(-149.9003, 61.2181), "us")   # 앵커리지 — 둘째 상자
            self.assertEqual(osm_context.get_country(2.2945, 48.8584), "")        # 파리 — 프랑스를 내렸다
            self.assertEqual(osm_context.get_country(8.6416, 46.8807), "ch")      # 알트도르프 — 내장 그대로
            self.assertEqual(data_pack.get_pack_country("us06037_context.db"), "us")
            self.assertEqual(data_pack.get_pack_source_ids()["overture"], "us")
            self.assertEqual(data_pack.get_pack_label("overture"), "Overture")
            self.assertEqual(data_pack.get_pack_label("osm"), "")
        finally:
            if saved is None:
                data_pack._MANIFEST.pop(constants.DATA_MANIFEST_URL, None)
            else:
                data_pack._MANIFEST[constants.DATA_MANIFEST_URL] = saved
        packs = data_pack.get_country_packs()   # 매니페스트를 못 받았으면 내장 목록(상자는 목록 꼴)
        self.assertEqual(set(packs), set(constants.COUNTRY_PACKS))
        self.assertEqual(packs["jp"]["bounds"], [constants.JP_BOUNDS])

    def test_height_src_label_and_services(self):
        """새 나라 팩의 height_src(overture_levels …)는 코드 사전 없이 팩 라벨로 범례에 나오고, 매니페스트 services가 외부 주소를 덮는다(https만)."""
        import constants
        saved = data_pack._MANIFEST.get(constants.DATA_MANIFEST_URL)
        data_pack._MANIFEST[constants.DATA_MANIFEST_URL] = {"version": "t", "packs": [], "countries": [
            {"code": "xx", "label": "NewLand 3D", "source_id": "newland", "manifest": "xx/manifest.json", "bounds": [10, 10, 11, 11], "code_pattern": r"\d{3}"}],
            "services": {"overpass": ["https://overpass.example.org/api/interpreter", "http://plain.example.org"], "nominatim": "ftp://bad", "terrain_tiles": 5}}
        try:
            self.assertEqual(data_pack.get_height_src_label("plateau_height"), "PLATEAU 실측 높이")      # 내장 사전
            self.assertEqual(data_pack.get_height_src_label("overture_levels"), "Overture 층수")        # 내장 나라
            self.assertEqual(data_pack.get_height_src_label("newland_height"), "NewLand 3D 높이")      # 매니페스트로만 아는 나라
            self.assertEqual(data_pack.get_height_src_label("newland_lidar"), "NewLand 3D lidar")
            self.assertEqual(data_pack.get_height_src_label("mystery"), "mystery")
            self.assertEqual(data_pack.get_service("overpass", constants.OSM_OVERPASS_URLS), ("https://overpass.example.org/api/interpreter",))   # http는 버림
            self.assertEqual(data_pack.get_service("nominatim", constants.OSM_NOMINATIM_URL), constants.OSM_NOMINATIM_URL)   # https 아님 → 내장
            self.assertEqual(data_pack.get_service("terrain_tiles", constants.OSM_TERRAIN_URL), constants.OSM_TERRAIN_URL)
        finally:
            if saved is None:
                data_pack._MANIFEST.pop(constants.DATA_MANIFEST_URL, None)
            else:
                data_pack._MANIFEST[constants.DATA_MANIFEST_URL] = saved
        self.assertEqual(data_pack.get_service("overpass", constants.OSM_OVERPASS_URLS), tuple(constants.OSM_OVERPASS_URLS))   # 매니페스트 없음

    def test_countries_json_matches_builtin(self):
        """docs/countries.json(매니페스트 원본)은 전부 검증을 지나고, 내장 constants.COUNTRY_PACKS와 값이 같다 — 오프라인 내장 목록이 원격과 어긋나지 않게."""
        import constants
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "countries.json")
        with open(path, encoding="utf-8") as f:
            entries = json.load(f)["countries"]
        remote = {entry["code"]: data_pack._get_country_pack(entry) for entry in entries}
        self.assertTrue(all(remote.values()), [code for code, pack in remote.items() if not pack])
        data_pack._MANIFEST.pop(constants.DATA_MANIFEST_URL, None)   # 내장만
        builtin = data_pack.get_country_packs()
        for code in constants.COUNTRY_PACKS:
            self.assertEqual(builtin[code], remote[code], code)

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
