"""일본 건물 팩 — 국토교통성 3D 도시모델(Project PLATEAU)에서 건물 외곽·높이만 뽑아 시구정촌마다 팩 하나를 만든다.

Rhino 밖 python3, 표준 라이브러리만. 도시별 CityGML zip(대부분 DEM이라 수백 MB~수백 GB)은 받지 않고 HTTP Range로
udx/bldg/*.gml만 흘려 읽는다. 팩 = build/packs/jp/jp<시구정촌코드>_context.db.xz, 목록 = 같은 폴더 manifest.json →
Hugging Face 데이터셋(constants.DATA_REPO_ID)의 jp/. 좌표는 경위도(EPSG:6697 — WGS84와 수 cm 차이라 같은 것으로 본다),
칸은 런타임(context_db._building_from_row)이 읽는 이름 그대로. 근거 docs/research/japan.md, 계획 docs/japan_plan.md.

    python3 scripts/dev_plateau.py catalog          # CKAN → data/raw/plateau/catalog.json (도시별 최신 CityGML zip)
    python3 scripts/dev_plateau.py build [코드 …]   # 팩 만들기. 코드가 없으면 카탈로그 전부, 같은 연도 팩이 있으면 건너뛴다
    python3 scripts/dev_plateau.py roads [코드 …]   # 있는 팩에 도로면(udx/tran, tran:Road LOD1)을 features 표로 넣는다 — bldg는 다시 읽지 않는다
    python3 scripts/dev_plateau.py upload           # 팩·매니페스트·데이터셋 카드를 올린다(huggingface_hub 로그인 먼저)
"""

import argparse
import concurrent.futures
import datetime
import hashlib
import http.client
import io
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402

CATALOG_PATH = os.path.join(ROOT_DIR, "data", "raw", "plateau", "catalog.json")
PACK_DIR = os.path.join(ROOT_DIR, "build", "packs", constants.JP_PACK_DIR)
GML = "{http://www.opengis.net/gml}"
PACKAGE_NAME = re.compile(r"^plateau-(\d{5})-.+-(\d{4})$")   # plateau-13215-kunitachi-shi-2025
CITY_NAME = re.compile(r"）(.+?)（\d{4}年度）")                 # 3D都市モデル（Project PLATEAU）国立市（2025年度）
ZIP_BUFFER_BYTES = 16 << 20       # Range 요청 하나에 16 MB — 도시 전체 18 GB를 요청 1,200개 안팎으로 받는다
BATCH_ROWS = 5000
RETRIES = 4
SCHEMA_SQL = """
CREATE TABLE data_sources (
    source_id TEXT PRIMARY KEY, name TEXT NOT NULL, page_url TEXT NOT NULL, reference_date TEXT,
    acquired_at TEXT NOT NULL, crs TEXT, license TEXT, note TEXT
);
CREATE TABLE buildings (
    building_id INTEGER PRIMARY KEY, src_key TEXT NOT NULL, pnu TEXT, usability TEXT, strct_cd TEXT,
    grnd_flr INTEGER NOT NULL DEFAULT 0, ugrnd_flr INTEGER NOT NULL DEFAULT 0, flr_src TEXT,
    height_m REAL NOT NULL, height_src TEXT NOT NULL, height_grade TEXT NOT NULL, attr_flag TEXT, use_apr_day TEXT,
    status TEXT NOT NULL DEFAULT 'active', bld_nm TEXT, ngii_kind TEXT, ngii_use TEXT,
    footprint_area_sqm REAL NOT NULL, total_area_sqm REAL, geometry_json TEXT NOT NULL, geometry_crs INTEGER NOT NULL,
    source_id TEXT NOT NULL, reference_date TEXT, min_x REAL NOT NULL, max_x REAL NOT NULL, min_y REAL NOT NULL, max_y REAL NOT NULL
);
"""   # 한국 컨텍스트 팩(dev_context_builder) 중 런타임이 읽는 칸만. ngii_kind = 원천 용도 코드(OSM 갈래가 building 태그를 두는 자리)
FEATURES_SQL = """
CREATE TABLE IF NOT EXISTS features (
    feature_id INTEGER PRIMARY KEY, source_id TEXT NOT NULL, theme TEXT NOT NULL, kind TEXT NOT NULL, code TEXT, name TEXT, value REAL,
    attrs_json TEXT, sheet TEXT, geometry_json TEXT NOT NULL, geometry_crs INTEGER NOT NULL, reference_date TEXT,
    min_x REAL NOT NULL, max_x REAL NOT NULL, min_y REAL NOT NULL, max_y REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_features_bbox ON features(min_x, max_x, min_y, max_y);
CREATE INDEX IF NOT EXISTS idx_features_theme ON features(theme, kind);
"""   # 한국 컨텍스트 팩 features와 같은 칸(context_db._feature_from_row) — 도로면(theme road, kind surface, code = tran:function)
LICENSE = "CC BY 4.0(公共データ利用規約 第1.0版 호환). 저작권은 각 지방공공단체"


# ── 받기 ────────────────────────────────────────────────

def _get(url, headers=None):
    # type: (str, dict) -> bytes
    """GET 본문. 끊기면 몇 번 다시 시도한다(전국 18 GB를 받는 동안 연결이 몇 번은 끊긴다)."""
    request = urllib.request.Request(url, headers=dict(headers or {}, **{"User-Agent": constants.OSM_USER_AGENT}))
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read()
        except (OSError, http.client.HTTPException):
            if attempt == RETRIES - 1:
                raise
            time.sleep(5 * (attempt + 1))


class RangeFile(io.RawIOBase):
    """HTTP Range로 읽는 파일 — zipfile이 zip 전체를 받지 않고 필요한 항목만 읽는다(PLATEAU 자산 서버는 Range를 받는다, research §5)."""

    def __init__(self, url):
        self.url, self.pos = url, 0
        request = urllib.request.Request(url, method="HEAD", headers={"User-Agent": constants.OSM_USER_AGENT})
        with urllib.request.urlopen(request, timeout=60) as response:
            self.size = int(response.headers["Content-Length"])

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        self.pos = (offset, self.pos + offset, self.size + offset)[whence]
        return self.pos

    def readinto(self, buffer):
        if self.pos >= self.size:
            return 0
        data = _get(self.url, {"Range": "bytes=%d-%d" % (self.pos, min(self.pos + len(buffer), self.size) - 1)})
        buffer[:len(data)] = data
        self.pos += len(data)
        return len(data)


def get_catalog():
    # type: () -> dict
    """CKAN의 PLATEAU 패키지 → 도시별 최신 연도 CityGML zip {코드: {year, url, title, city, page_url}}. catalog.json에도 쓴다."""
    packages, start = [], 0
    while True:
        query = urllib.parse.urlencode({"q": constants.PLATEAU_CKAN_QUERY, "rows": 1000, "start": start})
        result = json.loads(_get(constants.PLATEAU_CKAN_URL + "?" + query).decode("utf-8"))["result"]
        packages += result["results"]
        start += 1000
        if start >= result["count"]:
            break
    catalog = {}
    for package in packages:
        match = PACKAGE_NAME.match(package["name"])
        if not match or match.group(1) in constants.PLATEAU_SKIP_CODES:
            continue
        code, year = match.group(1), int(match.group(2))
        resources = [r for r in package["resources"] if (r.get("name") or "").startswith("CityGML") and (r.get("format") or "").upper() == "ZIP"]
        if not resources or (code in catalog and catalog[code]["year"] >= year):
            continue
        resource = max(resources, key=lambda r: int((re.findall(r"v(\d+)", r["name"]) or ["1"])[0]))   # 'CityGML（v5）' — 같은 해 판이 여럿이면 최신 사양
        city = CITY_NAME.search(package["title"])
        catalog[code] = {"year": year, "url": resource["url"], "title": package["title"], "city": city.group(1) if city else code,
                         "page_url": "https://www.geospatial.jp/ckan/dataset/" + package["name"]}
    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(catalog.items())), f, ensure_ascii=False, indent=1)
    return catalog


# ── CityGML 읽기 ────────────────────────────────────────

def _get_name(element):
    # type: (ET.Element) -> str
    return element.tag.rsplit("}", 1)[-1]


def _get_points(ring):
    # type: (ET.Element) -> list
    """gml:exterior·interior → [(경도, 위도, 표고)]. 원천 posList 순서는 위도·경도·표고다(EPSG:6697)."""
    pos_list = ring.find(".//" + GML + "posList")
    if pos_list is not None:
        values, dim = (pos_list.text or "").split(), int(pos_list.get("srsDimension") or 3)
    else:
        values, dim = [v for pos in ring.iter(GML + "pos") for v in (pos.text or "").split()], 3
    return [(float(values[i + 1]), float(values[i]), float(values[i + 2]) if dim > 2 else 0.0) for i in range(0, len(values) - dim + 1, dim)]


def get_clean_ring(points):
    # type: (list) -> list
    """[(경도, 위도, …)] → 소수 PLATEAU_DIGITS 자리 [[경도, 위도]] 닫힌 링. 반올림 뒤 연속 중복을 빼고, 꼭짓점 3개 미만이면 None."""
    ring = []
    for point in points:
        xy = [round(point[0], constants.PLATEAU_DIGITS), round(point[1], constants.PLATEAU_DIGITS)]
        if not ring or ring[-1] != xy:
            ring.append(xy)
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring.pop()
    return ring + [ring[0]] if len(ring) >= 3 else None


def _get_polygon(polygon):
    # type: (ET.Element) -> list
    """gml:Polygon → [바깥 링, 구멍 …](원천 점 그대로). 바깥 링이 없으면 None."""
    exterior = polygon.find(GML + "exterior")
    if exterior is None:
        return None
    return [_get_points(exterior)] + [_get_points(ring) for ring in polygon.findall(GML + "interior")]


def _get_footprint(element):
    # type: (ET.Element) -> list
    """건물(또는 BuildingPart) → 외곽 폴리곤 [[바깥 링, 구멍 …], …](get_clean_ring 꼴).
    lod0RoofEdge(지붕 외곽 투영) → lod0FootPrint(1층 외곽) → lod1Solid 바닥면(가장 낮은 면) 순. 구니타치 2025는 전부 lod0RoofEdge."""
    children = {_get_name(child): child for child in element}
    polygons = []
    for name in ("lod0RoofEdge", "lod0FootPrint"):
        if name in children:
            polygons = [p for p in (_get_polygon(e) for e in children[name].iter(GML + "Polygon")) if p]
            if polygons:
                break
    if not polygons and "lod1Solid" in children:
        faces = [p for p in (_get_polygon(e) for e in children["lod1Solid"].iter(GML + "Polygon")) if p and p[0]]
        if faces:
            bottom = min(max(z for _x, _y, z in face[0]) for face in faces)
            polygons = [face for face in faces if max(z for _x, _y, z in face[0]) <= bottom + 0.01]
    result = []
    for polygon in polygons:
        rings = [get_clean_ring(ring) for ring in polygon]
        if rings[0]:
            result.append([rings[0]] + [ring for ring in rings[1:] if ring])
    return result


def _get_attributes(element):
    # type: (ET.Element) -> dict
    """직속 자식의 속성 문자열 — measuredHeight·storeysAboveGround·storeysBelowGround·usage·name(gml:name)."""
    attributes = {}
    for child in element:
        name = _get_name(child)
        if name in ("measuredHeight", "storeysAboveGround", "storeysBelowGround", "usage") or child.tag == GML + "name":
            attributes[name] = (child.text or "").strip()
    return attributes


def _get_buildings(building):
    # type: (ET.Element) -> list
    """bldg:Building 하나 → 건물 dict 목록 {id, polygons, 속성…}. 자기 외곽이 없고 BuildingPart만 있으면 부분마다 한 동(속성은 부분 것이 먼저)."""
    attributes = _get_attributes(building)
    polygons = _get_footprint(building)
    if polygons:
        return [dict(attributes, id=building.get(GML + "id") or "", polygons=polygons)]
    parts = []
    for part in building.iter():
        if _get_name(part) == "BuildingPart":
            polygons = _get_footprint(part)
            if polygons:
                part_attributes = {k: v for k, v in _get_attributes(part).items() if v}
                parts.append(dict(attributes, **part_attributes, id=part.get(GML + "id") or "", polygons=polygons))
    return parts


def iter_buildings(stream):
    # type: (object) -> object
    """CityGML 바이트 스트림 → 건물 dict를 차례로(_get_buildings). 루트 직속 요소는 끝나는 대로 비운다 — 텍스처 좌표(appearanceMember)가 수 GB다."""
    depth, root = 0, None
    for event, element in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
            root = element if root is None else root
            depth += 1
            continue
        depth -= 1
        if element.tag.endswith("}Building"):
            yield from _get_buildings(element)
        if depth == 1:
            root.clear()


def _get_lod1_polygons(element):
    # type: (ET.Element) -> list
    """tran:Road 직속 lod1MultiSurface의 폴리곤 → [[바깥 링, 구멍 …]](get_clean_ring 꼴). LOD1 도로면은 삼각형 여럿으로 쪼개져 있다(신주쿠 457면 → 10,825폴리곤)."""
    polygons = []
    for child in element:
        if _get_name(child) == "lod1MultiSurface":
            for polygon in (_get_polygon(e) for e in child.iter(GML + "Polygon")):
                if polygon:
                    rings = [get_clean_ring(ring) for ring in polygon]
                    if rings[0]:
                        polygons.append([rings[0]] + [ring for ring in rings[1:] if ring])
    return polygons


def iter_roads(stream):
    # type: (object) -> object
    """tran CityGML 스트림 → 도로 dict {id, function, name, polygons}(tran:Road마다). TrafficArea(LOD2 차로·보도)는 읽지 않는다."""
    depth, root = 0, None
    for event, element in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
            root = element if root is None else root
            depth += 1
            continue
        depth -= 1
        if element.tag.endswith("}Road"):
            polygons = _get_lod1_polygons(element)
            if polygons:
                attributes = {_get_name(c): (c.text or "").strip() for c in element if _get_name(c) in ("function", "class") or c.tag == GML + "name"}
                yield dict(id=element.get(GML + "id") or "", polygons=polygons, function=attributes.get("function", ""),
                           cls=attributes.get("class", ""), name=attributes.get("name", ""))
        if depth == 1:
            root.clear()


def get_road_geometry(polygons):
    # type: (list) -> dict
    """도로 하나의 LOD1 폴리곤들 → GeoJSON (Multi)Polygon(경위도). 신주쿠 2025는 도로마다 폴리곤 하나(31,433면 전부)라 그대로 쓰고,
    여럿이면 m로 투영해 공유 변을 지운 외곽으로 합친 뒤(non_rhino_utils.get_merged_rings — m 단위 전제) 경위도로 되돌린다. 합치지 못하면 None."""
    if len(polygons) == 1:
        return {"type": "Polygon", "coordinates": polygons[0]}
    import non_rhino_utils
    lng0, lat0 = polygons[0][0][0]
    non_rhino_utils.set_projection(lng0, lat0)
    try:
        metric = [[[non_rhino_utils.get_tm_from_wgs84(x, y) for x, y in ring] for ring in polygon] for polygon in polygons]
        outers, holes = non_rhino_utils.get_merged_rings(metric, constants.PLATEAU_ROAD_TOLERANCE_M)
        if not outers:
            return None
        parts = []
        for outer in outers:
            inner = [h for h in holes if non_rhino_utils.is_point_in_ring(h[0][0], h[0][1], outer)]
            parts.append([[[round(v, constants.PLATEAU_DIGITS) for v in non_rhino_utils.get_wgs84_from_tm(x, y)] for x, y in ring + [ring[0]]]
                          for ring in [outer] + inner])
    finally:
        non_rhino_utils.set_projection()
    return {"type": "Polygon", "coordinates": parts[0]} if len(parts) == 1 else {"type": "MultiPolygon", "coordinates": parts}


def get_road_row(road, feature_id, reference_date):
    # type: (dict, int, str) -> tuple
    """도로 dict → features 행(FEATURES_SQL 칸 순서). 외곽을 못 만들거나 일본 밖이면 None."""
    geometry = get_road_geometry(road["polygons"])
    if geometry is None:
        return None
    rings = geometry["coordinates"] if geometry["type"] == "Polygon" else [r for polygon in geometry["coordinates"] for r in polygon]
    xs = [p[0] for ring in rings for p in ring]
    ys = [p[1] for ring in rings for p in ring]
    west, south, east, north = constants.JP_BOUNDS
    if not (west <= min(xs) and max(xs) <= east and south <= min(ys) and max(ys) <= north):
        return None
    attrs = {"plateau": road["id"], "function": road["function"], "class": road["cls"]}
    return (feature_id, "plateau", "road", "surface", road["function"], road["name"] or None, None, json.dumps(attrs, ensure_ascii=False, separators=(",", ":")),
            "", json.dumps(geometry, separators=(",", ":")), 4326, reference_date, min(xs), max(xs), min(ys), max(ys))


def add_roads(code, entry, pack_dir=PACK_DIR):
    # type: (str, dict, str) -> dict
    """있는 팩(xz)을 풀어 udx/tran/*.gml의 도로면을 features 표에 넣고 다시 xz. 매니페스트 항목(size·sha256·xz_size·roads)을 돌려준다.
    feature_id = 코드 × 10⁶ + 순번(팩끼리 겹치지 않는다). tran이 없는 도시는 roads 0으로 표만 만든다(런타임이 OSM 버퍼로 메운다)."""
    started = time.time()
    name = "%s%s_context.db" % (constants.JP_PACK_PREFIX, code)
    path = os.path.join(pack_dir, name)
    if not os.path.exists(path + ".xz"):
        return None
    if os.path.exists(path):
        os.remove(path)
    subprocess.run(["xz", "-dk", path + ".xz"], check=True)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = MEMORY")
    connection.execute("PRAGMA synchronous = OFF")
    connection.executescript(FEATURES_SQL)
    connection.execute("DELETE FROM features WHERE source_id = 'plateau'")
    reference_date = connection.execute("SELECT reference_date FROM data_sources WHERE source_id = 'plateau'").fetchone()
    reference_date = reference_date[0] if reference_date else None
    archive = zipfile.ZipFile(io.BufferedReader(RangeFile(entry["url"]), ZIP_BUFFER_BYTES))
    members = sorted(i.filename for i in archive.infolist() if i.filename.startswith("udx/tran/") and i.filename.count("/") == 2
                     and i.filename.endswith(".gml"))
    seen, rows, stats = set(), [], {"roads": 0, "skipped": 0, "polygons": 0, "gml_bytes": sum(archive.getinfo(m).compress_size for m in members)}
    for member in members:
        with archive.open(member) as stream:
            for road in iter_roads(stream):
                if road["id"] in seen:
                    continue
                seen.add(road["id"])
                stats["polygons"] += len(road["polygons"])
                row = get_road_row(road, int(code) * 10 ** 6 + len(seen), reference_date)
                if row is None:
                    stats["skipped"] += 1
                    continue
                rows.append(row)
                stats["roads"] += 1
                if len(rows) >= BATCH_ROWS:
                    connection.executemany("INSERT INTO features VALUES (%s)" % ",".join("?" * 16), rows)
                    rows = []
    connection.executemany("INSERT INTO features VALUES (%s)" % ",".join("?" * 16), rows)
    connection.execute("UPDATE data_sources SET note = note || ' · 도로면(tran:Road LOD1 외곽, function 코드)' WHERE source_id = 'plateau' AND note NOT LIKE '%도로면%'")
    connection.commit()
    connection.execute("VACUUM")
    connection.close()
    size, sha256 = os.path.getsize(path), _get_sha256(path)
    subprocess.run(["xz", "-6", "-T1", "-f", path], check=True)
    stats["seconds"] = round(time.time() - started)
    return {"name": name, "size": size, "sha256": sha256, "xz_size": os.path.getsize(path + ".xz"), "roads": stats["roads"], "stats": stats}


def add_roads_all(codes=None, workers=6):
    # type: (list, int) -> list
    """매니페스트의 팩(codes만, 없으면 전부)에 도로면을 넣는다. 끝날 때마다 매니페스트(size·sha256·roads)를 고쳐 쓴다. 실패한 코드 목록을 돌려준다."""
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    manifest_path = os.path.join(PACK_DIR, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
    todo = [code for code in (codes or sorted(catalog)) if "%s%s_context.db" % (constants.JP_PACK_PREFIX, code) in packs
            and (codes or "roads" not in packs["%s%s_context.db" % (constants.JP_PACK_PREFIX, code)])]
    print("PLATEAU 도로면 %d곳 (작업 %d개)" % (len(todo), workers), flush=True)
    failed = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(add_roads, code, catalog[code]): code for code in todo}
        for future in concurrent.futures.as_completed(futures):
            code = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                failed.append(code)
                print("  %s %s 실패: %r" % (code, catalog[code]["city"], exc), flush=True)
                continue
            if result is None:
                continue
            pack = packs[result["name"]]
            pack.update({k: v for k, v in result.items() if k != "stats"})
            _write_manifest(packs)
            print("  %s %s: 도로면 %s · %d s · xz %.1f MB" % (code, catalog[code]["city"], format(result["roads"], ","), result["stats"]["seconds"],
                                                           result["xz_size"] / 1e6), flush=True)
    print("실패 %d %s" % (len(failed), " ".join(sorted(failed))), flush=True)
    return failed


# ── 행 만들기 ───────────────────────────────────────────

def _get_number(text):
    # type: (str) -> float
    """속성 문자열 → 수. 비었거나 PLATEAU '모름'(9999·-9999)이면 0."""
    try:
        value = float(text)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if abs(value) >= constants.PLATEAU_UNKNOWN else value


def get_height(attributes):
    # type: (dict) -> tuple
    """속성 → (높이 m, 지상층수, height_src, height_grade). measuredHeight B → 층수 × 층고 C → 기본값 D(osm_context.get_building_height와 같은 등급)."""
    height = _get_number(attributes.get("measuredHeight"))
    levels = int(_get_number(attributes.get("storeysAboveGround")))
    low, high = constants.PLATEAU_HEIGHT_RANGE
    if low <= height <= high:
        return round(height, 2), levels, "plateau_height", "B"
    if levels > 0:
        base, per = constants.FLOOR_HEIGHT_DEFAULT
        return round(base + per * levels, 2), levels, "plateau_levels", "C"
    return constants.DEFAULT_BUILDING_HEIGHT_M, 0, "default", "D"


def get_ring_area(ring):
    # type: (list) -> float
    """경위도 링 → 면적 ㎡. 위도 가운데 등장방형 근사 — 건물 크기에서 오차 0.1 % 미만."""
    meters = math.radians(1.0) * 6378137.0
    scale_x = meters * math.cos(math.radians(sum(p[1] for p in ring) / len(ring)))
    return abs(sum((ring[i][0] * ring[i + 1][1] - ring[i + 1][0] * ring[i][1]) for i in range(len(ring) - 1))) * 0.5 * scale_x * meters


def get_row(building, building_id):
    # type: (dict, int) -> tuple
    """건물 dict → buildings 행(SCHEMA_SQL 칸 순서). 원천 좌표가 일본 밖이면 None(원천 오류)."""
    polygons = building["polygons"]
    xs = [p[0] for polygon in polygons for p in polygon[0]]
    ys = [p[1] for polygon in polygons for p in polygon[0]]
    west, south, east, north = constants.JP_BOUNDS
    if not (west <= min(xs) and max(xs) <= east and south <= min(ys) and max(ys) <= north):
        return None
    height, levels, height_src, grade = get_height(building)
    geometry = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
    return (building_id, "plateau:" + building["id"], None, "", None, levels, int(_get_number(building.get("storeysBelowGround"))),
            "plateau" if levels else "", height, height_src, grade, None, None, "active", building.get("name") or None,
            building.get("usage") or None, None, round(sum(get_ring_area(polygon[0]) for polygon in polygons), 2), None,
            json.dumps(geometry, separators=(",", ":")), 4326, "plateau", None, min(xs), max(xs), min(ys), max(ys))


# ── 팩 ──────────────────────────────────────────────────

def _get_sha256(path):
    # type: (str) -> str
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_pack(code, entry, pack_dir=PACK_DIR):
    # type: (str, dict, str) -> dict
    """도시 하나 → jp<코드>_context.db.xz. 매니페스트 항목 dict(통계 stats 포함)를 돌려준다. 건물이 없으면 None.
    building_id = 코드 × 10⁷ + 순번(팩끼리 겹치지 않는다), 같은 gml:id는 한 번만, reference_date는 행이 아니라 data_sources에."""
    started = time.time()
    name = "%s%s_context.db" % (constants.JP_PACK_PREFIX, code)
    path = os.path.join(pack_dir, name)
    for stale in (path, path + ".xz"):
        if os.path.exists(stale):
            os.remove(stale)
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = MEMORY")
    connection.execute("PRAGMA synchronous = OFF")
    connection.executescript(SCHEMA_SQL)
    archive = zipfile.ZipFile(io.BufferedReader(RangeFile(entry["url"]), ZIP_BUFFER_BYTES))
    # udx/bldg/<3차 메시>_bldg_6697_op.gml — 일부 도시는 _op가 없다(幸手市·大館市 2024). 텍스처는 하위 폴더라 빠진다
    members = sorted(i.filename for i in archive.infolist() if i.filename.startswith("udx/bldg/") and i.filename.count("/") == 2
                     and i.filename.endswith(".gml"))
    seen, rows, stats = set(), [], {"buildings": 0, "duplicates": 0, "outside": 0, "max_extent": 0.0,
                                    "grades": {}, "gml_bytes": sum(archive.getinfo(m).compress_size for m in members)}
    for member in members:
        with archive.open(member) as stream:
            for building in iter_buildings(stream):
                if building["id"] in seen:
                    stats["duplicates"] += 1
                    continue
                seen.add(building["id"])
                row = get_row(building, int(code) * 10 ** 7 + len(seen))
                if row is None:
                    stats["outside"] += 1
                    continue
                rows.append(row)
                stats["buildings"] += 1
                stats["grades"][row[10]] = stats["grades"].get(row[10], 0) + 1
                stats["max_extent"] = max(stats["max_extent"], row[-3] - row[-4], row[-1] - row[-2])
                if len(rows) >= BATCH_ROWS:
                    connection.executemany("INSERT INTO buildings VALUES (%s)" % ",".join("?" * 27), rows)
                    rows = []
    connection.executemany("INSERT INTO buildings VALUES (%s)" % ",".join("?" * 27), rows)
    if not stats["buildings"]:
        connection.close()
        os.remove(path)
        return None
    year = entry["year"]
    connection.execute("INSERT INTO data_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        "plateau", entry["title"], entry["page_url"], "%d-03-31" % (year + 1),
        datetime.datetime.now().isoformat(timespec="seconds"), "EPSG:6697 → 경위도(소수 %d자리)" % constants.PLATEAU_DIGITS, LICENSE,
        "整備年度 %d(%d-04~%d-03). 건물 LOD0 외곽(lod0RoofEdge 우선)·measuredHeight·층수·용도 코드만 뽑아 Gorani가 가공" % (year, year, year + 1)))
    connection.execute("CREATE INDEX idx_buildings_bbox ON buildings(min_x, max_x, min_y, max_y)")
    bounds = connection.execute("SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM buildings").fetchone()
    connection.execute("PRAGMA user_version = %d" % constants.CONTEXT_DATABASE_SCHEMA_VERSION)
    connection.commit()
    connection.close()
    size, sha256 = os.path.getsize(path), _get_sha256(path)
    subprocess.run(["xz", "-6", "-T1", "-f", path], check=True)
    stats["seconds"] = round(time.time() - started)
    return {"name": name, "label": "%s 建物" % entry["city"], "url": name + ".xz", "size": size, "sha256": sha256,
            "bounds": [round(v, constants.PLATEAU_DIGITS) for v in bounds], "xz_size": os.path.getsize(path + ".xz"),
            "year": year, "buildings": stats["buildings"], "stats": stats}


def _write_manifest(packs, pack_dir=PACK_DIR):
    # type: (dict, str) -> str
    """{이름: 항목} → pack_dir/manifest.json(data_pack 매니페스트 꼴, 빌드 통계 stats는 뺀다)."""
    path = os.path.join(pack_dir, "manifest.json")
    entries = [{k: v for k, v in pack.items() if k != "stats"} for _name, pack in sorted(packs.items())]
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        json.dump({"version": datetime.date.today().isoformat(), "packs": entries}, f, ensure_ascii=False, indent=1)
    os.replace(path + ".tmp", path)
    return path


def build(codes=None, workers=8, force=False):
    # type: (list, int, bool) -> list
    """카탈로그의 도시(codes만, 없으면 전부)를 병렬로 팩으로 만든다. 같은 연도 팩이 있으면 건너뛴다(force면 다시).
    끝날 때마다 매니페스트를 고쳐 쓴다 — 중간에 멈춰도 다시 실행하면 이어 만든다. 실패한 코드 목록을 돌려준다."""
    if not os.path.exists(CATALOG_PATH):
        get_catalog()
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    os.makedirs(PACK_DIR, exist_ok=True)
    manifest_path = os.path.join(PACK_DIR, "manifest.json")
    packs = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
    todo = []
    for code in codes or sorted(catalog):
        name = "%s%s_context.db" % (constants.JP_PACK_PREFIX, code)
        done = packs.get(name)
        if not force and done and done["year"] == catalog[code]["year"] and os.path.exists(os.path.join(PACK_DIR, done["url"])):
            continue
        todo.append(code)
    print("PLATEAU 팩 %d곳 만들기 (작업 %d개)" % (len(todo), workers), flush=True)
    failed = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(build_pack, code, catalog[code]): code for code in todo}
        for future in concurrent.futures.as_completed(futures):
            code = futures[future]
            try:
                pack = future.result()
            except Exception as exc:   # 서버·원천 오류 — 나머지는 계속, 다시 실행하면 이 도시만 다시 한다
                failed.append(code)
                print("  %s %s 실패: %r" % (code, catalog[code]["city"], exc), flush=True)
                continue
            if pack is None:
                print("  %s %s: 건물 없음" % (code, catalog[code]["city"]), flush=True)
                continue
            stats = pack["stats"]
            packs[pack["name"]] = pack
            _write_manifest(packs)
            print("  %s %s %d: %s동 · B %.1f %% · %d s · %.1f MB → xz %.1f MB%s" % (
                code, catalog[code]["city"], pack["year"], format(stats["buildings"], ","),
                100.0 * stats["grades"].get("B", 0) / stats["buildings"], stats["seconds"], pack["size"] / 1e6, pack["xz_size"] / 1e6,
                " · 넓은 건물 %.4f°" % stats["max_extent"] if stats["max_extent"] > constants.PLATEAU_MAX_EXTENT_DEG else ""), flush=True)
    total = sum(p["xz_size"] for p in packs.values())
    print("팩 %d개 · 압축 %.2f GB · 실패 %d %s" % (len(packs), total / 1e9, len(failed), " ".join(sorted(failed))), flush=True)
    return failed


# ── 올리기 ──────────────────────────────────────────────

def upload():
    # type: () -> str
    """build/packs/jp/의 팩을 Hugging Face 데이터셋 jp/에 올린 뒤 매니페스트를 올린다(팩이 다 올라간 뒤에야 목록에 보인다).
    데이터셋 카드(dev_deploy.DATASET_CARD)도 고친다. 끊겨도 다시 실행하면 이어 올린다(upload_large_folder)."""
    from huggingface_hub import HfApi
    import dev_deploy
    api = HfApi()
    api.upload_large_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=os.path.dirname(PACK_DIR),
                            allow_patterns=["%s/%s*_context.db.xz" % (constants.JP_PACK_DIR, constants.JP_PACK_PREFIX)])
    api.upload_file(path_or_fileobj=os.path.join(PACK_DIR, "manifest.json"), path_in_repo="%s/manifest.json" % constants.JP_PACK_DIR,
                    repo_id=constants.DATA_REPO_ID, repo_type="dataset", commit_message="일본 건물 팩 매니페스트")
    api.upload_file(path_or_fileobj=dev_deploy.DATASET_CARD.encode("utf-8"), path_in_repo="README.md",
                    repo_id=constants.DATA_REPO_ID, repo_type="dataset", commit_message="데이터셋 카드: 일본 건물 팩")
    return constants.DATA_JP_MANIFEST_URL


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("catalog", "build", "roads", "upload"))
    parser.add_argument("codes", nargs="*", help="시구정촌 코드(build·roads) — 없으면 카탈로그 전부(roads는 아직 없는 팩만)")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--force", action="store_true", help="같은 연도 팩이 있어도 다시 만든다")
    args = parser.parse_args()
    if args.command == "catalog":
        catalog = get_catalog()
        years = {}
        for entry in catalog.values():
            years[entry["year"]] = years.get(entry["year"], 0) + 1
        print("PLATEAU 도시 %d곳 — 연도별 %s → %s" % (len(catalog), dict(sorted(years.items())), CATALOG_PATH))
    elif args.command == "build":
        sys.exit(1 if build(args.codes, args.workers, args.force) else 0)
    elif args.command == "roads":
        sys.exit(1 if add_roads_all(args.codes, args.workers) else 0)
    else:
        print("올림 →", upload())


if __name__ == "__main__":
    main()
