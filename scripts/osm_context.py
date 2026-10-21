"""해외 대상지 컨텍스트 — OSM(Overpass API) 건물·도로·철도·수계·녹지 + AWS Terrain Tiles 지형을 context_db와 같은 형식으로.

국내는 로컬 DB(context_db)를 쓰고, 대상지가 한국 밖이면(non_rhino_utils.is_local_projection) context_builder가 이 모듈을 부른다.
좌표는 non_rhino_utils의 지금 투영(대상지 중심 지역 횡메르카토르) m. 표준 라이브러리만 쓴다(urllib·json·zlib).

출처 표기: 건물·도로 등 "© OpenStreetMap contributors"(ODbL — 산출물은 출처 표기만, DB로 재배포하지 않는다),
지형 "Terrain Tiles, Mapzen/AWS Open Data(SRTM·GMTED 등 공개 DEM)".
"""

import json
import math
import struct
import urllib.parse
import urllib.request
import zlib

import constants
import non_rhino_utils
from context_db import BuildingInfo, ContextData, DataSource, FeatureInfo
from i18n import tr

_CACHE = {}   # (질의 종류, bbox) → 응답 — 같은 대상지를 다시 생성할 때 Overpass를 또 부르지 않는다


# ── 받기 ────────────────────────────────────────────────

def _get_lnglat_bbox(bounds):
    # type: (tuple) -> tuple
    """TM bounds(min_x, min_y, max_x, max_y) → (south, west, north, east) 경위도."""
    corners = [non_rhino_utils.get_wgs84_from_tm(x, y) for x in (bounds[0], bounds[2]) for y in (bounds[1], bounds[3])]
    return (min(c[1] for c in corners), min(c[0] for c in corners), max(c[1] for c in corners), max(c[0] for c in corners))


def _fetch(url, data=None):
    # type: (str, bytes) -> bytes
    request = urllib.request.Request(url, data=data, headers={"User-Agent": constants.OSM_USER_AGENT})
    with urllib.request.urlopen(request, timeout=constants.OSM_TIMEOUT_SECONDS) as response:
        return response.read()


def get_overpass_elements(bounds):
    # type: (tuple) -> list
    """bounds 안 OSM 요소(out geom). 미러를 차례로 시도한다. 실패하면 RuntimeError."""
    bbox = "%.6f,%.6f,%.6f,%.6f" % _get_lnglat_bbox(bounds)
    key = ("overpass", bbox)
    if key in _CACHE:
        return _CACHE[key]
    query = constants.OSM_OVERPASS_QUERY.replace("{bbox}", bbox)
    errors = []
    for endpoint in constants.OSM_OVERPASS_URLS:
        try:
            body = _fetch(endpoint, urllib.parse.urlencode({"data": query}).encode("utf-8"))
            _CACHE[key] = json.loads(body.decode("utf-8"))["elements"]
            return _CACHE[key]
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
            feature_id=len(features) + 1, theme=theme, kind=kind, code=tags.get("highway") or tags.get("railway") or tags.get("waterway") or "",
            name=tags.get("name", ""), value=value, attrs={"osm": "%s/%d" % (element["type"], element["id"])}, sheet="",
            geometry=geometry, source_id="osm", reference_date=reference_date, min_x=min_x, max_x=max_x, min_y=min_y, max_y=max_y,
        ))
    return features


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


def get_terrain_spots(bounds, reference_date):
    # type: (tuple, str) -> list
    """bounds를 덮는 지형 타일을 받아 표고점(theme terrain, kind spot)으로. 간격 = 타일 픽셀 × OSM_TERRAIN_STEP."""
    south, west, north, east = _get_lnglat_bbox(bounds)
    zoom = constants.OSM_TERRAIN_ZOOM
    x0, y0 = non_rhino_utils.get_tile_xy(west, north, zoom)
    x1, y1 = non_rhino_utils.get_tile_xy(east, south, zoom)
    spots = []
    for tx in range(int(x0), int(x1) + 1):
        for ty in range(int(y0), int(y1) + 1):
            key = ("terrain", zoom, tx, ty)
            if key not in _CACHE:
                _CACHE[key] = decode_png(_fetch(constants.OSM_TERRAIN_URL.format(z=zoom, x=tx, y=ty)))
            width, height, channels, rows = _CACHE[key]
            for py in range(0, height, constants.OSM_TERRAIN_STEP):
                lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (ty + (py + 0.5) / height) / 2 ** zoom))))
                for px in range(0, width, constants.OSM_TERRAIN_STEP):
                    lng = (tx + (px + 0.5) / width) / 2 ** zoom * 360.0 - 180.0
                    if not (west <= lng <= east and south <= lat <= north):
                        continue
                    r, g, b = rows[py][px * channels:px * channels + 3]
                    elevation = r * 256.0 + g + b / 256.0 - 32768.0
                    x, y = non_rhino_utils.get_tm_from_wgs84(lng, lat)
                    spots.append(FeatureInfo(
                        feature_id=10 ** 9 + len(spots), theme="terrain", kind="spot", code="", name="", value=round(elevation, 2), attrs={},
                        sheet="", geometry={"type": "Point", "coordinates": [round(x, 3), round(y, 3)]}, source_id="aws_terrain",
                        reference_date=reference_date, min_x=x, max_x=x, min_y=y, max_y=y,
                    ))
    return spots


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
    """bounds(TM m) 안 OSM 건물·피처 + 지형 표고점 → ContextData. 받는 날짜를 기준일로 적는다."""
    elements = get_overpass_elements(bounds)
    sources = [
        DataSource("osm", "OpenStreetMap (Overpass API)", "https://www.openstreetmap.org/copyright", today, today,
                   non_rhino_utils.get_crs_label(), "ODbL 1.0 — © OpenStreetMap contributors", tr("건물 높이는 height·building:levels 태그, 없으면 기본값")),
        DataSource("aws_terrain", "Terrain Tiles (AWS Open Data, terrarium)", "https://registry.opendata.aws/terrain-tiles/", "", today,
                   non_rhino_utils.get_crs_label(), tr("공개(출처 표기)"), tr("SRTM·GMTED 등 혼합 DEM, 해상도 지역별 상이(약 30 m)")),
    ]
    buildings = _get_buildings(elements, today)
    _apply_public_use(buildings, elements)
    return ContextData(bounds=tuple(bounds), buildings=buildings,
                       features=_get_features(elements, today) + get_terrain_spots(bounds, today), sources=sources)


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
