"""해외 대상지 컨텍스트 — OSM(Overpass API) 건물·도로·철도·수계·녹지 + AWS Terrain Tiles 지형을 context_db와 같은 형식으로.

국내는 로컬 DB(context_db)를 쓰고, 대상지가 한국 밖이면(non_rhino_utils.is_local_projection) context_builder가 이 모듈을 부른다.
좌표는 non_rhino_utils의 지금 투영(대상지 중심 지역 횡메르카토르) m. 표준 라이브러리만 쓴다(urllib·json·zlib·sqlite3).
일본은 받아 둔 PLATEAU 건물 팩(jp<시구정촌코드>_context.db — cmd_site가 생성 직전에 받는다)을 먼저 쓰고 OSM 건물은 그와 겹치지 않는
것만 보탠다. 지형은 국토지리원(GSI) 5 m 표고 타일. 근거 docs/research/japan.md.

출처 표기: 건물·도로 등 "© OpenStreetMap contributors"(ODbL — 산출물은 출처 표기만, DB로 재배포하지 않는다),
지형 "Terrain Tiles, Mapzen/AWS Open Data(SRTM·GMTED 등 공개 DEM)", 일본 건물 "3D都市モデル（Project PLATEAU）<도시>（<연도>年度）"
(CC BY 4.0), 일본 지형 "国土地理院 標高タイル".
"""

import json
import sqlite3
import math
import re
import struct
import urllib.error
import urllib.parse
import urllib.request
import zlib

import constants
import context_db
import data_pack
import non_rhino_utils
from context_db import BuildingInfo, ContextData, DataSource, FeatureInfo
from i18n import tr

_CACHE = {}   # (질의 종류, bbox) → 응답 — 같은 대상지를 다시 생성할 때 Overpass를 또 부르지 않는다. OSM_CACHE_MAX를 넘으면 비운다(_keep)


# ── 받기 ────────────────────────────────────────────────

def _get_lnglat_bbox(bounds):
    # type: (tuple) -> tuple
    """TM bounds(min_x, min_y, max_x, max_y) → (south, west, north, east) 경위도."""
    corners = [non_rhino_utils.get_wgs84_from_tm(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])]
    return (min(c[1] for c in corners), min(c[0] for c in corners), max(c[1] for c in corners), max(c[0] for c in corners))


def get_lnglat_bounds(bounds):
    # type: (tuple) -> tuple
    """TM bounds → (서, 남, 동, 북) 경위도 — 일본 건물 팩 범위(매니페스트·packs.json bounds)와 같은 순서."""
    south, west, north, east = _get_lnglat_bbox(bounds)
    return west, south, east, north


def get_country(lng, lat):
    # type: (float, float) -> str
    """경위도가 나라별 건물 팩(constants.COUNTRY_PACKS) 상자 안이면 그 나라 코드, 아니면 "". 상자가 겹치면(프랑스 상자 안의 스위스) 작은 상자가 이긴다."""
    found = []
    for code, pack in constants.COUNTRY_PACKS.items():
        west, south, east, north = pack["bounds"]
        if west <= lng <= east and south <= lat <= north:
            found.append(((east - west) * (north - south), code))
    return min(found)[1] if found else ""


def is_japan(lng, lat):
    # type: (float, float) -> bool
    """경위도가 일본인지(대략) — 지리원 지형 타일을 먼저 받을지. 일본 상자 안이고 한국(non_rhino_utils.is_korea — 북규슈·쓰시마는 뺀다)이 아니면.
    틀려도 지리원 타일이 404라 AWS 타일로 돌아간다."""
    west, south, east, north = constants.JP_BOUNDS
    return west <= lng <= east and south <= lat <= north and not non_rhino_utils.is_korea(lng, lat)


def _fetch(url, data=None):
    # type: (str, bytes) -> bytes
    request = urllib.request.Request(url, data=data, headers={"User-Agent": constants.OSM_USER_AGENT})
    with urllib.request.urlopen(request, timeout=constants.OSM_TIMEOUT_SECONDS) as response:
        return response.read()


def _keep(key, value):
    # type: (tuple, object) -> object
    """응답 하나를 캐시에 넣고 돌려준다. 항목이 OSM_CACHE_MAX를 넘으면 먼저 비운다 — 긴 Blender 세션에서 Overpass 응답(대상지마다 수십 MB)이 쌓이지 않게."""
    if len(_CACHE) >= constants.OSM_CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = value
    return value


def get_overpass_elements(bounds, query=None, endpoints=None):
    # type: (tuple, str, tuple) -> list
    """bounds 안 OSM 요소(out geom). query = Overpass 질의 틀({bbox} 자리, 기본 constants.OSM_OVERPASS_QUERY), endpoints = 미러(기본 전부).
    미러를 차례로 시도한다. 실패하면 RuntimeError."""
    bbox = "%.6f,%.6f,%.6f,%.6f" % _get_lnglat_bbox(bounds)
    query = (query or constants.OSM_OVERPASS_QUERY).replace("{bbox}", bbox)
    key = ("overpass", query)
    if key in _CACHE:
        return _CACHE[key]
    errors = []
    for endpoint in endpoints or constants.OSM_OVERPASS_URLS:
        try:
            body = _fetch(endpoint, urllib.parse.urlencode({"data": query}).encode("utf-8"))
            return _keep(key, json.loads(body.decode("utf-8"))["elements"])
        except Exception as error:   # 미러 하나가 막혀도 다음 것을 쓴다
            errors.append("%s: %s" % (endpoint, error))
    raise RuntimeError(tr("OSM(Overpass) 데이터를 받지 못했습니다. 인터넷 연결을 확인하세요") + "\n" + "\n".join(errors))


# ── 도형 ────────────────────────────────────────────────

def _get_tm_line(geometry):
    # type: (list) -> list
    return [non_rhino_utils.get_tm_from_wgs84(p["lon"], p["lat"]) for p in geometry if p]


def _get_rings_from_ways(ways):
    # type: (list) -> list
    """관계 멤버 웨이(좌표 목록)들을 끝점끼리 이어 닫힌 링들로. 닫히지 않는 조각은 버린다(예외 형상 원칙)."""
    pending = [list(w) for w in ways if len(w) >= 2]
    rings = []
    while pending:
        ring = pending.pop()
        changed = True
        while ring[0] != ring[-1] and changed:
            changed = False
            for i, way in enumerate(pending):
                if way[0] == ring[-1]:
                    ring += way[1:]
                elif way[-1] == ring[-1]:
                    ring += way[-2::-1]
                elif way[-1] == ring[0]:
                    ring = way[:-1] + ring
                elif way[0] == ring[0]:
                    ring = way[:0:-1] + ring
                else:
                    continue
                pending.pop(i)
                changed = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def _get_polygon(element):
    # type: (dict) -> dict
    """웨이·멀티폴리곤 관계 → TM GeoJSON (Multi)Polygon. 못 만들면 None."""
    if element["type"] == "way":
        line = _get_tm_line(element.get("geometry") or [])
        if len(line) < 4 or line[0] != line[-1]:
            return None
        return {"type": "Polygon", "coordinates": [line]}
    outers = _get_rings_from_ways([_get_tm_line(m.get("geometry") or []) for m in element.get("members", []) if m.get("role") == "outer"])
    inners = _get_rings_from_ways([_get_tm_line(m.get("geometry") or []) for m in element.get("members", []) if m.get("role") == "inner"])
    if not outers:
        return None
    polygons = [[outer] + [inner for inner in inners if non_rhino_utils.is_point_in_ring(inner[0][0], inner[0][1], outer)] for outer in outers]
    return {"type": "Polygon", "coordinates": polygons[0]} if len(polygons) == 1 else {"type": "MultiPolygon", "coordinates": polygons}


def _get_bounds(geometry):
    # type: (dict) -> tuple
    points = []
    stack = [geometry["coordinates"]]
    while stack:
        item = stack.pop()
        if item and isinstance(item[0], (int, float)):
            points.append(item)
        else:
            stack.extend(item)
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), max(xs), min(ys), max(ys)


def _get_outer_area(geometry):
    # type: (dict) -> float
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return sum(abs(non_rhino_utils.get_ring_area(polygon[0])) for polygon in polygons)


# ── 건물 ────────────────────────────────────────────────

def _parse_meters(text):
    # type: (str) -> float
    """'12', '12 m', '12.5m' → 12.0. 해석 못 하면 0."""
    try:
        return float(str(text).lower().replace("m", "").strip().split()[0])
    except (ValueError, IndexError):
        return 0.0


def get_building_height(tags):
    # type: (dict) -> tuple
    """OSM 태그 → (높이 m, 층수, height_src, height_grade). height 태그 B, building:levels C, 없으면 기본값 D(국내 규칙과 같은 등급 체계)."""
    height = _parse_meters(tags.get("height", ""))
    levels = int(_parse_meters(tags.get("building:levels", "")))
    if 2.0 <= height <= 500.0:
        return round(height, 2), levels, "osm_height", "B"
    if levels > 0:
        low, per = constants.FLOOR_HEIGHT_DEFAULT
        return round(low + per * levels, 2), levels, "osm_levels", "C"
    return constants.DEFAULT_BUILDING_HEIGHT_M, 0, "default", "D"


def get_building_use(tags):
    # type: (dict) -> str
    """building 태그 → 국내 건축물용도 대분류 코드(시트 색칠용, 대략). 건물에 단 시설 태그(amenity·leisure)도 본다. 모르면 빈 값."""
    return constants.OSM_BUILDING_USE.get(tags.get("building", ""), "") or constants.OSM_PUBLIC_USE.get(tags.get("amenity") or tags.get("leisure") or "", "")


def _get_buildings(elements, reference_date):
    # type: (list, str) -> list
    buildings = []
    for element in elements:
        tags = element.get("tags") or {}
        if "building" not in tags or element["type"] not in ("way", "relation"):
            continue
        geometry = _get_polygon(element)
        if geometry is None:
            continue
        height, levels, src, grade = get_building_height(tags)
        min_x, max_x, min_y, max_y = _get_bounds(geometry)
        buildings.append(BuildingInfo(
            building_id=len(buildings) + 1, src_key="osm:%s/%d" % (element["type"], element["id"]), pnu="", usability=get_building_use(tags),
            strct_cd="", grnd_flr=levels, ugrnd_flr=int(_parse_meters(tags.get("building:levels:underground", ""))),
            flr_src="osm" if levels else "", height_m=height, height_src=src, height_grade=grade, attr_flag="", use_apr_day="",
            status="active", bld_nm=tags.get("name", ""), ngii_kind=tags.get("building", ""), ngii_use="",
            footprint_area=round(_get_outer_area(geometry), 3), total_area=0.0, geometry=geometry, source_id="osm",
            reference_date=reference_date, min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
        ))
    return buildings


# ── 일본 건물 (PLATEAU 팩) ──────────────────────────────

def _get_tm_geometry(geometry):
    # type: (dict) -> dict
    """경위도 GeoJSON (Multi)Polygon → 지금 투영 m(소수 3자리)."""
    def ring(points):
        return [[round(v, 3) for v in non_rhino_utils.get_tm_from_wgs84(lng, lat)] for lng, lat in points]
    if geometry["type"] == "Polygon":
        return {"type": "Polygon", "coordinates": [ring(r) for r in geometry["coordinates"]]}
    return {"type": "MultiPolygon", "coordinates": [[ring(r) for r in polygon] for polygon in geometry["coordinates"]]}


def load_plateau_buildings(lnglat_bounds, data_dir=None):
    # type: (tuple, str) -> tuple
    """경위도 범위(서, 남, 동, 북)에 걸리는 받아 둔 나라별 건물 팩(일본 PLATEAU·네덜란드 PDOK …)의 건물 → (BuildingInfo 목록(지금 투영 m), DataSource 목록).
    팩이 없으면 ([], []). 이름은 옛 것(일본만 있던 때)이라 그대로 둔다.

    처리: 팩마다 따로 열어 data_sources 한 줄(도시·연도)과 범위 안 건물을 읽는다. 새 기준일 팩부터 — 같은 src_key는 한 번만(도쿄도 팩끼리 경계
          3차 메시를 함께 담는다: 국립·국분지 13,245동 2026-10-21), 다른 팩의 같은 자리 건물은 먼저 넣은 것을 남긴다(get_buildings_apart).
          용도는 PLATEAU만 원천 코드(ngii_kind) → 국내 대분류(constants.PLATEAU_USE).
    출력: 출처는 건물이 실제로 들어간 팩을 source_id마다 하나로 묶은 DataSource(plateau·pdok …).
    """
    paths = data_pack.get_jp_paths(lnglat_bounds, data_dir)
    if not paths:
        return [], []
    west, south, east, north = lnglat_bounds
    packs = []   # (기준일, data_sources 행, 건물 행)
    for path in paths:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute("SELECT * FROM buildings WHERE min_x BETWEEN ? AND ? AND max_x >= ? AND min_y <= ? AND max_y >= ?",
                                      (west - constants.PLATEAU_MAX_EXTENT_DEG, east, west, north, south)).fetchall()
            source = connection.execute("SELECT * FROM data_sources").fetchone()
        finally:
            connection.close()
        if rows and source is not None:
            packs.append((source["reference_date"] or "", source, rows))
    packs.sort(key=lambda item: item[0], reverse=True)
    buildings, seen, used = [], set(), {}
    for date, source, rows in packs:
        group = []
        for row in rows:
            if row["src_key"] in seen:
                continue
            seen.add(row["src_key"])
            building = context_db._building_from_row(row)
            building.geometry = _get_tm_geometry(building.geometry)
            building.min_x, building.max_x, building.min_y, building.max_y = _get_bounds(building.geometry)
            building.usability = constants.PLATEAU_USE.get(building.ngii_kind, "") if source["source_id"] == "plateau" else (building.usability or "")
            building.reference_date = date
            group.append(building)
        group = get_buildings_apart(group, buildings)
        if group:
            used.setdefault(source["source_id"], []).append(source)
        buildings += group
    sources = []
    crs = non_rhino_utils.get_crs_label()
    for source_id, rows in used.items():
        if source_id == "plateau":
            names = "・".join(row["name"].replace("3D都市モデル（Project PLATEAU）", "") for row in rows)   # 国立市（2025年度）・国分寺市（2025年度）
            sources.append(DataSource("plateau", "3D都市モデル（Project PLATEAU）" + names, "https://www.mlit.go.jp/plateau/open-data/",
                                      min(row["reference_date"] or "" for row in rows), rows[0]["acquired_at"], crs, rows[0]["license"],
                                      "出典：3D都市モデル（Project PLATEAU）%s、国土交通省。" % names
                                      + tr("Gorani에서 건물 외곽·높이를 추출·가공. 높이는 measuredHeight(항공측량 실측, B)·층수(C)·기본값(D)")))
        else:   # 네덜란드 PDOK 등 — 팩 data_sources의 name·page_url·license·note를 그대로, 이름은 도엽을 이어 붙인다
            names = ", ".join(dict.fromkeys(row["name"] for row in rows))
            sources.append(DataSource(source_id, names, rows[0]["page_url"], min(row["reference_date"] or "" for row in rows), rows[0]["acquired_at"],
                                      crs, rows[0]["license"], rows[0]["note"] or ""))
    return buildings, sources


def load_plateau_roads(lnglat_bounds, data_dir=None):
    # type: (tuple, str) -> list
    """경위도 범위에 걸리는 받아 둔 나라별 팩의 도로면(features theme road·kind surface — 일본 PLATEAU tran, dev_plateau roads) → FeatureInfo 목록(지금 투영 m).
    features 표가 없는 팩(옛 일본 팩·네덜란드 팩)은 건너뛴다 — 런타임이 OSM 버퍼로 메운다."""
    paths = data_pack.get_jp_paths(lnglat_bounds, data_dir)
    if not paths:
        return []
    west, south, east, north = lnglat_bounds
    features, seen = [], set()
    for path in paths:
        connection = sqlite3.connect(path)
        connection.row_factory = sqlite3.Row
        try:
            try:
                rows = connection.execute("SELECT * FROM features WHERE theme = 'road' AND kind = 'surface' AND min_x BETWEEN ? AND ? AND max_x >= ? AND min_y <= ? AND max_y >= ?",
                                          (west - constants.PLATEAU_ROAD_MAX_EXTENT_DEG, east, west, north, south)).fetchall()
            except sqlite3.OperationalError:   # features 표가 없는 팩
                continue
        finally:
            connection.close()
        for row in rows:
            feature = context_db._feature_from_row(row)
            key = (feature.attrs or {}).get("plateau") or feature.feature_id
            if key in seen:   # 도쿄도 팩끼리 경계 3차 메시를 함께 담는다 — 같은 gml:id는 한 번만
                continue
            seen.add(key)
            feature.geometry = _get_tm_geometry(feature.geometry)
            feature.min_x, feature.max_x, feature.min_y, feature.max_y = _get_bounds(feature.geometry)
            features.append(feature)
    return features


def get_surfaces_apart(features, roads):
    # type: (list, list) -> list
    """OSM 피처 중 PLATEAU 도로면과 겹치는 버퍼 도로면을 뺀다 — 중심선의 가운데 점이 PLATEAU 도로면 안이면 그 도로는 이미 면이 있다.
    PLATEAU는 공도만 담고 사유지 통로·공원 길은 없어 OSM 버퍼가 그 빈 곳을 메운다. 입력은 바꾸지 않는다."""
    if not roads:
        return features
    shapes = non_rhino_utils.GridIndex(constants.CLASSIFY_GRID)
    for road in roads:
        shapes.add((road.min_x, road.min_y, road.max_x, road.max_y), road)
    kept = []
    for f in features:
        if f.theme == "road" and f.kind == "surface" and (f.attrs or {}).get("derived") == "buffer":
            x, y = f.attrs["mid"]
            if any(o.min_x <= x <= o.max_x and o.min_y <= y <= o.max_y and _is_inside(x, y, o.geometry) for o in shapes.query(x, y)):
                continue
        kept.append(f)
    return kept


def get_buildings_apart(buildings, others):
    # type: (list, list) -> list
    """others와 겹치지 않는 buildings만(새 목록). 중심점(bbox 가운데)이 다른 쪽 외곽 안이거나 다른 쪽 중심점을 품으면 같은 건물로 본다.
    PLATEAU를 OSM으로 메울 때(도시 경계 밖·PLATEAU 이후 신축)와 다른 도시 PLATEAU 팩의 같은 자리 건물을 거를 때 쓴다."""
    if not others:
        return list(buildings)
    cell = constants.CLASSIFY_GRID
    shapes, centers = non_rhino_utils.GridIndex(cell), non_rhino_utils.GridIndex(cell)
    for other in others:
        x, y = (other.min_x + other.max_x) * 0.5, (other.min_y + other.max_y) * 0.5
        shapes.add((other.min_x, other.min_y, other.max_x, other.max_y), other)
        centers.add((x, y, x, y), (x, y))
    kept = []
    for building in buildings:
        x, y = (building.min_x + building.max_x) * 0.5, (building.min_y + building.max_y) * 0.5
        if any(o.min_x <= x <= o.max_x and o.min_y <= y <= o.max_y and _is_inside(x, y, o.geometry) for o in shapes.query(x, y)):
            continue
        inner = [p for ix in range(int(math.floor(building.min_x / cell)), int(math.floor(building.max_x / cell)) + 1)
                 for iy in range(int(math.floor(building.min_y / cell)), int(math.floor(building.max_y / cell)) + 1)
                 for p in centers.query((ix + 0.5) * cell, (iy + 0.5) * cell)
                 if building.min_x <= p[0] <= building.max_x and building.min_y <= p[1] <= building.max_y]
        if any(_is_inside(px, py, building.geometry) for px, py in inner):
            continue
        kept.append(building)
    return kept


def _is_inside(x, y, geometry):
    # type: (float, float, dict) -> bool
    return any(non_rhino_utils.is_point_in_polygon(x, y, part) for part in non_rhino_utils.get_polygon_parts_from_geojson(geometry))


# ── 피처 ────────────────────────────────────────────────

def get_feature_kind(tags, is_area):
    # type: (dict, bool) -> tuple
    """OSM 태그 → (theme, kind). 해당 없으면 None. 면은 수면·학교 부지·광장·녹지, 선은 도로·철도·하천."""
    if is_area:
        if tags.get("natural") == "water" or tags.get("waterway") == "riverbank" or tags.get("landuse") in ("reservoir", "basin"):
            return "water", "river"
        if tags.get("amenity") in constants.OSM_SCHOOL_AMENITIES:
            return "public", "school_lot"   # 공공시설 도면 '학교 부지'(국내 지목 학교용지)
        if tags.get("place") == "square":
            return "public", "plaza"
        if tags.get("area:highway") or tags.get("amenity") == "parking" or (tags.get("highway") in constants.OSM_ROAD_WIDTHS and tags.get("area") == "yes"):
            return "road", "surface"   # 포장면 — 도로면 폴리곤(드묾)·보행자 광장·주차장. 국내 도로경계 면과 같은 자리
        for key, values in constants.OSM_GREEN_TAGS.items():
            if tags.get(key) in values:
                return "green", "park"
        return None
    if tags.get("highway") in constants.OSM_ROAD_WIDTHS:
        return "road", "centerline"
    if tags.get("railway") in constants.OSM_RAIL_TYPES:
        return "rail", "centerline"
    if tags.get("waterway") in ("river", "stream", "canal", "drain"):
        return "water", "centerline"
    return None


def get_road_width(tags):
    # type: (dict) -> float
    """도로폭 m — width 태그, 없으면 차로수 × 차로폭, 없으면 도로 등급 기본값."""
    width = _parse_meters(tags.get("width", ""))
    if width > 0:
        return width
    lanes = int(_parse_meters(tags.get("lanes", "")))
    if lanes > 0:
        return lanes * constants.OSM_LANE_WIDTH
    return constants.OSM_ROAD_WIDTHS.get(tags.get("highway"), 0.0)


def _get_feature_geometry(element, tags):
    # type: (dict, dict) -> tuple
    """요소 하나 → (geometry, (theme, kind)), 해당 없으면 (None, None). 점 = 이름 있는 역(역세권·보행권 도면), 닫힌 길·관계 = 면, 그 외 길 = 선."""
    if element["type"] == "node":
        if tags.get("railway") != "station" or not tags.get("name"):
            return None, None
        x, y = non_rhino_utils.get_tm_from_wgs84(float(element["lon"]), float(element["lat"]))
        return {"type": "Point", "coordinates": [round(x, 3), round(y, 3)]}, ("transit", "station")
    if element["type"] == "relation" or (element.get("geometry") and element["geometry"][0] == element["geometry"][-1] and get_feature_kind(tags, True)):
        target = get_feature_kind(tags, True)
        geometry = _get_polygon(element) if target else None
        if geometry is not None:
            return geometry, target
    target = get_feature_kind(tags, False)
    line = _get_tm_line(element.get("geometry") or []) if target and element["type"] == "way" else []
    return ({"type": "LineString", "coordinates": line}, target) if len(line) >= 2 else (None, None)


def _get_features(elements, reference_date):
    # type: (list, str) -> list
    features = []
    for element in elements:
        tags = element.get("tags") or {}
        if "building" in tags or element["type"] not in ("node", "way", "relation"):
            continue
        geometry, target = _get_feature_geometry(element, tags)
        if geometry is None:
            continue
        theme, kind = target
        min_x, max_x, min_y, max_y = _get_bounds(geometry)
        value = get_road_width(tags) if theme == "road" else None
        features.append(FeatureInfo(
            feature_id=len(features) + 1, theme=theme, kind=kind, code=tags.get("highway") or tags.get("railway") or tags.get("waterway") or tags.get("area:highway") or tags.get("amenity") or "",
            name=tags.get("name", ""), value=value, attrs={"osm": "%s/%d" % (element["type"], element["id"])}, sheet="",
            geometry=geometry, source_id="osm", reference_date=reference_date, min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
        ))
        surface = get_road_surface(geometry, tags, value) if theme == "road" and kind == "centerline" else None
        if surface is not None:
            features.append(FeatureInfo(
                feature_id=len(features) + 1, theme="road", kind="surface", code=tags.get("highway") or "", name=tags.get("name", ""), value=value,
                attrs={"osm": "%s/%d" % (element["type"], element["id"]), "derived": "buffer", "bridge": tags.get("bridge", ""),
                       "mid": list(geometry["coordinates"][len(geometry["coordinates"]) // 2])}, sheet="",   # 중심선 가운데 꼭짓점 — get_surfaces_apart가 쓴다
                geometry=surface, source_id="osm", reference_date=reference_date, min_x=min_x - value, max_x=max_x + value, min_y=min_y - value, max_y=max_y + value,
            ))
    return features


def get_road_surface(geometry, tags, width):
    # type: (dict, dict, float) -> dict
    """도로 중심선 → 도로면 GeoJSON Polygon(폭만큼 버퍼). OSM은 도로를 선으로만 두므로 지도 타일처럼 폭을 입혀야 면이 된다.
    터널(OSM_ROAD_NO_SURFACE_TAGS)·폭 0·점 하나는 None. 교량은 지형에 얹힌 면으로 둔다."""
    if width <= 0 or geometry.get("type") != "LineString":
        return None
    if any(tags.get(key, "no") != "no" for key in constants.OSM_ROAD_NO_SURFACE_TAGS):
        return None
    ring = non_rhino_utils.get_buffered_line_ring(geometry["coordinates"], width, constants.OSM_ROAD_ARC_SEGMENTS)
    if ring is None:
        return None
    return {"type": "Polygon", "coordinates": [[[round(x, 3), round(y, 3)] for x, y in ring]]}


# ── 지형 (Terrain Tiles, terrarium PNG) ─────────────────

def decode_png(data):
    # type: (bytes) -> tuple
    """8비트 RGB/RGBA 비인터레이스 PNG → (폭, 높이, 채널 수, 행 목록 bytes). 지형 타일 전용 최소 디코더."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(tr("PNG가 아닙니다"))
    pos, idat, width = 8, b"", 0
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        chunk = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", chunk[:10])
            if depth != 8 or color not in (2, 6):
                raise ValueError(tr("지원하지 않는 PNG 형식(비트 {0}, 색 {1})", depth, color))
            channels = 3 if color == 2 else 4
        elif kind == b"IDAT":
            idat += chunk
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = width * channels
    rows, previous = [], bytearray(stride)
    for y in range(height):
        start = y * (stride + 1)
        kind, line = raw[start], bytearray(raw[start + 1:start + 1 + stride])
        for i in range(stride):
            left = line[i - channels] if i >= channels else 0
            up = previous[i]
            corner = previous[i - channels] if i >= channels else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        rows.append(bytes(line))
        previous = line
    return width, height, channels, rows


def get_elevation(source_id, r, g, b):
    # type: (str, int, int, int) -> float
    """화소 → 표고 m. 지리원(gsi_dem): x = R·2¹⁶ + G·2⁸ + B를 0.01 m 단위로, x = 2²³은 값 없음(None), 2²³보다 크면 음수(x − 2²⁴).
    AWS terrarium: R·256 + G + B/256 − 32768."""
    if source_id == "gsi_dem":
        value = (r << 16) + (g << 8) + b
        if value == constants.GSI_NO_DATA:
            return None
        return (value - (1 << 24) if value > constants.GSI_NO_DATA else value) * 0.01
    return r * 256.0 + g + b / 256.0 - 32768.0


def _get_terrain_tile(zoom, tx, ty, japan):
    # type: (int, int, int, bool) -> tuple
    """타일 하나 → (source_id, decode_png 결과). 일본이면 지리원 5 m(5A → 5B → 5C, 없는 타일은 404)를 먼저, 다 없거나 일본 밖이면 같은 타일의 AWS terrarium."""
    key = ("terrain", zoom, tx, ty, japan)
    if key not in _CACHE:
        tile = None
        for url in constants.GSI_TERRAIN_URLS if japan else ():
            try:
                tile = ("gsi_dem", decode_png(_fetch(url.format(z=zoom, x=tx, y=ty))))
                break
            except Exception:   # 404(없는 타일)뿐 아니라 5xx·시간 초과도 '없음'으로 — 지리원이 잠깐 막혀도 일본 생성이 통째로 죽지 않게 AWS로 간다(2026-10-22 통합 리뷰)
                continue
        _keep(key, tile or ("aws_terrain", decode_png(_fetch(constants.OSM_TERRAIN_URL.format(z=zoom, x=tx, y=ty)))))
    return _CACHE[key]


def get_terrain_spots(bounds, reference_date):
    # type: (tuple, str) -> tuple
    """bounds를 덮는 지형 타일을 받아 표고점(theme terrain, kind spot)으로. 일본이면 지리원 5 m 타일(z15, 약 8 m 간격), 아니면 AWS terrarium
    (z13, 약 30 m). 출력: (표고점 목록, 실제로 쓴 원천 id 집합 — gsi_dem·aws_terrain)."""
    south, west, north, east = _get_lnglat_bbox(bounds)
    japan = is_japan((west + east) * 0.5, (south + north) * 0.5)
    zoom, step = (constants.GSI_TERRAIN_ZOOM, constants.GSI_TERRAIN_STEP) if japan else (constants.OSM_TERRAIN_ZOOM, constants.OSM_TERRAIN_STEP)
    x0, y0 = non_rhino_utils.get_tile_xy(west, north, zoom)
    x1, y1 = non_rhino_utils.get_tile_xy(east, south, zoom)
    spots, used = [], set()
    for tx in range(int(x0), int(x1) + 1):
        for ty in range(int(y0), int(y1) + 1):
            source_id, (width, height, channels, rows) = _get_terrain_tile(zoom, tx, ty, japan)
            used.add(source_id)
            for py in range(0, height, step):
                lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (ty + (py + 0.5) / height) / 2 ** zoom))))
                for px in range(0, width, step):
                    lng = (tx + (px + 0.5) / width) / 2 ** zoom * 360.0 - 180.0
                    if not (west <= lng <= east and south <= lat <= north):
                        continue
                    elevation = get_elevation(source_id, *rows[py][px * channels:px * channels + 3])
                    if elevation is None:   # 지리원 수면 — 수계 평탄화가 경계 Z로 메운다
                        continue
                    x, y = non_rhino_utils.get_tm_from_wgs84(lng, lat)
                    spots.append(FeatureInfo(
                        feature_id=10 ** 9 + len(spots), theme="terrain", kind="spot", code="", name="", value=round(elevation, 2), attrs={},
                        sheet="", geometry={"type": "Point", "coordinates": [round(x, 3), round(y, 3)]}, source_id=source_id,
                        reference_date=reference_date, min_x=x, max_x=x, min_y=y, max_y=y,
                    ))
    return spots, used


# ── 지명 검색 (Nominatim) ───────────────────────────────

def search_places(query, limit):
    # type: (str, int) -> list
    """지명·주소 → [{"name", "center": [lng, lat]}]. 국내 필지 검색이 비었을 때만 부른다(Nominatim 이용 정책: 초당 1건, 식별 가능한 User-Agent).
    네트워크 오류면 빈 목록."""
    url = constants.OSM_NOMINATIM_URL + "?" + urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": limit})
    try:
        places = json.loads(_fetch(url).decode("utf-8"))
    except Exception:
        return []
    return [{"name": p.get("display_name", ""), "center": [round(float(p["lon"]), 7), round(float(p["lat"]), 7)]} for p in places]


# ── 묶기 ────────────────────────────────────────────────

def load(bounds, today):
    # type: (tuple, str) -> ContextData
    """bounds(TM m) 안 OSM 건물·피처 + 지형 표고점 → ContextData. 받는 날짜를 OSM·지형 기준일로 적는다.
    일본: 받아 둔 PLATEAU 팩 건물을 먼저 쓰고 OSM 건물은 그와 겹치지 않는 것만, 지형은 지리원 5 m 타일. 출처는 실제로 쓴 것만(역할은 뒤의 것이 차지)."""
    plateau, plateau_sources = load_plateau_buildings(get_lnglat_bounds(bounds))   # 나라별 팩 건물(일본 PLATEAU·네덜란드 PDOK)
    if plateau:   # 팩이 있는 곳 — 도로·수계·녹지 먼저(건물 줄 뺀 질의), OSM 건물은 따로 첫 미러에만(constants.OSM_OVERPASS_BUILDING_QUERY 주석)
        try:
            elements, osm_ok = get_overpass_elements(bounds, constants.OSM_OVERPASS_QUERY.replace(constants.OSM_OVERPASS_BUILDINGS, "")), True
        except RuntimeError:   # 공개 Overpass 서버가 모두 막힘(2026-10-21 Rhino 실측: 502·504·시간 초과) — 팩 건물·지형만으로 만든다
            elements, osm_ok = [], False   # 출처에 osm이 빠진 것을 context_builder가 보고 알린다
        try:
            osm_buildings = _get_buildings(get_overpass_elements(bounds, constants.OSM_OVERPASS_BUILDING_QUERY, constants.OSM_OVERPASS_URLS[:1]), today) if osm_ok else []
        except RuntimeError:   # 메우기용이라 못 받아도 넘어간다
            osm_buildings = []
    else:
        elements, osm_ok = get_overpass_elements(bounds), True
        osm_buildings = _get_buildings(elements, today)
    buildings = plateau + get_buildings_apart(osm_buildings, plateau)
    _apply_public_use(buildings, elements)
    spots, terrain_ids = get_terrain_spots(bounds, today)
    crs = non_rhino_utils.get_crs_label()
    sources = [DataSource("osm", "OpenStreetMap (Overpass API)", "https://www.openstreetmap.org/copyright", today, today, crs,
                          "ODbL 1.0 — © OpenStreetMap contributors", tr("건물 높이는 height·building:levels 태그, 없으면 기본값"))] if osm_ok else []
    if "aws_terrain" in terrain_ids:
        sources.append(DataSource("aws_terrain", "Terrain Tiles (AWS Open Data, terrarium)", "https://registry.opendata.aws/terrain-tiles/", "", today,
                                  crs, tr("공개(출처 표기)"), tr("SRTM·GMTED 등 혼합 DEM, 해상도 지역별 상이(약 30 m)")))
    sources += plateau_sources
    if "gsi_dem" in terrain_ids:   # 이름은 지리원 출처 표기 그대로(일본어)
        sources.append(DataSource("gsi_dem", "国土地理院 標高タイル（基盤地図情報数値標高モデル DEM5A・5B・5C）", "https://maps.gsi.go.jp/development/ichiran.html",
                                  "", today, crs, tr("국토지리원 콘텐츠 이용규약(공공데이터 이용규약 제1.0판 호환) — 출처 표기"),
                                  tr("표고 타일을 가공해 만듦. 5 m 격자, 표고 기준 T.P.(도쿄만 평균해면)")))
    roads = load_plateau_roads(get_lnglat_bounds(bounds)) if plateau else []   # 팩에 도로면이 있으면(2026-10-22 roads 단계) 그것을 쓰고 OSM 버퍼는 빈 곳만
    features = roads + get_surfaces_apart(_get_features(elements, today), roads) + spots
    return ContextData(bounds=tuple(bounds), buildings=buildings, features=features, sources=sources)


def _apply_public_use(buildings, elements):
    # type: (list, list) -> int
    """시설 면(학교·병원·도서관…, OSM_PUBLIC_USE) 안에 중심이 있는 용도 미상 건물에 국내 용도 대분류를 준다 — 공공시설 도면.
    OSM은 시설을 부지 면에 달고 건물은 building=yes로만 그리는 일이 흔하다. 반환: 바꾼 동 수."""
    areas = []
    for element in elements:
        tags = element.get("tags") or {}
        use = constants.OSM_PUBLIC_USE.get(tags.get("amenity") or tags.get("leisure") or "")
        if use and "building" not in tags and element["type"] in ("way", "relation"):
            polygon = _get_polygon(element)
            if polygon:
                areas.append((use, non_rhino_utils.get_polygon_parts_from_geojson(polygon), _get_bounds(polygon)))
    changed = 0
    for building in buildings:
        if building.usability:
            continue
        x, y = (building.min_x + building.max_x) * 0.5, (building.min_y + building.max_y) * 0.5
        for use, parts, (min_x, max_x, min_y, max_y) in areas:
            if min_x <= x <= max_x and min_y <= y <= max_y and any(non_rhino_utils.is_point_in_polygon(x, y, part) for part in parts):
                building.usability = use
                changed += 1
                break
    return changed
