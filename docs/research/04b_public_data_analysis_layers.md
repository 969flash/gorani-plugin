# 04b. 분석 보조 데이터 인벤토리 — 도시설계 현황분석용 비(非)기본도 공공데이터

- 작성일 / 모든 URL 접근일: **2026-10-07**
- **2026-10-07 1차 검증 반영본** — 정정·보강 내역은 맨 아래 "검증 이력" 절 참조.
- 범위: 기본도(필지·건물·도로·지형·하천)를 제외한, 현황분석 시트에 얹는 보조 레이어. 서울 우선, 전국 데이터는 서울 적용 가능 여부 기준으로 평가.
- 표 열: **데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처**
  - 접근 등급: **즉시**(인증키 자동승인 또는 로그인 없는 파일) / **로그인**(포털 회원 로그인 후 즉시) / **신청**(심사·운영계정·자료신청 등 사람 손 필요) / **불가**(공간데이터 미개방)
  - "확인 필요" 표기 = 1차 출처를 열어 직접 확인하지 못한 항목. URL은 지어내지 않았음.
- 출처 성격: 공공데이터포털(data.go.kr)·서울 열린데이터광장·각 기관 공식 페이지 = **공식 문서**. 언론 보도는 `[언론]`으로 구분.

---

## 0. 요약

**결론: 서울 현황분석 시트 14종 중 12종은 공식 개방데이터로 구성 가능하다 — 단, 그중 상당수는 일부 레이어에 로그인·자료신청이 필요하다(아래 표 '로그인·신청 필요' 열: 데이터마켓·T-data·국토정보플랫폼 로그인, 산림청·KTDB 자료신청, Earthdata·SNS 로그인 등).** 나머지 2종(경관 중점관리구역, 정비·개발사업 구역경계)은 PDF·웹 목록만 있어 수작업 디지타이징이 필요하다. 이 밖에 검증(2026-10-07)에서 드러난 공백 2개 — **지하철 출입구 포인트 좌표**(T-data 10045에는 역 좌표만 있음)와 **자전거도로 선형**(공식 SHP 미발견) — 은 도보 네트워크 노드 등 대체원 또는 디지타이징으로 메워야 한다(§5·§6·검증 이력 참조).

핵심 판단 7가지:

1. **인구는 SGIS 집계구 + 서울 생활인구 250m 격자로 간다.** 집계구 경계는 SGIS OpenAPI `boundary/statsarea.geojson`으로 받는다 — 요청변수는 **accessToken·adm_cd(행정동코드 8자리) 두 개뿐**이고, year(2000–2025)·low_search는 행정구역 경계 `boundary/hadmarea.geojson` 전용이다(집계구 연도는 응답 properties의 `base_year`로 확인). 좌표계는 경계 API 절에 명시돼 있지 않으나 예제 응답 좌표(957947, 1951107)가 UTM-K(EPSG:5179) 수치 범위와 일치하고 같은 문서의 지오코딩 API는 "UTM-K, EPSG:5179"로 명시 → 실 응답으로 재확인 권장. 통계는 `stats/population.json`(2015–2024)으로 붙인다. 일일 호출 한도 무제한. 서울 생활인구는 **집계구 단위 생산이 2026-07-31로 종료**되었고 250m 국가표준격자 데이터셋(OA-23019~23022)으로 바뀌었다 — 신규 설계는 격자 기준으로. 월 단위 최신 인구가 필요하면 주민등록인구(행안부 jumin.mois.go.kr·data.go.kr 등재 XLSX/HWP, 포맷 확인 필요)를 보조로 쓴다.
2. **상권은 소진공 상가정보 CSV(분기, 전국 ~200만 건, 경위도 포함)가 1차 소스.** 서울 상권분석서비스(서울신용보증재단)는 추정매출·길단위인구가 유용하지만 2024년 표준단위구역 개편으로 2021년 이후만 제공, 상권영역 SHP는 EPSG:5181. 소진공 API는 오퍼레이션 15개 중 **지번(PNU) 단위 조회 storeListInPnu**가 있어 보유 필지DB와 직접 조인된다.
3. **지가·소유·공시지가 벌크 파일은 전부 Vworld '디지털트윈국토 데이터마켓'(vworld.kr/dtmk)에 있다.** 구 국가공간정보포털(nsdi.go.kr)은 2026-10-07 현재 DNS가 풀리지 않는다. 데이터마켓은 로그인 필요, 시도별 SHP/CSV, 개별공시지가 반기·토지소유 '연간' 갱신(포털 메타 표기). **단 토지소유정보 등재본은 `_20240408`이고 차기 등록 예정일 2025-11-01이 경과한 채 미갱신** — 국공유지 레이어 기준시점이 2년 이상 늦을 수 있고, 소유구분 컬럼 구성도 공개 페이지에 나열돼 있지 않아 '컬럼 정의서'(로그인 후 다운로드) 확인이 선행 과제다. 개별공시지가 전국 건수는 출처별로 다르다(data.go.kr 159,935,632행 vs 데이터마켓 dsId=6 '공간정보 38,378,643 / 정보 790,263,935').
4. **교통 레이어는 서울 열린데이터광장 + T-data(서울교통빅데이터플랫폼) 조합.** 정류소·역사 좌표·승하차는 즉시. 역 좌표 마스터(T-data data_id=36)는 페이지상 **서울시 통합 로그인** 표기. 지하철 **출입구**는 정정: T-data '지하철 출입구 정보 및 주변정류장 정보'(data_id=10045, `tnSubwayEntrc.csv`)는 **로그인 없이 바로 다운로드되지만**(2026-10-07 비로그인 curl HTTP 200, 2,788,890바이트) **출입구 좌표가 없다** — 헤더는 `지하철역ID,출입구번호,정류장ID,주변건물,출구와정류장간이동거리,지하철역X좌표,지하철역Y좌표`로, 좌표는 **역(station) 좌표**(투영좌표, 좌표계 미표기; 예 195710.0/442518.2)다. 출입구 포인트 좌표의 공식 전수 데이터셋은 data.go.kr 검색에서도 찾지 못했고(리프트 설치 출입구 83건·캐노피 설치정보 1,447행·국가철도공단 출구정보 API만 확인), **1차 대체원은 도보 네트워크 OA-21208의 지하철 출입구 노드(WGS84, 노드 유형 코드·지하철역코드 보유)**다. 도보 네트워크(노드링크, 횡단보도·육교 포함)와 횡단보도(EPSG:5186, 월간)는 즉시.
5. **재해는 침수흔적도(2010–2025 연도별 SHP)·침수예상도(SHP, EPSG:5186)가 즉시, 산사태위험지도는 신청(2025년판 래스터만, map.forest.go.kr 일반인 신청), 급경사지는 전국 파일(37,778건, 주소 기반).**
6. **라이선스 함정 3개**: 서울 가로수 위치정보(OA-22904)는 **공공누리 4유형(상업적 이용금지·변경금지)**, 에어코리아 API와 학교알리미 API는 **변경금지** 조건. 유료 플러그인에 번들하려면 이 셋은 "사용자가 직접 내려받기" 방식으로 분리해야 한다.
7. **서울 열린데이터광장은 2026-10-07 하루 동안 여러 페이지가 간헐적으로 `서비스 지연(103)`을 반환했다.** 수집기는 재시도·백오프를 기본으로 두고, 열린데이터광장 의존 레이어는 캐시를 전제로 설계할 것. 검증 단계(같은 날)에도 OA-15554가 WebFetch 2회 연속 103을 반환하고 curl 재시도로만 성공해 이 전제는 재확인됐다.

### 시트별 접근성 한눈에 보기

| 현황분석 시트 | 즉시 | 로그인·신청 필요 | 불가(수작업) |
|---|---|---|---|
| 인구·가구·주택 | SGIS 집계구·통계 API, 생활인구 250m(열린데이터광장), 수도권 생활이동, K-apt 단지 API, 주민등록인구 통계(행안부 jumin.mois.go.kr·data.go.kr XLSX/HWP — 포맷·행정동 매칭 확인 필요) | 국토통계지도 격자(국토정보플랫폼 로그인), KOSIS(개발계정 1,000/일) | — |
| 상권·유동 | 소진공 상가 CSV/API, 상권분석 추정매출·길단위인구·영역, S-DoT 방문자수, 실시간 도시데이터 | — | — |
| 지가·거래 | 서울 개별공시지가 API(1989–2026), 실거래가 API 11종 | 개별공시지가·표준지 벌크(데이터마켓 로그인), 공시지가 WMS/WFS(운영단계 심의) | — |
| 소유·건물 | 건축HUB 건축물대장 10종, 건축HUB 건물에너지정보 API(월간), 건물에너지 전기·가스 벌크 XLSX | 토지소유정보 벌크(데이터마켓 로그인; 등재본 2024-04-08, 컬럼 정의서 확인 선행) / API(운영단계 심의) | — |
| 대중교통 | 서울 버스정류소·노선·승하차, 지하철 승하차, 전국 버스정류장, 따릉이 마스터, 지하철 출입구–인접정류장 매핑 CSV(T-data 10045, 무로그인·**출입구 좌표 없음**) | 역사 좌표 마스터(T-data 36, 로그인 표기), KTDB GTFS(자료신청) | 지하철 출입구 포인트 좌표(공식 전수 데이터셋 미확인 → 도보 네트워크 OA-21208 노드로 대체), 버스 노선 선형(소스 미발견) |
| 보행·자전거 | 도보 네트워크, 횡단보도(서울·전국표준), 어린이보호구역 표준 | — | 자전거도로(data.go.kr에 SHP·좌표 데이터셋 없음 → 디지타이징 또는 수치지형도 대체) |
| 교통량 | 서울 지점별 일자별 교통량(API·DB), 교통량 이력 API, 연보 PDF | KTDB 교통량·네트워크(자료신청) | — |
| 공원·녹지 | 전국도시공원 표준, 도시계획시설(공간시설) SHP, 보호수, **생태현황도(비오톱 평가도) SHP** | 환경부 토지피복지도(환경공간정보서비스 로그인·자료신청) | 가로수(4유형, 번들 불가) |
| 생활SOC | 병의원·약국 XLSX(좌표), 어린이집 기본정보(좌표), 유치원알리미(좌표), 통학구역 표준, 주차장·CCTV·화장실·신호등 표준 | 유치원알리미(SNS 로그인) | 학교알리미·NEIS는 좌표 없음→지오코딩 |
| 역사·경관 | 국가유산 공간정보 SHP, 역사문화환경 허용기준 SHP, 경관지구·고도지구(DB 보유) | — | 경관 중점관리구역도(PDF) |
| 정비·개발 | 정보몽땅 사업장 엑셀(대표지번), Vworld 주거환경개선지구 WMS | — | 신속통합기획·모아타운·도시재생 구역경계(웹 목록·PDF) |
| 재해·안전 | 침수흔적도·침수예상도 SHP, 급경사지 전국 CSV, 생활안전지도 WMS | 산사태위험지도(산림청 신청) | — |
| 환경 | S-DoT 환경정보(1,170개소), 에어코리아 API(변경금지), 서울 도로교통소음(4지점) | — | 전략소음지도(개방 미확인) |
| 기상·야간 | ASOS 시간자료 API(1904~), KMA API허브, 가로등 CSV, VIIRS 야간광 | VIIRS(Earthdata 로그인) | — |

---

## 1. 인구·가구·주택

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| SGIS 집계구·행정구역 경계 (`boundary/statsarea.geojson`, `boundary/hadmarea.geojson`) | 국가데이터처 SGIS | OpenAPI, GeoJSON | 집계구·읍면동·시군구·시도. 좌표계: 경계 API 절에 명시 없음 — 예제 응답 좌표(957947, 1951107)가 **UTM-K EPSG:5179** 범위와 일치하고 같은 문서의 지오코딩 API는 EPSG:5179 명시 → 실 응답으로 확인 권장 | hadmarea: year 2000–2025 / statsarea: 응답 `base_year`로 확인 | 즉시(회원가입→인증키, accessToken) | 무료 | **두 엔드포인트의 파라미터가 다름.** `statsarea.geojson`: accessToken(필수) + adm_cd(행정동코드 8자리, 필수) **두 개뿐**. `hadmarea.geojson`: accessToken, year(2000–2025), adm_cd(2/5/8자리), low_search(0/1/2, 기본 1). 응답 properties: base_year, sido_cd, sgg_cd, emdong_cd, adm_cd, adm_nm, addr_en, x, y. https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/addressBoundary.html |
| SGIS 총조사 주요지표 (`stats/population.json`) | 국가데이터처 SGIS | OpenAPI JSON | 시도/시군구/읍면동(adm_cd) | 인구·주택 2015–2024, 사업체 2000–2024 | 즉시 | 무료 | 응답 tot_ppltn, ppltn_dnsty, aged_child_idx, avg_age, tot_family, avg_fmember_cnt, tot_house. **일일 사용한도 무제한**(변경 가능 고지). 테스트키→상용키 승인 절차. https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html , https://sgis.mods.go.kr/developer/html/newOpenApi/api/intro.html |
| KOSIS 통계자료 조회 서비스 | 국가데이터처 | REST JSON/XML | 통계표 단위(비공간) | 실시간 | 즉시(자동승인) | 공공누리 1유형 | 개발계정 1,000건/일, 운영 증설 가능. 1회 최대 40,000셀은 2차 출처(PublicDataReader 문서) 기준 — 확인 필요. https://www.data.go.kr/data/15127755/openapi.do |
| 서울 생활인구 — 집계구 단위(내국인) OA-14979 | 서울시+KT | CSV(zip), Sheet/OpenAPI | 집계구, 1시간 | 매일(4일 전까지) | 즉시 | 공공누리 1유형 | **"국가표준격자(250m) 단위 전환으로 기존 데이터 생산이 2026-07-31 이후 종료"**. 3명 이하 `*` 마스킹. 과거 분석용으로만 사용. https://data.seoul.go.kr/dataList/OA-14979/S/1/datasetView.do |
| 서울 생활인구 — **250m 격자** [내국인] OA-23019, [장기외국인] OA-23020, [단기외국인] OA-23021, 일별집계표 OA-23022/OA-23060 | 서울시+KT | CSV(연도별 zip, 2023~), Sheet/OpenAPI(당해연도, 4일 전까지) | 국가표준격자 250m(서울 약 8,500셀), 자치구별 파일, 1시간 | 매일 1회 | 즉시 | 공공누리 1유형 | 격자 경계 파일은 페이지에 미표기 → 격자ID 체계로 지오메트리 산출 가능 여부 확인 필요. https://data.seoul.go.kr/dataList/OA-23019/S/1/datasetView.do , 관련목록: https://data.seoul.go.kr/dataList/OA-14991/S/1/datasetView.do , 개요: https://data.seoul.go.kr/dataVisual/seoul/seoulLivingPopulation.do |
| 수도권 생활이동 (OD) OA-22298~OA-22659 (11종) | 서울시+KT | CSV | 서울 행정동 OD(타지역 시군구), 1시간, 월 단위 공개 | 월간 | 즉시 | 확인 필요 | 2024-01부터. 통근·등교·귀가·쇼핑·병원·관광·기타 7목적, 연령·성별. 250m 격자판은 빅데이터캠퍼스 내부 전용. https://data.seoul.go.kr/dataVisual/seoul/capitalRegionLivingMigration.do |
| 국토통계지도 — 인구 격자 (국토지리정보원) | 국토교통부 국토지리정보원 | SHP | 격자 100km/10km/1km/500m/250m/100m + 행정경계·용도지역별 | 수시 | 로그인(국토정보플랫폼) | 공공누리 1유형 | 9부문 164지표(총인구·유소년·생산가능·고령·학생·연령별). 대용량 전송 SW 필요. https://www.data.go.kr/data/15059921/fileData.do , 다운로드: http://map.ngii.go.kr/ms/map/NlipMap.do?tabGb=statsMap |
| 주민등록인구 통계(행정동·월별·연령별) — 행안부 주민등록 인구통계(jumin.mois.go.kr) / data.go.kr '서울특별시_등록인구 통계'(15046941, XLSX)·'서울특별시_주민등록인구(연령별 동별) 통계'(15046954, HWP) | 행정안전부 / 서울시 | 웹 통계표(다운로드 포맷 확인 필요) / XLSX / **HWP** | 행정동(비공간 — 행정동코드로 경계에 매칭) | 월간(주민등록 기준) | 즉시(파일·웹) — **포맷·행정동 매칭 확인 필요** | 확인 필요 | 센서스(SGIS 2024)보다 최신인 월 단위 인구 보조 소스. jumin.mois.go.kr는 접속 확인(2026-10-07) 및 메뉴 '행정동별 주민등록 인구통계 — 주민등록 인구 및 세대현황·연령별 인구현황·평균연령·인구증감·성/연령별 1인세대' 확인, 다운로드 포맷(CSV/XLS)·기간은 미확인(JS 렌더링). data.go.kr 등재본은 HWP가 섞여 표 추출 필요. https://jumin.mois.go.kr/ , 검색: https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=서울 주민등록인구 행정동 |
| 공동주택 단지 목록제공 서비스 (`AptListService3`) + 기본정보 서비스 | 국토교통부(K-apt) | REST JSON | 단지(주소·법정동코드, 좌표 없음) | 실시간 | 즉시(자동승인) | 무료 | 개발계정 5,000건/일. getTotalAptList3/getSidoAptList3/getSigunguAptList3/getLegaldongAptList3/getRoadnameAptList3. 세대수·동수·사용승인일·연면적은 기본정보 서비스. https://www.data.go.kr/data/15057332/openapi.do |
| 주택 공시가격 정보 / 표준지공시지가 파일 | 국토교통부 | 파일 | — | 연간 | 확인 필요 | 확인 필요 | 제목만 확인(국토교통부_주택 공시가격 정보_20250626, 국토교통부_표준지공시지가_20260101). https://www.data.go.kr/data/3073746/fileData.do , https://www.data.go.kr/data/15004246/fileData.do |

## 2. 상권·업종·유동인구

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 상가(상권)정보 파일 (최신판 `_20260630`) | 소상공인시장진흥공단 | CSV UTF-8 | 점포 포인트(경도·위도), 법정동코드 | **분기**(2026-08-05 수정, 차기 2026-10-31) | 즉시(로그인 불요) | 이용허락범위 제한 없음 | 상가업소번호·상호명·상권업종대분류코드·표준산업분류코드·지번·도로명주소. 포털 설명상 전국 약 200만 건, 10개 대분류. https://www.data.go.kr/data/15083033/fileData.do |
| 상가(상권)정보 API | 소상공인시장진흥공단 | REST JSON/XML | 반경·사각형·폴리곤·행정동·**지번(PNU)**·건물·상권영역 질의 | 실시간 | 즉시(자동승인) | 무료 | 오퍼레이션 **15개**(기반경로 `/B553077/api/open/sdsc2`; 호출 호스트는 신청 후 활용가이드로 확인): 상권영역 storeZoneOne·storeZoneInRadius·storeZoneInRectangle·storeZoneInAdmi, 상가 storeOne·storeListInBuilding·**storeListInPnu**·storeListInDong·storeListInArea·storeListInRadius·storeListInRectangle·storeListInPolygon·storeListInUpjong·storeListByDate, 업종분류 baroApi. **storeListInPnu는 보유 필지DB(PNU)와 직접 조인 가능**, storeListByDate로 증분 갱신. 개발계정 10,000건/일. https://www.data.go.kr/data/15012005/openapi.do |
| 서울시 상권분석서비스(영역-상권) OA-15560 | 서울신용보증재단 | ZIP(2.07MB) | 상권 폴리곤, **EPSG:5181** | 비정기(2023-10-23) | 즉시 | 공공누리 1유형 | 상권_구분_코드·상권_코드·엑스/와이좌표·행정동_코드·영역_면적. https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do |
| 상권분석(추정매출-상권) OA-15572 | 서울신용보증재단 | CSV, OpenAPI | 상권×서비스업종, 분기 | 분기(2026-09-11) | 즉시 | 공공누리 1유형 | **2024년 표준단위구역 개편으로 2026-07-03부터 2021년 이후분만 제공.** 요일·시간대·성별·연령대별 매출. https://data.seoul.go.kr/dataList/OA-15572/A/1/datasetView.do |
| 상권분석(길단위인구-상권) OA-15568 | 서울신용보증재단 | DB/CSV | 상권, 분기 | 월간(2026-09-11) | 즉시 | 공공누리 1유형 | 총_유동인구_수, 성별·연령대·시간대·요일별. 동일한 2021~ 제한. https://data.seoul.go.kr/dataList/OA-15568/S/1/datasetView.do |
| S-DoT 유동(방문자수) OA-15964 / 실시간 OA-22832 | 서울시 디지털도시국 | CSV, OpenAPI | 센서 포인트(설치위치 별도 xlsx) | 실시간(2026-02-02부터 1시간 내 제공) | 즉시 | 공공누리 1유형 | 센서 1,100개소(2026-03 기준). https://news.seoul.go.kr/gov/archives/539344 |
| 서울 실시간 도시데이터 (`citydata`) | 서울시 | OpenAPI XML | 주요 장소 약 120곳(핫스팟), 5분 | 실시간 | 즉시(인증키) | 공공누리 1유형 | 실시간 인구 혼잡도·예측, 상권, 도로소통, 대중교통, 날씨. 1회 1장소. https://www.data.go.kr/data/15146211/openapi.do |

## 3. 지가·거래

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 개별공시지가정보 벌크 (데이터마켓 dsId=6) | 국토교통부 | **SHP/CSV, 시도별** | 필지(PNU), **GRS80 EPSG:5186** | **반기**(기준 2026-05-26) | **로그인**(Vworld 디지털트윈국토) | 이용허락범위 제한 없음 | 전국 건수는 출처별로 다름 — data.go.kr 메타 **159,935,632행** vs 데이터마켓 dsId=6 페이지 '개별공시지가공간정보 **38,378,643** / 개별공시지가정보 **790,263,935**'(공간정보=필지 수, 정보=연도별 누적 속성으로 추정 — 확인 필요). 서울 SHP 수십~140MB. PNU로 보유 필지DB에 조인. https://www.data.go.kr/data/15052266/fileData.do , https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=6 |
| 개별공시지가정보 (WMS/WFS/속성정보) API | 국토교통부 국가공간정보센터 | REST JSON/XML, WMS/WFS | 필지 | 실시간 | 개발 자동 / **운영 심의승인** | 제한 없음 | 운영 전환 시 심의 필요 → 벌크 파일이 실무상 유리. https://www.data.go.kr/data/15124014/openapi.do |
| 서울시 개별공시지가 정보 OA-1180 | 서울시 토지관리과 | ZIP, OpenAPI | 법정동코드+지번, 1989–2026 | 연 4회(1/3, 5/3, 7/3, 9/3) | 즉시 | 공공누리 1유형 | 기준연도·공시지가·공시일자·표준지여부. 시계열 지가변동 분석용. https://data.seoul.go.kr/dataList/OA-1180/S/1/datasetView.do |
| 아파트 매매 실거래가 자료 API (+ 전월세·연립다세대·단독다가구·오피스텔·토지·상업업무용·공장창고·분양권 등 11종) | 국토교통부 | REST **XML** | 법정동 5자리(LAWD_CD)×계약년월(DEAL_YMD), 지번·도로명 | 실시간 | 즉시(자동승인) | 무료 | 개발계정 10,000건/일. 층 정보 제한, 동 정보는 소유권이전 등기 완료분. 정확한 서비스 경로는 신청 후 상세페이지의 활용가이드로 재확인(확인 필요). https://www.data.go.kr/data/15126469/openapi.do |
| 2025-09-30 "오픈API 대체서비스 안내(125종)" | 공공데이터포털 공지(스크립드 재게시본) | — | — | — | — | — | 국토부 실거래가 4종 포함된 대체 안내 문서가 비공식 경로에서 확인됨. **원문 공지 확인 필요**. https://www.scribd.com/document/926853673/ |

## 4. 토지소유·건축물대장·국공유지

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 토지소유정보 벌크 (데이터마켓 dsId=12) | 국토교통부 국가공간정보센터 | SHP/CSV, 시도별(데이터마켓 제공형식 '웹 다운로드 서비스, API 서비스') | 필지(PNU) | 포털 메타 '연간/매년'. **단 등재본은 `_20240408`, 차기 등록 예정일 2025-11-01이 경과한 채 2026-10-07 현재 미갱신** → 데이터마켓 실제 최신본 날짜 확인 필요 | **로그인**(데이터마켓, loginYn 체크) | 제한 없음 | 전국 38,378,643행. **컬럼 구성은 data.go.kr·vworld 페이지 어디에도 나열돼 있지 않음** — '컬럼 정의서'(로그인 후 별도 다운로드) **확인 필요**. 소유구분(국유지·시도유지·군유지·법인·개인 등) 컬럼이 있어야 **국공유지 레이어**를 만들 수 있으므로 정의서 확인이 선행 과제. 기준시점이 2년 이상 늦을 수 있음을 레이어 메타에 명기. https://www.data.go.kr/data/15045905/fileData.do (다운로드 https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=12) |
| 토지소유정보 (WMS/WFS/속성정보) API | 국토교통부 | WMS/WFS/REST | 필지 | 실시간 | 개발 자동 / 운영 심의 | 제한 없음 | https://www.data.go.kr/data/15123976/openapi.do |
| 건축HUB 건축물대장정보 서비스 (`apis.data.go.kr/1613000/BldRgstHubService`) | 국토교통부 | REST JSON/XML(`_type=json`) | sigunguCd+bjdongCd+bun+ji(필지) | **월간** | 즉시(자동승인) | 무료 | 10개 오퍼레이션: getBrBasisOulnInfo, getBrRecapTitleInfo, **getBrTitleInfo(표제부: mainPurpsCdNm, strctCdNm, grndFlrCnt, ugrndFlrCnt, useAprDay, totArea, archArea, platArea, bcRat, vlRat, indrAutoUtcnt, oudrAutoUtcnt)**, getBrFlrOulnInfo, getBrAtchJibunInfo, getBrExposPubuseAreaInfo, getBrWclfInfo, getBrHsprcInfo, getBrExposInfo, getBrJijiguInfo. 개발 10,000건/일. 898,800필지 전수 수집 시 운영계정 증설 필요. https://www.data.go.kr/data/15134735/openapi.do |
| 건축HUB 건물에너지정보 서비스 API | 국토교통부 | REST JSON/XML | sigunguCd+bjdongCd+bun+ji(필지)+useYm(사용연월) | **월간** | 즉시(자동승인) | 무료 | 개발계정 10,000건/일. 건축물대장과 동일 키로 조인. 탄소·에너지 현황 시트 소스. https://www.data.go.kr/data/15135963/openapi.do |
| 건물에너지 벌크 — 전기에너지 `_20240930` / 가스에너지 | 국토교통부(건축HUB hub.go.kr 다운로드) | XLSX | 지번 단위, 전기 **76,349,183행** | 확인 필요(등재본 2024-09-30) | 즉시(파일) | 확인 필요 | **단독주택·200세대 미만 공동주택 제외.** 대용량 → 서울분 필터 후 PNU 조인. 가스에너지는 data.go.kr 데이터셋 15054213(페이지 미열람, 확인 필요). https://www.data.go.kr/data/15054214/fileData.do |
| Vworld 디지털트윈국토 데이터마켓 (총 737개 데이터셋) | 국토교통부 | SHP/CSV/3D/TXT | — | 데이터셋별 | 로그인 | — | 연속지적도형·용도지역지구·GIS건물통합정보·토지이동이력 등. **nsdi.go.kr은 2026-10-07 DNS 미해석(ENOTFOUND)** — 구 오픈마켓 경로는 폐기된 것으로 보임(공식 이관 공지 미확인). https://www.vworld.kr/dtmk/dtmk_ntads_s001.do |

## 5. 대중교통

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 지하철역 좌표정보(역사마스터) T-data data_id=36 | 서울시 TAIMS | CSV | 역 포인트(위경도), 호선·환승 | 분기 | **서울시 통합 로그인**(페이지 표기 기준 — 10045가 비로그인 다운로드된 사례가 있어 실제 요건 재확인 권장) | CC BY | 2026-10-07 수정. https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=36 |
| 지하철 출입구 정보 및 주변정류장 정보 T-data data_id=10045 (`tnSubwayEntrc.csv`) | 서울시 BIS/미래첨단교통과 | CSV(2,788,890바이트, UTF-8; **각 필드 앞에 U+FEFF(BOM) 문자가 붙어 있어 파싱 시 strip 필요**) | **출입구 포인트 아님.** 헤더: 지하철역ID, 출입구번호, 정류장ID, 주변건물, 출구와정류장간이동거리, 지하철역X좌표, 지하철역Y좌표 — 좌표는 **역(station) 좌표**, 투영좌표, 좌표계 미표기(예 195710.0/442518.2, 206032.1/459511.0 → 값 범위상 FN 500,000 중부원점 TM 계열(EPSG:5181 또는 Bessel EPSG:5174/2097) 추정, 확인 필요) | 일별 | **즉시 — 로그인 불요**(페이지 JS `fileDownload()`가 `/dataprovide/download.do?id=11056`으로 직접 이동, 로그인 체크 없음; 2026-10-07 비로그인 curl HTTP 200·Content-Disposition attachment 확인) | CC BY | 용도는 **출입구별 인접 버스정류장 매핑**(환승·접근 분석). 출입구 포인트 좌표 소스는 아래 행 참조. https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=10045 |
| **지하철 출입구 포인트 좌표**(전수) | — | — | — | — | **확인 필요(공식 전수 데이터셋 미확인)** | — | 2026-10-07 data.go.kr 검색('서울 지하철 출입구', '지하철 출구 위치', '지하철 출입구 좌표')에서 전수 출입구 좌표 데이터셋 미발견. 확인된 인접 데이터: ① 서울특별시_지하철 출입구 리프트 위치정보(15098149 = 열린데이터광장 OA-21211; CSV **83행**, 리프트 설치 출입구만, WGS84, 노드링크 유형·노드 WKT·노드 ID·노드 유형 코드·시군구·읍면동·지하철역코드·지하철역명 — **도보 네트워크 노드의 부분집합**, 1유형) https://www.data.go.kr/data/15098149/fileData.do ; ② 서울교통공사_외부출입구_캐노피_설치정보(15082999; CSV 1,447행, 호선·역명·출입구번호·자치구·출입구 폭·관리주체·캐노피 종류·설치년도, **좌표 없음**, 수정 2026-09-08, 제한 없음) https://www.data.go.kr/data/15082999/fileData.do ; ③ 국가철도공단_역사별 출구정보 API(15041677; LINK형 JSON/XML, 개발·운영 자동승인, 좌표 포함 여부 미확인) https://www.data.go.kr/data/15041677/openapi.do . **1차 대체원: OA-21208 도보 네트워크 노드(①과 같은 스키마 → 노드 유형 코드로 지하철 출입구 노드 추출, 지하철역코드로 역 매칭)**; 보조: 수치지형도 지하철 출입구 심볼, ②의 출입구번호 목록으로 전수 검증. |
| 서울시 역사마스터 정보 OA-21232 | 서울시 | DB, OpenAPI | 역사_ID·호선·좌표 | 수시(2026-02-27) | 즉시 | 공공누리 1유형 | 파일 없음, API/시트만. https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do |
| 서울시 버스정류소 위치정보 OA-15067 | 서울시 미래첨단교통과 | XLSX/CSV, OpenAPI | 정류소 포인트(X,Y) | 수시(2026-09-02) | 즉시 | 공공누리 1유형 | NODE_ID, ARS_ID(5자리; CSV에서 앞 0 탈락 주의), 정류소타입. 페이지에 "WGS84(EPSG-5179)"로 모순 표기 → 실제 좌표 단위 확인 필요. https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do |
| 서울시 버스노선별 정류장별 시간대별 승하차 OA-12913 | 서울시 | CSV(월별), OpenAPI | 노선×정류장(표준정류장ID, ARS), 시간대 00–23 | 월간(익월 5일) | 즉시 | 공공누리 1유형 | 2015~, 교통카드 기준(현금 제외). https://data.seoul.go.kr/dataList/OA-12913/S/1/datasetView.do |
| 서울시 지하철호선별 역별 승하차 OA-12914 | 서울시 | CSV, OpenAPI | 역, 일별 | 일별 | 즉시 | 공공누리 1유형 | 2015~. https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do |
| 전국 버스정류장 위치정보 `_20251031` | 국토교통부(TAGO) | CSV(EUC-KR), OpenAPI XML/JSON | 206,022건 포인트, **WGS84** | 연간 | 즉시 | 제한 없음 | NODE_ID, NODE_NM, GPS_LATI/LONG, CITY_CD. BIS 연계 지자체만 포함. https://www.data.go.kr/data/15067528/fileData.do |
| (TAGO) 버스정류소정보 API | 국토교통부 | REST | — | — | 확인 필요 | — | 제목만 확인. https://www.data.go.kr/data/15098534/openapi.do |
| 따릉이 대여소 마스터 OA-21235 | 서울시(TOPIS) | DB, OpenAPI | 대여소 포인트(위도·경도) | 수시(2026-02-27) | 즉시 | 공공누리 1유형 | https://data.seoul.go.kr/dataList/OA-21235/S/1/datasetView.do ; T-data API `TaimsTbOprStation/1.0`(월 1회, apikey) https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1044 |
| KTDB GTFS 기반정보(2023-03 기준) | 한국교통연구원 국가교통DB | GTFS | 전국 8개 수단 정류장·노선·시간표 | 비정기 | **자료신청**(정보공개>자료신청>교통망 GIS DB>대중교통) | — | 접근성 지표 분석용 시범자료. 누구나 신청 가능. https://www.ktdb.go.kr/www/selectBbsNttView.do?key=45&bbsNo=2&nttNo=3764 , https://www.ktdb.go.kr/www/contents.do?key=202 |
| 버스 노선 형상(링크 지오메트리) | — | — | — | — | **확인 필요(소스 미발견)** | — | 5절은 정류소 포인트·승하차만 확보. 2026-10-07 data.go.kr 키워드 검색으로 서울 버스 노선 선형 데이터셋 미발견(열린데이터광장 검색은 WebFetch로 동작하지 않음). 대체: 노선별 정류소 순번을 연결한 근사 선형, 또는 T-data 노선정보 확인. 노선도 시트가 실제로 필요할 때만 추진. |

## 6. 보행·자전거

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 서울시 자치구별 도보 네트워크 공간정보 OA-21208 | 서울시 미래첨단교통과 | CSV(자치구별), 코드표 xlsx | 노드·링크, **WGS84**, 2020 기준 | 매일 1회(2026-02-27) | 즉시 | 공공누리 1유형 | 보행자도로·횡단보도·육교·정류장·지하철 출입구 포함. 보행 네트워크 분석(Space Syntax 류)의 기반. https://data.seoul.go.kr/dataList/OA-21208/S/1/datasetView.do |
| 서울시 교통안전시설물 횡단보도 정보 OA-15554 | 서울시 교통운영과 | DB/ZIP, OpenAPI | 포인트+속성, **EPSG:5186** | 월간(매월 1일; 2026-10-01) | 즉시 | 공공누리 1유형 | 노드ID·종류·폭·길이·신호등 유무. **검증 시 2회 연속 `서비스 지연(103)`, curl 재시도로만 성공 — 좌표계·갱신주기는 HTML meta로만 확인됨, 컬럼 상세는 재검증 필요.** https://data.seoul.go.kr/dataList/OA-15554/S/1/datasetView.do |
| 전국횡단보도표준데이터 | 국토교통부·경찰청(55개 지자체 제공) | CSV/XLS/JSON/XML/RDF, OpenAPI | 포인트(위도·경도) 24항목 | 반기(2025-07-10) | 즉시 | — | 보행자신호등·녹색시간·음향신호기·점자블록·조명 유무. 서울 제공 여부는 55개 기관 목록에서 확인 필요. https://www.data.go.kr/data/15028201/standard.do |
| 전국어린이보호구역표준데이터 | 경찰청·교육부(227개 기관) | 파일, OpenAPI(자동승인) | 포인트(위도·경도) | 반기(2026-09-22) | 즉시 | — | CCTV 대수·도로폭. https://www.data.go.kr/data/15012891/standard.do |
| 생활안전지도 도로시설(횡단보도, WMS) | 행정안전부 | **WMS** | 국토지리정보원 횡단보도 레이어 | 실시간 | 개발 자동 / 운영 심의 | 제한 없음 | XML은 시군구 통계만, 공간은 WMS만. https://www.data.go.kr/data/15101840/openapi.do |
| 자전거도로 공간정보 | 서울시 | — | — | — | **불가(공식 공간데이터 미발견)** | — | 2026-10-07 data.go.kr 검색 결과 서울 관련은 '서울특별시_자전거 길 안내지도'(15051884, 2019, txt/pdf)뿐, SHP·좌표 데이터셋 미발견. 수치지형도 자전거도로 레이어 또는 디지타이징으로 대체. 열린데이터광장 직접 검색은 103 지연으로 미수행. 검색: https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=서울 자전거도로 |

## 7. 교통량

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 서울특별시 지점별 일자별 교통량 OA-22819 | 서울시 미래첨단교통과 | DB, OpenAPI | 관측지점×일×방향×시간대 | 월간(2025-11-20 개시) | 즉시 | 공공누리 1유형 | 파일 없음, API 수집. https://data.seoul.go.kr/dataList/OA-22819/S/1/datasetView.do |
| 서울특별시_교통량 이력 정보 API (지점정보·교통량) | 서울시 | REST JSON/XML | 지점(좌표 포함)·방향·차로 | 실시간 | 즉시(자동승인) | 제한 없음 | 열린데이터광장 인증키. https://www.data.go.kr/data/15056899/openapi.do ; 지점정보 OA-13314 https://data.seoul.go.kr/dataList/OA-13314/S/1/datasetView.do |
| 서울시 교통량 정보(조사 보고서) OA-15064 | 서울시(TOPIS) | **PDF**(최근), XLS/ZIP(과거) 2005–2024 | 간선·도시고속도로 지점 | 연간(2025-03-06) | 즉시 | 공공누리 1유형 | 도심 24·시계 38·교량 21개소 검지기(언론·TOPIS 설명). 표 추출 필요. https://data.seoul.go.kr/dataList/OA-15064/F/1/datasetView.do |
| 국가교통DB 교통분석자료(여객·화물 O/D, 교통량, 분석용 네트워크, 교통주제도) | 한국교통연구원 | SHP 등(형식 미표기) | 존·링크 | 연간 | **자료신청**(자료선택→신청서→만족도조사→다운로드, "누구나") | — | https://www.ktdb.go.kr/www/contents.do?key=202 ; 요약 파일 https://www.data.go.kr/data/15117884/fileData.do |
| 교통량정보제공시스템(road.re.kr) | 국토교통부·건설기술연구원 | — | 국도·고속도로 지점 AADT | — | 확인 필요(TLS 인증서 오류로 미열람) | — | 서울 시내도로는 대상 아님(일반적 사실, 확인 필요). http://www.road.re.kr/ |

## 8. 공원·녹지

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 전국도시공원정보표준데이터 | 국토교통부(233개 지자체) | CSV/XLS/JSON/XML/RDF, OpenAPI | 포인트(위도·경도)+공원면적 | 연간(2026-06-22) | 즉시 | — | 공원구분 값 어린이공원·근린공원·소공원·수변·체육·문화·역사·기타는 **샘플 데이터에서 관찰된 값**이며 표준의 허용값 목록 원문이 아님(페이지는 '공공데이터 제공 표준 전문 참고'로 안내) → 묘지공원·도시자연공원 등 포함 여부 확인 필요. 미조성 제외. 폴리곤 아님. https://www.data.go.kr/data/15012890/standard.do |
| 서울시 도시계획시설(공간시설) 공간정보 OA-21129 (`UQ153_..._202609.zip`) | 서울시 도시계획상임기획과 | **SHP** | 공원·녹지·광장·유원지·공공공지 폴리곤, **EPSG:5174(Bessel TM)** | 수시/월간(2026-10-03) | 즉시 | 공공누리 1유형 | 법적 효력 없음 고지. 보유 도시계획시설 DB와 중복 가능 — 갱신본 비교용. https://data.seoul.go.kr/dataList/OA-21129/S/1/datasetView.do |
| 서울시 가로수 위치 정보(경도, 위도) OA-22904 | 서울시 정원도시국 조경과 | XLSX(12.63MB) | 포인트, 자치구·노선·수종 | 연간(2026-04-20) | 즉시 | **공공누리 4유형(출처표시+상업적 이용금지+변경금지)** | **상용 배포물에 번들 불가.** 사용자 직접 다운로드 흐름으로 분리. https://data.seoul.go.kr/dataList/OA-22904/A/1/datasetView.do |
| 서울시 보호수 및 노거수 위치정보 OA-318(ITRF2000) / WGS84판 | 서울시 조경과 | MAP/SHP(검색 색인 기준) | 포인트 | — | 즉시(페이지 103 오류로 세부 미확인) | 공공누리(유형 확인 필요) | https://data.seoul.go.kr/dataList/OA-318/S/1/datasetView.do |
| 서울시 생활권계획 생활권경계 공간정보 OA-15527 | 서울시 도시계획상임기획과 | SHP(CP949) | 권역·지역생활권 폴리곤, **EPSG:5174** | 비정기(2026-10-03) | 즉시 | 공공누리 1유형 | 2018 생활권계획 체계. 분석 범위 설정용. https://data.seoul.go.kr/dataList/OA-15527/A/1/datasetView.do |
| 서울특별시_생태현황도(개별비오톱 평가도) 공간정보 | 서울시 | **SHP** | 비오톱 폴리곤, **EPSG:5174(Bessel TM)** | 수시(수정 2025-08-19) | 즉시(로그인 불요) | 공공누리 1유형 | 비오톱 유형·평가등급(보전가치) — 녹지·생태 분석의 표준 레이어. 도시계획시설(공간시설)·생활권경계와 같은 5174 → 변환 파이프라인 공유. https://www.data.go.kr/data/15125731/fileData.do |
| 환경부 토지피복지도 — 대분류 7종·30m / 중분류 22종·5m(최신 2024) / 세분류 41종·1m(최신 2025) | 환경부 환경공간정보서비스 | SHP·PDF | 전국 폴리곤(분류별 해상도) | 분류별(중분류 2024, 세분류 2025) | **로그인·자료신청**(환경공간정보서비스) | 확인 필요 | 토지이용 현황도·녹지율·불투수면 분석용. 구 egis.me.go.kr은 aid.mcee.go.kr로 301 이관. https://aid.mcee.go.kr/intro/land.do |

## 9. 생활SOC (교육·보육·의료·공공시설)

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 전국 병의원 및 약국 현황 `_20251231` | 건강보험심사평가원 | XLSX(병원·약국·상세 3개 API 스냅샷) | 포인트(좌표X·Y), 종별·의사수·개설일 | 수시(분기·연말 스냅샷) | 즉시 | 공공누리 1유형 | https://www.data.go.kr/data/15051059/fileData.do ; API: 병원정보서비스 https://www.data.go.kr/data/15001698/openapi.do |
| 어린이집 기본정보 (전국) | 한국사회보장정보원 | XLS | 포인트(**위도·경도 포함**), 정원·현원·보육실·CCTV·통학차량 | 수시(자동 갱신) | 즉시 | 제한 없음 | 파일명 `_20220710`(메타 기준일 주의). API판 "어린이집별 기본정보 조회" https://www.data.go.kr/data/15101154/openapi.do . https://www.data.go.kr/data/15083298/fileData.do ; 원 포털 OPEN API는 개발계정→운영계정 심사 https://info.childcare.go.kr/info/oais/openapi/OpenApiSlL.jsp |
| 유치원알리미 Open API (일반현황 `api/notice/basicInfo2.do`) | 교육부 | REST(key, sidoCode, sggCode) | 포인트(**위도·경도 항목 33–34**) | 수시 | **SNS 로그인**으로 키 발급 | 출처표시 시 상업적 이용 허용 | 최근 3년치만. 14개 항목(건물·교실면적·통학차량 등). https://e-childschoolinfo.moe.go.kr/openApi/openApiList.do |
| 학교알리미 공시정보 API | 한국교육학술정보원 | LINK형 JSON | 학교(주소; **좌표 미확인**) | 실시간 | 개발 자동 / 운영 심의 | **공공누리 3유형(변경금지)** | 학생·교원·시설·급식 등 2008~. https://www.data.go.kr/data/15098092/openapi.do |
| NEIS 학교기본정보 (`schoolInfo`) | 교육부·시도교육청 | REST JSON/XML | 학교(도로명주소; 좌표 미표기) | 주간 | 즉시(인증키) | — | 지오코딩 필요. https://open.neis.go.kr/portal/data/service/selectServicePage.do?infId=OPEN17020190531110010104913&infSeq=2 |
| 전국초등학교통학구역표준데이터 | 교육부(제공: 한국교육시설안전원) | CSV/XLS/JSON/XML/RDF, OpenAPI `tn_pubr_public_elesch_atndskl_zn_api` | 학구 폴리곤("도면", 공간객체ID; 지오메트리 인코딩 방식 확인 필요) | 수시(2026-10-06) | 즉시 | — | 학구ID·학구명·학구분류(0 단독/1 공동)·교육지원청. 뷰어: https://schoolzone.emac.kr/ . https://www.data.go.kr/data/15021149/standard.do |
| 전국주차장정보표준데이터 | 국토교통부(250개 기관) | 파일, OpenAPI | 포인트(위도·경도), 구획수·요금·운영시간 | 반기(2026-04-20) | 즉시 | — | https://www.data.go.kr/data/15012896/standard.do |
| 기타 표준데이터셋(총 300종, 포털 기준) | 행정안전부 개방표준 | 파일, OpenAPI | 대부분 포인트(위도·경도) | 반기~연간 | 즉시 | — | 전국CCTV https://www.data.go.kr/data/15013094/standard.do , 공중화장실 https://www.data.go.kr/data/15012892/standard.do , 공공시설개방정보 https://www.data.go.kr/data/15013117/standard.do , 신호등 15028198, 지역아동센터 15129438, 주유소 15129441 등. 목록: https://www.data.go.kr/tcs/dss/selectDataSetList.do?dType=STD&keyword= |

## 10. 역사문화·경관

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 국가유산청_문화재 공간 정보 (OpenAPI + SHP) | 국가유산청 디지털정보담당 | OpenAPI XML; **SHP는 gis-heritage.go.kr 데이터개방>파일다운로드**; WMS/WFS | 지정문화재 약 15,000건(2023) 구역·보호구역 폴리곤 | 실시간 | 즉시(자동승인) | 제한 없음 | https://www.data.go.kr/data/3070426/openapi.do , 지도: https://gis-heritage.go.kr/newMap.do |
| 역사문화환경 보존지역 내 건축행위 허용기준 데이터(2023 개방목록) | 국가유산청 | **SHP, 행정구역별** | 허용기준 구역 폴리곤 | 연 1회 개방목록 공지 | 즉시(gis-heritage 파일다운로드) | — | 2023-07-14 공지. 이후 연도 개방 여부 확인 필요. https://cha.go.kr/cop/bbs/selectBoardArticle.do?bbsId=BBSMSTR_1045&mn=NS_03_09_01&nttId=86290&pageUnit=0 |
| Vworld WMS/WFS 2.0 — `lt_c_uo301` 국가유산 지정/보호구역, `lt_c_uq121` 경관지구, `lt_c_uq123` 고도지구, `lt_c_uq124` 방화지구, `lt_c_uo101` 교육환경보호구역, `lt_c_ud801` 개발제한구역 | 국토교통부 | WMS/WFS(`api.vworld.kr/req/wms`, `/req/wfs`; WFS maxfeatures 기본 1000) | CRS: EPSG:4326/3857/5179/5181/5186 등 | — | 즉시(인증키, domain) | — | 보유 용도지구 DB와 교차검증용. https://www.vworld.kr/dev/v4dv_wmsguide2_s001.do |
| 서울시 용도지구(경관지구) 공간정보 OA-21127 (`UQ121_..._202602.zip`) | 서울시 도시계획상임기획과 | SHP | 폴리곤 | 수시 | 즉시 | 공공누리 1유형 | 보유 DB와 중복 — 갱신 비교용. https://data.seoul.go.kr/dataList/OA-21127/S/1/datasetView.do |
| **경관 중점경관관리구역도** (역사도심·한강변·주요산 주변) | 서울시(2016 서울특별시 경관계획, 페이지 수정 2026-04-03) | **PDF**(중점경관관리구역도 활용방법, 가이드라인 HWP/PDF) | — | — | **불가(공간데이터 미개방)** | — | 2024/2025 재정비판 언급 없음 → 2016 계획이 현행으로 보임(확인 필요). 디지타이징 필요. https://news.seoul.go.kr/citybuild/archives/533012 , https://urban.seoul.go.kr/view/html/PMNU3080000001 |

## 11. 정비·개발사업

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 서울시 재개발 재건축 정비사업 현황 OA-2253 | 서울시 주거정비과 | — | — | — | **종료**("해당 데이터는 종료된 서비스입니다" 표기. 페이지의 종료일 필드는 접근일과 같은 날짜가 찍혀 동적 표시로 보여 날짜 인용은 생략) | — | 대체 소스는 아래 정보몽땅. https://data.seoul.go.kr/dataList/OA-2253/F/1/datasetView.do |
| 정비사업 정보몽땅 — 사업장검색 | 서울시 | 웹 표 + **엑셀다운로드** | 자치구·사업구분·사업장명·**대표지번**·진행단계(폴리곤·면적 없음) | 수시 | 즉시(로그인 불요) | — | 약 1,177개 사업장(추진주체구성전 122/추진위 218/조합 780/청산 57, 2026-10-07). 대표지번→PNU 조인으로 포인트화 가능. https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do |
| 신속통합기획 재개발 공모 선정구역 | 서울시 정보몽땅 | 웹 목록 + **위치도 이미지** | 구역명·자치구·면적·용도지역 (좌표·폴리곤 없음) | 수시 | **불가(공간데이터 없음)** | — | 1차 21, 2차 23, 수시선정 약 100, 취소 3(약 144). https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanArea.do |
| 모아타운 대상지 | 서울시 | — | — | — | **불가** | — | 공공데이터포털·열린데이터광장 검색에서 데이터셋 미발견(2026-10-07). 보도자료·공고 PDF 기반 수작업. |
| 도시재생 사업 현황정보 | 국토교통부 도시재생종합정보체계 | 웹 표·정적 지도 이미지 | 사업유형·선정연도·지자체 | 연간(2026년 34곳) | **불가(다운로드·SHP 없음)** | — | https://www.city.go.kr/portal/business/newDeal/statusInfo/link.do |
| Vworld `lt_c_ud601` 주거환경개선지구, `lt_c_ud610` 국민임대주택, `lt_c_ud620` 보금자리주택 | 국토교통부 | WMS/WFS | 폴리곤 | — | 즉시 | — | 정비구역(도시정비법) 폴리곤은 **보유 용도구역 DB(토지이용계획 지역지구)에 포함 여부 먼저 확인** — 포함 시 별도 수집 불필요. https://www.vworld.kr/dev/v4dv_wmsguide2_s001.do |

## 12. 재해·안전

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 서울시 침수흔적도 OA-15636 | 서울시 치수안전과 | **SHP(연도별 zip) 2010–2025** | 침수 폴리곤(원인·일시·침수심) | 비정기(2026-04-27) | 즉시 | 공공누리 1유형 | **2015·2021년은 침수 없음으로 파일 없음.** 포털 미러: https://www.data.go.kr/data/15133406/fileData.do . https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do |
| 서울시 풍수해 침수예상도 공간정보 | 서울시 데이터전략과 | **SHP, CP949, EPSG:5186** | 침수 단계별 폴리곤 | 페이지 수정일 2025-12-04('자동 갱신' 표기) / **데이터 기준일은 파일명 `_20231203`** — 페이지 수정일과 데이터 기준일을 구분해 기록할 것 | 즉시 | 공공누리 1유형 | 열린데이터광장 OA-21172 동일. https://www.data.go.kr/data/15125748/fileData.do |
| 산사태위험지도 | 산림청 | **래스터(SHP 미구축)** 10m 격자, 1~5등급 | 전국 산림 | 연 1회 | **신청**: map.forest.go.kr → 산림공간정보 다운로드 → 무료신청 → **일반인 신청** | 제한 없음 | **2025년판만 제공**, 과거판(2013·2019·2022~2024)은 정보공개청구. https://www.data.go.kr/data/15074817/fileData.do , Q&A: https://www.forest.go.kr/newkfsweb/cop/bbs/selectBoardArticle.do?nttId=3215640&bbsId=BBSMSTR_1351&mn=KFS_02_04_07_02&orgId=fgis |
| 급경사지 현황 `_20260630` | 행정안전부 | CSV, OpenAPI | **37,778건**, 지번·도로명 주소(좌표 미확인 → PNU 조인) | 연간(차기 2027-07-01) | 즉시(로그인 불요) | 제한 없음 | 사유 급경사지 제외. 좌표 포함 API: 공유플랫폼_지역급경사지 https://www.data.go.kr/data/15139709/openapi.do . https://www.data.go.kr/data/15083292/fileData.do |
| 생활안전지도(safemap.go.kr) | 행정안전부 | 웹지도, Open API, data.go.kr WMS 다수 | 8분야 130개 레이어(침수흔적·하천범람·도시침수·지진 등) | 실시간 | 개발 자동 / 운영 심의 | 제한 없음 | https://www.mois.go.kr/frt/sub/a06/b10/safemap/screen.do |

## 13. 환경(소음·대기)

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| S-DoT 환경정보 OA-15969 / 실시간 OA-22833 | 서울시 디지털도시국 정보통신과 | CSV(주간), OpenAPI | **1,170개 센서**(설치위치 xlsx 별도), 1시간 min/max/avg | 실시간 | 즉시 | 공공누리 1유형 | 온도·습도·조도·소음·진동·자외선·PM2.5·풍향·풍속·흑구온도. **PM10은 환경규정상 미제공**, "개인 연구" 인용 조건. https://data.seoul.go.kr/dataList/OA-15969/S/1/datasetView.do |
| 에어코리아 대기오염정보 API + 측정소정보 API(`getMsrstnList`, dmX/dmY WGS84) | 한국환경공단 | REST JSON/XML | 측정소 포인트, 실시간/일 | 실시간 | 개발 자동(**500건/일**) / 운영 심의 | **출처표시·변경금지** | PM10·PM2.5·O3·NO2·CO·SO2·통합지수. **축 주의: 측정소정보의 dmX/dmY는 필드명과 반대로 예시값 dmX=37.57(위도), dmY=127.00(경도)** → 수집기에서 값 범위로 위도/경도 자동 판별. https://www.data.go.kr/data/15073861/openapi.do , https://www.data.go.kr/data/15073877/openapi.do |
| 서울시 도로교통 소음 측정정보 OA-15473 | 서울시 보건환경연구원 | TXT/XLSX(반기 zip) | **4개 지점**(시청·신사·신촌·성수), 1시간 Leq 주/야 | 반기(2026-09-01) | 즉시 | 공공누리 1유형 | 지점 수가 적어 면적 분석 불가 — 참고치. https://data.seoul.go.kr/dataList/OA-15473/S/1/datasetView.do |
| 국가소음정보시스템 소음지도 | 기후에너지환경부·한국환경공단 | 웹(실시간 측정망 지도) | 측정망 지점 | 분기·반기 확정치 | 다운로드·API **미확인** | — | 전국 측정망 2,005지점(환경부 844·지자체 1,161)은 `[언론]` 한경 2020-06-24 기준. 전략소음지도(3D) 개방 여부 확인 필요. https://www.noiseinfo.or.kr/ |

## 14. 기상·야간조명

| 데이터 | 제공처 | 형태·포맷 | 공간단위·좌표계 | 갱신 | 접근 | 라이선스 | 비고·출처 |
|---|---|---|---|---|---|---|---|
| 지상(종관, ASOS) 시간자료 조회서비스 (`apis.data.go.kr/1360000/AsosHourlyInfoService/getWthrDataList`) | 기상청 | REST JSON/XML | 관측소(stnIds), 시간 | 실시간(전일까지) | 즉시(자동승인, 10,000건/일) | 공공누리 1유형 | ta 기온·ws 풍속·wd 풍향·ss 일조·icsr 일사·hm·rn. **1904-04~**(지점별 상이). 바람장미·일조 통계의 1차 소스. https://www.data.go.kr/data/15057210/openapi.do ; 지점정보 https://www.data.go.kr/data/15139439/openapi.do |
| 기상청 API허브 (apihub.kma.go.kr) | 기상청 | REST, `disp=0`이면 CSV | 지상·해양·고층·레이더·위성·수치모델 등 13분류 | 실시간 | 즉시(**회원가입 시 인증키 자동 발급**, 마이페이지 확인) | — | 일일 호출 한도는 안내 PDF에 미기재 → 확인 필요. https://apihub.kma.go.kr/ , 사용방법 PDF https://apihub.kma.go.kr/static/file/기상청_API허브_사용_방법_안내.pdf |
| 서울시 가로등 위치 정보 OA-22205 | 서울시 도시기반시설본부 설비부 | CSV(0.65MB) | 포인트(위도·경도), 등주형태·등기구·광원 | 주기없음(2023-12-21) | 즉시 | 공공누리 1유형 | 용량상 시 관리분(간선) 위주로 추정 — 자치구 관리 가로등 포함 여부 확인 필요. https://data.seoul.go.kr/dataList/OA-22205/F/1/datasetView.do |
| VIIRS Black Marble VNP46A3 (월별 야간광) | NASA LAADS DAAC | HDF5(약 58MB/타일) | 15 arc-sec(~500m) 전지구 | 월간, 2012-01~ | **Earthdata 로그인** | 공개(DOI 10.5067/VIIRS/VNP46A3.002) | 야간 활동 강도 레이어. 일별 VNP46A1/A2, 연간 VNP46A4 동일 계열. https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP46A3 |

---

## 15. 공통 인프라 메모 (구현 시 전제)

| 항목 | 내용 |
|---|---|
| 포털 상태 | 서울 열린데이터광장: 2026-10-07 간헐적 `서비스 지연(103)`(OA-21235·22904·13314·2253·318·15527·1180·15473·15572 중 다수가 1회 이상 실패, 재시도 시 성공; 검증 단계에서도 OA-15554가 WebFetch 2회 연속 103 → curl 재시도로만 성공). nsdi.go.kr: DNS 미해석. KOSIS openapi 루트: SSO 리다이렉트(문서는 data.go.kr 페이지로 대체). T-data: 10045는 비로그인 직접 다운로드(`download.do?id=11056`) 확인. 환경부 egis.me.go.kr → aid.mcee.go.kr 301 이관. |
| 인증키 종류 | (a) data.go.kr 1개 키로 다수 API(자동승인/심의 구분), (b) 서울 열린데이터광장 키(`openapi.seoul.go.kr:8088/{KEY}/...`), (c) T-data apikey(별도), (d) SGIS consumer key→accessToken, (e) Vworld 키(domain 등록), (f) KMA API허브 authKey, (g) 유치원알리미 SNS 로그인 키, (h) Earthdata 토큰. |
| 좌표계 분포 | EPSG:5179(SGIS 경계 — 문서 명시 없음, 예제 좌표 기준; Vworld 가능), **5186**(공시지가·토지소유 SHP, 횡단보도, 침수예상도), **5181**(상권영역), **5174 Bessel**(서울 도시계획시설·생활권경계·**생태현황도**), 4326(대부분 포인트 CSV, 도보 네트워크·리프트 위치정보). **좌표계 미표기**: T-data 10045 역 좌표(값 범위상 FN 500,000 중부원점 계열 추정). **축 뒤바뀜**: 에어코리아 dmX=위도/dmY=경도. 수집 단계에서 전부 EPSG:5186 또는 5179로 통일 권장. |
| 인코딩 | 전국 버스정류장 CSV EUC-KR, 서울 SHP 다수 CP949(Windows-949), 소진공 CSV UTF-8. |
| 식별자 조인 키 | PNU(공시지가·토지소유·급경사지 지번, 상가 storeListInPnu, 건물에너지 sigunguCd+bjdongCd+bun+ji), 법정동코드(실거래가 LAWD_CD 5자리), 집계구코드/격자ID(인구), 행정동코드 8자리(SGIS adm_cd·주민등록인구), 표준정류장ID·ARS_ID(버스; T-data 10045 정류장ID로 출입구–정류장 매핑), 역사_ID(지하철; 10045 지하철역ID·도보 네트워크 지하철역코드와의 대응은 확인 필요), 상권_코드(상권분석). |
| 재배포 가능 라이선스 | 공공누리 1유형·"제한 없음" = 가공·재배포 가능. **4유형(가로수)·3유형(학교알리미)·변경금지(에어코리아)**는 플러그인 번들 금지 → 사용자 다운로드 유도. |

## 16. 시트별 분류 — 즉시 / 준비 필요 / 불가 (상세)

**즉시 (인증키 자동승인 또는 무로그인 파일)**
- 인구: SGIS 경계·통계 API, 생활인구 250m(OA-23019~), 수도권 생활이동, K-apt 단지 API, 주민등록인구 통계(jumin.mois.go.kr·data.go.kr 파일 — 포맷 확인 필요)
- 상권: 소진공 상가 CSV·API, 상권분석 영역·추정매출·길단위인구, S-DoT 유동, 실시간 도시데이터
- 지가·거래: 서울 개별공시지가 OA-1180, 실거래가 API 11종
- 건물: 건축HUB 건축물대장 10종, 건축HUB 건물에너지정보 API, 건물에너지 전기·가스 벌크 XLSX
- 교통: 서울 버스정류소·승하차(버스·지하철), 역사마스터 API, 전국 버스정류장, 따릉이 마스터, 교통량 이력 API·지점별 일자별 교통량, 지하철 출입구–정류장 매핑 CSV(T-data 10045, 무로그인·출입구 좌표 없음)
- 보행: 도보 네트워크, 횡단보도(서울·전국), 어린이보호구역
- 공원: 전국도시공원 표준, 도시계획시설(공간시설) SHP, 생활권경계, 생태현황도(비오톱 평가도) SHP
- SOC: 병의원·약국 XLSX, 어린이집 기본정보 XLS, 통학구역 표준, 주차장·CCTV·화장실·신호등 표준, NEIS(좌표 없음)
- 역사: 국가유산 SHP·WMS/WFS, 역사문화환경 허용기준 SHP, Vworld 경관·고도지구
- 정비: 정보몽땅 사업장 엑셀(대표지번)
- 재해: 침수흔적도·침수예상도 SHP, 급경사지 CSV, 생활안전지도 WMS(개발)
- 환경: S-DoT 환경정보, 서울 도로교통소음
- 기상: ASOS 시간자료 API, KMA API허브, 가로등 CSV

**준비 필요 (로그인·신청·심의)**
- 데이터마켓 로그인: 개별공시지가·토지소유 SHP/CSV(시도별; 토지소유는 컬럼 정의서·최신본 날짜 확인 선행), 기타 737종
- 국토정보플랫폼 로그인: 국토통계지도 격자 인구
- 서울시 통합 로그인(T-data): 지하철역 좌표 마스터(data_id=36; 페이지 표기 기준) — 출입구 CSV(10045)는 로그인 불요로 확인돼 여기서 제외
- 운영단계 심의: 공시지가·토지소유 WMS/WFS, 에어코리아 운영계정, 학교알리미 운영계정, 생활안전지도 WMS 운영
- 자료신청: KTDB 교통량·O/D·네트워크·GTFS
- 산림청 무료신청(일반인): 산사태위험지도 2025 래스터
- 환경공간정보서비스 로그인·자료신청: 환경부 토지피복지도(중분류 5m·세분류 1m SHP)
- SNS 로그인: 유치원알리미
- Earthdata 로그인: VIIRS
- 라이선스 격리(번들 금지): 가로수(4유형), 학교알리미(3유형), 에어코리아(변경금지)

**불가 (공간데이터 미개방 → PDF·웹 목록 디지타이징)**
- 경관 중점경관관리구역도(PDF)
- 신속통합기획 선정구역(위치도 이미지), 모아타운 대상지(데이터셋 없음), 도시재생 사업지(웹 표·정적 지도)
- 서울 재개발·재건축 정비사업 현황 OA-2253(서비스 종료) — 정보몽땅 엑셀로 대체
- 자전거도로 선형(data.go.kr에 SHP·좌표 데이터셋 없음 — 디지타이징 또는 수치지형도 대체)
- 지하철 출입구 포인트 좌표(공식 전수 데이터셋 미확인 — 도보 네트워크 OA-21208 노드로 대체), 버스 노선 선형(소스 미발견)
- 전략소음지도(개방 미확인)

## 17. 확인 필요 / 미해결

1. 서울 생활인구 250m 격자ID → 지오메트리 변환 규칙(국가표준격자 체계) 및 격자 경계 파일 제공처.
2. 국토교통부 실거래가 API의 정확한 서비스 경로(신청 후 활용가이드로 확인) 및 2025-09-30 "대체서비스 안내 125종" 원문 공지.
3. 소진공 상가정보 전국 건수(약 200만)·분류체계 수치의 1차 출처 문구.
4. 서울 버스정류소 위치정보(OA-15067) 좌표계 표기 모순("WGS84(EPSG-5179)") — 실제 값 단위 확인.
5. 전국횡단보도표준데이터 55개 제공기관에 서울 자치구 포함 여부.
6. 역사문화환경 허용기준 SHP의 2024·2025년 개방목록 공지 존재 여부.
7. 2016 서울특별시 경관계획 이후 재정비판(2024/2025) 고시 여부.
8. 보유 용도구역 DB에 정비구역(도시정비법)·역사문화환경보존지역 레이어 포함 여부(포함 시 11·10절 일부 수집 불필요).
9. KMA API허브 일일 호출 한도, KOSIS 1회 40,000셀 제한의 1차 출처.
10. 국가소음정보시스템 측정망 원자료 다운로드·API 제공 여부, 서울시 전략소음지도 개방 여부.
11. 서울 가로등 CSV(0.65MB)의 관리 주체 범위(시 관리분만인지).
12. 서울 자전거도로 공간정보: data.go.kr 검색에서는 '서울특별시_자전거 길 안내지도'(15051884, 2019, txt/pdf)뿐 → '불가'로 분류 완료. 열린데이터광장 직접 검색은 103 지연으로 미수행(잔여 확인).
13. 급경사지 현황 CSV의 좌표 컬럼 유무(주소만이면 PNU 조인).
14. 보호수 OA-318 세부 컬럼·라이선스(103 오류로 미확인).
15. nsdi.go.kr → vworld 데이터마켓 이관의 공식 공지.
16. 지하철 출입구 포인트 좌표의 공식 전수 소스 — OA-21208 도보 네트워크 노드의 '노드 유형 코드'에 지하철 출입구 유형이 있는지, 출입구번호가 속성에 있는지 실데이터로 확인. 국가철도공단 역사별 출구정보 API(15041677)의 좌표 포함 여부.
17. T-data 10045 '지하철역X/Y좌표'의 좌표계(값 범위상 FN 500,000 중부원점 계열 추정) 및 data_id=36 역사마스터의 실제 로그인 요건.
18. 토지소유정보(dsId=12) 컬럼 정의서(소유구분 컬럼 유무·코드표)와 데이터마켓 실제 최신본 날짜(등재본 2024-04-08).
19. 개별공시지가 전국 건수 기준(data.go.kr 159,935,632 vs 데이터마켓 38,378,643/790,263,935)의 의미.
20. 도로명주소 전자지도(business.juso.go.kr: 건물·도로구간·기초구역 SHP)의 메뉴·포맷·갱신주기 — 사이트가 JS 렌더링이라 curl/WebFetch로 미확인. 건물명·도로명 라벨과 도로 선형의 전국 무료 소스로 베이스맵에 중요(기본도 문서 범위이나 여기서 플래그).
21. 버스 노선 선형(링크 지오메트리) 소스 — 정류소 순번 연결 또는 T-data 노선정보로 대체 가능 여부.
22. 환경부 토지피복지도 자료신청 절차·소요기간·라이선스(aid.mcee.go.kr).
23. 주민등록인구 행정동·월별·연령별 통계의 다운로드 포맷(jumin.mois.go.kr CSV/XLS 여부; data.go.kr 15046954는 HWP).
24. 전국도시공원정보표준데이터 '공원구분' 허용값 전문(표준 전문 확인; 묘지공원·도시자연공원 포함 여부).
25. SGIS 경계 API 실 응답의 좌표계(문서 미명시; 예제 좌표는 UTM-K 범위).
26. 건물에너지 벌크의 갱신주기·라이선스, 가스에너지 데이터셋(15054213) 페이지 열람.
27. 열린데이터광장 의존 행(OA-15554 등)의 컬럼 상세 재검증(103 지연으로 HTML meta만 확인된 항목).

## 18. 출처 목록 (모두 접근일 2026-10-07)

공식 문서
- SGIS 개발지원센터: https://sgis.mods.go.kr/developer/html/newOpenApi/api/intro.html , https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/census.html , https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/addressBoundary.html
- KOSIS 통계자료 조회 서비스: https://www.data.go.kr/data/15127755/openapi.do
- 서울 생활인구: https://data.seoul.go.kr/dataList/OA-14979/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-14991/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-23019/S/1/datasetView.do , https://data.seoul.go.kr/dataVisual/seoul/seoulLivingPopulation.do
- 수도권 생활이동: https://data.seoul.go.kr/dataVisual/seoul/capitalRegionLivingMigration.do
- 국토통계지도 인구: https://www.data.go.kr/data/15059921/fileData.do
- 주민등록인구: https://jumin.mois.go.kr/ , https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=서울 주민등록인구 행정동
- K-apt 단지 목록: https://www.data.go.kr/data/15057332/openapi.do
- 소진공 상가정보: https://www.data.go.kr/data/15083033/fileData.do , https://www.data.go.kr/data/15012005/openapi.do
- 서울 상권분석: https://data.seoul.go.kr/dataList/OA-15560/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-15572/A/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-15568/S/1/datasetView.do
- 실시간 도시데이터: https://www.data.go.kr/data/15146211/openapi.do
- S-DoT: https://news.seoul.go.kr/gov/archives/539344 , https://data.seoul.go.kr/dataList/OA-15969/S/1/datasetView.do
- 개별공시지가: https://www.data.go.kr/data/15052266/fileData.do , https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=6 , https://www.data.go.kr/data/15124014/openapi.do , https://data.seoul.go.kr/dataList/OA-1180/S/1/datasetView.do
- 실거래가: https://www.data.go.kr/data/15126469/openapi.do
- 토지소유정보: https://www.data.go.kr/data/15045905/fileData.do , https://www.data.go.kr/data/15123976/openapi.do , https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=12
- 건축HUB: https://www.data.go.kr/data/15134735/openapi.do
- 건물에너지: https://www.data.go.kr/data/15135963/openapi.do , https://www.data.go.kr/data/15054214/fileData.do
- 데이터마켓: https://www.vworld.kr/dtmk/dtmk_ntads_s001.do
- 대중교통: https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=36 , https://t-data.seoul.go.kr/dataprovide/trafficdataviewfile.do?data_id=10045 , https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-15067/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-12913/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-12914/S/1/datasetView.do , https://www.data.go.kr/data/15067528/fileData.do , https://data.seoul.go.kr/dataList/OA-21235/S/1/datasetView.do , https://t-data.seoul.go.kr/dataprovide/trafficdataviewopenapi.do?data_id=1044
- 지하철 출입구 관련(검증 추가): https://t-data.seoul.go.kr/dataprovide/download.do?id=11056 (10045 CSV 직접 다운로드 경로) , https://www.data.go.kr/data/15098149/fileData.do , https://www.data.go.kr/data/15082999/fileData.do , https://www.data.go.kr/data/15041677/openapi.do , 검색: https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=서울 지하철 출입구
- KTDB: https://www.ktdb.go.kr/www/contents.do?key=202 , https://www.ktdb.go.kr/www/selectBbsNttView.do?key=45&bbsNo=2&nttNo=3764 , https://www.data.go.kr/data/15117884/fileData.do
- 보행: https://data.seoul.go.kr/dataList/OA-21208/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-15554/S/1/datasetView.do , https://www.data.go.kr/data/15028201/standard.do , https://www.data.go.kr/data/15012891/standard.do , https://www.data.go.kr/data/15101840/openapi.do
- 자전거도로 검색: https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=서울 자전거도로
- 교통량: https://data.seoul.go.kr/dataList/OA-22819/S/1/datasetView.do , https://www.data.go.kr/data/15056899/openapi.do , https://data.seoul.go.kr/dataList/OA-13314/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-15064/F/1/datasetView.do
- 공원·녹지: https://www.data.go.kr/data/15012890/standard.do , https://data.seoul.go.kr/dataList/OA-21129/S/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-22904/A/1/datasetView.do , https://data.seoul.go.kr/dataList/OA-15527/A/1/datasetView.do
- 생태·토지피복: https://www.data.go.kr/data/15125731/fileData.do , https://aid.mcee.go.kr/intro/land.do
- 생활SOC: https://www.data.go.kr/data/15051059/fileData.do , https://www.data.go.kr/data/15083298/fileData.do , https://info.childcare.go.kr/info/oais/openapi/OpenApiSlL.jsp , https://e-childschoolinfo.moe.go.kr/openApi/openApiList.do , https://www.data.go.kr/data/15098092/openapi.do , https://open.neis.go.kr/portal/data/service/selectServicePage.do?infId=OPEN17020190531110010104913&infSeq=2 , https://www.data.go.kr/data/15021149/standard.do , https://schoolzone.emac.kr/ , https://www.data.go.kr/data/15012896/standard.do , https://www.data.go.kr/tcs/dss/selectDataSetList.do?dType=STD&keyword=
- 역사·경관: https://www.data.go.kr/data/3070426/openapi.do , https://cha.go.kr/cop/bbs/selectBoardArticle.do?bbsId=BBSMSTR_1045&mn=NS_03_09_01&nttId=86290&pageUnit=0 , https://www.vworld.kr/dev/v4dv_wmsguide2_s001.do , https://news.seoul.go.kr/citybuild/archives/533012 , https://urban.seoul.go.kr/view/html/PMNU3080000001
- 정비·개발: https://data.seoul.go.kr/dataList/OA-2253/F/1/datasetView.do , https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do , https://cleanup.seoul.go.kr/cleanup/view/publicIntgrPlanArea.do , https://www.city.go.kr/portal/business/newDeal/statusInfo/link.do
- 재해: https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do , https://www.data.go.kr/data/15133406/fileData.do , https://www.data.go.kr/data/15125748/fileData.do , https://www.data.go.kr/data/15074817/fileData.do , https://www.forest.go.kr/newkfsweb/cop/bbs/selectBoardArticle.do?nttId=3215640&bbsId=BBSMSTR_1351&mn=KFS_02_04_07_02&orgId=fgis , https://www.data.go.kr/data/15083292/fileData.do , https://www.mois.go.kr/frt/sub/a06/b10/safemap/screen.do
- 환경: https://www.data.go.kr/data/15073861/openapi.do , https://www.data.go.kr/data/15073877/openapi.do , https://data.seoul.go.kr/dataList/OA-15473/S/1/datasetView.do , https://www.noiseinfo.or.kr/
- 기상·야간: https://www.data.go.kr/data/15057210/openapi.do , https://apihub.kma.go.kr/ , https://data.seoul.go.kr/dataList/OA-22205/F/1/datasetView.do , https://ladsweb.modaps.eosdis.nasa.gov/missions-and-measurements/products/VNP46A3

언론·2차 출처
- `[언론]` 한국경제 2020-06-24, 전국 소음측정망 2,005지점: https://www.hankyung.com/article/202006243009Y
- 2차: PublicDataReader 문서(실거래가 서비스 11종·KOSIS 셀 제한): https://github.com/WooilJeong/PublicDataReader/blob/main/assets/docs/portal/TransactionPrice.md
- 비공식 재게시: 공공데이터포털 오픈API 대체서비스 안내(125종, 2025-09-30): https://www.scribd.com/document/926853673/

## 검증 이력

**2026-10-07 — 1차 검증 반영.** 검증은 WebSearch 세션 한도(200회) 소진으로 전부 WebFetch·curl 직접 열람(원문 HTML grep 포함)으로 수행했고, 모든 판정은 1차 출처 페이지 원문 기준이다. 반영 과정에서 T-data 10045 CSV 헤더(curl, 2,788,890바이트), data.go.kr 검색 결과와 리프트·캐노피·국가철도공단 출구정보 페이지, jumin.mois.go.kr 접속은 다시 직접 확인했다.

| 구분 | 항목 | 조치 |
|---|---|---|
| refuted | SGIS 집계구 경계 API 파라미터(§0-1, §1) | statsarea.geojson은 accessToken·adm_cd(8자리)만 받음으로 정정. year(2000–2025)·low_search는 hadmarea.geojson 전용으로 분리 기재. 좌표계는 '경계 API 절 미명시, 예제 좌표가 UTM-K 범위, 지오코딩 API는 EPSG:5179 명시 → 실 응답 확인 권장'으로 완화. 응답 properties(base_year, sido_cd, sgg_cd, emdong_cd, adm_cd, adm_nm, addr_en, x, y) 추가. |
| refuted | T-data 10045 지하철 출입구 CSV(§0-4, §0 표, §5, §16) | '서울시 통합 로그인 필요' → '로그인 불요(비로그인 curl 200)'로 정정. '출입구 포인트' → '역 좌표만 포함, 출입구 좌표 없음'으로 정정. '유일한 공식 소스' 문구 삭제. 출입구 포인트 좌표는 §5 신규 행(확인 필요)과 §17-16으로 분리하고 1차 대체원을 OA-21208 도보 네트워크 노드로 명시. 재확인 중 발견한 각 필드 앞 U+FEFF(BOM) 파싱 주의 추가. |
| unverifiable | 토지소유정보 벌크 컬럼 5종(§0-3, §4) | 포맷·갱신·행수·링크는 유지. 소유구분코드 등 컬럼명 5종은 data.go.kr·vworld 어디에도 없음 → '컬럼 정의서(로그인 후 다운로드) 확인 필요'로 표기. '연간' 갱신은 메타 표기일 뿐 등재본 _20240408·차기 2025-11-01 경과 미갱신임을 명시. |
| 과장 | §0 결론 '12종은 공식 개방데이터만으로 바로 구성 가능' | '구성 가능(일부 로그인·자료신청 필요)'로 수정, 검증에서 드러난 공백(출입구 좌표·자전거도로) 추가. |
| 모호 | 침수예상도 갱신(§12) | 페이지 수정일(2025-12-04)과 데이터 기준일(_20231203) 구분. |
| 모호 | OA-2253 종료일(§11) | 접근일과 같은 동적 날짜로 보여 날짜 인용 삭제. |
| 모호 | 도시공원 표준 공원구분 8종(§8) | '샘플에서 관찰된 값, 허용값 원문 아님' 명시, 확인 필요 추가(§17-24). |
| 추가 발견 | 개별공시지가 건수(§0-3, §3) | data.go.kr 159,935,632 vs 데이터마켓 38,378,643/790,263,935 병기. |
| 추가 발견 | 에어코리아 dmX/dmY 축(§13, §15) | dmX=위도·dmY=경도 예시값 주의 추가. |
| 추가 발견 | 소진공 상가 API 오퍼레이션(§0-2, §2) | 5개 → 15개(기반경로 /B553077/api/open/sdsc2) 전체 나열, storeListInPnu의 필지DB 조인 가치 명시. |
| 추가 발견 | OA-15554 103 지연(§0-7, §6, §15) | 검증 중 재현 사실 기록, 컬럼 상세 재검증 필요 표기. |
| 누락 보강 | 생태현황도(비오톱 평가도) SHP, 환경부 토지피복지도(§0 표, §8, §16) | 신규 행 추가(출처 포함). |
| 누락 보강 | 건축HUB 건물에너지정보 API·전기/가스 벌크(§0 표, §4, §16) | 신규 행 2개 추가. 가스에너지 15054213은 페이지 미열람으로 확인 필요. |
| 누락 보강 | 주민등록인구(§0-1, §0 표, §1, §16) | 신규 행 추가. jumin.mois.go.kr 접속·메뉴 확인, 다운로드 포맷은 확인 필요. |
| 누락 보강 | 도로명주소 전자지도, 버스 노선 선형(§5, §17) | '확인 필요' 항목으로 추가. |
| 미해결 확정 | 자전거도로(§0 표, §6, §16, §17-12) | data.go.kr 검색 결과 SHP 없음 → '불가(디지타이징·수치지형도 대체)'로 분류. |
