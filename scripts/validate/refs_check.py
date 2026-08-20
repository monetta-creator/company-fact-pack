"""The dangling-pointer gate (rule 2): every reference must resolve, or the build fails.

Checks:
- every source_ptr.doc_id (observations, events, entities, briefs, products) → a manifest
- every entity reference (obs.entity_id, event.entity_ids, brief.entities,
  product.issuer_entity_id) → entities/<id>.yaml
- every obs.metric_id → metrics/definitions/definitions.yaml
- every brief depends_on → an existing brief/entity/metric id
- every manifest files[] entry → the file exists (pass --hashes to re-verify SHA-256s)
"""

from __future__ import annotations

import argparse
import json

import yaml

from factpack import config, manifest as mlib
from factpack.http import sha256_file
from scripts.validate.schema_check import iter_brief_paths, parse_frontmatter


def load_universe():
    doc_ids, entity_ids, metric_ids, brief_ids = set(), set(), set(), set()
    for doc_id, _ in mlib.iter_manifests():
        doc_ids.add(doc_id)
    for path in (config.ROOT / "entities").glob("*.yaml"):
        entity_ids.add(yaml.safe_load(path.read_text())["id"])
    defs_path = config.ROOT / "metrics/definitions/definitions.yaml"
    if defs_path.exists():
        for d in yaml.safe_load(defs_path.read_text()) or []:
            metric_ids.add(d["metric_id"])
    for path in iter_brief_paths():
        brief_ids.add(parse_frontmatter(path.read_text())["id"])
    return doc_ids, entity_ids, metric_ids, brief_ids


def iter_problems(verify_hashes: bool):
    doc_ids, entity_ids, metric_ids, brief_ids = load_universe()
    all_ids = entity_ids | metric_ids | brief_ids

    def ptr(where: str, p: dict):
        if p["doc_id"] not in doc_ids:
            yield f"{where}: dangling doc_id {p['doc_id']!r}"

    def ent(where: str, eid: str):
        if eid not in entity_ids:
            yield f"{where}: unknown entity {eid!r}"

    # manifests: files exist (+hashes on demand); entity_ids resolve
    for doc_id, m in mlib.iter_manifests():
        for entry in m["files"]:
            f = mlib.file_location(doc_id, entry)
            if not f.exists():
                yield f"{doc_id}: missing file {entry['name']} ({entry['stored']})"
            elif verify_hashes and sha256_file(f) != entry["sha256"]:
                yield f"{doc_id}: hash mismatch on {entry['name']}"
        for eid in m.get("entity_ids", []):
            yield from ent(doc_id, eid)

    for path in (config.ROOT / "metrics/observations").glob("*.jsonl"):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            o = json.loads(line)
            where = f"{path.name}:{i}"
            yield from ptr(where, o["source_ptr"])
            yield from ent(where, o["entity_id"])
            if o["metric_id"] not in metric_ids:
                yield f"{where}: unknown metric {o['metric_id']!r}"

    for path in (config.ROOT / "events").glob("*.jsonl"):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            e = json.loads(line)
            where = f"{path.name}:{i}"
            for p in e["source_ptr"]:
                yield from ptr(where, p)
            for eid in e["entity_ids"]:
                yield from ent(where, eid)

    for path in (config.ROOT / "entities").glob("*.yaml"):
        ent_obj = yaml.safe_load(path.read_text())
        for p in ent_obj.get("sources", []):
            yield from ptr(path.name, p)
        for edge in ent_obj.get("edges", []):
            yield from ent(f"{path.name} edge", edge["target"])

    for path in (config.ROOT / "products").glob("*.yaml"):
        pr = yaml.safe_load(path.read_text())
        where = path.name
        yield from ent(where, pr["issuer_entity_id"])
        if pr["agreement_doc_id"] not in doc_ids:
            yield f"{where}: dangling agreement_doc_id {pr['agreement_doc_id']!r}"
        for p in pr.get("sources", []):
            yield from ptr(where, p)

    for path in iter_brief_paths():
        fm = parse_frontmatter(path.read_text())
        where = path.name
        for p in fm["sources"]:
            yield from ptr(where, p)
        for eid in fm["entities"]:
            yield from ent(where, eid)
        for dep in fm.get("depends_on", []):
            if dep not in all_ids:
                yield f"{where}: dangling depends_on {dep!r}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hashes", action="store_true", help="re-verify every file SHA-256")
    args = ap.parse_args()
    problems = list(iter_problems(args.hashes))
    for p in problems:
        print(f"REF: {p}")
    print(f"refs_check: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
