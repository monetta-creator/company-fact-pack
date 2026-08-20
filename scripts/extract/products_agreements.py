"""CFPB card agreement PDFs -> effective-dated product records (model-assisted).

HUMAN GATE (rule 3 / D9): refuses to run on main; writes epistemic_status: draft on a
draft/* branch. Effective dating comes from quarter presence across the sampled ZIPs.
"""

from __future__ import annotations

import datetime as dt
import re

import yaml

from factpack import config, manifest as mlib, model
from factpack.runlog import RunLog, run_isolated
from scripts.extract.entity_spine import require_draft_branch, slugify

SECTION_RE = re.compile(r"=== AGREEMENT ([^/]+) / (.+?) ===")
BATCH = 8
TERMS_SCHEMA = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "product_name": {"type": "string"},
            "purchase_apr": {"type": "string"},
            "annual_fee": {"type": "string"},
            "late_fee": {"type": "string"},
            "foreign_transaction_fee": {"type": "string"},
            "rewards": {"type": "string"},
        },
        "required": ["key", "product_name"],
        "additionalProperties": False,
    },
}


def quarter_date(label: str, end: bool) -> str:
    y, q = int(label[:4]), int(label[-1])
    month = q * 3
    return f"{y}-{month:02d}-28" if end else f"{y}-{month - 2:02d}-01"


def main() -> None:
    require_draft_branch()

    def run(log: RunLog) -> None:
        today = dt.date.today().isoformat()
        # sections[(quarter, issuer, filename)] = text
        sections: dict[tuple[str, str, str], str] = {}
        for doc_id, m in mlib.iter_manifests():
            if m["source"] != "cfpb-agreements":
                continue
            quarter = m["meta"]["quarter"]
            text = (mlib.doc_dir(doc_id) / "extracted.txt").read_text(errors="replace")
            marks = list(SECTION_RE.finditer(text))
            for i, mt in enumerate(marks):
                end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
                sections[(quarter, mt.group(1).strip(), mt.group(2).strip())] = text[mt.start():end]
        log.note(f"{len(sections)} agreement sections across quarters")
        if not sections:
            return

        quarters = sorted({q for q, _, _ in sections})
        latest = quarters[-1]
        latest_items = [(k, v) for k, v in sections.items() if k[0] == latest]

        def extract_batch(batch):
            listing = "\n\n".join(
                f"key: {i}\nissuer: {k[1]}\nfile: {k[2]}\ntext:\n{v[:2500]}"
                for i, (k, v) in batch
            )
            r = model.call(
                "Each item below is a credit card agreement (Schumer-box region included). "
                "Extract the marketed product/card name and pricing terms verbatim where "
                "present (ranges as printed, e.g. '19.99% - 29.99% variable'). Echo each "
                "item's key. Omit fields not stated.\n\n" + listing,
                feature="product_terms", schema=TERMS_SCHEMA,
            )
            return r.json

        indexed = list(enumerate(latest_items))
        batches = [indexed[i : i + BATCH] for i in range(0, len(indexed), BATCH)]
        try:
            results = model.map_calls(batches, extract_batch)
        except model.UsageLimitError:
            log.note("usage limit hit; partial product set (re-run to finish)")
            results = []

        (config.ROOT / "products").mkdir(exist_ok=True)
        written = 0
        for batch, result in zip(batches, results):
            if not result:
                continue
            by_key = {str(i): (k, v) for i, (k, v) in batch}
            for item in result:
                hit = by_key.get(str(item["key"]))
                if hit is None:
                    continue
                (quarter, issuer, filename), _ = hit
                entity = "cof" if re.search(r"capital", issuer, re.I) else "dfs"
                pid = slugify(f"{entity}-{item['product_name']}")
                if not pid:
                    continue
                path = config.ROOT / "products" / f"{pid}.yaml"
                if path.exists():
                    continue
                # effective range: first/last sampled quarter where this filename family appears
                name_root = filename[:20].lower()
                qs = sorted({q for (q, iss, fn) in sections if fn[:20].lower() == name_root})
                doc_ref = f"cfpb-agreements/{quarter}"
                product = {
                    "product_id": pid,
                    "issuer_entity_id": entity,
                    "name": item["product_name"][:120],
                    "agreement_doc_id": doc_ref,
                    "effective_from": quarter_date(qs[0], end=False),
                    "effective_to": None if qs[-1] == latest else quarter_date(qs[-1], end=True),
                    "terms": {
                        k: v
                        for k, v in item.items()
                        if k in ("purchase_apr", "annual_fee", "late_fee",
                                 "foreign_transaction_fee", "rewards") and v
                    },
                    "epistemic_status": "draft",
                    "as_of": today,
                    "sources": [{"doc_id": doc_ref, "locator": filename}],
                }
                path.write_text(yaml.safe_dump(product, sort_keys=False, allow_unicode=True))
                written += 1
        log.ok(products_written=written)

    run_isolated("extract.products", run)


if __name__ == "__main__":
    main()
