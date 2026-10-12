"""시도별 컨텍스트 DB(data/<시도>_context.db)를 구축한다 — 건물·도로·지형·수계·녹지·철도.

Rhino가 아니라 개발용 python3(geopandas 환경)에서 실행한다. 원천은 두 가지다.
  1) 수치지형도 1:5000 Ver2.0 — 시군구 묶음 data/raw/수치지형도_5000_시군구/2MAP5000_SHP_<시도>_<시군구>.zip(dsId=30205)을
     data/raw/수치지형도_5000/<도엽>.zip으로 풀어 쓴다. 도엽은 묶음 이름의 시도 하나에 배정한다(get_sheet_sido).
  2) GIS건물통합정보 시도 SHP           — data/raw/vworld_GIS건물통합정보/AL_D010_<시도>_<기준일>.zip (수동 다운로드)

    python3 scripts/dev_context_builder.py --sido 26                         # 부산
    python3 scripts/dev_context_builder.py --sido all                        # 묶음이 있는 시도 전부
    python3 scripts/dev_context_builder.py                                   # 서울 (묶음이 없으면 도엽 폴더 전부)
    python3 scripts/dev_context_builder.py --sheets 37705072,37705073,37705082,37705083   # 성수 4도엽만 (개발·테스트)
    python3 scripts/dev_context_builder.py --sheets 37705072 --out /tmp/ctx.db           # 결과 파일 지정

하는 일
  - 건물: GIS건물통합정보를 1순위로 넣고, 수치지형도 건물(층수·종류·용도)을 대표점 공간조인으로 붙인다.
    어느 GIS 폴리곤에도 안 들어가는 수치지형도 건물은 별도 행(src_key 'ngii:…')으로 보충한다.
    높이는 docs/deliverables.md §A.4 규칙으로 확정한다(height_m·height_src·height_grade·flr_src·attr_flag).
  - 피처: constants.TOPO_LAYERS에 있는 레이어만 features에 넣는다(theme/kind/code/name/value/attrs_json/sheet).
    교량·입체교차부·인터체인지 면의 5 m 버퍼 안 표고점은 kind='spot_struct'로 바꿔 TIN에서 빠지게 한다.
  - 정합 샘플(P0): 도엽마다 지목 '도로' 필지(seoul_site.db) 합집합 경계를 10 m 간격으로 샘플해 수치지형도 도로경계면 합집합 경계까지
    최근접거리·dx·dy를 features(theme 'qa', kind 'align_sample', value=거리 m, attrs {dx,dy}, sheet)에 넣는다. 런타임은 statistics로 중앙값·p90만 낸다.
  - 모든 좌표는 EPSG:5186 GeoJSON(소수 3자리) + 경계상자 컬럼. RTree는 쓰지 않는다.
  - 파일 단위 적재 이력(source_files, sha256)을 남긴다. 검증을 통과해야 기존 DB를 교체한다.
"""

import argparse
import csv
import datetime
import hashlib
import json
import os
import sqlite3
import sys
import time
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pyogrio
import shapely
from shapely import STRtree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constants  # noqa: E402
import non_rhino_utils  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[1]
SHEET_DIR = ROOT_DIR / constants.TOPO_SHEET_DIRNAME
BUILDING_DIR = ROOT_DIR / constants.BUILDING_BULK_DIRNAME
DATABASE_PATH = ROOT_DIR / constants.CONTEXT_DATABASE_PATH
SITE_DATABASE_PATH = ROOT_DIR / constants.DATABASE_PATH   # 정합 샘플용 지목 도로 필지
BUNDLE_DIR = ROOT_DIR / constants.TOPO_BUNDLE_DIRNAME
SEOUL_CODE = "11"
ID_OFFSET_PER_SIDO = 10 ** 9   # dev_database_builder와 같다 — 시도 DB 여러 개를 한 연결로 묶어도 id가 겹치지 않게
DROPPED_GEOMETRIES = []  # (도엽, 레이어 파일, 버린 피처 수) — 빌드 끝에 출력

TOPO_SOURCE = {
    "source_id": "ngii_topo_5000",
    "name": "국토지리정보원 수치지형도 1:5,000 Ver2.0 (브이월드 도엽 다운로드)",
    "page_url": "https://map.ngii.go.kr/ms/map/NlipMap.do",
    "license": "공공누리 제1유형(출처표시). 등고선·표고값은 온라인 표시 제한(국토지리정보원 보안관리규정 별표1)",
    "crs": "EPSG:5186",
    "note": "도엽 zip 그대로 보관. 레이어 접두(N3/N1)는 무시하고 '도형자_코드'로 매핑. 제작연도는 sheets.csv year 열(비면 다운로드일).",
}
BUILDING_SOURCE = {
    "source_id": "vworld_building",
    "name": "국토교통부 GIS건물통합정보 (국가중점데이터 dsId=18, 서울 전체본)",
    "page_url": "https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=18",
    "license": "CC BY(브이월드) / 공공누리 제1유형(data.go.kr 15083092). 정보제공 목적, 법적 효력 없음",
    "crs": "EPSG:5186",
    "note": "월간 전체본 교체. 높이 A16은 건축물대장 법정 높이(채움 약 40%). 층수 결측은 수치지형도 층수로 보충.",
}

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS data_sources (
    source_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    page_url TEXT NOT NULL,
    reference_date TEXT,
    acquired_at TEXT NOT NULL,
    crs TEXT,
    license TEXT,
    note TEXT
);
-- 원천 파일 단위 적재 이력. sha256이 같으면 다시 적재하지 않는다.
CREATE TABLE IF NOT EXISTS source_files (
    source_id TEXT NOT NULL,
    file_name TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    size_bytes INTEGER,
    listed_date TEXT,
    loaded_at TEXT NOT NULL,
    PRIMARY KEY (source_id, file_name)
);
-- 건물 한 동 = 한 행. 1순위 GIS건물통합정보, 보충 수치지형도(src_key 'ngii:…').
CREATE TABLE IF NOT EXISTS buildings (
    building_id INTEGER PRIMARY KEY,
    src_key TEXT NOT NULL UNIQUE,
    pnu TEXT,
    pnu_src TEXT,                 -- source(원천 A2) / none
    pnu_raw TEXT,                 -- 19자리가 아닌 원값
    bld_nm TEXT,
    dong_nm TEXT,
    usability TEXT,               -- 건축물용도코드 5자리
    strct_cd TEXT,
    grnd_flr INTEGER NOT NULL DEFAULT 0,   -- 채택 지상층수 (0 = 결측)
    ugrnd_flr INTEGER NOT NULL DEFAULT 0,
    flr_src TEXT,                 -- grnd_flr(대장) / topo(수치지형도) / ''
    height_m REAL NOT NULL,
    height_src TEXT NOT NULL,     -- height / topo_flr / grnd_flr / default (+'!' 속성 불신, '?' 부속동 의심)
    height_grade TEXT NOT NULL,   -- A~D
    attr_flag TEXT,               -- '!' / '?' / ''
    use_apr_day TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    demol_day TEXT,
    arch_area_sqm REAL,
    total_area_sqm REAL,
    plat_area_sqm REAL,
    bc_rat REAL,
    vl_rat REAL,
    ngii_kind TEXT,               -- 수치지형도 '종류' (아파트·연립주택·일반주택·주택외건물·무벽건물·가건물·공사중건물)
    ngii_use TEXT,                -- 수치지형도 '용도'
    ngii_floors INTEGER,          -- 수치지형도 '층수'
    data_changed_date TEXT,
    footprint_area_sqm REAL NOT NULL,
    geometry_json TEXT NOT NULL,
    geometry_crs INTEGER NOT NULL,
    source_id TEXT NOT NULL,
    reference_date TEXT,
    sheet TEXT,
    min_x REAL NOT NULL,
    max_x REAL NOT NULL,
    min_y REAL NOT NULL,
    max_y REAL NOT NULL
);
-- 건물 외 전부. 필지 DB overlays와 같은 모양.
CREATE TABLE IF NOT EXISTS features (
    feature_id INTEGER PRIMARY KEY,
    source_id TEXT NOT NULL,
    theme TEXT NOT NULL,
    kind TEXT NOT NULL,
    code TEXT,
    name TEXT,
    value REAL,
    attrs_json TEXT,
    sheet TEXT,
    geometry_json TEXT NOT NULL,
    geometry_crs INTEGER NOT NULL,
    reference_date TEXT,
    min_x REAL NOT NULL,
    max_x REAL NOT NULL,
    min_y REAL NOT NULL,
    max_y REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_buildings_bbox ON buildings(min_x, max_x, min_y, max_y);
CREATE INDEX IF NOT EXISTS idx_buildings_pnu ON buildings(pnu);
CREATE INDEX IF NOT EXISTS idx_buildings_status ON buildings(status);
CREATE INDEX IF NOT EXISTS idx_features_bbox ON features(min_x, max_x, min_y, max_y);
CREATE INDEX IF NOT EXISTS idx_features_theme ON features(theme, kind);
CREATE INDEX IF NOT EXISTS idx_features_sheet ON features(sheet);
"""


def _now():
    # type: () -> str
    return datetime.datetime.now().isoformat(timespec="seconds")


def _sha256(path):
    # type: (Path) -> str
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect(database_path):
    # type: (Path) -> sqlite3.Connection
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    connection.execute("PRAGMA journal_mode = MEMORY")
    connection.execute("PRAGMA synchronous = OFF")
    connection.execute("PRAGMA temp_store = MEMORY")
    connection.executescript(SCHEMA_SQL)
    connection.execute("PRAGMA user_version = %d" % constants.CONTEXT_DATABASE_SCHEMA_VERSION)
    return connection


def _upsert_source(connection, source, reference_date):
    # type: (sqlite3.Connection, dict, str) -> None
    connection.execute(
        """
        INSERT INTO data_sources (source_id, name, page_url, reference_date, acquired_at, crs, license, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET reference_date = excluded.reference_date, acquired_at = excluded.acquired_at
        """,
        (source["source_id"], source["name"], source["page_url"], reference_date, _now(),
         source["crs"], source["license"], source["note"]),
    )


def _record_file(connection, source_id, path, listed_date, sha=None):
    # type: (sqlite3.Connection, str, Path, str, str) -> None
    connection.execute(
        "INSERT OR REPLACE INTO source_files (source_id, file_name, sha256, size_bytes, listed_date, loaded_at) VALUES (?, ?, ?, ?, ?, ?)",
        (source_id, path.name, sha or _sha256(path), path.stat().st_size, listed_date, _now()),
    )


# ── 지오메트리 공통 ──────────────────────────────────────────

def _geojson_strings(geometries):
    # type: (np.ndarray) -> list
    """shapely 배열 → GeoJSON 문자열 목록. 좌표는 mm로 반올림(pointwise, 위상 변경 없음)."""
    rounded = shapely.set_precision(geometries, constants.GEOMETRY_JSON_PRECISION, mode="pointwise")
    return list(shapely.to_geojson(rounded))


def _bounds_columns(geometries):
    # type: (np.ndarray) -> np.ndarray
    """(n, 4) = min_x, min_y, max_x, max_y"""
    return shapely.bounds(geometries)


def _to_5186(frame, label):
    # type: (object, str) -> object
    """프레임 좌표계를 확인해 EPSG:5186이 아니면 변환한다. .prj가 없으면 Y 범위로 판정한다.

    서울 EPSG:5186 Y는 540~565 k, EPSG:5174(Bessel)는 436~467 k. 그 밖이면 멈춘다.
    """
    crs = frame.crs
    epsg = crs.to_epsg() if crs is not None else None
    if epsg is None and crs is not None and "Korea_2000" in crs.to_wkt():
        epsg = next((code for belt, code in constants.KOREA_2000_BELTS.items() if belt in crs.to_wkt()), None)
    if epsg == constants.DATABASE_CRS:
        return frame.set_crs(epsg=constants.DATABASE_CRS, allow_override=True)
    if epsg in constants.KOREA_2000_BELTS.values():
        # 서부·동부·동해 원점 도엽(예: 충북 36801001 EPSG:5187)은 내부 좌표계 중부원점으로 옮긴다 — 반도 안은 왜곡 무시 가능
        return frame.to_crs(epsg=constants.DATABASE_CRS)
    y_values = shapely.bounds(frame.geometry.values)[:, 1]
    median_y = float(np.nanmedian(y_values)) if len(y_values) else 0.0
    if 530000 <= median_y <= 575000 and epsg is None:
        return frame.set_crs(epsg=constants.DATABASE_CRS, allow_override=True)
    if epsg == constants.SEOUL_SOURCE_CRS or 430000 <= median_y <= 470000:
        source_epsg = epsg or constants.SEOUL_SOURCE_CRS
        return frame.set_crs(epsg=source_epsg, allow_override=True).to_crs(epsg=constants.DATABASE_CRS)
    raise RuntimeError("%s: 좌표계를 판정할 수 없습니다 (epsg=%s, 중앙 Y=%.0f)" % (label, epsg, median_y))


# ── 수치지형도 도엽 ──────────────────────────────────────────

def read_sheet_index(sheet_dir=SHEET_DIR):
    # type: (Path) -> dict
    """sheets.csv → {도엽번호: 행}. 없으면 빈 dict."""
    path = sheet_dir / constants.TOPO_SHEET_INDEX_FILENAME
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return {row["sheet"]: row for row in csv.DictReader(f)}


def _sheet_layers(zip_path):
    # type: (Path) -> dict
    """zip 안 SHP → {'A_A0010000': 'zip 안 경로'}. 접두 N3/N1을 뗀다."""
    with zipfile.ZipFile(zip_path) as z:
        names = [n for n in z.namelist() if n.lower().endswith(".shp")]
    return {Path(n).name[2:12]: n for n in names}


def _read_layer(zip_path, member):
    # type: (Path, str) -> object
    """zip 안 SHP 레이어 하나를 읽는다. GEOS가 못 만드는 도형(닫히지 않은 링 등)은 버리고 건수만 기록한다.

    도엽 37608066 도로경계면(N3A_A0010000) 1건의 링이 닫혀 있지 않아 전체 빌드가 멈췄다(2026-10-07).
    원천 오류를 알고리즘으로 고치지 않고 그 피처만 뺀다(CLAUDE.md 예외 형상 원칙).
    """
    path = "/vsizip/%s/%s" % (zip_path.resolve(), member)
    frame = pyogrio.read_dataframe(path, encoding=constants.TOPO_ENCODING, on_invalid="ignore")
    dropped = int(frame.geometry.isna().sum())
    if dropped:
        DROPPED_GEOMETRIES.append((zip_path.stem, Path(member).name, dropped))
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
    if len(frame):
        frame = _to_5186(frame, "%s:%s" % (zip_path.name, member))
    return frame


def _attrs_json(frame, drop_columns):
    # type: (object, set) -> list
    """도형·값 필드를 뺀 나머지 속성을 행별 JSON으로. 빈 값은 뺀다."""
    columns = [c for c in frame.columns if c != "geometry" and c not in drop_columns]
    records = frame[columns].to_dict("records") if columns else [{} for _ in range(len(frame))]
    out = []
    for record in records:
        clean = {}
        for key, value in record.items():
            if value is None or (isinstance(value, float) and np.isnan(value)) or value == "":
                continue
            clean[key] = value.item() if hasattr(value, "item") else value
        out.append(json.dumps(clean, ensure_ascii=False) if clean else None)
    return out


def _value_column(frame, field):
    # type: (object, str) -> list
    if not field or field not in frame.columns:
        return [None] * len(frame)
    return [float(v) if v not in (None, "") and not (isinstance(v, float) and np.isnan(v)) else None
            for v in pd.to_numeric(frame[field], errors="coerce").tolist()]


def load_sheet(connection, zip_path, sheet_row, topo_buildings):
    # type: (sqlite3.Connection, Path, dict, list) -> dict
    """도엽 zip 하나를 features에 넣고 건물 프레임은 topo_buildings에 모은다. 레이어별 건수를 돌려준다."""
    code = zip_path.stem
    reference_date = (sheet_row or {}).get("year") or ""
    if not reference_date:
        reference_date = ((sheet_row or {}).get("downloaded_at") or _now())[:10] + " (제작연도 미기재)"
    layers = _sheet_layers(zip_path)
    counts = {}
    rows = []
    for key, member in layers.items():
        if key == constants.TOPO_BUILDING_LAYER:
            frame = _read_layer(zip_path, member)
            if len(frame):
                frame = frame.assign(sheet=code, reference_date=reference_date)
                topo_buildings.append(frame)
            counts["building"] = len(frame)
            continue
        mapping = constants.TOPO_LAYERS.get(key)
        if mapping is None:
            continue
        theme, kind, value_field = mapping
        frame = _read_layer(zip_path, member)
        if not len(frame):
            continue
        geometries = frame.geometry.values
        bounds = _bounds_columns(geometries)
        geojson = _geojson_strings(geometries)
        names = frame[constants.TOPO_NAME_FIELD].tolist() if constants.TOPO_NAME_FIELD in frame.columns else [None] * len(frame)
        values = _value_column(frame, value_field)
        attrs = _attrs_json(frame, {value_field, constants.TOPO_NAME_FIELD} - {None})
        for i in range(len(frame)):
            rows.append((TOPO_SOURCE["source_id"], theme, kind, key[2:], names[i] or None, values[i], attrs[i], code,
                         geojson[i], constants.DATABASE_CRS, reference_date,
                         float(bounds[i][0]), float(bounds[i][2]), float(bounds[i][1]), float(bounds[i][3])))
        counts[kind] = counts.get(kind, 0) + len(frame)
    connection.executemany(
        """INSERT INTO features (source_id, theme, kind, code, name, value, attrs_json, sheet,
               geometry_json, geometry_crs, reference_date, min_x, max_x, min_y, max_y)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    return counts


def reclassify_struct_spots(connection):
    # type: (sqlite3.Connection) -> int
    """교량·입체교차부·인터체인지 면의 버퍼 안 표고점을 spot_struct로 바꾼다. 바꾼 수를 돌려준다."""
    placeholders = ",".join("?" for _ in constants.TOPO_STRUCT_KINDS)
    struct_rows = connection.execute(
        "SELECT geometry_json FROM features WHERE theme = 'bridge' AND kind IN (%s)" % placeholders,
        constants.TOPO_STRUCT_KINDS,
    ).fetchall()
    if not struct_rows:
        return 0
    structures = shapely.from_geojson([r[0] for r in struct_rows])
    structures = shapely.buffer(structures, constants.SPOT_STRUCT_BUFFER)
    spot_rows = connection.execute(
        "SELECT feature_id, geometry_json FROM features WHERE theme = 'terrain' AND kind = 'spot'"
    ).fetchall()
    if not spot_rows:
        return 0
    points = shapely.from_geojson([r[1] for r in spot_rows])
    tree = STRtree(structures)
    hit = tree.query(points, predicate="intersects")  # (2, n): [점 index, 구조물 index]
    spot_indexes = sorted(set(hit[0].tolist()))
    connection.executemany(
        "UPDATE features SET kind = 'spot_struct' WHERE feature_id = ?",
        [(spot_rows[i][0],) for i in spot_indexes],
    )
    return len(spot_indexes)


# ── 정합 샘플 (theme qa / kind align_sample) ──────────────────

def get_align_samples(cad_polys, topo_polys, seam=None, step=constants.ALIGN_SAMPLE_STEP, max_dist=constants.ALIGN_MAX_DIST):
    # type: (list, list, object, float, float) -> list
    """지목 도로 필지 ↔ 수치지형도 도로경계면의 경계선 정합 샘플 (08정합 A1b 'cad→topo, ≤10 m 매칭분' 재현).

    입력: cad_polys·topo_polys = shapely 폴리곤 목록(EPSG:5186), seam = 제외 영역(도엽 경계 버퍼, None이면 없음), step 샘플 간격 m, max_dist 상대선 없음 기준 m.
    처리: 각 합집합의 경계선 → cad 경계를 step 간격 샘플(dev_probe_alignment.sample_along) → seam 안 점 제외 → topo 경계까지 최근접거리·벡터(nearest_dist)
          → max_dist 이하만(그보다 멀면 상대선이 없는 것으로 보고 버린다 — 전부 넣으면 p90이 11 m로 뛴다, 08정합 실측).
    출력: ``[(x, y, dist, dx, dy)]`` — dx·dy는 cad 점에서 topo 최근접점으로 가는 벡터(m).
    """
    from dev_probe_alignment import nearest_dist, sample_along, union_polygons   # scipy·geopandas를 끌어오므로 호출 때만 import

    if not len(cad_polys) or not len(topo_polys):
        return []
    cad_union = union_polygons(list(cad_polys))
    topo_union = union_polygons(list(topo_polys))
    # 도로가 없는 도엽(한강 수면 등)은 합집합이 None/빈 도형이다 — 서울 전체 빌드 때 도엽 1장에서 멈춘 적 있다(2026-10-07)
    if cad_union is None or topo_union is None or cad_union.is_empty or topo_union.is_empty:
        return []
    cad_line = cad_union.boundary
    topo_line = topo_union.boundary
    pts = sample_along(cad_line, step)
    if seam is not None and len(pts):
        pts = pts[~shapely.intersects(shapely.points(pts), seam)]
    if not len(pts):
        return []
    dist, vec = nearest_dist(pts, topo_line)
    keep = dist <= max_dist
    return [(float(x), float(y), round(float(d), 3), round(float(dx), 3), round(float(dy), 3))
            for (x, y), d, (dx, dy) in zip(pts[keep], dist[keep], vec[keep])]


def load_align_samples(connection, site_database_path=SITE_DATABASE_PATH):
    # type: (sqlite3.Connection, Path) -> int
    """features에 적재된 도엽마다 정합 샘플을 만들어 theme 'qa'로 넣는다(그 도엽의 qa 행은 먼저 지운다 — 도엽 교체 규칙). 넣은 행 수를 돌려준다.

    입력: 도엽 features가 들어간 connection, 필지 DB 경로(없으면 0건·메시지). 처리: 도엽별 road/surface 합집합 bbox 안 지목 '도로' 필지를 bbox 질의 →
          도엽 bbox로 자르고 → get_align_samples(seam = bbox 경계 SEAM_BUFFER). 출력: 적재 행 수.
    """
    from dev_probe_alignment import SEAM_BUFFER

    site_database_path = Path(site_database_path)
    if not site_database_path.exists():
        print("정합 샘플 건너뜀 — 필지 DB 없음: %s" % site_database_path, flush=True)
        return 0
    site = sqlite3.connect(str(site_database_path))
    total = 0
    try:
        sheets = connection.execute(
            "SELECT sheet, MIN(reference_date) FROM features WHERE theme = 'road' AND kind = 'surface' GROUP BY sheet ORDER BY sheet").fetchall()
        for code, reference_date in sheets:
            rows = connection.execute("SELECT geometry_json FROM features WHERE theme = 'road' AND kind = 'surface' AND sheet = ?", (code,)).fetchall()
            topo = shapely.make_valid(shapely.from_geojson([r[0] for r in rows]))
            min_x, min_y, max_x, max_y = shapely.total_bounds(topo)
            tile = shapely.box(min_x, min_y, max_x, max_y)
            cad_rows = site.execute(
                "SELECT geometry_json FROM parcels WHERE land_category = '도로' AND min_x <= ? AND max_x >= ? AND min_y <= ? AND max_y >= ?",
                (max_x, min_x, max_y, min_y)).fetchall()
            cad = shapely.intersection(shapely.make_valid(shapely.from_geojson([r[0] for r in cad_rows])), tile) if cad_rows else []
            samples = get_align_samples(cad, topo, tile.boundary.buffer(SEAM_BUFFER))
            connection.execute("DELETE FROM features WHERE theme = 'qa' AND kind = 'align_sample' AND sheet = ?", (code,))
            connection.executemany(
                """INSERT INTO features (source_id, theme, kind, code, name, value, attrs_json, sheet,
                       geometry_json, geometry_crs, reference_date, min_x, max_x, min_y, max_y)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                [(TOPO_SOURCE["source_id"], "qa", "align_sample", None, None, d, json.dumps({"dx": dx, "dy": dy}), code,
                  json.dumps({"type": "Point", "coordinates": [round(x, 3), round(y, 3)]}), constants.DATABASE_CRS, reference_date, x, x, y, y)
                 for x, y, d, dx, dy in samples])
            total += len(samples)
            print("정합 샘플 %s — 도로 필지 %d · 샘플 %d" % (code, len(cad_rows), len(samples)), flush=True)
    finally:
        site.close()
    return total


# ── 건물 ────────────────────────────────────────────────────

def _find_building_zip(building_dir=BUILDING_DIR, sido_code=SEOUL_CODE):
    # type: (Path, str) -> Path
    pattern = constants.BUILDING_BULK_FILE_GLOB % sido_code
    paths = sorted(building_dir.glob(pattern))
    if not paths:
        raise FileNotFoundError(
            "GIS건물통합정보 zip이 없습니다: %s/%s\n브이월드 국가중점데이터(dsId=18)에서 시도 전체본을 받아 두세요."
            % (building_dir, pattern)
        )
    return paths[-1]  # 파일명의 기준일이 가장 늦은 것


def get_sheet_sido(bundle_dir=BUNDLE_DIR, sheet_dir=SHEET_DIR):
    # type: (Path, Path) -> dict
    """시군구 묶음 → {도엽번호: 시도 코드}. 안 풀린 도엽 zip은 sheet_dir에 푼다.

    경계 도엽은 이웃 시도 묶음에도 들어 있다 — 가장 많은 묶음에 든 시도, 같으면 코드가 작은 시도 하나에 배정한다
    (여러 시도 팩을 한 연결로 묶을 때 같은 도엽이 두 번 나오지 않게). ponytail: 도엽 중심이 실제로 어느 시도인지는 보지 않는다.
    """
    votes = {}
    for bundle in sorted(bundle_dir.glob("2MAP5000_SHP_*.zip")):
        prefix = bundle.stem[len("2MAP5000_SHP_"):].split("_")[0]
        code = constants.TOPO_BUNDLE_SIDO.get(prefix)
        if code is None:
            print("시도를 모르는 묶음 — 건너뜀: %s" % bundle.name, flush=True)
            continue
        if not zipfile.is_zipfile(bundle):
            print("손상된 묶음 — 건너뜀(다시 받을 것): %s" % bundle.name, flush=True)
            continue
        with zipfile.ZipFile(bundle) as archive:
            for name in archive.namelist():
                sheet = Path(name).stem
                if not name.endswith(".zip") or not sheet.isdigit():
                    continue
                target = sheet_dir / (sheet + ".zip")
                if not target.exists():
                    sheet_dir.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as src, open(target, "wb") as dst:
                        dst.write(src.read())
                votes.setdefault(sheet, {}).setdefault(code, 0)
                votes[sheet][code] += 1
    return {sheet: sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0] for sheet, counts in votes.items()}


def _get_sido_bounds(sido_code):
    # type: (str) -> tuple
    """시도 필지 DB의 범위(min_x, min_y, max_x, max_y). 필지 DB가 이미 팩으로 압축돼 지워졌으면 매니페스트 범위, 둘 다 없으면 None."""
    import dev_database_builder
    path = dev_database_builder.get_database_path(sido_code)
    if not path.exists():
        manifest_path = ROOT_DIR / "build" / "packs" / "manifest.json"
        if manifest_path.exists():
            for pack in json.loads(manifest_path.read_text(encoding="utf-8"))["packs"]:
                if pack["name"] == path.name and pack.get("bounds"):
                    return tuple(pack["bounds"])
        return None
    connection = sqlite3.connect(str(path))
    try:
        return connection.execute("SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM parcels").fetchone()
    finally:
        connection.close()


def _read_neighbor_buildings(sido_code, bbox, building_dir=BUILDING_DIR):
    # type: (str, tuple, Path) -> list
    """bbox에 걸치는 이웃 시도의 GIS건물 프레임 목록 — 경계 도엽의 수치지형도 건물을 이웃 대장 건물과 매칭만 하려고 읽는다(넣지 않는다)."""
    frames = []
    for code in sorted(constants.SIDO):
        if code == sido_code:
            continue
        bounds = _get_sido_bounds(code)
        if bounds is None or not (bounds[0] <= bbox[2] and bounds[2] >= bbox[0] and bounds[1] <= bbox[3] and bounds[3] >= bbox[1]):
            continue
        try:
            frames.append(read_bulk_buildings(_find_building_zip(building_dir, code), bbox))
        except FileNotFoundError:
            continue
    return frames


def _offset_ids(connection, offset):
    # type: (sqlite3.Connection, int) -> None
    """building_id·feature_id를 offset만큼 띄운다(dev_database_builder._offset_ids와 같은 이유)."""
    connection.execute("UPDATE buildings SET building_id = building_id + ?", (offset,))
    connection.execute("UPDATE features SET feature_id = feature_id + ?", (offset,))
    connection.commit()


def read_bulk_buildings(zip_path, bbox=None):
    # type: (Path, tuple) -> object
    """GIS건물통합정보 zip → 프레임(표준 컬럼명, EPSG:5186). bbox=(min_x, min_y, max_x, max_y)면 그 안만."""
    with zipfile.ZipFile(zip_path) as z:
        member = [n for n in z.namelist() if n.lower().endswith(".shp")][0]
    path = "/vsizip/%s/%s" % (zip_path.resolve(), member)
    frame = pyogrio.read_dataframe(path, encoding=constants.BUILDING_BULK_ENCODING,
                                   columns=list(constants.BUILDING_BULK_COLUMNS), bbox=bbox)
    frame = frame.rename(columns=constants.BUILDING_BULK_COLUMNS)
    frame = frame[frame.geometry.notna() & ~frame.geometry.is_empty]
    frame = _to_5186(frame, zip_path.name)
    for column in ("grnd_flr", "ugrnd_flr"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    for column in ("arch_area_sqm", "total_area_sqm", "plat_area_sqm", "height_raw", "bc_rat", "vl_rat"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
    for column in ("src_id", "pnu", "usability", "strct_cd", "use_apr_day", "reference_date", "bld_nm", "dong_nm", "data_changed_date"):
        frame[column] = frame[column].fillna("").astype(str).str.strip()
    return frame.reset_index(drop=True)


def _normalize_topo_buildings(frames):
    # type: (list) -> object
    """도엽별 수치지형도 건물 프레임을 하나로 합치고 컬럼을 정리한다."""
    if not frames:
        return None
    frame = pd.concat(frames, ignore_index=True)
    frame["ngii_floors"] = pd.to_numeric(frame.get("층수"), errors="coerce").fillna(0).astype(int)
    frame["ngii_kind"] = frame.get("종류", pd.Series([""] * len(frame))).fillna("").astype(str).str.strip()
    frame["ngii_use"] = frame.get("용도", pd.Series([""] * len(frame))).fillna("").astype(str).str.strip()
    frame["ngii_name"] = frame.get("명칭", pd.Series([""] * len(frame))).fillna("").astype(str).str.strip()
    frame["ufid"] = frame.get("UFID", pd.Series([""] * len(frame))).fillna("").astype(str).str.strip()
    # 도엽 경계에서 같은 건물이 두 도엽에 걸쳐 두 번 나온다 — UFID가 같으면 하나만
    frame = frame[~((frame["ufid"] != "") & frame.duplicated("ufid"))]
    return frame.reset_index(drop=True)


def _use_category(usability, ngii_kind, ngii_use, usable):
    # type: (str, str, str, bool) -> str
    """높이 모델 대분류(usability 앞 2자리). 대장이 없거나 불신이면 수치지형도 종류·용도로."""
    if usable and usability and usability[:2] in constants.FLOOR_HEIGHT_MODEL:
        return usability[:2]
    if ngii_kind in constants.TOPO_KIND_TO_USE:
        return constants.TOPO_KIND_TO_USE[ngii_kind]
    if ngii_use in constants.TOPO_USE_TO_USE:
        return constants.TOPO_USE_TO_USE[ngii_use]
    if usable and usability and usability[:2].isdigit():
        return usability[:2]
    return ""


def _model_height(category, floors):
    # type: (str, int) -> float
    a, b = constants.FLOOR_HEIGHT_MODEL.get(category, constants.FLOOR_HEIGHT_DEFAULT)
    height = a + b * floors
    low, high = constants.FLOOR_HEIGHT_CLAMP
    return float(min(max(height, low * floors), high * floors))


def decide_height(row):
    # type: (dict) -> dict
    """docs/deliverables.md §A.4 규칙. 입력 키: usability, grnd_flr, height_raw, arch_area_sqm,
    footprint_area_sqm, ngii_kind, ngii_use, ngii_floors. 출력: grnd_flr, flr_src, height_m, height_src, height_grade, attr_flag."""
    footprint = float(row["footprint_area_sqm"])
    arch = float(row.get("arch_area_sqm") or 0.0)
    flag = ""
    if arch > 0 and arch < footprint * constants.BUILDING_ATTR_DISTRUST_RATIO:
        flag = "!"
    elif arch > footprint * constants.BUILDING_ATTR_SUSPECT_RATIO:
        flag = "?"
    usable = flag != "!"
    grnd = int(row.get("grnd_flr") or 0) if usable else 0
    ngii_floors = int(row.get("ngii_floors") or 0)
    ngii_kind = row.get("ngii_kind") or ""
    height_raw = float(row.get("height_raw") or 0.0) if usable else 0.0
    usability = row.get("usability") or ""

    flr_src = ""
    topo_apt = ngii_kind in constants.TOPO_APT_KINDS and ngii_floors >= grnd + constants.TOPO_APT_FLOOR_GAP
    if topo_apt:
        grnd, flr_src = ngii_floors, "topo"
    elif grnd > 0:
        flr_src = "grnd_flr"
    elif ngii_floors > 0:
        grnd, flr_src = ngii_floors, "topo"

    category = _use_category(usability, ngii_kind, row.get("ngii_use") or "", usable)
    per_low, per_high = constants.HEIGHT_RAW_PER_FLOOR_RANGE
    abs_low, abs_high = constants.HEIGHT_RAW_RANGE_NO_FLOOR
    raw_floors = int(row.get("grnd_flr") or 0) if usable else 0
    if height_raw > 0 and (
        (raw_floors > 0 and per_low <= height_raw / raw_floors <= per_high)
        or (raw_floors <= 0 and abs_low <= height_raw <= abs_high)
    ):
        height, src, grade = height_raw, "height", "A"
    elif topo_apt:
        height, src, grade = _model_height("02", grnd), "topo_flr", "B"
    elif flr_src == "grnd_flr":
        height, src, grade = _model_height(category, grnd), "grnd_flr", "B"
    elif flr_src == "topo":
        height, src, grade = _model_height(category, grnd), "topo_flr", "C"
    else:
        height, src, grade = constants.DEFAULT_BUILDING_HEIGHT_M, "default", "D"
    if flag == "?" and grade != "D":
        grade = constants.HEIGHT_GRADES[constants.HEIGHT_GRADES.index(grade) + 1]
    return {"grnd_flr": grnd, "flr_src": flr_src, "height_m": round(height, 2),
            "height_src": src + flag, "height_grade": grade, "attr_flag": flag}


def merge_buildings(bulk, topo):
    # type: (object, object) -> tuple
    """GIS건물(1순위)에 수치지형도 건물을 대표점 공간조인으로 붙인다. (합친 프레임, 매칭 수, 보충 수)."""
    bulk = bulk.copy()
    bulk["footprint_area_sqm"] = shapely.area(bulk.geometry.values)
    bulk["ngii_kind"], bulk["ngii_use"], bulk["ngii_floors"] = "", "", 0
    bulk["src_key"] = "bldg:" + bulk["src_id"]
    bulk["source_id"] = BUILDING_SOURCE["source_id"]
    bulk["sheet"] = None
    matched = 0
    extra = None
    if topo is not None and len(topo) and len(bulk):
        tree = STRtree(bulk.geometry.values)
        points = shapely.point_on_surface(topo.geometry.values)
        hit = tree.query(points, predicate="within")  # [topo index, bulk index]
        # 한 GIS 폴리곤에 여러 수치지형도 건물이 들어가면 발자국이 가장 큰 것을 쓴다
        pairs = pd.DataFrame({"topo": hit[0], "bulk": hit[1]})
        pairs["area"] = shapely.area(topo.geometry.values[pairs["topo"].values])
        pairs = pairs.sort_values("area", ascending=False).drop_duplicates("bulk")
        pairs = pairs.drop_duplicates("topo")
        bulk.loc[pairs["bulk"].values, "ngii_kind"] = topo["ngii_kind"].values[pairs["topo"].values]
        bulk.loc[pairs["bulk"].values, "ngii_use"] = topo["ngii_use"].values[pairs["topo"].values]
        bulk.loc[pairs["bulk"].values, "ngii_floors"] = topo["ngii_floors"].values[pairs["topo"].values]
        matched = len(pairs)
        unmatched = topo[~topo.index.isin(set(hit[0].tolist()))]
        # 대표점은 밖인데 몸통이 GIS 건물과 절반 넘게 겹치면 같은 건물이다 — 보충하면 두 번 그려진다
        # (서울 전체 실측: 보충 후보의 1~2 %. 그 외 83~86 %는 전혀 안 겹치는 미등재 건물)
        if len(unmatched):
            cand = tree.query(unmatched.geometry.values, predicate="intersects")  # [unmatched index, bulk index]
            if cand.shape[1]:
                inter = shapely.area(shapely.intersection(unmatched.geometry.values[cand[0]], bulk.geometry.values[cand[1]]))
                ratio = inter / np.maximum(shapely.area(unmatched.geometry.values[cand[0]]), 1e-9)
                dup_positions = set(cand[0][ratio > constants.TOPO_DUPLICATE_OVERLAP_RATIO].tolist())
                keep = np.ones(len(unmatched), dtype=bool)
                keep[list(dup_positions)] = False
                unmatched = unmatched[keep]
        extra = pd.DataFrame({
            "src_key": ["ngii:%s" % (u or "%s-%d" % (s, i)) for u, s, i in zip(unmatched["ufid"], unmatched["sheet"], unmatched.index)],
            "src_id": "", "pnu": "", "bld_nm": unmatched["ngii_name"].values, "dong_nm": "",
            "usability": "", "strct_cd": "", "grnd_flr": 0, "ugrnd_flr": 0, "height_raw": 0.0,
            "arch_area_sqm": 0.0, "total_area_sqm": 0.0, "plat_area_sqm": 0.0, "bc_rat": 0.0, "vl_rat": 0.0,
            "use_apr_day": "", "reference_date": unmatched["reference_date"].values, "data_changed_date": "",
            "ngii_kind": unmatched["ngii_kind"].values, "ngii_use": unmatched["ngii_use"].values,
            "ngii_floors": unmatched["ngii_floors"].values, "sheet": unmatched["sheet"].values,
            "source_id": TOPO_SOURCE["source_id"],
            "geometry": unmatched.geometry.values,
        })
        extra["footprint_area_sqm"] = shapely.area(extra["geometry"].values)
    elif topo is not None and len(topo):
        extra = pd.DataFrame({
            "src_key": ["ngii:%s" % (u or "%s-%d" % (s, i)) for u, s, i in zip(topo["ufid"], topo["sheet"], topo.index)],
            "src_id": "", "pnu": "", "bld_nm": topo["ngii_name"].values, "dong_nm": "", "usability": "", "strct_cd": "",
            "grnd_flr": 0, "ugrnd_flr": 0, "height_raw": 0.0, "arch_area_sqm": 0.0, "total_area_sqm": 0.0,
            "plat_area_sqm": 0.0, "bc_rat": 0.0, "vl_rat": 0.0, "use_apr_day": "", "reference_date": topo["reference_date"].values,
            "data_changed_date": "", "ngii_kind": topo["ngii_kind"].values, "ngii_use": topo["ngii_use"].values,
            "ngii_floors": topo["ngii_floors"].values, "sheet": topo["sheet"].values,
            "source_id": TOPO_SOURCE["source_id"], "geometry": topo.geometry.values,
        })
        extra["footprint_area_sqm"] = shapely.area(extra["geometry"].values)
    merged = pd.concat([bulk, extra], ignore_index=True) if extra is not None and len(extra) else bulk
    # 중복 src_key(수치지형도 UFID 결측 등)는 뒤의 것을 버린다
    merged = merged[~merged.duplicated("src_key")].reset_index(drop=True)
    return merged, matched, 0 if extra is None else len(extra)


def insert_buildings(connection, merged):
    # type: (sqlite3.Connection, object) -> dict
    """높이 규칙을 적용해 buildings에 넣는다. height_src 분포를 돌려준다."""
    geometries = np.asarray(merged["geometry"].values)
    bounds = _bounds_columns(geometries)
    geojson = _geojson_strings(geometries)
    records = merged.drop(columns=["geometry"]).to_dict("records")
    rows = []
    stats = {}
    for i, record in enumerate(records):
        decided = decide_height(record)
        stats[decided["height_src"]] = stats.get(decided["height_src"], 0) + 1
        pnu = str(record.get("pnu") or "")
        pnu_ok = len(pnu) == constants.PNU_LENGTH and pnu.isdigit()
        rows.append((
            record["src_key"], pnu if pnu_ok else None, "source" if pnu_ok else "none", None if pnu_ok else (pnu or None),
            record.get("bld_nm") or None, record.get("dong_nm") or None,
            record.get("usability") or None, record.get("strct_cd") or None,
            decided["grnd_flr"], int(record.get("ugrnd_flr") or 0), decided["flr_src"],
            decided["height_m"], decided["height_src"], decided["height_grade"], decided["attr_flag"],
            record.get("use_apr_day") or None,
            float(record.get("arch_area_sqm") or 0.0) or None, float(record.get("total_area_sqm") or 0.0) or None,
            float(record.get("plat_area_sqm") or 0.0) or None, float(record.get("bc_rat") or 0.0) or None, float(record.get("vl_rat") or 0.0) or None,
            record.get("ngii_kind") or None, record.get("ngii_use") or None, int(record.get("ngii_floors") or 0) or None,
            record.get("data_changed_date") or None,
            float(record["footprint_area_sqm"]), geojson[i], constants.DATABASE_CRS,
            record["source_id"], record.get("reference_date") or None, record.get("sheet") or None,
            float(bounds[i][0]), float(bounds[i][2]), float(bounds[i][1]), float(bounds[i][3]),
        ))
    connection.executemany(
        """INSERT INTO buildings (src_key, pnu, pnu_src, pnu_raw, bld_nm, dong_nm, usability, strct_cd,
               grnd_flr, ugrnd_flr, flr_src, height_m, height_src, height_grade, attr_flag, use_apr_day,
               arch_area_sqm, total_area_sqm, plat_area_sqm, bc_rat, vl_rat, ngii_kind, ngii_use, ngii_floors,
               data_changed_date, footprint_area_sqm, geometry_json, geometry_crs, source_id, reference_date, sheet,
               min_x, max_x, min_y, max_y)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        rows,
    )
    return stats


# ── 전체 흐름 ────────────────────────────────────────────────

def get_database_path(sido_code):
    # type: (str) -> Path
    """시도 코드 → data/<시도>_context.db."""
    return ROOT_DIR / "data" / ("%s_context.db" % constants.SIDO[sido_code][1])


def build(sheets=None, out_path=None, sheet_dir=SHEET_DIR, building_dir=BUILDING_DIR, sido_code=SEOUL_CODE):
    # type: (list, Path, Path, Path, str) -> Path
    """한 시도의 DB를 새로 만든다. sheets가 있으면 그 도엽만(건물도 그 범위만) 넣는다.

    도엽 = 시군구 묶음에서 그 시도에 배정된 것(get_sheet_sido). 묶음이 없으면(서울 개발 DB) 도엽 폴더 전부.
    건물 = 그 시도 GIS건물 전체본 + 수치지형도 보충. 경계 도엽의 수치지형도 건물은 이웃 시도 GIS건물과도 매칭해 보고
    이웃 것과 같으면 넣지 않는다(이웃 팩에 이미 있다). 서울 외 시도는 id를 시도 코드 × 10^9만큼 띄운다.
    """
    out_path = Path(out_path or get_database_path(sido_code))
    build_path = out_path.with_suffix(".building.db")
    index = read_sheet_index(sheet_dir)
    sheet_sido = get_sheet_sido(sheet_dir=sheet_dir)
    zip_paths = sorted(sheet_dir.glob("*.zip"))
    if sheet_sido:
        zip_paths = [p for p in zip_paths if sheet_sido.get(p.stem) == sido_code]
    if sheets:
        wanted = set(sheets)
        zip_paths = [p for p in zip_paths if p.stem in wanted]
        missing = wanted - {p.stem for p in zip_paths}
        if missing:
            raise FileNotFoundError("도엽 zip이 없습니다: %s" % sorted(missing))
    if not zip_paths:
        raise FileNotFoundError("수치지형도 zip이 없습니다: %s" % sheet_dir)
    building_zip = _find_building_zip(building_dir, sido_code)

    if build_path.exists():
        build_path.unlink()
    connection = _connect(build_path)
    started = time.time()
    try:
        _upsert_source(connection, TOPO_SOURCE, "")
        # 1) 도엽
        topo_buildings = []
        totals = {}
        for i, zip_path in enumerate(zip_paths, start=1):
            row = index.get(zip_path.stem)
            if not zipfile.is_zipfile(zip_path):   # 덜 받힌 묶음에서 푼 도엽 등 — 건너뛰고 끝에 경고(2026-10-12 37716060 외 7장)
                DROPPED_GEOMETRIES.append((zip_path.stem, "zip 손상", 0))
                print("도엽 %3d/%d %s — zip 손상, 건너뜀" % (i, len(zip_paths), zip_path.stem), flush=True)
                continue
            counts = load_sheet(connection, zip_path, row, topo_buildings)
            for kind, n in counts.items():
                totals[kind] = totals.get(kind, 0) + n
            _record_file(connection, TOPO_SOURCE["source_id"], zip_path, (row or {}).get("year") or None, (row or {}).get("zip_sha256"))
            connection.commit()
            print("도엽 %3d/%d %s — %s" % (i, len(zip_paths), zip_path.stem,
                                           ", ".join("%s %d" % kv for kv in sorted(counts.items()))), flush=True)
        struct_spots = reclassify_struct_spots(connection)
        print("표고점 재분류(spot_struct): %d" % struct_spots, flush=True)
        import dev_database_builder
        align = load_align_samples(connection, dev_database_builder.get_database_path(sido_code))
        connection.commit()
        print("정합 샘플(qa/align_sample): %d" % align, flush=True)
        if DROPPED_GEOMETRIES:
            print("읽지 못해 버린 도형: %s" % ", ".join("%s/%s %d" % item for item in DROPPED_GEOMETRIES), flush=True)

        # 2) 건물
        bbox = None
        if sheets or sheet_sido:
            from pyproj import Transformer
            to5186 = Transformer.from_crs("EPSG:4326", "EPSG:%d" % constants.DATABASE_CRS, always_xy=True)
            lons, lats = [], []
            for p in zip_paths:
                l, b, r, t = non_rhino_utils.get_topo_sheet_bounds(p.stem)
                lons += [l, r]
                lats += [b, t]
            xs, ys = to5186.transform(lons, lats)
            bbox = (min(xs), min(ys), max(xs), max(ys))
        print("건물 읽기: %s%s" % (building_zip.name, " (범위 한정)" if bbox else ""), flush=True)
        bulk = read_bulk_buildings(building_zip, None if sheet_sido and not sheets else bbox)
        reference_date = bulk["reference_date"].mode().iloc[0] if len(bulk) else ""
        _upsert_source(connection, BUILDING_SOURCE, reference_date)
        _record_file(connection, BUILDING_SOURCE["source_id"], building_zip, building_zip.stem.split("_")[-1])
        topo = _normalize_topo_buildings(topo_buildings)
        bulk["own"] = True
        neighbors = _read_neighbor_buildings(sido_code, bbox, building_dir) if bbox and sheet_sido else []
        for frame in neighbors:
            frame["own"] = False
        merged, matched, extra = merge_buildings(pd.concat([bulk] + neighbors, ignore_index=True) if neighbors else bulk, topo)
        merged = merged[merged["own"].fillna(True).astype(bool)].drop(columns=["own"]).reset_index(drop=True)
        if neighbors:
            print("경계 매칭용 이웃 시도 GIS건물 %d동 (넣지 않음)" % sum(len(f) for f in neighbors), flush=True)
        print("건물 GIS %d동 + 수치지형도 %d동 → 매칭 %d, 보충 %d, 합계 %d"
              % (len(bulk), 0 if topo is None else len(topo), matched, extra, len(merged)), flush=True)
        stats = insert_buildings(connection, merged)
        connection.commit()
        print("높이 출처: %s" % ", ".join("%s %d" % kv for kv in sorted(stats.items(), key=lambda kv: -kv[1])), flush=True)

        for table, limit in constants.CONTEXT_MAX_EXTENT.items():
            extent = connection.execute("SELECT MAX(MAX(max_x - min_x, max_y - min_y)) FROM %s" % table).fetchone()[0] or 0.0
            if extent > limit:
                raise RuntimeError("%s 최대 폭 %.0f m가 CONTEXT_MAX_EXTENT %.0f m를 넘는다 — bbox 질의가 객체를 놓친다. 상수를 키우세요" % (table, extent, limit))
        if sido_code != SEOUL_CODE:
            _offset_ids(connection, int(sido_code) * ID_OFFSET_PER_SIDO)
        connection.execute("ANALYZE")
        connection.commit()
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise RuntimeError("생성 DB 무결성 검사 실패: %s" % integrity)
    finally:
        connection.close()

    os.replace(build_path, out_path)
    print("완료 %.0f초 — %s (%.0f MB)" % (time.time() - started, out_path, out_path.stat().st_size / 1e6), flush=True)
    return out_path


def main():
    parser = argparse.ArgumentParser(description="시도별 컨텍스트 DB 구축 (수치지형도 1:5000 + GIS건물통합정보)")
    parser.add_argument("--sido", default=SEOUL_CODE, help="PNU 앞 2자리 시도 코드(기본 11 서울). all = 묶음에 도엽이 있는 시도 전부")
    parser.add_argument("--sheets", help="쉼표로 구분한 도엽번호. 주면 그 도엽(과 그 범위의 건물)만 넣는다")
    parser.add_argument("--out", help="결과 DB 경로 (기본 data/<시도>_context.db)")
    args = parser.parse_args()
    sheets = [s.strip() for s in args.sheets.split(",") if s.strip()] if args.sheets else None
    codes = sorted(set(get_sheet_sido().values())) if args.sido == "all" else [args.sido]
    for code in codes:
        if code not in constants.SIDO:
            parser.exit(1, "모르는 시도 코드: %s\n" % code)
        print("== %s" % constants.SIDO[code][0], flush=True)
        try:
            build(sheets=sheets, out_path=args.out, sido_code=code)
        except (FileNotFoundError, RuntimeError, ValueError) as error:
            parser.exit(1, "DB 생성 중단: %s\n" % error)


if __name__ == "__main__":
    main()
