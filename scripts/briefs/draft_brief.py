"""Draft one doctrine brief from its packet (model-assisted).

HUMAN GATE (rule 3 / D9): refuses to run on main. The draft lands as
briefs/<id>.md with epistemic_status: draft and review_by +180d. In-text citations
use [src:<doc_id>#section]; a brief-level citation gate drops (never repairs) any
citation pointing outside the packet and records it in the draft's audit note.
"""

from __future__ import annotations

import argparse
import datetime as dt
import re

import yaml

from factpack import config, model
from scripts.briefs.assemble_packet import assemble
from scripts.briefs.topics import TOPICS
from scripts.extract.entity_spine import require_draft_branch

SRC_RE = re.compile(r"\[src:([^\]#\s]+)(#[^\]]*)?\]")

SYSTEM = (
    "You write doctrine briefs for a cited corpus about Capital One. Rules:\n"
    "1. Use ONLY the source packet. No outside knowledge, however confident you are.\n"
    "2. Cite every factual paragraph with [src:<doc_id>#<section>] tokens copied exactly "
    "from the packet.\n"
    "3. Numbers only where the packet provides them, cited to their source.\n"
    "4. Where the packet is thin, write what it supports and flag the gap explicitly in a "
    "'Gaps' section at the end — do not pad.\n"
    "5. Structure: ## sections with descriptive headings; 600-1200 words; analytical, "
    "not promotional."
)


def gate_brief(text: str, allowed_docs: set[str]) -> tuple[str, list[str]]:
    audit: list[str] = []

    def sub(m: re.Match) -> str:
        if m.group(1) in allowed_docs:
            return m.group(0)
        audit.append(m.group(0))
        return ""

    return SRC_RE.sub(sub, text), audit


def draft(brief_id: str) -> str:
    topic = TOPICS[brief_id]
    packet = assemble(brief_id)
    allowed = {m[0] for m in SRC_RE.findall(packet)}

    r = model.call(
        f"SOURCE PACKET:\n\n{packet[:150000]}\n\nWrite the doctrine brief: {topic['title']!r}.",
        system=SYSTEM, feature="brief_draft", model=config.MODEL_SONNET, timeout_s=600,
    )
    body, audit = gate_brief(r.text, allowed)

    today = dt.date.today()
    used_docs = sorted({m[0] for m in SRC_RE.findall(body)})
    fm = {
        "id": brief_id,
        "title": topic["title"],
        "entities": topic["entities"],
        "as_of": today.isoformat(),
        "epistemic_status": "draft",
        "review_by": (today + dt.timedelta(days=180)).isoformat(),
        "sources": [{"doc_id": d, "locator": None} for d in used_docs]
                   or [{"doc_id": next(iter(sorted(allowed)), "edgar-cof/xbrl_companyfacts"),
                        "locator": None}],
        "depends_on": [],
    }
    front = yaml.safe_dump(fm, sort_keys=False, allow_unicode=True)
    note = (
        f"\n\n---\n*Draft generated {today}; citation audit: "
        + (", ".join(audit) if audit else "clean")
        + ". Human review required before status upgrade (rule 3).*\n"
    )
    path = config.ROOT / "briefs" / f"{brief_id}.md"
    path.write_text(f"---\n{front}---\n\n# {topic['title']}\n\n{body}{note}")
    return f"drafted briefs/{brief_id}.md (audit: {len(audit)} dropped citations)"


def main() -> None:
    require_draft_branch()
    ap = argparse.ArgumentParser()
    ap.add_argument("brief_id", choices=sorted(TOPICS) + ["all"])
    args = ap.parse_args()
    targets = sorted(TOPICS) if args.brief_id == "all" else [args.brief_id]
    for bid in targets:
        try:
            print(draft(bid))
        except model.UsageLimitError as e:
            print(f"STOPPED at {bid}: usage limit ({e}); re-run to continue")
            break
        except Exception as e:  # noqa: BLE001 — one brief failing never stops the batch
            print(f"FAILED {bid}: {e}")


if __name__ == "__main__":
    main()
