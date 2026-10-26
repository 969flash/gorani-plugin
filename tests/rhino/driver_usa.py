"""driver_usa — 윌밍턴(Wilmington, DE) 중심 위치 방식 R=300 (python3 scripts/dev_rhino_run.py tests/rhino/driver_usa.py).
미국 팩(data/us10003_context.db — dev_us.py, 뉴캐슬 카운티)의 Overture 건물 + OSM 도로면 버퍼 + Terrain Tiles.
나라 목록은 매니페스트 countries[]에서 오므로(data_pack.get_country_packs) 올리기 전에는 여기서 us 항목을 넣어 준다. 단언: ok·Overture 건물·출처 줄·3dm·도면."""
import json
import os
import shutil
import time

import Rhino

import constants
import context_builder
import data_pack
import non_rhino_utils

doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
res = {"checks": {}}


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": detail}
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


try:
    data_pack._MANIFEST[constants.DATA_MANIFEST_URL] = {"version": "driver", "packs": [], "countries": [
        {"code": "us", "label": "Overture", "source_id": "overture", "manifest": "us/manifest.json", "bounds": list(constants.US_BOUNDS), "code_pattern": r"\d{5}"}]}
    print("country:", data_pack.get_country_packs().get("us"))
    non_rhino_utils.set_projection(-75.5466, 39.7459)
    x, y = non_rhino_utils.get_tm_from_wgs84(-75.5466, 39.7459)
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
    check("overture source", "Overture" in lines, lines[:240])
    stats = response["context"].get("stats") or {}
    print("height_src:", stats.get("height_src"), "grade:", stats.get("height_grade"))
    check("crs", doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]).startswith("+proj=tmerc"), doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]))
    model = os.path.join(response["dir"], constants.CONTEXT_MODEL_FILE_NAME)
    check("3dm", os.path.exists(model))
    if os.path.exists(model):
        shutil.copy2(model, os.path.join(OUT_DIR, "usa_" + constants.CONTEXT_MODEL_FILE_NAME))   # noqa: F821
    sheets = [s for s in response["sheets"] if s.get("path")]
    check("sheets", len(sheets) >= 3, "%d장" % len(sheets))
finally:
    data_pack._MANIFEST.pop(constants.DATA_MANIFEST_URL, None)
    non_rhino_utils.set_projection()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
