"""Bounded deep-research loop (D7). Every axis is capped by module constants enforced
by THIS loop, not by the model — a runaway session is structurally impossible:
MAX_ROUNDS, MAX_CALLS_PER_ROUND, RESULT_CAP_CHARS, TOTAL_TOOL_CHARS, INPUT_TOKEN_CAP,
WALL_CLOCK_CAP_S (values in config). Tags are minted server-side on the shared counter,
so citations resolve across turns.
"""

from __future__ import annotations

import json
import time

from . import answer as answer_mod, config, model, tools
from .router import RetrievalPack, build_pack
from .tags import Tagger
from .understand import understand

ROUND_SCHEMA = {
    "type": "object",
    "properties": {
        "calls": {
            "type": "array",
            "maxItems": config.MAX_CALLS_PER_ROUND,
            "items": {
                "type": "object",
                "properties": {"tool": {"type": "string"}, "args": {"type": "object"}},
                "required": ["tool", "args"],
                "additionalProperties": False,
            },
        },
        "answer": {"type": "string"},
    },
    "additionalProperties": False,
}

SYSTEM = (
    "You are the deep-research loop over a cited Capital One corpus. Each round, either "
    "request tool calls to gather evidence or produce the final answer.\n"
    'Reply with JSON only: {"calls": [{"tool": ..., "args": {...}}]} to investigate, or '
    '{"answer": "..."} when the gathered pack suffices.\n'
    + tools.TOOL_DOCS
    + "\nIn the final answer, cite every factual sentence with pack tags in brackets; "
    "figures only from [obs:...] rows."
)


def deep_ask(question: str, *, conversation_tags: dict[str, str] | None = None,
             on_status=None) -> answer_mod.AnswerResult:
    t0 = time.monotonic()
    tagger = Tagger(conversation_tags)
    u = understand(question)
    pack: RetrievalPack = build_pack(question, u, tagger)
    transcript: list[str] = []
    tool_chars = 0
    status = on_status or (lambda _msg: None)

    for round_no in range(1, config.MAX_ROUNDS + 1):
        if time.monotonic() - t0 > config.WALL_CLOCK_CAP_S:
            status(f"wall-clock cap hit in round {round_no}")
            break
        rendered = answer_mod.render_pack(pack)
        # INPUT_TOKEN_CAP enforced by character budget (~4 chars/token)
        budget = config.INPUT_TOKEN_CAP * 4 - len(SYSTEM) - len(question) - 2000
        history = "\n".join(transcript)[-budget // 3 :]
        prompt = (
            f"QUESTION: {question}\n\nPACK SO FAR:\n{rendered[: budget - len(history)]}\n\n"
            f"PRIOR TOOL RESULTS:\n{history}\n\nRound {round_no} of {config.MAX_ROUNDS}. "
            "JSON only."
        )
        try:
            r = model.call(prompt, system=SYSTEM, feature="deep_round",
                           model=config.MODEL_SONNET, schema=ROUND_SCHEMA)
        except model.ModelError as e:
            status(f"round {round_no} model error: {e}")
            break
        data = r.json or {}
        if data.get("answer") or not data.get("calls"):
            status(f"answer produced in round {round_no}")
            break
        calls = data["calls"][: config.MAX_CALLS_PER_ROUND]
        status(f"round {round_no}: {len(calls)} tool call(s)")
        for call in calls:
            if tool_chars >= config.TOTAL_TOOL_CHARS:
                transcript.append("SYSTEM: total tool-result budget exhausted.")
                break
            result = tools.run_tool(str(call["tool"]), call.get("args", {}), pack, tagger)
            result = result[: config.RESULT_CAP_CHARS]
            tool_chars += len(result)
            transcript.append(f"> {call['tool']}({json.dumps(call.get('args', {}))[:300]})\n{result}")
        else:
            continue
        break  # inner budget break exits the loop too

    # Final answer is ALWAYS produced through the gated single-shot path over the
    # accumulated pack — same gate, same two-layer verify.
    return answer_mod.ask(
        question, conversation_tags=tagger.export(), pack=pack, understanding=u
    )
