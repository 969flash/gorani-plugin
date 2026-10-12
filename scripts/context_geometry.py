"""컨텍스트 지오메트리 — Prepared(세계좌표 m) → RhinoCommon 객체(로컬 좌표) BakeItem 목록 (docs/code_map.md §5~§7.1).

    build(prepared) -> ContextGeo                 지형·건물·커브 전부
    build_terrain(prepared) -> (meshes, tris, counts)   TIN → 면 분류 → 수면 평탄 → 분류별 Mesh
    build_buildings(prepared, tin_mesh) -> (items, counts, skipped, warnings)
    build_curves(prepared) -> items               Site·Parcels·Roads::centerline·Ref 범위·도엽 경계·(옵션) Zoning

RhinoDoc은 쓰지 않는다 — 객체를 만들어 돌려줄 뿐 문서는 context_baker가 만진다.
원점 적용(세계 → 로컬)은 get_local_pts 한 함수에서만 한다. sheet_svg용 삼각형은 세계좌표로 되돌려 준다.
"""

import math
import time
from dataclasses import dataclass, field

import Rhino
import Rhino.Geometry as rg
from Rhino.Geometry.Intersect import Intersection
from System.Collections.Generic import List

import basemap_ai
import constants
import context_report
import non_rhino_utils
import sheet_svg
from context_builder import DomainError

TOPO_SOURCE_ID = "ngii_topo_5000"
_CLASS_LAYERS = {"terrain": "Terrain", "water": "Water", "road": "Roads", "green": "Green", "rail": "Rail"}
_SITE_LAYERS = {"site_wall": "Terrain::site_wall", "site_original": "Terrain::site_original"}   # site_ground는 옵션 따라(_get_terrain_items)


@dataclass
class BakeItem:
    """베이크 한 건. layer는 FullPath('CTX::Buildings'), geometry는 로컬 좌표 RhinoCommon 객체, attrs는 UserString(키 → str).
    text_height는 TextEntity의 높이 m — 문서 밖 TextEntity의 TextHeight 속성은 믿을 수 없어(스타일이 문서에 없으면 1.0으로 읽힘) 따로 싣는다."""

    layer: str
    geometry: object
    attrs: dict = field(default_factory=dict)
    name: str = ""
    text_height: float = 0.0


@dataclass
class ContextGeo:
    """build()의 결과. terrain_tris_world는 세계좌표 [((x,y,z),(x,y,z),(x,y,z), class_name)] — sheet_svg용."""

    items: list = field(default_factory=list)
    terrain_tris_world: list = field(default_factory=list)
    counts: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


# ── 좌표 ───────────────────────────────────────────────────

def get_local_pts(coords, origin, z=None):
    # type: (list, tuple, float) -> list
    """세계좌표 → 로컬 Point3d 목록. 원점(E, N)을 빼는 유일한 자리.

    입력: coords ``[(x, y)]`` 또는 ``[(x, y, z)]``, origin ``(E, N)``, z: 주면 모든 점의 Z를 이 값으로.
    처리: x − E, y − N. Z는 z 인자 → 좌표의 세 번째 값 → 0 순.
    출력: ``[Rhino.Geometry.Point3d]``. 입력은 바꾸지 않는다.
    """
    ox, oy = float(origin[0]), float(origin[1])
    pts = []
    for c in coords:
        cz = z if z is not None else (float(c[2]) if len(c) > 2 else 0.0)
        pts.append(rg.Point3d(float(c[0]) - ox, float(c[1]) - oy, cz))
    return pts


def _layer(name):
    # type: (str) -> str
    return "%s::%s" % (constants.CTX_ROOT_LAYER, name)


def _warning(level, code, text, detail=""):
    # type: (str, str, str, str) -> dict
    """panel_ui.md 공통 경고 스키마 한 건(context_builder._warning과 같은 모양 — 순환 import를 피해 여기 둔다)."""
    return {"level": level, "code": code, "text": text, "detail": detail, "action": None, "center": None}


def _strip_ring(ring):
    # type: (list) -> list
    """GeoJSON 링 → ``[(x, y)]`` 닫힘 중복점 제거."""
    pts = [(float(p[0]), float(p[1])) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def _get_parts(geometry):
    # type: (dict) -> list
    """Polygon·MultiPolygon → ``[[outer, hole, ...], ...]`` (링은 _strip_ring). 다른 타입은 빈 목록."""
    if not geometry or geometry.get("type") not in ("Polygon", "MultiPolygon"):
        return []
    return [[_strip_ring(ring) for ring in part if len(ring) >= 3] for part in non_rhino_utils.get_polygon_parts_from_geojson(geometry)]


def _get_ring_crv(ring, origin, z):
    # type: (list, tuple, float) -> rg.PolylineCurve
    """``[(x, y)]`` 세계좌표 링 → 닫힌 PolylineCurve(로컬, Z 고정)."""
    pts = get_local_pts(ring, origin, z)
    pts.append(pts[0])
    return rg.PolylineCurve(pts)


def _get_prism_mesh(part, origin, base_z, height):
    # type: (list, tuple, float, float) -> rg.Mesh
    """건물 한 파트(외곽 링 + 구멍 링들, 세계좌표) → 닫힌 각기둥 Mesh(로컬). 실패면 None.

    Extrusion을 만들고 Rhino 내장 Mesh.CreateFromExtrusion(Minimal)으로 메시화한다 — 파이썬에서 정점을 하나씩 넣는 직접 조립(0.74 s)보다
    빠르고(3,454동 0.16 s) 결과가 같다(면 44,423·전부 닫힘, 2026-10-08 실측).
    왜 Mesh인가: Extrusion 3,454동은 Rhino가 첫 음영 화면에서 동마다 렌더 메시를 만들어 18.7 s 멈춘다. 동별 Mesh는 0.9 s.
    """
    plane = rg.Plane(rg.Point3d(0, 0, base_z), rg.Vector3d.ZAxis)
    ext = rg.Extrusion.Create(_get_ring_crv(part[0], origin, base_z), plane, float(height), True)
    if ext is None:
        return None
    for hole in part[1:]:
        ext.AddInnerProfile(_get_ring_crv(hole, origin, base_z))
    return rg.Mesh.CreateFromExtrusion(ext, rg.MeshingParameters.Minimal)


class _NearestXYZ(object):
    """(x, y, z) 점의 격자 색인 — 최근접 점의 Z. 범위 링 정점·수면 경계·건물 폴백 ①이 쓴다."""

    def __init__(self, points, cell):
        # type: (list, float) -> None
        self.cell = float(cell)
        self._cells = {}
        for p in points:
            self._cells.setdefault(self._key(p[0], p[1]), []).append(p)

    def _key(self, x, y):
        # type: (float, float) -> tuple
        return int(math.floor(x / self.cell)), int(math.floor(y / self.cell))

    def nearest_z(self, x, y, max_rings=64):
        # type: (float, float, int) -> float
        """셀 링을 넓혀 가며 찾는다. 링 r에서 찾은 최단거리가 r×cell 이하면 확정. 못 찾으면 None."""
        ix, iy = self._key(x, y)
        best, best_d = None, None
        for r in range(max_rings):
            if r == 0:
                keys = [(ix, iy)]
            else:   # 링 r의 둘레 셀만
                keys = ([(ix + d, iy - r) for d in range(-r, r + 1)] + [(ix + d, iy + r) for d in range(-r, r + 1)]
                        + [(ix - r, iy + d) for d in range(-r + 1, r)] + [(ix + r, iy + d) for d in range(-r + 1, r)])
            for key in keys:
                for p in self._cells.get(key, ()):
                    d = (p[0] - x) ** 2 + (p[1] - y) ** 2
                    if best_d is None or d < best_d:
                        best, best_d = p, d
            if best is not None and best_d <= (r * self.cell) ** 2:
                break
        return best[2] if best is not None else None


# ── 지형 ───────────────────────────────────────────────────

def _get_class_polygons(prepared):
    # type: (object) -> list
    """면 분류 폴리곤 ``[(class, name, parts)]``. water = features 하천·실폭하천·호수 ∪ 지목 하천·구거·유지,
    rail = 철도부지선(면), road = 도로경계(면), green = 경지계 ∪ 지목 공원·임야·체육용지·유원지."""
    polys = []
    for f in prepared.features:
        cls = None
        if f.theme == "water" and f.kind in constants.WATER_SURFACE_KINDS:
            cls = "water"
        elif f.theme == "rail" and f.kind == "surface":
            cls = "rail"
        elif f.theme == "road" and f.kind == "surface":
            cls = "road"
        elif f.theme == "green":
            cls = "green"
        if cls:
            polys.append((cls, f.name or f.kind, _get_parts(f.geometry)))
    for lot in list(prepared.target_lots) + list(prepared.near_lots):
        if lot.land_category in constants.LAND_CATEGORIES_WATER:
            polys.append(("water", lot.land_category, _get_parts(lot.geometry)))
        elif constants.SHEET_LAND_CATEGORY_KEYS.get(lot.land_category) in ("park", "forest"):
            polys.append(("green", lot.land_category, _get_parts(lot.geometry)))
    return polys


def get_tin_points(prepared):
    # type: (object) -> tuple
    """TIN 입력점(세계좌표). 드라이버의 정밀도 검사도 이것과 비교한다.

    입력: Prepared. 처리: TIN 범위 = 범위 bbox ∪ 범위 안 건물 bbox + TERRAIN_MARGIN → 등고선 4 m 리샘플 + 표고점(spot_struct 제외)
          → (x, y) mm 단위 중복 제거 → 범위 링 정점(Z = 최근접 입력점) → 분류 폴리곤 경계 조밀화(수면 WATER_EDGE_STEP, 도로·철도·녹지 TERRAIN_RESAMPLE
          × radius/CONTEXT_RADIUS — 반경에 비례해 간격을 넓힌다, Z = 최근접, 범위 bbox 안만).
    출력: ``([(x, y, z)], water_polys, counts)``. 등고선·표고점이 0이면 DomainError(no_terrain_points).
    """
    buildings = context_report.get_buildings_in_extent(prepared)
    ex0, ey0, ex1, ey1 = non_rhino_utils.get_bbox(prepared.extent_ring)
    min_x, min_y, max_x, max_y = ex0, ey0, ex1, ey1
    for b in buildings:
        min_x, min_y, max_x, max_y = min(min_x, b.min_x), min(min_y, b.min_y), max(max_x, b.max_x), max(max_y, b.max_y)
    m = constants.TERRAIN_MARGIN
    min_x, min_y, max_x, max_y = min_x - m, min_y - m, max_x + m, max_y + m
    pts = {}

    def in_bounds(x, y):
        return min_x <= x <= max_x and min_y <= y <= max_y

    def add(x, y, z):
        if z is not None and in_bounds(x, y):
            pts[(round(x, 3), round(y, 3))] = (x, y, float(z))

    for f in prepared.context.get_features("terrain", "contour"):
        if f.value is None or f.geometry.get("type") != "LineString":
            continue
        for p in non_rhino_utils.get_resampled_ring(f.geometry["coordinates"], constants.TERRAIN_RESAMPLE, closed=False):
            add(p[0], p[1], f.value)
    for f in prepared.context.get_features("terrain", "spot"):
        if f.value is not None and f.geometry.get("type") == "Point":
            add(float(f.geometry["coordinates"][0]), float(f.geometry["coordinates"][1]), f.value)
    n_input = len(pts)
    if not n_input:
        raise DomainError("no_terrain_points", "범위 안 등고선·표고점이 없습니다 — 컨텍스트 DB 도엽을 확인하세요")
    nearest = _NearestXYZ(list(pts.values()), constants.CLASSIFY_GRID)
    for x, y in prepared.extent_ring:
        add(x, y, nearest.nearest_z(x, y))
    # 분류 폴리곤 경계 조밀화 — 수면 WATER_EDGE_STEP, 도로·철도·녹지 TERRAIN_RESAMPLE. 성수 fixture는 등고선·표고점이 689점뿐이라
    # (평지) 이 점이 없으면 범위 안 면 1,488개·도로면 124개로 분류가 무의미했다(job 1007-221623-027d).
    # 간격은 반경에 비례(R=500 4 m, R=1 km 8 m) — 폴리곤 수가 R²로 늘어 R=1 km에서 74,014점·148k면·분류 6.3 s였다(job 1007-225058)
    # ponytail: 그래도 점 수 ∝ R. 1 km 분류가 거슬리면 step ∝ R² 또는 범위 링 안(is_point_in_ring)만 넣기
    polys = _get_class_polygons(prepared)
    water_polys = [p for p in polys if p[0] == "water"]
    step_factor = max(1.0, float(prepared.radius) / constants.CONTEXT_RADIUS)
    for cls, _name, parts in polys:
        step = (constants.WATER_EDGE_STEP if cls == "water" else constants.TERRAIN_RESAMPLE) * step_factor
        for part in parts:
            for ring in part:
                for p in non_rhino_utils.get_resampled_ring(ring, step):
                    # 범위 bbox 안만(건물 bbox로 넓힌 TIN 여유 구역은 등고선·표고점만) — 범위 밖 점에 최근접 탐색을 돌리지 않는다(하천 필지는 수 km)
                    if ex0 <= p[0] <= ex1 and ey0 <= p[1] <= ey1:
                        add(p[0], p[1], nearest.nearest_z(p[0], p[1]))
    counts = {"tin_input": n_input, "tin_points": len(pts), "tin_bounds": (min_x, min_y, max_x, max_y),
              "struct_excluded": len(prepared.context.get_features("terrain", "spot_struct"))}
    return list(pts.values()), water_polys, counts


def _get_closed_crv(ring):
    # type: (list) -> rg.PolylineCurve
    """로컬 링 [(x, y)] → Z=0 닫힌 PolylineCurve."""
    pts = [rg.Point3d(x, y, 0.0) for x, y in ring]
    return rg.PolylineCurve(pts + [pts[0]])


def _get_region_meshes(ext_ring, cut_rings, edge, counts):
    # type: (list, list, float, dict) -> list
    """범위 평면 Brep 하나를 경계 커브(분류 폴리곤·대상지)로 면 분할 → Rhino 메싱(평면도 격자 — 안쪽 쿼드, 경계만 삼각형).
    면끼리 모서리를 공유하므로 이웃 영역 경계 정점이 같다(용접하면 이음매 없음). 입력은 로컬 m. 출력은 Brep 면 순서의 Mesh 목록(Z=0).
    2026-10-10: 격자를 경계로 자르면 계단(분류) 또는 243 s(SplitWithProjectedPolylines 643 링) — 이 방법은 반경 500 m 2.6 s."""
    tol = constants.GEOMETRY_TOLERANCE
    t = time.time()
    breps = rg.Brep.CreatePlanarBreps(_get_closed_crv(ext_ring), tol)
    if not breps:
        raise RuntimeError("범위 평면을 만들지 못했습니다")
    brep = breps[0]
    split = brep.Faces[0].Split(List[rg.Curve]([_get_closed_crv(r) for r in cut_rings]), tol) if cut_rings else None
    if split is None and cut_rings:
        counts["region_split_failed"] = True
    brep = split or brep
    counts["regions"] = brep.Faces.Count
    counts["split_s"] = round(time.time() - t, 3)
    mp = rg.MeshingParameters()
    mp.SimplePlanes = False                  # 평면도 격자로 — 기본(True)은 평면을 긴 삼각형 몇 개로 끝낸다
    mp.MaximumEdgeLength = edge
    mp.MinimumEdgeLength = 0.0001
    mp.GridAspectRatio = 1.0                 # 정사각 칸
    mp.GridAngle = 0.0
    mp.RefineGrid = False
    mp.JaggedSeams = False
    mp.Tolerance = 0.0
    return list(rg.Mesh.CreateFromBrep(brep, mp) or [])


def _drape(meshes, tin):
    # type: (list, rg.Mesh) -> None
    """메시들 정점 Z = TIN 수직 투영(전부 한 번에). TIN 밖 점은 최근접 TIN 정점 Z. 같은 XY는 같은 Z라 용접 뒤에도 이음매가 없다."""
    top = tin.GetBoundingBox(True).Max.Z + 100.0
    pts, owners = [], []
    for m_index, mesh in enumerate(meshes):
        mesh.Vertices.UseDoublePrecisionVertices = True
        for k, v in enumerate(mesh.Vertices.ToPoint3dArray()):
            pts.append(rg.Point3d(v.X, v.Y, top))
            owners.append((m_index, k))
    out, indices = _project_to_mesh(tin, pts)
    zs = [None] * len(pts)
    for pt, i in zip(out, indices):
        if zs[i] is None or pt.Z > zs[i]:
            zs[i] = pt.Z
    missing = [i for i, z in enumerate(zs) if z is None]
    if missing:
        nearest = _NearestXYZ([(v.X, v.Y, v.Z) for v in tin.Vertices.ToPoint3dArray()], constants.CLASSIFY_GRID)
        for i in missing:
            zs[i] = nearest.nearest_z(pts[i].X, pts[i].Y) or 0.0
    for (m_index, k), p, z in zip(owners, pts, zs):
        meshes[m_index].Vertices.SetVertex(k, p.X, p.Y, z)
    return len(missing)


def _join(meshes):
    # type: (list) -> rg.Mesh
    """메시들을 하나로 + 같은 정점 용접 + 법선. 비어 있으면 빈 Mesh."""
    joined = rg.Mesh()
    joined.Vertices.UseDoublePrecisionVertices = True
    for mesh in meshes:
        joined.Append(mesh)
    if joined.Vertices.Count:
        joined.Vertices.CombineIdentical(True, True)
        joined.Compact()
        joined.Normals.ComputeNormals()
    return joined


def _get_mesh_faces(mesh):
    # type: (rg.Mesh) -> tuple
    """(정점 [(x,y,z)], 면 [(a,b,c) 또는 (a,b,c,d)]) — .NET 호출을 면마다 하지 않게 한 번에(job 1007-221823-c0aa: 면마다 호출 2분)."""
    verts = [(p.X, p.Y, p.Z) for p in mesh.Vertices.ToPoint3dArray()]
    flat = list(mesh.Faces.ToIntArray(False))
    faces = []
    for i in range(0, len(flat), 4):
        a, b, c, d = flat[i], flat[i + 1], flat[i + 2], flat[i + 3]
        faces.append((a, b, c) if c == d else (a, b, c, d))
    return verts, faces


def _get_site_level(mesh, rings, how):
    # type: (rg.Mesh, list, str) -> float
    """평탄화 높이 — 대상지 경계(로컬 m)를 격자 간격으로 조밀화한 점의 자연 지반 Z의 평균|최저|최고."""
    pts = []
    for ring in rings:
        pts += [rg.Point3d(x, y, 1e5) for x, y in non_rhino_utils.get_resampled_ring(ring, constants.TERRAIN_GRID, True)]
    out, _indices = _project_to_mesh(mesh, pts)
    zs = [pt.Z for pt in out]
    if not zs:
        raise RuntimeError("대상지 경계에서 지반 높이를 읽지 못했습니다")
    return min(zs) if how == "min" else max(zs) if how == "max" else sum(zs) / len(zs)


def _get_site_wall(site_mesh, level):
    # type: (rg.Mesh, float) -> rg.Mesh
    """평탄면과 주변 지반 사이 수직 벽(옹벽 자리). 대상지 원지형 메시의 바깥 경계(GetNakedEdges) 정점을 그대로 쓴다 —
    윗선 = 주변 지형 경계와 같은 정점(분할 Brep이 모서리를 공유), 아랫선 = 같은 XY의 평탄 높이 → 틈이 생길 수 없다.
    2026-10-10: 경계를 3 m마다 다시 뽑은 점으로 만들었더니 정점이 어긋나고 모서리를 건너뛰어 틈이 보였다(사용자 지적)."""
    wall = rg.Mesh()
    for polyline in site_mesh.GetNakedEdges() or []:
        pts = list(polyline)
        if len(pts) > 1 and pts[0].DistanceTo(pts[-1]) < 1e-9:
            pts = pts[:-1]
        n = len(pts)
        for k in range(n):
            a, b = pts[k], pts[(k + 1) % n]
            da, db = abs(a.Z - level) > 1e-4, abs(b.Z - level) > 1e-4
            if not da and not db:
                continue
            base = wall.Vertices.Count
            wall.Vertices.Add(a.X, a.Y, level)
            wall.Vertices.Add(b.X, b.Y, level)
            if da and db:
                wall.Vertices.Add(b.X, b.Y, b.Z)
                wall.Vertices.Add(a.X, a.Y, a.Z)
                wall.Faces.AddFace(base, base + 1, base + 2, base + 3)
            elif db:
                wall.Vertices.Add(b.X, b.Y, b.Z)
                wall.Faces.AddFace(base, base + 1, base + 2)
            else:
                wall.Vertices.Add(a.X, a.Y, a.Z)
                wall.Faces.AddFace(base, base + 1, base + 2)
    wall.Vertices.UseDoublePrecisionVertices = True
    wall.Vertices.CombineIdentical(True, True)
    wall.Compact()
    wall.Normals.ComputeNormals()
    return wall


def build_terrain(prepared):
    # type: (object) -> tuple
    """TIN(보간용) → 범위 평면을 분류·대상지 경계로 면 분할 → 쿼드 위주 메싱 → TIN 높이 입히기 → 분류별 메시 (code_map §5.1~§5.4).

    입력: Prepared(세계좌표). options.flatten_site·flatten_level(mean|min|max)·site_output(mesh|curve) — 대상지 처리는 lots·area만.
    처리: get_tin_points → Mesh.CreateFromTessellation(보간에만 — 들로네 삼각형은 내보내지 않는다)
          → _get_region_meshes(범위 링, 범위와 겹치는 분류 폴리곤 링 + 대상지 링) — 경계는 원래 선 그대로, 안쪽은 TERRAIN_GRID m 쿼드
          → 영역마다 안쪽 한 점으로 분류(TERRAIN_CLASS_PRIORITY 순 PIP)·대상지 여부 → _drape(TIN 수직 투영) → 분류별로 용접
          → 수면 = 수면 폴리곤별 최저 Z + WATER_LIFT 평면 → 대상지: 바닥 메시 출력(site_output=mesh)이나 평탄화면 따로 떼어
            평탄면(site_ground, Z = 경계 자연 지반 mean|min|max)·경계 벽(site_wall)·원지형 사본(site_original, 숨김 레이어).
    출력: ``(meshes, tris_world, counts)``. meshes = {"all": 건물 투영용 최종 지반, "terrain"|"water"|"road"|"green"|"rail"|"site_ground"|"site_wall"|"site_original"}.
          tris_world = 세계좌표 TIN 삼각형 [((x,y,z)×3, "terrain"|"outside")] — 평탄화 전 자연 지형(시트 12·13, sheet_svg가 outside를 거른다).
    """
    origin = prepared.origin
    ox, oy = float(origin[0]), float(origin[1])
    options = prepared.request.get("options") or {}
    points, water_polys, counts = get_tin_points(prepared)

    t = time.time()
    tin = rg.Mesh.CreateFromTessellation(get_local_pts(points, origin), List[List[rg.Point3d]](), rg.Plane.WorldXY, False)
    if tin is None or tin.Faces.Count == 0:
        raise RuntimeError("지형 TIN 생성 실패 — 입력점 %d" % len(points))
    tin.Vertices.UseDoublePrecisionVertices = True
    counts["tin_s"] = round(time.time() - t, 3)
    counts["tin_faces"] = tin.Faces.Count

    # 시트용 자연 지형 삼각형 = TIN
    verts, faces = _get_mesh_faces(tin)
    ext_ring = prepared.extent_ring
    wx0, wy0, wx1, wy1 = non_rhino_utils.get_bbox(ext_ring)
    tris = []
    for f in faces:
        a, b, c = f[0], f[1], f[2]
        x = (verts[a][0] + verts[b][0] + verts[c][0]) / 3.0 + ox
        y = (verts[a][1] + verts[b][1] + verts[c][1]) / 3.0 + oy
        inside = wx0 <= x <= wx1 and wy0 <= y <= wy1 and non_rhino_utils.is_point_in_ring(x, y, ext_ring)
        tris.append(((verts[a][0] + ox, verts[a][1] + oy, verts[a][2]), (verts[b][0] + ox, verts[b][1] + oy, verts[b][2]),
                     (verts[c][0] + ox, verts[c][1] + oy, verts[c][2]), "terrain" if inside else "outside"))

    # 경계 커브 — 범위와 겹치는 분류 폴리곤 링 전부 + 대상지 링
    polys = _get_class_polygons(prepared)
    index_grid = non_rhino_utils.GridIndex(constants.CLASSIFY_GRID)
    cut_rings = []
    for index, (cls, _name, parts) in enumerate(polys):
        prio = constants.TERRAIN_CLASS_PRIORITY.index(cls)
        for part in parts:
            if not part:
                continue
            index_grid.add(non_rhino_utils.get_bbox(part[0]), (prio, index, part))
            for ring in part:
                r0, s0, r1, s1 = non_rhino_utils.get_bbox(ring)
                if r1 >= wx0 and r0 <= wx1 and s1 >= wy0 and s0 <= wy1:
                    cut_rings.append([(x - ox, y - oy) for x, y in ring])
    mode = getattr(prepared, "mode", "lots")
    site_world = getattr(prepared, "site_rings", None) or []
    flatten = bool(options.get("flatten_site")) and mode in ("lots", "area") and bool(site_world)
    site_mesh_out = options.get("site_output") == "mesh" and mode in ("lots", "area") and bool(site_world)
    separate_site = flatten or site_mesh_out
    site_local = [[(x - ox, y - oy) for x, y in ring] for ring in site_world] if separate_site else []
    cut_rings += site_local

    t = time.time()
    edge = max(constants.TERRAIN_GRID, math.sqrt((wx1 - wx0) * (wy1 - wy0) / float(constants.TERRAIN_GRID_MAX_FACES)))
    counts["mesh_edge"] = round(edge, 2)
    regions = _get_region_meshes([(x - ox, y - oy) for x, y in ext_ring], cut_rings, edge, counts)
    counts["mesh_s"] = round(time.time() - t - counts["split_s"], 3)

    # 영역 분류 — 영역 안쪽 한 점(첫 면 중심)
    t = time.time()
    buckets = {}
    water_regions = {}
    for mesh in regions:
        if mesh is None or mesh.Faces.Count == 0:
            continue
        c = mesh.Faces.GetFaceCenter(0)
        x, y = c.X + ox, c.Y + oy
        if separate_site and any(non_rhino_utils.is_point_in_ring(c.X, c.Y, ring) for ring in site_local):
            buckets.setdefault("site", []).append(mesh)
            continue
        best = None
        for prio, index, part in index_grid.query(x, y):
            if (best is None or prio < best[0]) and non_rhino_utils.is_point_in_polygon(x, y, part):
                best = (prio, index)
                if prio == 0:
                    break
        cls = constants.TERRAIN_CLASS_PRIORITY[best[0]] if best else "terrain"
        buckets.setdefault(cls, []).append(mesh)
        if cls == "water":
            water_regions.setdefault(best[1], []).append(mesh)
    counts["classify_s"] = round(time.time() - t, 3)
    t = time.time()
    counts["drape_missing"] = _drape([m for group in buckets.values() for m in group], tin)
    counts["drape_s"] = round(time.time() - t, 3)

    meshes = {}
    for cls in ("terrain", "road", "green", "rail"):
        if buckets.get(cls):
            meshes[cls] = _join(buckets[cls])
    # 수면 — 수면 폴리곤별 최저 Z = 수위, 평면 + WATER_LIFT
    water_bodies, water_parts = [], []
    for index in sorted(water_regions):
        body = _join(water_regions[index])
        level = min(v.Z for v in body.Vertices.ToPoint3dArray())
        for k in range(body.Vertices.Count):
            v = body.Vertices.Point3dAt(k)
            body.Vertices.SetVertex(k, v.X, v.Y, level + constants.WATER_LIFT)
        body.Normals.ComputeNormals()
        water_parts.append(body)
        water_bodies.append({"name": polys[index][1], "level": round(level, 2), "faces": body.Faces.Count})
    if water_parts:
        meshes["water"] = _join(water_parts)
    counts["water_bodies"] = water_bodies

    # 대상지 — 바닥 메시(원지형) 또는 평탄면 + 벽 + 원지형 사본(숨김)
    ground_parts = [meshes[cls] for cls in ("terrain", "road", "green", "rail") if cls in meshes]
    if buckets.get("site"):
        site_in = _join(buckets["site"])
        if flatten:
            level = _get_site_level(tin, site_local, options.get("flatten_level") or "mean")
            flat = site_in.DuplicateMesh()
            for k in range(flat.Vertices.Count):
                v = flat.Vertices.Point3dAt(k)
                flat.Vertices.SetVertex(k, v.X, v.Y, level)
            flat.Normals.ComputeNormals()
            meshes.update(site_ground=flat, site_wall=_get_site_wall(site_in, level), site_original=site_in)
            counts.update(site_level=round(level, 2), site_level_how=options.get("flatten_level") or "mean")
        else:
            meshes["site_ground"] = site_in
        counts["site_output"] = "mesh" if site_mesh_out else "flatten_only"
        ground_parts.append(meshes["site_ground"])
    meshes["all"] = _join([m.DuplicateMesh() for m in ground_parts])
    counts["faces"] = sum(m.Faces.Count for k, m in meshes.items() if k in ("terrain", "road", "green", "rail", "site_ground"))
    counts["quads"] = sum(m.Faces.QuadCount for k, m in meshes.items() if k in ("terrain", "road", "green", "rail", "site_ground"))
    counts["faces_by_class"] = {k: m.Faces.Count for k, m in meshes.items() if k != "all"}
    return meshes, tris, counts


def _get_terrain_items(prepared, meshes, counts):
    # type: (object, dict, dict) -> list
    """분류별 메시 + 구조물 위 표고점 → BakeItem(code_map §7.1 UserString)."""
    items = []
    for cls, mesh in meshes.items():
        if cls == "all":
            continue
        if cls == "terrain":
            attrs = {"SRC": TOPO_SOURCE_ID, "RESAMPLE_M": "%g" % constants.TERRAIN_RESAMPLE,
                     "N_POINTS": str(counts["tin_points"]), "N_STRUCT_EXCLUDED": str(counts["struct_excluded"])}
        elif cls == "water":
            bodies = counts["water_bodies"]
            attrs = {"NAME": "; ".join(b["name"] for b in bodies), "LEVEL_M": "; ".join("%.2f" % b["level"] for b in bodies),
                     "LEVEL_SRC": "terrain_min"}
        elif cls == "green":
            attrs = {"KIND": "field|park|forest"}
        elif cls == "rail":
            attrs = {"KIND": "surface", "SRC": TOPO_SOURCE_ID}
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
            layer = _SITE_LAYERS.get(cls) or _CLASS_LAYERS[cls]
        items.append(BakeItem(_layer(layer), mesh, attrs))
    min_x, min_y, max_x, max_y = counts["tin_bounds"]
    for f in prepared.context.get_features("terrain", "spot_struct"):
        x, y = float(f.geometry["coordinates"][0]), float(f.geometry["coordinates"][1])
        if f.value is not None and min_x <= x <= max_x and min_y <= y <= max_y:
            items.append(BakeItem(_layer("Terrain::struct_pts"), rg.Point(get_local_pts([(x, y)], prepared.origin, float(f.value))[0]),
                                  {"SRC": TOPO_SOURCE_ID, "ELEV_M": "%g" % f.value, "KIND": "spot_struct"}))
    return items


# ── 건물 ───────────────────────────────────────────────────

def _project_to_mesh(mesh, pts):
    # type: (rg.Mesh, list) -> tuple
    """Intersection.ProjectPointsToMeshesEx 1회 → (투영점 목록, 입력 인덱스 목록). 출력은 입력과 1:1이 아니다
    (빗나간 점 소실·다중 적중 중복 — 벤치 14,768 → 14,241) — indices로 동을 되찾는다. pythonnet은 out 인자를 반환 튜플로 준다."""
    direction, tol = rg.Vector3d(0, 0, -1), constants.GEOMETRY_TOLERANCE
    try:
        result = Intersection.ProjectPointsToMeshesEx([mesh], pts, direction, tol)
    except TypeError:   # out 인자를 자리로 요구하는 바인딩
        result = Intersection.ProjectPointsToMeshesEx([mesh], pts, direction, tol, None)
    if isinstance(result, tuple):
        out, indices = result
    else:   # out 인자가 반환되지 않는 바인딩이면 1:1로 간주할 수 없다 — 빈 결과로 폴백 ①에 맡긴다
        out, indices = [], []
    return list(out or []), list(indices or [])


def _get_building_attrs(b, height_src):
    # type: (object, str) -> dict
    """CTX::Buildings UserString 14키(code_map §7.1). DEMOL_DAY는 v1 빈 값."""
    return {"BLD_ID": str(b.building_id), "PNU": b.pnu, "PNU_SRC": b.src_key.split(":")[0],
            "GRND_FLR": str(b.grnd_flr), "FLR_SRC": b.flr_src, "UGRND_FLR": str(b.ugrnd_flr),
            "HEIGHT_M": "%.2f" % b.height_m, "HEIGHT_SRC": height_src, "HEIGHT_GRADE": b.height_grade,
            "USABILITY": b.usability, "USEAPR_DAY": b.use_apr_day, "BLD_NM": b.bld_nm, "STATUS": b.status, "DEMOL_DAY": ""}


def build_buildings(prepared, tin_mesh):
    # type: (object, rg.Mesh) -> tuple
    """범위 안 건물 → 동별 Mesh BakeItem (code_map §5.5; 2026-10-08 Extrusion → Mesh — 첫 음영 화면 18.7 s → 0.9 s).

    입력: Prepared, tin_mesh = build_terrain()의 meshes["all"](로컬 좌표 전체 TIN).
    처리: 발자국 정점 전체를 ProjectPointsToMeshesEx 1회 → indices로 동별 최저 Z(base_z)·고저차 → 투영 0인 동은 ① 최근접 TIN 정점 Z
          ② 없으면 건너뜀 → 고저차 > BUILDING_SLOPE_FLAG면 HEIGHT_SRC '~slope' → 파트별 각기둥 Mesh(_get_prism_mesh)를 동 하나로 합친다.
    출력: ``(items, counts, skipped, warnings)``. skipped = 건너뛴 동 'BLD_ID(사유)' 목록, counts에 투영·폴백·실패 수.
    """
    origin = prepared.origin
    buildings = context_report.get_buildings_in_extent(prepared)
    top_z = tin_mesh.GetBoundingBox(True).Max.Z + 1.0
    pts, owner, parts_by_building = [], [], []
    for bi, b in enumerate(buildings):
        parts = _get_parts(b.geometry)
        parts_by_building.append(parts)
        for part in parts:
            for ring in part:
                pts.extend(get_local_pts(ring, origin, top_z))
                owner.extend([bi] * len(ring))

    t = time.time()
    out, indices = _project_to_mesh(tin_mesh, pts)
    z_min, z_max = {}, {}
    for p, idx in zip(out, indices):
        bi = owner[idx]
        z_min[bi] = min(z_min.get(bi, p.Z), p.Z)
        z_max[bi] = max(z_max.get(bi, p.Z), p.Z)
    counts = {"buildings_in_extent": len(buildings), "project_in": len(pts), "project_out": len(out), "project_indices": len(indices),
              "project_s": round(time.time() - t, 3), "fallback_nearest": 0, "fallback_skipped": 0, "extrude_failed": 0, "parts": 0}
    nearest = None
    items, skipped = [], []
    t = time.time()
    for bi, b in enumerate(buildings):
        parts = parts_by_building[bi]
        if not parts or b.height_m <= 0:
            skipped.append("%s(빈 발자국·높이 0)" % b.building_id)
            counts["fallback_skipped"] += 1
            continue
        if bi in z_min:
            base_z, top = z_min[bi], z_max[bi]
        else:
            # 폴백 ① — 큰 단지·TIN 가장자리 발자국이 투영에 빗나간 동(벤치 527점 소실): 최근접 TIN 정점 Z
            if nearest is None:
                nearest = _NearestXYZ([(p.X, p.Y, p.Z) for p in tin_mesh.Vertices.ToPoint3dArray()], constants.CLASSIFY_GRID)
            center_pt = get_local_pts([((b.min_x + b.max_x) * 0.5, (b.min_y + b.max_y) * 0.5)], origin)[0]
            base_z = nearest.nearest_z(center_pt.X, center_pt.Y)
            if base_z is None:
                skipped.append("%s(투영·최근접 정점 없음)" % b.building_id)
                counts["fallback_skipped"] += 1
                continue
            top = base_z
            counts["fallback_nearest"] += 1
        height_src = b.height_src + ("~slope" if top - base_z > constants.BUILDING_SLOPE_FLAG else "")
        attrs = _get_building_attrs(b, height_src)
        building_mesh = rg.Mesh()          # 멀티폴리곤 파트도 한 동 = 한 객체(UserText 한 벌)
        made = 0
        for part in parts:
            part_mesh = _get_prism_mesh(part, origin, base_z, float(b.height_m))
            if part_mesh is None:
                continue
            building_mesh.Append(part_mesh)
            made += 1
        if made:
            items.append(BakeItem(_layer("Buildings"), building_mesh, attrs, b.bld_nm))
        counts["parts"] += made
        if not made:
            # 자기교차 발자국 → 캡·Extrusion 모두 실패 (벤치 8,517동 중 2) — 건너뛰고 기록
            skipped.append("%s(압출 실패)" % b.building_id)
            counts["extrude_failed"] += 1
    counts["extrude_s"] = round(time.time() - t, 3)
    counts["buildings"] = len(buildings) - counts["fallback_skipped"] - counts["extrude_failed"]
    warnings = []
    if skipped:
        warnings.append(_warning("warn", "skipped", "건물 %d동 건너뜀 — 투영·압출 실패" % len(skipped), ", ".join(skipped[:20])))
    return items, counts, skipped, warnings


# ── 커브 ───────────────────────────────────────────────────

def build_curves(prepared):
    # type: (object) -> list
    """Site·Parcels(구멍 보존)·Roads::centerline·Ref 범위·도엽 경계·(옵션) Zoning PolylineCurve Z=0 (code_map §5.6·§7.1).

    입력: Prepared. 처리: 대상 필지는 가장 넓은 조각 외곽선 하나(CLAUDE.md), 주변 필지는 범위 bbox와 겹치는 것 전부 링마다 커브,
          도로중심선 = features road/centerline LineString(범위 bbox와 겹치는 것) → 열린 PolylineCurve, UserString WIDTH_M·LANES·NAME,
          Ref = extent_ring + prepared.stats['sheets'] 도엽 사각형(경위도 → TM), Zoning = options.include_zoning일 때 overlays theme zone.
    출력: BakeItem 목록.
    """
    origin = prepared.origin
    mode = getattr(prepared, "mode", "lots")
    items = []
    targets = set()
    if mode == "lots":   # 필지 방식 — 대상 필지마다 Site 커브(가장 넓은 조각 외곽)
        for lot in prepared.target_lots:
            targets.add(lot.pnu)
            parts = _get_parts(lot.geometry)
            outer = max((part[0] for part in parts if part), key=non_rhino_utils.get_ring_area)
            items.append(BakeItem(_layer("Site"), _get_ring_crv(outer, origin, 0.0), {"PNU": lot.pnu}, lot.lot_number))
    for ring in (prepared.site_rings or []) if mode == "area" else []:   # 구역 방식 — 구역 링 하나, 안의 필지는 Parcels에 IN_SITE=1
        items.append(BakeItem(_layer("Site"), _get_ring_crv(ring, origin, 0.0),
                              {"KIND": "area", "AREA_M2": "%.1f" % non_rhino_utils.get_ring_area(ring), "LOTS": str(len(prepared.target_lots))}, "area"))
    in_site = {lot.pnu for lot in prepared.target_lots} if mode == "area" else set()
    for lot in context_report.get_lots_in_extent(prepared):
        if lot.pnu in targets:
            continue
        attrs = {"PNU": lot.pnu, "JIMOK": lot.land_category or "", "ZONE": lot.zone_name or ""}
        if lot.pnu in in_site:
            attrs["IN_SITE"] = "1"
        for part in _get_parts(lot.geometry):
            for ring in part:
                items.append(BakeItem(_layer("Parcels"), _get_ring_crv(ring, origin, 0.0), attrs))
    ex0, ey0, ex1, ey1 = non_rhino_utils.get_bbox(prepared.extent_ring)
    for f in prepared.context.get_features("road", "centerline"):
        if f.geometry.get("type") != "LineString" or f.max_x < ex0 or f.min_x > ex1 or f.max_y < ey0 or f.min_y > ey1:
            continue
        attrs = {"WIDTH_M": "" if f.value is None else "%g" % f.value, "LANES": str((f.attrs or {}).get("차로수", "")), "NAME": f.name or ""}
        items.append(BakeItem(_layer("Roads::centerline"), rg.PolylineCurve(get_local_pts(f.geometry["coordinates"], origin, 0.0)), attrs, f.name or ""))
    items.append(BakeItem(_layer("Ref"), _get_ring_crv(prepared.extent_ring, origin, 0.0),
                          {"KIND": "extent", "RADIUS_M": "%g" % prepared.radius, "SHAPE": prepared.shape}, "extent"))
    for code in (prepared.stats or {}).get("sheets") or []:
        left, bottom, right, top = non_rhino_utils.get_topo_sheet_bounds(code)
        ring = [non_rhino_utils.get_tm_from_wgs84(lng, lat) for lng, lat in ((left, bottom), (right, bottom), (right, top), (left, top))]
        items.append(BakeItem(_layer("Ref"), _get_ring_crv(ring, origin, 0.0), {"KIND": "topo_sheet", "SHEET": code}, code))
    if (prepared.request.get("options") or {}).get("include_zoning"):
        for o in prepared.overlays:
            if o.theme != constants.OVERLAY_THEME_ZONE:
                continue
            attrs = {"THEME": o.theme, "KIND": o.kind or "", "NAME": o.name or "", "NOTICE_NO": o.notice_number or ""}
            for part in _get_parts(o.geometry):
                for ring in part:
                    items.append(BakeItem(_layer("Zoning"), _get_ring_crv(ring, origin, 0.0), attrs, o.name or ""))
    return items


# ── 베이스맵 2D (BM::) ───────────────────────────────────────

def build_basemap_2d(prepared, scale):
    # type: (object, int) -> list
    """basemap_<축척>.ai와 같은 도면(basemap_ai.build_ai)을 3dm 2D 레이어 BakeItem으로. Z=0 커브·텍스트, 칠은 없다(레이어 색만).

    입력: Prepared, 축척 분모(레이어 선택·프레임 범위·글자 높이를 정한다). 처리: ShapeRecorder로 받아 polygon 링 → 닫힌 커브,
          line → 열린 커브, text → TextEntity(가운데 정렬, 높이 = 종이 mm × 축척 / 1000 m). 레이어는 'BM::07_bldg_low 건물 1~4층'.
    출력: BakeItem 목록. BM 루트 레이어는 베이커가 꺼 둔 채 만든다(constants.BM_ROOT_LAYER).
    """
    recorder = basemap_ai.build_ai(prepared, scale, basemap_ai.ShapeRecorder())
    labels = {name: label for name, label, *_ in constants.BM_LAYERS}
    origin = prepared.origin
    items = []
    for name, kind, data in recorder.shapes:
        layer = "%s::%s %s" % (constants.BM_ROOT_LAYER, name, labels[name])
        if kind == "polygon":
            items += [BakeItem(layer, _get_ring_crv(ring, origin, 0.0)) for ring in data]
        elif kind == "line":
            items.append(BakeItem(layer, rg.PolylineCurve(get_local_pts(data, origin, 0.0))))
        else:
            content, x, y, size_mm = data
            height = size_mm * scale / 1000.0
            text = rg.TextEntity()
            text.Plane = rg.Plane(get_local_pts([(x, y)], origin, 0.0)[0], rg.Vector3d.ZAxis)
            text.PlainText = content
            text.Justification = rg.TextJustification.MiddleCenter
            text.TextHeight = height
            items.append(BakeItem(layer, text, name=content, text_height=height))
    return items



# ── 구역 커브 (패널 '구역 그리기') ───────────────────────────

def get_curve_ring(curve, unit_scale, tolerance):
    # type: (rg.Curve, float, float) -> tuple
    """Rhino 커브 → 구역 링(문서 좌표를 m로 환산한 값). 안전장치에 걸리면 (None, 사용자용 이유).

    입력: curve(문서 단위), unit_scale(문서 단위 → m 배율), tolerance(문서 단위 — doc.ModelAbsoluteTolerance).
    처리: 닫힘 → XY 평면(법선 ±Z) → 자기교차 0 → 폴리라인(아니면 CURVE_POLYLINE_TOLERANCE로 근사) → m 환산 → get_clean_ring·get_ring_problem.
    출력: ([(x, y)] m, '') 또는 (None, 이유).
    """
    if curve is None:
        return None, "커브가 아닙니다"
    if not curve.IsClosed:
        return None, "닫힌 커브가 아닙니다 — 끝점이 붙은 커브만 받습니다"
    ok, plane = curve.TryGetPlane(tolerance)
    if not ok:
        return None, "평면 커브가 아닙니다"
    if abs(plane.Normal.Z) < 0.999:
        return None, "XY 평면(Top)에 놓인 커브여야 합니다 — 기울어진 커브입니다"
    events = Intersection.CurveSelf(curve, tolerance)
    if events is not None and events.Count > 0:
        return None, "자기교차가 있는 커브입니다 — 꼬이지 않은 닫힌 커브만 받습니다"
    ok, polyline = curve.TryGetPolyline()
    if not ok:
        approx = curve.ToPolyline(constants.CURVE_POLYLINE_TOLERANCE / unit_scale, math.radians(2.0), 0.0, 0.0)
        if approx is None:
            return None, "커브를 폴리라인으로 바꾸지 못했습니다"
        polyline = approx.ToPolyline()
    ring = non_rhino_utils.get_clean_ring([(pt.X * unit_scale, pt.Y * unit_scale) for pt in polyline])
    problem = non_rhino_utils.get_ring_problem(ring)
    return (None, problem) if problem else (ring, "")


def _get_local_crv(ring, ox, oy):
    # type: (list, float, float) -> rg.PolylineCurve
    pts = [rg.Point3d(x - ox, y - oy, 0.0) for x, y in ring]
    return rg.PolylineCurve(pts + [pts[0]])


def _get_largest_ring(curves, ox, oy, tolerance):
    # type: (list, float, float, float) -> list
    """닫힌 커브들 중 가장 넓은 것의 세계좌표 링(구멍·작은 조각은 버린다). 없으면 None."""
    best, best_area = None, 0.0
    for crv in curves or []:
        ok, polyline = crv.TryGetPolyline()
        if not ok:
            polyline = crv.ToPolyline(tolerance, math.radians(2.0), 0.0, 0.0).ToPolyline()
        ring = [(pt.X + ox, pt.Y + oy) for pt in polyline]
        area = non_rhino_utils.get_ring_area(ring)
        if area > best_area:
            best, best_area = ring, area
    return non_rhino_utils.get_clean_ring(best) if best else None


def get_snapped_ring(area_ring, add_rings, cut_rings, tolerance):
    # type: (list, list, list, float) -> list
    """구역계를 필지 경계에 맞춘다 — (구역 ∪ 더할 필지) − 뺄 필지, 가장 넓은 조각의 바깥 경계(세계좌표 m).

    입력: context_builder.get_snap_rings 결과. 처리: 큰 좌표의 불리언 오차를 피하려고 구역 첫 정점 기준 로컬에서
          Curve.CreateBooleanUnion → CreateBooleanDifference. 도로·하천(선형 지목)은 입력에 없어 그린 선이 그대로 남는다.
    출력: 링 또는 None(불리언 실패).
    """
    ox, oy = area_ring[0]
    current = [_get_local_crv(area_ring, ox, oy)]
    if add_rings:
        union = rg.Curve.CreateBooleanUnion(List[rg.Curve](current + [_get_local_crv(r, ox, oy) for r in add_rings]), tolerance)
        if union:
            current = [max(union, key=lambda c: abs(rg.AreaMassProperties.Compute(c).Area) if rg.AreaMassProperties.Compute(c) else 0.0)]
    if cut_rings:
        diff = rg.Curve.CreateBooleanDifference(current[0], List[rg.Curve]([_get_local_crv(r, ox, oy) for r in cut_rings]), tolerance)
        if diff:
            current = list(diff)
    return _get_largest_ring(current, ox, oy, tolerance)


# ── 전체 ───────────────────────────────────────────────────

def build(prepared):
    # type: (object) -> ContextGeo
    """지형 → 건물 → 커브 → 2D 도면(BM::) 순으로 전부 만들어 ContextGeo로 묶는다(phase 'terrain' 전체). 문서는 건드리지 않는다."""
    meshes, tris, counts = build_terrain(prepared)
    items = _get_terrain_items(prepared, meshes, counts)
    b_items, b_counts, skipped, warnings = build_buildings(prepared, meshes["all"])
    items += b_items
    curve_items = build_curves(prepared)
    items += curve_items
    bm_items = build_basemap_2d(prepared, min(prepared.scales))   # 2D는 가장 상세한 축척 한 장만 — 축척마다 넣으면 3dm이 축척 수만큼 커진다
    items += bm_items
    counts["basemap_2d"] = len(bm_items)
    counts.update(b_counts)
    counts["curves"] = len(curve_items)
    counts["items"] = len(items)
    counts["demolished"] = 0   # v1: status 전부 active (code_map §7.1 P1)
    return ContextGeo(items=items, terrain_tris_world=tris, counts=counts, skipped=skipped, warnings=warnings)
