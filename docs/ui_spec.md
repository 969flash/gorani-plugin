# 「UrbanSite」 패널 UX/UI 스펙 — 최종

- 작성 2026-10-07. 근거: `docs/deliverables.md`(요약·A.2·A.4·B·C 공통·E), `docs/data_sources.md` §0·§2.4, `CLAUDE.md`. 제안 3안(`docs/ui_proposals/wizard.md`·`map.md`·`single.md`)과 심사 3건(user·dev·craft)을 종합했다.
- 구현 계약(명령·푸시·상태 머신·파일 구성)은 `docs/panel_ui.md`가 원본이다. 이 문서는 화면·행동·문안을 정한다.
- **2026-10-10 변경**: ① 대상지 앞에 '방식 고르기' 화면이 생겼다(필지로 고르기·구역 그리기·위치만 찍기). ② 범위·옵션에 '좌표'(원점으로 옮김·실제 좌표)가 생겼다. 아래 ① 절의 필지 검색 화면은 '필지로 고르기' 방식의 화면이다. 방식별 동작·문안은 `docs/panel_ui.md` §대상지 방식이 원본.
- 제약: Eto WebView 1장(480×900, 리사이즈 가능, 도킹 불가) · 단일 HTML + 바닐라 JS/CSS · Leaflet 1.9.4·Pretendard 인라인 · 오프라인 · JS→Python `send({cmd})` 큐, Python→JS `window.app.receive({type})` 1개 · 파일 대화상자·Rhino 문서 조작은 Python · 1인 개발.

---

## 채택 이유

| 안 | user | dev | craft | 합계 |
|---|---|---|---|---|
| **wizard(단계형)** | 43 | 37 | 42 | **122** |
| single(단일 폼) | 36 | 40 | 39 | 115 |
| map(지도 중심) | 37 | 30 | 34 | 101 |

**뼈대 = wizard.** 세 심사 중 둘이 1위, 합계 1위. 채택 근거는 심사가 공통으로 꼽은 네 가지다.

1. 화면당 결정 하나(어디 → 얼마나 → 결과)라 처음 쓰는 비개발자가 헤맬 자리가 없다. 스텝퍼가 '지금 어디'를 늘 보여 준다.
2. 생성 **전** 자료 상태(기준일·새 판·도엽 커버리지·키)와 생성 **후** 신뢰도(높이 출처·정합 오차·건너뜀)의 역할이 분리돼 있다. data_sources §2.4(노랑 = 경과 AND 새 판)와 deliverables §C ⑤ 문안을 그대로 쓴다.
3. 예외 표가 가장 완전하다(컨텍스트 DB 없음은 차단하지 않고 필지만 생성, Import 실패 시 경로 표시, 취소 시 부분 폴더 유지, 창 닫기 시 서브프로세스 종료).
4. 진행 화면의 고정 phase 체크리스트 + 경과 타이머 + 스피너 금지 — Rhino UI 스레드가 Import 때 멈추는 현실을 정확히 반영한다.

**접목한 것** (심사가 지목한 다른 안의 아이디어, 전부 v1):

| 출처 | 접목 | 해소하는 wizard 약점 |
|---|---|---|
| map | ②의 SVG 미니맵 대신 **Leaflet 인스턴스를 ②로 옮겨**(컨테이너 이동, remove 없음) 타일 위에 범위(버퍼/원/사각형)·도엽 경계·미보유 도엽 해치·베이스맵 프레임을 그린다 | "②에서 지도가 사라진다, 500 m가 어디까지인지 못 본다" |
| map | ② 자료 상태 위에 **예상 한 줄**(건물 약 n동 · 도엽 n/m장 · ~초 · 약 MB) | 기다림의 크기를 미리 모른다 |
| map | ③ 베이스맵 카드의 [.ai 내보내기]에 축척 select(1000·3000·5000 고정) → 3dm 재생성 없이 `basemap_<축척>.ai`. 축척별 차이(선두께·지적선·지번 on/off)는 .ai를 쓸 때 적용(DB에서 다시 씀) | 축척 3종을 받으려면 세 번 생성 |
| map | 사전 경고·결과 경고·초기 경고를 **같은 스키마** `{level, code, text, action, center}`로, 렌더 함수 하나. `center`가 있으면 클릭 → 지도 이동(②) / Rhino 뷰 이동(③) | 같은 경고를 두 곳에서 따로 그린다 |
| map | 접힌 `고급 ▸`·`[바꾸기 ▸]`·`[고르기 ▸]` 요약에 **비기본값만** 표시("무벽건물 포함 · A0 · 시트 9장") | 숨긴 옵션이 켜져 있는지 안 보인다 |
| map | 첫 실행 블로커를 **4행 ✓✗○ 체크리스트**로(필지 DB · 컨텍스트 DB · 생성기 python3 · 키. 차단은 필지 DB 없음·생성기 없음) | — |
| map | 오류는 토스트 금지(카드 안 블록), **성공만 토스트** | 오류 토스트가 사라져 버린다 |
| single | 헤더 고정 **배지**(필지 날짜 · 건물 날짜 · 키 n/2)에 §2.4 색 → ①·③에서도 자료 상태가 보인다. 클릭 = `init`(다시 확인, 이동 없음). wizard의 ⓘ 툴팁 대체 | 상시 상태가 ②에만 있다 |
| single | 빈 검색줄에서 ↓ = **최근 대상지 5건**(`prefs.recent`), 창 열림 시 검색줄 자동 포커스, ⌘Enter = 어디서든 1차 동작 | 반복 사용 비용 |
| single | ① 푸터에 2차 버튼 **[바로 생성]**(사전 점검 경고 없을 때 노출) → J6가 1~2클릭 | 반복 사용 비용(wizard가 v2로 미룬 것) |
| single | ③→② 복귀 후 옵션이 바뀌면 유지된 결과 카드에 **"이전 결과 — 설정이 바뀜"** 띠 | — |
| single | 시트 썸네일 base64 푸시 **삭제**. ③ 시트는 13줄 목록(빈 시트 흐림+사유) + 클릭 = OS 기본 앱 | 30 MB 문자열 위험 |
| single | `?mock=1` 브라우저 목 + 계약 unittest 1개 | Rhino 없이 UI를 못 돌린다 |
| single | running 중 ①②를 `<fieldset disabled>` + `body[data-step][data-run]` CSS로 처리 | JS 분기 수 |
| single | INVALID_KEY 조치 문장에 ".env의 `= ` 뒤 공백 확인", 건물 0 = 노랑 / 필지 0 = 실패, 베이스맵 프레임 > 반경 경고 | 예외 표 보강 |
| dev 종합 | `preflight`는 **Rhino 안 로직 모듈**(stdlib sqlite + RhinoCommon 커브 오프셋)로 100 ms급 — 서브프로세스·shapely 없음 | 아키텍처 충돌 |
| dev 종합 | `open_folder`·`open_file`·`open_doc`·`open_env` → **`open_path` 하나** | Python 처리기 수 |
| dev 종합 | '다시 넣기'는 옵션 없이 **항상 기존 CTX·BM 삭제 후 Import**(상수) | 중복 베이크 함정 |
| dev 종합 | '새 판 있음' 조회(브이월드 목록 HTTP)는 `init`에서 동기로 하지 않는다 — 비차단 서브프로세스가 캐시 파일에 쓰고 `preflight`·생성기가 읽는다. 실패면 `newer_date:null` | 창 열림 시간 |
| dev 종합 | `map_lots`에 `seq`를 붙여 늦은 응답을 버린다 | 지도 연속 이동 시 역전 |

## 버린 대안

| 대안 | 출처 | 버린 이유 |
|---|---|---|
| 하단 3단 드래그 드로어(64/360/820) | map | 480×900에서 결과 상태가 되면 지도가 80 px 띠가 돼 '지도 중심'이 무색해진다. 비개발자에게 설명 없는 상호작용 축이 하나 는다 |
| 옵션 `localStorage` 저장 | map | 인라인 HTML을 임시 파일 file:// 출처로 여는 WKWebView/WebView2에서 보장되지 않는다 → Python `~/.urbansite/prefs.json` |
| 컨텍스트 DB 없음 → 전체 차단 | map | deliverables·CLAUDE.md("예외는 경고로")대로 필지만으로 생성 허용 |
| .ai 내보내기를 Import 전에 누르면 몰래 Import→Export→정리 | map | Undo 스택 오염. .ai 버튼은 Import 완료 전 비활성 |
| 원·사각형 드래그 리사이즈, 지도 레이어 토글 팝오버(⊞) | map | 세그먼트+직접 입력으로 전부 가능. 자체 드래그 구현은 버그 표면만 는다 |
| 시트 SVG 문자열 푸시·페이저 뷰어 / 13장 base64 썸네일 | map·wizard | 1~3 MB×13을 WebView에 올린다. OS 기본 앱으로 연다. 필요해지면 생성기가 200 px PNG를 떨어뜨려 `done.sheets[].thumb`로 |
| 옵션 전부 노출(세그먼트·select 10여 개가 24~28 px 줄에) | single | 처음 쓰는 비개발자가 압도된다(안 스스로 인정). 기본 4체크 → 인라인 디스클로저 → 고급 3계층 유지 |
| 지도 260 px 고정 + [⤢]/F 토글 | single | 합필 클릭(J1 핵심)에 작다. ①은 세로 전부를 지도가 쓴다 |
| Import 직후 축척 3개 .ai 자동 Export | single | UI 스레드 멈춤이 3번 겹치고 실패 연쇄가 불명확. 명시적 버튼 1개 |
| 사전 점검 없음(생성 후에만 도엽 커버·데이터 없음을 앎) | single | 수십 초 기다린 뒤 '지형 일부 생략'을 보는 경험 |
| ③ 생성을 별도 스텝퍼 단계로 | wizard | 사용자가 결정하지 않는 단계가 스텝퍼를 차지하고 480 px에 한글 4라벨이 빠듯. 생성 진행은 ③ 결과 자리에서 `run=running`으로 그린다 — 스텝은 3개 |
| `save_api_key`로 `.env` 직접 쓰기 | wizard | 쓰기 코드가 `= ` 공백 버그를 다시 만들 여지. `.env`를 OS 편집기로 열고 [다시 확인] |
| `existing_ctx`(바꾸기/옆에 추가)·`folder_name`(대상지명/PNU) 옵션 | wizard | 상태만 는다. 바꾸기 고정, 폴더명 = 대상지명 고정 |
| `preflight`를 별도 Python 서브프로세스로 | wizard·map | 100 ms가 아니다. Rhino 안 로직 모듈로 |
| 다크 모드, 터치, 애니메이션 | 공통 | Rhino 라이트 창 하나. 진행 막대 폭 전환 150 ms만 |

---

## 1. 요약 — 설계 원칙

1. **화면당 결정 하나, 단계는 셋.** ① 어디(대상지) → ② 얼마나(범위·옵션, 지도 위에서) → ③ 무엇이 나왔나(생성 진행과 결과). 더 쪼개지 않는다.
2. **기본값으로 끝까지 간다.** 대상지만 고르면 ①에서 [바로 생성]으로 끝난다. ②는 반경·형태·산출물 4체크만 드러내고 나머지는 접는다.
3. **경고는 생성 전에 보여 주고(자료 상태), 생성 후에 다시 센다(신뢰도).** 어느 경고도 생성을 막지 않는다(CRS 자가검사 실패만 중단).
4. **공간 판단은 지도에서.** 범위·도엽 커버·베이스맵 프레임·불일치 지점은 글이 아니라 지도 위 도형이다. Leaflet 인스턴스는 하나이고 ①↔② 사이를 옮겨 다닌다.
5. **상태는 `step`(1~3)과 `run`(idle·running·done·failed·cancelled) 둘.** 모달 없음. 전역 오버레이는 "준비 안 됨" 블로커(필지 DB·생성기 python3) 하나, 토스트는 성공 알림만.
6. **되돌아가도 잃지 않는다.** ③→②(옵션만 바꿔 재생성)·③→①(새 대상지)이 한 클릭. 옵션·최근 대상지는 Python이 `prefs.json`에 기억한다.

---

## 2. 사용자·과업

사용자: 사내 건축사·도시설계자. Rhino는 쓰지만 코드·GIS 툴은 모른다. 하루 1~3곳, 착수 당일 오전에 컨텍스트와 현황도 초안을 들고 회의에 들어간다.

| # | 과업 | 성공 기준 | 빈도 |
|---|---|---|---|
| J1 | 주소·지번으로 대상지를 찾고 지도에서 눌러 필지 여러 개를 합친다 | 2분 안에 확정. 합필 면적 합이 보인다 | 매번 |
| J2 | 주변을 얼마나 가져올지 정한다 | 범위 도형이 타일 지도에 보이고, 규모(건물 n동·도엽 n/m·~초)를 미리 안다 | 매번 |
| J3 | 3D 컨텍스트를 지금 열린 Rhino 문서에 넣는다 | 버튼 1개, 원점·단위를 신경 쓰지 않는다. 실패하면 왜인지 안다 | 매번 |
| J4 | 베이스맵 .ai를 Illustrator에서 연다 | 레이어 분리. 축척을 바꿔 다시 낼 때 3dm을 다시 만들지 않는다 | 매번 2~3회 |
| J5 | 현황도 13장·조서 CSV를 받는다 | 폴더가 열리고 어느 시트가 비었는지(사유) 안다 | 매번 |
| J6 | 결과를 믿어도 되는지 판단한다 | "건물 4.9개월 지남", "높이 추정 61 %", "정합 1.2 m"를 읽고 각주를 쓸 수 있다. 불일치 지점을 위치로 본다 | 매번 |
| J7 | 반경·축척만 바꿔 다시 뽑는다 | 대상지 재선택 없이 30초 안에 | 자주 |
| J8 | 키·DB가 없는 상황을 해결한다 | 무엇이 없고 어디서 받아 어디 두는지 한 화면 | 설치 때 |

비과업: 규모검토·자동배치·법규 판정·웹 공유·데이터 수집(§0 체크리스트는 개발자가).

---

## 3. 정보구조(IA)와 화면 흐름

### 3.1 IA

```
UrbanSite (창 1개, 480×900)
├─ 헤더 56: 제목 + 배지(필지·건물·키) / 스텝퍼 [① 대상지] [② 범위·옵션] [③ 결과]
├─ 경고 띠(있을 때만): init_state.warnings — 컨텍스트 DB 없음 등
├─ 본문 780 스크롤(②는 스크롤 전제): section[data-step] 셋 중 하나만 표시
│   ① 대상지   : 검색줄(+최근) · 지도(남는 세로 전부) · 대상 칩 · 합계
│   ② 범위·옵션: 대상지 1줄 · 지도(240) · 반경·형태 · 예상 · 산출물 4체크 · 자료 상태(ok 접힘) · 고급 ▸
│   ③ 결과     : run=running → phase 체크리스트·타이머·로그·[취소]
│                run=done    → 완료 줄 · 문서/베이스맵/시트·조서 카드 · 경고 · 신뢰도 · 산출물 목록
│                run=failed|cancelled → 체크리스트(✗) · 오류 카드 · [뒤로][다시 시도]
├─ 푸터 64: 단계별 버튼(§4.1 표)
└─ 전역: "준비 안 됨" 블로커(본문 덮음) · 토스트(성공만, 3초)
```

### 3.2 상태 전이

```
            init_state.blocked (필지 DB 없음 · 생성기 python3 없음)
 시작 ───────────────────────────────────────────▶ [블로커] ──(파일 배치·설치 → 다시 확인)──▶ ①
   │
   └ 정상 ▶ ① 대상지 ──(lots ≥ 1, 다음)──▶ ② 범위·옵션 ──(생성 시작)──▶ ③ running ──done──▶ ③ done
             │  ▲  │                        ▲   │                              │               │ ▲
             │  │  └──(바로 생성)────────────┼───┘                              │ failed/       │ │
             │  │                           │                                  │ cancelled     │ │
             │  └────── 뒤로 ───────────────┘◀──────── 뒤로 ───────────────── ③ failed ◀──────┘ │
             │                                                                  (다시 시도 → running)
             │  ◀──────────────────── 새 대상지(lots·result 초기화) ──────────────────────────────┘
             └──────────────────────────────── 옵션 바꿔 다시(→ ②, result 유지) ───────────────┘
```

규칙
- 스텝퍼: 현재 단계 `aria-current`, 완료 단계는 클릭 가능, 미도달 단계 비활성. ③은 `run ≠ idle`일 때만 도달 상태.
- ①에서 lots = 0이면 [다음]·[바로 생성] 비활성, 힌트 "지도에서 필지를 누르거나 주소를 검색하세요".
- `preflight`는 ① lots 변경 직후와 ② 진입·반경/형태/용지/축척 변경 시(300 ms 디바운스) 보낸다. 응답 전에도 [생성 시작]은 눌린다 — 사전 점검은 정보이지 게이트가 아니다.
- [바로 생성]은 lots ≥ 1 이고 최신 `preflight_result.warnings`에 `warn`·`danger`가 없을 때만 보인다. 누르면 현재 `options` 그대로 `generate`.
- ③ running 중 ①②는 `fieldset[disabled]`, 스텝퍼 클릭 불가. 창 닫기 = 취소.
- ③→② 이동: lots·result 유지. 이후 옵션이 하나라도 바뀌면 `dirty=true` → 스텝퍼로 ③에 돌아오면 결과 카드 위에 "이전 결과 — 설정이 바뀜(옵션 그대로 다시 생성하려면 ② [생성 시작])" 띠. 카드의 버튼(폴더 열기 등)은 유효.
- ③→①(새 대상지): lots·preflight·result 초기화, options 유지, run=idle.
- 창을 닫았다 열면 ①부터. options·recent는 `prefs.json`에서 복원.
- 세션 중 `init`(배지 클릭·[다시 확인])은 화면을 옮기지 않는다 — 배지·헤더 띠·블로커·자료 상태만 갱신, `step`·`run`·`lots`·`options`·`result` 유지(panel_ui 상태표). ②에 있으면 `preflight`를 다시 보낸다.

### 3.3 해피 패스(클릭 수)

- 처음: 검색 Enter(후보 1건이면 대상 추가 + flyTo) → 옆 필지 클릭(합필) → [다음] → [생성 시작] → 결과. 4동작.
- 두 번째부터(J7): 창 열림 → 빈 검색줄 ↓ → 최근 대상지 Enter → [바로 생성] 또는 ⌘Enter. 3동작. 반경만 바꾸려면 [다음] → 반경 클릭 → [생성 시작].

---

## 4. 화면별 와이어프레임(480×900)과 컴포넌트

공통 셸: 헤더 56(제목·배지 행 28 + 스텝퍼 28), 푸터 64, 본문 780 스크롤, 좌우 패딩 16. 창을 늘리면 ①은 지도가, ②③은 여백이 먹는다. ①은 스크롤 없음(지도가 남는 세로를 먹음), ②③은 스크롤 전제 — 푸터 1차 버튼은 고정이라 스크롤과 무관하게 보인다.

### 4.1 헤더·스텝퍼·푸터(공통)

```
┌────────────────────────────────────────────────┐
│ UrbanSite     필지 05-13 · 건물 05-09 ● · 키 2/2 │  ← 배지: §2.4 색(회/노/빨), 키 2/2·브이월드만·없음. 클릭 = init
│ ● 대상지 ━━━━━━ ○ 범위·옵션 ━━━━━━ ○ 결과        │  ← 현재 = 채운 원+굵게, 완료 = ✓(클릭), 미도달 = 빈 원 회색
└────────────────────────────────────────────────┘
```

- 배지 문구는 `init_state.sources`에서: `필지 MM-DD` · `건물 MM-DD` (level≠ok면 ● 색점) · `키 2/2`/`브이월드만`/`포털만`/`키 없음`(`sources[api].keys`). 배지 클릭 = **`init` 재전송 하나**(다시 확인). 화면 이동 없음 — 자료 상태 상세는 ②에서, ②에는 [다시 확인] 링크가 따로 있다. 툴팁은 `title`로 원천명·기준일. 창 폭 < 420이면 날짜를 숨기고 점만.
- 푸터 버튼(단계별 테이블 하나):

| step·run | 왼쪽(2차) | 오른쪽(1차) |
|---|---|---|
| ① | [바로 생성](조건부, 2차) | [다음: 범위·옵션 →] |
| ② | [← 뒤로] | [⚡ 생성 시작] |
| ③ running | — | [취소] (phase=import·busy 중 비활성, 툴팁 "문서에 넣는 중에는 취소할 수 없습니다") |
| ③ done | [옵션 바꿔 다시] | [새 대상지 →] |
| ③ failed/cancelled | [← 뒤로] | [다시 시도] |

### 4.2 ① 대상지

```
┌────────────────────────────────────────────────┐
│ UrbanSite     필지 05-13 · 건물 05-09 ● · 키 2/2 │
│ ● 대상지 ━━━━━━ ○ 범위·옵션 ━━━━━━ ○ 결과        │
├────────────────────────────────────────────────┤
│ ┌──────────────────────────────────┐ ┌───────┐ │
│ │ 🔍 주소·지번·PNU (↓ 최근 대상지)   │ │ 검색  │ │  ← 창 열림 시 자동 포커스
│ └──────────────────────────────────┘ └───────┘ │
│   └ 후보 3건 ▾ / 최근 5건 ▾ (listbox, ↑↓ Enter)   │
│ ┌──────────────────────────────────────────────┐│
│ │                                              ││
│ │              Leaflet 지도                     ││
│ │      필지 폴리곤 · 클릭 = 대상 토글            ││
│ │                                              ││
│ │   [확대하면 필지가 보입니다] ← 줌 < 17 칩       ││  ← 세로 남는 전부 (≈ 520)
│ │   [일부만 표시 — 더 확대] ← truncated 칩        ││
│ │                                        ⊕ ⊖   ││
│ └──────────────────────────────────────────────┘│
│ 대상 필지 2  ·  합계 1,234.5 ㎡        [모두 지움]│
│ │ 성수동2가 277-17   대 · 612.3 ㎡          ✕   ││
│ │ 성수동2가 277-18   대 · 622.2 ㎡  ⚠2조각   ✕   ││  ← 행 호버 = 지도 강조, 행 클릭 = 지도 flyTo
├────────────────────────────────────────────────┤
│ [바로 생성  500 m · 버퍼 · 전부]  [다음: 범위·옵션 →]│
└────────────────────────────────────────────────┘
```

컴포넌트
- `search-bar`: input + 버튼. Enter = `search`. 결과 1건 → flyTo(줌 17.5) + `select_lots`(추가). 여러 건 → 아래 `listbox`(최대 8, 주소 · 지목 · 면적). 빈 입력에서 ↓ 또는 ⌄ = `prefs.recent` 5건(라벨 "성수동2가 277-17 외 1 · 1,234 ㎡ · 10-06"), 선택 = `select_lots {pnus}` + flyTo. VWorld 보조 검색은 키 있을 때 자동(토글 없음). 0건: 입력 아래 1줄 "찾지 못했습니다 — 동 이름까지 적어 보세요(예: 성수동2가 277-17 또는 19자리 PNU)".
- `map`: Leaflet 캔버스. 줌 ≥ 17에서 `map_lots {bbox, seq}`(moveend 250 ms 디바운스), 응답 `seq` < 최신이면 버림. 필지 스타일 §9. 대상은 `targetLayer`로 별도 유지. 호버 툴팁 `주소 / 지목 · 면적`.
- `lot-chips`: 행 = 지번 · 지목 · 면적 · (⚠ 다조각/구멍 배지, 툴팁 "가장 넓은 조각의 바깥 경계만 씁니다") · ✕(`aria-label="277-18 제외"`). [모두 지움].
- 푸터 [바로 생성]: 2차 버튼. 라벨 옆 작은 글자로 현재 옵션 요약(반경 · 형태 · 산출물 수). preflight 경고(warn/danger) 있으면 숨김.

### 4.3 ② 범위·옵션

```
┌────────────────────────────────────────────────┐
│ UrbanSite     필지 05-13 · 건물 05-09 ● · 키 2/2 │
│ ✓ 대상지 ━━━━━━ ● 범위·옵션 ━━━━━━ ○ 결과        │
├────────────────────────────────────────────────┤
│ 성수동2가 277-17 외 1 · 1,234.5 ㎡          [변경]│
│ ┌──────────────────────────────────────────────┐│
│ │  (같은 Leaflet, 240 px, 클릭 없음)            ││
│ │   ■ 대상지   ╌╌ 범위 500 m   ┆ 도엽 37705072   ││
│ │   ▒▒ 미보유 도엽(사선 해치 "지형 없음")        ││
│ │   □ 베이스맵 프레임 A1 1:3000                  ││
│ └──────────────────────────────────────────────┘│
│ 반경   (300) (●500) (1000) (직접 ____ m)         │
│ 형태   (●경계 버퍼) (중심 원) (사각형)             │
│ 예상   건물 약 1,842동 · 도엽 3/4장 · ~40초 · 8 MB │
│ 산출물 (context.3dm은 항상)                      │
│  [✓] 생성 뒤 현재 문서에 넣기                     │
│  [✓] 베이스맵 .ai   A1                 [바꾸기 ▸] │
│  [✓] 현황도 시트    13장 전체          [고르기 ▸] │
│  [✓] 조서 CSV                                  │
│ 자료 상태                          [다시 확인]   │
│  ▸ 필지 ✓ · 지형 ✓  (ok 행은 접힘 1줄)            │
│  ● 건물  GIS건물 2026-05-09 · 4.9개월 · 새 판 있음 ▾│
│    ⚠ 건물 자료가 4.9개월 지났습니다 … [절차 열기]  │
│  ○ 키  브이월드만 → 철거·말소 반영 생략 [.env 열기] │
│ ▸ 고급   무벽건물 포함                            │
├────────────────────────────────────────────────┤
│ [← 뒤로]                         [⚡ 생성 시작]  │
└────────────────────────────────────────────────┘
```

컴포넌트
- `lot-summary`: 1줄 + [변경](→ ①).
- `map`(이동): ② 진입 시 `#map_slot_2.appendChild(mapEl)` 후 `invalidateSize()`, `fitBounds(extent)`. 필지 클릭 비활성(`lotsLayer` 숨김). 그리는 레이어: `targetLayer`, `extentLayer`(`preflight_result.extent_geojson` role=extent), `topoLayer`(role=`topo_sheet` — 수치지형도 도엽, `have=false`면 SVG pattern 사선 해치 + 라벨 "지형 없음"), `frameLayer`(role=frame, `options.scales`마다 사각형 + 라벨 "A1 1:3000"), `qaLayer`(done 뒤 `done.qa_geojson`, 마젠타 점). 응답 전에는 원·사각형만 JS가 즉시 그리고(중심·반경 계산) 버퍼는 응답을 기다린다(≤100 ms).
- `radius-seg`: `role=radiogroup`. 직접 = 숫자(100~2000, step 50). > 1000이면 아래 회색 힌트 "1 km 초과는 파일이 수십 MB — 분할 권장".
- `shape-seg`: 사각형 선택 시 힌트 "베이스맵 프레임과 맞출 때".
- `estimate`: `preflight_result.estimate` 1줄. 응답 전 "계산 중…" 회색(200 ms 지연 후 표시).
- `deliverable-rows`: 체크 4 — `import_after`·`make_basemap`·`make_sheets`·`make_tables`. `context.3dm`은 항상 쓰므로(수 초, 산출물의 뼈대) 체크가 없고 섹션 제목 옆 회색 "context.3dm은 항상"으로만 알린다. [바꾸기 ▸]·[고르기 ▸]는 행 아래 인라인 디스클로저(§6). 접힌 요약은 비기본값만("A0 · 1:1000·1:3000", "9장").
- `data-status`: `preflight_result.sources` 행 = 색 점(● ok/warn/danger, ○ missing) · 라벨 · 원천명 · 기준일 · 경과 · 부가. **ok 행은 접어서 1줄**("▸ 필지 ✓ · 지형 ✓", 전부 ok면 "자료 상태 ✓ 4건 ▸"), warn/danger/missing 행만 펼친 채 시작(조치 문장 §5 문안이 바로 보임). 지형 행의 [▸지도]는 `warnings[].center`로 flyTo. 키 행(`sources[api].keys`): 둘 다 있음 "키 2/2", 브이월드만 "브이월드만 → 철거·말소 반영 생략", 포털만 "포털만 → 건물 최신화 생략", 없음 "키 없음 → 건물 최신화·철거 반영 생략". [.env 열기] = `open_path {path:".env"}`(없으면 두 줄 템플릿). 섹션 제목 옆 **[다시 확인]** = `init` — 저장 후 ①로 돌아갈 필요가 없다(화면 유지, 자료 상태만 갱신).
- `advanced`: 네이티브 `<details>`. 요약에 비기본값. 내용 §6.4.
- 높이 예산(900 창, 본문 780): 대상지 32 + 지도 240 + 반경 36 + 형태 36 + 예상 28 + 산출물(제목 38 + 4행 128) + 자료 상태(제목 38 + ok 접힘 24 + warn 행 24 + 조치 2줄 40) + 고급 32 + 섹션 간격 12×4 ≈ 700. 기본 상태에서 [생성 시작](푸터 고정)과 자료 상태가 함께 보인다. **②는 스크롤 전제**다 — warn/danger 여러 행·[바꾸기 ▸] 인라인(≈100)·1 km 힌트가 열리면 넘친다. 그래서 자료 상태 행 24, 섹션 제목 위 간격 12(§9).

### 4.4 ③ 결과 — running

```
┌────────────────────────────────────────────────┐
│ ✓ 대상지 ━━━━━━ ✓ 범위·옵션 ━━━━━━ ● 결과        │
├────────────────────────────────────────────────┤
│ 생성 중 — 성수동2가 277-17 외 1 · 반경 500 m 버퍼  │
│ ████████████░░░░░░░░░░░░░░░░░  38 %    0:14 경과 │
│                                                │
│  ✓ 필지·건물·지형 조회           1,842동 · 3도엽  │
│  — 건물 최신화(VWorld·건축HUB)    건너뜀 — 키 없음 │
│  ● 지형 TIN·면 분류·정합 측정     12만 점…        │
│  ○ 3dm 쓰기                                     │
│  ○ 베이스맵 레이어                               │
│  ○ 현황도 시트 13장                              │
│  ○ 조서 CSV                                     │
│  ○ 문서에 넣기(Import)                           │
│                                                │
│  ▸ 로그 (23줄)                                  │
│                                                │
│  Rhino는 이 동안 멈추지 않습니다.                 │
│  마지막 'Import' 단계만 몇 초 멈춥니다.           │
├────────────────────────────────────────────────┤
│                                      [ 취소 ]   │
└────────────────────────────────────────────────┘
```

- `progress-bar`: `role=progressbar`. 경과 시간은 JS 타이머(서브프로세스가 멈춘 듯 보여도 돈다). 스피너 금지. 10초 넘으면 아래에 회색 "반경 500 m는 보통 10~40초".
- `phase-list`: 고정 8행(`progress.phase_status`). ✓ done / ● running / ○ pending / — skipped / ✗ failed. 오른쪽에 `detail` 짧은 수치. 체크 안 한 산출물의 phase(베이스맵·시트·조서·Import)는 "건너뜀"으로 표시하고 % 분모에서 뺀다(Python). 3dm 쓰기는 항상. 건물 최신화 detail: "건물 12동 갱신 · 철거 3동 반영" / "건너뜀 — 키 없음" / "건너뜀 — 포털 키 없음(철거 생략)" / "건너뜀 — 네트워크 없음". **phase 단위 실패**(베이스맵·시트·조서가 예외로 통째로 실패)는 ✗ + detail "생성 실패"로 찍고 다음 phase로 계속 — 결과는 done으로 끝나고 ③ 카드에 드러난다(§7).
- `log-drawer`: `<details>` 안 `<pre>` 등폭 12 px, 400줄 상한, 새 줄 자동 스크롤(사용자가 올려 두면 멈춤). `⚠`·`✗` 줄은 색.
- failed/cancelled: 해당 행 ✗ 또는 "취소됨" + 아래 오류 카드(`role=alert`: 제목 1줄 · 상세 접힘 · [로그 복사]). 부분 산출물 폴더가 있으면 [폴더 열기] 유지.
- [취소]: `progress.phase === "import"` 또는 `busy.on`이면 비활성 + 툴팁 "문서에 넣는 중에는 취소할 수 없습니다"(Import는 UI 스레드라 취소가 닿지 않고, Python도 `proc is None`이면 무시한다). 취소 직후 자식이 끝나도 `done`은 오지 않는다 — 항상 cancelled로 끝난다.

### 4.5 ③ 결과 — done

```
┌────────────────────────────────────────────────┐
│ ✓ 대상지 ━━━━━━ ✓ 범위·옵션 ━━━━━━ ● 결과        │
├────────────────────────────────────────────────┤
│ ✓ 생성 완료 · 0:41 · result/20261007/성수동2가_277-17외1 ↗│
│ (이전 결과 — 설정이 바뀜)              ← dirty일 때만│
│ ┌ 문서 ───────────────────────────────────────┐ │
│ │ CTX 레이어 12 · 건물 1,842 · 필지 2,310     │ │
│ │ [문서에 넣음 ✓]  [대상지로 줌]  [다시 넣기]   │ │
│ └────────────────────────────────────────────┘ │
│ ┌ 베이스맵 ───────────────────────────────────┐ │
│ │ A1 · 레이어 15                                │ │
│ │ [.ai 내보내기]  축척 [1:3000 ▾]   (다른 축척 · 1초 안팎)│ │  ← select 1000·3000·5000 고정, 기본 = options.scales[0]
│ │ basemap_3000.ai ✓                            │ │
│ └────────────────────────────────────────────┘ │
│ ┌ 시트·조서 ──────────────────────────────────┐ │
│ │ 시트 13장(빈 시트 1) · CSV 5                  │ │
│ │ [폴더 열기]  [시트 목록 ▾]                    │ │
│ └────────────────────────────────────────────┘ │
│                                                │
│ ⚠ 경고 3건                                     │
│  ● 건물 높이 추정 비중 큼 — A+B 등급 61 %     ▸   │
│  ● 건물 자료 4.9개월 경과 · 새 판 있음         ▸   │
│  ○ 지적–지형 불일치 의심 7건            [Rhino]   │
│                                                │
│ 신뢰도                                         │
│  높이 출처  █████████▒▒▒▒▒░░░  대장 34 · 층수 27 │
│             · 지형도 29 · 기본 10 %              │
│  정합 오차  중앙값 1.2 m · p90 3.9 m (n=17,581)  │
│  건너뜀     건물 3동 · 필지 1          [log.txt] │
│  자료기준   필지 05-13 · 건물 05-09 · 지형 24~26  │
│                                                │
│ ▸ 산출물 목록 (파일 21개)                        │
├────────────────────────────────────────────────┤
│ [옵션 바꿔 다시]                  [새 대상지 →]  │
└────────────────────────────────────────────────┘
```

상세는 §7. 동작 버튼 4개(문서·.ai·폴더·시트)가 첫 780 px 안에 들어온다.

### 4.6 전역 — "DB 없음" 블로커

```
┌────────────────────────────────────────────────┐
│ UrbanSite                                       │
├────────────────────────────────────────────────┤
│   UrbanSite를 쓰려면 데이터가 필요합니다          │
│                                                │
│   ✗ 필지 DB      data/seoul_site.db 없음        │
│   ✓ 컨텍스트 DB  data/seoul_context.db (05-09)  │
│   ✗ 생성기       python3(geopandas·rhino3dm) 없음│
│   ○ 키           브이월드만 — 선택(철거 반영 생략) │
│                                                │
│   필지 DB는 data/seoul_site.db                   │
│   seoul_site.db 를 data 폴더에 넣으세요.        │
│   절차: docs/data_sources.md §0                  │
│   생성기는 docs/install.md 대로 설치하세요.       │
│   ([문서 열기] → install.md)                    │
│                                                │
│   [data 폴더 열기]  [문서 열기]  [다시 확인]      │
└────────────────────────────────────────────────┘
```

- 체크리스트 4행 고정: 필지 DB · 컨텍스트 DB · 생성기 python3(`init_state.generator`) · 키(`sources[api].keys`). 차단은 **필지 DB 없음**과 **생성기 없음**(`generator.ok=false`) — 생성이 아예 불가하므로 경고로 허용할 대상이 아니다. 컨텍스트 DB 없음·키 없음은 헤더 아래 경고 띠(`init_state.warnings`)로만: "지형·건물 DB 없음 — 필지·대상지만 생성됩니다(시트 7~10·12·13 비어 있음)".
- 생성기 행 조치 문장: `generator.text`("python3 없음" / "rhino3dm 없음" 등) + "설치: docs/install.md" + [문서 열기](`open_path {path: paths.install_doc}`). 비개발자 PC의 가장 흔한 첫 실행 실패라 ③까지 가서 'returncode≠0'로 보이게 두지 않는다.
- [다시 확인] = `init` 재전송. 생성기 점검은 세션 캐시이나 [다시 확인]·배지 클릭이면 다시 돈다(≤20 s 타임아웃).

---

## 5. 상태·예외

표시 규칙: 색 + 아이콘(●/○/✓/✗/—/⚠) + 글자 셋을 항상 같이. 오류는 토스트가 아니라 그 자리의 블록(`role=alert`)이고 사라지지 않는다. 성공만 토스트(3초). 경고 스키마는 한 가지(`{level, code, text, action, center}`, §8)이고 어디서 왔든 같은 함수가 그린다.

| 상황 | 어디서 | 표시 | 사용자 동작 | 생성 |
|---|---|---|---|---|
| 필지 DB 없음 | 시작 | 블로커(4.6) | 파일 배치 → [다시 확인] | 차단 |
| 생성기 python3 없음(`generator.ok=false`) | 시작 | 블로커(4.6) ✗ 행 + "설치: docs/install.md" [문서 열기] | 설치 → [다시 확인] | 차단 |
| 컨텍스트 DB 없음 | 헤더 띠 + ② 자료 상태 빨강 행 | "지형·건물 DB 없음 — 필지·대상지만 생성. 시트 7~10·12·13 비어 있음" | 생성 가능. ③ 시트 목록에 "데이터 없음" | 허용 |
| 대상지 반경 안 도엽 미보유(부분/전체) | ② 지도 해치 + 자료 상태 지형 행 + ③ 경고 | "도엽 37705073(북동쪽) 지형 자료 없음 — 그 구역 지형·도로면·건물 층수 보완 빠짐". 전체 미보유면 [생성 시작] 보조문구 "지형 없이 생성" | [▸지도] flyTo | 허용 |
| VWorld 키 없음 | 헤더 배지 회색 + ② 자료 상태 ○ 행 | "VWorld 키 없음 — 건물 최신화 생략, 벌크 기준일(05-09)로 생성" [.env 열기] | `.env` 편집 → ② [다시 확인] 또는 배지 클릭(= `init`, 화면 유지) | 허용 |
| 공공데이터포털 키 없음(`keys.data_go_kr=false`) | 배지 "브이월드만" + ② 자료 상태 키 행 | "공공데이터포털 키 없음 → 철거·말소 반영 생략(건축HUB). `.env`에 `DATA_GO_KR_KEY=` 추가" [.env 열기]. ③ phase detail "건너뜀 — 포털 키 없음(철거 생략)" | 동일 | 허용 |
| 오프라인(키 있음) | ③ phase + 경고 | `refresh` 첫 HTTP 호출이 5 s(`GENERATOR_HTTP_TIMEOUT`, 재시도 0) 안에 실패 → phase "건너뜀 — 네트워크 없음" + 경고 `skipped` "네트워크 없음 — 건물 최신화·철거 반영 생략, 벌크 기준일로 생성". 10~15회 호출을 매달리지 않는다 | — | 허용 |
| 키 무효(`INVALID_KEY`) | ③ phase "건너뜀 — 키 거부" + 경고 | "VWorld 키가 거부됨 — 재발급·재입력. `.env`의 `VWORLD_API_KEY= ` '= ' 뒤 공백을 확인하세요" [.env 열기] | — | 허용(벌크로 계속) |
| 기준일 노랑(경과 ≥ 임계 AND 새 판) | 배지·② 자료 상태·③ 경고 | deliverables §C ⑤ 예문 그대로: "⚠ 건물 자료가 4.9개월 지났습니다(GIS건물통합정보 2026-05-09). 브이월드에서 새 전체본(기준일 2026-09-09)이 확인됨 → data_sources.md §0 절차로 교체하세요" [절차 열기] | 정보 | 허용 |
| 기준일 빨강(경과만) | 동일 | 같은 형식, "새 판 미확인(목록 조회 실패 또는 게시 지연)" | 정보 | 허용 |
| 새 판 조회 실패(오프라인) | — | `newer_date:null` → 노랑 조건 불성립, 빨강만 가능. log.txt에 "새 판 조회 생략" | — | 허용 |
| CRS 자가검사 실패(중앙값 > 0.5 m) | ③ failed | phase ✗ + 오류 카드 "도시계획 레이어가 지적선과 0.8 m 어긋남 — 입력 SHP 좌표계 의심(deliverables §A.3). 개발자에게 알려 주세요" + TRANSFORM 문자열 | [뒤로] | 중단 |
| 높이 추정 비중 큼(A+B < 70 %) | ③ 경고 + 신뢰도 막대 | 노랑 "건물 높이 추정 비중 큼 — 대장 높이·층수(A+B) 61 %. 시트 8·9 여백 카드에 표기됨" | 정보 | — |
| 지적–지형 불일치 의심 n건 | ③ 경고 + ② 지도 마젠타 점 | 회색(정보) "레이어 CTX::QA::cadastre_mismatch(잠금·숨김). 현장 확인 대상" [Rhino](`zoom_view {dir: result.dir, center}`) | 클릭 → Rhino 뷰 이동(Import 후) | — |
| 정합 표본 부족(n < 200) | ③ 신뢰도 | "표본 부족(n=120)" | — | — |
| 건물 0동 | ③ 경고 | 노랑 "반경 안 건물 0동 — 컨텍스트 DB 범위·반경 확인" | — | 허용 |
| 필지 0건 | ③ failed | "반경 안 필지 0건 — 대상지·반경 확인" | [뒤로] | 실패 |
| 베이스맵 프레임 > 범위 | ② [바꾸기] 힌트 + ③ 경고 | 회색 "1:5000 A1 프레임(4.2×3.0 km)이 반경을 넘음 — 가장자리 빈 곳". ② 지도의 프레임 사각형으로 눈으로 확인 | 반경 키우기/축척 변경 | 허용 |
| 1 km 초과 반경 | ② | 회색 힌트 | 정보 | 허용 |
| 다조각·구멍 대상 필지 | ① 칩 ⚠ 배지 | "가장 넓은 조각의 바깥 경계만 씁니다"(CLAUDE.md 규칙) | 정보 | 허용 |
| 검색 0건 | ① 검색줄 아래 | "찾지 못했습니다 — 동 이름까지 적어 보세요" | 재검색 | — |
| 줌 < 17 | ① 지도 칩 | "확대하면 필지가 보입니다" | 줌 | — |
| 필지 5,000건 잘림 | ① 지도 칩 | "일부만 표시 — 더 확대하세요" | 줌 | — |
| 타일 오류 3회 | ① | VWorld → OSM `setUrl` 1회, 속성 표기만 바뀜 | 없음 | — |
| 타일 오류 — 폴백 뒤에도 3회(오프라인) | ①② 지도 칩 | "지도 타일을 못 받음(오프라인) — 필지선만 표시". 더 전환하지 않음. 필지·범위·검색은 로컬 DB라 계속 동작 | 없음 | 허용 |
| 생성 실패(예외, query·terrain·write_3dm 또는 생성기 비정상 종료) | ③ failed | phase ✗ + 오류 카드(요약 · traceback 접힘 · [로그 복사] · 부분 폴더 있으면 [폴더 열기]) | [다시 시도]/[뒤로] | — |
| phase 단위 실패(basemap·sheets·tables 예외) | ③ done | phase ✗ "생성 실패" + 경고 `skipped`(빨강) "베이스맵 레이어 생성 실패" + log. 다음 phase로 계속, 결과는 done. 베이스맵 카드: `basemap.ready=false` → 카드 안 빨강 1줄 "생성 실패 — [log.txt]" + 버튼 비활성. 시트: 전부 `empty` + 사유 "오류". 조서: "CSV 0" | [log.txt] | 허용(부분 결과) |
| 취소 | ③ cancelled | "취소됨 — 3/8까지 완료. 부분 산출물은 폴더에 남아 있습니다(log.txt 끝에 기록)". 취소 직후 자식이 정상 종료해도 `done`은 오지 않는다 | [다시 시도]/[뒤로] | — |
| Import phase 중 취소 시도 | ③ running | [취소]·Esc 비활성 + 툴팁 "문서에 넣는 중에는 취소할 수 없습니다"(Python도 `proc is None`이면 `cancel` 무시) | 기다림 | — |
| 생성 중 창 닫기 | ③ | Python이 서브프로세스 terminate(취소와 같은 경로) | — | — |
| Import 실패(문서 잠김·단위 등) | ③ 문서 카드 | 카드 안 빨강 1줄(`done.context.import_text` 또는 `imported.text`) + 경로 "…/context.3dm — Rhino에서 직접 Import할 수 있습니다" [다시 넣기]. 생성 끝 자동 Import 실패는 `done.context.imported=false`로 와서 `done`만으로 그린다(running 중 `imported`는 무시) | 재시도/수동 | — |
| 다시 넣기 | ③ 문서 카드 | 항상 기존 `CTX` 레이어와 객체 삭제 후 Import(옵션 없음). 버튼 툴팁 "기존 CTX 레이어를 지우고 다시 넣습니다" | — | — |
| .ai 내보내기 전제 미충족 | ③ 베이스맵 카드 | `basemap.ready=false`면 비활성 + 툴팁 "베이스맵 생성 실패". 문서 Import와 무관(DB에서 다시 씀) | — | — |
| .ai 내보내기 실패 | ③ 베이스맵 카드 | 카드 안 빨강 1줄(오류 메시지) + "log.txt 확인" | 재시도 | — |
| 결과 폴더 이미 있음(같은 날 같은 대상지) | ③ | 생성기 시작 시 `sheets/`·`tables/`·`context.3dm`·`context.json`을 지우고 새로 쓴다. `basemap_*.ai`·`log.txt`는 보존(log는 이어 쓰고 구분선). 이전 .ai는 산출물 목록에만 보이고 베이스맵 카드의 ✓ 누적은 이번 세션 `exported`로만 | — | — |
| dirty(③→② 후 옵션 변경) | ③ | 결과 카드 위 띠 "이전 결과 — 설정이 바뀜" | 카드 버튼은 유효 | — |
| 창 폭 < 420 | CSS | 배지 날짜 숨김, 세그먼트 줄바꿈, 스텝퍼 라벨 번호만 | — | — |

---

## 6. 설정·옵션

② 화면에 드러나는 것은 **반경·형태·산출물 4체크**뿐. 나머지는 각 행의 인라인 디스클로저 또는 고급. 모든 값은 바뀔 때마다 `save_prefs`(500 ms 디바운스)로 Python이 `~/.urbansite/prefs.json`에 저장하고 `init_state.options`로 돌려준다.

### 6.1 기본 노출

| 항목 | 키 | 값 | 기본 | 근거 |
|---|---|---|---|---|
| 반경 | `radius` | 300 / **500** / 1000 / 직접(100~2000) | 500 | A.2 |
| 형태 | `shape` | `buffer` / `circle` / `rect` | buffer | A.2 |
| 생성 뒤 현재 문서에 넣기 | `import_after` | 체크 | 켬 | A.5. `context.3dm`은 항상 쓴다(옵션 없음) — .ai는 3dm과 별개로 DB에서 직접 쓴다 |
| 베이스맵 .ai | `make_basemap` | 체크 | 켬 | B |
| 현황도 시트 | `make_sheets` | 체크 | 켬 | C |
| 조서 CSV | `make_tables` | 체크 | 켬 | E |

> **2026-10-13 개정**: 비주얼 토큰(§9)은 `DESIGN.md`(방안지 구성 격자 — 모눈 바탕·1 px 사각 괘선·블루 하나)가 대신한다. 용지 기본은 A3 가로, 시트는 16장(`constants.SHEET_CATALOG`).
> ④ 결과에 '도면' 카드(16장 칸 + [스타일] + .ai)가 생겼고, [스타일]은 결과 안 하위 화면이다: 미리보기(Python이 한 장을 다시 그린 SVG) · 프리셋 · 레이아웃 · 요소 색 10개(범례 행을 누르면 견본 16 + 색 코드 + 직접 고르기) · 단계색 · 선·글자 · 범위 밖 흐리기 · 표제 → [N장에 적용]·[저장]. 생성 전 ③에서는 스타일만 고른다(편집은 결과에서). 레이어 단위 색·선두께는 패널에 없다 — Illustrator에서.

### 6.2 베이스맵 [바꾸기 ▸]

| 항목 | 키 | 값 | 기본 |
|---|---|---|---|
| 용지 | `paper`, `paper_mm` | A1(841×594) / A0(841×1189) / 직접(가로·세로 mm) | A1 |
| 축척(복수) | `scales` | ☐1:1000 ☑1:3000 ☐1:5000 중 1개 이상. **② 프레임 미리보기와 ③ .ai select 기본값에만 쓴다** — 축척별 on/off·선두께는 .ai를 쓸 때 `constants.BASEMAP_SCALE_LAYERS`로. `generate`에 보내지 않고 dirty 판정에서도 뺀다 | [3000] |
| 기본 off 레이어 켜기 | `basemap_layers_on` | `02b_landuse`·`05_road_center`·`11_zoning` 체크 | [] |
| 프레임 중심 | — | 대상지 중심 고정 | — |

프레임이 범위를 넘으면 행 아래 회색 힌트(§5). 지도의 `frameLayer`가 축척마다 사각형을 그린다. 접힌 요약: 비기본값만("A0 · 1:1000·1:3000").

### 6.3 현황도 시트 [고르기 ▸]

체크 13개 + [전체] [없음]. 번호·이름은 deliverables §C: 1 위치·범위 / 2 토지이용현황 / 3 지목 / 4 용도지역 / 5 용도지구·구역 / 6 도시계획시설·지구단위 / 7 건축물 용도 / 8 층수 / 9 노후도 / 10 도로 폭원·위계 / 11 공시지가 / 12 표고 / 13 경사. `preflight_result.empty_sheets`에 든 시트는 체크 옆 회색 "데이터 없음"(비활성 아님 — 생성해도 빈 시트가 나올 뿐). 컨텍스트 DB 자체가 없으면 12·13 비활성 + 사유.

| 키 | 값 | 기본 |
|---|---|---|
| `sheet_ids` | int[] | 1~13 |
| `floor_breaks` | 두 수 | [12, 20] (C #8) |
| `elev_preset` | `"20m"`(서울 2013 10단계) / `"50m"` | 20m (C #12) |

접힌 요약: "13장 전체" / "9장" / "9장 · 표고 50 m".

### 6.4 고급 ▸

| 그룹 | 키 | 값 | 기본 | 근거 |
|---|---|---|---|---|
| 건물 | `include_minor_buildings` | 무벽건물·가건물 포함 | 끔 | A.1 |
| 건물 | `demolished` | 철거 건물 `dashed`(점선·회색) / `exclude` | dashed | A.1 |
| 건물 | `refresh_buildings` | VWorld로 최신화(키 있을 때만 활성) | 켬 | A.5 |
| 건물 | `include_api_objects` | API 유래 객체를 납품물에 포함 | 끔(서면 동의 전) | data_sources §3 |
| 3dm | `include_zoning` | `CTX::Zoning` 도시계획 경계선(용도지역·지구·구역·시설·지구단위) | 켬 | A.1 |
| 3dm | `terrain_vertex_color` | 지형 정점색(표고) | 끔 | 요약 |
| 문서 | `zoom_after_import` | 넣은 뒤 대상지로 줌 | 켬 | — |

고급에 넣지 않는 것(고정, 이유): 원점·단위·좌표계(A.3), 높이 모델 상수(constants.py), 정합 측정(항상), 기준일 임계값(§2.4), 등고선 포함(데스크톱 납품이라 항상, B.4), 기존 CTX 처리(항상 바꾸기), 결과 폴더명(대상지명), 레이어 색·선두께(constants.py). 비개발자가 바꿀 이유가 없고 옵션 하나당 상태·테스트가 는다.

---

## 7. 결과 화면(③ done)

"됐다 → 가져가라 → 믿어도 되나" 순서. 동작 버튼 4개가 첫 780 px 안에.

| 블록 | 내용 | 동작 |
|---|---|---|
| 완료 줄 | ✓ 소요 · 폴더 경로(↗ 클릭 = 폴더) | `open_path {path:dir}` |
| 문서 카드 | 레이어·건물·필지 수. `import_after`면 생성 끝에 자동 Import 되어 "문서에 넣음 ✓"로 시작(`done.context.imported`), 실패면 빨강 1줄(`import_text`) + 경로 + [다시 넣기]; `import_after` 꺼짐이면 [문서에 넣기] 1차 | [대상지로 줌] `zoom_view {dir}` · [다시 넣기]/[문서에 넣기] `import_context {dir}`(항상 기존 CTX·BM 삭제 후). 실패 시 카드 안 빨강 1줄 + 경로 |
| 베이스맵 카드 | 용지 · 레이어 수. 축척 select 1000·3000·5000 고정, 기본값 `options.scales[0]`. `basemap.ready=false`(phase 실패)면 카드 안 빨강 1줄 "생성 실패 — [log.txt]" + 버튼 비활성 | [.ai 내보내기] `export_basemap {dir, scale}` → `busy` → Python이 `context.json`으로 DB에서 다시 `prepare` → `basemap_ai.write_basemap`(축척별 레이어 on/off: 1:1000 = 08·08b on, 1:3000 = 08 on·08b off, 1:5000 = 08·08b off) → `exported` → 카드에 "basemap_3000.ai ✓" 누적(`done.basemap.exported`에 생성 때 쓴 파일이 들어 있고, 같은 경로는 한 번만) + 토스트. `make_basemap` 꺼져 있으면 카드 자체 숨김 |
| 시트·조서 카드 | 시트 n장(빈 m) · CSV 5 | [폴더 열기] · [시트 목록 ▾] → 13줄(번호 · 이름 · 빈 시트는 흐림 + 사유 "지형 없음"), 줄 클릭 = `open_path` OS 기본 앱 |
| 경고 목록 | `done.warnings` 전부. 아이콘·1줄 · ▸ 펼치면 조치 문장 + action 버튼(절차 열기/.env 열기). `center` 있으면 [Rhino] = `zoom_view {dir: result.dir, center}`(Import 전 비활성). 0건이면 "경고 없음" 회색 1줄 | 펼침·이동 |
| 신뢰도 | 높이 출처 누적 막대(대장/층수/지형도/기본 — 회색 명도 4단 + 수치) · 정합 중앙값·p90·n(표본 부족 표기) · 건너뜀 건수 · 자료기준 1줄(§C ① 요약) | [log.txt] `open_path` |
| 산출물 목록 | `<details>`: 파일명 · 크기, 클릭 = `open_path` | — |
| 푸터 | [옵션 바꿔 다시](→ ②, 대상지·결과 유지) · [새 대상지 →](→ ①, 초기화) | — |

.ai 내보내기를 생성에 자동 포함하지 않는 이유: `_-Export`는 UI 스레드에서 뷰·선택 상태를 바꾸고 축척마다 수 초 멈춘다. 사용자가 보는 앞에서 축척을 고르고 누르는 쪽이 안전하고, 축척 추가가 3dm 재생성 없이 된다 — 그래서 생성 시 축척을 고르게 하지 않는다(B.2의 축척별 차이는 전부 Export 시점의 레이어 on/off·선두께).

---

## 8. 메시지 계약(요약 — 원본은 `docs/panel_ui.md`)

네이밍은 CLAUDE.md: 대지 `lot`, 요소 `building`·`road`·`terrain`·`water`·`green`·`rail`, 베이스맵 `basemap`, 현황도 한 장 `sheet`, 수치지형도 도엽 `topo_sheet`(`estimate.topo_have/topo_total`·`coverage.missing[].topo_sheet`·`extent_geojson` role=`topo_sheet`). m·㎡ 접미사 없음. 좌표는 WGS84 `[lng, lat]`.

| cmd | → 푸시 | 쓰는 곳 |
|---|---|---|
| `init` | `init_state` | 창 열림 · [다시 확인](블로커·② 자료 상태) · 배지 클릭 — 셋 다 같은 명령. 첫 수신만 ①로, 이후는 배지·띠·블로커·자료 상태만 갱신 |
| `search {query}` | `search_result` | ① |
| `map_lots {bbox, seq}` | `map_lots {seq}` | ① 줌 ≥ 17 |
| `select_lots {pnus}` | `lot_state` | ① 클릭·검색·최근·✕ |
| `preflight {pnus, radius, shape, paper, paper_mm, scales, seq}` | `preflight_result {seq}` | ① lots 변경 · ② 진입·옵션 변경 |
| `generate {pnus, options}` (`options.scales` 제외) | `progress`* · `log`* · (`busy`·`imported` — running 중 무시) · `done` | ② [생성 시작] · ① [바로 생성] · ③ [다시 시도] |
| `cancel` | `progress {state:"cancelled"}` (Import 중·이미 종료면 무시) | ③ running(phase≠import) |
| `import_context {dir}` | `busy` · `imported` | ③ 문서 카드 |
| `export_basemap {dir, scale}` | `busy` · `exported` | ③ 베이스맵 카드 |
| `zoom_view {dir, center?}` | — | ③ (JS가 `result.dir`을 붙인다) |
| `open_path {path}` | (`error`) | 폴더·파일·문서·.env 전부 |
| `save_prefs {options}` | — | ② 변경 시 |

경고 스키마(`init_state.warnings`·`preflight_result.warnings`·`done.warnings` 공통):

```jsonc
{"level":"info|warn|danger", "code":"stale_building|coverage|no_api_key|invalid_key|height_estimate|mismatch|skipped|no_context_db|empty|frame_over",
 "text":"한 줄", "detail":"조치 문장(§5)", "action":{"label":"절차 열기","path":"docs/data_sources.md"}, "center":[lng,lat]}
```

---

## 9. 비주얼 토큰

중립 회색 + 패널 강조 1색. 지도 위 도형은 **별도 토큰**(타일의 파랑 수계·녹색 공원·흰 도로 위에서 튀는 색을 따로 고른다 — 패널 accent 파랑은 VWorld 수계색과 겹친다).

```
패널
--bg        #f5f6f7   창 바탕
--surface   #ffffff   카드·입력
--border    #e3e6ea
--ink       #1c2128   본문
--sub       #6b7480   보조·캡션 (bg 위 4.6:1)
--muted     #a0a7b1   비활성 글자·빈 원 (3:1, 읽혀야 하는 비활성은 sub)
--accent    #2f6fed   선택 테두리·링크·진행 막대·스텝퍼
--accent-dn #1f55c4   채운 1차 버튼(흰 글자 6:1)
--accent-bg #e9f0fd   선택 배경
--ok        #1f7a4d   ✓
--warn      #b4600a   노랑 경고 글자 (배경 #fff4e5)
--danger    #c43c3c   빨강 경고 글자 (배경 #fdeaea)
막대 톤(높이 출처): #3b4452 / #6b7480 / #a0a7b1 / #d5d9de — 색 아님, 명도 4단

지도
--map-lot      #6b7480  주변 필지 선 1 px 40 %, 채움 투명(fillOpacity .01 — 히트용)
--map-target   #d8322d  대상지 선 2 px + 채움 30 %  (타일 위에서 유일하게 튀는 색)
--map-extent   #1c2128  범위 선 1.5 px 점선 "6 4" + 채움 5 %, 라벨 "500 m"
--map-topo     #5c5c58  도엽(topo_sheet) 경계 점선 1 px + 번호 라벨; 미보유는 SVG pattern 사선 해치 (#5c5c58 35 %) + "지형 없음"
--map-frame    #2f6fed  베이스맵 프레임 실선 1 px + "A1 1:3000"
--map-qa       #d400d4  불일치 의심 점 r=4 (3dm QA 레이어색과 동일)

타이포 (Pretendard 인라인; 폴백 -apple-system, "Apple SD Gothic Neo", "Malgun Gothic", sans-serif)
제목·완료 줄            16 / 600 / 1.3
섹션 제목               13 / 600 / 1.4, 위 12 아래 8
본문·입력·버튼          13 / 400 / 1.5
보조(캡션·배지·로그)     12 / 400 / 1.5 — 하한
큰 숫자(합계·%)          20 / 600 / 1.2, tabular-nums
등폭(로그·경로·PNU)     "SF Mono", Menlo, Consolas, monospace 12

간격·형태
4 px 그리드. 좌우 패딩 16. 카드 패딩 12, 카드 간격 12, 섹션 간격 12.
행 높이: 입력·버튼 36, 칩·목록 행 32, 자료 상태 행 24(펼친 조치 문장은 별도 줄), 터치 목표 최소 36(클릭 목표는 행 전체).
모서리 6(카드·입력), 999(세그먼트·칩·배지). 그림자 없음 — border 1 px와 bg/surface 대비만.
세그먼트 선택 = accent 1.5 px + accent-bg. 1차 버튼 accent-dn 채움. 2차 surface + border. 위험(제외·지움)은 글자만 danger.
포커스 링 2 px accent 바깥선(offset 2), 마우스·키보드 구분 없이 항상.
경고 띠: 좌측 3 px 보더만 색, 배경 틴트. 회색 정보 띠는 muted.
```

---

## 10. 접근성·키보드

| 키 | 어디서 | 동작 |
|---|---|---|
| (창 열림) | — | 검색줄 자동 포커스 |
| `/` | 입력 중 아닐 때 | 검색줄 포커스·전체 선택 |
| `Enter` | 검색줄 | 검색. 목록 열려 있으면 선택 |
| `↓ ↑` | 검색줄·목록 | 이동. 빈 검색줄에서 ↓ = 최근 대상지 |
| `⌘/Ctrl+Enter` | 어디서나 | 현재 단계 1차 동작(① 바로 생성 가능하면 바로 생성, 아니면 다음 / ② 생성 시작 / ③ done 새 대상지) |
| `Esc` | 목록·디스클로저 / ③ running | 닫기 / 취소(확인 없음 — 부분 폴더가 남고 재실행이 쉽다) |
| `Alt+← / →` | ①②③ | 뒤로 / 다음 |
| `⌫` | 칩 포커스 | 그 필지 제거 |
| `Tab` 순서 | — | 배지 → 스텝퍼(활성만) → 본문(검색 → 목록 → 지도 건너뜀 `tabindex=-1` → 칩…) → 푸터 |

- 스텝퍼 `<ol>` + `<button>`, 현재 `aria-current="step"`. 단계 전환 시 본문 `h2[tabindex=-1]`로 포커스 이동.
- 세그먼트 `role=radiogroup` + 숨긴 `<input type=radio>`(←→ 공짜). 체크·select·details 전부 네이티브.
- 지도 클릭은 키보드로 못 한다 → 검색·최근 목록으로 같은 결과. 후보 목록 `role=listbox`.
- 진행률 `role=progressbar aria-valuenow`, 현재 phase 1줄 `aria-live=polite`, 오류 카드 `role=alert`, 로그는 live 아님. ③ done 진입 시 "생성 완료, 경고 3건" 1회 낭독.
- 색만으로 상태를 전하지 않는다. 대비: 본문 4.5:1 이상, 보조 4.6:1.
- 고정 높이는 지도에만. 창 리사이즈·⌘+ 확대에 레이아웃이 깨지지 않는다.

---

## 11. 구현 메모

### 11.1 JS 구조(파일 1개, ≈1,000줄)

```js
const state = { step: 1, run: "idle", blocked: false, dirty: false,
  lots: [], lotState: null,                 // lot_state 그대로
  options: {},                              // init_state.options → 사용자 변경
  preflight: null, progress: null, result: null,
  seq: { map: 0, preflight: 0 } };

function go(step) { state.step = step; render(); }          // step 전환 때만 호출
function render() {                                           // 섹션 innerHTML 재렌더는 여기서만
  document.body.dataset.step = state.step; document.body.dataset.run = state.run;   // CSS가 hidden·disabled·버튼 라벨 처리
  renderHeader(); renderFooter();
  ({1: renderLots, 2: renderOptions, 3: renderResult})[state.step]();
  placeMap();                                // step 1·2에서 지도 컨테이너 이동 + invalidateSize
  document.querySelector(`section[data-step="${state.step}"] h2`).focus();
}
function setRun(run) { state.run = run; document.body.dataset.run = run; renderFooter(); }   // 섹션 재렌더 없음
window.app = { receive(msg) { handlers[msg.type]?.(msg); } };
```

- **섹션 `innerHTML` 재렌더는 step 전환(`go`) 때만.** 푸시 핸들러는 슬롯 요소만 교체한다: `preflight_result`→`#estimate`·`#data_status`·지도 레이어 / `progress`→`#phase_list`·progressbar 속성·[취소] 활성 / `log`→`<pre>` append / `lot_state`→`#lot_chips`·합계 / `init_state`(두 번째부터)→`#badges`·`#menu`·블로커 / `done`→③ 섹션 1회 렌더(`go(3)`와 같음) / `imported`·`exported`→카드 안 슬롯. 반경 직접 입력 중 300 ms 뒤 `preflight_result`가 와도 포커스·커서·IME 조합(한글 검색줄)·열린 `<details>`·로그 스크롤 위치가 보존된다 — 옵션 입력은 네이티브 폼 요소라 값 보존 코드가 없다. 가상 DOM·컴포넌트 없음. 이벤트는 섹션별 위임 1개.
- CSS: `body[data-run="running"] section[data-step="1"], …[data-step="2"] { pointer-events:none }` + `fieldset[disabled]`. 스텝퍼 `canGo(step) = step <= maxReached && run !== "running"`.
- 옵션 변경 → `state.options` 갱신 → `save_prefs`(500 ms) + ②면 `preflight`(300 ms) + `run==="done"`이면 `dirty=true`.
- 경고 렌더 함수 하나 `renderWarnings(list, slot)`. 오류 푸시는 `error.context`로 슬롯(`generate`·`import`·`export`·`search`·`select`·`open`·`init`)을 골라 그 자리에 블록, 모르는 context는 헤더 아래 띠.

### 11.2 Leaflet

- 인스턴스 1개(`preferCanvas:true`, 줌 컨트롤 우하단). DOM 컨테이너 `#map`을 `#map_slot_1`(①) ↔ `#map_slot_2`(②) 사이에서 `appendChild`로 옮기고 `invalidateSize()`. `map.remove()` 금지.
- 레이어: `tiles`(VWorld, `tileerror` 3회면 OSM `setUrl` 1회; 폴백 뒤에도 3회면 지도 위 칩 "지도 타일을 못 받음(오프라인) — 필지선만 표시" 후 더 전환 없음) · `lotsLayer`(①만, moveend마다 교체) · `targetLayer` · `extentLayer` · `topoLayer`(도엽) · `frameLayer` · `qaLayer`. 클릭 핸들러는 `lotsLayer`에만.
- ② 진입: `lotsLayer` 숨김, `fitBounds(extent ∪ frame)`. 원·사각형은 `preflight` 응답 전에도 JS가 `L.circle`/`L.rectangle`로 즉시, 버퍼는 응답(≤100 ms)으로 교체.
- 해치는 `<svg><pattern>` 1개를 문서에 두고 `fillPattern` 대신 Leaflet SVG 렌더러 path에 `fill: url(#hatch)` — `topoLayer`만 SVG 렌더러(`renderer: L.svg()`), 나머지는 캔버스.

### 11.3 긴 작업·진행률 (2026-10-07 개정 — code_map.md 확정: 서브프로세스 없음)

> **개정**: 생성은 Rhino CPython 안에서 `context_builder.run(request, progress, doc)`을 UI 스레드에서 동기 호출한다. 진행률은 콜백 안 `host.push` + `Rhino.RhinoApp.Wait()`로 펌핑, 취소는 플래그 → 콜백 False → 엔진 중단·되돌림. 생성기 python3 블로커 행은 항상 ✓(없어도 됨), `generate` 페이로드에 `scales` 포함, phase `import`는 항상 '건너뜀 — 베이크로 대체'. 아래 원문은 서브프로세스 시절 기록이라 `docs/panel_ui.md`가 우선한다.


- 생성은 Rhino 밖 python3 서브프로세스(deliverables A.5). 컨트롤러가 `subprocess.Popen(stdout=PIPE)`로 띄우고 자식은 **stdout에 JSON 1줄씩**(`{"progress":…}` / `{"log":…}`). Eto `UITimer`(200 ms)가 비차단으로 읽어 그대로 푸시. WebView는 멈추지 않는다.
- 자식이 끝나면 `context.json`을 읽어 `done`을 조립. `import_after`면 그 직전에 `busy on` → `_-Import`(UI 스레드 수 초) → 결과를 `done.context.imported/import_text`에 → `busy off` → `done`. 이 구간은 `proc=None`이라 `cancel`이 무시된다(JS도 [취소] 비활성).
- 생성기 시작 시 `sheets/`·`tables/`·`context.3dm`·`context.json` 삭제 후 새로 씀(`.ai`·`log.txt` 보존). phase 단위 예외(basemap·sheets·tables)는 `failed` + 경고 `skipped` + log 후 계속, 결과는 `done`. HTTP는 `GENERATOR_HTTP_TIMEOUT` 5 s·재시도 0, 첫 실패면 `refresh` 통째로 skipped.
- 취소·창 닫기 = `cancel_requested` 플래그 + `proc.terminate()`. 플래그가 서 있으면 자식이 정상 종료해도 `done`을 조립하지 않는다. 부분 폴더는 두고 `log.txt` 끝에 "cancelled".
- 생성기 python3 유무는 `init`이 `GENERATOR_PYTHON -c "import geopandas, shapely, numpy, rhino3dm"`로 점검(세션 캐시, [다시 확인]이면 재실행) → `init_state.generator`. 없으면 블로커.
- `export_basemap`·`import_context`도 UI 스레드. `busy` 푸시 → `AsyncInvoke`로 작업 예약(busy가 먼저 그려지도록).

### 11.4 preflight(Rhino 안, 100 ms급)

- 범위 폴리곤: `buffer` = 대상지 합집합 바깥 경계 `PolylineCurve.Offset(Plane.WorldXY, radius, tol, CurveOffsetCornerStyle.Round)`(RhinoCommon, 문서 불필요). `circle`·`rect` = 중심+반경 산술. python3 테스트 환경(RhinoCommon 없음)에서는 bbox 둥근 사각형으로 폴백.
- 도엽 교차: 컨텍스트 DB의 도엽 목록(도엽번호·bbox·제작연도, `data_sources.md`의 `sheets.csv` 적재분)과 범위 bbox 교차(stdlib). 보유/미보유 + 빠진 방향(범위 중심 기준 8방위).
- 예상치: 범위 bbox로 `buildings` COUNT(인덱스 컬럼 `min_x/max_x/min_y/max_y`), 초 = `3 + buildings/60`, MB = `buildings/230`(07 §8 규모 감에서 역산, constants).
- 빈 시트: 범위 bbox에 해당 테이블 행이 0이면 그 시트 id.
- 기준일: `data_sources`·컨텍스트 DB `source_files`에서 기준일 → 경과 개월 → §2.4 임계. 새 판은 `~/.urbansite/source_news.json`(init이 띄운 비차단 체크 서브프로세스가 쓴 캐시, 1일 유효)에서 읽는다.
- 결과를 `(tuple(pnus), radius, shape, paper, tuple(paper_mm), tuple(scales))` 키로 메모이즈(`paper_mm`이 빠지면 용지 '직접'에서 가로·세로를 바꿔도 프레임·frame_over가 안 바뀐다). `init`마다 비운다(키 유무·새 판 캐시는 키에 없으므로). `seq` 에코.
- 새 판 캐시 `source_news.json`은 체크 서브프로세스(stdlib urllib, Rhino CPython으로 실행)가 tmp에 쓰고 `os.replace`하므로 읽는 중 깨진 JSON이 없다.

### 11.5 성능·크기

- `map_lots` GeoJSON 소수 7자리·최대 5,000건(기존 `review_map.get_parcels_in_bbox`). 줌 17 조건으로 실측 1~2천 건.
- `preflight_result.extent_geojson`은 수 KB. 썸네일·SVG 푸시 없음.
- 로그 400줄 상한.
- `prefs.json`은 사용자 홈(`~/.urbansite/`) — 저장소를 더럽히지 않고 WebView `localStorage`에 의존하지 않는다.

### 11.6 개발 보조

- `site_ui.html?mock=1`로 브라우저에서 열면 `send()`가 콘솔에 찍고 `receive`에 샘플 JSON(`init_state`·`lot_state`·`preflight_result`·`progress`·`done`)을 순서대로 흘려 넣는 20줄 목. Leaflet·폰트는 `<!--VENDOR_*-->` 자리라 목 모드에서는 `scripts/vendor/` 상대 경로 `<link>`/`<script>`를 JS가 삽입.
- `tests/test_site_ui_contract.py`: `init_state`·`preflight_result`·`done` 샘플(컨트롤러의 조립 함수가 만든 dict)이 `docs/panel_ui.md` 키 집합을 갖는지 unittest 1개. python3로 돈다.

### 11.7 기존 자산 재사용

- `review_map.py`(타일 설정·bbox 필지·GeoJSON) 그대로. `panel_host.py` 브리지(`bridge:flush` + title 이벤트, `__flush`, AsyncInvoke) 그대로 — 바뀌는 건 명령·푸시 이름뿐. `lot_db.load_parcels_in_bounds`·`pnu_loader.search_lots` 재사용.
- 새 Python: `preflight` 로직(stdlib + RhinoCommon 오프셋), 생성기 드라이버(`dev_*`, 별도 python3), 새 판 체크(`dev_check_sources.py`, stdlib만 — Rhino CPython으로 실행), 베이커 함수 3개(Import·Export·줌), `prefs`·`source_news` 읽기쓰기, `constants`에 `GENERATOR_PYTHON`·`GENERATOR_HTTP_TIMEOUT`·`BASEMAP_SCALE_LAYERS`·`INSTALL_DOC` 추가.

---

## 12. 남는 약점·대안

| 약점 | 영향 | 완화·대안 |
|---|---|---|
| ③에서 지도가 없다 | 결과 범위·QA 점을 패널에서 보려면 ②로 가야 한다 | ③의 경고 [Rhino]가 Rhino 뷰로 보낸다 — 이 툴의 확인 장소는 뷰포트. ②로 돌아가면 `qaLayer`가 그려져 있다 |
| ② 지도 240 px가 범위 1 km·프레임 4.2 km를 한 화면에 담기엔 작다 | 축소하면 대상지가 점 | `fitBounds` 패딩 + 창 세로를 늘리면 지도가 먹지는 않는다(②는 여백이 먹음). 불만이 나오면 ②도 지도가 늘어나게 CSS 한 줄 |
| ②는 스크롤이 생긴다(기본 ≈700, warn 여러 행·[바꾸기 ▸]·힌트가 열리면 780 초과) | 자료 상태 아래쪽이 가려질 수 있다 | ok 행 접기·행 24·섹션 간격 12로 기본 상태는 한 화면. 푸터 [생성 시작]은 고정이라 스크롤과 무관. 경고 행은 위쪽(산출물 아래)이라 먼저 보인다 |
| preflight가 RhinoCommon 오프셋에 기댄다 | python3 테스트는 폴백 경로만 검증 | 오프셋 실패(자가교차 등) 시 bbox 둥근 사각형으로 폴백하고 log |
| 새 판 조회가 캐시 기반이라 당일 첫 실행에서는 노랑이 안 뜰 수 있다 | 빨강(경과만)은 뜬다. 생성기가 조회해 `done.warnings`에는 반영 | 캐시 1일. 수동 [다시 확인]으로 재조회 |
| [바로 생성]이 "경고 없을 때만"이라 노출 조건이 보이지 않는다 | 사용자가 왜 어떤 날은 있고 어떤 날은 없는지 모른다 | 숨기지 않고 비활성 + 툴팁 "자료 상태 경고가 있어 ②에서 확인 후 생성"으로 바꿀 수 있음 — 써 보고 결정 |
| .ai 축척마다 버튼을 눌러야 한다 | 축척 3개면 3번 | 각 수 초. 자동 연쇄는 UI 멈춤·실패 연쇄 때문에 뺐다. 요청 오면 "전부 내보내기" 버튼 1개 추가 |
| 같은 날 같은 대상지 재생성은 `sheets/`·`tables/`·3dm을 지우고 다시 쓴다 | 이전 생성의 .ai는 남는다(사용자가 만든 것). Illustrator가 .ai를 열어 둔 상태면 Export 쓰기 실패 가능 | 이전 .ai는 산출물 목록에만 보이고 카드 ✓는 이번 세션 `exported`로만. Export 실패 1줄로 보인다. `_2` 접미는 E 규약에 없어 안 넣는다 |
| 구현량 ≈1,000줄 JS + preflight·베이커·드라이버 | 1인 개발 1~2주 | 썸네일·드래그·드로어·save_api_key를 뺀 결과. 더 줄이려면 ② 지도를 먼저 뺀다(SVG 미니맵으로 후퇴) |

## 검토 반영

2026-10-07 검토 13건 반영. 명령·푸시 표는 `docs/panel_ui.md`와 같다.

- [high] 생성기 python3: `init_state.generator{ok, python, text}` 추가. 블로커 4행(필지 DB · 컨텍스트 DB · 생성기 python3 · 키), 생성기 없음은 필지 DB와 같은 급으로 차단. 조치 = `docs/install.md` + [문서 열기]. `dev_check_sources.py`는 stdlib만 써 Rhino CPython으로 돈다.
- [high] `make_context` 삭제(옵션 20개). `context.3dm`은 항상 쓴다. ② 첫 행 = '[✓] 생성 뒤 현재 문서에 넣기'(`import_after`). §6.1 표·§4.4 phase 문구에서 `write_3dm`을 꺼지는 phase에서 제외.
- [high] `zoom_view {dir, center?}` — §5·§7·§8에서 JS가 `result.dir`을 붙인다.
- [medium] 배지 클릭 = `init` 하나(이동 없음). ② 자료 상태 제목 옆 [다시 확인]. 두 번째 `init_state`는 배지·띠·블로커·자료 상태만 갱신(§3.2 규칙). Python은 `init`마다 preflight 메모이즈를 비운다.
- [medium] 부분 실패: phase 단위 예외 → ✗ + 경고 `skipped` + log, 결과는 done(§4.4·§5). `basemap.ready=false` 카드 표현, 시트 `reason:"오류"`, `done.context.import_text`로 Import 실패를 `done`만으로 그림(running 중 `imported` 무시).
- [medium] 오프라인: `GENERATOR_HTTP_TIMEOUT` 5 s·재시도 0, 첫 실패면 `refresh` skipped "건너뜀 — 네트워크 없음"(§5 '오프라인(키 있음)' 행). 타일 폴백 뒤에도 3회면 칩 "지도 타일을 못 받음(오프라인) — 필지선만 표시". 새 판 캐시는 tmp → `os.replace`.
- [medium] preflight 메모 키 `(tuple(pnus), radius, shape, paper, tuple(paper_mm), tuple(scales))`(§11.4).
- [medium] 재생성 시 `sheets/`·`tables/`·`context.3dm`·`context.json` 초기화, `.ai`·`log.txt` 보존. `done.basemap.exported`는 빈 배열로 시작, 이 세션 `exported`로만 누적(§5·§7·§12).
- [medium] 키 2종: `sources[api].keys{vworld, data_go_kr}`, 배지 "키 2/2"/"브이월드만", §5에 '공공데이터포털 키 없음' 행, `.env` 템플릿 두 줄, phase detail "철거 n동 반영"/"건너뜀 — 포털 키 없음".
- [medium] 도엽 = `topo_sheet`(§8 네이밍·§4.3 `topoLayer`·§9 `--map-topo`). 현황도 `sheet`와 분리.
- [medium] ② 스크롤 전제로 고침(§3.1·§4·§4.3 높이 예산 ≈700). 자료 상태 행 28→24, 섹션 간격 20→12, ok 행 접힘 1줄.
- [medium] `render()`는 step 전환 때만 섹션 재렌더, 푸시 핸들러는 슬롯만 교체(§11.1).
- [medium] `scales`는 ② 프레임·③ select 기본값 전용, `generate`에 안 보내고 dirty 판정 제외(§6.2·§7). ③ select 1000·3000·5000 고정. Export 축척별 레이어 표·`_NC` 제외 명시.
- [medium] 취소 경합: Import phase·busy 중 [취소] 비활성 + 툴팁(§4.1·§4.4·§5). Python은 `proc is None`이면 무시, `cancel_requested`면 `done` 조립 안 함(§11.3).
