"""driver_terrain_teeth — 매끈 지형에 톱니(거의 수직인 면)가 생기는 자리를 센다 (python3 scripts/dev_rhino_run.py tests/rhino/driver_terrain_teeth.py).

2026-11-08 사용자: 3D 지형 [매끈하게]인데 물가 지형 끝이 톱니처럼 깨지고, 계단도 마찬가지(죽림리 301-3 구역·번암리 215-11 구역).
~/Gorani/result의 그 결과(context.json의 target·options)로 다시 만들고, 레이어마다 법선 Z < 0.3인 면 수·그 면들의 높이 차를 낸다.
매끈이면 지형 덩어리(Terrain::block)·대상지 벽 말고는 수직 면이 없어야 한다. 헤드리스 문서, 결과: OUT_DIR/result.json.
"""
import json
import os

import Rhino
import Rhino.Geometry as rg

import context_builder
import data_pack

HOME = os.path.join(os.path.expanduser("~"), "Gorani")
data_pack.get_data_dir = lambda *a, **k: os.path.join(HOME, "data")
RESULT = os.environ.get("TEETH_RESULT") or "죽림리_301-3_구역_20261108"
meta = json.load(open(os.path.join(HOME, "result", RESULT, "context.json"), encoding="utf-8"))
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Meters
res = {}
for step in (0, 1):
    options = dict(meta.get("options") or {}, terrain_step=step, make_basemap=False, make_sheets=False, make_tables=False, make_dwg=False)
    r = context_builder.run({"target": meta["target"], "result_root": os.path.join(OUT_DIR, "result"), "options": options}, lambda *a: True, doc)   # noqa: F821
    print("step", step, "ok", r["ok"], (r.get("error") or {}).get("title", ""))
    stats = {}
    for o in doc.Objects:
        g = o.Geometry
        if not isinstance(g, rg.Mesh):
            continue
        layer = doc.Layers[o.Attributes.LayerIndex].FullPath
        g.FaceNormals.ComputeFaceNormals()
        steep = [i for i in range(g.Faces.Count) if abs(g.FaceNormals[i].Z) < 0.3]
        if not steep:
            stats.setdefault(layer, [0, 0, 0.0])[1] += g.Faces.Count
            continue
        s = stats.setdefault(layer, [0, 0, 0.0])
        s[0] += len(steep)
        s[1] += g.Faces.Count
        for i in steep[:2000]:
            f = g.Faces[i]
            zs = [g.Vertices[k].Z for k in ((f.A, f.B, f.C, f.D) if f.IsQuad else (f.A, f.B, f.C))]
            s[2] = max(s[2], max(zs) - min(zs))
    for layer, (n, total, dz) in sorted(stats.items()):
        print("  %-28s 수직면 %6d / %7d  최대 높이차 %.2f m" % (layer, n, total, dz))
    res["step%d" % step] = stats
    res["step%d_counts" % step] = {k: v for k, v in (r.get("context") or {}).items() if k in ("water_walls", "water_bodies", "site_output", "drape_missing")}
    print("  counts", res["step%d_counts" % step])
    lot_key = context_builder.get_target_key(meta["target"])
    import context_baker
    context_baker.clear_previous(doc, lot_key)
with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
