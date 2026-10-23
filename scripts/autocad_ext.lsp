;;; Gorani AutoCAD판 본문 — 번들에서는 Gorani.bundle/Contents/gorani.lsp(dev_deploy.py autocad가 복사한다).
;;;
;;; AutoCAD 안 명령은 GORANI 하나 — 패널을 기본 브라우저로 연다(Windows startapp, Mac SHELL).
;;; AutoCAD에는 파이썬·SQLite가 없어 계산은 파이썬 사이드카(scripts/cmd_autocad.py)가 하고, 결과는 파일이다:
;;;   ~/Gorani/result/<대상지>_<날짜>/2d/cad_<축척>.dxf (2D 현황도) + 현황도 SVG·조서 CSV
;;; 도면은 건드리지 않는다. 패널의 [DXF 열기] 또는 AutoCAD 열기(OPEN)로 연다. 사용법은 docs/autocad.md.
;;; ActiveX(vla-)를 쓰지 않는다 — Mac·LT에도 같은 파일. 문자열은 UTF-8(AutoCAD 2021+ LISPSYS 1).

(defun gorani:windows-p ()
  (wcmatch (strcase (getvar "PLATFORM")) "*WINDOWS*"))

(defun gorani:first-file (paths / found)
  ;; 목록에서 처음 있는 파일 경로
  (while (and paths (not found))
    (setq found (findfile (car paths)) paths (cdr paths)))
  found)

(defun gorani:root (/ lsp found)
  ;; 번들 Contents 폴더(끝에 구분자). 지원 경로(PackageContents SupportPath)에 있으면 그 자리, 아니면 설치될 수 있는 자리 중 gorani.lsp가 있는 곳.
  ;; 오토로더가 지원 경로를 안 붙이면 findfile이 못 찾는다(2026-10-23 accoreconsole 실측) — 스토어 설치본은 Program Files에 깔린다
  (if (setq lsp (findfile "gorani.lsp"))
    (substr lsp 1 (- (strlen lsp) (strlen "gorani.lsp")))
    (progn
      (foreach dir
        (if (gorani:windows-p)
          (list (strcat (getenv "ProgramFiles") "\\Autodesk\\ApplicationPlugins\\Gorani.bundle\\Contents\\")
                (strcat (getenv "ProgramData") "\\Autodesk\\ApplicationPlugins\\Gorani.bundle\\Contents\\")
                (strcat (getenv "APPDATA") "\\Autodesk\\ApplicationPlugins\\Gorani.bundle\\Contents\\"))
          (list (strcat (getenv "HOME") "/Library/Application Support/Autodesk/ApplicationAddins/Gorani.bundle/Contents/")
                "/Library/Application Support/Autodesk/ApplicationAddins/Gorani.bundle/Contents/"))
        (if (and (not found) (findfile (strcat dir "gorani.lsp"))) (setq found dir)))
      (if found found ""))))   ; 못 찾으면 "" — c:GORANI가 '프로그램 파일이 없습니다'를 낸다

(defun gorani:python (root)
  ;; 번들 파이썬(python/<플랫폼>) → 없으면 PC의 파이썬(개발용)
  (cond
    ((gorani:windows-p)
     (cond ((gorani:first-file (list (strcat root "python\\win-x64\\pythonw.exe")))) ("pythonw.exe")))
    ((gorani:first-file
       (list (strcat root "python/mac-arm64/bin/python3.12") (strcat root "python/mac-x64/bin/python3.12") "/usr/bin/python3")))))

(defun gorani:launch (python script / args)
  ;; 사이드카를 띄우고 기다리지 않는다. Windows = startapp.
  ;; Mac AutoCAD 2027은 startapp으로 띄우지 못했다(2026-10-18 실측 — '띄우지 못했습니다') → acad.pgp의 SHELL(OS 명령, 플래그 1 = 기다리지 않음)
  (setq args (strcat "-I -B -X utf8 \"" script "\""))
  (if (gorani:windows-p)
    (and startapp (startapp python args))
    (progn (command "SHELL" (strcat "\"" python "\" " args " >/dev/null 2>&1 &")) T)))

(defun gorani:home ()
  ;; 사이드카의 쓰기 자리(constants.HOME_DIR = 사용자 홈/Gorani)
  (if (gorani:windows-p) (strcat (getenv "USERPROFILE") "\\Gorani\\") (strcat (getenv "HOME") "/Gorani/")))

(defun gorani:insert-pending (/ file handle path block)
  ;; 사이드카가 남긴 '넣을 DXF'(autocad_insert.txt — 1줄 경로, 2줄 블록 이름)를 지금 도면 0,0에 블록으로 넣고 그 블록으로 줌. 없으면 nil.
  ;; Windows는 생성이 끝나면 사이드카가 COM으로 이 함수를 부르고, 맥·LT는 GORANI를 다시 치면 c:GORANI가 부른다
  (setq file (strcat (gorani:home) "autocad_insert.txt"))
  (if (findfile file)
    (progn
      (setq handle (open file "r" "utf8") path (read-line handle) block (read-line handle))
      (close handle)
      (vl-file-delete file)
      (if (and path block (findfile path))
        (progn
          (command "_.-INSERT" (strcat block "=" path) "0,0" "1" "1" "0")
          (command "_.ZOOM" "_O" (entlast) "")
          (princ (strcat "\nGorani: 지금 도면에 블록 " block "으로 넣었습니다. 분해(EXPLODE)하면 레이어별 선이 됩니다."))
          T)
        (progn (princ (strcat "\nGorani: 넣을 DXF가 없습니다 — " (if path path ""))) nil)))))

(defun c:GORANI (/ root python script)
  (setq root (gorani:root)
        script (strcat root (if (gorani:windows-p) "scripts\\cmd_autocad.py" "scripts/cmd_autocad.py"))
        python (gorani:python root))
  (cond
    ((gorani:insert-pending))   ; 넣을 결과가 있으면 넣기만 한다(맥·LT — 패널은 브라우저에 그대로 떠 있다)
    ((not (findfile script))
     (princ (strcat "\nGorani: 프로그램 파일이 없습니다 — " script "\n번들을 다시 설치하세요.")))
    ((not python)
     (princ "\nGorani: 파이썬을 찾지 못했습니다 — 번들을 다시 설치하세요."))
    ((gorani:launch python script)
     (princ "\nGorani: 패널을 브라우저로 엽니다 (처음에는 몇 초 걸립니다)."))
    (T
     (princ (strcat "\nGorani: 이 AutoCAD에서는 프로그램을 띄우지 못했습니다. 터미널에서 다음을 실행하세요:\n  \""
                    python "\" \"" script "\""))))
  (princ))

(princ "\nGorani 불러옴 — 명령: GORANI")
(princ)
