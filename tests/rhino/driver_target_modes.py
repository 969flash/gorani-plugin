"""driver_target_modes — 대상지 방식(area·point)·결과 좌표(world)·구역 커브 검증·합필 (python3 scripts/dev_rhino_run.py tests/rhino/driver_target_modes.py).

① 구역 방식(fixture, 원점 이동) — 헤드리스 문서에서 run → CTX::Site 구역 커브 1개·Parcels IN_SITE = 안의 필지 수.
   (사용자 문서는 건드리지 않는다 — 열린 문서가 없을 때도 돈다)
② 위치 방식 + 실제 좌표 — 헤드리스 문서(사용자 문서와 원점 방식이 섞이지 않게)에서 run → 건물 메시 bbox가 세계좌표(E 20만대)·
   배정밀도 정점·doc.Strings 원점 (0,0)·context.3dm 되읽기 객체 위치.
③ get_curve_ring — 사각형 OK·원(곡선) OK·열린 커브·자기교차·기울어진 커브 거부, mm 문서 배율.
④ 합필 — 맞닿은 두 필지는 CTX::Site 커브 하나(면적 = 합), 합필 전 필지는 CTX::Site::lots.
"""
import json
import os
import time

import Rhino
import Rhino.Geometry as rg

import constants
import context_baker
import context_builder
import context_geometry
import non_rhino_utils

FIXTURE_DIR = os.path.join(JOB_DIR, "tests", "fixtures")   # noqa: F821 — dev_rhino_run 머리말 전역
SITE_DB = os.path.join(FIXTURE_DIR, "seongsu_site.db")
CONTEXT_DB = os.path.join(FIXTURE_DIR, "seongsu_context.db")
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters   # 사용자 문서 관행(mm) — 단위 환산도 같이 본다
res = {"checks": {}}


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": detail}
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


lot = context_builder.lot_db.load([constants.TEST_CONTEXT_PNU], SITE_DB).lots[0]
cx, cy = (lot.min_x + lot.max_x) * 0.5, (lot.min_y + lot.max_y) * 0.5
area_ring = [(cx - 150, cy - 100), (cx + 150, cy - 100), (cx + 150, cy + 100), (cx - 150, cy + 100)]
keys = []
try:
    # ① 구역 방식 — 활성 문서
    t0 = time.time()
    request = {"target": {"mode": "area", "ring": area_ring}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
               "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
               "options": {"radius": 300, "shape": "rect", "scales": [3000], "make_basemap": True, "make_sheets": True, "make_tables": True,
                           "flatten_site": True, "flatten_level": "mean"}}
    response = context_builder.run(request, None, doc)
    check("area_ok", response["ok"], str(response["error"]))
    meta = json.load(open(os.path.join(response["dir"], constants.CONTEXT_META_FILE_NAME), encoding="utf-8"))
    key = meta["lot_key"]
    keys.append(key)
    objs = [o for o in context_baker._get_objects(doc) if o.Attributes.GetUserString(constants.UDT_LOT_KEY) == key]
    site = [o for o in objs if doc.Layers[o.Attributes.LayerIndex].FullPath == "CTX::Site"]
    in_site = [o for o in objs if o.Attributes.GetUserString("IN_SITE") == "1"]
    lots_in = len(meta["pnus"])
    check("area_site_curve", len(site) == 1 and site[0].Attributes.GetUserString("KIND") == "area", "%d" % len(site))
    check("area_in_site_parcels", lots_in > 0 and len({o.Attributes.GetUserString("PNU") for o in in_site}) == lots_in, "%d vs %d" % (len(in_site), lots_in))
    n_sheets = len(context_builder.get_sheet_ids(response["options"]))   # 기본 시트 = 틀 뺀 것(driver_full_run과 같은 기준)
    check("area_sheets_tables", len(response["sheets"]) == n_sheets and len(response["tables"]) == 5 and response["basemap"]["ready"],
          "sheets %d/%d · tables %d · basemap %s" % (len(response["sheets"]), n_sheets, len(response["tables"]), response["basemap"]["ready"]))
    # 쿼드 지형 + 평탄화(경계 평균) — 평탄면 Z 하나, 원지형 사본 레이어는 꺼져 있고 면적 = 구역, 벽 있음, 대상지 안 건물 바닥 = 평탄 높이
    def layer_objs(path):
        return [o for o in objs if doc.Layers[o.Attributes.LayerIndex].FullPath == path]
    terrain = layer_objs("CTX::Terrain")
    quads = sum(o.Geometry.Faces.QuadCount for o in terrain)
    faces = sum(o.Geometry.Faces.Count for o in terrain)
    check("terrain_quads", terrain and quads >= 0.5 * faces, "quad %d / %d" % (quads, faces))   # 경계 옆만 삼각형
    flat, wall, orig = layer_objs("CTX::Terrain::site_flat"), layer_objs("CTX::Terrain::site_wall"), layer_objs("CTX::Terrain::site_original")
    scale = context_baker.get_model_unit_scale(doc)
    level = float(flat[0].Attributes.GetUserString("LEVEL_M")) if flat else None
    zs = {round(flat[0].Geometry.Vertices.Point3dAt(k).Z / scale, 3) for k in range(flat[0].Geometry.Vertices.Count)} if flat else set()
    check("site_flat_level", flat and len(zs) == 1 and abs(next(iter(zs)) - level) < 0.006, "%s %s" % (level, sorted(zs)[:3]))   # LEVEL_M은 소수 2자리
    orig_index = doc.Layers.FindByFullPath("CTX::Terrain::site_original", -1)
    area_m2 = rg.AreaMassProperties.Compute(flat[0].Geometry).Area / scale ** 2 if flat else 0
    check("site_original_hidden", orig and orig_index >= 0 and not doc.Layers[orig_index].IsVisible)
    check("site_area_exact", abs(area_m2 - 60000.0) < 60.0, "%.1f ㎡" % area_m2)
    check("site_wall", wall and wall[0].Geometry.Faces.Count > 10, str(wall[0].Geometry.Faces.Count if wall else 0))
    # 틈 없음 — 지형·도로·녹지·철도 + 평탄면 + 벽을 합쳐 용접 → 대상지 경계 1 m 안에 열린 모서리 0
    joined = rg.Mesh()
    for path in ("CTX::Terrain", "CTX::Roads", "CTX::Green", "CTX::Rail", "CTX::Terrain::site_flat", "CTX::Terrain::site_wall"):
        for o in layer_objs(path):
            if isinstance(o.Geometry, rg.Mesh):
                joined.Append(o.Geometry)
    joined.Vertices.CombineIdentical(True, True)
    origin = response["context"]["origin"]
    local_ring = [((x - origin[0]) * scale, (y - origin[1]) * scale) for x, y in area_ring]
    def near_site(pt):
        best = 1e18
        for i in range(len(local_ring)):
            (x1, y1), (x2, y2) = local_ring[i], local_ring[(i + 1) % len(local_ring)]
            dx, dy = x2 - x1, y2 - y1
            t = max(0.0, min(1.0, ((pt.X - x1) * dx + (pt.Y - y1) * dy) / (dx * dx + dy * dy)))
            best = min(best, ((pt.X - x1 - t * dx) ** 2 + (pt.Y - y1 - t * dy) ** 2) ** 0.5)
        return best < 1.0 * scale
    open_pts = [pt for pl in (joined.GetNakedEdges() or []) for pt in pl if near_site(pt)]
    check("site_no_gap", len(open_pts) == 0, "대상지 경계 근처 열린 모서리 점 %d" % len(open_pts))
    on_site = [o for o in layer_objs("CTX::Buildings") if area_ring[0][0] + 20 < o.Geometry.GetBoundingBox(True).Center.X / scale + response["context"]["origin"][0] < area_ring[1][0] - 20
               and area_ring[0][1] + 20 < o.Geometry.GetBoundingBox(True).Center.Y / scale + response["context"]["origin"][1] < area_ring[2][1] - 20]
    bases = [o.Geometry.GetBoundingBox(True).Min.Z / scale for o in on_site]
    check("buildings_on_flat", bases and all(abs(z - level) < 0.05 for z in bases), "%d동 %s" % (len(bases), [round(z, 2) for z in bases[:4]]))
    res["terrain"] = {"quads": quads, "faces": faces, "level": level}
    res["area_seconds"] = round(time.time() - t0, 2)

    # ①b 필지 방식 기본(대상지 바닥 메시) — CTX::Site::ground 메시 1개, 면적 = 필지, 지형에서는 빠진다
    lots_req = {"pnus": [constants.TEST_CONTEXT_PNU], "site_db": SITE_DB, "context_db": CONTEXT_DB, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
                "options": {"radius": 200, "shape": "circle", "site_output": "mesh", "make_basemap": False, "make_sheets": False, "make_tables": False}}
    r2 = context_builder.run(lots_req, None, doc)
    key2 = context_builder.get_target_key({"mode": "lots", "pnus": [constants.TEST_CONTEXT_PNU]})
    ground = [o for o in context_baker._get_objects(doc) if o.Attributes.GetUserString(constants.UDT_LOT_KEY) == key2
              and doc.Layers[o.Attributes.LayerIndex].FullPath == "CTX::Site::ground"]
    g_area = rg.AreaMassProperties.Compute(ground[0].Geometry).Area / context_baker.get_model_unit_scale(doc) ** 2 if ground else 0
    check("lots_site_ground", r2["ok"] and len(ground) == 1 and abs(g_area - lot.geometry_area) / lot.geometry_area < 0.01,
          "%d · %.1f ㎡ vs %.1f" % (len(ground), g_area, lot.geometry_area))

    # ② 위치 방식 + 실제 좌표 — 헤드리스 문서(m 단위)
    t0 = time.time()
    headless = Rhino.RhinoDoc.CreateHeadless(None)
    headless.ModelUnitSystem = Rhino.UnitSystem.Meters
    request = {"target": {"mode": "point", "center": [cx, cy]}, "site_db": SITE_DB, "context_db": CONTEXT_DB,
               "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
               "options": {"shape": "frame", "scales": [1000], "placement": "world", "make_basemap": False, "make_sheets": False, "make_tables": False}}
    response = context_builder.run(request, None, headless)
    check("world_ok", response["ok"], str(response["error"]))
    check("world_doc_origin", context_baker.get_doc_origin(headless) == (0.0, 0.0), str(context_baker.get_doc_origin(headless)))
    meshes = [o for o in headless.Objects if headless.Layers[o.Attributes.LayerIndex].FullPath == "CTX::Buildings"]
    box = rg.BoundingBox.Empty
    for o in meshes:
        box.Union(o.Geometry.GetBoundingBox(True))
    check("world_buildings_at_world_coords", meshes and abs(box.Center.X - cx) < 600 and abs(box.Center.Y - cy) < 600,
          "n=%d center %.1f %.1f vs %.1f %.1f" % (len(meshes), box.Center.X, box.Center.Y, cx, cy))
    check("world_double_precision", meshes and all(o.Geometry.Vertices.UseDoublePrecisionVertices for o in meshes[:50]))
    ref = [o for o in headless.Objects if isinstance(o.Geometry, rg.Point) and headless.Layers[o.Attributes.LayerIndex].FullPath == "CTX::Ref"]
    origin = response["context"]["origin"]
    check("world_ref_point", ref and abs(ref[0].Geometry.Location.X - origin[0]) < 1e-6 and abs(ref[0].Geometry.Location.Y - origin[1]) < 1e-6,
          str(ref[0].Geometry.Location if ref else None))
    copy = Rhino.FileIO.File3dm.Read(response["context"]["path"])
    cbox = rg.BoundingBox.Empty
    for o in copy.Objects:
        if copy.AllLayers.FindIndex(o.Attributes.LayerIndex).FullPath == "CTX::Buildings":
            cbox.Union(o.Geometry.GetBoundingBox(True))
    check("world_copy_coords", abs(cbox.Center.X - box.Center.X) < 1e-3 and abs(cbox.Center.Y - box.Center.Y) < 1e-3, str(cbox.Center))
    # 같은 헤드리스 문서에 원점 이동으로 다시 → placement_mismatch
    again = context_builder.run(dict(request, options=dict(request["options"], placement="origin")), None, headless)
    check("world_mismatch_blocked", (not again["ok"]) and again["error"]["code"] == "placement_mismatch", str(again["error"]))
    res["world_seconds"] = round(time.time() - t0, 2)
    headless.Dispose()

    # ③ get_curve_ring
    tol = 0.001
    rect = rg.PolylineCurve([rg.Point3d(0, 0, 0), rg.Point3d(100, 0, 0), rg.Point3d(100, 50, 0), rg.Point3d(0, 50, 0), rg.Point3d(0, 0, 0)])
    ring, why = context_geometry.get_curve_ring(rect, 1.0, tol)
    check("curve_rect", ring is not None and abs(non_rhino_utils.get_ring_area(ring) - 5000.0) < 1e-6, why)
    ring, why = context_geometry.get_curve_ring(rect, 0.001, tol * 1000)   # mm 문서: 100 mm × 50 mm = 0.005 ㎡ → 너무 작음
    check("curve_mm_scale_small", ring is None and "작" in why, why)
    circle = rg.ArcCurve(rg.Circle(rg.Point3d(0, 0, 0), 100.0))
    ring, why = context_geometry.get_curve_ring(circle, 1.0, tol)
    check("curve_circle", ring is not None and abs(non_rhino_utils.get_ring_area(ring) - 31415.9) / 31415.9 < 0.002, "%s %s" % (len(ring or []), why))
    open_crv = rg.PolylineCurve([rg.Point3d(0, 0, 0), rg.Point3d(100, 0, 0), rg.Point3d(100, 50, 0)])
    check("curve_open_rejected", context_geometry.get_curve_ring(open_crv, 1.0, tol)[0] is None)
    bowtie = rg.PolylineCurve([rg.Point3d(0, 0, 0), rg.Point3d(100, 100, 0), rg.Point3d(100, 0, 0), rg.Point3d(0, 100, 0), rg.Point3d(0, 0, 0)])
    ring, why = context_geometry.get_curve_ring(bowtie, 1.0, tol)
    check("curve_bowtie_rejected", ring is None and "자기교차" in why, why)
    tilted = rg.PolylineCurve([rg.Point3d(0, 0, 0), rg.Point3d(100, 0, 0), rg.Point3d(100, 50, 50), rg.Point3d(0, 50, 50), rg.Point3d(0, 0, 0)])
    ring, why = context_geometry.get_curve_ring(tilted, 1.0, tol)
    check("curve_tilted_rejected", ring is None and "XY" in why, why)

    # ④ 합필 — 맞닿은 두 필지(333-139 + 333-132)는 CTX::Site 커브 하나(면적 = 두 필지 합)·바닥 메시 하나,
    #    합필 전 필지는 CTX::Site::lots 둘(레이어 꺼짐), 3dm 2D 도면의 BM 10b도 꺼짐(BM 루트를 켜도 꺼진 채)
    pnus = [constants.TEST_CONTEXT_PNU, "1120011500103330132"]
    r4 = context_builder.run({"pnus": pnus, "site_db": SITE_DB, "context_db": CONTEXT_DB, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
                              "options": {"radius": 200, "shape": "circle", "site_output": "mesh", "scales": [1000], "make_basemap": True,
                                          "make_sheets": False, "make_tables": False}}, None, doc)
    key4 = context_builder.get_target_key({"mode": "lots", "pnus": pnus})
    objs4 = [o for o in context_baker._get_objects(doc) if o.Attributes.GetUserString(constants.UDT_LOT_KEY) == key4]
    by_path = lambda path: [o for o in objs4 if doc.Layers[o.Attributes.LayerIndex].FullPath == path]
    sites, before, ground = by_path("CTX::Site"), by_path("CTX::Site::lots"), by_path("CTX::Site::ground")
    scale = context_baker.get_model_unit_scale(doc)
    want = sum(l.geometry_area for l in context_builder.lot_db.load(pnus, SITE_DB).lots)
    got = rg.AreaMassProperties.Compute(sites[0].Geometry).Area / scale ** 2 if len(sites) == 1 else 0.0
    g_area = rg.AreaMassProperties.Compute(ground[0].Geometry).Area / scale ** 2 if len(ground) == 1 else 0.0
    lots_layer = doc.Layers.FindByFullPath("CTX::Site::lots", -1)
    bm_layer = next((l for l in doc.Layers if l.FullPath.startswith(constants.BM_ROOT_LAYER + "::10b_site_lots")), None)
    check("merged_site", r4["ok"] and len(sites) == 1 and abs(got - want) < 1.0 and abs(g_area - want) / want < 0.01,   # 바닥 메시는 지형 경사만큼 크다
          "Site %d · %.1f ㎡ · 바닥 %.1f ㎡ vs %.1f ㎡" % (len(sites), got, g_area, want))
    check("merged_lots_hidden", len(before) == 2 and lots_layer >= 0 and not doc.Layers[lots_layer].IsVisible
          and bm_layer is not None and not bm_layer.IsVisible and not bm_layer.GetPersistentVisibility(),
          "lots %d · CTX 보임 %s · BM 10b 보임 %s 다시 켤 때 %s" % (len(before), doc.Layers[lots_layer].IsVisible if lots_layer >= 0 else None,
                                                             bm_layer and bm_layer.IsVisible, bm_layer and bm_layer.GetPersistentVisibility()))
finally:
    doc.Dispose()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    failed = [k for k, v in res["checks"].items() if not v["ok"]]
    print("ALL PASS" if not failed else "FAILED: %s" % failed)
    assert not failed, failed
