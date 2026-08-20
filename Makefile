.PHONY: fetch extract validate compile evals serve test cost

# Each fetch/extract target continues past per-source failure; runlog collects status.
fetch:
	uv run python -m scripts.fetch.run_all

extract:
	uv run python -m scripts.extract.run_all

validate:
	uv run python -m scripts.validate.run_all

compile:
	uv run python -m scripts.compile.run_all

evals:
	uv run python evals/run_retrieval.py
	uv run python evals/run_answers.py

serve:
	uv run factpack serve

test:
	uv run pytest -q

cost:
	uv run factpack cost
