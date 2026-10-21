"""Gorani 패널의 지도 데이터 제공자.

로컬 DB의 필지(EPSG:5186)를 WGS84 GeoJSON으로 바꾸고 타일·초기 뷰 설정을 준다.
Rhino를 import하지 않아 python3로 바로 테스트할 수 있다.
"""

import json
import urllib.request

import constants
import lot_db
import non_rhino_utils
import pnu_loader
from i18n import tr

# 지도 전용 상수 — 패널 지도와 항공사진 시트(sheet_svg가 get_tile_config를 부른다)만 쓰므로 constants.py가 아니라 여기 둔다.
VWORLD_TILE_URL_TEMPLATE = (
    "https://api.vworld.kr/req/wmts/1.0.0/%s/Base/{z}/{y}/{x}.png"
)
VWORLD_ATTRIBUTION = "© VWorld"
OSM_TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
OSM_ATTRIBUTION = "© OpenStreetMap contributors"
# 해외 배경(VWorld는 국내만) — OSM 표준 타일. 소량 사용·출처 표기 조건(타일 이용 정책). CARTO는 2026-10 기준 키가 필요해 쓰지 않는다
ABROAD_TILE_URL = OSM_TILE_URL
ABROAD_ATTRIBUTION = OSM_ATTRIBUTION
# 위성·항공 영상 — 국내는 VWorld 영상지도(국토지리정보원 정사영상, 줌 19까지, 2026-10-14 키로 받아짐 확인)
VWORLD_AERIAL_URL_TEMPLATE = "https://api.vworld.kr/req/wmts/1.0.0/%s/Satellite/{z}/{y}/{x}.jpeg"
VWORLD_AERIAL_ATTRIBUTION = "© VWorld 영상지도"
# 키가 없거나 해외면 Esri World Imagery(키 없이 받아짐). 이용 조건은 Esri 약관 — 확인 필요(소량·출처 표기로만 쓴다)
ESRI_AERIAL_URL = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
ESRI_AERIAL_ATTRIBUTION = "Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community"
MAP_CENTER = [126.9784, 37.5665]  # 서울시청 (WGS84 lng, lat) — IP로 위치를 짐작하지 못했을 때
MAP_ZOOM = 16
# 패널 첫 화면 — 사용자 IP로 도시를 짐작한다(위치 권한 창이 없다). ipinfo.io는 키 없이 받아짐(2026-10-21 확인, 0.3 s).
# 키 없는 사용 한도는 IP별이라 패널을 열 때 한 번이면 넉넉하다(한도 수치는 확인 필요). IP 위치는 도시 수준(수~수십 km)이라 도시가 보이는 배율로 연다
IP_LOCATE_URL = "https://ipinfo.io/json"
IP_LOCATE_TIMEOUT_SECONDS = 2
IP_MAP_ZOOM = 12   # 패널 폭 400 px에 약 12 km(서울 위도)
COORDINATE_DECIMALS = 7  # GeoJSON 좌표 반올림 자리수 (약 1cm)


def get_tile_config():
    # type: () -> dict
    """지도 타일 설정을 만든다.

    입력:
        없음. VWORLD_API_KEY 환경변수 또는 프로젝트 .env를 읽는다.
    처리:
        키가 있으면 VWorld WMTS(지도·영상)를 기본으로, 없으면 OSM 지도 + Esri 영상.
    출력:
        ``{"url", "fallback_url", "attribution", "abroad_url", "abroad_attribution",
        "aerial_url", "aerial_attribution", "abroad_aerial_url", "abroad_aerial_attribution"}``.
        abroad_aerial_url(Esri)은 국내 영상을 못 받을 때의 폴백도 겸한다.
    """
    config = {
        "url": OSM_TILE_URL, "fallback_url": OSM_TILE_URL, "attribution": OSM_ATTRIBUTION,
        "abroad_url": ABROAD_TILE_URL, "abroad_attribution": ABROAD_ATTRIBUTION,
        "aerial_url": ESRI_AERIAL_URL, "aerial_attribution": ESRI_AERIAL_ATTRIBUTION,
        "abroad_aerial_url": ESRI_AERIAL_URL, "abroad_aerial_attribution": ESRI_AERIAL_ATTRIBUTION,
    }
    api_key = pnu_loader.get_local_env_value(constants.VWORLD_API_KEY_ENV)
    if api_key:
        config.update(url=VWORLD_TILE_URL_TEMPLATE % api_key, attribution=VWORLD_ATTRIBUTION,
                      aerial_url=VWORLD_AERIAL_URL_TEMPLATE % api_key, aerial_attribution=tr(VWORLD_AERIAL_ATTRIBUTION))
    import context_builder   # 호스트 판정 — 모듈 수준 import는 순환
    if not constants.HOST_LABELS[context_builder.get_host()].get("aerial", True):   # Blender — 위성 영상 없음(패널은 [위성]을 숨긴다)
        config.update(aerial_url="", abroad_aerial_url="")
    return config


def get_ip_center():
    # type: () -> list
    """사용자 IP로 지도 첫 위치를 짐작한다(패널 첫 init에 한 번).

    입력:
        없음.
    처리:
        IP 위치 서비스 응답의 loc("위도,경도")을 읽는다. 오프라인·서비스 장애·이상한 응답이면 짐작하지 않는다.
    출력:
        ``[lng, lat]`` 또는 None(서울시청으로 연다).
    """
    import context_builder   # 호스트 판정 — 모듈 수준 import는 순환
    if not constants.HOST_LABELS[context_builder.get_host()].get("ip_center", True):   # Blender — 확장 약관: 사용자가 하지 않은 제3자 전송 금지
        return None
    try:
        with urllib.request.urlopen(IP_LOCATE_URL, timeout=IP_LOCATE_TIMEOUT_SECONDS) as response:
            lat, lng = (float(value) for value in json.loads(response.read().decode("utf-8"))["loc"].split(","))
    except Exception:   # 패널 열기를 막지 않는다
        return None
    return [lng, lat] if -90 <= lat <= 90 and -180 <= lng <= 180 else None   # nan은 JSON으로 못 보낸다


def get_map_init(center=None):
    # type: (list) -> dict
    """지도 초기 뷰를 만든다 — center(IP로 짐작한 [lng, lat])가 있으면 그 도시, 없으면 서울시청.
    ``{"center": [lng, lat], "zoom", "korea_bounds": [서, 남, 동, 북], "korea_cut": [경도, 위도]}`` — 화면 중심이 한국 밖이면 해외 타일.
    korea_cut = 사각형 안 일본 모서리(이 경도 동쪽·위도 남쪽은 한국 밖, non_rhino_utils.is_korea와 같은 판정)."""
    return {"center": list(center or MAP_CENTER), "zoom": IP_MAP_ZOOM if center else MAP_ZOOM,
            "korea_bounds": list(non_rhino_utils.KOREA_LNGLAT_BOUNDS), "korea_cut": list(non_rhino_utils.KOREA_JAPAN_CORNER)}


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
