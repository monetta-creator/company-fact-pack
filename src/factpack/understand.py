"""Query understanding (D2): extract entity/period/doc-type filters and classify intent
BEFORE any retrieval scores relevance. Rules first (fast, free); haiku fallback only
when the rules can't classify.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, field

from . import config, db as dblib, model


@dataclass
class Understanding:
    intent: str = "narrative"  # quantitative | narrative | relational | event
    entities: list[str] = field(default_factory=list)
    period_start: str | None = None  # ISO date bounds applied to period_end/filed_date
    period_end: str | None = None
    doc_types: list[str] = field(default_factory=list)
    metric_hint: str | None = None


@functools.cache
def alias_map() -> dict[str, str]:
    out: dict[str, str] = {}
    try:
        db = dblib.connect()
        for row in db.execute("SELECT id, name, aliases FROM entities"):
            out[row["name"].lower()] = row["id"]
            out[row["id"]] = row["id"]
            for a in json.loads(row["aliases"]):
                out[a.lower()] = row["id"]
        db.close()
    except Exception:  # noqa: BLE001 — pre-build usage
        pass
    return out


DOC_TYPE_HINTS = {
    "10-k": "10-K", "annual report": "10-K", "10-q": "10-Q", "quarterly report": "10-Q",
    "8-k": "8-K", "press release": "8-K", "proxy": "DEF 14A", "s-4": "S-4",
    "merger proxy": "S-4", "transcript": "earnings-transcript", "10-d": "10-D",
    "servicer report": "10-D", "consent order": "consent-order",
    "agreement": "card-agreements", "complaint": "complaints-csv", "dfast": "dfast",
    "stress test": "dfast",
}
QUANT_RE = re.compile(
    r"\b(how much|how many|what (was|is|were) (the )?(value|rate|ratio|balance|total)|"
    r"revenue|net income|eps|charge.?off|delinquen|deposits?|assets?|allowance|provision|"
    r"payment rate|yield|cet1|roa|roe|nim|complaint (count|volume)|loans?)\b", re.I)
EVENT_RE = re.compile(r"\b(when|what happened|timeline|announce|history of|events?)\b", re.I)
REL_RE = re.compile(r"\b(who|subsidiar|board|director|officer|structure|owns?|parent|segments?)\b", re.I)

FALLBACK_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"enum": ["quantitative", "narrative", "relational", "event"]},
        "entities": {"type": "array", "items": {"type": "string"}},
        "year_start": {"type": ["integer", "null"]},
        "year_end": {"type": ["integer", "null"]},
    },
    "required": ["intent"],
    "additionalProperties": False,
}


def parse_periods(q: str) -> tuple[str | None, str | None]:
    years = [int(y) for y in re.findall(r"\b(20[0-3]\d)\b", q)]
    qm = re.search(r"\b[qQ]([1-4])\s*(20[0-3]\d)\b|\b(20[0-3]\d)\s*[qQ]([1-4])\b", q)
    if qm:
        quarter = int(qm.group(1) or qm.group(4))
        year = int(qm.group(2) or qm.group(3))
        return f"{year}-{quarter * 3 - 2:02d}-01", f"{year}-{quarter * 3:02d}-31"
    if years:
        return f"{min(years)}-01-01", f"{max(years)}-12-31"
    return None, None


def understand(question: str, *, allow_model_fallback: bool = True) -> Understanding:
    q = question.lower()
    u = Understanding()
    for alias, eid in alias_map().items():
        if len(alias) >= 3 and alias in q and eid not in u.entities:
            u.entities.append(eid)
    for hint, dt in DOC_TYPE_HINTS.items():
        if hint in q and dt not in u.doc_types:
            u.doc_types.append(dt)
    u.period_start, u.period_end = parse_periods(q)

    if QUANT_RE.search(q):
        u.intent = "quantitative"
        u.metric_hint = QUANT_RE.search(q).group(0)
    elif EVENT_RE.search(q):
        u.intent = "event"
    elif REL_RE.search(q):
        u.intent = "relational"
    elif allow_model_fallback and len(q.split()) > 3:
        try:
            r = model.call(
                "Classify this question about Capital One for a retrieval router. "
                f"Question: {question}",
                feature="query_understand", model=config.MODEL_HAIKU, schema=FALLBACK_SCHEMA,
                timeout_s=60, retries=1,
            )
            data = r.json or {}
            u.intent = data.get("intent", "narrative")
            for name in data.get("entities", []) or []:
                eid = alias_map().get(str(name).lower())
                if eid and eid not in u.entities:
                    u.entities.append(eid)
            if data.get("year_start"):
                u.period_start = u.period_start or f"{data['year_start']}-01-01"
            if data.get("year_end"):
                u.period_end = u.period_end or f"{data['year_end']}-12-31"
        except model.ModelError:
            u.intent = "narrative"
    return u
