"""Self-resuming build driver: pushes all remaining model-dependent work to completion,
sleeping through usage-cap windows and retrying. Designed to run detached for hours.

Phases:
1. events + enrichment until both fully caught up (cap-resilient, cache-backed)
2. final compile rebuild (index/metrics/verify) with complete preambles, on main
3. draft-branch content (rule 3): entity spine, products, eval bank, all 12 briefs
   on draft/model-content — committed there, never on main
4. golden retrieval eval baseline

Emits progress markers on stdout for the monitor: PHASE_*, WAITING_FOR_CAP, DRIVE_DONE.
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

from factpack import config
from scripts.briefs.topics import TOPICS

SLEEP_S = 1800
MAX_CYCLES = 24  # hard backstop: ~12h of cap-waiting


def counts(name: str) -> dict:
    try:
        d = json.loads((config.STATUS / f"{name}.json").read_text())
        return d.get("counts", {}) if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def run(module: str, *args: str) -> int:
    print(f"RUN {module} {' '.join(args)}", flush=True)
    return subprocess.run([sys.executable, "-m", module, *args], check=False).returncode


def git(*args: str) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True, cwd=config.ROOT)
    return r.stdout.strip()


def main() -> int:
    # Phase 1: events (model-dependent, cap-cycled) + local labeling (free, one pass)
    print("PHASE_1_ENRICH", flush=True)
    for cycle in range(MAX_CYCLES):
        run("scripts.extract.events_8k")
        ev_pending = counts("extract.events_8k").get("pending", 0)
        print(f"CYCLE {cycle}: events_pending={ev_pending}", flush=True)
        if ev_pending == 0:
            break
        print("WAITING_FOR_CAP", flush=True)
        time.sleep(SLEEP_S)
    else:
        print("MAX_CYCLES_REACHED (continuing with what we have)", flush=True)
    run("scripts.compile.enrich")  # aboutness ladder: local, zero model calls

    # Phase 2: final rebuild on main with full preambles
    print("PHASE_2_REBUILD", flush=True)
    if git("branch", "--show-current") != "main":
        git("checkout", "main")
    for stage in ("scripts.compile.index", "scripts.compile.metrics_load",
                  "scripts.compile.verify_build"):
        run(stage)

    # Phase 3: draft-branch content (rule 3 — never on main)
    print("PHASE_3_DRAFTS", flush=True)
    git("checkout", "-B", "draft/model-content", "main")
    try:
        for cycle in range(MAX_CYCLES):
            progressed = False
            if not list((config.ROOT / "entities").glob("person-*.yaml")):
                run("scripts.extract.entity_spine")
                progressed = True
            if not list((config.ROOT / "products").glob("*.yaml")):
                run("scripts.extract.products_agreements")
                progressed = True
            if not (config.ROOT / "evals/associate_bank.yaml").exists():
                run("scripts.briefs.draft_eval_bank")
                progressed = True
            missing = [b for b in sorted(TOPICS) if not (config.ROOT / "briefs" / f"{b}.md").exists()]
            for b in missing:
                run("scripts.briefs.draft_brief", b)
            missing_after = [
                b for b in sorted(TOPICS) if not (config.ROOT / "briefs" / f"{b}.md").exists()
            ]
            done = (
                not missing_after
                and (config.ROOT / "evals/associate_bank.yaml").exists()
                and list((config.ROOT / "products").glob("*.yaml"))
            )
            print(f"DRAFT_CYCLE {cycle}: briefs_missing={len(missing_after)}", flush=True)
            if done:
                break
            if not progressed and missing == missing_after:
                print("WAITING_FOR_CAP", flush=True)
                time.sleep(SLEEP_S)
        git("add", "entities", "products", "briefs", "evals/associate_bank.yaml")
        subprocess.run(
            ["git", "commit", "-q", "-m",
             "Draft (rule 3, human gate): entity spine, products, eval bank, 12 briefs\n\n"
             "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"],
            cwd=config.ROOT, check=False,
        )
    finally:
        git("checkout", "main")

    # Phase 4: golden retrieval baseline (deterministic, no model)
    print("PHASE_4_EVAL", flush=True)
    subprocess.run([sys.executable, "evals/run_retrieval.py"], check=False, cwd=config.ROOT)

    print("DRIVE_DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
