"""yak 로직 모듈 — Rhino 8(CPython 3.9)·Rhino 9(3.13)가 같은 scripts/에서 각자 판의 .pyc를 읽는지(dev_deploy._stage_scripts).

2026-11-27: 3.9 .pyc만 넣은 0.3.9가 Rhino 9에서 'bad magic number in i18n'으로 열리지 않았다.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
import dev_deploy   # noqa: E402

IMPORT_SOURCE = "import sys; sys.path.insert(0, sys.argv[1]); import constants, i18n; print(constants.PANEL_VERSION, constants.__file__)"


@unittest.skipUnless(all(os.path.exists(p) for p in dev_deploy.YAK_PYTHONS.values()), "YAK_PYTHONS 파이썬이 없다")
class YakPycTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        dev_deploy._stage_scripts(cls.temp.name)
        cls.scripts = os.path.join(cls.temp.name, "scripts")

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_each_rhino_python_reads_its_pyc(self):
        for python in dev_deploy.YAK_PYTHONS.values():
            result = subprocess.run([python, "-I", "-B", "-c", IMPORT_SOURCE, self.scripts], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            version, path = result.stdout.split()
            self.assertEqual(version, dev_deploy.constants.PANEL_VERSION)
            self.assertEqual(path, os.path.join(self.scripts, "constants.py"))   # 경로 계산(constants._ROOT_DIR·i18n.json)은 .py 자리 그대로

    def test_no_source_shipped(self):
        with open(os.path.join(self.scripts, "constants.py"), encoding="utf-8") as f:
            self.assertEqual(f.read(), dev_deploy.MODULE_STUB)

    def test_unknown_python_gets_message(self):
        with tempfile.TemporaryDirectory() as prefix:
            result = subprocess.run([sys.executable, "-I", "-B", "-X", "pycache_prefix=" + prefix, "-c",
                                     "import sys; sys.path.insert(0, sys.argv[1]); import constants", self.scripts], capture_output=True, text=True)
        self.assertIn("does not support Python", result.stderr)   # 캐시 자리를 옮기면 .pyc를 못 찾는다 = 모르는 판


if __name__ == "__main__":
    unittest.main()
