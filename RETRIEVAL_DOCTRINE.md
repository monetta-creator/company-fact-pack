# Retrieval Doctrine — the Consumer Layer

Second grounding document for the repo. GROUNDING_CORPUS_PLAN.md governs what
the dataset is; this document governs how anything is allowed to consume it.
It distills the proven mechanics of the AI Atlas (the reference implementation:
github.com/monetta-creator/ai-atlas) and current retrieval best practice into
house doctrine. Every principle below names its mechanism, its Atlas reference
where one exists, and its adaptation to this corpus. When building the
retrieval layer, implement the mechanism; the prose is only its explanation.

---

## 0. Lineage

The Atlas proved the full consumer stack at small scale: hybrid full-text
retrieval with conversation-scoped citation tags (`lib/ask/retrieve.ts`),
peek panels over guest-safe record fetches (`lib/ask/search.ts`), a
deterministic citation gate (`lib/citations.ts`), a two-layer answer
faithfulness check (`lib/ask/verify.ts` + `/api/ask/verify`), and a bounded
deep-research loop (`lib/ask/deep.ts`). This repo ports those mechanics onto a
corpus with richer structure (manifests, entity spine, governed metrics,
bitemporal facts) — the structure is what upgrades the Atlas pattern from
good to state-of-the-art.

## 1. Doctrine

### D1 — Structure before search
Retrieval quality is decided at index time. Mechanisms:
- **Section-aware chunking.** Filing items, transcript speaker turns, and
  regulatory schedules are the chunk units. Tables are atomic: a table is one
  chunk, never split mid-row.
- **Contextual enrichment.** Before embedding, every chunk receives a short
  generated preamble situating it (document, section, entity, period):
  "From COF 10-K FY2025, Item 7 MD&A, credit card segment." Raw filing text is
  ambiguous out of context; the preamble is the highest-leverage recall
  improvement available and it costs one cheap model call per chunk at build.
- **Metadata on every chunk.** Entity IDs, doc type, period, source tier —
  inherited from the corpus manifest, never re-derived at query time.

### D2 — Filter before relevance
A query-understanding step runs first: extract entity, period, and doc-type
filters; classify intent (quantitative / narrative / relational / event).
Retrieval scores relevance only within the filtered slice. This is the
AlphaSense pattern, and the manifests carry exactly the fields it needs.

### D3 — Route numbers to definitions
Quantitative intent compiles to SQL against `/metrics` with its governed
definitions and returns values with source pointers. Numbers are never
answered from chunks: a figure retrieved from prose has unknown basis
(restated? segment? trust data?), while a figure from the metric store has
exactly one blessed definition.

### D4 — Hybrid retrieval, fused, reranked
Lexical (SQLite FTS5 / BM25) and dense (local vector store) retrieval run in
parallel within the filtered slice; results merge by reciprocal rank fusion;
a cross-encoder reranks the fused top-N. At this corpus's scale, first-stage
retrieval is recall-heavy (top ~200) because reranking that many candidates
costs pennies — an advantage large systems lack.

### D5 — Citation is a gate, never decoration
Atlas reference: `enforceCitations` in `lib/citations.ts`. Mechanism: a
generated answer may cite only into its own frozen retrieval pack, held as an
allowlist; any citation outside the pack is **dropped to plain text and
recorded in an audit list, never repaired**. The gate runs at generation time
and again at save/render boundaries. Adaptation: the allowlist is corpus doc
IDs + chunk locations + metric observation IDs.

### D6 — Verify, then show the flags
Atlas reference: `lib/ask/verify.ts` + `/api/ask/verify`. Two layers, always
in this order:
1. **Deterministic checks**: every quoted string and every number in the
   answer is matched against the cited source text. Pure string/figure
   comparison, zero model involvement, zero latency.
2. **Model faithfulness pass**: a small model (Haiku-class) judges
   per-statement support against the exact cited records, via a forced tool.
Flags render to the reader; the system never silently edits an answer to make
it pass. Trust comes from visible verification, never from suppression.

### D7 — Bounded agency
Atlas reference: `lib/ask/deep.ts`. The deep-research loop is capped on every
axis — rounds (4), tool calls per round (6), characters per tool result,
total input tokens, wall clock — so a runaway session is structurally
impossible. Tools for this corpus: `search_corpus`, `query_metrics`,
`get_entity`, `list_events`, `fetch_document`. Tags for retrieved chunks are
minted server-side on one shared counter, seeded from tags the conversation
already holds, so a record rediscovered in a later turn keeps its original
tag and citations resolve across turns.

### D8 — Stable IDs beat minted tags where they exist
Entities, briefs, metrics, and events have permanent slugs from the corpus —
cite those directly. Minted conversation-scoped tags (the Atlas S/P pattern)
are only for records with no stable short code (raw corpus chunks). The
Atlas needed minting broadly; this corpus mostly doesn't, which simplifies
verification.

### D9 — The model proposes, the human commits
Anything the consumer layer writes back toward the corpus (extracted facts,
draft briefs, flagged staleness) lands as a draft on a branch. Publishing is
a human act. This is the Atlas human gate, and it is already rule 3 of the
corpus plan; the retrieval layer inherits it without exception.

### D10 — Every call metered
Atlas reference: `lib/cost.ts`. Every model call logs feature, tokens,
latency, and cost with the rate frozen at call time. Enrichment passes at
index time are where spend actually accumulates; the meter is how you notice.

### D11 — Eval-bounded quality
Two suites, run on every build:
- **Golden retrieval set**: query → expected corpus chunks, scored recall@k.
  This is the only instrument that can see index-time failures (bad chunk
  boundaries, missing metadata), which are otherwise silent.
- **Answer harness** (Phase 4 of the corpus plan): associate-equivalence
  questions, graded rubric, with-corpus vs. without.
Retrieval recall bounds everything the verify pass can later certify.

## 2. Anti-patterns

- **GraphRAG on top of briefs.** Its community summaries duplicate the
  doctrine briefs with worse provenance. The entity spine covers traversal.
- **Silent citation repair.** A wrong citation is dropped and audited, never
  guessed into a plausible one.
- **Answering numbers from prose.** See D3.
- **Unfiltered semantic search.** Dense retrieval over the whole corpus
  without metadata filters retrieves the right words about the wrong period.
- **Splitting tables.** A half-table chunk is worse than no chunk.
- **Unbounded loops.** Every agentic path has hard caps before it ships.
- **Porting the doctrine as prose.** Each principle above is a mechanism
  (a gate, a cap, a check, a build step). If the implementation lacks the
  enforcement, the principle is absent regardless of what comments say.

## 3. What makes this proprietary

No single component here is secret; the compound is. Public tools each hold a
piece: NotebookLM grounds and cites, AlphaSense filters before relevance,
research agents decompose queries. This system's identity is the full chain —
a bitemporal, provenance-complete corpus underneath; structure-first indexing;
definition-routed numbers; gated citations; visible two-layer verification;
bounded agency; human-committed writes; eval-bounded quality — with every
link enforced in code and proven in a running reference implementation. An
answer from this system is checkable end-to-end: sentence → citation → chunk
→ manifest → public source. That property is the product.
