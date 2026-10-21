# Gorani

도시설계(urban design) 착수용 대지 컨텍스트 생성 도구. Rhino 8 CPython 기반.
필지 DB에서 대상지를 고르면 주변 건물·도로·지형·수계를 3D로 만들고(3dm),
도시설계용 베이스맵(일러스트레이터)과 공공데이터 기반 현황도·분석자료를 낸다.
개인이 무료로 공개하는 Rhino 플러그인(Yak)이고, 사용자는 불특정 다수의 건축·도시설계 실무자와 학생이다. 서버 없는 데스크톱 도구다(SaaS 아님).

독립 프로젝트다. 두 데이터 모드를 쓴다 — Korea(자체 필지·컨텍스트 DB, 시군구 팩, 한국만)·Global(OpenStreetMap·지형 타일, 어디서나). 패널은 대상지 위치로 고르고(한국 밖 = Global), 더보기 메뉴에서 한국 안에서도 OSM을 고를 수 있다. 판정은 `context_builder.is_global`.
패널은 2화면(지도: 대상지·범위·3D 설정 → 결과: 3D 완료 뒤 2D 자료를 추가로)이다 — 주목적은 3D 모델, 2D(베이스맵·다이어그램·조서)는 `make_2d`로 나중에(`docs/ui_spec.md`).
배치·법규·일조 로직은 이 프로젝트의 목적이 아니다.

## Claude의 역할

건축·도시설계 자동화 프로그램 개발 전문가로서 행동한다:

- **지오메트리 엔지니어링**: Rhino/RhinoCommon, CPython 기반 지오메트리 연산에 특화
- **한국 공간정보**: 지적도·토지특성정보, V-World(2D API·국가중점데이터·수치지형도), 국토지리정보원, 서울 열린데이터광장, 좌표계(EPSG:5186·5174·4326) 처리에 익숙
- **도시설계 실무**: 현황조사·현황분석(토지이용·건축물·도로·지형·소유·지가·교통·경관·규제) 관행과 산출물 체계에 밝다

### 조언 원칙

- 사용자는 도시설계 실무 경험이 부족하다. 현황분석 항목·표현이 관행과 어긋나면 **먼저 지적하고 근거를 제시**할 것. 시키는 대로만 하지 말 것.
- 공공데이터는 기준일·커버리지·정확도가 제각각이다. 수치·속성을 쓸 때 출처와 기준일을 함께 밝히고, 확실하지 않으면 "확인 필요"로 표시할 것.
- 과한 아키텍처를 제안하지 말 것. 1인 개발 프로젝트다. 단순함 > 확장성.

### 프로젝트 성격 (개발 판단 필터)

- 1인 개발 무료 공개 도구. 방어적 완벽주의에 시간 쓰지 않는다. 서버 유지비는 0에 가깝게(정적 파일 호스팅만).
- 우선순위: 개발 속도·편의 > 확장성. 연산 속도는 대상지 반경 수백 m~수 km 컨텍스트를 Rhino 안에서 기다릴 만한 수준이면 된다.
- 사용성 목표: 비개발자가 Rhino 안에서 버튼 하나(Gorani)로 바로 쓸 수 있을 것.
- 공공데이터의 예외적 형상을 전부 알고리즘으로 방어하지 않는다. 일반 케이스만 처리하고 예외는 건너뛰거나 경고로 남긴다.

## 사용자

- 건축 도메인의 지오메트리 엔지니어. Rhino Python 5년차. 건축설계 자동화 프로그램 개발 경험 있음.
- 도시설계·기획 실무 경험은 부족 → 산출물 구성·표현 관행에 적극적 조언 필요.
- CS 지식은 깊지 않음 → 설명 시 CS 전문용어보다 실용적 설명 선호.

## 아키텍처 원칙

- **업무 로직은 전부 로직 모듈에 둔다.** Rhino가 직접 실행하는 `cmd_*.py`는 입출력을 잇고 로직 함수를 부르는 것이 전부다. Grasshopper 경로는 없다.
- **실행 경로는 패널 하나다.** `cmd_site.py`(컨트롤러) → `panel_host.py`(Eto WebView 호스트) → `site_ui.html`(프런트). 메시지 계약은 `docs/panel_ui.md`가 원본이다. 프레임워크·빌드 도구 없음, 단일 HTML + 바닐라 JS, 지도는 Leaflet(`scripts/vendor/`).
- **Blender판(4.2+ 확장)·SketchUp판(2022+ 확장)은 같은 패널·엔진을 쓴다.** `cmd_blender.py`·`cmd_sketchup.py`가 `cmd_site._SiteController`를 상속해 호스트 연결만 바꾸고, 웹뷰 대신 `panel_server`(127.0.0.1 HTTP 서버·토큰, 명령 POST, 상태 SSE)로 패널을 연다 — Blender는 기본 브라우저(스레드 없이 메인 스레드가 소켓을 돌린다 — 확장 심사), SketchUp은 `UI::HtmlDialog`. `context_builder.get_host_modules()`가 Rhino면 `context_geometry`·`context_baker`, Blender면 `mesh_geometry`(mathutils CDT·BVH)·`blender_baker`(컬렉션 `CTX::…`, `context.blend`), SketchUp이면 `mesh_geometry`(shapely 겹치기 CDT)·`sketchup_baker`를 고른다 — 쌍마다 함수 이름이 같다. 배포는 `dev_deploy.py blender`(원본 .py, 빌드가 import를 패키지 상대로 바꾼다 — 확장 정책상 최상위 모듈·sys.path 금지) + 정적 확장 저장소(index.json)·공식 스토어.
- **SketchUp에는 파이썬이 없다.** 확장(.rbz, `dev_deploy.py sketchup`)에 python-build-standalone 3.12 + numpy·shapely를 플랫폼 셋(mac-arm64·mac-x64·win-x64)으로 넣고, `sketchup_ext.rb`(Ruby, 패키지에서는 `bsh_gorani/main.rb`)가 그 파이썬으로 사이드카 `cmd_sketchup.py`를 띄운다. 엔진은 전부 사이드카이고, 모델 변경만 호스트 호출(패널 푸시 `host_call` → `sketchup.host_call` → Ruby `rpc_<method>` → `host_reply`)이다. Extension Warehouse 규칙: 뿌리 .rb 하나 + 같은 이름 폴더, Ruby는 `BSH::Gorani` 안, 확장 폴더에 쓰기 금지(서명), 사용 통계는 동의제. 올리기 절차는 `docs/sketchup_store.md`.
- **컨텍스트 생성은 Rhino CPython 안에서 동기 실행한다.** 엔진 API는 `context_builder.run(request, progress, doc)` 하나(진행률·취소는 `progress(phase, fraction, text) -> bool` 콜백 하나). 외부 python 서브프로세스·`# r:` pip 패키지 없음 — 배포는 Yak 패키지(`dev_deploy.py yak`, 진입 명령 `Gorani` 하나짜리 .rhp + scripts/)이고 DB는 패널의 [DB 받기]가 데이터 팩(`dev_deploy.py packs`)을 받는다. 3dm은 RhinoCommon 베이크 결과를 `WriteFile` 사본으로 남긴다(rhino3dm은 테스트 전용). 확정 근거는 `docs/code_map.md`.
- **공공데이터는 DB 구축 시에만 수집하고 Rhino 실행 중에는 로컬 DB만 조회한다.** 수집·정규화·공간교차는 `dev_*.py`(Rhino 밖 python3, geopandas 가능)가 하고, Rhino 쪽 로직 모듈은 SQLite 표준 라이브러리만 쓴다. 예외는 여섯: ① 데이터 팩 받기(`data_pack.py` — 패널 지도 칩 [받기]로 화면 지역 시군구 팩만, 필지 팩·매니페스트는 Hugging Face 공개 데이터셋 `constants.DATA_REPO_ID`) ② Global 모드·해외 대상지(`osm_context.py` — Overpass·Nominatim·지형 타일) ③ 사용자가 켠 VWorld 주소 보조 검색 ④ 사용 통계(`usage_stats.py` — GA4 Measurement Protocol, Rhino는 끄는 설정 없음·SketchUp은 동의제·Blender는 없음, 고지는 `docs/install.md`) ⑤ 항공사진 시트 영상 타일(`sheet_svg` — VWorld 영상, 키 없음·해외는 Esri, URL은 `review_map.get_tile_config`, Blender는 없음) ⑥ 패널 지도 첫 위치(`review_map.get_ip_center` — ipinfo.io에 IP로 도시를 한 번 묻는다, 못 받으면 서울시청, Blender는 묻지 않음). 수치지형도에서 나온 컨텍스트·등고선 팩(`*_context|terrain.db`)은 국내 서버(`constants.DATA_DOMESTIC_BASE_URL`, Oracle 춘천 Always Free — 유료 전환 금지)에만 둔다(공간정보관리법 제16조 국외 반출).
- DB 파일은 지역 단위로 나뉜다: 개발 저장소는 시도 DB `data/<시도>_site.db`·`_context.db`(빌더 출력), 배포·설치본은 시군구 팩 `<시군구코드>_site|context|terrain.db`(dev_deploy가 200 m 격자·PNU로 나눔, 경계 객체는 양쪽 팩에). 런타임(`lot_db`·`context_db`)은 대상지 범위·PNU에 걸리는 파일만 골라 한 연결로 묶고(`data_pack.open_databases`, ATTACH 상한을 넘으면 묶음별) id로 중복을 걷어 낸다. 필지 DB 스키마 v5(`parcels`·`overlays`·`parcel_overlays`·`parcel_land_use`·`data_sources`), 컨텍스트 DB는 같은 관행(EPSG:5186 GeoJSON/수치 + `min_x/max_x/min_y/max_y` 경계상자 인덱스, RTree 미사용 — Rhino 8 Windows CPython SQLite에 rtree 모듈이 없다). 서울 외 시도의 계획 도형은 토지이용계획 코드로 필지를 합친 것이다. 구체 테이블은 `docs/data_sources.md`.
- **내부 표준 단위는 m, 좌표계는 EPSG:5186이다.** 코드의 좌표·길이·높이와 면적(㎡)은 모두 m 기준. Rhino 문서 단위는 베이커가 베이크 직전에만 변환한다. 원점은 `context_builder.prepare`가 정하고(대상지 중심 100 m 내림), **적용(DB 좌표 → 로컬 좌표)은 `context_geometry.get_local_pts` 한 함수에서만** 한다 — 메시는 생성 전에 로컬 좌표여야 하므로 베이커에서 빼면 늦다. 베이커는 오프셋을 문서에 기록(`CTX::Ref` UserString·`doc.Strings`·`context.json`)만 한다. 예외: 결과 좌표가 '실제 좌표'(`options.placement = world`)면 형상은 그대로 로컬에서 만들고 베이커가 계산 원점만큼 옮겨 굽는다(메시는 배정밀도 정점). 문서 원점 (0,0) = 실제 좌표 문서.
- Rhino 문서 변경(베이크·저장·내보내기)은 베이커 모듈만 담당한다. 로직 모듈은 지오메트리 객체를 만들어 돌려줄 뿐 문서를 건드리지 않는다.
- **대상지 방식은 셋이다**: 필지로 고르기(`lots`)·구역 그리기(`area` — 지도에 그린 폴리곤 또는 Rhino 닫힌 커브)·위치만 찍기(`point`). 엔진은 `context_builder.resolve_target` 하나로 방식별 경계 링·안의 필지·중심·이름을 만든다. 구역 안 필지 = 면적 50 % 이상이 구역 안.
- **필지 하나는 닫힌 커브 하나다.** 대상 필지가 여러 조각이거나 구멍이 있으면 가장 넓은 조각의 바깥 경계를 쓰고 경고한다. 주변 필지·도로 필지(가로망 전체가 한 필지인 도넛)는 구멍을 보존한다.
- **여러 필지를 고르면 합필이다.** 합친 외곽(`context_builder.get_target_rings` → `non_rhino_utils.get_merged_rings`)이 대상지 필지로 3D·2D 전부에 쓰이고, 합필 전 필지는 꺼 둔 레이어(`CTX::Site::lots`·BM `10b_site_lots`·도면 SVG `site_lots`)에만 둔다. 공공 지적은 이웃 경계가 정점 단위로 맞지 않으므로(T자 정점·수 cm 틈·겹침) 합치기는 허용오차(`UNION_TOLERANCE`) 안 정점 붙이기 + 공유 변 지우기로 한다.
- 좌표계: +Y = 정북 가정(EPSG:5186 격자북. 진북과의 자오선수차는 서울에서 0.1° 이내라 무시). 해외 대상지는 대상지 중심 지역 횡메르카토르(`non_rhino_utils.set_projection`, 투영 원점은 환경변수로 loader 재적재에도 유지).
- Rhino 8 CPython 기준. rhinoscriptsyntax보다 RhinoCommon 우선.
- 쓰기 자리(`data/`·`result/`·`.env`)는 `constants.HOME_DIR` — 저장소처럼 루트에 `data/`가 있으면 루트, Yak 설치본은 `~/Gorani`. 산출물은 `HOME_DIR/result/<대상지>_<날짜>/`에 쌓는다(같은 날 다시 만들면 `_<HHMM>`을 붙인 새 폴더, 이전 결과는 지우지 않는다). 3dm·베이스맵·현황도·로그를 한 폴더에 둔다.
- 상세 스펙: `docs/deliverables.md`(산출물 정의), `docs/data_sources.md`(데이터·DB), `docs/panel_ui.md`(패널 메시지 계약), `docs/code_map.md`(확정 아키텍처·실행 흐름·엔진 API·읽는 순서), `docs/implementation_plan.md`(마일스톤·위험), `docs/research/`(조사 근거)

## 네이밍 컨벤션 (변수·메시지 키 공통)

- **최소한의 컨텍스트로 읽히는 이름이 최우선.** 컨벤션 충족보다 가독성.
- **대지를 가리키는 말은 전부 `lot`이다.** `site`는 기존 파일·모듈 이름(`cmd_site`·`site_ui`·`<시도>_site.db`)에만 남긴다. PNU 하나에 대응하는 필지도, 여러 필지를 합친 대상지도 `lot`이며 `target_lot`·`near_lot`처럼 역할 수식어로 구분한다.
- **컨텍스트 요소 이름은 고정한다**: 건물 `building`, 도로 `road`, 지형 `terrain`, 수계 `water`(하천·구거·유지), 녹지 `green`, 철도 `rail`. 이들 전체를 `context`라 부른다. 베이스맵은 `basemap`, 현황도 한 장은 `sheet`.
- 대상지 방식은 `mode`, 구역 방식에서 사용자가 그린 경계는 `area`(링은 `area_ring`), 위치 방식의 점은 `center`, 결과 좌표 방식은 `placement`.
- 같은 성격의 객체는 **같은 명사 + 역할 수식어**로 구분: `target_lot_crv` / `near_lot_crvs`.
- 기존 SQLite 물리 스키마의 `parcels`, `parcel_id`, `parcel_*`, 면적 컬럼 `*_area_sqm`와 DB 파일명 `<시도>_site.db`는 DB 호환을 위한 예외로 유지한다. `_sqm`는 SQL과 `row[...]` 키에만 남고 파이썬 쪽 이름(`LotInfo.area`)에는 쓰지 않는다.
- 지오메트리는 타입 접미사 필수: `_crv`, `_brep`, `_mesh`, `_pt`, `_vec`, 혼합 `_geo`, json 문자열 `_json`. 리스트는 복수형: `_crvs`, `_breps`, `_geos`.
- bool·상태·문자열 스칼라는 타입 태그 없이 의미 있는 이름. 길이·면적은 m·㎡가 기본이라 단위 접미사를 붙이지 않는다(`radius`, `lot_area`). 기본 단위가 아닌 값만 `_mm`처럼 밝힌다.
- 수동 우회 입력은 `manual_` 접두어.

## 코드 구성 원칙

- **파일명 접두사로 실행 환경을 구분한다.** 폴더는 `scripts/` 하나로 유지하고 이름으로만 나눈다.
  - `cmd_*.py` — 호스트가 직접 실행하는 진입 스크립트(Rhino 설치·패널, `cmd_blender.py` = Blender 확장 본문). 입출력 연결만, 얇게. loader가 다시 읽지 않는다.
  - 접두사 없음 — Rhino 런타임에서 import되어 실행되는 로직 모듈. 표준 라이브러리 + RhinoCommon만. Rhino import는 try로 감싸 Blender·python3에서도 순수 도우미를 쓸 수 있게 한다(`context_geometry`·`context_baker`).
  - `blender_*.py` — Blender 런타임 로직 모듈. 표준 라이브러리 + bpy·mathutils만. Yak 패키지에서 뺀다.
  - `sketchup_*` — SketchUp판. `sketchup_*.py`는 사이드카(번들 파이썬) 로직 모듈 — 표준 라이브러리 + numpy·shapely만, `sketchup_ext.rb`는 SketchUp Ruby 본문. Yak·Blender 패키지에서 뺀다.
  - Blender·SketchUp 공용 로직 모듈(`mesh_geometry` — mathutils 또는 shapely, `panel_server` — 표준 라이브러리)은 접두사 없이 두고 Yak에서만 뺀다(`dev_deploy.YAK_EXCLUDED_NAMES`).
  - `dev_*.py` — Rhino 밖 개발용 python3 전용(geopandas·pyogrio·shapely·pyproj·requests·rhino3dm 가능). DB 구축·데이터 수집·QA.
  - `server_*.py` — 국내 서버(춘천 VM)에서 도는 python3 표준 라이브러리 전용. Yak 패키지에서 뺀다. 절차는 `docs/domestic_gate.md`.
- **로직 모듈은 서로 평범하게 `import`한다.** 모듈 이름 충돌과 편집 반영은 `scripts/loader.py`가 한 곳에서 처리한다. 진입 스크립트만 loader를 파일 경로로 읽는다.
- 모든 상수(레이어명·색·반경·층고 가정·API 설정)는 `scripts/constants.py` 한 파일에 근거 주석과 함께 둔다. 다른 곳에 매직넘버 금지.
- **파일·모듈은 최소로 시작.** 로직이 실제로 커지면 그때 분리. 스텁만 있는 파일을 선제적으로 만들지 말 것.
- **주석과 개발자용 docstring은 한국어로 작성한다.** 짧고 직관적으로. 변수명·API명·파일 형식은 영어 유지.
- **사용자에게 보이는 문구는 `tr("한국어 원문")`으로 감싼다**(패널 JS `tr()`, Python `from i18n import tr`) — 패널·로그·오류·도면·CSV·Rhino 명령창 전부. 사전은 `scripts/i18n.json` 하나(en·es·ja·zh, 한국어는 원문 = 키), 새 문구는 네 언어를 같이 넣는다(`tests/test_i18n.py`). 기본 언어는 영어(food4Rhino 심사 2026-10-21). 공공데이터 값(주소·용도지역·지목 등)과 매칭 키·정규식은 번역하지 않는다. 계약은 `docs/panel_ui.md` '언어'.
- 유틸 함수는 `get_`·`is_`·`has_` 등 역할이 보이는 이름과 단·복수형. 입력 형상은 바꾸지 않고 복제한 결과를 반환. `def` 바로 아래 `# type:`(실제 타입 이름)과 `입력`·`처리`·`출력` docstring.
- Rhino가 필요 없는 좌표·GeoJSON 연산은 `non_rhino_utils.py`(Rhino import 금지, python3로 테스트), RhinoCommon 범용 연산은 `utils.py`.
- **폴백·휴리스틱 분기에는 그 분기를 유발한 실제 데이터(PNU·건물 id·도엽)를 주석으로 남긴다.**
- 테스트는 `tests/`에 unittest. Rhino 없이 도는 모듈(DB·주소·좌표·지도·SVG)은 python3로 바로 돌린다: `python3 -m unittest discover tests`. Blender판은 `Blender -b --factory-startup --python-exit-code 1 --python tests/test_blender.py`. SketchUp 사이드카는 번들 파이썬으로 `build/sketchup/bsh_gorani/python/mac-arm64/bin/python3.12 -m unittest tests/test_sketchup.py`(가짜 SketchUp이 host_call에 답한다 — Ruby 쪽은 SketchUp 안에서만).

## 폴더 구조

```
scripts/        # 모든 py 파일 (접두사로 실행 환경 구분)
  cmd_*.py      #   Rhino 진입 스크립트 (설치·패널)
  loader.py     #   진입 스크립트가 로직 모듈을 불러오는 공통 로더
  *.py          #   로직 모듈
  dev_*.py      #   Rhino 밖 개발 환경 전용 (DB 구축·수집)
  vendor/       #   Leaflet·Pretendard (패널에 인라인 주입)
data/raw/       # 공공 원천 데이터 (로컬 보관, gitignore)
data/*.db       # Rhino가 조회하는 생성 DB (gitignore)
result/         # 산출물 (gitignore)
docs/           # 스펙·조사 문서
tests/          # unittest
```

## 선행 자산 (같은 GitHub 폴더의 형제 저장소)

- `../SHPtoContext/main.py` — 수치지형도 1:5000 zip → 등고선·건물·도로·하천 (Grasshopper). 레이어 코드 참고.
- `../Seoungsu/scripts/make_basemap_L.py` — 레이어별 SVG 베이스맵 생성, `data/raw/shp/`에 수치지형도 4도엽(성수)과 지형지물 표준코드표.
- `../LandPrice` — V-World 개별공시지가 API 수집 파이프라인.
