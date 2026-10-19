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

**Short description**(영어 다음 줄에 한국어):
The city around your site, modeled in Rhino. Free 3D context of buildings, roads, terrain and water anywhere OpenStreetMap has data, plus parcels, zoning and contours in Korea.
대상지 주변 도시를 Rhino에 3D로 만들어 주는 무료 플러그인. 해외는 OpenStreetMap, 국내는 지적 필지·용도지역·등고선까지.

**Description**(영어 다음에 한국어를 이어 쓴다):

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

한국어

Gorani는 대상지 주변의 3D 컨텍스트 모델을 지금 열린 Rhino 문서에 만들어 줍니다.

쓰는 법
1. 패키지 매니저(PackageManager)에서 Gorani를 검색해 설치하고 Rhino를 다시 켭니다.
2. 명령창에 Gorani를 입력하면 지도가 있는 패널이 뷰포트 옆에 열립니다.
3. 필지를 클릭하거나 구역을 그리거나 위치를 찍고, 범위(한 변 500 m~2 km 사각형 또는 반경)를 고른 뒤 [3D 모델 만들기]를 누릅니다.

만들어지는 것
- 건물 매스·도로·지형 메시·하천·공원·철도가 레이어별로 들어옵니다. 건물 높이는 국내는 층수, 해외는 OpenStreetMap 태그로 정합니다.
- 같은 패널에서 2D도 만들 수 있습니다. 레이어가 나뉜 일러스트레이터 베이스맵(1:1,000~1:5,000), 도시설계 현황·분석도(SVG·AI, 도형-배경도·토지이용·용도지역·가로 위계 등), DWG, 필지·건물 조서 CSV입니다.

지원 범위
- 해외: OpenStreetMap 건물·도로와 공개 지형 타일. 생성할 때 인터넷이 필요합니다.
- 국내: 전국 지적 필지·용도지역·건물·1:5,000 등고선. 지역(시군구) 데이터는 패널에서 처음 한 번 받습니다.

알아 둘 것
- Rhino 8(Windows·Mac). 그래스호퍼·회원가입·API 키가 필요 없습니다.
- 사용 통계를 Google Analytics로 보냅니다. 설치마다 만든 무작위 ID, 버전·OS, 생성한 위치·범위·걸린 시간·오류 종류입니다. 이름·파일 경로·도면 내용은 보내지 않습니다.
- 국내 등고선·표고가 든 결과물은 인터넷에 올리지 마세요(국토지리정보원 보안관리규정).

**Website**: https://969flash.github.io/gorani/en/ (한국어: https://969flash.github.io/gorani/)

**Support**: https://github.com/969flash/gorani/issues

**Price / Licence**: Free

**Rhino version / OS**: Rhino 8 / Windows, Mac

**Category**(있는 것 중에서): Architecture, Urban Design / Planning, GIS / Mapping, Landscape

**Tags**: site context, urban design, city model, OpenStreetMap, GIS, terrain, topography, contours, basemap, site analysis, Korea, 도시설계, 대지분석, 현황도

**Release**: Rhino Package Manager 패키지 `Gorani`로 연결(파일을 따로 올리지 않는다). 새 판은 yak에만 올리면 된다.
