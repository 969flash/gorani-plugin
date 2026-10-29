# 설치

Rhino 7·8, Blender 4.2 이상, SketchUp 2022 이상. 파이썬·pip 패키지를 따로 깔 필요가 없다(프로그램 내장 파이썬 — SketchUp판·Rhino 7판은 패키지에 든 파이썬).
Blender는 아래 [Blender](#blender), SketchUp은 [SketchUp](#sketchup) 절.

## 1. 플러그인 설치

Rhino 8 명령창에 `PackageManager` → `Gorani` 검색 → 설치 → Rhino를 다시 켠다. Rhino 7도 같다 — PackageManager가 Rhino 7용 판을 골라 받는다.
Rhino 7판은 패널이 Mac은 Rhino 안 창, Windows는 Edge 창으로 열리고, DWG 저장이 없다.

## 2. 데이터 받기 (지역마다 처음 한 번)

명령창에 `Gorani`를 입력하면 패널이 열린다.

- **국내**: DB는 시군구 단위로 받는다(구 하나에 수십 MB). 처음이면 패널의 [지도에서 지역 골라 받기]를 누르고, 지도를 대상지로 옮긴 뒤 지도 왼쪽 아래 [받기]를 누른다. 받은 지역은 `~/Gorani/data/`에 남는다. 새 판이 나오면 같은 자리에 '새 판 있음'이 뜬다.
- **Global**: 패널 오른쪽 위 [Korea | Global] 토글에서 Global — DB 없이 어디서나. 건물·도로·지형은 생성할 때 OpenStreetMap·지형 타일에서 받는다(인터넷 필요). 필지·용도지역 도면은 Korea에만 있고, 건물 높이는 OSM 태그(없으면 기본값)다. 처음 실행은 한국(시간대·언어·국내 DB)이면 Korea로 시작한다.

| 파일(`~/Gorani/`) | 내용 |
|---|---|
| `data/<시군구코드>_site.db` | 필지·토지이용계획·계획 도형 |
| `data/<시군구코드>_context.db` | 건물·도로·수계·철도·녹지 |
| `data/<시군구코드>_terrain.db` | 등고선·표고점 |
| `.env` | `VWORLD_API_KEY=…`(선택, 본인 키 — 지도·위성 배경과 항공사진을 VWorld로, 주소 보조 검색). 없어도 같은 기능이 동작한다(지도는 OSM, 위성·항공사진은 Esri, 검색은 지명). 패널 [.env 열기]가 템플릿을 만든다. `=` 뒤에 공백을 두지 말 것 |

## 3. 사용

- 결과는 `~/Gorani/result/<대상지>_<날짜>/`에 쌓인다(`context.3dm`, `log.txt`, 2D 자료는 만들 때마다 `2D_<스타일>_<시각>/` 안에 `basemap_<축척>.ai`, `sheets/*.svg`, `tables/*.csv`). 같은 대상지를 같은 날 다시 만들면 `<대상지>_<날짜>_<시각>/` 새 폴더에 쌓이고 이전 결과는 남는다.
- 문서 단위는 mm·cm·m 아무거나 된다. 내부 계산은 m이고 베이크 때 문서 단위로 환산한다.
- 등고선·표고값·3D 컨텍스트는 온라인에 올리지 않는다(국토지리정보원 보안관리규정 별표1). 파일 납품만.

## 4. 문제가 생기면

- 패널이 안 열림: 명령창의 오류 메시지를 복사해 개발자에게.
- [받기]가 멈췄다: 다시 누르면 남은 팩만 받는다.
- 해외 생성이 실패: OSM 서버(Overpass)가 붐빌 때가 있다 — 잠시 뒤 다시.
- .ai를 열 때 '레거시 텍스트 업데이트'를 묻는다: 업데이트하지 않아도 한글은 보인다.
- 로그: 결과 폴더 `log.txt`, 패널 진단 `임시폴더/gorani_panel_debug.log`.

## Blender

1. 설치 — Blender 환경 설정 > Get Extensions에서 Gorani를 검색해 [Install](공식 확장 저장소 extensions.blender.org — 심사 통과 뒤). 새 판도 여기서 받는다.
   zip 파일을 받았으면 Get Extensions > 오른쪽 위 ⌄ > Install from Disk.
2. 명령줄·AI 에이전트:
   ```
   blender -c extension install -s -e gorani
   ```
   zip이면 `blender -c extension install-file -r user_default -e gorani-<버전>.zip`.
3. 환경 설정 > 시스템 > 네트워크 > **온라인 접근 허용**(Allow Online Access)을 켠다(지도·지역 데이터를 받는다).
4. 3D 뷰 사이드바(N) > Gorani > [Open Panel](한국어 인터페이스면 [패널 열기]) 또는 파일 > 가져오기 > Gorani Site Context —
   패널이 기본 브라우저 탭으로 열린다(Blender 안에는 웹 창이 없다). 쓰는 법은 Rhino와 같다. 브라우저 창이 넓으면 지도가 왼쪽, 설정이 오른쪽에 온다.
   생성 중에는 Blender 화면이 멈추고 진행률은 브라우저에 보인다. 탭을 닫았으면 [Open Panel]을 다시 누른다(앞 탭은 '새 탭에서 열렸습니다'로 멈춘다).

- 데이터·결과 폴더는 Rhino와 같다(`~/Gorani`) — 한쪽에서 받은 지역은 다른 쪽도 쓴다.
- 3D는 장면의 컬렉션 `CTX::…`와 사본 `context.blend`(열면 'Gorani' 장면). 건물은 메시 하나이고 면 속성 `height`·`floors`·`building_id`가 있다(지오메트리 노드로 색칠). 필지는 레이어마다 커브 하나로 묶여 PNU 속성이 없다(대상 필지 `CTX::Site`만 필지마다).
- 장면 단위는 m로 둔다(Blender 기본). Rhino판의 2D 도면 레이어(BM::)·DWG 저장은 없다 — `basemap_<축척>.ai`·`sheets/*.svg`를 쓴다.
- 위성 영상(지도 [위성]·항공사진 도면)은 없다 — 확장 스토어 약관이 상용 영상 서비스(Esri)를 막는다. 업데이트 안내 창도 띄우지 않는다(Blender가 확장 업데이트를 알린다).
- [Blender 커브 가져오기]는 닫힌(Cyclic) 커브 객체 하나를 쓴다. 미리 선택해 두면 바로, 아니면 누른 뒤 1분 안에 Blender에서 고르면 가져온다(Rhino 고르기와 같다). 베지어는 곡선을 따라 나눈다.

## SketchUp

1. 설치 — 확장 > Extension Warehouse에서 Gorani [설치]. `.rbz` 파일을 받았으면 확장 > 확장 관리자(Extension Manager) > [Install Extension]으로 고른다.
   Extension Warehouse를 거치지 않은 `.rbz`(서명 없음)는 확장 관리자 왼쪽 아래 톱니 > Loading Policy를 **Unrestricted**로 둬야 켜진다.
2. 확장 > Gorani(또는 Gorani 도구 막대 단추) — 패널 창이 열린다. 쓰는 법은 Rhino와 같다.
   생성 중 모델에 넣는 동안(몇 초~수십 초) SketchUp 화면이 멈춘다. 계산은 확장에 든 파이썬이 따로 돌린다.
   만드는 중에 패널 창을 닫으면 Rhino처럼 멈춘다(넣다 만 3D는 다시 만들면 지워진다).

- 데이터·결과 폴더는 Rhino·Blender와 같다(`~/Gorani`) — 한쪽에서 받은 지역은 다른 쪽도 쓴다.
- 3D는 대상지마다 그룹 `Gorani <대상지명>` 하나. 안에 태그 `CTX::…`(태그 폴더 CTX)마다 그룹이 있고, 건물은 동마다 솔리드 그룹이다(속성 사전 `Gorani`에 높이·층수·PNU — Entity Info > 고급 속성 또는 속성 확장으로 본다). 한 번의 생성은 실행 취소 한 번으로 지운다.
- 사본 `context.skp`는 대상지 그룹만 담은 파일이다(좌표는 대상지 중심 기준 — `context.json` origin).
- Rhino판의 2D 도면 레이어(BM::)·DWG 저장은 없다 — `basemap_<축척>.ai`·`sheets/*.svg`를 쓴다.
- [SketchUp 커브 가져오기]는 면 하나, 또는 끊김 없이 한 바퀴 닫힌 선들을 먼저 선택하고 누른다.
- 문제가 생기면 `~/Gorani/sketchup_sidecar.log`(계산 쪽 기록)와 창 > Ruby 콘솔을 본다.

## 5. 사용 통계

도구를 고치고 어디서 얼마나 쓰이는지 알기 위해 Google Analytics로 아래를 보낸다. 이름·파일 경로·도면 내용은 보내지 않는다.
SketchUp판은 패널에서 [보내기]를 고른 사람만 보낸다(처음 한 번 묻고, 더보기 메뉴 > 설정 > 사용 통계에서 바꾼다).
Blender판은 보내지 않는다(확장 스토어 심사가 동의를 받아도 분석 전송을 받지 않는다).

- 설치마다 만든 무작위 ID, 패널·Rhino(또는 SketchUp) 버전, OS·언어
- 생성한 대상지 — 필지 PNU·중심 좌표, 구역은 중심·면적·크기, 위치는 그 좌표
- 범위·결과·걸린 시간·건물 수, 받은 데이터 팩 지역, 예상 밖 오류 종류

국내 지역 데이터(건물·도로·등고선)를 받을 때는 같은 무작위 ID를 국내 서버(Oracle 춘천)에 함께 보낸다. 하루 받기 한도를 설치마다 세는 데만 쓴다.

패널을 열 때 지도 첫 위치를 정하려고 ipinfo.io에 한 번 접속한다. 접속 IP로 도시를 짐작할 뿐 그 위치를 저장하거나 보내지 않는다. Blender판은 접속하지 않는다(서울시청에서 연다 — 확장 스토어 약관).
