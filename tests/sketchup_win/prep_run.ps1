# 시험 준비 — SketchUp을 끝까지 닫고 이전 결과 표시를 지운다
Get-Process SketchUp -ErrorAction SilentlyContinue | Stop-Process -Force
for ($i = 0; $i -lt 30 -and (Get-Process SketchUp -ErrorAction SilentlyContinue); $i++) { Start-Sleep -Milliseconds 500 }
Remove-Item C:\Users\bsh96\Gorani_test\out\* -Force -ErrorAction SilentlyContinue
schtasks /End /TN GoraniSketchUp 2>$null | Out-Null
schtasks /Run /TN GoraniSketchUp
