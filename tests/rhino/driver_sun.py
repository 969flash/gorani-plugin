"""driver_sun — 패널 '해와 그림자'(set_sun)를 Rhino 8에서 확인한다(2026-11-14).
python3 scripts/dev_rhino_run.py tests/rhino/driver_sun.py → out/log.txt·result.json·sun_<시각>.png.

헤드리스 문서(m)에 성북동 경사지(위치 방식, 한 변 500 m)를 3D로 만들고, 같은 카메라에서 동지 9·12·15시·하지 12시(진태양시)마다
context_builder.get_sun_state → context_baker.set_sun을 부르고 doc.Lights.Sun 방위·고도·벡터를 solar 값과 맞춘다. 끄기(on = false)도 본다.
그 뒤 make_2d로 도면 25~28 계산 시간을 잰다. 헤드리스 뷰는 Rhino 8이 그리지 않아 캡처는 비어 있다(ViewCapture·DrawToBitmap 모두 None, 2026-11-14).
화면 캡처를 하려고 공유 Rhino에 새 문서 창(RhinoDoc.Create)을 열고 RhinoApp.RunScript(새 문서, "_-Close")로 닫게 했더니 Rhino가 멈췄다
(2026-11-14 17:36, 캡처도 그림자 없는 같은 그림이었다). 드라이버에서 일반 문서를 만들거나 닫지 않는다 — 화면 캡처는 사용자가 직접.
사용자 문서는 건드리지 않는다. 컨텍스트 팩은 HOME_DIR(~/Gorani)/data.
"""
import json
import os
import time

import Rhino
import System

import context_baker
import context_builder
import non_rhino_utils

LNG, LAT = 127.0005, 37.5935   # 성북동 — 북쪽 언덕, 남쪽 성북천
SHOTS = (("winter_0900", "winter", 540), ("winter_1200", "winter", 720), ("winter_1500", "winter", 900), ("summer_1200", "summer", 720))
res = {"shots": {}}
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Meters
x, y = non_rhino_utils.get_tm_from_wgs84(LNG, LAT)
request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821 — dev_rhino_run 머리말 전역
           "options": {"output_lang": "en", "radius": 250, "shape": "rect", "region": "kr", "make_basemap": False, "make_sheets": False, "make_tables": False,
                       "terrain_block": True}}
t = time.time()
keep = {}
response = context_builder.run(request, lambda phase, fraction, text: True, doc, keep)
res["run"] = {"ok": response["ok"], "elapsed_s": round(time.time() - t, 1), "error": response["error"], "buildings": response["context"].get("buildings")}
print("run", json.dumps(res["run"], ensure_ascii=False))
assert response["ok"], response["error"]

view = None
try:
    view = doc.Views.Add("sun", Rhino.Display.DefinedViewportProjection.Perspective, System.Drawing.Rectangle(0, 0, 1600, 1000), True)
except Exception as exc:   # noqa: BLE001
    print("view add failed", exc)
res["view"] = view is not None
meta = json.load(open(os.path.join(response["dir"], "context.json"), encoding="utf-8"))
cx, cy = meta["center"][0] - meta["origin"][0], meta["center"][1] - meta["origin"][1]
if view is not None:
    vp = view.ActiveViewport
    vp.DisplayMode = Rhino.Display.DisplayModeDescription.GetDisplayMode(Rhino.Display.DisplayModeDescription.RenderedId)
    target = Rhino.Geometry.Point3d(cx, cy, 45.0)
    vp.SetCameraLocations(target, Rhino.Geometry.Point3d(cx - 260.0, cy - 520.0, 420.0))
    vp.Camera35mmLensLength = 40.0
for name, season, minutes in SHOTS:
    state = context_builder.get_sun_state(response["dir"], {"season": season, "minutes": minutes})
    ok = context_baker.set_sun(doc, state)
    sun = doc.Lights.Sun
    vec = sun.Vector
    res["shots"][name] = {"applied": ok, "azimuth": round(state["azimuth"], 2), "altitude": round(state["altitude"], 2), "enabled": sun.Enabled,
                          "rhino_azimuth": round(sun.Azimuth, 2), "rhino_altitude": round(sun.Altitude, 2), "vector": [round(vec.X, 3), round(vec.Y, 3), round(vec.Z, 3)],
                          "expected_vector": [round(-v, 3) for v in state["vector"]], "kst": "%02d:%02d" % tuple(state["local"][3:])}
    if view is not None:
        view.Redraw()
        capture = Rhino.Display.ViewCapture()
        capture.Width, capture.Height = 1600, 1000
        capture.ScaleScreenItems, capture.DrawAxes, capture.DrawGrid = False, False, False
        bitmap = capture.CaptureToBitmap(view)
        if bitmap is not None:
            bitmap.Save(os.path.join(OUT_DIR, "sun_%s.png" % name))   # noqa: F821
            res["shots"][name]["png"] = True
    print(name, json.dumps(res["shots"][name]))
context_baker.set_sun(doc, {"on": False})
res["off"] = {"enabled": doc.Lights.Sun.Enabled}
# 도면 25~28 — Rhino CPython 계산 시간(장마다)
marks = []
t = time.time()
made = context_builder.make_2d(response["dir"], {"make_sheets": True, "sheet_ids": [25, 26, 27, 28], "make_basemap": False, "make_tables": False},
                               lambda phase, fraction, text: marks.append((round(time.time() - t, 2), phase, text)) or True, keep)
res["sheets"] = {"ok": made["ok"], "elapsed_s": made["elapsed_s"], "error": made["error"], "marks": [m for m in marks if m[1] == "sheets"],
                 "sheets": [(s_["id"], s_["empty"], s_["reason"]) for s_ in made["sheets"]]}
print("sheets", json.dumps(res["sheets"], ensure_ascii=False))
print("off", res["off"])
with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as handle:   # noqa: F821
    json.dump(res, handle, ensure_ascii=False, indent=1)
doc.Dispose()
assert not res["off"]["enabled"]
assert all(shot["enabled"] and abs(shot["rhino_altitude"] - shot["altitude"]) < 0.5 for shot in res["shots"].values()), res["shots"]
print("PASS sun")
