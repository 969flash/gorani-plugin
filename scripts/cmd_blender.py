"""UrbanSite Blender 확장 진입 — 등록·버튼·브라우저 패널 브리지·컨트롤러(cmd_site._SiteController 상속).

Blender에는 웹뷰가 없어 패널(site_ui.html)을 기본 브라우저로 연다. 서버·토큰·큐는 panel_server.Bridge(SketchUp판과 공용) —
명령은 Blender 메인 스레드(bpy.app.timers)에서 bridge.pump()가 컨트롤러로 넘긴다. cancel만 서버 스레드에서 바로 플래그를 세운다
(생성은 메인 스레드를 막고 돈다 — 그동안 큐는 안 빠진다). 서버 스레드는 bpy를 건드리지 않는다. 메시지 계약은 docs/panel_ui.md.

확장 패키지의 __init__.py(dev_deploy.py blender가 만든다)가 `from .scripts import cmd_blender`로 읽어 register·unregister를 넘긴다.
로직 모듈은 cmd_site처럼 loader.load로 가져온다 — 이 파일과 cmd_site는 cmd_ 접두사라 loader가 다시 읽지 않아 서버 상태가 유지된다.
"""

import importlib.util
import os
import sys
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


def get_bridge():
    # type: () -> object
    """panel_server.Bridge 하나(첫 [패널 열기]에 만든다)."""
    global _bridge
    if _bridge is None:
        _bridge = loader.load("panel_server").Bridge(_BlenderController())
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
