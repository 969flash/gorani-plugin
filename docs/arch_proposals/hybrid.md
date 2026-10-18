# 엔진 아키텍처 제안 — 혼합(무거운 계산은 사전 처리) 안

- 작성일 2026-10-07. 경쟁 안과 함께 심사받는 설계서. 근거 표기: `[00 §1]`처럼 `docs/research/` 번호, `[실측]` = 이 설계서를 쓰며 이 Mac에서 직접 돌린 값(명령은 §13), **확인 필요** = 아직 못 확인한 사실.
- 한 줄 요약: **지형 TIN·면 분류·건물 높이 규칙·건물 바닥 표고·정합 오차를 전부 개발 Mac의 `dev_context_builder.py`에서 미리 계산해 `data/seoul_context.db`에 넣고, Rhino 쪽은 SQLite bbox 질의 → 원점 이동 → RhinoCommon 조립(메시·압출·커브·해치·텍스트)만 한다.** 런타임 pip 의존성 0, `# r:` 지시자 없음, 서브프로세스 없음.

---

## 1. 요약과 핵심 선택

### 1.1 런타임 배치 — Rhino CPython 안에서 전부, 의존성 0

| 선택지 | 판정 | 이유 |
|---|---|---|
| **Rhino 8 CPython 안에서 전부(표준 라이브러리 + RhinoCommon)** | **채택** | 배포 PC에 python이 없다. 무거운 계산을 DB 구축 단계로 옮기면 런타임에 남는 것은 `sqlite3`·`zlib`·`array`·`json`·`csv`·`struct`와 RhinoCommon뿐이라 `# r:` 패키지가 하나도 필요 없다. 첫 실행 설치 시간 0, 인터넷 불필요, Windows wheel 호환 걱정 없음 |
| 외부 python 서브프로세스 | 기각 | 배포 PC에 python이 없고, 설치해 주는 순간 "폴더 복사로 끝" 원칙(기존 선례)이 깨진다 |
| Rhino CPython + `# r: numpy, scipy, shapely` | 폴백 | cp39 wheel은 전부 있음(§2) — 하지만 scipy 46 MB·numpy 16 MB 설치가 첫 실행에 수 분, 사내 망 차단 시 실패. 사전 처리로 필요 자체를 없애는 쪽이 싸다 |

### 1.2 deliverables.md와 다른 점 (의도된 이탈 — 심사 포인트)

| 항목 | deliverables | 이 안 | 이유 |
|---|---|---|---|
| 3dm 생성 | Rhino 밖 rhino3dm writer → 패널에서 `_-Import` [A.5] | **RhinoCommon 베이크 → `doc.WriteFile` 사본** (§5) | 런타임에 shapely·scipy가 없으니 "Rhino 밖 생성"의 이점(헤드리스 계산)이 사라진다. 데이터가 이미 삼각형·압출 파라미터로 와 있어 조립만 하면 되고, 베이크 패턴은 기존 베이커에 이미 있다. rhino3dm은 **개발·테스트 전용**(python3가 결과 3dm을 다시 읽어 검증)으로 남긴다 |
| 정합 오차 | 매 실행 shapely로 재계산 [A.3] | 빌드 때 10 m 간격 샘플점 + 최근접거리를 타일 blob으로 저장, 런타임은 반경 안 샘플만 골라 중앙값·p90 (`statistics` 모듈) | 결과는 같고(같은 샘플·같은 거리) 런타임 shapely가 필요 없다 |
| 범위 클리핑 | 메시 생성 전 shapely 클리핑 [A.2] | 250 m 타일 단위 + 면 중심점 거리 필터(원형일 때) | 톱니 가장자리(≤4 m)를 허용. `ponytail:` 깔끔한 경계가 필요하면 빌드 때 100 m 격자선을 TIN 제약점으로 넣는 쪽으로 |
| 지형 TIN 단위 | 대상지마다 생성 | **서울 전체를 한 번에 Delaunay** → 250 m 타일로 잘라 저장 | 도엽 경계 이음새 문제가 없다. 대가: 도엽 하나만 바뀌어도 지형 단계는 전체 재빌드(§7, 약 5분) |
| 주변 필지 Z | (미정) | v1은 Z=0 (2D 레이어와 같은 평면) | 런타임 보간이 없다. `ponytail:` 순수 python 삼각형 탐색(§5.6)으로 드레이프 가능, P1 |

### 1.3 배포 시나리오

```
개발 Mac: python3 scripts/dev_context_builder.py       → data/seoul_context.db (≈1 GB)
          python3 scripts/dev_deploy.py <USB>           → UrbanDesignTool/ (scripts .pyc + data 2 DB + rui)
사용자 PC: 폴더 복사 → Rhino에서 cmd_install.py 1회 → 명령 `Gorani`
          패널 → 필지 선택 → [생성] → 10~20초 뒤 현재 문서에 CTX::/BM:: 레이어, result/에 3dm·ai·svg·csv
```

---

## 2. 의존성 전략

### 2.1 런타임(Rhino CPython 3.9.10)에 넣을 패키지 — **없음**

| 패키지 | 런타임 필요? | 대신 쓰는 것 |
|---|---|---|
| shapely | **아니오** | 교차·합집합·분류·클리핑은 빌드 때. 런타임 GeoJSON → `Rhino.Geometry.PolylineCurve`는 `non_rhino_utils.get_polygon_parts_from_geojson`(보유) |
| scipy | **아니오** | Delaunay·보간은 빌드 때. 메시는 타일 blob의 정점·면 배열을 `Mesh.Vertices.Add`/`Faces.AddFace`로 조립 |
| numpy | **아니오** | blob 디코딩은 `array('f')`·`array('I')` + `zlib`(표준 라이브러리) |
| rhino3dm | **아니오** | 문서 쓰기는 RhinoCommon `doc.WriteFile`. rhino3dm은 python3 테스트에서 결과 3dm 검증용 |
| pyproj | **아니오** | 입력은 전부 EPSG:5186으로 적재됨. 패널 지도용 WGS84 변환은 `non_rhino_utils.get_wgs84_from_tm`(보유, 자체 TM 공식) |
| openpyxl·reportlab(선례) | 아니오 | 조서는 CSV, 시트는 SVG — 둘 다 표준 라이브러리 |

Rhino CPython 실측 [실측]: `~/.rhinocode/py39-rh8/python3.9` = 3.9.10 universal2(arm64 네이티브), `sqlite3.sqlite_version` 3.35.5, `zlib`·`array`·`struct`·`statistics` 사용 가능. site-envs에는 openpyxl·reportlab·pyshp·Pillow만 깔려 있음(선례의 `# r:` 흔적).

### 2.2 폴백용 wheel 존재 근거 (만약 런타임 계산이 필요해질 때)

`pip download --only-binary=:all: --python-version 3.9 --implementation cp` [실측 2026-10-07]:

| 패키지 | win_amd64 cp39 | macOS cp39 | 비고 |
|---|---|---|---|
| numpy 2.0.2 | O (15.9 MB) | O arm64 (13.7 MB) | 2.0.x가 cp39 마지막 계열 |
| scipy 1.13.1 | O (46.2 MB) | O `macosx_12_0_arm64` | `macosx_11_0_arm64` 태그로는 1.8.0rc1만 잡힘 → macOS 12 이상 필요 |
| shapely 2.0.7 | O (1.4 MB) | O arm64 | |
| rhino3dm 8.35.0 | O (2.7 MB) | O `macosx_14_0_universal2`만 | **macOS 13 이하 Mac은 설치 불가 — 확인 필요** |
| pyproj 3.6.1 | O (6.1 MB) | O arm64 | |
| triangle 20250106 | O | 미확인 | CDT 브레이크라인용, 빌드 쪽에서만 검토 |

→ 폴백 경로(`# r: numpy, scipy, shapely`)는 Windows에서 성립하지만 첫 실행 다운로드 ≈ 65 MB. 이 안에서는 쓰지 않는다.

### 2.3 개발 Mac(빌드 전용) 의존성 [실측]

`/usr/bin/python3` 3.9.6: numpy 2.0.2 · scipy 1.13.1 · shapely 2.0.7 · pyproj 3.6.1 · pyogrio 0.11.1 · geopandas 1.0.1 · rhino3dm 8.35.0. fiona·triangle 없음(불필요). 전부 `dev_*.py`에서만 import.

---

## 3. 모듈 지도

파일은 `scripts/` 하나, 접두사로 환경 구분(CLAUDE.md). **재사용** = 이미 있음, **신규** = 이 안에서 만든다. 스텁 선제 생성 금지 — 아래 신규 파일은 마일스톤(§11)에서 필요해질 때 만든다.

| 파일 | 구분 | 환경 | 책임 | import |
|---|---|---|---|---|
| `loader.py` | 재사용 | Rhino | 로직 모듈 로더·리로드 | — |
| `constants.py` | 재사용+추가 | 공통 | `CTX_LAYERS`·`BM_LAYERS`(이름·색·순서), `CONTEXT_RADIUS_DEFAULT=500`, `ORIGIN_SNAP=100`, `TERRAIN_TILE_SIZE=250`, `FLOOR_HEIGHT_MODEL`(A.4), `NGII_LAYER_MAP`(코드→theme/kind), `CONTEXT_STEPS`, `TEST_CONTEXT_PNU` | — |
| `non_rhino_utils.py` | 재사용 | 공통 | GeoJSON 링 분해·bbox·TM↔WGS84 | — |
| `lot_db.py` | 재사용 | 공통 | 필지·오버레이 bbox 질의 (`load`, `load_near_lot_candidates`, `load_near_overlays`) | constants |
| `pnu_loader.py`·`review_map.py` | 재사용 | 공통 | 주소 해석·패널 지도 GeoJSON | lot_db |
| **`context_db.py`** | 신규 | 공통(Rhino 없음) | `seoul_context.db` 조회: `load_buildings_in_bounds`, `load_features_in_bounds(theme, kinds)`, `load_terrain_tiles(bounds)`(blob 디코드 → `{class: (verts, faces, slope_cls)}`), `load_align_samples(bounds)`, `load_sources()` | constants |
| **`building_height.py`** | 신규 | 공통(Rhino 없음) | A.4 높이 규칙 한 벌: `get_building_height(attrs) -> (height, src, grade, floors, flr_src)`. **빌드와 런타임(VWorld 갱신, P1)이 같은 함수를 쓴다** | constants |
| **`context_builder.py`** | 신규 | 공통(Rhino 없음) | 엔진 API `run()`의 Rhino 없는 절반 = `prepare(request, progress, should_cancel) -> Prepared`: 대상 필지 → 범위·원점 → DB 질의 → 통계·경고·메타(`context.json` 내용) 산출 | lot_db, context_db, building_height, non_rhino_utils |
| **`context_geometry.py`** | 신규 | Rhino | `Prepared` → RhinoCommon 지오메트리 목록(`BakeItem(layer_path, geo, user_strings)`): GeoJSON→PolylineCurve, 건물→Extrusion, 타일→Mesh, 2D 베이스맵 커브·해치·텍스트. **문서를 건드리지 않는다** | Rhino.Geometry, constants |
| **`context_baker.py`** | 신규 | Rhino | 문서 변경 전담: 레이어 트리, 속성·UserString, 단위 배율, Undo 묶음, 이전 결과 교체, `CTX::Ref`·EarthAnchorPoint, `WriteFile` 사본, `.ai` 내보내기 명령 | Rhino, context_geometry |
| **`sheet_svg.py`** | 신규 | 공통(Rhino 없음) | 프레임 수학(용지·축척·중심) + SVG 작성기(레이어 `<g>`, clipPath, 범례·카드·여백 문구). 현황도 11장 + 표고·경사 2장 | constants, non_rhino_utils |
| **`context_report.py`** | 신규 | 공통(Rhino 없음) | `tables/*.csv`, `context.json`, `log.txt` | — |
| **`cmd_site.py`** | 신규 | Rhino 진입 | 컨트롤러(옛 기존 컨트롤러 패턴): 명령 라우팅, `busy`/`progress`/`cancel`, 결과 폴더 열기 | loader → panel_host, review_map, pnu_loader, context_builder, context_geometry, context_baker, sheet_svg, context_report |
| `panel_host.py`·`site_ui.html` | 재사용/별도 워크플로 | Rhino | Eto WebView 호스트·프런트 | — |
| `cmd_install.py` | 재사용(+컨텍스트 DB 존재 확인 1줄) | Rhino 진입 | 설치 | loader |
| **`dev_context_builder.py`** | 신규 | 개발 python3 | §7 빌더(단계별) | geopandas·pyogrio·shapely·scipy·numpy, constants, building_height |
| **`dev_deploy.py`** | 신규(이식) | 개발 | 배포 폴더 생성(.pyc·DB 사본) | — |
| `dev_check_updates.py` | 신규(≈10줄) | 개발 | 브이월드 새 판 감지 [data_sources §2.3] | — |
| `dev_database_builder.py`·`dev_rhino_run.py`·`dev_probe_*.py` | 재사용 | 개발 | 필지 DB·Rhino 드라이버 실행·실측 | — |

import 방향: `cmd_site` → (`context_builder` → `context_db`/`lot_db`) → `context_geometry` → `context_baker`. Rhino 없는 모듈(`context_db`·`building_height`·`context_builder`·`sheet_svg`·`context_report`)은 `python3 -m unittest`로 바로 돈다.

---

## 4. 데이터 흐름

```
[원천 zip]                                 [개발 Mac: dev_context_builder.py]                      [data/seoul_context.db]
수치지형도 139도엽 zip ──pyogrio cp949──▶ ① features 단계: 17레이어 → GeoJSON(5186, 0.01 m) ──────▶ features (theme/kind/sheet/bbox)
  + sheets.csv(제작연도)                     등고선·표고점·구조물 폴리곤 보관(data/build/*.npy)
GIS건물통합정보 AL_D010_11 zip ──────────▶ ② buildings 단계: A2 PNU 검증·공간조인(결측만) ────────▶ buildings (+ base_z, ground_dz)
  + 수치지형도 B001 건물                       ngii 대표점 조인 → 층수 보완 → A.4 높이(building_height.py)
                                           ③ terrain 단계: 등고선 4 m 리샘플 + 표고점(구조물 5 m 버퍼 제외)
                                              + 수면 경계 조밀화 → 서울 전체 Delaunay → 긴 변 제거
                                              → 면 중심점 분류(water/road/green/rail/terrain, STRtree)
                                              → hydro-flatten → 면 경사 등급 → 250 m 타일 blob(zlib) ─▶ tiles (theme='terrain_*')
                                              → 건물 발자국 정점 보간 → buildings.base_z 갱신
                                           ④ align 단계: 지목 도로 필지 ∪ 경계 ↔ A001 경계 10 m 샘플 → 거리 ─▶ tiles (theme='align')
                                           ⑤ 메타: data_sources·source_files(sha256) 갱신, data/backup/ 1장

[Rhino 런타임: cmd_site → context_builder.prepare]                       [context_geometry → context_baker]
PNU → lot_db.load → target bbox → radius → bounds, origin(100 m 내림)   Prepared → BakeItem 목록(원점 이동 여기서만)
lot_db: 주변 필지·오버레이 bbox 질의                                     → CTX::* 레이어 베이크(Undo 1묶음, Redraw 1회)
context_db: buildings·features·tiles·align bbox 질의, blob 디코드          → BM::* 2D 레이어 베이크 → _-Export .ai
통계(높이 출처 비율·노후·도로율), 정합 중앙값·p90, 기준일 경고             → doc.WriteFile(context.3dm, 선택 객체만)
                                                                          sheet_svg → sheets/*.svg, context_report → tables/*.csv, context.json, log.txt
```

좌표·단위: DB와 `Prepared`는 EPSG:5186 절대좌표 m. 원점 이동과 문서 단위 배율은 `context_geometry`/`context_baker` 경계 한 곳(CLAUDE.md "베이커 한 곳"). SVG 프레임 수학은 `sheet_svg`가 절대좌표 → 종이 mm로 직접 변환(원점 이동과 무관).

---

## 5. 3dm 생성 설계 — RhinoCommon 베이크로 확정

### 5.1 왜 rhino3dm 쓰기가 아니라 베이크인가

- 런타임에 shapely·scipy가 없으므로 "Rhino 밖에서 다 만들어 Import"의 전제(헤드리스 계산)가 이 안에는 없다. 남는 일은 **조립**이고, 조립은 RhinoCommon이 가장 빠르고 검증된 길이다(기존 베이커에 레이어·속성·Undo·단위 배율·사본 저장이 이미 있음).
- Import 경로의 추가 단계(파일 쓰기 → `_-Import` → 단위 환산 → 레이어 병합)와 rhino3dm Python의 빈 구멍(`File3dm.Strings` 쓰기 불가 [00 §1], 메시 연산 없음 [07 §5.2])을 피한다.
- 결과 파일 `context.3dm`은 베이크 직후 `doc.WriteFile(path, WriteSelectedObjectsOnly=True)`로 이번 결과 객체만 담아 저장(기존 베이커 `_save_document` 재사용). 문서 단위가 mm든 m든 사본에 그대로 들어가고, 사이드카 `context.json`에 단위·원점을 적는다.
- rhino3dm은 `tests/`에서 결과 3dm을 다시 읽어 레이어·UserString·객체 수를 검증하는 데만 쓴다(00 실측대로 읽기는 안정적).

### 5.2 지형 — 타일 blob → Mesh

- 빌드 결과: 250 m 타일 × 분류(`terrain`·`road`·`water`·`green`·`rail`) 행마다 `payload = zlib(header + float32 verts[n_v×3] + uint32 faces[n_f×3] + uint8 slope_cls[n_f])`. 헤더 `struct '<4sHHII'` = (`b"UDT1"`, 포맷 버전, 분류 코드, n_v, n_f).
- 런타임: bbox에 걸리는 타일 행을 읽어 `zlib.decompress` → `array('f')`·`array('I')`·`bytes`로 풀고, 분류별로 하나의 `Rhino.Geometry.Mesh`에 이어 붙인다(정점 오프셋만 더함). `Mesh.Normals.ComputeNormals()`·`Compact()` 1회.
- 원형 범위면 면 중심점이 반경 밖인 면을 뺀다(순수 python, 500 m 반경 ≈ 1만 면이라 수십 ms). 사각형 범위는 타일 그대로.
- 규모 [실측, 성수 4도엽 24.5 km²]: 등고선 4 m 리샘플 + 표고점 122,928점 → 245,798면, **1 km²당 정점 5,008·면 10,015·raw 0.18 MB(zlib 0.07 MB)**. 500 m 타일 기준 정점 중복 6.6 %, 250 m는 약 13 %로 추정.
- `CTX::Terrain::struct_pts`: 제외된 구조물 위 표고점은 `features(kind='spot_struct')`에 그대로 있어 Point로 베이크.

### 5.3 건물 — 사전 계산 파라미터 → Extrusion

- 빌드 때 확정해 `buildings`에 넣는 값: `height_m`·`height_src`·`height_grade`·`grnd_flr`·`flr_src`·`attr_flag`(A.4 전부), **`base_z`**(발자국 정점의 TIN 보간 최저값), **`ground_dz`**(정점 고저차; >3 m면 `height_src`에 `~slope`), 링은 shapely `orient`로 외곽 CCW·구멍 CW 고정, 좌표 0.01 m 반올림.
- 런타임: 외곽 링 → `PolylineCurve`(Z=`base_z`) → `Extrusion.Create(crv, height_m, True)` → 구멍은 `AddInnerProfile`. **압출 방향은 생성 직후 `GetBoundingBox(True).Max.Z`가 `base_z`보다 낮으면 `-height_m`로 다시 만든다** — 07 §2.4("CW 링은 음수 높이가 위")와 deliverables A.1("CW 정규화 후 양수")이 서로 반대라 상수 대신 결과로 판정한다(1줄, 건물당 비용 무시 가능). M2에서 어느 쪽이 맞는지 기록해 상수 `EXTRUSION_SIGN`으로 고정하면 검사를 뺄 수 있다.
- `Extrusion.Create`는 정점 Z가 다르면 None [07 §7-5] → 모든 정점 Z를 `base_z`로 통일한 평면 커브라 통과.
- `STATUS=demolished`는 옵션: 제외(기본) / 회색 점선 외곽선만.
- 규모: 1 km²당 ≈1,700동 [07 §8] → 반경 500 m 1~2천 Extrusion. RhinoCommon 추가는 `RedrawEnabled=False`로 묶어 1~3 s 예상(**확인 필요** — M2 드라이버에서 측정).

### 5.4 도로·수면·녹지·철도 — 분류된 메시가 그대로 레이어

- TIN 면 분류 결과가 분류별 타일 행이므로 런타임은 `CTX::Roads`·`CTX::Water`·`CTX::Green`·`CTX::Rail`에 메시를 넣기만 한다. 수면 Z는 빌드 때 hydro-flatten(경계 최저 Z)이 끝나 있다.
- 분류 우선순위(빌드): water > rail > road > green > terrain. 원천: water = 필지 지목 하천·구거·유지 ∪ `E0010001`·`E0032111`·`E0052114`; road = `A0010000`(폴백 중심선 `도로폭`/2 버퍼); green = 지목 공원·임야 ∪ 도시계획시설 공원·녹지 ∪ `D0010000`; rail = `A0160024` 지상부 [deliverables A.1].
- 도로 속성(`WIDTH_M`·`LANES`)은 메시가 아니라 `CTX::Roads::centerline` 커브(`features kind='centerline'`)의 UserString에 둔다 — 메시 하나에 속성 수백 개를 붙일 수 없어서다.
- 교량(P1)은 features 폴리곤 + 양끝 접속부 표고(빌드 때 `attrs_json.z0/z1`에 저장) → 런타임은 두께 1.5 m 슬래브 Extrusion.

### 5.5 원점·레이어·UserString·메타

- 원점: 대상 필지(들) bbox 중심을 `ORIGIN_SNAP=100` m 단위로 내림 → `(origin_e, origin_n)`. **`context_geometry`에서만 뺀다**. Z는 절대 표고 그대로.
- 문서 단위: 기존 베이커 `_get_model_unit_scale` 이식 — m → 문서 단위 배율을 지오메트리 복제본에 적용.
- 레이어: `constants.CTX_LAYERS` 순서대로 `CTX::Site/Parcels/Buildings/Terrain/Water/Roads/Green/Rail/Bridges/Zoning/QA/Ref`(색은 deliverables A.1). 레이어 생성·캐시는 기존 베이커 `_ensure_layer` 이식.
- 이전 결과 교체: 객체 UserString `UDT_MANAGED=1`·`UDT_LOT_KEY=<PNU들 해시>`로 추적, 같은 대상지의 이전 객체만 지운다(기존 베이커 `_clear_baked` 패턴). Undo 1묶음.
- UserString: deliverables A.1 표 그대로(건물 14개, 필지 `PNU`·`JIMOK`·`ZONE`, 수면 `NAME`·`LEVEL_M`·`LEVEL_SRC` …).
- `CTX::Ref`: 원점 Point + TextDot, 범위 커브, 도엽 경계 커브(`features kind='sheet_frame'`), UserString에 `CRS`·`ORIGIN_E/N`·`RADIUS_M`·`SRC_SHEETS`·`BUILT_AT`·`ALIGN_*`·`TRANSFORM`·`VDATUM`·기준일 문자열. 추가로 RhinoCommon `doc.EarthAnchorPoint`(위경도·`ModelNorth=(0,1,0)`)와 `doc.Strings.SetString("UDT_ORIGIN_E", …)` — RhinoCommon에는 문서 문자열 쓰기가 있으므로 rhino3dm의 한계 [00 §1]가 사라진다. 사이드카 `context.json`도 같이 쓴다.

### 5.6 `ponytail:` 표시해 둔 단순화

- 주변 필지·용도지역 커브 Z=0. 드레이프가 필요하면 `context_geometry`에 "타일 면을 25 m 격자 버킷에 넣고 점마다 무게중심 좌표로 삼각형 찾기" 40줄(순수 python, 1.5만 점 ≈ 0.3 s 예상)을 추가.
- 범위 가장자리 톱니(≤4 m) 허용.
- 무제약 Delaunay(브레이크라인 `F003/F004` 없음) — 옹벽·제방이 뭉개지면 빌드 쪽을 `triangle` CDT로 교체(런타임 무관).

---

## 6. 베이스맵·시트 생성 설계

### 6.1 베이스맵 .ai — Rhino 2D 레이어 + 내장 내보내기 (1차)

- `context_geometry`가 같은 `Prepared`에서 2D 항목을 만든다: 수면·녹지·도로면·건물(층수 4단계) = 닫힌 PolylineCurve + **solid Hatch**(`Hatch.Create(crvs, 0, 0, 1, tol)`, 색은 레이어), 지적선·등고선·철도·대상지 = 커브, 라벨 = `TextEntity`(Pretendard, 지명·도로명·지번(1:1000만)). 레이어는 `BM::00_frame_scale … 13_grid`(deliverables B.2 이름·K 톤을 `constants.BM_LAYERS`에 RGB 회색으로). Z=0.
- 내보내기(`context_baker.export_ai`): `BM::*` 객체만 선택 → Top 뷰 → `Rhino.RhinoApp.RunScript('_-Export "<path>.ai" <옵션> _Enter', False)`. **옵션 문자열은 확인 필요** — 00 §2는 기본값(`_Enter`)으로 레이어 보존만 확인했다. 확인 절차: Rhino에서 `-Export`를 대화식으로 1회 실행해 프롬프트(축척 보존 `1 모델단위 = 1 mm`, 해치 solid, 레이어 순서)의 정확한 키워드를 받아 `constants.AI_EXPORT_OPTIONS`에 고정(M5).
- 축척: 내보내기의 "모델 축척 보존" 옵션으로 1:1000 = `1 m = 1 mm`. 그 옵션이 스크립트로 안 잡히면 **폴백 ①**: BM 지오메트리를 종이 mm 좌표(`(x−cx)·1000/scale`)로 베이크해 축척 옵션 없이 내보낸다(코드 5줄). **폴백 ②**: `_-Export .svg`(00 실측 레이어 `<g>` 보존) → Illustrator JSX [06].
- 한글 라이브 텍스트·4만 해치 성능·캔버스 한계는 06 §5 테스트 3·5를 M5에서 1회 돌린다. 깨지면 라벨만 SVG 경로로.
- 내보내기 후 `BM` 부모 레이어는 끄고(사용자 문서를 어지럽히지 않게) 유지한다 — Make2D 없이 평면도 밑그림으로 재사용 가능.

### 6.2 현황도 SVG 시트 — 순수 python 작성기 (`sheet_svg.py`)

- Seoungsu `make_basemap_L.py`의 구조(레이어 `<g id>`, register rect, K 톤 상수, 라벨 충돌 회피)를 가져오되 geopandas·shapely 호출을 전부 뺀다: 입력은 `Prepared`의 GeoJSON dict, 변환은 `(x−cx)/scale·1000 + 종이중심` 한 줄, **클리핑은 `<clipPath id="frame">`**(Illustrator가 클리핑 마스크로 연다) — 지오메트리 교차 연산 없음.
- 프레임: `(paper, scale, center)` → viewBox mm. A1 1:1000 = 841×594 mm = 0.84×0.59 km. 반경 500 m 전부를 담으려면 1:3000 — 범위 초과는 경고만 [deliverables B.1].
- 주제 레이어는 속성 분류뿐: #2 토지이용(`land_use_status` 재분류표) #3 지목 #4~6 오버레이 theme/kind #7 용도 앞 2자리 #8 `grnd_flr` 구간 #9 `use_apr_day` 연차 #10 중심선 `도로폭` 7등급 #11 `land_price_won` 분위(`statistics.quantiles`) — 전부 `constants`의 표. #12 표고 = 타일 면 중심 Z 구간 채색, #13 경사 = 빌드 때 저장한 `slope_cls`(6단계) 그대로.
- 여백 공통 문구 ①~⑤(자료기준·출처·좌표계·정합 오차·기준일 경고)는 `Prepared.meta`에서 문자열로 조립.
- 범례·수치 카드(높이 출처 비율 90×45 mm 등)는 `<rect>`·`<text>` 조합의 함수 3개.

### 6.3 조서 CSV·context.json·log.txt (`context_report.py`)

`csv.writer`(utf-8-sig, Excel 호환) 5개 파일, `json.dump(meta)`, 건너뛴 피처·폴백 사유 로그. 끝.

---

## 7. DB 빌더 설계 (`dev_context_builder.py`)

### 7.1 테이블 — data_sources.md §2 + 추가 1개·컬럼 2개

- `data_sources`·`source_files`·`buildings`·`features`: §2.2 그대로.
- `buildings`에 **`base_z REAL`, `ground_dz REAL`** 추가(§5.3).
- **`tiles`**(신규): `theme TEXT`(`terrain_terrain`·`terrain_road`·`terrain_water`·`terrain_green`·`terrain_rail`·`align`), `tile_x INT`, `tile_y INT`, `min_x/max_x/min_y/max_y REAL`, `n INT`, `payload BLOB`, `source_id TEXT`, `built_at TEXT`, `PRIMARY KEY(theme, tile_x, tile_y)`, 인덱스 `idx_tiles_bbox`. 타일 원점 `(190000, 540000)`·크기 250 m는 `constants`. `align` payload = float32 `(x, y, d, dx, dy)`×n.
- RTree 없음, GeoJSON 텍스트 유지(필지 DB 관행). `ponytail:` 번들이 커서 문제면 `features.geometry_json`을 zlib blob 컬럼으로 바꾸는 것은 `context_db` 한 함수 수정.

### 7.2 단계와 순서 (`--stage` 인자로 따로 돌릴 수 있게)

| 단계 | 입력 | 처리 | 출력 | 소요(추정, 근거) |
|---|---|---|---|---|
| ① `features` | 139 zip + `sheets.csv` | zip 안 SHP를 pyogrio(cp949)로 읽어 `.prj`·Y 범위로 5186 확인, `NGII_LAYER_MAP`(17레이어)으로 theme/kind, `set_precision(0.01)`, 도엽 단위 `DELETE WHERE source_id=? AND sheet=?` → INSERT. 등고선·표고점·구조물·수면·도로·녹지 폴리곤은 `data/build/<sheet>.pkl`로도 보관(③④ 재사용) | `features` | 17레이어 4도엽 읽기 2.1 s [실측] → 139도엽 **≈3~5분** |
| ② `buildings` | `AL_D010_11_*.zip` + ① 건물 | 전체본 교체(한 트랜잭션). A2 PNU 검증(19자리·parcels 존재), 결측만 대표점 공간조인. ngii 건물 대표점 조인 → 층수 보완(아파트·연립 `층수 ≥ grnd_flr+3`), 매칭 안 된 ngii 건물 `src_key=ngii:*` 추가. `building_height.get_building_height` 적용(규칙 0·0′ 플래그 포함) | `buildings`(base_z 비움) | 129 MB zip 읽기 + 조인 **≈3~5분** (서울 동 수 미확인 [data_sources §4-23]) |
| ③ `terrain` | `data/build/*.pkl` | 등고선 `segmentize(4)` + 표고점(구조물 `A007/A009/A010` 5 m 버퍼 제외, 보조 +10 m 규칙) + 수면 경계 2 m 조밀화 + 서울 외곽 사각형 테두리 점 → `np.unique(round 2)` → **서울 전체 `Delaunay` 1회** → 변 길이 >150 m 면 제거(외곽 슬리버) → 면 중심점 `STRtree.query(predicate='within')`로 분류(우선순위 §5.4) → water 정점 Z = 수면별 경계 최저 → 면 경사 6등급 → 250 m 타일별·분류별 blob → `tiles`. 이어서 `LinearNDInterpolator`로 모든 건물 정점 Z → `buildings.base_z/ground_dz` | `tiles(terrain_*)`, `buildings.base_z` | 4도엽: TIN 0.6 s·분류 2.3 s·건물 29만 정점 보간 1.6 s [실측] → 서울(×25, 점 ≈3백만·면 ≈6백만): **≈3~6분**, Qhull 메모리 피크 **2~4 GB 추정(확인 필요)** |
| ④ `align` | 필지 DB 지목 도로 + ① `A0010000` | `dev_probe_alignment.py`의 `sample_along`·`nearest_dist` 재사용(10 m 샘플, 10 m 초과 = 상대선 없음) → 타일 blob | `tiles(align)` | 4도엽 17,581샘플 [08정합] → 서울 ≈60만 샘플 **≈2~4분** |
| ⑤ `meta` | 위 전부 | `data_sources`(기준일 = `sheets.csv` 제작연도 / A22) · `source_files`(sha256, 같으면 단계 건너뜀) · 적재 전 `data/backup/seoul_context_<날짜>.db` 1장(3판 초과 삭제) | | 1분 |

전체 첫 빌드 **≈15~25분**, 메모리 피크 **6~10 GB 추정(확인 필요 — M1에서 4도엽 RSS 재고 ×35 외삽)**. `data/build/`(중간 pkl·npy ≈ 1 GB)는 gitignore.

### 7.3 저장 용량 (정직한 산정)

| 테이블 | 근거 [실측 성수 1도엽 37705072] | 서울 139도엽 추정 |
|---|---|---|
| `features`(건물 제외 16레이어) | GeoJSON 3.6 MB/도엽(등고선 0.75·도로면 0.73·중심선 0.61 + 속성) | **0.3~0.6 GB**(성수는 밀집 도엽, 산지는 등고선이 늘고 나머지가 준다) |
| `buildings` | ngii 건물 GeoJSON 평균 205 B + 속성 ≈300 B | 60~100만 동 × 0.5 KB = **0.3~0.5 GB** |
| `tiles(terrain_*)` | 0.07 MB/km² zlib + 타일 중복 13 % | 605 km² → **≈50 MB** |
| `tiles(align)` | 20 B/샘플 | ≈60만 → **≈12 MB** |
| 인덱스 | bbox 4열 B-tree | +10 % |
| **합계 `seoul_context.db`** | | **≈0.8~1.2 GB** — 필지 DB 2.1 GB와 합쳐 번들 **≈3.0~3.3 GB** |

### 7.4 중복·교체·갱신

- 도엽 겹침: 도엽 경계에서 잘린 도로면·하천면은 **dissolve하지 않고 그대로**(data_sources §2.2). 지형은 서울 전체 TIN이라 경계 문제 없음. 등고선 중복 정점은 `np.unique`.
- 도엽 교체: `--stage features --sheet 37705072` → 그 도엽 행만 교체(수십 초). **지형·정합은 전체 재빌드**(③④ ≈5~10분) — 단일 TIN의 대가로 받아들인다. `sheets.csv`의 제작연도가 바뀐 도엽만 재수령(연 1회).
- 건물 월간 교체: ② 재실행 + ③의 보간만(`--stage buildings` 안에서 `data/build/terrain_points.npy`를 읽어 base_z 재계산, TIN 재구성 ≈1분).
- 필지 DB 반기 교체 후: `pnu_src='spatial'`·`pnu NOT IN parcels` 행만 재조인 [data_sources §2.2].
- 실패 시: 단계마다 한 트랜잭션, 예외면 이전 판 유지.

---

## 8. 엔진 API

### 8.1 호출 형태

```python
# cmd_site.py (UI 스레드)
prepared = context_builder.prepare(request, progress=progress, should_cancel=should_cancel)   # Rhino 없음
items    = context_geometry.get_bake_items(prepared)                                          # RhinoCommon 객체, 문서 X
result   = context_baker.run(prepared, items, doc, progress=progress, should_cancel=should_cancel)  # 베이크·3dm·ai
result  |= sheet_svg.write_sheets(prepared, result["result_dir"]) | context_report.write(prepared, result)
```

`run(request) → dict`라는 단일 진입을 원하면 `context_builder.run()`이 위 4줄을 감싼다(Rhino 모듈은 함수 안에서 `loader.load`로 지연 import). 패널은 `run` 하나만 안다.

### 8.2 요청 dict

```json
{
  "target_pnus": ["1120011500103330139"],
  "radius": 500,                      // m. 300/500/1000/임의
  "shape": "buffer",                  // buffer(대상지 bbox+반경, 기본) | circle | rect
  "outputs": {"context_3dm": true, "basemap_ai": true, "sheets_svg": true, "tables_csv": true},
  "basemap": {"paper": "A1", "scale": 1000, "center": null},   // center null = 대상지 중심
  "options": {
    "include_demolished": false,      // 철거 건물 점선 포함
    "include_ngii_shed": false,       // 무벽·가건물 포함
    "parcel_z": "zero",               // zero | terrain(P1)
    "vworld_refresh": false,          // LT_C_BLDGINFO 세션 갱신(P1, 사용자 키)
    "keep_basemap_layers": true
  },
  "result_root": null                 // null = <루트>/result
}
```

검증은 `prepare` 첫 줄: PNU 19자리·DB 존재·반경 >0·축척 ∈ {1000,3000,5000,임의 양수}. 실패는 `ValueError`(한국어 메시지).

### 8.3 응답 dict

```json
{
  "ok": true,
  "result_dir": "result/20261007/성수동2가_333-139",
  "files": {"context_3dm": "...", "context_json": "...", "basemap_ai": "...", "sheets": ["..."], "tables": ["..."], "log": "..."},
  "counts": {"parcels": 1524, "buildings": 1830, "terrain_faces": 10200, "features": 640, "baked_objects": 4100},
  "meta": {
    "origin_e": 204700, "origin_n": 548900, "radius": 500, "crs": "EPSG:5186", "doc_unit": "Millimeters",
    "sources": [{"source_id": "...", "reference_date": "2026-09-09", "age_months": 1.0, "warn": null}],
    "alignment": {"median_m": 1.2, "p90_m": 3.9, "n": 1431, "dx": 0.36, "dy": -0.05},
    "height_src_ratio": {"height": 0.31, "grnd_flr": 0.44, "topo_flr": 0.19, "default": 0.06},
    "sheets": ["37705072", "37705073"]
  },
  "warnings": [{"code": "height_estimated_ratio", "text": "높이 추정 비중 큼 — 등급 A+B 61 %"},
               {"code": "lot_multipart", "text": "대상 필지가 2조각 — 가장 넓은 조각 사용"}],
  "errors": [],
  "seconds": 12.4
}
```

`ok=false`면 `errors[0].text`가 사용자 메시지, 부분 산출물은 `files`에 남는다(3dm은 됐는데 .ai가 실패한 경우 등).

### 8.4 진행률 콜백·취소·오류 규약

- `progress(step, fraction, text)` — `step ∈ constants.CONTEXT_STEPS = ("query", "terrain", "buildings", "features", "bake", "basemap", "sheets", "tables")`, `fraction` 0~1(단계 안), `text` 한 줄. 패널 메시지 `{"type": "progress", "step", "fraction", "text"}`로 그대로 전달(메시지 계약은 `docs/panel_ui.md`가 확정).
- 단일 UI 스레드 전제: 컨트롤러의 `progress`는 `host.push` 뒤 `Rhino.RhinoApp.Wait()`를 불러 WebView가 그려지고 큐의 `cancel` 명령이 처리되게 한다. **Mac WKWebView에서 `RhinoApp.Wait`가 Eto 이벤트를 펌핑하는지 확인 필요** — 안 되면 `prepare`만 `threading.Thread`로 빼고 베이크는 UI 스레드(두 번째로 단순한 길).
- `should_cancel() -> bool` — 각 단계 사이와 긴 루프 200객체마다 확인. True면 `context_builder.Cancelled` 예외 → 베이커는 Undo 묶음 안의 추가분을 지우고(기존 베이커 롤백 패턴) `ok=false, errors=[{"code": "cancelled"}]`.
- 오류 3종: `ValueError`(도메인·입력, 메시지 그대로 표시) / `Cancelled` / 그 외(traceback 포함 `예상 밖 오류`). 경고는 예외가 아니라 `warnings` 누적 + `log.txt`. 피처 하나의 실패(잘못된 링 등)는 건너뛰고 경고(CLAUDE.md "예외는 건너뛰거나 경고").

---

## 9. 테스트 전략

| 범위 | 도구 | 내용 |
|---|---|---|
| 타일 코덱 | `python3 unittest` | numpy 인코더(dev) ↔ `array` 디코더(runtime) 왕복, 헤더 버전 불일치 예외 |
| `context_db` | unittest + **고정 테스트 DB** `tests/fixtures/seongsu_context.db`(성수 4도엽·반경 1 km만 잘라 만든 20~30 MB; 빌더 `--extent` 옵션으로 생성, gitignore 아님) | bbox 질의 건수, 타일 분류 키, 기준일·source 행 |
| `building_height` | unittest | A.4 규칙 0~7 표 기반 케이스(08높이 실측값), 클램프·소표본 플래그 |
| `context_builder.prepare` | unittest(고정 DB) | 원점 100 m 내림, 범위 3종, 정합 통계, 경고 코드, 멀티파트 필지 |
| `sheet_svg`·`context_report` | unittest | 프레임 수학(A1 1:1000 = 841×594 mm ↔ 0.841×0.594 km), SVG가 `xml.etree`로 파싱되고 `<g id>` 14개, CSV 헤더 |
| 빌더 | python3 스크립트(테스트 아님) | `dev_context_builder.py --extent 성수 --stage all` 후 건수·시간·RSS 출력을 `docs/arch_proposals/hybrid_bench.md`에 기록 |
| 베이크·3dm | `python3 scripts/dev_rhino_run.py tests/rhino/drv_context_bake.py` | 고정 대상지로 `run` 실행 → `OUT_DIR/context.3dm` → python3에서 rhino3dm으로 다시 읽어 레이어 12개·건물 UserString 14키·메시 유효성·압출 Z 범위(`base_z ≤ z ≤ base_z+height`) 확인, 소요 시간 로그 |
| .ai 내보내기 | `drv_export_ai.py` | 옵션 문자열 확정, 파일에 `%AI5_BeginLayer` 레이어 수 = BM 레이어 수, 한글 텍스트 바이트 존재 |
| 패널 | 수동 | Mac Rhino + Windows 노트북에서 진행률·취소·폴더 열기 |

**고정 테스트 대상지**: `TEST_CONTEXT_PNU = "1120011500103330139"`(성동구 성수동2가 333-139, 지목 대, 5,586 ㎡, 준공업지역, 중심 ≈ E 204,713 / N 548,999) — 성수 4도엽 범위(E 202,208~206,630 / N 547,279~552,831) 안쪽이라 반경 500 m·1 km가 모두 도엽 안에 든다 [실측]. 기존 `TEST_PNU`(제기동)는 4도엽 북쪽 바깥(N 554,130)이라 쓰지 않는다.

---

## 10. 배포

```
UrbanDesignTool/
  설치방법.txt, UrbanDesignTool.rui, .env(선택: VWorld 키)
  scripts/  loader.py cmd_install.py cmd_site.py site_ui.html vendor/        # 평문
            constants.pyc lot_db.pyc pnu_loader.pyc review_map.pyc non_rhino_utils.pyc
            context_db.pyc building_height.pyc context_builder.pyc context_geometry.pyc
            context_baker.pyc sheet_svg.pyc context_report.pyc panel_host.pyc  # optimize=2
  data/     seoul_site.db (2.1 GB, rtree 제거 사본)  seoul_context.db (≈1 GB)
```

- `dev_deploy.py`는 기존 것을 그대로 가져와 `DATABASE_NAMES`에 컨텍스트 DB를 더하고 `dev_*`·`cmd_*`·loader 제외 규칙은 동일. `.pyc`는 3.9로 컴파일(Mac `/usr/bin/python3` 3.9.6 = Rhino 3.9.10과 매직 넘버 동일).
- 번들 ≈ **3.0~3.3 GB** → USB·사내 공유 폴더 복사 5~10분. DB 2개는 월간·반기 교체 때 파일만 덮어쓴다.
- **첫 실행 패키지 설치 시간 0초** — `# r:` 없음. 첫 실행이 느린 요인은 SQLite 페이지 캐시 워밍(수 초)뿐.
- 사용자 PC 요구: Rhino 8(CPython 3.9 내장), 디스크 4 GB. 인터넷은 VWorld 지도 타일·주소 보조검색·(P1) 건물 갱신에만.

---

## 11. 구현 순서 — 마일스톤 7개

| # | 할 일 | 보이는 결과 |
|---|---|---|
| **M1** 데이터 바닥 | `constants` CTX 절, `context_db.py`, `dev_context_builder.py` ①③(features·terrain) + 타일 코덱 + `--extent 성수`, `building_height.py`, unittest 4종 | `python3 -m unittest` 통과. `seongsu_context.db` 생성(건수·소요·RSS 기록). python3에서 타일을 디코드해 matplotlib 없이 면 수·분류 비율 출력 |
| **M2** 첫 3D | `context_builder.prepare`, `context_geometry`(지형 메시·건물 압출만), `context_baker`(레이어·속성·Undo·WriteFile), `drv_context_bake.py` | Rhino에 성수 333-139 반경 500 m **지형 + 건물**이 뜬다. 3dm 사본을 rhino3dm으로 재검증. 압출 방향 상수 확정 |
| **M3** 컨텍스트 완성 | 필지·도로·수면·녹지·철도·Ref·UserString·context.json·log, 빌더 ②④(GIS건물 벌크·정합), 경고 계산 | 레이어 12개 전부 채워진 3dm. 정합 중앙값·p90이 08 실측(1.2/3.9 m)과 일치 |
| **M4** 버튼 | `cmd_site.py`(init/search/select_pnus/map_parcels/run/cancel/open_folder/open_eum), 진행률·취소, `cmd_install` 보강 | 패널에서 필지 고르고 [생성] → 진행 막대 → 문서에 베이크 → 폴더 열기. 취소 시 되돌아감 |
| **M5** 베이스맵 | BM 2D 항목(해치·커브·텍스트), `.ai` 옵션 문자열 확정(`drv_export_ai.py`), 폴백 결정 | `basemap_1000.ai`를 Illustrator에서 열면 레이어 14개 분리, 1 m = 1 mm |
| **M6** 시트·조서 | `sheet_svg.py` 11+2장, `context_report.py` CSV 5개 | `sheets/01~13_*.svg`가 Illustrator에서 열리고 여백에 자료기준·정합·경고 문구가 자동으로 들어감 |
| **M7** 서울 전체·배포 | 139도엽 전체 빌드(시간·메모리 실측 → §7 수치 갱신), `dev_deploy.py`, Windows 노트북 설치 테스트 | 사용자 PC에서 폴더 복사 → 설치 → 임의 서울 대상지 생성 20초 이내 |
| M8(P1) | VWorld 세션 갱신(`building_height` 재사용), `CTX::QA::cadastre_mismatch`, 필지 드레이프, 교량 | — |

---

## 12. 위험과 대안

| 위험 | 가능성 | 영향 | 대안 |
|---|---|---|---|
| 서울 전체 Delaunay 메모리 초과(점 3백만 이상, 산지 등고선 밀도) | 중 | 빌드 실패 | 4분할 + 겹침 500 m 후 면 중심점 소속으로 합치기(이음새 미세 불일치 허용) 또는 산지 등고선만 8 m 리샘플 |
| 번들 1 GB 초과·복사 시간 | 중 | 배포 불편 | `features.geometry_json` zlib blob(≈4~5배 축소), 등고선 `set_precision(0.1)` |
| `_-Export .ai` 축척·해치 옵션이 스크립트로 안 잡힘 | 중 | 베이스맵 축척 수작업 | 종이 mm 좌표로 베이크(5줄) → 옵션 불필요. 최후 폴백 SVG+JSX [06] |
| 한글 라이브 텍스트 .ai 손상 [06 포럼] | 중 | 라벨 수작업 | 라벨만 SVG 시트에서 가져오기 / 아웃라인 커브 변환 |
| `RhinoApp.Wait`가 Mac WebView를 안 그림 → 진행률·취소 먹통 | 중 | UX | `prepare`를 스레드로, 베이크만 UI 스레드 |
| 도엽 1장 갱신에 지형 전체 재빌드 5~10분 | 확실 | 갱신 번거로움 | 연 1회 작업이라 수용. 자주 바뀌면 TIN을 4분할 캐시 |
| 런타임 보간 없음 → 필지 커브 Z=0, VWorld 신규 건물 base_z 없음 | 확실 | 시각 어색함(P1 전) | §5.6 순수 python 삼각형 탐색 40줄 |
| 서울 GIS건물 동 수·A2 19자리 초과 건수 미확인 [data_sources §4-23] | 중 | 용량·시간 추정 어긋남 | M3에서 실측 후 §7 갱신 |
| 2,000 Extrusion 베이크가 예상(1~3 s)보다 느림 | 낮 | 대기 | `RedrawEnabled=False` 확인, 메시 선계산 없이 Extrusion 유지, 그래도 느리면 `Mesh`로 통합 베이크 옵션 |
| Rhino 문서 단위가 None/Custom | 낮 | 베이크 중단 | 기존 베이커처럼 `ValueError`로 안내(mm·m만 지원) |

---

## 13. 이 설계서의 실측 명령(재현용)

- 지형 규모·타일: 성수 4도엽 등고선 `segmentize(4)` + 표고점 → `scipy.spatial.Delaunay` → 500 m 타일링(`/tmp` 스크립트, §5.2 수치).
- 빌드 소요: 17레이어 읽기·`LinearNDInterpolator` 건물 29만 정점·`STRtree.query(within)` 24.6만 면(§7.2 수치).
- 용량: 도엽 37705072 17레이어 `shapely.to_geojson(set_precision(0.01))` 바이트 합(§7.3).
- 필지 DB: 성수 1 km 박스 bbox 질의 1,524필지 0.053 s, GeoJSON 1.1 MB.
- wheel: `pip download --only-binary=:all: --no-deps --python-version 3.9 --implementation cp --platform {win_amd64|macosx_12_0_arm64|macosx_14_0_universal2}`(§2.2).
- Rhino CPython: `~/.rhinocode/py39-rh8/python3.9 -c "import sys,sqlite3; print(sys.version, sqlite3.sqlite_version)"`.
