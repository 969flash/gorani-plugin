"""driver_full_run — context_builder.run 전체 (python3 scripts/dev_rhino_run.py tests/rhino/driver_full_run.py).

fixture 주입 요청(333-139, R=500, scales [3000], 시트 전부, 표 전부) → run → response.json·context.3dm·context.json·basemap_3000.ai를 OUT_DIR로 복사
→ 단언(ok·건물 수·레이어 수·파일 존재·phase 순서·elapsed·basemap ready·basemap_3000.ai 용지 bbox·레이어 순서) → 두 번째 run은 write_3dm 중 취소(result_root를 OUT_DIR/result_cancel로 따로 줘
첫 run의 시트·CSV가 디스크에 남는다) → 문서에 베이크 객체 0 단언 → 끝에 clear_previous + doc.Strings 원점 복구(실행 전에 없었으면 삭제)로
문서를 원상 복구한다. 결과: OUT_DIR/result.json + log.txt, OUT_DIR/result/<날짜>/<대상지>/ 에 산출물 전부.
"""
import json
import os
import re
import shutil
import time

import Rhino

import constants
import context_baker
import context_builder

FIXTURE_DIR = os.path.join(JOB_DIR, "tests", "fixtures")   # noqa: F821 — dev_rhino_run 머리말 전역
# 항상 헤드리스 문서(mm)에서 돈다 — 사용자가 열어 둔 문서를 건드리지 않는다(2026-10-10: 사용자 문서가 '실제 좌표' 방식이라 섞일 뻔했다)
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
res = {"doc_unit": str(doc.ModelUnitSystem), "checks": {}}
request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": os.path.join(FIXTURE_DIR, "seongsu_site.db"),
           "context_db": os.path.join(FIXTURE_DIR, "seongsu_context.db"), "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
           "options": {"radius": 500, "scales": [3000], "make_basemap": True, "make_sheets": True, "make_tables": True, "make_dwg": True}}
lot_key = context_baker.get_lot_key(request["pnus"])
had_origin = context_baker.get_doc_origin(doc)


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": detail}
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


def count_baked():
    return sum(1 for ro in context_baker._get_objects(doc) if ro.Attributes.GetUserString(constants.UDT_LOT_KEY) == lot_key)


try:
    calls = []
    t0 = time.time()

    def progress(phase, fraction, text):
        calls.append([phase, round(fraction, 2), text, round(time.time() - t0, 2)])
        print("progress %-9s %.2f %6.2fs %s" % (phase, fraction, time.time() - t0, text))
        return True

    keep = {}
    response = context_builder.run(request, progress, doc, keep)
    res["response"] = response
    res["calls"] = calls
    with open(os.path.join(OUT_DIR, "response.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(response, f, ensure_ascii=False, indent=1, default=str)
    print(json.dumps({k: response[k] for k in ("ok", "elapsed_s", "context", "basemap", "error")}, ensure_ascii=False, indent=1, default=str))
    print("warnings", json.dumps(response["warnings"], ensure_ascii=False, default=str))
    for name in (constants.CONTEXT_MODEL_FILE_NAME, constants.CONTEXT_META_FILE_NAME, constants.BASEMAP_FILE_FORMAT % 3000, constants.RESULT_LOG_FILE_NAME):
        path = os.path.join(response["dir"], name)
        if os.path.exists(path):
            shutil.copy2(path, os.path.join(OUT_DIR, name))   # noqa: F821

    check("ok", response["ok"], str(response["error"]))
    check("imported", response["context"]["imported"])
    check("buildings", 2500 <= response["context"]["buildings"] <= 4000, str(response["context"]["buildings"]))   # 기본 형태 원(2026-10-10) 2,792 / 예전 버퍼 3,454
    check("layers", response["context"]["layers"] >= 7, str(response["context"]["layers"]))
    baked_layers = {doc.Layers[ro.Attributes.LayerIndex].FullPath for ro in context_baker._get_objects(doc)
                    if ro.Attributes.GetUserString(constants.UDT_LOT_KEY) == lot_key}
    check("centerline_layer", "CTX::Roads::centerline" in baked_layers, str(sorted(baked_layers)))
    check("baked_objects", count_baked() >= response["context"]["buildings"] + 2, str(count_baked()))   # CTX만(베이스맵은 basemap_ai가 .ai로 직접 — 문서에 안 굽는다)
    check("context_3dm", os.path.exists(response["context"]["path"]) and os.path.getsize(response["context"]["path"]) > 1_000_000,
          "%s %d bytes" % (response["context"]["path"], os.path.getsize(response["context"]["path"]) if os.path.exists(response["context"]["path"]) else -1))
    check("context_json", os.path.exists(os.path.join(response["dir"], constants.CONTEXT_META_FILE_NAME)))
    n_sheets = len(context_builder.get_sheet_ids(response["options"]))   # 기본 시트 = 틀(frame) 뺀 것(2026-10-19 패널 2화면, constants 기본 sheet_ids)
    check("sheets_all", len(response["sheets"]) == n_sheets and all(r["path"] and os.path.exists(r["path"]) for r in response["sheets"]),
          str([(r["id"], r["empty"], r["reason"]) for r in response["sheets"]]))
    # 도면 스타일 — 이번 run의 시트 데이터(지형 삼각형 포함)로 미리보기·적용(2026-10-13)
    preview = context_builder.preview_sheet(response["dir"], constants.SHEET_IDS["elev"], {"preset": "dark"}, keep)
    check("style_preview_terrain", not preview["empty"] and 'id="pv_map"' in preview["svg"], str(preview["reason"]))
    applied = context_builder.apply_style(response["dir"], {"preset": "mono", "layout": "bottom"}, keep)
    check("style_apply", len(applied["sheets"]) == n_sheets and applied["kept"] == [] and len(applied["basemaps"]) == 1,
          "%d sheets kept=%s basemaps=%s" % (len(applied["sheets"]), applied["kept"], applied["basemaps"]))
    check("tables_5", len(response["tables"]) == 5 and all(os.path.exists(t["path"]) for t in response["tables"]), str([t["name"] for t in response["tables"]]))
    check("files", {f["name"] for f in response["files"]} >= {constants.CONTEXT_MODEL_FILE_NAME, constants.CONTEXT_META_FILE_NAME, constants.RESULT_LOG_FILE_NAME},
          str(len(response["files"])))
    check("elapsed", 0.0 < response["elapsed_s"] < 120.0, str(response["elapsed_s"]))
    phases = []
    for c in calls:
        if not phases or phases[-1] != c[0]:
            phases.append(c[0])
    expected = [p for p in constants.PHASES if p not in ("refresh", "import") and (p != "basemap" or response["basemap"]["ready"])]
    check("phase_order", phases == expected, "%s vs %s" % (phases, expected))
    check("callback_fractions", all(c[1] <= n[1] or c[0] != n[0] for c, n in zip(calls, calls[1:])) and calls[-1][1] == 1.0, str(len(calls)))
    # 베이스맵 — basemap_ai가 직접 쓴 .ai: ready·존재·%%BoundingBox = 용지 pt·%AI5_ArtSize·레이어 순서(BM_LAYERS)·문서에 BM 객체 없음
    import re
    ai_path = os.path.join(context_builder.get_2d_dir(response["dir"]), constants.BASEMAP_FILE_FORMAT % 3000)   # 2D 산출물은 결과 폴더 안 2D/(2026-10-19)
    bm = response["basemap"]
    check("basemap_ready", bm["ready"] and bm["exported"] == [ai_path] and os.path.exists(ai_path), "ready=%s exported=%s" % (bm["ready"], bm["exported"]))
    ai_text = open(ai_path, encoding="ascii").read() if os.path.exists(ai_path) else ""
    res["ai_size_mb"] = round(len(ai_text) / 1048576.0, 2)
    paper_pt = [int(round(v * 72.0 / 25.4)) for v in response["options"]["paper_mm"]]
    check("basemap_bbox_paper", ("%%%%BoundingBox: 0 0 %d %d" % tuple(paper_pt)) in ai_text and ("%%AI5_ArtSize: %d %d" % tuple(paper_pt)) in ai_text,
          "%s pt, %.2f MB" % (paper_pt, res["ai_size_mb"]))
    ai_layers = re.findall(r"^\((\d\d[a-z_0-9]+)[^\n]*\) Ln$", ai_text, re.M)
    expected_order = [name for name, *_ in constants.BM_LAYERS if name in set(ai_layers)]
    check("basemap_ai_layer_order", ai_layers == expected_order and len(ai_layers) >= 14, "%s" % ai_layers)
    # 2D 도면(BM::) — 문서에 커브·텍스트로 들어가고 루트는 꺼져 있고(자식은 PersistentVisibility 유지), 사본 3dm에서도 꺼져 있다
    bm_objects = [ro for ro in context_baker._get_objects(doc) if ro.Attributes.GetUserString(constants.UDT_LOT_KEY) == lot_key
                  and doc.Layers[ro.Attributes.LayerIndex].FullPath.startswith("BM::")]
    bm_layers = {doc.Layers[ro.Attributes.LayerIndex].FullPath for ro in bm_objects}
    res["bm_objects"] = len(bm_objects)
    check("bm_in_doc", len(bm_objects) > 1000 and len(bm_layers) >= 10 and any(isinstance(ro, Rhino.DocObjects.TextObject) for ro in bm_objects),
          "%d objects %s" % (len(bm_objects), sorted(bm_layers)))
    bm_root = doc.Layers[doc.Layers.FindByFullPath(constants.BM_ROOT_LAYER, -1)]
    bm_children = [doc.Layers[doc.Layers.FindByFullPath(path, -1)] for path in bm_layers]
    check("bm_hidden_in_doc", not bm_root.IsVisible and not any(l.IsVisible for l in bm_children) and all(l.GetPersistentVisibility() for l in bm_children))
    bm_objects[0].Select(True)   # 숨김 객체는 선택되지 않아야 한다(= 화면에 안 보인다)
    check("bm_not_selectable", not bm_objects[0].IsSelected(False))
    dwg_path = response["context"]["dwg"]
    dwg_doc = Rhino.RhinoDoc.CreateHeadless(None)
    dwg_read = bool(dwg_path) and os.path.exists(dwg_path) and Rhino.FileIO.FileDwg.Read(dwg_path, dwg_doc, Rhino.FileIO.FileDwgReadOptions())
    dwg_count = dwg_doc.Objects.Count if dwg_read else -1
    dwg_doc.Dispose()
    check("dwg", dwg_read and dwg_path.endswith(constants.DWG_FILE_FORMAT % 3000) and dwg_count >= 0.95 * len(bm_objects),   # DWG 읽기가 퇴화 커브 몇 개를 버린다
          "%s objects %d vs bm %d" % (dwg_path, dwg_count, len(bm_objects)))
    file_layers = {l.FullPath: l for l in Rhino.FileIO.File3dm.Read(response["context"]["path"]).AllLayers}
    # 파일에는 자식이 '켜짐'(= PersistentVisibility)으로 남고 루트만 꺼진다 — 열면 Rhino가 자식을 숨긴다(OpenHeadless 확인, job 1012-224122-18be)
    check("bm_hidden_in_file", not file_layers[constants.BM_ROOT_LAYER].IsVisible and all(file_layers[path].GetPersistentVisibility() for path in bm_layers)
          and file_layers["CTX::Buildings"].IsVisible, str({k: v.IsVisible for k, v in file_layers.items() if k.startswith("BM")}))
    with open(os.path.join(response["dir"], constants.RESULT_LOG_FILE_NAME), encoding="utf-8") as f:
        log_text = f.read()
    check("save_timing_logged", re.search(r"context\.3dm .*bytes", log_text) is not None)   # 언어와 무관하게(로그는 패널 언어)
    check("basemap_logged", "basemap_3000.ai — " in log_text)
    check("doc_origin_written", context_baker.get_doc_origin(doc) == tuple(response["context"]["origin"]), str(context_baker.get_doc_origin(doc)))
    res["phase_seconds"] = {p: round(max(c[3] for c in calls if c[0] == p) - min(c[3] for c in calls if c[0] == p), 2) for p in phases}
    print("phase seconds", res["phase_seconds"])

    # 되읽기(Rhino 안 File3dm) — 사본 객체 수 = 베이크 수
    copy = Rhino.FileIO.File3dm.Read(response["context"]["path"])
    baked = count_baked()
    res["copy_objects"] = copy.Objects.Count if copy else -1
    check("copy_objects", copy is not None and copy.Objects.Count == baked, "%d vs baked %d" % (res["copy_objects"], baked))

    # 취소 — write_3dm 첫 청크 뒤 False → 베이크 객체 0, 폴더에 log 'cancelled at write_3dm'. result_root를 따로 줘 첫 run 산출물을 보존한다
    t1 = time.time()

    def cancelling(phase, fraction, text):
        return not (phase == "write_3dm" and fraction > 0.0)

    cancelled = context_builder.run(dict(request, result_root=os.path.join(OUT_DIR, "result_cancel"),   # noqa: F821
                                         options=dict(request["options"], make_basemap=False, make_sheets=False, make_tables=False)), cancelling, doc)
    res["cancel"] = {"ok": cancelled["ok"], "cancelled": cancelled["cancelled"], "error": cancelled["error"], "seconds": round(time.time() - t1, 2),
                     "baked_after": count_baked()}
    print("cancel", json.dumps(res["cancel"], ensure_ascii=False, default=str))
    check("cancel_response", (not cancelled["ok"]) and cancelled["cancelled"] and cancelled["error"]["code"] == "cancelled")
    check("cancel_rollback", count_baked() == 0, str(count_baked()))
    with open(os.path.join(cancelled["dir"], constants.RESULT_LOG_FILE_NAME), encoding="utf-8") as f:
        check("cancel_log", "cancelled at write_3dm" in f.read())
    check("first_run_kept", len(response["sheets"]) == n_sheets and all(os.path.exists(r["path"]) for r in response["sheets"])
          and all(os.path.exists(t["path"]) for t in response["tables"]) and os.path.exists(response["context"]["path"]))
finally:
    deleted, layers = context_baker.clear_previous(doc, lot_key)
    if had_origin is None:
        for key in constants.DOC_ORIGIN_KEYS:
            doc.Strings.Delete(key)
        doc.EarthAnchorPoint = Rhino.DocObjects.EarthAnchorPoint()
    res["cleanup"] = {"objects": deleted, "layers": layers, "origin_restored": context_baker.get_doc_origin(doc) == had_origin}
    check("cleanup", count_baked() == 0 and res["cleanup"]["origin_restored"], str(res["cleanup"]))
    doc.Views.Redraw()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    failed = [k for k, v in res["checks"].items() if not v["ok"]]
    print("ALL PASS" if not failed else "FAILED: %s" % failed)
    assert not failed, failed
