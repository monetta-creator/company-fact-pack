"""Orphan detection (warnings, not failures): unreferenced entities, empty extractions."""

from __future__ import annotations

import json

import yaml

from factpack import config, manifest as mlib
from scripts.validate.schema_check import parse_frontmatter


def main() -> int:
    referenced_entities: set[str] = set()
    for path in (config.ROOT / "metrics/observations").glob("*.jsonl"):
        for line in path.read_text().splitlines():
            if line.strip():
                referenced_entities.add(json.loads(line)["entity_id"])
    for path in (config.ROOT / "events").glob("*.jsonl"):
        for line in path.read_text().splitlines():
            if line.strip():
                referenced_entities.update(json.loads(line)["entity_ids"])
    for path in (config.ROOT / "briefs").glob("*.md"):
        referenced_entities.update(parse_frontmatter(path.read_text())["entities"])
    for _, m in mlib.iter_manifests():
        referenced_entities.update(m.get("entity_ids", []))

    warnings = []
    for path in sorted((config.ROOT / "entities").glob("*.yaml")):
        ent = yaml.safe_load(path.read_text())
        if ent["id"] not in referenced_entities:
            warnings.append(f"entity {ent['id']!r} referenced by nothing")

    for doc_id, m in mlib.iter_manifests():
        extracted = [f for f in m["files"] if f["role"] == "extracted"]
        if not extracted:
            warnings.append(f"{doc_id}: no extracted text file")
        elif all(f.get("size", 0) < 40 for f in extracted):
            warnings.append(f"{doc_id}: extracted text nearly empty")

    for w in warnings:
        print(f"ORPHAN: {w}")
    print(f"orphans: {len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
