"""테스트 픽스처 DB 2개를 전체 DB에서 SQL로 추출한다 (Rhino 밖, sqlite3만).

    python3 scripts/dev_make_fixture.py --extent 203700,548000,205800,550100

성수동2가 333-139 중심 ±1.05 km. tests/fixtures/seongsu_context.db(buildings·features·data_sources·source_files)와
seongsu_site.db(parcels·overlays·parcel_overlays·parcel_land_use·data_sources, 스키마 v5). 합 ≈10 MB라 커밋한다.
"""
import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constants  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT_DIR / "tests" / "fixtures"
BBOX_WHERE = "min_x <= :max_x AND max_x >= :min_x AND min_y <= :max_y AND max_y >= :min_y"


def _copy_schema(source, target, names):
    rows = source.execute("SELECT type, name, sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'").fetchall()
    for kind, name, sql in rows:
        table = name if kind == "table" else sql.split(" ON ")[1].split("(")[0].strip() if " ON " in sql else ""
        if kind == "table" and name in names or kind == "index" and table in names:
            target.execute(sql)


def make(extent, context_src, site_src, out_dir=FIXTURE_DIR):
    out_dir.mkdir(parents=True, exist_ok=True)
    params = dict(zip(("min_x", "min_y", "max_x", "max_y"), extent))
    # 컨텍스트
    out = out_dir / "seongsu_context.db"
    out.unlink(missing_ok=True)
    src = sqlite3.connect(str(context_src))
    dst = sqlite3.connect(str(out))
    _copy_schema(src, dst, ("data_sources", "source_files", "buildings", "features"))
    dst.execute("PRAGMA user_version = %d" % constants.CONTEXT_DATABASE_SCHEMA_VERSION)
    dst.execute("ATTACH DATABASE ? AS full", (str(context_src),))
    dst.execute("INSERT INTO data_sources SELECT * FROM full.data_sources")
    dst.execute("INSERT INTO source_files SELECT * FROM full.source_files")
    dst.execute("INSERT INTO buildings SELECT * FROM full.buildings WHERE " + BBOX_WHERE, params)
    dst.execute("INSERT INTO features SELECT * FROM full.features WHERE " + BBOX_WHERE, params)
    dst.commit()
    counts = {t: dst.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in ("buildings", "features")}
    dst.execute("DETACH DATABASE full"); dst.execute("VACUUM"); dst.close(); src.close()
    print("context fixture:", out, "%.1f MB" % (out.stat().st_size / 1e6), counts)
    # 필지
    out = out_dir / "seongsu_site.db"
    out.unlink(missing_ok=True)
    src = sqlite3.connect(str(site_src))
    dst = sqlite3.connect(str(out))
    _copy_schema(src, dst, ("data_sources", "parcels", "overlays", "parcel_overlays", "parcel_land_use"))
    dst.execute("PRAGMA user_version = %d" % constants.DATABASE_SCHEMA_VERSION)
    dst.execute("ATTACH DATABASE ? AS full", (str(site_src),))
    dst.execute("INSERT INTO data_sources SELECT * FROM full.data_sources")
    dst.execute("INSERT INTO parcels SELECT * FROM full.parcels WHERE " + BBOX_WHERE, params)
    dst.execute("INSERT INTO overlays SELECT * FROM full.overlays WHERE " + BBOX_WHERE, params)
    dst.execute("INSERT INTO parcel_overlays SELECT l.* FROM full.parcel_overlays l WHERE l.pnu IN (SELECT pnu FROM parcels) AND l.overlay_id IN (SELECT overlay_id FROM overlays)")
    dst.execute("INSERT INTO parcel_land_use SELECT l.* FROM full.parcel_land_use l WHERE l.pnu IN (SELECT pnu FROM parcels)")
    dst.commit()
    counts = {t: dst.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0] for t in ("parcels", "overlays", "parcel_overlays", "parcel_land_use")}
    dst.execute("DETACH DATABASE full"); dst.execute("VACUUM"); dst.close(); src.close()
    print("site fixture:", out, "%.1f MB" % (out.stat().st_size / 1e6), counts)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--extent", default="203700,548000,205800,550100", help="min_x,min_y,max_x,max_y (EPSG:5186)")
    args = parser.parse_args()
    extent = [float(v) for v in args.extent.split(",")]
    make(extent, ROOT_DIR / constants.CONTEXT_DATABASE_PATH, ROOT_DIR / constants.DATABASE_PATH)


if __name__ == "__main__":
    main()
