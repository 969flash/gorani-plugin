"""등고선 팩 분리 — dev_deploy가 나눈 컨텍스트·등고선 두 파일을 context_db가 원본 한 파일과 같게 읽는지."""

import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
import constants  # noqa: E402
import context_db  # noqa: E402
import dev_deploy  # noqa: E402

FIXTURE = os.path.join(ROOT_DIR, "tests", "fixtures", "seongsu_context.db")


class TerrainPackTest(unittest.TestCase):
    def test_split_reads_like_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            context_path = os.path.join(tmp, "seoul_context.db")
            terrain_path = os.path.join(tmp, constants.TERRAIN_DATABASE_NAME)
            dev_deploy._make_pack_database("seoul_context.db", FIXTURE, context_path)
            context_only = context_db.get_counts(context_path)
            dev_deploy._make_pack_database(constants.TERRAIN_DATABASE_NAME, FIXTURE, terrain_path)
            self.assertFalse(any(key.startswith(constants.TERRAIN_THEME + "/") for key in context_only["features"]))
            packed, original = context_db.get_counts(context_path), context_db.get_counts(FIXTURE)
            packed["features"].pop("qa/align_sheet"), original["features"].pop("qa/align_sample")   # 팩은 정합 샘플을 도엽 요약으로 줄인다
            self.assertEqual(packed, original)
            sheet_bounds = (-1e9, 1e9, -1e9, 1e9)
            self.assertEqual(len(context_db.load_features_in_bounds(sheet_bounds, themes=[constants.TERRAIN_THEME], database_path=context_path)),
                             len(context_db.load_features_in_bounds(sheet_bounds, themes=[constants.TERRAIN_THEME], database_path=FIXTURE)))


if __name__ == "__main__":
    unittest.main()
