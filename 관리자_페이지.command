#!/bin/bash
# 관리자 페이지 (macOS) — 더블클릭. 브라우저가 열리고, 이 터미널 창을 닫으면 끝난다
cd "$(dirname "$0")" && /usr/bin/python3 scripts/dev_admin.py
