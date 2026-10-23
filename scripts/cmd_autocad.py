"""Gorani AutoCAD판 사이드카 — 파이썬이 실행하는 진입 스크립트(컨트롤러 = cmd_site._SiteController 상속).

AutoCAD에는 파이썬·SQLite가 없어 AutoLISP 명령 GORANI(gorani.lsp)가 이 파일을 띄운다:
    <파이썬> -I -B -X utf8 <번들>/Contents/scripts/cmd_autocad.py
127.0.0.1 패널 서버(panel_server — 토큰)를 켜고 기본 브라우저로 패널을 연다. 이미 떠 있는 사이드카가 있으면 그 주소만 다시 열고 끝난다
(HOME_DIR/autocad_panel.json). AutoCAD 도면은 만지지 않는다 — 결과는 cad_<축척>.dxf 파일이고 사용자가 AutoCAD에서 연다.
엔진은 2D만 돈다(context_builder._run_cad_phase — 지형 메시·베이크 없음). 메시지 계약은 docs/panel_ui.md, 사용법은 docs/autocad.md.
"""

import importlib.util
import json
import os
import subprocess
import sys
import threading
import urllib.request
import webbrowser

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
os.environ["GORANI_HOST"] = "autocad"   # constants.HOST_ENV — context_builder.get_host가 본다(constants보다 먼저)
_spec = importlib.util.spec_from_file_location("gorani_cmd_site", os.path.join(SCRIPTS_DIR, "cmd_site.py"))
cmd_site = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = cmd_site
_spec.loader.exec_module(cmd_site)
loader = cmd_site.loader
tr = loader.load("i18n").tr


class _AutoCADController(cmd_site._SiteController):
    """cmd_site 컨트롤러에 AutoCAD 연결만 바꿔 단다. 문서가 없다 — 생성은 DXF 파일을 쓰는 것으로 끝난다."""

    def _get_doc(self):
        return None

    def _pump(self):
        """생성 중 cancel은 서버 스레드가 플래그를 바로 세운다 — 여기서 돌릴 이벤트가 없다."""

    def _defer(self, work):
        work()   # busy 푸시는 이미 패널로 나갔다

    def _redraw(self, doc):
        """다시 그릴 문서가 없다."""

    def _get_host_stats(self):
        return {"host": "autocad"}

    def _generate(self, msg):
        """생성 뒤 DXF를 지금 AutoCAD 도면에 넣는다 — done 푸시 직전에 넣고, 넣었는지를 done.context.imported에 담는다."""
        options = dict(msg.get("options") or {}, zoom_after_import=False)   # 줌은 gorani.lsp가 넣으면서 한다
        push = self.push

        def push_with_insert(out):
            if out.get("type") == "done" and out.get("ok"):
                out = dict(out, context=dict(out["context"], **self._insert(out)))
            push(out)

        self.push = push_with_insert
        try:
            cmd_site._SiteController._generate(self, dict(msg, options=options))
        finally:
            self.push = push

    def _insert(self, response):
        # type: (dict) -> dict
        """DXF를 '넣을 것'으로 남기고(CAD_INSERT_FILE) Windows면 실행 중인 AutoCAD에 넣기 명령을 보낸다. → {imported, import_text}."""
        constants = loader.load("constants")
        block = "Gorani_" + os.path.basename(response["dir"].rstrip("\\/"))   # 결과 폴더는 생성마다 새 이름 — 블록 이름이 겹치지 않는다
        with open(os.path.join(constants.HOME_DIR, constants.CAD_INSERT_FILE), "w", encoding="utf-8") as f:
            f.write(response["context"]["path"] + "\n" + block + "\n")
        if _send_insert_command(constants.CAD_INSERT_TIMEOUT):
            return {"imported": True, "import_text": ""}
        return {"imported": False, "import_text": tr("AutoCAD 명령줄에 GORANI를 입력하면 지금 도면에 들어갑니다")}

    def _pick_curve(self, msg):
        raise ValueError(tr("AutoCAD판은 아직 도면의 선을 가져오지 못합니다 — 지도에 구역을 그리세요"))

    def _import_context(self, msg):
        """[다시 넣기] — 결과 폴더의 DXF를 지금 도면에 다시 넣는다(생성 끝의 _insert와 같은 길)."""
        import glob
        context_builder = loader.load("context_builder")
        result_dir = str(msg.get("dir") or "")
        paths = sorted(glob.glob(os.path.join(context_builder.get_2d_dir(result_dir), "cad_*.dxf")))
        if not paths:
            raise ValueError(tr("결과 폴더가 없습니다: {0}", result_dir))
        result = self._insert({"dir": result_dir, "context": {"path": paths[-1]}})
        self.push({"type": "imported", "ok": result["imported"], "dir": result_dir, "layers": 0, "objects": 0, "replaced": False, "text": result["import_text"]})

    def _zoom_view(self, msg):
        raise ValueError(tr("AutoCAD판은 도면을 움직이지 않습니다 — DXF를 열면 처음부터 대상지 전체가 보입니다"))


def _send_insert_command(timeout):
    # type: (float) -> bool
    """Windows — 실행 중인 AutoCAD(COM AutoCAD.Application)에 (gorani:insert-pending)을 보낸다. 맥·LT·명령 중 거절이면 False.
    ponytail: 맥 AutoCAD는 밖에서 명령을 보낼 길이 없다 — 사용자가 GORANI를 한 번 더 친다."""
    if not sys.platform.startswith("win"):
        return False
    lsp = os.path.join(os.path.dirname(SCRIPTS_DIR), "gorani.lsp").replace("\\", "/")   # 수요 로드라 GORANI 전이면 LISP가 아직 없다 — 먼저 불러온다
    lisp = '(progn (if (not gorani:insert-pending) (load "%s")) (gorani:insert-pending))' % lsp
    script = ("$a = [Runtime.InteropServices.Marshal]::GetActiveObject('AutoCAD.Application'); "
              "$a.ActiveDocument.SendCommand('%s' + [char]13)" % lisp.replace("'", "''"))
    try:
        done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script], timeout=timeout,
                              capture_output=True, creationflags=0x08000000)   # CREATE_NO_WINDOW — 콘솔 창을 띄우지 않는다
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0


def _open_panel(url):
    # type: (str) -> None
    """패널을 주소창 없는 작은 앱 창으로 연다(Edge·Chrome --app). 둘 다 없으면 기본 브라우저(맥 Safari 등)."""
    constants = loader.load("constants")
    paths = constants.CAD_PANEL_BROWSERS["win" if sys.platform.startswith("win") else "mac"]
    browser = next((p for p in (os.path.expandvars(p) for p in paths) if os.path.isfile(p)), None)
    if not browser:
        webbrowser.open(url)
        return
    profile = os.path.join(constants.HOME_DIR, constants.CAD_PANEL_PROFILE_DIR)
    width, height = constants.CAD_PANEL_SIZE
    subprocess.Popen([browser, "--app=" + url, "--user-data-dir=" + profile, "--window-size=%d,%d" % (width, height),
                      "--no-first-run", "--no-default-browser-check", "--disable-features=Translate",   # 패널 언어를 번역하자는 팝업
                      "--use-mock-keychain", "--password-store=basic"],   # 맥 키체인을 안 건드린다 — 패널 프로필에 저장할 비밀이 없다
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _is_autocad_alive(parent_pid):
    # type: (int) -> bool
    """AutoCAD가 아직 떠 있나. Windows = 사이드카를 띄운 부모(startapp → acad.exe)가 살아 있나,
    맥 = AutoCAD 프로세스가 하나라도 있나(SHELL 경유라 부모 셸은 바로 끝난다)."""
    if sys.platform.startswith("win"):
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x1000, False, parent_pid)   # PROCESS_QUERY_LIMITED_INFORMATION — os.kill(pid, 0)은 윈도에서 프로세스를 죽인다
        if not handle:
            return False
        code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        kernel32.CloseHandle(handle)
        return code.value == 259   # STILL_ACTIVE
    try:
        names = subprocess.run(["ps", "-axo", "comm"], capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        return True   # 못 보면 살아 있다고 친다
    return "/Autodesk/AutoCAD" in names


def _watch_autocad(bridge, state_path):
    # type: (object, str) -> None
    """AutoCAD가 꺼지면 패널 창을 닫고(superseded — 패널이 window.close) 사이드카도 끝낸다. 백그라운드 스레드."""
    import time
    constants = loader.load("constants")
    parent_pid = os.getppid()
    while _is_autocad_alive(parent_pid):
        time.sleep(constants.CAD_WATCH_SECONDS)
    bridge.push({"type": "superseded"})
    time.sleep(1.0)   # 패널이 받고 닫을 틈
    try:
        os.remove(state_path)
    except OSError:
        pass
    print("AutoCAD closed — sidecar exits")
    os._exit(0)


def _get_live_url(state_path):
    # type: (str) -> str
    """앞서 띄운 사이드카가 아직 응답하면 그 패널 주소, 아니면 None."""
    try:
        with open(state_path, encoding="utf-8") as f:
            url = json.load(f)["url"]
        urllib.request.urlopen(url, timeout=2).close()
        return url
    except (OSError, ValueError, KeyError):
        return None


def main():
    # type: () -> None
    constants = loader.load("constants")
    os.makedirs(constants.HOME_DIR, exist_ok=True)
    state_path = os.path.join(constants.HOME_DIR, constants.CAD_PANEL_STATE_FILE)
    url = _get_live_url(state_path)
    if url:   # 이미 떠 있다 — 패널만 다시 연다
        _open_panel(url)
        return
    log = open(os.path.join(constants.HOME_DIR, constants.CAD_SIDECAR_LOG), "w", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = log   # startapp으로 띄우면 콘솔이 없다(pythonw는 None)
    bridge = loader.load("panel_server").Bridge(_AutoCADController())
    with open(state_path, "w", encoding="utf-8") as f:
        json.dump({"url": bridge.url, "pid": os.getpid()}, f)
    print("Gorani AutoCAD panel: %s" % bridge.url)
    _open_panel(bridge.url)
    threading.Thread(target=_watch_autocad, args=(bridge, state_path), daemon=True).start()   # AutoCAD를 끄면 같이 끝난다
    while True:
        bridge.dispatch(bridge.inbox.get())


if __name__ == "__main__":
    main()
