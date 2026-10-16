# 지형 드라이버 — fixture로 prepare(333-139, R=500) → build_terrain: 시간·면 수·IsValid·Z 범위·정밀도·압출 방향·1 km 분류 시간.
# python3 scripts/dev_rhino_run.py tests/rhino/driver_terrain.py → result/rhino_jobs/<id>/out/log.txt·terrain.json. 문서에 아무것도 베이크하지 않는다.
import json
import os
import time

import Rhino.Geometry as rg

import constants
import context_builder
import context_geometry
import context_report
import non_rhino_utils

FIXTURES = os.path.join(JOB_DIR, "tests", "fixtures")   # noqa: F821 — dev_rhino_run 전역


def get_request(radius):
    return {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": os.path.join(FIXTURES, "seongsu_site.db"),
            "context_db": os.path.join(FIXTURES, "seongsu_context.db"), "options": {"radius": radius, "shape": "buffer"}}


result = {}
t = time.time()
prepared = context_builder.prepare(get_request(500))
result["prepare_s"] = round(time.time() - t, 2)
print("prepare %.2fs origin %s buildings %d features %d" % (result["prepare_s"], prepared.origin, len(prepared.buildings), len(prepared.features)))

t = time.time()
meshes, tris, counts = context_geometry.build_terrain(prepared)
result["build_terrain_s"] = round(time.time() - t, 2)
result["counts"] = counts
tin = meshes["all"]
bbox = tin.GetBoundingBox(True)
result["tin"] = {"vertices": tin.Vertices.Count, "faces": tin.Faces.Count, "valid": tin.IsValid, "z": [round(bbox.Min.Z, 2), round(bbox.Max.Z, 2)],
                 "double": tin.Vertices.UseDoublePrecisionVertices}
for cls, mesh in meshes.items():
    b = mesh.GetBoundingBox(True)
    result.setdefault("meshes", {})[cls] = {"faces": mesh.Faces.Count, "valid": mesh.IsValid, "z": [round(b.Min.Z, 2), round(b.Max.Z, 2)]}
print(json.dumps(result, ensure_ascii=False, indent=1, default=str))
assert tin.IsValid, "TIN IsValid False"
assert 0.0 < bbox.Min.Z and bbox.Max.Z < 100.0, "Z 범위 이상 %s" % result["tin"]["z"]   # 성수 fixture 실측 4.2(중랑천 하상 표고점)~19.7
assert sum(1 for tri in tris if tri[3] != "outside") > 3000, "범위 안 면이 너무 적다"   # 시트용 = TIN 삼각형

# 쿼드 위주 메시(2026-10-10) — 영역 경계는 원래 선(범위 면적 = 링 면적), 안쪽 쿼드, 정점 Z = TIN 투영(1 mm, 수면 제외)
terrain = meshes["terrain"]
result["mesh"] = {"faces": terrain.Faces.Count, "quads": terrain.Faces.QuadCount, "edge": counts["mesh_edge"], "regions": counts["regions"],
                  "split_s": counts["split_s"], "drape_s": counts["drape_s"]}
assert terrain.Faces.QuadCount >= 0.5 * terrain.Faces.Count, "쿼드 비율 %s" % result["mesh"]
plan_area = sum(rg.AreaMassProperties.Compute(m).Area for k, m in meshes.items() if k in ("terrain", "road", "green", "rail", "water"))
ring_area = non_rhino_utils.get_ring_area(prepared.extent_ring)
result["mesh"]["area_ratio"] = round(plan_area / ring_area, 4)
assert 0.999 < plan_area / ring_area < 1.01, "범위 면적 비 %.4f(경사로 약간 큼)" % (plan_area / ring_area)
points, water_polys, _ = context_geometry.get_tin_points(prepared)
from System.Collections.Generic import List
tin = rg.Mesh.CreateFromTessellation(context_geometry.get_local_pts(points, prepared.origin), List[List[rg.Point3d]](), rg.Plane.WorldXY, False)
verts = terrain.Vertices.ToPoint3dArray()
sample = [verts[k] for k in range(0, len(verts), 97)]
out, idx = context_geometry._project_to_mesh(tin, [rg.Point3d(v.X, v.Y, 1e4) for v in sample])
worst = max(abs(pt.Z - sample[k].Z) for pt, k in zip(out, idx))
result["precision"] = {"worst_mm": round(worst * 1000, 3), "sampled": len(sample)}
print("mesh", result["mesh"], "precision", result["precision"])
assert worst <= 0.001, "정점 Z − TIN %.4f m" % worst

# 압출 방향 — 샘플 발자국 10동, 평면 오버로드 Extrusion.Create → Max.Z ≈ base_z + h
checked = 0
for b in context_report.get_buildings_in_extent(prepared)[:10]:
    parts = context_geometry.get_parts(b.geometry)
    base_z, h = 12.0, float(b.height_m)
    crv = context_geometry._get_ring_crv(parts[0][0], prepared.origin, base_z)
    ext = rg.Extrusion.Create(crv, rg.Plane(rg.Point3d(0, 0, base_z), rg.Vector3d.ZAxis), h, True)
    assert ext is not None, "압출 실패 %s" % b.building_id
    eb = ext.GetBoundingBox(True)
    assert abs(eb.Max.Z - (base_z + h)) < 0.001 and abs(eb.Min.Z - base_z) < 0.001, "압출 방향 %s: %s~%s (h %s, 링 방향 %d)" % (
        b.building_id, eb.Min.Z, eb.Max.Z, h, non_rhino_utils.get_ring_orientation(parts[0][0]))
    checked += 1
result["extrusion_direction_ok"] = checked
print("extrusion direction ok for", checked)

# 1 km — 분류 시간 기록 (목표 ≤ 1 s)
t = time.time()
prepared_1km = context_builder.prepare(get_request(1000))
prep_1km = round(time.time() - t, 2)
t = time.time()
meshes_1km, tris_1km, counts_1km = context_geometry.build_terrain(prepared_1km)
result["km1"] = {"prepare_s": prep_1km, "build_terrain_s": round(time.time() - t, 2), "classify_s": counts_1km["classify_s"],
                 "tin_s": counts_1km["tin_s"], "faces": counts_1km["faces"], "tin_points": counts_1km["tin_points"],
                 "faces_by_class": counts_1km["faces_by_class"], "valid": meshes_1km["all"].IsValid}
print("1km", json.dumps(result["km1"], ensure_ascii=False, default=str))

with open(os.path.join(OUT_DIR, "terrain.json"), "w", encoding="utf-8") as f:   # noqa: F821
    json.dump(result, f, ensure_ascii=False, indent=1, default=str)
print("OK")
