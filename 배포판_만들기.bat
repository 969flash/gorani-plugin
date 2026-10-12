@echo off
rem 배포판 만들기 (Windows) — 더블클릭. Rhino 8이 설치한 CPython 3.9로 실행
cd /d "%~dp0"
"%USERPROFILE%\.rhinocode\py39-rh8\python.exe" scripts\dev_deploy.py
pause
