"""driver_real_site — 전체 DB(서울)로 실제 대상지를 생성해 저장소 result/ 에 산출물을 남긴다 (python3 scripts/dev_rhino_run.py tests/rhino/driver_real_site.py).

fixture가 아니라 data/seoul_site.db·seoul_context.db(심링크)를 쓴다. 결과 폴더는 저장소 result/<날짜>/<대상지>/ (사용자가 Illustrator·Rhino로 열어 보는 용도).
문서는 끝에 원상 복구한다(베이크 객체·레이어 삭제, 원점 문자열 복구). 전역 PNUS·RADIUS·SCALES 로 바꿔 쓴다.
"""
import json
import os
import time

import Rhino

import constants
import context_baker
import context_builder

PNUS = [constants.TEST_CONTEXT_PNU]
RADIUS = 500
SCALES = [3000]
RESULT_ROOT = "/Users/sanghoon/Documents/GitHub/UrbanDesignTool/result"

# 항상 헤드리스 문서(mm)에서 돈다 — 사용자가 열어 둔 문서를 건드리지 않는다(2026-10-10: 사용자 문서가 '실제 좌표' 방식이라 섞일 뻔했다)
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
request = {"pnus": PNUS, "result_root": RESULT_ROOT,
           "options": {"radius": RADIUS, "scales": SCALES, "make_basemap": True, "make_sheets": True, "make_tables": True}}
lot_key = context_baker.get_lot_key(PNUS)
had_origin = context_baker.get_doc_origin(doc)
t0 = time.time()


def progress(phase, fraction, text):
    print("progress %-9s %.2f %6.2fs %s" % (phase, fraction, time.time() - t0, text))
    return True


try:
    response = context_builder.run(request, progress, doc)
    print(json.dumps({k: response[k] for k in ("ok", "dir", "elapsed_s", "context", "basemap", "error")}, ensure_ascii=False, indent=1, default=str))
    print("quality", json.dumps(response["quality"], ensure_ascii=False, default=str))
    print("warnings", json.dumps(response["warnings"], ensure_ascii=False, default=str))
    print("sheets", [(s["id"], s["empty"], s["reason"]) for s in response["sheets"]])
    with open(os.path.join(OUT_DIR, "response.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(response, f, ensure_ascii=False, indent=1, default=str)
finally:
    deleted, layers = context_baker.clear_previous(doc, lot_key)
    if had_origin is None:
        for key in constants.DOC_ORIGIN_KEYS:
            doc.Strings.Delete(key)
        doc.EarthAnchorPoint = Rhino.DocObjects.EarthAnchorPoint()
    doc.Views.Redraw()
    print("cleanup objects %d layers %d origin_restored %s" % (deleted, layers, context_baker.get_doc_origin(doc) == had_origin))
