"""driver_terrain_webp — 해외 지형 Mapterhorn 전/후(2026-11-14) (python3 scripts/dev_rhino_run.py tests/rhino/driver_terrain_webp.py).

① Rhino CPython에서 무손실 WebP 해독 시간(/tmp/mth/cache의 Mapterhorn 타일, 없으면 건너뜀).
② 대상지마다 같은 요청을 두 번 — 전 = Mapterhorn을 막아 예전 길(AWS terrarium z13), 후 = Mapterhorn. 헤드리스 문서(m), 2D 없음.
   OSM 응답은 osm_context 캐시라 두 번째는 Overpass를 다시 부르지 않는다. 생성 시간·지형 받기 시간·TIN 점 수를 result.json에,
   문서의 메시를 레이어별 OBJ(out/<대상지>_<전후>.obj, 로컬 m)로 — Blender로 같은 각도 렌더(PR 이미지).
TERRAIN_SITES 환경 변수(쉼표)로 대상지를 고른다. 사용자 문서는 건드리지 않는다.
"""
import glob
import json
import os
import sys
import time

import Rhino

import context_baker
import context_builder
import context_geometry
import non_rhino_utils
import osm_context

SITES = {"lauterbrunnen": (7.9090, 46.5935, 500), "innsbruck": (11.3933, 47.2692, 1000), "flam": (7.1140, 60.8630, 500),
         "zurich": (8.5450, 47.3600, 500)}
CHOSEN = [s for s in (os.environ.get("TERRAIN_SITES") or "lauterbrunnen,innsbruck,flam").split(",") if s in SITES]
res = {"python": sys.version.split()[0], "sites": {}}

files = sorted(glob.glob("/tmp/mth/cache/m_*.webp"))[:24]
if files:
    t = time.time()
    for path in files:
        with open(path, "rb") as f:
            osm_context.decode_webp(f.read())
    res["decode_avg_s"] = round((time.time() - t) / len(files), 3)
    print("decode", len(files), "tiles avg", res["decode_avg_s"], "s", res["python"])

original_spots, original_fetch, original_mapterhorn = osm_context.get_terrain_spots, osm_context._fetch, osm_context._get_mapterhorn_spots
original_build = context_geometry.build
fetched, geo_counts = [], {}


def counting_build(prepared):   # 지형·건물 단계 counts(tin_s·mesh_s …)
    geo = original_build(prepared)
    geo_counts.clear()
    geo_counts.update(geo.counts)
    return geo


context_geometry.build = counting_build


def counting_fetch(url, data=None, timeout=None):
    body = original_fetch(url, data, timeout)
    if "overpass" not in url:
        fetched.append((url, len(body)))
    return body


def blocked(bounds, today):
    raise RuntimeError("blocked for before")


def dump_obj(doc, path):
    # 레이어별 메시 → OBJ(o <레이어>) — 정점 번호는 파일 전체 누적
    lines, base, faces = [], 1, 0
    for ro in context_baker._get_objects(doc):
        mesh = ro.Geometry if isinstance(ro.Geometry, Rhino.Geometry.Mesh) else None
        if mesh is None and isinstance(ro.Geometry, Rhino.Geometry.Extrusion):
            mesh = ro.Geometry.GetMesh(Rhino.Geometry.MeshType.Render)
        if mesh is None or mesh.Vertices.Count == 0:
            continue
        lines.append("o %s" % doc.Layers[ro.Attributes.LayerIndex].FullPath.replace(" ", "_"))
        for i in range(mesh.Vertices.Count):
            p = mesh.Vertices.Point3dAt(i)
            lines.append("v %.2f %.2f %.2f" % (p.X, p.Y, p.Z))
        for f in mesh.Faces:
            lines.append("f %d %d %d" % (f.A + base, f.B + base, f.C + base) if f.IsTriangle else
                         "f %d %d %d %d" % (f.A + base, f.B + base, f.C + base, f.D + base))
            faces += 1
        base += mesh.Vertices.Count
    with open(path, "w") as f:
        f.write("\n".join(lines))
    return faces


for name in CHOSEN:
    lng, lat, radius = SITES[name]
    for phase in ("before", "after"):
        non_rhino_utils.set_projection(lng, lat)
        x, y = non_rhino_utils.get_tm_from_wgs84(lng, lat)
        osm_context._get_mapterhorn_spots = blocked if phase == "before" else original_mapterhorn
        osm_context._TERRAIN_TILES.clear()
        timing = {}

        def timed_spots(bounds, today):
            t0 = time.time()
            del fetched[:]
            result = original_spots(bounds, today)
            timing.update(terrain_s=round(time.time() - t0, 2), spots=len(result[0]), ids=sorted(result[1]), tiles=len(fetched),
                          tile_kb=round(sum(n for _u, n in fetched) / 1024.0), grid=osm_context.get_mapterhorn_grid(bounds))
            return result
        osm_context.get_terrain_spots, osm_context._fetch = timed_spots, counting_fetch
        doc = Rhino.RhinoDoc.CreateHeadless(None)
        doc.ModelUnitSystem = Rhino.UnitSystem.Meters
        request = {"target": {"mode": "point", "center": [x, y]}, "result_root": os.path.join(OUT_DIR, "result"),   # noqa: F821 — dev_rhino_run 전역
                   "options": {"region": "global", "radius": radius, "shape": "rect", "make_basemap": False, "make_sheets": False,
                               "make_tables": False, "output_lang": "ko"}}
        t = time.time()
        phases = {}

        def progress(phase_, fraction, text):
            phases.setdefault(phase_, round(time.time() - t, 1))   # 단계 시작 시각
            return True
        response = context_builder.run(request, progress, doc)
        elapsed = round(time.time() - t, 1)
        counts = dict(geo_counts)
        meta = []
        if response.get("dir") and os.path.exists(os.path.join(response["dir"], "context.json")):
            with open(os.path.join(response["dir"], "context.json"), encoding="utf-8") as f:
                meta = (json.load(f).get("meta_lines") or [])[:3]
        faces = dump_obj(doc, os.path.join(OUT_DIR, "%s_%s.obj" % (name, phase))) if response.get("ok") else 0   # noqa: F821
        res["sites"].setdefault(name, {})[phase] = dict(timing, ok=response.get("ok"), error=response.get("error"), elapsed_s=elapsed, obj_faces=faces,
                                                        counts={k: counts.get(k) for k in ("tin_input", "tin_points", "tin_s", "tin_faces", "mesh_s", "mesh_edge",
                                                                                           "split_s", "water_points_excluded")},
                                                        phases=phases, meta=meta)
        print(name, phase, json.dumps(res["sites"][name][phase], ensure_ascii=False, default=str))
        doc.Dispose()
osm_context.get_terrain_spots, osm_context._fetch, osm_context._get_mapterhorn_spots = original_spots, original_fetch, original_mapterhorn
context_geometry.build = original_build
non_rhino_utils.set_projection()
with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
bad = {n: p for n, v in res["sites"].items() for p, r in v.items() if not r["ok"]}
assert not bad, bad
assert all(v["after"]["ids"] == ["mapterhorn"] for v in res["sites"].values()), "Mapterhorn을 쓰지 않았다"
print("PASS terrain webp")
