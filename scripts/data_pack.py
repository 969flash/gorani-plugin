"""데이터 팩 — 받기(Yak 설치본은 DB 없이 깔리고 패널에서 HOME_DIR/data/에 받는다)와 로컬 팩 열기.

팩 = 시도 하나의 DB 파일 하나(`<시도>_<종류>.db`, 종류 = site·context·terrain)의 xz 압축본. 매니페스트(json)가 목록을 갖는다.
    {"version": "2026-10", "packs": [{"name": "seoul_site.db", "label": "서울 필지", "url": "seoul_site.db.xz",
                                      "size": 원본 바이트, "sha256": 원본 sha256, "bounds": [min_x, min_y, max_x, max_y]}, ...]}
url은 매니페스트 위치 기준 상대경로 또는 절대 URL(컨텍스트·등고선 팩은 국내 서버). 받은 팩의 sha256·bounds는 data/packs.json에 적어
다음 확인 때 바뀐 팩만 다시 받고, 조회 때 대상지에 걸리는 시도 파일만 연다. 표준 라이브러리만 쓴다. 매니페스트는 dev_deploy.py가 만든다.
"""

import hashlib
import json
import lzma
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request

import constants


class _Cancelled(Exception):
    """progress 콜백이 False를 돌려 사용자가 받기를 멈췄다."""


def get_data_dir():
    # type: () -> str
    """팩을 둘 폴더(HOME_DIR/data)."""
    return os.path.join(constants.HOME_DIR, os.path.dirname(constants.DATABASE_PATH))


_MANIFEST = {}   # 매니페스트 주소 → 받은 매니페스트 — 지도를 옮길 때마다(area_packs) 다시 받지 않는다


def get_manifest(manifest_url=None, refresh=False):
    # type: (str, bool) -> dict
    """매니페스트를 받아 dict로(Rhino 세션 동안 한 번). 각 팩의 url을 절대 URL로 바꿔 둔다. 주소가 비었으면 ValueError."""
    manifest_url = manifest_url or constants.DATA_MANIFEST_URL
    if not manifest_url:
        raise ValueError("데이터 주소가 아직 정해지지 않았습니다(constants.DATA_MANIFEST_URL)")
    if refresh or manifest_url not in _MANIFEST:
        with urllib.request.urlopen(manifest_url, timeout=constants.DATA_TIMEOUT_SECONDS) as response:
            manifest = json.loads(response.read().decode("utf-8"))
        for pack in manifest["packs"]:
            pack["url"] = urllib.parse.urljoin(manifest_url, pack["url"])
        _MANIFEST[manifest_url] = manifest
    return _MANIFEST[manifest_url]


def _read_state(data_dir):
    # type: (str) -> dict
    """data/packs.json → {파일명: {"sha256", "bounds"}}. 없거나 깨졌으면 빈 dict."""
    try:
        with open(os.path.join(data_dir, constants.DATA_STATE_FILE_NAME), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def get_local_paths(kind, bounds=None, sido_codes=None, data_dir=None, sgg_codes=None):
    # type: (str, tuple, set, str, set) -> list
    """data/의 `<지역>_<kind>.db` 경로 목록(정렬). 지역 = 시도 접두어(seoul — 개발 DB·옛 시도 팩) 또는 시군구 코드 5자리(배포 팩).

    입력: kind = site·context·terrain. bounds = (min_x, min_y, max_x, max_y) EPSG:5186 — packs.json 범위가 겹치는 파일만.
          sido_codes = PNU 앞 2자리 집합, sgg_codes = PNU 앞 5자리 집합 — 그 지역 파일만(시도 파일은 시도로 본다).
          범위·지역을 모르는 파일은 거르지 않는다.
    출력: 경로 문자열 목록. 없으면 빈 목록.
    """
    data_dir = data_dir or get_data_dir()
    suffix = "_%s.db" % kind
    state = _read_state(data_dir)
    slugs = {constants.SIDO[code][1] for code in sido_codes if code in constants.SIDO} if sido_codes else None
    paths = []
    for name in sorted(os.listdir(data_dir)) if os.path.isdir(data_dir) else []:
        if not name.endswith(suffix):
            continue
        region = name[:-len(suffix)]
        if region.isdigit():
            if (sgg_codes is not None and region not in sgg_codes) or (slugs is not None and region[:2] not in sido_codes):
                continue
        elif slugs is not None and region not in slugs:
            continue
        pack_bounds = (state.get(name) or {}).get("bounds") if isinstance(state.get(name), dict) else None
        if bounds and pack_bounds and not (bounds[0] <= pack_bounds[2] and bounds[2] >= pack_bounds[0]
                                           and bounds[1] <= pack_bounds[3] and bounds[3] >= pack_bounds[1]):
            continue
        paths.append(os.path.join(data_dir, name))
    return paths


class _Rows(list):
    """여러 연결의 결과를 이어 붙인 행 목록 — sqlite3 커서처럼 fetchall·fetchone을 쓴다."""

    def fetchall(self):
        return list(self)

    def fetchone(self):
        return self[0] if self else None


class _Connections:
    """파일이 SQLite ATTACH 상한을 넘을 때 — 묶음마다 open_union 연결을 열고 같은 질의 결과를 이어 붙인다.
    COUNT·GROUP BY는 묶음마다 한 줄씩 나오므로 호출자가 합친다(lot_db·context_db). 같은 id가 여러 시군구 팩에 있으면 호출자가 걸러 낸다."""

    def __init__(self, groups):
        self.groups = groups

    def execute(self, sql, params=()):
        """묶음에 그 테이블이 없으면 건너뛴다 — 컨텍스트+등고선 팩이 상한을 넘으면 등고선 팩만 든 묶음이 생긴다(buildings 없음,
        성수 R=2000 = 6개 구 × 2 = 12개, 2026-10-19). 모든 묶음에 없을 때만 오류."""
        rows, missing, answered = _Rows(), None, False
        for connection in self.groups:
            try:
                rows.extend(connection.execute(sql, params).fetchall())
                answered = True
            except sqlite3.OperationalError as exc:
                if "no such table" not in str(exc):
                    raise
                missing = exc
        if not answered:
            raise missing
        return rows

    def close(self):
        for connection in self.groups:
            connection.close()


def open_databases(paths):
    # type: (list) -> object
    """파일 목록 → 연결 하나(open_union). 상한(DATA_MAX_OPEN_FILES)을 넘으면 묶음마다 연결해 결과를 이어 붙이는 _Connections."""
    size = constants.DATA_MAX_OPEN_FILES
    if len(paths) <= size:
        return open_union(paths)
    return _Connections([open_union(paths[i:i + size]) for i in range(0, len(paths), size)])


def open_union(paths):
    # type: (list) -> sqlite3.Connection
    """여러 시도 DB를 한 연결로 연다.

    처리: 첫 파일이 main, 나머지는 ATTACH. 둘 이상이 가진 테이블마다 같은 이름의 TEMP VIEW(UNION ALL)를 만들어
          본 테이블을 가린다 — 이름 해석이 temp → main → 붙인 DB 순이라 기존 질의문을 그대로 쓴다. id는 빌드 때
          시도 코드로 띄워 두어(dev 빌더) 겹치지 않는다. 각 갈래가 자기 인덱스를 쓴다(EXPLAIN 확인).
    출력: sqlite3.Connection(row_factory = Row). SQLite가 붙일 수 있는 파일은 main 포함 11개까지 — 넘으면 RuntimeError.
    """
    if len(paths) > constants.DATA_MAX_OPEN_FILES:
        raise RuntimeError("한 번에 열 수 있는 지역 DB는 %d개까지입니다(%d개). 대상지를 줄이거나 쓰지 않는 지역 DB를 data 폴더에서 빼세요"
                           % (constants.DATA_MAX_OPEN_FILES, len(paths)))
    connection = sqlite3.connect(paths[0])
    connection.row_factory = sqlite3.Row
    schemas = ["main"]
    for index, path in enumerate(paths[1:], start=1):
        schema = "pack%d" % index
        connection.execute("ATTACH DATABASE ? AS %s" % schema, (path,))
        schemas.append(schema)
    if len(schemas) == 1:
        return connection
    tables = {}
    for schema in schemas:
        for (name,) in connection.execute("SELECT name FROM %s.sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%%'" % schema):
            tables.setdefault(name, []).append(schema)
    for name, owners in tables.items():
        if len(owners) > 1:
            connection.execute('CREATE TEMP VIEW "%s" AS %s' % (name, " UNION ALL ".join('SELECT * FROM %s."%s"' % (s, name) for s in owners)))
    return connection


def _write_state(data_dir, state):
    # type: (str, dict) -> None
    path = os.path.join(data_dir, constants.DATA_STATE_FILE_NAME)
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)


def get_missing_packs(manifest, data_dir=None, bounds=None):
    # type: (dict, str, tuple) -> list
    """받아야 할 팩 목록 — 파일이 없거나 받은 sha256이 매니페스트와 다른 것. bounds(EPSG:5186)를 주면 그 범위에 걸치는 팩만(시군구 팩)."""
    data_dir = data_dir or get_data_dir()
    state = _read_state(data_dir)
    return [pack for pack in manifest["packs"]
            if ((state.get(pack["name"]) or {}).get("sha256") != pack["sha256"] or not os.path.exists(os.path.join(data_dir, pack["name"])))
            and (bounds is None or _is_overlapping(bounds, pack.get("bounds")))]


def get_installed_names(manifest, data_dir=None):
    # type: (dict, str) -> set
    """받아 둔 팩 이름 — 매니페스트와 sha256이 같은 것."""
    data_dir = data_dir or get_data_dir()
    state = _read_state(data_dir)
    return {pack["name"] for pack in manifest["packs"] if (state.get(pack["name"]) or {}).get("sha256") == pack["sha256"]}


def _is_overlapping(bounds, pack_bounds):
    # type: (tuple, list) -> bool
    return not pack_bounds or (bounds[0] <= pack_bounds[2] and bounds[2] >= pack_bounds[0]
                               and bounds[1] <= pack_bounds[3] and bounds[3] >= pack_bounds[1])


def _open_pack(pack, client_id, manifest_url):
    # type: (dict, str, str) -> tuple
    """팩 주소를 연다. 403·404면 국내 서버 주소가 바뀐 것일 수 있어(문지기 서버로 옮김·되돌림) 매니페스트를 새로 받아 한 번만 다시 연다.
    문지기 서버의 하루 한도(429)는 사용자에게 보일 문장으로 바꾼다. 출력: (응답, 실제로 받는 팩 dict)."""
    headers = {"User-Agent": "%s/%s" % (constants.TOOL_NAME, constants.PANEL_VERSION)}
    if client_id and not pack["name"].endswith("_site.db"):   # 필지 팩(Hugging Face)에는 보내지 않는다
        headers["X-UDT-Client"] = client_id   # 국내 문지기 서버가 설치마다 하루 한도를 센다(docs/domestic_gate.md)

    def open_url(url):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=constants.DATA_TIMEOUT_SECONDS)
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                raise ValueError("오늘 받을 수 있는 지역 데이터 양을 넘었습니다 — 내일 다시 받아 주세요") from None
            raise

    try:
        return open_url(pack["url"]), pack
    except urllib.error.HTTPError as exc:
        if exc.code not in (403, 404):
            raise
        fresh = next((p for p in get_manifest(manifest_url, refresh=True)["packs"] if p["name"] == pack["name"]), None)
        if not fresh or fresh["url"] == pack["url"]:
            raise
    return open_url(fresh["url"]), fresh


def download_pack(pack, data_dir=None, progress=None, client_id="", manifest_url=None):
    # type: (dict, str, callable, str, str) -> bool
    """팩 하나를 받아 풀면서 쓴다.

    입력: 매니페스트의 팩 dict(절대 url), 저장 폴더, progress(받은 원본 바이트, 전체 원본 바이트) -> False면 취소,
          설치 ID(usage_stats.get_client_id — 국내 서버가 설치마다 한도를 센다), 다시 받을 매니페스트 주소(None = constants).
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
        response, pack = _open_pack(pack, client_id, manifest_url)
        with response, open(part, "wb") as f:
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
    state[pack["name"]] = {"sha256": pack["sha256"], "bounds": pack.get("bounds")}
    _write_state(data_dir, state)
    return True
