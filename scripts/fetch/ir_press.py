"""COF investor-relations press releases — best-effort RSS/newsroom sweep.

Material releases already land as 8-K exhibits (fetched via EDGAR), so this only adds
non-material PR history. Any failure is recorded and never blocks the build.
"""

from __future__ import annotations

import re

from factpack import manifest, textextract
from factpack.http import get
from factpack.runlog import RunLog, run_isolated

FETCHER = "ir_press v1"
FEEDS = [
    "https://investor.capitalone.com/rss/pressrelease.aspx",
    "https://www.capitalone.com/about/newsroom/rss/",
]


def main() -> None:
    def run(log: RunLog) -> None:
        items: list[tuple[str, str, str]] = []  # (date, title, link)
        for feed in FEEDS:
            try:
                xml = get(feed, retries=1).text
                for m in re.finditer(r"<item>(.*?)</item>", xml, re.S):
                    block = m.group(1)
                    title = _tag(block, "title")
                    link = _tag(block, "link")
                    date = _tag(block, "pubDate")
                    if title and link:
                        items.append((date, title, link))
                log.note(f"{feed}: {len(items)} items")
                if items:
                    break
            except Exception as e:  # noqa: BLE001
                log.note(f"{feed}: {e}")
        if not items:
            log.note("No reachable IR feed; material PRs are covered by 8-K exhibits.")
            return
        for date, title, link in items:
            slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
            doc_id = f"ir-press/{slug}"
            if manifest.already_fetched(doc_id):
                log.count("skipped")
                continue
            try:
                html = get(link, retries=1).content
                text, method = textextract.extract(html)
                files = [
                    manifest.store_bytes(doc_id, "release.html", html, "raw"),
                    manifest.store_bytes(doc_id, "extracted.txt", text.encode(), "extracted"),
                ]
                m = manifest.base_manifest(
                    doc_id, source="ir-press", tier="B", doc_type="press-release",
                    url=link, fetcher=FETCHER, entity_ids=["cof"], title=title,
                )
                m["extraction_method"] = method
                m["files"] = files
                m["meta"] = {"pub_date": date}
                manifest.write(m)
                log.count("fetched")
            except Exception as e:  # noqa: BLE001
                log.count("failed")
                log.note(f"{slug}: {e}")
    run_isolated("fetch.ir_press", run)


def _tag(block: str, tag: str) -> str:
    m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
    return re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1)).strip() if m else ""


if __name__ == "__main__":
    main()
