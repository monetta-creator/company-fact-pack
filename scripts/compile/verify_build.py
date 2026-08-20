"""Post-build verification: counts, round-trip probes, golden smoke recall.

Writes build/build_report.md; exits nonzero when a probe fails outright.
"""

from __future__ import annotations

import json

import numpy as np
import yaml

from factpack import config, db as dblib, embed
from factpack.runlog import RunLog, run_isolated


def main() -> None:
    def run(log: RunLog) -> None:
        db = dblib.connect()
        counts = {
            t: db.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("chunks", "chunks_fts", "entities", "events",
                      "metric_definitions", "metric_observations", "briefs")
        }
        lines = ["# Build report\n", "## Counts\n"]
        lines += [f"- {k}: {v}" for k, v in counts.items()]
        ok = counts["chunks"] > 0 and counts["chunks"] == counts["chunks_fts"]

        # FTS round trip
        hit = db.execute(
            "SELECT chunk_id FROM chunks_fts WHERE chunks_fts MATCH ? LIMIT 1", ("credit",)
        ).fetchone()
        lines.append(f"\n- FTS probe ('credit'): {'hit' if hit else 'MISS'}")
        ok = ok and hit is not None

        # vector round trip
        vecs, rowids = dblib.vectors()
        q = embed.embed_query("credit card charge-off trends")
        top = rowids[np.argsort(vecs @ q)[::-1][:3]]
        sample = db.execute(
            f"SELECT doc_id FROM chunks WHERE rowid IN ({','.join('?' * len(top))})",
            [int(r) for r in top],
        ).fetchall()
        lines.append(f"- vector probe top-3 docs: {[r['doc_id'] for r in sample]}")
        ok = ok and len(sample) == len(top) and vecs.shape[0] == counts["chunks"]

        # golden smoke (first 10 queries if the set exists)
        golden = config.ROOT / "evals/golden/retrieval.yaml"
        if golden.exists():
            from factpack.retrieve import retrieve_chunks

            queries = yaml.safe_load(golden.read_text())[:10]
            hits = 0
            for g in queries:
                pack = retrieve_chunks(g["query"], filters={}, top_n=10)
                got_docs = {c["doc_id"] for c in pack}
                texts = " ".join(c["text"].lower() for c in pack)
                want = g.get("expect_doc_prefix")
                contain = g.get("must_contain")
                good = (not want or any(d.startswith(want) for d in got_docs)) and (
                    not contain or contain.lower() in texts
                )
                hits += good
            lines.append(f"- golden smoke: {hits}/{len(queries)} recall@10")
            ok = ok and hits >= max(1, len(queries) // 2)
        else:
            lines.append("- golden smoke: (no golden set yet)")

        meta = dict(db.execute("SELECT key, value FROM build_meta").fetchall())
        lines.append(f"\nbuilt_at: {meta.get('built_at')}  corpus_commit: {meta.get('corpus_commit')}")
        (config.BUILD / "build_report.md").write_text("\n".join(lines) + "\n")
        log.data["counts"].update(counts)
        if not ok:
            raise RuntimeError("build verification failed — see build/build_report.md")
        log.ok(**{k: v for k, v in counts.items()})

    run_isolated("compile.verify_build", run)


if __name__ == "__main__":
    main()
