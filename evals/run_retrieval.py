"""Golden retrieval eval (D11): query -> expected evidence, scored recall@k + MRR.

Expectations are doc-id prefixes and/or must_contain spans (chunk_ids are
content-addressed and shift across rebuilds, so they are never the target).
Appends one row per run to evals/history.csv; details to build/eval_retrieval.json.
"""

from __future__ import annotations

import csv
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factpack import config
from factpack.retrieve import retrieve_chunks


def hit(chunks: list[dict], g: dict) -> int | None:
    """rank (0-based) of the first chunk satisfying the expectation, else None"""
    for i, c in enumerate(chunks):
        ok = True
        if g.get("expect_doc_prefix"):
            ok = c["doc_id"].startswith(g["expect_doc_prefix"])
        if ok and g.get("must_contain"):
            ok = g["must_contain"].lower() in (c["preamble"] + c["text"]).lower()
        if ok:
            return i
    return None


def main() -> int:
    golden = yaml.safe_load((config.ROOT / "evals/golden/retrieval.yaml").read_text())
    results = []
    r10 = r25 = 0
    mrr = 0.0
    for g in golden:
        chunks = retrieve_chunks(g["query"], g.get("filters", {}), top_n=25)
        rank = hit(chunks, g)
        results.append({"query": g["query"], "rank": rank})
        if rank is not None:
            mrr += 1.0 / (rank + 1)
            r25 += 1
            if rank < 10:
                r10 += 1
    n = len(golden)
    summary = {
        "date": dt.date.today().isoformat(),
        "n": n,
        "recall_at_10": round(r10 / n, 3),
        "recall_at_25": round(r25 / n, 3),
        "mrr": round(mrr / n, 3),
    }
    config.BUILD.mkdir(exist_ok=True)
    (config.BUILD / "eval_retrieval.json").write_text(
        json.dumps({"summary": summary, "results": results}, indent=1)
    )
    hist = config.ROOT / "evals/history.csv"
    new = not hist.exists()
    with hist.open("a") as f:
        w = csv.DictWriter(f, fieldnames=list(summary))
        if new:
            w.writeheader()
        w.writerow(summary)
    print(json.dumps(summary))
    misses = [r["query"] for r in results if r["rank"] is None]
    if misses:
        print("misses:", *misses, sep="\n  ")
    return 0 if summary["recall_at_10"] >= 0.5 else 1


if __name__ == "__main__":
    raise SystemExit(main())
