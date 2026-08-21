# Handoff: context wrangling inside the walls

*For the agent (Claude Code or otherwise) that picks this up on Capital One systems.
Read this with PLAN.md §7, README "Taking this inside a corporate boundary", and
EXPLAINER.md. You may have very different tools than the machine this was built on —
that's expected. This document tells you what we're solving for and which parts of the
process are load-bearing, so you can improvise the rest.*

## What we're solving for

**The money is context wrangling.** Off-the-shelf products already retrieve and
summarize public filings well. What doesn't exist anywhere is an *auditable, versioned,
structured context layer over Capital One's internal evidence* — strategy decks,
planning docs, internal data — wrangled so that powerful downstream synthesizers
(Claude, the AI Atlas, whatever comes next) can consume it with provenance intact.

This public repo is the proof of concept: ~1,400 public documents wrangled into
manifests, governed metrics, events, entities, and human-gated briefs, exported as
context packs any tool can load in one fetch. Your job is the same machine pointed at
internal evidence — where the differentiated value actually lives, because only
in-house wrangling can touch it.

## The six invariants (keep these; improvise everything else)

The code here is one implementation. The *pattern* is what matters:

1. **Every document gets a provenance record** — where it came from (a SharePoint
   path counts), when it was captured, a content hash. No orphan evidence.
2. **Originals are kept; text is extracted deterministically.** The extraction can be
   crude; the original must survive beside it.
3. **The distillation points back.** Numbers go in a governed table (one definition
   per figure, source pointer per value). Events, entities, and claims each cite the
   document they came from. A pointer that resolves to nothing is a build failure.
4. **History is append-only.** Corrections supersede; nothing is overwritten. Status
   on everything (`draft | reported | settled | contested | superseded`).
5. **Humans hold the pen.** Anything model-written enters as a draft; a person
   promotes it or it never counts.
6. **The output is plain files.** Context packs — JSON/markdown at stable paths —
   that any synthesizer can consume. No bespoke API required.

Plus the boundary rule, which is absolute: **one-way flow.** This public repo is a
read-only upstream. The internal overlay only *adds* (new roots like
`corpus-internal/`, `briefs-internal/`, a claims ledger) and references public IDs
(entity slugs, metric ids, doc ids are stable for exactly this reason). Nothing
internal ever flows back out — the public repo's history is the standing proof that
nothing learned inside ever left.

## Ingestion recipes by format (what you'll actually face)

- **PDF decks** (the big one): one slide = one chunk; extract text per page
  (pypdf/pdfplumber if you have Python; any OCR available for image slides —
  Tesseract, macOS Vision, an internal service). Record deck title, author/team,
  date, and version in the manifest — decks get revised, and supersession is how you
  keep v3 from silently replacing v2.
- **Word/Google docs**: convert to text or markdown (pandoc, python-docx, export
  menus — whatever exists). Heading-aware chunking if cheap; plain paragraphs if not.
- **CSVs / Excel**: these are *metric observations*, not prose. Define internal
  metrics (owner, definition, unit) and load rows with source pointers. Never chunk
  a spreadsheet into text — that's how numbers lose their basis.
- **Strategy plans specifically**: decompose into *claims* — each strategic assertion
  becomes a record (statement, owner, date, status, evidence pointers to internal and
  public docs). This is the hypothesis/claim/evidence ledger PLAN.md always intended;
  internal strategy is where it finally lives. A plan decomposed this way is queryable
  ("which claims depend on deposit growth?") in a way a PDF never is.
- **Wikis/email/notes**: page-level manifests, section chunks, same as everything.

## The degradation ladder (unknown tooling is fine)

Work down this ladder to wherever the internal environment lets you stand:

1. **Full port** — Python + git + a local embedding model + an approved LLM endpoint:
   bring this repo's code (code-only transfer, README option 1), add overlay roots,
   swap `factpack/model.py` to the approved endpoint. Everything works.
2. **No embeddings** — keyword search (SQLite FTS5/BM25) alone is genuinely fine at
   internal scale; the labeling ladder's dictionary + TF-IDF rungs need no models.
3. **No LLM at all** — the machine still works: manifests, extraction, governed
   numbers, claims, exports. Humans write briefs using synthesizers interactively
   *outside* the pipeline, fed by your context packs. Model calls were always the
   optional layer here.
4. **No Python/git** — the schema is the product. Folders + hand-written
   `manifest.yaml` + a spreadsheet-as-metric-store + append-only naming conventions
   preserve every invariant. Ugly beats absent.

## Suggested first moves inside

1. Confirm the transfer door with IT/security (README lists four, safest first) and
   which model endpoints may see which document classes (their AI policy, not yours).
2. Stand up the overlay repo. Ingest 5–10 documents end-to-end — one strategy deck
   all the way to a decomposed claims file is the vertical slice that proves it.
3. Export the first internal context pack and feed it to whatever synthesizer the
   team uses. That demo — "ask about our strategy, get answers with receipts" — is
   what buys the runway for the rest.

## What exists here that you can reuse verbatim

Schemas (`schemas/`), the validation logic (`scripts/validate/`), the chunking and
labeling approach (`scripts/compile/`), the export shape (`export/*.json`), and the
governing docs (PLAN.md, RETRIEVAL_DOCTRINE.md). The public context packs themselves
are your day-one seed: the internal layer's claims can cite public briefs and metrics
from the moment it exists.
