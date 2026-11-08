"""driver_site_line — 대상지는 면(CTX::Site::ground)으로 보이고, 선(Site·Zoning·필지·도로 중심선)은 Z=0 평면선 (python3 scripts/dev_rhino_run.py tests/rhino/driver_site_line.py).

2026-11-07 사용자: 3D 설정 대상지 [Line]이면 Z=0 커브만 있고 지형 위에는 선이 안 보였다(해발 지형이 14~70 m라 Z=0 선은 지형 안에 묻힌다).
→ 2026-11-08 지형에 얹은 복사본(Site::draped)은 없애고, 면 생성(CTX::Site::ground)을 기본으로 했다. 대상지 안쪽이 보이는 면으로 다 덮여야 한다.
~/Gorani/data의 성동구 팩으로 금호동3가 450 외 1을 두 설정으로 만든다 — 매끈 / 계단 2 m + 평평하게. 옵션으로 site_output을 주지 않는다.
CTX::Site·Zoning·Site::lots(합필 전 필지)·Parcels·Roads::centerline은 Z=0 평면 선이다. 헤드리스 문서, 결과: OUT_DIR/result.json.
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


def interior_coverage(site_curve, meshes, n=18):
    """대상지 안쪽 격자점(n×n 중 경계 안)을 보이는 면에 수직 투영 → (점 수, 맞은 점 수). 맞은 수 < 점 수면 안쪽이 비어 보인다."""
    box = site_curve.GetBoundingBox(True)
    pts = []
    for i in range(n):
        for j in range(n):
            x = box.Min.X + (i + 0.5) / n * (box.Max.X - box.Min.X)
            y = box.Min.Y + (j + 0.5) / n * (box.Max.Y - box.Min.Y)
            if site_curve.Contains(rg.Point3d(x, y, 0), rg.Plane.WorldXY, 0.001) == rg.PointContainment.Inside:
                pts.append(rg.Point3d(x, y, 1e4))
    joined = rg.Mesh()
    for m in meshes:
        joined.Append(m)
    out, idx = Intersect.Intersection.ProjectPointsToMeshesEx([joined], pts, rg.Vector3d(0, 0, -1), 0.001)
    return len(pts), len(set(idx))


# site_output은 주지 않는다 — 패널에서 [Line]·[Surface] 선택을 없애고 면 생성을 기본값으로 했다(2026-11-08). 엔진 기본값이 mesh여야 한다
cases = [("매끈", {"terrain_step": 0}), ("계단 1 m", {"terrain_step": 1}),
         ("계단 2 m·평평하게", {"terrain_step": 2, "flatten_site": True})]
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
    # ① 대상지 경계 CTX::Site·용도지역 선은 Z=0 평면선
    flat_site = curves_on(lambda p: p == "CTX::Site")
    # 면 생성이 기본 — 대상지 바닥 면(Site::ground)이 있고, 대상지 안쪽이 보이는 면으로 다 덮인다(안쪽이 비어 보이지 않는다)
    ground_faces = [g for p, g in objs if p == "CTX::Site::ground" and isinstance(g, rg.Mesh)]
    total, hit = interior_coverage(flat_site[0], surfaces) if flat_site else (0, 0)
    row["Site::ground"] = {"meshes": len(ground_faces), "interior_pts": total, "interior_hit": hit}
    # 면 출력(평평하게 끔) — 대상지 안 지형·녹지만 대상지 면, 도로·철도·수면은 그대로, 원래 지형·녹지는 꺼 둔 Site::original(2026-11-08)
    flattened = bool(extra.get("flatten_site"))
    if not flattened and flat_site:
        box = flat_site[0].GetBoundingBox(True)
        probe = []
        for i in range(24):
            for j in range(24):
                q = rg.Point3d(box.Min.X + (i + 0.5) / 24 * (box.Max.X - box.Min.X), box.Min.Y + (j + 0.5) / 24 * (box.Max.Y - box.Min.Y), 1e4)
                if flat_site[0].Contains(rg.Point3d(q.X, q.Y, 0), rg.Plane.WorldXY, 0.001) == rg.PointContainment.Inside:
                    probe.append(q)

        def hits(layers):   # 꺼 둔 레이어(Site::original)는 doc.Objects에 안 나온다 — 레이어로 찾는다
            joined = rg.Mesh()
            for path in layers:
                index = doc.Layers.FindByFullPath(path, -1)
                for o in (doc.Objects.FindByLayer(doc.Layers[index]) or []) if index >= 0 else []:
                    if isinstance(o.Geometry, rg.Mesh):
                        joined.Append(o.Geometry)
            if joined.Vertices.Count == 0:
                return set()
            _out, idx = Intersect.Intersection.ProjectPointsToMeshesEx([joined], probe, rg.Vector3d(0, 0, -1), 0.001)
            return set(idx)
        on_site = hits({"CTX::Site::ground"})
        on_cut = hits({"CTX::Terrain", "CTX::Green"})
        on_keep = hits({"CTX::Roads", "CTX::Rail", "CTX::Water"})
        on_orig = hits({"CTX::Site::original::Terrain", "CTX::Site::original::Green"})
        overlap = len(on_site & (on_cut | on_keep))
        cover = len(on_site | on_keep)
        ok_cut = overlap == 0 and cover == len(probe) and on_orig == on_site
        print("%-14s %-13s 안쪽 %d점 · 대상지 면 %d · 그대로(도로·철도·수면) %d · 겹침 %d · 원래 사본=대상지 면 %s  %s"
              % (name, "구멍·사본", len(probe), len(on_site), len(on_keep), overlap, on_orig == on_site, "PASS" if ok_cut else "FAIL"))
        if not ok_cut:
            failed.append("%s/구멍·사본" % name)
        row["cut"] = {"pts": len(probe), "site": len(on_site), "keep": len(on_keep), "overlap": overlap}
    ok = bool(ground_faces) and total > 50 and hit == total
    print("%-14s %-13s 면 %d개 · 안쪽 %d점 중 %d점 덮임  %s" % (name, "Site::ground", len(ground_faces), total, hit, "PASS" if ok else "FAIL"))
    if not ok:
        failed.append("%s/Site::ground" % name)
    for label, curves in (("Site 평면", flat_site), ("Zoning 평면", curves_on(lambda p: p.startswith("CTX::Zoning")))):
        zr = z_range(curves)
        ok = bool(curves) and zr == (0.0, 0.0)
        row[label] = {"curves": len(curves), "z_range": zr}
        print("%-14s %-13s 선 %3d개 · Z %s  %s" % (name, label, len(curves), zr, "PASS" if ok else "FAIL"))
        if not ok:
            failed.append("%s/%s" % (name, label))
    draped = [p for p, g in objs if p == "CTX::Site::draped"]   # 지형에 얹은 복사본은 없앴다(2026-11-08)
    print("%-14s Site::draped 없음 %s" % (name, "PASS" if not draped else "FAIL %d개" % len(draped)))
    if draped:
        failed.append("%s/draped" % name)
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
