"""Gorani Blender 확장 진입 — 등록·버튼·브라우저 패널 브리지·컨트롤러(cmd_site._SiteController 상속).

Blender에는 웹뷰가 없어 패널(site_ui.html)을 기본 브라우저로 연다. 서버·토큰은 panel_server.Bridge(SketchUp판과 공용)의 스레드 없는 판 —
Blender 메인 스레드가 타이머(bpy.app.timers)로 bridge.pump()를 돌려 연결을 받고 명령을 컨트롤러로 넘긴다. 생성 중에는 진행 콜백의 _pump가
bridge.poll()로 cancel·새 탭을 받는다(Rhino의 RhinoApp.Wait 자리). 확장 심사가 Blender 안 스레드를 막는다. 메시지 계약은 docs/panel_ui.md.

확장 패키지의 __init__.py(dev_deploy.py blender가 만든다)가 `from .scripts import cmd_blender`로 읽어 register·unregister를 넘긴다.
로직 모듈은 cmd_site처럼 loader.load로 가져온다 — 이 파일과 cmd_site는 cmd_ 접두사라 loader가 다시 읽지 않아 서버 상태가 유지된다.
"""

import importlib.util
import os
import sys
import time
import webbrowser

import bpy
from mathutils import geometry

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
if __package__:   # 설치본 — scripts/가 확장의 하위 패키지(확장 정책: 최상위 모듈·sys.path 변경 금지)
    from . import cmd_site
else:   # 저장소에서 경로로 읽을 때(tests/test_blender.py)
    _spec = importlib.util.spec_from_file_location("gorani_cmd_site", os.path.join(SCRIPTS_DIR, "cmd_site.py"))
    cmd_site = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = cmd_site
    _spec.loader.exec_module(cmd_site)
loader = cmd_site.loader
tr = cmd_site.tr   # 패널로 보내는 문구 — 패널 언어(i18n.json)

_bridge = None   # 첫 [패널 열기]에 만든다


def _tag_redraw():
    # type: () -> None
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()


def _set_status(text):
    # type: (str) -> None
    """상태 표시줄 글(None = 지움) — Rhino 명령줄 프롬프트 자리."""
    for window in bpy.context.window_manager.windows:
        window.workspace.status_text_set(text)


def _get_selected_curves():
    # type: () -> list
    return [o for o in bpy.context.view_layer.objects if o.select_get() and o.type == "CURVE"]


def get_curve_ring(obj, scale):
    # type: (bpy.types.Object, float) -> tuple
    """Blender 커브 객체 → 구역 링(m, scale = 장면 scale_length). 안전장치에 걸리면 (None, 사용자용 이유) — context_geometry.get_curve_ring의 Blender판.
    첫 스플라인만. 베지어는 구간마다 resolution_u로 나눠 곡선을 따른다(제어점만 이으면 Bezier Circle이 사각형이 됐다), 폴리·NURBS는 점을 잇는다."""
    spline = obj.data.splines[0] if obj.data.splines else None
    if spline is None or not spline.use_cyclic_u:
        return None, tr("닫힌 커브가 아닙니다. Cyclic(닫힘)을 켠 커브만 받습니다")
    if spline.type == "BEZIER":
        knots = list(spline.bezier_points)
        points = []
        for a, b in zip(knots, knots[1:] + knots[:1]):
            points += geometry.interpolate_bezier(a.co, a.handle_right, b.handle_left, b.co, spline.resolution_u + 1)[:-1]
    else:
        points = [p.co.xyz for p in spline.points]
    world = [obj.matrix_world @ p for p in points]
    if max(p.z for p in world) - min(p.z for p in world) > 1e-3:
        return None, tr("XY 평면(Top)에 놓인 커브여야 합니다")
    non_rhino_utils = loader.load("non_rhino_utils")
    ring = non_rhino_utils.get_clean_ring([(p.x * scale, p.y * scale) for p in world])
    problem = non_rhino_utils.get_ring_problem(ring)
    return (None, problem) if problem else (ring, "")


class _BlenderController(cmd_site._SiteController):
    """cmd_site 컨트롤러에 Blender 호스트 연결만 바꿔 단다. 문서 = 현재 장면."""

    def __init__(self):
        cmd_site._SiteController.__init__(self)
        self._curve_wait = False   # 커브 고르기를 기다리는 중(두 번 눌러도 타이머 하나)

    def _get_doc(self):
        return bpy.context.scene

    def _pump(self):
        """긴 작업 중 브라우저 요청을 받는다 — 진행 푸시는 이미 나갔고 cancel·새 탭이 여기서 처리된다(다른 명령은 끝난 뒤 pump)."""
        if _bridge is not None:
            _bridge.poll()

    def _defer(self, work):
        work()   # busy 푸시는 이미 브라우저로 나갔다

    def _redraw(self, doc):
        _tag_redraw()

    def _get_host_stats(self):
        return {"host": "blender %s" % bpy.app.version_string}

    def _open(self, path):
        """파일·폴더는 Blender wm.path_open, 주소는 wm.url_open — 브라우저를 여는 단추는 그렇다고 적혀 있다(확장 약관 4.4)."""
        if "://" in path:
            bpy.ops.wm.url_open(url=path)
        else:
            bpy.ops.wm.path_open(filepath=path)

    def _pick_curve(self, msg):
        """선택한 닫힌 커브 하나 → curve_shape. 고른 커브가 없으면 Rhino 고르기 프롬프트처럼 Blender에서 고를 때까지 기다린다
        (상태 표시줄 안내, constants.BLENDER_CURVE_WAIT 뒤 멈춤 — 명령은 바로 돌아오고 타이머가 선택을 본다)."""
        curves = _get_selected_curves()
        if len(curves) > 1:
            self.push({"type": "curve_shape", "ok": False, "text": tr("커브를 하나만 선택하세요({0}개 선택됨)", len(curves))})
        elif curves:
            self._send_curve(curves[0])
        elif not self._curve_wait:
            self._curve_wait = True
            deadline = time.time() + CURVE_WAIT_SECONDS
            _set_status(_tr("Gorani: select a closed curve for the site area"))

            def poll():
                picked = _get_selected_curves()
                if len(picked) != 1 and time.time() < deadline:
                    return 0.3
                self._curve_wait = False
                _set_status(None)
                if len(picked) == 1:
                    self._guard("select", lambda: self._send_curve(picked[0]))
                else:
                    self.push({"type": "curve_shape", "ok": False, "text": tr("커브를 고르지 않아 멈췄습니다. Blender에서 커브를 선택하고 다시 누르세요")})
                return None

            bpy.app.timers.register(poll, first_interval=0.3)

    def _send_curve(self, obj):
        scene = self._get_doc()
        ring, problem = get_curve_ring(obj, scene.unit_settings.scale_length or 1.0)
        baker = loader.load("context_builder").get_host_modules()[1]
        self.push(cmd_site.get_curve_shape(ring, problem, baker.get_doc_origin(scene)))

    def _import_context(self, msg):
        result_dir = str(msg.get("dir") or "")
        if not os.path.isdir(result_dir):
            raise ValueError(tr("결과 폴더가 없습니다: {0}", result_dir))
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

        self._run_busy(tr("장면에 넣는 중"), "import", work)


def get_bridge():
    # type: () -> object
    """panel_server.Bridge 하나(첫 [패널 열기]에 만든다)."""
    global _bridge
    if _bridge is None:
        _bridge = loader.load("panel_server").Bridge(_BlenderController(), threaded=False)
    return _bridge


def _pump_timer():
    if _bridge is not None:
        _bridge.pump()
    return POLL_SECONDS


class GORANI_OT_open(bpy.types.Operator):
    """Open the Gorani panel in your web browser. Pick a site on the map and build the city around it"""

    bl_idname = "gorani.open"
    bl_label = "Gorani"

    def execute(self, context):
        if not bpy.app.online_access:
            self.report({"ERROR"}, _tr("Gorani downloads maps and regional data. Turn on Preferences > System > Network > Allow Online Access"))
            return {"CANCELLED"}
        url = get_bridge().url
        print("[Gorani] panel: %s" % url)
        if not webbrowser.open(url):
            self.report({"ERROR"}, _tr("Could not open a web browser. Open this address:") + " " + url)
            return {"CANCELLED"}
        self.report({"INFO"}, _tr("Opened the Gorani panel in your web browser"))
        return {"FINISHED"}


class GORANI_PT_panel(bpy.types.Panel):
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Gorani"
    bl_label = "Gorani"

    def draw(self, context):
        row = self.layout.row()
        row.scale_y = 1.5
        row.operator(GORANI_OT_open.bl_idname, text="Open Panel", icon="URL")
        if _bridge is not None:
            self.layout.label(text="Closed the browser tab? Click again")


def _draw_import_menu(self, context):
    self.layout.operator(GORANI_OT_open.bl_idname, text="Gorani Site Context", icon="URL")


def _tr(text):
    # type: (str) -> str
    return bpy.app.translations.pgettext_iface(text)


# Blender 화면 글은 영어가 기본, Blender 인터페이스 언어가 아래면 번역(패널 HTML은 패널 언어 — i18n.json). 단추 글은 연산자 맥락으로도 찾는다
_UI_TEXTS = {
    "Open Panel": {"ko_KR": "패널 열기", "es": "Abrir panel", "ja_JP": "パネルを開く", "zh_HANS": "打开面板"},
    "Closed the browser tab? Click again": {"ko_KR": "브라우저 탭을 닫았으면 다시 누르세요", "es": "¿Cerró la pestaña? Pulse de nuevo",
                                            "ja_JP": "タブを閉じたらもう一度押してください", "zh_HANS": "关闭了浏览器标签页？请再点一次"},
    "Gorani Site Context": {"ko_KR": "Gorani 사이트 모델", "es": "Contexto del sitio Gorani", "ja_JP": "Gorani 敷地モデル", "zh_HANS": "Gorani 场地模型"},
    "Open the Gorani panel in your web browser. Pick a site on the map and build the city around it": {
        "ko_KR": "Gorani 패널을 기본 브라우저로 엽니다. 지도에서 대상지를 고르면 주변 도시를 만듭니다",
        "es": "Abre el panel de Gorani en el navegador. Elija un sitio en el mapa y construya la ciudad a su alrededor",
        "ja_JP": "Gorani パネルをブラウザで開きます。地図で敷地を選ぶと周辺の街をつくります",
        "zh_HANS": "在浏览器中打开 Gorani 面板。在地图上选择场地，生成周边城市"},
    "Gorani downloads maps and regional data. Turn on Preferences > System > Network > Allow Online Access": {
        "ko_KR": "Gorani는 지도와 지역 데이터를 인터넷에서 받습니다. 환경 설정 > 시스템 > 네트워크 > 온라인 접근 허용을 켜세요",
        "es": "Gorani descarga mapas y datos regionales. Active Preferencias > Sistema > Red > Permitir acceso en línea",
        "ja_JP": "Gorani は地図と地域データをダウンロードします。プリファレンス > システム > ネットワーク > オンラインアクセスを許可 をオンにしてください",
        "zh_HANS": "Gorani 需要下载地图和地区数据。请开启 偏好设置 > 系统 > 网络 > 允许在线访问"},
    "Could not open a web browser. Open this address:": {"ko_KR": "브라우저를 열지 못했습니다. 이 주소를 여세요:", "es": "No se pudo abrir el navegador. Abra esta dirección:",
                                                       "ja_JP": "ブラウザを開けませんでした。このアドレスを開いてください:", "zh_HANS": "无法打开浏览器。请打开此地址："},
    "Opened the Gorani panel in your web browser": {"ko_KR": "Gorani 패널을 브라우저로 열었습니다", "es": "Panel de Gorani abierto en el navegador",
                                                    "ja_JP": "Gorani パネルをブラウザで開きました", "zh_HANS": "已在浏览器中打开 Gorani 面板"},
    "Gorani: select a closed curve for the site area": {"ko_KR": "Gorani: 대상지 구역으로 쓸 닫힌 커브를 고르세요", "es": "Gorani: seleccione una curva cerrada para el área del sitio",
                                                        "ja_JP": "Gorani: 敷地範囲にする閉じたカーブを選んでください", "zh_HANS": "Gorani：请选择作为场地范围的闭合曲线"},
}
TRANSLATIONS = {}
for _en, _texts in _UI_TEXTS.items():
    for _locale, _text in _texts.items():
        for _context in ("*", "Operator"):
            TRANSLATIONS.setdefault(_locale, {})[(_context, _en)] = _text
_CLASSES = (GORANI_OT_open, GORANI_PT_panel)
POLL_SECONDS = loader.load("constants").BLENDER_PANEL_POLL
CURVE_WAIT_SECONDS = loader.load("constants").BLENDER_CURVE_WAIT


def register():
    for cls in _CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.TOPBAR_MT_file_import.append(_draw_import_menu)
    bpy.app.translations.register(__name__, TRANSLATIONS)
    if not bpy.app.timers.is_registered(_pump_timer):
        bpy.app.timers.register(_pump_timer, first_interval=POLL_SECONDS, persistent=True)


def unregister():
    global _bridge
    if bpy.app.timers.is_registered(_pump_timer):
        bpy.app.timers.unregister(_pump_timer)
    if _bridge is not None:
        _bridge.close()
        _bridge = None
    bpy.app.translations.unregister(__name__)
    bpy.types.TOPBAR_MT_file_import.remove(_draw_import_menu)
    for cls in reversed(_CLASSES):
        bpy.utils.unregister_class(cls)
