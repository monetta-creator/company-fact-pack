"""Manifest read/write + the idempotency contract every fetcher honors.

A corpus doc lives at corpus/<doc_id>/ where doc_id = "<source>/<name>".
Raw files over the commit size policy live at build/cache/<doc_id>/<name>;
their SHA-256 in the manifest is the provenance proof (rule 2).
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import yaml

from . import config, schemas
from .http import sha256_file


def doc_dir(doc_id: str) -> Path:
    return config.CORPUS / doc_id


def cache_dir(doc_id: str) -> Path:
    return config.CACHE / doc_id


def manifest_path(doc_id: str) -> Path:
    return doc_dir(doc_id) / "manifest.yaml"


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_location(doc_id: str, entry: dict) -> Path:
    base = cache_dir(doc_id) if entry["stored"] == "cache" else doc_dir(doc_id)
    return base / entry["name"]


def read(doc_id: str) -> dict:
    return yaml.safe_load(manifest_path(doc_id).read_text())


def write(m: dict) -> None:
    schemas.validate(m, "manifest")
    path = manifest_path(m["doc_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(m, sort_keys=False, allow_unicode=True))


def already_fetched(doc_id: str, *, verify_hashes: bool = False) -> bool:
    """The re-run/skip contract. Default trusts manifest presence + file existence
    (hash verification over gigabytes is `make validate`'s job, not every fetch run)."""
    path = manifest_path(doc_id)
    if not path.exists():
        return False
    try:
        m = yaml.safe_load(path.read_text())
        for entry in m["files"]:
            f = file_location(doc_id, entry)
            if not f.exists():
                return False
            if verify_hashes and sha256_file(f) != entry["sha256"]:
                return False
        return True
    except Exception:
        return False


def store_bytes(doc_id: str, name: str, data: bytes, role: str) -> dict:
    """Write a file under the size policy; return its manifest files[] entry."""
    stored = "corpus" if len(data) <= _limit(doc_id) or role == "extracted" else "cache"
    base = doc_dir(doc_id) if stored == "corpus" else cache_dir(doc_id)
    base.mkdir(parents=True, exist_ok=True)
    path = base / name
    path.write_bytes(data)
    return {
        "name": name,
        "role": role,
        "sha256": sha256_file(path),
        "size": len(data),
        "stored": stored,
    }


def place_downloaded(doc_id: str, name: str, tmp: Path, sha256: str, size: int, role: str) -> dict:
    """Move an already-downloaded file into corpus or cache per the size policy."""
    stored = "corpus" if size <= _limit(doc_id) else "cache"
    base = doc_dir(doc_id) if stored == "corpus" else cache_dir(doc_id)
    base.mkdir(parents=True, exist_ok=True)
    tmp.replace(base / name)
    return {"name": name, "role": role, "sha256": sha256, "size": size, "stored": stored}


def _limit(doc_id: str) -> int:
    return min(config.RAW_COMMIT_EXCEPTIONS.get(doc_id, config.RAW_COMMIT_MAX_BYTES), 90 * 1024 * 1024)


def base_manifest(doc_id: str, *, source: str, tier: str, doc_type: str, url: str,
                  fetcher: str, entity_ids: list[str], title: str = "", **extra) -> dict:
    m = {
        "doc_id": doc_id,
        "source": source,
        "source_tier": tier,
        "doc_type": doc_type,
        "title": title,
        "url": url,
        "retrieved_at": now_iso(),
        "entity_ids": entity_ids,
        "fetcher": fetcher,
        "files": [],
    }
    m.update(extra)
    return m


def iter_manifests():
    """Yield (doc_id, manifest) for every doc in the corpus."""
    for path in sorted(config.CORPUS.glob("*/*/manifest.yaml")):
        m = yaml.safe_load(path.read_text())
        yield m["doc_id"], m
