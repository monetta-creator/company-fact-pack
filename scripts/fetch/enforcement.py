"""Enforcement actions: Fed enforcement CSV (structured) + curated agency documents.

The Fed publishes a CSV of all enforcement actions; rows naming Capital One/Discover
are kept and their order PDFs fetched. OCC/CFPB lack a clean bulk endpoint — a curated
candidate list covers the known anchors; unreachable items are quarantined, never fatal.
"""

from __future__ import annotations

import csv
import io
import re

from factpack import manifest
from factpack.http import download, get
from factpack.manifest import doc_dir
from factpack.runlog import RunLog, run_isolated

FETCHER = "enforcement v1"
FED_CSV = "https://www.federalreserve.gov/supervisionreg/files/enforcementactions.csv"
NAME_RE = re.compile(r"capital one|discover (financial|bank)", re.I)

# Known anchors with stable agency URLs; each is attempted and quarantined on failure.
CURATED = [
    # (slug, url, title, entity_ids)
    (
        "occ-2020-aml-consent-order-cobna",
        "https://www.occ.gov/static/enforcement-actions/ea2020-056.pdf",
        "OCC consent order 2020 (Capital One, N.A. - AML/BSA)",
        ["cof"],
    ),
    (
        "occ-2019-breach-related",
        "https://www.occ.gov/static/enforcement-actions/ea2020-055.pdf",
        "OCC civil money penalty 2020 (2019 data breach)",
        ["cof"],
    ),
]


def save_doc(doc_id: str, url: str, title: str, entity_ids: list[str], doc_type: str, log: RunLog) -> None:
    if manifest.already_fetched(doc_id):
        log.count("skipped")
        return
    name = re.sub(r"[^A-Za-z0-9._-]", "_", url.rsplit("/", 1)[-1])[:120] or "document.pdf"
    tmp = doc_dir(doc_id) / (name + ".part")
    sha, size = download(url, tmp)
    entry = manifest.place_downloaded(doc_id, name, tmp, sha, size, "raw")
    dest = manifest.file_location(doc_id, entry)
    if name.lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader

            text = "\n".join((p.extract_text() or "") for p in PdfReader(str(dest)).pages)
        except Exception as e:  # noqa: BLE001
            text = f"(pdf text extraction failed: {e})"
    else:
        from factpack import textextract

        text, _ = textextract.extract(dest.read_bytes())
    files = [entry, manifest.store_bytes(doc_id, "extracted.txt", text.encode(), "extracted")]
    m = manifest.base_manifest(
        doc_id, source="enforcement", tier="A", doc_type=doc_type,
        url=url, fetcher=FETCHER, entity_ids=entity_ids, title=title,
    )
    m["files"] = files
    manifest.write(m)
    log.count("fetched")


def main() -> None:
    def run(log: RunLog) -> None:
        # 1) Fed enforcement CSV -> matching rows -> order PDFs
        try:
            raw = get(FED_CSV).text
            rows = [r for r in csv.DictReader(io.StringIO(raw)) if NAME_RE.search(str(r))]
            log.note(f"Fed CSV: {len(rows)} matching rows")
            # keep the row data itself as one corpus doc
            doc_id = "enforcement/fed-actions-index"
            if not manifest.already_fetched(doc_id):
                buf = io.StringIO()
                if rows:
                    w = csv.DictWriter(buf, fieldnames=rows[0].keys())
                    w.writeheader()
                    w.writerows(rows)
                files = [
                    manifest.store_bytes(doc_id, "fed_actions_slice.csv", buf.getvalue().encode(), "raw"),
                    manifest.store_bytes(
                        doc_id, "extracted.txt",
                        ("Federal Reserve enforcement actions naming Capital One/Discover:\n\n"
                         + "\n".join(
                             " | ".join(f"{k}: {v}" for k, v in r.items() if v) for r in rows
                         )).encode(),
                        "extracted",
                    ),
                ]
                m = manifest.base_manifest(
                    doc_id, source="enforcement", tier="A", doc_type="enforcement-index",
                    url=FED_CSV, fetcher=FETCHER, entity_ids=["cof", "dfs"],
                    title="Fed enforcement actions index (COF/Discover rows)",
                )
                m["files"] = files
                m["meta"] = {"rows": len(rows)}
                manifest.write(m)
                log.count("fetched")
            for r in rows:
                url = next((v for k, v in r.items() if v and str(v).lower().endswith(".pdf")), None)
                if not url:
                    continue
                if url.startswith("/"):
                    url = "https://www.federalreserve.gov" + url
                slug = re.sub(r"[^a-z0-9]+", "-", url.rsplit("/", 1)[-1].lower())[:80]
                try:
                    save_doc(f"enforcement/fed-{slug}", url, f"Fed enforcement order {slug}",
                             ["cof"] if "capital" in str(r).lower() else ["dfs"], "consent-order", log)
                except Exception as e:  # noqa: BLE001
                    log.count("failed")
                    log.note(f"fed order {slug}: {e}")
        except Exception as e:  # noqa: BLE001
            log.note(f"Fed CSV failed: {e}")

        # 2) curated agency documents
        for slug, url, title, ents in CURATED:
            try:
                save_doc(f"enforcement/{slug}", url, title, ents, "consent-order", log)
            except Exception as e:  # noqa: BLE001
                log.count("failed")
                log.note(f"{slug}: {e}")

    run_isolated("fetch.enforcement", run)


if __name__ == "__main__":
    main()
