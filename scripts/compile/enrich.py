"""Contextual enrichment (D1): a generated preamble situating every chunk before embedding.

Two layers:
- deterministic floor: built from manifest metadata alone (no model call) — always present;
- model upgrade: batched haiku preambles, cached in build/enrich-cache/<chunk_id>.json,
  so incremental rebuilds only pay for new chunks and usage-limit interruptions resume.

Every model call is metered (D10). Output: build/enriched.jsonl
"""

from __future__ import annotations

import json

from factpack import config, model
from factpack.runlog import RunLog, run_isolated

BATCH = 15
# Templated monthly reports gain nothing from a generated preamble — the deterministic
# floor (doc, period, entity) already situates them. Override with FACTPACK_ENRICH_ALL=1.
SKIP_MODEL_DOC_TYPES = {"10-D", "10-D/A"}
SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "chunk_id": {"type": "string"},
            "preamble": {"type": "string", "maxLength": 400},
        },
        "required": ["chunk_id", "preamble"],
        "additionalProperties": False,
    },
}


def deterministic_preamble(c: dict) -> str:
    bits = [f"From {c['title'] or c['doc_id']}"]
    if c.get("section_id") and c["section_id"] != "main":
        bits.append(f"section {c['section_id'].split(':')[-1]}")
    if c.get("period_end"):
        bits.append(f"period ending {c['period_end']}")
    if c.get("entities"):
        bits.append("entities: " + ", ".join(c["entities"]))
    return "; ".join(bits) + "."


def cache_path(chunk_id: str):
    return config.ENRICH_CACHE / f"{chunk_id}.json"


def main() -> None:
    def run(log: RunLog) -> None:
        config.ENRICH_CACHE.mkdir(parents=True, exist_ok=True)
        chunks = [
            json.loads(line)
            for line in (config.BUILD / "chunks.jsonl").read_text().splitlines()
            if line.strip()
        ]
        import os

        skip_types = set() if os.environ.get("FACTPACK_ENRICH_ALL") else SKIP_MODEL_DOC_TYPES
        pending = [
            c for c in chunks
            if c["doc_type"] not in skip_types and not cache_path(c["chunk_id"]).exists()
        ]
        log.note(f"{len(chunks)} chunks; {len(pending)} need model preambles "
                 f"(doc types skipped: {sorted(skip_types)})")

        def enrich_batch(batch: list[dict]) -> int:
            listing = "\n\n".join(
                f"chunk_id: {c['chunk_id']}\ndoc: {c['doc_id']} — {c['title'] or ''} "
                f"({c['doc_type']}, filer/entities: {', '.join(c['entities']) or 'n/a'}, "
                f"period {c.get('period_end') or 'n/a'}) section {c['section_id']}\n"
                f"text:\n{c['text'][:1200]}"
                for c in batch
            )
            r = model.call(
                "For each chunk below, write ONE sentence (<=45 words) situating it for a "
                "retrieval index: document, section, entity, period, and what the chunk "
                "specifically covers. Name the FILER shown in the entities field (cof = "
                "Capital One, dfs = Discover Financial Services, comet/dcent = card trusts) "
                "— never guess a different company. Example: 'From DFS 10-Q Q2 2024, Item 2 "
                "MD&A: net charge-off and delinquency trends.' Echo chunk_id.\n\n" + listing,
                feature="chunk_enrich", schema=SCHEMA,
            )
            wrote = 0
            for item in r.json or []:
                p = cache_path(item["chunk_id"])
                if not p.exists():
                    p.write_text(json.dumps({"preamble": item["preamble"], "model": r.model}))
                    wrote += 1
            return wrote

        batches = [pending[i : i + BATCH] for i in range(0, len(pending), BATCH)]
        try:
            done = model.map_calls(batches, enrich_batch)
            log.count("model_preambles", sum(d or 0 for d in done))
        except model.UsageLimitError:
            log.note("usage limit hit — remaining chunks keep deterministic preambles; re-run to upgrade")

        out = (config.BUILD / "enriched.jsonl").open("w")
        upgraded = 0
        for c in chunks:
            p = cache_path(c["chunk_id"])
            if p.exists():
                c["preamble"] = json.loads(p.read_text())["preamble"]
                upgraded += 1
            else:
                c["preamble"] = deterministic_preamble(c)
            out.write(json.dumps(c, separators=(",", ":")) + "\n")
        out.close()
        still_pending = sum(
            1 for c in chunks
            if c["doc_type"] not in skip_types and not cache_path(c["chunk_id"]).exists()
        )
        log.ok(chunks=len(chunks), model_upgraded=upgraded, still_pending=still_pending)

    run_isolated("compile.enrich", run)


if __name__ == "__main__":
    main()
