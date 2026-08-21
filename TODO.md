# Next steps

**The mission, restated:** the money is *context wrangling for downstream synthesis* —
turning evidence into an auditable, versioned context layer that more powerful
synthesizers consume. Retrieval/chat products are commoditized; wrangled, provenanced
context is not. This public repo is the working proof of concept. The next phase is the
same machine pointed at proprietary evidence inside Capital One's walls, where only
in-house wrangling can go. See **INTERNAL_HANDOFF.md** for the full brief to the
inside-the-walls agent.

## Phase next: the internal overlay (the actual prize)

- [ ] Ask IT/security which transfer door is open (README lists four, safest first)
      and which model endpoints may see which document classes.
- [ ] Stand up the overlay repo inside: `corpus-internal/`, `briefs-internal/`,
      `ledger/` — strictly additive on public IDs, one-way flow, nothing comes back.
- [ ] Vertical slice: one strategy deck ingested end-to-end — manifest → slide chunks
      → decomposed claims file → internal context pack → demo against a synthesizer.
- [ ] Digest machinery for internal formats (PDF decks, docs, CSVs/Excel, wikis) —
      recipes and the tool-degradation ladder are in INTERNAL_HANDOFF.md; get creative
      with whatever tooling exists there, keep the six invariants.
- [ ] Optional upstream feature (buildable out here first): multi-root corpus/brief
      support in `config.py` + a visible `internal` badge on citations.

## Public layer (maintenance mode — feed the packs, don't gold-plate)

- [ ] Transcript backfill: Motley Fool publishes COF calls free. Upload via the app
      (type: transcript) or `inbox/transcripts/` + sidecar; target last 8–12 quarters.
      Local-only (gitignored) — republication stays an open question.
- [ ] Brief-depth redraft AFTER transcripts land: raise target to 2,000–3,000 words,
      double queries in `scripts/briefs/topics.py`, redraft on a `draft/*` branch,
      diff and merge (human gate). Priority: credit-cycle-posture, then
      how-the-company-makes-money, discover-acquisition.
- [ ] Answer-harness baseline: `uv run python evals/run_answers.py --limit 10`.
- [ ] FR Y-9C: browser-download BHCF ZIPs into `inbox/ffiec/`, re-run update.
- [ ] Golden-set misses to tune when convenient (liquidity 10-K item, AML consent
      order, Ex-21) — see evals/history.csv.
- [x] Enrichment cost problem — SOLVED by the aboutness ladder (2026-08-21): zero
      model calls, local extraction + SEC section dictionary; embedding cache makes
      one-doc rebuilds ~2 min; answer model-verify is opt-in (--verify). Verify the
      golden A/B in evals/history.csv confirms parity with the paid labels.

## Keep-the-docs-true rule

Whenever the machine or the mission shifts, update in the same commit: README.md
(front door + transfer options), EXPLAINER.md (plain-English what/why),
INTERNAL_HANDOFF.md (the inside brief), and this file. The next agent should be able
to start from these four documents cold.

## Parking lot

- DCENT trust monthlies are scanned JPGs — OCR someday, or never.
- Brief-lint: run deterministic verify over brief bodies at draft time.
- Atlas deep tier: `POST /api/ask` for figure-grade answers (briefs.json covers
  ambient context today).
