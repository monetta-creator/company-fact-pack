"""Section-aware chunking (D1). Retrieval quality is decided here.

- 10-K/10-Q: split on PART/ITEM headings; paragraphs packed to the token targets,
  never across item boundaries.
- 8-K: one section per item + each exhibit its own section.
- [TABLE]...[/TABLE] blocks are ATOMIC — one chunk regardless of size (anti-pattern:
  never split a table). A unit test asserts no chunk holds a partial table.
- chunk_id is content-addressed -> incremental enrich/index for free.
- Metadata (entities, doc type, period, tier) inherited from the manifest, never
  re-derived at query time.

Output: build/chunks.jsonl
"""

from __future__ import annotations

import hashlib
import json
import re

from factpack import config, manifest as mlib
from factpack.runlog import RunLog, run_isolated

ITEM_RE = re.compile(
    r"^\s*(PART [IVX]+|ITEM\s+\d{1,2}[A-C]?\.?)\s", re.I | re.M
)
EXHIBIT_RE = re.compile(r"^=== (EXHIBIT|AGREEMENT) (.+?) ===$", re.M)
TABLE_OPEN, TABLE_CLOSE = "[TABLE]", "[/TABLE]"

# doc types that are machine data, not prose — excluded from the text index (D3 keeps
# their numbers in the metric store)
SKIP_DOC_TYPES = {"xbrl-companyfacts", "fdic-financials", "fdic-sod", "complaints-csv",
                  "fr-y9c", "call-report"}


def toks(s: str) -> int:
    return max(1, len(s) // 4)


def split_sections(text: str, doc_type: str) -> list[tuple[str, str]]:
    """-> [(section_id, section_text)]"""
    sections: list[tuple[str, str]] = []
    # exhibits/agreements first: they delimit hard boundaries
    marks = list(EXHIBIT_RE.finditer(text))
    spans: list[tuple[str, str]] = []
    if marks:
        head = text[: marks[0].start()]
        if head.strip():
            spans.append(("main", head))
        for i, m in enumerate(marks):
            end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
            label = re.sub(r"[^A-Za-z0-9._-]+", "_", m.group(2))[:60]
            spans.append((f"ex_{label}", text[m.end():end]))
    else:
        spans = [("main", text)]

    for span_id, span_text in spans:
        if doc_type.startswith(("10-K", "10-Q", "DEF 14A", "S-4")):
            items = list(ITEM_RE.finditer(span_text))
            if len(items) >= 3:
                if items[0].start() > 0:
                    sections.append((f"{span_id}:preamble", span_text[: items[0].start()]))
                for i, m in enumerate(items):
                    end = items[i + 1].start() if i + 1 < len(items) else len(span_text)
                    label = re.sub(r"\s+", "", m.group(1).upper()).rstrip(".")
                    sections.append((f"{span_id}:{label}", span_text[m.start():end]))
                continue
        sections.append((span_id, span_text))
    return sections


def pack_section(section_text: str) -> list[str]:
    """Pack a section into chunks: tables atomic, paragraphs packed to target size
    with overlap, never merging across a table boundary."""
    pieces: list[tuple[str, bool]] = []  # (text, is_table)
    pos = 0
    while True:
        t0 = section_text.find(TABLE_OPEN, pos)
        if t0 == -1:
            pieces.append((section_text[pos:], False))
            break
        pieces.append((section_text[pos:t0], False))
        t1 = section_text.find(TABLE_CLOSE, t0)
        if t1 == -1:
            pieces.append((section_text[t0:], False))  # unterminated marker: treat as prose
            break
        t1 += len(TABLE_CLOSE)
        pieces.append((section_text[t0:t1], True))
        pos = t1

    chunks: list[str] = []
    buf: list[str] = []
    buf_toks = 0

    def flush():
        nonlocal buf, buf_toks
        joined = "\n".join(buf).strip()
        if joined and toks(joined) >= config.CHUNK_MIN_TOKENS:
            chunks.append(joined)
        elif joined and chunks and not chunks[-1].endswith(TABLE_CLOSE):
            chunks[-1] = chunks[-1] + "\n" + joined  # merge small tails, but never into a table
        elif joined:
            chunks.append(joined)
        buf, buf_toks = [], 0

    for text, is_table in pieces:
        if is_table:
            flush()
            chunks.append(text.strip())  # atomic, whatever its size
            continue
        for para in re.split(r"\n\s*\n", text):
            p = para.strip()
            if not p:
                continue
            pt = toks(p)
            if buf_toks + pt > config.CHUNK_MAX_TOKENS and buf_toks >= config.CHUNK_MIN_TOKENS:
                flush()
                # overlap: carry the tail of the previous chunk forward
                if chunks and config.CHUNK_OVERLAP_TOKENS:
                    tail = chunks[-1][-config.CHUNK_OVERLAP_TOKENS * 4 :]
                    buf, buf_toks = [tail], toks(tail)
            buf.append(p)
            buf_toks += pt
            if buf_toks >= config.CHUNK_TARGET_TOKENS:
                flush()
    flush()
    return chunks


def main() -> None:
    def run(log: RunLog) -> None:
        config.BUILD.mkdir(exist_ok=True)
        out = (config.BUILD / "chunks.jsonl").open("w")
        n = 0
        for doc_id, m in mlib.iter_manifests():
            if m["doc_type"] in SKIP_DOC_TYPES:
                continue
            text_path = mlib.doc_dir(doc_id) / "extracted.txt"
            if not text_path.exists():
                continue
            text = text_path.read_text(errors="replace")
            if len(text) < 200:
                continue
            for section_id, section_text in split_sections(text, m["doc_type"]):
                for seq, chunk_text in enumerate(pack_section(section_text)):
                    chunk_id = hashlib.sha256(
                        f"{doc_id}|{section_id}|{seq}|{chunk_text}".encode()
                    ).hexdigest()[:16]
                    out.write(json.dumps({
                        "chunk_id": chunk_id,
                        "doc_id": doc_id,
                        "section_id": section_id,
                        "seq": seq,
                        "kind": "table" if chunk_text.startswith(TABLE_OPEN) else "text",
                        "text": chunk_text,
                        "doc_type": m["doc_type"],
                        "source": m["source"],
                        "tier": m["source_tier"],
                        "title": m.get("title", ""),
                        "entities": m.get("entity_ids", []),
                        "filed_date": m.get("filed_date"),
                        "period_end": m.get("period_end"),
                    }, separators=(",", ":")) + "\n")
                    n += 1
            log.count("docs")
        out.close()
        log.ok(chunks=n)

    run_isolated("compile.chunk", run)


if __name__ == "__main__":
    main()
