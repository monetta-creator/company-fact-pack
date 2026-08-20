"""CFPB credit card agreement database: quarterly ZIPs -> COF + Discover issuer PDFs.

Sampling policy (config flag FULL=1 to override): one quarter per year 2016-2023,
then every quarter 2024+. Quarterly ZIPs are industry-wide (hundreds of MB) and stay
in build/cache; only the target issuers' PDFs + extracted text are committed.
"""

from __future__ import annotations

import os
import re
import zipfile
from pathlib import Path

from factpack import config, manifest
from factpack.http import download, get
from factpack.runlog import RunLog, run_isolated

FETCHER = "cfpb_agreements v1"
LANDING = "https://www.consumerfinance.gov/credit-cards/agreements/archive/"
ISSUER_RE = re.compile(r"capital\s*one|discover", re.I)
SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def zip_links() -> dict[str, str]:
    """quarter label 'YYYY_QN' -> URL, scraped from the landing page."""
    html = get(LANDING).text
    out: dict[str, str] = {}
    for href in re.findall(r'href="([^"]+\.zip)"', html, re.I):
        mt = re.search(r"(20\d{2})[_\- ]?Q([1-4])", href, re.I)
        if mt:
            url = href if href.startswith("http") else "https://files.consumerfinance.gov" + href
            out[f"{mt.group(1)}_Q{mt.group(2)}"] = url
    return out


def wanted_quarters(available: list[str]) -> list[str]:
    if os.environ.get("FULL") == "1":
        return available
    picks: list[str] = []
    by_year: dict[int, list[str]] = {}
    for label in sorted(available):
        by_year.setdefault(int(label[:4]), []).append(label)
    for year, labels in sorted(by_year.items()):
        if year >= 2024:
            picks.extend(labels)
        elif 2016 <= year <= 2023:
            q4 = [x for x in labels if x.endswith("Q4")]
            picks.append(q4[0] if q4 else labels[-1])
    return sorted(set(picks))


def fetch_quarter(label: str, url: str, log: RunLog) -> None:
    doc_id = f"cfpb-agreements/{label}"
    if manifest.already_fetched(doc_id):
        log.count("skipped")
        return
    cached = config.CACHE / "cfpb-agreements" / f"{label}.zip"
    if not cached.exists():
        download(url, cached)
    files_meta = []
    texts = []
    issuers_seen = set()
    with zipfile.ZipFile(cached) as zf:
        for name in zf.namelist():
            parts = [p for p in name.split("/") if p]
            if len(parts) < 2 or not name.lower().endswith(".pdf"):
                continue
            issuer = parts[-2]
            if not ISSUER_RE.search(issuer):
                continue
            issuers_seen.add(issuer)
            data = zf.read(name)
            safe = SAFE_RE.sub("_", f"{issuer}__{parts[-1]}")[:180]
            files_meta.append(manifest.store_bytes(doc_id, safe, data, "raw"))
            texts.append(f"\n\n=== AGREEMENT {issuer} / {parts[-1]} ===\n\n" + pdf_text(data))
    if not files_meta:
        log.note(f"{label}: no COF/Discover agreements in ZIP")
        log.count("empty")
        return
    extracted = "".join(texts)
    files_meta.append(manifest.store_bytes(doc_id, "extracted.txt", extracted.encode(), "extracted"))
    m = manifest.base_manifest(
        doc_id, source="cfpb-agreements", tier="A", doc_type="card-agreements",
        url=url, fetcher=FETCHER, entity_ids=["cof", "dfs"],
        title=f"CFPB card agreements {label} (COF + Discover)",
    )
    m["period_end"] = f"{label[:4]}-{'03 06 09 12'.split()[int(label[-1]) - 1]}-28"
    m["files"] = files_meta
    m["meta"] = {"quarter": label, "issuers": sorted(issuers_seen), "pdfs": len(files_meta) - 1}
    manifest.write(m)
    cached.unlink(missing_ok=True)  # industry-wide ZIP: provenance is the manifest URL; disk is finite
    log.count("fetched")


def pdf_text(data: bytes) -> str:
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception as e:  # noqa: BLE001 — scanned/broken PDFs still get committed raw
        return f"(pdf text extraction failed: {e})"


def main() -> None:
    def run(log: RunLog) -> None:
        links = zip_links()
        log.note(f"{len(links)} quarterly ZIPs listed")
        for label in wanted_quarters(list(links)):
            try:
                fetch_quarter(label, links[label], log)
            except Exception as e:  # noqa: BLE001
                log.count("failed")
                log.note(f"{label}: {e}")

    run_isolated("fetch.cfpb_agreements", run)


if __name__ == "__main__":
    main()
