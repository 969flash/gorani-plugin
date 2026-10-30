# Gorani 패널 — 구현 계약(파일 구성·JS↔Python 메시지·상태 머신)

세 층(`site_ui.html` 프런트 / `panel_host.py` Eto 호스트 / `cmd_site.py` 컨트롤러)이 이 문서의 계약만 보고 독립적으로 작업할 수 있어야 한다. 화면·행동·문안은 `docs/ui_spec.md`, 산출물은 `docs/deliverables.md`, 데이터는 `docs/data_sources.md`. 이 문서가 메시지 계약의 원본이다 — 키를 바꾸면 여기부터 고친다.

- 작성 2026-10-07. 브리지 배관은 `send` 큐·`__flush`·`window.app.receive`.
- 네이밍: CLAUDE.md. 대지 = `lot`(필지도, 합필 대상지도), 요소 = `building`·`road`·`terrain`·`water`·`green`·`rail`, 전체 = `context`, 베이스맵 = `basemap`, 현황도 한 장 = `sheet`, 수치지형도 **도엽** = `topo_sheet`(현황도 `sheet`와 섞지 않는다). 길이 m·면적 ㎡는 접미사 없음. 좌표는 WGS84 `[lng, lat]`(소수 7자리), GeoJSON FeatureCollection = FC. 리스트는 복수형.

## 배경과 목표

- Rhino 8 CPython. 명령 `Gorani` → 떠 있는 모덜리스 창 480×900(리사이즈 가능, 도킹 불가) → WebView 1장이 패널 전부.
- 흐름은 2화면(지도: 대상지·범위·3D 설정 → 결과: 3D 진행·완료 → 2D 추가, 2026-10-19 — `docs/ui_spec.md`). 3D(`generate`)와 2D(`make_2d`)는 따로 만든다. **생성은 Rhino CPython 안에서 동기 실행**(`context_builder.run(request, progress, doc)`, docs/code_map.md 확정 — 서브프로세스·외부 python 없음). 진행률은 콜백 안에서 `host.push` + `Rhino.RhinoApp.Wait()`, 취소는 플래그(콜백이 False를 돌려주면 엔진이 중단·되돌림).
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
| `scripts/site_prefs.py` | `~/.gorani/prefs.json`·`source_news.json` 읽기쓰기, 최근 대상지 5건 | 아니오 |
| `scripts/context_baker.py` | Rhino 문서 조작 전부: 베이크(= 생성), `clear_previous`, `import_3dm`(재삽입), 뷰 줌. 베이스맵 .ai는 `basemap_ai.py`가 문서 없이 쓴다. 문서를 만지는 유일한 모듈 | 예 |
| `scripts/dev_check_sources.py` | 브이월드 목록 '새 판' 조회(dsId=18 등) → `~/.gorani/source_news.json`. **stdlib(urllib)만** 써서 `init`이 Rhino CPython(`sys.executable`)으로 비차단 실행 — `GENERATOR_PYTHON` 없이도 돈다. tmp 파일에 쓰고 `os.replace`(preflight가 쓰는 중 읽어도 깨진 JSON 없음). 네트워크 실패면 파일을 안 쓴다 | 아니오 |
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
| `init` | — | `init_state` | 창 열림·더보기 메뉴 [다시 확인](같은 명령, 화면 이동 없음). `generator`는 항상 `{ok:true, python:"Rhino Python", text:"Rhino 내장"}`(Blender면 Blender)(서브프로세스 없음 — 키는 UI 호환으로 유지). `dev_check_sources.py`는 P1(없으면 `newer_date:null`). **매번 preflight 메모이즈를 비운다**(키 유무·새 판은 메모 키에 없으므로) |
| `search` | `query`(str) | `search_result` | 주소·지번·PNU. 키 있으면 VWorld 보조(`pnu_loader.search_lots`) |
| `map_lots` | `bbox`[minLng,minLat,maxLng,maxLat], `seq`(int) | `map_lots`(같은 `seq`) | 줌 ≥ 17. JS는 `seq` < 최신이면 버린다 |
| `select_lots` | `pnus`(list, 현재 대상 전체) | `lot_state` / `error{context:"select"}` | 토글마다 전체 목록. 상태 원본은 JS. 빈 배열 = 모두 지움(응답 `lots:[]`) |
| `set_area` | `ring_tm` \| `ring_lnglat` \| `center`+`offsets` (없으면 지움) | `area_state` | 구역 방식. 지도에 그린 링(경위도), Rhino 커브 실제 좌표(`ring_tm`), 지도에서 옮겨 놓은 커브(`center` 경위도 + `offsets` m). 안전장치·안의 필지는 Python(§대상지 방식) |
| `set_point` | `center`([lng,lat], 없으면 지움) | `point_state` | 위치 방식. 지도 클릭·검색 결과 |
| `pick_curve` | — | `curve_shape` | Rhino 전용. 선택된 커브가 하나면 그것, 없으면 고르기 프롬프트 |
| `preflight` | `target`(없으면 `pnus` = 필지 방식), `radius`, `shape`, `paper`, `paper_mm`, `scales`, `seq` | `preflight_result`(같은 `seq`) | 2026-10-19부터 Rhino 패널은 보내지 않는다(범위를 JS가 그린다). 예전: ① lots 변경 직후, ② 진입·옵션 변경(300 ms 디바운스). 메모이즈 키 `(tuple(pnus), radius, shape, paper, tuple(paper_mm), tuple(scales))` — `paper_mm`이 빠지면 용지 '직접'에서 가로·세로를 바꿔도 프레임이 안 바뀐다. `init`마다 비운다 |
| `generate` | `target`(없으면 `pnus`), `options`(§옵션 키 **`scales` 포함** — 가장 큰 축척 프레임이 DB 질의 범위를 정한다, code_map §3) | `progress`* ↔ `log`* → `done` / `progress{state:"failed"}` / `progress{state:"cancelled"}` | `context_builder.run` 동기 실행(UI 스레드, 콜백 안 `RhinoApp.Wait()`로 푸시·취소 명령 펌핑). 이미 running이면 무시하고 `error{context:"generate"}`. 베이크가 곧 '문서에 넣기'라 `busy`·`imported`는 오지 않는다(`done.context.imported`로 전한다). 생성기는 BM 레이어를 항상 전부 쓴다 — 축척별 차이는 Export 때만 |
| `make_2d` | `dir`(결과 폴더), `options`(2D 키 — `make_basemap`·`paper`·`paper_mm`·`scales`·`basemap_layers_on`·`make_dwg`·`make_sheets`·`sheet_ids`·`floor_breaks`·`elev_preset`·`make_tables`·`style`) | `data_progress`* → `progress`* ↔ `log`* → `made_2d` | 3D 결과에 2D 자료를 더한다(2026-10-19). `context_builder.make_2d`: `context.json`의 대상지·옵션 위에 2D 옵션을 덮어 다시 `prepare`(가장 큰 프레임까지 조회 — 생성 전에 그 범위 팩을 받는다) → basemap·sheets·tables phase(run과 같은 함수) → `context.json` 갱신. 만들 때마다 결과 폴더 안 새 폴더 `2D_<스타일 이름>_<HHMM>/`(같은 분이면 `_2`…, `context_builder.get_new_2d_dir`)에 베이스맵·도면·조서를 쓴다 — 스타일을 바꿔 다시 만들어도 앞 폴더를 덮어쓰지 않는다(2026-10-21). `made_2d.folder`가 그 폴더, `context.json.last_2d_dir`에 기록하고 [다른 축척]·[모두 .ai로 저장]은 그 폴더에 쓴다. `sheet_view`·`sheet_ai` 한 장은 그 결과 폴더 안 어느 2D 폴더든 받는다. `make_dwg`(베이스맵과 함께만, Rhino만)면 basemap phase 끝에 가장 상세한 축척의 2D 선 도면을 새 헤드리스 문서에 구워 `basemap_<축척>.dwg`(`context_baker.save_dwg` — 활성 문서는 안 건드린다). 원점은 `context.json.doc_origin`을 써 3dm과 같은 좌표. 지형 삼각형은 이번 세션 3D 결과(`_keep`)에서, 없으면 지형 도면이 빈다. 문서는 건드리지 않는다. running 중이면 `error{context:"generate"}`. progress는 `query`·`basemap`·`sheets`·`tables`만(나머지 skipped). 취소는 `cancel` 그대로 |
| `cancel` | — | `progress{state:"cancelled"}` 또는 무시 | running이 아니면 **무시**(응답 없음). running이면 `cancel_requested` 플래그만 세운다 — 다음 콜백이 False를 돌려주고 엔진이 `Cancelled`로 중단·이번 베이크 객체 삭제 → `ok=false, cancelled=true`. 부분 폴더 유지, `log.txt`에 "cancelled at <phase>" |
| `import_context` | `dir`(결과 폴더 절대경로) | `busy{on}` → `imported` → `busy{off}` | 재삽입: 같은 `GORANI_LOT_KEY` 객체 삭제 후 `context_baker.import_3dm`(`context.json.origin`이 문서 원점과 다르면 차이만큼 이동). `zoom_after_import`면 줌 |
| `export_basemap` | `dir`, `scale`(1000\|3000\|5000) | `busy{on}` → `exported` → `busy{off}` | `context_builder.export_basemap(dir, scale)`: 결과 폴더의 `context.json`(pnus·options)으로 DB에서 다시 `prepare` → `basemap_ai.write_basemap` → `<dir>/basemap_<scale>.ai`. 문서를 거치지 않는다(import 불필요, 1초 안팎). 축척별 레이어 표(`constants.BASEMAP_SCALE_LAYERS`): 1:1000 = `08`(지적선) on · `08b`(지번) on, 1:3000 = `08` on · `08b` off, 1:5000 = `08`·`08b` off. 실패하면 `exported{ok:false, text}` |
| `zoom_view` | `dir`(결과 폴더 절대경로), `center`[lng,lat](선택) | — (`error{context:"open"}`) | `import_context`·`export_basemap`과 같은 꼴 — JS가 `result.dir`을 붙인다(Python은 마지막 결과 폴더를 기억하지 않는다). `center` 없으면 `CTX::Site` 객체로 줌. 있으면 `<dir>/context.json`의 ORIGIN으로 문서 좌표 환산 후 그 점 주변 100 m |
| `open_path` | `path`(str) | — (`error{context:"open"}`) | 절대경로 또는 프로젝트 루트 상대(`docs/data_sources.md`, `.env`, `data`). 폴더 = 탐색기, 파일 = OS 기본 앱. `.env`가 없으면 한 줄 템플릿(`VWORLD_API_KEY=`)을 만든 뒤 연다. 외부 URL은 열지 않는다(WebView가 이동하므로 JS에서도 링크 금지 — 토지이음은 `open_eum`) |
| `open_url` | `key`(`constants.PANEL_LINKS`의 키 — 지금은 `website`) 또는 `notice`(공지 id) | — (`error{context:"open"}`) | 더보기 메뉴 '고라니 웹페이지'·업데이트 [업데이트 방법]은 `key`, 공지 [자세히]는 `notice` — 매니페스트에서 그 공지의 http(s) 주소를 찾아 연다. 임의 URL은 받지 않는다 |
| `open_eum` | `pnu`(19자리) | — (`error{context:"open"}`) | ① 필지 정보 [토지이음 ↗]. Python이 `constants.EUM_LAND_USE_URL % pnu`를 만들어 OS 브라우저로 연다(임의 URL은 받지 않는다) |
| `save_prefs` | `options` | — | `prefs.json`에 `options`만 덮어쓴다(`recent`는 `generate` 성공 시 Python이 갱신) |
| `remove_recent` | `pnus` | 없음 (`error{context:"init"}`) | 최근 대상지 줄의 x — 같은 PNU 묶음을 `prefs.json` `recent`에서 지운다. JS가 `init.recent`에서 먼저 빼고 트레이·메뉴를 다시 그린다 |
| `style_preview` | `dir`, `sheet_id`(0~15), `style`(스타일 dict), `seq` | `style_preview`(같은 `seq`) / `error{context:"style"}` | ③ 2D 카드 다이어그램 타일 [편집]의 스타일 화면(만들기 전). `context_builder.preview_sheet` — 한 장을 스타일로 다시 그린 SVG 문자열(파일 안 씀). 시트 데이터는 컨트롤러 `_keep`(이번 세션 생성 결과, 지형 삼각형 포함). 2D를 아직 안 만들었으면 3D를 만든 Prepared를 그대로 써서 다시 조회하지 않는다(`get_sheet_data(quick=True)` — 자료는 3D 범위까지. 다시 prepare하면 Global은 OSM·지형 타일을 또 받아 55 s 걸렸다, 2026-10-19). `_keep`이 다른 결과면 `context.json`으로 한 번 prepare(지형 시트는 비어 나온다). SVG id·`url(#…)`은 `pv_` 접두어(패널 `#map`과 겹치지 않게). JS 250 ms 디바운스, 늦은 `seq`는 버린다 |
| `apply_style` | `dir`, `style` | `busy{on}` → `style_applied` → `busy{off}` | `context_builder.apply_style` — 결과 폴더의 시트 전부 + 이미 쓴 `basemap_<축척>.ai`를 다시 쓰고 `context.json.options.style`을 바꾼다. 지형 삼각형이 없으면 지형 시트 파일은 그대로(`kept`). JS는 성공하면 `options.style`을 `save_prefs`. **2026-10-19부터 패널은 보내지 않는다** — 스타일은 만들기 전에 정하고 [적용]은 `options.style`만 바꾼다 |
| `save_style` | `name`, `style` | `styles` / `error{context:"style"}` | `site_prefs.save_style` → `HOME_DIR/styles/<이름>.json`(경로 문자 제거, 같은 이름 덮어씀). 사무소 표준을 파일로 나눠 쓴다 |
| `sheet_view` | `dir`, `path`(도면 SVG) | `sheet_view{path, svg}` / `error{context:"view"}` | 다이어그램 칸 → 패널 보기 창(2026-10-19). SVG 내용을 그대로 보낸다 — OS로 열면 .svg도 Illustrator에 묶인 PC가 많았다. `path`는 그 결과의 sheets 폴더 안 .svg만. JS는 Blob URL `<img>`로 그린다(패널 id와 안 겹침), ←→ 넘기기, 누르면 확대, Esc 닫기 |
| `sheet_ai` | `dir`, `path`(도면 SVG) 또는 `all:true` | `busy{on}` → `sheet_ai` → `busy{off}` | `sheet_svg.get_sheet_ai` — 도면 SVG를 레이어 .ai로(없거나 SVG보다 오래됐을 때만 다시 쓴다). 한 장이면 쓰고 OS로 연다. 생성 때 .ai를 다 쓰지 않는다(23장이면 Rhino에서 10 s+). 패널은 [모두 .ai로 저장](`all`)만 보낸다 — 칸을 누르면 `sheet_view`로 패널 안에서 본다(2026-10-19). `write_sheets`는 다시 쓴 SVG 옆에 .ai가 있으면 .ai도 새로 쓴다 |
| `area_packs` | `bbox`([서, 남, 동, 북] 경위도), `seq` | `area_packs` | 지도 이동(600 ms 디바운스)마다. 화면에 걸리는데 파일이 없는 시군구 **필지** 팩 `{seq, missing[{name, label, mb}], mb, labels}`(건물·도로·지형 팩과 새 판은 생성할 때 범위만) — 해외·매니페스트 없음·오프라인은 빈 목록. 배율 16 이상이면 JS가 곧바로 `download_data{names}` |
| `stats_consent` | `on`(bool) | 없음 (`error{context:"init"}`) | Blender·SketchUp만 — 사용 통계 동의를 `~/.gorani/prefs.json`에 남긴다. `usage_stats.is_enabled`가 `host.ask_stats` 호스트면 이 값이 true일 때만 보낸다(Blender 확장 약관 4.5, Extension Warehouse 개인정보 심사) |
| `download_data` | `names`(선택 — 없으면 전부) | `data_progress`×N → `data_progress{done}` → `init_state` (`error{context:"init"}`) | 지도 자동 받기·진행 줄 [다시 받기]. 멈추면 그때까지 받은 팩은 남는다(받던 팩은 버리고 쓰던 DB는 그대로). `data_pack`이 매니페스트(`constants.DATA_MANIFEST_URL`)의 절대 주소에서 `HOME_DIR/data/`로 받는다. `generate`도 시작 전에 같은 방식으로 범위(`context_builder.get_query_bounds`)에 걸치는 없거나 새 판인 시군구 팩을 받는다 |

명령 16개(+ 도면 스타일 3개·도면 .ai 1개, 2026-10-13). `auth_pin`(옛 PIN 인증)은 없다 — 사내 배포라 인증 게이트 없음.

## 푸시 목록 (Python → JS)

### 공통 — 경고·원천 스키마

경고 하나(`warning`)는 어디서 오든 같은 모양이고 JS 렌더 함수 하나가 그린다.

```jsonc
{"level":"info|warn|danger",
 "code":"stale_lot|stale_building|stale_terrain|coverage|no_context_db|no_api_key|invalid_key|height_estimate|mismatch|skipped|empty_buildings|frame_over|multipart|merge_failed|merge_apart|merge_hole",
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
 "keys":{"vworld":true},                                  // api만. VWorld — 지도·위성 배경, 항공사진, 주소 보조 검색(없으면 OSM·Esri·지명 검색)
 "text":"4.8개월"}                                         // 행 오른쪽 짧은 부가. api: "있음" | "없음"
```

`level` 규칙(data_sources §2.4): `warn` = 경과 ≥ 노랑 임계 AND `newer_date` 있음, `danger` = 경과 ≥ 빨강 임계(새 판 무관), `missing` = 원천 없음(컨텍스트 DB 없음·키 없음), 그 외 `ok`. 생성은 어느 경우도 막지 않는다.

### 브라우저 호스트 (Blender·SketchUp·Rhino 7)

Blender·SketchUp·Rhino 7에는 Rhino 8식 웹뷰 브리지가 없어 `panel_server.Bridge`가 127.0.0.1에 서버를 띄우고 `/?token=<세션 토큰>`을 연다 —
Blender는 기본 브라우저(`cmd_blender.py`), SketchUp은 `UI::HtmlDialog`(`sketchup_ext.rb`가 사이드카 `cmd_sketchup.py`의 첫 줄 주소를 연다), Rhino 7은 Mac = Eto WebView·Windows = Edge 앱 창(`rhino7_host.cs`가 사이드카 `cmd_rhino7.py`의 첫 줄 주소를 연다 — Rhino 7 Windows 웹뷰는 IE). JS는 URL에 토큰이 있으면
`send()`를 `POST cmd?token=…`(본문 = 명령 JSON)으로, 푸시는 `EventSource("events?token=…")`의 `data:` 한 줄(= 푸시 JSON)로 받는다.
이벤트 줄이 열린 뒤(`onopen`) `init`을 보낸다 — 다시 연결돼도 init으로 전부 다시 받는다. 새 이벤트 줄이 열리면 앞 줄로는 보내지 않는다(탭 하나) —
앞 줄에는 마지막으로 `{"type":"superseded"}`를 보내고, 그 탭은 이벤트 줄을 닫고(다시 붙지 않음) '새 탭에서 열렸습니다' + [이 탭에서 계속](새로 고침)만 보인다.
명령은 호스트 메인 스레드(Blender = bpy.app.timers, SketchUp·Rhino 7 사이드카 = 메인 루프)에서 처리하고, `cancel`·`host_reply`만 바로 받는다(SketchUp = 서버 스레드 — Rhino 7의 `host_reply`는 stdin을 읽는 스레드, Blender = 스레드 없이 메인 스레드 `poll` — 생성 중에는 진행 콜백이 `poll`을 불러 cancel·새 탭을 받는다). 토큰이 틀리면 403.
Blender판 `init_state.host`는 `ask_stats:false`(통계 없음)·`aerial:false`(`tile`의 영상 주소가 비고 [위성]·항공사진 도면 없음)·`update_notice:false`(`update` 늘 null)·`ip_center:false`(`map`은 늘 서울시청)다.

SketchUp 호스트 호출 — 사이드카는 SketchUp 모델을 직접 만지지 못해 패널을 거쳐 Ruby를 부른다(엔진 `run`은 응답을 기다리며 막혀 있다):

```jsonc
{"type":"host_call","id":3,"method":"bake","args":{"path":"/tmp/gorani_bake_….json"}}   // 푸시 → JS가 window.sketchup.host_call(JSON 문자열)
{"cmd":"host_reply","id":3,"ok":true,"result":[…],"error":""}                               // 명령 ← Ruby가 execute_script("send(…)")로 보낸다
```

`method` = `get_model_attrs{keys}`·`set_model_attrs{values}`·`clear{lot_key}`·`bake{path}`·`ref{…}`·`save{path}`·`zoom{lot_key, box, min_span}`·`import{path, lot_key, lot_name, shift}`·`pick_curve{}`
(`sketchup_baker`·`cmd_sketchup`이 부르고 `sketchup_ext.rb`의 `rpc_<method>`가 받는다). `window.sketchup`이 없는 창(일반 브라우저)이면 무시한다 — 사이드카는 `SKETCHUP_HOST_TIMEOUT` 뒤 실패. 패널 창을 닫으면 Ruby가 사이드카 stdin으로 `{"cmd":"panel_closed"}`를 보내 생성 중이면 취소하고, 기다리던 호출은 바로 실패한다(다시 연 패널의 init이 막히지 않게).

Rhino 7 호스트 호출 — 같은 `method`·`args`를 패널 대신 사이드카 stdout 한 줄(`{"type":"host_call",…}`)로 쓰고, `rhino7_host.cs`가 stdin 한 줄(`{"cmd":"host_reply",…}`)로 답한다(Edge 창은 Rhino에 닿지 못한다). 베이커는 `sketchup_baker` 그대로이고 사본만 `context.3dm`이다. Mac 패널 창을 닫으면 stdin `panel_closed`, Rhino가 끝나면 stdin EOF로 사이드카도 끝난다.

### 푸시 정의

```jsonc
{"type":"init_state",
 "version":"0.2.0",                               // constants.PANEL_VERSION = 패키지 버전(dev_deploy.PACKAGE_VERSION)
 "blocked":false,                                 // true = 필지 DB 없음 → 블로커(차단은 이것뿐. 컨텍스트 DB 없음은 경고)
 "paths":{"root":"<HOME_DIR>","lot_db":"data/seoul_site.db","context_db":"data/seoul_context.db","env":".env","install_doc":"docs/install.md"},
 "generator":{"ok":true,"python":"Rhino Python","text":"Rhino 내장"},   // 항상 ok. UI 호환용(블로커 3행째는 ✓ 고정). Blender면 "Blender …"
 "host":{"id":"rhino","name":"Rhino","doc":"Rhino 문서","model":"context.3dm","dwg":true,"ask_stats":false},   // constants.HOST_LABELS — 패널 문구(문서 이름·모델 파일)와 DWG 옵션 표시. Blender = {"id":"blender","name":"Blender","doc":"Blender 장면","model":"context.blend","dwg":false,"ask_stats":true}, SketchUp = {"id":"sketchup",…,"model":"context.skp","dwg":false,"ask_stats":true}, Rhino 7 = Rhino와 같고 `"dwg":false`
 "output_langs":[["ko","한국어"],["en","English"]],   // constants.OUTPUT_LANGS — 메뉴 '결과 언어' 칸
 "links":{"website":"https://969flash.github.io/gorani/"},   // constants.PANEL_LINKS — 메뉴 '웹페이지' 줄이 주소를 링크로 보여 주고, 누르면 open_url{key}
 "stats_consent":null,                            // 사용 통계 동의 true|false|null(안 물음) — host.ask_stats(Blender + 측정 ID 있음)면 null일 때 정보 띠로 한 번 묻고([보내기]·[보내지 않음] → stats_consent{on}), 더보기 메뉴 설정에서 바꾼다
 "can_download":true,                             // DATA_MANIFEST_URL이 있으면 블로커에 [DB 받기]·[멈추기]
 "sources":[source, source, source, source],      // id = lot, building, terrain, api 순서 고정(더보기 메뉴 자료 칸·블로커 체크리스트·첫 실행 모드 판정)
 "warnings":[warning],                            // 더보기 메뉴 자료 칸(no_api_key는 설정 칸 API 키 행). warn·danger면 메뉴 버튼의 점(Korea 모드). 띠로 띄우지 않는다
 "tile":{"url":"…","fallback_url":"…","attribution":"…","abroad_url":"…","abroad_attribution":"…",
         "aerial_url":"…","aerial_attribution":"…","abroad_aerial_url":"…","abroad_aerial_attribution":"…"},   // review_map.get_tile_config(). 지도 중심이 map.korea_bounds 밖(또는 그 안 일본 모서리 map.korea_cut — 후쿠오카·쓰시마)이면 abroad_url(OSM). 지도 오른쪽 아래 [위성]을 누르면 aerial_url(VWorld 영상, 키 없으면 Esri) — 해외·폴백 뒤는 abroad_aerial_url(Esri)
 "map":{"center":[126.9784,37.5665],"zoom":16},              // review_map.get_map_init(map_center) — 첫 init에 IP로 짐작한 도시(zoom 12, get_ip_center), 못 받으면 서울시청(zoom 16)
 "options":{…옵션 키 전부, prefs.json 복원 또는 기본값…},
 "recent":[{"pnus":["…"],"label":"성수동2가 277-17 외 1","total_area":1234.5,"date":"2026-10-06"}],   // 최대 5, 필지 방식만. 트레이(대상지 없을 때)·더보기 메뉴에 5개까지, 줄을 누르면 필지 방식으로 select_lots, 오른쪽 x는 remove_recent. done 때 JS가 같은 꼴로 앞에 넣는다(다음 init까지)
 "sheet_catalog":[{"id":0,"key":"base","name":"베이스맵","needs":"lot","korea_only":false,"group":"base"},…,{"id":19,"key":"slope","name":"경사","needs":"terrain","korea_only":false,"group":"status"}],   // group = constants.SHEET_GROUP: base(베이스맵·항공사진)·status(현황도)·analysis(분석도)·frame(틀) — 2D 카드 묶음 칩   // constants.SHEET_CATALOG 25장(분석도 8 · 현황도 12 · 틀 3 · 항공사진 1 · 입체 매스도 1, needs image = 영상 타일). done.sheets[].thumb = 160 px PNG data URI(패널 도면 칸, 항공사진만 SVG data URI)
 "style_presets":{"std":{"name":"표준","paper":"#FFFFFF",…,"ramp":"warm"},"vivid":…,"mono":…,"dark":…},   // constants.STYLE_PRESETS
 "style_defaults":{"layout":"side","line_scale":1.0,"text_scale":1.0,"font":"sans","fade_outside":0.55,"labels":true,"subtitle_en":true,"project":"","axo_view":"se","axo_ground":"block"},
 "style_ramps":{"warm":["#FBEFC9",…],…},
 "styles":[{"name":"OO건축 표준","style":{…}}],     // HOME_DIR/styles/*.json
 "update":null,                                   // 매니페스트 update — 아래 '업데이트·공지'. 못 받았으면 null
 "notices":[]}                                    // 매니페스트 notices [{id, level:"warn"|"info", date, text, url}]

{"type":"search_result","query":"…","seq":null,
 "matches":[{"pnu":"1120010200102770017","address":"서울특별시 성동구 성수동2가 277-17","jibun":"277-17",
             "land_category":"대","area":612.3,"center":[lng,lat]}],   // 0~8건. 1건이면 JS가 바로 select_lots
 "message":"후보 3건"}                                                 // 0건: "찾지 못했습니다 — 동 이름까지 적어 보세요"

{"type":"map_lots","seq":17,"geojson":FC,"truncated":false}
   // properties = {pnu, address, jibun, land_category, area}. review_map.get_parcels_in_bbox 그대로

{"type":"lot_state",
 "lots":[{"pnu":"…","address":"…","jibun":"277-17","land_category":"대","area":612.3,"warn":null,   // warn: "multipart"|"hole"|null
          // ① 필지 정보(접힘) — 로컬 DB만. zones = 토지특성 용도지역 1·2('지정되지않음' 제외) + 법정 [건폐 상한, 용적 하한, 상한] %
          // (constants.LEGAL_ZONE_LIMITS, 시행령 제84·85조 — 조례값 아님, 표에 없으면 null). designations = 토지이용계획 포함·저촉(접함 제외,
          // 용도지역과 같은 이름 제외). area_gap = 도형(연속지적도) − 대장 ㎡(대장 없으면 null), flag = |차이| ≥ AREA_GAP_FLAG_RATIO × 대장
          "zones":[{"name":"제2종일반주거지역","limits":[60,100,250]}],"designations":[{"name":"교육환경보호구역","conflict":"저촉"}],
          "registered_area":612.3,"geometry_area":615.8,"area_gap":3.5,"area_gap_flag":false,"reference_date":"2026-05-13"}],
 "total_area":1234.5,
 "land_use_date":"2026-08-25",                     // 토지이용계획 data_sources 기준일(데이터기준일자 최댓값). 예전 팩은 ""
 "lot_name":"성수동2가_277-17외1",                 // 결과 폴더명·recent 라벨 원본
 "center":[lng,lat],                             // 원점 후보(100 m 내림 전 값)
 "target_geojson":FC,                            // 필지별 role="lot" + 합집합 1개 role="target"
 "warnings":[warning]}                           // code=multipart 등. ① 칩 배지로

{"type":"preflight_result","seq":5,
 "sources":[source×4],                           // coverage 포함
 "extent_geojson":FC,                            // role="extent" 1개(properties.radius, shape)
                                                 // role="topo_sheet" n개(properties.topo_sheet, year, have:bool) — 수치지형도 도엽
                                                 // role="frame" 축척마다 1개(properties.scale, paper, over:bool)
 "estimate":{"buildings":1842,"lots":2310,"topo_have":3,"topo_total":4,"seconds":40,"mb":8,"pending_mb":0},   // pending_mb>0 = 건물·지형 팩을 생성할 때 받는다(그 전 건물 수·도엽은 0으로 센 값 — 패널은 "생성할 때 받음"만 보인다)
   // topo_* = 도엽
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
{"type":"data_progress","text":"종로구 지역 데이터 받는 중 42%","fraction":0.42,"in_generate":false}   // 받기 진행(1 % 단위). 지도 밖 푸터 위 한 줄(#dl) — 생성 중(in_generate)이면 [멈추기] 없이(푸터 [취소]가 멈춘다)
{"type":"data_progress","done":true,"ok":false,"text":"받기를 멈췄습니다 — 받은 지역은 남습니다","in_generate":false}   // 끝. ok면 줄을 숨기고, 아니면 text + [다시 받기]
{"type":"error","context":"init|search|select|preflight|generate|import|export|open","text":"한 줄","detail":"traceback 또는 빈 문자열"}

{"type":"done",
 "dir":"/…/result/성수동2가_277-17외1_20261007",
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

{"type":"made_2d","ok":true,"cancelled":false,"dir":"…","folder":"…/2D","elapsed_s":12.4,   // folder = 2D 산출물 폴더(결과 폴더/2D — 베이스맵 .ai·.dwg, sheets/, tables/)
 "options":{…2D 옵션을 덮은 옵션…},
 "basemap":{"ready":true,"paper":"A3","layers":14,"scales":[5000],"exported":["…/basemap_5000.ai"],"dwg":"…/basemap_5000.dwg"},   // done.basemap과 같은 꼴. make_basemap 끔이면 ready=false·exported=[]. dwg: make_dwg로 쓴 경로, 아니면 ""
 "sheets":[…done.sheets와 같은 꼴…],"tables":[…],"files":[…],"warnings":[warning],
 "error":null}                                   // ok=false면 error{code,title,detail}(취소면 code "cancelled"). 3D 결과·문서는 그대로
{"type":"imported","ok":true,"dir":"…","layers":12,"objects":4120,"replaced":true,"text":""}   // ok=false면 text에 Rhino 메시지. run=running 중(import_after 경로)에는 JS가 무시 — 결과는 done.context에 담겨 온다
{"type":"exported","ok":true,"dir":"…","scale":3000,"path":"…/basemap_3000.ai","text":""}
{"type":"style_preview","seq":3,"sheet_id":0,"svg":"<svg …>","empty":false,"reason":""}   // id는 pv_ 접두어
{"type":"style_applied","ok":true,"dir":"…","sheets":[{id,name,path,thumb,empty,reason}],"basemaps":["…/basemap_5000.ai"],"kept":[14,15],"text":""}
{"type":"sheet_ai","ok":true,"dir":"…","paths":["…/sheets/02_필지규모.ai"]}
{"type":"styles","styles":[{"name":"OO건축 표준","style":{…}}],"saved":"OO건축 표준","dir":"<HOME_DIR>/styles"}
```

`data_progress{in_generate:true}`는 `generate`·`make_2d`가 생성 전에 그 범위 팩을 받을 때 온다 — 패널은 지도 밖 받기 줄이 아니라 진행 목록의 '지역 데이터 받기' 줄과 막대 앞 20 %로 그린다.

푸시 13종. `toast`는 없다 — 성공 토스트는 JS가 `imported`·`exported`를 받아 띄운다.

## 업데이트·공지 (2026-10-21)

이미 깔린 플러그인에 코드 수정 없이 알린다. 원본은 `docs/notices.json`, 올리기는 `python3 scripts/dev_deploy.py notices`(HF 매니페스트의 `update`·`notices`만 바꾼다. `upload`도 같이 넣는다).
보통은 관리자 페이지로 한다 — 저장소 루트의 `관리자_페이지.command`를 더블클릭(= `python3 scripts/dev_admin.py`) — 이 Mac의 127.0.0.1에만 뜨고(실행마다 새 토큰, 인터넷에 올리지 않는다), 고친 것은 초안(`docs/notices.json`)에 바로 저장한다. 공지는 패널 띠 모양으로(게시됨·새로 추가·수정됨·내림), 버전 안내는 구간(안내 없음·업데이트 권장·사용 불가)으로 보여 주고 구간마다 그 버전 사용자 화면을 실제 패널(목 모드)로 미리 본다. [게시하기]는 바뀐 점을 보여 주고 확인을 받은 뒤 올리고, [변경 취소]는 초안을 게시된 내용으로 되돌린다. 새 버전·사용 불가 기준이 `PANEL_VERSION`보다 높으면(아직 배포 안 한 버전) 저장·게시를 막는다. 관리자 페이지 첫 화면은 대시보드다(사이드바: 개요·사용·유입·웹·품질·데이터·서버 | 공지·버전·연결). `dev_stats.py`가 GA(서비스 계정이 볼 수 있는 Rhino·SketchUp·웹 속성 — 측정 ID로 구분)·yak·Hugging Face·국내 서버(nginx 기록·버킷)를 모아 직전 같은 길이 기간과 비교하고, 규칙으로 고른 인사이트(활성화율·성공률·최신 버전 사용률·무료 한도 등)를 낸다. 대시보드가 읽는 GA 이벤트 매개변수는 `constants.ADMIN_GA_DIMENSIONS`이고 [연결]의 버튼이 맞춤 측정기준으로 한 번에 등록한다(서비스 계정 = 편집자). 열쇠는 저장소 밖(`constants.ADMIN_DIR`), 국내 서버 기록은 서버가 2주만 남겨 같은 곳에 이어 붙여 둔다. 주소 뒤 `&demo=1`은 GA 자리에 예시 데이터(연결 전 화면 확인).

```json
{"update": {"latest": "0.3.0", "min": "0.2.0", "body": "새 버전부터 계정으로 로그인합니다. 무료로 계속 쓸 수 있습니다.",
            "items": ["로그인", "현황도 3종 추가"], "deadline": "12월 1일", "title": ""},
 "notices": [{"id": "2026-11-maint", "level": "info", "date": "2026-10-28", "text": "11월 3일 02~06시 서버 점검으로 DB 받기가 멈춥니다", "url": "https://…"}]}
```

- 패널을 열 때(`init`) 매니페스트를 `NOTICE_TIMEOUT_SECONDS`(3 s)까지 기다린다. 못 받으면 아무것도 띄우지 않는다 — 사용자를 막지 않는다.
- `version < update.min` → 강제 모달(닫기 없음, [다시 확인]·[결과 폴더]·[웹페이지]). 지원을 끊을 때만 올린다.
- `version < update.latest` → 권장 모달(하루 한 번 — [나중에] = `options.update_later_date`) + 주황 띠(닫기 없음, 업데이트할 때까지).
- 공지 → 위쪽 띠는 한 번에 하나(업데이트 > 공지 순서), 나머지는 띠의 `+N` → 더보기 메뉴 '공지' 목록. 띠 [×]는 `options.closed_notices`에 id를 넣고, 메뉴에서는 계속 보인다(흐리게 '닫음'). `level`: `warn` = 주황(꼭 알아야 할 것), `info` = 파랑. 빨강은 오류에만.
- 공지 `id`는 바꾸지 않는다 — 바꾸면 닫은 사람에게 다시 뜬다. 목 패널: `site_ui.html?mock=1&step=1&update=soft|hard`(공지 견본 셋 포함), `&notice=1`은 공지만.
- 버전은 `constants.PANEL_VERSION` 하나 — 배포할 때 올린다. 0.1.0 이전 설치본에는 이 확인이 없다(그 사용자는 막을 수 없다).
- `countries[]`(2026-10-23) — 나라별 공식 건물 팩 목록. 원본 `docs/countries.json`, 올리기는 같은 `dev_deploy.py notices`(`upload`도 같이 넣는다). 항목 `{code(소문자 2자 = 팩 이름 접두사), label, source_id, manifest(한국 매니페스트 기준 상대경로 가능), bounds[서, 남, 동, 북] 또는 그 목록(미국처럼 본토·알래스카·하와이), code_pattern, disabled?}`. 플러그인은 `init`에 받아 둔 매니페스트의 이 목록으로 대상지 나라를 고르고(`data_pack.get_country_packs` → `osm_context.get_country`, 상자가 겹치면 작은 것), 못 받았으면 내장 `constants.COUNTRY_PACKS`(같은 값). 틀린 항목은 그 나라만 건너뛰고 `disabled: true`는 내장에서도 뺀다. **새 나라 = 팩·`<나라>/manifest.json` 올리기 + 이 목록 한 줄 — 플러그인 판은 올리지 않는다**(0.3.3·0.3.4를 나라 추가만으로 올린 뒤 바꿈). 생성 직전(`_download_for_generate`)에도 매니페스트를 한 번 더 받아 둔다(init 3 s 안에 못 받은 경우).
- `services{}`(2026-10-23) — 외부 주소 덮어쓰기(같은 `docs/countries.json`의 `services`): `overpass`(미러 목록)·`nominatim`·`terrain_tiles`(`{z}/{x}/{y}` 틀). `data_pack.get_service(key, 내장값)` — https만 받고 틀리면 내장 상수. 미러가 죽거나 주소가 바뀌어도 판 없이.
- **원격 설정 `config.json`**(2026-10-23, 매니페스트 옆) — 코드가 아니라 '값'을 판 없이 바꾼다: 도면 색·범례·틀 치수(`STYLE_PRESETS`·`SHEET_LEGENDS`·`SHEET_*_MM`·`BM_LAYERS`), 분류 구간·코드표(`SHEET_*_BREAKS`·`SHEET_*_KEYS`·`PLATEAU_USE`·`OSM_BUILDING_USE`), 높이·범위 파라미터(`FLOOR_HEIGHT_*`·`CONTEXT_RADIUS`), OSM 질의·도로폭, `PANEL_LINKS`, 번역 사전 전체. 목록은 `remote_config.REMOTE_KEYS`(원본 = `constants.py`·`i18n.json`, 올리기 = `dev_deploy.py notices`가 `remote_config.build()`로 만들어 같이 올림, 자가 점검 후). 플러그인은 컨트롤러 생성 때 캐시(`HOME_DIR/data/config.json`)를 덮고(패널 HTML에 번역을 심기 전), `init`에서 ETag로 새 것을 받는다(3 s, 못 받으면 캐시·내장값). 덮는 규칙: 이름이 목록에 있고 꼴(dict·list·str·수)이 내장값과 같고 dict는 내장 키를 다 가질 때만, 틀린 항목은 그 항목만 건너뜀. 번역은 `test_i18n`과 같은 규칙(자리표시 일치, 원문에 없는 `" & < >` 금지). **상수의 꼴을 바꾸는 판을 내면 `remote_config.COMPAT_MIN`을 그 판으로** — 옛 설치본은 원격 설정을 받지 않고 내장값으로 돈다. 그리는 코드·새 도면·패널 HTML은 원격으로 바꾸지 않는다(스토어 규정·보안).
- **데이터 호환 규칙** — 팩·매니페스트만 바꿔도 깔린 플러그인이 그대로 돌게: ① 팩 표는 칸을 더하기만 한다(런타임은 `SELECT *` + 이름 조회라 모르는 칸을 무시한다), 칸 삭제·이름 바꾸기 금지 ② `PRAGMA user_version`은 호환이 깨질 때만 올린다(런타임은 자기보다 낮은 판만 거절한다) ③ 새 `height_src`는 `<source_id>_<height|levels|roof>` 꼴로 — 범례 표기는 `data_pack.get_height_src_label`이 팩 라벨로 만든다 ④ 새 출처(`source_id`)의 고지는 팩 `data_sources.note`에(런타임은 PLATEAU만 코드 특례, 나머지는 note 그대로) ⑤ 용도(`usability`)는 빌드 때 팩에 쓴다(런타임 코드 사전은 옛 PLATEAU 팩용) ⑥ 매니페스트에 모르는 키가 있어도 무시한다.

## 언어 (2026-10-21)

food4Rhino 심사(McNeel, 2026-10-21 '영어가 없으면 올릴 수 없다')로 패널을 다섯 언어로 쓴다: 영어(기본)·한국어·스페인어·일본어·중국어 간체.

- 사전은 `scripts/i18n.json` 하나 — `{"한국어 원문": {"en", "es", "ja", "zh"}}`. 패널 JS `tr("원문", a, b)`와 Python `i18n.tr("원문", a, b)`가 같은 사전을 쓴다. 원문(키)은 한국어 그대로라 한국어는 사전을 보지 않는다. 번역이 없으면 영어, 영어도 없으면 원문. 자리표시 `{0}`·`{1}`(Python은 `{0:.1f}`처럼 형식도).
- 호스트(`panel_host`·`panel_server.get_html`)가 HTML의 `<!--I18N-->` 자리에 `window.I18N = {…}`를 심는다. 파일로 연 목(`?mock=1`)은 옆의 `i18n.json`을 읽는다. `&lang=ko|es|ja|zh`로 언어를 고른다.
- 언어는 `options.lang`(prefs). 고르기는 헤더의 지구본 칸(언어 이름은 그 언어로). 바꾸면 `save_prefs` 후 지금 화면을 다시 그린다(대상지·결과는 그대로).
- JS는 모든 명령에 `lang`을 붙이고, `cmd_site.handle`이 그 값으로 Python 언어(환경변수 `GORANI_LANG`)를 바꾼다 — 그 명령의 푸시 문구·로그·도면·CSV가 그 언어로 나온다. 첫 `init`은 패널도 모르므로 저장한 `options.lang`.
- 처음 설치는 영어(`constants.DEFAULT_LANG`). 0.3.0 전에 쓰던 설치본(prefs에 options는 있고 `lang`이 없다)은 한국어 그대로(`site_prefs.get_options`).
- 패널이 tr()로 바꾸는 Python 원문: `sheet_catalog[].name`, `style_presets[].name`, `done.sheets[].name·reason`, `host.name`(웹판 '브라우저'). 이미 번역돼 온 글은 사전에 없어 그대로 나온다.
- 번역문에는 원문에 없는 `" & < >`를 쓰지 않는다 — 패널이 한국어 원문처럼 HTML에 그대로 넣는다. 매니페스트 공지·업데이트 글(`update.title·body·items·deadline`, `notices[].text`)은 문자열 또는 `{en, ko, …}`(패널 `pickLang`).
- 웹페이지 링크: 한국어는 `PANEL_LINKS.website`, 그 밖은 `website_en`(영어 페이지).
- 새 문구를 넣으면 `tr()`로 감싸고 `i18n.json`에 네 언어를 넣는다. `tests/test_i18n.py`가 빠진 번역·자리표시·특수문자·안 쓰는 키를 잡는다.

## 시군구 팩 (2026-10-13)

- 배포 팩은 시군구 단위 `<시군구코드>_<site|context|terrain>.db.xz`(dev_deploy가 시도 DB를 200 m 격자·PNU로 나눈다, 경계 객체는 양쪽에). 런타임은 대상지 범위에 걸리는 파일만 열고 id로 중복을 걷어 낸다.
- 필지 DB가 없어도 `can_download`면 블로커 없이 지도로 시작한다. 지도가 배율 16 이상이면 `area_packs`의 안 받은 팩을 저절로 `download_data{names}`(새 판은 칩 [받기]로만). 칩 [멈추기]를 누르면 그 패널에서는 자동 받기를 끈다. 블로커는 받을 곳이 없을 때(`can_download=false`)만.

## 데이터 모드 Korea · Global (2026-10-16 — 옛 '해외 대상지')

- **2026-10-19: 헤더 토글을 없앴다.** 모드는 위치로 정한다 — 대상지(없으면 지도 중심)가 `map.korea_bounds` 안이면 Korea, 밖이면 Global. 사각형 안 남동쪽 일본 모서리(`map.korea_cut` = [129.1, 35.0] — 그 동쪽·남쪽, 후쿠오카·기타큐슈·쓰시마)는 밖으로 본다(`non_rhino_utils.is_korea`와 같다). `options.region = "global"`은 더보기 메뉴 설정 '한국에서도 OpenStreetMap 쓰기'(한국 안에서도 Global)이고, `kr`·`null`은 자동이다. JS `region()`이 이 규칙으로 보낼 값을 정한다. 자료 날짜·자료 경고는 패널에 없다.
- (예전) `options.region` = `kr`(국가 DB — 필지·건축물대장·UPIS·수치지형도, 한국 대상지만) | `global`(OSM·지형 타일 — 어디서나). prefs에 저장.
- 첫 실행(`options.region = null`)은 JS가 정한다: 국내 필지 DB가 있거나 · 시간대 `Asia/Seoul`(`Intl`) · 언어 `ko*`(`navigator.languages`) 중 하나면 `kr`, 아니면 `global`. 망 접속 없음, Mac·Windows 웹뷰·Blender 브라우저 공통.
- `search`·`set_area`·`set_point`·`preflight`에 JS가 `region`을 붙인다(`REGION_CMDS`). Global이면 필지 DB를 보지 않는다 — 검색은 Nominatim만, 구역 안 필지 0, preflight는 DB 개수 대신 경고 `abroad`, 생성은 `osm_context`(Overpass·지형 타일, 팩 받기 없음). 엔진 판정은 `context_builder.is_global(request)` = `region == "global"` 또는 지역 TM 원점.
- 좌표계는 모드가 아니라 위치로 정한다: 대상지 중심이 `map.korea_bounds` 밖이면 `set_area`·`set_point`가 투영 원점을 그 중심으로(`non_rhino_utils.set_projection`, 이후 `ring_tm`·`center_tm`은 지역 횡메르카토르 m), 한국 안이면 Global이어도 EPSG:5186. `select_lots`는 늘 EPSG:5186.
- Global: 필지 방식 칸 비활성(필지 방식이었으면 위치 방식으로), 지도 필지선·시군구 팩 칩·DB 안내 화면 없음, 구역 안의 필지 수 없음. 도면 목록은 `sheet_catalog[].korea_only`(= `constants.SHEET_KOREA_ONLY`)를 뺀다 — 엔진도 `get_sheet_ids`에서 뺀다.
- Korea에서 대상지가 한국 밖이 되면(`area_state`·`point_state` 중심) Global로 바꾸고 토스트. 한국 밖 대상지가 있는 채로 Korea는 고를 수 없다. 최근 대상지(필지)를 고르면 Korea로.
- 블로커(필지 DB 없음, 받을 곳 없음)는 Korea 모드에서만, 버튼 [Global로 쓰기].
- 하는 일이 없는 칸은 보이지 않는다: Global은 고급의 무벽·가건물·도시계획 경계선, 베이스맵 레이어 토지이용·용도지역, 결과 신뢰도의 정합 오차·국가 DB 기준일·필지 수가 없다. 한국 밖 대상지는 ③ 좌표 칸이 없고 늘 원점으로(실제 좌표가 지역 TM이라 GIS와 겹칠 수 없다). 행이 없는 조서 CSV는 쓰지 않는다.
- Global 역세권·공공시설 도면 = OSM `railway=station` 점(이름 있는 것) · 학교 면(학교 부지)·`place=square`(광장) · 시설 면(`constants.OSM_PUBLIC_USE`) 안 용도 미상 건물에 국내 용도 대분류(osm_context._apply_public_use).
- `search`(Korea): 국내 필지에서 못 찾거나 필지 DB가 없으면 OSM Nominatim 지명 후보 — `matches[].pnu = ""`, `center` 있음. JS는 위치 방식이면 `set_point`, 아니면 지도만 옮긴다.

## 대상지 방식 (2026-10-10)

① 첫 화면은 지도다(2026-10-14 — 소개·방식 고르기 화면 없음). 지도 위 도구줄의 방식 칸 [필지·구역·위치]로 바꾸고, 처음엔 마지막 방식(`options.mode`, 저장된 옵션 그대로). 방식을 바꾸면 대상지를 지우고 `init_state.modes.defaults[mode]`(constants `MODE_DEFAULTS` — 축척·대상지 바닥면만: 필지 1:1000·1:3000 / 구역 1:3000 / 위치 1:5000)를 옵션에 덮고 `save_prefs`. 범위(radius·shape)는 방식을 바꿔도 마지막 값 그대로다(기본 사각형 한 변 500 m = radius 250, 2026-10-19). `prefs.json`의 `version` < 2면 예전에 저장한 radius·shape는 한 번 버린다(`site_prefs.PREFS_VERSION`). [새 대상지]는 대상지만 지우고 같은 방식의 지도로.

| 방식 | 요청 `target` | 대상지 경계(`site_rings`) | 대상 필지 | 결과 폴더명 |
|---|---|---|---|---|
| lots 필지로 고르기 | `{mode:"lots", pnus}` | 합필 외곽(필지마다 가장 넓은 조각을 합친 것 — 맞닿지 않으면 덩어리마다) | 고른 필지 | `성수동2가_333-139(외n)` |
| area 구역 그리기 | `{mode:"area", ring:[[x,y]] EPSG:5186}` | 구역 링 1개 | 면적 50 % 이상이 구역 안인 필지(`AREA_LOT_MIN_FRACTION`) | `<중심 필지 동_지번>_구역` |
| point 위치만 찍기 | `{mode:"point", center:[x,y]}` | 없음 | 없음 | `<가장 가까운 필지>_일대` |

- 구역 안전장치(`non_rhino_utils.get_ring_problem`): 꼭짓점 3~2000개, 자기교차 없음, 면적 ≥ 100 ㎡, bbox 긴 변 ≤ 4 km. Rhino 커브는 추가로 닫힘·XY 평면(법선 ±Z)·`Intersection.CurveSelf` 0을 본다(`context_geometry.get_curve_ring`). 곡선 커브는 0.05 m 허용오차 폴리라인으로 바꾼다.
- Rhino 커브 위치: 이 도구가 만든 문서(문서 원점 있음)면 로컬 + 원점, 아니면 좌표가 서울 EPSG:5186 범위(`SEOUL_TM_BOUNDS`)면 그대로 = `located:true` → 패널이 바로 `set_area{ring_tm}`. 그 밖이면 모양만(`offsets` m) → 패널이 화면 가운데에 파란 구역을 고정해 얹고, 사용자가 지도를 끌어 맞춘 뒤 [여기에 놓기] → `set_area{center, offsets}`. 모양은 m 그대로라 축척이 변하지 않는다.
- 범위 형태(2026-10-19): 모든 방식이 circle|rect(`SHAPES_BY_MODE`). circle = 대상지 중심 반경 `radius`, **rect = 대상지 중심 한 변 2 × `radius` 정사각형**(예전: 대상지 bbox ± radius). 엔진은 예전 요청의 buffer·site(그린 경계 그대로)·frame(가장 큰 축척 용지 프레임)도 받는다.
- DB 조회 범위: 2D(`make_basemap`·`make_sheets`·`make_dwg`)가 꺼져 있으면 범위 bbox만(3D만 — 프레임 크기만큼 받지 않는다), 켜져 있으면 범위 ∪ 가장 큰 프레임 ∪ 도면 범위. 3dm 안 2D 선 도면(`BM::`)도 `make_basemap`·`make_dwg`일 때만 굽는다.

```jsonc
{"type":"area_state","ok":true,"text":"",            // ok=false면 text 한 줄(자기교차·너무 작음…) — 패널은 이전 구역을 유지한다
 "ring_tm":[[x,y]],"ring_lnglat":[[lng,lat]],"center":[lng,lat],"center_tm":[x,y],"offsets":[[dx,dy]],
 "area":60000.0,"lots":69,"lots_area":44242.0,"lot_name":"성수동2가_333-139_구역",
 "target_geojson":FC,                                 // role="target" 안의 필지 + role="area" 구역 1개
 "warnings":[warning]}
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
 "make_basemap":true,"paper":"A3","paper_mm":[420,297],"scales":[5000],"basemap_layers_on":[],"basemap_preset":"a3",   // basemap_preset: 패널 2D 카드 칩 a3|a1(축척을 범위에 맞춰 자동 — 범위 2 × radius가 용지에 들어가는 가장 상세한 축척)|custom. 엔진은 보지 않는다   // A3 가로 = 분석도 템플릿 기준(2026-10-13)   // "02b_landuse"|"05_road_center"|"11_zoning" — Global은 05만 보인다
                                                       // scales: ② 프레임 미리보기·③ .ai select 기본값 전용(prefs·preflight에만). generate 페이로드에서 JS가 뺀다. dirty 판정 제외
 "make_sheets":true,"sheet_ids":[0,1,…,22],"floor_breaks":[12,20],"elev_preset":"20m",   // "20m"|"50m". 카탈로그에 없는 id는 엔진이 버린다(get_sheet_ids)
 "make_tables":true,
 "include_minor_buildings":false,                       // Korea만 보인다(국가 DB 무벽·가건물). 2026-10-16 v1에서 아무 일도 안 하던 demolished·refresh_buildings·include_api_objects는 뺐다
 "include_zoning":true,                                // Korea만 보인다   // CTX::Zoning::<구분>::<종류> — 용도지역·용도지구·용도구역·도시계획시설·지구단위계획(현황도 11~13 범례 색, 범위 bbox로 자름)
 "terrain_vertex_color":false,
 "terrain_step":0,                                     // 지형 표현(③ 지형): 0 = 매끈, 1|2|5 = 계단형(등고 모형) 단 간격 m. 지반·수면 메시를 단마다 수평면 + 수직 벽으로, 건물 바닥도 계단 지반 기준
 "terrain_block":true,                                 // 지형을 바닥까지 채우기: 지형 옆면·바닥(CTX::Terrain::block, BASE_M). 건물·필지·도로중심선·용도지역은 이 값과 상관없이 늘 범위 링으로 자른다(원·사각형 범위만). 끄면 3D 설정 요약에 '지형 표면만'. 입체 매스도는 style.axo_ground
 "make_dwg":false,                                     // 3dm 2D 도면(BM::)만 basemap_<축척>.dwg로도 저장(고급 > 3dm). 결과 경로는 done.context.dwg
 "zoom_after_import":true,
 "style":{"preset":"std"}}                              // 도면 스타일 — 사용자가 고른·바꾼 값. 해석은 sheet_svg.get_style(STYLE_*): 색 10개(paper·block·road·green·water·building·rail·site·extent·ink),
                                                       // ramp, layout(side|bottom|map), line_scale, text_scale, font(sans|serif), fade_outside, labels, subtitle_en, project, name(저장한 스타일),
                                                       // axo_view(se|sw|ne|nw — 입체 매스도 시점, Rhino 등각. 스타일 화면에서 바꾸면 미리보기가 입체 매스도로 넘어간다)
                                                       // axo_ground(block|flat — 입체 매스도 지형. block = 지형 덩어리(기본), flat = 평평한 바닥. 3D의 terrain_block과 따로. 바꾸면 미리보기가 입체 매스도로)
```

2026-10-19: `make_basemap`·`make_sheets`·`make_tables` 기본 false(3D 먼저). 패널은 `generate`에 이 셋과 `make_dwg`를 false로(DWG는 2D 카드의 베이스맵 'DWG로도 저장' → `make_2d`), `import_after`·`zoom_after_import`를 true로, `include_minor_buildings`를 false로 고정해 보낸다 — prefs의 `make_*`는 결과 화면 2D 카드 체크의 마지막 값이고 `make_2d`가 쓴다. `shape`가 circle·rect가 아니면(옛 prefs) 패널이 circle로 바꾼다.

28개. 모르는 키는 Python이 무시하고 빠진 키는 기본값(constants)으로 채운다. `generate`는 `pnus`를 옵션 밖 별도 키로 받는다(옵션은 대상지와 독립이어야 prefs로 재사용된다). **`scales`는 `generate`에도 포함한다**(code_map §3: 가장 큰 프레임이 질의 범위) — dirty 판정에서는 여전히 제외.

## 상태 머신

**화면(2026-10-19 2화면)**: `screen ∈ {map, result}` + 결과 화면 안 하위 화면 `styleOpen`. 3D 상태 `run ∈ {idle, running, done, failed, cancelled}`, 2D 상태 `job2d ∈ {idle, running, done, failed, cancelled}` + `blocked`. `document.body.dataset.screen/run`으로 노출해 CSS가 섹션 표시를 처리한다.

| 현재 | 이벤트 | 다음 | 부수 효과 |
|---|---|---|---|
| (시작) | `init_state.blocked=true`(받을 곳 없음) | blocked | 블로커. [다시 확인] → `init` |
| (시작) | `init_state` | map, run idle | 마지막 방식의 지도. options·recent 복원 |
| 초기화 뒤 어디서나 | `init_state`([다시 확인]·받기 끝) | 변화 없음 | `tile`·`paths`·`blocked`·메뉴만 갱신. 화면·대상지·옵션·결과는 건드리지 않는다 |
| map | 방식 칸(다른 방식) | map | 대상지 지움(토스트 [되돌리기])·방식 기본값 적용·`save_prefs`. 구역이면 곧바로 그리기 |
| map | `lot_state.lots ≥ 1` / `area_state.ok` / `point_state.center` | map | 트레이에 범위·3D 설정. 지도에 범위(JS가 즉시 그림). [3D 모델 만들기] 활성(그리기·옮기기 중 비활성) |
| map | 범위·3D 설정 변경 | map | `save_prefs`(500 ms). 범위는 지도에 즉시 |
| map | [3D 모델 만들기] / ⌘Enter | result, run running | `generate`(§옵션 키의 고정값) |
| result running | `progress{state:"done"}` → `done` | result, run done | 3D 블록 + 2D 카드. Python이 `recent` 갱신 |
| result running | `progress{state:"failed"}` / `cancelled` | result, run failed/cancelled | 오류 블록. 푸터 [← 지도로][다시 시도] |
| result running | [취소] / 창 닫기 | (cancelled로) | `cancel`. Esc로는 취소하지 않는다(2026-10-19) |
| result done | [2D 만들기] | job2d running | `make_2d{dir, options}` — 진행은 2D 카드 자리 |
| job2d running | `made_2d` | job2d done/failed/cancelled | 2D 카드가 결과(.ai·다이어그램 격자·CSV)로 바뀐다 |
| result done | [← 지도로] / ⌘Enter | map, run idle | 대상지·옵션 유지. 결과·2D 상태는 JS가 맡겨 둔다(`state.last`) |
| map | [결과로 돌아가기] | result, run done | 맡긴 결과로. 대상지·범위·3D 설정(2D 옵션 뺀 `generate` 옵션)이 그 결과를 만들 때와 같을 때만 보인다. 메시지 없음. [3D 모델 만들기]는 맡긴 결과를 버린다 |
| result failed/cancelled | [다시 시도] | result, run running | 같은 `generate` |

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

`HOME_DIR`(constants) = 저장소·폴더 배포판처럼 루트에 `data/`가 있으면 루트, Yak 설치본이면 `~/Gorani`(패키지 폴더는 업데이트 때 바뀐다). `open_path`의 상대경로는 `HOME_DIR` 기준이고, 거기 없으면 코드 루트(`docs/install.md` 등)를 본다.

| 파일 | 내용 | 쓰는 쪽 | 읽는 쪽 |
|---|---|---|---|
| `~/.gorani/prefs.json` | `{"options":{…20키…(lang 포함)}, "recent":[{pnus,label,total_area,date}×5]}` | `save_prefs`(options), `generate` 성공(recent 앞에 삽입·중복 제거·5개), `remove_recent`(x) | `init` |
| `~/.gorani/source_news.json` | `{"checked_at":"2026-10-07","building":{"newer_date":"2026-09-09"},"lot":{…},"upis":{…}}` | `dev_check_sources.py`(P1. 없으면 `newer_date:null`) | `preflight`·`init`(배지)·생성기(`done.warnings`) |
| `~/.gorani/client_id` | 무작위 UUID 한 줄(사용 통계 설치 식별) | `usage_stats.get_client_id`(없으면 생성) | `usage_stats` |
| `.env`(`HOME_DIR`) | `VWORLD_API_KEY=…`(지도·위성 배경, 항공사진, 주소 보조 검색 — 없으면 OSM·Esri·지명 검색). `= ` 뒤 공백 금지 | 사용자(OS 편집기). 없으면 `open_path`가 한 줄 템플릿 생성 | `pnu_loader._read_local_env_value`(strip)·생성기 |
| `HOME_DIR/data/*.db`·`packs.json` | 필지·컨텍스트·등고선 DB. `packs.json` = 받은 팩의 sha256 | `download_data` | `init`·전 명령 |
| `HOME_DIR/result/<lot_name>_<YYYYMMDD>/` | deliverables §E. 2026-10-19부터 그 폴더에 이전 결과(`context.json`·3dm·blend·skp)가 있으면 첫 베이크 직전에 `<lot_name>_<YYYYMMDD>_<HHMM>/`(같은 분이면 `_2`…) 새 폴더를 쓴다(`context_builder.get_free_result_dir`) — 이전 결과를 지우지 않는다. 문서의 이전 3D는 그대로 바꾼다(`clear_previous`). 패널은 이 패널에서 이미 만든 대상지면 [3D 모델 다시 만들기]와 '이전 3D를 새것으로 바꿉니다'를 보인다. 2D는 `2D/` 아래 | 생성기·베이커(.ai) | `done`·`open_path` |

`localStorage`·쿠키는 쓰지 않는다(file:// 임시 파일 출처).

## 컨트롤러(cmd_site) 동작 규칙

- 명령 처리기는 `{"init": self._init, "search": …}` dict 하나. 모르는 cmd는 `error{context:"init"}`.
- `init`: DB 존재·기준일(`lot_db` `data_sources` 테이블, 컨텍스트 DB `source_files`), 키 유무(`VWORLD_API_KEY`·`DATA_GO_KR_KEY` 각각), 타일·지도 초기값, prefs, 시트 카탈로그 → `init_state`. `blocked = not lot_db`. preflight 메모이즈 비움. 네트워크 접근 없음.
- `preflight`: `context_builder.preflight({"pnus", "options"})` → dict. 메모이즈 키 = `(tuple(pnus), radius, shape, paper, tuple(paper_mm), tuple(scales))`. `init`마다 비움. 응답에 요청 `seq` 에코.
- `generate`: `context_builder.run({"pnus", "options"}, progress_callback, doc)`를 UI 스레드에서 동기 호출. 콜백 = push + `RhinoApp.Wait()` + 취소 플래그 확인. 응답 dict에 `type:"done"`을 붙여 push(ok=false면 `progress{state:"failed"|"cancelled"}`). 성공 시 `recent` 갱신.
- Rhino 문서 변경 후 `doc.Views.Redraw()`. 문서 조작은 `context_baker`만.
- 창 닫힘: running이면 `cancel_requested=True`(다음 콜백에서 중단).

## 프런트엔드(site_ui.html) 요점

레이아웃·문안은 `docs/ui_spec.md`, 토큰은 `DESIGN.md`. 여기서는 계약에 직접 걸리는 것만.

- 상태: `state = {screen, run, job2d, blocked, mode, lots, lotState, area, point, options, progress, result, made2d, seq:{map, packs, style}}`. `render()`는 **화면 전환 때만** 섹션 `innerHTML`을 다시 그린다. 푸시 핸들러는 **슬롯 요소만 교체**한다 — 입력 중 포커스·IME 조합·열린 `<details>`·로그 스크롤이 날아가지 않도록.
- `receive` 핸들러(슬롯만 교체): `init_state`→첫 수신이면 상태 복원·`render()`, 이후는 메뉴·블로커·타일만 / `search_result`→`#search_list` 또는 즉시 선택 / `map_lots`→`seq` 검사 후 `lotsLayer` / `lot_state`·`area_state`·`point_state`→트레이·`targetLayer`·범위 / `progress`→진행 목록·막대(3D면 결과 섹션, `job2d=running`이면 2D 카드) / `data_progress{in_generate}`→진행 목록의 받기 줄 / `log`→`<pre>` / `done`→결과 섹션 1회 렌더 / `made_2d`→2D 카드 / `imported`·`exported`→카드 안 슬롯·토스트 / `error`→`context` 슬롯.
- `preflight`는 패널이 보내지 않는다(2026-10-19 — 범위가 원·사각형뿐이라 JS가 그린다). 명령은 남아 있다(Blender·SketchUp·예전 패널).
- Leaflet 인스턴스 1개, 지도 화면에만 있다(결과 화면에서는 `#map_park`에 대피). `map.remove()` 금지. 줌 ≥ 17에서만 `map_lots`(moveend 250 ms 디바운스, `seq` 증가). `tileerror` 3회 → `fallback_url`로 `setUrl` 1회, 폴백 뒤에도 3회면 지도 위 칩.
- `generate` 페이로드: `{target, options}` — 옵션 키 절의 고정값을 덮어 보낸다. `make_2d` 페이로드: `{dir: result.dir, options}`.
- `?mock=1`: `send`를 콘솔 출력으로 바꾸고 `tests/fixtures/site_ui_mock.json`을 순서대로 흘린다(`init_state` → `search_result` → `lot_state` → `data_progress`·`progress`… → `done` → (`&step=2d`면) `progress`… → `made_2d`). `&step=1`은 지도까지, `&menu=1`은 메뉴를 연다. `&lang=ko`처럼 언어를 고른다(기본 영어).

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

GA4 Measurement Protocol로 데몬 스레드에서 보내고 실패는 버린다. 호스트마다 GA4 속성이 따로다(`constants.GA_STREAMS` — 키는 `context_builder.get_host()`, 웹사이트·SketchUp도 각자 속성). 그 호스트의 측정 ID·API secret이 비었을 때만 보내지 않는다. 끄는 설정은 없다(무료 도구 — 사용자 결정 2026-10-14). 보내는 항목은 `docs/install.md` §5에 고지(이 표와 같게 유지).

| 이벤트 | 보내는 곳 | 매개변수 |
|---|---|---|
| `panel_open` | 첫 `init` | `version`·`rhino`(Rhino 버전 — Rhino 7판도 이 키, 7.x) 또는 `host`(SketchUp `sketchup <버전>`)·`has_lot_db`·`packs`(받은 시군구 필지 팩 수) |
| `build` | `generate` 끝(성공·실패·취소) | `mode`·`lng`·`lat`·`korea` + 필지 `pnus`·`pnus_2`…(5개씩 최대 20필지)·`lot_count`·`area` / 구역 `area`·`width`·`height`(링은 보내지 않는다) + `result`·`error`·`elapsed_s`·`radius`·`shape`·`placement`·`buildings` |
| `pack_download` | `download_data` 끝 | `packs`(시군구 코드)·`count`·`requested` |
| `error` | `_guard`의 예상 밖 예외 | `context`·`error`(예외 타입명) |

모든 이벤트에 `session_id`(패널 하나)·`engagement_time_msec`, 요청에 `device`(OS·언어). GA 보고서에서 매개변수를 보려면 관리 > 맞춤 정의에 이벤트 범위 측정기준으로 등록한다.


### 결과물 언어 (2026-10-21)

`options.output_lang`(`constants.OUTPUT_LANGS`, 지금 ko·en)이 결과 폴더와 파일 이름의 언어를 정한다. 패널 글은 한국어 그대로다. 첫 실행(`null`)이면 패널이 시스템 언어로 고르고(지원 목록에 있으면 그것, 아니면 영어) `save_prefs`, 메뉴 설정 '결과 언어'에서 바꾼다. `generate`와 `make_2d` 둘 다 보낸다(`KEYS_2D`, `_2D_OPTION_KEYS`).

| 무엇 | 한국어 | English |
|---|---|---|
| 결과 폴더 꼬리 | `…외1`, `…_구역`, `…_일대` | `…+1`, `…_area`, `…_vicinity` |
| 2D 폴더 | `2D_선명_1432` | `2D_Vivid_1432` |
| 베이스맵 | `베이스맵_1000.ai`(.dwg) | `basemap_1000.ai` |
| 도면 폴더·파일 | `다이어그램/09_토지이용현황.svg` | `sheets/09_Land_use.svg` |
| 조서 폴더·파일 | `조서/필지조서.csv`, `건축물조서.csv`, `도면통계.csv`, `높이출처통계.csv`, `정합점검.csv` | `tables/parcels.csv` … |

동 이름·지번은 자료 그대로(로마자로 바꾸지 않는다). `context.3dm`·`context.json`·`log.txt`는 프로그램이 읽어 언어와 무관하다. 언어를 더하려면 `OUTPUT_LANGS`에 코드, `OUTPUT_NAMES`에 같은 꼴의 dict(도면 이름은 `"sheets": {키: 이름}`)를 더한다. 없는 항목은 영어로 채운다(`non_rhino_utils.get_output_name`). 읽는 쪽(`get_sheets_dir`·`find_named_subdir`, 베이스맵 축척 정규식)은 모든 언어 이름을 받는다.
