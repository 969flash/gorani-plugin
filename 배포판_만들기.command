#!/bin/bash
# 배포판 만들기 (macOS) — 더블클릭. 저장소 루트의 scripts/dev_deploy.py를 Rhino와 같은 Python 3.9로 실행
cd "$(dirname "$0")" && /usr/bin/python3 scripts/dev_deploy.py
