"""메시 컨텍스트 지오메트리 — Prepared(세계좌표 m) → 로컬 좌표 메시·커브 데이터(BakeItem). context_geometry의 메시판.

    build(prepared) -> ContextGeo                    지형·건물·커브 전부(context_geometry.ContextGeo와 같은 모양)
    build_terrain(prepared) -> (meshes, tris, counts)
    build_buildings(prepared, ground) -> (items, counts, skipped, warnings)
    build_curves(prepared) -> items

호스트 문서는 쓰지 않는다 — 정점·면 목록만 만들고 장면은 베이커(blender_baker)가 만진다. CDT·지반 높이 조회는 mathutils(delaunay_2d_cdt·BVHTree).
규칙(TIN 입력점·분류 우선순위·수면·대상지 평탄화·건물 바닥 = 발자국 정점의 최저 지반) — 범위 링·분류 폴리곤 링·대상지 링을 제약 면으로
TIN 점과 함께 CDT 한 번 → 삼각형마다 자기를 품은 입력 링으로 분류 → 정점 Z = TIN 수직 투영. 원점 적용(세계 → 로컬)은 이 파일의 get_local_pts 한 함수에서만 한다.
"""
# [blender-cut]
# SketchUp 사이드카(번들 파이썬)도 이 파일을 쓴다 — mathutils가 없으면 shapely(GEOS — 겹치기 + 제약 들로네, numpy) + 격자 점 찾기로 같은 모양의 출력을 만든다.
# 면 채우기가 없어 건물은 각기둥(링·바닥·높이)으로 넘기고 SketchUp이 구멍 있는 면을 그대로 만든다(BakeItem.prisms).
# Shewchuk triangle은 상업 사용 제한 약관이라 쓰지 않는다. Blender 확장 패키지는 [blender-cut] 구간을 뺀다(dev_deploy.get_blender_source)
# [/blender-cut]

import math
import time
from dataclasses import dataclass, field

try:   # Blender
    from mathutils import Vector, geometry
    from mathutils.bvhtree import BVHTree
except ImportError:   # mathutils 없음 — python3 시험·아래 [blender-cut] 구간
    geometry = None
# [blender-cut]
if geometry is None:
    import numpy
    import shapely
# [/blender-cut]

import constants
import context_report
import non_rhino_utils
from context_geometry import (CLASS_LAYERS, SITE_LAYERS, TOPO_SOURCE_ID, ContextGeo, NearestXYZ, get_building_attrs, get_class_polygons, get_parts,
                              get_tin_points, get_zoning_rings)
from i18n import tr

_DOWN = Vector((0.0, 0.0, -1.0)) if geometry is not None else None


@dataclass
class BakeItem:
    """베이크 한 건 = 객체 하나. layer = 컬렉션 이름('CTX::Buildings'), 좌표는 로컬 m.
    메시는 verts [(x, y, z)] + faces [(a, b, c[, d])] (+ face_attrs {이름: 면마다 값}), 커브는 polylines [([(x, y, z)], 닫힘)].
    attrs는 객체 사용자 속성(키 → str)."""

    layer: str
    name: str
    verts: list = field(default_factory=list)
    faces: list = field(default_factory=list)
    polylines: list = field(default_factory=list)
    attrs: dict = field(default_factory=dict)
    face_attrs: dict = field(default_factory=dict)
    # [blender-cut] 각기둥(SketchUp 건물) prisms [(파트 [[외곽 링, 구멍 링…]…], 바닥 Z, 높이, 속성 dict, 이름)] — 동 하나 = 그룹 하나(Rhino판 동별 객체와 같은 속성)
    prisms: list = field(default_factory=list)
    # [/blender-cut]


def get_local_pts(coords, origin, z=None):
    # type: (list, tuple, float) -> list
    """세계좌표 → 로컬 ``[(x, y, z)]``. 원점(E, N)을 빼는 유일한 자리(Blender판). Z는 z 인자 → 좌표의 세 번째 값 → 0 순."""
    ox, oy = float(origin[0]), float(origin[1])
    return [(float(c[0]) - ox, float(c[1]) - oy, z if z is not None else (float(c[2]) if len(c) > 2 else 0.0)) for c in coords]


def _layer(name):
    # type: (str) -> str
    return "%s::%s" % (constants.CTX_ROOT_LAYER, name)


def _get_local_ring(ring, origin):
    # type: (list, tuple) -> list
    """세계좌표 링 → 로컬 2D 반시계 링(1 mm 안 중복점·닫힘 중복점 제거)."""
    return non_rhino_utils.get_clean_ring([(x, y) for x, y, _z in get_local_pts(ring, origin)])


def _is_ccw(a, b, c):
    # type: (tuple, tuple, tuple) -> bool
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]) > 0


def _get_tin(local_pts, epsilon):
    # type: (list, float) -> tuple
    """로컬 (x, y, z) 점 → 들로네 TIN(볼록 껍질). 출력: (정점 [(x, y, z)], 반시계 삼각형 [(a, b, c)]). 같은 자리 점은 하나만 쓴다."""
    if geometry is not None:
        out = geometry.delaunay_2d_cdt([Vector(p[:2]) for p in local_pts], [], [], 0, epsilon)
        return [(v.x, v.y, local_pts[orig[0]][2]) for v, orig in zip(out[0], out[3])], [tuple(f) for f in out[2]]
    # [blender-cut] shapely판
    index = {}
    for i, p in enumerate(local_pts):
        index.setdefault((float(p[0]), float(p[1])), i)
    tris = shapely.get_parts(shapely.delaunay_triangles(shapely.multipoints([p[:2] for p in local_pts])))
    corners = shapely.get_coordinates(shapely.get_exterior_ring(tris)).reshape(-1, 4, 2)[:, :3, :].tolist()
    faces = []
    for a, b, c in corners:   # GEOS는 입력 좌표를 그대로 옮긴다 — 좌표로 입력 번호를 찾는다
        face = (index[tuple(a)], index[tuple(b)], index[tuple(c)])
        faces.append(face if _is_ccw(a, b, c) else (face[0], face[2], face[1]))
    return [(float(p[0]), float(p[1]), p[2]) for p in local_pts], faces
    # [/blender-cut]


def _get_cdt(rings, loose_pts, epsilon):
    # type: (list, list, float) -> tuple
    """로컬 2D 링마다 제약 면 하나 + 떨어진 점 → CDT(면 안 삼각형만).

    출력: (정점 [(x, y)], 반시계 삼각형 [(a, b, c)], 삼각형마다 자기를 품은 링 번호 집합). 겹친 링은 전부 들어간다.
    """
    # [blender-cut]
    if geometry is None:
        return _get_overlay_cdt(rings, loose_pts, epsilon)
    # [/blender-cut]
    verts, faces = [], []
    for ring in rings:
        start = len(verts)
        verts.extend(Vector(p) for p in ring)
        faces.append(list(range(start, len(verts))))
    verts.extend(Vector(p[:2]) for p in loose_pts)
    out_verts, _edges, out_faces, _orig_verts, _orig_edges, orig_faces = geometry.delaunay_2d_cdt(verts, [], faces, 1, epsilon)
    xy = [(v.x, v.y) for v in out_verts]
    tris = []
    for face in out_faces:
        a, b, c = face
        tris.append((a, b, c) if _is_ccw(xy[a], xy[b], xy[c]) else (a, c, b))
    return xy, tris, [set(o) for o in orig_faces]


# [blender-cut] shapely판 CDT
def _get_valid_polygon(polygon, epsilon):
    # type: (object, float) -> object
    """자기교차 링(OSM 도로면 버퍼의 짧은 변 안쪽 고리) → make_valid 결과 중 가장 넓은 폴리곤 하나(분류는 링 번호 = 입력 순서라 하나만) → epsilon 격자.
    set_precision은 유효하지 않은 입력에 'side location conflict'를 던지므로 make_valid를 먼저 한다(신주쿠 2026-10-22)."""
    if not shapely.is_valid(polygon):
        parts = [g for g in shapely.get_parts(shapely.make_valid(polygon)) if shapely.get_type_id(g) == 3]
        polygon = max(parts, key=shapely.area) if parts else polygon
    try:
        return shapely.set_precision(polygon, epsilon)
    except shapely.errors.GEOSException:
        return polygon


def _get_overlay_cdt(rings, loose_pts, epsilon):
    # type: (list, list, float) -> tuple
    """_get_cdt의 shapely(GEOS)판 — 같은 모양의 출력을 겹치기(overlay)로 만든다.
    링 테두리를 epsilon 격자로 이어 붙여(교점 포함) 면으로 나누면 면마다 품은 링이 정해진다(대표점 within) → 떨어진 점의 들로네 TIN
    삼각형과 면을 겹쳐 조각 → 조각을 제약 들로네로 삼각형. TIN 껍질 밖의 면은 그대로 삼각형으로 만든다(높이는 지반 조회 폴백).
    ponytail: 삼각형이 CDT 한 번보다 많다(TIN 삼각형이 면 경계에서 잘린다) — 성수 500 m 2배 안팎."""
    polys = numpy.array([_get_valid_polygon(shapely.Polygon(ring), epsilon) for ring in rings], dtype=object)
    noded = shapely.unary_union(shapely.get_exterior_ring(polys), grid_size=epsilon)
    cells = shapely.get_parts(shapely.polygonize(shapely.get_parts(noded)))
    cell_rings = [set() for _ in range(len(cells))]
    for cell, ring in zip(*shapely.STRtree(polys).query(shapely.point_on_surface(cells), predicate="within").tolist()):
        cell_rings[cell].add(ring)
    pieces, owners = cells, numpy.arange(len(cells))
    if loose_pts:
        points = shapely.multipoints([p[:2] for p in loose_pts])
        tin = shapely.get_parts(shapely.delaunay_triangles(points))
        cell_ids, tin_ids = shapely.STRtree(tin).query(cells, predicate="intersects")
        outside = shapely.difference(cells, shapely.convex_hull(points), grid_size=epsilon)
        keep = ~shapely.is_empty(outside)
        try:
            cut = shapely.intersection(cells[cell_ids], tin[tin_ids], grid_size=epsilon)
        except shapely.errors.GEOSException:   # 스냅 반올림이 드물게 'Ring edge missing'(신주쿠 OSM 도로면 버퍼 2026-10-22) — 격자 없이 자르고 뒤에 맞춘다
            cut = shapely.set_precision(shapely.intersection(shapely.make_valid(cells[cell_ids]), tin[tin_ids]), epsilon)
        pieces = numpy.concatenate([cut, outside[keep]])
        owners = numpy.concatenate([cell_ids, numpy.nonzero(keep)[0]])
    parts, piece_ids = shapely.get_parts(shapely.constrained_delaunay_triangles(pieces), return_index=True)
    is_tri = shapely.get_type_id(parts) == 3
    parts, piece_ids = parts[is_tri], piece_ids[is_tri]
    corners = shapely.get_coordinates(shapely.get_exterior_ring(parts)).reshape(-1, 4, 2)[:, :3, :]
    keys = numpy.round(corners.reshape(-1, 2) / epsilon).astype(numpy.int64)
    _keys, first, inverse = numpy.unique(keys, axis=0, return_index=True, return_inverse=True)
    xy = corners.reshape(-1, 2)[first]
    tris = inverse.reshape(-1, 3)
    a, b, c = xy[tris[:, 0]], xy[tris[:, 1]], xy[tris[:, 2]]
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    tris[cross < 0] = tris[cross < 0][:, [0, 2, 1]]
    valid = (cross != 0) & (tris[:, 0] != tris[:, 1]) & (tris[:, 1] != tris[:, 2]) & (tris[:, 0] != tris[:, 2])
    inside = [cell_rings[cell] for cell in owners[piece_ids[valid]].tolist()]
    return [tuple(p) for p in xy.tolist()], [tuple(t) for t in tris[valid].tolist()], inside
# [/blender-cut]


class _Ground(object):
    """지반 메시의 높이 조회 — 위에서 수직으로 쏴(BVH 광선) 첫 면의 Z, 빗나가면 최근접 정점 Z(context_geometry._drape 폴백과 같다)."""

    def __init__(self, verts, faces):
        # type: (list, list) -> None
        self.verts = verts
        self.misses = 0
        self._nearest = None
        if geometry is not None:
            self.bvh = BVHTree.FromPolygons([Vector(v) for v in verts], faces)
            self.top = max(v[2] for v in verts) + 100.0
            return
        # [blender-cut] shapely판 — 격자 칸에 걸친 삼각형(4각형은 둘로)의 무게중심 좌표. 수직 면은 건너뛰고 겹치면 가장 높은 면
        self.cell = constants.SKETCHUP_GROUND_CELL
        self.cells = {}
        for face in faces:
            for a, b, c in ((face[0], face[k], face[k + 1]) for k in range(1, len(face) - 1)):
                (x0, y0, z0), (x1, y1, z1), (x2, y2, z2) = verts[a], verts[b], verts[c]
                det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
                if abs(det) < 1e-9:
                    continue
                tri = (x0, y0, z0, x1 - x0, y1 - y0, x2 - x0, y2 - y0, 1.0 / det, z1 - z0, z2 - z0)
                for i in range(int(math.floor(min(x0, x1, x2) / self.cell)), int(math.floor(max(x0, x1, x2) / self.cell)) + 1):
                    for j in range(int(math.floor(min(y0, y1, y2) / self.cell)), int(math.floor(max(y0, y1, y2) / self.cell)) + 1):
                        self.cells.setdefault((i, j), []).append(tri)
        # [/blender-cut]

    def get_z(self, x, y):
        # type: (float, float) -> float
        z = self.hit_z(x, y)
        return self.get_nearest_z(x, y) if z is None else z

    def hit_z(self, x, y):
        # type: (float, float) -> float
        """수직 투영 Z, 빗나가면 None."""
        if geometry is not None:
            hit = self.bvh.ray_cast(Vector((x, y, self.top)), _DOWN)[0]
            return None if hit is None else hit.z
        # [blender-cut] shapely판
        best = None
        for x0, y0, z0, e1x, e1y, e2x, e2y, inv, dz1, dz2 in self.cells.get((int(math.floor(x / self.cell)), int(math.floor(y / self.cell))), ()):
            dx, dy = x - x0, y - y0
            u = (dx * e2y - dy * e2x) * inv
            v = (e1x * dy - e1y * dx) * inv
            if u >= -1e-9 and v >= -1e-9 and u + v <= 1.0 + 1e-9:
                z = z0 + u * dz1 + v * dz2
                if best is None or z > best:
                    best = z
        return best
        # [/blender-cut]

    def get_nearest_z(self, x, y):
        # type: (float, float) -> float
        self.misses += 1
        if self._nearest is None:
            self._nearest = NearestXYZ(self.verts, constants.CLASSIFY_GRID)
        z = self._nearest.nearest_z(x, y)
        return 0.0 if z is None else z


def _get_mesh(tris, xy, zs, z=None):
    # type: (list, list, dict, float) -> tuple
    """삼각형(공용 정점 번호) → 따로 쓰는 (정점, 면). 쓰는 정점만 새 번호로. z를 주면 모든 Z를 그 값으로."""
    remap, verts, faces = {}, [], []
    for tri in tris:
        face = []
        for i in tri:
            if i not in remap:
                remap[i] = len(verts)
                verts.append((xy[i][0], xy[i][1], zs[i] if z is None else z))
            face.append(remap[i])
        faces.append(tuple(face))
    return verts, faces


def _join(meshes):
    # type: (list) -> tuple
    """(정점, 면) 여럿 → 하나(정점 번호를 밀어 붙인다)."""
    verts, faces = [], []
    for mesh_verts, mesh_faces in meshes:
        start = len(verts)
        verts.extend(mesh_verts)
        faces.extend(tuple(start + i for i in face) for face in mesh_faces)
    return verts, faces


def _get_site_wall(tris, xy, zs, level, step=0.0):
    # type: (list, list, dict, float, float) -> tuple
    """평탄면과 주변 지반 사이 수직 벽 — 대상지 삼각형의 바깥 변(반대 방향 변이 없는 변)마다 평탄 높이 ↔ 자연 지반.
    윗선이 주변 지형과 같은 정점이라 틈이 없다(context_geometry._get_site_wall과 같은 규칙). step > 0이면 윗선 = 주변 계단 단 높이."""
    edges = {(t[k], t[(k + 1) % 3]) for t in tris for k in range(3)}
    index, verts, faces = {}, [], []

    def vertex(p):
        if p not in index:
            index[p] = len(verts)
            verts.append(p)
        return index[p]

    for i, j in edges:
        if (j, i) in edges:
            continue
        for a, b in non_rhino_utils.get_stepped_edges((xy[i][0], xy[i][1], zs[i]), (xy[j][0], xy[j][1], zs[j]), step):
            da, db = abs(a[2] - level) > 1e-4, abs(b[2] - level) > 1e-4
            if not da and not db:
                continue
            a0, b0 = vertex((a[0], a[1], level)), vertex((b[0], b[1], level))
            if da and db:
                faces.append((a0, b0, vertex(b), vertex(a)))
            elif db:
                faces.append((a0, b0, vertex(b)))
            elif da:
                faces.append((a0, b0, vertex(a)))
    return verts, faces


def build_terrain(prepared):
    # type: (object) -> tuple
    """TIN(보간용) → 범위·분류·대상지 링 제약 CDT → 삼각형 분류 → TIN 높이 → 분류별 메시 (context_geometry.build_terrain과 같은 출력 규칙).

    입력: Prepared(세계좌표). options.flatten_site·flatten_level(mean|min|max)·site_output(mesh|curve) — 대상지 처리는 lots·area만.
          options.terrain_step(m, 0 = 매끈) — 지반 메시를 계단형으로(평탄면·원지형 사본은 그대로, 경계 벽 윗선은 계단에 맞춘다).
    처리: get_tin_points → CDT(볼록 껍질) = TIN → 범위 링(면 0) + 범위 bbox와 겹치는 분류 폴리곤 링(외곽·구멍) + 대상지 링을 제약 면으로,
          TIN 점을 내부 정점으로 다시 CDT → 범위 안 삼각형만, 품은 링으로 분류(외곽 안 + 같은 파트 구멍 밖, TERRAIN_CLASS_PRIORITY 앞이 이김)
          → 정점 Z = TIN 투영 → 수면은 폴리곤별 최저 Z + WATER_LIFT 평면 → 대상지 평탄면·경계 벽·원지형.
    출력: ``(meshes, tris_world, counts)``. meshes = {"all": 건물 투영용 지반, "terrain"|"water"|"road"|"green"|"rail"|"site_ground"|"site_wall"|
          "site_original": (정점, 면)}. tris_world = 세계좌표 TIN 삼각형 [((x,y,z)×3, "terrain"|"outside")] — 시트 12·13.
    """
    origin = prepared.origin
    ox, oy = float(origin[0]), float(origin[1])
    options = prepared.request.get("options") or {}
    eps = constants.CDT_EPSILON
    points, _water_polys, counts = get_tin_points(prepared)

    t = time.time()
    local_pts = get_local_pts(points, origin)
    tin_verts, tin_faces = _get_tin(local_pts, eps)
    if not tin_faces:
        raise RuntimeError(tr("지형 TIN 생성 실패 — 입력점 {0}", len(points)))
    tin = _Ground(tin_verts, tin_faces)
    counts.update(tin_s=round(time.time() - t, 3), tin_faces=len(tin_faces))

    # 시트용 자연 지형 삼각형 = TIN(세계좌표)
    ext_ring = prepared.extent_ring
    wx0, wy0, wx1, wy1 = non_rhino_utils.get_bbox(ext_ring)
    tris_world = []
    for a, b, c in tin_faces:
        pa, pb, pc = ((tin_verts[i][0] + ox, tin_verts[i][1] + oy, tin_verts[i][2]) for i in (a, b, c))
        x, y = (pa[0] + pb[0] + pc[0]) / 3.0, (pa[1] + pb[1] + pc[1]) / 3.0
        inside = wx0 <= x <= wx1 and wy0 <= y <= wy1 and non_rhino_utils.is_point_in_ring(x, y, ext_ring)
        tris_world.append((pa, pb, pc, "terrain" if inside else "outside"))

    # 제약 링 — 0 = 범위, 다음 = 분류 폴리곤(범위 bbox와 겹치는 파트만), 끝 = 대상지
    rings, owners = [_get_local_ring(ext_ring, origin)], [None]
    polys = get_class_polygons(prepared)
    for index, (cls, _name, parts) in enumerate(polys):
        prio = constants.TERRAIN_CLASS_PRIORITY.index(cls)
        for part_no, part in enumerate(parts):
            if not part:
                continue
            r0, s0, r1, s1 = non_rhino_utils.get_bbox(part[0])
            if r1 < wx0 or r0 > wx1 or s1 < wy0 or s0 > wy1:
                continue
            for k, ring in enumerate(part):
                local = _get_local_ring(ring, origin)
                if len(local) >= 3:
                    rings.append(local)
                    owners.append((prio, index, part_no, k == 0))
    mode = getattr(prepared, "mode", "lots")
    site_world = getattr(prepared, "site_rings", None) or []
    flatten = bool(options.get("flatten_site")) and mode in ("lots", "area") and bool(site_world)
    site_mesh_out = options.get("site_output") == "mesh" and mode in ("lots", "area") and bool(site_world)
    separate_site = flatten or site_mesh_out
    site_start = len(rings)
    if separate_site:
        rings += [_get_local_ring(ring, origin) for ring in site_world]

    t = time.time()
    xy, tris, inside_rings = _get_cdt(rings, local_pts, eps)
    counts["regions"] = len(rings)
    counts["split_s"] = round(time.time() - t, 3)

    # 삼각형 분류
    t = time.time()
    buckets, water_regions = {}, {}
    for tri, inside in zip(tris, inside_rings):
        if 0 not in inside:
            continue
        if separate_site and any(i >= site_start for i in inside):
            buckets.setdefault("site", []).append(tri)
            continue
        parts = {}
        for i in inside:
            if 0 < i < site_start:
                prio, index, part_no, outer = owners[i]
                state = parts.setdefault((index, part_no), [prio, False, False])
                state[1 if outer else 2] = True
        best = min(((prio, index) for (index, _p), (prio, outer, hole) in parts.items() if outer and not hole), default=None)
        cls = constants.TERRAIN_CLASS_PRIORITY[best[0]] if best else "terrain"
        buckets.setdefault(cls, []).append(tri)
        if cls == "water":
            water_regions.setdefault(best[1], []).append(tri)
    counts["classify_s"] = round(time.time() - t, 3)

    t = time.time()
    used = {i for group in buckets.values() for tri in group for i in tri}
    zs = {i: tin.get_z(xy[i][0], xy[i][1]) for i in used}
    counts["drape_missing"] = tin.misses
    counts["drape_s"] = round(time.time() - t, 3)

    meshes = {}
    for cls in ("terrain", "road", "green", "rail"):
        if buckets.get(cls):
            meshes[cls] = _get_mesh(buckets[cls], xy, zs)
    # 수면 — 수면 폴리곤별 최저 Z = 수위, 평면 + WATER_LIFT
    water_bodies, water_parts = [], []
    for index in sorted(water_regions):
        level = min(zs[i] for tri in water_regions[index] for i in tri)
        body = _get_mesh(water_regions[index], xy, zs, level + constants.WATER_LIFT)
        water_parts.append(body)
        water_bodies.append({"name": polys[index][1], "level": round(level, 2), "faces": len(body[1])})
    if water_parts:
        meshes["water"] = _join(water_parts)
    counts["water_bodies"] = water_bodies
    step = float(options.get("terrain_step") or 0)
    if step > 0:
        t = time.time()
        for cls in ("terrain", "road", "green", "rail", "water"):
            if cls in meshes:
                meshes[cls] = non_rhino_utils.get_stepped_mesh(*meshes[cls], step=step)
        counts.update(terrain_step=step, step_s=round(time.time() - t, 3))

    # 대상지 — 바닥 메시(원지형) 또는 평탄면 + 벽 + 원지형 사본(숨김 컬렉션)
    ground_parts = [meshes[cls] for cls in ("terrain", "road", "green", "rail") if cls in meshes]
    if buckets.get("site"):
        site_tris = buckets["site"]
        if flatten:
            how = options.get("flatten_level") or "mean"
            edge_zs = [tin.get_z(x, y) for ring in rings[site_start:]
                       for x, y in non_rhino_utils.get_resampled_ring(ring, constants.TERRAIN_GRID, True)]
            if not edge_zs:
                raise RuntimeError(tr("대상지 경계에서 지반 높이를 읽지 못했습니다"))
            level = min(edge_zs) if how == "min" else max(edge_zs) if how == "max" else sum(edge_zs) / len(edge_zs)
            meshes.update(site_ground=_get_mesh(site_tris, xy, zs, level), site_wall=_get_site_wall(site_tris, xy, zs, level, step),
                          site_original=_get_mesh(site_tris, xy, zs))
            counts.update(site_level=round(level, 2), site_level_how=how)
        else:
            meshes["site_ground"] = _get_mesh(site_tris, xy, zs)
            if step > 0:
                meshes["site_ground"] = non_rhino_utils.get_stepped_mesh(*meshes["site_ground"], step=step)
        counts["site_output"] = "mesh" if site_mesh_out else "flatten_only"
        ground_parts.append(meshes["site_ground"])
    meshes["all"] = _join(ground_parts)
    if not meshes["all"][1]:
        raise RuntimeError(tr("범위 안 지형 면이 없습니다"))
    surfaces = ("terrain", "road", "green", "rail", "site_ground")
    counts["faces"] = sum(len(m[1]) for k, m in meshes.items() if k in surfaces)
    counts["quads"] = 0
    counts["faces_by_class"] = {k: len(m[1]) for k, m in meshes.items() if k != "all"}
    return meshes, tris_world, counts


def _get_terrain_items(meshes, counts):
    # type: (dict, dict) -> list
    """분류별 메시 → BakeItem(context_geometry._get_terrain_items와 같은 레이어·속성). 구조물 위 표고점은 Blender판에서 뺀다."""
    items = []
    for cls, (verts, faces) in meshes.items():
        if cls == "all" or not faces:
            continue
        if cls == "terrain":
            attrs = {"SRC": TOPO_SOURCE_ID, "RESAMPLE_M": "%g" % constants.TERRAIN_RESAMPLE, "N_POINTS": str(counts["tin_points"])}
        elif cls == "water":
            bodies = counts["water_bodies"]
            attrs = {"NAME": "; ".join(b["name"] for b in bodies), "LEVEL_M": "; ".join("%.2f" % b["level"] for b in bodies),
                     "LEVEL_SRC": "terrain_min"}
        elif cls.startswith("site_"):
            flat = "site_level" in counts
            attrs = {"KIND": {"site_ground": "flattened" if flat else "natural", "site_wall": "edge_wall", "site_original": "natural"}[cls]}
            if flat:
                attrs.update(LEVEL_M="%.2f" % counts["site_level"], LEVEL_SRC="site_edge_%s" % counts["site_level_how"])
        else:
            attrs = {"SRC": TOPO_SOURCE_ID}
        if cls == "site_ground":   # 바닥 메시 출력이면 대상지 색(CTX::Site::ground), 평탄화만이면 지형 색
            layer = "Site::ground" if counts.get("site_output") == "mesh" else "Terrain::site_flat"
        else:
            layer = SITE_LAYERS.get(cls) or CLASS_LAYERS[cls]
        items.append(BakeItem(_layer(layer), layer.split("::")[-1].lower(), verts=verts, faces=faces, attrs=attrs))
    return items


# ── 건물 ───────────────────────────────────────────────────

def _add_prism(verts, faces, rings, base_z, height):
    # type: (list, list, list, float, float) -> int
    """로컬 2D 링(외곽 + 구멍) → 닫힌 각기둥 면을 verts·faces에 붙인다. 뚜껑은 mathutils 면 채우기(구멍 포함).
    출력: 붙인 면 수(0 = 채우기 실패 — 자기교차 발자국 등)."""
    rings = [ring for ring in rings if len(ring) >= 3]
    if not rings:
        return 0
    flat = [rings[0]] + [list(reversed(ring)) for ring in rings[1:]]   # 외곽 반시계, 구멍 시계 — 옆면 법선이 바깥(구멍 쪽)을 본다
    tris = geometry.tessellate_polygon([[(x, y, 0.0) for x, y in ring] for ring in flat])
    if not tris:
        return 0
    pts = [p for ring in flat for p in ring]
    n, start = len(pts), len(verts)
    verts.extend((x, y, base_z) for x, y in pts)
    verts.extend((x, y, base_z + height) for x, y in pts)
    for a, b, c in tris:
        if not _is_ccw(pts[a], pts[b], pts[c]):
            b, c = c, b
        faces.append((start + n + a, start + n + b, start + n + c))   # 위 — 반시계(법선 +Z)
        faces.append((start + a, start + c, start + b))               # 바닥 — 반대
    k = 0
    for ring in flat:
        m = len(ring)
        for i in range(m):
            a, b = start + k + i, start + k + (i + 1) % m
            faces.append((a, b, b + n, a + n))
        k += m
    return 2 * len(tris) + n


def build_buildings(prepared, ground):
    # type: (object, tuple) -> tuple
    """범위 안 건물 → 건물 메시 하나(면 속성 building_id·height·floors) (context_geometry.build_buildings와 같은 바닥·폴백 규칙).

    입력: Prepared, ground = build_terrain()의 meshes["all"](로컬 (정점, 면)).
    처리: 발자국 정점마다 지반 수직 투영 → 동별 최저 Z(base)·고저차 → 투영이 하나도 안 맞은 동은 ① bbox 중심의 최근접 지반 정점 Z
          ② 없으면 건너뜀 → 파트별 각기둥. 동마다 객체를 만들면 수천 개라 Blender가 느려진다 — 한 메시 + 면 속성으로 묶는다.
    출력: ``(items, counts, skipped, warnings)``.
    """
    origin = prepared.origin
    buildings = context_report.get_buildings_in_extent(prepared)
    surface = _Ground(*ground)
    counts = {"buildings_in_extent": len(buildings), "fallback_nearest": 0, "fallback_skipped": 0, "extrude_failed": 0, "parts": 0, "slope_flagged": 0}
    verts, faces, ids, heights, floors = [], [], [], [], []
    # [blender-cut]
    prisms = []
    # [/blender-cut]
    skipped = []
    t = time.time()
    for b in buildings:
        parts = [[_get_local_ring(ring, origin) for ring in part] for part in get_parts(b.geometry)]
        if not parts or b.height_m <= 0:
            skipped.append(tr("{0}(빈 발자국·높이 0)", b.building_id))
            counts["fallback_skipped"] += 1
            continue
        zs = [z for part in parts for ring in part for z in (surface.hit_z(x, y) for x, y in ring) if z is not None]
        if zs:
            base_z, top = min(zs), max(zs)
        else:
            # 폴백 ① — 투영에 빗나간 동(지반 가장자리): bbox 중심의 최근접 지반 정점 Z
            cx, cy, _z = get_local_pts([((b.min_x + b.max_x) * 0.5, (b.min_y + b.max_y) * 0.5)], origin)[0]
            base_z = top = surface.get_nearest_z(cx, cy)
            counts["fallback_nearest"] += 1
        slope = top - base_z > constants.BUILDING_SLOPE_FLAG
        counts["slope_flagged"] += slope
        # [blender-cut] SketchUp(면 채우기 없음)은 동마다 각기둥 하나(prisms)로 넘긴다 — 구멍 있는 면·옆면은 SketchUp이 만든다
        if geometry is None:
            prisms.append((parts, base_z, float(b.height_m), get_building_attrs(b, b.height_src + ("~slope" if slope else "")), b.bld_nm))
            counts["parts"] += len(parts)
            continue
        # [/blender-cut]
        made = 0
        for part in parts:
            added = _add_prism(verts, faces, part, base_z, float(b.height_m))
            if added:
                ids.extend([int(b.building_id)] * added)
                heights.extend([float(b.height_m)] * added)
                floors.extend([int(b.grnd_flr or 0)] * added)
                made += 1
        counts["parts"] += made
        if not made:
            skipped.append(tr("{0}(압출 실패)", b.building_id))
            counts["extrude_failed"] += 1
    counts["extrude_s"] = round(time.time() - t, 3)
    counts["buildings"] = len(buildings) - counts["fallback_skipped"] - counts["extrude_failed"]
    items = []
    # [blender-cut]
    if prisms:
        items.append(BakeItem(_layer("Buildings"), "buildings", prisms=prisms, attrs={"COUNT": str(counts["buildings"])}))
    # [/blender-cut]
    if faces:
        items.append(BakeItem(_layer("Buildings"), "buildings", verts=verts, faces=faces,
                              attrs={"COUNT": str(counts["buildings"]), "HEIGHT_SRC": "see tables/buildings.csv"},
                              face_attrs={"building_id": ids, "height": heights, "floors": floors}))
    warnings = []
    if skipped:
        warnings.append({"level": "warn", "code": "skipped", "text": tr("건물 {0}동 건너뜀 — 투영·압출 실패", len(skipped)),
                         "detail": ", ".join(skipped[:20]), "action": None, "center": None})
    return items, counts, skipped, warnings


# ── 커브 ───────────────────────────────────────────────────

def build_curves(prepared):
    # type: (object) -> list
    """Site·Parcels·Roads::centerline·Ref(범위·도엽)·(옵션) Zoning::<구분>::<종류> 커브 Z=0 (context_geometry.build_curves와 같은 대상).
    Rhino는 필지마다 커브(PNU 속성)지만 여기는 레이어마다 객체 하나에 폴리라인 여럿 — 합필 전 필지(Site::lots)만 필지마다 객체."""
    origin = prepared.origin
    mode = getattr(prepared, "mode", "lots")

    def closed(ring):
        return get_local_pts(ring, origin, 0.0), True

    items = []
    targets = {lot.pnu for lot in prepared.target_lots} if mode == "lots" else set()
    if mode == "lots":   # 필지 방식 — 대상지 외곽(여러 필지면 합필한 외곽). 합필 전 필지는 Site::lots(기본 끔)
        merged = len(prepared.target_lots) > 1
        items.append(BakeItem(_layer("Site"), prepared.lot_name if merged else (prepared.target_lots[0].lot_number or prepared.target_lots[0].pnu),
                              polylines=[closed(ring) for ring in prepared.site_rings or []], attrs={"PNU": ",".join(sorted(targets)), "LOTS": str(len(targets))}))
        for lot in prepared.target_lots if merged else []:
            outer = max((part[0] for part in get_parts(lot.geometry) if part), key=non_rhino_utils.get_ring_area)
            items.append(BakeItem(_layer("Site::lots"), lot.lot_number or lot.pnu, polylines=[closed(outer)], attrs={"PNU": lot.pnu}))
    if mode == "area":   # 구역 방식 — 구역 링 하나, 안의 필지는 Parcels의 'parcels_in_site' 객체
        for ring in prepared.site_rings or []:
            items.append(BakeItem(_layer("Site"), "area", polylines=[closed(ring)],
                                  attrs={"KIND": "area", "AREA_M2": "%.1f" % non_rhino_utils.get_ring_area(ring), "LOTS": str(len(prepared.target_lots))}))
    in_site = {lot.pnu for lot in prepared.target_lots} if mode == "area" else set()
    parcels, parcels_in_site = [], []
    for lot in context_report.get_lots_in_extent(prepared):
        if lot.pnu in targets:
            continue
        rings = [closed(ring) for part in get_parts(lot.geometry) for ring in part]
        (parcels_in_site if lot.pnu in in_site else parcels).extend(rings)
    if parcels:
        items.append(BakeItem(_layer("Parcels"), "parcels", polylines=parcels))
    if parcels_in_site:
        items.append(BakeItem(_layer("Parcels"), "parcels_in_site", polylines=parcels_in_site, attrs={"IN_SITE": "1"}))
    ex0, ey0, ex1, ey1 = non_rhino_utils.get_bbox(prepared.extent_ring)
    roads = [(get_local_pts(f.geometry["coordinates"], origin, 0.0), False) for f in prepared.context.get_features("road", "centerline")
             if f.geometry.get("type") == "LineString" and not (f.max_x < ex0 or f.min_x > ex1 or f.max_y < ey0 or f.min_y > ey1)]
    if roads:
        items.append(BakeItem(_layer("Roads::centerline"), "road_centerlines", polylines=roads))
    items.append(BakeItem(_layer("Ref"), "extent", polylines=[closed(prepared.extent_ring)],
                          attrs={"KIND": "extent", "RADIUS_M": "%g" % prepared.radius, "SHAPE": prepared.shape}))
    sheets = []
    for code in (prepared.stats or {}).get("sheets") or []:
        left, bottom, right, top = non_rhino_utils.get_topo_sheet_bounds(code)
        sheets.append(closed([non_rhino_utils.get_tm_from_wgs84(lng, lat) for lng, lat in ((left, bottom), (right, bottom), (right, top), (left, top))]))
    if sheets:
        items.append(BakeItem(_layer("Ref"), "topo_sheets", polylines=sheets,
                              attrs={"KIND": "topo_sheet", "SHEETS": ",".join((prepared.stats or {}).get("sheets") or [])}))
    if (prepared.request.get("options") or {}).get("include_zoning"):   # 레이어(구분·종류)마다 객체 하나
        zoning = {}
        for layer, _overlay, ring in get_zoning_rings(prepared):
            zoning.setdefault(layer, []).append(closed(ring))
        for layer, rings in zoning.items():
            items.append(BakeItem(_layer(layer), layer.rpartition("::")[2], polylines=rings))
    return items


# ── 전체 ───────────────────────────────────────────────────

def build(prepared):
    # type: (object) -> ContextGeo
    """지형 → 건물 → 커브 순으로 전부 만들어 ContextGeo로 묶는다(phase 'terrain' 전체). 2D 도면(BM::)은 .ai·SVG로 충분해 메시판에서 뺀다."""
    meshes, tris, counts = build_terrain(prepared)
    items = _get_terrain_items(meshes, counts)
    b_items, b_counts, skipped, warnings = build_buildings(prepared, meshes["all"])
    items += b_items
    curve_items = build_curves(prepared)
    items += curve_items
    counts.update(b_counts)
    counts["curves"] = sum(len(item.polylines) for item in curve_items)
    counts["items"] = len(items)
    counts["demolished"] = 0
    return ContextGeo(items=items, terrain_tris_world=tris, counts=counts, skipped=skipped, warnings=warnings)
