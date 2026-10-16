"""Blender판 — 엔진 run(베이크·context.blend)·다시 넣기·필지 경계 맞추기·브라우저 패널 브리지. Blender 안에서만 돈다(python3 discover는 skip).

    /Applications/Blender.app/Contents/MacOS/Blender -b --factory-startup --python-exit-code 1 --python tests/test_blender.py
"""

import importlib.util
import json
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

if bpy is not None:
    _spec = importlib.util.spec_from_file_location("urbansite_cmd_blender", str(SCRIPTS_DIR / "cmd_blender.py"))
    cmd_blender = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = cmd_blender
    _spec.loader.exec_module(cmd_blender)
    loader = cmd_blender.loader


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
        self.assertEqual(buildings["URBANSITE_MANAGED"], "1")
        self.assertTrue(bpy.data.collections["CTX::Terrain::site_original"].hide_viewport)
        ref = bpy.data.objects["origin"]
        self.assertEqual(ref["ORIGIN_E"], "%.3f" % self.response["context"]["origin"][0])
        self.assertEqual(bpy.context.scene["URBANSITE_ORIGIN_E"], ref["ORIGIN_E"])

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
        before = len([o for o in bpy.data.objects if o.get("URBANSITE_MANAGED") == "1"])
        result = baker.import_blend(bpy.context.scene, self.response["dir"])
        self.assertTrue(result["ok"], result["text"])
        self.assertTrue(result["replaced"])
        self.assertEqual(len([o for o in bpy.data.objects if o.get("URBANSITE_MANAGED") == "1"]), before)


@unittest.skipUnless(bpy is not None and HAS_FIXTURES, "Blender 안에서 fixture DB로만 돈다")
class SteppedTerrainTest(unittest.TestCase):
    """계단 지형 1 m + 평탄화 — 지반 정점 Z는 전부 1 m 배수, 경계 벽 윗선도 단 높이(아랫선만 평탄 높이)."""

    def test_levels(self):
        constants = loader.load("constants")
        request = {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
                   "options": {"radius": 300, "shape": "circle", "flatten_site": True, "terrain_step": 1}}
        prepared = loader.load("context_builder").prepare(request)
        meshes, _tris, counts = loader.load("blender_geometry").build_terrain(prepared)
        self.assertEqual(counts["terrain_step"], 1)
        zs = {v[2] for v in meshes["terrain"][0]}
        self.assertGreater(len(zs), 1)
        self.assertTrue(all(z == round(z) for z in zs), sorted(zs)[:5])
        level = counts["site_level"]   # 0.01 m 반올림 값
        self.assertTrue(all(abs(v[2] - level) <= 0.005 or v[2] == round(v[2]) for v in meshes["site_wall"][0]))


@unittest.skipUnless(bpy is not None, "Blender 안에서만")
class SnapTest(unittest.TestCase):
    def test_union_minus_cut(self):
        geometry = loader.load("blender_geometry")
        area = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]
        add = [[(10.0, 0.0), (20.0, 0.0), (20.0, 10.0), (10.0, 10.0)]]
        cut = [[(0.0, 0.0), (5.0, 0.0), (5.0, 5.0), (0.0, 5.0)]]
        ring = geometry.get_snapped_ring(area, add, cut, 0.05)
        self.assertAlmostEqual(loader.load("non_rhino_utils").get_ring_area(ring), 175.0, 3)


@unittest.skipUnless(bpy is not None and HAS_FIXTURES, "Blender 안에서만")
class BridgeTest(unittest.TestCase):
    """서버 스레드 ↔ 메인 스레드 펌프 — 토큰 없으면 403, init → init_state(host blender)."""

    def test_init_roundtrip(self):
        bridge = cmd_blender.get_bridge()
        bridge.controller._send_stats = lambda name, params: None   # 시험에서 사용 통계를 보내지 않는다
        base = bridge.url.split("?")[0]
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(base + "?token=wrong")
        self.assertEqual(caught.exception.code, 403)
        page = urllib.request.urlopen(bridge.url).read().decode("utf-8")
        self.assertIn("BRIDGE_TOKEN", page)
        self.assertNotIn("<!--VENDOR_JS-->", page)
        received = []
        opened = threading.Event()

        def listen():
            with urllib.request.urlopen(base + "events?token=" + bridge.token, timeout=30) as stream:
                opened.set()
                for line in stream:
                    if line.startswith(b"data: "):
                        received.append(json.loads(line[6:]))
                        return

        thread = threading.Thread(target=listen, daemon=True)
        thread.start()
        self.assertTrue(opened.wait(10))
        request = urllib.request.Request(base + "cmd?token=" + bridge.token, data=json.dumps({"cmd": "init"}).encode("utf-8"), method="POST")
        self.assertEqual(urllib.request.urlopen(request).status, 204)
        for _ in range(100):
            bridge.pump()
            thread.join(0.1)
            if received:
                break
        self.assertEqual(received[0]["type"], "init_state")
        self.assertEqual(received[0]["host"]["id"], "blender")


if __name__ == "__main__":
    result = unittest.main(argv=[sys.argv[0]] + sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else [sys.argv[0]], exit=False, verbosity=2).result
    if not result.wasSuccessful():
        raise SystemExit(1)
