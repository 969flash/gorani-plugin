#!/usr/bin/env python3
"""건물 높이·층수 신뢰도 실측 (Rhino 밖 python3 전용, geopandas 필요).

입력  data/raw/vworld_buildings/merged_5186.json, tile_*.json — VWorld 2D API LT_C_BLDGINFO 캐시(EPSG:5186 WKT)
      ../Seoungsu/data/raw/shp/<도엽>/N3A_B0010000.shp — 수치지형도 1:5000 건물(층수·종류·용도)
처리  두 자료의 실제 수집 범위가 겹치는 영역만 잘라 발자국 대표점 공간조인
      → (a) 매칭률 (b) grnd_flr vs 층수 (c) 용도별 층고 (d) 종류별 미매칭률 (e) 코드표 검증 (f) 높이 모델 비교
출력  markdown 표를 stdout으로. 결과는 docs/research/08_building_height_reliability.md 에 옮겨 적는다.
실행  /usr/bin/python3 scripts/probe_building_height.py
"""
import glob
import json
import os
import sys

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box, shape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VW_DIR = os.path.join(ROOT, "data", "raw", "vworld_buildings")
SHP_DIR = os.path.join(ROOT, "..", "Seoungsu", "data", "raw", "shp")
SHEETS = ["37705072", "37705073", "37705082", "37705083"]
EDGE = 30  # m. 수집 범위 경계에서 잘린 건물을 빼기 위한 안쪽 버퍼

# 건축물용도코드 대분류(앞 2자리). 출처: VWorld 국가중점데이터 컬럼정의서(26.08.19) '참조코드' 22번 건축물용도코드
# (단독주택 01000 … 장례시설 29000, 자원순환관련시설 30000 … 군사시설 33000). 상세는 08 문서 §3.
USABILITY = {
    "01": "단독주택", "02": "공동주택", "03": "제1종근린생활", "04": "제2종근린생활",
    "05": "문화및집회", "06": "종교", "07": "판매", "08": "운수", "09": "의료",
    "10": "교육연구", "11": "노유자", "12": "수련", "13": "운동", "14": "업무",
    "15": "숙박", "16": "위락", "17": "공장", "18": "창고", "19": "위험물저장처리",
    "20": "자동차관련", "21": "동물및식물", "22": "분뇨쓰레기처리", "23": "교정및군사",
    "24": "방송통신", "25": "발전", "26": "묘지관련", "27": "관광휴게", "28": "가설건축물", "29": "장례",
    "30": "자원순환", "31": "야영장", "32": "교정", "33": "군사",
}
BANDS = ([0, 2, 4, 6, 10, 20, 999], ["1-2", "3-4", "5-6", "7-10", "11-20", "21+"])


def md(df, fmt="{:.2f}"):
    # type: (pd.DataFrame, str) -> str
    """DataFrame → markdown 표(의존성 없이)."""
    cols = list(df.columns)
    out = ["| " + " | ".join(str(c) for c in cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join(fmt.format(v) if isinstance(v, (float, np.floating)) and not np.isnan(v) else str(v) for v in r) + " |")
    return "\n".join(out)


def load_vworld():
    # type: () -> (gpd.GeoDataFrame, object)
    """캐시 전체 GeoDataFrame과 타일별 수집 범위(건물 bbox 합집합)."""
    d = json.load(open(os.path.join(VW_DIR, "merged_5186.json")))
    df = pd.DataFrame([dict(bld_id=k, wkt=v["geom"], **v["props"]) for k, v in d.items()])
    for c in ("grnd_flr", "ugrnd_flr", "height", "archarea", "totalarea"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    major = df["usability"].str[:2].map(USABILITY)
    df["use_major"] = major.where(major.notna(), df["usability"].map(lambda u: "(결측)" if u == "" else "기타"))
    vw = gpd.GeoDataFrame(df.drop(columns="wkt"), geometry=gpd.GeoSeries.from_wkt(df["wkt"]), crs="EPSG:5186")
    boxes = []
    for f in glob.glob(os.path.join(VW_DIR, "tile_*.json")):
        t = json.load(open(f))
        feats = t.get("features") if isinstance(t, dict) else t  # 타일 파일은 GeoJSON Feature 리스트(EPSG:4326)
        geoms = [shape(x["geometry"]) for x in feats if x.get("geometry")]
        if geoms:
            boxes.append(box(*gpd.GeoSeries(geoms, crs="EPSG:4326").to_crs("EPSG:5186").total_bounds))
    return vw, gpd.GeoSeries(boxes, crs="EPSG:5186").union_all()


def load_topo():
    # type: () -> (gpd.GeoDataFrame, object)
    parts = []
    for s in SHEETS:
        g = gpd.read_file(os.path.join(SHP_DIR, s, "N3A_B0010000.shp"))
        g["sheet"] = s
        parts.append(g)
    t = pd.concat(parts, ignore_index=True)
    t = t[t.geometry.notna() & ~t.geometry.is_empty].copy()
    if t.crs is None or t.crs.to_epsg() != 5186:
        t = t.to_crs("EPSG:5186")
    t["층수"] = pd.to_numeric(t["층수"], errors="coerce").fillna(0).astype(int)
    cover = gpd.GeoSeries([box(*t[t.sheet == s].total_bounds) for s in SHEETS], crs="EPSG:5186").union_all()
    return t, cover


def rep(gdf):
    # type: (gpd.GeoDataFrame) -> gpd.GeoDataFrame
    g = gdf.copy()
    g["geometry"] = gdf.representative_point()
    return g


def band(s):
    return pd.cut(s, BANDS[0], labels=BANDS[1])


def main():
    (vw, vw_cover), (topo, topo_cover) = load_vworld(), load_topo()
    overlap = vw_cover.intersection(topo_cover).buffer(-EDGE)
    ob = gpd.GeoSeries([overlap], crs="EPSG:5186").to_crs(4326).total_bounds.round(4).tolist()
    print(f"- VWorld 캐시 범위 ∩ 수치지형도 4도엽 범위(안쪽 {EDGE} m 버퍼): {overlap.area/1e6:.2f} km², EPSG:4326 bbox {ob}")
    vw_in = rep(vw)[rep(vw).within(overlap)].copy()
    topo_in = topo[rep(topo).within(overlap)].copy()
    vw_poly_in = vw.loc[vw_in.index]
    print(f"- 겹침 영역 안 건물: LT_C_BLDGINFO {len(vw_in):,}동, 수치지형도 {len(topo_in):,}동 (수치지형도 4도엽 전체 {len(topo):,}동, 캐시 전체 {len(vw):,}동)")

    # A. VW 대표점 → 수치지형도 폴리곤 / B. 수치지형도 대표점 → VW 폴리곤
    a = gpd.sjoin(vw_in, topo_in[["층수", "종류", "용도", "geometry"]], how="left", predicate="within")
    a = a[~a.index.duplicated(keep="first")]
    a["matched"] = a["index_right"].notna()
    b = gpd.sjoin(rep(topo_in), vw_poly_in[["bld_id", "grnd_flr", "height", "geometry"]], how="left", predicate="within")
    b = b[~b.index.duplicated(keep="first")]
    b["matched"] = b["index_right"].notna()
    # 보조: 폴리곤 겹침 비율(대표점 방식의 기하 오프셋 민감도 확인)
    ov = gpd.overlay(vw_poly_in[["bld_id", "geometry"]], topo_in[["층수", "geometry"]], how="intersection", keep_geom_type=False)
    ov["ratio"] = ov.area / ov.bld_id.map(vw_poly_in.set_index("bld_id").area)
    best = ov.groupby("bld_id").ratio.max().reindex(vw_in.bld_id).fillna(0)

    print("\n## (a) 매칭률")
    print(f"- LT_C_BLDGINFO {len(vw_in):,}동 중 대표점이 수치지형도 건물 안에 드는 동: {a.matched.sum():,} ({a.matched.mean()*100:.1f}%)")
    print(f"  · 폴리곤 겹침으로 보면: 겹침 전무 {(best==0).mean()*100:.1f}%, 겹침비율 <0.5 {((best>0)&(best<0.5)).mean()*100:.1f}%, ≥0.5 {(best>=0.5).mean()*100:.1f}%")
    print(f"- 수치지형도 {len(topo_in):,}동 중 대표점이 LT_C_BLDGINFO 건물 안에 드는 동: {b.matched.sum():,} ({b.matched.mean()*100:.1f}%)")
    g0 = a[a.grnd_flr <= 0]
    print(f"- LT_C_BLDGINFO 층수 결측(grnd_flr≤0) {len(g0):,}동({len(g0)/len(a)*100:.1f}%) 중 수치지형도 층수를 받을 수 있는 동: {g0.matched.sum():,} ({g0.matched.mean()*100:.1f}%); "
          f"받은 층수 분포 1층 {(g0[g0.matched]['층수']==1).mean()*100:.0f}% / 2층 {(g0[g0.matched]['층수']==2).mean()*100:.0f}% / 3층+ {(g0[g0.matched]['층수']>=3).mean()*100:.0f}%; 종류 가건물·무벽건물 {g0[g0.matched]['종류'].isin(['가건물','무벽건물']).mean()*100:.1f}%")
    # 대장 속성이 엉뚱한 폴리곤에 붙은 경우의 탐지: 대장 건축면적(archarea)과 발자국 면적의 괴리 (전체 캐시)
    pa = vw[vw.archarea > 0].copy()
    pa["ratio"] = pa.archarea / pa.area
    print(f"- 전체 캐시 archarea>0 {len(pa):,}동: 대장 archarea < 발자국 면적×0.5 → {(pa.ratio < 0.5).mean()*100:.1f}%, > ×2 → {(pa.ratio > 2).mean()*100:.1f}% (0.5–2 안 {((pa.ratio >= 0.5) & (pa.ratio <= 2)).mean()*100:.1f}%)")
    h0 = a[a.height <= 0]
    print(f"- LT_C_BLDGINFO 높이 결측(height≤0) {len(h0):,}동({len(h0)/len(a)*100:.1f}%) 중 grnd_flr>0 {(h0.grnd_flr>0).mean()*100:.1f}%, 수치지형도 층수 매칭 {h0.matched.mean()*100:.1f}%, 둘 다 없음 {((h0.grnd_flr<=0)&~h0.matched).mean()*100:.1f}%")

    print("\n## (b) grnd_flr(>0) vs 수치지형도 층수 (매칭 동)")
    m = a[a.matched & (a.grnd_flr > 0) & (a["층수"] > 0)].copy()
    m["diff"] = (m.grnd_flr - m["층수"]).astype(int)
    m["bucket"] = pd.cut(m["diff"].abs(), [-1, 0, 1, 2, 9999], labels=["±0", "±1", "±2", "±3 이상"])
    dist = m.bucket.value_counts().sort_index()
    print(md(pd.DataFrame({"|grnd_flr−층수|": dist.index, "동수": dist.values, "비율%": (dist.values / len(m) * 100).round(1)}), "{:.1f}"))
    print(f"- n={len(m):,}; grnd_flr>층수 {(m['diff']>0).mean()*100:.1f}% / grnd_flr<층수 {(m['diff']<0).mean()*100:.1f}%; 평균차이 {m['diff'].mean():+.2f}")
    agg = dict(n=("diff", "size"), 일치율=("diff", lambda s: (s == 0).mean() * 100), 평균차이=("diff", "mean"), 중앙차이=("diff", "median"))
    print(md(m.groupby("종류").agg(**agg).reset_index().sort_values("n", ascending=False)))
    m["층수대"] = band(m["층수"])
    print(md(m.groupby("층수대", observed=True).agg(**agg).reset_index()))
    apt = m[m["종류"].isin(["아파트", "연립주택"]) & (m["층수"] >= 10)].copy()
    print(f"- 아파트·연립 10층 이상(n={len(apt)}): grnd_flr 상위값 {apt.grnd_flr.astype(int).value_counts().head(6).to_dict()}, bld_nm 비어있음 {(apt.bld_nm=='').mean()*100:.0f}%, dong_nm 비어있음 {(apt.dong_nm=='').mean()*100:.0f}%")
    apt_h = apt[apt.height > 0]
    if len(apt_h):
        print(f"  · 그중 height>0 n={len(apt_h)}: height/grnd_flr 중앙값 {(apt_h.height/apt_h.grnd_flr).median():.2f} vs height/층수 중앙값 {(apt_h.height/apt_h['층수']).median():.2f}")
    apt["vw_poly_area"] = vw_poly_in.loc[apt.index].area
    print("  · 사례(아파트, |차이|≥3, 상위 8) — archarea(대장)와 vw_poly_area(발자국 면적)가 다르면 폴리곤에 엉뚱한 대장이 붙은 것:")
    print(md(apt[apt["diff"].abs() >= 3][["bld_id", "bld_nm", "dong_nm", "grnd_flr", "층수", "height", "archarea", "vw_poly_area"]].head(8), "{:.1f}"))
    bad = apt[apt["diff"].abs() >= 3]
    print(f"  · |차이|≥3인 아파트·연립 {len(bad)}동 중 대장 archarea가 발자국 면적의 절반 미만: {(bad.archarea < 0.5 * bad.vw_poly_area).mean()*100:.0f}%")

    print("\n## (c) height/grnd_flr 층고 — usability 대분류별 (전체 캐시, height>0 & grnd_flr>0)")
    c = vw[(vw.height > 0) & (vw.grnd_flr > 0)].copy()
    c["fh"] = c.height / c.grnd_flr
    print(f"- n={len(c):,} (전체 {len(vw):,}동 중 {len(c)/len(vw)*100:.1f}%), 2–8 m 밖 {((c.fh<2)|(c.fh>8)).mean()*100:.1f}%, 전체 중앙값 {c.fh.median():.2f} / IQR {c.fh.quantile(.25):.2f}–{c.fh.quantile(.75):.2f}")
    cc = c.groupby("use_major").fh.agg(n="size", 중앙값="median", Q1=lambda s: s.quantile(.25), Q3=lambda s: s.quantile(.75), 밖=lambda s: ((s < 2) | (s > 8)).mean() * 100).reset_index().sort_values("n", ascending=False)
    print(md(cc[cc.n >= 30].rename(columns={"use_major": "용도 대분류", "밖": "2–8m 밖 %"})))
    c2 = c[(c.fh >= 2) & (c.fh <= 8)].copy()
    c2["층수대"] = band(c2.grnd_flr)
    print("\n층수대별 층고(전체 용도, 2–8 m 내)")
    print(md(c2.groupby("층수대", observed=True).fh.agg(n="size", 중앙값="median", Q1=lambda s: s.quantile(.25), Q3=lambda s: s.quantile(.75)).reset_index()))
    print("\n용도×층수대 중앙값 층고")
    pv = c2[c2.use_major.isin(["단독주택", "공동주택", "제1종근린생활", "제2종근린생활", "업무", "공장", "교육연구"])].pivot_table(index="use_major", columns="층수대", values="fh", aggfunc="median", observed=True).round(2)
    pv.index.name = "용도\\층수"
    print(md(pv.reset_index()))
    hm = a[a.matched & (a.height > 0) & (a["층수"] > 0)].copy()
    print(f"\n- 독립 검증: height>0 & 수치지형도 층수>0 n={len(hm):,}, height/층수 중앙값 {(hm.height/hm['층수']).median():.2f} (IQR {(hm.height/hm['층수']).quantile(.25):.2f}–{(hm.height/hm['층수']).quantile(.75):.2f})")

    print("\n## (d) 수치지형도 종류별 LT_C_BLDGINFO 미매칭률 (겹침 영역)")
    dd = b.groupby("종류").agg(n=("matched", "size"), 미매칭률=("matched", lambda s: (~s).mean() * 100), VW층수있음=("grnd_flr", lambda s: (s > 0).mean() * 100), VW높이있음=("height", lambda s: (s > 0).mean() * 100), 평균층수=("층수", "mean")).reset_index().sort_values("n", ascending=False)
    print(md(dd, "{:.1f}"))
    print(md(b.groupby("용도").agg(n=("matched", "size"), 미매칭률=("matched", lambda s: (~s).mean() * 100)).reset_index().sort_values("n", ascending=False).head(10), "{:.1f}"))

    print("\n## (e) usability 대분류 × 수치지형도 용도 교차표 (코드표 검증)")
    x = a[a.matched & (a.usability != "")]
    ct = pd.crosstab(x.use_major, x["용도"])
    ct = ct[ct.sum().sort_values(ascending=False).index[:8]]
    ct = ct.loc[ct.sum(axis=1).sort_values(ascending=False).index[:12]]
    ct.index.name = "usability\\용도"
    print(md(ct.reset_index(), "{:.0f}"))

    print("\n## (g) 사용승인 연대별 height 채움률과 층고 (전체 캐시)")
    vw["decade"] = pd.to_numeric(vw.useapr_day.str[:4], errors="coerce").floordiv(10).mul(10)
    gdec = vw[vw.decade.notna() & (vw.decade >= 1950)].copy()
    gdec["fh"] = np.where((gdec.height > 0) & (gdec.grnd_flr > 0), gdec.height / gdec.grnd_flr, np.nan)
    tab = gdec.groupby("decade").agg(n=("bld_id", "size"), height있음=("height", lambda s: (s > 0).mean() * 100), 층고중앙값=("fh", "median"),
                                   공동주택층고=("fh", lambda s: s[gdec.loc[s.index, "use_major"] == "공동주택"].median() if (gdec.loc[s.index, "use_major"] == "공동주택").any() else np.nan)).reset_index()
    tab["decade"] = tab.decade.astype(int).astype(str) + "s"
    print(f"- useapr_day 있음 {vw.decade.notna().mean()*100:.1f}%")
    print(md(tab))

    print("\n## (f) 높이 모델 비교 — height>0 & grnd_flr>0, 2–8 m 내 (n=%d)" % len(c2))
    rows = []
    for use, g in c2.groupby("use_major"):
        if len(g) < 100:
            continue
        slope, icpt = np.polyfit(g.grnd_flr, g.height, 1)
        fh_med = g.fh.median()
        rows.append({"용도": use, "n": len(g), "a+b·n: a": icpt, "b": slope,
                     "MAE 3.2n": (g.height - 3.2 * g.grnd_flr).abs().mean(),
                     "MAE med·n": (g.height - fh_med * g.grnd_flr).abs().mean(),
                     "MAE a+b·n": (g.height - (icpt + slope * g.grnd_flr)).abs().mean()})
    slope, icpt = np.polyfit(c2.grnd_flr, c2.height, 1)
    rows.append({"용도": "(전체)", "n": len(c2), "a+b·n: a": icpt, "b": slope,
                 "MAE 3.2n": (c2.height - 3.2 * c2.grnd_flr).abs().mean(),
                 "MAE med·n": (c2.height - c2.fh.median() * c2.grnd_flr).abs().mean(),
                 "MAE a+b·n": (c2.height - (icpt + slope * c2.grnd_flr)).abs().mean()})
    print(md(pd.DataFrame(rows).sort_values("n", ascending=False)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
