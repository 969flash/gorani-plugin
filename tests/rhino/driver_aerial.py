"""driver_aerial — 지역 공개 정사영상(2026-11-14): 파리 루브르 위치 방식 R=250(사각형 한 변 500 m), 지형에 항공사진(terrain_aerial) + 23 항공사진·도형-배경(겹치기 0.5).
python3 scripts/dev_rhino_run.py tests/rhino/driver_aerial.py → out/log.txt·result.json·aerial_context.3dm·aerial_drape.jpg·sheets_after/·sheets_before/·render_*.png.

헤드리스 문서(m) — 사용자 문서는 건드리지 않는다. OSM(Overpass 한 번)·AWS 지형·IGN 영상을 받는다.
before = 같은 SheetData를 지역 영상 없이(Esri만) 다시 그린 23 항공사진. 렌더 캡처는 헤드리스 문서에 뷰를 붙일 수 있을 때만(안 되면 건너뛴다).
"""
import json
import os
import shutil
import time

import Rhino
import System

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


def capture(doc, path, perspective):
    """헤드리스 문서에 뷰를 하나 붙여 Rendered로 찍는다. 못 붙이면 False."""
    try:
        projection = Rhino.Display.DefinedViewportProjection.Perspective if perspective else Rhino.Display.DefinedViewportProjection.Top
        view = doc.Views.Add("aerial", projection, System.Drawing.Rectangle(0, 0, 1400, 1000), True)
    except Exception as error:   # noqa: BLE001
        print("view add failed", error)
        return False
    if view is None:
        return False
    viewport = view.ActiveViewport
    viewport.DisplayMode = Rhino.Display.DisplayModeDescription.FindByName("Rendered")
    if perspective:
        viewport.SetCameraLocations(Rhino.Geometry.Point3d(0, 0, 0), Rhino.Geometry.Point3d(-420, -520, 380))
    viewport.ZoomExtents()
    capture_ = Rhino.Display.ViewCapture()
    capture_.Width, capture_.Height = 1400, 1000
    bitmap = capture_.CaptureToBitmap(view)
    if bitmap is None:
        return False
    bitmap.Save(path)
    return True


doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Meters
try:
    non_rhino_utils.set_projection(LNG, LAT)
    x, y = non_rhino_utils.get_tm_from_wgs84(LNG, LAT)
    sheet_ids = [constants.SHEET_IDS["aerial"], constants.SHEET_IDS["figure"]]
    request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
               "options": {"region": "global", "radius": 250, "shape": "rect", "scales": [2500], "paper": "A3", "make_sheets": True, "sheet_ids": sheet_ids,
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
    res["render_top"] = capture(doc, os.path.join(OUT_DIR, "render_top.png"), False)   # noqa: F821
    res["render_persp"] = capture(doc, os.path.join(OUT_DIR, "render_persp.png"), True)   # noqa: F821
    print("render", res["render_top"], res["render_persp"])
finally:
    non_rhino_utils.set_projection()
    doc.Dispose()
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
assert all(c["ok"] for c in res["checks"].values()), json.dumps(res["checks"], ensure_ascii=False)
print("PASS aerial")
