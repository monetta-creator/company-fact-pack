"""Fetch FDIC BankFind Suite data: quarterly financials + Summary of Deposits.

api.fdic.gov (verified 2026-08-19) — primary source for bank-subsidiary regulatory
series; FFIEC bulk files only enrich on top of this.
"""

from __future__ import annotations

import json

from factpack import config, manifest
from factpack.http import get_json
from factpack.runlog import RunLog, run_isolated

FETCHER = "fdic v1"
BASE = "https://api.fdic.gov/banks"


def _paged(path: str, filters: str) -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        data = get_json(
            f"{BASE}/{path}", params={"filters": filters, "limit": 10000, "offset": offset}
        )
        batch = [d["data"] for d in data.get("data", [])]
        rows.extend(batch)
        if len(batch) < 10000:
            return rows
        offset += 10000


def fetch_cert(name: str, cert: str, log: RunLog) -> None:
    for kind, path, filters in (
        ("financials", "financials", f"CERT:{cert}"),
        ("sod", "sod", f"CERT:{cert}"),
    ):
        doc_id = f"fdic/{kind}_{name}"
        rows = _paged(path, filters)
        if not rows:
            log.note(f"{doc_id}: no rows")
            continue
        raw = json.dumps(rows, separators=(",", ":")).encode()
        files = [manifest.store_bytes(doc_id, f"{kind}.json", raw, "raw")]
        summary = (
            f"FDIC {kind} for {name} (cert {cert}): {len(rows)} rows. "
            "Machine data; see metrics layer.\n"
        )
        files.append(manifest.store_bytes(doc_id, "extracted.txt", summary.encode(), "extracted"))
        m = manifest.base_manifest(
            doc_id, source="fdic", tier="A", doc_type=f"fdic-{kind}",
            url=f"{BASE}/{path}?filters={filters}", fetcher=FETCHER, entity_ids=[name],
            title=f"FDIC {kind} {name}",
        )
        m["files"] = files
        m["meta"] = {"cert": cert, "rows": len(rows)}
        manifest.write(m)
        log.count("fetched")


def main() -> None:
    def run(log: RunLog) -> None:
        for name, cert in config.FDIC_CERT.items():
            fetch_cert(name, cert, log)

    run_isolated("fetch.fdic", run)


if __name__ == "__main__":
    main()
