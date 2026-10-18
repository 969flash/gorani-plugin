"""UrbanSite 웹판 — 브라우저 Pyodide 워커(web_worker.js)가 실행하는 진입 스크립트(컨트롤러 = cmd_site._SiteController 상속).

워커가 scripts/를 가상 파일계에 풀고 이 파일을 실행한 뒤 start(push)를 부른다. 패널 명령은 handle(JSON 문자열)로 들어오고 푸시는
push(JSON 문자열)로 워커 → 페이지(web_app.html) → 패널(iframe site_ui.html)로 나간다. 메시지 계약은 데스크톱과 같다(docs/panel_ui.md).
생성은 워커 안에서 동기로 돈다 — 그동안 들어온 명령은 줄을 서므로 취소는 페이지가 워커를 끝내고 새로 띄운다(받은 팩·결과는 사라진다).
Pyodide에는 소켓이 없어 urllib.request.urlopen을 동기 XHR(_urlopen)로 바꿔 단다 — data_pack·osm_context·sheet_svg가 그대로 쓴다.
OS로 열기(open_path·open_eum·sheet_ai)는 web_open 푸시 — 워커가 파일(폴더는 zip)을 읽어 페이지가 내려받거나 새 탭·3D 뷰어로 연다.
"""

import email.message
import importlib.util
import io
import json
import os
import sys
import urllib.error
import urllib.request
import zipfile

import js
from pyodide.ffi import to_js

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["URBANSITE_HOST"] = "web"   # constants.HOST_ENV — context_builder.get_host가 본다(constants보다 먼저)
_spec = importlib.util.spec_from_file_location("urbansite_cmd_site", os.path.join(SCRIPTS_DIR, "cmd_site.py"))
cmd_site = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cmd_site
_spec.loader.exec_module(cmd_site)
loader = cmd_site.loader

_UNSAFE_HEADERS = ("user-agent", "referer", "accept-encoding", "connection", "host", "content-length")   # 브라우저가 거부한다(콘솔 오류만 남는다)
ZIP_DIR = "/tmp/urbansite_zip"


class _Response(io.BytesIO):
    """urlopen 응답 흉내 — read(n)·status·headers·with."""

    def __init__(self, body, status, url, headers):
        io.BytesIO.__init__(self, body)
        self.status, self.url, self.headers = status, url, headers

    def getcode(self):
        return self.status


def _urlopen(url, data=None, timeout=None, **_kwargs):
    # type: (object, bytes, float, object) -> _Response
    """urllib.request.urlopen 대신 — 워커의 동기 XMLHttpRequest. 본문은 한 번에 다 받는다(진행률 콜백은 받은 뒤 한꺼번에 돈다).
    HTTP 오류는 HTTPError(code), 네트워크·CORS·시간 초과는 URLError — 호출자가 데스크톱과 같이 처리한다."""
    request = url if isinstance(url, urllib.request.Request) else urllib.request.Request(url, data)
    body = request.data if request.data is not None else data
    xhr = js.XMLHttpRequest.new()
    xhr.open(request.get_method(), request.full_url, False)
    xhr.responseType = "arraybuffer"
    if timeout:
        xhr.timeout = int(timeout * 1000)
    for key, value in request.header_items():
        if key.lower() not in _UNSAFE_HEADERS:
            xhr.setRequestHeader(key, value)
    try:
        xhr.send(to_js(body) if body is not None else None)
    except Exception as exc:   # noqa: BLE001 — JS NetworkError(CORS 거부·오프라인·시간 초과)
        raise urllib.error.URLError("%s (%s)" % (exc, request.full_url)) from None
    if xhr.status == 0:
        raise urllib.error.URLError("연결 실패 또는 CORS 거부 (%s)" % request.full_url)
    headers = email.message.Message()
    for line in str(xhr.getAllResponseHeaders()).split("\r\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            headers[key.strip()] = value.strip()
    payload = js.Uint8Array.new(xhr.response).to_bytes() if xhr.response else b""
    if xhr.status >= 400:
        raise urllib.error.HTTPError(request.full_url, xhr.status, str(xhr.statusText), headers, io.BytesIO(payload))
    return _Response(payload, xhr.status, str(xhr.responseURL), headers)


urllib.request.urlopen = _urlopen


def get_open_path(path):
    # type: (str) -> str
    """web_open이 넘길 파일 — 폴더면 zip으로 묶은 사본 경로(/tmp), 파일이면 그대로."""
    if not os.path.isdir(path):
        return path
    os.makedirs(ZIP_DIR, exist_ok=True)
    target = os.path.join(ZIP_DIR, (os.path.basename(path.rstrip("/")) or "urbansite") + ".zip")
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for folder, _dirs, files in os.walk(path):
            for name in sorted(files):
                full = os.path.join(folder, name)
                zf.write(full, os.path.relpath(full, os.path.dirname(path.rstrip("/"))))
    return target


class _WebController(cmd_site._SiteController):
    """cmd_site 컨트롤러에 브라우저 연결만 바꿔 단다. 문서 = web_baker.WebDoc(마지막 생성 항목)."""

    def __init__(self):
        cmd_site._SiteController.__init__(self)
        self.doc = loader.load("web_baker").WebDoc()

    def _get_doc(self):
        return self.doc

    def _pump(self):
        """생성 중에는 명령이 줄을 선다 — 취소는 페이지가 워커를 새로 띄운다."""

    def _defer(self, work):
        work()

    def _redraw(self, doc):
        """페이지 뷰어가 done 뒤에 모델을 읽는다."""

    def _get_host_stats(self):
        return {"host": "web"}

    def _open(self, path):
        """URL은 새 탭, 파일·폴더는 페이지가 받는다(web_worker.js가 web_open을 가로채 파일을 읽어 넘긴다)."""
        if "://" in path:
            self.push({"type": "web_open", "url": path})
        else:
            opened = get_open_path(path)
            self.push({"type": "web_open", "path": opened, "name": os.path.basename(opened)})

    def _pick_curve(self, msg):
        self.push({"type": "curve_shape", "ok": False, "text": "웹판에서는 지도에 구역을 그려 주세요"})

    def _import_context(self, msg):
        """'3D 보기' — 결과 폴더의 context.glb를 페이지 뷰어로."""
        result_dir = self._get_result_dir(msg)
        self.push({"type": "web_open", "path": os.path.join(result_dir, loader.load("constants").WEB_MODEL_FILE_NAME), "view": True})

    def _generate(self, msg):
        constants = loader.load("constants")
        radius = float((msg.get("options") or {}).get("radius") or 0)
        if radius > constants.WEB_MAX_RADIUS:
            raise ValueError("웹판은 반경 %.0f m까지입니다 — 더 넓은 범위는 Rhino·Blender·SketchUp판을 쓰세요" % constants.WEB_MAX_RADIUS)
        cmd_site._SiteController._generate(self, msg)


_controller = None


def start(push, config_json="{}"):
    # type: (object, str) -> None
    """워커가 한 번 부른다. push = JS 함수(JSON 문자열 하나). config: manifest(로컬 시험용 매니페스트 주소)."""
    global _controller
    config = json.loads(config_json or "{}")
    constants = loader.load("constants")
    if config.get("manifest"):
        constants.DATA_MANIFEST_URL = config["manifest"]
    _controller = _WebController()
    _controller.push = lambda msg: push(json.dumps(msg, ensure_ascii=False, default=str))


def handle(msg_json):
    # type: (str) -> None
    _controller.handle(json.loads(msg_json))
