"""Fetch EDGAR filings for one entity into corpus/edgar-<entity>/.

Usage:
  python -m scripts.fetch.edgar_filings --entity cof --forms 10-K,10-Q,8-K,DEF14A,S-4,425 \
      --since 2016-01-01 [--until 2026-12-31]

Idempotent: filings whose manifest + files already exist are skipped.
Downloads the primary document plus EX-21/EX-99 exhibits (subsidiaries lists,
press releases, servicer reports); writes one extracted.txt per filing.
"""

from __future__ import annotations

import argparse
import re

from factpack import config, edgar, manifest, textextract
from factpack.http import download
from factpack.runlog import RunLog, run_isolated

FETCHER = "edgar_filings v1"
EXHIBIT_RE = re.compile(r"(?:^|[-_.a-z])ex[-_.]?(?:21|99)", re.I)
KEEP_EXT = (".htm", ".html", ".txt")
MAX_FILE_BYTES = 60 * 1024 * 1024

# forms that carry exhibits worth pulling (press releases, servicer reports, subsidiaries)
EXHIBIT_FORMS = {"8-K", "8-K/A", "10-D", "10-K", "10-K/A"}


def norm_form(form: str) -> str:
    return form.replace(" ", "").replace("/", "")


def wanted(form: str, targets: set[str]) -> bool:
    base = form.removesuffix("/A")
    return norm_form(base) in targets or norm_form(form) in targets


def fetch_filing(entity: str, cik: str, f: dict, log: RunLog) -> None:
    form_slug = norm_form(f["form"])
    doc_id = f"edgar-{entity}/{form_slug}_{f['filing_date']}_{f['accession']}"
    if manifest.already_fetched(doc_id):
        log.count("skipped")
        return

    files_meta = []
    texts: list[str] = []

    def grab(name: str, role: str) -> None:
        url = edgar.archive_url(cik, f["accession"], name)
        tmp = manifest.doc_dir(doc_id) / (name.replace("/", "_") + ".part")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        sha, size = download(url, tmp)
        entry = manifest.place_downloaded(
            doc_id, name.replace("/", "_"), tmp, sha, size, role
        )
        files_meta.append(entry)
        if name.lower().endswith(KEEP_EXT):
            data = manifest.file_location(doc_id, entry).read_bytes()
            if textextract.is_probably_html(data, name):
                text, method = textextract.extract(data)
            else:
                text, method = data.decode("utf-8", errors="replace"), "plain"
            header = "" if role == "raw" else f"\n\n=== EXHIBIT {name} ===\n\n"
            texts.append(header + text)
            methods.append(method)

    methods: list[str] = []
    primary = f["primary_doc"]
    if primary:
        grab(primary, "raw")
    if f["form"] in EXHIBIT_FORMS or not primary:
        try:
            for item in edgar.filing_index(cik, f["accession"]):
                name = item["name"]
                if name == primary or not name.lower().endswith(KEEP_EXT):
                    continue
                if item["size"] and item["size"] > MAX_FILE_BYTES:
                    continue
                if EXHIBIT_RE.search(name) or (not primary and name.endswith(".txt")):
                    grab(name, "exhibit")
        except Exception as e:  # noqa: BLE001 — exhibits are best-effort
            log.note(f"{doc_id}: exhibit listing failed: {e}")

    if not files_meta:
        log.count("empty")
        return

    extracted = "".join(texts) or "(no extractable text)\n"
    files_meta.append(manifest.store_bytes(doc_id, "extracted.txt", extracted.encode(), "extracted"))

    m = manifest.base_manifest(
        doc_id,
        source=f"edgar-{entity}",
        tier="A",
        doc_type=f["form"],
        url=edgar.archive_url(cik, f["accession"], primary or ""),
        fetcher=FETCHER,
        entity_ids=[entity],
        title=f"{f['form']} filed {f['filing_date']}" + (f" (period {f['report_date']})" if f["report_date"] else ""),
    )
    m["filed_date"] = f["filing_date"]
    m["period_end"] = f["report_date"]
    m["extraction_method"] = "+".join(sorted(set(methods))) or None
    m["files"] = files_meta
    m["meta"] = {"accession": f["accession"], "form": f["form"], "items": f["items"]}
    manifest.write(m)
    log.count("fetched")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--entity", required=True, choices=sorted(config.CIK))
    ap.add_argument("--forms", required=True, help="comma-separated; amendments (/A) included automatically")
    ap.add_argument("--since", default="1994-01-01")
    ap.add_argument("--until", default="2099-12-31")
    args = ap.parse_args()

    cik = config.CIK[args.entity]
    targets = {norm_form(x) for x in args.forms.split(",")}

    def run(log: RunLog) -> None:
        filings = [
            f
            for f in edgar.submissions_all(cik)
            if wanted(f["form"], targets) and args.since <= f["filing_date"] <= args.until
        ]
        log.note(f"{len(filings)} filings match for {args.entity}")
        for f in filings:
            try:
                fetch_filing(args.entity, cik, f, log)
            except Exception as e:  # noqa: BLE001 — one bad filing never stops the sweep
                log.count("failed")
                log.note(f"{f['form']} {f['accession']}: {e}")

    run_isolated(f"fetch.edgar_{args.entity}", run)


if __name__ == "__main__":
    main()
