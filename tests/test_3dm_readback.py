"""driver_full_run이 남긴 context.3dm 되읽기 — rhino3dm(테스트 전용, 배포 불포함)으로 레이어 FullPath·CTX::Buildings 수·UserString 14키·doc.Strings 원점.

대상: result/rhino_jobs/<가장 최근 job>/out/context.3dm (+ 같은 폴더 response.json). 없으면 skip.
    python3 scripts/dev_rhino_run.py tests/rhino/driver_full_run.py && python3 -m unittest tests.test_3dm_readback
"""

import glob
import json
import os
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants

ROOT_DIR = Path(__file__).resolve().parents[1]
MODEL_PATHS = sorted(glob.glob(str(ROOT_DIR / "result" / "rhino_jobs" / "*" / "out" / constants.CONTEXT_MODEL_FILE_NAME)))
# Rhino는 값이 빈 UserString을 저장하지 않는다(job 1007-223545-f01e 실측: DEMOL_DAY·ALIGN_MEDIAN_M이 사본에서 사라짐) —
# 그래서 '있는 키 ⊆ 14키'와 '항상 값이 있는 키는 반드시 있다'로 단언한다.
BUILDING_KEYS = ("BLD_ID", "PNU", "PNU_SRC", "GRND_FLR", "FLR_SRC", "UGRND_FLR", "HEIGHT_M", "HEIGHT_SRC", "HEIGHT_GRADE",
                 "USABILITY", "USEAPR_DAY", "BLD_NM", "STATUS", "DEMOL_DAY")
BUILDING_KEYS_REQUIRED = ("BLD_ID", "PNU_SRC", "GRND_FLR", "UGRND_FLR", "HEIGHT_M", "HEIGHT_SRC", "HEIGHT_GRADE", "STATUS")
REF_KEYS = ("CRS", "ORIGIN_E", "ORIGIN_N", "RADIUS_M", "SHAPE", "SRC_SHEETS", "BUILT_AT", "TOOL_VERSION", "ALIGN_MEDIAN_M", "ALIGN_P90_M",
            "ALIGN_N", "ALIGN_DX_DY", "TOPO_YEAR", "TRANSFORM", "VDATUM", "DATE_LOT", "DATE_BUILDING", "DATE_TERRAIN", "DATE_UPIS", "META_LINES", "PLACEMENT")
REF_KEYS_REQUIRED = tuple(k for k in REF_KEYS if k not in ("ALIGN_MEDIAN_M", "ALIGN_P90_M"))   # fixture에는 정합 샘플이 없어 둘은 빈 값
MANAGED_KEYS = {constants.UDT_MANAGED_KEY, constants.UDT_LOT_KEY}


@unittest.skipUnless(MODEL_PATHS, "result/rhino_jobs/*/out/context.3dm 없음 — driver_full_run.py를 먼저 돌린다")
class ReadbackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import rhino3dm
        cls.path = MODEL_PATHS[-1]
        cls.model = rhino3dm.File3dm.Read(cls.path)
        response_path = os.path.join(os.path.dirname(cls.path), "response.json")
        cls.response = json.load(open(response_path, encoding="utf-8")) if os.path.exists(response_path) else None
        cls.layer_paths = {layer.Index: layer.FullPath for layer in cls.model.Layers}
        cls.by_layer = {}
        for obj in cls.model.Objects:
            cls.by_layer.setdefault(cls.layer_paths.get(obj.Attributes.LayerIndex, ""), []).append(obj)

    def _user_strings(self, obj):
        return dict(obj.Attributes.GetUserStrings())

    def test_layer_full_paths(self):
        paths = set(self.layer_paths.values())
        for name in ("Site", "Parcels", "Buildings", "Terrain", "Ref"):
            self.assertIn("%s::%s" % (constants.CTX_ROOT_LAYER, name), paths)
        ctx = {p for p in paths if p.startswith(constants.CTX_ROOT_LAYER + "::")}
        self.assertGreaterEqual(len(ctx), 7, sorted(ctx))
        bm = {p for p in paths if p.startswith(constants.BM_ROOT_LAYER + "::")}   # 2D 도면 레이어(기본 off)
        self.assertGreaterEqual(len(bm), 10, sorted(bm))
        if self.response:
            self.assertEqual(len(ctx) + len(bm), self.response["context"]["layers"], sorted(ctx | bm))

    def test_building_count_matches_counts(self):
        buildings = self.by_layer.get(constants.CTX_ROOT_LAYER + "::Buildings", [])
        if self.response:
            self.assertEqual(len(buildings), self.response["context"]["buildings"])
        else:
            self.assertGreater(len(buildings), 3000)
        self.assertEqual(len(self.by_layer.get(constants.CTX_ROOT_LAYER + "::Site", [])), 1)

    def test_building_user_strings_14_keys(self):
        buildings = self.by_layer[constants.CTX_ROOT_LAYER + "::Buildings"]
        present = set()
        for obj in buildings:
            attrs = self._user_strings(obj)
            self.assertTrue(set(attrs) <= set(BUILDING_KEYS) | MANAGED_KEYS, sorted(set(attrs) - set(BUILDING_KEYS) - MANAGED_KEYS))
            self.assertTrue(set(BUILDING_KEYS_REQUIRED) <= set(attrs), sorted(set(BUILDING_KEYS_REQUIRED) - set(attrs)))
            self.assertEqual(attrs[constants.UDT_MANAGED_KEY], "1")
            self.assertEqual(len(attrs[constants.UDT_LOT_KEY]), 8)
            present |= set(attrs)
        self.assertTrue(set(BUILDING_KEYS) - {"DEMOL_DAY"} <= present, sorted(set(BUILDING_KEYS) - present))   # DEMOL_DAY는 v1 항상 빈 값
        attrs = self._user_strings(buildings[0])
        self.assertGreater(float(attrs["HEIGHT_M"]), 0.0)
        self.assertIn(attrs["HEIGHT_GRADE"], constants.HEIGHT_GRADES)

    def _origin_attrs(self):
        ref = [o for o in self.by_layer.get(constants.CTX_ROOT_LAYER + "::Ref", []) if o.Attributes.Name == "origin"]
        self.assertEqual(len(ref), 1)
        return self._user_strings(ref[0])

    def test_ref_origin_user_strings(self):
        attrs = self._origin_attrs()
        self.assertTrue(set(attrs) <= set(REF_KEYS) | MANAGED_KEYS, sorted(set(attrs) - set(REF_KEYS) - MANAGED_KEYS))
        self.assertTrue(set(REF_KEYS_REQUIRED) <= set(attrs), sorted(set(REF_KEYS_REQUIRED) - set(attrs)))
        self.assertEqual(attrs["CRS"], "EPSG:%d" % constants.DATABASE_CRS)
        self.assertEqual(len(attrs["META_LINES"].split("\n")), 5)
        origin = (float(attrs["ORIGIN_E"]), float(attrs["ORIGIN_N"]))
        self.assertEqual(origin, (origin[0] // constants.ORIGIN_SNAP * constants.ORIGIN_SNAP, origin[1] // constants.ORIGIN_SNAP * constants.ORIGIN_SNAP))
        if self.response:
            self.assertEqual(list(origin), self.response["context"]["origin"])

    def test_doc_strings_origin(self):
        """doc.Strings URBANSITE_ORIGIN_E/N이 사본에 있으면 Ref 원점과 같아야 한다.
        실측(job 1007-223545-f01e): WriteSelectedObjectsOnly 사본에는 문서 문자열이 안 들어온다 → context_baker.save_copy 과제(open point)."""
        strings = self.model.Strings
        if not len(strings):
            self.skipTest("사본에 doc.Strings 없음 — context_baker.save_copy(WriteSelectedObjectsOnly)가 문서 문자열을 쓰지 않는다")
        attrs = self._origin_attrs()
        self.assertEqual((float(strings[constants.DOC_ORIGIN_KEYS[0]]), float(strings[constants.DOC_ORIGIN_KEYS[1]])),
                         (float(attrs["ORIGIN_E"]), float(attrs["ORIGIN_N"])))
        self.assertEqual(strings[constants.DOC_ORIGIN_KEYS[2]], "EPSG:%d" % constants.DATABASE_CRS)


if __name__ == "__main__":
    unittest.main()
