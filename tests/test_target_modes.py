"""대상지 방식 3가지(lots·area·point)와 결과 좌표 방식(origin·world) — Rhino 없이 도는 부분 전부."""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import basemap_ai   # noqa: E402
import constants   # noqa: E402
import context_builder   # noqa: E402
import context_report   # noqa: E402
import lot_db   # noqa: E402
import non_rhino_utils   # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
SITE_DB = str(FIXTURE_DIR / "seongsu_site.db")
CONTEXT_DB = str(FIXTURE_DIR / "seongsu_context.db")
HAS_FIXTURES = os.path.exists(SITE_DB) and os.path.exists(CONTEXT_DB)   # 컨텍스트 픽스처는 저장소에 없다(수치지형도 — dev_make_fixture.py)


def _load_cmd_site():
    spec = importlib.util.spec_from_file_location("cmd_site_target_test", SCRIPTS_DIR / "cmd_site.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cmd_site = _load_cmd_site()


def _center():
    lot = lot_db.load([constants.TEST_CONTEXT_PNU], SITE_DB).lots[0]
    return (lot.min_x + lot.max_x) * 0.5, (lot.min_y + lot.max_y) * 0.5


def _box(cx, cy, half_w, half_h):
    return [(cx - half_w, cy - half_h), (cx + half_w, cy - half_h), (cx + half_w, cy + half_h), (cx - half_w, cy + half_h)]


class RingTest(unittest.TestCase):
    def test_clean_ring_ccw_without_closing_point(self):
        ring = non_rhino_utils.get_clean_ring([(0, 0), (0, 10), (10, 10), (10, 0), (0, 0)])   # 시계 + 닫힘점
        self.assertEqual(len(ring), 4)
        self.assertEqual(non_rhino_utils.get_ring_orientation(ring), 1)

    def test_ring_problems(self):
        self.assertIn("자기교차", non_rhino_utils.get_ring_problem([(0, 0), (100, 100), (100, 0), (0, 100)]))
        self.assertIn("너무 작", non_rhino_utils.get_ring_problem(_box(0, 0, 4, 4)))
        self.assertIn("너무 큽", non_rhino_utils.get_ring_problem(_box(0, 0, 3000, 10)))
        self.assertIn("3개 이상", non_rhino_utils.get_ring_problem([(0, 0), (10, 0)]))
        self.assertEqual(non_rhino_utils.get_ring_problem(non_rhino_utils.get_clean_ring(_box(0, 0, 50, 50))), "")

    def test_inside_fraction(self):
        area = _box(0, 0, 50, 50)
        lot = lambda ring: [[ring]]
        self.assertEqual(non_rhino_utils.get_inside_fraction(lot(_box(0, 0, 10, 10)), area), 1.0)
        self.assertEqual(non_rhino_utils.get_inside_fraction(lot(_box(200, 0, 10, 10)), area), 0.0)
        half = non_rhino_utils.get_inside_fraction(lot(_box(50, 0, 10, 10)), area)   # 경계가 필지 한가운데
        self.assertAlmostEqual(half, 0.5, delta=0.05)


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class ResolveTargetTest(unittest.TestCase):
    def test_lots_key_matches_previous_lot_key(self):
        request = context_builder.get_request_with_defaults({"pnus": [constants.TEST_CONTEXT_PNU], "site_db": SITE_DB})
        target = context_builder.resolve_target(request)
        self.assertEqual(target.mode, "lots")
        self.assertEqual(target.key, hashlib.sha1(constants.TEST_CONTEXT_PNU.encode()).hexdigest()[:8])   # 예전 UDT_LOT_KEY와 같아야 다시 넣기·정리가 된다
        self.assertEqual(len(target.site_rings), 1)

    def test_area_lots_and_name(self):
        cx, cy = _center()
        request = context_builder.get_request_with_defaults({"target": {"mode": "area", "ring": _box(cx, cy, 150, 100)}, "site_db": SITE_DB})
        target = context_builder.resolve_target(request)
        self.assertIn(constants.TEST_CONTEXT_PNU, [lot.pnu for lot in target.lots])
        self.assertTrue(target.name.endswith("_구역"))
        self.assertAlmostEqual(non_rhino_utils.get_ring_area(target.site_rings[0]), 60000.0, delta=1.0)

    def test_area_invalid_is_domain_error(self):
        request = context_builder.get_request_with_defaults({"target": {"mode": "area", "ring": [(0, 0), (1, 0), (1, 1)]}, "site_db": SITE_DB})
        with self.assertRaises(context_builder.DomainError) as ctx:
            context_builder.resolve_target(request)
        self.assertEqual(ctx.exception.code, "area_invalid")

    def test_snap_rings_skip_linear_lots(self):
        cx, cy = _center()
        ring = _box(cx, cy, 150, 100)
        add, cut = context_builder.get_snap_rings(ring, SITE_DB)
        fractions = context_builder.get_area_lot_fractions(ring, SITE_DB)
        linear = [lot for lot, _f in fractions if lot.land_category in constants.AREA_SNAP_LINEAR_CATEGORIES]
        self.assertTrue(linear)   # 성수 구역에는 도로 필지가 걸친다 — 이것들은 더하지도 빼지도 않는다
        self.assertEqual(len(add) + len(cut), len(fractions) - len(linear))

    def test_point_name(self):
        cx, cy = _center()
        request = context_builder.get_request_with_defaults({"target": {"mode": "point", "center": [cx, cy]}, "site_db": SITE_DB})
        target = context_builder.resolve_target(request)
        self.assertEqual((target.lots, target.site_rings), ([], []))
        self.assertEqual(target.name, "성수동2가_333-139_일대")


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class PrepareTest(unittest.TestCase):
    def test_area_prepare_outputs(self):
        cx, cy = _center()
        with tempfile.TemporaryDirectory() as tmp:
            p = context_builder.prepare({"target": {"mode": "area", "ring": _box(cx, cy, 150, 100)}, "options": {"radius": 300, "shape": "site"},
                                         "site_db": SITE_DB, "context_db": CONTEXT_DB, "result_root": tmp})
            self.assertEqual(p.mode, "area")
            self.assertTrue(p.target_lots)
            self.assertFalse({lot.pnu for lot in p.target_lots} & {lot.pnu for lot in p.near_lots})
            self.assertEqual(sorted(p.extent_ring), sorted(p.site_rings[0]))   # 그린 경계 그대로가 범위
            rect = context_builder.prepare({"target": {"mode": "area", "ring": _box(cx, cy, 150, 100)}, "options": {"radius": 300, "shape": "rect"},
                                            "site_db": SITE_DB, "context_db": CONTEXT_DB})
            self.assertLess(non_rhino_utils.get_bbox(rect.extent_ring)[0], cx - 150 - 299)   # 사각형은 경계에서 반경만큼 밖
            ai = basemap_ai.write_basemap(p, 5000, tmp)
            self.assertEqual(ai["counts"]["10_site"], 2)   # 구역 경계 + 범위
            path = context_report.write_context_json(p, {}, tmp)
            meta = json.load(open(path, encoding="utf-8"))
            self.assertEqual((meta["mode"], meta["target"]["mode"], meta["lot_key"]), ("area", "area", p.target_key))
            again = context_builder.export_basemap(tmp, 1000, SITE_DB, CONTEXT_DB)   # context.json의 target으로 다시 쓴다
            self.assertTrue(os.path.exists(again["path"]))

    def test_point_frame_extent(self):
        cx, cy = _center()
        p = context_builder.prepare({"target": {"mode": "point", "center": [cx, cy]}, "options": {"shape": "frame", "scales": [1000, 3000]},
                                     "site_db": SITE_DB, "context_db": CONTEXT_DB})
        self.assertEqual(non_rhino_utils.get_bbox(p.extent_ring), p.frame_bounds[3000])   # 가장 큰 축척 프레임 = 범위
        self.assertEqual(p.target_lots, [])
        self.assertTrue(p.overlays)   # 필지 없이도 중심 주변 오버레이를 읽는다

    def test_placement_world_and_mismatch(self):
        cx, cy = _center()
        base = {"target": {"mode": "point", "center": [cx, cy]}, "site_db": SITE_DB, "context_db": CONTEXT_DB}
        p = context_builder.prepare(dict(base, options={"placement": "world"}))
        self.assertEqual(p.doc_origin, (0.0, 0.0))
        self.assertLess(abs(p.origin[0] - cx), constants.ORIGIN_SNAP)   # 형상은 대상지 근처 로컬에서 만든다
        for doc_origin, placement in (((0.0, 0.0), "origin"), (p.origin, "world")):
            with self.assertRaises(context_builder.DomainError) as ctx:
                context_builder.prepare(dict(base, options={"placement": placement}, doc_origin=doc_origin))
            self.assertEqual(ctx.exception.code, "placement_mismatch")


@unittest.skipUnless(HAS_FIXTURES, "tests/fixtures/seongsu_*.db가 없다 (python3 scripts/dev_make_fixture.py)")
class ControllerTest(unittest.TestCase):
    def test_area_state_roundtrip_and_errors(self):
        cx, cy = _center()
        state = cmd_site.get_area_state({"ring_tm": _box(cx, cy, 150, 100)}, SITE_DB)
        self.assertTrue(state["ok"])
        self.assertEqual(state["target_geojson"]["features"][-1]["properties"]["role"], "area")
        moved = cmd_site.get_area_state({"center": state["center"], "offsets": state["offsets"]}, SITE_DB)   # 지도에서 옮겨 놓기
        self.assertLess(max(abs(a[0] - b[0]) + abs(a[1] - b[1]) for a, b in zip(moved["ring_tm"], state["ring_tm"])), 0.05)
        bad = cmd_site.get_area_state({"ring_tm": [(cx, cy), (cx + 100, cy + 100), (cx + 100, cy), (cx, cy + 100)]}, SITE_DB)
        self.assertFalse(bad["ok"])
        self.assertIn("자기교차", bad["text"])
        self.assertTrue(cmd_site.get_area_state({}, SITE_DB)["ok"])   # 지움

    def test_preflight_key_differs_by_target(self):
        lots = cmd_site.get_preflight_key({"pnus": [constants.TEST_CONTEXT_PNU], "radius": 500})
        point = cmd_site.get_preflight_key({"target": {"mode": "point", "center": [1, 2]}, "radius": 500})
        self.assertNotEqual(lots, point)


if __name__ == "__main__":
    unittest.main()
