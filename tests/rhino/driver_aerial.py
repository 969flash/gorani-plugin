"""driver_aerial — 지역 공개 정사영상(2026-11-14): 파리 루브르 위치 방식 R=250(사각형 한 변 500 m), 지형에 항공사진(terrain_aerial) + 23 항공사진·도형-배경(겹치기 0.5).
python3 scripts/dev_rhino_run.py tests/rhino/driver_aerial.py → out/log.txt·result.json·aerial_context.3dm·aerial_drape.jpg·aerial.obj·sheets_after/·sheets_before/.

헤드리스 문서(m) — 사용자 문서는 건드리지 않는다. OSM(Overpass 한 번)·AWS 지형·IGN 영상을 받는다.
before = 같은 SheetData를 지역 영상 없이(Esri만) 다시 그린 23 항공사진. 헤드리스 문서는 뷰 캡처가 빈 그림이라(2026-11-14 시험 — RhinoView·ViewCaptureSettings 모두)
렌더는 aerial.obj(UV = 객체에 저장된 매핑 채널 1로 Rhino가 계산)를 Blender로 찍는다.
"""
import json
import os
import shutil
import time

import Rhino

import constants
import context_baker
import context_builder
import non_rhino_utils
import sheet_svg

LNG, LAT = 2.3376, 48.8606
res = {"checks": {}}


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": detail}
    print("%s %s %s" % ("PASS" if ok else "FAIL", name, detail))


def write_obj(doc, path):
    """렌더용 OBJ — 항공사진을 입힌 땅 면(객체에 저장된 매핑 채널 1로 Rhino가 계산한 UV)과 건물. 헤드리스 문서는 뷰 캡처가 비어서(2026-11-14 시험) Blender로 렌더한다."""
    lines, offset, counts = ["mtllib aerial.mtl"], 1, {"draped": 0, "buildings": 0}
    for rhino_object in context_baker._get_objects(doc):
        layer = doc.Layers[rhino_object.Attributes.LayerIndex].FullPath
        draped = rhino_object.Attributes.MaterialSource == Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject
        if not (draped or layer.startswith("CTX::Buildings")):
            continue
        mesh = rhino_object.Geometry if isinstance(rhino_object.Geometry, Rhino.Geometry.Mesh) else None
        if mesh is None:
            meshes = Rhino.Geometry.Mesh.CreateFromBrep(rhino_object.Geometry.ToBrep() if hasattr(rhino_object.Geometry, "ToBrep") else rhino_object.Geometry,
                                                         Rhino.Geometry.MeshingParameters.FastRenderMesh) or []
            mesh = Rhino.Geometry.Mesh()
            for part in meshes:
                mesh.Append(part)
        mesh = mesh.DuplicateMesh()
        mesh.Faces.ConvertQuadsToTriangles()
        if draped:
            mesh.SetTextureCoordinates(rhino_object.GetTextureMapping(1), Rhino.Geometry.Transform.Identity, False)
        lines.append("o %s_%d" % ("ground" if draped else "building", offset))
        lines.append("usemtl %s" % ("aerial" if draped else "white"))
        lines += ["v %.3f %.3f %.3f" % (v.X, v.Y, v.Z) for v in mesh.Vertices]
        if draped:
            lines += ["vt %.6f %.6f" % (t.X, t.Y) for t in mesh.TextureCoordinates]
        for face in mesh.Faces:
            a, b, c = face.A + offset, face.B + offset, face.C + offset
            lines.append("f %d/%d %d/%d %d/%d" % (a, a, b, b, c, c) if draped else "f %d %d %d" % (a, b, c))
        offset += mesh.Vertices.Count
        counts["draped" if draped else "buildings"] += 1
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    with open(os.path.join(os.path.dirname(path), "aerial.mtl"), "w") as f:
        f.write("newmtl aerial\nKd 1 1 1\nmap_Kd %s\nnewmtl white\nKd 0.92 0.92 0.9\n" % constants.AERIAL_DRAPE_FILE_NAME)
    return counts


doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Meters
try:
    non_rhino_utils.set_projection(LNG, LAT)
    x, y = non_rhino_utils.get_tm_from_wgs84(LNG, LAT)
    sheet_ids = [constants.SHEET_IDS["aerial"], constants.SHEET_IDS["figure"]]
    request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
               "options": {"region": "global", "radius": 250, "shape": "rect", "scales": [3000], "paper": "A3", "make_sheets": True, "sheet_ids": sheet_ids,
                           "terrain_aerial": True, "terrain_block": True, "output_lang": "ko", "style": {"preset": "std", "aerial_opacity": 0.5}}}
    t0 = time.time()

    def progress(phase, fraction, text):
        print("progress %-9s %.2f %6.2fs %s" % (phase, fraction, time.time() - t0, text))
        return True

    keep = {}
    response = context_builder.run(request, progress, doc, keep)
    res["response"] = {k: response[k] for k in ("ok", "elapsed_s", "context", "error", "warnings")}
    print(json.dumps(res["response"], ensure_ascii=False, indent=1, default=str))
    aerial = response["context"].get("aerial") or {}
    check("ok", response["ok"], str(response.get("error")))
    check("draped", aerial.get("objects", 0) > 0 and "IGN" in aerial.get("attribution", ""), json.dumps(aerial, ensure_ascii=False))
    check("jpg", os.path.exists(aerial.get("path", "")), aerial.get("path", ""))
    draped = [o for o in context_baker._get_objects(doc) if o.Attributes.MaterialSource == Rhino.DocObjects.ObjectMaterialSource.MaterialFromObject]
    layers = sorted({doc.Layers[o.Attributes.LayerIndex].FullPath for o in draped})
    check("layers", "CTX::Terrain" in layers, ", ".join(layers))
    model = os.path.join(response["dir"], constants.CONTEXT_MODEL_FILE_NAME)
    copy = Rhino.FileIO.File3dm.Read(model)
    textured = [m for m in copy.Materials if m.GetBitmapTexture()] if copy else []
    check("3dm material", bool(textured), "%d" % len(textured))
    shutil.copy2(model, os.path.join(OUT_DIR, "aerial_context.3dm"))   # noqa: F821
    if aerial.get("path"):
        shutil.copy2(aerial["path"], os.path.join(OUT_DIR, constants.AERIAL_DRAPE_FILE_NAME))   # noqa: F821
    after = [s for s in response["sheets"] if s.get("path")]
    check("sheets", len(after) == 2, str([(s["id"], s["empty"]) for s in response["sheets"]]))
    os.makedirs(os.path.join(OUT_DIR, "sheets_after"), exist_ok=True)   # noqa: F821
    for sheet in after:
        shutil.copy2(sheet["path"], os.path.join(OUT_DIR, "sheets_after", os.path.basename(sheet["path"])))   # noqa: F821
    data = keep.get("data")
    if data is not None:   # 전 — 같은 도면 자료를 지역 영상 없이(Esri만)
        saved = constants.AERIAL_REGIONS
        constants.AERIAL_REGIONS = []
        try:
            data.options["style"] = {"preset": "std"}
            data.cache = {k: v for k, v in data.cache.items() if not (isinstance(k, tuple) and k and str(k[0]).startswith("aerial"))}
            before = sheet_svg.write_sheets(data, os.path.join(OUT_DIR, "sheets_before"), [constants.SHEET_IDS["aerial"]])   # noqa: F821
            check("sheet before", before and before[0].get("path"), str(before))
        finally:
            constants.AERIAL_REGIONS = saved
    res["obj"] = write_obj(doc, os.path.join(OUT_DIR, "aerial.obj"))   # noqa: F821
    check("obj uv", res["obj"]["draped"] > 0, json.dumps(res["obj"]))
finally:
    non_rhino_utils.set_projection()
    doc.Dispose()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
assert all(c["ok"] for c in res["checks"].values()), json.dumps(res["checks"], ensure_ascii=False)
print("PASS aerial")
