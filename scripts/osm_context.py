"""해외 대상지 컨텍스트 — OSM(Overpass API) 건물·도로·철도·수계·녹지 + Mapterhorn 지형(못 받으면 AWS Terrain Tiles)을 context_db와 같은 형식으로.

국내는 로컬 DB(context_db)를 쓰고, 대상지가 한국 밖이면(non_rhino_utils.is_local_projection) context_builder가 이 모듈을 부른다.
좌표는 non_rhino_utils의 지금 투영(대상지 중심 지역 횡메르카토르) m. 표준 라이브러리만 쓴다(urllib·json·zlib·sqlite3).
일본은 받아 둔 PLATEAU 건물 팩(jp<시구정촌코드>_context.db — cmd_site가 생성 직전에 받는다)을 먼저 쓰고 OSM 건물은 그와 겹치지 않는
것만 보탠다. 지형은 Mapterhorn(지리원 DEM을 담았다), 못 받으면 국토지리원(GSI) 5 m 표고 타일. 근거 docs/research/japan.md·data_sources.md §6.

출처 표기: 건물·도로 등 "© OpenStreetMap contributors"(ODbL — 산출물은 출처 표기만, DB로 재배포하지 않는다),
지형 "© Mapterhorn" + 원천 기관(get_mapterhorn_credit), 대신 쓰면 "Terrain Tiles, Mapzen/AWS Open Data(SRTM·GMTED 등 공개 DEM)", 일본 건물 "3D都市モデル（Project PLATEAU）<도시>（<연도>年度）"
(CC BY 4.0), 일본 지형 "国土地理院 標高タイル".
"""

import array
import gzip
import json
import sqlite3
import math
import re
import struct
import time
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
    # ponytail: 날짜변경선을 넘는 범위는 180°에서 자른다(Overpass 400, 2026-10-23 감사 179.996°) — 건너편 반쪽은 비지만 생성은 된다
    clamp = lambda lng: max(-180.0, min(180.0, lng))
    return (min(c[1] for c in corners), clamp(min(c[0] for c in corners)), max(c[1] for c in corners), clamp(max(c[0] for c in corners)))


def get_lnglat_bounds(bounds):
    # type: (tuple) -> tuple
    """TM bounds → (서, 남, 동, 북) 경위도 — 일본 건물 팩 범위(매니페스트·packs.json bounds)와 같은 순서."""
    south, west, north, east = _get_lnglat_bbox(bounds)
    return west, south, east, north


def get_country(lng, lat):
    # type: (float, float) -> str
    """경위도가 나라별 건물 팩(data_pack.get_country_packs — 매니페스트 countries[], 내장 constants.COUNTRY_PACKS) 상자 안이면 그 나라 코드, 아니면 "".
    상자가 겹치면(프랑스 상자 안의 스위스) 작은 상자가 이긴다."""
    found = []
    for code, pack in data_pack.get_country_packs().items():
        for west, south, east, north in pack["bounds"]:   # 나라 하나에 상자 여럿(미국 본토·알래스카·하와이)
            if west <= lng <= east and south <= lat <= north:
                found.append(((east - west) * (north - south), code))
    return min(found)[1] if found else ""


def is_japan(lng, lat):
    # type: (float, float) -> bool
    """경위도가 일본인지(대략) — 지리원 지형 타일을 먼저 받을지. 일본 상자 안이고 한국(non_rhino_utils.is_korea — 북규슈·쓰시마는 뺀다)이 아니면.
    틀려도 지리원 타일이 404라 AWS 타일로 돌아간다."""
    west, south, east, north = constants.JP_BOUNDS
    return west <= lng <= east and south <= lat <= north and not non_rhino_utils.is_korea(lng, lat)


def _fetch(url, data=None, timeout=None):
    # type: (str, bytes, float) -> bytes
    request = urllib.request.Request(url, data=data, headers={"User-Agent": constants.OSM_USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout or constants.OSM_TIMEOUT_SECONDS) as response:
        return response.read()


def _keep(key, value):
    # type: (tuple, object) -> object
    """응답 하나를 캐시에 넣고 돌려준다. 항목이 OSM_CACHE_MAX를 넘으면 먼저 비운다 — 긴 Blender 세션에서 Overpass 응답(대상지마다 수십 MB)이 쌓이지 않게."""
    if len(_CACHE) >= constants.OSM_CACHE_MAX:
        _CACHE.clear()
    _CACHE[key] = value
    return value


def _is_busy(error):
    # type: (Exception) -> bool
    """서버에 닿았는데 붐빔·한도(429·502~504)이거나 200인데 중간에 멈춘 결과(runtime error) — 인터넷 탓이 아니고, 잠시 뒤 다시 물으면 받아진다."""
    return (isinstance(error, urllib.error.HTTPError) and error.code in (429, 502, 503, 504)) or "runtime error" in str(error)


def _wait_retry(seconds, attempt, total, on_wait):
    # type: (float, int, int, object) -> None
    """다시 묻기 전 기다림 — 1초마다 on_wait(문구)로 진행 줄을 바꾼다(생성 화면이 멈춘 것처럼 보이지 않게, 취소도 그 사이에 받는다)."""
    for left in range(int(math.ceil(seconds)), 0, -1):
        if on_wait is not None:
            on_wait(tr("OSM 서버가 붐벼 다시 시도합니다 ({0}/{1}, {2}초 뒤)", attempt, total, left))
        time.sleep(1.0)


def get_overpass_elements(bounds, query=None, endpoints=None, on_wait=None):
    # type: (tuple, str, tuple, object) -> list
    """bounds 안 OSM 요소(out geom). query = Overpass 질의 틀({bbox} 자리, 기본 constants.OSM_OVERPASS_QUERY), endpoints = 미러(기본 전부).
    미러를 차례로 시도한다. 첫 서버가 붐비면 OSM_RETRY_WAITS만큼 쉬며 다시 묻는다(on_wait = 기다리는 동안 진행 문구 콜백 — 취소 예외는 그대로 올라간다).
    실패하면 RuntimeError."""
    bbox = "%.6f,%.6f,%.6f,%.6f" % _get_lnglat_bbox(bounds)
    query = (query or constants.OSM_OVERPASS_QUERY).replace("{bbox}", bbox)
    key = ("overpass", query)
    if key in _CACHE:
        return _CACHE[key]
    errors, busy = [], False
    for index, endpoint in enumerate(endpoints or data_pack.get_service("overpass", constants.OSM_OVERPASS_URLS)):   # 매니페스트 services.overpass가 미러 목록을 덮을 수 있다
        waits = constants.OSM_RETRY_WAITS if index == 0 else ()
        for attempt in range(1 + len(waits)):
            try:
                body = _fetch(endpoint, urllib.parse.urlencode({"data": query}).encode("utf-8"),
                              timeout=None if index == 0 else constants.OSM_MIRROR_TIMEOUT_SECONDS)
                result = json.loads(body.decode("utf-8"))
                if "runtime error" in (result.get("remark") or ""):   # 200인데 서버가 시간 초과·메모리로 중간에 멈춘 빈 결과 — 캐시하지 않고 다음 미러(2026-10-23 감사)
                    raise RuntimeError(result["remark"][:200])
                return _keep(key, result["elements"])
            except Exception as error:   # 미러 하나가 막혀도 다음 것을 쓴다
                if attempt < len(waits) and _is_busy(error):   # 첫 서버의 순간 붐빔 — 쉬었다 다시(constants.OSM_RETRY_WAITS 주석)
                    _wait_retry(waits[attempt], attempt + 1, len(waits), on_wait)
                    continue
                errors.append("%s: %s" % (endpoint, error))
                # 붐빔·한도·응답 지연은 인터넷 탓이 아니다(2026-10-23: 429인데 '인터넷 연결을 확인하세요'가 떴다)
                busy = busy or _is_busy(error) or "timed out" in str(error)
                break
    title = (tr("OSM(Overpass) 서버가 붐빕니다. 1~2분 뒤 다시 시도하세요") if busy
             else tr("OSM(Overpass) 데이터를 받지 못했습니다. 인터넷 연결을 확인하세요"))
    raise RuntimeError(title + "\n" + "\n".join(errors))


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
            building.usability = (building.usability or "") or (constants.PLATEAU_USE.get(building.ngii_kind, "") if source["source_id"] == "plateau" else "")   # 팩 값 먼저 — 옛 PLATEAU 팩만 코드 사전
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
    """OSM 태그 → (theme, kind). 해당 없으면 None. 면은 수면·학교 부지·광장·녹지, 선은 도로·철도·하천·담·옹벽·가로수 줄."""
    if is_area:
        if tags.get("waterway") == "riverbank" or (tags.get("natural") == "water" and tags.get("water") in constants.OSM_FLOWING_WATER):
            return "water", "river"
        if tags.get("natural") == "water" or tags.get("landuse") in ("reservoir", "basin"):
            return "water", "lake"   # 고인 물(water=* 없는 natural=water는 대개 호수·연못) — 평평한 수면
        if tags.get("amenity") in constants.OSM_SCHOOL_AMENITIES:
            return "public", "school_lot"   # 공공시설 도면 '학교 부지'(국내 지목 학교용지)
        if tags.get("place") == "square":
            return "public", "plaza"
        if tags.get("railway") == "platform":
            return "rail", "platform"   # 승강장 면 — 선로 옆 각기둥(context_geometry.get_rail_detail). 선으로 그린 승강장은 쓰지 않는다
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
    if tags.get("barrier") in ("wall", "retaining_wall", "fence"):   # 옹벽은 지반 고저차로 세로 벽, 담·울타리는 일정 높이(context_geometry.get_structure_lines)
        return "structure", "wall" if tags["barrier"] == "retaining_wall" else "fence"
    if tags.get("natural") == "tree_row":
        return "tree", "row"
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
        target = ("tree", "tree") if tags.get("natural") == "tree" else ("transit", "station") if tags.get("railway") == "station" and tags.get("name") else None
        if target is None:
            return None, None
        x, y = non_rhino_utils.get_tm_from_wgs84(float(element["lon"]), float(element["lat"]))
        return {"type": "Point", "coordinates": [round(x, 3), round(y, 3)]}, target
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
        attrs = {"osm": "%s/%d" % (element["type"], element["id"])}
        if theme in ("rail", "road"):   # 지하·교량·층 정보와 궤간 — 지상 선로·승강장만 3D로, 교량은 상판(context_geometry.get_rail_detail·get_bridges)
            attrs.update((key, tags[key]) for key in ("tunnel", "bridge", "layer", "level", "gauge") if key in tags)
        elif theme in ("tree", "structure"):   # 나무 높이·수관 지름·수종, 담 높이(context_geometry.get_trees·get_structure_lines)
            attrs.update((key, tags[key]) for key in ("height", "diameter_crown", "species", "genus", "leaf_type", "barrier") if key in tags)
        features.append(FeatureInfo(
            feature_id=len(features) + 1, theme=theme, kind=kind, code=tags.get("highway") or tags.get("railway") or tags.get("waterway") or tags.get("area:highway") or tags.get("amenity") or "",
            name=tags.get("name", ""), value=value, attrs=attrs, sheet="",
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
    for ring, osm_id in get_crosswalk_rings(elements):
        min_x, max_x, min_y, max_y = _get_bounds({"type": "Polygon", "coordinates": [ring]})
        features.append(FeatureInfo(
            feature_id=len(features) + 1, theme="marking", kind="crosswalk", code="", name="", value=None, attrs={"osm": "node/%d" % osm_id}, sheet="",
            geometry={"type": "Polygon", "coordinates": [ring]}, source_id="osm", reference_date=reference_date, min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
        ))
    return features


def is_marked_crossing(tags):
    # type: (dict) -> bool
    """highway=crossing 점이 칠한 횡단보도인지 — crossing:markings(no 빼고), 없으면 옛 crossing 값(OSM_CROSSWALK_MARKED)."""
    if tags.get("highway") != "crossing":
        return False
    markings = tags.get("crossing:markings")
    if markings:
        return markings != "no"
    return tags.get("crossing") in constants.OSM_CROSSWALK_MARKED or tags.get("crossing_ref") == "zebra"


def get_crosswalk_rings(elements):
    # type: (list) -> list
    """칠한 횡단보도 점 → 그 점을 지나는 차도(보행로 빼고) 방향의 직사각형 ``[(링 [[x, y]…], 노드 id)]`` (TM).
    길이 = 그 도로 폭(get_road_width), 폭 = OSM_CROSSWALK_WIDTH. 점 하나는 처음 만난 도로 하나에만."""
    crossings = {}
    for element in elements:
        if element["type"] == "node" and is_marked_crossing(element.get("tags") or {}):
            crossings[element["id"]] = non_rhino_utils.get_tm_from_wgs84(float(element["lon"]), float(element["lat"]))
    out = []
    for element in elements if crossings else []:
        tags = element.get("tags") or {}
        ids, geom = element.get("nodes") or [], element.get("geometry") or []
        if element["type"] != "way" or tags.get("highway") not in constants.OSM_ROAD_WIDTHS or tags.get("highway") in constants.OSM_PATH_HIGHWAYS \
                or len(ids) != len(geom) or len(ids) < 2:
            continue
        for k, node_id in enumerate(ids):
            if node_id not in crossings:
                continue
            (ax, ay), (bx, by) = (non_rhino_utils.get_tm_from_wgs84(geom[i]["lon"], geom[i]["lat"]) for i in (max(0, k - 1), min(len(ids) - 1, k + 1)))
            length = math.hypot(bx - ax, by - ay)
            if length < 1e-6:
                continue
            (cx, cy), dx, dy = crossings.pop(node_id), (bx - ax) / length, (by - ay) / length
            along, across = constants.OSM_CROSSWALK_WIDTH / 2.0, get_road_width(tags) / 2.0
            ring = [[round(cx + dx * sa * along - dy * sb * across, 3), round(cy + dy * sa * along + dx * sb * across, 3)] for sa, sb in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            out.append((ring + [ring[0]], node_id))
    return out


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


# ── 지형 (Mapterhorn WebP → 못 받으면 Terrain Tiles·지리원 PNG) ─────────

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


# 무손실 WebP(VP8L) 해독 — 표준 라이브러리로는 WebP를 못 열고 Rhino 8 CPython엔 pip 패키지를 못 싣는다(Yak). 스펙 RFC 9649.
# 2026-11-14 Mapterhorn 타일 58장을 dwebp 1.6.0과 화소 단위로 비교해 모두 같았다(512 px 한 장 평균 0.32 s, python 3.9).
_WEBP_CODE_ORDER = (17, 18, 0, 1, 2, 3, 4, 5, 16, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15)   # 코드 길이 코드의 길이를 읽는 순서
_WEBP_PLANE = bytes.fromhex(   # 거리 코드 1~120 → (dy << 4) | (8 − dx) — libwebp kCodeToPlane
    "1807171928062729161a262a38053739151b363a252b48044749141c353b464a242c58454b343c035759131d565a232d444c555b333d68026769121e"
    "666a222e545c434d656b323e78017779535d111f646c424e767a212f757b313f636d525e00747c414f1020626e30737d515f40727e616f50717f6070")
_WEBP_S8 = [v - 256 if v > 127 else v for v in range(256)]   # 바이트 → 부호 있는 8비트(색 변환)


class _WebpBits(object):
    """LSB부터 읽는 비트 읽기 — 헤더·부호표용(화소 루프는 지역 변수로 따로 돈다)."""

    def __init__(self, data, pos):
        self.data, self.pos, self.val, self.n = data, pos, 0, 0

    def read(self, n):
        if self.n < n:
            self.val |= int.from_bytes(self.data[self.pos:self.pos + 8], "little") << self.n
            self.pos += 8
            self.n += 64
        value = self.val & ((1 << n) - 1)
        self.val >>= n
        self.n -= n
        return value

    def symbol(self, code):
        table, mask = code
        if self.n < 15:
            self.val |= int.from_bytes(self.data[self.pos:self.pos + 8], "little") << self.n
            self.pos += 8
            self.n += 64
        entry = table[self.val & mask]
        self.val >>= entry & 15
        self.n -= entry & 15
        return entry >> 4


def _get_webp_code(lengths):
    # type: (list) -> tuple
    """기호별 코드 길이 → (표, 마스크) 정규 허프만 — 표[다음 비트] = 기호 << 4 | 길이. 기호가 하나면 길이 0(비트를 읽지 않는다)."""
    used = sorted((n, s) for s, n in enumerate(lengths) if n)
    if not used:
        raise ValueError("WebP: empty code")
    if len(used) == 1:
        return [used[0][1] << 4], 0
    top = used[-1][0]
    table = [0] * (1 << top)
    code, previous = 0, used[0][0]
    for n, s in used:
        code <<= n - previous
        previous = n
        table[int(format(code, "0%db" % n)[::-1], 2)::1 << n] = [s << 4 | n] * (1 << (top - n))   # 비트를 거꾸로 읽으므로 뒤집은 코드 자리마다
        code += 1
    if code != 1 << top:
        raise ValueError("WebP: bad code")
    return table, (1 << top) - 1


def _read_webp_code(bits, size):
    # type: (_WebpBits, int) -> tuple
    """부호표 하나(단순 = 기호 1~2개, 일반 = 코드 길이를 부호화)."""
    lengths = [0] * size
    if bits.read(1):
        count = bits.read(1) + 1
        lengths[bits.read(1 + 7 * bits.read(1))] = 1
        if count == 2:
            lengths[bits.read(8)] = 1
        return _get_webp_code(lengths)
    length_lengths = [0] * 19
    for i in range(4 + bits.read(4)):
        length_lengths[_WEBP_CODE_ORDER[i]] = bits.read(3)
    length_code = _get_webp_code(length_lengths)
    max_symbol = 2 + bits.read(2 + 2 * bits.read(3)) if bits.read(1) else size
    previous, s = 8, 0
    while s < size and max_symbol:
        max_symbol -= 1
        c = bits.symbol(length_code)
        if c < 16:
            lengths[s] = c
            s += 1
            previous = c or previous
        else:
            extra, offset = ((2, 3), (3, 3), (7, 11))[c - 16]
            repeat = bits.read(extra) + offset
            if s + repeat > size:
                raise ValueError("WebP: bad repeat")
            lengths[s:s + repeat] = [previous if c == 16 else 0] * repeat
            s += repeat
    return _get_webp_code(lengths)


def _read_webp_pixels(bits, width, height, is_main):
    # type: (_WebpBits, int, int, bool) -> list
    """엔트로피 부호 화소 → ARGB int 목록(색 캐시·메타 부호표·LZ77 역참조). is_main이면 메타 부호표(화소 구역별 부호표 묶음)가 올 수 있다."""
    cache_bits = bits.read(4) if bits.read(1) else 0
    if cache_bits > 11:
        raise ValueError("WebP: bad color cache")
    prefix_bits, group_map, group_width = 0, None, 1
    if is_main and bits.read(1):
        prefix_bits = bits.read(3) + 2
        group_width = (width + (1 << prefix_bits) - 1) >> prefix_bits
        group_map = [(p >> 8) & 0xffff for p in _read_webp_pixels(bits, group_width, (height + (1 << prefix_bits) - 1) >> prefix_bits, False)]
    cache_size = (1 << cache_bits) if cache_bits else 0
    groups = [tuple(_read_webp_code(bits, size) for size in (280 + cache_size, 256, 256, 256, 40))
              for _ in range(max(group_map) + 1 if group_map else 1)]
    # 화소 루프 — 512 px 한 장에 26만 번 돈다. 함수 호출 없이 지역 변수로(비트는 한 번에 64개씩 채운다, 화소 하나는 최대 58비트)
    data, pos, val, n = bits.data, bits.pos, bits.val, bits.n
    total = width * height
    out = [0] * total
    cache, cache_shift, cached = [0] * cache_size, 32 - cache_bits, 0
    mask_x = (1 << prefix_bits) - 1
    (gt, gm), (rt, rm), (bt, bm), (at, am), (dt, dm) = groups[0]
    i = x = y = 0
    from_bytes = int.from_bytes
    while i < total:
        if group_map is not None and not (x & mask_x):
            (gt, gm), (rt, rm), (bt, bm), (at, am), (dt, dm) = groups[group_map[(y >> prefix_bits) * group_width + (x >> prefix_bits)]]
        if n < 64:
            val |= from_bytes(data[pos:pos + 8], "little") << n
            pos += 8
            n += 64
        e = gt[val & gm]
        val >>= e & 15
        n -= e & 15
        code = e >> 4
        if code < 256:   # 글자 화소 — 초록 다음 빨강·파랑·알파
            e = rt[val & rm]
            val >>= e & 15
            n -= e & 15
            red = e >> 4
            e = bt[val & bm]
            val >>= e & 15
            n -= e & 15
            blue = e >> 4
            e = at[val & am]
            val >>= e & 15
            n -= e & 15
            out[i] = (e >> 4) << 24 | red << 16 | code << 8 | blue
            i += 1
            x += 1
            if x == width:
                x = 0
                y += 1
        elif code < 280:   # 역참조 — 길이·거리 접두 코드
            code -= 256
            if code < 4:
                length = code + 1
            else:
                extra = (code - 2) >> 1
                length = ((2 + (code & 1)) << extra) + (val & ((1 << extra) - 1)) + 1
                val >>= extra
                n -= extra
            e = dt[val & dm]
            val >>= e & 15
            n -= e & 15
            code = e >> 4
            if code < 4:
                dist = code + 1
            else:
                extra = (code - 2) >> 1
                dist = ((2 + (code & 1)) << extra) + (val & ((1 << extra) - 1)) + 1
                val >>= extra
                n -= extra
            if dist > 120:
                dist -= 120
            else:
                plane = _WEBP_PLANE[dist - 1]
                dist = max(1, (plane >> 4) * width + 8 - (plane & 15))
            if dist > i or i + length > total:
                raise ValueError("WebP: bad backward reference")
            if dist >= length:
                out[i:i + length] = out[i - dist:i - dist + length]
            else:   # 겹치는 복사(반복 무늬)는 하나씩
                for k in range(i, i + length):
                    out[k] = out[k - dist]
            i += length
            x += length
            while x >= width:
                x -= width
                y += 1
            if group_map is not None and i < total:
                (gt, gm), (rt, rm), (bt, bm), (at, am), (dt, dm) = groups[group_map[(y >> prefix_bits) * group_width + (x >> prefix_bits)]]
        else:   # 색 캐시 — 앞 화소를 넣어 두고 꺼낸다
            while cached < i:
                c = out[cached]
                cache[((c * 0x1e35a7bd) & 0xffffffff) >> cache_shift] = c
                cached += 1
            out[i] = cache[code - 280]
            i += 1
            x += 1
            if x == width:
                x = 0
                y += 1
    bits.pos, bits.val, bits.n = pos, val, n
    return out


def _add_argb(a, b):
    # type: (int, int) -> int
    """채널별 (a + b) mod 256."""
    return (((a & 0xff00ff00) + (b & 0xff00ff00)) & 0xff00ff00) | (((a & 0x00ff00ff) + (b & 0x00ff00ff)) & 0x00ff00ff)


def _average_argb(a, b):
    # type: (int, int) -> int
    """채널별 내림 평균."""
    return (((a ^ b) & 0xfefefefe) >> 1) + (a & b)


def _get_webp_prediction(mode, left, top, top_left, top_right):
    # type: (int, int, int, int, int) -> int
    """예측 변환 모드 0~13 → 예측 화소(스펙 4.1)."""
    if mode == 1:
        return left
    if mode == 2:
        return top
    if mode == 3:
        return top_right
    if mode == 4:
        return top_left
    if mode == 5:
        return _average_argb(_average_argb(left, top_right), top)
    if mode == 6:
        return _average_argb(left, top_left)
    if mode == 7:
        return _average_argb(left, top)
    if mode == 8:
        return _average_argb(top_left, top)
    if mode == 9:
        return _average_argb(top, top_right)
    if mode == 10:
        return _average_argb(_average_argb(left, top_left), _average_argb(top, top_right))
    if mode == 11:   # Select — 예측(L + T − TL)에 더 가까운 쪽
        to_left = to_top = 0
        for s in (0, 8, 16, 24):
            corner = (top_left >> s) & 255
            to_left += abs(((top >> s) & 255) - corner)
            to_top += abs(((left >> s) & 255) - corner)
        return left if to_left < to_top else top
    if mode == 12:   # ClampAddSubtractFull
        result = 0
        for s in (0, 8, 16, 24):
            result |= min(255, max(0, ((left >> s) & 255) + ((top >> s) & 255) - ((top_left >> s) & 255))) << s
        return result
    if mode == 13:   # ClampAddSubtractHalf — 나눗셈은 C처럼 0 쪽으로
        average, result = _average_argb(left, top), 0
        for s in (0, 8, 16, 24):
            a, b = (average >> s) & 255, (top_left >> s) & 255
            result |= min(255, max(0, a + int((a - b) / 2))) << s
        return result
    return 0xff000000


def _undo_webp_predictor(px, width, height, bits, modes):
    # type: (list, int, int, int, list) -> None
    """예측 변환 되돌리기 — 첫 화소는 검정, 첫 행은 왼쪽, 첫 열은 위, 나머지는 블록 모드. 오른쪽 끝 열의 오른쪽 위는 같은 행 첫 화소(목록에서 i − w + 1)."""
    block_width = (width + (1 << bits) - 1) >> bits
    size = 1 << bits
    px[0] = _add_argb(px[0], 0xff000000)
    for i in range(1, width):
        px[i] = _add_argb(px[i], px[i - 1])
    for y in range(1, height):
        row = y * width
        px[row] = _add_argb(px[row], px[row - width])
        for block, mode_pixel in enumerate(modes[(y >> bits) * block_width:(y >> bits) * block_width + block_width]):
            mode = (mode_pixel >> 8) & 15
            start, stop = row + max(1, block * size), row + min(width, (block + 1) * size)
            if mode in (1, 2, 3, 4):   # 이웃 하나를 그대로 — 지형 타일 블록의 절반 이상
                offset = (1, width, width - 1, width + 1)[mode - 1]
                for i in range(start, stop):
                    a, b = px[i], px[i - offset]
                    px[i] = (((a & 0xff00ff00) + (b & 0xff00ff00)) & 0xff00ff00) | (((a & 0x00ff00ff) + (b & 0x00ff00ff)) & 0x00ff00ff)
            else:
                for i in range(start, stop):
                    px[i] = _add_argb(px[i], _get_webp_prediction(mode, px[i - 1], px[i - width], px[i - width - 1], px[i - width + 1]))


def _undo_webp_color(px, width, height, bits, transforms):
    # type: (list, int, int, int, list) -> None
    """색 변환 되돌리기 — 빨강 += g2r·초록 >> 5, 파랑 += g2b·초록 >> 5 + r2b·빨강 >> 5(부호 있는 8비트). 0인 블록은 건너뛴다(지형 타일 99 %)."""
    block_width = (width + (1 << bits) - 1) >> bits
    size, s8 = 1 << bits, _WEBP_S8
    for y in range(height):
        row = y * width
        for block, t in enumerate(transforms[(y >> bits) * block_width:(y >> bits) * block_width + block_width]):
            if not t & 0xffffff:
                continue
            g2r, g2b, r2b = s8[t & 255], s8[(t >> 8) & 255], s8[(t >> 16) & 255]
            for i in range(row + block * size, row + min(width, (block + 1) * size)):
                p = px[i]
                g = s8[(p >> 8) & 255]
                r = ((p >> 16) + ((g2r * g) >> 5)) & 255
                px[i] = (p & 0xff00ff00) | r << 16 | ((p + ((g2b * g) >> 5) + ((r2b * s8[r]) >> 5)) & 255)


def decode_webp(data):
    # type: (bytes) -> tuple
    """무손실 WebP(RIFF/VP8L) → (폭, 높이, ARGB int 목록). 손실 WebP(VP8)는 ValueError — terrarium은 값이 1만 바뀌어도 표고가 틀린다."""
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError(tr("WebP가 아닙니다"))
    pos = 12
    while pos + 8 <= len(data) and data[pos:pos + 4] != b"VP8L":   # VP8X 등 다른 덩어리는 건너뛴다
        pos += 8 + ((int.from_bytes(data[pos + 4:pos + 8], "little") + 1) & ~1)
    if data[pos:pos + 4] != b"VP8L" or data[pos + 8] != 0x2f:
        raise ValueError(tr("무손실 WebP가 아닙니다"))
    bits = _WebpBits(data, pos + 9)
    width, height = bits.read(14) + 1, bits.read(14) + 1
    bits.read(1)   # 알파 사용 표시 — 값은 화소에 그대로 있다
    if bits.read(3):
        raise ValueError("WebP: bad version")
    transforms, xsize = [], width
    while bits.read(1):
        kind = bits.read(2)
        if kind in (0, 1):   # 예측·색 변환 — 블록별 값 이미지
            b = bits.read(3) + 2
            transforms.append((kind, b, _read_webp_pixels(bits, (xsize + (1 << b) - 1) >> b, (height + (1 << b) - 1) >> b, False), xsize))
        elif kind == 2:      # 초록 빼기
            transforms.append((2, 0, None, xsize))
        else:                # 색 인덱스(팔레트) — 작은 팔레트는 한 화소에 여러 개를 묶는다
            size = bits.read(8) + 1
            palette = _read_webp_pixels(bits, size, 1, False)
            for k in range(1, size):
                palette[k] = _add_argb(palette[k], palette[k - 1])
            b = 3 if size <= 2 else 2 if size <= 4 else 1 if size <= 16 else 0
            transforms.append((3, b, palette + [0] * (256 - size), xsize))
            xsize = (xsize + (1 << b) - 1) >> b
    px = _read_webp_pixels(bits, xsize, height, True)
    for kind, b, sub, xs in reversed(transforms):
        if kind == 0:
            _undo_webp_predictor(px, xs, height, b, sub)
        elif kind == 1:
            _undo_webp_color(px, xs, height, b, sub)
        elif kind == 2:
            for i, p in enumerate(px):
                g = (p >> 8) & 255
                px[i] = (p & 0xff00ff00) | (((p & 0x00ff00ff) + (g << 16 | g)) & 0x00ff00ff)
        else:
            per, bits_per = 1 << b, 8 >> b
            mask, packed_width, packed, px = (1 << bits_per) - 1, (xs + (1 << b) - 1) >> b, px, []
            for y in range(height):
                line = []
                for p in packed[y * packed_width:(y + 1) * packed_width]:
                    g = (p >> 8) & 255
                    line.extend(sub[(g >> (k * bits_per)) & mask] for k in range(per))
                px.extend(line[:xs])
    return width, height, px


def get_elevation(source_id, r, g, b):
    # type: (str, int, int, int) -> float
    """화소 → 표고 m. 지리원(gsi_dem): x = R·2¹⁶ + G·2⁸ + B를 0.01 m 단위로, x = 2²³은 값 없음(None), 2²³보다 크면 음수(x − 2²⁴).
    AWS terrarium·Mapterhorn: R·256 + G + B/256 − 32768."""
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
        _keep(key, tile or ("aws_terrain", decode_png(_fetch(data_pack.get_service("terrain_tiles", constants.OSM_TERRAIN_URL).format(z=zoom, x=tx, y=ty)))))
    return _CACHE[key]


def _get_spot(index, lng, lat, elevation, source_id, reference_date):
    # type: (int, float, float, float, str, str) -> FeatureInfo
    """경위도 표고 → 표고점(theme terrain, kind spot, 지금 투영 m)."""
    x, y = non_rhino_utils.get_tm_from_wgs84(lng, lat)
    return FeatureInfo(feature_id=10 ** 9 + index, theme="terrain", kind="spot", code="", name="", value=round(elevation, 2), attrs={},
                       sheet="", geometry={"type": "Point", "coordinates": [round(x, 3), round(y, 3)]}, source_id=source_id,
                       reference_date=reference_date, min_x=x, max_x=x, min_y=y, max_y=y)


def get_mapterhorn_grid(bounds):
    # type: (tuple) -> tuple
    """TM bounds → (줌, 화소 건너뛰기(실수, 1 이상), 표고점 간격 m). 간격 = max(TERRAIN_SPOT_SPACING, √(면적 ÷ TERRAIN_MAX_SPOTS)),
    줌 = 화소(512 px 타일)가 그 간격 × TERRAIN_SPOT_SLACK 이하인 가장 낮은 줌(MAPTERHORN_MIN~MAX_ZOOM) — 화소를 간격만큼 건너뛰어 표고점 수가 상한을 넘지 않는다."""
    south, west, north, east = _get_lnglat_bbox(bounds)
    area = max(1.0, (bounds[2] - bounds[0]) * (bounds[3] - bounds[1]))
    spacing = max(constants.TERRAIN_SPOT_SPACING, math.sqrt(area / constants.TERRAIN_MAX_SPOTS))
    pixel0 = constants.WEB_MERCATOR_EQUATOR * math.cos(math.radians((south + north) * 0.5)) / constants.MAPTERHORN_TILE_SIZE   # 줌 0 화소 m
    zoom = max(constants.MAPTERHORN_MIN_ZOOM, min(constants.MAPTERHORN_MAX_ZOOM, int(math.ceil(math.log(pixel0 / (spacing * constants.TERRAIN_SPOT_SLACK), 2)))))
    step = max(1.0, spacing * 2 ** zoom / pixel0)
    return zoom, step, round(pixel0 / 2 ** zoom * step, 1)


def _get_mapterhorn_tile(zoom, tx, ty):
    # type: (int, int, int) -> object
    """Mapterhorn 타일 하나 → decode_webp 결과(ARGB는 array로 — 512 px 한 장 1 MB). 고해상 원천이 없는 곳(404)은 None. 그 밖의 오류는 그대로 올린다."""
    key = ("mapterhorn", zoom, tx, ty)
    if key not in _TERRAIN_TILES:
        try:
            width, height, px = decode_webp(_fetch(data_pack.get_service("mapterhorn", constants.MAPTERHORN_URL).format(z=zoom, x=tx, y=ty),
                                                   timeout=constants.TERRAIN_TIMEOUT_SECONDS))
            tile = (width, height, array.array("I", px))
        except urllib.error.HTTPError as exc:
            if exc.code != 404:
                raise
            tile = None
        if len(_TERRAIN_TILES) >= constants.TERRAIN_TILE_CACHE_MAX:
            _TERRAIN_TILES.clear()
        _TERRAIN_TILES[key] = tile
    return _TERRAIN_TILES[key]


_TERRAIN_TILES = {}   # Mapterhorn 해독 타일 — 같은 대상지를 다시 만들 때 받기·해독(한 장 0.3 s)을 건너뛴다. TERRAIN_TILE_CACHE_MAX를 넘으면 비운다


def _get_mapterhorn_spots(bounds, reference_date):
    # type: (tuple, str) -> list
    """bounds를 덮는 Mapterhorn 타일(get_mapterhorn_grid 줌·건너뛰기) → 표고점. 그 줌 타일이 404(고해상 원천 없음)면 한 단계씩 부모 타일의 같은 구역을
    건너뛰기를 줄여(간격 유지, 최소 1화소 — 거친 원천을 촘촘히 되풀이하지 않는다) 쓴다. 최저 줌도 없으면 RuntimeError."""
    south, west, north, east = _get_lnglat_bbox(bounds)
    zoom, step, _spacing = get_mapterhorn_grid(bounds)
    x0, y0 = non_rhino_utils.get_tile_xy(west, north, zoom)
    x1, y1 = non_rhino_utils.get_tile_xy(east, south, zoom)
    spots = []
    for tx in range(int(x0), int(x1) + 1):
        for ty in range(int(y0), int(y1) + 1):
            up, tile = 0, None
            while tile is None:
                tile = _get_mapterhorn_tile(zoom - up, tx >> up, ty >> up)
                if tile is None:
                    if zoom - up <= constants.MAPTERHORN_MIN_ZOOM:
                        raise RuntimeError(tr("Mapterhorn 지형 타일이 없습니다 — {0}/{1}/{2}", zoom - up, tx >> up, ty >> up))
                    up += 1
            width, height, px = tile
            z, px_tx, px_ty = zoom - up, tx >> up, ty >> up
            size, k = width >> up, max(1.0, step / (1 << up))   # 부모 타일에서 이 타일 구역은 size 화소, 건너뛰기도 그만큼 줄인다
            ox, oy = (tx - (px_tx << up)) * size, (ty - (px_ty << up)) * size
            picks = [int(j * k) for j in range(int(math.ceil(size / k)))]   # 실수 간격 → 가까운 화소
            for py in (oy + j for j in picks):
                lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (px_ty + (py + 0.5) / height) / 2 ** z))))
                if not south <= lat <= north:
                    continue
                for px_x in (ox + j for j in picks):
                    lng = (px_tx + (px_x + 0.5) / width) / 2 ** z * 360.0 - 180.0
                    if not west <= lng <= east:
                        continue
                    p = px[py * width + px_x]
                    spots.append(_get_spot(len(spots), lng, lat, ((p >> 16) & 255) * 256.0 + ((p >> 8) & 255) + (p & 255) / 256.0 - 32768.0,
                                           "mapterhorn", reference_date))
    return spots


def _get_tile_spots(bounds, reference_date):
    # type: (tuple, str) -> tuple
    """Mapterhorn을 못 받을 때 — 일본이면 지리원 5 m 타일(z15, 약 8 m 간격), 아니면 AWS terrarium(z13, 약 30 m). 출력: (표고점, 원천 id 집합 — gsi_dem·aws_terrain)."""
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
                    spots.append(_get_spot(len(spots), lng, lat, elevation, source_id, reference_date))
    return spots, used


def get_terrain_spots(bounds, reference_date):
    # type: (tuple, str) -> tuple
    """bounds를 덮는 지형 표고점(theme terrain, kind spot). Mapterhorn(나라별 라이다 합본, 간격 get_mapterhorn_grid)을 먼저,
    받기·해독이 실패하면(서버 오류·시간 초과 — 404는 부모 타일로) 지리원 5 m·AWS terrarium. 출력: (표고점 목록, 쓴 원천 id 집합 — mapterhorn·gsi_dem·aws_terrain)."""
    try:
        return _get_mapterhorn_spots(bounds, reference_date), {"mapterhorn"}
    except (OSError, ValueError, RuntimeError):   # URLError·시간 초과는 OSError, 해독 실패는 ValueError
        return _get_tile_spots(bounds, reference_date)


def _read_pb(data):
    # type: (bytes) -> list
    """프로토콜 버퍼 메시지 한 겹 → [(필드 번호, 값)] — 값은 varint면 int, 길이 구분이면 bytes(벡터 타일 coverage 층 읽기용)."""
    fields, i = [], 0
    while i < len(data):
        key = shift = 0
        while True:
            c = data[i]
            i += 1
            key |= (c & 127) << shift
            shift += 7
            if c < 128:
                break
        kind = key & 7
        if kind in (0, 2):
            value = shift = 0
            while True:
                c = data[i]
                i += 1
                value |= (c & 127) << shift
                shift += 7
                if c < 128:
                    break
            if kind == 2:
                value, i = data[i:i + value], i + value
        else:   # 64·32비트 고정
            size = 8 if kind == 1 else 4
            value, i = data[i:i + size], i + size
        fields.append((key >> 3, value))
    return fields


def get_mapterhorn_sources(bounds):
    # type: (tuple) -> list
    """bounds에 걸치는 Mapterhorn 원천 → [attribution.json 항목](해상도 순, 고운 것 먼저). coverage 벡터 타일(MAPTERHORN_COVERAGE_ZOOM)의
    source 값 — 타일 하나가 수 km라 범위 밖 이웃 원천이 섞일 수 있다(출처를 덜 적는 것보다 낫다). 못 받으면 []."""
    south, west, north, east = _get_lnglat_bbox(bounds)
    zoom = constants.MAPTERHORN_COVERAGE_ZOOM
    x0, y0 = non_rhino_utils.get_tile_xy(west, north, zoom)
    x1, y1 = non_rhino_utils.get_tile_xy(east, south, zoom)
    try:
        names = set()
        for tx in range(int(x0), int(x1) + 1):
            for ty in range(int(y0), int(y1) + 1):
                data = _fetch(constants.MAPTERHORN_COVERAGE_URL.format(z=zoom, x=tx, y=ty), timeout=constants.TERRAIN_TIMEOUT_SECONDS)
                data = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
                for number, layer in _read_pb(data):
                    if number == 3:   # Tile.layers → Layer.values(4) → Value.string_value(1)
                        names.update(dict(_read_pb(v)).get(1, b"").decode("utf-8") for n, v in _read_pb(layer) if n == 4)
        key = ("mapterhorn_attribution",)
        if key not in _CACHE:
            _keep(key, json.loads(_fetch(constants.MAPTERHORN_ATTRIBUTION_URL, timeout=constants.TERRAIN_TIMEOUT_SECONDS).decode("utf-8")))
        catalog = {item.get("source"): item for item in _CACHE[key]}
    except (OSError, ValueError, IndexError):
        return []
    return sorted((catalog[name] for name in names if name in catalog), key=lambda item: float(item.get("resolution") or 0))


def get_mapterhorn_credit(sources):
    # type: (list) -> str
    """get_mapterhorn_sources → 출처 표기 '제작 기관 원천 이름 해상도 (라이선스); …'. 비면 원천 목록 주소."""
    return "; ".join("%s %s %g m (%s)" % (s.get("producer", ""), s.get("name", ""), float(s.get("resolution") or 0), s.get("license", ""))
                     for s in sources) or "mapterhorn.com/attribution"


# ── 지명 검색 (Nominatim) ───────────────────────────────

def search_places(query, limit):
    # type: (str, int) -> list
    """지명·주소 → [{"name", "center": [lng, lat]}]. 국내 필지 검색이 비었을 때만 부른다(Nominatim 이용 정책: 초당 1건, 식별 가능한 User-Agent).
    네트워크 오류면 빈 목록."""
    url = data_pack.get_service("nominatim", constants.OSM_NOMINATIM_URL) + "?" + urllib.parse.urlencode({"q": query, "format": "jsonv2", "limit": limit})
    try:
        places = json.loads(_fetch(url, timeout=constants.OSM_SEARCH_TIMEOUT_SECONDS).decode("utf-8"))
    except Exception:
        return []
    return [{"name": p.get("display_name", ""), "center": [round(float(p["lon"]), 7), round(float(p["lat"]), 7)]} for p in places]


def get_place_address(lng, lat, lang):
    # type: (float, float, str) -> str
    """경위도 → 짧은 주소 '도로, 동네, 도시'(Nominatim reverse, lang 언어). 해외 대상지 패널 표시용. 못 받으면 ''."""
    key = (round(lng, 5), round(lat, 5), lang)
    if key in _ADDRESS_CACHE:
        return _ADDRESS_CACHE[key]
    url = data_pack.get_service("nominatim_reverse", constants.OSM_NOMINATIM_REVERSE_URL) + "?" + urllib.parse.urlencode(
        {"lat": lat, "lon": lng, "format": "jsonv2", "zoom": 16, "accept-language": lang or "en"})   # 16 = 도로 단위. 18은 건물 안 표기가 도로로 왔다(도쿄역: 'エレベーター;1階')
    try:
        address = json.loads(_fetch(url, timeout=constants.OSM_REVERSE_TIMEOUT_SECONDS).decode("utf-8")).get("address") or {}
    except Exception:
        return ""
    street = address.get("road") or ""
    street = "" if ";" in street else street   # 여러 값 태그(도쿄역 zoom 17: 'JR東京駅;9番線')는 도로 이름이 아니다
    street = " ".join(constants.ADDRESS_ABBREVIATIONS.get(word, word) for word in street.split())   # Greenwich Street → Greenwich St
    area = address.get("suburb") or address.get("neighbourhood") or address.get("quarter") or ""
    city = address.get("city") or address.get("town") or address.get("village") or address.get("county") or address.get("state") or ""
    text = ", ".join(v for v in (street, area, city) if v) or address.get("country", "")
    _ADDRESS_CACHE[key] = text
    return text


_ADDRESS_CACHE = {}   # 같은 자리를 다시 찍어도 묻지 않는다(Nominatim 이용 정책: 초당 1건)


# ── 묶기 ────────────────────────────────────────────────

def load(bounds, today, on_wait=None, details=()):
    # type: (tuple, str, object, tuple) -> ContextData
    """bounds(TM m) 안 OSM 건물·피처 + 지형 표고점 → ContextData. 받는 날짜를 OSM·지형 기준일로 적는다.
    일본: 받아 둔 PLATEAU 팩 건물을 먼저 쓰고 OSM 건물은 그와 겹치지 않는 것만, 지형은 지리원 5 m 타일. 출처는 실제로 쓴 것만(역할은 뒤의 것이 차지).
    details = 켠 디테일 옵션 키 — OSM_OVERPASS_DETAIL_PARTS의 줄만 따로 묻는다(못 받으면 notes에 osm_detail_missing, 나머지는 그대로)."""
    plateau, plateau_sources = load_plateau_buildings(get_lnglat_bounds(bounds))   # 나라별 팩 건물(일본 PLATEAU·네덜란드 PDOK)
    if plateau:   # 팩이 있는 곳 — 도로·수계·녹지 먼저(건물 줄 뺀 질의), OSM 건물은 따로 첫 미러에만(constants.OSM_OVERPASS_BUILDING_QUERY 주석)
        try:
            elements, osm_ok = get_overpass_elements(bounds, constants.OSM_OVERPASS_QUERY.replace(constants.OSM_OVERPASS_BUILDINGS, ""), on_wait=on_wait), True
        except RuntimeError:   # 공개 Overpass 서버가 모두 막힘(2026-10-21 Rhino 실측: 502·504·시간 초과) — 팩 건물·지형만으로 만든다
            elements, osm_ok = [], False   # 출처에 osm이 빠진 것을 context_builder가 보고 알린다
        try:
            osm_buildings = _get_buildings(get_overpass_elements(bounds, constants.OSM_OVERPASS_BUILDING_QUERY, constants.OSM_OVERPASS_URLS[:1], on_wait), today) if osm_ok else []
        except RuntimeError:   # 메우기용이라 못 받아도 넘어간다
            osm_buildings = []
    else:
        elements, osm_ok = get_overpass_elements(bounds, on_wait=on_wait), True
        osm_buildings = _get_buildings(elements, today)
    buildings = plateau + get_buildings_apart(osm_buildings, plateau)
    _apply_public_use(buildings, elements)
    parts = [constants.OSM_OVERPASS_DETAIL_PARTS[key] for key in sorted(details) if key in constants.OSM_OVERPASS_DETAIL_PARTS]
    notes = []
    if parts and osm_ok:   # 디테일 — 따로, 첫 미러에만(붐비면 디테일만 빠진다)
        try:
            elements = elements + get_overpass_elements(bounds, constants.OSM_OVERPASS_DETAIL_QUERY % " ".join(parts), constants.OSM_OVERPASS_URLS[:1], on_wait)
        except RuntimeError:
            notes.append("osm_detail_missing")
    spots, terrain_ids = get_terrain_spots(bounds, today)
    crs = non_rhino_utils.get_crs_label()
    sources = [DataSource("osm", "OpenStreetMap (Overpass API)", "https://www.openstreetmap.org/copyright", today, today, crs,
                          "ODbL 1.0 — © OpenStreetMap contributors", tr("건물 높이는 height·building:levels 태그, 없으면 기본값"))] if osm_ok else []
    if "mapterhorn" in terrain_ids:   # 이름 = 표고점 간격(패널·좌표계 줄), 비고 = 실제 원천 기관(출처 줄 — CC BY 등은 기관 표기가 조건)
        terrain_sources = get_mapterhorn_sources(bounds)
        sources.append(DataSource("mapterhorn", tr("Mapterhorn 지형(표고점 약 {0} m 간격)", get_mapterhorn_grid(bounds)[2]), "https://mapterhorn.com/attribution",
                                  "", today, crs, ", ".join(sorted({s.get("license", "") for s in terrain_sources})) or tr("원천별 공개 라이선스 — 출처 표기"),
                                  get_mapterhorn_credit(terrain_sources)))
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
    return ContextData(bounds=tuple(bounds), buildings=buildings, features=features, sources=sources, notes=notes)


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
