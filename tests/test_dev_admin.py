"""관리자 페이지(dev_admin)의 공지 검사·바뀐 점 문장. 네트워크·서버 없이 돈다."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import dev_admin  # noqa: E402
import dev_stats  # noqa: E402

NOTICE = {"id": "2026-10-21-1", "level": "info", "date": "2026-10-21", "text": "점검", "url": "https://example.com"}


class NoticeErrorsTest(unittest.TestCase):
    def test_valid(self):
        data = {"update": {"latest": dev_admin.constants.PANEL_VERSION, "min": "0.0.1"}, "notices": [NOTICE]}
        self.assertEqual(dev_admin.get_notice_errors(data), [])
        self.assertEqual(dev_admin.get_notice_errors({"update": None, "notices": []}), [])

    def test_bad_values(self):
        data = {"update": {"latest": "0.0.1", "min": "0.0.2"},
                "notices": [NOTICE, dict(NOTICE, text="", level="loud", url="example.com")]}
        errors = dev_admin.get_notice_errors(data)
        self.assertIn("사용 불가 기준이 새 버전보다 높습니다", errors)
        self.assertTrue(any("겹칩니다" in e for e in errors))
        self.assertTrue(any("글이 비었습니다" in e for e in errors))
        self.assertTrue(any("https://" in e for e in errors))
        self.assertEqual(dev_admin.get_notice_errors({"update": {"latest": "v0.3"}, "notices": []}),
                         ["새 버전은 0.3.0처럼 숫자와 점만 씁니다"])

    def test_unreleased_version_blocks(self):   # 아직 배포 안 한 버전 — min이면 모두 차단, latest면 없는 버전으로 안내
        version = dev_admin.constants.PANEL_VERSION
        self.assertEqual(dev_admin.get_notice_errors({"update": {"latest": version, "min": version}, "notices": []}), [])
        errors = dev_admin.get_notice_errors({"update": {"latest": version + ".1", "min": version + ".1"}, "notices": []})
        self.assertTrue(any("있지도 않은 버전" in e for e in errors))
        self.assertTrue(any("모든 사용자가 막힙니다" in e for e in errors))
        self.assertEqual(dev_admin.get_notice_errors({"update": {"min": "0.0.1"}, "notices": []}), ["알릴 새 버전을 적으세요"])

    def test_version_compare_matches_panel(self):   # 패널 cmpVer: 빈 자리 = 0
        self.assertEqual(dev_admin.get_version_key("0.10.0") > dev_admin.get_version_key("0.9"), True)


class ChangesTest(unittest.TestCase):
    def test_changes(self):
        remote = {"update": None, "notices": [NOTICE, dict(NOTICE, id="old", text="옛 공지")]}
        local = {"update": {"latest": "0.3.0"}, "notices": [dict(NOTICE, text="점검 바뀜"), dict(NOTICE, id="new", text="새 공지")]}
        self.assertEqual(dev_admin.get_changes(local, remote), [
            "버전 안내: 없음 → 새 버전 0.3.0", "공지 수정: 점검 바뀜", "새 공지: 새 공지", "공지 내림: 옛 공지"])
        self.assertEqual(dev_admin.get_changes(remote, remote), [])


class StatsTest(unittest.TestCase):

    def test_split_counts(self):
        rows = [["11110,11140", 2.0], ["11110", 1.0], ["(not set)", 9.0]]
        self.assertEqual(dev_stats.get_split_counts(rows, {"11110": "서울특별시 종로구"}),
                         [["11110 서울특별시 종로구", 3.0], ["11140", 2.0]])

    def test_gate_summary(self):
        import datetime
        lines = ['2026-10-21T01:00:00+00:00 1.2.3.4 200 100 "/11110_context.db.xz" "Gorani/0.3.1" "abc"',
                 '2026-10-21T02:00:00+00:00 1.2.3.4 206 50 "/11110_context.db.xz" "Gorani/0.3.1" "abc"',
                 '2026-10-21T03:00:00+00:00 1.2.3.5 429 0 "/11110_terrain.db.xz" "Gorani/0.3.1" "def"',
                 '2026-10-21T04:00:00+00:00 9.9.9.9 404 181 "/favicon.ico" "Scanner" "-"',
                 '2026-09-10T00:00:00+00:00 1.2.3.4 200 999 "/11110_context.db.xz" "Gorani/0.1" "old"']
        period = dev_stats.get_period(30, datetime.date(2026, 10, 22))
        summary = dev_stats.get_gate_summary(lines, period, {"11110_context.db": "종로구 건물"},
                                             datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc))
        self.assertEqual((summary["downloads"], summary["bytes"], summary["installs"]), ([2, 1], [150, 999], [1, 1]))
        self.assertEqual((summary["rejected"], summary["month_bytes"]), ({"403": 0, "429": 1}, 150))
        self.assertEqual(summary["packs"], [["종로구 건물", 2, 150]])
        self.assertEqual(sum(summary["daily"]["downloads"]), 2)
        mine = dev_stats.get_gate_summary(lines, period, {}, datetime.datetime(2026, 10, 22, tzinfo=datetime.timezone.utc), dev_clients={"abc"})
        self.assertEqual((mine["downloads"], mine["rejected"]["429"]), ([0, 1], 1))   # 내 설치 abc를 빼면 이번 기간 받기 0

    def test_dev_filter_joins_event_filter(self):
        import datetime
        body = dev_stats._report(dev_stats.get_period(7, datetime.date(2026, 10, 22)), ["date"], ["eventCount"], event="build", exclude_dev=True)
        expressions = body["dimensionFilter"]["andGroup"]["expressions"]
        self.assertEqual(expressions[1]["notExpression"]["filter"]["fieldName"], "customEvent:dev")

    def test_app_stats_parses_ga_reports(self):
        """가짜 GA 응답(batchRunReports 모양)으로 사용자 비교·날짜별·매개변수·대상지 점·지역을 읽는지."""
        import datetime
        period = dev_stats.get_period(3, datetime.date(2026, 10, 22))

        def report(dims, metrics, rows):
            return {"dimensionHeaders": [{"name": d} for d in dims], "metricHeaders": [{"name": m} for m in metrics],
                    "rows": [{"dimensionValues": [{"value": v} for v in r[:len(dims)]],
                              "metricValues": [{"value": str(v)} for v in r[len(dims):]]} for r in rows]}

        def run(requests):
            out = []
            for body in requests:
                dims = [d["name"] for d in body["dimensions"]] + (["dateRange"] if len(body["dateRanges"]) > 1 else [])
                metrics = [m["name"] for m in body["metrics"]]
                key = tuple(dims)
                rows = {("dateRange",): [["cur", 10, 4], ["prev", 8, 2]],
                        ("eventName", "dateRange"): [["build", "cur", 30, 6], ["build", "prev", 20, 5], ["panel_open", "cur", 50, 10]],
                        ("date",): [["20261021", 5, 2], ["20261022", 7, 1]],
                        ("date", "eventName"): [["20261022", "build", 9]],
                        ("eventName", "customEvent:version"): [["panel_open", "0.3.2", 7], ["build", "(not set)", 30]],
                        ("customEvent:pnus",): [["1111010100100010000,1111010100100020000", 2], ["2635010500100010000", 1]],
                        ("customEvent:lng", "customEvent:lat"): [["126.97", "37.56", 3], ["(not set)", "(not set)", 1]],
                        }.get(key, [])
                out.append(report(dims, metrics, rows))
            return out

        metadata = {"dimensions": [{"apiName": "customEvent:version"}, {"apiName": "customEvent:pnus"},
                                   {"apiName": "customEvent:lng"}, {"apiName": "customEvent:lat"}], "metrics": []}
        stats = dev_stats.get_app_stats(run, period, metadata, {"11110": "종로구"})
        self.assertEqual(stats["totals"]["users"], [10, 8])
        self.assertEqual(stats["events"]["build"]["count"], [30, 20])
        self.assertEqual(stats["daily"]["users"], [0, 5, 7])
        self.assertEqual(stats["daily"]["builds"], [0, 0, 9])
        self.assertEqual(stats["dims"]["panel_open.version"], [["0.3.2", 7]])
        self.assertEqual(stats["dims"]["build.region"], [["11110 종로구", 2], ["26350", 1]])
        self.assertEqual(stats["points"], [[126.97, 37.56, 3]])
        self.assertIn("mode", stats["missing"])

    def test_insights(self):
        app = {"totals": {"users": [10, 20]}, "events": {"panel_open": {"users": [10, 0], "count": [10, 0]},
                                                       "build": {"users": [2, 0], "count": [3, 0]}},
               "dims": {"build.result": [["ok", 7], ["failed", 3]]}}
        insights = dev_stats.get_insights({"ga": {"apps": {"rhino": app}}, "bucket": {"size": 18, "limit": 20}})
        levels = dict((x["area"], x["level"]) for x in insights)
        self.assertEqual((levels["사용자"], levels["활성화"], levels["품질"], levels["서버"]), ("serious", "warning", "serious", "serious"))
        self.assertEqual(insights[0]["level"], "serious")


if __name__ == "__main__":
    unittest.main()
