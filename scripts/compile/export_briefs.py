"""Export merged briefs as one JSON for downstream consumers (the AI Atlas).

Only non-draft briefs are included — the human gate (rule 3) travels with the export.
Deterministic (no timestamps), so the committed file only changes when briefs do.
Consumers fetch one URL:
  https://raw.githubusercontent.com/monetta-creator/company-fact-pack/main/export/briefs.json
Each brief body cites [src:<doc_id>#section]; doc_urls maps every cited doc_id to its
original public source URL, so citations remain checkable outside this repo.
"""

from __future__ import annotations

import json
import re

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated
from scripts.validate.schema_check import iter_brief_paths, parse_frontmatter

SRC_RE = re.compile(r"\[src:([^\]#\s]+)(#[^\]]*)?\]")
OUT = config.ROOT / "export" / "briefs.json"


def main() -> None:
    def run(log: RunLog) -> None:
        briefs = []
        cited: set[str] = set()
        for path in iter_brief_paths():
            fm = parse_frontmatter(path.read_text())
            if fm["epistemic_status"] == "draft":
                log.count("drafts_excluded")
                continue
            body = path.read_text().split("---", 2)[2].strip()
            doc_ids = sorted({m[0] for m in SRC_RE.findall(body)}
                             | {s["doc_id"] for s in fm.get("sources", [])})
            cited.update(doc_ids)
            briefs.append({
                "id": fm["id"],
                "title": fm["title"],
                "entities": fm["entities"],
                "as_of": fm["as_of"],
                "review_by": fm["review_by"],
                "epistemic_status": fm["epistemic_status"],
                "sources": doc_ids,
                "body": body,
            })
            log.count("exported")
        doc_urls = {}
        for doc_id, m in mlib.iter_manifests():
            if doc_id in cited:
                doc_urls[doc_id] = m["url"]
        OUT.parent.mkdir(exist_ok=True)
        OUT.write_text(json.dumps({
            "dataset": "company-fact-pack",
            "subject": "Capital One Financial Corporation",
            "license_note": "All content derives from public sources; each doc_id resolves "
                            "to its origin URL in doc_urls.",
            "brief_count": len(briefs),
            "briefs": sorted(briefs, key=lambda b: b["id"]),
            "doc_urls": doc_urls,
        }, indent=1, ensure_ascii=False))
        log.ok(briefs=len(briefs), cited_docs=len(doc_urls))

    run_isolated("compile.export_briefs", run)


if __name__ == "__main__":
    main()
