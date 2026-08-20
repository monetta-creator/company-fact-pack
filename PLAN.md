# Capital One Public Grounding Corpus — Build Plan

Seed document for the repo. This file defines the operating rules, the repo layout,
the source registry, and the phased roadmap. It is written to be read by both the
human maintainer and Claude Code; treat it as the navigation index until a fuller
CLAUDE.md exists.

---

## 1. Purpose

Build a versioned, cited, machine-consumable dataset that gives an LLM
associate-grade grounding on Capital One: what the company is, how it makes money,
what it has done, what it offers, and how it has performed — every item traceable
to a public source. This corpus is the grounding layer beneath a separate
hypothesis/claim/evidence ledger (built later, in-house).

## 2. Operating rules

1. **Public-only.** Every item in this repo derives from a publicly available
   source. Anything learned at work stays out of this repo entirely. The git
   history plus source manifests constitute proof of public provenance.
2. **Provenance is mandatory.** Every document in `/corpus` has a manifest with
   URL, retrieval date, and content hash. Every fact, event, and brief points to
   corpus doc IDs. A citation that fails to resolve fails CI.
3. **Human gate.** Model-generated content lands on branches and enters `main`
   only through review. `epistemic_status: draft` items are invisible to
   retrieval builds.
4. **Epistemic status on everything.** One of: `settled`, `reported`,
   `estimated`, `contested`, `superseded`, `draft`. Company self-reporting is
   `reported` until corroborated.
5. **Bitemporal fields.** Facts carry `valid_from`/`valid_to` (true in the
   world) and `as_of` (when we recorded it). Supersede, never delete.
6. **Decay policy.** Every brief carries `review_by`. CI emits a staleness
   report on every build.
7. **Interpretations are claims.** If a competent outside analyst could dispute
   it, it belongs in the (future) ledger, however widely believed. Grounding
   admits only what is checkable against a source.

## 3. Repo layout

```
/corpus/<source>/<doc_id>/     # raw file + extracted text + manifest.yaml
/entities/                     # one YAML per entity: id, type, aliases, edges, status
/metrics/definitions/          # one file per metric: formula, basis, source schedule
/metrics/observations/         # JSONL: metric_id, period, value, dims, source_ptr
/products/                     # effective-dated product records (terms, pricing, dates)
/events/                       # JSONL: date, type, entity_ids, title, source_ptr
/briefs/                       # authored doctrine: markdown + YAML frontmatter
/schemas/                      # JSON Schema for every file type above
/scripts/fetch/                # per-source acquisition scripts
/scripts/extract/              # structured reads: corpus -> entities/events/metrics
/scripts/validate/             # CI: schema, reference resolution, staleness, orphans
/scripts/compile/              # build: SQLite + embeddings index + context packs
/evals/                        # associate-equivalence question bank + rubrics
PLAN.md                        # this file
```

Brief frontmatter: `id`, `title`, `entities[]`, `as_of`, `epistemic_status`,
`review_by`, `sources[]` (corpus doc pointers), `depends_on[]` (brief/entity/
metric IDs). IDs are permanent slugs; supersession replaces deletion.

## 4. Source registry

Priority: A = build first, structured or near-structured. B = company voice,
semi-structured. C = third-party context. Each entry lists what it feeds.

### Tier A — Regulatory and structured filings

| Source | What it yields | Feeds | Cadence | Access |
|---|---|---|---|---|
| SEC EDGAR: 10-K / 10-Q | XBRL financials, risk factors, MD&A, segment detail | metrics, briefs, corpus | Quarterly/annual | EDGAR full-text + XBRL APIs, free |
| SEC EDGAR: 8-K | Material events; **monthly credit card trust performance** (delinquency/charge-off/payment rate via securitization reporting) | events, metrics | Monthly + ad hoc | EDGAR API |
| SEC EDGAR: DEF 14A proxy | Governance, executive comp, board, ownership | entities, briefs | Annual | EDGAR |
| SEC EDGAR: S-4 / merger proxy (Discover) | Deal rationale, background-of-the-merger narrative, projections, fairness analysis — one of the densest doctrine sources available | briefs, events | One-time | EDGAR |
| Discover's own historical filings | Pre-merger grounding on the acquired business and network | briefs, metrics, events | Historical backfill | EDGAR |
| FR Y-9C (holding co.) + FFIEC Call Reports (bank subs) | Deep regulatory financials: loan categories, delinquency schedules, deposit composition, capital | metrics | Quarterly | FFIEC/NIC bulk downloads, free |
| FFIEC UBPR | Peer-group performance comparisons, precomputed ratios | metrics, briefs | Quarterly | FFIEC, free |
| FDIC Summary of Deposits | Branch-level deposit footprint over time | metrics, entities | Annual | FDIC API |
| Federal Reserve stress tests (DFAST/CCAR disclosures) | Loss rates under scenarios; regulator's view of the book | metrics, briefs | Annual | Fed website |
| Fed/OCC approval order for the Discover acquisition | Regulator's analysis of the combined company, conditions imposed | briefs, events, corpus | One-time | Fed website |
| CFPB credit card agreement database | Actual filed card agreements — the effective-dated product catalog source | products | Quarterly | CFPB website, free |
| CFPB consumer complaint database | Structured complaints by company/product/issue — external signal on product friction | events, briefs (later: ledger evidence) | Continuous | CFPB API |
| CFPB / OCC / Fed enforcement actions | Consent orders and penalties | events, corpus | Ad hoc | Agency sites |
| Fed G.19 + Philadelphia Fed credit card data | Industry-level consumer credit context | metrics (industry), briefs | Monthly/quarterly | Fed sites |
| USPTO patents/trademarks | Technology direction, brand activity | events, briefs | Continuous | USPTO/PatentsView APIs |
| PACER / CourtListener | Litigation record (breach settlement, partnership disputes) | events, corpus | Ad hoc | CourtListener free tier |

### Tier B — Company voice

| Source | What it yields | Feeds | Notes |
|---|---|---|---|
| Earnings call transcripts | Management's causal narrative, guidance, Q&A pressure points | briefs, events | Richest doctrine source; backfill several years |
| Investor Day / conference presentations | Strategy framing, segment economics, targets | briefs, corpus | IR site + financial-conference webcasts |
| Press releases | Events feed | events | IR site archive |
| Annual report letters | CEO framing over time — doctrine evolution | briefs | |
| Product pages + Wayback Machine snapshots | Terms, pricing, positioning over time | products | Schumer boxes; snapshot quarterly going forward |
| Capital One tech/engineering blog | Cloud migration story, build-vs-buy posture, engineering culture | briefs | Genuinely distinctive for this company |
| Job postings (careers site) | Org signals, tech stack, strategic hiring themes | events, briefs | Treat as `reported`; snapshot periodically |

### Tier C — Third-party context

| Source | What it yields | Notes |
|---|---|---|
| Trade press: American Banker, Payments Dive, Banking Dive | Event coverage, industry framing | Some paywalls; headlines/summaries still useful |
| Wire services: Reuters, AP | Event corroboration | |
| Rating agency actions (Moody's/S&P/Fitch) | External credit assessment; action rationales are public | Mark `reported` with agency attribution |
| Wikipedia + cited sources | Historical scaffold; follow citations to primaries | Never a terminal citation — use to find primaries |
| Academic/industry studies (card economics, deposit betas) | Mechanism briefs | |

## 5. Doctrine brief backlog (initial)

Write in this order; each cites corpus documents. Items marked (verify) need
dates/details confirmed against primaries before the brief leaves `draft`.

1. How the company makes money: card economics, funding model, deposit franchise, interchange, credit spread
2. The Discover acquisition: rationale, terms, integration state, network strategy
3. Corporate history and lineage: spinoff origins, IPO, major acquisitions and exits (verify each against filings)
4. Credit cycle posture: how management discusses underwriting through cycles (from transcripts)
5. The technology thesis: cloud migration, in-house software posture, AI positioning
6. Deposit strategy: branch-light model, digital bank evolution
7. Segment map: Credit Card / Consumer Banking / Commercial — economics of each
8. Regulatory posture: consent-order history, current constraints, capital requirements
9. Partnership history: co-brand and retail card wins/losses (verify)
10. Competitive field: issuer and network landscape, where the company sits
11. The 2019 data breach and aftermath (verify settlement details against court records)
12. Marketing and brand strategy over time

## 6. Phased roadmap

**Phase 1 — Corpus + spine**
Fetch scripts for EDGAR, FFIEC, CFPB agreement DB, transcripts. Entity spine
drafted and reviewed. Schemas + CI validation running. *Done when:* every schema
validates, entity references resolve, corpus manifests complete.

**Phase 2 — Metrics + events**
Y-9C/call report parser → observations. XBRL pull for company-reported figures.
Monthly trust data ingested. Event backfill from 8-Ks and press releases,
several years deep. *Done when:* a compiled SQLite answers period/segment metric
queries with source pointers.

**Phase 3 — Doctrine briefs**
Source-packet assembly script + drafting workflow. Work the backlog above.
*Done when:* top 12 briefs merged at `reported` or better.

**Phase 4 — Eval harness (start alongside Phase 3)**
Associate-equivalence question bank (~100 questions across tenure levels),
graded rubric, harness comparing model-with-corpus vs. model-alone. *Done when:*
the harness runs on every build and the delta is tracked over time.

**Phase 5 — Retrieval layer**
A NotebookLM/AlphaSense-grade search and answer surface over the corpus,
ported from the Atlas Ask architecture (hybrid retrieval, citation tags +
peek, citation gate, faithfulness verify, bounded deep-research loop).
Consumers touch only compiled artifacts, rebuilt on every merge.

*Index time:* section-aware chunking (filing items, transcript speaker turns,
regulatory schedules; tables kept whole) → contextual enrichment (generated
per-chunk preamble situating it in doc/section/period before embedding) →
dual index: SQLite FTS5 (BM25) + local vector store, every chunk carrying
manifest metadata (entities, doc type, period, tier).

*Query time:* query understanding extracts filters (entity, period, doc type)
and classifies intent → router: quantitative → SQL over /metrics with governed
definitions; narrative → lexical + dense retrieval within the filtered slice,
reciprocal-rank fusion, cross-encoder rerank.

*Answer time:* citation tags resolving to source spans; citation gate (a
sentence citing outside the retrieved pack is dropped); deterministic
quote/number verification + model faithfulness pass, flags shown to reader.

*Deep mode:* bounded agentic loop (capped rounds/calls/context) over typed
tools: search_corpus, query_metrics, get_entity, list_events, fetch_document.

*Explicitly skipped:* GraphRAG — doctrine briefs are the human-reviewed
equivalent of its community summaries, with better provenance; the entity
spine covers relationship traversal.

*Evals:* a golden retrieval set (query → expected corpus chunks, recall@k)
maintained alongside the Phase 4 answer harness; both run on every build.

## 7. Transfer-in-house design notes

- This repo remains the public upstream. Internal enrichment happens only on
  work systems, as an overlay (e.g., `/briefs-internal/`, `/ledger/`) that
  references public IDs. The repos fork at the boundary; nothing flows back.
- Manifests + git history document public origin for any review that transfer
  triggers.
- Keep schemas free of any internal-only concepts so the overlay can extend
  rather than modify.

## 8. Immediate next actions

1. `git init`; commit this file; add `/schemas` drafts for manifest, entity,
   event, observation, brief frontmatter.
2. EDGAR fetch script (10-K/Q, 8-K, proxy, S-4) with manifest writer.
3. FFIEC bulk download for Y-9C, most recent 12 quarters.
4. Draft the entity spine from the latest 10-K (subsidiaries exhibit) and proxy.
5. Stand up CI validation (schema + reference resolution) before any extraction
   pass runs.
