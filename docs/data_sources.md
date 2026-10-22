# 데이터 준비 목록과 DB 설계 (data_sources)

> **2026-10-07 아키텍처 확정(docs/code_map.md)**: 생성은 Rhino CPython 안에서 RhinoCommon 베이크로 한다 — 'rhino3dm writer → _-Import', 'scipy Delaunay', 'shapely 클리핑' 문구는 `Mesh.CreateFromTessellation`·'클리핑 없음(bbox + TIN 면 제거)'·`doc.WriteFile` 사본으로 읽는다. 정합 오차는 빌드 때 샘플(features theme `qa`) → 런타임 통계. `File3dm.Strings` 대신 RhinoCommon `doc.Strings.SetString`을 쓴다.


- 작성일: 2026-10-07, 같은 날 08 보강 조사 반영 갱신. `docs/deliverables.md`의 산출물에서 역산한 데이터 목록. 근거는 `docs/research/00~08`(번호 인용; 08은 [08높이]·[08기준일]·[08정합]·[08전국]으로 구분).
- **08로 바뀐 것(요지)**: ① GIS건물통합정보 벌크에 높이 컬럼(A16) 있음 → 벌크가 건물 1순위, `LT_C_BLDGINFO` API 응답은 **세션 캐시만**(VWorld 약관 제19조, 배포 DB 미적재) ② 건물 `pnu`는 공간조인이 아니라 벌크 `A2` 원천값 우선 ③ 변동분(일간) 미채택, 월간 전체본 교체 + `source_files` 표 ④ 철거는 건축HUB 폐쇄말소·철거멸실(벌크 월간 + 대상지 API) ⑤ 토지특성·토지이용계획 라이선스 표기는 '이용허락범위 제한 없음'(공공누리 1유형 아님), 연속지적도형정보는 포털 4유형 → 번들 금지 ⑥ 등고선 전국 zip 19개 중 5개 ≤500 MB(04a '전량 >500 MB' 정정) ⑦ 좌표 변환은 pyproj 기본 경로(EPSG:5189)만.
- 접근 등급: **자동** = 스크립트(무로그인 파일 또는 API 키) / **키** = 인증키 발급 후 자동 / **수동** = 로그인·신청·브라우저 필요.
- 모든 URL 접근일 2026-10-07. "확인 필요" = 1차 출처에서 직접 확인 못 한 항목.

---

## 0. 지금 당장 사용자가 수동으로 해야 할 것 (체크리스트)

| ✓ | 할 일 | 어디서 | 왜 지금 | 결과 보관 | 근거 |
|---|---|---|---|---|---|
| ☐ | **수치지형도 1:5000 Ver2.0(SHP) 서울 139도엽** 다운로드. 도엽 목록 `docs/reference/서울_수치지형도_5000_도엽목록.txt`, 크롬 Claude용 절차 `docs/reference/크롬_브이월드_다운로드_프롬프트.md`. **받을 때 플랫폼 목록의 제작(수정)년도를 `data/raw/수치지형도_5000/sheets.csv`(열 `sheet, year, downloaded_at, zip_sha256`)에 적는다** — SHP 속성·폴더 어디에도 날짜가 없음(로컬 42레이어 전수 확인) | 국토정보플랫폼 https://map.ngii.go.kr/ms/map/NlipMap.do (로그인) 또는 브이월드 지도 메뉴 | 지형·도로면·수계·건물 층수·철도·교량의 **유일한 고정밀 공개 원천**. 등고선 5 m 간격, 절대정확도 95 % 1.5 m·최대 3.0 m. 현재 성수 4도엽만 보유. 연도가 없으면 산출물 기준일 표기·정합 오차의 시간차 분리가 안 됨 | `data/raw/수치지형도_5000/<도엽번호>.zip` + `sheets.csv` | 00 §4, 04a §0.1, 05 §3, 08기준일 §1.4, 08정합 §1 |
| ☐ | **GIS건물통합정보 서울특별시 SHP**(dsId=18, 월간 전체본 **129 MB**, 기준일 매월 9일경·게시 0~15일 뒤) 다운로드. 서울 전체본 이력은 `…dsId=18&fileGbnCd=AL&sidoCd=11`로 1년치가 보임 | https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=18 (로그인; 서울 단위는 500 MB 미만이라 라온K 없이 iframe 다운로드) | API `LT_C_BLDGINFO` 전수 호출(1,162페이지)은 차단 위험이고 **약관 제19조상 저장 금지** → 배포 DB의 건물은 벌크. 컬럼 정의서(로그인 없이 받아짐)로 **A16 높이(m)·A26/A27 층수·A8 용도코드·A2 PNU·A22 데이터기준일자·A28 데이터생성변경일자** 확정. 좌표계 EPSG:5186(2023-08-08~; 페이지 메타 블록의 'Bessel' 표기는 상충이니 `.prj`로 검증) | `data/raw/vworld_GIS건물통합정보/AL_D010_11_<기준일>.zip` + 컬럼 정의서 `국가중점데이터_컬럼정의서(26.08.19)_배포용.xlsx` | 01 §2.3, 05 §1.2·§2, 08높이 §3.1, 08기준일 §1.2 |
| ☐ | **VWorld 인증키 서비스 범위 확인** — 2D 데이터 API `LT_C_BLDGINFO`·`LT_L_N3A0020000`·`LT_C_WKMSTRM` 호출 OK(00 실측, 08 재확인: 군 단위까지 전국 응답). `.env`에 키·도메인 유지. **주의: `.env` 2행 `VWORLD_API_KEY= …`의 '= ' 뒤 공백** — `grep/cut`·셸 `source`로 읽으면 키에 공백이 붙어 `INVALID_KEY`가 난다 → python-dotenv `dotenv_values`로 읽거나 공백 제거. 발급일·유효기간을 마이페이지에서 확인해 기록 | https://www.vworld.kr (마이페이지) | 대상지 단위 건물 갱신·주소 보조검색. 개발키는 FAQ상 "QGIS 등 외부 SW·연구/개인용"이라 배포 사용자도 각자 개발키 | `.env` `VWORLD_API_KEY`·`VWORLD_API_DOMAIN` | 00 §6, 05 §1.7, 08전국 §1·§3.1·§5.1 |
| ☐ | **공공데이터포털 키 1개 발급** → 건축HUB **건축물대장정보(15134735)·건축인허가정보(15136267)·폐쇄말소대장정보(15137093)**·소진공 상가(15012005) 활용신청(자동승인, 개발계정 10,000건/일, **1회 100건**) | https://www.data.go.kr/data/15134735/openapi.do , …/15136267/openapi.do , …/15137093/openapi.do | 건물 높이(`heit`) 보정(P1·조건부), **철거·폐쇄말소 상태**(`getApDemolExtngMgmRgstInfo`·`getSrTitleInfo`, 대상지 생성 시), 상권(P1) | `.env` `DATA_GO_KR_KEY` | 05 §1.6, 04b §2, 08높이 §2.2, 08기준일 §2.1 |
| ☐ | (P1) **건축HUB 대용량(월간) '폐쇄말소대장 표제부' + '건축인허가 철거멸실관리대장'** 벌크 — 전월분이 익월 20일 게시. 서울 전역 `buildings.status` 채움 | https://www.hub.go.kr/portal/opn/lps/idx-lgcpt-pvsn-srvc-list.do (로그인; 파일 용량·시도 분할·컬럼·PK 매칭은 로그인 후 확인 필요) | 월간 전체본 diff만으로는 대장 말소 지연을 못 잡음. 대상지 API 호출의 게시 공백(최대 ~7주)을 메움 | `data/raw/hub_bulk/<YYYYMM>/` | 08기준일 §2.1·§2.3 E |
| ☐ | (P1) **건축HUB 표제부 벌크 XLSX**(전국 7,865,698행, 높이·지상층수·주용도코드·사용승인일·주부속구분코드·관리건축물대장PK 포함) — 서울 전체 높이 보정용. 서울시 CSV(OA-22424)는 2026-10-07 현재 '파일이 없습니다' | 포털 15044720 → 실제 다운로드 https://www.hub.go.kr/portal/opn/tyb/idx-bdrg-ttlldr.do (로그인·시도 분할·`높이` 채움률 확인 필요) | 건축HUB API(일 10,000건)로 서울 수십만 동을 훑는 대신 1파일. VW `height`와 같은 세움터 원천이라 결측 보충 효과는 **100 PNU 샘플 실측 후** 확정 | `data/raw/hub_title_bulk/` | 08높이 §2.6·§7-11·§7-17 |
| ☐ | (P1) **토지소유정보 서울 SHP/CSV + 컬럼 정의서**(dsId=12) | https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=12 (로그인) | 국공유지 시트. 등재본 `_20240408`이고 소유구분 컬럼 유무가 공개 페이지에 없음 → 정의서부터 확인 | `data/raw/vworld_토지소유정보/` | 04b §4 |
| ☐ | (P1) **국가유산 공간정보 SHP** 다운로드 메뉴 확인(JS 페이지라 브라우저 필요) | https://gis-heritage.go.kr/ 데이터개방 > 파일다운로드 | 역사문화자원 시트, 보존지역 500 m | `data/raw/heritage/` | 04b §10 |
| ☐ | (대상지별) **1:1000 수치지형도 Ver2.0** 대상지 도엽 | 국토정보플랫폼(로그인, "공개 자료만") | 1:1000 베이스맵·결정도 축척. 등고선·표고점은 공개제한이라 빠져 있을 수 있음(확인 필요) | `data/raw/수치지형도_1000/<도엽>.zip` | 05 §3.1·§4.3 |
| ☐ | (선택·검증용) **S-Map 오픈랩 가입** → 로그인 후 공지 "[공지] S-Map 데이터 제공 관련 FAQ 안내"(2025-08-18) 첨부 `★ 3D 제공 관련 FAQ 모음집(2026.04.).pdf` 열람. 08 확인: 3D 데이터는 **'공개제한 공간정보 제공 신청'**(학술연구·민간 사업자 양식 별도, 공간정보과 02-2133-2852) | https://openlab.eseoul.go.kr/ | **플러그인 상시 원천으로는 부적합**(신청·승인형, 배포 불가). 대상지 1곳 높이 검증용 1회 신청만 | — | 01 §2.1, 04a §1, 08높이 §6.1 |
| ☐ | (서면 질의 3건, 상업 배포 전) ① 국토지리정보원: "1:5,000 등고선·표고값을 데스크톱 툴로 처리해 3dm·AI 파일로 납품하는 것이 별표 1 '인터넷 등을 통한 표시 불가'에 해당하는가" ② VWorld(1661-0115): 이용약관 제13조(영리 이용)·제19조(저장 금지)가 **데이터마켓 벌크**와 유료 플러그인의 API 사용·납품에 미치는 범위, 저작권정책(공공누리 1유형)·CC BY 표기와의 관계 ③ 국가공간정보센터: 연속지적도형정보 CC BY(VWorld) vs 제4유형(포털 15125044) 중 어느 것이 유효한지, 토지특성공간정보(dsId=4) SHP 도형("연속지적도 융복합")의 이용허락 범위 | — | ①은 등고선 온라인 차단을 풀지, ②는 벌크 번들·API 유래 객체 납품 허용 여부, ③은 필지 폴리곤 번들 가능 여부를 결정 | `docs/legal_notes.md`(답변 오면) | 05 §4.3, 08전국 §5.1·§5.4·§7.1 |
| ☐ | **연속수치지형도 등고선(30185) 서울 포함 zip 식별** — 목록 첨부 `시도별_등고선_파일_목록.xlsx`(2026-10-06, 로그인)로 서울·수도권 파일과 용량 확인. 전국 19 zip 중 **5개는 ≤500 MB**(452·417·331·409·498 MB)라 서울분이 그중 하나면 **macOS만으로 1단계 완료** | https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=MK&dsId=30185 (pageIndex=1~3) | 04a §0.2 "전량 >500 MB"는 1페이지만 본 오류 → 정정. 도엽 139장 수동 경로의 대안 | `data/raw/연속수치지형도/` | 08전국 §2.3·§4.3 |
| ☐ | (Windows VM, 연 1회) 500 MB 초과 벌크(등고선 14개 zip·도로경계_선/면·토지이용계획 SHP 8개 시도·경기 토지이용계획 CSV 875 MB) — 라온K(Windows 전용) 필요. 경로: **UTM(무료, Apple Silicon ARM64) + Windows 11 Pro ₩324,600**(Microsoft Store KR, 2026-10-07; Parallels 가격·ARM 라이선스 적용은 확인 필요) | https://mac.getutm.app/ , https://www.microsoft.com/ko-kr/d/windows-11-pro/dg7gmgf0d8h4 | 수도권·전국 확장(deliverables §F 2·3단계) 때만. 서울 1단계는 불필요(위 행 결과에 따라) | `data/raw/연속수치지형도/` | 04a §0.2, 08전국 §4.1 C·§4.3 |

자동으로 받는 것(스크립트가 처리, 사용자 조작 없음): 서울 UPIS SHP(보유 파이프라인), `LT_C_BLDGINFO` 타일(런타임 세션 캐시만), 서울 역사마스터·버스정류소, 생활인구 250 m 격자, 소진공 상가 CSV, 침수흔적도·침수예상도 SHP, SGIS 행정동 경계, 도보 네트워크, 생태현황도 SHP, Copernicus GLO-30, 브이월드 목록 **새 판 감지**(`GET …dsId=18&fileGbnCd=AL&sidoCd=11` 첫 행 기준일 vs `source_files.listed_date`, dsId=13·14·23 동일 — 다운로드는 로그인이라 사람이).

---

## 1. 데이터 준비 목록 (우선순위순)

보관 경로 규칙: `data/raw/<id>/` 원본 그대로(zip 포함), 가공은 DB로만. `<id>`는 아래 표의 보관 열.

### P0 — 첫 릴리스에 필요

| 데이터 | 제공처·URL | 접근 | 범위 | 갱신 | 보관 `data/raw/` | DB 테이블 | 라이선스·출처표기 | 비고·근거 |
|---|---|---|---|---|---|---|---|---|
| 서울 필지 DB(토지특성정보 dsId=4 + 토지이용계획 dsId=14 + 서울 UPIS) | 보유 `data/seoul_site.db` | 보유 | 서울 898,800필지 | 토지특성 반기(현재 판 목록 기준일 2026-05-20·레코드 `데이터기준일자` 2026-05-13·게시 07-10), 토지이용계획 속성 CSV 월간(매월 9일경, 게시 최대 ~2개월 지연)·공간 SHP 분기, UPIS 월 | `vworld_토지특성정보/`, `전국_토지이용계획정보/`(보유) | `parcels`·`overlays`·`parcel_overlays`·`parcel_land_use` | 토지특성·토지이용계획: data.go.kr 15048121·15045900 **"이용허락범위 제한 없음"**(VWorld 상세는 '라이센스가 지정되어 있지 않습니다') → '공공누리 1유형/CC BY'로 적지 않음; UPIS 공공누리 1유형(법적 효력 없음 고지). **토지특성공간정보 SHP 도형은 "연속지적도 융복합" 파생물**이라 번들은 질의 결과 전까지 '추정' | 지목 도로 143,132·하천 8,939·구거 6,229·유지 314필지, 도시계획시설·지구단위 오버레이 보유 → 도로면·수계·공원 결정선은 **추가 수집 없음** [00 §5]. 토지특성 컬럼 A0~A26에 토지이동 사유·종전지번 없음 → 토지이동은 dsId=13(P1) [08기준일 §3.1·§5.2, 08전국 §5.4] |
| 수치지형도 1:5000 Ver2.0 SHP (서울 139도엽) | 국토지리정보원 국토정보플랫폼 https://map.ngii.go.kr/ms/map/NlipMap.do ; data.go.kr 15015482 | **수동**(로그인, 도엽 선택) | 서울 전역 139도엽(4도엽 보유) | 1년 주기(도시·비도시) + 수시수정; **SHP·폴더에 날짜 없음 → `sheets.csv`에 제작연도 기록** | `수치지형도_5000/<도엽>.zip` + `sheets.csv` | `features`(theme=`terrain`·`road`·`water`·`rail`·`bridge`·`structure`·`label`, `sheet`=도엽), `buildings`(층수 보완·누락 보충) | 공공누리 1유형(출처표시). **등고선·표고값 온라인 표시 제한**(별표 1) | 레이어: `N3L_F0010000` 등고선, `N3P_F0020000` 표고점(**TIN 필수**; 교량 `A0070000`·입체교차부 `A0090000`·인터체인지 `A0100000` 5 m 버퍼 안 점은 구조물로 분리, `A0160024`는 철도경계), `N3A_A0010000` 도로경계 면, `N3L_A0020000` 도로중심선(`도로폭`·`차로수` 100% 채움), `N3A_B0010000` 건물(`층수`·`종류` 100%), `E001/E003/E005` 수계, `A015~A017` 철도, `A007` 교량, `F003/F004` 성절토·옹벽, `H004` 지명. EPSG:5186, cp949. 절대정확도 95 % 1.5 m·최대 3.0 m(고시 제2026-2524호). 도엽 경계 분절은 dissolve [00 §4, 04a §2.4, 05 §7, 07 §1, 08정합 §2.4, 08기준일 §1.4] |
| GIS건물통합정보 서울 SHP (dsId=18) | https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=18 ; data.go.kr 15083092 ; 컬럼 정의서 https://www.vworld.kr/contents/국가중점데이터_컬럼정의서(26.08.19)_배포용.xlsx | **수동**(로그인) | 전국(서울 단위 129 MB) | 전체 월간(서울 기준일 매월 9일경, 게시 0~15일 뒤)·변동 '일간'(영업일·결측일 있음, **미채택**) | `vworld_GIS건물통합정보/AL_D010_11_<기준일>.zip` | `buildings`(**1순위 원천**) | CC BY(VWorld) / 공공누리 1유형(포털) — 두 창구 일치 | `AL_D010` 29컬럼: A2 PNU(19자리 초과 가능 — 절단 금지, 공간조인으로), A6 특수지코드(1 일반·2 산·3~8 가지번/블록·9 기타), A8 용도코드(33 대분류 공식 코드표), A10 구조코드, A13 사용승인일, A16 **높이(m)**, A22 데이터기준일자, A26/A27 지상·지하층수, A28 데이터생성변경일자. API `LT_C_BLDGINFO` 필드와 1:1. 포털 면책 "구축기관이 상이하여 참고용". 2023-08-05 이전 파일(EPSG:5174)과 혼용 금지 [04a §2.2, 08높이 §3, 08기준일 §1.2·§3.4] |
| VWorld 2D API `LT_C_BLDGINFO` | https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=bldginfo | **키**(보유 코드 `_fetch_tile` 재사용, 사용자 본인 키) | 전국(군 단위까지 실측), 대상지 BOX 단위 | 수시(페이지 갱신일 2026-09-23; 응답에 기준일 필드 없음 → 호출 시각으로 기록) | **런타임 세션 캐시만**(`vworld_buildings/` 기존 캐시 78,862동은 검증 스크립트용으로만 유지) | **없음**(배포 DB·영구 캐시 미적재) — 대상지 생성 시 메모리에서 벌크 `buildings`에 덮어씀 | VWorld 이용약관 제13조(영리 이용은 운영기관 동의)·**제19조(사전 승낙 없는 저장 금지)** → 저장·재배포 안 함, 응답 유래 객체는 "출처 ⓒ 국토교통부·브이월드" UserString, 납품물 포함은 사용자 옵션(기본 off, 서면 동의 전) | `size`≤1000·`page`, `geomFilter` BOX 크기 제한 없음, `crs=EPSG:5186` 직접 요청 가능. 반경 500 m ≈ 건물 2~4페이지, 7레이어 ≈ 10~15회. `height` 결측 70% → A.4 규칙. 전수 호출 금지(FAQ "무리한 호출 시 일시 차단"), `INVALID_KEY`는 재발급 안내 [05 §1, 08전국 §3.1·§4.2·§5.1] |

### P1 — 데이터 있으면 생성

| 데이터 | 제공처·URL | 접근 | 범위 | 갱신 | 보관 | DB 테이블 | 라이선스 | 비고·근거 |
|---|---|---|---|---|---|---|---|---|
| 건축HUB 건축물대장 표제부 API `getBrTitleInfo` | https://www.data.go.kr/data/15134735/openapi.do | **키**(자동승인, 10,000건/일, **1회 100건**) | 전국, 대상지 PNU 단위 | 월간 | `hub_title/<PNU>.json`(캐시 1개월; '제한 없음'이라 캐시 가능) | `buildings.height_m` 보정(`height_src=hub`, 등급 A) — **조건부 P1**: VW `height`와 같은 세움터 원천이라 `height=0` 건물 100 PNU 샘플로 `heit>0` 비율을 잰 뒤 채택 | 이용허락범위 제한 없음 | PNU → `sigunguCd=pnu[0:5]`·`bjdongCd=pnu[5:10]`·`platGbCd`(**`pnu[10]=='1'→0 대지, '2'→1 산**, 반례 0; 특수지코드 ≥3·19자리 초과는 미조회)·`bun=pnu[11:15]`·`ji=pnu[15:19]`. 응답 `heit`(m, 법정 높이)·`grndFlrCnt`·`ugrndFlrCnt`·`mainPurpsCd`(5자리, `usability`와 같은 체계)·`strctCd`·`useAprDay`·`mainAtchGbCd`(주·부속 구분 → A.4 규칙 0' 해제)·`mgmBldrgstPk`(층별개요 키). 같은 지번 여러 동은 `dongNm`·`archArea`로 짝. 반경 500 m 결측 건물만 호출 ≈ 800~2,300회 [05 §1.6, 08높이 §2, 08전국 §4.2] |
| 건축HUB 표제부 **벌크 XLSX**(전국) | 포털 15044720 → https://www.hub.go.kr/portal/opn/tyb/idx-bdrg-ttlldr.do (로그인) | **수동** | 전국 7,865,698행(시도 분할 여부 확인 필요) | 월간(최근 월 수집분) | `hub_title_bulk/` | `buildings.height_m`·`grnd_flr` 서울 전체 보정, `mainAtchGbCd`로 주·부속 분리 | 이용허락범위 제한 없음 | API 한도를 통째로 대체. 컬럼(포털 설명문): 관리건축물대장PK·주부속구분코드·주용도코드·높이·지상/지하층수·사용승인일 등 77항목. `높이` 채움률이 VW 캐시 30 %와 같은지 실물 확인 [08높이 §2.6] |
| 건축HUB 건축인허가정보 API 15136267 `getApDemolExtngMgmRgstInfo`(철거멸실관리대장) + 폐쇄말소대장정보 API 15137093 `getSrTitleInfo` | https://www.data.go.kr/data/15136267/openapi.do , …/15137093/openapi.do | **키**(자동승인, 10,000건/일) | 대상지 반경 내 필지(PNU 단위, 필지당 2호출) | 월간 | `hub_demol/<PNU>.json`(캐시 1개월) | `buildings.status`(`demolished`)·`demol_day` | 제한 없음 | 응답: `demolExtngGbCd/Nm`·`demolStrtDay`·`demolEndDay`·`demolExtngDay` / `shterGbCd/Nm`·`shterDay`. 공통 `startDate/endDate`(YYYYMMDD; 거르는 필드는 `crtnDay` 추정, 확인 필요). 생성 시 최근 24개월 자동 호출. 건축물대장 API에는 철거 오퍼레이션 없음 [08기준일 §2.1·§2.3 C] |
| 건축HUB 대용량(월간) **폐쇄말소대장 표제부·철거멸실관리대장** 벌크 | https://www.hub.go.kr/portal/opn/lps/idx-lgcpt-pvsn-srvc-list.do (로그인) ; 철거멸실 유형별 https://www.hub.go.kr/portal/opn/tyb/idx-acpmslg-demol.do | **수동** | 전국(시도 분할·용량·컬럼 확인 필요) | 월간(전월분 익월 20일) | `hub_bulk/<YYYYMM>/` | `buildings.status` 서울 전역 | 제한 없음 | API 호출 없이 서울 전역 철거·말소. PK(관리건축물대장PK ↔ GIS건물 A19 건축물ID) 매칭 규칙은 『첨부1 PK전환 규칙』 확인 [08기준일 §2.3 E] |
| 토지이동이력정보 dsId=13 (서울 월간 CSV) | https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=13 | **수동**(로그인) | 서울 33~35 MB(전국 124,991,895건) | 전체 월간(기준일 말일; **7개 판이 2026-07-24 일괄 게시**된 사례 — 수개월 지연 가능)·변동 '일간' | `vworld_토지이동이력/` | `parcel_moves`(pnu, 사유코드, 토지이동일자, 말소일자) → `buildings.pnu` 재조인 대상 집합 | CC BY | `AL_D157` 18열: `토지이동사유코드`(20·21 분할, 30·31 합병, 40 지목변경, 43 지번변경, 44~46 정정 …)·`토지이동일자`·`토지이동말소일자`·`폐쇄순번`. 종전지번이 문자열로 채워지는지는 서울본 1개 수령 후 확인. 지목변경(40)은 `land_category_pending` 플래그만(값은 반기본에서) [08기준일 §3.2·§3.4] |
| 서울 역사마스터 OA-21232 / 버스정류소 OA-15067 | https://data.seoul.go.kr/dataList/OA-21232/S/1/datasetView.do , …/OA-15067/… | **자동**(무로그인 CSV·API) | 서울 | 수시 | `seoul_transit/` | `features`(theme=`transit`, kind=`subway_station`/`bus_stop`) | 공공누리 1유형 | 버스정류소 좌표계 표기 모순("WGS84(EPSG-5179)") → 값 범위로 판별. 지하철 출입구 좌표는 공식 전수 없음 [04b §5] |
| 서울 생활인구 250 m 격자 OA-23019(내국인) | https://data.seoul.go.kr/dataList/OA-23019/S/1/datasetView.do | **자동** | 서울 약 8,500셀, 1시간 | 매일 | `seoul_living_pop/` | `features`(theme=`population`, kind=`grid250`, attrs_json 시간대별) | 공공누리 1유형 | 집계구 단위는 2026-07-31 종료. 격자ID→지오메트리 규칙 확인 필요 [04b §1] |
| 소상공인 상가정보 CSV(분기) / API `storeListInPnu` | https://www.data.go.kr/data/15083033/fileData.do , https://www.data.go.kr/data/15012005/openapi.do | **자동**/키 | 전국 약 200만 점 | 분기 | `semas_store/` | `features`(theme=`commerce`, kind=`store`) | 제한 없음 | 경위도 점, 업종 대분류. PNU 조인 가능 [04b §2] |
| 서울 침수흔적도 OA-15636 / 침수예상도 | https://data.seoul.go.kr/dataList/OA-15636/F/1/datasetView.do , https://www.data.go.kr/data/15125748/fileData.do | **자동** | 서울 | 비정기 | `seoul_flood/` | `features`(theme=`hazard`, kind=`flood_trace_<년>`/`flood_forecast`) | 공공누리 1유형 | 침수예상도 EPSG:5186, 흔적도 2010~2025 연도별 [04b §12] |
| SGIS 행정동 경계 SHP / API | https://www.data.go.kr/data/15129688/fileData.do , https://sgis.mods.go.kr/developer/html/newOpenApi/api/dataApi/addressBoundary.html | **자동**/키 | 전국 | 반기 | `sgis_boundary/` | `features`(theme=`admin`, kind=`emd_adm`) | 제한 없음 | EPSG:5179 → 5186 변환 [04a §2.6] |
| 토지소유정보 서울 (dsId=12) | https://www.vworld.kr/dtmk/dtmk_ntads_s002.do?svcCde=NA&dsId=12 | **수동**(로그인) | 전국 | 메타 '연간', 등재본 2024-04-08 | `vworld_토지소유정보/` | `parcel_owner`(pnu, owner_class) | 제한 없음 | 컬럼 정의서 확인 선행 [04b §4] |
| 국가유산 공간정보 SHP + 역사문화환경 허용기준 SHP | https://gis-heritage.go.kr/ ; API https://www.data.go.kr/data/3070426/openapi.do | **수동**(브라우저 메뉴 확인) | 전국 | 실시간/연 | `heritage/` | `features`(theme=`heritage`) | 제한 없음 | WMS/WFS `lt_c_uo301`로 대체 가능 [04b §10] |
| 서울 1:1000 수치지형도 Ver2.0 (대상지 도엽) | 국토정보플랫폼 | **수동** | 대상지만 | 2021~2025 전면 갱신 | `수치지형도_1000/<도엽>.zip` | `features`·`buildings`(scale=1000 구분) | 공공누리 1유형, 등고선 공개제한 | 도엽코드 9자리 체계 [05 §3.2] |
| 서울 개별공시지가 시계열 OA-1180 | https://data.seoul.go.kr/dataList/OA-1180/S/1/datasetView.do | **자동** | 서울 1989~ | 연 4회 | `seoul_land_price/` | `parcel_price_history`(pnu, year, price) | 공공누리 1유형 | 지가 변동 분석 [04b §3] |
| 서울 생태현황도(비오톱 평가도) SHP | https://www.data.go.kr/data/15125731/fileData.do | **자동** | 서울 | 수시 | `seoul_biotope/` | `features`(theme=`green`, kind=`biotope`) | 공공누리 1유형 | EPSG:5174 → 5186 datum 변환 [04b §8] |

### P2 — 선택·후속

| 데이터 | 제공처·URL | 접근 | 보관 | DB | 비고·근거 |
|---|---|---|---|---|---|
| 서울 도보 네트워크 OA-21208 | https://data.seoul.go.kr/dataList/OA-21208/S/1/datasetView.do | 자동 | `seoul_walk_net/` | `features`(theme=`walk`, kind=`node`/`link`) | 등시선·지하철 출입구 노드 대체원 [04b §6] |
| 표준노드링크(ITS) | https://www.its.go.kr/nodelink/ | 자동(TLS 체인 불완전 → `verify=False`) | `its_nodelink/` | `features`(theme=`road`, kind=`link`) | 차로수·도로등급. 세가로 누락 [04a §2.3] |
| Copernicus DEM GLO-30 | https://registry.opendata.aws/copernicus-dem/ (타일 `N37_00_E126_00`, `N37_00_E127_00`) ; 사양 https://dataspace.copernicus.eu/explore-data/data-collections/copernicus-contributing-missions/collections-description/COP-DEM | 자동(무로그인 S3) | `copernicus_dem/` | 파일 그대로(래스터) | 광역 산세 배경만. **DSM(건물·수목 포함)·수직기준 EGM2008·절대 수직정확도 <4 m(LE90)·수평 <6 m·TanDEM-X 2011~2015** → 표고점 ↔ GLO-30 샘플 중앙값으로 경험적 오프셋(`GLO30_OFFSET_M`), 서울 EGM2008 N≈23.2 m 기록. KNGeoid18−EGM2008 차이는 확인 필요(우선순위 낮음) [05 §4.2, 08정합 §2.5·§3.4] |
| 국토지리정보원 공개DEM(IMG) | https://www.data.go.kr/data/15059920/fileData.do ; 국토정보플랫폼 '공개DEM' 메뉴 | 자동/수동(확인 필요) | `ngii_dem/` | 래스터 | 이용허락범위 제한 없음. **격자 해상도 포털 미표기**(04a는 2015 보도자료 근거 90 m) → 다운로드 후 확인. 광역 컨텍스트 대안으로 등고선 전량 수령 의존도를 낮춤 [08전국 §2.3] |
| 연속수치지형도 전국 레이어(dsId 30162~30256) | https://www.vworld.kr/dtmk/dtmk_ntads_s001.do?svcCde=MK ; 건물 30162 2페이지에 `연속수치지형도 데이타베이스설계서_Ver 5.1.9.hwp`·`_데이터_설명서.pdf` 첨부 | 수동(500 MB 초과분은 라온K·Windows) | `연속수치지형도/` | `features` | 도엽 접합 대체. 8레이어 44 zip **20,651 MB**(등고선 30185 13,358 MB·19 zip 중 **5개 ≤500 MB**, 표고점 30245 126 MB, 도로중심선 30182 1,591 MB·8 zip 모두 ≤339 MB, 도로경계_면 30179 944·738 MB, 실폭하천 30207 215 MB, 하천경계 30248 167 MB). EPSG:5179, CC BY. 서울분 식별은 `시도별_등고선_파일_목록.xlsx`. 속성 스키마는 첨부 설계서로(05 §1.4 코드표 미확인 해소 경로) [04a §0.2, 08전국 §2.3] |
| OSM(Overpass) / Overture Maps buildings | https://overpass-api.de/api/interpreter (과부하 잦음; 대안 https://overpass.kumi.systems/api/interpreter ) ; Overture `s3://overturemaps-us-west-2/release/<릴리스>/theme=buildings/type=building/*`(DuckDB) | 자동 | `osm/`, `overture/` — **별도 디렉터리, DB 미적재** | 없음(검증 리포트용) | **ODbL**(share-alike) → 공공데이터 테이블에 섞지 않음. 성수 bbox: OSM 9,684동 `height` 20.3 %·`levels` 19.0 %, Overture 22,539동 `height` 8.6 %(전부 OSM 유래, 'East Asian Buildings' zenodo 8174931은 발자국만·CC BY 4.0). Google 2.5D·Microsoft GlobalML은 한국 미포함. 층수 일치 71 %라 A.4 검증(등급 C)에만 [08높이 §4] |
| 정비사업 정보몽땅 사업장 엑셀 | https://cleanup.seoul.go.kr/cleanup/bsnssttus/lscrMainIndx.do | 자동(엑셀) | `seoul_redevelop/` | `features`(theme=`project`, 대표지번→PNU 점) | 폴리곤 없음 [04b §11] |
| 서울 가로수 OA-22904 | https://data.seoul.go.kr/dataList/OA-22904/A/1/datasetView.do | 자동 | 사용자 로컬만 | `features`(theme=`tree`) | **공공누리 4유형(상업 이용·변경 금지)** → DB 배포본에서 제외, 사용자 직접 적재 [04b §8] |
| 한강홍수통제소 수위 API(`GDT`·`PFH`) | https://www.hrfco.go.kr/web/openapiPage/reference.do | 키 | `hrfco/` | `features.attrs_json`(water 레이어 수위) | 한강·중랑천 수면 표고·계획홍수위 [07 §1.5] |
| 기상청 ASOS 시간자료 / EPW(onebuilding) | https://www.data.go.kr/data/15057210/openapi.do , https://climate.onebuilding.org/WMO_Region_2_Asia/KOR_South_Korea/index.html | 키/자동 | `weather/` | 파일 | 일조·그림자(P2)용 [02 §0, 04b §14] |

---

## 2. DB 설계

### 2.1 파일 구성

| 파일 | 내용 | 비고 |
|---|---|---|
| `data/seoul_site.db` | 필지 DB(보유, 스키마 v5) | 손대지 않음 |
| **`data/seoul_context.db`** (신규) | 건물·도로·지형·수계·철도 + 분석 보조 레이어(교통·인구·상권·재해·행정경계) 전부 | 테이블 4개(`data_sources`·`source_files`·`buildings`·`features`)로 시작. 분석 레이어가 커지면 그때 파일 분리 |
| `data/backup/seoul_context_<YYYYMMDD>.db` | 전체본 교체 직전 `cp` 1장 | 이것이 스냅샷. 3판 넘으면 오래된 것 삭제. 스냅샷 테이블·SCD2(`valid_from/valid_to`)는 만들지 않는다 [08기준일 §4.1] |
| (전국 확장 시) `data/packages/<시도코드>_site.db`·`_context.db` | 사용자 로컬 '지역 패키지 빌더'가 VWorld zip에서 생성(시도 0.5~14 GB) | 시도 경계 대상지는 `ATTACH`로 2개 동시 로드. 번들은 서울만 [08전국 §3.4, deliverables §F] |

관행(CLAUDE.md): EPSG:5186 GeoJSON 문자열 + `min_x/max_x/min_y/max_y` 경계상자 컬럼 + B-tree 인덱스 `idx_<table>_bbox`. **RTree 가상 테이블은 쓰지 않는다**(Rhino 8 Windows CPython SQLite에 rtree 모듈 없음). 조회는 `WHERE max_x >= ? AND min_x <= ? AND max_y >= ? AND min_y <= ?` 후 shapely 없이 Rhino 쪽에서 GeoJSON → 커브.

기준일 규칙 [08기준일 §1.1]: `data_sources.reference_date`에는 **레코드의 데이터기준일자**(있으면), `source_files.listed_date`에는 **목록의 기준일(파일명 날짜)**. 둘이 다른 것이 정상(토지특성 파일명 `_20260520`, 레코드 전부 2026-05-13). 날짜는 `norm_date()`로 `YYYY-MM-DD` 10자 통일(정의서 샘플에 `2024/01/18`·`2024-01-18`·`20240118` 혼재) — 길이 10이 아니면 적재 중단.

### 2.2 테이블

**`data_sources`** — 필지 DB와 동일 스키마 재사용 (`source_id` PK, `name`, `page_url`, `reference_date`, `acquired_at`, `crs`, `license`, `note`). 모든 행이 `source_id`로 여기 연결되어 시트 여백의 출처·기준일 표기를 자동 생성. `license`에는 두 창구 표기를 함께(예 `CC BY(브이월드 dsId=18)/공공누리 제1유형(data.go.kr 15083092)`), `note`에 변환 경로(`transform=EPSG:5189; pyproj 3.6.1/PROJ 9.3.0; accuracy_m=1.0`).

**`source_files`** (신규, 08기준일 §4.2) — 원천 파일 단위 적재 이력. 해시가 같으면 재적재를 건너뛴다.

```sql
CREATE TABLE IF NOT EXISTS source_files (
    source_id   TEXT NOT NULL,            -- data_sources.source_id
    file_name   TEXT NOT NULL,            -- 예 AL_D010_11_20260909.zip / 37705072.zip / UQ111_…_202609.zip
    sha256      TEXT NOT NULL,
    size_bytes  INTEGER,
    listed_date TEXT,                     -- 목록 기준일(파일명 날짜; 수치지형도는 sheets.csv 제작년도; API 캐시는 호출일)
    loaded_at   TEXT NOT NULL,            -- ISO 시각
    PRIMARY KEY (source_id, file_name)
);
```

**`buildings`** — 건물 한 동 = 한 행. 현황도 7·8·9와 3dm이 가장 많이 거는 질의라 전용 컬럼.

| 컬럼 | 형 | 내용 | 원천 필드 |
|---|---|---|---|
| `building_id` | INTEGER PK | | |
| `src_key` | TEXT UNIQUE | 원천 식별자(`bldg:<A1 GIS건물통합식별번호>`, `ngii:<UFID>`; 런타임 API 행은 메모리에서만 `bldginfo:<해시>`) | A1 / UFID |
| `pnu`, `pnu_src`, `pnu_raw` | TEXT | 대표 필지. **벌크 `A2` 원천값 우선**(`pnu_src='source'`); A2가 비거나 `parcels`에 없거나 **19자리 초과**(절단 금지, 원값은 `pnu_raw`)면 발자국 대표점 공간조인(`pnu_src='spatial'`) | `A2` / 공간조인 |
| `bld_nm`, `dong_nm` | TEXT | 건물명·동명 | `A24`, `A25` |
| `usability` | TEXT | 용도 코드 5자리(공식 코드표: 01000 단독주택 … 33000 국방·군사; `Z` 계열 구 코드는 대분류 결측 처리) | `A8` |
| `strct_cd` | TEXT | 구조 코드(참조코드 '건축물구조코드') | `A10` |
| `grnd_flr`, `ugrnd_flr` | INTEGER | 지상·지하 층수(0=결측). `grnd_flr`는 A.4가 채택한 값 | `A26`, `A27` / 수치지형도 `층수` |
| `flr_src` | TEXT | `grnd_flr`(대장) / `topo`(수치지형도 — 아파트·연립 `층수 ≥ grnd_flr+3`, 또는 결측 보충) | |
| `height_m` | REAL | 확정 높이(A.4 규칙 적용 후) | `A16 높이`·`heit`·`a+b·n` 모델 |
| `height_src`, `height_grade` | TEXT | `height`/`hub`/`topo_flr`/`grnd_flr`/`default` (+`!` 속성 불신, `?` 부속동 의심, `~slope` 고저차 >3 m) / `A`~`D` | |
| `attr_flag` | TEXT | A.4 규칙 0·0′ 결과(`archarea < 발자국×0.5` → `!`, `> ×2` → `?`) | `A12` vs 발자국 면적 |
| `use_apr_day` | TEXT | 사용승인일 YYYYMMDD(결측 34 %) | `A13` |
| `status`, `demol_day` | TEXT | `active`/`demolished`/`closed`(폐쇄말소) + 철거멸실일·폐쇄말소일 | 건축HUB `demolExtngDay`·`shterDay`(API·벌크), 월간 전체본 diff |
| `arch_area_sqm`, `total_area_sqm`, `plat_area_sqm` | REAL | 건축·연·대지면적 | `A12`, `A14`, `A15` |
| `bc_rat`, `vl_rat` | REAL | 건폐·용적률 | `A17`, `A18` |
| `ngii_kind`, `ngii_use` | TEXT | 수치지형도 종류(아파트·연립·일반주택·주택외건물·무벽건물·가건물·공사중건물)·용도 | `종류`, `용도` |
| `data_changed_date` | TEXT | 레코드 변경일(최근 N개월 신규·변경 추출용; 철거는 못 잡음) | `A28` |
| `geometry_json`, `geometry_crs` | TEXT, INTEGER | MultiPolygon GeoJSON, 5186 | |
| `source_id`, `reference_date` | TEXT | `reference_date` = `A22 데이터기준일자`(norm_date) | |
| `min_x`,`max_x`,`min_y`,`max_y` | REAL | bbox | |

인덱스: `idx_buildings_bbox(min_x,max_x,min_y,max_y)`, `idx_buildings_pnu(pnu)`, `idx_buildings_status(status)`.
적재 순서(08 개정): GIS건물통합정보 벌크 SHP(전체본 교체: 한 트랜잭션 `DELETE … WHERE source_id=?` → INSERT, 실패 시 이전 판 유지) → `pnu`는 A2 그대로, 결측·미존재·19자리 초과만 공간조인 → 수치지형도 `N3A_B0010000`와 대표점(`representative_point`) 조인: `grnd_flr=0`이면 `층수` 채움, 종류가 아파트·연립이고 `층수 ≥ grnd_flr+3`이면 `층수`로 치환(`flr_src='topo'`) → A.4 규칙 0·0′ 플래그 → 높이 모델 → 매칭 안 된 수치지형도 건물(성수 20 %)은 `src_key=ngii:*`로 추가(무벽건물·가건물 포함, `ngii_kind`로 필터) → 건축HUB 폐쇄말소·철거멸실 벌크(월간)로 `status` → 필지 DB 반기 교체 후에는 `pnu_src='spatial'`·`pnu NOT IN parcels` 행만 재조인, 토지이동이력 월간본의 사유코드 ∈ {20,21,30,31,43,44,45,46} PNU 집합(과 그 bbox)만 재조인 [08높이 §0.3, 08기준일 §3.4·§4.3].

**`features`** — 나머지 전부(도로·지형·수계·녹지·철도·교량·구조물·라벨·교통·인구·상권·재해·행정경계). 필지 DB `overlays`와 같은 모양.

| 컬럼 | 형 | 내용 |
|---|---|---|
| `feature_id` | INTEGER PK | |
| `source_id` | TEXT | → `data_sources` |
| `theme` | TEXT | `terrain`·`road`·`water`·`green`·`rail`·`bridge`·`structure`·`label`·`transit`·`population`·`commerce`·`hazard`·`admin`·`heritage`·`walk`·`project`·`tree` |
| `kind` | TEXT | 세부: `contour`·`spot`·**`spot_struct`**(교량 `A0070000`·입체교차부 `A0090000`·인터체인지 `A0100000` 5 m 버퍼 안 표고점 — TIN 제외, `CTX::Terrain::struct_pts`)·`breakline` / `surface`·`centerline`·`sidewalk`·`bridge`·`overpass`·`interchange` / `river`·`stream`·`lake` / `subway_station`·`bus_stop` / `grid250` / `store` / `flood_trace_2022` … |
| `code` | TEXT | 원천 코드(수치지형도 통합코드 `A0020000`, 지목, 용도 코드 등) |
| `name` | TEXT | 명칭(하천명·도로명·역명·지명) |
| `value` | REAL | 숫자 하나가 주인 피처용: 등고선 `등고수치`, 표고점 `수치`, 도로폭, 옹벽 높이 |
| `attrs_json` | TEXT | 나머지 속성 그대로(차로수·일방통행·시간대별 인구…) |
| `sheet` | TEXT | 수치지형도 도엽코드(접합·갱신 단위) |
| `geometry_json`, `geometry_crs` | TEXT, INTEGER | Point/LineString/Polygon(Multi 포함), 5186 |
| `min_x`,`max_x`,`min_y`,`max_y` | REAL | bbox |

인덱스: `idx_features_bbox`, `idx_features_theme(theme, kind)`, `idx_features_sheet(sheet)`.
등고선은 도엽당 ~100~400피처라 서울 139도엽 ≈ 수만 행 — 행 단위로 둬도 bbox 질의로 충분. 도로면·하천면은 도엽 경계에서 잘려 있으므로 **적재 시 dissolve하지 않고 그대로 두고**, 3dm 생성기가 클리핑 후 `unary_union`한다(단순함 우선). `sheet`가 있으므로 도엽 단위 교체(`DELETE FROM features WHERE source_id=? AND sheet=?`)가 되고, `reference_date`는 `sheets.csv`의 제작연도(미기재면 다운로드일 + 표기 "(제작연도 미기재)").

**부속 소형 테이블(P1, 필요할 때 추가)**: `parcel_owner(pnu PK, owner_class, source_id)`, `parcel_price_history(pnu, year, price_won, PK(pnu,year))`, `parcel_moves(pnu, move_code, move_date, close_date, source_id)`(토지이동이력 dsId=13).

### 2.3 적재 스크립트(dev_*.py) 책임

| 스크립트 | 입력 | 출력 | 비고 |
|---|---|---|---|
| `dev_context_builder.py` | `data/raw/수치지형도_5000/*.zip` + `sheets.csv`, `vworld_GIS건물통합정보/AL_D010_11_*.zip`, 건축HUB 벌크(폐쇄말소·철거멸실) | `seoul_context.db` `buildings`·`features`(theme 1~8)·`source_files` | zip 안 cp949 SHP를 pyogrio로 읽고 `.prj` 확인 → 5186 강제. 레이어 코드 → theme/kind 매핑표는 `constants.py`. **파일 단위 전체 교체**(sha256 같으면 건너뜀, 한 트랜잭션, 적재 전 `data/backup/` 복사 1장). `LT_C_BLDGINFO` 캐시는 입력에서 제외(런타임 전용) [08기준일 §4.3] |
| `dev_analysis_builder.py` | 서울 열린데이터광장·data.go.kr 파일/API | `features`(theme 9~) | 열린데이터광장 `서비스 지연(103)` 재시도·백오프 기본 [04b §0] |
| `dev_database_builder.py`(보유) | 토지특성·UPIS | `seoul_site.db` | `reference_date` 상수(`"2026-02"`)·해시 미사용 → 같은 `source_files` 규칙으로 맞춤(소폭) [08기준일 §4.3] |
| `dev_check_updates.py`(신규, ~10줄) | 브이월드 목록 `GET …dsId={18,13,14,23}&fileGbnCd=AL&sidoCd=11` | 콘솔 "새 판 YYYY-MM-DD 있음" | 첫 행 기준일 > `source_files.listed_date`면 안내. 결과는 §2.4 경고의 두 번째 조건 |
| `scripts/dev_probe_building_height.py`·`probe_alignment.py`·`probe_alignment_followup.py`(보유) | 캐시·성수 4도엽·필지 DB | `result/probe_alignment/*.json` | 08 실측 재현용. 강남·구도심 타일 추가 수집 후 재실행해 A.4 상수·정합 기본값 재확인 |

좌표계 변환표(적재 시 전부 5186으로): 수치지형도·토지특성·GIS건물·침수예상도 = 5186 그대로 / 연속수치지형도·도로명주소·SGIS = 5179 / 서울 UPIS·생태현황도·생활권 = **5174(Bessel, datum 변환)** / 포인트 CSV·API 기본 = 4326. VWorld 페이지 '메타데이터' 블록의 Bessel 표기는 믿지 말고 `.prj`·좌표값으로 판정 [04a §3]. **변환 경로는 `pyproj.Transformer.from_crs(src, 5186, always_xy=True)` 기본 경로만**(5174→5186 = EPSG:5189 "Korean 1985 to KGD2002 (1)" Molodensky-Badekas, 격자 없음, 공칭 1.0 m; 서울 UPIS는 지적선과 중앙값 0.000 m로 왕복 일치, 구형 `+towgs84` 수동 입력은 +3~4 cm, 5174를 2097로 오인하면 255 m) — `+towgs84`·사용자 파이프라인 금지. 판별 요령: 서울 Y가 540~565 k면 5186, 436~467 k면 5174; `.prj` `Central_Meridian` 127.00289면 5174. 변환 후 용도지역 경계 ↔ 지적선 중앙값 0.5 m 초과면 중단 [08정합 §2.3·§4.1].

### 2.4 기준일 관리·갱신 체크리스트 (08기준일 §5.3·§6 요약)

경고 임계값(원천 기준일 → 생성 시각 경과 개월). 월간·분기 원천의 노란 경고는 **(a) 경과 ≥ 임계값 AND (b) 브이월드 목록에 새 판 있음** 두 조건이 모두 참일 때만(게시가 기준일보다 46~53일, 토지이동이력은 최대 ~7개월 늦은 실측이 있어 고정 임계값은 상시 발동함). 빨간 위험은 경과만으로, 생성은 허용.

| 원천 | 공식 갱신주기 | 노란 경고 | 빨간 위험 |
|---|---|---|---|
| GIS건물통합정보 벌크 | 월간(서울 매월 9일경) | 3개월 AND 새 판 | 5개월 |
| `LT_C_BLDGINFO`·건축HUB 캐시 | 수시 / 월간(익월 20일) | 1개월 → 자동 재호출 | — |
| 토지특성정보(필지 DB) | 반기 | 8개월 | 12개월 |
| 토지이용계획 속성 / 공간 | 월간 / 분기 | 3 / 5개월 AND 새 판 | 5 / 8개월 |
| 연속지적도 / 토지이동이력 | 월간 | 3개월 AND 새 판 | 5 / 8개월 |
| 서울 UPIS | 수시(월간, 열린데이터광장 등록일) | 3개월 AND 새 판 | 6개월 |
| 수치지형도 1:5,000(도로·수계 레이어 포함) | 1년 주기 + 수시 | 18개월(제작연도 기준) | 36개월 |
| 수치지형도 1:1,000 | 수시(평균 5~7년) | 84개월 | — |
| 역사마스터·정류소 / 생활인구 / 상가 / 침수흔적도 | 수시 / 매일 / 분기 / 연 | 6 / 3 / 4 / 14개월 | — |

사용자 갱신 체크리스트(소요는 추정): **월 1회 ≈ 40~50분** — GIS건물 서울 전체본(129 MB, 수동) · UPIS 20종(자동) · 토지이용계획 속성 CSV 서울(96~150 MB zip, 비압축 ≈ 2 GB·1,040만 행, 수동; 적재 전 전 판과 행 수 비교) · 건축HUB 폐쇄말소·철거멸실 벌크(수동) · (선택) 토지이동이력 서울(33 MB). **반기 1회 ≈ 1~2시간** — 토지특성 서울 25개 구 SHP(5·11월 갱신 후) → `dev_database_builder.py` 재빌드 → `buildings.pnu` 재조인. **연 1회 ≈ 반나절** — 수치지형도 139도엽 중 플랫폼 제작(수정)년도가 `sheets.csv`보다 새 도엽만 재수령, P1 자동 수집 재실행. **대상지 생성 시 자동** — `LT_C_BLDGINFO` 재호출(1개월 만료) → 건축HUB 철거멸실(최근 24개월)·폐쇄말소 호출 → `status` → 경고 계산 → 시트·3dm·`context.json` 표기.

---

## 3. 라이선스·출처표기 규칙 (08전국 §5·§7.2 반영 개정)

**바뀐 점**: 종전 "제한 없음·1유형·CC BY만 번들" 원칙은 유지하되 ① 토지특성·토지이용계획을 '공공누리 1유형'으로 적던 것을 포털 표기 **'이용허락범위 제한 없음'**으로 정정(브이월드는 '미지정' — 공공데이터법 제3조④상 금지 표시가 아니라 메타데이터 누락) ② 연속지적도형정보는 VWorld CC BY vs 포털 **제4유형** 충돌 → 보수적으로 번들·납품 금지 ③ VWorld 2D API 응답은 **약관 제19조** 때문에 어떤 층에도 저장하지 않음 ④ 3D 컨텍스트 웹 업로드 기능 자체를 만들지 않음(별표 1 '3차원 좌표 포함 90 m보다 정밀').

1. **분류 4단**: 번들(배포본 DB) / 로컬(사용자가 받아 적재) / 납품(3dm·AI 포함) / 온라인(웹 공유·클라우드 표시). 모든 원천을 08전국 §5.6 표의 4열로 `data_sources.license`에 등록한다.
2. **번들 조건**: 제공기관이 공공데이터포털 또는 VWorld 상세 페이지에 '이용허락범위 제한 없음'·공공누리 1유형·CC BY로 표기한 벌크 파일만 — 토지특성 CSV·토지이용계획(제한 없음), GIS건물통합정보(CC BY/1유형 일치), 수치지형도 1:5,000(1유형), 서울 UPIS(1유형), SGIS·소진공·건축HUB(제한 없음). 두 창구 표기가 다르면 (a) 포털 표기를 1차로 (b) 포털이 2·4유형이면 번들·납품 금지 (c) 포털 '제한 없음'·VWorld '미지정'은 번들 허용하되 두 표기와 근거를 함께 기록 (d) 포털 표기가 속성 CSV에만 걸려 있고 도형이 다른 원천의 파생물인 경우(**토지특성공간정보 dsId=4 SHP** — "연속지적도 융복합")는 국가공간정보센터 질의 결과 전까지 '번들(추정)'. VWorld 데이터마켓 벌크 전반의 번들은 약관 제19조 범위 질의 결과 전까지 '가능(질의 중)'.
3. **VWorld 2D API·WMS/WMTS 응답은 배포본 DB와 사용자 영구 캐시에 넣지 않는다**(이용약관 제19조 "사전 승낙 없이 데이터를 무단으로 저장하지 못합니다"). 런타임 세션 캐시만, 사용자 본인 인증키 필수, 응답에서 만든 객체에는 "출처 ⓒ 국토교통부·브이월드" UserString. `INVALID_KEY`·만료 응답은 '키 재발급/재입력' 안내로 매핑. 서면 동의 전까지 API 유래 객체의 납품물 포함은 사용자 옵션(기본 off).
4. **등고선·표고값(1:5,000 이상)은 온라인 기능에서 제외**(deliverables §B.4). 1:1,000 등고선·표고점은 공개제한이라 어떤 층에도 넣지 않는다. **3D 컨텍스트(건물+지형)를 웹에 올리는 기능은 만들지 않는다.**
5. **로컬 전용·비영리 검토용**(CC BY-NC-ND·4유형): UPIS 전국 벌크 dsId=30074·30065~30117, 건물통합정보_마스터 dsId=30524, 도로명주소 전자지도 VWorld 재배포본 dsId=30055/30056, 연속지적도형정보 dsId=23(포털 15125044 4유형)·전국 dsId=30563, 센서스 행정동경계 dsId=30017, 가로수 OA-22904. 도로명주소 전자지도는 원천(juso.go.kr, 포털 15050413 '제1유형' 표기이나 PPTX 안내문만) 이용조건 확인 후 재분류. 납품물 레이어 이름에 접미사 **`_NC`**를 붙여 내보내기 단계에서 자동 제외. OSM·Overture(ODbL)는 공공데이터와 같은 테이블에 섞지 않고 검증 리포트에만.
6. **출처표기 문자열**: 공공누리 양식("본 저작물은 국토교통부에서 2026년 작성하여 공공누리 제1유형으로 개방한 'GIS건물통합정보'를 이용하였으며 …") + CC BY 원천은 "CC BY 2.0 KR, https://www.vworld.kr/dtmk/…dsId=18" 병기 + 변경 사실("재투영·병합·단순화") 표기 + "본 데이터는 정보제공 목적이며 법적 효력이 없음(국토교통부 국가중점데이터 안내)". 모든 시트·베이스맵 여백·3dm `CTX::Ref`에 `data_sources` 기반으로 자동 삽입(형식은 deliverables §C 공통 ①②). 공공누리 1유형과 CC BY 4.0은 실질 동일(출처표시만, 상업·변경 허용) — 차이는 표기 양식뿐.
7. **배경지도 타일 이미지**는 납품물 기본 제외. 포함 옵션은 VWorld 서면 답변(영리 이용·인쇄물) 확보 후. NGII 정사영상(공개·1유형)은 출처표시 조건으로 인쇄 베이스맵·공모 도판 삽입 가능, 단 온라인에는 좌표(격자·지번) 없이; 25 cm보다 정밀한 항공사진 원본은 승인·기록 대상이라 제외.
8. 시도 패키지는 '로컬' 분류로 통일하고 번들은 서울 패키지만. 패키지 빌더는 원본 zip의 파일명·기준일·라이선스 표기를 `data_sources`·`source_files`에 자동 기록.

---

## 4. 미해결 (확인 필요)

**08로 해소된 것**: ~~1. GIS건물통합정보 컬럼 정의서~~ → A16 높이 있음, `usability` 33 대분류·`strct_cd` 참조코드 확정 [08높이 §3]. ~~10. `platGbCd` ↔ PNU 11번째 자리~~ → `'1'→0 대지`, `'2'→1 산`(필지 DB 반례 0) [08높이 §2.3]. 9(부분) → VWorld FAQ: 데이터 API는 "별도 제한 없음, 무리한 호출 시 일시 차단", 개발키는 외부 SW·개인용으로 배포 사용자 각자 발급이 FAQ 문구에 맞음(유효기간 수치는 여전히 없음) [08전국 §5.1]. 8(부분) → S-Map 3D는 공개제한 신청형으로 확인, 플러그인 원천 부적합 [08높이 §6.1]. 5 → 서면 질의 3건으로 확장(§0).

1. 토지소유정보(dsId=12) 컬럼 정의서·실제 최신본 날짜 [04b §17-18].
2. 수치지형도 1:1000 서울 다운로드본에 등고선·표고점이 포함되는지, 도엽코드 9자리 체계 [05 §8-6].
3. 국토정보플랫폼 '공개DEM'(포털 15059920) 현행 격자 해상도(포털 미표기; 04a는 2015 보도자료 근거 90 m)와 시도별 용량, 5 m DEM 제공 조건 [04a §5-2, 05 §8-14, 08전국 §8-19].
4. 서면 질의 3건(§0): NGII 별표 1 데스크톱 납품 해석 / VWorld 약관 제13·19조의 벌크·유료 플러그인 적용 범위(오픈API 이용약관 페이지는 '시스템 에러') / 국가공간정보센터 연속지적 CC BY vs 4유형·토지특성공간정보 도형 이용허락 [08전국 §8-6·7].
5. 생활인구 250 m 격자ID → 지오메트리 변환 규칙 [04b §17-1].
6. 국가유산 공간정보 다운로드 메뉴·형식(브라우저) [04a §5-17].
7. S-Map 오픈랩 로그인 후 FAQ 모음집 PDF 본문(3D 데이터 종류·확장자), LiDAR 구축 방식 1차 출처 [08높이 §7-1].
8. VWorld 개발키 발급일·유효기간·만료 시 오류코드(`INVALID_KEY` 여부) — 마이페이지 확인 [08전국 §8-20].
9. `File3dm.Strings` 쓰기 가능 여부 — 00(불가)·07(가능) 실측 상충 → 재실측 1회(불가면 기준일 메타는 `CTX::Ref` 더미 포인트 UserString).
10. 지하철 출입구 포인트 공식 소스, 도보 네트워크 노드 유형 코드에 출입구가 있는지 [04b §17-16].
11. 도로명주소 전자지도(business.juso.go.kr) 건물 도형의 층수·용도 속성, 실폭도로·도로구간 제공 조건 — SPA 개편('퍼블.250722')으로 종전 `.do` 경로 404, 로그인 후 '주소정보 다운로드' 확인 [04a §5-1, 08높이 §4.6, 08정합 §5-10].
12. **건축HUB `heit` 보정 효과** — VW `height=0` 건물 100 PNU 샘플로 `heit>0` 비율 측정 후 A.4 규칙 2 유지·삭제 결정(`.env`에 data.go.kr 키 필요) [08높이 §7-11].
13. 건축HUB 표제부 벌크 XLSX 실물(hub.go.kr 로그인·시도 분할·서울 행 수·`높이` 채움률), 대용량 폐쇄말소·철거멸실 벌크의 용량·컬럼·PK 매칭(건축물대장 PK ↔ GIS건물 A19) [08높이 §7-17, 08기준일 §7-13].
14. 건축HUB `startDate/endDate`가 거르는 날짜 필드(`crtnDay` 추정) — 활용가이드 확인 [08기준일 §7-3].
15. GIS건물 변동분 `입력구분` 코드값(I/U/D?)과 삭제 레코드 도형 유무; 월간 전체본 간 `A1 식별번호` 안정성(두 판 diff) — 미채택이지만 diff 로그 신뢰도에 영향 [08기준일 §7-1·2].
16. **수치지형도 4도엽(37705072·73·82·83) 제작·수시수정 연도** — 국토정보플랫폼 로그인 목록(제작년도 열)에서 읽어 `sheets.csv`에 기록; zip 원본에 메타데이터 파일이 있는지. 이 값이 있어야 정합 오차의 시간차 몫을 분리 [08기준일 §7-4, 08정합 §5-9].
17. 연속수치지형도 등고선 19 zip 중 서울·경기·인천 포함 파일·용량(`시도별_등고선_파일_목록.xlsx`, 로그인) — macOS 단독 1단계 가능 여부 결정 [08전국 §8-3].
18. 국토정보플랫폼 '연속수치지형도' 영역 선택 신청 흐름·한도(현재 근거는 주석 처리된 템플릿 문구뿐), 공개 수치지형도 도엽 일괄 신청 절차 [08전국 §8-4·5].
19. 토지이동이력 CSV `토지이동사유` 문자열에 종전·상대 지번이 실제로 채워지는지(서울 월간본 1개 수령 후) [08기준일 §7-10].
20. 토지이용계획 CSV 08-26판(zip 96 MB, 10,403,113행)의 결손 여부 — 09-09판(150 MB) 수령 후 행 수·코드별 비교; 파일명 코드 D155 vs 정의서 D154 [08기준일 §7-8·11].
21. 서울시 지적공부 세계측지계 변환 완료 공고 시점(자치구별), 서울 지적재조사 진행률 [08정합 §5-2·3].
22. A.4 상수·정합 기본값의 지역 편향 — 강남(대단지 아파트)·구도심(단독 밀집)에서 VW 타일 추가 수집 후 `probe_building_height.py`·`probe_alignment.py` 재실행(규칙 3 임계 +3층, `archarea×0.5` 오탐률 포함) [08높이 §7-3].
23. 서울 GIS건물 전체본 동 수·적재 소요, `A2` PNU 19자리 초과 건수; 전국 건수 포털 6,656,497 vs VWorld 14,422,486 2배 차이 이유 [08기준일 §7-12, 08높이 §7-16].
24. 용도지역지구정보 dsId=24의 포털 대응 ID·라이선스(서울 UPIS 대체 가능성, 변동 SHP에 고시일자 필드 있음) [08기준일 §7-7, 08전국 §8-8].
25. 국가공간정보포털(nsdi.go.kr) DNS NXDOMAIN(2026-10-07) — 서비스 이전·통합 여부 [08전국 §8-17].

---

## 5. 일본 (Global 모드 안, 2026-10-21)

근거 `docs/research/japan.md`, 계획·결정 `docs/japan_plan.md`. 일본 대상지는 Global 모드 그대로이고 건물·지형만 일본 공공데이터로 바꾼다. 도로·수계·녹지·철도는 OSM.

| 요소 | 원천 | 받는 방식 | 형식·기준 |
|---|---|---|---|
| 건물 | 국토교통성 3D 도시모델 PLATEAU `bldg` — LOD0 외곽(RoofEdge 우선), `measuredHeight`, 층수, 용도 코드. 306개 시구정촌 최신 연도판(2020~2025년도), 엑스포 회장 제외 | `dev_plateau.py build` → HF `jp/jp<시구정촌코드>_context.db.xz`(합계 압축 2.69 GB, 최대 요코하마 80.5 MB) → 생성 직전 범위만 받는다 | 경위도 소수 6자리, `buildings` 칸은 런타임이 읽는 한국 이름 그대로(`ngii_kind` = 원천 용도 코드, `usability`는 런타임 `constants.PLATEAU_USE`). 층수 9999·높이 -9999 = 모름 |
| 도로면 | PLATEAU `tran` — `tran:Road` LOD1 외곽 폴리곤(도로마다 하나, 신주쿠 31,433면·306팩 1,073만 면, tran이 없는 7팩은 0), `function`(1 고속·2 국도·3 도도부현도·4 시정촌도·5 그 밖·9020 등) | `dev_plateau.py roads` → 같은 팩의 `features`(theme road·kind surface, 한국 컨텍스트 팩과 같은 칸) | 2026-10-22. 팩에 도로면이 없거나(옛 판) 공도가 아닌 길(사유지 통로·공원 길)은 OSM 중심선 버퍼로 메운다(`osm_context.get_surfaces_apart`) |
| 지형 | 국토지리원 표고 타일 DEM5A → 5B → 5C(z15, 약 8 m 간격), 없으면 같은 타일의 AWS terrarium | 실행 중(세션 캐시만, 저장·재배포 안 함) | 표고 기준 T.P. — PLATEAU와 같다 |

- 라이선스: PLATEAU = 公共データ利用規約 第1.0版(CC BY 4.0 호환), 저작권은 각 지방공공단체, 가공 사실을 따로 적는다(산출물 메타 줄·데이터셋 카드). 지리원 타일 = 실시간 읽기는 출처 표기만. 국외 반출 제한이 없어 국내 서버가 필요 없다.
- 도시 경계 3차 메시는 이웃 도시 팩에도 들어 있다(도쿄도 팩끼리 같은 gml:id — 국립·국분지 13,245동). 런타임이 `src_key`(gml:id)로, 다른 도시 팩의 같은 자리 건물은 새 연도 팩 것을 남겨 걸러 낸다.
- 2020년도판 일부(豊中市 등)는 용도 코드가 없다. 건축 연도는 비어 있어 노후도 도면을 만들 수 없다.
- 갱신: PLATEAU 새 연도판이 나오면 `dev_plateau.py catalog` → `build`(바뀐 도시만) → `roads`(그 도시) → `upload`. `build`는 건물만 다시 만들므로 `roads`를 꼭 이어서 돌린다.

### 네덜란드 — Kadaster 3D Basisvoorziening 건물 팩 (`nl/`, 경위도, 2026-10-22)

| 항목 | 원천 | 팩 | 비고 |
|---|---|---|---|
| 건물 | Kadaster PDOK **3D Basisvoorziening** `hoogtestatistieken_gebouwen`(2D 건물 + 높이 통계, 항공 lidar AHN 기반). 도엽(bladnr 1:10k) zip 안 GeoPackage, EPSG:28992. 2025년판 1,327도엽 2.23 GB | `dev_nl.py catalog → build → upload` → HF `nl/nl<도엽>_context.db.xz` + `nl/manifest.json`. 칸은 일본 팩과 같다(`dev_plateau.SCHEMA_SQL`). 높이 = `rf_h_roof_50p − rf_h_ground`(B, 없으면 70p·max, 범위 밖은 기본값 D), 건축연도 `oorspronkelijkbouwjaar` → `use_apr_day`(1500년 미만 자리표시는 모름), 지붕형 `rf_roof_type` → `ngii_kind` | 한 pand가 지붕 조각마다 행으로 나뉜다(암스테르담 25GN1 72,942행 중 13,809 pand가 여러 행) — `src_key`에 `#n`을 붙여 전부 남긴다. 철거·허가 단계(`PDOK_SKIP_STATUS`)는 뺀다 |

- 라이선스: **CC BY 4.0**(OGC API collections의 license 링크 `https://creativecommons.org/licenses/by/4.0/deed.nl`). 출처 고지는 팩 `data_sources.note` 그대로 도면 출처 줄에 적는다: "Bron: Kadaster, 3D Basisvoorziening (CC BY 4.0), bewerkt door Gorani". 국외 반출 제한 없음.
- 런타임: 나라 목록 `docs/countries.json`의 `nl`(한국 매니페스트 `countries[]` → `data_pack.get_country_packs`, 내장 기본값 `constants.COUNTRY_PACKS`) — 대상지 중심이 그 상자 안이면 생성 직전에 범위에 걸치는 도엽 팩을 받고(`cmd_site._download_for_generate`), `osm_context.load_plateau_buildings`가 팩 건물을 먼저, OSM 건물은 겹치지 않는 것만. 도로면은 OSM 버퍼(팩에 features 표 없음), 지형은 Terrain Tiles.
- 조사 근거·다른 나라 후보(프랑스 BD TOPO·스위스 swissBUILDINGS3D·독일): `docs/research/country_buildings.md`.
- **새 나라 추가 절차(2026-10-23)**: ① `dev_<나라>.py catalog → build → upload`(팩 + `<나라>/manifest.json`, HF 올리기는 사용자 확인 뒤) ② `docs/countries.json`에 한 줄(코드·상자·라벨·source_id·고지) ③ `python3 scripts/dev_deploy.py notices`. 플러그인 판은 올리지 않는다 — 깔린 플러그인이 켤 때 목록을 받는다. 내리기는 `disabled: true`.

### 프랑스 — IGN BD TOPO® 건물 팩 (`fr/`, 경위도, 2026-10-22)

| 항목 | 원천 | 팩 | 비고 |
|---|---|---|---|
| 건물 | IGN **BD TOPO® v3.5** `batiment` — 데파르트망별 7z(모든 테마 GeoPackage, EPSG:2154, 파리 210 MB → 1.3 GB). Géoplateforme Atom 피드(`data.geopf.fr/telechargement/resource/BDTOPO?page=N`) 96 데파르트망(본토·코르시카), 2026-09-15판 | `dev_fr.py catalog → build → upload` → HF `fr/fr<데파르트망>_context.db.xz` + `fr/manifest.json`. 높이 `hauteur`(B — 지붕 처마선까지의 높이라 PLATEAU·PDOK의 지붕 50 %보다 낮다), 없으면 `nombre_d_etages` × 층고(C), 기본값(D). `usage_1` → 대분류(`BDTOPO_USE`: 주거는 호수 1이면 단독), `date_d_apparition` → `use_apr_day`, 층수 → `grnd_flr` | 벨포르(D090) 161,412동·B 96.8 %·xz 12.1 MB. `etat_de_l_objet` 계획·철거(`BDTOPO_SKIP_STATES`)는 뺀다. 해외 데파르트망(LAMB93 아님)은 없다 |

- 라이선스: **Licence Ouverte / Open Licence 2.0**(Etalab; data.gouv.fr 데이터셋 `bd-topo` license `lov2`). 출처 고지: "Source : IGN, BD TOPO® <판> (Licence Ouverte 2.0), traité par Gorani"(팩 `data_sources.note`, 도면 출처 줄).
- 런타임: `countries.json`의 `fr`(상자 본토·코르시카). 도로면은 OSM 버퍼, 지형은 Terrain Tiles.

### 스위스 — swisstopo swissBUILDINGS3D 3.0 Beta 건물 팩 (`ch/`, 경위도, 2026-10-23)

| 항목 | 원천 | 팩 | 비고 |
|---|---|---|---|
| 건물 | swisstopo **swissBUILDINGS3D 3.0 Beta** — STAC `ch.swisstopo.swissbuildings3d_3_0` 타일(1:25k 도엽 하위, 연도별 6,724타일 → 하위 타일마다 최신 연도 3,230개) FileGDB(LoD2, MultiPatch) | `dev_ch.py catalog → build → upload` → HF `ch/ch<도엽>_context.db.xz`(252도엽) + `ch/manifest.json`. GDAL(brew) `ogr2ogr`로 `Floor` 층(3D TIN → MULTIPOLYGON25D), `ogrinfo`로 `Building_solid` 속성. 바닥 = Floor 삼각형을 LV95 m에서 합친 외곽, 지반 = Floor 최저 z, 높이 = `GESAMTHOEHE`(B) → `DACH_MAX` − 지반(B) → 기본값(D). 종류 `OBJEKTART` → `ngii_kind`, 용도 `GEBAEUDE_NUTZUNG` → `ngii_use` | 도엽 1192(알트도르프) 10,563동·B 100 %·xz 1.1 MB. 지하·가려진 건물·담장(`Unterirdisches Gebaeude`·`Gebaeude unsichtbar`·`Mauer*`)은 뺀다. pyogrio는 MultiPatch(지오메트리 1016)를 못 읽어 GDAL이 필요하다 |

- 이용약관: swisstopo "Terms of use for free geodata and geoservices"(2022-08-26, Version 1.3.2021) — 자유 이용·가공·상업 이용·재배포, 출처 표기 의무. 고지: "Source: ©swisstopo, swissBUILDINGS3D 3.0 Beta (<연도>), processed by Gorani"(팩 `data_sources.note`). STAC 메타의 license 값 "proprietary"는 약관과 다르다(확인 필요 — 약관 원문을 따른다).
- 런타임: `countries.json`의 `ch`(상자 스위스·리히텐슈타인). 프랑스 상자와 겹치므로 `osm_context.get_country`는 작은 상자를 우선한다. CityGML 배포는 EGID가 있는 주만이라 쓰지 않는다.

### 미국 — Overture Maps buildings 건물 팩 (`us/`, 경위도, 2026-10-23 빌더·시험, 전체 빌드·HF 올리기는 사용자 확인 뒤)

| 항목 | 원천 | 팩 | 비고 |
|---|---|---|---|
| 건물 | **Overture Maps Foundation buildings** 테마(판 `constants.OVERTURE_RELEASE`, 달마다) — Microsoft ML Buildings(GERS로 합본)·OpenStreetMap·Esri Community Maps. S3 GeoParquet(`overturemaps-us-west-2`, 익명) | `dev_us.py catalog → fetch <주> → build [FIPS] → upload` → HF `us/us<카운티 FIPS 5자리>_context.db.xz` + `us/manifest.json`. 카운티 경계는 Census `cb_2024_us_county_500k`(GEOID, 3,235개 — 준주 포함), 건물 중심점이 든 카운티에(경계 300 m 넓힘, 겹침은 런타임 `src_key` 중복 제거). 높이 `height`(B — **Microsoft ML 추정이라 실측 아님**) → `num_floors` × 층고(C) → 기본값(D). `subtype`·`class` → `ngii_kind`·`ngii_use`와 대분류(`OVERTURE_USE_*`), `names.primary` → `bld_nm`, 출처 데이터셋 → `attr_flag`(msft·osm·esri) | 델라웨어 시험(2026-10-23): 3카운티 435,190동, 뉴캐슬 175,200동·B 80.5 %·xz 16.4 MB·22 s(주 parquet 받기 6분). 콜로라도 주 전체 B 68.9 %(시골 포함), LA 도심 98.8 %. 지하(`is_underground`)는 뺀다. 용도는 약 9 %만 있다(델라웨어) |

- 라이선스: **ODbL 1.0**(Overture buildings 테마 전체 — docs.overturemaps.org/attribution. Microsoft ML Buildings도 ODbL로 제공). 우리 OSM 사용과 같은 라이선스이고 share-alike라 팩도 ODbL이다(데이터셋 카드에 적는다). 고지(팩 `data_sources.note`, 도면 출처 줄): "Source: Overture Maps Foundation (buildings, release <판>, ODbL 1.0) — © OpenStreetMap contributors, Microsoft; processed by Gorani. Heights mostly ML estimates".
- 공식 출처를 안 쓴 이유: FEMA·ORNL USA Structures는 HEIGHT가 약 32M/125M동뿐이고 약관이 CC BY 4.0(ArcGIS Hub)과 미국 정부 저작물(data.gov)로 갈린다. 용도(OCC_CLS)는 더 좋아 나중에 보강 후보. 근거 `docs/research/country_buildings.md`.
- 런타임: `countries.json`의 `us` — 상자 넷(`constants.US_BOUNDS` 본토·알래스카·하와이·푸에르토리코). 도로면은 OSM 버퍼, 지형은 Terrain Tiles.
- 갱신: Overture 새 판 → `constants.OVERTURE_RELEASE` 바꾸고 `fetch`(주 parquet 다시) → `build`(판이 다르면 다시 만든다) → `upload`.
