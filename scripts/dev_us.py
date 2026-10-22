"""미국 건물 팩 — Overture Maps buildings(ODbL — Microsoft ML Buildings·OpenStreetMap·Esri Community Maps 합본)에서 바닥 윤곽·높이·층수·용도만 뽑아
카운티(Census FIPS 5자리)마다 팩 하나. 일본 PLATEAU 팩(dev_plateau.py)과 같은 buildings 표·매니페스트 꼴, 좌표는 경위도.

S3 GeoParquet(익명)을 DuckDB httpfs로 주 상자만 읽어 로컬 parquet에 두고(fetch), 카운티 경계(Census cb_2024_us_county_500k, 300 m 넓혀서)에
건물 중심점이 든 것을 카운티 팩으로 쓴다(build). 높이 = Overture height(대부분 Microsoft ML 추정, B) → 층수 × 층고(C) → 기본값(D).
Rhino 밖 python3 + duckdb·pyogrio·shapely. 팩 = build/packs/us/us<FIPS>_context.db.xz, 목록 manifest.json → HF us/.

    python3 scripts/dev_us.py catalog                 # Census 카운티 경계 받기·요약(주별 카운티 수)
    python3 scripts/dev_us.py fetch CA TX …           # 주 상자의 Overture 건물 → data/raw/us/overture_<판>/<주>.parquet (없으면 전부)
    python3 scripts/dev_us.py build [06037 …] [--state CA]   # 카운티 팩. 코드가 없으면 받아 둔 주의 카운티 전부. 같은 판이면 건너뛴다
    python3 scripts/dev_us.py upload                  # 외부 공개 — 사용자 확인 뒤에만
"""

import argparse
import concurrent.futures
import datetime
import json
import os
import sqlite3
import subprocess
import sys
import time
import urllib.request

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402
import dev_plateau  # noqa: E402 — SCHEMA_SQL·get_clean_ring·get_ring_area·_get_sha256·_write_manifest

RAW_DIR = os.path.join(ROOT_DIR, "data", "raw", "us")
COUNTY_ZIP = os.path.join(RAW_DIR, os.path.basename(constants.CENSUS_COUNTY_URL))
STATE_DIR = os.path.join(RAW_DIR, "overture_%s" % constants.OVERTURE_RELEASE)
PACK_DIR = os.path.join(ROOT_DIR, "build", "packs", constants.US_PACK_DIR)
SELECT_SQL = """
SELECT id, ST_AsGeoJSON(geometry) AS geojson, ST_X(ST_Centroid(geometry)) AS cx, ST_Y(ST_Centroid(geometry)) AS cy,
       subtype, class, height, num_floors, num_floors_underground, names.primary AS name, sources[1].dataset AS dataset, is_underground
FROM read_parquet('%s', hive_partitioning=1)
WHERE bbox.xmin > %.4f AND bbox.xmax < %.4f AND bbox.ymin > %.4f AND bbox.ymax < %.4f
"""   # bbox 칸이 행 그룹 통계라 주 상자 밖 파일은 읽지 않는다
DATASET_FLAGS = {"Microsoft ML Buildings": "msft", "OpenStreetMap": "osm", "Esri Community Maps": "esri", "Google Open Buildings": "google"}


_CONNECTION = None


def _connect():
    # type: () -> object
    """프로세스마다 DuckDB 연결 하나를 돌려쓴다 — S3 parquet 메타데이터(수백 파일 footer) 읽기가 연결마다 약 900 s라(2026-10-23 실측: 건물 2만 동인
    아메리칸사모아도 987 s) 주를 바꿔도 다시 읽지 않게 parquet_metadata_cache를 켠다. 메모리는 6 GB로 제한(두 프로세스 병렬)."""
    global _CONNECTION
    if _CONNECTION is None:
        import duckdb
        _CONNECTION = duckdb.connect()
        _CONNECTION.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2'; "
                            "SET parquet_metadata_cache=true; SET memory_limit='6GB';")
    return _CONNECTION


# ── 카운티 ──────────────────────────────────────────────

def get_counties(states=None):
    # type: (list) -> list
    """Census 카운티 경계 → [{geoid, name, state, bounds(서, 남, 동, 북), geometry(shapely, 경위도)}] GEOID 순. states(USPS 2자)를 주면 그 주만."""
    import pyogrio
    if not os.path.exists(COUNTY_ZIP):
        os.makedirs(RAW_DIR, exist_ok=True)
        urllib.request.urlretrieve(constants.CENSUS_COUNTY_URL, COUNTY_ZIP)
    frame = pyogrio.read_dataframe("/vsizip/" + COUNTY_ZIP).to_crs("EPSG:4326")
    if states:
        frame = frame[frame["STUSPS"].isin(states)]
    counties = []
    for row in frame.sort_values("GEOID").itertuples():
        counties.append({"geoid": row.GEOID, "name": row.NAMELSAD, "state": row.STUSPS, "bounds": tuple(round(v, 4) for v in row.geometry.bounds),
                         "geometry": row.geometry})
    return counties


def get_state_bounds(counties):
    # type: (list) -> tuple
    """카운티 목록의 바깥 상자(서, 남, 동, 북) — 0.01° 여유."""
    return (min(c["bounds"][0] for c in counties) - 0.01, min(c["bounds"][1] for c in counties) - 0.01,
            max(c["bounds"][2] for c in counties) + 0.01, max(c["bounds"][3] for c in counties) + 0.01)


# ── 받기 ────────────────────────────────────────────────

def fetch_state(state, counties):
    # type: (str, list) -> str
    """주 하나의 Overture 건물을 S3에서 읽어 STATE_DIR/<주>.parquet에 둔다(있으면 그대로). 알래스카는 날짜변경선 너머(알류샨 서쪽)를 뺀다."""
    os.makedirs(STATE_DIR, exist_ok=True)
    path = os.path.join(STATE_DIR, "%s.parquet" % state)
    if os.path.exists(path):
        return path
    if os.path.exists(path + ".tmp"):   # 죽은 실행이 남긴 조각
        os.remove(path + ".tmp")
    west, south, east, north = get_state_bounds(counties)
    if state == "AK":   # 알류샨 서쪽(애투섬 등)이 경도 +179°라 상자가 지구 북반구 51~72° 띠 전체가 된다(2026-10-23: 2시간 넘게 받다 죽임) — 동쪽을 -129°로 자른다
        west, east = max(west, -180.0), min(east, -129.0)
    connection = _connect()
    started = time.time()
    connection.execute("COPY (%s) TO '%s' (FORMAT PARQUET, COMPRESSION ZSTD)" % (SELECT_SQL % (constants.OVERTURE_S3_URL, west, east, south, north), path + ".tmp"))
    os.replace(path + ".tmp", path)
    count = connection.execute("SELECT count(*), count(height) FROM read_parquet('%s')" % path).fetchone()
    print("  %s: %s동(height %s) · %d s · %.0f MB" % (state, format(count[0], ","), format(count[1], ","), time.time() - started, os.path.getsize(path) / 1e6), flush=True)
    return path


# ── 행 ──────────────────────────────────────────────────

def get_height(height, floors):
    # type: (float, int) -> tuple
    """Overture height(m, 대부분 Microsoft ML 추정 — B) → 층수 × 층고(C) → 기본값(D)."""
    low, high = constants.OVERTURE_HEIGHT_RANGE
    if height is not None and low <= height <= high:
        return round(float(height), 2), "overture_height", "B"
    levels = int(floors) if floors else 0
    if levels > 0:
        base, per = constants.FLOOR_HEIGHT_DEFAULT
        return round(base + per * levels, 2), "overture_levels", "C"
    return constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"


def get_use(subtype, class_name):
    # type: (str, str) -> str
    """Overture subtype·class → 국내 건축물용도 대분류(시트 색). 모르면 ""."""
    return constants.OVERTURE_USE_CLASS.get(class_name or "") or constants.OVERTURE_USE_SUBTYPE.get(subtype or "", "")


def get_polygons(geojson):
    # type: (str) -> list
    """Overture 건물 GeoJSON → [[외곽, 구멍 …]] (소수 6자리 닫힌 링). 외곽이 없으면 []."""
    geometry = json.loads(geojson)
    parts = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"] if geometry["type"] == "MultiPolygon" else []
    polygons = []
    for part in parts:
        rings = [dev_plateau.get_clean_ring(ring) for ring in part]
        if rings and rings[0]:
            polygons.append([rings[0]] + [ring for ring in rings[1:] if ring])
    return polygons


def get_row(record, building_id):
    # type: (tuple, int) -> tuple
    """fetch한 parquet 한 행(SELECT_SQL 칸 순서) → buildings 행(dev_plateau.SCHEMA_SQL 칸 순서). 지하·윤곽 없음은 None."""
    (overture_id, geojson, _cx, _cy, subtype, class_name, height, floors, floors_below, name, dataset, underground) = record
    if underground:
        return None
    polygons = get_polygons(geojson)
    if not polygons:
        return None
    height, height_src, grade = get_height(height, floors)
    geometry = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
    xs = [p[0] for polygon in polygons for p in polygon[0]]
    ys = [p[1] for polygon in polygons for p in polygon[0]]
    levels = int(floors) if floors else 0
    return (building_id, "overture:%s" % overture_id, None, get_use(subtype, class_name), None, levels, int(floors_below or 0), "overture" if levels else "",
            height, height_src, grade, DATASET_FLAGS.get(dataset or "", "other"), None, "active", name or None, subtype or None, class_name or None,
            round(sum(dev_plateau.get_ring_area(polygon[0]) for polygon in polygons), 2), None,
            json.dumps(geometry, separators=(",", ":")), 4326, "overture", None, min(xs), max(xs), min(ys), max(ys))


# ── 팩 ──────────────────────────────────────────────────

def build_pack(county, pack_dir=PACK_DIR):
    # type: (dict, str) -> dict
    """카운티 하나 → us<GEOID>_context.db.xz. 받아 둔 주 parquet에서 중심점이 (넓힌) 카운티 안인 건물."""
    started = time.time()
    state_path = os.path.join(STATE_DIR, "%s.parquet" % county["state"])
    name = "%s%s_context.db" % (constants.US_PACK_PREFIX, county["geoid"])
    path = os.path.join(pack_dir, name)
    for stale in (path, path + ".xz"):
        if os.path.exists(stale):
            os.remove(stale)
    area = county["geometry"].buffer(constants.US_COUNTY_BUFFER_DEG)
    west, south, east, north = area.bounds
    cursor = _connect().cursor()
    cursor.execute(
        "SELECT * FROM read_parquet(?) WHERE cx BETWEEN ? AND ? AND cy BETWEEN ? AND ? AND ST_Within(ST_Point(cx, cy), ST_GeomFromText(?))",
        [state_path, west, east, south, north, area.wkt])
    count, stats, pack_no = 0, {"skipped": 0, "grades": {}, "flags": {}}, int(county["geoid"])
    os.makedirs(pack_dir, exist_ok=True)
    pack = sqlite3.connect(path)   # 배치마다 바로 쓴다 — 로스앤젤레스 카운티 300만 동을 메모리에 다 들지 않게
    pack.execute("PRAGMA journal_mode = MEMORY")
    pack.execute("PRAGMA synchronous = OFF")
    pack.executescript(dev_plateau.SCHEMA_SQL)
    while True:
        batch = cursor.fetchmany(20000)
        if not batch:
            break
        rows = []
        for record in batch:
            row = get_row(record, pack_no * 10 ** 7 + count + len(rows) + 1)
            if row is None:
                stats["skipped"] += 1
                continue
            rows.append(row)
            stats["grades"][row[10]] = stats["grades"].get(row[10], 0) + 1
            stats["flags"][row[11]] = stats["flags"].get(row[11], 0) + 1
        pack.executemany("INSERT INTO buildings VALUES (%s)" % ",".join("?" * 27), rows)
        count += len(rows)
    cursor.close()
    if not count:
        pack.close()
        os.remove(path)
        return None
    release_date = constants.OVERTURE_RELEASE.split(".")[0]
    connection = pack
    connection.execute("INSERT INTO data_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        "overture", "Overture Maps buildings %s — %s, %s" % (constants.OVERTURE_RELEASE, county["name"], county["state"]), constants.OVERTURE_PAGE_URL, release_date,
        datetime.datetime.now().isoformat(timespec="seconds"), "EPSG:4326(소수 %d자리)" % constants.PLATEAU_DIGITS, constants.OVERTURE_LICENSE,
        "Source: Overture Maps Foundation (buildings, release %s, ODbL 1.0) — © OpenStreetMap contributors, Microsoft; processed by Gorani. Heights mostly ML estimates" % constants.OVERTURE_RELEASE))
    connection.execute("CREATE INDEX idx_buildings_bbox ON buildings(min_x, max_x, min_y, max_y)")
    bounds = connection.execute("SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM buildings").fetchone()
    connection.execute("PRAGMA user_version = %d" % constants.CONTEXT_DATABASE_SCHEMA_VERSION)
    connection.commit()
    connection.close()
    size, sha256 = os.path.getsize(path), dev_plateau._get_sha256(path)
    subprocess.run(["xz", "-6", "-T1", "-f", path], check=True)
    stats["seconds"] = round(time.time() - started)
    return {"name": name, "label": "%s, %s" % (county["name"], county["state"]), "url": name + ".xz", "size": size, "sha256": sha256,
            "bounds": [round(v, constants.PLATEAU_DIGITS) for v in bounds], "xz_size": os.path.getsize(path + ".xz"),
            "release": constants.OVERTURE_RELEASE, "buildings": count, "stats": stats}


def build(codes=None, states=None, workers=4, force=False):
    # type: (list, list, int, bool) -> list
    """카운티(codes만, 없으면 states 또는 받아 둔 주의 전부)를 팩으로. 같은 Overture 판이면 건너뛴다(force면 다시). 실패한 카운티 목록을 돌려준다."""
    fetched = sorted(name[:-8] for name in os.listdir(STATE_DIR) if name.endswith(".parquet")) if os.path.isdir(STATE_DIR) else []
    counties = get_counties(states or None)
    if codes:
        counties = [c for c in counties if c["geoid"] in set(codes)]
    counties = [c for c in counties if c["state"] in fetched or (states and c["state"] in states)]
    for state in sorted({c["state"] for c in counties} - set(fetched)):   # 안 받은 주는 먼저 받는다
        fetch_state(state, [c for c in get_counties([state])])
    os.makedirs(PACK_DIR, exist_ok=True)
    manifest_path = os.path.join(PACK_DIR, "manifest.json")
    packs = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
    todo = []
    for county in counties:
        done = packs.get("%s%s_context.db" % (constants.US_PACK_PREFIX, county["geoid"]))
        if not force and done and done.get("release") == constants.OVERTURE_RELEASE and os.path.exists(os.path.join(PACK_DIR, done["url"])):
            continue
        todo.append(county)
    print("Overture 미국 카운티 팩 %d곳 만들기 (작업 %d개)" % (len(todo), workers), flush=True)
    failed = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(build_pack, county): county for county in todo}
        for future in concurrent.futures.as_completed(futures):
            county = futures[future]
            try:
                pack = future.result()
            except Exception as exc:
                failed.append(county["geoid"])
                print("  %s %s 실패: %r" % (county["geoid"], county["name"], exc), flush=True)
                continue
            if pack is None:
                print("  %s %s: 건물 없음" % (county["geoid"], county["name"]), flush=True)
                continue
            packs[pack["name"]] = pack
            dev_plateau._write_manifest(packs, PACK_DIR)
            stats = pack["stats"]
            print("  %s %s: %s동 · B %.1f %% · %d s · xz %.1f MB" % (county["geoid"], pack["label"], format(pack["buildings"], ","),
                                                                100.0 * stats["grades"].get("B", 0) / pack["buildings"], stats["seconds"], pack["xz_size"] / 1e6), flush=True)
    total = sum(p["xz_size"] for p in packs.values())
    print("팩 %d개 · 압축 %.2f GB · 실패 %d %s" % (len(packs), total / 1e9, len(failed), " ".join(sorted(failed))), flush=True)
    return failed


def upload():
    # type: () -> str
    """build/packs/us/의 팩을 Hugging Face 데이터셋 us/에 올린 뒤 매니페스트를 올린다. 외부 공개 — 사용자 확인 뒤에만."""
    from huggingface_hub import HfApi
    api = HfApi()
    api.upload_large_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=os.path.dirname(os.path.realpath(PACK_DIR)),
                            allow_patterns=["%s/%s*_context.db.xz" % (constants.US_PACK_DIR, constants.US_PACK_PREFIX)])
    api.upload_file(path_or_fileobj=os.path.join(PACK_DIR, "manifest.json"), path_in_repo="%s/manifest.json" % constants.US_PACK_DIR,
                    repo_id=constants.DATA_REPO_ID, repo_type="dataset", commit_message="미국 건물 팩 매니페스트")
    import dev_deploy   # 데이터셋 카드(README.md) — 나라별 출처·라이선스 절은 dev_deploy.DATASET_CARD 하나에 있다
    api.upload_file(path_or_fileobj=dev_deploy.DATASET_CARD.encode("utf-8"), path_in_repo="README.md",
                    repo_id=constants.DATA_REPO_ID, repo_type="dataset", commit_message="데이터셋 카드: 나라별 건물 팩 출처·라이선스")
    return "https://huggingface.co/datasets/%s/resolve/main/%s/manifest.json" % (constants.DATA_REPO_ID, constants.US_PACK_DIR)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("catalog", "fetch", "build", "upload"))
    parser.add_argument("codes", nargs="*", help="fetch: 주(USPS 2자, 없으면 전부) · build: 카운티 FIPS 5자리(없으면 받아 둔 주 전부)")
    parser.add_argument("--state", action="append", help="build: 이 주의 카운티만(여러 번 가능)")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "catalog":
        counties = get_counties()
        by_state = {}
        for county in counties:
            by_state[county["state"]] = by_state.get(county["state"], 0) + 1
        print("카운티 %d개 · 주·준주 %d개 → %s" % (len(counties), len(by_state), COUNTY_ZIP))
        print(" ".join("%s %d" % item for item in sorted(by_state.items())))
    elif args.command == "fetch":
        counties = get_counties()
        states = args.codes or sorted({c["state"] for c in counties})
        for state in states:
            fetch_state(state, [c for c in counties if c["state"] == state])
    elif args.command == "build":
        sys.exit(1 if build(args.codes, args.state, args.workers, args.force) else 0)
    else:
        print("올림 →", upload())


if __name__ == "__main__":
    main()
