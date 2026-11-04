# Brep 출력 드라이버 — 같은 요청(333-139, 기본 사각형 500 m, 대상지 바닥면·평탄화)을 geometry_type mesh·brep으로 build → 헤드리스 문서에 베이크.
# 단언: brep이면 건물이 전부 닫힌 Brep, 지형 분류도 유효한 Brep(실패는 counts.brep_failed)이고 층별 면적이 mesh와 같다, 동 수도 같다. mesh(기본)는 예전 그대로 Mesh.
# python3 scripts/dev_rhino_run.py tests/rhino/driver_brep.py → out/log.txt·brep.json·context_brep.3dm. 사용자 문서는 건드리지 않는다.
import json
import os
import time

import Rhino
import Rhino.Geometry as rg

import constants
import context_baker
import context_builder
import context_geometry

FIXTURES = os.path.join(JOB_DIR, "tests", "fixtures")   # noqa: F821 — dev_rhino_run 전역
result = {}


def run(geometry_type, step=0):
    request = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": os.path.join(FIXTURES, "seongsu_site.db"),
               "context_db": os.path.join(FIXTURES, "seongsu_context.db"),
               "options": {"radius": 250, "shape": "rect", "site_output": "mesh", "flatten_site": True, "terrain_block": True,
                           "terrain_step": step, "geometry_type": geometry_type}}
    prepared = context_builder.prepare(request)
    t = time.time()
    geo = context_geometry.build(prepared)
    build_s = round(time.time() - t, 2)
    doc = Rhino.RhinoDoc.CreateHeadless(None)
    doc.ModelUnitSystem = Rhino.UnitSystem.Meters
    t = time.time()
    ids = context_baker.bake(doc, geo.items, prepared)
    bake_s = round(time.time() - t, 2)
    path = os.path.join(OUT_DIR, "context_%s%s.3dm" % (geometry_type, "_step%d" % step if step else ""))   # noqa: F821
    t = time.time()
    doc.WriteFile(path, Rhino.FileIO.FileWriteOptions())
    write_s = round(time.time() - t, 2)
    types, open_buildings, faces, areas, invalid, down = {}, 0, {}, {}, [], {}
    for item in geo.items:
        layer = item.layer.split("::", 1)[1] if "::" in item.layer else item.layer
        types.setdefault(layer, set()).add(type(item.geometry).__name__)
        if isinstance(item.geometry, (rg.Brep, rg.Mesh)) and layer != "Buildings":   # 지형 층 면적 — mesh·brep이 같아야 모양이 같다
            areas[layer] = round(areas.get(layer, 0) + rg.AreaMassProperties.Compute(item.geometry).Area, 1)
        if isinstance(item.geometry, rg.Brep):
            faces[layer] = faces.get(layer, 0) + item.geometry.Faces.Count
            if not item.geometry.IsValid:
                invalid.append(layer)
            if layer in ("Terrain", "Roads", "Green", "Site::ground"):   # 윗면 층 — 면이 전부 위를 봐야 음영이 메시와 같다
                for face in item.geometry.Faces:
                    n = face.NormalAt(face.Domain(0).Mid, face.Domain(1).Mid)
                    if (-n.Z if face.OrientationIsReversed else n.Z) < -0.5:   # 계단 지형의 수직 벽(Z ≈ 0)은 빼고 아래를 보는 면만
                        down[layer] = down.get(layer, 0) + 1
            if layer == "Buildings" and not item.geometry.IsSolid:
                open_buildings += 1
    doc.Dispose()
    out = {"build_s": build_s, "bake_s": bake_s, "write_s": write_s, "baked": len(ids), "buildings": geo.counts["buildings"],
           "brep_failed": geo.counts.get("brep_failed"), "open_buildings": open_buildings, "mb": round(os.path.getsize(path) / 1e6, 1),
           "types": {k: sorted(v) for k, v in types.items()}, "brep_faces": faces, "areas": areas, "invalid": invalid, "down_faces": down, "warnings": [w["code"] for w in geo.warnings]}
    print(geometry_type, step, json.dumps(out, ensure_ascii=False))
    return out


result["mesh"] = run("mesh")
result["brep"] = run("brep")
result["brep_step2"] = run("brep", 2)
with open(os.path.join(OUT_DIR, "brep.json"), "w", encoding="utf-8") as f:   # noqa: F821
    json.dump(result, f, ensure_ascii=False, indent=1)

mesh, brep = result["mesh"], result["brep"]
assert mesh["types"]["Buildings"] == ["Mesh"] and mesh["types"]["Terrain"] == ["Mesh"], mesh["types"]
assert brep["types"]["Buildings"] == ["Brep"], brep["types"]
assert brep["buildings"] == mesh["buildings"], (brep["buildings"], mesh["buildings"])
assert brep["open_buildings"] == 0, brep["open_buildings"]
assert not brep["brep_failed"], brep["brep_failed"]
assert not brep["invalid"] and not result["brep_step2"]["invalid"], (brep["invalid"], result["brep_step2"]["invalid"])
assert not brep["down_faces"] and not result["brep_step2"]["down_faces"], (brep["down_faces"], result["brep_step2"]["down_faces"])
for layer, area in mesh["areas"].items():   # 같은 평면 면 묶기(get_mesh_brep)가 모양을 바꾸지 않았다
    assert abs(brep["areas"][layer] - area) <= 0.5, (layer, area, brep["areas"][layer])   # site_wall 27.3 → 27.2: CreateFromMesh가 높이 0인 벽 조각을 버린다
for run_name in ("brep", "brep_step2"):   # mesh 판에서 Mesh였던 층은 전부 Brep
    for layer, kinds in mesh["types"].items():
        if "Mesh" in kinds:
            assert result[run_name]["types"].get(layer) == ["Brep"], (run_name, layer, result[run_name]["types"].get(layer))
print("PASS")
