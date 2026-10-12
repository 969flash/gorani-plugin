#!/usr/bin/env python3
"""08 문서 검증 보강용 후속 실측 (probe_alignment.py 헬퍼 재사용).

A. 최대 수직오차 지점의 최근접 교량(A007)·입체교차부(A016)·도로중심선(A002) 명칭/거리
B. 지적→지형도 정합 오차의 도엽별 분해
C. '+10 m 구조물 규칙'을 실제로 구현해 5-fold 재측정 + 오탐/재현율 점검
D. 도엽 메타(제작·수정연도) 필드 유무 스캔

실행: /usr/bin/python3 scripts/probe_alignment_followup.py  → result/probe_alignment/followup.json
"""
import json, os, sys, time
import numpy as np, shapely, pyproj, pyogrio
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import cKDTree
from shapely import STRtree
from shapely.ops import unary_union

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import probe_alignment as P

t0 = time.time()
OUT = {}
def log(m=""): print(m, flush=True)

# ---------------------------------------------------------------- A. worst points
summary = json.load(open(os.path.join(P.OUT_DIR, "summary.json")))
worst = summary["A3_vertical"]["contour_plus_spot_no_struct"]["worst"] + summary["A3_vertical"]["contour_plus_spot"]["worst"]
seen, pts = set(), []
for w in worst:
    k = (w["x"], w["y"])
    if k not in seen:
        seen.add(k); pts.append(w)
bridge = P.read_tiles("N3A_A0070000"); ic9 = P.read_tiles("N3A_A0090000"); ic10 = P.read_tiles("N3A_A0100000"); rail16 = P.read_tiles("N3A_A0160024"); road = P.read_tiles("N3L_A0020000")
tr = pyproj.Transformer.from_crs(5186, 4326, always_xy=True)
def nearest(gdf, p, namecols):
    i = STRtree(gdf.geometry.values).nearest(p)
    g = gdf.iloc[i]
    return {c: (None if g[c] is None else str(g[c])) for c in namecols} | {"dist_m": round(float(shapely.distance(p, g.geometry)), 1)}
rows = []
for w in pts:
    p = shapely.points(w["x"], w["y"])
    lon, lat = tr.transform(w["x"], w["y"])
    r = {"x": w["x"], "y": w["y"], "lon": round(lon, 4), "lat": round(lat, 4), "z_spot": w["z_spot"], "z_tin": w["z_tin"],
         "bridge_A007": nearest(bridge, p, ["명칭", "종류"]), "grade_sep_A009": nearest(ic9, p, ["명칭", "구분"]), "interchange_A010": nearest(ic10, p, ["명칭"]), "rail_A016": nearest(rail16, p, ["UFID"]),
         "road_A002": nearest(road, p, ["명칭", "도로구분", "자동차전용"])}
    r["inside_struct_buffer_5m_A007_A009_A010"] = bool(min(r["bridge_A007"]["dist_m"], r["grade_sep_A009"]["dist_m"], r["interchange_A010"]["dist_m"]) <= 5)
    r["inside_old_buffer_A007_A016"] = bool(min(r["bridge_A007"]["dist_m"], r["rail_A016"]["dist_m"]) <= 5)
    rows.append(r)
    log(f"[A] ({r['lon']},{r['lat']}) z {r['z_spot']} vs {r['z_tin']} | 교량 {r['bridge_A007']['명칭']}/{r['bridge_A007']['종류']} {r['bridge_A007']['dist_m']} m | 입체교차부 {r['grade_sep_A009']['명칭']}/{r['grade_sep_A009']['구분']} {r['grade_sep_A009']['dist_m']} m | 인터체인지 {r['interchange_A010']['명칭']} {r['interchange_A010']['dist_m']} m | 도로 {r['road_A002']['명칭']}/{r['road_A002']['도로구분']}/{r['road_A002']['자동차전용']} {r['road_A002']['dist_m']} m | 정정 버퍼 안 {r['inside_struct_buffer_5m_A007_A009_A010']} / 구 버퍼(A007+A016) 안 {r['inside_old_buffer_A007_A016']}")
OUT["A_worst_points"] = rows
OUT["A_attr_values"] = {"자동차전용": sorted(set(map(str, road["자동차전용"].values))), "도로구분": sorted(set(map(str, road["도로구분"].values)))}
log(f"[A] 자동차전용 값 {OUT['A_attr_values']['자동차전용']} / 도로구분 {OUT['A_attr_values']['도로구분']}")

# ---------------------------------------------------------------- B. per-tile offset
roads_topo = P.read_tiles("N3A_A0010000")
boxes = P.tile_boxes(); bbox = unary_union(boxes)
seam = unary_union([b.boundary for b in boxes]).buffer(P.SEAM_BUFFER)
parcels = P.load_parcels(bbox.bounds)
parcels["geometry"] = shapely.intersection(parcels.geometry.values, bbox)
parcels = parcels[~parcels.geometry.is_empty]
road_cad = P.union_polygons(parcels[parcels.land_category == "도로"].geometry.values)
road_topo = P.union_polygons(roads_topo.geometry.values)
rng = np.random.default_rng(0)
p_all = P.sample_along(road_cad.boundary, P.SAMPLE_STEP)
if len(p_all) > 20000: p_all = p_all[rng.choice(len(p_all), 20000, replace=False)]
keep = ~shapely.intersects(shapely.points(p_all), seam); p_all = p_all[keep]
d, vec = P.nearest_dist(p_all, road_topo.boundary)
tile_of = np.full(len(p_all), "", dtype=object)
for t, b in zip(P.TILES, boxes):
    tile_of[shapely.contains_xy(b, p_all[:, 0], p_all[:, 1])] = t
per = {}
for t in P.TILES + ["ALL"]:
    m = (tile_of == t) if t != "ALL" else np.ones(len(d), bool)
    mm = m & (d <= 10)
    per[t] = {"n": int(m.sum()), "median_all": round(P.pct(d[m], 50), 2), "n_matched": int(mm.sum()), "median": round(P.pct(d[mm], 50), 2), "p90": round(P.pct(d[mm], 90), 2),
              "unmatched_share": round(float((~(d[m] <= 10)).mean()), 3), "dx": round(float(np.median(vec[mm, 0])), 2), "dy": round(float(np.median(vec[mm, 1])), 2),
              "le_2m": round(float((d[mm] <= 2).mean()), 3), "gt_3m_le_10m": round(float(((d[m] > 3) & (d[m] <= 10)).mean()), 3)}
    log(f"[B] {t}: n={per[t]['n']} 매칭 {per[t]['n_matched']} 중앙값 {per[t]['median']} p90 {per[t]['p90']} 비매칭 {per[t]['unmatched_share']:.1%} dx,dy ({per[t]['dx']},{per[t]['dy']}) 3~10 m {per[t]['gt_3m_le_10m']:.1%}")
OUT["B_per_tile_cad_to_topo"] = per

# ---------------------------------------------------------------- C. +10 m rule
cont = P.read_tiles("N3L_F0010000"); spot = P.read_tiles("N3P_F0020000"); bldg = P.read_tiles("N3A_B0010000")
seg = shapely.segmentize(cont.geometry.values, P.CONTOUR_RESAMPLE)
cxy = shapely.get_coordinates(seg); cz = np.repeat(cont["등고수치"].values.astype(float), shapely.get_num_coordinates(seg))
cpts = np.c_[cxy, cz]; _, k = np.unique(np.round(cpts[:, :2], 2), axis=0, return_index=True); cpts = cpts[np.sort(k)]
sxy = shapely.get_coordinates(spot.geometry.values); sz = spot["수치"].values.astype(float)
ok = np.isfinite(sz) & (sz > -5) & (sz < 300); spts = np.c_[sxy, sz][ok]
struct_geoms = np.concatenate([bridge.geometry.values, ic9.geometry.values, ic10.geometry.values])
struct_u = unary_union(struct_geoms).buffer(5)
old_u = unary_union(np.concatenate([bridge.geometry.values, rail16.geometry.values])).buffer(5)
on_old = shapely.intersects(shapely.points(spts[:, :2]), old_u)
on_struct = shapely.intersects(shapely.points(spts[:, :2]), struct_u)
tin_a = LinearNDInterpolator(cpts[:, :2], cpts[:, 2])
za_all = tin_a(spts[:, :2]); dz = spts[:, 2] - za_all
flag10 = np.isfinite(dz) & (dz >= 10)
# 설명 가능 여부: 자동차전용 도로중심선 15 m 이내 / 교량·입체교차 30 m 이내 / 건물 폴리곤 안
sp = shapely.points(spts[:, :2])
auto = road[road["자동차전용"].astype(str) == "자동차전용"]
auto_u = unary_union(auto.geometry.values).buffer(15) if len(auto) else None
near_auto = shapely.intersects(sp, auto_u) if auto_u is not None else np.zeros(len(sp), bool)
near_struct30 = shapely.intersects(sp, unary_union(struct_geoms).buffer(30))
in_bldg = np.zeros(len(sp), bool); in_bldg[np.unique(STRtree(bldg.geometry.values).query(sp, predicate="intersects")[0])] = True  # ponytail: 41k 건물 unary_union은 분 단위라 트리 질의로
explained = on_struct | near_auto | near_struct30
unexpl = flag10 & ~explained
rtree = STRtree(road.geometry.values)
unexpl_rows = []
for i in np.where(unexpl)[0]:
    j = rtree.nearest(sp[i]); g = road.iloc[j]
    lon, lat = tr.transform(spts[i, 0], spts[i, 1])
    unexpl_rows.append({"lon": round(lon, 4), "lat": round(lat, 4), "z_spot": float(spts[i, 2]), "z_tin_contour_only": round(float(za_all[i]), 1), "dz": round(float(dz[i]), 1),
                        "road": str(g["명칭"]), "road_kind": str(g["도로구분"]), "road_dist_m": round(float(shapely.distance(sp[i], g.geometry)), 1), "in_building": bool(in_bldg[i]),
                        "tile": str(spot.iloc[np.where(ok)[0][i]]["tile"])})
C = {"n_spot": int(len(spts)), "on_struct_5m_A007_A009_A010": int(on_struct.sum()), "on_old_A007_A016_5m": int(on_old.sum()), "old_only_rail_not_struct": int((on_old & ~on_struct).sum()), "struct_not_in_old": int((on_struct & ~on_old).sum()), "flag10_n": int(flag10.sum()), "flag10_share": round(float(flag10.mean()), 3),
     "flag10_and_on_struct": int((flag10 & on_struct).sum()), "recall_of_on_struct_by_flag10": round(float((flag10 & on_struct).sum() / on_struct.sum()), 3),
     "flag10_not_on_struct": int((flag10 & ~on_struct).sum()), "flag10_near_auto_road_15m": int((flag10 & near_auto).sum()), "flag10_not_on_struct_near_struct_30m": int((flag10 & ~on_struct & near_struct30).sum()), "flag10_not_on_struct_near_auto_15m": int((flag10 & ~on_struct & near_auto).sum()),
     "flag10_in_building": int((flag10 & in_bldg).sum()), "flag10_unexplained": int(unexpl.sum()), "unexplained_rows": unexpl_rows,
     "dz_distribution_flag10": {"min": round(float(dz[flag10].min()), 1), "median": round(float(np.median(dz[flag10])), 1), "max": round(float(dz[flag10].max()), 1)} if flag10.any() else None,
     "n_dz_5_to_10": int((np.isfinite(dz) & (dz >= 5) & (dz < 10)).sum())}
log(f"[C] 구조물 버퍼(A007+A009+A010) 안 {C['on_struct_5m_A007_A009_A010']} / 구 버퍼(A007+A016) 안 {C['on_old_A007_A016_5m']} (철도부지만 {C['old_only_rail_not_struct']}, 구 버퍼가 놓친 구조물 점 {C['struct_not_in_old']})")
log(f"[C] +10 m 플래그 {C['flag10_n']}/{C['n_spot']} ({C['flag10_share']:.1%}) | 구조물 버퍼 안 {C['on_struct_5m_A007_A009_A010']} 중 플래그 {C['flag10_and_on_struct']} (재현율 {C['recall_of_on_struct_by_flag10']:.1%}) | 버퍼 밖 플래그 {C['flag10_not_on_struct']} → 자동차전용 15 m {C['flag10_not_on_struct_near_auto_15m']} / 구조물 30 m {C['flag10_not_on_struct_near_struct_30m']} / 건물 안 {C['flag10_in_building']} / 미설명 {C['flag10_unexplained']}")
for r in unexpl_rows: log(f"     미설명: {r}")

# 규칙을 실제로 적용한 5-fold (같은 seed·fold)
excl = on_struct | flag10
rng = np.random.default_rng(0); folds = np.array_split(rng.permutation(len(spts)), 5)
e_rule, e_rule_alltest, e_ns, flat_l = [], [], [], []
d_contour = cKDTree(cpts[:, :2]).query(spts[:, :2])[0]; flat = d_contour >= P.FLAT_DIST
for test in folds:
    train = np.setdiff1d(np.arange(len(spts)), test)
    tr_r = train[~excl[train]]
    tin_r = LinearNDInterpolator(np.vstack([cpts[:, :2], spts[tr_r, :2]]), np.concatenate([cpts[:, 2], spts[tr_r, 2]]))
    e = tin_r(spts[test, :2]) - spts[test, 2]
    e_rule_alltest.append(e.copy()); e2 = e.copy(); e2[excl[test]] = np.nan; e_rule.append(e2); flat_l.append(flat[test])
flat_c = np.concatenate(flat_l)
def stats(e, m=None):
    v = np.isfinite(e) if m is None else (np.isfinite(e) & m); a = np.abs(e[v])
    return {"n": int(v.sum()), "rmse": round(float(np.sqrt((e[v] ** 2).mean())), 2), "median_abs": round(float(np.median(a)), 2), "p90_abs": round(P.pct(a, 90), 2), "max_abs": round(float(a.max()), 1),
            "share_gt_5m": round(float((a > 5).mean()), 3), "share_gt_10m": round(float((a > 10).mean()), 3), "rmse_excl_gt_10m": round(float(np.sqrt((e[v][a <= 10] ** 2).mean())), 2)}
er, ea = np.concatenate(e_rule), np.concatenate(e_rule_alltest)
C["cv_rule_applied"] = {"excluded_from_train_n": int(excl.sum()), "eval_excluding_excluded": {"all": stats(er), "flat": stats(er, flat_c), "slope": stats(er, ~flat_c)},
                        "eval_all_heldout_incl_excluded": {"all": stats(ea), "flat": stats(ea, flat_c), "slope": stats(ea, ~flat_c)}}
r1, r2 = C["cv_rule_applied"]["eval_excluding_excluded"]["all"], C["cv_rule_applied"]["eval_all_heldout_incl_excluded"]["all"]
log(f"[C] 규칙 적용 TIN 5-fold: 제외점 제외 평가 n={r1['n']} RMSE {r1['rmse']} 중앙값 {r1['median_abs']} p90 {r1['p90_abs']} 최대 {r1['max_abs']} >10 m {r1['share_gt_10m']:.1%} | 평지 {C['cv_rule_applied']['eval_excluding_excluded']['flat']} ")
log(f"[C] 규칙 적용 TIN 5-fold: 전체 hold-out 평가 n={r2['n']} RMSE {r2['rmse']} 중앙값 {r2['median_abs']} p90 {r2['p90_abs']} 최대 {r2['max_abs']} >10 m {r2['share_gt_10m']:.1%}")
OUT["C_rule_10m"] = C

# ---------------------------------------------------------------- D. metadata scan
D = {}
for t in P.TILES:
    hits = {}
    for f in sorted(os.listdir(os.path.join(P.SHP_DIR, t))):
        if f.endswith(".shp"):
            try:
                fields = list(pyogrio.read_info(os.path.join(P.SHP_DIR, t, f))["fields"])
            except Exception as ex:
                fields = [f"ERR {ex}"]
            dh = [c for c in fields if any(k in c for k in ("연도", "년도", "일자", "날짜", "DATE", "date", "수정", "제작"))]
            if dh: hits[f] = dh
    D[t] = {"n_shp": sum(f.endswith(".shp") for f in os.listdir(os.path.join(P.SHP_DIR, t))), "non_shp_files": [f for f in os.listdir(os.path.join(P.SHP_DIR, t)) if not f.split(".")[-1].lower() in ("shp", "shx", "dbf", "prj", "cpg", "sbn", "sbx")], "date_like_fields": hits}
    log(f"[D] {t}: shp {D[t]['n_shp']} 비-shp 파일 {D[t]['non_shp_files']} 날짜류 필드 {hits}")
OUT["D_metadata"] = D
json.dump(OUT, open(os.path.join(P.OUT_DIR, "followup.json"), "w"), ensure_ascii=False, indent=1)
log(f"완료 {time.time() - t0:.0f}s → {os.path.join(P.OUT_DIR, 'followup.json')}")
