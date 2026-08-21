# company-fact-pack

A versioned, public-source-only grounding corpus on Capital One, with a retrieval layer
that only says what it can prove. Every answer is checkable end-to-end:
**sentence → citation → chunk → manifest → public source.**

- **Corpus**: a decade of SEC filings (COF, Discover, both card trusts, exhibits included),
  FDIC financials and branch deposits, monthly trust performance, CFPB card agreements and
  complaints, Fed stress tests, enforcement orders, litigation records. Every document
  carries a manifest with its URL, retrieval date, and SHA-256.
- **Structured layers**: governed metrics (one definition per figure), dated events, an
  entity spine, effective-dated products, and reviewed doctrine briefs.
- **Ask layer**: hybrid retrieval with a citation gate (unprovable citations are dropped
  and logged, never repaired) and two-layer verification (string checks, then a judge
  model) with flags shown to the reader.

Governing documents: [`PLAN.md`](PLAN.md) (what the dataset is) and
[`RETRIEVAL_DOCTRINE.md`](RETRIEVAL_DOCTRINE.md) (how anything may consume it).
Every doctrine principle exists as an enforced code artifact — a gate, a cap, a check,
a build step — never prose.

## Quickstart

```sh
uv sync
uv run factpack serve        # app at localhost:8787 — Ask · Update · How to · Architecture · About
uv run factpack ask "How did trust charge-off rates trend through 2025?"
make fetch extract validate compile   # the full update pipeline, by hand
```

The **Update** page does the same with one button: add a file (earnings transcript or
FFIEC ZIP), press Run. Validation runs before compile — bad data can never replace a
working database.

## One-URL consumption

Downstream tools (e.g. an agent that wants standing Capital One context) fetch a single
JSON of all human-approved briefs, with every citation resolvable to its public source:

```
https://raw.githubusercontent.com/monetta-creator/company-fact-pack/main/export/briefs.json
```

Only briefs a human merged and promoted appear here — the review gate travels with the
export.

## Layout

| Path | Contents |
|---|---|
| `corpus/` | Source documents + extracted text + provenance manifests |
| `entities/ events/ metrics/ products/ briefs/` | Structured layers, versioned in git |
| `schemas/` | JSON Schema contract for every record type |
| `scripts/` | Pipeline stages: fetch, extract, validate, compile, briefs |
| `src/factpack/` | The ask layer: router, retrieval, citation gate, verify, app |
| `export/` | Compiled artifacts for downstream consumers |
| `build/` | Local database and caches — disposable, regenerated, gitignored |

## Taking this inside a corporate boundary

External git remotes are often blocked on work systems. Four sanctioned-path options, in
order of preference — ask your security/IT team which door is open before picking one:

1. **Code only; re-fetch the data inside.** Strip `corpus/` and transfer a few MB of
   reviewable source code plus the structured layers. Inside, `make fetch` rebuilds the
   entire corpus directly from sec.gov, fdic.gov, and consumerfinance.gov — hosts
   corporate egress usually allows. Nothing crosses the boundary except code; every byte
   of data arrives from the government with fresh manifests. The cleanest story to tell a
   security review.
2. **`git bundle` — one file, full history.** `git bundle create factpack.bundle --all`,
   transfer the file, `git clone factpack.bundle` inside. The commit history — the
   standing proof of public provenance — arrives intact.
3. **The export JSON alone.** Where only HTTPS browsing is allowed, the one-URL
   `export/briefs.json` above may be reachable even when cloning isn't, and can seed a
   downstream tool by itself.
4. **Plain ZIP.** Content stays verifiable (manifests carry hashes) but git history is
   lost; prefer the bundle when both pass the same gate.

### Adding proprietary context (the overlay pattern)

This repo remains the **public upstream**, per [`PLAN.md`](PLAN.md) §7. Internal
enrichment lives in a separate overlay repo on work systems (`corpus-internal/`,
`briefs-internal/`, a claims ledger) that only *adds* files and references public IDs —
entity slugs, metric definitions, doc and brief IDs are stable for exactly this reason.
Nothing flows back outward: the public repo's history is the proof that nothing learned
inside ever left, and it stays proof only if the flow is strictly inward.

## Operating rules (short form)

1. Public sources only; manifests + git history prove it.
2. Every fact points at a corpus document; a dangling pointer fails CI.
3. Model-generated content enters as `draft` on a branch; **merging is a human act**.
4. Epistemic status on everything; bitemporal fields; supersede, never delete.
5. Every brief carries a review date; staleness is reported on every build.
