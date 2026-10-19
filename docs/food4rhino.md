# food4rhino 올리기

Rhino판을 yak에 올린 뒤 food4rhino(https://www.food4rhino.com)에 앱 페이지를 만든다. 설치는 PackageManager로 하고, food4rhino에는 소개와 링크만 둔다.
올리는 일은 사용자 계정(McNeel 계정 로그인)으로 한다. 아래 칸 이름은 2026-10 기준 기억에 의존한다 — 실제 폼과 다르면 고친다(확인 필요).

## 올리기 전에

- Windows Rhino 8에서 한 번 돌려 본다. 아래 설명은 Windows·Mac 둘 다라고 적는다.
- Rhino 뷰포트 스크린샷 1~2장을 직접 찍는다. **해외(Global, OpenStreetMap) 대상지로** 찍는다 — 수치지형도에서 나온 국내 3D·도면·등고선 이미지는 해외 사이트에 올리지 않는다(공간정보관리법 제16조, 웹사이트와 같은 규칙).
- 이미지는 `build/food4rhino/`(2026-10-19 만듦, gitignore — 지워졌으면 아래 원본에서 다시 만든다)
  - `icon_256.png` — 앱 아이콘(`docs/brand/png/gorani_256.png`)
  - `banner_1200x630.png` — 웹사이트 공유 이미지(영문, `../gorani/og.html`)
  - `panel_map.png`·`panel_3d.png`·`panel_2d.png` — 패널 목 화면(`scripts/site_ui.html?mock=1&step=1|3d|2d&w=360`, Chrome 헤드리스 2배)
  - 뷰포트 스크린샷(직접)

## 칸

**Name**: Gorani

**Short description**:
The city around your site, modeled in Rhino. Free 3D context of buildings, roads, terrain and water anywhere OpenStreetMap has data, plus parcels, zoning and contours in Korea.

**Description**:

Gorani builds a 3D context model of the area around your site in your open Rhino document.

How to use
1. Open the Package Manager, search for Gorani, install it and restart Rhino.
2. Type Gorani. A panel with a map opens next to the viewport.
3. Click parcels, draw an area or drop a point, choose the extent (a 500 m to 2 km square, or a radius) and press the 3D button.

What you get
- Building masses, roads, a terrain mesh, rivers, parks and railways, each on its own layer. Building heights come from floor counts in Korea and from OpenStreetMap tags elsewhere.
- Optional 2D output from the same panel: a layered Illustrator basemap at 1:1,000 to 1:5,000, urban analysis maps as SVG and AI (figure-ground, land use, zoning, street hierarchy and more), a DWG, and parcel and building tables as CSV.

Coverage
- Worldwide: OpenStreetMap buildings and roads with public terrain tiles. Generating needs an internet connection.
- Korea: nationwide cadastral parcels, zoning, buildings and 1:5,000 contours. The panel downloads the data for each district once.

Good to know
- Rhino 8 for Windows and Mac. You don't need Grasshopper, an account or an API key.
- The panel is in Korean for now. The website has a short glossary of the words you need.
- Gorani sends anonymous usage statistics to Google Analytics: a random ID per install, versions and OS, where you generated, the extent, run time and error types. No names, file paths or drawing contents.
- Results that contain Korean contours or elevations must not be posted online (National Geographic Information Institute security rules).

**Website**: https://969flash.github.io/gorani/ (English: https://969flash.github.io/gorani/en/)

**Support**: https://github.com/969flash/gorani/issues

**Price / Licence**: Free

**Rhino version / OS**: Rhino 8 / Windows, Mac

**Category**(있는 것 중에서): Architecture, Urban Design / Planning, GIS / Mapping, Landscape

**Tags**: site context, urban design, city model, OpenStreetMap, GIS, terrain, topography, contours, basemap, site analysis, Korea

**Release**: Rhino Package Manager 패키지 `Gorani`로 연결(파일을 따로 올리지 않는다). 새 판은 yak에만 올리면 된다.
