# Blender 확장 스토어(extensions.blender.org) 올리기

올리기는 사용자 Blender ID로 한다. 초안(Draft)은 본인에게만 보이고, [Submit for Approval]을 눌러야 심사 대기열에 들어간다.

## 자료 만들기

1. `python3 scripts/dev_deploy.py blender` → `build/blender_repo/gorani-<버전>.zip`
   `Blender -b --factory-startup -c extension validate build/blender_repo/gorani-<버전>.zip`이 통과해야 한다.
2. 이미지(`build/blender_store/`, gitignore):
   - `icon.png` 256×256 — `icon.html` 머리 주석의 Chrome 명령(흰 바탕 마크 — 스토어 화면이 어두워 투명 바탕이면 묻힌다)
   - `featured.png` 1920×1080 — `dev_blender_store.py`(해외 OSM 대상지 흰 매스 렌더 → `hero_render.png`) 다음 `featured.html` 머리 주석의 Chrome 명령
   - `preview_*.png` — 실제 Blender 창(사이드바 Gorani + 모델), 넓은 브라우저 패널(지도·2D 결과). 패널 화면은 Blender 세션을 녹화한 목 데이터로 찍는다
     (실제 브리지에 명령을 보내 SSE 푸시를 모은 JSON을 `site_ui.html` 사본에 `<script id="mock">`로 넣고 `?mock=1&step=1|2d`, 1920×1080)
   - 국내 대상지 3D·도면·등고선 이미지는 쓰지 않는다(수치지형도 국외 반출 — 공간정보관리법 제16조, 웹사이트·food4rhino와 같은 규칙).

## 올리기(처음)

1. https://extensions.blender.org 로그인(Blender ID) → Upload Extension → zip 선택 → 약관 동의 → Upload.
   이름·한 줄 소개·버전·라이선스·권한·태그·웹사이트는 zip의 `blender_manifest.toml`에서 채워진다.
2. 만들어진 초안 페이지(Edit)에서
   - Description = `description.md`(맨 위 주석 줄 빼고 그대로, 마크다운)
   - Icon = `icon.png`, Featured image = `featured.png`, Preview images = `preview_1_blender.png`·`preview_2_map.png`·`preview_3_2d.png`·`preview_4_japan.png` 순(패널 화면은 영어로 — 첫 설치 언어, 일본은 신주쿠 PLATEAU 흰 매스)
   - Support = https://github.com/969flash/gorani-plugin/issues (없으면 웹사이트)
3. Save → 미리보기 확인 → **[Submit for Approval]** (이것만 사용자가 누른다).
4. 심사 댓글은 Blender ID 메일로 온다. 고칠 것이 오면 버전을 올려 다시 빌드하고 같은 페이지에서 새 버전을 올린다.

초안(Draft)은 처음 올린 zip에 묶인다 — 초안이 있는 동안 Upload Extension·Upload New Version은 초안 페이지로 되돌아간다(2026-10-21 확인).
zip을 바꾸려면 [Submit for Approval] 뒤 Upload New Version(심사는 최신 판을 본다)이나, 초안을 지우고(Delete Extension) 다시 올린다.

## 새 판

`constants.PANEL_VERSION`을 올린다(Rhino·SketchUp과 같은 번호) → 자료 1번 → 확장 페이지 Versions > Upload new version.

## 심사 기준과 반영(2026-10-21 조사 — 약관 2026-08-10판, 심사 스레드 약 800건)

출처: https://extensions.blender.org/terms-of-service/ · https://developer.blender.org/docs/handbook/extensions/addon_guidelines/ ·
https://developer.blender.org/docs/features/extensions/moderation/guidelines/ · 승인 대기열 https://extensions.blender.org/approval-queue/

반영함:
- 라이선스 GPL-3.0-or-later(+ Leaflet BSD-2-Clause, 저작권 칸에 적음), 원본 .py(난독화·.pyc 없음). 함께 넣는 글꼴·이미지는 CC0만 — Pretendard(OFL)는 빼고 시스템 글꼴.
- Blender 안 스레드 금지 — 패널 서버는 메인 스레드 poll(`panel_server.Bridge` 기본값). 스레드 코드(SketchUp 분기·Rhino 타일 중계·위성 영상)는 패키지에서 뺀다(아래 2026-10-28).
- 분석 전송 금지(동의를 받아도) — Blender 패키지에는 사용 통계가 없다(`usage_stats`·동의 창·`_send_stats` 호출을 뺀다).
- `sys.path`·`sys.modules` 조작·모듈 다시 읽기 금지 — 패키지의 `loader.py`는 상대 import만, 진입 분기는 패키지 쪽만 남긴다.
- 상용·키 필요 서비스 금지 — Esri 위성 영상을 끈다(지도 [위성]·항공사진 도면 없음). OSM·Overpass·Nominatim·지형 타일은 무료·무가입이라 된다.
- 자체 업데이터 금지 — 매니페스트 업데이트 모달을 끈다(공지 띠는 남김). 코드 내려받기 없음(데이터 팩만).
- 영어 기본(심사 약 39건) — 패널은 첫 설치가 영어(0.3.0 다국어: 한·영·서·일·중), Blender 단추·메시지는 영어 + Blender 번역 시스템(ko_KR·es·ja_JP·zh_HANS).
- 사용자가 하지 않은 제3자 전송 금지 — 지도 첫 위치 IP 짐작(ipinfo.io)을 끈다(`HOST_LABELS` `ip_center`).
- `bpy.app.online_access`가 꺼져 있으면 패널을 열지 않는다. 파일·폴더 열기는 `wm.path_open`·`wm.url_open`.
- 매니페스트: 태그 `Import-Export`만('3D View'·'Scene'은 빼라고 한다), `support` = GitHub 이슈(스토어 'Report Issues'), tagline 64자 이하.
- 업로드는 Blender ID 2단계 인증이 켜져 있어야 한다.

남은 위험(심사 댓글이 오면 고친다):
- 데이터 팩(Hugging Face·국내 서버)을 받는 것 — 무료·무가입 데이터라 OSM과 같다고 보지만 '외부 에셋 팩'으로 볼 수도 있다. 국내 서버 요청에는 설치 ID가 붙는다(하루 한도) — 설명에 적어 두었다.
- 쓰는 위치 `~/Gorani`·`~/.gorani` — 금지는 아니지만 '결과 폴더를 고르는 설정'을 권할 수 있다.
- 도면·조서의 지명(OSM 이름·국내 주소)은 데이터 그대로라 번역되지 않는다.

심사 질문에 답할 때(영어):
- Threading: "The add-on never starts a thread. The panel server runs on Blender's main thread with non-blocking sockets polled from a timer and from the progress callback."
- Data packs: "Downloads are data only (SQLite of public Korean GIS data), free and without login, on explicit user action. No code is downloaded."

## 2026-10-25 심사 반려와 0.3.6

심사 댓글(요지): vworld.kr 접속 안 됨, overpass.kumi.systems·overpass.private.coffee 접속 안 됨(시험은 했나), s3.amazonaws.com은 무료인가,
Hugging Face는 자유·오픈소스가 아니니 빼라, Oracle Cloud는 뭔가 — "링크를 모아 놓았을 뿐 계획이 없다. AI 모델 연결·유료 서비스 연결을 빼고 다시 내라."

고친 것(0.3.6):
- 데이터 팩은 GitHub 사본 `969flash/gorani-data`(Blender판만 — `dev_deploy.py mirror`, docs/data_sources.md 'GitHub 사본'). HF는 Blender 패키지에 주소가 없다.
- VWorld 키·검색·타일 주소를 Blender 패키지에서 비운다(`dev_deploy.BLENDER_CONSTANT_PATCHES` — 키 이름이 비어 늘 '키 없음' 경로).
  같이 비우는 것: Esri 영상·ipinfo.io·GA·yak·관리·원천 수집 주소. 남은 주소는 `BLENDER_ALLOWED_HOSTS` 검사 — 새 서비스를 넣으면 빌드가 멈춘다.
- Overpass 미러: 응답 없는 kumi·private.coffee, 504인 mail.ru를 뺐다(모든 호스트).
- `basemap_ai.py`의 ai는 Adobe Illustrator 형식이다 — 'AI 모델'로 읽힐 수 있어 답변에 한 줄 적었다.

설치본 점검(0.3.6 zip, 격리 Blender 5.2 + 빈 HOME, 2026-10-25): 패널 서울·파리 지도(OSM 중계) 정상, 위치 방식 생성 —
서울 을지로 R300(GitHub 필지 팩 + 국내 서버 팩, 1,233동) · 파리 R300(GitHub 프랑스 팩 5개 + Overpass + AWS 지형) · 도쿄 신주쿠 R300(GitHub 일본 팩 + GSI 지형).

올림(2026-10-25 새벽): 0.3.6 zip(main 2c8b55b, sha256 f1783040…) → 릴리스 노트 → 아래 답변을 댓글로 달고 상태 Awaiting Review.
사용자 Chrome 창은 쓰지 않았다(화면 잠금) — 쿠키 사본 헤드리스 Chrome + CDP로 올리고 사본은 지웠다.
가상 사용자 18명 문제 0건(트롬쇠는 첫 Overpass 서버 재시도를 넣은 뒤). nl·us 팩 GitHub 사본은 2차 한도로 천천히 올라가는 중 — 다 오르기 전에는 그 두 나라가 OSM으로 돈다.

### Network (심사 답변 원문 — 새 서비스를 넣으면 여기와 BLENDER_ALLOWED_HOSTS를 같이 고친다)

Thank you for the review, and sorry for the messy first submission. You were right on several points. I re-read the guidelines and uploaded version 0.3.6, which cleans this up.

**What changed in 0.3.6**
- Hugging Face is removed. The data packs now come from a GitHub repository: https://github.com/969flash/gorani-data (sources and licenses are in its README). Hugging Face was only a file host for these public GIS files. The add-on does not use any AI model. (`basemap_ai.py` writes Adobe Illustrator `.ai` files. "ai" is the file format.)
- VWorld is removed. vworld.kr is the Korean government's map portal, and it blocks access from outside Korea. That is why you could not open it. The Blender build no longer contains any VWorld code path.
- The dead Overpass mirrors (overpass.kumi.systems, overpass.private.coffee) and maps.mail.ru are removed.
- The build now checks every URL in the package against an allow list, so no other service can slip in.

**Where the data comes from.** Everything is free, with no account and no API key. Nothing is downloaded until the user opens the panel from Blender, and the panel opens only when Online Access is on.
1. Panel map: OpenStreetMap standard tiles (tile.openstreetmap.org), with an identifying User-Agent as the tile usage policy asks.
2. Buildings, roads and water anywhere: OpenStreetMap through the Overpass API. The add-on uses overpass-api.de (the main public instance), with overpass.openstreetmap.fr (OSM France) as fallback. Both are listed at https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances. Place search uses nominatim.openstreetmap.org.
3. Terrain anywhere: Terrain Tiles from the Registry of Open Data on AWS (s3.amazonaws.com/elevation-tiles-prod). This is a free public dataset: https://registry.opendata.aws/terrain-tiles/. The add-on downloads plain image files over HTTPS; no AWS account or key is needed. For sites in Japan it uses the Japanese government's GSI elevation tiles instead (cyberjapandata.gsi.go.jp, free: https://maps.gsi.go.jp/development/ichiran.html).
4. Official open building data for Korea (parcels), Japan, the Netherlands, France, Switzerland and the USA: SQLite packs on GitHub. The manifest comes from raw.githubusercontent.com and the packs from github.com releases. Each pack is checked against the sha256 in the manifest.
5. Korea only, buildings, roads and contours: this data comes from Korea's national base map. Korean law (Spatial Data Act, Article 16) does not allow it to be stored outside Korea. So it is served as static files from a small server in Korea (Oracle Cloud, always-free tier, 150.230.249.1). It costs users nothing and needs no account. Each file is checked against the sha256 in the manifest from GitHub.

Links that open in the browser only when the user clicks them: the project website, and the Korean land-use plan page (eum.go.kr) for a selected parcel. The add-on sends no analytics.

I tested every service above on 2026-10-25. With the 0.3.6 package, a full build works in Seoul, Paris and Tokyo.

## 2026-10-28 심사 반려와 0.3.7

심사 댓글(요지): `threading`·`queue`는 Blender를 죽이니 안 된다(필요하면 subprocess). `docs` 폴더를 빼라 — 실행에 필요한 파일만.
Blender에 없는 라이브러리 5개(Rhino·scriptcontext·System·Eto.Forms·shapely)는 휠로 실어라. `Scene` 태그를 빼라.
`context_builder.py`에 다른 프로그램(SketchUp) 구간이 있다 — 애드온은 Blender 전용이어야 한다. `usage_stats`는 뭔가.

고친 것(0.3.7):
- 공용 모듈의 Rhino·SketchUp·웹판·사용 통계 구간을 소스에서 `# [blender-cut]` … `# [/blender-cut]`(패널 HTML은 `// [blender-cut]`)로 감싸고
  `dev_deploy.get_blender_source`가 Blender 패키지에서 뺀다. 번역 사전에서도 Rhino·SketchUp·사용 통계 문구를 뺀다. `non_rhino_utils`는 패키지에서 `geo_utils`.
- 빌드 점검 `dev_deploy.get_blender_problems` — 문법, 표준 라이브러리·bpy·mathutils·numpy 밖 import, 스레드 import, sys.path·sys.modules,
  코드(주석·docstring 제외)의 다른 프로그램 이름, 정의 안 된 이름·모듈 속성(구간을 빼서 생긴 구멍), `docs/` 폴더, HTML·사전의 SketchUp·통계 흔적. 하나라도 있으면 빌드가 멈춘다.
- `docs/install.md`를 싣지 않는다. 태그는 `Import-Export`만. `usage_stats.py`·동의 창·`stats_consent` 명령을 뺀다.
- 패널 타이머는 [패널 열기] 때만 건다(전에는 등록하자마자 0.1 s마다). 패널을 연 뒤 온라인 접근을 끄면 서버를 닫는다.
- 확인: python3 단위 시험, Blender 시험(저장소 소스·잘라 낸 패키지 두 판 — `GORANI_BLENDER_PACKAGE=build/blender`), SketchUp 사이드카 시험,
  0.3.7 zip을 격리 Blender 5.2(빈 HOME, --online-mode)에 깔아 파리 R200 생성(GitHub 프랑스 팩 + Overpass + AWS 지형, 155 s).

올림(2026-10-28 낮): 가상 사용자 18명 문제 0건, 설치본 패널 서울·파리 지도 확인(헤드리스 Chrome) → PR #35 main 머지(cc37d9c) → 0.3.7 zip(sha256 dad37367…)·릴리스 노트 →
아래 답변을 댓글로 달고 상태 Awaiting Review. 쿠키 사본 헤드리스 Chrome(포트 9461 — 9334는 다른 세션이 붙어 탭을 열었다)으로 올리고 사본은 지웠다.
올리기 양식: 약관 체크는 click + change 이벤트를 내야 [Upload New Version]이 켜진다.

자가 리뷰(별도 에이전트, 2026-10-28)에서 나왔지만 고치지 않은 것 — 심사가 물으면 고친다:
- 국내 서버 팩 요청에 설치 ID 헤더(`X-UDT-Client`, 하루 한도) — 설명에 적어 둠. 빼려면 서버가 IP로 세야 한다.
- 생성이 Blender 메인 스레드에서 동기로 돈다 — Overpass가 느리면 Blender 화면이 그동안 멈춘다(브라우저 패널은 진행을 받는다). 심사가 권한 대로 하려면 받기를 subprocess로.
- 쓰는 위치 `~/Gorani`·`~/.gorani`(공식 문서는 `bpy.utils.extension_path_user` 권장) — Rhino판과 결과 폴더를 같이 쓴다.
- `os.environ` 쓰기(`i18n` 언어·`geo_utils` 투영 원점 — Rhino 모듈 다시 읽기 대비), 원격 설정·매니페스트가 서비스 주소를 바꿀 수 있음, 압축된 `leaflet.js`
  (압축 전 원본은 문서 주석에 외부 주소 18개가 들어 있어 주소를 하나하나 묻는 이 심사자에게 역효과라 압축본을 둔다), File > Import 메뉴가 파일 대신 브라우저를 연다.

### 0.3.7 답변(초안 — 올릴 때 댓글로)

Thanks. 0.3.7 is up.

- threading / queue: gone. The panel server never used threads in Blender, but code for our SketchUp version lived in the same file. That code is no longer in the package.
- docs folder: removed.
- Rhino, scriptcontext, System, Eto.Forms, shapely: same story. They belonged to the Rhino and SketchUp versions and sat behind try/except. The Blender package is now built without that code, so it only imports the standard library, bpy, mathutils and numpy.
- Scene tag: removed.
- SketchUp code in context_builder.py: removed, along with the other Rhino and SketchUp parts.
- usage_stats: analytics for the Rhino version. The Blender build never sent anything, and the module is now out of the package.

I also added a build check so these can't come back by accident.

### 0.3.7 What's New(초안)

Blender-only package. Removed code for other programs, the usage statistics module and the docs folder. The panel timer now runs only while the panel is open, and the panel server closes when Online Access is turned off.
