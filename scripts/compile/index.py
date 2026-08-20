"""Build the compiled index: chunks + FTS5 + embeddings + entities/events/briefs tables.

Rule 3 enforced structurally: every loader here EXCLUDES epistemic_status='draft' rows,
so drafts are invisible to retrieval even if one were merged by mistake.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess

import numpy as np
import yaml

from factpack import config, db as dblib, embed
from factpack.runlog import RunLog, run_isolated
from scripts.validate.schema_check import iter_brief_paths, parse_frontmatter


def main() -> None:
    def run(log: RunLog) -> None:
        seen: set[str] = set()
        chunks = []
        dupes = 0
        for line in (config.BUILD / "enriched.jsonl").read_text().splitlines():
            if not line.strip():
                continue
            c = json.loads(line)
            if c["chunk_id"] in seen:  # identical text can repeat within a doc (TOC/boilerplate)
                dupes += 1
                continue
            seen.add(c["chunk_id"])
            chunks.append(c)
        if dupes:
            log.note(f"{dupes} duplicate chunk_ids collapsed")
        config.DB_PATH.unlink(missing_ok=True)
        db = dblib.connect()
        db.executescript(
            """
            CREATE TABLE chunks (
                rowid INTEGER PRIMARY KEY, chunk_id TEXT UNIQUE, doc_id TEXT, section_id TEXT,
                seq INT, kind TEXT, preamble TEXT, text TEXT, doc_type TEXT, source TEXT,
                tier TEXT, title TEXT, entities TEXT, filed_date TEXT, period_end TEXT);
            CREATE INDEX idx_chunks_doc ON chunks(doc_id);
            CREATE INDEX idx_chunks_source ON chunks(source, doc_type);
            CREATE VIRTUAL TABLE chunks_fts USING fts5(chunk_id UNINDEXED, body, tokenize='porter');
            CREATE TABLE entities (
                id TEXT PRIMARY KEY, name TEXT, type TEXT, status TEXT, aliases TEXT,
                identifiers TEXT, edges TEXT, summary TEXT, epistemic_status TEXT, as_of TEXT,
                sources TEXT);
            CREATE TABLE events (
                id TEXT PRIMARY KEY, date TEXT, type TEXT, entity_ids TEXT, title TEXT,
                summary TEXT, source_ptr TEXT, epistemic_status TEXT, as_of TEXT);
            CREATE INDEX idx_events_date ON events(date);
            CREATE TABLE briefs (
                id TEXT PRIMARY KEY, title TEXT, entities TEXT, as_of TEXT,
                epistemic_status TEXT, review_by TEXT, sources TEXT, body TEXT);
            CREATE TABLE build_meta (key TEXT PRIMARY KEY, value TEXT);
            """
        )

        rows = []
        fts_rows = []
        texts_for_embedding = []
        for i, c in enumerate(chunks, start=1):
            rows.append((
                i, c["chunk_id"], c["doc_id"], c["section_id"], c["seq"], c["kind"],
                c["preamble"], c["text"], c["doc_type"], c["source"], c["tier"],
                c["title"], json.dumps(c["entities"]), c.get("filed_date"), c.get("period_end"),
            ))
            fts_rows.append((c["chunk_id"], c["preamble"] + "\n" + c["text"]))
            texts_for_embedding.append(c["preamble"] + "\n" + c["text"][:4000])
        db.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
        db.executemany("INSERT INTO chunks_fts (chunk_id, body) VALUES (?,?)", fts_rows)
        log.count("chunks", len(rows))

        log.note("embedding chunks (MPS/CPU)...")
        vecs = embed.embed_passages(texts_for_embedding)
        rowids = np.arange(1, len(chunks) + 1, dtype=np.int64)
        np.savez_compressed(config.VECTORS_NPZ, embeddings=vecs, rowids=rowids)
        log.note(f"embeddings: {vecs.shape}")

        # entities / events / briefs — drafts excluded structurally
        for path in sorted((config.ROOT / "entities").glob("*.yaml")):
            e = yaml.safe_load(path.read_text())
            if e["epistemic_status"] == "draft":
                continue
            db.execute(
                "INSERT OR REPLACE INTO entities VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (e["id"], e["name"], e["type"], e["status"], json.dumps(e.get("aliases", [])),
                 json.dumps(e.get("identifiers", {})), json.dumps(e.get("edges", [])),
                 e.get("summary", ""), e["epistemic_status"], e["as_of"],
                 json.dumps(e.get("sources", []))),
            )
            log.count("entities")
        for path in sorted((config.ROOT / "events").glob("*.jsonl")):
            for line in path.read_text().splitlines():
                if not line.strip():
                    continue
                ev = json.loads(line)
                if ev["epistemic_status"] == "draft":
                    continue
                db.execute(
                    "INSERT OR REPLACE INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                    (ev["id"], ev["date"], ev["type"], json.dumps(ev["entity_ids"]), ev["title"],
                     ev.get("summary", ""), json.dumps(ev["source_ptr"]),
                     ev["epistemic_status"], ev["as_of"]),
                )
                log.count("events")
        for path in iter_brief_paths():
            fm = parse_frontmatter(path.read_text())
            if fm["epistemic_status"] == "draft":
                continue
            body = path.read_text().split("---", 2)[2]
            db.execute(
                "INSERT OR REPLACE INTO briefs VALUES (?,?,?,?,?,?,?,?)",
                (fm["id"], fm["title"], json.dumps(fm["entities"]), fm["as_of"],
                 fm["epistemic_status"], fm["review_by"], json.dumps(fm["sources"]), body),
            )
            log.count("briefs")

        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=config.ROOT
        ).stdout.strip()
        for k, v in [
            ("built_at", dt.datetime.now(dt.UTC).isoformat()),
            ("corpus_commit", commit),
            ("embed_model", config.EMBED_MODEL),
            ("rerank_model", config.RERANK_MODEL),
        ]:
            db.execute("INSERT OR REPLACE INTO build_meta VALUES (?,?)", (k, v))
        db.commit()
        db.close()

    run_isolated("compile.index", run)


if __name__ == "__main__":
    main()
