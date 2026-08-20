"""`make extract` — deterministic extractors. Model-assisted draft-branch scripts
(entity_spine, products_agreements) are run separately and refuse to run on main.

DFAST numbers stay narrative-only this iteration (results tables are chunked prose;
no stress metrics in the governed store) — recorded here so the gap is visible.
"""

from __future__ import annotations

import subprocess
import sys

from factpack.runlog import print_status_table

STAGES = [
    "scripts.extract.entity_seeds",
    "scripts.extract.xbrl_observations",
    "scripts.extract.fdic_observations",
    "scripts.extract.complaints_rollup",
    "scripts.extract.trust_observations",
    "scripts.extract.y9c_observations",
    "scripts.extract.events_8k",
]


def main() -> int:
    for stage in STAGES:
        print(f"\n== {stage} ==", flush=True)
        subprocess.run([sys.executable, "-m", stage], check=False)
    print("\n== extract status ==")
    print_status_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
