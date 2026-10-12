# 조사 문서 색인 (docs/research)

작성일 2026-10-07. 모든 문서는 같은 날 1차 출처(공식 사이트·법령 원문·API 레퍼런스)와 로컬 실측으로 작성·검증했다. 종합 결론은 `../deliverables.md`(산출물)·`../data_sources.md`(데이터·DB)에 있다. 웹 조사와 로컬 실측(00)이 다르면 **00이 우선**하고, **08 보강 조사(같은 날 후속 실측·1차 출처 재확인)가 00~07의 수치·규칙과 다르면 08이 우선**한다(예: 건물 높이 규칙 A.4, 구조물 레이어 코드, 라이선스 표기, 등고선 zip 용량).

| 파일 | 한 줄 요약 | 핵심 결론 |
|---|---|---|
| `00_local_probe.md` | 이 Mac·Rhino 8.35·보유 데이터로 **직접 돌려 확인**한 사실만 | rhino3dm으로 Rhino 밖에서 쓴 3dm(중첩 레이어·Extrusion·Mesh·UserString)을 Rhino가 그대로 읽음. Mac Rhino `.ai` 내보내기는 레이어 보존(사용자가 Illustrator에서 확인). `LT_C_BLDGINFO` 높이 결측 70%·층수 결측 22%, 높이/층수 중앙값 3.25 m; 수치지형도 건물 층수 100% 채움. 필지 DB에 도로 143,132·하천 8,939·구거 6,229필지와 도시계획시설·지구단위 오버레이가 이미 있음. **VWorld 3D DEM 타일은 2019년 폐쇄 — 지형은 수치지형도 등고선으로** |
| `01_platforms_kr.md` | 국내 프롭테크·공공 디지털트윈 13곳이 "대지분석" 명목으로 주는 것 | 국내는 전부 규모검토·AI 가설계·사업성(포화 시장). 레이어 분리 벡터 베이스맵·속성 있는 3D 컨텍스트·필지 단위 현황 주제도를 **파일로 주는 곳은 없음** → 이 툴의 자리. 빌드잇 지적도 DWG(3만 ㎡ 무료)와 Cadmapper(1 km² 무료, 3DM·AI)가 가장 가까운 비교 대상 |
| `02_platforms_intl.md` | 해외 21개 플랫폼(Forma·Giraffe·Cadmapper·TestFit·ArcGIS Urban·Ladybug 등)의 컨텍스트·분석·내보내기·가격 | 해외 표준 컨텍스트 = OSM 건물(층당 3 m 추정)+30 m DEM. 한국 공공데이터는 **높이·층수·용도·연도 속성과 5 m 등고선에서 더 낫다**. 재현 가능: 일조·그림자·가시권·접근성·밀도; 불가: ML 바람·소음지도·탄소·디지털 조닝 룰. Forma Rhino 애드인이 이미 OSM 컨텍스트를 Rhino로 가져오므로 차별점은 '가져오기'가 아니라 속성·정밀도·베이스맵 |
| `03_urban_design_survey_items.md` | 법정 기초조사([별표] 14대항목)·서울시 2013 실태조사 주제도 29종·2017 지구단위 수립기준·LH 공모 요구에서 뽑은 현황도 표준 | 현황도 시트 **P0 16·P1 11·P2 7**(최종 반영은 deliverables §C). 채색 공식 규정은 관리계획 도면작성지침(ACI 색)·기본계획 별첨5(먼셀) 두 곳뿐, 건물 용도·층수·노후도 범례는 공식 표준 없음 → 법정 임계값(1종일반 4층, 경관지구 4·6층, 노후 20/30년, 단독주택 20년 예외)으로 설계. 축척 1/1000~1/5000, 주변 500 m 원칙, 역세권 정의 2종(역 250/500 m vs 승강장 250/350 m) |
| `04a_public_data_base_layers.md` | 필지·건물·도로·지형·수계·행정경계·교통망·도시계획·주소의 원천 인벤토리(URL·형식·좌표계·갱신·라이선스·함정) | 건물 1순위 GIS건물통합정보(dsId=18, EPSG:5186, CC BY); 도로 = 연속수치지형도 중심선(폭·차로수)+실폭도로 또는 도엽판 도로경계 면; 지형 = 수치지형도 등고선·표고점 TIN(공개 DEM은 90 m); 수계 = 연속수치지형도 하천경계·실폭하천. 브이월드 벌크는 로그인 필수, **500 MB 초과분(등고선 전국·도로경계_선)은 라온K(Windows 전용)** → macOS는 도엽 단위. 좌표계 4종(5186/5179/5174/4326) 혼재 |
| `04b_public_data_analysis_layers.md` | 인구·상권·지가·소유·교통·보행·공원·SOC·역사·정비·재해·환경·기상 등 분석 보조 데이터 14분야 인벤토리 | 서울 시트 14종 중 12종은 공식 개방데이터로 가능(일부 로그인·신청). 생활인구는 2026-07-31부터 **250 m 격자**, 상권은 소진공 CSV+`storeListInPnu`, 침수흔적도 연도별 SHP 즉시, 토지소유정보는 컬럼·최신본 미확인. 라이선스 함정: 가로수(4유형)·학교알리미·에어코리아(변경금지). 공백: 지하철 출입구 좌표·자전거도로 선형 |
| `05_vworld_technical.md` | VWorld 2D 데이터 API 158레이어·필드·호출 제한, 데이터마켓 벌크, 수치지형도 도엽 체계, DEM 비교, 3D 사용 조건, WMS/WMTS, 수치지형도 레이어 코드표(로컬 확인) | `size`≤1000+`page`, `geomFilter` BOX 크기 제한 없음, `crs=EPSG:5186` 직접 요청, 일일 한도 비공개(`OVER_REQUEST_LIMIT` 존재). 실응답은 Multi*(파서 규칙). 지형은 API 없음 → 등고선 TIN + Copernicus GLO-30(광역). **별표 1: 1:5,000 이상 등고선·표고값 인터넷 표시 불가** → 온라인 기능 제외 기본값. VWorld 3D(xdworld)는 공개제한·사용 금지. 배포본에 개발자 키 내장 금지(사용자별 키) |
| `06_illustrator_export.md` | 레이어 있는 `.ai`를 자동 생성하는 8가지 경로 비교(Rhino .ai·SVG·SVG+JSX·OCG PDF·DXF·QGIS·legacy AI 직접 생성) | 레이어를 포맷에 담는 중간 포맷은 **DXF와 legacy PostScript AI**뿐; SVG는 그룹, PDF OCG는 Illustrator가 무시. 주력 (b′) SVG→Illustrator JSX(`layers.add`+`createFromFile`), 대안 (d) DXF R2007+`AutoCADFileOptions`, 보조 (a) Rhino 내장 .ai(legacy, 한글·해치·캔버스 리스크). 베이스맵 레이어 19종·K톤·선두께 제안, A0 1:5000 수납 산술 정정 |
| `07_3d_context_generation.md` | Rhino 8 CPython/rhino3dm으로 지형 메시·건물 압출·도로 드레이프·수면 평탄화·원점·대량 처리 기술 조사 + 로컬 벤치마크 | **지오메트리는 Rhino 밖(numpy·shapely·scipy)에서 계산하고 rhino3dm으로 .3dm 작성, 플러그인은 Import만**. 등고선 4 m 리샘플 → scipy Delaunay(12만 점 0.3 s), 면 중심점 분류로 도로·수면·녹지 분리, 수면은 경계 Z 고정. 건물 = Extrusion, 바닥 = 최저 지형 표고, 높이 `height`→층수×3.2→수치지형도 층수(**→ 08 높이 문서로 개정**). 압출 방향은 링 방향(CW/CCW)에 따라 뒤집힘. 원점 = 대상지 중심 이동(5186 좌표 55만은 Rhino 권장 10만 초과). 3만 동+36만 정점 ≈ 40 MB·3~4 s |
| `08_building_height_reliability.md` | `LT_C_BLDGINFO` 높이·층수를 수치지형도 건물(성수 겹침 2.38 km², 6,840동 vs 5,411동)과 교차 검증, 건축HUB·GIS건물통합정보 컬럼 정의서·국제 오픈데이터(Overture·Google·Microsoft·OSM) 판정 | `height`(30 % 채움)는 건축물대장 법정 높이(규칙 별표 '영 §119①5 산정' 원문 확인)라 신뢰, **`grnd_flr`는 아파트에서 51 % 오류**(부속건물 대장이 탑동에 붙음 → `archarea < 발자국×0.5` 플래그). 층수→높이는 `3.2×n` 대신 **용도별 `a+b·n`**(MAE 1.54→1.21 m, 공동주택 2.62→1.35). 아파트·연립은 수치지형도 `층수` 우선. GIS건물통합정보 벌크에 **높이 컬럼 A16 있음**, `usability` 공식 코드표 33 대분류 확정. 건축HUB 1회 100건·일 10,000건, PNU 11번째 자리→`platGbCd`(1→0, 2→1). 서울 전체 보정은 **건축HUB 표제부 벌크 XLSX(786만 행)**. Overture·Google·Microsoft는 한국 높이 없음, OSM은 성수 20 %(ODbL, 검증용만). S-Map 3D·NGII 건물높이공간정보는 공개제한(신청형) — 플러그인 원천 부적합. 실측 스크립트 `scripts/dev_probe_building_height.py` |
| `08_data_currency_update_pipeline.md` | 원천별 새 판 감지·변동분 구조·철거/토지이동 반영·DB 기준일 설계·산출물 표기·경고 임계값·갱신 체크리스트 | 새 판 감지는 브이월드 목록 `fileGbnCd=AL&sidoCd=11`(서울 전체본 1년치 이력, GIS건물 129 MB 매월 9일 기준·게시 0~15일 뒤). **일간 변동분은 쓰지 않고 월간 전체본 교체**(트랜잭션 DELETE/INSERT + `source_files` 표 1개, sha256로 재적재 판정). 철거 = 월간 diff + **건축HUB 폐쇄말소대장·철거멸실관리대장 벌크(월간, 익월 20일)** + 대상지 단위 `getApDemolExtngMgmRgstInfo`·`getSrTitleInfo`. 토지이동은 토지이동이력정보(dsId=13, 서울 33 MB 월간). 건물 `pnu`는 **벌크 A2 원천값 우선**, 공간조인은 결측만. 수치지형도 SHP에 날짜 필드 없음 → `sheets.csv`에 제작연도 기록. 라이선스: 토지특성·토지이용계획은 브이월드 '미지정'·포털 '제한 없음'이라 '공공누리 1유형'으로 적지 않음. 경고: 월간 원천 3개월 경과 **AND 새 판 있음** |
| `08_crs_precision_cadastre_alignment.md` | 5174→5186 변환 경로·정밀도, 지적–지형 정합 오차 실측(성수 4도엽), 등고선+표고점 TIN 수직 정확도 교차검증, 수직기준·GLO-30 | UPIS 5174→5186은 pyproj 기본 경로 **EPSG:5189**(Molodensky-Badekas, 격자 없음)만 쓴다 — 서울 UPIS는 지적선과 중앙값 0.000 m(왕복 일치), towgs84 수동 입력은 +3~4 cm, 2097 오인은 **255 m**. 지적 도로필지 ↔ 지형도 도로경계 정합 **중앙값 1.2 m·p90 3.9 m(n=17,581)**, 동쪽 +0.36 m(보정 안 함). 규정: 1:5,000 절대정확도 95 % 1.5 m·최대 3.0 m → **3.0 m 초과 = 지적불부합 의심 레이어**. TIN은 등고선만이면 면의 54 %가 평삼각형(평지 중앙값 2.0 m) → **표고점 필수**, 단 교량 `A007`·입체교차부 `A009`·인터체인지 `A010` 5 m 버퍼 안 표고점(7.7 %)은 제외(RMSE 3.48→1.54 m; v1이 `A016`을 입체교차부로 오인한 것을 정정). 수직기준 인천만 평균해수면, EGM2008 N≈23.2 m, GLO-30은 DSM·<4 m LE90. 실측 `scripts/dev_probe_alignment.py`·`result/probe_alignment/` |
| `08_nationwide_scale_cost_license.md` | 전국 확장 수량·용량·시간·비용, VWorld·NGII·공공누리·CC BY 원문, 배포 모델 결정 | 전국 필지 DB ≈ 74~91 GB → 배포 불가. **추천 (ii)+(iii) 혼합: 서울 패키지 번들 + 시도 패키지는 사용자 로컬 빌드 + 런타임 VWorld API**. VWorld 2D API는 군 단위까지 전국 커버(8지역 실측)이나 지형 API 없음. **VWorld 이용약관 제19조 '사전 승낙 없는 저장 금지' → API 응답으로 DB 안 만듦(세션 캐시만)**, 벌크는 CC BY·1유형·'제한 없음'이라 번들 가능(제19조 범위는 질의 중). 연속지적도형정보는 포털 4유형 → 번들·납품 금지. 별표 1: 1:5,000 등고선·표고값 온라인 표시 금지, 3차원 좌표 90 m보다 정밀한 3D는 공개제한 → **3dm 웹 업로드 기능 안 만듦**. 등고선 전국 19 zip 중 5개 ≤500 MB(04a '전량 >500 MB' 정정) — 서울 포함 파일은 xlsx 확인 필요. Windows VM 경로 = UTM 무료 + Windows 11 Pro ₩324,600. 건축HUB API 무료·제한 없음. 서면 질의 3건(VWorld·NGII·국가공간정보센터) |

## 읽는 순서 추천

1. 산출물을 알고 싶으면 `../deliverables.md` → 근거가 궁금한 절만 03·06·07, 건물 높이·정합·기준일은 08.
2. 데이터를 받으려면 `../data_sources.md` §0 체크리스트 → 04a·04b·05 → 라이선스·갱신은 08(전국 확장·기준일).
3. 구현 전 `00_local_probe.md`(실측)와 07 §7(선행 코드 개선점), 08 세 실측 스크립트(`scripts/dev_probe_building_height.py`·`probe_alignment.py`·`probe_alignment_followup.py`).

## 참고 자료 (`../reference/`)

- `수치지형도_지형지물_표준코드.csv` — 국토지리정보원 별표 1 코드표(685행 원본, 05 §7에 SHP 실측 대조표)
- `서울_수치지형도_5000_도엽목록.txt` — 서울 139도엽 번호
- `vworld_wms_layers.tsv` — WMS GetCapabilities 182레이어
- `크롬_브이월드_다운로드_프롬프트.md` — 로그인 세션을 유지한 채 도엽·건물 SHP를 받는 브라우저 작업 절차

## 실측 산출물 (`../../scripts/`, `../../result/`)

- `scripts/dev_probe_building_height.py` — 08 건물 높이 실측(6.6 s). 입력 `data/raw/vworld_buildings/merged_5186.json` + `../Seoungsu/data/raw/shp/3770507{2,3,82,83}/N3A_B0010000.shp`
- `scripts/dev_probe_alignment.py`·`probe_alignment_followup.py` → `result/probe_alignment/summary.json`·`followup.json`·`run.log` — 08 정합·TIN 수직 정확도. v1(`A016` 오인) 결과는 `summary_v1_A016_20261007.json`으로 보존
