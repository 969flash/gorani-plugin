"""Rhino 7판 사이드카(cmd_rhino7) — 호스트 호출이 패널이 아니라 stdout 한 줄·stdin 한 줄로 오가고, sketchup_baker가 사본을 context.3dm으로 쓴다.
Rhino 쪽(rhino7_host.cs)은 Rhino 7 안에서만 — 여기서는 같은 줄 약속으로 답하는 가짜 Rhino를 쓴다.
numpy·shapely가 있는 번들 파이썬에서만 돈다(test_sketchup과 같다):

    build/sketchup/bsh_gorani/python/mac-arm64/bin/python3.12 -m unittest tests/test_rhino7.py
"""

import importlib.util
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import test_sketchup  # noqa: E402 — 같은 fixture·요청·가짜 호스트(rpc 흉내)

SCRIPT = str(test_sketchup.SCRIPTS_DIR / "cmd_rhino7.py")


def setUpModule():
    """cmd_rhino7은 읽을 때 GORANI_HOST를 둔다 — 이 파일이 끝나면 되돌린다."""
    global cmd_rhino7, _old_host
    if not test_sketchup.READY:
        return
    _old_host = os.environ.get("GORANI_HOST")
    spec = importlib.util.spec_from_file_location("gorani_cmd_rhino7", SCRIPT)
    cmd_rhino7 = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cmd_rhino7
    spec.loader.exec_module(cmd_rhino7)
    test_sketchup.loader = cmd_rhino7.loader   # test_sketchup._request가 쓴다


def tearDownModule():
    if not test_sketchup.READY:
        return
    if _old_host is None:
        os.environ.pop("GORANI_HOST", None)
    else:
        os.environ["GORANI_HOST"] = _old_host


class FakeRhino(test_sketchup.FakeSketchUp):
    """rhino7_host.cs 흉내 — cmd_rhino7이 stdout에 쓴 호출 한 줄을 받아 FakeSketchUp(sketchup_ext.rb 흉내)처럼 답한다."""

    def __init__(self, controller):
        test_sketchup.FakeSketchUp.__init__(self, controller)
        self.lines = []
        cmd_rhino7._out = self

    def write(self, text):
        self.lines.append(text)
        self.push(json.loads(text))

    def flush(self):
        pass


@unittest.skipUnless(test_sketchup.READY, "numpy·shapely 번들 파이썬 + fixture DB에서만")
class SidecarRunTest(unittest.TestCase):
    """엔진 run → sketchup_baker → stdout 호출 — 사본은 context.3dm, 패널에는 Rhino로 보인다."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.controller = cmd_rhino7._Rhino7Controller("7.37.24107.15001")
        cls.fake = FakeRhino(cls.controller)
        cls.response = cmd_rhino7.loader.load("context_builder").run(test_sketchup._request(cls.tmp.name), lambda *a: True, cls.controller.host)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ok_and_copy(self):
        r = self.response
        self.assertTrue(r["ok"], r["error"])
        self.assertTrue(r["context"]["path"].endswith("context.3dm"))
        self.assertTrue(os.path.exists(r["context"]["path"]))
        self.assertEqual(self.fake.calls[:3], ["get_model_attrs", "clear", "bake"])
        self.assertTrue(all(line.endswith("\n") and line.count("\n") == 1 and line.isascii() for line in self.fake.lines))   # 한 줄 = 호출 하나

    def test_host_label(self):
        constants = cmd_rhino7.loader.load("constants")
        label = constants.HOST_LABELS[cmd_rhino7.loader.load("context_builder").get_host()]
        self.assertEqual((label["id"], label["model"], label["dwg"]), ("rhino", "context.3dm", False))
        self.assertEqual(self.controller._get_host_stats(), {"rhino": "7.37.24107.15001"})

    def test_import_replaces(self):
        result = cmd_rhino7.loader.load("sketchup_baker").import_skp(self.controller.host, self.response["dir"])
        self.assertTrue(result["ok"], result["text"])
        self.assertEqual(self.fake.calls[-1], "import")


@unittest.skipUnless(test_sketchup.READY, "numpy·shapely 번들 파이썬 + fixture DB에서만")
class PipeTest(unittest.TestCase):
    """실제 사이드카 프로세스 — 첫 줄 패널 주소, 패널 명령이 부른 호스트 호출이 stdout으로 나오고 stdin 답으로 끝나며, stdin을 닫으면 끝난다."""

    def test_call_reply_and_exit(self):
        process = subprocess.Popen([sys.executable, "-I", "-B", "-X", "utf8", SCRIPT, "7.0"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        lines = queue.Queue()
        threading.Thread(target=lambda: [lines.put(line) for line in process.stdout], daemon=True).start()
        try:
            url = lines.get(timeout=30).strip()
            self.assertTrue(url.startswith("http://127.0.0.1:"), url)

            def post(msg):
                request = urllib.request.Request(url.replace("/?", "/cmd?"), data=json.dumps(msg).encode("utf-8"), method="POST")
                urllib.request.urlopen(request, timeout=10)

            post({"cmd": "pick_curve"})
            # 첫 호출이 stdin 답을 받아 끝나야 둘째 호출(안내 문구와 함께 보낼 문서 원점)이 나온다(메인 스레드 하나)
            for expected_id, method, result in ((1, "pick_curve", {"count": 0, "ring": None, "problem": ""}), (2, "get_model_attrs", [None, None, None])):
                call = json.loads(lines.get(timeout=30))
                self.assertEqual((call["type"], call["id"], call["method"]), ("host_call", expected_id, method))
                process.stdin.write(json.dumps({"cmd": "host_reply", "id": call["id"], "ok": True, "result": result}) + "\n")
                process.stdin.flush()
            process.stdin.close()   # Rhino 종료
            self.assertEqual(process.wait(timeout=30), 0)
        finally:
            if process.poll() is None:
                process.kill()


if __name__ == "__main__":
    unittest.main()
