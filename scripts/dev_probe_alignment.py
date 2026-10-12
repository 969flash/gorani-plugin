#!/usr/bin/env python3
"""지적(필지 DB)–수치지형도 정합 오차, UPIS 5174→5186 변환 경로, 지형 TIN 수직 정확도 실측.

docs/research/08_crs_precision_cadastre_alignment.md 의 로컬 실측 근거를 만드는 1회성 스크립트.
Rhino 밖 python3 전용(geopandas·shapely·scipy·pyproj).

실행: /usr/bin/python3 scripts/probe_alignment.py
출력: 표준출력(markdown 표) + result/probe_alignment/summary.json
입력:
  data/seoul_site.db                         필지(EPSG:5186)
  ../Seoungsu/data/raw/shp/3770507*/         수치지형도 1:5000 성수 4도엽(EPSG:5186)
  data/raw/seoul_zoning/2026-02/extracted/**/UPIS_C_UQ111.shp  서울 용도지역 원본(EPSG:5174)
"""
import glob
import json
import os
import sqlite3
import time

import geopandas as gpd
import numpy as np
import pyproj
import shapely
from pyproj.transformer import TransformerGroup
from scipy.interpolate import LinearNDInterpolator
from shapely import STRtree
from shapely.geometry import box
from shapely.ops import unary_union

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(ROOT, "data", "seoul_site.db")
SHP_DIR = os.path.join(ROOT, "..", "Seoungsu", "data", "raw", "shp")
TILES = ["37705072", "37705073", "37705082", "37705083"]
UPIS_GLOB = os.path.join(ROOT, "data", "raw", "seoul_zoning", "2026-02", "extracted", "*", "UPIS_C_UQ111.shp")
OUT_DIR = os.path.join(ROOT, "result", "probe_alignment")
SAMPLE_STEP = 10.0      # 경계선 샘플 간격 m
SEAM_BUFFER = 3.0       # 도엽 경계·bbox 경계 주변 제외 폭 m
CONTOUR_RESAMPLE = 4.0  # 07 §1.3 RESOLUTION
FLAT_DIST = 50.0        # 가장 가까운 등고선 정점까지 거리가 이 값 이상이면 '평지' 분류
LEGACY_TOWGS84 = "-115.80,474.99,674.11,1.16,-2.31,-1.63,6.43"  # 구 PROJ/QGIS 5174 정의에 들어 있던 7-parameter (출처는 08 문서 §2)

SUMMARY = {}


def log(msg=""):
    print(msg, flush=True)


def pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def dist_stats(d):
    d = np.asarray(d, dtype=float)
    return {
        "n": int(len(d)),
        "median": round(pct(d, 50), 3),
        "p90": round(pct(d, 90), 3),
        "mean": round(float(d.mean()), 3) if len(d) else None,
        "le_0.5m": round(float((d <= 0.5).mean()), 3) if len(d) else None,
        "le_1m": round(float((d <= 1.0).mean()), 3) if len(d) else None,
        "le_2m": round(float((d <= 2.0).mean()), 3) if len(d) else None,
        "le_5m": round(float((d <= 5.0).mean()), 3) if len(d) else None,
    }


def polygonal(geoms):
    """make_valid가 만든 GeometryCollection에서 면 부분만 남긴다(선·점 조각은 버림)."""
    out = []
    for g in geoms:
        if g.geom_type in ("Polygon", "MultiPolygon"):
            out.append(g)
        elif g.geom_type == "GeometryCollection":
            ps = [p for p in g.geoms if p.geom_type in ("Polygon", "MultiPolygon")]
            if ps:
                out.append(unary_union(ps))
    return out


def union_polygons(geoms):
    u = unary_union(polygonal(geoms))
    return unary_union(polygonal([u])) if u.geom_type == "GeometryCollection" else u


def read_tiles(layer):
    frames = []
    for t in TILES:
        path = os.path.join(SHP_DIR, t, layer + ".shp")
        if os.path.exists(path):  # 인터체인지(A0100000)처럼 일부 도엽에만 있는 레이어 허용
            f = gpd.read_file(path)
            f["tile"] = t
            frames.append(f)
    g = gpd.GeoDataFrame(gpd.pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    g["geometry"] = shapely.make_valid(g.geometry.values)
    return g


def tile_boxes():
    return [box(*gpd.read_file(os.path.join(SHP_DIR, t, "N3A_A0010000.shp")).total_bounds) for t in TILES]


def sample_along(lines, step):
    """MultiLineString/LineString 들을 step 간격으로 점 샘플. 반환 (N,2)"""
    parts = shapely.get_parts(lines)
    parts = parts[shapely.get_type_id(parts) == 1]  # LineString만
    pts = []
    for ln in parts:
        n = max(1, int(ln.length // step))
        pts.append(shapely.get_coordinates(shapely.line_interpolate_point(ln, np.linspace(0, ln.length, n + 1))))
    return np.vstack(pts) if pts else np.zeros((0, 2))


def nearest_dist(points_xy, target_lines, mask_geom=None):
    """점 → 선 집합 최근접 거리(m)와 최근접점 벡터(dx,dy). mask_geom 안의 점은 제외."""
    pts = shapely.points(points_xy)
    if mask_geom is not None:
        keep = ~shapely.intersects(pts, mask_geom)
        pts = pts[keep]
    parts = shapely.get_parts(target_lines)
    tree = STRtree(parts)
    idx = tree.nearest(pts)
    near = parts[idx]
    d = shapely.distance(pts, near)
    seg = shapely.shortest_line(pts, near)
    c = shapely.get_coordinates(seg).reshape(-1, 2, 2)
    vec = c[:, 1, :] - c[:, 0, :]
    return d, vec


def load_parcels(bounds):
    xmin, ymin, xmax, ymax = bounds
    con = sqlite3.connect(DB_PATH)
    rows = con.execute(
        "SELECT pnu, land_category, geometry_json FROM parcels "
        "WHERE max_x >= ? AND min_x <= ? AND max_y >= ? AND min_y <= ?",
        (xmin, xmax, ymin, ymax),
    ).fetchall()
    con.close()
    geoms = shapely.make_valid(shapely.from_geojson([r[2] for r in rows]))
    return gpd.GeoDataFrame({"pnu": [r[0] for r in rows], "land_category": [r[1] for r in rows]}, geometry=geoms, crs=5186)


# ---------------------------------------------------------------- A1 수평 정합
def probe_horizontal():
    t0 = time.time()
    roads_topo = read_tiles("N3A_A0010000")
    bldg = read_tiles("N3A_B0010000")
    boxes = tile_boxes()
    bbox = unary_union(boxes)
    bounds = bbox.bounds
    seam = unary_union([b.boundary for b in boxes]).buffer(SEAM_BUFFER)  # 도엽 경계·외곽

    parcels = load_parcels(bounds)
    parcels["geometry"] = shapely.intersection(parcels.geometry.values, bbox)
    parcels = parcels[~parcels.geometry.is_empty]
    road_cad = union_polygons(parcels[parcels.land_category == "도로"].geometry.values)
    road_topo = union_polygons(roads_topo.geometry.values)
    log(f"[A1] 필지 {len(parcels):,} (도로 {int((parcels.land_category == '도로').sum()):,}) / 지형도 도로경계면 {len(roads_topo):,} / 건물 {len(bldg):,} / 범위 {bbox.area / 1e6:.2f} km² ({time.time() - t0:.1f}s) / 합집합 타입 {road_cad.geom_type}·{road_topo.geom_type}")

    inter = road_cad.intersection(road_topo).area
    union = road_cad.union(road_topo).area
    a1 = {
        "area_km2": round(bbox.area / 1e6, 3),
        "road_cad_area_ha": round(road_cad.area / 1e4, 2),
        "road_topo_area_ha": round(road_topo.area / 1e4, 2),
        "iou": round(inter / union, 4),
        "cad_covered_by_topo": round(inter / road_cad.area, 4),
        "topo_covered_by_cad": round(inter / road_topo.area, 4),
    }
    log(f"[A1a] IoU={a1['iou']:.3f}  도로필지 중 지형도 도로면 안={a1['cad_covered_by_topo']:.3f}  지형도 도로면 중 도로필지 안={a1['topo_covered_by_cad']:.3f}")

    # (b) 경계선 간 최근접 거리 — 양방향
    cad_line = road_cad.boundary
    topo_line = road_topo.boundary
    rng = np.random.default_rng(0)
    res_b = {}
    for name, src, dst in (("cad→topo", cad_line, topo_line), ("topo→cad", topo_line, cad_line)):
        pts = sample_along(src, SAMPLE_STEP)
        if len(pts) > 20000:
            pts = pts[rng.choice(len(pts), 20000, replace=False)]
        d, vec = nearest_dist(pts, dst, mask_geom=seam)
        matched = d <= 10.0
        res_b[name] = {
            "all": dist_stats(d),
            "matched_le_10m": dist_stats(d[matched]),
            "unmatched_share_gt_10m": round(float((~matched).mean()), 3),
            "median_dx_dy_matched": [round(float(np.median(vec[matched, 0])), 3), round(float(np.median(vec[matched, 1])), 3)],
        }
        s = res_b[name]
        log(f"[A1b] {name}: n={s['all']['n']:,} 중앙값 {s['all']['median']} m / p90 {s['all']['p90']} m | ≤10 m 매칭분 중앙값 {s['matched_le_10m']['median']} / p90 {s['matched_le_10m']['p90']} (매칭 제외 {s['unmatched_share_gt_10m']:.1%}) | 체계 오프셋 중앙 dx,dy={s['median_dx_dy_matched']}")
    a1["boundary_distance"] = res_b

    # (c) 건물 발자국이 필지 경계를 넘는 비율
    b = bldg[~shapely.intersects(bldg.geometry.values, seam)].copy()  # 도엽 경계에 걸린 건물 제외
    b = b[b.geometry.area >= 10]
    tree = STRtree(parcels.geometry.values)
    pairs = tree.query(b.geometry.values, predicate="intersects")  # (2, M): [bldg_idx, parcel_idx]
    bg = b.geometry.values[pairs[0]]
    pg = parcels.geometry.values[pairs[1]]
    ia = shapely.area(shapely.intersection(bg, pg))
    is_road = (parcels.land_category.values[pairs[1]] == "도로")
    n = len(b)
    best = np.zeros(n)
    road_area = np.zeros(n)
    np.maximum.at(best, pairs[0], ia)
    np.add.at(road_area, pairs[0], np.where(is_road, ia, 0.0))
    barea = b.geometry.area.values
    overflow = 1.0 - best / barea
    road_share = road_area / barea
    a1["building_overflow"] = {
        "n": int(n),
        "overflow_vs_best_parcel": {
            "median": round(float(np.median(overflow)), 4),
            "p75": round(pct(overflow, 75), 4),
            "p90": round(pct(overflow, 90), 4),
            "share_le_1pct": round(float((overflow <= 0.01).mean()), 3),
            "share_le_5pct": round(float((overflow <= 0.05).mean()), 3),
            "share_le_10pct": round(float((overflow <= 0.10).mean()), 3),
            "share_gt_25pct": round(float((overflow > 0.25).mean()), 3),
        },
        "share_on_road_parcel": {
            "median": round(float(np.median(road_share)), 4),
            "p90": round(pct(road_share, 90), 4),
            "share_bldg_gt_5pct_on_road": round(float((road_share > 0.05).mean()), 3),
            "share_bldg_gt_20pct_on_road": round(float((road_share > 0.20).mean()), 3),
            "total_bldg_area_on_road_ha": round(float(road_area.sum() / 1e4), 2),
        },
    }
    # 종류별(아파트 등 대형 필지 건물은 여러 필지에 걸치는 게 정상이라 분리 표시)
    by_kind = {}
    for kind in ("일반주택", "주택외건물", "아파트", "연립"):
        m = (b["종류"].values == kind)
        if m.sum() > 50:
            by_kind[kind] = {"n": int(m.sum()), "overflow_median": round(float(np.median(overflow[m])), 4), "overflow_p90": round(pct(overflow[m], 90), 4), "road_share_gt_5pct": round(float((road_share[m] > 0.05).mean()), 3)}
    a1["building_overflow"]["by_kind"] = by_kind
    o = a1["building_overflow"]
    log(f"[A1c] 건물 n={n:,}: 최대겹침 필지 밖 면적비 중앙값 {o['overflow_vs_best_parcel']['median']:.1%} / p90 {o['overflow_vs_best_parcel']['p90']:.1%}, ≤5% 비율 {o['overflow_vs_best_parcel']['share_le_5pct']:.1%} | 도로필지 위 면적 >5%인 건물 {o['share_on_road_parcel']['share_bldg_gt_5pct_on_road']:.1%}, 도로 위 건물면적 합 {o['share_on_road_parcel']['total_bldg_area_on_road_ha']} ha")
    for k, v in by_kind.items():
        log(f"       {k}: n={v['n']:,} overflow 중앙값 {v['overflow_median']:.1%} p90 {v['overflow_p90']:.1%} 도로>5% {v['road_share_gt_5pct']:.1%}")
    SUMMARY["A1_horizontal"] = a1
    return parcels, bbox, seam


# ---------------------------------------------------------------- A2 UPIS 5174
def probe_upis(parcels, bbox, seam):
    path = glob.glob(UPIS_GLOB)[0]
    prj = open(path[:-4] + ".prj", encoding="utf-8", errors="replace").read()
    raw = gpd.read_file(path)
    a2 = {"prj": prj, "crs_detected": str(raw.crs), "crs_to_epsg": raw.crs.to_epsg() if raw.crs else None,
          "raw_bounds_5174": [round(v, 1) for v in raw.total_bounds], "n_features": int(len(raw))}
    log(f"[A2] UPIS_C_UQ111 .prj: {prj[:90]}…")
    log(f"[A2] pyproj 인식: {raw.crs.name if raw.crs else None} → to_epsg()={a2['crs_to_epsg']} | 원천 좌표 범위 {a2['raw_bounds_5174']}")

    tr = pyproj.Transformer.from_crs(5174, 5186, always_xy=True)
    tg = TransformerGroup(5174, 5186, always_xy=True)
    a2["pipeline"] = {"description": tr.description, "definition": tr.definition, "accuracy_m": tr.accuracy,
                      "uses_grid": any(k in tr.definition for k in ("hgridshift", "gridshift", ".gsb", ".tif", "grids=")),
                      "n_candidates": len(tg.transformers), "unavailable": [str(u) for u in tg.unavailable_operations],
                      "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str, "network": pyproj.network.is_network_enabled()}
    log(f"[A2] pyproj {pyproj.__version__} / PROJ {pyproj.proj_version_str}: {tr.description} | accuracy {tr.accuracy} m | grid 사용 {a2['pipeline']['uses_grid']} | 후보 {len(tg.transformers)}개")
    log(f"     {tr.definition}")

    # 변환 경로 민감도: EPSG 기본(5189 Molodensky-Badekas) vs 구 towgs84 7-parameter vs 5174를 2097로 오인
    crs_legacy = pyproj.CRS.from_proj4(f"+proj=tmerc +lat_0=38 +lon_0=127.002890277778 +k=1 +x_0=200000 +y_0=500000 +ellps=bessel +towgs84={LEGACY_TOWGS84} +units=m +no_defs")
    tr_legacy = pyproj.Transformer.from_crs(crs_legacy, 5186, always_xy=True)
    tr_2097 = pyproj.Transformer.from_crs(2097, 5186, always_xy=True)
    gx, gy = np.meshgrid(np.linspace(180000, 215000, 8), np.linspace(440000, 470000, 8))  # 서울 전역(5174 좌표)
    ex, ey = tr.transform(gx.ravel(), gy.ravel())
    lx, ly = tr_legacy.transform(gx.ravel(), gy.ravel())
    wx, wy = tr_2097.transform(gx.ravel(), gy.ravel())
    d_legacy = np.hypot(ex - lx, ey - ly)
    d_2097 = np.hypot(ex - wx, ey - wy)
    a2["sensitivity"] = {"legacy_towgs84_vs_epsg5189_m": {"min": round(float(d_legacy.min()), 3), "median": round(float(np.median(d_legacy)), 3), "max": round(float(d_legacy.max()), 3), "median_dx": round(float(np.median(lx - ex)), 3), "median_dy": round(float(np.median(ly - ey)), 3)},
                         "as_2097_instead_of_5174_m": {"median": round(float(np.median(d_2097)), 1), "max": round(float(d_2097.max()), 1), "median_dx": round(float(np.median(wx - ex)), 1), "median_dy": round(float(np.median(wy - ey)), 1)}}
    log(f"[A2] 구 towgs84 7-parameter 경로와의 차이(서울 격자): 중앙값 {a2['sensitivity']['legacy_towgs84_vs_epsg5189_m']['median']} m (최대 {a2['sensitivity']['legacy_towgs84_vs_epsg5189_m']['max']} m, dx {a2['sensitivity']['legacy_towgs84_vs_epsg5189_m']['median_dx']} dy {a2['sensitivity']['legacy_towgs84_vs_epsg5189_m']['median_dy']})")
    log(f"[A2] 5174를 2097(원점 127°00′00″)로 오인하면: 중앙값 {a2['sensitivity']['as_2097_instead_of_5174_m']['median']} m (dx {a2['sensitivity']['as_2097_instead_of_5174_m']['median_dx']} dy {a2['sensitivity']['as_2097_instead_of_5174_m']['median_dy']})")

    # 용도지역 경계 vs 5186 지적선 오프셋 (성수 4도엽)
    b74 = box(*tr.transform(*np.array(bbox.bounds)[[0, 1]], direction="INVERSE"), *tr.transform(*np.array(bbox.bounds)[[2, 3]], direction="INVERSE"))
    sub = raw[raw.intersects(b74)]
    parcel_lines = shapely.get_parts(shapely.boundary(np.array(polygonal(parcels.geometry.values), dtype=object)))  # ponytail: 합집합 없이 필지별 경계선 그대로(공유변 중복) — 최근접 거리에는 무방
    res = {}
    for name, t in (("epsg5189_default", tr), ("legacy_towgs84", tr_legacy)):
        g = sub.geometry.values
        xy = shapely.get_coordinates(g)
        x2, y2 = t.transform(xy[:, 0], xy[:, 1])
        g2 = shapely.set_coordinates(g.copy(), np.c_[x2, y2])
        g2 = shapely.intersection(shapely.make_valid(g2), bbox)
        lines = shapely.union_all(shapely.boundary(g2[~shapely.is_empty(g2)]))
        pts = sample_along(lines, SAMPLE_STEP)
        d, vec = nearest_dist(pts, parcel_lines, mask_geom=seam)
        m = d <= 5.0
        res[name] = {"all": dist_stats(d), "matched_le_5m": dist_stats(d[m]), "unmatched_share_gt_5m": round(float((~m).mean()), 3),
                     "median_dx_dy_matched": [round(float(np.median(vec[m, 0])), 3), round(float(np.median(vec[m, 1])), 3)]}
        s = res[name]
        log(f"[A2] 용도지역 경계→지적선 ({name}): n={s['all']['n']:,} 중앙값 {s['all']['median']} m p90 {s['all']['p90']} m | ≤5 m 매칭분 중앙값 {s['matched_le_5m']['median']} p90 {s['matched_le_5m']['p90']} (제외 {s['unmatched_share_gt_5m']:.1%}) | 중앙 dx,dy {s['median_dx_dy_matched']}")
    a2["zoning_vs_cadastre"] = res

    # DB overlays(필지 DB 구축 때 변환해 저장한 값)와 지금 변환한 값이 같은 경로인지 확인
    con = sqlite3.connect(DB_PATH)
    rows = con.execute("SELECT feature_id, geometry_json FROM overlays WHERE kind='용도지역' AND max_x >= ? AND min_x <= ? AND max_y >= ? AND min_y <= ?", bbox.bounds[0:1] + bbox.bounds[2:3] + bbox.bounds[1:2] + bbox.bounds[3:4]).fetchall()
    con.close()
    db = {fid: shapely.from_geojson(gj) for fid, gj in rows}
    idcol = [c for c in sub.columns if c.upper() in ("UFID", "ID", "FID")] or [sub.columns[0]]
    diffs = []
    for fid, g in zip(sub[idcol[0]].values, sub.geometry.values):
        if fid in db:
            xy = shapely.get_coordinates(g)
            x2, y2 = tr.transform(xy[:, 0], xy[:, 1])
            xy_db = shapely.get_coordinates(db[fid])
            if len(xy_db) == len(xy):
                diffs.append(float(np.abs(np.c_[x2, y2] - xy_db).max()))
    a2["db_overlays_same_pipeline"] = {"n_compared": len(diffs), "max_abs_coord_diff_m": round(max(diffs), 6) if diffs else None, "id_column": idcol[0]}
    log(f"[A2] DB overlays와 재변환 좌표 최대 차이: {a2['db_overlays_same_pipeline']}")
    SUMMARY["A2_upis_5174"] = a2


# ---------------------------------------------------------------- A3 수직 정확도
def probe_vertical():
    cont = read_tiles("N3L_F0010000")
    spot = read_tiles("N3P_F0020000")
    boxes = dict(zip(TILES, tile_boxes()))
    dens = {}
    for t in TILES:
        a = boxes[t].area / 1e6
        c = cont[cont.tile == t]
        s = spot[spot.tile == t]
        dens[t] = {"area_km2": round(a, 2), "contour_n": int(len(c)), "contour_km": round(float(c.length.sum() / 1000), 1),
                   "contour_km_per_km2": round(float(c.length.sum() / 1000 / a), 1), "spot_n": int(len(s)), "spot_per_km2": round(len(s) / a, 1),
                   "contour_z_min_max": [float(c["등고수치"].min()) if len(c) else None, float(c["등고수치"].max()) if len(c) else None],
                   "spot_z_min_max": [float(s["수치"].min()), float(s["수치"].max())]}
    log("[A3] 도엽별 밀도: " + json.dumps(dens, ensure_ascii=False))

    seg = shapely.segmentize(cont.geometry.values, CONTOUR_RESAMPLE)
    cxy = shapely.get_coordinates(seg)
    cz = np.repeat(cont["등고수치"].values.astype(float), shapely.get_num_coordinates(seg))
    cpts = np.c_[cxy, cz]
    _, keep = np.unique(np.round(cpts[:, :2], 2), axis=0, return_index=True)
    cpts = cpts[np.sort(keep)]
    sxy = shapely.get_coordinates(spot.geometry.values)
    sz = spot["수치"].values.astype(float)
    ok = np.isfinite(sz) & (sz > -5) & (sz < 300)
    spts = np.c_[sxy, sz][ok]
    log(f"[A3] 등고선 점 {len(cpts):,} (4 m 리샘플·중복 제거), 표고점 {len(spts):,}")

    from scipy.spatial import cKDTree
    d_contour = cKDTree(cpts[:, :2]).query(spts[:, :2])[0]
    flat = d_contour >= FLAT_DIST
    # 교량(A007)·입체교차부(A009 고가차도/지하차도)·인터체인지(A010) 위 표고점 = 상판 높이라 지표 TIN에 넣으면 안 됨 → 제외 변형도 비교
    # 2026-10-07 정정: 이전 판은 N3A_A0160024(철도경계·철도부지선)를 입체교차부로 오인해 사용 — 표준코드표(docs/reference/수치지형도_지형지물_표준코드.csv) 기준 입체교차부는 A0090000
    STRUCT_LAYERS = ("N3A_A0070000", "N3A_A0090000", "N3A_A0100000")
    structs = [read_tiles(l).geometry.values for l in STRUCT_LAYERS if any(os.path.exists(os.path.join(SHP_DIR, t, l + ".shp")) for t in TILES)]
    on_struct = shapely.intersects(shapely.points(spts[:, :2]), shapely.union_all(np.concatenate(structs)).buffer(5)) if structs else np.zeros(len(spts), bool)
    rng = np.random.default_rng(0)
    folds = np.array_split(rng.permutation(len(spts)), 5)
    tin_a = LinearNDInterpolator(cpts[:, :2], cpts[:, 2])
    err = {"contour_only": [], "contour_plus_spot": [], "contour_plus_spot_no_struct": []}
    is_flat = []
    for k, test in enumerate(folds):
        train = np.setdiff1d(np.arange(len(spts)), test)
        tin_b = LinearNDInterpolator(np.vstack([cpts[:, :2], spts[train, :2]]), np.concatenate([cpts[:, 2], spts[train, 2]]))
        tr_c = train[~on_struct[train]]
        tin_c = LinearNDInterpolator(np.vstack([cpts[:, :2], spts[tr_c, :2]]), np.concatenate([cpts[:, 2], spts[tr_c, 2]]))
        za = tin_a(spts[test, :2])
        zb = tin_b(spts[test, :2])
        zc = tin_c(spts[test, :2])
        err["contour_only"].append(za - spts[test, 2])
        err["contour_plus_spot"].append(zb - spts[test, 2])
        ec = zc - spts[test, 2]
        ec[on_struct[test]] = np.nan  # 구조물 위 표고점은 평가에서도 제외
        err["contour_plus_spot_no_struct"].append(ec)
        is_flat.append(flat[test])
    is_flat = np.concatenate(is_flat)
    order = np.concatenate(folds)  # 오차 배열과 같은 순서의 표고점 인덱스
    log(f"[A3] 교량(A007)·입체교차부(A009)·인터체인지(A010) 5 m 버퍼 위 표고점 {int(on_struct.sum())}개 / {len(spts)} — 'no_struct' 변형은 이를 학습·평가 모두에서 제외")
    a3 = {"density": dens, "n_contour_pts": int(len(cpts)), "n_spot": int(len(spts)), "flat_threshold_m": FLAT_DIST, "flat_share": round(float(is_flat.mean()), 3), "folds": 5}
    for name, es in err.items():
        e = np.concatenate(es)
        valid = np.isfinite(e)
        rows = {}
        for cls, m in (("all", valid), ("flat", valid & is_flat), ("slope", valid & ~is_flat)):
            ae = np.abs(e[m])
            rows[cls] = {"n": int(m.sum()), "rmse": round(float(np.sqrt((e[m] ** 2).mean())), 2), "median_abs": round(float(np.median(ae)), 2),
                         "p90_abs": round(pct(ae, 90), 2), "max_abs": round(float(ae.max()), 2), "bias_mean": round(float(e[m].mean()), 2),
                         "share_gt_2m": round(float((ae > 2).mean()), 3), "share_gt_5m": round(float((ae > 5).mean()), 3), "share_gt_10m": round(float((ae > 10).mean()), 3),
                         "rmse_excl_gt_10m": round(float(np.sqrt((e[m][ae <= 10] ** 2).mean())), 2)}
        rows["outside_hull_n"] = int((~valid).sum())
        worst = np.argsort(-np.abs(np.where(valid, e, 0)))[:8]
        rows["worst"] = [{"x": round(float(spts[order[i], 0]), 1), "y": round(float(spts[order[i], 1]), 1), "z_spot": float(spts[order[i], 2]), "z_tin": round(float(spts[order[i], 2] + e[i]), 1), "dist_to_contour_m": round(float(d_contour[order[i]]), 1)} for i in worst]
        a3[name] = rows
        log(f"[A3] {name}: 전체 RMSE {rows['all']['rmse']} m (중앙값 {rows['all']['median_abs']}, p90 {rows['all']['p90_abs']}, 최대 {rows['all']['max_abs']}, 편향 {rows['all']['bias_mean']}; |e|>5 m {rows['all']['share_gt_5m']:.1%}, >10 m {rows['all']['share_gt_10m']:.1%}, 10 m 초과 제외 RMSE {rows['all']['rmse_excl_gt_10m']}) | 평지 n={rows['flat']['n']} RMSE {rows['flat']['rmse']} 중앙값 {rows['flat']['median_abs']} p90 {rows['flat']['p90_abs']} | 경사지 n={rows['slope']['n']} RMSE {rows['slope']['rmse']} 중앙값 {rows['slope']['median_abs']} p90 {rows['slope']['p90_abs']}")
        log(f"       최대 오차 지점: {rows['worst'][:5]}")
    # 등고선만 TIN에서 '평평한 삼각형'(세 꼭짓점 Z 동일) 비율
    tri = tin_a.tri
    tz = cpts[tri.simplices, 2]
    flat_tri = (tz.max(axis=1) == tz.min(axis=1))
    a3["contour_only_flat_triangle_share"] = round(float(flat_tri.mean()), 3)
    log(f"[A3] 등고선만 TIN의 평평한 삼각형 비율 {flat_tri.mean():.1%} (면 {len(tz):,})")
    SUMMARY["A3_vertical"] = a3


if __name__ == "__main__":
    t0 = time.time()
    parcels, bbox, seam = probe_horizontal()
    probe_upis(parcels, bbox, seam)
    probe_vertical()
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(SUMMARY, f, ensure_ascii=False, indent=1)
    log(f"완료 {time.time() - t0:.0f}s → {os.path.join(OUT_DIR, 'summary.json')}")
