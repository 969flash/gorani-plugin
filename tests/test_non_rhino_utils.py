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


class CleanEdgeTest(unittest.TestCase):
    """범위로 자르기·지형 덩어리 — 볼록 판정·선/건물 자르기·덩어리 바닥 높이·옆면."""

    BOX = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0)]

    def test_convex_ring(self):
        self.assertEqual(u.get_convex_ring(list(reversed(self.BOX)) + [self.BOX[0]])[0], (0.0, 0.0))
        self.assertEqual(u.get_ring_orientation(u.get_convex_ring(list(reversed(self.BOX)))), 1)   # 시계 → 반시계
        self.assertIsNone(u.get_convex_ring([(0, 0), (10, 0), (5, 2), (10, 10), (0, 10)]))   # 오목

    def test_clipped_lines(self):
        self.assertEqual(u.get_clipped_lines([(-5.0, 5.0), (15.0, 5.0)], self.BOX), [[(0.0, 5.0), (10.0, 5.0)]])
        pieces = u.get_clipped_lines([(5.0, 5.0), (15.0, 5.0), (15.0, 8.0), (5.0, 8.0), (5.0, 9.0)], self.BOX)   # 나갔다 다시 들어온다
        self.assertEqual(pieces, [[(5.0, 5.0), (10.0, 5.0)], [(10.0, 8.0), (5.0, 8.0), (5.0, 9.0)]])
        self.assertEqual(u.get_clipped_lines([(20.0, 0.0), (20.0, 10.0)], self.BOX), [])

    def test_clipped_parts(self):
        inside = [[(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]]
        cross = [[(8, 4), (14, 4), (14, 6), (8, 6), (8, 4)], [(8.5, 4.5), (9, 4.5), (9, 5), (8.5, 4.5)], [(11, 5), (12, 5), (12, 5.5), (11, 5)]]
        out = u.get_clipped_parts([inside, cross, [[(20, 20), (21, 20), (21, 21), (20, 20)]]], self.BOX)
        self.assertEqual(out[0], inside)   # 다 안 = 그대로
        self.assertAlmostEqual(u.get_ring_area(out[1][0]), 4.0)   # 걸친 외곽 = 잘림, 다 밖 = 빠짐
        self.assertEqual(len(out), 2)
        self.assertEqual(len(out[1]), 2)   # 안에 든 구멍만 남는다

    def test_block_base(self):
        ring = [(0, 0), (500, 0), (500, 500), (0, 500)]
        self.assertEqual(u.get_block_base(23.4, ring), 5.0)    # 23.4 − 15 = 8.4 → 5 m 단위 내림
        self.assertEqual(u.get_block_base(-3.0, ring), -20.0)  # 해수면 아래(간척지)도 같은 규칙
        self.assertEqual(u.get_block_base(10.0, [(0, 0), (50, 0), (50, 50), (0, 50)]), 5.0)   # 작은 범위는 두께 하한 5 m

    def test_block_skirt_closes_top(self):
        # 윗면 = 10 × 10을 2 × 2 쿼드로, z = x(비탈). 덩어리(윗면 + 옆면 + 바닥)의 모든 변이 정확히 두 면에 걸려야 닫힌 것
        verts = [(x * 5.0, y * 5.0, x * 5.0) for y in range(3) for x in range(3)]
        faces = [(y * 3 + x, y * 3 + x + 1, (y + 1) * 3 + x + 1, (y + 1) * 3 + x) for y in range(2) for x in range(2)]
        skirt_verts, skirt_faces = u.get_block_skirt([(verts, faces)], self.BOX, -5.0)
        self.assertEqual(len(skirt_faces), 8 + 8)   # 경계 변 8개 → 벽 8, 바닥 부채꼴 8
        edges = {}
        for vs, fs in ((verts, faces), (skirt_verts, skirt_faces)):
            for f in fs:
                for k in range(len(f)):
                    key = frozenset((tuple(round(c, 6) for c in vs[f[k]]), tuple(round(c, 6) for c in vs[f[(k + 1) % len(f)]])))
                    edges[key] = edges.get(key, 0) + 1
        self.assertEqual(set(edges.values()), {2})
        for f in skirt_faces[:8]:   # 벽 법선(정점 순서)이 바깥
            a, b = skirt_verts[f[0]], skirt_verts[f[1]]
            nx, ny = b[1] - a[1], a[0] - b[0]
            self.assertGreater(nx * ((a[0] + b[0]) / 2 - 5) + ny * ((a[1] + b[1]) / 2 - 5), 0)

    def test_water_walls_close_gaps(self):
        # y 띠 넷: 지형 z3 | 수면 A z1 | 수면 B z2 | 지형 z2. 틈은 지형→A(y=2)·B→A(y=6) 두 곳, B와 위 지형(같은 높이)은 막을 것 없음
        def quad(y0, y1, z):
            return [(0, y0, z), (10, y0, z), (10, y1, z), (0, y1, z)], [(0, 1, 2, 3)]
        bank, top = quad(0, 2, 3.0), quad(8, 10, 2.0)
        (a_verts, a_faces), (b_verts, b_faces) = quad(2, 6, 1.0), quad(6, 8, 2.0)
        water = (a_verts + b_verts, a_faces + [tuple(i + 4 for i in f) for f in b_faces])
        walls = u.get_water_walls(water, [bank, top])
        self.assertEqual(len(walls[1]), 2)
        edges = {}
        for vs, fs in (bank, top, water, walls):
            for f in fs:
                for k in range(len(f)):
                    p, q = vs[f[k]], vs[f[(k + 1) % len(f)]]
                    if p[0] != q[0] and p[1] == q[1] and 0 < p[1] < 10:   # 안쪽 가로 변
                        key = frozenset((tuple(p), tuple(q)))
                        edges[key] = edges.get(key, 0) + 1
        self.assertEqual(set(edges.values()), {2})   # 안쪽 가로 변이 모두 두 면에 걸린다 = 틈 없음
        for f in walls[1]:   # 벽 법선이 낮은 수면 A(2 < y < 6) 쪽
            pts = [walls[0][i] for i in f]
            ny = sum((pts[k][2] - pts[(k + 1) % len(pts)][2]) * (pts[k][0] + pts[(k + 1) % len(pts)][0]) for k in range(len(pts)))
            self.assertGreater(ny * (4 - pts[0][1]), 0)

    def test_water_surface(self):
        # 흐르는 물: 물가가 0 m(하류 x=0)에서 10 m(상류 x=400)로 오르는 4 m 폭 띠 + 둑 꼭대기 튀는 값 하나, 끝에 고인 물(연못 z 3)
        verts, faces = [], []
        for k in range(41):
            x = k * 10.0
            z = x / 40.0 + (20.0 if k == 20 else 0.0)   # 1/40 = 2.5 % 기울기, x=200 물가에 둑 꼭대기 +20 m
            verts += [(x, 0.0, z), (x, 4.0, z)]
            if k:
                faces.append((2 * k - 2, 2 * k, 2 * k + 1, 2 * k - 1))
        pond = ([(-10.0, 0.0, 3.0), (0.0, 0.0, 3.5), (0.0, 4.0, 3.5), (-10.0, 4.0, 3.0)], [(0, 1, 2, 3)])
        ring = [(-1000, -1000), (1000, -1000), (1000, 1000), (-1000, 1000)]
        (river, still), levels = u.get_water_surface([(verts, faces), pond], [False, True], ring, 50.0, 0.05, 10.0)
        self.assertEqual({v[2] for v in still}, {3.0})   # 고인 물 = 물가 하위 10 % 평면
        zs = [v[2] for v in river[0::2]]
        self.assertTrue(all(b >= a - 0.05 for a, b in zip(zs, zs[1:])), zs)   # 하류 → 상류로 내려가지 않는다(튀는 값에 솟지 않는다)
        self.assertLess(max(zs), 10.0)   # 물가 높이를 넘지 않는다
        self.assertGreater(zs[-1], 7.0)   # 상류가 하류 수위로 가라앉지 않는다(2.5 % 기울기를 따른다)
        self.assertLess(abs(river[0][2] - river[1][2]), 0.05)   # 단면은 양안이 같은 높이
        self.assertLessEqual(river[0][2], 3.0 + 1e-6)   # 연못과 만나는 물가는 연못 수위 이하
        self.assertEqual(levels[1], (3.0, 3.0))

    def test_noded_segments(self):
        # 겹친 변(두 네모가 x=10에서 맞닿음)과 십자 교차(가운데 네모가 걸침) — 노딩 뒤 겹치는 선분 없이 교차점에서 나뉜다
        a = [(0, 0), (10, 0), (10, 10), (0, 10)]
        b = [(10, 0), (20, 0), (20, 10), (10, 10)]
        c = [(5, 5), (15, 5), (15, 15), (5, 15)]
        segs = u.get_noded_segments([a, b, c])
        self.assertEqual(len(segs), len(set(segs)))
        self.assertEqual(sum(1 for p, q in segs if p[0] == q[0] == 10.0 and 0 <= p[1] <= 10 and 0 <= q[1] <= 10), 2)   # x=10 공유 변 한 번만, (10,5)에서 나뉨
        self.assertIn(((5.0, 10.0), (10.0, 10.0)), segs)   # c의 왼쪽 변 × a의 위 변 교차점 (5, 10)에서 나뉨
        # 제약선으로 나뉜 영역: 네모 하나를 대각선으로 두 삼각형 → 대각선이 제약이면 두 영역, 아니면 한 영역
        verts, faces = [(0, 0), (1, 0), (1, 1), (0, 1)], [(0, 1, 2), (0, 2, 3)]
        self.assertEqual(len(u.get_split_triangles(verts, faces, [((0, 0), (1, 1))])), 2)
        self.assertEqual(len(u.get_split_triangles(verts, faces, [((0, 0), (1, 0))])), 1)

    def test_polygon_index(self):
        idx = u.PolygonIndex([[[(0, 0), (10, 0), (10, 10), (0, 10)], [(4, 4), (6, 4), (6, 6), (4, 6)]]])   # 구멍 있는 네모
        self.assertEqual([idx.contains(2, 2), idx.contains(5, 5), idx.contains(11, 5)], [True, False, False])
        self.assertEqual([idx.is_near(12, 5, 3.0), idx.is_near(15, 5, 3.0), idx.is_near(5, 5, 1.0)], [True, False, True])

    def test_shore_fitted(self):
        water = ([(0, 0, 1.0), (10, 0, 2.0), (10, 4, 2.0), (0, 4, 1.0)], [(0, 1, 2, 3)])
        bank = [(5, 0, 7.0), (5, -3, 9.0), (10, 2, 4.0)]   # 물가선 위 점은 그 자리 수면(보간)으로, 물에서 떨어진 점은 그대로
        self.assertEqual(u.get_shore_fitted(bank, u.WaterShore(water), reach=0), [(5, 0, 1.5), (5, -3, 9.0), (10, 2, 2.0)])
        # 물가 비탈(2026-11-08) — reach 안은 smoothstep으로 수면 쪽으로, reach 밖·수면보다 낮은 점은 그대로
        out = u.get_shore_fitted([(5, -3, 9.0), (5, -20, 9.0), (5, -1, 0.5)], u.WaterShore(water), reach=10.0)
        t = 0.3
        self.assertAlmostEqual(out[0][2], 1.5 + (9.0 - 1.5) * t * t * (3 - 2 * t), places=6)
        self.assertEqual(out[1][2], 9.0)
        self.assertEqual(out[2][2], 0.5)

    def test_contours(self):
        tri = ((0, 0, 0.0), (10, 0, 10.0), (0, 10, 0.0))
        segments = u.get_contour_segments([tri], 5.0)
        self.assertEqual([round(s[0][2]) for s in segments], [5, 10])   # 꼭짓점이 딱 10 m면 길이 0 토막
        self.assertAlmostEqual(segments[0][0][0], 5.0)
        self.assertAlmostEqual(u.TriangleZ([tri]).get_z(5.0, 2.0), 5.0)


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


class SteppedMeshTinTest(SteppedMeshTest):
    """같은 검사를 TIN 단면 교차점(tin=)으로 — TIN은 쿼드를 반대 대각선으로 나눠 메시 변과 단면이 다르다(대각선 교차점이 메시 보간과 어긋나도 틈이 없어야)."""

    def setUp(self):
        super(SteppedMeshTinTest, self).setUp()
        n = self.N
        tin_faces = []
        for j in range(n):
            for i in range(n):
                a = j * (n + 1) + i
                tin_faces += [(a, a + 1, a + n + 1), (a + 1, a + n + 2, a + n + 1)]
        self.tin = u.TinProfile(self.verts, tin_faces, 4.0)
        self.out_verts, self.out_faces = u.get_stepped_mesh(self.verts, self.faces, self.STEP, self.tin)

    def test_stepped_edges_match_mesh(self):
        out = set(self.out_verts)
        for i in range(self.N):
            for p, q in u.get_stepped_edges(self.verts[i], self.verts[i + 1], self.STEP, self.tin):
                self.assertIn(p, out)
                self.assertIn(q, out)


class SteppedTinPlateauTest(unittest.TestCase):
    """등고선 TIN의 평평한 삼각형 — 3 m 격자 정점이 단 높이에 정확히 놓여도 단 테두리는 격자가 아니라 TIN의 평지 끝(실제 등고선)을 따른다
    (죽림리 301-3 구역 톱니, 2026-11-08). 평지 z = 2(x + 0.5·y ≥ 13), 그 아래는 비탈."""

    def test_wall_follows_tin_plateau_edge(self):
        tin_verts = [(0.0, 0.0, 0.0), (0.0, 30.0, 0.0), (13.0, 0.0, 2.0), (-2.0, 30.0, 2.0), (40.0, 0.0, 2.0), (40.0, 30.0, 2.0)]
        tin = u.TinProfile(tin_verts, [(0, 2, 3), (0, 3, 1), (2, 4, 5), (2, 5, 3)], 10.0)
        verts, faces, n = [], [], 10
        for j in range(n + 1):
            for i in range(n + 1):
                x, y = 3.0 * i + 0.4, 3.0 * j
                verts.append((x, y, min(2.0, 2.0 * (x + 0.5 * y) / 13.0)))   # TIN에 입힌 높이
        for j in range(n):
            for i in range(n):
                a = j * (n + 1) + i
                faces.append((a, a + 1, a + n + 2, a + n + 1))
        for tin_arg, on_edge in ((None, False), (tin, True)):
            out_verts, out_faces = u.get_stepped_mesh(verts, faces, 1.0, tin_arg)
            tops = [out_verts[i] for f in out_faces if len({out_verts[k][:2] for k in f}) == 2 for i in f if abs(out_verts[i][2] - 2.0) < 1e-9]
            self.assertTrue(tops)
            off = max(abs(p[0] + 0.5 * p[1] - 13) for p in tops)
            if on_edge:
                self.assertLess(off, 0.01)   # TIN 평지 끝 선 위
            else:
                self.assertGreater(off, 0.5)   # 선형 보간은 격자 정점을 따라간다(톱니)


class FlatFillTest(unittest.TestCase):
    """등고선 TIN의 평평한 삼각형 — 골짜기(이웃이 높다)는 안쪽을 낮추고 꼭대기(이웃이 낮다)는 올린다, 등고선 높이가 아닌 평지는 그대로."""

    def _valley(self, side_z):
        # 가운데 띠(x 10~30)는 양쪽 50 m 등고선 점끼리 이은 평지, 바깥(x 0·40)은 side_z
        verts, faces = [], []
        for j in range(7):
            for x, z in ((0, side_z), (10, 50.0), (30, 50.0), (40, side_z)):
                verts.append((float(x), j * 10.0, z))
        for j in range(6):
            a = j * 4
            for i in range(3):
                faces += [(a + i, a + i + 1, a + i + 5), (a + i, a + i + 5, a + i + 4)]
        return verts, faces

    def test_valley_goes_down_ridge_goes_up(self):
        for side_z, sign in ((55.0, -1), (45.0, 1)):
            verts, faces = self._valley(side_z)
            pts = u.get_flat_fill_points(verts, faces, [45.0, 50.0, 55.0])
            self.assertTrue(pts)
            self.assertTrue(all(10 <= x <= 30 for x, _y, _z in pts))
            zs = [z for _x, _y, z in pts]
            extreme = min(zs) if sign < 0 else max(zs)
            self.assertTrue(0.5 < abs(extreme - 50.0) <= 2.5 + 1e-9)   # 이웃 등고선 간격 5 m의 절반 안
            self.assertTrue(all((z - 50.0) * sign >= 0 for z in zs))

    def test_not_contour_level_untouched(self):
        verts, faces = self._valley(55.0)
        self.assertEqual(u.get_flat_fill_points(verts, faces, [45.0, 55.0]), [])


class SmoothedZTest(unittest.TestCase):
    def test_fixed_and_band(self):
        # 줄 9점: 0·8번 고정, 4번은 등고선 높이(50) 위라 그대로, 나머지는 이웃 평균으로 가되 [45, 50]·[50, 55] 밖으로 못 나간다
        zs = [45.0, 49.9, 46.0, 49.0, 50.0, 54.0, 51.0, 54.5, 55.0]
        nb = [[1]] + [[i - 1, i + 1] for i in range(1, 8)] + [[7]]
        fixed = [True] + [False] * 7 + [True]
        out = u.get_smoothed_z(zs, nb, fixed, [45.0, 50.0, 55.0], 200)
        self.assertEqual((out[0], out[4], out[8]), (45.0, 50.0, 55.0))
        for z0, z1 in zip(zs, out):
            lo = 45.0 if z0 < 50 else 50.0
            self.assertTrue(lo <= z1 <= lo + 5.0)
        self.assertAlmostEqual(out[2], 47.5, 3)   # 45 → 50 사이 곧은 비탈
        self.assertAlmostEqual(out[6], 52.5, 3)

class BoundaryLoopsTest(unittest.TestCase):
    def test_hole_and_pinch(self):
        n = 3
        quads = [(j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i) for j in range(n) for i in range(n)]
        loops = u.get_boundary_loops([q for k, q in enumerate(quads) if k != 4])   # 가운데 칸을 뺀 고리
        self.assertEqual(sorted(len(loop) for loop in loops), [4, 12])
        self.assertIsNone(u.get_boundary_loops([quads[0], quads[4]]))   # 꼭짓점 하나로 맞닿음


class PlanarFacesTest(unittest.TestCase):
    """Brep 조립용 평면 면 — 구멍 있는 묶음은 면 하나(바깥 반시계 + 구멍 시계), 좌표가 같은 정점은 하나, 평면 아닌 4각형은 삼각형 둘."""

    def _area(self, uv):
        ring = [q[1:] for q in uv]
        return u.get_ring_area(ring) * u.get_ring_orientation(ring)

    def test_group_with_hole_shares_vertices(self):
        n = 3
        verts = [(float(i), float(j), 5.0) for j in range(n + 1) for i in range(n + 1)]
        quads = [(j * (n + 1) + i, j * (n + 1) + i + 1, (j + 1) * (n + 1) + i + 1, (j + 1) * (n + 1) + i) for j in range(n) for i in range(n)]
        verts += [verts[i] for i in quads[4]]   # 가운데 칸은 따로 둔 정점(용접 안 한 계단 지형처럼)
        faces = [q for k, q in enumerate(quads) if k != 4] + [tuple(range(16, 20))]
        points, planes = u.get_planar_faces(verts, faces, [list(range(8))], 1e-3)
        self.assertEqual(len(points), 16)
        self.assertEqual(len(planes), 2)
        ring = max(planes, key=lambda pl: len(pl[3]))
        self.assertEqual([len(loop) for loop in ring[3]], [12, 4])
        self.assertAlmostEqual(self._area(ring[3][0]), 9.0)
        self.assertAlmostEqual(self._area(ring[3][1]), -1.0)
        center = min(planes, key=lambda pl: len(pl[3]))
        self.assertEqual({q[0] for q in center[3][0]}, {q[0] for q in ring[3][1]})   # 구멍과 가운데 면이 같은 정점

    def test_flipped_group_falls_back(self):
        # 평탄면 높이를 가로지르는 경계 벽 띠 — 위로 선 면, 꼬인 4각형, 아래로 선 면이 한 평면 묶음(성수 333-139 site_wall)
        verts = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1), (2, 0, 0), (2, 0, -1), (3, 0, 0), (3, 0, -1)]
        faces = [(0, 1, 2, 3), (1, 4, 5, 2), (4, 6, 7, 5)]
        _points, planes = u.get_planar_faces(verts, faces, [[0, 1, 2]], 1e-3)
        self.assertEqual(len(planes), 4)   # 면 둘 + 꼬인 4각형 → 삼각형 둘
        self.assertAlmostEqual(sum(self._area(pl[3][0]) for pl in planes), 3.0)

    def test_wall_and_bent_quad(self):
        verts = [(0, 0, 0), (1, 0, 0), (1, 0, 1), (0, 0, 1), (0, 0, 0), (1, 0, 0), (1, 1, 0.5), (0, 1, 0)]
        points, planes = u.get_planar_faces(verts, [(0, 1, 2, 3), (4, 7, 6, 5)], [], 1e-3)
        self.assertEqual(len(points), 6)
        self.assertEqual(len(planes), 3)   # 벽 하나 + 꺾인 4각형 → 삼각형 둘
        for _o, _x, _y, loops in planes:
            self.assertGreater(self._area(loops[0]), 0)



if __name__ == "__main__":
    unittest.main()


class OutputNameTest(unittest.TestCase):
    def test_lang_fallback_and_names(self):
        self.assertEqual(u.get_output_lang({}), constants.OUTPUT_LANG_DEFAULT)
        self.assertEqual(u.get_output_lang({"output_lang": "xx"}), constants.OUTPUT_LANG_DEFAULT)
        self.assertEqual(u.get_output_name("more", "en") % 1, "+1")
        self.assertEqual(u.get_output_name("styles", "ko", "vivid"), "선명")
        self.assertEqual(u.get_output_name("styles", "ja", "vivid"), "Vivid")   # 아직 없는 언어 → 영어
        self.assertEqual(u.get_sheet_label("land_use", "ko"), "토지이용현황")
        self.assertEqual(u.get_sheet_label("lot_size", "en"), "Plot size")   # 파일 이름·제목이 같은 i18n.json 이름
        self.assertEqual(u.get_sheet_label("lot_size", "ja"), "区画規模")
        self.assertEqual(u.get_safe_file_part("Land use / 2"), "Land_use_2")
        self.assertEqual(u.get_safe_file_part("녹지·수계"), "녹지수계")


class BufferedLineTest(unittest.TestCase):
    def test_straight_and_bent(self):
        ring = u.get_buffered_line_ring([(0, 0), (100, 0)], 10)
        self.assertEqual(ring[0], ring[-1])
        self.assertAlmostEqual(abs(u.get_ring_area(ring)), 100 * 10 + 3 * 25, delta=1)   # 반원 두 개 = 12각형 내접원
        for (x, y), inside in (((50, 4.9), True), ((50, 5.1), False), ((-4, 0), True), ((-6, 0), False)):
            self.assertEqual(u.is_point_in_ring(x, y, ring), inside, (x, y))
        bent = u.get_buffered_line_ring([(0, 0), (50, 0), (50, 50)], 10)   # ㄱ자 — 바깥 꺾임 호, 안쪽 교점
        for (x, y), inside in (((47, 25), True), ((40, 45), False), ((54, -4), False), ((53, -3), True), ((56, 3), False)):
            self.assertEqual(u.is_point_in_ring(x, y, bent), inside, (x, y))
        hairpin = u.get_buffered_line_ring([(0, 0), (30, 0), (31, 0.5), (0, 1)], 10)   # 되돌아오는 급꺾임 — 캡슐 합집합으로
        self.assertFalse(u.is_ring_self_intersecting(hairpin))
        self.assertTrue(u.is_point_in_ring(15, 0.5, hairpin))
        self.assertFalse(u.is_point_in_ring(15, 7, hairpin))
        self.assertIsNone(u.get_buffered_line_ring([(0, 0), (0, 0)], 10))
        self.assertIsNone(u.get_buffered_line_ring([(0, 0), (1, 1)], 0))



class StreetDetailTest(unittest.TestCase):
    """가로·철도 디테일(2026-11-08) — 연석(차도 내리기)·선로 단면·노면표시."""

    def test_curb(self):
        road = ([(0, 0, 1), (10, 0, 1), (20, 0, 1), (0, 10, 1), (10, 10, 1), (20, 10, 1)], [(0, 1, 4, 3), (1, 2, 5, 4)])
        (verts, faces), (wall_verts, wall_faces) = u.get_curb(road, [(0, 0), (20, 0), (20, -50), (0, -50)], 0.15)
        self.assertEqual(faces, road[1])
        self.assertTrue(all(abs(z - 0.85) < 1e-9 for _x, _y, z in verts))
        self.assertEqual(len(wall_faces), 4)   # 경계 변 6개 중 범위 링(y=0) 위 2개는 지형 옆면이 막는다
        for face in wall_faces:   # 옆면은 차도 쪽(안쪽)을 본다
            a, b, c = (wall_verts[i] for i in face[:3])
            nx, ny = (b[1] - a[1]) * (c[2] - b[2]), -(b[0] - a[0]) * (c[2] - b[2])
            self.assertGreater(nx * (10 - (a[0] + b[0]) / 2) + ny * (5 - (a[1] + b[1]) / 2), 0)
        self.assertEqual(u.get_curb(road, [], 0.0), (road, ([], [])))
        # 차도 안 실금 — 가운데 변 정점이 0.1 mm 어긋나 두 벌(삼각분할 겹친 경계). 그 변에는 연석을 세우지 않는다
        cracked = ([(0, 0, 1), (10, 0, 1), (0, 10, 1), (10, 10, 1), (10.0001, 0, 1), (20, 0, 1), (10.0001, 10, 1), (20, 10, 1)], [(0, 1, 3, 2), (4, 5, 7, 6)])
        _road, (_v, walls) = u.get_curb(cracked, [(0, 0), (20, 0), (20, -50), (0, -50)], 0.15)
        self.assertEqual(len(walls), 4)   # 바깥 둘레(위 변 둘·양 끝 둘)만

    def test_line_runs(self):
        runs = u.get_line_runs([(0, 0), (100, 0)], lambda x, y: 40 < x < 60, 2.0)
        self.assertEqual([(r[0][0], r[-1][0]) for r in runs], [(0.0, 40.0), (60.0, 100.0)])

    def test_track_meshes(self):
        dims = constants.RAIL_TRACK
        out = u.get_track_meshes([([(0, 0), (100, 0)], 1.435)], lambda x, y: 10.0, dims, 5.0, 30.0)
        rails = out["rails"][0]
        self.assertAlmostEqual(max(v[2] for v in rails), 10 + dims["ballast_height"] + dims["sleeper_rise"] + dims["rail_height"])
        self.assertAlmostEqual(max(v[1] for v in rails) - min(v[1] for v in rails), 1.435 + 2 * dims["rail_width"])
        self.assertEqual(len(out["sleepers"][1]), 5 * 167)   # 0.3 m부터 0.6 m마다 100 m 안 = 167개, 상자마다 5면
        verts, faces = out["ballast"]
        a, b, c = (verts[i] for i in faces[1][:3])   # 단면 둘째 변 = 윗면 — 위를 본다
        self.assertGreater((b[0] - a[0]) * (c[1] - b[1]) - (b[1] - a[1]) * (c[0] - b[0]), 0)

    def test_marking_meshes(self):
        style = {"widths": constants.MARKING_WIDTHS, "dash": (3.0, 5.0), "gap": 0.1, "bar": (0.5, 0.5), "lift": {"white": 0.02, "yellow": 0.03}, "step": 3.0}
        out = u.get_marking_meshes([([(0, 0), (16, 0)], "lane", "white", "dashed"), ([(0, 5), (10, 5)], "center", "yellow", "double")],
                                   [[(0, 20), (20, 20), (20, 24), (0, 24)]], lambda x, y: 1.0, style)
        verts, faces = out["white"]
        dashes = sorted({round(verts[i][0], 3) for face in faces for i in face if verts[i][1] < 1})
        self.assertEqual(dashes, [0.0, 3.0, 8.0, 11.0])   # 3 m 칠·5 m 빈칸, 16 m 끝은 빈칸 시작
        self.assertEqual(sum(1 for face in faces if verts[face[0]][1] >= 20), 20 * 2 * 2)   # 20 m 횡단보도 = 줄무늬 20개(0.5·0.5), 길이 4 m를 step 3 m로 둘로, 조각마다 삼각형 둘
        self.assertTrue(all(abs(v[2] - 1.02) < 1e-9 for v in verts))
        self.assertEqual(sorted({round(v[1], 3) for v in out["yellow"][0]}), [4.8, 4.95, 5.05, 5.2])

    def test_marking_no_coincident_corners(self):
        """껍질로 자른 횡단보도 줄무늬에 겹친 꼭짓점이 남지 않는다(Rhino가 메시를 거절했다 — 2026-11-08 성수)."""
        style = {"widths": constants.MARKING_WIDTHS, "dash": (3.0, 5.0), "gap": 0.1, "bar": (0.5, 0.5), "lift": {"white": 0.02, "yellow": 0.03}, "step": 3.0}
        ring = [(0, 0), (12, 2), (11.5, 6), (-0.5, 4)]   # 비스듬한 횡단보도 — 줄무늬 끝이 껍질 꼭짓점에 걸친다
        verts, faces = u.get_marking_meshes([], [ring], lambda x, y: 0.0, style)["white"]
        for face in faces:
            pts = [verts[i] for i in face]
            self.assertTrue(all(math.hypot(a[0] - b[0], a[1] - b[1]) > 1e-6 for a, b in zip(pts, pts[1:] + pts[:1])), pts)

    def test_welded_mesh(self):
        """조각 이음매의 mm 어긋난 정점을 하나로 — 공유 변이 생기고 경계 변(SketchUp이 그리는 선)이 바깥 둘레만 남는다(2026-11-08)."""
        a = ([(0, 0, 1), (10, 0, 1), (10, 10, 1), (0, 10, 1)], [(0, 1, 2, 3)])
        b = ([(10.0004, 0, 1), (20, 0, 1), (20, 10, 1), (10.0002, 10.0003, 1)], [(0, 1, 2, 3)])
        verts = a[0] + b[0]
        faces = a[1] + [tuple(4 + i for i in f) for f in b[1]]
        self.assertEqual(len(u._get_boundary_edges(verts, faces)), 8)   # 이음매가 양쪽 테두리로 남는다
        welded = u.get_welded_mesh(verts, faces, 0.005)
        self.assertEqual(len(welded[0]), 6)
        self.assertEqual(len(u._get_boundary_edges(*welded)), 6)
        sliver = u.get_welded_mesh([(0, 0, 0), (5, 0, 0), (5, 0.001, 0)], [(0, 1, 2)], 0.005)   # 이음매 납작한 틈 — 버린다
        self.assertEqual(sliver[1], [])


class BridgeTest(unittest.TestCase):
    """교량·고가 상판(2026-11-13) — 축·끝점 가리기, 상판 높이(표고점·추정), 닫힌 상판 메시."""

    RING = [(0.0, 0.0), (100.0, 0.0), (100.0, 10.0), (0.0, 10.0)]   # 100 m × 10 m 상판

    @staticmethod
    def fan(rings, _loose):   # 볼록 면만 — 무게중심 부채꼴(호스트 CDT 대신)
        ring = rings[0]
        cx, cy = sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)
        xy = [(cx, cy)] + list(ring)
        return xy, [(0, i + 1, (i + 1) % len(ring) + 1) for i in range(len(ring))]

    def test_axes(self):
        ext = [(-200.0, -200.0), (300.0, -200.0), (300.0, 200.0), (-200.0, 200.0)]
        lines = [[(-20.0, 5.0), (120.0, 5.0)],   # 상판을 따라 건너간다 — 축, 양 끝 땅
                 [(50.0, -20.0), (50.0, 30.0)],  # 밑을 직각으로 건넌다 — 축 아님
                 [(20.0, 3.0), (60.0, 3.0)]]     # 상판 안에서 끊긴 선 조각 — 축이지만 끝점 아님
        axes, ends = u.get_bridge_axes([[self.RING]], lines, ext, 3.0, 3.0)
        self.assertEqual(len(axes), 2)
        self.assertEqual(len(ends), 2)
        self.assertTrue(all(min(abs(x), abs(x - 100.0)) <= 3.0 for x, _y in ends))   # 테두리에서 조밀화 간격 안
        rail_axes, _ = u.get_bridge_axes([[self.RING]], lines, ext, 3.0, 3.0, along_only=False)
        self.assertEqual(len(rail_axes), 3)   # 선로는 나란하지 않아도 상판 위

    def test_top_z(self):
        ground = lambda x, y: 0.0
        rule = u.BridgeDeck([[self.RING]], [], [(0.0, 5.0), (100.0, 5.0)], [], 6.0, 1.5, ground)
        self.assertEqual(rule.src, "rule")
        self.assertAlmostEqual(rule.top_z(50.0, 5.0), 50.0 * constants.BRIDGE_GRADE + constants.BRIDGE_LIFT)   # 끝점에서 경사로 오른다
        self.assertLess(rule.top_z(1.0, 5.0), 0.5)
        spot = u.BridgeDeck([[self.RING]], [], [(0.0, 5.0), (100.0, 5.0)], [(50.0, 5.0, 8.0), (60.0, 5.0, 0.5)], 6.0, 1.5, ground)
        self.assertEqual((spot.src, len(spot.spots)), ("spot", 1))   # 지반에 붙은 표고점(교량 밑 도로)은 뺀다
        self.assertAlmostEqual(spot.top_z(50.0, 5.0), 8.0)
        self.assertTrue(spot.is_on(50.0, 5.0, 1.0, 0.0) and not spot.is_on(50.0, 5.0, 0.0, 1.0))   # 나란한 차선만 상판 위
        self.assertTrue(spot.is_on(50.0, 5.0, 0.0, 1.0, "rail") is False)   # 도로 상판 위 선로는 없다

    def test_meshes(self):
        ext = [(-200.0, -200.0), (300.0, -200.0), (300.0, 200.0), (-200.0, 200.0)]
        deck = u.BridgeDeck([[self.RING]], [[(0.0, 5.0), (100.0, 5.0)]], [], [(50.0, 5.0, 10.0)], 6.0, 1.5, lambda x, y: 0.0)
        out = u.get_bridge_meshes([deck], self.fan, ext, 3.0)
        verts, faces = out["deck"]
        edges = {}
        for face in faces:
            for a, b in zip(face, face[1:] + face[:1]):
                key = tuple(sorted((verts[a], verts[b])))
                edges[key] = edges.get(key, 0) + 1
        self.assertTrue(edges and all(n == 2 for n in edges.values()))   # 윗면·밑면·옆면이 닫힌 판
        self.assertTrue(out["parapet"][1] and out["pier"][1])
        self.assertTrue(all(abs(z - 10.0) < 1e-6 or abs(z - 8.5) < 1e-6 for _x, _y, z in verts))   # 끝점 없음 = 표고점 높이 그대로


class DetailTest(unittest.TestCase):
    """디테일(2026-11-13) — 파라펫·층선·옹벽·담장·가로수 메시."""

    SQUARE = [(0.0, 0.0), (20.0, 0.0), (20.0, 20.0), (0.0, 20.0)]

    def test_parapet(self):
        verts, faces = u.get_parapet_mesh([([[self.SQUARE]], 30.0), ([[[(0, 0), (3, 0), (3, 3), (0, 3)]]], 9.0)], constants.PARAPET)
        self.assertEqual(len(faces), 4 * 3)   # 작은 동(9 ㎡)은 빼고, 변마다 바깥·위·안
        zs = sorted({z for _x, _y, z in verts})
        self.assertEqual(zs, [30.0, 30.0 + constants.PARAPET["height"]])
        inner = [(x, y) for x, y, z in verts if 0 < x < 20 and 0 < y < 20]
        self.assertTrue(inner and all(abs(min(x, y, 20 - x, 20 - y) - constants.PARAPET["width"]) < 1e-6 for x, y in inner))   # 지붕 쪽으로 들인다

    def test_floor_rings(self):
        rings = u.get_floor_rings([([[self.SQUARE]], 10.0, 12.0, 4), ([[self.SQUARE]], 0.0, 3.0, 1)], 2)
        self.assertEqual([round(pts[0][2], 3) for pts, _closed in rings], [13.0, 16.0, 19.0])   # 1층 위부터 지붕 아래까지, 단층은 뺀다

    def test_retaining_wall(self):
        step = lambda x, y: 10.0 if y > 0 else 6.0   # y = 0 선에서 4 m 단
        verts, faces = u.get_retaining_wall_mesh([[(0.0, 0.0), (20.0, 0.0)]], step, constants.WALL)
        self.assertTrue(faces)
        self.assertAlmostEqual(max(z for _x, _y, z in verts), 10.0 + constants.WALL["coping"])
        self.assertAlmostEqual(min(z for _x, _y, z in verts), 6.0 - constants.WALL["embed"])
        self.assertEqual(u.get_retaining_wall_mesh([[(0.0, 0.0), (20.0, 0.0)]], lambda x, y: 5.0, constants.WALL), ([], []))   # 지형에 단이 없으면 세우지 않는다

    def test_fence_and_trees(self):
        verts, faces = u.get_fence_mesh([[(0.0, 0.0), (9.0, 0.0)]], lambda x, y: 2.0, constants.FENCE)
        self.assertAlmostEqual(max(z for _x, _y, z in verts), 2.0 + constants.FENCE["height"])
        trees = [(0.0, 0.0, "은행나무 암나무", None, None), (10.0, 0.0, "모르는나무", None, None), (20.0, 0.0, "", 15.0, 6.0)]
        verts, faces = u.get_tree_mesh(trees, lambda x, y: 1.0, constants.TREES, constants.TREE_TRUNK)
        tops = [max(z for x, _y, z in verts if abs(x - cx) < 5) for cx in (0.0, 10.0, 20.0)]
        self.assertAlmostEqual(tops[0], 1.0 + constants.TREES["은행나무"][0])   # 수종 앞부분 일치(원뿔 꼭대기)
        self.assertAlmostEqual(tops[2], 16.0)   # 데이터 높이가 있으면 그 값
