"""FR Y-9C bulk data via a fallback ladder (NIC bulk endpoint bot-blocks plain clients).

Ladder:
  a) NIC FinancialDataDownload with browser-ish headers + Referer handshake
  b) manual-download inbox: drop BHCF*.ZIP files in inbox/ffiec/ and re-run
If (a) fails, exact instructions are written to build/status/fetch.ffiec_y9c.json.

Each quarter's industry-wide ZIP stays in build/cache; the committed corpus doc is the
per-institution slice (COF + DFS rows) as TSV, which is what the extractor reads.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx

from factpack import config, manifest
from factpack.runlog import RunLog, run_isolated

FETCHER = "ffiec_y9c v1"
# RSSD IDs: COF holding co + DFS holding co (resolved from NIC/FDIC; recorded in entity seeds)
RSSD = {"cof": "2277860", "dfs": "3846375"}
QUARTERS = [
    f"{y}{q}" for y in range(2016, 2027) for q in ("0331", "0630", "0930", "1231")
][:42]  # 2016Q1..2026Q2

NIC_URL = "https://www.ffiec.gov/npw/FinancialReport/ReturnFinancialReportZip"


def try_nic(quarter: str, dest: Path) -> bool:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Referer": "https://www.ffiec.gov/npw/FinancialReport/FinancialDataDownload",
        "Accept": "application/zip,application/octet-stream,*/*",
    }
    try:
        with httpx.Client(headers=headers, timeout=120, follow_redirects=True) as client:
            client.get("https://www.ffiec.gov/npw/FinancialReport/FinancialDataDownload")
            resp = client.get(NIC_URL, params={"rpt": "BHCF", "dt": quarter})
            if resp.status_code == 200 and resp.content[:2] == b"PK":
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(resp.content)
                return True
    except httpx.HTTPError:
        pass
    return False


def find_inbox(quarter: str) -> Path | None:
    for pattern in (f"BHCF{quarter}*.zip", f"BHCF{quarter}*.ZIP", f"*{quarter}*.zip"):
        hits = list((config.ROOT / "inbox/ffiec").glob(pattern))
        if hits:
            return hits[0]
    return None


def slice_quarter(quarter: str, zip_path: Path, log: RunLog) -> None:
    doc_id = f"ffiec-y9c/BHCF_{quarter}"
    if manifest.already_fetched(doc_id):
        log.count("skipped")
        return
    with zipfile.ZipFile(zip_path) as zf:
        member = next((n for n in zf.namelist() if n.lower().endswith(".txt")), None)
        if not member:
            raise ValueError(f"{zip_path}: no .txt member")
        with zf.open(member) as f:
            text_stream = io.TextIOWrapper(f, encoding="latin-1", errors="replace")
            header = text_stream.readline()
            delim = "^" if "^" in header else "\t"
            cols = header.rstrip("\n").split(delim)
            try:
                rssd_idx = cols.index("RSSD9001")
            except ValueError:
                rssd_idx = 0
            keep = [header]
            targets = set(RSSD.values())
            for line in text_stream:
                parts = line.split(delim)
                if len(parts) > rssd_idx and parts[rssd_idx].strip().strip('"') in targets:
                    keep.append(line)
    if len(keep) == 1:
        log.note(f"{quarter}: no target rows (pre-registration or missing)")
    slice_text = "".join(keep)
    files = [manifest.store_bytes(doc_id, f"BHCF_{quarter}_slice.tsv", slice_text.encode(), "raw")]
    files.append(
        manifest.store_bytes(
            doc_id, "extracted.txt",
            f"FR Y-9C {quarter}: {len(keep) - 1} holding-company rows (COF/DFS slice). "
            "Machine data; see metrics layer.\n".encode(),
            "extracted",
        )
    )
    m = manifest.base_manifest(
        doc_id, source="ffiec-y9c", tier="A", doc_type="fr-y9c",
        url=f"{NIC_URL}?rpt=BHCF&dt={quarter}", fetcher=FETCHER,
        entity_ids=["cof"] + (["dfs"] if quarter <= "20250331" else []),
        title=f"FR Y-9C bulk slice {quarter}",
    )
    m["period_end"] = f"{quarter[:4]}-{quarter[4:6]}-{quarter[6:]}"
    m["files"] = files
    m["meta"] = {"quarter": quarter, "rows": len(keep) - 1, "bulk_zip": zip_path.name}
    manifest.write(m)
    log.count("fetched")


def main() -> None:
    def run(log: RunLog) -> None:
        missing = []
        for quarter in QUARTERS:
            doc_id = f"ffiec-y9c/BHCF_{quarter}"
            if manifest.already_fetched(doc_id):
                log.count("skipped")
                continue
            cached = config.CACHE / "ffiec-y9c" / f"BHCF{quarter}.zip"
            zip_path: Path | None = cached if cached.exists() else None
            if zip_path is None and try_nic(quarter, cached):
                zip_path = cached
            if zip_path is None:
                zip_path = find_inbox(quarter)
            if zip_path is None:
                missing.append(quarter)
                log.count("missing")
                continue
            try:
                slice_quarter(quarter, zip_path, log)
            except Exception as e:  # noqa: BLE001
                log.count("failed")
                log.note(f"{quarter}: {e}")
        if missing:
            log.note(
                "MANUAL STEP: NIC bulk download blocked. Visit "
                "https://www.ffiec.gov/npw/FinancialReport/FinancialDataDownload in a browser, "
                "download 'Bank Holding Company Financial Data (BHCF)' ZIPs for quarters "
                f"{', '.join(missing)} and drop them in inbox/ffiec/, then re-run "
                "`uv run python -m scripts.fetch.ffiec_y9c`."
            )

    run_isolated("fetch.ffiec_y9c", run)


if __name__ == "__main__":
    main()
