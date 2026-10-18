"""Gorani 패널의 Eto WebView 호스트. 창 띄우기와 JS↔Python 브리지만 담당한다.

로직 모듈을 import하지 않는다. 명령이 오면 무엇을 할지는 `cmd_site.py`가
`on_command` 콜백으로 넣어 주고, 상태는 `push()`로 JS에 보낸다.
메시지 계약은 docs/panel_ui.md가 원본이다.
"""

import base64
import json
import os
import tempfile
import time
import traceback

import Eto.Drawing as drawing
import Eto.Forms as forms
import Rhino
import Rhino.UI
import System

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))


PANEL_CAPTION = "Gorani"
UI_FILE_NAME = "site_ui.html"  # 프런트엔드 전부 (마크업·스타일·JS)

# 브리지 진단 로그 — Rhino 이벤트 핸들러의 print는 화면에 안 보일 수 있어
# 파일로 남긴다. 패널을 열 때마다 새로 쓴다.
DEBUG_LOG_PATH = os.path.join(tempfile.gettempdir(), "gorani_panel_debug.log")


def _debug(text):
    # type: (str) -> None
    """진단 한 줄을 임시 로그 파일에 붙인다. 실패해도 조용히 넘어간다."""
    try:
        with open(DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), text))
    except OSError:
        pass


def _get_flush_messages(raw_json):
    # type: (str) -> list
    """`window.__flush()`가 돌려준 문자열을 명령 목록으로 되돌린다.

    입력:
        raw_json: ExecuteScript 반환값. 플랫폼마다 감싼 모양이 다르다.
    처리:
        mac WKWebView는 JSON 배열 문자열을 그대로 준다. Windows WebView2는
        결과를 JSON 문자열로 한 번 더 감싸는데 Eto가 겉따옴표만 떼어
        `[{\\"cmd\\":\\"init\\"}]`처럼 이스케이프가 남은 채로 온다
        (2026-09-09 배포판에서 확인) — 그대로는 못 읽으니 따옴표를 다시
        씌워 한 겹 벗긴다.
    출력:
        명령 dict 목록. 어떤 모양으로도 못 읽으면 빈 목록.
    """
    if not raw_json:
        return []
    for candidate in (raw_json, '"%s"' % raw_json):
        try:
            value = json.loads(candidate)
        except ValueError:
            continue
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if isinstance(value, list):
            return [message for message in value if isinstance(message, dict)]
    _debug("flush 결과를 읽지 못했습니다: %r" % (raw_json[:120],))
    return []


def _get_ui_file_uri():
    # type: () -> object
    """vendor를 주입한 HTML을 임시 파일로 만들고 file:// System.Uri를 돌려준다.

    입력:
        없음 — scripts/site_ui.html과 scripts/vendor/를 읽는다.
    처리:
        `<!--VENDOR_CSS-->`·`<!--VENDOR_JS-->` 주석 자리를 파일 내용으로 바꿔
        임시 폴더에 쓴다. LoadHtml(html, http URI)는 Mac WKWebView가
        LoadFileUrl로 처리해 NSInvalidArgumentException으로 Rhino째 죽는다
        (2026-09-08 크래시) — 반드시 실제 파일 + file URL로 연다.
    출력:
        임시 HTML 파일의 file:// System.Uri.
    """
    with open(os.path.join(SCRIPTS_DIR, UI_FILE_NAME), encoding="utf-8") as f:
        html = f.read()
    with open(
        os.path.join(SCRIPTS_DIR, "vendor", "leaflet.css"), encoding="utf-8"
    ) as f:
        vendor_css = f.read()
    with open(
        os.path.join(SCRIPTS_DIR, "vendor", "leaflet.js"), encoding="utf-8"
    ) as f:
        vendor_js = f.read()
    html = html.replace("<!--VENDOR_CSS-->", "<style>" + vendor_css + "</style>")
    html = html.replace("<!--VENDOR_JS-->", "<script>" + vendor_js + "</script>")
    # 번들 폰트는 base64 data URI로 심는다 — file:// 페이지의 폰트 파일
    # 참조는 Chromium(WebView2) CORS에 막힐 수 있다
    with open(
        os.path.join(SCRIPTS_DIR, "vendor", "PretendardVariable.woff2"), "rb"
    ) as f:
        font_b64 = base64.b64encode(f.read()).decode("ascii")
    html = html.replace("<!--FONT_WOFF2-->", "data:font/woff2;base64," + font_b64)
    ui_path = os.path.join(tempfile.gettempdir(), "gorani_site_ui.html")
    with open(ui_path, "w", encoding="utf-8") as f:
        f.write(html)
    return System.Uri("file://" + ui_path)


def _get_rhino_owner_window():
    # type: () -> object
    """폴백 창의 Owner로 쓸 Rhino 메인 창을 찾는다.

    입력:
        없음.
    처리:
        Mac Rhino는 문서 창이 여럿이라 활성 문서의 창을 먼저 찾고,
        없으면 메인 창으로 돌아간다.
    출력:
        Eto 창 객체.
    """
    try:
        window = Rhino.UI.RhinoEtoApp.MainWindowForDocument(Rhino.RhinoDoc.ActiveDoc)
        if window is not None:
            return window
    except Exception:
        pass
    return Rhino.UI.RhinoEtoApp.MainWindow


class PanelHost:
    """WebView 하나를 떠 있는 창으로 띄우는 호스트.

    `on_command(dict)`로 JS 명령을 넘기고, `push(dict)`로 상태를 JS에 보낸다.

    Rhino 도킹 패널(Panels.RegisterPanel)은 쓰지 않는다 — 첫 인자로 PlugIn
    인스턴스가 필요하고 패널 타입에 GuidAttribute·기본 생성자를 요구해
    CPython 스크립트에서는 등록이 성립하지 않는다 (2026-09-08 검증).
    도킹이 필요해지면 .rhp 플러그인으로 만들어야 한다.
    """

    def __init__(self, on_command):
        # type: (object) -> None
        self._on_command = on_command
        self.on_closed = None  # 창이 닫힐 때 부른다 (cmd_site가 넣는다)
        self.form = None
        try:
            os.remove(DEBUG_LOG_PATH)   # 세션마다 새 로그
        except OSError:
            pass
        self.webview = forms.WebView()
        self.webview.DocumentLoading += self._handle_document_loading
        self.webview.DocumentTitleChanged += self._handle_title_changed
        self.webview.Url = _get_ui_file_uri()
        _debug("호스트 생성 — %s" % self.webview.Url)

    # ── JS → Python ──────────────────────────────────────────
    # JS의 send()는 신호를 두 갈래로 보낸다 — mac WKWebView는 bridge: 커스텀
    # 스킴 내비게이션으로, Windows WebView2는 그 내비게이션을 막으므로
    # document.title 변경으로. 어느 쪽이 먼저 오든 __flush가 outbox를 비우니
    # 늦게 온 신호는 빈 목록을 받고 끝난다.

    def _handle_document_loading(self, sender, e):
        """`location.href = "bridge:flush"` 내비게이션을 가로채 명령을 회수한다."""
        try:
            _debug("nav: %s" % e.Uri)
            if e.Uri is None or e.Uri.Scheme != "bridge":
                return
            e.Cancel = True
            self._schedule_flush()
        except Exception:
            _debug("nav 처리 실패\n%s" % traceback.format_exc())
            print("[Gorani] 명령 회수 실패\n%s" % traceback.format_exc())

    def _handle_title_changed(self, sender, e):
        """JS의 `document.title = "bridge<n>"` 신호로 명령을 회수한다."""
        try:
            title = str(getattr(e, "Title", "") or "")
            _debug("title: %r" % title)
            if not title.startswith("bridge"):
                return
            self._schedule_flush()
        except Exception:
            _debug("title 처리 실패\n%s" % traceback.format_exc())
            print("[Gorani] 명령 회수 실패\n%s" % traceback.format_exc())

    def _schedule_flush(self):
        # type: () -> None
        """명령 회수를 UI 스레드 큐로 미룬다.

        입력:
            없음.
        처리:
            웹뷰 이벤트 콜백 안에서 ExecuteScript 결과를 기다리면 Windows
            WebView2가 그 결과를 돌려주지 못한다 — 2026-09-09 Windows 배포판에서
            `title: 'bridge1'` 뒤로 flush가 끝나지 않아 첫 init 명령이 사라졌고,
            그래서 PIN 화면도 안 떴다. 이벤트 핸들러를 먼저 끝내고 회수한다.
        출력:
            없음.
        """
        forms.Application.Instance.AsyncInvoke(System.Action(self._flush_commands))

    def _flush_commands(self):
        """JS outbox의 명령을 회수해 UI 스레드에서 하나씩 실행한다.

        여기서 예외가 새면 .NET 델리게이트로 빠져나가 라이노가 그대로 죽는다
        (2026-09-09 Windows 배포판에서 확인) — 전부 받아 로그로만 남긴다.
        """
        _debug("flush 시작")
        try:
            raw_json = self.webview.ExecuteScript("return window.__flush();")
            _debug("flush 원본: %r" % (raw_json[:120] if raw_json else raw_json))
            messages = _get_flush_messages(raw_json)
            _debug("flush 명령 %d개: %s" % (len(messages), [m.get("cmd") for m in messages]))
            for message in messages:
                # 이벤트 처리가 끝난 뒤 UI 스레드에서 실행 — busy가 먼저
                # 그려진다. pythonnet 클로저는 루프 변수를 공유하므로 기본
                # 인자로 고정한다.
                forms.Application.Instance.AsyncInvoke(
                    System.Action(lambda message=message: self._run_command(message))
                )
        except Exception:
            _debug("flush 실패\n%s" % traceback.format_exc())
            print("[Gorani] 명령 회수 실패\n%s" % traceback.format_exc())

    def _run_command(self, message):
        # type: (dict) -> None
        """컨트롤러 콜백을 부른다.

        입력:
            message: JS가 보낸 명령 dict.
        처리:
            여기가 .NET 델리게이트의 끝이라 예외가 새면 라이노가 그대로
            죽는다 — 전부 받아 로그와 폼 오류 표시로 돌린다. 컨트롤러가
            자체 try(_guard)로 못 막는 자리(인증 확인 등)도 이걸로 덮인다.
        출력:
            없음.
        """
        try:
            self._on_command(message)
        except Exception:
            text = traceback.format_exc()
            _debug("명령 처리 실패\n%s" % text)
            print("[Gorani] 명령 처리 실패\n%s" % text)
            self.push(
                {"type": "error", "context": message.get("cmd", "명령"),
                 "text": "예상 밖 오류\n%s" % text}
            )

    # ── Python → JS ──────────────────────────────────────────

    def push(self, msg):
        # type: (dict) -> None
        """상태 메시지를 JS `window.app.receive`로 보낸다.

        푸시 실패로 Rhino가 죽으면 안 된다 — 예외는 print로만 남긴다.
        """
        script = "window.app.receive(%s);" % json.dumps(msg, ensure_ascii=True)
        _debug("push: %s" % msg.get("type"))
        try:
            execute_async = getattr(self.webview, "ExecuteScriptAsync", None)
            if execute_async is not None:
                try:
                    execute_async(script)
                    return
                except Exception:
                    pass  # 미지원 플랫폼 — 동기 실행으로 넘어간다
            self.webview.ExecuteScript(script)
        except Exception as error:
            print("[Gorani] 푸시 실패: %s" % error)

    # ── 표시 ─────────────────────────────────────────────────

    def show(self):
        """떠 있는 창을 띄운다."""
        self._show_form()
        print("[Gorani] 패널 창을 열었습니다")

    def bring_to_front(self):
        """이미 떠 있는 창을 앞으로 가져온다."""
        if self.form is not None:
            self.form.BringToFront()
            self.form.Focus()

    def _show_form(self):
        """모덜리스 창에 웹뷰를 담아 띄운다."""
        form = forms.Form()
        form.Title = PANEL_CAPTION
        form.Owner = _get_rhino_owner_window()
        form.Resizable = True
        form.ClientSize = drawing.Size(480, 900)
        form.Content = self.webview
        form.Closed += self._handle_form_closed
        self.form = form
        form.Show()

    def _handle_form_closed(self, sender, args):
        if self.on_closed is not None:
            self.on_closed()
