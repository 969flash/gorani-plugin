"""Blender 스토어 대표 이미지용 렌더 — 해외(OpenStreetMap) 대상지를 저장소 scripts로 생성하고 흰 매스로 렌더한다(Blender 안, 개발 전용).

    Blender -b --factory-startup --python scripts/dev_blender_store.py -- build/blender_store

→ <출력 폴더>/hero_render.png(배경 투명 1920×1080, docs/blender_store/featured.html이 얹는다)와 강조 건물 꼭대기 화면 좌표(콘솔 target_px —
featured.html .site 위치). 국내 대상지는 쓰지 않는다 — 수치지형도에서 나온 3D 이미지는 해외 사이트에 올리지 않는다(공간정보관리법 제16조).
시험이 ~/Gorani·~/.gorani를 건드리지 않게 HOME을 임시 폴더로 바꿔 돌린다.
"""

import importlib.util
import math
import os
import sys
import tempfile

import bmesh
import bpy
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector

SITE = (-122.4040, 37.7960, 850.0)       # 샌프란시스코 금융가 — 사각형 한 변 1.7 km(언덕 + 고층)
HIGHLIGHT = (106.0, -89.0)               # m, 대상지 중심에서 — Transamerica Pyramid(260 m)를 '대상지'로 파랗게
CAMERA = (225.0, 30.0, 1.45)             # 방위각(도, 0 = 남쪽에서), 고도각(도), 거리 배율(범위 폭 대비)
COLORS = {"CTX::Buildings": "F2F3F5", "CTX::Terrain": "27303D", "CTX::Roads": "394354", "CTX::Water": "2E6FD0", "CTX::Green": "3E7A4E",
          "CTX::Rail": "4A5260"}         # food4rhino 대표 이미지와 같은 톤(어두운 바탕 #00151c)
HIGHLIGHT_COLOR = "2F6BFF"


def _get_linear(hex_rgb):
    # type: (str) -> tuple
    c = [int(hex_rgb[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple((v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4) for v in c) + (1.0,)


def _split_highlight(tx, ty):
    # type: (float, float) -> object
    """건물 메시에서 (tx, ty) 40 m 안 가장 높은 동을 떼어 새 객체로."""
    buildings = bpy.data.collections["CTX::Buildings"].objects[0]
    mesh = buildings.data
    ids, heights = mesh.attributes["building_id"].data, mesh.attributes["height"].data
    best = max(((heights[p.index].value, ids[p.index].value) for p in mesh.polygons if math.hypot(p.center.x - tx, p.center.y - ty) < 40.0))
    target = buildings.copy()
    target.data = mesh.copy()
    bpy.context.scene.collection.objects.link(target)
    for obj, keep in ((buildings, False), (target, True)):
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        layer = bm.faces.layers.int.get("building_id")
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if (f[layer] == best[1]) != keep], context="FACES")
        bm.to_mesh(obj.data)
        bm.free()
    return target


def render(out_dir):
    # type: (str) -> None
    scripts_dir = os.path.dirname(os.path.abspath(__file__))
    spec = importlib.util.spec_from_file_location("gorani_cmd_blender", os.path.join(scripts_dir, "cmd_blender.py"))
    cmd_blender = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cmd_blender
    spec.loader.exec_module(cmd_blender)
    loader = cmd_blender.loader
    scene = bpy.context.scene
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    lng, lat, radius = SITE
    non_rhino_utils = loader.load("non_rhino_utils")
    non_rhino_utils.set_projection(lng, lat)
    center = non_rhino_utils.get_tm_from_wgs84(lng, lat)
    request = {"target": {"mode": "point", "center": list(center)}, "result_root": tempfile.mkdtemp(),
               "options": {"region": "global", "radius": radius, "shape": "rect", "placement": "origin",
                           "make_sheets": False, "make_basemap": False, "make_tables": False}}
    response = loader.load("context_builder").run(request, lambda phase, fraction, text: print(phase, text) or True, scene)
    if not response["ok"]:
        raise SystemExit(response["error"])
    origin = response["context"]["doc_origin"]
    target = _split_highlight(center[0] - origin[0] + HIGHLIGHT[0], center[1] - origin[1] + HIGHLIGHT[1])
    for collection in bpy.data.collections:
        collection.hide_render = collection.name.startswith(("CTX::Ref", "CTX::Parcels"))
        key = next((k for k in COLORS if collection.name.startswith(k)), None)
        for obj in collection.objects:
            obj.color = _get_linear(COLORS.get(key, COLORS["CTX::Terrain"]))
            obj.hide_render = obj.hide_render or obj.type != "MESH"
    target.color = _get_linear(HIGHLIGHT_COLOR)

    points = [o.matrix_world @ Vector(c) for o in scene.objects if o.type == "MESH" for c in o.bound_box]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    look = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z + 30.0))
    azimuth, elevation, distance = math.radians(CAMERA[0]), math.radians(CAMERA[1]), max(hi.x - lo.x, hi.y - lo.y) * CAMERA[2]
    camera = bpy.data.objects.new("camera", bpy.data.cameras.new("camera"))
    camera.data.clip_end = 100000.0
    scene.collection.objects.link(camera)
    camera.location = look + Vector((math.sin(azimuth) * math.cos(elevation), -math.cos(azimuth) * math.cos(elevation), math.sin(elevation))) * distance
    camera.rotation_euler = (look - camera.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = camera
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 1920, 1080, 100
    scene.render.film_transparent = True
    shading = scene.display.shading
    shading.light, shading.color_type = "STUDIO", "OBJECT"
    shading.show_cavity, shading.cavity_type, shading.cavity_ridge_factor, shading.cavity_valley_factor = True, "WORLD", 0.6, 1.2
    shading.show_shadows, shading.shadow_intensity = True, 0.45
    scene.display.light_direction = (-0.45, -0.35, 0.82)
    scene.display.render_aa = "32"
    scene.view_settings.view_transform = "Standard"
    scene.render.filepath = os.path.join(out_dir, "hero_render.png")
    bpy.ops.render.render(write_still=True)
    corners = [target.matrix_world @ Vector(c) for c in target.bound_box]
    top = world_to_camera_view(scene, camera, Vector((sum(p.x for p in corners) / 8, sum(p.y for p in corners) / 8, max(p.z for p in corners))))
    print("hero_render.png · target_px %.0f %.0f" % (top.x * 1920, (1 - top.y) * 1080))


if __name__ == "__main__":
    render(os.path.abspath(sys.argv[sys.argv.index("--") + 1]))
