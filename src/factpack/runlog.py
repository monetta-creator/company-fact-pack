"""Per-script status files in build/status/ — the failure-isolation substrate.

run_isolated() lets a run_all driver continue past one source's failure; the status
table at the end shows what succeeded, what failed, and why.
"""

from __future__ import annotations

import datetime as dt
import json
import traceback
from typing import Callable

from . import config


class RunLog:
    def __init__(self, name: str):
        self.name = name
        self.data: dict = {"name": name, "status": "running", "counts": {}, "notes": []}
        self.data["started_at"] = _now()
        self._flush()

    def note(self, msg: str) -> None:
        self.data["notes"].append(f"{_now()} {msg}")
        self._flush()

    def count(self, key: str, n: int = 1) -> None:
        self.data["counts"][key] = self.data["counts"].get(key, 0) + n

    def ok(self, **counts) -> None:
        self.data["counts"].update(counts)
        self.data["status"] = "ok"
        self.data["finished_at"] = _now()
        self._flush()

    def fail(self, err: BaseException | str) -> None:
        self.data["status"] = "failed"
        self.data["error"] = str(err)[:2000]
        self.data["finished_at"] = _now()
        self._flush()

    def _flush(self) -> None:
        config.STATUS.mkdir(parents=True, exist_ok=True)
        (config.STATUS / f"{self.name}.json").write_text(json.dumps(self.data, indent=1))


def _now() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_isolated(name: str, fn: Callable[[RunLog], None]) -> bool:
    """Run one pipeline stage; never raises. Returns True on success."""
    log = RunLog(name)
    try:
        fn(log)
        if log.data["status"] == "running":
            log.ok()
        return log.data["status"] == "ok"
    except Exception as e:  # noqa: BLE001 — isolation is the point
        traceback.print_exc()
        log.fail(e)
        return False


def print_status_table() -> None:
    rows = []
    for path in sorted(config.STATUS.glob("*.json")):
        d = json.loads(path.read_text())
        if not isinstance(d, dict) or "name" not in d:
            continue  # quarantine lists etc. share the status dir
        rows.append((d["name"], d["status"], d.get("counts", {}), d.get("error", "")[:80]))
    width = max((len(r[0]) for r in rows), default=10)
    for name, status, counts, err in rows:
        mark = {"ok": "✓", "failed": "✗", "running": "…"}.get(status, "?")
        print(f"{mark} {name:<{width}}  {counts if counts else ''} {err}")
