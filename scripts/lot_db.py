"""로컬 SQLite에서 필지와 계획 오버레이를 조회한다.

계획 오버레이는 용도지역·용도지구·용도구역·도시계획시설·지구단위계획을 뜻하며
`overlays` 테이블 한 곳에 있다. 원천과 수집 방법은 docs/database.md를 본다.
PNU 하나가 필지(lot) 하나에 대응한다. 여러 필지를 합필한 대상지는 LotData로 묶는다.
DB의 EPSG:5186 좌표·경계값은 m, 계산면적은 ㎡로 다룬다.
기존 SQLite 물리 스키마의 `parcels`, `parcel_*`는 DB 호환을 위해 그대로 쓴다.
"""

import json
import re
import sqlite3
from dataclasses import asdict, dataclass, field
from pathlib import Path

import constants
import data_pack

HOME_DIR = Path(constants.HOME_DIR)
DEFAULT_DATABASE_PATH = HOME_DIR / constants.DATABASE_PATH
_PNU_PATTERN = re.compile(r"^\d{%d}$" % constants.PNU_LENGTH)


@dataclass
class LotInfo:
    """한 필지의 DB 정보. 좌표·경계값은 m, 면적은 ㎡다."""

    lot_id: int
    pnu: str
    address: str
    lot_number: str
    land_category: str
    registered_area: float
    geometry_area: float
    geometry: dict
    geometry_crs: int
    source_id: str
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    # 토지특성정보 대장 속성. 정북일조는 정북방향 인접대지의 용도지역을 봐야
    # 하므로(시행령 제86조2항3호) 주변 필지도 zone_code를 그대로 갖는다.
    zone_code: str = ""
    zone_name: str = ""
    zone_code_2: str = ""
    zone_name_2: str = ""
    land_use_status: str = ""
    terrain_height: str = ""
    terrain_shape: str = ""
    road_contact: str = ""
    land_price_won: float = None
    reference_date: str = ""

    @property
    def area(self):
        """대지면적 기준값. 건축법은 등록면적을 쓰고, 없으면 도형 계산면적."""
        return float(self.registered_area or self.geometry_area)


@dataclass
class OverlayInfo:
    """필지에 겹치는 계획정보 한 건.

    용도지역·용도지구·용도구역·도시계획시설·지구단위계획을 같은 모양으로 다룬다.
    ``theme``으로 대분류를, ``kind``로 세부 종별을 구분한다. 면적은 ㎡다.
    """

    pnu: str
    overlay_id: int
    theme: str
    layer: str
    kind: str
    code: str
    name: str
    feature_id: str
    notice_number: str
    created_date: str
    area: float
    overlap_area: float
    overlap_ratio: float
    source_id: str
    attrs: dict = field(default_factory=dict)
    geometry: dict = field(default_factory=dict, repr=False)

    @property
    def road_grade(self):
        """도시계획시설 도로의 등급명. 도로가 아니면 빈 문자열."""
        return constants.ROAD_GRADE_WIDTHS.get(self.code, ("", None, None))[0]

    @property
    def road_width_range(self):
        """도로 결정 폭원 구간 (최소 m, 최대 m). 실측 폭이 아니다."""
        return constants.ROAD_GRADE_WIDTHS.get(self.code, ("", None, None))[1:]


@dataclass
class DesignationInfo:
    """토지이용계획정보의 지역지구등 지정 한 건.

    토지이음의 "지역지구등 지정여부"와 같은 원천이다. 도형 없이 필지 단위 속성이라
    공간교차가 필요 없다. ``conflict``는 포함·저촉·접함 중 하나다.
    """

    pnu: str
    code: str
    name: str
    conflict: str

    @property
    def applied(self):
        """이 지정이 대지에 실제로 걸리는지. 접함은 인접일 뿐이라 제외한다."""
        return self.conflict in constants.LAND_USE_APPLIED


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
class LotData:
    pnus: list = field(default_factory=list)
    lots: list = field(default_factory=list)
    overlays: list = field(default_factory=list)
    designations: list = field(default_factory=list)
    sources: list = field(default_factory=list)

    @property
    def applied_designations(self):
        """대지에 실제로 걸리는 지역지구등만 추린다. 접함은 뺀다."""
        return [item for item in self.designations if item.applied]

    @property
    def land_uses(self):
        """용도지역 오버레이만 추린다."""
        return self.get_overlays(theme=constants.OVERLAY_THEME_ZONE)

    @property
    def district_plans(self):
        """지구단위계획 오버레이만 추린다."""
        return self.get_overlays(theme=constants.OVERLAY_THEME_PLAN)

    def get_overlays(self, theme=None, kind=None):
        # type: (str, str) -> list
        """theme·kind로 오버레이를 걸러 낸다. 둘 다 None이면 전부 반환한다."""
        return [
            overlay
            for overlay in self.overlays
            if (theme is None or overlay.theme == theme)
            and (kind is None or overlay.kind == kind)
        ]

    def to_dict(self):
        return asdict(self)

    def to_json(self):
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def metadata_json(self):
        """저장·리포트용 JSON을 만든다. 형상은 제외한다."""
        data = self.to_dict()
        for lot in data["lots"]:
            lot.pop("geometry", None)
        return json.dumps(data, ensure_ascii=False, indent=2)


def _normalize_pnus(pnus):
    if isinstance(pnus, str):
        pnus = [pnus]
    normalized = [str(pnu).strip() for pnu in (pnus or [])]
    invalid = [pnu for pnu in normalized if not _PNU_PATTERN.fullmatch(pnu)]
    if invalid:
        raise ValueError(
            "PNU는 %d자리 숫자여야 합니다: %s" % (constants.PNU_LENGTH, invalid)
        )
    if not normalized:
        raise ValueError("PNU가 하나 이상 필요합니다")
    return list(dict.fromkeys(normalized))


def _open_database(database_path=None, bounds=None, pnus=None):
    """필지 DB 연결. database_path를 주면 그 파일 하나, 아니면 data/의 시도별 `*_site.db` 중
    bounds(min_x, min_y, max_x, max_y)에 걸리거나 pnus의 시도에 해당하는 것을 한 연결로 묶는다(data_pack.open_union)."""
    if database_path:
        paths = [str(database_path)] if Path(database_path).exists() else []
    else:
        paths = data_pack.get_local_paths("site", bounds, {pnu[:2] for pnu in pnus} if pnus else None,
                                          sgg_codes={pnu[:5] for pnu in pnus} if pnus else None)
    if not paths:
        raise FileNotFoundError("로컬 DB가 없습니다: %s" % (database_path or DEFAULT_DATABASE_PATH))
    return data_pack.open_databases(paths)


def _get_lots_bounds(lots, margin):
    # type: (list, float) -> tuple
    """필지 목록의 경계상자 + 여유 m → (min_x, min_y, max_x, max_y)."""
    return (min(lot.min_x for lot in lots) - margin, min(lot.min_y for lot in lots) - margin,
            max(lot.max_x for lot in lots) + margin, max(lot.max_y for lot in lots) + margin)


def _lot_info_from_row(row):
    return LotInfo(
        lot_id=int(row["parcel_id"]),
        pnu=row["pnu"],
        address=row["address"] or "",
        lot_number=row["lot_number"] or "",
        land_category=row["land_category"] or "",
        registered_area=row["registered_area_sqm"],
        geometry_area=float(row["geometry_area_sqm"]),
        zone_code=row["zone_code"] or "",
        zone_name=row["zone_name"] or "",
        zone_code_2=row["zone_code_2"] or "",
        zone_name_2=row["zone_name_2"] or "",
        land_use_status=row["land_use_status"] or "",
        terrain_height=row["terrain_height"] or "",
        terrain_shape=row["terrain_shape"] or "",
        road_contact=row["road_contact"] or "",
        land_price_won=row["land_price_won"],
        reference_date=row["reference_date"] or "",
        geometry=json.loads(row["geometry_json"]),
        geometry_crs=int(row["geometry_crs"]),
        source_id=row["source_id"],
        min_x=float(row["min_x"]),
        max_x=float(row["max_x"]),
        min_y=float(row["min_y"]),
        max_y=float(row["max_y"]),
    )


def _overlay_info_from_row(row):
    return OverlayInfo(
        pnu=row["pnu"],
        overlay_id=int(row["overlay_id"]),
        theme=row["theme"],
        layer=row["layer"],
        kind=row["kind"],
        code=row["code"] or "",
        name=row["name"] or "",
        feature_id=row["feature_id"] or "",
        notice_number=row["notice_number"] or "",
        created_date=row["created_date"] or "",
        area=float(row["area_sqm"]),
        overlap_area=float(row["overlap_area_sqm"]),
        overlap_ratio=float(row["overlap_ratio"]),
        source_id=row["source_id"],
        attrs=json.loads(row["attrs_json"]) if row["attrs_json"] else {},
        geometry=json.loads(row["geometry_json"]),
    )


def load(pnus, database_path=None):
    """PNU 목록을 조회하여 하나의 LotData로 반환한다."""
    pnus = _normalize_pnus(pnus)
    connection = _open_database(database_path, pnus=pnus)
    placeholders = ",".join("?" for _ in pnus)
    try:
        _require_bbox_index(connection)
        lot_rows = connection.execute(
            "SELECT * FROM parcels WHERE pnu IN (%s)" % placeholders, pnus
        ).fetchall()
        found_pnus = {row["pnu"] for row in lot_rows}
        missing_pnus = [pnu for pnu in pnus if pnu not in found_pnus]
        if missing_pnus:
            raise KeyError("DB에 없는 PNU: %s" % missing_pnus)

        lot_by_pnu = {row["pnu"]: row for row in lot_rows}
        lots = [_lot_info_from_row(lot_by_pnu[pnu]) for pnu in pnus]

        overlay_rows = connection.execute(
            """
            SELECT link.pnu, overlay.overlay_id, overlay.theme, overlay.layer,
                   overlay.kind, overlay.code, overlay.name, overlay.feature_id,
                   overlay.notice_number, overlay.created_date,
                   overlay.area_sqm, overlay.attrs_json, overlay.geometry_json,
                   link.overlap_area_sqm, link.overlap_ratio, overlay.source_id
            FROM parcel_overlays link
            JOIN overlays overlay ON overlay.overlay_id = link.overlay_id
            WHERE link.pnu IN (%s)
            ORDER BY link.pnu, overlay.theme, link.overlap_ratio DESC
            """ % placeholders,
            pnus,
        ).fetchall()
        # 시군구 팩은 경계에 걸친 계획 도형을 양쪽에 넣는다 — 같은 (필지, 도형)은 한 번만
        overlay_rows = list({(row["pnu"], row["overlay_id"]): row for row in overlay_rows}.values())
        overlays = [_overlay_info_from_row(row) for row in overlay_rows]

        designation_rows = connection.execute(
            """
            SELECT pnu, code, name, conflict FROM parcel_land_use
            WHERE pnu IN (%s)
            ORDER BY pnu, conflict, name
            """ % placeholders,
            pnus,
        ).fetchall()
        designations = [DesignationInfo(pnu=pnu, code=code, name=name, conflict=conflict)
                        for pnu, code, name, conflict in dict.fromkeys(tuple(row) for row in designation_rows)]

        source_rows = connection.execute(
            "SELECT * FROM data_sources GROUP BY source_id ORDER BY source_id"
        ).fetchall()
        sources = list({row["source_id"]: DataSource(**dict(row)) for row in source_rows}.values())
    finally:
        connection.close()

    return LotData(
        pnus=pnus,
        lots=lots,
        overlays=overlays,
        designations=designations,
        sources=sources,
    )


def _require_bbox_index(connection):
    """150m 조회에 필요한 DB 스키마와 경계상자 인덱스를 확인한다."""
    schema_version = connection.execute("PRAGMA user_version").fetchone()[0]
    lot_columns = {
        row[1] for row in connection.execute("PRAGMA table_info(parcels)").fetchall()
    }
    required_columns = {"parcel_id", "min_x", "max_x", "min_y", "max_y"}
    overlay_table = connection.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type = 'table' AND name = 'overlays'
        """
    ).fetchone()
    if (
        schema_version < constants.DATABASE_SCHEMA_VERSION
        or overlay_table is None
        or not required_columns.issubset(lot_columns)
    ):
        raise RuntimeError(
            "현재 로컬 DB가 스키마 v%d가 아닙니다(필지 경계상자·계획 오버레이). "
            "dev_database_builder.py로 DB를 다시 구축하세요"
            % constants.DATABASE_SCHEMA_VERSION
        )

    # RTree는 SQLite 빌드에 따라 없다(Rhino 8 Windows CPython). 경계상자 컬럼에
    # 일반 인덱스를 걸면 같은 결과를 얻는다. 다른 PC로 복사해 온 DB에 인덱스가
    # 없으면 여기서 한 번 만든다(서울 전체 약 1초).
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_parcels_bbox
            ON parcels(min_x, max_x, min_y, max_y);
        CREATE INDEX IF NOT EXISTS idx_overlays_bbox
            ON overlays(min_x, max_x, min_y, max_y);
        """
    )


def load_near_lot_candidates(
    target_lots,
    radius=None,
    database_path=None,
):
    """경계상자 인덱스로 대상 경계상자에서 지정 거리 안의 필지 후보를 조회한다."""
    radius = (
        float(constants.LOT_CONTEXT_RADIUS)
        if radius is None
        else float(radius)
    )
    if radius <= 0:
        raise ValueError("주변 필지 조회 거리는 0보다 커야 합니다")
    if not target_lots:
        return []

    target_pnus = {lot.pnu for lot in target_lots}
    candidates_by_pnu = {}
    connection = _open_database(database_path, _get_lots_bounds(target_lots, radius))
    try:
        _require_bbox_index(connection)
        for target in target_lots:
            rows = connection.execute(
                """
                SELECT lot.*
                FROM parcels lot
                WHERE lot.min_x <= ?
                  AND lot.max_x >= ?
                  AND lot.min_y <= ?
                  AND lot.max_y >= ?
                """,
                (
                    target.max_x + radius,
                    target.min_x - radius,
                    target.max_y + radius,
                    target.min_y - radius,
                ),
            ).fetchall()
            for row in rows:
                if row["pnu"] not in target_pnus:
                    candidates_by_pnu[row["pnu"]] = row
    finally:
        connection.close()

    return [
        _lot_info_from_row(candidates_by_pnu[pnu])
        for pnu in sorted(candidates_by_pnu)
    ]


def load_near_overlays(
    target_lots,
    radius=None,
    themes=None,
    kinds=None,
    database_path=None,
):
    # type: (list, float, tuple, tuple, object) -> list
    """대상 필지 주변의 계획 오버레이를 도형째 조회한다.

    입력:
        target_lots: LotInfo 목록. radius: 경계상자 확장 거리 m.
        themes: 걸러 낼 theme 튜플. kinds: 걸러 낼 kind 튜플. None이면 전부.
        database_path: DB 경로 override.
    처리:
        경계상자 인덱스로 후보를 좁힌다. 도로 오버레이는 가로 전체로 길쭉해
        경계상자가 넓게 잡히므로 실제 거리는 소비자 쪽에서 다시 걸러야 한다.
        필지에 겹치지 않아도 반환한다 — 시행령 제86조6항은 "대지 사이에" 있는
        도로·공원을 보기 때문이다.
    출력:
        OverlayInfo 목록. pnu는 빈 문자열이고 overlap 값은 0이다.
    """
    radius = (
        float(constants.LOT_CONTEXT_RADIUS)
        if radius is None
        else float(radius)
    )
    if radius <= 0:
        raise ValueError("주변 오버레이 조회 거리는 0보다 커야 합니다")
    if not target_lots:
        return []

    filters, values = [], []
    if themes:
        filters.append(
            "overlay.theme IN (%s)" % ",".join("?" for _ in themes)
        )
        values.extend(themes)
    if kinds:
        filters.append("overlay.kind IN (%s)" % ",".join("?" for _ in kinds))
        values.extend(kinds)
    filter_sql = (" AND " + " AND ".join(filters)) if filters else ""

    rows_by_id = {}
    connection = _open_database(database_path, _get_lots_bounds(target_lots, radius))
    try:
        _require_bbox_index(connection)
        for target in target_lots:
            rows = connection.execute(
                """
                SELECT '' AS pnu, overlay.overlay_id, overlay.theme,
                       overlay.layer, overlay.kind, overlay.code, overlay.name,
                       overlay.feature_id, overlay.notice_number,
                       overlay.created_date, overlay.area_sqm,
                       overlay.attrs_json, overlay.geometry_json,
                       0.0 AS overlap_area_sqm, 0.0 AS overlap_ratio,
                       overlay.source_id
                FROM overlays overlay
                WHERE overlay.min_x <= ? AND overlay.max_x >= ?
                  AND overlay.min_y <= ? AND overlay.max_y >= ?
                """ + filter_sql,
                [
                    target.max_x + radius,
                    target.min_x - radius,
                    target.max_y + radius,
                    target.min_y - radius,
                ] + values,
            ).fetchall()
            for row in rows:
                rows_by_id[int(row["overlay_id"])] = row
    finally:
        connection.close()

    return [
        _overlay_info_from_row(rows_by_id[overlay_id])
        for overlay_id in sorted(rows_by_id)
    ]


def load_parcels_in_bounds(
    min_x,
    min_y,
    max_x,
    max_y,
    limit=5000,
    database_path=None,
):
    # type: (float, float, float, float, int, object) -> tuple
    """경계상자(EPSG:5186 m)와 겹치는 필지를 가벼운 순서로 조회한다.

    지도 뷰포트 채우기용이라 정렬 없이 LIMIT+1건을 읽어 초과 여부만 본다.
    ``limit=None``이면 전부 읽는다(컨텍스트 생성 — 1 km bbox 8,918필지 0.34 s).
    출력: ``(list[LotInfo], truncated)``.
    """
    connection = _open_database(database_path, (min_x, min_y, max_x, max_y))
    try:
        _require_bbox_index(connection)
        sql = """
            SELECT * FROM parcels
            WHERE min_x <= ? AND max_x >= ?
              AND min_y <= ? AND max_y >= ?
            """
        values = [float(max_x), float(min_x), float(max_y), float(min_y)]
        if limit is not None:
            sql += " LIMIT ? + 1"
            values.append(int(limit))
        rows = connection.execute(sql, values).fetchall()
    finally:
        connection.close()

    if limit is None:
        return [_lot_info_from_row(row) for row in rows], False
    truncated = len(rows) > int(limit)
    return [_lot_info_from_row(row) for row in rows[: int(limit)]], truncated


def load_sources(database_path=None):
    # type: (object) -> list
    """필지 DB의 원천 목록만 읽는다(형상 없음). 패널 자료 상태용."""
    connection = _open_database(database_path)
    try:
        rows = connection.execute("SELECT * FROM data_sources GROUP BY source_id ORDER BY source_id").fetchall()
    finally:
        connection.close()
    return list({row["source_id"]: DataSource(**dict(row)) for row in rows}.values())


def count_parcels_in_bounds(min_x, min_y, max_x, max_y, database_path=None):
    # type: (float, float, float, float, object) -> int
    """경계상자(EPSG:5186 m)와 겹치는 필지 수. 형상을 읽지 않아 빠르다(사전 점검 예상치용)."""
    connection = _open_database(database_path, (min_x, min_y, max_x, max_y))
    try:
        _require_bbox_index(connection)
        return sum(int(row[0]) for row in connection.execute(   # 묶음마다 한 줄(data_pack._Connections)
            "SELECT COUNT(*) FROM parcels WHERE min_x <= ? AND max_x >= ? AND min_y <= ? AND max_y >= ?",
            (float(max_x), float(min_x), float(max_y), float(min_y)),
        ).fetchall())
    finally:
        connection.close()


# ═════════════════════════════════════════════════════════
# 주소/PNU 해석 — 패널 입력용
# ═════════════════════════════════════════════════════════
