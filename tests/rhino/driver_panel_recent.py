"""driver_panel_recent — 실제 Rhino 패널(WebView)에서 '최근 결과'를 사용자처럼 눌러 본다 (python3 scripts/dev_rhino_run.py tests/rhino/driver_panel_recent.py).

임시 홈(OUT_DIR/home)에 결과 둘을 만든다 — 사용자 ~/Gorani/result는 건드리지 않는다:
  A) 금호동3가 450 외 1 → 2D를 두 번(표준·선명, made_2d.json) → 결과 폴더·2D 폴더 이름을 바꿔 둔다
  B) A의 사본에서 made_2d.json을 지운 것 — 이 기능 전에 만든 결과
패널을 열고(Gorani를 누른 것과 같다) DOM 클릭으로 ① 목록 ② 결과 열기(제목·2D 선택) ③ 선택 바꾸기 ④ [‹ 지도로](대상지 복원·[결과로 돌아가기])
⑤ 돌아가기 ⑥ 옛 결과를 확인하고 JS 오류(window.__errs)가 없어야 한다. 끝나면 패널을 닫는다(PANEL_KEEP=1이면 열어 둔다).
화면은 찍지 않는다 — Rhino 프로세스에서 screencapture를 부르면 macOS가 'Rhino 8' 화면 기록 권한을 묻는다(2026-11-07).
이 시험은 사용자 prefs(~/.gorani/prefs.json)를 쓴다(패널이 옵션을 저장) — 없던 파일이면 끝에 지운다.
"""
import json
import os
import runpy
import shutil
import time

import Eto.Forms as forms
import Rhino
import scriptcontext

import constants
import context_baker
import context_builder
import data_pack
import usage_stats

REAL = os.path.join(os.path.expanduser("~"), "Gorani")
PREFS = os.path.join(os.path.expanduser("~"), ".gorani", "prefs.json")
HOME_TMP = os.path.join(OUT_DIR, "home")   # noqa: F821 — dev_rhino_run 머리말 전역
PNUS = ["1120011100104500000", "1120011100104490000"]   # 금호동3가 450 외 1
had_prefs = os.path.exists(PREFS)
constants.HOME_DIR = HOME_TMP
data_pack.get_data_dir = lambda *a, **k: os.path.join(REAL, "data")
usage_stats.send_event = lambda *a, **k: False   # 시험이 실제 GA로 나가지 않게
res = {"checks": {}, "errors": []}

# 사용자가 열어 둔 Gorani 패널이 있으면 건드리지 않고 멈춘다 — 시험이 그 패널에 붙어 닫고 prefs까지 지울 뻔했다(2026-11-07)
open_panels = [w for w in forms.Application.Instance.Windows if w.Title == "Gorani"]
assert not open_panels and scriptcontext.sticky.get("gorani_site_panel") is None, "열린 Gorani 패널이 있다 — 닫은 뒤 다시 실행(이 시험은 열려 있는 패널에 손대지 않는다)"


def check(name, ok, detail=""):
    res["checks"][name] = {"ok": bool(ok), "detail": str(detail)}
    print("%-28s %s %s" % (name, "PASS" if ok else "FAIL", detail))


def pump(seconds):
    end = time.time() + seconds
    while time.time() < end:
        Rhino.RhinoApp.Wait()
        time.sleep(0.05)


def wait_for(host, cond, timeout=20.0):
    """JS 조건(return 식)이 참이 될 때까지 펌프하며 기다린다 — 고정 대기는 느린 날 틀렸다(2026-11-07: 대상지 정보가 5 s 넘게 걸렸다)."""
    end = time.time() + timeout
    while time.time() < end:
        Rhino.RhinoApp.Wait()
        if js(host, "return (%s) ? '1' : '0';" % cond) == "1":
            return True
        time.sleep(0.2)
    return False


def js(host, code):
    return host.webview.ExecuteScript("return (function(){ " + code + " })();")


# ── 결과 둘 만들기 ──
root = os.path.join(HOME_TMP, "result")
doc = Rhino.RhinoDoc.CreateHeadless(None)
doc.ModelUnitSystem = Rhino.UnitSystem.Millimeters
lot_key = context_baker.get_lot_key(PNUS)
response = context_builder.run({"target": {"mode": "lots", "pnus": PNUS}, "result_root": root,
                                "options": {"radius": 250, "shape": "rect", "output_lang": "ko", "make_basemap": False, "make_sheets": False, "make_tables": False}},
                               lambda *a: True, doc)
context_baker.clear_previous(doc, lot_key)
assert response["ok"], response.get("error")
result_a = response["dir"]
for preset in ("std", "vivid"):
    two = context_builder.make_2d(result_a, {"make_sheets": True, "sheet_ids": [9], "output_lang": "ko", "style": {"preset": preset}}, lambda *a: True)
    assert two["ok"], two.get("error")
    time.sleep(1.1)   # 2D 폴더 수정 시각 순서
legacy = os.path.join(root, "옛결과_금호동")
shutil.copytree(result_a, legacy)
for name in os.listdir(legacy):
    path = os.path.join(legacy, name, constants.MADE_2D_FILE_NAME)
    if os.path.exists(path):
        os.remove(path)   # 이 기능 전에 만든 2D — 카드 없이 폴더만
for name in sorted(os.listdir(legacy)):   # 2D 폴더는 하나만 남긴다
    if name.startswith("2D_") and name != sorted(n for n in os.listdir(legacy) if n.startswith("2D_"))[0]:
        shutil.rmtree(os.path.join(legacy, name))
renamed = os.path.join(root, "내가_바꾼_이름")
os.rename(result_a, renamed)
os.utime(renamed, None)
meta = os.path.join(renamed, "context.json")
os.utime(meta, None)   # 목록 맨 위 = A

# ── 패널 ──
runpy.run_path(os.path.join(JOB_DIR, "scripts", "cmd_site.py"), run_name="__main__")   # noqa: F821 — Gorani를 누른 것과 같다
host = scriptcontext.sticky.get("gorani_site_panel")
assert host is not None, "패널이 안 열렸다"
try:
    pump(9)   # WebView 로드 + init
    js(host, "window.__errs = []; window.addEventListener('error', function (e) { window.__errs.push(String(e.message)); }); return 1;")
    check("목록 2개", js(host, "return document.querySelectorAll('.recent-row').length;") == "2", js(host, "return document.querySelectorAll('.recent-row').length;"))

    js(host, "document.querySelector('[data-act=recent][data-i=\"0\"]').click(); return 1;")
    wait_for(host, "state.screen === 'result' && document.getElementById('pick2d')")
    info = js(host, "return state.screen + '|' + document.getElementById('doc_title').textContent + '|' + (document.getElementById('pick2d') ? document.getElementById('pick2d').options.length : 0);")
    check("결과 열기·제목·2D 선택", info == "result|3D 모델 생성 완료|2", info)

    first = js(host, "var s = document.getElementById('pick2d'); return s ? s.options[0].text : '';")
    js(host, "var s = document.getElementById('pick2d'); s.selectedIndex = s.options.length - 1; s.dispatchEvent(new Event('change', {bubbles: true})); return 1;")
    pump(1.5)
    second = js(host, "var s = document.getElementById('pick2d'); return s ? s.options[s.selectedIndex].text : '';")
    check("선택 바꾸면 카드 바뀜", first != second and "표준" in second and "선명" in first, "%s → %s" % (first, second))
    check("도면 카드 있음", js(host, "return document.querySelectorAll('#card2d .cell, #card2d [data-act=sheet_view]').length > 0 ? '1' : '0';") == "1")

    js(host, "document.querySelector('[data-act=rerange]').click(); return 1;")
    wait_for(host, "state.screen === 'map' && state.lots.length === 2")
    info = js(host, "return state.screen + '|' + state.lots.length + '|' + !!document.querySelector('[data-act=to_result]');")
    if info != "map|2|true":   # 진단 — 어느 단계에서 비었나
        print("진단", js(host, "return JSON.stringify({mode: state.mode, lots: state.lots, draw: draw.on, stamp: stamp.on, last: !!state.last, lastRestored: !!(state.last && state.last.restored), "
                              "restoredTarget: state.last && state.last.restored ? state.last.restored.target : null, errs: window.__errs, "
                              "lotState: state.lotState ? state.lotState.lots.length : null, tray: (document.getElementById('tray_err') || {}).textContent || ''});"))
    check("지도로 — 대상지 2필지 복원·돌아가기", info == "map|2|true", info)

    js(host, "document.querySelector('[data-act=to_result]').click(); return 1;")
    wait_for(host, "state.screen === 'result'")
    info = js(host, "return state.screen + '|' + document.getElementById('doc_title').textContent;")
    check("결과로 돌아가기", info == "result|3D 모델 생성 완료", info)

    js(host, "document.querySelector('[data-act=rerange]').click(); return 1;")
    wait_for(host, "state.screen === 'map' && state.lots.length === 2")
    js(host, "ACTIONS.clear(); return 1;")   # 대상지를 지워도 돌아가기는 남는다
    wait_for(host, "state.lots.length === 0")
    check("대상지를 지워도 돌아가기", js(host, "return !!document.querySelector('[data-act=to_result]') ? '1' : '0';") == "1")
    js(host, "var rows = document.querySelectorAll('[data-act=recent]'); rows[1].click(); return 1;")
    wait_for(host, "state.screen === 'result'")
    pump(1)
    info = js(host, "return document.getElementById('doc_title').textContent + '|' + ((document.querySelector('#card2d .prev2d') || {}).textContent || '카드') + '|' + (document.getElementById('pick2d') ? '선택' : '선택없음');")
    check("옛 결과 — 폴더 한 줄", "만든 2D 1개" in info and "선택없음" in info, info)

    res["errors"] = json.loads(js(host, "return JSON.stringify(window.__errs || []);") or "[]")
    check("JS 오류 없음", not res["errors"], res["errors"])
finally:
    if os.environ.get("PANEL_KEEP") != "1":
        host.form.Close()
        scriptcontext.sticky.pop("gorani_site_panel", None)
    if not had_prefs and os.path.exists(PREFS):
        os.remove(PREFS)   # 시작 때 없던 파일만 — 시험이 만든 것(위 가드로 다른 패널이 없다는 것을 확인했다)
    failed = [k for k, v in res["checks"].items() if not v["ok"]]
    res["failed"] = failed
    with open(os.path.join(OUT_DIR, "result.json"), "w", encoding="utf-8") as f:   # noqa: F821
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("%d개 중 실패 %d" % (len(res["checks"]), len(failed)))
assert not failed, failed
