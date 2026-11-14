"""OSM 받기 보험(osm_context — OpenFreeMap 벡터 타일) — 네트워크 없이: 작은 MVT 픽스처 해독, 레이어 → OSM 태그 대응,
타일 경계에서 잘린 건물 이어 붙이기·선 버퍼 겹침 없애기, Overpass가 막혔을 때 load가 타일로 만들고 출처·경고 거리를 남기는지."""

import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import constants  # noqa: E402
import non_rhino_utils  # noqa: E402
import osm_context  # noqa: E402

TEMPLATE = "https://tiles.example/planet/20261101_080013_pt/{z}/{x}/{y}.pbf"
TILE_X, TILE_Y = 8298, 5636   # 파리 z14 — 두 타일(TILE_X, TILE_X + 1)에 걸친 건물·도로


def _varint(n):
    out = b""
    while True:
        byte, n = n & 0x7F, n >> 7
        if not n:
            return out + bytes([byte])
        out += bytes([byte | 0x80])


def _field(number, wire, payload):
    if wire == 0:
        return _varint(number << 3) + _varint(payload)
    if wire == 1:
        return _varint(number << 3 | 1) + payload
    return _varint(number << 3 | 2) + _varint(len(payload)) + payload


def _zigzag(n):
    return (n << 1) ^ (n >> 63)


def _geometry(parts, closed):
    commands, x, y = [], 0, 0
    for part in parts:
        commands.append(1 | 1 << 3)
        for i, (px, py) in enumerate(part):
            if i == 1:
                commands.append(2 | (len(part) - 1) << 3)
            commands += [_zigzag(px - x), _zigzag(py - y)]
            x, y = px, py
        if closed:
            commands.append(7 | 1 << 3)
    return b"".join(_varint(c) for c in commands)


def _value(v):
    if isinstance(v, bool):
        return _field(7, 0, int(v))
    if isinstance(v, int):
        return _field(6, 0, _zigzag(v))
    if isinstance(v, float):
        return _field(3, 1, struct.pack("<d", v))
    return _field(1, 2, v.encode("utf-8"))


def _mvt(layers):
    """{레이어: [(속성, 종류, 점 목록들)]} → MVT bytes(extent 4096)."""
    tile = b""
    for name, features in layers.items():
        keys, values, body = [], [], _field(1, 2, name.encode("utf-8"))
        for props, kind, parts in features:
            tags = []
            for key, value in props.items():
                if key not in keys:
                    keys.append(key)
                if (type(value), value) not in values:
                    values.append((type(value), value))
                tags += [keys.index(key), values.index((type(value), value))]
            feature = _field(1, 0, 7) + _field(2, 2, b"".join(_varint(t) for t in tags)) + _field(3, 0, kind) + _field(4, 2, _geometry(parts, kind == 3))
            body += _field(2, 2, feature)
        body += b"".join(_field(3, 2, key.encode("utf-8")) for key in keys)
        body += b"".join(_field(4, 2, _value(value)) for _type, value in values)
        tile += _field(3, 2, body + _field(5, 0, 4096) + _field(15, 0, 2))
    return tile


def _box(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]   # 타일 좌표(y 아래로)에서 면적 + = 바깥 링


# 경계 x = 4096(왼쪽 타일) = 0(오른쪽 타일)에 걸친 건물 하나(실제 3900~4300)와 도로 하나 — 타일마다 64 단위 버퍼까지 담는다
LEFT = _mvt({
    "building": [({"render_height": 18, "render_min_height": 0}, 3, [_box(3900, 100, 4160, 300)]),
                 ({"render_height": 9, "render_min_height": 0, "hide_3d": True}, 3, [_box(1000, 1000, 1100, 1100)])],   # 부분이 따로 있는 외곽 — 뺀다
    "transportation": [({"class": "primary"}, 2, [[(3000, 2000), (4160, 2000)]])],
    "poi": [({"class": "railway", "subclass": "station", "name": "Gare"}, 1, [[(4120, 3000)]])],   # 버퍼 안 점 — 오른쪽 타일 것
})
RIGHT = _mvt({
    "building": [({"render_height": 18, "render_min_height": 0}, 3, [_box(-64, 100, 204, 300)])],
    "transportation": [({"class": "primary"}, 2, [[(-64, 2000), (1000, 2000)]])],
    "poi": [({"class": "railway", "subclass": "station", "name": "Gare"}, 1, [[(24, 3000)]])],
})


def _tile_bounds():
    """두 타일 가운데쯤(왼쪽 타일 x 3000 ~ 오른쪽 타일 x 1000, y 0 ~ 3500)을 TM bounds로 — 투영 원점도 그 자리."""
    (west, north), (east, south) = (non_rhino_utils.get_lnglat_from_tile(TILE_X + x / 4096.0, TILE_Y + y / 4096.0, 14) for x, y in ((3000, 50), (5096, 3500)))
    non_rhino_utils.set_projection((west + east) / 2, (south + north) / 2)
    (x0, y0), (x1, y1) = non_rhino_utils.get_tm_from_wgs84(west, south), non_rhino_utils.get_tm_from_wgs84(east, north)
    return x0, y0, x1, y1


class TileFallbackTest(unittest.TestCase):
    def setUp(self):
        self.saved = osm_context._fetch, dict(osm_context._TILE_TEMPLATES)
        tiles = {TEMPLATE.format(z=14, x=TILE_X, y=TILE_Y): LEFT, TEMPLATE.format(z=14, x=TILE_X + 1, y=TILE_Y): RIGHT}
        self.calls = []

        def fake_fetch(url, data=None, timeout=None):
            self.calls.append(url)
            return tiles[url]
        osm_context._fetch = fake_fetch
        osm_context._TILE_TEMPLATES[constants.OSM_FALLBACK_TILEJSON_URL] = TEMPLATE
        osm_context._CACHE.clear()

    def tearDown(self):
        osm_context._fetch = self.saved[0]
        osm_context._TILE_TEMPLATES.clear()
        osm_context._TILE_TEMPLATES.update(self.saved[1])
        osm_context._CACHE.clear()
        non_rhino_utils.set_projection()

    def test_decode_mvt(self):
        """MoveTo·LineTo·ClosePath, zigzag 음수, 문자열·정수·실수·참거짓 값, 레이어 고르기."""
        data = _mvt({"water": [({"class": "lake", "id": -5, "area": 1.5, "intermittent": False}, 3, [_box(-10, 0, 20, 30)])],
                     "poi": [({"class": "cafe"}, 1, [[(5, 6)]])]})
        layers = osm_context.decode_mvt(data)
        extent, features = layers["water"]
        self.assertEqual(extent, 4096)
        props, kind, lines = features[0]
        self.assertEqual((props, kind), ({"class": "lake", "id": -5, "area": 1.5, "intermittent": False}, 3))
        self.assertEqual(lines, [_box(-10, 0, 20, 30)])
        self.assertEqual(layers["poi"][1][0][2], [[(5, 6)]])
        self.assertEqual(list(osm_context.decode_mvt(data, ("poi",))), ["poi"])
        import gzip
        self.assertEqual(osm_context.decode_mvt(gzip.compress(data)), layers)

    def test_tile_tags(self):
        """OpenMapTiles 레이어 → Overpass와 같은 OSM 태그 — 그 뒤는 기존 get_feature_kind·높이 규칙이 그대로 읽는다."""
        tags = osm_context.get_tile_tags
        self.assertEqual(tags("transportation", {"class": "minor"}, 2), {"highway": "residential"})
        self.assertEqual(tags("transportation", {"class": "path", "subclass": "footway", "brunnel": "bridge", "layer": 1}, 2),
                         {"highway": "footway", "bridge": "yes", "layer": "1"})
        self.assertEqual(tags("transportation", {"class": "rail", "subclass": "rail", "brunnel": "tunnel"}, 2), {"railway": "rail", "tunnel": "yes"})
        self.assertEqual(tags("transportation", {"class": "path", "subclass": "pedestrian"}, 3), {"highway": "pedestrian", "area": "yes"})
        self.assertIsNone(tags("transportation", {"class": "path", "subclass": "platform"}, 3))   # 버스·철도 승강장을 가를 수 없다
        self.assertIsNone(tags("transportation", {"class": "primary_construction"}, 2))
        self.assertEqual(tags("water", {"class": "river"}, 3), {"natural": "water", "water": "river"})
        self.assertIsNone(tags("water", {"class": "ocean"}, 3))
        self.assertEqual(tags("landuse", {"class": "school"}, 3), {"amenity": "school"})
        self.assertEqual(tags("landcover", {"class": "grass", "subclass": "park"}, 3), {"leisure": "park"})
        self.assertEqual(tags("landcover", {"class": "wood", "subclass": "forest"}, 3), {"landuse": "forest"})
        self.assertEqual(tags("poi", {"class": "railway", "subclass": "subway", "name": "Odéon"}, 1), {"railway": "station", "name": "Odéon"})
        self.assertIsNone(tags("poi", {"class": "railway", "subclass": "halt", "name": "x"}, 1))
        self.assertIsNone(tags("building", {"render_height": 30, "render_min_height": 10}, 3))   # 떠 있는 부분
        self.assertEqual(osm_context.get_feature_kind(tags("landuse", {"class": "school"}, 3), True), ("public", "school_lot"))
        self.assertEqual(osm_context.get_building_height({"building": "yes", "render_height": 18})[2:], ("openfreemap_height", "C"))
        self.assertEqual(osm_context.get_building_height({"building": "yes", "render_height": 5})[2:], ("default", "D"))   # OpenMapTiles 기본값
        self.assertEqual(osm_context.get_tile_date(TEMPLATE), "2026-11-01")

    def test_seams(self):
        """타일 경계에서 잘린 건물은 한 동으로, 도로는 버퍼 겹침 없이, 버퍼 안 점은 한 번만."""
        bounds = _tile_bounds()
        elements = osm_context.get_tile_elements(bounds)
        self.assertEqual(self.calls, [TEMPLATE.format(z=14, x=TILE_X, y=TILE_Y), TEMPLATE.format(z=14, x=TILE_X + 1, y=TILE_Y)])
        buildings = [e for e in elements if "building" in e["tags"]]
        self.assertEqual(len(buildings), 1)
        xs = [non_rhino_utils.get_tile_xy(p["lon"], p["lat"], 14)[0] * 4096 - TILE_X * 4096 for p in buildings[0]["geometry"]]
        self.assertAlmostEqual(min(xs), 3900, delta=0.01)
        self.assertAlmostEqual(max(xs), 4096 + 204, delta=0.01)   # 오른쪽 조각이 붙었다(경계 정점은 지워진다)
        self.assertEqual(buildings[0]["geometry"][0], buildings[0]["geometry"][-1])
        roads = [e for e in elements if "highway" in e["tags"]]
        length = sum(abs(non_rhino_utils.get_tile_xy(e["geometry"][-1]["lon"], 0, 14)[0] - non_rhino_utils.get_tile_xy(e["geometry"][0]["lon"], 0, 14)[0])
                     for e in roads) * 4096
        self.assertAlmostEqual(length, (4096 - 3000) + 1000, delta=0.01)   # 버퍼 64 단위가 두 번 들어가지 않는다
        self.assertEqual(len([e for e in elements if e["type"] == "node"]), 1)

    def test_load_falls_back(self):
        """Overpass가 다 막히면 타일로 만든다 — 출처 openfreemap(기준일 = 타일 판), 건물 키·높이 출처, 켠 디테일은 빠졌다고 알린다."""
        bounds = _tile_bounds()
        saved = osm_context.get_terrain_spots, osm_context.load_plateau_buildings
        osm_context.get_terrain_spots, osm_context.load_plateau_buildings = (lambda b, t: ([], set())), (lambda b: ([], []))
        os.environ[constants.OSM_FALLBACK_FORCE_ENV] = "1"   # Overpass를 부르지 않고 붐빔으로
        try:
            waits = []
            context = osm_context.load(bounds, "2026-11-14", on_wait=waits.append, details=("detail_trees",))
        finally:
            del os.environ[constants.OSM_FALLBACK_FORCE_ENV]
            osm_context.get_terrain_spots, osm_context.load_plateau_buildings = saved
        self.assertEqual([(s.source_id, s.reference_date) for s in context.sources], [("openfreemap", "2026-11-01")])
        self.assertEqual([(b.src_key, b.height_m, b.height_src) for b in context.buildings], [("openfreemap:1", 18.0, "openfreemap_height")])
        self.assertEqual(sorted({(f.theme, f.kind) for f in context.features}), [("road", "centerline"), ("road", "surface"), ("transit", "station")])
        self.assertEqual(context.notes, ["osm_detail_missing"])
        self.assertTrue(all(url.startswith("https://tiles.example/") for url in self.calls))   # Overpass는 부르지 않았다
        self.assertEqual(len(waits), 2)   # 타일마다 진행 문구

    def test_pack_path_falls_back(self):
        """나라별 팩(일본 PLATEAU 등)이 있는 곳 — 본 질의가 막히면 도로·건물 메우기 모두 타일, 본 질의는 되고 건물 질의만 막히면 건물만 타일."""
        bounds = _tile_bounds()
        far = [list(non_rhino_utils.get_tm_from_wgs84(*non_rhino_utils.get_lnglat_from_tile(TILE_X + x / 4096.0, TILE_Y + y / 4096.0, 14)))
               for x, y in ((3200, 1000), (3300, 1000), (3300, 1100), (3200, 1100), (3200, 1000))]
        pack = osm_context.BuildingInfo(1, "plateau:a", "", "", "", 0, 0, "", 10.0, "plateau_height", "B", "", "", "active", "", "", "", 0.0, 0.0,
                                        {"type": "Polygon", "coordinates": [far]}, "plateau", "", *osm_context._get_bounds({"type": "Polygon", "coordinates": [far]}))
        source = osm_context.DataSource("plateau", "PLATEAU", "", "2025-03-31", "", "", "", "")
        queries = []

        def overpass(bounds, query=None, endpoints=None, on_wait=None):
            queries.append(query)
            if query == constants.OSM_OVERPASS_BUILDING_QUERY or self.down:
                raise RuntimeError("Overpass busy")
            return []
        saved = osm_context.get_terrain_spots, osm_context.load_plateau_buildings, osm_context.load_plateau_roads, osm_context.get_overpass_elements
        osm_context.get_terrain_spots, osm_context.load_plateau_buildings = (lambda b, t: ([], set())), (lambda b: ([pack], [source]))
        osm_context.load_plateau_roads, osm_context.get_overpass_elements = (lambda b: []), overpass
        try:
            self.down = True
            context = osm_context.load(bounds, "2026-11-14")
            self.assertEqual([s.source_id for s in context.sources], ["openfreemap", "plateau"])
            self.assertEqual([b.src_key for b in context.buildings], ["plateau:a", "openfreemap:1"])
            self.assertIn(("road", "centerline"), {(f.theme, f.kind) for f in context.features})
            self.assertEqual(len(queries), 1)   # 본 질의가 막히면 건물 질의는 묻지 않고 같은 타일을 쓴다
            self.down = False
            context = osm_context.load(bounds, "2026-11-14")
            self.assertEqual([s.source_id for s in context.sources], ["osm", "openfreemap", "plateau"])
            self.assertEqual([b.src_key for b in context.buildings], ["plateau:a", "openfreemap:1"])
            self.assertNotIn(("road", "centerline"), {(f.theme, f.kind) for f in context.features})   # 도로는 Overpass(빈 응답) 그대로
        finally:
            osm_context.get_terrain_spots, osm_context.load_plateau_buildings, osm_context.load_plateau_roads, osm_context.get_overpass_elements = saved

    def test_meta_lines(self):
        """도면 자료기준·출처 줄 — 타일 대체면 'OpenFreeMap <판 날짜>'와 OpenFreeMap·OpenMapTiles·OSM 표기, 높이 줄은 render_height."""
        import types
        import context_report
        crs = non_rhino_utils.get_crs_label()
        sources = [osm_context.DataSource("openfreemap", "OpenFreeMap (OpenMapTiles z14)", "", "2026-11-01", "2026-11-14", crs, "", ""),
                   osm_context.DataSource("aws_terrain", "Terrain Tiles", "", "", "2026-11-14", crs, "", "")]
        lines = context_report.get_meta_lines(types.SimpleNamespace(sources=sources, meta={"built_at": "2026-11-14T10:00:00"}))
        self.assertIn("OpenFreeMap 2026-11-01", lines[0])
        self.assertIn(constants.OSM_FALLBACK_CREDIT, lines[1])
        self.assertIn("render_height", lines[4])

    def test_both_down(self):
        """Overpass·타일 모두 막히면 두 오류를 함께 담은 RuntimeError(context_builder가 osm_failed로)."""
        def down(url, data=None, timeout=None):
            raise OSError("tiles down")
        osm_context._fetch = down
        os.environ[constants.OSM_FALLBACK_FORCE_ENV] = "1"
        try:
            with self.assertRaises(RuntimeError) as caught:
                osm_context.get_elements(_tile_bounds())
        finally:
            del os.environ[constants.OSM_FALLBACK_FORCE_ENV]
        self.assertIn("OpenFreeMap: tiles down", str(caught.exception))
        self.assertIn(constants.OSM_FALLBACK_FORCE_ENV, str(caught.exception))


if __name__ == "__main__":
    unittest.main()
