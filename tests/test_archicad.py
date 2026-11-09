"""Archicad판 사이드카 — 순수 도우미(고리 잇기·각기둥 Morph·지면 Mesh) + 엔진 run(가짜 Archicad JSON 서버가 GoraniCommand에 답한다).
엔진 시험은 numpy·shapely 2.1+가 있는 파이썬(번들 파이썬)에서만 돈다 — 개발 Mac python3 discover는 도우미 시험만.

    build/sketchup/bsh_gorani/python/mac-arm64/bin/python3 -m unittest tests/test_archicad.py
"""

import http.server
import importlib.util
import itertools
import json
import os
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
sys.path.insert(0, str(SCRIPTS_DIR))
try:   # 번들 파이썬과 같은 shapely 2.1+(constrained_delaunay_triangles) — 개발 Mac python3의 2.0은 엔진 시험을 건너뛴다
    import shapely
    HAS_BACKEND = hasattr(shapely, "constrained_delaunay_triangles") and importlib.util.find_spec("mathutils") is None
except ImportError:
    HAS_BACKEND = False
READY = HAS_BACKEND and os.path.exists(SITE_DB) and os.path.exists(CONTEXT_DB)


class HelperTest(unittest.TestCase):
    """Rhino·shapely 없이 도는 도우미."""

    def test_edge_chains(self):
        import non_rhino_utils
        square = [(0, 1), (1, 2), (2, 3), (3, 0)]
        loops = non_rhino_utils.get_edge_chains(square, closed=True)
        self.assertEqual(len(loops), 1)
        self.assertEqual(sorted(loops[0]), [0, 1, 2, 3])
        # T자: 가지 친 점 1에서 끊긴다 — 0-1, 1-2, 1-3
        chains = non_rhino_utils.get_edge_chains([(0, 1), (1, 2), (1, 3)], closed=False)
        self.assertEqual(sorted(sorted(c) for c in chains), [[0, 1], [1, 2], [1, 3]])
        self.assertEqual(non_rhino_utils.get_signed_area([(0, 0), (1, 0), (1, 1), (0, 1)]), 1.0)

    def test_prism_body(self):
        import archicad_baker
        outer = [(0, 0), (0, 10), (10, 10), (10, 0)]   # 시계 — 고쳐 쓴다
        hole = [(2, 2), (8, 2), (8, 8), (2, 8)]          # 반시계 — 고쳐 쓴다
        body = archicad_baker.get_prism_body([[outer, hole]], 5.0, 12.0)
        self.assertEqual(len(body["vertices"]), 16)
        self.assertEqual(len(body["polygons"]), 2 + 8)   # 위·아래 + 옆 8
        top = body["polygons"][0]
        ring = [(body["vertices"][i]["x"], body["vertices"][i]["y"]) for i in top["vertexIds"]]
        self.assertGreater(archicad_baker.non_rhino_utils.get_signed_area(ring), 0)
        self.assertEqual(body["vertices"][top["vertexIds"][0]]["z"], 17.0)
        self.assertEqual(len(top["holes"]), 1)

    def test_ground_mesh(self):
        """두 분류(왼쪽 지형·오른쪽 도로) + 범위 링 → 바깥 고리 4점(높이는 같은 자리 정점), 안쪽 점 = 고리 밖 정점 2개."""
        import archicad_baker
        from types import SimpleNamespace
        left = SimpleNamespace(layer="CTX::Terrain", verts=[(0, 0, 1), (1, 0, 2), (1, 1, 3), (0, 1, 4)], faces=[(0, 1, 2), (0, 2, 3)])
        right = SimpleNamespace(layer="CTX::Roads", verts=[(1, 0, 2), (2, 0, 5), (2, 1, 6), (1, 1, 3)], faces=[(0, 1, 2), (0, 2, 3)])
        mesh = archicad_baker.get_ground_mesh([left, right], [(0, 0, 0), (2, 0, 0), (2, 1, 0), (0, 1, 0), (0, 0, 0)])
        self.assertEqual(mesh["outer"], [(0, 0, 1), (2, 0, 5), (2, 1, 6), (0, 1, 4)])
        self.assertEqual(sorted(line[0] for line in mesh["sublines"]), [(1, 0, 2), (1, 1, 3)])

    def test_addon_version(self):
        import constants
        text = (ROOT_DIR / "archicad" / "Sources" / "AddOnVersion.hpp").read_text(encoding="utf-8")
        self.assertEqual(re.search(r'ADDON_VERSION "([^"]+)"', text).group(1), constants.PANEL_VERSION)

    def test_panel_bridge_threaded(self):
        # 사이드카 메인 루프가 bridge.inbox.get()(스레드판 큐)을 기다린다 — threaded 없이 만들면 서버가 안 돌아 팔레트가 빈 화면(2026-11-09 Archicad 30 실기)
        text = (SCRIPTS_DIR / "cmd_archicad.py").read_text(encoding="utf-8")
        self.assertRegex(text, r"Bridge\(_ArchicadController\([^)]*\), threaded=True\)")


FLAT_TYPES = ("PolyLine", "Hotspot", "Text")   # Archicad 2D 요소 — 분류·속성을 못 받는다


class FakeArchicad(object):
    """Archicad JSON 서버 흉내 — API.IsAlive·API.ExecuteAddOnCommand(GoraniCommand)에 답하고 요소·레이어·속성·프로젝트 정보를 기억한다."""

    def __init__(self):
        self.ids = itertools.count(1)
        self.elements = {}    # guid → {type, props}
        self.layers = {"Layer": 1}
        self.properties = {}  # 이름 → guid
        self.groups = []
        self.info = {}        # 이름 → (id, 값)
        self.systems = []     # 분류 체계 이름
        self.classified = set()
        self.calls = []
        self.surfaces = {}    # 이름 → CreateSurfaces 항목
        self.hidden = set()   # 꺼 둔 채 만든 레이어
        self.morphs = []      # CreateMorphs 입력
        self.window = "3DModel"   # 사용자가 3D 창을 보던 중 — 모듈 저장은 평면도에서만 된다
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                result = fake.handle(body)
                data = json.dumps({"succeeded": True, "result": result}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()

    def _new(self, kind, count):
        out = []
        for _ in range(count):
            guid = "G%06d" % next(self.ids)
            self.elements[guid] = {"type": kind, "props": {}}
            out.append({"elementId": {"guid": guid}})
        return {"elements": out}

    def handle(self, body):
        if body["command"] == "API.IsAlive":
            return {"isAlive": True}
        if body["command"] != "API.ExecuteAddOnCommand":   # Archicad 기본 명령(분류·레이어 상태)
            return getattr(self, "a_" + body["command"][4:])(body.get("parameters") or {})
        name = body["parameters"]["addOnCommandId"]["commandName"]
        p = body["parameters"]["addOnCommandParameters"]
        self.calls.append(name)
        return {"addOnCommandResponse": getattr(self, "c_" + name, lambda p: {})(p)}

    def a_GetAllClassificationSystems(self, p):
        return {"classificationSystems": [{"classificationSystemId": {"guid": "C" + n}, "name": n} for n in self.systems]}

    def a_GetAllClassificationsInSystem(self, p):
        return {"classificationItems": [{"classificationItem": {"classificationItemId": {"guid": "CTX"}, "id": "CTX"}}]}

    def a_SetClassificationsOfElements(self, p):   # 2D 요소는 Archicad처럼 거부한다('Element not supported')
        rows = p["elementClassifications"]
        ok = [self.elements.get(row["elementId"]["guid"], {}).get("type") not in FLAT_TYPES for row in rows]
        self.classified.update(row["elementId"]["guid"] for row, good in zip(rows, ok) if good)
        return {"executionResults": [{"success": True} if good else {"success": False, "error": {"code": 7203, "message": "Element not supported"}} for good in ok]}

    def a_GetElementsByClassification(self, p):
        return {"elements": [{"elementId": {"guid": g}} for g in self.elements if g in self.classified]}

    def a_GetLayerAttributes(self, p):
        return {"attributes": []}

    def c_CreateClassificationSystems(self, p):
        self.systems += [x["classificationSystem"]["name"] for x in p["classificationSystemsWithItems"]]
        return {"executionResults": [{"success": True}]}

    def c_GetProjectInfoFields(self, p):
        return {"fields": [{"projectInfoId": i, "projectInfoName": n, "projectInfoValue": v} for n, (i, v) in self.info.items()]}

    def c_CreateProjectInfoFields(self, p):
        for f in p["projectInfoFields"]:
            self.info[f["projectInfoName"]] = ("I" + f["projectInfoName"], f.get("projectInfoValue", ""))
        return self.c_GetProjectInfoFields(p)

    def c_SetProjectInfoField(self, p):
        for n, (i, _v) in list(self.info.items()):
            if i == p["projectInfoId"]:
                self.info[n] = (i, p["projectInfoValue"])
        return {}

    def c_GetAttributesByType(self, p):
        if p["attributeType"] == "Surface":
            return {"attributes": [{"attributeId": {"guid": "S" + n}, "index": i, "name": n} for i, n in enumerate(self.surfaces, 1)]}
        return {"attributes": [{"attributeId": {"guid": "L%d" % i}, "index": i, "name": n} for n, i in self.layers.items()]}

    def c_CreateBuildingMaterials(self, p):
        return {"attributeIds": [{"attributeId": {"guid": "B" + m["name"]}} for m in p["buildingMaterialDataArray"]]}

    def c_CreateLayers(self, p):
        for layer in p["layerDataArray"]:
            self.layers.setdefault(layer["name"], len(self.layers) + 1)
            if layer.get("isHidden"):
                self.hidden.add(layer["name"])
        return {"attributeIds": [{"attributeId": {"guid": "L%d" % self.layers[l["name"]]}} for l in p["layerDataArray"]]}

    def c_CreateSurfaces(self, p):
        self.surfaces.update((s["name"], s) for s in p["surfaceDataArray"])
        return {"attributeIds": [{"attributeId": {"guid": "S" + s["name"]}} for s in p["surfaceDataArray"]]}

    def c_GetAllProperties(self, p):
        return {"properties": [{"propertyId": {"guid": g}, "propertyName": n, "propertyGroupName": "Gorani"} for n, g in self.properties.items()],
                "propertyGroups": [{"name": n} for n in self.groups]}

    def c_CreatePropertyGroups(self, p):
        self.groups += [g["propertyGroup"]["name"] for g in p["propertyGroups"]]
        return {"propertyGroupIds": [{}]}

    def c_CreatePropertyDefinitions(self, p):
        out = []
        for d in p["propertyDefinitions"]:
            self.properties[d["propertyDefinition"]["name"]] = "P" + d["propertyDefinition"]["name"]
            out.append({"propertyId": {"guid": self.properties[d["propertyDefinition"]["name"]]}})
        return {"propertyIds": out}

    def c_SetPropertyValuesOfElements(self, p):
        for row in p["elementPropertyValues"]:
            self.elements[row["elementId"]["guid"]]["props"][row["propertyId"]["guid"]] = row["propertyValue"]["value"]
        return {"executionResults": [{"success": True}] * len(p["elementPropertyValues"])}

    def c_GetPropertyValuesOfElements(self, p):
        prop = p["properties"][0]["propertyId"]["guid"]
        return {"propertyValuesForElements": [{"propertyValues": [{"propertyValue": {"value": self.elements[e["elementId"]["guid"]]["props"].get(prop, "")}}]}
                                              for e in p["elements"]]}

    def c_GetElementsByType(self, p):
        return {"elements": [{"elementId": {"guid": g}} for g, e in self.elements.items() if e["type"] == p["elementType"]]}

    def c_DeleteElements(self, p):
        for e in p["elements"]:
            self.elements.pop(e["elementId"]["guid"], None)
        return {"executionResults": []}

    def c_CreateMorphs(self, p):
        self.morphs += p["morphsData"]
        return self._new("Morph", len(p["morphsData"]))

    def c_SetDetailsOfElements(self, p):
        for row in p["elementsWithDetails"]:
            self.elements[row["elementId"]["guid"]]["layer"] = row["details"]["layerIndex"]
        return {"executionResults": [{"success": True}] * len(p["elementsWithDetails"])}

    def c_CreateMeshes(self, p):
        self.mesh = p["meshesData"][0]
        return self._new("Mesh", len(p["meshesData"]))

    def c_CreatePolylines(self, p):
        return self._new("PolyLine", len(p["polylinesData"]))

    def c_CreateHotspots(self, p):
        return self._new("Hotspot", len(p["hotspotsData"]))

    def c_CreateTexts(self, p):
        return self._new("Text", len(p["textsData"]))

    def a_Get3DBoundingBoxes(self, p):
        return {"boundingBoxes3D": [{"boundingBox3D": {"xMin": -100, "yMin": -100, "zMin": 10, "xMax": 100, "yMax": 100, "zMax": 60}} for _ in p["elements"]]}

    def c_Set3DProjectionSettings(self, p):
        self.camera = p["perspective"]
        return {"success": True}

    def c_FitInWindow(self, p):
        self.fitted = [e["elementId"]["guid"] for e in p.get("elements") or []]
        return {"success": True}

    def c_GetCurrentWindowType(self, p):
        return {"currentWindowType": self.window}

    def c_ChangeWindow(self, p):
        self.window = p["windowType"]
        return {"success": True}

    def c_SaveAsModuleFile(self, p):
        if self.window != "FloorPlan":
            return {"success": False, "error": {"code": -2130312312, "message": "the current window is not a model window"}}
        with open(p["moduleFilePath"], "wb") as f:
            f.write(b"mod")
        return {"success": True}

    def c_CreateHotlinkNodes(self, p):
        return {"hotlinkNodes": [{"hotlinkNodeId": {"guid": "H1"}, "existing": False}]}

    def c_CreateHotlinkInstances(self, p):
        return self._new("Hotlink", len(p["hotlinkInstances"]))


def _request(result_root, **options):
    import constants
    base = {"radius": 500, "shape": "buffer", "flatten_site": True, "site_output": "mesh", "make_sheets": False, "make_basemap": False}
    return {"target": {"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
            "result_root": result_root, "options": dict(base, **options)}


@unittest.skipUnless(READY, "numpy·shapely 번들 파이썬 + fixture DB에서만")
class SidecarRunTest(unittest.TestCase):
    """엔진 run → archicad_baker → 가짜 Archicad — 건물은 동마다 Morph·속성, 지형은 Mesh 하나, 원점은 프로젝트 정보, 사본은 context.mod."""

    @classmethod
    def setUpClass(cls):
        global cmd_archicad, loader
        cls._old_host = os.environ.get("GORANI_HOST")
        spec = importlib.util.spec_from_file_location("gorani_cmd_archicad", str(SCRIPTS_DIR / "cmd_archicad.py"))
        cmd_archicad = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = cmd_archicad
        spec.loader.exec_module(cmd_archicad)
        loader = cmd_archicad.loader
        cls.fake = FakeArchicad()
        cls.tmp = tempfile.TemporaryDirectory()
        constants = loader.load("constants")
        cls._old_home, constants.HOME_DIR = constants.HOME_DIR, cls.tmp.name   # 2D id 목록(archicad_2d.json)을 사용자 ~/Gorani에 쓰지 않게
        cls.host = cmd_archicad.ArchicadHost(cls.fake.port)
        cls.response = loader.load("context_builder").run(_request(cls.tmp.name), lambda *a: True, cls.host)

    @classmethod
    def tearDownClass(cls):
        loader.load("constants").HOME_DIR = cls._old_home
        cls.fake.close()
        cls.tmp.cleanup()
        if cls._old_host is None:
            os.environ.pop("GORANI_HOST", None)
        else:
            os.environ["GORANI_HOST"] = cls._old_host

    def test_ok_and_copy(self):
        r = self.response
        self.assertTrue(r["ok"], r["error"])
        self.assertTrue(r["context"]["path"].endswith("context.mod"))
        self.assertTrue(os.path.exists(r["context"]["path"]))
        self.assertEqual(self.fake.window, "3DModel")   # 저장하려고 평면도로 갔다가 보던 창으로
        self.assertFalse([w for w in r["warnings"] if w["code"] == "skipped"], r["warnings"])

    def test_elements(self):
        kinds = [e["type"] for e in self.fake.elements.values()]
        self.assertGreater(kinds.count("Morph"), 2500)   # 건물 동마다 + 분류 면 — 범위 링으로 늘 자른다(53659d6), 성수 R500 2,743개
        self.assertEqual(kinds.count("Mesh"), 1)
        self.assertGreater(len(self.fake.mesh["polygonCoordinates"]), 4)
        self.assertEqual(self.fake.mesh["buildingMaterialId"], {"guid": "BGorani CTX::Terrain"})   # 지형 색 — 없으면 Mesh 기본 잔디
        # 보이는 지형은 TIN 그대로의 Morph 면, Archicad Mesh는 꺼 둔 레이어(다시 삼각분할해 도로 위로 솟았다 — 2026-11-09)
        mesh_layer = [e["layer"] for e in self.fake.elements.values() if e["type"] == "Mesh"]
        self.assertEqual(mesh_layer, [self.fake.layers["CTX::Terrain::mesh"]])
        self.assertIn("CTX::Terrain::mesh", self.fake.hidden)
        terrain = self.fake.layers["CTX::Terrain"]
        self.assertTrue(any(e["type"] == "Morph" and e.get("layer") == terrain for e in self.fake.elements.values()))
        self.assertIn("CTX::Buildings", self.fake.layers)
        surface = self.fake.surfaces["Gorani CTX::Buildings"]   # 애드온은 red·green·blue 키만 읽는다 — r·g·b로 보내면 검정(2026-11-09)
        self.assertEqual(sorted(surface["surfaceColor"]), ["blue", "green", "red"])
        self.assertGreater(surface["diffuseReflection"], 0)
        lot_prop = self.fake.properties["GORANI_LOT_KEY"]
        self.assertTrue(all(lot_prop in e["props"] for e in self.fake.elements.values() if e["type"] not in FLAT_TYPES))
        self.assertEqual(self.fake.classified, {g for g, e in self.fake.elements.items() if e["type"] not in FLAT_TYPES})   # 속성은 분류에 매인다 — 2D 빼고 전부
        self.assertTrue(any(e["type"] == "PolyLine" for e in self.fake.elements.values()))
        self.assertTrue(any("PBLD_ID" in e["props"] for e in self.fake.elements.values()))

    def test_fit_skips_2d(self):   # 도엽 경계(수 km 폴리선)까지 맞추면 대상지가 점만 했다
        baker = loader.load("archicad_baker")
        self.fake.window = "FloorPlan"
        baker.zoom_to_site(self.host, self.response["dir"])
        types = {self.fake.elements[g]["type"] for g in self.fake.fitted}
        self.assertIn("Morph", types)
        self.assertFalse(types & set(FLAT_TYPES))
        self.fake.window = "3DModel"   # 3D 창은 대상지를 내려다보는 카메라
        self.fake.fitted = None
        baker.zoom_to_site(self.host, self.response["dir"])
        self.assertIsNone(self.fake.fitted)
        cam = self.fake.camera
        self.assertLess(cam["cameraPosition"]["y"], cam["targetPosition"]["y"])
        self.assertGreater(cam["cameraPosition"]["z"], cam["targetPosition"]["z"])

    def test_has_lot(self):
        baker = loader.load("archicad_baker")
        lot_key = loader.load("context_baker").read_meta(self.response["dir"])["lot_key"]
        self.assertTrue(baker.has_lot(self.host, lot_key))
        self.assertFalse(baker.has_lot(self.host, "nope"))

    def test_origin_written(self):
        self.assertEqual(self.fake.info["GORANI_ORIGIN_E"][1], "%.3f" % self.response["context"]["origin"][0])

    def test_rerun_replaces(self):
        before = len(self.fake.elements)
        baker = loader.load("archicad_baker")
        result = baker.import_mod(self.host, self.response["dir"])
        self.assertTrue(result["ok"], result["text"])
        self.assertTrue(result["replaced"])
        self.assertEqual([e["type"] for e in self.fake.elements.values()], ["Hotlink"])
        self.assertGreater(before, 1)


if __name__ == "__main__":
    unittest.main()
