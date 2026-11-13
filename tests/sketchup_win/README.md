# Windows SketchUp 실기 시험 (노트북 `sf-win2`)

SketchUp 관련 검증은 Windows 노트북(호스트 hoon-x13, 사용자 bsh96, SketchUp 2027, `~/.ssh/config`의 `sf-win2`)에서 한다. `sf-win`은 다른 PC라 쓰지 않는다.

1. 빌드: `python3 scripts/dev_deploy.py sketchup` → `build/bsh_gorani-<판>.rbz`
2. 올리기: `scp build/bsh_gorani-<판>.rbz sf-win2:C:/Users/bsh96/Downloads/`, 이 폴더 파일은 `C:\Users\bsh96\Gorani_test\`로
3. 설치: `ssh sf-win2 "powershell -ExecutionPolicy Bypass -File C:\Users\bsh96\Gorani_test\install.ps1"`
   (확장 관리자가 하는 일과 같다 — rbz를 Plugins에 푼다. 시험 DB `seoul_*.db`도 `~/Gorani/data`로)
4. 실행: 예약 작업 `GoraniSketchUp`(사용자 화면 세션, `run_su.ps1`) → SketchUp이 빈 모델 + `-RubyStartup autotest.rb`로 뜬다.
   `autotest.json`의 대상지마다 패널을 열고 사이드카에 `generate`를 보낸 뒤, 결과 폴더에 `context.skp`가 생기면 화면을 PNG로 쓴다.
   끝 표시는 `out\done.txt`, 기록은 `out\log.txt`.
5. 화면 보기: 예약 작업 `GoraniShot`(`shot.ps1`) → `Gorani_test\shot.png`. 창 조작은 노트북의 Orca CLI를 SSH로
   (`C:\Users\bsh96\AppData\Local\Programs\orca\resources\bin\orca.exe computer …` — 사용자 화면의 앱을 다룬다).

같은 노트북의 Rhino는 다른 세션이 쓰므로 건드리지 않는다.
