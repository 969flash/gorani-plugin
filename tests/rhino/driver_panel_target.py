"""driver_panel_target — 실제 Rhino 패널(WebView)에서 대상지 줄을 본다 (python3 scripts/dev_rhino_run.py tests/rhino/driver_panel_target.py).

PR #57(2026-11-08) 패널 변경:
  ① 구역 — 라벨 '대상지', 이름에 동·지번(…구역), 같은 줄 끝에 [다시 그리기]·[옮기기]·[지우기] 아이콘(따로 단추 줄 없음)
  ② 3D 설정 — 체크박스 줄 높이 32 px(다른 줄 40 px)
  ③ 지도 단추(위성·확대) 바탕이 테마색(--surface) — 다크 모드에서 흰 바탕에 흰 글씨였다
  ④ 해외 위치(샌프란시스코) — 라벨 '대상지', 위경도 대신 주소(Nominatim reverse)
~/Gorani/data의 성동구 팩. 열린 Gorani 패널이 있으면 멈춘다. 사용자 prefs(~/.gorani/prefs.json)는 시작 때 내용을 두었다가 끝에 되돌린다.
화면은 찍지 않는다(macOS 화면 기록 권한). 결과: OUT_DIR/result.json.
"""
import json
import os
import runpy
import time

import Eto.Forms as forms
import Rhino
import scriptcontext

import data_pack
import usage_stats

REAL = os.path.join(os.path.expanduser("~"), "Gorani")
PREFS = os.path.join(os.path.expanduser("~"), ".gorani", "prefs.json")
AREA = [[127.0219, 37.5535], [127.0231, 37.5535], [127.0231, 37.5545], [127.0219, 37.5545]]   # 금호동3가 언저리 약 100 m
SF = [-122.4187, 37.8010]
data_pack.get_data_dir = lambda *a, **k: os.path.join(REAL, "data")
usage_stats.send_event = lambda *a, **k: False   # 시험이 실제 GA로 나가지 않게
prefs_before = open(PREFS, encoding="utf-8").read() if os.path.exists(PREFS) else None
res = {"checks": {}}

open_panels = [w for w in forms.Application.Instance.Windows if w.Title == "Gorani"]
assert not open_panels and scriptcontext.sticky.get("gorani_site_panel") is None, "열린 Gorani 패널이 있다 — 닫은 뒤 다시 실행"


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": str(detail)}
    print("%-30s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def js(host, code):
    return host.webview.ExecuteScript("return (function(){ " + code + " })();")


def wait_for(host, cond, timeout=20.0):
    end = time.time() + timeout
    while time.time() < end:
        Rhino.RhinoApp.Wait()
        if js(host, "return (%s) ? '1' : '0';" % cond) == "1":
            return True
        time.sleep(0.2)
    return False


runpy.run_path(os.path.join(JOB_DIR, "scripts", "cmd_site.py"), run_name="__main__")   # noqa: F821 — Gorani를 누른 것과 같다
host = scriptcontext.sticky.get("gorani_site_panel")
assert host is not None, "패널이 안 열렸다"
try:
    wait_for(host, "typeof state !== 'undefined' && !!document.getElementById('tray')", 30)
    js(host, "window.__errs = []; window.addEventListener('error', function (e) { window.__errs.push(String(e.message)); }); return 1;")

    # ① 구역
    js(host, "resetLots('area'); cancelDraw(); send({ cmd: 'set_area', ring_lnglat: %s }); return 1;" % json.dumps(AREA))
    ok = wait_for(host, "state.area && state.area.ok && document.querySelector('#tray [data-act=area_clear]')", 30)
    if not ok:
        print("진단", js(host, "return JSON.stringify({mode: state.mode, area: state.area ? {ok: state.area.ok, text: state.area.text, lots: state.area.lots, name: state.area.lot_name} : null, "
                              "region: state.options.region, tray: (document.getElementById('tray') || {}).textContent.slice(0, 200)});"))
    info = json.loads(js(host, "var row = document.querySelector('#tray [data-act=area_clear]').closest('.trow'); return JSON.stringify({"
                               "label: row.querySelector('.lbl').textContent, want: tr('대상지'), name: row.querySelector('.tval').textContent, "
                               "icons: ['draw_start', 'area_move', 'area_clear'].filter(function (a) { return row.querySelector('[data-act=' + a + ']'); }).length, "
                               "toolsRow: !!document.querySelector('#tray .tools [data-act=draw_start]'), oneLine: row.offsetHeight});") or "{}") if ok else {}
    check("구역 라벨 '대상지'", ok and info.get("label") == info.get("want"), info.get("label"))
    check("구역 이름에 동·지번", ok and ("구역" in info.get("name", "") or "area" in info.get("name", "").lower()), info.get("name"))
    check("구역 아이콘 셋이 같은 줄", ok and info.get("icons") == 3 and not info.get("toolsRow"), "icons %s · 단추 줄 %s · 줄 높이 %s" % (info.get("icons"), info.get("toolsRow"), info.get("oneLine")))

    # ② 체크박스 줄 높이
    js(host, "var d = document.getElementById('s3d'); if (d) d.open = true; return 1;")
    time.sleep(0.5)
    heights = json.loads(js(host, "return JSON.stringify(Array.prototype.map.call(document.querySelectorAll('#s3d .body > .trow'), function (r) {"
                                  " return [!!r.querySelector(':scope > label.chk'), r.offsetHeight]; }));") or "[]")
    chk = [h for c, h in heights if c]
    other = [h for c, h in heights if not c]
    check("체크박스 줄 32 px", chk and all(h <= 33 for h in chk) and other and min(other) >= 39, "체크 %s · 나머지 %s" % (chk, other))

    # ③ 지도 단추 바탕 = --surface
    colors = json.loads(js(host, "var b = document.getElementById('aerial_btn'), z = document.querySelector('.leaflet-control-zoom-in');"
                                 " var probe = document.createElement('div'); probe.style.background = 'var(--surface)'; document.body.appendChild(probe);"
                                 " var want = getComputedStyle(probe).backgroundColor; probe.remove();"
                                 " return JSON.stringify({aerial: b ? getComputedStyle(b).backgroundColor : '', zoom: z ? getComputedStyle(z).backgroundColor : '', want: want,"
                                 " dark: matchMedia('(prefers-color-scheme: dark)').matches});") or "{}")
    check("지도 단추 바탕 = 테마색", colors.get("zoom") == colors.get("want") and (not colors.get("aerial") or colors.get("aerial") == colors.get("want")),
          "%s · 다크 %s" % (colors.get("zoom"), colors.get("dark")))

    # ④ 해외 위치
    js(host, "ACTIONS.clear && ACTIONS.clear(); resetLots('point'); send({ cmd: 'set_point', center: %s }); return 1;" % json.dumps(SF))
    ok = wait_for(host, "state.point && state.point.center && state.point.center[0] < -100", 30)
    info = json.loads(js(host, "var row = document.querySelector('#tray .trow'); return JSON.stringify({address: state.point ? state.point.address : '', "
                               "lot_name: state.point ? state.point.lot_name : '', label: row ? row.querySelector('.lbl').textContent : '', want: tr('대상지'), "
                               "shown: row && row.querySelector('.tval') ? row.querySelector('.tval').textContent : ''});") or "{}") if ok else {}
    check("해외 위치 주소", ok and bool(info.get("address")) and "N37" not in info.get("shown", ""), "%s | 폴더 %s" % (info.get("shown"), info.get("lot_name")))
    check("위치 라벨 '대상지'", ok and info.get("label") == info.get("want"), info.get("label"))

    res["errors"] = json.loads(js(host, "return JSON.stringify(window.__errs || []);") or "[]")
    check("JS 오류 없음", not res["errors"], res["errors"])
finally:
    if os.environ.get("PANEL_KEEP") != "1":
        host.form.Close()
        scriptcontext.sticky.pop("gorani_site_panel", None)
    if prefs_before is None:
        if os.path.exists(PREFS):
            os.remove(PREFS)
    else:
        with open(PREFS, "w", encoding="utf-8") as f:
            f.write(prefs_before)   # 사용자 설정을 시작 때 그대로
    failed = [k for k, v in res["checks"].items() if not v["ok"]]
    res["failed"] = failed
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("%d개 중 실패 %d" % (len(res["checks"]), len(failed)))
assert not failed, failed
