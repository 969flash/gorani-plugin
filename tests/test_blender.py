"""Blender판 — 엔진 run(베이크·context.blend)·다시 넣기·브라우저 패널 브리지. Blender 안에서만 돈다(python3 discover는 skip).

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 --python tests/test_blender.py
빌드한 확장 패키지(`# [blender-cut]` 구간을 뺀 판)로 돌리려면 GORANI_BLENDER_PACKAGE=build/blender (dev_deploy.py blender가 만든 폴더).
"""

import importlib.util
import json
import math
import os
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

try:
    import bpy
except ImportError:
    bpy = None

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
HAS_FIXTURES = os.path.exists(SITE_DB) and os.path.exists(CONTEXT_DB)

PACKAGE_DIR = os.environ.get("GORANI_BLENDER_PACKAGE")
GEO_UTILS = "geo_utils" if PACKAGE_DIR else "non_rhino_utils"   # 패키지는 이름을 바꿔 싣는다(dev_deploy.BLENDER_RENAMES)

if bpy is not None and PACKAGE_DIR:   # 설치본과 같은 패키지 상대 import
    sys.path.insert(0, os.path.abspath(PACKAGE_DIR))
    cmd_blender = importlib.import_module("gorani.scripts.cmd_blender")
    loader = cmd_blender.loader
elif bpy is not None:
    _spec = importlib.util.spec_from_file_location("gorani_cmd_blender", str(SCRIPTS_DIR / "cmd_blender.py"))
    cmd_blender = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = cmd_blender
    _spec.loader.exec_module(cmd_blender)
    loader = cmd_blender.loader


@unittest.skipUnless(bpy is not None, "Blender 안에서만 돈다")
class LargeIdTest(unittest.TestCase):
    def test_split_building_id(self):
        """32비트를 넘는 건물 id(한국 시도 팩 시도 × 10⁹, 일본 팩 시구정촌 × 10⁷)는 아래 9자리 + _high로 나눠 담는다."""
        mesh_geometry, blender_baker = loader.load("mesh_geometry"), loader.load("blender_baker")
        ids = [26 * 10 ** 9 + 5, 13104 * 10 ** 7 + 7, 3]
        item = mesh_geometry.BakeItem("CTX::Buildings", "buildings", verts=[(0, 0, 0), (1, 0, 0), (0, 1, 0), (1, 1, 0)],
                                      faces=[(0, 1, 2), (1, 3, 2), (0, 2, 3)], face_attrs={"building_id": ids, "height": [1.0, 2.0, 3.0]})
        mesh = blender_baker._make_data(item)
        low = [d.value for d in mesh.attributes["building_id"].data]
        high = [d.value for d in mesh.attributes["building_id_high"].data]
        self.assertEqual([h * 10 ** 9 + v for h, v in zip(high, low)], ids)
        bpy.data.meshes.remove(mesh)


@unittest.skipUnless(bpy is not None and HAS_FIXTURES, "Blender 안에서 fixture DB로만 돈다")
class RunTest(unittest.TestCase):
    """성수 fixture 500 m — 대상지 평탄화 + 바닥 메시까지 켠 생성 한 번."""

    @classmethod
    def setUpClass(cls):
        constants = loader.load("constants")
        cls.tmp = tempfile.TemporaryDirectory()
        request = {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
                   "result_root": cls.tmp.name, "options": {"radius": 500, "shape": "buffer", "flatten_site": True, "site_output": "mesh",
                                                            "make_sheets": False, "make_basemap": False}}
        cls.phases = []
        cls.response = loader.load("context_builder").run(request, lambda phase, fraction, text: cls.phases.append(phase) or True, bpy.context.scene)

    @classmethod
    def tearDownClass(cls):
        loader.load("blender_baker").clear_previous(bpy.context.scene)
        cls.tmp.cleanup()

    def test_ok_and_blend_written(self):
        r = self.response
        self.assertTrue(r["ok"], r["error"])
        self.assertTrue(r["context"]["path"].endswith("context.blend"))
        self.assertTrue(os.path.exists(r["context"]["path"]))
        self.assertGreater(r["context"]["buildings"], 3000)
        self.assertIn("write_3dm", self.phases)

    def test_collections_and_attributes(self):
        names = {c.name for c in bpy.data.collections}
        for layer in ("CTX::Buildings", "CTX::Terrain", "CTX::Roads", "CTX::Site", "CTX::Site::ground", "CTX::Terrain::site_wall", "CTX::Ref"):
            self.assertIn(layer, names)
        buildings = bpy.data.collections["CTX::Buildings"].objects[0]
        mesh = buildings.data
        self.assertEqual(len(mesh.attributes["height"].data), len(mesh.polygons))
        self.assertEqual(buildings["GORANI_MANAGED"], "1")
        self.assertTrue(bpy.data.collections["CTX::Terrain::site_original"].hide_viewport)
        ref = bpy.data.objects["origin"]
        self.assertEqual(ref["ORIGIN_E"], "%.3f" % self.response["context"]["origin"][0])
        self.assertEqual(bpy.context.scene["GORANI_ORIGIN_E"], ref["ORIGIN_E"])

    def test_buildings_stand_on_ground(self):
        """건물 바닥 Z가 지형 높이 범위 안 — 원점 이동이 지형·건물에 같게 걸렸는지."""
        terrain = bpy.data.collections["CTX::Terrain"].objects[0].data
        zs = [v.co.z for v in terrain.vertices]
        mesh = bpy.data.collections["CTX::Buildings"].objects[0].data
        bottom = min(v.co.z for v in mesh.vertices)
        self.assertGreaterEqual(bottom, min(zs) - 1.0)
        self.assertLessEqual(bottom, max(zs) + 1.0)

    def test_import_blend_replaces(self):
        baker = loader.load("blender_baker")
        before = len([o for o in bpy.data.objects if o.get("GORANI_MANAGED") == "1"])
        result = baker.import_blend(bpy.context.scene, self.response["dir"])
        self.assertTrue(result["ok"], result["text"])
        self.assertTrue(result["replaced"])
        self.assertEqual(len([o for o in bpy.data.objects if o.get("GORANI_MANAGED") == "1"]), before)


@unittest.skipUnless(bpy is not None and HAS_FIXTURES, "Blender 안에서 fixture DB로만 돈다")
class SteppedTerrainTest(unittest.TestCase):
    """계단 지형 1 m + 평탄화 — 지반 정점 Z는 전부 1 m 배수, 경계 벽 윗선도 단 높이(아랫선만 평탄 높이)."""

    def test_levels(self):
        constants = loader.load("constants")
        request = {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
                   "options": {"radius": 300, "shape": "circle", "flatten_site": True, "terrain_step": 1}}
        prepared = loader.load("context_builder").prepare(request)
        meshes, _tris, counts = loader.load("mesh_geometry").build_terrain(prepared)
        self.assertEqual(counts["terrain_step"], 1)
        zs = {v[2] for v in meshes["terrain"][0]}
        self.assertGreater(len(zs), 1)
        self.assertTrue(all(z == round(z) for z in zs), sorted(zs)[:5])
        level = counts["site_level"]   # 0.01 m 반올림 값
        self.assertTrue(all(abs(v[2] - level) <= 0.005 or v[2] == round(v[2]) for v in meshes["site_wall"][0]))

    def test_clean_edge_block(self):
        constants = loader.load("constants")
        for shape in ("rect", "circle"):
            request = {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
                       "options": {"radius": 300, "shape": shape, "clean_edge": True, "site_output": "mesh"}}
            prepared = loader.load("context_builder").prepare(request)
            meshes, _tris, counts = loader.load("mesh_geometry").build_terrain(prepared)
            _assert_block_closed(self, prepared, meshes, counts)


def _assert_block_closed(test, prepared, meshes, counts):
    """경계 정리 — 범위 링 위 윗면 변마다 옆면 변이 하나씩 붙는다(덩어리가 둘레에서 닫힘), 옆면 아래 = 바닥 높이."""
    ring = [(x - prepared.origin[0], y - prepared.origin[1]) for x, y in loader.load("context_geometry").get_clip_ring(prepared)]

    def on_ring(p):
        for (ax, ay), (bx, by) in zip(ring, ring[1:] + ring[:1]):
            dx, dy = bx - ax, by - ay
            t = max(0.0, min(1.0, ((p[0] - ax) * dx + (p[1] - ay) * dy) / (dx * dx + dy * dy)))
            if math.hypot(p[0] - ax - dx * t, p[1] - ay - dy * t) < 1e-3:
                return True
        return False

    edges = {}
    for key in ("terrain", "road", "green", "rail", "water", "site_ground", "block"):
        verts, faces = meshes.get(key, ([], []))
        for face in faces:
            for k in range(len(face)):
                p, q = verts[face[k]], verts[face[(k + 1) % len(face)]]
                if math.hypot(q[0] - p[0], q[1] - p[1]) > 1e-6 and on_ring(p) and on_ring(q) and on_ring(((p[0] + q[0]) / 2, (p[1] + q[1]) / 2)):
                    edge = frozenset((tuple(round(c, 4) for c in p), tuple(round(c, 4) for c in q)))
                    edges[edge] = edges.get(edge, 0) + 1
    test.assertTrue(edges)
    test.assertEqual({n for e, n in edges.items() if all(v[2] > counts["block_base"] for v in e)}, {2})
    test.assertEqual(min(v[2] for v in meshes["block"][0]), counts["block_base"])


@unittest.skipUnless(bpy is not None, "Blender 안에서만 돈다")
class CurveRingTest(unittest.TestCase):
    def test_bezier_circle_follows_curve(self):
        """Bezier Circle(제어점 4개)은 원을 따라 링이 된다 — 제어점만 이으면 넓이가 원의 64 %(마름모)였다."""
        bpy.ops.curve.primitive_bezier_circle_add(radius=50.0)
        obj = bpy.context.active_object
        try:
            ring, problem = cmd_blender.get_curve_ring(obj, 1.0)
            self.assertEqual(problem, "")
            self.assertAlmostEqual(loader.load(GEO_UTILS).get_ring_area(ring), math.pi * 50.0 ** 2, delta=0.01 * math.pi * 50.0 ** 2)
            obj.data.splines[0].use_cyclic_u = False
            self.assertIsNone(cmd_blender.get_curve_ring(obj, 1.0)[0])
        finally:
            bpy.data.objects.remove(obj, do_unlink=True)


@unittest.skipUnless(bpy is not None and HAS_FIXTURES, "Blender 안에서만")
class BridgeTest(unittest.TestCase):
    """스레드 없는 브리지 — 메인 스레드 pump가 연결을 받는다. 토큰 없으면 403, init → init_state(host blender, 사용 통계 묻지 않음)."""

    def _call(self, bridge, request):
        """브라우저 쪽 요청 하나 — 서버는 메인 스레드 pump가 돌리므로 요청은 옆 스레드에서 보낸다."""
        box = {}

        def run():
            try:
                with urllib.request.urlopen(request, timeout=10) as response:
                    box["status"], box["body"] = response.status, response.read()
            except urllib.error.HTTPError as error:
                box["status"] = error.code

        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        while thread.is_alive():
            bridge.pump()
            thread.join(0.02)
        return box

    def test_init_roundtrip(self):
        bridge = cmd_blender.get_bridge()
        self.assertFalse(bridge.threaded)
        base = bridge.url.split("?")[0]
        self.assertEqual(self._call(bridge, base + "?token=wrong")["status"], 403)
        page = self._call(bridge, bridge.url)["body"].decode("utf-8")
        self.assertIn("BRIDGE_TOKEN", page)
        self.assertNotIn("<!--VENDOR_JS-->", page)
        received = []

        def listen():
            with urllib.request.urlopen(base + "events?token=" + bridge.token, timeout=30) as stream:
                for line in stream:
                    if line.startswith(b"data: "):
                        received.append(json.loads(line[6:]))
                        return

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
        for _ in range(250):
            bridge.pump()
            if bridge.streams:
                break
            thread.join(0.02)
        request = urllib.request.Request(base + "cmd?token=" + bridge.token, data=json.dumps({"cmd": "init"}).encode("utf-8"), method="POST")
        self.assertEqual(self._call(bridge, request)["status"], 204)
        for _ in range(250):
            bridge.pump()
            thread.join(0.02)
            if received:
                break
        self.assertEqual(received[0]["type"], "init_state")
        self.assertEqual(received[0]["host"]["id"], "blender")
        self.assertFalse(received[0]["host"].get("ask_stats"))   # Blender판은 사용 통계를 묻지도 보내지도 않는다(패키지에는 키도 없다)
        self.assertNotIn("aerial", [sheet["key"] for sheet in received[0]["sheet_catalog"]])
        self.assertEqual(received[0]["tile"]["abroad_aerial_url"], "")
        self.assertIsNone(received[0]["update"])


if __name__ == "__main__":
    result = unittest.main(argv=[sys.argv[0]] + sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [sys.argv[0]], exit=False, verbosity=2).result
    if not result.wasSuccessful():
        raise SystemExit(1)
