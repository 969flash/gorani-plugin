# SketchUp Extension Warehouse 올리기

올리는 일은 사용자 계정(Trimble ID)으로 한다. 개발자 등록은 따로 승인을 받아야 업로드 칸이 열린다.

## 순서

1. 빌드 — `python3 scripts/dev_deploy.py sketchup` → `build/bsh_gorani-<버전>.rbz`(약 90 MB). 배포용은 깨끗한 origin/main 워크트리에서 만든다.
2. 이 Mac에서 써 본다 — 확장 > 확장 관리자(Extension Manager) > Install Extension > rbz.
   서명 전이라 확장 관리자 왼쪽 아래 톱니 > Loading Policy = Unrestricted가 필요하다(올린 판은 Warehouse가 서명한다).
3. https://extensions.sketchup.com 에 Trimble ID로 로그인 → 개발자 등록(지원 연락처 필수 — 아래 '개발자' 칸) → 승인 메일을 기다린다.
   2026-10-22 신청함(Settings > Apply to be a developer! → Developer → 지원 이메일·홈페이지 → Next가 곧 제출) — 승인 메일 대기 중. 승인 전에는 메뉴에 My Extensions가 없다.
4. My Extensions > Upload Extension → rbz → 아래 '칸'을 채운다 → 심사 제출.
5. 심사 결과는 메일로 온다. 승인되면 My Extensions에서 직접 Publish해야 공개된다.
   고칠 것이 오면 버전을 올려 다시 빌드하고 같은 확장의 새 판(Create New Draft)으로 올린다.

새 판: `constants.PANEL_VERSION`을 올린다 → 1번 → 확장 페이지에서 새 판 업로드. Title·Version은 rbz의 `SketchupExtension`과 같아야 한다(`Gorani`, `PANEL_VERSION`).

## 개발자

- 계정: Trimble ID bsh969flash@gmail.com(표시 이름 Shabushabu H. — 바꾸려면 Trimble Profile)
- Support email: bsh969flash@gmail.com(신청에 넣음)
- Company Home Page: https://969flash.github.io/gorani/en/(신청에 넣음)
- Support URL: https://github.com/969flash/gorani/issues

## 칸

**Title**: Gorani

**Version**: rbz와 같은 값(`constants.PANEL_VERSION`)

**Short description**(영어 다음 줄에 한국어):

The city around your site, modeled in SketchUp. Free 3D buildings, roads and terrain from OpenStreetMap, plus parcels, zoning and contours in Korea.
지도에서 대상지를 고르면 주변 건물·도로·지형이 SketchUp에 3D로 들어옵니다. 무료입니다.

**Description**(영어 다음에 한국어를 이어 쓴다. 두괄식, 한 줄에 한 가지):

```
The city around your site, modeled in SketchUp.
Pick a site on the map and the buildings, roads and terrain around it come into your open model. It's free.

How to use
1. Install Gorani and click Extensions > Gorani (or the Gorani toolbar button).
2. Pick a site on the map: click parcels, draw an area or drop a point.
3. Choose the extent and press the 3D button.

What you get
- 3D: building masses, terrain, roads, parks, water and railways. Each layer is a tag in the CTX folder.
- Buildings: one solid group per building with height and floors attached.
- 2D (optional): layered Illustrator basemap (1:1,000 to 1:5,000), urban analysis maps (SVG, AI) and CSV tables.
- Every run is one Undo step, and a copy is saved as context.skp in ~/Gorani/result.

Data
- Worldwide: OpenStreetMap buildings and roads with public terrain data. Needs an internet connection.
- Korea: nationwide parcels, zoning, buildings and 1:5,000 contours. Each district is downloaded once.

Good to know
- SketchUp 2022 or later, Windows and macOS. Nothing else to install.
- Gorani brings its own Python engine. It runs as a helper process, and the panel talks to it only on your computer (127.0.0.1).
- The panel is in English, Korean, Spanish, Japanese and Chinese. Pick the language from the globe button at the top.
- Usage statistics are sent only if you opt in from the panel.
- Results with Korean contours or elevations must not be posted online (National Geographic Information Institute security rules).

한국어

지도에서 대상지를 고르면 주변 건물·도로·지형이 SketchUp에 3D로 들어옵니다.
대지 주변 현황 모델을 직접 그릴 필요가 없습니다. 무료입니다.

사용 방법
1. 설치하고 확장 > Gorani(또는 Gorani 도구 막대 단추)를 누릅니다.
2. 지도에서 대상지를 고릅니다. 필지 클릭, 구역 그리기, 위치 찍기 중 하나입니다.
3. 범위를 정하고 [3D 모델 만들기]를 누릅니다.

결과물
- 3D: 건물 매스, 지형, 도로, 녹지, 하천, 철도가 CTX 태그 폴더에 태그별로 들어옵니다.
- 건물: 동마다 솔리드 그룹이고 높이·층수 속성이 붙습니다.
- 2D(필요할 때만): 일러스트레이터 베이스맵(1:1,000~1:5,000), 현황도·분석도(SVG·AI), 조서 CSV를 만듭니다.
- 한 번 만든 것은 실행 취소 한 번으로 지워지고, 사본이 ~/Gorani/result에 context.skp로 남습니다.

데이터
- 국내: 전국 필지 경계·용도지역·건물·1:5,000 등고선. 지역 데이터는 처음 한 번 받습니다(구 하나에 수십 MB).
- 해외: OpenStreetMap 건물·도로와 공개 지형 데이터. 만들 때 인터넷이 필요합니다.

참고
- SketchUp 2022 이상(윈도우·맥)에서 씁니다. 따로 설치할 것은 없습니다.
- 계산 엔진(파이썬)이 확장에 들어 있습니다. 내 컴퓨터 안(127.0.0.1)에서만 패널과 주고받습니다.
- 패널은 영어·한국어·스페인어·일본어·중국어를 지원합니다. 위쪽 지구본 단추에서 고릅니다.
- 사용 통계는 패널에서 동의한 사람만 보냅니다.
- 등고선·표고가 들어간 국내 결과물은 인터넷에 올리면 안 됩니다(국토지리정보원 보안관리규정).
```

**Price**: Free

**SketchUp versions / OS**: 2022, 2023, 2024, 2025, 2026 / Windows, macOS

**Category**(있는 것 중에서): Architecture, Urban Planning, Landscape, GIS/Mapping, Modeling

**Tags**: site context, urban design, city model, OpenStreetMap, GIS, terrain, topography, contours, basemap, site analysis, Korea

**Release notes**: First release.

**Images**(1920×1080, `build/sketchup_store/`): `card_hero.png`(대표) · `card_window.png` · `card_twod.png`. 아이콘 `icon_512.png`·`icon_256.png`.
`card_world.png`(도쿄 긴자)는 2026-10-21 Overpass 장애로 못 만들었다 — `render_world.png`를 만들면 넣는다.

**Notes for reviewers**(칸이 있으면, 없으면 설명 끝에):

```
How to test:
1. Extensions > Gorani opens the panel (English by default).
2. Click "Point" at the top left, type "Flatiron Building, New York" in the search box and press Enter.
3. Press "Create 3D model" at the bottom right. It takes 30-60 seconds, depending on the OpenStreetMap servers,
   and the context appears as one group "Gorani N40.74…". One Undo removes it.
4. Optional: "Create 2D material" writes drawings to ~/Gorani/result. Nothing else touches the model.

Why there are executables:
- SketchUp has no Python, so the geometry engine runs in a bundled CPython 3.12 (python-build-standalone, PSF license)
  with numpy and shapely (BSD). It is started with -I -B and writes nothing into the extension folder.
  Data packs, results and logs go to ~/Gorani.
- The panel (UI::HtmlDialog) is served by that process on 127.0.0.1 with a random per-session token.
- All model changes happen in Ruby (BSH::Gorani), wrapped in one start_operation/commit_operation per run.
- Network: map tiles, an approximate start position for the map (ipinfo.io), regional data packs (Hugging Face and
  a Korean server), OpenStreetMap Overpass/Nominatim for sites outside Korea, and Google Analytics only after the user opts in.
```

## 이미지

해외(OpenStreetMap) 대상지만 쓴다 — 수치지형도에서 나온 국내 3D·도면·등고선은 해외 사이트에 올리지 않는다(공간정보관리법 제16조).

1. SketchUp에서 뉴욕 플랫아이언(구역, 원 250 m)·도쿄 긴자(위치, 원 250 m)를 만들고, 흰 매스·그림자 보기로 `view.write_image(transparent: true)` →
   `build/sketchup_store/render_nyc.png`·`render_world.png`(2400×1500). 실제 화면(패널 + 모델)은 `window.png`.
2. 2D 카드 그림은 뉴욕 결과의 `2D/sheets/*.svg`를 `build/sketchup_store/sheets/s<번호>.svg`로 복사한다.
3. 카드: `docs/sketchup_store/cards.html` 머리 주석의 Chrome 명령(`?card=hero|window|twod|world`) → `card_*.png`.
4. 아이콘: `docs/blender_store/icon.html`을 Chrome으로 256(그대로)·512(`--force-device-scale-factor=2`).

## 심사 규칙에 맞춘 것(이미 반영)

- rbz 뿌리에 `bsh_gorani.rb` 하나 + 같은 이름 폴더 하나, Ruby는 전부 `BSH::Gorani` 안. 뿌리 파일은 등록만 한다.
- 전역 변수·eval·exit·`$LOAD_PATH`·`ENV` 변경·gem 설치·puts 없음. 모델 변경은 작업(start_operation) 하나로 묶는다. 대화창은 HtmlDialog.
- 사용 통계는 동의한 사람만(패널이 처음 한 번 묻는다). `constants.GA_STREAMS["sketchup"]`이 비면 묻지도 보내지도 않는다.
- 업데이트를 스스로 받아 깔지 않는다 — 패널은 새 판이 나왔다고 알리고 확장 관리자로 안내만 한다. 받는 것은 데이터 팩(SQLite)뿐이다.
- 번들 파이썬·라이브러리 약관 사본: `python/<플랫폼>/…/LICENSE.txt`(PSF), `site-packages/*.dist-info/licenses/`(numpy BSD, shapely BSD·GEOS LGPL),
  `scripts/vendor/LICENSE-leaflet.txt`·`LICENSE-pretendard.txt`(OFL). Shewchuk triangle(상업 사용 제한)은 쓰지 않는다.
- 확장 폴더에 아무것도 쓰지 않는다(사이드카 `-B`, 데이터·결과·로그는 `~/Gorani`) — 서명한 파일 목록이 바뀌지 않는다.
- 맥: 확장 관리자·Warehouse로 깐 파일에는 격리(quarantine) 속성이 붙지 않아 번들 파이썬이 Gatekeeper에 막히지 않는다(SketchUp은 LSFileQuarantineEnabled가 없다, 2026-10-21 확인).

## 아직 못 한 것

- Windows 실기 시험(번들 `pythonw.exe` 사이드카·SmartScreen). 이 Mac에서는 mac-arm64만 돌려 봤다.
