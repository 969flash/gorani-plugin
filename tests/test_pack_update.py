"""토지이용계획 월간 갱신 — 필지 팩만 다시 만들 때 매니페스트의 컨텍스트·등고선 항목 유지. zip 읽기 시험은 gorani-ops tests/test_dev_database_builder.py."""

import json
import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
import dev_deploy  # noqa: E402


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
