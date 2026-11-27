"""account — 회원 권한 거르기·써 보기·브라우저 로그인(가짜 Firebase + 가짜 브라우저)·확인·로그아웃·로그인 고장이면 열기·생성 기록."""
import base64
import datetime
import http.client
import http.server
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

import account
import constants

NOW = datetime.datetime(2026, 11, 19, tzinfo=datetime.timezone.utc)
ADVANCED = constants.FEATURES["detail_advanced"]["options"]


def make_id_token(claims):
    part = base64.urlsafe_b64encode(json.dumps(claims).encode("utf-8")).decode("ascii").rstrip("=")
    return "e30." + part + ".sig"


class FakeFirebase(object):
    """securetoken·Realtime Database·로그인 페이지 흉내. 열쇠 → (uid, 토큰 값). DB는 메모리 나무, 토큰의 uid와 경로 uid가 다르면 401."""

    def __init__(self):
        self.keys = {"rt-1": ("u1", {"email": "a@x.com"})}   # 열쇠 → (uid, 토큰 값)
        self.disabled = set()   # 사용 중지된 uid
        self.fail = None        # None | 500 | "config" — 고장 흉내
        self.db = {}
        self.calls = []
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _reply(self, status, value):
                data = json.dumps(value).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                return self.rfile.read(int(self.headers.get("Content-Length") or 0)).decode("utf-8")

            def _handle(self):
                parts = urllib.parse.urlsplit(self.path)
                query = urllib.parse.parse_qs(parts.query)
                fake.calls.append((self.command, parts.path))
                if fake.fail == 500:
                    return self._reply(503, {"error": {"code": 503, "message": "UNAVAILABLE"}})
                if parts.path == "/login/":
                    data = b"<html>login</html>"
                    self.send_response(200)
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    return self.wfile.write(data)
                if parts.path == "/v1/token":
                    if fake.fail == "config":
                        return self._reply(400, {"error": {"code": 400, "message": "API key not valid. Please pass a valid API key."}})
                    token = urllib.parse.parse_qs(self._body()).get("refresh_token", [""])[0]
                    if token not in fake.keys:
                        return self._reply(400, {"error": {"code": 400, "message": "INVALID_REFRESH_TOKEN"}})
                    uid, claims = fake.keys[token]
                    if uid in fake.disabled:
                        return self._reply(400, {"error": {"code": 400, "message": "USER_DISABLED"}})
                    return self._reply(200, {"id_token": make_id_token(dict(claims, user_id=uid, sub=uid)), "refresh_token": token,
                                             "expires_in": "3600", "user_id": uid})
                if parts.path.endswith(".json"):
                    keys = [k for k in parts.path[1:-len(".json")].split("/") if k]
                    auth = (query.get("auth") or [""])[0]
                    try:
                        uid = json.loads(base64.urlsafe_b64decode(auth.split(".")[1] + "==").decode("utf-8"))["user_id"]
                    except (IndexError, ValueError, KeyError):
                        uid = None
                    if len(keys) < 2 or keys[0] != "users" or keys[1] != uid:
                        return self._reply(401, {"error": "Permission denied"})
                    return self._db(keys, query)
                self._reply(404, {"error": "not found"})

            def _db(self, keys, query):
                node = fake.db
                for key in keys[:-1]:
                    node = node.setdefault(key, {}) if self.command in ("PUT", "PATCH") else (node.get(key) or {})
                last = keys[-1]
                if self.command == "GET":
                    value = node.get(last) if isinstance(node, dict) else None
                    if query.get("shallow") and isinstance(value, dict):
                        value = {k: True for k in value}
                    return self._reply(200, value)
                if self.command == "PUT":
                    node[last] = json.loads(self._body())
                    return self._reply(200, node[last])
                if self.command == "PATCH":
                    node.setdefault(last, {}).update(json.loads(self._body()))
                    return self._reply(200, node[last])
                if self.command == "DELETE":
                    if isinstance(node, dict):
                        node.pop(last, None)
                    return self._reply(200, None)

            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = "http://127.0.0.1:%d" % self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True).start()

    def node(self, *keys):
        value = self.db
        for key in keys:
            value = (value or {}).get(key) if isinstance(value, dict) else None
        return value

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class AccountTestBase(unittest.TestCase):
    NAMES = ("ACCOUNT_ENABLED", "ACCOUNT_FIREBASE", "ACCOUNT_TOKEN_URL", "ACCOUNT_LOGIN_URL", "ACCOUNT_DONE_URL", "ACCOUNT_PROBE_SECONDS",
             "ACCOUNT_TIMEOUT_SECONDS", "HISTORY_MAX")

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "account.json")
        self.fb = FakeFirebase()
        self.saved = {k: getattr(constants, k) for k in self.NAMES}
        constants.ACCOUNT_ENABLED = True
        constants.ACCOUNT_FIREBASE = {"api_key": "k", "project_id": "p", "db_url": self.fb.base}
        constants.ACCOUNT_TOKEN_URL = self.fb.base + "/v1/token"
        constants.ACCOUNT_LOGIN_URL = self.fb.base + "/login/"
        constants.ACCOUNT_DONE_URL = "https://gorani.site/login/done/"
        constants.ACCOUNT_PROBE_SECONDS = 2
        constants.ACCOUNT_TIMEOUT_SECONDS = 2

    def tearDown(self):
        for k, v in self.saved.items():
            setattr(constants, k, v)
        self.fb.close()
        self.tmp.cleanup()

    def member(self, **extra):
        return dict({"refresh_token": "rt-1", "uid": "u1", "email": "a@x.com", "entitlement": {"plan": "free", "valid_until": ""},
                     "checked_at": NOW.isoformat()}, **extra)

    def close_port(self):   # 고장 흉내 — 닫힌 포트
        dead = "http://127.0.0.1:9"
        constants.ACCOUNT_FIREBASE = dict(constants.ACCOUNT_FIREBASE, db_url=dead)
        constants.ACCOUNT_TOKEN_URL = dead + "/v1/token"
        constants.ACCOUNT_LOGIN_URL = dead + "/login/"


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
        self.assertEqual((options["detail_level"], used), ("advanced", ["detail_advanced"]))
        options, used = account.get_allowed_options(self.options("basic"), {}, trial=True, now=NOW)
        self.assertEqual(used, [], "기본으로 만들면 써 보기를 쓰지 않는다")
        spent = {"trials_used": {"detail_advanced": constants.GUEST_TRIALS["detail_advanced"]}}
        options, used = account.get_allowed_options(self.options(), spent, trial=True, now=NOW)
        self.assertEqual((options["detail_level"], used), ("basic", []))

    def test_member_never_expires(self):   # 30일 만료 없앰 — 오래 확인 못 해도 회원
        old = self.member(checked_at=(NOW - datetime.timedelta(days=400)).isoformat())
        self.assertEqual(account.get_state(old), "member")
        self.assertEqual(account.get_allowed_options(self.options(), old, now=NOW)[0]["detail_level"], "advanced")

    def test_plan_from_remote_config_and_until(self):
        pro = self.member(entitlement={"plan": "pro", "valid_until": (NOW + datetime.timedelta(days=1)).isoformat()})
        saved = constants.PLAN_FEATURES
        try:
            constants.PLAN_FEATURES = {"free": ["detail_advanced"], "pro": ["detail_advanced", "laser_cut"]}
            self.assertIn("laser_cut", account.get_features(pro, now=NOW))
            later = NOW + datetime.timedelta(days=2)   # 기한이 지나면 free
            self.assertEqual((account.get_plan(pro, later), account.get_features(pro, now=later)), ("free", ["detail_advanced"]))
        finally:
            constants.PLAN_FEATURES = saved

    def test_disabled_and_fallback_open_everything(self):   # ACCOUNT_ENABLED 꺼짐·Blender·로그인 고장으로 연 실행 — 고급 누구나
        options, _ = account.get_allowed_options(self.options(), {}, enabled=False, now=NOW)
        self.assertEqual(options["detail_level"], "advanced")
        self.assertFalse(account.is_enabled("blender"))
        constants.ACCOUNT_FIREBASE = {"api_key": "", "project_id": "", "db_url": ""}
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
        self.fb.db = {"users": {"u1": {"connections": {"c1": {"host": "rhino", "created": 1}}}}}
        account.save(dict(data, **self.member(conn_id="c1", conn_registered=True)), self.path)
        data = account.logout(self.path)
        self.assertNotIn("refresh_token", data)
        self.assertEqual(data["trials_used"]["detail_advanced"], 2)
        for _ in range(50):   # 연결 줄 지우기는 데몬 스레드
            if not self.fb.node("users", "u1", "connections", "c1"):
                break
            time.sleep(0.05)
        self.assertIsNone(self.fb.node("users", "u1", "connections", "c1"))

    def test_logout_offline_still_signs_out(self):
        account.save(self.member(conn_id="c1", conn_registered=True), self.path)
        self.close_port()
        self.assertNotIn("refresh_token", account.logout(self.path))

    def test_panel_state(self):
        guest = account.get_panel_state({}, "rhino", now=NOW)
        self.assertEqual((guest["enabled"], guest["state"], guest["email"], guest["plan_name"], guest["fallback"]), (True, "guest", "", "Guest", False))
        self.assertEqual(guest["trials_left"], {"detail_advanced": constants.GUEST_TRIALS["detail_advanced"]})
        self.assertEqual(guest["features"], [])
        member = account.get_panel_state(self.member(), "rhino", now=NOW)
        self.assertEqual((member["state"], member["email"], member["plan_name"]), ("member", "a@x.com", "Member"))
        self.assertEqual(member["features"], constants.PLAN_FEATURES["free"])
        self.assertFalse(account.get_panel_state(self.member(), "blender", now=NOW)["enabled"])
        fallback = account.get_panel_state({}, "rhino", fallback=True, now=NOW)   # 로그인 고장 — 기능 전부, 처음 만들 때 창 없음, 로그인은 그대로
        self.assertEqual((fallback["enabled"], fallback["state"], fallback["fallback"], fallback["prompt_on_build"]), (True, "guest", True, "off"))
        self.assertEqual(sorted(fallback["features"]), sorted(constants.FEATURES))

    def test_refresh_updates_and_registers(self):
        self.fb.keys["rt-1"] = ("u1", {"email": "b@x.com", "plan": "pro"})
        account.save(self.member(), self.path)
        data = account.refresh("rhino", "0.4.0", self.path, now=NOW)
        self.assertEqual((data["email"], data["entitlement"]["plan"], data["checked_at"]), ("b@x.com", "pro", NOW.isoformat()))
        self.assertTrue(data["conn_registered"])   # 로그인 때 못 한 등록을 다시
        row = self.fb.node("users", "u1", "connections", data["conn_id"])
        self.assertEqual((row["host"], row["version"]), ("rhino", "0.4.0"))

    def test_refresh_denied_logs_out(self):   # 사용 중지·탈퇴 — 확실한 거절
        account.save(self.member(), self.path)
        self.fb.disabled.add("u1")
        self.assertNotIn("refresh_token", account.refresh(path=self.path, now=NOW))

    def test_refresh_down_keeps(self):   # 접속 안 됨·5xx·설정 실수는 고장 — 그대로 회원
        account.save(self.member(), self.path)
        self.fb.fail = 500
        self.assertEqual(account.refresh(path=self.path, now=NOW)["refresh_token"], "rt-1")
        self.fb.fail = "config"
        self.assertEqual(account.refresh(path=self.path, now=NOW)["refresh_token"], "rt-1")
        self.close_port()
        self.assertEqual(account.refresh(path=self.path, now=NOW)["refresh_token"], "rt-1")

    def test_refresh_revoked_connection_logs_out(self):   # 웹에서 이 PC 해제 — 등록된 적 있는 줄이 없어졌다
        account.save(self.member(conn_id="c1", conn_registered=True), self.path)
        self.fb.db = {"users": {"u1": {"connections": {"c1": {"host": "rhino", "created": 1, "seen": 1}}}}}
        data = account.refresh(path=self.path, now=NOW)
        self.assertEqual(data["refresh_token"], "rt-1")
        self.assertEqual(self.fb.node("users", "u1", "connections", "c1", "seen"), int(NOW.timestamp() * 1000))
        self.fb.db["users"]["u1"]["connections"] = {}
        self.assertNotIn("refresh_token", account.refresh(path=self.path, now=NOW))

    def test_flag(self):
        account.set_flag("login_prompt_seen", True, self.path)
        self.assertTrue(account.load(self.path)["login_prompt_seen"])
        with self.assertRaises(ValueError):
            account.set_flag("refresh_token", "x", self.path)

    def test_service_probe(self):
        self.assertTrue(account.is_service_up())
        self.fb.fail = "config"   # 설정 실수 — 고장으로 본다
        self.assertFalse(account.is_service_up())
        self.close_port()
        self.assertFalse(account.is_service_up())


class LoginTest(AccountTestBase):
    def browser(self, login, **form):   # 웹 /login/이 하는 폼 POST를 그대로 한다(넘겨받은 302는 따라가지 않는다)
        conn = http.client.HTTPConnection("127.0.0.1", login.port, timeout=5)
        conn.request("POST", account.LOGIN_PATH, urllib.parse.urlencode(form), {"Content-Type": "application/x-www-form-urlencoded"})
        response = conn.getresponse()
        location = response.getheader("Location") or ""
        conn.close()
        return response.status, location

    def wait_url(self, login):
        for _ in range(100):
            url = login.take_url()
            if url or login.poll() is not None:
                return url
            time.sleep(0.02)
        return ""

    def test_url_after_probe(self):
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        try:
            url = self.wait_url(login)
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
            self.assertTrue(url.startswith(constants.ACCOUNT_LOGIN_URL))
            self.assertEqual((query["port"], query["h"], query["lang"], query["state"]), ([str(login.port)], ["rhino"], ["ko"], [login.state]))
            self.assertEqual(login.take_url(), "", "주소는 한 번만")
        finally:
            login.close()

    def test_success(self):
        login = account.Login("rhino", "0.4.0", "en", self.path)
        try:
            self.wait_url(login)
            self.assertEqual(self.browser(login, state="wrong", refresh_token="rt-1")[0], 400)   # 남의 링크
            self.assertIsNone(login.poll())
            status, location = self.browser(login, state=login.state, refresh_token="rt-1")
            self.assertEqual((status, location), (302, constants.ACCOUNT_DONE_URL + "?ok=1&lang=en&h=rhino"))
            self.assertEqual(login.poll(), {"ok": True})
            data = account.load(self.path)
            self.assertEqual((data["refresh_token"], data["uid"], data["email"]), ("rt-1", "u1", "a@x.com"))
            self.assertEqual(self.fb.node("users", "u1", "connections", data["conn_id"], "host"), "rhino")
        finally:
            login.close()

    def test_idle_connection_does_not_block(self):   # 크롬이 미리 열어 두는 빈 연결 — 받는 곳·poll·close가 멈추지 않는다(2026-11-19 실제 시험)
        import socket
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        try:
            self.wait_url(login)
            idle = socket.create_connection(("127.0.0.1", login.port), timeout=5)   # 요청을 보내지 않는 연결
            try:
                status, _location = self.browser(login, state=login.state, refresh_token="rt-1")
                self.assertEqual(status, 302)
                started = time.time()
                self.assertEqual(login.poll(), {"ok": True})
                self.assertLess(time.time() - started, 1.0, "poll(close)이 빈 연결을 기다렸다")
            finally:
                idle.close()
        finally:
            login.close()

    def test_bad_token_is_denied(self):
        login = account.Login("sketchup", "0.4.0", "ko", self.path)
        try:
            self.wait_url(login)
            status, location = self.browser(login, state=login.state, refresh_token="used")
            self.assertEqual((status, location.endswith("?ok=0&lang=ko&h=sketchup")), (302, True))
            self.assertEqual(login.poll(), {"ok": False, "error": "INVALID_REFRESH_TOKEN"})
            self.assertNotIn("refresh_token", account.load(self.path))
        finally:
            login.close()

    def test_web_error_opens(self):   # 웹이 구글·Firebase에 닿지 못함 — 연다
        login = account.Login("archicad", "0.4.0", "ko", self.path)
        try:
            self.wait_url(login)
            status, location = self.browser(login, state=login.state, error="service")
            self.assertEqual((status, location), (302, constants.ACCOUNT_DONE_URL + "?fallback=1&lang=ko&h=archicad"))
            self.assertEqual(login.poll(), {"ok": False, "fallback": True, "error": "web_service"})
        finally:
            login.close()

    def test_firebase_down_after_web_opens(self):   # 웹은 열쇠를 넘겼는데 플러그인이 Firebase에 닿지 못함 — 연다
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        try:
            self.wait_url(login)
            self.fb.fail = "config"
            status, location = self.browser(login, state=login.state, refresh_token="rt-1")
            self.assertTrue(location.startswith(constants.ACCOUNT_DONE_URL + "?fallback=1"))
            self.assertTrue(login.poll()["fallback"])
        finally:
            login.close()

    def test_probe_down_opens_without_browser(self):
        self.close_port()
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        try:
            self.assertEqual(self.wait_url(login), "")
            self.assertEqual(login.result, {"ok": False, "fallback": True, "error": "probe"})
        finally:
            login.close()

    def test_timeout_checks_again(self):
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        self.wait_url(login)
        login.deadline = 0
        result = None
        for _ in range(100):   # 다시 재는 동안은 None
            result = login.poll()
            if result:
                break
            time.sleep(0.02)
        self.assertEqual(result, {"ok": False, "error": "timeout"}, "살아 있으면 열지 않는다 — 사용자가 끝내지 않은 것")
        login.close()   # 이미 닫혔어도 된다

    def test_timeout_when_down_opens(self):
        login = account.Login("rhino", "0.4.0", "ko", self.path)
        self.wait_url(login)
        self.fb.fail = 500
        login.deadline = 0
        result = None
        for _ in range(100):
            result = login.poll()
            if result:
                break
            time.sleep(0.02)
        self.assertEqual(result, {"ok": False, "fallback": True, "error": "timeout_down"})


class HistoryTest(AccountTestBase):
    STATE = {"entry_id": "20261119010203-abcdef", "label": "성수동2가 277-17", "lot_name": "성수동2가_277-17",
             "target": {"mode": "lots", "pnus": ["1120011500102770017"]}, "options": {"radius": 250, "shape": "rect", "detail_level": "advanced"},
             "context": {"buildings": 812}, "target_lnglat": {"center": [127.0561234567, 37.5441234567], "ring": []}}

    def test_entry(self):
        entry_id, entry = account.get_history_entry(self.STATE, "rhino", "0.4.0", now=NOW)
        self.assertEqual(entry_id, "20261119010203-abcdef")
        self.assertEqual((entry["host"], entry["mode"], entry["detail"], entry["shape"], entry["radius"], entry["buildings"]),
                         ("rhino", "lots", "advanced", "rect", 250, 812))
        self.assertEqual(json.loads(entry["target"]), {"pnus": ["1120011500102770017"]})
        self.assertEqual(entry["center"], [127.056123, 37.544123])
        self.assertNotIn("dir", entry)   # 폴더 경로는 넣지 않는다
        area = dict(self.STATE, target={"mode": "area"}, target_lnglat={"center": [1, 2], "ring": [[i * 0.001, 0] for i in range(1000)]})
        self.assertLessEqual(len(json.loads(account.get_history_entry(area, "rhino", "0.4.0")[1]["target"])["ring"]), 200)
        self.assertEqual(account.get_history_entry(dict(self.STATE, entry_id=""), "rhino", "0.4.0"), (None, None))   # 옛 결과

    def test_send_queue_and_flush(self):
        account.save(self.member(), self.path)
        entry_id, entry = account.get_history_entry(self.STATE, "rhino", "0.4.0", now=NOW)
        self.fb.fail = 500
        self.assertFalse(account.add_history(entry_id, entry, self.path))   # 고장 — 줄에 남는다
        self.assertEqual([p[0] for p in account.load(self.path)["pending_history"]], [entry_id])
        self.fb.fail = None
        account.refresh("rhino", "0.4.0", self.path, now=NOW)   # 다음 확인 때 보낸다
        self.assertEqual(self.fb.node("users", "u1", "history", entry_id, "label"), "성수동2가 277-17")
        self.assertEqual(account.load(self.path)["pending_history"], [])

    def test_trim_keeps_starred(self):
        constants.HISTORY_MAX = 2
        account.save(self.member(), self.path)
        self.fb.db = {"users": {"u1": {"history": {"a": {"built_at": 1, "host": "rhino", "star": True}, "b": {"built_at": 2, "host": "rhino"}}}}}
        entry_id, entry = account.get_history_entry(self.STATE, "rhino", "0.4.0", now=NOW)
        self.assertTrue(account.add_history(entry_id, entry, self.path))
        self.assertEqual(sorted(self.fb.node("users", "u1", "history")), sorted(["a", entry_id]))   # b(오래된·즐겨찾기 아님)가 빠짐

    def test_list_change_delete(self):
        account.save(self.member(), self.path)
        entry_id, entry = account.get_history_entry(self.STATE, "rhino", "0.4.0", now=NOW)
        account.add_history(entry_id, entry, self.path)
        listed = account.get_history(self.path)
        self.assertTrue(listed["ok"])
        self.assertEqual((listed["items"][0]["id"], listed["items"][0]["target"]["pnus"][0]), (entry_id, "1120011500102770017"))
        self.assertTrue(account.change_history(entry_id, {"star": True, "label": "우리 대지", "dir": "/x"}, path=self.path, now=NOW))
        row = self.fb.node("users", "u1", "history", entry_id)
        self.assertEqual((row["star"], row["label"], "dir" in row), (True, "우리 대지", False))
        self.assertTrue(account.change_history(entry_id, {"made_2d": '{"basemap": "A3", "sheets": 9, "tables": true}'}, path=self.path, now=NOW))
        self.assertEqual(account.get_history(self.path)["items"][0]["made_2d"], {"basemap": "A3", "sheets": 9, "tables": True})   # JSON 글을 푼다
        self.assertTrue(account.change_history(entry_id, delete=True, path=self.path))
        self.assertIsNone(self.fb.node("users", "u1", "history", entry_id))
        self.fb.fail = 500
        self.assertFalse(account.get_history(self.path)["ok"])   # 고장 — 화면은 이 PC 기록만


class Made2dSummaryTest(unittest.TestCase):
    def test_summary(self):   # 웹 계정 페이지 out2dText 꼴 — 베이스맵 = 마지막 용지, 다이어그램 = 가장 많이, 조서 = 하나라도
        runs = [{"made2d": {"basemap": {"ready": True, "paper": "A3"}, "sheets": [1, 2], "tables": []}},
                {"made2d": None},
                {"made2d": {"basemap": {"ready": False}, "sheets": [1, 2, 3], "tables": [{"name": "parcels"}]}},
                {"made2d": {"basemap": {"ready": True, "paper": "A1"}, "sheets": [], "tables": []}}]
        self.assertEqual(account.get_made_2d_summary(runs), {"basemap": "A1", "sheets": 3, "tables": True})
        self.assertIsNone(account.get_made_2d_summary([{"made2d": None}]))
        self.assertIsNone(account.get_made_2d_summary([]))


if __name__ == "__main__":
    unittest.main()
