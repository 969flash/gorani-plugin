# Autodesk 스토어(Design and Make Marketplace) 올리기 — AutoCAD판

올리는 일은 사용자 계정(Autodesk ID bsh969flash@gmail.com)으로 한다. 게시자 등록은 2026-10-23에 했다(Publisher Corner, apps.autodesk.com/en/MyUploads).
무료 앱은 비용·결제 정보가 없고, 디벨로퍼 허브(APS)는 필요 없다(Forma·BIM 360 연동 앱만).

## 순서

1. 빌드 — `python3 scripts/dev_deploy.py autocad` → `build/Gorani-autocad-win-<버전>.zip`(약 32 MB), `build/Gorani-autocad-mac-<버전>.zip`(약 63 MB).
   스토어에는 Windows판을 먼저 낸다(Windows 필수, 맥은 선택 — 맥 AutoCAD에는 리본이 없어 CUIX 의무가 어떻게 적용되는지 확인 필요).
2. Windows 노트북에서 써 본다 — zip을 풀어 `Gorani.bundle`을 `C:\Program Files\Autodesk\ApplicationPlugins`에 두고 AutoCAD를 다시 켠다.
   리본 플러그인 탭 > Gorani 버튼 → 패널(Edge 앱 창) → [CAD 도면 만들기] → 지금 도면에 블록이 들어오는지.
3. 개인정보 처리방침 페이지를 웹사이트에 올린다(아래 초안, 사용자 허락 뒤) — 앱 설명과 앱 안(help.html) 양쪽에 링크가 필요하다.
4. 제출 전에 appsubmissions@autodesk.com에 미리 묻는다(아래 메일 초안) — 번들 파이썬 실행 파일·127.0.0.1 로컬 서버 허용 여부가 공식 문서에 없다.
5. Publisher Corner > Publish a New Product → 게시자 약관 동의(사용자가 누른다) → 아래 '칸' → Preview → Submit.
6. 24~48시간 안에 심사자가 연락하고, 승인까지 최대 2주. 설명만 고치면 바로 반영, 파일·호환 제품을 바꾸면 다시 심사.

새 판: `constants.PANEL_VERSION`을 올린다(ProductCode는 버전마다 dev_deploy가 새로 만든다, UpgradeCode는 고정) → 1번 → Manage > Edit에서 파일 Remove → 새 zip.

## 게시자(2026-10-23 등록)

- Publisher Information: Sanghoon Byun, bsh969flash@gmail.com, Company URL https://969flash.github.io/gorani/en/, Support Contact bsh969flash@gmail.com
- My Page: Company name `Gorani`, Company information(사용자가 붙여 넣기로 함):
  `Gorani is a free tool made by an individual developer, Sanghoon Byun. It builds the site context for architecture and urban design projects: surrounding buildings, roads, terrain and water as 3D models or 2D CAD drawings, plus base maps and analysis diagrams. Free to use. Contact: bsh969flash@gmail.com`

## 칸

- App type: Desktop · OS: Win64 · Language: English(설명), 앱은 영어·한국어·스페인어·일본어·중국어
- Title: `Gorani — Site Context Drawing`
- App file: `build/Gorani-autocad-win-<버전>.zip`(단일 zip, 600 MB까지)
- Icon: `docs/brand/png/gorani_badge_120.png`(120×120)
- Price: Free
- Compatible products: AutoCAD 2027(필수), 2025·2026 — 시험한 판만 체크한다(2021~2024는 SeriesMin으로 열려 있지만 시험 전). 버티컬(Architecture 등)은 체크하지 않는다.
- Categories: Architecture · Civil Engineering · Data Import/Export(실제 목록에서 고른다)
- Description(4000자):

```
Gorani draws the existing conditions around your site straight into your AutoCAD drawing.

Pick parcels on the map (or draw an area, or drop a point) and click Create CAD drawing. A few seconds later the site plan base is in your current drawing at 0,0 as one block:
- Parcel lines and lot numbers (your site and its neighbors)
- Building outlines with above-ground floor counts
- Road edges, center lines, road names and measured road widths
- Contours with elevations and spot heights
- Zoning and urban planning boundaries
- Your site boundary in red, everything else in gray, each on its own US-* layer

Drawing units mm or m, text sized for 1:100 to 1:1200, origin at the site or real-world coordinates (EPSG:5186 in Korea).
Optional extras: analysis diagrams (SVG, AI) and parcel and building tables (CSV).

Data: South Korea uses national public data (cadastral map, building register, 1:5,000 digital topographic map, urban planning data); each area's data pack downloads the first time you use it. Parcel lines are not survey results. Confirm legal boundaries and road widths with a survey before design.

Free. No account. No usage statistics. Privacy policy: <개인정보 처리방침 URL>
```

- General Usage Instructions(필수 — 자동으로 HTML 도움말이 된다):

```
1. Open the Plug-ins tab and click Gorani (or type GORANI). A small Gorani window opens.
2. Search an address or click parcels on the map. Set the drawing unit and scale under Drawing settings.
3. Click Create CAD drawing. The drawing is inserted into the current drawing at 0,0 as a block and the view zooms to it.
4. EXPLODE the block to edit lines on their own US-* layers. The DXF also stays in the Gorani/result folder in your user folder.
```

- Installation/Uninstallation: `standard text`
- Support Information(1000자): `Email bsh969flash@gmail.com. Website https://969flash.github.io/gorani/en/`
- Known Issues: `Mac: type GORANI again after creating to insert the drawing (AutoCAD for Mac cannot be driven from outside).`
- 스크린샷(10장까지, 2 MB 이하, 장마다 설명): ① 플러그인 탭 Gorani 버튼 ② 패널에서 필지 고르기 ③ 지금 도면에 들어온 결과 ④ 확대(지번·층수·도로폭) ⑤ 경사지 등고선 ⑥ 레이어 목록(US-*)

## 심사 전 문의 메일 초안(appsubmissions@autodesk.com)

```
Subject: Pre-submission question: AutoCAD app with a bundled Python helper

Hello,
I am preparing a free AutoCAD app (Gorani) for the Marketplace. Before submitting I would like to confirm two points:

1. AutoCAD has no Python, so the bundle includes CPython 3.12 (python-build-standalone, PSF license). The AutoLISP command starts it as a helper process with STARTAPP. It writes only to the user's Gorani folder, never to the bundle folder.
2. The helper serves its panel only on 127.0.0.1 with a per-session token and opens it in a small Edge app window. When a drawing is ready it inserts the DXF into the active drawing through COM (AutoCAD.Application SendCommand, -INSERT).

The app also downloads public map data packs (Hugging Face and a server in Korea) when the user first uses an area. It sends no usage statistics.

Is this acceptable for the Marketplace? Thank you.
Sanghoon Byun (bsh969flash@gmail.com)
```

## 개인정보 처리방침 초안(웹사이트에 올릴 것 — /privacy/)

```
Gorani privacy policy (AutoCAD, Rhino, SketchUp, Blender)

What Gorani sends
- Data packs: when you use an area for the first time, Gorani downloads that area's data from Hugging Face or from Gorani's server in Korea. The Korean server receives a random installation ID to count a daily download limit. It is not linked to your name.
- Maps: the panel map loads tiles from OpenStreetMap (and Esri or VWorld imagery when you turn on satellite view). Outside Korea, Gorani queries OpenStreetMap services for the area you pick.
- Usage statistics: the AutoCAD and Blender versions send none. The SketchUp version sends anonymous statistics only if you agree. The Rhino version sends anonymous statistics (random installation ID, versions, OS and language, the site you generated, run time and errors) to Google Analytics.
What Gorani does not send: your name, file paths or drawing contents.
Storage: results stay on your computer (Gorani folder in your user folder). Google Analytics data is kept for <보관 기간 — GA 관리 > 데이터 보관 설정값 확인 필요>.
Your choices: SketchUp — More menu > Settings > Usage statistics. To delete statistics linked to your installation ID, email bsh969flash@gmail.com with the ID in ~/.gorani/client_id.
Contact: bsh969flash@gmail.com
```
