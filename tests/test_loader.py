import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def _load_loader():
    """진입 스크립트(cmd_*.py)와 같은 방식으로 loader를 읽는다."""
    spec = importlib.util.spec_from_file_location(
        "urbansite_loader_test",
        SCRIPTS_DIR / "loader.py",
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class LoaderTest(unittest.TestCase):
    def setUp(self):
        self.loader = _load_loader()
        self.saved_modules = dict(sys.modules)

    def tearDown(self):
        sys.modules.clear()
        sys.modules.update(self.saved_modules)

    def test_project_module_names_exclude_entry_scripts(self):
        names = self.loader._get_project_module_names()

        self.assertIn("constants", names)
        self.assertIn("lot_db", names)
        for name in names:
            self.assertFalse(name.startswith("cmd_"), name)
        self.assertNotIn("loader", names)

    def test_load_returns_project_module(self):
        module = self.loader.load("constants")

        self.assertEqual(
            Path(module.__file__).resolve(),
            (SCRIPTS_DIR / "constants.py").resolve(),
        )

    def test_load_replaces_foreign_module_of_same_name(self):
        foreign = types.ModuleType("constants")
        foreign.__file__ = "/somewhere/else/constants.py"
        foreign.MARKER = "외부모듈"
        sys.modules["constants"] = foreign

        self.loader.load("lot_db")

        self.assertFalse(hasattr(sys.modules["constants"], "MARKER"))
        self.assertEqual(
            Path(sys.modules["constants"].__file__).parent.resolve(),
            SCRIPTS_DIR.resolve(),
        )

    def test_second_load_keeps_same_module_object(self):
        first = self.loader.load("constants")
        second = self.loader.load("constants")

        self.assertIs(first, second)

    def test_entry_script_module_is_not_reloaded(self):
        entry = types.ModuleType("__main__")
        entry.__file__ = str(SCRIPTS_DIR / "cmd_site.py")
        sys.modules["__main__"] = entry

        self.loader.load("constants")

        self.assertNotIn(entry, self.loader._get_project_modules())

    def test_퍼지하는_모듈이_reload돼도_방금_읽은_것을_돌려준다(self):
        """road_setback_qa처럼 import 때 sys.modules를 비우는 러너 방어.

        그 러너가 이미 올라와 있으면 load()의 reload 루프가 본문을 다시
        실행해 방금 import한 모듈까지 걷어낸다 — 부지검토 폼이 KeyError로
        죽던 자리다.
        """
        purger = types.ModuleType("lot_db")   # 프로젝트 이름을 쓴 가짜 러너
        purger.__file__ = str(SCRIPTS_DIR / "lot_db.py")

        def purge():
            sys.modules.pop("constants", None)

        # reload는 spec으로 파일을 다시 읽으므로, 여기서는 reload 대상 목록에
        # 들어간 모듈이 sys.modules를 건드리는 상황만 직접 흉내낸다.
        original_reload = self.loader.importlib.reload
        self.addCleanup(setattr, self.loader.importlib, "reload", original_reload)
        self.loader.importlib.reload = lambda module: purge()
        sys.modules["lot_db"] = purger

        module = self.loader.load("constants")

        self.assertEqual(
            Path(module.__file__).resolve(),
            (SCRIPTS_DIR / "constants.py").resolve(),
        )

    def test_pyc만_있는_모듈도_이름에_들어간다(self):
        """배포판은 로직 모듈이 .pyc뿐이다."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            file_names = ("alpha.pyc", "beta.py", "beta.pyc", "cmd_a.py", "cmd_b.pyc", "loader.py", "note.txt")
            for file_name in file_names:
                Path(tmp_dir, file_name).touch()
            self.addCleanup(setattr, self.loader, "SCRIPTS_DIR", self.loader.SCRIPTS_DIR)
            self.loader.SCRIPTS_DIR = tmp_dir

            names = self.loader._get_project_module_names()

        self.assertEqual(sorted(names), ["alpha", "beta"])

    def test_source_stamp_changes_with_file_mtime(self):
        self.loader.load("constants")
        stamp = self.loader.source_stamp()

        self.assertTrue(stamp)
        self.assertNotEqual(stamp, tuple(sorted((path, 0.0) for path, _ in stamp)))


if __name__ == "__main__":
    unittest.main()
