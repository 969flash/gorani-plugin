"""네덜란드 건물 팩 — Kadaster 3D Basisvoorziening '2D 건물 + 높이 통계'(hoogtestatistieken_gebouwen, CC BY 4.0)에서 바닥 윤곽·높이만 뽑아
도엽(bladnr, 1:10k)마다 팩 하나를 만든다. 일본 PLATEAU 팩(dev_plateau.py)과 같은 buildings 표·매니페스트 꼴, 좌표는 경위도.

Rhino 밖 python3 + pyogrio(GeoPackage 읽기)·pyproj(EPSG:28992 → 4326). 팩 = build/packs/nl/nl<도엽>_context.db.xz,
목록 = 같은 폴더 manifest.json → Hugging Face 데이터셋(constants.DATA_REPO_ID)의 nl/. 근거 docs/research/country_buildings.md.

    python3 scripts/dev_nl.py catalog          # PDOK items API → data/raw/pdok/catalog.json (도엽마다 최신 연도 zip)
    python3 scripts/dev_nl.py build [도엽 …]   # 팩 만들기. 도엽이 없으면 카탈로그 전부, 같은 연도 팩이 있으면 건너뛴다
    python3 scripts/dev_nl.py upload           # 팩·매니페스트·데이터셋 카드를 올린다 — 외부 공개라 사용자 확인 뒤에만
"""

import argparse
import concurrent.futures
import datetime
import io
import json
import os
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

CATALOG_PATH = os.path.join(ROOT_DIR, "data", "raw", "pdok", "catalog.json")
PACK_DIR = os.path.join(ROOT_DIR, "build", "packs", constants.NL_PACK_DIR)
PAGE_URL = "https://www.pdok.nl/introductie/-/article/3d-basisvoorziening"
COLUMNS = ("identificatie", "status", "oorspronkelijkbouwjaar", "rf_h_ground", "rf_h_roof_50p", "rf_h_roof_70p", "rf_h_roof_max", "rf_roof_type")
# 2025년판 칸 이름. 2019년판은 h_maaiveld·dd_h_dak_50p·pandstatus·bouwjaar — 카탈로그가 최신 연도만 고르므로 쓰지 않는다
USER_AGENT = "Gorani dev_nl (https://969flash.github.io/gorani/)"


def _download(url, retries=6):
    # type: (str, int) -> bytes
    """zip 통째로 받기. PDOK 서버가 10 MB쯤에서 연결을 끊는다(IncompleteRead, 2026-10-22) — 받은 데서 Range로 이어 받는다."""
    import http.client
    data, total = b"", None
    for attempt in range(retries):
        headers = {"User-Agent": USER_AGENT}
        if data:
            headers["Range"] = "bytes=%d-" % len(data)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=300) as response:
                if total is None:
                    total = int(response.headers.get("Content-Length") or 0)
                if data and response.status != 206:   # Range를 못 받으면 처음부터
                    data = b""
                data += response.read()
        except http.client.IncompleteRead as exc:
            data += exc.partial
        except OSError:
            if attempt == retries - 1:
                raise
        if total and len(data) >= total:
            return data
        if not total and data:
            return data
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("받다 끊김: %s (%d/%s bytes)" % (url, len(data), total))


def _get_json(url):
    # type: (str) -> dict
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": USER_AGENT}), timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def get_catalog():
    # type: () -> dict
    """PDOK OGC API items(도엽 × 연도) → {도엽: {year, url, size, bbox}} 도엽마다 최신 연도. data/raw/pdok/catalog.json에 저장."""
    url, catalog = constants.PDOK_ITEMS_URL, {}
    while url:
        page = _get_json(url)
        for feature in page.get("features", []):
            p = feature["properties"]
            bladnr = p["bladnr"].lower()
            if bladnr not in catalog or catalog[bladnr]["year"] < p["jaargang_luchtfoto"]:
                xs = [c[0] for ring in feature["geometry"]["coordinates"] for c in ring]
                ys = [c[1] for ring in feature["geometry"]["coordinates"] for c in ring]
                catalog[bladnr] = {"year": p["jaargang_luchtfoto"], "url": p["download_link"], "size": p["download_size_bytes"],
                                   "bbox": [round(min(xs), 6), round(min(ys), 6), round(max(xs), 6), round(max(ys), 6)]}
        url = next((link["href"] for link in page.get("links", []) if link.get("rel") == "next"), None)
    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1, sort_keys=True)
    return catalog


# ── 행 만들기 ───────────────────────────────────────────

def get_height(ground, roof_50p, roof_70p, roof_max):
    # type: (float, float, float, float) -> tuple
    """지붕 표고 − 지반 표고 → (높이 m, height_src, grade). 50 % 지붕 높이(B, 항공 lidar 실측)가 없으면 70 % → 최고 → 기본값(D)."""
    low, high = constants.PDOK_HEIGHT_RANGE
    for roof in (roof_50p, roof_70p, roof_max):
        if ground is not None and roof is not None and low <= roof - ground <= high:
            return round(roof - ground, 2), "pdok_height", "B"
    return constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"


def get_rows(gpkg_path, pack_no, transformer=None):
    # type: (str, int, object) -> list
    """GeoPackage(EPSG:28992) → buildings 행 목록(dev_plateau.SCHEMA_SQL 칸 순서, 경위도). 철거·허가 단계(PDOK_SKIP_STATUS)는 뺀다.
    building_id = 팩 번호 × 10⁷ + 순번(팩끼리 겹치지 않는다 — 번호는 카탈로그 정렬 순)."""
    import pyogrio
    import pyproj
    import shapely
    transformer = transformer or pyproj.Transformer.from_crs("EPSG:28992", "EPSG:4326", always_xy=True)
    info = pyogrio.read_info(gpkg_path)
    columns = [c for c in COLUMNS if c in list(info["fields"])]
    meta, _index, geoms, values = pyogrio.raw.read(gpkg_path, columns=columns, return_fids=False)
    col = {name: values[i] for i, name in enumerate(meta["fields"])}
    rows, n, seen = [], 0, {}
    for k, wkb in enumerate(geoms):
        status = col["status"][k] if "status" in col else ""
        if status in constants.PDOK_SKIP_STATUS or wkb is None:
            continue
        geometry = shapely.from_wkb(wkb)
        parts = list(geometry.geoms) if geometry.geom_type == "MultiPolygon" else [geometry]
        polygons = []
        for part in parts:
            rings = []
            for ring in [part.exterior] + list(part.interiors):
                xs, ys = transformer.transform([c[0] for c in ring.coords], [c[1] for c in ring.coords])
                clean = dev_plateau.get_clean_ring(list(zip(xs, ys)))
                if clean:
                    rings.append(clean)
            if rings:
                polygons.append(rings)
        if not polygons:
            continue
        height, height_src, grade = get_height(col["rf_h_ground"][k], col["rf_h_roof_50p"][k], col.get("rf_h_roof_70p", [None] * len(geoms))[k],
                                               col.get("rf_h_roof_max", [None] * len(geoms))[k])
        year = col["oorspronkelijkbouwjaar"][k] if "oorspronkelijkbouwjaar" in col else None
        use_apr_day = "%04d-01-01" % int(year) if year and constants.PDOK_YEAR_MIN <= int(year) < 2100 else None   # 건축 연도 → 건축물 연한 도면
        xs = [p[0] for polygon in polygons for p in polygon[0]]
        ys = [p[1] for polygon in polygons for p in polygon[0]]
        geo = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
        n += 1
        pand = col["identificatie"][k]
        seen[pand] = seen.get(pand, 0) + 1
        src_key = "pdok:%s" % pand if seen[pand] == 1 else "pdok:%s#%d" % (pand, seen[pand])   # 한 pand가 지붕 조각마다 행으로 나뉜다(암스테르담 25GN1: 13,809건·38,700행, 대부분 겹치지 않는 조각)
        rows.append((pack_no * 10 ** 7 + n, src_key, None, "", None, 0, 0, "", height, height_src, grade, None, use_apr_day,
                     "active", None, col["rf_roof_type"][k] if "rf_roof_type" in col else None, None,
                     round(sum(dev_plateau.get_ring_area(polygon[0]) for polygon in polygons), 2), None,
                     json.dumps(geo, separators=(",", ":")), 4326, "pdok", None, min(xs), max(xs), min(ys), max(ys)))
    return rows


# ── 팩 ──────────────────────────────────────────────────

def build_pack(bladnr, entry, pack_no, pack_dir=PACK_DIR):
    # type: (str, dict, int, str) -> dict
    """도엽 하나 → nl<도엽>_context.db.xz. 매니페스트 항목 dict(통계 stats 포함)를 돌려준다. 건물이 없으면 None."""
    started = time.time()
    name = "%s%s_context.db" % (constants.NL_PACK_PREFIX, bladnr)
    path = os.path.join(pack_dir, name)
    for stale in (path, path + ".xz"):
        if os.path.exists(stale):
            os.remove(stale)
    data = _download(entry["url"])
    work = tempfile.mkdtemp(prefix="pdok_")
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            gpkgs = [m for m in archive.namelist() if m.lower().endswith(".gpkg")]
            if not gpkgs:
                return None
            archive.extract(gpkgs[0], work)
        rows = get_rows(os.path.join(work, gpkgs[0]), pack_no)
    finally:
        shutil.rmtree(work, ignore_errors=True)
    if not rows:
        return None
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA journal_mode = MEMORY")
    connection.execute("PRAGMA synchronous = OFF")
    connection.executescript(dev_plateau.SCHEMA_SQL)
    connection.executemany("INSERT INTO buildings VALUES (%s)" % ",".join("?" * 27), rows)
    year = int(entry["year"])
    connection.execute("INSERT INTO data_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        "pdok", "3D Basisvoorziening hoogtestatistieken gebouwen %s (%d)" % (bladnr.upper(), year), PAGE_URL, "%d-12-31" % year,
        datetime.datetime.now().isoformat(timespec="seconds"), "EPSG:28992 → 경위도(소수 %d자리)" % constants.PLATEAU_DIGITS, constants.PDOK_LICENSE,
        "Bron: Kadaster, 3D Basisvoorziening (CC BY 4.0), bewerkt door Gorani — hoogte = rf_h_roof_50p − rf_h_ground (luchtfoto %d)" % year))
    connection.execute("CREATE INDEX idx_buildings_bbox ON buildings(min_x, max_x, min_y, max_y)")
    bounds = connection.execute("SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM buildings").fetchone()
    connection.execute("PRAGMA user_version = %d" % constants.CONTEXT_DATABASE_SCHEMA_VERSION)
    connection.commit()
    connection.close()
    size, sha256 = os.path.getsize(path), dev_plateau._get_sha256(path)
    subprocess.run(["xz", "-6", "-T1", "-f", path], check=True)
    grades = {}
    for row in rows:
        grades[row[10]] = grades.get(row[10], 0) + 1
    return {"name": name, "label": "%s gebouwen" % bladnr.upper(), "url": name + ".xz", "size": size, "sha256": sha256,
            "bounds": [round(v, constants.PLATEAU_DIGITS) for v in bounds], "xz_size": os.path.getsize(path + ".xz"),
            "year": year, "buildings": len(rows), "stats": {"grades": grades, "seconds": round(time.time() - started), "zip_bytes": len(data)}}


def build(codes=None, workers=6, force=False):
    # type: (list, int, bool) -> list
    """카탈로그의 도엽(codes만, 없으면 전부)을 병렬로 팩으로 만든다. 같은 연도 팩이 있으면 건너뛴다(force면 다시).
    끝날 때마다 매니페스트를 고쳐 쓴다 — 중간에 멈춰도 다시 실행하면 이어 만든다. 실패한 도엽 목록을 돌려준다."""
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
    numbers = {bladnr: i + 1 for i, bladnr in enumerate(sorted(catalog))}
    todo = []
    for bladnr in [c.lower() for c in codes] if codes else sorted(catalog):
        name = "%s%s_context.db" % (constants.NL_PACK_PREFIX, bladnr)
        done = packs.get(name)
        if not force and done and done["year"] == catalog[bladnr]["year"] and os.path.exists(os.path.join(PACK_DIR, done["url"])):
            continue
        todo.append(bladnr)
    print("PDOK 팩 %d곳 만들기 (작업 %d개)" % (len(todo), workers), flush=True)
    failed = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(build_pack, bladnr, catalog[bladnr], numbers[bladnr]): bladnr for bladnr in todo}
        for future in concurrent.futures.as_completed(futures):
            bladnr = futures[future]
            try:
                pack = future.result()
            except Exception as exc:
                failed.append(bladnr)
                print("  %s 실패: %r" % (bladnr, exc), flush=True)
                continue
            if pack is None:
                print("  %s: 건물 없음" % bladnr, flush=True)
                continue
            packs[pack["name"]] = pack
            dev_plateau._write_manifest(packs, PACK_DIR)
            stats = pack["stats"]
            print("  %s %d: %s동 · B %.1f %% · %d s · xz %.1f MB" % (bladnr, pack["year"], format(pack["buildings"], ","),
                                                                  100.0 * stats["grades"].get("B", 0) / pack["buildings"], stats["seconds"], pack["xz_size"] / 1e6), flush=True)
    total = sum(p["xz_size"] for p in packs.values())
    print("팩 %d개 · 압축 %.2f GB · 실패 %d %s" % (len(packs), total / 1e9, len(failed), " ".join(sorted(failed))), flush=True)
    return failed


def upload():
    # type: () -> str
    """build/packs/nl/의 팩을 Hugging Face 데이터셋 nl/에 올린 뒤 매니페스트를 올린다. 외부 공개 — 사용자 확인 뒤에만 실행한다."""
    from huggingface_hub import HfApi
    api = HfApi()
    api.upload_large_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=os.path.dirname(os.path.realpath(PACK_DIR)),
                            allow_patterns=["%s/%s*_context.db.xz" % (constants.NL_PACK_DIR, constants.NL_PACK_PREFIX)])
    api.upload_file(path_or_fileobj=os.path.join(PACK_DIR, "manifest.json"), path_in_repo="%s/manifest.json" % constants.NL_PACK_DIR,
                    repo_id=constants.DATA_REPO_ID, repo_type="dataset", commit_message="네덜란드 건물 팩 매니페스트")
    return constants.COUNTRY_PACKS["nl"]["manifest"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("catalog", "build", "upload"))
    parser.add_argument("codes", nargs="*", help="도엽(bladnr, build) — 없으면 카탈로그 전부")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "catalog":
        catalog = get_catalog()
        years = {}
        for entry in catalog.values():
            years[entry["year"]] = years.get(entry["year"], 0) + 1
        print("PDOK 도엽 %d곳 — 연도별 %s · zip %.2f GB → %s" % (len(catalog), dict(sorted(years.items())), sum(e["size"] for e in catalog.values()) / 1e9, CATALOG_PATH))
    elif args.command == "build":
        sys.exit(1 if build(args.codes, args.workers, args.force) else 0)
    else:
        print("올림 →", upload())


if __name__ == "__main__":
    main()
