# 해외 도시설계·사이트 분석 플랫폼의 산출물 조사 (02_platforms_intl)

- 작성일: 2026-10-07 (모든 URL 접근일 동일)
- 목적: UrbanDesignTool(Rhino 8 플러그인)의 산출물(3dm 컨텍스트, 일러스트 베이스맵, 현황도·분석자료)을 정하기 위해, 해외 플랫폼이 "컨텍스트 자동 생성"과 "분석"으로 실제 무엇을 주는지, 어떤 형식으로 내보내는지, 얼마인지 확인
- 출처 표기: **[공식]** 운영사 사이트·문서·블로그·공공데이터 페이지를 직접 열람 / **[언론]** 기사·업계 매체 / **[블로그]** 제3자 글·리뷰 사이트 / **[미열람]** 검색 결과 요약만 확인(직접 열람 실패: 403·JS 렌더링·DNS). 열어서 확인하지 못한 사실은 "확인 필요"로 표기
- 제약: 세션 검색 한도(200회) 소진으로 후반부는 WebFetch·curl만 사용. autodesk.com, suplacemaker.com, food4rhino.com, trustradius.com은 403, modelur.com·www2.modelur.eu는 접속 불가(ECONNREFUSED/DNS). 해당 플랫폼은 대체 호스트(blogs.autodesk.com, placemakerdata.com, docs.urbano.io, forums.sketchup.com)로 보강. 2026-10-07 2차 검증 반영분은 문서 끝 "검증 이력" 참조

---

## 0. 요약

### 결론 한 줄
해외 플랫폼의 "표준 컨텍스트"는 **OSM 건물(높이 없으면 층당 3 m 추정) + 25–30 m 전지구 DEM + OSM 도로·수계 + Mapbox 위성영상**이고, "표준 분석"은 **일조시간·그림자·일사·조망(가시권)·바람·소음·보행 접근성·밀도(FAR/세대수)·탄소**다. 이 중 **일조·그림자·일사·조망·접근성·밀도**는 지오메트리와 EPW만 있으면 한국 공공데이터로 그대로 재현되고, 오히려 **건물 높이·층수(GIS건물통합정보·건축물대장)와 5 m DEM, 시간대별 생활인구**는 해외 표준보다 낫다. 반면 **ML 기반 즉시 바람(rapid wind)·소음지도·디지털화된 조닝 룰(Zoneomics류)·수목 캐노피·VMT 교통모델**은 한국 공개 데이터로는 못 만든다(소음은 측정점 4곳뿐, 조닝은 PDF 조례). 단, **Forma는 공식 Rhino 애드인으로 OSM 기반 지형·주변 건물을 Rhino에 직접 가져오므로**(§2.1, 공식 블로그 2023-11-03·2024-06-03) '컨텍스트를 Rhino로 가져온다'는 것 자체는 차별점이 아니다. 차별점은 한국 공공데이터 **속성**(높이·층수·용도·준공연도·용도지역)과 5 m급 지형이다.

### 조사 대상 21개 중 실존·현황 (2026-10-07 기준)
| 구분 | 플랫폼 | 상태 | 비고 |
|---|---|---|---|
| 초기설계+환경분석 SaaS | Autodesk Forma (Site Design) | 운영 중 | 2026-09-15 Forma Street Design 비공개 베타 발표 [공식] |
| | Digital Blue Foam | 운영 중(Pro는 대기자 명단) | 가격 비공개 [공식] |
| | Giraffe | 운영 중 | Core US$45/월 [공식] |
| | Snaptrude | 운영 중 | Free/US$60/US$100 [공식] |
| | Hypar | 운영 중 | 공간계획 중심, 자동 컨텍스트 없음(확인 범위) [공식] |
| | Modelur (SketchUp) | 운영 중 | modelur.com 접속 불가, 가격 확인 필요 |
| 규모검토·부동산 | TestFit | 운영 중 | Site Solver US$15,000/년~ [공식] |
| | Deepblocks | 운영 중(미국 전용) | DEV/AIM US$99.99–499.99/월 [공식] |
| | Archistar | 운영 중(호주 전용) | A$95–595/월 [공식] |
| | Sidewalk Labs Delve | **종료** | delve.sidewalklabs.com → Google Maps Platform으로 302 리디렉트, `utm_campaign=sunset` [공식-curl] |
| 컨텍스트 생성 전문 | Cadmapper | 운영 중 | 1 km² 무료 [공식] |
| | PlaceMaker (SketchUp/Revit/Web) | 운영 중 | US$109/년 + 크레딧 [공식] |
| | blosm (Blender-OSM) | 운영 중 | 기본 무료·GPL [공식 README]; Premium 19.99(Gumroad 내장 JSON, 통화 미표기·USD 추정) [공식-curl] |
| | BlenderGIS | 운영 중(오픈소스) | Blender ≥2.83 [공식] |
| | VU.CITY | 운영 중(영국·아일랜드 26개 도시) | 15 cm 정밀 모델, 가격 비공개 [공식] |
| 도시계획 GIS | Esri ArcGIS Urban / CityEngine | 운영 중 | Professional Plus 유저타입 필요 여부는 **확인 필요**(trial 페이지의 간접 근거만, Esri KB 403) [미열람]; 가격 US$2,200/4,200/년 [언론] |
| | UrbanFootprint | 운영 중(미국 전용) | 가격 비공개 [공식] |
| | Morphocode Explorer | 운영 중(NYC 베타, 2020~) | explorer.morphocode.com HTTP 200 [공식-curl] |
| Grasshopper 오픈툴 | Ladybug Tools | 운영 중(GPL) | Pollination Rhino 플러그인 US$1,375/년 [공식] |
| | Urbano (Cornell) | 운영 중(v2, 문서 2026-03-28 갱신) | v1 비유지 [공식] |
| | DeCodingSpaces Toolbox | 배포 중(GPLv3), 최신 빌드 2018.01 언급 | 유지보수 여부 확인 필요 [공식] |
| 실존 미확인 | Kinetica | **해당 없음** | 호주 도시계획 컨설팅(2023-07-01 Urbis 합병) 또는 GPU DB 회사만 검색됨. 소프트웨어 플랫폼 아님 [미열람] |

### 해외 플랫폼이 "표준"으로 주는 컨텍스트 레이어
| 레이어 | 표준 출처 | 제공 플랫폼 수(21 중) | 주의 |
|---|---|---|---|
| 건물 footprint + 높이 | OpenStreetMap(`height`/`building:levels`), 없으면 층당 3 m 추정(Forma) | 12+ (Forma, Cadmapper, PlaceMaker, blosm, BlenderGIS, CityEngine, Modelur, Snaptrude, DBF, Urbano, Giraffe, VU.CITY) | OSM 높이 결측이 많아 상용은 지역 공급자(Esri, Nearmap, Microsoft 등) 보강 |
| 지형 DEM | ASTER GDEM 30 m / EU-DEM 25 m / SRTM ~30 m | 10+ | 일본은 Esri 6–13 m 보강(Forma) [미열람]; 한국 커버리지 확인 필요 |
| 도로·보행로·철도 | OSM | 10+ | 중심선+폭(blosm은 폭 기반 커브), 3D 도로는 PlaceMaker만 명시 |
| 수계(하천·호수·해안) | OSM | 8+ | 폴리곤 수준 |
| 식생(숲·개별 수목) | OSM 폴리곤; 개별 수목은 blosm Premium, PlaceMaker, VU.CITY(런던 1,039만 그루) | 4 | 수목 캐노피는 LiDAR 기반 상용 데이터 |
| 필지 | 미국 Regrid류/지자체(TestFit, Snaptrude: 미국·캐나다 일부), 호주 cadastre(Archistar), Forma 지역 공급자 | 6 | 지역 한정 |
| 용도지역·조닝 룰 | Zoneomics(TestFit, Forma), Deepblocks(조례 디지털화), Archistar(호주), ArcGIS Urban(사용자 입력) | 5 | 전부 미국·호주 한정 |
| 위성·항공영상 | Mapbox(Forma, blosm), Nearmap/Google(PlaceMaker, Archistar) | 8+ | |
| 포토리얼 3D 메시 | Google Photorealistic 3D Tiles(blosm, PlaceMaker), 자체 측량(VU.CITY) | 3 | Google은 API 키·과금 필요 |
| 기상 | ERA5/C3S 시간별(Forma; 블로그 원문 표기는 'ERAS C3S'로 ERA5의 오타로 해석), EPW(Ladybug, DBF) | 4 | |
| 환경 위험 | FEMA 홍수·습지·SSURGO 토양(TestFit, 4.8 블로그 기준), 홍수·산불·해수면(UrbanFootprint), 홍수·대기질·소음(VU.CITY 레이어) | 3 | 미국·영국 한정 |

### 해외 플랫폼이 "표준"으로 주는 분석 산출물
| 분석 | 제공 플랫폼 | 산출 형태 | 한국 재현 |
|---|---|---|---|
| 일조시간(sun hours, 지면·입면) | Forma, Giraffe, Archistar, Ladybug, DBF, VU.CITY | 격자 색상맵, 날짜별 | **가능** (지오메트리+태양위치) |
| 그림자(shadow cast: 임계 시간·누적·이산) | ArcGIS Urban, Archistar, DBF, Giraffe, VU.CITY, Ladybug | 시각별·누적 그림자 폴리곤 | **가능** |
| 일사량(solar radiation)·태양광 잠재량 | Forma(solar energy), DBF, Ladybug | 입면·지붕 kWh/m² | **가능** (EPW 필요) |
| 주광 잠재량(daylight potential/autonomy) | Forma, DBF, Honeybee | 입면·실내 지표 | 가능(Radiance) |
| 바람(rapid ML / detailed CFD) | Forma(ML + OpenFOAM 8방향), DBF(Wind Score), Butterfly | 보행자 쾌적도 맵 | ML **불가**, CFD 가능(무거움) |
| 소음(도로·철도) | Forma(rapid/detailed), VU.CITY(레이어) | dB 격자 | **데이터 없음**, 교통량 기반 자체 모델링 필요 |
| 미기후·열쾌적(UTCI) | Forma, Ladybug | 외부공간 쾌적도 맵 | 가능(EPW+CFD/간이) |
| 조망·가시권(view, isovist, ZTV, viewshed) | Giraffe, ArcGIS Urban, VU.CITY, DeCodingSpaces, Ladybug | 가시 영역·시야 폴리곤 | **가능** |
| 보행 접근성(walkscore, isochrone, 15분 도시) | Urbano, UrbanFootprint, Morphocode(5분 pedshed), DBF | 블록별 점수, 등시선 | **가능** (도로망+POI) |
| 가로망 중심성(betweenness/closeness) | DeCodingSpaces, Urbano | 선형 색상맵 | **가능** |
| 밀도·용적 지표(FAR, coverage, 세대수, 주차) | TestFit, Giraffe(Squeeze), Modelur, Deepblocks, ArcGIS Urban, Archistar | 대시보드·Excel | **가능** (기존 DB) |
| 적정성(suitability) 가중 중첩 | ArcGIS Urban | 필지별 점수 | **가능** |
| 교통 VMT·수단분담 / 에너지·물·배출 | UrbanFootprint | 구역별 지표 | **불가**(모델·계수 없음) |
| 탄소(내재·운영·총) | Forma(2026-08-01 미국 허브 우선), Honeybee(운영) | 건물별 tCO₂e | 부분 가능(국내 LCA DB 필요) |
| 토공(cut/fill)·토양 | TestFit | 체적·비용 | 가능(DEM) |
| 사업성 pro forma | TestFit, Deepblocks, Archistar, Delve(종료) | 재무표 | 범위 외 |

### 한국 공공데이터로 재현 가능 / 불가능 (결론)
| 판정 | 항목 | 근거 |
|---|---|---|
| **해외보다 낫게 가능** | 건물 높이·층수·용도·사용승인일 | GIS건물통합정보(Vworld 다운로드·LT_C_BLDGINFO) + 건축HUB 건축물대장 API(`heit`, `grndFlrCnt`, `ugrndFlrCnt`, `mainPurpsCdNm`, 무료) [공식] |
| | 지형 | 국토지리정보원 DEM(data.go.kr: IMG, 무료, 로그인, 해상도 미기재) + 국토정보플랫폼 '공개DEM' 메뉴(map.ngii.go.kr, 해상도·공개제한 미기재) + 보유 수치지형도 1:5000 등고선 [공식]; 해외 baseline은 25–30 m. 5 m 공개 여부는 §7-9 확인 필요 |
| | 필지·용도지역·지구·도시계획시설 | 보유 DB(898,800필지) + Vworld 2D Data API 158개 레이어(`LP_PA_CBND_BUBUN`, `LT_C_UQ111`…) [공식] |
| | 시간대별 인구 | 서울 생활인구(집계구, 매일 갱신, CSV/API, 공공누리 1유형; 2026-07-31부터 250 m 격자 전환) [공식] + SGIS 집계구 통계·경계 GeoJSON [공식] |
| **동등하게 가능** | 도로·수계·식생 폴리곤 | 수치지형도 레이어(보유) + Vworld 교통시설 레이어. 추가 후보: 도로명주소 전자지도(행정안전부, 건물·도로구간 SHP, 전국 무료) — 공식 다운로드 페이지 미열람, 확인 필요(§7-17) |
| | 일조·그림자·일사·조망·가시권·접근성·중심성·밀도·적정성 | 데이터가 아니라 계산. Ladybug(GPL) 또는 자체 구현 |
| | 기상(EPW) | climate.onebuilding.org KOR: Seoul WS·Incheon·Gimpo·Suwon 등 TMYx 2009-2023/2011-2025 무료 [공식] |
| | 위성·항공영상 | Vworld 정사영상·WMTS(이용약관 확인 필요) |
| **부분 가능** | 포토리얼 3D 메시 | Vworld 공간정보 다운로드에 3D 포맷 72건 존재(세부 범위 확인 필요) [공식]; S-Map은 화면 배치용(다운로드 확인 필요); Google 3D Tiles는 유료 API |
| | 침수·재해 | 서울 침수흔적도(2014) 데이터셋은 2024-08-05 서비스 종료 [공식]; 생활안전지도 전국 침수흔적도 SHP는 확인 필요 [미열람] |
| | 바람 CFD·미기후 | Butterfly/OpenFOAM으로 가능하나 Rhino 플러그인 안에서 즉시 결과는 불가 |
| | 탄소 | 운영 에너지는 EPW+간이 계수, 내재탄소는 국내 LCA DB 필요 |
| **불가** | 소음지도 | 서울시 도로교통 소음 측정망은 4개소(시청·신사·신촌·성수), 1시간 등가소음도 [공식]; 격자 소음지도 공개 없음 — 국가소음정보시스템(noiseinfo.or.kr) 메인에 '실시간 소음 지도'(환경소음 실시간/수동·항공기·철도·도로진동)가 있으나 **측정점 기반**이지 격자 소음지도는 아님 [공식]; 지자체 전략소음지도(소음·진동관리법) 공개 여부는 확인 필요(§7-13). TOPIS 교통량·속도로 간이 모델은 가능 |
| | ML 즉시 바람(rapid wind) | 학습 데이터·모델 없음 |
| | 디지털 조닝 룰(세트백·높이·FAR 자동 적용) | 조례·지구단위계획이 PDF. 용도지역별 건폐율·용적률 표는 수작업 테이블로 대체 |
| | 수목 캐노피(개별 수목 높이) | LiDAR 기반 상용 데이터. 서울 가로수 위치 데이터는 확인 필요 |
| | VMT·수단분담·에너지·물 사용 모델 | 미국 전용 계수(UrbanFootprint) |

### UrbanDesignTool에 대한 권고(이 조사의 결론)
1. **컨텍스트 3dm 레이어 세트는 Forma 기준선(건물·지형·도로·수계·필지·영상)을 그대로 쓰되 높이·층수·용도·준공연도 속성을 UserText로 심는다.** 해외는 이 속성이 없어서 못 하는 분석(노후도·층수 분포)이 우리 차별점. Forma가 공식 Rhino 애드인으로 OSM 기반 지형·주변 건물을 Rhino에 직접 가져오는 경쟁 경로가 이미 있으므로(§2.1), '가져오기' 자체가 아니라 속성·정밀도가 차별점이다.
2. **1차 분석은 "데이터 없이 지오메트리만으로 되는 것"만:** 일조시간(하지·동지·춘추분), 누적 그림자(ArcGIS Urban 3모드 참고), 가시권, 표고·경사·향, 밀도(FAR·층수·용도 분포), 보행 등시선. §4의 해외 표준 분석 15종 중 6~7종에 해당한다(개수 비율 약 40–47%; 나머지는 바람·소음·탄소·사업성 등 데이터·모델이 필요한 항목).
3. **2차:** 생활인구 히트맵(해외에 없는 자료), 일사량(EPW), 가로망 중심성, 침수 중첩.
4. **하지 않는다:** rapid wind, 소음, 탄소, pro forma, 자동 배치.
5. **내보내기 표준:** 3dm(레이어·속성) + AI/SVG 베이스맵 + GeoJSON(Giraffe가 Rhino 교환 형식으로 채택; VU.CITY 신플랫폼은 GeoJSON을 '데이터 가져오기' 형식으로만 명시) + CSV(지표). glTF/OBJ는 후순위.

---

## 1. 조사 범위와 방법
- 대상: 과제에 열거된 21개. "실존 확인된 것만"이라는 조건에 따라 Kinetica는 제외(§2.F).
- 각 플랫폼마다 (a) 컨텍스트 자동 생성 범위와 출처, (b) 분석 산출물, (c) 내보내기 형식, (d) 가격을 공식 페이지에서 확인. 공식 페이지가 막힌 경우 운영사 블로그·문서·대체 도메인 → 언론 → 리뷰 사이트 순으로 보강하고 등급을 표기.
- 가격은 2026-10-07 기준 공개 리스트 가격. 세금·지역 차이 미반영.

---

## 2. 플랫폼별 상세

### A. 초기설계 + 환경분석 SaaS

#### 2.1 Autodesk Forma (Forma Site Design)
- 포지션: 클라우드 초기설계. 사이트를 열면 컨텍스트가 자동 생성되고 그 위에 매스를 그리며 분석.
- **컨텍스트 자동 생성** [공식 블로그 2023-12-11]:
  - 제공 항목: 지형, 건물 지오메트리, 도로, 필지 경계(지역 한정), 위성영상.
  - 기준선 출처(지역 데이터 없을 때): 건물 footprint·도로 = OpenStreetMap, 지형(유럽) = EU-DEM 25 m, 지형(전지구) = ASTER GDEM 30 m, 지도 텍스처·위성 = Mapbox, 기상 = ERA5(C3S) 시간별(블로그 원문 표기는 'ERAS C3S' — ERA5의 오타로 해석). 수계·식생은 이 글에 언급 없음.
  - 건물 높이: OSM에 높이 없으면 **층당 3 m, 최소 1층으로 추정**.
  - 지역 데이터 커버리지는 Data Coverage App(app.autodeskforma.eu/data-provider-map)에서 확인(JS 앱이라 내용 미열람). 일본은 Esri 지형 6–13 m 제공 [미열람]. **한국 커버리지 확인 필요.**
  - 미국은 Zoneomics 제휴로 조닝 반응형 건축 외피 생성(2024-08-19) [공식 블로그].
- **분석 산출물**:
  - 공식 블로그(2026-07-17)가 열거한 분석군: 일조(sun exposure), 주광 잠재량, 바람, 소음, 미기후, 태양에너지, 탄소 [공식].
  - 일조시간: 지면·입면 격자, 임의 날짜, 수 분 내 결과 [공식 블로그 2026-02-09].
  - 바람: **rapid = ML 즉시 결과(풍향·보행자 쾌적도), detailed = 클라우드 OpenFOAM 8방향 CFD** [공식 블로그 2026-07-03].
  - 총탄소(내재+운영): 건물 유형·외벽 재료·창면적비 입력, **2026-08-01 미국 허브 우선 출시**, 타 지역 2026년 내 확대 예정 [공식 블로그 2026-07-17].
  - 소음(도로·철도, rapid/detailed), 미기후(열쾌적), 태양에너지(연간 잠재량·패널 배치), 주광 잠재량의 상세 설명은 제품 페이지 검색 스니펫에서만 확인 [미열람, autodesk.com 403].
  - 생성 도구: Site Automation(배치안 자동 생성·순위), Line Buildings [미열람].
- **내보내기**: Send to Revit(Forma Add-in: 지형→Toposolid, 건물→Generic Model 그룹, 사이트 경계→Model Line, UTM 좌표) [공식 블로그]; IFC 4.3로 Docs에 내보내기(컨텍스트 건물 포함) [블로그 cadforum.cz 2025-02-28]; 제안안 OBJ zip 내보내기 [미열람, 커뮤니티 포럼 403]. **Rhino 애드인 있음** [공식 블로그]: "Forma's integration with Rhino and Dynamo"(2023-11-03)와 "How to connect a Forma project to Rhino"(2024-06-03)가 Forma↔Rhino **양방향 동기화**를 명시 — Forma의 지형·주변 건물 데이터를 Rhino로 가져오고('bringing your Forma terrain and surrounding building data back into Rhino'), Rhino 매스를 Forma로 보내 분석. 즉 Forma는 OSM 기반 컨텍스트를 Rhino에 직접 넣는 경쟁 경로다. Grasshopper 전용 애드인은 두 글에 언급 없음(확인 필요).
- **가격**: 단독 US$1,460/년 [블로그 TrustRadius 스니펫, 확인 필요]; AEC Collection에 Forma Site Design 포함(컬렉션 US$3,375–3,675/년) [블로그 스니펫, 확인 필요]. autodesk.com 가격 페이지는 403.
- **신규**: Forma Street Design — 2026-09-15 Autodesk University에서 발표, 비공개 베타 대기자 명단. 가로 선형·곡선반경·차로폭·교차로를 파라메트릭 생성, 평면·단면 동시, Vehicle Tracking 주행궤적, GIS 레이어·지형·인접 건물·필지 가져오기, 승인 후 Civil 3D로 이관 [공식 블로그].

#### 2.2 Digital Blue Foam (DBF)
- 포지션: 웹 기반 초기 개발안 탐색·평가(싱가포르).
- 컨텍스트: 주변 건물·지형·기상을 포함한 사이트 설정, GIS 가져오기 [공식 docs]. 출처(OSM 등) 명시 없음 — 확인 필요.
- 분석: Daylight Autonomy, 그림자 [공식 docs]; 출시 당시 목록 — Daylight Autonomy Score, Solar Radiation Simulation, Instant Shadow Study, Wind Score, Sun Path Animation, 근린 점수(15분 도시) [언론 AEC Magazine 2022-02-02].
- 내보내기: 3D 모델·2D CAD [공식 docs]; DBF Hub 플러그인 Revit·Archicad [공식 docs]; Rhino·SketchUp 연동 [언론].
- 가격: Academic/Pro는 대기자 명단(출시 시 7일 전체 액세스), Enterprise/Gov(1,000명+)는 사용량 기반 맞춤 [공식]. Hikari라는 별도 per-seat SaaS 존재 [공식].

#### 2.3 Giraffe (호주)
- 포지션: 브라우저 GIS + 매싱 + 지표 계산, 앱 생태계.
- 컨텍스트: 데이터 라이브러리 "수천 개 레이어 — 조닝·필지·등고선 등, 수백 개 도시"; Esri 맵서버 연결, 사용자 공간데이터 업로드 [공식]. 건물 3D 출처는 명시 없음 — 확인 필요.
- 분석: 그림자, 일조, 조망, 수율(yield), 사이트 면적·FAR [공식]. 번들 앱 4종: Paper(라이브 모델에서 도면 세트), Squeeze(세대수·사업성), Spatial Toolkit(포트폴리오 스크리닝), Trees(식재·가로경관) [공식].
- 내보내기: STL, OBJ, DXF, IFC, GeoJSON [공식]; Rhino는 **Projected GeoJSON + 제공 Python 스크립트(`giraffeToRhino_projected`)로 가져오기** 권장 [공식 help]; .glb, .csv/.xls, jpg/pdf [미열람].
- 가격: Core US$45/월(무약정), Teams US$1,500/유저/년, Enterprise 맞춤. 신용카드 없이 탐색 가능 [공식].

#### 2.4 Snaptrude
- 포지션: 웹 BIM(스케치→BIM→Revit).
- 컨텍스트: 주소·위경도로 사이트 가져오기 → 선택 항목은 **Elevations(지형·표고), Buildings(주변 건물), Satellite view(위성영상)** + Property parcels(필지: 미국·미국령·캐나다 일부, 최대 10필지, 축척 200 m 이하에서만 표시) [공식 help]. **도로는 help 문서 선택 항목에 없음**(전문에 'road' 0건 — 생성 여부 확인 필요). 출처 미명시. 등고 사이트는 Toposolid로 가져와 절성토 자동 계산 [미열람].
- 분석: 기후 분석(사이트 가져오기 목적에 언급) [공식 help]. 상세 목록 없음.
- 내보내기: Revit(벽·슬래브·계단·문창 재생성), ArchiCAD [공식].
- 가격: Free(3 프로젝트), Individual US$60/월, Organization US$100/월(연간), Enterprise 맞춤 [공식 pricing 페이지].

#### 2.5 Hypar
- 포지션: 공간계획(test fit) 생성·Revit 핸드오프. **자동 사이트 컨텍스트 기능은 문서에서 확인되지 않음**(DXF/DWG/PDF/이미지 가져오기만).
- 내보내기: Revit·Rhino 직접, DXF/DWG(유료), PDF/PNG [공식 docs]; IFC/JSON/glTF [미열람].
- 가격: Personal 무료(소유 프로젝트 3개, 업무 사용 불가), Professional US$100/월 또는 US$1,000/년, Studio 20석+ 인보이스 [공식 docs].

#### 2.6 Modelur (SketchUp)
- 포지션: SketchUp 파라메트릭 매싱 + 조닝 검사 + 지표.
- 컨텍스트: OSM 3D 건물·2D footprint 원클릭 가져오기 [미열람], OSM 통합 무료, 지형 위 배치, GIS(shapefile) 가져오기, GeoJSON 입출력 [미열람], Excel LiveSync(Windows) [공식 포럼 2022].
- 분석: FAR·주차·세대수 자동 계산, Interactive 3D Zoning(위반 경고) [공식 포럼].
- 가격: 무료 플랜 한도 = 파라메트릭 건물 10동, 블록 1개, 용도 4개, OSM 타일 1개; 유료는 월·분기·연 구독(금액 미공개) [공식 포럼]. Modelur 2026 = SketchUp 2023–2026, Mac/Win [미열람]. **modelur.com 접속 불가로 현재 가격 확인 필요.**

### B. 규모검토·부동산 피저빌리티

#### 2.7 TestFit (미국)
- 컨텍스트(미국 한정): 필지(APN 선택 또는 경계 수동), 조닝(허용용도·FAR·건폐·세트백·높이), 2D 지형 + 3D 지형, 홍수, 습지(자동 이격), 토양(종류·지하수위·암반심도·경사), 발전소 위치, 제외구역. **출처명 주의**: Site Solver 페이지는 'ESRI integration'·'built-in zoning data'로만 표기 [공식 Site Solver]; Zoneomics·FEMA·SSURGO 등 구체 데이터 출처명은 TestFit 4.8 블로그에만 있음 [공식 블로그 4.8].
- 분석: 세대수·주차대수, pro forma(토지·직접·간접비), 절성토 체적·토공비, 물량산출, KPI(FAR·효율·yield on cost·건폐·높이), 개략 공사비 [공식].
- 내보내기: DXF, SKP, glTF, CSV, PDF 보고서, Revit 애드인, TT Core Studio [공식].
- 가격 [공식 pricing]: Parking Solver US$195/월; Site Solver US$15,000/년~; Site Solver Portfolio US$20,000/년~. 애드온: Site Intelligence +US$150/월(조닝·환경·3D 지형), Pro Forma +US$170/월, MCP 연결 +US$100/월.

#### 2.8 Deepblocks (미국)
- 컨텍스트: 필지 지오메트리, 조닝 규제·오버레이·주법(조례 원문 링크), 기존 건물 면적은 공식 기록 없으면 footprint×높이로 계산. 도시는 요청 후 0–3 영업일 내 구축 [공식].
- 분석: DEV(즉시 3D 매싱·피저빌리티·재무모델), AIM(사이트 선정); 조닝 리포트(허용용도·개발기준·용량) [공식].
- 내보내기: 확인 필요(공식 페이지 미기재).
- 가격: DEV·AIM 각 US$99.99–499.99/월(도시 수 5/16/30, 3/12/24) [공식].

#### 2.9 Archistar (호주)
- 컨텍스트: 연방·주·지방 정부 문서에서 계획 규칙 집계; Domain·CoreLogic·BCI·Cordell·Nearmap 제휴; 유료 플랜에 3D 건물·지형·Nearmap 고해상 항공영상 [공식 FAQ·pricing]. 호주 8개 주·준주만 [공식 FAQ].
- 분석: 일조 접근·지면 그림자·오버섀도잉, 플로어플레이트·세대 믹스, 환경 위험·등고선·시세 [공식]; 생성형 3D 설계는 무료 포함 전 등급.
- 내보내기: pricing 비교표의 'Export designs to CAD file' 행은 Free ×, Basic ○, Professional ○(아이콘 minus-grey / check-navy 순서로 확인); National은 비교표에 없고 카드에 'Everything in BASIC, plus'로 표기 → **CAD 내보내기는 Basic 이상에서 가능, Free만 불가** [공식 pricing].
- 가격(세금 포함, 무약정) [공식]: Free; Basic A$95/월(연간 A$79.17/월, 2,000 m² 미만·1개 주); Professional A$345/월(A$287.50); National A$595/월(A$495.83, 전국).

#### 2.10 Sidewalk Labs Delve — 종료
- 현황: `curl -I https://delve.sidewalklabs.com/` → **302 → mapsplatform.google.com/maps-products/earth/capabilities/?utm_source=delve&utm_medium=product&utm_campaign=sunset** [공식-curl]. 랜딩 페이지는 Google Earth 기능(2,500+ 도시 포토리얼 3D, "generative design to identify optimal sites", 태양광 설계 평가)을 소개하며 Delve를 언급하지 않음 [공식].
- 경위: 2022년 Google에 흡수, 독립 제품 종료 [블로그 datadrivenaec, aecplustech]. 당시 산출물: 수천 개 시나리오 생성, 일조·오픈스페이스·보행성·세대수·조닝 적합성·수익률 평가 [블로그].

### C. 컨텍스트 생성 전문

#### 2.11 Cadmapper
- 출처: OpenStreetMap, NASA, USGS [공식]. 건물 높이·지형은 "많은 지역에서" 제공(출처·정확도 미기재) [공식].
- 레이어: 건물, 지형, 도로 3등급 폴리라인, 수계; 전 도시 도로망 DXF는 200+ 대도시권 무료·계정 불필요 [공식].
- 형식: AutoCAD, SketchUp 8+, Rhinoceros 5+, Adobe Illustrator [공식]; OBJ/FBX/STL [블로그].
- 가격: **1 km²까지 무료(모든 데이터·형식)**, 100 km²까지 "소액"(금액 비공개, 학술 메일 할인) [공식]; 2018년 보도 기준 6 km² US$9, 100 km² 약 US$63 [언론 Fabbaloo, 현재가 확인 필요].
- 분석: 없음.

#### 2.12 PlaceMaker (SketchUp / Revit / Web)
- 컨텍스트 [공식 placemakerdata.com]: OSM 3D 건물·도로·보행로·철도·수계·수목(구독자 무료), 항공영상·지형·3D 메시·포인트클라우드(크레딧 할인), Google Earth·Nearmap 영상은 개인 API 키로 무료(EEA 제외). Google Earth 3D 메시는 SketchUp Pro 2022+ 및 구독 필요 [미열람 일부].
- 가격 [공식]: 구독 US$109/년(OSM 3D 가져오기 무료); 종량제 크레딧 US$20/100크레딧부터(shop 페이지), 만료 없음. **크레딧 단가는 운영사 페이지 간 불일치(확인 필요)**: credits 페이지는 'nominal value of $0.15 USD each'로 명목가치 US$0.15/크레딧을 명시하나, shop 페이지의 최소 팩은 US$20/100크레딧 = US$0.20/크레딧 환산(검증 세션은 shop 페이지가 US$0.20을 표기한다고 보고; 본 세션 curl에서는 '$20 for 100 credits' 문구만 검출). 명목가치와 구매단가를 구분해 확인할 것. ¼마일×¼마일 예시: 브라이언트파크 76크레딧(종량) vs 9(구독) 등.
- 지원: SketchUp 2021.1+, Revit 2022+, 웹 [공식].

#### 2.13 blosm (구 Blender-OSM)
- 컨텍스트 [공식 GitHub README]: OSM 건물(높이·층수 반영), 도로·보행로·철도(폭 있는 커브), 수계·숲·식생 폴리곤, 지형 약 30 m(SRTM), GPX. Premium [공식 wiki Premium-Version — 기능만 기재, 가격·30 m 지형 언급 없음]: 텍스처 건물·UV, 숲·단목 3D, 위성(ArcGIS·Mapbox·Google URL)·웹맵(OSM Mapnik·Mapbox) 지형 투영, Google 3D Tiles 텍스처 베이킹. **Google 3D Tiles는 Maps Tiles API 키·결제계정 필수.**
- 가격: 기본 무료(기부 선택)·GPL [공식 README]; Premium은 Gumroad 페이지 내장 JSON `"price":19.99`(통화 미표기, USD 추정) [공식-curl].

#### 2.14 BlenderGIS
- 기능 [공식 GitHub]: shapefile·OSM XML 가져오기, GeoTIFF DEM·래스터, Overpass API OSM, SRTM, OpenTopography(2022년부터 API 키), XYZ 베이스맵, Delaunay 지형, 지오레퍼런스 카메라·래스터 렌더. Blender ≥2.83, 9.4k stars, 513 커밋. 라이선스 표기는 README 요약에 없음 — 확인 필요.

#### 2.15 VU.CITY (영국·아일랜드)
- 컨텍스트 [공식]: 26개 도시, **15 cm 정밀도**, 3,000 km² 이상; 런던 1,730.56 km², 수목 10,390,300그루(높이·캐노피), 데이터 레이어 290종(계획 인허가, 대기질·홍수·소음, TfL 도로, 유산·보전지역, 녹지·생물다양성, 소득·박탈·인구밀도).
- 분석 [공식]: 일조·주광 초기 영향, 그림자 오버캐스팅, ZTV(이론적 가시지대), 뷰셰드·카메라 뷰 연구, 미기후(런던 페이지).
- **가져오기** [공식 pricing — 표 항목명이 'Model import formats'·'Data import formats'로, 내보내기가 아니라 가져오기 형식임]: Legacy(Unity) = 모델 .FBX·.OBJ, 데이터 가져오기 형식 N/A(데이터 유형 점·선·면); Early Access(Unreal) = 모델 .glTF/.GLB(.FBX·.OBJ 'coming soon'), 데이터 GEOJSON·.glTF/.GLB(유형 점·선·면·메시·래스터·BIM·시계열). Revit·Rhino·SketchUp·3ds Max 모델 가져오기. **내보내기 형식은 pricing 페이지에 미기재 — 확인 필요**.
- 가격: Basic(1개 도시·3명)/Pro(1개 도시·플로팅)/Enterprise(전 도시). "2026년 신규 플랫폼 도입으로 가격 구조 변경 중, 문의" — 금액 비공개 [공식].

### D. 도시계획 GIS

#### 2.16 Esri ArcGIS Urban / CityEngine
- ArcGIS Urban [공식 overview·doc]: 필지·조닝·3D 건물·베이스맵 입력; 조닝·토지이용 계획, 시나리오, 용량 지표; 시나리오 비교 보고서를 **Microsoft Excel 워크북으로 다운로드** [공식 doc 'Create a scenario comparison report']; 적정성 분석(가중치); **그림자 분석 3모드 — areas above threshold(임계시간 초과 영역) / total shadow duration(누적, continuous·hourly) / discrete shadows(이산), 시간대·색·투명도 설정** [공식 doc 'Work with shadow cast']; 가시성·단면·표고 프로파일. 내보내기는 **시나리오·도시 web scene 생성**만 doc에서 확인 [공식 doc 'Work with scenario web scenes'] — **CityEngine·SLPK 내보내기는 doc 사이트맵 86페이지 전수 grep에서 미확인(확인 필요)**. **Professional Plus 유저타입 필요 여부는 확인 필요** [미열람]: overview 페이지는 'This app is included with ArcGIS user types'라고만 쓰고 유저타입명이 없으며, user types overview 페이지에도 Urban 언급 없음; trial 페이지의 'The trial includes one Professional Plus and three Viewer user types'가 유일한 간접 근거. Esri KB 000035058은 403.
- CityEngine [공식 doc]: Get Map Data로 OSM 건물 footprint + DTM 가져오기; 내보내기 ABC·DAE·FBX·OBJ·glTF·USD·DWG·VOB·Datasmith·KMZ/KML·FileGDB·SLPK·MSPK·3VR·**IFC(buildingSMART)**, 가로망은 SHP·GDB·DXF. CityEngine 2026은 2026-07-13 출시(Python 3 API 정식, Street Designer 개선) [언론 CG Channel].
- 가격: 2026년 기준 ArcGIS Professional US$2,200/년, Professional Plus US$4,200/년 구독 전용, 영구 라이선스 판매 2025-06 종료 [언론 CG Channel; Esri 구매 페이지에는 금액 미표시]. Urban이 Professional Plus에 포함된 시점(2025-06 업데이트)은 Esri KB 403으로 [미열람].

#### 2.17 UrbanFootprint (미국)
- 데이터 [공식]: 미국 전역 1억 6천만 필지, Built Environment / People & Vulnerabilities / Climate & Hazards 3축, 수천 개 데이터셋 통합.
- 분석 모듈 [공식 블로그]: Walk Accessibility, Transit Accessibility, Transportation(VMT·수단분담), Energy Use, Water Use, Emissions, Household Costs, Risk & Resilience(홍수·산불·해수면), Land Consumption, Conservation(캘리포니아).
- 내보내기: Analyst·Explorer 앱, 직접 데이터 피드 [공식]. 가격 비공개(데모 요청) [공식].

#### 2.18 Morphocode Explorer
- 브라우저 도구. 5분 보행권(pedshed)을 끌면 토지이용·개발강도·대중교통·인구(Census)·도시형태 지표가 실시간 갱신. NYC 베타(2020 출시), 북미·유럽·호주 확장 "예정" [공식]. 2026-10-07 HTTP 200으로 서비스 중 [공식-curl]. 가격 미표시.

### E. Grasshopper 오픈툴

#### 2.19 Ladybug Tools
- 구성 [공식]: Ladybug(태양경로·풍배도·일사·일조시간·그림자·조망), Honeybee(Radiance·Daysim·EnergyPlus·OpenStudio 주광·에너지·열쾌적), Butterfly(OpenFOAM CFD), Dragonfly(도시 규모, Urban Weather Generator). 입력은 EPW. GPLv3.
- 상용(Pollination) [공식 pricing]: Grasshopper 플러그인 US$0; Rhino 플러그인 US$1,375/년(US$125/월); Revit US$2,750/년; 번들 US$3,575/년; 클라우드 연산 별도.

#### 2.20 Urbano (Cornell ESL)
- v1 비유지, **v2 유지 중**(문서 갱신 2026-03-28) [공식 docs]. 가져오기: OSM·Shapefile·GeoJSON → 건물·가로·지형·녹지·대중교통; 가로망 라우팅; Walkscore(블록별), 어메니티 점수, betweenness 중심성 [공식 docs]. 배포는 Rhino 패키지 매니저(urbano.io Download → rhinopackages) [공식]. 라이선스·비용 미기재 — 확인 필요(food4rhino 403).

#### 2.21 DeCodingSpaces Toolbox (CPlan, Bauhaus-Weimar/ETH/AIT/FCL)
- GPLv3 무료 Grasshopper [공식]. 생성: 가로망 합성·필지 분할·건물 생성(WIP); 분석: 가로망 중심성(betweenness·closeness·gravity, 반경별), 2D/3D 아이소비스트, 수문; Mapbox·OSM 연동. 사이트가 언급하는 최신 빌드는 2018.01 — 유지보수 상태 확인 필요.

### F. 실존 미확인
- **Kinetica**: "Kinetica Studio"(호주 도시계획 컨설팅, 2023-07-01 Urbis 합병)와 kinetica.com(GPU 분석 DB)만 검색됨. 도시설계 소프트웨어 플랫폼으로 확인되지 않아 제외 [미열람].

---

## 3. 횡단 비교

### 3.1 컨텍스트 자동 생성 범위 (○ 제공, △ 제한·유료 옵션, × 없음, ? 확인 필요)
| 플랫폼 | 건물 | 높이 출처 | 지형 | 도로 | 수계 | 식생 | 필지 | 조닝 | 영상 |
|---|---|---|---|---|---|---|---|---|---|
| Forma | ○ | OSM→3 m/층 추정, 지역 공급자 | ○ 25–30 m(+지역) | ○ OSM | ? | ? | △ 지역 | △ Zoneomics(미) | ○ Mapbox |
| Cadmapper | ○ | OSM(있을 때) | △ | ○ 3등급 | ○ | × | × | × | × |
| PlaceMaker | ○ | OSM 3D·Google 메시 | ○ | ○ 3D | ○ | ○ | × | × | ○ |
| blosm | ○ | OSM height/levels | ○ SRTM 30 m | ○ 폭 | ○ | ○(Premium 3D) | × | × | △ Premium |
| BlenderGIS | △ OSM | OSM | ○ SRTM/GeoTIFF | ○ | ○ | △ | △ shp | × | ○ XYZ |
| CityEngine | ○ | OSM | ○ DTM | ○ | ○ | △ | △ | 사용자 | ○ AGOL |
| ArcGIS Urban | ○ 입력 | 사용자/Esri | ○ | ○ | ○ | △ | ○ 입력 | ○ 입력 | ○ |
| TestFit | △ 3D 컨텍스트 | ? | ○ 2D+3D | ○ | △ 홍수·습지 | × | ○ 미국 | ○ Zoneomics | ○ |
| Giraffe | ? | ? | ○ 등고 | ○ | ○ | ○ Trees 앱 | ○ 라이브러리 | ○ 라이브러리 | ○ |
| Snaptrude | ○ | ? | ○ | ? (help 항목에 없음) | ? | × | △ 미·캐 | × | ○ |
| Archistar | ○ 유료 | ? | ○ | ? | ? | × | ○ 호주 | ○ 호주 | ○ Nearmap |
| Deepblocks | △ 면적 | footprint×높이 | × | × | × | × | ○ 미국 | ○ 조례 | × |
| VU.CITY | ○ 15 cm | 자체 측량 | ○ | ○ | ○ | ○ 개별수목 | △ | ○ 정책 레이어 | ○ |
| Modelur | ○ OSM | OSM | ○ 배치 | ? | ? | × | △ shp | ○ 사용자 | × |
| DBF | ○ | ? | ○ | ? | ? | ? | ? | × | ? |
| Urbano | ○ OSM | OSM | ○ | ○ | △ 녹지 | △ | × | × | × |
| Ladybug | × | — | × | × | × | × | × | × | × |
| DeCodingSpaces | △ 생성 | — | × | ○ 생성·분석 | × | × | △ 생성 | × | × |
| UrbanFootprint | ○ 속성 | 기록 | × | ○ | ○ 위험 | ○ 보전 | ○ 1.6억 | ○ | × |
| Hypar | × | — | × | × | × | × | × | × | × |
| Morphocode | ○ 속성 | 기록 | × | ○ | × | × | ○ | ○ 용도 | × |

### 3.2 내보내기 형식
| 플랫폼 | Rhino 직결 | 벡터/CAD | 3D 교환 | GIS | 표·보고서 |
|---|---|---|---|---|---|
| Forma | **○ Rhino 애드인(양방향 동기화, 지형·주변 건물→Rhino)** [공식 블로그]; Grasshopper 전용은 확인 필요 | — | OBJ, IFC 4.3, Revit 애드인 | — | — |
| Cadmapper | 3DM | DXF/DWG, AI, SKP | (OBJ/FBX/STL [블로그]) | — | — |
| PlaceMaker | × (SketchUp/Revit 내) | — | — | — | — |
| blosm / BlenderGIS | × (Blender 내) | — | Blender 경유 전 형식 | shp/GeoTIFF 입력 | — |
| CityEngine | OBJ/DAE/FBX 경유 | DWG, DXF(가로) | ABC·DAE·FBX·OBJ·glTF·USD·Datasmith·IFC | KML/KMZ, FileGDB, SLPK | — |
| ArcGIS Urban | × | — | web scene(SLPK·CityEngine 내보내기는 확인 필요) | — | Excel [공식 doc] |
| TestFit | DXF/SKP 경유 | DXF, SKP | glTF, Revit 애드인 | — | CSV, PDF |
| Giraffe | **Projected GeoJSON + Python 스크립트** | DXF | STL, OBJ, IFC, (GLB) | GeoJSON | (CSV/XLS) |
| Snaptrude | × | — | Revit, ArchiCAD | — | — |
| Archistar | △ CAD(Basic 이상, Free 불가) | CAD(Basic 이상) | — | — | — |
| VU.CITY | 가져오기만 | — | (가져오기 형식) FBX/OBJ(Legacy), glTF/GLB(신); 내보내기 미기재 | (가져오기 형식) GeoJSON(신) | 이미지·영상 |
| Hypar | ○ Rhino 직접 | DXF/DWG | Revit, (IFC/glTF) | — | PDF/PNG |
| DBF | △ 연동 | 2D CAD | 3D 모델, Revit·Archicad 플러그인 | — | — |
| Ladybug/Urbano/DeCodingSpaces | ○ (Grasshopper 네이티브) | Rhino 전 형식 | Rhino 전 형식 | GeoJSON/shp 입력 | CSV |

### 3.3 가격 요약(공개 리스트가)
| 플랫폼 | 가격 | 등급 |
|---|---|---|
| Forma | US$1,460/년(단독), AEC Collection 포함 | [블로그] 확인 필요 |
| TestFit | Parking US$195/월; Site Solver US$15,000/년~; 애드온 +US$100–170/월 | [공식] |
| Giraffe | Core US$45/월; Teams US$1,500/유저/년 | [공식] |
| Cadmapper | 1 km² 무료; 100 km²까지 소액(비공개) | [공식] |
| PlaceMaker | US$109/년 + 크레딧(US$20/100; 명목가치 US$0.15 vs 최소 팩 환산 US$0.20 — 페이지 간 불일치, 확인 필요) | [공식] |
| blosm | 무료 / Premium 19.99(Gumroad JSON, 통화 미표기) | [공식-curl] |
| BlenderGIS, Ladybug, DeCodingSpaces | 무료(GPL) | [공식] |
| Pollination(Ladybug 상용) | Rhino US$1,375/년, Revit US$2,750/년 | [공식] |
| Esri CityEngine/Urban | Professional US$2,200/년, Professional Plus US$4,200/년 | [언론] |
| Hypar | 무료(비상업) / US$1,000/년 | [공식] |
| Snaptrude | 무료 / US$60/월 / US$100/월 | [공식] |
| Deepblocks | US$99.99–499.99/월 | [공식] |
| Archistar | A$95 / 345 / 595/월 | [공식] |
| DBF, UrbanFootprint, VU.CITY | 비공개(문의) | [공식] |
| Modelur | 무료 플랜 + 유료(금액 확인 필요) | [공식 포럼] |
| Urbano, Morphocode | 미표시 | [공식] |

---

## 4. 결론 A — 해외 플랫폼의 표준 산출물 목록
**컨텍스트(파일로 받는 것)**
1. 건물 매스(footprint 압출, 높이 또는 층수×3 m) — 전 플랫폼
2. 지형 메시 또는 등고선(25–30 m급, 상용은 지역 고해상) — 대부분
3. 도로 중심선(+폭·위계), 보행로, 철도 — 대부분
4. 수계 폴리곤 — 8종(Cadmapper·PlaceMaker·blosm·BlenderGIS·CityEngine·ArcGIS Urban·Giraffe·VU.CITY; Forma는 공식 블로그에 수계 언급이 없어 미확인, §3.1)
5. 식생 폴리곤(숲), 개별 수목(일부) — 절반
6. 필지선·조닝(미·호주 한정) — 규모검토 계열
7. 위성·항공 영상 텍스처 — 대부분
8. 포토리얼 3D 메시(Google 3D Tiles) — 컨텍스트 전문 2종

**분석(화면·파일로 받는 것)**
1. 일조시간(지면·입면, 날짜 선택) 2. 그림자(이산·누적·임계) 3. 일사·태양광 잠재량 4. 주광 잠재량 5. 바람(ML 즉시 + CFD) 6. 소음(도로·철도) 7. 미기후·열쾌적 8. 조망·가시권(ZTV/viewshed/isovist) 9. 보행·대중교통 접근성(walkscore·등시선·5/15분) 10. 가로망 중심성 11. 밀도·용량 지표(FAR·건폐·세대·주차) 12. 적정성 중첩 13. 토공 14. 탄소 15. 사업성

**교환 형식의 사실상 표준**: GeoJSON(Giraffe→Rhino, Modelur, Urbano 입력; VU.CITY 신플랫폼은 데이터 가져오기 형식) · DXF(Cadmapper, TestFit, Giraffe, CityEngine) · glTF/OBJ(3D 뷰어용) · IFC(BIM 핸드오프: Forma 4.3, Giraffe, CityEngine buildingSMART) · CSV/Excel(지표).

## 5. 결론 B — 한국 공공데이터로 재현 가능/불가능
§0의 표가 결론이다. 요점만 재정리:
- **가능(데이터 우위)**: 건물 속성(높이·층수·용도·준공연도), 5 m급 지형, 필지·용도지역, 시간대별 생활인구.
- **가능(계산)**: 일조·그림자·일사·조망·가시권·접근성·중심성·밀도·적정성·토공. Rhino 안에서 자체 구현하거나 Ladybug(GPL) 호출.
- **부분**: 3D 포토리얼 메시(Vworld 3D 72건·S-Map 범위 확인), 침수(2014 서울 데이터셋 종료, 생활안전지도 확인), 바람 CFD·미기후(가능하나 플러그인 즉시성 없음), 탄소(계수 DB 부재).
- **불가**: ML 즉시 바람, 소음지도, 디지털 조닝 룰, 수목 캐노피, VMT·에너지·물 모델.

## 6. UrbanDesignTool 시사점(요약 외 추가)
- 그림자 UI는 ArcGIS Urban 3모드(임계·누적·이산)가 가장 명료하다. 일조는 Forma처럼 "지면/입면 × 날짜 다중" 2축이면 충분.
- 보행 접근성은 Urbano v2의 "Import Buildings/Streets/Transit → Walkscore by Block" 템플릿 구조를 따르면 도로망(수치지형도 도로중심선)+역·정류장으로 바로 된다.
- 내보내기는 Giraffe가 Rhino를 위해 GeoJSON+스크립트를 택한 점이 시사적 — 우리 플러그인은 반대로 Rhino가 소스이므로 **3dm(레이어·UserText) + GeoJSON + AI/SVG + CSV** 네 가지로 고정.
- Forma Street Design(2026-09 베타)이 "가로 단면·교차로 파라메트릭"을 들고 나왔다. 도로를 선이 아니라 폭·보도·차로 속성이 있는 객체로 저장해 두면 후속 확장이 쉽다.
- **Forma Rhino 애드인이 이미 OSM 기반 지형·주변 건물을 Rhino에 직접 가져온다**(§2.1). 따라서 UrbanDesignTool의 가치는 '컨텍스트를 Rhino로'가 아니라 (a) 한국 공공데이터 속성(높이·층수·용도·준공연도·용도지역·생활인구)이 UserText로 들어간 객체, (b) 5 m급 지형·1:5000 수치지형도 정밀도, (c) 일러스트 베이스맵·현황도 산출이다. Forma 애드인의 지원 Rhino 버전·교환 단위는 §7-2 확인 필요.

## 7. 미해결 질문(확인 필요)
1. Forma의 한국 지역 데이터 공급자(건물 높이·지형) 유무 — Data Coverage App 수동 확인 필요.
2. ~~Forma Rhino 애드인 존재 여부~~ → **해결**(공식 블로그 2023-11-03·2024-06-03, 양방향 동기화). 남은 것: Grasshopper 전용 애드인 유무, 애드인이 주는 교환 단위(지형 메시·건물 솔리드 형식·좌표계)와 Rhino 8 지원 범위.
3. Forma 단독 가격(US$1,460/년)과 AEC Collection 포함 여부 — autodesk.com 직접 확인.
4. Cadmapper 현재 유료 단가(1–100 km²).
5. Modelur 2026 유료 플랜 금액(modelur.com 접속 불가).
6. Urbano v2 라이선스(오픈소스 여부).
7. Giraffe 건물 3D 컨텍스트 출처(OSM? 지자체?).
8. Vworld 2D Data API `LT_C_BLDGINFO`의 `size` 상한·`page` 파라미터 — 가이드 상세 페이지가 JS 렌더링이라 미확인(보유 코드로 검증 가능).
9. 국토지리정보원 DEM 공개 해상도(5 m 공개제한 vs 90 m 공개) — data.go.kr 페이지와 국토정보플랫폼 '공개DEM' 메뉴(map.ngii.go.kr/ms/map/NlipMap.do) 모두 해상도·공개제한 미기재. 확인 방법: 국토정보플랫폼 로그인 후 공개DEM 메뉴에서 격자 크기·도엽 단위 확인.
10. Vworld 공간정보 다운로드의 3D 포맷 72건이 건물 LOD·텍스처를 포함하는지, 서울 전역인지.
11. 행정안전부 생활안전지도 전국 침수흔적도 SHP 제공 여부·연도 — safemap.go.kr 본문이 JS 미렌더링으로 curl 확인 불가. 확인 방법: 브라우저에서 생활안전지도 침수흔적도 메뉴 열람 + 공공데이터포털 '침수흔적도' 검색.
12. 서울 가로수 위치·수종 데이터셋 ID, 보행자 네트워크 공개 데이터, 건물에너지 사용량 공개 범위, S-Map 3D 모델 다운로드 형식(smapModelLibrary.do는 '배치' 기능만 확인, 형식 미기재) — 검색 한도 소진으로 미확인.
13. 국가소음정보시스템의 '실시간 소음 지도'는 측정점 기반(환경소음 실시간/수동·항공기·철도·도로진동)으로 확인됨. 남은 것: 지자체 전략소음지도(소음·진동관리법상 소음지도) 격자 자료의 공개·다운로드 여부.
14. ArcGIS Urban: Professional Plus 유저타입 요구 여부(Esri KB 000035058 403 미열람; trial 페이지 간접 근거만), CityEngine·SLPK 내보내기 유무(doc 사이트맵 86 URL에 없음).
15. VU.CITY 내보내기 형식 — pricing 페이지는 가져오기 형식(Model/Data import formats)만 기재.
16. PlaceMaker 크레딧 명목가치(credits 페이지 US$0.15)와 최소 팩 환산 단가(US$0.20)의 차이 — 팩 크기별 단가표 확인.
17. 도로명주소 전자지도(행정안전부, 건물·도로구간 SHP) 공식 다운로드 페이지·갱신 주기·좌표계 — 추정 URL 404로 미열람. 확인 방법: 공공데이터포털·주소정보 공식 사이트에서 '도로명주소 전자지도' 검색.
18. Snaptrude 사이트 가져오기의 도로 생성 여부(help 문서 선택 항목에 없음).

---

## 출처 목록 (접근일 2026-10-07)

### 공식(직접 열람)
- Autodesk Forma 블로그 "Site Context in Revit via Forma" (2023-12-11): https://blogs.autodesk.com/forma/2023/12/11/site-context-in-revit-via-forma/
- Autodesk Forma 블로그 "Introducing total carbon analysis in Forma Site Design" (2026-07-17): https://blogs.autodesk.com/forma/2026/07/17/introducing-total-carbon-analysis-in-forma-site-design-understand-embodied-operational-and-total-carbon-from-the-earliest-stage-of-design/
- Autodesk Forma 블로그 "sun hours analysis" (2026-02-09): https://blogs.autodesk.com/forma/2026/02/09/balancing-comfort-and-efficiency-with-formas-sun-hours-analysis/
- Autodesk Forma 블로그 "Designing with wind" (2026-07-03): https://blogs.autodesk.com/forma/2026/07/03/designing-with-wind-what-a-childrens-science-museum-taught-us/
- Autodesk Forma 블로그 "Introducing Autodesk Forma Street Design" (2026-09-15): https://blogs.autodesk.com/forma/2026/09/15/introducing-autodesk-forma-street-design/
- Autodesk Forma 블로그 색인(Zoneomics 제휴 2024-08-19 포함): https://blogs.autodesk.com/forma/
- Autodesk Forma 블로그 "Forma's integration with Rhino and Dynamo" (2023-11-03): https://blogs.autodesk.com/forma/2023/11/03/formas-integration-with-rhino-and-dynamo/
- Autodesk Forma 블로그 "How to connect a Forma project to Rhino" (2024-06-03, 'bringing your Forma terrain and surrounding building data back into Rhino'): https://blogs.autodesk.com/forma/2024/06/03/combined-forma-rhino/
- TestFit Pricing: https://www.testfit.io/pricing
- TestFit Site Solver: https://www.testfit.io/product/site-solver
- TestFit 4.8 Data Maps: https://www.testfit.io/blog/testfit-4-8-reduce-risks-with-data-maps
- Giraffe Self-serve(가격): https://www.giraffe.build/self-serve
- Giraffe for Architects(분석·내보내기): https://www.giraffe.build/architects/
- Giraffe Help "Rhino": https://help.giraffe.build/en/articles/12038002-rhino
- Cadmapper: https://cadmapper.com/
- PlaceMaker Shop(구독·종량제): https://placemakerdata.com/placemaker-shop-now/
- PlaceMaker Credits: https://placemakerdata.com/placemaker-credits/
- blosm GitHub README: https://github.com/vvoovv/blosm
- blosm Wiki Premium Version: https://github.com/vvoovv/blosm/wiki/Premium-Version
- blosm Gumroad(내장 JSON price 19.99): https://prochitecture.gumroad.com/l/blosm
- BlenderGIS GitHub: https://github.com/domlysz/BlenderGIS
- Esri ArcGIS Urban overview: https://www.esri.com/en-us/arcgis/products/arcgis-urban/overview
- Esri ArcGIS Urban "Work with shadow cast": https://doc.esri.com/en/arcgis-urban/latest/help/help-analysis-shadow-cast.html
- Esri ArcGIS Urban "Create a scenario comparison report" (2026.2, Microsoft Excel 워크북 다운로드): https://doc.esri.com/en/arcgis-urban/2026.2/help/help-create-scenario-comparison-report.html
- Esri ArcGIS Urban "Work with scenario web scenes" (2026.2): https://doc.esri.com/en/arcgis-urban/2026.2/help/help-create-scenario-web-scene.html
- Esri ArcGIS Urban 문서 사이트맵(86 URL; export·CityEngine·SLPK 페이지 없음): https://doc.esri.com/en/arcgis-urban/latest/sitemap.xml
- Esri ArcGIS Urban trial("The trial includes one Professional Plus and three Viewer user types"): https://www.esri.com/en-us/arcgis/products/arcgis-urban/trial
- Esri ArcGIS user types overview(Urban 언급 없음): https://www.esri.com/en-us/arcgis/products/user-types/overview
- Esri CityEngine FAQ: https://doc.arcgis.com/en/cityengine/latest/get-started/cityengine-faq.htm
- Esri CityEngine "Export models overview": https://doc.arcgis.com/en/cityengine/latest/help/help-export-models-overview.htm
- Esri ArcGIS Online 구매 페이지(유저타입 구성, 금액 미표시): https://www.esri.com/en-us/arcgis/products/arcgis-online/buy
- Hypar Plans/pricing: https://docs.hypar.io/pricing-and-purchasing
- Delve 리디렉트(curl -I): https://delve.sidewalklabs.com/ → https://mapsplatform.google.com/maps-products/earth/capabilities/
- Digital Blue Foam Pricing: https://www.digitalbluefoam.com/pricing
- Digital Blue Foam Docs About: https://docs.digitalbluefoam.com/docs/about/
- Digital Blue Foam Features: https://digitalbluefoam.com/features
- Archistar Pricing: https://www.archistar.ai/pricing/
- Archistar FAQ: https://www.archistar.ai/faq/
- Snaptrude Pricing: https://www.snaptrude.com/pricing
- Snaptrude Help "Import Site (Topography)": https://help.snaptrude.com/en/articles/11114145-import-site-topography
- Morphocode Explorer overview: https://morphocode.com/morphocode-explorer-overview/ ; 서비스 확인: https://explorer.morphocode.com/
- Urbano Docs: https://docs.urbano.io/latest/ , https://docs.urbano.io/latest/urbano-2/ ; 사이트: https://www.urbano.io/
- DeCodingSpaces Toolbox: https://toolbox.decodingspaces.net/
- Ladybug Tools About: https://www.ladybug.tools/about.html
- Pollination Pricing: https://www.pollination.solutions/pricing
- Modelur 공식 포럼 스레드(SketchUp Community, 2022): https://forums.sketchup.com/t/modelur-free-data-driven-urban-design-extension/205033
- VU.CITY Pricing: https://www.vu.city/pricing ; London: https://www.vu.city/cities/london
- Deepblocks: https://deepblocks.com/
- UrbanFootprint Platform: https://urbanfootprint.com/platform/ ; Analysis Modules: https://urbanfootprint.com/blog/blog-post/get-more-from-urbanfootprint-using-analysis-modules/
- Google Maps Platform Earth capabilities(Delve 리디렉트 목적지): https://mapsplatform.google.com/maps-products/earth/capabilities/
- Vworld 2D Data API 가이드(레이어 목록): https://www.vworld.kr/dev/v4dv_2ddataguide2_s001.do ; 레퍼런스(158개): https://www.vworld.kr/dev/v4dv_2ddataguide_s001.do
- Vworld 공간정보 다운로드(737건, 포맷별 건수): https://www.vworld.kr/dtmk/dtmk_ntads_s001.do
- 공공데이터포털 국토지리정보원 DEM: https://www.data.go.kr/data/15059920/fileData.do
- 국토정보플랫폼 국토정보맵('공개DEM' 메뉴 확인, 해상도 미기재): https://map.ngii.go.kr/ms/map/NlipMap.do
- 공공데이터포털 건축HUB 건축물대장정보 서비스: https://www.data.go.kr/data/15134735/openapi.do
- 서울 열린데이터광장 집계구 단위 서울 생활인구(OA-14979): https://data.seoul.go.kr/dataList/OA-14979/S/1/datasetView.do
- 서울 열린데이터광장 수방 침수흔적도 2014(OA-21178, 서비스 종료 표기): https://data.seoul.go.kr/dataList/OA-21178/S/1/datasetView.do
- 서울 열린데이터광장 도로교통 소음 측정정보(OA-15473): https://data.seoul.go.kr/dataList/OA-15473/F/1/datasetView.do
- 서울 TOPIS 교통정보 열람(교통량 메뉴): https://topis.seoul.go.kr/refRoom/openRefRoom_1.do
- 통계청 SGIS 오픈API: https://sgis.mods.go.kr/developer/html/openApi/api/data.html
- OneBuilding 한국 EPW 목록: https://climate.onebuilding.org/WMO_Region_2_Asia/KOR_South_Korea/index.html
- S-Map 모델 라이브러리: https://smap.seoul.go.kr/smapModelLibrary.do
- 국가소음정보시스템(메인 '실시간 소음 지도' 확인 — 환경소음 실시간/수동·항공기·철도·도로진동, 측정점 기반): https://www.noiseinfo.or.kr/

### 언론
- AEC Magazine "Digital Blue Foam launches for sustainable building design" (2022-02-02): https://aecmag.com/concept-design/digital-blue-foam-launches-for-sustainable-building-design
- CG Channel "Esri releases CityEngine 2026" (2026-07): https://www.cgchannel.com/2026/07/esri-releases-cityengine-2026/
- Fabbaloo "The Amazing CADMAPPER" (2018-12, 과거 단가): https://www.fabbaloo.com/2018/12/the-amazing-cadmapper

### 블로그·리뷰(제3자)
- CAD Forum "How to export an IFC model from Autodesk Forma" (2025-02-28): https://www.cadforum.cz/en/how-to-export-an-ifc-model-from-autodesk-forma-tip14661
- DataDrivenAEC "Delve by Sidewalk Labs": https://datadrivenaec.com/tools/delve-by-sidewalk-labs
- aec+tech "Delve": https://www.aecplustech.com/tools/delve

### 미열람(검색 스니펫만; 403·JS)
- Autodesk Forma 제품 상세/환경분석/가격: https://www.autodesk.com/products/forma/product-details , https://www.autodesk.com/products/forma-site-design/environmental-impact-analysis , https://www.autodesk.com/products/forma/pricing
- Autodesk 지원 "How to use Contextual data when coverage varies in Autodesk Forma Site Design"(일본 Esri 지형 6–13 m): https://www.autodesk.com/support/technical/article/caas/sfdcarticles/sfdcarticles/How-to-use-Contextual-data-when-coverage-varies-in-Autodesk-Forma-Site-Design.html
- Forma Data Coverage App(JS): https://app.autodeskforma.eu/data-provider-map
- TrustRadius Forma 가격: https://www.trustradius.com/products/autodesk-forma/pricing
- Esri KB "Product sales update: ArcGIS Urban": https://support.esri.com/en-us/knowledge-base/product-sales-update-arcgis-urban-000035058
- SketchUp PlaceMaker 공식(403): https://www.suplacemaker.com/
- Modelur(접속 불가): https://modelur.com/
- food4rhino Urbano(403): https://www.food4rhino.com/en/app/urbano
- Kinetica Studio LinkedIn: https://au.linkedin.com/company/kineticastudio
- 행정안전부 생활안전지도(본문 JS 미렌더링): https://www.safemap.go.kr/

---

## 검증 이력

- **2026-10-07 2차 검증 반영.** 검증 세션과 본 반영 세션 모두 WebSearch 한도(200회) 소진 상태라 WebFetch·curl만 사용. 아래 표의 출처 URL은 반영 세션에서 curl로 재확인했고(HTTP 200·문구 검출), Esri KB 000035058은 403으로 여전히 미열람.

| 판정 | 항목 | 수정 내용(절) | 근거 |
|---|---|---|---|
| refuted | Archistar CAD 내보내기 | 'Professional·National만' → **Basic 이상 가능, Free만 불가** (§2.9, §3.2) | archistar.ai/pricing 비교표 'Export designs to CAD file' 행 아이콘 순서 minus-grey→check-navy→check-navy; National 카드 'Everything in BASIC, plus' |
| refuted | PlaceMaker 크레딧 명목가치 | 'US$0.15' 단일 표기 → credits 페이지 US$0.15 vs shop 최소 팩 환산 US$0.20 **불일치·확인 필요** (§2.12, §3.3, §7-16) | placemakerdata.com/placemaker-credits/ 'nominal value of $0.15 USD each'; placemaker-shop-now/ '$20 for 100 credits'(본 세션 curl에는 $0.20 문구 미검출) |
| refuted | Snaptrude 컨텍스트 '도로' | 도로 삭제, '확인 필요' (§2.4, §3.1 '?', §7-18); 가격 출처를 pricing 페이지로 분리 | help.snaptrude.com 11114145: 선택 항목 Elevations·Buildings·Satellite view·Property parcels, 'road' 0건 |
| unverifiable | ArcGIS Urban Professional Plus·CityEngine/SLPK 내보내기 | [공식] → **[미열람·확인 필요]**; 그림자 3모드·Excel 출처를 doc.esri.com 페이지로 교체; 내보내기는 web scene 생성만 기재 (§0, §2.16, §3.2, §7-14) | overview 페이지 'included with ArcGIS user types'만; trial 페이지 'one Professional Plus'; doc 사이트맵 86 URL에 export·CityEngine·SLPK 없음 |
| 추가 | Forma 공식 Rhino 애드인 | '존재 여부 확인 필요' → **존재 확인, 양방향 동기화** (§0 결론·권고 1, §2.1, §3.2, §6, §7-2) | blogs.autodesk.com/forma 2023-11-03, 2024-06-03 |
| 추가 | VU.CITY 가져오기/내보내기 | §2.15 '내보내기' → **가져오기**로 정정(pricing 표는 Model/Data import formats); GeoJSON은 Early Access 데이터 가져오기 형식으로 확인; 내보내기 형식 미기재 (§0 권고 5, §3.2, §4, §7-15) | vu.city/pricing |
| 추가 | CityEngine IFC | 내보내기 목록에 IFC(buildingSMART) 추가 (§2.16, §3.2, §4) | doc.arcgis.com CityEngine export models overview |
| 추가 | TestFit 출처명 | Zoneomics·FEMA·SSURGO는 4.8 블로그 근거로 한정; Site Solver 페이지는 'ESRI integration'·'built-in zoning data' (§0, §2.7) | testfit.io/product/site-solver |
| 추가 | Forma 기상 표기 | 블로그 원문 'ERAS C3S' 오타 주석, 수계·식생 미언급 명시 (§0, §2.1) | blogs.autodesk.com/forma 2023-12-11 |
| 추가 | blosm 출처 분리 | 30 m·무료·GPL=README, Premium 기능=wiki(가격 없음), 19.99=Gumroad JSON(통화 미표기) (§0, §2.13, §3.3) | github.com/vvoovv/blosm, wiki Premium-Version, Gumroad |
| 추가 | §0 권고 2 '70%' | 근거 없는 수치 삭제 → '15종 중 6~7종(약 40–47%)' | 문서 내부 §4 목록 |
| 추가 | §4 수계 '대부분' | Forma 미확인 → 8종 명시 | §3.1 표 |
| 추가 | 국가소음정보시스템 | '측정자료·자료실만' → '실시간 소음 지도 있음(측정점 기반, 격자 아님)'; 전략소음지도 확인 필요 (§0, §7-13) | noiseinfo.or.kr 메인 |
| 추가 | 국토지리정보원 DEM | 국토정보플랫폼 '공개DEM' 메뉴 추가, 해상도 미기재 (§0, §7-9, 출처) | map.ngii.go.kr/ms/map/NlipMap.do |
| 추가 | 도로명주소 전자지도 | 후속 조사 목록 추가(공식 페이지 미열람) (§0, §7-17) | — |
| 유지 | 확인 필요 그대로 | 서울 가로수, S-Map 3D 다운로드 형식, 생활안전지도 침수흔적도 SHP, Forma 한국 커버리지, Forma 단독 가격 | — |
