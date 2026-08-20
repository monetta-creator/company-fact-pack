"""Intent router (D3): quantitative -> metric store; relational -> entity spine;
event -> events table; narrative -> hybrid retrieval. Every route also carries a few
narrative chunks for context, but the answer prompt permits figures ONLY from
observation rows.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from . import config, db as dblib, metrics_sql, retrieve
from .tags import Tagger
from .understand import Understanding


@dataclass
class RetrievalPack:
    chunks: list[dict] = field(default_factory=list)      # each carries ["tag"]
    observations: list[dict] = field(default_factory=list)
    entities: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    briefs: list[dict] = field(default_factory=list)

    def allowlist(self) -> set[str]:
        allowed = {c["tag"] for c in self.chunks}
        allowed |= {f"obs:{o['obs_id']}" for o in self.observations}
        allowed |= {f"ent:{e['id']}" for e in self.entities}
        allowed |= {f"ev:{e['id']}" for e in self.events}
        allowed |= {f"brief:{b['id']}" for b in self.briefs}
        return allowed

    def all_text(self) -> str:
        parts = [c["preamble"] + "\n" + c["text"] for c in self.chunks]
        parts += [b.get("body", "") for b in self.briefs]
        parts += [e.get("title", "") + " " + e.get("summary", "") for e in self.events]
        return "\n".join(parts)

    def obs_values(self) -> list[float]:
        vals = [o["value"] for o in self.observations]
        # values also appear in prose scaled to millions/billions; add common rescales
        for o in self.observations:
            v = o["value"]
            for scale in (1e3, 1e6, 1e9):
                vals.append(v / scale)
                vals.append(round(v / scale, 1))
                vals.append(round(v / scale, 2))
        return vals


def _filters(u: Understanding) -> dict:
    return {
        "entities": u.entities or None,
        "doc_types": u.doc_types or None,
        "period_start": u.period_start,
        "period_end": u.period_end,
    }


def build_pack(question: str, u: Understanding, tagger: Tagger | None = None) -> RetrievalPack:
    tagger = tagger or Tagger()
    pack = RetrievalPack()
    db = dblib.connect()

    if u.intent == "quantitative":
        metric_ids = [m["metric_id"] for m in metrics_sql.find_metrics(question)]
        period_prefix = (u.period_start or "")[:4] or None
        pack.observations = metrics_sql.query_observations(
            metric_ids or None,
            entity_id=u.entities[0] if u.entities else None,
            period_prefix=period_prefix,
        )
        # trim SOD/complaint dimension floods to the most recent periods
        if len(pack.observations) > 60:
            pack.observations = pack.observations[:60]

    if u.intent == "relational" or u.entities:
        ids = u.entities or [r["id"] for r in db.execute("SELECT id FROM entities LIMIT 8")]
        for eid in ids[:8]:
            row = db.execute("SELECT * FROM entities WHERE id = ?", (eid,)).fetchone()
            if row:
                e = dict(row)
                for k in ("aliases", "identifiers", "edges", "sources"):
                    e[k] = json.loads(e[k])
                pack.entities.append(e)
        if u.intent == "relational":
            # pull entities connected by edges too
            for e in list(pack.entities):
                for edge in e["edges"][:10]:
                    row = db.execute(
                        "SELECT * FROM entities WHERE id = ?", (edge["target"],)
                    ).fetchone()
                    if row and all(x["id"] != row["id"] for x in pack.entities):
                        t = dict(row)
                        for k in ("aliases", "identifiers", "edges", "sources"):
                            t[k] = json.loads(t[k])
                        pack.entities.append(t)

    if u.intent == "event":
        clauses, params = ["1=1"], []
        if u.entities:
            ors = " OR ".join("entity_ids LIKE ?" for _ in u.entities)
            clauses.append(f"({ors})")
            params.extend(f'%"{e}"%' for e in u.entities)
        if u.period_start:
            clauses.append("date >= ?")
            params.append(u.period_start)
        if u.period_end:
            clauses.append("date <= ?")
            params.append(u.period_end)
        rows = db.execute(
            f"SELECT * FROM events WHERE {' AND '.join(clauses)} ORDER BY date DESC LIMIT 40",
            params,
        ).fetchall()
        for r in rows:
            ev = dict(r)
            ev["entity_ids"] = json.loads(ev["entity_ids"])
            ev["source_ptr"] = json.loads(ev["source_ptr"])
            pack.events.append(ev)

    # merged briefs matching the entities always ride along (they're the doctrine layer)
    for r in db.execute("SELECT * FROM briefs LIMIT 6"):
        b = dict(r)
        b["entities"] = json.loads(b["entities"])
        if not u.entities or set(b["entities"]) & set(u.entities):
            pack.briefs.append(b)
    db.close()

    # narrative chunks for every intent (context), fewer when data rows carry the answer
    top_n = config.PACK_N if u.intent == "narrative" else max(4, config.PACK_N // 2)
    for c in retrieve.retrieve_chunks(question, _filters(u), top_n=top_n):
        c["tag"] = tagger.mint(c["chunk_id"])
        pack.chunks.append(c)
    return pack
