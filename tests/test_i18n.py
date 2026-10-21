"""다국어 사전(scripts/i18n.json) — 패널·로직 모듈의 tr("…") 원문이 전부 사전에 있고, 네 언어 번역의 자리표시가 원문과 같은지."""

import ast
import json
import os
import re
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants   # noqa: E402
import i18n   # noqa: E402

TARGET_LANGS = [lang for lang in constants.LANGS if lang != "ko"]   # 한국어는 원문(키)
PLACEHOLDER = re.compile(r"\{\d+(?::[^{}]*)?\}")
JS_TR = re.compile(r"""\btr\(\s*(?:"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)')""")


def get_js_keys(path):
    # type: (Path) -> set
    """패널 HTML의 tr("…")·tr('…') 첫 인자 원문."""
    keys = set()
    for double, single in JS_TR.findall(path.read_text(encoding="utf-8")):
        keys.add(json.loads('"%s"' % double) if double else json.loads('"%s"' % single.replace("\\'", "'").replace('"', '\\"')))
    return keys


def get_py_keys(path):
    # type: (Path) -> set
    """파이썬 모듈의 tr("…") 첫 인자 원문(문자열 상수만)."""
    keys = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
            if name == "tr":
                keys.add(node.args[0].value)
    return keys


def get_code_files():
    # type: () -> list
    return [SCRIPTS_DIR / "site_ui.html"] + sorted(p for p in SCRIPTS_DIR.glob("*.py") if not p.name.startswith(("dev_", "server_")))


class I18nTest(unittest.TestCase):
    def setUp(self):
        self.texts = i18n.get_texts()

    def test_every_key_translated(self):
        missing = {}
        for path in get_code_files():
            keys = get_js_keys(path) if path.suffix == ".html" else get_py_keys(path)
            for key in keys:
                entry = self.texts.get(key) or {}
                langs = [lang for lang in TARGET_LANGS if not entry.get(lang)]
                if langs:
                    missing.setdefault(path.name, []).append("%s %s" % (key, langs))
        self.assertEqual(missing, {}, "i18n.json에 번역이 없다")

    def test_placeholders_match(self):
        bad = []
        for key, entry in self.texts.items():
            want = sorted(PLACEHOLDER.findall(key))
            for lang in TARGET_LANGS:
                if sorted(PLACEHOLDER.findall(entry.get(lang) or "")) != want:
                    bad.append("%s [%s] %s" % (key, lang, entry.get(lang)))
        self.assertEqual(bad, [], "번역의 자리표시가 원문과 다르다")

    def test_panel_html_safe(self):
        # 패널은 번역문을 HTML에 그대로 넣는다(한국어 원문처럼) — 원문에 없는 " & < >가 번역에 생기면 속성·마크업이 깨진다
        bad = []
        for key in get_js_keys(SCRIPTS_DIR / "site_ui.html"):
            for lang in TARGET_LANGS:
                text = (self.texts.get(key) or {}).get(lang) or ""
                bad += ["%s [%s] %s" % (key, lang, text) for ch in '"&<>' if ch in text and ch not in key]
        self.assertEqual(bad, [], "패널 번역에 HTML 특수문자")

    def test_panel_placeholders_once(self):
        # 호스트는 자리표시를 str.replace로 바꾼다 — 스크립트 주석 등에 같은 글이 또 있으면 그 자리에도 들어가 script가 깨진다
        html = (SCRIPTS_DIR / "site_ui.html").read_text(encoding="utf-8")
        for mark in ("<!--I18N-->", "<!--VENDOR_JS-->", "<!--VENDOR_CSS-->", "<!--FONT_WOFF2-->"):
            self.assertEqual(html.count(mark), 1, mark)

    def test_only_known_langs(self):
        bad = [key for key, entry in self.texts.items() if set(entry) - set(TARGET_LANGS)]
        self.assertEqual(bad, [], "모르는 언어 코드(한국어는 키라 넣지 않는다)")

    def test_no_orphan_keys(self):
        # 패널은 Python이 보낸 원문(도면 이름·스타일 이름 등)을 tr(변수)로 바꾼다 — 소스 어딘가에 원문이 있으면 쓰는 것으로 친다.
        # 파이썬은 문자열 상수(이어 쓴 리터럴은 합친 값, 이스케이프는 푼 값), 패널 HTML은 글 그대로 찾는다
        html = (SCRIPTS_DIR / "site_ui.html").read_text(encoding="utf-8")
        constants_ = set()
        for path in get_code_files()[1:]:
            constants_ |= {node.value for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
                           if isinstance(node, ast.Constant) and isinstance(node.value, str)}
        orphans = [key for key in self.texts if key not in constants_ and key not in html]
        self.assertEqual(orphans, [], "코드에 없는 원문 — 문구를 고쳤으면 사전 키도 고친다")

    def test_default_lang_in_prefs(self):
        # 처음 설치는 영어, 0.2.2까지 쓰던 설치본(options는 있고 lang이 없다)은 한국어, 고른 언어는 그대로
        import json
        import tempfile
        import site_prefs
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "prefs.json")
            self.assertEqual(site_prefs.get_options(path)["lang"], "en")
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"version": 2, "options": {"mode": "area"}}, f)
            self.assertEqual(site_prefs.get_options(path)["lang"], "ko")
            site_prefs.save_options({"lang": "ja"}, path)
            self.assertEqual(site_prefs.get_options(path)["lang"], "ja")

    def test_tr_fallbacks(self):
        old = os.environ.get(constants.LANG_ENV)
        try:
            i18n.set_lang("ko")
            self.assertEqual(i18n.tr("없는 문구 {0}", 3), "없는 문구 3")
            i18n.set_lang("en")
            self.assertEqual(i18n.tr("없는 문구 {0}", 3), "없는 문구 3")   # 사전에 없으면 원문
            i18n.set_lang("xx")   # 모르는 값은 무시
            self.assertEqual(i18n.get_lang(), "en")
            key = next(iter(self.texts))
            self.assertEqual(i18n.tr(key), self.texts[key]["en"])
        finally:
            if old is None:
                os.environ.pop(constants.LANG_ENV, None)
            else:
                os.environ[constants.LANG_ENV] = old


if __name__ == "__main__":
    unittest.main()
