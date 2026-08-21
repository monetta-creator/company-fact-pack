# Next steps

Working list from the 2026-08 build sessions. Each item is runnable independently;
model-dependent items pause gracefully on usage caps and resume when re-run.

## Transcripts (highest-leverage context gap)
- [x] Ingest COF Q1 2026 (Motley Fool) — in local corpus, indexed
- [ ] Backfill more quarters: Motley Fool publishes free COF transcripts
      (fool.com/earnings/call-transcripts/…). Upload via the app's Update page
      (type: transcript, set company + quarter) or drop `.txt` + `.yaml` sidecar
      in `inbox/transcripts/`, then run an update. Target: last 8–12 quarters,
      plus Discover's final quarters if findable.
- [ ] Policy note: transcripts are third-party renderings — kept LOCAL ONLY
      (`corpus/transcripts/` is gitignored). Revisit only with a clear basis to
      republish. Anything committed that cites a transcript doc_id will fail CI
      on GitHub (the doc isn't there) — keep transcript-citing briefs local or
      cite filings alongside.

## Brief quality pass (after transcripts land)
- [ ] Redraft with deeper parameters: raise target to 2,000–3,000 words, double
      the retrieval queries per topic in `scripts/briefs/topics.py`, include full
      metric series in packets. Run `scripts.briefs.draft_brief <id>` per brief on
      a `draft/*` branch; diff old vs. new; merge what's better (human gate).
- [ ] Priority order: credit-cycle-posture (was thin — needs transcripts),
      how-the-company-makes-money, discover-acquisition.

## Deferred pipeline work
- [ ] Optimize and speed up the index enricher (`scripts/compile/enrich.py`):
      - Raise batch size 15 → ~30 chunks/call (haiku handles it; halves call count —
        watch JSON-array fidelity at larger batches, keep the repair retry).
      - Trim chunk excerpts in the prompt 1,200 → ~700 chars; the label needs the
        gist, not the body. Roughly 40% input-token cut.
      - Raise `MODEL_CONCURRENCY` during enrich-only runs (8–10 lanes; backoff
        already handles rate errors) — config knob or env override.
      - Skip more templated doc types beyond 10-D (425 merger communications and
        card-agreement PDFs are highly repetitive; measure retrieval delta first
        via the golden set before/after).
      - Add an embedding cache keyed by chunk_id (mirror of enrich-cache) so a
        one-doc update re-embeds ~25 chunks instead of 62k — cuts reindex from
        ~20 min to ~2 min and makes frequent transcript adds painless.
      - Stretch idea: batch API / prompt-cache the shared instruction prefix if
        calls ever move off the CLI onto a key.
- [ ] Enrichment backfill: ~34k chunks still on deterministic preambles.
      `uv run python -m scripts.compile.drive` (cap-resilient; sleeps and resumes).
- [ ] Answer-harness baseline: `uv run python evals/run_answers.py --limit 10`
      (bank is merged; measures grounded vs. bare model).
- [ ] FR Y-9C: browser-download BHCF quarterly ZIPs from the NIC site into
      `inbox/ffiec/`, re-run update. Y-9C extractor and MDRM map are ready.
- [ ] Golden-set misses to tune: liquidity 10-K item, AML consent order,
      Ex-21 subsidiaries (see evals/history.csv).

## Atlas integration (separate chat has that context)
- [ ] Atlas consumes merged briefs from one URL:
      `https://raw.githubusercontent.com/monetta-creator/company-fact-pack/main/export/briefs.json`
      Render `as_of`, respect `review_by` (stale = flag or drop), dereference
      citations via `doc_urls`.
- [ ] Later tier: Atlas calls this repo's `POST /api/ask` for figure-grade
      answers instead of paraphrasing briefs.

## Work overlay (proprietary context — PLAN.md §7)
- [ ] Ask IT/security which transfer door is open. Preference order:
      (1) code-only + re-fetch inside, (2) `git bundle`, (3) export JSON only,
      (4) plain ZIP. Details in README "Taking this inside a corporate boundary".
- [ ] Build overlay repo inside: `corpus-internal/`, `briefs-internal/`, ledger.
      Strictly additive; references public IDs; nothing flows back out.
- [ ] Optional upstream feature: multi-root corpus/brief support in `config.py`
      (env-var extra roots + visible `internal` badge on citations).
- [ ] Settle which model endpoint internal calls use, and whether strategic
      plans may touch it (employer AI policy).

## Housekeeping
- [ ] Merged-brief citation flags from the first ask session (wrong obs cited for
      2026 figure in the charge-off answer) were caught by verify — consider a
      brief-lint pass that runs deterministic verify over brief bodies at draft time.
- [ ] DCENT trust monthlies are scanned JPGs — needs OCR if ever wanted.
