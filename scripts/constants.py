"""UrbanDesignTool 상수 — 한 파일에 근거 주석과 함께 둔다. 다른 곳에 매직넘버 금지.

필지 DB·주소 해석·VWorld 호출·컨텍스트 생성 상수만 둔다. 컨텍스트(건물·도로·지형·수계) 상수는 그 모듈을 만들 때
여기에 절을 추가한다.
"""

import os

# ─────────────────────────────────────────────────────────
# 도구 이름 — 명령 앨리어스·툴바·패널 캡션이 같은 이름을 쓴다
# ─────────────────────────────────────────────────────────
TOOL_NAME = "UrbanDesignTool"
PANEL_CAPTION = "대지검토"

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
SIDO = {
    "11": ("서울특별시", "seoul"), "26": ("부산광역시", "busan"), "27": ("대구광역시", "daegu"), "28": ("인천광역시", "incheon"),
    "30": ("대전광역시", "daejeon"), "31": ("울산광역시", "ulsan"), "36": ("세종특별자치시", "sejong"), "41": ("경기도", "gyeonggi"),
    "43": ("충청북도", "chungbuk"), "44": ("충청남도", "chungnam"), "47": ("경상북도", "gyeongbuk"), "48": ("경상남도", "gyeongnam"),
    "50": ("제주특별자치도", "jeju"), "51": ("강원특별자치도", "gangwon"), "52": ("전북특별자치도", "jeonbuk"),
    "12": ("전남광주통합특별시", "jeonnamgwangju"),
}
DATABASE_CRS = 5186                   # 내부 형상 좌표계 (GRS80 중부원점, EPSG:5186)
SEOUL_SOURCE_CRS = 5174               # 서울 UPIS 공개 SHP 좌표계
RAW_DATA_DIRNAME = "data/raw"         # 공공 원천 데이터 보관 (gitignore)
LAND_CHAR_DIRNAME = "data/raw/vworld_토지특성정보"  # 시군구별 SHP 폴더 (수동 다운로드)
LAND_CHAR_ENCODING = "cp949"          # .cpg는 UTF-8이라 적혀 있으나 실제는 CP949
DATABASE_PATH = "data/seoul_site.db"  # Rhino가 읽는 필지 SQLite DB (스키마 v5)
DATABASE_SCHEMA_VERSION = 5           # 5: parcel_land_use(필지별 지역지구등 지정 현황) 추가
RESULT_DIRNAME = "result"             # 산출물(3dm·베이스맵·현황도) 저장 루트 (gitignore)
# 쓰기 자리(data/·result/·.env)의 기준 폴더. 저장소·폴더 배포판은 루트에 data/가 있어 루트를 쓴다.
# Yak 설치본은 패키지 폴더가 업데이트 때 통째로 바뀌므로 사용자 홈 아래 ~/UrbanDesignTool을 쓴다.
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

# 토지이음(국토교통부) 토지이용계획 열람 상세 — 패널의 "토지이음 ↗" 버튼이 연다.
# mode=search·isNoScr=script를 붙인 형태로 pnu가 상세 폼에 실리는 것을 확인했다.
EUM_LAND_USE_URL = (
    "https://www.eum.go.kr/web/ar/lu/luLandDet.jsp"
    "?pnu=%s&mode=search&isNoScr=script"
)

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
# 배포본은 등고선·표고점(features theme terrain)을 별도 파일로 나눈다 — 수치지형도 등고선은 국내 서버에만 둔다
# (국가공간정보 보안관리규정 별표1·공간정보관리법 제16조). 컨텍스트 DB 옆에 있으면 context_db가 붙여 읽는다.
TERRAIN_DATABASE_NAME = "seoul_terrain.db"
TERRAIN_THEME = "terrain"

# 데이터 팩 받기(data_pack.py) — Yak 설치본은 DB 없이 깔리고 패널에서 받는다
DATA_MANIFEST_URL = ""                 # 매니페스트 주소. 호스팅(Hugging Face 등)이 정해지면 채운다
DATA_STATE_FILE_NAME = "packs.json"    # data/ 안. 받은 팩의 sha256 — 바뀐 팩만 다시 받는다
DATA_TIMEOUT_SECONDS = 30              # 연결·조각 읽기 제한
DATA_CHUNK_BYTES = 1024 * 1024         # 압축 스트림을 1 MB씩 읽어 풀고 진행률을 알린다
DATA_MAX_OPEN_FILES = 11               # 한 연결에 여는 지역 DB 수 상한 — SQLite ATTACH 기본 상한 10 + main(2026-10-12 실측)
# 테이블별 객체 최대 폭 m — bbox 질의의 min_x 하한에 쓴다. dev_context_builder가 빌드 끝에 넘지 않는지 검사한다.
# 실측(2026-10-08): 건물 최대 887 m(가로·세로 중 큰 값), features 최대 2,779 m(도엽 1장 높이 — 도엽 단위로 잘려 있다).
CONTEXT_MAX_EXTENT = {"buildings": 1000.0, "features": 3000.0}
TOPO_SHEET_DIRNAME = "data/raw/수치지형도_5000"        # 도엽 zip 그대로 + sheets.csv (수동 다운로드)
TOPO_SHEET_INDEX_FILENAME = "sheets.csv"
TOPO_ENCODING = "cp949"                              # 수치지형도 SHP 속성 인코딩 (성수 4도엽 실측)
BUILDING_BULK_DIRNAME = "data/raw/vworld_GIS건물통합정보"  # AL_D010_11_<기준일>.zip (수동 다운로드)
BUILDING_BULK_ENCODING = "cp949"
BUILDING_BULK_FILE_GLOB = "AL_D010_11_*.zip"

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
# 패널(대지검토) — docs/panel_ui.md·docs/ui_spec.md
# ═════════════════════════════════════════════════════════
PANEL_VERSION = "0.1"
INSTALL_DOC = "docs/install.md"
PREFS_DIRNAME = ".urbandesigntool"            # 사용자 홈 아래. prefs.json·source_news.json
RESULT_DATE_FORMAT = "%Y%m%d"                  # result/<YYYYMMDD>/<대상지명>/
CONTEXT_MODEL_FILE_NAME = "context.3dm"
CONTEXT_META_FILE_NAME = "context.json"
BASEMAP_FILE_FORMAT = "basemap_%d.ai"          # 축척 분모
DWG_FILE_FORMAT = "basemap_%d.dwg"             # 3dm BM:: 2D 레이어만 내보낸 것(옵션 make_dwg). 축척 = 2D를 만든 축척(요청 중 가장 상세)
RESULT_LOG_FILE_NAME = "log.txt"

# 3dm 레이어 — deliverables §A.1 (부모 CTX), §B.2 (부모 BM). 색은 RGB.
CTX_ROOT_LAYER = "CTX"
BM_ROOT_LAYER = "BM"
CTX_LAYERS = {   # 이름: (RGB)
    "Site": (220, 40, 40), "Parcels": (185, 185, 180), "Buildings": (128, 128, 128), "Terrain": (236, 232, 222),
    "Water": (46, 125, 224), "Roads": (168, 168, 162), "Green": (228, 235, 226), "Rail": (110, 110, 110),
    "Bridges": (150, 150, 150), "Zoning": (200, 120, 40), "QA::cadastre_mismatch": (255, 0, 255), "Ref": (0, 0, 0),
    "Site::ground": (236, 150, 120), "Terrain::site_flat": (214, 196, 170), "Terrain::site_wall": (150, 140, 128), "Terrain::site_original": (236, 232, 222),
}
CTX_HIDDEN_LAYERS = ("Terrain::site_original",)   # 처음 만들 때 끈다(평탄화 전 원지형 — 필요할 때 켜 본다). 사용자가 켠 뒤로는 건드리지 않는다
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
PAPER_SIZES_MM = {"A1": (841, 594), "A0": (1189, 841)}
# 베이스맵 .ai(basemap_ai) — 범위는 축척별 프레임 bbox. 객체는 bbox로 자른다.
BM_CLIP_INSET = 0.01            # m — 구멍 링은 이만큼 안쪽 사각형으로 잘라 바깥 링과 변이 겹치지 않게(겹치면 Hatch.Create 실패). 1:1000에서 0.01 mm
BM_TEXT_MM = {"08b_parcel_no": (1.5, 1000), "12_labels": (2.5, 3000)}   # (종이 mm, 기준 축척) → 모델 높이 m = mm × 축척 / 1000. 지번은 1:1000 전용, 주기는 1:3000 기준
# basemap_ai — Illustrator 레거시 .ai 직접 쓰기(2026-10-08 Illustrator 2026 실측)
# 한글은 CP949 바이트 + KSCms-UHC-H CMap 글꼴이어야 보인다(UTF-8 + Helvetica는 깨짐). 글꼴이 없는 PC에서도 대체 글꼴로 한글이 나온다.
import sys as _sys
AI_FONT_CMAP = ("MalgunGothic" if _sys.platform.startswith("win") else "AppleSDGothicNeo-Regular") + "-KSCms-UHC-H"
AI_CAP_HEIGHT_RATIO = 0.7      # 대문자·한글 높이 / 글꼴 크기 — 종이 mm 높이 → Tf 크기
BM_CONTOUR_INDEX_K = 55        # 계곡선(25 m) 선 톤 K — 주곡선은 09_contour 레이어 톤(K35), deliverables B.2
BM_GRID_STEP = 500.0            # m — 13_grid 간격(세계좌표 배수). 1 km 배수 선은 UserString STEP_M=1000
BM_GREEN_FACILITY_KINDS = ("공원", "녹지")   # overlays facility kind 중 02_green에 넣는 것(FACILITY_KINDS 값)
# 등고선 '구분' → 09_contour 서브레이어 ASCII 키. .ai 레이어 블록 '(BM::09_contour::main) Ln'은 Latin-1 PostScript라 한글이면 깨진다(job 1007-235316-709b 'ì£¼ê³¡ì…').
# 한글 값은 UserString GUBUN에 남긴다. 표에 없거나 비면 'main'. 톤은 전부 부모 K35(계곡선 K55는 deliverables B.2 보류 주석).
BM_DIM_STYLE_FORMAT = "UDT_%g"               # 문자 높이(문서 단위)별 치수 스타일 이름 — 객체 TextHeight 오버라이드는 Add에서 사라진다(context_baker._get_dim_style_id)

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
SHEET_CATALOG = [   # (id, 이름, 필요한 데이터: lot|building|terrain|road)
    (1, "위치·범위도", "lot"), (2, "토지이용현황도", "lot"), (3, "지목 현황도", "lot"), (4, "용도지역도", "lot"),
    (5, "용도지구·구역도", "lot"), (6, "도시계획시설·지구단위계획구역도", "lot"), (7, "건축물 용도 현황도", "building"),
    (8, "건축물 층수 현황도", "building"), (9, "건축물 노후도 현황도", "building"), (10, "도로현황도(폭원·위계)", "road"),
    (11, "공시지가 현황도", "lot"), (12, "표고 분석도", "terrain"), (13, "경사 분석도", "terrain"),
]
PANEL_DEFAULT_OPTIONS = {
    "mode": "lots", "placement": "origin",
    "radius": 500, "shape": "circle",
    "flatten_site": False, "flatten_level": "mean",
    "site_output": "curve",   # 대상지 표시(lots·area): curve = 경계 커브만, mesh = 대상지 바닥 메시도(CTX::Site::ground, 대상지 색). 필지 방식 기본 mesh   # 대상지 평탄화(lots·area) — 높이 = 경계 자연 지반의 mean|min|max
    "import_after": True,
    "make_basemap": True, "paper": "A1", "paper_mm": [841, 594], "scales": [3000], "basemap_layers_on": [],
    "make_sheets": True, "sheet_ids": list(range(1, 14)), "floor_breaks": [12, 20], "elev_preset": "20m",
    "make_tables": True,
    "include_minor_buildings": False, "demolished": "dashed", "refresh_buildings": True, "include_api_objects": False,
    "include_zoning": False, "terrain_vertex_color": False,
    "make_dwg": False,   # 2D 도면(BM::)을 .dwg로도 — CAD 사용자용. 기본 off
    "zoom_after_import": True,
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
# 방식별 기본 범위·축척 — 실무 관행에서 고른 제안값(확인 필요: 사내 기준이 있으면 바꾼다).
# 필지 = 건축 대지검토 규모, 구역 = 지구단위계획·정비구역 현황분석 규모, 위치 = 광역 베이스맵(범위 = 용지 프레임)
MODE_DEFAULTS = {
    "lots": {"radius": 200, "shape": "circle", "scales": [1000], "site_output": "mesh"},
    "area": {"radius": 500, "shape": "site", "scales": [3000], "site_output": "curve"},
    "point": {"radius": 500, "shape": "frame", "scales": [5000], "site_output": "curve"},
}
# 패널에 보이는 범위 형태(2026-10-10 버퍼 제외). site = 그린 구역 그대로가 범위. 엔진은 buffer도 받는다(예전 요청 호환)
SHAPES_BY_MODE = {"lots": ("circle", "rect"), "area": ("site", "circle", "rect"), "point": ("frame", "circle", "rect")}
AREA_LOT_MIN_FRACTION = 0.5     # 구역 안 필지 = 필지 면적의 50 % 이상이 구역 안(구역계 토지조서 관행)
AREA_SAMPLE_GRID = 12           # 구역 경계에 걸친 필지의 안쪽 비율을 12×12 격자 점으로 잰다(ponytail: 근사 — 작은 필지 ±5 %)
AREA_MIN = 100.0                # ㎡ — 이보다 작은 구역은 잘못 그린 것으로 본다
AREA_MAX_SPAN = 4000.0          # m — 구역 bbox 긴 변 상한(반경 상한 2 km와 같은 규모)
AREA_MAX_VERTICES = 2000        # 구역 링 꼭짓점 상한(자기교차 검사가 n²)
CURVE_POLYLINE_TOLERANCE = 0.05 # m — Rhino 곡선 구역 커브를 폴리라인으로 바꿀 때 허용오차
UNION_TOLERANCE = 0.05          # m — '필지 경계에 맞추기' 필지 합집합 허용오차(필지 사이 틈 메움)
AREA_SNAP_LINEAR_CATEGORIES = ("도로", "하천", "구거", "철도용지", "제방")   # 구역계가 가로질러도 되는 선형 지목 — 길게 뻗어 50 % 규칙에 안 걸린다(2026-10-10 성수 실측: 도로가 빠져 합집합이 덩어리 3개)
SEOUL_TM_BOUNDS = (179000.0, 536000.0, 217000.0, 567500.0)   # EPSG:5186 — 필지 DB 범위(2026-10-10 실측) — Rhino 커브가 실제 좌표인지 판정
PLACEMENTS = ("origin", "world")   # 결과 좌표: origin = 대상지 중심(100 m 내림)을 (0,0)으로, world = EPSG:5186 그대로(문서 원점 0,0)
TERRAIN_RESAMPLE = 4.0          # m — 등고선 리샘플 간격 (07 §1)
TERRAIN_GRID = 3.0              # m — 출력 지형 메시 칸(2026-10-10: 들로네 대신 쿼드 위주 — 영역 경계는 원래 선, 안쪽은 정사각 칸)
TERRAIN_GRID_MAX_FACES = 250000 # 범위 bbox ÷ 칸² 상한 — 넘으면 칸을 키운다(위치 1:5000 용지 4.2×3.0 km → 약 7 m)
TERRAIN_MARGIN = 20.0           # m — TIN 입력 범위 여유 (범위 bbox ∪ 건물 bbox + 이 값)
CLASSIFY_GRID = 50.0            # m — 면 분류용 격자 버킷
WATER_LIFT = 0.02               # m — 수면 메시를 지형 위로 띄우는 높이
WATER_EDGE_STEP = 2.0           # m — 수면 경계 조밀화 간격 (TIN 입력, code_map §5.1)
WATER_SURFACE_KINDS = ("river", "stream", "lake")   # features theme water 중 수면(면)으로 다루는 kind — 3dm CTX::Water 분류·시트 바탕 수계가 같이 쓴다. shore(습지)는 TOPO_LAYERS 주석 참고
TERRAIN_CLASS_PRIORITY = ("water", "rail", "road", "green")   # 면 분류 우선순위(앞이 이김), 나머지 terrain, 범위 밖 outside (code_map §5.3)
BUILDING_SLOPE_FLAG = 3.0       # m — 발자국 정점 지형 고저차가 이보다 크면 HEIGHT_SRC에 '~slope' (deliverables A.1)
SLOPE_BREAKS_DEG = (5, 10, 15, 21, 27)       # 경사 6단계 (서울시 2013 범례)
ELEV_PRESETS = {"20m": 20.0, "50m": 50.0}    # 표고 단계 간격
FLOOR_BREAKS_DEFAULT = (12, 20)              # 층수 현황도 구간 (C #8)
ALIGN_SAMPLE_STEP = 10.0        # m — 정합 샘플 간격 (지목 도로 경계 ↔ 수치지형도 도로경계)
ALIGN_MAX_DIST = 10.0           # m — 이보다 멀면 상대선 없음
ALIGN_LOW_SAMPLE = 200          # 표본 수 미만이면 '표본 부족'
TOPO_MINOR_KINDS = ("무벽건물", "가건물", "공사중건물")   # 보충(ngii) 행에서 기본 제외하는 종류 — DB ngii_kind 실제 값
QUERY_MARGIN = 20.0             # m — DB 질의 bounds 여유 (범위 bbox ∪ 최대 프레임 bbox + 이 값, code_map §3)
HEIGHT_GRADE_AB_MIN = 0.7       # 높이 등급 A+B 비율이 이 미만이면 height_estimate 경고 (deliverables §C #8, 08높이 §0.5)
COMPASS_DIRECTIONS = ("동", "북동", "북", "북서", "서", "남서", "남", "남동")   # 미보유 도엽 방향 표기 (atan2 45° 단위)
RUN_BAKE_CHUNK = 500            # run이 이 수만큼 베이크할 때마다 progress 콜백(취소 지점). 청크마다 Redraw 1회 — 성수 500 m 7,200개 실측으로 조정
UDT_MANAGED_KEY = "UDT_MANAGED"    # 베이크 객체 UserString — clear_previous 대상 표시
UDT_LOT_KEY = "UDT_LOT_KEY"        # 베이크 객체 UserString — pnus 정렬 sha1 앞 8자리
DOC_ORIGIN_KEYS = ("UDT_ORIGIN_E", "UDT_ORIGIN_N", "UDT_CRS")   # doc.Strings 문서 수준 원점 기록
# CTX::Ref UserString 고정 문자열 — deliverables §A.1 Ref 행. TRANSFORM은 UPIS 5174→5186 변환(META_CRS_LINE과 같은 근거), VDATUM은 수치지형도 표고 기준
REF_TRANSFORM = "EPSG:5189 (UPIS EPSG:5174→5186, 공칭 ±1 m)"
REF_VDATUM = "인천만 평균해수면(수준원점 26.6871 m)"
# 조서·메타(context_report) — deliverables §C 공통 ①~⑤·§E 폴더 규약
RESULT_TABLES_DIRNAME = "tables"
RESULT_SHEETS_DIRNAME = "sheets"
# data_sources.source_id → 메타 역할(lot·building·terrain·upis). prepare가 DataSource 객체를 그대로 넘겨도 역할을 찾는다
SOURCE_ID_ROLES = {"vworld_land_char": "lot", "vworld_building": "building", "ngii_topo_5000": "terrain", "seoul_zoning": "upis"}
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
SHEET_FONT_FAMILY = "Pretendard, 'Noto Sans KR', sans-serif"
SHEET_MARGIN_MM = 8.0            # 범례·카드·메타 박스가 용지 가장자리에서 띄우는 거리
SHEET_FONT_MM = {"title": 6.0, "legend": 3.2, "card": 3.2, "meta": 2.2, "label": 2.4}
SHEET_LEGEND_ROW_MM = 5.0        # 범례 한 줄 높이
SHEET_BOX_WIDTH_MM = {"legend": 70.0, "card": 80.0}
SHEET_SCALE_BAR_M = {1000: 200.0, 3000: 500.0, 5000: 1000.0}   # 축척별 축척 막대 길이
SHEET_LINE_MM = {"parcel": 0.08, "site": 0.7, "extent": 0.4, "overlay": 0.5, "frame": 0.5, "building": 0.06}
SHEET_CLIP_MARGIN_MM = 2.0       # 면 형상을 용지 밖 이 거리에서 잘라 쓴다(도로 필지·시설 결정선 같은 거대 폴리곤이 파일을 키운다 — 성수 #6 2.4 MB 실측)
SHEET_META_BAND_WIDTH_MM = 560.0   # 제목·메타 흰 띠 폭(A1 가로 841의 2/3 — 축척 막대·방위 자리는 비운다)
SHEET_MIN_VERTEX_MM = 0.05       # 종이에서 이보다 가까운 연속 정점은 버린다(1:3000에서 0.15 m — 선굵기 0.08 mm 아래)
SHEET_HEIGHT_SRC_LABELS = {"height": "대장 높이", "grnd_flr": "대장 층수", "topo_flr": "지형도 층수", "hub": "건축HUB", "default": "기본값"}  # #8 카드, A.4 HEIGHT_SRC
SHEET_HATCH = {"landlocked": {"stroke": "#D83A3A", "stroke-width": 0.25, "spacing_mm": 1.5}}   # <pattern id="hatch_<키>"> 45° 사선
# 베이스(모든 시트 공통) — BM_LAYERS K톤을 회색 RGB로 옮긴 값
SHEET_BASE_STYLE = {
    "water": {"fill": "#E2E6EA"}, "green": {"fill": "#EAEFE6"}, "road": {"fill": "#D9D9D6"},
    "building": {"fill": "#E8E8E6", "stroke": "#C6C6C3"}, "parcel": {"stroke": "#B0B0AC"},
    "site": {"stroke": "#DC2828"}, "extent": {"stroke": "#3A3A38", "stroke-dasharray": "3 1.5"},
    "ink": "#3A3A38", "muted": "#8A8A86",
}
# 시트 id → (대상, [(키, 범례 라벨, SVG 스타일 attrs)]). 대상 ∈ target_lot|lot|overlay|building|road|terrain.
# 분류 함수(sheet_svg.SHEETS)가 돌려주는 키가 이 표에 있어야 그려진다. 범례가 데이터로 정해지는 시트(#8 층수·#11 지가·#12 표고)는 [] 두고
# sheet_svg가 SHEET_RAMPS에서 색을 꺼내 만든다.
SHEET_LEGENDS = {
    1: ("target_lot", [("target", "대상지 (K100)", {"fill": "#1E1E1C"})]),   # 위치·범위 — 대상지 검정 채움 + 범위 링(공통 extent 그룹). 광역 인셋은 생략
    2: ("lot", [   # parcels.land_use_status → 2013 도시관리계획 수립지침 토지이용 재분류(단독/공동/주상/상업/공업/나지/도로·하천·공원)
        ("detached", "단독주택", {"fill": "#F6E7A9"}), ("multi", "다세대·연립", {"fill": "#F0C96B"}),
        ("apartment", "아파트", {"fill": "#E09A3C"}), ("residential_etc", "주거 기타", {"fill": "#F9F0CF"}),
        ("mixed", "주상복합", {"fill": "#F2B7A3"}), ("commercial", "상업·업무", {"fill": "#E07070"}),
        ("industrial", "공업", {"fill": "#A9B4D6"}), ("vacant", "나지", {"fill": "#FFFFFF", "stroke": "#8A8A86"}),
        ("road", "도로", {"fill": "#D9D9D6"}), ("water", "하천", {"fill": "#C9D8E8"}), ("park", "공원·녹지", {"fill": "#C5DBB9"}),
        ("etc", "기타·미상", {"fill": "#EFEFEC"}),
    ]),
    3: ("lot", [   # parcels.land_category 28 지목 → 통합 범례
        ("site", "대", {"fill": "#F6E7A9"}), ("factory", "공장용지", {"fill": "#A9B4D6"}), ("road", "도로", {"fill": "#D9D9D6"}),
        ("water", "하천·구거·유지", {"fill": "#C9D8E8"}), ("levee", "제방", {"fill": "#D8CFC0"}), ("farm", "전·답·과수원", {"fill": "#E4ECC8"}),
        ("forest", "임야", {"fill": "#B9CFA8"}), ("park", "공원", {"fill": "#C5DBB9"}), ("school", "학교용지", {"fill": "#F2C7D6"}),
        ("religion", "종교용지", {"fill": "#E8D2EC"}), ("rail", "철도용지", {"fill": "#B9B9B4"}), ("parking", "주차장·주유소", {"fill": "#D0CCDD"}),
        ("public", "공공시설(수도·창고 등)", {"fill": "#CFE1E6"}), ("misc", "잡종지", {"fill": "#EFE6D3"}), ("etc", "기타·미상", {"fill": "#EFEFEC"}),
    ]),
    4: ("lot", [   # parcels.zone_name → 도시·군관리계획 수립지침 도면 색표의 RGB 근사(ACI 변환표는 확인 필요)
        ("r1e", "제1종전용주거", {"fill": "#FFF6C2"}), ("r2e", "제2종전용주거", {"fill": "#FFEFA0"}),
        ("r1", "제1종일반주거", {"fill": "#FFE680"}), ("r2", "제2종일반주거", {"fill": "#FFD966"}), ("r3", "제3종일반주거", {"fill": "#F4B942"}),
        ("rq", "준주거", {"fill": "#F2A08C"}), ("c_center", "중심상업", {"fill": "#D83A3A"}), ("c_general", "일반상업", {"fill": "#E86060"}),
        ("c_near", "근린상업", {"fill": "#F08C8C"}), ("c_dist", "유통상업", {"fill": "#F5B0B0"}),
        ("i_exclusive", "전용공업", {"fill": "#6F7FC2"}), ("i_general", "일반공업", {"fill": "#8F9CD3"}), ("i_quasi", "준공업", {"fill": "#B3BCE2"}),
        ("g_conserve", "보전녹지", {"fill": "#7FB77E"}), ("g_produce", "생산녹지", {"fill": "#A6CF9E"}), ("g_natural", "자연녹지", {"fill": "#CFE6C3"}),
        ("etc", "기타·미지정", {"fill": "#EFEFEC"}),
    ]),
    5: ("overlay", [   # overlays theme district(용도지구)·area(용도구역) — v1은 색 경계선 + 라벨
        ("district", "용도지구", {"fill": "none", "stroke": "#B05A1E", "stroke-width": 0.5}),
        ("area", "용도구역", {"fill": "none", "stroke": "#2F6DB5", "stroke-width": 0.5, "stroke-dasharray": "2 1"}),
    ]),
    6: ("overlay", [   # overlays theme facility(kind) + plan(지구단위계획구역) — 결정선
        ("road", "도로", {"fill": "none", "stroke": "#D83A3A", "stroke-width": 0.4}),
        ("park", "공원·녹지", {"fill": "#C5DBB9", "stroke": "#4E8A3E", "stroke-width": 0.3}),
        ("plaza", "광장·공공공지", {"fill": "#F3E3B8", "stroke": "#B08A2E", "stroke-width": 0.3}),
        ("parking", "주차장", {"fill": "#D0CCDD", "stroke": "#6E5FA0", "stroke-width": 0.3}),
        ("rail", "철도", {"fill": "none", "stroke": "#3A3A38", "stroke-width": 0.5, "stroke-dasharray": "3 1"}),
        ("facility_etc", "기타 시설", {"fill": "none", "stroke": "#7A4EA0", "stroke-width": 0.3}),
        ("plan", "지구단위계획구역", {"fill": "none", "stroke": "#1E5AA8", "stroke-width": 0.7, "stroke-dasharray": "4 1.5"}),
    ]),
    7: ("building", [   # buildings.usability 앞 2자리(VWorld 건축물용도코드 33종) → 대분류
        ("detached", "단독주택", {"fill": "#F6E7A9"}), ("apartment", "공동주택", {"fill": "#E09A3C"}),
        ("neighborhood", "근린생활시설", {"fill": "#E07070"}), ("culture", "문화·집회·종교·판매", {"fill": "#D98CB3"}),
        ("education", "교육연구", {"fill": "#8FB8DE"}), ("welfare", "노유자·의료", {"fill": "#B5D8C8"}),
        ("office", "업무", {"fill": "#7F8FC9"}), ("lodging", "숙박·위락", {"fill": "#C9A0DC"}),
        ("factory", "공장·창고", {"fill": "#A3A3C2"}), ("vehicle", "자동차·위험물", {"fill": "#BFBFBF"}),
        ("etc", "기타", {"fill": "#E5E5E2"}), ("unknown", "용도 미상", {"fill": "#FFFFFF", "stroke": "#8A8A86"}),
    ]),
    8: ("building", []),   # 층수 — 1/2~3/4/5~6/7~b1/b1+1~b2/b2+1+ (b1, b2 = options.floor_breaks). SHEET_RAMPS['floor']
    9: ("building", [   # 사용승인 경과 연수(AGE_BANDS_YEARS) — 철거 건물은 집계 제외(v1 status 전부 active)
        ("age0", "10년 미만", {"fill": "#F6F0D8"}), ("age1", "10~19년", {"fill": "#F1D08C"}),
        ("age2", "20~29년", {"fill": "#E09A3C"}), ("age3", "30년 이상", {"fill": "#B5541E"}),
        ("unknown", "연도 미상", {"fill": "#FFFFFF", "stroke": "#8A8A86"}),
    ]),
    10: ("road", [   # 수치지형도 도로중심선 도로폭(features.value) → 규칙 제9조 폭원 등급 + 맹지(parcels.road_contact)
        ("w_grand", "광로 (40 m 이상)", {"fill": "none", "stroke": "#1E1E1C", "stroke-width": 1.6}),
        ("w_large", "대로 (25~40 m)", {"fill": "none", "stroke": "#1E1E1C", "stroke-width": 1.2}),
        ("w_mid", "중로 (12~25 m)", {"fill": "none", "stroke": "#3A3A38", "stroke-width": 0.8}),
        ("w_small1", "소로1류 (10~12 m)", {"fill": "none", "stroke": "#5A5A58", "stroke-width": 0.5}),
        ("w_small2", "소로2류 (8~10 m)", {"fill": "none", "stroke": "#7A7A78", "stroke-width": 0.35}),
        ("w_small3", "소로3류 (8 m 미만)", {"fill": "none", "stroke": "#9A9A98", "stroke-width": 0.2}),
        ("w_unknown", "폭 미상", {"fill": "none", "stroke": "#9A9A98", "stroke-width": 0.2, "stroke-dasharray": "1 1"}),
        ("landlocked", "맹지", {"fill": "url(#hatch_landlocked)", "stroke": "#D83A3A", "stroke-width": 0.2}),   # 사선 해치(SHEET_HATCH)
    ]),
    11: ("lot", []),   # 공시지가 5분위 — 데이터 분위수로 범례 생성. SHEET_RAMPS['price']
    12: ("terrain", []),   # 표고 — ELEV_PRESETS 간격 밴드. SHEET_RAMPS['elev']
    13: ("terrain", [   # 경사 — SLOPE_BREAKS_DEG 6단계 (서울시 2013 범례)
        ("s0", "0~5°", {"fill": "#F3F7EC"}), ("s1", "5~10°", {"fill": "#D9E8C4"}), ("s2", "10~15°", {"fill": "#F1DC9A"}),
        ("s3", "15~21°", {"fill": "#E7A85C"}), ("s4", "21~27°", {"fill": "#C9663A"}), ("s5", "27° 이상", {"fill": "#8E2F2F"}),
    ]),
}
SHEET_PRICE_QUANTILES = 5
SHEET_RAMPS = {
    "floor": ["#F7F2DC", "#F1DFA8", "#E8C476", "#DB9F4A", "#C97A2C", "#A6531E", "#6E3214"],
    "price": ["#F2F0E6", "#E3D7B8", "#D0B57E", "#B98A4A", "#8F5A26"],
    "elev": ["#F6F7F1", "#E9EFDA", "#D8E4BF", "#C6D9A6", "#B9CB8C", "#C8B97C", "#D2A36A", "#C6835A", "#A8654C", "#7F4A3C"],
}
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
