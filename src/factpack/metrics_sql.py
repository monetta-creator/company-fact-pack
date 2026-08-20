"""Governed metric queries (D3): numbers come from current_observations with their
definitions and source pointers — never from prose chunks.
"""

from __future__ import annotations

import json
import re

from . import db as dblib


def find_metrics(hint: str) -> list[dict]:
    """Match metric definitions by id or name substring."""
    db = dblib.connect()
    tokens = [t for t in re.findall(r"[a-z0-9]+", hint.lower()) if len(t) > 2]
    rows = [dict(r) for r in db.execute("SELECT * FROM metric_definitions")]
    db.close()
    scored = []
    for r in rows:
        text = f"{r['metric_id']} {r['name']}".lower()
        score = sum(1 for t in tokens if t in text)
        if score:
            scored.append((score, r))
    scored.sort(key=lambda x: -x[0])
    return [r for _, r in scored[:5]]


def query_observations(
    metric_ids: list[str] | None = None,
    entity_id: str | None = None,
    period_prefix: str | None = None,
    limit: int = 60,
) -> list[dict]:
    db = dblib.connect()
    clauses, params = ["1=1"], []
    if metric_ids:
        clauses.append(f"metric_id IN ({','.join('?' * len(metric_ids))})")
        params.extend(metric_ids)
    if entity_id:
        clauses.append("entity_id = ?")
        params.append(entity_id)
    if period_prefix:
        clauses.append("(period LIKE ? OR period LIKE ?)")
        params.extend([period_prefix + "%", "FY" + period_prefix[:4] + "%"])
    rows = db.execute(
        f"""SELECT o.*, d.name AS metric_name, d.unit AS def_unit, d.basis, d.formula
            FROM current_observations o JOIN metric_definitions d USING (metric_id)
            WHERE {' AND '.join(clauses)}
            ORDER BY period DESC, metric_id LIMIT ?""",
        [*params, limit],
    ).fetchall()
    db.close()
    out = []
    for r in rows:
        d = dict(r)
        d["dims"] = json.loads(d["dims"])
        out.append(d)
    return out
