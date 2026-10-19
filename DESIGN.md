---
name: Gorani 패널
description: 방안지 위의 구성 격자 — Rhino에 붙는 480 px 패널
colors:
  paper: "#F5F7FA"
  grid: "#E4EAF2"
  surface: "#FFFFFF"
  ink: "#111418"
  ink-2: "#465061"
  ink-3: "#7D8798"
  hair: "#C9D2DE"
  rule: "#111418"
  line: "#A9C0F2"
  blue: "#0057FF"
  blue-dn: "#0044CC"
  blue-ink: "#0047D6"
  blue-wash: "#E9F0FF"
  on-blue: "#FFFFFF"
  warn: "#A8460B"
  dark-paper: "#0C1016"
  dark-grid: "#18202B"
  dark-surface: "#111821"
  dark-ink: "#E8ECF2"
  dark-ink-2: "#A9B3C3"
  dark-ink-3: "#8792A4"
  dark-hair: "#2A3442"
  dark-rule: "#5B6677"
  dark-line: "#24427A"
  dark-blue: "#2E69EE"
  dark-blue-dn: "#2457C9"
  dark-blue-ink: "#8CB0FF"
  dark-blue-wash: "#132241"
  map-topo: "#5c5c58"
  map-qa: "#d400d4"
typography:
  body:
    fontFamily: "Pretendard Variable, Pretendard, Apple SD Gothic Neo, Malgun Gothic, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: 1.5
  title:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "16px"
    fontWeight: 700
    lineHeight: 2
  figure:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "20px"
    fontWeight: 600
    lineHeight: 1.2
  heading:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.33
  section:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.23
  caption:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.33
  micro:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.27
  numeral:
    fontFamily: "Pretendard Variable, Pretendard, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    letterSpacing: "0.01em"
rounded:
  none: "0px"
spacing:
  cell: "8px"
  gutter: "16px"
  row: "32px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.on-blue}"
    rounded: "{rounded.none}"
    height: "32px"
    padding: "0 12px"
  button-primary-hover:
    backgroundColor: "{colors.blue-dn}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.none}"
    height: "32px"
    padding: "0 12px"
  cell:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink-2}"
    rounded: "{rounded.none}"
    height: "32px"
    padding: "6px 8px"
  cell-selected:
    textColor: "{colors.blue-ink}"
  step-current:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.on-blue}"
    height: "32px"
---

# Design System: Gorani 패널

## Overview

패널은 방안지(모눈종이) 위에 그린 구성 격자다. 모든 행·셀·견본이 8 px 모눈에 맞물리고, 1 px 사각 괘선과 크라우얼 블루 한 색만 쓴다. 회색 카드와 파란 알약 버튼의 SaaS 설정창을 거부한다. 패널은 Rhino 옆에 붙는 480 px Eto WebView라서 패널 자체가 화면 전체다. 그래서 모눈 바탕은 패널 본문 안에 있다.

기준 시안: `docs/ui_proposals/panel_grid_proto.html` (실데이터 자리는 `__DATA__`). 이식 대상: `scripts/site_ui.html`.

## Colors

전략은 Restrained다. 중립 잉크와 모눈 위에 파란색 하나만 쓴다.

### Primary
- `blue`: 주행동 버튼, 현재 단계, 선택된 셀의 테두리, 체크 상태에만 쓴다.
- `blue-ink`: 흰 바탕 위 파란 글자(섹션 제목, 선택된 셀 글자).
- `blue-wash`: 행 hover와 펼친 범례 행의 바탕.

### Neutral
- `paper` + `grid`: 패널 본문의 모눈 바탕(8 px 간격, 1 px 선).
- `surface`: 셀·범례 상자·모듈처럼 모눈 위에 놓이는 흰 면.
- `rule`: 패널 외곽·모듈·주 버튼의 1 px 잉크 괘선.
- `hair`: 셀과 범례 행의 가는 경계.
- `line`: 섹션 사이 구분선(옅은 파랑).

### Named Rules
- 파란색 하나 규칙: 상태 표시용 색을 더 만들지 않는다. 경고만 `warn`을 쓴다.
- 도면 색은 패널 색이 아니다: 미리보기 안 도면은 사용자 스타일 색(대상지 빨강 등)으로 그리고, 패널 지도(① ②)의 대상지는 `blue`로 그린다.
- 다크 모드는 같은 이름에 `dark-` 값을 쓴다. 다크에서 주 버튼 파랑은 흰 글자 대비 4.5:1 이상이어야 한다.

## Typography

패널은 Pretendard 한 가지다(오프라인 번들 — 다른 글꼴을 받을 수 없다). 숫자는 tabular-nums로 자리를 맞춘다. 단계는 11/12/13/15/16 px로 촘촘하고, 합계 같은 큰 수만 20 px다. 시안(docs/ui_proposals/panel_grid_proto.html)의 Tektur 숫자는 글꼴을 번들할 때까지 보류.

### Hierarchy
- 패널 제목 16 px 700, 하위 화면 제목 15 px 600
- 섹션 제목 13 px 600 `blue-ink`, 섹션 위 구분선 `line`
- 본문·버튼 13 px, 보조·캡션 12 px `ink-3`, 도면 칸 이름 11 px, 합계 숫자 20 px

### Named Rules
- 숫자 규칙: `<span class="num">`으로 감싸 tabular-nums.
- 라벨은 한 번만 규칙: 견본이 곧 색 선택기다. 설명 문장을 덧붙이지 않는다.

## Layout

- 모눈 단위 8 px. 행·버튼·셀 높이 32, 좌우 여백 16, 섹션 간격 16.
- 셀 묶음은 같은 폭 격자(`--n`열, 간격 8). 폭이 모자라면 열 수를 줄인다.
- 하단 바는 패널 안에서 sticky이고, 주행동은 항상 오른쪽 끝에 둔다.

## Elevation & Depth

그림자는 없다. 깊이는 모눈 바탕 위에 흰 면을 놓고 1 px 괘선으로 가르는 것으로만 만든다.

## Shapes

모든 모서리는 0이다. 버튼에 사선("/")이나 개수를 붙이지 않는다(2026-10-19 — 스텝퍼가 없어져 사선을 쓰는 곳이 없다).

## Components

### Buttons
- 주행동(`primary`): 파란 면 + 흰 글자. 한 화면에 하나.
- 보조: 흰 면 + 잉크 괘선. hover는 테두리와 글자가 파랑으로.
- 고스트: 테두리 없음, `ink-2` 글자. 뒤로·초기화·해제에 쓴다.

### Cells (선택기)
- 세그먼트·프리셋·레이아웃·선 굵기·단계색을 모두 같은 셀로 만든다. 선택된 셀은 파란 2 px(바깥 1 + 안쪽 1) 테두리와 파란 글자다.
- 셀 안에는 결과를 미리 보여 주는 표본을 넣는다: 색 띠, 선 굵기 표본, 레이아웃 도식, "가" 글자 크기.

### Legend rows (요소 색)
- 범례 상자 안에 그룹 "면"(종이·가구·도로·녹지·수계·건물)과 "선·글자"(철도·대상지·분석 범위·글자)를 둔다. 행은 견본, 이름, 색 코드(tabular-nums), 펼침 표시 순서다.
- 행을 누르면 그 아래에 견본 16개, 코드 입력, [직접 고르기]가 펼쳐진다. 한 번에 한 행만 펼친다.
- 잠긴 항목(관행색·출처 줄)은 범례 맨 아래에 자물쇠 아이콘과 함께 한 줄로 둔다.

### Modules (결과 화면)
- 흰 면 + 잉크 괘선, 위에 제목과 요약, 아래 괘선 너머에 행동 막대. 모듈 안에 모듈을 넣지 않는다.
- 도면 칸: 4열 격자, 칸마다 정사각 썸네일(160 px PNG) + 번호 + 이름. 빈 도면은 흐리게. 누르면 레이어 .ai로 연다.

### Navigation
- 화면은 둘(지도 → 결과)이고 스텝퍼는 없다(2026-10-19). 지도 화면의 주행동은 [3D 모델 만들기], 결과 화면의 2D는 카드 안의 [2D 만들기]. 스타일 화면은 결과에 속하고 미리보기를 위에 고정한다.
- 첫 화면은 지도다. 소개 문단과 방식 고르기 화면을 두지 않는다. 지도 위 도구줄 = 방식 칸 셋(필지·구역·위치, 괘선으로 붙은 셀, 선택은 안쪽 파란 2 px) + 검색칸. 지도 아래 트레이에 고른 것과 방식별 도구를 둔다.
- 지도 위 안내: 지도 위 가운데의 흰 면 + 파란 괘선 한 줄. 다음에 할 일(필지 누르기·꼭짓점 찍기·위치 찍기)만 말하고, 대상지가 생기면 사라진다.
- 더보기 메뉴: 헤더 오른쪽 메뉴 아이콘 버튼 하나가 연다. 헤더 괘선 아래로 내려오는 흰 면이고, 화면에 안 맞는 것(최근 대상지·작업 폴더·한국 자료 OSM 전환·API 키·안내)을 표 행(라벨 열 72 px)으로 모은다. 자료 기준일·경고는 패널에 두지 않는다. Esc·바깥 누르기로 닫는다.

### Icons
- 16 px, 선 1.5, 각진 끝의 인라인 SVG 심볼(`i-back`, `i-check`, `i-x`, `i-down`, `i-lock`, `i-search`, `i-menu`, 방식 표본 `i-lots`·`i-area`·`i-point`). 글리프나 이모지는 쓰지 않는다.

## Copy

- 안내 문구에 줄표("—")를 쓰지 않는다. 문장을 마침표로 끊는다.
- 가운뎃점("·")은 꼭 필요한 낱말 묶음에만 쓴다. 나열은 쉼표, 덧붙임은 괄호로 쓴다.
- 완료 제목은 짧은 명사형으로 쓴다(예: "3D 모델 생성 완료").

## Do's and Don'ts

### Do:
- 모든 크기를 8 px 배수로 맞춘다.
- 선택 상태를 파란 테두리로 보여 주고, 표본으로 결과를 미리 보여 준다.
- 도면 미리보기는 같은 틀과 축척을 유지한다. 도면을 바꿔도 지도가 움직이지 않는다.

### Don't:
- 둥근 모서리, 알약 모양, 그림자, 그라데이션을 쓰지 않는다.
- 섹션 제목 위에 영문 소제목(eyebrow)을 달지 않는다.
- 파란색 외에 강조색을 추가하지 않는다.
- 설명 문장으로 컨트롤을 해설하지 않는다.
