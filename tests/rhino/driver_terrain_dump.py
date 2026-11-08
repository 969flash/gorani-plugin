"""driver_terrain_dump — 지형 메시(매끈·계단 1 m)를 JSON으로 꺼낸다 — 계단 테두리 톱니 원인 찾기 (python3 scripts/dev_rhino_run.py tests/rhino/driver_terrain_dump.py).

2026-11-08 사용자: 물가는 나아졌는데 다른 지형의 계단 테두리가 여전히 삐죽삐죽(죽림리 301-3 구역).
context_geometry.build_terrain을 바로 불러 terrain·site_ground 메시와 TIN 입력점을 OUT_DIR/terrain_<step>.json으로 쓴다(문서에 굽지 않는다).
"""
import json
import os

import context_builder
import context_geometry
import data_pack

HOME = os.path.join(os.path.expanduser("~"), "Gorani")
data_pack.get_data_dir = lambda *a, **k: os.path.join(HOME, "data")
RESULT = os.environ.get("TEETH_RESULT") or "죽림리_301-3_구역_20261108"
meta = json.load(open(os.path.join(HOME, "result", RESULT, "context.json"), encoding="utf-8"))
for step in (0, 1):
    options = dict(meta.get("options") or {}, terrain_step=step, make_basemap=False, make_sheets=False, make_tables=False, make_dwg=False)
    prepared = context_builder.prepare({"target": meta["target"], "result_root": os.path.join(OUT_DIR, "result"), "options": options})   # noqa: F821
    meshes, tris, counts = context_geometry.build_terrain(prepared)
    out = {"origin": list(prepared.origin), "counts": {k: v for k, v in counts.items() if isinstance(v, (int, float, str))}, "meshes": {}}
    for cls in ("terrain", "site_ground", "road", "green"):
        if cls in meshes:
            v, f = context_geometry._get_mesh_faces(meshes[cls])
            out["meshes"][cls] = {"v": [[round(c, 3) for c in p] for p in v], "f": f}
    with open(os.path.join(OUT_DIR, "terrain_%d.json" % step), "w") as fh:   # noqa: F821
        json.dump(out, fh)
    print("step", step, {k: len(m["f"]) for k, m in out["meshes"].items()}, "mesh_edge", counts.get("mesh_edge"), "tin_points", counts.get("tin_points"))
