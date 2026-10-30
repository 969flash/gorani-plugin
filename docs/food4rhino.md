# food4rhino 올리기

Rhino판을 yak에 올린 뒤 food4rhino(https://www.food4rhino.com)에 앱 페이지를 만든다. 설치는 PackageManager로 하고, food4rhino에는 소개와 링크만 둔다.
올리는 일은 사용자 계정(McNeel 계정 로그인)으로 한다.
문구 원칙(2026-10-19 사용자): 두괄식, 쉬운 문장, 합니다체(해요체 아님), 한 줄에 한 가지로 줄바꿈. 번역투를 피한다. PackageManager 설명(`dev_deploy.YAK_MANIFEST`)도 같은 원칙이다. 아래 칸 이름은 2026-10 기준 기억에 의존한다 — 실제 폼과 다르면 고친다(확인 필요).

## 올리기 전에

- Windows Rhino 8에서 한 번 돌려 본다. 아래 설명은 Windows·Mac 둘 다라고 적는다.
- Rhino 7판(2026-10-30)은 Mac Rhino 7.37만 실측했다. Windows Rhino 7(Edge 창 패널)도 한 번 돌려 본다.
- Rhino 뷰포트 스크린샷 1~2장을 직접 찍는다. **해외(Global, OpenStreetMap) 대상지로** 찍는다 — 수치지형도에서 나온 국내 3D·도면·등고선 이미지는 해외 사이트에 올리지 않는다(공간정보관리법 제16조, 웹사이트와 같은 규칙).
- 스크린샷은 영어 패널로 찍는다(목 화면 `&lang=en`, 심사자가 영어를 본다).
- 이미지는 `build/food4rhino/`(2026-10-19 만듦, gitignore — 지워졌으면 아래 원본에서 다시 만든다)
  - `icon_256.png` — 앱 아이콘(`docs/brand/png/gorani_256.png`)
  - `banner_1200x630.png` — 웹사이트 공유 이미지(영문, `../gorani/og.html`)
  - `panel_map.png`·`panel_3d.png`·`panel_2d.png` — 패널 목 화면(`scripts/site_ui.html?mock=1&step=1|3d|2d&w=360`, Chrome 헤드리스 2배)
  - 뷰포트 스크린샷(직접)

## 칸

**Name**: Gorani

**Short description**(영어 다음 줄에 한국어):

The city around your site, modeled in Rhino. Free 3D buildings, roads and terrain from OpenStreetMap, plus parcels, zoning and contours in Korea.
필지를 고르면 주변 건물·도로·지형이 라이노에 3D로 들어옵니다. 무료입니다.

**Description**(영어 다음에 한국어를 이어 쓴다. 두괄식, 한 줄에 한 가지):

The city around your site, modeled in Rhino.
Pick a site on the map and the buildings, roads and terrain around it come into your open document. It's free.

How to use
1. Type PackageManager, search for Gorani and install it.
2. Restart Rhino and type Gorani.
3. Pick a site on the map: click parcels, draw an area or drop a point.
4. Choose the extent and press the 3D button.

What you get
- 3D: building masses, roads, terrain, rivers, parks and railways on separate layers.
- Heights: floor counts in Korea, OpenStreetMap height tags elsewhere.
- 2D (optional): layered Illustrator basemap (1:1,000 to 1:5,000), urban analysis maps (SVG, AI), DWG (Rhino 8) and CSV tables.

Data
- Worldwide: OpenStreetMap buildings and roads with public terrain data. Needs an internet connection.
- Korea: nationwide parcels, zoning, buildings and 1:5,000 contours. Each district is downloaded once.

Good to know
- Rhino 7 and 8 for Windows and Mac. You don't need Grasshopper, an account or an API key.
- The panel is in English, Korean, Spanish, Japanese and Simplified Chinese. Switch with the globe button at the top.
- Anonymous usage statistics go to Google Analytics: a random ID per install, versions and OS, where you generated, the extent, run time and error types. No names, file paths or drawing contents.
- Results with Korean contours or elevations must not be posted online (National Geographic Information Institute security rules).

한국어

필지를 고르면 주변 건물·도로·지형이 라이노에 3D로 들어옵니다.
대지 주변 현황 모델을 직접 그릴 필요가 없습니다. 무료입니다.

사용 방법
1. 명령창에 PackageManager를 입력하고 Gorani를 검색해 설치합니다.
2. 라이노를 다시 켜고 명령창에 Gorani를 입력합니다.
3. 지도에서 대상지를 고릅니다. 필지 클릭, 구역 그리기, 위치 찍기 중 하나입니다.
4. 범위를 정하고 [3D 모델 만들기]를 누릅니다.

결과물
- 3D: 건물 매스, 도로, 지형, 하천, 녹지, 철도가 레이어별로 들어옵니다.
- 높이: 국내는 층수, 해외는 OpenStreetMap 높이 태그로 정합니다.
- 속성: 건물과 필지에 PNU·층수·용도가 User Text로 붙습니다.
- 2D(필요할 때만): 일러스트레이터 베이스맵(1:1,000~1:5,000), 현황도·분석도(SVG·AI), DWG(라이노 8), 조서 CSV를 만듭니다.

데이터
- 국내: 전국 필지 경계·용도지역·건물·1:5,000 등고선. 지역 데이터는 처음 한 번 받습니다(구 하나에 수십 MB).
- 해외: OpenStreetMap 건물·도로와 공개 지형 데이터. 만들 때 인터넷이 필요합니다.

참고
- 라이노 7·8(윈도우·맥)에서 씁니다. 그래스호퍼, 회원가입, API 키는 필요 없습니다.
- 패널은 영어·한국어·스페인어·일본어·중국어로 쓸 수 있습니다. 위쪽 지구본 버튼에서 바꿉니다.
- 사용 통계를 Google Analytics로 보냅니다. 설치별 무작위 ID, 버전·OS, 만든 위치·범위·걸린 시간·오류 종류이고, 이름·파일 경로·도면 내용은 보내지 않습니다.
- 등고선·표고가 들어간 국내 결과물은 인터넷에 올리면 안 됩니다(국토지리정보원 보안관리규정).

**Website**: https://969flash.github.io/gorani/en/ (한국어: https://969flash.github.io/gorani/)

**Support**: https://github.com/969flash/gorani/issues

**Price / Licence**: Free

**Rhino version / OS**: Rhino 7, Rhino 8 / Windows, Mac (Rhino 7은 2026-10-30 추가 — 앱 페이지의 이 칸은 사용자 계정으로 고친다)

**Category**(있는 것 중에서): Architecture, Urban Design / Planning, GIS / Mapping, Landscape

**Tags**: site context, urban design, city model, OpenStreetMap, GIS, terrain, topography, contours, basemap, site analysis, Korea, 도시설계, 대지분석, 현황도

**Release**: Rhino Package Manager 패키지 `Gorani`로 연결(파일을 따로 올리지 않는다). 새 판은 yak에만 올리면 된다 — Rhino 8판(`rh8_0-any`)과 Rhino 7판(`rh7_0-mac`·`rh7_0-win`)을 같은 버전으로 같이 올린다.

## 심사 반려 대응 (2026-10-21)

McNeel 심사자 메일: "영어가 없는 콘텐츠는 올릴 수 없다. 컴포넌트를 영어로 번역한 새 버전을 올려 달라." → 패널을 다섯 언어로 만들고 기본을 영어로 했다(`docs/panel_ui.md` '언어'). 그다음 할 일(2026-10-21 조사 — food4Rhino FAQ·McNeel 포럼, 공식 '재심사' 버튼은 없다):

1. `constants.PANEL_VERSION`을 올리고 깨끗한 origin/main 워크트리에서 `dev_deploy.py yak`·`dev_deploy.py rhino7` → 세 파일을 `yak push`. food4Rhino 페이지가 패키지에 연결돼 있으면 새 버전이 저절로 보인다(파일을 다시 올리지 않는다).
2. food4Rhino 'My Content'에서 앱을 고친다 — 위 칸 문구(영어 먼저), 스크린샷을 영어 패널로. 필수 칸(Category·License·Support·Icon)이 찼는지 본다.
3. 페이지가 Yak 패키지에 연결됐는지 본다(파일·연결 없는 페이지는 초안으로 남은 사례가 있다). 안 돼 있으면 'Add App from Package Manager'로 다시 만들거나 회신 때 연결을 부탁한다.
4. Publish 버튼이 보이면 누른다(FAQ의 검토 요청 방법).
5. 심사자 메일에 회신한다 — 패키지 이름 Gorani, 새 버전 번호, 영어가 기본이고 헤더 지구본 버튼으로 언어를 바꾼다는 것. 2~3 영업일 답이 없으면 food4rhino@mcneel.com 또는 McNeel 포럼 food4Rhino 카테고리에 묻는다(지원 시간 평일 9~14시 CET).
6. 확인 필요: 검토 중 페이지를 고치면 다시 검토에 들어가는지, 승인 뒤 새 버전도 검토하는지는 공식 설명이 없다.

