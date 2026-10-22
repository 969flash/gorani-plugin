# Gorani for Archicad

Gorani builds the city around your site inside Archicad: buildings, roads, terrain and water, plus a basemap and analysis maps.
Archicad에서 대상지 주변 도시(건물·도로·지형·수계)와 베이스맵·분석도를 만듭니다.

Archicad 27, 28, 29, 30 · macOS · Windows

## Install / 설치

1. Download the zip for your Archicad version and OS, and unzip it. You get a `Gorani` folder.
   Archicad 버전·운영체제에 맞는 zip을 받아 풉니다. `Gorani` 폴더가 나옵니다.
2. Move the `Gorani` folder somewhere it can stay, such as Documents. Keep the files inside it together.
   `Gorani` 폴더를 문서 폴더처럼 계속 둘 곳으로 옮깁니다. 안의 파일은 흩지 않습니다.
3. macOS only: the add-on is not signed, so allow it once. Open Terminal and run:
   macOS만: 서명하지 않은 애드온이라 한 번 허용합니다. 터미널에서 실행합니다.

   ```
   xattr -dr com.apple.quarantine ~/Documents/Gorani
   ```

4. In Archicad, open **Options > Add-On Manager > Edit List of Available Add-Ons > Add**, pick `Gorani_AC<version>_Mac.bundle` (macOS) or `Gorani_AC<version>_Win.apx` (Windows) in the folder, and click **OK**.
   Archicad **옵션 > 애드온 관리자 > 사용 가능한 애드온 목록 편집 > 추가**에서 폴더 안 애드온 파일을 고르고 **확인**을 누릅니다.

## Use / 사용

Click **Gorani > Gorani Site Context…** in the menu bar. The Gorani panel opens as an Archicad palette. Pick a site on the map and click **Create 3D model**.
메뉴 막대의 **Gorani > Gorani Site Context…**를 누르면 Archicad 안에 Gorani 패널이 열립니다. 지도에서 대상지를 고르고 **3D 모델 만들기**를 누릅니다.

What you get in Archicad / Archicad에 들어가는 것:

- Layers `CTX::Buildings`, `CTX::Terrain`, `CTX::Roads` … (same names as the Rhino, SketchUp and Blender versions)
- Buildings: one Morph per building. Terrain: one Mesh. Roads, green, water: thin Morph surfaces just above the terrain. Parcels and the site: plan polylines.
- Classification **Gorani > Site context** and the property group **Gorani** (height, floors, use, approval date, height source …) on every element.
- Heights are real elevations above sea level (Korea: Incheon mean sea level).
- Basemap (.ai), analysis maps (SVG) and tables (CSV) go to the result folder, as in the other versions.

## Uninstall / 지우기

Remove Gorani in **Add-On Manager**, restart Archicad, then delete the `Gorani` folder. Settings and downloaded data stay in `~/Gorani`.
애드온 관리자에서 Gorani를 빼고 Archicad를 다시 시작한 뒤 `Gorani` 폴더를 지웁니다. 설정·받은 데이터는 `~/Gorani`에 남습니다.

## How it works / 구성

The add-on adds the Gorani menu and the Archicad commands Gorani needs. It is based on [Tapir](https://github.com/ENZYME-APD/tapir-archicad-automation) (MIT, `LICENSE-tapir.txt`). The engine runs in the bundled Python (`python/`, `scripts/`) and talks to Archicad through its local JSON interface (127.0.0.1).
애드온은 Gorani 메뉴와 필요한 Archicad 명령을 더합니다(Tapir 기반, MIT). 엔진은 함께 든 파이썬에서 돌고 Archicad 로컬 JSON 창구(127.0.0.1)로 모델을 만듭니다.

Developer notes (repository only): the add-on source is `archicad/` (forked from Tapir `2600b931`, see `archicad/TAPIR_COMMIT`), built by `.github/workflows/archicad.yml` for Archicad 27–30 on macOS and Windows. `python3 scripts/dev_deploy.py archicad` downloads the CI build for the current `archicad/` tree and makes one zip per Archicad version and OS. The add-on ID (MDID) in `archicad/Sources/RFIX/AddOnFix.grc` must be the registered Graphisoft developer ID; the placeholder `1 1` only loads in Archicad demo mode (`--dev` builds such a test zip). Test: `tests/test_archicad.py` (fake Archicad JSON server; engine tests need the bundled Python with shapely 2.1+).
