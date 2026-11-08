"""driver_recent_results — 최근 결과(PR #53)와 지형 바닥 채우기(#38)를 Rhino 안(CPython 3.9)에서 실제 데이터로 (python3 scripts/dev_rhino_run.py tests/rhino/driver_recent_results.py).

~/Gorani/data의 시군구 팩(성동구)으로 금호동3가 450 외 1을 만든다 → 단언:
  ① 생성 ok, 지형 덩어리 레이어 CTX::Terrain::block에 객체(BASE_M UserString), 범위 경계로 자른 건물 수
  ② context_baker.has_lot — 구운 뒤 True, clear_previous 뒤 False (지난 결과의 [불러오기] 숨김 근거)
  ③ get_recent_results가 이 결과를 찾고, get_result_state의 대상지(PNU)·경위도가 맞다
  ④ make_2d → made_2d.json, 결과 폴더·2D 폴더 이름을 바꿔도 get_result_state의 2D 카드 경로가 지금 위치
문서는 헤드리스(사용자 문서를 건드리지 않는다). 결과: OUT_DIR/result.json.
"""
import json
import os
import sys
import time

import Rhino

import constants
import context_baker
import context_builder
import data_pack
import non_rhino_utils

DATA_DIR = os.path.join(os.path.expanduser("~"), "Gorani", "data")
PNUS = ["1120011100104500000", "1120011100104490000"]   # 금호동3가 450 외 1 (2026-11-06 사용자 결과와 같은 대상지)
data_pack.get_data_dir = lambda *a, **k: DATA_DIR   # 저장소 data/가 없다 — 설치본 팩 폴더

doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
res = {"python": sys.version.split()[0], "rhino": str(Rhino.RhinoApp.Version), "checks": {}}
result_root = os.path.join(OUT_DIR, "result")   # noqa: F821 — dev_rhino_run 머리말 전역
t0 = time.time()


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": str(detail)}
    print("%-34s %s %s" % (name, "PASS" if ok else "FAIL", detail))


lot_key = context_baker.get_lot_key(PNUS)
try:
    request = {"target": {"mode": "lots", "pnus": PNUS}, "result_root": result_root,
               "options": {"radius": 250, "shape": "rect", "terrain_block": True, "site_output": "mesh", "make_basemap": False, "make_sheets": False,
                           "make_tables": False, "output_lang": "ko"}}
    response = context_builder.run(request, lambda *a: True, doc)
    check("생성 ok", response["ok"], (response.get("error") or {}).get("title", "%.1fs" % response["elapsed_s"]))
    result_dir = response["dir"]
    res["dir"] = result_dir

    # ① 지형 덩어리
    def layer_path(o):
        return doc.Layers[o.Attributes.LayerIndex].FullPath
    block = [o for o in doc.Objects if layer_path(o) == "CTX::Terrain::block"]
    check("지형 덩어리 객체", len(block) > 0, "%d개" % len(block))
    check("BASE_M UserString", all(o.Attributes.GetUserString("BASE_M") for o in block[:1]) if block else False,
          block[0].Attributes.GetUserString("BASE_M") if block else "")
    check("건물 수", (response["context"].get("buildings") or 0) > 0, response["context"].get("buildings"))

    # ② 문서에 있나
    check("has_lot 구운 뒤 True", context_baker.has_lot(doc, lot_key))
    context_baker.clear_previous(doc, lot_key)
    check("has_lot 지운 뒤 False", not context_baker.has_lot(doc, lot_key))
    check("has_lot 빈 키 False", not context_baker.has_lot(doc, ""))

    # ③ 최근 결과·지난 결과 상태
    recent = context_builder.get_recent_results(result_root, model_name="context.3dm")
    check("최근 결과에 든다", any(r["dir"] == result_dir for r in recent), [r["label"] for r in recent][:2])
    state = context_builder.get_result_state(result_dir, "context.3dm")
    check("대상지 PNU 복원", state["target"].get("pnus") == PNUS, state["target"].get("pnus"))
    lng, lat = state["target_lnglat"]["center"]
    check("경위도 성동구 안", 127.0 < lng < 127.1 and 37.5 < lat < 37.6, "%.5f, %.5f" % (lng, lat))
    check("lot_key 일치", state.get("lot_key") == lot_key, state.get("lot_key"))

    # ④ 2D 만들기 → made_2d.json → 이름을 바꿔도
    two = context_builder.make_2d(result_dir, {"make_sheets": True, "sheet_ids": [9], "output_lang": "ko"}, lambda *a: True)
    check("make_2d ok", two["ok"], (two.get("error") or {}).get("title", "도면 %d장" % len(two["sheets"])))
    check("made_2d.json 있음", os.path.exists(os.path.join(two["folder"], constants.MADE_2D_FILE_NAME)))
    new_dir = result_dir + "_이름변경"
    os.rename(result_dir, new_dir)
    renamed = os.path.join(new_dir, os.path.basename(two["folder"]))
    os.rename(renamed, os.path.join(new_dir, "우리팀_납품본"))
    st2 = context_builder.get_result_state(new_dir, "context.3dm")
    card = [x for x in st2["made2d_list"] if x["made2d"]][-1]["made2d"]
    check("이름 바꾼 2D 폴더를 찾음", os.path.basename(st2["made2d_list"][-1]["dir"]) == "우리팀_납품본", [os.path.basename(x["dir"]) for x in st2["made2d_list"]])
    check("카드 도면 경로가 지금 위치", card["sheets"] and os.path.exists(card["sheets"][0]["path"]) and new_dir in card["sheets"][0]["path"],
          card["sheets"][0]["path"][-48:] if card["sheets"] else "도면 없음")
    check("투영 원점 되돌림", non_rhino_utils.get_crs_label() == "EPSG:5186", non_rhino_utils.get_crs_label())
finally:
    context_baker.clear_previous(doc, lot_key)
    res["elapsed_s"] = round(time.time() - t0, 1)
    failed = [k for k, v in res["checks"].items() if not v["ok"]]
    res["failed"] = failed
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("python %s · Rhino %s · %.1fs · %d개 중 실패 %d" % (res["python"], res["rhino"], res["elapsed_s"], len(res["checks"]), len(failed)))
assert not failed, failed
