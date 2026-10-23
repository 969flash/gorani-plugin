"""스위스 건물 팩 — swisstopo swissBUILDINGS3D 3.0 Beta(OGD 이용약관, 출처 "©swisstopo")에서 바닥 윤곽·높이·종류만 뽑아 1:25k 도엽마다 팩 하나.
일본 PLATEAU 팩(dev_plateau.py)과 같은 buildings 표·매니페스트 꼴, 좌표는 경위도.

STAC 타일(도엽 하위, 연도별)의 FileGDB(MultiPatch LoD2)를 받아 GDAL `ogr2ogr`로 Floor 층(3D TIN → MULTIPOLYGON25D)을 GeoJSON으로,
`ogrinfo`로 Building_solid 속성(DACH_MAX·DACH_MIN 등)을 읽는다 — pyogrio는 MultiPatch(지오메트리 1016)를 못 읽는다.
바닥 = Floor 삼각형을 LV95 m에서 합친 외곽(non_rhino_utils.get_merged_rings), 지반 = Floor 최저 z, 높이 = GESAMTHOEHE(있으면) 또는 DACH_MAX − 지반.
Rhino 밖 python3 + GDAL(brew)·pyproj. 팩 = build/packs/ch/ch<도엽>_context.db.xz, 목록 manifest.json → HF ch/.

    python3 scripts/dev_ch.py catalog          # STAC items → data/raw/swiss/catalog.json (타일마다 bbox·gdb.zip)
    python3 scripts/dev_ch.py build [도엽 …]   # 팩 만들기(1172). 도엽이 없으면 전부, 같은 연도 묶음이 있으면 건너뛴다
    python3 scripts/dev_ch.py upload           # 외부 공개 — 사용자 확인 뒤에만
"""

import argparse
import collections
import concurrent.futures
import datetime
import io
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402
import dev_plateau  # noqa: E402 — SCHEMA_SQL·get_clean_ring·get_ring_area·_get_sha256·_write_manifest
import non_rhino_utils  # noqa: E402
from dev_nl import _download, USER_AGENT  # noqa: E402

CATALOG_PATH = os.path.join(ROOT_DIR, "data", "raw", "swiss", "catalog.json")
PACK_DIR = os.path.join(ROOT_DIR, "build", "packs", constants.CH_PACK_DIR)
PAGE_URL = "https://www.swisstopo.admin.ch/en/landscape-model-swissbuildings3d-3-0-beta"
TILE_ID = re.compile(r"swissbuildings3d_3_0_(\d{4})_(\d{4})-(\d{2})")   # 연도_도엽-하위
GDAL_BIN = "/opt/homebrew/bin"
SKIP_KINDS = ("Unterirdisches Gebaeude", "Gebaeude unsichtbar", "Mauer gross", "Mauer")   # 지하 건물·가려진 건물·담장(1192 도엽: Mauer gross 24) — 지상 건물 매스가 아니다
MERGE_TOLERANCE_M = 0.02


def get_catalog():
    # type: () -> dict
    """STAC items 전부 → {타일 id: {bbox, url}}. 전국 한 파일(swissbuildings3d_3_0_<연도>, 14 GB)은 뺀다."""
    url, items = constants.SWISS_STAC_ITEMS_URL, {}
    while url:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120) as response:
            page = json.loads(response.read().decode("utf-8"))
        for feature in page.get("features", []):
            if not TILE_ID.fullmatch(feature["id"]):
                continue
            gdb = [a["href"] for k, a in feature.get("assets", {}).items() if k.endswith(".gdb.zip")]
            if gdb:
                items[feature["id"]] = {"bbox": feature["bbox"], "url": gdb[0]}
        url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=1, sort_keys=True)
    return items


def get_sheets(catalog):
    # type: (dict) -> dict
    """{도엽: {하위 타일: (연도, 타일 id)}} — 하위 타일마다 최신 연도만."""
    sheets = {}
    for tile_id in catalog:
        year, sheet, sub = TILE_ID.fullmatch(tile_id).groups()
        current = sheets.setdefault(sheet, {}).get(sub)
        if current is None or current[0] < year:
            sheets[sheet][sub] = (year, tile_id)
    return sheets


# ── 타일 읽기 ───────────────────────────────────────────

def _ogr(args):
    # type: (list) -> str
    env = dict(os.environ, PATH=GDAL_BIN + os.pathsep + os.environ.get("PATH", ""))
    return subprocess.run(args, check=True, capture_output=True, text=True, env=env).stdout


def read_tile(gdb_path):
    # type: (str) -> dict
    """FileGDB 하나 → {UUID: {kind, use, egid, ground, roof_max, total_height, triangles[[(x, y)]]}} (LV95 m)."""
    layers = _ogr(["ogrinfo", "-so", "-q", gdb_path])
    if "Layer: Floor " not in layers:   # Roof·Roof_solid만 있는 타일(1156-24 2022) — 바닥이 없으면 건물도 없다
        return {}
    work = tempfile.mkdtemp(prefix="swiss_")
    try:
        floor_path = os.path.join(work, "floor.json")
        _ogr(["ogr2ogr", "-f", "GeoJSON", "-nlt", "MULTIPOLYGON25D", "-skipfailures", floor_path, gdb_path, "Floor"])
        with open(floor_path, encoding="utf-8") as f:
            floor = json.load(f)
        attrs = _ogr(["ogrinfo", "-al", "-geom=NO", "-q", gdb_path, "Building_solid"])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    solids = {}
    for block in attrs.split("OGRFeature(Building_solid):")[1:]:
        values = dict(re.findall(r"\n\s*([A-Z_]+) \([^)]*\) = (.*)", block))
        uuid = values.get("UUID", "").strip()
        if uuid:
            solids[uuid] = values
    buildings = {}
    for feature in floor.get("features", []):
        p = feature.get("properties") or {}
        uuid = p.get("UUID") or ""
        geometry = feature.get("geometry") or {}
        if not uuid or geometry.get("type") != "MultiPolygon":
            continue
        zs = [c[2] for part in geometry["coordinates"] for ring in part for c in ring if len(c) > 2]
        solid = solids.get(uuid, {})
        buildings[uuid] = {
            "kind": p.get("OBJEKTART") or "", "use": p.get("GEBAEUDE_NUTZUNG") or "", "egid": p.get("EGID"),
            "ground": min(zs) if zs else _get_number(p.get("GELAENDEPUNKT")), "total_height": _get_number(p.get("GESAMTHOEHE")),
            "roof_max": _get_number(solid.get("DACH_MAX")), "roof_min": _get_number(solid.get("DACH_MIN")),
            "triangles": [[(c[0], c[1]) for c in part[0]] for part in geometry["coordinates"] if part and len(part[0]) >= 4],
        }
    return buildings


def _get_number(value):
    # type: (object) -> float
    try:
        return None if value in (None, "", "(null)") else float(value)
    except (TypeError, ValueError):
        return None


def get_height(building):
    # type: (dict) -> tuple
    """GESAMTHOEHE(실측 전체 높이) → DACH_MAX − 지반(Floor 최저 z) → 기본값."""
    low, high = constants.SWISS_HEIGHT_RANGE
    total = building.get("total_height")
    if total is not None and low <= total <= high:
        return round(total, 2), "swisstopo_height", "B"
    roof, ground = building.get("roof_max"), building.get("ground")
    if roof is not None and ground is not None and low <= roof - ground <= high:
        return round(roof - ground, 2), "swisstopo_roof", "B"
    return constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"


def get_footprint(triangles, transformer):
    # type: (list, object) -> dict
    """Floor 삼각형(LV95 m) → 공유 변을 지운 외곽 → 경위도 GeoJSON (Multi)Polygon. 합치지 못하면 None."""
    polygons = [[[(float(x), float(y)) for x, y in tri[:-1]] if tri[0] == tri[-1] else [(float(x), float(y)) for x, y in tri]] for tri in triangles]
    polygons = [p for p in polygons if len(p[0]) >= 3]
    if not polygons:
        return None
    outers, holes = non_rhino_utils.get_merged_rings(polygons, MERGE_TOLERANCE_M)
    if not outers:
        return None
    parts = []
    for outer in outers:
        inner = [h for h in holes if non_rhino_utils.is_point_in_ring(h[0][0], h[0][1], outer)]
        rings = []
        for ring in [outer] + inner:
            xs, ys = transformer.transform([p[0] for p in ring], [p[1] for p in ring])
            clean = dev_plateau.get_clean_ring(list(zip(xs, ys)))
            if clean:
                rings.append(clean)
        if rings:
            parts.append(rings)
    if not parts:
        return None
    return {"type": "Polygon", "coordinates": parts[0]} if len(parts) == 1 else {"type": "MultiPolygon", "coordinates": parts}


def get_row(uuid, building, building_id, transformer):
    # type: (str, dict, int, object) -> tuple
    """건물 dict → buildings 행(dev_plateau.SCHEMA_SQL 칸 순서). 지하 건물·바닥 없음은 None."""
    if building["kind"] in SKIP_KINDS:
        return None
    geometry = get_footprint(building["triangles"], transformer)
    if geometry is None:
        return None
    height, height_src, grade = get_height(building)
    rings = geometry["coordinates"] if geometry["type"] == "Polygon" else [r for polygon in geometry["coordinates"] for r in polygon]
    xs = [p[0] for ring in rings for p in ring]
    ys = [p[1] for ring in rings for p in ring]
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return (building_id, "swisstopo:%s" % uuid.strip("{}").lower(), None, "", None, 0, 0, "", height, height_src, grade, None, None, "active",
            None, building["kind"] or None, building["use"] or None, round(sum(dev_plateau.get_ring_area(polygon[0]) for polygon in polygons), 2), None,
            json.dumps(geometry, separators=(",", ":")), 4326, "swisstopo", None, min(xs), max(xs), min(ys), max(ys))


# ── 팩 ──────────────────────────────────────────────────

def build_pack(sheet, tiles, pack_no, pack_dir=PACK_DIR):
    # type: (str, dict, int, str) -> dict
    """도엽 하나(하위 타일 dict {sub: (연도, 타일 id)}) → ch<도엽>_context.db.xz. 타일 겹침은 UUID로 한 번만."""
    import pyproj
    started = time.time()
    transformer = pyproj.Transformer.from_crs("EPSG:2056", "EPSG:4326", always_xy=True)
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    name = "%s%s_context.db" % (constants.CH_PACK_PREFIX, sheet)
    path = os.path.join(pack_dir, name)
    for stale in (path, path + ".xz"):
        if os.path.exists(stale):
            os.remove(stale)
    rows, seen, years, stats = [], set(), set(), {"tiles": 0, "skipped": 0, "grades": {}}
    for sub in sorted(tiles):
        year, tile_id = tiles[sub]
        work = tempfile.mkdtemp(prefix="swiss_")
        try:
            data = _download(catalog[tile_id]["url"])
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                archive.extractall(work)
            gdbs = [os.path.join(root, d) for root, dirs, _files in os.walk(work) for d in dirs if d.lower().endswith(".gdb")]
            if not gdbs:
                continue
            buildings = read_tile(gdbs[0])
        finally:
            shutil.rmtree(work, ignore_errors=True)
        stats["tiles"] += 1
        years.add(int(year))
        for uuid, building in buildings.items():
            if uuid in seen:
                continue
            seen.add(uuid)
            row = get_row(uuid, building, pack_no * 10 ** 7 + len(seen), transformer)
            if row is None:
                stats["skipped"] += 1
                continue
            rows.append(row)
            stats["grades"][row[10]] = stats["grades"].get(row[10], 0) + 1
    if not rows:
        return None
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = MEMORY")
    connection.execute("PRAGMA synchronous = OFF")
    connection.executescript(dev_plateau.SCHEMA_SQL)
    connection.executemany("INSERT INTO buildings VALUES (%s)" % ",".join("?" * 27), rows)
    year = max(years)
    connection.execute("INSERT INTO data_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        "swisstopo", "swissBUILDINGS3D 3.0 Beta %s (%d)" % (sheet, year), PAGE_URL, "%d-12-31" % year,
        datetime.datetime.now().isoformat(timespec="seconds"), "EPSG:2056 → 경위도(소수 %d자리)" % constants.PLATEAU_DIGITS, constants.SWISS_LICENSE,
        "Source: ©swisstopo, swissBUILDINGS3D 3.0 Beta (%d), processed by Gorani — footprint from Floor, height = DACH_MAX − ground" % year))
    connection.execute("CREATE INDEX idx_buildings_bbox ON buildings(min_x, max_x, min_y, max_y)")
    bounds = connection.execute("SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM buildings").fetchone()
    connection.execute("PRAGMA user_version = %d" % constants.CONTEXT_DATABASE_SCHEMA_VERSION)
    connection.commit()
    connection.close()
    size, sha256 = os.path.getsize(path), dev_plateau._get_sha256(path)
    subprocess.run(["xz", "-6", "-T1", "-f", path], check=True)
    stats["seconds"] = round(time.time() - started)
    return {"name": name, "label": "%s Gebäude" % sheet, "url": name + ".xz", "size": size, "sha256": sha256,
            "bounds": [round(v, constants.PLATEAU_DIGITS) for v in bounds], "xz_size": os.path.getsize(path + ".xz"),
            "year": year, "tiles": sorted(tiles[sub][1] for sub in tiles), "buildings": len(rows), "stats": stats}


def build(codes=None, workers=4, force=False):
    # type: (list, int, bool) -> list
    """도엽(codes만, 없으면 전부)을 팩으로. 같은 타일 묶음이면 건너뛴다(force면 다시). 실패한 도엽 목록을 돌려준다."""
    if not os.path.exists(CATALOG_PATH):
        get_catalog()
    with open(CATALOG_PATH, encoding="utf-8") as f:
        catalog = json.load(f)
    sheets = get_sheets(catalog)
    os.makedirs(PACK_DIR, exist_ok=True)
    manifest_path = os.path.join(PACK_DIR, "manifest.json")
    packs = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
    numbers = {sheet: i + 1 for i, sheet in enumerate(sorted(sheets))}
    todo = []
    for sheet in codes or sorted(sheets):
        name = "%s%s_context.db" % (constants.CH_PACK_PREFIX, sheet)
        done = packs.get(name)
        want = sorted(sheets[sheet][sub][1] for sub in sheets[sheet])
        if not force and done and done.get("tiles") == want and os.path.exists(os.path.join(PACK_DIR, done["url"])):
            continue
        todo.append(sheet)
    print("swissBUILDINGS3D 팩 %d곳 만들기 (작업 %d개)" % (len(todo), workers), flush=True)
    failed = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(build_pack, sheet, sheets[sheet], numbers[sheet]): sheet for sheet in todo}
        for future in concurrent.futures.as_completed(futures):
            sheet = futures[future]
            try:
                pack = future.result()
            except Exception as exc:
                failed.append(sheet)
                print("  %s 실패: %r" % (sheet, exc), flush=True)
                continue
            if pack is None:
                print("  %s: 건물 없음" % sheet, flush=True)
                continue
            packs[pack["name"]] = pack
            dev_plateau._write_manifest(packs, PACK_DIR)
            stats = pack["stats"]
            print("  %s %d: %s동(타일 %d) · B %.1f %% · %d s · xz %.1f MB" % (sheet, pack["year"], format(pack["buildings"], ","), stats["tiles"],
                                                                         100.0 * stats["grades"].get("B", 0) / pack["buildings"], stats["seconds"], pack["xz_size"] / 1e6), flush=True)
    total = sum(p["xz_size"] for p in packs.values())
    print("팩 %d개 · 압축 %.2f GB · 실패 %d %s" % (len(packs), total / 1e9, len(failed), " ".join(sorted(failed))), flush=True)
    return failed


def upload():
    # type: () -> str
    """build/packs/ch/의 팩을 Hugging Face 데이터셋 ch/에 올린 뒤 매니페스트를 올린다. 외부 공개 — 사용자 확인 뒤에만."""
    from huggingface_hub import HfApi
    api = HfApi()
    api.upload_large_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=os.path.dirname(os.path.realpath(PACK_DIR)),
                            allow_patterns=["%s/%s*_context.db.xz" % (constants.CH_PACK_DIR, constants.CH_PACK_PREFIX)])
    api.upload_file(path_or_fileobj=os.path.join(PACK_DIR, "manifest.json"), path_in_repo="%s/manifest.json" % constants.CH_PACK_DIR,
                    repo_id=constants.DATA_REPO_ID, repo_type="dataset", commit_message="스위스 건물 팩 매니페스트")
    return constants.COUNTRY_PACKS["ch"]["manifest"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("catalog", "build", "upload"))
    parser.add_argument("codes", nargs="*", help="1:25k 도엽(build) — 1172. 없으면 전부")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "catalog":
        catalog = get_catalog()
        sheets = get_sheets(catalog)
        print("swissBUILDINGS3D 타일 %d · 도엽 %d · 하위 타일 %d → %s" % (len(catalog), len(sheets), sum(len(v) for v in sheets.values()), CATALOG_PATH))
    elif args.command == "build":
        sys.exit(1 if build(args.codes, args.workers, args.force) else 0)
    else:
        print("올림 →", upload())


if __name__ == "__main__":
    main()
