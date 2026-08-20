"""Model-assisted entity spine (subsidiaries, board, executives, segments).

HUMAN GATE (rule 3 / D9): refuses to run on main; writes epistemic_status: draft on a
draft/* branch. Merging is a human act; compile excludes drafts regardless.
"""

from __future__ import annotations

import datetime as dt
import re
import subprocess

import yaml

from factpack import config, manifest as mlib, model
from factpack.runlog import RunLog, run_isolated

BRANCH = "draft/entity-spine"

SUBS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "jurisdiction": {"type": "string"},
            "kind": {"enum": ["bank", "trust", "subsidiary", "brand"]},
        },
        "required": ["name", "kind"],
        "additionalProperties": False,
    },
}
PEOPLE_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "role": {"type": "string"},
            "kind": {"enum": ["officer", "director", "both"]},
        },
        "required": ["name", "role", "kind"],
        "additionalProperties": False,
    },
}


def require_draft_branch() -> None:
    branch = subprocess.run(
        ["git", "branch", "--show-current"], capture_output=True, text=True, cwd=config.ROOT
    ).stdout.strip()
    if branch in ("main", "master", ""):
        current = branch or "(detached)"
        raise SystemExit(
            f"REFUSED: model-generated content cannot land on {current!r} (rule 3). "
            f"Run: git checkout -b {BRANCH}"
        )


def slugify(name: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", name.lower())).strip("-")[:60]


def latest_doc(source: str, doc_type_prefix: str) -> tuple[str, dict] | None:
    best = None
    for doc_id, m in mlib.iter_manifests():
        if m["source"] == source and m["doc_type"].startswith(doc_type_prefix):
            key = m.get("filed_date") or ""
            if best is None or key > best[1].get("filed_date", ""):
                best = (doc_id, m)
    return best


def main() -> None:
    require_draft_branch()

    def run(log: RunLog) -> None:
        today = dt.date.today().isoformat()
        written = 0

        tenk = latest_doc("edgar-cof", "10-K")
        if tenk:
            doc_id, _ = tenk
            text = (mlib.doc_dir(doc_id) / "extracted.txt").read_text(errors="replace")
            ex21 = text
            mt = re.search(r"=== EXHIBIT [^=]*ex[-_.]?21[^=]*===", text, re.I)
            if mt:
                ex21 = text[mt.start() : mt.start() + 30000]
            else:
                mt = re.search(r"subsidiaries of (the )?(registrant|company)", text, re.I)
                ex21 = text[mt.start() : mt.start() + 30000] if mt else text[-30000:]
            r = model.call(
                "Extract the list of subsidiaries from this SEC 10-K subsidiaries exhibit. "
                "Classify each: bank (chartered depository), trust (securitization/statutory "
                "trust), brand (consumer brand), else subsidiary. Only entities explicitly "
                "listed.\n\n" + ex21,
                feature="entity_spine", model=config.MODEL_SONNET, schema=SUBS_SCHEMA,
            )
            for sub in r.json or []:
                eid = slugify(sub["name"])
                if not eid or (config.ROOT / "entities" / f"{eid}.yaml").exists():
                    continue
                ent = {
                    "id": eid, "name": sub["name"], "type": sub["kind"],
                    "status": "active", "aliases": [],
                    "edges": [{"type": "subsidiary_of", "target": "cof"}],
                    "epistemic_status": "draft", "as_of": today,
                    "sources": [{"doc_id": doc_id, "locator": "Exhibit 21"}],
                }
                (config.ROOT / "entities" / f"{eid}.yaml").write_text(
                    yaml.safe_dump(ent, sort_keys=False, allow_unicode=True)
                )
                written += 1

        proxy = latest_doc("edgar-cof", "DEF 14A")
        if proxy:
            doc_id, _ = proxy
            text = (mlib.doc_dir(doc_id) / "extracted.txt").read_text(errors="replace")[:60000]
            r = model.call(
                "From this proxy statement text, list the board of directors and named "
                "executive officers with their titles. Only people explicitly named.\n\n" + text,
                feature="entity_spine", model=config.MODEL_SONNET, schema=PEOPLE_SCHEMA,
            )
            for p in r.json or []:
                eid = "person-" + slugify(p["name"])
                if (config.ROOT / "entities" / f"{eid}.yaml").exists():
                    continue
                edge_type = "director_of" if p["kind"] == "director" else "officer_of"
                edges = [{"type": edge_type, "target": "cof"}]
                if p["kind"] == "both":
                    edges.append({"type": "director_of", "target": "cof"})
                ent = {
                    "id": eid, "name": p["name"], "type": "person", "status": "active",
                    "aliases": [], "summary": p["role"], "edges": edges,
                    "epistemic_status": "draft", "as_of": today,
                    "sources": [{"doc_id": doc_id, "locator": "board/executive sections"}],
                }
                (config.ROOT / "entities" / f"{eid}.yaml").write_text(
                    yaml.safe_dump(ent, sort_keys=False, allow_unicode=True)
                )
                written += 1

        # segments (from 10-K segment reporting; fixed trio, drafted for human confirmation)
        for seg_id, seg_name in [
            ("segment-credit-card", "Credit Card segment"),
            ("segment-consumer-banking", "Consumer Banking segment"),
            ("segment-commercial-banking", "Commercial Banking segment"),
        ]:
            path = config.ROOT / "entities" / f"{seg_id}.yaml"
            if path.exists() or not tenk:
                continue
            ent = {
                "id": seg_id, "name": seg_name, "type": "segment", "status": "active",
                "aliases": [], "edges": [{"type": "segment_of", "target": "cof"}],
                "epistemic_status": "draft", "as_of": today,
                "sources": [{"doc_id": tenk[0], "locator": "segment reporting"}],
            }
            path.write_text(yaml.safe_dump(ent, sort_keys=False, allow_unicode=True))
            written += 1

        log.ok(entities_written=written)

    run_isolated("extract.entity_spine", run)


if __name__ == "__main__":
    main()
