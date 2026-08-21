"""Ingest user-provided earnings-call transcripts from inbox/transcripts/.

Earnings transcripts are paywalled, so this run fetches none. Drop a transcript file
(txt/html/pdf) plus a YAML sidecar `<name>.yaml` with {date, quarter, source_desc}
into inbox/transcripts/ and re-run. url is recorded as 'user-provided' (tier B).
"""

from __future__ import annotations

import re

import yaml

from factpack import config, manifest, textextract
from factpack.runlog import RunLog, run_isolated

FETCHER = "transcripts_stub v1"


def main() -> None:
    def run(log: RunLog) -> None:
        inbox = config.ROOT / "inbox/transcripts"
        inbox.mkdir(parents=True, exist_ok=True)
        for sidecar in sorted(inbox.glob("*.yaml")):
            meta = yaml.safe_load(sidecar.read_text())
            body = next(
                (p for p in inbox.glob(sidecar.stem + ".*") if p.suffix != ".yaml"), None
            )
            if body is None:
                log.note(f"{sidecar.name}: no matching transcript file")
                continue
            quarter = str(meta.get("quarter", "unknown"))
            doc_id = f"transcripts/{re.sub(r'[^A-Za-z0-9_-]', '_', quarter)}_{sidecar.stem}"
            if manifest.already_fetched(doc_id):
                log.count("skipped")
                continue
            data = body.read_bytes()
            if body.suffix.lower() == ".pdf":
                import io

                from pypdf import PdfReader

                text = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
                method = "pypdf"
            elif textextract.is_probably_html(data, body.name):
                text, method = textextract.extract(data)
            else:
                text, method = data.decode("utf-8", errors="replace"), "plain"
            files = [
                manifest.store_bytes(doc_id, body.name, data, "raw"),
                manifest.store_bytes(doc_id, "extracted.txt", text.encode(), "extracted"),
            ]
            m = manifest.base_manifest(
                doc_id, source="transcripts", tier="B", doc_type="earnings-transcript",
                url=meta.get("url", "user-provided"), fetcher=FETCHER,
                entity_ids=[meta.get("entity", "cof")],
                title=f"Earnings call transcript {quarter} ({meta.get('source_desc', 'user-provided')})",
            )
            m["filed_date"] = str(meta.get("date")) if meta.get("date") else None
            m["extraction_method"] = method
            m["files"] = files
            m["meta"] = {"quarter": quarter, "source_desc": meta.get("source_desc", "")}
            manifest.write(m)
            log.count("fetched")

    run_isolated("fetch.transcripts", run)


if __name__ == "__main__":
    main()
