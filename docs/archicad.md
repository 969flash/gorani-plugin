# Gorani for Archicad

Gorani builds the city around your site inside Archicad: buildings, roads, terrain and water, plus a basemap and analysis maps.
Archicad에서 대상지 주변 도시(건물·도로·지형·수계)와 베이스맵·분석도를 만듭니다.

Archicad 27, 28, 29, 30 · macOS · Windows

## Install / 설치

1. Download the zip for your Archicad version and OS. Windows: in the zip file's Properties tick Unblock, then extract it. You get a `Gorani` folder.
   Archicad 버전·운영체제에 맞는 zip을 받습니다. Windows는 zip 속성에서 차단 해제를 체크한 뒤 풉니다. `Gorani` 폴더가 나옵니다.
2. Move the `Gorani` folder into the `Add-Ons` folder of your Archicad (change `30` to your version). Keep the files inside it together.
   `Gorani` 폴더를 Archicad의 `Add-Ons` 폴더로 옮깁니다(`30`은 쓰는 버전으로). 안의 파일은 흩지 않습니다.
   - Windows: `C:\Program Files\Graphisoft\Archicad 30\Add-Ons` (Windows asks for administrator permission / 관리자 권한을 물으면 계속)
   - macOS: `/Applications/Graphisoft/Archicad 30/Add-Ons`
3. macOS only: the add-on is not signed, so allow it once. Open Terminal and run:
   macOS만: 서명하지 않은 애드온이라 한 번 허용합니다. 터미널에서 실행합니다.

   ```
   xattr -dr com.apple.quarantine /Applications/Graphisoft/Archicad\ 30/Add-Ons/Gorani
   ```

4. Restart Archicad. Another way: keep the folder anywhere and add `Gorani_AC<version>_Mac.bundle` or `Gorani_AC<version>_Win.apx` in **Options > Add-On Manager**.
   Archicad를 다시 시작합니다. 폴더를 다른 곳에 두고 **옵션 > 애드온 관리자**에서 애드온 파일을 추가해도 됩니다.

## Use / 사용

Click **Gorani > Gorani Site Context…** in the menu bar at the top of the screen (between Window and Help). The Gorani panel opens as an Archicad palette. Pick a site on the map and click **Create 3D model**.
화면 맨 위 메뉴 막대의 **Gorani > Gorani Site Context…**를 누릅니다(Window와 Help 사이). Archicad 안에 Gorani 패널이 열립니다. 지도에서 대상지를 고르고 **3D 모델 만들기**를 누릅니다.

What you get in Archicad / Archicad에 들어가는 것:

- Layers `CTX::Buildings`, `CTX::Terrain`, `CTX::Roads` … (same names as the Rhino, SketchUp and Blender versions)
- Buildings: one Morph per building. Terrain, roads, green, water: Morph surfaces that follow the terrain exactly (as in the other versions). An Archicad Mesh of the terrain for site tools sits on the hidden layer `CTX::Terrain::mesh`. Parcels and the site: plan polylines.
  건물은 동마다 Morph, 지형·도로·녹지·수면은 지형을 그대로 따르는 Morph 면입니다. 지형 도구용 Archicad Mesh는 꺼 둔 레이어 `CTX::Terrain::mesh`에 있습니다.
- Everything shows on the Ground Floor plan. Making the same site again replaces the earlier one.
  모두 0층 평면에 보입니다. 같은 대상지를 다시 만들면 이전 것을 바꿉니다.
- Classification **Gorani > Site context** and the property group **Gorani** (height, floors, use, approval date, height source …) on every element.
- Heights are real elevations above sea level (Korea: Incheon mean sea level).
- Basemap (.ai), analysis maps (SVG) and tables (CSV) go to the result folder, as in the other versions.

## Uninstall / 지우기

Quit Archicad and delete the `Gorani` folder (if you added it in **Add-On Manager**, remove it there first). Settings and downloaded data stay in `~/Gorani`.
Archicad를 끄고 `Gorani` 폴더를 지웁니다(애드온 관리자로 넣었다면 거기서 먼저 뺍니다). 설정·받은 데이터는 `~/Gorani`에 남습니다.

## How it works / 구성

The add-on adds the Gorani menu and the Archicad commands Gorani needs. It is based on [Tapir](https://github.com/ENZYME-APD/tapir-archicad-automation) (MIT, `LICENSE-tapir.txt`). The engine runs in the bundled Python (`python/`, `scripts/`) and talks to Archicad through its local JSON interface (127.0.0.1).
애드온은 Gorani 메뉴와 필요한 Archicad 명령을 더합니다(Tapir 기반, MIT). 엔진은 함께 든 파이썬에서 돌고 Archicad 로컬 JSON 창구(127.0.0.1)로 모델을 만듭니다.

Developer notes (repository only): the add-on source is `archicad/` (forked from Tapir `2600b931`, see `archicad/TAPIR_COMMIT`), built by `.github/workflows/archicad.yml` for Archicad 27–30 on macOS and Windows. `python3 scripts/dev_deploy.py archicad` downloads the CI build for the current `archicad/` tree and makes one zip per Archicad version and OS. The add-on ID (MDID) in `archicad/Sources/RFIX/AddOnFix.grc` is Gorani's registered Graphisoft ID (developer 1127443810, add-on 'Gorani' in the archicadapi.graphisoft.com profile); a `1 1` placeholder only loads in Archicad demo mode (`--dev` builds such a test zip). Test: `tests/test_archicad.py` (fake Archicad JSON server; engine tests need the bundled Python with shapely 2.1+).
