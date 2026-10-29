# 건물 드라이버 — fixture로 prepare(333-139, R=500) → build_terrain → build_buildings: 동 수(≈3,500)·실패 목록·
# ProjectPointsToMeshesEx len(indices)==len(out) 단언·폴백 ①② 수·Z 범위·UserString 14키. build_curves 수도 같이 기록.
# python3 scripts/dev_rhino_run.py tests/rhino/driver_buildings.py → out/log.txt·buildings.json. 문서에 아무것도 베이크하지 않는다.
import json
import os
import time

import Rhino.Geometry as rg

import constants
import context_builder
import context_geometry

FIXTURES = os.path.join(JOB_DIR, "tests", "fixtures")   # noqa: F821 — dev_rhino_run 전역
request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": os.path.join(FIXTURES, "seongsu_site.db"),
           "context_db": os.path.join(FIXTURES, "seongsu_context.db"), "options": {"radius": 500, "shape": "buffer"}}   # 기대 동 수(≈3,500)는 버퍼 범위 기준

result = {}
prepared = context_builder.prepare(request)
meshes, tris, t_counts = context_geometry.build_terrain(prepared)
tin = meshes["all"]

# 투영 단언 — 출력은 입력과 1:1이 아니지만 indices와는 1:1
pts = [rg.Point3d(0, 0, 500.0), rg.Point3d(10, 10, 500.0), rg.Point3d(99999.0, 99999.0, 500.0)]
out, indices = context_geometry._project_to_mesh(tin, pts)
result["project_probe"] = {"in": len(pts), "out": len(out), "indices": indices}
print("project probe", result["project_probe"])
assert len(indices) == len(out), "indices %d != out %d" % (len(indices), len(out))
assert len(out) >= 1 and all(i in (0, 1) for i in indices), "원점 근처 점이 TIN에 맞아야 한다"

t = time.time()
items, counts, skipped, warnings = context_geometry.build_buildings(prepared, tin)
result["build_buildings_s"] = round(time.time() - t, 2)
result["counts"] = counts
result["skipped"] = skipped
result["warnings"] = warnings
print(json.dumps({"counts": counts, "skipped": skipped, "warnings": warnings}, ensure_ascii=False, indent=1, default=str))
assert counts["project_indices"] == counts["project_out"], "len(indices) != len(out)"
assert 3000 <= counts["buildings"] <= 4000, "동 수 %d (≈3,500 기대)" % counts["buildings"]
assert len(skipped) <= 3, "건너뜀 %d" % len(skipped)
assert counts["fallback_skipped"] == 0, "폴백 ② %d" % counts["fallback_skipped"]

# 압출 검사 — Z 범위·Max.Z ≈ Min.Z + HEIGHT_M·UserString 14키·레이어
keys = ("BLD_ID", "PNU", "PNU_SRC", "GRND_FLR", "FLR_SRC", "UGRND_FLR", "HEIGHT_M", "HEIGHT_SRC", "HEIGHT_GRADE",
        "USABILITY", "USEAPR_DAY", "BLD_NM", "STATUS", "DEMOL_DAY")
z_lo, z_hi, slope = [], [], 0
for item in items:
    assert item.layer == "CTX::Buildings" and isinstance(item.geometry, rg.Mesh) and item.geometry.IsValid and item.geometry.IsClosed
    assert tuple(item.attrs.keys()) == keys, item.attrs.keys()
    bb = item.geometry.GetBoundingBox(True)
    z_lo.append(bb.Min.Z)
    z_hi.append(bb.Max.Z)
    assert abs((bb.Max.Z - bb.Min.Z) - float(item.attrs["HEIGHT_M"])) < 0.01, "압출 높이 %s" % item.attrs
    slope += item.attrs["HEIGHT_SRC"].endswith("~slope")
result["extrusions"] = {"n": len(items), "base_z": [round(min(z_lo), 2), round(max(z_lo), 2)], "top_z": [round(min(z_hi), 2), round(max(z_hi), 2)],
                        "slope_flagged": slope}
print("extrusions", result["extrusions"])
tin_bb = tin.GetBoundingBox(True)
assert tin_bb.Min.Z - 0.01 <= min(z_lo) and max(z_lo) <= tin_bb.Max.Z + 0.01, "base_z가 TIN Z 범위 밖"
# 안뜰 — 구멍이 빠지면 꽉 찬 덩어리가 된다(_get_prism_mesh 단면 좌표). BLD_ID 929230 = (외곽 54.284 − 구멍 6.073 ㎡) × 3.8 m, 메워지면 206.3
courtyard = next(item for item in items if item.attrs["BLD_ID"] == "929230")
result["courtyard_m3"] = round(courtyard.geometry.Volume(), 1)
print("courtyard 929230 %.1f m3" % result["courtyard_m3"])
assert abs(result["courtyard_m3"] - 183.2) < 0.5, "안뜰 부피 %.1f (183.2 기대)" % result["courtyard_m3"]

t = time.time()
curves = context_geometry.build_curves(prepared)
by_layer = {}
for item in curves:
    by_layer[item.layer] = by_layer.get(item.layer, 0) + 1
result["curves"] = {"s": round(time.time() - t, 2), "by_layer": by_layer}
print("curves", result["curves"])
assert by_layer.get("CTX::Site") == 1 and by_layer.get("CTX::Parcels", 0) > 1000 and by_layer.get("CTX::Ref", 0) >= 2
assert all(item.geometry.IsClosed for item in curves if item.layer != "CTX::Roads::centerline")   # 중심선은 열린 선

t = time.time()
geo = context_geometry.build(prepared)
result["build_all_s"] = round(time.time() - t, 2)
result["build_items"] = geo.counts["items"]
print("build() %.2fs items %d" % (result["build_all_s"], geo.counts["items"]))

with open(os.path.join(OUT_DIR, "buildings.json"), "w", encoding="utf-8") as f:   # noqa: F821
    json.dump(result, f, ensure_ascii=False, indent=1, default=str)
print("OK")
