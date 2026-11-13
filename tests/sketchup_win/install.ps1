$ErrorActionPreference = "Stop"
$plugins = "$env:APPDATA\SketchUp\SketchUp 2027\SketchUp\Plugins"
$rbz = (Get-ChildItem "C:\Users\bsh96\Downloads\bsh_gorani-*.rbz" | Sort-Object LastWriteTime | Select-Object -Last 1).FullName   # 가장 최근에 올린 판
Remove-Item -Recurse -Force "$plugins\bsh_gorani" -ErrorAction SilentlyContinue
Remove-Item -Force "$plugins\bsh_gorani.rb" -ErrorAction SilentlyContinue
Copy-Item $rbz "$env:TEMP\bsh_gorani.zip" -Force
Expand-Archive -Path "$env:TEMP\bsh_gorani.zip" -DestinationPath $plugins -Force
New-Item -ItemType Directory -Force -Path "C:\Users\bsh96\Gorani\data" | Out-Null
# 시험 DB는 노면표시·가로수만 담은 seoul_context.db 하나 — 나머지는 생성 때 공식 시군구 팩을 받는다. 필지 DB를 같이 넣으면 팩과 필지가 겹쳐 수면이 두 장 생겼다(2026-11-08)
Copy-Item "C:\Users\bsh96\Downloads\seoul_context.db" "C:\Users\bsh96\Gorani\data\" -Force
Get-ChildItem $plugins | Where-Object { $_.Name -like "bsh_gorani*" } | Select-Object Name
Get-ChildItem "$plugins\bsh_gorani" | Select-Object Name
Get-ChildItem "C:\Users\bsh96\Gorani\data" | Select-Object Name, Length
