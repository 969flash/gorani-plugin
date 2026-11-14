# SketchUp 시험 실행 — 빈 모델(시작 화면 없이) + 시작 스크립트로 띄운다. 예약 작업(사용자 화면)에서 돈다.
# 매번 새 파일 이름으로 연다 — 같은 이름을 강제 종료 뒤 다시 열면 '복구된 버전을 여시겠습니까?' 창에서 멈췄다(2026-11-08)
$su = "C:\Program Files\SketchUp\SketchUp 2027\SketchUp\SketchUp.exe"
$dir = "C:\Users\bsh96\Gorani_test"
$blank = "$dir\blank.skp"
if (-not (Test-Path $blank)) { Copy-Item "C:\Program Files\SketchUp\SketchUp 2027\SketchUp\resources\en-US\Templates\Temp03b - Arch.skp" $blank }
Remove-Item "$dir\run_*.skp", "$dir\run_*.skb", "$dir\AutoSave_run_*.skp" -Force -ErrorAction SilentlyContinue
$run = "$dir\run_$(Get-Date -Format yyyyMMddHHmmss).skp"
Copy-Item $blank $run -Force
Start-Process -FilePath $su -ArgumentList @("`"$run`"", '-RubyStartup', "`"$dir\autotest.rb`"")
