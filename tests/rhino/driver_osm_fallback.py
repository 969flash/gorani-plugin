"""driver_osm_fallback — OSM 받기 보험 비교 (python3 scripts/dev_rhino_run.py tests/rhino/driver_osm_fallback.py).

파리(2026-11-04 GA에서 Overpass가 실패했던 곳)를 R=300 원으로 Overpass 한 번, 강제 대체(GORANI_FORCE_OSM_FALLBACK=1, OpenFreeMap 타일) 한 번
context_builder.run → 받기 시간(osm_context.load)·건물 수·도로 중심선 길이·경고 코드·지형 면 분할 수치·context.3dm.
큰 범위는 Rhino를 오래 잡는다(2026-11-14 같은 드라이버: Innsbruck R=1000 사각형 Overpass 2,015 s·타일 1,197 s, 파리 R=900 사각형 901 s —
지형 면 분할 RhinoSplitBrepFace가 대부분. SITES에 넣을 때 반경을 먼저 작게).
진행은 log.txt에 바로 쓴다. /tmp/ofm_cancel 파일을 만들면 다음 진행 보고에서 취소한다(네이티브 연산 안에서는 못 멈춘다).
헤드리스 문서라 사용자 문서는 건드리지 않는다. 결과: OUT_DIR/result.json + <곳>_<overpass|tiles>.3dm(그림은 Rhino 밖에서 같은 시점으로 그린다).
"""
import json
import math
import os
import shutil
import sys
import time

import Rhino

import constants
import context_builder
import context_geometry
import non_rhino_utils
import osm_context

SITES = [("paris", 2.3488, 48.8534, 300)]
CANCEL_PATH = "/tmp/ofm_cancel"
loaded = {}
original_load = osm_context.load


def timed_load(*args, **kwargs):
    t = time.time()
    context = original_load(*args, **kwargs)
    loaded["seconds"] = round(time.time() - t, 1)
    loaded["context"] = context
    return context


def kept_build(prepared, *args, **kwargs):
    geo = original_build(prepared, *args, **kwargs)
    loaded["counts"] = dict(geo.counts)
    return geo


osm_context.load = timed_load
original_build = context_geometry.build
context_geometry.build = kept_build
res = {}


def progress(phase, fraction, text):
    print("  %6.1fs %-8s %.2f %s" % (time.time() - started_at, phase, fraction, text))
    sys.stdout.flush()   # 머리말의 log.txt는 버퍼라 바로 쓴다
    return not os.path.exists(CANCEL_PATH)


try:
    for name, lng, lat, radius in SITES:
        for mode in ("overpass", "tiles"):
            if mode == "tiles":
                os.environ[constants.OSM_FALLBACK_FORCE_ENV] = "1"
            doc = Rhino.RhinoDoc.CreateHeadless(None)
            doc.ModelUnitSystem = Rhino.UnitSystem.Meters
            try:
                non_rhino_utils.set_projection(lng, lat)
                x, y = non_rhino_utils.get_tm_from_wgs84(lng, lat)
                request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821
                           "options": {"output_lang": "en", "radius": radius, "shape": "circle", "make_basemap": False, "make_sheets": False,
                                       "make_tables": False}}
                loaded.clear()
                t = started_at = time.time()
                print(name, mode, "start")
                response = context_builder.run(request, progress, doc, {})
                context = loaded.get("context")
                roads = [f for f in (context.features if context else []) if f.theme == "road" and f.kind == "centerline"]
                road_m = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for f in roads for a, b in zip(f.geometry["coordinates"], f.geometry["coordinates"][1:]))
                row = {"ok": response["ok"], "error": response.get("error"), "load_s": loaded.get("seconds"), "total_s": round(time.time() - t, 1),
                       "buildings": (response.get("context") or {}).get("buildings"), "road_km": round(road_m / 1000.0, 1), "road_lines": len(roads),
                       "sources": [s.source_id for s in (context.sources if context else [])],
                       "warnings": [w["code"] for w in response.get("warnings") or []],
                       "terrain": {k: (loaded.get("counts") or {}).get(k) for k in (
                           "union_rings", "union_s", "union_failed", "split_s", "regions", "region_split_failed", "sub_split_failed", "mesh_s")}}
                model = os.path.join(response.get("dir") or "", constants.CONTEXT_MODEL_FILE_NAME)
                if os.path.exists(model):
                    shutil.copy2(model, os.path.join(OUT_DIR, "%s_%s.3dm" % (name, mode)))   # noqa: F821
                res["%s_%s" % (name, mode)] = row
                print(name, mode, json.dumps(row, ensure_ascii=False, default=str))
            finally:
                os.environ.pop(constants.OSM_FALLBACK_FORCE_ENV, None)
                non_rhino_utils.set_projection()
                doc.Dispose()
finally:
    osm_context.load, context_geometry.build = original_load, original_build
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
bad = {k: v for k, v in res.items() if not v["ok"] or (k.endswith("_tiles") and ("openfreemap" not in v["sources"] or "osm_fallback" not in v["warnings"]))}
assert not bad, json.dumps(bad, ensure_ascii=False, default=str)
print("PASS osm fallback")
