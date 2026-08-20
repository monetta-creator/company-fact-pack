"""Assemble the source packet for one brief: retrieval + metrics + events, every item
carrying its corpus doc pointer. Output: build/packets/<brief-id>.md
"""

from __future__ import annotations

import argparse
import json

from factpack import config, db as dblib, metrics_sql, retrieve
from scripts.briefs.topics import TOPICS


def assemble(brief_id: str) -> str:
    topic = TOPICS[brief_id]
    parts = [f"# Source packet: {topic['title']} ({brief_id})\n"]
    seen: set[str] = set()

    parts.append("## Corpus excerpts\n")
    for q in topic["queries"]:
        for c in retrieve.retrieve_chunks(q, {"entities": topic["entities"]}, top_n=6):
            if c["chunk_id"] in seen:
                continue
            seen.add(c["chunk_id"])
            parts.append(
                f"### [src:{c['doc_id']}#{c['section_id']}]\n"
                f"({c['title']}, filed {c.get('filed_date')})\n\n"
                f"{c['preamble']}\n\n{c['text'][:2200]}\n"
            )

    if topic["metric_hints"]:
        parts.append("\n## Governed observations\n")
        for hint in topic["metric_hints"]:
            defs = metrics_sql.find_metrics(hint)
            if not defs:
                continue
            obs = metrics_sql.query_observations(
                [d["metric_id"] for d in defs],
                entity_id=topic["entities"][0] if topic["entities"] else None,
                limit=24,
            )
            for o in obs:
                parts.append(
                    f"- [src:{o['source_doc']}] {o['metric_id']} {o['entity_id']} "
                    f"{o['period']} = {o['value']} {o['unit']}"
                )

    db = dblib.connect()
    rows = db.execute(
        "SELECT * FROM events WHERE "
        + " OR ".join("entity_ids LIKE ?" for _ in topic["entities"])
        + " ORDER BY date DESC LIMIT 30",
        [f'%"{e}"%' for e in topic["entities"]],
    ).fetchall()
    db.close()
    if rows:
        parts.append("\n## Events\n")
        for r in rows:
            src = json.loads(r["source_ptr"])
            src_id = src[0]["doc_id"] if src else "?"
            parts.append(f"- [src:{src_id}] {r['date']} ({r['type']}) {r['title']}")

    packet = "\n".join(parts)
    config.PACKETS.mkdir(parents=True, exist_ok=True)
    (config.PACKETS / f"{brief_id}.md").write_text(packet)
    return packet


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("brief_id", choices=sorted(TOPICS))
    args = ap.parse_args()
    packet = assemble(args.brief_id)
    print(f"packet written: build/packets/{args.brief_id}.md ({len(packet)} chars)")


if __name__ == "__main__":
    main()
