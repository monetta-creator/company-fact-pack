"""CFPB consumer complaints: full-database ZIP (static file), filtered locally to
Capital One + Discover, committed as per-entity .csv.gz.

The search API rejects large exports; the full DB at files.consumerfinance.gov/ccdb/
is one reliable request. The industry-wide ZIP stays in build/cache.
"""

from __future__ import annotations

import csv
import gzip
import io
import re
import zipfile

from factpack import config, manifest
from factpack.http import download
from factpack.runlog import RunLog, run_isolated

FETCHER = "cfpb_complaints v2"
FULL_DB = "https://files.consumerfinance.gov/ccdb/complaints.csv.zip"
COMPANY_RE = {
    "cof": re.compile(r"^CAPITAL ONE", re.I),
    "dfs": re.compile(r"^DISCOVER", re.I),
}


def main() -> None:
    def run(log: RunLog) -> None:
        if all(manifest.already_fetched(f"cfpb-complaints/{e}") for e in COMPANY_RE):
            log.ok(skipped=2)
            return
        cached = config.CACHE / "cfpb-complaints" / "complaints.csv.zip"
        if not cached.exists():
            log.note("downloading full complaints DB (large)")
            download(FULL_DB, cached)
        writers: dict[str, tuple] = {}
        counts = dict.fromkeys(COMPANY_RE, 0)
        with zipfile.ZipFile(cached) as zf:
            member = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
            with zf.open(member) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"))
                header = next(reader)
                try:
                    company_idx = next(
                        i for i, h in enumerate(header) if h.strip().lower() == "company"
                    )
                except StopIteration:
                    raise ValueError(f"no Company column in {header[:10]}") from None
                for entity in COMPANY_RE:
                    buf = io.BytesIO()
                    gz = gzip.GzipFile(fileobj=buf, mode="wb")
                    tw = io.TextIOWrapper(gz, encoding="utf-8", newline="")
                    w = csv.writer(tw)
                    w.writerow(header)
                    writers[entity] = (buf, gz, tw, w)
                for row in reader:
                    if len(row) <= company_idx:
                        continue
                    company = row[company_idx]
                    for entity, rx in COMPANY_RE.items():
                        if rx.search(company):
                            writers[entity][3].writerow(row)
                            counts[entity] += 1
                            break
        for entity, (buf, gz, tw, _) in writers.items():
            tw.flush()
            gz.close()
            doc_id = f"cfpb-complaints/{entity}"
            if manifest.already_fetched(doc_id):
                continue
            files = [
                manifest.store_bytes(doc_id, "complaints.csv.gz", buf.getvalue(), "raw"),
                manifest.store_bytes(
                    doc_id, "extracted.txt",
                    f"CFPB consumer complaints ({entity}): {counts[entity]} rows filtered from "
                    "the full database export. Aggregate signal; monthly rollups in metrics.\n".encode(),
                    "extracted",
                ),
            ]
            m = manifest.base_manifest(
                doc_id, source="cfpb-complaints", tier="A", doc_type="complaints-csv",
                url=FULL_DB, fetcher=FETCHER, entity_ids=[entity],
                title=f"CFPB complaints slice ({entity})",
            )
            m["files"] = files
            m["meta"] = {"rows": counts[entity], "filter": COMPANY_RE[entity].pattern}
            manifest.write(m)
            log.count("fetched")
        cached.unlink(missing_ok=True)  # full-DB ZIP is re-downloadable; slices are committed
        log.note(f"rows: {counts}")

    run_isolated("fetch.cfpb_complaints", run)


if __name__ == "__main__":
    main()
