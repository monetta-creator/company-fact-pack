"""EDGAR helpers: submissions pagination, archive URL building, filing index."""

from __future__ import annotations

from . import http


def pad_cik(cik: str | int) -> str:
    return str(int(cik)).zfill(10)


def submissions_all(cik: str) -> list[dict]:
    """Every filing for a CIK: walks filings.recent plus every paginated page in
    filings.files (the recent window only holds ~1000 items)."""
    cik = pad_cik(cik)
    root = http.get_json(f"https://data.sec.gov/submissions/CIK{cik}.json")
    batches = [root["filings"]["recent"]]
    for extra in root["filings"].get("files", []):
        batches.append(http.get_json(f"https://data.sec.gov/submissions/{extra['name']}"))
    out = []
    for b in batches:
        n = len(b["accessionNumber"])
        for i in range(n):
            out.append(
                {
                    "accession": b["accessionNumber"][i],
                    "form": b["form"][i],
                    "filing_date": b["filingDate"][i],
                    "report_date": b.get("reportDate", [""] * n)[i] or None,
                    "primary_doc": b.get("primaryDocument", [""] * n)[i],
                    "primary_desc": b.get("primaryDocDescription", [""] * n)[i],
                    "items": b.get("items", [""] * n)[i],
                    "size": b.get("size", [0] * n)[i],
                }
            )
    return out


def archive_url(cik: str, accession: str, filename: str) -> str:
    acc = accession.replace("-", "")
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/{filename}"


def filing_index(cik: str, accession: str) -> list[dict]:
    """Files in a filing: [{name, size, type?}] from the archive index.json."""
    acc = accession.replace("-", "")
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc}/index.json"
    idx = http.get_json(url)
    return [
        {"name": it["name"], "size": int(it.get("size") or 0), "type": it.get("type", "")}
        for it in idx["directory"]["item"]
        if it.get("name") and not it["name"].endswith("/")
    ]


def companyfacts_url(cik: str) -> str:
    return f"https://data.sec.gov/api/xbrl/companyfacts/CIK{pad_cik(cik)}.json"
