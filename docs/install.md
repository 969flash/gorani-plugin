# 설치

Rhino 8 전용. 파이썬·pip 패키지가 필요 없다(Rhino 내장 CPython + 표준 라이브러리만 쓴다).

## 1. 플러그인 설치

Rhino 8 명령창에 `PackageManager` → `UrbanDesignTool` 검색 → 설치 → Rhino를 다시 켠다.

## 2. 데이터 받기 (처음 한 번)

명령창에 `UrbanSite`(또는 `대지검토`)를 입력하면 패널이 열린다. 데이터가 없으면 패널이 [DB 받기]를 보여 준다.
누르면 서울 DB(압축 약 600 MB, 풀면 약 3.9 GB)를 받아 `~/UrbanDesignTool/data/`에 넣는다. 받는 동안 Rhino가 느려진다.

| 파일 | 내용 | 없으면 |
|---|---|---|
| `seoul_site.db` | 서울 필지 898,800건 — 필수 | 패널이 "준비 안 됨" 블로커를 띄운다 |
| `seoul_context.db` | 서울 건물·도로·수계 — 권장 | 필지·대상지만 생성되고 현황도 일부가 빈다 |
| `seoul_terrain.db` | 서울 등고선·표고점 | 지형 없이 평면으로 생성된다 |
| `~/UrbanDesignTool/.env` | `VWORLD_API_KEY=…`(건물 최신화·주소 보조검색), `DATA_GO_KR_KEY=…`(선택) | 없어도 동작. 패널 [.env 열기]가 템플릿을 만든다. `=` 뒤에 공백을 두지 말 것 |

## 3. 사용

- 결과는 `~/UrbanDesignTool/result/<날짜>/<대상지>/`에 쌓인다(`context.3dm`, `basemap_<축척>.ai`, `sheets/*.svg`, `tables/*.csv`, `log.txt`).
- 문서 단위는 mm·cm·m 아무거나 된다. 내부 계산은 m이고 베이크 때 문서 단위로 환산한다.
- 등고선·표고값·3D 컨텍스트는 온라인에 올리지 않는다(국토지리정보원 보안관리규정 별표1). 파일 납품만.

## 4. 문제가 생기면

- 패널이 안 열림: 명령창의 오류 메시지를 복사해 개발자에게.
- [DB 받기]가 멈췄다: 다시 누르면 그 파일부터 다시 받는다. 다 받은 파일은 다시 받지 않는다.
- .ai를 열 때 '레거시 텍스트 업데이트'를 묻는다: 업데이트하지 않아도 한글은 보인다.
- 로그: 결과 폴더 `log.txt`, 패널 진단 `임시폴더/urban_design_tool_panel_debug.log`.
