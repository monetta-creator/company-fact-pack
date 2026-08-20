"""FastAPI answer surface: /api/ask, /api/peek/*, static single-page UI.

The citation gate runs again at this render boundary (D5): the served answer is
re-gated against its own pack before leaving the process.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import citations as gate, config, db as dblib, update as updater
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


UI = Path(__file__).parent / "ui"
PAGES = {"/": "index.html", "/update": "update.html", "/howto": "howto.html",
         "/about": "about.html", "/architecture": "architecture.html"}


@app.get("/ui.css")
def stylesheet():
    from fastapi.responses import Response

    return Response((UI / "style.css").read_text(), media_type="text/css")


@app.get("/api/stats")
def stats():
    db = dblib.connect()
    out = {
        "docs": db.execute("SELECT COUNT(DISTINCT doc_id) FROM chunks").fetchone()[0],
        "chunks": db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0],
        "observations": db.execute("SELECT COUNT(*) FROM metric_observations").fetchone()[0],
        "events": db.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "briefs": db.execute("SELECT COUNT(*) FROM briefs").fetchone()[0],
    }
    db.close()
    return out


@app.get("/", response_class=HTMLResponse)
def index():
    return (UI / "index.html").read_text()


@app.get("/update", response_class=HTMLResponse)
def update_page():
    return (UI / "update.html").read_text()


@app.get("/howto", response_class=HTMLResponse)
def howto_page():
    return (UI / "howto.html").read_text()


@app.get("/about", response_class=HTMLResponse)
def about_page():
    return (UI / "about.html").read_text()


@app.get("/architecture", response_class=HTMLResponse)
def architecture_page():
    return (UI / "architecture.html").read_text()


@app.post("/api/update/start")
def update_start():
    err = updater.start_detached()
    return {"started": err is None, "error": err}


@app.get("/api/update/status")
def update_status():
    status = updater.read_status()
    status["running"] = updater.is_running()
    try:
        status["log_tail"] = updater.LOG_FILE.read_text()[-3000:]
    except OSError:
        status["log_tail"] = ""
    staleness = config.BUILD / "staleness_report.md"
    status["staleness"] = staleness.read_text() if staleness.exists() else ""
    return status


SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")


@app.post("/api/update/upload")
def update_upload(
    file: UploadFile = File(...),
    kind: str = Form(...),  # transcript | y9c | call
    entity: str = Form("cof"),
    quarter: str = Form(""),
    date: str = Form(""),
    source_desc: str = Form(""),
):
    name = SAFE_NAME.sub("_", file.filename or "upload")[:120]
    data = file.file.read()
    if not data:
        return {"ok": False, "error": "empty file"}
    if kind == "transcript":
        if not quarter:
            return {"ok": False, "error": "transcripts need a quarter (e.g. 2024Q3)"}
        dest_dir = config.ROOT / "inbox/transcripts"
        dest_dir.mkdir(parents=True, exist_ok=True)
        stem = SAFE_NAME.sub("_", f"{entity}_{quarter}")
        body_path = dest_dir / f"{stem}{Path(name).suffix or '.txt'}"
        body_path.write_bytes(data)
        (dest_dir / f"{stem}.yaml").write_text(yaml.safe_dump({
            "entity": entity, "quarter": quarter, "date": date or None,
            "source_desc": source_desc or "user upload", "original_name": name,
        }))
        where = str(body_path.relative_to(config.ROOT))
    elif kind in ("y9c", "call"):
        dest_dir = config.ROOT / "inbox/ffiec"
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / name).write_bytes(data)
        where = f"inbox/ffiec/{name}"
    else:
        return {"ok": False, "error": f"unknown kind {kind!r}"}
    return {"ok": True, "saved_to": where,
            "note": "Included next time an update runs (it verifies before it publishes)."}
