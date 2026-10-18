"""브라우저 패널 서버 — 웹뷰가 없는 호스트(Blender·SketchUp)가 패널(site_ui.html)을 127.0.0.1 HTTP로 띄운다.

    GET  /?token=…        패널 HTML(vendor 주입 — panel_host와 같은 자리표시)
    POST /cmd?token=…     명령 → inbox 큐 → 호스트 메인 스레드가 pump()로 컨트롤러에 넘긴다.
                          cancel·host_reply만 서버 스레드에서 바로 넘긴다(메인 스레드는 생성·호스트 호출로 막혀 있다)
    GET  /events?token=…  상태 푸시(SSE). 새로 연결하면 앞 연결은 다음 대기 끝에 닫힌다(탭 하나)
토큰은 서버를 켤 때마다 새로 만든다 — 다른 웹 페이지가 로컬 서버로 명령(open_path 등)을 보내지 못하게 한다.
서버 스레드는 호스트(bpy 등)를 건드리지 않는다. 메시지 계약은 docs/panel_ui.md.
Blender는 기본 브라우저(cmd_blender), SketchUp은 UI::HtmlDialog(sketchup_ext.rb)가 이 주소를 연다.
"""

import base64
import hmac
import http.server
import json
import os
import queue
import secrets
import socketserver
import threading
import traceback
import urllib.parse

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DIRECT_CMDS = ("cancel", "host_reply")   # 서버 스레드에서 바로 — 플래그·응답만 건드린다


def get_html():
    # type: () -> str
    """site_ui.html에 vendor(Leaflet CSS·JS, Pretendard data URI)를 심은 문자열 — panel_host._get_ui_file_uri와 같은 주입.
    Blender 확장 설치본에는 Pretendard가 없다(약관 1.2 CC0만) — 빈 data URI로 두면 브라우저가 CSS의 다음 글꼴(시스템 한글 글꼴)로 그린다."""
    def read(*parts):
        with open(os.path.join(SCRIPTS_DIR, *parts), encoding="utf-8") as f:
            return f.read()
    html = read("site_ui.html")
    html = html.replace("<!--VENDOR_CSS-->", "<style>" + read("vendor", "leaflet.css") + "</style>")
    html = html.replace("<!--VENDOR_JS-->", "<script>" + read("vendor", "leaflet.js") + "</script>")
    font_path = os.path.join(SCRIPTS_DIR, "vendor", "PretendardVariable.woff2")
    if not os.path.exists(font_path):
        return html.replace("<!--FONT_WOFF2-->", "data:,")
    with open(font_path, "rb") as f:
        font_b64 = base64.b64encode(f.read()).decode("ascii")
    return html.replace("<!--FONT_WOFF2-->", "data:font/woff2;base64," + font_b64)


class _Handler(http.server.BaseHTTPRequestHandler):
    """패널 HTML·명령·이벤트 줄. 토큰이 맞지 않으면 403."""

    def log_message(self, *args):
        pass

    def _get_path(self):
        # type: () -> str
        parts = urllib.parse.urlsplit(self.path)
        token = urllib.parse.parse_qs(parts.query).get("token", [""])[0]
        if hmac.compare_digest(token, self.server.bridge.token):
            return parts.path
        self.send_error(403)
        return None

    def do_GET(self):
        path = self._get_path()
        if path == "/":
            body = get_html().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif path == "/events":
            self._stream()
        elif path is not None:
            self.send_error(404)

    def do_POST(self):
        path = self._get_path()
        if path != "/cmd":
            if path is not None:
                self.send_error(404)
            return
        try:
            msg = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        except ValueError:
            self.send_error(400)
            return
        bridge = self.server.bridge
        if isinstance(msg, dict) and msg.get("cmd") in DIRECT_CMDS:
            bridge.controller.handle(msg)
        elif isinstance(msg, dict):
            bridge.inbox.put(msg)
        self.send_response(204)
        self.end_headers()

    def _stream(self):
        events = self.server.bridge.subscribe()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            while self.server.bridge.events is events:
                try:
                    data = events.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": ping\n\n")   # 끊긴 연결을 알아챈다
                else:
                    self.wfile.write(("data: %s\n\n" % data).encode("utf-8"))
                self.wfile.flush()
        except OSError:
            pass


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):
        """HTTPServer.server_bind의 socket.getfqdn(역방향 DNS)을 건너뛴다 — 이 Mac에서 127.0.0.1 조회가 35 s 걸렸다(2026-10-15)."""
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


class Bridge(object):
    """서버 하나 + 명령 큐(서버 → 메인 스레드) + 이벤트 큐(컨트롤러 → 서버). controller.push를 이 브리지로 바꿔 단다."""

    def __init__(self, controller):
        self.token = secrets.token_urlsafe(16)
        self.inbox = queue.Queue()
        self.events = queue.Queue()
        self.controller = controller
        self.controller.push = self.push
        self.server = _Server(("127.0.0.1", 0), _Handler)
        self.server.bridge = self
        threading.Thread(target=self.server.serve_forever, name="urbansite-panel", daemon=True).start()
        self.url = "http://127.0.0.1:%d/?token=%s" % (self.server.server_address[1], self.token)

    def push(self, msg):
        # type: (dict) -> None
        self.events.put(json.dumps(msg, ensure_ascii=True))

    def subscribe(self):
        # type: () -> queue.Queue
        """새 이벤트 줄 — 앞 줄로 가던 푸시는 이제 여기로 온다(새로 연 탭이 init으로 전부 다시 받는다)."""
        self.events = queue.Queue()
        return self.events

    def dispatch(self, msg):
        # type: (dict) -> None
        """메인 스레드에서 명령 하나. 예외는 컨트롤러가 error 푸시로 바꾼다 — 그래도 새면 콘솔에만."""
        try:
            self.controller.handle(msg)
        except Exception:
            traceback.print_exc()

    def pump(self):
        # type: () -> None
        """쌓인 명령을 전부 처리하고 돌아온다(Blender 타이머)."""
        while True:
            try:
                msg = self.inbox.get_nowait()
            except queue.Empty:
                return
            self.dispatch(msg)

    def close(self):
        # type: () -> None
        self.controller.on_close()
        self.server.shutdown()
        self.server.server_close()
