"""웹판 — web_baker GLB(각기둥 면 풀기·레이어 노드)와 엔진 run(GORANI_HOST=web → mesh_geometry + web_baker).
numpy·shapely 2.1+가 있는 파이썬(SketchUp 번들 파이썬·Pyodide)에서만 돈다 — 개발 Mac python3 discover는 skip.

    build/sketchup/bsh_gorani/python/mac-arm64/bin/python3.12 -m unittest tests/test_web.py
"""

import importlib.util
import json
import os
import struct
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
try:
    import shapely
    HAS_BACKEND = hasattr(shapely, "constrained_delaunay_triangles") and importlib.util.find_spec("mathutils") is None
except ImportError:
    HAS_BACKEND = False
READY = HAS_BACKEND and os.path.exists(SITE_DB)
sys.path.insert(0, str(SCRIPTS_DIR))


def read_glb(data):
    """GLB → (json dict, bin bytes)."""
    magic, version, total = struct.unpack_from("<III", data, 0)
    assert (magic, version, total) == (0x46546C67, 2, len(data))
    json_len, json_type = struct.unpack_from("<II", data, 12)
    assert json_type == 0x4E4F534A
    gltf = json.loads(data[20:20 + json_len])
    bin_len, bin_type = struct.unpack_from("<II", data, 20 + json_len)
    assert bin_type == 0x004E4942
    return gltf, data[28 + json_len:28 + json_len + bin_len]


@unittest.skipUnless(READY, "numpy·shapely 2.1+ + fixture DB에서만")
class WebBakerTest(unittest.TestCase):
    def test_prism_with_hole(self):
        """10 × 10 m에 2 × 2 m 구멍, 높이 5 m → 윗면 넓이 96 ㎡, 옆면 사각형 8개, 윗면은 위를 본다."""
        import numpy
        import web_baker
        outer = [(0, 0), (10, 0), (10, 10), (0, 10), (0, 0)]
        hole = [(4, 4), (4, 6), (6, 6), (6, 4), (4, 4)]
        points, indices = web_baker._get_prism_arrays([([[outer, hole]], 1.0, 5.0, {}, "")])
        tris = points[indices.reshape(-1, 3)]
        normal_z = (tris[:, 1, 0] - tris[:, 0, 0]) * (tris[:, 2, 1] - tris[:, 0, 1]) - (tris[:, 1, 1] - tris[:, 0, 1]) * (tris[:, 2, 0] - tris[:, 0, 0])
        top = numpy.all(tris[:, :, 2] == 6.0, axis=1)
        self.assertAlmostEqual(normal_z[top].sum() / 2, 96.0, 6)
        self.assertTrue((normal_z[top] > 0).all())
        walls = ~numpy.all(tris[:, :, 2] == tris[:, :1, 2], axis=1)
        self.assertEqual(walls.sum(), 16)


@unittest.skipUnless(READY, "numpy·shapely 2.1+ + fixture DB에서만")
class WebRunTest(unittest.TestCase):
    """엔진 run → web_baker → context.glb — 레이어 노드, 인덱스 범위, 원점 extras."""

    @classmethod
    def setUpClass(cls):
        cls.old_host = os.environ.get("GORANI_HOST")
        os.environ["GORANI_HOST"] = "web"
        import constants
        import context_builder
        import web_baker
        cls.tmp = tempfile.TemporaryDirectory()
        request = {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
                   "result_root": cls.tmp.name, "options": {"radius": 300, "shape": "buffer", "make_sheets": False, "make_basemap": False}}
        cls.response = context_builder.run(request, lambda *a: True, web_baker.WebDoc())

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        if cls.old_host is None:
            os.environ.pop("GORANI_HOST", None)
        else:
            os.environ["GORANI_HOST"] = cls.old_host

    def test_glb(self):
        r = self.response
        self.assertTrue(r["ok"], r["error"])
        self.assertTrue(r["context"]["path"].endswith("context.glb"))
        with open(r["context"]["path"], "rb") as f:
            gltf, binary = read_glb(f.read())
        names = [n["name"] for n in gltf["nodes"]]
        self.assertIn("CTX::Buildings", names)
        self.assertNotIn("CTX::Terrain::site_original", names)   # 숨김 레이어
        self.assertEqual(gltf["asset"]["extras"]["gorani"]["origin"], [round(v, 3) for v in r["context"]["origin"]])
        for mesh in gltf["meshes"]:
            for prim in mesh["primitives"]:
                count = gltf["accessors"][prim["attributes"]["POSITION"]]["count"]
                index = gltf["accessors"][prim["indices"]]
                view = gltf["bufferViews"][index["bufferView"]]
                values = struct.unpack_from("<%dI" % index["count"], binary, view["byteOffset"])
                self.assertLess(max(values), count, mesh["name"])


if __name__ == "__main__":
    unittest.main()
