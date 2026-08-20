"""The citation gate (D5): a generated answer may cite only into its own frozen
retrieval pack. Anything else is DROPPED to plain text and recorded in an audit list —
never repaired. Runs at generation time and again at render/save boundaries.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# citation-shaped tokens: [C12], [ent:cof], [obs:ab12...], [ev:...], [brief:...]
CITE_RE = re.compile(r"\[((?:C\d+)|(?:(?:ent|obs|ev|brief):[A-Za-z0-9._-]+))\]")


@dataclass
class GateResult:
    text: str
    citations: list[str] = field(default_factory=list)  # unique, in first-use order
    audit: list[str] = field(default_factory=list)      # dropped tokens, never repaired


def enforce(text: str, allowlist: set[str]) -> GateResult:
    used: list[str] = []
    audit: list[str] = []

    def sub(m: re.Match) -> str:
        token = m.group(1)
        if token in allowlist:
            if token not in used:
                used.append(token)
            return m.group(0)
        audit.append(token)
        return ""  # dropped to plain text

    clean = CITE_RE.sub(sub, text)
    clean = re.sub(r"[ \t]+([.,;:)])", r"\1", clean)  # tidy space left by drops
    clean = re.sub(r"[ \t]{2,}", " ", clean)
    return GateResult(text=clean, citations=used, audit=audit)
