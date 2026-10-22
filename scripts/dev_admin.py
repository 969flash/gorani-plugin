"""관리자 페이지 — 사용·유입·품질·서버 대시보드(dev_stats가 GA·yak·HF·국내 서버를 모은다)와 공지·버전 안내 편집
(Rhino 밖 python3, 이 Mac에서만). 주소 뒤 &demo=1 = GA 자리에 예시 데이터(연결 전 화면 확인).

    python3 scripts/dev_admin.py        # 127.0.0.1 임의 포트 + 실행마다 새 토큰으로 기본 브라우저를 연다. 저장소 루트 관리자_페이지.command = 더블클릭

인터넷에 올리지 않는다 — 공개 페이지가 없으니 로그인도 없다. 열쇠(Hugging Face 쓰기 토큰 = `hf auth login`)는 이 Mac에만 있다.
토큰이 없는 요청은 403이라 다른 웹 페이지가 로컬 서버로 공지를 올리지 못한다. 예외는 /vendor/(Leaflet — 공개 파일).
고친 것은 초안 = docs/notices.json(바로 저장, git으로 되돌린다). [게시하기]가 dev_deploy.upload_notices로 HF 매니페스트에 넣고,
[변경 취소]는 초안을 게시된 내용으로 되돌린다.
칸 뜻은 docs/panel_ui.md '업데이트·공지'.
"""

import datetime
import json
import os
import re
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402
import dev_deploy  # noqa: E402
import dev_stats  # noqa: E402
import panel_server  # noqa: E402

ADMIN_HTML_PATH = os.path.join(SCRIPTS_DIR, "dev_admin.html")
MOCK_PATH = os.path.join(ROOT_DIR, "tests", "fixtures", "site_ui_mock.json")
VERSION_PATTERN = re.compile(r"^\d+(\.\d+)*$")
UPDATE_TEXT_KEYS = ("title", "body", "deadline")


def get_version_key(version):
    # type: (str) -> tuple
    """'0.2.0' → (0, 2, 0) — 패널 cmpVer와 같은 비교(빈 자리는 0)."""
    return tuple(int(part) for part in str(version).split("."))


def get_notice_errors(data):
    # type: (dict) -> list
    """
    입력: {"update": dict|None, "notices": [dict]} — docs/notices.json 모양.
    처리: 버전 꼴(숫자.숫자), min ≤ latest, latest·min ≤ 저장소 버전(아직 없는 버전), 공지 id 중복·빈 글·level·주소(http(s))를 본다.
    출력: 고칠 것 문장 목록(빈 목록 = 저장·게시 가능).
    """
    errors = []
    update = data.get("update")
    if update is not None:
        if not isinstance(update, dict):
            return ["업데이트 안내 모양이 잘못됐습니다"]
        for key, label in (("latest", "새 버전"), ("min", "사용 불가 기준 버전")):
            if update.get(key) and not VERSION_PATTERN.match(str(update[key])):
                errors.append("%s은 0.3.0처럼 숫자와 점만 씁니다" % label)
        if not update.get("latest"):
            errors.append("알릴 새 버전을 적으세요")
        formats_ok = not errors
        if formats_ok and update.get("latest") and update.get("min") and get_version_key(update["min"]) > get_version_key(update["latest"]):
            errors.append("사용 불가 기준이 새 버전보다 높습니다")
        for key, effect in (("latest", "있지도 않은 버전으로 업데이트하라고 안내합니다"), ("min", "모든 사용자가 막힙니다")):
            if formats_ok and update.get(key) and get_version_key(update[key]) > get_version_key(constants.PANEL_VERSION):
                errors.append("%s은 아직 배포하지 않은 버전입니다(배포한 최신 %s) — 이대로면 %s. 그 버전을 배포하고 PANEL_VERSION을 올린 뒤에 게시하세요"
                              % (update[key], constants.PANEL_VERSION, effect))
    seen = set()
    for index, notice in enumerate(data.get("notices") or []):
        name = "공지 %d" % (index + 1)
        if not str(notice.get("id") or "").strip():
            errors.append("%s: id가 없습니다" % name)
        elif notice["id"] in seen:
            errors.append("%s: id %s가 겹칩니다" % (name, notice["id"]))
        seen.add(notice.get("id"))
        if not str(notice.get("text") or "").strip():
            errors.append("%s: 글이 비었습니다" % name)
        if notice.get("level") not in constants.NOTICE_LEVELS:
            errors.append("%s: 종류는 warn·info 중 하나입니다" % name)
        if notice.get("url") and not str(notice["url"]).startswith(("https://", "http://")):
            errors.append("%s: 주소는 https://로 시작해야 합니다" % name)
    return errors


def get_changes(local, remote):
    # type: (dict, dict) -> list
    """
    입력: local(docs/notices.json), remote(지금 HF 매니페스트의 update·notices).
    처리: 버전 안내 하나 + 공지(id 기준) 새 공지·수정·내림을 사람이 읽는 문장으로.
    출력: 바뀐 점 목록(빈 목록 = 올린 것과 같다).
    """
    changes = []
    old_update, new_update = remote.get("update"), local.get("update")
    if old_update != new_update:
        describe = lambda u: "없음" if not u else "새 버전 %s" % u.get("latest") + (" · %s 미만 사용 불가" % u["min"] if u.get("min") else "")
        changes.append("버전 안내: %s → %s" % (describe(old_update), describe(new_update)))
    old_notices = {n.get("id"): n for n in remote.get("notices") or []}
    new_notices = {n.get("id"): n for n in local.get("notices") or []}
    for notice_id, notice in new_notices.items():
        if notice_id not in old_notices:
            changes.append("새 공지: %s" % notice.get("text"))
        elif notice != old_notices[notice_id]:
            changes.append("공지 수정: %s" % notice.get("text"))
    changes += ["공지 내림: %s" % n.get("text") for notice_id, n in old_notices.items() if notice_id not in new_notices]
    return changes


def read_local():
    # type: () -> dict
    return dev_deploy._read_notices()


def write_local(data):
    # type: (dict) -> None
    """docs/notices.json을 통째로 쓴다(update·notices만). 빈 칸은 빼서 파일을 짧게 둔다."""
    update = data.get("update")
    if update:
        update = {key: value for key, value in update.items() if value not in ("", None, [])}
    notices = [{key: value for key, value in n.items() if value not in ("", None)} for n in data.get("notices") or []]
    with open(dev_deploy.NOTICES_PATH + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"update": update or None, "notices": notices}, f, ensure_ascii=False, indent=1)
        f.write("\n")
    os.replace(dev_deploy.NOTICES_PATH + ".tmp", dev_deploy.NOTICES_PATH)


def get_remote():
    # type: () -> dict
    """지금 올라가 있는 매니페스트의 update·notices(네트워크). 실패하면 예외."""
    request = urllib.request.Request(constants.DATA_MANIFEST_URL, headers={"Cache-Control": "no-cache"})
    with urllib.request.urlopen(request, timeout=constants.DATA_TIMEOUT_SECONDS) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    return {"update": manifest.get("update"), "notices": manifest.get("notices") or []}


def get_preview_html(data, version):
    # type: (dict, str) -> str
    """
    입력: data(update·notices), version(미리 볼 사용자 버전).
    처리: 패널(site_ui.html, vendor 주입)을 목 모드로 — 목 데이터 init_state에 version·update·notices를 바꿔 넣고
          닫은 공지·[나중에]는 비워 처음 여는 사용자처럼 보이게 한다.
    출력: HTML 문자열(/panel?mock=1&step=1로 연다).
    """
    with open(MOCK_PATH, encoding="utf-8") as f:
        msgs = json.load(f)
    options = dict(msgs[0].get("options") or {}, closed_notices=[], update_later_date="")
    msgs[0] = dict(msgs[0], version=version, update=data.get("update"), notices=data.get("notices") or [], options=options)
    mock = '<script type="application/json" id="mock">%s</script>' % json.dumps(msgs, ensure_ascii=False).replace("</", "<\\/")
    return panel_server.get_html().replace("</body>", mock + "</body>")


class _State(object):
    """서버 한 번 동안의 상태 — 토큰, 마지막으로 받은 원격 공지(올린 뒤·[다시 받기]에만 새로 받는다)."""

    def __init__(self):
        self.token = secrets.token_urlsafe(16)
        self.remote, self.remote_error = None, ""   # remote = 지금 사용자에게 게시된 update·notices
        self.lock = threading.Lock()
        self.stats = {}   # (일수, 예시, 내 테스트 제외) → dev_stats.get_stats 결과(탭을 다시 열 때 재사용, [새로고침]에만 다시 모은다)
        self.stats_lock = threading.Lock()   # 통계는 몇 초 걸린다 — 공지 잠금과 따로

    def refresh_remote(self):
        try:
            self.remote, self.remote_error = get_remote(), ""
        except Exception as error:
            self.remote, self.remote_error = None, "게시된 내용을 불러오지 못했습니다(%s)" % error

    def get_summary(self, local):
        # type: (dict) -> dict
        return {"local": local, "remote": self.remote, "errors": get_notice_errors(local), "remote_error": self.remote_error,
                "changes": get_changes(local, self.remote) if self.remote is not None else [],
                "version": constants.PANEL_VERSION, "today": datetime.date.today().isoformat()}


class _Handler(panel_server.http.server.BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass

    def _route(self):
        # type: () -> tuple
        """(경로, 쿼리) — 토큰이 틀리면 403을 보내고 경로 None. /vendor/는 토큰 없이."""
        parts = urllib.parse.urlsplit(self.path)
        query = urllib.parse.parse_qs(parts.query)
        if parts.path.startswith("/vendor/") or secrets.compare_digest(query.get("token", [""])[0], self.server.state.token):
            return parts.path, query
        self.send_error(403)
        return None, None

    def _send(self, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, query = self._route()
        state = self.server.state
        if path == "/":
            with open(ADMIN_HTML_PATH, encoding="utf-8") as f:
                self._send(f.read(), "text/html; charset=utf-8")
        elif path == "/api/state":
            with state.lock:
                if state.remote is None or query.get("refresh"):
                    state.refresh_remote()
                self._send(state.get_summary(read_local()))
        elif path == "/api/stats":
            days = max(1, min(365, int(query.get("days", ["30"])[0] or 30)))
            key = (days, bool(query.get("demo")), bool(query.get("exclude")))   # exclude = [내 테스트 제외]
            with state.stats_lock:
                if key not in state.stats or query.get("refresh"):
                    state.stats[key] = dev_stats.get_stats(*key)
                self._send(state.stats[key])
        elif path == "/panel":
            self._send(get_preview_html(read_local(), query.get("as", [constants.PANEL_VERSION])[0]), "text/html; charset=utf-8")
        elif path and path.startswith("/vendor/"):
            name = os.path.basename(path)
            file_path = os.path.join(SCRIPTS_DIR, "vendor", name)
            types = {".js": "text/javascript", ".css": "text/css", ".woff2": "font/woff2"}
            if os.path.splitext(name)[1] in types and os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    self._send(f.read(), types[os.path.splitext(name)[1]])
            else:
                self.send_error(404)
        elif path is not None:
            self.send_error(404)

    def do_POST(self):
        path, _query = self._route()
        if path is None:
            return
        state = self.server.state
        try:
            msg = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            self.send_error(400)
            return
        with state.lock:
            if path == "/api/save":   # 고칠 것이 있으면 파일은 그대로 두고 알려 준다
                data = {"update": msg.get("update"), "notices": msg.get("notices") or []}
                if not get_notice_errors(data):
                    write_local(data)
                self._send(dict(state.get_summary(read_local()), errors=get_notice_errors(data)))
            elif path == "/api/revert":   # 변경 취소 — 초안(docs/notices.json)을 게시된 내용으로
                if state.remote is not None:
                    write_local(state.remote)
                self._send(state.get_summary(read_local()))
            elif path == "/api/dev_client":   # 국내 서버 설치 ID 하나를 '내 시험'으로 표시·해제 — 모은 숫자는 다시 모은다
                dev_stats.set_dev_client(str(msg.get("id") or ""), bool(msg.get("dev")))
                with state.stats_lock:
                    state.stats.clear()
                self._send({"ok": True})
            elif path == "/api/ga_register":   # 대시보드가 쓰는 매개변수를 GA 맞춤 측정기준으로(서비스 계정 = 편집자)
                try:
                    self._send({"ok": True, "lines": dev_stats.register_dimensions()})
                except Exception as error:
                    self._send({"ok": False, "lines": ["등록하지 못했습니다: %s (서비스 계정이 속성의 '편집자'인지 확인)" % error]})
                with state.stats_lock:
                    state.stats.clear()
            elif path == "/api/publish":
                local = read_local()
                errors = get_notice_errors(local)
                if errors:
                    self._send({"ok": False, "text": errors[0]})
                    return
                try:
                    dev_deploy.upload_notices()
                except Exception as error:   # huggingface_hub 없음·로그인 안 함·네트워크
                    self._send({"ok": False, "text": "게시하지 못했습니다: %s (hf auth login 했는지 확인)" % error})
                    return
                state.refresh_remote()
                self._send(dict(state.get_summary(local), ok=True, text="게시했습니다. 사용자가 다음에 패널을 열 때 받습니다"))
            else:
                self.send_error(404)


def main():
    state = _State()
    server = panel_server._Server(("127.0.0.1", 0), _Handler)   # 역방향 DNS를 건너뛰는 서버(panel_server 주석)
    server.state = state
    url = "http://127.0.0.1:%d/?token=%s" % (server.server_address[1], state.token)
    print("관리자 페이지: %s\n  끄기: Ctrl+C" % url, flush=True)
    webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
