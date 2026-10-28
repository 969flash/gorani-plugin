"""배포 빌더 — Yak 패키지와 데이터 팩을 만든다 (Rhino 밖 전용, macOS).

    python3 scripts/dev_deploy.py            # 둘 다
    python3 scripts/dev_deploy.py smoke      # 배포 전 점검만 — yak·blender·sketchup 빌드는 먼저 이걸 돌리고 실패하면 멈춘다
    python3 scripts/dev_deploy.py yak        # build/Gorani-<버전>-rh8_0-any.yak
    python3 scripts/dev_deploy.py blender    # build/blender_repo/gorani-<버전>.zip + index.json(정적 확장 저장소)
    python3 scripts/dev_deploy.py sketchup   # build/bsh_gorani-<버전>.rbz (Extension Warehouse·확장 관리자 설치)
    python3 scripts/dev_deploy.py web        # build/web/ (정적 파일 — 웹사이트 app/에 올린다)
    python3 scripts/dev_deploy.py packs      # build/packs/*.db.xz + manifest.json
    python3 scripts/dev_deploy.py packs --sido 43 --drop   # 시도 하나만 압축하고 원본 DB를 지운다(전국 빌드 흐름)
    python3 scripts/dev_deploy.py repack     # 시도 팩 압축본을 풀어 (줄이고) 시군구 팩으로 나눠 다시 압축
    python3 scripts/dev_deploy.py rebounds   # 매니페스트의 팩 범위만 다시 잰다(시군구 필지 중심점 핵심 범위 — constants.PACK_BOUNDS_*)
    python3 scripts/dev_deploy.py upload     # 필지 팩 + 매니페스트는 Hugging Face(hf auth login 먼저), 컨텍스트·등고선 팩은 국내 버킷(~/.oci/config 먼저)
    python3 scripts/dev_deploy.py notices    # docs/notices.json(업데이트·공지)·docs/countries.json(나라별 건물 팩 목록·services)을 Hugging Face 매니페스트에 넣고, config.json(원격 설정 — remote_config.build: 도면 색·범례·구간·코드표·파라미터·번역)을 같이 올린다 — 팩은 그대로. 새 나라·도면 색·번역 수정은 이것으로 끝(플러그인 판 없음)
    python3 scripts/dev_deploy.py config     # build/config.json만 만들어 본다(올리지 않음)
    python3 scripts/dev_deploy.py mirror     # Hugging Face 데이터셋 → GitHub 사본(constants.DATA_GITHUB_REPO, 팩은 Releases — Blender판이 읽는다). upload·notices 뒤에 돌린다

yak: 진입 명령 Gorani 하나짜리 .rhp를 rhinocode로 빌드하고(떠 있는 Rhino 8 필요), 그 옆에 scripts/(평문 진입 스크립트 +
     로직 .pyc + 패널 HTML·vendor)를 두고 yak CLI로 묶는다. rhinocode의 Shared 리소스는 폴더 구조를 펴 버려서 쓰지 않는다
     (2026-10-12 실측: scripts/vendor/b.txt → shared/b.txt). Gorani는 .rhp 옆 scripts/cmd_site.py를 그대로 실행한다.
blender: Blender 확장(4.2+) — gorani/__init__.py(scripts/cmd_blender.py로 넘김) + blender_manifest.toml + scripts/ 원본 .py·UI 에셋을
     Blender CLI(extension build)로 zip, 그 폴더에 server-generate로 index.json·index.html. 로직은 .pyc가 아니라 원본이다 — Blender 4.2~4.5는
     파이썬 3.11, 5.x는 3.13이라 .pyc 하나로 못 덮고, Blender 확장은 GPL이다. Rhino 전용(panel_host·cmd_install)과 dev_·server_는 뺀다.
sketchup: SketchUp 확장(.rbz = zip) — 뿌리 bsh_gorani.rb(등록) + bsh_gorani/main.rb(scripts/sketchup_ext.rb) + scripts/(평문 진입 스크립트
     + 로직 .pyc + 패널 HTML·vendor) + python/<플랫폼>/(python-build-standalone 3.12 + numpy·shapely, 플랫폼 셋: mac-arm64·mac-x64·win-x64).
     SketchUp에는 파이썬이 없어 확장이 번들 파이썬으로 사이드카(cmd_sketchup)를 띄운다. 런타임 tar는 build/cache/에 받아 둔다.
     .pyc는 번들 파이썬(3.12)으로 컴파일한다(unchecked-hash — zip이 수정 시각을 2초 단위로 줄여도 다시 컴파일하지 않는다).
web: 브라우저판 정적 파일 — index.html(scripts/web_app.html) + panel.html(site_ui.html에 vendor 주입, panel_server.get_html) + web_worker.js
     + scripts.zip(로직 원본 .py — 워커가 Pyodide 가상 파일계에 푼다). Pyodide·numpy·shapely·three.js는 CDN에서 받는다(web_worker.js·web_app.html 맨 위).
packs: data/의 시도별 `<시도>_site.db`·`<시도>_context.db`마다 필지(rtree 제거)·컨텍스트(등고선 제외)·등고선 팩을
       xz로 압축하고 sha256·범위를 매니페스트에 적는다. 컨텍스트·등고선 팩은 국내 서버에 올린다(constants.DATA_DOMESTIC_BASE_URL 주석).

`.pyc`는 Python 마이너 버전에 묶이므로 Rhino 8의 CPython과 같은 3.9로 실행해야 한다. macOS 기본 /usr/bin/python3가 3.9다.
"""

import argparse
import ast
import builtins
import datetime
import hashlib
import json
import os
import pkgutil
import py_compile
import re
import shutil
import sqlite3
import statistics
import subprocess
import symtable
import sys
import sysconfig
import tokenize

import shapely

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
import constants  # noqa: E402
import data_pack  # noqa: E402 — countries.json 검증은 런타임과 같은 함수로
import remote_config  # noqa: E402 — config.json(원격 설정)은 런타임과 같은 함수로 만들고 자가 점검한다

BUILD_DIR = os.path.join(ROOT_DIR, "build")
NOTICES_PATH = os.path.join(ROOT_DIR, "docs", "notices.json")   # 매니페스트 update·notices 원본 — 칸은 docs/panel_ui.md '업데이트·공지'
COUNTRIES_PATH = os.path.join(ROOT_DIR, "docs", "countries.json")   # 매니페스트 countries 원본 — 나라별 건물 팩 목록(data_pack.get_country_packs). 새 나라는 여기에만(플러그인 판 없이)
RHINO_BIN_DIR = "/Applications/Rhino 8.app/Contents/Resources/bin"
BRAND_DIR = os.path.join(ROOT_DIR, "docs", "brand")      # 로고 원본 SVG(currentColor)와 크기별 PNG — docs/brand/logo.html
TOOLBAR_ICON_COLORS = {"light": "#111418", "dark": "#E8ECF2"}   # Rhino 도구 막대 라이트·다크 아이콘 색 = DESIGN.md 잉크·다크 잉크

PACKAGE_NAME = constants.TOOL_NAME
PACKAGE_VERSION = constants.PANEL_VERSION                  # 올릴 때마다 constants.PANEL_VERSION을 올린다 — yak은 같은 버전을 다시 받지 않는다
PLUGIN_ID = "8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a10"         # 바꾸지 말 것 — Gorani가 이 id로 자기 폴더를 찾는다
COMMAND_ID = "8b0c1f5e-3d0a-4f53-9a6e-2c7e1d4b9a11"
COMMAND_NAME = "Gorani"
PUBLISHER = {"name": "sanghoon", "email": "bsh969flash@gmail.com"}
WEBSITE_URL = "https://969flash.github.io/gorani/en/"   # PackageManager 링크 — 영어 페이지(한국어 페이지는 거기서 링크, food4Rhino 심사 2026-10-21)
# yak manifest — rhinocode가 쓰는 manifest.yml은 url·검색어가 비고 버전에 +빌드번호가 붙는다. PackageManager 목록·검색에 보일 내용으로 갈아 쓴다.
# 설명은 영어를 먼저 쓴다(food4Rhino 심사 2026-10-21 — 영어가 없으면 올릴 수 없다).
# PackageManager 검색은 이름·설명·검색어를 다 본다(2026-10-19 yak search 실측 — 'terrain'·'roads'가 설명만으로 걸림). 설명은 쉬운 말로, 사람들이 찾을 낱말을 넣는다.
# guid: 검색어는 지우지 말 것 — Rhino가 이 플러그인 id로 패키지를 찾는다. 검색어는 영문·숫자·-·_만(공백이면 yak push가 400).
YAK_MANIFEST = '''name: %(name)s
version: %(version)s
authors:
- %(author)s
description: |-
  The city around your site, modeled in Rhino.
  It's free. The panel is in English, Korean, Spanish, Japanese and Chinese.

  How to use
  1. Restart Rhino after installing.
  2. Type Gorani.
  3. Pick a site on the map and press Create 3D model.

  What you get
  - 3D: buildings, roads, terrain, rivers, parks and railways on separate layers
  - 2D: Illustrator basemap, urban analysis maps, DWG, CSV tables
  - Data: Korea nationwide; official building data with heights where available (Japan, Netherlands, France, Switzerland, United States and more — the list grows without plugin updates, see the website); elsewhere OpenStreetMap

  한 번에 쉽게 하는 사이트 모델링 및 사이트 분석
  패널 언어는 위쪽 언어 버튼에서 한국어로 바꿀 수 있습니다.

  사용 방법
  1. 설치 후 라이노를 다시 켭니다.
  2. 명령창에 Gorani를 입력합니다.
  3. 지도에서 대상지를 고르고 [3D 모델 만들기]를 누릅니다.

  결과물
  - 3D: 건물 매스, 도로, 지형, 하천, 녹지, 철도 (레이어별)
  - 2D: 일러스트레이터 베이스맵, 현황도·분석도, DWG, 조서 CSV
  - 데이터: 국내 전국, 공식 건물 데이터(높이 포함)가 있는 나라는 그것(일본·네덜란드·프랑스·스위스·미국 등 — 플러그인 업데이트 없이 늘어납니다, 웹사이트 참고), 그 밖은 OpenStreetMap
license: MIT
url: %(url)s
icon: icon.png
keywords:
- gorani
- urban-design
- site-model
- context-model
- city-model
- 3d-city
- buildings
- terrain
- topography
- contours
- openstreetmap
- osm
- japan
- plateau
- netherlands
- france
- switzerland
- gis
- basemap
- site-analysis
- korea
- cadastral
- zoning
- guid:%(plugin_id)s
'''

PLAIN_SCRIPT_NAMES = ("loader.py", "cmd_site.py")         # 입출력 연결뿐이라 감출 로직이 없다
UI_FILE_NAMES = ("site_ui.html", "i18n.json")   # i18n.json = 다국어 사전(패널 tr()·로직 모듈 i18n.tr 공용)
UI_DIR_NAMES = ("vendor",)
DOC_FILE_NAMES = ("docs/install.md",)
EXCLUDED_MODULE_PREFIXES = ("dev_", "cmd_", "probe_", "server_", "blender_", "sketchup_", "web_")     # 개발·실측 전용, 진입 스크립트, 국내 서버(VM) 전용, Blender·SketchUp·웹판
YAK_EXCLUDED_NAMES = ("mesh_geometry", "panel_server")      # Blender·SketchUp 공용(mathutils·shapely, 브라우저 패널) — Rhino는 안 쓴다

# Gorani 명령 본문 — rhinocode가 .rhp에 넣는다.
COMMAND_SOURCE = '''#! python 3
"""Gorani — 패널을 연다. Yak 설치 폴더(.rhp 옆)의 scripts/cmd_site.py를 그대로 실행한다."""
import os
import runpy

import Rhino
import System

folder = os.path.dirname(Rhino.PlugIns.PlugIn.PathFromId(System.Guid("%(plugin_id)s")))
script = os.path.join(folder, "scripts", "cmd_site.py")
if not os.path.exists(script):
    # Rhino를 끄지 않고 Package Manager로 업데이트하면 켤 때 읽은 옛 판 폴더의 scripts가 지워진다(2026-10-23 0.3.4 → 0.3.5 사용자 신고).
    # 옆 판 폴더 중 가장 새 것을 쓰고, 그것도 없으면 재시작을 안내한다
    def version_key(name):
        return tuple(int(part) if part.isdigit() else 0 for part in name.split("."))
    root = os.path.dirname(folder)
    versions = sorted((name for name in os.listdir(root) if os.path.exists(os.path.join(root, name, "scripts", "cmd_site.py"))),
                      key=version_key) if os.path.isdir(root) else []
    script = os.path.join(root, versions[-1], "scripts", "cmd_site.py") if versions else ""
if script:
    runpy.run_path(script, run_name="__main__")
else:
    Rhino.UI.Dialogs.ShowMessage("Gorani was updated. Please restart Rhino to finish the update.", "Gorani")
'''

BLENDER_APP = "/Applications/Blender.app/Contents/MacOS/Blender"
BLENDER_PACKAGE_ID = "gorani"
BLENDER_EXCLUDED_NAMES = ("panel_host.py", "cmd_install.py", "cmd_sketchup.py", "cmd_web.py", "usage_stats.py")    # Rhino 전용(Eto·RhinoCommon·사용 통계), SketchUp 사이드카, 웹판
# 확장 심사(2026-10-28): 애드온에는 Blender 코드만 — 다른 프로그램(Rhino·SketchUp) 분기, Blender에 없는 라이브러리 import, 스레드(threading·queue)는 안 된다.
# 공용 모듈의 그런 구간은 소스에서 `# [blender-cut]` … `# [/blender-cut]` 줄(패널 HTML은 `// [blender-cut]`)로 감싸 두고 패키지에서 뺀다(get_blender_source).
# 남으면 get_blender_problems가 빌드를 멈춘다. 번역 사전은 다른 프로그램·사용 통계 문구를 뺀다(BLENDER_I18N_DROPPED)
BLENDER_CUT = re.compile(r"^[ \t]*(?:#|//) \[blender-cut\][^\n]*\n.*?^[ \t]*(?:#|//) \[/blender-cut\][^\n]*\n", re.S | re.M)
BLENDER_I18N_DROPPED = re.compile(r"(?i)rhino|라이노|sketchup|사용 통계")
BLENDER_UI_FOREIGN = re.compile(r"(?i)sketchup|stats_consent|ask_stats|usage_stats")   # 패널 HTML·번역 사전에 남으면 안 되는 말(HTML 주석의 Rhino 이야기는 둔다)
BLENDER_RENAMES = {"non_rhino_utils": "geo_utils"}   # 모듈 이름에 다른 프로그램 이름을 남기지 않는다(같은 내용, 이름만)
BLENDER_PYTHON_MODULES = ("bpy", "mathutils", "bmesh", "bpy_extras", "gpu", "numpy")   # Blender가 함께 싣는 모듈 — 이 밖(표준 라이브러리 제외)은 휠로 실어야 한다
BLENDER_BANNED_MODULES = ("threading", "queue", "_thread", "concurrent", "multiprocessing", "asyncio")   # Blender 안 스레드 — 심사: Blender를 죽인다(subprocess는 된다)
BLENDER_FOREIGN_WORDS = re.compile(r"(?i)rhino|sketchup|archicad|autocad|usage_stats|analytics")   # 코드(이름·문자열, 주석·docstring 제외)에 남으면 안 되는 말
# 확장 약관 1.2 — 함께 넣는 글꼴·이미지는 CC0만. Pretendard(OFL)는 빼고 패널은 시스템 글꼴(Apple SD Gothic Neo·맑은 고딕)로 그린다
BLENDER_EXCLUDED_ASSETS = ("PretendardVariable.woff2", "LICENSE-pretendard.txt")
BLENDER_LICENSE_PATH = os.path.join(ROOT_DIR, "docs", "licenses", "GPL-3.0.txt")   # 확장 약관 1.1 — 애드온은 GPL-3.0-or-later
BLENDER_INIT_SOURCE = '''"""Gorani Blender 확장 — 본문은 scripts/cmd_blender.py(등록만 넘긴다)."""
from .scripts import cmd_blender


def register():
    cmd_blender.register()


def unregister():
    cmd_blender.unregister()
'''
# Blender 패키지에만 들어가는 판 — 확장 심사(2026-10-21 조사: docs/blender_store/README.md)가 sys.path·sys.modules 조작, 모듈 다시 읽기,
# Blender 안 스레드, 분석 전송을 막는다. Rhino판 loader(공유 인터프리터 이름 충돌·편집 반영)와 GA 통계는 패키지에 넣지 않는다.
BLENDER_LOADER_SOURCE = '''"""로직 모듈 로더 — Blender 확장판(dev_deploy.py blender가 scripts/loader.py 대신 넣는다).
패키지 상대 import만 쓰고 sys.path·sys.modules는 건드리지 않는다. 모듈은 한 번 읽고, 다시 읽기는 Blender가 확장을 껐다 켤 때 한다.
"""

import importlib
import os

SCRIPTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPTS_DIR)


def load(module_name):
    # type: (str) -> object
    return importlib.import_module("." + module_name, __package__)
'''
BLENDER_USAGE_STATS_SOURCE = '''"""사용 통계 — Blender 확장판은 보내지 않는다(확장 약관 4.5·심사 관행). dev_deploy.py blender가 scripts/usage_stats.py 대신 넣는 빈 판.
설치 ID만 남긴다 — 국내 데이터 팩 서버가 설치마다 하루 받기 한도를 센다(docs/install.md 5).
"""

from site_prefs import get_client_id  # noqa: F401


def is_configured():
    # type: () -> bool
    return False


def is_enabled():
    # type: () -> bool
    return False


def send_event(name, params=None):
    # type: (str, dict) -> bool
    return False


def get_target_params(target, lots=None):
    # type: (dict, list) -> dict
    return {}
'''
BLENDER_SOURCE_OVERRIDES = {"loader.py": BLENDER_LOADER_SOURCE, "usage_stats.py": BLENDER_USAGE_STATS_SOURCE}
# Blender 패키지에서 값을 바꿔 넣는 최상위 상수(get_patched_source) — 확장 심사(2026-10-25)가 Blender판이 부르지 않는 외부 서비스 주소까지 문제 삼았다
# (VWorld는 해외에서 막힘, Hugging Face는 'AI 서비스', 상용·유료 서비스). 데이터 팩은 GitHub 사본, VWorld 키는 읽지 않는다(키 이름이 비면 늘 없음).
# 나머지는 Rhino 전용(통계·업데이트·스토어), 개발·관리 전용(원천 수집·올리기), 키·상용 서비스(VWorld·Esri·IP 위치)라 비운다. 남은 주소는 BLENDER_ALLOWED_HOSTS로 검사
BLENDER_CONSTANT_PATCHES = {
    "constants.py": {
        "DATA_MANIFEST_URL": "DATA_GITHUB_MANIFEST_URL", "DATA_REPO_ID": '""', "DATA_DOMESTIC_BUCKET_URL": '""',
        "VWORLD_API_KEY_ENV": '""', "VWORLD_SEARCH_URL": '""',
        "OSM_USER_AGENT": '"Gorani/0.3 (Blender add-on; https://969flash.github.io/gorani/)"',
        "PDOK_ITEMS_URL": '""', "BDTOPO_FEED_URL": '""', "SWISS_STAC_ITEMS_URL": '""', "PLATEAU_CKAN_URL": '""', "CENSUS_COUNTY_URL": '""', "OVERTURE_S3_URL": '""',
    },
    "review_map.py": {"VWORLD_TILE_URL_TEMPLATE": '""', "VWORLD_AERIAL_URL_TEMPLATE": '""', "ESRI_AERIAL_URL": '""', "IP_LOCATE_URL": '""'},
}
# Blender 패키지에 남아도 되는 주소 — 위는 실제로 접속하는 곳(모두 무료·무가입), 아래는 링크·출처 표기·주석·라이선스 글(접속하지 않는다).
# 새 외부 서비스를 넣으면 빌드가 멈춘다 — 심사 답변(docs/blender_store/README.md 'Network')과 함께 여기에 넣는다
BLENDER_ALLOWED_HOSTS = (
    "127.0.0.1",                                                       # 패널 서버(이 컴퓨터)
    "tile.openstreetmap.org", "nominatim.openstreetmap.org", "overpass-api.de", "overpass.openstreetmap.fr",   # OpenStreetMap — 지도·지명 검색·건물·도로
    "s3.amazonaws.com", "cyberjapandata.gsi.go.jp",                    # 지형 타일 — AWS Open Data Terrain Tiles, 일본 국토지리원
    "raw.githubusercontent.com", "github.com",                         # 데이터 팩 매니페스트·팩(GitHub 사본 constants.DATA_GITHUB_REPO)
    "150.230.249.1",                                                   # 한국 건물·도로·등고선 팩(국내 서버 — 공간정보관리법 제16조, constants.DATA_DOMESTIC_BASE_URL)
    "969flash.github.io", "extensions.blender.org", "www.eum.go.kr", "www.openstreetmap.org", "wiki.openstreetmap.org", "registry.opendata.aws",
    "maps.gsi.go.jp", "www.mlit.go.jp", "overturemaps.org", "creativecommons.org", "www.w3.org", "leafletjs.com", "bugs.chromium.org",
    "bugzilla.mozilla.org", "fsf.org", "www.gnu.org",
)
# `if __package__:` … `else:` 진입 분기(cmd_site·cmd_blender) — 패키지에서는 앞쪽만 남긴다(뒤쪽은 Rhino·저장소 시험용 sys.modules 넣기)
PACKAGE_BRANCH = re.compile(r"^if __package__:[^\n]*\n((?:    [^\n]*\n)+)else:[^\n]*\n(?:    [^\n]*\n)+", re.M)
# 확장 매니페스트 — 칸 규칙은 Blender 매뉴얼 Extensions > Getting started(tagline·permissions 사유 64자 이하, 끝 마침표 없음).
# 태그: 심사가 '3D View'·'Scene'을 빼라고 했다(2026-10-28 — 장면 도구가 아니다). support = 스토어 'Report Issues' 칸(공개 이슈 트래커). Leaflet(BSD-2-Clause)을 넣어 라이선스·저작권에 적는다
BLENDER_MANIFEST = '''schema_version = "1.0.0"
id = "%(id)s"
version = "%(version)s"
name = "%(name)s"
tagline = "Site context for urban design: buildings, roads, terrain"
maintainer = "%(maintainer)s"
type = "add-on"
website = "https://969flash.github.io/gorani/"
support = "https://github.com/969flash/gorani-plugin/issues"
tags = ["Import-Export"]
blender_version_min = "4.2.0"
license = ["SPDX:GPL-3.0-or-later", "SPDX:BSD-2-Clause"]
copyright = ["2026 sanghoon", "2010-2023 Volodymyr Agafonkin (Leaflet)", "2010-2011 CloudMade (Leaflet)"]

[permissions]
network = "Map tiles, regional data packs and OpenStreetMap context"   # IP 위치 조회는 Blender판에서 끈다(HOST_LABELS ip_center)
files = "Write results and data packs to the Gorani home folder"
'''

PACK_KINDS = (   # (종류, 표시 이름 꼬리, 원본 DB 종류) — 등고선 팩은 컨텍스트 DB에서 terrain만 떼어 낸다
    ("site", "필지", "site"),
    ("context", "건물·도로·수계", "context"),
    ("terrain", "등고선", "context"),
)
REWRITE_CHUNK = 100000      # 도형 다시 쓰기 한 번에 읽는 id 구간
SPLIT_CELL = 200.0          # m — 시군구 나누기 격자. 필지 중심 다수결로 격자의 시군구를 정한다
SPLIT_SEARCH = 50           # 칸 — 필지 없는 곳(바다·큰 산)은 이 범위(10 km) 안 가장 가까운 격자의 시군구로
SLIM_PACK_ID = 0x55445431   # 'UDT1' — slim_pack_database를 거친 팩 표시(PRAGMA application_id)
BOUNDS_SQL = {   # 팩 범위(EPSG:5186) — data_pack이 대상지에 걸리는 시도 파일만 열 때 쓴다
    "site": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM parcels",
    "context": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM buildings",
    "terrain": "SELECT MIN(min_x), MIN(min_y), MAX(max_x), MAX(max_y) FROM features",
}


def get_core_bounds(points):
    # type: (list) -> tuple
    """점 [(x, y)]의 범위 — 핵심 범위(PACK_BOUNDS_CORE_QUANTILE~1-q)를 각 변마다 그 폭의 절반(최소 PACK_BOUNDS_EXTEND_MIN)까지 넓힌 창 안의
    점만으로 min/max를 재고 PACK_BOUNDS_MARGIN을 더한다. 창 밖 점(원천 좌표 오류)은 버린다. 점이 없으면 None."""
    if not points:
        return None
    window = []
    for axis in (0, 1):
        values = sorted(p[axis] for p in points)
        q = constants.PACK_BOUNDS_CORE_QUANTILE
        low, high = values[int(q * (len(values) - 1))], values[int((1 - q) * (len(values) - 1))]
        extend = max((high - low) * 0.5, constants.PACK_BOUNDS_EXTEND_MIN)
        window.append((low - extend, high + extend))
    kept = [p for p in points if window[0][0] <= p[0] <= window[0][1] and window[1][0] <= p[1] <= window[1][1]]
    margin = constants.PACK_BOUNDS_MARGIN
    return (min(p[0] for p in kept) - margin, min(p[1] for p in kept) - margin,
            max(p[0] for p in kept) + margin, max(p[1] for p in kept) + margin)


def get_site_pack_bounds(site_path):
    # type: (str) -> tuple
    """시군구 필지 팩의 범위(get_core_bounds — 필지 경계상자 중심). 같은 시군구의 컨텍스트·등고선 팩도 이 범위를 쓴다."""
    connection = sqlite3.connect(site_path)
    points = [((a + b) * 0.5, (c + d) * 0.5) for a, b, c, d in connection.execute("SELECT min_x, max_x, min_y, max_y FROM parcels")]
    connection.close()
    return get_core_bounds(points)


def get_deploy_module_names():
    # type: () -> list
    """.pyc로 컴파일해 배포할 로직 모듈 이름(정렬). 진입 스크립트·개발 전용·loader를 뺀다."""
    names = []
    for file_name in sorted(os.listdir(SCRIPTS_DIR)):
        if not file_name.endswith(".py") or file_name.startswith(EXCLUDED_MODULE_PREFIXES):
            continue
        name = file_name[:-3]
        if name != "loader" and name not in YAK_EXCLUDED_NAMES:
            names.append(name)
    return names


def strip_spatial_index(database_path):
    # type: (str) -> int
    """DB 사본에서 rtree 가상테이블과 트리거를 지운다 — Rhino 8 Windows CPython의 SQLite에는 rtree 모듈이 없다."""
    connection = sqlite3.connect(database_path)
    trigger_names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' AND sql LIKE '%spatial_index%'")]
    table_names = [row[0] for row in connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name LIKE '%spatial_index'")]
    for name in trigger_names:
        connection.execute('DROP TRIGGER "%s"' % name)
    for name in table_names:
        connection.execute('DROP TABLE "%s"' % name)
    connection.commit()
    connection.close()
    return len(trigger_names) + len(table_names)


# ── yak ─────────────────────────────────────────────────

def _stage_scripts(package_dir):
    # type: (str) -> int
    """package_dir/scripts/ — 평문 진입 스크립트 + UI 에셋 + 로직 .pyc(optimize=2, 개발 PC 경로 제거)."""
    target = os.path.join(package_dir, "scripts")
    os.makedirs(target)
    for file_name in PLAIN_SCRIPT_NAMES + UI_FILE_NAMES:
        shutil.copyfile(os.path.join(SCRIPTS_DIR, file_name), os.path.join(target, file_name))
    for dir_name in UI_DIR_NAMES:
        shutil.copytree(os.path.join(SCRIPTS_DIR, dir_name), os.path.join(target, dir_name))
    names = get_deploy_module_names()
    for name in names:
        py_compile.compile(os.path.join(SCRIPTS_DIR, name + ".py"), cfile=os.path.join(target, name + ".pyc"),
                           dfile=name + ".py", doraise=True, optimize=2)
    for path in DOC_FILE_NAMES:
        os.makedirs(os.path.join(package_dir, os.path.dirname(path)), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT_DIR, path), os.path.join(package_dir, path))
    return len(names)


def _build_plugin(project_dir):
    # type: (str) -> str
    """Gorani 명령 하나짜리 rhproj를 쓰고 rhinocode로 빌드한다. 빌드 결과 폴더(rhp·rui·manifest.yml)를 돌려준다."""
    os.makedirs(os.path.join(project_dir, "commands"))
    with open(os.path.join(project_dir, "commands", COMMAND_NAME + ".py"), "w", encoding="utf-8") as f:
        f.write(COMMAND_SOURCE % {"plugin_id": PLUGIN_ID})
    project = {
        # rhinocode가 host를 보고 8.11 미만에서 저장한 프로젝트로 판정하면 거부한다 — os·arch까지 있어야 통과(2026-10-12 실측)
        "host": {"name": "Rhino3D", "version": "8.35", "os": "macOS", "arch": "arm64"},
        "id": PLUGIN_ID,
        "identity": {
            "name": PACKAGE_NAME, "version": PACKAGE_VERSION, "publisher": PUBLISHER, "license": "MIT",
            "description": "Site context models for urban design: 3D buildings, roads, terrain and water, basemap and analysis maps. Command: Gorani",
        },
        "settings": {
            "buildPath": "build/",
            "buildTarget": {"host": {"name": "Rhino3D", "version": "8"}, "title": "Rhino3D (8.*)", "slug": "rh8"},
            "publishTarget": {"title": "McNeel Yak Server"},
        },
        "codes": [{"id": COMMAND_ID, "language": {"id": "*.*.python", "version": "3.*.*"},
                   "title": COMMAND_NAME, "uri": "commands/%s.py" % COMMAND_NAME}],
    }
    project_path = os.path.join(project_dir, PACKAGE_NAME + ".rhproj")
    with open(project_path, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)
    result = subprocess.run([os.path.join(RHINO_BIN_DIR, "rhinocode"), "project", "build", project_path],
                            capture_output=True, text=True)
    output_dir = os.path.join(project_dir, "build", "rh8")
    if result.returncode != 0 or not os.path.exists(os.path.join(output_dir, PACKAGE_NAME + ".rhp")):
        sys.exit("rhinocode 빌드 실패 — Rhino 8이 떠 있어야 합니다.\n%s%s" % (result.stdout, result.stderr))
    return output_dir


def _get_mark_svg(file_name, color):
    # type: (str, str) -> str
    """docs/brand의 마크 SVG(currentColor)를 한 색으로 칠한 문자열."""
    with open(os.path.join(BRAND_DIR, file_name), encoding="utf-8") as f:
        return f.read().strip().replace("currentColor", color)


def _set_rui_icons(rui_path):
    # type: (str) -> None
    """rhinocode가 쓴 .rui의 명령 아이콘(기본 회색 상자 SVG)을 Gorani 마크로 바꾼다. .rhproj의 아이콘 칸은 빌드에 반영되지 않아
    (2026-10-19 실측 — identity·codes에 icon·image·imageSet을 원문·base64로 넣어도 .rui는 기본 아이콘) 빌드 뒤에 갈아 끼운다.
    도구 막대는 24 px 안팎이라 작은 판(gorani_mark_small.svg)을 쓴다."""
    with open(rui_path, encoding="utf-8") as f:
        text = f.read()
    for mode, color in TOOLBAR_ICON_COLORS.items():
        svg = _get_mark_svg("gorani_mark_small.svg", color)
        text, count = re.subn(r"<%s>.*?</%s>" % (mode, mode), lambda m: "<%s>%s</%s>" % (mode, svg, mode), text, flags=re.S)
        if not count:
            sys.exit(".rui에 <%s> 아이콘 자리가 없습니다 — rhinocode 출력 형식이 바뀌었는지 확인하세요: %s" % (mode, rui_path))
    with open(rui_path, "w", encoding="utf-8") as f:
        f.write(text)


# 배포 전 점검 — 패널 지도 타일을 키 없는 설치본의 길 그대로 받아 본다. 곳마다 그림이 달라야 통과:
# 막힘('Access blocked')·키 필요·자료 없음 그림은 어디서나 같다(2026-10-23 OSM 차단 사고 — 개발 PC는 .env VWorld 키로 OSM을 안 써 몰랐다)
SMOKE_PLACES = {"domestic": ((126.9784, 37.5665), (129.0756, 35.1796)),   # 서울시청·부산시청 — url·aerial_url(국내)
                "abroad": ((2.3488, 48.8534), (139.7671, 35.6812))}       # 파리·도쿄 — abroad_url·abroad_aerial_url
SMOKE_ZOOM = 16
SMOKE_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 Edg/130.0"   # 웹뷰처럼, Referer 없이
SMOKE_MIN_BYTES = 1000


def check_tiles():
    # type: () -> None
    """배포 전 점검. 실패하면 sys.exit — 빌드하지 않는다.

    입력:
        없음. 네트워크가 필요하다.
    처리:
        .env 없는 HOME·키 없는 환경에서 호스트별(rhino 중계 스레드, sketchup·blender의 panel_server 경로) get_tile_config를 만들고
        지도·영상 주소마다 두 곳의 타일을 받는다. 개발 PC에 VWorld 키가 있으면 키 있는 설정도 본다.
    출력:
        없음. 통과한 주소를 찍는다.
    """
    import math
    import tempfile
    import urllib.request
    from unittest.mock import patch
    import panel_server
    import pnu_loader
    import review_map

    def get_xyz(lng, lat):
        n = 2 ** SMOKE_ZOOM
        return SMOKE_ZOOM, int((lng + 180) / 360 * n), int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)

    def fetch(url):
        request = urllib.request.Request(url, headers={"User-Agent": SMOKE_USER_AGENT})
        with urllib.request.urlopen(request, timeout=15) as response:
            return response.headers.get("Content-Type", ""), response.read()

    class Controller(object):
        push = None

    key = pnu_loader.get_local_env_value(constants.VWORLD_API_KEY_ENV)
    bridge = panel_server.Bridge(Controller(), threaded=True)   # sketchup·blender 패널 출처(상대 경로 /osm/) — 점검은 서버 스레드로 받는다
    base = bridge.url.split("/?")[0]
    cases = []
    with tempfile.TemporaryDirectory() as home:
        for host in ("rhino", "sketchup"):
            env = {constants.HOST_ENV: host} if host != "rhino" else {}
            with patch.dict(os.environ, env), patch.object(pnu_loader, "HOME_DIR", home), patch.object(pnu_loader, "get_local_env_value", return_value=None):
                os.environ.pop(constants.VWORLD_API_KEY_ENV, None)
                cases.append((host, review_map.get_tile_config()))
                if key:
                    with patch.object(pnu_loader, "get_local_env_value", return_value=key):
                        cases.append((host + "+key", review_map.get_tile_config()))
    failures, checked = [], set()
    for label, config in cases:
        for field, region in (("url", "domestic"), ("aerial_url", "domestic"), ("abroad_url", "abroad"), ("abroad_aerial_url", "abroad")):
            template = config[field]
            if not template or (template, region) in checked:
                continue
            checked.add((template, region))
            url = base + template if template.startswith("/") else template
            try:
                tiles = [fetch(url.format(**dict(zip("zxy", get_xyz(*place))))) for place in SMOKE_PLACES[region]]
            except Exception as error:
                failures.append("%s %s: %s" % (label, field, error))
                continue
            bad = [kind for kind, body in tiles if not kind.startswith("image/")] + ["%d B" % len(body) for _, body in tiles if len(body) < SMOKE_MIN_BYTES]
            if bad or tiles[0][1] == tiles[1][1]:
                failures.append("%s %s: %s" % (label, field, ", ".join(bad) or "두 곳 타일이 같다(막힘·키 필요·자료 없음 그림)"))
                continue
            print("  타일 통과: %s %s" % (label, field))
    bridge.server.shutdown()
    if failures:
        sys.exit("배포 전 점검 실패 — 패널 지도 타일:\n  " + "\n  ".join(failures))


def build_yak():
    # type: () -> str
    """build/yak/ 아래에서 스크립트를 모으고 플러그인을 빌드해 .yak 하나를 build/에 만든다. 경로를 돌려준다."""
    work_dir = os.path.join(BUILD_DIR, "yak")
    shutil.rmtree(work_dir, ignore_errors=True)
    package_dir = os.path.join(work_dir, "package")
    os.makedirs(package_dir)
    print("  로직 모듈 %d개 컴파일" % _stage_scripts(package_dir))
    plugin_dir = _build_plugin(os.path.join(work_dir, "project"))
    for file_name in (PACKAGE_NAME + ".rhp", PACKAGE_NAME + ".rui"):
        shutil.copyfile(os.path.join(plugin_dir, file_name), os.path.join(package_dir, file_name))
    _set_rui_icons(os.path.join(package_dir, PACKAGE_NAME + ".rui"))
    shutil.copyfile(os.path.join(BRAND_DIR, "png", "gorani_128.png"), os.path.join(package_dir, "icon.png"))   # PackageManager 목록 아이콘
    with open(os.path.join(package_dir, "manifest.yml"), "w", encoding="utf-8") as f:
        f.write(YAK_MANIFEST % {"name": PACKAGE_NAME, "version": PACKAGE_VERSION, "author": PUBLISHER["name"],
                                "url": WEBSITE_URL, "plugin_id": PLUGIN_ID})
    result = subprocess.run([os.path.join(RHINO_BIN_DIR, "yak"), "build", "--platform", "any"],
                            cwd=package_dir, capture_output=True, text=True)
    packages = [name for name in os.listdir(package_dir) if name.endswith(".yak")]
    if result.returncode != 0 or len(packages) != 1:
        sys.exit("yak build 실패\n%s%s" % (result.stdout, result.stderr))
    target = os.path.join(BUILD_DIR, packages[0])
    shutil.move(os.path.join(package_dir, packages[0]), target)
    return target


# ── blender ─────────────────────────────────────────────

def get_package_source(source, module_names):
    # type: (str, list) -> str
    """프로젝트 모듈 import를 패키지 상대 import로 바꾼 소스(`import constants` → `from . import constants`,
    `from context_builder import X` → `from .context_builder import X`)이고, `if __package__:` 진입 분기는 앞쪽만 남긴다.
    Blender 확장 정책이 최상위 모듈·sys.path·sys.modules 변경을 막는다 — Rhino판은 scripts/를 sys.path에 넣는 평범한 import 그대로 둔다."""
    source = PACKAGE_BRANCH.sub(lambda m: re.sub(r"^    ", "", m.group(1), flags=re.M), source)
    pattern = re.compile(r"^(\s*)(import|from) (%s)\b" % "|".join(sorted(module_names, key=len, reverse=True)), re.M)
    return pattern.sub(lambda m: "%sfrom . import %s" % (m.group(1), m.group(3)) if m.group(2) == "import" else "%sfrom .%s" % (m.group(1), m.group(3)), source)


def get_patched_source(source, patches):
    # type: (str, dict) -> str
    """최상위 대입 `NAME = …`(여러 줄 포함)을 `NAME = <새 식>` 한 줄로 바꾼 소스. patches = {이름: 새 식(파이썬 소스)}.
    이름이 소스에 없으면 ValueError — 상수 이름이 바뀌었는데 빌드가 조용히 옛 값을 싣지 않게."""
    found = {node.targets[0].id: (node.lineno, node.end_lineno) for node in ast.parse(source).body
             if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id in patches}
    if set(patches) - set(found):
        raise ValueError("바꿀 상수가 없습니다: %s" % sorted(set(patches) - set(found)))
    lines = source.splitlines(True)
    for name, (start, end) in sorted(found.items(), key=lambda item: -item[1][0]):
        lines[start - 1:end] = ["%s = %s   # Blender판(dev_deploy.BLENDER_CONSTANT_PATCHES)\n" % (name, patches[name])]
    return "".join(lines)


def get_blender_source(source, name, module_names):
    # type: (str, str, list) -> str
    """Blender 패키지에 넣을 모듈 소스 — `# [blender-cut]` 구간을 빼고(BLENDER_CUT), 상수를 바꿔 넣고(BLENDER_CONSTANT_PATCHES),
    import를 패키지 상대로 바꾸고(get_package_source), 모듈 이름을 바꾼다(BLENDER_RENAMES). 구간을 뺀 자리의 빈 줄은 두 줄로 줄인다."""
    source = re.sub(r"\n{4,}", "\n\n\n", BLENDER_CUT.sub("", source))
    source = get_package_source(get_patched_source(source, BLENDER_CONSTANT_PATCHES.get(name, {})), module_names)
    for old, new in BLENDER_RENAMES.items():
        source = re.sub(r"\b%s\b" % old, new, source)
    return source


def _get_defined_names(table):
    # type: (symtable.SymbolTable) -> set
    """모듈 symtable에서 최상위에 정의되는 이름(대입·import·def·class, 함수 안 global 대입 포함)."""
    names = {sym.get_name() for sym in table.get_symbols() if sym.is_assigned() or sym.is_imported() or sym.is_namespace()}
    stack = list(table.get_children())
    while stack:
        child = stack.pop()
        names |= {sym.get_name() for sym in child.get_symbols() if sym.is_declared_global() and sym.is_assigned()}
        stack += child.get_children()
    return names


def get_blender_problems(package_dir):
    # type: (str) -> list
    """Blender 패키지 자가 점검 — 심사에서 걸린 것(2026-10-25·28)이 다시 들어가지 않게. 문제 ["상대경로:줄: 내용"].
    문법, Blender에 없는 라이브러리·스레드 import, sys.path·sys.modules, 코드의 다른 프로그램 이름(BLENDER_FOREIGN_WORDS),
    정의 안 된 전역 이름·모듈 속성(`# [blender-cut]`으로 정의만 빠지고 쓰는 곳이 남은 경우), 실행에 필요 없는 docs/ 폴더."""
    stdlib = set(getattr(sys, "stdlib_module_names", ())) or (   # 3.9(yak 빌드 파이썬)는 표준 라이브러리 폴더를 훑는다
        set(sys.builtin_module_names) | {m.name for m in pkgutil.iter_modules([sysconfig.get_paths()["stdlib"], os.path.join(sysconfig.get_paths()["stdlib"], "lib-dynload")])})
    problems = ["%s: 실행에 필요 없는 문서 폴더" % os.path.relpath(os.path.join(package_dir, d), package_dir) for d in ("docs",)
                if os.path.exists(os.path.join(package_dir, d))]
    for folder, _, names in os.walk(package_dir):
        for name in sorted(n for n in names if n.endswith((".html", ".json"))):
            with open(os.path.join(folder, name), encoding="utf-8") as f:
                problems += ["%s:%d: 다른 프로그램·통계 흔적 %s" % (os.path.relpath(os.path.join(folder, name), package_dir), n, m.group(0))
                             for n, line in enumerate(f, 1) for m in [BLENDER_UI_FOREIGN.search(line)] if m]
    sources, trees, defined, own = {}, {}, {}, {}
    for folder, _, names in os.walk(package_dir):
        for name in sorted(n for n in names if n.endswith(".py")):
            path = os.path.join(folder, name)
            rel = os.path.relpath(path, package_dir)
            with open(path, encoding="utf-8") as f:
                sources[rel] = f.read()
            try:
                trees[rel] = ast.parse(sources[rel])
            except SyntaxError as error:
                problems.append("%s:%s: 문법 오류 %s" % (rel, error.lineno, error.msg))
                continue
            own[rel] = _get_defined_names(symtable.symtable(sources[rel], rel, "exec"))
            if name != "__init__.py":
                defined[name[:-3]] = own[rel]
    known = set(dir(builtins)) | {"__file__", "__name__", "__package__", "__spec__", "__doc__", "__path__"}
    for rel, tree in trees.items():
        found = []
        docstrings = {node.body[0].value.lineno for node in ast.walk(tree) if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef))
                      and node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant)
                      and isinstance(node.body[0].value.value, str)}
        aliases = {alias.asname or alias.name for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.level == 1 and not node.module
                   for alias in node.names}   # from . import m — 이 파일에서 모듈을 가리키는 이름(같은 이름의 지역 변수는 보지 않는다)
        for node in ast.walk(tree):
            modules = []
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                modules = [node.module]
            for module in modules:
                top = module.split(".")[0]
                if top in BLENDER_BANNED_MODULES:
                    found.append((node.lineno, "스레드 import %s" % module))
                elif top not in stdlib and top not in BLENDER_PYTHON_MODULES:
                    found.append((node.lineno, "Blender에 없는 라이브러리 import %s" % module))
            if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module in defined:   # from .m import a
                found += [(node.lineno, "%s에 없는 이름 %s" % (node.module, alias.name)) for alias in node.names if alias.name not in defined[node.module]]
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "sys" and node.attr in ("path", "modules"):
                    found.append((node.lineno, "sys.%s" % node.attr))
                elif node.value.id in aliases and node.value.id in defined and node.attr not in defined[node.value.id]:   # constants.X
                    found.append((node.lineno, "%s에 없는 이름 %s" % (node.value.id, node.attr)))
            if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Attribute)
                    and node.value.func.attr == "load" and node.value.args and isinstance(node.value.args[0], ast.Constant)
                    and node.value.args[0].value in defined and node.attr not in defined[node.value.args[0].value]):   # loader.load("m").X
                found.append((node.lineno, "%s에 없는 이름 %s" % (node.value.args[0].value, node.attr)))
        top = symtable.symtable(sources[rel], rel, "exec")
        stack = [top]
        while stack:
            table = stack.pop()
            for sym in table.get_symbols():
                implicit = sym.is_global() if table is not top else not (sym.is_assigned() or sym.is_imported() or sym.is_namespace())
                if sym.is_referenced() and implicit and sym.get_name() not in own[rel] and sym.get_name() not in known:
                    found.append((table.get_lineno(), "정의 안 된 이름 %s" % sym.get_name()))
            stack += table.get_children()
        for token in tokenize.generate_tokens(iter(sources[rel].splitlines(True)).__next__):
            if (token.type == tokenize.NAME or token.type == tokenize.STRING and token.start[0] not in docstrings) and BLENDER_FOREIGN_WORDS.search(token.string):
                found.append((token.start[0], "다른 프로그램 흔적 %s" % token.string[:60]))
        problems += ["%s:%d: %s" % (rel, line, text) for line, text in sorted(set(found))]
    return problems


def get_foreign_hosts(package_dir, allowed):
    # type: (str, tuple) -> list
    """package_dir 안 글 파일의 http(s) 주소 중 호스트가 allowed 밖인 것 ["상대경로: 호스트"]. 그림·글꼴처럼 UTF-8이 아닌 파일은 건너뛴다."""
    found = []
    for folder, _, names in os.walk(package_dir):
        for name in sorted(names):
            path = os.path.join(folder, name)
            try:
                with open(path, encoding="utf-8") as f:
                    text = f.read()
            except UnicodeDecodeError:
                continue
            found += ["%s: %s" % (os.path.relpath(path, package_dir), host) for host in sorted(set(re.findall(r"https?://([A-Za-z0-9.-]+)", text)))
                      if host not in allowed]
    return found


def _run_blender(*args):
    # type: (str) -> None
    result = subprocess.run([BLENDER_APP, "-b", "--factory-startup", "-c", "extension"] + list(args), capture_output=True, text=True)
    if result.returncode != 0:
        sys.exit("Blender %s 실패\n%s%s" % (args[0], result.stdout, result.stderr))


def build_blender():
    # type: () -> str
    """build/blender/gorani/에 확장 폴더를 모아 zip으로 묶고, build/blender_repo/에 zip과 정적 저장소 색인을 만든다. zip 경로를 돌려준다."""
    work_dir = os.path.join(BUILD_DIR, "blender")
    repo_dir = os.path.join(BUILD_DIR, "blender_repo")
    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(repo_dir, ignore_errors=True)
    package_dir = os.path.join(work_dir, BLENDER_PACKAGE_ID)
    target = os.path.join(package_dir, "scripts")
    os.makedirs(target)
    names = [n for n in sorted(os.listdir(SCRIPTS_DIR)) if n.endswith(".py") and n not in BLENDER_EXCLUDED_NAMES
             and not n.startswith(("dev_", "probe_", "server_", "sketchup_", "web_"))]
    for name in names:
        with open(os.path.join(SCRIPTS_DIR, name), encoding="utf-8") as f:
            source = get_blender_source(BLENDER_SOURCE_OVERRIDES.get(name) or f.read(), name, [n[:-3] for n in names])
        with open(os.path.join(target, BLENDER_RENAMES.get(name[:-3], name[:-3]) + ".py"), "w", encoding="utf-8") as f:
            f.write(source)
    with open(os.path.join(target, "__init__.py"), "w", encoding="utf-8") as f:
        f.write('"""Gorani 로직 모듈 — Blender 확장에서는 하위 패키지."""\n')
    for name in UI_FILE_NAMES:
        with open(os.path.join(SCRIPTS_DIR, name), encoding="utf-8") as f:
            text = f.read()
        if name.endswith(".json"):   # 번역 사전 — 다른 프로그램·사용 통계 문구는 빼고 같은 꼴로
            texts = {key: value for key, value in json.loads(text).items() if not BLENDER_I18N_DROPPED.search(json.dumps([key, value], ensure_ascii=False))}
            text = json.dumps(texts, ensure_ascii=False, indent=1) + "\n"
        with open(os.path.join(target, name), "w", encoding="utf-8") as f:
            f.write(BLENDER_CUT.sub("", text))
    for dir_name in UI_DIR_NAMES:
        shutil.copytree(os.path.join(SCRIPTS_DIR, dir_name), os.path.join(target, dir_name), ignore=shutil.ignore_patterns(*BLENDER_EXCLUDED_ASSETS))
    shutil.copyfile(BLENDER_LICENSE_PATH, os.path.join(package_dir, "LICENSE"))
    with open(os.path.join(package_dir, "__init__.py"), "w", encoding="utf-8") as f:
        f.write(BLENDER_INIT_SOURCE)
    with open(os.path.join(package_dir, "blender_manifest.toml"), "w", encoding="utf-8") as f:
        f.write(BLENDER_MANIFEST % {"id": BLENDER_PACKAGE_ID, "version": PACKAGE_VERSION, "name": PACKAGE_NAME,
                                    "maintainer": "%s <%s>" % (PUBLISHER["name"], PUBLISHER["email"])})
    print("  모듈 %d개" % len(names))
    foreign = get_foreign_hosts(package_dir, BLENDER_ALLOWED_HOSTS)
    if foreign:   # 확장 심사 2026-10-25 — 쓰지 않는 외부 주소가 남으면 싣지 않는다
        sys.exit("Blender 패키지에 허용 목록(BLENDER_ALLOWED_HOSTS) 밖 주소가 있습니다:\n  " + "\n  ".join(foreign))
    problems = get_blender_problems(package_dir)
    if problems:   # 확장 심사 2026-10-28 — 다른 프로그램 코드·Blender에 없는 라이브러리·스레드가 남으면 싣지 않는다
        sys.exit("Blender 패키지 점검 실패 %d건(scripts의 `# [blender-cut]` 구간을 확인):\n  " % len(problems) + "\n  ".join(problems))
    os.makedirs(repo_dir)
    _run_blender("build", "--source-dir", package_dir, "--output-dir", repo_dir)
    _run_blender("server-generate", "--repo-dir", repo_dir, "--html")
    return os.path.join(repo_dir, "%s-%s.zip" % (BLENDER_PACKAGE_ID, PACKAGE_VERSION))


# ── sketchup ────────────────────────────────────────────

SKETCHUP_EXT_ID = "bsh_gorani"          # 뿌리 .rb·폴더 이름(Extension Warehouse 규칙 — 개발자 접두어 + 둘이 같은 이름)
SKETCHUP_PYTHON_URL = "https://github.com/astral-sh/python-build-standalone/releases/download/20261013/cpython-3.12.15%%2B20261013-%s-install_only_stripped.tar.gz"
SKETCHUP_PYTHON_VERSION = "3.12"
SKETCHUP_PLATFORMS = {   # 폴더: (python-build-standalone 대상, pip 플랫폼 태그 — 앞이 우선, macOS 14 전용 Accelerate 휠은 넣지 않는다)
    "mac-arm64": ("aarch64-apple-darwin", ("macosx_11_0_arm64",)),
    "mac-x64": ("x86_64-apple-darwin", ("macosx_11_0_x86_64", "macosx_10_13_x86_64", "macosx_10_9_x86_64")),
    "win-x64": ("x86_64-pc-windows-msvc", ("win_amd64",)),
}
SKETCHUP_PIP_PACKAGES = ("numpy", "shapely>=2.1", "certifi")   # certifi = 맥 번들 파이썬은 /etc/ssl/cert.pem(낡음, HARICA 없음)을 써서 일부 HTTPS가 검증 실패(2026-10-23 감사)   # shapely 2.1+ = constrained_delaunay_triangles(mesh_geometry 겹치기 CDT)
SKETCHUP_PLAIN_NAMES = ("loader.py", "cmd_site.py", "cmd_sketchup.py")
SKETCHUP_EXCLUDED_NAMES = ("panel_host", "cmd_install", "blender_baker")   # Rhino·Blender 전용
# 런타임에서 뺄 것(번들 크기) — 런타임 루트 기준 fnmatch(대소문자 구분, * 는 / 도 넘는다). 표준 라이브러리 lib/python3.12(맥)·Lib(윈도)는 {lib}로 쓴다
# 맥 실행 파일 python3.12는 정적 링크라 libpython dylib가 필요 없고, bin/python·python3 링크는 zip에서 18 MB 사본이 된다(2026-10-18 실측)
SKETCHUP_PYTHON_DROP = ("bin/2to3*", "bin/idle3*", "bin/pip*", "bin/pydoc3*", "bin/python3*-config", "bin/python", "bin/python3", "lib/libpython3*.dylib",
                        "include", "share", "lib/pkgconfig",
                        "lib/tcl*", "lib/tk*", "lib/itcl*", "lib/thread*", "lib/libtcl*", "lib/libtk*", "Scripts", "libs", "tcl",
                        "DLLs/_tkinter.pyd", "DLLs/tcl*.dll", "DLLs/tk*.dll", "{lib}/config-3.12-darwin", "{lib}/lib-dynload/_tkinter*",
                        "{lib}/idlelib", "{lib}/tkinter", "{lib}/turtledemo", "{lib}/test", "{lib}/ensurepip", "{lib}/lib2to3", "{lib}/pydoc_data",
                        "{lib}/site-packages/pip", "{lib}/site-packages/pip-*", "{lib}/site-packages/numpy/tests", "{lib}/site-packages/numpy/**/tests", "{lib}/site-packages/shapely/tests")
SKETCHUP_PYTHON_KEEP = ("threading.py", "queue.py", "http/server.py", "sqlite3/__init__.py", "ssl.py", "json/__init__.py")   # 지우면 사이드카가 못 뜬다
SKETCHUP_ROOT_SOURCE = '''# Gorani — 도시설계 착수용 대지 컨텍스트(주변 건물·도로·지형·수계 3D, 베이스맵, 현황도). 본문은 %(id)s/main.rb
require "sketchup.rb"
require "extensions.rb"

module BSH
  module Gorani
    unless file_loaded?(__FILE__)
      extension = SketchupExtension.new("Gorani", "%(id)s/main")
      extension.description = "The city around your site, modeled in SketchUp: buildings, roads, terrain and water, " \\
                              "plus an Illustrator basemap and analysis maps. Extensions > Gorani. " \\
                              "한 번에 쉽게 하는 사이트 모델링 및 사이트 분석. 확장 > Gorani"
      extension.version = "%(version)s"
      extension.creator = "%(creator)s"
      extension.copyright = "%(year)s %(creator)s"
      Sketchup.register_extension(extension, true)
      file_loaded(__FILE__)
    end
  end
end
'''


def _get_python_runtime(platform):
    # type: (str) -> str
    """python-build-standalone tar를 build/cache/에 받아 두고 경로를 돌려준다(있으면 다시 받지 않는다)."""
    url = SKETCHUP_PYTHON_URL % SKETCHUP_PLATFORMS[platform][0]
    path = os.path.join(BUILD_DIR, "cache", os.path.basename(url).replace("%2B", "+"))
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        print("  받기 %s" % os.path.basename(path))
        subprocess.run(["curl", "-sSLf", "-o", path + ".part", url], check=True)
        os.replace(path + ".part", path)
    return path


def _get_site_packages(runtime_dir):
    # type: (str) -> str
    win = os.path.exists(os.path.join(runtime_dir, "python.exe"))
    return os.path.join(runtime_dir, "Lib" if win else os.path.join("lib", "python" + SKETCHUP_PYTHON_VERSION), "site-packages")


def _stage_python(python_dir):
    # type: (str) -> str
    """플랫폼마다 런타임을 풀고 numpy·shapely 휠을 깔고 줄인 뒤 .pyc(unchecked-hash)를 만든다. 이 Mac에서 돌릴 파이썬 경로를 돌려준다."""
    import fnmatch
    import tarfile
    host_python = os.path.join(python_dir, "mac-arm64", "bin", "python3.12")
    for platform in SKETCHUP_PLATFORMS:   # mac-arm64가 처음 — 그 pip로 다른 플랫폼 휠도 받는다
        runtime_dir = os.path.join(python_dir, platform)
        with tarfile.open(_get_python_runtime(platform)) as tar:
            tar.extractall(python_dir)   # 공식 릴리스(HTTPS) — 이것을 그대로 배포한다
        os.rename(os.path.join(python_dir, "python"), runtime_dir)
        site = _get_site_packages(runtime_dir)
        platform_args = [arg for tag in SKETCHUP_PLATFORMS[platform][1] for arg in ("--platform", tag)]
        subprocess.run([host_python, "-m", "pip", "install", "-q", "--disable-pip-version-check", "--upgrade", "--target", site,
                        "--only-binary=:all:", "--implementation", "cp", "--python-version", SKETCHUP_PYTHON_VERSION] + platform_args
                       + list(SKETCHUP_PIP_PACKAGES), check=True)
    for platform in SKETCHUP_PLATFORMS:
        runtime_dir = os.path.join(python_dir, platform)
        lib = os.path.relpath(os.path.dirname(_get_site_packages(runtime_dir)), runtime_dir)
        # 실제 파일 이름을 걸으며 대소문자까지 맞춘다 — glob은 macOS(대소문자 무시)에서 lib/thread*(Tcl)로 윈도 Lib/threading.py를 지웠다(2026-10-23, 0.2.0 rbz)
        patterns = [pattern.format(lib=lib) for pattern in SKETCHUP_PYTHON_DROP]
        for root, dir_names, file_names in os.walk(runtime_dir):
            for name in list(dir_names) + file_names:
                path = os.path.join(root, name)
                if not any(fnmatch.fnmatchcase(os.path.relpath(path, runtime_dir).replace(os.sep, "/"), pattern) for pattern in patterns):
                    continue
                if os.path.isdir(path) and not os.path.islink(path):
                    shutil.rmtree(path)
                    dir_names.remove(name)
                elif os.path.lexists(path):
                    os.remove(path)
        shutil.rmtree(os.path.join(_get_site_packages(runtime_dir), "bin"), ignore_errors=True)
        for name in SKETCHUP_PYTHON_KEEP:   # 사이드카가 쓰는 표준 모듈이 지워졌으면 멈춘다 — 윈도 런타임은 이 Mac에서 돌려 볼 수 없다
            if not os.path.exists(os.path.join(runtime_dir, lib, name)):
                sys.exit("%s 런타임에 %s가 없습니다 — SKETCHUP_PYTHON_DROP을 확인하세요" % (platform, name))
        subprocess.run([host_python, "-m", "compileall", "-q", "-f", "-j", "0", "--invalidation-mode", "unchecked-hash",
                        os.path.join(runtime_dir, lib)], check=True)
    return host_python


def build_sketchup():
    # type: () -> str
    """build/sketchup/에 확장 폴더를 모아 build/bsh_gorani-<버전>.rbz로 묶는다. rbz 경로를 돌려준다."""
    import zipfile
    work_dir = os.path.join(BUILD_DIR, "sketchup")
    shutil.rmtree(work_dir, ignore_errors=True)
    ext_dir = os.path.join(work_dir, SKETCHUP_EXT_ID)
    target = os.path.join(ext_dir, "scripts")
    os.makedirs(target)
    host_python = _stage_python(os.path.join(ext_dir, "python"))
    for name in SKETCHUP_PLAIN_NAMES + UI_FILE_NAMES:
        shutil.copyfile(os.path.join(SCRIPTS_DIR, name), os.path.join(target, name))
    for dir_name in UI_DIR_NAMES:
        shutil.copytree(os.path.join(SCRIPTS_DIR, dir_name), os.path.join(target, dir_name))
    names = [n[:-3] for n in sorted(os.listdir(SCRIPTS_DIR)) if n.endswith(".py") and n[:-3] not in SKETCHUP_EXCLUDED_NAMES
             and n[:-3] != "loader" and not n.startswith(("dev_", "cmd_", "probe_", "server_", "blender_", "web_"))]
    compile_source = ("import py_compile, sys\nsource, target = sys.argv[1:3]\n"
                      "for name in sys.argv[3:]:\n"
                      "    py_compile.compile(source + '/' + name + '.py', cfile=target + '/' + name + '.pyc', dfile=name + '.py', doraise=True, optimize=2)\n")
    subprocess.run([host_python, "-I", "-c", compile_source, SCRIPTS_DIR, target] + names, check=True)
    shutil.copyfile(os.path.join(SCRIPTS_DIR, "sketchup_ext.rb"), os.path.join(ext_dir, "main.rb"))
    os.makedirs(os.path.join(ext_dir, "icons"))
    # 도구 막대 아이콘 — Windows는 SVG, macOS는 PNG(SketchUp 맥은 SVG 대신 PDF를 받는다 — PNG는 48 px를 줄여 그린다)
    with open(os.path.join(ext_dir, "icons", "gorani.svg"), "w", encoding="utf-8") as f:
        f.write(_get_mark_svg("gorani_mark_small.svg", TOOLBAR_ICON_COLORS["light"]))
    shutil.copyfile(os.path.join(BRAND_DIR, "png", "gorani_48.png"), os.path.join(ext_dir, "icons", "gorani.png"))
    for path in DOC_FILE_NAMES:
        os.makedirs(os.path.join(ext_dir, os.path.dirname(path)), exist_ok=True)
        shutil.copyfile(os.path.join(ROOT_DIR, path), os.path.join(ext_dir, path))
    with open(os.path.join(work_dir, SKETCHUP_EXT_ID + ".rb"), "w", encoding="utf-8") as f:
        f.write(SKETCHUP_ROOT_SOURCE % {"id": SKETCHUP_EXT_ID, "version": PACKAGE_VERSION, "creator": PUBLISHER["name"],
                                        "year": datetime.date.today().year})
    print("  로직 모듈 %d개 컴파일" % len(names))
    rbz = os.path.join(BUILD_DIR, "%s-%s.rbz" % (SKETCHUP_EXT_ID, PACKAGE_VERSION))
    with zipfile.ZipFile(rbz, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for folder, _dirs, files in os.walk(work_dir):
            for name in sorted(files):
                path = os.path.join(folder, name)
                zf.write(path, os.path.relpath(path, work_dir))   # 심볼릭 링크는 원본 내용으로(rbz를 푸는 SketchUp이 링크를 모른다)
    return rbz


# ── web ─────────────────────────────────────────────────

WEB_DIR = os.path.join(BUILD_DIR, "web")
WEB_EXCLUDED_PREFIXES = ("dev_", "probe_", "server_", "blender_", "sketchup_")
WEB_EXCLUDED_NAMES = ("panel_host", "panel_server", "cmd_install", "cmd_blender", "cmd_sketchup")   # Rhino·Blender·SketchUp 연결


def build_web():
    # type: () -> str
    """build/web/에 웹판 정적 파일을 모은다. 폴더 경로를 돌려준다."""
    import zipfile
    sys.path.insert(0, SCRIPTS_DIR)
    import panel_server
    shutil.rmtree(WEB_DIR, ignore_errors=True)
    os.makedirs(WEB_DIR)
    shutil.copyfile(os.path.join(SCRIPTS_DIR, "web_app.html"), os.path.join(WEB_DIR, "index.html"))
    shutil.copyfile(os.path.join(SCRIPTS_DIR, "web_worker.js"), os.path.join(WEB_DIR, "web_worker.js"))
    with open(os.path.join(WEB_DIR, "panel.html"), "w", encoding="utf-8") as f:
        f.write(panel_server.get_html())
    names = [n for n in sorted(os.listdir(SCRIPTS_DIR)) if n.endswith(".py") and not n.startswith(WEB_EXCLUDED_PREFIXES)
             and n[:-3] not in WEB_EXCLUDED_NAMES]
    with zipfile.ZipFile(os.path.join(WEB_DIR, "scripts.zip"), "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in names + ["i18n.json"]:   # 다국어 사전 — i18n.py가 모듈 옆에서 읽는다
            zf.write(os.path.join(SCRIPTS_DIR, name), name)
    print("  모듈 %d개 · scripts.zip %.0f KB · panel.html %.0f KB" % (len(names), os.path.getsize(os.path.join(WEB_DIR, "scripts.zip")) / 1e3,
                                                                  os.path.getsize(os.path.join(WEB_DIR, "panel.html")) / 1e3))
    return WEB_DIR


# ── packs ───────────────────────────────────────────────

def _get_rounded(value, digits):
    # type: (object, int) -> object
    if isinstance(value, float):
        return round(value, digits)
    if isinstance(value, list):
        return [_get_rounded(v, digits) for v in value]
    return value


def _rewrite_geometries(connection, table, id_column, where, digits, tolerance=None):
    # type: (sqlite3.Connection, str, str, str, int, float) -> None
    """geometry_json을 digits 자리로 반올림(공백 없는 JSON)하고, tolerance가 있으면 그만큼 단순화한다(shapely — 개발 환경 전용).
    id 구간 REWRITE_CHUNK씩 나눠 읽는다 — 충북 컨텍스트(9.6 GB)를 한 번에 읽었더니 스왑으로 3시간 멈췄다(2026-10-13)."""
    low, high = connection.execute("SELECT MIN(%s), MAX(%s) FROM %s" % (id_column, id_column, table)).fetchone()
    if low is None:
        return
    condition = (where + " AND" if where else "WHERE") + " %s BETWEEN ? AND ?" % id_column
    for start in range(low, high + 1, REWRITE_CHUNK):
        rows = connection.execute("SELECT %s, geometry_json FROM %s %s" % (id_column, table, condition), (start, start + REWRITE_CHUNK - 1)).fetchall()
        _rewrite_rows(connection, table, id_column, rows, digits, tolerance)
        connection.commit()


def _rewrite_rows(connection, table, id_column, rows, digits, tolerance):
    # type: (sqlite3.Connection, str, str, list, int, float) -> None
    updates = []
    for row_id, text in rows:
        geometry = json.loads(text)
        if tolerance:
            simplified = shapely.from_geojson(text).simplify(tolerance, preserve_topology=geometry["type"].endswith("Polygon"))
            if not simplified.is_empty:
                geometry = json.loads(shapely.to_geojson(simplified))
        geometry["coordinates"] = _get_rounded(geometry["coordinates"], digits)
        updates.append((json.dumps(geometry, separators=(",", ":")), row_id))
    connection.executemany("UPDATE %s SET geometry_json = ? WHERE %s = ?" % (table, id_column), updates)


def _aggregate_align_samples(connection):
    # type: (sqlite3.Connection) -> int
    """정합 샘플 점(theme qa, kind align_sample — 서울만 134만 행)을 도엽별 요약 1행(kind align_sheet)으로 바꾼다.
    value = 거리 중앙값, attrs {n, p90, dx, dy}, 점 = 샘플 평균 위치. 런타임은 n 가중평균으로 합친다(context_builder._get_align_stats)."""
    groups = {}
    for sheet, value, attrs, geometry, source_id, reference_date in connection.execute(
            "SELECT sheet, value, attrs_json, geometry_json, source_id, reference_date FROM features WHERE theme = 'qa' AND kind = 'align_sample'"):
        attrs = json.loads(attrs or "{}")
        group = groups.setdefault(sheet, {"values": [], "dx": [], "dy": [], "xy": [], "source": (source_id, reference_date)})
        group["values"].append(float(value))
        group["dx"].append(float(attrs.get("dx", 0.0)))
        group["dy"].append(float(attrs.get("dy", 0.0)))
        group["xy"].append(json.loads(geometry)["coordinates"])
    rows = []
    for sheet, group in groups.items():
        values = group["values"]
        x = sum(p[0] for p in group["xy"]) / len(values)
        y = sum(p[1] for p in group["xy"]) / len(values)
        attrs = {"n": len(values), "p90": round(statistics.quantiles(values, n=10)[8] if len(values) >= 2 else values[0], 2),
                 "dx": round(statistics.median(group["dx"]), 2), "dy": round(statistics.median(group["dy"]), 2)}
        rows.append((group["source"][0], "qa", "align_sheet", round(statistics.median(values), 2), json.dumps(attrs), sheet,
                     json.dumps({"type": "Point", "coordinates": [round(x, 2), round(y, 2)]}), constants.DATABASE_CRS, group["source"][1], x, x, y, y))
    connection.execute("DELETE FROM features WHERE theme = 'qa' AND kind = 'align_sample'")
    connection.executemany("""INSERT INTO features (source_id, theme, kind, value, attrs_json, sheet, geometry_json, geometry_crs,
                                  reference_date, min_x, max_x, min_y, max_y) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
    return len(rows)


def slim_pack_database(connection, kind):
    # type: (sqlite3.Connection, str) -> None
    """배포 팩 용량 줄이기 — 원천 정확도(수치지형도 ±1.5 m, 지적 ±0.36 m)에 맞춰 정밀도를 낮추고 런타임이 안 쓰는 것을 뺀다.

    공통: 좌표 cm(0.01 m)·공백 없는 JSON. 등고선: 0.3 m 단순화 + 0.1 m(서울 실측 163 → 67 MB). 계획 도형: 0.1 m 단순화.
    컨텍스트: 정합 샘플 → 도엽 요약, 피처 속성의 UFID(원천 식별자, 런타임 미사용 — 서울 약 45 MB) 삭제.
    필지: 파생 계획 도형의 필지 연결표(parcel_land_use와 같은 정보)·빌드용 지목 인덱스 삭제.
    처리한 팩은 PRAGMA application_id = SLIM_PACK_ID로 표시한다(repack이 두 번 줄이지 않게).
    """
    if kind == "site":
        connection.execute("DROP INDEX IF EXISTS idx_parcels_category")
        connection.execute("DELETE FROM parcel_overlays WHERE overlay_id IN (SELECT overlay_id FROM overlays WHERE source_id = 'molit_land_use')")
        _rewrite_geometries(connection, "parcels", "parcel_id", "", 2)
        _rewrite_geometries(connection, "overlays", "overlay_id", "", 2, 0.1)
    else:
        if kind == "context":
            _aggregate_align_samples(connection)
            _rewrite_geometries(connection, "buildings", "building_id", "", 2)
        _rewrite_geometries(connection, "features", "feature_id", "WHERE theme = 'terrain' AND kind = 'contour'", 1, 0.3)
        _rewrite_geometries(connection, "features", "feature_id", "WHERE NOT (theme = 'terrain' AND kind = 'contour')", 2)
        connection.execute("UPDATE features SET attrs_json = json_remove(attrs_json, '$.UFID') WHERE attrs_json LIKE '%\"UFID\"%'")
        connection.execute("UPDATE features SET attrs_json = NULL WHERE attrs_json = '{}'")
    connection.execute("PRAGMA application_id = %d" % SLIM_PACK_ID)
    connection.commit()


def _make_pack_database(pack_name, source, target):
    # type: (str, str, str) -> None
    """팩 하나의 DB 파일. 필지 = 사본 + rtree 제거, 컨텍스트 = 사본 − 등고선, 등고선 = features 스키마 + terrain 행만."""
    if pack_name.endswith("_terrain.db"):
        connection = sqlite3.connect(target)
        connection.execute("ATTACH DATABASE ? AS source", (source,))
        for (sql,) in connection.execute("SELECT sql FROM source.sqlite_master WHERE tbl_name = 'features' AND sql IS NOT NULL").fetchall():
            connection.execute(sql)
        connection.execute("INSERT INTO features SELECT * FROM source.features WHERE theme = ?", (constants.TERRAIN_THEME,))
        connection.execute("PRAGMA user_version = %d" % connection.execute("PRAGMA source.user_version").fetchone()[0])
        connection.commit()
        connection.execute("DETACH DATABASE source")
    else:
        shutil.copyfile(source, target)
        connection = sqlite3.connect(target)
        if pack_name.endswith("_context.db"):
            connection.execute("DELETE FROM features WHERE theme = ?", (constants.TERRAIN_THEME,))
            connection.commit()
        connection.close()
        strip_spatial_index(target)
        connection = sqlite3.connect(target)
    slim_pack_database(connection, pack_name.rsplit("_", 1)[1][:-3])
    connection.execute("ANALYZE")
    connection.execute("VACUUM")
    connection.close()


class SggMap:
    """200 m 격자 → 시군구 코드(격자 안 필지 중심이 가장 많은 시군구). 필지 없는 격자는 가장 가까운 격자를 따른다."""

    def __init__(self, site_path):
        counts, names = {}, {}
        connection = sqlite3.connect(site_path)
        for sgg, x, y, address in connection.execute(
                "SELECT substr(pnu, 1, 5), (min_x + max_x) / 2, (min_y + max_y) / 2, address FROM parcels"):
            cell = (int(x // SPLIT_CELL), int(y // SPLIT_CELL))
            bucket = counts.setdefault(cell, {})
            bucket[sgg] = bucket.get(sgg, 0) + 1
            if sgg not in names:
                names[sgg] = _get_sgg_name(address)
        connection.close()
        self.cells = {cell: max(bucket.items(), key=lambda item: item[1])[0] for cell, bucket in counts.items()}
        self.names = names

    def get_sggs(self, min_x, min_y, max_x, max_y):
        # type: (float, float, float, float) -> set
        """경계상자가 걸치는 격자의 시군구들. 하나도 없으면 중심에서 가까운 격자(최대 SPLIT_SEARCH칸)의 시군구 하나."""
        x0, y0, x1, y1 = int(min_x // SPLIT_CELL), int(min_y // SPLIT_CELL), int(max_x // SPLIT_CELL), int(max_y // SPLIT_CELL)
        found = {self.cells[(x, y)] for x in range(x0, x1 + 1) for y in range(y0, y1 + 1) if (x, y) in self.cells}
        if found:
            return found
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        for radius in range(1, SPLIT_SEARCH + 1):
            ring = [(cx + dx, cy + dy) for dx in range(-radius, radius + 1) for dy in (-radius, radius)]
            ring += [(cx + dx, cy + dy) for dx in (-radius, radius) for dy in range(-radius + 1, radius)]
            hits = [self.cells[c] for c in ring if c in self.cells]
            if hits:
                return {max(set(hits), key=hits.count)}
        return set()


def _get_sgg_name(address):
    # type: (str) -> str
    """'경기도 성남시 분당구 정자동 1' → '성남시 분당구', '서울특별시 성동구 성수동2가 1' → '성동구'."""
    parts = (address or "").split()
    if len(parts) >= 3 and parts[1].endswith("시") and parts[2].endswith("구"):
        return "%s %s" % (parts[1], parts[2])
    return parts[1] if len(parts) > 1 else ""


def _copy_rows(source_path, target_path, plan, user_version):
    # type: (str, str, dict, int) -> None
    """source의 테이블을 target에 같은 스키마로 만들고 plan대로 행을 옮긴다. plan = {테이블: None(전부) | (id 열, id 목록) | "pnu5:<코드>"}.
    인덱스는 행을 다 넣은 뒤 만든다(빠르다)."""
    connection = sqlite3.connect(target_path)
    connection.execute("ATTACH DATABASE ? AS source", (source_path,))
    schema = connection.execute("SELECT type, name, tbl_name, sql FROM source.sqlite_master WHERE sql IS NOT NULL").fetchall()
    plan = {table: rule for table, rule in plan.items() if any(kind == "table" and name == table for kind, name, _t, _s in schema)}
    for kind, name, table, sql in schema:
        if kind == "table" and table in plan:
            connection.execute(sql)
    connection.execute("CREATE TEMP TABLE keep (id INTEGER PRIMARY KEY)")
    for table, rule in plan.items():
        if rule is None:
            connection.execute('INSERT INTO "%s" SELECT * FROM source."%s"' % (table, table))
        elif isinstance(rule, str):
            connection.execute('INSERT INTO "%s" SELECT * FROM source."%s" WHERE substr(pnu, 1, 5) = ?' % (table, table), (rule[5:],))
        else:
            column, ids = rule
            connection.execute("DELETE FROM keep")
            connection.executemany("INSERT OR IGNORE INTO keep VALUES (?)", ((i,) for i in ids))
            connection.execute('INSERT INTO "%s" SELECT * FROM source."%s" WHERE %s IN (SELECT id FROM keep)' % (table, table, column))
    for kind, name, table, sql in schema:
        if kind == "index" and table in plan:
            connection.execute(sql)
    connection.execute("PRAGMA user_version = %d" % user_version)
    connection.execute("PRAGMA application_id = %d" % SLIM_PACK_ID)
    connection.commit()
    connection.execute("DETACH DATABASE source")
    connection.execute("ANALYZE")
    connection.close()


def _get_ids_by_sgg(path, table, id_column, sgg_map, pnu_column=None):
    # type: (str, str, str, SggMap, str) -> dict
    """테이블 행 → {시군구: [id]}. pnu_column이 있고 값이 있으면 그 시군구 하나, 아니면 경계상자가 걸치는 격자의 시군구 전부."""
    result = {}
    connection = sqlite3.connect(path)
    columns = "%s, min_x, min_y, max_x, max_y" % id_column + (", %s" % pnu_column if pnu_column else "")
    for row in connection.execute("SELECT %s FROM %s" % (columns, table)):
        pnu = row[5] if pnu_column else None
        sggs = {pnu[:5]} if pnu and len(pnu) == constants.PNU_LENGTH else sgg_map.get_sggs(*row[1:5])
        for sgg in sggs:
            result.setdefault(sgg, []).append(row[0])
    connection.close()
    return result


def split_sido_packs(slug, pack_dir):
    # type: (str, str) -> list
    """pack_dir의 <시도>_site·_context·_terrain.db(줄인 팩)를 시군구 팩 <코드>_<종류>.db로 나눈다. [(이름, 표시 이름, 경로)]. 시도 파일은 지운다.

    필지·토지이용계획·필지 연결표는 PNU 앞 5자리로, 계획 도형·건물(PNU 없는 보충 건물)·피처는 경계상자가 걸치는 200 m 격자의 시군구 전부로
    (경계 객체는 양쪽 팩에 들어간다 — 시군구 팩 하나만 받아도 그 지역은 빠짐없이 나온다. 런타임이 id로 중복을 걷어 낸다).
    """
    site = os.path.join(pack_dir, slug + "_site.db")
    sgg_map = SggMap(site)
    sido_name = next(name for name, s in constants.SIDO.values() if s == slug)
    version = {kind: sqlite3.connect(os.path.join(pack_dir, "%s_%s.db" % (slug, kind))).execute("PRAGMA user_version").fetchone()[0]
               for kind in ("site", "context", "terrain") if os.path.exists(os.path.join(pack_dir, "%s_%s.db" % (slug, kind)))}
    overlay_ids = _get_ids_by_sgg(site, "overlays", "overlay_id", sgg_map)
    out = []
    for sgg in sorted(sgg_map.names):
        target = os.path.join(pack_dir, "%s_site.db" % sgg)
        if os.path.exists(target):
            os.remove(target)
        _copy_rows(site, target, {"data_sources": None, "parcels": "pnu5:" + sgg, "parcel_land_use": "pnu5:" + sgg,
                                  "parcel_overlays": "pnu5:" + sgg, "overlays": ("overlay_id", overlay_ids.get(sgg, []))}, version["site"])
        out.append(("%s_site.db" % sgg, "%s %s 필지" % (sido_name, sgg_map.names[sgg]), target))
    for kind, label in (("context", "건물·도로·수계"), ("terrain", "등고선")):
        source = os.path.join(pack_dir, "%s_%s.db" % (slug, kind))
        if not os.path.exists(source):
            continue
        feature_ids = _get_ids_by_sgg(source, "features", "feature_id", sgg_map)
        building_ids = _get_ids_by_sgg(source, "buildings", "building_id", sgg_map, "pnu") if kind == "context" else {}
        for sgg in sorted(sgg_map.names):
            target = os.path.join(pack_dir, "%s_%s.db" % (sgg, kind))
            if os.path.exists(target):
                os.remove(target)
            plan = {"data_sources": None, "features": ("feature_id", feature_ids.get(sgg, []))}
            if kind == "context":
                plan.update({"source_files": None, "buildings": ("building_id", building_ids.get(sgg, []))})
            _copy_rows(source, target, plan, version[kind])
            out.append(("%s_%s.db" % (sgg, kind), "%s %s %s" % (sido_name, sgg_map.names[sgg], label), target))
    for kind in ("site", "context", "terrain"):
        path = os.path.join(pack_dir, "%s_%s.db" % (slug, kind))
        if os.path.exists(path):
            os.remove(path)
    return out


def _get_sha256(path):
    # type: (str) -> str
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _update_manifest(pack_dir, slug, entries):
    # type: (str, str, list) -> str
    """매니페스트에서 그 시도의 항목(시도 팩 <slug>_* 와 그 시도 시군구 팩)을 빼고 entries를 넣는다. 파일 잠금 — 시도 여러 개를 동시에 압축한다."""
    import fcntl
    manifest_path = os.path.join(pack_dir, "manifest.json")
    code = next(c for c, (_name, s) in constants.SIDO.items() if s == slug)
    with open(manifest_path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        packs = {}
        if os.path.exists(manifest_path):
            with open(manifest_path, encoding="utf-8") as f:
                packs = {pack["name"]: pack for pack in json.load(f)["packs"]}
        packs = {name: pack for name, pack in packs.items()
                 if not name.startswith(slug + "_") and not (name[:5].isdigit() and name[:2] == code)}
        packs.update({entry["name"]: entry for entry in entries})
        with open(manifest_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump({"version": datetime.date.today().isoformat(), "packs": sorted(packs.values(), key=lambda p: p["name"])},
                      f, ensure_ascii=False, indent=1)
        os.replace(manifest_path + ".tmp", manifest_path)
    return manifest_path


def _split_and_compress(slug, pack_dir):
    # type: (str, str) -> list
    """pack_dir의 시도 팩 DB(줄인 것) → 시군구 팩 → xz. 빈 팩은 버린다. 매니페스트 항목 목록."""
    entries, sgg_bounds = [], {}
    for name, label, path in split_sido_packs(slug, pack_dir):   # 필지 팩이 먼저 나온다
        kind = name.rsplit("_", 1)[1][:-3]
        connection = sqlite3.connect(path)
        bounds = connection.execute(BOUNDS_SQL[kind]).fetchone()
        if kind == "context" and bounds[0] is None:   # 건물 없는 시군구(섬 등) — 피처 범위로
            bounds = connection.execute(BOUNDS_SQL["terrain"]).fetchone()
        connection.close()
        if bounds[0] is None:
            os.remove(path)
            continue
        if kind == "site":
            sgg_bounds[name[:5]] = get_site_pack_bounds(path)
        bounds = sgg_bounds.get(name[:5]) or bounds
        size, sha256 = os.path.getsize(path), _get_sha256(path)
        subprocess.run(["xz", "-6", "-T0", "-f", path], check=True)
        entries.append({"name": name, "label": label, "url": name + ".xz", "size": size, "sha256": sha256,
                        "bounds": [round(v, 1) for v in bounds], "xz_size": os.path.getsize(path + ".xz")})
    print("  %s → 시군구 팩 %d개 (압축 %.2f GB)" % (slug, len(entries), sum(e["xz_size"] for e in entries) / 1024.0 ** 3), flush=True)
    return entries


def build_packs(sido_codes=None, drop=False):
    # type: (list, bool) -> str
    """data/의 시도 DB → 줄인 시도 팩 DB → 시군구 팩(<시군구코드>_<종류>.db.xz) + manifest.json. 매니페스트 경로를 돌려준다.

    사용자는 대상지에 걸리는 시군구 팩만 받는다(data_pack). sido_codes를 주면 그 시도만 만들고 다른 시도 항목은 그대로 둔다.
    drop이면 압축 뒤 원본 DB(data/<시도>_site.db·_context.db)를 지운다 — 서울은 개발용이라 남긴다. 전국 원본은 디스크에 다 못 둔다.
    """
    pack_dir = os.path.join(BUILD_DIR, "packs")
    os.makedirs(pack_dir, exist_ok=True)
    manifest_path = os.path.join(pack_dir, "manifest.json")
    data_dir = os.path.join(ROOT_DIR, "data")
    for code, (sido_name, slug) in sorted(constants.SIDO.items(), key=lambda item: item[1][1]):
        if sido_codes and code not in sido_codes:
            continue
        sources = set()
        for kind, _label, source_kind in PACK_KINDS:
            source = os.path.join(data_dir, "%s_%s.db" % (slug, source_kind))
            if not os.path.exists(source):
                continue
            sources.add(source)
            pack_name = "%s_%s.db" % (slug, kind)
            target = os.path.join(pack_dir, pack_name)
            print("  %s 만드는 중..." % pack_name, flush=True)
            if os.path.exists(target):
                os.remove(target)
            _make_pack_database(pack_name, source, target)
        if not sources:
            continue
        manifest_path = _update_manifest(pack_dir, slug, _split_and_compress(slug, pack_dir))
        for kind in ("site", "context", "terrain"):   # 옛 시도 팩 압축본
            old = os.path.join(pack_dir, "%s_%s.db.xz" % (slug, kind))
            if os.path.exists(old):
                os.remove(old)
        if drop and code != "11":
            for source in sources:
                os.remove(source)
    return manifest_path


def repack():
    # type: () -> list
    """build/packs/의 시도 팩 압축본(<시도>_<종류>.db.xz)을 풀어 줄이고(slim 이전 팩이면) 시군구 팩으로 나눠 다시 압축한다. 처리한 시도 목록.
    원본 DB를 지운 시도도 팩에서 바로 다시 만들 수 있다."""
    pack_dir = os.path.join(BUILD_DIR, "packs")
    done = []
    for code, (_name, slug) in sorted(constants.SIDO.items(), key=lambda item: item[1][1]):
        archives = [os.path.join(pack_dir, "%s_%s.db.xz" % (slug, kind)) for kind in ("site", "context", "terrain")]
        if not os.path.exists(archives[0]):
            continue
        print("  %s 풀기..." % slug, flush=True)
        for archive in archives:
            if not os.path.exists(archive):
                continue
            subprocess.run(["xz", "-d", "-f", "-T0", archive], check=True)
            path = archive[:-3]
            connection = sqlite3.connect(path)
            if connection.execute("PRAGMA application_id").fetchone()[0] != SLIM_PACK_ID:
                slim_pack_database(connection, os.path.basename(path).rsplit("_", 1)[1][:-3])
                connection.execute("VACUUM")
            connection.close()
        _update_manifest(pack_dir, slug, _split_and_compress(slug, pack_dir))
        done.append(slug)
    _fill_manifest(pack_dir)
    return done


def _fill_manifest(pack_dir):
    # type: (str) -> list
    """매니페스트에 없는 시군구 팩 압축본을 풀어 크기·sha256·범위를 재고 항목을 채운다(동시 실행으로 항목이 덮어써진 경우, 2026-10-13 대전·서울)."""
    import fcntl
    manifest_path = os.path.join(pack_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        packs = json.load(f)["packs"]
    known = {pack["name"] for pack in packs}
    site_bounds = {pack["name"][:5]: pack["bounds"] for pack in packs if pack["name"].endswith("_site.db")}
    added = []
    for file_name in sorted(os.listdir(pack_dir), key=lambda n: (n[:5], not n.endswith("_site.db.xz"))):   # 필지 팩 먼저(이름)
        name = file_name[:-3]
        if not file_name.endswith(".db.xz") or not name[:5].isdigit() or name in known:
            continue
        path = os.path.join(pack_dir, name)
        subprocess.run(["xz", "-d", "-k", "-f", "-T0", path + ".xz"], check=True)
        kind = name.rsplit("_", 1)[1][:-3]
        connection = sqlite3.connect(path)
        bounds = connection.execute(BOUNDS_SQL[kind]).fetchone()
        if kind == "context" and bounds[0] is None:
            bounds = connection.execute(BOUNDS_SQL["terrain"]).fetchone()
        if kind == "site":
            bounds = get_site_pack_bounds(path) or bounds
        else:   # 같은 시군구 필지 팩 범위(이번에 채운 것 또는 매니페스트에 있는 것)
            bounds = next((p["bounds"] for p in added if p["name"] == name[:5] + "_site.db"), None) or site_bounds.get(name[:5]) or bounds
        sgg_name = ""
        if kind == "site":
            sgg_name = _get_sgg_name((connection.execute("SELECT address FROM parcels LIMIT 1").fetchone() or [""])[0])
        connection.close()
        if not sgg_name:   # 컨텍스트·등고선 팩 — 같은 시군구 필지 팩 항목의 이름을 따른다
            sgg_name = next((" ".join(p["label"].split()[1:-1]) for p in added if p["name"] == name[:5] + "_site.db"), "") or name[:5]
        code = name[:2]
        label = "%s %s %s" % (constants.SIDO[code][0], sgg_name, dict((k, l) for k, l, _s in PACK_KINDS)[kind])
        added.append({"name": name, "label": label, "url": file_name, "size": os.path.getsize(path), "sha256": _get_sha256(path),
                      "bounds": [round(v, 1) for v in bounds], "xz_size": os.path.getsize(path + ".xz")})
        os.remove(path)
    if added:
        with open(manifest_path + ".lock", "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            manifest["packs"] = sorted(manifest["packs"] + added, key=lambda p: p["name"])
            with open(manifest_path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=1)
            os.replace(manifest_path + ".tmp", manifest_path)
    print("  매니페스트에 채운 팩 %d개" % len(added), flush=True)
    return added


DATASET_CARD = """---
license: other
license_name: kogl-type1-cc-by-4.0-etalab-2.0-swisstopo-ogd-odbl
pretty_name: Gorani 데이터 팩
language: [ko, ja, nl, fr, de, en]
tags: [geospatial, korea, japan, netherlands, france, switzerland, usa, plateau, overture, cadastral, buildings, rhino]
---
# Gorani 데이터 팩

Rhino 플러그인 Gorani가 대상지 주변만 받아 쓰는 지역 단위 SQLite 팩(xz 압축)입니다.

## 한국 — 시군구 팩 (좌표계 EPSG:5186)

- `<시군구코드>_site.db.xz` — 필지(토지특성정보 도형·속성), 토지이용계획 지정 현황, 계획 도형(서울 UPIS / 그 외 지정 코드로 필지를 합친 것)
- `manifest.json` — 팩 목록·sha256·범위. 플러그인이 읽는다.
- 건물·도로·수계·등고선 팩(`*_context`·`*_terrain`)은 여기 두지 않는다. 수치지형도(기본측량성과)에서 나온 자료라 국외 서버에 둘 수 없어
  (공간정보관리법 제16조) 국내 서버에 있고, 매니페스트에 그 주소가 적혀 있다.

출처·라이선스 (원천 그대로 — 가공: 재투영·병합·단순화·시군구 분할)
- 국토교통부 토지특성정보·토지이용계획정보 — 이용허락범위 제한 없음(공공데이터포털 15048121·15045900)
- 서울특별시 도시계획정보(UPIS) — 공공누리 제1유형
- 본 데이터는 정보제공 목적이며 법적 효력이 없다(국토교통부 국가중점데이터 안내).

## 일본 — 시구정촌 건물 팩 (`jp/`, 경위도) / 日本 — 市区町村の建物パック

- `jp/jp<시구정촌코드>_context.db.xz` — 국토교통성 3D 도시모델(PLATEAU)의 건물만: LOD0 외곽, LOD1 실측 높이(measuredHeight), 층수, 용도 코드. 306개 시구정촌, 도시마다 최신 연도판.
- `jp/manifest.json` — 일본 팩 목록·sha256·범위(경위도 [서, 남, 동, 북]).
- 각 팩의 `data_sources` 표에 도시 이름·연도·데이터셋 주소가 있다. 도시 경계의 3차 메시는 이웃 도시 팩에도 들어 있어 같은 건물이 두 팩에 있을 수 있다(gml:id로 걸러 낸다).

出典：3D都市モデル（Project PLATEAU）各市区町村（各年度）、国土交通省。CC BY 4.0（公共データ利用規約 第1.0版と互換）。著作権は各地方公共団体にあります。
加工：Gorani が建物の外形・高さ・階数・用途コードだけを抽出し、経緯度（小数6桁）に変換して市区町村ごとの SQLite にしました。国土交通省・地方公共団体が作成したものではありません。

## 네덜란드 — 도엽 건물 팩 (`nl/`, 경위도) / Nederland — gebouwen per kaartblad

- `nl/nl<도엽>_context.db.xz` — Kadaster 3D Basisvoorziening(hoogtestatistieken_gebouwen)의 건물 바닥 윤곽·높이(지붕 50 % − 지반)·건축연도·지붕형만. `nl/manifest.json`.
- Bron: Kadaster, 3D Basisvoorziening (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/deed.nl), bewerkt door Gorani — alleen omtrek, hoogte, bouwjaar en daktype, omgezet naar WGS84 (6 decimalen).

## 프랑스 — 데파르트망 건물 팩 (`fr/`, 경위도) / France — bâtiments par département

- `fr/fr<데파르트망>_context.db.xz` — IGN BD TOPO® `batiment`의 바닥 윤곽·높이(hauteur, 처마)·층수·용도·출현일만(본토·코르시카). `fr/manifest.json`.
- Source : IGN, BD TOPO® (Licence Ouverte / Open Licence 2.0, Etalab), traité par Gorani — emprise, hauteur, étages, usage et date d'apparition uniquement, reprojetés en WGS84 (6 décimales).

## 스위스 — 1:25k 도엽 건물 팩 (`ch/`, 경위도) / Schweiz — Gebäude pro Kartenblatt

- `ch/ch<도엽>_context.db.xz` — swisstopo swissBUILDINGS3D 3.0 Beta의 바닥 윤곽(Floor)·높이(GESAMTHOEHE 또는 DACH_MAX − 지반)·종류·용도만(리히텐슈타인 포함). `ch/manifest.json`.
- Quelle: ©swisstopo, swissBUILDINGS3D 3.0 Beta (OGD-Nutzungsbedingungen — freie Nutzung und Weitergabe mit Quellenangabe), bearbeitet durch Gorani — nur Grundriss, Höhe, Objektart und Nutzung, umgerechnet nach WGS84 (6 Dezimalstellen).

## 미국 — 카운티 건물 팩 (`us/`, 경위도) / United States — buildings per county

- `us/us<카운티 FIPS 5자리>_context.db.xz` — Overture Maps Foundation buildings 테마(Microsoft ML Buildings·OpenStreetMap·Esri Community Maps 합본)의 바닥 윤곽·높이·층수·용도·이름만. 높이는 대부분 Microsoft ML 추정값이다(실측 아님). 카운티 경계는 미국 인구조사국 cartographic boundary(공개). `us/manifest.json`.
- Source: Overture Maps Foundation (buildings theme, release in each pack's `data_sources`), © OpenStreetMap contributors, Microsoft (Global ML Building Footprints) — **Open Database License (ODbL) 1.0**. The `us/` packs are derivative databases and are themselves made available under ODbL 1.0. Processed by Gorani: footprint, height, floors, class and name only, 6-decimal WGS84, split by county. Heights are mostly machine-learning estimates.
"""


def upload():
    # type: () -> str
    """build/packs/의 시군구 팩을 올린다. 필지 팩 + 공개 매니페스트 + 설명은 Hugging Face 데이터셋(constants.DATA_REPO_ID, 공개),
    컨텍스트·등고선 팩은 국내 버킷(constants.DATA_DOMESTIC_BUCKET_URL)에 올리고 매니페스트에는 받기 주소(DATA_DOMESTIC_BASE_URL —
    문지기 서버 또는 버킷)로 적는다.

    `hf auth login`(쓰기 토큰)과 OCI CLI(`brew install oci-cli`, ~/.oci/config API 키)가 먼저 필요하다.
    둘 다 끊겨도 다시 실행하면 이어 올린다(upload_large_folder, oci sync는 크기가 다르거나 로컬이 더 새 파일만 올린다).
    """
    from huggingface_hub import HfApi
    pack_dir = os.path.join(BUILD_DIR, "packs")
    with open(os.path.join(pack_dir, "manifest.json"), encoding="utf-8") as f:
        manifest = json.load(f)
    public = []
    for pack in manifest["packs"]:
        if not pack["name"][:5].isdigit():   # 옛 시도 팩
            continue
        if not pack["name"].endswith("_site.db"):
            pack = dict(pack, url=constants.DATA_DOMESTIC_BASE_URL + pack["url"])
        public.append(pack)
    # 주소 꼴: https://objectstorage.<리전>.oraclecloud.com/n/<namespace>/b/<bucket>/o/
    parts = constants.DATA_DOMESTIC_BUCKET_URL.rstrip("/").split("/")
    subprocess.run(["oci", "os", "object", "sync", "-ns", parts[-4], "-bn", parts[-2], "--src-dir", ".",
                    "--include", "[0-9]*_context.db.xz", "--include", "[0-9]*_terrain.db.xz"],
                   check=True, cwd=pack_dir, env=dict(os.environ, SUPPRESS_LABEL_WARNING="True"))   # --include는 현재 폴더 기준
    stage = os.path.join(BUILD_DIR, "hf_stage")
    os.makedirs(stage, exist_ok=True)
    with open(os.path.join(stage, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(dict(_read_notices(), version=manifest["version"], packs=public), f, ensure_ascii=False, indent=1)
    with open(os.path.join(stage, "README.md"), "w", encoding="utf-8") as f:
        f.write(DATASET_CARD)
    build_config(os.path.join(stage, remote_config.CONFIG_FILE_NAME))   # 원격 설정도 같이(매니페스트 옆)
    api = HfApi()
    api.create_repo(constants.DATA_REPO_ID, repo_type="dataset", private=False, exist_ok=True)
    api.upload_large_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=pack_dir,
                            allow_patterns=["[0-9][0-9][0-9][0-9][0-9]_site.db.xz"])
    api.upload_folder(repo_id=constants.DATA_REPO_ID, repo_type="dataset", folder_path=stage, commit_message="manifest·README")
    print("  올림: 팩 %d개 → https://huggingface.co/datasets/%s + %s" % (len(public), constants.DATA_REPO_ID,
                                                                        constants.DATA_DOMESTIC_BASE_URL), flush=True)
    return constants.DATA_MANIFEST_URL


def _read_notices():
    # type: () -> dict
    """docs/notices.json + docs/countries.json → {"update", "notices", "countries"}. 매니페스트를 올릴 때마다 넣어 팩을 다시 올려도 공지·나라 목록이 지워지지 않게 한다.
    나라 항목이 런타임 검증(data_pack._get_country_pack)에 걸리면 올리기 전에 멈춘다 — 플러그인은 그 나라를 말없이 건너뛰므로 여기서 잡는다."""
    with open(NOTICES_PATH, encoding="utf-8") as f:
        data = json.load(f)
    with open(COUNTRIES_PATH, encoding="utf-8") as f:
        remote = json.load(f)
    countries, services = remote["countries"], remote.get("services") or {}
    bad = [entry.get("code") for entry in countries if not entry.get("disabled") and data_pack._get_country_pack(entry) is None]
    if bad:
        raise ValueError("docs/countries.json 항목이 틀렸습니다(code 2자·bounds 4수·code_pattern 정규식·manifest·source_id·label): %s" % bad)
    return {"update": data.get("update"), "notices": data.get("notices") or [], "countries": countries, "services": services}


def build_config(path=None):
    # type: (str) -> str
    """constants(remote_config.REMOTE_KEYS) + i18n.json → build/config.json. 올리기 전 자가 점검 — 만든 것을 내장값 사본에 apply해 전부 받아들여지고 값이 같아야 한다."""
    config = json.loads(json.dumps(remote_config.build(), ensure_ascii=False))   # JSON 왕복(tuple → list, int 키 → 문자열)을 런타임이 되돌리는지까지
    snapshot = remote_config.get_snapshot()
    report = remote_config.apply(config, target=snapshot, texts={}, version=remote_config.COMPAT_MIN)
    bad = report["rejected"] or [name for name in remote_config.REMOTE_KEYS if getattr(snapshot, name) != getattr(constants, name)]
    if bad or len(report["applied"]) != len(remote_config.REMOTE_KEYS):
        raise ValueError("config.json 자가 점검 실패: %s" % bad)
    path = path or os.path.join(BUILD_DIR, remote_config.CONFIG_FILE_NAME)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False)
    print("  config.json: 상수 %d개 · 번역 %d개 · %.0f KB · compat_min %s" % (len(config["constants"]), len(config["i18n"]), os.path.getsize(path) / 1024.0,
                                                                      config["compat_min"]), flush=True)
    return path


def upload_notices():
    # type: () -> str
    """Hugging Face의 지금 매니페스트를 받아 update·notices(docs/notices.json)·countries(docs/countries.json)만 바꿔 다시 올린다(팩·팩 목록은 그대로)."""
    import urllib.request
    from huggingface_hub import HfApi
    with urllib.request.urlopen(constants.DATA_MANIFEST_URL, timeout=constants.DATA_TIMEOUT_SECONDS) as response:
        manifest = json.loads(response.read().decode("utf-8"))
    manifest.update(_read_notices())
    stage = os.path.join(BUILD_DIR, "hf_stage")
    os.makedirs(stage, exist_ok=True)
    path = os.path.join(stage, "manifest.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)
    api = HfApi()
    api.upload_file(path_or_fileobj=path, path_in_repo="manifest.json", repo_id=constants.DATA_REPO_ID, repo_type="dataset",
                    commit_message="manifest: 업데이트·공지·나라 목록")
    api.upload_file(path_or_fileobj=build_config(), path_in_repo=remote_config.CONFIG_FILE_NAME, repo_id=constants.DATA_REPO_ID, repo_type="dataset",
                    commit_message="config.json: 원격 설정(도면·코드표·파라미터·번역)")
    print("  올림: update %s, 공지 %d개, 나라별 건물 팩 %d나라(%s)" % ("있음" if manifest["update"] else "없음", len(manifest["notices"]),
          len(manifest["countries"]), "·".join(c["code"] for c in manifest["countries"])), flush=True)
    return constants.DATA_MANIFEST_URL


# ── GitHub 사본(Blender판 데이터) ─────────────────────────

MIRROR_SKIP_NAMES = (".gitattributes", "README.md")   # 데이터셋 카드는 사본 저장소 README로(mirror가 따로 올린다)
# GitHub 2차 한도 — 쓰기 요청(자산 올리기 포함) 시간당 약 500건. 2026-10-25 첫 사본에서 4개 동시로 1시간에 약 1,100개를 올리자
# 'secondary rate limit … scraping GitHub'로 막혔다. 하나씩, 시작 간격을 두고 올리고, 막히면 길게 쉰다(되풀이하면 계정이 제한될 수 있다)
MIRROR_INTERVAL = 7.5          # s — 자산 하나 올리기 시작 간격(시간당 480개 이하)
MIRROR_RETRIES = 5             # 그 밖의 오류(HF 끊김 등) — 60 s × 횟수만큼 쉬고 다시
MIRROR_LIMIT_RETRIES = 12      # 2차 한도 — MIRROR_LIMIT_WAIT씩 쉬고 다시
MIRROR_LIMIT_WAIT = 900        # s


def _get_hf_files():
    # type: () -> list
    """Hugging Face 데이터셋 파일 [(경로, 크기, sha256|None)] — 트리 API는 1,000개씩 끊어 주므로 Link 헤더를 따라간다."""
    import urllib.request
    url = "https://huggingface.co/api/datasets/%s/tree/main?recursive=true&limit=1000" % constants.DATA_REPO_ID
    files = []
    while url:
        with urllib.request.urlopen(url, timeout=constants.DATA_TIMEOUT_SECONDS) as response:
            files += [(item["path"], (item.get("lfs") or item)["size"], (item.get("lfs") or {}).get("oid"))
                      for item in json.loads(response.read().decode("utf-8")) if item["type"] == "file"]
            found = re.search(r'<([^>]+)>;\s*rel="next"', response.headers.get("Link") or "")
        url = found.group(1) if found else None
    return files


def _gh(*args):
    # type: (str) -> str
    """gh CLI(개인 계정 토큰 — 회사 계정으로 올리지 않게 GH_TOKEN을 DATA_GITHUB_REPO 주인 것으로 채운다)."""
    env = dict(os.environ)
    if not env.get("GH_TOKEN"):
        env["GH_TOKEN"] = subprocess.run(["gh", "auth", "token", "-u", constants.DATA_GITHUB_REPO.split("/")[0]],
                                         capture_output=True, text=True, check=True).stdout.strip()
    result = subprocess.run(["gh"] + list(args), capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise RuntimeError("gh %s: %s" % (" ".join(args[:3]), (result.stderr or result.stdout).strip()[-300:]))
    return result.stdout


def _get_release_assets():
    # type: () -> dict
    """사본 저장소 릴리스 {태그: {자산 이름: (크기, sha256|None)}}."""
    releases = {}
    pages = json.loads(_gh("api", "--paginate", "--slurp", "repos/%s/releases?per_page=100" % constants.DATA_GITHUB_REPO) or "[]")   # --slurp = 쪽 목록
    for release in (r for page in pages for r in page):
        asset_pages = json.loads(_gh("api", "--paginate", "--slurp", "repos/%s/releases/%d/assets?per_page=100" % (constants.DATA_GITHUB_REPO, release["id"])))
        releases[release["tag_name"]] = {a["name"]: (a["size"], (a.get("digest") or "").replace("sha256:", "") or None)
                                         for page in asset_pages for a in page}
    return releases


def _put_repo_file(path, data):
    # type: (str, bytes) -> bool
    """사본 저장소 main에 파일 하나를 쓴다(contents API). 내용이 같으면 그대로 두고 False."""
    import base64
    try:
        current = json.loads(_gh("api", "repos/%s/contents/%s" % (constants.DATA_GITHUB_REPO, path)))
    except RuntimeError:   # 처음 — 404
        current = None
    if current and base64.b64decode(current["content"]) == data:
        return False
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        body = os.path.join(tmp, "body.json")
        with open(body, "w") as f:
            json.dump(dict({"message": "%s (from the Hugging Face data set)" % path, "content": base64.b64encode(data).decode("ascii")},
                           **({"sha": current["sha"]} if current else {})), f)
        _gh("api", "-X", "PUT", "repos/%s/contents/%s" % (constants.DATA_GITHUB_REPO, path), "--input", body)
    return True


def mirror(dirs=None):
    # type: (list) -> str
    """Hugging Face 데이터셋을 GitHub(constants.DATA_GITHUB_REPO)에 그대로 옮긴다 — Blender판이 읽는 사본(확장 심사 2026-10-25: 'Hugging Face는 빼라').

    입력: dirs = 옮길 데이터셋 폴더(""는 한국 필지 팩이 있는 맨 위, 기본 전부). 개인 계정 gh 로그인 필요.
    처리: 팩은 폴더마다 릴리스(태그 kr·jp·…)에 — 팩이 DATA_GITHUB_ASSET_MAX를 넘으면 us-2 …로 잇는다(이미 올린 팩은 그 자리에 둔다).
          크기·sha256이 같은 팩은 건너뛴다. 하나씩 MIRROR_INTERVAL 간격(GitHub 2차 한도) — 첫 사본 5,479개는 반나절 걸린다. 팩을 다 올린 뒤 매니페스트·config.json을 저장소 같은 경로에 쓴다 — 매니페스트의 상대 팩 주소는
          실제 릴리스의 절대 주소로 바꾸고, 국내 서버 주소(컨텍스트·등고선 팩)와 countries[].manifest(상대 "jp/manifest.json")는 그대로 둔다.
          HF에서 지운 팩은 사본에 남는다(매니페스트가 가리키지 않으니 쓰이지 않는다).
    출력: 사본 한국 매니페스트 주소. 팩·매니페스트를 고친 뒤(dev_deploy upload·notices, dev_plateau 등) 이것을 돌린다.
    """
    import tempfile
    import time
    import urllib.request
    hf_base = "https://huggingface.co/datasets/%s/resolve/main/" % constants.DATA_REPO_ID
    gh_base = "https://github.com/%s/releases/download/" % constants.DATA_GITHUB_REPO
    repo_files = ("manifest.json", remote_config.CONFIG_FILE_NAME)   # 저장소 파일로 두는 것(나머지는 릴리스 자산)
    by_dir = {}
    for path, size, sha in _get_hf_files():
        folder, _, name = path.rpartition("/")
        if name not in MIRROR_SKIP_NAMES and (dirs is None or folder in dirs):
            by_dir.setdefault(folder, []).append((name, size, sha))
    releases = _get_release_assets()

    def fetch(folder, name):
        with urllib.request.urlopen(hf_base + (folder + "/" if folder else "") + name, timeout=120) as response:
            return response.read()

    def fetch_and_upload(item):
        folder, tag, name = item
        errors, limits = 0, 0
        while True:
            started = time.time()
            try:
                with tempfile.TemporaryDirectory() as tmp:
                    path = os.path.join(tmp, name)
                    with urllib.request.urlopen(hf_base + (folder + "/" if folder else "") + name, timeout=120) as response, open(path, "wb") as out:
                        shutil.copyfileobj(response, out, 1024 * 1024)
                    _gh("release", "upload", tag, path, "--clobber", "-R", constants.DATA_GITHUB_REPO)
                time.sleep(max(0.0, MIRROR_INTERVAL - (time.time() - started)))
                return name
            except Exception as error:
                limited = any(word in str(error) for word in ("secondary rate limit", "scraping GitHub", "HTTP 429", "HTTP 403"))
                errors, limits = errors + (not limited), limits + limited
                if errors >= MIRROR_RETRIES or limits >= MIRROR_LIMIT_RETRIES:
                    raise
                wait = MIRROR_LIMIT_WAIT if limited else 60 * errors
                print("  %s %s — %d s 쉬고 다시: %s" % ("한도" if limited else "오류", name, wait, str(error)[:120]), flush=True)
                time.sleep(wait)

    for folder in sorted(by_dir, key=lambda f: (f != "", f)):   # 한국 필지 팩부터
        base_tag = folder or "kr"
        tags = sorted((t for t in releases if t == base_tag or re.fullmatch(re.escape(base_tag) + r"-\d+", t)),
                      key=lambda t: int(t.rsplit("-", 1)[1]) if t != base_tag else 1)
        files = by_dir[folder]
        located = {name: tag for tag in tags for name in releases[tag]}
        todo, place = [], {}
        for name, size, sha in sorted(files):
            if name in repo_files:
                continue
            tag = located.get(name)
            if not tag:   # 새 팩 — 자리가 남은 첫 릴리스, 없으면 하나 더
                tag = next((t for t in tags if len(releases[t]) < constants.DATA_GITHUB_ASSET_MAX), None)
                if not tag:
                    tag = base_tag if not tags else "%s-%d" % (base_tag, len(tags) + 1)
                    _gh("release", "create", tag, "-R", constants.DATA_GITHUB_REPO, "--title", tag, "--latest=false",
                        "--notes", "Gorani data packs: %s. Sources and licenses: README." % (folder or "Korean parcels"))
                    releases[tag] = {}
                    tags.append(tag)
                releases[tag][name] = (None, None)   # 자리 잡기
            place[name] = tag
            have = releases[tag].get(name)
            if not have or have[0] != size or (sha and have[1] and have[1] != sha):
                todo.append((folder, tag, name))
        print("%s → %s: 파일 %d개, 올릴 팩 %d개" % (folder or "(맨 위)", "·".join(tags), len(files), len(todo)), flush=True)
        for index, name in enumerate(map(fetch_and_upload, todo), 1):
            if index % 20 == 0 or index == len(todo):
                print("  %d/%d %s" % (index, len(todo), name), flush=True)
        for name in (n for n, _, _ in files if n in repo_files):
            data = fetch(folder, name)
            if name == "manifest.json":
                manifest = json.loads(data.decode("utf-8"))
                for pack in manifest.get("packs") or []:
                    if "://" not in pack["url"]:
                        pack_name = pack["url"].rsplit("/", 1)[-1]
                        if pack_name not in place:
                            raise ValueError("매니페스트가 가리키는 팩이 데이터셋에 없습니다: %s/%s" % (folder, pack_name))
                        pack["url"] = gh_base + place[pack_name] + "/" + pack_name
                data = json.dumps(manifest, ensure_ascii=False, indent=1).encode("utf-8")
            path = (folder + "/" if folder else "") + name
            print("  %s %s" % ("씀" if _put_repo_file(path, data) else "같음", path), flush=True)
    return constants.DATA_GITHUB_MANIFEST_URL


def rebounds():
    # type: () -> str
    """build/packs/의 시군구 필지 팩을 하나씩 풀어 범위(get_site_pack_bounds)를 다시 재고, 그 시군구 세 팩의 매니페스트 bounds를 바꾼다.
    팩 파일·sha256은 그대로라 올릴 때 매니페스트만 바뀐다(dev_deploy upload)."""
    import fcntl
    import tempfile
    pack_dir = os.path.join(BUILD_DIR, "packs")
    manifest_path = os.path.join(pack_dir, "manifest.json")
    with open(manifest_path, encoding="utf-8") as f:
        sites = [pack["name"] for pack in json.load(f)["packs"] if pack["name"][:5].isdigit() and pack["name"].endswith("_site.db")]
    new_bounds = {}
    for index, name in enumerate(sites):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, name)
            with open(path, "wb") as out:
                subprocess.run(["xz", "-dc", "-T0", os.path.join(pack_dir, name + ".xz")], stdout=out, check=True)
            bounds = get_site_pack_bounds(path)
        if bounds:
            new_bounds[name[:5]] = [round(v, 1) for v in bounds]
        print("  %d/%d %s %s" % (index + 1, len(sites), name, new_bounds.get(name[:5])), flush=True)
    with open(manifest_path + ".lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
        for pack in manifest["packs"]:
            if pack["name"][:5] in new_bounds:
                pack["bounds"] = new_bounds[pack["name"][:5]]
        with open(manifest_path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=1)
        os.replace(manifest_path + ".tmp", manifest_path)
    return manifest_path


def main():
    parser = argparse.ArgumentParser(description="Yak 패키지·Blender·SketchUp 확장·웹판·데이터 팩 빌드")
    parser.add_argument("what", nargs="?", default="all", choices=("all", "smoke", "yak", "blender", "sketchup", "web", "packs", "repack", "upload", "notices", "config", "rebounds", "mirror"))
    parser.add_argument("--sido", help="packs: 쉼표로 구분한 시도 코드만 (기본 data/에 있는 전부)")
    parser.add_argument("--drop", action="store_true", help="packs: 압축 뒤 원본 시도 DB를 지운다(서울 제외)")
    parser.add_argument("--dirs", help="mirror: 쉼표로 구분한 데이터셋 폴더만(맨 위 = 빈 이름, 예: ',jp') — 기본 전부")
    args = parser.parse_args()
    if args.what in ("all", "yak") and sys.version_info[:2] != (3, 9):
        sys.exit("Rhino 8의 CPython(3.9)과 같은 Python 3.9로 실행해야 .pyc가 호환됩니다. 현재: %d.%d" % sys.version_info[:2])
    if args.what in ("all", "smoke", "yak", "blender", "sketchup"):   # 배포 전 점검 — 건너뛰는 옵션 없음
        check_tiles()
        if args.what == "smoke":
            return
    if args.what == "blender":
        print("blender: %s" % build_blender())
        print("  설치: Blender 4.2+ 환경 설정 > Get Extensions > Install from Disk, 또는 Blender -c extension install-file -r user_default -e <zip>")
        return
    if args.what == "sketchup":
        rbz = build_sketchup()
        print("sketchup: %s (%.0f MB)" % (rbz, os.path.getsize(rbz) / 1e6))
        print("  설치: SketchUp 2022+ 확장 > Extension Manager > Install Extension, 올리기: docs/sketchup_store.md")
        return
    if args.what == "web":
        print("web: %s" % build_web())
        print("  로컬 시험: python3 -m http.server -d build/web 8766 → http://127.0.0.1:8766/ (팩 주소는 ?manifest=)")
        return
    if args.what == "upload":
        print("manifest: %s" % upload())
        return
    if args.what == "config":
        print("만듦 →", build_config())
        return
    if args.what == "notices":
        print("notices: %s" % upload_notices())
        return
    if args.what == "mirror":
        print("mirror: %s" % mirror(args.dirs.split(",") if args.dirs is not None else None))
        return
    if args.what == "rebounds":
        print("rebounds: %s" % rebounds())
        return
    if args.what == "repack":
        print("repack: %s" % repack())
        return
    if args.what in ("all", "yak"):
        print("yak: %s" % build_yak())
    if args.what in ("all", "packs"):
        manifest_path = build_packs(args.sido.split(",") if args.sido else None, args.drop)
        print("packs: %s" % manifest_path)
        print("  올리기: python3 scripts/dev_deploy.py upload (필지 → Hugging Face, 컨텍스트·등고선 → 국내 버킷)")


if __name__ == "__main__":
    main()
