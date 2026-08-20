"""CFPB complaints CSV -> monthly complaint-count observations by product (deterministic)."""

from __future__ import annotations

import csv
import datetime as dt
import gzip
import hashlib
import io
import json

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated


def main() -> None:
    def run(log: RunLog) -> None:
        today = dt.date.today().isoformat()
        rows: list[dict] = []
        for entity in ("cof", "dfs"):
            doc_id = f"cfpb-complaints/{entity}"
            path = mlib.doc_dir(doc_id) / "complaints.csv.gz"
            if not path.exists():
                path = mlib.cache_dir(doc_id) / "complaints.csv.gz"
                if not path.exists():
                    log.note(f"{doc_id}: missing")
                    continue
            counts: dict[tuple[str, str], int] = {}
            with gzip.open(path, "rt", errors="replace") as f:
                reader = csv.DictReader(f)
                date_col = next((c for c in reader.fieldnames or [] if "received" in c.lower()), None)
                prod_col = next((c for c in reader.fieldnames or [] if c.lower() == "product"), None)
                if not date_col or not prod_col:
                    log.note(f"{doc_id}: columns not found in {reader.fieldnames[:6]}")
                    continue
                for r in reader:
                    d = (r.get(date_col) or "")[:7]
                    if len(d) != 7:
                        continue
                    product = (r.get(prod_col) or "unknown")[:60]
                    counts[(d, product)] = counts.get((d, product), 0) + 1
            for (month, product), n in sorted(counts.items()):
                rows.append(
                    {
                        "obs_id": hashlib.sha256(
                            f"complaint-count|{entity}|{month}|{product}".encode()
                        ).hexdigest()[:16],
                        "metric_id": "complaint-count",
                        "entity_id": entity,
                        "period": month,
                        "period_type": "month",
                        "value": float(n),
                        "unit": "count",
                        "dims": {"product": product},
                        "source_ptr": {"doc_id": doc_id, "locator": f"month={month} product={product}"},
                        "as_of": today,
                        "epistemic_status": "reported",
                    }
                )
            log.count(f"{entity}_months")
        out = config.ROOT / "metrics/observations/complaints.jsonl"
        out.write_text("".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows))
        log.ok(rows=len(rows))

    run_isolated("extract.complaints", run)


if __name__ == "__main__":
    main()
