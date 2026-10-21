"""조서·메타 — 시트 여백 5줄·CSV 5개·context.json·log.txt (docs/code_map.md §2, deliverables §C 공통·§E).

Rhino 금지, 표준 라이브러리만. 입력 `prepared`는 context_builder.Prepared지만 속성 접근만 하므로
SimpleNamespace로 대신해도 된다(테스트). 읽는 속성:
    request(dict: pnus·options) · lot_name · target_lots · near_lots(lot_db.LotInfo) · origin · origin_reused · radius · shape
    extent_ring · scales · bounds · frame_bounds · buildings(context_db.BuildingInfo) · features(FeatureInfo) · align_samples
    designations(lot_db.DesignationInfo — 대상 필지만, 없으면 빈 칸)
    sources: [{"id": lot|building|terrain|upis, "name", "date", "age_months", "level", "newer_date"}] (site_preflight.get_sources 모양)
             또는 DataSource 객체(source_id → constants.SOURCE_ID_ROLES)
    stats: {"align": {"median", "p90", "n", "low_sample", "dx", "dy"}, "mismatch_count", "height_src": {...}}
    meta: {"built_at": ISO 문자열}(없으면 지금) · warnings(panel_ui.md 경고 dict)
없는 값은 '—'로 적는다. 좌표는 전부 EPSG:5186 세계좌표 m.
"""

import csv
import datetime
import json
import os

import constants
import lot_db
import non_rhino_utils
from i18n import tr

MISSING = "—"

PARCEL_COLUMNS = ("pnu", "is_target", "address", "lot_number", "land_category", "registered_area_sqm", "geometry_area_sqm", "area_gap_sqm",
                  "zone_code", "zone_name", "zone_name_2", "legal_bcr", "legal_far", "designations", "land_use_status", "land_price_won",
                  "reference_date", "eum_url")
BUILDING_COLUMNS = ("building_id", "src_key", "pnu", "bld_nm", "usability", "strct_cd", "grnd_flr", "ugrnd_flr", "flr_src",
                    "height_m", "height_src", "height_grade", "attr_flag", "use_apr_day", "status", "ngii_kind", "ngii_use",
                    "footprint_area_sqm", "total_area_sqm", "source_id", "reference_date")
SHEET_STAT_COLUMNS = ("sheet_id", "sheet_name", "category", "count", "area_sqm", "ratio")
HEIGHT_STAT_COLUMNS = ("kind", "key", "count", "ratio")
ALIGN_COLUMNS = ("feature_id", "sheet", "x", "y", "dist_m", "dx", "dy")


# ── 작은 헬퍼 ──────────────────────────────────────────────

def _get(obj, name, default=None):
    # type: (object, str, object) -> object
    """속성 또는 dict 키. 없으면 default."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _text(value):
    # type: (object) -> str
    return MISSING if value in (None, "") else str(value)


def _bbox_of_ring(ring):
    # type: (list) -> tuple
    """[(x, y)] → (min_x, min_y, max_x, max_y). 빈 링이면 None."""
    if not ring:
        return None
    xs = [p[0] for p in ring]
    ys = [p[1] for p in ring]
    return (min(xs), min(ys), max(xs), max(ys))


def _in_bbox(item, bbox):
    # type: (object, tuple) -> bool
    """min_x/max_x/min_y/max_y를 가진 객체가 bbox와 겹치는가. bbox 없으면 전부 통과."""
    if bbox is None:
        return True
    return (_get(item, "min_x", bbox[0]) <= bbox[2] and _get(item, "max_x", bbox[2]) >= bbox[0]
            and _get(item, "min_y", bbox[1]) <= bbox[3] and _get(item, "max_y", bbox[3]) >= bbox[1])


def get_lots_in_extent(prepared):
    # type: (object) -> list
    """조서 대상 필지 = 대상지 + 범위 bbox와 겹치는 주변 필지(code_map §3 규칙 2)."""
    bbox = _bbox_of_ring(_get(prepared, "extent_ring") or [])
    return list(_get(prepared, "target_lots") or []) + [lot for lot in (_get(prepared, "near_lots") or []) if _in_bbox(lot, bbox)]


def get_buildings_in_extent(prepared):
    # type: (object) -> list
    bbox = _bbox_of_ring(_get(prepared, "extent_ring") or [])
    return [b for b in (_get(prepared, "buildings") or []) if _in_bbox(b, bbox)]


def get_sources_by_role(prepared):
    # type: (object) -> dict
    """prepared.sources → {역할: {"name", "date", "age_months", "level", "newer_date", "license"}}.
    dict(site_preflight 모양)와 DataSource 객체(source_id → SOURCE_ID_ROLES) 둘 다 받는다."""
    result = {}
    for src in _get(prepared, "sources") or []:
        role = _get(src, "id") or constants.SOURCE_ID_ROLES.get(_get(src, "source_id"))
        if not role or role == "api":
            continue
        result[role] = {"name": _get(src, "name", ""), "date": _get(src, "date") or _get(src, "reference_date") or "",
                        "age_months": _get(src, "age_months"), "level": _get(src, "level", "ok"),
                        "newer_date": _get(src, "newer_date"), "license": _get(src, "license", "")}
    return result


def get_source_dates(prepared):
    # type: (object) -> dict
    """{"lot", "building", "terrain", "upis"} → 기준일 문자열(없으면 '—'). context.json quality.dates와 같은 값."""
    by_role = get_sources_by_role(prepared)
    return {role: _text((by_role.get(role) or {}).get("date")) for role in ("lot", "building", "terrain", "upis")}


def get_sheet_codes(prepared):
    # type: (object) -> list
    """범위 안 피처가 속한 수치지형도 도엽 코드(정렬)."""
    return sorted({_get(f, "sheet") for f in (_get(prepared, "features") or []) if _get(f, "sheet")})


def _built_at(prepared):
    # type: (object) -> str
    return _get(_get(prepared, "meta") or {}, "built_at") or datetime.datetime.now().isoformat(timespec="seconds")


# ── ① ~ ⑤ 메타 5줄 ────────────────────────────────────────

def _get_abroad_meta_lines(prepared):
    # type: (object) -> list
    """Global(OSM) 메타 5줄 — OSM·지형 타일 출처와 좌표계(해외 = 지역 횡메르카토르, 한국 = EPSG:5186).
    일본은 PLATEAU 건물(도시·연도, CC BY 4.0 가공 표기)과 지리원 표고 타일을 쓴 만큼 적는다."""
    dates = get_source_dates(prepared)
    sources = {getattr(s, "source_id", ""): s for s in getattr(prepared, "sources", None) or []}
    plateau, gsi = sources.get("plateau"), "gsi_dem" in sources
    crs_name = tr("대상지 중심 횡메르카토르(GRS80, 축척 1)") if non_rhino_utils.is_local_projection() else "EPSG:5186"
    if not plateau and not gsi:
        return [
            tr("자료기준 — OpenStreetMap {0} · Terrain Tiles · {1} · 생성 {2} · {3} v{4}", dates["building"], non_rhino_utils.get_crs_label(),
               _built_at(prepared)[:10], constants.TOOL_NAME, constants.PANEL_VERSION),
            tr("출처: © OpenStreetMap contributors (ODbL 1.0, openstreetmap.org/copyright); 지형 Terrain Tiles (Mapzen·AWS Open Data, SRTM 등 공개 DEM)"),
            tr("좌표계: {0} · 지형 약 30 m 격자 — 실측·법정 자료 아님", crs_name),
            tr("정합 오차: — (필지 자료 없음)"),
            tr("건물 높이: OSM height 태그(B)·층수(C)·기본값 {0:.1f} m(D)", constants.DEFAULT_BUILDING_HEIGHT_M),
        ]
    osm = sources.get("osm")   # Overpass가 막히면 없다(osm_context.load)
    data = (["PLATEAU %s" % plateau.reference_date] if plateau else []) + (["OpenStreetMap %s" % osm.reference_date] if osm else [])
    data.append("国土地理院 標高タイル" if gsi else "Terrain Tiles")
    credits = ([tr("{0}、国土交通省 (CC BY 4.0, Gorani 가공)", plateau.name)] if plateau else []) + (
        ["© OpenStreetMap contributors (ODbL 1.0, openstreetmap.org/copyright)"] if osm else []) + [
        tr("지형 国土地理院 標高タイル (加工)") if gsi else tr("지형 Terrain Tiles (Mapzen·AWS Open Data, SRTM 등 공개 DEM)")]
    return [
        tr("자료기준 — {0} · {1} · 생성 {2} · {3} v{4}", " · ".join(data), non_rhino_utils.get_crs_label(), _built_at(prepared)[:10],
           constants.TOOL_NAME, constants.PANEL_VERSION),
        tr("출처: {0}", "; ".join(credits)),
        tr("좌표계: {0} · 지형 5 m 격자(표고 T.P.) — 실측·법정 자료 아님", crs_name) if gsi else tr("좌표계: {0} · 지형 약 30 m 격자 — 실측·법정 자료 아님", crs_name),
        tr("정합 오차: — (필지 자료 없음)"),
        tr("건물 높이: PLATEAU 실측 높이(B)·층수(C), 없는 곳은 OSM height 태그(B)·층수(C)·기본값 {0:.1f} m(D)", constants.DEFAULT_BUILDING_HEIGHT_M) if plateau
        else tr("건물 높이: OSM height 태그(B)·층수(C)·기본값 {0:.1f} m(D)", constants.DEFAULT_BUILDING_HEIGHT_M),
    ]


def get_meta_lines(prepared):
    # type: (object) -> list
    """deliverables §C 공통 ①자료기준 ②출처·라이선스 ③좌표계·정확도 ④정합 오차 ⑤기준일 경고 — 5줄.
    SVG 여백·context.json·CTX::Ref META_LINES가 모두 이 문자열을 쓴다."""
    if any(getattr(s, "source_id", "") in constants.GLOBAL_SOURCE_IDS for s in getattr(prepared, "sources", None) or []):   # Global — 한국 안이어도 출처는 OSM(ODbL 표기)
        return _get_abroad_meta_lines(prepared)
    dates = get_source_dates(prepared)
    sheets = get_sheet_codes(prepared)
    sheet_text = MISSING if not sheets else (tr("{0} 외 {1}", sheets[0], len(sheets) - 1) if len(sheets) > 1 else sheets[0])
    parts = ["%s %s" % (tr(constants.META_SOURCE_NAMES[role]), dates[role]) for role in ("lot", "building", "upis")]
    parts.append(tr("{0}(도엽 {1}, {2})", tr(constants.META_SOURCE_NAMES["terrain"]), sheet_text, dates["terrain"]))
    parts += ["EPSG:%d" % constants.DATABASE_CRS, tr("생성 {0}", _built_at(prepared)[:10]), "%s v%s" % (constants.TOOL_NAME, constants.PANEL_VERSION)]
    line1 = tr("자료기준 — {0}", " · ".join(parts))

    stats = _get(prepared, "stats") or {}
    align = _get(stats, "align") or {}
    if align.get("n"):
        line4 = tr("정합 오차 중앙값 {0:.1f} m, p90 {1:.1f} m (n={2}, 도로경계 자동 비교)", align.get("median") or 0.0, align.get("p90") or 0.0, align["n"])
        if align.get("low_sample"):
            line4 += " · " + tr("표본 부족")
    else:
        line4 = tr("정합 오차 — (측정 없음)")
    mismatch = _get(stats, "mismatch_count") or 0
    if mismatch:
        line4 += " · " + tr("지적–지형 불일치 의심 {0}건(현장 확인 대상, 레이어 qa_mismatch)", mismatch)

    stale = [w.get("detail") or w.get("text") for w in (_get(prepared, "warnings") or []) if str(w.get("code", "")).startswith("stale_")]
    line5 = " / ".join(stale) if stale else tr("기준일 경고 없음")
    return [line1, tr(constants.META_SOURCE_LINE), tr(constants.META_CRS_LINE), line4, line5]


# ── CSV 5개 ────────────────────────────────────────────────

def _write_csv(path, columns, rows):
    # type: (str, tuple, list) -> None
    """utf-8-sig(엑셀 한글) CSV. rows는 dict 목록, 없는 키는 ''."""
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(columns), extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row.get(k) is None else row.get(k)) for k in columns})


def _parcel_rows(prepared):
    """필지 조서. 법정 건폐·용적은 용도지역 1·2를 ' / '로 잇는다. 지역지구등은 대상 필지만(주변 필지는 조회하지 않는다)."""
    target_pnus = {_get(lot, "pnu") for lot in (_get(prepared, "target_lots") or [])}
    designations = _get(prepared, "designations") or []
    rows = []
    for lot in get_lots_in_extent(prepared):
        limits = [lot_db.get_legal_limits(name) for name in lot_db.get_zone_names(lot)]
        gap = lot_db.get_area_gap(lot)
        row = {k: _get(lot, k, "") for k in PARCEL_COLUMNS}
        row.update({"is_target": 1 if _get(lot, "pnu") in target_pnus else 0,
                    "registered_area_sqm": _get(lot, "registered_area", ""), "geometry_area_sqm": _get(lot, "geometry_area", ""),
                    "area_gap_sqm": "" if gap is None else round(gap, 2),
                    "legal_bcr": " / ".join(str(item[0]) for item in limits if item),
                    "legal_far": " / ".join("%d~%d" % item[1:] for item in limits if item),
                    "designations": "; ".join(item.name + (tr("(저촉)") if item.conflict == constants.LAND_USE_OVERLAP else "")
                                              for item in lot_db.get_lot_designations(lot, designations)),
                    "eum_url": constants.EUM_LAND_USE_URL % _get(lot, "pnu")})
        rows.append(row)
    return rows


def _building_rows(prepared):
    rows = []
    for b in get_buildings_in_extent(prepared):
        row = {k: _get(b, k, "") for k in BUILDING_COLUMNS}
        row.update({"footprint_area_sqm": _get(b, "footprint_area", ""), "total_area_sqm": _get(b, "total_area", "")})
        rows.append(row)
    return rows


def _floor_band(floors, breaks):
    # type: (int, tuple) -> str
    """층수 → 구간 라벨(C #8: 1/2~3/4/5~6/7~b1/b1+1~b2/b2+1+)."""
    b1, b2 = breaks
    if not floors or floors <= 0:
        return tr("미상")
    for lo, hi in ((1, 1), (2, 3), (4, 4), (5, 6), (7, b1), (b1 + 1, b2)):
        if lo <= floors <= hi:
            return str(lo) if lo == hi else "%d~%d" % (lo, hi)
    return "%d+" % (b2 + 1)


def _age_band(use_apr_day, today):
    # type: (str, datetime.date) -> str
    """사용승인일 → 노후 구간(C #9: <10 / 10~19 / 20~29 / 30+ / 연도 미상)."""
    digits = "".join(ch for ch in (use_apr_day or "") if ch.isdigit())
    if len(digits) < 4:
        return tr("연도 미상")
    years = today.year - int(digits[:4])
    b = constants.AGE_BANDS_YEARS
    if years < b[0]:
        return tr("{0}년 미만", b[0])
    for lo, hi in zip(b, b[1:]):
        if lo <= years < hi:
            return tr("{0}~{1}년", lo, hi - 1)
    return tr("{0}년 이상", b[-1])


def _group(sheet_id, sheet_name, items, key_fn, area_fn=None):
    # type: (int, str, list, object, object) -> list
    """항목을 key_fn으로 묶어 count·area·ratio 행으로. ratio는 면적이 있으면 면적 비율, 없으면 건수 비율."""
    groups = {}
    for item in items:
        key = key_fn(item) or MISSING
        count, area = groups.get(key, (0, 0.0))
        groups[key] = (count + 1, area + (float(area_fn(item) or 0.0) if area_fn else 0.0))
    total_count = sum(c for c, _ in groups.values()) or 1
    total_area = sum(a for _, a in groups.values())
    rows = []
    for key in sorted(groups):
        count, area = groups[key]
        ratio = area / total_area if total_area else count / float(total_count)
        rows.append({"sheet_id": sheet_id, "sheet_name": sheet_name, "category": key, "count": count,
                     "area_sqm": round(area, 1) if area_fn else "", "ratio": round(ratio, 4)})
    return rows


def _sheet_stat_rows(prepared, today):
    lots = get_lots_in_extent(prepared)
    buildings = get_buildings_in_extent(prepared)
    options = _get(_get(prepared, "request") or {}, "options") or {}
    breaks = tuple(options.get("floor_breaks") or constants.FLOOR_BREAKS_DEFAULT)
    sheet = dict((key, (sid, tr(name))) for sid, key, name, _en, _needs in constants.SHEET_CATALOG)
    lot_area = lambda lot: _get(lot, "registered_area") or _get(lot, "geometry_area")
    rows = []
    rows += _group(*sheet["land_use"], lots, lambda lot: _get(lot, "land_use_status"), lot_area)
    rows += _group(*sheet["land_category"], lots, lambda lot: _get(lot, "land_category"), lot_area)
    rows += _group(*sheet["zone"], lots, lambda lot: _get(lot, "zone_name"), lot_area)
    rows += _group(*sheet["use"], buildings, lambda b: (_get(b, "usability") or "")[:2])
    rows += _group(*sheet["floor"], buildings, lambda b: _floor_band(_get(b, "grnd_flr"), breaks))
    rows += _group(*sheet["age"], buildings, lambda b: _age_band(_get(b, "use_apr_day"), today))
    return rows


def get_height_src_stats(prepared):
    # type: (object) -> dict
    """범위 안 건물의 높이 출처·등급 비율 {"height_src": {src: ratio}, "height_grade": {grade: ratio}, "n": n}.
    출처는 플래그(! ? ~slope)를 뗀 기본 이름으로 묶는다."""
    buildings = get_buildings_in_extent(prepared)
    n = len(buildings) or 1
    src_counts, grade_counts = {}, {}
    for b in buildings:
        src = str(_get(b, "height_src") or MISSING).split("~")[0].rstrip("!?")
        src_counts[src] = src_counts.get(src, 0) + 1
        grade = _get(b, "height_grade") or MISSING
        grade_counts[grade] = grade_counts.get(grade, 0) + 1
    return {"height_src": {k: round(v / float(n), 4) for k, v in src_counts.items()},
            "height_grade": {k: round(v / float(n), 4) for k, v in grade_counts.items()}, "n": len(buildings)}


def _height_stat_rows(prepared):
    stats = get_height_src_stats(prepared)
    n = stats["n"]
    rows = []
    for kind in ("height_src", "height_grade"):
        for key in sorted(stats[kind]):
            rows.append({"kind": kind, "key": key, "count": int(round(stats[kind][key] * n)), "ratio": stats[kind][key]})
    return rows


def _align_rows(prepared):
    rows = []
    for s in _get(prepared, "align_samples") or []:
        coords = (_get(s, "geometry") or {}).get("coordinates") or [None, None]
        attrs = _get(s, "attrs") or {}
        rows.append({"feature_id": _get(s, "feature_id", ""), "sheet": _get(s, "sheet", ""), "x": coords[0], "y": coords[1],
                     "dist_m": _get(s, "value", ""), "dx": attrs.get("dx", ""), "dy": attrs.get("dy", "")})
    return rows


def write_tables(prepared, out_dir, today=None):
    # type: (object, str, datetime.date) -> list
    """tables/parcels.csv·buildings.csv·sheet_stats.csv·height_src_stats.csv·alignment.csv → [{name, path}]. 행이 없는 표는 쓰지 않는다
    (Global은 필지·정합이 없다 — 머리글만 있는 빈 파일을 산출물 목록에 남기지 않는다)."""
    today = today or datetime.date.today()
    tables_dir = os.path.join(out_dir, constants.RESULT_TABLES_DIRNAME)
    os.makedirs(tables_dir, exist_ok=True)
    plan = (("parcels.csv", PARCEL_COLUMNS, _parcel_rows(prepared)),
            ("buildings.csv", BUILDING_COLUMNS, _building_rows(prepared)),
            ("sheet_stats.csv", SHEET_STAT_COLUMNS, _sheet_stat_rows(prepared, today)),
            ("height_src_stats.csv", HEIGHT_STAT_COLUMNS, _height_stat_rows(prepared)),
            ("alignment.csv", ALIGN_COLUMNS, _align_rows(prepared)))
    written = []
    for name, columns, rows in plan:
        if not rows:
            continue
        path = os.path.join(tables_dir, name)
        _write_csv(path, columns, rows)
        written.append({"name": name, "path": path})
    return written


# ── context.json · log.txt ────────────────────────────────

def write_context_json(prepared, response_partial, out_dir):
    # type: (object, dict, str) -> str
    """context.json — 원점·범위·원천별 기준일/라이선스·정합·경고·counts·meta 5줄. response_partial(context·basemap·sheets·tables…)은 그대로 합친다.
    site_baker/context_baker.import_3dm이 origin을 읽어 문서 원점과 비교한다."""
    features = _get(prepared, "features") or []
    theme_counts = {}
    for f in features:
        theme_counts[_get(f, "theme")] = theme_counts.get(_get(f, "theme"), 0) + 1
    stats = _get(prepared, "stats") or {}
    frame_bounds = _get(prepared, "frame_bounds") or {}
    data = {
        "tool": constants.TOOL_NAME, "version": constants.PANEL_VERSION, "built_at": _built_at(prepared),
        "lot_name": _get(prepared, "lot_name", ""), "pnus": list((_get(prepared, "request") or {}).get("pnus") or []),
        "mode": _get(prepared, "mode", "lots"), "target": (_get(prepared, "request") or {}).get("target"),
        "lot_key": _get(prepared, "target_key", ""), "center": list(_get(prepared, "center") or []),
        "placement": _get(prepared, "placement", "origin"), "doc_origin": list(_get(prepared, "doc_origin") or _get(prepared, "origin") or []),
        "crs": non_rhino_utils.get_crs_label(),
        "origin": list(_get(prepared, "origin") or []), "origin_reused": bool(_get(prepared, "origin_reused", False)),
        "radius": _get(prepared, "radius"), "shape": _get(prepared, "shape"),
        "extent_ring": [list(p) for p in (_get(prepared, "extent_ring") or [])],
        "bounds": list(_get(prepared, "bounds") or []), "scales": list(_get(prepared, "scales") or []),
        "frame_bounds": {str(k): list(v) for k, v in frame_bounds.items()},
        "sheets": get_sheet_codes(prepared),
        "sources": get_sources_by_role(prepared), "dates": get_source_dates(prepared),
        "align": _get(stats, "align") or {}, "mismatch_count": _get(stats, "mismatch_count") or 0,
        "height_src": get_height_src_stats(prepared),
        "counts": {"buildings": len(get_buildings_in_extent(prepared)), "lots": len(get_lots_in_extent(prepared)),
                   "features": theme_counts, "align_samples": len(_get(prepared, "align_samples") or [])},
        "warnings": list(_get(prepared, "warnings") or []),
        "meta_lines": get_meta_lines(prepared),
        "options": dict((_get(prepared, "request") or {}).get("options") or {}),
    }
    data.update(response_partial or {})
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, constants.CONTEXT_META_FILE_NAME)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1, default=str)
    return path


def append_log(out_dir, lines, now=None):
    # type: (str, list, datetime.datetime) -> str
    """log.txt 끝에 구분선 + 시각 + 줄들을 덧붙인다. lines는 문자열 하나여도 된다."""
    if isinstance(lines, str):
        lines = [lines]
    now = now or datetime.datetime.now()
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, constants.RESULT_LOG_FILE_NAME)
    with open(path, "a", encoding="utf-8") as f:
        f.write("──── %s\n" % now.strftime("%Y-%m-%d %H:%M:%S"))
        for line in lines:
            f.write(str(line).rstrip("\n") + "\n")
    return path
