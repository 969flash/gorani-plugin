"""Blender 패키지 정리 — 쓰지 않는 외부 주소를 비우고(dev_deploy.get_patched_source) 허용 목록 밖 주소를 잡는지(get_foreign_hosts),
다른 프로그램 구간을 빼고(get_blender_source) 남은 흔적·스레드·없는 라이브러리를 잡는지(get_blender_problems).
확장 심사 2026-10-25: VWorld·Hugging Face·상용 서비스 주소를 빼라. 2026-10-28: threading·queue, Rhino·shapely import, SketchUp 분기, docs 폴더를 빼라."""
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
                source = dev_deploy.get_blender_source(f.read(), name, ["constants"])   # 상수 이름이 바뀌면 여기서 ValueError
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
        self.assertEqual(patched.VWORLD_API_KEY_ENV, "")
        self.assertFalse(hasattr(patched, "GA_STREAMS"))   # 사용 통계 구간은 통째로 빠진다
        self.assertEqual(list(patched.HOST_LABELS), ["blender"])

    def test_foreign_host_is_caught(self):
        with open(os.path.join(self.tmp.name, "extra.py"), "w", encoding="utf-8") as f:
            f.write('URL = "https://api.example.com/v1"\n')
        self.assertEqual(dev_deploy.get_foreign_hosts(self.tmp.name, dev_deploy.BLENDER_ALLOWED_HOSTS), ["extra.py: api.example.com"])

    def test_cut_and_problems(self):
        """# [blender-cut] 구간은 빠지고, 남은 다른 프로그램 흔적·스레드·없는 라이브러리·정의 안 된 이름은 점검이 잡는다."""
        source = ("import json\n# [blender-cut] Rhino\ntry:\n    import Rhino\nexcept ImportError:\n    Rhino = None\n# [/blender-cut]\n"
                  "X = json.dumps(1)\n")
        self.assertEqual(dev_deploy.get_blender_source(source, "m.py", ["m"]), "import json\nX = json.dumps(1)\n")
        package = os.path.join(self.tmp.name, "pkg")
        os.makedirs(os.path.join(package, "docs"))
        with open(os.path.join(package, "bad.py"), "w", encoding="utf-8") as f:
            f.write('"""Rhino 이야기는 docstring이면 된다."""\nimport threading\nimport shapely\nimport bpy\nimport numpy\n\n\ndef f():\n'
                    '    """설명."""\n    return Rhino.RhinoDoc, "sketchup"\n')
        found = [p.split(": ", 1)[1] for p in dev_deploy.get_blender_problems(package)]
        self.assertEqual(sorted(found), sorted(["실행에 필요 없는 문서 폴더", "스레드 import threading", "Blender에 없는 라이브러리 import shapely",
                                                "정의 안 된 이름 Rhino", "다른 프로그램 흔적 Rhino", "다른 프로그램 흔적 RhinoDoc", '다른 프로그램 흔적 "sketchup"']))

    def test_missing_constant_stops_build(self):
        with self.assertRaises(ValueError):
            dev_deploy.get_patched_source("A = 1\n", {"B": '""'})


if __name__ == "__main__":
    unittest.main()
