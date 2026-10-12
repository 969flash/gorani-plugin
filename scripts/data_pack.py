"""배포 DB(데이터 팩) 받기 — Yak 설치본은 DB 없이 깔리고, 패널에서 이 모듈로 HOME_DIR/data/에 받는다.

매니페스트(json) 하나가 팩 목록을 갖는다. 팩 = DB 파일 하나의 xz 압축본.
    {"version": "2026-10", "packs": [{"name": "seoul_site.db", "label": "서울 필지", "url": "seoul_site.db.xz",
                                      "size": 원본 바이트, "sha256": 원본 sha256}, ...]}
url은 매니페스트 위치 기준 상대경로 또는 절대 URL(등고선 팩은 국내 서버). 받은 팩의 sha256은 data/packs.json에 적어
다음 확인 때 바뀐 팩만 다시 받는다. 표준 라이브러리만 쓴다(urllib·lzma·hashlib). 매니페스트는 dev_deploy.py가 만든다.
"""

import hashlib
import json
import lzma
import os
import urllib.parse
import urllib.request

import constants


class _Cancelled(Exception):
    """progress 콜백이 False를 돌려 사용자가 받기를 멈췄다."""


def get_data_dir():
    # type: () -> str
    """팩을 둘 폴더(HOME_DIR/data)."""
    return os.path.join(constants.HOME_DIR, os.path.dirname(constants.DATABASE_PATH))


def get_manifest(manifest_url=None):
    # type: (str) -> dict
    """매니페스트를 받아 dict로. 각 팩의 url을 절대 URL로 바꿔 둔다. 주소가 비었으면 ValueError."""
    manifest_url = manifest_url or constants.DATA_MANIFEST_URL
    if not manifest_url:
        raise ValueError("데이터 주소가 아직 정해지지 않았습니다(constants.DATA_MANIFEST_URL)")
    with urllib.request.urlopen(manifest_url, timeout=constants.DATA_TIMEOUT_SECONDS) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    for pack in manifest["packs"]:
        pack["url"] = urllib.parse.urljoin(manifest_url, pack["url"])
    return manifest


def _read_state(data_dir):
    # type: (str) -> dict
    """data/packs.json → {파일명: sha256}. 없거나 깨졌으면 빈 dict."""
    try:
        with open(os.path.join(data_dir, constants.DATA_STATE_FILE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _write_state(data_dir, state):
    # type: (str, dict) -> None
    path = os.path.join(data_dir, constants.DATA_STATE_FILE_NAME)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def get_missing_packs(manifest, data_dir=None):
    # type: (dict, str) -> list
    """받아야 할 팩 목록 — 파일이 없거나 받은 sha256이 매니페스트와 다른 것."""
    data_dir = data_dir or get_data_dir()
    state = _read_state(data_dir)
    return [pack for pack in manifest["packs"]
            if state.get(pack["name"]) != pack["sha256"] or not os.path.exists(os.path.join(data_dir, pack["name"]))]


def download_pack(pack, data_dir=None, progress=None):
    # type: (dict, str, callable) -> bool
    """팩 하나를 받아 풀면서 쓴다.

    입력: 매니페스트의 팩 dict(절대 url), 저장 폴더, progress(받은 원본 바이트, 전체 원본 바이트) -> False면 취소.
    처리: xz 스트림을 조각마다 풀어 .part 파일에 쓰며 sha256을 잰다. 끝까지 맞으면 원래 이름으로 바꾸고 packs.json에 적는다.
          취소·오류면 .part를 지운다. 기존 파일은 다 받은 뒤에야 교체하므로 중간에 끊겨도 쓰던 DB는 남는다.
    출력: 다 받았으면 True, 취소면 False. sha256 불일치는 ValueError.
    """
    data_dir = data_dir or get_data_dir()
    os.makedirs(data_dir, exist_ok=True)
    target = os.path.join(data_dir, pack["name"])
    part = target + ".part"
    digest = hashlib.sha256()
    decompressor = lzma.LZMADecompressor()
    written = 0
    try:
        with urllib.request.urlopen(pack["url"], timeout=constants.DATA_TIMEOUT_SECONDS) as response, open(part, "wb") as f:
            while True:
                chunk = response.read(constants.DATA_CHUNK_BYTES)
                if not chunk:
                    break
                data = decompressor.decompress(chunk)
                f.write(data)
                digest.update(data)
                written += len(data)
                if progress and progress(written, pack["size"]) is False:
                    raise _Cancelled
        if digest.hexdigest() != pack["sha256"]:
            raise ValueError("%s 내려받기가 손상됐습니다(sha256 불일치). 다시 받아 주세요" % pack["name"])
        os.replace(part, target)
    except _Cancelled:
        os.remove(part)
        return False
    except BaseException:
        if os.path.exists(part):
            os.remove(part)
        raise
    state = _read_state(data_dir)
    state[pack["name"]] = pack["sha256"]
    _write_state(data_dir, state)
    return True
