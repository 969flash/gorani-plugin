<!-- extensions.blender.org 'Description' 칸에 아래 줄부터 그대로 붙인다(마크다운). 이름·한 줄 소개·라이선스·권한·태그는 zip의 blender_manifest.toml에서 채워진다.
     문구 원칙: 두괄식, 한 줄에 한 가지, 한국어는 합니다체(번역투 금지) — docs/food4rhino.md와 같다. 2026-10-21 패널 2화면(지도 → 결과) 기준. -->
The city around your site, modeled in Blender.
Pick a site on a map and the buildings, roads, terrain, water and parks around it come into your scene in 3D. It's free.

## How to use

1. In the 3D Viewport, press `N` to open the sidebar, go to the **Gorani** tab and click **Open Panel** (also in *File > Import > Gorani Site Context*).
2. The panel opens in your web browser. Blender has no built-in web view, so the add-on serves the panel from your own computer (`127.0.0.1`).
3. Pick a site on the map: drop a point or draw an area (in South Korea you can also click parcels).
4. Choose the extent and press **3D 모델 만들기** (Make 3D model). The model appears in the `CTX` collection.
5. Optional: on the results screen, press **2D 자료 만들기** (Make 2D) for drawings and tables.

## What you get

- **3D**: collections `CTX::Buildings`, `CTX::Terrain`, `CTX::Roads`, `CTX::Water`, `CTX::Green`, `CTX::Rail`, `CTX::Site`, `CTX::Parcels`. Buildings are one mesh with the face attributes `height`, `floors` and `building_id`, so you can color them with Geometry Nodes or attribute shading. A copy is saved as `context.blend`.
- **2D**: a layered Illustrator basemap (`basemap_<scale>.ai`) and analysis diagrams as SVG and AI: figure-ground, street hierarchy, transit catchment, walking distance, green and blue, community facilities, building height, elevation, slope and axonometric massing. South Korea adds zoning, land use, parcels, building use and age, and land price.
- **Tables**: CSV for buildings, parcels and diagram statistics.

Everything is saved in `~/Gorani/result/<site>_<date>/`.

## Data

- **Anywhere**: buildings, roads, water and parks from OpenStreetMap (© OpenStreetMap contributors, ODbL) and terrain from public elevation tiles. They are downloaded when you generate.
- **South Korea**: parcels, zoning, buildings and 1:5,000 contours from Korean public data. Each district is downloaded once (tens of MB) to `~/Gorani/data/`. Buildings and contours come from our server in Korea, which counts a daily download limit per install with a random install ID.
- Results with Korean contours or elevations must not be posted online (National Geographic Information Institute security rules).

## Permissions

- **Internet**: map tiles, regional data packs and OpenStreetMap. The panel opens only when *Allow Online Access* is on (*Preferences > System > Network*).
- **Files**: results and data packs are written to the `~/Gorani` folder. The Rhino version of Gorani uses the same folder.
- **No usage statistics**: the add-on sends nothing about you or your work. Network requests only fetch map tiles and data.

## Requirements

Blender 4.2 or later on Windows, macOS or Linux, and an internet connection. No Python packages to install.
The panel is in English, Korean, Spanish, Japanese and Chinese (pick it in the panel header). The Blender buttons follow Blender's interface language.

---

**한국어**

지도에서 대상지를 고르면 주변 건물·도로·지형·하천이 Blender 장면에 3D로 들어옵니다.
대지 주변 현황 모델을 직접 그릴 필요가 없습니다. 무료입니다.

사용 방법
1. 3D 뷰에서 N을 눌러 사이드바를 열고, Gorani 탭의 [패널 열기]를 누릅니다.
2. 기본 브라우저에 패널이 열립니다.
3. 지도에서 대상지를 고르고 [3D 모델 만들기]를 누릅니다.
4. 2D 자료가 필요하면 결과 화면에서 [2D 자료 만들기]를 누릅니다.

결과물
- 3D: 건물 매스, 도로, 지형, 하천, 녹지, 철도 (컬렉션별)
- 2D: 일러스트레이터 베이스맵, 현황도·분석도, 조서 CSV

데이터
- 국내: 필지, 용도지역, 건물, 1:5,000 등고선. 시군구마다 한 번 받습니다.
- 해외: OpenStreetMap 건물·도로와 공개 지형 데이터를 씁니다.
- 국내 등고선·표고가 든 결과물은 인터넷에 올리면 안 됩니다(국토지리정보원 보안 규정).

참고
- 결과와 데이터는 `~/Gorani` 폴더에 저장합니다. 라이노판과 같은 폴더를 씁니다.
- 사용 통계는 보내지 않습니다.
- 패널 언어는 위쪽 언어 단추에서 한국어로 바꿀 수 있습니다.
