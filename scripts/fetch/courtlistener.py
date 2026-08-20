"""CourtListener REST v4: dockets + opinions for major COF/Discover litigation."""

from __future__ import annotations

import json
import re

from factpack import manifest
from factpack.http import get_json
from factpack.runlog import RunLog, run_isolated

FETCHER = "courtlistener v1"
API = "https://www.courtlistener.com/api/rest/v4/search/"
QUERIES = [
    ('"Capital One Consumer Data Security Breach Litigation"', "r", "cof"),
    ('"Capital One" data breach 2019', "o", "cof"),
    ('"Capital One" v. "Walmart"', "o", "cof"),
    ('"Discover Financial Services" antitrust', "o", "dfs"),
]
MAX_RESULTS = 20


def main() -> None:
    def run(log: RunLog) -> None:
        for query, qtype, entity in QUERIES:
            slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:70]
            doc_id = f"courtlistener/{qtype}_{slug}"
            if manifest.already_fetched(doc_id):
                log.count("skipped")
                continue
            try:
                data = get_json(API, params={"q": query, "type": qtype, "order_by": "score desc"})
                results = data.get("results", [])[:MAX_RESULTS]
                if not results:
                    log.note(f"{query}: 0 results")
                    log.count("empty")
                    continue
                raw = json.dumps(results, indent=1).encode()
                text_parts = []
                for r in results:
                    name = r.get("caseName") or r.get("caseNameFull") or "(unnamed)"
                    court = r.get("court") or r.get("court_id") or ""
                    date = r.get("dateFiled") or r.get("dateArgued") or ""
                    snippet = re.sub(r"<[^>]+>", " ", str(r.get("snippet") or ""))[:1500]
                    docket = r.get("docketNumber") or ""
                    text_parts.append(f"CASE: {name}\nCOURT: {court}  DATE: {date}  DOCKET: {docket}\n{snippet}\n")
                files = [
                    manifest.store_bytes(doc_id, "results.json", raw, "raw"),
                    manifest.store_bytes(
                        doc_id, "extracted.txt",
                        (f"CourtListener search: {query}\n\n" + "\n---\n".join(text_parts)).encode(),
                        "extracted",
                    ),
                ]
                m = manifest.base_manifest(
                    doc_id, source="courtlistener", tier="A", doc_type="litigation-search",
                    url=f"{API}?q={query}&type={qtype}", fetcher=FETCHER, entity_ids=[entity],
                    title=f"CourtListener: {query}",
                )
                m["files"] = files
                m["meta"] = {"result_count": len(results)}
                manifest.write(m)
                log.count("fetched")
            except Exception as e:  # noqa: BLE001
                log.count("failed")
                log.note(f"{query}: {e}")

    run_isolated("fetch.courtlistener", run)


if __name__ == "__main__":
    main()
