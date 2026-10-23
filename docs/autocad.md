# AutoCAD판 (2026-10-18 착수)

AutoCAD판은 **3D를 내지 않는다.** 사무소는 AutoCAD로 3D 작업을 하지 않기 때문이다. 대신 바탕 도면으로 바로 쓸 수 있는 2D 현황도 DXF 한 장(`cad_<축척>.dxf`)을 만들고, 다른 판과 같은 현황도 SVG·.ai 베이스맵·조서 CSV를 함께 낸다.

## 구성

| 파일 | 하는 일 |
|---|---|
| `scripts/autocad_ext.lsp` | AutoCAD 명령 `GORANI` 하나. 파이썬 사이드카를 띄운다(Windows `startapp`, Mac은 `startapp`이 안 돼 acad.pgp의 `SHELL`). ActiveX를 쓰지 않아 Mac과 LT 2024+에서도 같은 파일이 돈다 |
| `scripts/cmd_autocad.py` | 사이드카 진입. 패널 서버(`panel_server`, 127.0.0.1 + 토큰)를 켜고 기본 브라우저로 패널을 연다. 이미 떠 있으면 그 주소만 다시 연다(`HOME_DIR/autocad_panel.json`) |
| `scripts/cad_dxf.py` | Prepared(세계좌표 m) → DXF R12. 표준 라이브러리만 쓴다 |
| `context_builder._run_cad_phase` | 호스트가 `autocad`(환경변수 `GORANI_HOST`)일 때 terrain·write_3dm 자리에서 DXF만 쓴다. 지형 메시와 베이크는 없다 |
| `dev_deploy.py autocad [--install]` | `build/autocad/Gorani.bundle`(PackageContents.xml + Contents/gorani.lsp + scripts) → zip. `--install`은 이 PC의 번들 폴더에 복사한다 |

AutoCAD 도면은 건드리지 않는다. 결과는 파일로만 나오고, 사용자가 AutoCAD에서 연다. AutoCAD에는 파이썬과 SQLite가 없어서 엔진은 사이드카에서 돈다.

## DXF 내용 (`constants.CAD_*`)

- **좌표·단위**: 모형 공간 1:1이고 단위는 mm(기본) 또는 m다. 좌표 방식은 기존 옵션을 따른다. 원점 방식이면 대상지 중심(100 m 내림)이 (0,0)이고, 그 자리에 기준점 십자가 있으며 TM 좌표는 도면 아래 글자로 적는다. 실제 좌표 방식이면 EPSG:5186 그대로다. 측량도나 수치지형도 DXF와 겹치려면 **m + 실제 좌표**를 고른다.
- **축척·범위**: 도면 축척(`cad_scale`, 1:100~1:1200, 기본 1:500)은 글자 크기만 정한다(1:500이면 지번 높이 0.75 m). AutoCAD판 기본값은 건축물 단위 작업에 맞춰 반경 100 m(최소 30 m)이고, .ai 베이스맵과 현황도 시트는 꺼져 있다. 패널 설정은 Rhino판과 따로 저장한다(`~/.gorani/prefs_autocad.json`). 2026-10-19 사용자 지적: 1:1000 이상과 큰 범위만으로는 사무소 CAD 작업에 맞지 않는다.
- **레이어 `US-*`**: 사무소 표준 레이어와 겹치지 않게 접두사를 붙였다. 바탕은 회색이고 대상지만 빨강이다. 색이 CTB 출력 펜을 정한다. 해치는 넣지 않는다.
  - 대상지·범위·지적선·건물 외곽·지상층수(`4F`)
  - 지번은 대상지와 인접 필지(대상지 bbox + 30 m)만 `US-LOT-NO`에 켜 둔다. 나머지는 `US-LOT-NO-ALL`에 넣고 레이어를 꺼 둔다. 필지마다 다 뜨면 너무 어지럽다는 2026-10-19 사용자 지적 때문이다.
  - 도로면 경계·도로중심선·도로명과 현황 도로폭. 도로폭은 수치지형도 값이므로 법정 폭은 지적도와 도시계획도로로 확인해야 한다.
  - 철도·하천·녹지
  - 등고선 주곡선·계곡선. 2D 폴리선이지만 고도 값으로 표고를 담는다. 계곡선 표고 글자와 표고점(POINT, Z = 표고)도 넣는다.
  - 용도지역과 지구단위계획구역 경계·이름, 도시계획시설 도로(저촉 확인용)
  - 기준점·방위표. 도면 아래에 자료 출처·기준일과 레이어 범례를 적는다.
- **글꼴**: `romans.shx` + 한글 큰 글꼴 `whgtxt.shx`(국내 사무소 관행). AutoCAD가 Win과 Mac 모두 함께 깔고, 호환 CAD도 갖고 있다. TrueType(Mac AppleSDGothicNeo.ttc)은 AutoCAD 2027 Mac에서 한글이 전부 '?'로 나왔다.
- **형식은 R12(AC1009)**: 한글은 CP949로 쓴다. AutoCAD, LT, ZWCAD, 캐디안, BricsCAD가 모두 연다. 선굵기는 없다(사무소 출력은 색 → CTB). R2000을 먼저 시험했는데 ezdxf 감사는 통과했지만 AutoCAD 2027 Mac이 열다가 멈췄다.
- 성수 fixture 기준으로 R=500 1:1000은 객체 4,663개, 1.9 MB, 0.1 s다.

## 처음 써 보기 (이 Mac, AutoCAD 2027)

1. 번들 설치: `python3 scripts/dev_deploy.py autocad --install`을 실행하면 `~/Library/Application Support/Autodesk/ApplicationAddins/Gorani.bundle`에 복사된다.
2. AutoCAD 아래쪽 명령줄에 다음을 붙여 넣고 Enter를 누른다. 보안 경고가 뜨면 [로드]를 누른다.
   `(load "/Users/sanghoon/Library/Application Support/Autodesk/ApplicationAddins/Gorani.bundle/Contents/gorani.lsp")`
3. 명령줄에 `GORANI`를 입력하고 Enter를 누르면 브라우저에 패널이 뜬다. 패널을 띄우지 못했다는 메시지가 나오면 거기 적힌 명령을 터미널에서 실행한다.
4. 패널에서 대상지를 고르고 '도면 설정'에서 단위·축척을 정한 뒤 [CAD 도면 만들기]를 누른다. DXF는 `~/Gorani/result/<대상지>_<날짜>/2D/cad_<축척>.dxf`에 남는다.
5. 지금 도면에 넣기: Windows는 생성이 끝나면 사이드카가 COM(`AutoCAD.Application.SendCommand`)으로 `(gorani:insert-pending)`을 불러 0,0에 블록(`Gorani_<결과 폴더>`)으로 넣고 줌한다. 맥·LT·COM 실패면 `~/Gorani/autocad_insert.txt`에 남기고, `GORANI`를 다시 치면 그때 넣는다. 설치 자리는 신뢰 위치 `C:\Program Files\Autodesk\ApplicationPlugins` — `%APPDATA%`는 SECURELOAD=1에서 LISP 로드가 막혔다(2026-10-23 노트북).

## 확인 필요

- Mac AutoCAD 2027: `startapp`은 띄우지 못했다. `SHELL`로 바꾼 뒤에는 패널이 열렸다(2026-10-19 사용자 확인). `~/Library/.../ApplicationAddins` 자동 로드는 아직 모른다 — 안 되면 위 2번처럼 `load`로 불러온다.
- 한글 SHX(`whgtxt.shx`) 표시. CP949 해석이 문제였다면 글꼴을 바꿔도 '?'가 남는다 — 그때는 `\U+XXXX`로 쓴다.
- Windows `%APPDATA%\Autodesk\ApplicationPlugins` 자동 로드와 `startapp`으로 띄운 `pythonw`.
- 회사 PC 보안 프로그램이 파이썬 실행이나 127.0.0.1 로컬 서버를 막는지.
- 현재 도면에 바로 넣기. 최신 INSERT 대화상자는 DWG만 받는다는 포럼 답변이 있고, CLASSICINSERT나 끌어다 놓기로는 DXF가 들어간다고 한다. 시험한 뒤에 명령으로 만든다.

## 남은 일 (2026-10-23 main에 옮긴 뒤)

- 2026-10-18~19 작업(`.claude/worktrees/autocad`, 커밋 안 됨)을 Gorani 이름·2화면 패널·다국어 위에 다시 얹었다. 명령은 `GORANI`, 번들은 `Gorani.bundle`, 환경변수는 `GORANI_HOST`(SketchUp·웹과 같은 `constants.HOST_ENV`).
- 번들 파이썬(`_stage_python`)을 `Contents/python/<플랫폼>/`에 넣는다. 지금은 Mac `/usr/bin/python3`, Windows PATH의 `pythonw`를 쓴다.
- `get_host_modules`의 autocad 몫을 `(mesh_geometry, None)`으로 바꾸면 표고·경사 시트가 찬다(번들 파이썬의 shapely 필요).
- DXF 안 글자(레이어 설명 범례·출처)는 아직 한국어만이다 — `output_lang`을 따르게 한다.
- AutoCAD에서 다시 열어 보는 확인: 이름을 바꾼 뒤로는 실기에서 돌려 보지 않았다.

## Autodesk 스토어 등록

절차·칸·문의 메일·개인정보 처리방침 초안은 `docs/autocad_store.md`.
