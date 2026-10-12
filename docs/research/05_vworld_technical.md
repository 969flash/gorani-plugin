# 05. 브이월드(V-World) 기술 조사 — 건물·도로·지형·수계 자동 생성의 데이터 기반

- 작성일 / 모든 URL 접근일: **2026-10-07** — 같은 날 2차 검증 결과를 반영한 수정판(변경 내역은 문서 끝 「검증 이력」)
- 범위: (1) 2D 데이터 API 전체 레이어·필드·호출 제한, (2) 국가중점데이터·공간정보 다운로드(벌크), (3) 수치지형도 다운로드·도엽 체계, (4) 지형(DEM) 소스 비교·추천, (5) 3D 건물 데이터 사용 조건, (6) WMS/WMTS 배경지도, (7) 로컬 1차 자료(수치지형도 SHP·표준코드 CSV)로 확인한 레이어 코드표
- 출처 표기: **[공식]** vworld.kr·ngii.go.kr·law.go.kr·data.go.kr·공식 SDK 코드 / **[실측]** 2026-10-07에 본 프로젝트의 V-World 인증키(`.env`)·curl로 직접 호출해 확인 / **[로컬]** 사용자 보유 파일에서 확인 / **[블로그]** 제3자 글 / **[언론]** 기사. 열어서 확인하지 못한 것은 "확인 필요".
- 조사 제약: WebSearch 한도(200회) 소진 후에는 WebFetch·curl·law.go.kr DRF(OC=test)만 사용. V-World 게시판 상세는 `brdIde` 파라미터로만 열림(URL 패턴은 게시판 JS에서 확인).

---

## 0. 요약

### 결론 한 줄
**건물·도로·수계·행정경계·용도지역은 2D 데이터 API(`https://api.vworld.kr/req/data`) 한 벌로 즉시 생성 가능하고, 지형만은 V-World가 아니라 국토지리정보원 연속수치지형도 등고선·표고점(데이터마켓 벌크 SHP, V-World 표기 CC BY, **다운로드 시 로그인 요구 여부는 확인 필요**)으로 가야 한다.** V-World 3D(DEM 타일·facility_build)는 엔드포인트가 지금도 살아 있지만 법적으로 '공개제한 공간정보'라 플러그인에 쓸 수 없다.

> **법적 단서(§4.3, 검증 반영)**: 국토지리정보원 보안관리규정 별표 1은 공개 지도라도 "인터넷·내비게이션·휴대폰 등을 통해 좌표와 1:5,000 축척 이상 지도의 등고선·표고값 표시 불가"로 규정한다. 한국 축척 표기에서 '1:5,000 이상'은 1:5,000을 포함하므로, 1순위로 추천한 1:5,000 등고선·표고점을 **웹/클라우드형 뷰어나 온라인 공유 베이스맵에 올리면 저촉될 수 있다**. 데스크톱 Rhino 플러그인 내부 처리·3dm/AI 파일 납품은 '인터넷 표시'가 아니라는 해석이 필요하며, V-World 데이터마켓의 CC BY 배포와 별표 1 표시 제한이 어떻게 양립하는지는 **확인 필요**(국토지리정보원·V-World 고객센터 서면 질의 권장). 그때까지 등고선·표고값은 온라인 기능에서 제외하는 것을 기본값으로 둔다.

### 레이어별 추천 소스

| 생성 대상 | 1차 소스(즉시, API) | 벌크/보조 소스 | 비고 |
|---|---|---|---|
| 건물 footprint + 층수·높이·용도 | 2D 데이터 API `LT_C_BLDGINFO` (MultiPolygon, 필드 13개: bld_nm·usability·grnd_flr·ugrnd_flr·height·archarea·totalarea·platarea·bc_rat·vl_rat·useapr_day·strct_cd) | GIS건물통합정보 SHP(데이터마켓 dsId=18, 전체 월간·변동 일간, CC BY) / 건물통합정보_마스터(dsId=30524, `F_FAC_BUILDING_시도_시군구.zip`, **CC BY-NC-ND**) | 서울을 덮는 BOX(126.76,37.43,127.18,37.70 — 고양·성남·구리 등 경기 일부 포함) 1회 조회 = 1,161,721건·1,162페이지 [실측], **서울 건물 수가 아님**. 높이 0인 건물은 층수×층고로 대체하거나 건축HUB 건축물대장 표제부 `heit`·`grndFlrCnt`(§1.6)로 보정 |
| 도로(면·중심선) | `LT_L_N3A0020000` 연속수치지형도 도로중심선(차로수 `rdln`, 도로폭 `rvwd`, 도로구분 `rddv`) / `LT_L_MOCTLINK` 교통링크(도로등급·제한속도) / `LT_C_UPISUQ151` 도시계획도로(계획선) | 연속수치지형도 **도로경계_면**(dsId=30179, 전국 2 zip, 연간, EPSG:5179) | API에는 도로경계 '면'이 없음 → 베이스맵 도로면은 벌크 또는 중심선 ± 폭/2 버퍼. 대안 후보: 도로명주소 전자지도(juso.go.kr — 도로구간·실폭도로·건물 폴리곤, §2.1 **확인 필요**) |
| 필지 | 기존 DB(토지특성정보) 유지. 보조: `LP_PA_CBND_BUBUN` (pnu·jibun·jiga) | 연속지적도형정보(dsId=23, SHP/CSV, 월간·일간) | 기존 자산 그대로 |
| 수계(하천·호수) | `LT_C_WKMSTRM` 하천망(레퍼런스 표기 POLYGON, **실응답 MultiPolygon**; riv_nm·cat_nam) | 연속수치지형도 하천경계(30248)·실폭하천(30207)·하천중심선(30249)·호수/저수지(30256) | 중랑천·청계천·성북천 등 서울 도심 하천 폴리곤 확인 [실측 5건] |
| 지형 | **(API 없음)** | **연속수치지형도 등고선(dsId=30185, 1:5,000, 주곡선 5 m·계곡선 25 m) + 표고점(30245)** → Rhino TIN. 광역 컨텍스트는 Copernicus GLO-30(무로그인 S3, 한국 타일 존재 확인) | 서울 1:1,000 등고선·표고점은 '공개제한'(국토지리정보원 보안관리규정 별표1). 1:5,000 등고선·표고값도 '인터넷 등을 통한 표시 불가' 조항 대상 → 로컬 처리·파일 납품에 한정(§4.3) |
| 행정경계 | `LT_C_ADSIDO_INFO`/`LT_C_ADSIGG_INFO`/`LT_C_ADEMD_INFO` | 연속수치지형도 행정경계(30252~30254) | 코드로 단건 조회 가능(`attrFilter=sig_cd:=:11650`) |
| 용도지역·지구·구역, 도시계획시설, 지구단위계획 | `LT_C_UQ111`(도시지역: 용도지역명 uname) 등 UQ1xx, `LT_C_UPISUQ151~159`(도시계획시설), `LT_C_UPISUQ161`(지구단위계획), `LT_C_UD801`(개발제한구역) | 데이터마켓 '도시계획정보_○○(현황)' 시리즈(건축지정선·건축한계선·공공보행통로·차량출입불허구간 등, dsId 30064~30117, 월간, EPSG:5186, **CC BY-NC-ND**) | 공원·녹지는 수치지형도에 코드가 없고 UPIS 공간시설(UQ153)·도시자연공원구역(UQ162)에서 |
| 교통 노드·CCTV·정류장 | `LT_P_MOCTNODE`(교차점), `LT_P_UTISCCTV` | 연속수치지형도 정거장(30226)·플랫폼(30246) | **버스정류장·지하철역·철도 전용 레이어는 2D 데이터 API에 없음**(04b 문서의 서울 열린데이터광장·T-data로 보완) |
| 배경지도(래스터) | WMTS `https://api.vworld.kr/req/wmts/1.0.0/{key}/{Base\|Satellite\|Hybrid\|midnight\|white}/{z}/{y}/{x}.{png\|jpeg}` | — | TileMatrixSet은 EPSG:3857 `GoogleMapsCompatible` 하나뿐, z 6–19(레퍼런스는 white·midnight를 6–18로 적지만 Capabilities 실측은 5개 레이어 모두 6–19 세트 참조 — §6 각주), 256 px. `gray` 레이어는 현재 Capabilities에 없음. 플러그인(EPSG:5186)용 베이스맵 래스터는 재투영이 필요 없는 **WMS GetMap(crs=EPSG:5186)** 이 더 적합(§6) |

### 호출 제한·운영 규칙(핵심 수치)

| 항목 | 값 | 근거 |
|---|---|---|
| `size` | 1–1000 (2000 입력 시 `INVALID_RANGE`) | [공식] 레퍼런스 + [실측] |
| `page` | 1부터, 응답 `page.total`로 끝 판단 | [공식]+[실측] |
| `geomFilter` BOX 크기 | **제한 없음** — 서울을 덮는 BOX(126.76,37.43,127.18,37.70)도 OK. 1페이지 응답 15.3 s(1차) → 6.2 s·5.7 s(재실측)로 **가변, 참고치**; 0.06°×0.05° 박스 0.5 s | [실측] |
| `crs` | 응답 좌표계이자 geomFilter 좌표계 — `crs=EPSG:5186`이면 BOX도 5186 좌표로 입력 | [실측] |
| 일일 호출 한도 | 지오코더만 40,000건/일. 그 외 API는 FAQ 원문대로 "지오코더 API 이외 API에서는 **별도의 일일 제한량이 없으나, 부하 테스트 등 무리하게 호출이 많을 경우 일시적으로 차단될 수 있습니다**". `OVER_REQUEST_LIMIT`(level 2, "서비스 사용량이 일일 제한량을 초과") 오류코드는 TMS뿐 아니라 **2D 데이터 API 레퍼런스에도 정의**돼 있음 → 임계치는 비공개, "확인 필요" | [공식] FAQ(bodIde=52)·Geocoder·TMS·2D 데이터 API 레퍼런스(svcIde=adsido·n3a0020000) |
| 도메인 | 비브라우저(서버·플러그인)에서는 인증키 발급 시 등록한 URL을 `domain` 파라미터로 보냄. FAQ: URL은 "외부에서 접근 가능한 주소"를 등록. 현재 프로젝트 키의 등록 URL은 `http://localhost:8080` [로컬 .env] → 배포본에 내장 불가, 사용자별 키 필요(§1.7) | [공식]+[로컬] |
| 인증키 종류 | 개발키(연구·개인·QGIS 등 외부 SW 사용)·운영키('실제로 운영하고 있는 서비스'에만 발급). 운영키 연장은 유선(1661-0115), 개발키는 재발급. 유효기간 수치는 FAQ 본문에서 확인되지 않음(§8-3) | [공식] FAQ |
| 국가중점데이터 API(`/ned/`) | 트래픽 999,999,999/일, `numOfRows`·`maxFeatures` 최대 1000 | [공식] |

### 지형(DEM) 최종 추천 순위
1. **연속수치지형도 등고선 + 표고점(1:5,000)** — V-World 데이터마켓 표기 CC BY·무료·연 1회 전국 SHP. 다운로드 시 **로그인 요구 여부는 확인 필요**(§2·§8-1; 목록 페이지는 '로그인 후 모든 서비스 이용'만 안내). 5 m 주곡선이라 도시설계 현황도(경사·단면)에는 충분. 단 별표 1 '1:5,000 축척 이상 등고선·표고값 인터넷 표시 불가' 조항 때문에 **데스크톱 처리·3dm/AI 납품에 한정**하고 웹 뷰어·온라인 공유 베이스맵에는 올리지 않는다(§4.3, CC BY 배포와의 양립 여부 확인 필요). 1:1,000 등고선(1 m)은 공개제한이라 배포형 툴에 넣을 수 없다.
2. **Copernicus DEM GLO-30** — DSM(건물·수목 포함)·30 m·EGM2008. `s3://copernicus-dem-30m/Copernicus_DSM_COG_10_N37_00_E127_00_DEM/…tif` HEAD 200 확인(로그인·AWS 계정 불필요). 광역 산세·단면 컨텍스트용. 수직기준(EGM2008)과 DSM 특성이 등고선(국가 수준면·지표고)과 다르므로 §4.2의 오프셋·수목고 보정 절차를 거친 뒤 접합한다.
3. SRTMGL1 v3(30 m, EGM96, 2000년 촬영) — Earthdata 로그인(.netrc 자동화 가능). Copernicus가 있으면 불필요.
4. 국토지리정보원 공개 DEM — '90 m'는 2015년 etnews 기사에만 근거하며 data.go.kr 15059920·국토정보플랫폼 공식 페이지에는 해상도 미기재 → 현행 사양(해상도·형식·범위) **확인 필요**(국토정보플랫폼 로그인 후 '공개DEM' 메타데이터). 로그인·수동 다운로드·IMG. 90 m가 맞다면 해상도 부족.
5. V-World DEM 타일(`xdworld.vworld.kr …?Layer=dem`) — 엔진 전용·공개제한. **사용 금지**.
6. 국토지리정보원 5 m DEM·건물높이DB — 공개제한, 보안심사 후 공문 신청. 1인 개발·배포형 툴에는 부적합.

---

## 1. 2D 데이터 API(`/req/data`, WFS 성격)

### 1.1 요청 규격 [공식] (출처: https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=adsido)

- URL: `https://api.vworld.kr/req/data` (GET). 비브라우저·HTTPS 환경은 `domain=등록URL` 추가.

| 파라미터 | 필수 | 기본값 | 값 |
|---|---|---|---|
| `service` | – | data | data |
| `version` | – | 2.0 | 2.0 |
| `request` | **M** | – | `GetFeature` / `GetFeatureType` |
| `key` | **M** | – | 인증키 |
| `data` | **M** | – | 레이어 ID (`LT_C_BLDGINFO` 등) |
| `geomFilter` | 조건부 | – | `POINT(x y)`, `LINESTRING(...)`, `POLYGON(...)`, `MULTIPOLYGON`, `BOX(minx,miny,maxx,maxy)` |
| `attrFilter` | – | – | `필드:연산자:값` (`=`, `>=`, `<=`, `<`, `>`, `<>`, `BETWEEN`, `LIKE`, `IN`), 여러 조건은 `\|` 구분 |
| `columns` | – | 전체 | 반환 컬럼 |
| `geometry` / `attribute` | – | true | true/false |
| `buffer` | – | 0 | geomFilter 확장 거리(m) |
| `crs` | – | EPSG:4326 | EPSG:4326, 4019, 3857/900913, 5179(UTM-K), 5180–5188 |
| `size` | – | 10 | **1–1000** |
| `page` | – | 1 | 숫자 |
| `format` / `errorFormat` | – | json | json/xml |
| `callback` | – | – | JSONP |
| `domain` | 조건부 | – | 등록 URL |

- 필터 규칙: geomFilter 또는 attrFilter(단일검색 가능 필드) 중 하나 필수. 연속지적도는 둘 다 없으면 `emdCd`(읍면동코드) 필수 (출처: …?svcIde=cadastral).
- 응답 구조: `response.status`(OK/NOT_FOUND/ERROR), `record.total/current`, `page.total/current/size`, `result.featureCollection`(GeoJSON). 오류 예: `{"status":"ERROR","error":{"level":"1","code":"INVALID_RANGE","text":"size 파라미터의 값이 유효한 범위를 넘었습니다. 유효한 파라미터 값의 범위 : 1 ~ 1000"}}` [실측]. 레퍼런스 오류코드 표에는 `INVALID_KEY`·`INCORRECT_KEY`(발급 시 입력한 도메인 불일치)·`UNAVAILABLE_KEY`·**`OVER_REQUEST_LIMIT`(level 2, "서비스 사용량이 일일 제한량을 초과하여 더 이상 서비스를 사용할 수 없습니다")**·`SYSTEM_ERROR`·`UNKNOWN_ERROR`가 정의돼 있다 — 즉 FAQ의 '일일 제한량 없음'과 별개로 API 쪽에는 한도 초과 코드가 존재한다 [공식, svcIde=adsido·n3a0020000 2026-10-07 확인].

### 1.2 실측 결과 (2026-10-07, 본 프로젝트 키) [실측]

| # | 호출 | 결과 |
|---|---|---|
| 1 | `LT_C_BLDGINFO`, BOX 0.006°×0.006°(성수), size=1000 | OK, total 815, 1페이지, 0.3 s, MultiPolygon |
| 2 | `LT_C_BLDGINFO`, BOX 서울 전체(126.76,37.43,127.18,37.70) | OK, **total 1,161,721, page.total 1,162** → BOX 크기 제한 없음. 1페이지 응답 15.3 s(1차) → 6.2 s·5.7 s(재실측 2회): **가변, 참고치**. 이 BOX는 서울 행정경계를 넘어 고양·성남·구리 등 경기 일부를 포함 → **서울 건물 수로 인용 금지** |
| 3 | `LT_C_BLDGINFO`, BOX 0.06°×0.05° | OK, total 50,772, 51페이지, 0.5 s |
| 4 | `LT_C_BLDGINFO`, `crs=EPSG:5186`, BOX(203000,550500,203500,551000) | OK, total 691 → geomFilter는 `crs` 좌표계로 해석 |
| 5 | `LT_L_N3A0020000` 도로중심선, 성수 BOX | OK 378건, **MultiLineString**(레퍼런스 표기는 LINESTRING), 필드 `ufid, rdnu, name, rddv, pvqt, dvyn, rdln, rvwd, onsd, rest, rdnm, scls` |
| 6 | `LT_C_WKMSTRM` 하천망, 성동 일대 | OK 5건, **MultiPolygon**(레퍼런스 표기는 POLYGON), 필드 `riv_nm, cat_nam` |
| 7 | `LT_C_UPISUQ153` 도시계획(공간시설) | OK 75건, 필드 19개(`dgm_nm`=시설명, `dgm_ar`, `lcl_nam/mls_nam/scl_nam`, `excut_se` 집행여부 등) |
| 8 | `LT_L_MOCTLINK` 교통링크 | OK 62건, `link_id, road_name, max_spd, rd_rank_h, rd_type_h, rest_veh_h, rest_w, rest_h, remark` (차로수 없음) |
| 9 | `LP_PA_CBND_BUBUN` | OK 127건, `gosi_year, pnu, jibun, bonbun, bubun, addr, gosi_month, jiga` |
| 10 | `LT_C_UPISUQ161` 지구단위계획 | OK 14건 |
| 11 | `LT_L_SPRD` 도로명주소 도로 | OK, 필드 `rn` 하나뿐(도로폭 없음) |
| 12 | `size=2000` | ERROR `INVALID_RANGE` |

기존 수집 코드(`dev_plan_qa_univ_cases.py::_fetch_tile`)는 0.006° 타일 × size 1000 × page 반복 구조이며 `record.total`로 종료 판단한다 [로컬]. 서울을 덮는 BOX는 타일 분할 없이도 1,162페이지 순차 호출로 받을 수 있으나(6~15 s/page이면 약 2~5시간), FAQ가 "무리하게 호출이 많을 경우 일시적으로 차단"을 명시하고 레퍼런스에 `OVER_REQUEST_LIMIT`가 정의돼 있어 **전수 순차 호출은 차단 위험이 있다**. 전수 수집은 벌크 SHP(§2)로 하고, API는 대상지 BOX 단위 호출(페이지 간 sleep·백오프, `OVER_REQUEST_LIMIT`·`UNAVAILABLE_KEY` 시 중단)로 한정한다.
- 키 읽기 주의 [로컬]: `.env`는 2행(`VWORLD_API_KEY`)·5행(`PLAN_QA_NIGHT_DIR`) 값에 공백·한글 경로가 있어 `set -a; . .env`로 source하면 깨진다. `grep '^VWORLD_API_KEY=' .env | cut -d= -f2- | awk '{print $1}'` 처럼 grep/cut으로 읽거나 python-dotenv로 파싱할 것.

### 1.3 제공 레이어 전체 목록(158종) [공식]
출처: https://www.vworld.kr/dev/v4dv_2ddataguide2_s001.do (pageIndex=1~16 전부 열람, 상세는 `v4dv_2ddataguide2_s002.do?svcIde=<id>`).

| 분류 | 레이어 ID (svcIde) — 한글명 [갱신일] |
|---|---|
| 토지·지적 | `LP_PA_CBND_BUBUN`(cadastral) 연속지적도 [2026-09-21], `LT_C_LHZONE` 사업지구경계도, `LT_C_LHBLPN` 토지이용계획도, `LT_C_LANDINFOBASEMAP` LX맵 [2026-06-11] |
| 건물·주소 | **`LT_C_BLDGINFO`(bldginfo) 건축물정보 [2026-09-23]**, `LT_C_SPBD`(spbd) 도로명주소 건물, `LT_L_SPRD`(sprd) 도로명주소 도로 [2026-09-10] |
| 행정경계 | `LT_C_ADSIDO_INFO`(adsido) 광역시도, `LT_C_ADSIGG_INFO`(adsigg) 시군구, `LT_C_ADEMD_INFO`(ademd) 읍면동, `LT_C_ADRI_INFO`(adri) 리 [2026-09-10] |
| 교통 | `LT_L_MOCTLINK`(moctlink) 교통링크, `LT_P_MOCTNODE`(moctnode) 교통노드 [2026-09-21], **`LT_L_N3A0020000`(n3a0020000) 도로중심선(연속수치지형도) [2024-05-28]**, `LT_P_UTISCCTV` 교통CCTV, `LT_P_BYCRACKS` 자전거보관소 |
| 용도지역·지구·구역(UPIS UQ) | `LT_C_UQ111` 도시지역, `UQ112` 관리지역, `UQ113` 농림지역, `UQ114` 자연환경보전지역, `UQ121` 경관지구, `UQ123` 고도지구, `UQ124` 방화지구, `UQ125` 방재지구, `UQ126` 보호지구, `UQ128` 취락지구, `UQ129` 개발진흥지구, `UQ130` 특정용도제한지구, `UQ141` 국토계획구역, `UQ162` 도시자연공원구역, `LT_C_UD801` 개발제한구역, `LT_C_UMA100` 자연공원용도지구(WMS 목록) [2026-09-15~17] |
| 도시계획시설(UPIS) | `LT_C_UPISUQ151` 도로, `152` 교통시설, `153` 공간시설(공원·녹지·광장), `154` 유통공급시설, `155` 공공문화체육시설, `156` 방재시설, `157` 보건위생시설, `158` 환경기초시설, `159` 기타기반시설, **`161` 지구단위계획**, `171` 개발행위허가제한지역 [2026-09-17] |
| 기타 용도지역지구(UB/UD/UF/UH/UJ/UM/UO/UP) | `UB901` 시장정비구역, `UD601` 주거환경개선지구, `UD610` 국민임대주택, `UD620` 보금자리주택, `UF151` 산림보호구역, `UF602` 임업·산촌진흥권역, `UF901` 백두대간보호지역, `UH402` 자유무역지역, `UH501` 유통단지, `UH701` 벤처기업육성지역, `UJ401` 온천지구, `UM000` 가축사육제한구역, `UM221` 야생동식물보호, `UM301` 대기환경규제지역, `UM710` 상수원보호, `UM901` 습지보호지역, `UO101` 교육환경보호구역, `UO301` 국가유산보호도, `UO501` 전통사찰보존, `UO601` 관광지, `UP201` 재해위험지구, `UP401` 급경사재해예방지역 |
| 수자원 | **`LT_C_WKMSTRM` 하천망 [2023-06-09]**, `LT_C_WKMBBSN` 대권역, `WKMMBSN` 중권역, `WKMSBSN` 표준권역 |
| 학교·교육 | `LT_C_DESCH` 초등학교통학구역, `DMSCH` 중학교군, `DHSCH` 고등학교군, `EADIST` 교육행정구역 [2026-05-20] |
| 산업단지 | `LT_C_DAMDAN` 단지경계, `DAMYOD` 단지용도지역, `DAMYOJ` 단지시설용지, `DAMYUCH` 단지유치업종; `LT_C_WGISIEGUG/IENONG/IEILBAN/IEDOSI` 산업단지 4종 |
| 복지·문화·관광·산업 | `LT_P_MGPRTFA~D` 보호시설 4종, `LT_P_DGTOURISTINFO`, `LT_P_DGMUSEUMART`, `LT_P_TRADSIJANG`, `LT_P_BUSIINCUBATOR`, `LT_P_SMALLLIBRARY`, `LT_C_DGMAINBIZ` 주요상권, `LT_C_DOGPARK`, `LT_P_NSNMSSITENM` 국가지명 |
| 자연·지질·토양 | `LT_C_GIMSHYDRO`, `GIMSSTIFF`, `LT_L_GIMSEC`, `LT_C_GIMSLINEA`, `LT_L_GIMSLINEA`, `GIMSDEPTH`, `GIMSPOTEN`, `GIMSDIREC`, `GIMSFAULT`, `LT_C_GIMSSCS` 토양도, `LT_C_ASITSOILDRA/SURSTON/SOILDEP/DEEPSOIL`, `LT_C_FSDIFRSTS` 산림입지도, `LT_C_KFDRSSIGUGRADE` 산불위험, `LT_L_FRSTCLIMB` 등산로, `LT_C_AGRIXUE101/102` |
| 환경·수질 | `LT_P_WEISSITEMA/B/D/E/F` 수질측정망, `LT_P_SGISGWCHG`, `LT_P_SGISGOLF`, `LT_P_WEISPLAFACW` |
| 해양·연안 | `LT_C_WGISPL2USE/ABS/CON/SPA`, `WGISREPLAN`, `WGISRECOMP`, `WGISARWET`, `WGISNPGUG/GUN/DO` 자연공원, `LT_C_TFISMPA` |
| 항공 | `LT_C_AIS*` 22종, `LT_L_AISPATH` 등 |
| 재난 | `LT_C_USFSFFB` 소방서관할구역 |

- **없는 것**: 버스정류장·지하철역·철도선·공원 전용·건물 3D. WFS GetCapabilities(§1.5)에는 목록 페이지에 없는 `lt_p_cctv`, `lt_p_crosswalk`(횡단보도), `lt_p_shelter`, `lt_p_elevator`, `lt_p_safelight`, `dt_d002`(연속지적), `dt_d160`, `pmap_od_zone` 등이 추가로 보인다 [실측].

### 1.4 핵심 레이어 필드 [공식] (각 `v4dv_2ddataguide2_s002.do?svcIde=…`)

**건축물정보 `LT_C_BLDGINFO`** (svcIde=bldginfo): `bld_nm` 건물명, `dong_nm` 동명, `usability` 건물용도코드(예 14000), `strct_cd` 구조코드, `grnd_flr`/`ugrnd_flr` 지상/지하층수, `archarea` 건축면적, `height` 높이(m), `vl_rat` 용적률, `bc_rat` 건폐율, `totalarea` 연면적, `platarea` 대지면적, `useapr_day` 사용승인일(YYYYMMDD), `ag_geom` MULTIPOLYGON. geomFilter 또는 emdCd 필수. (PNU·건물관리번호는 필드 목록에 없음 → 필지 매칭은 공간조인 또는 국가중점데이터 `getBldgisSpceWFS`의 `pnu` 사용. 속성(높이·층수·용도·사용승인일) 보정은 건축HUB 건축물대장 표제부 §1.6.)

**연속지적도 `LP_PA_CBND_BUBUN`**: `pnu`(19자리, 단일검색 가능), `jibun`, `bonbun`, `bubun`, `addr`, `gosi_year`, `gosi_month`, `jiga`, `ag_geom`.

**교통링크 `LT_L_MOCTLINK`**: `link_id`(검색 가능), `road_name`, `max_spd`, `rd_rank_h` 도로등급(예 "시·군도"), `rd_type_h` 도로유형, `rest_veh_h`, `rest_w`, `rest_h`, `remark`. **교통노드 `LT_P_MOCTNODE`**: `node_id`, `node_name`, `nd_type_h`(도로교차점 등), `turn_type`.

**행정경계**: 시군구 `sig_cd`(검색), `full_nm`(검색), `sig_kor_nm`(검색), `sig_eng_nm`; 읍면동 `emd_cd`, `full_nm`, `emd_kor_nm`, `emd_eng_nm`; 광역시도 `ctprvn_cd`, `ctp_kor_nm`, `ctp_eng_nm`.

**도시지역 `LT_C_UQ111`**: `uname`(예 제1종일반주거지역), `sido_name`, `sigg_name`, `dyear`, `dnum`. **도시계획(도로) `LT_C_UPISUQ151`**: `present_sn`, `lclas_cl/mlsfc_cl/sclas_cl`, `atrb_se`, `dgm_nm`(예 소로3류), `dgm_ar`, `dgm_lt`, `grad_se`(소로/중로/대로), `road_ty`, `road_no`, `road_role`, `excut_se`(집행여부), `sig_nam`. **공간시설 `UQ153`**: `dgm_nm`(예 어린이공원), `dgm_ar` 등. **지구단위계획 `UQ161`**: `dgm_nm`(예 제1종지구단위계획구역), `dgm_ar`, `dgm_lt`, `ntfc_sn` 고시관리번호.

**하천망 `LT_C_WKMSTRM`**: 레퍼런스 `ag_geom`은 `POLYGON(...)`으로 표기되나 **실응답은 MultiPolygon** [실측]. `riv_nm`(검색), `cat_nam`(지방2급하천 등). 제공 한강홍수통제소.

**도로명주소 건물 `LT_C_SPBD`**: `bd_mgt_sn`(검색), `buld_nm`, `bul_eng_nm`, `gro_flo_co` 지상층수, `buld_nm_dc`, `sido`, `sigungu`, `rd_nm`, `buld_no`, `gu`. **도로명주소 도로 `LT_L_SPRD`**: `rn`만 제공.

**도로중심선 `LT_L_N3A0020000`**(출처 국토지리정보원 연속수치지형도): `ufid`, `rdnu` 도로번호, `name`, `rddv` 도로구분(코드 예 RDD009), `pvqt` 포장재질(RDQ005), `dvyn` 분리대유무(CSU002), `rdln` 차로수, `rvwd` 도로폭(m), `onsd` 일방통행(ITH002), `rest`, `rdnm` 도로명, `scls` 통합코드(예 A0023119). 레퍼런스 `ag_geom`은 `LINESTRING(...)`이지만 **실응답은 MultiLineString** [실측]. 분리대 필드명은 레퍼런스 원문·실응답 모두 `dvyn`("dvyn N CSU002 분리대 유․무" — 2026-10-07 레퍼런스 HTML 재확인; 검증 요약의 'dvqt'는 오독). **파서 규칙: 2D 데이터 API 도형은 레이어 불문 Multi\*(MultiPolygon/MultiLineString) 전제로 작성**하고, 단일 도형이 와도 깨지지 않게 `shapely.geometry.shape()` 후 `getattr(g, 'geoms', [g])` 순회로 통일한다. 코드값(RDD/RDQ/CSU/ITH)의 코드표는 데이터마켓 첨부 `연속수치지형도_데이터_설명서.pdf`(dsId=30179·30182 첨부) — 본 조사에서 열지 못함, **확인 필요**.

### 1.5 WMS/WFS 2.0·국가중점데이터 API [공식]+[실측]
- WMS `https://api.vworld.kr/req/wms?key=…`, WFS `https://api.vworld.kr/req/wfs?key=…` (출처: https://www.vworld.kr/dev/v4dv_wmsguide2_s001.do). 레이어 최대 4개/요청, WFS `maxfeatures` 기본·최대 1000, 출력 GML2/GML3/application/json, OGC Filter 1.1 지원. 문서 레이어 수 169(22분류).
- GetCapabilities 실측: **WFS FeatureType 187개**(DefaultSRS EPSG:4326), **WMS 레이어 375개**(스타일 변형 포함), WMS CRS = EPSG:3857/4019/4326/5174/5179/5180~5188/900913.
- 국가중점데이터 API(구 NSDI 오픈API, 115종): 속성 `https://api.vworld.kr/ned/data/<서비스>?key=…&pnu=…`, WFS `https://api.vworld.kr/ned/wfs/<서비스>`, WMS `https://api.vworld.kr/ned/wms/<서비스>` (출처: https://www.vworld.kr/dtna/dtna_guide_s001.do, 목록 https://www.vworld.kr/dtna/dtna_apiSvcList_s001.do, 상세 `dtna_apiSvcFc_s001.do?apiNum=N`).

| apiNum | 서비스 | URL | typename/주요 필드 |
|---|---|---|---|
| 18 | 토지특성속성조회 | `/ned/data/getLandCharacteristics` (pnu 필수, stdrYear, numOfRows≤1000) | pnu, ldCode, lndcgrCode, lndpclAr, prposArea1/2, ladUseSittn, tpgrphHgCode, tpgrphFrmCode, roadSideCode, pblntfPclnd |
| 17 | 토지특성WFS조회 | `/ned/wfs/getLandCharacteristicsWFS` | typename `dt_d194`, bbox(4326은 ymin,xmin,ymax,xmax), maxFeatures≤1000 |
| 76 | GIS건물통합WFS조회 | `/ned/wfs/getBldgisSpceWFS` | typename `dt_d010` (기준일 2026-10-06); 필드 gis_idntfc_no, **pnu**, buld_prpos_code, strct_code, ar, totar, hg(높이), use_confm_de, btl_rt, measrmt_rt |
| 92 | 연속지적도WFS조회 | `/ned/wfs/getCtnlgsSpceWFS` | typename `dt_d002`; pnu, lnm_lndcgr_smbol(지목), mnnm, slno |
| 25 | 개별공시지가속성조회 | `/ned/data/getIndvdLandPriceAttr` | pnu, stdrYear, pblntfPclnd(원/㎡), stdLandAt |
| 51 | 토지이용계획속성조회 | `/ned/data/getLandUseAttr` | prposAreaDstrcCode/Nm, cnflcAt(1 포함/2 저촉/3 접합) |
| 3 / 6 | 건축물연령 / 용도별건물 속성조회 | `/ned/data/getBuildingAge`, `/ned/data/getBuildingUse` | buldAge, groundFloorCo, undgrndFloorCo, **buldHg**(높이 m), mainPrposCode, buldTotar |

트래픽 표기는 전부 "999,999,999/일". 2025-04-07 공지 "국가중점 API 토지 소유 공간정보 사용량 제한 안내"는 토지소유정보 API의 대용량 호출로 호출 범위를 제한했다고만 적혀 있음(수치 없음).

### 1.6 건물 속성 보조 소스 비교 — 건축물대장 API 추가 [공식] (검증 반영: 누락 보완)
`LT_C_BLDGINFO`의 `height`가 0인 건물을 층수·높이·용도·사용승인일로 보정할 때 쓸 속성 소스 비교. footprint는 여전히 `LT_C_BLDGINFO`/GIS건물통합정보가 담당하고, 아래는 **속성 보강용**이다.

| 소스 | 엔드포인트 | 높이·층수·용도 필드 | 조회 키 | 호출 한도 | 라이선스 | 출처 |
|---|---|---|---|---|---|---|
| V-World 2D `LT_C_BLDGINFO` | `/req/data` | `height`, `grnd_flr`/`ugrnd_flr`, `usability`(코드), `useapr_day` | BOX/attrFilter(PNU 없음) | FAQ: 별도 제한 없음(과다 호출 시 일시 차단) | V-World 오픈API 약관 | §1.4 |
| V-World 국가중점 `getBuildingAge`/`getBuildingUse`(apiNum 3/6) | `/ned/data/…` | `buldHg`, `groundFloorCo`/`undgrndFloorCo`, `mainPrposCode`, `buldAge` | pnu | 999,999,999/일 표기 | – | §1.5 |
| **국토교통부_건축HUB_건축물대장정보 서비스** | `https://apis.data.go.kr/1613000/BldRgstHubService/{오퍼레이션}` — `getBrBasisOulnInfo`(기본개요)·`getBrRecapTitleInfo`(총괄표제부)·`getBrTitleInfo`(표제부)·`getBrFlrOulnInfo`(층별개요)·`getBrAtchJibunInfo`(부속지번)·`getBrExposPubuseAreaInfo`(전유공용면적)·`getBrWclfInfo`(오수정화시설)·`getBrHsprcInfo`(주택가격)·`getBrExposInfo`(전유부)·`getBrJijiguInfo`(지역지구구역) 10종 | 표제부(`getBrTitleInfo`) 응답 스키마에 **`heit` 높이(m)·`grndFlrCnt` 지상층수·`ugrndFlrCnt` 지하층수·`mainPurpsCdNm` 주용도코드명·`hhldCnt` 세대수·`useAprDay` 사용승인일** 등 포함 [공식 페이지 내장 OpenAPI 스펙 JSON, 2026-10-07 확인] | `sigunguCd`(5)·`bjdongCd`(5)·`platGbCd`(0 대지/1 산/2 블록)·`bun`·`ji` — PNU 19자리를 `pnu[0:5]`, `pnu[5:10]`, `pnu[10]`(PNU 1→대지 0, 2→산 1: 매핑 **확인 필요**), `pnu[11:15]`, `pnu[15:19]`로 분해 | **개발계정 10,000/일**, 운영계정은 활용사례 등록 시 증량; 개발·운영 모두 자동승인 | 이용허락범위 제한 없음·무료·월간 갱신(등록 2024-09-02, 수정 2026-07-10) | https://www.data.go.kr/data/15134735/openapi.do |

- 추천: 대상지 필지 PNU 목록 → 건축HUB 표제부 조회(필지당 1~N동) → `heit`(0이면 `grndFlrCnt`×층고) → `LT_C_BLDGINFO` footprint에 공간조인/PNU 매칭. 일 10,000건이면 대상지 단위(수백~수천 필지)에는 충분하고 서울 전수 보정에는 부족 → 전수는 GIS건물통합정보 SHP(`hg`)로.

### 1.7 배포형 플러그인의 인증키 운용 [공식 FAQ]+[로컬] (검증 반영: 누락 보완)
- FAQ(https://www.vworld.kr/v4po_brdfaq_s001.do?bodIde=52): 개발키는 연구·개인·외부 SW(QGIS 등) 용도, 운영키는 '실제로 운영하고 있는 서비스'에만 발급, 등록 URL은 '외부에서 접근 가능한 주소'. 인증키 유효기간 수치는 FAQ 본문에서 확인되지 않음(§8-3).
- 현재 프로젝트 키는 `VWORLD_API_DOMAIN`=`http://localhost:8080`으로 등록된 개발자 개인 개발키 [로컬 .env] → **배포본에 내장하면 안 된다**(발급 목적 외 사용 + 차단·만료 시 전 사용자 동시 중단). localhost 등록 키로도 발급·호출은 실제로 된다[실측]. 배포 사용자가 같은 방식으로 발급받아도 되는지는 **확인 필요**(FAQ 문구상 외부 접근 가능 주소 권고).
- 설계 반영 항목:
  1. 설정 UI에 **사용자별 V-World 인증키 + 등록 도메인** 입력란(건축HUB `serviceKey`도 같은 화면). 첫 실행 시 "vworld.kr 회원가입 → 오픈API 인증키 발급(개발키) → 키·URL 입력" 안내 링크.
  2. 키 보관: 사용자 홈의 플러그인 설정 파일(예 `~/.urbandesigntool/config.json`, 권한 0600) 또는 macOS Keychain. 3dm·SVG/AI·로그·DB에 키를 기록하지 않음.
  3. 오류 매핑: `INCORRECT_KEY`(도메인 불일치 → "등록 URL을 확인하세요"), `INVALID_KEY`, `UNAVAILABLE_KEY`, `OVER_REQUEST_LIMIT`(→ 당일 중단 안내), FAQ의 일시 차단(HTTP 오류·빈 응답) → 백오프 후 재시도 상한.
  4. 벌크 SHP(§2)를 로컬 DB로 미리 적재해 두면 일상 사용에서 API 호출량 자체를 줄일 수 있다(키 미입력 상태에서도 필지·건물·도로 기본 기능 동작).

---

## 2. 국가중점데이터·공간정보 다운로드(벌크)

- 구 국가공간정보포털(NSDI) 오픈마켓·국가중점데이터 다운로드는 **2023-12-31 V-World로 통합**(namu.wiki 인용, [블로그]; `data.nsdi.go.kr`는 2026-10-07 현재 DNS 미해결 [실측]). 현재 위치: https://www.vworld.kr/dtmk/dtmk_ntads_s001.do?svcCde=MK (총 737건, 74페이지; 상세 `dtmk_ntads_s002.do?dsId=…`).
- GIS건물통합정보 등 대용량 파일은 상세 페이지 문구상 "라온K 다운로드 솔루션" **설치가 필요합니다**('권장'이 아님). 목록 페이지(svcCde=MK)는 '로그인 후 디지털트윈국토의 모든 서비스를 이용'만 안내하고, 다운로드 버튼의 로그인 요구 여부는 본 조사·2차 검증 모두 확인하지 못함 → **확인 필요**(확인 방법: 비로그인 브라우저에서 `dsId=30185` 상세의 다운로드 버튼 클릭 → 로그인 페이지로 리다이렉트되는지 확인; 04b 문서의 '로그인 필요' 관찰과 대조).

| dsId | 데이터 | 포맷 | 단위 | 갱신 | 라이선스(V-World 상세 / data.go.kr — 출처별로 다를 수 있음) | 출처 |
|---|---|---|---|---|---|---|
| 4 (svcCde=NA) | 토지특성정보(+토지특성공간정보 SHP) | CSV·SHP | 전국/시도/시군구 필터 | 반기(5·11월), 기준일 2026-05-20 | V-World 상세: **'라이센스가 지정되어 있지 않습니다'** / data.go.kr 15048121: 이용허락범위 제한 없음·무료 | https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=4 ; data.go.kr 15048121 |
| 18 | GIS건물통합정보 | SHP(CSV) | 전국, 지역 필터 | 전체 월간·변동 일간, 14,422,486건·6,605 MB | CC BY(공공누리 1유형) | …?svcCde=NA&dsId=18 ; data.go.kr 15083092 |
| 23 | 연속지적도형정보 | SHP·CSV | 전국/시도 | 전체 월간·변동 일간 | V-World 상세: CC BY / data.go.kr 15125044: **제4유형(출처표시·상업적 이용금지·변경금지)** — 불일치 2026-10-07 재확인, 어느 표기가 유효한지 **확인 필요** | …?svcCde=NA&dsId=23 ; https://www.data.go.kr/data/15125044/fileData.do |
| 24 | 용도지역지구정보 | SHP·CSV | 전국/시도 | 전체 월간·변동 일간 | – | …?svcCde=NA&dsId=24 |
| 30524 (MK) | 건물통합정보_마스터 | SHP `F_FAC_BUILDING_충북_충주시.zip` 형식 | 시군구 | 변경발생시(2026-09) | **CC BY-NC-ND** | …?dsId=30524&svcCde=MK ; data.go.kr 15146873 |
| 30162 | (연속수치지형도) 건물 | SHP zip 10개(`건물_001`~`건물_010`, 각 200~240 MB; 상세 페이지 첨부 목록은 '총 12건'이나 나머지 2건은 설명서 등) | 전국 | 연간, 2026-10-01 | CC BY | …?dsId=30162 |
| 30179 | (연속수치지형도) 도로경계_면 | SHP 2 zip(738+944 MB) + 설명서 PDF | 전국 | 연간 | CC BY | …?dsId=30179 |
| 30182 | (연속수치지형도) 도로중심선 | SHP 8 zip(157~339 MB) | 전국 | 연간 | CC BY | …?dsId=30182 |
| 30185 | (연속수치지형도) 등고선 | SHP zip 20개(542~1,232 MB) + 메타데이터 xlsx 1개 | 전국 | 연간 | CC BY | …?dsId=30185 |
| 30245 / 30248 / 30249 / 30207 / 30256 | 표고점 / 하천경계 / 하천중심선 / 실폭하천 / 호수·저수지 | SHP | 전국 | 연간 | CC BY | 목록 pageIndex 8·11·12 |
| 30164 계단, 30168 교량, 30176 담장, 30181 도로분리대, 30214 옹벽, 30220 육교, 30221 인도(보도), 30223 입체교차부, 30226 정거장, 30229 주차장, 30234 철도경계, 30235 철도중심선, 30238 터널, 30246 플랫폼, 30252~30254 행정경계 | 연속수치지형도 지형지물 시리즈 | SHP | 전국 | 연간 | CC BY | 목록 pageIndex 6~12 |
| 30074 | 도로(현황) — 도시계획시설 | `C_UQ151.zip`(269 MB)+`Z_UPIS_C_UQ151.xlsx` | 전국 | 매월 | **CC BY-NC-ND** | …?dsId=30074 |
| 30065 / 30066 / 30077 / 30085 / 30086 / 30089 / 30097 / 30115 / 30117 | 건축지정선 / 건축한계선 / 공공보행통로 / 보행자우선도로 / 보행자전용도로 / 차량출입불허구간 / 벽면지정선 / 지구단위계획구역 / 획지선 (현황) | SHP `C_UQ163_AS.zip` 등, EPSG:5186 | 전국 | 매월 | **CC BY-NC-ND** | …?dsId=30065 등 |
| DAT_…123 / 125 / 203 / 204 / 215 | 수치표고모형 / 3차원 시설물 LoD4·LoD3·LoD1 / 건물높이DB | "3D" | – | – | 상세 페이지 비어 있음("등록된 데이터가 없습니다") | 목록 pageIndex 12 |

- 연속수치지형도 시리즈 좌표계: **GRS80 UTM-K (EPSG:5179)**; UPIS(도시계획) 시리즈: **GRS80 TM 중부 (EPSG:5186)** [공식 상세 페이지].
- 파일 명명 [로컬 확인]: 토지특성정보 `AL_D194_{시군구코드5자리}_{기준일YYYYMMDD}.shp/.dbf/.prj/.cpg` (예 `AL_D194_11110_20260520`), 용도지역지구 전국 `AL_D024_00_20260809.shp`(+`.fix`). 즉 `AL_{데이터코드 D###}_{지역코드(00=전국, 5자리=시군구)}_{기준일}`. WFS typename `dt_d194/dt_d010/dt_d002`가 같은 코드 체계.
- 데이터마켓 내 키워드 검색(`searchKeyword=`)은 0건을 반환해 동작하지 않음 → 목록 페이지 순회 또는 dsId 직접 지정.

### 2.1 비교표에 추가 검토할 V-World 외 소스 (검증 반영: 누락 보완)

| 소스 | 내용 | 상태(2026-10-07) |
|---|---|---|
| 도로명주소 전자지도(행정안전부, 주소기반산업지원서비스 `business.juso.go.kr`) | 도로구간·실폭도로·건물 폴리곤 등을 무료 월간 제공하는 것으로 알려짐 → 2D 데이터 API에 없는 **도로 '면'(실폭도로)** 의 대안 후보 | **확인 필요**: `https://business.juso.go.kr/`는 SPA(JS 렌더)라 curl로 메뉴·제공 조건을 읽지 못했고(`/addrlink/elctrnMapProvd/geoDBDwldList.do`는 404), 본 세션 WebSearch 한도 소진. 브라우저에서 '전자지도' 메뉴의 레이어 구성·포맷·좌표계·갱신주기·회원가입 요건을 확인할 것 |
| 서울시 S-Map 디지털트윈(https://smap.seoul.go.kr/) | 메인에 '오픈랩'·'3D라이브러리' 링크. 3D라이브러리(`https://smap.seoul.go.kr/smapModelLibrary.do`)는 "3D 건물을 지도에 배치해 볼 수 있습니다" — 브라우저 내 모델 배치 도구이며 데이터 다운로드 메뉴는 없음 [실측]. 오픈랩(https://openlab.eseoul.go.kr/)은 회원가입제 '개방형 실험실'로, 자유게시판에 'S-Map 3D 실외 입체모형 데이터 제공 신청 문의'(2026-09-02)·'3차원 지형 및 건물 데이터 제공 문의'(2026-09-18)·'항공 LiDAR 원시 점군자료 제공 문의'(2025-08-18) 글이 있어 데이터는 **신청·승인 방식**으로 보임 [실측] | 공개 다운로드·라이선스·포맷 **확인 필요**(오픈랩 문의처 openlab@xdworld.net). 3차원 좌표를 포함한 건물·지형은 §4.3 공개제한 분류와 충돌할 수 있어 배포형 플러그인 소스로는 보수적으로 본다 |

---

## 3. 수치지형도 다운로드·도엽 체계

### 3.1 다운로드 [공식]
- 국토정보플랫폼 국토정보맵: https://map.ngii.go.kr/ms/map/NlipMap.do?tabGb=total — 통합검색 → 수치지도 → 축척·버전 체크 → 다운로드(**로그인 필요**). 제공: 수치지형도(DXF, v1.0)·수치지형도 Ver2.0(SHP·NGI) 1:1,000~1:250,000, 항공사진, 정사영상, 공개DEM, 국토위성영상, 토지특성도·토지이용현황도. (출처: data.go.kr 15015482 "국토지리정보원_수치지도", 라이선스 공공누리 1유형, 무료, 갱신 수시)
- **항공사진·정사영상(현황도 배경 후보, 검증 반영)**: 위 메뉴에 정사영상이 있어 현황도 배경(정사영상 베이스맵)의 1차 후보지만, 본 조사에서는 이름만 확인했다. 공개본의 해상도(GSD)·보안처리 여부·라이선스·다운로드 조건(로그인·도엽 단위·포맷) 모두 **확인 필요** — 확인 방법: 국토정보플랫폼 로그인 → 통합검색 → '정사영상' 탭에서 성수 도엽(37705072 등) 메타데이터 열람. 별표 1(§4.3)의 영상 공개제한 기준(2차원 30 m·3차원 90 m)과 공개본 해상도의 관계도 함께 확인.
- **서울 1:1,000**: 서울시 "수치지형도제작" 페이지가 1/1,000 v1.0(DXF)·v2.0(NGI)을 국토정보플랫폼에서 로그인 후 다운로드할 수 있다고 명시, 단 "서울시 공간정보 보안관리 기준에 따라 **공개데이터만 제공**" (출처: https://news.seoul.go.kr/gov/archives/528208). 1:1,000 등고선·표고점은 §4.3의 분류기준상 공개제한이므로 다운로드본에 빠져 있을 가능성이 큼 — 실제 레이어 구성은 **확인 필요**.
- 도엽코드 XLSX(1K/5K/25K/50K/250K 색인): data.go.kr 15062161 "국토지리정보원_도엽코드"(공공누리 1유형).

### 3.2 도엽코드 체계 [공식: 수치지도 작성 작업규칙(국토교통부령, 시행 2015-06-04) 별표 "도엽코드 및 도곽의 크기"(제5조제2항 관련)]
law.go.kr DRF: `https://www.law.go.kr/DRF/lawService.do?OC=test&target=law&MST=171727&type=XML`, 별표 PDF `https://www.law.go.kr/LSW/flDownload.do?flSeq=166645039`

| 축척 | 코드 구성 | 도곽 | 예 |
|---|---|---|---|
| 1/50,000 | 경위도 1° 블록을 15′씩 **16등분**, 하단 위도 두 자리 + 좌측 경도 끝자리 + 2자리 색인(01~16, 좌상→행 우선) | 15′×15′ | `36715` |
| 1/25,000 | 1/50,000을 4등분, 끝에 1자리(1~4) | 7′30″×7′30″ | `367154` |
| 1/10,000 | 1/50,000을 25등분, 끝에 2자리(01~25) | 3′×3′ | `3671523` |
| 1/5,000 | 1/50,000을 **100등분**, 끝에 3자리(001~100) | 1′30″×1′30″ | `36715098` |
| 1/2,500 | 1/25,000을 100등분, 끝에 2자리(0A~9J) | 45″×45″ | `3671549H` |
| **1/1,000** | **1/10,000을 100등분**, 끝에 2자리(01~00) | 18″×18″ | `367152398` (9자리) |
| 1/500 | 1/1,000을 4등분, 끝에 1자리 | 9″×9″ | `3671523984` |

- 검증 [로컬]: 성수 4도엽 도곽 SHP(`N3L_H0010000`, EPSG:5186)를 4326으로 변환하면 37705072 = lon 127°01.5′–127°03.0′, lat 37°33.0′–37°34.5′로 아래 공식과 일치(37705073·37705082·37705083도 동일 검증).

```python
def sheet5k_bounds(code):            # '37705072' -> (lon0, lat0, lon1, lat1), WGS84 deg
    lat2, lon1, i50, i5 = int(code[:2]), int(code[2]), int(code[3:5]), int(code[5:8])
    lon_deg = 120 + lon1 if lon1 >= 4 else 130 + lon1      # 7 -> 127E
    r50, c50 = divmod(i50 - 1, 4); r5, c5 = divmod(i5 - 1, 10)
    top = lat2 + 1 - r50 * 0.25 - r5 * 0.025                # 15' = 0.25deg, 1'30" = 0.025deg
    left = lon_deg + c50 * 0.25 + c5 * 0.025
    return left, top - 0.025, left + 0.025, top
assert sheet5k_bounds('37705072') == (127.025, 37.55, 127.05, 37.575)
```
(1/1,000 9자리 코드는 1/10,000(3′) 셀을 10×10으로 나눠 같은 방식으로 계산; `lon_deg` 규칙은 한반도 범위(124~131°E)에서만 유효.)

### 3.3 수치지형도 작성 규정 [공식]
- 「수치지형도 작성 작업 및 성과에 관한 규정」(국토지리정보원 고시 제2026-2524호, 2026-05-28): 지형지물 표준코드는 별표 1(엑셀, PDF `flSeq=164725433`), 속성목록은 별표 2(제15조, `flSeq=164725439`). 제13조⑤ "1/1,000 수치지형도의 경우 지자체별 상황과 특성에 따라 별표 1 지형지물 표준코드를 가감할 수 있다", ⑥ 1/25,000은 1/5,000 기반 자동 생산 시 일반화 가능. 구조화편집(제15조) 12호 "등고선·표고점·기준점에는 높이값(3차원 데이터)을 정확히 입력", 13호 "1/1,000은 건물·교량에서 등고선 단락". (DRF `target=admrul&ID=2100000280186`)
- 사용자 보유 CSV(`docs/reference/수치지형도_지형지물_표준코드.csv`, 1,799행)는 위 별표 1과 같은 "수치지도 지형지물 표준코드" 표(통합코드·1.0 축척별 구조/표현/색상·2.0 구조) [로컬].

---

## 4. 지형(DEM) — 소스 비교와 추천

### 4.1 V-World 3D 지형 타일 [공식 SDK 코드]+[실측]
- 공식 3D 지도 API 3.0 SDK 파일 `WSViewerStartup.js`(`https://map.vworld.kr/js/ws3dmap/WS3DRelease3/WSViewerStartup.js`, Cesium 기반 — 직접 URL로 열어 내용 확인) 안에 지형 공급자가 하드코딩돼 있음(단, 로더 `webglMapInit.js.do?version=3.0` 응답 본문에서 이 파일 경로 문자열은 grep으로 찾지 못해 동적 로드로 추정 → 로더→SDK 연결 고리는 **확인 필요**): `http://xdworld.vworld.kr:8080/XDServer/requestLayerNode?Layer=dem&APIKey=<SDK 내장 키>&Level={z}&IDX={x}&IDY={y}`. 타일 = **65×65 Float32(리틀엔디언) 높이값, 16,900 바이트**(`heightmapSrcWidth=65`, `heightValueDataByteSize=4`, `expectedResponseBufferLength` 일치 검사), 타일링 = 지리좌표 **레벨0 10×5 타일(타일 1개 = 36°)**, 요청 시 `IDY = (레벨의 Y타일수 − y − 1)`로 남쪽 기준 뒤집음. 즉 레벨 L의 타일 크기 = 36°/2^L (L=15 ≈ 0.0011° ≈ 122 m, 샘플 간격 ≈ 1.9 m).
- 엔드포인트 존재 확인 [실측]: 더미 키로 `…/XDServer/requestLayerNode`와 `…/XDServer3d/requestLayerNode` 모두 HTTP 200 + XML `<Error code="ERROR_DB_GENERAL">`. **타일 자체는 받지 않았다**(공개제한 데이터).
- 제3자 기록 [블로그]: vw-lab.com/52(2018, 2019-07 갱신) — 레벨 1~15, 레벨 15 ≈ 1.5 m, `.bil`, 2019-07 "브이월드 측에서 3D 데이터 Open API를 폐쇄"; 저장 금지 요구를 받았다고 기록. EgisCorp/XDWorld 이슈 #618(2025)에서도 엔진 DEM 포맷을 `"bil"`로 설정.
- 결론: 포맷은 Float32 65×65 grid(실질 'bil')로 특정되나, §4.3 법규상 복제·저장 불가 → **플러그인 사용 금지**.

### 4.2 공개 DEM 비교

| 소스 | 해상도·종류 | 수직기준 | 접근 | 라이선스 | 자동화 | 출처 |
|---|---|---|---|---|---|---|
| 연속수치지형도 등고선+표고점 (NGII) | 1:5,000, 주곡선 **5 m**·계곡선 25 m [로컬 4도엽 검증], 표고점 0.1 m | 국가 수준면(인천만 평균해수면) | 데이터마켓 dsId 30185/30245, 전국 SHP, 다운로드 시 로그인 여부 확인 필요 | CC BY(V-World 표기) — 단 별표 1 '1:5,000 이상 등고선·표고값 인터넷 표시 불가'와의 양립 확인 필요(§4.3) | 연 1회 수동 다운로드 → 로컬 DB(로컬 처리·파일 납품 한정) | §2 |
| 수치지형도 1:1,000 등고선 (서울) | 1 m 간격 추정 | 〃 | **공개제한**(1:1,000 축척 이상 지도의 등고선·표고점) | – | 불가 | §4.3 |
| NGII 공개 DEM | **90 m** 격자·RMSE 6.2 m — [언론] 2015년 기사 수치일 뿐, data.go.kr 15059920·국토정보플랫폼 공식 페이지에는 해상도 미기재 → 현행 사양(해상도·형식·범위) **확인 필요** | – | 국토정보플랫폼, 로그인, IMG | 공공누리 1유형(제한 없음) | 수동 | data.go.kr 15059920; [언론] etnews 2015-01-04 (확인 방법: 국토정보플랫폼 로그인 후 '공개DEM' 메타데이터) |
| NGII 5 m DEM | 5 m(1:5,000 도엽 단위 성과) | – | **공개제한**: 영상자료 교부신청, 보안심사 | – | 불가 | data.go.kr 15067637·15067641(도엽별 성과·신청내역); §4.3 |
| NGII 건물높이공간정보 | 건물별 높이 | – | 공개제한: 공문 신청·보안심사 승인자만 온라인 열람(학술·공공복리·안전 목적) | – | 불가 | https://map.ngii.go.kr/bl/map/buldEncView.do |
| **Copernicus DEM GLO-30** | 30 m **DSM**(건물·수목 포함) | EGM2008 | `s3://copernicus-dem-30m` (eu-central-1), COG, `--no-sign-request`; 한국 타일 `Copernicus_DSM_COG_10_N37_00_E127_00_DEM.tif` HEAD 200 [실측] (90 m도 200) | 무료, 출처표기 "© DLR e.V. 2010-2014 and © Airbus Defence and Space GmbH 2014-2018 provided under COPERNICUS by the European Union and ESA" | **완전 자동화 가능** | https://registry.opendata.aws/copernicus-dem/ ; https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM |
| SRTMGL1 v003 | 1″(30 m), 2000-02 촬영, 공극 보완 | EGM96 | LP DAAC/Earthdata Cloud, **Earthdata 로그인** 필요, HGT(`N37E127.SRTMGL1.hgt.zip`) | 제한 없음(인용 권장 DOI 10.5067/MEASURES/SRTM/SRTMGL1.003) | .netrc로 자동화 가능 | https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003 |

- 추천 조합: **등고선+표고점 TIN(도시 블록 스케일) + Copernicus GLO-30(광역 산세·단면 배경)**. GLO-30은 DSM이라 건물 밀집지에서 지반고가 과대 → 건물 footprint 내부는 등고선 TIN 값을 쓰고, 산지만 GLO-30 보간.
- **수직기준·DSM 보정 절차(검증 반영: 누락 보완)**: 등고선·표고점은 국가 수준면(인천만 평균해수면) 기준 표고, GLO-30은 EGM2008 지오이드 기준 표고의 **DSM**(https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM). 서울 일대 두 기준의 오프셋 수치는 **확인 필요**(국토지리정보원 KNGeoid18 vs EGM2008 비교)이므로 플러그인은 수치 대신 **경험적 보정**으로 처리한다: (1) 대상지 외곽 전이대(등고선 TIN 범위 바깥 0.5~1 km)에서 수목·건물이 없는 표고점(`N3P_F0020000`, 도로·광장 위)과 같은 위치의 GLO-30 샘플 차이를 모아 중앙값(필요하면 1차 평면)으로 오프셋을 추정해 GLO-30 전체에 적용, (2) GLO-30은 산지에서 수목 캐노피 높이가 포함되므로 등고선 TIN이 있는 범위에서는 쓰지 않고, 범위 밖 산지는 '참고 배경 지형' 레이어로 분리하거나 임상(산림입지도 `LT_C_FSDIFRSTS`) 기준 캐노피 가정값(10~15 m, **확인 필요**)을 빼서 보정, (3) 경계부 단차는 전이대 폭 200~500 m에서 거리 가중 블렌딩, (4) 3dm 레이어 노트에 수직기준·적용 오프셋·보정 방법을 기록해 납품물에서 추적 가능하게 한다.

### 4.3 법적 근거(공개제한) [공식, law.go.kr DRF]
- 「국토지리정보원 국가공간정보 보안관리규정」(예규, 2024-05-01, ID 2100000240356) 별표 1 "국가공간정보 세부 분류기준"(PDF `flSeq=144914683`):
  - 전자지도 **공개제한**: "1:1,000 축척 이상 지도의 등고선과 표고점"; 공개 지도라도 "인터넷·내비게이션·휴대폰 등을 통해 좌표와 1:5,000 축척 이상 지도의 등고선·표고값 표시 불가". **해석 주의(검증 반영)**: 한국 축척 표기에서 '1:5,000 이상'은 1:5,000을 포함(대축척 쪽)하므로, 본 문서가 1순위로 추천한 연속수치지형도 1:5,000 등고선·표고점도 웹/클라우드형 뷰어나 온라인 공유 베이스맵에 올리면 저촉될 수 있다. 데스크톱 Rhino 플러그인 내부 처리와 3dm·AI 파일 납품은 '인터넷 등을 통한 표시'가 아니라는 해석이 필요하며, V-World 데이터마켓이 같은 데이터를 CC BY로 배포하는 것과 이 표시 제한이 어떻게 양립하는지는 **확인 필요**(국토지리정보원 공간정보 보안 담당 또는 V-World 고객센터 1661-0115에 서면 질의 권장). 그때까지 플러그인은 등고선·표고값을 **온라인 기능(웹 공유·클라우드 렌더)에서 제외**하는 것을 기본값으로 둔다.
  - 기타공간정보 **공개제한**: "해상도가 90m보다 정밀하고 3차원 좌표가 포함된 3차원 공간정보"(도로 지역은 보안성 검토 후 공개 가능). 항공사진·위성영상: 3차원 좌표 포함 90 m보다 정밀한 자료 = 공개제한, 2차원 좌표 포함 30 m보다 정밀한 자료 = 공개제한.
- 「국토교통부 국가공간정보 보안관리규정」(훈령 제1566호, 2022-11-18, ID 2100000215941) 제10조(공간정보의 복제·출력 등 제한) ①: 비공개·공개제한 공간정보는 다음 3개 호 외에는 복제·출력 불가 — 1호 영 제25조에 따른 복제·관리, 2호 비공개 공간정보는 관리기관의 장의 허가를 받은 때, 3호 "공개가 제한되는 공간정보는 보안담당관의 허가를 받은 때"(2차 검증에서 3개 호 전체 확인; 본 문서는 3호를 인용).
- 「공개제한 공간정보의 보안심사 규정」(국토교통부 고시 제2024-286호, ID 2100000241872): 국가공간정보 기본법 제35조의2에 따라 공개제한 공간정보를 제공받으려는 자의 보안심사 절차. 별표 1 "보안심사 기준"(PDF `flSeq=140815841`): 보안대책 수립, 보안서약, 외부망 차단 또는 암호화, 공개서버 분리, 사용 만료 시 파기 등 — 1인 개발·배포형 플러그인과 양립 어려움.

---

## 5. V-World 3D 건물(facility_build 등) 사용 조건

| 항목 | 내용 | 출처 |
|---|---|---|
| 과거 3D DATA API | `http://xdworld.vworld.kr:8080/XDServer/3DData?Request=GetCapabilities/GetLayerExists/GetLayer&Layer=facility_build|dem|tile&Level&IDX&IDY&DataFile` — 레이어 facility_build(Real3D, 레벨 0–15, .xdo 메시+텍스처), dem(terrainDEM), tile(terrainImg) | [블로그] jacegem 2018 |
| 현재 상태 | "과거 사용자가 공개제한 공간정보인 3D 공간정보를 크롤링하여 … 3D DATA API 서비스를 중지", 정당한 취득은 「공개제한 공간정보 보안심사 규정」 절차로 유도 | [블로그] namu.wiki V-World(원문 인용), vw-lab.com/53 (2019-07 폐쇄 기록). V-World 공지 게시판(2011~2026, 10페이지 전부 열람)에서는 해당 공지 제목을 찾지 못함 → 공식 공지 **확인 필요** |
| 현재 공식 3D | 웹지엘 3D지도 API 2.0/3.0(`webglMapInit.js.do`, Cesium 기반), 3D 데스크톱 API(32비트 Windows C/S), 3D 모바일 API — 모두 "표출" 엔진이며 데이터 추출 API 아님 | [공식] https://www.vworld.kr/dev/v4apiRefer.do, v4dv_opnws3dmap3guide_s001.do, v4dv_dhapiguide_s001.do |
| 데이터마켓 3D 항목 | 3차원 시설물 LoD1/LoD3/LoD4, 수치표고모형, 건물높이DB가 목록에는 있으나 상세 페이지는 비어 있음 | [공식] §2 |
| 법적 분류 | 3차원 좌표 포함·90 m보다 정밀 → 공개제한(§4.3) | [공식] |
| 결론 | **사용 불가.** 건물 3D는 `LT_C_BLDGINFO`(또는 GIS건물통합정보 SHP) footprint를 `height`(없으면 `grnd_flr`×층고) 로 extrude | – |

---

## 6. WMS/WMTS 배경지도 [공식]+[실측]

- WMTS 레퍼런스: https://www.vworld.kr/dev/v4dv_wmtsguide_s001.do — GetCapabilities `https://api.vworld.kr/req/wmts/1.0.0/{key}/WMTSCapabilities.xml`, GetTile `https://api.vworld.kr/req/wmts/1.0.0/{key}/{layer}/{tileMatrix}/{tileRow}/{tileCol}.{tileType}` (= `{z}/{y}/{x}`, Google XYZ 인덱스). TMS 레퍼런스: https://www.vworld.kr/dev/v4dv_tmsguide_s001.do — `https://api.vworld.kr/req/tms/1.0.0/{key}/{tileMap}/{tileMatrix}/{tileRow}/{tileCol}.{tileType}` (동일하게 Google Index Y).

| 레이어 | 포맷 | 줌 범위(레퍼런스) | Capabilities 실측 |
|---|---|---|---|
| `Base` | png | 6–19 | TileMatrixSet `GoogleMapsCompatible`(EPSG:3857, 6–19, 256 px) |
| `white` | png | 6–18 | 〃 ¹ |
| `midnight` | png | 6–18 | 〃 ¹ |
| `Hybrid` | png | 6–19 | 〃 |
| `Satellite` | jpeg | 6–19 | 〃 |
| `gray` | (블로그에만 등장) | – | **Capabilities에 없음** — 과거 명칭으로 보임 |
| 해외 테마(`Satellite/themes/cities/2024/Paris` 등) | png | 6–18(도시)/6–16(재난) | 템플릿 `{TileMatrix}/{TileCol}/{TileRow}` 순서 주의 |

¹ 레퍼런스 표는 `white`·`midnight`를 6–18로 적지만, 2026-10-07 Capabilities 실측에서는 두 레이어도 `Base`와 같은 `GoogleMapsCompatible`(6–19) TileMatrixSet을 참조한다(레퍼런스와 불일치). z=19 타일이 실제로 응답하는지는 GetTile로 **확인 필요**.

- 타일 실측: `…/{key}/Base/15/12694/27950.png` → `image/png` 3,570 B. 잘못된 키는 OWS ExceptionReport(`InvalidParameterValue`, "등록되지 않은 인증키입니다").
- WMS GetMap: `https://api.vworld.kr/req/wms?key=…&service=WMS&request=GetMap&version=1.3.0&layers=lt_c_uq111&styles=lt_c_uq111&crs=EPSG:5186&bbox=…&width=…&height=…&format=image/png&transparent=true` (레이어 최대 4개, bbox는 4326일 때 y,x 순). 범례이미지 API 별도(`v4dv_legendguide2_s001.do`).
- **베이스맵 래스터 좌표계 처리(검증 반영: 누락 보완)**: WMTS TileMatrixSet은 EPSG:3857 `GoogleMapsCompatible` 하나뿐 [실측 Capabilities]. 플러그인·수치지형도·UPIS는 EPSG:5186/5179이므로 WMTS 타일을 베이스맵에 깔려면 타일 모자이크 → 재투영(GDAL warp 3857→5186) → 월드파일(PNG+PGW)로 일러스트레이터 배치가 필요하고, 재투영 리샘플링으로 라벨·선이 흐려진다. 반면 **WMS GetMap은 `crs=EPSG:5186`을 직접 지원**(§1.5 CRS 목록)하므로 5186 bbox·원하는 px 크기로 한 장을 바로 받을 수 있어 **베이스맵용 래스터는 WMS가 적합**(한 요청 레이어 ≤4, 최대 이미지 크기는 확인 필요). WMTS는 화면 미리보기·네비게이션용으로 한정.
- V-World 타일/WMS 이미지를 일러스트레이터 베이스맵(납품물)에 포함할 때의 **출처표기·2차 가공 허용 조건은 조사되지 않음 → 확인 필요**(V-World 오픈API 이용약관·저작권 안내 페이지, 배경지도 하단 'ⓒ 국토교통부' 표기 요구 여부).

---

## 7. 수치지형도 레이어 코드표 — 로컬 1차 자료로 확인

- 자료: `/Users/sanghoon/Documents/GitHub/Seoungsu/data/raw/shp/37705072/` (성동, 1:5,000 Ver2.0 SHP, EPSG:5186, cp949) 외 3도엽, 코드표 CSV `docs/reference/수치지형도_지형지물_표준코드.csv`. 파일명 규칙 `N3{A|L|P}_{통합코드 8자리}` (A=면, L=선, P=점). 각 피처의 `UFID`(34자)에 도엽코드가 포함(예 `1000037705072B0011…`).
- 코드표의 "2.0 구조"와 실제 SHP 도형이 다른 경우가 있음(인도 A0033320·주유소 C0423365는 코드표 '선/점'이지만 SHP는 '면', 도로분리대 C0520000은 코드표 '면'이지만 SHP는 '선').

| 코드(SHP) | 의미(대분류/중분류) | 도형 | 핵심 필드(실측) | 용도 |
|---|---|---|---|---|
| `N3A_A0010000` | 교통/도로경계 | 면 (2,789) | UFID | **도로면 베이스맵** |
| `N3L_A0020000` | 교통/도로중심선 | 선 (5,443) | 도로번호, 명칭, 도로구분(미분류/면리간도로/소로), 시점, 종점, 포장재질, 분리대유무, **차로수**(1~10), **도로폭**(m), 일방통행, 자동차전용, 기타 | 도로망·폭·차로 |
| `N3A_A0033320` | 교통/인도(보도) | 면 (588) | 폭, 재질(블록/아스콘) | 보도 |
| `N3A_A0053326` | 교통/안전지대 | 면 | 구조, 명칭 | 교차로 디테일 |
| `N3A_A0063321` | 교통/육교 | 면 | 명칭, 연장, 폭, 높이, 형태 | 입체보행 |
| `N3A_A0070000` | 교통/교량 | 면 (24) | 명칭, 종류(도로교/철교), 연장, 폭, 설치연도, 재질, 하천명 | 교량 3D |
| `N3A_A0080000` | 교통/교차로 | 면 | 명칭, 종류 | – |
| `N3A_A0090000` | 교통/입체교차부 | 면 | 명칭, 구분, 연장, 높이, 통과하중, 재질, 보도 | 고가 |
| `N3A_A0100000` | 교통/인터체인지 | 면 | 명칭, 기타 | – |
| `N3A_A0110020` | 교통/터널 | 면 | 명칭, 연장, 폭, 높이 | 터널 |
| `N3L_A0123373` | 교통/터널입구 | 선 | 명칭 | – |
| `N3P_A0131122` | 교통/정거장 | 점 | 명칭 | 역·정류장 라벨 |
| `N3L_A0150000` | 교통/철도 | 선 | 명칭, 구분, 관리기관 | 철도 |
| `N3A_A0160024` | 교통/철도경계(철도부지선) | 면 | UFID | 철도부지 |
| `N3L_A0171119` | 교통/철도중심선 | 선 | 명칭, 구분, 구조, 관리기관 | 선로 |
| `N3A_A0191221` / `N3A_A0201222` | 교통/플랫폼·플랫폼의 지붕 | 면 | 명칭 | 역사 |
| **`N3A_B0010000`** | 건물/건물경계 | 면 (12,426) | 명칭, 구분, **종류**(주택외건물/일반주택/무벽건물/연립주택/아파트/가건물/공사중건물), 용도, 주기, **층수**, 측량방법 | 건물 매스(층수 extrude) |
| `N3L_B0020000` | 건물/담장 | 선 (573) | 구분(담/문주), 재질 | 담장 |
| `N3L_C0050000` | 시설/제방 | 선 | 명칭, 구분, 재질, 상하구분, 연장, 높이 | 하천 제방 |
| `N3L_C0060000` / `N3L_C0070000` | 시설/수문·암거 | 선 | 구분, 재질 | – |
| `N3A_C0186115` | 시설/탱크 | 면 | 명칭, 용도, 관리기관 | – |
| `N3P_C0380000` | 시설/놀이시설 | 점 | 명칭, 구분 | – |
| `N3A_C0390000` | 시설/계단 | 면 (90) | 명칭, 구조, 폭 | 지형 단차 |
| `N3A_C0423365` | 시설/주유소 | 면 | 명칭, 종류 | – |
| `N3A_C0430000` | 시설/주차장 | 면 | 명칭, 구분, 수용량 | 주차 |
| `N3L_C0520000` | 시설/도로분리대 | 선 | 구조 | – |
| `N3A_D0010000` | 식생/경지계 | 면 | 구분 | 녹지(경작) |
| `N3P_D0030000` | 식생/독립수 | 점 | 관리번호, 명칭, 구분, 직경, 높이, 수령, 수종 | 보호수 |
| **`N3A_E0010001`** | 수계/하천경계 | 면 (9) | UFID | **하천면** |
| `N3L_E0020000` | 수계/하천중심선 | 선 | 하천번호, 명칭, 구분 | 하천 라벨 |
| `N3A_E0032111` | 수계/실폭하천 | 면 | UFID | 소하천 |
| `N3P_E0042326` | 수계/유수방향 | 점 | – | – |
| `N3A_E0052114` | 수계/호수·저수지 | 면 (13) | 명칭, 용도, 면적, 관리기관 | 수면 |
| **`N3L_F0010000`** | 지형/등고선 | 선 (126) | 구분(주곡선/계곡선), **등고수치**(5 m 간격, 계곡선 25·50·75·100) | **지형 TIN** |
| **`N3P_F0020000`** | 지형/표고점 | 점 (786) | **수치**(0.1 m) | 지형 TIN 보강 |
| `N3L_F0030000` | 지형/성·절토 | 선 | 구분, 상하구분 | 법면 |
| `N3L_F0040000` | 지형/옹벽 | 선 (448) | 종류(옹벽/석축), 상하구분, 연장, **높이**, 재질 | 옹벽 3D |
| `N3A_G0010000` | 경계/행정경계 | 면 | 명칭, 구분(특별시/구) | 경계 |
| `N3A_G0020000` | 경계/수부지형경계 | 면 | 명칭, 형태(습지) | 습지 |
| `N3L_G0030000` | 경계/기타경계 | 선 (323) | 용도(기타콘크리트구조물/지하주차장입구) | – |
| `N3L_H0010000` | 주기/도곽 | 선 | 도엽명, 도엽코드 | 도엽 범위 |
| `N3P_H0020000` | 주기/기준점 | 점 | 구분, 번호, 좌표, 표고 | 측량 기준 |
| `N3P_H0040000` | 주기/지명 | 점 | 명칭, 구분, 형태 | 라벨 |
| `N3P_H0059153` | 주기/산·산맥 | 점 | 산명, 높이 | 라벨 |

- 코드표에 **공원·녹지 코드는 없음**(시설 대분류에 묘지계 C0290000·주차장 C0430000 정도). 공원은 UPIS 공간시설(`LT_C_UPISUQ153`·데이터마켓 30068)·도시자연공원구역(`LT_C_UQ162`)에서 가져온다.
- 2D 데이터 API `LT_L_N3A0020000`은 같은 도로중심선이지만 속성이 코드값(RDD009 등)이고 전국 연속(도엽 경계 없음)인 반면, 도엽 SHP는 한글값이며 도엽 단위로 잘린다.

---

## 8. 미해결·확인 필요
1. 데이터마켓 파일 다운로드 버튼의 로그인 요구 여부(상세 페이지 열람은 비로그인 가능; 목록 페이지는 '로그인 후 모든 서비스 이용'만 안내) — 비로그인 브라우저에서 dsId=30185 다운로드 클릭으로 재확인. §0 요약의 '로그인 없음'은 이에 맞춰 '확인 필요'로 내렸다.
2. 2D 데이터 API·WMTS의 운영상 일일 임계치: FAQ "별도 일일 제한량 없음, 단 무리한 호출 시 일시 차단"; 2D 데이터 API·TMS 레퍼런스 모두 `OVER_REQUEST_LIMIT` 정의 → 임계치 비공개. 대상지 단위 호출·백오프로 운용(§1.2·§1.7).
3. 인증키 유효기간: FAQ·공지(2024-02-22 "유효기간 확대")는 수치를 본문에서 못 읽음(검색 요약: 개발키 6개월·3회 연장, 운영키 2년 — 미확인). 배포 사용자가 `localhost` 등록 개발키로 써도 되는지(§1.7).
4. 3D DATA API 중지의 공식 공지 원문(게시판 제목 목록에 없음; namu.wiki·vw-lab 기록만).
5. `LT_L_N3A0020000` 코드값(RDD/RDQ/CSU/ITH) 코드표 — 데이터마켓 첨부 `연속수치지형도_데이터_설명서.pdf`. (분리대 필드명은 `dvyn`으로 확정.)
6. 서울 1:1,000 수치지형도 다운로드본에 등고선·표고점 레이어가 포함되는지(공개제한 분류상 제외 가능성).
7. 라이선스 표기 불일치: 연속지적도형정보(V-World CC BY / data.go.kr 15125044 제4유형), 토지특성정보(V-World '라이센스 미지정' / data.go.kr 15048121 제한 없음) — 어느 표기가 유효한지.
8. 데이터마켓 3D 항목(수치표고모형·3차원 시설물·건물높이DB) 상세 미기재.
9. V-World WMTS `gray` 레이어 존재 여부(현재 Capabilities에는 없음); `white`·`midnight`의 z=19 실제 응답 여부.
10. **법적 공백**: 별표 1 '1:5,000 축척 이상 등고선·표고값 인터넷 표시 불가'와 V-World 데이터마켓 CC BY 배포의 양립, 데스크톱 플러그인·파일 납품이 '인터넷 표시'에 해당하지 않는다는 해석의 근거 — 국토지리정보원·V-World 서면 질의(§4.3).
11. 수직기준: 국가 수준면(인천만) vs EGM2008(GLO-30)의 서울 일대 오프셋 수치, 산지 캐노피 가정값(§4.2).
12. 도로명주소 전자지도(business.juso.go.kr) 제공 레이어(실폭도로·도로구간·건물)·포맷·좌표계·갱신·회원 요건(§2.1).
13. 서울시 S-Map/오픈랩 3D 건물·지형 데이터의 제공 방식·라이선스(§2.1).
14. 국토정보플랫폼 공개 정사영상·항공사진의 해상도·라이선스·다운로드 조건(§3.1); 공개 DEM의 현행 사양(90 m 여부, §4.2).
15. V-World 타일/WMS 이미지를 납품 베이스맵에 포함할 때의 출처표기 조건; WMS GetMap 최대 이미지 크기(§6).
16. `webglMapInit.js.do?version=3.0` → `WSViewerStartup.js` 로드 경로(동적 로드 추정, §4.1).
17. 건축HUB 표제부 `platGbCd`(0 대지/1 산/2 블록)와 PNU 11번째 자리(1 토지/2 산)의 매핑(§1.6).

---

## 출처 목록 (접근일 2026-10-07)

[공식] V-World
- 2D 데이터 API 2.0 레퍼런스(광역시도·파라미터 전체): https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=adsido
- 건축물정보: …?svcIde=bldginfo / 연속지적도: …?svcIde=cadastral / 교통링크: …?svcIde=moctlink / 교통노드: …?svcIde=moctnode / 시군구: …?svcIde=adsigg / 읍면동: …?svcIde=ademd / 도시지역: …?svcIde=uq111 / 도시계획(도로): …?svcIde=upisuq151 / 공간시설: …?svcIde=upisuq153 / 지구단위계획: …?svcIde=upisuq161 / 하천망: …?svcIde=wkmstrm / 도로명주소 건물: …?svcIde=spbd / 도로명주소 도로: …?svcIde=sprd / 도로중심선: …?svcIde=n3a0020000
- 2D 데이터 API 레이어 목록(158): https://www.vworld.kr/dev/v4dv_2ddataguide2_s001.do (pageIndex=1~16)
- WMS/WFS 2.0: https://www.vworld.kr/dev/v4dv_wmsguide2_s001.do / WMTS: https://www.vworld.kr/dev/v4dv_wmtsguide_s001.do / TMS: https://www.vworld.kr/dev/v4dv_tmsguide_s001.do / API 목록: https://www.vworld.kr/dev/v4apiRefer.do
- Geocoder 2.0(일 40,000건·실시간 사용): https://www.vworld.kr/dev/v4dv_geocoderguide2_s001.do / FAQ: https://www.vworld.kr/v4po_brdfaq_s001.do?bodIde=52 / 공지: https://www.vworld.kr/v4po_brdnotice_s001.do?bodIde=51 (상세 `v4po_brdnotice_s002.do?brdIde=29831`, `=26490`)
- 3D: https://www.vworld.kr/dev/v4dv_opnws3dmap3guide_s001.do , https://www.vworld.kr/dev/v4dv_opnws3dmap2guide_s001.do , https://www.vworld.kr/dev/v4dv_dhapiguide_s001.do , SDK `https://map.vworld.kr/js/webglMapInit.js.do?version=3.0` → `https://map.vworld.kr/js/ws3dmap/WS3DRelease3/WSViewerStartup.js`
- 국가중점데이터 API: https://www.vworld.kr/dtna/dtna_guide_s001.do , https://www.vworld.kr/dtna/dtna_apiSvcList_s001.do , 상세 `https://www.vworld.kr/dtna/dtna_apiSvcFc_s001.do?apiNum=18|17|25|51|76|92|3|6`
- 공간정보 다운로드(데이터마켓): https://www.vworld.kr/dtmk/dtmk_ntads_s001.do?svcCde=MK , 상세 `https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=4|18|23|24`, `…?dsId=30162|30179|30182|30185|30074|30065`, `…?dsId=30524&svcCde=MK`

[공식] 국토지리정보원·법령·공공데이터포털
- 국토정보플랫폼: https://map.ngii.go.kr/ms/map/NlipMap.do?tabGb=total , https://map.ngii.go.kr/mn/mainPage.do , 건물높이공간정보 https://map.ngii.go.kr/bl/map/buldEncView.do
- 서울시 수치지형도제작: https://news.seoul.go.kr/gov/archives/528208
- data.go.kr: 수치지도 15015482, DEM 15059920, 도엽코드 15062161, 수치표고성과내역 15067637, 수치표고신청내역 15067641, 토지특성정보 15048121, GIS건물통합정보 15083092, 연속지적 15125044, 연속수치지형도_건물 15125047, 건물통합정보_마스터 15146873, 3D 데스크톱 API 15101109, **건축HUB 건축물대장정보 15134735(https://www.data.go.kr/data/15134735/openapi.do)**, 연속지적 파일데이터 https://www.data.go.kr/data/15125044/fileData.do
- 수치지도 작성 작업규칙(부령): https://www.law.go.kr/DRF/lawService.do?OC=test&target=law&MST=171727&type=XML , 별표 PDF https://www.law.go.kr/LSW/flDownload.do?flSeq=166645039
- 수치지형도 작성 작업 및 성과에 관한 규정(고시): https://www.law.go.kr/DRF/lawService.do?OC=test&target=admrul&ID=2100000280186&type=XML
- 국토지리정보원 국가공간정보 보안관리규정: …&ID=2100000240356 , 별표1 PDF https://www.law.go.kr/LSW/flDownload.do?flSeq=144914683
- 국토교통부 국가공간정보 보안관리규정: …&ID=2100000215941 / 공개제한 공간정보의 보안심사 규정: …&ID=2100000241872 , 별표1 PDF https://www.law.go.kr/LSW/flDownload.do?flSeq=140815841

[공식] 서울시·기타(2차 검증 시 추가)
- S-Map 디지털트윈 서울: https://smap.seoul.go.kr/ , 3D라이브러리 https://smap.seoul.go.kr/smapModelLibrary.do , 오픈랩 https://openlab.eseoul.go.kr/
- 주소기반산업지원서비스(도로명주소 전자지도): https://business.juso.go.kr/ (SPA — 전자지도 메뉴 내용은 브라우저로 확인 필요; `/addrlink/elctrnMapProvd/geoDBDwldList.do` 는 404)

[공식] 해외 DEM
- Copernicus DEM(AWS Open Data): https://registry.opendata.aws/copernicus-dem/ ; 라이선스·EGM2008: https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM ; 타일 확인 `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N37_00_E127_00_DEM/Copernicus_DSM_COG_10_N37_00_E127_00_DEM.tif`
- SRTMGL1 v003: https://www.earthdata.nasa.gov/data/catalog/lpcloud-srtmgl1-003

[블로그·언론·2차]
- vw-lab DEM/건물: https://www.vw-lab.com/52 , https://www.vw-lab.com/53 ; jacegem 3D 포맷: https://jacegem.github.io/blog/2018/Vworld-3D-Data%EB%A5%BC-Three.js%EB%A1%9C-%EC%B6%9C%EB%A0%A5%ED%95%98%EA%B8%B0/ ; EgisCorp/XDWorld 이슈: https://github.com/EgisCorp/XDWorld/issues/618 ; namu.wiki V-World: https://namu.wiki/w/V-World ; 도엽번호(daum 카페): https://m.cafe.daum.net/GPSGIS/Lrtt/472 ; WMTS 예제 블로그: https://blog.itcode.dev/projects/2022/03/21/gis-guide-for-programmer-11 ; [언론] etnews 2015-01-04 DEM 90 m 공개: https://m.etnews.com/20150104000013

[로컬]
- `/Users/sanghoon/Documents/GitHub/Seoungsu/data/raw/shp/{37705072,37705073,37705082,37705083}/` , `/Users/sanghoon/Documents/GitHub/UrbanDesignTool/docs/reference/수치지형도_지형지물_표준코드.csv` , `dev_plan_qa_univ_cases.py` , `data/raw/vworld_토지특성정보/AL_D194_*`

---

## 검증 이력

**2026-10-07 — 2차 검증 결과 반영**

| # | 구분 | 위치 | 조치 |
|---|---|---|---|
| 1 | 모순 해소 | §0 결론·지형 순위 1, §4.2, §8-1 | 등고선·표고점 '로그인 없음' 단정 → '다운로드 시 로그인 요구 여부 확인 필요'로 통일(목록 페이지는 '로그인 후 모든 서비스 이용'만 안내) |
| 2 | 법적 공백 | §0 결론(인용 블록 추가), §0 지형 표·순위 1, §4.2 표, §4.3, §8-10 | 별표 1 '1:5,000 축척 이상 등고선·표고값 인터넷 표시 불가'(1:5,000 포함)와 1순위 추천의 긴장 명시, 온라인 기능 제외를 기본값으로, CC BY 배포와의 양립은 '확인 필요' |
| 3 | 과장 정정 | §0 호출 제한 표, §1.1, §1.2, §8-2 | FAQ 후반부("무리하게 호출이 많을 경우 일시적으로 차단") 복원; `OVER_REQUEST_LIMIT`가 2D 데이터 API 레퍼런스(svcIde=adsido·n3a0020000)에도 정의됨을 반영; 서울 전수 1,162페이지 순차 호출의 차단 위험 명시 |
| 4 | 정확성 | §0 건물 행·호출 제한 표, §1.2 #2 | 응답 15.3 s → 재실측 6.2 s·5.7 s로 가변, '참고치' 표기; BOX(126.76,37.43,127.18,37.70)는 경기 일부 포함 → 1,161,721건을 서울 건물 수로 인용하지 않도록 수정 |
| 5 | 추가 발견 | §0 수계 행, §1.2 #5·#6, §1.4 하천망·도로중심선 | `LT_L_N3A0020000`·`LT_C_WKMSTRM` 레퍼런스 LINESTRING/POLYGON vs 실응답 MultiLineString/MultiPolygon 명시, 파서 Multi\* 전제 규칙 추가 |
| 6 | 확인 필요 → 확정 | §1.4 도로중심선, §8-5 | 분리대 필드명: 레퍼런스 HTML을 다시 열어 `dvyn`("dvyn N CSU002 분리대 유․무") 확인 — 검증 요약의 'dvqt'는 오독으로 기록 |
| 7 | 누락 보완 | §1.6 신설 | 건축HUB 건축물대장정보 API(10개 오퍼레이션; 표제부 응답 스키마의 `heit`·`grndFlrCnt`·`ugrndFlrCnt`·`useAprDay`를 data.go.kr 15134735 페이지 내장 스펙 JSON에서 확인; 개발계정 10,000/일·자동승인·무료·월간) 비교표 추가; PNU 분해 규칙(platGbCd 매핑은 확인 필요) |
| 8 | 누락 보완 | §1.7 신설, §0 도메인·인증키 행 | 배포형 플러그인 인증키 운용: FAQ 개발키/운영키 구분·외부 접근 가능 URL, 현재 키 `domain=http://localhost:8080`(배포본 내장 불가), 사용자별 키 UI·보관·오류 매핑·벌크 우선 설계 |
| 9 | 정확성 | §2 머리말 | 라온K '권장' → 페이지 문구대로 '설치가 필요합니다'; 다운로드 로그인 여부 확인 방법 추가 |
| 10 | 출처 분리 | §2 표 라이선스 열(헤더·dsId 4·23), §8-7 | dsId=4: V-World '라이센스가 지정되어 있지 않습니다' / data.go.kr 15048121 '제한 없음·무료'; dsId=23: V-World CC BY / data.go.kr 15125044 제4유형 — 출처 병기 |
| 11 | 정확성 | §2 표 30162·30185 | 30162: zip 10개(건물_001~010, 첨부 목록 '총 12건' 주석); 30185: 'SHP 21 파일' → 'zip 20개 + 메타데이터 xlsx 1개' |
| 12 | 누락 보완 | §2.1 신설, §0 도로 행, §8-12·13 | 도로명주소 전자지도(juso.go.kr; SPA·404로 미확인), 서울시 S-Map(3D라이브러리는 배치 도구, 오픈랩은 신청·승인형으로 보임) 추가 — 모두 '확인 필요' |
| 13 | 누락 보완 | §3.1, §8-14 | 국토정보플랫폼 항공사진·정사영상을 현황도 배경 소스로 평가 항목화(해상도·라이선스·다운로드 조건 확인 필요) |
| 14 | 확인 필요 표기 | §4.1, §8-16 | `webglMapInit.js.do?version=3.0` 본문에서 `WSViewerStartup.js` 경로 미발견(동적 로드 추정) — SDK 파일 자체는 직접 URL로 확인 |
| 15 | 확인 필요 표기 | §0 순위 4, §4.2 표, §8-14 | NGII 공개 DEM '90 m'는 2015 etnews 기사 근거뿐 — 공식 페이지 해상도 미기재, 현행 사양 확인 방법 추가 |
| 16 | 누락 보완 | §0 순위 2, §4.2, §8-11 | 등고선(국가 수준면) vs GLO-30(EGM2008·DSM) 수직기준 오프셋 경험적 보정·캐노피 보정·전이대 블렌딩·3dm 노트 기록 절차 추가 |
| 17 | 보강 | §4.3 | 국토교통부 보안관리규정 제10조 ①의 예외 3개 호 전체 기재(기존 인용은 3호로 정확) |
| 18 | 추가 발견 | §0 배경지도 행, §6 표 각주 ¹, §6 본문, §8-9·15 | white·midnight도 GoogleMapsCompatible(6–19) 세트 참조(레퍼런스 6–18과 불일치); WMTS는 EPSG:3857뿐이라 재투영 필요 → 베이스맵 래스터는 EPSG:5186 지원 WMS GetMap 권장; 타일 출처표기 조건은 '확인 필요' |
| 19 | 로컬 메모 | §1.2 | `.env` 2행·5행은 shell source 불가 형식 → grep/cut 또는 python-dotenv로 읽기 |
| 20 | 추가 1차 확인(본 수정 시 curl, 2026-10-07) | — | n3a0020000·wkmstrm 레퍼런스(ag_geom 표기, dvyn, 오류코드 표), data.go.kr 15134735(표제부 스키마·트래픽), smap.seoul.go.kr·smapModelLibrary.do·openlab.eseoul.go.kr. business.juso.go.kr은 SPA·404로 미확인(세션 WebSearch 한도 소진) |
