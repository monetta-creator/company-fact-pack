"""FastAPI answer surface: /api/ask, /api/peek/*, static single-page UI.

The citation gate runs again at this render boundary (D5): the served answer is
re-gated against its own pack before leaving the process.
"""

from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import citations as gate, db as dblib
from .answer import ask as do_ask
from .deep import deep_ask

app = FastAPI(title="factpack")


class AskBody(BaseModel):
    question: str
    deep: bool = False
    tags: dict[str, str] = {}


@app.post("/api/ask")
def api_ask(body: AskBody):
    if body.deep:
        res = deep_ask(body.question, conversation_tags=body.tags or None)
    else:
        res = do_ask(body.question, conversation_tags=body.tags or None)
    regated = gate.enforce(res.answer, res.pack.allowlist())  # render-boundary gate
    citation_meta = {}
    for token in regated.citations:
        r = res.resolve_citation(token)
        if not r:
            continue
        if token.startswith("obs:"):
            citation_meta[token] = {"kind": "obs", "label": f"{r['metric_id']} {r['period']}",
                                    "doc_id": r["source_doc"]}
        elif token.startswith("ent:"):
            citation_meta[token] = {"kind": "entity", "label": r["name"], "id": r["id"]}
        elif token.startswith("ev:"):
            citation_meta[token] = {"kind": "event", "label": r["title"][:80], "id": r["id"]}
        elif token.startswith("brief:"):
            citation_meta[token] = {"kind": "brief", "label": r["title"], "id": r["id"]}
        else:
            citation_meta[token] = {"kind": "chunk", "label": r["doc_id"],
                                    "chunk_id": r["chunk_id"]}
    return {
        "answer": regated.text,
        "citations": regated.citations,
        "citation_meta": citation_meta,
        "audit": res.audit + regated.audit,
        "verify": {
            "quotes_checked": res.verify.quotes_checked,
            "numbers_checked": res.verify.numbers_checked,
            "model_checked": res.verify.model_checked,
            "flags": res.verify.flags,
        },
        "tags": res.tags,
        "cost_usd": res.cost_usd,
    }


@app.get("/api/peek/chunk/{chunk_id}")
def peek_chunk(chunk_id: str):
    db = dblib.connect()
    row = db.execute("SELECT * FROM chunks WHERE chunk_id = ?", (chunk_id,)).fetchone()
    db.close()
    if not row:
        return {"error": "unknown chunk"}
    c = dict(row)
    c["entities"] = json.loads(c["entities"])
    return c


@app.get("/api/peek/{kind}/{item_id:path}")
def peek(kind: str, item_id: str):
    db = dblib.connect()
    table = {"entity": "entities", "event": "events", "brief": "briefs"}.get(kind)
    if not table:
        return {"error": "unknown kind"}
    row = db.execute(f"SELECT * FROM {table} WHERE id = ?", (item_id,)).fetchone()
    db.close()
    return dict(row) if row else {"error": "not found"}


@app.get("/", response_class=HTMLResponse)
def index():
    return (Path(__file__).parent / "ui" / "index.html").read_text()
