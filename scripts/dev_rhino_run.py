"""Rhino 실행 래퍼 — 드라이버 .py를 떠 있는 Mac Rhino 8에 던지고 결과를 가져온다 (Rhino 밖 전용).

Mac 전용. 여러 세션이 동시에 던지면
뒤 작업이 조용히 밀리므로, 던진 뒤 done.json이 생길 때까지 기다렸다가 결과를 가져온다.

    python3 scripts/dev_rhino_run.py /tmp/my_driver.py     # 던지고 기다렸다가 result/rhino_jobs/<작업 id>/ 에 가져온다
    python3 scripts/dev_rhino_run.py --status              # Rhino가 떠 있는지(rhinocode 파이프)만 본다

드라이버 규약:
    - 결과 파일은 전역 ``OUT_DIR``에 쓴다. 끝나면 그 폴더째 가져온다.
    - 작업 폴더의 scripts/가 sys.path 맨 앞에 있고 프로젝트 모듈은 이름으로 걷어낸 상태다. 그냥 import한다.
    - print는 out/log.txt에 남는다. 예외도 traceback째 남고 done.json의 ok가 false가 된다.

작업 폴더에는 실행 시점의 scripts/를 복사하고 data/의 DB는 심볼릭 링크한다. 그래서 던진 뒤 코드를
고쳐도 도는 작업에는 영향이 없다. ponytail: Windows 노트북 경로는 빼 두었다 — 필요해지면 원본에서 가져온다.
"""
import argparse
import datetime
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import constants  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT_DIR / "scripts"
JOBS_DIR = Path("/tmp/udt_rhino_jobs")
RHINOCODE = "/Applications/Rhino 8.app/Contents/Resources/bin/rhinocode"
RESULT_DIRNAME = "result/rhino_jobs"
POLL_SEC = 3
TIMEOUT_SEC = 3600
KEEP_DAYS = 3

# Rhino 안에서 도는 머리말. 드라이버를 감싸 sys.path·모듈 정리, 로그, 완료 표시(done.json)를 맡는다.
RUNNER_TEMPLATE = r'''# dev_rhino_run 머리말 — 드라이버를 감싸 로그와 완료 표시를 남긴다
import importlib, json, os, platform, sys, time, traceback
JOB_DIR = r"__JOB_DIR__"
SCRIPTS_DIR = os.path.join(JOB_DIR, "scripts")
OUT_DIR = os.path.join(JOB_DIR, "out")
os.makedirs(OUT_DIR, exist_ok=True)
for name in [f[:-3] for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py")]:
    sys.modules.pop(name, None)
if SCRIPTS_DIR in sys.path:
    sys.path.remove(SCRIPTS_DIR)
sys.path.insert(0, SCRIPTS_DIR)
importlib.invalidate_caches()
started = time.time()
error = None
stdout = sys.stdout
log = open(os.path.join(OUT_DIR, "log.txt"), "w", encoding="utf-8")
sys.stdout = log
try:
    with open(os.path.join(JOB_DIR, "driver.py"), encoding="utf-8") as f:
        code = compile(f.read(), "driver.py", "exec")
    exec(code, {"__name__": "__main__", "JOB_DIR": JOB_DIR, "OUT_DIR": OUT_DIR, "SCRIPTS_DIR": SCRIPTS_DIR})
except BaseException:
    error = traceback.format_exc()
    log.write(error)
finally:
    sys.stdout = stdout
    log.close()
    done = {"ok": error is None, "error": error, "seconds": round(time.time() - started, 1), "machine": platform.node()}
    with open(os.path.join(JOB_DIR, "done.json.tmp"), "w", encoding="utf-8") as f:
        json.dump(done, f, ensure_ascii=False)
    os.replace(os.path.join(JOB_DIR, "done.json.tmp"), os.path.join(JOB_DIR, "done.json"))
'''


def main():
    parser = argparse.ArgumentParser(description="드라이버를 Mac Rhino에 던지고 결과를 가져온다")
    parser.add_argument("driver", nargs="?", help="Rhino에서 돌릴 드라이버 .py")
    parser.add_argument("--status", action="store_true", help="Rhino 상태만 보여 준다")
    args = parser.parse_args()

    pipe = get_pipe()
    if args.status:
        print(json.dumps({"pipe": pipe, "queue": count_queue()}, ensure_ascii=False))
        return 0
    if not args.driver:
        parser.error("드라이버 경로가 필요합니다")
    if not pipe:
        print("Mac Rhino가 rhinocode에 잡히지 않습니다 — Rhino 8을 띄우고 ScriptEditor를 한 번 여세요")
        return 2

    job_id = datetime.datetime.now().strftime("%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    job_dir = launch(job_id, Path(args.driver), pipe)
    print("[rhino_run] 작업 %s 던짐 — 끝나기를 기다립니다" % job_id, flush=True)
    done = wait_done(job_dir)
    if done is None:
        print("[rhino_run] %d초 안에 끝나지 않았습니다. 작업 폴더: %s" % (TIMEOUT_SEC, job_dir))
        return 2
    local_dir = ROOT_DIR / RESULT_DIRNAME / job_id
    local_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(job_dir / "out", local_dir / "out", dirs_exist_ok=True)
    shutil.copy2(job_dir / "done.json", local_dir / "done.json")
    print("[rhino_run] %s %.1fs — %s" % ("완료" if done["ok"] else "실패", done["seconds"], local_dir))
    if not done["ok"]:
        print(done["error"])
    return 0 if done["ok"] else 1


def get_pipe():
    # type: () -> str
    """``rhinocode list`` 출력에서 첫 Rhino의 파이프 ID. 없으면 빈 문자열."""
    try:
        text = subprocess.run([RHINOCODE, "list"], capture_output=True, text=True, check=True).stdout
    except (subprocess.CalledProcessError, FileNotFoundError):
        return ""
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0].isdigit():
            return parts[1]
    return ""


def launch(job_id, driver_path, pipe):
    # type: (str, Path, str) -> Path
    """작업 폴더를 만들고(scripts 복사·DB 링크) Rhino에 던진다."""
    prune()
    job_dir = JOBS_DIR / job_id
    shutil.copytree(SCRIPTS_DIR, job_dir / "scripts", ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    (job_dir / "data").mkdir()
    for database_path in sorted((ROOT_DIR / "data").glob("*.db")):   # 필지 DB·컨텍스트 DB 전부 (심링크면 원본)
        (job_dir / "data" / database_path.name).symlink_to(database_path.resolve())
    fixtures_dir = ROOT_DIR / "tests" / "fixtures"
    if fixtures_dir.exists():
        shutil.copytree(fixtures_dir, job_dir / "tests" / "fixtures")
    env_path = ROOT_DIR / ".env"
    if env_path.exists():
        shutil.copy2(env_path, job_dir / ".env")
    shutil.copy2(driver_path, job_dir / "driver.py")
    (job_dir / "run.py").write_text(RUNNER_TEMPLATE.replace("__JOB_DIR__", str(job_dir)), encoding="utf-8")
    subprocess.run([RHINOCODE, "-r", pipe, "script", str(job_dir / "run.py")], capture_output=True, text=True, check=True)
    return job_dir


def wait_done(job_dir):
    # type: (Path) -> dict
    """done.json이 생길 때까지 기다린다. 상한을 넘기면 None."""
    deadline = time.time() + TIMEOUT_SEC
    while time.time() < deadline:
        done_path = job_dir / "done.json"
        if done_path.exists():
            return json.loads(done_path.read_text(encoding="utf-8"))
        time.sleep(POLL_SEC)
    return None


def count_queue():
    # type: () -> int
    """던졌는데 아직 done.json이 없는 작업 수. 상한보다 오래된 것은 죽은 것으로 본다."""
    if not JOBS_DIR.exists():
        return 0
    limit = time.time() - TIMEOUT_SEC
    return sum(1 for d in JOBS_DIR.iterdir()
               if d.is_dir() and not (d / "done.json").exists() and d.stat().st_mtime > limit)


def prune():
    # type: () -> None
    """보관 일수가 지난 작업 폴더를 지운다. DB는 심링크라 원본은 남는다."""
    if not JOBS_DIR.exists():
        return
    limit = time.time() - KEEP_DAYS * 86400
    for d in JOBS_DIR.iterdir():
        if d.is_dir() and d.stat().st_mtime < limit:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
