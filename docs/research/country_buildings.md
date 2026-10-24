# 나라별 공식 3D 건물 데이터 조사 (2026-10-22)

Global 모드는 OSM 건물에 높이 태그가 드물어 기본값(3.8 m·층수 추정)을 쓴다. 공식 공개 3D 건물 데이터가 있는 나라는 일본 PLATEAU처럼
바닥 윤곽 + 높이만 뽑아 팩(`<나라><코드>_context.db.xz`)으로 HF 데이터셋에 둔다. 조건: 재배포 허용 라이선스, 전국 단일 출처, 높이 포함.
**HF 업로드는 사용자 확인 뒤에 한다.**

| 순위 | 나라 | 출처 | 라이선스(원문 확인) | 받기 | 높이 칸 | 비고 |
|---|---|---|---|---|---|---|
| 1 | 네덜란드 | Kadaster **3D Basisvoorziening** — `hoogtestatistieken_gebouwen`(2D 건물 + 높이 통계) | CC BY 4.0 (`https://creativecommons.org/licenses/by/4.0/deed.nl`, OGC API collections의 license 링크) | 타일(bladnr 1:10k 도엽) zip → GeoPackage 한 파일, 2025년판 1,327타일 2.23 GB(타일 중앙값 0.8 MB). 목록 `api.pdok.nl/kadaster/3d-basisvoorziening/ogc/v1/collections/hoogtestatistieken_gebouwen/items`(download_link·download_size_bytes), 받기 `download.pdok.nl/kadaster/basisvoorziening-3d/v1_0/<연도>/hoogtestatistieken/<bladnr>_<연도>_hoogtestatistieken_gebouwen.zip` | `dd_h_dak_50p`·`70p`·`max`(지붕 NAP 표고) − `h_maaiveld`(지반 NAP) = 높이. `bouwjaar`, `pandstatus`, `bagpandid`, `lod` | EPSG:7415(RD New + NAP). 공식(카다스터) 출처 |
| 1′ | 네덜란드 | **3DBAG**(TU Delft 3D geoinformation + 3DGI) | CC BY 4.0. 고지 문구 원문: "© 3DBAG by tudelft3d and 3DGI" + 디지털 매체는 copyright 페이지 링크(docs.3dbag.nl/en/copyright/, 2025 아카이브에서 확인) | docs.3dbag.nl·data.3dbag.nl이 2026-10-22 이 네트워크에서 안 열림(ECONNREFUSED). GeoPackage/CityJSON 타일 | `b3_h_50p`·`b3_h_70p`·`b3_h_max`(NAP) − `b3_h_maaiveld` | 같은 원천(BAG + AHN). 받기 경로를 확인 못 해 1순위는 PDOK로 |
| 2 | 프랑스 | IGN **BD TOPO** v3.5 | Licence Ouverte / Open Licence 2.0 (data.gouv.fr 데이터셋 `bd-topo`, license `lov2`) — 출처 표기 "IGN — BD TOPO®" | 데파르트망별 7z(GeoPackage, 모든 테마) — Géoplateforme Atom 피드 `data.geopf.fr/telechargement/resource/BDTOPO?page=N`(10건씩, 2026-10-22 기준 2026-09-15판). 파리 `BDTOPO_3-5_TOUSTHEMES_GPKG_LAMB93_D075_2026-09-15.7z` 210 MB. 약 100 데파르트망 | 층 `batiment`: `hauteur`(m), `nombre_d_etages`, `usage_1`, `date_d_apparition` (확인 필요: 칸 이름은 3.5 문서) | EPSG:2154. 7z 풀기 필요(py7zr 또는 7z) |
| 2 | 스위스 | swisstopo **swissBUILDINGS3D 3.0 Beta** | swisstopo OGD 이용약관(무료, 출처 표기 "© swisstopo") — 원문 `swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices` 확인 필요. STAC 메타의 license 값은 "proprietary"로 적혀 있다(메타 오류로 보임, 확인 필요) | STAC `data.geo.admin.ch/api/stac/v0.9/collections/ch.swisstopo.swissbuildings3d_3_0/items` — 타일(1:25k 도엽 1/4)마다 `.gdb.zip`·`.dwg.zip`, CityGML은 별도 배포(2024-08-14) | 3D 솔리드(LoD2) — 바닥면 최저 z·지붕 최고 z에서 높이를 뽑는다(PLATEAU lod1Solid 방식). FileGDB는 pyogrio로 | EPSG:2056. 리히텐슈타인 포함 |
| 3 | 독일 | 주별 LoD1/LoD2 (대부분 dl-de/by-2-0, 바이에른 CC BY 4.0, 일부 주는 유료·제한) | 주마다 다름 | 주마다 다름(CityGML 타일) | — | 전국 단일 출처가 없어 마지막 |

## 팩 설계(공통)

- 파일: `<나라 2자><지역코드>_context.db.xz` — `buildings` 표는 jp 팩과 같은 칸(`dev_plateau.SCHEMA_SQL`), 좌표는 경위도(EPSG:4326, 소수 6자리), `src_key = "<출처>:<원천 id>"`, `height_src`·`height_grade`는 PLATEAU와 같은 규칙(실측 B).
- 매니페스트: 나라마다 `<나라>/manifest.json`(bounds 경위도). 런타임 `osm_context`는 `is_japan` 대신 나라 매니페스트 목록(`constants.COUNTRY_PACKS`)에서 범위로 고른다.
- 지역 단위: 네덜란드 = PDOK 도엽(bladnr), 프랑스 = 데파르트망, 스위스 = STAC 타일(묶어서 도엽 단위).
- 빌더: `dev_<나라>.py`(python3, 표준 라이브러리 + pyproj·pyogrio 허용). 원천 zip은 받지 않고 흘려 읽거나(PDOK zip 0.8 MB는 통째로), 7z는 풀어서.

## 진행 (2026-10-22 저녁)

- 네덜란드: `dev_nl.py` 완성(카탈로그 1,328도엽, 암스테르담 25GN1 72,942동·실측 98.5 %·xz 5.5 MB). 전체 빌드 진행 중. 런타임은 `constants.COUNTRY_PACKS`로 일반화(일본·네덜란드·프랑스).
- 프랑스: `dev_fr.py` 작성(Atom 피드 카탈로그 → 데파르트망 7z → py7zr로 GPKG 추출 → `batiment`). D090 시험 중. D090 7z 72 MB → GPKG 435 MB(모든 테마), 건물 161,412.
- 스위스: STAC 자산이 DWG·FileGDB뿐이고 FileGDB가 MultiPatch(GDAL 지오메트리 1016)라 pyogrio가 못 읽는다(ogr2ogr·GDAL 바인딩 없음). CityGML 배포(2024-08-14)의 받기 주소를 확인하거나 GDAL을 설치해야 한다 — **보류**.
- 독일: 마지막(주별).

## 스위스 진행 (2026-10-23)

- 이용약관 원문(swisstopo "Terms of use for free geodata and geoservices", 2022-08-26 게시, Version 1.3.2021): 데이터는 "may be used, distributed and made accessible", 가공·상업 이용 허용. 출처 표기 의무 — "©swisstopo" 또는 "Federal Office of Topography swisstopo". 과다 사용 시 접근 제한 가능.
- CityGML 배포는 EGID가 있는 주(AG·AI·AR·BE·BL·BS·GL·JU·TG + 취리히시)만이라 전국이 아니다 → 전국 FileGDB(STAC `ch.swisstopo.swissbuildings3d_3_0`, 6,728타일, 1:25k 도엽 256장)를 쓴다. FileGDB MultiPatch는 pyogrio가 못 읽어 GDAL(brew)의 `ogr2ogr`로 변환한다.


## 미국·중국 조사 (2026-10-23)

사용자 요청: 미국은 데이터가 크니 OSM인지 좋은 공개 데이터가 있는지 보고 대응, 다음은 중국(폐쇄적 — 기대 낮음).

### 미국 — 결론: Overture Maps buildings(ODbL) 하나로 카운티 팩

| 후보 | 라이선스 | 높이 | 받기 | 판단 |
|---|---|---|---|---|
| **Overture Maps buildings**(Microsoft ML Buildings·OSM·Esri Community Maps·Google Open Buildings 합본) | 테마 전체 ODbL(docs.overturemaps.org/attribution — Microsoft ML도 ODbL로 제공). 우리 OSM 사용과 같은 라이선스 | DuckDB로 S3 직접 셈(판 2026-10-21.0): 로스앤젤레스 도심 10 km 상자 105,095동 중 height 98.8 %, 오스틴 89.3 %(출처 Microsoft ML Buildings·OSM). 전 세계는 약 8 %뿐이라 미국이 특별히 좋다 | `s3://overturemaps-us-west-2/release/<판>/theme=buildings/type=building/` GeoParquet, 익명 읽기. bbox 칸으로 행 그룹 건너뛰기 — LA 상자 첫 질의 326 s(메타 읽기), 다음부터 5~8 s | **채택**. 높이는 ML 추정(`height_src overture_height`, B — 실측은 아님을 문서에 적는다). 층수(`num_floors`)·용도(`subtype`·`class`)·이름 있음. 달마다 새 판 |
| FEMA·ORNL **USA Structures** | ArcGIS Hub·DataLumos는 CC BY 4.0, data.gov는 "U.S. Government Works" — 갈린다. Hub API에 licenseInfo 없음(2026-10-23) | HEIGHT 약 32M / 125M동(NGA 출처만) | 주별 FileGDB zip 56개 약 42 GB(disasters.geoplatform.gov → gis-fema.hub.arcgis.com) | 높이가 1/4뿐이고 약관이 갈려 보류. 용도(OCC_CLS·PRIM_OCC)는 Overture보다 낫다 — 나중에 보강 후보 |
| Microsoft GlobalMLBuildingFootprints | CDLA Permissive 2.0 | 2023-06 기준 174M동에 높이, 2026-01~02 미국 Vexcel 2021~2025 높이 추가(1.0~1.2M씩) | 타일 csv.gz(GeoJSON 줄) | Overture가 같은 데이터를 GERS id로 합쳐 두므로 따로 받지 않는다 |
| 3D-GloBFP(Che 2024 ESSD, 2020년 기준 XGBoost 높이) | CC BY 4.0(Zenodo 15487037·Figshare 10파트) | 33 소구역 R² 0.66~0.96, RMSE 1.9~14.6 m | 격자 shapefile zip 10파트 약 200 GB. readme는 중국·미국을 성·주 단위 파일이라 하나 Figshare 목록에서 `_CN`·`_US` 파일을 찾지 못함(2026-10-23) | 미국은 Overture가 낫다. 다른 나라 보강 후보 |
| GlobalBuildingAtlas(TUM 2025, LoD1) | **CC BY-NC 4.0** | 전 세계 | HF zhu-xlab/GBA.LoD1 1.05 TB | 비영리 한정이라 제외(실무 사용자) |

- 팩 단위: Census 카운티(cb_2024_us_county_500k, GEOID 5자리, 3,235개 — 준주 포함). 주 단위는 캘리포니아 1,200만 동이라 너무 크다. 건물은 중심점이 든 카운티에(경계 300 m 넓혀서 — 해안 간략화, 겹침은 런타임 src_key 중복 제거).
- 나라 상자: 본토·알래스카·하와이·푸에르토리코 네 개(`constants.US_BOUNDS`) — 매니페스트 `countries[].bounds`가 상자 목록을 받도록 했다(캐나다·멕시코가 본토 상자에 걸리지 않게).
- 고지: "Source: Overture Maps Foundation (buildings, release <판>, ODbL 1.0) — © OpenStreetMap contributors, Microsoft; processed by Gorani". ODbL은 share-alike라 팩(데이터베이스)도 ODbL로 둔다 — 데이터셋 카드에 적는다.

### 중국 — 결론: 당분간 OSM 그대로(보류)

- 공식 공개 건물 데이터 없음. 민간(百度·高德)은 폐쇄.
- 연구 데이터: ① **East Asian buildings**(Shi 2023, 中山大·武漢大, Zenodo 8174931, CC BY 4.0, 23 GB) — 중국·일본·남북한·몽골 바닥 윤곽, 높이는 안 적혀 있음(Overture 베이징 건물의 출처가 이것). ② **CNBH-10m**(Wu 2023, 10 m 래스터 높이 2020, Zenodo 7923866 — 라이선스 칸 비어 있음, 확인 필요). ③ 3D-GloBFP 중국 성 파일은 찾지 못함.
- Overture 베이징 둥청 7 km 상자: 50,336동 중 height 1.1 % → 높이는 사실상 없다.
- 법: 测绘法·2015 지도관리조례가 지도 데이터의 국외 보관·반출을 제한한다(확인 필요 — 2차 자료뿐). 연구 데이터(CC BY)는 저자들이 공개한 것이지만, 우리가 중국 건물 팩을 HF(미국)에 두는 것은 위험을 떠안는 일이라 사용자 결정 사항.
- 만들려면: ①의 윤곽 + ②의 래스터 높이(중심점 표본, 등급 C)로 성(省)별 팩. 품질은 ML 추정이라 '참고' 수준.
