"""Draft the associate-equivalence question bank (~100 questions, rubrics, levels).

HUMAN GATE (rule 3): the eval bank is model-generated content — refuses to run on
main; writes evals/associate_bank.yaml on the draft branch for human review. Questions
are generated FROM corpus material (packets), so answers are checkable against sources.
"""

from __future__ import annotations

import yaml

from factpack import config, model
from scripts.briefs.assemble_packet import assemble
from scripts.briefs.topics import TOPICS
from scripts.extract.entity_spine import require_draft_branch

PER_TOPIC = 8  # 12 topics x 8 = 96 questions
SCHEMA = {
    "type": "array",
    "minItems": 4,
    "items": {
        "type": "object",
        "properties": {
            "question": {"type": "string", "maxLength": 300},
            "level": {"enum": ["new-hire", "associate", "senior"]},
            "rubric": {"type": "string", "maxLength": 400},
            "expected_sources": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["question", "level", "rubric"],
        "additionalProperties": False,
    },
}


def main() -> None:
    require_draft_branch()
    bank: list[dict] = []
    for brief_id, topic in sorted(TOPICS.items()):
        packet = assemble(brief_id)[:60000]
        try:
            r = model.call(
                f"You are building an evaluation bank that tests whether a model has "
                f"associate-grade knowledge of Capital One, on the topic {topic['title']!r}. "
                f"From the source material below, write {PER_TOPIC} questions an informed "
                "colleague could answer, split across levels: new-hire (basic orientation), "
                "associate (working knowledge), senior (mechanisms and tradeoffs). Each "
                "question must be answerable FROM THIS MATERIAL; the rubric names the "
                "specific facts a good answer must contain. expected_sources lists the "
                "doc_ids the answer should draw on.\n\n" + packet,
                feature="eval_bank_draft", model=config.MODEL_SONNET, schema=SCHEMA,
                timeout_s=600,
            )
            for i, q in enumerate(r.json or []):
                q["id"] = f"{brief_id}-{i + 1}"
                q["topic"] = brief_id
                bank.append(q)
            print(f"{brief_id}: {len(r.json or [])} questions")
        except model.UsageLimitError:
            print(f"usage limit at {brief_id}; partial bank saved")
            break
        except Exception as e:  # noqa: BLE001
            print(f"{brief_id} failed: {e}")
    (config.ROOT / "evals/associate_bank.yaml").write_text(
        "# DRAFT (rule 3): model-generated question bank awaiting human review.\n"
        "# Merging to main is a human act.\n"
        + yaml.safe_dump(bank, sort_keys=False, allow_unicode=True)
    )
    print(f"wrote evals/associate_bank.yaml with {len(bank)} questions (draft)")


if __name__ == "__main__":
    main()
