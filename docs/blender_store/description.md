<!-- extensions.blender.org 'Description' 칸에 아래 줄부터 그대로 붙인다. 이름·한 줄 소개·라이선스·권한은 zip의 blender_manifest.toml에서 자동으로 채워진다. -->
Gorani builds the site context for an urban design project. Pick a site on a map and it creates the buildings, roads, terrain and water around it as Blender objects. It also writes an Illustrator basemap, a set of analysis drawings and CSV tables.

## How to use

1. Open the sidebar in the 3D Viewport (`N`), select the **Gorani** tab and click **패널 열기** (Open Panel).
2. The panel opens in your web browser. Blender has no embedded web view, so the add-on serves the panel from your own computer (`127.0.0.1`).
3. Pick a site on the map: click parcels, draw an area, or drop a point. Choose the radius and click **생성 시작** (Generate).
4. The context appears in the scene under the `CTX` collection. The browser shows the progress and the output files.

## What you get

- **3D context** in collections `CTX::Buildings`, `CTX::Terrain`, `CTX::Roads`, `CTX::Water`, `CTX::Green`, `CTX::Rail`, `CTX::Site` and `CTX::Parcels`. Buildings are one mesh with the face attributes `height`, `floors` and `building_id`, so you can colour them with Geometry Nodes. A copy is saved as `context.blend`.
- **Illustrator basemap** (`basemap_<scale>.ai`) with drawing-style layers.
- **Analysis sheets**: 25 SVG drawings, including figure-ground, street hierarchy, land use, zoning, building height, building age, elevation, slope and axonometric massing.
- **CSV tables** for parcels, buildings and sheet statistics.

Everything is written to `~/Gorani/result/<date>/<site>/`.

## Data

- **South Korea**: parcels, land-use plans, buildings, roads and contours are downloaded per district (tens of MB each) the first time you work there. They come from Korean public data published by MOLIT, NGII and Seoul. They are stored in `~/Gorani/data/` and reused offline.
- **Other countries**: buildings, roads and water come from OpenStreetMap (© OpenStreetMap contributors, ODbL). Terrain comes from public elevation tiles. They are downloaded when you generate.

## Permissions

- **Internet**: map tiles, regional data packs, OpenStreetMap context and one IP lookup (ipinfo.io) for where the map starts. The panel only opens when *Allow Online Access* is enabled in Preferences.
- **Files**: results and data packs are written to the `~/Gorani` folder. The Rhino version of Gorani uses the same folder, so data is shared.
- **Usage statistics**: nothing is sent unless you opt in from the panel. You can change this later in the panel menu.

## Requirements

Blender 4.2 or later and an internet connection. No Python packages are needed. The panel is currently in Korean.

---

도시설계 착수용 대지 컨텍스트 도구. 지도에서 대상지를 고르면 주변 건물·도로·지형·수계를 Blender에 만들고, 일러스트 베이스맵·현황도·조서를 함께 냅니다. 국내는 시군구 데이터 팩, 해외는 OpenStreetMap을 씁니다.
