"""Chunk labeling via the aboutness ladder — ZERO model calls, all local.

A label has two halves: situating (free metadata) and aboutness. Aboutness comes from:
  Rung 0 — the regulator's own structure: SEC form sections have fixed meanings
           (10-K Item 7 is always MD&A). A static dictionary covers most chunks.
  Rung 1 — extraction, not generation: the chunk's own topic sentence (nearest its
           embedding centroid, computed with the local embedder) plus its most
           distinctive terms (TF-IDF against the whole corpus).
Legacy model-written labels (build/enrich-cache/, paid for in earlier runs) are still
honored where they exist. Results cache in build/aboutness.jsonl keyed by content-
addressed chunk_id, so re-runs only compute new chunks.

Output: build/enriched.jsonl
"""

from __future__ import annotations

import json
import math
import re
from collections import Counter

from factpack import config
from factpack.runlog import RunLog, run_isolated

ABOUTNESS = config.BUILD / "aboutness.jsonl"

# Rung 0: section -> topic, by form family. Matched on the section label inside section_id.
TOPICS_10K = {
    "ITEM1": "business overview", "ITEM1A": "risk factors",
    "ITEM1B": "unresolved staff comments", "ITEM1C": "cybersecurity disclosure",
    "ITEM2": "properties", "ITEM3": "legal proceedings",
    "ITEM5": "stock and shareholder matters", "ITEM6": "selected financial data",
    "ITEM7": "management's discussion and analysis (MD&A)",
    "ITEM7A": "market risk disclosures", "ITEM8": "financial statements and notes",
    "ITEM9A": "controls and procedures", "ITEM10": "directors and governance",
    "ITEM11": "executive compensation", "ITEM12": "ownership",
    "ITEM13": "related-party transactions", "ITEM14": "auditor fees",
    "ITEM15": "exhibits and schedules",
}
TOPICS_10Q = {
    "ITEM1": "financial statements and notes",
    "ITEM1A": "risk factor updates",
    "ITEM2": "management's discussion and analysis (MD&A)",
    "ITEM3": "market risk disclosures", "ITEM4": "controls and procedures",
}
STOP = set("""the and for that with this from are was were has have had its their our your
which will would could should than then them they there been being also may can must
not any all each such other more most some out over under between during per upon these
those into within without about above below after before while where when what who whom
whose how why does did doing done because however therefore thereof herein hereby
company companies inc corp corporation""".split())
WORD_RE = re.compile(r"[a-z][a-z0-9-]{2,}")
SENT_RE = re.compile(r"(?<=[.!?])\s+")


def section_topic(doc_type: str, section_id: str, kind: str) -> str | None:
    label = section_id.split(":")[-1].upper().replace(" ", "")
    if doc_type.startswith("10-Q") and label in TOPICS_10Q:
        return TOPICS_10Q[label]
    if label in TOPICS_10K:
        return TOPICS_10K[label]
    low = section_id.lower()
    if "ex_" in low and "21" in low:
        return "subsidiaries list"
    if "ex_" in low and "99" in low:
        return "press release / exhibit"
    if kind == "table":
        return "financial table"
    return None


def deterministic_preamble(c: dict, topic: str | None) -> str:
    bits = [f"From {c['title'] or c['doc_id']}"]
    if topic:
        bits.append(topic)
    elif c.get("section_id") and c["section_id"] != "main":
        bits.append(f"section {c['section_id'].split(':')[-1]}")
    if c.get("period_end"):
        bits.append(f"period ending {c['period_end']}")
    if c.get("entities"):
        bits.append("filer: " + ", ".join(c["entities"]))
    return "; ".join(bits) + "."


def tokenize(text: str) -> list[str]:
    return [w for w in WORD_RE.findall(text.lower()) if w not in STOP]


def usable_sentences(text: str) -> list[str]:
    text = re.sub(r"\[TABLE\].*?\[/TABLE\]", " ", text, flags=re.S)
    out = [s.strip() for s in SENT_RE.split(text) if 40 <= len(s.strip()) <= 300]
    return out[:8]


def compute_aboutness(chunks: list[dict], log: RunLog) -> dict[str, dict]:
    """chunk_id -> {topic_sentence, keywords}; cached in build/aboutness.jsonl."""
    cache: dict[str, dict] = {}
    if ABOUTNESS.exists():
        for line in ABOUTNESS.read_text().splitlines():
            if line.strip():
                d = json.loads(line)
                cache[d["chunk_id"]] = d
    pending = [c for c in chunks if c["chunk_id"] not in cache]
    log.note(f"aboutness: {len(cache)} cached, {len(pending)} to compute")
    if not pending:
        return cache

    # corpus document frequencies for TF-IDF (one pass, local)
    df: Counter = Counter()
    for c in chunks:
        df.update(set(tokenize(c["text"])))
    n_docs = len(chunks)

    # batch-embed every candidate sentence across all pending chunks in one pass
    sent_index: list[tuple[int, int]] = []  # (chunk_idx, sent_idx)
    sentences: list[str] = []
    per_chunk: list[list[str]] = []
    for i, c in enumerate(pending):
        ss = usable_sentences(c["text"]) if c["kind"] != "table" else []
        per_chunk.append(ss)
        for j, s in enumerate(ss):
            sent_index.append((i, j))
            sentences.append(s)
    best_sentence: dict[int, str] = {}
    if sentences:
        import numpy as np

        from factpack import embed

        vecs = embed.embed_passages(sentences)
        offset = 0
        for i, ss in enumerate(per_chunk):
            k = len(ss)
            if k >= 2:
                block = vecs[offset : offset + k]
                centroid = block.mean(axis=0)
                centroid /= np.linalg.norm(centroid) or 1.0
                best_sentence[i] = ss[int(np.argmax(block @ centroid))]
            elif k == 1:
                best_sentence[i] = ss[0]
            offset += k

    with ABOUTNESS.open("a") as f:
        for i, c in enumerate(pending):
            tf = Counter(tokenize(c["text"]))
            scored = sorted(
                ((cnt * math.log(n_docs / (1 + df[w])), w) for w, cnt in tf.items()),
                reverse=True,
            )
            entry = {
                "chunk_id": c["chunk_id"],
                "topic_sentence": best_sentence.get(i, "")[:200],
                "keywords": [w for _, w in scored[:5]],
            }
            cache[c["chunk_id"]] = entry
            f.write(json.dumps(entry, separators=(",", ":")) + "\n")
    log.count("computed", len(pending))
    return cache


def main() -> None:
    def run(log: RunLog) -> None:
        chunks = [
            json.loads(line)
            for line in (config.BUILD / "chunks.jsonl").read_text().splitlines()
            if line.strip()
        ]
        aboutness = compute_aboutness(chunks, log)

        out = (config.BUILD / "enriched.jsonl").open("w")
        legacy = 0
        for c in chunks:
            legacy_path = config.ENRICH_CACHE / f"{c['chunk_id']}.json"
            topic = section_topic(c["doc_type"], c["section_id"], c["kind"])
            if legacy_path.exists():
                lead = json.loads(legacy_path.read_text())["preamble"]
                legacy += 1
            else:
                lead = deterministic_preamble(c, topic)
            about = aboutness.get(c["chunk_id"], {})
            parts = [lead]
            if about.get("topic_sentence"):
                parts.append(f"Covers: {about['topic_sentence']}")
            if about.get("keywords"):
                parts.append("Key terms: " + ", ".join(about["keywords"]))
            c["preamble"] = " ".join(parts)[:600]
            out.write(json.dumps(c, separators=(",", ":")) + "\n")
        out.close()
        log.ok(chunks=len(chunks), legacy_model_labels=legacy, still_pending=0)

    run_isolated("compile.enrich", run)


if __name__ == "__main__":
    main()
