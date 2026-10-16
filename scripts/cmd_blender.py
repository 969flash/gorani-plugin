"""UrbanSite Blender 확장 진입 — 등록·버튼·브라우저 패널 브리지·컨트롤러(cmd_site._SiteController 상속).

Blender에는 웹뷰가 없어 패널(site_ui.html)을 기본 브라우저로 연다. 127.0.0.1의 작은 HTTP 서버(데몬 스레드)가
    GET  /?token=…        패널 HTML(vendor 주입 — panel_host와 같은 자리표시)
    POST /cmd?token=…     명령 → 큐 → Blender 메인 스레드(bpy.app.timers)에서 컨트롤러가 처리. cancel만 바로 플래그를 세운다
                          (생성은 메인 스레드를 막고 돈다 — 그동안 큐는 안 빠진다)
    GET  /events?token=…  상태 푸시(SSE). 새로 연결하면 앞 연결은 다음 대기 끝에 닫힌다(탭 하나)
토큰은 Blender를 켤 때마다 새로 만든다 — 다른 웹 페이지가 로컬 서버로 명령(open_path 등)을 보내지 못하게 한다.
서버 스레드는 bpy를 건드리지 않는다. 메시지 계약은 docs/panel_ui.md.

확장 패키지의 __init__.py(dev_deploy.py blender가 만든다)가 `from .scripts import cmd_blender`로 읽어 register·unregister를 넘긴다.
로직 모듈은 cmd_site처럼 loader.load로 가져온다 — 이 파일과 cmd_site는 cmd_ 접두사라 loader가 다시 읽지 않아 서버 상태가 유지된다.
"""

import base64
import hmac
import http.server
import importlib.util
import json
import os
import queue
import secrets
import socketserver
import sys
import threading
import traceback
import urllib.parse
import webbrowser

import bpy

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if __package__:   # 설치본 — scripts/가 확장의 하위 패키지(확장 정책: 최상위 모듈·sys.path 변경 금지)
    from . import cmd_site
else:   # 저장소에서 경로로 읽을 때(tests/test_blender.py)
    _spec = importlib.util.spec_from_file_location("urbansite_cmd_site", os.path.join(SCRIPTS_DIR, "cmd_site.py"))
    cmd_site = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = cmd_site
    _spec.loader.exec_module(cmd_site)
loader = cmd_site.loader

_bridge = None   # 첫 [패널 열기]에 만든다


def _get_html():
    # type: () -> str
    """site_ui.html에 vendor(Leaflet CSS·JS, Pretendard data URI)를 심은 문자열 — panel_host._get_ui_file_uri와 같은 주입.
    확장 설치본에는 Pretendard가 없다(약관 1.2 CC0만) — 빈 data URI로 두면 브라우저가 CSS의 다음 글꼴(시스템 한글 글꼴)로 그린다."""
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


def _tag_redraw():
    # type: () -> None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


class _BlenderController(cmd_site._SiteController):
    """cmd_site 컨트롤러에 Blender 호스트 연결만 바꿔 단다. 문서 = 현재 장면."""

    def _get_doc(self):
        return bpy.context.scene

    def _pump(self):
        """생성 중 cancel은 서버 스레드가 플래그를 바로 세운다 — 여기서 돌릴 이벤트가 없다."""

    def _defer(self, work):
        work()   # busy 푸시는 이미 브라우저로 나갔다

    def _redraw(self, doc):
        _tag_redraw()

    def _get_host_stats(self):
        return {"host": "blender %s" % bpy.app.version_string}

    def _pick_curve(self, msg):
        """선택한 닫힌 커브 객체 하나 → curve_shape. Blender에는 고르기 프롬프트가 없어 먼저 선택해 두어야 한다.
        베지어는 제어점, 폴리·NURBS는 점을 잇는다(곡선 근사 안 함). 장면 단위 배율(scale_length)로 m 환산."""
        scene = self._get_doc()
        curves = [o for o in bpy.context.view_layer.objects if o.select_get() and o.type == "CURVE"]
        if len(curves) != 1:
            self.push({"type": "curve_shape", "ok": False,
                       "text": "닫힌 커브 하나를 선택한 뒤 누르세요" + (" (%d개 선택됨)" % len(curves) if curves else "")})
            return
        obj = curves[0]
        spline = obj.data.splines[0] if obj.data.splines else None
        if spline is None or not spline.use_cyclic_u:
            self.push({"type": "curve_shape", "ok": False, "text": "닫힌 커브가 아닙니다 — Cyclic(닫힘)을 켠 커브만 받습니다"})
            return
        points = [p.co for p in spline.bezier_points] if spline.type == "BEZIER" else [p.co.xyz for p in spline.points]
        world = [obj.matrix_world @ p for p in points]
        if max(p.z for p in world) - min(p.z for p in world) > 1e-3:
            self.push({"type": "curve_shape", "ok": False, "text": "XY 평면(Top)에 놓인 커브여야 합니다"})
            return
        non_rhino_utils = loader.load("non_rhino_utils")
        scale = scene.unit_settings.scale_length or 1.0
        ring = non_rhino_utils.get_clean_ring([(p.x * scale, p.y * scale) for p in world])
        problem = non_rhino_utils.get_ring_problem(ring)
        baker = loader.load("context_builder").get_host_modules()[1]
        self.push(cmd_site.get_curve_shape(None if problem else ring, problem, baker.get_doc_origin(scene)))

    def _import_context(self, msg):
        result_dir = str(msg.get("dir") or "")
        if not os.path.isdir(result_dir):
            raise ValueError("결과 폴더가 없습니다: %s" % result_dir)
        context_builder = loader.load("context_builder")
        baker = context_builder.get_host_modules()[1]

        def work():
            scene = self._get_doc()
            result = baker.import_blend(scene, result_dir)
            self.push({"type": "imported", "ok": result["ok"], "dir": result_dir, "layers": result["layers"], "objects": result["objects"],
                       "replaced": result["replaced"], "text": result["text"]})
            if result["ok"] and loader.load("site_prefs").get_options().get("zoom_after_import"):
                baker.zoom_to_site(scene, result_dir)
            _tag_redraw()

        self._run_busy("장면에 넣는 중", "import", work)


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
            body = _get_html().encode("utf-8")
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
        if isinstance(msg, dict) and msg.get("cmd") == "cancel":
            bridge.controller.handle(msg)   # 플래그만 — 메인 스레드는 생성으로 막혀 있다
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


class _Bridge(object):
    """서버 하나 + 명령 큐(서버 → 메인 스레드) + 이벤트 큐(컨트롤러 → 서버)."""

    def __init__(self):
        self.token = secrets.token_urlsafe(16)
        self.inbox = queue.Queue()
        self.events = queue.Queue()
        self.controller = _BlenderController()
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

    def pump(self):
        # type: () -> None
        """메인 스레드에서 쌓인 명령을 처리한다. 예외는 컨트롤러가 error 푸시로 바꾼다 — 그래도 새면 콘솔에만."""
        while True:
            try:
                msg = self.inbox.get_nowait()
            except queue.Empty:
                return
            try:
                self.controller.handle(msg)
            except Exception:
                traceback.print_exc()

    def close(self):
        # type: () -> None
        self.controller.on_close()
        self.server.shutdown()
        self.server.server_close()


def get_bridge():
    # type: () -> _Bridge
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()
    return _bridge


def _pump_timer():
    if _bridge is not None:
        _bridge.pump()
    return POLL_SECONDS


class URBANSITE_OT_open(bpy.types.Operator):
    """대상지 패널을 기본 브라우저로 엽니다"""

    bl_idname = "urbansite.open"
    bl_label = "UrbanSite"

    def execute(self, context):
        if not bpy.app.online_access:
            self.report({"ERROR"}, "UrbanSite는 지도·지역 데이터를 인터넷에서 받습니다 — 환경 설정 > 시스템 > 네트워크 > 온라인 접근 허용을 켜세요")
            return {"CANCELLED"}
        url = get_bridge().url
        webbrowser.open(url)
        print("[UrbanSite] 패널: %s" % url)
        self.report({"INFO"}, "UrbanSite 패널을 브라우저로 열었습니다")
        return {"FINISHED"}


class URBANSITE_PT_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "UrbanSite"
    bl_label = "UrbanSite"

    def draw(self, context):
        self.layout.operator(URBANSITE_OT_open.bl_idname, text="패널 열기", icon="URL")
        if _bridge is not None:
            self.layout.label(text="브라우저 탭을 닫았으면 다시 누르세요")


_CLASSES = (URBANSITE_OT_open, URBANSITE_PT_panel)
POLL_SECONDS = loader.load("constants").BLENDER_PANEL_POLL


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    if not bpy.app.timers.is_registered(_pump_timer):
        bpy.app.timers.register(_pump_timer, first_interval=POLL_SECONDS, persistent=True)


def unregister():
    global _bridge
    if bpy.app.timers.is_registered(_pump_timer):
        bpy.app.timers.unregister(_pump_timer)
    if _bridge is not None:
        _bridge.close()
        _bridge = None
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
