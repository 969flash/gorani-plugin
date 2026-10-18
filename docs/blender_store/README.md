# Blender 확장 스토어(extensions.blender.org) 올리기

처음 한 번:

1. `python3 scripts/dev_deploy.py blender` → `build/blender_repo/gorani-<버전>.zip`
2. 대표 이미지·아이콘(웹사이트 저장소 `../gorani`가 옆에 있어야 한다):
   `featured.html`·`icon.html` 머리 주석의 Chrome 명령 → `build/blender_store/featured.png`(1920×1080)·`icon.png`(256×256)
3. https://extensions.blender.org 로그인(Blender ID) → Upload Extension → zip → 칸 채우기:
   Description = `description.md`(주석 줄 빼고), 아이콘·대표 이미지·미리보기(`build/blender_store/preview_*.png`) → Submit for Approval
4. 심사 댓글은 Blender ID 메일로 온다. 고칠 것이 오면 버전을 올려 다시 빌드하고 같은 페이지에서 새 버전을 올린다.

새 판: `dev_deploy.py`의 `PACKAGE_VERSION`을 올린다 → 1번 → 확장 페이지 Manage > Upload new version.
약관이 막는 것(이미 반영): GPL-3.0-or-later 원본 .py, 번들 글꼴·이미지는 CC0만(Pretendard 제외), 동의 없는 통계 전송 금지, 최상위 모듈·sys.path 금지, `bpy.app.online_access` 확인.
