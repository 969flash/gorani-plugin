"""driver_wait_pump — RhinoApp.Wait() 펌프 최소 실험 (python3 scripts/dev_rhino_run.py tests/rhino/driver_wait_pump.py).

패널(PanelHost) 없이, 콜백 20회 사이에 RhinoApp.Wait() + sleep(0.2)를 넣고 Wait 1회 소요·누적 경과를 기록한다.
Wait가 이벤트를 펌핑하면 Rhino 화면이 멈추지 않고(수동 관찰) 호출 자체는 수 ms로 끝나야 한다. 결과: OUT_DIR/wait_pump.json.
실제 WebView 진행 막대·cancel 유입 확인은 패널을 열어 사용자가 본다(implementation_plan M4 첫 항목).
실측 [1007-224732-ea83, Mac Rhino 8.35]: 20회 4.05 s, Wait 1회 1.3~4.8 ms(평균 1.6 ms), Rhino 멈춤 없음 — 동기 유지.
"""
import json
import os
import time

import Rhino

rows = []
t0 = time.time()
for i in range(20):
    t1 = time.time()
    Rhino.RhinoApp.Wait()
    wait_ms = (time.time() - t1) * 1000.0
    time.sleep(0.2)
    rows.append({"i": i, "wait_ms": round(wait_ms, 2), "elapsed_s": round(time.time() - t0, 2)})
    print("callback %2d  Wait %.2f ms  elapsed %.2f s" % (i, wait_ms, time.time() - t0))
res = {"n": len(rows), "total_s": round(time.time() - t0, 2), "wait_ms_max": max(r["wait_ms"] for r in rows),
       "wait_ms_mean": round(sum(r["wait_ms"] for r in rows) / len(rows), 3), "rows": rows}
with open(os.path.join(OUT_DIR, "wait_pump.json"), "w", encoding="utf-8") as f:   # noqa: F821 — dev_rhino_run 머리말 전역
    json.dump(res, f, ensure_ascii=False, indent=1)
print("total %.2f s, Wait max %.2f ms, mean %.3f ms" % (res["total_s"], res["wait_ms_max"], res["wait_ms_mean"]))
assert 3.5 < res["total_s"] < 8.0, res["total_s"]
