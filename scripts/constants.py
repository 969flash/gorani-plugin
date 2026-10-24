"""Gorani 상수 — 한 파일에 근거 주석과 함께 둔다. 다른 곳에 매직넘버 금지.

필지 DB·주소 해석·VWorld 호출·컨텍스트 생성 상수만 둔다. 컨텍스트(건물·도로·지형·수계) 상수는 그 모듈을 만들 때
여기에 절을 추가한다.
"""

import os

# ─────────────────────────────────────────────────────────
# 도구 이름 — 명령 앨리어스·툴바·패널 캡션이 같은 이름을 쓴다
# ─────────────────────────────────────────────────────────
TOOL_NAME = "Gorani"

# ─────────────────────────────────────────────────────────
# 지오메트리 범위·정밀도 (내부 단위 m)
# ─────────────────────────────────────────────────────────
LOT_CONTEXT_RADIUS = 150.0      # 대상 필지 경계에서 주변 필지 조회 기본 거리 150m
GEOMETRY_TOLERANCE = 0.001      # 내부 평면 연산 허용오차 0.001m (1mm)
ANGLE_TOLERANCE = 0.0175        # 각도 허용오차 약 1도(rad). 커브 단순화에 쓴다
SPATIAL_OVERLAP_MIN_AREA = 0.01  # DB 공간교차에서 무시할 미세 중첩면적 ㎡

# ─────────────────────────────────────────────────────────
# 행정·데이터·경로
# ─────────────────────────────────────────────────────────
# PNU 앞 2자리 → (시도명, 데이터 팩 파일 접두어). 2026-09 기준 16개 시도 — 강원 51·전북 52(특별자치도 전환),
# 전남광주통합특별시 12(광주 29·전남 46 통합). 근거: data/raw/전국_토지이용계획정보 AL_D155_<코드> 파일 목록(2026-08-26)
# 통합으로 코드가 바뀐 시도 — 토지특성정보(2026-05)는 아직 옛 코드다. 빌드 때 시군구 이름으로 새 코드에 맞춘다
# (dev_database_builder.get_legacy_sgg_map). 예: 광주 동구 29110 → 12210, 전남 광양 46230 → 12190, 목포 46110 → 12110
SIDO_LEGACY_CODES = {"12": ("29", "46")}
SIDO = {
    "11": ("서울특별시", "seoul"), "26": ("부산광역시", "busan"), "27": ("대구광역시", "daegu"), "28": ("인천광역시", "incheon"),
    "30": ("대전광역시", "daejeon"), "31": ("울산광역시", "ulsan"), "36": ("세종특별자치시", "sejong"), "41": ("경기도", "gyeonggi"),
    "43": ("충청북도", "chungbuk"), "44": ("충청남도", "chungnam"), "47": ("경상북도", "gyeongbuk"), "48": ("경상남도", "gyeongnam"),
    "50": ("제주특별자치도", "jeju"), "51": ("강원특별자치도", "gangwon"), "52": ("전북특별자치도", "jeonbuk"),
    "12": ("전남광주통합특별시", "jeonnamgwangju"),
}
DATABASE_CRS = 5186                   # 내부 형상 좌표계 (GRS80 중부원점, EPSG:5186)
# 수치지형도 도엽은 지역마다 원점이 다르다(.prj 이름 → EPSG). 빌드 때 전부 DATABASE_CRS로 옮긴다
UTMK_CRS = 5179   # UTM-K — 일부 도엽(충남 36603020)의 .prj
KOREA_2000_BELTS = {"East_Sea_Belt_2010": 5188, "West_Belt_2010": 5185, "Central_Belt_2010": 5186, "East_Belt_2010": 5187}
SEOUL_SOURCE_CRS = 5174               # 서울 UPIS 공개 SHP 좌표계
RAW_DATA_DIRNAME = "data/raw"         # 공공 원천 데이터 보관 (gitignore)
LAND_CHAR_DIRNAME = "data/raw/vworld_토지특성정보"  # 시군구별 SHP 폴더 (수동 다운로드)
LAND_CHAR_ENCODING = "cp949"          # .cpg는 UTF-8이라 적혀 있으나 실제는 CP949
DATABASE_PATH = "data/seoul_site.db"  # Rhino가 읽는 필지 SQLite DB (스키마 v5)
DATABASE_SCHEMA_VERSION = 5           # 5: parcel_land_use(필지별 지역지구등 지정 현황) 추가
RESULT_DIRNAME = "result"             # 산출물(3dm·베이스맵·현황도) 저장 루트 (gitignore)
# 쓰기 자리(data/·result/·.env)의 기준 폴더. 저장소·폴더 배포판은 루트에 data/가 있어 루트를 쓴다.
# Yak 설치본은 패키지 폴더가 업데이트 때 통째로 바뀌므로 사용자 홈 아래 ~/Gorani를 쓴다.
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOME_DIR = _ROOT_DIR if os.path.isdir(os.path.join(_ROOT_DIR, "data")) else os.path.join(os.path.expanduser("~"), TOOL_NAME)

# ─────────────────────────────────────────────────────────
# 토지이용계획정보 — 필지별 지역지구등 지정 현황
# 국토교통부 제공 파일데이터(공공데이터포털). 분기 갱신, 시도별 CSV.
# 토지이음의 "지역지구등 지정여부"와 같은 원천이라 화면과 결과가 일치한다.
# 공간교차가 필요 없다. 고유번호가 곧 PNU라 parcels와 바로 붙는다.
# ─────────────────────────────────────────────────────────
LAND_USE_DIRNAME = "data/raw/전국_토지이용계획정보"
LAND_USE_ENCODING = "cp949"          # .csv에 표기가 없다. 실제 바이트로 확인했다
LAND_USE_FILE_FORMAT = "AL_D155_%s_"  # 시도코드(PNU 앞 2자리)별 파일 접두어
LAND_USE_SOURCE_ID = "molit_land_use"  # data_sources 행 id — 기준일(데이터기준일자 최댓값)을 패널에 보인다

# 저촉여부 — 대지에 실제로 걸리는지를 가른다
LAND_USE_INCLUDED = "포함"   # 필지 전체가 그 지역지구 안에 있다
LAND_USE_OVERLAP = "저촉"    # 필지 일부가 걸친다
LAND_USE_ADJACENT = "접함"   # 경계에 닿아 있을 뿐 필지에 걸리지는 않는다
LAND_USE_APPLIED = (LAND_USE_INCLUDED, LAND_USE_OVERLAP)

# ─────────────────────────────────────────────────────────
# 지목 — 토지특성정보 A11이 지목명("대", "도로")을 그대로 준다.
#        공간정보관리법 시행령 제58조의 28개 지목. 부호 파싱은 하지 않는다.
# ─────────────────────────────────────────────────────────
LAND_CATEGORY_ROAD = "도로"
# 수계로 볼 지목 — 하천·구거(도랑)·유지(연못·저수지). 제방은 수면이 아니라 뺀다.
LAND_CATEGORIES_WATER = ("하천", "구거", "유지")

# 토지특성정보 A13(용도지역코드1) → UPIS 코드. 대장 값이라 공간교차보다 정확하다.
# 표에 없는 코드(00 지정되지않음, 44 개발제한구역, 51 용도미지정, 61~ 비도시지역)는
# 용도지역으로 확정하지 않는다. 개발제한구역은 용도구역이라 overlays에서 본다.
LAND_CHAR_ZONE_CODES = {
    "11": "UQA111", "12": "UQA112",
    "13": "UQA121", "14": "UQA122", "15": "UQA123",
    "16": "UQA130", "17": "UQA129",
    "21": "UQA210", "22": "UQA220", "23": "UQA230", "24": "UQA240",
    "31": "UQA310", "32": "UQA320", "33": "UQA330",
    "41": "UQA410", "42": "UQA420", "43": "UQA430",
}

# ─────────────────────────────────────────────────────────
# 계획 오버레이 — UPIS 용도지역·용도지구·용도구역·도시계획시설·지구단위계획
# DB의 overlays 테이블 한 곳에 담고 theme/kind로 구분한다.
# 수집 원천 목록은 dev_database_builder.SEOUL_SOURCES에 있다.
# ─────────────────────────────────────────────────────────
OVERLAY_THEME_ZONE = "zone"          # 용도지역
OVERLAY_THEME_DISTRICT = "district"  # 용도지구
OVERLAY_THEME_AREA = "area"          # 용도구역
OVERLAY_THEME_FACILITY = "facility"  # 도시계획시설
OVERLAY_THEME_PLAN = "plan"          # 지구단위계획
# 서울 외 시도는 계획 도형 원천(UPIS 열린데이터)이 없다 — 토지이용계획 CSV의 필지별 지정 코드로 필지를 합쳐 만든다
# (dev_database_builder.derive_overlays). 코드 앞부분 → (theme, kind, UPIS 레이어). 긴 접두가 먼저 맞는다.
# 근거: 서울 overlays의 code 열(UPIS ATRB_SE)과 토지이용계획 코드가 같은 체계(예: UQA122·UQF132·UQS122·UQT220, 2026-10-12 확인)
DERIVED_OVERLAY_CODES = (
    ("UQA001", None, None, None),   # '도시지역' — 하위 용도지역의 상위 묶음이라 건너뛴다
    ("UQA", "zone", "용도지역", "UQ111"), ("UQB", "zone", "용도지역", "UQ111"), ("UQC", "zone", "용도지역", "UQ111"),
    ("UQD", "zone", "용도지역", "UQ111"),
    ("UQF", "district", "경관지구", "UQ121"), ("UQH", "district", "고도지구", "UQ123"), ("UQI", "district", "방화지구", "UQ124"),
    ("UQJ", "district", "방재지구", "UQ125"), ("UQK", "district", "보호지구", "UQ126"), ("UQM", "district", "취락지구", "UQ128"),
    ("UQN", "district", "개발진흥지구", "UQ129"), ("UQO", "district", "특정용도제한지구", "UQ130"), ("UQP", "district", "기타용도지구", "UQ131"),
    ("UDV", "area", "개발제한구역", "UQ141"), ("UQT600", "area", "도시자연공원구역", "UQ142"),
    ("UQQ300", "plan", "지구단위계획구역", "UQ161"),
    ("UQS1", "facility", "도로", "UQ151"), ("UQS2", "facility", "주차장", "UQ152"), ("UQS3", "facility", "자동차정류장", "UQ152"),
    ("UQS5", "facility", "철도", "UQ152"), ("UQS8", "facility", "공항", "UQ152"), ("UQS", "facility", "기타교통시설", "UQ152"),
    ("UQT1", "facility", "광장", "UQ153"), ("UQT2", "facility", "공원", "UQ153"), ("UQT3", "facility", "녹지", "UQ153"),
    ("UQT4", "facility", "유원지", "UQ153"), ("UQT5", "facility", "공공공지", "UQ153"), ("UQT", "facility", "공간시설", "UQ153"),
    ("UQW", "facility", "방재시설", "UQ155"),
)
DERIVED_OVERLAY_TILE = 1000.0   # m — 합친 도형을 이 격자로 나눈다. 시도 전체가 한 도형이면 패널 조회가 느리다

# 도시계획시설의 세부 종별. 원천 SHP의 LCLAS_CL(대분류 코드)로 판정한다.
# 코드에 없으면 원천 레이어의 기본 kind를 쓴다.
FACILITY_KINDS = {
    # UQ153 공간시설
    "UQT100": "광장", "UQT110": "광장",
    "UQT200": "공원", "UQT220": "공원", "UQT290": "공원",
    "UQT300": "녹지", "UQT390": "녹지",
    "UQT400": "유원지",
    "UQT500": "공공공지", "UQT510": "공공공지",
    # UQ152 교통시설(도로외)
    "UQS200": "주차장", "UQS201": "주차장",
    "UQS300": "자동차정류장",
    "UQS400": "자동차검사시설",
    "UQS500": "철도", "UQS520": "철도",
    "UQS550": "궤도",
    "UQS800": "공항",
}

# 도시계획시설 도로의 등급 — 도시·군계획시설의 결정·구조 및 설치기준에 관한 규칙 제9조.
# UPIS 코드 → (등급명, 최소너비 m, 최대너비 m). 최대 None은 상한 없음.
# 결정 폭원의 구간일 뿐 실측 폭이 아니다. 정확한 폭은 도형에서 다시 재야 한다.
ROAD_GRADE_WIDTHS = {
    "UQS111": ("광로1류", 70.0, None),
    "UQS112": ("광로2류", 50.0, 70.0),
    "UQS113": ("광로3류", 40.0, 50.0),
    "UQS114": ("대로1류", 35.0, 40.0),
    "UQS115": ("대로2류", 30.0, 35.0),
    "UQS116": ("대로3류", 25.0, 30.0),
    "UQS117": ("중로1류", 20.0, 25.0),
    "UQS118": ("중로2류", 15.0, 20.0),
    "UQS119": ("중로3류", 12.0, 15.0),
    "UQS120": ("소로1류", 10.0, 12.0),
    "UQS121": ("소로2류", 8.0, 10.0),
    "UQS122": ("소로3류", 0.0, 8.0),
    "UQS190": ("기타도로시설", None, None),  # 폭원 미상 — 도형에서 재야 한다
}

# ─────────────────────────────────────────────────────────
# PNU — 연속지적도 A1 기준: 법정동코드 10 + 일반/산 1 + 본번 4 + 부번 4
# ─────────────────────────────────────────────────────────
PNU_LENGTH = 19
PNU_LEGAL_DONG_LENGTH = 10
PNU_LAND_TYPE_INDEX = 10
PNU_MAIN_START = 11
PNU_MAIN_END = 15
PNU_SUB_START = 15
PNU_SUB_END = 19
PNU_LAND_TYPE_ORDINARY = "1"
PNU_LAND_TYPE_MOUNTAIN = "2"
TEST_PNU = "1123010300106760006"       # DB 검증용 PNU (동대문구 제기동 676-6)

# 필지 검색 — Rhino 실행 중 로컬 SQLite에서 후보를 보여 주는 상한
ADDRESS_SEARCH_MAX_RESULTS = 20

# 패널 더보기 메뉴의 바깥 링크(open_url) — 키만 받아 이 주소를 연다(임의 URL은 받지 않는다)
PANEL_LINKS = {
    "website": "https://969flash.github.io/gorani/",   # 고라니 웹페이지 — 설치·사용법
    "website_en": "https://969flash.github.io/gorani/en/",   # 같은 페이지 영어판 — 패널 언어가 한국어가 아니면 이쪽
}

# 토지이음(국토교통부) 토지이용계획 열람 상세 — 패널 필지 정보의 [토지이음 ↗](open_eum)과 parcels.csv eum_url.
# mode=search·isNoScr=script를 붙인 형태로 pnu가 상세 폼에 실리는 것을 확인했다.
EUM_LAND_USE_URL = (
    "https://www.eum.go.kr/web/ar/lu/luLandDet.jsp"
    "?pnu=%s&mode=search&isNoScr=script"
)

# 용도지역별 법정 건폐율·용적률 — 국토계획법 시행령 제84조(건폐율 상한)·제85조(용적률 범위).
# 실제 한도는 이 범위 안에서 시·군 도시계획조례가 정하고(예: 서울 2종일반 용적률 법정 250 %, 조례 200 %),
# 지구단위계획구역이면 그 계획이 우선한다 — 패널·조서는 '법정'으로만 적고 조례값은 토지이음으로 보낸다.
# zone_name 부분 문자열 → (건폐율 상한 %, 용적률 하한 %, 용적률 상한 %). 개발제한구역 등 표에 없는 이름은 범위 없음.
LEGAL_ZONE_LIMITS = {
    "제1종전용주거": (50, 50, 100), "제2종전용주거": (50, 50, 150),
    "제1종일반주거": (60, 100, 200), "제2종일반주거": (60, 100, 250), "제3종일반주거": (50, 100, 300), "준주거": (70, 200, 500),
    "중심상업": (90, 200, 1500), "일반상업": (80, 200, 1300), "근린상업": (70, 200, 900), "유통상업": (80, 200, 1100),
    "전용공업": (70, 150, 300), "일반공업": (70, 150, 350), "준공업": (70, 150, 400),
    "보전녹지": (20, 50, 80), "생산녹지": (20, 50, 100), "자연녹지": (20, 50, 100),
    "보전관리": (20, 50, 80), "생산관리": (20, 50, 80), "계획관리": (40, 50, 100),
    "농림": (20, 50, 80), "자연환경보전": (20, 50, 80),
}
ZONE_NAME_NONE = "지정되지않음"   # 토지특성정보 A16 — 두 번째 용도지역이 없는 필지(성수동2가 333-139)
# 대장 면적 대비 도형 면적 차이가 이 비율 이상이면 '지적불부합 의심'으로 표시한다. 도형은 연속지적도(도곽을 이어 붙인
# 참고도)라 차이 대부분은 도해지적 정밀도 탓이다. 서울 지목 '대' 65.8만 필지 중 5 % 초과 18 %, 10 % 초과 7 %
# (seoul_site.db, 2026-10-16). 법정 허용오차(공간정보관리법 시행령 제19조, 도해 1/1200·300 ㎡ ≈ 4.7 %)보다 넉넉히 잡는다.
AREA_GAP_FLAG_RATIO = 0.10

# ─────────────────────────────────────────────────────────
# VWorld — 인증키·도메인은 .env(gitignore)에 둔다. 코드·로그에 키를 넣지 않는다.
# ─────────────────────────────────────────────────────────
VWORLD_API_KEY_ENV = "VWORLD_API_KEY"
VWORLD_API_DOMAIN_ENV = "VWORLD_API_DOMAIN"

# 주소 검색 — 사용자가 켠 경우에만 로컬 미검색 주소를 보조 조회한다.
VWORLD_SEARCH_URL = "https://api.vworld.kr/req/search"
VWORLD_SEARCH_SERVICE = "search"
VWORLD_SEARCH_REQUEST = "search"
VWORLD_SEARCH_VERSION = "2.0"
VWORLD_SEARCH_TYPE_ADDRESS = "address"
VWORLD_SEARCH_CATEGORY_ROAD = "road"
VWORLD_SEARCH_CATEGORY_LOT = "parcel"  # VWorld 외부 규격 값은 parcel을 사용
VWORLD_SEARCH_FORMAT = "json"
VWORLD_SEARCH_SIZE = 10
VWORLD_SEARCH_TIMEOUT_SECONDS = 5

# ═════════════════════════════════════════════════════════
# 컨텍스트 DB — 건물·도로·지형·수계·녹지·철도 (data/seoul_context.db)
# 설계 근거: docs/data_sources.md §2, docs/deliverables.md §A
# ═════════════════════════════════════════════════════════
CONTEXT_DATABASE_PATH = "data/seoul_context.db"
CONTEXT_DATABASE_SCHEMA_VERSION = 1
# 배포본은 등고선·표고점(features theme terrain)을 별도 파일로 나눈다(보안관리규정 별표1 — 등고선·표고값 온라인 표시 제한).
# 컨텍스트 팩과 함께 국내 서버에 둔다(DATA_DOMESTIC_BASE_URL 주석). 컨텍스트 DB 옆에 있으면 context_db가 붙여 읽는다.
TERRAIN_DATABASE_NAME = "seoul_terrain.db"
TERRAIN_THEME = "terrain"

# 해외 대상지(osm_context.py) — OSM Overpass + AWS Terrain Tiles. 사용자 PC가 직접 부른다(서버 없음).
# Overpass 이용 기준: IP당 하루 1만 질의·1 GB 미만(https://wiki.openstreetmap.org/wiki/Overpass_API) — 대상지 1회 1질의
OSM_USER_AGENT = "Gorani/0.3 (Rhino/Blender/SketchUp plugin; https://969flash.github.io/gorani/)"   # Overpass·Nominatim·타일 중계(review_map) — OSM 정책: 앱을 밝힌다
OSM_CACHE_MAX = 8                # osm_context 응답 캐시 항목 상한(넘으면 비운다) — Blender판은 모듈을 다시 읽지 않아 세션 내내 쌓인다. 같은 대상지 다시 만들기(Overpass 1~2 + 지형 타일 수 장)만 덮으면 된다(도심 Overpass 응답은 수십 MB)
OSM_TIMEOUT_SECONDS = 60         # 미러 하나당. 공개 Overpass는 자주 붐빈다(2026-10-13 파리 900 m: 독일 504, kumi·coffee 120 s 초과, mail.ru 22 s)
# 2026-10-23 감사: overpass-api.de 429·차단일 때 kumi·coffee는 서울에서 60 s 시간 초과, mail.ru는 HARICA 인증서라 Windows·번들 파이썬에서 검증 실패.
# openstreetmap.fr은 200·1.3 s(자료 기준일 2026-07-21 — 3개월 묵음, 대체로만).
# 2026-10-25 다시 확인: kumi·coffee는 응답 없음, mail.ru 504 → 뺐다(Blender 심사: 접속 안 되는 서버를 왜 쓰냐). 미러가 더 필요하면 매니페스트 services.overpass로
OSM_OVERPASS_URLS = ("https://overpass-api.de/api/interpreter", "https://overpass.openstreetmap.fr/api/interpreter")
OSM_MIRROR_TIMEOUT_SECONDS = 30   # 두 번째 미러부터 — 다 죽은 날 생성이 수 분 멈추지 않게(첫 서버는 OSM_TIMEOUT_SECONDS)
OSM_OVERPASS_QUERY = """[out:json][timeout:55][bbox:{bbox}];
(
  way["building"]; relation["building"]["type"="multipolygon"];
  way["highway"]; way["railway"];
  way["waterway"]; way["natural"="water"]; relation["natural"="water"]; way["landuse"~"^(reservoir|basin|grass|forest|meadow|recreation_ground|village_green|cemetery)$"];
  way["leisure"~"^(park|garden|pitch|playground)$"]; relation["leisure"="park"]; way["natural"~"^(wood|scrub|grassland)$"];
  node["railway"="station"];
  way["amenity"~"^(school|kindergarten|college|university|library|hospital|clinic|nursing_home|social_facility|childcare|community_centre|arts_centre|theatre)$"];
  relation["amenity"~"^(school|college|university|hospital)$"]["type"="multipolygon"];
  way["leisure"="sports_centre"]; way["place"="square"];
  way["area:highway"]; way["amenity"="parking"]; relation["amenity"="parking"]["type"="multipolygon"];
);
out geom;"""   # 역·시설 줄은 OSM_PUBLIC_USE와 맞춘다(tests/test_osm_context가 확인). 도로면 폴리곤(area:highway, 드묾)·주차장 면은 포장면으로
# 일본(PLATEAU 팩이 있는 곳)은 건물 줄을 빼고 도로·수계·녹지를 먼저 묻고, OSM 건물(PLATEAU 빈 곳 메우기)은 따로 첫 미러에만 묻는다.
# 도심은 OSM 건물이 많아 한 질의가 통째로 시간 초과됐다(2026-10-22 Rhino 시험: 도쿄타워·시부야·후쿠오카 덴진 — 7곳 중 3곳 도로 없음)
OSM_OVERPASS_BUILDINGS = 'way["building"]; relation["building"]["type"="multipolygon"];'
OSM_OVERPASS_BUILDING_QUERY = """[out:json][timeout:25][bbox:{bbox}];
(
  %s
);
out geom;""" % OSM_OVERPASS_BUILDINGS
OSM_ROAD_WIDTHS = {   # highway 등급 → 기본 도로폭 m (width·lanes 태그가 없을 때). 국내 도로 분류와 비교한 대략값
    "motorway": 22.0, "trunk": 18.0, "primary": 15.0, "secondary": 12.0, "tertiary": 9.0, "unclassified": 6.0,
    "residential": 6.0, "living_street": 5.0, "service": 4.0, "pedestrian": 6.0, "footway": 2.0, "cycleway": 2.0, "path": 1.5,
    "motorway_link": 8.0, "trunk_link": 8.0, "primary_link": 7.0, "secondary_link": 7.0, "tertiary_link": 6.0, "track": 3.0, "steps": 2.0,
}
OSM_LANE_WIDTH = 3.3            # m — 차로당 폭
# OSM 도로는 선(중심선)뿐이라 폭만큼 버퍼해 도로면을 만든다(수치지형도 도로경계 면에 해당). 지도 타일도 같은 방식으로 선을 굵게 그린다
OSM_ROAD_ARC_SEGMENTS = 3       # 도로면 버퍼의 끝 반원·바깥 꺾임 호 분할(90°당). 폭 6 m 도로 끝 반원 6변 — 꼭짓점 수가 지형 면 분할 시간에 비례한다
OSM_ROAD_MITER_LIMIT = 4.0      # 버퍼 안쪽 꺾임 교점 허용 거리(폭의 배수) — 예각에서 교점이 멀리 달아나는 것을 막는다
OSM_ROAD_NO_SURFACE_TAGS = ("tunnel",)   # 이 태그가 'no'가 아니면 도로면을 만들지 않는다(지하 — 지형을 깎지 않는다). 교량은 지형에 얹힌다(ponytail: 교량 높이는 다음에)
OSM_RAIL_TYPES = ("rail", "subway", "light_rail", "tram", "narrow_gauge", "monorail")
OSM_GREEN_TAGS = {"leisure": ("park", "garden", "pitch", "playground"), "natural": ("wood", "scrub", "grassland"),
                  "landuse": ("grass", "forest", "meadow", "recreation_ground", "village_green", "cemetery")}
OSM_BUILDING_USE = {   # building 태그 → 국내 건축물용도 대분류(시트 색). 근거: 건축법 시행령 별표1 대분류와 뜻이 가까운 것만
    "house": "01000", "detached": "01000", "semidetached_house": "01000", "bungalow": "01000",
    "apartments": "02000", "residential": "02000", "terrace": "02000", "dormitory": "02000",
    "retail": "03000", "kiosk": "03000", "commercial": "04000", "office": "14000", "hotel": "15000",
    "industrial": "17000", "warehouse": "18000", "school": "10000", "university": "10000", "college": "10000", "kindergarten": "11000",
    "hospital": "09000", "church": "06000", "cathedral": "06000", "temple": "06000", "mosque": "06000", "train_station": "08000",
}
# 공공시설·역세권 도면(Global) — 역 = railway=station 점(이름 있는 것). 시설 면(amenity·leisure) 안 용도 미상 건물에 국내 용도 대분류를 준다
# (OSM은 시설을 부지 면에 달고 건물은 building=yes로만 그리는 일이 흔하다). 학교 면은 '학교 부지', place=square는 '광장'. 근거: 건축법 시행령 별표1
OSM_SCHOOL_AMENITIES = ("school", "kindergarten", "college", "university")
OSM_PUBLIC_USE = {"school": "10000", "kindergarten": "10000", "college": "10000", "university": "10000", "library": "10000",
                  "hospital": "09000", "clinic": "09000", "nursing_home": "11000", "social_facility": "11000", "childcare": "11000",
                  "community_centre": "05000", "arts_centre": "05000", "theatre": "05000", "sports_centre": "13000"}
OSM_NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"   # 지명 검색 — 사용자가 [검색]을 누를 때 한 번
OSM_SEARCH_TIMEOUT_SECONDS = 10   # 지명 검색은 UI 스레드에서 기다린다 — Overpass 60 s를 쓰면 막힌 망에서 검색 한 번에 1분 멈췄다(2026-10-23 감사)
OSM_TERRAIN_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
OSM_TERRAIN_ZOOM = 13           # 픽셀 약 19 m(적도)·15 m(위도 37°). 원천 DEM이 약 30 m라 더 키워도 정밀해지지 않는다
OSM_TERRAIN_STEP = 2            # 픽셀 건너뛰기 — 표고점 간격 약 30 m

# 데이터 팩 받기(data_pack.py) — Yak 설치본은 DB 없이 깔리고 패널에서 받는다
DATA_REPO_ID = "hooooooooon/urbandesigntool-data"   # Hugging Face 공개 데이터셋(필지 시군구 팩 + 매니페스트) — dev_deploy upload
# 같은 데이터셋의 GitHub 사본 — Blender판만 이쪽을 읽는다(dev_deploy blender가 DATA_MANIFEST_URL을 바꿔 넣는다. 확장 심사 2026-10-25: 'Hugging Face는 빼라').
# 매니페스트·config.json은 저장소 파일(HF와 같은 폴더 구조 — 상대경로 "jp/manifest.json"이 그대로 풀린다), 팩은 폴더마다 릴리스(태그 kr·jp·…,
# 자산 1,000개 상한이라 넘치면 us-2 …)에 두고 매니페스트가 절대 주소로 가리킨다. 릴리스 태그는 data·data/jp처럼 겹칠 수 없다(git 참조) — dev_deploy.py mirror
DATA_GITHUB_REPO = "969flash/gorani-data"
DATA_GITHUB_MANIFEST_URL = "https://raw.githubusercontent.com/%s/main/manifest.json" % DATA_GITHUB_REPO
DATA_GITHUB_ASSET_MAX = 950            # 릴리스 하나에 넣는 팩 수(GitHub 상한 1,000)
DATA_MANIFEST_URL = "https://huggingface.co/datasets/%s/resolve/main/manifest.json" % DATA_REPO_ID
# 수치지형도에서 나온 컨텍스트·등고선 팩은 국내 서버에만 둔다 — 수치지형도는 기본측량성과라 국외 반출에 허가가 필요하다
# (공간정보관리법 제16조). Oracle Cloud 춘천 리전 Always Free 버킷(공개 읽기·목록 금지). 계정을 유료로 올리지 말 것 —
# Always Free 전용 계정은 과금 수단이 없어 한도(저장 20 GB·전송 월 10 TB)를 넘으면 멈출 뿐 청구되지 않는다.
DATA_DOMESTIC_BUCKET_URL = "https://objectstorage.ap-chuncheon-1.oraclecloud.com/n/axmhzznfqthg/b/urbandesigntool-data/o/"   # 올리는 곳
# 매니페스트에 적는 받기 주소. 문지기 서버(scripts/server_gate.py, 같은 리전 VM)를 세우면 "http://<VM 공인 IP>/"로 바꾸고
# 버킷을 Private로 돌린다. 되돌리기 = 버킷 주소로 바꿔 dev_deploy upload + 버킷 Public — 플러그인은 매니페스트만 보므로 사용자는 할 일이 없다.
DATA_DOMESTIC_BASE_URL = "http://150.230.249.1/"   # 문지기 VM udt-gate(2026-10-14, VM.Standard.E2.1.Micro)
DATA_STATE_FILE_NAME = "packs.json"    # data/ 안. 받은 팩의 sha256 — 바뀐 팩만 다시 받는다
DATA_TIMEOUT_SECONDS = 30              # 연결·조각 읽기 제한
NOTICE_LEVELS = ("warn", "info")      # 매니페스트 notices[].level — warn = 주황 띠(꼭 알아야 할 것), info = 파랑 띠
DATA_CHUNK_BYTES = 1024 * 1024         # 압축 스트림을 1 MB씩 읽어 풀고 진행률을 알린다
DATA_MAX_OPEN_FILES = 11               # 한 연결에 여는 지역 DB 수 상한 — SQLite ATTACH 기본 상한 10 + main(2026-10-12 실측)
# 팩 범위(매니페스트 bounds) — 시군구 필지 중심점의 핵심 범위(0.5~99.5 %)를 각 변마다 그 폭의 절반(최소 5 km)까지 넓힌 창 안의 필지만으로 잰다.
# 원천 오류 객체 몇 개가 범위를 수백 km로 늘려 엉뚱한 지역 팩을 받게 했다(2026-10-14: 41591 화성 만세구 필지 9개가 y 617 km,
# 11305 강북구 건물 2동이 x 459 km — 홍천 팩 범위 331×243 km). 퍼센타일만 자르면 진짜 섬(화성 서쪽 8 km)이 잘린다.
PACK_BOUNDS_CORE_QUANTILE = 0.005
PACK_BOUNDS_EXTEND_MIN = 5000.0        # m
PACK_BOUNDS_MARGIN = 200.0             # m — 시군구 분할 격자 한 칸(경계 객체는 양쪽 팩에 있다)
# 일본 건물 팩 — 국토교통성 3D 도시모델(PLATEAU) 건물을 시구정촌마다 한 팩으로(dev_plateau.py). 근거 docs/research/japan.md, 계획 docs/japan_plan.md.
# 국외 반출 제한이 없고 CC BY 4.0 호환이라 필지 팩과 같은 Hugging Face 데이터셋의 jp/ 폴더에 둔다. 매니페스트도 따로 둔다 —
# 한국 팩 올리기(dev_deploy upload)가 일본 항목을 덮지 않고, 한국 대상지는 일본 목록을 받지 않는다.
JP_PACK_DIR = "jp"                     # 데이터셋 안 폴더·로컬 build/packs/jp
JP_PACK_PREFIX = "jp"                  # 팩 이름 jp<시구정촌코드>_context.db — 시구정촌 코드(5자리)가 한국 시군구 코드와 겹친다
DATA_JP_MANIFEST_URL = DATA_MANIFEST_URL.rsplit("/", 1)[0] + "/%s/manifest.json" % JP_PACK_DIR
JP_BOUNDS = (122.0, 20.0, 154.0, 46.0)   # 일본 경위도 상자(서, 남, 동, 북) — 범위 밖 좌표는 원천 오류로 버린다
# 네덜란드 — Kadaster 3D Basisvoorziening '2D 건물 + 높이 통계'(hoogtestatistieken_gebouwen, CC BY 4.0). 도엽(bladnr) zip 안 GeoPackage, EPSG:28992
NL_PACK_DIR = "nl"
NL_PACK_PREFIX = "nl"                  # 팩 이름 nl<도엽>_context.db — 도엽 25gn1처럼 소문자 영숫자
NL_BOUNDS = (3.2, 50.7, 7.3, 53.7)     # 네덜란드 경위도 상자(서, 남, 동, 북)
PDOK_ITEMS_URL = "https://api.pdok.nl/kadaster/3d-basisvoorziening/ogc/v1/collections/hoogtestatistieken_gebouwen/items?f=json&limit=1000"
PDOK_LICENSE = "CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/deed.nl) — 출처 표기: Kadaster, 3D Basisvoorziening"
PDOK_HEIGHT_RANGE = (1.0, 400.0)       # rf_h_roof_50p − rf_h_ground 사용 범위 m(암스테르담 2025 최대 138 m)
PDOK_YEAR_MIN = 1500                   # BAG oorspronkelijkbouwjaar — 1005 같은 자리표시 연도는 모름으로(암스테르담 25GN1)
PDOK_SKIP_STATUS = ("Pand gesloopt", "Niet gerealiseerd pand", "Bouwvergunning verleend", "Pand buiten gebruik", "Sloopvergunning verleend")   # BAG pandstatus — 없는·허가만 난 건물
# 프랑스 — IGN BD TOPO v3.5 `batiment`(Licence Ouverte 2.0). 데파르트망별 7z(GeoPackage 모든 테마, EPSG:2154) — Géoplateforme Atom 피드
FR_PACK_DIR = "fr"
FR_PACK_PREFIX = "fr"                  # 팩 이름 fr<데파르트망 3자리 소문자>_context.db — fr075, fr02a
FR_BOUNDS = (-5.6, 41.2, 9.9, 51.2)    # 프랑스 본토·코르시카 경위도 상자(서, 남, 동, 북) — 해외 데파르트망(LAMB93 아님)은 빼둔다
BDTOPO_FEED_URL = "https://data.geopf.fr/telechargement/resource/BDTOPO?page=%d"   # 10건씩, 2026-10-22 기준 400쪽 안팎
BDTOPO_LICENSE = "Licence Ouverte / Open Licence 2.0 (Etalab) — 출처 표기: IGN, BD TOPO®"
BDTOPO_HEIGHT_RANGE = (1.0, 400.0)     # hauteur 사용 범위 m
BDTOPO_SKIP_STATES = ("En projet", "Détruit")   # etat_de_l_objet — 없는 건물
BDTOPO_USE = {"Résidentiel": "02000", "Commercial et services": "04000", "Industriel": "17000", "Agricole": "21000"}   # usage_1 → 국내 대분류(시트 색). 그 밖은 빈 값
# 스위스 — swisstopo swissBUILDINGS3D 3.0 Beta(OGD 이용약관: 자유 이용·재배포, 출처 "©swisstopo"). STAC 타일(1:25k 도엽 하위 타일) FileGDB(MultiPatch LoD2) → GDAL ogr2ogr로 읽는다
CH_PACK_DIR = "ch"
CH_PACK_PREFIX = "ch"                  # 팩 이름 ch<1:25k 도엽 4자리>_context.db — ch1172
CH_BOUNDS = (5.9, 45.8, 10.6, 47.9)    # 스위스·리히텐슈타인 경위도 상자(서, 남, 동, 북)
SWISS_STAC_ITEMS_URL = "https://data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissbuildings3d_3_0/items?limit=100"
SWISS_LICENSE = "swisstopo OGD 이용약관(2022-08-26, Version 1.3.2021) — 자유 이용·가공·배포, 출처 표기 \"©swisstopo\""
SWISS_HEIGHT_RANGE = (1.0, 400.0)      # 솔리드 최고 z − 최저 z 사용 범위 m
# 미국 — Overture Maps buildings(ODbL. Microsoft ML Buildings·OpenStreetMap·Esri Community Maps 합본 — 미국 높이는 대부분 Microsoft ML 추정, 로스앤젤레스 98.8 %·오스틴 89.3 %
# 2026-10-23 실측 docs/research/country_buildings.md). 공식 출처(FEMA USA Structures)는 높이가 1/4뿐이고 약관이 갈려 쓰지 않는다. 카운티(Census FIPS 5자리)마다 팩 하나 — dev_us.py
US_PACK_DIR = "us"
US_PACK_PREFIX = "us"                  # 팩 이름 us<카운티 FIPS 5자리>_context.db — us06037 로스앤젤레스
US_BOUNDS = ((-125.0, 24.3, -66.9, 49.5), (-170.0, 51.0, -129.0, 72.0), (-161.0, 18.5, -154.0, 22.5), (-68.0, 17.5, -64.4, 18.6))   # 본토·알래스카·하와이·푸에르토리코/버진아일랜드(서, 남, 동, 북)
OVERTURE_RELEASE = "2026-10-21.0"      # 달마다 새 판 — 바꾸면 fetch부터 다시
OVERTURE_S3_URL = "s3://overturemaps-us-west-2/release/%s/theme=buildings/type=building/*" % OVERTURE_RELEASE   # 익명 읽기(DuckDB httpfs, us-west-2)
OVERTURE_PAGE_URL = "https://overturemaps.org"
OVERTURE_LICENSE = "ODbL 1.0 (Open Database License) — 출처 표기: Overture Maps Foundation, © OpenStreetMap contributors, Microsoft (Global ML Building Footprints)"
OVERTURE_HEIGHT_RANGE = (1.0, 700.0)   # height 사용 범위 m(One World Trade Center 541 m)
OVERTURE_USE_CLASS = {"apartments": "02000", "dormitory": "02000", "hotel": "15000", "office": "14000", "warehouse": "18000", "garage": "20000", "garages": "20000",
                      "parking": "20000", "school": "10000", "university": "10000", "college": "10000", "hospital": "09000", "church": "06000"}   # class 우선
OVERTURE_USE_SUBTYPE = {"residential": "01000", "commercial": "04000", "industrial": "17000", "agricultural": "21000", "education": "10000", "medical": "09000",
                        "religious": "06000", "civic": "14000", "transportation": "08000", "entertainment": "05000", "military": "23000"}   # subtype → 국내 대분류(시트 색). service·outbuilding은 빈 값
CENSUS_COUNTY_URL = "https://www2.census.gov/geo/tiger/GENZ2024/shp/cb_2024_us_county_500k.zip"   # 카운티 경계(미국 정부 저작물, 공개). GEOID = FIPS 5자리, 3,235개(준주 포함)
US_COUNTY_BUFFER_DEG = 0.003           # 카운티 경계를 넓혀 건물 중심을 배정(약 300 m) — 해안선 간략화(1:500k)로 빠지는 부두·매립지 건물. 겹친 건물은 런타임이 src_key로 한 번만
# 나라별 공식 건물 팩(경위도, 매니페스트는 나라마다 따로 — HF 데이터셋 <dir>/manifest.json). 키 = 팩 이름 접두사. 런타임은 대상지 중심이 bounds 안인 나라의 팩을 쓴다
# source_id = 팩 data_sources.source_id, label = 화면·도면 표기, code_pattern = 접두사 뒤 지역 코드 꼴(한국 시도 슬러그 jpn 같은 이름과 구분)
# manifest = 한국 매니페스트(DATA_MANIFEST_URL) 기준 상대경로 — data_pack이 urljoin으로 푼다(HF·GitHub 사본 어느 쪽이든 같은 꼴).
# ※ 내장 기본값일 뿐이다 — 런타임은 data_pack.get_country_packs()(한국 매니페스트 countries[]가 덮는다, 원본 docs/countries.json, 올리기 dev_deploy.py notices).
#    새 나라는 여기 말고 docs/countries.json에 넣는다 — 데이터만 바뀌는 일에 플러그인 판을 올리지 않는다(2026-10-23, 0.3.3·0.3.4를 나라 추가만으로 올린 뒤).
#    여기 값은 countries.json과 같게 둔다(tests/test_data_pack.py가 맞춘다) — 오프라인 사용자에게 지금 넷 나라는 그대로 돌게.
COUNTRY_PACKS = {
    "jp": {"dir": JP_PACK_DIR, "manifest": "jp/manifest.json", "bounds": JP_BOUNDS, "source_id": "plateau", "label": "PLATEAU", "code_pattern": r"\d{5}"},
    "nl": {"dir": NL_PACK_DIR, "manifest": "nl/manifest.json",
           "bounds": NL_BOUNDS, "source_id": "pdok", "label": "3D Basisvoorziening", "code_pattern": r"\d{2}[a-z]{2}\d"},   # 도엽 25gn1
    "fr": {"dir": FR_PACK_DIR, "manifest": "fr/manifest.json",
           "bounds": FR_BOUNDS, "source_id": "bdtopo", "label": "BD TOPO", "code_pattern": r"\d{3}|02[ab]"},   # 데파르트망 075·02a
    "ch": {"dir": CH_PACK_DIR, "manifest": "ch/manifest.json",
           "bounds": CH_BOUNDS, "source_id": "swisstopo", "label": "swissBUILDINGS3D", "code_pattern": r"\d{4}"},   # 1:25k 도엽 1172
    "us": {"dir": US_PACK_DIR, "manifest": "us/manifest.json",
           "bounds": US_BOUNDS, "source_id": "overture", "label": "Overture", "code_pattern": r"\d{5}"},   # 카운티 FIPS 06037. 상자 넷(2026-10-23)
}
PLATEAU_CKAN_URL = "https://www.geospatial.jp/ckan/api/3/action/package_search"   # G空間情報センター. 카탈로그 API 리다이렉트는 404(2026-10-21)
PLATEAU_CKAN_QUERY = "3D都市モデル（Project PLATEAU）"
PLATEAU_SKIP_CODES = ("27999",)        # 2025 오사카·간사이 엑스포 회장 — 철거 중인 임시 행사장
PLATEAU_DIGITS = 6                     # 경위도 소수 자리(0.11 m) — 원천 외곽은 지도정보레벨 2500(평면 표준편차 1.75 m)
PLATEAU_HEIGHT_RANGE = (1.0, 700.0)    # measuredHeight(항공측량 실측) 사용 범위 m — -9999 = 모름, 도쿄 스카이트리 634 m
PLATEAU_UNKNOWN = 9999                 # 층수 9999·높이 -9999 = 모름(구니타치 2025 실측: 층수 9999 6,155동 = 용도 461 '불명'과 같은 동)
PLATEAU_MAX_EXTENT_DEG = 0.03          # 건물 최대 폭(경위도) — bbox 질의의 min_x 하한. dev_plateau가 빌드 끝에 넘지 않는지 검사한다
PLATEAU_ROAD_TOLERANCE_M = 0.02        # 도로면 LOD1 폴리곤이 여럿일 때 합치기(공유 변 지우기) 허용오차 m — 조각은 정점을 정확히 공유한다
PLATEAU_ROAD_MAX_EXTENT_DEG = 0.1      # 도로면 하나의 최대 폭(경위도) — 간선도로 한 구간이 수 km. bbox 질의의 min_x 하한
PLATEAU_USE = {   # PLATEAU 용도 코드(zip 안 codelists/Building_usage.xml, 2026-10-21 확인) → 국내 건축물용도 대분류(시트 색). 454 その他·461 不明은 빈 값
    "401": "14000", "402": "04000", "403": "15000", "404": "04000",                   # 業務·商業·宿泊·商業系複合施設
    "411": "01000", "412": "02000", "413": "01000", "414": "02000", "415": "01000",   # 住宅·共同住宅·店舗等併用(共同)住宅·作業所併用住宅
    "421": "14000", "422": "10000", "431": "18000", "441": "17000",                   # 官公庁·文教厚生·運輸倉庫施設·工場
    "451": "21000", "452": "22000", "453": "23000",                                   # 農林漁業用·供給処理·防衛施設
}
# 일본 지형 — 국토지리원(GSI, 国土地理院) 표고 타일. 앱이 실시간으로 읽는 것은 출처 표기만으로 쓴다(地理院タイル一覧). 저장·재배포하지 않는다.
# 같은 지점에서 AWS terrarium이 평균 3.8 m(평지)~12.9 m(산지) 높았다(research §9.3). 표고 기준 T.P.로 PLATEAU 건물과 같다
GSI_TERRAIN_URLS = tuple("https://cyberjapandata.gsi.go.jp/xyz/%s/{z}/{x}/{y}.png" % kind
                         for kind in ("dem5a_png", "dem5b_png", "dem5c_png"))   # 항공 레이저 5 m → 사진 측량 5 m 순. 없는 타일은 404
GSI_TERRAIN_ZOOM = 15                  # 5 m 타일의 최대 줌 — 위도 35°에서 화소 약 3.9 m. 다 없으면 같은 타일의 AWS terrarium(z15)
GSI_TERRAIN_STEP = 2                   # 화소 건너뛰기 — 표고점 약 8 m 간격
GSI_NO_DATA = 1 << 23                  # RGB (128, 0, 0) = 값 없음(수면 등)
# 사용 통계(usage_stats.py) — GA4 Measurement Protocol. 측정 ID·secret이 비면 보내지 않는다. 끄는 설정 없음(고지는 docs/install.md)
# 호스트마다 GA4 속성을 따로 둔다 — 웹사이트·Rhino·Blender·SketchUp을 섞지 않고 본다(사용자 결정 2026-10-16). 키 = context_builder.get_host()
# 값 = (웹 스트림 측정 ID G-…, 관리 > 데이터 스트림 > Measurement Protocol API secret). 비면 그 호스트는 보내지 않는다. secret은 드러나도 된다(가짜 이벤트 주입 위험만)
# Blender는 넣지 않는다 — 확장 스토어 심사가 동의를 받아도 분석 전송을 거절한다(약관 4.5, 2026-10-21 심사 사례 조사). 속성 "Gorani Blender"(G-9D69356PZJ)는 GA에 남아 있다
GA_STREAMS = {
    "rhino": ("G-NJC4VMHPM1", "Yxwc8yciQiGRUAVajxTBjg"),
    "sketchup": ("G-651J4ER1QV", "10JBBMCITO2ZnpwOFZiiiQ"),   # 속성 "Gorani SketchUp" 559864110, 스트림 16174947817(2026-10-21) — 동의한 사람만
}
GA_ENDPOINT = "https://www.google-analytics.com/mp/collect"
GA_TIMEOUT_SECONDS = 5  # 백그라운드 스레드라 패널을 막지 않는다
GA_PARAM_VALUE_MAX = 100  # GA4 표준 속성 이벤트 매개변수 값 길이 상한(360은 500)
GA_PNU_PARAMS = 4  # 필지 PNU를 나눠 담는 매개변수 수(값 하나에 5개 → 20필지). 이벤트당 매개변수 상한 25 안에서
# 관리자 페이지 통계(dev_stats — 이 Mac에서만). 열쇠·쌓은 기록은 저장소 밖 ADMIN_DIR에 둔다(공개 저장소)
ADMIN_DIR = os.path.join(os.path.expanduser("~"), ".config", "gorani")
ADMIN_GA_KEY_PATH = os.path.join(ADMIN_DIR, "ga_service_account.json")   # GA4 Data API 서비스 계정 키(GCP gorani-stats) — GA 계정 단위 '편집자'(맞춤 측정기준 등록에 필요)
ADMIN_DEV_CLIENTS_PATH = os.path.join(ADMIN_DIR, "dev_clients.json")   # 국내 서버 기록에서 '내 시험'으로 표시한 설치 ID 목록(이 Mac 설치 ID는 자동)
ADMIN_GATE_LOG_PATH = os.path.join(ADMIN_DIR, "udt.log")   # 국내 서버 nginx 기록을 이어 붙인 사본 — 서버는 logrotate로 2주만 남긴다
ADMIN_GATE_SSH = ("ubuntu", os.path.join(os.path.expanduser("~"), ".ssh", "udt-gate.key"))   # docs/domestic_gate.md
ADMIN_YAK_VERSIONS_URL = "https://yak.rhino3d.com/versions/%s" % TOOL_NAME   # 버전별 download_count(공개 API)
ADMIN_HF_API_URL = "https://huggingface.co/api/datasets/%s?expand%%5B%%5D=downloads&expand%%5B%%5D=downloadsAllTime&expand%%5B%%5D=usedStorage" % DATA_REPO_ID   # 데이터셋 전체 합계만(파일별 없음)
ADMIN_ORACLE_FREE_STORAGE = 20 * 1024 ** 3   # Always Free 오브젝트 스토리지 20 GB(넘으면 유료 — 전환 금지)
ADMIN_ORACLE_FREE_EGRESS = 10 * 1000 ** 4    # Always Free 아웃바운드 월 10 TB
ADMIN_STORE_URLS = {   # 프로그램별 배포 자리 — 빈 값 = 아직 공개 전(심사 중). Blender는 이 주소가 200이면 공개된 것으로 본다
    "rhino": "https://yak.rhino3d.com/packages/Gorani",
    "sketchup": "",   # Extension Warehouse 심사 중(docs/sketchup_store.md) — 공개되면 페이지 주소를 넣는다
    "blender": "https://extensions.blender.org/add-ons/gorani/",
}
ADMIN_TEST_AGENTS = ("curl/", "HeadlessChrome", "python-requests")   # 국내 서버 기록에서 늘 시험으로 보는 User-Agent
ADMIN_GA_WEB_ID = "G-ZVM7EZPRPQ"   # 웹사이트 속성 "Gorani 웹"(969flash/gorani assets/site.js). 플러그인 속성은 GA_STREAMS — 이 밖의 속성(옛 Blender)은 대시보드에서 뺀다
# 대시보드가 쓰는 이벤트 매개변수 — GA 맞춤 측정기준·측정항목으로 등록해야 Data API로 읽힌다(등록한 날부터 쌓임). 관리자 페이지 [연결]에서 한 번에 등록
# 플러그인 = cmd_site._send_stats(panel_open·build·pack_download·error) + usage_stats.get_target_params, 웹 = site.js track(copy_command·install_tab·demo_chapter)
ADMIN_GA_DIMENSIONS = {
    "app": ("version", "host", "rhino", "mode", "result", "korea", "error", "context", "packs", "placement", "shape", "radius",
            "lng", "lat", "pnus", "pnus_2", "pnus_3", "pnus_4", "dev"),
    "web": ("host", "command", "chapter", "dev"),   # dev = 개발자 PC·브라우저 표시(usage_stats·site.js) — [내 테스트 제외]
}
ADMIN_GA_METRICS = {"app": (("elapsed_s", "SECONDS"), ("buildings", "STANDARD"), ("area", "STANDARD")), "web": ()}
# 테이블별 객체 최대 폭 m — bbox 질의의 min_x 하한에 쓴다. dev_context_builder가 빌드 끝에 넘지 않는지 검사한다.
# 실측(2026-10-08): 건물 최대 887 m(가로·세로 중 큰 값), features 최대 2,779 m(도엽 1장 높이 — 도엽 단위로 잘려 있다).
CONTEXT_MAX_EXTENT = {"buildings": 2000.0, "features": 3000.0}   # 부산 건물 최대 1,340 m(2026-10-13 전국 빌드)
TOPO_SHEET_DIRNAME = "data/raw/수치지형도_5000"        # 도엽 zip 그대로 + sheets.csv (수동 다운로드)
TOPO_SHEET_INDEX_FILENAME = "sheets.csv"
TOPO_ENCODING = "cp949"                              # 수치지형도 SHP 속성 인코딩 (성수 4도엽 실측)
BUILDING_BULK_DIRNAME = "data/raw/vworld_GIS건물통합정보"  # AL_D010_11_<기준일>.zip (수동 다운로드)
BUILDING_BULK_ENCODING = "cp949"
BUILDING_BULK_FILE_GLOB = "AL_D010_%s_*.zip"   # 시도 코드별 전체본
# 수치지형도 1:5,000 Ver2.0 시군구 묶음(브이월드 dsId=30205, 2MAP5000_SHP_<시도>_<시군구>.zip — 안에 도엽 zip들).
# 도엽 zip은 TOPO_SHEET_DIRNAME에 풀어 쓰고, 묶음 이름의 시도로 도엽을 시도 하나에 배정한다(경계 도엽은 여러 묶음에 들어 있다).
TOPO_BUNDLE_DIRNAME = "data/raw/수치지형도_5000_시군구"
TOPO_BUNDLE_SIDO = {   # 묶음 이름 앞부분 → 시도 코드. 광주·전남은 2026-09 전남광주통합특별시(12)로 합쳐졌다
    "서울": "11", "부산": "26", "대구": "27", "인천": "28", "광주": "12", "전남": "12", "대전": "30", "울산": "31",
    "세종시": "36", "경기": "41", "충북": "43", "충남": "44", "경북": "47", "경남": "48", "제주": "50", "강원": "51", "전북": "52",
}

# 수치지형도 레이어 → (theme, kind, 값 필드). 키는 접두 'N3'/'N1'을 뗀 '도형자_코드'다.
# 도엽마다 접두가 다르다(137장 중 2장이 N1). 코드 의미는 docs/reference/수치지형도_지형지물_표준코드.csv.
# 여기 없는 레이어(행정경계·탱크·놀이시설·유수방향·도곽 등)는 적재하지 않는다.
TOPO_LAYERS = {
    "L_F0010000": ("terrain", "contour", "등고수치"),      # 등고선 — TIN 입력
    "P_F0020000": ("terrain", "spot", "수치"),            # 표고점 — TIN 입력(구조물 위는 spot_struct로 재분류)
    "P_H0020000": ("terrain", "benchmark", "표고"),       # 측량기준점 — 표고 있음
    "L_F0030000": ("structure", "cutfill", None),        # 성/절토 경계 — 브레이크라인 후보
    "L_F0040000": ("structure", "wall", "높이"),          # 옹벽
    "L_B0020000": ("structure", "fence", None),          # 담장
    "L_C0050000": ("structure", "levee", "높이"),         # 제방
    "A_C0390000": ("structure", "stairs", None),         # 계단
    "A_A0110020": ("structure", "tunnel", None),         # 터널
    "A_A0010000": ("road", "surface", None),             # 도로경계(면) — 도로면 1순위
    "L_A0020000": ("road", "centerline", "도로폭"),       # 도로중심선 — 도로폭·차로수 100% 채움
    "A_A0033320": ("road", "sidewalk", "폭"),             # 인도(면)
    "A_A0053326": ("road", "safety_zone", None),         # 안전지대
    "A_A0080000": ("road", "intersection", None),        # 교차로(면)
    "A_C0430000": ("road", "parking", None),             # 주차장(면)
    "A_C0520000": ("road", "median", None),              # 도로분리대
    "A_A0070000": ("bridge", "bridge", None),            # 교량 — 표고점 제외 버퍼 대상
    "A_A0090000": ("bridge", "overpass", None),          # 입체교차부(고가·지하차도) — 표고점 제외 버퍼 대상
    "A_A0100000": ("bridge", "interchange", None),       # 인터체인지 — 표고점 제외 버퍼 대상
    "A_A0063321": ("bridge", "footbridge", None),        # 육교
    "L_A0150000": ("rail", "line", None),                # 철도(지하철 지하/지상은 속성 '구분')
    "L_A0171119": ("rail", "centerline", None),          # 철도중심선
    "A_A0160024": ("rail", "surface", None),             # 철도부지선(면)
    "A_A0191221": ("rail", "platform", None),            # 플랫폼
    "A_A0201222": ("rail", "platform_roof", None),       # 플랫폼 지붕
    "P_A0131122": ("transit", "station", None),          # 정거장(점)
    "A_E0010001": ("water", "river", None),              # 하천경계(면)
    "A_E0032111": ("water", "stream", None),             # 실폭하천(면)
    "A_E0052114": ("water", "lake", None),               # 호수/저수지(면)
    "L_E0020000": ("water", "centerline", None),         # 하천중심선
    "A_G0020000": ("water", "shore", None),              # 수부지형경계(면) — 성수 fixture 3건 전부 형태 '습지'(G0020000): 수면이 아니라 WATER_SURFACE_KINDS에서 제외
    "A_D0010000": ("green", "field", None),              # 경지계(농경지)
    "P_H0040000": ("label", "place", None),              # 지명(점)
    "P_H0059153": ("label", "peak", "높이"),              # 산 정상(점)
}
TOPO_BUILDING_LAYER = "A_B0010000"                     # 건물 — features가 아니라 buildings 테이블로
TOPO_NAME_FIELD = "명칭"
TOPO_STRUCT_KINDS = ("bridge", "overpass", "interchange")  # 이 면 위 표고점은 상판 높이라 TIN에서 뺀다
SPOT_STRUCT_BUFFER = 5.0                               # m — 구조물 면 버퍼 (성수 실측: 제외 전 RMSE 3.48 → 1.54 m)
GEOMETRY_JSON_PRECISION = 0.001                        # m — GeoJSON 좌표 반올림 (mm). DB 용량 절감

# GIS건물통합정보(AL_D010) 컬럼 — 국가중점데이터 컬럼정의서(26.08.19)
BUILDING_BULK_COLUMNS = {
    "A1": "src_id",            # GIS건물통합식별번호
    "A2": "pnu",
    "A8": "usability",         # 건축물용도코드 5자리 (01000 단독주택 … 33000)
    "A10": "strct_cd",
    "A12": "arch_area_sqm",    # 건축면적
    "A13": "use_apr_day",      # 사용승인일자 YYYY-MM-DD
    "A14": "total_area_sqm",   # 연면적
    "A15": "plat_area_sqm",    # 대지면적
    "A16": "height_raw",       # 높이 m (법정 높이, 채움 39.7%)
    "A17": "bc_rat",
    "A18": "vl_rat",
    "A22": "reference_date",   # 데이터기준일자
    "A24": "bld_nm",
    "A25": "dong_nm",
    "A26": "grnd_flr",
    "A27": "ugrnd_flr",
    "A28": "data_changed_date",
}

# 건물 높이 규칙 — docs/deliverables.md §A.4 (성수·동대문 실측, 잠정 상수)
# 대분류(usability 앞 2자리) → (a, b): 높이 = a + b × 지상층수
FLOOR_HEIGHT_MODEL = {
    "01": (2.4, 2.4),   # 단독주택
    "02": (1.1, 2.8),   # 공동주택
    "03": (0.0, 3.3),   # 제1종근생
    "04": (0.7, 3.1),   # 제2종근생
    "05": (0.0, 4.0), "07": (0.0, 4.0), "09": (0.0, 4.0), "17": (0.0, 4.0), "18": (0.0, 4.0), "19": (0.0, 4.0), "20": (0.0, 4.0),
    "06": (0.0, 4.2),   # 종교
    "10": (1.4, 3.7),   # 교육연구
    "11": (0.7, 3.3),   # 노유자
    "14": (1.0, 3.4),   # 업무
}
FLOOR_HEIGHT_DEFAULT = (1.5, 2.8)      # 결측·구 코드·그 외
FLOOR_HEIGHT_CLAMP = (2.5, 8.0)        # 층당 최소·최대 m — 모델값을 이 범위로 자른다
DEFAULT_BUILDING_HEIGHT_M = 3.8        # 층수도 없을 때 (1층 실측 중앙값)
HEIGHT_RAW_PER_FLOOR_RANGE = (2.0, 8.0)  # 대장 높이/층수 가 이 범위 밖이면 대장 높이를 믿지 않는다
HEIGHT_RAW_RANGE_NO_FLOOR = (2.0, 100.0) # 층수 없을 때 대장 높이 허용 범위
BUILDING_ATTR_DISTRUST_RATIO = 0.5     # 건축면적 < 발자국면적 × 0.5 → 대장 속성 불신('!')
BUILDING_ATTR_SUSPECT_RATIO = 2.0      # 건축면적 > 발자국면적 × 2 → 부속동 의심('?'), 등급 한 단계 강등
TOPO_DUPLICATE_OVERLAP_RATIO = 0.5       # 보충 후보 수치지형도 건물이 GIS 건물과 이 비율 넘게 겹치면 중복으로 보고 뺀다
TOPO_APT_FLOOR_GAP = 3                 # 수치지형도 아파트·연립 층수 ≥ 대장 층수 + 3 이면 수치지형도 층수 채택
TOPO_APT_KINDS = ("아파트", "연립주택")
# 수치지형도 '종류'·'용도' → 높이 모델 대분류
TOPO_KIND_TO_USE = {"아파트": "02", "연립주택": "02", "일반주택": "01"}
TOPO_USE_TO_USE = {
    "주택": "01", "근린생활시설": "04", "교육연구시설": "10", "업무시설": "14",
    "종교시설": "06", "노유자(노인및어린이)시설": "11", "자동차관련시설": "20",
}
HEIGHT_GRADES = ("A", "B", "C", "D")

# ═════════════════════════════════════════════════════════
# 패널 — docs/panel_ui.md·docs/ui_spec.md
# ═════════════════════════════════════════════════════════
PANEL_VERSION = "0.3.6"   # 배포 버전 하나(Yak·Blender·SketchUp 패키지 버전 = dev_deploy.PACKAGE_VERSION). 매니페스트 update.latest·min과 비교한다
NOTICE_TIMEOUT_SECONDS = 3   # 패널을 열 때 매니페스트(공지·업데이트)를 기다리는 한도 — 못 받으면 공지 없이 연다
MANIFEST_RETRY_SECONDS = 60   # 지도 이동(area_packs)이 매니페스트를 못 받았으면 이만큼은 다시 묻지 않는다 — 막힌 망에서 이동마다 멈추지 않게
# 언어 — 패널 헤더에서 고른다(options.lang). 사전은 scripts/i18n.json 하나(패널 JS·Python 공용, i18n.py)
LANGS = ("en", "ko", "es", "ja", "zh")   # 고르기 순서. zh = 중국어 간체
DEFAULT_LANG = "en"   # food4Rhino 심사(2026-10-21 McNeel 메일 '영어가 없으면 올릴 수 없다') — 처음 설치는 영어. 0.3.0 전에 쓰던 설치본은 한국어 그대로(site_prefs.get_options)
LANG_ENV = "GORANI_LANG"   # 지금 언어 — loader.load가 모듈을 다시 읽어도 남게 환경변수에 둔다(투영 원점과 같은 방식)
INSTALL_DOC = "docs/install.md"
PREFS_DIRNAME = ".gorani"            # 사용자 홈 아래. prefs.json·source_news.json
RESULT_TIME_FORMAT = "%H%M"                    # 같은 날 같은 대상지를 다시 만들면 result/<대상지명>_<YYYYMMDD>_<HHMM>/ — 이전 결과를 지우지 않는다(2026-10-19)
RESULT_DATE_FORMAT = "%Y%m%d"                  # result/<대상지명>_<YYYYMMDD>/ — 날짜는 맨 뒤(2026-10-19 사용자 결정, 예전 result/<YYYYMMDD>/<대상지명>/)
RESULT_DIR_FORMAT = "%s_%s"                    # (대상지명, 날짜)
CONTEXT_MODEL_FILE_NAME = "context.3dm"
BLENDER_MODEL_FILE_NAME = "context.blend"      # Blender판 사본(blender_baker.save_copy) — 3dm 대신
SKETCHUP_MODEL_FILE_NAME = "context.skp"       # SketchUp판 사본(sketchup_baker.save_copy — 대상지 그룹 정의를 저장)
WEB_MODEL_FILE_NAME = "context.glb"            # 웹판 사본(web_baker.save_copy) — 페이지 뷰어가 바로 그리고 Blender·Rhino 8이 가져온다
CONTEXT_META_FILE_NAME = "context.json"
BASEMAP_FILE_FORMAT = "basemap_%d.ai"          # 축척 분모
# DWG 저장 스위치. 활성 문서에서 .dwg를 쓰면 Mac Rhino 8이 12분 멈춘 뒤 실패했다(2026-10-14 을지로1가 87, job 1014-152138 731 s) →
# 3dm 사본을 헤드리스로 열어 쓴다(context_baker.save_dwg_from_3dm, 0.14 s). Windows는 아직 확인 전
DWG_EXPORT_ENABLED = True
DWG_FILE_FORMAT = "basemap_%d.dwg"             # 3dm BM:: 2D 레이어만 내보낸 것(옵션 make_dwg). 축척 = 2D를 만든 축척(요청 중 가장 상세)
RESULT_LOG_FILE_NAME = "log.txt"

# 3dm 레이어 — deliverables §A.1 (부모 CTX), §B.2 (부모 BM). 색은 RGB.
CTX_ROOT_LAYER = "CTX"
BM_ROOT_LAYER = "BM"
CTX_LAYERS = {   # 이름: (RGB)
    "Site": (220, 40, 40), "Parcels": (185, 185, 180), "Buildings": (128, 128, 128), "Terrain": (236, 232, 222),
    "Water": (46, 125, 224), "Roads": (168, 168, 162), "Green": (228, 235, 226), "Rail": (110, 110, 110),
    "Bridges": (150, 150, 150), "Zoning": (200, 120, 40), "QA::cadastre_mismatch": (255, 0, 255), "Ref": (0, 0, 0),
    "Site::ground": (236, 150, 120), "Site::lots": (235, 140, 140), "Terrain::site_flat": (214, 196, 170), "Terrain::site_wall": (150, 140, 128), "Terrain::site_original": (236, 232, 222),
}
# CTX::Zoning 하위 레이어 — overlays theme → 'CTX::Zoning::<이름>::<종류>'. 종류는 용도지역이면 현황도 11 범례 이름, 나머지는 overlay.kind.
# 색은 현황도 11~13 범례 색(context_baker.get_layer_rgb). 현황도에 없는 theme(건축선 notice_road)은 넣지 않는다.
ZONING_LAYERS = {"zone": "용도지역", "district": "용도지구", "area": "용도구역", "facility": "도시계획시설", "plan": "지구단위계획"}
CTX_HIDDEN_LAYERS = ("Terrain::site_original", "Site::lots")   # 처음 만들 때 끈다(평탄화 전 원지형·합필 전 필지 — 필요할 때 켜 본다). 사용자가 켠 뒤로는 건드리지 않는다
# 베이스맵 레이어 순서·K톤(0~100)·선두께 mm(1:5000, 1:1000). fill=None이면 선만.
BM_LAYERS = [
    ("00_frame_scale", "프레임·축척·방위", None, 100, (0.5, 0.5)),
    ("01_water", "수계", 10, None, (0, 0)),
    ("02_green", "녹지·공원", 6, None, (0, 0)),
    ("02b_landuse", "토지이용현황", 8, None, (0, 0)),
    ("03_road_surface", "도로면", 18, None, (0, 0)),
    ("04_road_edge", "도로경계", None, 40, (0.1, 0.15)),
    ("05_road_center", "도로중심선", None, 60, (0.1, 0.1)),
    ("06_rail", "철도·역", None, 80, (0.3, 0.4)),
    ("07_bldg_low", "건물 1~4층", 12, 45, (0.08, 0.12)),
    ("07_bldg_mid", "건물 5~9층", 22, 45, (0.08, 0.12)),
    ("07_bldg_high", "건물 10~19층", 32, 45, (0.08, 0.12)),
    ("07_bldg_tower", "건물 20층+", 45, 45, (0.08, 0.12)),
    ("08_parcel", "지적선", None, 50, (0.05, 0.08)),
    ("08b_parcel_no", "지번", None, 60, (0, 0)),
    ("09_contour", "등고선", None, 35, (0.08, 0.1)),
    ("10_site", "대상지", None, 100, (0.7, 0.9)),
    ("10b_site_lots", "합필 전 필지", None, 70, (0.1, 0.15)),
    ("11_zoning", "용도지역·지구단위", None, 70, (0.3, 0.4)),
    ("12_labels", "주기", None, 85, (0, 0)),
    ("13_grid", "격자", None, 25, (0.1, 0.1)),
]
BM_FLOOR_BREAKS = (4, 9, 19)                   # low ≤4 / mid 5~9 / high 10~19 / tower 20+
# 축척별 레이어 on/off — Export 때만 적용. 표에 없는 레이어는 그대로.
BASEMAP_SCALE_LAYERS = {
    1000: {"08_parcel": True, "08b_parcel_no": True},
    3000: {"08_parcel": True, "08b_parcel_no": False},
    5000: {"08_parcel": False, "08b_parcel_no": False},
}
BASEMAP_SCALES = (1000, 3000, 5000)
BASEMAP_DEFAULT_OFF_LAYERS = ("02b_landuse", "05_road_center", "11_zoning")
BM_HIDDEN_LAYERS = ("10b_site_lots",)   # 파일에는 넣되 꺼 둔다(.ai 레이어 보기 끔·3dm BM 하위 레이어 끔) — 합필 전 필지 외곽·지번
PAPER_SIZES_MM = {"A3": (420, 297), "A1": (841, 594), "A0": (1189, 841)}   # A3 가로 = 보고서·분석도 기본, A1·A0 = 판넬
# 베이스맵 .ai(basemap_ai) — 범위는 축척별 프레임 bbox. 객체는 bbox로 자른다.
BM_CLIP_INSET = 0.01            # m — 구멍 링은 이만큼 안쪽 사각형으로 잘라 바깥 링과 변이 겹치지 않게(겹치면 Hatch.Create 실패). 1:1000에서 0.01 mm
BM_TEXT_MM = {"08b_parcel_no": (1.5, 1000), "10b_site_lots": (1.5, 1000), "12_labels": (2.5, 3000)}   # (종이 mm, 기준 축척) → 모델 높이 m = mm × 축척 / 1000. 지번은 1:1000 전용, 주기는 1:3000 기준
# basemap_ai — Illustrator 레거시 .ai 직접 쓰기(2026-10-08 Illustrator 2026 실측)
# 한글은 CP949 바이트 + KSCms-UHC-H CMap 글꼴이어야 보인다(UTF-8 + Helvetica는 깨짐). 글꼴이 없는 PC에서도 대체 글꼴로 한글이 나온다.
import sys as _sys
AI_FONT_CMAP = ("MalgunGothic" if _sys.platform.startswith("win") else "AppleSDGothicNeo-Regular") + "-KSCms-UHC-H"
# 텍스트 글꼴(CID 글꼴-CMap, 바이트 코덱) — 한글·영어는 AI_FONT_CMAP(CP949). CP949에 없는 일본어·중국어 간체(図·駅·场地)는 같은 방식의 Shift-JIS·GBK CMap으로.
# ponytail: 일본어·중국어 CMap은 Illustrator에서 아직 확인 전(한글 KSCms-UHC-H만 2026-10-08 실측) — 깨지면 도면은 SVG를 Illustrator로 연다
AI_FONTS = {"ko": (AI_FONT_CMAP, "cp949"),
            "ja": (("YuGothic-Regular" if _sys.platform.startswith("win") else "HiraginoSans-W3") + "-90ms-RKSJ-H", "cp932"),
            "zh": (("MicrosoftYaHei" if _sys.platform.startswith("win") else "PingFangSC-Regular") + "-GBK-EUC-H", "gbk")}
AI_CHAR_SUBSTITUTES = {"\u2014": "\u2015", "\u2013": "-", "\u00a9": "(c)"}   # CP949에 없는 대시(—·–)·© → 담기는 글자
AI_CAP_HEIGHT_RATIO = 0.7      # 대문자·한글 높이 / 글꼴 크기 — 종이 mm 높이 → Tf 크기
BM_CONTOUR_INDEX_K = 55        # 계곡선(25 m) 선 톤 K — 주곡선은 09_contour 레이어 톤(K35), deliverables B.2
BM_GRID_STEP = 500.0            # m — 13_grid 간격(세계좌표 배수). 1 km 배수 선은 UserString STEP_M=1000
BM_GREEN_FACILITY_KINDS = ("공원", "녹지")   # overlays facility kind 중 02_green에 넣는 것(FACILITY_KINDS 값)
# 등고선 '구분' → 09_contour 서브레이어 ASCII 키. .ai 레이어 블록 '(BM::09_contour::main) Ln'은 Latin-1 PostScript라 한글이면 깨진다(job 1007-235316-709b 'ì£¼ê³¡ì…').
# 한글 값은 UserString GUBUN에 남긴다. 표에 없거나 비면 'main'. 톤은 전부 부모 K35(계곡선 K55는 deliverables B.2 보류 주석).
BM_DIM_STYLE_FORMAT = "Gorani_%g"               # 문자 높이(문서 단위)별 치수 스타일 이름 — 객체 TextHeight 오버라이드는 Add에서 사라진다(context_baker._get_dim_style_id)

# 생성 phase와 진행률 가중치 — panel_ui.md 진행률 규약
PHASES = ("query", "refresh", "terrain", "write_3dm", "basemap", "sheets", "tables", "import")
PHASE_WEIGHTS = {"query": 15, "refresh": 10, "terrain": 25, "write_3dm": 15, "basemap": 10, "sheets": 15, "tables": 5, "import": 5}
PHASE_LABELS = {"query": "필지·건물·지형 조회", "refresh": "건물 최신화(VWorld·건축HUB)", "terrain": "지형 TIN·면 분류·정합 측정",
                "write_3dm": "3dm 쓰기", "basemap": "베이스맵 레이어", "sheets": "현황도 시트", "tables": "조서 CSV", "import": "문서에 넣기(Import)"}
GENERATOR_HTTP_TIMEOUT = 5                     # 초. 재시도 0

# 사전 점검 예상치 계수 — run 실측(job 1007-235316-709b, BM 포함: 성수 R=500 건물 3,454동, 1:3000 .ai·시트 13·CSV 5 포함 51.2 s, context.3dm 73.1 MB)에서 역산.
# BM 없는 run(job 1007-231036-8796)은 20.1 s / 13.6 MB였다 — BM 5만 항목이 시간 2.5배·용량 5배
# 2026-10-10 실측(전체 서울 DB, 메시 건물·.ai 직접 쓰기 뒤): 반경 500 m 3,454동 8.3 s·16.8 MB / 위치 1:5000 용지 18,016동 50.7 s·110 MB
ESTIMATE_SECONDS_BASE = 2.0
ESTIMATE_SECONDS_PER_BUILDING = 1.0 / 370.0   # (50.7 − 2) / 18016
ESTIMATE_MB_PER_BUILDING = 1.0 / 170.0        # 110 / 18016 (반경 500 m는 1/205)
RADIUS_MIN, RADIUS_MAX = 100, 2000
SHEET_CATALOG = [   # (id, 키, 이름, 필요한 데이터: lot|building|terrain|road|image). 다른 언어 이름은 i18n.json(이름이 키) 하나 — 영어 이름은 영국 Design and Access Statement 현황 분석 용어. 번호 = 파일 번호(00_베이스맵.svg)
    # 도시설계 분석도(형태·조직·접근·녹지·시설) → 현황도(가로·토지·규제·건축물·지가·지형) → 직접 그리는 틀. 2026-10-13 개편 — 옛 #1 위치·범위도는 00 베이스맵이 맡는다
    (0, "base", "베이스맵", "lot"),
    (1, "figure", "도형-배경도", "building"),
    (2, "lot_size", "필지 규모", "lot"),
    (3, "density", "블록 밀도", "building"),
    (4, "transit", "대중교통 역세권", "building"),
    (5, "walk", "보행권", "road"),
    (6, "green", "녹지·수계", "building"),
    (7, "public", "생활 공공시설", "building"),
    (8, "road", "가로 위계", "road"),
    (9, "land_use", "토지이용현황", "lot"),
    (10, "land_category", "지목 현황", "lot"),
    (11, "zone", "용도지역", "lot"),
    (12, "district", "용도지구·구역", "lot"),
    (13, "facility", "도시계획시설·지구단위계획", "lot"),
    (14, "use", "건축물 용도", "building"),
    (15, "floor", "건축물 층수", "building"),
    (16, "age", "건축물 노후도", "building"),
    (17, "price", "공시지가", "lot"),
    (18, "elev", "표고", "terrain"),
    (19, "slope", "경사", "terrain"),
    (20, "view", "경관·조망 (틀)", "lot"),
    (21, "image", "이미지맵 (틀)", "lot"),
    (22, "synthesis", "종합분석 (틀)", "lot"),
    # 2026-10-14 추가 — 번호를 끼워 넣으면 저장된 sheet_ids·옛 결과 폴더가 다른 시트를 가리켜서 끝에 붙인다. image = 영상 타일(생성 때 받음, DB 무관)
    (23, "aerial", "항공사진", "image"),
    (24, "axo", "입체 매스도", "building"),   # 2026-10-15 추가 — 범위 안 건물을 평행 투상(등각)으로
]
SHEET_IDS = {key: sheet_id for sheet_id, key, _name, _needs in SHEET_CATALOG}
# 패널 2D 카드의 다이어그램 묶음 칩(전체·현황도·분석도) — 실무 보고서의 현황도/분석도 구분. 기본(베이스맵·항공사진)은 두 묶음에 다 넣고, 틀은 '전체'에만
SHEET_GROUP = dict(
    [(key, "analysis") for key in ("figure", "lot_size", "density", "transit", "walk", "green", "public", "road", "axo")] +
    [(key, "status") for key in ("land_use", "land_category", "zone", "district", "facility", "use", "floor", "age", "price", "elev", "slope")] +
    [(key, "frame") for key in ("view", "image", "synthesis")] +
    [(key, "base") for key in ("base", "aerial")])
# Korea 모드 전용 도면 — 필지·건축물대장·UPIS·공시지가가 있어야 한다. Global(OSM)은 목록에서 뺀다.
# 역세권·공공시설은 Global도 된다 — OSM 역(railway=station)·시설 면(OSM_PUBLIC_USE)
SHEET_KOREA_ONLY = ("lot_size", "density", "land_use", "land_category", "zone", "district", "facility", "use", "age", "price")
PANEL_DEFAULT_OPTIONS = {
    "lang": DEFAULT_LANG,   # 패널 언어(LANGS) — 헤더 언어 고르기
    "region": None,   # 데이터 모드 kr(국가 DB) | global(OSM) — None = 첫 실행, 패널이 정한다(국내 DB·시간대 Asia/Seoul·한국어면 kr)
    "mode": "lots", "placement": "origin",
    "output_lang": None,   # 결과물(폴더·파일 이름) 언어 OUTPUT_LANGS — None = 첫 실행, 패널이 시스템 언어로 정한다(한국어면 ko, 아니면 en)
    "radius": 250, "shape": "rect",   # 범위 기본 = 사각형 한 변 500 m(2026-10-19 사용자 결정). 방식을 바꿔도 마지막 범위를 유지한다
    "flatten_site": False, "flatten_level": "mean",
    "site_output": "curve",   # 대상지 표시(lots·area): curve = 경계 커브만, mesh = 대상지 바닥 메시도(CTX::Site::ground, 대상지 색). 필지 방식 기본 mesh   # 대상지 평탄화(lots·area) — 높이 = 경계 자연 지반의 mean|min|max
    "import_after": True,
    # 2D 자료는 기본 끔 — 주목적은 3D, 2D는 패널 결과 화면에서 3D 뒤에 고른다(make_2d, 2026-10-19). 3D만이면 실측 약 8 s, 2D까지면 시간 2.5배(ESTIMATE_* 주석)
    "make_basemap": False, "paper": "A3", "paper_mm": [420, 297], "scales": [5000], "basemap_layers_on": [],
    "basemap_preset": "a3",   # 패널 2D 카드 베이스맵 칩: a3(보고서 A3)·a1(판넬 A1) = 축척을 범위에 맞춰 자동, custom = 용지·축척 직접. 엔진은 보지 않는다
    "make_sheets": False, "sheet_ids": [sheet_id for sheet_id, key, *_ in SHEET_CATALOG if SHEET_GROUP.get(key) != "frame"],   # 그려 넣을 틀은 따로 켠다(패널 '더 넣기') "floor_breaks": [12, 20], "elev_preset": "20m",
    "make_tables": False,
    "include_minor_buildings": False,
    "include_zoning": True,   # CTX::Zoning — 용도지역·용도지구·용도구역·도시계획시설·지구단위계획 경계(현황도 11~13의 2D 커브)
    "terrain_vertex_color": False,
    "terrain_step": 0,   # 지형 표현: 0 = 매끈(TIN), > 0 = 계단형(등고 모형) 단 간격 m — 패널은 1·2·5 m. 국내 원천 등고선은 5 m 간격이라 1·2 m 단은 보간값
    "make_dwg": False,   # 2D 도면(BM::)을 .dwg로도 — CAD 사용자용. 기본 off
    "zoom_after_import": True,
    "update_later_date": "",   # 권장 업데이트 모달에서 [나중에]를 누른 날(YYYY-MM-DD) — 그날은 다시 띄우지 않는다
    "closed_notices": [],   # 패널 공지 띠에서 닫은 공지 id(매니페스트 notices) — 더보기 메뉴에서는 계속 보인다
    "style": {"preset": "std"},   # 도면 스타일 — 사용자가 바꾼 값만. 해석은 sheet_svg.get_style(STYLE_*)
}

# 기준일 경고 임계(개월) — data_sources.md §2.4. (노랑, 빨강). 노랑은 새 판이 있을 때만.
SOURCE_AGE_THRESHOLDS = {"lot": (8, 12), "building": (3, 5), "terrain": (18, 36), "upis": (3, 6)}
SOURCE_LABELS = {"lot": "필지", "building": "건물", "terrain": "지형", "api": "키"}

# ═════════════════════════════════════════════════════════
# 컨텍스트 생성 엔진 — docs/code_map.md §4~§7
# ═════════════════════════════════════════════════════════
TEST_CONTEXT_PNU = "1120011500103330139"   # 성수동2가 333-139, 5,586 ㎡ — 성수 4도엽 안쪽, 반경 1 km까지 도엽 안
TEST_CONTEXT_PNU_SMALL = "1120011500103150001"  # 성수동2가 315-1, 1,931 ㎡ — 빠른 반복용
CONTEXT_RADIUS = 500.0          # m 기본 반경 (deliverables A.2)
ORIGIN_SNAP = 100.0             # m — 대상지 중심을 이 단위로 내림해 원점으로 (07 §6.2)
ORIGIN_MAX_OFFSET = 20000.0     # m — 문서에 기록된 원점과 새 대상지 중심이 이보다 멀면 다른 지역 문서로 보고 중단
EXTENT_ARC_SEGMENTS = 12        # 버퍼 범위 꼭짓점 호 분할 수(90°당 — 500 m에서 외접 오차 1 m)
EXTENT_CIRCLE_SEGMENTS = 64     # circle 범위·퇴화 버퍼의 원 분할 수

# 대상지 방식(2026-10-10) — lots = 필지로 고르기, area = 구역 그리기(지도·Rhino 커브), point = 위치만 찍기
TARGET_MODES = ("lots", "area", "point")
REGIONS = ("kr", "global")   # 헤더 토글. kr = 국가 DB(필지·대장·UPIS·수치지형도, 한국만), global = OSM·지형 타일(어디서나, 필지·용도지역 없음)
# 방식별 기본 범위·축척 — 실무 관행에서 고른 제안값(확인 필요: 사내 기준이 있으면 바꾼다).
# 필지 = 건축 대지검토 규모, 구역 = 지구단위계획·정비구역 현황분석 규모, 위치 = 광역 베이스맵(범위 = 용지 프레임)
# 범위(radius·shape)는 방식과 무관하게 마지막 값을 쓴다 — 방식마다 덮으면 기본값이 제각각이라 혼란이었다(2026-10-19 QA)
MODE_DEFAULTS = {
    "lots": {"scales": [1000, 3000], "site_output": "mesh"},   # A3 1:1000 = 420×297 m(지번) + 1:3000 주변
    "area": {"scales": [3000], "site_output": "curve"},
    "point": {"scales": [5000], "site_output": "curve"},
}
# 패널에 보이는 범위 형태 — 어느 방식이든 원(반경)·사각형(한 변 = 2 × radius) 둘(2026-10-19, 방식마다 달라 혼란이었다).
# 엔진은 buffer·site(그린 구역 그대로)·frame(용지 프레임)도 받는다(예전 요청 호환)
SHAPES_BY_MODE = {"lots": ("circle", "rect"), "area": ("circle", "rect"), "point": ("circle", "rect")}
AREA_LOT_MIN_FRACTION = 0.5     # 구역 안 필지 = 필지 면적의 50 % 이상이 구역 안(구역계 토지조서 관행)
AREA_SAMPLE_GRID = 12           # 구역 경계에 걸친 필지의 안쪽 비율을 12×12 격자 점으로 잰다(ponytail: 근사 — 작은 필지 ±5 %)
AREA_MIN = 100.0                # ㎡ — 이보다 작은 구역은 잘못 그린 것으로 본다
AREA_MAX_SPAN = 4000.0          # m — 구역 bbox 긴 변 상한(반경 상한 2 km와 같은 규모)
AREA_MAX_VERTICES = 2000        # 구역 링 꼭짓점 상한(자기교차 검사가 n²)
CURVE_POLYLINE_TOLERANCE = 0.05 # m — Rhino 곡선 구역 커브를 폴리라인으로 바꿀 때 허용오차
UNION_TOLERANCE = 0.05          # m — 합필(필지 방식 여러 필지) 외곽선 허용오차: 이웃 필지 경계의 어긋난 정점·틈을 이만큼 붙인다(non_rhino_utils.get_merged_rings)
UNION_AREA_GAP = 0.01           # 합필 면적 ÷ 필지 면적 합이 이만큼 넘게 어긋나면 합치기 실패로 보고 필지별 외곽선을 쓴다. 겹친 필지는 최대 0.5 % 어긋났다(2026-10-21 서울 2,800묶음)
SEOUL_TM_BOUNDS = (179000.0, 536000.0, 217000.0, 567500.0)   # EPSG:5186 — 필지 DB 범위(2026-10-10 실측) — Rhino 커브가 실제 좌표인지 판정
PLACEMENTS = ("origin", "world")   # 결과 좌표: origin = 대상지 중심(100 m 내림)을 (0,0)으로, world = EPSG:5186 그대로(문서 원점 0,0)
TERRAIN_RESAMPLE = 4.0          # m — 등고선 리샘플 간격 (07 §1)
TERRAIN_GRID = 3.0              # m — 출력 지형 메시 칸(2026-10-10: 들로네 대신 쿼드 위주 — 영역 경계는 원래 선, 안쪽은 정사각 칸)
TERRAIN_GRID_MAX_FACES = 250000 # 범위 bbox ÷ 칸² 상한 — 넘으면 칸을 키운다(위치 1:5000 용지 4.2×3.0 km → 약 7 m)
TERRAIN_MARGIN = 20.0           # m — TIN 입력 범위 여유 (범위 bbox ∪ 건물 bbox + 이 값)
TERRAIN_STEP_SNAP = 1e-4        # m — 계단 지형: 단 경계에서 이만큼 안의 정점은 경계 위로 본다(투영 오차로 생기는 실오라기 면 방지)
CLASSIFY_GRID = 50.0            # m — 면 분류용 격자 버킷
WATER_LIFT = 0.02               # m — 수면 메시를 지형 위로 띄우는 높이
WATER_EDGE_STEP = 2.0           # m — 수면 경계 조밀화 간격 (TIN 입력, code_map §5.1)
WATER_SURFACE_KINDS = ("river", "stream", "lake")   # features theme water 중 수면(면)으로 다루는 kind — 3dm CTX::Water 분류·시트 바탕 수계가 같이 쓴다. shore(습지)는 TOPO_LAYERS 주석 참고
TERRAIN_CLASS_PRIORITY = ("water", "rail", "road", "green")
TERRAIN_UNION_CLASSES = ("road", "green")   # Rhino 면 분할 전에 Boolean 합집합으로 겹침을 없애는 분류 — OSM 도로면 버퍼(교차부마다 겹침)·녹지. 수면은 폴리곤별 수위를 따로 쓰므로 합치지 않는다   # 면 분류 우선순위(앞이 이김), 나머지 terrain, 범위 밖 outside (code_map §5.3)
BUILDING_SLOPE_FLAG = 3.0       # m — 발자국 정점 지형 고저차가 이보다 크면 HEIGHT_SRC에 '~slope' (deliverables A.1)
SLOPE_BREAKS_DEG = (5, 10, 15, 21, 27)       # 경사 6단계 (서울시 2013 범례)
ELEV_PRESETS = {"20m": 20.0, "50m": 50.0}    # 표고 단계 간격
ELEV_MIN_BANDS = 4                           # 이보다 단계가 적으면(평탄지) 아래 간격으로 줄인다 — 표고도에 읽을 거리가 생기게
ELEV_FINE_STEPS = (10.0, 5.0, 2.0, 1.0)
FLOOR_BREAKS_DEFAULT = (12, 20)              # 층수 현황도 구간 (C #8)
ALIGN_SAMPLE_STEP = 10.0        # m — 정합 샘플 간격 (지목 도로 경계 ↔ 수치지형도 도로경계)
ALIGN_MAX_DIST = 10.0           # m — 이보다 멀면 상대선 없음
ALIGN_LOW_SAMPLE = 200          # 표본 수 미만이면 '표본 부족'
TOPO_MINOR_KINDS = ("무벽건물", "가건물", "공사중건물")   # 보충(ngii) 행에서 기본 제외하는 종류 — DB ngii_kind 실제 값
QUERY_MARGIN = 20.0             # m — DB 질의 bounds 여유 (범위 bbox ∪ 최대 프레임 bbox + 이 값, code_map §3)
HEIGHT_GRADE_AB_MIN = 0.7       # 높이 등급 A+B 비율이 이 미만이면 height_estimate 경고 (deliverables §C #8, 08높이 §0.5)
COMPASS_DIRECTIONS = ("동", "북동", "북", "북서", "서", "남서", "남", "남동")   # 미보유 도엽 방향 표기 (atan2 45° 단위)
RUN_BAKE_CHUNK = 500            # run이 이 수만큼 베이크할 때마다 progress 콜백(취소 지점). 청크마다 Redraw 1회 — 성수 500 m 7,200개 실측으로 조정
UDT_MANAGED_KEY = "GORANI_MANAGED"  # 베이크 객체 UserString — clear_previous 대상 표시
UDT_LOT_KEY = "GORANI_LOT_KEY"      # 베이크 객체 UserString — pnus 정렬 sha1 앞 8자리
DOC_ORIGIN_KEYS = ("GORANI_ORIGIN_E", "GORANI_ORIGIN_N", "GORANI_CRS")   # doc.Strings 문서 수준 원점 기록(Blender는 장면 사용자 속성)
# 패널이 호스트마다 바꿔 쓰는 이름(init_state.host) — 문서 이름·결과 모델 파일·DWG 저장(Rhino만)·커브 가져오기.
# ask_stats = 사용 통계를 동의한 사람만 보낸다(Blender 확장 약관 4.5 '사용자 허락 없이 외부 전송 금지', 사용자 결정 2026-10-16 — Rhino는 그대로).
# SketchUp도 Extension Warehouse 심사(개인정보 정책 위반 = 반려 사유)라 동의제 — GA_STREAMS에 sketchup 속성을 넣기 전에는 묻지도 않는다
# aerial = 위성 영상(지도 배경·항공사진 시트), update_notice = 매니페스트 업데이트 모달, ip_center = 지도 첫 위치 IP 짐작(ipinfo.io) — 없으면 True, Blender는 셋 다 끈다
HOST_LABELS = {
    "rhino": {"id": "rhino", "name": "Rhino", "doc": "Rhino 문서", "model": CONTEXT_MODEL_FILE_NAME, "dwg": True, "ask_stats": False},
    "blender": {"id": "blender", "name": "Blender", "doc": "Blender 장면", "model": BLENDER_MODEL_FILE_NAME, "dwg": False, "ask_stats": True,
                "aerial": False, "update_notice": False, "ip_center": False},   # 확장 스토어 약관: 상용 영상(Esri)·제3자 IP 조회 불가, 업데이트는 Blender가 한다
    "sketchup": {"id": "sketchup", "name": "SketchUp", "doc": "SketchUp 모델", "model": SKETCHUP_MODEL_FILE_NAME, "dwg": False, "ask_stats": True},
    "web": {"id": "web", "name": "브라우저", "doc": "3D 모델", "model": WEB_MODEL_FILE_NAME, "dwg": False, "ask_stats": False},   # 통계는 웹사이트 GA(페이지)만
}
# 메시판(mesh_geometry — Blender·SketchUp)
CDT_EPSILON = 1e-4              # m — CDT 근접 판정(mathutils delaunay_2d_cdt는 0이면 안 된다, shapely판은 겹치기 격자). 0.1 mm — 원천 좌표는 mm 반올림
# Blender판(cmd_blender)
BLENDER_PANEL_POLL = 0.1        # s — 브라우저 패널 명령을 Blender 메인 스레드에서 꺼내는 간격(bpy.app.timers)
BLENDER_VIEW_CLIP_END = 20000.0  # m — 줌할 때 3D 뷰 먼 클리핑(기본 1 km면 반경 1 km 지형이 잘린다)
BLENDER_CURVE_WAIT = 60.0       # s — [Blender 커브 가져오기]를 눌렀는데 고른 커브가 없을 때 Blender에서 고르기를 기다리는 시간(Rhino 고르기 프롬프트 자리)
# SketchUp판(cmd_sketchup 사이드카 — 번들 파이썬 + sketchup_ext.rb)
HOST_ENV = "GORANI_HOST"     # SketchUp 사이드카는 'sketchup', 웹판 워커는 'web'으로 둔다 — context_builder.get_host
SKETCHUP_HOST_TIMEOUT = 1800.0  # s — 호스트 호출(베이크 등) 응답 대기 상한. 패널을 닫으면(Ruby가 panel_closed를 stdin으로) 기다리지 않고 바로 실패한다
SKETCHUP_HOST_POLL = 0.5        # s — 응답을 기다리며 패널 닫힘을 확인하는 간격
SKETCHUP_ZOOM_MIN_SPAN = 400.0  # m — 생성 뒤 화면 맞춤에서 대상지 + 여백의 최소 한 변. 작은 필지도 주변 맥락이 보이게(Rhino는 대상지 + 대각선 반 여백만)
SKETCHUP_GROUND_CELL = 5.0      # m — 지반 높이 조회 격자 칸(mesh_geometry._Ground shapely판). 지형 리샘플 4 m 삼각형이 칸마다 열 개 안팎
# 웹판(cmd_web — 브라우저 Pyodide 워커 web_worker.js + 페이지 web_app.html). Pyodide·three.js 주소는 JS 파일 맨 위 상수
# 반경 상한 — 2026-10-19 실측(Chrome·Apple M5, 성수 333-139): 500 m 5 s·탭 0.8 GB, 1 km 11 s·0.9 GB, 2 km 39 s·1.8 GB(시군구 팩 6곳 681 MB 포함).
# CPU 4배 감속(오래된 보급형 노트북 가정)이면 500 m 20 s·1 km 45 s. 3 km는 팩만 1.8 GB(10곳)라 탭 메모리에 못 든다
WEB_MAX_RADIUS = 2000.0
# CTX::Ref UserString 고정 문자열 — deliverables §A.1 Ref 행. TRANSFORM은 UPIS 5174→5186 변환(META_CRS_LINE과 같은 근거), VDATUM은 수치지형도 표고 기준
REF_TRANSFORM = "EPSG:5189 (UPIS EPSG:5174→5186, 공칭 ±1 m)"
REF_VDATUM = "인천만 평균해수면(수준원점 26.6871 m)"
# 조서·메타(context_report) — deliverables §C 공통 ①~⑤·§E 폴더 규약
# 결과물 언어 — 폴더·파일 이름만(패널 글은 한국어). 언어를 더하려면 OUTPUT_LANGS에 코드, OUTPUT_NAMES에 같은 꼴의 dict 하나를 더한다
# (ja·zh·es 예정, 2026-10-21 사용자). 없는 항목은 영어로 채운다(non_rhino_utils.get_output_name). context.3dm·context.json·log.txt는 프로그램이 읽어 언어와 무관
OUTPUT_LANGS = (("ko", "한국어"), ("en", "English"))
OUTPUT_LANG_DEFAULT = "ko"
OUTPUT_NAMES = {
    "ko": {"area": "구역", "vicinity": "일대", "more": "외%d", "basemap": "베이스맵_%d", "sheets_dir": "다이어그램", "tables_dir": "조서",
           "tables": {"parcels": "필지조서", "buildings": "건축물조서", "sheet_stats": "도면통계", "height_src_stats": "높이출처통계", "alignment": "정합점검"},
           "styles": {"std": "표준", "vivid": "선명", "mono": "흑백", "dark": "다크"}},
    "en": {"area": "area", "vicinity": "vicinity", "more": "+%d", "basemap": "basemap_%d", "sheets_dir": "sheets", "tables_dir": "tables",
           "tables": {"parcels": "parcels", "buildings": "buildings", "sheet_stats": "sheet_stats", "height_src_stats": "height_src_stats", "alignment": "alignment"},
           "styles": {"std": "Standard", "vivid": "Vivid", "mono": "Mono", "dark": "Dark"}},
}   # 도면 이름은 여기 말고 i18n.json(SHEET_CATALOG 이름이 키) — non_rhino_utils.get_sheet_label
RESULT_2D_DIR_FORMAT = "2D_%s_%s"   # (스타일 이름, HHMM) — [2D 자료 만들기]마다 결과 폴더 안 새 폴더. 같은 결과에 스타일을 바꿔 다시 만들면 앞 것을 덮어썼다(2026-10-21 사용자)
RESULT_2D_DIRNAME = "2D"   # 2D 산출물(베이스맵 .ai·.dwg·sheets/·tables/)을 결과 폴더 안 한곳에 — 패널 2D 카드 [폴더 열기]가 여기를 연다(2026-10-19)
RESULT_TABLES_DIRNAME = "tables"
RESULT_SHEETS_DIRNAME = "sheets"
# data_sources.source_id → 메타 역할(lot·building·terrain·upis). prepare가 DataSource 객체를 그대로 넘겨도 역할을 찾는다
SOURCE_ID_ROLES = {"vworld_land_char": "lot", "vworld_building": "building", "ngii_topo_5000": "terrain", "seoul_zoning": "upis",
                   "osm": "building", "aws_terrain": "terrain",   # osm·aws_terrain = 해외 대상지(osm_context)
                   "plateau": "building", "gsi_dem": "terrain"}   # 일본 — PLATEAU 건물 팩·지리원 표고 타일(뒤에 둔 것이 역할을 차지한다)
GLOBAL_SOURCE_IDS = ("osm", "aws_terrain", "plateau", "gsi_dem")   # 이 출처가 하나라도 있으면 Global 산출물(메타 줄·도면 문구) — 일본은 OSM 없이도 만든다
META_SOURCE_NAMES = {"lot": "필지 토지특성정보", "building": "건물 GIS건물통합정보", "upis": "도시계획 서울시 UPIS", "terrain": "지형 수치지형도 1:5,000"}
# ② 출처·라이선스 — 토지특성·토지이용계획은 '이용허락범위 제한 없음'(공공누리 1유형/CC BY로 적지 않는다, data_sources §3)
META_SOURCE_LINE = ("출처: 국토교통부(GIS건물통합정보 — CC BY/공공누리 1유형; 토지특성정보·토지이용계획정보 — 이용허락범위 제한 없음), "
                    "서울특별시(UPIS, 공공누리 1유형, 법적 효력 없음), 국토지리정보원(수치지형도 Ver2.0, 공공누리 1유형) · "
                    "본 데이터는 정보제공 목적이며 법적 효력이 없음")
# ③ 좌표계·정확도 — 수치지형도 고시 제2026-2524호, 지적측량 시행규칙 제27조
META_CRS_LINE = ("좌표계 EPSG:5186 (KGD2002 / Central Belt 2010); 도시계획 레이어 EPSG:5174→5186 (EPSG:5189, 공칭 ±1 m) · "
                 "수치지형도 1:5,000 절대정확도 95 % 1.5 m·최대 3.0 m · 지적 경계점 허용 ±0.36 m")
AGE_BANDS_YEARS = (10, 20, 30)   # 노후도 구간 (C #9)

# ═════════════════════════════════════════════════════════
# 현황도 시트(sheet_svg) — deliverables §C 1~13, code_map §2 'SHEETS 선언 표'
# ═════════════════════════════════════════════════════════
# ── 도면 템플릿 (A3 가로 기준 mm. 다른 용지는 min(가로/420, 세로/297)배로 키운다) ──
# side = 정사각 지도 + 오른쪽 정보 열, bottom = 넓은 지도 + 아래 정보 띠, map = 지도만(축척·방위·출처 한 줄은 남긴다)
SHEET_TEMPLATE_MM = {"margin": 12.0, "gap": 12.0, "column": 111.0, "strip": 50.0}
SHEET_FONT_MM = {"number": 11.0, "title": 5.4, "subtitle": 2.2, "head": 2.6, "body": 2.4, "small": 2.1, "meta": 1.7, "label": 2.3}
SHEET_LEGEND_ROW_MM = 5.0        # 범례 한 줄 높이(정보 열)
SHEET_SCALE_BAR_M = {1000: 100.0, 3000: 300.0, 5000: 500.0}   # 축척별 축척 막대 길이 — 4칸(0·¼·½·1)
SHEET_LINE_MM = {"parcel": 0.08, "site": 0.6, "extent": 0.3, "frame": 0.35, "building": 0.05, "rail": 0.35, "station": 0.45}
SHEET_CLIP_MARGIN_MM = 2.0       # 면 형상을 지도 칸 밖 이 거리에서 잘라 쓴다(도로 필지·시설 결정선 같은 거대 폴리곤이 파일을 키운다 — 성수 #6 2.4 MB 실측)
SHEET_MIN_VERTEX_MM = 0.05       # 종이에서 이보다 가까운 연속 정점은 버린다(1:3000에서 0.15 m — 선굵기 0.08 mm 아래)
SHEET_PARCEL_MAX_SCALE = 3000    # 이 축척보다 작은 도면(1:5000)은 지적선을 그리지 않는다 — deliverables B.2 '1:5000 지적선 off'
SHEET_FADE_TO_PAPER = 0.45       # 주제도의 바탕(가구·건물·녹지·수계)을 종이색 쪽으로 이만큼 흐린다 — 주제 색이 먼저 읽히게
SHEET_HEIGHT_SRC_LABELS = {"height": "대장 높이", "grnd_flr": "대장 층수", "topo_flr": "지형도 층수", "hub": "건축HUB", "default": "기본값",
                           "osm_height": "OSM 높이", "osm_levels": "OSM 층수",
                           "plateau_height": "PLATEAU 실측 높이", "plateau_levels": "PLATEAU 층수"}  # 층수 카드, A.4 HEIGHT_SRC. 여기 없는 키는 data_pack.get_height_src_label이 팩 라벨로 만든다
HEIGHT_SRC_KIND_LABELS = {"height": "{0} 높이", "height_rel": "{0} 높이", "levels": "{0} 층수", "roof": "{0} 지붕 높이"}   # '<source_id>_<종류>' 꼴 height_src의 종류 — 새 나라 팩은 코드 수정 없이
SHEET_HATCH = {"landlocked": {"stroke": "#D83A3A", "stroke-width": 0.25, "spacing_mm": 1.5}}   # <pattern id="hatch_<키>"> 45° 사선
# 지명 라벨에서 뺄 이름 — 수치지형도 명칭 레이어에 공사장 안내가 섞여 있다(성수 '성수동오피스신축공사(24년01월예정)' 2026-10-13 실측)
SHEET_LABEL_SKIP_PATTERN = r"공사|예정|\d{2}년"
SHEET_TRANSIT_RADII_M = (250.0, 500.0)   # 역세권 1차·2차 — 서울시 2017 역세권 기준 반경(deliverables C #17). 역 중심점 기준(출입구 아님)
SHEET_TRANSIT_COLOR = "#2D6CB5"
SHEET_LOT_SIZE_BREAKS = (90.0, 200.0, 500.0, 1000.0, 3000.0)   # ㎡ — 90 = 서울시 건축조례 주거지역 분할 최소면적, '과소필지' 기준(deliverables C #21)
SHEET_DENSITY_BREAKS = (100.0, 200.0, 300.0, 500.0, 800.0)     # 블록 용적률 % — 2종일반 200·3종 250~300·준주거 400~500·상업 800 언저리를 가른다
SHEET_BLOCK_MIN_AREA = 300.0     # ㎡ — 도로 필지 구멍 중 이보다 작은 것은 블록이 아니다(교통섬·조각)
SHEET_WALK_SPEED_M_PER_MIN = 80.0   # 4.8 km/h — 보행권 관행(5분 400 m · 10분 800 m)
SHEET_WALK_MINUTES = (5, 10, 15)
SHEET_WALK_COLORS = ("#0E5C49", "#4FAF8E", "#A9D9C7")   # 5분 진하게 → 15분 옅게(선 굵기도 1.0 → 0.6 mm)
SHEET_WALK_SNAP_M = 1.0          # 도로 중심선 정점을 이 격자로 맞춰 교차점을 잇는다(수치지형도 A002는 교차점에서 끊겨 끝점이 같다)
SHEET_WALK_START_M = 150.0       # 대상지 중심에서 이 거리 안 중심선 정점을 출발점으로(직선 거리를 더한다)
SHEET_PUBLIC_USE = {"10": "education", "09": "welfare", "11": "welfare", "05": "culture", "12": "culture", "13": "culture"}   # 건축물대장 용도 앞 2자리
SHEET_PUBLIC_NGII = {"교육연구시설": "education", "의료시설": "welfare", "노유자(노인및어린이)시설": "welfare",
                     "문화및집회시설": "culture", "운동시설": "culture", "수련시설": "culture"}   # 대장 용도가 빈 건물은 수치지형도 용도로
SHEET_PUBLIC_FACILITY = {"광장": "plaza", "공공공지": "plaza", "자동차정류장": "plaza", "보건위생시설": "welfare"}   # UPIS 시설 — 학교·청사는 서울 UPIS 시설 레이어에 없다(2026-10-13 확인)
SHEET_NO_MASK = ("base", "walk", "aerial")   # 범위 밖을 흐리지 않는 시트 — 보행권은 15분(1.2 km)이 범위보다 넓다, 항공사진은 주변이 곧 내용
SHEET_TEMPLATE_KEYS = ("view", "image", "synthesis")   # 직접 그리는 틀 — 빈 레이어와 범례만
SHEET_THUMB_PX = 160             # 패널 도면 칸 썸네일(정사각 지도 칸 가운데) 한 변 px — PNG 1장 ≈ 5~15 KB
# 항공사진 시트 — 웹 메르카토르 영상 타일을 받아 SVG <image>로 깐다(JPEG을 풀지 않는다). 타일 URL·출처는 review_map.get_tile_config(패널 지도와 같은 선택)
AERIAL_DPI = 150                 # 인쇄 해상도 목표 — A3 1:5000이면 줌 18(위도 37°에서 0.47 m/px, 타일 ≈150장·SVG ≈4 MB). 원천 정사영상은 25~51 cm
AERIAL_PREVIEW_DPI = 60          # 패널 '도면 스타일' 미리보기 — 인쇄 해상도 SVG(수 MB)를 웹뷰로 밀지 않는다
AERIAL_MAX_ZOOM = 19             # VWorld 영상·Esri 공통 최대 줌
AERIAL_ZOOM_DROPS = 2            # 그 줌에 영상이 없으면(Esri 404) 낮춰 보는 단계 수 — 1:1000 시트 z19 → z17까지
AERIAL_MAX_TILES = 400           # 한 장 상한 — 넘으면 줌을 한 단계씩 낮춘다(A1 1:5000 줌 18 ≈ 530장 → 17)
AERIAL_TIMEOUT_SECONDS = 10      # 타일 한 장
AERIAL_WORKERS = 8               # 동시에 받는 타일 수
AERIAL_TILE_OVERLAP = 1.0 + 1.0 / 256   # 타일을 1 px 겹쳐 놓는다 — 뷰어 안티앨리어싱으로 생기는 타일 사이 머리카락 틈을 덮는다
# 입체 매스도(axo) — 범위 안 건물(발자국 × height_m)을 평행 투상. 시점은 Rhino _SetView 등각 넷과 같다(카메라가 있는 방위). 지형은 평탄 가정
AXO_VIEWS = {"se": ("남동 등각", 135.0), "sw": ("남서 등각", 225.0), "ne": ("북동 등각", 45.0), "nw": ("북서 등각", 315.0)}   # (이름, 카메라 방위각 — 북 0°, 시계)
AXO_ELEVATION_DEG = 35.264       # 등각 투상 고도각 = atan(1/√2) — Rhino Isometric과 같다
AXO_MARGIN_MM = 10.0             # 지도 칸 가장자리 여백(A3 기준 — 용지 배율을 곱한다)
AXO_LINE_MM = 0.12               # 건물 모서리 선(평면 건물선 0.05 mm는 입체에서 묻힌다)
AXO_WALL_SHADE = (0.12, 0.28)    # 벽 두 방향(화면 오른쪽·왼쪽을 향한 면)을 글자색 쪽으로 섞는 비율 — 지붕은 건물색 그대로
AXO_EDGE_SHADE = 0.6             # 모서리 선 = 건물색을 글자색 쪽으로 이만큼
AXO_SITE_TINT = 0.55             # 대상지 안 건물 면을 대상지 색 쪽으로 섞는 비율 — 대상지가 먼저 읽히게

# ── 도면 스타일 (패널 '도면 스타일' 화면 · HOME_DIR/styles/*.json · options.style) ──
# 색은 도면 요소별, 나머지는 전 도면 공통. 법정·관행 색표가 있는 주제(용도지역·토지이용)는 SHEET_LEGENDS에 고정 — 바꾸면 보는 사람이 오독한다
STYLE_COLOR_KEYS = ("paper", "block", "road", "green", "water", "building", "rail", "site", "extent", "ink")
STYLE_RAMPS = {   # 단계색(층수·노후도·지가·표고) 6단 — 단계 수가 다르면 sheet_svg가 보간
    "warm": ("#FBEFC9", "#F5D58A", "#EDB45C", "#DB8A3A", "#B85E2A", "#7E3A1E"),
    "cool": ("#E3EEF7", "#B9D3EA", "#86B2DA", "#5288C2", "#2D62A3", "#173F73"),
    "green": ("#E8F2DC", "#C4DFA6", "#97C46F", "#66A045", "#3F7A2E", "#22501D"),
    "mono": ("#EEEEEE", "#D0D0D0", "#ABABAB", "#828282", "#575757", "#2E2E2E"),
}
STYLE_PRESETS = {
    "std": {"name": "표준", "paper": "#FFFFFF", "block": "#ECECE8", "road": "#FFFFFF", "green": "#DDE6D3", "water": "#D2DEE7",
            "building": "#C2C2BC", "rail": "#8C8C88", "site": "#E2412F", "extent": "#2B2B29", "ink": "#2B2B29", "ramp": "warm"},
    "vivid": {"name": "선명", "paper": "#FFFFFF", "block": "#E8EDF1", "road": "#FFFFFF", "green": "#C9E0BA", "water": "#B7D2EC",
              "building": "#98A6B3", "rail": "#4E5A66", "site": "#FF4F1F", "extent": "#16202A", "ink": "#16202A", "ramp": "cool"},
    "mono": {"name": "흑백", "paper": "#FFFFFF", "block": "#EDEDED", "road": "#FFFFFF", "green": "#E0E0E0", "water": "#D5D5D5",
             "building": "#BDBDBD", "rail": "#6E6E6E", "site": "#111111", "extent": "#111111", "ink": "#111111", "ramp": "mono"},
    "dark": {"name": "다크", "paper": "#15181C", "block": "#23272D", "road": "#15181C", "green": "#27332A", "water": "#1E2A35",
             "building": "#464B53", "rail": "#7A828E", "site": "#FF6A4D", "extent": "#D9DDE3", "ink": "#E6E8EB", "ramp": "cool"},
}
STYLE_DEFAULT_PRESET = "std"
STYLE_DEFAULTS = {"layout": "side", "line_scale": 1.0, "text_scale": 1.0, "font": "sans", "fade_outside": 0.55,
                  "labels": True, "subtitle_en": True, "project": "", "axo_view": "se"}
STYLE_CHOICES = {"layout": ("side", "bottom", "map"), "font": ("sans", "serif"), "ramp": tuple(STYLE_RAMPS), "axo_view": tuple(AXO_VIEWS)}
STYLE_RANGES = {"line_scale": (0.5, 2.0), "text_scale": (0.8, 1.4), "fade_outside": (0.0, 0.8)}
STYLE_FONTS = {"sans": "Pretendard, 'Apple SD Gothic Neo', 'Malgun Gothic', 'Noto Sans KR', sans-serif",
               "serif": "'Noto Serif KR', AppleMyungjo, Batang, serif"}
# 일본어·중국어 도면은 그 언어 글꼴을 STYLE_FONTS 앞에 둔다 — 한국어 글꼴이 같은 한자를 한국식 자형으로 그리지 않게.
# 일본어 고딕은 Hiragino Sans가 아니라 ProN — 굵기 800이 W9로 가서 넓은 숫자가 번호(04) 옆 제목에 겹쳤다(2026-10-21 rsvg 확인)
STYLE_FONTS_CJK = {"ja": {"sans": "'Hiragino Kaku Gothic ProN', 'Yu Gothic', Meiryo, 'Noto Sans JP', ", "serif": "'Hiragino Mincho ProN', 'Yu Mincho', 'Noto Serif JP', "},
                   "zh": {"sans": "'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', ", "serif": "'Songti SC', SimSun, 'Noto Serif SC', "}}
STYLE_PROJECT_MAX = 60           # 표제 프로젝트명 글자 수 상한
STYLES_DIRNAME = "styles"        # HOME_DIR/styles/<이름>.json — 사무소 표준을 파일로 나눠 쓴다

# 시트 키 → (대상, [(키, 범례 라벨, SVG 스타일 attrs)]). 대상 ∈ target_lot|lot|overlay|building|road|terrain|station|green.
# 분류 함수(sheet_svg.SHEETS)가 돌려주는 키가 이 표에 있어야 그려진다. 범례 색이 스타일·데이터로 정해지는 시트(베이스맵·도형-배경·역세권·
# 층수·노후도·지가·표고)는 [] 두고 sheet_svg가 만든다(스타일 요소 색, 단계색 STYLE_RAMPS).
SHEET_LEGENDS = {
    "base": ("target_lot", []),       # 대상지 + 바탕 요소 — 스타일 색
    "figure": ("building", []),       # 건물 = 글자·선 색, 나머지 = 종이
    "transit": ("station", []),       # 역 · 250/500 m 원 · 철도 강조(SHEET_TRANSIT_COLOR)
    "lot_size": ("lot", []),          # 필지 면적 6구간(SHEET_LOT_SIZE_BREAKS) — 단계색. 도로·하천 필지는 뺀다
    "density": ("block", []),         # 블록(도로 필지 구멍) 용적률 6구간 — 단계색
    "walk": ("walk", []),             # 도로 중심선 네트워크 거리 5·10·15분 — SHEET_WALK_COLORS
    "public": ("public", [            # 건축물대장 용도·지목 학교용지·UPIS 광장·공공공지
        ("school_lot", "학교 부지", {"fill": "#F6E3B4", "stroke": "#B08A2E", "stroke-width": 0.2}),
        ("plaza", "광장·공공공지·정류장", {"fill": "#E7DDF2", "stroke": "#6E5FA0", "stroke-width": 0.2}),
        ("education", "교육연구 시설", {"fill": "#D9822B"}),
        ("welfare", "의료·노유자 시설", {"fill": "#C43C3C"}),
        ("culture", "문화·집회·체육 시설", {"fill": "#6E5FA0"}),
    ]),
    "view": ("none", [                # 직접 그리는 틀 — 빈 레이어(조망점 근경 250 m·중경 500 m·원경, 눈높이 1.5 m — deliverables D.1)
        ("viewpoint", "조망점", {"shape": "circle", "fill": "#FFFFFF", "stroke": "#C2185B", "stroke-width": 0.5}),
        ("axis", "조망축", {"fill": "none", "stroke": "#C2185B", "stroke-width": 0.8, "stroke-dasharray": "3 1.5"}),
        ("landmark", "경관 요소", {"fill": "#F4B6C8", "stroke": "#C2185B", "stroke-width": 0.3}),
        ("barrier", "시야 차폐", {"fill": "none", "stroke": "#555555", "stroke-width": 1.2}),
    ]),
    "image": ("none", [               # 케빈 린치 도시 이미지 5요소
        ("path", "통로", {"fill": "none", "stroke": "#2D6CB5", "stroke-width": 1.2}),
        ("edge", "경계", {"fill": "none", "stroke": "#8E2F2F", "stroke-width": 1.6, "stroke-dasharray": "4 1.5"}),
        ("district", "지역", {"fill": "#F3E3B8", "stroke": "#B08A2E", "stroke-width": 0.3}),
        ("node", "결절점", {"shape": "circle", "fill": "#FFFFFF", "stroke": "#2D6CB5", "stroke-width": 0.6}),
        ("landmark", "랜드마크", {"fill": "#2B2B29"}),
    ]),
    "aerial": ("none", []),           # 영상 타일 + 대상지·범위 선 — 범례는 sheet_svg가 만든다
    "axo": ("none", []),              # 평행 투상 건물·바닥(도로·수계·녹지·대상지) — 범례는 sheet_svg가 만든다
    "synthesis": ("none", [           # 제약·기회 두 층 — 현황도를 겹쳐 사람이 판단한다(03 §5)
        ("opportunity", "기회·강점", {"fill": "#CFE8D8", "stroke": "#1F8A5B", "stroke-width": 0.3}),
        ("constraint", "제약·약점", {"fill": "#F6D0C8", "stroke": "#C43C3C", "stroke-width": 0.3}),
        ("improve", "개선 대상", {"fill": "none", "stroke": "#A8460B", "stroke-width": 0.8, "stroke-dasharray": "2 1"}),
        ("link", "연계 축", {"fill": "none", "stroke": "#2D6CB5", "stroke-width": 1.2}),
        ("hub", "거점", {"shape": "circle", "fill": "#2D6CB5", "stroke": "#2D6CB5", "stroke-width": 0.5}),
    ]),
    "green": ("green", [              # 공원(도시계획시설·지목) · 녹지(임야·수치지형도 녹지) · 수계(지목·수면)
        ("park", "공원", {"fill": "#8DBF73", "stroke": "#5E8F48", "stroke-width": 0.15}),
        ("green", "녹지·임야", {"fill": "#C3DDAE"}),
        ("water", "하천·수면", {"fill": "#86B3DA"}),
    ]),
    "land_use": ("lot", [   # parcels.land_use_status → 2013 도시관리계획 수립지침 토지이용 재분류(단독/공동/주상/상업/공업/나지/도로·하천·공원)
        ("detached", "단독주택", {"fill": "#F6E7A9"}), ("multi", "다세대·연립", {"fill": "#F0C96B"}),
        ("apartment", "아파트", {"fill": "#E09A3C"}), ("residential_etc", "주거 기타", {"fill": "#F9F0CF"}),
        ("mixed", "주상복합", {"fill": "#F2B7A3"}), ("commercial", "상업·업무", {"fill": "#E07070"}),
        ("industrial", "공업", {"fill": "#A9B4D6"}), ("vacant", "나지", {"fill": "#FFFFFF", "stroke": "#8A8A86"}),
        ("road", "도로", {"fill": "#D9D9D6"}), ("water", "하천", {"fill": "#C9D8E8"}), ("park", "공원·녹지", {"fill": "#C5DBB9"}),
        ("etc", "기타·미상", {"fill": "#EFEFEC"}),
    ]),
    "land_category": ("lot", [   # parcels.land_category 28 지목 → 통합 범례
        ("site", "대", {"fill": "#F6E7A9"}), ("factory", "공장용지", {"fill": "#A9B4D6"}), ("road", "도로", {"fill": "#D9D9D6"}),
        ("water", "하천·구거·유지", {"fill": "#C9D8E8"}), ("levee", "제방", {"fill": "#D8CFC0"}), ("farm", "전·답·과수원", {"fill": "#E4ECC8"}),
        ("forest", "임야", {"fill": "#B9CFA8"}), ("park", "공원", {"fill": "#C5DBB9"}), ("school", "학교용지", {"fill": "#F2C7D6"}),
        ("religion", "종교용지", {"fill": "#E8D2EC"}), ("rail", "철도용지", {"fill": "#B9B9B4"}), ("parking", "주차장·주유소", {"fill": "#D0CCDD"}),
        ("public", "공공시설(수도·창고 등)", {"fill": "#CFE1E6"}), ("misc", "잡종지", {"fill": "#EFE6D3"}), ("etc", "기타·미상", {"fill": "#EFEFEC"}),
    ]),
    "zone": ("lot", [   # parcels.zone_name → 도시·군관리계획 수립지침 도면 색표의 RGB 근사(ACI 변환표는 확인 필요)
        ("r1e", "제1종전용주거", {"fill": "#FFF6C2"}), ("r2e", "제2종전용주거", {"fill": "#FFEFA0"}),
        ("r1", "제1종일반주거", {"fill": "#FFE680"}), ("r2", "제2종일반주거", {"fill": "#FFD966"}), ("r3", "제3종일반주거", {"fill": "#F4B942"}),
        ("rq", "준주거", {"fill": "#F2A08C"}), ("c_center", "중심상업", {"fill": "#D83A3A"}), ("c_general", "일반상업", {"fill": "#E86060"}),
        ("c_near", "근린상업", {"fill": "#F08C8C"}), ("c_dist", "유통상업", {"fill": "#F5B0B0"}),
        ("i_exclusive", "전용공업", {"fill": "#6F7FC2"}), ("i_general", "일반공업", {"fill": "#8F9CD3"}), ("i_quasi", "준공업", {"fill": "#B3BCE2"}),
        ("g_conserve", "보전녹지", {"fill": "#7FB77E"}), ("g_produce", "생산녹지", {"fill": "#A6CF9E"}), ("g_natural", "자연녹지", {"fill": "#CFE6C3"}),
        ("etc", "기타·미지정", {"fill": "#EFEFEC"}),
    ]),
    "district": ("overlay", [   # overlays theme district(용도지구)·area(용도구역) — v1은 색 경계선 + 라벨
        ("district", "용도지구", {"fill": "none", "stroke": "#B05A1E", "stroke-width": 0.5}),
        ("area", "용도구역", {"fill": "none", "stroke": "#2F6DB5", "stroke-width": 0.5, "stroke-dasharray": "2 1"}),
    ]),
    "facility": ("overlay", [   # overlays theme facility(kind) + plan(지구단위계획구역) — 결정선
        ("road", "도로", {"fill": "none", "stroke": "#D83A3A", "stroke-width": 0.4}),
        ("park", "공원·녹지", {"fill": "#C5DBB9", "stroke": "#4E8A3E", "stroke-width": 0.3}),
        ("plaza", "광장·공공공지", {"fill": "#F3E3B8", "stroke": "#B08A2E", "stroke-width": 0.3}),
        ("parking", "주차장", {"fill": "#D0CCDD", "stroke": "#6E5FA0", "stroke-width": 0.3}),
        ("rail", "철도", {"fill": "none", "stroke": "#3A3A38", "stroke-width": 0.5, "stroke-dasharray": "3 1"}),
        ("facility_etc", "기타 시설", {"fill": "none", "stroke": "#7A4EA0", "stroke-width": 0.3}),
        ("plan", "지구단위계획구역", {"fill": "none", "stroke": "#1E5AA8", "stroke-width": 0.7, "stroke-dasharray": "4 1.5"}),
    ]),
    "use": ("building", [   # buildings.usability 앞 2자리(VWorld 건축물용도코드 33종) → 대분류
        ("detached", "단독주택", {"fill": "#F6E7A9"}), ("apartment", "공동주택", {"fill": "#E09A3C"}),
        ("neighborhood", "근린생활시설", {"fill": "#E07070"}), ("culture", "문화·집회·종교·판매", {"fill": "#D98CB3"}),
        ("education", "교육연구", {"fill": "#8FB8DE"}), ("welfare", "노유자·의료", {"fill": "#B5D8C8"}),
        ("office", "업무", {"fill": "#7F8FC9"}), ("lodging", "숙박·위락", {"fill": "#C9A0DC"}),
        ("factory", "공장·창고", {"fill": "#A3A3C2"}), ("vehicle", "자동차·위험물", {"fill": "#BFBFBF"}),
        ("etc", "기타", {"fill": "#E5E5E2"}), ("unknown", "용도 미상", {"fill": "#FFFFFF", "stroke": "#8A8A86"}),
    ]),
    "floor": ("building", []),   # 층수 — 1/2~3/4/5~6/7~b1/b1+1~b2/b2+1+ (b1, b2 = options.floor_breaks). 단계색
    "age": ("building", []),     # 사용승인 경과 연수(AGE_BANDS_YEARS) 4구간 + 미상. 단계색. 철거 건물은 집계 제외(v1 status 전부 active)
    "road": ("road", [   # 수치지형도 도로중심선 도로폭(features.value) → 규칙 제9조 폭원 등급 + 맹지(parcels.road_contact)
        ("w_grand", "광로 (40 m 이상)", {"fill": "none", "stroke": "#1E1E1C", "stroke-width": 1.6}),
        ("w_large", "대로 (25~40 m)", {"fill": "none", "stroke": "#1E1E1C", "stroke-width": 1.2}),
        ("w_mid", "중로 (12~25 m)", {"fill": "none", "stroke": "#3A3A38", "stroke-width": 0.8}),
        ("w_small1", "소로1류 (10~12 m)", {"fill": "none", "stroke": "#5A5A58", "stroke-width": 0.5}),
        ("w_small2", "소로2류 (8~10 m)", {"fill": "none", "stroke": "#7A7A78", "stroke-width": 0.35}),
        ("w_small3", "소로3류 (8 m 미만)", {"fill": "none", "stroke": "#9A9A98", "stroke-width": 0.2}),
        ("w_unknown", "폭 미상", {"fill": "none", "stroke": "#9A9A98", "stroke-width": 0.2, "stroke-dasharray": "1 1"}),
        ("landlocked", "맹지", {"fill": "url(#hatch_landlocked)", "stroke": "#D83A3A", "stroke-width": 0.2}),   # 사선 해치(SHEET_HATCH)
    ]),
    "price": ("lot", []),   # 공시지가 5분위 — 데이터 분위수로 범례 생성. 단계색
    "elev": ("terrain", []),   # 표고 — ELEV_PRESETS 간격 밴드. 단계색
    "slope": ("terrain", [   # 경사 — SLOPE_BREAKS_DEG 6단계 (서울시 2013 범례)
        ("s0", "0~5°", {"fill": "#F3F7EC", "stroke": "#F3F7EC", "stroke-width": "0.15"}), ("s1", "5~10°", {"fill": "#D9E8C4", "stroke": "#D9E8C4", "stroke-width": "0.15"}),
        ("s2", "10~15°", {"fill": "#F1DC9A", "stroke": "#F1DC9A", "stroke-width": "0.15"}), ("s3", "15~21°", {"fill": "#E7A85C", "stroke": "#E7A85C", "stroke-width": "0.15"}),
        ("s4", "21~27°", {"fill": "#C9663A", "stroke": "#C9663A", "stroke-width": "0.15"}), ("s5", "27° 이상", {"fill": "#8E2F2F", "stroke": "#8E2F2F", "stroke-width": "0.15"}),   # 같은 색 가는 선 = 삼각형 이음매 가림
    ]),
}
SHEET_PRICE_QUANTILES = 5
SHEET_LAND_USE_KEYS = {   # land_use_status → #2 키 (없으면 etc)
    "단독": "detached", "다세대": "multi", "연립": "multi", "아파트": "apartment", "주거기타": "residential_etc",
    "주상용": "mixed", "주상기타": "mixed", "상업용": "commercial", "상업기타": "commercial", "업무용": "commercial",
    "공업용": "industrial", "공업기타": "industrial",
    "주거나지": "vacant", "주상나지": "vacant", "상업나지": "vacant", "공업나지": "vacant",
    "도로등": "road", "하천등": "water", "공원등": "park",
}
SHEET_LAND_CATEGORY_KEYS = {   # land_category(지목) → #3 키 (없으면 etc)
    "대": "site", "공장용지": "factory", "도로": "road", "하천": "water", "구거": "water", "유지": "water", "제방": "levee",
    "전": "farm", "답": "farm", "과수원": "farm", "목장용지": "farm", "임야": "forest", "공원": "park", "학교용지": "school",
    "종교용지": "religion", "철도용지": "rail", "주차장": "parking", "주유소용지": "parking", "수도용지": "public", "창고용지": "public",
    "체육용지": "park", "유원지": "park", "잡종지": "misc", "사적지": "etc", "묘지": "etc", "광천지": "etc", "염전": "etc", "양어장": "etc",
}
SHEET_ZONE_KEYS = {   # zone_name 부분 문자열 → #4 키. 앞에서부터 처음 맞는 것
    "제1종전용주거": "r1e", "제2종전용주거": "r2e", "제1종일반주거": "r1", "제2종일반주거": "r2", "제3종일반주거": "r3", "준주거": "rq",
    "중심상업": "c_center", "일반상업": "c_general", "근린상업": "c_near", "유통상업": "c_dist",
    "전용공업": "i_exclusive", "일반공업": "i_general", "준공업": "i_quasi",
    "보전녹지": "g_conserve", "생산녹지": "g_produce", "자연녹지": "g_natural",
}
SHEET_FACILITY_KEYS = {"도로": "road", "공원": "park", "녹지": "park", "광장": "plaza", "공공공지": "plaza", "주차장": "parking", "철도": "rail"}
SHEET_USE_KEYS = {   # usability 앞 2자리 → #7 키
    "01": "detached", "02": "apartment", "03": "neighborhood", "04": "neighborhood",
    "05": "culture", "06": "culture", "07": "culture", "08": "welfare", "09": "welfare", "10": "education", "11": "welfare",
    "12": "culture", "13": "culture", "14": "office", "15": "lodging", "16": "lodging", "17": "factory", "18": "factory",
    "19": "vehicle", "20": "vehicle",
}
SHEET_FLOOR_BANDS_FIXED = (1, 3, 4, 6)                 # 층수 고정 구간 상한 — 뒤에 options.floor_breaks 2개가 붙는다
SHEET_ROAD_WIDTH_BREAKS = ((40.0, "w_grand"), (25.0, "w_large"), (12.0, "w_mid"), (10.0, "w_small1"), (8.0, "w_small2"), (0.0, "w_small3"))
SHEET_LANDLOCKED = "맹지"                               # parcels.road_contact 값
