"""SketchUp판 사이드카 — mesh_geometry shapely판(겹치기 CDT·격자 지반)·엔진 run(가짜 SketchUp이 host_call에 답한다)·다시 넣기·host_reply 경로.
numpy·shapely 2.1+가 있는 파이썬(번들 파이썬)에서만 돈다 — 개발 Mac python3 discover는 skip.

    build/sketchup/bsh_gorani/python/mac-arm64/bin/python3 -m unittest tests/test_sketchup.py
"""

import importlib.util
import json
import math
import os
import sys
import tempfile
import unittest
import urllib.request
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
try:   # 번들 파이썬과 같은 shapely 2.1+(constrained_delaunay_triangles) — 개발 Mac python3의 2.0은 건너뛴다
    import shapely
    HAS_BACKEND = hasattr(shapely, "constrained_delaunay_triangles") and importlib.util.find_spec("mathutils") is None
except ImportError:
    HAS_BACKEND = False
READY = HAS_BACKEND and os.path.exists(SITE_DB) and os.path.exists(CONTEXT_DB)


def setUpModule():
    """cmd_sketchup은 읽을 때 GORANI_HOST를 둔다 — 이 파일이 끝나면 되돌린다(같은 프로세스의 다른 시험이 Rhino 경로를 탄다)."""
    global cmd_sketchup, loader, _old_host
    if not READY:
        return
    _old_host = os.environ.get("GORANI_HOST")
    spec = importlib.util.spec_from_file_location("gorani_cmd_sketchup", str(SCRIPTS_DIR / "cmd_sketchup.py"))
    cmd_sketchup = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cmd_sketchup
    spec.loader.exec_module(cmd_sketchup)
    loader = cmd_sketchup.loader


def tearDownModule():
    if not READY:
        return
    if _old_host is None:
        os.environ.pop("GORANI_HOST", None)
    else:
        os.environ["GORANI_HOST"] = _old_host


def _request(result_root, **options):
    constants = loader.load("constants")
    base = {"radius": 500, "shape": "buffer", "flatten_site": True, "site_output": "mesh", "make_sheets": False, "make_basemap": False}
    return {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
            "result_root": result_root, "options": dict(base, **options)}


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


class FakeSketchUp(object):
    """sketchup_ext.rb rpc_* 흉내 — 컨트롤러 push를 가로채 host_call에 바로 답한다(같은 스레드)."""

    def __init__(self, controller):
        self.controller = controller
        self.attrs = {}
        self.items = []
        self.calls = []
        self.pushed = []
        controller.push = self.push

    def push(self, msg):
        if msg.get("type") != "host_call":
            self.pushed.append(msg)
            return
        method, args = msg["method"], msg["args"]
        self.calls.append(method)
        if method == "get_model_attrs":
            result = [self.attrs.get(key) for key in args["keys"]]
        elif method == "set_model_attrs":
            self.attrs.update(args["values"])
            result = True
        elif method == "clear":   # 구운 항목 기록은 남긴다(시험 순서와 무관하게 test_payload가 본다)
            result = [1 if self.items and args["lot_key"] else 0, 0]
        elif method == "bake":
            with open(args["path"], encoding="utf-8") as f:
                data = json.load(f)
            self.items += data["items"]
            result = list(range(len(data["items"])))
        elif method == "ref":
            result = [1, 2]
        elif method == "save":
            with open(args["path"], "wb") as f:
                f.write(b"skp")
            result = len(self.items)
        elif method == "import":
            result = {"objects": 7, "layers": 5}
        else:
            result = True
        self.controller.replies.put({"cmd": "host_reply", "id": msg["id"], "ok": True, "result": result, "error": ""})


@unittest.skipUnless(READY, "numpy·shapely 번들 파이썬 + fixture DB에서만")
class MeshGeometryTest(unittest.TestCase):
    """shapely판 겹치기 — 분류별 넓이 합 = 범위 넓이(틈·겹침 없음), 대상지 바닥 = 대상지 링 넓이(Blender판과 소수 첫째 자리까지 같다 — 2026-10-18)."""

    def test_areas(self):
        non_rhino_utils = loader.load("non_rhino_utils")
        prepared = loader.load("context_builder").prepare(_request(None))
        meshes, _tris, counts = loader.load("mesh_geometry").build_terrain(prepared)

        def area(mesh):
            verts, faces = mesh
            return sum(((verts[b][0] - verts[a][0]) * (verts[c][1] - verts[a][1]) - (verts[b][1] - verts[a][1]) * (verts[c][0] - verts[a][0])) / 2
                       for a, b, c in faces)

        total = sum(area(meshes[k]) for k in ("terrain", "road", "green", "rail", "water", "site_ground") if k in meshes)
        self.assertAlmostEqual(total, non_rhino_utils.get_ring_area(prepared.extent_ring), delta=1.0)
        self.assertAlmostEqual(area(meshes["site_ground"]), sum(non_rhino_utils.get_ring_area(r) for r in prepared.site_rings), delta=0.5)
        self.assertEqual(counts["drape_missing"], 0)

    def test_stepped_levels(self):
        prepared = loader.load("context_builder").prepare(_request(None, radius=300, shape="circle", terrain_step=1))
        meshes, _tris, counts = loader.load("mesh_geometry").build_terrain(prepared)
        zs = {v[2] for v in meshes["terrain"][0]}
        self.assertGreater(len(zs), 1)
        self.assertTrue(all(z == round(z) for z in zs), sorted(zs)[:5])

    def test_clean_edge_block(self):
        for step in (0, 2):
            prepared = loader.load("context_builder").prepare(_request(None, radius=300, shape="rect", flatten_site=False, clean_edge=True, terrain_step=step))
            meshes, _tris, counts = loader.load("mesh_geometry").build_terrain(prepared)
            _assert_block_closed(self, prepared, meshes, counts)


@unittest.skipUnless(READY, "numpy·shapely 번들 파이썬 + fixture DB에서만")
class SidecarRunTest(unittest.TestCase):
    """엔진 run → sketchup_baker → host_call — 건물은 동마다 각기둥, 원점은 모델 속성, 사본은 context.skp."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.controller = cmd_sketchup._SketchUpController("test")
        cls.fake = FakeSketchUp(cls.controller)
        cls.response = loader.load("context_builder").run(_request(cls.tmp.name), lambda *a: True, cls.controller.host)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_ok_and_copy(self):
        r = self.response
        self.assertTrue(r["ok"], r["error"])
        self.assertTrue(r["context"]["path"].endswith("context.skp"))
        self.assertTrue(os.path.exists(r["context"]["path"]))
        self.assertEqual(self.fake.calls[:3], ["get_model_attrs", "clear", "bake"])
        self.assertFalse([w for w in r["warnings"] if w["code"] == "skipped" and "베이크" in w["text"]])

    def test_payload(self):
        layers = {item["layer"]: item for item in self.fake.items}
        buildings = layers["CTX::Buildings"]
        self.assertGreater(len(buildings["prisms"]), 3000)
        parts, base, height, attrs, _name = buildings["prisms"][0]
        self.assertGreater(height, 0)
        self.assertIn("BLD_ID", attrs)
        self.assertEqual(len(parts[0][0][0]), 2)   # 링 점은 (x, y)
        self.assertTrue(layers["CTX::Terrain::site_original"]["hidden"])
        self.assertEqual(layers["CTX::Water"]["rgb"], [46, 125, 224])

    def test_origin_written(self):
        self.assertEqual(self.fake.attrs["GORANI_ORIGIN_E"], "%.3f" % self.response["context"]["origin"][0])

    def test_import_replaces(self):
        baker = loader.load("sketchup_baker")
        result = baker.import_skp(self.controller.host, self.response["dir"])
        self.assertTrue(result["ok"], result["text"])
        self.assertEqual(result["shift"], [0.0, 0.0])   # 같은 원점 모델


@unittest.skipUnless(READY, "numpy·shapely 번들 파이썬 + fixture DB에서만")
class BridgeTest(unittest.TestCase):
    """host_reply는 서버 스레드에서 바로 컨트롤러 응답 큐로(메인 스레드는 응답을 기다리며 막혀 있다)."""

    def test_host_reply_bypasses_inbox(self):
        bridge = loader.load("panel_server").Bridge(cmd_sketchup._SketchUpController("test"), threaded=True)
        try:
            body = json.dumps({"cmd": "host_reply", "id": 9, "ok": True, "result": [1]}).encode("utf-8")
            request = urllib.request.Request(bridge.url.replace("/?", "/cmd?"), data=body, method="POST")
            self.assertEqual(urllib.request.urlopen(request).status, 204)
            self.assertEqual(bridge.controller.replies.get(timeout=5)["id"], 9)
            self.assertTrue(bridge.inbox.empty())
        finally:
            bridge.close()

    def test_panel_closed_ends_wait(self):
        """패널을 닫으면(Ruby → stdin panel_closed) 생성은 취소, 답이 오지 않는 호스트 호출은 30분이 아니라 바로 끝난다. init이면 다시 연다."""
        controller = cmd_sketchup._SketchUpController("test")
        controller._running = True
        controller.handle({"cmd": "panel_closed"})
        self.assertTrue(controller._cancel_requested)
        with self.assertRaises(cmd_sketchup.HostError):
            controller.host.call("bake", path="x")
        controller._init = lambda msg: None   # 매니페스트·통계 없이 열림 표시만
        controller.handle({"cmd": "init"})
        self.assertTrue(controller.panel_open)


if __name__ == "__main__":
    unittest.main()
