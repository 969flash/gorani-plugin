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
