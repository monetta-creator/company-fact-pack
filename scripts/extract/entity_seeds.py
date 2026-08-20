"""Deterministic entity seeds — identifier records derived mechanically from fetched data.

No model judgment: names/identifiers come from API responses already in the corpus;
status is derived from data recency (an entity whose filings/reports stopped >400 days
ago is 'historical'). Narrative enrichment (edges, officers, summaries) is the
model-assisted spine and lands on a draft/* branch instead (rule 3).
"""

from __future__ import annotations

import datetime as dt
import json

import yaml

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated

SEEDS = [
    # id, name, type, aliases, identifiers, source doc candidates (first existing wins)
    ("cof", "Capital One Financial Corporation", "holding_co",
     ["Capital One", "COF"], {"cik": config.CIK["cof"], "ticker": "COF"},
     ["edgar-cof/xbrl_companyfacts"]),
    ("dfs", "Discover Financial Services", "holding_co",
     ["Discover", "DFS"], {"cik": config.CIK["dfs"], "ticker": "DFS"},
     ["edgar-dfs/xbrl_companyfacts"]),
    ("comet", "Capital One Multi-asset Execution Trust", "trust",
     ["COMET"], {"cik": config.CIK["comet"]}, []),
    ("dcent", "Discover Card Execution Note Trust", "trust",
     ["DCENT"], {"cik": config.CIK["dcent"]}, []),
    ("cona", "Capital One, National Association", "bank",
     ["Capital One NA", "CONA"], {"fdic_cert": config.FDIC_CERT["cona"]},
     ["fdic/financials_cona"]),
    ("cobna", "Capital One Bank (USA), National Association", "bank",
     ["COBNA"], {"fdic_cert": config.FDIC_CERT["cobna"]},
     ["fdic/financials_cobna"]),
    ("discover-bank", "Discover Bank", "bank",
     [], {"fdic_cert": config.FDIC_CERT["discover-bank"]},
     ["fdic/financials_discover-bank"]),
]


def newest_activity(entity_id: str) -> dt.date | None:
    newest = None
    for _, m in mlib.iter_manifests():
        if entity_id in m.get("entity_ids", []):
            d = m.get("filed_date") or m.get("period_end") or m["retrieved_at"][:10]
            if d and (newest is None or d > newest):
                newest = d
    # FDIC docs: use the latest REPDTE inside the data, not retrieval date
    fin = mlib.doc_dir(f"fdic/financials_{entity_id}") / "financials.json"
    if fin.exists():
        try:
            dates = [str(r.get("REPDTE", "")) for r in json.loads(fin.read_text())]
            best = max((d for d in dates if len(d) == 8), default=None)
            if best:
                newest = f"{best[:4]}-{best[4:6]}-{best[6:]}"
        except Exception:  # noqa: BLE001
            pass
    return dt.date.fromisoformat(newest) if newest else None


def main() -> None:
    def run(log: RunLog) -> None:
        today = dt.date.today()
        existing_docs = {doc_id for doc_id, _ in mlib.iter_manifests()}
        for eid, name, etype, aliases, idents, source_docs in SEEDS:
            sources = [{"doc_id": d, "locator": None} for d in source_docs if d in existing_docs]
            if not sources:
                fallback = next((d for d in sorted(existing_docs) if eid in d.split("/")[0]), None)
                if fallback is None:
                    fallback = next(
                        (d for d, m in mlib.iter_manifests() if eid in m.get("entity_ids", [])),
                        None,
                    )
                if fallback is None:
                    log.note(f"{eid}: no corpus doc yet; skipping seed")
                    continue
                sources = [{"doc_id": fallback, "locator": None}]
            last = newest_activity(eid)
            status = "active" if last and (today - last).days <= 400 else "historical"
            ent = {
                "id": eid,
                "name": name,
                "type": etype,
                "status": status,
                "aliases": aliases,
                "identifiers": idents,
                "edges": [],
                "summary": "",
                "epistemic_status": "reported",
                "as_of": today.isoformat(),
                "sources": sources,
            }
            (config.ROOT / "entities" / f"{eid}.yaml").write_text(
                yaml.safe_dump(ent, sort_keys=False, allow_unicode=True)
            )
            log.count("seeded")

    run_isolated("extract.entity_seeds", run)


if __name__ == "__main__":
    main()
