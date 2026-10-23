"""브라우저 패널 서버 — 웹뷰가 없는 호스트(Blender·SketchUp)가 패널(site_ui.html)을 127.0.0.1 HTTP로 띄운다.

    GET  /?token=…        패널 HTML(vendor 주입 — panel_host와 같은 자리표시)
    POST /cmd?token=…     명령 → inbox 큐 → 호스트 메인 스레드가 pump()로 컨트롤러에 넘긴다.
                          cancel·host_reply만 서버 스레드에서 바로 넘긴다(메인 스레드는 생성·호스트 호출로 막혀 있다)
    GET  /events?token=…  상태 푸시(SSE). 새로 연결하면 앞 연결은 다음 대기 끝에 닫힌다(탭 하나)
토큰은 서버를 켤 때마다 새로 만든다 — 다른 웹 페이지가 로컬 서버로 명령(open_path 등)을 보내지 못하게 한다.
서버 스레드는 호스트(bpy 등)를 건드리지 않는다. 메시지 계약은 docs/panel_ui.md.
Blender는 기본 브라우저(cmd_blender), SketchUp은 UI::HtmlDialog(sketchup_ext.rb)가 이 주소를 연다.

두 가지로 돈다:
    threaded=True   SketchUp 사이드카(Blender 밖 별도 프로세스) — 서버 스레드가 요청을 받고 명령은 큐로 메인 루프에 넘긴다.
    threaded=False  Blender — 스레드 없이 메인 스레드가 poll()로 소켓을 돌린다(타이머 + 생성 진행 콜백, Rhino의 RhinoApp.Wait 자리).
                    확장 심사가 Blender 안 스레드를 막는다(threading·queue는 Blender를 죽인다 — 2026-10-21 심사 사례 조사).
                    이벤트 줄 소켓은 브리지가 들고 push가 바로 쓴다.
"""

import base64
import collections
import hmac
import http.server
import json
import os
import select
import secrets
import socketserver
import time
import traceback
import urllib.parse

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
DIRECT_CMDS = ("cancel", "host_reply")   # 서버 스레드(메인 스레드 판은 poll)에서 바로 — 플래그·응답만 건드린다
PING_SECONDS = 15        # 이벤트 줄 ping 간격 — 끊긴 탭을 알아챈다
REQUEST_TIMEOUT = 5      # s — 메인 스레드 판에서 느린 연결 하나가 Blender를 오래 막지 않게(요청 읽기·이벤트 쓰기)
REQUEST_QUEUE = 64       # 메인 스레드 판 연결 대기열 — 다음 poll까지(타이머 0.1 s, 생성 중에는 진행 콜백 사이) 쌓이는 요청


def get_html():
    # type: () -> str
    """site_ui.html에 vendor(Leaflet CSS·JS, Pretendard data URI)와 다국어 사전(i18n.json)을 심은 문자열 — panel_host._get_ui_file_uri와 같은 주입.
    Blender 확장 설치본에는 Pretendard가 없다(약관 1.2 CC0만) — 깔린 Pretendard(local), 없으면 CSS의 다음 글꼴(시스템 한글 글꼴)로 그린다."""
    def read(*parts):
        with open(os.path.join(SCRIPTS_DIR, *parts), encoding="utf-8") as f:
            return f.read()
    html = read("site_ui.html")
    html = html.replace("<!--VENDOR_CSS-->", "<style>" + read("vendor", "leaflet.css") + "</style>")
    html = html.replace("<!--VENDOR_JS-->", "<script>" + read("vendor", "leaflet.js") + "</script>")
    import json
    import i18n   # 다국어 사전 — 패널 tr(). 파일이 아니라 i18n.get_texts()(원격 설정 remote_config가 덮은 뒤)
    html = html.replace("<!--I18N-->", "<script>window.I18N = " + json.dumps(i18n.get_texts(), ensure_ascii=False).replace("</", "<\\/") + ";</script>")
    font_path = os.path.join(SCRIPTS_DIR, "vendor", "PretendardVariable.woff2")
    if not os.path.exists(font_path):
        return html.replace('url("<!--FONT_WOFF2-->") format("woff2-variations")', 'local("Pretendard Variable")')   # 깔려 있으면 쓴다(빈 data URI는 콘솔 경고)
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
            bridge.put(msg)
        self.send_response(204)
        self.end_headers()

    def _stream(self):
        bridge = self.server.bridge
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if not bridge.threaded:   # 메인 스레드 판 — 소켓을 브리지에 넘기고 돌아온다(서버는 닫지 않는다)
            self.wfile.flush()
            bridge.add_stream(self.connection)
            return
        import queue
        events = bridge.subscribe()
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


class _Bind(object):
    def server_bind(self):
        """HTTPServer.server_bind의 socket.getfqdn(역방향 DNS)을 건너뛴다 — 이 Mac에서 127.0.0.1 조회가 35 s 걸렸다(2026-10-15)."""
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "127.0.0.1", self.server_address[1]


class _Server(_Bind, http.server.ThreadingHTTPServer):
    """SketchUp 사이드카 — 요청마다 스레드."""
    daemon_threads = True


class _PollServer(_Bind, http.server.HTTPServer):
    """Blender — 스레드 없음. Bridge.poll()이 기다리는 연결만 받는다. 이벤트 줄 소켓은 닫지 않는다(브리지가 든다)."""
    timeout = 0
    request_queue_size = REQUEST_QUEUE   # 기본 5는 패널이 한꺼번에 보내는 명령(첫 화면·생성 중 지도 이동)에 넘쳐 fetch가 끊겼다(2026-10-21)

    def get_request(self):
        sock, address = http.server.HTTPServer.get_request(self)
        sock.settimeout(REQUEST_TIMEOUT)
        return sock, address

    def shutdown_request(self, request):
        if request not in self.bridge.streams:
            http.server.HTTPServer.shutdown_request(self, request)


class Bridge(object):
    """서버 하나 + 명령 inbox(서버 → 메인 스레드) + 이벤트(컨트롤러 → 탭). controller.push를 이 브리지로 바꿔 단다.
    threaded=False(Blender)는 스레드·큐 없이 poll()·pump()가 메인 스레드에서 소켓을 돌린다(머리말)."""

    def __init__(self, controller, threaded=True):
        self.token = secrets.token_urlsafe(16)
        self.threaded = threaded
        self.streams = []           # 메인 스레드 판의 이벤트 줄 소켓(탭 하나)
        self._pinged = time.time()
        self.controller = controller
        self.controller.push = self.push
        self.server = (_Server if threaded else _PollServer)(("127.0.0.1", 0), _Handler)
        self.server.bridge = self
        if threaded:   # SketchUp 사이드카(Blender 밖 프로세스)만
            import queue
            import threading
            self.inbox = queue.Queue()
            self.events = queue.Queue()
            threading.Thread(target=self.server.serve_forever, name="gorani-panel", daemon=True).start()
        else:
            self.inbox = collections.deque()
        self.url = "http://127.0.0.1:%d/?token=%s" % (self.server.server_address[1], self.token)

    def put(self, msg):
        # type: (dict) -> None
        """명령 하나를 메인 스레드 몫으로 쌓는다."""
        if self.threaded:
            self.inbox.put(msg)
        else:
            self.inbox.append(msg)

    def push(self, msg):
        # type: (dict) -> None
        data = json.dumps(msg, ensure_ascii=True)
        if self.threaded:
            self.events.put(data)
            return
        for sock in list(self.streams):
            self._write(sock, ("data: %s\n\n" % data).encode("utf-8"))

    def subscribe(self):
        # type: () -> object
        """스레드 판의 새 이벤트 줄 — 앞 줄로 가던 푸시는 이제 여기로 온다(새로 연 탭이 init으로 전부 다시 받는다).
        앞 줄에는 superseded를 보내 그 탭이 다시 붙지 않게 한다 — 안 보내면 두 탭이 15 s마다 서로 줄을 뺏으며 init을 되풀이했다(2026-10-21)."""
        import queue
        self.events.put(json.dumps({"type": "superseded"}))
        self.events = queue.Queue()
        return self.events

    def add_stream(self, sock):
        # type: (object) -> None
        """메인 스레드 판의 새 이벤트 줄 — 앞 줄에는 superseded를 보내고 닫는다(subscribe와 같은 규칙)."""
        for old in list(self.streams):
            self._write(old, ("data: %s\n\n" % json.dumps({"type": "superseded"})).encode("utf-8"))
            self._drop(old)
        self.streams.append(sock)

    def _write(self, sock, data):
        # type: (object, bytes) -> None
        try:
            sock.sendall(data)
        except OSError:   # 닫힌 탭·REQUEST_TIMEOUT 넘게 안 읽는 탭
            self._drop(sock)

    def _drop(self, sock):
        # type: (object) -> None
        if sock in self.streams:
            self.streams.remove(sock)
        try:
            sock.close()
        except OSError:
            pass

    def poll(self):
        # type: () -> None
        """메인 스레드 판 — 기다리는 연결을 전부 받아 처리하고 바로 돌아온다(Blender 타이머·생성 진행 콜백). PING_SECONDS마다 이벤트 줄에 ping."""
        while select.select([self.server], [], [], 0)[0]:
            self.server.handle_request()
        if self.streams and time.time() - self._pinged > PING_SECONDS:
            self._pinged = time.time()
            for sock in list(self.streams):
                self._write(sock, b": ping\n\n")

    def dispatch(self, msg):
        # type: (dict) -> None
        """메인 스레드에서 명령 하나. 예외는 컨트롤러가 error 푸시로 바꾼다 — 그래도 새면 콘솔에만."""
        try:
            self.controller.handle(msg)
        except Exception:
            traceback.print_exc()

    def pump(self):
        # type: () -> None
        """쌓인 명령을 전부 처리하고 돌아온다(Blender 타이머). 메인 스레드 판은 먼저 기다리는 연결을 받는다."""
        if not self.threaded:
            self.poll()
            while self.inbox:
                self.dispatch(self.inbox.popleft())
            return
        while not self.inbox.empty():
            self.dispatch(self.inbox.get_nowait())

    def close(self):
        # type: () -> None
        self.controller.on_close()
        if self.threaded:
            self.server.shutdown()
        for sock in list(self.streams):
            self._drop(sock)
        self.server.server_close()
