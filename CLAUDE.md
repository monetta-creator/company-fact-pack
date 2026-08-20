# company-fact-pack

Versioned, public-source-only grounding corpus on Capital One, plus its retrieval layer.
**PLAN.md and RETRIEVAL_DOCTRINE.md are law.** Every doctrine principle (D1–D11) must exist
as an enforced code artifact — a gate, a cap, a check, a build step — never prose.

## Non-negotiable rules (from PLAN.md §2)

1. Public sources only. Nothing learned at work enters this repo.
2. Every corpus doc has a `manifest.yaml` (URL, retrieval date, SHA-256). Every fact/event/brief
   points to corpus doc IDs. A dangling pointer fails `make validate`.
3. **Human gate**: model-generated content (briefs, entity spine, products, eval bank) is written
   with `epistemic_status: draft` on a `draft/*` branch. The drafting scripts refuse to run on
   `main`. Merging is a human act. Compile excludes `draft` rows regardless.
4. Epistemic status on everything: `settled|reported|estimated|contested|superseded|draft`.
5. Bitemporal: `valid_from`/`valid_to`/`as_of`. Supersede, never delete or edit history.
6. Every brief carries `review_by`; staleness is reported on every build.

## Layout

- `corpus/<source>/<doc_id>/` — raw + `extracted.txt` + `manifest.yaml`
- `entities/ metrics/ products/ events/ briefs/ schemas/ evals/` — structured layers
- `scripts/{fetch,extract,validate,compile,briefs}/` — pipeline stages (thin CLIs over `src/factpack`)
- `src/factpack/` — installed package: shared libs + the retrieval/answer layer
- `build/` — ALL compiled artifacts and caches; gitignored; never hand-edit
- `inbox/` — user-dropped files (transcripts) awaiting ingest; gitignored

## Conventions

- Never hand-edit `metrics/observations/*.jsonl` — regenerate via `make extract`.
- Fetchers are idempotent: a doc whose manifest + hashes verify is skipped. Raw files >25MB stay in
  `build/cache/` with their hash in the manifest; extracted text is always committed.
- All model calls go through `factpack.model.call()` (claude -p headless) — metered to
  `build/cost.sqlite`, never call the CLI directly from scripts.
- EDGAR requests only through `factpack.http` (shared 8 req/s bucket, declared User-Agent).

## Commands

`make fetch | extract | validate | compile | evals | test | serve | cost`
