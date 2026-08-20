"""HTML -> text with a three-tier fallback chain (old EDGAR HTML is messy).

Tables are serialized as atomic [TABLE]...[/TABLE] blocks (rows joined with ' | ')
so the chunker can keep each table whole (D1 / anti-pattern: never split a table).
The method that succeeded is recorded in the manifest as extraction_method.
"""

from __future__ import annotations

import re

BLOCK_TAGS = {
    "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article", "blockquote", "pre",
}


def _norm(s: str) -> str:
    return re.sub(r"[ \t\xa0  ]+", " ", s).strip()


def _table_text(table) -> str:
    rows = []
    for tr in table.iter("tr"):
        cells = []
        for cell in tr.iter("td", "th"):
            cells.append(_norm(" ".join(cell.itertext())))
        if any(cells):
            rows.append(" | ".join(cells))
    if len(rows) < 2:
        return "\n".join(rows)  # 0/1-row tables are layout artifacts, render inline
    return "[TABLE]\n" + "\n".join(rows) + "\n[/TABLE]"


def _render_lxml(el, out: list[str]) -> None:
    tag = el.tag if isinstance(el.tag, str) else ""
    if tag == "table":
        # Nested layout tables: only serialize tables that contain no child table.
        if el.find(".//table") is None:
            out.append("\n" + _table_text(el) + "\n")
            if el.tail and el.tail.strip():
                out.append(_norm(el.tail) + " ")
            return
    if tag.lower() in BLOCK_TAGS:
        out.append("\n")
    if el.text and el.text.strip():
        out.append(_norm(el.text) + " ")
    for child in el:
        _render_lxml(child, out)
    if tag.lower() in BLOCK_TAGS:
        out.append("\n")
    if el.tail and el.tail.strip():
        out.append(_norm(el.tail) + " ")


def _via_lxml(data: bytes) -> str:
    from lxml import html as lhtml

    doc = lhtml.fromstring(data)
    for bad in doc.xpath("//script|//style|//head"):
        bad.drop_tree()
    out: list[str] = []
    _render_lxml(doc, out)
    return "".join(out)


def _via_bs4(data: bytes) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(data, "html.parser")
    for bad in soup(["script", "style", "head"]):
        bad.decompose()
    return soup.get_text(separator="\n")


def _via_strip(data: bytes) -> str:
    import html as htmllib

    text = data.decode("utf-8", errors="replace")
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = re.sub(r"<[^>]+>", "\n", text)
    return htmllib.unescape(text)


def _cleanup(text: str) -> str:
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"


def extract(data: bytes) -> tuple[str, str]:
    """Returns (text, method). Never raises — the last resort always produces something."""
    for method, fn in (("lxml", _via_lxml), ("bs4", _via_bs4), ("strip", _via_strip)):
        try:
            text = _cleanup(fn(data))
            if len(text) > 20:
                return text, method
        except Exception:  # noqa: BLE001 — fall through the chain
            continue
    return _cleanup(data.decode("utf-8", errors="replace")), "raw"


def is_probably_html(data: bytes, name: str = "") -> bool:
    if name.lower().endswith((".htm", ".html", ".xhtml")):
        return True
    head = data[:2048].lower()
    return b"<html" in head or b"<!doctype" in head or b"<div" in head or b"<table" in head
