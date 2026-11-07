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
        # 대구 달성군 구지면 → 구지읍: 필지(토지특성)는 옛 코드 2771038021, 토지이용계획은 새 코드 2771026821
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            connection = dev_database_builder._connect_database(folder / "t.db")
            connection.execute("INSERT INTO data_sources (source_id, name, page_url, acquired_at) VALUES ('s', 's', 's', 's')")
            for pnu, address in (("2771038021100010001", "대구광역시 달성군 구지면 창리 1-1"), ("2771025021200010001", "대구광역시 달성군 화원읍 천내리 산1-1")):
                connection.execute("INSERT INTO parcels (pnu, address, geometry_area_sqm, geometry_json, geometry_crs, source_id, min_x, max_x, min_y, max_y)"
                                   " VALUES (?, ?, 1, '{}', 5186, 's', 0, 1, 0, 1)", (pnu, address))
            lines = ["고유번호,법정동명,용도지역지구코드,용도지역지구명,저촉여부",
                     "2771026821100010001,대구광역시 달성군 구지읍 창리,UQA430,자연녹지지역,포함",
                     "2771025021200010001,대구광역시 달성군 화원읍 천내리,UQA430,자연녹지지역,포함",
                     "2771099999100010001,대구광역시 달성군 없는면 새리,UQA430,자연녹지지역,포함"]
            with zipfile.ZipFile(folder / "AL_D155_27_20261009.zip", "w") as archive:
                archive.writestr("AL_D155_27_20261009.csv", ("\n".join(lines) + "\n").encode("cp949"))
            dev_database_builder.load_land_use(connection, land_use_dir=folder, sido_code="27")
            pnus = sorted(row[0] for row in connection.execute("SELECT pnu FROM parcel_land_use"))
            connection.close()
            self.assertEqual(pnus, ["2771025021200010001", "2771038021100010001", "2771099999100010001"])


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
