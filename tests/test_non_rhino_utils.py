"""non_rhino_utils 순수 기하 6함수 — docs/implementation_plan.md M1 표 그대로."""

import json
import math
import random
import sys
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants
import lot_db
import non_rhino_utils as u

FIXTURE_SITE_DB = str(Path(__file__).resolve().parent / "fixtures" / "seongsu_site.db")
DONUT_ROAD_PNU = "1120011400100130219"   # 성수동1가 도로 필지 — 구멍 3개(fixture 실측)

SQUARE = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0), (0.0, 100.0)]
HOLE = [(40.0, 40.0), (60.0, 40.0), (60.0, 60.0), (40.0, 60.0)]


def _dist_point_segment(px, py, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - (ax + dx * t), py - (ay + dy * t))


def _dist_point_ring(px, py, ring):
    return min(_dist_point_segment(px, py, ring[i - 1], ring[i]) for i in range(len(ring)))


def _cross(o, a, b):
    return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])


def _segments_cross(a, b, c, d):
    """닫힌 구간 교차(끝점 공유 제외)."""
    d1, d2 = _cross(c, d, a), _cross(c, d, b)
    d3, d4 = _cross(a, b, c), _cross(a, b, d)
    return (d1 > 0) != (d2 > 0) and (d3 > 0) != (d4 > 0) and all(abs(v) > 1e-9 for v in (d1, d2, d3, d4))


def _assert_simple_convex(test, ring):
    n = len(ring)
    turns = [_cross(ring[i - 1], ring[i], ring[(i + 1) % n]) for i in range(n)]
    test.assertTrue(all(t >= -1e-6 for t in turns), "오목 꼭짓점 있음")
    test.assertEqual(u.get_ring_orientation(ring), 1)
    for i in range(n):
        for j in range(i + 2, n):
            if i == 0 and j == n - 1:
                continue
            test.assertFalse(_segments_cross(ring[i], ring[(i + 1) % n], ring[j], ring[(j + 1) % n]), "자기교차 %d-%d" % (i, j))


class KoreaTest(unittest.TestCase):
    def test_korea_box_without_japan_corner(self):
        """한국 판정 사각형에서 남동쪽 일본 모서리(후쿠오카·기타큐슈·쓰시마)를 뺀다. 부산·제주·울릉은 한국 그대로."""
        for name, lng, lat in (("서울", 126.98, 37.57), ("부산역", 129.04, 35.12), ("태종대", 129.08, 35.05), ("제주", 126.53, 33.50),
                               ("울릉도", 130.90, 37.50), ("독도", 131.87, 37.24)):
            self.assertTrue(u.is_korea(lng, lat), name)
        for name, lng, lat in (("후쿠오카", 130.40, 33.59), ("기타큐슈", 130.88, 33.88), ("쓰시마", 129.30, 34.40), ("사세보", 129.72, 33.18),
                               ("시모노세키", 130.94, 33.96), ("도쿄", 139.70, 35.69)):
            self.assertFalse(u.is_korea(lng, lat), name)


class PointInPolygonTest(unittest.TestCase):
    def test_donut_hole_is_outside(self):
        rings = [SQUARE, HOLE]
        self.assertFalse(u.is_point_in_polygon(50, 50, rings))
        self.assertTrue(u.is_point_in_polygon(10, 10, rings))
        self.assertFalse(u.is_point_in_polygon(200, 50, rings))
        self.assertTrue(u.is_point_in_ring(50, 50, SQUARE + [SQUARE[0]]))   # 닫힘 중복점 허용

    def test_fixture_road_parcel_hole(self):
        lot = lot_db.load([DONUT_ROAD_PNU], FIXTURE_SITE_DB).lots[0]
        rings = u.get_polygon_parts_from_geojson(lot.geometry)[0]
        self.assertGreater(len(rings), 1)
        hole = rings[1]
        min_x, min_y, max_x, max_y = u.get_bbox({"type": "Polygon", "coordinates": [hole]})
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        self.assertTrue(u.is_point_in_ring(cx, cy, hole))          # 구멍(가구) 중심
        self.assertTrue(u.is_point_in_ring(cx, cy, rings[0]))      # 외곽 안이지만
        self.assertFalse(u.is_point_in_polygon(cx, cy, rings))     # 도로 필지 안은 아니다


class GridIndexTest(unittest.TestCase):
    def test_candidates_superset_of_brute_force(self):
        rng = random.Random(7)
        grid = u.GridIndex(constants.CLASSIFY_GRID)
        boxes = []
        for i in range(300):
            x, y = rng.uniform(0, 1000), rng.uniform(0, 1000)
            box = (x, y, x + rng.uniform(1, 200), y + rng.uniform(1, 200))
            boxes.append(box)
            grid.add(box, i)
        for _ in range(500):
            px, py = rng.uniform(-50, 1100), rng.uniform(-50, 1100)
            expected = {i for i, b in enumerate(boxes) if b[0] <= px <= b[2] and b[1] <= py <= b[3]}
            self.assertTrue(expected <= set(grid.query(px, py)))
        self.assertEqual(grid.query(-999, -999), [])


class ResampleTest(unittest.TestCase):
    def test_closed_ring_spacing(self):
        out = u.get_resampled_ring(SQUARE + [SQUARE[0]], constants.TERRAIN_RESAMPLE)
        self.assertEqual(len(out), 100)                               # 변당 25점, 닫힘 중복 없음
        for i in range(len(out)):
            a, b = out[i - 1], out[i]
            self.assertLessEqual(math.hypot(b[0] - a[0], b[1] - a[1]), constants.TERRAIN_RESAMPLE + 1e-9)
        for p in SQUARE:
            self.assertIn(p, out)

    def test_open_line_keeps_ends_and_z(self):
        out = u.get_resampled_ring([(0, 0, 10), (10, 0, 20)], 4, closed=False)
        self.assertEqual(out[0], (0.0, 0.0, 10.0))
        self.assertEqual(out[-1], (10.0, 0.0, 20.0))
        self.assertEqual(len(out), 4)
        self.assertAlmostEqual(out[1][2], 13.333333, 5)


class OrientationAndBboxTest(unittest.TestCase):
    def test_orientation_sign(self):
        self.assertEqual(u.get_ring_orientation(SQUARE), 1)
        self.assertEqual(u.get_ring_orientation(list(reversed(SQUARE))), -1)
        self.assertEqual(u.get_ring_orientation([(0, 0), (1, 1), (2, 2)]), 0)

    def test_bbox_order(self):
        poly = {"type": "Polygon", "coordinates": [[[3, 10], [7, 20], [5, 30], [3, 10]]]}
        self.assertEqual(u.get_bbox(poly), (3.0, 10.0, 7.0, 30.0))
        old = u.get_bounds_from_geojson(poly)
        self.assertEqual(u.get_bbox(poly), (old[0], old[2], old[1], old[3]))   # 구 순서와 대응
        self.assertEqual(u.get_bbox({"type": "LineString", "coordinates": [[1, 2], [-1, 5]]}), (-1.0, 2.0, 1.0, 5.0))
        self.assertEqual(u.get_bbox({"type": "Point", "coordinates": [1, 2]}), (1.0, 2.0, 1.0, 2.0))


class ExtentRingTest(unittest.TestCase):
    def setUp(self):
        lot = lot_db.load([constants.TEST_CONTEXT_PNU], FIXTURE_SITE_DB).lots[0]
        self.lot_ring = [(p[0], p[1]) for p in u.get_polygon_parts_from_geojson(lot.geometry)[0][0]]
        self.radius = constants.CONTEXT_RADIUS

    def test_buffer_distance_convex_simple(self):
        ring = u.get_extent_ring([self.lot_ring], self.radius, "buffer")
        _assert_simple_convex(self, ring)
        dists = [_dist_point_ring(x, y, ring) for x, y in self.lot_ring]
        self.assertGreaterEqual(min(dists), self.radius - 0.001)
        self.assertLess(min(dists), self.radius + 0.01)              # 꽉 붙어 있다(과대 오프셋 아님)
        min_x, min_y, max_x, max_y = u.get_bbox(self.lot_ring)
        rx0, ry0, rx1, ry1 = u.get_bbox(ring)
        over = self.radius * (1 / math.cos(math.radians(90.0 / constants.EXTENT_ARC_SEGMENTS) / 2) - 1)   # 외접 오차 ≈ 1.07 m
        self.assertTrue(min_x - self.radius - over <= rx0 <= min_x - self.radius)
        self.assertTrue(max_y + self.radius <= ry1 <= max_y + self.radius + over)
        self.assertLess(len(ring), 300)
        print("\n[measure] buffer ring points=%d min_dist=%.4f max_dist=%.4f" % (len(ring), min(dists), max(dists)))

    def test_buffer_of_square_bbox(self):
        ring = u.get_extent_ring([SQUARE], 5.0, "buffer")
        _assert_simple_convex(self, ring)
        self.assertEqual(u.get_bbox(ring), (-5.0, -5.0, 105.0, 105.0))
        self.assertFalse(any(abs(x + 5) < 1e-6 and abs(y + 5) < 1e-6 for x, y in ring))   # 모서리는 둥글다

    def test_circle_and_rect(self):
        circle = u.get_extent_ring([self.lot_ring], self.radius, "circle")
        rect = u.get_extent_ring([self.lot_ring], self.radius, "rect")
        _assert_simple_convex(self, circle)
        _assert_simple_convex(self, rect)
        self.assertEqual(len(circle), constants.EXTENT_CIRCLE_SEGMENTS)
        self.assertEqual(len(rect), 4)
        min_x, min_y, max_x, max_y = u.get_bbox(self.lot_ring)
        cx, cy = (min_x + max_x) / 2, (min_y + max_y) / 2
        self.assertEqual(u.get_bbox(rect), (cx - self.radius, cy - self.radius, cx + self.radius, cy + self.radius))   # 한 변 = 2 × radius
        for x, y in circle:
            self.assertAlmostEqual(math.hypot(x - cx, y - cy), self.radius, 6)
        with self.assertRaises(ValueError):
            u.get_extent_ring([self.lot_ring], self.radius, "hexagon")


class MergedRingsTest(unittest.TestCase):
    """합필 — 공공 지적처럼 어긋난 경계(T자 정점·틈·겹침)도 덩어리 하나로."""

    @staticmethod
    def _box(x0, y0, x1, y1):
        return [[(x0, y0), (x1, y0), (x1, y1), (x0, y1)]]

    def _merge(self, polygons):
        outers, holes = u.get_merged_rings(polygons, 0.05)
        return [round(u.get_ring_area(r), 1) for r in outers], [round(u.get_ring_area(r), 1) for r in holes]

    def test_t_junction_and_gap(self):
        right = [[(10.02, 0), (20, 0), (20, 10), (10.02, 10), (10.02, 5)]]   # 2 cm 틈 + 이웃 변 가운데 정점(T자)
        outers, holes = self._merge([self._box(0, 0, 10, 10), right])
        self.assertEqual((len(outers), holes), (1, []))
        self.assertAlmostEqual(outers[0], 200.0, delta=0.5)

    def test_overlap_and_contained(self):
        self.assertEqual(self._merge([self._box(0, 0, 10, 10), self._box(9, 0, 20, 10)]), ([200.0], []))   # 1 m 겹침
        self.assertEqual(self._merge([self._box(0, 0, 10, 10), self._box(2, 2, 4, 4)]), ([100.0], []))     # 안에 든 필지

    def test_apart_and_hole(self):
        self.assertEqual(self._merge([self._box(0, 0, 10, 10), self._box(20, 0, 30, 10)]), ([100.0, 100.0], []))
        ring = [self._box(0, 0, 30, 10), self._box(0, 20, 30, 30), self._box(0, 10, 10, 20), self._box(20, 10, 30, 20)]
        self.assertEqual(self._merge(ring), ([900.0], [100.0]))   # 가운데를 안 고른 'ㅁ'자
        donut = [[(0, 0), (30, 0), (30, 30), (0, 30)], [(10, 10), (10, 20), (20, 20), (20, 10)]]
        self.assertEqual(self._merge([donut, self._box(10, 10, 20, 20)]), ([900.0], []))   # 구멍을 메운 필지

    def test_fixture_neighbors(self):
        # 성수동2가 333-139 + 333-132 — 실제 지적 이웃
        lots = lot_db.load([constants.TEST_CONTEXT_PNU, "1120011500103330132"], FIXTURE_SITE_DB).lots
        polygons = [u.get_polygon_parts_from_geojson(lot.geometry)[0] for lot in lots]
        outers, holes = self._merge(polygons)
        self.assertEqual((len(outers), holes), (1, []))
        self.assertAlmostEqual(outers[0], sum(u.get_ring_area(p[0]) for p in polygons), delta=0.5)


class SteppedMeshTest(unittest.TestCase):
    """계단 지형 — 단 면은 수평·step 배수, 평면 면적 보존, 안쪽 변은 정확히 두 번(반대 방향) — 틈·겹침·뒤집힌 벽이 없다."""

    N, STEP = 12, 1.0

    def setUp(self):
        n = self.N
        verts = []
        for j in range(n + 1):
            for i in range(n + 1):
                z = 0.37 * i + 0.21 * j + 1.5 * math.sin(i * 0.7) * math.cos(j * 0.5)
                if (i + j) % 3 == 0 or 4 <= i <= 6:
                    z = float(round(z))   # 경계 위 정점·경계를 따라가는 변(원천 등고선 값 그대로인 정점)
                verts.append((float(i), float(j), z))
        faces = []
        for j in range(n):
            for i in range(n):
                a = j * (n + 1) + i
                quad = (a, a + 1, a + n + 2, a + n + 1)
                faces += [quad] if (i + j) % 2 else [quad[:3], (quad[0], quad[2], quad[3])]
        self.verts, self.faces = verts, faces
        self.out_verts, self.out_faces = u.get_stepped_mesh(verts, faces, self.STEP)

    def test_terraces_flat_and_area_kept(self):
        area = 0.0
        for face in self.out_faces:
            pts = [self.out_verts[i] for i in face]
            ring_area = u.get_ring_area([p[:2] for p in pts]) * u.get_ring_orientation([p[:2] for p in pts])
            if abs(ring_area) < 1e-12:   # 수직 벽
                self.assertAlmostEqual(abs(pts[2][2] - pts[1][2]), self.STEP, 9)
                continue
            self.assertGreater(ring_area, 0)   # 위를 본다
            self.assertEqual(len({p[2] for p in pts}), 1)
            self.assertAlmostEqual(pts[0][2] / self.STEP, round(pts[0][2] / self.STEP), 9)
            area += ring_area
        self.assertAlmostEqual(area, self.N * self.N, 6)

    def test_watertight_inside(self):
        edges = {}
        for face in self.out_faces:
            for k in range(len(face)):
                key = (self.out_verts[face[k - 1]], self.out_verts[face[k]])
                self.assertNotIn(key, edges, "같은 방향 변 두 번 — 겹치거나 뒤집힌 면")
                edges[key] = True
        n = self.N
        on_side = lambda p, q: any(p[c] == q[c] == v for c in (0, 1) for v in (0.0, float(n)))
        open_edges = [e for e in edges if (e[1], e[0]) not in edges]
        self.assertTrue(open_edges)
        for p, q in open_edges:
            self.assertTrue(on_side(p, q), "안쪽에 열린 변 %s-%s — 벽이 빠졌다" % (p, q))

    def test_stepped_edges_match_mesh(self):
        out = set(self.out_verts)
        n = self.N
        for i in range(n):   # 아래 변(y = 0)을 따라 — 대상지 경계 벽 윗선이 주변 계단 지형 정점에 맞는다
            for p, q in u.get_stepped_edges(self.verts[i], self.verts[i + 1], self.STEP):
                self.assertIn(p, out)
                self.assertIn(q, out)
        self.assertEqual(u.get_stepped_edges((0, 0, 1.3), (1, 0, 2.7), 0), [((0, 0, 1.3), (1, 0, 2.7))])


if __name__ == "__main__":
    unittest.main()
