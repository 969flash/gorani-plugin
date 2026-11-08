"""토지이용계획 월간 갱신 — 가장 늦은 판 zip만 읽기, 필지 팩만 다시 만들 때 매니페스트의 컨텍스트·등고선 항목 유지."""

import csv
import json
import os
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
import dev_deploy  # noqa: E402

try:
    import dev_database_builder  # noqa: E402 — geopandas·pyogrio(개발 환경)
except ImportError:
    dev_database_builder = None


@unittest.skipIf(dev_database_builder is None, "geopandas·pyogrio가 없다")
class LandUsePathTest(unittest.TestCase):
    def test_reads_latest_zip_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "AL_D155_11_20260826.csv.gz").write_bytes(b"")   # 옛 판
            (folder / "AL_D155_41_20261109.zip").write_bytes(b"")      # 다른 시도
            with zipfile.ZipFile(folder / "AL_D155_11_20261009.zip", "w") as archive:
                archive.writestr("AL_D155_11_20261009.csv", "고유번호,용도지역지구코드\n1111010100100010000,UQA100\n".encode("cp949"))
            paths = dev_database_builder._get_land_use_paths(folder, "AL_D155_11_")
            self.assertEqual([path.name for path in paths], ["AL_D155_11_20261009.zip"])
            with dev_database_builder._open_land_use(paths[0]) as handle:
                self.assertEqual(list(csv.reader(handle)), [["고유번호", "용도지역지구코드"], ["1111010100100010000", "UQA100"]])

    def test_moved_dong_code_follows_parcels(self):
        # 필지(토지특성 05-20판)는 옛 코드, 토지이용계획(10-09판)은 새 코드인 동을 필지 쪽 코드로 맞춘다
        parcels = [
            ("2771038021", "대구광역시 달성군 구지면 창리"),      # 읍 승격 → 2771026821
            ("2771025021", "대구광역시 달성군 화원읍 천내리"),    # 그대로
            ("2814010100", "인천광역시 동구 만석동"),             # 개편 → 제물포구 2812510100(시도 안에 이름 하나)
            ("2814010600", "인천광역시 동구 금곡동"),             # 개편 → 제물포구 2812510600(이름 둘 — 만석동이 가리킨 옛 동구에서)
            ("2826010400", "인천광역시 서구 금곡동"),             # 같은 이름, 다른 동(지번이 달라 붙이지 않는다)
        ]
        land_use = [
            ("2771026821", "대구광역시 달성군 구지읍 창리", "2771038021"),
            ("2771025021", "대구광역시 달성군 화원읍 천내리", "2771025021"),
            ("2812510100", "인천광역시 제물포구 만석동", "2814010100"),
            ("2812510600", "인천광역시 제물포구 금곡동", "2814010600"),
            ("2829010700", "인천광역시 검단구 금곡동", "2829010700"),   # 서구 금곡동과 지번이 안 겹친다 → 못 맞춤(그대로)
            ("2771099999", "대구광역시 달성군 없는면 새리", "2771099999"),
        ]
        lot_suffixes = ["1%04d0000" % n for n in range(1, 11)]
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            connection = dev_database_builder._connect_database(folder / "t.db")
            connection.execute("INSERT INTO data_sources (source_id, name, page_url, acquired_at) VALUES ('s', 's', 's', 's')")
            for dong, name in parcels:
                suffixes = ["2%04d0000" % n for n in range(1, 11)] if dong == "2826010400" else lot_suffixes
                for suffix in suffixes:
                    connection.execute("INSERT INTO parcels (pnu, address, geometry_area_sqm, geometry_json, geometry_crs, source_id, min_x, max_x, min_y, max_y)"
                                       " VALUES (?, ?, 1, '{}', 5186, 's', 0, 1, 0, 1)", (dong + suffix, name + " 1"))
            lines = ["고유번호,법정동명,용도지역지구코드,용도지역지구명,저촉여부"]
            lines += ["%s%s,%s,UQA430,자연녹지지역,포함" % (dong, suffix, name) for dong, name, _ in land_use for suffix in lot_suffixes]
            for code in ("27", "28"):
                with zipfile.ZipFile(folder / ("AL_D155_%s_20261009.zip" % code), "w") as archive:
                    archive.writestr("AL_D155_%s_20261009.csv" % code, ("\n".join(lines) + "\n").encode("cp949"))
            dev_database_builder.load_land_use(connection, land_use_dir=folder, sido_code="27")
            dongs = {row[0] for row in connection.execute("SELECT substr(pnu, 1, 10) FROM parcel_land_use")}
            connection.close()
            self.assertEqual(dongs, {expected for _, _, expected in land_use})


class ManifestKindsTest(unittest.TestCase):
    def test_site_entries_keep_context_and_terrain(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = ["11110_site.db", "11999_site.db", "11110_context.db", "11110_terrain.db", "26110_site.db"]
            with open(os.path.join(tmp, "manifest.json"), "w") as f:
                json.dump({"version": "x", "packs": [{"name": name} for name in old]}, f)
            dev_deploy._update_manifest(tmp, "seoul", [{"name": "11110_site.db", "new": True}])
            with open(os.path.join(tmp, "manifest.json")) as f:
                packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
            # 서울 필지 팩은 새 목록으로 통째로(11999 없어짐), 서울 컨텍스트·등고선과 다른 시도는 그대로
            self.assertEqual(sorted(packs), ["11110_context.db", "11110_site.db", "11110_terrain.db", "26110_site.db"])
            self.assertTrue(packs["11110_site.db"]["new"])


if __name__ == "__main__":
    unittest.main()
