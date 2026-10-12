"""로컬 컨텍스트 DB(data/seoul_context.db)에서 건물·피처를 경계상자로 조회한다.

필지 DB의 lot_db.py와 같은 관행이다 — 표준 라이브러리 sqlite3만 쓰고, Rhino 안에서 import된다.
DB는 dev_context_builder.py가 만든다. 좌표는 EPSG:5186 m, 형상은 GeoJSON dict.
"""

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

import constants
import data_pack

DEFAULT_DATABASE_PATH = Path(constants.HOME_DIR) / constants.CONTEXT_DATABASE_PATH


@dataclass
class BuildingInfo:
    """건물 한 동. 높이·층수는 dev_context_builder가 §A.4 규칙으로 확정한 값이다."""

    building_id: int
    src_key: str
    pnu: str
    usability: str
    strct_cd: str
    grnd_flr: int
    ugrnd_flr: int
    flr_src: str
    height_m: float
    height_src: str
    height_grade: str
    attr_flag: str
    use_apr_day: str
    status: str
    bld_nm: str
    ngii_kind: str
    ngii_use: str
    footprint_area: float
    total_area: float
    geometry: dict
    source_id: str
    reference_date: str
    min_x: float
    max_x: float
    min_y: float
    max_y: float


@dataclass
class FeatureInfo:
    """건물 외 피처 한 건 — 등고선·표고점·도로면·수면·철도·교량·지명 등."""

    feature_id: int
    theme: str
    kind: str
    code: str
    name: str
    value: float
    attrs: dict
    sheet: str
    geometry: dict
    source_id: str
    reference_date: str
    min_x: float
    max_x: float
    min_y: float
    max_y: float


@dataclass
class DataSource:
    source_id: str
    name: str
    page_url: str
    reference_date: str
    acquired_at: str
    crs: str
    license: str
    note: str


@dataclass
class ContextData:
    """경계상자 하나의 조회 결과 묶음."""

    bounds: tuple = ()
    buildings: list = field(default_factory=list)
    features: list = field(default_factory=list)
    sources: list = field(default_factory=list)

    def get_features(self, theme=None, kind=None):
        # type: (str, str) -> list
        return [f for f in self.features
                if (theme is None or f.theme == theme) and (kind is None or f.kind == kind)]


def _open_database(database_path=None, bounds=None):
    """컨텍스트 DB 연결. database_path를 주면 그 파일(+ 옆의 `<시도>_terrain.db`), 아니면 data/의 시도별
    `*_context.db`·`*_terrain.db` 중 bounds(min_x, min_y, max_x, max_y)에 걸리는 것을 한 연결로 묶는다(data_pack.open_union).
    등고선 팩은 배포 때 따로 받는다(constants.TERRAIN_DATABASE_NAME 주석)."""
    if database_path:
        database_path = Path(database_path)
        terrain_path = database_path.with_name(database_path.name.replace("_context.db", "_terrain.db"))
        paths = [str(database_path)] if database_path.exists() else []
        if paths and terrain_path != database_path and terrain_path.exists():
            paths.append(str(terrain_path))
    else:
        paths = data_pack.get_local_paths("context", bounds) + data_pack.get_local_paths("terrain", bounds)
    if not paths:
        raise FileNotFoundError(
            "컨텍스트 DB가 없습니다: %s\npython3 scripts/dev_context_builder.py 로 만드세요" % (database_path or DEFAULT_DATABASE_PATH)
        )
    connection = data_pack.open_union(paths)
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version < constants.CONTEXT_DATABASE_SCHEMA_VERSION:
        connection.close()
        raise RuntimeError(
            "컨텍스트 DB 스키마가 v%d가 아닙니다(v%d). dev_context_builder.py로 다시 만드세요"
            % (constants.CONTEXT_DATABASE_SCHEMA_VERSION, version)
        )
    return connection


def _building_from_row(row):
    return BuildingInfo(
        building_id=int(row["building_id"]), src_key=row["src_key"], pnu=row["pnu"] or "",
        usability=row["usability"] or "", strct_cd=row["strct_cd"] or "",
        grnd_flr=int(row["grnd_flr"] or 0), ugrnd_flr=int(row["ugrnd_flr"] or 0), flr_src=row["flr_src"] or "",
        height_m=float(row["height_m"]), height_src=row["height_src"], height_grade=row["height_grade"],
        attr_flag=row["attr_flag"] or "", use_apr_day=row["use_apr_day"] or "", status=row["status"],
        bld_nm=row["bld_nm"] or "", ngii_kind=row["ngii_kind"] or "", ngii_use=row["ngii_use"] or "",
        footprint_area=float(row["footprint_area_sqm"]), total_area=float(row["total_area_sqm"] or 0.0),
        geometry=json.loads(row["geometry_json"]), source_id=row["source_id"],
        reference_date=row["reference_date"] or "",
        min_x=float(row["min_x"]), max_x=float(row["max_x"]), min_y=float(row["min_y"]), max_y=float(row["max_y"]),
    )


def _feature_from_row(row):
    return FeatureInfo(
        feature_id=int(row["feature_id"]), theme=row["theme"], kind=row["kind"], code=row["code"] or "",
        name=row["name"] or "", value=row["value"],
        attrs=json.loads(row["attrs_json"]) if row["attrs_json"] else {}, sheet=row["sheet"] or "",
        geometry=json.loads(row["geometry_json"]), source_id=row["source_id"],
        reference_date=row["reference_date"] or "",
        min_x=float(row["min_x"]), max_x=float(row["max_x"]), min_y=float(row["min_y"]), max_y=float(row["max_y"]),
    )


# min_x 하한(min_x ≥ 질의 min_x − 최대 폭)을 같이 걸어야 B-tree 인덱스가 좁은 범위만 훑는다.
# 하한이 없으면 'min_x ≤ 질의 max_x'가 서울 서쪽 절반을 다 읽는다(건물 0.84 s → 0.02 s, 2026-10-08 실측).
_BBOX_SQL = " WHERE min_x BETWEEN ? AND ? AND max_x >= ? AND min_y <= ? AND max_y >= ?"


def _bbox_values(bounds, table):
    # type: (tuple, str) -> tuple
    """bounds = (min_x, min_y, max_x, max_y) → 경계상자 교차 조건 값. table의 최대 폭(CONTEXT_MAX_EXTENT)으로 min_x 하한을 둔다."""
    min_x, min_y, max_x, max_y = [float(v) for v in bounds]
    return (min_x - constants.CONTEXT_MAX_EXTENT[table], max_x, min_x, max_y, min_y)


def load_buildings_in_bounds(bounds, database_path=None, include_demolished=False, include_minor=False):
    # type: (tuple, object, bool, bool) -> list
    """경계상자(EPSG:5186 m)와 겹치는 건물. 철거 건물은 기본 제외.

    ``include_minor=False``면 보충(src_key 'ngii:…') 행 중 무벽건물·가건물·공사중건물을 뺀다.
    대장과 매칭된 벌크 건물은 ngii_kind와 무관하게 남긴다.
    """
    connection = _open_database(database_path, bounds)
    try:
        sql = "SELECT * FROM buildings" + _BBOX_SQL
        values = list(_bbox_values(bounds, "buildings"))
        if not include_demolished:
            sql += " AND status = 'active'"
        if not include_minor:
            sql += " AND NOT (src_key LIKE 'ngii:%%' AND ngii_kind IN (%s))" % ",".join("?" for _ in constants.TOPO_MINOR_KINDS)
            values.extend(constants.TOPO_MINOR_KINDS)
        rows = connection.execute(sql, values).fetchall()
    finally:
        connection.close()
    return [_building_from_row(row) for row in rows]


def load_features_in_bounds(bounds, themes=None, kinds=None, database_path=None):
    # type: (tuple, tuple, tuple, object) -> list
    """경계상자와 겹치는 피처. themes·kinds로 거른다(None이면 전부)."""
    filters, values = [], list(_bbox_values(bounds, "features"))
    if themes:
        filters.append("theme IN (%s)" % ",".join("?" for _ in themes))
        values.extend(themes)
    if kinds:
        filters.append("kind IN (%s)" % ",".join("?" for _ in kinds))
        values.extend(kinds)
    sql = "SELECT * FROM features" + _BBOX_SQL + ("".join(" AND " + f for f in filters))
    connection = _open_database(database_path, bounds)
    try:
        rows = connection.execute(sql, values).fetchall()
    finally:
        connection.close()
    return [_feature_from_row(row) for row in rows]


def load_sources(database_path=None):
    # type: (object) -> list
    connection = _open_database(database_path)
    try:
        rows = connection.execute("SELECT * FROM data_sources GROUP BY source_id ORDER BY source_id").fetchall()
    finally:
        connection.close()
    return [DataSource(**dict(row)) for row in rows]


def load(bounds, themes=None, database_path=None, include_minor=False):
    # type: (tuple, tuple, object, bool) -> ContextData
    """경계상자 하나의 건물·피처·출처를 한 번에 묶어 돌려준다."""
    return ContextData(
        bounds=tuple(float(v) for v in bounds),
        buildings=load_buildings_in_bounds(bounds, database_path, include_minor=include_minor),
        features=load_features_in_bounds(bounds, themes, None, database_path),
        sources=load_sources(database_path),
    )


def count_in_bounds(bounds, database_path=None, include_minor=False):
    # type: (tuple, object, bool) -> dict
    """경계상자 안 건물 수와 theme별 피처 수. 형상을 읽지 않는다(사전 점검 예상치·빈 시트 판정용).
    건물 필터는 load_buildings_in_bounds와 같다(철거 제외·보충 행의 무벽·가건물·공사중 제외) — preflight 예상치 = prepare 실제 수."""
    values = _bbox_values(bounds, "buildings")
    sql = "SELECT COUNT(*) FROM buildings" + _BBOX_SQL + " AND status = 'active'"
    bld_values = list(values)
    if not include_minor:
        sql += " AND NOT (src_key LIKE 'ngii:%%' AND ngii_kind IN (%s))" % ",".join("?" for _ in constants.TOPO_MINOR_KINDS)
        bld_values.extend(constants.TOPO_MINOR_KINDS)
    connection = _open_database(database_path, bounds)
    try:
        buildings = connection.execute(sql, bld_values).fetchone()[0]
        themes = {
            row[0]: int(row[1])
            for row in connection.execute("SELECT theme, COUNT(*) FROM features" + _BBOX_SQL + " GROUP BY theme", _bbox_values(bounds, "features"))
        }
    finally:
        connection.close()
    return {"buildings": int(buildings), "themes": themes}


def load_sheet_codes(database_path=None):
    # type: (object) -> dict
    """적재된 수치지형도 도엽 → 기준일(제작연도, 없으면 적재일) dict. source_files에서 읽어 빠르다."""
    connection = _open_database(database_path)
    try:
        rows = connection.execute(
            "SELECT file_name, listed_date, loaded_at FROM source_files WHERE source_id = 'ngii_topo_5000'").fetchall()
    finally:
        connection.close()
    return {row[0].rsplit(".", 1)[0]: (row[1] or (row[2] or "")[:10]) for row in rows}


def get_counts(database_path=None):
    # type: (object) -> dict
    """건물 수와 theme/kind별 피처 수. 패널의 데이터 상태 표시와 QA에 쓴다."""
    connection = _open_database(database_path)
    try:
        buildings = connection.execute("SELECT COUNT(*) FROM buildings").fetchone()[0]
        features = {
            "%s/%s" % (row[0], row[1]): int(row[2])
            for row in connection.execute("SELECT theme, kind, COUNT(*) FROM features GROUP BY 1, 2")
        }
        sheets = connection.execute("SELECT COUNT(DISTINCT sheet) FROM features").fetchone()[0]
    finally:
        connection.close()
    return {"buildings": int(buildings), "features": features, "sheets": int(sheets)}
