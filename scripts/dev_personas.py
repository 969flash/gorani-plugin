"""가상 사용자 시험 — 설치본처럼 빈 HOME(~/Gorani, data·.env 없음)에서 패널 명령 순서 그대로(init → 대상지 → preflight → generate → make_2d).
SketchUp 사이드카 엔진 + 가짜 SketchUp(호스트 호출에 바로 답한다) — Rhino 없이 나라·언어·방식별 첫 실행을 끝까지 돌린다.
2026-10-23 OSM 'Access blocked' 사고 뒤 감사에서 만들었다(CLAUDE.md '배포 전 점검'). 공개 Overpass를 쓰므로 한 명씩, 사이를 둔다
(같은 IP에서 몰아 보내면 overpass-api.de가 IP를 막는다 — 2026-10-23 실제로 막혔다).

    python3 scripts/dev_personas.py                       # 전부 (약 40분) — 번들 파이썬은 build/sketchup/…/mac-arm64 (dev_deploy.py sketchup)
    python3 scripts/dev_personas.py jp_tokyo kr_seoul_fresh   # 골라서
결과: build/personas/<id>.json, 문제가 있으면 종료 코드 1.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
OUT_DIR = os.path.join(ROOT_DIR, "build", "personas")
BUNDLE_PYTHON = os.path.join(ROOT_DIR, "build", "sketchup", "bsh_gorani", "python", "mac-arm64", "bin", "python3.12")
GAP_SECONDS = 20   # 공개 Overpass에 몰아 보내지 않는다
# 나라·언어·방식·가장자리(날짜변경선·고위도·빈 땅·바다·국내 첫 실행·반경 2 km)
PERSONAS = [
    {"id": "ar_buenosaires", "lang": "es", "center": [-58.3816, -34.6037]},
    {"id": "fr_paris_area", "lang": "en", "ring": [[2.3470, 48.8540], [2.3500, 48.8540], [2.3500, 48.8558], [2.3470, 48.8558]], "radius": 400},
    {"id": "jp_tokyo", "lang": "ja", "center": [139.7016, 35.6580]},
    {"id": "nl_amsterdam", "lang": "en", "center": [4.8952, 52.3702]},
    {"id": "ch_zurich", "lang": "en", "center": [8.5417, 47.3769]},
    {"id": "us_nyc", "lang": "en", "center": [-73.9857, 40.7484], "radius": 500},
    {"id": "au_sydney", "lang": "en", "center": [151.2093, -33.8688]},
    {"id": "ke_nairobi", "lang": "en", "center": [36.8219, -1.2921]},
    {"id": "fj_suva", "lang": "en", "center": [178.4419, -18.1416]},
    {"id": "no_tromso", "lang": "en", "center": [18.9553, 69.6492]},
    {"id": "eg_cairo", "lang": "en", "center": [31.2357, 30.0444]},
    {"id": "cn_shanghai", "lang": "zh", "center": [121.4737, 31.2304]},
    {"id": "de_berlin", "lang": "en", "center": [13.4050, 52.5200]},
    {"id": "sahara_grid", "lang": "en", "center": [23.4, 25.0]},   # 원점 (0,0) 내림 — placement_mismatch(2026-10-23)
    {"id": "ocean_point", "lang": "en", "center": [-30.0, 0.0]},
    {"id": "kr_seoul_osm", "lang": "ko", "center": [127.0276, 37.4979]},
    {"id": "kr_seoul_fresh", "lang": "ko", "region": "kr", "download_bbox": [127.050, 37.540, 127.060, 37.548], "query": "성수동2가 277-17", "pick_search": True},
    {"id": "us_nyc_r2000", "lang": "en", "center": [-73.9857, 40.7484], "radius": 2000, "make_2d": False},
]


class FakeSketchUp(object):
    def __init__(self, controller):
        self.controller = controller
        self.attrs, self.items, self.pushed = {}, [], []
        controller.push = self.push

    def push(self, msg):
        if msg.get("type") != "host_call":
            self.pushed.append(msg)
            return
        method, args = msg["method"], msg["args"]
        if method == "get_model_attrs":
            result = [self.attrs.get(key) for key in args["keys"]]
        elif method == "set_model_attrs":
            self.attrs.update(args["values"]); result = True
        elif method == "clear":
            result = [0, 0]
        elif method == "bake":
            with open(args["path"], encoding="utf-8") as f:
                data = json.load(f)
            self.items += data["items"]; result = list(range(len(data["items"])))
        elif method == "ref":
            result = [1, 2]
        elif method == "save":
            with open(args["path"], "wb") as f:
                f.write(b"skp")
            result = len(self.items)
        elif method == "import":
            result = {"objects": 7, "layers": 5}
        else:
            result = True
        self.controller.replies.put({"cmd": "host_reply", "id": msg["id"], "ok": True, "result": result, "error": ""})


def main():
    # type: () -> int
    """골라 둔 가상 사용자를 한 명씩 번들 파이썬으로 돌리고 요약을 찍는다. 문제 수 합이 0이 아니면 1."""
    if not os.path.exists(BUNDLE_PYTHON):
        sys.exit("번들 파이썬이 없습니다 — python3 scripts/dev_deploy.py sketchup 먼저: %s" % BUNDLE_PYTHON)
    work = tempfile.mkdtemp(prefix="gorani_personas_")
    shutil.copytree(SCRIPTS_DIR, os.path.join(work, "pkg", "scripts"), ignore=shutil.ignore_patterns("__pycache__"))   # data/ 없는 설치본처럼
    os.makedirs(OUT_DIR, exist_ok=True)
    chosen = [p for p in PERSONAS if not sys.argv[1:] or p["id"] in sys.argv[1:]]
    total = 0
    for index, persona in enumerate(chosen):
        if index:
            time.sleep(GAP_SECONDS)
        home = os.path.join(work, "home", persona["id"])
        os.makedirs(home)
        env = dict(os.environ, HOME=home, USERPROFILE=home, PERSONA_PKG=os.path.join(work, "pkg", "scripts"), PERSONA_OUT=OUT_DIR)
        env.pop("VWORLD_API_KEY", None)
        result = subprocess.run([BUNDLE_PYTHON, os.path.abspath(__file__), "--one", json.dumps(persona)], env=env, capture_output=True, text=True)
        line = (result.stdout.strip().splitlines() or [result.stderr.strip()[-300:]])[-1]
        print(line, flush=True)
        try:
            total += len(json.load(open(os.path.join(OUT_DIR, persona["id"] + ".json"), encoding="utf-8"))["problems"])
        except (OSError, ValueError):
            total += 1
    print("문제 %d건 — 자세히는 %s/<id>.json" % (total, OUT_DIR))
    return 1 if total else 0


def run_one(persona):
    # type: (dict) -> None
    """한 명 — 번들 파이썬 안에서 돈다(PERSONA_PKG의 cmd_sketchup)."""
    pkg = os.environ["PERSONA_PKG"]
    out_path = os.path.join(os.environ["PERSONA_OUT"], "%s.json" % persona["id"])
    spec = importlib.util.spec_from_file_location("gorani_cmd_sketchup", os.path.join(pkg, "cmd_sketchup.py"))
    cmd_sketchup = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = cmd_sketchup
    spec.loader.exec_module(cmd_sketchup)
    pid = persona["id"]

    report = {"persona": persona, "steps": [], "problems": []}


    def step(name, msg):
        before = len(fake.pushed)
        t0 = time.time()
        try:
            controller.handle(msg)
        except Exception:
            report["problems"].append({"step": name, "kind": "exception", "detail": traceback.format_exc()[-1500:]})
        got = fake.pushed[before:]
        report["steps"].append({"step": name, "seconds": round(time.time() - t0, 1), "types": [m.get("type") for m in got]})
        for m in got:
            if m.get("type") == "error":
                report["problems"].append({"step": name, "kind": "error", "text": m.get("text"), "detail": (m.get("detail") or "")[-1500:]})
            elif m.get("type") == "log" and m.get("level") in ("error", "warn"):
                report["problems"].append({"step": name, "kind": "log_" + m["level"], "text": m.get("text")})
            elif m.get("type") == "progress" and m.get("state") in ("failed", "cancelled"):
                report["problems"].append({"step": name, "kind": "progress_" + m["state"], "text": json.dumps(m, ensure_ascii=False)[:1500]})
            elif m.get("type") == "data_progress" and m.get("done") and not m.get("ok"):
                report["problems"].append({"step": name, "kind": "data_failed", "text": m.get("text")})
        return got

    controller = cmd_sketchup._SketchUpController("persona")
    fake = FakeSketchUp(controller)
    lang = persona.get("lang", "en")
    region = persona.get("region", "global")
    try:
        init = step("init", {"cmd": "init", "lang": lang})
        state = next((m for m in init if m.get("type") == "init_state"), {})
        report["init"] = {k: state.get(k) for k in ("blocked", "warnings", "map", "tile", "version")}
        options = dict(state.get("options") or {})
        options.update({"region": region, "radius": persona.get("radius", 300), "shape": "rect", "make_basemap": False, "make_sheets": False,
                        "make_tables": False, "make_dwg": False, "import_after": True, "zoom_after_import": True, "include_minor_buildings": False,
                        "output_lang": persona.get("output_lang") or options.get("output_lang") or (lang if lang in ("ko", "en") else "en"), "lang": lang})   # 패널 detectOutputLang
        step("save_prefs", {"cmd": "save_prefs", "options": options})   # 패널은 첫 init 뒤 언어·결과 언어를 저장한다
        if persona.get("download_bbox"):   # 지도 칩 [받기] — 화면 지역 시군구 팩
            got = step("area_packs", {"cmd": "area_packs", "bbox": persona["download_bbox"], "seq": 1, "lang": lang})
            packs = next((m for m in got if m.get("type") == "area_packs"), {})
            report["area_packs"] = packs
            names = [p.get("name") for p in (packs.get("missing") or [])]
            if names:   # 이름 없이 보내면 전국을 받는다 — 패널도 늘 이름을 붙인다(site_ui.html 1179)
                step("download_data", {"cmd": "download_data", "names": names, "lang": lang})
        if persona.get("query"):
            got = step("search", {"cmd": "search", "query": persona["query"], "region": region, "lang": lang})
            report["search"] = [m for m in got if m.get("type") == "search_result"][:1]
            if persona.get("pick_search") and report["search"]:
                items = report["search"][0].get("matches") or []
                report["search_first"] = items[:1]
                if items and items[0].get("pnu"):
                    persona["pnus"] = [items[0]["pnu"]]
        if persona.get("ring"):
            got = step("set_area", {"cmd": "set_area", "ring_lnglat": persona["ring"], "region": region, "lang": lang})
            st = next((m for m in got if m.get("type") == "area_state"), {})
            target = {"mode": "area", "ring": st.get("ring_tm")}
            report["target_name"] = st.get("lot_name")
        elif persona.get("pnus") or persona.get("pick_search"):
            got = step("select_lots", {"cmd": "select_lots", "pnus": persona["pnus"], "lang": lang})
            target = {"mode": "lots", "pnus": persona["pnus"]}
        else:
            got = step("set_point", {"cmd": "set_point", "center": persona["center"], "region": region, "lang": lang})
            st = next((m for m in got if m.get("type") == "point_state"), {})
            target = {"mode": "point", "center": st.get("center_tm")}
            report["target_name"] = st.get("lot_name")
        step("preflight", {"cmd": "preflight", "target": target, "radius": options["radius"], "shape": "rect", "region": region, "seq": 1, "lang": lang})
        got = step("generate", {"cmd": "generate", "target": target, "options": options, "lang": lang})
        done = next((m for m in got if m.get("type") == "done"), None)
        report["done"] = done and {k: done.get(k) for k in ("dir", "lot_name", "counts", "warnings", "sources", "context")}
        if done and persona.get("make_2d", True):
            options2 = dict(options, make_basemap=True, make_sheets=True, make_tables=True, sheet_ids=list(range(0, 30)))
            got = step("make_2d", {"cmd": "make_2d", "dir": done["dir"], "options": options2, "lang": lang})
            made = next((m for m in got if m.get("type") == "made_2d"), None)
            report["made_2d"] = made and {k: made.get(k) for k in ("ok", "error", "folder", "sheets", "warnings", "files")}
        if done:
            files = []
            for root, _, names in os.walk(done["dir"]):
                for n in names:
                    p = os.path.join(root, n)
                    files.append([os.path.relpath(p, done["dir"]), os.path.getsize(p)])
            report["files"] = files
    except Exception:
        report["problems"].append({"step": "harness", "kind": "exception", "detail": traceback.format_exc()[-2000:]})
    report["skp_items"] = len(fake.items)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1, default=str)
    print(pid, "problems=%d" % len(report["problems"]), "done=%s" % bool(report.get("done")), "files=%d" % len(report.get("files") or []))


if __name__ == "__main__":
    if sys.argv[1:2] == ["--one"]:
        run_one(json.loads(sys.argv[2]))
    else:
        sys.exit(main())
