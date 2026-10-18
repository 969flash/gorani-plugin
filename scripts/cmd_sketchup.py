"""Gorani SketchUp판 사이드카 — 번들 파이썬이 실행하는 진입 스크립트(컨트롤러 = cmd_site._SiteController 상속).

SketchUp에는 파이썬이 없어 확장(sketchup_ext.rb)이 번들 파이썬으로 이 파일을 띄운다:
    <확장>/python/<플랫폼>/python -I -B -X utf8 <확장>/scripts/cmd_sketchup.py <SketchUp 버전>
첫 줄로 패널 주소(panel_server — 127.0.0.1·토큰)를 stdout에 쓰고, SketchUp의 UI::HtmlDialog가 그 주소를 연다.
그 뒤 출력은 stderr(SketchUp이 ~/Gorani/sketchup_sidecar.log로 돌린다). stdin이 닫히면(SketchUp 종료) 끝난다.

엔진은 전부 여기서 돈다. SketchUp 모델을 만지는 일만 호스트 호출이다 — 컨트롤러가 {"type": "host_call", id, method, args}를
패널로 푸시하면 패널 JS가 sketchup.host_call로 Ruby에 넘기고, Ruby가 끝나면 패널이 {"cmd": "host_reply", id, ok, result, error}를 보낸다.
메인 스레드는 응답을 기다리며 막혀 있으므로 host_reply는 서버 스레드에서 바로 받는다(panel_server.DIRECT_CMDS).
-B: 확장 폴더에 __pycache__를 쓰지 않는다(Extension Warehouse 서명 파일 목록이 바뀐다).
"""

import importlib.util
import itertools
import os
import queue
import sys
import threading

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["GORANI_HOST"] = "sketchup"   # constants.HOST_ENV — context_builder.get_host가 본다(constants보다 먼저)
_spec = importlib.util.spec_from_file_location("gorani_cmd_site", os.path.join(SCRIPTS_DIR, "cmd_site.py"))
cmd_site = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cmd_site
_spec.loader.exec_module(cmd_site)
loader = cmd_site.loader


class HostError(RuntimeError):
    """SketchUp 쪽 호출 실패 — 엔진 run이 RuntimeError로 받아 패널에 보인다."""


class _Host(object):
    """SketchUp 호출 창구 — 엔진의 doc 자리에 들어간다(sketchup_baker 함수의 첫 인자)."""

    def __init__(self, controller):
        self._controller = controller
        self._ids = itertools.count(1)

    def call(self, method, **args):
        # type: (str, object) -> object
        """패널을 거쳐 Ruby rpc_<method>를 부르고 결과를 기다린다. 패널을 닫았으면 SKETCHUP_HOST_TIMEOUT 뒤 HostError."""
        constants = self._controller.constants
        call_id = next(self._ids)
        self._controller.push({"type": "host_call", "id": call_id, "method": method, "args": args})
        while True:   # 앞 호출이 시간을 넘겨 늦게 온 응답은 버린다
            try:
                reply = self._controller.replies.get(timeout=constants.SKETCHUP_HOST_TIMEOUT)
            except queue.Empty:
                raise HostError("SketchUp이 응답하지 않습니다(%s) — 패널을 닫았으면 다시 열고 생성하세요" % method)
            if reply.get("id") == call_id:
                break
        if not reply.get("ok"):
            raise HostError("SketchUp %s 실패: %s" % (method, reply.get("error") or "알 수 없는 오류"))
        return reply.get("result")


class _SketchUpController(cmd_site._SiteController):
    """cmd_site 컨트롤러에 SketchUp 호스트 연결만 바꿔 단다. 문서 = _Host(호출 창구)."""

    def __init__(self, version):
        cmd_site._SiteController.__init__(self)
        self.version = version
        self.replies = queue.Queue()
        self.constants = loader.load("constants")
        self.host = _Host(self)

    def handle(self, msg):
        if (msg or {}).get("cmd") == "host_reply":   # 서버 스레드 — 기다리는 call에 넘기기만
            self.replies.put(msg)
            return
        cmd_site._SiteController.handle(self, msg)

    def _get_doc(self):
        return self.host

    def _pump(self):
        """생성 중 cancel은 서버 스레드가 플래그를 바로 세운다 — 여기서 돌릴 이벤트가 없다."""

    def _defer(self, work):
        work()   # busy 푸시는 이미 패널로 나갔다

    def _redraw(self, doc):
        """SketchUp은 호스트 호출이 끝날 때 다시 그린다."""

    def _get_host_stats(self):
        return {"host": "sketchup %s" % self.version}

    def _pick_curve(self, msg):
        """SketchUp에서 고른 면 하나(바깥 고리) 또는 끊김 없이 한 바퀴 도는 선들 → curve_shape. 좌표는 모델 원점 기준 m."""
        non_rhino_utils = loader.load("non_rhino_utils")
        baker = loader.load("context_builder").get_host_modules()[1]
        picked = self.host.call("pick_curve")
        points = picked.get("ring")
        if not points:
            self.push({"type": "curve_shape", "ok": False, "text": picked.get("text") or "닫힌 커브를 고르지 못했습니다"})
            return
        if max(p[2] for p in points) - min(p[2] for p in points) > 1e-3:
            self.push({"type": "curve_shape", "ok": False, "text": "수평(XY 평면)에 놓인 면·선이어야 합니다"})
            return
        ring = non_rhino_utils.get_clean_ring([(p[0], p[1]) for p in points])
        problem = non_rhino_utils.get_ring_problem(ring)
        self.push(cmd_site.get_curve_shape(None if problem else ring, problem, baker.get_doc_origin(self.host)))

    def _import_context(self, msg):
        result_dir = str(msg.get("dir") or "")
        if not os.path.isdir(result_dir):
            raise ValueError("결과 폴더가 없습니다: %s" % result_dir)
        baker = loader.load("context_builder").get_host_modules()[1]

        def work():
            result = baker.import_skp(self.host, result_dir)
            self.push({"type": "imported", "ok": result["ok"], "dir": result_dir, "layers": result["layers"], "objects": result["objects"],
                       "replaced": result["replaced"], "text": result["text"]})
            if result["ok"] and loader.load("site_prefs").get_options().get("zoom_after_import"):
                baker.zoom_to_site(self.host, result_dir)

        self._run_busy("모델에 넣는 중", "import", work)


def _exit_with_parent():
    # type: () -> None
    """stdin EOF = SketchUp이 닫혔다(파이프가 끊긴다) — 사이드카도 끝낸다."""
    try:
        sys.stdin.buffer.read()
    finally:
        os._exit(0)


def main():
    # type: () -> None
    version = sys.argv[1] if len(sys.argv) > 1 else ""
    bridge = loader.load("panel_server").Bridge(_SketchUpController(version))
    sys.stdout.write(bridge.url + "\n")
    sys.stdout.flush()
    sys.stdout = sys.stderr   # 남은 print는 로그로 — SketchUp은 첫 줄만 읽는다(안 읽는 파이프가 차면 막힌다)
    threading.Thread(target=_exit_with_parent, name="gorani-parent", daemon=True).start()
    while True:
        bridge.dispatch(bridge.inbox.get())


if __name__ == "__main__":
    main()
