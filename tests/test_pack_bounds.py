"""팩 범위 — 원천 좌표 오류 몇 개가 매니페스트 bounds를 늘리지 않는지(dev_deploy.get_core_bounds)."""
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
import dev_deploy   # noqa: E402


class CoreBoundsTest(unittest.TestCase):
    def test_outlier_dropped_but_edge_island_kept(self):
        # 시군구 본토 20×20 km 격자 + 서쪽 8 km 섬 몇 개(진짜) + 200 km 밖 좌표 오류 2개(11305 강북구 건물 같은 것)
        points = [(200000.0 + i * 100, 550000.0 + j * 100) for i in range(200) for j in range(200)]
        points += [(192000.0, 551000.0)] * 30 + [(459500.0, 301300.0), (200000.0, 750000.0)]
        min_x, min_y, max_x, max_y = dev_deploy.get_core_bounds(points)
        self.assertLess(min_x, 192000.0)
        self.assertLess(max_x, 230000.0)
        self.assertGreater(min_y, 540000.0)
        self.assertLess(max_y, 580000.0)

    def test_empty(self):
        self.assertIsNone(dev_deploy.get_core_bounds([]))


if __name__ == "__main__":
    unittest.main()
