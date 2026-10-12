# 07. 도시 컨텍스트 3D 모델 생성 기술 조사 — Rhino 8 CPython / rhino3dm

- 작성일: 2026-10-07 (모든 URL 접근일 동일). 검증 반영 개정: 2026-10-07 (문서 끝 "검증 이력" 참조)
- 대상 환경: macOS, Rhino 8.35(로컬 설치 확인), Rhino 8 내장 CPython 3.9.10, 시스템 `/usr/bin/python3` 3.9 + geopandas 1.0.1 / shapely 2.0.7 / scipy 1.13.1 / pyproj / rhino3dm 8.35.0(설치 확인)
- 조사 방법: 1차 출처(RhinoCommon 공식 API 문서, McNeel 포럼 스태프 발언, rhino3dm 저장소·공식 문서, VWorld API 레퍼런스, USGS·SIG3D·OSM 표준 문서, EPSG 레지스트리) + **로컬 실측**(성수 1:5000 수치지형도 4도엽 SHP, VWorld 건물 캐시 **78,862동(서울 77타일)**, rhino3dm 8.35.0 쓰기 벤치마크, scipy Delaunay 벤치마크). developer.rhino3d.com의 API 페이지는 JS 렌더링이라 본문 수집에 실패했으므로, 동일 내용의 **로컬 Rhino 8.35 설치본 `RhinoCommon.xml`**(공식 API 주석 원문)을 1차 문서로 사용했다 [S1].
- 표기: `[S#]` = 문서 끝 출처 목록. "로컬 실측"은 이 조사에서 직접 돌린 측정값. **확인 필요** = 1차 출처를 직접 열어 확인하지 못한 항목. 벤치마크 수치는 실행마다 ±30% 흔들리므로 **범위·근사값**으로 읽는다.

---

## 0. 요약 — 결론과 추천

| 항목 | 추천 | 핵심 근거 |
|---|---|---|
| 전체 구조 | **지오메트리 계산은 Rhino 밖(numpy·shapely·scipy)에서 하고 rhino3dm으로 .3dm을 쓴다. 플러그인 버튼은 그 파일을 Import만 한다.** 코드 경로 하나, pytest로 테스트 가능, 배치 생성 가능. | rhino3dm 8.35.0 cp39 macOS 휠 존재·API 전수 검증(레이어·유저스트링·단위·EarthAnchorPoint·Extrusion·Mesh·블록) [S13][S15][S29]; 3만 동+36만 정점 지형을 **약 3–4 s / 약 40 MB**로 기록(2회 실측 2.8–4.4 s, 38.8–40.2 MB) [S29] |
| 지형 | 등고선(`등고수치`)+표고점(`수치`)을 4 m로 리샘플 → **Delaunay TIN**(scipy, 또는 브레이크라인·경계 보장이 필요하면 `triangle` CDT) → Mesh. 격자 DEM이 있으면 격자→쿼드 메시 직접 구성. 범위 자르기는 **메시 전에 입력 점·선을 shapely로 클리핑**. | 성수 4도엽(≈4.4×5.6 km) 등고선 63,905 정점 → 4 m 리샘플 **약 12만 점**(중복 제거 방식에 따라 120,665–120,904), scipy Delaunay 0.3 s [S27][S30]; Rhino 안이라면 `Mesh.CreateFromTessellation`(Rhino 6 RhinoCommon부터 — 포럼 스태프 발언 기준, XML에 `<since>` 없음; 제약변 지원) 또는 `Mesh.CreatePatch`(since 6.0, 외곽 경계 트림·브레이크라인 지원) [S1][S2] |
| 수계 | 수면 폴리곤 경계를 **제약변**으로 넣고 내부 정점을 수위로 고정 = hydro-flattening. 수위는 ① 한강홍수통제소 Open API 관측소 제원·실측 수위(`GDT` 영점표고, `PFH` 계획홍수위) ② 없으면 제방 최저 표고 | USGS 정의 "flat and level from bank to bank" [S5]; 한강홍수통제소 API 레퍼런스 [S50] |
| 건물 | **Extrusion**(경량 압출). 발자국 정점을 지형에 투영해 **최저 표고**에 바닥을 두고 위로 압출. 높이 = `height>0`이면 height, 아니면 `지상층수 × 3.2 m`(서울 캐시 78,862동 실측 중앙값 3.25 m), 층수도 없으면 수치지형도 `층수`(샘플 100% 채움), 지하층은 제외. **height 결측 70%의 1순위 보완 후보 = 건축HUB 건축물대장 표제부 API**(필드명 확인 필요) | SIG3D 모델링 가이드: 바닥면 표고 = 지형 교선의 최저 절대고 [S6]; VWorld 캐시 78,862동 중 height≤0 **70.0%**, 둘 다 있는 건물의 height/grnd_flr 중앙값 **3.25 m** [S28]; OSM 렌더러 기본값 3 m/층 [S8]; 경량 압출 "메모리 적게, 메싱 빠르게, 저장 작게" [S9]; 건축HUB API 무료·이용허락 제한 없음 [S48] |
| 도로 | 1순위 수치지형도 **도로경계 폴리곤(N3A_A0010000)**, 2순위 도로중심선(N3L_A0020000)의 `도로폭`/2 버퍼(샘플 100% 채움), 3순위 지목 '도로' 필지. 지형 위 올리기는 **하나의 TIN에 도로·수면·녹지 경계를 넣고 면을 분류**. 경계를 **제약변(CDT)**으로 넣으면 갭·z-fighting 없음; 무제약 scipy 경로는 경계 조밀화로 근사(미세 톱니 가능). Rhino 안이라면 `Mesh.SplitWithProjectedPolylines`(Rhino 7+) | 로컬 실측 [S27]; `SplitWithProjectedPolylines`·`ProjectPointsToMeshes`·`Curve.ProjectToMesh` API 원문 [S1] |
| 교량·철도·입체시설 | 수치지형도 1:5000의 `A0070000` 교량, `A0090000` 입체교차부(고가차도 `A0093351`·지하차도 `A0093352`), `A0110020` 터널, `A0131122` 정거장, `A0150000` 철도(지하철 지하부 `A0151115`·지상부 `A0151116`, 지하철역 출입구 `A0151224`), `A0160024` 철도경계, `A0171119` 철도중심선을 사용(4.1절). **VWorld 2D API 158개 서비스(16페이지 전수 확인)에는 교량·철도·지하철 전용 레이어가 없다** | 저장소 코드표 [S37]; VWorld 2D 목록 [S36] |
| 원점·단위·정북 | 단위 m, 허용오차 0.001. **대지 중심(또는 도엽 모서리의 100 m 반올림 값)으로 원점 이동**, 오프셋을 `File3dm.Strings`(문서 사용자 문자열)와 `EarthAnchorPoint.Description`에 기록. 정북 = +Y, 성수에서 도북-진북 수렴각 0.034°라 무시 가능. 입력 SHP는 `.prj`를 읽어 EPSG:5186이 아니면 pyproj(`always_xy=True`)로 변환 | Rhino 도움말 "모델 크기 100,000 단위 이내" [S22]; EPSG:5186 좌표가 성수에서 (E≈204,922, N≈549,467) [S24][로컬]; 원점 멀면 디스플레이 메시 단정밀도 문제 [S19]; 기존 이미 `origin_easting/northing` 차감 방식 사용 [S41] |
| 대량 처리 | Rhino 안에서 베이크할 때는 `doc.Views.RedrawEnabled=False`, rhinoscriptsyntax 대신 RhinoCommon, Extrusion 사용. 블록은 건물에는 효과 없음(모두 다른 형상), 가로수·가로등 같은 반복물에만. 구 단위 이상은 도엽/행정동으로 파일을 쪼개고 링크 블록으로 조립 | 포럼(McNeel 스태프) "Disabling redraw always increase performance (drastically so)" [S12]; 경량 압출은 "tens of thousands of objects" 모델을 위해 도입 [S9]; 블록 인스턴스는 변환 비용으로 표시 성능 이득이 상쇄될 수 있음(Pascal Golay) [S11]; 먼 원점 대응 워크플로(링크 블록) [S19] |

**미확인(확인 필요)**: 국토지리정보원 DEM 격자 해상도·5 m 현행 제공 조건, 건축HUB 표제부 응답 필드명(높이·지상층수·지하층수), 서울 1:1000 수치지형도의 서울 전역 제공 범위, 공식 3D 건물 모델(국토지리정보원 3차원 공간정보·VWorld 3D) 제공 형식, 도로명주소 도로구간 `ROAD_BT` 공식 컬럼 정의, 표준노드링크 `LANES`/`ROAD_RANK` 공식 정의(its.go.kr 인증서 오류), S-Map "2008년 이전 층당 3 m" 관행의 1차 출처, 건축법 시행령 제119조 원문, 3차원국토공간정보구축작업규정의 건물 기준면 규정. → 9절.

---

## 1. 지형 메시

### 1.1 입력 데이터

| 데이터 | 레이어/필드 | 로컬 실측(성수 4도엽 37705072·73·82·83, 범위 E 202,208–206,630 / N 547,279–552,831 ≈ 4.4×5.6 km) | 비고 |
|---|---|---|---|
| 등고선 | `N3L_F0010000`, 표고 필드 `등고수치`(float), 그 외 `구분`, `UFID` | 341 피처, 63,905 정점, 총연장 319 km, 정점 평균 간격 5.02 m, 표고 5–115 m | 1:5000 주곡선 5 m·계곡선 25 m [S31, 2차] — 실측 최소 5 m와 일치 |
| 표고점 | `N3P_F0020000`, 표고 필드 `수치` | 2,263 점 | 능선·정상·평지 보강용 |
| 격자 DEM | 국토지리정보원 DEM — 공공데이터포털 메타: IMG 포맷, 무료, 국토정보플랫폼 로그인 후 다운로드, "대용량 파일전송 S/W가 필요", 수시(자동 갱신), 최종수정 2025-06-17, **격자 해상도 미기재** [S32]; 국토정보플랫폼 다운로드 메뉴에 'DEM'(격자 간격별) 항목 존재 [S49] | — | 2015년 공개분 90 m 격자 보도 [S33]는 현행 제공분과 무관할 수 있음; **5 m 격자 현행 제공 범위·조건 확인 필요** |
| 좌표계 | SHP `.prj` → EPSG:5186 | 4개 레이어 모두 5186 | pyogrio가 (x=동향, y=북향) 순서로 읽음 — 범위값으로 확인. **파이프라인 요건**: `.prj`를 읽어 5186이 아니면(구버전 수치지형도 v1.x·일부 지자체 자료는 Bessel 1841 기반 구 TM 중부 좌표계로 배포된다고 알려짐 — 해당 EPSG 코드는 **확인 필요**) `pyproj.Transformer.from_crs(src, 5186, always_xy=True)`로 datum 변환 분기 |

- 레이어 코드표는 저장소에 이미 있음: `docs/reference/수치지형도_지형지물_표준코드.csv` [S37]. 관련 상위 코드: `F0010000` 등고선, `F0020000` 표고점, `F0030000` 성/절토, `F0040000` 옹벽(브레이크라인 후보), `E0010001` 하천경계, `E0020000` 하천중심선, `E0032111` 실폭하천, `G0020000` 수부지형경계, `D0010000` 경지계, `D0020000` 지류계. 교량·철도·입체교차부 등 추가 컨텍스트 코드는 4.1절.
- 서울은 1:5000 외에 **1:1000 수치지형도**도 존재한다: 국토정보플랫폼 다운로드 메뉴의 축척 옵션에 '수치지형도(DXF파일)'·'수치지형도Ver2.0(SHP,NGI파일)' 1:1,000이 있음(메뉴 라벨 확인) [S49]. 도시설계 현황도 축척(1:1000–1:2500)에는 1:5000보다 적합하므로 **서울 전역 제공 범위·갱신연도 확인 필요**(9절 11번). 레이어 코드 체계는 동일 표준코드를 쓰므로 파이프라인은 축척과 무관하게 동작해야 한다.

### 1.2 생성 방법 비교

| 방법 | 어디서 실행 | 입력 | 장점 | 단점 | 출처 |
|---|---|---|---|---|---|
| `Mesh.CreateFromTessellation(points, edges, plane, allowNewVertices)` | Rhino(RhinoCommon) | 점 + 선택적 `edges`(폴리라인 = 고정 변, 구멍) | Grasshopper 불필요, **제약변 지원** ("triangulation of a list of points, projected on a plane, including its holes and fixed edges") [S1]. "This is available in the V6 RhinoCommon"(Steve Baer, 2018-07-17) [S2] — `RhinoCommon.xml`에는 이 메서드의 `<since>` 태그가 없어 '6부터'는 이 발언에만 의존 | 포럼 사용자(Bendiko, 2025-01-16)가 결과 면을 법선·종횡비로 걸러내야 했고(Delaunay 일반 특성상 외곽이 볼록껍질까지 채워지는 것으로 해석) "It is however much slower than the Grasshopper component". Dale Fugier(McNeel): "Grasshopper's Delaunay solver is not use the the RhinoCommon method you've referenced" [S3] | [S1][S2][S3] |
| `Mesh.CreatePatch(outerBoundary, angleTol, pullbackSurface, innerBoundaryCurves, innerBothSideCurves, innerPoints, trimback, divisions)` (since 6.0, XML 확인) | Rhino | 외곽 경계 폴리라인 + 내부 점 + 브레이크라인 | **외곽 경계로 자동 트림**("Any of the input that is completely outside the outer boundary will be ignored"), `innerBothSideCurves`로 양쪽 면을 만드는 브레이크라인, `innerBoundaryCurves`로 구멍 | Rhino 전용, 대규모 성능 수치 미확인 | [S1] |
| 격자 DEM → 쿼드 메시 직접 구성 | 어디서나 | 격자 표고 배열 | 정점·면 인덱스를 산술로 생성(601×601=361,201 정점, 360,000 쿼드 구성 0.004 s) → 삼각분할 자체가 필요 없음. RhinoCommon `MeshVertexList.AddVertices(IEnumerable<Point3d>)`(배정밀도), `MeshFaceList.AddFaces` | DEM 입수가 전제(확인 필요); 건물·도로 경계와 무관한 격자라 경계면이 계단 | [S1][S30] |
| `scipy.spatial.Delaunay` | Rhino 밖(또는 Rhino 8 안 `# r: scipy`) | 점 | 빠름(아래 표), numpy 배열 그대로 → rhino3dm Mesh | 제약변 불가(브레이크라인·수면 경계는 사후 처리) | [S25][S30] |
| `triangle`(Shewchuk) CDT | Rhino 밖 | 점 + 세그먼트 | 진짜 제약 Delaunay(브레이크라인·수면·도로 경계가 변으로 보장) | 의존성 1개 추가; cp39 macOS arm64 휠 `triangle-20250106` 확인 | [S45] |
| `ghpythonlib.components.DelaunayMesh` | Rhino + Grasshopper | 점 | 선행 코드가 사용. Rhino 8 CPython 3.9 사이트에도 `ghpythonlib`이 동봉돼 호출은 가능 | Grasshopper 로드 필요, 경계·제약 없음, 테스트 불가 | [S26] |
| `shapely.delaunay_triangles` | Rhino 밖 | 점 | 설치돼 있음 | shapely 2.0.7에는 `constrained_delaunay_triangles` 없음(로컬 확인) | 로컬 |

### 1.3 성능 실측 (scipy 1.13.1, /usr/bin/python3 3.9, Apple Silicon) [S30][S27]

| 입력 | 점 수 | 면 수 | 시간 |
|---|---|---|---|
| 성수 4도엽 등고선 4 m 리샘플(중복 제거) | **약 120,700**(정확 일치 제거 120,695; 소수 2자리 반올림 120,665; 제거 전 120,904) | 약 241,000 | 0.3 s |
| 무작위 50,000 | 50,000 | 99,967 | 0.1 s(1회) |
| 무작위 200,000 | 200,000 | 399,960 | 0.4 s(1회) |
| 무작위 1,000,000 | 1,000,000 | 1,999,963 | **2.6–4.4 s**(3회: 3.53 / 2.56 / 4.40) |
| 무작위 4,000,000 | 4,000,000 | 7,999,960 | **13–18 s**(4회: 13.0 / 16.6 / 16.96 / 18.34) |

- 환산: 성수 4도엽 ≈ 24.5 km²에서 4 m 리샘플이 12만 점 → **1 km²당 약 5천 점**. 서울 1개 구(15–47 km²)도 25만 점 이내로 Delaunay 1 s 미만. 병목은 삼각분할이 아니라 Rhino 표시·파일 크기. 벤치마크는 실행마다 ±30% 흔들리므로 자릿수 하나 수준의 근사치로만 쓴다.
- 리샘플 간격: 선행 코드 `RESOLUTION = 4` 유지가 합리적. 등고선 정점 평균 간격이 이미 5 m라 2 m 이하로 내려도 정보가 늘지 않음. Lands Design 스레드에서는 "dividing the curves per 0.5m gives a better result"라는 사용자 경험이 있으나 이는 측량 곡선(스플라인) 입력 기준 [S4].
- 품질 이슈: 등고선만 쓰면 등고선 사이에 **평평한 삼각형**(세 꼭짓점이 같은 등고선)이 생김 — "Delaunay knows nothing about how these points were originally connected"(Albert Rodríguez, Lands Design) [S4]. 완화책: 표고점 `수치` 추가(성수 2,263점 → 등고선+표고점 중복 제거 122,958점), 능선·계곡선 보간점 추가, 또는 평삼각형 제거 후 재보간. 1:5000 컨텍스트 모델 수준에서는 표고점 추가만으로 충분.

### 1.4 범위(대지·도엽)로 자르기

| 방법 | 설명 | 판단 |
|---|---|---|
| **사전 클리핑(추천)** | shapely로 등고선·표고점·경계선을 `범위.buffer(여유)`로 자른 뒤 삼각분할. 범위 경계 폴리곤을 제약변(CDT)으로 넣으면 경계가 정확히 직선 | 가장 단순·빠름. 외곽 긴 삼각형 문제도 사라짐(경계 밖 면만 제거) |
| `Mesh.CreatePatch(outerBoundary=…)` | 외곽 경계 바깥 입력을 무시하고 경계에 맞춰 메시 | Rhino 안에서 할 때의 정답 [S1] |
| `Mesh.Split(Plane)` (since 5.0) | 무한 평면으로 분할 → 직사각형 범위면 4번 | 단순하지만 비직사각형 불가 [S1] |
| `Mesh.Split(IEnumerable<Mesh>, tolerance, splitAtCoplanar, …)` (since 7.0) | 메시로 메시 분할. 문서 경고: tolerance는 "typically in the (10e-8 - 10e-4) range" | 느리고 허용오차 민감 [S1] |
| `Mesh.SplitWithProjectedPolylines(curves, tolerance)` (since 7.0) | 폴리라인을 투영해 변을 추가하고 분할. "Polyline segments that are measured not to be on the mesh will be ignored" | 비직사각형 범위·도로·수면 경계에 범용 [S1] |
| `Mesh.CreateFromFilteredFaceList(mesh, inclusion)` (since 7.0) | 불리언 마스크로 부분 메시 | 면 중심점이 폴리곤 안인지로 마스크 생성 → 분류별 메시 분리에 사용 [S1] |

`Mesh.Trim`은 RhinoCommon에 없음(로컬 XML 검색 결과 NOT FOUND) [S1]. 위 `Mesh.*` 메서드는 모두 RhinoCommon 전용이며 rhino3dm Python에는 없다(5.2절).

### 1.5 수계 평탄화(hydro-flattening)

- 정의(USGS Lidar Base Specification 용어집): hydro-flattening = "Processing of a lidar-derived surface (DEM or TIN) so that mapped waterbodies, streams, rivers, reservoirs, and other cartographically polygonal water surfaces are flat and, where appropriate, level from bank to bank." hydro-enforcement = 호수는 수평, 하천은 하류로 흐르게. breakline = "A linear feature that describes a change in the smoothness or continuity of a surface." [S5]
- 수위 데이터 소스(한강·중랑천 등 관측소가 있는 하천): **한강홍수통제소 Open API** — URL 패턴 `https://api.hrfco.go.kr/{ServiceKey}/{HydroType}/{DataType}/{TimeType}/{ObsCode}/{StartDate}/{EndDate}.{Format}`(예 `…/waterlevel/list/10M.xml`), 수위·강수량·댐·보·홍수예보발령 5종, xml/json, 인증키는 사이트 '오픈 API → 인증키' 메뉴. 수위관측소 제원 응답 필드: `WLOBSCD` 관측소코드, `OBSNM`, `GDT` 영점표고(EL.m), `ATTWL`/`WRNWL`/`ALMWL`/`SRSWL` 관심·주의보·경보·심각 수위, **`PFH` 계획홍수위** [S50]. 홈페이지 '홍수특보지점 기준홍수위' 표(주의보·경보·계획홍수위 열)는 JS 렌더링이라 본문 **확인 필요** [S51]. 관측 수위는 영점표고 기준 상대값이므로 절대 표고 = `GDT + 수위`(단위·기준 확인 필요).
- 구현(권장 순서):
  1. 수면 폴리곤 결정 — 수치지형도 `E0010001 하천경계`(성수 26 피처), `E0032111 실폭하천`, `G0020000 수부지형경계`(성수 18 피처, `명칭`·`형태` 보유), 호수/저수지, VWorld `LT_C_WKMSTRM 하천망`(`riv_nm`, `cat_nam`; 한강홍수통제소 수자원관리도) [S36].
  2. 수위 = ① 관측소가 있으면 API 실측 수위(평수위) 또는 설계 검토용 `PFH` 계획홍수위를 레이어/사용자 문자열로 병기 ② 없으면 폴리곤 경계를 따라 지형(등고선 TIN)을 샘플링한 **최저값**(제방 양안이 다르면 낮은 쪽; 하천은 구간별로 나눠 하류로 단조 감소 — hydro-enforcement).
  3. 경계를 2 m 이하로 조밀화해 Z=수위로 점에 추가하고, CDT라면 세그먼트로도 넣는다(scipy 무제약이면 조밀화만으로 횡단 삼각형이 **거의** 사라지지만 경계 변이 보장되지는 않음).
  4. 폴리곤 내부 정점 Z를 수위로 고정 → 내부 면은 "Water"로 분류(1.6의 면 분류와 동일 로직).
  5. 수면 자체는 별도 레이어의 평면 메시로 둬서 끄고 켤 수 있게(RhinoCommon이라면 `Brep.CreatePlanarBreps`도 가능하나 rhino3dm에는 없음 → 평면 메시).

### 1.6 추천 파이프라인(코드 스케치)

```python
# /usr/bin/python3 3.9 — Rhino 밖. 입력은 EPSG:5186 (x=동향, y=북향) 로컬 좌표(원점 이동 후).
import numpy as np, shapely
from scipy.spatial import Delaunay           # 제약변 필요하면: import triangle
pts = np.vstack([contour_pts_4m, spot_pts, water_edge_pts, road_edge_pts, bbox_edge_pts])  # (N,3)
tri = Delaunay(pts[:, :2])                   # 0.3 s @ 12만 점
faces = tri.simplices                        # (F,3)
cent = pts[faces][:, :, :2].mean(axis=1)     # 면 중심
cls = classify(cent, polygons={"Water": water, "Road": roads, "Green": green})  # shapely STRtree contains
pts[inside(pts, water), 2] = water_level     # hydro-flatten
# → rhino3dm.Mesh 로 분류별로 쪼개 기록 (5절)
```
`ponytail:` 무제약 Delaunay + 경계 조밀화(경계 변 미보장, 미세 톱니 허용). 제방·옹벽이 뭉개지거나 도로·수면 경계 톱니가 거슬리면 `triangle` CDT로 교체 — 그때부터 3.3절 A안의 '갭·z-fighting 없음'이 보장된다.

---

## 2. 건물

### 2.1 발자국을 지형에 안착 — 최저 vs 평균 표고

| 선택 | 결과 | 근거 |
|---|---|---|
| **최저 표고(추천)** | 바닥이 지형 아래로 파묻히는 쪽은 없고, 경사지에서 높은 쪽 지면 아래에 벽이 묻힘(보이지 않음) → 뚫림 없음 | SIG3D(독일 3D 도시모델 품질 가이드, CityGML LoD1~3): "If the ground surface … is generated by an intersection with the terrain, the elevation of the (horizontal) ground surface is set to the lowest absolute height of the corresponding terrain intersection line." [S6]. 선행 코드도 `min_z` 사용 |
| 지하실 바닥 하단 | SIG3D의 또 다른 규칙: "If there is information available about cellars, the elevation of the ground surface is set to the lower edge of the floor of the cellar" [S6] | LT_C_BLDGINFO는 `ugrnd_flr`(지하층수)만 있고 깊이가 없어 적용 불가 → 지하층은 모델링하지 않음(2.2 규칙 5). 필요하면 `ugrnd_flr × 3 m`로 아래로 압출하는 선택 옵션 |
| 평균 표고 | 경사지에서 낮은 쪽에 바닥이 떠서 지형과 틈이 보임 | 시각적 결함 → 비추천 |
| 최고 표고 | 낮은 쪽이 크게 뜸 | 비추천 |

- 바닥을 최저 표고에 두면 건물 높이(HEIGHT)는 **지상 최저 지반에서의 높이**로 해석됨 — SIG3D의 `measuredHeight` 정의("the measured or computed difference between the lowest terrain intersection point and the highest roof point")와 같은 해석 [S6]. 건축법상 높이 산정 기준면과 다를 수 있으나 컨텍스트 매스 용도에는 충분.
- 투영 방법: Rhino 밖이면 `scipy.interpolate.LinearNDInterpolator(tri, z)`로 발자국 정점 Z 일괄 보간(성수 41,532동·292,255 정점도 벡터 연산 1회). Rhino 안이면 `Intersection.ProjectPointsToMeshes(meshes, points, Vector3d(0,0,-1), tol)`(배치, since 5.0) 또는 `Mesh.PullPointsToMesh` [S1]. 정점별 `Intersection.MeshRay` 루프(선행 코드)는 점 수만큼 .NET 호출이 일어나 느림.

### 2.2 높이 추정 규칙

**데이터 필드**

| 소스 | 높이·층수 필드 | 비고 | 출처 |
|---|---|---|---|
| VWorld 2D API `LT_C_BLDGINFO`(건물통합정보) | `height` 건물높이, `grnd_flr` 지상층수, `ugrnd_flr` 지하층수, `usability` 건물용도, `strct_cd` 구조, `archarea`/`totalarea`/`platarea`, `bc_rat`, `vl_rat`, `useapr_day`, `bld_nm`, `dong_nm`, `ag_geom` | 요청: `request`·`key`·`data` 필수, **`geomFilter` 필수**(POINT/LINESTRING/POLYGON/MULTIPOLYGON/BOX; 레퍼런스 주석 "단일검색=Y도 없고 geomFilter도 없을 경우, emdCd(읍면동코드) 필수"), `size` 기본 10·최대 1000, `page` 기본 1, `crs` 기본 EPSG:4326, `buffer`(m), `domain`(비브라우저 환경에서 필요); 응답 `format` json/xml | [S7] |
| **국토교통부 건축HUB 건축물대장정보 서비스**(공공데이터포털 OpenAPI) | 표제부에 건축물대장 기반 높이·지상층수·지하층수가 있을 것으로 기대되나 **응답 필드명은 활용가이드 zip("OpenAPI활용가이드-_건축HUB_건축물대장_1.0.zip") 안에만 있어 확인 필요** | REST, JSON/XML(`_type`), 무료, "이용허락범위 제한 없음", 월간 갱신, 최종수정 2026-07-10, 개발계정 10,000건/일; 오퍼레이션: 기본개요·표제부·총괄표제부·층별개요·부속지번·전유공용면적·오수정화시설·주택가격·지역지구구역. 조회 키가 시군구코드·법정동코드·번·지(PNU 분해)라 기존 필지 DB와 바로 조인 가능 → **height 결측(70%) 보완 1순위 후보** | [S48] |
| 수치지형도 건물 `N3A_B0010000` | `층수`(int), `명칭`, `구분`, `종류`, `용도`, `주기`, `측량방법` | 성수 4도엽 41,532동 중 `층수` 0/결측 **0.0%**, 최대 58층; 구멍(중정) 12개, 멀티폴리곤 6개 | [S27] |
| VWorld `LT_C_SPBD`(도로명주소 건물) | `gro_flo_co` 건물층수(지상), `bd_mgt_sn`, `buld_nm` | 높이 없음 | [S36] |
| 공식 3D 건물 모델(국토지리정보원 3차원 공간정보, VWorld 3D) | 실측 높이·지붕 형상을 줄 수 있는 대안 | VWorld 3D 가이드 URL(`v4dv_3dmapguide_s001.do`)은 404; VWorld 데이터마켓에 포맷 '3D' 72건 필터는 있으나 목록 미확인 [S52]; 공공데이터포털 '국토지리정보원 3차원' 검색 결과는 수치지도(DXF)·정밀도로지도뿐 [S53] → **제공 여부·형식 확인 필요** | [S52][S53] |

**로컬 실측 — VWorld 건물 캐시(`data/raw/vworld_buildings/merged_5186.json`, 서울 77타일 78,862동, 2026-10-06 갱신)** [S28]

| 지표 | 값(78,862동) | 참고: 단일 타일 `tile_127.008_37.570.json`(2,183동, 이전 판 수치) |
|---|---|---|
| `height ≤ 0`(결측 포함) | **70.0%** | 79.9% |
| `grnd_flr ≤ 0` | 22.4% | 22.8% |
| height·층수 둘 다 있음 | **30.0%**(n=23,637) | 20.0% |
| height/grnd_flr (둘 다 있고 2–8 m 범위, n=23,555) | 중앙값 **3.25 m**, 평균 3.36 m; 분위 10% 2.73 / 25% 2.98 / 75% 3.75 / 90% 3.92 | 중앙값 3.17(n=435) |
| 용도별 중앙값(usability 코드, 코드표 확인 필요) | 01000: **3.40** (n=12,241), 02000: **2.96** (4,792), 04000: 3.20 (2,934), 03000: 3.25 (2,171), 10000: 4.00 (423), 06000: 4.00 (190), 14000: 3.46 (281) | 01000 3.13, 02000 3.20, 04000 3.06, 03000 3.28 |
| `ugrnd_flr > 0` | **42.9%** → 지하층은 높이에 넣지 않는다 | 34.2% |

- 77타일이 서울 전역을 빈틈없이 덮는지(타일 경계 누락·중복)는 별도 확인 필요(9절 8번). 수치는 캐시가 갱신되면 `scripts`에서 재산출한다.

**추천 규칙(우선순위)**

1. `height > 0` → 그대로(m). 단, `height/grnd_flr`가 2 m 미만·8 m 초과면 의심 → 2번으로.
2. `height ≤ 0`이고 건축HUB 표제부에 높이가 있으면 그 값(필드명 확인 후 도입; 2차 버전).
3. `grnd_flr > 0` → `grnd_flr × 3.2 m`(실측 중앙값 3.25 반올림). 용도별 계수는 전체 캐시에서 01000(단독주택 추정) 3.40, 02000(공동주택 추정) 2.96, 04000 3.20, 03000 3.25로 차이가 있어 2차 버전에서 `usability`별 계수 도입을 검토 — 코드표 공식 문서 확인이 선행.
4. 둘 다 없으면 수치지형도 `층수 × 3.2 m`(샘플에서 100% 채움).
5. 그래도 없으면 3 m×1층. OSM 위키 `building:levels`: "The usual dimension is a height of 3 meters for each floor (default floor height used for 3D renderings when the height tags are not specified)" [S8].
6. 지하층(`ugrnd_flr`) 제외. OSM도 지하층은 levels에서 제외 [S8]. SIG3D의 지하실 바닥 규칙(2.1)은 깊이 정보가 없어 적용하지 않음.
7. 결과 객체에 `HEIGHT_SRC`(`height`/`hub`/`grnd_flr*3.2`/`층수*3.2`/`default`)를 사용자 문자열로 남긴다.

- 서울시 S-Map은 "서울 전역의 지형은 물론 약 60만 동의 시설물까지 3D로 구현"(2020-07-01 서비스) [S35]. 검색 결과에 "2008년까지 층당 3 m, 2009년 이후 항공 LiDAR 실측"이라는 요약이 있었으나 1차 페이지(news.seoul.go.kr/gov/archives/1380)가 접근 차단되어 **확인 필요**.
- 건축법 시행령 제119조 제1항 제9호의 "층의 구분이 명확하지 아니한 건축물은 높이 4 m마다 하나의 층"은 법적 층수 산정 규칙이며 역산(층→높이)의 근거는 아님. 원문은 law.go.kr가 JS 렌더링이라 미확인(**확인 필요**).

### 2.3 Extrusion vs Brep vs Mesh

| 타입 | 장점 | 단점 | 적용 |
|---|---|---|---|
| **Extrusion** | "use less memory, meshes faster, and saves smaller than the traditional polysurface"; 고객이 "tens of thousands of objects"인 건축 모델에서 폴리서피스는 느리고 메모리를 많이 썼으나 경량 압출은 반응성 유지 [S9]. Rhino 8 도움말: 폴리서피스 다량이면 "performance can be sluggish", 경량 압출이면 "more responsive and consume less system memory" [S10]. 내부 프로파일(중정) 지원 — rhino3dm `AddInnerProfile` 로컬 검증(ProfileCount=2) | 프로파일이 평면이어야 함. **정점 Z가 다른 발자국을 넣으면 `Extrusion.Create`가 None**(로컬 검증) → 먼저 Z를 최저 표고로 통일. 편집 명령에 따라 폴리서피스로 변환됨 [S10] | 건물 전부 |
| Brep(폴리서피스) | 임의 형상 | 무겁고 파일 큼 | 압출 실패(자기교차 등) 시 폴백: RhinoCommon이면 `Brep.CreatePlanarBreps(curve, tol)` + 압출; rhino3dm 경로에서는 해당 API가 없으므로 shapely 삼각분할 → 메시 폴백 |
| Mesh | 가장 가벼운 표시, 지형과 동일 파이프라인 | 스냅·편집 불편, 설계 대상 건물과 이질 | 지형·도로·수면·녹지 |

### 2.4 압출 방향은 커브 방향에 따라 뒤집힌다(선행 코드 버그 원인)

`Extrusion.Create(planarCurve, height, cap)`(since 5.1, XML 확인): "If the height > 0, the bottom of the extrusion will be in plane and the top will be height units above the plane. If the height < 0, the top of the extrusion will be in plane … The plane used is the one that is returned from the curve's TryGetPlane" [S1]. 평면 법선은 커브 진행 방향(우수 법칙)에 따르므로 **같은 부호의 height라도 링 방향에 따라 위/아래가 바뀐다**. 로컬 검증(rhino3dm 8.35.0):

| 링 방향 | height | 결과 Z 범위(바닥 z=10) |
|---|---|---|
| CCW | +30 | 10 → 40 (위) |
| CCW | −30 | −20 → 10 (아래) |
| CW(ESRI Shapefile 외곽 링) | +30 | −20 → 10 (아래) |
| CW | −30 | 10 → 40 (위) |

선행 코드의 `Extrusion.Create(base_curve, -height, True)`는 Shapefile 외곽 링이 CW라서 위로 올라간 것. GeoJSON(RFC 7946, 외곽 CCW)이나 shapely 정규화 결과를 넣으면 지하로 내려간다. 해결: 압출 전 `shapely.orient(poly, sign=-1)`(CW)로 통일하거나, Rhino 8의 `Extrusion.Create(curve, plane, height, cap)`(since 8.0, XML 확인)에 `Plane.WorldXY`를 z만 옮겨 명시 [S1].

---

## 3. 도로

### 3.1 데이터 소스

| 소스 | 형태 | 속성 | 성수 4도엽 실측 | 판단 |
|---|---|---|---|---|
| 수치지형도 도로경계 `N3A_A0010000` | 폴리곤 | `UFID`만 | 10,101 피처, 92,508 정점, 면적 4.57 km² | **1순위 면 소스**(실제 포장 경계) |
| 수치지형도 도로중심선 `N3L_A0020000` | 선 | `도로폭`, `차로수`, `도로구분`, `포장재질`, `일방통행`, `도로번호`, `명칭` 등 | 19,190 피처; `도로폭`·`차로수` **100% 채움**(도로폭 최빈 3.0/5.5/4.0/7.0 m, 차로수 1이 80%) | 도로경계 없는 곳의 폴백: `중심선.buffer(도로폭/2)`. VWorld 2D API에도 `LT_L_N3A0020000 도로중심선`(국토지리정보원)으로 서비스됨 [S36] |
| 지목 '도로' 필지(기존 DB 898,800필지) | 폴리곤 | 지목·PNU | — | 법적 도로부지. 포장 경계와 다르고 보도 포함 → 베이스맵용 |
| 도로명주소 전자지도 도로구간(`TL_SPRD_MANAGE`), 실폭도로 | 선/면 | `ROAD_BT` 도로폭, `ROA_CLS_SE` 위계(검색 요약) | — | 전자지도는 11종 레이어("건물, 건물군, 도로구간, 실폭도로, 기초구간, 출입구, 기초구역, 행정구역경계") [S43]. 컬럼 정의서는 business.juso.go.kr 404로 **확인 필요**. VWorld `LT_L_SPRD`에는 `rn`(도로명)만 노출 [S36] |
| 표준노드링크(ITS) / VWorld `LT_L_MOCTLINK` | 선 | VWorld 노출 필드: `link_id`, `road_name`, `max_spd`, `rd_rank_h`, `rd_type_h`, `rest_veh_h`, `rest_w`, `rest_h` — **차로수 미노출** | — | its.go.kr 인증서 오류로 공식 속성표 **확인 필요**. 도시설계 컨텍스트에는 중심선 `차로수`가 이미 있어 불필요 |

### 3.2 면 생성

- 도로경계 폴리곤을 그대로 면으로 쓴다(교차로에서 자연히 합쳐져 있음). 폴리곤 간 미세 틈은 `shapely.unary_union` 후 `buffer(0)`.
- 폴백 버퍼: `중심선.buffer(도로폭/2, cap_style="flat", join_style="mitre")` → `unary_union`. 폭 필드가 0/결측이면 `차로수 × 3.0 m`(차로폭 가정, 확인 필요).

### 3.3 지형 위에 올리기(드레이프)

| 방법 | API(출처 [S1]) | 정밀도·특성 |
|---|---|---|
| **A. 하나의 TIN에 경계를 넣고 면 분류(추천, Rhino 밖)** | scipy/`triangle` + numpy | 도로·수면·녹지 경계를 삼각분할 입력에 포함 → 면 중심점 분류 후 분류별 메시로 분리(레이어별). **`triangle` CDT로 경계를 제약변으로 넣을 때** 지형 면이 경계에 정확히 맞아 갭·관통·z-fighting 없음. **무제약 scipy Delaunay(1.6절 기본 경로)**는 경계 조밀화로 횡단 삼각형을 줄이는 근사 — 경계 변이 보장되지 않아 미세 톱니가 남을 수 있음(지형 TIN 자체 오차 외 추가 정밀도 손실은 없음) |
| B. 투영 분할(Rhino 안) | `Mesh.SplitWithProjectedPolylines(IEnumerable<PolylineCurve>, tolerance)` since 7.0 | A(CDT)와 동등한 결과를 Rhino 메시에 직접. 메시 위에 있지 않은 세그먼트는 무시됨 |
| C. 평면 메시 만들고 정점만 투영 | `Mesh.CreateFromPlanarBoundary(curve, MeshingParameters, tolerance)` since 6.0 → `Intersection.ProjectPointsToMeshes(meshes, points, direction, tolerance)` since 5.0 / `ProjectPointsToMeshesEx`(인덱스 반환, 5.10) | 빠르지만 도로 삼각형과 지형 삼각형이 달라 **정점 사이에서 관통/뜸**. 오차 ≤ 그 구간 지형 기복. 도로 메시 변 길이를 지형 변 길이 이하(≈4 m)로 잘게 하고 +0.02~0.05 m 올려 z-fighting 회피 |
| D. 커브만 올리기 | `Curve.ProjectToMesh(curves, meshes, direction, tolerance)` since 5.0(8.17에 `loose` 오버로드), `Curve.PullToMesh(mesh, tolerance)` | 경계선·연석선 표현용 |
| E. 점 단위 | `Intersection.MeshRay(mesh, ray)` → "≥ 0.0 parameter along ray if successful. < 0.0 if no intersection found"; `Mesh.ClosestPoint(testPoint, out pointOnMesh, maximumDistance)` → 면 인덱스, 실패 −1 | ClosestPoint는 수직 투영이 아니라 최근접점(급경사에서 XY가 이동)이므로 드레이프엔 MeshRay/ProjectPoints가 맞음. 둘 다 점 단위 호출이라 대량엔 배치 API 사용 |

B–E는 RhinoCommon 전용(rhino3dm에는 메시 교차 API가 없음, 5.2절).

---

## 4. 하천·수면·녹지·교량·철도 등을 지형 위에 올리기

| 대상 | 소스 레이어 | 처리 |
|---|---|---|
| 하천·호수 수면 | `E0010001 하천경계`, `E0032111 실폭하천`, 호수/저수지, `G0020000 수부지형경계`, VWorld `LT_C_WKMSTRM` [S36][S37]; 수위는 한강홍수통제소 API `GDT`/`PFH`/실측 수위 [S50] | 1.5절 hydro-flattening → 지형 면 중 수면 내부를 "Water" 레이어로 분리하고, 수위 평면 메시를 별도 레이어로 추가. 계획홍수위 `PFH`는 별도 평면(끈 상태)로 두면 홍수위·친수공간 검토에 바로 쓸 수 있음 |
| 하천 중심선 | `E0020000` | 커브로만(베이스맵용), 지형 투영은 `Curve.ProjectToMesh`(RhinoCommon) 또는 scipy 보간 |
| 녹지·공원·경작지 | `D0010000 경지계`, `D0020000 지류계`(성수 각 152·—피처), 도시계획시설(공원) 오버레이(기존 DB), 지목 '공원'·'임야' 필지 | 3.3-A 면 분류로 "Green" 레이어. 수면과 달리 Z 고정 없음 |
| 제방·옹벽·성절토 | `C0050000 제방`(콘크리트/흙 제방 상단·하단 `C0052211`–`C0052214`), `F0040000 옹벽`(콘크리트옹벽 상단/하단 `F0047224`/`F0047225`), `F0030000 성/절토` | 브레이크라인(제약변) 후보 — 필요할 때만(`ponytail:` 1차 버전에서는 생략) |

표시 팁: 같은 평면에 겹치는 메시(지형 위에 수면 평면)는 z-fighting이 나므로 수면을 +0.02 m 올리거나 지형의 해당 면을 분리해 둔다.

### 4.1 추가 컨텍스트 요소 — 교량·고가·지하차도·터널·철도·지하철 (수치지형도 1:5000 코드 [S37])

도시설계 현황 모델에는 교량·고가도로·지하차도·철도·지하철 노선/역 출입구가 필요하다. **VWorld 2D API 158개 서비스를 16페이지 전수 확인한 결과 교량·철도·지하철 전용 레이어는 없고**, 관련 레이어는 `LT_L_MOCTLINK` 교통링크·`LT_P_MOCTNODE` 교통노드·`LT_L_SPRD` 도로명주소 도로·`LT_C_UPISUQ152` 도시계획(교통시설, 계획선)·`LT_L_N3A0020000` 도로중심선뿐이다 [S36]. 따라서 소스는 수치지형도다(성수 4도엽 피처 수는 미집계 — 9절 15번).

| 요소 | 코드(기하) | 1차 버전 처리 | 비고 |
|---|---|---|---|
| 교량 | `A0070000` 교량(면), `A0071212` (철교)고가부(면), `A0071213` 철도터널(면) | 교량 폴리곤을 양끝 접속부 지형 표고로 선형보간해 띄운 슬래브 메시(두께 1–2 m 가정), 아래 지형은 그대로 | 상판 표고 필드 유무 확인 필요 |
| 입체교차부 | `A0090000` 입체교차부, `A0093351` 고가차도(선), `A0093352` 지하차도(선) | 고가차도 = 선을 도로폭으로 버퍼해 교량과 같은 방식; 지하차도 = 커브만(베이스맵 점선) | 선 레이어라 폭은 도로중심선 `도로폭` 참조 |
| 터널 | `A0110020` 터널(선), `A0123373` 터널입구(선), `A0013122` 터널안도로(선) | 커브만(베이스맵 점선), 3D 생략 | |
| 철도 | `A0150000` 철도(선): `A0151111` 보통철도, `A0151115` 지하철(지하부), `A0151116` 지하철(지상부), `A0151118` 고가부(도로시설), `A0151121` 복선철도; `A0160024` 철도경계(철도부지선), `A0171119` 철도중심선 | 지상부 = 철도경계 폴리곤(없으면 중심선 버퍼, 폭 필드 확인 필요)을 3.3-A 면 분류 "Rail"; 지하부 = 커브만(점선) | 지상·지하 구분 코드가 있어 베이스맵 심볼 분리 가능 |
| 역·출입구 | `A0131122` 정거장(면), `A0151224` 지하철역 출입구(면), `C0471223` 지하철 환기통(면) | 출입구·환기통 = 소형 압출(기본 3 m); 정거장 = 건물과 동일 규칙 | |
| 육교 | `A0063321` 육교(면) | 띄운 슬래브(교량과 동일) | |

`ponytail:` 1차 버전은 교량·고가·철도 지상부·지하철역 출입구만 3D로, 나머지는 커브(베이스맵)로. 상판 표고가 데이터에 없으면 접속부 지형 보간으로 충분.

---

## 5. rhino3dm(Rhino 밖)과 RhinoCommon(Rhino 안) 비교

### 5.1 버전·지원

| 항목 | 내용 | 출처 |
|---|---|---|
| 최신 버전 | PyPI 8.35.0 (`pip index versions` 로컬 확인: 8.35.0, 8.32.1, 8.32.0, 8.17.0 …). CHANGELOG: 8.35.0 2026-09-15, 8.32.0 2026-07-28 | [S13][S15] |
| Python 3.9 | 8.32.0에서 "Dropped the Python 3.8 build target … `python_requires` is now `>=3.9`" → 3.9는 최하 지원선. 로컬에서 cp39 macOS 휠 **2종** 다운로드 성공: `rhino3dm-8.35.0-cp39-cp39-macosx_14_0_universal2.whl`, `…-macosx_15_0_universal2.whl`; `/usr/bin/python3`에 8.35.0 설치됨 | [S13][S15] |
| README | "can be used on all current versions of CPython (3.8 - 3.14)", "pip install --user rhino3dm", OpenNURBS 기반으로 Rhino 없이 지오메트리 접근 (3.8 표기는 CHANGELOG와 불일치 — README가 뒤처진 것) | [S14] |
| Rhino 8 내장 Python | CPython **3.9.10**(`~/.rhinocode/py39-rh8/include/python3.9/patchlevel.h`), `# r: numpy, scipy` 지정자로 pip 설치 가능, `# env:` 로 로컬 경로 추가 | [S25][S26] |

### 5.2 rhino3dm 8.35.0 Python API 로컬 검증 결과 [S29]

| 기능 | 결과 |
|---|---|
| `File3dm()`, `Settings.ModelUnitSystem = UnitSystem.Meters`, `ModelAbsoluteTolerance = 0.001` | OK(쓰고 읽어 유지) |
| `Settings.EarthAnchorPoint` | **생성자 없음**(`EarthAnchorPoint()` → "No constructor defined!"). `e = m.Settings.EarthAnchorPoint` → 속성 설정 → `m.Settings.EarthAnchorPoint = e`. 위도·경도·고도·`ModelBasePoint`·`ModelNorth`·`ModelEast`·`Name`·`Description`·`EarthLocationIsSet()`·`GetModelCompass()`·`GetModelToEarthTransform()` 존재. `EarthAnchorPoint` 클래스는 Python/JS에 **0.16.0(2021-05-24)** 추가 [S13]. CHANGELOG 8.4.0(2024-02-19)의 "File3dm.EarthAnchorPoint #554"는 **(dotnet) 항목**이라 Python `File3dm`에는 해당 속성이 없음(`hasattr(File3dm,'EarthAnchorPoint')=False`, `hasattr(File3dmSettings,'EarthAnchorPoint')=True`) → Python에서는 `m.Settings.EarthAnchorPoint`만 사용 | [S13][S16] |
| 레이어 | `m.Layers.AddLayer("Buildings", (r,g,b,a))` → 인덱스 반환; 중첩은 `Layer()` + `ParentLayerId = parent.Id` → `FullPath` "Context::Roads" 확인 | [S18] |
| Extrusion | `Extrusion.Create(PolylineCurve, height, cap)` OK; `AddInnerProfile` OK(중정); `GetMesh`/`SetMesh` 존재(렌더 메시 선저장 가능) | |
| 속성·사용자 문자열 | `ObjectAttributes.LayerIndex`, `.Name`, `.ObjectColor`, `.ColorSource`; `SetUserString/GetUserString/GetUserStrings/UserStringCount`는 `CommonObject`에서 상속(바인딩 `bnd_object.cpp`), 쓰고 읽어 유지 확인 | [S17] |
| 문서 사용자 문자열 | `m.Strings["CRS"] = "EPSG:5186"`(`__setitem__/__getitem__`), `DocumentUserTextCount()`; 읽기 후 유지 | |
| 객체 추가 | `Objects.AddExtrusion/AddMesh/AddCurve/AddPolyline/AddBrep/AddPoint/AddInstanceObject` | [S16] |
| 블록 | `InstanceDefinitions.Add(name, description, url, urlTag, basePoint, (geometry,), (attributes,))` → 인덱스; `InstanceReference(idef.Id, Transform.Translation(...))` | 7개 인자 시그니처만 허용 |
| Mesh | `Vertices.Add(x,y,z)`, `Faces.AddFace(a,b,c,d)`, `Normals.ComputeNormals()` | |
| 쓰기 | `m.Write(path, 8)` → Rhino 8 포맷 | |
| `Intersection` | **클래스 있음** — 멤버 10개: `LineBox`, `LineCircle`, `LineCylinder`, `LineLine`, `LinePlane`, `LineSphere`, `PlanePlane`, `PlanePlanePlane`, `PlaneSphere`, `SphereSphere`(`dir` 확인; `SphereSphere`·`PlaneSphere`는 8.32.0 "(py, js)" 추가 [S13]). 해석 프리미티브 교차만 제공 | [S13][S16] |
| **없는 것** | `Mesh.CreateFromTessellation`, `Mesh.CreatePatch`, `Mesh.SplitWithProjectedPolylines`, `Mesh.CreateFromPlanarBoundary`, `Mesh.ClosestPoint`, `Mesh.Split`, `Brep.CreatePlanarBreps`, `Curve.ProjectToMesh` 없음(`hasattr` 확인). **메시 교차**(`Intersection.MeshRay`, `ProjectPointsToMeshes`, `MeshPolyline` 등) 없음(공식 Python API 문서 `Mesh.html`에도 없음 [S16]) → 메시·투영·분할 계산은 numpy/shapely/scipy로 | [S16] |

벤치마크(동일 스크립트, 2회 실측): 무작위 발자국 **30,000 Extrusion**(각 2개 사용자 문자열) 생성 0.2 s + 361,201 정점/360,000 쿼드 지형 메시 생성 0.3 s + `Write` **2.8–4.4 s** → **38.8–40.2 MB**, 다시 읽기 0.2 s. 수치는 실행마다 ±30% 흔들린다.

### 5.3 장단점

| 관점 | rhino3dm(Rhino 밖) | RhinoCommon(Rhino 안 베이크) |
|---|---|---|
| 지오메트리 연산 | 해석 프리미티브 교차(`Intersection.LineLine` 등)뿐 → 메시·투영·분할은 numpy/shapely/scipy로 직접(이미 설치됨, 빠름) | Delaunay·투영·분할·평면 Brep 등 SDK 전부 |
| 테스트 | `/usr/bin/python3` + pytest로 헤드리스. 결과 3dm을 다시 읽어 검증 가능 | Rhino UI 스레드에서만. 자동화 테스트 어려움 |
| 배치 | 구·도엽 단위 N개 파일 생성 가능 | 사용자가 Rhino를 띄우고 있어야 함 |
| 렌더 메시 | 저장 안 함(Rhino가 열 때 생성) — 필요하면 `Extrusion.SetMesh` | 표시 시 생성, 저장 시 포함 |
| 문서 통합 | 파일을 `Import`하면 레이어·속성·사용자 문자열 그대로 들어옴 | 현재 문서에 바로 추가, `RedrawEnabled` 관리 필요 |
| 좌표계·단위 | `ModelUnitSystem`·`Settings.EarthAnchorPoint`·문서 문자열을 파일에 심음 | 현재 문서 단위에 맞춰 변환 필요(기존 베이커가 이미 이 변환을 함 [S41]) |

**추천**: 생성기는 rhino3dm 경로 하나만 둔다. 플러그인의 "대지검토" 버튼은 (1) PNU·범위 입력 → (2) 생성기 실행(서브프로세스 또는 Rhino 8 CPython 안에서 동일 모듈 import; Rhino 안이라도 rhino3dm 대신 RhinoCommon이 필요 없도록 생성기는 **순수 numpy/shapely 출력 → 작성기(writer) 1개**) → (3) `.3dm` Import. RhinoCommon 전용 기능(`SplitWithProjectedPolylines` 등)은 쓰지 않는다. `ponytail:` RhinoCommon 작성기는 만들지 않음; Import가 느리거나 사용자 문서 병합이 문제가 되면 그때 추가.

---

## 6. 레이어·색상·단위·원점·정북

### 6.1 단위·허용오차
- 모델 단위 m, 절대 허용오차 0.001. Rhino 8 도움말: 허용오차는 "around 0.01 to 0.001", 작은 피처는 허용오차의 10배 이상, **"keep your model size within 100,000 units"** [S22]. 기존 코드도 내부 표준 단위 m [S41].

### 6.2 원점 처리 — EPSG:5186 좌표를 그대로 두면 안 되는 이유
- EPSG:5186 "KGD2002 / Central Belt 2010": TM, 중앙자오선 127°, 원점 위도 38°, 축척 1.0, 가산 동향 200,000 m, 가산 북향 600,000 m; **축 순서 northing, easting (X=북, Y=동)**; 2010-01-01부터 법정 좌표계 [S24]. pyproj `CRS(5186).axis_info`도 `X:north, Y:east` → 변환 시 `always_xy=True` 필수(로컬 확인). Shapefile/pyogrio는 (x=동향, y=북향)으로 저장돼 있음(성수 범위값으로 확인).
- **입력 좌표계 점검(요건)**: 모든 SHP가 5186이라고 가정하지 말고 `.prj`(또는 `gpd.read_file(...).crs`)를 읽어 분기한다. 구버전 수치지형도(v1.x)·일부 지자체 배포본은 Bessel 1841 기반 구 TM 중부 좌표계로 알려져 있어(해당 EPSG 코드와 실제 사례는 **확인 필요**) datum 변환(`Transformer.from_crs(src, "EPSG:5186", always_xy=True)`)이 필요하다. 5186끼리라도 ±수십 m 어긋나면 datum 오류를 먼저 의심.
- 성수 중심(127.0557E, 37.5447N) → (E 204,922, N 549,467) [로컬 pyproj]. 55만 단위는 Rhino 권장 모델 크기(100,000) 초과.
- McNeel 위키: "Objects that are extremely far (millions of units) from the world origin suffer from display and precision problems due to the polygon mesh vertex locations being represented by a single precision number." 권장 워크플로 = 복사본을 원점으로 옮겨 작업하고 원본엔 링크 블록으로 삽입 [S19]. 포럼(McNeel 스태프): "take your Rhino unit precision (0.01m or whatever), multiply by 10^7, and try to keep within that distance of the origin"(Christopher Savage); "there is no real ideal maximum distance"(Menno Deij) [S20]; Dale Lear: 배정밀도 ~16자리라 큰 평행이동이 세부 치수를 잠식 [S21]. 큰 좌표 입력 시 표시값에 1e-6 수준 잔차가 붙는 사례(474,350 / 4,203,130) [S44].
- **관행**: 대지 중심(또는 범위 최소 모서리를 100 m 단위로 내림한 값)을 (0,0)으로. 오프셋은 세 곳에 기록: ① `File3dm.Strings`: `CRS=EPSG:5186`, `ORIGIN_E`, `ORIGIN_N`(복원식: 세계좌표 = 로컬 + ORIGIN) ② `Settings.EarthAnchorPoint`(위경도·`ModelBasePoint=(0,0,0)`·`ModelNorth=(0,1,0)`·`Description`에 동일 문자열) — Rhino 명령 `EarthAnchorPoint`가 "adds information to the model about the model's position in latitude, longitude, and elevation for GIS mapping applications" [S23] ③ 모델 안 원점 마커(점 + TextDot). 기존 코드는 이미 `origin_easting/origin_northing`을 빼서 커브를 만들고(`lot_builder.py`) 되돌릴 때 더함(기존 컨트롤러) [S41] → **같은 필드명과 규약을 재사용**.
- Z: 표고를 그대로 둔다(성수 5–115 m, 정밀도 문제 없음) — 단면·일조에서 절대표고가 필요.

### 6.3 정북
- Rhino +Y = 정북 규약(CLAUDE.md "좌표계: 한국 투영좌표계 기준, +Y = 정북 가정") [S41]. `EarthAnchorPoint.ModelNorth=(0,1,0)`로 명시.
- 도북(그리드 북)과 진북의 차이 = 자오선 수렴각. pyproj `get_factors`: 성수 **0.034°**, 서울 서단(126.78E) −0.134° [로컬]. 1 km에서 0.6 m / 2.3 m 수준 → 매스 컨텍스트에서는 무시, 정밀 일조 분석이 필요하면 수렴각만큼 회전.

### 6.4 레이어·색 제안(Seoungsu 베이스맵 팔레트와 맞춤 [S42])

| 레이어(FullPath) | 타입 | 색(RGB) | 사용자 문자열 |
|---|---|---|---|
| `CTX::Terrain` | Mesh | 236,232,222 (배경 #F2F2EE 계열) | `SRC`, `RESAMPLE_M` |
| `CTX::Water` | Mesh(평면, 수위) | 46,125,224 (#2E7DE0) | `NAME`, `LEVEL_M`, `LEVEL_SRC`(`hrfco`/`terrain_min`), `PFH_M` |
| `CTX::Roads` | Mesh(지형 면 분류) | 168,168,162 (#A8A8A2) | `WIDTH_M`, `LANES`, `SRC` |
| `CTX::Rail` | Mesh / Curve(지하부) | 110,110,110 | `KIND`(철도/지하철 지상·지하), `SRC` |
| `CTX::Bridges` | Mesh(띄운 슬래브) | 150,150,150 | `KIND`(교량/고가차도/육교), `DECK_Z_SRC` |
| `CTX::Green` | Mesh | 228,235,226 (#E4EBE2) | `KIND` |
| `CTX::Buildings` | Extrusion | 128,128,128 | `PNU`/`UFID`, `GRND_FLR`, `UGRND_FLR`, `HEIGHT_M`, `HEIGHT_SRC`, `USABILITY`, `BLD_NM` |
| `CTX::Parcels` | PolylineCurve | 185,185,180 | `PNU`, `JIMOK`, `ZONE` |
| `CTX::Site` | PolylineCurve | 220,40,40 | `PNU` |
| `CTX::Ref` | Point/TextDot/Curve | 0,0,0 | 원점 마커, 도엽 경계, `ORIGIN_E/N`, `SRC_CRS` |

(색은 제안. 레이어 생성·탐색은 기존 베이커의 `Layers.FindByFullPath` → 없으면 `Layers.Add` 패턴을 그대로 가져온다 [S41].)

---

## 7. 선행 코드 `/Users/sanghoon/Documents/GitHub/SHPtoContext/main.py` 개선점

| # | 현재 코드 | 문제 | 개선 |
|---|---|---|---|
| 1 | `ghcomp.DelaunayMesh(mesh_points)` | Grasshopper 의존, 경계·제약 없음, 볼록껍질까지 채움, 테스트 불가 [S3][S26] | scipy/`triangle` → rhino3dm Mesh(1.6). Rhino 안이면 `Mesh.CreatePatch(outerBoundary=…)` |
| 2 | `Extrusion.Create(base_curve, -height, True)` | 음수 높이가 위로 가는 건 ESRI 외곽 링이 CW이기 때문(2.4 로컬 검증). CCW 입력이면 지하로 압출 | 링 방향 정규화 후 양수 높이, 또는 Rhino 8 `Create(curve, plane, height, cap)` |
| 3 | `height = record[5] * 3.5` | 매직넘버, 필드 인덱스 의존(`층수`가 6번째라 우연히 맞음) | 필드명 접근(`층수`), 계수 3.2(실측 중앙값 3.25) 상수화 + `HEIGHT_SRC` 기록. VWorld `height` 우선 |
| 4 | 정점마다 `Intersection.MeshRay` 2회 루프 | 29만 정점 × .NET 호출 → 느림 | `ProjectPointsToMeshes` 배치 또는 scipy 보간 1회 |
| 5 | `base_curve.Translate(... min_z - vertices[0].Z)` 후 압출 | 정점 Z가 다르면 `Extrusion.Create`가 None(로컬 검증) — 지금은 Z=0 평면 커브라 통과 | 발자국 Z를 최저 표고로 통일한 평면 커브 생성 |
| 6 | `geom[0]`만 사용 | 멀티폴리곤 나머지 파트·구멍(성수 12개 중정) 무시 | 외곽 + `AddInnerProfile`(구멍), 파트별 객체 |
| 7 | 좌표 그대로(EPSG:5186 20만/55만) | 원점 멀어 정밀도·스냅·표시 문제 [S19][S20] | 6.2 원점 이동 + 오프셋 기록 |
| 8 | 레이어·속성·사용자 문자열 없음, 도로·하천은 커브만 | 결과 활용·검수 불가, 면 없음 | 6.4 레이어 트리 + 속성; 도로·수면·녹지 면(3·4절) |
| 9 | `shapefile`(pyshp) 수동 파싱, 인코딩 `cp949` | 동작하나 geopandas/pyogrio가 이미 있음 | `gpd.read_file(..., encoding="cp949", engine="pyogrio")` 한 줄 + `.crs` 점검(6.2) |
| 10 | 표고점 `N3P_F0020000` 미사용 | 등고선 사이 평삼각형 [S4] | 표고점 `수치` 추가 |
| 11 | 등고선을 PolylineCurve로 만들고 `DivideByLength` | Python 루프 + .NET 객체 생성 | `shapely.segmentize(4.0)` → `get_coordinates` |

---

## 8. 대량 처리 성능 — 서울 1개 구(수만 동) 기준

| 주제 | 사실 | 출처 |
|---|---|---|
| 규모 감 | 성수 4도엽(24.5 km²)에 건물 41,532동(정점 292,255) → 1 km²당 약 1,700동; VWorld 캐시 서울 77타일 78,862동; 서울 전체 S-Map 약 60만 동 | [S27][S28][S35] |
| Extrusion 권장 이유 | Rhino 5에서 "tens of thousands of objects"의 건축 모델을 위해 도입; 폴리서피스 대비 "less memory, meshes faster, saves smaller" | [S9][S10] |
| 파일 크기·시간(rhino3dm) | 3만 Extrusion + 36만 정점 지형 ≈ **40 MB**, 쓰기 **약 3–4 s**(2회 2.8–4.4 s), 읽기 0.2 s | [S29] |
| Rhino 안 베이크 | `doc.Views.RedrawEnabled = False`로 감싸고 마지막에 한 번 `Redraw()`; rhinoscriptsyntax는 객체마다 Redraw를 불러 "painfully slow"(Farouk Serragedine, McNeel) | [S12] |
| 블록 | 정의 1개를 여러 인스턴스가 공유해 "Keep a smaller model size"; 그러나 인스턴스 변환이 표시에서 비용이라 "it might eat into any performance gain"(Pascal Golay) — 발자국이 전부 다른 건물엔 효과 없음. 가로수·벤치 등 반복물에만 | [S39][S11] |
| 렌더 메시 | NURBS/압출은 표시 시 렌더 메시 생성; "Jagged and faster" 프리셋이 저밀도 메시로 빠르게 셰이딩. 압출 수만 개면 첫 셰이딩 시 메시 생성 지연이 있으므로 문서 메시 설정을 Jagged로 두거나 rhino3dm에서 `Extrusion.SetMesh`로 선저장 | [S38][S29] |
| 메시 크기 | 15만–60만 점 메시에서 Rhino 편집(SoftTransform)이 무거웠다는 사용자 보고; 스태프는 `ReduceMesh`·선택적 리메시 권장 — 지형은 분류별로 쪼개고 범위 밖은 자르는 것이 먼저 | [S47] |
| 한계 인식 | "Rhino isn't a game engine" — 도시 전체는 파일 분할·레이어 분리로 | [S34] |
| 실무 규칙 | 범위 = 대상지 + 반경(500 m~1 km)로 제한; 구 전체가 필요하면 행정동/도엽별 파일 + 링크 블록 조립 [S19] | |

---

## 9. 미해결·확인 필요

1. 국토지리정보원 DEM: 공공데이터포털 메타는 "IMG, 무료, 로그인 후 다운로드, 대용량 파일전송 S/W 필요, 수시 갱신, 최종수정 2025-06-17"이며 **격자 해상도를 적지 않음** [S32]. 국토정보플랫폼 다운로드 메뉴에 'DEM'(격자 간격별) 항목은 있으나 JS 앱이라 간격·범위 미확인 [S49]. 2015년 90 m 보도 [S33]는 현행과 무관할 수 있음. → **5 m 격자의 현행 제공 범위·조건** 확인 필요(플랫폼 로그인 후 메뉴 직접 확인).
2. 도로명주소 전자지도 도로구간 `ROAD_BT`·`ROA_CLS_SE` 공식 컬럼 정의서(business.juso.go.kr 404, juso.go.kr 404).
3. 표준노드링크 `LANES`·`ROAD_RANK` 공식 정의(its.go.kr·nodelink.its.go.kr 인증서/접속 오류). VWorld `LT_L_MOCTLINK`에는 `lanes`가 노출되지 않음 [S36].
4. S-Map 건물 높이 구축 방식(2008년 이전 층당 3 m, 2009년 이후 LiDAR)의 1차 출처(news.seoul.go.kr 차단).
5. 건축법 시행령 제119조(높이·층고·층수) 원문(law.go.kr JS) — 코드에 넣기 전 사용자와 확인.
6. 3차원국토공간정보구축작업규정(국토지리정보원 고시)의 건물 기준면·LOD 정의(law.go.kr JS).
7. Rhino 안 `Mesh.CreateFromTessellation`/`CreatePatch`의 10만 점 이상 성능 수치(미실측; 포럼은 정성적 "느림"만). `CreateFromTessellation`의 도입 버전은 XML `<since>`가 없어 포럼 발언 [S2]에만 의존.
8. VWorld `LT_C_BLDGINFO` `height` 결측률: **서울 77타일 78,862동 기준 70.0%로 재산출 완료**(2.2절). 남은 것: 77타일이 서울 전역을 빈틈없이 덮는지(타일 경계·누락), `usability` 코드표(01000 단독주택 등) 공식 문서.
9. `도로폭` 결측 시 `차로수 × 3.0 m` 가정의 근거(도로의 구조·시설 기준에 관한 규칙 차로폭 — 확인 필요).
10. **건축HUB 건축물대장정보 서비스 표제부 응답 필드명**(높이·지상층수·지하층수) — 공공데이터포털 페이지에는 오퍼레이션명만 있고 필드는 활용가이드 zip 안 [S48]. zip을 받아 확인한 뒤 2.2 규칙 2번을 활성화.
11. **서울 1:1000 수치지형도**: 국토정보플랫폼 다운로드 메뉴에 축척 1:1,000 옵션 존재 확인 [S49]. 서울 전역 제공 범위·갱신연도, 서울시 자체 배포(서울 열린데이터광장) 여부는 미확인(검색 한도 소진; 열린데이터광장 검색·스마트서울맵 홈에는 수치지형도 항목이 보이지 않음 [S54]). 확인 방법: 국토정보플랫폼 로그인 → 수치지형도Ver2.0(SHP) → 축척 1:1,000 → 서울 도엽 검색.
12. **공식 3D 건물 모델**: VWorld 데이터마켓에 포맷 '3D' 72건 필터가 있으나 검색 파라미터를 몰라 목록 미확인 [S52]; VWorld 3D 가이드 URL 404; 국토지리정보원 홈은 JS로 본문 없음; 공공데이터포털 '국토지리정보원 3차원' 검색에는 3D 건물 데이터셋 없음 [S53]. 확인 방법: 데이터마켓에서 포맷 '3D' 필터 직접 클릭, 국토정보플랫폼 '3차원 공간정보' 메뉴 확인.
13. 한강홍수통제소 홈페이지 '홍수특보지점 기준홍수위' 표의 관측소별 값(JS) [S51] — Open API 수위관측소 제원 `PFH`·`GDT`로 대체 가능 [S50]; `PFH` 단위(m vs EL.m)와 영점표고 기준 확인.
14. `.prj`가 EPSG:5186이 아닌 입력(구버전 수치지형도·지자체 자료)의 실제 EPSG 코드와 사례 확인(6.2).
15. 교량·철도·지하철 레이어(4.1)의 성수 4도엽 피처 수·속성 필드(상판 표고, 철도 폭) 미집계 — 다음 실측 때 `geopandas`로 집계.

---

## 출처 (접근일 2026-10-07)

- [S1] RhinoCommon 공식 API 주석 원문 — 로컬 Rhino 8.35 설치본 `/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources/RhinoCommon.xml` (developer.rhino3d.com/api/rhinocommon 과 동일 소스; 웹 페이지는 JS 렌더링으로 본문 수집 실패). `<since>` 태그 확인: `Extrusion.Create(curve,height,cap)` 5.1, `Extrusion.Create(curve,plane,height,cap)` 8.0, `Mesh.CreatePatch` 6.0, `Mesh.CreateFromTessellation` 태그 없음
- [S2] McNeel Forum, "Mesh.CreateFromTessellation not in Rhinocommon?" (Steve Baer, 2018-07-17 "This is available in the V6 RhinoCommon"; 이 스레드에는 성능·볼록껍질 언급 없음) https://discourse.mcneel.com/t/mesh-createfromtessellation-not-in-rhinocommon/67105
- [S3] McNeel Forum, "Delaunay mesh in rhinocommon" (Bendiko 2025-01-16 "It is however much slower than the Grasshopper component"; Dale Fugier "Grasshopper's Delaunay solver is not use the the RhinoCommon method you've referenced") https://discourse.mcneel.com/t/delaunay-mesh-in-rhinocommon/197925
- [S4] McNeel Forum, "Building an accurate terrain mesh" (Lands Design, Albert Rodríguez) https://discourse.mcneel.com/t/building-an-accurate-terrain-mesh/151760
- [S5] USGS, Lidar Base Specification — Glossary https://www.usgs.gov/ngp-standards-and-specifications/lidar-base-specification-glossary
- [S6] SIG3D, Modeling Guide for 3D Objects – Part 2: Modeling of Buildings (LoD1, LoD2, LoD3) — 지형 교선 최저고 규칙, 지하실 바닥 하단 대안, measuredHeight 정의 https://en.wiki.quality.sig3d.org/index.php/Modeling_Guide_for_3D_Objects_-_Part_2:_Modeling_of_Buildings_(LoD1,_LoD2,_LoD3)
- [S7] VWorld 2D 데이터 API 2.0 레퍼런스 — LT_C_BLDGINFO(요청 파라미터 필수/선택 표, geomFilter 필수) https://www.vworld.kr/dev/v4dv_2ddataguide2_s002.do?svcIde=bldginfo
- [S8] OpenStreetMap Wiki, Key:building:levels https://wiki.openstreetmap.org/wiki/Key:building:levels
- [S9] McNeel Wiki, "Lightweight Extrusion Objects" https://wiki.mcneel.com/rhino/rhinov5status_extrusions
- [S10] Rhino 8 Help, "Polysurfaces and lightweight extrusion objects" https://docs.mcneel.com/rhino/8/help/en-us/seealso/sak_polysurfaces.htm
- [S11] McNeel Forum, "Blocks vs Extrusions" (Pascal Golay) https://discourse.mcneel.com/t/blocks-vs-extrusions/140803
- [S12] McNeel Forum, "Rhinoscriptsyntax - Add Object, redraw - performance" (Farouk Serragedine) https://discourse.mcneel.com/t/rhinoscriptsyntax-add-object-redraw-performance/164333
- [S13] mcneel/rhino3dm CHANGELOG (8.x) — 8.35.0 2026-09-15, 8.32.0 2026-07-28 "(py, js) Intersection.SphereSphere and Intersection.PlaneSphere", "Dropped the Python 3.8 build target … python_requires >=3.9"; 8.4.0 2024-02-19 "(dotnet) File3dm.EarthAnchorPoint #554"; 0.16.0 2021-05-24 "(js, py) EarthAnchorPoint class" https://github.com/mcneel/rhino3dm/blob/8.x/CHANGELOG.md
- [S14] mcneel/rhino3dm README (8.x) https://github.com/mcneel/rhino3dm/blob/8.x/README.md
- [S15] PyPI rhino3dm https://pypi.org/project/rhino3dm/ (로컬 `pip index versions rhino3dm`, `pip download rhino3dm==8.35.0 --only-binary=:all:` 로 cp39 `macosx_14_0_universal2`·`macosx_15_0_universal2` 휠 2종 확인)
- [S16] rhino3dm Python API 문서 https://mcneel.github.io/rhino3dm/python/api/File3dm.html , File3dmSettings.html , File3dmObjectTable.html , ObjectAttributes.html , Extrusion.html , Mesh.html , Layer.html , EarthAnchorPoint.html
- [S17] mcneel/rhino3dm `src/bindings/bnd_object.cpp`(SetUserString/GetUserString/GetUserStrings/UserStringCount 바인딩) https://github.com/mcneel/rhino3dm/blob/8.x/src/bindings/bnd_object.cpp
- [S18] McNeel Forum, "Rhino3dm Python Library - How to add a Layer to the model?" https://discourse.mcneel.com/t/rhino3dm-python-library-how-to-add-a-layer-to-the-model/163936
- [S19] McNeel Wiki, "Objects far from origin" https://wiki.mcneel.com/rhino/farfromorigin
- [S20] McNeel Forum, "Ideal maximum distance from Origin" https://discourse.mcneel.com/t/ideal-maximum-distance-from-origin/201751
- [S21] McNeel Forum, "The pain with models far away from the origin" (Dale Lear) https://discourse.mcneel.com/t/the-pain-with-models-far-away-from-the-origin/26790
- [S22] Rhino 8 Help, Document Properties: Units https://docs.mcneel.com/rhino/8/help/en-us/documentproperties/units.htm
- [S23] Rhino 8 Help, EarthAnchorPoint command https://docs.mcneel.com/rhino/8/help/en-us/commands/earthanchorpoint.htm
- [S24] EPSG:5186 KGD2002 / Central Belt 2010 https://epsg.io/5186
- [S25] Rhino Developer Docs, "Python Packages"(`# r:`) https://developer.rhino3d.com/guides/rhinopython/python-packages/ ; "Scripting: Command" https://developer.rhino3d.com/guides/scripting/scripting-command/
- [S26] 로컬: `~/.rhinocode/py39-rh8/include/python3.9/patchlevel.h`(PY_VERSION "3.9.10"), `~/.rhinocode/py39-rh8/site-rhinoghpython/ghpythonlib/components.py`
- [S27] 로컬 실측: 수치지형도 1:5000 v2.0 도엽 37705072·37705073·37705082·37705083(`~/Downloads`) — geopandas 1.0.1/pyogrio로 피처·정점·필드 집계; 4 m 리샘플 재집계(2026-10-07: 제거 전 120,904 / 정확 일치 제거 120,695 / 2자리 반올림 120,665 / 등고선+표고점 122,958)
- [S28] 로컬 실측: `data/raw/vworld_buildings/merged_5186.json`(LT_C_BLDGINFO, dict `{id:{geom,props}}`, 서울 77타일 78,862동, 수정일 2026-10-06 13:38) 통계. 이전 판의 2,183동 수치는 같은 폴더의 단일 타일 `tile_127.008_37.570.json`과 정확히 일치
- [S29] 로컬 실측: rhino3dm 8.35.0 쓰기/읽기 테스트 및 3만 Extrusion 벤치마크(2회: Write 4.4 s/38.8 MB, 2.8 s/40.2 MB); `hasattr`/`dir`로 API 존재 확인(Intersection 멤버 10개, File3dm.EarthAnchorPoint 없음)
- [S30] 로컬 실측: scipy 1.13.1 `Delaunay` 벤치마크(1M: 3.53/2.56/4.40 s, 4M: 13.0/16.6/16.96/18.34 s), 격자 메시 인덱스 구성
- [S31] (2차) 게으른 나무 블로그, "QGIS 수치지형도(1:5000)를 이용해 DEM 만들기 (TIN 보간)" https://lazytrees.com/1570/
- [S32] 공공데이터포털, 국토교통부 국토지리정보원_DEM(IMG, 무료, 로그인 후 다운로드, "대용량 파일전송 S/W가 필요합니다", 수시 갱신, 최종수정 2025-06-17, 격자 해상도 미기재) https://www.data.go.kr/data/15059920/fileData.do
- [S33] (언론) 아시아투데이 2015-01-04, "국토지리정보원, 3차원으로 지형 볼수 있는 수치표고모델 공개"(90 m 격자) https://www.asiatoday.co.kr/kn/view.php?key=20150104010001116
- [S34] McNeel Forum, "Making city in Rhino" https://discourse.mcneel.com/t/making-city-in-rhino/164967
- [S35] 스마트시티 종합포털(정부), "서울시, 도시문제해결 시뮬레이션 '디지털 트윈 S-Map' 전국 최초 구축"(약 60만 동) https://smartcity.go.kr/2021/04/01/%EC%84%9C%EC%9A%B8%EC%8B%9C-%EB%8F%84%EC%8B%9C%EB%AC%B8%EC%A0%9C%ED%95%B4%EA%B2%B0-%EC%8B%9C%EB%AE%AC%EB%A0%88%EC%9D%B4%EC%85%98-%EB%94%94%EC%A7%80%ED%84%B8-%ED%8A%B8%EC%9C%88-s-map-%EC%A0%84/
- [S36] VWorld 2D 데이터 API 목록(총 158건, 16페이지 — 2026-10-07 `pageIndex=1…16` 전수 확인: 교량·철도·지하철 전용 레이어 없음; 교통 관련은 `sprd`, `spbd`(p.3), `wkmstrm`, `moctlink`, `moctnode`(p.4), `upisuq151/152/156`(p.9), `bldginfo`(p.15), `n3a0020000` 도로중심선·`landinfobasemap`(p.16)) https://www.vworld.kr/dev/v4dv_2ddataguide2_s001.do ; 상세 `?svcIde=moctlink`, `?svcIde=sprd`, `?svcIde=spbd`, `?svcIde=wkmstrm`
- [S37] 저장소 `docs/reference/수치지형도_지형지물_표준코드.csv`(교량 A0070000, 입체교차부 A0090000, 터널 A0110020, 정거장 A0131122, 철도 A0150000, 철도경계 A0160024, 철도중심선 A0171119, 제방 C0050000, 옹벽 F0040000 등); `docs/reference/vworld_wms_layers.tsv`(WMS 레이어 184행)
- [S38] Rhino 8 Help, Document Properties: Mesh https://docs.mcneel.com/rhino/8/help/en-us/documentproperties/mesh.htm
- [S39] Rhino 8 Help, Block command https://docs.mcneel.com/rhino/8/help/en-us/commands/block.htm
- [S40] Ladybug Tools Forum, "How to properly treat real world coordinates?" https://discourse.ladybug.tools/t/how-to-properly-treat-real-world-coordinates/14581
- [S41] 기존 코드: 기존 필지·베이커 코드(Layers.FindByFullPath/Add, ModelUnitSystem 변환), `CLAUDE.md`(+Y=정북, 단위 m)
- [S42] 저장소 `Seoungsu/scripts/make_minimap_layers.py` 색상 팔레트
- [S43] 공공데이터포털, 행정안전부_도로명주소 전자지도(11종 레이어) https://www.data.go.kr/data/15050413/fileData.do
- [S44] McNeel Forum, "Precision problem in large coords" (Steve Baer) https://discourse.mcneel.com/t/precision-problem-in-large-coords/170921
- [S45] PyPI triangle(로컬 `pip download triangle --only-binary=:all:` → `triangle-20250106-cp39-cp39-macosx_11_0_arm64.whl`) https://pypi.org/project/triangle/
- [S46] McNeel Forum, "Rhino3dm 8.32.0 released" https://discourse.mcneel.com/t/rhino3dm-8-32-0-released/221906
- [S47] McNeel Forum, "Dense mesh landscapes very slow in Rhino" https://discourse.mcneel.com/t/dense-mesh-landscapes-very-slow-in-rhino/202562
- [S48] 공공데이터포털, 국토교통부_건축HUB_건축물대장정보 서비스(REST, JSON/XML, 무료, "이용허락범위 제한 없음", 월간, 최종수정 2026-07-10; 오퍼레이션 기본개요·표제부·총괄표제부·층별개요·부속지번·전유공용면적·오수정화시설·주택가격·지역지구구역; 필드는 활용가이드 zip) https://www.data.go.kr/data/15134735/openapi.do
- [S49] 국토지리정보원 국토정보플랫폼(JS 앱; 다운로드 메뉴 라벨 "수치지형도(DXF파일)" 1:1,000–1:250,000, "수치지형도Ver2.0(SHP,NGI파일)", "기본공간정보(SHP파일)", "DEM", "정사영상", "항공사진") https://map.ngii.go.kr/ms/map/NlipMap.do
- [S50] 한강홍수통제소 Open API — 레퍼런스(수위·강수량·댐·보·홍수예보발령; URL 패턴 `https://api.hrfco.go.kr/{ServiceKey}/{HydroType}/{DataType}/{TimeType}/{ObsCode}/{StartDate}/{EndDate}.{Format}`; 수위관측소 제원 필드 `WLOBSCD`, `OBSNM`, `GDT`, `ATTWL`, `WRNWL`, `ALMWL`, `SRSWL`, `PFH`) https://www.hrfco.go.kr/web/openapiPage/reference.do ; 인증키 https://www.hrfco.go.kr/web/openapiPage/certifyKey.do ; 홈(실시간 수문자료 `/sumun/waterlevelList.do`) https://www.hrfco.go.kr/
- [S51] 한강홍수통제소, 홍수특보지점 기준홍수위(표 본문 JS, 미확인) https://www.hrfco.go.kr/web/floodPage/floodLevel.do
- [S52] VWorld 데이터마켓(공간정보분류 12개·737건, 포맷 '3D' 72건 필터; 검색 파라미터 미확인) https://www.vworld.kr/dtmk/dtmk_ntads_s001.do
- [S53] 공공데이터포털 검색 '국토지리정보원 3차원'(결과 4건: 정밀도로지도 15059912, 수치지도 DXF 15015482, 온맵 15059914, 서비스데이터정보 15064032 — 3D 건물 모델 없음) https://www.data.go.kr/tcs/dss/selectDataSetList.do?keyword=%EA%B5%AD%ED%86%A0%EC%A7%80%EB%A6%AC%EC%A0%95%EB%B3%B4%EC%9B%90+3%EC%B0%A8%EC%9B%90
- [S54] 서울 공간정보(스마트서울맵, `gis.seoul.go.kr` → 301) https://map.seoul.go.kr/ ('3D 서울지도' 메뉴 있음, 수치지형도·다운로드 언급 없음); 서울 열린데이터광장 검색 https://data.seoul.go.kr/dataList/datasetList.do (검색어 파라미터 미적용, 수치지형도 결과 미확인)

---

## 검증 이력

2026-10-07 검증 결과 반영(검증자 지적 → 조치). 모든 수치는 이 세션에서 로컬 재실행·1차 출처 재열람으로 다시 확인했다.

| # | 지적 | 조치 |
|---|---|---|
| 1 | [refuted] `File3dm.EarthAnchorPoint`는 8.4.0 추가 | CHANGELOG 8.4.0 항목은 "(dotnet)" 전용으로 확인. Python은 `File3dmSettings.EarthAnchorPoint`만 존재(`hasattr` 재확인), 클래스 자체는 0.16.0(2021-05-24) 추가. 5.2절·[S13] 수정 |
| 2 | [refuted] rhino3dm Python에 `Intersection` 모듈이 없다 | `rhino3dm.Intersection` 존재(멤버 10개: LineBox…SphereSphere) 확인. '전부 없음' → '메시 교차(MeshRay, ProjectPointsToMeshes 등) 없음'으로 5.2·5.3절 수정. 나머지 5개 메서드 부재는 유지하고 `CreatePatch`·`SplitWithProjectedPolylines`·`CreateFromPlanarBoundary` 부재도 추가 |
| 3 | [refuted] VWorld 캐시 2,183동 통계(79.9%/3.17 m/34.2%) | 수치가 `merged_5186.json`이 아닌 단일 타일 `tile_127.008_37.570.json`(2,183동) 기준이었음을 확인. 전체 캐시(77타일 78,862동)로 재산출: height≤0 70.0%, grnd_flr≤0 22.4%, 둘 다 30.0%(n=23,637), 2–8 m 비율 n=23,555 중앙값 3.25(평균 3.36, 10/25/75/90% 2.73/2.98/3.75/3.92), ugrnd>0 42.9%, 용도별 01000 3.40·02000 2.96·04000 3.20·03000 3.25. 요약·2.2·8·9-8·[S28] 갱신. 층고 계수 3.2 m 유지. 두 검증자의 평균값 차이(3.36 vs 3.39)는 2–8 m 필터 유무 차이로 확인 |
| 4 | geomFilter는 필수 | VWorld 레퍼런스에서 Required 확인. 2.2 표에 '필수'와 "단일검색=Y도 없고 geomFilter도 없을 경우 emdCd 필수" 주석, `size` 기본 10, `domain` 조건 추가 |
| 5 | CreateFromTessellation 행의 포럼 발언 출처 | [S2](67105)에는 Steve Baer의 V6 가용성 발언만 있음을 확인. 'much slower'(Bendiko 2025-01-16)·Dale Fugier 발언은 [S3](197925)로 출처 이동. '볼록껍질까지 채움'은 포럼 원문 표현이 아니라 해석임을 명시. `RhinoCommon.xml`에 `<since>` 없음 → 'Rhino 6부터'는 포럼 발언 근거임을 1.2·9-7·[S1]에 표기. `Extrusion.Create` since 5.1/8.0, `CreatePatch` since 6.0은 XML로 확인 |
| 6 | PyPI cp39 macOS 휠 2종 | `macosx_14_0_universal2`·`macosx_15_0_universal2` 둘 다 다운로드 확인. 5.1·[S15] 수정 |
| 7 | 벤치마크 변동(Write 4.4→2.8 s, Delaunay 1M 3.53→2.56, 4M 13.0→16.96) | 이 세션 재실행 추가(1M 4.40 s, 4M 18.34 s). 1.3·5.2·8·요약을 범위/근사값(1M 2.6–4.4 s, 4M 13–18 s, Write 약 3–4 s/약 40 MB)으로 표기하고 ±30% 변동 주석 추가 |
| 8 | 4 m 리샘플 점 수 모순(120,904 vs 120,664) | 재집계: 제거 전 120,904, 정확 일치 제거 120,695, 2자리 반올림 120,665 — 중복 제거 방식 차이. '약 12만 점(120,665–120,904)'으로 통일 |
| 9 | '갭·관통·z-fighting 없음' 과장 | CDT(`triangle`) 사용 시로 한정하고 무제약 scipy 경로의 한계(경계 변 미보장) 명시. 요약·1.5·1.6·3.3-A 수정 |
| 10 | 건물 높이 소스 누락(건축HUB) | 공공데이터포털 15134735 열어 확인(무료·이용허락 제한 없음·월간·오퍼레이션 목록). 2.2 표·추천 규칙 2번·요약·9-10 추가. 표제부 필드명은 zip 안이라 확인 필요 |
| 11 | 교량·철도·지하철·옹벽·제방 누락 | 저장소 코드표에서 코드 확인(교량 `A0070000`, 철도 `A0150000` 등 — 검증자가 적은 'B003/A005'는 코드표와 불일치하여 채택하지 않음). VWorld 2D 목록 16페이지 전수 확인 → 전용 레이어 없음. 4.1절 신설, 요약·6.4 레이어 추가 |
| 12 | 서울 1:1000 수치지형도 | 국토정보플랫폼 다운로드 메뉴에 1:1,000 축척 옵션 확인 [S49]. 서울 전역 범위·서울시 자체 배포는 미확인(WebSearch 한도 소진) → 1.1·9-11에 확인 방법과 함께 표기 |
| 13 | 공식 3D 건물 모델 | VWorld 데이터마켓 '3D' 72건 필터만 확인, 목록·형식 미확인; 공공데이터포털 검색에는 없음 → 2.2 표·9-12에 확인 필요로 추가 |
| 14 | 수위 데이터 누락 | 한강홍수통제소 Open API 레퍼런스 열어 URL 패턴·`PFH`·`GDT` 등 필드 확인 [S50]. 1.5·4절·요약·6.4(`LEVEL_SRC`, `PFH_M`) 반영. 홈페이지 기준홍수위 표는 JS라 확인 필요 |
| 15 | 좌표계 점검 누락 | `.prj` 확인·`always_xy=True` datum 변환 분기를 1.1·6.2·7-9에 요건으로 추가. 구 좌표계 EPSG 코드는 1차 출처 미확인이라 '확인 필요' |
| 16 | SIG3D 지하실 대안 | 원문 "If there is information available about cellars, the elevation of the ground surface is set to the lower edge of the floor of the cellar" 확인. 2.1 표에 행 추가, measuredHeight 정의도 인용 |
| 17 | DEM 페이지 세부 | 15059920 재열람: IMG·무료·로그인·"대용량 파일전송 S/W가 필요"·수시 갱신·최종수정 2025-06-17·해상도 미기재 확인. 1.1·9-1 갱신, 2015년 90 m 보도는 현행과 무관할 수 있음 명시 |
