"""관리자 페이지(dev_admin)의 공지 검사·바뀐 점 문장. 네트워크·서버 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dev_admin  # noqa: E402

NOTICE = {"id": "2026-10-21-1", "level": "info", "date": "2026-10-21", "text": "점검", "url": "https://example.com"}


class NoticeErrorsTest(unittest.TestCase):
    def test_valid(self):
        data = {"update": {"latest": "0.3.0", "min": "0.2.0"}, "notices": [NOTICE]}
        self.assertEqual(dev_admin.get_notice_errors(data), [])
        self.assertEqual(dev_admin.get_notice_errors({"update": None, "notices": []}), [])

    def test_bad_values(self):
        data = {"update": {"latest": "0.0.1", "min": "0.0.2"},
                "notices": [NOTICE, dict(NOTICE, text="", level="loud", url="example.com")]}
        errors = dev_admin.get_notice_errors(data)
        self.assertIn("최소 버전이 최신 버전보다 높습니다", errors)
        self.assertTrue(any("겹칩니다" in e for e in errors))
        self.assertTrue(any("글이 비었습니다" in e for e in errors))
        self.assertTrue(any("https://" in e for e in errors))
        self.assertEqual(dev_admin.get_notice_errors({"update": {"latest": "v0.3"}, "notices": []}),
                         ["최신 버전은 0.3.0처럼 숫자와 점만 씁니다"])

    def test_min_above_repo_version_blocks(self):   # 아직 배포 안 한 버전을 최소로 = 모든 사용자 차단
        version = dev_admin.constants.PANEL_VERSION
        self.assertEqual(dev_admin.get_notice_errors({"update": {"min": version}, "notices": []}), [])
        errors = dev_admin.get_notice_errors({"update": {"min": version + ".1"}, "notices": []})
        self.assertTrue(errors and "모든 사용자가 막힙니다" in errors[0])

    def test_version_compare_matches_panel(self):   # 패널 cmpVer: 빈 자리 = 0
        self.assertEqual(dev_admin.get_version_key("0.10.0") > dev_admin.get_version_key("0.9"), True)


class ChangesTest(unittest.TestCase):
    def test_changes(self):
        remote = {"update": None, "notices": [NOTICE, dict(NOTICE, id="old", text="옛 공지")]}
        local = {"update": {"latest": "0.3.0"}, "notices": [dict(NOTICE, text="점검 바뀜"), dict(NOTICE, id="new", text="새 공지")]}
        self.assertEqual(dev_admin.get_changes(local, remote), [
            "업데이트 안내: 없음 → 최신 0.3.0 · 최소 –", "공지 수정: 점검 바뀜", "공지 추가: 새 공지", "공지 삭제: 옛 공지"])
        self.assertEqual(dev_admin.get_changes(remote, remote), [])


if __name__ == "__main__":
    unittest.main()
