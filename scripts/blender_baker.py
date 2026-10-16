"""Blender 장면을 만지는 유일한 모듈 — 베이크·원점 기록·사본(.blend) 저장·다시 넣기·줌. context_baker의 Blender판.

blender_geometry의 BakeItem(로컬 m 정점·면·폴리라인)을 객체로 만든다. 레이어 = 컬렉션('CTX' 아래 'CTX::Buildings'처럼 전체 경로 이름),
색 = 레이어마다 재질 하나(constants.CTX_LAYERS). 모든 객체에 URBANSITE_MANAGED·URBANSITE_LOT_KEY·URBANSITE_LAYER 사용자 속성을 붙여
clear_previous가 같은 키의 객체만 지운다(사용자 객체 보존). 문서 원점은 장면 사용자 속성(constants.DOC_ORIGIN_KEYS)에 둔다.
장면 단위는 m로 가정한다(Blender 기본) — 실제 좌표 방식은 객체 위치로 옮긴다(메시 정점은 단정밀도라 로컬로 둔다).

    bake(scene, items, prepared, lot_key) → [이름]        write_ref_and_origin(scene, prepared, lot_key) → [이름]
    save_copy(scene, path, names, timing) → context.blend  import_blend(scene, result_dir) → {ok, layers, objects, replaced, text}
    clear_previous(scene, lot_key) → (objects, layers)     zoom_to_site(scene, result_dir, center_lng_lat) → bool
"""

import math
import os
import time

import bpy

import constants
import non_rhino_utils
from context_baker import get_layer_rgb, get_lot_key, get_ref_attrs, read_meta

LAYER_KEY = "URBANSITE_LAYER"   # 객체가 속한 레이어(컬렉션) 이름 — .blend에서 다시 넣을 때 제자리를 찾는다


# ── 원점 ───────────────────────────────────────────────────

def get_doc_origin(scene):
    # type: (object) -> tuple
    """장면 사용자 속성 원점 → (E, N). 없거나 좌표계가 지금과 다르면 None (context_baker.get_doc_origin과 같은 규칙)."""
    e, n, crs = (scene.get(key) for key in constants.DOC_ORIGIN_KEYS)
    if crs and crs != non_rhino_utils.get_crs_label():
        return None
    try:
        return (float(e), float(n)) if e and n else None
    except ValueError:
        return None


def _set_doc_origin(scene, origin):
    # type: (object, tuple) -> None
    scene[constants.DOC_ORIGIN_KEYS[0]] = "%.3f" % origin[0]
    scene[constants.DOC_ORIGIN_KEYS[1]] = "%.3f" % origin[1]
    scene[constants.DOC_ORIGIN_KEYS[2]] = non_rhino_utils.get_crs_label()


# ── 컬렉션·재질 ─────────────────────────────────────────────

def _get_linear(rgb):
    # type: (tuple) -> tuple
    """0~255 sRGB → Blender 색 속성(선형) RGBA."""
    def channel(value):
        c = value / 255.0
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    return (channel(rgb[0]), channel(rgb[1]), channel(rgb[2]), 1.0)


def _get_collection(scene, full_path):
    # type: (object, str) -> object
    """'CTX::Buildings' 컬렉션을 찾거나 만들어 'CTX' 아래에 건다(CTX는 장면 아래). 숨김 레이어(CTX_HIDDEN_LAYERS)는 만들 때만 끈다."""
    root = bpy.data.collections.get(constants.CTX_ROOT_LAYER) or bpy.data.collections.new(constants.CTX_ROOT_LAYER)
    if root.name not in scene.collection.children:
        scene.collection.children.link(root)
    if full_path == root.name:
        return root
    collection = bpy.data.collections.get(full_path)
    if collection is None:
        collection = bpy.data.collections.new(full_path)
        if full_path.partition("::")[2] in constants.CTX_HIDDEN_LAYERS:
            collection.hide_viewport = collection.hide_render = True
    if collection.name not in root.children:
        root.children.link(collection)
    return collection


def _get_material(full_path):
    # type: (str) -> object
    """레이어 이름의 재질(뷰포트 색 + Principled 기본색 = 레이어 색)."""
    material = bpy.data.materials.get(full_path) or bpy.data.materials.new(full_path)
    color = _get_linear(get_layer_rgb(full_path))
    material.diffuse_color = color
    nodes = material.node_tree.nodes if material.node_tree else []
    for node in nodes:
        if node.type == "BSDF_PRINCIPLED":
            node.inputs["Base Color"].default_value = color
    return material


def _get_objects(lot_key=None):
    # type: (str) -> list
    """이 도구가 만든 객체(lot_key를 주면 그 대상지만)."""
    return [o for o in bpy.data.objects
            if o.get(constants.UDT_MANAGED_KEY) == "1" and (lot_key is None or o.get(constants.UDT_LOT_KEY) == lot_key)]


# ── 지우기·베이크 ────────────────────────────────────────────

def clear_previous(scene, lot_key=None):
    # type: (object, str) -> tuple
    """URBANSITE_MANAGED 객체(lot_key를 주면 같은 키만)와 그 데이터 삭제 + 빈 CTX 컬렉션 정리. 출력 (지운 객체 수, 지운 컬렉션 수)."""
    deleted = 0
    for obj in _get_objects(lot_key):
        data = obj.data
        bpy.data.objects.remove(obj, do_unlink=True)
        deleted += 1
        if data is not None and data.users == 0:
            if isinstance(data, bpy.types.Mesh):
                bpy.data.meshes.remove(data)
            elif isinstance(data, bpy.types.Curve):
                bpy.data.curves.remove(data)
    removed = 0
    root = bpy.data.collections.get(constants.CTX_ROOT_LAYER)
    if root is not None:
        for child in list(root.children):
            if not child.all_objects and not child.children:
                bpy.data.collections.remove(child)
                removed += 1
        if not root.all_objects and not root.children:
            bpy.data.collections.remove(root)
            removed += 1
    return deleted, removed


def _get_shift(prepared):
    # type: (object) -> tuple
    """계산 원점 − 문서 원점(실제 좌표 방식이면 계산 원점 그대로) — 객체 위치로 옮긴다."""
    doc_origin = getattr(prepared, "doc_origin", None) or prepared.origin
    return (prepared.origin[0] - doc_origin[0], prepared.origin[1] - doc_origin[1], 0.0)


def _make_data(item):
    # type: (object) -> object
    """BakeItem → Mesh(면 속성 포함) 또는 Curve(POLY 스플라인)."""
    if item.faces:
        mesh = bpy.data.meshes.new(item.name)
        mesh.from_pydata(item.verts, [], item.faces)
        for name, values in (item.face_attrs or {}).items():
            attribute = mesh.attributes.new(name, "INT" if values and isinstance(values[0], int) else "FLOAT", "FACE")
            attribute.data.foreach_set("value", values)
        mesh.validate(clean_customdata=False)
        mesh.update()
        return mesh
    curve = bpy.data.curves.new(item.name, "CURVE")
    curve.dimensions = "3D"
    for pts, closed in item.polylines:
        if len(pts) < 2:
            continue
        spline = curve.splines.new("POLY")
        spline.points.add(len(pts) - 1)
        spline.points.foreach_set("co", [c for x, y, z in pts for c in (x, y, z, 1.0)])
        spline.use_cyclic_u = closed
    return curve


def bake(scene, items, prepared, lot_key=None):
    # type: (object, list, object, str) -> list
    """BakeItem 목록을 장면에 넣는다. 출력: 만든 객체 이름 목록(실패 항목은 빠진다 — run이 수를 비교해 경고)."""
    lot_key = lot_key or getattr(prepared, "target_key", "") or get_lot_key((prepared.request or {}).get("pnus") or [])
    shift = _get_shift(prepared)
    names = []
    for item in items:
        data = _make_data(item)
        obj = bpy.data.objects.new(item.name or item.layer.split("::")[-1], data)
        obj.location = shift
        material = _get_material(item.layer)
        if item.faces:
            data.materials.append(material)
        obj.color = material.diffuse_color   # 커브는 뷰포트에서 객체 색으로 그린다
        for key, value in (item.attrs or {}).items():
            obj[str(key)] = "" if value is None else str(value)
        obj[constants.UDT_MANAGED_KEY] = "1"
        obj[constants.UDT_LOT_KEY] = lot_key
        obj[LAYER_KEY] = item.layer
        _get_collection(scene, item.layer).objects.link(obj)
        names.append(obj.name)
    return names


def write_ref_and_origin(scene, prepared, lot_key=None):
    # type: (object, object, str) -> list
    """원점 표식 두 개(CTX::Ref) — 빈 객체(사용자 속성 = Ref 속성 전부) + 'ORIGIN E … N …' 글자. 장면 원점은 재사용이 아니면 기록.
    출력: 객체 이름 2개(context_baker와 같은 수 — run이 베이크 실패를 센다)."""
    lot_key = lot_key or getattr(prepared, "target_key", "")
    layer = constants.CTX_ROOT_LAYER + "::Ref"
    collection = _get_collection(scene, layer)
    attrs = get_ref_attrs(prepared)
    text = bpy.data.curves.new("origin_label", "FONT")
    text.body = "ORIGIN E %.0f N %.0f" % tuple(prepared.origin)
    text.size = 5.0
    marker = bpy.data.objects.new("origin", None)
    marker.empty_display_type = "ARROWS"
    marker.empty_display_size = 10.0
    names = []
    for obj in (marker, bpy.data.objects.new("origin_label", text)):
        obj.location = _get_shift(prepared)
        for key, value in attrs.items():
            obj[key] = value
        obj[constants.UDT_MANAGED_KEY] = "1"
        obj[constants.UDT_LOT_KEY] = lot_key
        obj[LAYER_KEY] = layer
        collection.objects.link(obj)
        names.append(obj.name)
    if not prepared.origin_reused:
        _set_doc_origin(scene, getattr(prepared, "doc_origin", None) or prepared.origin)
    return names


def save_copy(scene, path, names=None, timing=None):
    # type: (object, str, list, dict) -> str
    """CTX 컬렉션 전체를 사본 context.blend로 쓴다(열면 'UrbanSite' 장면 하나). path의 파일 이름은 무시하고 같은 폴더에 쓴다.
    ponytail: 같은 장면에 대상지가 여럿이면 함께 들어간다 — 이번 객체만 쓰려면 컬렉션 이름이 겹쳐 '.001'이 붙는다."""
    path = os.path.join(os.path.dirname(path), constants.BLENDER_MODEL_FILE_NAME)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    timing = timing if timing is not None else {}
    root = bpy.data.collections.get(constants.CTX_ROOT_LAYER)
    if root is None:
        raise RuntimeError("저장할 CTX 컬렉션이 없습니다")
    t = time.time()
    copy = bpy.data.scenes.new(constants.TOOL_NAME)
    try:
        copy.collection.children.link(root)
        for key in constants.DOC_ORIGIN_KEYS:
            if key in scene:
                copy[key] = scene[key]
        for view_layer in copy.view_layers:   # 갱신 안 된 새 장면을 쓰면 Blender가 죽는다(5.2.2 BKE_view_layer_copy_data, 2026-10-15 실측)
            view_layer.update()
        bpy.data.libraries.write(path, {copy}, fake_user=False, compress=True)
    finally:
        bpy.data.scenes.remove(copy)
    timing.update(select_s=0.0, write_s=round(time.time() - t, 2), objects=len(root.all_objects), bytes=os.path.getsize(path))
    return path


# ── 다시 넣기·줌 ─────────────────────────────────────────────

def import_blend(scene, result_dir):
    # type: (object, str) -> dict
    """<result_dir>/context.blend의 객체를 장면에 다시 넣는다(panel_ui.md import_context — context_baker.import_3dm과 같은 규칙).
    같은 lot_key 객체를 먼저 지우고, 파일 원점 ≠ 장면 원점이면 차이만큼 옮긴다(차이 > ORIGIN_MAX_OFFSET이면 거부). 장면에 원점이 없으면 파일 원점을 기록."""
    path = os.path.join(result_dir, constants.BLENDER_MODEL_FILE_NAME)
    result = {"ok": False, "layers": 0, "objects": 0, "replaced": False, "text": "", "shift": [0.0, 0.0]}
    if not os.path.exists(path):
        result["text"] = "파일이 없습니다: %s" % path
        return result
    meta = read_meta(result_dir)
    file_origin = tuple(float(v) for v in (meta.get("doc_origin") or meta.get("origin") or [])) or None
    doc_origin = get_doc_origin(scene)
    if file_origin and doc_origin and (file_origin == (0.0, 0.0)) != (doc_origin == (0.0, 0.0)):
        result["text"] = "좌표 방식이 다른 장면입니다(원점 이동 / 실제 좌표) — 새 장면에서 넣으세요"
        return result
    if file_origin and doc_origin and math.hypot(file_origin[0] - doc_origin[0], file_origin[1] - doc_origin[1]) > constants.ORIGIN_MAX_OFFSET:
        result["text"] = "다른 지역 장면입니다 — 새 장면에서 넣으세요 (원점 차이 > %.0f m)" % constants.ORIGIN_MAX_OFFSET
        return result
    lot_key = meta.get("lot_key") or (get_lot_key(meta["pnus"]) if meta.get("pnus") else None)
    if lot_key:
        result["replaced"] = clear_previous(scene, lot_key)[0] > 0
    with bpy.data.libraries.load(path, link=False) as (source, target):
        target.objects = list(source.objects)
    shift = (file_origin[0] - doc_origin[0], file_origin[1] - doc_origin[1]) if file_origin and doc_origin else (0.0, 0.0)
    layers = set()
    for obj in target.objects:
        if obj is None:
            continue
        layer = obj.get(LAYER_KEY) or constants.CTX_ROOT_LAYER
        _get_collection(scene, layer).objects.link(obj)
        obj.location.x += shift[0]
        obj.location.y += shift[1]
        layers.add(layer)
        result["objects"] += 1
    if file_origin and not doc_origin:
        _set_doc_origin(scene, file_origin)
    result.update(ok=result["objects"] > 0, layers=len(layers), shift=list(shift),
                  text="" if result["objects"] else "파일에 객체가 없습니다: %s" % path)
    return result


def zoom_to_site(scene, result_dir, center_lng_lat=None):
    # type: (object, str, list) -> bool
    """3D 뷰를 이번 결과의 CTX::Site(없으면 context.json 중심 500 m, 경위도를 주면 그 주변 100 m)로 옮긴다.
    먼 클리핑을 BLENDER_VIEW_CLIP_END까지 늘린다. 3D 뷰가 없으면(백그라운드) False."""
    meta = read_meta(result_dir)
    sites = [o for o in _get_objects(meta.get("lot_key")) if o.get(LAYER_KEY) == constants.CTX_ROOT_LAYER + "::Site"]
    if sites and not center_lng_lat:
        corners = [o.matrix_world @ v.co.xyz for o in sites if o.type == "CURVE" for s in o.data.splines for v in s.points]
        xs, ys = [c.x for c in corners], [c.y for c in corners]
        cx, cy, half = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, max(max(xs) - min(xs), max(ys) - min(ys), 20.0)
    else:
        origin = get_doc_origin(scene) or meta.get("doc_origin") or meta.get("origin") or [0.0, 0.0]
        if center_lng_lat:
            world, half = non_rhino_utils.get_tm_from_wgs84(float(center_lng_lat[0]), float(center_lng_lat[1])), 100.0
        elif meta.get("center"):
            world, half = meta["center"], 500.0
        else:
            return False
        cx, cy = world[0] - origin[0], world[1] - origin[1]
    moved = False
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.clip_end = max(space.clip_end, constants.BLENDER_VIEW_CLIP_END)
            space.region_3d.view_location = (cx, cy, 0.0)
            space.region_3d.view_distance = half * 3.0
            area.tag_redraw()
            moved = True
    return moved
