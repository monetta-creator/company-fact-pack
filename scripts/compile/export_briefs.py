"""Export the context pack for downstream synthesizers — the product's front door.

Four stable-URL JSON files under export/ (raw.githubusercontent.com/.../main/export/):
  briefs.json    human-approved doctrine (drafts excluded — the gate travels with it)
  metrics.json   every governed definition + current observation, source pointer each
  events.json    the dated timeline, source pointers each
  entities.json  the entity map with identifiers and edges
Deterministic (no timestamps): committed files change only when the data does.
doc_urls in each file resolves every cited doc_id to its original public source.
"""

from __future__ import annotations

import json
import re

from factpack import config, db as dblib, manifest as mlib
from factpack.runlog import RunLog, run_isolated
from scripts.validate.schema_check import iter_brief_paths, parse_frontmatter

SRC_RE = re.compile(r"\[src:([^\]#\s]+)(#[^\]]*)?\]")
OUT = config.ROOT / "export"
HEADER = {
    "dataset": "company-fact-pack",
    "subject": "Capital One Financial Corporation",
    "license_note": "All content derives from public sources; each doc_id resolves to its "
                    "origin URL in doc_urls.",
}


def _doc_urls(cited: set[str]) -> dict[str, str]:
    return {doc_id: m["url"] for doc_id, m in mlib.iter_manifests() if doc_id in cited}


def _write(name: str, payload: dict) -> None:
    OUT.mkdir(exist_ok=True)
    (OUT / name).write_text(json.dumps({**HEADER, **payload}, indent=1, ensure_ascii=False))


def main() -> None:
    def run(log: RunLog) -> None:
        # briefs (from files: the human gate lives in frontmatter, not the DB)
        briefs, cited = [], set()
        for path in iter_brief_paths():
            fm = parse_frontmatter(path.read_text())
            if fm["epistemic_status"] == "draft":
                log.count("drafts_excluded")
                continue
            body = path.read_text().split("---", 2)[2].strip()
            doc_ids = sorted({m[0] for m in SRC_RE.findall(body)}
                             | {s["doc_id"] for s in fm.get("sources", [])})
            cited.update(doc_ids)
            briefs.append({"id": fm["id"], "title": fm["title"], "entities": fm["entities"],
                           "as_of": fm["as_of"], "review_by": fm["review_by"],
                           "epistemic_status": fm["epistemic_status"],
                           "sources": doc_ids, "body": body})
        _write("briefs.json", {"brief_count": len(briefs),
                               "briefs": sorted(briefs, key=lambda b: b["id"]),
                               "doc_urls": _doc_urls(cited)})
        log.count("briefs", len(briefs))

        db = dblib.connect()

        defs = [dict(r) for r in db.execute("SELECT * FROM metric_definitions")]
        obs, obs_docs = [], set()
        for r in db.execute("SELECT * FROM current_observations ORDER BY metric_id, period"):
            o = dict(r)
            o["dims"] = json.loads(o["dims"])
            o.pop("superseded_by", None)
            obs.append(o)
            obs_docs.add(o["source_doc"])
        _write("metrics.json", {"definitions": defs, "observation_count": len(obs),
                                "observations": obs, "doc_urls": _doc_urls(obs_docs)})
        log.count("observations", len(obs))

        events, ev_docs = [], set()
        for r in db.execute("SELECT * FROM events ORDER BY date DESC"):
            e = dict(r)
            e["entity_ids"] = json.loads(e["entity_ids"])
            e["source_ptr"] = json.loads(e["source_ptr"])
            ev_docs.update(p["doc_id"] for p in e["source_ptr"])
            events.append(e)
        _write("events.json", {"event_count": len(events), "events": events,
                               "doc_urls": _doc_urls(ev_docs)})
        log.count("events", len(events))

        entities = []
        for r in db.execute("SELECT * FROM entities ORDER BY type, id"):
            e = dict(r)
            for k in ("aliases", "identifiers", "edges", "sources"):
                e[k] = json.loads(e[k])
            entities.append(e)
        _write("entities.json", {"entity_count": len(entities), "entities": entities})
        log.count("entities", len(entities))

        db.close()

    run_isolated("compile.export_briefs", run)


if __name__ == "__main__":
    main()
