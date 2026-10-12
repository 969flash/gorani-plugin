# 06. 도시설계 베이스맵 Illustrator(.ai) 파일 생성 방법 조사

- 작성일·접근일: 2026-10-07 (2차 검증 반영판 — 맨 아래 "검증 이력" 참조)
- 로컬 확인 환경: macOS, Rhino 8.35 (`/Applications/Rhino 8.app`), Adobe Illustrator 2026 v30.2.1, QGIS 3.44.7, Affinity 3.2.0, `/usr/bin/python3` 3.9.6 (geopandas·shapely·matplotlib 3.9.4 설치, ezdxf·pikepdf 미설치)
- 표기: **[공식]** 제조사 문서·API·소스코드, **[미러]** 제조사 레퍼런스를 커뮤니티가 옮겨 둔 사이트(docsforadobe 등 — 원문과 같은 내용이지만 Adobe 호스팅 아님), **[포럼]** McNeel Discourse·Adobe Community·UserVoice(사용자/전문가 발언), **[로컬]** 설치된 바이너리·파일에서 직접 확인, **[미검증]** 초안 작성 시 인용했으나 2026-10-07 2차 검증에서 다시 열어 확인하지 못한 출처(내용이 틀렸다는 뜻은 아님), **확인 필요** = 열어서 확인하지 못했거나 실험이 필요한 사항

---

## 0. 요약 (결론·추천)

| 순위 | 방법 | 판정 | 한 줄 근거 |
|---|---|---|---|
| **1 (주력)** | **(b′) Python이 레이어별 SVG 생성 → Illustrator ExtendScript(JSX)가 "SVG 1개 = 레이어 1개"로 자동 조립 → `.ai` 저장** | **채택 (§5 테스트 1·4·7 통과 조건부)** | 레이어를 Illustrator 자신이 스크립트로 명시 생성하므로 중간 포맷 해석에 의존하지 않음. 축척·단위·정밀도·톤·선두께를 우리가 100% 제어. 기존 Seoungsu SVG 스크립트 재사용. API(`layers.add`, `groupItems.createFromFile`, `saveAs`)는 Illustrator Scripting Reference **[미러]**. 단 `createFromFile`의 SVG 텍스트 라이브 유지·배치 기준점·단위 해석·무인 실행 트리거는 아직 미확인 → "확실·완결"은 테스트 전까지 보류 |
| **2 (대안·동급 후보)** | **(d) ezdxf → DXF R2007 → JSX가 `app.preferences.AutoCADFileOptions` 설정 후 `app.open()` → `.ai` 저장** | **채택 후보 (§5 테스트 6 결과로 1·2순위 결정)** | DXF는 레이어를 포맷 자체에 담고(`mergeLayers` 기본 false **[미러]**), R2007은 UTF-8이라 한글 OK **[공식]**, 좌표 double, 축척·단위·선두께는 `OpenOptionsAutoCAD`(unit·unitScaleRatio·globalScaleOption·scaleLineweights)로 스크립트 지정 가능 → 대화상자 없이 전 과정 자동화. 약점: DXF 폴리라인에는 면 채움 개념이 없어 건물 톤을 solid `HATCH`에 의존(Illustrator 변환 품질 미검증), 폰트 매핑, ezdxf 미설치 |
| 3 (보조) | (a) Rhino 8 내장 `.ai` export (`Preserve model scale`) | 보조·현장용 | 공식 문서에는 `Order layers`(레이어 순서) 옵션만 있고 "레이어·색 보존" 문장은 없음. 레이어 보존은 바이너리의 `%AI5_BeginLayer` **[로컬]** 와 교육자료 **[미검증]** 로 간접 확인. Rhino가 쓰는 포맷은 **AI3/AI5 세대 PostScript(.ai legacy)** → Illustrator "부분적으로만 읽음" 보고 다수, Mac 버그 보고(체크박스 상태 고착, 치수·문자 포함 시 파일 손상), 해치는 solid fill 또는 선뿐(해치가 중요하면 PDF 경로가 낫다는 McNeel 발언 — §1(a)), 한글 문자 신뢰도 미확인 |
| 4 (조건부·실험) | (g) Python이 legacy AI(PostScript, AI3 procset + `%AI5_BeginLayer`)를 **직접** 텍스트로 생성 | 실험 후 결정 | Rhino가 쓰는 legacy AI는 평문 PostScript라 Python만으로 "레이어를 직접 담는" .ai를 쓸 수 있고 Illustrator 스크립트 의존이 없음. 단 지오메트리 전용(한글 텍스트는 PostScript 폰트 경로라 제외), 포맷 사양 URL 미확인, Illustrator 2026이 AI3 레이어를 복원하는지 실험 필요 |
| 5 | (f) QGIS 레이아웃 → SVG(`Export map layers as SVG groups`) → (b′)의 JSX로 레이어화 | 가능 | 그룹명=QGIS 레이어명. 다만 Qt SVG가 "very basic" **[공식]**, 지도 스타일을 QGIS에서 다시 잡아야 하므로 Python SVG 직접 생성보다 이득 없음 |
| 6 | (e) Rhino PDF (OCG 레이어) | 비추천(.ai 목적) | 선두께·해치 재현은 좋으나 **Illustrator는 PDF OCG를 레이어로 열지 않음**(McNeel 스태프·Adobe 전문가·UserVoice 2018~2026 미해결; 스크립팅 API `PDFFileOptions`에도 레이어 관련 옵션이 없음 **[미러]**). 해치가 중요한 1회성 도면 전달에는 (a)보다 유리 |
| 7 | (c) Python으로 OCG PDF 생성(pikepdf 등) | 폐기 | (e)와 같은 이유로 Illustrator에서 레이어가 되지 않음. 생성 도구와 무관 |
| 8 | (b) SVG를 그냥 Illustrator에서 `Open` | 수동 보조 | 모든 `<g>`가 **한 레이어 안의 그룹**으로 들어옴(Adobe Community Expert, 2025-10). Layers 패널 메뉴 `Release to Layers (Sequence/Build)`로 1회 수동 레이어화는 가능(메뉴 존재는 **[로컬]**, 동작 상세는 확인 필요). `i:layer="yes"` 어휘는 SVG 플러그인에 남아 있으나 레이어 승격 동작은 **실험 필요** |

핵심 결론: 중간 포맷 가운데 **Illustrator 레이어를 포맷 자체에 담는 것은 DXF(layer 테이블)와 legacy PostScript AI(`%AI5_BeginLayer`)** 뿐이고, SVG는 그룹만, PDF는 OCG가 무시된다. 따라서 "레이어 있는 .ai"를 자동으로 만드는 신뢰할 만한 길은 두 가지 — **(b′) Illustrator(JSX)가 레이어를 직접 만들게 하거나, (d) DXF를 `AutoCADFileOptions`로 무대화상자 열기** — 이며, 둘 다 §5의 1회 테스트로 확정한다. Rhino 자체 .ai는 legacy 포맷이라 대형·한글·해치에서 깨질 위험이 있어 보조로 둔다.

---

## 1. 후보별 상세

### (a) Rhino 8 내장 Adobe Illustrator(.ai) 내보내기

**옵션 (Windows/Mac 공통) [공식]** — McNeel Rhino 8 Help "Adobe Illustrator (.ai) Import/Export" (Windows: http://docs.mcneel.com/rhino/8/help/en-us/fileio/ai_ai_import_export.htm, Mac: https://docs.mcneel.com/rhino/8mac/help/en-us/fileio/ai_ai_import_export.htm, 접근 2026-10-07)

| 옵션 | 공식 설명(원문) | 메모 |
|---|---|---|
| Snapshot of current view | "Rhino exports the curves as a 2-D snapshot from the active viewport." | 화면 크기 기준, 축척 없음 |
| Preserve model scale | "Sets the scale factor and units you want to use." / "You cannot preserve the scale and units from a perspective viewport." | 평면(Top) 뷰에서만 축척 유지 |
| RGB / CMYK | 색 체계 선택 | 인쇄용은 CMYK |
| Export viewport boundary | "Exports a rectangle that corresponds to the current viewport boundary." | 렌더링과 레지스터용 |
| Hatches exported as solid fills | 체크 시 solid fill, 해제 시 선으로 export | **패턴 해치는 보존 안 됨** |
| Order layers | "Exports layers using their display order in the Layer panel." | 레이어 순서 보존. **레이어·색 "보존"을 명시한 문장은 Windows·Mac 페이지 어디에도 없다** |
| Always use these settings. Do not show this dialog again. | Mac 페이지에 기재(2026-10-07 확인; Windows 페이지 기재 여부 재확인 필요) | 바이너리 설정 키 `AI_Rhino DontShowDialog` **[로컬]** 에 대응 → GUI `Export`·`RhinoDoc.Export` 경유 무인 export 시 유용 |
| 곡선 | "Curves have fewer control points than the original because the Adobe Illustrator file format only supports non-rational cubic Bézier curves." / degree 3 이하 자유곡선을 Top 뷰에서 내보내면 refit 안 됨 | 좌표 정밀도는 refit 허용오차에 좌우(수치 미공개) |
| 문자·치수 | "Text and dimensions are exported to AI files" | 라이브 텍스트 |
| NURBS·메시 | 와이어프레임 곡선으로 export | 3D 불가 |

Mac 도움말 페이지는 Windows와 같은 옵션에 "Always use these settings. Do not show this dialog again." 체크박스가 더 기재되어 있고, 그 밖의 Mac 전용 기능 서술은 없다 (Mac 페이지, 2026-10-07 확인).

**실제 파일 포맷 [로컬]** — `/Applications/Rhino 8.app/Contents/PlugIns/export_AI.rhp/Contents/MacOS/export_AI` (Rhino 8.35) 바이너리의 wide 문자열:
`%!PS-Adobe-3.0`, `%%Creator: Rhinoceros`, `%%IncludeResource: procset Adobe_IllustratorA_AI3 1.0 0`, `%AI3_ColorUsage: Color`, `%AI5_BeginLayer` / `%AI5_EndLayer--`, `%%DocumentFonts: %ls`, `%%IncludeFont: %ls`, `(%ls) Tx`, `%%BoundingBox: %d %d %d %d`, `%AI3_TileBox: 0 0 576 768`, 경로·색 연산자 `%ls %ls m` / `%ls %ls l` / `%ls %ls L`, `%.4f %.4f %.4f %.4f K` / `k`(CMYK 선·면), `%.4f %.4f %.4f XA` / `Xa`, 문자 `… 0 Tp`.

> **추출 방법(재현용)**: macOS 기본 `/usr/bin/strings`에는 `-e` 옵션이 없어(`unknown flag: -e`, 2026-10-07 확인) wide 문자열이 나오지 않는다. 이 플러그인의 wide 문자열은 macOS `wchar_t` = **UTF-32LE**(문자당 4바이트)이므로 Python으로 뽑는다:
> ```python
> import re
> b = open("/Applications/Rhino 8.app/Contents/PlugIns/export_AI.rhp/Contents/MacOS/export_AI", "rb").read()
> for m in re.finditer(rb"(?:[\x20-\x7e]\x00\x00\x00){4,}", b):
>     print(m.group().decode("utf-32le"))
> ```
> (`export_ACAD.rhp`의 DWG 스킴 문자열도 같은 방법.)

→ Rhino는 **PostScript 기반 legacy AI(AI3 procset + AI5 레이어 주석)** 를 쓴다. 현재 .ai(PDF 기반)가 아니다. 레이어는 `%AI5_BeginLayer`로 들어가므로 Illustrator가 legacy 파서로 읽을 때 레이어로 복원된다고 보는 것이 합리적이며, 교육자료도 같은 말을 한다("All exported objects will retain their Rhino layers and colors", UT Austin wiki https://wikis.utexas.edu/display/SOAdigitech/Exporting+from+Rhino+to+.dwg,+.ai [교육자료, **미검증**]). 공식 문서에는 이 보존 문장이 없으므로 **간접 확인** 수준이다. 문자는 PostScript `Tx`/`Tp` 연산자와 `%%DocumentFonts`(글꼴명)로 기록 → 한글(멀티바이트) 처리 여부 **확인 필요**(아래 버그 보고 참조).

**스크립트 호출 [로컬]+[포럼]**
- 바이너리에서 확인된 명령행 옵션 토큰: `PreserveUnits`, `PreserveModelScale`, `ViewportBoundary`, `ExportViewBoundary`, `ExportHatchesAsSolidFills`, `HatchesAsSolidFills`, `OrderLayers`, `UseCMYK`, `Unit`, `AiUnits`, `RhinoScale`, `AIScale` (설정 키: `AI_Rhino Export Scale`, `AI_Rhino MakeSolidHatches`, `AI_Rhino Order Layers`, `AI_Rhino ViewportBoundary`, `AI_Rhino WriteCMYK`, **`AI_Rhino DontShowDialog`**).
- 포럼에 공유된 실제 매크로(Windows Rhino 5, okeating 2016-02-25): `! _-Export _Pause "C:\...\curves.ai" PreserveUnits=Yes _Unit=MM ViewportBoundary=No _Enter` — https://discourse.mcneel.com/t/copy-paste-between-rhino-illustrator/29721 [포럼]. Rhino 8.35에서의 정확한 프롬프트 순서는 `-Export`를 대화식으로 한 번 실행해 명령행에 뜨는 옵션명으로 확정할 것(Dale Fugier 2023-12-27 권고: 파일 확장자로 포맷 결정, `_-Export "{filename}" _Enter` — https://discourse.mcneel.com/t/export-command-line-options/87537 [포럼]).
- RhinoCommon **[공식, 로컬 RhinoCommon.xml 8.35]**: `RhinoDoc.Export(string)` (7.0) / `RhinoDoc.Export(string, ArchivableDictionary options)` (8.0, "Options to help define how data should be exported") / `ExportSelected(...)` 동일 / `RhinoDoc.WriteFile(string, FileWriteOptions)`; `FileWriteOptions.SuppressDialogBoxes` = "If true, it means the command has been run with a '-', meaning you should not ask questions during writing." `ArchivableDictionary`에 넣을 AI 플러그인 키 이름은 미공개 → **확인 필요**(위 설정 키 `AI_Rhino …`가 후보; `AI_Rhino DontShowDialog`를 켜 두면 대화상자 없이 마지막 설정으로 export될 가능성이 높음 — 실험 필요).
- CPython(Rhino 8 ScriptEditor)에서는 `rs.Command('-_Export "…/x.ai" PreserveUnits=Yes Unit=Millimeters … _Enter')` 형태가 가장 확실.

**알려진 문제 [포럼]**
| 보고 | 내용 | 출처 |
|---|---|---|
| Mac, Rhino 7·8, 2024-01 | "Preserve model scale" 체크 해제해도 활성 상태 유지(체크박스 상태 고착). McNeel(Gijs) 재현 실패 | https://discourse.mcneel.com/t/export-into-illustrator-bug/172613 |
| Mac, 2024-08 / 2026-07 | 치수·지시선 포함 레이어 켜고 export 시 Illustrator "could partially read this file"; 문자 객체 삭제하니 정상. Dale Fugier: "Try saving a PDF file from Rhino and opening that in Illustrator" | https://discourse.mcneel.com/t/exporting-from-rhino-to-adobe-illustrator/190010 |
| Win, 2018-11 | 중첩 블록 안 해치가 아트보드 중앙에 쌓임, 스케일된 해치 누락 → 버그 RH-49623. 같은 스레드에서 Pascal Golay(2018-11-21): **"printing to pdf seems to get it right as far as the hatches in AI go."** → 해치가 중요하면 .ai 직접 export보다 Rhino PDF→Illustrator가 해치 재현에 유리(McNeel 측 발언, 2026-10-07 재확인) | https://discourse.mcneel.com/t/illustrator-export-with-hatches/75082 |
| Win, 2018-12 | Export with origin이 .ai에서 무시 → RH-49877; 문자 정렬·크기 불일치 | https://discourse.mcneel.com/t/export-illustrator-with-origin-doesnt-work-bug/76079 |
| Mac, 2021-12 **[미검증]** | 원점에서 먼 객체가 Illustrator 최대 캔버스(약 227 in) 밖에 놓여 "빈 파일"처럼 보임. Wim Dekeyser: "I would first try with a more modern file format like PDF" | https://discourse.mcneel.com/t/rhino-to-illustrator-not-working/134755 |
| 2017-11 **[미검증]** | 같은 현상; Illustrator 오류 "Artboard size cannot be bigger than the canvas size." | https://community.adobe.com/t5/illustrator-discussions/blank-page-when-exported-rhino-drawing-file-into-illustrator/td-p/8495434 |
| 2024-10~12 | 레이아웃(페이퍼 스페이스)은 .ai export 불가, 모델 뷰포트만. PDF 레이어는 Illustrator가 인식 못 함(Wim Dekeyser: "Adobe's Illustrator product apparently does not") | https://discourse.mcneel.com/t/trying-to-export-a-layout-into-illustrator-with-layers/193378 |
| 2025-05 **[미검증]** | .ai가 export 목록에 없음 → `PluginManager`에서 Adobe Illustrator 플러그인 체크 | https://discourse.mcneel.com/t/option-to-export-as-illustrator-ai-not-showing-up/204814 |
| 2023-01 **[미검증]** | Preserve model scale 입력 방법: Pascal Golay "if your file is in mm, and you export with 25.4 mm = 1 inch, then in AI if you set the units to inches, it should measure correctly" (좌=모델 단위, 우=AI 단위) | https://discourse.mcneel.com/t/question-about-preserve-model-scale-when-exporting-as-ai-illustrator/153606 |

**Mac/Windows 차이 정리**: export 옵션은 동일[공식](Mac 페이지에 "Always use these settings…" 체크박스 추가 기재). Rhino↔Illustrator **클립보드 벡터 복사는 Windows 전용**(Steve Baer 2023-05: "only have this working on Windows for now", 29721 [포럼]). Mac Rhino 8은 macOS 시스템 인쇄 대화상자를 쓰지 않으며 되살릴 계획도 없음(Dan, 2023-12-04: "We do not have plans to bring back the macOS system print dialog in Rhino." — https://discourse.mcneel.com/t/rhino-8-print-dialog-missing-pdf-options/170592 [포럼], 2026-10-07 재확인). 같은 스레드의 **RH-79156(Dan, 2023-12-15)은 "Print Dialog: Open in Preview functionality missed" 티켓으로, 시스템 인쇄 대화상자가 아니라 'Preview로 열기' 편의 기능 누락 건**이다(초안의 연결 오류 정정). Mac 전용 버그 보고가 상대적으로 많다(위 표).

**평가**: 레이어·색·축척은 되는 것으로 보이지만(공식 문서상 보장은 아님) (1) legacy 포맷, (2) 해치=solid/선 — 해치 재현은 PDF 경로가 낫다는 McNeel 발언(75082), (3) 한글·치수 포함 시 손상 보고, (4) 캔버스 한계, (5) 레이어 톤·선두께를 Rhino에서 다시 세팅해야 함. 베이스맵 "최종본" 파이프라인보다는 Rhino 안에서 그린 보조 선형을 빠르게 넘기는 용도로 한정.

### (b) SVG 생성 후 Illustrator에서 열기

- **그룹→레이어 규칙**: Illustrator는 SVG `<g>`를 레이어가 아닌 **그룹**으로 연다. Adobe Community Expert Monika Gause(2025-10-21): "SVGs do not have a layer element, so it will be difficult for any application to figure out what the user intended." 질문자는 "an Illustrator script to convert these `<g>` elements into layers after importing the SVG"로 해결 중 — https://community.adobe.com/questions-652/how-to-create-g-elements-in-svg-that-are-recognized-as-layers-in-illustrator-817756 [포럼]. 같은 전문가, 2021: "SVG doesn't know the concept of layers anyway. Make groups instead." — https://community.adobe.com/t5/illustrator-discussions/layered-svg-export-in-adobe-illustrator/td-p/14083757 [포럼].
- **스크립트 없는 수동 레이어화 — `Release to Layers`**: Illustrator 30.2.1 Layers 패널 메뉴에 `Release to Layers (Sequence)` / `Release to Layers (Build)` 항목이 있음 **[로컬]** (`Adobe Illustrator.app/Contents/Required/Plug-ins/Extensions/Layers.aip/Contents/Resources/mnu/LayersPanel.mnu`, `…/str/11000.str`). 선택한 그룹(레이어)의 하위 항목을 각각 서브레이어로 승격하는 기능으로 알려져 있어, SVG를 `Open`한 뒤 최상위 그룹들을 1회 클릭으로 레이어화하는 수동 대안이 된다. Adobe helpx 레이어 페이지는 접근 차단으로 동작 원문 **확인 필요**(하위 항목이 "서브레이어"로 가는지, 최상위 레이어로 가는지, 이름이 유지되는지 — §5 테스트 8).
- **`i:layer="yes"` (xmlns:i="http://ns.adobe.com/AdobeIllustrator/10.0/") 현황**:
  - Illustrator 30.2.1의 SVG 포맷 플러그인(`Adobe Illustrator.app/Contents/Required/Plug-ins/Illustrator Formats/svgFileFormat.aip`)에 문자열 `http://ns.adobe.com/AdobeIllustrator/10.0/`, `&ns_ai;`, `i:layer`, `i:dimmedPercent`, `rgbTrio`, `i:aipgfRef`, `adobe_illustrator_pgf`가 존재 **[로컬]** → 파서가 이 어휘를 알고 있다(자체 "Preserve Illustrator Editing Capabilities" SVG의 PGF 데이터용). `inkscape:groupmode`, `sodipodi` 문자열은 없음 → Inkscape 레이어 표기는 무시된다고 봐야 함.
  - 그러나 "외부 생성 SVG의 `<g i:layer="yes">`를 레이어로 승격하는가"를 확인한 공식 문서·현행 버전 테스트는 찾지 못함 → **실험 필요**(§5 테스트 키트). 2008년 Inkscape 버그 리포트에서는 Illustrator CS2가 자체 SVG에 `i:layer`를 쓰지 않았고, 수동 삽입 시 "invalid XML"로 열리지 않았다는 기록(네임스페이스 미선언 추정) — https://bugs.launchpad.net/inkscape/+bug/179680 [포럼, **미검증**].
- **단위**: Illustrator는 SVG에 저장된 단위 정보를 문서 단위로 쓰지 않음. Ton Frederiks(Community Expert, 2023-10): "There is no unit saved when you export an SVG. The last opened/created file or the last set unit in the Preferences is used when opening an SVG." — https://community.adobe.com/t5/illustrator-discussions/default-unit-millimeters-when-opening-svg-files-not-pixels/m-p/14190269 [포럼]. 따라서 **`width="841mm" height="594mm" viewBox="0 0 841 594"`** 처럼 절대단위로 쓰고, 열린 뒤 아트보드가 841×594 mm인지 1회 검증(§5).
- **텍스트**: `<text>`는 라이브 텍스트로 들어옴(기존 Seoungsu 스타일 가이드 전제: `font-family="Pretendard, 'Noto Sans KR', sans-serif"` 인라인 지정, 아웃라인 금지 — `/Users/sanghoon/Documents/GitHub/Seoungsu/figures/style_guide.md` [로컬]). 폰트가 설치돼 있어야 치환이 안 일어난다.
- **해치**: SVG `<pattern>`의 Illustrator 임포트 지원 범위 미확인 → 베이스맵은 회색 solid fill만 사용하고, 꼭 필요한 해치는 선 지오메트리로 직접 생성(Rhino .ai export와 같은 원칙).
- **성능 실측 [로컬, 2026-10-07 재확인]**: Seoungsu `figures/basemap_L/05_buildings.svg` = `<path>` 41,537개, 6,772,970 B(6.77 MB); `04_roads.svg` = `<path>` 10,106개, 1,461,592 B(1.46 MB) (1px=5m 캔버스, 소수 1자리). 두 파일만 합쳐도 약 5.2만 path가 `createFromFile` 2회 호출로 들어간다. Illustrator 열기 시간은 미측정 → **확인 필요**(§5 테스트 4의 "10 s" 기준은 근거 없는 작업 편의상 임계값이다). 좌표를 소수 2~3자리(종이 mm 기준)로 제한하고 `simplify(0.05 mm 종이)`를 적용하면 파일·앵커 수를 더 줄일 수 있다.
- **기존 자산의 서술 정정**: "Illustrator에서 열면 위 5개 레이어로 분리되어 편집 가능하다"는 문장은 `figures/basemap_L/README.md`가 아니라 **`figures/style_guide.md` §6 "레이어 구조(모든 SVG 공통)"**(66행; 모든 분석 SVG 공통 `<g id="bg|geo|data|labels|sources">` 5그룹)에 있다 **[로컬]**. 이 서술은 위 Adobe 전문가 답변(그룹으로 열림)과 상충 → 실제 동작 **재확인 필요**. 반면 `basemap_L/README.md`는 레이어 자동 분리를 주장하지 않고, 레이어별 SVG 12개(00_satellite … 11_office_share)를 각각 열어 **"전체 선택 → Paste in Place(⇧⌘V)"로 수동 중첩**하는 워크플로(모든 레이어 동일 캔버스 + 투명 register 사각형)를 전제한다 — 이 register 방식이 (b′)의 배치 기준점 문제 해결책이기도 하다.

### (b′) [채택] SVG → Illustrator ExtendScript로 레이어 조립 → .ai 저장

**근거 API [미러]** (Adobe Illustrator Scripting Reference를 옮겨 둔 docsforadobe — Adobe 공식 호스팅이 아닌 커뮤니티 미러, 접근 2026-10-07)
- `GroupItems.createFromFile(imageFile)`: "Places an external vector art file as a group item in the document." 반환 `GroupItem` — https://ai-scripting.docsforadobe.dev/jsobjref/GroupItems/
- `Document.saveAs(saveIn, options)`: "Saves the document in the specified file as an Illustrator, EPS, or PDF file." — https://ai-scripting.docsforadobe.dev/jsobjref/Document/
- `IllustratorSaveOptions`: `compatibility`(기본 ILLUSTRATOR19), `pdfCompatible`(기본 true), `compressed`, `embedICCProfile`, `fontSubsetThreshold` — https://ai-scripting.docsforadobe.dev/jsobjref/IllustratorSaveOptions/
- 스크립트 실행 경로: "File > Scripts", Presets/Scripts 폴더, "File > Scripts > Other Script", 시작 스크립트 폴더 — https://ai-scripting.docsforadobe.dev/introduction/executingScripts/
- 실전 사례 [포럼]: GIS에서 나온 SVG 10개를 레이어별 .ai 하나로 합치는 스크립트(Muppet Mark, 2012-12-11): `doc.layers.add()` + `lay.groupItems.createFromFile(fileList[i])` — https://community.adobe.com/t5/illustrator/svg-files-into-one-layered-ai-file/td-p/4733751
- 대안 사례 [포럼, **미검증**]: SVG를 `Open`한 뒤 최상위 그룹을 레이어로 바꾸는 스크립트(Silly-V, 2016-01-12; "works best when you start out with only 1 layer and that layer has only groups inside the top-level") — https://community.adobe.com/questions-652/how-to-convert-all-groups-to-layers-769433

**왜 가장 신뢰할 수 있나**: 레이어는 Illustrator가 직접 만들고, 레이어명·순서·잠금·색은 JSX에서 지정하므로 중간 포맷의 해석 차이에 의존하지 않는다. 축척·좌표계는 Python 쪽에서 EPSG:5186 미터 → 종이 mm로 선형변환하므로 Rhino 캔버스 한계·refit 오차와 무관. 실패 모드는 (1) `createFromFile` 배치 위치, (2) SVG 단위 해석, (3) 폰트 치환 — 셋 다 §5의 1회 테스트로 고정 가능. **단, 테스트 전까지는 "확실·완결"이 아니라 "가장 유력"이다.**

**한계·확인 필요**
- `createFromFile`가 SVG 텍스트를 라이브로 유지하는지(`Open`과 동일 파서인지), 그룹 배치 기준점(아트보드 중앙 vs 원점) — register 사각형(캔버스 전체 크기의 투명 rect, Seoungsu 방식)으로 모든 레이어의 bounds를 동일하게 만들어 `position`을 한 줄로 정렬하면 해결.
- **Python → Illustrator 무인 실행 트리거**: 로컬 `Adobe Illustrator.app/Contents/Resources/Adobe Illustrator.sdef`(301,978 B)에 AppleScript 명령 `do javascript`가 정의되어 있음 **[로컬]** — `<command name="do javascript" code="miscDjxM" description="execute a javascript">`, direct-parameter "javascript code or file to execute"(type any), 옵션 `with arguments`(list), `show debugger`. (초안의 "sdef 추출 실패"는 `sdef` 도구 호출 실패였고 파일 자체는 존재.) 따라서 1순위 트리거는
  `osascript -e 'tell application "Adobe Illustrator" to do javascript (POSIX file "/abs/build_ai.jsx")'`
  (코드 문자열/파일 참조 중 어느 형태를 받는지, `with arguments`로 SVG 목록을 넘길 수 있는지는 §5 테스트 7에서 1회 확인). Adobe의 "Illustrator AppleScript Scripting Reference"에 같은 명령이 문서화돼 있는 것으로 알려져 있으나 본 검증에서 1차 출처 URL **미확인 → 확인 필요**(확인 방법: Adobe Developer 사이트의 Illustrator scripting PDF 묶음에서 AppleScript Reference를 열어 `do javascript` 항목 대조). `open -a "Adobe Illustrator" build.jsx`는 .jsx를 "열기"로 실행하는 동작이 보장되지 않으므로 2순위. 최악의 경우 File > Scripts > Other Script로 1회 클릭.
- **ExtendScript 지속성 리스크**: Illustrator 2026(v30)에서 .jsx는 여전히 실행되지만(sdef `do javascript` 존재, 실행 경로 문서), Adobe가 UXP 스크립팅으로 전환 중이므로 장기 지원·폐기 일정은 **확인 필요**. 스크립트는 API 표면을 작게(`layers.add`, `createFromFile`, `saveAs`, `open`) 유지해 이식 비용을 낮춘다.

### (c) 레이어 있는 PDF(OCG)를 Python으로 생성 → Illustrator

- PDF "레이어"는 Optional Content Group이며 Illustrator 레이어와 다른 개념. Ton Frederiks(Adobe Community Expert, 2022-09-13): "PDF Layers" are not the kind of layers you see in an Illustrator file … are named Optional Content Groups — https://community.adobe.com/questions-652/pdf-layers-visible-in-illustrator-797937 [포럼, **미검증**]. Stephen Marsh(2020-05-27): "A PDF is flat, it does not have layers, PDF layers are actually Optional Content Groups (OCG) and are more like a content filter than a layer." — https://community.adobe.com/questions-712/open-a-one-page-pdf-from-illustrator-into-layers-1094113 [포럼, **미검증**].
- Illustrator가 외부 OCG를 레이어로 열지 않는다는 점은 2018-10-29 기능요청(39표)이 2026년까지 열려 있고 댓글(Lance, 2020-07) "Illustrator does not see OCG's." — https://illustrator.uservoice.com/forums/333657-illustrator-desktop-feature-requests/suggestions/35852185-keep-layers-from-pdf-when-opening-the-file-in-illu [포럼]. McNeel 측도 동일 확인(193378, 98973).
- **스크립팅 API 측 보강 [미러]**: `app.preferences.PDFFileOptions`(PDF 열기·배치 옵션)에는 `pageToOpen`(기본 1), `pDFCropToBox`(기본 `PDFBoxType.PDFMediaBox`)뿐이고 **레이어/OCG 관련 속성이 없다** — https://ai-scripting.docsforadobe.dev/jsobjref/PDFFileOptions/ , https://ai-scripting.docsforadobe.dev/jsobjref/Preferences/ (2026-10-07). 반면 AutoCAD 열기 옵션에는 `mergeLayers`가 있다(§1(d)). 즉 Illustrator에는 PDF OCG를 레이어로 받는 기능 자체가 노출돼 있지 않다.
- Adobe 공식 "Import PDF files" 도움말은 2026-10-07 현재 직접/프록시/아카이브 모두 접근 차단(HTTP 403/422/404) → 공식 문구 **확인 필요**. 그러나 위 독립 출처(Adobe 전문가·UserVoice·McNeel 스태프·API 부재)가 일치.
- 결론: pikepdf/reportlab/matplotlib/cairo 어느 것으로 만들어도 Illustrator에서는 평면화됨. (Affinity 3.2는 PDF 레이어를 읽는다는 사용자 보고 — 193378 [포럼] — .ai가 목표가 아니면 대안.)

### (d) DXF/DWG(ezdxf) → Illustrator — 2차 검증에서 "전 자동화 가능"으로 상향

- Illustrator **[공식]** "Import AutoCAD files"(최종 수정 2023-05-24): "You can import AutoCAD files from version 2.5 through version 2007." / "Illustrator will not open AutoCAD files saved in a version later than AutoCAD 2007." 임포트 시 Scale, Unit 매핑, Line weight scaling, Layout 선택, Center artwork 옵션 제공. 지원 데이터: 3D objects, shapes/paths, external references, region, spline(베지어로 변환), raster, text — https://helpx.adobe.com/illustrator/using/importing-eps-dcs-autocad-files.html (리더 프록시 경유 확인). 레이어 보존 문장은 프록시 추출에 없었으나, 아래 스크립팅 API의 `mergeLayers`(기본 false = 레이어를 합치지 않음)가 **DXF 레이어가 기본적으로 Illustrator 레이어로 유지됨**을 Adobe 측 레퍼런스로 뒷받침한다.
- **스크립팅으로 임포트 대화상자 대체 [미러]** — `app.preferences.AutoCADFileOptions`(type `OpenOptionsAutoCAD`, "Options to use when opening or placing an AutoCAD file") — https://ai-scripting.docsforadobe.dev/jsobjref/Preferences/ ; 속성 — https://ai-scripting.docsforadobe.dev/jsobjref/OpenOptionsAutoCAD/ (2026-10-07):

  | 속성 | 형 | 기본값 | 설명(원문) |
  |---|---|---|---|
  | `centerArtwork` | Boolean | true | "If true, the artwork is centered on the artboard." |
  | `globalScaleOption` | AutoCADGlobalScaleOption | FitArtboard | "How to scale the drawing on import." |
  | `globalScalePercent` | Number | 100.0 | "The value when globalScaleOption is ScaleByValue, expressed as a percentage" |
  | `mergeLayers` | Boolean | **false** | "If true, the layers of the artwork are merged." |
  | `scaleLineweights` | Boolean | false | "If true, line weights are scaled by the same factor as the rest of the drawing." |
  | `selectedLayoutName` | String | - | "The name of the layout in the drawing to import." |
  | `unit` | AutoCADUnit | Millimeters | "The unit to map to." |
  | `unitScaleRatio` | Number | 1.0 | "The ratio by which to scale while mapping units." |

  이 속성들을 설정한 뒤 `app.open(File)`을 부르면 대화상자 없이 열린다 → **초안의 "자동화 끊김" 판정은 철회**. 골격:
  ```javascript
  var o = app.preferences.AutoCADFileOptions;          // OpenOptionsAutoCAD
  o.unit = AutoCADUnit.Millimeters; o.unitScaleRatio = 1.0;   // DXF 1 unit = 1 mm (종이 mm 좌표로 쓴 DXF 전제)
  o.globalScaleOption = AutoCADGlobalScaleOption.ScaleByValue; o.globalScalePercent = 100; // 기본 FitArtboard는 축척을 깨므로 반드시 변경
  o.centerArtwork = false; o.mergeLayers = false; o.scaleLineweights = false;
  var doc = app.open(new File("/abs/path/basemap.dxf"));
  doc.saveAs(new File("/abs/path/basemap.ai"), new IllustratorSaveOptions());
  ```
  (enum 식별자 `AutoCADUnit.Millimeters`, `AutoCADGlobalScaleOption.ScaleByValue`의 정확한 철자, 열린 문서의 아트보드 크기 결정 방식은 §5 테스트 6에서 확인.)
- ezdxf **[공식]**: 쓰기 지원 "R12, R2000, R2004, R2007, R2010, R2013 and R2018"; DWG는 ODA File Converter(`odafc` 애드온) 필요; 최신 1.4.4(2026-05-14)는 Python ≥3.10 — https://ezdxf.readthedocs.io/en/stable/ . **Python 3.9 환경에서는 ezdxf 1.3.5(2024-12-15, requires_python >=3.9)** — https://pypi.org/pypi/ezdxf/1.3.5/json . 인코딩: "Starting with DXF R2007 (AC1021) the drawing file is UTF-8 encoded" (R2004 이하는 `$DWGCODEPAGE`, 한글은 ANSI_949) — https://ezdxf.readthedocs.io/en/stable/dxfinternals/fileencoding.html . 단위: `$INSUNITS` 6=m, 4=mm, `doc.units = units.M` — https://ezdxf.readthedocs.io/en/stable/concepts/units.html . 베이스맵용으로는 frame.py의 종이 mm 좌표를 그대로 쓰고 `$INSUNITS=4`(mm)로 저장하는 것이 가장 단순.
- Rhino 자체 DWG/DXF export 스킴에 `2007 Natural / 2007 Lines / 2007 Polylines / 2007 Solids`가 있음(`export_ACAD.rhp` 문자열 **[로컬]**, 추출 방법은 §1(a)) → ezdxf 없이도 Illustrator 호환 DWG 생성 가능.
- 남는 한계: (1) DXF 폴리라인에는 면 채움 속성이 없으므로 건물·수계 톤은 solid `HATCH`(ezdxf `add_hatch` + `set_solid_fill`) 엔티티로 써야 하고 Illustrator의 HATCH→채움 변환 품질·성능 미확인, (2) 폰트 매핑(DXF TEXT/MTEXT 스타일 → Illustrator 폰트) 미확인, (3) 선두께는 DXF lineweight(1/100 mm 정수 단계)로 제한되나 `scaleLineweights=false`면 그대로 pt 변환되는지 미확인, (4) ezdxf 설치 필요. 좌표 정밀도는 DXF double이라 충분, 레이어명 한글은 R2007 UTF-8로 OK.

### (e) Rhino PDF 내보내기

- **[공식]** "Rhino PDF is Rhino's own PDF printer that supports saving layers to PDF files." / "Raster Output does not support saving layers to PDF." / "PDF readers have to support viewing layers. (Such as Adobe Acrobat Reader)" / `Rhino.Options.Advanced.PDF.OptionalContentGroups=0`으로 비활성 — https://docs.mcneel.com/rhino/8/help/en-us/commands/print.htm , http://docs.mcneel.com/rhino/8/help/en-us/fileio/portable_document_format_pdf_import_export.htm
- **[공식, 로컬 RhinoCommon.xml]** `Rhino.FileIO.FilePdf.LayersAsOptionalContentGroups` (7.0): "Add layers as "optional content groups" to the PDF. This is the visible layer tree available in PDF viewers"; `FilePdf.Create()`, `AddPage(ViewCaptureSettings)`, `Write(path)`; `ViewCaptureSettings.SetModelScaleToValue(double)`, `DefaultPrintWidthMillimeters`, `OutputColor`, `RasterMode`, `UsePrintWidths` → 스크립트로 축척 지정 PDF 생성 가능.
- Steve Baer(2020-05-26): "PDF actually calls this feature optional content groups and is really only for allowing the visibility to be toggled." 2021-09 사용자 보고: Illustrator가 이 레이어를 인식 못 함 — https://discourse.mcneel.com/t/how-to-print-pdf-with-layers/98973 [포럼, **미검증**]. Illustrator 스크립팅 API에도 PDF 레이어 옵션이 없음(§1(c)).
- 선두께: Mac Rhino 7 PDF는 0.25 mm(0.7 pt) 미만 선이 올려짐 보고(2021-11, 미해결) — https://discourse.mcneel.com/t/pdf-via-export-line-width-below-0-25mm-0-7-pt/132509 [포럼]. 베이스맵 지적선(0.05~0.1 mm)에 치명적 → Rhino 8에서 재확인 필요.
- 해치: Pascal Golay(2018-11-21, 75082): "printing to pdf seems to get it right as far as the hatches in AI go" → Rhino 안에서 그린 해치를 Illustrator로 넘길 때는 .ai export보다 PDF가 낫다(McNeel 측 발언). 단 레이어는 사라진다.
- 결론: Illustrator 목적에는 레이어가 사라지므로 부적합. 다만 (1) 해치가 중요한 1회성 도면, (2) Rhino에서 그린 3D 컨텍스트의 Make2D 결과를 "참조 이미지"로 깔 때는 유용.

### (f) 기타: QGIS, Inkscape

- QGIS 3.44 **[공식]** SVG: "Export map layers as SVG groups: exported items are grouped within layers whose name matches the layer names from QGIS"; "Always export as vectors"; "Simplify geometries to reduce output file size"; "Text export: … text or outline objects"; "Note: Currently, the SVG output is very basic. This is not a QGIS problem, but a problem with the underlying Qt library." — https://docs.qgis.org/3.44/en/docs/user_manual/print_layout/create_output.html
- QGIS PDF **[공식]**: "Create Geospatial PDF: Generate a georeferenced PDF file." + "Include vector feature information (choose the layers and group them into logical PDF groups)". 소스코드 확인: `QgsLayoutExporter::exportToPdf`는 `settings.writeGeoPdf || settings.exportLayersAsSeperateFiles`일 때만 레이어별 PDF를 만들어 GDAL PDF 드라이버(`COMPOSITION_FILE`, `IfLayerOn` 요소)로 합성하고, 아니면 Qt `QPdfWriter`로 단일 스트림을 쓴다 — https://raw.githubusercontent.com/qgis/QGIS/master/src/core/layout/qgslayoutexporter.cpp , https://raw.githubusercontent.com/qgis/QGIS/master/src/core/qgsabstractgeopdfexporter.cpp (접근 2026-10-07). 즉 **PDF OCG 레이어는 Geospatial PDF 모드에서만** 생성되며(GDAL PDF 드라이버 `LAYER_NAME`, `OGR_DISPLAY_LAYER_NAMES`, `OFF_LAYERS` 등 — https://gdal.org/en/stable/drivers/raster/pdf.html [공식]), 어차피 Illustrator가 OCG를 무시하므로 (c)와 같은 결론. North Road 소개글(2019-09-03)도 Acrobat Reader 기준 설명 — https://north-road.com/2019/09/03/qgis-3-10-loves-geospatialpdf/ [블로그].
- 레이어 불투명도 <100%는 PDF export 시 래스터화됨 **[공식]**(같은 QGIS 페이지) → 톤은 불투명 회색으로.
- Inkscape: 미설치. Inkscape 레이어 표기(`inkscape:groupmode="layer"`)는 Illustrator SVG 플러그인에 어휘가 없음 **[로컬]** → Illustrator에서 그룹으로만 열림. Inkscape의 PDF 출력에도 OCG가 없다(확인 필요). 변환 경유 가치 없음.

### (g) [신규·조건부] Python이 legacy PostScript AI를 직접 생성

- 근거: §1(a)에서 확인했듯 Rhino의 .ai는 **평문 PostScript**(`%!PS-Adobe-3.0`, `%%IncludeResource: procset Adobe_IllustratorA_AI3 1.0 0`, `%AI5_BeginLayer` … `%AI5_EndLayer--`, 경로 연산자 `m`/`l`/`L`/`c`, 색 `K`/`k`/`XA`/`Xa`) 이다 **[로컬]**. 따라서 Rhino로 레이어 2~3개짜리 작은 .ai를 한 번 내보내 텍스트 에디터로 열면 그대로 템플릿이 되고, Python `str.format`만으로 "레이어를 포맷 자체에 담은" .ai를 쓸 수 있다 — Illustrator 스크립트·AppleScript·대화상자가 전혀 필요 없는 유일한 경로.
- 조건: (1) **지오메트리 전용** — 한글 라벨은 PostScript 폰트(`%%DocumentFonts`, `Tx`/`Tp`) 경로라 인코딩·폰트 치환 위험이 커서 제외하고, 라벨 레이어는 (b′)/(d)로 따로 넣거나 Illustrator에서 작성. (2) Illustrator 2026이 AI3 procset + AI5 레이어 주석을 지금도 레이어로 복원하는지는 (a)와 같은 실험으로 확인(§5 테스트 3·9). (3) 사양서: Adobe "Adobe Illustrator File Format Specification"(Version 7, 1998)이 공개돼 있는 것으로 알려져 있으나 본 검증에서 URL **미확인 → 확인 필요**(확인 방법: Adobe Developer/Acrobat SDK 문서 묶음 또는 archive.org에서 "Adobe Illustrator File Format Specification 7.0" 검색). 사양서 없이도 Rhino 출력물 모방으로 충분하다.
- 장점: 한 레이어 4만 path도 텍스트 쓰기이므로 생성이 즉시, 캔버스 한계(227 in)와 좌표 정밀도(`%.4f` pt)만 지키면 됨. 단점: 미공개 세부(레이어 색·잠금 플래그 인자 의미)는 실험으로 역추정해야 하고, Illustrator가 legacy 파서를 제거하면 바로 사장됨.

---

## 2. 후보 비교표

| 항목 | (a) Rhino .ai | (b′) SVG+JSX **[주력]** | (d) DXF R2007+JSX **[대안]** | (g) Python legacy AI | (e) Rhino PDF | (f) QGIS |
|---|---|---|---|---|---|---|
| Illustrator 레이어 보존 | O 추정 (legacy `%AI5_BeginLayer`, 공식 문장 없음) | **O (스크립트가 생성)** | **O (DXF layer; `mergeLayers` 기본 false [미러])** | O 추정 (`%AI5_BeginLayer` 직접 기록, 실험 필요) | X (OCG 무시, API도 없음) | SVG: 그룹→JSX 필요 / PDF: X |
| 축척 지정 | Preserve model scale(평면 뷰만) | mm viewBox로 임의 축척 | `unit`·`unitScaleRatio`·`globalScaleOption=ScaleByValue`를 JSX로 지정 | pt 좌표 직접 계산 | ViewCaptureSettings | 레이아웃 축척 |
| 레이어명 한글 | 가능(미검증) | O (JSX 문자열) | O (R2007 UTF-8) | X 권장(PostScript 문자열) | - | O |
| 한글 라이브 텍스트 | 손상 보고 있음, 미검증 | O (폰트 설치 전제) | 폰트 매핑 미검증 | X (지오메트리 전용) | 텍스트 유지 | 텍스트/아웃라인 선택 |
| 면 톤(fill) | solid 해치 | `fill` 그대로 | solid HATCH 의존(변환 미검증) | `k`/`f` 직접 기록 | 양호 | 양호 |
| 해치 | solid 또는 선(PDF가 낫다는 McNeel 발언) | solid 권장(`<pattern>` 미검증) | HATCH 변환 미검증 | 선으로 직접 | 양호 | 선패턴 벡터 |
| 선두께 | Rhino print width→pt 변환(보고 상이) | `stroke-width` mm 그대로 | DXF lineweight 단계 + `scaleLineweights` | `w` 연산자 직접 | 0.7pt 하한 보고(Mac R7) | 양호 |
| 좌표 정밀도 | 베지어 refit(허용오차 미공개) | 우리가 제어(소수 3자리 mm) | double | `%.4f` pt | 양호 | 단순화 옵션 |
| 수만 객체 | 보고 다수, 캔버스 227in 한계 | SVG 생성은 문제없음, 열기 시간 미측정 | 가능(HATCH 수만 개 성능 미측정) | 텍스트 쓰기라 생성 즉시, 열기 미측정 | 가능 | 가능 |
| 자동화 | `-Export` 옵션 문자열(확정 필요) | Python → JSX 전체 자동(`osascript do javascript`, 테스트 7) | **Python(ezdxf) → JSX `AutoCADFileOptions`+`open()` 전체 자동(대화상자 불필요)** | Python만으로 완결 | 전체 자동 | PyQGIS |
| 플랫폼 | Mac 버그 보고 다수 | Mac/Win 동일 | 동일 | 동일 | 동일 | 동일 |
| 구현 난이도 | 낮음 | 중(JSX 60줄 + Python) | 중(ezdxf 설치 + JSX 10줄) | 중(템플릿 역추정) | 낮음 | 높음(스타일 재작업) |

---

## 3. 도시설계 베이스맵 관행 → 레이어 설계

관행 요약(과제 제시 + Seoungsu 실무 레이어): 흑백·회색 톤, 축척 1:1000~1:5000, A1/A0, 레이어명 영문·한글 병기. 아래 수치는 **제안값**(실무 관행 기반, 공식 출처 없음 — 사용자 조정).

**용지·축척 조견(산술 정정)**: A1(841×594 mm) 1:5000 = 4.205×2.97 km, 1:1000 = 841×594 m. A0(841×1189 mm, ISO 216) 1:5000 = **4.205×5.945 km**. 성수 4도엽 프레임은 약 **4.41×5.55 km**(Seoungsu `figures/basemap_L/README.md` 2행, `scripts/make_basemap_L.py` 4행 [로컬]) → 1:5000이면 **882×1110 mm**가 필요하므로 A0 세로(폭 841)에도, 가로로 돌려도(4.41 km > 4.205 km) **수납 불가**(초안의 "A0 세로 1:5000 수납"은 오류). 선택지:

| 선택 | 용지 | 축척 | 프레임 종이 크기 | 여백(좌우/상하) |
|---|---|---|---|---|
| 축척 완화 | A0 세로 | 1:5500 | 802×1009 mm | 약 20 / 90 mm |
| 축척 완화 | A0 세로 | 1:6000 | 735×925 mm | 약 53 / 132 mm |
| 커스텀 용지 | 1000×1300 mm | 1:5000 | 882×1110 mm | 약 59 / 95 mm (Illustrator 캔버스 한계 227 in 이내) |
| 프레임 크롭 | A0 세로, 여백 20 mm | 1:5000 | 801×1149 mm = **4.005×5.745 km** | 20 / 20 mm |

frame.py는 (용지, 축척, 중심) 세 값으로 프레임을 계산하고 범위 초과 시 경고만 내면 된다.

| 순서(아래→위) | 레이어명 (영문 / 한글) | 원천 데이터 | 톤(K%) / 선 | 선두께 mm (1:5000 / 1:1000) | 비고 |
|---|---|---|---|---|---|
| 00 | `00_frame_scale / 프레임·축척·방위` | 생성 | K100 선, 축척바·N | 0.5 / 0.5 | 캔버스 전체 register rect 포함 |
| 01 | `01_water / 수계` | 필지 DB 지목 하천·구거 + 수치지형도 E001/E003/E005 | K10 fill | - | 강·하천면 |
| 02 | `02_green / 녹지·공원` | 수치지형도 경지·공원, OSM(ODbL 표기) | K6 fill | - | 공원명 라벨은 12 |
| 02b | `02b_landuse / 토지이용현황` | 필지 DB 지목·용도(대/공장/학교용지/공원/주차장 등) | 지목별 K4~K14 fill | - | **신규** — 현황도 필수. 기본 off, 02·03과 겹치지 않게 지목 대 중심 |
| 03 | `03_road_surface / 도로면` | 필지 DB 지목 도로 ∪ 수치지형도 A001 면 | K18 fill | - | 면으로 |
| 04 | `04_road_edge / 도로경계` | 수치지형도 A001 선 | K40 | 0.1 / 0.15 | |
| 05 | `05_road_center / 도로중심선` | A002 중심선 | K60 dashed | 0.1 / 0.1 | 보통 off |
| 06 | `06_rail / 철도·역` | 수치지형도 A005 / OSM | K80, 역은 ○ | 0.3 / 0.4 | 노선별 서브그룹(Seoungsu 06_rail 방식) |
| 06b | `06b_transit / 교통결절(지하철 출입구·버스정류장)` | 지하철 출입구·버스정류장 점 데이터 — 서울열린데이터광장/국가대중교통정보 (레이어·API 확정은 `04b_public_data_analysis_layers.md` 참조, **확인 필요**) | K70 점 마커 | 2 mm 심벌 | **신규** — 현황도 필수 |
| 07 | `07_bldg_low / 건물 1~4층` | VWorld LT_C_BLDGINFO + 수치지형도 B001 | K12 fill, K45 outline | 0.08 / 0.12 | 층수 톤 4단계 |
| 07 | `07_bldg_mid / 건물 5~9층` | 〃 | K22 fill | 〃 | |
| 07 | `07_bldg_high / 건물 10~19층` | 〃 | K32 fill | 〃 | |
| 07 | `07_bldg_tower / 건물 20층+` | 〃 | K45 fill | 〃 | |
| 08 | `08_parcel / 지적선` | 기존 필지 DB | K50 | 0.05 / 0.08 | 1:5000에선 off 기본 |
| 08b | `08b_parcel_no / 지번 라벨` | 필지 DB(PNU→지번) | K60 텍스트 | 4~5 pt | **신규** — 대상지 주변만, 1:1000용. 기본 off |
| 09 | `09_contour / 등고선` | 수치지형도 F001(주곡선)·F002(계곡선) 또는 DEM | K35 / 계곡선 K55 | 0.08 / 0.1, 계곡선 0.15 | 강 포함 지형 |
| 09b | `09b_spot_relief / 표고점·음영기복` | 수치지형도 표고점 / DEM 힐셰이드(래스터) | K70 점+수치 / 래스터 링크 | 4 pt | **신규·옵션** — 음영기복은 래스터이므로 SVG `<image>` 링크 또는 Illustrator Place |
| 10 | `10_site / 대상지` | 사용자 입력 | K100 | 0.7 / 0.9 | 대상지 경계 |
| 11 | `11_zoning / 용도지역·지구단위` | 필지 DB 오버레이 | K70 dashed | 0.3 / 0.4 | 보통 off, 분석도용. **구역명·고시번호·면적 부기 라벨을 구역 그룹 안에 내장**(Seoungsu 07_zones 방식 — 그룹 토글 시 함께 켜지고 꺼짐) |
| 11b | `11b_admin / 행정경계·행정동명` | 행정경계(시군구·행정동) 폴리곤 — 출처·레이어 확정은 `04a_public_data_base_layers.md` 참조(**확인 필요**) | K55 dash-dot, 연회색 라벨 | 0.25 / 0.3 | **신규** — 현황도 필수(Seoungsu 09_labels의 `admin(행정동)` 그룹을 독립 레이어로) |
| 11c | `11c_poi / 공공시설·랜드마크` | 수치지형도 건물 명칭·용도(관공서·학교·병원·문화) + 사용자 지정 | K90 점·다이아 마커 | 2.5 mm 심벌 | **신규** — Seoungsu 08_landmarks 방식(시설 점 + 기업·예정지 다이아) |
| 12 | `12_labels / 주기(지명·도로명·역명·시설명)` | 수치지형도 명칭, 도로명주소 | K85 텍스트 | 6~8 pt | 라이브 텍스트, Pretendard. 하위 그룹 facilities/stations/geo/admin(Seoungsu 09_labels 방식) |
| 13 | `13_grid / 격자` | 생성 | K25 | 0.1 | 500 m / 1 km |

원칙: 색은 모두 K(회색)만, 강조색은 Illustrator에서; 모든 fill은 불투명(투명도는 QGIS PDF 래스터화·AI 투명도 평탄화 원인); 레이어 하나 = SVG 파일 하나 = `<g id="…">` 하나. 신규 6개 레이어 중 **행정경계(11b)·토지이용(02b)·교통결절(06b)** 3종은 도시설계 현황도 표준 구성상 최소 추가분이고, 나머지(08b·09b·11c)는 축척·과제에 따라 선택.

---

## 4. 추천안 구현 스케치

```
[Rhino 안]  UrbanDesignTool 플러그인 (CPython 3.9, RhinoCommon)
  ├─ 대지검토 버튼 → 필지 DB(SQLite) 질의 → 3dm 컨텍스트(필지·건물·도로·지형) 생성
  ├─ "베이스맵 내보내기" 버튼: 프레임(중심·축척·용지·회전)만 결정하고 아래 외부 프로세스를 호출
  └─ (옵션) Rhino에서 그린 보조 선형 → `_-Export … .ai PreserveUnits=Yes Unit=Millimeters …` (보조)

[Rhino 밖]  basemap/ (순수 Python 3.9: geopandas·shapely·sqlite3 — 이미 설치)
  ├─ frame.py      : 용지(A1/A0/커스텀)·축척(1:1000~6000)·EPSG:5186 → 종이 mm 선형변환 (x_mm = (E-E0)/S*1000), 범위 초과 경고
  ├─ layers/*.py   : 레이어별 질의·클립(frame)·simplify(0.05 mm 종이)·톤 적용 → SVG 1개/레이어
  │                  (Seoungsu scripts/make_basemap_L.py 의 geom_paths/save_svg 재사용, 캔버스를 mm viewBox로 교체)
  ├─ build_jsx.py  : 레이어 목록·순서·이름(영문/한글)·출력 경로를 박은 build_ai.jsx 생성
  ├─ run_ai.py     : osascript `tell application "Adobe Illustrator" to do javascript (POSIX file …)` 호출 → basemap.ai, 동시에 PDF 사본
  └─ (대안 d) dxf_out.py : ezdxf로 레이어별 DXF R2007(종이 mm, $INSUNITS=4, 면은 solid HATCH) → JSX `AutoCADFileOptions` 설정 + `app.open()` → saveAs

[Illustrator]  build_ai.jsx
  documents.add(CMYK, 841mm, 594mm) → for 각 SVG: layers.add(name) → groupItems.createFromFile(File)
  → register rect 기준 정렬 → 레이어 색·잠금 → saveAs(.ai, pdfCompatible=true)
```

**SVG 규격(초안)** — `<svg xmlns="http://www.w3.org/2000/svg" width="841mm" height="594mm" viewBox="0 0 841 594">` + `<rect id="register" x="0" y="0" width="841" height="594" fill="none" stroke="none"/>` + `<g id="07_bldg_low">…</g>`; 좌표는 mm 소수 3자리; 스타일은 인라인 presentation attribute만(`fill`, `stroke`, `stroke-width`, `fill-rule="evenodd"`); 텍스트는 `<text font-family="Pretendard, 'Noto Sans KR', sans-serif" font-size="2.1">`(mm 단위 = 6 pt ≈ 2.1 mm).

**build_ai.jsx(골격)** — 모든 API는 §1 (b′) 출처

```javascript
// build_ai.jsx — generated by build_jsx.py
var MM = 72 / 25.4;
var doc = app.documents.add(DocumentColorSpace.CMYK, 841 * MM, 594 * MM);
var files = [ // bottom → top
  ["00_frame_scale 프레임·축척", "/abs/path/00_frame_scale.svg"],
  ["01_water 수계",            "/abs/path/01_water.svg"]
  // ...
];
for (var i = 0; i < files.length; i++) {
  var lay = doc.layers.add();
  lay.name = files[i][0];
  var g = lay.groupItems.createFromFile(new File(files[i][1]));
  g.left = 0; g.top = doc.height;          // register rect 가 캔버스 전체이므로 좌상단 정렬 (확인 필요: 좌표계)
  lay.zOrder(ZOrderMethod.BRINGTOFRONT);
}
var opt = new IllustratorSaveOptions(); opt.pdfCompatible = true;
doc.saveAs(new File("/abs/path/basemap.ai"), opt);
```

Python 쪽 트리거(1순위): `subprocess.run(["osascript", "-e", 'tell application "Adobe Illustrator" to do javascript (POSIX file "/abs/path/build_ai.jsx")'])` — sdef에 `do javascript` 명령 존재 **[로컬]**, 인자 형태는 §5 테스트 7에서 확정. 2순위 `open -a "Adobe Illustrator" build_ai.jsx`(실행 보장 없음), 최후 File > Scripts > Other Script 수동 1회.

**Rhino 보조 경로 매크로(초안, 옵션명은 바이너리 확인·프롬프트 순서는 대화식 1회 실행으로 확정)**
`_-Export "/abs/path/rhino_lines.ai" PreserveUnits=Yes Unit=Millimeters ViewportBoundary=No ExportHatchesAsSolidFills=Yes OrderLayers=Yes UseCMYK=Yes _Enter` — Top 뷰, 모델 원점을 프레임 좌하단으로 이동(`Export with origin` 무시 버그 RH-49877 회피) 후 실행. 해치가 많은 도면은 대신 `FilePdf`(§1(e))로 PDF를 만들어 Illustrator에 Place.

---

## 5. 사용자가 돌릴 1회 검증 테스트(채택안 확정용)

1. **단위·축척**: 위 규격의 빈 SVG(841×594 mm, register rect + 100 mm 정사각형) → Illustrator `Open` → 아트보드 841×594 mm, 정사각형 100 mm인지. `createFromFile`로도 동일한지.
2. **`i:layer` 실험**: `<svg xmlns:i="http://ns.adobe.com/AdobeIllustrator/10.0/" …><g id="L1" i:layer="yes">…</g><g id="L2" i:layer="yes">…</g></svg>` → `Open` → Layers 패널에 L1/L2가 레이어로 뜨는지. 뜨면 JSX 없이도 가능(그래도 JSX 경로를 기본으로 유지).
3. **한글 텍스트**: `<text>` 한글 10개(Pretendard) → 라이브 텍스트·폰트 유지 확인. 같은 문자열을 Rhino `.ai` export로도 내보내 손상 여부 비교(이때 Rhino .ai 파일을 텍스트 에디터로 열어 (g)용 템플릿도 확보).
4. **성능**: Seoungsu `05_buildings.svg`(41,537 path, 6.77 MB)와 `04_roads.svg`(10,106 path, 1.46 MB)를 `createFromFile`로 넣는 시간 측정. "10 s"는 근거 있는 기준이 아니라 작업 편의상 임계값 — 넘으면 `simplify` 강화·층수별 분할.
5. **Rhino `-Export` 옵션명**: Rhino 8.35에서 `-Export` 대화식 실행 → 명령행 옵션 철자·순서 기록 → 매크로 확정. GUI `Export`에서 "Always use these settings…"(`AI_Rhino DontShowDialog`)를 켠 뒤 `RhinoDoc.Export`가 무대화상자로 도는지도 확인.
6. **DXF 경로(대안 d)**: `pip install "ezdxf==1.3.5"` → 레이어 3개(한글명 포함)·100 mm 정사각형·solid HATCH 1개·TEXT 1개를 R2007·`$INSUNITS=4`로 저장 → §1(d) JSX로 `app.open()` → (i) 대화상자 없이 열리는지, (ii) 레이어 3개·한글명 유지, (iii) 정사각형 100 mm(축척), (iv) HATCH가 채움으로, TEXT가 라이브 텍스트로 들어오는지, (v) `AutoCADUnit`/`AutoCADGlobalScaleOption` enum 철자. 통과하면 (b′)와 성능·품질 비교 후 1·2순위 확정.
7. **무인 실행 트리거**: `osascript -e 'tell application "Adobe Illustrator" to do javascript (POSIX file "/abs/t.jsx")'`(t.jsx = `alert("ok")` 또는 파일 쓰기) → 실행되는지; 안 되면 `do javascript "코드 문자열"`, `with arguments` 전달 여부도 기록.
8. **Release to Layers**: Seoungsu SVG 하나를 `Open` → 최상위 레이어 선택 → Layers 패널 메뉴 `Release to Layers (Sequence)` → 하위 그룹이 레이어/서브레이어가 되는지, `id`가 이름으로 유지되는지(수동 비상 경로 확정용).
9. **legacy AI 직접 생성(대안 g)**: 테스트 3에서 확보한 Rhino .ai 템플릿을 Python으로 복제해 레이어 2개·사각형 2개짜리 .ai 작성 → Illustrator `Open` → 레이어 2개 복원·치수 정확 여부.

---

## 6. 출처 목록 (접근일 2026-10-07)

공식 문서·API·소스
- McNeel Rhino 8 Help, Adobe Illustrator (.ai) Import/Export — http://docs.mcneel.com/rhino/8/help/en-us/fileio/ai_ai_import_export.htm ; Mac 판 https://docs.mcneel.com/rhino/8mac/help/en-us/fileio/ai_ai_import_export.htm (Mac 판 2026-10-07 2차 재확인: "Always use these settings. Do not show this dialog again." 기재, 레이어·색 보존 문장 없음)
- McNeel Rhino 8 Help, PDF Import/Export — http://docs.mcneel.com/rhino/8/help/en-us/fileio/portable_document_format_pdf_import_export.htm ; Print — https://docs.mcneel.com/rhino/8/help/en-us/commands/print.htm
- RhinoCommon 8.35 XML 문서(로컬) — `/Applications/Rhino 8.app/Contents/Frameworks/RhCore.framework/Versions/A/Resources/RhinoCommon.xml` (FilePdf, FileWriteOptions, RhinoDoc.Export, ViewCaptureSettings); 온라인 페이지 https://developer.rhino3d.com/api/rhinocommon/rhino.fileio.filepdf/layersasoptionalcontentgroups 는 JS 렌더링으로 본문 추출 실패
- Rhino 8.35 플러그인 바이너리(로컬) — `export_AI.rhp`, `export_ACAD.rhp` (wide 문자열은 UTF-32LE; 추출 스크립트는 §1(a))
- Adobe Illustrator, Import AutoCAD files(최종 수정 2023-05-24) — https://helpx.adobe.com/illustrator/using/importing-eps-dcs-autocad-files.html (직접 접근 403, 리더 프록시로 본문 확인)
- Adobe Illustrator 도움말(PDF 가져오기·레이어·아트보드 한계·SVG) — https://helpx.adobe.com/illustrator/using/importing-pdf-files.html , …/layers.html , …/using-multiple-artboards.html , …/svg.html : 2026-10-07 직접·프록시·아카이브 모두 차단(403/422) → **확인 필요**
- Adobe Illustrator Scripting Reference(docsforadobe **커뮤니티 미러**) — https://ai-scripting.docsforadobe.dev/jsobjref/GroupItems/ , https://ai-scripting.docsforadobe.dev/jsobjref/Document/ , https://ai-scripting.docsforadobe.dev/jsobjref/IllustratorSaveOptions/ , https://ai-scripting.docsforadobe.dev/introduction/executingScripts/ , **https://ai-scripting.docsforadobe.dev/jsobjref/OpenOptionsAutoCAD/ , https://ai-scripting.docsforadobe.dev/jsobjref/Preferences/ , https://ai-scripting.docsforadobe.dev/jsobjref/PDFFileOptions/** (뒤 3개는 2026-10-07 2차 검증에서 추가)
- Illustrator 30.2.1 로컬 파일 — SVG 플러그인 문자열 `/Applications/Adobe Illustrator 2026/Adobe Illustrator.app/Contents/Required/Plug-ins/Illustrator Formats/svgFileFormat.aip` ; AppleScript 사전 `…/Contents/Resources/Adobe Illustrator.sdef`(`do javascript` 명령) ; Layers 패널 메뉴 `…/Contents/Required/Plug-ins/Extensions/Layers.aip/Contents/Resources/mnu/LayersPanel.mnu`, `…/str/11000.str`(`Release to Layers (Sequence)`/`(Build)`)
- Adobe Illustrator AppleScript Scripting Reference(`do javascript` 명령 문서) — URL **미확인, 확인 필요**
- Adobe Illustrator File Format Specification(Version 7, 1998; legacy PostScript AI 사양) — URL **미확인, 확인 필요**
- QGIS 3.44 Docs, Creating an Output — https://docs.qgis.org/3.44/en/docs/user_manual/print_layout/create_output.html
- QGIS 소스 — https://raw.githubusercontent.com/qgis/QGIS/master/src/core/layout/qgslayoutexporter.cpp , https://raw.githubusercontent.com/qgis/QGIS/master/src/core/qgsabstractgeopdfexporter.cpp
- GDAL PDF driver — https://gdal.org/en/stable/drivers/raster/pdf.html
- ezdxf — https://ezdxf.readthedocs.io/en/stable/ , https://ezdxf.readthedocs.io/en/stable/dxfinternals/fileencoding.html , https://ezdxf.readthedocs.io/en/stable/concepts/units.html ; PyPI https://pypi.org/pypi/ezdxf/1.3.5/json

포럼·커뮤니티(사용자/전문가 발언, 공식 아님)
- McNeel Discourse — 172613, 190010, 75082(2차 재확인), 76079, 29721, 87537, 193378, 132509, 170592(2차 재확인), 12921 ; **[미검증]** 153606, 98973, 134755, 204814 (URL은 본문 표 참조)
- Adobe Community — 817756, 14083757, 4733751, 14190269 ; **[미검증]** 769433, 797937, 1094113, 8495434 (URL은 본문 참조)
- Adobe UserVoice — https://illustrator.uservoice.com/forums/333657-illustrator-desktop-feature-requests/suggestions/35852185-keep-layers-from-pdf-when-opening-the-file-in-illu
- Inkscape bug 179680 **[미검증]** — https://bugs.launchpad.net/inkscape/+bug/179680
- North Road 블로그 — https://north-road.com/2019/09/03/qgis-3-10-loves-geospatialpdf/
- QGIS GitHub issues #17962, #34024 — https://github.com/qgis/QGIS/issues/17962 , https://github.com/qgis/QGIS/issues/34024
- UT Austin SOA wiki **[미검증]** — https://wikis.utexas.edu/display/SOAdigitech/Exporting+from+Rhino+to+.dwg,+.ai

로컬 기존 자산
- `/Users/sanghoon/Documents/GitHub/Seoungsu/scripts/make_basemap_L.py`(4행: 범위 ≈ 4.41×5.55 km), `figures/basemap_L/README.md`(2행 범위, 레이어 12개 표, "전체 선택 → Paste in Place" 워크플로), `figures/style_guide.md`(§6 66행: 공통 5그룹 bg/geo/data/labels/sources, "Illustrator에서 열면 위 5개 레이어로 분리" 서술)
- `/Users/sanghoon/Documents/GitHub/UrbanDesignTool/docs/research/04a_public_data_base_layers.md`, `04b_public_data_analysis_layers.md` — §3 신규 레이어(행정경계·교통결절)의 데이터 출처 확정은 이 문서들에서

---

## 검증 이력

**2026-10-07 2차 검증 반영** — WebSearch 세션 한도(200회) 소진으로 검색은 불가했고, 검증은 WebFetch로 1차 출처를 직접 열기 + 로컬 바이너리·파일 확인으로만 수행했다. 이 과정에서 다시 열지 못한 출처에는 **[미검증]** 태그를 붙였다(§1(a) 표 134755·8495434·204814·153606, §1(b) Inkscape 179680, §1(b′) 769433, §1(c) 797937·1094113, §1(e) 98973, UT Austin wiki).

| 구분 | 수정 내용 | 확인 방법 |
|---|---|---|
| refuted | §1(b)·§6: "Illustrator에서 열면 5개 레이어로 분리" 서술의 출처를 `basemap_L/README.md` → `figures/style_guide.md` §6(66행, bg/geo/data/labels/sources 5그룹)으로 정정. README는 12개 레이어 파일을 Paste in Place로 수동 중첩하는 워크플로를 전제한다고 기술 | 로컬 파일 cat/sed |
| refuted(산술) | §3: "성수 4도엽 프레임(4.41×5.55 km)은 A0 세로 1:5000 수납" 삭제. A0 1:5000 = 4.205×5.945 km, 프레임은 882×1110 mm 필요 → 어느 방향도 불가. 1:5500/1:6000, 커스텀 1000×1300 mm, 프레임 크롭 4선택지 표 추가 | ISO A0 치수 + README 2행·make_basemap_L.py 4행 |
| refuted(연결 오류) | §1(a) Mac/Windows 차이: RH-79156은 "Print Dialog: Open in Preview functionality missed"(Dan 2023-12-15) 티켓이고, 시스템 인쇄 대화상자 미복원 발언은 Dan 2023-12-04 — 분리해 정정 | WebFetch discourse 170592 |
| 과장 하향 | §0 (a): "레이어·색 보존은 공식 확인" → "Order layers 옵션만 공식, 보존은 `%AI5_BeginLayer`[로컬]·교육자료[미검증]로 간접 확인". §0 (b′): docsforadobe를 [미러]로 표기, "확실·완결" → "§5 테스트 1·4·7 통과 조건부" | WebFetch Mac 도움말, 로컬 바이너리 |
| 모순 수정 | §0 핵심 결론: "어느 중간 포맷도 레이어를 담을 수 없다" → DXF(layer)·legacy AI(`%AI5_BeginLayer`)는 담는다로 정정, (g) Python 직접 legacy AI 생성 옵션 신설(§1(g), §2 열 추가, §5 테스트 9) | 로컬 export_AI 문자열 |
| 판정 변경 | §0·§1(d)·§2: DXF 경로의 "Illustrator 측 수동·자동화 끊김" 철회. `app.preferences.AutoCADFileOptions`(`OpenOptionsAutoCAD`: centerArtwork true / globalScaleOption FitArtboard / globalScalePercent 100 / mergeLayers false / scaleLineweights false / selectedLayoutName / unit Millimeters / unitScaleRatio 1.0) + `app.open()`으로 무대화상자 자동화 가능. `mergeLayers` 기본 false로 레이어 보존 보강. (d)를 2순위 "대안·동급 후보"로 상향, (a)는 3순위로 | WebFetch docsforadobe OpenOptionsAutoCAD·Preferences |
| 보강 | §1(c)·(e): `PDFFileOptions`에는 pageToOpen·pDFCropToBox뿐 레이어/OCG 옵션 없음 → "Illustrator는 OCG를 레이어로 열지 않는다"를 API 부재로 보강 | WebFetch docsforadobe PDFFileOptions |
| 보강 | §1(a) 표·평가, §1(e), §0: Pascal Golay(2018-11-21, 75082) "printing to pdf seems to get it right as far as the hatches in AI go" 추가 → 해치 도면은 PDF 경로 | WebFetch discourse 75082 |
| 보강 | §1(a): Mac 도움말의 "Always use these settings. Do not show this dialog again." 옵션과 바이너리 설정 키 `AI_Rhino DontShowDialog` 대응 추가(무인 export용); §5 테스트 5에 반영 | WebFetch Mac 도움말, 로컬 바이너리 |
| 재현성 | §1(a): macOS 기본 `strings`에 `-e` 없음(로컬 `unknown flag: -e`) → wide 문자열은 UTF-32LE이며 Python 정규식 `(?:[\x20-\x7e]\x00\x00\x00){4,}` + `utf-32le` 디코드로 추출하는 방법 명시 | 로컬 실행 |
| 누락 보완 | §1(b′)·§4: 무인 실행 트리거 — 로컬 `Adobe Illustrator.sdef`에 `do javascript` 명령(code miscDjxM, direct-parameter "javascript code or file to execute", `with arguments`) 존재 확인 → osascript를 1순위, `open -a`는 2순위로. AppleScript Reference 원문 URL은 확인 필요. ExtendScript→UXP 전환 리스크 항목 추가(확인 필요) | 로컬 sdef grep |
| 누락 보완 | §1(b)·§0·§5: Layers 패널 메뉴 `Release to Layers (Sequence)`/`(Build)` 존재를 Layers.aip 메뉴·문자열 파일에서 확인 → 스크립트 없는 수동 레이어화 대안 추가(동작 상세는 확인 필요, 테스트 8) | 로컬 Layers.aip grep |
| 누락 보완 | §3: 행정경계·행정동명(11b), 토지이용현황(02b), 교통결절(06b), 공공시설·랜드마크(11c), 지번 라벨(08b), 표고점·음영기복(09b) 레이어 추가; 11_zoning에 고시번호 부기 내장 규칙 추가. 데이터 출처는 04a/04b 문서로 위임(확인 필요) | Seoungsu README 레이어 표 |
| 수치 보완 | §1(b)·§5: `04_roads.svg` `<path>` 10,106개 추가(05_buildings 41,537개·6,772,970 B, 04_roads 1,461,592 B 재확인). 테스트 4의 "10 s"는 근거 없는 편의상 임계값임을 명기 | 로컬 grep -c / ls -l |

미해결(확인 필요): Adobe helpx 원문(PDF 가져오기·레이어·Release to Layers 동작), Illustrator AppleScript Reference의 `do javascript` 원문 URL, Adobe Illustrator File Format Specification v7 URL, ExtendScript 지속 지원 일정, `AutoCADUnit`/`AutoCADGlobalScaleOption` enum 철자와 DXF `Open` 시 아트보드 결정 방식, `createFromFile`의 텍스트 라이브 유지·배치 기준점, [미검증] 태그 출처 9건의 재열람.
