"""브랜드 아이콘 생성 (Rhino 밖 python3, 표준 라이브러리만).

    python3 scripts/dev_brand.py

아래 ICONS 표가 패널 아이콘의 원본이다. 고치고 돌리면 docs/brand/에
icons/<이름>.svg · icons/sprite.svg(site_ui.html에 넣을 심볼) · icons/run/gorani_run_<n>.svg(로딩 8장) · ui_kit.html(시트)을 다시 쓴다.
시트 틀은 docs/brand/ui_kit_template.html, 마크는 docs/brand/gorani_mark*.svg.
"""

import html
import math
import os
import re

# 패널 아이콘 — 16 칸, 선 1.5, 둥근 끝·둥근 이음(Claude 데스크톱 앱 같은 단순한 선 아이콘)
# (이름, 쓰는 버튼, 내용) — 내용은 <path>·<circle>·<rect> 조각. fill="cf" = 면 채움
ICONS = [
  # 공통 이동·상태
  ("check", "완료·적용·닫기(그리기 완료)", '<path d="M3.5 8.5l3 3 6-7"/>'),
  ("x", "필지 빼기·닫기", '<path d="M4 4l8 8M12 4l-8 8"/>'),
  ("back", "지도로·범위 바꾸기·스타일에서 결과로", '<path d="M10 3.5 5.5 8l4.5 4.5"/>'),
  ("next", "최근 대상지 줄·지도로 이동", '<path d="M6 3.5 10.5 8 6 12.5"/>'),
  ("down", "펼치기(레이어·도면 고르기)", '<path d="M3.5 6 8 10.5 12.5 6"/>'),
  ("plus", "새 대상지·다른 2D도 만들기", '<path d="M8 3v10M3 8h10"/>'),
  ("menu", "더보기 메뉴", '<path d="M2.5 4h11M2.5 8h11M2.5 12h11"/>'),
  ("search", "주소·지번 검색", '<circle cx="7" cy="7" r="4.5"/><path d="M10.5 10.5l3 3"/>'),
  ("ext", "토지이음·외부 링크", '<path d="M9.5 2.5h4v4M13.5 2.5 7.5 8.5M12 9.5v3a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1h3"/>'),
  ("warn", "경고 줄", '<path d="M7.1 2.6a1 1 0 0 1 1.8 0l5.3 9.6a1 1 0 0 1-.9 1.5H2.7a1 1 0 0 1-.9-1.5z"/><path d="M8 6.5v3M8 11.5h.01"/>'),
  ("info", "안내", '<circle cx="8" cy="8" r="6.5"/><path d="M8 7.5v4M8 5h.01"/>'),
  ("lock", "잠긴 범례 줄(관행색·출처)", '<rect x="3.5" y="7" width="9" height="6.5" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 0 1 5 0v2"/>'),
  ("dot", "범례 — 켜짐", '<rect x="4.5" y="4.5" width="7" height="7" rx="2" fill="cf"/>'),
  ("ring", "범례 — 꺼짐", '<rect x="4.5" y="4.5" width="7" height="7" rx="2"/>'),
  # 대상지 방식
  ("lots", "방식: 필지로 고르기", '<path d="M2.5 5 10 2.5l3.5 7.5-9 3.5z" fill="cf" fill-opacity=".18"/>'),
  ("area", "방식: 구역 그리기", '<path d="M2.5 4 9.5 2.5l4 4.5-2 6.5-8.5-1z" stroke-dasharray="2.2 2"/>'),
  ("point", "방식: 위치만 찍기", '<circle cx="8" cy="8" r="5.5"/><circle cx="8" cy="8" r="1.5" fill="cf"/>'),
  # 대상지 도구
  ("pen", "지도에 그리기·다시 그리기", '<path d="M11 2.6a1.6 1.6 0 0 1 2.4 2.4L5 13.4l-3 .6.6-3z"/><path d="M9.5 4l2.5 2.5"/>'),
  ("curve", "Rhino 커브 가져오기", '<path d="M4.5 11.5C5.5 7.5 8.5 5 11.5 4.5"/><circle cx="3.5" cy="12.5" r="1.5"/><circle cx="12.5" cy="3.5" r="1.5"/>'),
  ("move", "구역 옮기기·위치 놓기", '<path d="M8 1.5v13M1.5 8h13M6 3.5l2-2 2 2M6 12.5l2 2 2-2M3.5 6l-2 2 2 2M12.5 6l2 2-2 2"/>'),
  ("trash", "지우기", '<path d="M2.5 4h11M6.5 4V2.5h3V4M3.8 4l.6 8.6a1 1 0 0 0 1 .9h5.2a1 1 0 0 0 1-.9l.6-8.6M6.5 7v4M9.5 7v4"/>'),
  ("focus", "대상지로 줌", '<path d="M2 5.5v-2A1.5 1.5 0 0 1 3.5 2h2M10.5 2h2A1.5 1.5 0 0 1 14 3.5v2M14 10.5v2a1.5 1.5 0 0 1-1.5 1.5h-2M5.5 14h-2A1.5 1.5 0 0 1 2 12.5v-2"/><circle cx="8" cy="8" r="2"/>'),
  ("globe", "Global·OpenStreetMap으로 쓰기", '<circle cx="8" cy="8" r="6.5"/><path d="M1.5 8h13M8 1.5c-2.3 2-2.3 11 0 13M8 1.5c2.3 2 2.3 11 0 13"/>'),
  # 만들기·결과
  ("cube", "3D 모델 만들기·3D 결과", '<path d="M8 1.75 13.75 5v6L8 14.25 2.25 11V5z"/><path d="M2.25 5 8 8.25 13.75 5M8 8.25v6"/>'),
  ("plan", "2D 만들기·2D 결과", '<rect x="2.5" y="2.5" width="11" height="11" rx="1.5"/><path d="M2.5 7.5H7v6M9.5 2.5V6h4"/>'),
  ("map", "베이스맵", '<path d="M1.5 3.5 5.5 2l5 1.5 4-1.5v10.5l-4 1.5-5-1.5-4 1.5z"/><path d="M5.5 2v10.5M10.5 3.5V14"/>'),
  ("layers", "베이스맵 레이어", '<path d="M8 1.75 14.25 5 8 8.25 1.75 5z"/><path d="M1.75 8 8 11.25 14.25 8M1.75 11 8 14.25 14.25 11"/>'),
  ("grid", "현황도 시트", '<rect x="2" y="2" width="5" height="5" rx="1"/><rect x="9" y="2" width="5" height="5" rx="1"/><rect x="2" y="9" width="5" height="5" rx="1"/><rect x="9" y="9" width="5" height="5" rx="1"/>'),
  ("table", "조서 CSV", '<rect x="2" y="3" width="12" height="10" rx="1.5"/><path d="M2 6.5h12M2 10h12M6.5 6.5V13"/>'),
  ("import", "Rhino에 불러오기·다시 불러오기", '<path d="M9.5 2.5h3a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1h-3M2 8h7.5M6.5 5l3 3-3 3"/>'),
  ("export", ".ai 내보내기·.ai 모두", '<path d="M6.5 2.5h-3a1 1 0 0 0-1 1v9a1 1 0 0 0 1 1h3M6 8h7.5M10.5 5l3 3-3 3"/>'),
  ("download", "지역 자료 받기·다시 받기·3dm 받기", '<path d="M8 2v8M4.5 6.5 8 10l3.5-3.5M2.5 10.5v2a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-2"/>'),
  ("eye", "3D 보기(웹판)", '<path d="M1.5 8S4 3.5 8 3.5 14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z"/><circle cx="8" cy="8" r="2"/>'),
  ("folder", "파일 위치 열기·폴더", '<path d="M2 4.5a1 1 0 0 1 1-1h3l1.5 1.5H13a1 1 0 0 1 1 1v6.5a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1z"/>'),
  ("file", "log.txt·산출물 파일", '<path d="M9 1.5H4.5a1 1 0 0 0-1 1v11a1 1 0 0 0 1 1h7a1 1 0 0 0 1-1V5zM9 1.5V5h3.5"/>'),
  ("copy", "로그 복사", '<rect x="5.5" y="5.5" width="8" height="8" rx="1.5"/><path d="M10.5 5.5v-2a1 1 0 0 0-1-1h-6a1 1 0 0 0-1 1v6a1 1 0 0 0 1 1h2"/>'),
  ("stop", "생성 취소·받기 멈추기", '<rect x="4" y="4" width="8" height="8" rx="1.5"/>'),
  ("refresh", "다시 시도·다시 확인", '<path d="M14 8a6 6 0 1 1-6-6c1.7 0 3.3.7 4.5 1.8L14 5.3"/><path d="M14 2v3.3h-3.3"/>'),
  # 스타일·메뉴
  ("palette", "도면 스타일", '<path d="M8 1.5a6.5 6.5 0 0 0 0 13c.9 0 1.5-.6 1.5-1.4 0-.9-.7-1.2-.7-2s.6-1.3 1.4-1.3h1.6a2.7 2.7 0 0 0 2.7-2.7C14.5 4 11.6 1.5 8 1.5z"/><circle cx="5" cy="7" r=".9" fill="cf"/><circle cx="8" cy="4.6" r=".9" fill="cf"/><circle cx="11" cy="6.6" r=".9" fill="cf"/>'),
  ("save", "스타일 저장", '<path d="M3.5 2.5h7l3 3v7a1 1 0 0 1-1 1h-9a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/><path d="M5 2.5v3h5M5 13.5v-4h6v4"/>'),
  ("undo", "되돌리기", '<path d="M5.5 2.5 2.5 5.5l3 3M2.5 5.5h7a4 4 0 0 1 0 8H6"/>'),
  ("clock", "최근 대상지", '<circle cx="8" cy="8" r="6.5"/><path d="M8 4.5V8l2.5 1.5"/>'),
  ("key", "API 키", '<circle cx="5.5" cy="10.5" r="3"/><path d="M7.6 8.4 13.5 2.5M11.5 4.5l2 2M9.8 6.2l1.5 1.5"/>'),
  ("database", "지역 자료(데이터 팩)", '<ellipse cx="8" cy="3.75" rx="5.5" ry="2"/><path d="M2.5 3.75v8.5c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2v-8.5M2.5 8c0 1.1 2.5 2 5.5 2s5.5-.9 5.5-2"/>'),
]

BRAND = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "brand")
ICON_DIR = os.path.join(BRAND, "icons")
ATTR = 'fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"'

def inner(s):
    return s.replace('fill="cf"', 'fill="currentColor"')

for name, use, body in ICONS:
    with open(os.path.join(ICON_DIR, name + ".svg"), "w") as f:
        f.write('<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 16 16" %s>%s</svg>\n' % (ATTR, inner(body)))

mark_small = re.search(r'd="([^"]*)"', open(os.path.join(BRAND, "gorani_mark_small.svg")).read()).group(1)
mark = re.search(r'd="([^"]*)"', open(os.path.join(BRAND, "gorani_mark.svg")).read()).group(1)
symbols = "\n".join('  <symbol id="i-%s" viewBox="0 0 16 16">%s</symbol>' % (n, inner(b)) for n, u, b in ICONS)
symbols += '\n  <symbol id="i-gorani" viewBox="0 0 256 256"><path d="%s" fill="currentColor" stroke="none" fill-rule="evenodd"/></symbol>' % mark_small
sprite = ('<!-- Gorani 패널 아이콘 스프라이트 — site_ui.html의 숨은 <svg><defs>에 그대로 넣는다. 원본 목록·쓰는 버튼: docs/brand/ui_kit.html\n'
          '     쓰는 쪽 CSS: .ico { width:16px; height:16px; fill:none; stroke:currentColor; stroke-width:1.5; stroke-linecap:round; stroke-linejoin:round }\n'
          '     i-gorani는 면 아이콘(브랜드) — 24 px 이하용 작은 판 path -->\n'
          '<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute" aria-hidden="true"><defs>\n%s\n</defs></svg>\n') % symbols
open(os.path.join(ICON_DIR, "sprite.svg"), "w").write(sprite)

# ── 달리는 고라니 8장 (docs/brand/concepts.html runFrame과 같은 식) ──
BODY = ["M13 21C13 14 20 11 27 13C33 15 39 17 44 19C49 21 49 29 43 30.5C35 32 26 31 19 29.5C15 28.5 13 25 13 21Z",
        "M40 21C43 15 47 11 51 9L56 13C52 17 48 23 46 29Z",
        "M49 7C53 4.5 58 6.5 62 11C63.5 13 62.5 15 60.5 15H54C50.5 15 48 11.5 49 7Z",
        "M51 8C49 3 45.5 0 42 0.5C42 4 45 8 49.5 11Z",
        "M14 17C12 14.5 11 12.5 11.5 11C13.5 12 15 14 16 16Z"]
def leg(hip, l1, l2, a, b, w1, w2):
    r = math.pi / 180
    kx, ky = hip[0] + l1 * math.sin(a * r), hip[1] + l1 * math.cos(a * r)
    fx, fy = kx + l2 * math.sin(b * r), ky + l2 * math.cos(b * r)
    return ('<path d="M%.2f %.2fL%.2f %.2f" stroke-width="%s"/><path d="M%.2f %.2fL%.2f %.2f" stroke-width="%s"/>'
            % (hip[0], hip[1], kx, ky, w1, kx, ky, fx, fy, w2))
def run_svg(i, n=8):
    p = i / n
    s = lambda o: math.sin(2 * math.pi * (p + o)); c = lambda o: math.cos(2 * math.pi * (p + o))
    bob = -1.6 * math.cos(4 * math.pi * p); legs = ""
    for o in (0.1, 0):
        ah = -38 * s(o); bh = ah - 28 - 46 * max(0, -c(o))
        af = 42 * s(o); bf = af - 85 * max(0, c(o))
        legs += leg((21, 24 + bob), 10, 13, ah, bh, 5, 2.6) + leg((41, 26 + bob), 9, 12, af, bf, 3.6, 2.4)
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="64" height="48" viewBox="0 0 64 48">'
            '<g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round">%s</g>'
            '<g fill="currentColor" transform="translate(0 %.2f)">%s</g></svg>' % (legs, bob, "".join('<path d="%s"/>' % d for d in BODY)))
runs = [run_svg(i) for i in range(8)]
for i, sv in enumerate(runs):
    open(os.path.join(ICON_DIR, "run", "gorani_run_%d.svg" % (i + 1)), "w").write(sv + "\n")

# ── UI 키트 시트 ──
def ico(n, size=16):
    return '<svg class="ico" width="%d" height="%d" aria-hidden="true"><use href="#i-%s"/></svg>' % (size, size, n)
cells = "".join('<div class="ic"><div class="g">%s%s</div><b>%s</b><span>%s</span></div>' % (ico(n, 24), ico(n), n, html.escape(u)) for n, u, b in ICONS)
MAP = [  # (화면, 버튼 문구, data-act, 아이콘, 버튼 종류)
  ("지도", "3D 모델 만들기", "generate", "cube", "주 버튼"),
  ("지도", "필지·구역·위치", "mode", "lots · area · point", "세그먼트"),
  ("지도", "Korea · Global", "region", "— (글자)", "세그먼트"),
  ("지도", "검색", "search", "search", "입력칸 안 아이콘"),
  ("지도", "더보기", "menu", "menu", "아이콘 버튼"),
  ("지도", "지도에 그리기 · 다시 그리기", "draw_start", "pen", "작은 버튼"),
  ("지도", "Rhino 커브 가져오기", "pick_curve", "curve", "작은 버튼"),
  ("지도", "옮기기 · 여기에 놓기", "area_move · stamp_place", "move", "작은 버튼"),
  ("지도", "완료(그리기 닫기)", "draw_done", "check", "작은 주 버튼"),
  ("지도", "취소(그리기·놓기)", "draw_cancel · stamp_cancel", "— (글자)", "작은 고스트"),
  ("지도", "지우기 · 모두 지움", "clear · area_clear · point_clear", "trash", "위험 고스트"),
  ("지도", "필지 빼기", "remove", "x", "아이콘 버튼(작게)"),
  ("지도", "토지이음", "eum", "ext", "링크"),
  ("지도", "다시 받기 · 멈추기", "download_area · download_stop", "download · stop", "작은 버튼"),
  ("결과", "취소(생성 중)", "cancel", "stop", "보조 버튼"),
  ("결과", "Rhino에 불러오기 · 다시 불러오기", "import", "import", "주 버튼 · 링크"),
  ("결과", "3D 보기(웹)", "import", "eye", "보조 버튼"),
  ("결과", "파일 위치 열기", "open", "folder", "보조 버튼"),
  ("결과", "3dm 받기(웹)", "open", "download", "보조 버튼"),
  ("결과", "2D 만들기", "make2d", "plan", "주 버튼"),
  ("결과", "다른 2D도 만들기", "form2d", "plus", "작은 버튼"),
  ("결과", ".ai 더 내보내기 · .ai 모두", "export · sheet_ai_all", "export", "작은 버튼"),
  ("결과", "스타일", "style_open", "palette", "보조 버튼"),
  ("결과", "로그 복사", "copylog", "copy", "작은 버튼"),
  ("결과", "log.txt", "open", "file", "링크"),
  ("결과", "지도로 · 범위 바꾸기", "back · rerange", "back", "고스트"),
  ("결과", "새 대상지", "newlot", "plus", "보조 버튼"),
  ("결과", "다시 시도", "retry", "refresh", "주 버튼"),
  ("스타일", "결과로", "style_back", "back", "아이콘 버튼"),
  ("스타일", "저장", "st_save · st_save_ok", "save", "보조 · 주 버튼"),
  ("스타일", "되돌리기", "st_revert", "undo", "고스트"),
  ("스타일", "n장에 적용", "st_apply", "check", "주 버튼"),
  ("메뉴", "최근 대상지 줄", "recent", "clock(제목) · next(줄)", "목록 줄"),
  ("메뉴", "폴더 · 지역 자료 · API 키 · 안내", "open · force_osm · open_url", "folder · database · key · info", "목록 줄"),
  ("메뉴", "OSM으로 · OpenStreetMap으로 쓰기", "force_osm · abroad", "globe", "작은 버튼"),
  ("공통", "다시 확인", "init", "refresh", "보조 버튼"),
  ("공통", "닫기(알림)", "dismiss", "x", "아이콘 버튼"),
  ("공통", "사용 통계 보내기·보내지 않음", "stats", "— (글자)", "작은 버튼"),
]
rows = "".join("<tr><td>%s</td><td>%s</td><td><code>%s</code></td><td>%s</td><td>%s</td></tr>" % (
    a, html.escape(b), html.escape(c),
    " ".join(ico(x.strip().split("(")[0]) for x in d.split("·") if x.strip() and not x.strip().startswith("—")) + " <span class='sub'>%s</span>" % html.escape(d), e) for a, b, c, d, e in MAP)
run_strip = "".join('<figure><div class="frame">%s</div><figcaption>%d</figcaption></figure>' % (sv, i + 1) for i, sv in enumerate(runs))

def comp_block():
    b = lambda cls, label, icon=None, extra="": '<button class="%s"%s>%s%s</button>' % (cls, extra, ico(icon) if icon else "", label)
    st = lambda cls, label, icon=None: "".join('<div class="st"><span class="sl">%s</span>%s</div>' % (n, b(cls + " " + c, label, icon, " disabled" if c == "is-dis" else "")) for n, c in (("기본", ""), ("올림", "is-hover"), ("누름", "is-active"), ("포커스", "is-focus"), ("비활성", "is-dis")))
    return (
      '<div class="crow"><h4>주 버튼</h4>%s</div>' % st("b primary", "3D 모델 만들기", "cube") +
      '<div class="crow"><h4>보조 버튼</h4>%s</div>' % st("b", "파일 위치 열기", "folder") +
      '<div class="crow"><h4>고스트</h4>%s</div>' % st("b ghost", "지도로", "back") +
      '<div class="crow"><h4>작은 버튼</h4>%s</div>' % st("b sm", "다시 그리기", "pen") +
      '<div class="crow"><h4>위험</h4>%s</div>' % st("b ghost danger sm", "지우기", "trash") +
      '<div class="crow"><h4>아이콘 버튼</h4><div class="st"><span class="sl">기본</span><div class="row"><button class="ib">%s</button><button class="ib">%s</button><button class="ib sm">%s</button></div></div><div class="st"><span class="sl">올림</span><button class="ib is-hover">%s</button></div><div class="st"><span class="sl">누름</span><button class="ib is-active">%s</button></div><div class="st"><span class="sl">포커스</span><button class="ib is-focus">%s</button></div></div>' % (ico("menu"), ico("search"), ico("x"), ico("menu"), ico("menu"), ico("menu")) +
      '<div class="crow"><h4>링크</h4><div class="st"><span class="sl">기본</span><a class="lk">토지이음%s</a></div><div class="st"><span class="sl">올림</span><a class="lk is-hover">토지이음%s</a></div><div class="st"><span class="sl">파일</span><a class="lk">%slog.txt</a></div></div>' % (ico("ext"), ico("ext"), ico("file")) +
      '<div class="crow"><h4>세그먼트</h4><div class="seg"><button aria-pressed="true">%s필지</button><button>%s구역</button><button>%s위치</button></div><div class="seg"><button aria-pressed="true">Korea</button><button>Global</button></div></div>' % (ico("lots"), ico("area"), ico("point")) +
      '<div class="crow"><h4>칩 토글</h4><div class="chips"><button class="chip" aria-pressed="true">1:1000</button><button class="chip">1:3000</button><button class="chip">1:5000</button><button class="chip" disabled>1:10000</button></div></div>' +
      '<div class="crow"><h4>입력칸</h4><label class="field">%s<input placeholder="주소 · 지번 검색" readonly></label><label class="field is-focus">%s<input value="성수동2가 277-8" readonly></label></div>' % (ico("search"), ico("search")) +
      '<div class="crow"><h4>목록 줄</h4><div class="list"><div class="lh">%s최근 대상지</div><button class="li"><span>성수동2가 277-8 외 3</span><span class="sub">2,140 ㎡ · 10-18</span>%s</button><button class="li is-hover"><span>을지로3가 일대 구역</span><span class="sub">8,920 ㎡ · 10-15</span>%s</button><button class="li">%s<span>API 키</span><span class="sub">VWorld 1/1</span>%s</button></div></div>' % (ico("clock"), ico("next"), ico("next"), ico("key"), ico("next")) +
      '<div class="crow"><h4>카드</h4><div class="card"><div class="ch">%s<b>3D 모델</b><span class="sub">건물 1,842동 · 지형 · 수계</span></div><div class="ca"><button class="b primary sm">%sRhino에 불러오기</button><button class="b sm">%s파일 위치 열기</button></div></div>'
      '<div class="card warn"><div class="ch">%s<b>지형 일부 생략</b></div><p class="sub">수치지형도 도엽 2장이 없습니다 — 그 범위는 평지로 만들었습니다.</p><a class="lk">지도에서 보기%s</a></div></div>' % (ico("cube"), ico("import"), ico("folder"), ico("warn"), ico("next")) +
      '<div class="crow"><h4>진행</h4><div class="card prog"><div class="ch"><b>3D 모델 만드는 중</b><span class="sub">지형 만드는 중 · 46 %%</span></div><div class="track"><div class="fill"></div><div class="runner">%s</div></div><div class="ca"><button class="b sm">%s취소</button></div></div></div>' % (runs[3], ico("stop"))
    )

PAGE = open(os.path.join(BRAND, "ui_kit_template.html"), encoding="utf-8").read()
PAGE = (PAGE.replace("%%SPRITE%%", "\n".join(sprite.splitlines()[3:]))
            .replace("%%MARK%%", mark).replace("%%CELLS%%", cells).replace("%%ROWS%%", rows)
            .replace("%%RUNS%%", run_strip).replace("%%COMP%%", comp_block()).replace("%%COUNT%%", str(len(ICONS))))
open(os.path.join(BRAND, "ui_kit.html"), "w", encoding="utf-8").write(PAGE)
print(len(ICONS), "icons")
