"""Validate every structured file against its JSON Schema. Hard-fails on first-error-per-file."""

from __future__ import annotations

import json

import yaml

from factpack import config, schemas


def iter_problems():
    # corpus manifests
    for path in sorted(config.CORPUS.glob("*/*/manifest.yaml")):
        try:
            schemas.validate(yaml.safe_load(path.read_text()), "manifest")
        except Exception as e:  # noqa: BLE001
            yield f"{path}: {e}"

    # entities
    for path in sorted((config.ROOT / "entities").glob("*.yaml")):
        try:
            schemas.validate(yaml.safe_load(path.read_text()), "entity")
        except Exception as e:  # noqa: BLE001
            yield f"{path}: {e}"

    # events (JSONL)
    for path in sorted((config.ROOT / "events").glob("*.jsonl")):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                schemas.validate(json.loads(line), "event")
            except Exception as e:  # noqa: BLE001
                yield f"{path}:{i}: {e}"

    # metric definitions (one list file) — *_map.yaml files are extractor config, not definitions
    defs_path = config.ROOT / "metrics/definitions/definitions.yaml"
    if defs_path.exists():
        for i, d in enumerate(yaml.safe_load(defs_path.read_text()) or []):
            try:
                schemas.validate(d, "metric_definition")
            except Exception as e:  # noqa: BLE001
                yield f"{defs_path}[{i}]: {e}"

    # observations (JSONL)
    for path in sorted((config.ROOT / "metrics/observations").glob("*.jsonl")):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if not line.strip():
                continue
            try:
                schemas.validate(json.loads(line), "metric_observation")
            except Exception as e:  # noqa: BLE001
                yield f"{path}:{i}: {e}"

    # products
    for path in sorted((config.ROOT / "products").glob("*.yaml")):
        try:
            schemas.validate(yaml.safe_load(path.read_text()), "product")
        except Exception as e:  # noqa: BLE001
            yield f"{path}: {e}"

    # brief frontmatter
    for path in iter_brief_paths():
        try:
            fm = parse_frontmatter(path.read_text())
            schemas.validate(fm, "brief")
        except Exception as e:  # noqa: BLE001
            yield f"{path}: {e}"


def parse_frontmatter(text: str) -> dict:
    if not text.startswith("---"):
        raise ValueError("missing YAML frontmatter")
    _, fm, _ = text.split("---", 2)
    return yaml.safe_load(fm)


def iter_brief_paths():
    """briefs/*.md that are actual briefs (frontmatter present); BACKLOG etc. excluded."""
    for path in sorted((config.ROOT / "briefs").glob("*.md")):
        if path.read_text(errors="replace").startswith("---"):
            yield path


def main() -> int:
    problems = list(iter_problems())
    for p in problems:
        print(f"SCHEMA: {p}")
    print(f"schema_check: {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
