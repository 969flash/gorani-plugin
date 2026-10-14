# 대지검토 패널 — 구현 계약(파일 구성·JS↔Python 메시지·상태 머신)

세 층(`site_ui.html` 프런트 / `panel_host.py` Eto 호스트 / `cmd_site.py` 컨트롤러)이 이 문서의 계약만 보고 독립적으로 작업할 수 있어야 한다. 화면·행동·문안은 `docs/ui_spec.md`, 산출물은 `docs/deliverables.md`, 데이터는 `docs/data_sources.md`. 이 문서가 메시지 계약의 원본이다 — 키를 바꾸면 여기부터 고친다.

- 작성 2026-10-07. 브리지 배관은 `send` 큐·`__flush`·`window.app.receive`.
- 네이밍: CLAUDE.md. 대지 = `lot`(필지도, 합필 대상지도), 요소 = `building`·`road`·`terrain`·`water`·`green`·`rail`, 전체 = `context`, 베이스맵 = `basemap`, 현황도 한 장 = `sheet`, 수치지형도 **도엽** = `topo_sheet`(현황도 `sheet`와 섞지 않는다). 길이 m·면적 ㎡는 접미사 없음. 좌표는 WGS84 `[lng, lat]`(소수 7자리), GeoJSON FeatureCollection = FC. 리스트는 복수형.

## 배경과 목표

- Rhino 8 CPython. 명령 `UrbanSite`/`대지검토` → 떠 있는 모덜리스 창 480×900(리사이즈 가능, 도킹 불가) → WebView 1장이 패널 전부.
- 흐름은 단계형 3단계(① 대상지 → ② 범위·옵션 → ③ 결과). **생성은 Rhino CPython 안에서 동기 실행**(`context_builder.run(request, progress, doc)`, docs/code_map.md 확정 — 서브프로세스·외부 python 없음). 진행률은 콜백 안에서 `host.push` + `Rhino.RhinoApp.Wait()`, 취소는 플래그(콜백이 False를 돌려주면 엔진이 중단·되돌림).
- 프레임워크·빌드 도구 없음. 단일 HTML + 바닐라 JS, Leaflet·Pretendard 인라인, 오프라인.

## 파일 구성

| 파일 | 역할 | Rhino 필요 |
|---|---|---|
| `scripts/cmd_site.py` | 진입 + 컨트롤러. `loader`로 로직 모듈을 읽고 `SitePanelHost(on_command=…)`를 띄운다. 명령(dict)을 받아 로직 함수를 부르고 `host.push()`로 상태를 보낸다. 로직은 없다 | 예 |
| `scripts/panel_host.py` | Eto WebView 호스트. 창·브리지 배관·`push()`만. 로직 모듈을 모른다(현재 파일 그대로) | 예 |
| `scripts/site_ui.html` | 프런트엔드 전부(마크업·CSS·JS). 로직·DB를 모른다. `<!--VENDOR_CSS-->`·`<!--VENDOR_JS-->`·`<!--VENDOR_FONT-->` 자리에 호스트가 vendor를 주입 | 아니오 |
| `scripts/review_map.py` | 지도 데이터 제공자(타일 설정·bbox 필지·GeoJSON). 기존 그대로 | 아니오 |
| `scripts/lot_db.py`, `scripts/pnu_loader.py` | 필지 조회·주소 해석. 기존 그대로 | 아니오 |
| `scripts/context_builder.py` | 엔진: `preflight(request)`(사전 점검 — 범위 링은 `non_rhino_utils.get_extent_ring` 순수 파이썬, 미리보기 = 실제 생성 범위)·`run(request, progress, doc)`·`get_progress_message(...)`. docs/code_map.md §4 | run만 Rhino |
| `scripts/site_prefs.py` | `~/.urbandesigntool/prefs.json`·`source_news.json` 읽기쓰기, 최근 대상지 5건 | 아니오 |
| `scripts/context_baker.py` | Rhino 문서 조작 전부: 베이크(= 생성), `clear_previous`, `import_3dm`(재삽입), 뷰 줌. 베이스맵 .ai는 `basemap_ai.py`가 문서 없이 쓴다. 문서를 만지는 유일한 모듈 | 예 |
| `scripts/dev_check_sources.py` | 브이월드 목록 '새 판' 조회(dsId=18 등) → `~/.urbandesigntool/source_news.json`. **stdlib(urllib)만** 써서 `init`이 Rhino CPython(`sys.executable`)으로 비차단 실행 — `GENERATOR_PYTHON` 없이도 돈다. tmp 파일에 쓰고 `os.replace`(preflight가 쓰는 중 읽어도 깨진 JSON 없음). 네트워크 실패면 파일을 안 쓴다 | 아니오 |
| `scripts/vendor/leaflet.js`·`leaflet.css`·`pretendard.css` | 원본 그대로(@preserve 헤더 유지) | — |
| `tests/test_site_ui_contract.py` | 컨트롤러 조립 함수가 만든 `init_state`·`preflight_result`·`done` 샘플이 이 문서의 키를 갖는지 | 아니오 |

상수(레이어명 `CTX`·`BM`, Export 옵션 문자열 `AI_EXPORT_OPTIONS`, phase 가중치, 예상치 계수, prefs 경로, `BASEMAP_SCALE_LAYERS`(축척별 레이어 on/off 표), `INSTALL_DOC`)는 `scripts/constants.py`에 있다. `GENERATOR_PYTHON`은 없다(서브프로세스 없음).

## JS ↔ Python 브리지(기존 그대로)

### JS → Python (명령)

```js
function send(msg) {
  window.__outbox.push(msg);
  document.title = "bridge" + (++window.__seq);  // Windows WebView2 — title 이벤트
  location.href = "bridge:flush";                // mac WKWebView — DocumentLoading에서 가로챈다
}
window.__flush = function () { var m = JSON.stringify(window.__outbox); window.__outbox = []; return m; };
```

호스트는 두 이벤트(DocumentLoading·DocumentTitleChanged) 어느 쪽이든 `AsyncInvoke` 뒤 `ExecuteScript("return window.__flush();")`로 회수하고, 명령마다 다시 `AsyncInvoke`로 컨트롤러 콜백을 예약한다(이벤트 핸들러 안에서 ExecuteScript 결과를 기다리면 Windows에서 첫 명령이 사라진다 — 2026-09-09 실측). 늦은 신호는 빈 배열이라 무해하다. Windows는 결과가 한 번 더 JSON으로 감싸여 와서 `_get_flush_messages`가 두 겹을 벗긴다.

### Python → JS (푸시)

`webview.ExecuteScriptAsync("window.app.receive(%s);" % json.dumps(msg, ensure_ascii=True))` — 없으면 `ExecuteScript`. JS는 `window.app.receive(msg)` 하나로 받아 `msg.type`으로 분기한다. 모든 푸시는 UI 스레드에서. 서브프로세스 stdout은 `UITimer`가 UI 스레드에서 읽으므로 별도 마샬링이 없다.

### 호스트 규칙(변경 없음)

- 모덜리스 `forms.Form` 480×900 Resizable. 도킹 패널은 CPython 스크립트에서 등록이 안 된다(.rhp 전까지 창 모드).
- HTML은 vendor 주입 후 임시 파일로 써서 `file://`로 연다(`LoadHtml`은 Mac에서 Rhino째 죽는다). file:// 출처라 `localStorage`를 믿지 않는다 → prefs는 Python.
- 같은 패널이 떠 있으면 앞으로 가져온다(`scriptcontext.sticky`).
- 창 닫힘 콜백 → 컨트롤러 `on_close()` → 생성 중이면 `cancel`과 같은 경로.

## 명령 목록 (JS → Python)

| cmd | 페이로드 | 응답 푸시(순서) | 비고 |
|---|---|---|---|
| `init` | — | `init_state` | 창 열림·더보기 메뉴 [다시 확인](같은 명령, 화면 이동 없음). `generator`는 항상 `{ok:true, python:"Rhino CPython", text:"Rhino 내장"}`(서브프로세스 없음 — 키는 UI 호환으로 유지). `dev_check_sources.py`는 P1(없으면 `newer_date:null`). **매번 preflight 메모이즈를 비운다**(키 유무·새 판은 메모 키에 없으므로) |
| `search` | `query`(str) | `search_result` | 주소·지번·PNU. 키 있으면 VWorld 보조(`pnu_loader.search_lots`) |
| `map_lots` | `bbox`[minLng,minLat,maxLng,maxLat], `seq`(int) | `map_lots`(같은 `seq`) | 줌 ≥ 17. JS는 `seq` < 최신이면 버린다 |
| `select_lots` | `pnus`(list, 현재 대상 전체) | `lot_state` / `error{context:"select"}` | 토글마다 전체 목록. 상태 원본은 JS. 빈 배열 = 모두 지움(응답 `lots:[]`) |
| `set_area` | `ring_tm` \| `ring_lnglat` \| `center`+`offsets` (없으면 지움) | `area_state` | 구역 방식. 지도에 그린 링(경위도), Rhino 커브 실제 좌표(`ring_tm`), 지도에서 옮겨 놓은 커브(`center` 경위도 + `offsets` m). 안전장치·안의 필지는 Python(§대상지 방식) |
| `set_point` | `center`([lng,lat], 없으면 지움) | `point_state` | 위치 방식. 지도 클릭·검색 결과 |
| `pick_curve` | — | `curve_shape` | Rhino 전용. 선택된 커브가 하나면 그것, 없으면 고르기 프롬프트 |
| `snap_area` | `ring_tm` | `area_state{snapped:true}` 또는 `area_state{ok:false,text}` | Rhino 전용. 필지 경계에 맞추기 |
| `preflight` | `target`(없으면 `pnus` = 필지 방식), `radius`, `shape`, `paper`, `paper_mm`, `scales`, `seq` | `preflight_result`(같은 `seq`) | ① lots 변경 직후, ② 진입·옵션 변경(300 ms 디바운스). 메모이즈 키 `(tuple(pnus), radius, shape, paper, tuple(paper_mm), tuple(scales))` — `paper_mm`이 빠지면 용지 '직접'에서 가로·세로를 바꿔도 프레임이 안 바뀐다. `init`마다 비운다 |
| `generate` | `target`(없으면 `pnus`), `options`(§옵션 키 **`scales` 포함** — 가장 큰 축척 프레임이 DB 질의 범위를 정한다, code_map §3) | `progress`* ↔ `log`* → `done` / `progress{state:"failed"}` / `progress{state:"cancelled"}` | `context_builder.run` 동기 실행(UI 스레드, 콜백 안 `RhinoApp.Wait()`로 푸시·취소 명령 펌핑). 이미 running이면 무시하고 `error{context:"generate"}`. 베이크가 곧 '문서에 넣기'라 `busy`·`imported`는 오지 않는다(`done.context.imported`로 전한다). 생성기는 BM 레이어를 항상 전부 쓴다 — 축척별 차이는 Export 때만 |
| `cancel` | — | `progress{state:"cancelled"}` 또는 무시 | running이 아니면 **무시**(응답 없음). running이면 `cancel_requested` 플래그만 세운다 — 다음 콜백이 False를 돌려주고 엔진이 `Cancelled`로 중단·이번 베이크 객체 삭제 → `ok=false, cancelled=true`. 부분 폴더 유지, `log.txt`에 "cancelled at <phase>" |
| `import_context` | `dir`(결과 폴더 절대경로) | `busy{on}` → `imported` → `busy{off}` | 재삽입: 같은 `UDT_LOT_KEY` 객체 삭제 후 `context_baker.import_3dm`(`context.json.origin`이 문서 원점과 다르면 차이만큼 이동). `zoom_after_import`면 줌 |
| `export_basemap` | `dir`, `scale`(1000\|3000\|5000) | `busy{on}` → `exported` → `busy{off}` | `context_builder.export_basemap(dir, scale)`: 결과 폴더의 `context.json`(pnus·options)으로 DB에서 다시 `prepare` → `basemap_ai.write_basemap` → `<dir>/basemap_<scale>.ai`. 문서를 거치지 않는다(import 불필요, 1초 안팎). 축척별 레이어 표(`constants.BASEMAP_SCALE_LAYERS`): 1:1000 = `08`(지적선) on · `08b`(지번) on, 1:3000 = `08` on · `08b` off, 1:5000 = `08`·`08b` off. 실패하면 `exported{ok:false, text}` |
| `zoom_view` | `dir`(결과 폴더 절대경로), `center`[lng,lat](선택) | — (`error{context:"open"}`) | `import_context`·`export_basemap`과 같은 꼴 — JS가 `result.dir`을 붙인다(Python은 마지막 결과 폴더를 기억하지 않는다). `center` 없으면 `CTX::Site` 객체로 줌. 있으면 `<dir>/context.json`의 ORIGIN으로 문서 좌표 환산 후 그 점 주변 100 m |
| `open_path` | `path`(str) | — (`error{context:"open"}`) | 절대경로 또는 프로젝트 루트 상대(`docs/data_sources.md`, `.env`, `data`). 폴더 = 탐색기, 파일 = OS 기본 앱. `.env`가 없으면 두 줄 템플릿(`VWORLD_API_KEY=`·`DATA_GO_KR_KEY=`)을 만든 뒤 연다. 외부 URL은 열지 않는다(WebView가 이동하므로 JS에서도 링크 금지) |
| `save_prefs` | `options` | — | `prefs.json`에 `options`만 덮어쓴다(`recent`는 `generate` 성공 시 Python이 갱신) |
| `style_preview` | `dir`, `sheet_id`(0~15), `style`(스타일 dict), `seq` | `style_preview`(같은 `seq`) / `error{context:"style"}` | ③ 결과의 도면 스타일 화면. `context_builder.preview_sheet` — 한 장을 스타일로 다시 그린 SVG 문자열(파일 안 씀). 시트 데이터는 컨트롤러 `_keep`(이번 세션 생성 결과, 지형 삼각형 포함), 없으면 `context.json`으로 한 번 prepare(지형 시트는 비어 나온다). SVG id·`url(#…)`은 `pv_` 접두어(패널 `#map`과 겹치지 않게). JS 250 ms 디바운스, 늦은 `seq`는 버린다 |
| `apply_style` | `dir`, `style` | `busy{on}` → `style_applied` → `busy{off}` | `context_builder.apply_style` — 결과 폴더의 시트 전부 + 이미 쓴 `basemap_<축척>.ai`를 다시 쓰고 `context.json.options.style`을 바꾼다. 지형 삼각형이 없으면 지형 시트 파일은 그대로(`kept`). JS는 성공하면 `options.style`을 `save_prefs` |
| `save_style` | `name`, `style` | `styles` / `error{context:"style"}` | `site_prefs.save_style` → `HOME_DIR/styles/<이름>.json`(경로 문자 제거, 같은 이름 덮어씀). 사무소 표준을 파일로 나눠 쓴다 |
| `sheet_ai` | `dir`, `path`(도면 SVG) 또는 `all:true` | `busy{on}` → `sheet_ai` → `busy{off}` | `sheet_svg.get_sheet_ai` — 도면 SVG를 레이어 .ai로(없거나 SVG보다 오래됐을 때만 다시 쓴다). 한 장이면 쓰고 OS로 연다. 생성 때 .ai를 다 쓰지 않는다(23장이면 Rhino에서 10 s+) |
| `area_packs` | `bbox`([서, 남, 동, 북] 경위도), `seq` | `area_packs` | 지도 이동(600 ms 디바운스)마다. 화면에 걸리는데 아직 안 받았거나 새 판이 나온 시군구 팩 `{seq, missing[{name, label, mb, update}], mb, labels}` — 전부 update면 칩이 '새 판 있음' — 해외·매니페스트 없음·오프라인은 빈 목록. 지도 칩 [받기] |
| `download_data` | `names`(선택 — 없으면 전부) | `data_progress`×N → `init_state` (`error{context:"init"}`) | 지도 칩 [받기](area_packs의 names). 멈추면 그때까지 받은 팩은 남는다. `data_pack`이 매니페스트(`constants.DATA_MANIFEST_URL`)에서 바뀐 팩만 `HOME_DIR/data/`에 받는다. 진행 중 `cancel`이면 그 팩에서 멈추고 `data_progress`로 알린다(받던 팩은 버리고 쓰던 DB는 그대로). 유일한 네트워크 명령(주소 보조검색 제외) |

명령 16개(+ 도면 스타일 3개·도면 .ai 1개, 2026-10-13). `auth_pin`(옛 PIN 인증)은 없다 — 사내 배포라 인증 게이트 없음.

## 푸시 목록 (Python → JS)

### 공통 — 경고·원천 스키마

경고 하나(`warning`)는 어디서 오든 같은 모양이고 JS 렌더 함수 하나가 그린다.

```jsonc
{"level":"info|warn|danger",
 "code":"stale_lot|stale_building|stale_terrain|coverage|no_context_db|no_api_key|invalid_key|height_estimate|mismatch|skipped|empty_buildings|frame_over|multipart",
 "text":"건물 자료 4.9개월 경과 · 새 판 있음",            // 1줄
 "detail":"⚠ 건물 자료가 4.9개월 지났습니다(…) → docs/data_sources.md §0 절차로 교체하세요",  // 펼침(deliverables §C ⑤ 문안)
 "action":{"label":"절차 열기","path":"docs/data_sources.md"},   // 선택. open_path 로 보낸다
 "center":[127.06,37.55]}                                       // 선택. 있으면 ② 지도 flyTo / ③ [Rhino] zoom_view
```

원천 상태 하나(`source`). `init_state`와 `preflight_result`가 같은 모양을 쓴다(`preflight_result`만 `coverage` 채움).

```jsonc
{"id":"lot|building|terrain|api",
 "label":"필지","name":"토지특성정보","date":"2026-05-13",   // date: 레코드 기준일. 수치지형도는 "2024~2026"
 "age_months":4.8,"level":"ok|warn|danger|missing",
 "newer_date":null,                                        // 새 판 기준일. 캐시 없음·조회 실패 = null
 "coverage":{"have":3,"total":4,"missing":[{"topo_sheet":"37705073","dir":"북동","center":[lng,lat]}]},  // terrain만, preflight만. 도엽 = topo_sheet
 "keys":{"vworld":true,"data_go_kr":false},                // api만. VWorld(건물 최신화) · 공공데이터포털(건축HUB 철거·말소)
 "text":"4.8개월"}                                         // 행 오른쪽 짧은 부가. api: "키 2/2" | "브이월드만" | "포털만" | "없음"
```

`level` 규칙(data_sources §2.4): `warn` = 경과 ≥ 노랑 임계 AND `newer_date` 있음, `danger` = 경과 ≥ 빨강 임계(새 판 무관), `missing` = 원천 없음(컨텍스트 DB 없음·키 둘 다 없음), 그 외 `ok`. `api`는 둘 중 하나만 있으면 `warn`(text "브이월드만" — 철거·말소 반영 생략 / "포털만" — 건물 최신화 생략). 생성은 어느 경우도 막지 않는다.

### 푸시 정의

```jsonc
{"type":"init_state",
 "version":"0.1",
 "blocked":false,                                 // true = 필지 DB 없음 → 블로커(차단은 이것뿐. 컨텍스트 DB 없음은 경고)
 "paths":{"root":"<HOME_DIR>","lot_db":"data/seoul_site.db","context_db":"data/seoul_context.db","env":".env","install_doc":"docs/install.md"},
 "generator":{"ok":true,"python":"Rhino CPython","text":"Rhino 내장"},   // 항상 ok. UI 호환용(블로커 3행째는 ✓ 고정)
 "can_download":true,                             // DATA_MANIFEST_URL이 있으면 블로커에 [DB 받기]·[멈추기]
 "sources":[source, source, source, source],      // id = lot, building, terrain, api 순서 고정(헤더 자료 날짜·더보기 메뉴 자료 칸·블로커 체크리스트)
 "warnings":[warning],                            // 더보기 메뉴 자료 칸(no_api_key는 설정 칸 API 키 행). warn·danger면 헤더 자료 날짜 옆 점. 띠로 띄우지 않는다
 "tile":{"url":"…","fallback_url":"…","attribution":"…","abroad_url":"…","abroad_attribution":"…"},   // review_map.get_tile_config(). 지도 중심이 map.korea_bounds 밖이면 abroad_url(OSM)
 "map":{"center":[126.9784,37.5665],"zoom":16},              // review_map.get_map_init()
 "options":{…옵션 키 전부, prefs.json 복원 또는 기본값…},
 "recent":[{"pnus":["…"],"label":"성수동2가 277-17 외 1","total_area":1234.5,"date":"2026-10-06"}],   // 최대 5, 필지 방식만. 더보기 메뉴 [최근 대상지] → 필지 방식으로 select_lots. done 때 JS가 같은 꼴로 앞에 넣는다(다음 init까지)
 "sheet_catalog":[{"id":0,"key":"base","name":"베이스맵","subtitle":"Base map","needs":"lot"},…,{"id":15,"key":"slope","name":"경사","subtitle":"Slope","needs":"terrain"}],   // constants.SHEET_CATALOG 23장(분석도 8 · 현황도 12 · 틀 3). done.sheets[].thumb = 160 px PNG data URI(패널 도면 칸)
 "style_presets":{"std":{"name":"표준","paper":"#FFFFFF",…,"ramp":"warm"},"vivid":…,"mono":…,"dark":…},   // constants.STYLE_PRESETS
 "style_defaults":{"layout":"side","line_scale":1.0,"text_scale":1.0,"font":"sans","fade_outside":0.55,"labels":true,"subtitle_en":true,"project":""},
 "style_ramps":{"warm":["#FBEFC9",…],…},
 "styles":[{"name":"OO건축 표준","style":{…}}]}      // HOME_DIR/styles/*.json

{"type":"search_result","query":"…","seq":null,
 "matches":[{"pnu":"1120010200102770017","address":"서울특별시 성동구 성수동2가 277-17","jibun":"277-17",
             "land_category":"대","area":612.3,"center":[lng,lat]}],   // 0~8건. 1건이면 JS가 바로 select_lots
 "message":"후보 3건"}                                                 // 0건: "찾지 못했습니다 — 동 이름까지 적어 보세요"

{"type":"map_lots","seq":17,"geojson":FC,"truncated":false}
   // properties = {pnu, address, jibun, land_category, area}. review_map.get_parcels_in_bbox 그대로

{"type":"lot_state",
 "lots":[{"pnu":"…","address":"…","jibun":"277-17","land_category":"대","area":612.3,"warn":null}],   // warn: "multipart"|"hole"|null
 "total_area":1234.5,
 "lot_name":"성수동2가_277-17외1",                 // 결과 폴더명·recent 라벨 원본
 "center":[lng,lat],                             // 원점 후보(100 m 내림 전 값)
 "target_geojson":FC,                            // 필지별 role="lot" + 합집합 1개 role="target"
 "warnings":[warning]}                           // code=multipart 등. ① 칩 배지로

{"type":"preflight_result","seq":5,
 "sources":[source×4],                           // coverage 포함
 "extent_geojson":FC,                            // role="extent" 1개(properties.radius, shape)
                                                 // role="topo_sheet" n개(properties.topo_sheet, year, have:bool) — 수치지형도 도엽
                                                 // role="frame" 축척마다 1개(properties.scale, paper, over:bool)
 "estimate":{"buildings":1842,"lots":2310,"topo_have":3,"topo_total":4,"seconds":40,"mb":8},   // topo_* = 도엽
 "empty_sheets":[10],                            // 데이터 없어 빌 시트 id
 "warnings":[warning]}                           // coverage(center 포함)·stale_*·no_api_key·frame_over·no_context_db

{"type":"progress",
 "state":"running|done|failed|cancelled",
 "phase":"query|refresh|terrain|write_3dm|basemap|sheets|tables|import",   // import는 v1 항상 skipped(베이크가 곧 문서에 넣기), refresh는 v1 skipped
 "phase_status":{"query":"done","refresh":"skipped","terrain":"running","write_3dm":"pending",
                 "basemap":"pending","sheets":"pending","tables":"pending","import":"pending"},   // done|running|pending|skipped|failed
 "phase_detail":{"query":"1,842동 · 3도엽","refresh":"건너뜀 — 키 없음","terrain":"12만 점…"},  // 행 오른쪽 짧은 글. 없는 키는 빈칸
                                                 // refresh: "건물 12동 갱신 · 철거 3동 반영" | "건너뜀 — 키 없음" | "건너뜀 — 포털 키 없음(철거 생략)" | "건너뜀 — 네트워크 없음"
                                                 // failed(phase 단위 예외): basemap "생성 실패" 등 — state는 계속 running, 다음 phase로
 "percent":38,
 "error":{"title":"","detail":"","code":""}}     // failed일 때만. code: crs_check|no_lots|exception|cancelled

{"type":"log","text":"여러 줄\n가능","level":"info|warn|error"}
{"type":"busy","on":true,"label":"문서에 넣는 중"}   // Import·Export처럼 UI 스레드가 멈추는 짧은 작업 전후
{"type":"data_progress","text":"서울 필지 받는 중 (1/3) 42% · 1.9 GB"}   // download_data 진행(1 % 단위)·멈춤 안내. 블로커 #data_progress 한 줄
{"type":"error","context":"init|search|select|preflight|generate|import|export|open","text":"한 줄","detail":"traceback 또는 빈 문자열"}

{"type":"done",
 "dir":"/…/result/20261007/성수동2가_277-17외1",
 "lot_name":"성수동2가_277-17외1",
 "elapsed_s":41,
 "options":{…generate에 쓰인 옵션 그대로…},        // dirty 판정·결과 카드 제목
 "context":{"path":"…/context.3dm","layers":12,"buildings":1842,"lots":2310,"demolished":9,"tin_points":5120,
            "origin":[198000.0,551800.0],"imported":true,"import_text":""},
            // imported: import_after 로 이미 넣었는가. 실패면 false + import_text(Rhino 메시지) — 문서 카드는 done만으로 그린다
 "basemap":{"ready":true,"paper":"A1","layers":14,"exported":[]},
            // ready=false: basemap phase 실패 → 카드 안 빨강 1줄 '생성 실패 — [log.txt]', 버튼 비활성
            // exported: 항상 빈 배열로 시작(폴더 스캔 안 함). JS가 exported 푸시로만 누적. 이전 실행의 .ai는 files에만 보인다
 "sheets":[{"id":1,"name":"위치·범위도","path":"…/sheets/01_위치범위도.svg","empty":false,"reason":""},
           {"id":12,"name":"표고 분석도","path":null,"empty":true,"reason":"지형 없음"}],   // reason: "지형 없음" | "데이터 없음" | "오류"(sheets phase 실패)
 "tables":[{"name":"parcels.csv","path":"…"},…],
 "files":[{"name":"context.3dm","path":"…","bytes":18400000},…],   // 산출물 목록(폴더 전체)
 "warnings":[warning],                           // height_estimate·stale_*·mismatch(center)·skipped·invalid_key·empty_buildings·frame_over·coverage
 "quality":{"height_src":{"height":0.34,"grnd_flr":0.27,"topo_flr":0.29,"default":0.10},
            "align":{"median":1.2,"p90":3.9,"n":17581,"low_sample":false},
            "skipped":{"buildings":3,"lots":1},
            "mismatch_count":7,
            "dates":{"lot":"2026-05-13","building":"2026-05-09","terrain":"2024~2026","upis":"2026-09"}},
 "qa_geojson":FC}                                // role="qa_mismatch" 점·선(② 지도 qaLayer). 없으면 빈 FC

{"type":"imported","ok":true,"dir":"…","layers":12,"objects":4120,"replaced":true,"text":""}   // ok=false면 text에 Rhino 메시지. run=running 중(import_after 경로)에는 JS가 무시 — 결과는 done.context에 담겨 온다
{"type":"exported","ok":true,"dir":"…","scale":3000,"path":"…/basemap_3000.ai","text":""}
{"type":"style_preview","seq":3,"sheet_id":0,"svg":"<svg …>","empty":false,"reason":""}   // id는 pv_ 접두어
{"type":"style_applied","ok":true,"dir":"…","sheets":[{id,name,path,thumb,empty,reason}],"basemaps":["…/basemap_5000.ai"],"kept":[14,15],"text":""}
{"type":"sheet_ai","ok":true,"dir":"…","paths":["…/sheets/02_필지규모.ai"]}
{"type":"styles","styles":[{"name":"OO건축 표준","style":{…}}],"saved":"OO건축 표준","dir":"<HOME_DIR>/styles"}
```

푸시 12종. `toast`는 없다 — 성공 토스트는 JS가 `imported`·`exported`를 받아 띄운다.

## 시군구 팩 (2026-10-13)

- 배포 팩은 시군구 단위 `<시군구코드>_<site|context|terrain>.db.xz`(dev_deploy가 시도 DB를 200 m 격자·PNU로 나눈다, 경계 객체는 양쪽에). 런타임은 대상지 범위에 걸리는 파일만 열고 id로 중복을 걷어 낸다.
- 필지 DB가 없을 때 블로커의 [지도에서 지역 골라 받기] — JS `state.dataLater = true`로 블로커를 닫고, 지도를 옮기면 `area_packs` → 칩 [받기] → `download_data{names}`.

## 해외 대상지 (2026-10-13)

- 대상지 중심(구역 링 평균·위치 점)이 `map.korea_bounds` 밖이면 `set_area`·`set_point`가 투영 원점을 그 중심으로 옮긴다(`non_rhino_utils.set_projection`). 이후 `ring_tm`·`center_tm`은 그 지역 횡메르카토르 m이다. `select_lots`는 늘 EPSG:5186으로 되돌린다.
- `preflight`·`generate`는 해외면 필지 DB를 보지 않고 `osm_context`(Overpass·지형 타일·인터넷 필요)를 쓴다. 필지가 필요한 시트는 빈 시트, 경고 `abroad`.
- 블로커(필지 DB 없음)에 [DB 없이 해외 대상지로 계속] — JS `state.abroadOnly = true`, 필지 방식 칸 비활성(필지 방식이었으면 위치 방식으로), 이후 `init_state.blocked`를 무시한다.
- `search`: 국내 필지에서 못 찾거나 필지 DB가 없으면 OSM Nominatim 지명 후보 — `matches[].pnu = ""`, `center` 있음. JS는 위치 방식이면 `set_point`, 아니면 지도만 옮긴다.

## 대상지 방식 (2026-10-10)

① 첫 화면은 지도다(2026-10-14 — 소개·방식 고르기 화면 없음). 지도 위 도구줄의 방식 칸 [필지·구역·위치]로 바꾸고, 처음엔 마지막 방식(`options.mode`, 저장된 옵션 그대로). 방식을 바꾸면 대상지를 지우고 `init_state.modes.defaults[mode]`(constants `MODE_DEFAULTS` — 필지 200 m·1:1000 / 구역 500 m·1:3000 / 위치 용지 프레임·1:5000)를 옵션에 덮고 `save_prefs`. [새 대상지]는 대상지만 지우고 같은 방식의 지도로.

| 방식 | 요청 `target` | 대상지 경계(`site_rings`) | 대상 필지 | 결과 폴더명 |
|---|---|---|---|---|
| lots 필지로 고르기 | `{mode:"lots", pnus}` | 필지마다 가장 넓은 조각 외곽 | 고른 필지 | `성수동2가_333-139(외n)` |
| area 구역 그리기 | `{mode:"area", ring:[[x,y]] EPSG:5186}` | 구역 링 1개 | 면적 50 % 이상이 구역 안인 필지(`AREA_LOT_MIN_FRACTION`) | `<중심 필지 동_지번>_구역` |
| point 위치만 찍기 | `{mode:"point", center:[x,y]}` | 없음 | 없음 | `<가장 가까운 필지>_일대` |

- 구역 안전장치(`non_rhino_utils.get_ring_problem`): 꼭짓점 3~2000개, 자기교차 없음, 면적 ≥ 100 ㎡, bbox 긴 변 ≤ 4 km. Rhino 커브는 추가로 닫힘·XY 평면(법선 ±Z)·`Intersection.CurveSelf` 0을 본다(`context_geometry.get_curve_ring`). 곡선 커브는 0.05 m 허용오차 폴리라인으로 바꾼다.
- Rhino 커브 위치: 이 도구가 만든 문서(문서 원점 있음)면 로컬 + 원점, 아니면 좌표가 서울 EPSG:5186 범위(`SEOUL_TM_BOUNDS`)면 그대로 = `located:true` → 패널이 바로 `set_area{ring_tm}`. 그 밖이면 모양만(`offsets` m) → 패널이 화면 가운데에 파란 구역을 고정해 얹고, 사용자가 지도를 끌어 맞춘 뒤 [여기에 놓기] → `set_area{center, offsets}`. 모양은 m 그대로라 축척이 변하지 않는다.
- 필지 경계에 맞추기: (구역 ∪ 50 % 이상 필지) − (걸쳤지만 50 % 미만 필지). 도로·하천·구거·철도용지·제방(`AREA_SNAP_LINEAR_CATEGORIES`)은 더하지도 빼지도 않아 그린 선이 그대로 가로지른다 — 구역계 관행.
- 범위 형태(2026-10-10 버퍼 제외): lots = circle|rect, area = site|circle|rect(site = 그린 경계 그대로가 범위, 기본), point = frame|circle|rect(`SHAPES_BY_MODE`). 엔진은 buffer도 받는다(예전 요청). frame = 가장 큰 축척 용지 프레임 사각형.

```jsonc
{"type":"area_state","ok":true,"text":"",            // ok=false면 text 한 줄(자기교차·너무 작음…) — 패널은 이전 구역을 유지한다
 "ring_tm":[[x,y]],"ring_lnglat":[[lng,lat]],"center":[lng,lat],"center_tm":[x,y],"offsets":[[dx,dy]],
 "area":60000.0,"lots":69,"lots_area":44242.0,"lot_name":"성수동2가_333-139_구역",
 "target_geojson":FC,                                 // role="target" 안의 필지 + role="area" 구역 1개
 "warnings":[warning],"snapped":false}
{"type":"point_state","ok":true,"center":[lng,lat],"center_tm":[x,y],"lot_name":"성수동2가_333-139_일대"}
{"type":"curve_shape","ok":true,"text":"","located":false,"ring_tm":[],"offsets":[[dx,dy]],"area":22800.0,"vertices":4}
```

## 결과 좌표 (`options.placement`)

- `origin`(기본): 대상지 중심(100 m 내림)을 Rhino (0,0)으로. 같은 문서의 다음 대상지는 문서 원점을 재사용(20 km 안).
- `world`: EPSG:5186 좌표 그대로. 형상은 대상지 근처 로컬에서 만들고 베이커가 계산 원점만큼 옮긴다(메시는 배정밀도 정점 — 단정밀도는 55만 m에서 6 cm 단위). 문서 원점 기록은 (0,0).
- 문서 원점 (0,0) = 실제 좌표 문서. 방식이 다른 문서에 생성하면 `placement_mismatch`로 중단, 다시 넣기(Import)도 거부한다.

## 옵션 키(`generate.options` = `save_prefs.options` = `init_state.options`)

```jsonc
{"mode":"lots","placement":"origin",                 // mode = 마지막 방식(첫 화면 방식 칸 초깃값). placement origin|world
 "radius":500,"shape":"circle",                       // circle|rect|frame|site(+예전 buffer). radius 100~2000
 "flatten_site":false,"flatten_level":"mean",          // 대상지 평탄화(lots·area) — 높이 = 대상지 경계 자연 지반 mean|min|max
 "site_output":"curve",                                // 대상지 표시(lots·area): curve = 경계 커브만, mesh = 바닥 메시도(CTX::Site::ground). 방식 기본: 필지 mesh, 구역 curve
 "import_after":true,                                  // context.3dm은 항상 쓴다(산출물의 뼈대, 수 초). 끌 수 있는 건 Import뿐
 "make_basemap":true,"paper":"A3","paper_mm":[420,297],"scales":[5000],"basemap_layers_on":[],   // A3 가로 = 분석도 템플릿 기준(2026-10-13)   // "02b_landuse"|"05_road_center"|"11_zoning"
                                                       // scales: ② 프레임 미리보기·③ .ai select 기본값 전용(prefs·preflight에만). generate 페이로드에서 JS가 뺀다. dirty 판정 제외
 "make_sheets":true,"sheet_ids":[0,1,…,22],"floor_breaks":[12,20],"elev_preset":"20m",   // "20m"|"50m". 카탈로그에 없는 id는 엔진이 버린다(get_sheet_ids)
 "make_tables":true,
 "include_minor_buildings":false,"demolished":"dashed","refresh_buildings":true,"include_api_objects":false,   // demolished: dashed|exclude
 "include_zoning":false,"terrain_vertex_color":false,
 "make_dwg":false,                                     // 3dm 2D 도면(BM::)만 basemap_<축척>.dwg로도 저장(고급 > 3dm). 결과 경로는 done.context.dwg
 "zoom_after_import":true,
 "usage_stats":true,                                   // 사용 통계 보내기 — 더보기 메뉴 설정의 체크박스(고지문 포함). generate에 실려도 엔진은 무시
 "style":{"preset":"std"}}                              // 도면 스타일 — 사용자가 고른·바꾼 값. 해석은 sheet_svg.get_style(STYLE_*): 색 10개(paper·block·road·green·water·building·rail·site·extent·ink),
                                                       // ramp, layout(side|bottom|map), line_scale, text_scale, font(sans|serif), fade_outside, labels, subtitle_en, project, name(저장한 스타일)
```

27개. 모르는 키는 Python이 무시하고 빠진 키는 기본값(constants)으로 채운다. `generate`는 `pnus`를 옵션 밖 별도 키로 받는다(옵션은 대상지와 독립이어야 prefs로 재사용된다). **`scales`는 `generate`에도 포함한다**(code_map §3: 가장 큰 프레임이 질의 범위) — dirty 판정에서는 여전히 제외.

## 상태 머신

**단계(2026-10-10 4단계)**: ① 대상지(방식·필지/구역/위치) → ② 범위(지도가 화면 대부분 — 형태·반경·용지·축척·예상만) → ③ 옵션(지도와 무관: 좌표·대상지 평탄화·산출물·자료 상태·고급) → ④ 결과. 아래 표의 'step 2 [생성 시작]'은 이제 step 3에서, 'step 3'(결과)은 step 4다.

JS 상태 두 축: `step ∈ {1,2,3,4}`, `run ∈ {idle, running, done, failed, cancelled}` + `blocked`·`dirty`. `document.body.dataset.step/run`으로 노출해 CSS가 섹션 표시·`fieldset[disabled]`·푸터 라벨을 처리한다.

| 현재 | 이벤트 | 다음 | 부수 효과 |
|---|---|---|---|
| (시작) | `init_state.blocked=true` | blocked | 블로커 표시(필지 DB 없음 또는 `generator.ok=false`). [다시 확인] → `init` |
| (시작) | `init_state.blocked=false` | step 1, run idle | 검색줄 포커스. options·recent 복원 |
| 초기화 뒤 어디서나 | `init_state`(배지 클릭·[다시 확인]) | 변화 없음 | `sources`·`warnings`·`tile`·`paths`·`generator`(·`blocked`)만 갱신. **`step`·`run`·`lots`·`options`·`result`는 건드리지 않는다.** ②에 있으면 `preflight`를 다시 보낸다(Python 메모이즈가 비워졌으므로 자료 상태가 바뀐다) |
| step 1 | 방식 칸(다른 방식) | step 1 | 대상지 지움·방식 기본값 적용·`save_prefs`. 방식별 트레이(필지 목록 / 구역 도구 / 위치) |
| step 1 | `lot_state.lots ≥ 1` / `area_state.ok` / `point_state.center` | step 1 | `preflight` 전송. [다음]·[바로 생성] 활성(그리기·옮기기 중에는 비활성) |
| step 1 | [다음] | step 2 | 지도 컨테이너 이동. `preflight`(메모이즈 적중이면 즉시) |
| step 1 | [바로 생성] (preflight warn/danger 없음) | step 3, run running | `generate` |
| step 2 | 옵션 변경 | step 2 | `save_prefs`(500 ms) · `preflight`(300 ms) · run=done이면 `dirty=true` |
| step 2 | [생성 시작] | step 3, run running | `generate`, `dirty=false` |
| step 3 running | `progress{state:"done"}` → `done` | step 3, run done | 결과 렌더. "생성 완료" 낭독. Python이 `recent` 갱신 |
| step 3 running | `progress{state:"failed"}` | step 3, run failed | 오류 카드. 푸터 [뒤로][다시 시도] |
| step 3 running | [취소] / Esc / 창 닫기 | step 3, run cancelled | `cancel`. `progress.phase === "import"` 또는 `busy.on`이면 [취소]·Esc 비활성(툴팁 "문서에 넣는 중에는 취소할 수 없습니다") |
| step 3 failed/cancelled | [다시 시도] | step 3, run running | `generate` 같은 payload |
| step 3 failed/cancelled | [뒤로] | step 2 | run 유지(스텝퍼 ③ 도달 가능) |
| step 3 done | [옵션 바꿔 다시] / 스텝퍼 ② | step 2 | lots·result 유지 |
| step 3 done | [새 대상지] / 스텝퍼 ① | step 1, run idle | lots·preflight·result 초기화, options 유지, `select_lots{pnus:[]}` |
| step 2 (run done, dirty) | 스텝퍼 ③ | step 3 done | "이전 결과 — 설정이 바뀜" 띠 |
| 어디서나 | `import_context`·`export_basemap`·`open_path`·`zoom_view` | 변화 없음 | 카드 안 버튼 상태만 |

스텝퍼 가드: `canGo(s) = s <= maxReached && run !== "running" && !(s === 3 && run === "idle")`.

Python 쪽 상태는 `running`과 `cancel_requested`(bool) 둘. `generate`는 `running`이 아닐 때만 받고 플래그를 내린다. 결과 폴더·원점 같은 '마지막 결과'는 기억하지 않는다 — 결과에 대한 명령(`import_context`·`export_basemap`·`zoom_view`)은 JS가 `dir`을 붙인다.

## 오류 규약

- 도메인 예외(`ValueError`·`KeyError`·`FileNotFoundError`·`RuntimeError`)는 `text`만, 그 외는 `detail`에 traceback. 컨트롤러의 `_guard(context, fn)` 하나가 전부 받는다 — 호스트 `_run_command`까지 예외가 새면 .NET 델리게이트에서 Rhino가 죽는다.
- 생성 중 오류는 `error`가 아니라 `progress{state:"failed", error:{…}}`로 온다(phase 행에 ✗를 찍어야 하므로). 서브프로세스 비정상 종료(returncode ≠ 0, `done` 없음)도 같다: stderr 마지막 20줄을 `error.detail`에.
- `error.context`로 JS가 표시 자리를 고른다: `generate`→③ 오류 카드, `import`→문서 카드, `export`→베이스맵 카드, `search`→검색줄 아래, `select`→칩 영역, `preflight`→자료 상태 1줄("확인 실패 — 생성은 가능"), `open`·`init`→헤더 아래 띠. 오류는 토스트로 띄우지 않고 사라지지 않는다. 모든 오류는 로그에도 남긴다.
- `imported{ok:false}`·`exported{ok:false}`는 `error`가 아니라 그 카드 안 빨강 1줄. Import 실패 문구에는 `context.3dm` 절대경로를 넣는다(수동 Import 가능).
- 생성 중단 조건은 단 둘: CRS 자가검사 실패(중앙값 > 0.5 m, `code:"crs_check"`)와 범위 안 필지 0건(`code:"no_lots"`). 그 외 전부 경고로 계속.
- **phase 단위 예외**(basemap·sheets·tables 등이 통째로 실패): `phase_status[phase]="failed"` + `warning{level:"danger", code:"skipped", text:"베이스맵 레이어 생성 실패"}` + `log{level:"error"}` 후 다음 phase로 계속. state는 running → `done`(failed가 아님). 결과에는 `basemap.ready:false` / 시트 `empty:true, reason:"오류"` / `tables:[]`로 드러난다.
- Import 실패(`import_after` 경로)는 `imported{ok:false}` 대신 `done.context.imported:false` + `import_text`(Rhino 메시지)로 전한다. JS는 run=running 중의 `imported`를 무시한다 — `done`이 오기 전엔 그릴 문서 카드가 없다. ③ [다시 넣기] 경로(`import_context`)에서는 `imported`가 카드를 갱신한다.
- 생성기 python3 없음(`init_state.generator.ok=false`)은 블로커(필지 DB와 같은 급). ③까지 가서 'returncode≠0'로 보이게 두지 않는다.

## 진행률 규약

- 엔진 콜백 `progress(phase, fraction, text) -> bool` 하나. 컨트롤러가 `context_builder.get_progress_message(phase, fraction, text, skipped, details)`로 `progress` 페이로드를 만들어 `host.push` → `Rhino.RhinoApp.Wait()`(WebView 이벤트·`cancel` 명령 펌핑) → `return not cancel_requested`.
- phase 8개 고정 순서: `query`(prepare: 필지·건물·지형 조회) → `refresh`(v1 `skipped`, detail "건너뜀 — v1 미구현") → `terrain`(TIN·면 분류·투영·압출·커브) → `write_3dm`(CTX 베이크 + `WriteFile` 사본 + context.json) → `basemap`(`basemap_ai`가 .ai 직접 작성, 축척마다) → `sheets` → `tables` → `import`(**항상 `skipped`**, detail "베이크로 대체"). 옵션으로 꺼진 phase는 처음부터 `skipped`로 보내고 `percent` 분모에서 뺀다. 가중치 `constants.PHASE_WEIGHTS`.
- 각 phase 시작·끝 최소 1회, 긴 루프(건물 200동·시트 1장)마다 콜백. `log`는 묶어서(최대 10줄/푸시).
- 취소: `cancel_requested=True` → 다음 콜백 False → 엔진 `Cancelled` → 이번 베이크 객체 삭제 → `progress{state:"cancelled"}` 1회. 부분 폴더 유지, `log.txt`에 "cancelled at <phase>". 베이크·WriteFile 같은 원자 구간 안에서는 콜백이 없어 그 구간이 끝난 뒤 취소된다.
- 경과 시간은 JS 타이머. 스피너 금지.
- **확인 필요(M4 첫 항목)**: `RhinoApp.Wait()`가 Mac WKWebView(Eto) 이벤트를 펌핑하는가. 안 되면 `prepare`(Rhino 금지)만 `threading.Thread`로 돌리고 push는 `Application.Instance.AsyncInvoke`, 베이크부터는 UI 스레드.

## 설정 저장 위치

`HOME_DIR`(constants) = 저장소·폴더 배포판처럼 루트에 `data/`가 있으면 루트, Yak 설치본이면 `~/UrbanDesignTool`(패키지 폴더는 업데이트 때 바뀐다). `open_path`의 상대경로는 `HOME_DIR` 기준이고, 거기 없으면 코드 루트(`docs/install.md` 등)를 본다.

| 파일 | 내용 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| `~/.urbandesigntool/prefs.json` | `{"options":{…20키…}, "recent":[{pnus,label,total_area,date}×5]}` | `save_prefs`(options), `generate` 성공(recent 앞에 삽입·중복 제거·5개) | `init` |
| `~/.urbandesigntool/source_news.json` | `{"checked_at":"2026-10-07","building":{"newer_date":"2026-09-09"},"lot":{…},"upis":{…}}` | `dev_check_sources.py`(P1. 없으면 `newer_date:null`) | `preflight`·`init`(배지)·생성기(`done.warnings`) |
| `~/.urbandesigntool/client_id` | 무작위 UUID 한 줄(사용 통계 설치 식별) | `usage_stats.get_client_id`(없으면 생성) | `usage_stats` |
| `.env`(`HOME_DIR`) | `VWORLD_API_KEY=…`(건물 최신화) · `DATA_GO_KR_KEY=…`(건축HUB 철거·말소). `= ` 뒤 공백 금지 | 사용자(OS 편집기). 없으면 `open_path`가 두 줄 템플릿 생성 | `pnu_loader._read_local_env_value`(strip)·생성기 |
| `HOME_DIR/data/*.db`·`packs.json` | 필지·컨텍스트·등고선 DB. `packs.json` = 받은 팩의 sha256 | `download_data` | `init`·전 명령 |
| `HOME_DIR/result/<YYYYMMDD>/<lot_name>/` | deliverables §E. 같은 폴더가 있으면 생성기 시작 시 `sheets/`·`tables/`·`context.3dm`·`context.json`을 지우고 새로 쓴다(이전 옵션의 시트·CSV가 새것처럼 남지 않도록). `basemap_*.ai`(사용자가 만든 것)·`log.txt`(이어 쓰고 구분선)는 보존 | 생성기·베이커(.ai) | `done`·`open_path` |

`localStorage`·쿠키는 쓰지 않는다(file:// 임시 파일 출처).

## 컨트롤러(cmd_site) 동작 규칙

- 명령 처리기는 `{"init": self._init, "search": …}` dict 하나. 모르는 cmd는 `error{context:"init"}`.
- `init`: DB 존재·기준일(`lot_db` `data_sources` 테이블, 컨텍스트 DB `source_files`), 키 유무(`VWORLD_API_KEY`·`DATA_GO_KR_KEY` 각각), 타일·지도 초기값, prefs, 시트 카탈로그 → `init_state`. `blocked = not lot_db`. preflight 메모이즈 비움. 네트워크 접근 없음.
- `preflight`: `context_builder.preflight({"pnus", "options"})` → dict. 메모이즈 키 = `(tuple(pnus), radius, shape, paper, tuple(paper_mm), tuple(scales))`. `init`마다 비움. 응답에 요청 `seq` 에코.
- `generate`: `context_builder.run({"pnus", "options"}, progress_callback, doc)`를 UI 스레드에서 동기 호출. 콜백 = push + `RhinoApp.Wait()` + 취소 플래그 확인. 응답 dict에 `type:"done"`을 붙여 push(ok=false면 `progress{state:"failed"|"cancelled"}`). 성공 시 `recent` 갱신.
- Rhino 문서 변경 후 `doc.Views.Redraw()`. 문서 조작은 `context_baker`만.
- 창 닫힘: running이면 `cancel_requested=True`(다음 콜백에서 중단).

## 프런트엔드(site_ui.html) 요점

레이아웃·문안·토큰은 `docs/ui_spec.md` §4·§5·§9. 여기서는 계약에 직접 걸리는 것만.

- 상태: `state = {step, run, blocked, dirty, lots, lotState, options, preflight, progress, result, seq:{map, preflight}}`. `render()`는 **step 전환 때만** 섹션 `innerHTML`을 다시 그린다(`body.dataset` 갱신 + 해당 섹션 템플릿 1회 + 지도 컨테이너 이동). 푸시 핸들러는 섹션을 다시 그리지 않고 **슬롯 요소만 교체**한다 — 입력 중 포커스·IME 조합·열린 `<details>`·로그 스크롤이 날아가지 않도록. 옵션 입력은 네이티브 폼 요소라 값 보존 코드가 필요 없다. 가상 DOM 없음.
- `receive` 핸들러 표(슬롯만 교체): `init_state`→첫 수신이면 상태 복원·`render()`; 이후는 `#badges`·`#menu`(열려 있으면)·블로커·`state.generator`만(step·run·lots·options·result 불변, ②면 `preflight` 재전송) / `search_result`→`#search_list` 또는 즉시 `select_lots` / `map_lots`→`seq` 검사 후 `lotsLayer` 교체 / `lot_state`→`#lot_chips`·합계·`targetLayer`·`preflight` 전송 / `preflight_result`→`seq` 검사 후 `#estimate`·`#data_status`·`extentLayer`·`topoLayer`·`frameLayer`·[바로 생성] 노출 / `progress`→`#phase_list`·progressbar 속성·[취소] 활성(phase≠import) / `log`→`<pre>` append(400줄) / `busy`→푸터 잠금·라벨·[취소] 비활성 / `done`→③ 섹션 1회 렌더·`qaLayer` / `imported`(run≠running일 때만)·`exported`→카드 안 슬롯·토스트 / `error`→`context` 슬롯.
- Leaflet 인스턴스 1개. ①↔② 사이 `#map` 컨테이너를 `appendChild`로 옮기고 `invalidateSize()`. `map.remove()` 금지. 줌 ≥ 17에서만 `map_lots`(moveend 250 ms 디바운스, `seq` 증가). `tileerror` 3회 → `fallback_url`로 `setUrl` 1회; 폴백 뒤에도 3회면 지도 위 칩 "지도 타일을 못 받음(오프라인) — 필지선만 표시"를 띄우고 더 전환하지 않는다(필지는 로컬 DB라 계속 동작).
- 경고 렌더 `renderWarnings(warnings, slotEl, {mapClick})` 하나. `center` 있으면 ②에서는 flyTo, ③에서는 [Rhino] = `zoom_view{dir: result.dir, center}`(`result.context.imported`일 때만 활성).
- `generate` 페이로드: `{pnus, options}`에서 `options.scales`를 뺀다. dirty 판정은 `done.options` vs 현재 `options`(둘 다 `scales` 제외) 얕은 비교.
- ③ 베이스맵 카드 축척 select는 1000·3000·5000 고정, 기본값 `options.scales[0]`. `basemap.ready=false`면 카드 안 빨강 1줄 '생성 실패 — [log.txt]' + 버튼 비활성.
- `?mock=1`: `send`를 콘솔 출력으로 바꾸고 `tests/fixtures/site_ui_mock.json`의 메시지를 순서대로 `receive`에 흘린다(`init_state` → `lot_state` → `preflight_result` → `progress`×3 → `done`). vendor는 상대 경로로 로드.

## 플랫폼 주의(기존 그대로)

- Mac WKWebView / Windows WebView2. `bridge:` 내비게이션은 DocumentLoading에서 취소되므로 실제 이동은 없다.
- Import·Export 중 WebView도 멈춘다(같은 UI 스레드). `busy` 푸시 → `AsyncInvoke`로 작업 예약 순서를 지켜야 busy가 먼저 그려진다. 생성 서브프로세스 중에는 멈추지 않는다.
- `ExecuteScript`는 Eto가 함수로 감싼다 — `return …;` 형태로.
- Windows 배포판은 flush 결과가 이스케이프된 채 한 겹 더 감싸여 온다(`_get_flush_messages`가 처리).

## 검토 반영

2026-10-07 검토 13건을 반영했다. `docs/ui_spec.md`와 같은 내용으로 맞췄다.

- 생성기 python3 점검: `init_state.generator{ok, python, text}` 추가, `blocked`에 생성기 없음 포함(필지 DB와 같은 급). `constants.GENERATOR_PYTHON`·`INSTALL_DOC` 추가 명시. `dev_check_sources.py`는 stdlib(urllib)만 쓰고 Rhino CPython으로 띄우며 tmp → `os.replace`.
- `make_context` 삭제(옵션 21→20). `context.3dm`은 항상 쓴다. `write_3dm`은 꺼지는 phase에서 제외.
- `zoom_view {dir, center?}` — JS가 `result.dir`을 붙인다. Python은 마지막 결과를 기억하지 않는다.
- `init` = 배지 클릭 = [다시 확인] 하나. 초기화 뒤의 `init_state`는 `sources`·`warnings`·`tile`·`paths`·`generator`만 갱신(상태표 1행 추가). Python은 `init`마다 preflight 메모이즈를 비운다.
- 부분 실패 규칙: phase 단위 예외는 `phase_status=failed` + `warning{skipped}` + log 후 계속, state는 `done`. `done.basemap.ready:false`, 시트 `reason:"오류"`, `done.context.import_text` 추가. running 중 `imported`는 JS가 무시.
- 오프라인: `GENERATOR_HTTP_TIMEOUT`(5 s, 재시도 0), 첫 호출 실패 시 `refresh`=skipped "건너뜀 — 네트워크 없음". 타일은 폴백 뒤에도 실패하면 칩 1줄, 더 전환 없음.
- preflight 메모 키에 `tuple(paper_mm)` 포함.
- 재생성 시 `sheets/`·`tables/`·`context.3dm`·`context.json` 초기화, `.ai`·`log.txt` 보존. `done.basemap.exported`는 빈 배열로 시작, `exported` 푸시로만 누적.
- `source(api).keys{vworld, data_go_kr}` 추가, text "키 2/2"/"브이월드만". `.env` 템플릿 두 줄. `refresh` phase_detail에 철거 반영/포털 키 없음 문구.
- 도엽 = `topo_sheet`: `estimate.topo_have/topo_total`, `coverage.missing[].topo_sheet`, `extent_geojson` role=`topo_sheet`, JS `topoLayer`.
- `render()`는 step 전환 때만 섹션 재렌더, 푸시 핸들러는 슬롯만 교체.
- `scales`는 prefs·preflight 전용(② 프레임·③ select 기본값). `generate`에서 JS가 뺀다. `export_basemap`에 `BASEMAP_SCALE_LAYERS` 표 명시. `done.basemap.scales` 삭제.
- 취소 경합: `cancel`은 `running`이 아니면 무시. `cancel_requested` 플래그가 있으면 `done` 조립 안 함. JS는 `phase==="import"`·`busy.on`이면 [취소] 비활성.


## 아키텍처 정합 (2026-10-07, code_map 확정 반영)

- 생성 서브프로세스·`GENERATOR_PYTHON`·`dev_generate_context.py`·`UITimer` stdout 읽기 삭제 → `context_builder.run` in-process + 콜백. `site_preflight.py`→`context_builder.preflight`, `site_baker.py`→`context_baker`. `init_state.generator`는 항상 ok(UI 호환). `generate` 페이로드에 `scales` 포함. phase `import`는 항상 skipped. 범위 링은 `non_rhino_utils.get_extent_ring` 하나(RhinoCommon Offset 경로 없음). `preflight_result.estimate`에 1:5000 프레임이면 '수십 초' 경고.

## 사용 통계(`usage_stats.py`)

GA4 Measurement Protocol로 데몬 스레드에서 보내고 실패는 버린다. `constants.GA_MEASUREMENT_ID`·`GA_API_SECRET`이 비었거나 `options.usage_stats=false`면 보내지 않는다. 고지·끄기는 헤더 [≡] 메뉴(`renderMenu` — 이 표와 같게 유지).

| 이벤트 | 보내는 곳 | 매개변수 |
|---|---|---|
| `panel_open` | 첫 `init` | `version`·`rhino`·`has_lot_db`·`packs`(받은 시군구 필지 팩 수) |
| `build` | `generate` 끝(성공·실패·취소) | `mode`·`lng`·`lat`·`korea` + 필지 `pnus`·`pnus_2`…(5개씩 최대 20필지)·`lot_count`·`area` / 구역 `area`·`width`·`height`(링은 보내지 않는다) + `result`·`error`·`elapsed_s`·`radius`·`shape`·`placement`·`buildings` |
| `pack_download` | `download_data` 끝 | `packs`(시군구 코드)·`count`·`requested` |
| `error` | `_guard`의 예상 밖 예외 | `context`·`error`(예외 타입명) |

모든 이벤트에 `session_id`(패널 하나)·`engagement_time_msec`, 요청에 `device`(OS·언어). GA 보고서에서 매개변수를 보려면 관리 > 맞춤 정의에 이벤트 범위 측정기준으로 등록한다.
