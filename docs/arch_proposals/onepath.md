# 엔진 아키텍처 제안 — 한 코드 경로(rhino3dm 작성)

- 작성일 2026-10-07. 접근: **생성 로직 전부를 Rhino 없이 도는 순수 Python 모듈(shapely·numpy·scipy·rhino3dm)로 두고, Rhino 안에서는 같은 모듈이 `.3dm`을 써서 `_-Import` 한다.** RhinoCommon 베이커는 만들지 않는다.
- 근거 표기: `[00 §n]`·`[07 §n]`·`[dl §n]`(deliverables)·`[ds §n]`(data_sources)는 기존 문서. **[실측]** 은 이 설계서를 쓰면서 오늘 직접 돌려 확인한 것(명령·결과를 본문에 적음). **확인 필요**는 못 돌려본 것.

---

## 1. 요약과 핵심 선택

| 결정 | 선택 | 한 줄 이유 |
|---|---|---|
| 런타임 배치 | **Rhino 8 CPython(3.9) 안에서 전부 실행** — 서브프로세스 없음, 혼합 없음 | 배포 PC에 외부 python이 없다. `# r:`로 numpy·scipy·shapely·rhino3dm이 Rhino CPython에 자동 설치되는 것을 Mac Rhino 8.35에서 **[실측]** 확인(아래 §2). 같은 .py가 `/usr/bin/python3`에서도 그대로 돈다 |
| 3dm 생성 | **rhino3dm 작성(writer) 하나** → 패널은 `_-Import` | 00 §1·[실측]: m 단위 3dm을 mm 문서에 Import하면 자동 환산(10 m → 10000 mm). RhinoCommon 베이크는 테스트가 Rhino 안에서만 되고 코드 경로가 둘이 된다 |
| 베이스맵 .ai | 같은 3dm에 `BM::` 2D 레이어를 함께 써서 Import 후 Rhino 내장 `.ai` 내보내기 | 00 §2(레이어 보존, 사용자 Illustrator 확인). SVG→JSX 경로는 1차가 깨질 때만 |
| 현황도 SVG·CSV | 순수 Python(`sheet_svg.py`·`context_report.py`) | Seoungsu `make_basemap_L.py`의 경로 생성 함수를 geopandas 없이 shapely+DB GeoJSON로 이식 |
| 개발·테스트 | `python3 -m unittest discover tests`가 **전체 파이프라인**(DB 질의→TIN→3dm 쓰기→SVG→CSV)을 Rhino 없이 돈다. Rhino는 Import·.ai 내보내기만 `dev_rhino_run.py` 드라이버로 | 1인 개발에서 가장 싼 테스트 루프 |
| 긴 작업 중 UI | v1은 UI 스레드 동기 실행 + 진행률 콜백 안에서 `Rhino.RhinoApp.Wait()` | 기존 컨트롤러 `_run`과 같은 `busy` 패턴. 스레드는 멈춤이 불편해질 때(§8·§12) |

### 배포 시나리오

1. 개발 Mac: `dev_context_builder.py`로 `data/seoul_context.db` 생성(§7), `dev_deploy.py`로 배포 폴더(진입 스크립트 평문 + 로직 `.pyc` + DB 2개 + vendor) 생성.
2. 사용자 PC(Windows 노트북·Mac): 폴더 복사 → Rhino 8에서 `cmd_install.py` 1회 실행(앨리어스·툴바 등록, 보유 코드 그대로).
3. 첫 `대지검토` 실행: `cmd_site.py` 첫 줄 `# r:` 지시자로 Rhino가 pip 설치(인터넷 필요, 1회, 수십 초). 이후 오프라인.
4. 패널에서 대상지 선택 → `context_builder.run(request, progress)` → `result/<날짜>/<대상지>/context.3dm` 등 → `context_baker.import_and_export()`가 `_-Import`·`_-Export .ai`.

---

## 2. 의존성 전략

### 2.1 Rhino CPython에 `# r:`로 넣을 패키지 (전부 cp39 wheel 실재 확인)

`cmd_site.py` 첫 줄(기존 컨트롤러의 `# r: openpyxl` 선례와 동일 자리):

```python
#! python 3
# r: numpy==2.0.2
# r: scipy==1.13.1
# r: shapely==2.0.7
# r: rhino3dm==8.35.0
```

| 패키지 | 왜 필요한가 | cp39 wheel 근거 **[실측, 2026-10-07]** | 대안 |
|---|---|---|---|
| numpy 2.0.2 | TIN 정점 배열·면 분류·경사/표고 계산 | `pip download --only-binary=:all: --python-version 39 --platform win_amd64` → `numpy-2.0.2-cp39-cp39-win_amd64.whl`. Mac: Rhino 자체 python(`~/.rhinocode/py39-rh8/python3.9`, universal2)으로 같은 명령 → `macosx_14_0_arm64`(macosx_11_0_arm64 휠도 존재). **2.0.x가 3.9를 지원하는 마지막 계열** | 없음(scipy 전제) |
| scipy 1.13.1 | `scipy.spatial.Delaunay`(TIN), `cKDTree`(표고점 필터·정합 거리) | win_amd64 휠 확인. Mac `macosx_12_0_arm64`(macOS 11용은 1.8.0rc1뿐 → **Mac은 macOS 12 이상**). 1.13.x가 3.9 마지막 | Delaunay만 필요하면 `triangle`(cp39 휠 있음, 확인 필요) 또는 순수 python Bowyer-Watson(12만 점에 느림) |
| shapely 2.0.7 | 클리핑·버퍼·union·STRtree·`segmentize`·`to_geojson` | win_amd64·macosx_11_0_arm64 휠 확인. 2.0.7이 3.9 마지막(2.1은 3.10+) | 없음. GEOS 없이 폴리곤 클리핑·union을 직접 쓰는 건 비현실적 |
| rhino3dm 8.35.0 | 3dm 쓰기(File3dm·Layer·Extrusion·Mesh·UserString) | win_amd64 휠 확인. Mac `macosx_14_0_universal2`·`macosx_15_0_universal2`만 존재 → **Mac은 macOS 14 이상**(사용자 Mac OS 버전 확인 필요). Rhino 안에서는 RhinoCommon이 있지만 **같은 writer 코드를 python3에서도 돌리기 위해** rhino3dm을 쓴다 | Rhino 안에서만 돌릴 거면 RhinoCommon `File3dm`로 대체 가능(코드 경로가 둘이 되므로 안 함) |
| pyproj | **런타임 불필요.** DB가 이미 EPSG:5186이고 패널 지도용 WGS84 변환은 `non_rhino_utils`에 순수 python으로 있음 | (dev 전용) win_amd64 3.6.1 휠은 있음 | `dev_*.py`에서만 import |
| geopandas·pyogrio·requests | 런타임 불필요. DB 구축(dev_*)에서만 | — | — |

### 2.2 Rhino 8 `# r:` 동작 — Mac에서 실제 확인 **[실측]**

떠 있는 Mac Rhino 8.35에 `rhinocode -r <pipe> script /tmp/udt_rtest.py`로 아래 머리말의 스크립트를 던졌다.

```
# r: numpy / # r: scipy / # r: shapely / # r: rhino3dm  (4줄)
```

| 항목 | 결과 |
|---|---|
| 설치 위치 | `~/.rhinocode/py39-rh8/site-envs/default-g3PW77Aa/`(numpy·scipy·shapely·rhino3dm dist-info 생성. openpyxl·reportlab 등 기존 설치분과 같은 폴더) |
| 소요 | 스크립트 내부 경과 **17.8 s**(설치 포함), 던지고 결과 파일까지 벽시계 34 s. 휠 합계 ≈ 60 MB |
| import 버전 | numpy 2.0.2 / scipy 1.13.1 / shapely 2.0.7 / rhino3dm 8.35.0 (python 3.9.10, arm64) |
| 연산 | `scipy.spatial.Delaunay` 12만 점 **0.39 s**(07 §1.3의 /usr/bin/python3 0.3 s와 같은 급) |
| rhino3dm 쓰기 → `_-Import` | `File3dm.Write` OK → `RhinoApp.RunScript('_-Import "<path>" _Enter')` True → mm 문서에 Extrusion 바운딩박스 `0,0,0 - 10000,8000,12000`(10×8×12 m 자동 환산) |
| SQLite | 3.35.5. 이 Mac Rhino에는 rtree가 있으나 Windows Rhino에는 없다(기존 실측) → bbox B-tree 규약 유지 |

버전 핀 문법 `# r: pkg==x.y.z`는 McNeel 포럼(ScriptEditor 스레드)에서 pip 지정자 그대로 지원한다고 안내한다 — 공식 가이드 페이지(`developer.rhino3d.com/guides/scripting/scripting-command/`)에는 `# r: numpy` 형태만 있고 핀 예시가 없다. **핀이 거부되면 핀을 빼도 결과는 같다**: 위 4개는 각각 cp39용 마지막 릴리스라 pip가 어차피 그 버전을 고른다.

Windows: 사용자 Windows 배포(기존 2026-09-09)에서 같은 `# r:` 메커니즘으로 openpyxl·reportlab이 설치된 선례 + 위 win_amd64 휠 존재로 충분하다고 본다. **Windows Rhino에서 scipy import 1회 실검증은 M1 끝에 사용자 노트북에서 한다**(확인 필요: Windows의 scipy 휠은 OpenBLAS 포함 45 MB라 첫 설치 1~2분).

### 2.3 안 쓰는 것

`triangle`(CDT)·`networkx`·`pandas`·`geopandas` — 런타임에 넣지 않는다. CDT가 필요해지면(옹벽·제방 단차) 그때 `triangle` 휠 확인 후 추가 [dl §A.1 ponytail].

---

## 3. 모듈 지도

```
scripts/
  cmd_install.py        (보유)   설치. 변경 없음
  cmd_site.py           (신규)   # r: 4줄 + 패널 컨트롤러. 명령 → 로직 호출 → push. 기존 컨트롤러 축소판
  site_ui.html          (별도 워크플로)
  panel_host.py         (보유)   변경 없음
  loader.py             (보유)   변경 없음
  constants.py          (보유+)  컨텍스트 절 추가: 레이어명·색·반경·층고 모델·수치지형도 코드→theme/kind·BM 레이어 표
  lot_db.py             (보유)   필지 질의. 변경 없음
  pnu_loader.py / review_map.py / non_rhino_utils.py (보유) 변경 없음
  context_db.py         (신규)   seoul_context.db bbox 질의 → dict 행. 표준 sqlite3만
  context_model.py      (신규)   질의 결과 → 범위 클리핑 → 건물 높이 규칙(A.4) → 도로/수면/녹지 폴리곤 union → 정합 오차 → ContextModel(shapely)
  context_terrain.py    (신규)   등고선·표고점 → 리샘플 → 표고점 필터 → Delaunay → 면 분류 → 수면 평탄화 → 경사/표고 (numpy·scipy)
  context_writer.py     (신규)   ContextModel + TIN → rhino3dm File3dm(CTX::·BM:: 레이어, UserString, 원점 이동 **유일한 자리**) + context.json
  sheet_svg.py          (신규)   베이스맵 엔진 + 현황도 시트 11장 + 표고·경사 2장 → SVG
  context_report.py     (신규)   parcels.csv·buildings.csv·sheet_stats.csv·height_src_stats.csv·alignment.csv·log.txt
  context_builder.py    (신규)   엔진 API run(request, progress) — 위 모듈을 순서대로 부르는 50~100줄
  context_baker.py      (신규)   Rhino 전용: _-Import, BM 레이어 선택 → _-Export .ai, 레이어 표시 복원. RhinoCommon
  dev_context_builder.py(신규)   수치지형도 139 zip + GIS건물 zip → seoul_context.db (geopandas·pyogrio·pyproj)
  dev_deploy.py         (이식)   기존 것에서 DB 2개·cmd_site·site_ui.html로 이름만 바꿈
  dev_rhino_run.py      (보유)   data/*.db 전부 심링크하도록 1줄 수정(지금은 seoul_site.db만)
  dev_check_updates.py  (P1)
```

import 관계(화살표 = import):

```
cmd_site ─loader→ context_builder, context_baker, lot_db, pnu_loader, review_map, constants
context_builder → lot_db, context_db, context_model, context_terrain, context_writer, sheet_svg, context_report, constants
context_model   → context_db(행 타입만), non_rhino_utils, constants      [shapely]
context_terrain → constants                                              [numpy, scipy, shapely]
context_writer  → constants                                              [rhino3dm, shapely(좌표 추출)]
sheet_svg       → constants                                              [shapely]
context_report  → constants                                              (표준 csv·json)
context_baker   → constants                                              [Rhino, scriptcontext]  ← 유일한 Rhino import
```

규칙: `context_*.py`·`sheet_svg.py`는 **Rhino를 import하지 않는다**(python3 테스트 대상). `context_baker.py`만 Rhino. 모든 좌표는 EPSG:5186 m 세계좌표로 들고 다니고 `context_writer`가 쓰는 순간에만 원점을 뺀다. SVG는 세계좌표 → 용지 mm 변환을 자체적으로 하므로 원점과 무관.

재사용 vs 신규: 보유 7개 그대로, 수정 2개(constants·dev_rhino_run), 신규 9개(+ site_ui.html). 선행 자산에서 가져오는 것: 기존 베이커 `_ensure_layer`(레이어 찾기/만들기 → `context_baker`의 BM 레이어 표시 토글에 축소 재사용), 기존 컨트롤러._guard/_run/busy`(컨트롤러 골격), `SHPtoContext` 레이어 코드 목록(07 §7의 11개 개선 반영 후 `dev_context_builder`로), Seoungsu `make_basemap_L.geom_paths/save_svg`(sheet_svg).

---

## 4. 데이터 흐름

```
[원천 zip, 사용자 수동]                        [개발 Mac, python3 + geopandas]            [배포 DB]
data/raw/수치지형도_5000/<도엽>.zip ×137 ──┐
data/raw/수치지형도_5000/sheets.csv        ├─→ dev_context_builder.py ─────────────→ data/seoul_context.db
data/raw/vworld_GIS건물통합정보/AL_D010_11_<기준일>.zip ┘   (sha256·sheet 단위 교체)        (buildings·features·data_sources·source_files)
토지특성·UPIS ──→ dev_database_builder.py(보유) ────────────────────────────────────→ data/seoul_site.db (v5, 변경 없음)

[런타임, Rhino CPython = python3 동일 코드]
request{pnus, radius…}
  → lot_db.load(pnus) → target lots (+ 여러 필지면 합집합, 구멍·조각 경고)             [dl CLAUDE.md 규칙]
  → 범위 폴리곤 = target 합집합 buffer(radius) | 원 | 사각형                               (shapely)
  → lot_db.load_parcels_in_bounds(bbox) / context_db.load_buildings(bbox) / load_features(bbox, themes)
  → context_model: 클리핑(범위 폴리곤과 intersection) → 건물 높이 규칙 → 도로·수면·녹지 union → 정합 오차
  → context_terrain: 등고선 segmentize(4 m) + 표고점(구조물 5 m 버퍼 제외) + 수면·도로·녹지·범위 경계점
        → Delaunay → 면 중심점 STRtree 분류(water/road/green/rail/terrain) → 수면 Z 고정 → 경사(deg)·표고 밴드
  → context_writer: File3dm — CTX::… (3D) + BM::… (2D, 축척 무관 세계좌표) + CTX::Ref 메타 → context.3dm, context.json
  → sheet_svg: 베이스맵 레이어 + 주제 1개 + 범례·카드·여백 메타 → sheets/NN_*.svg ×13
  → context_report: tables/*.csv, log.txt
  → response{result_dir, files, origin, counts, warnings}
[Rhino 전용]
  → context_baker.import_3dm(path) → _-Import (레이어·UserString 보존, 단위 자동 환산)
  → context_baker.export_basemap_ai(scales) → BM 레이어 켜고 선택 → _-Export … .ai → basemap_<축척>.ai
```

VWorld `LT_C_BLDGINFO` 런타임 갱신(세션 캐시)은 `context_model` 앞에 끼우는 선택 단계(`request.options.vworld_refresh`), P1.

---

## 5. 3dm 생성 설계 — rhino3dm 작성으로 확정

**이유** (RhinoCommon 베이크를 버리는 근거): ① python3 unittest에서 결과 3dm을 `rhino3dm.File3dm.Read`로 다시 읽어 레이어·객체 수·UserString·바운딩박스를 검증할 수 있다 ② Rhino 밖 배치 생성(여러 대상지·회귀 테스트)이 된다 ③ 00 §1·[실측]으로 Import 경로의 단위 환산·레이어·UserString 보존이 확인됐다 ④ 베이크 코드가 있으면 "Rhino 안에서는 베이크, 밖에서는 writer" 두 경로가 생겨 1인 개발에 맞지 않는다. Import가 느리거나 문서 병합 문제가 생기면 그때 베이커를 추가한다 [07 §5.3 ponytail].

| 항목 | 설계 |
|---|---|
| 파일 설정 | `Settings.ModelUnitSystem = Meters`, `ModelAbsoluteTolerance = 0.001`, `Write(path, 8)`. `Settings.EarthAnchorPoint`에 원점의 위경도(`non_rhino_utils.get_wgs84_from_tm`)·`ModelNorth=(0,1,0)`·`Description="EPSG:5186 ORIGIN_E=… ORIGIN_N=…"` [07 §5.2]. `File3dm.Strings`는 쓰지 않는다(00 §1) |
| 원점 | `origin = (floor(cx/100)*100, floor(cy/100)*100)`, cx·cy = 대상지 합집합 중심. **`context_writer`의 `_local(xy)` 한 함수만 뺀다.** Z는 절대 표고 그대로 [dl §A.3] |
| 레이어 | `CTX` 부모 + `Site·Parcels·Buildings·Terrain·Terrain::struct_pts·Water·Roads·Green·Rail·Bridges·Zoning·QA::cadastre_mismatch·Ref`; `BM` 부모 + §6 표. 색·이름은 `constants.CTX_LAYERS`/`BM_LAYERS`. rhino3dm: `Layer()` + `ParentLayerId` [07 §5.2]. `Zoning`·`QA`·`BM::*`는 `Visible=False`로 쓴다 |
| 지형 TIN | `context_terrain.build_tin(contours, spots, breaklines_pts, bbox_poly)`: ① `shapely.segmentize(4.0)` → `get_coordinates` ② 표고점 중 교량 `A0070000`·입체교차부 `A0090000`·인터체인지 `A0100000` 5 m 버퍼 안(STRtree)은 `struct_pts`로 분리 ③ 수면·도로·녹지·범위 경계도 4 m 조밀화해 정점으로 추가(Z = 주변 보간, `cKDTree` 최근접 k=8 IDW) ④ `Delaunay(xy)` ⑤ 면 중심점 분류 `contains`(STRtree) → `{"terrain","water","road","green","rail"}` ⑥ 수면 내부 정점 Z = 경계 정점 최저값(hydro-flatten) ⑦ 범위 밖 면 제거. 출력 `(vertices (N,3), faces (F,3), face_class (F,))`. 분류별 `rhino3dm.Mesh`(정점 재인덱싱) → `CTX::Terrain/Water/Roads/Green/Rail`. 성수 4도엽 12만 점 0.3~0.4 s [07 §1.3, 실측]. 무제약 Delaunay(경계 변 미보장) 그대로 — ponytail |
| 건물 | 발자국 외곽 링을 **CW로 정규화**(`shapely.orient(poly, sign=-1)`) → Z = 정점별 지형 보간(`scipy.interpolate.LinearNDInterpolator` 1회 생성, TIN 삼각형 그대로) 최저값 → `PolylineCurve`(평면, 같은 Z) → `Extrusion.Create(crv, height, True)` + 구멍은 `AddInnerProfile` [07 §2.4·§7]. 멀티폴리곤은 파트별 객체. `Create`가 None(자기교차)이면 건너뛰고 log에 `BLD_ID` 기록. 고저차 >3 m면 `HEIGHT_SRC`에 `~slope` |
| 높이 | `context_model.get_building_height(row, ngii_row)` = dl §A.4 규칙 0~7 그대로. 상수 `FLOOR_HEIGHT_MODEL`·`FLOOR_HEIGHT_DEFAULT`·`DEFAULT_BUILDING_HEIGHT_M`은 constants. DB에 `height_m`가 이미 있으면 그대로 쓰고(빌더가 계산) 런타임 VWorld 갱신분만 재계산 |
| 도로/수면/녹지 분류 | 수면 = 필지 DB 지목 하천·구거·유지 ∪ features `water`; 도로 = features `road/surface`(A001) ∪(폴백) 중심선 `도로폭/2` 버퍼 ∪ 지목 도로; 녹지 = 지목 공원·임야 ∪ overlays 공원·녹지 ∪ `D0010000`. 각각 `unary_union` 후 범위로 클리핑. 분류 우선순위 water > rail > road > green > terrain |
| 커브 | 필지·대상지·용도지역·도엽 경계·지하 철도·QA 선 = `PolylineCurve`(링별, 구멍 보존). `Objects.AddCurve(crv, attrs)` |
| UserString | `ObjectAttributes.SetUserString` — dl §A.1 표의 키 그대로(`PNU`·`BLD_ID`·`HEIGHT_M`·`HEIGHT_SRC`·`HEIGHT_GRADE`·`STATUS` …). `CTX::Ref` 원점 마커 Point에 `CRS`·`ORIGIN_E`·`ORIGIN_N`·`RADIUS_M`·`SRC_SHEETS`·`BUILT_AT`·`ALIGN_*`·기준일 키 |
| 사이드카 | `context.json` = Ref UserString 전부 + 원천별 기준일/파일/sha256 + 경고 목록 + 개수. 패널이 이 json으로 요약 카드 표시 |
| 크기·시간 | 반경 500 m: 건물 1~2천 동, TIN 1~2만 점 → 쓰기 1 s 미만, 수 MB. 반경 1 km: 5~6천 동 → 수 초, 수십 MB [07 §5.2 벤치마크 3만 동 2.8~4.4 s/40 MB] |

---

## 6. 베이스맵·시트 생성 설계

### 6.1 베이스맵 `.ai` — Rhino 2D 레이어 + 내장 내보내기

- `context_writer`가 같은 ContextModel로 **`BM::NN_name` 2D 커브/해치 레이어**를 context.3dm에 함께 쓴다(Z=0 평면, 세계좌표-원점). dl §B.2 표의 레이어·K톤 그대로; 색은 레이어 색(회색 K값 → RGB 등가), 선두께는 레이어 `PlotWeight`(mm). 건물 4단계 톤은 `BM::07_bldg_low/mid/high/tower` 레이어 색으로.
- 채움: rhino3dm에 `Hatch` 생성 API가 없다(확인 필요 — `rhino3dm.Hatch` 클래스는 있으나 `Create` 바인딩 유무 미확인). v1은 **닫힌 PolylineCurve만** 쓰고, 면 채움은 `context_baker`가 Import 직후 레이어별 `Hatch.Create(curves, solid_index, …)`(RhinoCommon)로 만든다 — 이것은 "문서 변경"이므로 베이커 책임에 맞다. 또는 사용자가 Illustrator에서 채움(K톤은 어차피 Illustrator에서 조정). ponytail: v1은 **커브만 + 베이커 해치**, Illustrator 쪽 처리로 충분하면 해치 생략.
- 라벨: `TextEntity`도 rhino3dm 생성 바인딩이 불확실 → `BM::12_labels`는 **`TextDot`**(rhino3dm `TextDot(text, location)` 있음)로 쓰고 베이커가 TextEntity로 바꾸거나, 라벨은 SVG 시트에만 둔다. v1: 라벨은 SVG에만, .ai 라벨은 P1(확인 필요: `_-Export` .ai가 TextDot을 어떻게 내보내는지).
- 내보내기(`context_baker.export_basemap_ai`): ① `BM::*` 레이어 Visible=True(원래 상태 기억) ② `CTX::*` 끄기 ③ Top 뷰 ④ `doc.Objects.Select(BM 객체 id)` ⑤ `RhinoApp.RunScript('_-Export "<dir>/basemap_<축척>.ai" _Enter', False)` — 00 §2에서 이 문자열로 레이어 보존 성공. 축척·단위 옵션 문자열(`PreserveUnits`·`Scale` 등)은 **대화식 `-Export`를 1회 돌려 프롬프트를 적은 뒤 constants `AI_EXPORT_OPTIONS`에 고정**(확인 필요). 축척별로 3번 반복 ⑥ 레이어 표시 복원, 선택 해제.
- 범위 초과(A1 1:1000 = 0.84×0.59 km < 반경 500 m 지름 1 km): 경고만 [dl §B.1].
- 한글 라이브 텍스트·4만 해치 성능·캔버스 한계는 dl §B.3의 "구현 전 1회 확인" 그대로 M4에서 본다.

### 6.2 현황도 SVG — `sheet_svg.py`

- 프레임 = (용지, 축척, 중심): `mm_per_m = 1000/scale`, viewBox mm. `world → paper` 변환 함수 하나. Seoungsu `make_basemap_L.py`의 `path_of/geom_paths/save_svg`를 shapely 2 `get_coordinates` 기반으로 이식(geopandas·WGS84 산술 제거, 입력은 ContextModel의 5186 폴리곤).
- 레이어 = `<g id="NN_name">`(Illustrator가 그룹으로 연다). 베이스 그룹 6개(01 수계·02 녹지·03 도로면·04 도로경계·06 철도·10 대상지) + 주제 그룹 1개 + `legend`·`card`·`meta` 그룹.
- 시트 13장 각각은 `SHEETS = [("02_landuse", classify_fn, legend), …]` 표 한 개로 선언. classify_fn은 필지/건물 행 → 범례 키. 표고·경사는 TIN 면(`face_class=="terrain"`)을 밴드별 폴리곤으로 채색(삼각형 그대로, 래스터화 안 함).
- 여백 메타 5줄(자료기준·출처·좌표계·정합·경고)은 `context_report.get_meta_lines(ctx)` 한 함수에서 만들어 SVG와 CSV·json이 같은 문자열을 쓴다.

---

## 7. DB 빌더 설계 — `dev_context_builder.py`

입력 실측 **[실측]**: 137/139 도엽 zip 246 MB, SHP 합계 505 MB, 레이어 코드 117종(접두 `N3`/`N1` 혼재 → 접두 2글자 뗀 키로 매핑). 10도엽 샘플에서 핵심 19개 레이어 43,649행 / 8.7 s(속성만) → 137도엽 ≈ **60만 행·2분**(형상 포함 2~3배). 성수 1도엽 11개 레이어 22,146행 1.18 s, 건물 12,426동 GeoJSON 2.8 MB 0.08 s. GIS건물 695,754동: 20만 행 읽기 3.6 s·GeoJSON 0.7 s·66 MB → 전체 **≈ 13 s 읽기, 230 MB GeoJSON**.

적재 순서(한 명령 `python3 scripts/dev_context_builder.py [--sheets 37705072,…] [--buildings]`):

| 단계 | 처리 | 예상 시간/메모리 |
|---|---|---|
| 0 | `data/backup/seoul_context_<날짜>.db`로 `cp` 1장(3판 초과 삭제). 작업은 `seoul_context.building.db`에 하고 끝나면 `os.replace` | 수 초 |
| 1 | `data_sources` upsert 2행(`ngii_5000`, `vworld_bldg`), `source_files` 생성 | — |
| 2 | **수치지형도 도엽 루프**(137회): zip sha256 → `source_files`와 같으면 건너뜀. 다르면 `DELETE FROM features WHERE source_id='ngii_5000' AND sheet=?` → `pyogrio.read_dataframe('/vsizip/…', encoding='cp949')`로 `constants.NGII_LAYER_MAP`(코드→theme/kind/value 컬럼)에 있는 레이어만 읽기 → `.prj`가 5186이 아니면 `pyproj` 변환(Y 범위 교차검사 [ds §2.3]) → 표고점 중 A007/A009/A010 5 m 버퍼 안은 `kind='spot_struct'` → GeoJSON+bbox 행 `executemany` → 도엽당 1 commit. 수치지형도 건물(`B0010000`)은 `features`가 아니라 임시 테이블 `ngii_bldg`에 | 도엽당 2~4 s → **5~10분**, 메모리 <500 MB |
| 3 | **GIS건물 전체본 교체**: sha256 비교 → 한 트랜잭션 `DELETE WHERE source_id='vworld_bldg'` → 5만 행 청크로 `pyogrio.read_dataframe(skip_features, max_features)` → `A2` PNU는 `ATTACH seoul_site.db`해서 `parcels.pnu` 존재 확인, 없거나 19자리 초과면 대표점 공간조인(`lot_db` bbox 질의 → shapely contains) → 행 삽입 | **3~5분**, 청크당 <300 MB |
| 4 | **수치지형도 건물 조인**: `ngii_bldg` STRtree(약 110만 폴리곤 추정 — 성수 밀도 2천/km² × 605 km²; 확인은 적재 로그로) ↔ GIS건물 대표점 → `grnd_flr=0`이면 `층수` 채움, 아파트·연립 `층수 ≥ grnd_flr+3`이면 치환(`flr_src='topo'`), `ngii_kind/use` 기록 → 매칭 안 된 `ngii_bldg`는 `src_key='ngii:<UFID>'`로 `buildings`에 추가(무벽·가건물 포함, 런타임 옵션으로 필터) | 2~3분 |
| 5 | 높이 모델(A.4 규칙 0~7) → `height_m/height_src/height_grade/attr_flag` 일괄 UPDATE | 1분 |
| 6 | 인덱스(`idx_buildings_bbox/pnu/status`, `idx_features_bbox/theme/sheet`) → `ANALYZE` → `VACUUM` | 1~2분 |

합계 **15~25분**, 피크 메모리 1~2 GB(개발 Mac). 중복 처리: 도엽 경계에서 잘린 도로면·하천면은 **dissolve하지 않고** 런타임 `unary_union` [ds §2.2]. 도엽 경계에 걸친 건물 폴리곤이 두 도엽에 중복될 수 있음 — v1은 처리 안 함(대표점 조인이라 GIS건물 한 동에 두 후보가 와도 첫 것만 씀; `ngii:*` 추가분은 중복 가능 → log 카운트만). 도엽 교체: 새 zip을 같은 이름으로 두고 재실행하면 sha256이 달라 그 도엽만 2단계 재적재; 건물 조인(4·5단계)은 `--buildings` 때만. `sheets.csv`의 `year` 열이 비어 있으면 `reference_date`에 다운로드일 + "(제작연도 미기재)" [ds §2.3]. 누락 2도엽(`37608050`·`37608073`)·등고선 없는 `37709006`은 `source_files`에 없으므로 런타임 `SRC_SHEETS` 경고로 드러난다.

예상 DB 크기: features GeoJSON ≈ 500~700 MB + buildings ≈ 300 MB + 인덱스 → **약 1.0~1.5 GB**(추정, 1차 빌드 후 확정).

---

## 8. 엔진 API — `context_builder.run(request, progress=None) -> dict`

```python
request = {
  "pnus": ["1120011500103140006"],            # 필수. 여러 개면 합집합 대상지
  "radius": 500.0,                            # m. 기본 constants.CONTEXT_RADIUS
  "shape": "buffer",                          # buffer | circle | rect
  "outputs": ["3dm", "basemap", "sheets", "tables"],   # 생략 = 전부
  "basemap": {"paper": "A1", "scales": [1000, 3000, 5000]},
  "options": {
    "include_temp_buildings": False,          # 수치지형도 무벽·가건물
    "demolished": "dashed",                   # dashed | exclude
    "zoning_layer": False,                    # CTX::Zoning 쓰기
    "vworld_refresh": False                   # P1: LT_C_BLDGINFO 세션 캐시 갱신
  },
  "result_dir": None,                         # None = result/<YYYYMMDD>/<대상지명>/
  "site_db": None, "context_db": None         # None = constants 경로 (테스트에서 덮어씀)
}

response = {
  "ok": True,
  "result_dir": ".../result/20261007/성수동2가_314-6",
  "files": {"3dm": ".../context.3dm", "json": ".../context.json",
            "sheets": [".../sheets/01_location.svg", ...], "tables": [...], "log": ".../log.txt",
            "basemap_ai": []},                # 베이커가 내보낸 뒤 채운다
  "origin": {"e": 204900.0, "n": 549400.0, "lng": 127.0554, "lat": 37.5441},
  "counts": {"target_lots": 1, "near_lots": 1499, "buildings": 1830, "tin_points": 18000,
             "skipped_buildings": 3, "demolished": 4},
  "alignment": {"median_m": 1.2, "p90_m": 3.9, "n": 1700},
  "warnings": ["등고선 없는 도엽 37709006 포함", "건물 자료 4.2개월 경과 …"],
  "seconds": 6.8
}
```

- **진행률 콜백** `progress(stage, fraction, text) -> bool`. `stage ∈ {"query","model","terrain","write","sheets","tables"}`, `fraction` 0~1 전체 진행률, `text` 한국어 한 줄. **False를 돌려주면 취소**: 엔진은 `Cancelled` 예외를 올리고 `result_dir`의 반쯤 쓴 파일을 지운다. 엔진 안에서 콜백은 단계 경계 + 건물 500동마다 + 시트 1장마다 부른다(초당 몇 번 수준).
- Rhino 쪽 콜백(`cmd_site`): `host.push({"type":"progress", "stage", "fraction", "text"})` 뒤 `Rhino.RhinoApp.Wait()` 호출 → 웹뷰가 그려지고 큐에 쌓인 `cancel` 명령이 처리된다. `cancel`은 컨트롤러의 플래그만 세우고 콜백이 그 플래그를 돌려준다. python3 테스트에서는 `progress=None`(무시) 또는 리스트에 append하는 람다.
- **오류 규약**: 도메인 오류는 `ValueError/KeyError/FileNotFoundError/RuntimeError`에 한국어 메시지(없는 PNU, DB 없음, 스키마 버전, 반경 0, 범위 안 지형 데이터 0건) → 컨트롤러 `_guard`가 `{"type":"error"}`로 푸시(기존 그대로). 예상 밖 예외는 traceback째. **경고는 예외가 아니라 `response.warnings`+log.txt**(건너뛴 건물·폴백 사유·기준일 경과·표본 부족). 파일 일부만 실패(예: 시트 1장)해도 `ok=True`로 두고 warnings에 적는다.
- 베이커 API(Rhino 전용, `context_baker`): `import_3dm(path) -> int(추가 객체 수)`, `export_basemap_ai(result_dir, scales) -> list[path]`, `clear_previous(lot_key)`(이전 CTX/BM 객체 삭제 — 기존 베이커 `_clear_baked` 축소). 호출 순서는 `cmd_site._run`: `busy on → run → import → export → push done → busy off`.

---

## 9. 테스트 전략

| 범위 | 방법 | 고정 대상지 |
|---|---|---|
| `tests/test_context_db.py` | 성수 bbox 질의 행 수·bbox 인덱스 존재·스키마 버전 | `seoul_context.db`가 없으면 `skipTest` |
| `tests/test_context_terrain.py` | 합성 등고선 3개 + 표고점 → TIN 면 수>0, 수면 정점 Z 동일, 구조물 버퍼 안 표고점 제외, 경사 0~90 | 합성 데이터(DB 불필요) |
| `tests/test_context_model.py` | 높이 규칙 0~7 표 기반 케이스(archarea 불신·아파트 topo 우선·클램프), CW 정규화, 범위 클리핑, 정합 오차 샘플 | 합성 + 성수 |
| `tests/test_context_writer.py` | `run()` 후 `rhino3dm.File3dm.Read` → 레이어 FullPath 집합, `CTX::Buildings` 객체 수 = counts, 원점 마커 UserString, 단위 Meters, 바운딩박스가 반경 안 | **성수동2가 314-6 (PNU `1120011500103140006`, 2,722 ㎡, 준공업지역, 성수역 150 m)** — 도엽 37705072·73·82·83 안, 1 km 상자 필지 1,499 [실측] |
| `tests/test_sheet_svg.py` | 13장 파일 생성·`<g id=` 레이어 수·viewBox mm·메타 5줄 포함 | 성수 |
| `tests/test_context_builder.py` | 전체 `run()` 1회 → response 스키마·진행률 콜백 호출 순서·취소(2번째 콜백에서 False → 폴더 비워짐) | 성수 (반경 300 m로 빠르게) |
| Rhino 드라이버 `dev/driver_import_export.py` (`python3 scripts/dev_rhino_run.py …`) | 성수 결과 3dm `_-Import` → 객체 수·레이어·단위 환산 확인 → `.ai` 3장 내보내기 → 파일 크기·`%AI5_BeginLayer` 개수 확인 → 문서 정리 | 성수. `dev_rhino_run`이 `data/*.db`를 전부 심링크하도록 수정 |
| Rhino `# r:` 설치 | 위 드라이버 첫 줄에 `# r:` 4줄을 두고 `site-envs`를 지운 뒤 1회 실행(설치 시간 기록) | — |

python3 테스트가 Rhino 없이 `context.3dm`까지 만들므로, Rhino 드라이버는 Import·Export 두 동작만 본다.

---

## 10. 배포

```
UrbanDesignTool/                     ← 폴더째 복사 (USB·공유폴더)
  UrbanDesignTool.rui, 설치방법.txt
  scripts/ loader.py cmd_install.py cmd_site.py site_ui.html vendor/   (평문)
           constants.pyc lot_db.pyc … context_*.pyc sheet_svg.pyc      (optimize=2, Rhino 3.9와 같은 magic)
  data/    seoul_site.db (2.1 GB, rtree 제거본)  seoul_context.db (≈1.0~1.5 GB 추정)
  result/  (실행 시 생성)
```

- `dev_deploy.py`: 기존 것을 이식. `PLAIN_SCRIPT_NAMES=("loader.py","cmd_install.py","cmd_site.py")`, `DATABASE_NAMES=("seoul_site.db","seoul_context.db")`, `strip_spatial_index`는 두 DB에 적용. `.pyc`는 3.9.x magic이 같아 Mac `/usr/bin/python3` 3.9.6으로 컴파일해도 Rhino 3.9.10이 읽는다(기존 선례).
- 번들 크기 **≈ 3.5 GB**. 첫 실행 패키지 설치: Mac 실측 ≈ 20~35 s(휠 60 MB); Windows는 scipy 휠이 더 커 **1~2분 추정**(인터넷 필요, 1회). 설치 위치 `~/.rhinocode/py39-rh8/site-envs/default-*/`. 설치 실패 시 안내: 그 폴더 삭제 후 재실행.
- `.env`(VWorld 키)는 사용자별. 배포본에 키 내장 금지 [ds §0].
- 코드 갱신 = `scripts/` 덮어쓰기, DB 갱신 = `data/*.db` 교체(cmd_install 재실행 불필요).

---

## 11. 구현 순서 (마일스톤과 '보이는 결과')

| M | 내용 | 보이는 결과 |
|---|---|---|
| **M1** 의존성·골격 (0.5일) | `cmd_site.py` 머리말 `# r:` 4줄 + 빈 컨트롤러(init·search·select_pnus·map_parcels는 (이식), `constants` 컨텍스트 절, `dev_rhino_run` DB 심링크 수정 | Windows 노트북·Mac에서 패널이 뜨고 로그에 numpy/scipy/shapely/rhino3dm 버전이 찍힘(설치 시간 기록) |
| **M2** 컨텍스트 DB (1~2일) | `dev_context_builder.py` 2·3단계(수치지형도 features + GIS건물 원본 적재) → 4·5단계(조인·높이) | `seoul_context.db` 생성, 성수 bbox 질의 행 수 로그, `test_context_db` 통과 |
| **M3** 3dm 1차 (2일) | `context_db`·`context_model`(클리핑·높이)·`context_terrain`·`context_writer`(CTX만)·`context_builder.run` 최소 | `python3 -m unittest` 로 성수 `context.3dm` 생성 → Rhino에서 열어 건물·지형·수면·도로가 보임 |
| **M4** 패널 연결 + Import/.ai (1일) | `context_baker`, `cmd_site._run`(busy·progress·cancel), `BM::` 레이어 쓰기, `.ai` 옵션 문자열 확정 | 패널 버튼 → 현재 문서에 컨텍스트 들어오고 `basemap_1000.ai` 등 3장이 result/에 생김, Illustrator에서 레이어 분리 확인 |
| **M5** 시트·조서 (2일) | `sheet_svg.py` 13장, `context_report.py` CSV 5개 + log + 메타 5줄 | `sheets/`·`tables/` 채워짐, 시트 여백에 자료기준·정합 오차 자동 표기 |
| **M6** QA·정합·기준일 (1일) | `CTX::QA::cadastre_mismatch`, 정합 오차 측정, 기준일 경과 경고, 철거 점선 옵션 | Ref UserString·context.json에 `ALIGN_*`, 경고가 패널·시트에 뜸 |
| **M7** 배포 (0.5일) | `dev_deploy.py` 이식, 설치방법.txt, Windows 노트북 실설치 | 사용자 PC에서 버튼 한 번으로 M4·M5 결과 재현 |
| **M8** P1 (이후) | VWorld 런타임 갱신(세션 캐시), 건축HUB 철거, Rail/Bridges 메시, 라벨 .ai, `dev_check_updates.py` | — |

---

## 12. 위험과 대안

| 위험 | 가능성·영향 | 대안 |
|---|---|---|
| Windows Rhino에서 `# r:` scipy 설치 실패(프록시·권한·pip 오류) | 낮음(openpyxl·reportlab 선례) / 치명 | ① `site-envs` 폴더 삭제 후 재실행 ② 개발 Mac에서 `pip download --platform win_amd64` 한 휠 5개를 배포 폴더 `wheels/`에 동봉하고 `cmd_site`가 `# env:` 대신 Rhino python의 pip로 `--no-index --find-links wheels/` 설치(확인 필요) |
| 사용자 Mac이 macOS 13 이하 → rhino3dm cp39 휠(14_0+) 없음 | 낮음 | Rhino 안에서는 RhinoCommon `File3dm`로 writer를 대체할 수 있으나 코드 경로가 둘이 됨 → 먼저 OS 업그레이드 요청 |
| 긴 작업(반경 1 km, 시트 13장) 동안 Rhino UI 멈춤·취소 지연 | 중간 / 불편 | 진행률 콜백의 `RhinoApp.Wait()`로 완화. 그래도 불편하면 엔진을 `threading.Thread`로 돌리고 `push`만 `Application.Instance.AsyncInvoke`로(엔진은 Rhino 문서를 안 건드리므로 스레드 안전). 마지막 수단: Rhino 번들 python(`~/.rhinocode/py39-rh8/python3.9`, Windows `%USERPROFILE%\.rhinocode\py39-rh8\python.exe`)으로 서브프로세스 — `PYTHONPATH`에 `site-envs` 경로를 넘기면 같은 패키지를 쓴다 |
| rhino3dm에 Hatch·TextEntity 생성 바인딩이 없을 때 .ai 채움·라벨 | 중간 / 베이스맵 완성도 | 베이커가 Import 후 RhinoCommon으로 해치·문자 추가(§6.1). 그래도 부족하면 dl §B.3 대안(SVG→Illustrator JSX) |
| `_-Export` .ai가 한글 텍스트·대량 해치에서 깨짐 | 알 수 없음(06 포럼 보고) | M4 1회 확인. 깨지면 라벨·해치는 SVG 경로로 |
| 무제약 Delaunay 톱니(도로·수면 경계), 옹벽 단차 뭉개짐 | 중간 / 외관 | `triangle` CDT + 브레이크라인(`F0030000/F0040000`) — cp39 휠 확인 후 `# r:` 1줄 추가 |
| 도엽 경계 건물 중복(`ngii:*` 추가분) | 낮음 / 조서 집계 오차 | 빌더 4단계에서 `ngii_bldg` 대표점이 다른 도엽의 같은 폴리곤 안에 있으면 하나만 남기는 10줄 추가 |
| context DB가 예상(1.5 GB)보다 커짐 | 낮음 | 등고선·표고점 좌표를 소수 2자리로 반올림(지형 1:5000 정확도 1.5 m라 손실 없음), `features`에서 분석 테마 분리 |
| Import가 사용자 문서 레이어와 충돌(같은 `CTX` 이름이 이미 있음) | 중간 | 베이커 `clear_previous`가 `CTX`·`BM` 하위 객체를 먼저 지움(기존 베이커 `_clear_baked` 패턴). 다른 대상지를 같은 문서에 겹치려면 사용자가 레이어 이름을 바꿔 두면 됨 — 안내만 |
