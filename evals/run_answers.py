"""Answer harness (D11 / Phase 4): with-corpus vs bare-model, rubric-graded by a judge.

Local-only (model-dependent). Usage: uv run python evals/run_answers.py [--limit N]
Writes build/eval_answers.json; appends the aggregate to evals/history_answers.csv.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from factpack import config, model
from factpack.answer import ask

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "grounded_score": {"type": "integer", "minimum": 0, "maximum": 10},
        "bare_score": {"type": "integer", "minimum": 0, "maximum": 10},
        "notes": {"type": "string", "maxLength": 400},
    },
    "required": ["grounded_score", "bare_score"],
    "additionalProperties": False,
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    bank_path = config.ROOT / "evals/associate_bank.yaml"
    if not bank_path.exists():
        print("no evals/associate_bank.yaml (drafted on a draft/* branch; merge it first)")
        return 1
    bank = yaml.safe_load(bank_path.read_text())
    if args.limit:
        bank = bank[: args.limit]

    rows = []
    for q in bank:
        try:
            grounded = ask(q["question"], skip_model_verify=True)
            bare = model.call(
                q["question"], feature="eval_bare", model=config.MODEL_SONNET
            )
            judge = model.call(
                "Grade two answers to the same question about Capital One on 0-10 using the "
                f"rubric.\nQUESTION: {q['question']}\nRUBRIC: {q.get('rubric', 'accuracy, "
                "specificity, sourcing')}\n\nANSWER A (grounded):\n"
                f"{grounded.answer[:6000]}\n\nANSWER B (bare):\n{bare.text[:6000]}\n\n"
                "grounded_score = A, bare_score = B.",
                feature="eval_grade", model=config.MODEL_SONNET, schema=JUDGE_SCHEMA,
            )
            j = judge.json or {}
            rows.append({
                "id": q.get("id"), "level": q.get("level"),
                "grounded": j.get("grounded_score"), "bare": j.get("bare_score"),
                "notes": j.get("notes", ""), "flags": len(grounded.verify.flags),
                "audit": len(grounded.audit),
            })
            print(f"{q.get('id')}: grounded {j.get('grounded_score')} vs bare {j.get('bare_score')}")
        except model.UsageLimitError:
            print("usage limit hit; stopping (partial results saved)")
            break
        except Exception as e:  # noqa: BLE001
            rows.append({"id": q.get("id"), "error": str(e)[:200]})

    scored = [r for r in rows if r.get("grounded") is not None]
    summary = {
        "date": dt.date.today().isoformat(),
        "n": len(scored),
        "grounded_avg": round(sum(r["grounded"] for r in scored) / len(scored), 2) if scored else None,
        "bare_avg": round(sum(r["bare"] for r in scored) / len(scored), 2) if scored else None,
    }
    config.BUILD.mkdir(exist_ok=True)
    (config.BUILD / "eval_answers.json").write_text(
        json.dumps({"summary": summary, "rows": rows}, indent=1)
    )
    hist = config.ROOT / "evals/history_answers.csv"
    new = not hist.exists()
    with hist.open("a") as f:
        w = csv.DictWriter(f, fieldnames=list(summary))
        if new:
            w.writeheader()
        w.writerow(summary)
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
