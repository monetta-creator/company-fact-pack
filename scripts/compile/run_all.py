"""`make compile` — warm -> chunk -> enrich -> index -> metrics_load -> verify_build."""

from __future__ import annotations

import subprocess
import sys

from factpack.runlog import print_status_table

STAGES = [
    "scripts.compile.warm_models",
    "scripts.compile.chunk",
    "scripts.compile.enrich",
    "scripts.compile.index",
    "scripts.compile.metrics_load",
    "scripts.compile.export_briefs",
    "scripts.compile.verify_build",
]


def main() -> int:
    for stage in STAGES:
        print(f"\n== {stage} ==", flush=True)
        rc = subprocess.run([sys.executable, "-m", stage], check=False).returncode
        if rc and stage.endswith(("chunk", "index")):
            print(f"FATAL: {stage} failed; aborting compile")
            return rc
    print("\n== compile status ==")
    print_status_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
