#pragma once

#include "GSRoot.hpp"

// Gorani 메뉴 — 애드온 옆 Gorani 폴더의 번들 파이썬으로 사이드카(scripts/cmd_archicad.py)를 띄운다.
// 사이드카가 패널(ShowScriptUI 팔레트)을 열고 엔진을 돌린다. 이미 떠 있으면 사이드카가 패널만 다시 연다.
void SetGoraniArchicadVersion (Int32 mainVersion);
void LaunchGorani ();
