"""driver_street_detail — 인도·연석·철도·노면표시(2026-11-08)·교량 상판(2026-11-13)을 Rhino 8 전체 실행으로 확인한다.
python3 scripts/dev_rhino_run.py tests/rhino/driver_street_detail.py → out/log.txt·result.json·<이름>.3dm.

헤드리스 문서(m)에서 context_builder.run — 성수 2호선 철교(상판·선로)·성수 교차로(인도·노면표시)·동호대교 북단(도로·철교 상판, 상판 위 차선), 동호대교는 Brep 출력도.
data/에 시군구 팩(11200 등 _context·_terrain)과 노면표시만 든 seoul_context.db(dev_context_builder.py --markings --out)가 있어야 한다. 사용자 문서는 건드리지 않는다.
"""
import json
import os
import time

import Rhino

import context_baker
import context_builder

DATA_DIR = os.path.join(JOB_DIR, "data")   # noqa: F821 — dev_rhino_run 머리말 전역
ALL = {"detail_fences": True, "building_parapet": True, "building_floors": True}   # 기본 끔인 디테일까지 켠다
SITES = [("seongsu_rail", (205500.0, 549250.0), 250, "mesh", {}), ("seongsu", (205670.0, 549190.0), 150, "mesh", ALL),
         ("dongho", (201750.0, 548850.0), 300, "mesh", {}), ("dongho_brep", (201750.0, 548850.0), 200, "brep", ALL),
         ("seongbuk", (200850.0, 555450.0), 200, "mesh", ALL), ("seongsu_off", (205670.0, 549190.0), 150, "mesh", {k: False for k in (
             "detail_curb", "detail_markings", "detail_rail", "detail_bridges", "detail_walls", "detail_trees")})]
EXPECT = {"seongsu_rail": ("CTX::Bridges::deck", "CTX::Bridges::pier", "CTX::Bridges::parapet", "CTX::Rail::rails", "CTX::Rail::ballast"),
          "seongsu": ("CTX::Roads::curb", "CTX::Roads::sidewalk", "CTX::Roads::marking_white", "CTX::Roads::marking_yellow"),
          "dongho": ("CTX::Bridges::deck", "CTX::Bridges::pier", "CTX::Rail::rails", "CTX::Roads::marking_white"),
          "dongho_brep": ("CTX::Bridges::deck", "CTX::Buildings::parapet"),
          "seongbuk": ("CTX::Walls::retaining", "CTX::Walls::fence", "CTX::Buildings::floors"),
          "seongsu_off": ()}
ABSENT = {"seongsu": (), "seongsu_off": ("CTX::Roads::curb", "CTX::Roads::marking_white", "CTX::Rail::rails", "CTX::Bridges::deck", "CTX::Trees")}   # 끈 디테일은 없어야 한다
EXPECT["seongsu"] = EXPECT["seongsu"] + ("CTX::Trees", "CTX::Buildings::parapet", "CTX::Buildings::floors")
res = {}
for name, center, radius, geometry_type, extra in SITES:
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    doc.ModelUnitSystem = Rhino.UnitSystem.Meters
    request = {"target": {"mode": "point", "center": list(center)}, "site_db": os.path.join(DATA_DIR, "seoul_site.db"),
               "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821 — 컨텍스트는 data/의 팩
               "options": {"output_lang": "en", "radius": radius, "shape": "rect", "make_basemap": False, "make_sheets": False, "make_tables": False,
                           "terrain_block": True, "geometry_type": geometry_type, **extra}}
    t = time.time()
    response = context_builder.run(request, lambda phase, fraction, text: True, doc, {})
    layers, invalid = {}, []
    for ro in context_baker._get_objects(doc):
        path = doc.Layers[ro.Attributes.LayerIndex].FullPath
        layers[path] = layers.get(path, 0) + 1
        if not ro.Geometry.IsValid:
            invalid.append(path)
    curb_h = sorted({ro.Attributes.GetUserString("HEIGHT_M") for ro in context_baker._get_objects(doc)
                     if doc.Layers[ro.Attributes.LayerIndex].FullPath == "CTX::Roads::curb"})
    missing = [layer for layer in EXPECT[name] if not layers.get(layer)] + ["not off: " + layer for layer in ABSENT.get(name, ()) if layers.get(layer)]
    res[name] = {"ok": response["ok"], "elapsed_s": round(time.time() - t, 1), "error": response.get("error"), "missing": missing, "invalid": sorted(set(invalid)),
                 "curb_height": curb_h, "layers": {k: v for k, v in sorted(layers.items()) if any(t in k for t in ("Roads", "Rail", "Bridges", "Walls", "Trees", "Buildings::"))},
                 "counts": {k: (response.get("context") or {}).get("counts", {}).get(k) for k in ("curb_faces", "rail_tracks", "rail_track_m", "rail_platforms",
                                                                                               "marking_lines", "crosswalks", "brep_failed",
                                                                                               "bridge_decks", "bridge_spot_decks", "bridge_piers", "trees", "wall_lines",
                                                                                               "fence_lines", "parapet_faces", "floor_lines")}}
    print(name, json.dumps(res[name], ensure_ascii=False, default=str))
    model = (response.get("context") or {}).get("model_path") or os.path.join(response.get("dir") or "", "context.3dm")
    print(" 3dm", model, os.path.exists(model))
    doc.Dispose()
with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
# 필지 커브 무효는 공공 지적 원천(겹친 꼭짓점) — 이 드라이버가 보는 가로·교량과 무관해 따로 적기만 한다(성수 2호선 R=250, 2026-11-13)
bad = {k: v for k, v in res.items() if not v["ok"] or v["missing"] or [layer for layer in v["invalid"] if layer != "CTX::Parcels"]}
assert not bad, json.dumps(bad, ensure_ascii=False, default=str)
print("PASS street detail")
