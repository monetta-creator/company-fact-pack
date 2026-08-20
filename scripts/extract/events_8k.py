"""8-K filings -> events/edgar.jsonl.

Deterministic: event id, date, source_ptr, base type from 8-K item numbers.
Model-assisted (haiku, batched, metered): title + summary + refined type.
Incremental: accessions already in events/edgar.jsonl are skipped, so usage-limit
interruptions resume cleanly.
"""

from __future__ import annotations

import datetime as dt
import json

from factpack import config, manifest as mlib, model
from factpack.runlog import RunLog, run_isolated

EVENTS_PATH = config.ROOT / "events/edgar.jsonl"
BATCH = 12
TYPES = ["merger", "acquisition", "divestiture", "enforcement", "litigation", "leadership",
         "capital_action", "product_launch", "partnership", "breach", "rating_action",
         "results", "guidance", "regulatory", "other"]
ITEM_BASE = {
    "2.01": "acquisition", "2.02": "results", "5.02": "leadership",
    "3.02": "capital_action", "3.03": "capital_action", "8.01": "other",
    "7.01": "other", "1.01": "other", "1.03": "other",
}

SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "doc_id": {"type": "string"},
            "title": {"type": "string", "maxLength": 160},
            "summary": {"type": "string", "maxLength": 500},
            "type": {"enum": TYPES},
        },
        "required": ["doc_id", "title", "summary", "type"],
        "additionalProperties": False,
    },
}


def existing_ids() -> set[str]:
    if not EVENTS_PATH.exists():
        return set()
    return {
        json.loads(line)["id"]
        for line in EVENTS_PATH.read_text().splitlines()
        if line.strip()
    }


def main() -> None:
    def run(log: RunLog) -> None:
        done = existing_ids()
        today = dt.date.today().isoformat()
        candidates = []
        for doc_id, m in mlib.iter_manifests():
            if not m["doc_type"].startswith("8-K"):
                continue
            if m["source"] not in ("edgar-cof", "edgar-dfs"):
                continue
            acc = m.get("meta", {}).get("accession", doc_id.split("_")[-1])
            ev_id = "ev-" + acc.replace("-", "")
            if ev_id in done:
                continue
            text_path = mlib.doc_dir(doc_id) / "extracted.txt"
            excerpt = text_path.read_text(errors="replace")[:900] if text_path.exists() else ""
            candidates.append(
                {
                    "ev_id": ev_id,
                    "doc_id": doc_id,
                    "date": m.get("period_end") or m.get("filed_date") or m["retrieved_at"][:10],
                    "entity": "cof" if m["source"] == "edgar-cof" else "dfs",
                    "items": m.get("meta", {}).get("items", ""),
                    "excerpt": excerpt,
                }
            )
        log.note(f"{len(candidates)} new 8-Ks to event-ize ({len(done)} already done)")

        def summarize(batch: list[dict]) -> list[dict] | None:
            listing = "\n\n".join(
                f"doc_id: {c['doc_id']}\nfiled: {c['date']}  8-K items: {c['items']}\n"
                f"excerpt:\n{c['excerpt']}"
                for c in batch
            )
            prompt = (
                "For each SEC 8-K filing below, write a factual title (<=160 chars) and a 1-3 "
                "sentence summary of the disclosed event, strictly from the excerpt — no outside "
                f"knowledge, no speculation. Pick type from {TYPES}. One output object per input, "
                "same doc_id.\n\n" + listing
            )
            r = model.call(prompt, feature="event_summarize", schema=SCHEMA)
            return r.json

        batches = [candidates[i : i + BATCH] for i in range(0, len(candidates), BATCH)]
        new_events: list[dict] = []
        try:
            results = model.map_calls(batches, summarize)
        except model.UsageLimitError:
            log.note("usage limit hit; writing partial results (resume by re-running)")
            results = []
        by_doc = {c["doc_id"]: c for c in candidates}
        for batch_result in results:
            if not batch_result:
                continue
            for item in batch_result:
                c = by_doc.get(item["doc_id"])
                if c is None:
                    continue
                base = next(
                    (ITEM_BASE[i.strip()] for i in c["items"].split(",") if i.strip() in ITEM_BASE),
                    "other",
                )
                new_events.append(
                    {
                        "id": c["ev_id"],
                        "date": c["date"],
                        "type": item["type"] if item["type"] in TYPES else base,
                        "entity_ids": [c["entity"]],
                        "title": item["title"][:160],
                        "summary": item["summary"][:500],
                        "source_ptr": [{"doc_id": c["doc_id"], "locator": None}],
                        "epistemic_status": "reported",
                        "as_of": today,
                    }
                )
        with EVENTS_PATH.open("a") as f:
            for e in new_events:
                f.write(json.dumps(e, separators=(",", ":")) + "\n")
        log.ok(new_events=len(new_events), pending=len(candidates) - len(new_events))

    run_isolated("extract.events_8k", run)


if __name__ == "__main__":
    main()
