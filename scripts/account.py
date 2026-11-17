"""회원 — 구글 로그인(gorani.site)으로 받은 연결 열쇠·권한을 ~/.gorani/account.json에 두고, 기능 키로 생성 옵션을 거른다.

설계는 docs/account_plan.md: 이용권(plan)은 서버(회원 API — 웹 저장소 tools/account)가 정하고, 플러그인은 기능(feature) 키만 본다.
로그인은 늘 시스템 브라우저에서 한다(구글이 앱 안 웹뷰 로그인을 막는다). 브라우저가 127.0.0.1의 받는 곳으로 일회용 교환권을 넘기면 claim으로 열쇠를 받는다.
표준 라이브러리만. 받는 곳 스레드·네트워크가 있어 Blender 패키지에서 뺀다(dev_deploy.BLENDER_EXCLUDED_NAMES — Blender판은 로그인 없이 전부 열림).
"""

import datetime
import http.server
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

import constants
import site_prefs

ACCOUNT_PATH = os.path.join(site_prefs.PREFS_DIR, "account.json")
LOGIN_PATH = "/gorani-login"   # 받는 곳 경로 — 웹 /login/이 이 주소로만 넘긴다


def load(path=ACCOUNT_PATH):
    # type: (str) -> dict
    """
    입력: account.json 경로.
    처리: 없거나 깨졌으면 빈 손님.
    출력: {token, email, entitlement{plan, plan_name, features, valid_until}, checked_at(ISO), trials_used{기능: 횟수}, login_prompt_seen}.
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(account, path=ACCOUNT_PATH):
    # type: (dict, str) -> None
    """account.json에 쓴다(임시 파일 → 바꿔치기 — 받는 곳 스레드와 패널이 겹쳐도 반쯤 쓴 파일이 남지 않게)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(account, f, ensure_ascii=False, indent=1)
    os.replace(temp, path)


def is_enabled(host_id=None):
    # type: (str) -> bool
    """회원 기능이 켜졌나 — 원격 설정 ACCOUNT_ENABLED, 회원 API 주소, 호스트(Blender·웹판은 없음)."""
    host = constants.HOST_LABELS.get(host_id or "", {})
    return bool(constants.ACCOUNT_ENABLED and constants.ACCOUNT_API_URL) and host.get("account", True)


def get_state(account, now=None):
    # type: (dict, datetime.datetime) -> str
    """'guest'(열쇠 없음) · 'member' · 'expired'(마지막 확인이 ACCOUNT_OFFLINE_DAYS를 넘음 — 권한은 손님처럼, 열쇠는 둔다)."""
    if not account.get("token"):
        return "guest"
    checked = _parse_time(account.get("checked_at"))
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if checked is None or now - checked > datetime.timedelta(days=constants.ACCOUNT_OFFLINE_DAYS):
        return "expired"
    return "member"


def get_features(account, enabled=True, now=None):
    # type: (dict, bool, datetime.datetime) -> list
    """지금 쓸 수 있는 기능 키. 회원 기능이 꺼졌으면 전부(누구나), 회원이면 서버가 준 권한, 아니면 GUEST_FEATURES."""
    if not enabled:
        return list(constants.FEATURES)
    if get_state(account, now) == "member":
        return list((account.get("entitlement") or {}).get("features") or [])
    return list(constants.GUEST_FEATURES)


def get_trials_left(account, key):
    # type: (dict, str) -> int
    """로그인 없이 써 볼 수 있는 남은 횟수(GUEST_TRIALS − 쓴 횟수)."""
    used = int((account.get("trials_used") or {}).get(key) or 0)
    return max(0, int(constants.GUEST_TRIALS.get(key) or 0) - used)


def get_allowed_options(options, account, trial=False, enabled=True, now=None):
    # type: (dict, dict, bool, bool, datetime.datetime) -> tuple
    """
    입력: 생성 options, account, trial(패널이 '로그인 없이 써 보기'를 골랐나), enabled(is_enabled).
    처리: 권한에 없는 기능은 그 옵션(FEATURES[키].options)을 끈다. trial이고 써 보기가 남았으면 이번만 연다.
          수준(detail_level)도 기본으로 — context_builder가 수준으로 고급 옵션을 다시 정하므로 키만 끄면 되살아난다.
    출력: (거른 options 사본, 써 보기로 연 기능 키 목록 — 그 기능을 실제로 고른 만들기만. 기본으로 만들면 써 보기를 쓰지 않는다).
    """
    options = dict(options or {})
    features = get_features(account, enabled, now)
    used = []
    for key, feature in constants.FEATURES.items():
        if key in features or not _wants(options, key, feature):
            continue
        if trial and get_trials_left(account, key) > 0:
            used.append(key)
            continue
        for option in feature.get("options") or []:
            options[option] = False
        if key == "detail_advanced" and "detail_level" in options:
            options["detail_level"] = "basic"
    return options, used


def add_trial(key, path=ACCOUNT_PATH):
    # type: (str, str) -> dict
    """써 보기 한 번을 센다(만들기가 성공했을 때만 — 실패·취소는 세지 않는다). 출력: 새 account."""
    account = load(path)
    used = dict(account.get("trials_used") or {})
    used[key] = int(used.get(key) or 0) + 1
    account["trials_used"] = used
    save(account, path)
    return account


def set_flag(key, value=True, path=ACCOUNT_PATH):
    # type: (str, object, str) -> None
    """패널 표시 기록(login_prompt_seen — 처음 만들 때 로그인 창을 봤다)."""
    if key not in ("login_prompt_seen",):
        raise ValueError(key)
    account = load(path)
    account[key] = value
    save(account, path)


def get_panel_state(account, host_id, now=None):
    # type: (dict, str, datetime.datetime) -> dict
    """
    입력: account, 호스트 id.
    출력: 패널 account 칸(panel_ui.md) — {enabled, state, email, plan_name, features, trials_left{기능: 남은 수}, prompt_on_build, prompt_seen}.
    """
    enabled = is_enabled(host_id)
    state = get_state(account, now) if enabled else "guest"
    entitlement = account.get("entitlement") or {}
    return {
        "enabled": enabled,
        "state": state,
        "email": (account.get("email") or "") if state != "guest" else "",
        "plan_name": (entitlement.get("plan_name") or "Member") if state == "member" else "Guest",
        "features": get_features(account, enabled, now),
        "trials_left": {key: get_trials_left(account, key) for key in constants.GUEST_TRIALS},
        "prompt_on_build": constants.LOGIN_PROMPT_ON_BUILD if enabled else "off",
        "prompt_seen": bool(account.get("login_prompt_seen")),
    }


def post(payload):
    # type: (dict) -> dict
    """
    입력: 회원 API 요청 {action, …}.
    처리: text/plain POST(JSON). 앱스 스크립트는 302로 결과 주소를 돌려주고 urllib가 GET으로 따라간다.
    출력: 응답 dict. 네트워크 실패는 OSError(URLError·시간 초과).
    """
    request = urllib.request.Request(constants.ACCOUNT_API_URL, data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "text/plain;charset=utf-8", "User-Agent": constants.OSM_USER_AGENT})
    with urllib.request.urlopen(request, timeout=constants.ACCOUNT_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def claim(grant, version, path=ACCOUNT_PATH, now=None):
    # type: (str, str, str, datetime.datetime) -> dict
    """교환권 → 연결 열쇠·권한을 받아 account.json에 둔다(써 보기 횟수·표시 기록은 그대로). 실패는 RuntimeError(오류 코드)."""
    result = post({"action": "claim", "grant": grant, "version": version})
    if not result.get("ok"):
        raise RuntimeError(result.get("error") or "invalid")
    account = load(path)
    account.update(token=result["token"], email=result.get("email") or "", entitlement=result.get("entitlement") or {},
                   checked_at=_iso(now))
    save(account, path)
    return account


def refresh(path=ACCOUNT_PATH, now=None):
    # type: (str, datetime.datetime) -> dict
    """
    입력: account.json 경로.
    처리: me로 권한을 다시 받는다. 열쇠가 무효(탈퇴·서버에서 끊음)면 로그아웃 상태로, 네트워크 실패면 그대로(30일까지 그대로 쓴다).
    출력: account.
    """
    account = load(path)
    if not account.get("token"):
        return account
    try:
        result = post({"action": "me", "token": account["token"]})
    except (OSError, ValueError):
        return account
    if result.get("ok"):
        account.update(email=result.get("email") or account.get("email") or "", entitlement=result.get("entitlement") or {}, checked_at=_iso(now))
    elif result.get("error") == "invalid":
        _clear(account)
    else:
        return account   # too_fast·server — 다음 확인 때
    save(account, path)
    return account


def refresh_later(path=ACCOUNT_PATH, now=None):
    # type: (str, datetime.datetime) -> bool
    """마지막 확인이 ACCOUNT_CHECK_HOURS를 넘었으면 데몬 스레드로 refresh — 패널을 열 때 기다리지 않게(결과는 다음에 열 때 보인다)."""
    account = load(path)
    checked = _parse_time(account.get("checked_at"))
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not account.get("token") or (checked and now - checked < datetime.timedelta(hours=constants.ACCOUNT_CHECK_HOURS)):
        return False
    threading.Thread(target=refresh, args=(path,), daemon=True).start()
    return True


def logout(path=ACCOUNT_PATH):
    # type: (str) -> dict
    """연결을 끊는다 — 서버 연결 줄 지우기는 되면 하고(오프라인이어도 로그아웃은 된다), 열쇠·메일·권한을 지운다. 써 보기 횟수는 남긴다."""
    account = load(path)
    if account.get("token"):
        try:
            post({"action": "logout", "token": account["token"]})
        except (OSError, ValueError):
            pass
    _clear(account)
    save(account, path)
    return account


class Login(object):
    """브라우저 로그인 한 번 — 127.0.0.1의 빈 포트에 받는 곳을 잠깐 열고, 돌아온 교환권을 claim한다.

    패널은 기다리는 동안 account_poll로 poll()을 부른다(받는 곳 스레드에서 패널로 바로 보내지 않는다 — 호스트마다 UI 스레드 규칙이 달라서).
    loader가 모듈을 다시 읽어도 컨트롤러가 이 객체를 들고 있어 그대로 쓴다.
    """

    def __init__(self, host_id, version, lang, path=ACCOUNT_PATH):
        self.state = secrets.token_urlsafe(24)
        self.result = None
        self.deadline = time.time() + constants.ACCOUNT_LOGIN_MINUTES * 60
        self._lock = threading.Lock()
        login = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parts = urllib.parse.urlsplit(self.path)
                query = urllib.parse.parse_qs(parts.query)
                if parts.path != LOGIN_PATH:
                    self.send_error(404)
                    return
                if (query.get("state") or [""])[0] != login.state or login.result is not None:
                    self.send_error(400)   # 남의 링크·옛 탭 — 이 패널이 연 로그인이 아니다
                    return
                try:
                    claim((query.get("grant") or [""])[0], version, path)
                    result = {"ok": True}
                except (RuntimeError, OSError, ValueError, KeyError) as error:
                    result = {"ok": False, "error": str(error) or "invalid"}
                with login._lock:
                    login.result = result
                self.send_response(302)
                self.send_header("Location", constants.ACCOUNT_DONE_URL + "?" + urllib.parse.urlencode(
                    {"ok": 1 if result["ok"] else 0, "lang": lang}))
                self.end_headers()

            def log_message(self, *args):
                pass

        self._server = http.server.HTTPServer(("127.0.0.1", 0), Handler)   # 127.0.0.1만 — Windows 방화벽 창이 뜨지 않는다
        self.port = self._server.server_address[1]
        self.url = constants.ACCOUNT_LOGIN_URL + "?" + urllib.parse.urlencode({"port": self.port, "state": self.state, "h": host_id, "lang": lang})
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()

    def poll(self):
        # type: () -> dict
        """돌아왔으면 {ok, error?}, 시간이 지났으면 {ok: False, error: 'timeout'}, 아직이면 None. 끝나면 받는 곳을 닫는다."""
        with self._lock:
            result = self.result
        if result is None and time.time() > self.deadline:
            result = {"ok": False, "error": "timeout"}
        if result is not None:
            self.close()
        return result

    def close(self):
        # type: () -> None
        """받는 곳을 닫는다(취소·끝·시간 초과). 두 번 불러도 된다."""
        server, self._server = self._server, None
        if server is not None:
            server.shutdown()
            server.server_close()


def _wants(options, key, feature):
    # 이번 만들기가 그 기능을 쓰려 하나 — 수준이 있으면 수준(고급), 없으면(시험 드라이버) 옵션 하나라도 켬
    if key == "detail_advanced" and "detail_level" in options:
        return options["detail_level"] == "advanced"
    return any(options.get(option, constants.PANEL_DEFAULT_OPTIONS.get(option)) for option in feature.get("options") or [])


def _clear(account):
    for key in ("token", "email", "entitlement", "checked_at"):
        account.pop(key, None)


def _iso(now=None):
    return (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()


def _parse_time(text):
    try:
        value = datetime.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
