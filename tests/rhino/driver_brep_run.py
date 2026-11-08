# Brep 출력 전체 실행 — context_builder.run(geometry_type=brep, 333-139 사각형 500 m) → 헤드리스 문서에 불러오기까지. 단언: ok·imported·건물 Brep.
# python3 scripts/dev_rhino_run.py tests/rhino/driver_brep_run.py → out/log.txt·context_brep_run.3dm. 사용자 문서는 건드리지 않는다.
import os
import shutil
import time

import Rhino

import constants
import context_baker
import context_builder

FIXTURES = os.path.join(JOB_DIR, "tests", "fixtures")   # noqa: F821
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Meters
request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": os.path.join(FIXTURES, "seongsu_site.db"),
           "context_db": os.path.join(FIXTURES, "seongsu_context.db"), "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
           "options": {"output_lang": "en", "radius": 250, "shape": "rect", "site_output": "mesh", "geometry_type": "brep"}}
t0 = time.time()
response = context_builder.run(request, lambda phase, fraction, text: print("progress %-9s %.2f %6.2fs %s" % (phase, fraction, time.time() - t0, text)) or True, doc, {})
print("ok", response["ok"], "error", response["error"], "elapsed", response["elapsed_s"], "imported", response["context"]["imported"])
kinds = {}
for ro in context_baker._get_objects(doc):
    layer = doc.Layers[ro.Attributes.LayerIndex].FullPath
    kinds.setdefault(layer, set()).add(ro.ObjectType.ToString())
print({k: sorted(v) for k, v in kinds.items() if "Zoning" not in k})
path = response["context"]["path"]
shutil.copy2(path, os.path.join(OUT_DIR, "context_brep_run.3dm"))   # noqa: F821 — context.3dm이면 test_3dm_readback이 집는다
print("3dm MB", round(os.path.getsize(path) / 1e6, 1))
assert response["ok"] and response["context"]["imported"], response["error"]
assert kinds["CTX::Buildings"] == {"Brep"}, kinds["CTX::Buildings"]
assert kinds["CTX::Terrain"] == {"Brep"}, kinds["CTX::Terrain"]
doc.Dispose()
print("PASS")
