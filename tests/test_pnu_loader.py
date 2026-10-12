import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import lot_db
import pnu_loader


class AddressResolverTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_dir.name) / "lot.db"
        connection = sqlite3.connect(str(self.database_path))
        connection.execute(
            """
            CREATE TABLE parcels (
                pnu TEXT PRIMARY KEY,
                address TEXT,
                lot_number TEXT,
                land_category TEXT,
                geometry_area_sqm REAL
            )
            """
        )
        connection.executemany(
            """
            INSERT INTO parcels
                (pnu, address, lot_number, land_category, geometry_area_sqm)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    "1123010300106760006",
                    "서울특별시 동대문구 제기동 676-6",
                    "676-6",
                    "대",
                    230.408,
                ),
                (
                    "1123010300106760007",
                    "서울특별시 동대문구 제기동 676-7",
                    "676-7",
                    "대",
                    120.0,
                ),
                (
                    "1126010300100090004",
                    "서울특별시 중랑구 중화동 9-4",
                    "9-4",
                    "대",
                    28.802,
                ),
                (
                    "1126010300200090004",
                    "서울특별시 중랑구 중화동 산9-4",
                    "산9-4",
                    "임야",
                    320.92,
                ),
            ],
        )
        connection.commit()
        connection.close()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_normalizes_jibun_variants(self):
        for query in ("제기동 676-6", "제기동676-6", "동대문 제기 676 6번지"):
            pnus, _matches_json, _log = pnu_loader.resolve_run(
                [query], database_path=self.database_path
            )
            self.assertEqual(pnus, ["1123010300106760006"])

    def test_partial_jibun_stays_ambiguous(self):
        pnus, matches_json, _log = pnu_loader.resolve_run(
            ["제기동 676"], database_path=self.database_path
        )
        self.assertEqual(pnus, [])
        self.assertEqual(json.loads(matches_json)[0]["status"], "ambiguous")

    def test_mountain_prefix_distinguishes_lots(self):
        pnus, matches_json, _log = pnu_loader.resolve_run(
            ["중화동 산9-4"], database_path=self.database_path
        )
        self.assertEqual(pnus, ["1126010300200090004"])
        self.assertEqual(
            json.loads(matches_json)[0]["matches"][0]["address"],
            "서울특별시 중랑구 중화동 산9-4",
        )

    def test_vworld_fallback_resolves_a_verified_local_lot(self):
        expected_match = pnu_loader.LotMatch(
            pnu="1123010300106760006",
            address="서울특별시 동대문구 제기동 676-6",
            lot_number="676-6",
            land_category="대",
            geometry_area=230.408,
            source="vworld",
        )
        with patch.object(
            pnu_loader,
            "_vworld_matches",
            return_value=([expected_match], "ok", "VWorld 주소 검색 후보 1건"),
        ) as vworld_matches:
            pnus, matches_json, _log = pnu_loader.resolve_run(
                ["서울특별시 동대문구 왕산로 123"],
                use_vworld=True,
                database_path=self.database_path,
            )

        self.assertEqual(pnus, ["1123010300106760006"])
        self.assertEqual(json.loads(matches_json)[0]["matches"][0]["source"], "vworld")
        vworld_matches.assert_called_once()

if __name__ == "__main__":
    unittest.main()
