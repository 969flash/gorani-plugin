# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

An open, unknown population of architecture and urban design practitioners and students in Korea. They use Rhino daily but do not know GIS or code. They open the tool on the first day of a project, pick a site, and want the site context in hand within minutes for a kickoff meeting, a report, a competition board, or a studio assignment.

## Product Purpose

UrbanSite turns one picked site into the starting material of an urban design project: a 3D context model in the open Rhino document, a layered basemap for Illustrator, and a family of analysis maps (현황도·분석도) built from public data. Success means a non-developer presses one button and gets drawings they can put straight into their own documents, with sources and reference dates already stated.

## Positioning

A free, personally published Rhino plugin (Yak) that works offline from local SQLite packs of Korean public data (parcels, buildings, roads, terrain, water, zoning). Paid Korean platforms sell feasibility reports; this tool instead hands designers editable drawings in their own tools (Rhino, Illustrator), on one shared drawing template.

## Operating Context

- Runs as a 480 px wide Eto WebView panel docked inside Rhino 8 (Windows and Mac). Single HTML file, vanilla JS, Leaflet map. No server.
- Flow: ① pick site (parcels, drawn area, or point) → ② range and outputs → ③ results (3D in the document, basemap .ai, analysis map SVG/AI, CSV tables).
- Outputs are finished in Illustrator and placed into A3 reports or A1 boards. Many offices have their own board template and graphic standard.

## Capabilities and Constraints

- Drawings share one template: same basemap, same layout, a theme layer per map. Users can set the drawing style (preset, element colors, line and text scale, layout) and save it as a JSON file to share.
- Conventional colors with legal or professional meaning (용도지역, 토지이용) stay locked by default.
- Source and reference-date lines are always printed (KOGL attribution, "no legal effect" notice).
- Contours at 1:5,000 or finer must not be shown on the web (공간정보관리법 / NGII security rules); desktop file delivery only.
- Terminology: 대상지 (site, `lot`), 범위 (extent), 베이스맵 (basemap), 현황도·분석도 (sheet). Korean UI copy.

## Brand Commitments

- Name: UrbanSite.
- Pretendard is bundled with the panel (`scripts/vendor/`).

## Evidence on Hand

- Real data: Seoul parcel and context DBs (`data/seoul_site.db`, `data/seoul_context.db`); fixture site 성수동2가 333-139.
- No user testimonials, usage numbers, or press exist; never invent them.

## Product Principles

1. One button to a usable result; defaults carry the user to the end.
2. The drawing is the product; the panel stays out of its way.
3. State the source and date of every public-data fact.
4. Simple over extensible: one developer, no server.
5. Follow urban design drawing conventions; point out when a request breaks them.
