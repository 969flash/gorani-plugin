# SketchUp Extension Warehouse 올리기

처음 한 번:

1. `python3 scripts/dev_deploy.py sketchup` → `build/bsh_gorani-<버전>.rbz`(약 90 MB, 런타임 tar는 `build/cache/`에 남아 다음 빌드는 받지 않는다).
2. 이 Mac에서 먼저 써 본다 — SketchUp > 확장 > Extension Manager > Install Extension > rbz.
   서명 전이라 Extension Manager 왼쪽 아래 톱니 > Loading Policy = Unrestricted가 필요하다(올린 판은 Warehouse가 서명한다).
3. https://extensions.sketchup.com 에 Trimble ID로 로그인 → 개발자 등록(지원 연락처 필수 — 이메일 또는 웹사이트 `https://969flash.github.io/gorani/`).
4. Upload Extension → rbz → 설명·분류·지원 SketchUp 판(2022 이상)·OS(Windows·macOS)·가격(무료)·스크린샷 → 심사 제출.
   설명은 웹사이트 소개 문안을 쓰고, 아이콘·스크린샷은 `docs/blender_store/`의 `icon.html`·`featured.html`과 같은 방법으로 만든다(칸 크기는 업로드 화면 안내대로 — 확인 필요).
5. 심사 결과는 메일로 온다. 고칠 것이 오면 버전을 올려 다시 빌드하고 같은 확장 페이지에 새 판을 올린다.

새 판: `dev_deploy.py`의 `PACKAGE_VERSION`을 올린다 → 1번 → 확장 페이지에서 새 판 업로드.

심사 규칙에 맞춘 것(이미 반영):
- rbz 뿌리에 `bsh_gorani.rb` 하나 + 같은 이름 폴더 하나, Ruby는 전부 `BSH::Gorani` 안.
- 사용 통계는 동의한 사람만(패널이 처음 한 번 묻는다). `constants.GA_STREAMS`에 `sketchup` 속성을 넣기 전에는 묻지도 보내지도 않는다 —
  GA4에서 속성 'Gorani SketchUp'을 만들고 측정 ID·API secret을 넣는다(Blender판과 같은 절차).
- 번들 파이썬·라이브러리 약관 사본: `python/<플랫폼>/…/LICENSE.txt`(PSF), `site-packages/*.dist-info/licenses/`(numpy BSD, shapely BSD·GEOS LGPL),
  `scripts/vendor/LICENSE-leaflet.txt`·`LICENSE-pretendard.txt`(OFL). Shewchuk triangle(상업 사용 제한)은 쓰지 않는다.
- 확장 폴더에 아무것도 쓰지 않는다(사이드카 `-B`, 데이터·결과·로그는 `~/Gorani`) — 서명한 파일 목록이 바뀌지 않는다.

심사에서 물을 만한 것 — 답:
- 왜 실행 파일이 들어 있나: SketchUp에 파이썬이 없어 엔진(파이썬)을 python-build-standalone로 함께 넣었다. 127.0.0.1에만 열고 세션 토큰이 없으면 거부한다.
- 인터넷 접속: 지역 데이터 팩 받기(Hugging Face·국내 서버), 해외 대상지 OpenStreetMap, 지도 타일, (동의 시) 사용 통계 — 패널을 열어 쓸 때만.
