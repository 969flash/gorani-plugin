"""회원 — 구글 로그인(gorani.site)으로 받은 Firebase 열쇠를 ~/.gorani/account.json에 두고, 기능 키로 생성 옵션을 거른다.

설계는 docs/account_plan.md: 회원 저장·인증은 Firebase(Auth + Realtime Database) — 우리 서버는 없다.
이용권(plan)은 Firebase 토큰의 맞춤 값, 이용권 → 기능은 원격 설정 PLAN_FEATURES. 플러그인은 기능(feature) 키만 본다.
로그인은 늘 시스템 브라우저에서 한다(구글이 앱 안 웹뷰 로그인을 막는다). 웹이 127.0.0.1의 받는 곳으로 열쇠(refresh token)를 폼 POST로 넘긴다.
로그인에 기대지 않는다 — 서버의 확실한 거절(ACCOUNT_DENIED_ERRORS)만 잠그고, 그 밖의 고장은 연다('로그인에 기대지 않기').
표준 라이브러리만. 받는 곳 스레드·네트워크가 있어 Blender 패키지에서 뺀다(dev_deploy.BLENDER_EXCLUDED_NAMES — Blender판은 로그인 없이 전부 열림).
"""

import base64
import datetime
import http.client
import http.server
import json
import os
import platform
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
_FILE_LOCK = threading.RLock()   # account.json 읽고 고쳐 쓰기 — 받는 곳·확인·기록 스레드와 패널이 겹친다


class Denied(Exception):
    """서버의 확실한 거절(정지·탈퇴·열쇠 무효 — ACCOUNT_DENIED_ERRORS). 잠근다."""


class Down(Exception):
    """로그인 쪽 고장(접속 안 됨·시간 초과·5xx·한도·설정 오류·이상한 응답). 막지 않고 연다."""


def load(path=ACCOUNT_PATH):
    # type: (str) -> dict
    """
    입력: account.json 경로.
    처리: 없거나 깨졌으면 빈 손님.
    출력: {refresh_token, uid, email, entitlement{plan, valid_until}, checked_at(ISO), conn_id, conn_registered,
          pending_history[[entry_id, entry]], trials_used{기능: 횟수}, login_prompt_seen}.
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
    """회원 기능이 켜졌나 — 원격 설정 ACCOUNT_ENABLED, Firebase 설정(API 키), 호스트(Blender·웹판은 없음)."""
    host = constants.HOST_LABELS.get(host_id or "", {})
    return bool(constants.ACCOUNT_ENABLED and (constants.ACCOUNT_FIREBASE or {}).get("api_key")) and host.get("account", True)


def get_state(account):
    # type: (dict) -> str
    """'guest'(열쇠 없음) · 'member'. 만료는 없다 — 서버가 확실히 거절했을 때만 열쇠를 지운다('로그인에 기대지 않기')."""
    return "member" if account.get("refresh_token") else "guest"


def get_plan(account, now=None):
    # type: (dict, datetime.datetime) -> str
    """회원의 이용권 — 토큰 값 plan(없으면 free). 기한(plan_until)이 지났으면 free(인터넷이 없어도 PC 시계로)."""
    entitlement = account.get("entitlement") or {}
    plan = str(entitlement.get("plan") or "free")
    until = _parse_time(entitlement.get("valid_until"))
    if until and until < (now or datetime.datetime.now(datetime.timezone.utc)):
        return "free"
    return plan


def get_features(account, enabled=True, now=None):
    # type: (dict, bool, datetime.datetime) -> list
    """지금 쓸 수 있는 기능 키. 회원 기능이 꺼졌으면(또는 로그인 고장으로 연 실행) 전부, 회원이면 PLAN_FEATURES[이용권], 아니면 GUEST_FEATURES."""
    if not enabled:
        return list(constants.FEATURES)
    if get_state(account) == "member":
        return list(constants.PLAN_FEATURES.get(get_plan(account, now)) or [])
    return list(constants.GUEST_FEATURES)


def get_trials_left(account, key):
    # type: (dict, str) -> int
    """로그인 없이 써 볼 수 있는 남은 횟수(GUEST_TRIALS − 쓴 횟수)."""
    used = int((account.get("trials_used") or {}).get(key) or 0)
    return max(0, int(constants.GUEST_TRIALS.get(key) or 0) - used)


def get_allowed_options(options, account, trial=False, enabled=True, now=None):
    # type: (dict, dict, bool, bool, datetime.datetime) -> tuple
    """
    입력: 생성 options, account, trial(패널이 '로그인 없이 써 보기'를 골랐나), enabled(is_enabled이고 로그인 고장으로 연 실행이 아님).
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
    def apply(account):
        used = dict(account.get("trials_used") or {})
        used[key] = int(used.get(key) or 0) + 1
        account["trials_used"] = used
    return _update(path, apply)


def set_flag(key, value=True, path=ACCOUNT_PATH):
    # type: (str, object, str) -> None
    """패널 표시 기록(login_prompt_seen — 처음 만들 때 로그인 창을 봤다)."""
    if key not in ("login_prompt_seen",):
        raise ValueError(key)
    _update(path, lambda account: account.__setitem__(key, value))


def get_panel_state(account, host_id, fallback=False, now=None):
    # type: (dict, str, bool, datetime.datetime) -> dict
    """
    입력: account, 호스트 id, fallback(이번 실행은 로그인 고장으로 고급을 열었다).
    출력: 패널 account 칸(panel_ui.md) — {enabled, state, fallback, email, plan_name, features, trials_left{기능: 남은 수},
          prompt_on_build, prompt_seen}. fallback이면 기능 전부·처음 만들 때 로그인 창 없음, 머리줄 [로그인]은 그대로(다시 시도).
    """
    enabled = is_enabled(host_id)
    state = get_state(account) if enabled else "guest"
    fallback = bool(enabled and fallback and state == "guest")
    plan = get_plan(account, now)
    return {
        "enabled": enabled,
        "state": state,
        "fallback": fallback,
        "email": (account.get("email") or "") if state == "member" else "",
        "plan_name": (constants.PLAN_NAMES.get(plan) or plan.title()) if state == "member" else "Guest",
        "features": get_features(account, enabled and not fallback, now),
        "trials_left": {key: get_trials_left(account, key) for key in constants.GUEST_TRIALS},
        "prompt_on_build": constants.LOGIN_PROMPT_ON_BUILD if enabled and not fallback else "off",
        "prompt_seen": bool(account.get("login_prompt_seen")),
    }


def get_token(refresh_token, timeout=None):
    # type: (str, float) -> tuple
    """
    입력: 열쇠(refresh token).
    처리: securetoken으로 1시간 토큰을 받고 가운데 칸을 풀어 값을 읽는다 — 구글에서 HTTPS로 직접 받은 토큰이라 서명은 확인하지 않는다.
    출력: (토큰, 새 열쇠, uid, 토큰 값 dict). 거절이면 Denied, 고장이면 Down.
    """
    data = _send(constants.ACCOUNT_TOKEN_URL + "?key=" + urllib.parse.quote(_firebase("api_key")),
                 {"grant_type": "refresh_token", "refresh_token": refresh_token}, form=True, timeout=timeout)
    if not isinstance(data, dict) or not data.get("id_token"):
        raise Down("no_id_token")
    try:
        part = str(data["id_token"]).split(".")[1]
        claims = json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)).decode("utf-8"))
    except (IndexError, ValueError):
        raise Down("bad_id_token")
    uid = str(data.get("user_id") or claims.get("user_id") or claims.get("sub") or "")
    if not uid:
        raise Down("no_uid")
    return data["id_token"], str(data.get("refresh_token") or refresh_token), uid, claims


def sign_in(refresh_token, host_id, version, path=ACCOUNT_PATH, now=None):
    # type: (str, str, str, str, datetime.datetime) -> dict
    """
    입력: 웹이 넘긴 열쇠, 호스트 id(HOST_LABELS id — rhino·sketchup·archicad), 판.
    처리: 열쇠로 토큰을 받아 메일·이용권을 account.json에 두고(써 보기 횟수·표시 기록은 그대로), 이 PC를 연결된 PC로 등록하고
          기록 저장 설정을 읽는다. 등록·설정은 되면 하고(고장이면 다음 확인 때) 로그인은 그대로 된다.
    출력: account. 열쇠가 거절되면 Denied, 고장이면 Down.
    """
    id_token, refresh_token, uid, claims = get_token(refresh_token)
    old = load(path)
    conn_id = old.get("conn_id") if old.get("uid") == uid else None   # 다른 계정으로 바뀌면 연결 id·못 보낸 기록을 버린다
    conn = {"conn_id": conn_id or secrets.token_hex(8), "conn_registered": False}
    try:
        _register(uid, id_token, conn["conn_id"], host_id, version, now)
        conn["conn_registered"] = True
    except (Denied, Down):
        pass

    def apply(account):
        if account.get("uid") != uid:
            account.pop("pending_history", None)
        account.update(refresh_token=refresh_token, uid=uid, email=str(claims.get("email") or ""), entitlement=_get_entitlement(claims),
                       checked_at=_iso(now), **conn)
    return _update(path, apply)


def refresh(host_id="", version="", path=ACCOUNT_PATH, now=None):
    # type: (str, str, str, datetime.datetime) -> dict
    """
    입력: 호스트 id·판(연결 줄을 다시 등록할 때), account.json 경로.
    처리: 열쇠로 토큰을 다시 받아 이용권을 고친다. 확실한 거절(정지·탈퇴·열쇠 무효)이면 로그아웃, 고장이면 그대로.
          웹에서 이 PC 연결을 해제했으면(등록된 적 있는 줄이 200 + null) 로그아웃 — 정직한 사용자용, 서버가 열쇠를 끊지는 못한다.
          그 밖에 연결 줄 seen 고침(등록 못 했으면 다시), 기록 저장 설정 읽기, 못 보낸 생성 기록 보내기.
    출력: account.
    """
    account = load(path)
    if not account.get("refresh_token"):
        return account
    try:
        id_token, refresh_token, uid, claims = get_token(account["refresh_token"])
    except Denied:
        return _update(path, _clear)
    except Down:
        return account
    changes = {"refresh_token": refresh_token, "uid": uid, "email": str(claims.get("email") or account.get("email") or ""),
               "entitlement": _get_entitlement(claims), "checked_at": _iso(now)}
    sent = []
    try:
        conn_path = "users/%s/connections/%s" % (uid, account.get("conn_id"))
        if account.get("conn_id") and account.get("conn_registered"):
            if _db(conn_path, id_token) is None:
                return _update(path, _clear)   # 웹에서 해제
            _db(conn_path, id_token, {"seen": _ms(now)}, "PATCH")
        elif host_id:
            conn_id = account.get("conn_id") or secrets.token_hex(8)
            _register(uid, id_token, conn_id, host_id, version, now)
            changes.update(conn_id=conn_id, conn_registered=True)
        sent = _send_history(uid, id_token, account.get("pending_history") or [], now)
    except (Denied, Down):
        pass

    def apply(account):
        if account.get("refresh_token"):   # 그사이 로그아웃했으면 되살리지 않는다
            account.update(changes)
            account["pending_history"] = [p for p in account.get("pending_history") or [] if p[0] not in sent]
    return _update(path, apply)


def refresh_later(host_id="", version="", path=ACCOUNT_PATH, now=None):
    # type: (str, str, str, datetime.datetime) -> bool
    """마지막 확인이 ACCOUNT_CHECK_HOURS를 넘었으면 데몬 스레드로 refresh — 패널을 열 때 기다리지 않게(결과는 다음에 열 때 보인다)."""
    account = load(path)
    checked = _parse_time(account.get("checked_at"))
    now = now or datetime.datetime.now(datetime.timezone.utc)
    if not account.get("refresh_token") or (checked and now - checked < datetime.timedelta(hours=constants.ACCOUNT_CHECK_HOURS)):
        return False
    threading.Thread(target=refresh, args=(host_id, version, path), daemon=True).start()
    return True


def logout(path=ACCOUNT_PATH):
    # type: (str) -> dict
    """이 PC의 연결을 끊는다 — 열쇠·메일·권한을 바로 지우고(써 보기 횟수는 남긴다), 웹의 연결 줄 지우기는 데몬 스레드로 되면 한다."""
    account = load(path)
    refresh_token, conn_id = account.get("refresh_token"), account.get("conn_id")
    if refresh_token and conn_id and account.get("conn_registered"):
        def forget():
            try:
                id_token, _token, uid, _claims = get_token(refresh_token)
                _db("users/%s/connections/%s" % (uid, conn_id), id_token, method="DELETE")
            except (Denied, Down):
                pass
        threading.Thread(target=forget, daemon=True).start()
    return _update(path, _clear)


def is_service_up(timeout=None):
    # type: (float) -> bool
    """로그인 쪽이 살아 있나 — 웹 로그인 페이지가 열리고, securetoken이 가짜 열쇠에 거절(INVALID_REFRESH_TOKEN)로 답하면 산 것."""
    timeout = timeout or constants.ACCOUNT_PROBE_SECONDS
    try:
        request = urllib.request.Request(constants.ACCOUNT_LOGIN_URL, headers={"User-Agent": constants.OSM_USER_AGENT})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1)
        get_token("gorani-probe", timeout=timeout)
    except Denied:
        return True
    except (Down, OSError, ValueError):
        return False
    return True


# ── 생성 기록(회원만, 아이디 하나에 통합 — Firebase users/<uid>/history) ─────────────

def get_history_entry(result_state, host_id, version, now=None):
    # type: (dict, str, str, datetime.datetime) -> tuple
    """
    입력: context_builder.get_result_state(결과 폴더)의 값, 호스트 id, 판.
    처리: 계정 생성 기록 한 줄(docs/account_plan.md 'Firebase에 남는 것') — 파일·폴더 경로·PC 이름은 넣지 않는다.
          대상은 필지 PNU(50개까지) 또는 구역 링 경위도(점 200개 이하로 솎음), 3D 설정은 JSON 글.
    출력: (entry_id, entry). entry_id가 없는 옛 결과면 (None, None).
    """
    entry_id = result_state.get("entry_id")
    if not entry_id:
        return None, None
    target = result_state.get("target") or {}
    lnglat = result_state.get("target_lnglat") or {}
    options = dict(result_state.get("options") or {})
    mode = str(target.get("mode") or "lots")
    spec = {}
    if mode == "lots" and target.get("pnus"):
        spec = {"pnus": [str(p) for p in target["pnus"]][:50]}
    elif mode == "area" and lnglat.get("ring"):
        ring = lnglat["ring"]
        step = max(1, -(-len(ring) // 200))
        spec = {"ring": [[round(p[0], 6), round(p[1], 6)] for p in ring[::step]]}
    stamp = _ms(now)
    entry = {"built_at": stamp, "edited": stamp, "host": host_id, "version": str(version)[:40],
             "label": str(result_state.get("label") or "")[:80], "mode": mode,
             "shape": str(options.get("shape") or ""), "radius": options.get("radius") or 0,
             "detail": "advanced" if options.get("detail_level") == "advanced" else "basic",
             "target": json.dumps(spec, ensure_ascii=False), "options": _get_options_text(options), "star": False}
    center = lnglat.get("center")
    if center and len(center) == 2 and all(isinstance(v, (int, float)) for v in center):
        entry["center"] = [round(center[0], 6), round(center[1], 6)]
    buildings = (result_state.get("context") or {}).get("buildings")
    if isinstance(buildings, int):
        entry["buildings"] = buildings
    return entry_id, entry


def add_history(entry_id, entry, path=ACCOUNT_PATH, now=None):
    # type: (str, dict, str, datetime.datetime) -> bool
    """
    입력: get_history_entry의 (entry_id, entry).
    처리: 회원이면 줄(pending_history)에 세우고 보낸다 — 데몬 스레드에서 부른다. 끄는 설정은 없다(2026-11-19 사용자 — 지우기·탈퇴로 지운다).
          못 보내면 줄에 남아 다음 확인(refresh) 때 보낸다. 줄은 HISTORY_MAX개까지.
    출력: 보냈나.
    """
    def queue(account):
        if account.get("refresh_token"):
            pending = [p for p in account.get("pending_history") or [] if p[0] != entry_id]
            account["pending_history"] = (pending + [[entry_id, entry]])[-constants.HISTORY_MAX:]
    account = _update(path, queue)
    if not account.get("pending_history"):
        return False
    try:
        id_token, refresh_token, uid, _claims = get_token(account["refresh_token"])
        sent = _send_history(uid, id_token, account["pending_history"], now)
    except (Denied, Down):
        return False

    def drop(account):
        account["pending_history"] = [p for p in account.get("pending_history") or [] if p[0] not in sent]
        if account.get("refresh_token"):
            account["refresh_token"] = refresh_token
    _update(path, drop)
    return entry_id in sent


def add_history_later(entry_id, entry, path=ACCOUNT_PATH):
    # type: (str, dict, str) -> None
    """add_history를 데몬 스레드로 — 만들기 끝에서 네트워크를 기다리지 않게."""
    threading.Thread(target=add_history, args=(entry_id, entry, path), daemon=True).start()


def get_history(path=ACCOUNT_PATH):
    # type: (str) -> dict
    """
    처리: 계정 생성 기록 전부를 받는다(패널 '생성 기록' 화면). 아직 못 보낸 이 PC 기록도 앞에 넣는다. JSON 글 칸(target·options)은 푼다.
    출력: {ok, items[{id, built_at, host, label, mode, center, target{}, shape, radius, detail, options{}, buildings, star, edited}]}.
          고장이면 ok False(화면은 이 PC 기록만 보인다).
    """
    account = load(path)
    items = {}
    ok = False
    if account.get("refresh_token"):
        try:
            id_token, _token, uid, _claims = get_token(account["refresh_token"])
            data = _db("users/%s/history" % uid, id_token)
            ok = True
            for key, value in (data or {}).items() if isinstance(data, dict) else []:
                if isinstance(value, dict):
                    items[key] = value
        except (Denied, Down):
            pass
    for entry_id, entry in account.get("pending_history") or []:
        items.setdefault(entry_id, entry)
    out = []
    for key, value in items.items():
        item = dict(value, id=key)
        for name in ("target", "options", "made_2d"):
            item[name] = _parse_json_text(item.get(name))
        out.append(item)
    out.sort(key=lambda it: it.get("built_at") or 0, reverse=True)
    return {"ok": ok, "items": out}


def change_history(entry_id, changes=None, delete=False, path=ACCOUNT_PATH, now=None):
    # type: (str, dict, bool, str, datetime.datetime) -> bool
    """생성 기록 한 줄의 이름(label)·즐겨찾기(star)를 고치거나 지운다(데몬 스레드에서 부른다). 못 하면 False(다음에 목록을 열면 원래대로)."""
    account = load(path)
    if not account.get("refresh_token") or not entry_id:
        return False
    try:
        id_token, _token, uid, _claims = get_token(account["refresh_token"])
        node = "users/%s/history/%s" % (uid, entry_id)
        if delete:
            _db(node, id_token, method="DELETE")
        else:
            body = {k: v for k, v in (changes or {}).items() if k in ("label", "star")}
            if "label" in body:
                body["label"] = str(body["label"])[:80]
            _db(node, id_token, dict(body, edited=_ms(now)), "PATCH")
    except (Denied, Down):
        return False
    if delete:
        _update(path, lambda a: a.__setitem__("pending_history", [p for p in a.get("pending_history") or [] if p[0] != entry_id]))
    return True


class HistoryFetch(object):
    """get_history를 데몬 스레드로 — 패널은 history_poll로 poll()을 부른다(받는 곳과 같은 까닭 — 스레드에서 패널로 바로 보내지 않는다)."""

    def __init__(self, path=ACCOUNT_PATH):
        self.result = None

        def run():
            try:
                self.result = get_history(path)
            except Exception:   # 스레드가 죽으면 패널이 '불러오는 중'에 멈춘다 — 받지 못한 것으로
                self.result = {"ok": False, "items": []}
        threading.Thread(target=run, daemon=True).start()

    def poll(self):
        # type: () -> dict
        """받았으면 get_history의 값, 아직이면 None."""
        return self.result


def change_history_later(entry_id, changes=None, delete=False, path=ACCOUNT_PATH):
    # type: (str, dict, bool, str) -> None
    """change_history를 데몬 스레드로 — 패널은 바꾼 모습을 먼저 그린다(못 하면 다음에 목록을 열 때 원래대로)."""
    threading.Thread(target=change_history, args=(entry_id, changes, delete, path), daemon=True).start()


class Login(object):
    """브라우저 로그인 한 번 — 먼저 로그인 쪽이 살아 있는지 재 보고(스레드), 살아 있으면 컨트롤러가 take_url()로 브라우저를 연다.
    127.0.0.1의 빈 포트에 받는 곳을 잠깐 열고, 웹이 폼 POST로 넘긴 열쇠로 sign_in한다(웹 쪽 고장이면 error=service).
    패널은 기다리는 동안 account_poll로 poll()을 부른다(받는 곳 스레드에서 패널로 바로 보내지 않는다 — 호스트마다 UI 스레드 규칙이 달라서).
    loader가 모듈을 다시 읽어도 컨트롤러가 이 객체를 들고 있어 그대로 쓴다.
    """

    def __init__(self, host_id, version, lang, path=ACCOUNT_PATH):
        self.state = secrets.token_urlsafe(24)
        self.result = None
        self.deadline = time.time() + constants.ACCOUNT_LOGIN_MINUTES * 60
        self._lock = threading.Lock()
        self._up = None          # 처음 재 보기 — None(재는 중)·True·False
        self._late_up = None     # 시간이 지난 뒤 다시 재 보기
        self._late_started = False
        self._url_taken = False
        login = self

        class Handler(http.server.BaseHTTPRequestHandler):
            timeout = 10   # 크롬이 미리 열어 두는 빈 연결(2026-11-19 실제 로그인 시험) — 요청 없이 붙어 있으면 끊는다

            def do_POST(self):
                parts = urllib.parse.urlsplit(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                if parts.path != LOGIN_PATH or length > 65536:
                    self.send_error(404)
                    return
                form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8", "replace"))
                value = lambda key: (form.get(key) or [""])[0]
                if value("state") != login.state or login.result is not None:
                    self.send_error(400)   # 남의 링크·옛 탭 — 이 패널이 연 로그인이 아니다
                    return
                if value("error"):   # 웹 쪽 고장(구글 버튼·Firebase에 닿지 않음) — 연다
                    result = {"ok": False, "fallback": True, "error": "web_" + value("error")[:40]}
                else:
                    try:
                        sign_in(value("refresh_token"), host_id, version, path)
                        result = {"ok": True}
                    except Denied as error:
                        result = {"ok": False, "error": str(error) or "invalid"}
                    except Down as error:
                        result = {"ok": False, "fallback": True, "error": str(error)[:80] or "down"}
                    except Exception as error:   # account.json 쓰기 실패 등 — 브라우저가 응답 없이 멈추고 패널이 5분 기다리지 않게
                        result = {"ok": False, "error": type(error).__name__[:40]}
                with login._lock:
                    login.result = result
                params = {"fallback": 1} if result.get("fallback") else {"ok": 1 if result["ok"] else 0}
                params.update(lang=lang, h=host_id)
                self.send_response(302)
                self.send_header("Location", constants.ACCOUNT_DONE_URL + "?" + urllib.parse.urlencode(params))
                self.end_headers()

            def log_message(self, *args):
                pass

        # 연결마다 스레드 — 크롬이 결과를 보낸 뒤 빈 연결을 하나 더 열어 두면 한 줄짜리 서버는 거기서 멈추고 close(shutdown)도 함께 멈췄다
        # (2026-11-19 실제 로그인 시험: 127.0.0.1:<port>에 ESTABLISHED 둘, 받는 곳은 recv에서 대기). 127.0.0.1만 — Windows 방화벽 창이 뜨지 않는다
        self._server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._server.daemon_threads = True
        self.port = self._server.server_address[1]
        self.url = constants.ACCOUNT_LOGIN_URL + "?" + urllib.parse.urlencode({"port": self.port, "state": self.state, "h": host_id, "lang": lang})
        threading.Thread(target=self._server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True).start()
        threading.Thread(target=self._probe, args=("_up",), daemon=True).start()

    def _probe(self, name):
        try:
            up = is_service_up()
        except Exception:   # 재다 죽으면 _up이 None으로 남아 5분을 기다린다 — 죽은 것으로
            up = False
        with self._lock:
            setattr(self, name, up)

    def take_url(self):
        # type: () -> str
        """재 보니 살아 있으면 브라우저로 열 주소를 한 번 준다(컨트롤러가 연다). 재는 중·죽음·이미 줌이면 빈 글."""
        with self._lock:
            if self._up and not self._url_taken:
                self._url_taken = True
                return self.url
        return ""

    def poll(self):
        # type: () -> dict
        """
        출력: 돌아왔으면 {ok, error?, fallback?}, 아직이면 None. 처음 재 보니 죽었으면 {fallback}(브라우저를 열지 않는다).
              시간이 지나면 한 번 더 재 보고 — 죽었으면 {fallback}, 살아 있으면 {error: timeout}. 끝나면 받는 곳을 닫는다.
        """
        with self._lock:
            result = self.result
            if result is None and self._up is False:
                result = self.result = {"ok": False, "fallback": True, "error": "probe"}
            elif result is None and time.time() > self.deadline:
                if self._late_up is not None:
                    result = self.result = {"ok": False, "error": "timeout"} if self._late_up else {"ok": False, "fallback": True, "error": "timeout_down"}
                elif not self._late_started:
                    self._late_started = True
                    threading.Thread(target=self._probe, args=("_late_up",), daemon=True).start()
        if result is not None:
            self.close()
        return result

    def close(self):
        # type: () -> None
        """받는 곳을 닫는다(취소·끝·시간 초과) — 닫기는 데몬 스레드로(패널의 UI 스레드가 기다리지 않게). 두 번 불러도 된다."""
        server, self._server = self._server, None
        if server is not None:
            def stop():
                server.shutdown()
                server.server_close()
            threading.Thread(target=stop, daemon=True).start()


# ── 안쪽 ─────────────

def _firebase(key):
    return str((constants.ACCOUNT_FIREBASE or {}).get(key) or "")


def _send(url, data=None, method=None, form=False, timeout=None):
    # type: (str, object, str, bool, float) -> object
    """
    입력: 주소, 보낼 값(form이면 폼, 아니면 JSON), 방법(GET·PUT·PATCH·DELETE — 없으면 값이 있을 때 POST).
    처리: 응답 JSON. HTTP 오류는 Firebase 오류 글(error.message 또는 error)이 거절 넷(ACCOUNT_DENIED_ERRORS)이면 Denied,
          나머지는 Down — 초기 설정 실수(API key not valid 등)도 '거절'처럼 보이지만 고장으로 본다. 접속 안 됨·시간 초과도 Down.
    출력: 응답 값(dict·list·None).
    """
    headers = {"User-Agent": constants.OSM_USER_AGENT}
    body = None
    if data is not None:
        if form:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout or constants.ACCOUNT_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8")
        return json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        message = _get_error_message(error)
        if message.replace(":", " ").split(" ")[0] in constants.ACCOUNT_DENIED_ERRORS:
            raise Denied(message)
        raise Down(message or "http_%d" % error.code)
    except (OSError, ValueError, http.client.HTTPException) as error:   # URLError·시간 초과·JSON 아님·끊긴 응답(IncompleteRead 등 — OSError가 아니다)
        raise Down(str(error)[:80] or type(error).__name__)


def _get_error_message(error):
    try:
        data = json.loads(error.read().decode("utf-8"))
    except (OSError, ValueError):
        return ""
    err = data.get("error") if isinstance(data, dict) else None
    return str((err.get("message") if isinstance(err, dict) else err) or "")


def _db(path, id_token, data=None, method=None, query=""):
    # type: (str, str, object, str, str) -> object
    """Realtime Database REST — <db_url>/<path>.json?auth=<토큰>. 규칙이 본인 것(users/<uid>)만 허락한다."""
    url = _firebase("db_url").rstrip("/") + "/" + path + ".json?auth=" + urllib.parse.quote(id_token) + query
    return _send(url, data, method or ("PUT" if data is not None else "GET"))


def _register(uid, id_token, conn_id, host_id, version, now=None):
    # 연결된 PC 한 줄 — 프로그램·판·OS·날짜만(PC 이름·경로는 넣지 않는다). 웹에서 해제하면 이 줄이 없어진다
    stamp = _ms(now)
    os_name = {"Darwin": "macOS"}.get(platform.system(), platform.system())
    _db("users/%s/connections/%s" % (uid, conn_id), id_token,
        {"host": host_id, "version": str(version)[:40], "os": os_name[:20], "created": stamp, "seen": stamp}, "PUT")


def _send_history(uid, id_token, pending, now=None):
    # type: (str, str, list, datetime.datetime) -> list
    """줄의 기록을 보낸다(같은 entry_id는 덮어씀). 보낸 entry_id 목록 — 하나라도 고장이면 거기서 멈추고 나머지는 다음에."""
    sent = []
    for entry_id, entry in pending:
        try:
            _db("users/%s/history/%s" % (uid, entry_id), id_token, entry, "PUT")
        except (Denied, Down):
            break
        sent.append(entry_id)
    if sent:
        _trim_history(uid, id_token)
    return sent


def _trim_history(uid, id_token):
    # 계정당 HISTORY_MAX개 — 넘치면 오래된 것부터, 즐겨찾기는 남긴다. 키만 먼저 세고 넘칠 때만 전부 받는다
    node = "users/%s/history" % uid
    keys = _db(node, id_token, query="&shallow=true") or {}
    if len(keys) <= constants.HISTORY_MAX:
        return
    items = _db(node, id_token) or {}
    order = sorted((k for k, v in items.items() if isinstance(v, dict) and not v.get("star")), key=lambda k: items[k].get("built_at") or 0)
    for key in order[:len(items) - constants.HISTORY_MAX]:
        _db("%s/%s" % (node, key), id_token, method="DELETE")


def _get_entitlement(claims):
    # 토큰 값 → 이용권(plan·기한). 기능은 쓸 때 원격 설정 PLAN_FEATURES로 정한다(설정이 바뀌면 바로 따라가게)
    return {"plan": str(claims.get("plan") or "free"), "valid_until": str(claims.get("plan_until") or "")}


def _get_options_text(options):
    # 3D 설정 JSON 글(규칙 4,000자) — 넘치면 글자·숫자·참거짓 값만
    text = json.dumps(options, ensure_ascii=False, default=str)
    if len(text) > 4000:
        text = json.dumps({k: v for k, v in options.items() if isinstance(v, (str, int, float, bool))}, ensure_ascii=False)
    return text if len(text) <= 4000 else "{}"


def _parse_json_text(value):
    if isinstance(value, (dict, list)):
        return value
    try:
        return json.loads(value) if value else {}
    except (TypeError, ValueError):
        return {}


def _update(path, apply):
    # account.json 읽고 고쳐 쓰기를 한 번에 — 스레드가 겹쳐도 남의 고침(써 보기 횟수 등)을 덮지 않게
    with _FILE_LOCK:
        account = load(path)
        apply(account)
        save(account, path)
        return account


def _wants(options, key, feature):
    # 이번 만들기가 그 기능을 쓰려 하나 — 수준이 있으면 수준(고급), 없으면(시험 드라이버) 옵션 하나라도 켬
    if key == "detail_advanced" and "detail_level" in options:
        return options["detail_level"] == "advanced"
    return any(options.get(option, constants.PANEL_DEFAULT_OPTIONS.get(option)) for option in feature.get("options") or [])


def _clear(account):
    for key in ("refresh_token", "uid", "email", "entitlement", "checked_at", "conn_id", "conn_registered", "pending_history"):
        account.pop(key, None)


def _ms(now=None):
    return int((now or datetime.datetime.now(datetime.timezone.utc)).timestamp() * 1000)


def _iso(now=None):
    return (now or datetime.datetime.now(datetime.timezone.utc)).isoformat()


def _parse_time(text):
    try:
        value = datetime.datetime.fromisoformat(str(text).replace("Z", "+00:00"))   # 3.9(Rhino 8)는 끝의 Z를 못 읽는다 — 3.12 사이드카와 같게
    except (TypeError, ValueError):
        return None
    return value if value.tzinfo else value.replace(tzinfo=datetime.timezone.utc)
