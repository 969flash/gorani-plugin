"""웹판 베이커 — 브라우저(Pyodide)에는 문서가 없어 구운 항목을 WebDoc에 들고 있다가 save_copy가 context.glb 한 파일로 쓴다. context_baker의 웹판.

    bake(doc, items, prepared, lot_key) → [id]         write_ref_and_origin(doc, prepared, lot_key) → [id, id]
    save_copy(doc, path, ids, timing) → context.glb    clear_previous(doc, lot_key) → (objects, 0)
    get_doc_origin(doc) → None                         zoom_to_site(doc, result_dir, center_lng_lat) → True
    get_glb(items, prepared) → bytes

GLB: 레이어마다 노드 하나(이름 'CTX::Buildings', 재질 = 레이어 색, CTX_HIDDEN_LAYERS는 뺀다) — 면은 TRIANGLES, 선은 LINES.
건물 각기둥(mesh_geometry shapely판의 prisms)은 여기서 면으로 푼다 — 윗면·바닥은 shapely 제약 들로네, 옆면은 링 변마다 사각형.
법선은 넣지 않는다(glTF 규약상 받는 쪽이 면 법선으로 그린다 — 각진 매스). 좌표는 로컬 m, glTF는 +Y가 위라 (x, y, z) → (x, z, −y)(정북 = −Z).
원점(EPSG:5186)·대상지 이름은 asset.extras.gorani와 context.json에 적는다. 생성마다 파일 하나로 끝나므로 문서 원점은 재사용하지 않는다.
"""

import json
import os
import struct
import time

import numpy
import shapely

import constants
import non_rhino_utils
from context_baker import get_layer_rgb

_GL_ARRAY_BUFFER, _GL_ELEMENT_ARRAY_BUFFER = 34962, 34963
_GL_FLOAT, _GL_UNSIGNED_INT = 5126, 5125
_GL_LINES, _GL_TRIANGLES = 1, 4


class WebDoc(object):
    """웹판의 '문서' — 마지막 생성에서 구운 항목. cmd_web 컨트롤러가 하나 들고 있다."""

    def __init__(self):
        self.items = []
        self.prepared = None


# ── 베이커 함수(context_baker와 같은 이름) ───────────────────

def get_doc_origin(doc):
    # type: (WebDoc) -> None
    """생성마다 새 원점(대상지 중심 100 m 내림) — 파일 하나로 끝나는 웹판에는 이어 붙일 문서가 없다."""
    return None


def clear_previous(doc, lot_key=None):
    # type: (WebDoc, str) -> tuple
    """앞 생성의 항목을 비운다. 출력 (지운 항목 수, 0)."""
    count = len(doc.items)
    doc.items = []
    return count, 0


def bake(doc, items, prepared, lot_key=None):
    # type: (WebDoc, list, object, str) -> list
    """항목을 들고만 있다(파일은 save_copy). 출력: 항목마다 id 하나 — run이 수를 비교한다."""
    doc.items.extend(items)
    doc.prepared = prepared
    return list(range(len(items)))


def write_ref_and_origin(doc, prepared, lot_key=None):
    # type: (WebDoc, object, str) -> list
    """원점 표식 대신 GLB asset.extras에 원점을 적는다(save_copy). 출력: id 2개(context_baker와 같은 수)."""
    doc.prepared = prepared
    return [0, 1]


def save_copy(doc, path, names=None, timing=None):
    # type: (WebDoc, str, list, dict) -> str
    """구운 항목 → <path 폴더>/context.glb(path의 파일 이름은 무시). 출력: 쓴 경로."""
    path = os.path.join(os.path.dirname(path), constants.WEB_MODEL_FILE_NAME)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    t = time.time()
    data = get_glb(doc.items, doc.prepared)
    with open(path, "wb") as f:
        f.write(data)
    if timing is not None:
        timing.update(select_s=0.0, write_s=round(time.time() - t, 2), objects=len(doc.items), bytes=len(data))
    return path


def zoom_to_site(doc, result_dir, center_lng_lat=None):
    # type: (WebDoc, str, list) -> bool
    """페이지 뷰어가 새 모델을 읽을 때 대상지에 맞춘다 — 여기서 할 일이 없다."""
    return True


# ── GLB ────────────────────────────────────────────────────

def get_glb(items, prepared):
    # type: (list, object) -> bytes
    """BakeItem 목록 → GLB 바이트. 레이어마다 노드 하나(면·선 프리미티브), 숨김 레이어는 뺀다."""
    layers = {}
    for item in items:
        if item.layer.partition("::")[2] in constants.CTX_HIDDEN_LAYERS:
            continue
        tris, lines = layers.setdefault(item.layer, ([], []))
        if item.verts and item.faces:
            tris.append(_get_mesh_arrays(item.verts, item.faces))
        if item.prisms:
            tris.append(_get_prism_arrays(item.prisms))
        if item.polylines:
            lines.append(_get_line_arrays(item.polylines))
    writer = _GlbWriter()
    for layer in sorted(layers):
        tris, lines = layers[layer]
        writer.add_node(layer, get_layer_rgb(layer), _merge(tris), _merge(lines))
    extras = {"unit": "m", "axes": "x = 동, y = 위, -z = 북(EPSG:5186 격자북)", "crs": non_rhino_utils.get_crs_label()}
    if prepared is not None:
        extras.update(origin=[round(float(v), 3) for v in prepared.origin], lot_name=prepared.lot_name)
    return writer.get_bytes({"gorani": extras})


def _get_mesh_arrays(verts, faces):
    # type: (list, list) -> tuple
    """정점·면(삼각형·사각형) → (정점 (n, 3), 삼각형 인덱스). 사각형은 대각선 a–c로 나눈다."""
    tris = [f for f in faces if len(f) == 3]
    quads = numpy.array([f for f in faces if len(f) == 4], dtype=numpy.int64).reshape(-1, 4)
    indices = numpy.concatenate([numpy.array(tris, dtype=numpy.int64).reshape(-1), quads[:, [0, 1, 2, 0, 2, 3]].reshape(-1)])
    return numpy.asarray(verts, dtype=numpy.float64)[:, :3], indices


def _get_line_arrays(polylines):
    # type: (list) -> tuple
    """[(점들, 닫힘)] → (정점, 선분 인덱스 쌍). 닫힌 선은 끝점이 첫 점과 다를 때만 닫는 선분을 더한다. 점은 (x, y[, z])."""
    points, indices = [], []
    for pts, closed in polylines:
        if len(pts) < 2:
            continue
        start = len(points)
        points.extend((p[0], p[1], p[2] if len(p) > 2 else 0.0) for p in pts)
        n = len(pts)
        indices.extend(i for k in range(n - 1) for i in (start + k, start + k + 1))
        if closed and tuple(pts[0]) != tuple(pts[-1]):
            indices.extend((start + n - 1, start))
    return numpy.array(points, dtype=numpy.float64).reshape(-1, 3), numpy.array(indices, dtype=numpy.int64)


def _get_cdt(polygons):
    # type: (object) -> object
    """제약 들로네를 배열째로 — GEOS가 한 동이라도 못 풀면 동마다 다시 풀고 못 푼 동은 빈 결과로 둔다."""
    try:
        return shapely.constrained_delaunay_triangles(polygons)
    except Exception:   # noqa: BLE001 — 자기 교차 발자국(GEOS TopologyException)
        empty = shapely.GeometryCollection()
        out = []
        for polygon in polygons:
            try:
                out.append(shapely.constrained_delaunay_triangles(polygon))
            except Exception:   # noqa: BLE001
                out.append(empty)
        return numpy.array(out, dtype=object)


def _get_prism_arrays(prisms):
    # type: (list) -> tuple
    """건물 각기둥 [(파트 [[외곽, 구멍…]…], 바닥 Z, 높이, 속성, 이름)] → (정점, 삼각형 인덱스).
    윗면·바닥 = 파트 폴리곤의 제약 들로네(구멍 제외), 옆면 = 링 변마다 사각형. 링이 3점 미만인 파트는 뺀다."""
    polygons, bottoms, tops = [], [], []
    for parts, base_z, height, _attrs, _name in prisms:
        for part in parts:
            try:
                polygon = shapely.Polygon(part[0], part[1:])
            except (ValueError, shapely.errors.GEOSException):
                continue
            polygons.append(polygon)
            bottoms.append(base_z)
            tops.append(base_z + height)
    if not polygons:
        return numpy.zeros((0, 3)), numpy.zeros(0, dtype=numpy.int64)
    polygons = shapely.orient_polygons(numpy.array(polygons, dtype=object))   # 바깥 링 반시계·구멍 시계 → 옆면이 밖을 본다
    bottoms, tops = numpy.array(bottoms), numpy.array(tops)
    tri_parts, owner = shapely.get_parts(_get_cdt(polygons), return_index=True)
    xy = shapely.get_coordinates(tri_parts).reshape(-1, 4, 2)[:, :3]   # 삼각형 = 닫힌 링 4점
    cw = ((xy[:, 1, 0] - xy[:, 0, 0]) * (xy[:, 2, 1] - xy[:, 0, 1]) - (xy[:, 1, 1] - xy[:, 0, 1]) * (xy[:, 2, 0] - xy[:, 0, 0])) < 0
    xy[cw] = xy[cw][:, ::-1]
    top = numpy.concatenate([xy, numpy.repeat(tops[owner], 3).reshape(-1, 3, 1)], axis=2)
    bottom = numpy.concatenate([xy[:, ::-1], numpy.repeat(bottoms[owner], 3).reshape(-1, 3, 1)], axis=2)
    rings, ring_owner = shapely.get_rings(polygons, return_index=True)
    coords, ring_index = shapely.get_coordinates(rings, return_index=True)
    same = ring_index[:-1] == ring_index[1:]   # 링 안의 이웃 점 = 변(닫힌 링이라 마지막 점 = 첫 점)
    a, b = coords[:-1][same], coords[1:][same]
    own = ring_owner[ring_index[:-1][same]]
    z0, z1 = bottoms[own][:, None], tops[own][:, None]
    walls = numpy.stack([numpy.hstack([a, z0]), numpy.hstack([b, z0]), numpy.hstack([b, z1]), numpy.hstack([a, z1])], axis=1)
    caps = numpy.concatenate([top, bottom]).reshape(-1, 3)
    wall_indices = (len(caps) + 4 * numpy.arange(len(walls))[:, None] + numpy.array([0, 1, 2, 0, 2, 3])).reshape(-1)
    return numpy.concatenate([caps, walls.reshape(-1, 3)]), numpy.concatenate([numpy.arange(len(caps)), wall_indices])


def _merge(arrays):
    # type: (list) -> tuple
    """[(정점, 인덱스)] → 하나로(인덱스는 앞 정점 수만큼 민다). 비었으면 None."""
    arrays = [(p, i) for p, i in arrays if len(i)]
    if not arrays:
        return None
    offsets = numpy.cumsum([0] + [len(p) for p, _i in arrays[:-1]])
    return numpy.concatenate([p for p, _i in arrays]), numpy.concatenate([i + o for (_p, i), o in zip(arrays, offsets)])


def _get_linear(c):
    # type: (int) -> float
    """sRGB 0–255 → glTF baseColorFactor(선형)."""
    c = c / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


class _GlbWriter(object):
    """glTF 2.0 바이너리 — 버퍼 하나, 레이어마다 노드·메시·재질 하나."""

    def __init__(self):
        self.bin = bytearray()
        self.gltf = {"asset": {"version": "2.0", "generator": "%s %s" % (constants.TOOL_NAME, constants.PANEL_VERSION)},
                     "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [], "materials": [], "accessors": [], "bufferViews": []}

    def _add_accessor(self, array, is_index):
        # type: (object, bool) -> int
        data = array.astype(numpy.uint32 if is_index else numpy.float32)
        self.bin.extend(b"\0" * (-len(self.bin) % 4))
        self.gltf["bufferViews"].append({"buffer": 0, "byteOffset": len(self.bin), "byteLength": data.nbytes,
                                         "target": _GL_ELEMENT_ARRAY_BUFFER if is_index else _GL_ARRAY_BUFFER})
        self.bin.extend(data.tobytes())
        accessor = {"bufferView": len(self.gltf["bufferViews"]) - 1, "count": len(data)}
        if is_index:
            accessor.update(componentType=_GL_UNSIGNED_INT, type="SCALAR")
        else:
            accessor.update(componentType=_GL_FLOAT, type="VEC3", min=data.min(axis=0).tolist(), max=data.max(axis=0).tolist())
        self.gltf["accessors"].append(accessor)
        return len(self.gltf["accessors"]) - 1

    def add_node(self, name, rgb, tris, lines):
        # type: (str, tuple, tuple, tuple) -> None
        """레이어 하나 — tris·lines = (정점, 인덱스) 또는 None. 둘 다 없으면 노드를 만들지 않는다."""
        primitives = []
        material = len(self.gltf["materials"])
        for arrays, mode in ((tris, _GL_TRIANGLES), (lines, _GL_LINES)):
            if arrays is None:
                continue
            points, indices = arrays
            y_up = numpy.column_stack([points[:, 0], points[:, 2], -points[:, 1]])
            primitives.append({"attributes": {"POSITION": self._add_accessor(y_up, False)}, "indices": self._add_accessor(indices, True),
                               "material": material, "mode": mode})
        if not primitives:
            return
        self.gltf["materials"].append({"name": name, "doubleSided": True, "pbrMetallicRoughness": {
            "baseColorFactor": [_get_linear(c) for c in rgb] + [1.0], "metallicFactor": 0.0, "roughnessFactor": 1.0}})
        self.gltf["meshes"].append({"name": name, "primitives": primitives})
        self.gltf["nodes"].append({"name": name, "mesh": len(self.gltf["meshes"]) - 1})
        self.gltf["scenes"][0]["nodes"].append(len(self.gltf["nodes"]) - 1)

    def get_bytes(self, extras):
        # type: (dict) -> bytes
        self.gltf["asset"]["extras"] = extras
        self.bin.extend(b"\0" * (-len(self.bin) % 4))
        self.gltf["buffers"] = [{"byteLength": len(self.bin)}]
        text = json.dumps(self.gltf, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        text += b" " * (-len(text) % 4)
        total = 12 + 8 + len(text) + 8 + len(self.bin)
        return (struct.pack("<III", 0x46546C67, 2, total) + struct.pack("<II", len(text), 0x4E4F534A) + text
                + struct.pack("<II", len(self.bin), 0x004E4942) + bytes(self.bin))
