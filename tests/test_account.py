"""account — 회원 권한 거르기·써 보기·브라우저 로그인(가짜 회원 API + 가짜 브라우저)·하루 1회 확인·로그아웃."""
import datetime
import http.client
import http.server
import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import account
import constants

NOW = datetime.datetime(2026, 11, 16, tzinfo=datetime.timezone.utc)
ENTITLEMENT = {"plan": "free", "plan_name": "Member", "features": ["detail_advanced"], "valid_until": ""}
ADVANCED = constants.FEATURES["detail_advanced"]["options"]


class FakeApi(object):
    """회원 API 흉내 — claim(교환권 하나)·me·logout. 받은 요청을 calls에 남긴다."""

    def __init__(self):
        self.calls, self.grants, self.tokens = [], {"good-grant": "tok-1"}, {"tok-1"}
        api = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])).decode("utf-8"))
                api.calls.append(body)
                action = body.get("action")
                if action == "claim":
                    token = api.grants.pop(body.get("grant"), None)
                    out = {"ok": True, "token": token, "email": "a@x.com", "entitlement": ENTITLEMENT} if token else {"ok": False, "error": "invalid"}
                elif action == "me":
                    out = {"ok": True, "email": "b@x.com", "entitlement": dict(ENTITLEMENT, plan_name="Pro")} if body.get("token") in api.tokens \
                        else {"ok": False, "error": "invalid"}
                elif action == "logout":
                    api.tokens.discard(body.get("token"))
                    out = {"ok": True}
                else:
                    out = {"ok": False, "error": "unknown_action"}
                data = json.dumps(out).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
        self.url = "http://127.0.0.1:%d/exec" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class AccountTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "account.json")
        self.api = FakeApi()
        self.saved = {k: getattr(constants, k) for k in ("ACCOUNT_API_URL", "ACCOUNT_ENABLED", "ACCOUNT_DONE_URL")}
        constants.ACCOUNT_API_URL = self.api.url
        constants.ACCOUNT_ENABLED = True
        constants.ACCOUNT_DONE_URL = "https://gorani.site/login/done/"

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(constants, k, v)
        self.api.close()
        self.tmp.cleanup()

    def member(self, days_ago=1):
        return {"token": "tok-1", "email": "a@x.com", "entitlement": ENTITLEMENT, "checked_at": (NOW - datetime.timedelta(days=days_ago)).isoformat()}


class AllowedOptionsTest(AccountTestBase):
    def options(self, level="advanced"):
        return dict(dict.fromkeys(ADVANCED, True), detail_level=level, detail_curb=True)

    def test_guest_without_trial_gets_basic(self):
        options, used = account.get_allowed_options(self.options(), {}, now=NOW)
        self.assertEqual(options["detail_level"], "basic")
        self.assertFalse(any(options[k] for k in ADVANCED))
        self.assertTrue(options["detail_curb"])   # 연석은 수준과 따로 — 누구나
        self.assertEqual(used, [])

    def test_guest_trial_opens_once_only_when_advanced_chosen(self):
        options, used = account.get_allowed_options(self.options(), {}, trial=True, now=NOW)
        self.assertEqual(options["detail_level"], "advanced")
        self.assertEqual(used, ["detail_advanced"])
        options, used = account.get_allowed_options(self.options("basic"), {}, trial=True, now=NOW)
        self.assertEqual(used, [], "기본으로 만들면 써 보기를 쓰지 않는다")
        spent = {"trials_used": {"detail_advanced": constants.GUEST_TRIALS["detail_advanced"]}}
        options, used = account.get_allowed_options(self.options(), spent, trial=True, now=NOW)
        self.assertEqual((options["detail_level"], used), ("basic", []))

    def test_member_keeps_and_expired_loses(self):
        options, used = account.get_allowed_options(self.options(), self.member(), now=NOW)
        self.assertEqual((options["detail_level"], used), ("advanced", []))
        stale = self.member(days_ago=constants.ACCOUNT_OFFLINE_DAYS + 1)
        self.assertEqual(account.get_state(stale, NOW), "expired")
        self.assertEqual(account.get_allowed_options(self.options(), stale, now=NOW)[0]["detail_level"], "basic")

    def test_disabled_opens_everything(self):   # ACCOUNT_ENABLED 꺼짐·Blender — 고급 누구나
        options, _ = account.get_allowed_options(self.options(), {}, enabled=False, now=NOW)
        self.assertEqual(options["detail_level"], "advanced")
        self.assertFalse(account.is_enabled("blender"))
        constants.ACCOUNT_API_URL = ""
        self.assertFalse(account.is_enabled("rhino"))

    def test_driver_without_level(self):   # 수준 없이 키마다 켠 요청도 거른다
        options, _ = account.get_allowed_options({"building_parapet": True}, {}, now=NOW)
        self.assertFalse(options["building_parapet"])
        self.assertNotIn("detail_level", options)


class StateTest(AccountTestBase):
    def test_trials_and_logout_keeps_them(self):
        account.add_trial("detail_advanced", self.path)
        account.add_trial("detail_advanced", self.path)
        data = account.load(self.path)
        self.assertEqual(account.get_trials_left(data, "detail_advanced"), constants.GUEST_TRIALS["detail_advanced"] - 2)
        account.save(dict(data, **self.member()), self.path)
        account.logout(self.path)
        data = account.load(self.path)
        self.assertNotIn("token", data)
        self.assertEqual(data["trials_used"]["detail_advanced"], 2)
        self.assertEqual(self.api.calls[-1], {"action": "logout", "token": "tok-1"})

    def test_logout_offline_still_signs_out(self):
        account.save(self.member(), self.path)
        self.api.close()
        constants.ACCOUNT_API_URL = "http://127.0.0.1:9/exec"   # 닫힌 포트
        self.assertNotIn("token", account.logout(self.path))

    def test_panel_state(self):
        guest = account.get_panel_state({}, "rhino", NOW)
        self.assertEqual((guest["enabled"], guest["state"], guest["email"], guest["plan_name"]), (True, "guest", "", "Guest"))
        self.assertEqual(guest["trials_left"], {"detail_advanced": constants.GUEST_TRIALS["detail_advanced"]})
        member = account.get_panel_state(self.member(), "rhino", NOW)
        self.assertEqual((member["state"], member["email"], member["features"]), ("member", "a@x.com", ["detail_advanced"]))
        self.assertFalse(account.get_panel_state(self.member(), "blender", NOW)["enabled"])

    def test_refresh(self):
        account.save(self.member(days_ago=2), self.path)
        data = account.refresh(self.path, now=NOW)
        self.assertEqual((data["email"], data["entitlement"]["plan_name"], data["checked_at"]), ("b@x.com", "Pro", NOW.isoformat()))
        self.api.tokens.clear()   # 서버에서 끊음·탈퇴
        self.assertNotIn("token", account.refresh(self.path, now=NOW))

    def test_refresh_offline_keeps(self):
        account.save(self.member(days_ago=2), self.path)
        self.api.close()
        constants.ACCOUNT_API_URL = "http://127.0.0.1:9/exec"
        self.assertEqual(account.refresh(self.path, now=NOW)["token"], "tok-1")

    def test_flag(self):
        account.set_flag("login_prompt_seen", True, self.path)
        self.assertTrue(account.load(self.path)["login_prompt_seen"])
        with self.assertRaises(ValueError):
            account.set_flag("token", "x", self.path)


class LoginTest(AccountTestBase):
    def browser(self, login, **query):   # 웹 /login/이 넘기는 주소를 그대로 부른다(넘겨받은 302는 따라가지 않는다)
        conn = http.client.HTTPConnection("127.0.0.1", login.port, timeout=5)
        conn.request("GET", account.LOGIN_PATH + "?" + urllib.parse.urlencode(query))
        response = conn.getresponse()
        location = response.getheader("Location") or ""
        conn.close()
        return response.status, location

    def test_url_carries_port_state_host(self):
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        try:
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(login.url).query)
            self.assertTrue(login.url.startswith(constants.ACCOUNT_LOGIN_URL))
            self.assertEqual((query["port"], query["h"], query["lang"]), ([str(login.port)], ["rhino"], ["ko"]))
            self.assertEqual(query["state"], [login.state])
        finally:
            login.close()

    def test_success(self):
        login = account.Login("rhino", "0.4.0", "en", self.path)
        try:
            self.assertEqual(self.browser(login, state="wrong", grant="good-grant")[0], 400)   # 남의 링크
            self.assertIsNone(login.poll())
            status, location = self.browser(login, state=login.state, grant="good-grant")
            self.assertEqual(status, 302)
            self.assertEqual(location, constants.ACCOUNT_DONE_URL + "?ok=1&lang=en")
            self.assertEqual(login.poll(), {"ok": True})
            data = account.load(self.path)
            self.assertEqual((data["token"], data["email"]), ("tok-1", "a@x.com"))
            self.assertEqual(self.api.calls[0], {"action": "claim", "grant": "good-grant", "version": "0.4.0"})
        finally:
            login.close()

    def test_bad_grant(self):
        login = account.Login("sketchup", "0.4.0", "ko", self.path)
        try:
            status, location = self.browser(login, state=login.state, grant="used")
            self.assertEqual((status, location.endswith("ok=0&lang=ko")), (302, True))
            self.assertEqual(login.poll(), {"ok": False, "error": "invalid"})
            self.assertNotIn("token", account.load(self.path))
        finally:
            login.close()

    def test_timeout_and_close_twice(self):
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        login.deadline = 0
        self.assertEqual(login.poll(), {"ok": False, "error": "timeout"})
        login.close()   # 이미 닫혔어도 된다


if __name__ == "__main__":
    unittest.main()
