"""Single-shot answer pipeline: understand -> route -> pack -> draft -> gate -> verify.

The answer is drafted from a frozen retrieval pack, the citation gate drops anything
outside it (never repairs), and both verification layers run before the result is
returned. Verify flags are surfaced, never silently fixed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import citations as gate, config, model, verify as verify_mod
from .router import RetrievalPack, build_pack
from .tags import Tagger
from .understand import Understanding, understand

SYSTEM = (
    "You are the answer layer over a versioned, cited corpus about Capital One. "
    "Rules:\n"
    "1. Use ONLY the retrieval pack below. No outside knowledge, however confident.\n"
    "2. Cite every factual sentence with its source tag(s) in brackets at the end of the "
    "sentence, e.g. [C2] or [obs:ab12cd34ef567890] or [ent:cof] or [ev:...] or [brief:...].\n"
    "3. NUMBERS: state a figure only if an [obs:...] row provides it, and cite that row. "
    "If prose mentions a number but no observation covers it, describe the trend "
    "qualitatively and note the corpus lacks a governed figure. Never invent or repair "
    "numbers.\n"
    "4. Quote sparingly and exactly; anything in double quotes must appear verbatim in "
    "the pack.\n"
    "5. If the pack cannot answer the question, say exactly what is missing instead of "
    "guessing."
)


def render_pack(pack: RetrievalPack) -> str:
    parts: list[str] = []
    for o in pack.observations:
        parts.append(
            f"[obs:{o['obs_id']}] {o['metric_name']} ({o['metric_id']}, basis {o['basis']}) "
            f"entity={o['entity_id']} period={o['period']} ({o['period_type']}) "
            f"value={o['value']} {o['unit']}"
            + (f" dims={o['dims']}" if o["dims"] else "")
            + f" — source {o['source_doc']}"
            + (f" [{o['source_locator']}]" if o.get("source_locator") else "")
        )
    for e in pack.entities:
        edges = "; ".join(f"{d['type']} {d['target']}" for d in e["edges"][:12])
        parts.append(
            f"[ent:{e['id']}] {e['name']} ({e['type']}, {e['status']}) "
            f"ids={e['identifiers']}" + (f" edges: {edges}" if edges else "")
            + (f" — {e['summary']}" if e.get("summary") else "")
        )
    for ev in pack.events:
        parts.append(
            f"[ev:{ev['id']}] {ev['date']} ({ev['type']}) {ev['title']} — "
            f"{ev.get('summary', '')[:400]}"
        )
    for b in pack.briefs:
        parts.append(f"[brief:{b['id']}] {b['title']} (as of {b['as_of']}):\n{b['body'][:1500]}")
    for c in pack.chunks:
        parts.append(f"[{c['tag']}] {c['preamble']}\n{c['text'][:2500]}")
    return "\n\n".join(parts)


@dataclass
class AnswerResult:
    question: str
    answer: str
    citations: list[str]
    audit: list[str]
    verify: verify_mod.VerifyReport
    understanding: Understanding
    pack: RetrievalPack
    tags: dict[str, str] = field(default_factory=dict)
    cost_usd: float = 0.0

    def resolve_citation(self, token: str) -> dict | None:
        if token.startswith("obs:"):
            return next((o for o in self.pack.observations if o["obs_id"] == token[4:]), None)
        if token.startswith("ent:"):
            return next((e for e in self.pack.entities if e["id"] == token[4:]), None)
        if token.startswith("ev:"):
            return next((e for e in self.pack.events if e["id"] == token[3:]), None)
        if token.startswith("brief:"):
            return next((b for b in self.pack.briefs if b["id"] == token[6:]), None)
        return next((c for c in self.pack.chunks if c["tag"] == token), None)


def ask(question: str, *, conversation_tags: dict[str, str] | None = None,
        pack: RetrievalPack | None = None, understanding: Understanding | None = None,
        skip_model_verify: bool = False) -> AnswerResult:
    tagger = Tagger(conversation_tags)
    u = understanding or understand(question)
    pack = pack or build_pack(question, u, tagger)
    rendered = render_pack(pack)
    cost = 0.0

    if not pack.allowlist():
        return AnswerResult(
            question=question,
            answer="The corpus has no indexed material matching this question.",
            citations=[], audit=[], verify=verify_mod.VerifyReport(), understanding=u,
            pack=pack, tags=tagger.export(),
        )

    r = model.call(
        f"RETRIEVAL PACK:\n\n{rendered[:120000]}\n\nQUESTION: {question}",
        system=SYSTEM, feature="answer_draft", model=config.MODEL_SONNET,
    )
    cost += r.cost_usd

    gated = gate.enforce(r.text, pack.allowlist())
    rep = verify_mod.deterministic(gated.text, pack.all_text(), pack.obs_values())
    if not skip_model_verify:
        rep = verify_mod.faithfulness(gated.text, rendered, rep)

    return AnswerResult(
        question=question, answer=gated.text, citations=gated.citations, audit=gated.audit,
        verify=rep, understanding=u, pack=pack, tags=tagger.export(), cost_usd=cost,
    )
