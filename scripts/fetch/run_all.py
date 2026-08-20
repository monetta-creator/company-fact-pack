"""`make fetch` — run every fetcher; continue past per-source failure; print status table.

EDGAR fetchers run sequentially first (they share one rate bucket); the rest follow.
"""

from __future__ import annotations

import subprocess
import sys

from factpack.runlog import print_status_table

STAGES = [
    ["scripts.fetch.edgar_filings", "--entity", "cof",
     "--forms", "10-K,10-Q,8-K,DEF14A,S-4,425,DEFM14A", "--since", "2016-01-01"],
    ["scripts.fetch.edgar_filings", "--entity", "dfs",
     "--forms", "10-K,10-Q,8-K,DEF14A,DEFM14A,425", "--since", "2016-01-01", "--until", "2025-06-30"],
    ["scripts.fetch.edgar_filings", "--entity", "comet", "--forms", "10-D,10-K,8-K", "--since", "2016-01-01"],
    ["scripts.fetch.edgar_filings", "--entity", "dcent", "--forms", "10-D,10-K,8-K", "--since", "2016-01-01"],
    ["scripts.fetch.edgar_xbrl"],
    ["scripts.fetch.fdic"],
    ["scripts.fetch.ffiec_y9c"],
    ["scripts.fetch.ffiec_call"],
    ["scripts.fetch.cfpb_agreements"],
    ["scripts.fetch.cfpb_complaints"],
    ["scripts.fetch.fed_stress"],
    ["scripts.fetch.enforcement"],
    ["scripts.fetch.courtlistener"],
    ["scripts.fetch.ir_press"],
    ["scripts.fetch.transcripts_stub"],
]


def main() -> int:
    for stage in STAGES:
        print(f"\n== {' '.join(stage)} ==", flush=True)
        subprocess.run([sys.executable, "-m", *stage], check=False)
    print("\n== fetch status ==")
    print_status_table()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
