# Third-party notices

Gorani is licensed under GPL-3.0-or-later (see [LICENSE](LICENSE)). The third-party code below keeps its own license. Gorani does not relicense these files.

## In this repository

| Component | Path | License | License text |
|---|---|---|---|
| [Leaflet](https://leafletjs.com) 1.9.4 | `scripts/vendor/leaflet.js`, `scripts/vendor/leaflet.css` | BSD-2-Clause | [`scripts/vendor/LICENSE-leaflet.txt`](scripts/vendor/LICENSE-leaflet.txt) |
| [Pretendard](https://github.com/orioncactus/pretendard) | `scripts/vendor/PretendardVariable.woff2` | SIL Open Font License 1.1 | [`scripts/vendor/LICENSE-pretendard.txt`](scripts/vendor/LICENSE-pretendard.txt) |
| [Tapir](https://github.com/ENZYME-APD/tapir-archicad-automation) (Archicad add-on, forked from commit `2600b931`, see `archicad/TAPIR_COMMIT`) | `archicad/` | MIT | [`archicad/LICENSE.tapir`](archicad/LICENSE.tapir) |

## Bundled in the release packages only

The SketchUp, Rhino 7 and Archicad packages include a Python runtime and two libraries. They are not in this repository. Each package carries their license texts next to them.

| Component | License |
|---|---|
| Python 3.12 ([python-build-standalone](https://github.com/astral-sh/python-build-standalone)) and the libraries it bundles | PSF-2.0 and others, see `python/<platform>/` in the package |
| [NumPy](https://numpy.org) | BSD-3-Clause |
| [Shapely](https://github.com/shapely/shapely) with [GEOS](https://libgeos.org) | BSD-3-Clause (Shapely), LGPL-2.1-or-later (GEOS) |

Data packs and online data (parcels, buildings, OpenStreetMap and others) have their own licenses: see [README.md](README.md#data-sources-and-licenses).
