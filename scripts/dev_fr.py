"""프랑스 건물 팩 — IGN BD TOPO® v3.5(Licence Ouverte 2.0)의 `batiment` 층에서 바닥 윤곽·높이·층수·용도·준공일만 뽑아 데파르트망마다 팩 하나.
일본 PLATEAU 팩(dev_plateau.py)과 같은 buildings 표·매니페스트 꼴, 좌표는 경위도.

Rhino 밖 python3 + py7zr(7z)·pyogrio(GeoPackage)·pyproj(EPSG:2154 → 4326). 팩 = build/packs/fr/fr<데파르트망>_context.db.xz,
목록 = 같은 폴더 manifest.json → Hugging Face 데이터셋(constants.DATA_REPO_ID)의 fr/. 근거 docs/research/country_buildings.md.

    python3 scripts/dev_fr.py catalog          # Géoplateforme Atom 피드 → data/raw/bdtopo/catalog.json (데파르트망마다 최신 GPKG LAMB93 7z)
    python3 scripts/dev_fr.py build [코드 …]   # 팩 만들기(075·02a). 코드가 없으면 카탈로그 전부, 같은 판이 있으면 건너뛴다
    python3 scripts/dev_fr.py upload           # 외부 공개 — 사용자 확인 뒤에만
"""

import argparse
import concurrent.futures
import datetime
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

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402
import dev_plateau  # noqa: E402 — SCHEMA_SQL·get_clean_ring·get_ring_area·_get_sha256·_write_manifest
from dev_nl import _download, USER_AGENT  # noqa: E402

CATALOG_PATH = os.path.join(ROOT_DIR, "data", "raw", "bdtopo", "catalog.json")
PACK_DIR = os.path.join(ROOT_DIR, "build", "packs", constants.FR_PACK_DIR)
PAGE_URL = "https://geoservices.ign.fr/bdtopo"
RESOURCE = re.compile(r"BDTOPO_3-\d_TOUSTHEMES_GPKG_LAMB93_D(\d{2}[0-9AB])_(\d{4}-\d{2}-\d{2})")
COLUMNS = ("cleabs", "usage_1", "etat_de_l_objet", "date_d_apparition", "nombre_de_logements", "nombre_d_etages", "hauteur", "nature")


def get_catalog():
    # type: () -> dict
    """Atom 피드(10건씩)를 끝까지 넘기며 데파르트망마다 최신 판 GPKG LAMB93 7z → {코드(소문자): {date, url}}. data/raw/bdtopo/catalog.json."""
    catalog, page = {}, 1
    while True:
        with urllib.request.urlopen(urllib.request.Request(constants.BDTOPO_FEED_URL % page, headers={"User-Agent": USER_AGENT}), timeout=60) as response:
            body = response.read().decode("utf-8")
        titles = re.findall(r"<title>(.*?)</title>", body)[1:]
        if not titles:
            break
        for title in titles:
            match = RESOURCE.fullmatch(title.strip())
            if match:
                code, date = match.group(1).lower(), match.group(2)
                if code not in catalog or catalog[code]["date"] < date:
                    catalog[code] = {"date": date, "url": "https://data.geopf.fr/telechargement/download/BDTOPO/%s/%s.7z" % (title.strip(), title.strip())}
        page += 1
        if page % 50 == 0:
            print("  피드 %d쪽 … %d데파르트망" % (page, len(catalog)), flush=True)
    os.makedirs(os.path.dirname(CATALOG_PATH), exist_ok=True)
    with open(CATALOG_PATH, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=1, sort_keys=True)
    return catalog


# ── 행 만들기 ───────────────────────────────────────────

def get_height(hauteur, etages):
    # type: (float, int) -> tuple
    """hauteur(m, 사진측량 B) → 층수 × 층고(C) → 기본값(D)."""
    low, high = constants.BDTOPO_HEIGHT_RANGE
    if hauteur is not None and low <= float(hauteur) <= high:
        return round(float(hauteur), 2), "bdtopo_height", "B"
    levels = int(etages) if etages else 0
    if levels > 0:
        base, per = constants.FLOOR_HEIGHT_DEFAULT
        return round(base + per * levels, 2), "bdtopo_levels", "C"
    return constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"


def get_rows(gpkg_path, pack_no, transformer=None):
    # type: (str, int, object) -> list
    """GeoPackage `batiment`(EPSG:2154, Z 있음) → buildings 행 목록(dev_plateau.SCHEMA_SQL 칸 순서, 경위도). 계획·철거(BDTOPO_SKIP_STATES)는 뺀다.
    building_id = 팩 번호 × 10⁷ + 순번."""
    import pyogrio
    import pyproj
    import shapely
    transformer = transformer or pyproj.Transformer.from_crs("EPSG:2154", "EPSG:4326", always_xy=True)
    info = pyogrio.read_info(gpkg_path, layer="batiment")
    columns = [c for c in COLUMNS if c in list(info["fields"])]
    meta, _index, geoms, values = pyogrio.raw.read(gpkg_path, layer="batiment", columns=columns, return_fids=False, force_2d=True)
    col = {name: values[i] for i, name in enumerate(meta["fields"])}
    none = [None] * len(geoms)
    rows, n = [], 0
    for k, wkb in enumerate(geoms):
        if wkb is None or col.get("etat_de_l_objet", none)[k] in constants.BDTOPO_SKIP_STATES:
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
        etages = col.get("nombre_d_etages", none)[k]
        height, height_src, grade = get_height(col.get("hauteur", none)[k], etages)
        usage = col.get("usage_1", none)[k] or ""
        usability = constants.BDTOPO_USE.get(usage, "")
        if usability == "02000" and (col.get("nombre_de_logements", none)[k] or 0) <= 1:
            usability = "01000"   # 주거 1호 = 단독주택
        appeared = str(col.get("date_d_apparition", none)[k] or "")[:10]
        use_apr_day = appeared if re.fullmatch(r"\d{4}-\d{2}-\d{2}", appeared) and appeared >= "1500-01-01" else None
        xs = [p[0] for polygon in polygons for p in polygon[0]]
        ys = [p[1] for polygon in polygons for p in polygon[0]]
        geo = {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}
        n += 1
        rows.append((pack_no * 10 ** 7 + n, "bdtopo:%s" % col["cleabs"][k], None, usability, None, int(etages) if etages else 0, 0,
                     "bdtopo" if etages else "", height, height_src, grade, None, use_apr_day, "active", None, usage or None, None,
                     round(sum(dev_plateau.get_ring_area(polygon[0]) for polygon in polygons), 2), None,
                     json.dumps(geo, separators=(",", ":")), 4326, "bdtopo", None, min(xs), max(xs), min(ys), max(ys)))
    return rows


# ── 팩 ──────────────────────────────────────────────────

def build_pack(code, entry, pack_no, pack_dir=PACK_DIR):
    # type: (str, dict, int, str) -> dict
    """데파르트망 하나 → fr<코드>_context.db.xz. 7z(모든 테마 GPKG, 파리 210 MB → 1.3 GB)를 임시 폴더에 풀어 batiment만 읽는다."""
    import py7zr
    started = time.time()
    name = "%s%s_context.db" % (constants.FR_PACK_PREFIX, code)
    path = os.path.join(pack_dir, name)
    for stale in (path, path + ".xz"):
        if os.path.exists(stale):
            os.remove(stale)
    work = tempfile.mkdtemp(prefix="bdtopo_")
    try:
        archive_path = os.path.join(work, "d.7z")
        with open(archive_path, "wb") as f:
            f.write(_download(entry["url"]))
        with py7zr.SevenZipFile(archive_path) as archive:
            gpkgs = [m for m in archive.getnames() if m.lower().endswith(".gpkg")]
            if not gpkgs:
                return None
            archive.extract(targets=gpkgs, path=work)
        os.remove(archive_path)
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
    connection.execute("INSERT INTO data_sources VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
        "bdtopo", "BD TOPO® v3.5 D%s (%s)" % (code.upper(), entry["date"]), PAGE_URL, entry["date"],
        datetime.datetime.now().isoformat(timespec="seconds"), "EPSG:2154 → 경위도(소수 %d자리)" % constants.PLATEAU_DIGITS, constants.BDTOPO_LICENSE,
        "Source : IGN, BD TOPO® %s (Licence Ouverte 2.0), traité par Gorani — hauteur, nombre d'étages, usage, date d'apparition" % entry["date"]))
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
    return {"name": name, "label": "D%s bâtiments" % code.upper(), "url": name + ".xz", "size": size, "sha256": sha256,
            "bounds": [round(v, constants.PLATEAU_DIGITS) for v in bounds], "xz_size": os.path.getsize(path + ".xz"),
            "year": int(entry["date"][:4]), "date": entry["date"], "buildings": len(rows), "stats": {"grades": grades, "seconds": round(time.time() - started)}}


def build(codes=None, workers=3, force=False):
    # type: (list, int, bool) -> list
    """카탈로그의 데파르트망(codes만, 없으면 전부)을 팩으로. 같은 판(date)이 있으면 건너뛴다. 7z 풀기에 디스크를 쓰므로 작업 수는 3."""
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
    numbers = {code: i + 1 for i, code in enumerate(sorted(catalog))}
    todo = []
    for code in [c.lower().lstrip("d") for c in codes] if codes else sorted(catalog):
        name = "%s%s_context.db" % (constants.FR_PACK_PREFIX, code)
        done = packs.get(name)
        if not force and done and done.get("date") == catalog[code]["date"] and os.path.exists(os.path.join(PACK_DIR, done["url"])):
            continue
        todo.append(code)
    print("BD TOPO 팩 %d곳 만들기 (작업 %d개)" % (len(todo), workers), flush=True)
    failed = []
    with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(build_pack, code, catalog[code], numbers[code]): code for code in todo}
        for future in concurrent.futures.as_completed(futures):
            code = futures[future]
            try:
                pack = future.result()
            except Exception as exc:
                failed.append(code)
                print("  %s 실패: %r" % (code, exc), flush=True)
                continue
            if pack is None:
                print("  %s: 건물 없음" % code, flush=True)
                continue
            packs[pack["name"]] = pack
            dev_plateau._write_manifest(packs, PACK_DIR)
            stats = pack["stats"]
            print("  D%s %s: %s동 · B %.1f %% · %d s · xz %.1f MB" % (code.upper(), pack["date"], format(pack["buildings"], ","),
                                                                    100.0 * stats["grades"].get("B", 0) / pack["buildings"], stats["seconds"], pack["xz_size"] / 1e6), flush=True)
    total = sum(p["xz_size"] for p in packs.values())
    print("팩 %d개 · 압축 %.2f GB · 실패 %d %s" % (len(packs), total / 1e9, len(failed), " ".join(sorted(failed))), flush=True)
    return failed


def upload():
    # type: () -> str
    """build/packs/fr/의 팩을 Hugging Face 데이터셋 fr/에 올린 뒤 매니페스트를 올린다. 외부 공개 — 사용자 확인 뒤에만."""
    from huggingface_hub import HfApi
    api = HfApi()
    api.upload_large_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=os.path.dirname(os.path.realpath(PACK_DIR)),
                            allow_patterns=["%s/%s*_context.db.xz" % (constants.FR_PACK_DIR, constants.FR_PACK_PREFIX)])
    api.upload_file(path_or_fileobj=os.path.join(PACK_DIR, "manifest.json"), path_in_repo="%s/manifest.json" % constants.FR_PACK_DIR,
                    repo_id=constants.DATA_REPO_ID, repo_type="dataset", commit_message="프랑스 건물 팩 매니페스트")
    return constants.COUNTRY_PACKS["fr"]["manifest"]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", choices=("catalog", "build", "upload"))
    parser.add_argument("codes", nargs="*", help="데파르트망 코드(build) — 075·02a. 없으면 카탈로그 전부")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.command == "catalog":
        catalog = get_catalog()
        print("BD TOPO 데파르트망 %d곳 — 판 %s → %s" % (len(catalog), sorted({e["date"] for e in catalog.values()}), CATALOG_PATH))
    elif args.command == "build":
        sys.exit(1 if build(args.codes, args.workers, args.force) else 0)
    else:
        print("올림 →", upload())


if __name__ == "__main__":
    main()
