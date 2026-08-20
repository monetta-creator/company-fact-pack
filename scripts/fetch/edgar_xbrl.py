"""Fetch XBRL companyfacts for COF + DFS into corpus/edgar-<entity>/xbrl_companyfacts.

The raw JSON is the source of record for company-reported figures; the extract stage
maps tagged facts to governed metrics. Not chunked for retrieval (numbers never come
from prose — D3 — and these aren't prose anyway).
"""

from __future__ import annotations

import json

from factpack import config, edgar, manifest
from factpack.http import get_json
from factpack.runlog import RunLog, run_isolated

FETCHER = "edgar_xbrl v1"


def fetch_entity(entity: str, log: RunLog) -> None:
    doc_id = f"edgar-{entity}/xbrl_companyfacts"
    url = edgar.companyfacts_url(config.CIK[entity])
    data = get_json(url)
    raw = json.dumps(data, separators=(",", ":")).encode()
    n_tags = sum(len(v) for v in data.get("facts", {}).values())

    files = [manifest.store_bytes(doc_id, "companyfacts.json", raw, "raw")]
    summary = (
        f"XBRL companyfacts for {data.get('entityName')} (CIK {data.get('cik')}). "
        f"{n_tags} tagged concepts across taxonomies: "
        f"{', '.join(data.get('facts', {}).keys())}. Machine data; see metrics layer.\n"
    )
    files.append(manifest.store_bytes(doc_id, "extracted.txt", summary.encode(), "extracted"))

    m = manifest.base_manifest(
        doc_id, source=f"edgar-{entity}", tier="A", doc_type="xbrl-companyfacts",
        url=url, fetcher=FETCHER, entity_ids=[entity],
        title=f"XBRL companyfacts {entity.upper()}",
    )
    m["files"] = files
    m["meta"] = {"concept_count": n_tags}
    manifest.write(m)
    log.count("fetched")


def main() -> None:
    def run(log: RunLog) -> None:
        for entity in ("cof", "dfs"):
            fetch_entity(entity, log)

    run_isolated("fetch.edgar_xbrl", run)


if __name__ == "__main__":
    main()
