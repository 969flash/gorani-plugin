"""Gorani Rhino 7판 사이드카 — 번들 파이썬이 실행하는 진입 스크립트. SketchUp판 사이드카(cmd_sketchup)에 호출 길만 바꿔 단다.

Rhino 7에는 CPython 3이 없어(IronPython 2.7뿐) Gorani.rhp(scripts/rhino7_host.cs)가 번들 파이썬으로 이 파일을 띄운다:
    <패키지>/python/<플랫폼>/python -I -B -X utf8 <패키지>/scripts/cmd_rhino7.py <Rhino 버전>
첫 줄 = 패널 주소(panel_server — 127.0.0.1·토큰). Rhino가 그 주소로 패널 창을 연다(Mac = Eto WebView, Windows = Edge 앱 창 —
Rhino 7 Windows의 Eto WebView는 IE 엔진이라 패널이 돌지 않는다).
그 뒤 stdout 한 줄 = 호스트 호출 {"type": "host_call", id, method, args}, stdin 한 줄 = Rhino의 답 {"cmd": "host_reply", id, ok, result, error}
또는 알림 {"cmd": "panel_closed"}. Edge 창은 Rhino에 닿는 다리가 없어 SketchUp판처럼 패널을 거치지 않는다.
호출 이름·인자는 SketchUp판(sketchup_ext.rb rpc_*)과 같아 베이커는 sketchup_baker를 그대로 쓴다(사본 이름만 context.3dm).
stdin이 닫히면(Rhino 종료) 끝난다. 나머지 출력은 stderr(Rhino가 ~/Gorani/rhino7_sidecar.log로 돌린다).
"""

import importlib.util
import json
import os
import queue
import sys
import threading

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("gorani_cmd_sketchup", os.path.join(SCRIPTS_DIR, "cmd_sketchup.py"))
cmd_sketchup = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cmd_sketchup
_spec.loader.exec_module(cmd_sketchup)
os.environ["GORANI_HOST"] = "rhino7"   # constants.HOST_ENV — cmd_sketchup이 둔 'sketchup'을 덮는다(context_builder.get_host는 실행 중에만 본다)
loader = cmd_sketchup.loader
tr = cmd_sketchup.tr

_out = sys.stdout   # main이 sys.stdout을 stderr로 돌린 뒤에도 호스트 호출은 Rhino가 읽는 파이프로
_out_lock = threading.Lock()


class _Host(cmd_sketchup._Host):
    """Rhino 호출 창구 — 엔진의 doc 자리(sketchup_baker 함수의 첫 인자). 패널이 아니라 stdout으로 부른다."""

    def call(self, method, **args):
        # type: (str, object) -> object
        """Rhino(rhino7_host.cs) rpc에 한 줄을 쓰고 stdin의 답을 기다린다. 응답이 없으면 SKETCHUP_HOST_TIMEOUT 뒤 HostError."""
        call_id = next(self._ids)
        line = json.dumps({"type": "host_call", "id": call_id, "method": method, "args": args})   # ASCII만 — 파이프 인코딩과 무관하게
        with _out_lock:
            _out.write(line + "\n")
            _out.flush()
        while True:   # 앞 호출이 시간을 넘겨 늦게 온 응답은 버린다
            try:
                reply = self._controller.replies.get(timeout=self._controller.constants.SKETCHUP_HOST_TIMEOUT)
            except queue.Empty:
                raise cmd_sketchup.HostError(tr("Rhino가 응답하지 않습니다({0})", method))
            if reply.get("id") == call_id:
                break
        if not reply.get("ok"):
            raise cmd_sketchup.HostError(tr("Rhino {0} 실패: {1}", method, reply.get("error") or tr("알 수 없는 오류")))
        return reply.get("result")


class _Rhino7Controller(cmd_sketchup._SketchUpController):
    """SketchUp판 컨트롤러에 Rhino 7 호출 창구만 바꿔 단다."""

    def __init__(self, version):
        cmd_sketchup._SketchUpController.__init__(self, version)
        self.host = _Host(self)

    def _get_host_stats(self):
        return {"rhino": self.version}   # Rhino 8판과 같은 키 — 통계에서 버전(7.x)으로 가른다

    def _pick_curve(self, msg):
        """Rhino에서 선택해 둔 닫힌 평면 커브 하나 → curve_shape(Rhino 8판 context_geometry.get_curve_ring과 같은 검사·문구).
        좌표는 문서 원점 기준 m(rhino7_host.cs가 단위를 바꾼다). Rhino 8판의 고르기 프롬프트는 없다 — 명령 밖에서 GetObject를 띄우지 않는다."""
        non_rhino_utils = loader.load("non_rhino_utils")
        baker = loader.load("context_builder").get_host_modules()[1]
        picked = self.host.call("pick_curve", tolerance=self.constants.CURVE_POLYLINE_TOLERANCE)
        problems = {"open": tr("닫힌 커브가 아닙니다. 끝점이 붙은 커브를 고르세요"), "planar": tr("평면 커브가 아닙니다"),
                    "tilted": tr("기울어진 커브입니다. XY 평면(Top)에 놓인 커브를 고르세요"),
                    "self": tr("꼬인(자기교차) 커브입니다. 꼬이지 않은 닫힌 커브를 고르세요")}
        if picked["count"] > 1:
            problem = tr("커브를 하나만 선택하세요({0}개 선택됨)", picked["count"])
        elif not picked["count"]:
            problem = tr("{0}에서 닫힌 평면 커브 하나를 먼저 선택해 두면 바로 가져옵니다", "Rhino")
        else:
            problem = problems.get(picked["problem"], "")
        ring = None
        if not problem:
            ring = non_rhino_utils.get_clean_ring([(p[0], p[1]) for p in picked["ring"]])
            problem = non_rhino_utils.get_ring_problem(ring)
        self.push(cmd_sketchup.cmd_site.get_curve_shape(None if problem else ring, problem, baker.get_doc_origin(self.host)))


def _read_parent(controller):
    # type: (object) -> None
    """stdin 한 줄 = Rhino의 답(host_reply) 또는 알림(panel_closed — Mac 패널 창을 닫았다). EOF = Rhino가 닫혔다 — 사이드카도 끝낸다."""
    try:
        for line in sys.stdin:
            try:
                msg = json.loads(line)
            except ValueError:
                continue
            if not isinstance(msg, dict):
                continue
            if msg.get("cmd") == "host_reply":
                controller.replies.put(msg)
            elif msg.get("cmd") == "panel_closed":
                controller.handle(msg)
    finally:
        os._exit(0)


def main():
    # type: () -> None
    version = sys.argv[1] if len(sys.argv) > 1 else ""
    bridge = loader.load("panel_server").Bridge(_Rhino7Controller(version), threaded=True)
    _out.write(bridge.url + "\n")
    _out.flush()
    sys.stdout = sys.stderr   # 남은 print는 로그로 — stdout은 호스트 호출만
    threading.Thread(target=_read_parent, args=(bridge.controller,), name="gorani-parent", daemon=True).start()
    while True:
        bridge.dispatch(bridge.inbox.get())


if __name__ == "__main__":
    main()
