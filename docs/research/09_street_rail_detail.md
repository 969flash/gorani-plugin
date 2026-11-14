# 09 가로·철도 디테일 — 인도·연석·노면표시·철도 (2026-11-08)

도로가 지형 위의 색 다른 평면뿐이라는 지적에 따라, 인도·연석 단차·노면표시·지상 철도를 3D로 만들 데이터와 비교 도구를 조사했다. 로컬 실측은 `data/seoul_context.db`(수치지형도 1:5000 Ver2.0)이고, 웹 조사는 같은 날 기준이다.

## 1. 이미 가진 것 — 수치지형도 1:5000 (로컬 실측)

- **인도 `A0033320`(면)**: 서울 41,639개, 칸은 `폭`·`재질`. 강릉(215도엽 4,373개)·해운대(3,383개)에도 있다.
  - 인도 면은 도로경계 `A0010000` 안에 들어 있다(성수 100 %, 서울역 97.7 %).
  - 중심선 `도로폭`은 인도를 포함한 전체 폭이다(실측 폭과 일치: 6차로 32.0 m vs 32.5 m, 이 가운데 인도 10.7 m).
  - 인도 면은 6차로 이상 간선에만 있다. 성수 1 km²에서 2차로(10~15 m) 도로 13곳의 인도 폭은 평균 0.2 m였다.
- **안전지대 `A0053326`**: `구조`에 교통섬과 어린이보호구역이 섞여 있다. 어린이보호구역은 도로 전체를 덮으므로 교통섬만 올린다.
- **철도 `A0150000`(선)**: 선로마다 한 줄이고 분기기 모양까지 그려져 있다(서울역 구내 30줄, 간격 약 5 m). `구분` = 고속철도·보통철도·지하철(지상), 지하 구간은 적재하지 않았다.
  - 철도중심선 `A0171119`는 노선 축 한 줄이다(`구조` 단선·복선).
  - 승강장 `A0191221`·승강장 지붕 `A0201222`는 면이다.
- **없는 것**: 횡단보도 `A0043325`는 코드표에만 있고 도엽에는 없다. 차선·정지선 코드도 없다. 연석 높이 속성도 없다.
- **1:1000 수치지형도**(서울 2021~25 갱신)는 공공누리 4유형이라 파생물 재배포에 맞지 않는다.

## 2. 국내 상세 데이터

| 자료 | 내용 | 커버리지·기준일 | 라이선스·받는 길 |
|---|---|---|---|
| 정밀도로지도(NGII) | A4 부속구간 `보도`(면, Z), B2 노면선표시(501 중앙선·503 차선·505 길가장자리·530 정지선), B3 노면표시(5321 횡단보도), 모두 3D | 고속국도·일반국도 완료, 수도권 특별·광역시도는 2027년까지. 성수 실측: 25 m 이상 도로 100 %, 15~25 m 66 %, 10~15 m 15 %, 10 m 미만 3~5 %. 갱신 2018~2025 | 공공누리 1유형. 벌크는 국토정보플랫폼(로그인, 전송 프로그램). VWorld WFS(`lt_l_b2surfacelinemark` 등)는 키 필요·1000건 단위·저장 약관 확인 필요 |
| 서울 교통안전시설물(교통운영과) | 횡단보도 OA-15554(면 37,324), 차선 OA-15537(선 341,957 — 중앙선·차선·정지선·가장자리구역선 등, 색·실선/점선), 안전지대 OA-15533, 방향표시 OA-15536 | 서울 전역, 이면도로 포함. **SHP는 2021-08-09판** | 공공누리 1유형, EPSG:5186, 로그인 없이 받음 |
| 전국횡단보도표준데이터(data.go.kr 15028201) | 점 + 폭·연장·차로수·고원식 | 지자체 제공, 서울은 사실상 없음. 2025-07 | 방향이 없어 3D로는 약함 |
| 국가철도공단 | 역 좌표·노선표뿐 | — | 궤도 선형 공개 자료 없음 |

- **연석 높이**: 정밀도로지도 보도 Z − 차도 가장자리선 Z = 중앙값 0.175 m(사분위 0.12~0.20, 성수 1,977점). 법정 상한은 「도로의 구조·시설 기준에 관한 규칙」 제16조 25 cm.
- **국외 반출**: 정밀도로지도는 기본측량성과(측량법 제12조 근거로 보임)라 파생 팩은 수치지형도처럼 국내 서버에만 둔다(확인 필요). 서울 교통안전시설물의 측량성과 해당 여부도 확인 필요 — 같은 컨텍스트 팩에 넣으면 자연히 국내 서버에만 놓인다.

## 3. 해외 데이터

- **OSM** (taginfo 2026-11-08): 주요 도로 중 `sidewalk*` 태그 비율 독일 41 %·네덜란드 27 %·프랑스 12 %·미국 9 %·일본 1.3 %·한국 1.8 %. 태그가 없으면 도로 등급별 기본값이 사실상 전부다. `highway=crossing` 노드 13.7 M(`crossing:markings=zebra` 3.3 M), `lanes` 20.2 M way. `barrier=kerb`는 대부분 낮춘 연석 점이라 연석 선으로는 못 쓴다.
- **PLATEAU tran LOD2**: 車道部·歩道部·島(TrafficArea·AuxiliaryTrafficArea) 면, 높이 0. 도로 있는 300 시정촌 중 59곳(도쿄 23구 대부분·오사카시·히로시마 등). `dev_plateau.iter_roads`는 지금 LOD1만 읽는다. LOD3.2는 15 cm 이상 단차를 잡는다.
- **PLATEAU rwy**: 공개 5곳뿐 — 쓰지 않는다.
- **네덜란드 BGT** `wegdeel.functie`(rijbaan·voetpad·fietspad)로 차도·인도를 나눌 수 있으나 연석 높이는 없다. NYC Planimetric은 Curb·Sidewalk·Roadbed를 공개한다.

## 4. 비교 도구

- 납작한 면·선까지: Cadmapper(등급별 폭 폴리라인), PlaceMaker(지형에 덮은 도로·보행로 면), Elk·Heron(중심선), BlenderGIS(엣지·메시).
- 단면까지: Blosm(도로 프로파일, 교차로·횡단보도 모듈은 미출시 개발 브랜치).
- 가로 전체: CityEngine(유료 — 차로 목록으로 차도·인도·연석·노면표시·지브라 횡단보도·연석 반경), OSM2World(LGPL, 차로·노면표시·`sidewalk`), osm2streets(Rust, Apache-2.0 — 차로 목록 → 차로 폴리곤·차선·정지선·지브라).
- 가져올 것: 도로 단면 = 차로 목록 규칙(osm2streets 방식을 파이썬으로 따라 만든다 — Rust 빌드는 번들에 넣지 않는다), 연석 15 cm, 노면표시는 텍스처가 아니라 노면 위 얇은 면(세 호스트에서 같게 보인다).
- 가져오지 않을 것: 교차로 정밀 형상, 회전 화살표, 가로시설물 자동 배치.

## 5. 교량·고가 (2026-11-13)

- 수치지형도 교량 면(서울 도로교 1,266·고가차도 278·철교 111·육교 376)은 상판 높이 속성이 없다. 고가차도·육교 `높이`는 밑을 지나는 통과높이(중앙값 4.0~4.5 m, 부산은 0)다.
- 상판 높이는 교량 면 안 표고점(`spot_struct`, 빌드 때 TIN에서 뺀 것)이 실측값이다. 성동구 교량·고가 43곳 중 33곳에 있다(성수대교 31 m — 둔치 지반 11~15 m). 이것을 쓰고, 없을 때만 끝점 경사 + 통과높이로 추정한다.
- 다른 도구: InfraWorks는 OSM에서 도로를 가져온 뒤 교량은 사용자가 시작·끝 지점과 형식을 골라 놓는다. Streets GL(OSM 3D)은 `layer` 쌓기 지원이 덜 됐다는 글이 있다(현재 상태 확인 필요). PLATEAU는 교량 LOD2(주형·바닥판) 실측 모델이 있으나 일부 도시뿐이다. 공개 데이터로 상판 높이를 자동 실측하는 곳은 찾지 못했다.
- 한계: 수치지형도에는 층 정보가 없어 교차하는 고가는 각자의 표고점으로만 높이가 갈린다. OSM은 `layer`만 있어 높이는 추정이다. 교각 위치는 데이터가 없어 30 m 간격으로 둔다.

## 출처

- 정밀도로지도 https://www.data.go.kr/data/15059912/fileData.do · 일반국도 완료 https://m.korea.kr/news/policyNewsView.do?newsId=148914276 · 레이어 표 https://koreascience.kr/article/JAKO202122260838090.pdf
- 서울 횡단보도 https://data.seoul.go.kr/dataList/OA-15554/S/1/datasetView.do · 차선 OA-15537 · 안전지대 OA-15533 · 방향표시 OA-15536
- 전국횡단보도표준데이터 https://www.data.go.kr/data/15028201/standard.do
- PLATEAU 도로 LOD2 https://www.mlit.go.jp/plateaudocument/toc4/toc4_03/toc4_03_01/toc4_03_01_03/_ee94cd7b-404c-9580-648f-9a22660032fe · LOD3.2 https://www.mlit.go.jp/plateaudocument/toc4/toc4_03/toc4_03_01/toc4_03_01_04/_6732ab4b-72b3-75ff-3210-40c9fc9d8278
- BGT wegdeel https://api.pdok.nl/lv/bgt/ogc/v1/collections/wegdeel/items?f=html
- osm2streets https://github.com/a-b-street/osm2streets · OSM2World https://wiki.openstreetmap.org/wiki/OSM2World · CityEngine https://doc.arcgis.com/en/cityengine/latest/help/help-street-and-crossing-shapes.htm · Blosm https://github.com/vvoovv/blosm/wiki/Documentation · Cadmapper https://cadmapper.com/
- OSM 인도 완성도 https://www.arxiv.org/pdf/2210.02350
- InfraWorks 교량 https://help.autodesk.com/cloudhelp/ENU/InfraWorks-BridgeDesign/files/GUID-958B3BD8-2C26-4DA7-B578-9CE63FBEAC62.htm · Streets GL https://community.openstreetmap.org/t/streets-gl-a-new-3d-renderer-for-osm/98594 · PLATEAU 橋梁モデル https://www.mlit.go.jp/plateaudocument02/tocL/tocL_02/tocL_02_01
