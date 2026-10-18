# "대지검토" 패널 UX/UI 스펙 — 안 A: 단일 화면 전문가 접근

- 작성일: 2026-10-07. 근거: `docs/deliverables.md`(요약·A.2·A.4·B·C 공통·E), `docs/data_sources.md` §0·§2.4, `CLAUDE.md`.
- 대상: Rhino 8 Eto WebView 창 480×900(크기 조절 가능, 도킹 불가), 단일 HTML + 바닐라 JS + Leaflet 1.9.4 + Pretendard(전부 인라인, 오프라인).
- 경쟁 안과의 차이: 탭·마법사 없이 **스크롤 한 장의 폼**. 대상지 → 범위 → 산출물 → 실행 → 결과가 위에서 아래로 한 번에 보이고, 두 번째 실행부터는 **검색줄에 지번 입력 → Enter → ⌘Enter** 세 동작으로 끝난다.

---

## 1. 요약 — 설계 원칙

1. **한 장**: 화면 전환·탭·모달 없음. 유휴 상태에서 900 px 안에 입력 전부가 들어가고, 결과·로그만 아래로 자란다.
2. **반복 속도**: 모든 옵션은 마지막 값을 기억(`prefs`)하고, 두 번째부터는 대상지만 바꿔 실행한다. 키보드만으로 검색→선택→실행이 된다.
3. **다 보이되 작게**: 옵션을 숨기지 않는다. 대신 한 줄에 한 산출물, 세부 옵션은 그 줄 안의 작은 컨트롤(세그먼트·select·체크)로 눌러 담는다.
4. **경고는 결과 카드에 한 번**: 기준일·정합·높이 추정·데이터 없음·키 없음은 등급(빨강/노랑/회색)과 **다음 행동 한 줄**을 붙여 결과 카드 상단에 모은다. 생성은 막지 않는다(CRS 자가검사 실패만 중단).
5. **상태는 5개**: `idle · ready · running · done · error`. 이 밖의 "모드"는 없다(도로 지정 모드 같은 것 없음 — 이 툴은 접도 판정이 없다).

---

## 2. 사용자·과업 (jobs-to-be-done)

| 사용자 | 상황 | 하고 싶은 일 | 성공 기준 |
|---|---|---|---|
| 도시설계자(비개발자) | 착수 회의 전날, 대상지 주소만 받음 | 반경 500 m 3D 컨텍스트를 Rhino 문서에 넣고 현황도 13장·조서를 폴더에 받는다 | 지번 입력 후 1분 안에 Rhino에 모델이 들어오고 result 폴더가 열린다 |
| 건축사 | 합필 검토, 필지 3~4개 | 지도에서 필지를 눌러 대상지를 묶고 범위를 300 m로 좁혀 빠르게 뽑는다 | 클릭으로 합필, 합계 면적이 바로 보임, 300 m는 수 초 |
| 둘 다 | 어제 뽑은 대상지를 반경만 바꿔 다시 | 설정 그대로 두고 반경만 1 km로 | 최근 대상지 선택 → 반경 클릭 → ⌘Enter |
| 둘 다 | 결과를 받았는데 뭔가 이상함(층수가 낮다, 도로가 어긋난다) | 왜 그런지(높이 추정 비중, 정합 오차, 기준일)와 어떻게 할지(DB 교체, 키 입력)를 안다 | 결과 카드의 경고 한 줄 + 로그에서 PNU·건물 id까지 추적 |
| 둘 다 | 베이스맵을 일러스트에서 열어야 함 | Rhino 레이어 → .ai 내보내기를 버튼 하나로 | Top 뷰·레이어 보존·mm 단위가 자동 |
| 개발자(1인) | 처음 설치, DB가 아직 없음 | 무엇이 없고 어디서 받는지 | DB 없음 배너 + 문서 §0 열기 |

하지 않는 일: 규모검토·자동배치·접도/도로 지정·일조. 지도는 **대상지 고르기 전용**이다.

---

## 3. 정보구조(IA)와 화면 흐름

### 3.1 IA — 세로 한 장, 5블록

```
헤더(고정)     제목 · DB 기준일 배지 · API 키 배지
① 대상지       검색줄(+최근 5건) → 지도(압축, 확대 토글) → 대상 칩 + 합계 면적
② 범위         반경 세그먼트 + 직접 입력 · 형태 세그먼트
③ 산출물       4줄: 3D 컨텍스트 / 베이스맵 .ai / 현황도 시트 / 조서 CSV — 줄마다 세부 옵션
실행 바(고정)   [대지검토 실행 ⌘↵] · 상태 1줄(진행률/결과 요약)
④ 결과         결과 카드(경고·수치·액션) → 로그(접힘)
```

고정(sticky) = 헤더와 실행 바. 가운데 ①~④만 스크롤. 유휴 상태 총 높이 ≈ 860 px이라 900 px 창에서는 스크롤이 거의 없고, 창을 1200 px로 키우면 지도가 남는 세로를 가져간다(`flex: 1 1 auto; min-height: 240px`).

### 3.2 상태 전이

```
            init_state(DB ok)                 select → targets≥1
 [boot] ───────────────────────▶ [idle] ──────────────────────────▶ [ready]
   │                               ▲  ◀──────────────────────────────┤  (targets=0)
   │ init_state(db_missing)        │                                  │ run (⌘↵)
   ▼                               │                                  ▼
 [blocked]  배너 + 폼 비활성       │   done(status=ok|partial)   [running]  진행률·취소
   (DB 넣고 "다시 확인")           │  ◀────────────────────────────┤
                                   │                                  │ done(status=failed) / error
                               [done] ──── 입력 변경 ──▶ [ready]      ▼
                                 ▲   (결과 카드는 '이전 결과'로 흐려짐) [error] ── 입력 변경/재실행 ──▶ [ready]/[running]
                                 └── import/export/open_* 는 상태를 바꾸지 않음(카드 안 버튼 상태만)
```

- `running` 동안 ①②③은 `<fieldset disabled>`, 실행 버튼은 **[취소]**로 바뀐다.
- `done` 뒤 입력(대상지·반경·옵션)을 바꾸면 결과 카드에 "이전 결과 — 설정이 바뀜" 띠를 얹고 액션 버튼은 그대로 둔다(폴더 열기 등은 여전히 유효).
- `blocked`는 DB 없음일 때만. API 키 없음·기준일 경과는 **배지와 경고**일 뿐 상태가 아니다.

### 3.3 기본 흐름(첫 사용)

1. Rhino 명령 `Gorani` → 창 뜸 → `init` → `init_state`(타일·지도 초기 위치·DB 기준일·키 유무·prefs).
2. 검색줄에 "성수동2가 277-17" Enter → `search_result` 1건이면 즉시 대상 추가 + 지도 flyTo; 여러 건이면 검색줄 아래 목록(↑↓ Enter).
3. 지도에서 옆 필지 클릭 = 합필 토글. 칩 × = 제거.
4. 반경·산출물은 기본값(500 m·버퍼·전부 체크) 그대로.
5. ⌘Enter → `run` → 진행률 → `done` → 결과 카드(자동 Import 완료, 폴더 열림 옵션).

두 번째부터: 검색줄 포커스(창 열릴 때 자동) → 지번 → Enter → ⌘Enter.

---

## 4. 와이어프레임(480×900)과 컴포넌트

### 4.1 유휴·ready 상태 (전체)

```
┌──────────────────────────────────────────────────────────┐ y=0
│ 대지검토            필지 2026-05-13 · 건물 2026-09-09 · 키 ✓ │ 헤더 36 (sticky)
├──────────────────────────────────────────────────────────┤
│ ① 대상지                                                  │
│ ┌──────────────────────────────────────────────┐ ┌─────┐ │
│ │ 🔍 주소 · 지번 · PNU                    ⌄최근 │ │검색 │ │ 36
│ └──────────────────────────────────────────────┘ └─────┘ │
│ ┌──────────────────────────────────────────────────────┐ │
│ │                                                      │ │
│ │                                                      │ │
│ │                 지도 (Leaflet, 캔버스)               │ │ 260
│ │           줌<17: "확대하면 필지가 보입니다"          │ │  (창 늘리면 자람)
│ │                                                      │ │
│ │                                           [+][−][⤢] │ │
│ └──────────────────────────────────────────────────────┘ │
│ ● 성수동2가 277-17 ×   ● 277-18 ×        합계 1,234.5 ㎡  │ 칩 32
│──────────────────────────────────────────────────────────│
│ ② 범위   [300][500][1000][  750 ] m    형태 [버퍼][원][사각] │ 36
│──────────────────────────────────────────────────────────│
│ ③ 산출물                                                  │
│ ☑ 3D 컨텍스트     생성 뒤 문서에 넣기 ☑ · 철거건물 [점선 ⌄]  │ 32
│                   무벽·가건물 포함 ☐ · 지형 정점색 ☐        │ 24
│ ☑ 베이스맵 .ai    용지 [A1 ⌄]  축척 ☑1:1000 ☑1:3000 ☑1:5000 │ 32
│ ☑ 현황도 시트     13/13 장  [고르기 ⌄]                      │ 32
│ ☑ 조서 CSV        필지 · 건물 · 시트집계 · 높이출처 · 정합  │ 24
│ ☐ 완료 뒤 result 폴더 열기                                 │ 24
│──────────────────────────────────────────────────────────│
│ ④ 결과                                                    │
│   아직 결과가 없습니다. 대상지를 고르고 ⌘↵ 로 실행하세요.    │ 빈 상태 48
│ ▸ 로그 (0줄)                                               │ 24
│                                                          │
├──────────────────────────────────────────────────────────┤
│ [        대지검토 실행   ⌘↵        ]  대상 2필지 · 500 m   │ 실행 바 56 (sticky)
└──────────────────────────────────────────────────────────┘ y=900
```

### 4.2 running 상태 (④와 실행 바만 바뀜)

```
│ ④ 결과                                                    │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ 3/7 건물 높이 계산 … 1,812동                         │ │
│ │ ████████████░░░░░░░░░░░░░░░░░░░░░░  38 %   00:07     │ │
│ └──────────────────────────────────────────────────────┘ │
│ ▾ 로그 (41줄)                                              │
│   12:03:41 필지 bbox 질의 2,318건                          │
│   12:03:42 LT_C_BLDGINFO 세션 캐시 적중(27일)              │
│   12:03:44 ⚠ 건물 1123010300100120003 발자국 다각형 자가교차 — 건너뜀 │
├──────────────────────────────────────────────────────────┤
│ [            취소   Esc            ]  실행 중 · 3/7       │
```

### 4.3 done 상태 — 결과 카드

```
│ ④ 결과   성수동2가 277-17 외 1 · 500 m 버퍼 · 12:04:12 (31 s) │
│ ┌──────────────────────────────────────────────────────┐ │
│ │ ● 건물 자료 4.2개월 경과 — 새 전체본(2026-09-09) 있음   │ │ 경고 띠(노랑)
│ │   → data_sources §0 절차로 교체  [문서 열기]            │ │
│ │ ● 높이 추정 비중 큼 — A+B 등급 63 %  [자세히]            │ │ 경고 띠(노랑)
│ │ ○ 건물 최신화 생략 — VWorld 키 없음  [.env 열기]         │ │ 안내 띠(회색)
│ ├──────────────────────────────────────────────────────┤ │
│ │ 필지 2,318   건물 1,812동(철거 7)   TIN 4,930점         │ │ 수치 3×2
│ │ 높이 A 31 % · B 32 % · C 29 % · D 8 %                  │ │
│ │ 정합 중앙값 1.2 m · p90 3.9 m (n=17,581)               │ │
│ │ 불일치 의심 14건(qa_mismatch)                           │ │
│ ├──────────────────────────────────────────────────────┤ │
│ │ [문서에 넣음 ✓]  [.ai 내보내기]  [폴더 열기]  [시트 ⌄]    │ │ 액션 32
│ └──────────────────────────────────────────────────────┘ │
│ ▸ 로그 (87줄)                                              │
├──────────────────────────────────────────────────────────┤
│ [        대지검토 실행   ⌘↵        ]  완료 · 경고 2        │
```

`[시트 ⌄]`를 누르면 바로 아래에 13줄 목록(01_위치범위 … 13_경사)이 펼쳐지고 줄 클릭 = `open_sheet`(OS 기본 앱으로 SVG 열기). 생략된 시트는 흐리게 + 사유("지형 없음").

### 4.4 현황도 시트 고르기(③ 안에서 인라인 펼침)

```
│ ☑ 현황도 시트     9/13 장  [접기 ⌃]   [전체] [없음]        │
│   ☑ 01 위치·범위       ☑ 02 토지이용현황                   │
│   ☑ 03 지목            ☑ 04 용도지역                       │
│   ☑ 05 용도지구·구역    ☑ 06 도시계획시설·지단             │
│   ☑ 07 건축물 용도      ☑ 08 층수 (단계 [12]·[20])          │
│   ☑ 09 노후도           ☐ 10 도로 폭원·위계                 │
│   ☐ 11 공시지가         ☐ 12 표고 (지형 없음)               │
│   ☐ 13 경사 (지형 없음)                                    │
```

### 4.5 컴포넌트 목록

| id | 컴포넌트 | 동작 |
|---|---|---|
| `hdr_db`, `hdr_key` | 헤더 배지 | DB 기준일(필지·건물) — 2.4 임계값으로 색(회/노/빨). 키 배지 `✓` / `없음`(클릭 → `open_env`) |
| `q` | 검색 입력 + `⌄최근` | Enter=검색. 빈 값에서 ⌄ 또는 ↓ = 최근 대상지 5건 목록(`prefs.recent`). 목록은 ↑↓/Enter/Esc |
| `q_list` | 검색 후보 드롭다운 | `search_result.matches` 2건 이상. 항목 = 주소 · 지목 · 면적 |
| `map` | Leaflet | `preferCanvas`, 줌≥17에서 `map_lots` 요청(250 ms 디바운스). 클릭 = 대상 토글. 호버 툴팁 `주소 / 지목·면적`. 우하단 `[⤢]` = 지도 높이 260↔560 토글(F 키) |
| `chips` | 대상 칩 | 지번 짧게(동 이하) + ×. 합계 면적 우측. 칩 수 0이면 "지도에서 필지를 클릭하거나 검색" 힌트 |
| `radius_seg`, `radius_in` | 반경 세그먼트 + 숫자 | 300/500/1000 버튼 또는 입력(100~2000). 1000 초과면 입력 옆에 "파일 분할 권장" 회색 글 |
| `shape_seg` | 형태 세그먼트 | 버퍼(기본)/원/사각 |
| `out_ctx` ~ `out_csv` | 산출물 체크 4개 | 줄 체크 끄면 그 줄의 세부 옵션 비활성(흐림) |
| `ctx_import`, `ctx_demol`, `ctx_shed`, `ctx_vcolor` | 3D 세부 | 자동 Import ☑ / 철거건물 select(점선·회색/제외) / 무벽·가건물 ☐ / 지형 정점색 ☐ |
| `bm_paper`, `bm_scale_*` | 베이스맵 세부 | 용지 A1/A0/커스텀(가로×세로 mm 입력 2칸이 옆에 뜸) / 축척 체크 3개(최소 1) |
| `sheet_*` | 시트 체크 13 + 전체/없음 | 08 층수 단계 입력 2칸(기본 12·20). 지형 DB 없으면 12·13 비활성+사유 |
| `open_after` | 완료 뒤 폴더 열기 ☐ | prefs 저장 |
| `run_btn` | 실행/취소 | ready에서만 활성. running이면 `취소`(`cancel`) |
| `status` | 실행 바 우측 1줄 | "대상 2필지 · 500 m" / "실행 중 · 3/7" / "완료 · 경고 2" / "실패" |
| `result_card` | 결과 카드 | 경고 띠(0~n) + 수치 + 액션 4개 |
| `log` | 접이식 로그 | 등폭 12 px, 최대 400줄, 자동 스크롤, `⚠`·`✗` 줄은 색 |
| `toast` | 상단 토스트 | `error`(context 포함) 4초, 로그에도 남김 |
| `banner_db` | 폼 위 배너 | DB 없음·지형 DB 없음·CRS 검사 실패 등 "실행 전" 안내 |

---

## 5. 상태·예외

| 상황 | 감지 | 표시 | 사용자 행동 |
|---|---|---|---|
| **첫 실행(prefs 없음)** | `init_state.prefs=null` | 기본값(500 m·버퍼·전부 체크·Import ☑·폴더 열기 ☐). ④에 빈 상태 문구 | 없음 |
| **필지 DB 없음** | `init_state.db.parcels=null` | `blocked`: 폼 위 빨간 배너 "필지 DB(data/seoul_site.db)가 없습니다 → data_sources.md §0" + [문서 열기] [다시 확인]. 지도는 타일만. 실행 버튼 비활성 | DB 넣고 [다시 확인](`init` 재전송) |
| **컨텍스트 DB(수치지형도) 없음** | `init_state.db.context=null` | 노란 배너 1줄 "지형·도로면·수계 원천 없음 — 3dm은 필지·건물만, 시트 12·13 생략". 해당 체크 비활성 + 사유 | 실행은 가능 |
| **대상지 도엽 없음**(DB는 있으나 반경 안 도엽 미보유) | `run` 중 Python | `log` ⚠ + 결과 경고 띠 "도엽 37705072 없음 — 지형 일부 생략" | 결과는 `partial` |
| **API 키 없음** | `init_state.api_key=false` | 헤더 배지 `키 없음`(회색). 결과 안내 띠 "건물 최신화 생략". 생성 허용 | 배지 클릭 → `.env` 열기 |
| **INVALID_KEY** | `run` 중 | 결과 경고 띠(노랑) "VWorld 키 거부 — 재발급/재입력(.env의 `= ` 뒤 공백 확인)" | `.env` 열기 |
| **기준일 경과** | `init_state.db.*.age_months` + `done.warnings` | 2.4 규칙: 노랑 = 경과 ≥ 임계값 AND 새 판 있음, 빨강 = 경과만. 헤더 배지 색 + 결과 띠에 원천명·기준일·새 판 기준일·"§0 절차로 교체" | [문서 열기] |
| **CRS 자가검사 실패**(중앙값 > 0.5 m) | `run` 중 | `done.status=failed` + 빨간 띠 "도시계획 레이어 좌표계 불일치(중앙값 ○ m) — 생성 중단". 로그에 TRANSFORM 문자열 | 개발자 호출 |
| **정합 오차** | `done.alignment` | 수치 블록에 항상 표기. 표본 < 200이면 "표본 부족". 불일치 의심 n건 | 참고 |
| **높이 추정 비중 큼**(A+B < 70 %) | `done.height_src` | 노란 띠 + 등급 4분위 1줄 | 참고 |
| **반경 안 건물 0 / 필지 0** | `run` 중 | 건물 0은 경고 띠(노랑), 필지 0은 `failed` | 반경·대상지 확인 |
| **대상 필지 여러 조각·구멍** | `target_state.warnings` | 칩 옆 ⚠ 툴팁 "가장 넓은 조각 사용" | 참고 |
| **베이스맵 범위 초과**(프레임 > 반경) | `run` 중 | 노란 띠 "1:5000 A1 프레임(4.2×3.0 km)이 반경을 넘음 — 가장자리 빈 곳" | 반경 키우거나 축척 변경 |
| **긴 작업** | `progress` | 4.2 카드. 단계 7개(아래). 단계명 + 세부 수치 + 경과시간. 10 s 넘으면 "반경 500 m는 보통 10~40 s" 힌트 | [취소] |
| **취소** | `cancel` | 서브프로세스 kill → `done.status=cancelled`. 부분 파일은 폴더에 남고 로그에 표기 | 재실행 |
| **예외(traceback)** | `error` | 토스트 + 결과 카드 빨강 "실행 실패 — 로그 보기" + 로그 자동 펼침 | [다시 실행] |
| **Import 실패**(문서 단위 등) | `imported.ok=false` | 액션 버튼이 `문서에 넣기 ✗`로, 툴팁에 사유. 재시도 가능 | 재시도 |
| **.ai 내보내기 전제** | 문서에 CTX/BM 레이어 없음 | `.ai 내보내기` 비활성 + 툴팁 "먼저 문서에 넣기" | Import 먼저 |
| **창 크기 작음**(< 420 px 폭) | CSS | 헤더 배지 숫자 숨기고 점만, 세그먼트 줄바꿈 허용 | — |

진행 단계(`progress.step` 1~7): ① 필지·대상지 ② 건물 수집·최신화(API) ③ 건물 높이·상태 ④ 지형 TIN·분류 ⑤ 정합·기준일 검사 ⑥ 3dm·베이스맵 레이어 쓰기 ⑦ 시트·조서. 체크 안 한 산출물의 단계는 건너뛰고 분모에서 뺀다.

---

## 6. 설정·옵션 (deliverables 기준)

| 그룹 | 옵션 | UI | 값·기본 | 근거 |
|---|---|---|---|---|
| 범위 | 반경 | 세그먼트 3 + 숫자 입력 | 300 / **500** / 1000 / 100~2000 m 입력. >1000이면 "파일 분할 권장" | A.2 |
| 범위 | 형태 | 세그먼트 | **버퍼** / 원 / 사각 | A.2 |
| 3D | 생성 | 체크 | ☑ | 요약 |
| 3D | 생성 뒤 문서에 넣기 | 체크 | ☑ (`_-Import`, 레이어·UserString 보존) | A.5 |
| 3D | 철거·폐쇄말소 건물 | select | **점선·회색** / 제외 | A.1 Buildings |
| 3D | 무벽건물·가건물 포함 | 체크 | ☐ | A.4 |
| 3D | 지형 메시 정점색(표고) | 체크 | ☐ | 요약 표고·경사 |
| 베이스맵 | 생성(BM 레이어 + .ai) | 체크 | ☑ | B |
| 베이스맵 | 용지 | select | **A1** / A0 / 커스텀(mm 2칸) | B.1 |
| 베이스맵 | 축척 | 체크 3 | ☑1:1000 ☑1:3000 ☑1:5000 (최소 1). 1:1000=지적선·지번 on, 1:5000=지적선 off는 자동 | B.1·B.2 |
| 베이스맵 | 내보내기 시점 | (없음) | Import 직후 자동 `_-Export`, 축척마다 `basemap_<축척>.ai`. 실패 시 결과 카드 버튼으로 재시도 | B.3 |
| 시트 | 선택 | 체크 13 + 전체/없음 | 전부 ☑. 12·13은 지형 DB 있을 때만 | C |
| 시트 | 08 층수 단계 | 숫자 2칸 | 12 · 20 | C #8 |
| 조서 | CSV | 체크 | ☑ (parcels·buildings·sheet_stats·height_src_stats·alignment 한 묶음, 개별 선택 없음) | E |
| 완료 뒤 | 폴더 열기 | 체크 | ☐ | — |

UI에 **두지 않는 것**(상수·자동): 레이어명·색, 층고 모델 상수, 원점 규칙, CRS 변환 경로, 정합 측정, 기준일 임계값, API 캐시 만료, `_NC` 레이어 제외, 라벨 글꼴. 전부 `constants.py`. 비개발자 사용자가 바꿀 이유가 없고 옵션 하나당 상태·테스트가 늘어난다.

모든 옵션은 바뀔 때마다 `save_prefs`(디바운스 500 ms)로 Python이 `~/.urbandesigntool/prefs.json`에 저장하고 `init_state.prefs`로 돌려준다. localStorage는 file:// 임시 파일 출처라 믿지 않는다.

---

## 7. 결과 화면

생성이 끝나면 ④가 **결과 카드**로 바뀐다(4.3). 스크롤은 카드 상단으로 자동 이동(`scrollIntoView`), 실행 바 상태는 "완료 · 경고 n".

| 영역 | 내용 | 비고 |
|---|---|---|
| 제목 줄 | 대상지 짧은 이름 · 반경·형태 · 완료 시각(소요) | `done.label` |
| 경고 띠 | 등급별 색(빨강/노랑/회색) + 한 줄 + 행동 버튼(문서 열기·.env 열기·자세히) | `done.warnings[]`. 0건이면 띠 없음 |
| 수치 | 필지 n · 건물 n동(철거 n) · TIN n점 / 높이 등급 A·B·C·D % / 정합 중앙값·p90·n / 불일치 의심 n | `done.stats` |
| 액션 | **문서에 넣기**(자동이면 `✓ 넣음`, 다시 누르면 재Import 확인 없이 실행 — 같은 레이어가 중복되므로 버튼 툴팁에 "기존 CTX 레이어가 있으면 중복됩니다") / **.ai 내보내기**(축척별 순차, 끝나면 `✓`) / **폴더 열기** / **시트 ⌄**(13줄, 클릭=OS로 열기) | `import_context`·`export_basemap`·`open_folder`·`open_sheet` |
| 이전 결과 띠 | 입력이 바뀌면 카드 위에 "이전 결과 — 설정이 바뀜(재실행 ⌘↵)" | 액션은 유효 |

시트 미리보기는 **인라인 썸네일을 두지 않는다** — SVG가 수 MB(건물 해치)라 WebView에 올리면 느리고, 사용자는 어차피 Illustrator/브라우저에서 본다. `open_sheet`로 OS 기본 앱을 연다. 필요해지면 Python이 생성 시 200 px PNG 썸네일을 같이 떨어뜨려 `done.sheets[].thumb`(data URL)로 보내는 식으로 추가.

---

## 8. 메시지 계약 초안

브리지는 기존 `panel_host.py` 그대로: JS `send({cmd,...})` → outbox → Python 회수, Python → `window.app.receive({type,...})`. `ensure_ascii=True`.

### 8.1 JS → Python

| cmd | 페이로드 | 응답 |
|---|---|---|
| `init` | — | `init_state` |
| `search` | `query`(str) | `search_result` |
| `select_lots` | `pnus`(list, 현재 대상 전체) | `target_state` (실패 `error`) |
| `map_lots` | `bbox`[minLng,minLat,maxLng,maxLat] | `lots` |
| `run` | `values`(아래) | `busy`→`progress`*→`log`*→`done`→(`imported`→`exported`)*→`busy` off |
| `cancel` | — | `done{status:"cancelled"}` |
| `import_context` | `result_dir` | `imported` |
| `export_basemap` | `result_dir`, `scales`(list[int]) | `exported`(축척마다 1회) |
| `open_folder` | `result_dir` | (실패 `error`) |
| `open_sheet` | `path` | (실패 `error`) |
| `open_env` | — | `.env` 를 OS 편집기로 (실패 `error`) |
| `open_doc` | `anchor`("data_sources#0" 등) | docs 파일 열기 |
| `open_eum` | `pnu` | 토지이음(기존) |
| `save_prefs` | `prefs`(values + `map_expanded`) | — |

`values` 키(전부 `prefs`에 그대로 저장):

```jsonc
{"pnus":["1123010300106760006"],
 "radius":500, "shape":"buffer",            // buffer|circle|square
 "context":{"on":true,"import_after":true,"demolished":"dashed", // dashed|exclude
            "include_shed":false,"terrain_vertex_color":false},
 "basemap":{"on":true,"paper":"A1","paper_mm":[841,594],"scales":[1000,3000,5000]},
 "sheets":{"on":true,"ids":[1,2,3,4,5,6,7,8,9,10,11,12,13],"floor_breaks":[12,20]},
 "csv":{"on":true},
 "open_folder_after":false}
```

### 8.2 Python → JS

```jsonc
{"type":"init_state",
 "tile":{"url":"…","fallback_url":"…","attribution":"…"},
 "map":{"center":[126.9784,37.5665],"zoom":16},
 "db":{"parcels":{"date":"2026-05-13","age_months":4.8,"warn":null},     // warn: null|"yellow"|"red"
       "buildings":{"date":"2026-09-09","age_months":0.9,"warn":null,"newer":null},
       "terrain":{"sheets":139,"years":"2024~2026","warn":null},          // 없으면 null
       "context":true},                                                   // 컨텍스트 DB 유무
 "api_key":true,                       // VWorld 키 유무
 "prefs":{…values…,"recent":[{"pnus":["…"],"label":"성수동2가 277-17 외 1"}],"map_expanded":false},
 "sheet_catalog":[{"id":1,"name":"위치·범위"},…,{"id":12,"name":"표고","needs":"terrain"}],
 "version":"0.1"}

{"type":"busy","on":true}
{"type":"progress","step":3,"steps":7,"label":"건물 높이 계산","detail":"1,812동","pct":38,"elapsed":7.2}
{"type":"log","text":"…","level":"info"}            // info|warn|error  (줄 색)
{"type":"error","context":"실행","text":"…"}

{"type":"search_result","query":"…","resolved":true,
 "matches":[{"pnu":"…","address":"…","land_category":"대","area":230.4,"center":[126.97,37.59]}],
 "message":"후보 3건"}
{"type":"lots","geojson":FC,"truncated":false}       // properties {pnu,address,jibun,land_category,area}
{"type":"target_state","targets":[{"pnu":"…","address":"…","jibun":"277-17","land_category":"대","area":230.4}],
 "total_area":1234.5,"target_geojson":FC,"warnings":["1123…: 2조각 — 가장 넓은 조각 사용"]}

{"type":"done","status":"ok",                        // ok|partial|failed|cancelled
 "result_dir":"/…/result/20261007/성수동2가_277-17",
 "label":"성수동2가 277-17 외 1 · 500 m 버퍼","elapsed":31.4,
 "warnings":[{"level":"yellow","code":"stale_buildings",
              "text":"건물 자료 4.2개월 경과 — 새 전체본(2026-09-09) 있음",
              "action":{"label":"문서 열기","cmd":"open_doc","anchor":"data_sources#0"}},
             {"level":"yellow","code":"height_estimated","text":"높이 추정 비중 큼 — A+B 63 %"},
             {"level":"gray","code":"no_api_key","text":"건물 최신화 생략 — VWorld 키 없음",
              "action":{"label":".env 열기","cmd":"open_env"}}],
 "stats":{"lots":2318,"buildings":1812,"demolished":7,"tin_points":4930,
          "height_grade":{"A":0.31,"B":0.32,"C":0.29,"D":0.08},
          "alignment":{"median":1.2,"p90":3.9,"n":17581,"low_sample":false},
          "mismatch":14},
 "files":{"context":"context.3dm","basemap_scales":[1000,3000,5000],
          "sheets":[{"id":1,"path":"sheets/01_위치범위.svg"},…,{"id":12,"path":null,"skipped":"지형 없음"}],
          "tables":["tables/parcels.csv",…]},
 "imported":false,"exported":[]}

{"type":"imported","ok":true,"result_dir":"…","objects":4120,"text":"CTX·BM 레이어 4,120개"}
{"type":"exported","ok":true,"scale":1000,"path":"…/basemap_1000.ai"}
```

컨트롤러 규칙: `run`은 `values`를 그대로 `dev` 생성기(python3 서브프로세스)에 JSON으로 넘기고, stdout의 한 줄 JSON(`progress`/`log`)을 그대로 푸시한다. 생성이 끝나면 `context.json`을 읽어 `done`을 만든다. `import_after`면 이어서 `_-Import` → `imported`, `basemap.on`이면 축척마다 `_-Export` → `exported`. 도메인 예외는 메시지만, 그 외는 traceback을 `error`로.

---

## 9. 비주얼 토큰

```
색   --bg #f6f7f8   --surface #fff   --line #e3e6ea   --ink #1c2127   --sub #6b7480   --mute #9aa3ad
     --accent #2563eb  (버튼 채움·선택 테두리·대상지 폴리곤·진행 막대 — 강조 1색)
     --accent-weak #e8efff
     --warn #b45309 / 배경 #fff7e6     --danger #c2410c / 배경 #fdecea     --ok #15803d
     경고 띠 좌측 3 px 보더만 색, 배경은 틴트. 회색 안내 띠는 --mute.
타이포 Pretendard(인라인) → -apple-system, "Apple SD Gothic Neo", "Malgun Gothic"
     제목 14/600 · 본문 13/400 · 보조·칩·배지 12/400 · 섹션 번호 12/600 대문자 자간 .02em
     숫자·로그·PNU: "SF Mono", Menlo, Consolas 12
간격 4 배수. 섹션 세로 패딩 8, 섹션 사이 1 px --line. 줄 높이: 입력·세그먼트 28, 체크 줄 24, 액션 버튼 28, 실행 버튼 36.
     좌우 여백 12. 컨트롤 간 가로 간격 8. 라벨 폭 ③ 섹션 96 px 고정(한 줄 그리드 `96px 1fr`).
라운드 4(컨트롤) · 6(카드) · 999(칩·배지)
초점  2 px --accent 아웃라인(outline-offset 1). 마우스 호버는 --bg 틴트만.
지도  대상지 fill accent 25 % / stroke accent 2 px · 주변 필지 stroke #6b7480 40 % 1 px fill 투명(fillOpacity .01)
     · 반경 범위 미리보기 stroke --ink 점선 1 px(대상지 선택 시 반경·형태에 따라 즉시 그림, 클라이언트 계산)
```

다크 모드 없음. 애니메이션은 진행 막대 폭 전환(150 ms)만 — 생성 중 UI 스레드가 멈추면 어차피 안 돈다.

---

## 10. 접근성·키보드

| 키 | 어디서 | 동작 |
|---|---|---|
| (창 열림) | — | 검색줄 자동 포커스 |
| `/` 또는 `⌘F` | 어디서나(입력 중 제외) | 검색줄 포커스·전체 선택 |
| `Enter` | 검색줄 | 검색. 후보 목록이 열려 있으면 선택 |
| `↓ ↑` | 검색줄·후보/최근 목록 | 목록 이동. 빈 검색줄에서 ↓ = 최근 목록 |
| `Esc` | 목록 / running | 목록 닫기 / 취소(확인 없음, 재실행 쉬움) |
| `⌘Enter` / `Ctrl+Enter` | 어디서나 | 실행(ready일 때) |
| `⌫`(칩 포커스) | 대상 칩 | 그 필지 제거 |
| `F` | 지도 밖 | 지도 확대 토글 |
| `⌘O` / `Ctrl+O` | done | 폴더 열기 |
| `Tab` | — | 헤더 배지 → 검색 → 지도(건너뜀, `tabindex=-1`) → 칩 → 반경 → 형태 → 산출물 체크·세부 순 → 실행 → 결과 액션 → 로그 토글 |

- 모든 컨트롤은 네이티브 `<input>`·`<select>`·`<button>`. 세그먼트는 `role="radiogroup"` + `<input type=radio>` 숨김(←→ 이동 공짜).
- 경고 띠는 색 + 아이콘(●/○) + 텍스트 병행. 진행률은 `role="progressbar" aria-valuenow`. 상태 줄은 `aria-live="polite"`, 오류 토스트는 `aria-live="assertive"`.
- 지도 클릭은 유일하게 키보드로 못 하는 동작 → 검색(지번)으로 같은 결과를 낼 수 있어 보완됨.
- 글자 최소 12 px, 대비 4.5:1(--sub on --surface 5.3:1).
- 창 폭 420 px 이하: 헤더 배지는 점만, 세그먼트는 줄바꿈, 지도 최소 200 px.

---

## 11. 구현 메모

**파일**: `scripts/site_ui.html` 하나(마크업·CSS·JS). vendor는 `<!--VENDOR_CSS-->`·`<!--VENDOR_JS-->` 자리에 주입(기존 `panel_host.py`). Pretendard woff2 base64도 같은 방식 1자리.

**JS 구조(≈600줄 예상)**:
```
state = {phase:"idle", targets:[], values:{…}, db:{…}, apiKey:false, recent:[], progress:null, result:null, log:[]}
send()/receive()           — 브리지 2개 (기존 그대로)
render()                   — phase·targets·values·result를 보고 DOM 갱신. 섹션별 renderTargets/renderOptions/renderResult/renderLog
bind()                     — 이벤트 1회 등록. 입력 change → state.values 갱신 → render() + savePrefs(디바운스)
map 모듈                   — initMap, requestLots(디바운스 250), onLotClick, drawTargets, drawRange(반경 미리보기)
keys                       — 전역 keydown 스위치 하나
```
템플릿 엔진 없음. 13개 시트 체크·칩·경고 띠는 `innerHTML` 문자열 조립 + `esc()`. 상태 전이는 `setPhase(p)`가 `document.body.dataset.phase=p`로 두고 CSS가 `[data-phase=running] fieldset{…}`로 비활성·버튼 라벨을 처리 — JS 분기 최소.

**Leaflet**: `preferCanvas:true`. 레이어 3개 — `lotsLayer`(bbox 필지, moveend마다 교체), `targetLayer`(`target_geojson`), `rangeLayer`(반경 미리보기: 버퍼는 Python이 `target_state.range_geojson`로 주면 정확하지만 v1은 클라이언트에서 중심 원·사각만 그리고 버퍼는 원으로 근사 — `ponytail:` 정확한 버퍼가 필요하면 `target_state`에 추가). 타일 `tileerror` 3회 → fallback. 줌 < 17이면 `lotsLayer` 비우고 힌트 칩(기존 실측: 줌 16은 6천 건 초과). 지도 높이 토글 뒤 `map.invalidateSize()`. 창 리사이즈 → `ResizeObserver`로 `invalidateSize`.

**진행률·취소**: 생성기는 python3 서브프로세스(`subprocess.Popen`, stdout 한 줄 JSON). Eto `UITimer` 100 ms로 stdout 큐를 비워 `push`. 취소 = `proc.terminate()`. Rhino CPython 인프로세스로 돌리면 WebView가 멈추므로 progress는 "실행 중" 정적 라벨 하나만 가능 — UI는 두 경우를 같은 `progress` 메시지로 받으므로 바꿀 것 없음.

**Import·Export**: 서브프로세스가 끝난 뒤 UI 스레드에서 `_-Import`·`_-Export`(각 수 초, 이 동안은 멈춤 — `busy` 유지). Export는 Top 뷰 활성화 → `_-SelLayer BM::*` → `_-Export … PreserveUnits=Yes Unit=Millimeters ExportHatchesAsSolidFills=Yes OrderLayers=Yes` 문자열은 `constants.py`.

**성능**: 결과 카드·로그는 400줄 캡. `lots` GeoJSON은 properties 5개만. 시트 썸네일 없음. 폼 전체 `render()`는 입력당 1회(수십 노드)라 비용 없음.

**테스트**: `tests/test_site_ui_contract.py` — `done`·`init_state` 샘플 JSON이 §8 키를 갖는지 python3 unittest 1개. HTML은 브라우저에서 `?mock=1`로 열면 `receive`에 샘플을 흘려 넣는 20줄 목(mock) — Rhino 없이 레이아웃 확인.

---

## 12. 이 안의 약점·대안

| 약점 | 영향 | 대안·완화 |
|---|---|---|
| 지도가 260 px로 작다 | 합필 클릭 시 필지가 작게 보임, 오클릭 | `[⤢]`/F 토글 560 px, 창 세로 늘리면 자동 확장. 그래도 부족하면 지도만 별창(Eto 두 번째 Form)은 복잡 — 비추천 |
| 옵션이 전부 보여 비개발자가 압도될 수 있다 | 첫 사용 망설임 | 기본값이 전부 "맞는 값"이라 건드릴 필요 없음을 ④ 빈 상태 문구로 알림("기본값 그대로 ⌘↵"). 그래도 문제면 ③을 "산출물 4줄"만 남기고 세부는 `[⋯]`로 접는 **B안(점진 공개)**로 전환 — 마크업 그대로 두고 CSS 클래스 하나로 접힘 |
| 결과가 폼 아래라 지도와 결과를 같이 못 본다 | 어긋난 도로를 지도에서 확인하고 싶을 때 | 이 툴의 확인 장소는 Rhino 뷰포트(Import 됨)라 패널 지도에서 볼 필요가 적음. 필요하면 `done` 뒤 지도에 `CTX::QA::cadastre_mismatch`를 GeoJSON으로 얹는 P1 |
| 한 화면이라 `done` 뒤 입력을 바꾸면 결과와 입력이 불일치 | 혼동 | "이전 결과" 띠 + 실행 바 상태 글. 결과를 아예 지우지는 않음(폴더 열기 유효) |
| 세로 900에 맞추느라 줄 높이 24~28 px — 마우스 타깃 작음 | 터치 없음, 데스크톱 전용이라 허용 | 창을 키우면 간격은 그대로(밀도 유지가 목적) |
| 진행률은 서브프로세스 전제 | 인프로세스로 가면 정적 라벨뿐 | deliverables A.5가 python3 경로를 1순위로 두므로 전제가 맞음 |
| `.ai` 내보내기가 Rhino 문서 상태(Top 뷰·레이어)에 의존 | 사용자가 레이어를 지우면 실패 | 실패 시 버튼에 사유, 재Import 후 재시도. 06 대안(SVG→JSX)은 1차 경로가 깨질 때만 |

경쟁 접근과의 선택 기준: 사용자가 **같은 설정으로 대상지만 바꿔 자주 돌린다**면 이 안(A)이 가장 빠르다. 사용자가 **옵션을 매번 고민**하거나 처음 보는 사람이 많다면 단계형(마법사) 안이 안전하다. 두 경우 모두 §8 계약은 같으므로 UI만 바꿀 수 있다.
