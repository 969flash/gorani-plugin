"""driver_switzerland — 알트도르프(Altdorf) 중심 위치 방식 R=300 (python3 scripts/dev_rhino_run.py tests/rhino/driver_netherlands.py).
네덜란드 팩(data/nl25gn1_context.db, dev_nl.py)의 PDOK 건물 + OSM 도로면 버퍼 + Terrain Tiles. 단언: ok·PDOK 건물·출처 줄·3dm·도면."""
import json
import os
import shutil
import time

import Rhino

import constants
import context_builder
import non_rhino_utils

doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
res = {"checks": {}}


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": detail}
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


try:
    non_rhino_utils.set_projection(8.6416, 46.8807)
    x, y = non_rhino_utils.get_tm_from_wgs84(8.6416, 46.8807)
    request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
               "options": {"region": "global", "radius": 300, "shape": "rect", "scales": [1000], "paper": "A3", "make_basemap": True,
                           "make_sheets": True, "sheet_ids": [0, 1, 15, 18], "make_tables": True, "output_lang": "en"}}
    t0 = time.time()

    def progress(phase, fraction, text):
        print("progress %-9s %.2f %6.2fs %s" % (phase, fraction, time.time() - t0, text))
        return True

    response = context_builder.run(request, progress, doc)
    res["response"] = {k: response[k] for k in ("ok", "elapsed_s", "context", "basemap", "error", "warnings")}
    print(json.dumps(res["response"], ensure_ascii=False, indent=1, default=str))
    check("ok", response["ok"], str(response.get("error")))
    check("buildings", response["context"]["buildings"] > 150, str(response["context"]["buildings"]))
    meta = json.load(open(os.path.join(response["dir"], constants.CONTEXT_META_FILE_NAME), encoding="utf-8"))
    lines = " ".join(meta.get("meta_lines") or [])
    check("swisstopo source", "swissBUILDINGS3D" in lines and "swisstopo" in lines, lines[:200])
    check("crs", doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]).startswith("+proj=tmerc"), doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]))
    model = os.path.join(response["dir"], constants.CONTEXT_MODEL_FILE_NAME)
    check("3dm", os.path.exists(model))
    if os.path.exists(model):
        shutil.copy2(model, os.path.join(OUT_DIR, "switzerland_" + constants.CONTEXT_MODEL_FILE_NAME))   # noqa: F821
    sheets = [s for s in response["sheets"] if s.get("path")]
    check("sheets", len(sheets) >= 3, "%d장" % len(sheets))
finally:
    non_rhino_utils.set_projection()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
