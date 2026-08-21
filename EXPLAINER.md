# What this is, in plain English

*A short explainer for people who don't write code.*

## Why we built it

AI models sound confident about everything, including things they're wrong about. If you
want to use AI seriously on a subject — here, one company — you need a way to know *why*
it said what it said. Our answer: don't teach the AI anything. Instead, build a library
of evidence so good, so organized, and so traceable that the AI never has to rely on
memory. Every sentence it produces points at a document you can open.

## What it is NOT

- **Not a chatbot.** The chat part is a small optional feature. The product is the library.
- **Not a trained AI.** No model was trained, tuned, or taught. Nothing here "learns."
- **Not scraped opinions.** Every source is a public record — SEC filings, regulator
  data, court documents — each stored with the receipt of where and when we got it.

## What it IS

A fact library about Capital One with three floors:

1. **The evidence** — 1,300+ original documents, each with a provenance record
   (its URL, the date we fetched it, a fingerprint proving it hasn't been altered).
2. **The distillation** — the numbers pulled into one governed table (every figure has
   exactly one definition), a timeline of events, a map of the companies and people,
   and a shelf of *briefs*: short, human-approved essays on how the company actually
   works, where every paragraph cites floor 1.
3. **The window** — an app to read the briefs, browse the numbers, and ask questions.
   Answers cite their sources, and a checker flags anything it can't verify — the flags
   are shown, never hidden.

## Where the AI actually shows up

Three AI models are involved, and none of them holds the knowledge:

- **A tiny "filing clerk"** (runs on the laptop, free) reads each half-page of evidence
  and places it on a giant map where similar meanings sit near each other. That's how
  a question finds the right passages even when the words don't match.
- **A tiny "desk checker"** (also local, free) double-checks the top candidates:
  *does this passage really answer this question?*
- **A big "writer/editor"** (Claude) drafts answers and brief drafts — but it may only
  use the passages handed to it, every citation it invents gets deleted and logged,
  and a second pass audits its claims against the sources.

The models are interchangeable parts. The knowledge is files in a folder.

## Why it's durable

- **It's all just files, versioned in git.** No vendor, no database server, no
  subscription required to *read* it. In 10 years, the evidence and its receipts open fine.
- **The database is disposable.** It's rebuilt from the files on demand, never edited —
  so it can't rot or drift from the truth.
- **History is append-only.** A corrected number doesn't overwrite the old one; it
  supersedes it, and the old one stays with a marker. You can always see what we
  believed and when.
- **Humans hold the pen.** Anything a model writes enters as a draft on a review
  branch. A person merges it, or it never counts.

## What this enables next

- **Instant context for other AI tools.** All approved briefs are published as one file
  at a stable web address — any tool can load "how this company works" in one fetch.
- **A private layer on top.** The same pattern extends inside a company: internal
  documents and strategy decomposed the same way, stacked on this public base,
  never flowing back out.
- **Any company, any subject.** Nothing here is Capital One-specific except the data.
  The machinery — receipts, gates, checks — is a template.

---

## The 101 version (how one answer happens)

1. Your question is read for *who*, *when*, and *what kind* (a number? a story? a date?).
2. Numbers route to the governed number table — never guessed from prose.
3. For narrative, two searches run at once — exact words and similar meaning — results
   are merged, and the desk checker re-sorts the best 200.
4. The writer drafts an answer from that evidence bundle alone, citing each sentence.
5. A gate deletes any citation that isn't in the bundle (and logs it — never "fixes" it).
6. Two checks run: exact string-matching of every quote and figure against the sources,
   then a second model auditing each claim. Problems appear as visible flags.

## The 301 version (the actual machinery)

- **Chunking**: documents are split on real structure (10-K items, exhibits, speaker
  turns), ~650 tokens per chunk, tables kept whole — never split mid-row. Chunk IDs are
  content-addressed (a hash of the text), which makes caching and incremental work free.
- **Enrichment**: each chunk gets a one-sentence generated preamble situating it
  (document, section, filer, period) before indexing — the cheapest big win for recall.
- **Dual index**: SQLite FTS5 (BM25) for lexical search + a 384-dim embedding matrix
  (`bge-small-en-v1.5`) for semantic search, both filtered by metadata *before* scoring.
  Results merge by reciprocal-rank fusion; a cross-encoder (`ms-marco-MiniLM`) reranks.
- **Governed metrics**: figures live in observation rows keyed to one definition each,
  with a source pointer per value; restatements supersede rather than overwrite
  (bitemporal: valid-time and as-of time both recorded).
- **The citation gate**: generation may cite only its frozen retrieval pack (an
  allowlist). Out-of-pack citations are stripped to plain text and appended to an audit
  list. The gate runs at generation *and* again at render.
- **Two-layer verify**: deterministic quote/number matching against pack text and
  observation values, then a schema-constrained model pass judging per-claim support.
  Flags render; the answer is never silently edited.
- **Bounded agency**: the deep-research mode is a loop with hard caps (rounds, calls
  per round, result size, total context, wall clock) enforced by the loop code.
- **Pipeline discipline**: fetchers are idempotent (a document whose manifest and
  hashes verify is skipped); validation fails the build on a single dangling citation;
  the compiled database is backed up and auto-restored if a rebuild fails verification;
  every model call is metered to a cost ledger.
