"""Form 10-D servicer reports -> monthly trust performance observations.

Patterns tuned against the live COMET format (verified 2026-08); DCENT historical
formats get alternative labels. 30+ delinquency is computed from the report's bucket
dollars over end-of-month principal receivables. Documents where fewer than 2 metrics
resolve are quarantined to build/status/trust_parse_failures.json, never fatal.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated

PCT_RE = re.compile(r"(-?\d{1,3}(?:\.\d{1,4})?)\s*%")
USD_RE = re.compile(r"\$?\s*(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?)")

# metric -> ordered label alternatives (first matching line wins), value kind
LABELS: dict[str, tuple[list[re.Pattern], str]] = {
    "trust-principal-receivables": ([
        re.compile(r"end of (the )?month principal receivables", re.I),
        re.compile(r"total principal receivables", re.I),
    ], "usd"),
    "trust-payment-rate": ([
        re.compile(r"principal payment rate", re.I),
        re.compile(r"monthly payment rate", re.I),
    ], "pct"),
    "trust-yield": ([
        re.compile(r"annualized yield", re.I),
        re.compile(r"portfolio yield", re.I),
    ], "pct"),
    "trust-charge-off-rate": ([
        re.compile(r"annualized net default rate", re.I),
        re.compile(r"net charge.?off rate|net loss rate|net principal charge.?offs? rate", re.I),
    ], "pct"),
    "trust-excess-spread": ([
        re.compile(r"excess spread", re.I),
    ], "pct"),
}
DELINQ_BUCKET_RE = re.compile(
    r"(?:30|60|90|120|150)\s*(?:-\s*\d+)?\s*\+?\s*days? delinquent", re.I
)


def parse_doc(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    delinq_total = 0.0
    for line in text.splitlines():
        for metric, (patterns, kind) in LABELS.items():
            if metric in found:
                continue
            rank = next((i for i, rx in enumerate(patterns) if rx.search(line)), None)
            if rank is None:
                continue
            m = PCT_RE.search(line) if kind == "pct" else USD_RE.search(line)
            if m:
                # % lines can also carry $ figures; PCT_RE targets the percent only
                found[metric] = float(m.group(1).replace(",", ""))
        if DELINQ_BUCKET_RE.search(line):
            amounts = USD_RE.findall(line)
            if amounts:
                delinq_total += float(amounts[-1].replace(",", ""))
    if delinq_total and found.get("trust-principal-receivables"):
        found["trust-delinq-30plus"] = round(
            100.0 * delinq_total / found["trust-principal-receivables"], 4
        )
    return found


def main() -> None:
    def run(log: RunLog) -> None:
        today = dt.date.today().isoformat()
        rows: list[dict] = []
        failures: list[dict] = []
        for entity in ("comet", "dcent"):
            for doc_id, m in mlib.iter_manifests():
                if m["source"] != f"edgar-{entity}" or not m["doc_type"].startswith("10-D"):
                    continue
                period_end = m.get("period_end") or m.get("filed_date")
                text_path = mlib.doc_dir(doc_id) / "extracted.txt"
                if not period_end or not text_path.exists():
                    continue
                found = parse_doc(text_path.read_text(errors="replace"))
                if len(found) < 2:
                    failures.append({"doc_id": doc_id, "matched": list(found)})
                    continue
                month = period_end[:7]
                for metric, value in found.items():
                    kind = "usd" if metric == "trust-principal-receivables" else "pct"
                    rows.append(
                        {
                            "obs_id": hashlib.sha256(
                                f"{metric}|{entity}|{month}".encode()
                            ).hexdigest()[:16],
                            "metric_id": metric,
                            "entity_id": entity,
                            "period": month,
                            "period_type": "month",
                            "value": value,
                            "unit": "USD" if kind == "usd" else "pct",
                            "dims": {},
                            "source_ptr": {"doc_id": doc_id, "locator": "monthly servicer report"},
                            "as_of": today,
                            "epistemic_status": "reported",
                        }
                    )
                log.count(f"{entity}_docs")
        out = config.ROOT / "metrics/observations/trust.jsonl"
        out.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
        config.STATUS.mkdir(parents=True, exist_ok=True)
        (config.STATUS / "trust_parse_failures.json").write_text(json.dumps(failures, indent=1))
        log.ok(rows=len(rows), parse_failures=len(failures))

    run_isolated("extract.trust", run)


if __name__ == "__main__":
    main()
