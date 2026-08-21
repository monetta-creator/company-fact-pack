"""Two-layer answer verification (D6), always in this order:
1) deterministic — every >=20-char quote and every number in the answer matched
   against the cited pack text / observation values; pure string work, no model;
2) model faithfulness — haiku judges per-statement support against the pack,
   schema-clamped as untrusted input.
Flags are RENDERED to the reader; the answer is never silently edited.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import citations as gate, config, model

QUOTE_RE = re.compile(r"[\"“”]([^\"“”]{20,})[\"“”]")
NUM_RE = re.compile(r"\$?\d[\d,]*\.?\d*%?")


def _norm(s: str) -> str:
    s = s.replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", s).lower().strip()


def _num_core(tok: str) -> str:
    return tok.strip("$%").replace(",", "").rstrip(".")


@dataclass
class VerifyReport:
    quotes_checked: int = 0
    numbers_checked: int = 0
    flags: list[dict] = field(default_factory=list)
    model_checked: int = 0


def deterministic(answer: str, pack_text: str, obs_values: list[float]) -> VerifyReport:
    rep = VerifyReport()
    body = gate.CITE_RE.sub("", answer)
    hay = _norm(pack_text)
    val_cores = {(_num_core(f"{v:.6f}").rstrip("0").rstrip(".")) for v in obs_values}
    val_cores |= {_num_core(f"{v:,.2f}") for v in obs_values}
    val_cores |= {_num_core(str(int(v))) for v in obs_values if float(v).is_integer()}

    for m in QUOTE_RE.finditer(body):
        rep.quotes_checked += 1
        if _norm(m.group(1)) not in hay:
            rep.flags.append(
                {"kind": "quote", "excerpt": m.group(1)[:140],
                 "issue": "quoted text not found in cited sources"}
            )
    hay_cores = {_num_core(t) for t in NUM_RE.findall(hay)}
    for tok in NUM_RE.findall(body):
        core = _num_core(tok)
        if len(core.replace(".", "")) < 3:
            continue  # 1-2 digit tokens are prose/date fragments, not figures
        if re.fullmatch(r"(19|20)\d{2}", core) and "$" not in tok and "%" not in tok:
            continue  # bare years are dates, not metrics
        rep.numbers_checked += 1
        if core in hay_cores or core in val_cores:
            continue
        try:  # value match after scale-normalizing (12.3 vs 12.30)
            f = float(core)
            if any(abs(f - v) < 1e-6 for v in obs_values):
                continue
        except ValueError:
            pass
        rep.flags.append(
            {"kind": "number", "excerpt": tok[:40],
             "issue": "figure not found in cited sources or observations"}
        )
    return rep


MODEL_SCHEMA = {
    "type": "object",
    "properties": {
        "checked": {"type": "integer"},
        "flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "excerpt": {"type": "string", "maxLength": 140},
                    "issue": {"type": "string", "maxLength": 280},
                },
                "required": ["excerpt", "issue"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["checked", "flags"],
    "additionalProperties": False,
}


def faithfulness(answer: str, pack_render: str, rep: VerifyReport) -> VerifyReport:
    try:
        r = model.call(
            "You are verifying an answer against its cited sources. For each factual claim "
            "in the ANSWER, check whether the SOURCES support it. Flag claims that are "
            "unsupported, contradicted, or stated more strongly than the sources allow. "
            "Do not flag phrasing or style.\n\n"
            f"SOURCES:\n{pack_render[:40000]}\n\nANSWER:\n{answer[:8000]}",
            feature="answer_verify", model=config.MODEL_HAIKU, schema=MODEL_SCHEMA,
        )
        data = r.json or {}
        rep.model_checked = min(int(data.get("checked", 0)), 500)
        for f in list(data.get("flags", []))[:20]:
            rep.flags.append(
                {"kind": "faithfulness", "excerpt": str(f["excerpt"])[:140],
                 "issue": str(f["issue"])[:280]}
            )
    except model.ModelError as e:
        rep.flags.append(
            {"kind": "verify-error", "excerpt": "", "issue": f"model verify pass failed: {e}"}
        )
    return rep
