"""사용자에게 보이는 문구를 패널 언어로 바꾼다 — 패널(site_ui.html)의 tr()와 같은 사전 scripts/i18n.json을 쓴다.

문구 원문(키)은 한국어 그대로 둔다: tr("건물 {0}동", n). 사전은 {"한국어 원문": {"en": …, "es": …, "ja": …, "zh": …}}.
번역이 없으면 영어, 영어도 없으면 원문. 자리표시는 str.format({0}·{1}, {0:.1f}처럼 형식도 된다).
지금 언어는 환경변수(constants.LANG_ENV)에 둔다 — loader.load가 모듈을 다시 읽어도 남는다. 패널 명령마다 cmd_site가 바꾼다.
새 문구를 tr()로 감싸면 i18n.json에 다섯 언어를 넣는다(tests/test_i18n.py가 빠진 것을 잡는다).
"""

import json
import os

import constants

TEXTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "i18n.json")
_texts = None


def get_lang():
    # type: () -> str
    """지금 언어(constants.LANGS). 정하지 않았으면 constants.DEFAULT_LANG."""
    lang = os.environ.get(constants.LANG_ENV, "")
    return lang if lang in constants.LANGS else constants.DEFAULT_LANG


def set_lang(lang):
    # type: (str) -> None
    """언어를 바꾼다. 모르는 값은 무시한다."""
    if lang in constants.LANGS:
        os.environ[constants.LANG_ENV] = lang


def get_texts():
    # type: () -> dict
    """사전 i18n.json(한 번 읽어 둔다)."""
    global _texts
    if _texts is None:
        with open(TEXTS_PATH, encoding="utf-8") as f:
            _texts = json.load(f)
    return _texts


def tr(text, *args):
    # type: (str, object) -> str
    """한국어 원문 → 지금 언어. args가 있으면 {0}·{1} 자리에 넣는다."""
    lang = get_lang()
    if lang != "ko":
        entry = get_texts().get(text) or {}
        text = entry.get(lang) or entry.get("en") or text
    return text.format(*args) if args else text
