"""Typed tools for the deep loop (D7). Input parsing returns ERROR STRINGS (never
raises) so the model can self-correct; every result is clipped to RESULT_CAP_CHARS.
"""

from __future__ import annotations

import json

from . import config, db as dblib, metrics_sql, retrieve
from .router import RetrievalPack
from .tags import Tagger

TOOL_DOCS = """Available tools (args must be a JSON object):
- search_corpus {"query": str, "entities": [ids]?, "doc_types": [str]?, "limit": int<=8}
- query_metrics {"metric_hint": str, "entity": id?, "period_prefix": "2024"|"2024Q2"?}
- get_entity {"id": str}
- list_events {"entity": id?, "date_start": "YYYY-MM-DD"?, "date_end": ...?, "type": str?}
- fetch_document {"doc_id": str, "section_id": str?}   (doc_ids appear in chunk headers)"""


def _clip(s: str) -> str:
    return s[: config.RESULT_CAP_CHARS]


def run_tool(name: str, args: dict, pack: RetrievalPack, tagger: Tagger) -> str:
    """Executes one tool, appending discoveries to the pack. Returns rendered result text
    (or an error string starting with 'ERROR:')."""
    try:
        if not isinstance(args, dict):
            return "ERROR: args must be a JSON object"
        if name == "search_corpus":
            query = args.get("query")
            if not isinstance(query, str) or not query.strip():
                return "ERROR: search_corpus requires a non-empty 'query' string"
            limit = min(int(args.get("limit", 6) or 6), 8)
            filters = {
                "entities": args.get("entities"),
                "doc_types": args.get("doc_types"),
            }
            hits = retrieve.retrieve_chunks(query, filters, top_n=limit)
            lines = []
            for c in hits:
                if all(x["chunk_id"] != c["chunk_id"] for x in pack.chunks):
                    c["tag"] = tagger.mint(c["chunk_id"])
                    pack.chunks.append(c)
                else:
                    c["tag"] = tagger.mint(c["chunk_id"])
                lines.append(f"[{c['tag']}] ({c['doc_id']} §{c['section_id']}) {c['preamble']} "
                             f"{c['text'][:240]}")
            return _clip("\n".join(lines) or "(no results)")

        if name == "query_metrics":
            hint = args.get("metric_hint")
            if not isinstance(hint, str) or not hint.strip():
                return "ERROR: query_metrics requires 'metric_hint'"
            metric_ids = [m["metric_id"] for m in metrics_sql.find_metrics(hint)]
            if not metric_ids:
                return f"ERROR: no governed metric matches {hint!r}; try different words"
            obs = metrics_sql.query_observations(
                metric_ids, entity_id=args.get("entity"),
                period_prefix=args.get("period_prefix"), limit=30,
            )
            for o in obs:
                if all(x["obs_id"] != o["obs_id"] for x in pack.observations):
                    pack.observations.append(o)
            lines = [
                f"[obs:{o['obs_id']}] {o['metric_id']} {o['entity_id']} {o['period']} = "
                f"{o['value']} {o['unit']} (source {o['source_doc']})"
                for o in obs
            ]
            return _clip("\n".join(lines) or "(no observations)")

        if name == "get_entity":
            eid = args.get("id")
            db = dblib.connect()
            row = db.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
            db.close()
            if not row:
                return f"ERROR: unknown entity {eid!r}"
            e = dict(row)
            for k in ("aliases", "identifiers", "edges", "sources"):
                e[k] = json.loads(e[k])
            if all(x["id"] != e["id"] for x in pack.entities):
                pack.entities.append(e)
            return _clip(
                f"[ent:{e['id']}] {e['name']} ({e['type']}, {e['status']}) ids={e['identifiers']} "
                f"edges={e['edges']}"
            )

        if name == "list_events":
            db = dblib.connect()
            clauses, params = ["1=1"], []
            if args.get("entity"):
                clauses.append("entity_ids LIKE ?")
                params.append(f'%"{args["entity"]}"%')
            if args.get("date_start"):
                clauses.append("date >= ?")
                params.append(args["date_start"])
            if args.get("date_end"):
                clauses.append("date <= ?")
                params.append(args["date_end"])
            if args.get("type"):
                clauses.append("type = ?")
                params.append(args["type"])
            rows = db.execute(
                f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY date DESC LIMIT 25",
                params,
            ).fetchall()
            db.close()
            lines = []
            for r in rows:
                ev = dict(r)
                ev["entity_ids"] = json.loads(ev["entity_ids"])
                ev["source_ptr"] = json.loads(ev["source_ptr"])
                if all(x["id"] != ev["id"] for x in pack.events):
                    pack.events.append(ev)
                lines.append(f"[ev:{ev['id']}] {ev['date']} ({ev['type']}) {ev['title']}")
            return _clip("\n".join(lines) or "(no events)")

        if name == "fetch_document":
            doc_id = args.get("doc_id")
            db = dblib.connect()
            clauses, params = ["doc_id = ?"], [doc_id]
            if args.get("section_id"):
                clauses.append("section_id = ?")
                params.append(args["section_id"])
            rows = db.execute(
                f"SELECT * FROM chunks WHERE {' AND '.join(clauses)} ORDER BY section_id, seq "
                "LIMIT 6",
                params,
            ).fetchall()
            db.close()
            if not rows:
                return f"ERROR: no chunks for doc {doc_id!r} (check doc_id/section_id)"
            lines = []
            for r in rows:
                c = dict(r)
                c["entities"] = json.loads(c["entities"])
                if all(x["chunk_id"] != c["chunk_id"] for x in pack.chunks):
                    c["tag"] = tagger.mint(c["chunk_id"])
                    pack.chunks.append(c)
                else:
                    c["tag"] = tagger.mint(c["chunk_id"])
                lines.append(f"[{c['tag']}] §{c['section_id']} {c['text'][:400]}")
            return _clip("\n".join(lines))

        return f"ERROR: unknown tool {name!r}. {TOOL_DOCS}"
    except Exception as e:  # noqa: BLE001 — errors feed back as strings, never crash the loop
        return f"ERROR: {name} failed: {e}"
