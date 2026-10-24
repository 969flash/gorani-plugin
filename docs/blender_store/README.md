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
- Blender 안 스레드 금지 — 패널 서버는 메인 스레드 poll(`panel_server.Bridge(threaded=False)`). 스레드 코드는 SketchUp 분기·위성 영상 분기에만 있고 Blender에서는 돌지 않는다.
- 분석 전송 금지(동의를 받아도) — Blender판은 사용 통계가 없다(`usage_stats`는 빈 판, `GA_STREAMS`에 blender 없음).
- `sys.path`·`sys.modules` 조작·모듈 다시 읽기 금지 — 패키지의 `loader.py`는 상대 import만, 진입 분기는 패키지 쪽만 남긴다.
- 상용·키 필요 서비스 금지 — Esri 위성 영상을 끈다(지도 [위성]·항공사진 도면 없음). OSM·Overpass·Nominatim·지형 타일은 무료·무가입이라 된다.
- 자체 업데이터 금지 — 매니페스트 업데이트 모달을 끈다(공지 띠는 남김). 코드 내려받기 없음(데이터 팩만).
- 영어 기본(심사 약 39건) — 패널은 첫 설치가 영어(0.3.0 다국어: 한·영·서·일·중), Blender 단추·메시지는 영어 + Blender 번역 시스템(ko_KR·es·ja_JP·zh_HANS).
- 사용자가 하지 않은 제3자 전송 금지 — 지도 첫 위치 IP 짐작(ipinfo.io)을 끈다(`HOST_LABELS` `ip_center`).
- `bpy.app.online_access`가 꺼져 있으면 패널을 열지 않는다. 파일·폴더 열기는 `wm.path_open`·`wm.url_open`.
- 매니페스트: 태그 `Import-Export`·`Scene`('3D View'는 자주 빼라고 한다), `support` = GitHub 이슈(스토어 'Report Issues'), tagline 64자 이하.
- 업로드는 Blender ID 2단계 인증이 켜져 있어야 한다.

남은 위험(심사 댓글이 오면 고친다):
- 데이터 팩(Hugging Face·국내 서버)을 받는 것 — 무료·무가입 데이터라 OSM과 같다고 보지만 '외부 에셋 팩'으로 볼 수도 있다. 국내 서버 요청에는 설치 ID가 붙는다(하루 한도) — 설명에 적어 두었다.
- 패키지에 Rhino 코드가 섞여 있다(`context_baker`·`context_geometry`의 공용 함수를 쓴다 — RhinoCommon import는 try 안).
- 쓰는 위치 `~/Gorani`·`~/.gorani` — 금지는 아니지만 '결과 폴더를 고르는 설정'을 권할 수 있다.
- 도면·조서의 지명(OSM 이름·국내 주소)은 데이터 그대로라 번역되지 않는다.

심사 질문에 답할 때(영어):
- Threading: "The add-on itself never starts a thread in Blender. The panel server runs on Blender's main thread with non-blocking sockets polled from a timer and from the progress callback. The threaded branch in panel_server.py is used only by our SketchUp sidecar, a separate process."
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

### Network (심사 답변 원문 — 새 서비스를 넣으면 여기와 BLENDER_ALLOWED_HOSTS를 같이 고친다)

Thank you for the review, and sorry for the messy first submission. You were right on several points. I re-read the guidelines and uploaded version 0.3.6, which cleans this up.

**What changed in 0.3.6**
- Hugging Face is removed. The data packs now come from a GitHub repository: https://github.com/969flash/gorani-data (sources and licenses are in its README). Hugging Face was only a file host for these public GIS files. The add-on does not use any AI model. (`basemap_ai.py` writes Adobe Illustrator `.ai` files. "ai" is the file format.)
- VWorld is removed. vworld.kr is the Korean government's map portal, and it blocks access from outside Korea. That is why you could not open it. The Blender build no longer contains any VWorld code path.
- The dead Overpass mirrors (overpass.kumi.systems, overpass.private.coffee) and maps.mail.ru are removed.
- The build now checks every URL in the package against an allow list, so no other service can slip in.

**Where the data comes from.** Everything is free, with no account and no API key. Requests happen only after the user clicks, and only when Online Access is on.
1. Panel map: OpenStreetMap standard tiles (tile.openstreetmap.org), with an identifying User-Agent as the tile usage policy asks.
2. Buildings, roads and water anywhere: OpenStreetMap through the Overpass API. The add-on uses overpass-api.de (the main public instance), with overpass.openstreetmap.fr (OSM France) as fallback. Both are listed at https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances. Place search uses nominatim.openstreetmap.org.
3. Terrain anywhere: Terrain Tiles from the Registry of Open Data on AWS (s3.amazonaws.com/elevation-tiles-prod). This is a free public dataset: https://registry.opendata.aws/terrain-tiles/. The add-on downloads plain image files over HTTPS; no AWS account or key is needed. For sites in Japan it uses the Japanese government's GSI elevation tiles instead (cyberjapandata.gsi.go.jp, free: https://maps.gsi.go.jp/development/ichiran.html).
4. Official open building data for Korea (parcels), Japan, the Netherlands, France, Switzerland and the USA: SQLite packs on GitHub. The manifest comes from raw.githubusercontent.com and the packs from github.com releases. Each pack is checked against the sha256 in the manifest.
5. Korea only, buildings, roads and contours: this data comes from Korea's national base map. Korean law (Spatial Data Act, Article 16) does not allow it to be stored outside Korea. So it is served as static files from a small server in Korea (Oracle Cloud, always-free tier, 150.230.249.1). Users need no account, and nobody pays for it. Each file is checked against the sha256 in the manifest from GitHub.

Links that open in the browser only when the user clicks them: the project website, and the Korean land-use plan page (eum.go.kr) for a selected parcel. The add-on sends no analytics.

I tested every service above on 2026-10-25. With the 0.3.6 package, a full build works in Seoul, Paris and Tokyo.
