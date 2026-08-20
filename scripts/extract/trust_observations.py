"""Form 10-D servicer reports -> monthly trust performance observations.

Header-keyword-driven table parsing (formats drift across a decade); a document where
fewer than 2 metrics match is quarantined to build/status/trust_parse_failures.json
and never stops the run.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated

# metric -> (row-label regex, value kind)  kind: pct | usd
PATTERNS: dict[str, tuple[re.Pattern, str]] = {
    "trust-principal-receivables": (
        re.compile(r"(?:total|sum of|aggregate)?\s*principal receivables", re.I), "usd"),
    "trust-payment-rate": (
        re.compile(r"(?:monthly\s+)?(?:principal\s+)?payment rate", re.I), "pct"),
    "trust-yield": (
        re.compile(r"portfolio yield|revenue yield|total yield", re.I), "pct"),
    "trust-charge-off-rate": (
        re.compile(r"(?:net\s+)?(?:principal\s+)?charge.?offs?\s*(?:rate)?|net loss rate", re.I), "pct"),
    "trust-delinq-30plus": (
        re.compile(r"(?:total\s+)?(?:30|thirty)\+?\s*(?:or more\s*)?days?\s*(?:or more\s*)?delinquent|delinquencies?\s*30", re.I), "pct"),
    "trust-excess-spread": (
        re.compile(r"excess spread", re.I), "pct"),
}
PCT_RE = re.compile(r"(-?\d{1,3}(?:\.\d{1,4})?)\s*%")
USD_RE = re.compile(r"\$?\s*(-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d{9,})")


def parse_doc(text: str) -> dict[str, float]:
    found: dict[str, float] = {}
    for line in text.splitlines():
        if "|" not in line and not any(p[0].search(line) for p in PATTERNS.values()):
            continue
        for metric, (rx, kind) in PATTERNS.items():
            if metric in found or not rx.search(line):
                continue
            if kind == "pct":
                m = PCT_RE.search(line)
                if m:
                    found[metric] = float(m.group(1))
            else:
                m = USD_RE.search(line)
                if m:
                    found[metric] = float(m.group(1).replace(",", ""))
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
                if not period_end:
                    continue
                text_path = mlib.doc_dir(doc_id) / "extracted.txt"
                if not text_path.exists():
                    continue
                found = parse_doc(text_path.read_text(errors="replace"))
                if len(found) < 2:
                    failures.append({"doc_id": doc_id, "matched": list(found)})
                    continue
                month = period_end[:7]
                for metric, value in found.items():
                    unit = "pct" if PATTERNS[metric][1] == "pct" else "USD"
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
                            "unit": unit,
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
