"""Call Report bulk data (FFIEC CDR) — enrichment only; FDIC API is the primary bank-sub source.

The CDR bulk page is an ASPX form without stable direct URLs. This fetcher processes any
'FFIEC CDR Call Bulk*' ZIPs the user drops in inbox/ffiec/, slicing the three target banks
by RSSD. It never blocks the build; missing quarters are simply reported.
"""

from __future__ import annotations

import io
import zipfile

from factpack import config, manifest
from factpack.runlog import RunLog, run_isolated

FETCHER = "ffiec_call v1"
# bank-level RSSDs (also recorded in entity seeds; FDIC API carries FED_RSSD)
BANK_RSSD = {"cona": "112837", "cobna": "1160925", "discover-bank": "30810"}


def main() -> None:
    def run(log: RunLog) -> None:
        inbox = config.ROOT / "inbox/ffiec"
        inbox.mkdir(parents=True, exist_ok=True)
        zips = sorted(inbox.glob("*[Cc]all*.zip")) + sorted(inbox.glob("*[Cc]all*.ZIP"))
        if not zips:
            log.note(
                "No Call Report bulk ZIPs found. Optional: download 'Call Reports -- Single "
                "Period' bulk ZIPs from https://cdr.ffiec.gov/public/pws/downloadbulkdata.aspx "
                "into inbox/ffiec/ and re-run. FDIC API already covers primary bank-sub series."
            )
            return
        targets = set(BANK_RSSD.values())
        for zpath in zips:
            label = zpath.stem.replace(" ", "_")[:80]
            doc_id = f"ffiec-call/{label}"
            if manifest.already_fetched(doc_id):
                log.count("skipped")
                continue
            try:
                kept_parts = []
                with zipfile.ZipFile(zpath) as zf:
                    for member in zf.namelist():
                        if not member.lower().endswith(".txt"):
                            continue
                        with zf.open(member) as f:
                            tw = io.TextIOWrapper(f, encoding="latin-1", errors="replace")
                            header = tw.readline()
                            keep = [f"# {member}\n", header]
                            for line in tw:
                                first = line.split("\t", 1)[0].strip('"')
                                if first in targets:
                                    keep.append(line)
                            if len(keep) > 2:
                                kept_parts.append("".join(keep))
                if not kept_parts:
                    log.note(f"{label}: no target-bank rows")
                    log.count("empty")
                    continue
                slice_text = "\n".join(kept_parts)
                files = [
                    manifest.store_bytes(doc_id, f"{label}_slice.tsv", slice_text.encode(), "raw"),
                    manifest.store_bytes(
                        doc_id, "extracted.txt",
                        f"Call Report bulk slice {label} for target banks. Machine data.\n".encode(),
                        "extracted",
                    ),
                ]
                m = manifest.base_manifest(
                    doc_id, source="ffiec-call", tier="A", doc_type="call-report",
                    url="user-provided (CDR bulk download)", fetcher=FETCHER,
                    entity_ids=list(BANK_RSSD), title=f"Call Report slice {label}",
                )
                m["files"] = files
                manifest.write(m)
                log.count("fetched")
            except Exception as e:  # noqa: BLE001
                log.count("failed")
                log.note(f"{label}: {e}")

    run_isolated("fetch.ffiec_call", run)


if __name__ == "__main__":
    main()
