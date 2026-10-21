"""driver_japan — 일본 대상지(PLATEAU 건물 팩 + 지리원 지형 + OSM) 전체 생성 (python3 scripts/dev_rhino_run.py tests/rhino/driver_japan.py).

신주쿠역 위치 방식 R=300, 1:1000 → context_builder.run(인터넷 필요: Overpass·지리원 타일). 일본 팩은 data/의 jp<코드>_context.db를 쓴다
(dev_plateau.py build 뒤 xz를 풀어 data/에 두면 dev_rhino_run이 작업 폴더에 잇는다). 단언: ok·PLATEAU 건물·지리원 지형·3dm·문서 좌표계.
결과: OUT_DIR/result.json + context.3dm 사본.
"""
import json
import os
import shutil
import time

import Rhino

import constants
import context_builder
import non_rhino_utils

doc = Rhino.RhinoDoc.CreateHeadless(None)   # 사용자 문서를 건드리지 않는다
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
res = {"checks": {}}


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": detail}
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


try:
    non_rhino_utils.set_projection(139.7006, 35.6896)
    x, y = non_rhino_utils.get_tm_from_wgs84(139.7006, 35.6896)
    request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
               "options": {"region": "global", "radius": 300, "shape": "rect", "scales": [1000], "paper": "A3", "make_basemap": True,
                           "make_sheets": True, "sheet_ids": [0, 1, 15, 18], "make_tables": True}}
    t0 = time.time()

    def progress(phase, fraction, text):
        print("progress %-9s %.2f %6.2fs %s" % (phase, fraction, time.time() - t0, text))
        return True

    response = context_builder.run(request, progress, doc)
    res["response"] = {k: response[k] for k in ("ok", "elapsed_s", "context", "basemap", "error", "warnings")}
    print(json.dumps(res["response"], ensure_ascii=False, indent=1, default=str))
    check("ok", response["ok"], str(response.get("error")))
    check("buildings", response["context"]["buildings"] > 300, str(response["context"]["buildings"]))
    meta = json.load(open(os.path.join(response["dir"], constants.CONTEXT_META_FILE_NAME), encoding="utf-8"))
    lines = " ".join(meta.get("meta_lines") or [])
    check("plateau source", "PLATEAU" in lines, lines[:200])
    check("gsi terrain", "国土地理院" in lines)
    check("crs", doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]).startswith("+proj=tmerc"), doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]))
    model = os.path.join(response["dir"], constants.CONTEXT_MODEL_FILE_NAME)
    check("3dm", os.path.exists(model))
    if os.path.exists(model):
        shutil.copy2(model, os.path.join(OUT_DIR, "japan_" + constants.CONTEXT_MODEL_FILE_NAME))   # noqa: F821
    sheets = [s for s in response["sheets"] if s.get("path")]
    check("sheets", len(sheets) >= 3, "%d장" % len(sheets))
finally:
    non_rhino_utils.set_projection()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
