# 고칠 것

2026-10-19 1차 배포(Rhino yak 0.1.0 공개, Gorani로 이름 변경) 뒤에 남은 일. 끝난 줄은 지운다.

## 배포

- [ ] 다른 컴퓨터(Windows일 수 있음)에서 Rhino판 실기 시험 — Mac에서 빌드한 .rhp·.pyc가 Windows Rhino 8에서 처음 도는 것일 수 있다.
- [ ] Blender 공식 스토어(extensions.blender.org)에 올리기 — 사용자 Blender ID. 절차 `docs/blender_store/README.md`.
- [ ] SketchUp Extension Warehouse 심사 제출 — 개발자 신청 2026-10-22 접수, 승인 메일이 오면 My Extensions > Upload. 칸·이미지·심사 메모는 `docs/sketchup_store.md`. Windows 실기 시험 전이다.
- [ ] `docs/install.md`(yak 패키지에 들어가 패널 [문서 열기]로 열린다)의 Blender·SketchUp 절이 아직 없는 설치 경로를 안내한다 — `969flash.github.io/gorani/blender/index.json`은 없다. 스토어에 오를 때까지 '준비 중'으로 바꾸거나 스토어 주소로 고친다.

## 웹사이트 (저장소 `~/Documents/GitHub/gorani`)

- [ ] SketchUp·Blender가 스토어에 오르면 설치 칸 두 곳(`index.html`·`en/index.html`)과 `llms.txt`·`README.md`의 '준비 중' 문구를 설치 방법으로 바꾼다.
- [ ] 웹사이트 패널 스크린샷 세 장(`assets/panel-*.webp`)과 '이렇게 생겼습니다'·설치 4단계 문구가 옛 4단계 패널이다 — 패널이 2화면(지도 → 결과)으로 바뀌었다(PR #4). `site_ui.html?mock=1&step=1|3d|2d`로 다시 찍고(`build/food4rhino/panel_*.png`가 지금 화면) 문구를 고친다.
- [ ] (옛 4단계 스크린샷 기준) 범위 단계(`assets/panel-extent.webp`): 용지는 A3가 골라져 있는데 지도 표시는 "A1 1:3000"이다. 목 데이터(`tests/fixtures/site_ui_mock.json`) 옵션과 preflight 결과를 맞추고 다시 찍는다(찍는 법은 메모리 project-website).
- [ ] 후원 링크: GitHub Sponsors 미가입이라 `github.com/sponsors/969flash`가 다른 곳으로 넘어간다. 토스 링크 자리 `#todo-toss`.
- [ ] 공유 미리보기 이미지(`og.html` → `assets/og*.png`)는 Rhino만 말한다. SketchUp·Blender가 나오면 다시 찍는다.
- [ ] 휴대폰 폭에서 본문이 오른쪽으로 넘치는지 실제 기기로 확인한다(헤드리스 Chrome 390 px 캡처에서 넘쳤지만 창 최소 폭 탓일 수 있다).
- [ ] 실제 Rhino 뷰포트 스크린샷(지금은 축측 도해 = 합성 데이터).

## 코드

- [ ] `tests/test_3dm_readback.test_layer_full_paths`: 3dm 레이어 47 ≠ 응답 `context.layers` 41. 차이 6 = `CTX::Zoning` 아래 부모 레이어 수. `context_baker`의 레이어 셈과 테스트 중 하나를 맞춘다(2026-10-19 driver_full_run job 1019-004730-a73c).
- [ ] 춘천 문지기 VM은 2026-10-19부터 web 브랜치의 `server_gate.py`로 돈다(웹판용 HTTPS 443·CORS, Let's Encrypt IP 인증서). main의 `scripts/server_gate.py`로 `install`을 다시 돌리면 443·CORS가 빠진다 — 웹판을 합칠 때까지 문지기를 고칠 일은 web 워크트리 판과 그 `docs/domestic_gate.md` 'HTTPS·CORS' 절로 한다. main 판은 systemd Description만 Gorani로 바뀌어 있다.

## 이름 변경 뒤처리

- [ ] AutoCAD 워크트리(`.claude/worktrees/autocad`, 커밋 안 됨)를 다시 열 때 main을 합치기 전에 같은 치환(UrbanSite→Gorani, urbansite→gorani, URBANSITE→GORANI)을 먼저 한다. 명령 `URBANSITE`→`GORANI`, DXF 레이어 접두사 `US-*`도 바꿀지 정한다.
- [ ] GA 속성 표시 이름(UrbanSite Rhino·Blender·Web)을 GA 화면에서 Gorani로 바꾼다. 측정 ID는 그대로. ('Gorani SketchUp'은 2026-10-21에 새로 만들어 이름이 맞다)
- [ ] 이 Mac의 옛 설치본 지우기: Blender 확장 `urbansite`(SketchUp `bsh_urbansite`는 지워졌다). 옛 결과·로그 `~/UrbanSite/`(result·*.log)는 확인 뒤 지우거나 `~/Gorani/`로 옮긴다.
- [ ] Hugging Face 데이터셋(`hooooooooon/urbandesigntool-data`) 카드에 옛 이름이 있는지 확인(저장소 이름은 그대로 둔다).
