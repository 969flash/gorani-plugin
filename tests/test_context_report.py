"""context_report — 합성 Prepared(SimpleNamespace)로 메타 5줄·CSV 헤더·BOM·context.json 키."""

import csv
import datetime
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import constants
import context_report
import lot_db

TODAY = datetime.date(2026, 10, 7)


def _read_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _lot(pnu, x, zone="준공업지역", jimok="대", area=100.0):
    return NS(pnu=pnu, address="서울 성동구 성수동2가 %s" % pnu[-7:], lot_number=pnu[-7:], land_category=jimok,
              registered_area=area, geometry_area=area * 0.99, zone_code="UQA230", zone_name=zone, zone_name_2="",
              land_use_status="단독", land_price_won=5_000_000, reference_date="2026-05-13",
              min_x=x, max_x=x + 10, min_y=549000.0, max_y=549010.0)


def _bld(bid, x, floors, src, grade, apr="19950301"):
    return NS(building_id=bid, src_key="bldg:%d" % bid, pnu="1120011500103330139", bld_nm="", usability="02000", strct_cd="21",
              grnd_flr=floors, ugrnd_flr=1, flr_src="grnd_flr", height_m=3.0 * floors, height_src=src, height_grade=grade,
              attr_flag="", use_apr_day=apr, status="active", ngii_kind="", ngii_use="", footprint_area=80.0, total_area=240.0,
              source_id="vworld_building", reference_date="2026-09-06",
              min_x=x, max_x=x + 10, min_y=549000.0, max_y=549010.0)


def _prepared(**overrides):
    ring = [(204264.0, 548552.0), (205264.0, 548552.0), (205264.0, 549552.0), (204264.0, 549552.0)]
    data = dict(
        request={"pnus": [constants.TEST_CONTEXT_PNU], "options": {"floor_breaks": [12, 20]}},
        lot_name="성수동2가_333-139",
        target_lots=[_lot(constants.TEST_CONTEXT_PNU, 204760.0)],
        near_lots=[_lot("1120011500103330140", 204800.0, jimok="도로"), _lot("1120011500109990001", 210000.0)],  # 두 번째는 범위 밖
        origin=(204700.0, 549000.0), origin_reused=False, radius=500.0, shape="buffer", extent_ring=ring, scales=[3000],
        bounds=(203500.0, 548100.0, 206000.0, 549900.0), frame_bounds={3000: (203500.0, 548100.0, 206000.0, 549900.0)},
        buildings=[_bld(1, 204770.0, 3, "height", "A"), _bld(2, 204790.0, 15, "topo_flr", "B", apr=""),
                   _bld(3, 204810.0, 25, "grnd_flr~slope", "B"), _bld(4, 210000.0, 1, "default", "D")],   # 4번은 범위 밖
        features=[NS(theme="terrain", kind="contour", sheet="37705072", geometry={}), NS(theme="road", kind="surface", sheet="37705073", geometry={})],
        align_samples=[NS(feature_id=9, sheet="37705072", value=1.2, attrs={"dx": 0.3, "dy": -0.1},
                          geometry={"type": "Point", "coordinates": [204700.0, 549000.0]})],
        sources=[{"id": "lot", "name": "토지특성정보", "date": "2026-05-13", "age_months": 4.8, "level": "ok", "newer_date": None},
                 {"id": "building", "name": "GIS건물통합정보", "date": "2026-09-06", "age_months": 1.0, "level": "ok", "newer_date": None},
                 {"id": "terrain", "name": "수치지형도 1:5,000", "date": "2024~2026", "age_months": 33.0, "level": "warn", "newer_date": None},
                 {"id": "api", "name": "키", "date": "", "age_months": None, "level": "missing", "newer_date": None}],
        meta={"built_at": "2026-10-07T21:00:00"},
        stats={"align": {"median": 1.2, "p90": 3.9, "n": 1431, "low_sample": False, "dx": 0.36, "dy": 0.0}, "mismatch_count": 2},
        warnings=[{"level": "danger", "code": "stale_terrain", "text": "지형 자료 33.0개월 경과",
                   "detail": "⚠ 지형 자료가 33.0개월 지났습니다(수치지형도 1:5,000 2024~2026). 새 판 미확인", "action": None, "center": None}],
    )
    data.update(overrides)
    return NS(**data)


class MetaLinesTest(unittest.TestCase):
    def test_five_lines(self):
        lines = context_report.get_meta_lines(_prepared())
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("자료기준 — 필지 토지특성정보 2026-05-13 · 건물 GIS건물통합정보 2026-09-06"))
        self.assertIn("도시계획 서울시 UPIS —", lines[0])            # upis 원천 없음 → '—'
        self.assertIn("도엽 37705072 외 1, 2024~2026", lines[0])
        self.assertIn("생성 2026-10-07 · UrbanSite v%s" % constants.PANEL_VERSION, lines[0])
        self.assertEqual(lines[1], constants.META_SOURCE_LINE)
        self.assertEqual(lines[2], constants.META_CRS_LINE)
        self.assertEqual(lines[3], "정합 오차 중앙값 1.2 m, p90 3.9 m (n=1431, 도로경계 자동 비교) · 지적–지형 불일치 의심 2건(현장 확인 대상, 레이어 qa_mismatch)")
        self.assertTrue(lines[4].startswith("⚠ 지형 자료가 33.0개월"))

    def test_missing_values_are_dashes(self):
        lines = context_report.get_meta_lines(_prepared(sources=[], features=[], stats={}, warnings=[], meta={}))
        self.assertIn("필지 토지특성정보 —", lines[0])
        self.assertIn("도엽 —, —", lines[0])
        self.assertEqual(lines[3], "정합 오차 — (측정 없음)")
        self.assertEqual(lines[4], "기준일 경고 없음")

    def test_datasource_objects_map_by_source_id(self):
        sources = [NS(source_id="vworld_land_char", name="토지특성정보", reference_date="2026-05-13", license="제한 없음"),
                   NS(source_id="seoul_zoning", name="용도지역", reference_date="2026-02", license="1유형")]
        dates = context_report.get_source_dates(_prepared(sources=sources))
        self.assertEqual(dates, {"lot": "2026-05-13", "building": "—", "terrain": "—", "upis": "2026-02"})


class TablesTest(unittest.TestCase):
    def test_five_csv_headers_and_bom(self):
        with tempfile.TemporaryDirectory() as tmp:
            tables = context_report.write_tables(_prepared(), tmp, today=TODAY)
            self.assertEqual([t["name"] for t in tables], ["parcels.csv", "buildings.csv", "sheet_stats.csv", "height_src_stats.csv", "alignment.csv"])
            for table in tables:
                with open(table["path"], "rb") as f:
                    self.assertEqual(f.read(3), b"\xef\xbb\xbf", table["name"])
            rows = {t["name"]: _read_csv(t["path"]) for t in tables}
            self.assertEqual(tuple(rows["parcels.csv"][0].keys()), context_report.PARCEL_COLUMNS)
            self.assertEqual(tuple(rows["buildings.csv"][0].keys()), context_report.BUILDING_COLUMNS)
            self.assertEqual(tuple(rows["sheet_stats.csv"][0].keys()), context_report.SHEET_STAT_COLUMNS)
            self.assertEqual(tuple(rows["height_src_stats.csv"][0].keys()), context_report.HEIGHT_STAT_COLUMNS)
            self.assertEqual(tuple(rows["alignment.csv"][0].keys()), context_report.ALIGN_COLUMNS)
            # 범위 bbox 밖 필지·건물은 조서에서 빠진다
            self.assertEqual(len(rows["parcels.csv"]), 2)
            self.assertEqual(rows["parcels.csv"][0]["is_target"], "1")
            self.assertEqual([r["building_id"] for r in rows["buildings.csv"]], ["1", "2", "3"])
            self.assertEqual(rows["alignment.csv"][0]["dist_m"], "1.2")

    def test_parcel_zone_designation_columns(self):
        designations = [lot_db.DesignationInfo(constants.TEST_CONTEXT_PNU, "UQA330", "준공업지역", "포함"),   # 용도지역 열과 겹쳐 뺀다
                        lot_db.DesignationInfo(constants.TEST_CONTEXT_PNU, "UOA100", "교육환경보호구역", "저촉"),
                        lot_db.DesignationInfo(constants.TEST_CONTEXT_PNU, "UQQ310", "제1종지구단위계획구역", "접함")]
        with tempfile.TemporaryDirectory() as tmp:
            tables = context_report.write_tables(_prepared(designations=designations), tmp, today=TODAY)
            target, near = _read_csv(tables[0]["path"])
        self.assertEqual((target["legal_bcr"], target["legal_far"]), ("70", "150~400"))
        self.assertEqual(target["designations"], "교육환경보호구역(저촉)")
        self.assertEqual(near["designations"], "")
        self.assertEqual(target["area_gap_sqm"], "-1.0")
        self.assertTrue(target["eum_url"].endswith("pnu=%s&mode=search&isNoScr=script" % constants.TEST_CONTEXT_PNU))

    def test_sheet_stats_bands(self):
        with tempfile.TemporaryDirectory() as tmp:
            tables = context_report.write_tables(_prepared(), tmp, today=TODAY)
            rows = _read_csv(tables[2]["path"])
            floors = {r["category"]: r["count"] for r in rows if r["sheet_id"] == str(constants.SHEET_IDS["floor"])}
            self.assertEqual(floors, {"2~3": "1", "13~20": "1", "21+": "1"})
            ages = {r["category"]: r["count"] for r in rows if r["sheet_id"] == str(constants.SHEET_IDS["age"])}
            self.assertEqual(ages, {"30년 이상": "2", "연도 미상": "1"})
            jimok = {r["category"]: r["ratio"] for r in rows if r["sheet_id"] == str(constants.SHEET_IDS["land_category"])}
            self.assertEqual(jimok, {"대": "0.5", "도로": "0.5"})

    def test_height_src_strips_flags(self):
        stats = context_report.get_height_src_stats(_prepared())
        self.assertEqual(stats["n"], 3)
        self.assertEqual(set(stats["height_src"]), {"height", "topo_flr", "grnd_flr"})
        self.assertAlmostEqual(stats["height_grade"]["B"], 2 / 3.0, 3)


class ContextJsonTest(unittest.TestCase):
    def test_keys_and_partial_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = context_report.write_context_json(_prepared(), {"context": {"path": "x.3dm", "model_unit": "Millimeters"}}, tmp)
            self.assertEqual(os.path.basename(path), constants.CONTEXT_META_FILE_NAME)
            data = json.loads(_read_text(path))
            for key in ("tool", "version", "built_at", "lot_name", "pnus", "crs", "origin", "origin_reused", "radius", "shape",
                        "extent_ring", "bounds", "scales", "frame_bounds", "sheets", "sources", "dates", "align", "mismatch_count",
                        "height_src", "counts", "warnings", "meta_lines", "options", "context"):
                self.assertIn(key, data)
            self.assertEqual(data["origin"], [204700.0, 549000.0])
            self.assertEqual(data["frame_bounds"], {"3000": [203500.0, 548100.0, 206000.0, 549900.0]})
            self.assertEqual(data["counts"], {"buildings": 3, "lots": 2, "features": {"terrain": 1, "road": 1}, "align_samples": 1})
            self.assertEqual(data["dates"]["building"], "2026-09-06")
            self.assertEqual(data["meta_lines"], context_report.get_meta_lines(_prepared()))
            self.assertEqual(data["context"]["model_unit"], "Millimeters")

    def test_append_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.datetime(2026, 10, 7, 21, 30, 0)
            context_report.append_log(tmp, "첫 줄", now=now)
            path = context_report.append_log(tmp, ["둘", "셋\n"], now=now)
            text = _read_text(path)
            self.assertEqual(text.count("──── 2026-10-07 21:30:00"), 2)
            self.assertEqual(text.splitlines(), ["──── 2026-10-07 21:30:00", "첫 줄", "──── 2026-10-07 21:30:00", "둘", "셋"])


if __name__ == "__main__":
    unittest.main()
