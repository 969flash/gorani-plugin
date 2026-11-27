# Changelog

User-facing changes per release. The same text appears in the in-app update notice (`docs/notices.json`).
Downloads: [Releases](https://github.com/969flash/gorani-plugin/releases).

## 0.4.0 (2026-11-27)

New
- Supports Rhino 9.
- Advanced model: adds roof parapets, floor lines, road markings, street trees, rail tracks and retaining walls. Choose [Advanced] under Level.
- The basic model now includes bridge and overpass decks and curbs (roadways lowered 15 cm).
- Sign in with your Google account to use the Advanced model for free and manage your History. You can try the Advanced model 3 times without signing in.
- Change where results are saved from the More menu.

Improved
- Terrain outside Korea is more detailed (Mapterhorn) and sites outside Korea build faster.
- Sites still build from OpenFreeMap map data when all OpenStreetMap servers are blocked.

Fixed
- Rhino 7 and SketchUp: fixed a 'could not add objects' warning that appeared even when everything was added.
- Archicad: fixed terrain rising above roads, 2D elements piling up when building again, and buildings and terrain missing from the floor plan.
- Archicad: fixed gray colors, bare ground painted as grass, and failures when building from the 3D window.

## 0.3.9 (2026-11-08)

New
- You can draw several areas for a site and merge their outlines.
- You can reopen a previous result and keep working on it.
- In Rhino, press [Update now] in the update notice to install right away.

Improved
- Terrain: stepped terrain now follows the original contours more accurately and smoothly.
- Water: lakes are flat and rivers slope along the shore.
- Rhino 8: building Brep output is much faster.
- Sites outside Korea show an address instead of latitude and longitude.
- Public data: land use plan updated to the 2026-10-09 edition and Seoul UPIS to 2026-09.

Fixed
- Fixed several issues, including failures when splitting terrain faces.

## 0.3.8 (2026-11-06)

- 3D terrain is now a solid block down to a base (default; you can turn it off in 3D settings). The massing diagram draws it too.
- Rhino 8: 3D geometry can now be output as Brep (closed polysurfaces).
- Overseas sites: retries after a short wait when the OSM server is busy.
- SketchUp Windows: fixed the panel not opening.
- You can remove recent sites from the list.
- SketchUp and Rhino 7: the app no longer freezes on first launch; a 'Starting' screen appears instead.

## Earlier

Versions before 0.3.8 have no release notes here. See [Releases](https://github.com/969flash/gorani-plugin/releases) and the git history.
