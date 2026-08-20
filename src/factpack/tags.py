"""Citation tags (D7/D8).

Stable corpus IDs (entities, events, briefs, metric observations) are cited directly —
[ent:cof], [ev:...], [brief:...], [obs:...]. Minted conversation-scoped C-tags exist
ONLY for raw chunks, on one shared counter seeded from tags the conversation already
holds, so a chunk rediscovered in a later turn keeps its original tag.
"""

from __future__ import annotations


class Tagger:
    def __init__(self, seed: dict[str, str] | None = None):
        """seed: existing {tag -> chunk_id} map from earlier turns of the conversation."""
        self.tag_to_chunk: dict[str, str] = dict(seed or {})
        self.chunk_to_tag: dict[str, str] = {v: k for k, v in self.tag_to_chunk.items()}
        self._counter = 0
        for tag in self.tag_to_chunk:
            if tag.startswith("C") and tag[1:].isdigit():
                self._counter = max(self._counter, int(tag[1:]))

    def mint(self, chunk_id: str) -> str:
        if chunk_id in self.chunk_to_tag:
            return self.chunk_to_tag[chunk_id]
        self._counter += 1
        tag = f"C{self._counter}"
        self.tag_to_chunk[tag] = chunk_id
        self.chunk_to_tag[chunk_id] = tag
        return tag

    def export(self) -> dict[str, str]:
        return dict(self.tag_to_chunk)
