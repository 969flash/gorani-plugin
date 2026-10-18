# 구현 계획 (implementation_plan)

`docs/code_map.md`의 확정 아키텍처를 마일스톤으로 쪼갠다. 각 작업은 **파일 단위**, 완료 기준은 **눈으로 확인할 수 있는 결과**, 테스트 방법은 `python3 -m unittest` 또는 `dev_rhino_run.py` 드라이버. 1인 개발 기준 일수는 추정.

- 작성 2026-10-07. 근거 표기는 code_map.md와 같다(**[실측 job]**·**[로컬]**·**확인 필요**).
- 지금 상태: `scripts/dev_context_builder.py`(699행)·`scripts/context_db.py`·`tests/test_context_builder.py`가 **이미 있고, 전체 컨텍스트 DB도 이미 있다** — `data/seoul_context.db` 1,509 MB, 139도엽 전부, 건물 995,026동(벌크 695,348 + ngii 보충 299,678 = 43 %), 빌드 372 s(`result/context_build.log`, 2026-10-07 21:10). 서울 전체 적재는 과제가 아니다. 아래 M1은 그 위에 얹는 나머지만 적는다.
- 각 마일스톤 '완료 기준'에 **사용자가 눈으로 보는 것** 1개를 고정: M2 = Rhino 문서의 지형 메시 + `context.3dm` 파일, M3 = 건물·필지 들어간 3dm, M4 = 패널 버튼, M5 = Illustrator에서 열린 `.ai`, M6 = 브라우저에서 열린 SVG 13장.

---

## 0. 고정 테스트 대상지와 fixture DB

| 항목 | 값 | 근거 |
|---|---|---|
| **`constants.TEST_CONTEXT_PNU`** | `1120011500103330139` — 성동구 성수동2가 333-139, 지목 대, 5,586.0 ㎡, 준공업지역, 중심 ≈ E 204,764 / N 549,052 | `seoul_site.db` 존재 확인 [로컬]. 성수 4도엽(37705072·73·82·83) 범위 E 202,208~206,630 / N 547,279~552,831 안쪽이라 **반경 500 m·1 km 모두 도엽 안** |
| 소형 대상지(빠른 반복) | `1120011500103150001` 315-1, 1,930.7 ㎡, E 205,004 / N 549,388 | inrhino 벤치가 쓴 PNU, 같은 4도엽 안 |
| 합필 대상지(여러 PNU) | `["1120011500103150001", "1120011500103140006"]` 315-1 + 314-6(2,703 ㎡) | 두 필지 인접 여부 **확인 필요**(M1에서 bbox로 확인). 아니면 333-139 인접 필지로 교체 |
| 기존 `TEST_PNU` | `1123010300106760006`(제기동) — 4도엽 북쪽 밖(N 554,130) | 필지 DB 전용으로 그대로 둔다. 컨텍스트 테스트에는 쓰지 않는다 |
| **fixture DB 2개** | `tests/fixtures/seongsu_context.db` + `tests/fixtures/seongsu_site.db` — `python3 scripts/dev_make_fixture.py --extent 203700,548000,205800,550100`(≈30줄: 전체 DB 2개 `ATTACH` → `INSERT INTO … SELECT … WHERE bbox 교차`. context = buildings·features·data_sources·source_files / site = parcels·overlays·parcel_overlays·parcel_land_use·data_sources, 스키마 v5·`user_version 5`·bbox 인덱스 포함) | extent(333-139 중심 ±1.05 km) 안 실측: features 7,148행·buildings 10,440행·페이로드 4.4 MB → **합 ≈10 MB** → **커밋**(gitignore 하지 않음; `data/*.db`만 gitignore). 저장소가 아직 git이 아니므로 `git init` 때 `.gitignore`에 `tests/fixtures/` 제외 규칙을 넣지 않는다. 빌더 `--extent`(SHP 재독) 경로는 만들지 않는다 |
| 테스트 DB 경로 주입 | `request["context_db"]`·`request["site_db"]`에 fixture 2개 — `prepare`·시트·조서 테스트가 `data/seoul_site.db` 없는 PC에서도 돈다(skipTest 없음) | code_map §4.2 |

`tests/test_context_builder.py`의 `UDT_CONTEXT_TEST_DB` 환경변수(`/tmp/udt_ctx_test.db`)는 fixture 경로 기본값으로 바꾼다.

---

## 1. 마일스톤

### M0 — 문서·상수 정합 (0.5일, Rhino 없음) ← 지금

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| 확정 아키텍처 문서 | `docs/code_map.md`·`docs/implementation_plan.md`(이 문서) | 있음 | — |
| CLAUDE.md 원칙 문구 | `CLAUDE.md` '아키텍처 원칙' — 원점 문장·실행 경로 문장 | code_map §9 표와 일치 | — |
| 상수 절 추가 | `scripts/constants.py` — **이미 있음(패널 워크플로, 2026-10-07 21:0x)**: `CTX_LAYERS`·`BM_LAYERS`·`BASEMAP_SCALE_LAYERS`·`PHASES`·`PHASE_WEIGHTS`·`PHASE_LABELS`·`RADIUS_MIN/MAX`·`SHEET_CATALOG`·`PAPER_SIZES_MM`. **추가할 것**: `CONTEXT_RADIUS=500`, `ORIGIN_SNAP=100`, `TEST_CONTEXT_PNU`, `AI_EXPORT_OPTIONS`(code_map §7.3 문자열), `TERRAIN_RESAMPLE=4.0`, `TERRAIN_MARGIN=20.0`, `CLASSIFY_GRID=50.0`, `WATER_LIFT=0.02`, `SLOPE_BREAKS_DEG=(5,10,15,21,27)`, `ELEV_PRESETS`, `FLOOR_BREAKS_DEFAULT=(12, 20)`, `ALIGN_SAMPLE_STEP=10.0`·`ALIGN_MAX_DIST=10.0`·`ALIGN_LOW_SAMPLE=200`, `ORIGIN_MAX_OFFSET=20000.0`, `TOPO_MINOR_KINDS=("무벽건물", "가건물", "공사중")`(실제 코드값은 DB `ngii_kind` DISTINCT로 확인), `EXTENT_ARC_SEGMENTS=12`. `ESTIMATE_SECONDS_PER_BUILDING`·`ESTIMATE_MB_PER_BUILDING`(있음)은 M4 `run` 실측 후 갱신. `GENERATOR_HTTP_TIMEOUT`은 서브프로세스 전제라 P1 `refresh` 때까지 미사용 | 다른 모듈에 매직넘버 없음 | `python3 -c "import constants"` |
| 드라이버 DB 심링크 | `scripts/dev_rhino_run.py:128–130` — `for p in (ROOT_DIR/"data").glob("*.db")` 전부 심링크 | 작업 폴더 `data/`에 DB 2개 | `--status` 후 job 폴더 확인 |
| 패널 워크플로 전달 | code_map §9의 `panel_ui.md`·`ui_spec.md §11.3` 변경 목록 + 검토 반영분(`generate`에 `scales`, `site_preflight`의 RhinoCommon Offset 범위 계산 삭제 → `get_extent_ring`, 1:5000 예상 시간 경고, `demolished` P1) | 전달됨 | — |

### M1 — 데이터 바닥 (2~3일, Rhino 없음) ← 진행 중

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| fixture 추출기 | `scripts/dev_make_fixture.py`(≈30줄, sqlite3만) — `ATTACH` 전체 DB 2개 → 두 fixture에 스키마 그대로 `INSERT … SELECT … WHERE bbox 교차`, `PRAGMA user_version=5`, 인덱스 생성 | `tests/fixtures/seongsu_context.db`·`seongsu_site.db` 합 ≈10 MB, `sqlite3` CLI로 건수 확인(features ≈7,148·buildings ≈10,440) | `python3 scripts/dev_make_fixture.py --extent 203700,548000,205800,550100` |
| 필지 LIMIT 분기 | `scripts/lot_db.load_parcels_in_bounds(…, limit=None)` — `limit is None`이면 `LIMIT` 절 생략, `truncated=False`(기존 뷰포트 5000 경로는 그대로) | R=1000 bbox 필지 8,918건 전부(0.34 s) | `tests/test_context_builder.py` `PrepareTest`: 'R=1000 near_lots > 5000' |
| 건물 필터 SQL | `scripts/context_db.load_buildings_in_bounds(bounds, include_minor=False, …)` — `AND NOT (src_key LIKE 'ngii:%' AND ngii_kind IN (?,?,?))`(`TOPO_MINOR_KINDS`). 대장 매칭 벌크 건물은 ngii_kind와 무관하게 유지 | 성수 500 m: 필터 전후 동 수 차이 로그(보충 중 무벽 143,822·가건물 19,931·공사중 1,415 서울 전체) | fixture로 `include_minor` True/False 건수 비교 1단언 |
| 도엽 경계 건물 중복 집계 | `dev_context_builder._normalize_topo_buildings`(UFID 중복 제거 있음) + 로그에 "경계 분절 의심(UFID 다른데 대표점 같은 셀)" 수 | 4도엽 경계에서 수치 1개 | 빌드 로그 |
| 순수 유틸 6함수 | `scripts/non_rhino_utils.py` — `is_point_in_ring(x, y, ring)`, `is_point_in_polygon(x, y, rings)`(외곽 in AND 구멍 out), `GridIndex(cell)`(`add(bounds, item)`·`query(x, y)`), `get_resampled_ring(ring, step)`, `get_ring_orientation(ring)`(+1 CCW / −1 CW), **`get_bbox(geometry) -> (min_x, min_y, max_x, max_y)`**(기존 `get_bounds_from_geojson`은 (min_x, max_x, min_y, max_y) — docstring에 '구 순서, review_map 호환' 표기, 새 코드 사용 금지), **`get_extent_ring(lots_rings, radius, shape) -> ring`**(buffer = 볼록껍질 단조 체인 + 변 오프셋 + 꼭짓점 호 / circle 64각 / rect) | — | `tests/test_non_rhino_utils.py`: 도넛 도로 필지 구멍 안 점 False, 격자 후보 ⊇ 전수, 4 m 리샘플 점 간격 ≤ 4, 방향 부호, `get_bbox` 순서, `get_extent_ring` — 모든 대상지 정점에서 링까지 거리 ≥ radius−1 mm·링 볼록·자기교차 없음 |
| 테스트 DB 경로 | `tests/test_context_builder.py` — fixture 2개 기본값(`UDT_CONTEXT_TEST_DB` 환경변수 제거) | `python3 -m unittest discover tests` 전부 통과(**심링크 없이**) | — |

완료 기준(M1 전체): `python3 -m unittest` 통과 + fixture DB 2개 존재 + 터미널에 "333-139 반경 500 m 건물 ≈3,500동(ngii 보충 포함, minor 제외), 높이 출처 비율" 출력(`context_db.load` 호출 스크립트 10줄, 테스트 안에 둔다).

### M2 — 첫 3D: 지형 + `run` 최소판 (3~4일, Rhino) — **눈으로 보는 것: Rhino 문서의 지형 메시 + `context.3dm` 파일**

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| `prepare` 최소 | `scripts/context_builder.py` — `prepare(request, progress)`: 입력 검증(`scales` 포함), `lot_db.load`, 원점(`request["doc_origin"]` 재사용 → 없으면 100 m 내림, 20 km 초과 ValueError), `get_extent_ring`, `bounds = 범위 ∪ 최대 프레임`(`(min_x, min_y, max_x, max_y)`), `load_parcels_in_bounds(limit=None)`, `context_db.load`, `Prepared` | fixture로 `prepare` 0.5 s 안쪽 | `tests/test_context_builder.py` `PrepareTest`(원점 100 m 내림 / `doc_origin` 주입 시 재사용·`origin_reused` / 20 km 초과 ValueError / 범위 3종 / `bounds[0] < bounds[2]`·`bounds[1] < bounds[3]`·중심 333-139 ±10 m / R=1000 `near_lots` > 5000 / `truncated`면 `lots_truncated` 경고 / 콜백 `query` 0→1 / `site_db`·`context_db` 주입) |
| 지형 생성 | `scripts/context_geometry.py` — `get_local_pts`, `build_terrain(prepared) -> {class: Mesh}` + 시트용 삼각형 리스트(**세계좌표**로 되돌려 반환): TIN 입력 범위 = 범위 bbox ∪ 건물 bbox 합집합(+20 m), 리샘플·spot 필터·범위 링 정점·수면 조밀화 → `CreateFromTessellation` → `GridIndex` 분류(`outside` = 범위 링 밖) → 수면 Z 고정 → `CreateFromFilteredFaceList` → 경사 등급 배열 | 성수 500 m: 면 ≈ 7~8천, `IsValid`, Z 10~35 | `tests/rhino/driver_terrain.py`(`/tmp/udt_bench/driver_bench.py` 이식): 시간·면 수·Z 범위 단언, **1 km 분류 ≤ 1 s** 기록. 넘기면 `# r: scipy` 분기(`scipy.spatial.Delaunay` + 동일 분류)로 비교만 — 배포 경로 아님 |
| 베이커 최소 | `scripts/context_baker.py` — `_ensure_layer`·`_get_model_unit_scale`·`clear_previous`, `bake(doc, items, prepared) -> [Guid]`(`RedrawEnabled` try/finally, UserString, `UDT_MANAGED`·`UDT_LOT_KEY`), `doc.Strings` 원점 3키(재사용이면 덮지 않음)·`_save_document`(WriteSelectedObjectsOnly) → `context.3dm` | Rhino 문서에 `CTX::Terrain/Water/Roads/Green` 메시가 레이어별로 뜨고 `context.3dm`이 생긴다 | 같은 드라이버에서 베이크 후 `doc.Objects.FindByLayer` 수 단언 |
| **`run` 최소판** | `context_builder.run(request, progress, doc)` — `doc.Strings` → `request["doc_origin"]` → `prepare` → `build_terrain` → `bake` → `WriteFile` → `context.json`(`context_report.write_context_json` 최소) → response dict. progress 콜백은 단계 시작·끝 2회만, `basemap`·`sheets`·`tables`·`refresh`·`import`는 `skipped`. 취소·되돌리기·`get_progress_message`는 M4 | `tests/rhino/driver_full_run.py`가 **M2 끝에 돈다**: response JSON + `context.3dm`을 OUT_DIR로 복사 | `tests/test_3dm_readback.py`(`rhino3dm.File3dm.Read` — 레이어 FullPath·`Strings` 원점; 파일 없으면 skip) |
| 압출 방향 확정 | `driver_terrain.py` 끝에 샘플 발자국 10동 `Extrusion.Create(crv, Plane(base_z), h, True)` → `GetBoundingBox(True).Max.Z ≈ base_z + h` 단언 | 통과하면 production 코드에 검사 없음 | 드라이버 |
| 정밀도 | 메시 `Vertices.UseDoublePrecisionVertices = True` 설정 후 정점 Z가 입력과 1 mm 안 일치 | 단언 통과 | 드라이버 |

### M2.5 — Windows 노트북 1회 검증 (0.5일 + 사용자 시간) ← 배포 위험을 먼저 태운다

| 작업 | 완료 기준 |
|---|---|
| 사용자 Windows 노트북 Rhino 8에서 `tests/rhino/driver_terrain.py`·`/tmp/udt_bench/driver_export4.py`(→ `tests/rhino/driver_export_ai.py`) 수동 실행(ScriptEditor `_Run`; `dev_rhino_run.py`는 Mac 전용이라 폴더 복사 후 직접). **DB는 전체 복사가 아니라 `tests/fixtures/` 2개(≈10 MB)만** — 드라이버가 `site_db`·`context_db`를 fixture로 지정 | `CreateFromTessellation` 결과 동일, `_-Export` 영문 토큰 수용·bbox 284 pt, 한국어 UI 해치 `FillType` 조회 OK, `sqlite3` rtree 부재 확인(설계상 미사용), Rhino python 3.9.x·sqlite 버전 기록 |
| 결과를 이 문서 §4에 적는다 | 실패 항목이 있으면 M3 전에 대안 결정 |

### M3 — 건물·3dm 완성 (3~4일, Rhino + python3) — **눈으로 보는 것: 건물·필지가 들어간 `context.3dm`**

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| 건물 | `context_geometry.build_buildings` — `Intersection.ProjectPointsToMeshesEx(…, out indices)` 1회 → `indices`로 동 복원 → 동별 최저 `base_z`(투영점 0인 동: ① 최근접 TIN 정점 Z ② 건너뜀+`skipped` 경고)·`~slope` → CW/CCW 무관 평면 오버로드 압출 → 구멍 `AddInnerProfile` → 멀티폴리곤 파트별 → 실패 건너뜀·id 기록. `demolished` 레이어는 **M3 범위 밖**(P1, status 전부 active) | 성수 500 m 건물 **≈3,500동**(ngii 보충 포함, minor 제외), 실패 ≤ 3, 폴백 ② 0동 | `tests/rhino/driver_buildings.py`: 수·실패 목록·Z 범위·**`len(indices) == len(out)` 단언**·폴백 ①② 동 수 |
| 커브 | `context_geometry.build_curves` — Site·Parcels(구멍 보존, 범위 bbox 안만)·Ref 범위(`extent_ring`)·도엽 경계·(옵션) Zoning | 레이어 11개 채워짐(demolished 제외) | `driver_full_run.py`(M2부터 있음) |
| 기록 | `context_baker.bake` 확장 — Ref Point+TextDot UserString 전부, `EarthAnchorPoint`(원점 재사용이면 유지), `import_3dm`(원점 차이 `Transform.Translation` 보정) | 3dm 사본에 Ref·UserString 14키, 같은 문서에 두 번째 대상지를 넣어도 원점이 하나 | 드라이버: 333-139 → 315-1 연속 생성 후 `doc.Strings` 원점 불변 단언 |
| 메타·CSV 뼈대 | `scripts/context_report.py` — `get_meta_lines(prepared)` 5줄, `write_context_json`, `append_log`, `write_tables`(parcels·buildings 2개 먼저) | SVG·CSV·json·Ref가 같은 문자열 | `tests/test_context_report.py`(fixture) |
| 정합 샘플(P0) | `dev_context_builder.py` — 단계 추가: 지목 도로 필지(`seoul_site.db` ATTACH) ∪ `road/surface` 경계 10 m 샘플 → 최근접거리·dx·dy(`dev_probe_alignment.sample_along`·`nearest_dist` 재사용) → `features(theme='qa', kind='align_sample', value=d, attrs_json={dx,dy}, sheet)` / `context_builder.prepare` — 범위 안 샘플 `statistics.median`·`quantiles(n=10)[8]`·n·`low_sample(n<200)` | 성수 4도엽 중앙값 ≈ 1.2 m·p90 ≈ 3.9 m(08정합 실측과 일치) | `tests/test_context_builder.py` `AlignTest` |
| 되읽기 | `tests/test_3dm_readback.py` — `rhino3dm.File3dm.Read(최근 job의 context.3dm)` → 레이어 FullPath 집합·`CTX::Buildings` 수 = counts·UserString 14키·`Strings` 원점 | 통과(파일 없으면 skip) | python3 |
| 정리 | `prepare` 완성(통계·경고 코드 `height_estimate`·`multipart`·`coverage`·`stale_*`·`skipped`·`lots_truncated`·`origin_reused`)·`preflight`(COUNT 질의, `extent_geojson` = `get_extent_ring`, `estimate`에 1:5000 '수십 초' 경고) | response JSON 스키마가 code_map §4.3과 같음 | `tests/test_context_builder.py` `ResponseSchemaTest`(response 키 집합)·`PreflightTest` |

### M4 — 패널 연결 (2~3일, Rhino) — **눈으로 보는 것: 패널 버튼 → 진행률 → 문서에 컨텍스트**

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| **첫 항목: Wait 펌프 확인** | 10줄 드라이버: `host.push` 20회 사이 `RhinoApp.Wait()` + `time.sleep(0.2)` — WebView 진행 막대가 움직이는가, `cancel` 명령이 콜백 사이에 들어오는가(Mac WKWebView) | 움직이면 동기 유지. 안 움직이면 `prepare`를 `threading.Thread`로, push는 `AsyncInvoke`, 베이크부터 UI 스레드 | 수동 |
| 오케스트레이션 마무리 | `context_builder.run`(M2 최소판 위에) — 긴 루프 안 콜백·`Cancelled` → 베이크 되돌리기·`get_progress_message`·`elapsed_s`. **`run` 실측으로 `ESTIMATE_SECONDS_PER_BUILDING`·`ESTIMATE_MB_PER_BUILDING` 갱신** | 취소 버튼 → 문서 원복, `ok=false, cancelled=true` | `tests/test_context_builder.py` `CancelTest`(2번째 콜백 False), `ProgressMessageTest`(percent·phase_status) |
| 컨트롤러 | `scripts/cmd_site.py`(패널 워크플로와 합류) — `generate{pnus, options, scales}`→`run`, `cancel` 플래그, `preflight`→`context_builder.preflight`, `import_context`→`context_baker.import_3dm`, `export_basemap`→`context_builder.export_basemap`(2026-10-08: DB에서 `basemap_ai`로 다시 씀), `zoom_view` | 패널 버튼 → 진행률 → 문서에 컨텍스트 → 결과 카드 | 수동(Mac) |
| 설치 | `cmd_install.py` — 컨텍스트 DB 존재 확인 1줄 | 설치 메시지에 DB 2개 | Rhino에서 1회 |

### M5 — 베이스맵 .ai (2~3일, Rhino + Illustrator 1회) — **눈으로 보는 것: Illustrator에서 열린 `basemap_3000.ai`**

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| BM 2D 항목 (**2026-10-08 대체: `scripts/basemap_ai.py`가 .ai를 직접 쓴다 — 아래 두 행은 당시 계획**) | `context_geometry.build_basemap(prepared, scale)` — 프레임 bbox 안 객체(`Prepared.frame_bounds[scale]`)만, 해치(FillType Solid)·커브·PlotWeight·`00_frame` 사각형(**`sheet_svg.Frame`에서 받음**, 자체 계산 금지)·`10_site` = `extent_ring`·`13_grid` | BM 레이어 14개(기본 off·잠금), 1:3000 프레임 2.52×1.78 km | `driver_export_ai.py` |
| 내보내기 | `context_baker.bake_basemap`·`export_ai(doc, dir, scale)` — Top 전환·`RhinoObject.Select(True)`·`AI_EXPORT_OPTIONS`·축척별 레이어 on/off(`BASEMAP_SCALE_LAYERS`)·`_NC` 제외·K-only 후처리·뷰·레이어 상태 복원 + **런타임 검산 10줄**(`%%BoundingBox` pt→mm vs 용지 mm ±1 %, `RunScript` 반환·`CommandHistoryWindowText` '잘못된 옵션' → `warnings[code=export_scale]`·`ready=false`·이력 5줄 log) | `basemap_3000.ai` 생성, `%%BoundingBox` = 용지 mm, 정상 파일에서 `export_scale` 경고 없음 | 드라이버 단언(bbox·`(BM::…) Ln` 수·`g` 연산자 수·경고 0) + 일부러 틀린 토큰 1회 → 경고 1 |
| Illustrator 판정 | 사용자 1회 열기 | 레이어 분리·100 mm 치수·한글 라벨 손상 여부 → 라벨 경로 확정(깨지면 `12_labels`·`08b`는 `.ai`에서 빼고 `labels.svg`) | 사람 |

### M6 — 현황도 SVG 13장·조서 CSV (5~6일, Rhino 없음 — M4·M5 대기 중 병행) — **눈으로 보는 것: 브라우저에서 열린 SVG 13장**

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| 프레임·작성기 | `scripts/sheet_svg.py` — `Frame(paper_mm, scale, center)`·`to_paper(x, y)`·`world_bounds()`(프레임 수학의 **유일한** 자리 — `context_geometry.build_basemap`·`prepare`의 `frame_bounds`도 이것) ·`<clipPath>`·`<g id>`·범례·카드 3함수·여백 5줄(`get_meta_lines`). **origin을 모른다 — 입력은 전부 세계좌표 m** | A1 1:3000 viewBox 841×594 ↔ 2.523×1.782 km. M2 `prepare`가 `frame_bounds`에 쓰므로 `Frame`은 M2에서 먼저 만든다(20줄) | `tests/test_sheet_svg.py`: 프레임 수학, `xml.etree` 파싱, `<g id>` 수 |
| 시트 선언 표 | `sheet_svg.SHEETS = [(id, name, classify_fn, legend), …]` 13장 — 분류표는 `constants` | `sheets/01~13_*.svg` 생성, 빈 시트는 `empty:true, reason` | fixture로 13장 생성 테스트 |
| 표고·경사 | `context_geometry.build_terrain`이 넘긴 `(삼각형 **세계좌표**, Z 밴드, 경사 등급)` 리스트를 `sheet_svg`가 채색(Rhino 안 값이 순수 모듈로 가는 유일한 입력 — 로컬→세계 되돌림은 `build_terrain` 안에서, 리스트라 python3 테스트는 합성 데이터) | #12·#13 — 시트 #12·#13만 원점 오프셋을 다시 더하는 예외 없음 | 합성 삼각형 테스트 |
| 조서 | `context_report.write_tables` — `parcels.csv`·`buildings.csv`·`sheet_stats.csv`·`height_src_stats.csv`·`alignment.csv`(utf-8-sig) | 5개 파일, 엑셀에서 한글 OK | `tests/test_context_report.py` 헤더 |

### M7 — 배포 (2일, Mac + Windows 노트북) — 서울 전체 적재는 **이미 끝났다**(§4)

| 작업 | 파일 | 완료 기준 | 테스트 |
|---|---|---|---|
| 서울 전역 확인 | 전체 DB로 임의 서울 PNU 3곳(강남·구도심·산지) | 각 `run` 성공, 소요 기록 | `driver_full_run` ×3 |
| 등고선 없는 도엽 | `prepare` 경고 `coverage`(`SRC_SHEETS`에 없는 도엽·범위 안 등고선 0) | 37709006 대상지에서 경고 뜸(37608050·37608073은 적재됨 — 누락 시나리오 무효) | python3 |
| 배포 빌더 | `scripts/dev_deploy.py` — DB 2개·`strip_spatial_index`·`.pyc` optimize=2·`설치방법.txt`·`Gorani.rui` | 배포 폴더 **≈3.6 GB**(2.1 + 1.5). 줄여야 할 실제 제약(USB 한도 등)이 생길 때만 등고선 `set_precision` 등 검토 — zlib BLOB은 하지 않는다(실측 1.8~2.2배, §4) | Mac 다른 폴더에 복사 → `cmd_install.py` → 실행 |
| Windows 설치 | 사용자 노트북: 폴더 복사 → `cmd_install.py` → `Gorani` → 333-139 생성 | 20 s 안쪽, `.ai`·SVG·CSV 생성, 인터넷 끊고도 동작 | 수동 |

### M8 — P1 (이후, 데이터·요청 있을 때)

`refresh` phase(VWorld `LT_C_BLDGINFO` 세션 캐시 — `decide_height`를 `building_height.py`로 옮겨 빌더·런타임 공유) · `CTX::QA::cadastre_mismatch`(정합 샘플 3~10 m 구간 + 건물 overflow) · 교량 슬래브·철도 지상/지하 · 주변 필지 드레이프(`ProjectPointsToMeshes` 1줄, `parcel_z` 옵션) · `CTX::Zoning` · `dev_check_updates.py` · m 단위 3dm 사본(`RhinoCommon.FileIO.File3dm`) · 1 km 성능 재측정.

---

## 2. 구현 순서와 병행

```
M0 ─► M1(python3) ─► M2(Rhino) ─► M2.5(Windows) ─► M3 ─► M4 ─► M5 ─► M7
                 └──────────────── M6(python3, Rhino 대기 중 병행) ───┘
```

- Rhino 드라이버 1회는 수십 초(던지기 + 폴링 3 s) — 지오메트리 모듈은 **python3로 테스트할 수 있는 부분(prepare·분류 함수·리샘플·메타·SVG·CSV)을 먼저 완성**하고 Rhino 드라이버는 메시·압출·베이크·export 네 가지만 본다.
- M3의 정합 샘플 빌더 작업은 python3라 M2 Rhino 대기 중에 할 수 있다.
- M6은 M3의 `Prepared`·`get_meta_lines`만 있으면 시작 가능.
- 첫 end-to-end(`driver_full_run.py` → `context.3dm`)는 **M2 끝**에 나온다. M3·M4는 그 위에 건물·취소·패널을 얹는다.
- 합계 **M0~M7 ≈ 4~5주**(1인). 가장 긴 M6(13장)은 시트 1장 템플릿이 서면 나머지는 분류표 추가라 뒤로 갈수록 빨라진다.

---

## 3. 위험·대안

| 위험 | 징후·근거 | 대안(비용) | 언제 |
|---|---|---|---|
| `RhinoApp.Wait()`가 Mac WKWebView(Eto) 이벤트를 펌핑하지 않음 → 진행률·취소 먹통 | 기존 컨트롤러에 Wait 선례 없음(grep), panel_host는 `AsyncInvoke`로 flush. 세 안 모두 미실측 | `prepare`만 스레드(Rhino 금지 모듈이라 안전) + push `AsyncInvoke`, 베이크부터 UI 스레드(반나절) | M4 첫 항목 |
| 1 km 면 분류가 격자로도 1 s를 넘김 | bbox 전수 16.86 s 실측, 격자 '<1 s'는 추정 | ① `Curve.Contains`에 같은 격자 ② 벤치 드라이버의 `# r: scipy` 분기로 `Delaunay`+STRtree 비교(배포 경로 아님) ③ 그래도면 분류만 빌드 때 사전 계산(hybrid 방식 축소) | M2 |
| Windows Rhino에서 `CreateFromTessellation`·`_-Export` 토큰·한국어 UI 해치 동작이 Mac과 다름 | Mac만 실측 | M2.5에서 1회 확인(30분). 토큰이 다르면 `AI_EXPORT_OPTIONS`를 OS별 dict로 | M2.5 |
| `.ai` 한글 라이브 텍스트 손상 | 파일에 UTF-8 바이트 `(…) Tx`·폰트 ArialMT [1007-203940-f62b], 06 포럼 보고 | 라벨을 `labels.svg`로 분리(반나절) 또는 `TextEntity.Explode()` 아웃라인 | M5 |
| 평삼각형·범위 경계 톱니(제약변 없음) | 07 §1.3, 08정합 §2.4 | 표고점 포함으로 1차 해결(08). 단차가 문제면 `Mesh.CreatePatch` 브레이크라인 시험(1~2일) | M2 후 사용자 피드백 |
| `Extrusion.Create` None(자기교차 발자국) | 8,517동 중 2 실측 | 건너뛰고 경고. 늘면 `Brep.CreatePlanarBreps` 폴백 | M3 |
| 도엽 경계 건물 중복(ngii 보충분) | `_normalize_topo_buildings` UFID 중복 제거만 있음, 분절 UFID 미확인 | M1 집계 → 필요하면 대표점-도엽 bbox 규칙 10줄 | M1 |
| 1:5000 프레임(4만 동·필지 10만)에서 `run`이 수십 초 | 실측 ±1,020 m 10,126동 → 외삽 | `preflight.estimate` 경고로 사용자가 알고 누른다. 길면 BM 해치를 `07_bldg_*`만 먼저 → 나머지 레이어 후순위 | M5 |
| 큰 단지 발자국이 TIN 밖 → 투영 0 | 벤치 527점 소실 | TIN 범위 = 범위 ∪ 건물 bbox 합집합이 1차 방어, 폴백 ①② | M3 |
| `.ai` 옵션 토큰 거부가 조용히 이전 세션 값으로 내보내짐 | job 1007-210846-96b5 7종 전부 '잘못된 옵션'인데 성공 저장 | `export_ai` 런타임 bbox 검산 → `export_scale` 경고 | M5 |
| 같은 문서에 두 대상지 → 좌표계 둘 | 원점 규칙이 문서 하나·대상지 하나 가정이었음 | `doc.Strings` 원점 재사용 + 20 km 초과 거부 | M2 |
| RhinoCommon Delaunay가 특정 입력(중복·공선)에서 None | 실측 범위 밖 | (x,y) 중복 제거는 함. None이면 1 mm 지터 재시도 → 그래도면 `# r: scipy` 1줄 보험(휠 확인됨, Rhino site-env에 이미 설치) | 발생 시 |
| 사내 망 차단 PC에서 보험 경로(`# r:`)가 안 됨 | onepath 약점 | 설계상 보험을 쓸 일이 없는 것이 1차 방어. 쓰게 되면 `pip download --platform win_amd64 --python-version 3.9 --only-binary=:all:` 휠을 `wheels/`에 두고 Rhino python pip `--no-index --find-links wheels/`(**확인 필요**, 배포 폴더엔 넣지 않음) | 발생 시 |
| `RedrawEnabled=False` 중 예외로 화면 멈춤 | — | `try/finally` 복원(베이커 공통) | M2 |
| Rhino 문서 단위 None/Custom | — | `ValueError("mm·cm·m 같은 표준 단위…")` → `doc_unit_invalid` | M2 |
| 폴리곤 불린이 결국 필요(QA mismatch 합집합) | P1 | `Curve.CreateBooleanUnion` 실측 → 느리면 "다른 도로 필지 안 샘플 제외" 근사 → 그래도면 빌드 때 사전 계산(정합 샘플처럼 `features qa`) | M8 |
| `panel_ui.md`가 서브프로세스 전제로 남아 세 층이 어긋남 | 현재 문서 상태 | code_map §9 목록을 패널 워크플로에 전달, M4 전 개정 | M0 |

---

## 4. 실측 기록 (채워 넣는 자리)

| 항목 | 값 | 날짜·job |
|---|---|---|
| **139도엽 전체 빌드: 372 s / 1,509 MB / 건물 995,026동(벌크 695,348 + ngii 보충 299,678 = 43 %) / 보충 중 무벽건물 143,822·가건물 19,931·공사중 1,415 / 높이 출처 topo_flr 387,344·height 295,965·grnd_flr 231,417·default 65,093** | 2026-10-07 21:10 `result/context_build.log` |
| dbstat: geometry_json 634 MB + attrs 93 MB, 테이블 본체 1,267 MB, 인덱스 242 MB; zlib 샘플 축소 features 2.17배·buildings 1.78배(→ zlib 해도 ≈1.2 GB, 채택 안 함) | 2026-10-07 [로컬] |
| 성수 333-139 전체 DB: bbox ±520 m 건물 3,539동 / ±1,020 m 10,126동 / 1 km bbox 필지 8,918건(전부 읽기 0.34 s) | 2026-10-07 [로컬] |
| fixture extent 203700,548000,205800,550100: features 7,148행·buildings 10,440행·페이로드 4.4 MB | 2026-10-07 [로컬] |
| **정합 샘플 포함 재빌드: 375 s / 1,942 MB / qa 1,339,783점(125도엽) / 서울 전체 정합 중앙값 1.15 m·p90 3.78 m, 성수 4도엽 1.17 / 3.84 (n=64,799)** | 2026-10-07 23:28 |
| `ProjectPointsToMeshes` 14,768 입력 → 14,241 출력(527 소실) — 1:1 아님 | [1007-203742-8486] |
| fixture 2개 생성: 소요 / MB | context 15.4 MB(건물 10,414·features 21,200 incl. qa 13,243) · site 29.8 MB(필지 9,186), 수 초 | 2026-10-07 23:30 [로컬] |
| 도엽 경계 건물 분절 의심 수 | | M1 |
| 1 km 면 분류(격자) 시간 | R=1000: TIN 42,642점, 분류 3.73 s(조밀화 간격 반경 비례 후) / R=500: 분류 1.04~1.23 s | 2026-10-07 [E1 드라이버] |
| 압출 방향(평면 오버로드) Max.Z − base_z ≈ height | 샘플 10동 오차 < 1 mm, Min.Z = base_z | 2026-10-07 [driver_terrain] |
| Windows: Rhino python 버전 / sqlite / `CreateFromTessellation` / export bbox / 해치 FillType | | M2.5 |
| 성수 333-139 500 m + A1 1:3000 `run` 전체 소요 / 1:5000 → `ESTIMATE_*` 갱신 | BM 포함 51.2 s(query 1.8 · terrain 4.7 · write_3dm 25.5 · basemap 8.8 · sheets 10.7 · tables 0.3), context.3dm 73 MB, 베이크 59,409객체, basemap_3000.ai 7.6 MB; BM 없이 20 s/13.6 MB. ESTIMATE 1/70 s·1/47 MB per 동. 1:5000 미측정 | 2026-10-07 [job 1007-235316-709b] |
| Illustrator: 레이어 분리 / 100 mm 검산 / 한글 | | M5 |
| 배포 폴더 크기(추정 3.6 GB) / Windows 첫 실행 소요 | | M7 |

기존 실측(재인용): TIN 4,121점 0.01 s·30,276점 0.03 s / 분류 0.69 s(500 m)·16.86 s(1 km, 전수) / 투영 14,768점 0.06 s / 압출 2,174동 0.19 s / 베이크 0.08 s / 해치 0.23 s [1007-203742-8486]; `.ai` bbox 284 pt [1007-204228-0084]; `FindName("Solid")` −1 → FillType [1007-204134-f8d9]; Rhino python 3.9.10·sqlite 3.35.5 [로컬].

---

## 검토 반영 (2026-10-07)

| # | 지적 | 반영 |
|---|---|---|
| 1 | 전체 DB가 이미 있는데(139도엽·995,026동·43 % 보충·372 s·1,509 MB) M7에 '적재 30분'·M1에 '4도엽 빌드 수치' 과제가 남아 있었다. zlib BLOB 규칙은 실측 1.8~2.2배라 가치 없음(≈1.2 GB), 배포 3.6 GB | 머리말·§4 수치 기입, M7 빌드 과제·'누락 2도엽' 시나리오 삭제, zlib 행 삭제(위험표·M7), 배포 3.6 GB |
| 2 | fixture를 빌더 `--extent`(SHP 재독)로 — 전체 DB에서 SQL 추출이면 끝(≈10 MB). `seoul_site.db` 없으면 테스트 절반이 skip | §0·M1 `dev_make_fixture.py`(context+site 2개), M2.5도 fixture 2개로 |
| 3 | M3 완료 기준이 M4 산출물(`run`)에 의존 — 첫 end-to-end가 2주 뒤 | M2에 `run` 최소판, M4는 취소·`get_progress_message`·컨트롤러만. 마일스톤마다 '눈으로 보는 것' 1개 |
| 4 | 건물 수 ≈1,8xx(500 m 반경 가정) → 실측 ±520 m 3,539동 | M1·M3 ≈3,500동, M4에서 `ESTIMATE_*` 갱신 |
| 5 | `ProjectPointsToMeshes` 1:1 아님·TIN 밖 발자국 폴백 없음 | M3 `ProjectPointsToMeshesEx` + 폴백 ①② + `len(indices) == len(out)` 단언, 위험표 |
| 6 | `load_parcels_in_bounds(limit=5000)` 조용한 절단 | M1 `limit=None` 분기, `PrepareTest` 'R=1000 near_lots > 5000' |
| 7 | 문서 하나에 대상지 둘이면 좌표계 둘 | M2 `prepare` `doc_origin` 재사용, M3 연속 생성 드라이버 단언, 위험표 |
| 8 | 범위 폴리곤·프레임 수학이 두 곳 | M1 `get_extent_ring`, M2·M5·M6 `sheet_svg.Frame` 단일 정의(M2에서 먼저 20줄) |
| 9 | bbox 튜플 순서 네 가지 | M1 `get_bbox`, M2 `PrepareTest` bounds 순서 단언 |
| 10 | `sheet_svg` 입력 좌표계 혼재 | M2·M6 `build_terrain` 삼각형 세계좌표 반환 |
| 11 | `.ai` sticky 옵션 조용한 실패 | M5 `export_ai` 런타임 검산 + 일부러 틀린 토큰 테스트, 위험표 |
| 12 | 건물 필터가 ngii_kind만 보면 벌크 매칭 건물까지 제외·demolished는 항상 0 | M0 `TOPO_MINOR_KINDS`, M1 `load_buildings_in_bounds(include_minor)` SQL 1줄, M3에서 demolished 제외(P1) |
