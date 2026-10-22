"""Gorani Archicad판 사이드카 — 번들 파이썬이 실행하는 진입 스크립트(컨트롤러 = cmd_site._SiteController 상속).

Archicad에는 파이썬이 없어 Gorani 애드온(archicad/ C++, Tapir에서 가져옴)의 메뉴가 번들 파이썬으로 이 파일을 띄운다:
    <Gorani 폴더>/python/<플랫폼>/python -I -B -X utf8 <Gorani 폴더>/scripts/cmd_archicad.py --port <JSON 포트> --version <Archicad 버전>
엔진은 전부 여기서 돈다. 모델 변경만 Archicad JSON API(127.0.0.1:<포트>)로 애드온 명령(constants.ARCHICAD_COMMAND_NAMESPACE)을 부른다 —
SketchUp판처럼 패널을 거치지 않고 사이드카가 바로 HTTP로 부른다. 패널(panel_server 스레드판)은 Archicad 안 브라우저 팔레트(애드온 ShowScriptUI —
패널 주소로 넘기는 한 줄짜리 페이지)에 띄우고, 안 되면 기본 브라우저로 연다.
같은 포트로 이미 떠 있는 사이드카가 있으면 그 패널 주소만 다시 열고 끝낸다(메뉴를 두 번 눌러도 엔진은 하나).
Archicad가 닫히면(JSON 포트 연결 거부) 사이드카도 끝낸다.
"""

import argparse
import importlib.util
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["GORANI_HOST"] = "archicad"   # constants.HOST_ENV — context_builder.get_host가 본다(constants보다 먼저)
_spec = importlib.util.spec_from_file_location("gorani_cmd_site", os.path.join(SCRIPTS_DIR, "cmd_site.py"))
cmd_site = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cmd_site
_spec.loader.exec_module(cmd_site)
loader = cmd_site.loader
tr = cmd_site.tr


class HostError(RuntimeError):
    """Archicad 쪽 호출 실패 — 엔진 run이 RuntimeError로 받아 패널에 보인다."""


class ArchicadHost(object):
    """Archicad JSON API 창구 — 엔진의 doc 자리에 들어간다(archicad_baker 함수의 첫 인자). 구운 요소 id를 대상지별로 기억한다(줌)."""

    def __init__(self, port, namespace=None):
        constants = loader.load("constants")
        self.url = "http://127.0.0.1:%d" % port
        self.namespace = namespace or constants.ARCHICAD_COMMAND_NAMESPACE
        self.timeout = constants.ARCHICAD_HOST_TIMEOUT
        self.baked = {}   # lot_key → [요소 id] — 이번 세션에 구운 것(화면 맞춤)

    def api(self, command, params=None):
        # type: (str, dict) -> object
        """Archicad 기본 명령 하나(API.*). 실패하면 HostError."""
        body = {"command": command}
        if params is not None:
            body["parameters"] = params
        request = urllib.request.Request(self.url, json.dumps(body).encode("utf-8"), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError) as error:
            raise HostError(tr("Archicad가 응답하지 않습니다({0}) — Archicad에 프로젝트가 열려 있는지 확인하세요", command)) from error
        if not data.get("succeeded"):
            raise HostError(tr("Archicad {0} 실패: {1}", command, (data.get("error") or {}).get("message") or tr("알 수 없는 오류")))
        return data.get("result")

    def call(self, name, **params):
        # type: (str, object) -> object
        """Gorani 애드온 명령 하나(API.ExecuteAddOnCommand). 응답의 error는 HostError."""
        result = self.api("API.ExecuteAddOnCommand", {"addOnCommandId": {"commandNamespace": self.namespace, "commandName": name},
                                                      "addOnCommandParameters": params})
        response = (result or {}).get("addOnCommandResponse")
        if isinstance(response, dict) and response.get("error"):
            raise HostError(tr("Archicad {0} 실패: {1}", name, response["error"].get("message") or response["error"]))
        return response

    def is_alive(self):
        # type: () -> bool
        """JSON 포트가 연결을 받는지 — 거부 = Archicad가 닫혔다. 바쁜(긴 명령 중) Archicad는 살아 있다고 본다."""
        try:
            self.api("API.IsAlive")
            return True
        except HostError as error:
            cause = error.__cause__
            return not (isinstance(cause, urllib.error.URLError) and isinstance(cause.reason, ConnectionRefusedError))


class _ArchicadController(cmd_site._SiteController):
    """cmd_site 컨트롤러에 Archicad 호스트 연결만 바꿔 단다. 문서 = ArchicadHost."""

    def __init__(self, host, version):
        cmd_site._SiteController.__init__(self)
        self.host = host
        self.version = version

    def _get_doc(self):
        return self.host

    def _pump(self):
        """생성 중 cancel은 서버 스레드가 플래그를 바로 세운다 — 여기서 돌릴 이벤트가 없다."""

    def _defer(self, work):
        work()   # busy 푸시는 이미 브라우저로 나갔다

    def _redraw(self, doc):
        """Archicad는 명령이 끝날 때 다시 그린다."""

    def _get_host_stats(self):
        return {"host": "archicad %s" % self.version}

    def _pick_curve(self, msg):
        """Archicad에서 고른 요소 하나(폴리선·채우기·슬래브·영역·메시)의 바깥 고리 → curve_shape. 좌표는 프로젝트 원점 기준 m."""
        non_rhino_utils = loader.load("non_rhino_utils")
        baker = loader.load("context_builder").get_host_modules()[1]
        points, text = baker.get_selected_ring(self.host)
        if not points:
            self.push({"type": "curve_shape", "ok": False, "text": text})
            return
        ring = non_rhino_utils.get_clean_ring(points)
        problem = non_rhino_utils.get_ring_problem(ring)
        self.push(cmd_site.get_curve_shape(None if problem else ring, problem, baker.get_doc_origin(self.host)))

    def _import_context(self, msg):
        result_dir = str(msg.get("dir") or "")
        if not os.path.isdir(result_dir):
            raise ValueError(tr("결과 폴더가 없습니다: {0}", result_dir))
        baker = loader.load("context_builder").get_host_modules()[1]

        def work():
            result = baker.import_mod(self.host, result_dir)
            self.push({"type": "imported", "ok": result["ok"], "dir": result_dir, "layers": result["layers"], "objects": result["objects"],
                       "replaced": result["replaced"], "text": result["text"]})
            if result["ok"] and loader.load("site_prefs").get_options().get("zoom_after_import"):
                baker.zoom_to_site(self.host, result_dir)

        self._run_busy(tr("모델에 넣는 중"), "import", work)


def open_panel(host, url):
    # type: (ArchicadHost, str) -> None
    """패널 주소를 Archicad 팔레트(ShowScriptUI)에 연다. 애드온 명령이 없거나 실패하면 기본 브라우저."""
    constants = loader.load("constants")
    width, height = constants.ARCHICAD_PANEL_SIZE
    page = '<!doctype html><meta charset="utf-8"><script>location.replace(%s)</script>' % json.dumps(url)
    try:
        host.call("ShowScriptUI", htmlContent=page, title="Gorani", width=width, height=height, contextMenuEnabled=False)
    except Exception:   # noqa: BLE001 — 팔레트가 없는 애드온·옛 Archicad는 브라우저로
        webbrowser.open(url)


def _get_lock_path(port):
    # type: (int) -> str
    return os.path.join(loader.load("constants").HOME_DIR, "archicad_panel_%d.json" % port)


def _get_running_url(port):
    # type: (int) -> str
    """같은 Archicad(포트)에 이미 떠 있는 사이드카의 패널 주소. 없거나 응답이 없으면 ''."""
    try:
        with open(_get_lock_path(port), encoding="utf-8") as f:
            url = json.load(f).get("url") or ""
        with urllib.request.urlopen(url, timeout=2) as response:
            return url if response.status == 200 else ""
    except (OSError, ValueError):
        return ""


def _watch_archicad(host):
    # type: (ArchicadHost) -> None
    """Archicad가 닫히면(포트 연결 거부가 이어지면) 사이드카를 끝낸다."""
    constants = loader.load("constants")
    misses = 0
    while True:
        time.sleep(constants.ARCHICAD_WATCH_SECONDS)
        misses = 0 if host.is_alive() else misses + 1
        if misses >= constants.ARCHICAD_WATCH_MISSES:
            os._exit(0)


def main():
    # type: () -> None
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--version", default="")
    parser.add_argument("--namespace", default=None)   # 개발 시험 — Tapir 애드온으로 돌릴 때 'TapirCommand'
    args = parser.parse_args()
    host = ArchicadHost(args.port, args.namespace)
    url = _get_running_url(args.port)
    if url:
        open_panel(host, url)
        return
    bridge = loader.load("panel_server").Bridge(_ArchicadController(host, args.version))
    lock_path = _get_lock_path(args.port)
    os.makedirs(os.path.dirname(lock_path), exist_ok=True)
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump({"pid": os.getpid(), "url": bridge.url}, f)
    print("[Gorani] panel: %s" % bridge.url, flush=True)
    threading.Thread(target=_watch_archicad, args=(host,), name="gorani-watch", daemon=True).start()
    open_panel(host, bridge.url)
    while True:
        bridge.dispatch(bridge.inbox.get())


if __name__ == "__main__":
    main()
