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

## 칸(2026-10-22 실제 양식 — 초안 extensions.sketchup.com/extension/be1e8d52-c032-40d5-a891-cc16b8caa8ab/edit)

Upload A New Extension → **Overview**(제목·요약) → **Categories**(3개까지) → **Create**가 초안을 만든다(제출 아님). 초안 화면은 탭 셋이고 위 **Save Draft**·**Submit For Review**(사용자가 누른다).

**Overview**
- Extension Title: `Gorani`(rbz `SketchupExtension` 이름과 같아야 한다)
- Extension Summary(120자): `Pick a site anywhere on the map. The city around it (buildings, roads, terrain, water) comes into SketchUp in 3D. Free.`
- Categories: Architecture · Landscape Architecture · Import & Export

**Extension File 탭**
- Extension File: `build/bsh_gorani-<버전>.rbz`(500 MB까지). Version Number = `constants.PANEL_VERSION`
- Encryption Type: **None**(소스가 공개라 암호화가 필요 없고, 암호화가 로더 경로를 깨뜨릴 위험만 있다)
- SketchUp Compatibility: 2022~2026 · OS: Windows, Mac OS X · Supported Languages: English, Spanish, Japanese, Korean, Simplified Chinese
- Release Notes(1000자):

```
First release on the Extension Warehouse.

- Pick a site on the map and get the city around it in 3D: buildings, terrain, roads, parks, water and railways, each on its own tag.
- Works worldwide with OpenStreetMap and public terrain data.
- Korea: nationwide parcels, zoning and 1:5,000 contours.
- Japan: PLATEAU buildings with measured heights and GSI 5 m terrain.
- Optional 2D: layered Illustrator basemap, analysis maps (SVG, AI) and CSV tables.
- Panel in English, Korean, Spanish, Japanese and Chinese.
```

- Testing instructions(1000자, 심사팀용):

```
1) Open Extensions > Gorani. The panel opens in English (the globe button at the top switches language).
2) Click "Point" at the top left, type "Flatiron Building, New York" (or "Ginza, Tokyo") in the search box and press Enter.
3) Press "Create 3D model" at the bottom right. It takes 30-60 seconds because the data is downloaded on the fly. The context appears as one group "Gorani ..."; one Undo removes it.
4) Optional: "Create 2D material" writes drawings to ~/Gorani/result. It does not touch the model.

Why the package contains executables: SketchUp has no Python, so Gorani bundles CPython 3.12 (python-build-standalone, PSF license) with numpy and shapely (BSD). It runs as a helper process started with -I -B and writes nothing into the extension folder. The panel (HtmlDialog) talks to it only on 127.0.0.1 with a per-session token. Usage statistics are sent only after the user opts in.
```

**Extension Details 탭**
- Screenshots(5장, 940×470 권장, 3 MB 이하): `build/sketchup_store/ew_hero.png` → `ew_steps` → `ew_window` → `ew_world` → `ew_twod` 순. 올리면 순서가 뒤집혀 들어가 끌어서 바로잡았다.
- Promo Video: YouTube 주소만 받는다. 영상 파일 `build/sketchup_store/gorani_sketchup_demo.mp4`(22초, 1920×1080) — 사용자가 YouTube에 올리고 주소를 넣는다.
- Website: `https://969flash.github.io/gorani/en/`
- Keywords(띄어쓰기가 나눔 기호라 한 낱말씩): site, context, urban, design, analysis, city, model, OpenStreetMap, GIS, terrain, buildings, basemap, Korea, Japan, PLATEAU, topography, contours, zoning, masterplan, Illustrator
- Description(Markdown, 5000자):

```markdown
## The city around your site, modeled in SketchUp

Pick a site on the map. The buildings, roads, terrain and parks around it come into your open model in 3D.
It's free.

### How to use
1. Click **Extensions > Gorani** (or the Gorani toolbar button).
2. Pick a site on the map: search a place, then click parcels, draw an area or drop a point.
3. Choose the extent (250 m to 2 km) and press **Create 3D model**.
4. Need drawings? Press **Create 2D material** on the result screen.

### What you get
- **3D context**: building masses, terrain, roads, parks, water and railways. Each layer is a tag in the **CTX** folder.
- **Buildings**: one solid group per building, with height and floors as attributes.
- **2D (optional)**: a layered Illustrator basemap (1:1,000 to 1:5,000), analysis maps as SVG and AI (figure-ground, street hierarchy, building height, elevation, transit and walking catchments, aerial photo) and CSV tables.
- Every run is one Undo step, and a copy is saved as `context.skp` in `~/Gorani/result`.

### Data
- **Worldwide**: OpenStreetMap buildings, roads and water with public terrain data. Heights come from OpenStreetMap tags.
- **Japan**: PLATEAU buildings (MLIT 3D city models) with measured heights, and GSI 5 m terrain.
- **Korea**: nationwide parcels, zoning, buildings and 1:5,000 contours. Pick sites parcel by parcel. Each district is downloaded once.

### Good to know
- SketchUp 2022 or later, Windows and macOS. Nothing else to install.
- The panel speaks English, Korean, Spanish, Japanese and Chinese. Switch it with the globe button.
- Gorani brings its own Python engine. It runs as a helper process, and the panel talks to it only on your computer (127.0.0.1).
- Data is downloaded when you generate, so you need an internet connection.
- Usage statistics are sent only if you opt in.
- Sources: © OpenStreetMap contributors (ODbL), PLATEAU (MLIT, CC BY 4.0), GSI tiles, Korean public data (MOLIT, NGII, Seoul).
- Results with Korean contours or elevations must not be posted online (NGII security rules).

Website: https://969flash.github.io/gorani/en/
Support: https://github.com/969flash/gorani/issues

---

### 한국어
지도에서 대상지를 고르면 주변 건물·도로·지형·녹지가 SketchUp에 3D로 들어옵니다. 무료입니다.
- **사용 방법**: 확장 > Gorani를 누르고, 지도에서 필지·구역·위치로 대상지를 고른 뒤 [3D 모델 만들기]를 누릅니다.
- **결과물**: 레이어마다 CTX 태그로 정리된 3D가 들어오고, 건물은 동마다 솔리드 그룹(높이·층수)입니다. 필요하면 일러스트레이터 베이스맵, 현황도·분석도, 조서 CSV도 만듭니다.
- **데이터**: 국내는 전국 필지·용도지역·1:5,000 등고선, 일본은 PLATEAU 실측 높이와 국토지리원(GSI) 5 m 지형, 그 밖은 OpenStreetMap을 씁니다.
- **언어**: 패널은 영어·한국어·스페인어·일본어·중국어를 지원합니다.

### 日本語
地図で敷地を選ぶと、周辺の建物・道路・地形・緑地がSketchUpに3Dで入ります。無料です。
- **使い方**: 拡張機能 > Gorani を開き、地図で敷地を選んで（エリアを描く・地点を置く）［3Dモデル作成］を押します。
- **日本のデータ**: PLATEAUの建物（実測高さ）と国土地理院の5 m標高。その他の地域はOpenStreetMapです。
- **2D（任意）**: Illustratorのベースマップ、分析図（SVG・AI）、CSV表を作成します。
- **言語**: パネルは英語・韓国語・スペイン語・日本語・中国語に対応しています。
```

**Pricing & Support 탭**: Customer Support = `bsh969flash@gmail.com`. 개발자(Developer) 계정은 무료 확장만 올린다.

## 이미지·영상

3D 그림은 해외(OpenStreetMap·PLATEAU) 대상지만 쓴다 — 수치지형도에서 나온 국내 3D·도면·등고선은 해외 사이트에 올리지 않는다(공간정보관리법 제16조). 한국은 필지 고르기 패널 화면만.

1. SketchUp에서 뉴욕 플랫아이언(구역, 원 250 m)·도쿄 긴자(위치, 원 250 m — PLATEAU)를 만들고, 흰 매스·그림자 보기로 `view.write_image(transparent: true)` →
   `build/sketchup_store/render_nyc.png`·`render_tokyo.png`(2400×1500).
2. 영어 패널 화면(`screencapture -l`): `panel_map_en.png`(뉴욕 구역)·`panel_result_en.png`(긴자 3D·2D 완료)·`panel_lots_en.png`(서울 필지), 실제 SketchUp 창 `window.png`.
3. 2D 카드 그림은 뉴욕 결과의 `2D/sheets/*.svg`를 `build/sketchup_store/sheets/s<번호>.svg`로 복사한다.
4. 카드 5장(1880×940): `docs/sketchup_store/cards.html` 머리 주석의 Chrome 명령 → `ew_hero|steps|window|world|twod.png`.
5. 영상: 긴자 모델을 `write_image`로 72장 돌려 찍고(남쪽 위 30°, 방위 10°→130°) 카드와 함께 ffmpeg로 묶는다(30 fps, 장면 사이 0.5초 겹침) → `gorani_sketchup_demo.mp4`.
6. 아이콘: `docs/blender_store/icon.html`을 Chrome으로 256(그대로)·512(`--force-device-scale-factor=2`).

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
