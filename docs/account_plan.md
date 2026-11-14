# 회원(구글 로그인)과 디테일 옵션 — 작업 계획

2026-11-14 작성. 기준: main 4d232c2(배포판 0.3.9). 디테일 옵션(`constants.DETAIL_OPTIONS` 9종 — 2938bfe, 2026-11-13)은 아직 배포되지 않았다.
목표: 디테일 옵션은 무료 회원(구글 로그인)만 쓰고, 나머지 기능은 지금처럼 누구나 쓴다. 돈은 받지 않는다. 서버비 0을 지킨다.

## 먼저 정할 것 — 권장안과 근거

| 질문 | 권장 | 근거 |
|---|---|---|
| 누가 회원인가 | 구글 로그인 + 동의만 하면 바로 회원(승인제 아님) | 승인제는 운영자가 매일 손대야 한다. 돈을 받지 않는 동안 구분하는 목적은 '누가 쓰는지 알고, 연락할 길을 만드는 것'이다 |
| 무엇을 잠그나 | 디테일 9종 전부(`MEMBER_OPTIONS`) — 원격 설정으로 빼고 넣는다 | 아직 아무도 받지 않은 기능이라 처음부터 회원 기능으로 내면 '써 보던 것을 빼앗는' 일이 없다. 교량을 끄면 철교 위 선로가 빠지고 도로가 지형에 얹히는(0.3.9 모양) 점이 불만으로 오면 교량만 손님에게 연다 — 판 없이 |
| 언제 내나 | 디테일과 로그인을 같은 판(0.4.0)으로 | 디테일만 먼저 내고 나중에 잠그면 써 본 사람에게서 빼앗는 꼴이 된다. 디테일 공개가 2주쯤 늦어지는 것을 감수한다 |
| 얼마나 단단히 잠그나 | 정직한 사용자용 구분만(서명·난독화 없음) | 설치본에 파이썬 원본이 그대로 있다(Blender판은 GPL 원본). 돈을 받기 전에는 막는 데 시간을 쓰지 않는다. 정말 막아야 할 때는 서버 쪽 자원으로 막는다(아래 '나중') |
| Blender판 | 로그인 없음, 디테일 전부 열림 | Blender Extensions 약관: 외부 서비스는 로그인·가입 같은 추가 제한 없이 쓰게 해야 한다([terms-of-service](https://extensions.blender.org/terms-of-service)). 심사 답변에도 "free and without login"이라 적었다(`docs/blender_store/README.md`) |
| 회원 정보는 어디에 | 앱스 스크립트 + 구글 시트(문의함과 같은 방식) | 서버비 0. 이미 운영 중인 방식이다(웹 저장소 `tools/contact`). 회원 표를 시트에서 바로 보고 고친다 |
| 무엇을 저장하나 | 구글 계정 고유번호(`sub`)·이메일·동의 기록만. 이름·사진은 받지 않는다 | 최소 수집 — 처리방침과 탈퇴가 단순해진다 |

## 등급

| 등급 | 누가 | 쓰는 것 |
|---|---|---|
| 손님 `guest` | 로그인하지 않음 | 지금 기능 전부 — 3D 기본(건물·도로·지형·수계·녹지·철도 부지), 2D 전부 |
| 회원 `member` | 구글 로그인 + 동의 | + `MEMBER_OPTIONS`(연석·노면표시·가로수·교량·선로·옹벽·담장·파라펫·층 구분선) |
| 막힘 `blocked` | 운영자가 시트에서 바꿈(남용·요청) | 손님과 같다 |
| (나중) 유료 | 정하지 않았다 | 시트에 `tier` 칸만 둔다. 값을 늘리면 된다 |

`ACCOUNT_ENABLED = False`(원격 설정)이면 회원 구분이 없다 — 로그인 버튼이 사라지고 디테일이 모두 열린다. 회원 API가 오래 멈췄을 때 쓰는 비상 스위치다.

## 사용자 흐름 — 플러그인

로그인은 **늘 시스템 브라우저에서** 한다. 구글은 앱 안 웹뷰(Rhino Eto WebView, SketchUp HtmlDialog, Archicad 팔레트)의 구글 로그인을 막는다(`disallowed_useragent` — [구글 공지](https://developers.googleblog.com/en/upcoming-security-changes-to-googles-oauth-20-authorization-endpoint-in-embedded-webviews/)).
플러그인은 구글과 직접 말하지 않는다. 로그인은 gorani.site가 하고, 플러그인은 '연결 코드'로 결과만 받는다. 그래서 플러그인에 구글 클라이언트 비밀값이 없고, 호스트 다섯 개가 같은 코드를 쓴다.

1. **처음 열 때 묻지 않는다.** 로그인 팝업·띠 없음 — 버튼 하나로 결과까지 간다는 원칙(PRODUCT.md)을 지킨다.
2. **3D 설정 '디테일' 줄** — 손님에게도 보인다(숨기면 회원 기능이 있는지 모른다). 체크박스는 흐리게 잠기고 줄 끝에 자물쇠 + `디테일은 무료 회원 기능입니다 [구글로 로그인]`. 요약 줄(`s3d_sum`)에는 손님의 디테일을 쓰지 않는다.
3. **더보기 메뉴 '설정' 맨 위 '계정' 줄** — 손님 `로그인 안 함 [구글로 로그인]`, 회원 `name@gmail.com [로그아웃]`.
4. **[구글로 로그인]** → 브라우저에 `https://gorani.site/link/?c=<코드>&h=rhino` 열림 → 패널: `브라우저에서 로그인을 마쳐 주세요 · 확인 코드 K7Q2 [주소 복사] [취소]`.
5. 웹에서 로그인(처음이면 동의) → `Rhino를 name@gmail.com으로 연결합니다. 패널의 코드가 K7Q2인가요? [연결]` → 패널이 저절로 바뀌고 토스트 `로그인했습니다 — 디테일을 쓸 수 있습니다`. 디테일 체크는 그 사람이 저장해 둔 값(없으면 기본값)으로 돌아온다.
6. **오프라인** — 마지막 확인 뒤 30일까지는 회원으로 돈다. 그 뒤에는 손님으로 돌고 디테일 줄에 `로그인을 다시 확인하지 못해 디테일이 꺼졌습니다 [다시 확인]`. 오류로 만들지 않는다.
7. **회원 API가 죽었을 때** — 손님으로 계속 쓴다. 사용자를 막지 않는다(공지·매니페스트와 같은 원칙).
8. 10분 안에 연결하지 않으면 코드가 끝나고 `시간이 지났습니다 [다시 시도]`.

## 사용자 흐름 — 웹페이지(gorani.site)

| 자리 | 내용 |
|---|---|
| 머리줄 오른쪽 | 작은 `로그인`(로그인하면 메일 첫 글자 동그라미 → 계정 페이지). 주 버튼은 여전히 '받기'다 |
| 처음 로그인(가입) | 한 화면: 필수 [이용약관 동의] [개인정보 수집·이용 동의] [만 14세 이상입니다], 선택 [업데이트 소식 메일 받기]. 동의한 판(`terms_v`·`privacy_v`)을 적어 두고, 판이 오르면 다음 로그인 때 다시 묻는다 |
| `/link/` | 플러그인이 여는 연결 화면 — 로그인 → 코드 확인 → [연결]. 연결한 뒤 `이제 Rhino로 돌아가세요` |
| `/account/` | 등급, 가입일, 연결된 프로그램(Rhino·SketchUp·Archicad — 판·마지막 확인일) + 프로그램마다 [연결 끊기], [소식 메일 받기] 끄고 켜기, [탈퇴](시트에서 줄을 지운다) |
| `/privacy/`·`/terms/` | 처리방침·약관. 바닥글·가입 화면·패널 메뉴에서 링크한다 |
| 설치 칸·FAQ | `디테일 옵션은 무료 회원 기능입니다` 한 줄 + FAQ '왜 로그인하나요? 무엇을 저장하나요?' |

다국어: 웹은 다섯 언어지만 계정·처리방침은 한국어·영어를 먼저 쓰고, es·ja·zh는 영어판으로 보낸다(법적 문서를 다섯 벌 관리하지 않는다. 영어판에 '한국어판이 우선한다').
웹 GA에는 `sign_up`·`login`·`link_device` 이벤트만 더한다(메일·id는 보내지 않는다).

## 구성

```
gorani.site (GitHub Pages, 정적) ── 구글 로그인 버튼(GIS) → ID 토큰 ──┐
플러그인(Rhino 8·7, SketchUp, Archicad) ── link_poll·me (3 s·하루 1회) ─┼─▶ 앱스 스크립트 웹 앱 '회원 API' ──▶ 구글 시트 '회원함'
관리자 페이지(dev_admin, 이 Mac) ── Sheets API(서비스 계정, 읽기) ─────┘        └ ID 토큰 확인: oauth2.googleapis.com/tokeninfo
```

- 구글 클라우드 프로젝트 하나(기존 `gorani-stats`를 써도 된다)에 OAuth 클라이언트 '웹 애플리케이션' 하나, 승인된 출처 `https://gorani.site`. 범위는 `openid email`만 — 이 범위만 쓰면 앱 심사가 필요 없고, 동의 화면에 이름·로고를 보이려면 가벼운 브랜드 인증만 받는다([구글 도움말](https://support.google.com/cloud/answer/10311615)). 브랜드 인증에는 Search Console에서 gorani.site 도메인 인증과 처리방침 주소가 필요하다.
- 요청은 문의 폼처럼 `text/plain` POST(JSON 본문) — 미리 보내기(preflight)가 없어 CORS 설정이 필요 없다.

### 회원 API(`action`)

| action | 부르는 곳 | 보냄 | 받음 |
|---|---|---|---|
| `login` | 웹 | `id_token`, 처음이면 `consent{terms_v, privacy_v, age14, news}`, `lang` | `session`(웹용), `user{email, tier, created}` / `need_consent` |
| `link_approve` | 웹 `/link/` | `session`, `code`, `host` | `ok` |
| `link_poll` | 플러그인 | `code`, `host`, `version` | `pending` / `{token, email, tier}` |
| `me` | 플러그인·웹 | `token` 또는 `session` | `{email, tier}` / `invalid` |
| `logout` | 플러그인·웹 | `token`(그 연결만) 또는 `session`+`token_id` | `ok` |
| `delete` | 웹 | `session` | `ok` — 회원 줄과 연결 전부 지움 |
| `set_news` | 웹 | `session`, `on` | `ok` |

- ID 토큰은 tokeninfo로 확인한다 — `aud` = 우리 클라이언트 ID, `email_verified`, `exp`. 앱스 스크립트에는 RSA 서명 확인이 없어 이 길을 쓴다.
- 연결 코드는 플러그인이 만든다(헷갈리는 글자를 뺀 8자, 40비트). 서버는 `link_approve` 때 CacheService에 10분 둔다. 한 번 받으면 지운다. 화면 두 곳에 같은 코드를 보여 '남의 코드를 승인하게 만드는' 장난을 막는다.
- `token`·`session`은 32바이트 무작위 값이다. 시트에는 SHA-256만 적는다(시트가 새도 토큰은 새지 않는다).
- 한도는 문의 폼처럼 CacheService로 건다 — 코드 하나당 `link_poll` 분당 30회, IP·메일당 `login` 분당 10회.

### 시트 '회원함'

| 탭 | 칸 |
|---|---|
| 회원 | `user_id`(무작위), `google_sub`, `email`, `tier`, 가입일, `terms_v`, `privacy_v`, 소식 메일(Y/N), 마지막 확인, 메모(사람) |
| 연결 | `token_hash`, `user_id`, `host`(web·rhino·sketchup·archicad), 판, 만든 날, 마지막 확인 |
| 기록 | 날짜, 사건(가입·탈퇴·등급 변경·연결), `host` — 메일 없이 숫자 세기용 |

시트 공유는 운영자 둘만(문의함과 같다). 설치 ID(`~/.gorani/client_id`)는 시트에 적지 않는다 — 적으면 GA·문지기 기록이 실명과 이어진다.

### 다른 길을 고르지 않은 까닭

| 후보 | 고르지 않은 까닭 |
|---|---|
| Firebase Auth + Firestore | 회원 관리 화면은 좋지만, 플러그인이 구글 데스크톱 OAuth(로컬 포트·PKCE)를 따로 해야 하고 보안 규칙·SDK를 익혀야 한다. 회원이 수천 명을 넘거나 돈을 받으면 옮길 곳으로 남긴다 |
| 춘천 VM(`server_gate` 확장) | 개인정보를 직접 지키는 서버가 된다(접근 통제·암호화 같은 안전성 확보조치). 1 GB VM 하나에 로그인까지 묶인다. 국외 반출 문제가 있는 것은 수치지형도뿐이라 회원 정보를 국내에 둘 까닭이 없다 |
| Supabase 무료 | 1주 동안 쓰지 않으면 프로젝트가 멈춘다(확인 필요) |

플러그인은 회원 API 주소 하나(`ACCOUNT_API_URL`, 원격 설정)만 안다. API 모양을 지키면 백엔드를 옮겨도 플러그인 판이 필요 없다.

## 플러그인 작업 — 0.4.0

| 파일 | 할 일 |
|---|---|
| `scripts/account.py`(새 로직 모듈, 표준 라이브러리) | `~/.gorani/account.json`(`token`·`email`·`tier`·`checked_at`) 읽기·쓰기, `get_link_url(code, host)`, `poll_link(code)`, `refresh()`(하루 1회 `me`), `logout()`, `is_member(account)`, `get_allowed_options(options, account, host_label)` — 손님이면 `MEMBER_OPTIONS`를 끈 사본. prefs.json에 넣지 않는다 — 로그아웃 = 파일 삭제 |
| `scripts/constants.py` | `ACCOUNT_ENABLED`, `ACCOUNT_API_URL`, `ACCOUNT_LINK_URL`, `MEMBER_OPTIONS = tuple(DETAIL_OPTIONS)`, `ACCOUNT_OFFLINE_DAYS = 30`, `ACCOUNT_POLL_SECONDS = 3`, `ACCOUNT_LINK_MINUTES = 10`. `HOST_LABELS`에 `account`(blender만 False) |
| `scripts/remote_config.py` | `REMOTE_KEYS`에 `ACCOUNT_ENABLED`·`ACCOUNT_API_URL`·`MEMBER_OPTIONS`. 새 키 추가라 `COMPAT_MIN`은 그대로 |
| `scripts/cmd_site.py` | 명령 `account_login`·`account_cancel`·`account_logout`, 푸시 `account_state{state: guest\|linking\|member\|expired, email, code}`, `init_state.account`. `generate` 직전에 `account.get_allowed_options` — 엔진(`context_builder`·`get_detail`)은 등급을 모른다. 저장한 prefs는 그대로 두고 생성 요청만 끈다. `context.json.options`에는 실제로 쓴 값이 남는다 |
| 폴링·확인 | 데몬 스레드(`usage_stats`와 같은 방식)가 3초마다 `link_poll`. 결과 푸시는 Rhino 8은 `AsyncInvoke`로 UI 스레드에서(`panel_host`와 같다), 사이드카는 기존 푸시 줄. `init`은 캐시로 바로 그리고, 마지막 확인이 하루를 넘었으면 같은 스레드로 `me` → 바뀌면 `account_state` |
| `scripts/site_ui.html` | 디테일 줄 잠금·자물쇠·로그인 링크, 메뉴 '계정' 줄, 연결 중 띠(코드·주소 복사·취소), 목 모드 `&account=guest\|linking\|member\|expired` |
| `scripts/i18n.json` | 새 문구 네 언어(`tests/test_i18n.py`) |
| `scripts/usage_stats.py` | `panel_open`·`build`에 `member`(0/1)만. `get_options3d`에 켠 디테일. 계정 id·메일은 보내지 않는다. `dev_stats`에 맞춤 측정기준 등록 |
| Blender 빌드 | `account` 네트워크 구간을 `# [blender-cut]`으로 감싼다. 회원 API 주소는 `BLENDER_ALLOWED_HOSTS`에 넣지 않는다(남으면 빌드가 멈춰서 실수를 잡는다) |
| `tests/test_account.py` | 가짜 회원 API(`http.server`)로 연결·폴링·만료·오프라인 30일·로그아웃·손님 옵션 끄기·`ACCOUNT_ENABLED` 꺼짐 |
| `scripts/dev_personas.py` | 지금 18명은 빈 HOME이라 손님이다 — 디테일이 꺼진 결과로 문제 0건인지 본다. 회원 1명 추가(가짜 `account.json` + 가짜 API) |

함께 고칠 문서: `docs/panel_ui.md`(명령·푸시·옵션 키·'계정' 절), `docs/code_map.md`, `CLAUDE.md`(Rhino 실행 중 외부 접속 예외 여섯 → 일곱: ⑦ 회원 확인), `docs/install.md`(보내는 것), `docs/food4rhino.md`(지금 "You don't need … an account" → "Detail options need a free Google sign-in"), `docs/sketchup_store.md` Privacy 줄.

## 웹 저장소 작업(`~/Documents/GitHub/gorani`)

- `tools/account/`(새로): `Code.gs`·`README.md` — 문의함과 같은 꼴(`setup` 실행 → 웹 앱 배포 → 주소를 `assets/site.js`와 `constants.ACCOUNT_API_URL`에). 설정값(클라이언트 ID)은 스크립트 속성에.
- `assets/site.js`: GIS 로그인 버튼, 세션(localStorage, 30일), 머리줄 계정 표시.
- `link/`·`account/`·`privacy/`·`terms/` 페이지(ko·en), `sitemap.xml`·`robots.txt`(계정·연결 페이지는 색인하지 않음), 바닥글 링크, FAQ·설치 칸 한 줄.
- 웹은 판 묶음 규칙이 없다 — 플러그인 0.4.0보다 먼저 올려 둔다.

## 개인정보·약관·스토어

**지금도 문제가 하나 있다**: 문의 폼으로 이메일을 받고 GA를 쓰는데 웹에 처리방침 페이지가 없다. 회원 기능과 별개로 이번에 같이 만든다.

| 할 일 | 근거 |
|---|---|
| 처리방침 공개 — 웹 `/privacy/`, 패널 메뉴·스토어 설명에서 링크 | 개인정보보호법 제30조. 초안은 개인정보위 개인정보 포털의 '처리방침 만들기' 도구로 쓴다 |
| 수집 동의 — 항목(구글 계정 고유번호·이메일), 목적(회원 확인·디테일 제공·선택 시 소식 메일), 보유(탈퇴하면 바로 지움), 거부할 권리와 불이익(디테일을 못 씀) | 제15조 제2항 |
| 만 14세 미만은 가입 불가 — 가입 화면 확인란 | 법정대리인 동의(제22조의2)를 받지 않으려고 |
| 구글(미국) 서버 보관을 처리방침에 적는다 — 이전받는 자 Google LLC, 국가, 항목, 목적, 보유기간 | 국외 이전(제28조의8, 계약 이행에 필요한 보관은 공개로 갈음 — 확인 필요) |
| 소식 메일은 선택 동의자에게만, 드물게 | 광고성 정보 전송 규정(정보통신망법 제50조 — 확인 필요). 큰 소식은 패널 공지(`notices`)로 한다. 무료 Gmail 하루 약 100통 한도 |
| 영어판에 EU 사용자 권리(열람·삭제 = [탈퇴]) | 네덜란드·프랑스·스위스 팩 사용자 — GDPR(확인 필요) |
| GA·문지기 기록과 계정을 잇지 않는다 | 이으면 지금의 익명 통계가 실명 개인정보가 된다 |

| 채널 | 로그인 | 디테일 | 할 일 |
|---|---|---|---|
| Rhino 8·7(yak·food4Rhino) | 있음 | 회원 | food4Rhino 설명·스크린샷 문구 |
| SketchUp(Extension Warehouse) | 있음 | 회원 | 다음 제출 때 Privacy 칸에 계정 항목. 개인정보 정책 위반은 반려 사유다 |
| Archicad(웹 zip) | 있음 | 회원 | 없음 |
| Blender(공식 스토어) | 없음 | 전부 열림 | 약관상 로그인 금지. 손님과 회원 사이 구멍이 되지만 돈을 받지 않는 동안은 받아들인다 |
| 웹판(Pyodide, 미공개) | 같은 사이트 세션 | 회원 | 공개할 때 |

## 운영

| 일 | 하는 법 |
|---|---|
| 평소 | 할 일 없다(가입·연결은 자동). 주 1회 관리자 페이지 '회원' 카드를 본다 |
| 막기 | 시트 `tier`를 `blocked`로 — 다음 `me` 확인 때 반영된다(늦어도 하루) |
| 탈퇴 요청 메일 | 웹 [탈퇴]를 안내하고, 못 하면 시트에서 그 사람의 회원·연결 줄을 지운다 |
| 회원 API 장애 | 플러그인은 30일 캐시로 돈다. 길어지면 `ACCOUNT_ENABLED`를 끄고 `dev_deploy.py notices`(디테일 모두 열림, 판 없음) |
| 잠글 기능 바꾸기 | `constants.MEMBER_OPTIONS`를 고치고 `dev_deploy.py notices` |
| 처리방침 개정 | `privacy_v`를 올린다 — 다음 로그인 때 다시 동의받는다. 웹에 바뀐 날짜를 남긴다 |
| 백업 | 시트 판 기록에 맡긴다. 개인정보라 로컬 사본(CSV)을 만들지 않는다 |
| 관리자 페이지 '회원' 카드 | 시트를 서비스 계정(기존 GA 키)에 '보기'로 공유하고 시트 ID만 `~/.config/gorani/`에. 누적 회원, 이번 주 가입, 프로그램별 연결, 30일 안 확인한 회원, 탈퇴 수 — 숫자만, 메일은 띄우지 않는다 |
| 볼 지표 | 주간 가입, 패널을 연 사람 중 회원 비율(GA `member`), 회원의 디테일 사용률, 연결 완료율(링크 연 수 대비 연결 수 — 낮으면 로그인 흐름이 막힌 것) |

## 일정

코드 판은 2주에 한 번 이하라 웹·회원 API(판 없음)를 먼저 끝내고, 0.4.0에 디테일과 로그인을 같이 낸다.

| 단계 | 기간(안) | 내용 |
|---|---|---|
| 0. 결정 | 11/14~11/16 | 위 '먼저 정할 것' 확정. Search Console 도메인 인증과 구글 브랜드 인증 신청(며칠 걸려 가장 먼저 한다) |
| 1. 웹·회원 API | 11/17~11/23 | OAuth 클라이언트·동의 화면, `tools/account` 앱스 스크립트·시트, `/privacy`·`/terms`·`/link`·`/account`(ko·en), 머리줄 로그인. 이 단계만으로도 웹 가입은 된다 |
| 2. 플러그인 0.4.0 | 11/24~12/04 | 위 표. 배포 전 점검 셋(check_tiles, 키 없는 실제 설치 화면, personas 문제 0건) + 로그인 실기 — Rhino 8 Mac·Windows, Rhino 7, SketchUp, Archicad에서 한 번씩 로그인 → 생성 → 로그아웃. Rhino 세 파일을 같은 버전으로 |
| 3. 배포 뒤 | 12/05~12/18 | 매니페스트 업데이트 안내 문구(`groups` 새 기능에 '디테일 — 무료 회원'), 관리자 카드, food4Rhino·EW 문구, 웹 es·ja·zh 안내 |

## 하지 않는 것

- 자체 비밀번호 가입·이메일 인증 — 구글 로그인 하나로 끝낸다.
- 승인제·초대 코드.
- 토큰 서명·난독화·플러그인 안 검증 — 원본이 공개라 의미가 없다.
- 앱 안 웹뷰에서 구글 로그인 — 구글이 막는다.
- 첫 실행 로그인 강요.
- GA에 계정 id, 시트에 설치 ID.
- 결제(아직).

## 나중 — 돈을 받을 때

- **서버 쪽 잠금**: 서울 노면표시·가로수는 지금 컨텍스트 팩에 덧붙여 국내 서버(문지기)로 나간다(41bf893). 회원 전용 팩(`<시군구코드>_detail.db`)으로 떼고 문지기가 회원 토큰을 확인하면 진짜로 막힌다. 교량·선로·옹벽처럼 기본 팩으로 계산하는 디테일과 해외 OSM 디테일(공개 Overpass)은 서버로 막을 수 없다.
- 회원이 1만 명을 넘거나 하루 `me`가 앱스 스크립트 한도의 절반을 넘으면 Firebase 등으로 옮긴다(API 모양을 지키면 플러그인은 원격 설정 주소만 바뀐다).
- 결제 대행·환불·세금은 그때 따로 계획한다. 스토어 정책도 다시 본다(Blender는 그때도 로그인 불가).

## 확인 필요

- 앱스 스크립트 무료 한도(외부 요청 하루 약 2만 회, 동시 실행 30) — 실제 값.
- tokeninfo 엔드포인트 — 구글은 디버깅용이라고 한다. 적은 양에서는 괜찮다고 보지만 막히면 GIS의 서명 확인을 웹에서 하고 서버는 다시 확인하는 식으로 바꾼다.
- 앱스 스크립트 POST는 302로 googleusercontent에 넘어간다. 브라우저(문의 폼)는 문제가 없었다 — Rhino 8 CPython·번들 파이썬 3.12·Pyodide의 urllib에서 시험한다.
- SketchUp EW·food4Rhino가 외부 계정 연결을 어떻게 보는지 — 다음 제출 때 문의.
- 처리방침·동의 문구 — 초안을 만든 뒤 가능하면 한 번 검토받는다.
