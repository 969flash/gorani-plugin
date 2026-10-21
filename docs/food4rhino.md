# food4rhino 올리기

Rhino판을 yak에 올린 뒤 food4rhino 앱 페이지(https://www.food4rhino.com/en/app/gorani, 편집 node/5903)를 고친다. 설치는 PackageManager로 하고, food4rhino에는 소개·이미지·설치용 zip을 둔다.
올리는 일은 사용자 계정(McNeel 계정 로그인)으로 한다. 저장은 [Submit] — McNeel 검토 뒤 게시된다.
문구 원칙(2026-10-19 사용자): 두괄식, 쉬운 문장, 한 줄에 한 가지. 번역투를 피한다. 일본어도 같은 원칙(です・ます체).

## 폼 (2026-10-21 실제)

- 영어만 받는다고 적혀 있다. 그래도 본문은 영어 → 한국어 → 日本語 순서로 셋 다 쓴다(2026-10-21 사용자: 한국어가 둘째 언어로 꼭 있어야 한다). 검토에서 문제 되면 다시 정한다.
- Short Description 180자, Category 최대 5, License = Closed Source > Proprietary.
- Images: 한 장 5 MB 이하, png·jpg·gif, 최대 10장. 첫 장이 대표 이미지.
- Files: 필수. Link는 다운로드 파일 주소만 받는다(웹페이지 거절, `.yak`은 허용 형식 아님) → yak 파일과 README를 `Gorani-<버전>-rh8.zip`으로 묶어 File로 올린다. **새 판을 yak에 올리면 이 zip도 바꾼다.**
- Downloads 표에는 yak 패키지 줄이 저절로 붙는다([Install] 단추, 설명은 `dev_deploy.YAK_MANIFEST` 그대로) — 그 설명도 이 문서와 같은 문안으로 맞춰야 한다(2026-10-21 아직 옛 문안 '한 번에 쉽게 하는 사이트 모델링…').
- 갤러리 상자 높이는 가장 키 큰 이미지에 맞춰진다 → 세로 GIF를 넣으면 대표 이미지가 위아래로 비어 보인다. 이미지는 전부 16:9로 맞춘다(GIF도 960×540, 왼쪽 설명 + 오른쪽 영상 — `cards/cap_a|b.html` 배경에 ffmpeg overlay, gifski).
- Rhino를 켤 때 패키지 자동 업데이트가 켜져 있으면 최신 yak이 깔린다(2026-10-21 0.2.1 → 0.2.2).

## 이미지 (`build/food4rhino/`, gitignore)

- 첫 장(대표)은 **글 카드가 아니라 강한 그림 한 장**이다. 상위 앱(Enscape·Urbano·Ladybug)은 모두 그림으로 시작하고, 갤러리 상자가 16:9 약 465 px라 작은 글씨는 읽히지 않는다(2026-10-21 사용자: 첫 카드가 '너무 별로'). → `01_hero.png` 1920×1080 = `cards/hero.html?lang=en|ko|ja`: 어두운 배경 + 원형 대지 렌더 + 대상지 건물(플랫아이언) 파란색 + 큰 제목 한 줄. 렌더는 Rendered·배경 단색(BackgroundStyle.SolidColor — 그라데이션은 띠가 생긴다)·커브 숨김·원 밖 건물 숨김.
- `en|ko|ja/02_steps … 05_world.png`(1600×1000) — `cards/cards.html?card=steps|rhino|twod|world&lang=en|ko|ja`를 Chrome 헤드리스로 찍는다:
  `"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless=new --hide-scrollbars --window-size=1600,1000 --virtual-time-budget=3000 --screenshot=out.png "file://$PWD/cards.html?card=hero&lang=en"`
- `render/` — 카드에 쓴 Rhino 캡처 원본. 설치본 엔진으로 해외 대상지를 생성하고(뉴욕 Madison Square 반경 350 m 490동, 도쿄 긴자 250 m 509동), Perspective를 Rendered + 레이어 재질색으로 `RhinoView.CaptureToBitmap(size, mode)`(ViewCapture는 Mac에서 와이어프레임만 나왔다).
- `demo_3d.gif`·`demo_2d.gif` — 사용자 시연 영상(`~/Downloads/고라니실행영상.mp4`)을 8 fps·432 px로 둘로 나눔(5 MB 제한). 국내(성수동) 3D·현황도가 보이지만 사용자가 올리기로 정했다(2026-10-21) — 대표 이미지 다음 2·3번째에 둔다.
- 해외 사이트에는 **해외(OpenStreetMap) 대상지 이미지만** 올린다 — 수치지형도에서 나온 국내 3D·도면·등고선 이미지는 올리지 않는다(공간정보관리법 제16조, 웹사이트와 같은 규칙).
- Overpass가 붐비면 도심 400 m 이상은 시간 초과가 난다(2026-10-21 신주쿠 400 m 실패, 250 m 성공). 2D까지 켜면 조회 범위가 용지 프레임(A3 1:3000 ≈ 1.3 km)으로 커진다.

## Short description (180자 이하)

Free Rhino 8 plugin that models the city around your site. Pick a site on the map and get buildings, roads, terrain and parks as 3D layers. Works worldwide.

## Description — English

Gorani is a free Rhino 8 plugin that models the city around your site.
Pick a site on the map and press one button. The surrounding buildings, roads, terrain, water and green space come into your open Rhino document as clean 3D layers. It works worldwide with OpenStreetMap, and in Korea with nationwide parcel, zoning and contour data.

How it works
1. In Rhino 8, type PackageManager, search for Gorani and install it. Restart Rhino.
2. Type Gorani. A panel with a map opens.
3. Pick your site: click parcels, draw an area or drop a point. You can also search by address.
4. Set the extent (100 m to 2 km) and press 3D. A 500 m site usually takes under a minute.

What you get in Rhino
- Building masses with heights (OpenStreetMap height and level tags; floor counts in Korea)
- Roads (surfaces in Korea, centerlines elsewhere), a terrain mesh, rivers and water, parks and green space, railways
- Each on its own layer (CTX::Buildings, CTX::Roads, CTX::Terrain …), at the origin or at real-world coordinates
- Height, floors and use stored as User Text on each building
- A copy saved as context.3dm in the result folder

Optional 2D
- A layered Illustrator basemap (A3 or A1, 1:1,000 to 1:5,000)
- Analysis maps as SVG and AI: figure-ground, street hierarchy, walking distance, transit catchment, green and blue, building height, elevation, slope and 3D massing
- In Korea, also land use, zoning, parcel grain, building age, land price and more
- Parcel and building tables as CSV
- Every sheet prints its data sources and dates

Data
- Worldwide: OpenStreetMap buildings and roads, public elevation tiles. Needs an internet connection while generating.
- Korea: nationwide parcels, zoning, buildings and 1:5,000 contours. Each district is downloaded once (tens of MB).
- Outside Korea, building heights depend on OpenStreetMap tags. Buildings without tags get a default height.

Good to know
- Rhino 8 for Windows and Mac. No Grasshopper, no account, no API key.
- The panel is in Korean for now. A Japanese version is coming soon. The website has a short glossary.
- Using Claude or ChatGPT with Rhino MCP? Ask it to install Gorani instead of drawing the buildings one by one.
- Anonymous usage statistics go to Google Analytics: a random ID per install, versions and OS, where you generated, the extent, run time and error types. No names, file paths or drawing contents.
- Results with Korean contours or elevations must not be posted online (National Geographic Information Institute security rules).
- Data © OpenStreetMap contributors (ODbL). Korean public data from MOLIT, NGII and Seoul Metropolitan Government. Not affiliated with McNeel.

## Description — 한국어 (영어 다음, 일본어 앞)

Gorani는 대지 주변 현황 모델을 자동으로 만들어 주는 무료 Rhino 8 플러그인입니다.
지도에서 대상지를 고르고 버튼 하나를 누르면, 주변 건물·도로·지형·하천·녹지가 지금 열려 있는 문서에 레이어별 3D로 들어옵니다. 국내는 전국 필지·용도지역·등고선 데이터로, 해외는 OpenStreetMap으로 만듭니다.

사용 방법
1. 라이노 8 명령창에 PackageManager를 입력하고 Gorani를 검색해 설치합니다. 라이노를 다시 켭니다.
2. 명령창에 Gorani를 입력하면 지도 패널이 열립니다.
3. 대상지를 고릅니다. 필지 클릭, 구역 그리기, 위치 찍기 중 하나이고, 주소·지번으로도 찾습니다.
4. 범위(100 m~2 km)를 정하고 [3D 모델 만들기]를 누릅니다. 500 m 범위면 대개 1분 안에 끝납니다.

Rhino에 들어오는 것
- 높이가 있는 건물 매스(국내는 층수, 해외는 OpenStreetMap 높이·층수 태그)
- 도로(국내는 도로면, 해외는 중심선), 지형 메시, 하천·수면, 공원·녹지, 철도
- 요소마다 다른 레이어(CTX::Buildings, CTX::Roads, CTX::Terrain …). 원점 기준과 실제 좌표 중에서 고릅니다
- 건물·필지 속성(PNU·층수·용도)을 User Text로 기록
- 결과 폴더에 context.3dm 사본 저장

2D(필요할 때만)
- 레이어로 나뉜 일러스트레이터 베이스맵(A3·A1, 1:1,000~1:5,000)
- SVG·AI 현황도·분석도: 도형-배경도, 가로 위계, 보행권, 대중교통 역세권, 녹지·수계, 건축물 층수, 표고, 경사, 입체 매스도
- 국내는 토지이용현황, 용도지역, 필지 규모, 건축물 노후도, 공시지가 등까지
- 필지·건물 조서(CSV)
- 도면마다 데이터 출처와 기준일 표기

데이터
- 국내: 전국 필지 경계·용도지역·건물·1:5,000 등고선. 지역 데이터는 처음 한 번 받습니다(구 하나에 수십 MB).
- 해외: OpenStreetMap 건물·도로와 공개 표고 타일. 만들 때 인터넷이 필요합니다.
- 해외 건물 높이는 OpenStreetMap 태그를 따르고, 태그가 없으면 기본 높이로 둡니다.

참고
- 라이노 8(윈도우·맥)에서 씁니다. 그래스호퍼, 회원가입, API 키는 필요 없습니다.
- Rhino MCP로 Claude나 ChatGPT를 쓰고 있다면, 건물을 하나씩 그리게 하지 말고 Gorani를 설치하게 하세요.
- 사용 통계를 Google Analytics로 보냅니다. 설치별 무작위 ID, 버전·OS, 만든 위치·범위·걸린 시간·오류 종류이고, 이름·파일 경로·도면 내용은 보내지 않습니다.
- 등고선·표고가 들어간 국내 결과물은 인터넷에 올리면 안 됩니다(국토지리정보원 보안관리규정).

## Description — 日本語

Goraniは、敷地まわりの街を3Dでつくる無料のRhino 8プラグインです。
地図で敷地を選んでボタンを押すと、周辺の建物・道路・地形・水系・緑地が、開いているRhinoのドキュメントにレイヤー分けされた3Dで入ります。世界中どこでもOpenStreetMapで、韓国では全国の筆地・用途地域・等高線データでつくります。

使い方
1. Rhino 8でPackageManagerと入力し、Goraniを検索してインストールします。Rhinoを再起動します。
2. Goraniと入力すると、地図付きのパネルが開きます。
3. 敷地を選びます。区画をクリック、範囲を描く、地点を打つのいずれかです。住所でも検索できます。
4. 範囲（100 m〜2 km）を決めて3Dを押します。500 m程度ならたいてい1分以内です。

Rhinoに入るもの
- 高さ付きの建物ボリューム（OpenStreetMapの高さ・階数タグ、韓国は階数）
- 道路（韓国は道路面、それ以外は中心線）、地形メッシュ、河川・水面、公園・緑地、鉄道
- 要素ごとに別レイヤー（CTX::Buildings、CTX::Roads、CTX::Terrain など）。原点基準か実座標かを選べます
- 建物ごとに高さ・階数・用途をUser Textで記録
- 結果フォルダにcontext.3dmのコピーを保存

2D（必要なときだけ）
- レイヤー分けしたIllustratorのベースマップ（A3・A1、1:1,000〜1:5,000）
- SVG・AIの分析図：図と地、街路の階層、徒歩圏、駅勢圏、緑地・水系、建物の階数、標高、勾配、3Dボリューム
- 韓国では土地利用・用途地域・筆地規模・建物の老朽度・公示地価なども
- 筆地・建物の一覧表（CSV）
- 図面ごとに出典と基準日を記載

データ
- 世界：OpenStreetMapの建物・道路と公開の標高タイル。生成時にインターネット接続が必要です。
- 韓国：全国の筆地・用途地域・建物・1:5,000等高線。地域ごとに最初に一度だけダウンロードします（区ひとつで数十MB）。
- 韓国以外の建物の高さはOpenStreetMapのタグによります。タグがない建物は既定の高さになります。

ご注意
- Rhino 8（Windows・Mac）で動きます。Grasshopper、アカウント、APIキーは不要です。
- パネルは現在韓国語です。日本語版をまもなく公開します。
- 匿名の利用統計をGoogle Analyticsに送ります。インストールごとのランダムID、バージョン・OS、生成した場所・範囲・所要時間・エラーの種類です。名前・ファイルパス・図面の内容は送りません。
- データ © OpenStreetMap contributors（ODbL）。McNeelとは関係のない個人プロジェクトです。

## 나머지 칸

- Category: Urban Planning & City Modeling, Architecture, Landscape, Environmental Design, Import & Export
- Support Forum: https://github.com/969flash/gorani/issues · Web: https://969flash.github.io/gorani/en/
- Files: `Gorani-0.2.2-rh8.zip`, Rhino 8 Windows·Mac
