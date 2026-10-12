# 엔진 아키텍처 제안 — "Rhino 안에서 전부" (in-Rhino)

- 작성일: 2026-10-07. 경쟁 제안(외부 python 서브프로세스 / 혼합)과 같은 심사 기준으로 읽히도록 12절 형식을 지켰다.
- 근거 표기: **[실측 YYYY-MM-DD job]** = 오늘 이 Mac Rhino 8.35에서 `dev_rhino_run.py`로 돌린 결과(`result/rhino_jobs/<job>/out/log.txt`), **[로컬]** = python3/pip로 직접 확인, **[00~08 §x]** = `docs/research`, **확인 필요** = 못 봤음.
- 한 줄 결론: **런타임은 Rhino 8 CPython + RhinoCommon + 표준 라이브러리만. pip 패키지 0개. 베이크가 곧 3dm 생성이다.** 오늘 실측에서 이 접근의 미지수였던 세 가지(RhinoCommon Delaunay 속도·Z 보존, 메시 투영 배치 속도, `.ai` 내보내기 옵션 문자열·해치 채움)가 전부 풀렸다.

---

## 1. 요약과 핵심 선택

### 1.1 런타임 배치: Rhino CPython 안에서 전부

| 단계 | 어디서 | 무엇으로 |
|---|---|---|
| 공공데이터 수집·정규화·공간교차·DB 구축 | 개발자 Mac `/usr/bin/python3`(`dev_*.py`) | geopandas·pyogrio·shapely·pyproj (지금 있음) |
| 대상지 선택 → DB 질의 → 높이 규칙 → TIN → 압출 → 베이크 → 3dm 저장 → 베이스맵 2D → `.ai` → SVG 시트 → CSV | **Rhino 8 CPython(3.9) 안, 패널 버튼 한 번** | `sqlite3`·`json`·`csv`·`math` + RhinoCommon |

외부 python 프로세스 없음. `# r:` 지시자 없음. 배포 = 폴더 복사 + `cmd_install.py` 1회(지금 그대로).

### 1.2 왜 이 선택인가 (오늘 실측)

| 미지수(07 §9-7, 06 §5) | 결과 | 출처 |
|---|---|---|
| `Mesh.CreateFromTessellation` 속도 | 성수 반경 500 m 실데이터 **4,121점 → 0.01 s(7,981면)**, 반경 1 km **30,276점 → 0.03 s(60,291면)**. 입력 Z 보존(bbox Z 10.5~35 m) | [실측 2026-10-07 1007-203742-8486] |
| 볼록껍질까지 채워지는 문제 | 반경 밖 면을 `GetFaceCenter` + `CreateFromFilteredFaceList`로 제거: 0.05 s(733면 제거) / 0.34 s | 같은 job |
| 도로 경계를 제약변으로 | **실패** — 겹치는 도로 링을 `edges`로 넣으면 `IsValid=False`(1 km는 면 0개). 제약변은 쓰지 않고 면 중심 분류로 간다 | 같은 job |
| 발자국 정점 지형 투영 | `Intersection.ProjectPointsToMeshes` **14,768점 0.06 s / 59,351점 0.25 s** | 같은 job |
| 건물 압출 | `Extrusion.Create(curve, plane, h, cap)` **2,174동 0.19 s / 8,517동 0.75 s**, 실패 1·2동(자기교차 추정) | 같은 job |
| 문서 베이크 | 2,175 Extrusion + 지형 메시, UserString 3개씩, `RedrawEnabled=False`: **0.08 s** | 같은 job |
| 면 분류(도로 609폴리곤 × 7,981면) | `Curve.Contains` 0.82 s, 순수 파이썬 ray-casting 0.69 s(결과 2,546 vs 2,549면). 1 km(1,708 × 60k면)는 bbox 전수 비교 탓에 16 s → **격자 버킷 필요**(§5.3) | 같은 job |
| 해치 2,175개 생성 | `Hatch.Create` 0.23 s | 같은 job |
| `.ai` 내보내기 옵션 문자열 | 프롬프트 실체: `AI 옵션 선택 ( 단위_유지(P) 뷰포트_경계(V) 컬러(C) 해치를_단색_채우기로(H) 레이어_순서지정(O) )` → 단위_유지=예 이후 `AI배율(A) 단위(U) Rhino배율(R)` 추가. 영문 토큰 **`_PreserveUnits _Unit=_mm _RhinoScale _AIScale _HatchesAsSolidFills _OrderLayers _Color`** 전부 수용. 300 m 정사각형(문서 mm)을 `_RhinoScale=3000 _Unit=_mm`로 내보내 **bbox 284 pt = 100 mm** 확인(1:3000 정확) | [실측 1007-204134-f8d9, 1007-204228-0084] |
| 해치가 solid fill로 들어가나 | 들어간다(`%AI5_BeginLayer … f` 연산자). 단 Solid 패턴을 `FindName("Solid")`로 찾으면 한국어 UI("채우기")에서 None → `FillType==Solid`로 찾는다 | [실측 1007-204228-0084] |
| 한글 라이브 텍스트 | 파일에는 UTF-8 바이트가 PostScript 문자열 `(…) Tx`로, 폰트 `ArialMT`. Illustrator가 이를 한글로 읽는지 **확인 필요**(06 포럼 손상 보고와 일치할 가능성 큼) → 라벨은 SVG 경로(§6.4) | [실측 1007-203940-f62b] |

→ 반경 500 m 전체 파이프라인의 지오메트리 계산은 **수 초**, 1 km도 **10 s 안쪽**(분류 격자화 후). "Rhino 안에서 기다릴 만한 수준"(CLAUDE.md)을 크게 밑돈다.

### 1.3 배포 시나리오

1. 개발자 Mac: `dev_context_builder.py`로 `data/seoul_context.db` 생성(§7), `dev_deploy.py`(이식)로 `UrbanDesignTool/` 배포 폴더 생성(로직 `.pyc`, 진입 평문, DB 2개).
2. 사용자 PC(Windows 노트북·Mac): 폴더 복사 → Rhino에서 `cmd_install.py` 1회 → 명령 `UrbanSite`. **인터넷·pip 불필요**(VWorld 보조 조회를 켠 경우만 네트워크).
3. 갱신: `scripts/` 덮어쓰기(코드), `data/*.db` 교체(데이터). 재설치 없음.

### 1.4 deliverables.md와 다른 점 (이 제안이 바꾸자는 것)

| deliverables 현재 | 이 제안 | 이유 |
|---|---|---|
| "Rhino 밖 rhino3dm writer → 패널에서 `_-Import`" | **RhinoCommon 베이크가 유일 경로**, 3dm은 베이크 결과를 `WriteFile`로 저장 | 코드 경로 하나는 그대로이고, Import 단계·외부 python·rhino3dm 의존이 사라짐. 배포 PC에 python이 없다는 제약을 가장 단순히 만족 |
| "numpy/scipy TIN" | `Mesh.CreateFromTessellation` | 0.03 s @ 30k점 실측. scipy 46 MB 휠 설치가 필요 없음 |
| "shapely 클리핑" | 클리핑 없음 — 점은 반경 안만 쓰고, 면은 TIN 면 중심 분류, 폴리곤은 bbox 겹침만으로 통째 포함 | 건물·필지는 자르면 오히려 틀리고, 도로·수면은 TIN 분류로 경계가 생긴다 |
| 원점 이동은 "베이커 한 곳" | 원점 결정은 `context_builder` 한 곳, **적용은 `utils.get_local_pts` 한 함수**(DB 좌표 → 로컬 좌표 변환기), 베이커는 단위 환산과 기록만 | Rhino `Mesh.Vertices`는 **단정밀도(Point3f)**라 E 20만·N 55만 좌표로 메시를 만들면 0.03~0.06 m 오차가 생긴다. 메시 생성 전에 로컬 좌표여야 한다(§5.5) |

---

## 2. 의존성 전략

### 2.1 런타임(Rhino CPython) — pip 패키지 0개

| 패키지 | 필요한가 | 대체 | cp39 휠(참고용, 안 씀) |
|---|---|---|---|
| **shapely** | 아니오 | 점-in-폴리곤·bbox·링 면적·리샘플은 순수 파이썬(`non_rhino_utils.py`, 성수 반경 500 m 기준 1 s 이내 실측). 폴리곤 불린은 설계에서 제거(§5.3). 정말 필요한 곳(P1 정합 오차의 도로 필지 합집합)은 `Curve.CreateBooleanUnion` | win_amd64 2.0.7 ✓, macosx_11_0_arm64 2.0.7 ✓ [로컬 pip download] |
| **numpy** | 아니오 | 배열 연산 규모가 수만 점이라 리스트로 충분(실측) | win 2.0.2 ✓, mac arm64 ✓ |
| **scipy** | 아니오 | `Mesh.CreateFromTessellation`(Delaunay, 제약변 없이). **비상 대안**: 진입 스크립트 1줄 `# r: scipy` + `scipy.spatial.Delaunay`(07 §1.3 0.3 s @ 12만 점) | win 1.13.1 ✓, **macosx_12_0_arm64** 1.13.1 ✓(11_0 태그로는 1.8.0rc1만 잡힘 — Rhino pip는 실제 OS 태그를 쓰므로 문제 없음) |
| **rhino3dm** | 아니오 | Rhino 안에서는 RhinoCommon이 상위호환. 3dm 저장은 `RhinoDoc.WriteFile` | win 8.35.0 ✓, macosx_14_0_universal2 8.35.0 ✓ |
| **pyproj** | 아니오 | DB는 전부 EPSG:5186 적재 완료 상태. VWorld 2D API는 `crs=EPSG:5186` 직접 요청 가능 [05 §1]. 패널 지도용 5186↔4326은 `non_rhino_utils.get_tm_from_wgs84`(이미 있음, 순수 파이썬) | win 3.6.1 ✓, mac arm64 ✓ |
| **requests** | 아니오 | `urllib`(이미 `pnu_loader.py`가 그렇게 함) | — |
| **sqlite3** | 표준 라이브러리 | Rhino 8 CPython 3.9.10의 sqlite 3.35.5 확인 [로컬 `~/.rhinocode/py39-rh8/python3.9`]. RTree 모듈 없음(CLAUDE.md) → bbox B-tree만 | — |

모든 휠이 있다는 사실은 **"막히면 1줄로 되돌릴 수 있다"**는 보험이지 계획이 아니다. 첫 실행 설치 시간 0, 오프라인 OK, Windows/Mac 동일 코드가 이 접근의 요지다.

### 2.2 개발자 Mac(`dev_*.py`) — 지금 있는 것 그대로

geopandas 1.0.1 / shapely 2.0.7 / pyogrio 0.11.1 / pyproj 3.6.1 / numpy 2.0.2 / **scipy 1.13.1(있음, 확인)** / rhino3dm 8.35.0 [로컬]. `triangle` 없음(쓸 일 없음).

### 2.3 Rhino 환경 전제

- Rhino 8 CPython 3.9.10, site-env `~/.rhinocode/py39-rh8/site-envs/default-*`(기존 넣은 openpyxl·reportlab·pyshp·pillow가 이미 있음 — 이 프로젝트는 쓰지 않음).
- `.pyc` 배포는 3.9 전용(dev_deploy.py가 강제).

---

## 3. 모듈 지도

```
scripts/
  cmd_install.py        (재사용) 설치 — 앨리어스·툴바
  cmd_site.py           (신규·패널 워크플로 소관) 컨트롤러: panel_host ↔ context_builder.run
  panel_host.py         (재사용) Eto WebView 호스트
  site_ui.html          (신규·패널 워크플로 소관)
  loader.py             (재사용)
  constants.py          (재사용+추가) CTX/BM 레이어·색·층고 모델·반경·도엽 코드 매핑·export 문자열
  ── 로직 모듈(Rhino 런타임 import, 표준 라이브러리 + RhinoCommon) ──
  lot_db.py             (재사용) 필지 DB 질의 (load / load_near_lot_candidates / load_parcels_in_bounds)
  pnu_loader.py         (재사용) 주소→PNU
  review_map.py         (재사용) 패널 지도 GeoJSON
  non_rhino_utils.py    (재사용+추가) GeoJSON 링·bbox·면적 + [추가] point_in_polygon, GridIndex, resample_ring, ring_orientation
  context_db.py         (신규, Rhino 금지) seoul_context.db bbox 질의 → dict 목록 (buildings / features by theme / data_sources / source_files)
  building_height.py    (신규, Rhino 금지) A.4 높이 규칙·층수 채택·HEIGHT_GRADE·attr_flag, 기준일 경과 경고
  vworld_buildings.py   (신규, Rhino 금지) LT_C_BLDGINFO BOX 호출(urllib), 세션 메모리 캐시, INVALID_KEY 매핑
  utils.py              (신규, RhinoCommon) GeoJSON→PolylineCurve, get_local_pts(원점 적용), 레이어 ensure(기존 베이커 패턴), 속성+UserString
  context_geometry.py   (신규, RhinoCommon, 문서 금지) TIN·면 분류·hydro-flatten·투영·압출·수면 평면·교량 슬래브 → ContextGeo
  context_baker.py      (신규, RhinoCommon+RhinoDoc) CTX:: 레이어 베이크, 단위 환산, EarthAnchorPoint, context.3dm 저장, context.json
  basemap_baker.py      (신규, RhinoCommon+RhinoDoc) BM:: 2D 레이어(해치·선·텍스트), _-Export .ai, K-only 후처리
  sheet_svg.py          (신규, Rhino 금지) 베이스맵 엔진(Seoungsu make_basemap_L 이식) + 시트 11장 + 표고·경사 2장 + CSV 조서
  context_builder.py    (신규, 오케스트레이터 = 엔진 API) run(request, progress, is_cancelled) → dict
  ── 개발 전용(python3) ──
  dev_database_builder.py (재사용) 필지 DB
  dev_context_builder.py  (신규) 139도엽 zip + GIS건물 zip → seoul_context.db
  dev_check_updates.py    (신규, ~10줄) 브이월드 새 판 확인
  dev_rhino_run.py        (재사용) Rhino 드라이버 실행
  dev_deploy.py           (신규, (이식) 배포 폴더
  dev_probe_*.py          (재사용) 08 실측 재현
```

import 관계(화살표 = import한다):

```
cmd_site ─► loader ─► context_builder ─► context_db, lot_db, building_height, vworld_buildings,
                                          context_geometry ─► utils ─► non_rhino_utils, constants
                                          context_baker   ─► utils
                                          basemap_baker   ─► utils, sheet_svg(라벨·범례 문자열 공유)
                                          sheet_svg       ─► non_rhino_utils, constants
```

규칙: `Rhino 금지` 모듈은 `python3 -m unittest`로 돈다. `context_geometry`는 RhinoCommon만 쓰고 `RhinoDoc`을 모른다(CLAUDE.md "로직 모듈은 지오메트리 객체를 만들어 돌려줄 뿐"). 문서를 만지는 것은 두 베이커뿐.

파일 수: 신규 로직 8 + dev 3. "스텁 금지"라 `bridges.py`·`alignment_qa.py` 같은 P1 모듈은 만들지 않고 `context_geometry.py` 안에 함수로 시작한다.

---

## 4. 데이터 흐름

```
[원천 zip]                       [dev 빌더, python3]                 [DB, 배포 번들]
수치지형도_5000/<도엽>.zip ×139 ─► dev_context_builder.py ──────────► seoul_context.db
  + sheets.csv(제작연도)            pyogrio(cp949) → .prj 5186 확인      features(theme/kind/sheet, GeoJSON+bbox)
AL_D010_11_<기준일>.zip(1.4 GB) ─►  → 코드→theme/kind 매핑(constants)    buildings(GIS 1순위 + ngii 보충)
건축HUB 벌크(P1)                    → 높이 규칙 A.4 사전 계산             data_sources / source_files
seoul_site.db(보유) ──────────────────────────────────────────────────► (그대로)

[런타임, Rhino CPython]
패널 PNU·반경 ─► context_builder.run
   1 lot_db.load(pnus)                      → target_lot GeoJSON, 중심 → origin(100 m 내림)
   2 context_db.load_in_bounds(bbox)        → buildings·features dict(세계좌표 5186)
     lot_db.load_parcels_in_bounds(bbox)    → near_lots
   3 (옵션) vworld_buildings.refresh(bbox)  → 메모리에서 buildings 덮어쓰기(세션 캐시)
   4 building_height.apply(buildings)       → height_m·HEIGHT_SRC·GRADE·채택 층수
   5 utils.get_local_pts(…, origin)         → 로컬 좌표(이 한 함수만 원점을 뺀다)
   6 context_geometry.build(…)              → ContextGeo{terrain_meshes{class→Mesh}, water_meshes, building_exts, lot_crvs, ref_items}
   7 context_baker.bake(doc, geo, meta)     → CTX:: 레이어 + UserString + EarthAnchorPoint → result/…/context.3dm + context.json
   8 basemap_baker.bake_and_export(doc, …) → BM:: 레이어(기본 off) → basemap_<축척>.ai
   9 sheet_svg.write_sheets(…)              → sheets/NN_*.svg, tables/*.csv (세계좌표 → 종이 mm, Rhino 무관)
  10 log.txt·결과 dict
```

---

## 5. 3dm 생성 설계 — RhinoCommon 베이크로 확정

### 5.1 왜 rhino3dm 쓰기가 아니라 베이크인가

| 관점 | rhino3dm 쓰기(07 추천) | **RhinoCommon 베이크(이 제안)** |
|---|---|---|
| 배포 PC 요구 | python3 + rhino3dm(+numpy/scipy/shapely) 또는 Rhino 안 `# r: rhino3dm` | 없음 |
| 지오메트리 SDK | 해석 프리미티브 교차뿐 → 삼각분할·투영을 직접 구현 | Delaunay·투영·압출·해치·텍스트 전부 있음(실측) |
| 문서 통합 | Import 1회(레이어·UserString 보존 확인, 00 §1) | 직접 추가. 00 실측대로 `WriteFile`로 3dm 사본도 남김 |
| 테스트 | 헤드리스 가능 | `dev_rhino_run.py` 드라이버(이미 있음, 오늘 5회 사용) + 순수 로직은 python3 unittest |
| 배치 생성 | 가능 | Rhino 떠 있어야 함 — 이 도구는 사용자가 Rhino 안에서 버튼을 누르는 도구라 요건이 아님 |

결론: 사용자 시나리오(Rhino 안 버튼 한 번)에 Import 단계가 끼어드는 이유가 없다. 3dm 파일은 "문서에 넣은 것의 사본"이다.

### 5.2 지형 TIN (`context_geometry.build_terrain`)

1. 입력: `features` theme=terrain kind=contour(`value`=표고)·spot(`value`)·**spot_struct 제외**(교량·입체교차부·인터체인지 5 m 버퍼 — 빌더가 미리 분류, §7). 범위 = 대상지 중심 반경 R + 여유 20 m.
2. 등고선 4 m 리샘플(`non_rhino_utils.resample_ring`, 순수 파이썬, 선형보간) → 반경 안 점만 → (x,y) 중복 제거(dict). 성수 R=500: 3,864점.
3. 범위 경계 원(64각) 점 추가, Z = 최근접 입력점 Z(간이; 경계는 어차피 잘려 보이지 않음).
4. 수면 폴리곤(§5.4) 경계를 2 m로 조밀화해 Z=수위로 추가(hydro-flatten 입력).
5. `Mesh.CreateFromTessellation(pts, [], Plane.WorldXY, False)` → 전체 TIN(Z 보존 실측).
6. 면 중심 분류(§5.3): `outside`(반경 밖, 버림) / `water` / `road` / `green` / `rail` / `terrain`. `Mesh.CreateFromFilteredFaceList(mesh, mask)`로 분류별 메시 분리 → 레이어 `CTX::Terrain`·`CTX::Roads`·`CTX::Green`·`CTX::Rail`(지상). 수면 내부 정점 Z는 수위로 고정(분류 전에 `Vertices.SetVertex`).
7. 표고·경사 시트(#12·#13)용 통계는 같은 면 배열에서 계산(법선 각 → 6단계) → `sheet_svg`에 삼각형+등급 목록으로 넘김.

`ponytail:` 제약변(브레이크라인·경계 보장) 없음. 겹치는 폴리곤 링을 `edges`로 넣으면 메시가 깨지는 것을 실측했으므로 v1은 조밀화 근사. 옹벽·제방 단차가 거슬리면 그때 `Mesh.CreatePatch(outerBoundary, …, innerBothSideCurves=브레이크라인)`을 성수 옹벽(`F0040000` 448건)으로 시험.

### 5.3 면 분류와 폴리곤 연산 — 불린 대신 Contains + 격자

- 1 km에서 bbox 전수 비교가 16 s였던 것은 `60k면 × 1,708폴리곤` 루프 때문. **50 m 격자 버킷**(`non_rhino_utils.GridIndex`: 폴리곤 bbox가 걸치는 셀에 등록, 면 중심은 자기 셀의 후보만 검사)으로 후보가 셀당 수 개로 줄어 1 s 안쪽이 된다(실측 기준 추정, M2에서 확인).
- 포함 판정은 순수 파이썬 ray-casting(실측 0.69 s)과 `Curve.Contains`(0.82 s)가 동급·동결과(2,549 vs 2,546). **순수 파이썬을 기본**으로 둔다 — python3 unittest가 되고 Rhino 밖 시트 생성(§6)과 같은 함수를 쓴다. 구멍(도넛 도로 필지)은 외곽 in AND 구멍 out.
- 폴리곤 클리핑·합집합은 하지 않는다. 건물·필지·도로면·수면은 **bbox가 범위와 겹치면 통째로** 가져오고, 3D에서 범위 경계는 TIN 면 제거로만 생긴다(건물은 반경 밖으로 삐져나와도 무방 — 필요하면 사용자 옵션 "반경 밖 건물 제외": 대표점 기준).
- 유일한 불린 후보는 P1 정합 QA의 '지목 도로 필지 합집합 경계' → `Curve.CreateBooleanUnion`(RhinoCommon, 실측 안 함) 또는 "다른 도로 필지 안에 있는 샘플점은 버림" 근사. P1에서 결정.

### 5.4 수면·도로·녹지·철도·교량

| 요소 | 폴리곤 원천(우선순위) | 처리 |
|---|---|---|
| water | features theme=water(수치지형도 E001/E003/E005) ∪ 필지 DB 지목 하천·구거·유지(`lot_db.load_parcels_in_bounds` 후 지목 필터) | 수위 = 폴리곤 경계 샘플 중 TIN 최저 Z(`ProjectPointsToMeshes`로 한 번에) → 내부 정점 Z 고정 → `water` 면을 `CTX::Water` 평면 메시로 분리(+0.02 m). UserString `NAME`·`LEVEL_M`·`LEVEL_SRC=terrain_min` |
| road | features theme=road kind=surface(A001) → 없으면 centerline `value`(도로폭)/2 버퍼(순수 파이썬 오프셋은 쓰지 않고 `Curve.Offset` 양쪽 + 끝 닫기, 폴백이라 품질 요구 낮음) → 없으면 지목 도로 필지 | 면 분류 `road`. 폭·차로수는 중심선 공간조인(가장 가까운 중심선, `Polyline.ClosestPoint`) → 메시 1개에 UserString 요약(WIDTH_M은 중심선별 커브 객체에) |
| green | 지목 공원·임야 + overlays 공원·녹지 + features theme=green(D001) | 면 분류 `green` |
| rail | features theme=rail(지상 면 A0160024 / 선 A015x) | 지상 = 면 분류 `rail`, 지하 = 커브만(점선 선종류) P1 |
| bridge | features theme=bridge(A007·A0093351·A0063321) | 폴리곤 정점 양끝 접속부 Z 선형보간 → `Mesh.CreateFromClosedPolyline` 상판 + 두께 1.5 m 압출(`Extrusion.Create`) P1 |

### 5.5 건물 (`context_geometry.build_buildings`)

1. `building_height.apply`(순수 파이썬)가 `height_m`·`HEIGHT_SRC`·`HEIGHT_GRADE`·`GRND_FLR`·`FLR_SRC`·`attr_flag`·`status`를 dict에 채운다(A.4 규칙 0~7, `constants.FLOOR_HEIGHT_MODEL`). DB 빌더가 같은 함수를 미리 돌려 `buildings` 컬럼에 넣어 두고, 런타임은 API 갱신분에만 다시 돌린다 — **같은 모듈, 두 곳에서 import**(python3·Rhino 양쪽에서 도는 모듈이라 가능).
2. 발자국 링(로컬 좌표) 전체 정점을 `ProjectPointsToMeshes([terrain_all], pts, (0,0,-1), tol)` 한 번에 → 동별 최저 Z(투영 실패 정점은 무시, 전부 실패면 Z=주변 건물 중앙값 + 경고). 고저차 >3 m면 `HEIGHT_SRC`에 `~slope`.
3. 외곽 링 **CW 정규화**(`non_rhino_utils.ring_orientation`, 신발끈 부호) 후 `PolylineCurve`(Z=최저 Z) → `Extrusion.Create(crv, Plane(Point3d(0,0,z_min), ZAxis), height_m, True)`(Rhino 8 평면 명시 오버로드, 방향 문제 없음 — 실측 Z 범위 12→42 양수 방향) → 구멍은 `AddInnerProfile`. `None`이면 `Brep.CreatePlanarBreps` → `Brep.CreateFromOffsetFace`로 1회 폴백, 그래도 실패면 건너뛰고 log(건물 id). 멀티폴리곤은 파트별 객체.
4. 철거(`status=demolished`)는 옵션: 제외 / 회색 점선(레이어 `CTX::Buildings::demolished`).
5. UserString: `BLD_ID PNU PNU_SRC GRND_FLR FLR_SRC UGRND_FLR HEIGHT_M HEIGHT_SRC HEIGHT_GRADE USABILITY USEAPR_DAY BLD_NM STATUS DEMOL_DAY SRC`(API 유래면 `"출처 ⓒ 국토교통부·브이월드"`).

### 5.6 원점·단위·좌표

- 원점 = 대상지(여러 필지면 합집합 bbox) 중심을 100 m 단위로 내림(E,N). **적용 위치는 `utils.get_local_pts(coords, origin)` 하나**(모든 GeoJSON→Point3d 변환이 이 함수를 거친다). 이유: `Mesh.Vertices`가 Point3f라 세계좌표 메시는 0.03~0.06 m 오차 — 베이크 직전 이동으로는 늦다. 이것이 CLAUDE.md "원점 이동은 베이커 한 곳"의 정신(한 곳)을 지키되 위치를 옮기는 유일한 변경이며, CLAUDE.md 문구를 그에 맞게 고친다.
- 단위: 로직은 m. `context_baker`가 `RhinoMath.UnitScale(Meters, doc.ModelUnitSystem)`(기존 베이커 `_get_model_unit_scale` 이식)로 `Transform.Scale`을 **베이크 직전 복제본**에 적용. Z도 같이 환산.
- 기록: ① `CTX::Ref` 원점 Point + TextDot, UserString `CRS=EPSG:5186 ORIGIN_E ORIGIN_N RADIUS_M SRC_SHEETS BUILT_AT TRANSFORM VDATUM …`(A.1 표 그대로) ② `doc.EarthAnchorPoint`(RhinoDoc 속성 존재 [로컬 RhinoCommon.xml]; 위경도는 `non_rhino_utils.get_wgs84_from_tm`, `ModelNorth=(0,1,0)`) ③ `context.json` 사이드카. `File3dm.Strings`는 쓰지 않음(00/07 상충).
- 정북 +Y. 수직기준 메타 문자열은 deliverables A.3 그대로.

### 5.7 레이어·베이크·저장 (`context_baker`)

- 레이어 트리 `CTX::Site/Parcels/Buildings/Terrain/Water/Roads/Green/Rail/Bridges/Zoning/QA/Ref`, 색은 `constants.CTX_LAYERS = {"Buildings": ((128,128,128), "Extrusion"), …}`. 생성은 기존 베이커 `_ensure_layer`(FindByFullPath → IsDeleted 확인 → Add) 이식.
- 이전 결과 정리: 같은 `LOT_KEY` UserString을 가진 객체만 삭제(기존 베이커 `_clear_baked` 패턴). 사용자가 그린 것은 건드리지 않음.
- `doc.Views.RedrawEnabled=False` … `Redraw()` 한 번(실측 0.08 s @ 2k동이라 체감 없음).
- 저장: `doc.WriteFile(path, FileWriteOptions{WriteSelectedObjectsOnly, SuppressDialogBoxes, UpdateDocumentPath=False})`에 이번 베이크 id만 선택(기존 베이커 `_save_document` 이식). 파일 단위 = 문서 단위(mm 문서면 mm) — `context.json`에 `model_unit` 기록. m 단위 사본이 꼭 필요하면 `RhinoDoc.CreateHeadless`(존재 확인)에 m로 다시 베이크 — P2.

### 5.8 성능 예산(반경 500 m / 1 km, 실측 기반)

DB 질의 0.3/0.8 s(추정, bbox 인덱스) · JSON→점 0.2/0.8 s · TIN 0.01/0.03 s · 분류 0.7/≈1 s(격자) · 투영 0.06/0.25 s · 압출 0.2/0.75 s · 베이크 0.1/0.4 s · 3dm 저장 1/3 s(추정) · 해치 0.2/0.9 s · `.ai` 0.4/1.5 s · SVG 13장 1/3 s(추정) → **합계 ≈ 4 s / ≈ 12 s**. 추정 항목은 M2·M4에서 실측해 표를 갱신한다.

---

## 6. 베이스맵·시트 생성 설계

### 6.1 2D 베이스맵 레이어 (`basemap_baker`)

- 같은 로컬 좌표·같은 문서에 `BM::NN_english / 한글` 레이어(B.2 순서, 기본 **off**·잠금)로 그린다. z=0 평면.
  - 면(01 water·02 green·03 road_surface·07 bldg_low/mid/high/tower): `Hatch.Create(List[Curve], solid_index, 0, 1, tol)` — **solid_index는 `FillType==Solid`인 패턴을 찾는다**(한국어 UI "채우기", 영어 "Solid"; 없으면 `HatchPatterns.Add(Defaults.Solid)`). 톤은 레이어 색(K10~K45 → 회색 RGB)으로.
  - 선(04 road_edge·05 center·06 rail·08 parcel·09 contour·10 site·11 zoning·13 grid): PolylineCurve, 선두께는 레이어 PlotWeight(mm)로 지정 — `.ai`에 선두께가 실리는지 M5에서 확인(실측 파일에 `w` 연산자 존재).
  - 라벨(08b 지번·12 labels): `TextEntity`. **한글 손상 가능성** → §6.4.
- 범위: 프레임 bbox(용지×축척, 중심)와 반경 bbox 중 큰 쪽으로 한 번에 질의(`context_builder`가 bbox 하나로 통합). 프레임 사각형 `00_frame`(register rect)도 커브로.

### 6.2 `.ai` 내보내기 — 확정 문자열 (실측)

```
_-SetActiveViewport Top                       # 또는 doc.Views.ActiveView = doc.Views.Find("Top", False)
(BM:: 레이어 객체만 RhinoObject.Select(True) — Objects.Select(List[Guid])는 해치에 실패했음)
_-Export "<result>/basemap_3000.ai" _PreserveUnits=_Yes _Unit=_mm _RhinoScale=<S> _AIScale=1 _HatchesAsSolidFills=_Yes _OrderLayers=_Yes _Color=_CMYK _Enter
```

- `S` = 축척 분모 × (문서 1단위의 mm 수)⁻¹ … 즉 문서 mm면 `S=3000`, 문서 m면 `S=3`. 실측: 300 m 정사각형(mm 문서, S=3000) → `%%BoundingBox` 284 pt = 100.2 mm ✓.
- 옵션은 **sticky**(이전 값이 남음)라 매번 전부 명시한다. 값 토큰은 `_mm`(`_Millimeters`는 거부).
- 레이어 이름은 FullPath(`BM::07_bldg_low`)로 `(…) Ln`에 들어간다. Illustrator에서 `BM::` 접두가 거슬리면 `_NC` 제외 규칙과 함께 파일 후처리(순수 텍스트, `%AI5_BeginLayer` 블록 단위)로 이름을 바꾸고 `_NC` 레이어 블록을 지운다.
- **K-only**: `_Color=_CMYK`는 (0.37,0.37,0.37,0.37)처럼 4채널 동일값을 쓴다. 후처리 1줄: `^(\S+) (\S+) (\S+) (\S+) k$` → `(1−k) g`(AI3 회색 연산자). 또는 Illustrator "Convert to Grayscale" 1회. 기본은 후처리.
- 활성 뷰가 Top이 아니면 edge-on 스냅샷이 된다(첫 실측 bbox 높이 2 pt) → 반드시 Top 전환 후 복귀.

### 6.3 시트 SVG·CSV (`sheet_svg.py`, Rhino 무관)

- Seoungsu `make_basemap_L.py`의 `path_of / geom_paths / save_svg` 패턴을 geopandas 없이 이식: 입력은 `context_db`·`lot_db`가 준 GeoJSON dict, 변환은 `mm = (E − E0)/S × 1000`(x), `(N0 − N)/S × 1000`(y). 용지(A1/A0/커스텀)·축척·중심 세 값(06 frame.py 요건).
- 한 시트 = 베이스(01~04·06·10 회색) + 주제 레이어 1 `<g id>` + 범례 + 수치 카드 + 자료기준·출처·좌표계·정합·기준일 경고 5줄(C 공통 ①~⑤; 문자열은 `data_sources`·`source_files`에서 자동).
- 시트 1~11 P0, 12·13(표고·경사)은 `context_geometry`가 넘긴 삼각형+등급으로 그린다(Rhino 안에서 계산된 값을 순수 모듈이 그리는 유일한 경우 — 입력은 리스트라 테스트 가능).
- 조서 CSV(`parcels.csv / buildings.csv / sheet_stats.csv / height_src_stats.csv`)는 `csv` 표준 라이브러리, UTF-8 BOM(엑셀).

### 6.4 베이스맵 라벨(한글) 결정

실측: Rhino `.ai`는 한글을 UTF-8 바이트 그대로 PostScript 문자열에 쓰고 폰트를 `ArialMT`로 적는다. Illustrator 레거시 파서의 해석은 **확인 필요**(M5 첫 항목). 깨지면 ① `12_labels`·`08b_parcel_no`는 `.ai`에서 빼고 같은 프레임의 `labels.svg`(sheet_svg가 어차피 만든다)를 Illustrator에 Place/JSX ② 또는 `TextEntity.Explode()`로 아웃라인 커브(라이브 텍스트 포기). 기본값은 ①.

---

## 7. DB 빌더 설계 (`dev_context_builder.py`)

### 7.1 입력 실측

- 도엽 zip 137개 수령(246 MB, `sheets.csv` 137행, `year` 비어 있음 — 플랫폼 목록에서 채워야 함), 1도엽 ≈ 46 MB 비압축·210파일·42레이어. 성수 37705072: 건물 12,426·도로면 2,789·중심선 5,443·등고선 126·표고점 786·하천 9, pyogrio 읽기 3.4 s, 주요 7레이어 GeoJSON 합 **6.3 MB** [로컬]. 139도엽 × ≈7 MB ≈ **1.0 GB**(features+ngii 건물 전부 넣을 때 상한).
- GIS건물 서울 `AL_D010_11_20260909.zip` 136 MB(압축) → dbf **1.26 GB**·shp 130 MB [로컬]. 행 수 확인 필요(≈ 60~100만 추정, 08 §7-23).

### 7.2 적재 순서

```
0  backup: cp data/seoul_context.db data/backup/seoul_context_<날짜>.db (있을 때)
1  schema: data_sources·source_files·buildings(+sheet 컬럼)·features, bbox B-tree 인덱스, PRAGMA journal_mode=OFF, synchronous=OFF (빌드 중)
2  GIS건물 전체본: pyogrio.read_dataframe(zip, skip_features/max_features 10만 행 청크, encoding cp949) → .prj 5186 확인(Y 540~565k)
   → 컬럼 매핑(A1..A28) → norm_date → building_height.apply 사전 계산(층수만으로; ngii 보완은 3단계 후 재계산)
   → 한 트랜잭션: DELETE WHERE source_id='gis_bldg' → INSERT. pnu: A2 그대로, 결측·19자리 초과·parcels 미존재만 대표점 bbox 질의 + shapely contains(청크당 parcels 조회)
3  도엽 139개 순차(도엽 = 트랜잭션 단위, sha256 같으면 skip):
   3a 42레이어 중 constants.NGII_LAYER_MAP에 있는 코드만 읽기(등고선·표고점·도로면·중심선·수계·녹지·철도·교량·입체교차·인터체인지·옹벽·지명·건물)
   3b spot vs spot_struct: 교량 A007·입체교차 A009·인터체인지 A010 폴리곤 5 m 버퍼(shapely, 도엽 안에서만) 안 표고점 → kind='spot_struct'
   3c features INSERT(theme/kind/code/name/value/attrs_json/sheet/geometry_json/bbox), dissolve 안 함
   3d 건물 매칭: DB buildings를 도엽 bbox로 읽어 STRtree(shapely) → 수치지형도 건물 대표점 포함 → grnd_flr=0이면 층수, 아파트·연립 층수≥grnd_flr+3이면 치환(flr_src='topo'), ngii_kind/use 기록, 높이 재계산
       미매칭 → src_key='ngii:<UFID>', sheet=<도엽>으로 INSERT (무벽·가건물 포함, ngii_kind로 런타임 필터)
   3e source_files INSERT(sheet, sha256, listed_date=sheets.csv year)
4  ANALYZE; VACUUM(옵션); PRAGMA 복원
```

- 시간: 도엽당 읽기 3.4 s + 변환·INSERT ≈ 5~8 s → **139도엽 15~20분**; GIS건물 1.26 GB dbf 청크 읽기 ≈ 5~10분(확인 필요). 전체 30분 안쪽, 메모리 도엽 1개 + 건물 청크 10만 행 ≈ 1 GB 이내.
- 중복: 도엽 경계에서 잘린 도로면·하천면은 그대로(런타임이 분류로 흡수). 건물은 경계 분절이 다른 UFID로 두 번 들어올 수 있음(**확인 필요**, 성수 4도엽 경계에서 셈) → 대표점이 도엽 bbox 밖이면 버리는 규칙으로 1차 방어.
- 도엽 교체: `DELETE FROM features WHERE source_id=? AND sheet=?` + `DELETE FROM buildings WHERE src_key LIKE 'ngii:%' AND sheet=?` → 3a~3e 재실행. 이를 위해 `buildings.sheet`(ngii 행만) 컬럼을 data_sources.md §2.2에 추가한다(작은 변경).
- 좌표계: 모든 입력 `.prj` 판독 → 5186 아니면 `pyproj.Transformer.from_crs(src, 5186, always_xy=True)` 기본 경로만(08정합), Y 범위 교차 확인 실패 시 중단.
- 라이선스·기준일: `data_sources` 행에 두 창구 표기, `note`에 transform 문자열; `reference_date`는 A22(건물)/sheets.csv year(지형).

---

## 8. 엔진 API (`context_builder.run`)

```python
def run(request, progress=None, is_cancelled=None, doc=None):
    # type: (dict, callable, callable, object) -> dict
```

### 8.1 요청 dict

```json
{
  "pnus": ["1120011500103150001"],              // 필수, 1개 이상 (여러 필지 = 합친 대상지)
  "lot_name": "성수동2가 315-1",                 // 결과 폴더명, 없으면 첫 PNU
  "radius": 500,                                 // m, 기본 constants.CONTEXT_RADIUS=500
  "range_shape": "buffer",                       // buffer(대지 경계 버퍼) | circle(중심 원) | rect
  "outputs": ["context_3dm", "basemap_ai", "sheets", "tables"],   // 부분 실행 허용
  "basemap": {"paper": "A1", "scale": 3000, "landscape": true, "center": null},
  "options": {
    "topo_only_buildings": true,                 // src_key ngii:* 포함
    "temporary_buildings": false,                // 무벽·가건물
    "demolished": "dashed",                      // dashed | exclude
    "refresh_buildings_api": false,              // LT_C_BLDGINFO 세션 갱신(키 필요)
    "vworld_api_key": null,
    "contours_in_outputs": true                  // 온라인 공유용이면 false(B.4)
  },
  "result_root": null                            // 기본 <루트>/result
}
```

### 8.2 응답 dict

```json
{
  "ok": true, "cancelled": false,
  "result_dir": ".../result/20261007/성수동2가_315-1",
  "files": {"context_3dm": "...", "context_json": "...", "basemap_ai": "...", "sheets": ["..."], "tables": ["..."], "log": "..."},
  "origin": {"e": 205000.0, "n": 549300.0}, "radius": 500, "bbox": [204500, 548800, 205500, 549800],
  "counts": {"target_lots": 1, "near_lots": 2345, "buildings": 2174, "buildings_skipped": 1, "terrain_faces": 7247, "road_faces": 2546, "water_faces": 0},
  "stats": {"height_src": {"height": 0.31, "grnd_flr": 0.46, "topo_flr": 0.19, "default": 0.04}, "grade_ab_ratio": 0.77,
            "alignment": null, "data_age": {"gis_bldg": {"ref": "2026-09-09", "months": 0.9, "level": "ok"}, "ngii_5000": {...}}},
  "warnings": [{"code": "building_extrude_failed", "text": "...", "ref": "bldg:1120011500103150001-3"}],
  "error": null,                                  // ok=false면 {"code", "text", "traceback"}
  "seconds": 4.2
}
```

### 8.3 진행률·취소·오류 규약

- `progress(step, done, total, text)` — `step ∈ {"lot","query","api","height","terrain","buildings","bake","save","basemap","sheets","tables"}`, `done/total`은 단계 안 진행(건물 100동마다 등), `text`는 사용자용 한 줄. 컨트롤러(`cmd_site`)는 이를 `panel_host.push({"type":"progress",…})`로 보내고 **`Rhino.RhinoApp.Wait()`** 를 호출해 UI를 펌프한다(RhinoCommon `RhinoApp.Wait` 존재 확인). 엔진은 UI 스레드에서 돈다(별도 스레드 금지 — RhinoDoc 접근).
- `is_cancelled()` — 컨트롤러가 JS "cancel" 명령(Wait 중 flush되어 들어옴) 또는 `RhinoApp.EscapeKeyPressed` 이벤트로 플래그를 세운다. 엔진은 단계 경계와 긴 루프 안에서 확인, `CancelledError`를 던지고 `run`은 `ok=False, cancelled=True`로 돌려주며 **이미 베이크한 객체는 되돌린다**(`doc.Objects.Delete` 이번 id).
- 경고: 건너뛴 피처(PNU·건물 id·도엽)는 `warnings`와 `log.txt` 둘 다. 오류 코드 최소 집합: `pnu_not_found`, `context_db_missing`, `no_terrain_points`, `doc_unit_invalid`, `api_invalid_key`, `export_failed`.
- 중복 실행: 같은 `lot_name`의 이전 객체는 베이크 직전에 `LOT_KEY`로 지운다. 결과 폴더는 `<날짜>/<대상지>/`에 덮어쓴다(deliverables §E).

---

## 9. 테스트 전략

| 층 | 도구 | 대상 | 고정 데이터 |
|---|---|---|---|
| 순수 로직 | `python3 -m unittest discover tests` | `non_rhino_utils`(point_in_polygon·GridIndex·resample·orientation), `building_height`(A.4 규칙표 케이스), `context_db`(bbox 질의·theme 필터), `sheet_svg`(mm 변환·시트 1장 생성·CSV 헤더), `vworld_buildings`(응답 파싱, 네트워크 모킹) | `tests/fixtures/seongsu_context.db` — `dev_context_builder.py --sheets 37705072,37705073,37705082,37705083 --buildings-bbox …`로 만든 소형 DB(수십 MB, gitignore, 생성 명령은 README) |
| Rhino 지오메트리 | `python3 scripts/dev_rhino_run.py tests/rhino/driver_*.py` | `driver_terrain.py`(TIN·분류·수면 Z 고정, 면 수·Z 범위·IsValid 단언, 시간 기록) · `driver_buildings.py`(투영·압출 수·실패 목록) · `driver_full_run.py`(`context_builder.run` 전체, 결과 dict JSON과 파일 존재·크기 단언) · `driver_export_ai.py`(bbox 284 pt 검산·레이어명·`f` 연산자 수) | **고정 대상지 PNU `1120011500103150001`**(성수동2가 315-1, 대 1,930.7 ㎡, 준공업지역; 반경 500 m·1 km가 성수 4도엽 안) → `constants.TEST_CONTEXT_PNU` |
| 사람 확인 1회 | Illustrator | 한글 라벨, 레이어 분리, 1:3000 치수(100 mm 검산 사각형을 `00_frame`에 넣어 둔다), K-only | M5 |

오늘 만든 벤치 드라이버(`/tmp/udt_bench/driver_bench.py`·`driver_export4.py`)를 `tests/rhino/`로 옮겨 첫 드라이버로 삼는다.

---

## 10. 배포

```
UrbanDesignTool/                 (dev_deploy.py 결과, 기존 방식)
  설치방법.txt, UrbanDesignTool.rui
  scripts/ loader.py cmd_install.py cmd_site.py site_ui.html vendor/   (평문)
           *.pyc (로직 모듈, Python 3.9 컴파일)
  data/    seoul_site.db (2.0 GB)  seoul_context.db (≈1.0~1.5 GB, 확인 필요)
  result/  (비어 있음)
```

- 크기 ≈ 3.5 GB → USB·사내 공유 폴더. 압축 전달 시 SQLite는 50~60 %로 준다.
- 첫 실행 패키지 설치 시간: **0 s**(pip 없음). 첫 실행 체감 = DB 열기 + 질의 ≈ 1 s.
- `.pyc` 3.9 전용. Windows에서 `dev_deploy.py`를 돌릴 일은 없고(Mac에서 만든다), `.pyc`는 OS 중립.
- Windows 주의: `sqlite3` rtree 없음(설계상 미사용), WebView2 브리지 quirk는 `panel_host.py`가 이미 처리. `_-Export` 옵션 토큰은 영문이라 로케일 무관(한국어 UI에서 실측).

---

## 11. 구현 순서 (마일스톤)

| # | 내용 | 보이는 결과 | 규모 |
|---|---|---|---|
| M1 | `dev_context_builder.py`(성수 4도엽 + GIS건물 성동구 bbox) · `context_db.py` · `building_height.py` · `non_rhino_utils` 추가 · unittest | `python3 -m unittest` 통과, `tests/fixtures/seongsu_context.db`, 성수 315-1 반경 500 m 건물 2,1xx동·높이 출처 비율이 터미널에 찍힘 | 3~4일 |
| M2 | `utils.py` · `context_geometry.build_terrain` · `context_baker`(Terrain/Water/Roads/Green + Ref) · `driver_terrain.py` | Rhino에 성수 지형 메시가 레이어별로 뜬다. 분류 격자 1 km 1 s 확인, 수면 평탄 확인 | 3일 |
| M3 | `build_buildings` · Site/Parcels 커브 · UserString · `context.3dm`+`context.json` 저장 · `driver_full_run.py` | 3dm 컨텍스트 완성본 1개(성수), log.txt에 건너뛴 건물 id | 3일 |
| M4 | `context_builder.run`(진행률·취소·오류) · `cmd_site.py` 연결(패널 워크플로의 메시지 계약 적용) | 패널 버튼 → 진행률 → 문서에 컨텍스트. 취소 버튼 동작 | 2~3일 |
| M5 | `basemap_baker`(BM 레이어·해치·텍스트·export·K-only 후처리) · Illustrator 1회 확인 | `basemap_3000.ai`를 Illustrator에서 열어 레이어·100 mm 검산·한글 판정 → 라벨 경로 확정 | 2~3일 |
| M6 | `sheet_svg.py`(엔진 + 시트 1~13 + CSV 4종 + 자료기준 5줄) · unittest | `result/<날짜>/<대상지>/sheets/*.svg 13장 + tables/*.csv` | 5~6일 |
| M7 | 139도엽 전체 적재 + GIS건물 서울 전체 + `source_files` + 기준일 경고 + `dev_deploy.py` + Windows 노트북 설치 | 서울 임의 PNU로 동작, 배포 폴더 1개, Windows 첫 실행 성공 | 3일 + 적재 30분 |
| M8 (P1) | VWorld 세션 갱신 · 교량/철도 · 정합 QA 레이어 · 1 km 성능 재측정 · Zoning 커브 | `CTX::QA::cadastre_mismatch`, 교량 슬래브, API 갱신 n동 로그 | 1~2주 |

M1~M7 ≈ 4~5주(1인). M1·M6은 Rhino 없이 진행 가능해 Rhino 드라이버 대기와 병행된다.

---

## 12. 위험과 대안

| 위험 | 근거·징후 | 대안(비용) |
|---|---|---|
| `.ai` 한글 라이브 텍스트 손상 | 파일에 UTF-8 바이트 + ArialMT(실측), 06 포럼 보고 | 라벨을 SVG로 분리(§6.4, 반나절) |
| 분류 성능이 1 km에서 커짐 | bbox 전수 16 s 실측 | 격자 버킷(§5.3, 반나절). 그래도 느리면 `Curve.Contains`→ 격자 동일 적용 |
| 평삼각형·경계 톱니(제약변 없음) | 07 §1.3, 08정합 §2.4 | 표고점 포함으로 1차 해결(08). 단차가 문제면 `Mesh.CreatePatch` 브레이크라인 시험(1~2일) |
| `Extrusion.Create` 실패 발자국 | 실측 8,517동 중 2 | 건너뛰고 경고(CLAUDE.md "예외는 건너뛴다"). 늘면 `Brep.CreatePlanarBreps` 폴백 |
| Rhino UI가 실행 중 멈춘 듯 보임 | UI 스레드 실행 | `RhinoApp.Wait()` 펌프 + 진행률(§8.3). 4~12 s라 체감 작음 |
| Windows Rhino의 `CreateFromTessellation`·export 토큰 차이 | Mac만 실측 | M7 Windows 노트북에서 `driver_terrain`·`driver_export_ai` 재실행(30분) |
| DB 1~1.5 GB 추가 | 7.1 추정 | 등고선·도로면만 남기고 ngii 건물 미매칭분만 저장(이미 설계), 중심선 attrs 축약; 필요 시 features를 도엽별 압축 GeoJSON(zlib BLOB, `zlib` 표준)으로 40 % 절감 |
| 도엽 경계 건물 중복 | 미확인 | 대표점-도엽 bbox 규칙 + 성수 4도엽 경계 집계(M1) |
| 폴리곤 불린이 결국 필요(정합 QA·합집합) | P1 | `Curve.CreateBooleanUnion` 실측 → 느리면 샘플 제외 근사 → 그래도면 그 단계만 `dev_*`로 사전 계산해 DB에 저장 |
| RhinoCommon Delaunay가 특정 입력(중복·공선)에서 None | 실측 범위 밖 | (x,y) 중복 제거는 이미 함. None이면 1 mm 지터 후 재시도 → 그래도면 `# r: scipy` 비상 경로(1줄, 휠 확인됨) |
| `RedrawEnabled=False` 중 예외로 화면이 멈춤 | 기존 베이커 선례 | `try/finally`로 복원(베이커 공통) |

**결정 요청 사항(심사자용)**: ① deliverables §A.5·07 §5.3의 "rhino3dm writer + Import"를 "RhinoCommon 베이크 + WriteFile"로 바꿀 것 ② CLAUDE.md "원점 이동은 베이커 한 곳"을 "원점 결정은 빌더, 적용은 `utils.get_local_pts` 한 곳"으로 ③ `buildings.sheet` 컬럼 추가(data_sources.md §2.2).
