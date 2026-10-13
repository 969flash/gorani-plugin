"""대지검토 패널의 지도 데이터 제공자.

로컬 DB의 필지(EPSG:5186)를 WGS84 GeoJSON으로 바꾸고 타일·초기 뷰 설정을 준다.
Rhino를 import하지 않아 python3로 바로 테스트할 수 있다.
"""

import constants
import lot_db
import non_rhino_utils
import pnu_loader

# 지도 전용 상수 — 패널 지도에서만 쓰므로 constants.py가 아니라 여기 둔다.
VWORLD_TILE_URL_TEMPLATE = (
    "https://api.vworld.kr/req/wmts/1.0.0/%s/Base/{z}/{y}/{x}.png"
)
VWORLD_ATTRIBUTION = "© VWorld"
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
# 해외 배경(VWorld는 국내만) — OSM 표준 타일. 소량 사용·출처 표기 조건(타일 이용 정책). CARTO는 2026-10 기준 키가 필요해 쓰지 않는다
ABROAD_TILE_URL = OSM_TILE_URL
ABROAD_ATTRIBUTION = OSM_ATTRIBUTION
MAP_CENTER = [126.9784, 37.5665]  # 서울시청 (WGS84 lng, lat)
MAP_ZOOM = 16
COORDINATE_DECIMALS = 7  # GeoJSON 좌표 반올림 자리수 (약 1cm)


def get_tile_config():
    # type: () -> dict
    """지도 타일 설정을 만든다.

    입력:
        없음. VWORLD_API_KEY 환경변수 또는 프로젝트 .env를 읽는다.
    처리:
        키가 있으면 VWorld WMTS를 기본으로, 없으면 OSM만 쓴다.
    출력:
        ``{"url", "fallback_url", "attribution"}`` 딕셔너리.
    """
    api_key = pnu_loader.get_local_env_value(constants.VWORLD_API_KEY_ENV)
    if api_key:
        return {
            "url": VWORLD_TILE_URL_TEMPLATE % api_key,
            "fallback_url": OSM_TILE_URL,
            "attribution": VWORLD_ATTRIBUTION,
            "abroad_url": ABROAD_TILE_URL, "abroad_attribution": ABROAD_ATTRIBUTION,
        }
    return {
        "url": OSM_TILE_URL,
        "fallback_url": OSM_TILE_URL,
        "attribution": OSM_ATTRIBUTION,
        "abroad_url": ABROAD_TILE_URL, "abroad_attribution": ABROAD_ATTRIBUTION,
    }


def get_map_init():
    # type: () -> dict
    """지도 초기 뷰(서울시청 중심)를 만든다. ``{"center": [lng, lat], "zoom", "korea_bounds": [서, 남, 동, 북]}`` — 화면 중심이 한국 밖이면 해외 타일."""
    return {"center": list(MAP_CENTER), "zoom": MAP_ZOOM, "korea_bounds": list(non_rhino_utils.KOREA_LNGLAT_BOUNDS)}


def get_wgs84_ring(ring):
    # type: (list) -> list
    """EPSG:5186 좌표 링을 WGS84 ``[lng, lat]`` 링으로 변환한다."""
    converted = []
    for point in ring:
        lng, lat = non_rhino_utils.get_wgs84_from_tm(float(point[0]), float(point[1]))
        converted.append(
            [round(lng, COORDINATE_DECIMALS), round(lat, COORDINATE_DECIMALS)]
        )
    return converted


def _get_wgs84_geometry(geometry):
    # type: (dict) -> dict
    """GeoJSON Polygon·MultiPolygon을 구멍 포함 그대로 WGS84로 변환한다."""
    geometry_type = geometry.get("type")
    if geometry_type == "Polygon":
        coordinates = [get_wgs84_ring(ring) for ring in geometry["coordinates"]]
    elif geometry_type == "MultiPolygon":
        coordinates = [
            [get_wgs84_ring(ring) for ring in polygon]
            for polygon in geometry["coordinates"]
        ]
    else:
        raise ValueError("지원하지 않는 GeoJSON 형상: %s" % geometry_type)
    return {"type": geometry_type, "coordinates": coordinates}


def _get_jibun(address):
    # type: (str) -> str
    """주소에서 동 이하 지번만 남긴다. 시·구는 지도 툴팁에서 반복이라 뺀다."""
    parts = (address or "").split()
    return " ".join(parts[2:]) if len(parts) > 2 else (address or "")


def _get_feature(lot, properties):
    # type: (lot_db.LotInfo, dict) -> dict
    """LotInfo 하나를 WGS84 GeoJSON Feature로 만든다."""
    return {
        "type": "Feature",
        "geometry": _get_wgs84_geometry(lot.geometry),
        "properties": properties,
    }


def get_parcels_in_bbox(bbox, limit=5000, database_path=None):
    # type: (list, int, object) -> dict
    """지도 뷰포트 경계상자 안의 필지를 GeoJSON으로 조회한다.

    입력:
        bbox: WGS84 ``[minLng, minLat, maxLng, maxLat]``. limit: 최대 필지 수.
    처리:
        경계상자 모서리를 EPSG:5186으로 바꿔 DB를 조회하고 형상을 WGS84로 변환한다.
    출력:
        ``{"geojson": FeatureCollection, "truncated": bool}``.
        properties = {pnu, address, jibun, land_category, area}.
    """
    min_lng, min_lat, max_lng, max_lat = [float(value) for value in bbox]
    x_low, y_low = non_rhino_utils.get_tm_from_wgs84(min_lng, min_lat)
    x_high, y_high = non_rhino_utils.get_tm_from_wgs84(max_lng, max_lat)
    lots, truncated = lot_db.load_parcels_in_bounds(
        min(x_low, x_high),
        min(y_low, y_high),
        max(x_low, x_high),
        max(y_low, y_high),
        limit,
        database_path,
    )
    features = [
        _get_feature(
            lot,
            {
                "pnu": lot.pnu,
                "address": lot.address,
                "jibun": _get_jibun(lot.address),
                "land_category": lot.land_category,
                "area": lot.area,
            },
        )
        for lot in lots
    ]
    return {
        "geojson": {"type": "FeatureCollection", "features": features},
        "truncated": truncated,
    }


def get_parcels_geojson(pnus, role, database_path=None):
    # type: (list, str, object) -> dict
    """PNU 목록을 역할 태그가 붙은 GeoJSON FeatureCollection으로 만든다.

    입력:
        pnus: PNU 목록. role: 지도 스타일용 역할 문자열 (예: "target").
    처리:
        DB에서 필지를 읽어 WGS84로 변환한다. 없는 PNU는 lot_db가 KeyError를 낸다.
    출력:
        FeatureCollection. properties = {pnu, address, land_category, area, role}.
    """
    lots = lot_db.load(pnus, database_path).lots
    features = [
        _get_feature(
            lot,
            {
                "pnu": lot.pnu,
                "address": lot.address,
                "land_category": lot.land_category,
                "area": lot.area,
                "role": role,
            },
        )
        for lot in lots
    ]
    return {"type": "FeatureCollection", "features": features}


def get_parcel_centers(pnus, database_path=None):
    # type: (list, object) -> dict
    """PNU별 필지 중심(경계상자 중심)의 WGS84 좌표를 만든다.

    출력: ``{pnu: [lng, lat]}``.
    """
    centers = {}
    for lot in lot_db.load(pnus, database_path).lots:
        center_x, center_y = non_rhino_utils.get_center_xy_from_bounds(
            (lot.min_x, lot.max_x, lot.min_y, lot.max_y)
        )
        lng, lat = non_rhino_utils.get_wgs84_from_tm(center_x, center_y)
        centers[lot.pnu] = [
            round(lng, COORDINATE_DECIMALS),
            round(lat, COORDINATE_DECIMALS),
        ]
    return centers
