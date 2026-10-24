"""Blender 패키지 정리 — 쓰지 않는 외부 주소를 비우고(dev_deploy.get_patched_source) 허용 목록 밖 주소를 잡는지(get_foreign_hosts).
확장 심사 2026-10-25: VWorld·Hugging Face·상용 서비스 주소를 빼라."""
import importlib.util
import os
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS_DIR = os.path.join(ROOT_DIR, "scripts")
sys.path.insert(0, SCRIPTS_DIR)
import constants   # noqa: E402
import dev_deploy   # noqa: E402


class BlenderPackageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        for name, patches in dev_deploy.BLENDER_CONSTANT_PATCHES.items():
            with open(os.path.join(SCRIPTS_DIR, name), encoding="utf-8") as f:
                source = dev_deploy.get_patched_source(f.read(), patches)   # 상수 이름이 바뀌면 여기서 ValueError
            with open(os.path.join(self.tmp.name, name), "w", encoding="utf-8") as f:
                f.write(source)

    def tearDown(self):
        self.tmp.cleanup()

    def test_patched_files_have_only_allowed_hosts(self):
        self.assertEqual(dev_deploy.get_foreign_hosts(self.tmp.name, dev_deploy.BLENDER_ALLOWED_HOSTS), [])

    def test_patched_constants_read_github_copy_and_no_vworld_key(self):
        spec = importlib.util.spec_from_file_location("blender_constants", os.path.join(self.tmp.name, "constants.py"))
        patched = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(patched)
        self.assertEqual(patched.DATA_MANIFEST_URL, constants.DATA_GITHUB_MANIFEST_URL)
        self.assertTrue(patched.DATA_JP_MANIFEST_URL.startswith("https://raw.githubusercontent.com/"))
        self.assertEqual((patched.VWORLD_API_KEY_ENV, patched.GA_STREAMS), ("", {}))

    def test_foreign_host_is_caught(self):
        with open(os.path.join(self.tmp.name, "extra.py"), "w", encoding="utf-8") as f:
            f.write('URL = "https://api.example.com/v1"\n')
        self.assertEqual(dev_deploy.get_foreign_hosts(self.tmp.name, dev_deploy.BLENDER_ALLOWED_HOSTS), ["extra.py: api.example.com"])

    def test_missing_constant_stops_build(self):
        with self.assertRaises(ValueError):
            dev_deploy.get_patched_source("A = 1\n", {"B": '""'})


if __name__ == "__main__":
    unittest.main()
