"""driver_site_line — 대상지 경계선(Site)·용도지역·지구(Zoning) 선이 Z=0이 아니라 지형 면 위에 있다 (python3 scripts/dev_rhino_run.py tests/rhino/driver_site_line.py).

2026-11-07 사용자: 3D 설정 대상지 [Line]이면 Z=0 커브만 있고 지형 위에는 선이 안 보였다(해발 지형이 14~70 m라 Z=0 선은 지형 안에 묻힌다).
→ 평면 Z=0 대상지 경계 CTX::Site는 그대로 두고(매싱·돌출용), 지형 위에 얹은 복사본 CTX::Site::draped를 더한다. 대상지만 올린다 — 용도지역·지구(Zoning)·필지·도로 중심선은 Z=0 그대로.
~/Gorani/data의 성동구 팩으로 금호동3가 450 외 1을 세 설정으로 만든다 — 매끈·경계선만 / 경계선 + 면 / 계단 2 m + 평평하게.
선 점마다 보이는 지형 면(지형·도로·녹지·수면·대상지 면)에 수직 투영한 가장 높은 Z와 비교해 0 ≤ 선 − 면 ≤ 0.35 m여야 한다.
범위 경계(특히 모서리) 위 점 몇 개(0.3 % 이하)는 투영이 빗나갈 수 있다 — 엔진이 안쪽으로 1 cm 밀어 다시 쏘고, 그래도 안 되면 같은 선의 가까운 점 높이로 채운다.
Zoning·Site::lots(합필 전 필지)·Parcels·Roads::centerline은 그대로 Z=0 평면 선이다(바꾸지 않았다). 헤드리스 문서, 결과: OUT_DIR/result.json.
"""
import json
import os
import time

import Rhino
import Rhino.Geometry as rg
from Rhino.Geometry import Intersect

import constants
import context_baker
import context_builder
import data_pack

data_pack.get_data_dir = lambda *a, **k: os.path.join(os.path.expanduser("~"), "Gorani", "data")
PNUS = ["1120011100104500000", "1120011100104490000"]   # 금호동3가 450 외 1 — 서울 지형 14.7~70.7 m
SURFACE_LAYERS = ("CTX::Terrain", "CTX::Roads", "CTX::Green", "CTX::Water", "CTX::Rail", "CTX::Site::ground")
res = {"cases": {}}
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Meters
lot_key = context_baker.get_lot_key(PNUS)


def layer_of(o):
    return doc.Layers[o.Attributes.LayerIndex].FullPath


def height_above_surface(curves, meshes):
    """curves의 점마다 (선 Z − 같은 XY의 보이는 면 Z) → (최소, 최대, 빗나간 점 수)."""
    joined = rg.Mesh()
    for m in meshes:
        joined.Append(m)
    pts, curve_z = [], []
    for c in curves:
        ok, pl = c.TryGetPolyline()
        for p in (pl if ok else []):
            pts.append(rg.Point3d(p.X, p.Y, 1e4))
            curve_z.append(p.Z)
    out, idx = Intersect.Intersection.ProjectPointsToMeshesEx([joined], pts, rg.Vector3d(0, 0, -1), 0.001)
    top = {}
    for pt, i in zip(out, idx):
        top[i] = max(top.get(i, -1e9), pt.Z)
    box = joined.GetBoundingBox(True)   # 범위 경계 위 점은 메시 가장자리라 빗나간다 — 안쪽으로 1 cm 밀어 다시(엔진과 같은 방법)
    cx, cy = (box.Min.X + box.Max.X) / 2.0, (box.Min.Y + box.Max.Y) / 2.0
    retry = [i for i in range(len(pts)) if i not in top]
    if retry:
        moved = []
        for i in retry:
            dx, dy = cx - pts[i].X, cy - pts[i].Y
            n = (dx * dx + dy * dy) ** 0.5 or 1.0
            moved.append(rg.Point3d(pts[i].X + dx / n * 0.01, pts[i].Y + dy / n * 0.01, 1e4))
        out2, idx2 = Intersect.Intersection.ProjectPointsToMeshesEx([joined], moved, rg.Vector3d(0, 0, -1), 0.001)
        for pt, j in zip(out2, idx2):
            top[retry[j]] = max(top.get(retry[j], -1e9), pt.Z)
    diffs = [curve_z[i] - top[i] for i in top]
    return (min(diffs), max(diffs), len(pts) - len(top)) if diffs else (None, None, len(pts))


cases = [("매끈·경계선만", {"terrain_step": 0, "site_output": "curve"}),
         ("경계선+면", {"terrain_step": 0, "site_output": "mesh"}),
         ("계단 2 m·평평하게", {"terrain_step": 2, "site_output": "mesh", "flatten_site": True})]
failed = []
for name, extra in cases:
    options = {"radius": 250, "shape": "rect", "make_basemap": False, "make_sheets": False, "make_tables": False}
    options.update(extra)
    t0 = time.time()
    r = context_builder.run({"target": {"mode": "lots", "pnus": PNUS}, "result_root": os.path.join(OUT_DIR, "result"), "options": options}, lambda *a: True, doc)   # noqa: F821
    elapsed = round(time.time() - t0, 1)
    objs = [(layer_of(o), o.Geometry) for o in doc.Objects]
    surfaces = [g for p, g in objs if p in SURFACE_LAYERS and isinstance(g, rg.Mesh)]
    row = {"ok": r["ok"], "elapsed_s": elapsed}
    def curves_on(match):
        return [g for p, g in objs if match(p) and isinstance(g, rg.PolylineCurve)]

    def z_range(curves):
        return (round(min(g.GetBoundingBox(True).Min.Z for g in curves), 2), round(max(g.GetBoundingBox(True).Max.Z for g in curves), 2)) if curves else None
    # ① 평면 대상지 경계 CTX::Site는 그대로 Z=0, 얹은 복사본 CTX::Site::draped만 지형 면 위(0.1 m). 용도지역 선은 Z=0 그대로(대상지만 올린다 — 사용자)
    flat_site = curves_on(lambda p: p == "CTX::Site")
    checks = [("Site 평면", flat_site, None), ("Site::draped", curves_on(lambda p: p == "CTX::Site::draped"), True),
              ("Zoning 평면", curves_on(lambda p: p.startswith("CTX::Zoning")), None)]
    for label, curves, on_surface in checks:
        if on_surface:
            lo, hi, miss = height_above_surface(curves, surfaces)
            n_pts = sum(g.PointCount for g in curves)
            ok = bool(curves) and lo is not None and lo >= -0.001 and hi <= 0.35 and miss <= 0.003 * n_pts   # 범위 모서리 몇 점은 투영이 빗나간다 — 엔진이 같은 선의 가까운 점 높이로 채운다
            if label == "Site::draped":
                ok = ok and len(curves) == len(flat_site)   # 평면 선마다 얹은 복사본이 하나
            row[label] = {"curves": len(curves), "above_min": None if lo is None else round(lo, 3), "above_max": None if hi is None else round(hi, 3), "missed": miss, "z_range": z_range(curves)}
            print("%-14s %-13s 선 %3d개 · 면 위 %.2f ~ %.2f m · 빗나감 %d · Z %s  %s" % (name, label, len(curves), lo if lo is not None else 0, hi if hi is not None else 0, miss, z_range(curves), "PASS" if ok else "FAIL"))
        else:
            zr = z_range(curves)
            ok = bool(curves) and zr == (0.0, 0.0)
            row[label] = {"curves": len(curves), "z_range": zr}
            print("%-14s %-13s 선 %3d개 · Z %s  %s" % (name, label, len(curves), zr, "PASS" if ok else "FAIL"))
        if not ok:
            failed.append("%s/%s" % (name, label))
    # ② 그대로 Z=0인 것 — 합필 전 필지(Site::lots)·필지·도로 중심선
    flat = curves_on(lambda p: p in ("CTX::Site::lots", "CTX::Parcels", "CTX::Roads::centerline"))
    zs = {round(g.GetBoundingBox(True).Min.Z, 3) for g in flat} | {round(g.GetBoundingBox(True).Max.Z, 3) for g in flat}
    row["flat_curves"] = {"n": len(flat), "z": sorted(zs)}
    print("%-14s Site::lots·필지·도로중심선 %d개 Z %s  %s" % (name, len(flat), sorted(zs), "PASS" if zs == {0.0} else "FAIL"))
    if zs != {0.0}:
        failed.append("%s/flat" % name)
    print("%-14s 생성 %.1f s" % (name, elapsed))
    res["cases"][name] = row
    context_baker.clear_previous(doc, lot_key)

res["failed"] = failed
with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
    json.dump(res, f, ensure_ascii=False, indent=1)
assert not failed, failed
