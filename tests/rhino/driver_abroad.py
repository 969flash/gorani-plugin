"""driver_abroad — 해외 대상지(OSM) 전체 생성 (python3 scripts/dev_rhino_run.py tests/rhino/driver_abroad.py).

파리 에펠탑 위치 방식 R=300, 1:1000 → context_builder.run(인터넷 필요: Overpass·지형 타일) → 단언(ok·건물 수·3dm·시트·베이스맵 파일·문서 좌표계)
→ 투영 원점을 되돌린다. 결과: OUT_DIR/result.json + 산출물 복사.
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
    non_rhino_utils.set_projection(2.2945, 48.8584)
    x, y = non_rhino_utils.get_tm_from_wgs84(2.2945, 48.8584)
    request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
               "options": {"output_lang": "en", "radius": 300, "shape": "circle", "scales": [1000], "paper": "A3", "make_basemap": True, "make_sheets": True,
                           "make_tables": True}}
    t0 = time.time()

    def progress(phase, fraction, text):
        print("progress %-9s %.2f %6.2fs %s" % (phase, fraction, time.time() - t0, text))
        return True

    response = context_builder.run(request, progress, doc)
    res["response"] = response
    print(json.dumps({k: response[k] for k in ("ok", "elapsed_s", "context", "basemap", "error")}, ensure_ascii=False, indent=1, default=str))
    print("warnings", json.dumps([w["code"] for w in response["warnings"]], ensure_ascii=False))
    check("ok", response["ok"], str(response.get("error")))
    check("buildings", response["context"]["buildings"] > 50, str(response["context"]["buildings"]))
    check("crs", doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]).startswith("+proj=tmerc"), doc.Strings.GetValue(constants.DOC_ORIGIN_KEYS[2]))
    for name in (constants.CONTEXT_MODEL_FILE_NAME, constants.BASEMAP_FILE_FORMAT % 1000):
        path = os.path.join(response["dir"], name)
        check("file " + name, os.path.exists(path))
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(OUT_DIR, "abroad_" + name))   # noqa: F821 — test_3dm_readback(국내 기준)이 context.3dm만 읽는다
    sheets = [s for s in response["sheets"] if s.get("path")]
    check("sheets", len(sheets) >= 5, "%d장 · 빈 %s" % (len(sheets), [s["id"] for s in response["sheets"] if s.get("empty")]))
finally:
    non_rhino_utils.set_projection()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
