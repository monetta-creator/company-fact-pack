"""One-button corpus update: fetch -> extract -> validate -> compile, fail-safe.

Fail-safe mechanics:
- a lock file prevents overlapping runs;
- VALIDATE runs before compile — bad data aborts the run and the serving database
  is untouched;
- the database + vectors are backed up before compile and auto-restored if
  verify_build fails, so a broken rebuild can never replace a working one;
- every stage writes runlog status; the UI polls /api/update/status.

Run detached: `python -m factpack.update` (the server's Start button does this).
"""

from __future__ import annotations

import datetime as dt
import json
import os
import shutil
import subprocess
import sys

from . import config

LOCK = config.BUILD / "update.lock"
STATUS_FILE = config.BUILD / "update_status.json"
LOG_FILE = config.BUILD / "update_run.log"

STAGES = [
    ("fetch", ["scripts.fetch.run_all"]),
    ("extract", ["scripts.extract.run_all"]),
    ("validate", ["scripts.validate.run_all"]),
    ("compile", ["scripts.compile.run_all"]),
]


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_status(**kw) -> None:
    config.BUILD.mkdir(exist_ok=True)
    cur = read_status()
    cur.update(kw)
    STATUS_FILE.write_text(json.dumps(cur, indent=1))


def read_status() -> dict:
    try:
        return json.loads(STATUS_FILE.read_text())
    except Exception:  # noqa: BLE001
        return {}


def is_running() -> bool:
    if not LOCK.exists():
        return False
    try:
        pid = int(LOCK.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, ProcessLookupError, PermissionError):
        LOCK.unlink(missing_ok=True)  # stale lock from a dead run
        return False


def start_detached() -> str | None:
    """Launch the update as its own process. Returns an error string or None."""
    if is_running():
        return "an update is already running"
    log = open(LOG_FILE, "w")
    subprocess.Popen(
        [sys.executable, "-m", "factpack.update"],
        stdout=log, stderr=subprocess.STDOUT,
        cwd=config.ROOT, start_new_session=True,
    )
    return None


def run() -> int:
    if is_running():
        print("update already running; exiting")
        return 1
    config.BUILD.mkdir(exist_ok=True)
    LOCK.write_text(str(os.getpid()))
    _write_status(state="running", stage="starting", started_at=_now(),
                  finished_at=None, error=None, stages={})
    backup_db = config.DB_PATH.with_suffix(".db.bak")
    backup_vec = config.VECTORS_NPZ.with_suffix(".npz.bak")
    try:
        stages_result: dict[str, str] = {}
        for name, modules in STAGES:
            _write_status(stage=name)
            print(f"=== STAGE {name} ===", flush=True)
            if name == "compile" and config.DB_PATH.exists():
                shutil.copy2(config.DB_PATH, backup_db)
                if config.VECTORS_NPZ.exists():
                    shutil.copy2(config.VECTORS_NPZ, backup_vec)
            rc = 0
            for mod in modules:
                rc |= subprocess.run(
                    [sys.executable, "-m", mod], cwd=config.ROOT, check=False
                ).returncode
            stages_result[name] = "ok" if rc == 0 else "failed"
            _write_status(stages=stages_result)
            if name == "validate" and rc != 0:
                _write_status(state="failed", error="validation failed — compile skipped, "
                              "serving database untouched", finished_at=_now())
                return 1
            if name == "compile":
                verify = json.loads(
                    (config.STATUS / "compile.verify_build.json").read_text()
                )
                if verify.get("status") != "ok":
                    if backup_db.exists():
                        shutil.copy2(backup_db, config.DB_PATH)
                    if backup_vec.exists():
                        shutil.copy2(backup_vec, config.VECTORS_NPZ)
                    _write_status(state="failed", error="rebuild failed verification — "
                                  "previous database restored", finished_at=_now())
                    return 1
        _write_status(state="ok", stage="done", finished_at=_now())
        print("=== UPDATE COMPLETE ===", flush=True)
        return 0
    except Exception as e:  # noqa: BLE001
        _write_status(state="failed", error=str(e)[:500], finished_at=_now())
        return 1
    finally:
        LOCK.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(run())
