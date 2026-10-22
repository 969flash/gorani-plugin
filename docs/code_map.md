# 코드 흐름 지도 (code_map) — 확정 아키텍처

어떤 파일부터 읽으면 되는지, 엔진 API가 무엇인지, 무엇에 의존하는지를 적는다. 산출물 정의는 `docs/deliverables.md`, 데이터·DB는 `docs/data_sources.md`, 패널 메시지는 `docs/panel_ui.md`, 마일스톤은 `docs/implementation_plan.md`.

- 확정일 2026-10-07. 세 설계서(`docs/arch_proposals/inrhino.md`·`onepath.md`·`hybrid.md`)를 세 관점(배포·단순성·데이터)으로 심사한 결과 **in-Rhino 안이 뼈대**(배포 38·단순 38·데이터 37 — 합계 1위), 여기에 심사가 지목한 접목 13건(아래 §0.2)을 넣었다. 근거 표기: **[실측 job]** = `result/rhino_jobs/<job>/out/`, **[로컬]** = 이 Mac에서 직접 확인, **[00~08 §x]** = `docs/research/`, **확인 필요** = 아직 못 봤음.

---

## 0. 한 줄 결정과 접목

### 0.1 결정

**런타임은 Rhino 8 CPython(3.9) + 표준 라이브러리 + RhinoCommon만. pip 패키지 0개, 서브프로세스 없음. 베이크가 곧 3dm 생성이다.** 공공데이터 수집·DB 구축은 개발 Mac `dev_*.py`(geopandas·shapely·scipy)에서만 돈다. 패널은 `context_builder.run(request, progress, doc)` 하나만 안다.

| 결정 | 선택 | 버린 것 | 이유(근거) |
|---|---|---|---|
| 런타임 배치 | Rhino CPython 안 동기 실행 | 외부 python3 서브프로세스(`docs/panel_ui.md` 현재 문구) | 배포 PC에 python이 없다. "폴더 복사 + `cmd_install.py`"로 끝나야 한다 |
| 런타임 의존성 | 표준 라이브러리 + RhinoCommon | `# r: numpy, scipy, shapely, rhino3dm`(onepath) | 첫 실행 휠 66 MB 다운로드·사내 망 차단·macOS 14 하한(rhino3dm cp39) 전부 사라짐 [로컬 pip download]. 되돌릴 보험은 §7.4 |
| 3dm 생성 | RhinoCommon 베이크 → `doc.WriteFile` 사본 | rhino3dm writer + `_-Import`(deliverables A.5 현행) | Delaunay·투영·압출·해치가 RhinoCommon에 전부 있고 수 초 안에 끝남을 실측 [1007-203742-8486]. Import 단계·rhino3dm 의존 제거 |
| 지형 TIN | 런타임 `Mesh.CreateFromTessellation` | 빌드 시 서울 전체 TIN → 타일 blob(hybrid) | 4,121점 0.01 s·30,276점 0.03 s 실측. 도엽 1장 교체가 `DELETE … WHERE sheet=?`로 끝남. tiles 테이블·바이너리 코덱이 없음 |
| 정합 오차(P0) | **빌드 때 샘플점을 `features`(theme `qa`, kind `align_sample`)에 저장 → 런타임 `statistics`로 중앙값·p90** | 런타임 shapely(onepath) / tiles(align) 테이블(hybrid) / P1로 연기(inrhino 원안) | 새 테이블 없이 hybrid의 사전 계산 이점을 가져옴. `dev_probe_alignment.sample_along`·`nearest_dist` 재사용 |
| 베이스맵 .ai | **순수 python이 레거시 AI(AI5 PostScript)를 직접 쓴다**(`scripts/basemap_ai.py`, 2026-10-08 전환) | Rhino `BM::` 2D 레이어 → `_-Export`(이전 구현) · SVG → Illustrator JSX(06 주력안) | Rhino export는 아트보드가 용지가 아니고(객체 bbox), 한글이 UTF-8 바이트로 깨지고, 문서의 다른 대상지 객체가 섞였다. BM 베이크·선택·export가 전체 시간의 절반(25 s+)이었다. 직접 쓰기: A1 1:3000 0.4 s, Illustrator에서 아트보드 = 용지, 한글 레이어명·라벨 확인 |
| 현황도·조서 | 순수 python SVG·CSV(`sheet_svg`·`context_report`) | — | Rhino 무관. python3 unittest |
| 긴 작업 중 UI | UI 스레드 동기 + 콜백 안 `RhinoApp.Wait()` | 스레드·서브프로세스 | 반경 500 m + A1 1:3000 ≈ 8 s(§5.8 예산, 1:5000 프레임은 수십 초). Wait가 Mac WKWebView를 펌핑하지 않으면 `prepare`만 스레드(§4.5) |

### 0.2 심사에서 가져온 것 (출처 안)

| # | 접목 | 출처 | 이 문서 위치 |
|---|---|---|---|
| 1 | 진행률·취소를 콜백 하나 `progress(phase, fraction, text) -> bool`(False = 취소)로 | onepath | §4.4 |
| 2 | `prepare(request, progress) -> Prepared`(Rhino 금지)와 `run()`을 명시적으로 분리. Rhino 모듈은 `run` 안에서 지연 import | hybrid | §4.1 |
| 3 | phase 이름·가중치를 `docs/panel_ui.md`의 8개(`query·refresh·terrain·write_3dm·basemap·sheets·tables·import`)·`PHASE_WEIGHTS`에 맞춤 | 공통 지적 | §4.4 |
| 4 | `get_meta_lines(prepared)` 한 함수로 시트 여백 5줄·CSV·context.json·CTX::Ref 문자열 공유, 시트 16장은 `SHEETS` 선언 표 하나(키 → 분류 함수·바탕 방식) | onepath | §3 `context_report`·`sheet_svg` |
| 5 | 요청 dict에 `site_db`·`context_db` 경로 덮어쓰기 키 — 테스트가 fixture DB를 꽂는 유일한 방법 | onepath | §4.2 |
| 6 | python3 테스트에서 `rhino3dm.File3dm.Read`로 결과 3dm 되읽어 레이어·객체 수·UserString·단위 단언(rhino3dm은 테스트 전용, 배포 불포함) | onepath·hybrid | §8 |
| 7 | `dev_rhino_run.py`가 `data/*.db` 전부를 심링크(지금은 `constants.DATABASE_PATH` 하나) | onepath 지적(확인: `scripts/dev_rhino_run.py:128–130`) | §3 |
| 8 | `doc.Strings.SetString("GORANI_ORIGIN_E", …)`로 문서 수준 메타(RhinoCommon `StringTable.SetString` 존재 [로컬 RhinoCommon.xml]) | hybrid | §6 |
| 9 | 건물 압출은 평면 명시 오버로드 `Extrusion.Create(crv, Plane(Point3d(0,0,base_z), ZAxis), height, True)`(bench F_z_range 12→42 확인). 방향 검사는 M2 드라이버의 단언으로만 | inrhino + hybrid | §5.3 |
| 10 | `tests/fixtures/seongsu_context.db`·`seongsu_site.db`(성수 ±1.05 km, 합 ≈10 MB)는 gitignore 하지 않고 커밋. 전체 DB에서 `dev_make_fixture.py`가 `ATTACH`+`INSERT … SELECT`로 추출(빌더 `--extent` 없음) | hybrid(축소) | §8 |
| 11 | Windows 노트북 검증을 M7에서 **M2 직후**로 당김(`driver_terrain`·`driver_full_run` 1회) | onepath | implementation_plan M2.5 |
| 12 | (삭제 — zlib BLOB. 실측 축소 1.8~2.2배라 가치 없음, §검토 반영) | — | — |
| 13 | 지형 메시 정점은 `Mesh.Vertices.UseDoublePrecisionVertices = True`로 두고, 원점은 **메시 생성 전** 로컬 좌표(단정밀도 근거 문구 정정) | 심사 지적 | §6 |
| — | (폐기) `context_baker.bake_basemap/export_ai` — 2026-10-08 `basemap_ai.py`로 대체. 베이스맵은 문서를 거치지 않는다 | 실측 | §7.2 |
| — | `# r: scipy` 1줄 폴백은 설계가 아니라 위험표의 보험으로만. `wheels/` 동봉 오프라인 설치는 절차 3줄만 기록 | onepath↔hybrid 절충 | §7.4 |

---

## 1. 실행 흐름 — 번호가 곧 읽는 순서

```
[개발 Mac, python3 — 1회·갱신 때만]
  dev_context_builder.py   수치지형도 139도엽 zip + GIS건물 zip → data/seoul_context.db (완료: 372 s, 1,509 MB, 995,026동)
  dev_make_fixture.py      전체 DB 2개 → tests/fixtures/seongsu_*.db (SQL 추출, ≈10 MB)
  dev_database_builder.py  (보유) 토지특성·UPIS → data/seoul_site.db
  dev_deploy.py            Yak 패키지(.rhp + scripts .pyc) · 데이터 팩(필지·컨텍스트·등고선 xz + manifest.json)

[국내 서버 VM, python3 — 문지기]
  server_gate.py           nginx auth_request로 팩 요청을 하루 한도로 거르고 비공개 버킷(PAR)에서 내준다 — docs/domestic_gate.md

[사용자 Rhino 8, 버튼 한 번]
  cmd_site.py ─► panel_host.py(Eto WebView) ◄─► site_ui.html
      │  generate{pnus, options, scales}
      ▼
  context_builder.run(request, progress, doc)
      1  prepare(request, progress)                 ← Rhino 금지. python3 unittest 대상
         lot_db.load(pnus) → target_lots, lot_name, origin(request.doc_origin 재사용 → 없으면 100 m 내림), extent_ring, bounds(범위 ∪ 최대 프레임)
         lot_db.load_parcels_in_bounds(…, limit=None) → near_lots
         context_db.load(bounds) → buildings·features(terrain/road/water/green/rail/bridge/label/qa)
         통계·기준일 경과·경고·meta 문자열(context_report.get_meta_lines)
      2  context_geometry.build(prepared)            ← RhinoCommon, 문서 금지
         get_local_pts(원점 적용, 유일한 자리) → TIN → 면 분류 → 수면 평탄 → 발자국 투영 → 압출 → 커브
         → BakeItem 목록(건물은 동별 Mesh)
      3  context_baker.bake(doc, items)              ← 문서 변경은 여기만
         CTX:: 레이어·UserString·Ref·doc.Strings·EarthAnchorPoint → WriteFile(context.3dm) → context.json
      4  basemap_ai.write_basemap(prepared, scale)    basemap_<축척>.ai — Prepared에서 직접(문서·Rhino 무관, python3 unittest 대상)
      5  sheet_svg.write_sheets(prepared, faces)     sheets/NN_*.svg 25장 + 썸네일 (Rhino 무관, 도면 스타일)
      6  context_report.write_tables(prepared)       tables/*.csv, log.txt
      ▼
  response dict(= panel_ui.md `done` 페이로드) → host.push
```

읽는 순서: `context_builder.run()` → `prepare()` → `context_geometry.build()` → `context_baker.bake()` → `sheet_svg.SHEETS` → `context_report.get_meta_lines()`. `cmd_site.py`는 명령 dict → 함수 호출 → push만이라 흐름 확인용으로만 본다.

---

## 2. 모듈 지도

파일은 `scripts/` 하나, 접두사로 환경 구분(CLAUDE.md). **보유** = 지금 있음(변경 없음), **보유+** = 있음·추가, **신규** = 마일스톤에서 만든다(스텁 선제 생성 금지).

| 파일 | 구분 | 환경 | 책임 | import |
|---|---|---|---|---|
| `cmd_install.py` | 보유+ | Rhino 진입 | 설치. 컨텍스트 DB 존재 확인 1줄 추가 | loader |
| `cmd_site.py` | 신규(패널 워크플로 소관) | Rhino 진입 | 컨트롤러: 명령 dict 라우팅, `busy`/`progress`/`cancel` 플래그, `context_builder.run` 호출, 결과 폴더 열기. 로직 없음 | loader → 아래 전부 |
| `site_ui.html` | 신규(패널 워크플로 소관) | — | 프런트 전부 | — |
| `panel_host.py` | 보유 | Rhino | Eto WebView 호스트·브리지·`push()` | — |
| `loader.py` | 보유 | Rhino | 로직 모듈 로더·리로드 | — |
| `i18n.py`·`i18n.json` | 보유(2026-10-21) | 공통 | 다국어: `tr("한국어 원문", …)` → 지금 언어(en·ko·es·ja·zh). 사전 `i18n.json`은 패널 JS `tr()`와 공용, 언어는 환경변수 `GORANI_LANG`(cmd_site가 명령마다 바꾼다). `docs/panel_ui.md` '언어' | constants |
| `constants.py` | 보유+ | 공통 | 추가: `CONTEXT_RADIUS=500`, `ORIGIN_SNAP=100`, `ORIGIN_MAX_OFFSET=20000`, `TOPO_MINOR_KINDS`, `EXTENT_ARC_SEGMENTS=12`, `CTX_LAYERS`, `BM_LAYERS`, `PHASES`·`PHASE_WEIGHTS`, `AI_FONT_CMAP`, `CONTEXT_MAX_EXTENT`(bbox 질의 창), `TERRAIN_RESAMPLE=4.0`, `CLASSIFY_GRID=50.0`, `WATER_LIFT=0.02`, `TEST_CONTEXT_PNU`, 시트 범례 표 | — |
| `non_rhino_utils.py` | 보유+ | 공통 | 추가 6함수: `is_point_in_ring`(ray casting), `GridIndex`(50 m 버킷), `get_resampled_ring`(선형보간), `get_ring_orientation`(신발끈 부호), **`get_bbox(geometry) -> (min_x, min_y, max_x, max_y)`**(새 코드는 전부 이것만; 기존 `get_bounds_from_geojson`은 (min_x, max_x, min_y, max_y) '구 순서' — review_map 호환으로만 남기고 docstring 표기), **`get_extent_ring(lots_rings, radius, shape) -> ring`**(범위 폴리곤의 유일한 정의, §5.0) | constants |
| `lot_db.py` | 보유+ | 공통 | 필지·오버레이 bbox 질의(`load`, `load_parcels_in_bounds`, `load_near_overlays`). 추가 1줄: `load_parcels_in_bounds(…, limit=None)`이면 `LIMIT`을 붙이지 않는다(지도 뷰포트는 기존 5000 유지, `prepare`는 None) | constants |
| `pnu_loader.py`·`review_map.py` | 보유 | 공통 | 주소 해석·패널 지도 GeoJSON | lot_db |
| **`context_db.py`** | **있음+** | 공통(Rhino 금지) | `seoul_context.db` bbox 질의 → `BuildingInfo`·`FeatureInfo`·`ContextData`; `get_counts`. 추가: `load_buildings_in_bounds(bounds, include_minor=False, …)` SQL 1줄 `AND NOT (src_key LIKE 'ngii:%' AND ngii_kind IN (?,?,?))`(`constants.TOPO_MINOR_KINDS` = 무벽건물·가건물·공사중 — 보충 행에만 건다, 대장 매칭 벌크 건물은 ngii_kind와 무관하게 유지) | constants |
| **`context_builder.py`** | 신규 | 공통(Rhino 금지) + `run`만 Rhino | 엔진 API: `prepare`·`run`·`preflight`·`get_progress_message`. `run`은 Rhino 모듈을 함수 안에서 `import`하고 `doc.Strings["GORANI_ORIGIN_E/N"]`을 읽어 `request["doc_origin"]`에 넣어 `prepare`에 준다(§6) | lot_db, context_db, context_report, non_rhino_utils |
| **`context_geometry.py`** | 신규 | Rhino(RhinoCommon, `RhinoDoc` 금지) | `build(prepared) -> ContextGeo`: `get_local_pts`(원점 적용 유일), TIN·면 분류·수면 평탄·투영(`ProjectPointsToMeshesEx`)·건물 Mesh·커브 | Rhino.Geometry, non_rhino_utils, sheet_svg, constants |
| **`context_baker.py`** | 신규 | Rhino(RhinoDoc) | `bake`(레이어 ensure·속성·UserString·Ref·단위 환산·`RedrawEnabled` try/finally·`WriteFile` 사본)·`clear_previous`(`GORANI_LOT_KEY`, `FindByUserString`)·`import_3dm`(재삽입용 `_-Import` 5줄 + `context.json.origin` ≠ 문서 원점이면 차이만큼 `Transform.Translation` 보정) | Rhino, constants |
| **`sheet_svg.py`** | 신규 | 공통(Rhino 금지, origin을 모른다 — 입력은 전부 세계좌표 m) | 프레임 수학 `Frame(paper_mm, scale, center)`(유일한 정의 — `context_geometry`도 이것을 쓴다) + 도면 템플릿(`get_map_box` — A3 기준 side·bottom·map, 지도 칸이 곧 Frame) + 도면 스타일 해석 `get_style(options)`(STYLE_PRESETS ← options.style) + SVG 작성기(`<g id>`·clipPath·범례·카드·여백 줄) + `SHEETS = {키: (classify_fn, 바탕 방식)}` 25장(2026-10-13, 23 항공사진은 영상 타일을 `<image>`로 — 이 장만 네트워크, 24 입체 매스도는 `get_axo_scene` 평행 투상 + 화가 알고리즘) + 블록(`get_blocks`)·보행망(`get_walk`, heapq Dijkstra)·썸네일(`render_thumbnail` — 스캔라인 격자 + zlib PNG). 레이어 .ai는 `get_sheet_ai` → `basemap_ai.write_svg_ai`(누를 때). 패널 미리보기·적용은 `context_builder.preview_sheet`·`apply_style`이 `render_sheet`·`write_sheets`를 다시 부른다. Seoungsu `make_basemap_L.py`의 `path_of/geom_paths/save_svg` 이식(geopandas 제거) | constants, non_rhino_utils, context_report |
| **`context_report.py`** | 신규 | 공통(Rhino 금지) | `get_meta_lines(prepared)`(자료기준·출처·좌표계·정합·경고 5줄 — SVG·CSV·json·Ref가 같은 문자열), `write_tables`(CSV 5), `write_context_json`, `append_log` | constants |
| **`basemap_ai.py`** | 신규(2026-10-08) | 공통(Rhino 금지) | `write_basemap(prepared, scale, out_dir)` — 레거시 AI5 PostScript 직접 작성(§5.7·§7.3). 색은 도면 스타일(`get_layer_paint` → CMYK, 2026-10-13). `export_basemap`(context_builder)이 다른 축척 재작성에 쓴다 | sheet_svg(Frame), constants |
| `dev_context_builder.py` | 있음+ | 개발 python3 | 도엽 features + GIS건물 병합·높이 규칙(`decide_height`). 139도엽 전체 빌드 완료(372 s). 추가: 정합 샘플(theme `qa`) 적재 | geopandas·pyogrio·shapely·pandas·numpy, constants |
| `dev_make_fixture.py` | 신규(≈30줄) | 개발 python3(sqlite3만) | 전체 DB 2개를 `ATTACH`하고 `INSERT INTO … SELECT … WHERE bbox 교차`로 `tests/fixtures/seongsu_context.db`(buildings·features·data_sources·source_files)와 `seongsu_site.db`(parcels·overlays·parcel_overlays·parcel_land_use·data_sources, 스키마 v5, `user_version 5`, bbox 인덱스 포함) 생성 | constants |
| `dev_deploy.py` | 신규 | 개발 | `yak`: rhinocode로 Gorani .rhp 빌드 + scripts/(평문 loader·cmd_site, 로직 .pyc optimize=2) → yak CLI. `packs`: 필지(rtree 제거)·컨텍스트(등고선 제외)·등고선 DB → xz + manifest.json. 받는 쪽은 `data_pack.py` | — |
| `osm_context.py` | (2026-10-13) | Rhino | Global 모드 컨텍스트 — Overpass 건물·피처 + 지형 타일 → `ContextData`(context_db와 같은 꼴). 일본(2026-10-21): 받아 둔 PLATEAU 팩 건물을 먼저, OSM 건물은 겹치지 않는 것만(`get_buildings_apart`), 지형은 지리원 5 m 타일(없으면 AWS). Overpass가 막혀도 PLATEAU가 있으면 건물·지형만으로 만든다 | `data_pack`·`context_db` 도로면(2026-10-22): OSM은 도로가 선뿐이라 `get_road_surface`가 폭(width → lanes → 등급 기본값)만큼 버퍼한 `road/surface` 피처를 더한다(터널 제외, attrs derived=buffer — 베이스맵은 경계선 없이 채우기만). 일본은 팩의 PLATEAU 도로면(`load_plateau_roads`)을 먼저 쓰고 OSM 버퍼는 중심선 가운데가 그 밖인 것만(`get_surfaces_apart`). `area:highway`·주차장·보행자 광장 면은 면 그대로 나라별 팩(2026-10-22): `get_country`가 `constants.COUNTRY_PACKS` 상자로 나라를 고르고 `load_plateau_buildings`(이름은 옛 것)가 그 나라 팩을 팩마다 따로 읽는다 — 일본 PLATEAU·네덜란드 PDOK |
| `dev_plateau.py` | (2026-10-21) | 개발 | 일본 건물·도로면 팩 — CKAN 목록 → zip을 HTTP Range로 열어 `udx/bldg` GML만 읽고(`roads`는 있는 팩에 `udx/tran` 도로면을 features 표로 더한다) 시구정촌마다 `jp<코드>_context.db.xz` + `jp/manifest.json` → HF `jp/` | — |
| `dev_nl.py` | (2026-10-22) | 개발 | 네덜란드 건물 팩 — PDOK 3D Basisvoorziening 도엽 zip(GeoPackage) → pyogrio·pyproj로 바닥 윤곽·높이 → `nl<도엽>_context.db.xz` + `nl/manifest.json` → HF `nl/`(올리기는 사용자 확인 뒤) | — |
| `dev_fr.py` | (2026-10-22) | 개발 | 프랑스 건물 팩 — Géoplateforme Atom 피드 카탈로그 → 데파르트망 7z(py7zr) → GeoPackage `batiment`(pyogrio·pyproj) → `fr<데파르트망>_context.db.xz` + `fr/manifest.json` → HF `fr/`(사용자 확인 뒤) | — |
| `dev_rhino_run.py` | 보유+ | 개발 | 128–130행: `data/*.db` 전부 심링크 | constants |
| `dev_database_builder.py`·`dev_probe_*.py` | 보유 | 개발 | 필지 DB·08 실측 재현 | — |

import 방향(화살표 = import한다):

```
cmd_site ─► loader ─► context_builder ─► lot_db, context_db, context_report, non_rhino_utils, constants
                                      └─(run 안에서)─► context_geometry ─► sheet_svg(Frame), non_rhino_utils, constants
                                                        context_baker    ─► constants
                                                        sheet_svg        ─► context_report, non_rhino_utils, constants
```

**파일 수**: Rhino 런타임 신규 로직 모듈 **6개**(context_db ✓·context_builder·context_geometry·context_baker·sheet_svg·context_report) + 보유 수정 3(constants·non_rhino_utils·cmd_install) + 진입 1(cmd_site) + HTML 1 + dev 신규 2(dev_deploy·dev_make_fixture) + dev 수정 2(dev_context_builder·dev_rhino_run) + 보유 수정 2(lot_db·context_db 각 1줄). Rhino 전용 모듈은 context_geometry·context_baker **2개**.

**만들지 않는 것**(이유): `utils.py` — RhinoCommon 공용 헬퍼가 두 모듈에서 겹칠 때 그때 분리 / `building_height.py` — 높이 규칙은 `dev_context_builder.decide_height`로 빌드 때 끝남, 런타임 VWorld 갱신(P1)이 생기면 그때 그 함수를 옮긴다 / `vworld_buildings.py` — P1 / `basemap_baker.py` — `context_baker` 함수 2개 / `bridges.py`·`alignment_qa.py` — `context_geometry` 안 함수 / `site_preflight.py` — `context_builder.preflight` / `site_baker.py` — `context_baker` / `dev_generate_context.py` — 서브프로세스 없음 / `dev_check_updates.py` — P1(10줄).

---

## 3. 데이터 흐름과 DB

```
[원천 zip, 사용자 수동]                         [dev_context_builder.py]                  [data/seoul_context.db]
수치지형도_5000/<도엽>.zip ×139 + sheets.csv ─► TOPO_LAYERS 36레이어 → GeoJSON(5186, mm) ─► features(theme/kind/code/name/value/attrs_json/sheet, bbox)
                                                교량·입체교차·IC 5 m 버퍼 안 표고점 → spot_struct
AL_D010_11_<기준일>.zip(GIS건물 695,754동) ──► A2 PNU 검증 → 수치지형도 건물 대표점 조인 ─► buildings(+sheet: ngii 행만, 높이 규칙 적용 완료)
                                                → 미매칭 ngii 건물 src_key 'ngii:*' 보충(실측 299,678동 = 43 %; 그중 무벽·가건물·공사중 165,168동은 런타임 기본 제외)
seoul_site.db 지목 도로 ∪ A001 도로경계 ──────► 10 m 샘플 최근접거리(dev_probe_alignment 재사용) ─► features(theme 'qa', kind 'align_sample',
                                                                                                    Point, value=거리 m, attrs {dx,dy})  ← M3
                                                                                              data_sources / source_files(sha256)
```

- 스키마는 `data_sources.md` §2.2 + `buildings.sheet`(이미 `dev_context_builder.SCHEMA_SQL`에 있음) + `features` theme `qa`. **새 테이블 없음.** RTree 없음, bbox B-tree 4열.
- 도엽 교체 = `DELETE FROM features WHERE source_id=? AND sheet=?` + `DELETE FROM buildings WHERE src_key LIKE 'ngii:%' AND sheet=?` → 그 도엽 재적재. 지형은 런타임 계산이라 재빌드 없음. 정합 샘플은 `qa` 행도 sheet로 교체.
- 건물 월간 교체 = 한 트랜잭션 `DELETE WHERE source_id='vworld_gis_building'` → INSERT(실패 시 이전 판 유지).
- **범위·프레임 규칙 3줄**(데이터량을 정하는 것은 반경이 아니라 베이스맵 프레임이다 — A1 1:3000 = 2.52×1.78 km 4.5 km², 1:5000 = 4.2×3.0 km 12.6 km²):
  1. DB 질의 1회 = `bounds` = `범위 bbox ∪ 요청 scales 중 가장 큰 프레임 bbox`(+여유 20 m) 하나로 buildings·features·parcels 세 테이블.
  2. CTX 레이어·TIN·조서(CSV)·시트 통계는 **범위 bbox 안 객체만**(건물·필지는 bbox가 범위와 겹치면 통째로).
  3. BM 레이어만 프레임 bbox(축척별 `BASEMAP_SCALE_LAYERS`).
- `near_lots`는 `lot_db.load_parcels_in_bounds(…, limit=None)`. 기본 `limit=5000`은 지도 뷰포트용(LIMIT+1 후 `truncated`)이라 그대로 쓰면 조용히 잘린다 — 실측 성수 1 km bbox 필지 8,918건(전부 읽기 0.34 s), A1 1:3000 프레임은 3만 건 이상. 그래도 `truncated=True`가 돌아오면 `ValueError`가 아니라 `warnings[code=lots_truncated]`.
- 실측(전체 DB, 성수 333-139): bbox ±520 m 건물 3,539동, ±1,020 m 10,126동 → 1:5000 프레임이면 4만 동·필지 10만 급. `preflight.estimate`가 1:5000에 '수십 초' 경고를 붙인다.

---

## 4. 엔진 API (`scripts/context_builder.py`)

### 4.1 함수 셋

```python
def prepare(request, progress=None):
    # type: (dict, callable) -> Prepared
    """Rhino 금지. 입력 검증 → 필지·컨텍스트 질의 → 원점·범위 → 통계·경고·meta. python3 unittest가 전부 덮는다."""

def run(request, progress=None, doc=None):
    # type: (dict, callable, object) -> dict
    """Rhino 안. prepare → context_geometry.build → context_baker.bake → basemap_ai → sheet_svg → context_report.
    Rhino 모듈은 이 함수 안에서 import한다. 반환 dict는 panel_ui.md `done` 페이로드와 같은 모양(type 키만 없음)."""

def preflight(request):
    # type: (dict) -> dict
    """Rhino 금지, 100 ms급. prepare의 질의를 COUNT로만 — 건물·필지 수, 도엽 보유/미보유, 예상 초·MB, 빈 시트, 기준일 경고. panel_ui.md `preflight_result`용."""

def get_progress_message(phase, fraction, text, skipped, details):
    # type: (str, float, str, set, dict) -> dict
    """순수 함수. constants.PHASES·PHASE_WEIGHTS로 phase_status·percent를 계산해 panel_ui.md `progress` 페이로드를 만든다. 컨트롤러가 콜백 안에서 부른다."""
```

`Prepared`(dataclass): `request`(기본값 채운 사본)·`lot_name`·`target_lots`·`near_lots`·`origin=(e, n)`(재사용 여부 `origin_reused`)·`radius`·`shape`·`extent_ring`(§5.0 링)·`scales`·**`bounds=(min_x, min_y, max_x, max_y)`**(GeoJSON bbox 순서 — `context_db.load`·`lot_db.load_parcels_in_bounds`와 같다; 코드베이스의 다른 세 순서는 §검토 반영)·`frame_bounds`(축척별 dict)·`buildings`(필터는 SQL에서 끝남: `include_minor` — 보충 행의 무벽·가건물·공사중)·`features`(ContextData)·`align_samples`·`overlays`·`sources`·`meta`(기준일·경과 개월·레벨·`get_meta_lines` 결과)·`stats`(높이 출처 비율·등급 A+B·노후·도로율)·`warnings`·`skipped_phases`·`result_dir`. 좌표는 전부 **EPSG:5186 세계좌표 m** — 원점은 아직 안 뺐다.

### 4.2 요청 dict

```jsonc
{
  "target": {"mode": "lots", "pnus": ["1120011500103330139"]},   // 2026-10-10. area = {"mode":"area","ring":[[x,y]]}, point = {"mode":"point","center":[x,y]} (EPSG:5186)
                                             // resolve_target이 방식별 경계 링·안의 필지·중심·이름·키를 만든다(panel_ui.md §대상지 방식)
  "pnus": ["1120011500103330139"],          // 예전 요청 호환 — target이 없으면 필지 방식. prepare 뒤에는 대상 필지 PNU 목록으로 덮인다
  "lot_name": null,                          // null = lot_db 주소로 "성수동2가_333-139" 생성(결과 폴더명)
  "options": {                               // panel_ui.md 옵션 20키 그대로 넘겨도 된다. 엔진이 쓰는 키만 아래. 모르는 키 무시, 빠진 키 constants 기본값
    "radius": 500, "shape": "buffer",        // m 100~2000 / buffer(대상지 볼록껍질 오프셋, §5.0)|circle|rect|frame(가장 큰 축척 용지 프레임)
    "placement": "origin",                   // origin(대상지 중심 → (0,0)) | world(EPSG:5186 그대로, §6)
    "make_basemap": true, "paper": "A1", "paper_mm": [841, 594], "basemap_layers_on": [],
    "scales": [3000],                        // 베이크·내보낼 프레임 축척. 가장 큰 값이 DB 질의 bounds를 정한다(§3). 패널 generate 페이로드에 포함(패널 워크플로에 전달)
    "make_sheets": true, "sheet_ids": [1,2,3,4,5,6,7,8,9,10,11,12,13], "floor_breaks": [12, 20], "elev_preset": "20m",
    "make_tables": true,
    "include_minor_buildings": false,        // 보충(src_key 'ngii:%') 행의 무벽·가건물·공사중 — SQL에서 제외(TOPO_MINOR_KINDS)
    "demolished": "dashed",                  // P1. v1은 status가 전부 'active'(995,026/995,026)라 항상 0 — 받기만 하고 무시
    "refresh_buildings": false,              // P1. v1은 항상 phase refresh=skipped
    "include_zoning": true, "terrain_vertex_color": false,
    "terrain_step": 0                        // m. 0 = 매끈, > 0 = 계단 지형(§5 5.2d)
  },
  "result_root": null,                       // null = <루트>/result
  "site_db": null, "context_db": null,       // null = constants 경로. 테스트가 tests/fixtures/seongsu_site.db·seongsu_context.db를 꽂는 자리
  "doc_origin": null                         // run이 doc.Strings GORANI_ORIGIN_E/N에서 읽어 채운다(§6). 테스트는 이 키로 직접 주입. prepare는 doc을 모른다
}
```

검증은 `prepare` 첫 줄: PNU 19자리·DB 파일 존재·반경 범위·용지 mm 양수·`scales ⊂ BASEMAP_SCALES`·`doc_origin`과 대상지 중심 거리 ≤ `ORIGIN_MAX_OFFSET`. 실패는 `ValueError`(한국어 메시지).

### 4.3 응답 dict (= `panel_ui.md` `done` 페이로드)

```jsonc
{
  "ok": true, "cancelled": false,
  "dir": ".../result/성수동2가_333-139_20261007", "lot_name": "성수동2가_333-139", "elapsed_s": 4.2,
  "options": { ...요청 options에 기본값 채운 것... },
  "context": {"path": ".../context.3dm", "layers": 12, "buildings": 3500, "lots": 8900, "demolished": 0, "tin_points": 4121,
              "origin": [204700.0, 548900.0], "origin_reused": false, "model_unit": "Millimeters", "imported": true, "import_text": ""},
  "basemap": {"ready": true, "paper": "A1", "layers": 14, "scales": [3000], "exported": [".../basemap_3000.ai"]},   // export_scale 검산 실패면 ready=false
  "sheets": [{"id": 1, "name": "위치·범위도", "path": ".../sheets/01_위치범위도.svg", "empty": false, "reason": ""}, ...],
  "tables": [{"name": "parcels.csv", "path": "..."}, ...],
  "files":  [{"name": "context.3dm", "path": "...", "bytes": 18400000}, ...],
  "warnings": [{"level": "warn", "code": "height_estimate", "text": "높이 추정 비중 큼 — 등급 A+B 61 %", "detail": "", "action": null, "center": null}],
              // code ∈ height_estimate|multipart|coverage|stale_*|skipped|lots_truncated|export_scale|origin_reused
  "quality": {"height_src": {"height": 0.31, "grnd_flr": 0.44, "topo_flr": 0.19, "default": 0.06},
              "align": {"median": 1.2, "p90": 3.9, "n": 1431, "low_sample": false},
              "skipped": {"buildings": 1, "lots": 0}, "mismatch_count": 0,
              "dates": {"lot": "2026-05-13", "building": "2026-09-06", "terrain": "2024~2026", "upis": "2026-09"}},
  "qa_geojson": {"type": "FeatureCollection", "features": []},
  "error": null                              // ok=false면 {"code", "title", "detail"} — code ∈ no_lots|context_db_missing|no_terrain_points|doc_unit_invalid|export_failed|cancelled|exception
}
```

`context.imported`는 베이크 성공 여부(베이크가 곧 '문서에 넣기'). 부분 실패(베이스맵·시트 한 장)는 `ok=true` + `warnings[code=skipped]` + 해당 항목 `ready:false`/`empty:true, reason:"오류"`(panel_ui.md phase 단위 예외 규약 그대로).

### 4.4 진행률·취소 — 콜백 하나

- 시그니처 **`progress(phase, fraction, text) -> bool`**. `phase ∈ constants.PHASES = ("query", "refresh", "terrain", "write_3dm", "basemap", "sheets", "tables", "import")`, `fraction` 0~1(단계 안), `text` 사용자용 한 줄. **False를 돌려주면 취소** — 엔진은 `Cancelled`를 올리고 이번 베이크 id를 `doc.Objects.Delete`로 되돌린 뒤 `ok=false, cancelled=true, error.code="cancelled"`. 부분 폴더는 두고 `log.txt`에 "cancelled at <phase>".
- 호출 빈도: 단계 시작(0)·끝(1) 최소 2회, 긴 루프(건물 200동·시트 1장)마다. python3 테스트는 리스트에 append하는 람다, 취소 시나리오는 "2번째 호출에서 False".
- 가중치 `constants.PHASE_WEIGHTS = {"query": 15, "refresh": 10, "terrain": 25, "write_3dm": 15, "basemap": 10, "sheets": 15, "tables": 5, "import": 5}`(panel_ui.md 그대로). `skipped`(옵션으로 꺼진 phase + v1의 `refresh`·`import`)는 분모에서 뺀다.
- in-Rhino에서의 phase 뜻: `query` = prepare 전체 / `refresh` = VWorld 갱신(P1, v1 `skipped` detail "건너뜀 — v1 미구현") / `terrain` = `context_geometry.build` 전체(TIN·분류·투영·압출·커브) / `write_3dm` = CTX 베이크 + `WriteFile` 사본 + context.json / `basemap` = BM 베이크 + `.ai` / `sheets` / `tables` / `import` = **`skipped`("베이크로 대체")** — panel_ui.md 개정 때 목록에서 뺀다(§9).
- 컨트롤러 쪽 콜백(`cmd_site`): `host.push(context_builder.get_progress_message(...))` → `Rhino.RhinoApp.Wait()` → `return not self._cancel_requested`. `cancel` 명령은 플래그만 세운다(Wait 중 flush되어 들어옴). `_phase_detail[phase] = text` 1줄은 컨트롤러가 들고 있는다.
- **확인 필요(M4 첫 항목)**: `RhinoApp.Wait()`가 Mac WKWebView(Eto) 이벤트를 펌핑하는가. 안 되면 `prepare`(Rhino 금지)만 `threading.Thread`로 돌리고 push는 `Application.Instance.AsyncInvoke`, 베이크부터는 UI 스레드.

### 4.5 오류 규약

- 도메인 오류 = `ValueError`/`KeyError`/`FileNotFoundError`/`RuntimeError` + 한국어 메시지 → `run`이 `ok=false, error{code, title, detail}`. 그 외 예외는 `code="exception"` + traceback. 컨트롤러 `_guard`(기존 컨트롤러 패턴)는 `run` 바깥 명령(search·select…)만 감싼다.
- 생성 중단 조건은 `no_lots`(DB에 없는 PNU·범위 안 필지 0)·`context_db_missing`·`no_terrain_points`(범위 안 등고선·표고점 0)·`doc_unit_invalid`(문서 단위 None/Custom)·`origin_mismatch`(문서 원점과 대상지 중심이 `ORIGIN_MAX_OFFSET` 초과 — "다른 지역 문서입니다 — 새 문서에서 생성하세요"). 나머지는 경고로 계속. **건물 투영 폴백은 중단이 아니다**: 동별 투영점 0이면 ① 가장 가까운 TIN 정점 Z(`GridIndex` 재사용) ② 그래도 없으면 그 동 건너뛰고 `warnings[code=skipped]` + log(§5.5).
- 피처 하나의 실패(자기교차 발자국 → `Extrusion.Create` None, 깨진 링)는 건너뛰고 `warnings[code=skipped]` + `log.txt`에 id(CLAUDE.md "예외는 건너뛰거나 경고").

---

## 5. 지오메트리 설계 요지 (`context_geometry`)

| 단계 | 방법 | 실측 |
|---|---|---|
| 5.0 범위 링 | `non_rhino_utils.get_extent_ring(lots_rings, radius, shape)` **하나**가 범위 폴리곤의 유일한 정의. `buffer` = 대상지 좌표 볼록껍질(단조 체인 20줄) 각 변을 바깥으로 radius 밀고 꼭짓점에 호(`EXTENT_ARC_SEGMENTS` 8~16분할) — 볼록이라 자기교차 없음 / `circle` = 중심 원 64각 / `rect` = bbox+radius. prepare·preflight(`extent_geojson`)·BM `10_site`·SVG #1·`CTX::Ref` 범위 커브·면 분류 `outside` 전부 이 링. RhinoCommon `PolylineCurve.Offset` 경로는 없다(패널 워크플로에 전달) | 순수 python, 테스트 가능 |
| 5.1 입력 점 | `terrain/contour` 4 m 리샘플(`get_resampled_ring`) + `terrain/spot`(`spot_struct` 제외) → **TIN 입력 범위 = 범위 bbox ∪ 적재된 건물 bbox 합집합**(+20 m; 큰 단지 발자국이 TIN 밖에 걸리지 않게) → (x,y) 중복 제거(dict) → 범위 링 정점(Z = 최근접 입력점) → 수면 경계 2 m 조밀화 점 | 성수 R=500: 3,864점 |
| 5.2 TIN | `Mesh.CreateFromTessellation(local_pts, [], Plane.WorldXY, False)`. 제약변 없음(겹치는 링을 edges로 넣으면 `IsValid=False` 실측). `Vertices.UseDoublePrecisionVertices = True` | 4,121점 0.01 s / 30,276점 0.03 s, Z 보존 [1007-203742-8486] |
| 5.2b 출력 지형 = 쿼드 위주 메시(2026-10-10 개정) | TIN은 **보간에만**. 범위 링으로 평면 Brep 하나 → 범위와 겹치는 분류 폴리곤 링 전부 + 대상지 링으로 `BrepFace.Split` → `Mesh.CreateFromBrep`(`SimplePlanes=False`·`MaximumEdgeLength=TERRAIN_GRID` 3 m·`GridAspectRatio=1`) — 영역 경계는 원래 선 그대로, 안쪽은 정사각 쿼드, 경계 옆만 삼각형. 면끼리 모서리를 공유해 이웃 영역 경계 정점이 같다(용접 → 이음매 없음). 영역마다 안쪽 한 점으로 분류(우선순위 PIP) → 정점 Z = TIN 수직 투영 1회. **버린 방법**: 격자를 범위로만 자르고 쿼드 중심으로 분류(경계 계단 — 사용자 거부), 격자를 분류 링 643개로 `SplitWithProjectedPolylines`(243 s·무효 메시) | 반경 500 m: 영역 825·분할 3.0 s·투영 2.3 s, 범위 면적 비 1.0005, 정점 Z − TIN 0.004 mm |
| 5.2c 대상지 바닥·평탄화 | 대상지 링도 분할 커브에 넣어 대상지 영역을 정확히 떼어 낸다(`site_output=mesh` 또는 `flatten_site`일 때만 — 둘 다 아니면 대상지도 일반 분류). 바닥 메시 = `CTX::Site::ground`(대상지 색 236,150,120, 필지 방식 기본). 평탄화 = 안쪽 정점 Z = 경계 자연 지반 mean|min|max → 바닥 메시(`site_output=mesh`면 Site::ground, 아니면 `CTX::Terrain::site_flat`) + 경계 수직 벽 `CTX::Terrain::site_wall`(대상지 원지형 메시의 바깥 경계 정점 그대로 — 윗선 = 주변 지형 경계 정점, 아랫선 = 평탄 높이. 경계를 다시 뽑아 만들면 정점이 어긋나 틈이 보였다, 2026-10-10) + 원지형 사본 `CTX::Terrain::site_original`(처음 만들 때 레이어 꺼짐). 건물은 최종 지반에 투영 | 필지 5,575.6 ㎡ → 바닥 메시 5,575.9 ㎡, 구역 6만 ㎡ 평탄 60,000.0 ㎡(`driver_target_modes`) |
| 5.2d 계단 지형(옵션, 2026-10-16) | `terrain_step` > 0이면 분류·수면까지 끝난 지반 메시(terrain·road·green·rail·water, 평탄화 안 한 Site::ground)를 `non_rhino_utils.get_stepped_mesh`로 바꾼다 — 정점 단 = floor(z/step)(경계 0.1 mm 안은 위 단), 한 단 안의 면은 그 높이로, 걸친 면은 삼각형 둘레를 돌며 단마다 다각형 + 단 경계선마다 수직 벽(아래 단 쪽을 본다). 교차점은 늘 아래 → 위 정점으로 보간해 이웃 면·다른 분류 메시와 같은 값. 벽 정점은 단 면과 따로(용접하면 모서리 음영이 뭉개진다). 평탄화 경계 벽 윗선은 `get_stepped_edges`로 같은 교차점·단 높이. 원지형 사본·시트(표고·경사)는 매끈한 TIN 그대로. 건물 바닥 = 계단 지반 최저 | 122,500 쿼드(고저 60 m) 1 m 단 → 41.6만 면 1.15 s(python3) |
| 5.3 면 분류 | 면 중심 → `GridIndex`(50 m) 후보 → `is_point_in_ring`(외곽 in AND 구멍 out). 우선순위 water > rail > road > green > terrain, 범위 밖 `outside`. `Mesh.CreateFromFilteredFaceList`로 분류별 메시 | 순수 python 0.69 s vs `Curve.Contains` 0.82 s(2,549 vs 2,546면). 1 km는 bbox 전수 16 s → 격자로 **1 s 안쪽 목표(M2 확인)** |
| 5.4 수면 | 수면 폴리곤(features water ∪ 지목 하천·구거·유지) 경계 샘플을 `ProjectPointsToMeshes`로 투영 → 최저 Z = 수위 → 내부 정점 Z 고정 → `CTX::Water` 평면 메시(+0.02 m). UserString `NAME`·`LEVEL_M`·`LEVEL_SRC=terrain_min` | — |
| 5.5 건물 | 발자국 정점 전체를 **`Intersection.ProjectPointsToMeshesEx([terrain], pts, (0,0,-1), tol, out indices)`** 1회 → `indices`로 동 복원(출력은 입력과 1:1이 아니다 — 빗나간 점 소실·다중 적중 중복) → 동별 최저 Z(`base_z`); 투영점 0인 동은 ① 최근접 TIN 정점 Z(`GridIndex`) ② 없으면 건너뛰고 `warnings[code=skipped]`+log; 고저차 >3 m면 `HEIGHT_SRC`에 `~slope` → 외곽 링 `PolylineCurve`(Z=base_z) → `Extrusion.Create(crv, Plane(Point3d(0,0,base_z), ZAxis), height_m, True)` + 구멍 `AddInnerProfile` → **`Mesh.CreateFromExtrusion(ext, MeshingParameters.Minimal)`**, 멀티폴리곤 파트는 한 메시로 `Append` → 동당 Mesh 1개 베이크. None이면 건너뛰고 경고 | Extrusion 그대로 구우면 첫 음영 표시 때 Rhino가 3천여 동의 렌더 메시를 만들어 **18.7 s** 멈췄다 → Mesh로 **0.9 s**. 생성 비용은 같다 |
| 5.6 커브 | Site·Parcels(구멍 보존)·Zoning(옵션, `CTX::Zoning::<구분>::<종류>` — 범위 bbox로 자름)·Ref 범위 원·도엽 경계 = `PolylineCurve` Z=0(주변 필지 드레이프는 P1 — 같은 `ProjectPointsToMeshes` 1줄) | — |
| 5.7 베이스맵 | `basemap_ai.write_basemap(prepared, scale, out_dir)` — `Prepared`(세계좌표)를 `sheet_svg.Frame`으로 용지 pt에 옮겨 AI5 PostScript를 쓴다. 프레임 밖은 버리고 선은 `get_clipped_lines`로 자른다. 레이어는 `get_basemap_layers(options, scale)`(축척별 on/off = `BASEMAP_SCALE_LAYERS`), 파일 순서 = `BM_LAYERS` 순(파일 뒤쪽 = Illustrator 위). 색은 K만(`0 0 0 k K/k`), 구멍 있는 면은 compound path(`*u`…`*U`), 라벨은 CP949 8진 이스케이프 + `AI_FONT_CMAP`(mac AppleSDGothicNeo / Windows MalgunGothic, `-KSCms-UHC-H`). 파일은 ASCII + CRLF | 성수 R=500 1:3000: 0.38 s · 6.3 MB · 레이어 15 |
| 5.8 실측(반경 500 m + A1 1:3000, 전체 서울 DB, 2026-10-08) | query 1.8 · terrain 1.6 · write_3dm 2.9(저장 0.7) · basemap 0.4 · sheets 1.4 · tables 0.1 → **8.3 s**, context.3dm **16.8 MB**(객체 8,672), basemap_3000.ai 6.3 MB. 이전 구현(BM 베이크 + Rhino export)은 51~63 s / 73~86 MB | 이번에 고친 병목: BM 베이크·export 제거(−35 s), 건물 Mesh(뷰 18.7→0.9 s), DB bbox 질의 창 `min_x BETWEEN`(건물 0.84→0.02 s), 시트 경로 캐시(5.1→0.85 s), `clear_previous` = `FindByUserString`(9.8→2.7 s, 17만 객체 문서) |

**좌표 규칙 1줄**: 시트·CSV·context.json에 들어가는 좌표는 전부 **세계좌표 m**, 로컬 좌표는 Rhino 객체에만. `build_terrain`이 `sheet_svg`용으로 돌려주는 삼각형 리스트도 세계좌표(함수 안에서 로컬 + origin으로 되돌림) — `sheet_svg`는 origin을 모른다.

`ponytail:` 폴리곤 불린·클리핑 없음 — 건물·필지·도로면·수면은 bbox가 범위와 겹치면 통째로, 3D 범위 경계는 TIN 면 제거로만. 옹벽·제방 단차가 거슬리면 `Mesh.CreatePatch` 브레이크라인을 성수 옹벽(F0040000 448건)으로 시험.

### 5.x Blender판 (`mesh_geometry`·`blender_baker`, 2026-10-15 — 2026-10-18 `blender_geometry` → `mesh_geometry`로 이름을 바꿔 SketchUp판과 함께 쓴다)

`context_builder.run`은 `get_host_modules()`로 지오메트리·베이커 쌍을 고른다(bpy가 있으면 Blender, 환경변수 `GORANI_HOST=sketchup`이면 SketchUp). 규칙은 위와 같고 방법만 다르다.

- 지형: TIN = `mathutils.geometry.delaunay_2d_cdt`(볼록 껍질). 면 분할 대신 범위 링·분류 폴리곤 링(외곽·구멍)·대상지 링을 **제약 면**으로, TIN 점을 내부 정점으로 CDT 한 번 → 삼각형마다 품은 링 목록(`orig_faces`)으로 분류(외곽 안 + 같은 파트 구멍 밖, 우선순위 앞이 이김) → 정점 Z = TIN `BVHTree.ray_cast`(빗나가면 최근접 정점). 쿼드 격자가 아니라 TIN 점 + 경계 정점 삼각형이다. 성수 R=500 TIN 0.04 s·분류 CDT 0.06 s.
- 건물: 발자국 정점 수직 투영 최저 Z, 뚜껑은 `tessellate_polygon`(구멍 포함). 동마다 객체 대신 **메시 하나 + 면 속성** `building_id`·`height`·`floors`(수천 객체는 Blender가 느리다).
- 커브: 레이어마다 커브 객체 하나(POLY 스플라인 여럿). 합필 전 필지(Site::lots)만 필지마다. 2D 도면(BM::)·구조물 표고점은 없다.
- 베이커: 레이어 = 컬렉션 `CTX::…`(CTX 아래 한 단), 색 = 레이어 이름 재질. 원점은 장면 사용자 속성, 실제 좌표 방식은 객체 위치로 옮긴다(메시는 단정밀도라 로컬). 사본은 임시 장면에 CTX를 걸어 `bpy.data.libraries.write` → `context.blend`(새 장면 view layer를 update하지 않으면 5.2.2가 죽는다).
- 성수 fixture R=500 전체(시트 25장 포함) 3.8 s, 건물 3,454동·지형 면 27,594(job 없음 — `tests/test_blender.py`).
- 패널: `panel_server.Bridge(threaded=False)` — 스레드 없이 메인 스레드가 소켓을 돌린다(타이머 `pump` + 생성 진행 콜백의 `_pump` → `poll`, Rhino의 `RhinoApp.Wait` 자리). 확장 심사가 Blender 안 스레드를 막는다(2026-10-21). 이벤트 줄 소켓은 브리지가 들고 `push`가 바로 쓴다. 새 탭이 열리면 앞 탭에 `superseded`.
- 패키지(`dev_deploy.py blender`): `loader.py`·`usage_stats.py`는 Blender 판으로 바꿔 넣는다(패키지 상대 import만·다시 읽기 없음 / 통계 없이 설치 ID만), `if __package__:` 진입 분기는 앞쪽만 남긴다. 위성 영상(Esri)·업데이트 모달은 `HOST_LABELS["blender"]`의 `aerial`·`update_notice`로 끈다. 사용 통계 없음(`GA_STREAMS`에 blender 없음).

### 5.y SketchUp판 (`cmd_sketchup`·`mesh_geometry`·`sketchup_baker`·`sketchup_ext.rb`, 2026-10-18)

SketchUp에는 파이썬이 없다(Ruby만, sqlite3 gem도 없음). 확장(.rbz)에 **python-build-standalone 3.12 + numpy·shapely**를 플랫폼마다(mac-arm64·mac-x64·win-x64) 넣고, Ruby가 그 파이썬으로 **사이드카**를 띄운다.

```
SketchUp(Ruby, sketchup_ext.rb = bsh_gorani/main.rb)            사이드카(번들 파이썬, cmd_sketchup.py)
  [Gorani] → IO.popen(python -I -B -X utf8 cmd_sketchup.py) ──► panel_server.Bridge 첫 줄로 127.0.0.1 주소
  UI::HtmlDialog.set_url(주소) ◄──── 패널 HTML·SSE·POST cmd ────► _SketchUpController(cmd_site 상속) → context_builder.run(doc = _Host)
  sketchup.host_call(json) ◄── SSE host_call{id, method, args} ─── sketchup_baker(blender_baker와 같은 함수 이름) → _Host.call
  rpc_<method> → 모델 변경 → execute_script("send({cmd:'host_reply'…})") ──► 서버 스레드가 바로 응답 큐로(DIRECT_CMDS)
```

- 지형: `mesh_geometry`의 shapely판 — 범위·분류·대상지 링 테두리를 0.1 mm 격자로 이어(교점 포함) `polygonize` → 면마다 품은 링(대표점 within) → 떨어진 점의 GEOS 들로네 TIN과 겹쳐 조각 → `constrained_delaunay_triangles`. 출력 모양은 mathutils `_get_cdt`와 같아 분류·수면·평탄화·계단 코드를 그대로 쓴다. 성수 R=500 분류별 넓이가 Blender판과 소수 첫째 자리까지 같다(면 39,287 — CDT 한 번보다 1.4배). 지반 높이는 5 m 격자 칸 삼각형 무게중심 좌표. Shewchuk `triangle`은 상업 사용 제한 약관이라 쓰지 않는다.
- 건물: 면 채우기가 없어 동마다 각기둥(`BakeItem.prisms` = 파트 링·바닥 Z·높이·Rhino판과 같은 14키 속성) → Ruby가 `Entities#build`(EntitiesBuilder, 2022+)로 구멍 있는 바닥·지붕·옆면 = 동마다 솔리드 그룹.
- 모델 모양: 대상지마다 최상위 그룹 `Gorani <대상지명>`(속성 사전 `Gorani`의 `GORANI_LOT_KEY`) 안에 태그 `CTX::…`(태그 폴더 CTX)마다 그룹, 색 = 태그 색 + 같은 이름 재질. 지형은 `PolygonMesh` → `fill_from_mesh`(자동 부드럽게), 커브는 `add_edges`. 원점은 모델 속성, 실제 좌표 방식은 대상지 그룹을 옮긴다. 한 번의 생성 = Undo 한 번(clear가 작업을 열고 뒤 호출은 투명 작업).
- 사본: 대상지 그룹 정의 `save_copy` → `context.skp`(로컬 좌표, 원점 = context.json `origin`). 다시 넣기는 `definitions.load` + 원점 차이만큼 옮긴 인스턴스.
- 사이드카는 `-B`(확장 폴더에 `__pycache__`를 쓰면 서명 파일 목록이 바뀐다), stdout 첫 줄만 주소·그 뒤는 stderr = `~/Gorani/sketchup_sidecar.log`, stdin 한 줄은 Ruby 알림(패널 닫힘 `panel_closed` → Rhino 창 닫기처럼 생성 취소, 기다리던 host_call은 바로 실패), stdin EOF(SketchUp 종료)에 끝난다. 응답 없는 host_call은 `SKETCHUP_HOST_TIMEOUT` 뒤 실패.
- 배포: `dev_deploy.py sketchup` → `build/bsh_gorani-<버전>.rbz`(약 90 MB — 런타임 셋, numpy OpenBLAS가 절반). 올리기는 `docs/sketchup_store.md`.

---

## 6. 원점·단위·좌표 규칙 (CLAUDE.md 개정 반영)

| 항목 | 규칙 |
|---|---|
| 원점 | **문서 원점은 문서 속성이다.** `request["doc_origin"]`(= `doc.Strings["GORANI_ORIGIN_E/N"]`, `run`이 읽어 넣는다)이 있으면 그 원점을 재사용(`origin_reused=true`, 경고 1줄) — 같은 문서에 대상지 A·B를 차례로 생성해도 좌표계가 하나다. 없을 때만 대상지(합필이면 합집합 bbox) 중심을 `ORIGIN_SNAP=100` m 단위로 내림. 재사용 원점과 새 대상지 중심 거리 > `ORIGIN_MAX_OFFSET`(20 km)이면 `ValueError("다른 지역 문서입니다 — 새 문서에서 생성하세요")`. **결정은 `context_builder.prepare`, 적용은 `context_geometry.get_local_pts(coords, origin)` 한 함수.** 모든 GeoJSON→Point3d 변환이 이 함수를 거친다 |
| 실제 좌표(`placement=world`, 2026-10-10) | 계산 원점은 그대로(대상지 중심 100 m 내림 — 형상은 로컬에서 만든다), 문서 원점 = (0,0). `context_baker.bake`가 (계산 원점 − 문서 원점)만큼 `Transform.Translation`(단위 Scale 앞)으로 옮긴다. 메시는 옮기기 전에 `Vertices.UseDoublePrecisionVertices = True` — 단정밀도는 55만 m에서 6 cm 단위(헤드리스 문서 실측 `driver_target_modes`). 문서 원점 (0,0) = 실제 좌표 문서 — 방식이 다르면 `placement_mismatch` |
| 왜 베이커가 아닌가 | 메시는 생성 전에 로컬 좌표여야 한다. RhinoCommon에 `MeshVertexList.UseDoublePrecisionVertices`가 있지만 `CreateFromTessellation` 출력의 정밀도는 미확인이고, 표시 메시·스냅은 어차피 원점 근처가 안전(07 §6.2). 베이커는 **문서 단위 환산과 원점 기록**만 |
| 단위 | 로직 m. `context_baker`가 `RhinoMath.UnitScale(Meters, doc.ModelUnitSystem)`을 베이크 직전 복제본에 `Transform.Scale`. 3dm 사본은 문서 단위 그대로 + `context.json.model_unit`. m 단위 사본은 P2(`RhinoCommon.FileIO.File3dm` 직접 쓰기 또는 `RhinoDoc.CreateHeadless(m)`) |
| 기록 세 곳 | ① `CTX::Ref` 원점 Point + TextDot UserString(§7 Ref 표) ② `doc.Strings.SetString("GORANI_ORIGIN_E"/"GORANI_ORIGIN_N"/"GORANI_CRS")` + `doc.EarthAnchorPoint`(위경도 `non_rhino_utils.get_wgs84_from_tm`, `ModelNorth=(0,1,0)`) — **원점이 재사용이면 덮어쓰지 않는다**(`GORANI_LOT_KEY`는 객체 UserString에만, 문서 수준 키 아님) ③ `context.json`. 복원식: 세계좌표 = 로컬 + ORIGIN. `import_3dm`은 파일 `context.json.origin` ≠ 문서 원점이면 차이만큼 `Transform.Translation`으로 보정(차이 > `ORIGIN_MAX_OFFSET`이면 거부) |
| Z·정북 | Z는 절대 표고 그대로. +Y = 격자북(수렴각 서울 0.03~0.13° 무시) |
| SVG·CSV·json | 전부 세계좌표 m. `sheet_svg.Frame`이 세계좌표 → 종이 mm(`(E − E0)/S × 1000`, E0 = 프레임 중심). 원점을 모른다 — `build_terrain`의 시트용 삼각형도 세계좌표로 되돌려 받는다 |

---

## 7. 레이어·UserString·의존성 표

### 7.1 `CTX::` 레이어 (`constants.CTX_LAYERS`, 색은 deliverables A.1 제안값)

| 레이어 | 타입 | 색 | UserString 키 | 우선 |
|---|---|---|---|---|
| `CTX::Site` | PolylineCurve | 220,40,40 | `PNU`(합필이면 쉼표로)·`LOTS`·`AREA_M2`, `GORANI_LOT_KEY` | P0 — 여러 필지면 합필 외곽 |
| `CTX::Site::lots` | PolylineCurve | 235,140,140 | `PNU` | 합필 전 필지(여러 필지일 때만, 레이어 꺼짐) |
| `CTX::Parcels` | PolylineCurve(구멍 보존) | 185,185,180 | `PNU`·`JIMOK`·`ZONE` | P0 |
| `CTX::Buildings` | Mesh(동당 1개) | 128,128,128 | `BLD_ID`·`PNU`·`PNU_SRC`·`GRND_FLR`·`FLR_SRC`·`UGRND_FLR`·`HEIGHT_M`·`HEIGHT_SRC`·`HEIGHT_GRADE`·`USABILITY`·`USEAPR_DAY`·`BLD_NM`·`STATUS`·`DEMOL_DAY`(14키) | P0 |
| `CTX::Buildings::demolished` | Extrusion 외곽선(점선) | 160,160,160 | 위와 같음 | **P1** — `status`는 v1 전부 'active'(건축HUB 벌크가 있어야 채워짐). 레이어는 데이터가 있을 때만 생성, `counts.demolished`는 v1 항상 0 |
| `CTX::Terrain` / `::struct_pts` | Mesh / Point | 236,232,222 | `SRC`·`RESAMPLE_M`·`N_POINTS`·`N_STRUCT_EXCLUDED` | P0 |
| `CTX::Site::ground` | Mesh | 236,150,120 | `KIND`(natural·flattened)·`LEVEL_M` | 대상지 바닥(옵션) |
| `CTX::Terrain::site_flat` / `::site_wall` / `::site_original`(꺼짐) | Mesh | 214,196,170 / 150,140,128 / 236,232,222 | `LEVEL_M`·`LEVEL_SRC`(site_edge_mean 등)·`KIND`(flattened·edge_wall·natural) | 평탄화 옵션일 때만(2026-10-10) |
| `CTX::Water` | Mesh(평면) | 46,125,224 | `NAME`·`LEVEL_M`·`LEVEL_SRC` | P0 |
| `CTX::Roads` / `::centerline` | Mesh / PolylineCurve | 168,168,162 | 메시 `SRC`; 중심선 `WIDTH_M`·`LANES`·`NAME` | P0 |
| `CTX::Green` | Mesh | 228,235,226 | `KIND` | P0 |
| `CTX::Rail` | Mesh(지상) / Curve(지하) | 110,110,110 | `KIND`·`SRC` | P1 |
| `CTX::Bridges` | Extrusion(슬래브 1.5 m) | 150,150,150 | `KIND`·`DECK_Z_SRC` | P1 |
| `CTX::Zoning::<구분>::<종류>` | PolylineCurve(기본 on) | 현황도 11~13 범례 색 | `THEME`·`KIND`·`NAME`·`NOTICE_NO` | P1 |
| `CTX::QA::cadastre_mismatch` | Curve(잠금·비표시) | 255,0,255 | `REASON`·`DIST_M` | P1 |
| `CTX::Ref` | Point·TextDot·Curve | 0,0,0 | `CRS=EPSG:5186`·`ORIGIN_E`·`ORIGIN_N`·`RADIUS_M`·`SHAPE`·`SRC_SHEETS`·`BUILT_AT`·`TOOL_VERSION`·`ALIGN_MEDIAN_M`·`ALIGN_P90_M`·`ALIGN_N`·`ALIGN_DX_DY`·`TOPO_YEAR`·`TRANSFORM`·`VDATUM`·`DATE_LOT`·`DATE_BUILDING`·`DATE_TERRAIN`·`DATE_UPIS`·`META_LINES`(get_meta_lines 5줄 `\n` 결합)·`GORANI_LOT_KEY` | P0 |

모든 베이크 객체에 `GORANI_MANAGED=1`·`GORANI_LOT_KEY=<pnus 정렬 후 sha1 앞 8자리>` — `clear_previous`는 같은 키의 객체만 지운다(사용자 객체 보존).

### 7.2 베이스맵 레이어 (`constants.BM_LAYERS`, deliverables B.2 순서·K톤) — `.ai`와 3dm `BM::` 2D 레이어

`00_frame_scale`·`01_water`·`02_green`·`02b_landuse`(off)·`03_road_surface`·`04_road_edge`·`05_road_center`(off)·`06_rail`·`07_bldg_low/mid/high/tower`·`08_parcel`·`08b_parcel_no`(1:1000만)·`09_contour`·`10_site`·`10b_site_lots`(합필 전 필지 외곽·지번 — 레이어 꺼짐, `BM_HIDDEN_LAYERS`)·`11_zoning`(off)·`12_labels`·`13_grid`. 3dm에도 같은 도면이 2D로 들어간다(2026-10-12): `context_geometry.build_basemap_2d`가 `basemap_ai.build_ai`를 `ShapeRecorder`로 받아 `BM::07_bldg_low 건물 1~4층` 같은 레이어에 Z=0 커브·텍스트(칠 없음, 레이어 색 = K톤 회색)로 만든다. 요청 축척 중 가장 상세한 한 장만, 범위는 그 프레임. `BM` 루트는 꺼진 채 만들어지고(자식은 PersistentVisibility 켜짐 — 루트만 켜면 전부 보인다), `save_copy`가 저장 뒤 파일 레이어 상태를 문서 상태로 되돌린다. 비용(성수 R=500, 1:3000): BM 객체 22,079 · write_3dm 1.6 → 5.2 s · context.3dm 18 → 38 MB. 옵션 `make_dwg`(기본 off, 패널 고급 > 3dm)이면 같은 BM 객체만 `save_copy`로 `basemap_<축척>.dwg`(레이어 `BM$…`, 켜진 채) — +1.1 s · 5.7 MB, 경로는 `done.context.dwg`. 레이어 이름은 `.ai`에 "`07_bldg_low` 건물 저층"처럼 이름 + 한글 설명(CP949)으로 들어간다. 꺼진 레이어(`BASEMAP_DEFAULT_OFF_LAYERS`)는 `basemap_layers_on` 옵션으로 켠다. 계곡선은 `BM_CONTOUR_INDEX_K`(K55).

**basemap은 실제 phase다**: `run`의 phase `basemap`이 축척마다 `basemap_ai.write_basemap`을 부른다. `get_skipped_phases`는 `make_basemap=False`일 때만 `basemap`을 skipped에 넣는다. 패널의 다른 축척 [.ai 내보내기]는 `context_builder.export_basemap(result_dir, scale)` — `context.json`의 pnus·options로 DB에서 다시 `prepare`해 쓴다(문서 import 불필요, 1초 안팎).

### 7.3 `.ai` 형식 메모 (Illustrator 2026 실측 2026-10-08)

- 헤더 `%%BoundingBox: 0 0 W H` + `%AI5_ArtSize: W H`(용지 pt) — 아트보드 = 용지 ✓.
- 레이어 블록 `%AI5_BeginLayer` … `(이름) Ln` … `%AI5_EndLayer--`. 파일 뒤쪽 레이어가 Illustrator 레이어 패널 위.
- 텍스트는 레거시 `To`/`Tx`라 Illustrator가 열 때 '레거시 텍스트 업데이트'를 묻는다. 업데이트하지 않아도 한글은 보인다.
- 글꼴이 없는 PC(예: mac 글꼴 이름으로 쓴 파일을 Windows에서 열기)는 대체 글꼴로 바뀐다 — `AI_FONT_CMAP`이 실행 OS에 맞춰 고른다.

### 7.4 의존성 표

| 구분 | 패키지·API | 버전 | 설치 | 확인 근거 |
|---|---|---|---|---|
| **Rhino 런타임** | Rhino 8 CPython | 3.9.10 (universal2) | Rhino 내장 | `~/.rhinocode/py39-rh8/python3.9` [로컬] |
| | `sqlite3` | SQLite 3.35.5 | 표준 | 같은 인터프리터. **rtree 없음(Windows)** → bbox B-tree만 |
| | `json`·`csv`·`math`·`statistics`·`re`·`hashlib`·`subprocess`(폴더 열기)·`urllib`(P1) | 표준 | — | import OK [로컬] |
| | RhinoCommon | 8.35.26251 | Rhino | `Mesh.CreateFromTessellation`·`CreateFromFilteredFaceList`·`Intersection.ProjectPointsToMeshesEx`(out indices)·`Extrusion.Create(Curve, Plane, double, bool)`·`Hatch.Create`·`RhinoDoc.Strings.SetString`·`EarthAnchorPoint`·`RhinoApp.Wait`·`MeshVertexList.UseDoublePrecisionVertices`·`FileWriteOptions.WriteSelectedObjectsOnly` 전부 RhinoCommon.xml에 존재 [로컬], 속도는 §5 실측 |
| | pip 패키지 | **0개** | `# r:` 없음 | 첫 실행 설치 0 s, 오프라인 OK |
| **개발 Mac(dev_*.py)** | `/usr/bin/python3` | 3.9.6 | OS | `.pyc` 3.9 magic이 Rhino 3.9.10과 같음|
| | geopandas / pyogrio / shapely / pyproj / pandas / numpy / scipy | 1.0.1 / 0.11.1 / 2.0.7 / 3.6.1 / 2.3.3 / 2.0.2 / 1.13.1 | 설치됨 | `import` 확인 [로컬 2026-10-07]. scipy는 `dev_probe_*`·향후 정합 샘플에만 |
| **테스트 전용** | rhino3dm | 8.35.0 | `/usr/bin/python3`에 설치됨(배포 불포함) | `File3dm.Read`로 드라이버 결과 3dm 되읽기(00 §1 읽기 안정) |
| **보험(설계 아님)** | `# r: scipy` 1줄 → `scipy.spatial.Delaunay` | cp39 휠: win_amd64 1.13.1 46.2 MB · macosx_12_0_arm64 | Rhino가 자동 설치(인터넷) | Rhino site-env에 numpy·scipy·shapely·rhino3dm이 오늘 `# r:` 테스트로 이미 깔려 있음(`default-g3PW77Aa`, 20:33) — M2 벤치 드라이버에 분기만 둔다. 오프라인이면 `pip download --platform win_amd64 --python-version 3.9 --only-binary=:all:` 휠을 `wheels/`에 두고 Rhino python의 pip(26.0.1 내장)로 `--no-index --find-links wheels/` — **확인 필요**, 배포 폴더에 넣지 않음 |

---

## 8. 테스트 지도

| 층 | 명령 | 대상 | 데이터 |
|---|---|---|---|
| 순수 로직 | `python3 -m unittest discover tests` | `test_context_builder.py`(있음: 높이 규칙 9케이스·도엽 경계·context_db 질의) → fixture 경로로 전환, `prepare()` 응답 스키마·원점 100 m 내림·`doc_origin` 재사용(+20 km 초과 ValueError)·범위 3종·`bounds[0] < bounds[2]`·`bounds[1] < bounds[3]`·중심 333-139 ±10 m·**R=1000 `near_lots` > 5000**(limit=None 확인)·콜백 순서·취소(2번째 False → 폴더 비움·`cancelled`), `get_progress_message` percent / `test_non_rhino_utils.py`(PIP 구멍·GridIndex·리샘플·방향) / `test_sheet_svg.py`(A1 1:1000 = 841×594 mm ↔ 0.841×0.594 km, `xml.etree` 파싱, `<g id>` 수, 메타 5줄 포함) / `test_context_report.py`(CSV 헤더·BOM, context.json 키) / `test_3dm_readback.py`(드라이버가 남긴 `result/rhino_jobs/<최근>/out/context.3dm`을 `rhino3dm.File3dm.Read` — 레이어 FullPath 12·건물 수 = counts·UserString 14키·`doc.Strings` 원점; 파일 없으면 skip) | **`tests/fixtures/seongsu_context.db` + `seongsu_site.db`**(커밋, 합 ≈10 MB) — `python3 scripts/dev_make_fixture.py --extent 203700,548000,205800,550100`(전체 DB 2개 ATTACH → SQL 추출; 실측 그 extent 안 features 7,148행·buildings 10,440행·페이로드 4.4 MB). 요청 dict `site_db`·`context_db`에 둘 다 꽂아 `prepare`가 어느 PC에서나 돈다 — `data/seoul_site.db` 없어 skipTest 하는 층이 없다 |
| Rhino 지오메트리 | `python3 scripts/dev_rhino_run.py tests/rhino/driver_*.py` | `driver_terrain.py`(TIN·분류 격자 시간·수면 Z·`IsValid`·Z 범위·압출 방향 단언 — `/tmp/udt_bench/driver_bench.py` 이식) · `driver_buildings.py`(투영·압출 수·실패 목록·**`ProjectPointsToMeshesEx` 단언: `len(indices) == len(out)` 그리고 폴백①②로 처리된 동 수 로그**) · `driver_full_run.py`(`context_builder.run` 전체 → response JSON·파일 존재·크기·`context.3dm`을 OUT_DIR로 복사) · `driver_real_site.py`(전체 서울 DB로 성수 333-139 생성 → 저장소 `result/`). `.ai`는 python3 `tests/test_basemap_ai.py` | `constants.TEST_CONTEXT_PNU = "1120011500103330139"` + fixture DB 2개(심링크) |
| Windows | 같은 드라이버 2개를 사용자 노트북 Rhino에서 1회 | `CreateFromTessellation`·`_-Export` 토큰·sqlite rtree 부재·한국어 UI 해치 패턴 | M2.5 |
| 사람 1회 | Illustrator | 레이어 분리·100 mm 검산 사각형(`00_frame`)·한글 라벨·K-only | M5 |

---

## 9. 다른 문서와의 차이 — 개정 목록

| 문서 | 현재 문구 | 개정 | 담당 |
|---|---|---|---|
| `CLAUDE.md` 아키텍처 원칙 | "원점 처리는 베이커 한 곳" | "원점 결정은 `context_builder`, 적용은 `context_geometry.get_local_pts` 한 함수, 베이커는 단위 환산·기록" + "컨텍스트 생성은 Rhino CPython 안 동기 실행(서브프로세스·`# r:` 없음)" | **이 워크플로(반영 완료)** |
| `docs/deliverables.md` | 요약·A.1·A.2·A.3·A.5·B.3: "Rhino 밖 rhino3dm writer → `_-Import`", "scipy Delaunay", "shapely 클리핑", "`File3dm.Strings` 쓰지 않는다" | "RhinoCommon 베이크 + `WriteFile` 사본", "`Mesh.CreateFromTessellation`", "클리핑 없음(bbox + TIN 면 제거)", "`doc.Strings.SetString` 사용". A.3 정합 오차는 "빌드 때 샘플 → 런타임 통계" | 다음 문서 정비 |
| `docs/data_sources.md` §2.2 | `buildings`에 `sheet` 없음, `features` theme 목록에 `qa` 없음 | `sheet TEXT`(ngii 행만, 도엽 교체용) 추가, theme `qa`/kind `align_sample` 추가, §2.3 빌더 책임에 정합 샘플 | 다음 문서 정비 |
| `docs/panel_ui.md`·`ui_spec.md` §11.3 | 생성 = Rhino 밖 python3 서브프로세스(`dev_generate_context.py`·`GENERATOR_PYTHON`·`UITimer` stdout·`proc.terminate`), `init_state.generator`, `site_baker.py`, phase `import` | 생성 = `context_builder.run` in-process(UI 스레드, 콜백 안 `RhinoApp.Wait`), `cancel` = 플래그 → 콜백 False, `generator` 키 삭제(블로커는 필지 DB·컨텍스트 DB 유무만), `site_baker`→`context_baker`, `site_preflight`→`context_builder.preflight`, phase `import` 삭제(`write_3dm` = 베이크+사본) 또는 항상 `skipped`, `import_context` 명령은 유지(`context_baker.import_3dm`). **추가(검토 반영)**: `generate` 페이로드에 `scales` 포함 / `site_preflight`의 RhinoCommon `PolylineCurve.Offset(Round)` 범위 계산과 '둥근 사각형 폴백' 삭제 → `context_builder.preflight`가 `non_rhino_utils.get_extent_ring`으로 만든 링을 `extent_geojson`으로 준다(미리보기 = 실제 생성 범위) / `preflight_result.estimate`에 1:5000 '수십 초' 경고 / `demolished` 옵션은 P1 표기 | **패널 워크플로에 전달** |

---

## 10. 파이프라인 밖

| 파일 | 역할 |
|---|---|
| `constants.py` | 모든 상수(레이어·색·반경·층고 모델·수치지형도 코드·export 문자열·phase) |
| `non_rhino_utils.py` | Rhino 없는 좌표·GeoJSON·TM↔WGS84·PIP·격자·리샘플 |
| `loader.py` | 진입 스크립트가 로직 모듈을 불러오는 공통 로더 |
| `cmd_install.py` | 새 PC 설치 — 앨리어스·툴바(한 번만) |
| `dev_*.py` | Rhino 밖 개발 전용(DB 구축·실측·배포판 빌드·Rhino 드라이버 실행) |
| `docs/arch_proposals/` | 세 설계서 원문(심사 기록). 결정은 이 문서가 원본 |

---

## 검토 반영 (2026-10-07)

| # | 지적 | 반영 위치 |
|---|---|---|
| 1 | `ProjectPointsToMeshes`는 입력과 1:1이 아니다(527점 소실·다중 적중 중복) → 인덱스로 동에 되돌리면 `base_z`가 다른 건물에 붙는다. TIN이 '범위+20 m'라 큰 단지는 투영 자체가 안 되는 동이 있는데 폴백이 없었다 | §5.5 `ProjectPointsToMeshesEx(… out indices)` + 폴백 ①②, §5.1 TIN 범위 = 범위 ∪ 건물 bbox 합집합, §4.5 중단 조건, §8 `driver_buildings` 단언 |
| 2 | 데이터량은 반경이 아니라 베이스맵 프레임이 정하는데 전체가 500 m 기준(실측 ±520 m 3,539동, 1:5000 프레임 4만 동). CTX가 프레임까지 쓰는지 규칙 없음, 요청에 `scales` 없음 | §3 규칙 3줄, §4.2 `scales`, §5.8 예산 재작성(≈8 s, 1:5000 수십 초), §4.3 counts, §9 패널 전달 |
| 3 | `load_parcels_in_bounds(limit=5000)`은 뷰포트용 LIMIT+1 — 1 km 8,918건이 5,000에서 조용히 잘림 | §2 lot_db `limit=None` 분기 1줄, §3 `lots_truncated` 경고, §8 'R=1000 near_lots > 5000' 단언 |
| 4 | 원점 규칙이 '문서 하나에 대상지 하나' 가정 — 두 번째 대상지에서 좌표계 둘이 섞임 | §6 문서 원점 재사용(`request.doc_origin`, `ORIGIN_MAX_OFFSET` 20 km), `import_3dm` Translation 보정, §4.2 `doc_origin`, §4.5 `origin_mismatch` |
| 5 | 전체 DB가 이미 있다(139도엽·995,026동·보충 43 %·372 s·1,509 MB). zlib BLOB은 실측 1.8~2.2배라 가치 없음, 배포 3.6 GB | §0.2 #12 삭제, §1·§3 수치, §7.4 `zlib` 제거. 임계값은 '배포 USB 한도' 같은 실제 제약이 생길 때만 |
| 6 | fixture를 빌더 `--extent`로 SHP 재독 → 전체 DB에서 SQL 추출이면 끝(≈10 MB). `seoul_site.db` 없으면 python3 테스트 절반이 skip | §0.2 #10, §2 `dev_make_fixture.py`(context+site 두 파일), §8 |
| 7 | 범위 폴리곤(`buffer`)이 prepare(순수 python, 정의 없음)와 `site_preflight`(RhinoCommon Offset) 두 곳. 프레임 수학도 `sheet_svg`·`context_geometry` 두 곳 | §5.0 `get_extent_ring` 하나(볼록껍질 오프셋), `sheet_svg.Frame`을 `context_geometry`가 import, §9 패널 전달(Offset 경로 삭제) |
| 8 | bbox 튜플 순서가 코드베이스에 네 가지(`get_bounds_from_geojson` (min_x, max_x, min_y, max_y) / `context_db.load`·`lot_db` (min_x, min_y, max_x, max_y) / `get_topo_sheet_bounds` (left, bottom, right, top) 경위도) | §4.1 `Prepared.bounds = (min_x, min_y, max_x, max_y)` 고정, §2 `non_rhino_utils.get_bbox` 신규(새 코드는 이것만, 구 함수는 review_map 호환), §8 테스트 |
| 9 | `sheet_svg` 입력이 로컬(지형 삼각형)·세계(필지·건물) 두 좌표계 | §5 좌표 규칙 1줄(시트·CSV·json은 세계좌표, 로컬은 Rhino 객체만), §6 SVG 행 |
| 10 | `.ai` 옵션은 sticky — 거부된 토큰은 오류 없이 이전 세션 값으로 내보내짐(job 1007-210846-96b5) | §7.3 런타임 검산 10줄(`%%BoundingBox` ±1 %·명령 이력 '잘못된 옵션') → `export_scale` 경고·`ready=false` |
| 11 | 무벽/가건물 필터가 `ngii_kind`만 보면 대장 매칭 벌크 건물까지 빠짐·python에서 거름 / `status`는 전부 'active'라 demolished는 항상 0 | §2 `context_db.load_buildings_in_bounds(include_minor)` SQL 1줄 + `TOPO_MINOR_KINDS`, §4.2·§7.1 demolished P1 |
