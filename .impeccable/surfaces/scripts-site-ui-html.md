---
version: 1
slug: "scripts-site-ui-html"
primary_target: "scripts/site_ui.html"
related_targets: []
---

# 대지검토 패널 (scripts/site_ui.html) — 스타일 화면 포함

Mode: Operate. 480 px Eto WebView docked in Rhino. Steps ① 대상지 ② 범위·출력 ③ 결과, plus ③ → 도면 스타일 sub-screen.
Job: pick a site, get 3D + basemap + analysis maps; set one drawing style for every map (preset, per-element color, line/text scale, layout) and save it as JSON.
Prototype: scratchpad style_editor.html (artifact) before porting to site_ui.html.

## Direction contract

THESIS: 패널은 방안지 위에 그린 구성 격자다. 모든 행·버튼·견본이 8 px 모눈에 맞물리고, 회색 카드+파란 알약의 SaaS 설정창을 거부한다.
OWN-WORLD: 모눈 헤어라인 바탕, 잉크 #111 1 px 사각 괘선, 크라우얼 블루 하나(선택·주행동·구조선), 모서리 0, 행동 버튼 오른쪽 사선. Pretendard 본문, Tektur는 축척·번호·수치에만.
STORY: 사용자는 단계 셋을 같은 괘선 문법으로 지나고, 결과의 도면 격자에서 [스타일]로 들어가 범례 행을 눌러 요소 색을 바꾸고 16장에 적용한다.
FIRST VIEWPORT: 스타일 화면 — 위 도면 미리보기(같은 틀·축척, 모눈 켜기), 아래 프리셋 셀 4, 범례형 요소 색 행 10, 선·글자 셀 선택기, 하단 고정 [16장에 적용 /].
FORM: 크라우얼 격자 견본(사용자 선택 challenger), seed 0d9a7724.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance
