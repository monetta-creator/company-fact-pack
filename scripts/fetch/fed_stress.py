"""Fed stress-test disclosures (DFAST results) 2016-2025: scrape per-year links, fetch PDFs/CSVs."""

from __future__ import annotations

import re

from factpack import manifest
from factpack.http import download, get
from factpack.manifest import doc_dir
from factpack.runlog import RunLog, run_isolated

FETCHER = "fed_stress v1"
LANDING = "https://www.federalreserve.gov/supervisionreg/stress-tests-capital-planning.htm"
FED = "https://www.federalreserve.gov"
LINK_RE = re.compile(r'href="([^"]*(?:dfast|stress-test)[^"]*20(1[6-9]|2[0-6])[^"]*\.(pdf|csv))"', re.I)
ALT_RE = re.compile(r'href="([^"]*20(1[6-9]|2[0-6])[^"]*dfast[^"]*\.(pdf|csv))"', re.I)


def pdf_or_csv_text(path, name: str) -> str:
    if name.lower().endswith(".csv"):
        return path.read_text(errors="replace")
    try:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:  # noqa: BLE001
        return f"(pdf text extraction failed: {e})"


def main() -> None:
    def run(log: RunLog) -> None:
        # per-year result pages: dfa-stress-tests-YYYY.htm (2020+), dfast-YYYY.htm (<=2019)
        pages = [f"/supervisionreg/dfa-stress-tests-{y}.htm" for y in range(2020, 2027)]
        pages += [f"/supervisionreg/dfast-{y}.htm" for y in range(2016, 2020)]
        urls: set[str] = set()
        for page in pages:
            try:
                sub = get(FED + page, retries=1).text
                found = {m[0] for m in LINK_RE.findall(sub)} | {m[0] for m in ALT_RE.findall(sub)}
                found |= set(re.findall(r'href="(/publications/files/[^"]+\.(?:pdf|csv))"', sub, re.I))
                found |= set(re.findall(r'href="(/supervisionreg/files/[^"]+\.(?:pdf|csv|zip))"', sub, re.I))
                urls |= found
            except Exception as e:  # noqa: BLE001
                log.note(f"subpage {page}: {e}")
        urls = {u for u in urls if re.search(r"dfast|stress|scenario", u, re.I)}
        log.note(f"{len(urls)} candidate DFAST files")
        for url in sorted(urls):
            full = url if url.startswith("http") else FED + url
            name = full.rsplit("/", 1)[-1]
            doc_id = f"fed-stress/{re.sub(r'[^A-Za-z0-9._-]', '_', name)[:120]}"
            if manifest.already_fetched(doc_id):
                log.count("skipped")
                continue
            try:
                tmp = doc_dir(doc_id) / (name + ".part")
                sha, size = download(full, tmp)
                entry = manifest.place_downloaded(doc_id, name, tmp, sha, size, "raw")
                dest = manifest.file_location(doc_id, entry)
                text = pdf_or_csv_text(dest, name)
                files = [entry, manifest.store_bytes(doc_id, "extracted.txt", text.encode(), "extracted")]
                m = manifest.base_manifest(
                    doc_id, source="fed-stress", tier="A", doc_type="dfast",
                    url=full, fetcher=FETCHER, entity_ids=["cof"],
                    title=f"Fed stress test file {name}",
                )
                m["files"] = files
                manifest.write(m)
                log.count("fetched")
            except Exception as e:  # noqa: BLE001
                log.count("failed")
                log.note(f"{name}: {e}")

    run_isolated("fetch.fed_stress", run)


if __name__ == "__main__":
    main()
