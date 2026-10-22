# 고칠 것

2026-10-19 1차 배포(Rhino yak 0.1.0 공개, Gorani로 이름 변경) 뒤에 남은 일. 끝난 줄은 지운다.

## 배포

- [ ] 다른 컴퓨터(Windows일 수 있음)에서 Rhino판 실기 시험 — Mac에서 빌드한 .rhp·.pyc가 Windows Rhino 8에서 처음 도는 것일 수 있다.
- [ ] Blender 공식 스토어 — 0.3.1 제출(2026-10-22 03시) 뒤 0.3.2를 Upload New Version으로 올려 둠(16:50, 심사는 최신 판을 본다, 다음 판은 2시간 뒤부터). Approval Status = Awaiting Review. 심사 댓글은 Blender ID 메일 — 답변 문안 `docs/blender_store/README.md`.
- [ ] SketchUp Extension Warehouse — 2026-10-22 09:30 0.3.1(main 68ab551 rbz, sha256 2d40e9cd…) Submit For Review 완료("allow 1 to 3 weeks"). RuboCop ModelEntities 5건은 루트 그룹 설계라 사유를 적고 제출. 심사 메일이 오면 `docs/sketchup_store.md`대로 대응, 승인 뒤 My Extensions에서 Publish를 눌러야 공개된다. 0.3.2(Global 도로면)는 심사 중이라 못 올렸다 — 승인 뒤 68ab551 이후 main으로 새 판을 만들어 올린다.
- [ ] 다음 묶음 배포(0.3.3) 때 같이 낼 것 — 관리자 대시보드 [내 테스트 제외](2026-10-22): ① 플러그인 `usage_stats`의 개발자 PC 표시(`dev`, `~/.config/gorani/`가 있는 PC)는 main에 들어가 있어 yak·SketchUp 빌드에 저절로 실린다(Blender판은 usage_stats가 빈 판이라 상관없다) ② 웹사이트 `site.js` 개발자 브라우저 표시는 웹 저장소 브랜치 `dev-traffic`(PR)로 따로 있다 — 웹사이트 배포 때 머지한다.
- [ ] `docs/install.md`(yak 패키지에 들어가 패널 [문서 열기]로 열린다)의 SketchUp 절이 아직 없는 설치 경로(Extension Warehouse)를 안내한다. 스토어에 오를 때까지 '준비 중'으로 바꾸거나 스토어 주소로 고친다(Blender 절은 2026-10-21 스토어 기준으로 고침).

## 웹사이트 (저장소 `~/Documents/GitHub/gorani`)

- [ ] SketchUp·Blender가 스토어에 오르면 설치 칸(`index.html`·`en/index.html`·`ja/index.html`)과 `llms.txt`·`README.md`가 이미 스토어 설치 절차를 적고 있으니 주소만 확인한다(2026-10-22 일본어 페이지 `ja/` 추가, 버전 0.3.1).
- [ ] 웹사이트 패널 스크린샷 세 장(`assets/panel-*.webp`)과 '이렇게 생겼습니다'·설치 4단계 문구가 옛 4단계 패널이다 — 패널이 2화면(지도 → 결과)으로 바뀌었다(PR #4). `site_ui.html?mock=1&step=1|3d|2d`로 다시 찍고(`build/food4rhino/panel_*.png`가 지금 화면) 문구를 고친다.
- [ ] (옛 4단계 스크린샷 기준) 범위 단계(`assets/panel-extent.webp`): 용지는 A3가 골라져 있는데 지도 표시는 "A1 1:3000"이다. 목 데이터(`tests/fixtures/site_ui_mock.json`) 옵션과 preflight 결과를 맞추고 다시 찍는다(찍는 법은 메모리 project-website).
- [ ] 후원 링크: GitHub Sponsors 미가입이라 `github.com/sponsors/969flash`가 다른 곳으로 넘어간다. 토스 링크 자리 `#todo-toss`.
- [ ] 공유 미리보기 이미지(`og.html` → `assets/og*.png`)는 Rhino만 말한다. SketchUp·Blender가 나오면 다시 찍는다.
- [ ] 휴대폰 폭에서 본문이 오른쪽으로 넘치는지 실제 기기로 확인한다(헤드리스 Chrome 390 px 캡처에서 넘쳤지만 창 최소 폭 탓일 수 있다).
- [ ] 실제 Rhino 뷰포트 스크린샷(지금은 축측 도해 = 합성 데이터).

## 코드

- [ ] Global 도로면 다음 단계(2026-10-22 도로면 1차 뒤): 교량(`attrs.bridge`)은 지금 지형에 얹힌다 — 양끝 높이로 띄우기. 보도(OSM `sidewalk=*`)·연석은 없다. PLATEAU `brid`(교량)·`veg`(가로수)·`luse`(토지이용)·`wtr`을 팩에 더할지. OSM 버퍼끼리 겹친 자리의 베이스맵 경계선(04)은 아직 안 그린다(Rhino Boolean 합집합이 생기면 그린다).

- [ ] Blender 패널 서버(`panel_server._PollServer`)는 연결을 받은 뒤 요청 줄을 REQUEST_TIMEOUT(5 s)까지 기다리며 읽는다 — 브라우저가 미리 열어 두고 아무것도 안 보내는 소켓이면 Blender 메인 스레드가 최대 5 s 멈출 수 있다(0.3.1 리뷰 지적). 헤드리스 Chrome 실측(패널 두 번 열기, pump 1,224번)은 최대 0.33 s로 체감 없음. 다음 판: accept한 소켓은 select(…, 0)로 읽을 거리가 있을 때만 처리하고, 없으면 목록에 두었다가 다음 poll에서 본다.
- [ ] 원 범위에서 건물이 범위 밖(경계상자 모서리)까지 들어와 지형 밖에 떠 보인다 — `context_report.get_buildings_in_extent`가 경계상자로만 거른다. 해외 OSM·국내 모두(2026-10-21 Blender 렌더에서 발견, 기본 범위는 사각형이라 덜 보인다).
- [ ] `tests/test_3dm_readback.test_layer_full_paths`: 3dm 레이어 47 ≠ 응답 `context.layers` 41. 차이 6 = `CTX::Zoning` 아래 부모 레이어 수. `context_baker`의 레이어 셈과 테스트 중 하나를 맞춘다(2026-10-19 driver_full_run job 1019-004730-a73c).
- [ ] 춘천 문지기 VM은 2026-10-19부터 web 브랜치의 `server_gate.py`로 돈다(웹판용 HTTPS 443·CORS, Let's Encrypt IP 인증서). main의 `scripts/server_gate.py`로 `install`을 다시 돌리면 443·CORS가 빠진다 — 웹판을 합칠 때까지 문지기를 고칠 일은 web 워크트리 판과 그 `docs/domestic_gate.md` 'HTTPS·CORS' 절로 한다. main 판은 systemd Description만 Gorani로 바뀌어 있다.

## 이름 변경 뒤처리

- [ ] AutoCAD 워크트리(`.claude/worktrees/autocad`, 커밋 안 됨)를 다시 열 때 main을 합치기 전에 같은 치환(UrbanSite→Gorani, urbansite→gorani, URBANSITE→GORANI)을 먼저 한다. 명령 `URBANSITE`→`GORANI`, DXF 레이어 접두사 `US-*`도 바꿀지 정한다.
- [x] GA 이름을 Gorani로 바꿨다(2026-10-22, Admin API): 계정 Gorani, 속성 Gorani Rhino·Blender·웹, 스트림 이름·기본 URL. 측정 ID는 그대로.
- [ ] 옛 결과·로그 `~/UrbanSite/`(result·*.log)는 확인 뒤 지우거나 `~/Gorani/`로 옮긴다(옛 설치본 bsh_urbansite·urbansite는 2026-10-22 확인 — 없다).
- [ ] Hugging Face 데이터셋(`hooooooooon/urbandesigntool-data`) 카드에 옛 이름이 있는지 확인(저장소 이름은 그대로 둔다).
