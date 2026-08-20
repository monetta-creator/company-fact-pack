"""Hybrid retrieval (D4): lexical + dense IN PARALLEL within the filtered slice,
reciprocal-rank fusion, cross-encoder rerank. Filters run BEFORE relevance (D2) —
dense scoring happens only over rows that pass the metadata WHERE (anti-pattern #4).
"""

from __future__ import annotations

import json
import re

import numpy as np

from . import config, db as dblib, embed


def _filter_sql(filters: dict) -> tuple[str, list]:
    clauses, params = [], []
    if filters.get("entities"):
        ors = []
        for e in filters["entities"]:
            ors.append("entities LIKE ?")
            params.append(f'%"{e}"%')
        clauses.append("(" + " OR ".join(ors) + ")")
    if filters.get("doc_types"):
        ors = []
        for dt in filters["doc_types"]:
            ors.append("doc_type LIKE ?")
            params.append(dt + "%")
        clauses.append("(" + " OR ".join(ors) + ")")
    if filters.get("period_start"):
        clauses.append("(COALESCE(period_end, filed_date) >= ?)")
        params.append(filters["period_start"])
    if filters.get("period_end"):
        clauses.append("(COALESCE(period_end, filed_date) <= ?)")
        params.append(filters["period_end"])
    return (" AND ".join(clauses) or "1=1"), params


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[A-Za-z0-9]{2,}", query)
    return " OR ".join(f'"{t}"' for t in tokens[:24]) or '"the"'


def retrieve_chunks(query: str, filters: dict, top_n: int = config.PACK_N) -> list[dict]:
    db = dblib.connect()
    where, params = _filter_sql(filters)

    # lexical (BM25) within the slice
    fts_rows = db.execute(
        f"""SELECT c.rowid AS rid, bm25(chunks_fts) AS score
            FROM chunks_fts JOIN chunks c ON c.chunk_id = chunks_fts.chunk_id
            WHERE chunks_fts MATCH ? AND {where}
            ORDER BY score LIMIT ?""",
        [_fts_query(query), *params, config.FTS_K],
    ).fetchall()
    fts_rank = {r["rid"]: i for i, r in enumerate(fts_rows)}

    # dense within the slice: exact masked KNN
    slice_rows = [r["rowid"] for r in db.execute(f"SELECT rowid FROM chunks WHERE {where}", params)]
    vec_rank: dict[int, int] = {}
    if slice_rows:
        vecs, rowids = dblib.vectors()
        pos = {int(r): i for i, r in enumerate(rowids)}
        idx = np.array([pos[r] for r in slice_rows if r in pos], dtype=np.int64)
        if len(idx):
            sims = vecs[idx] @ embed.embed_query(query)
            order = np.argsort(sims)[::-1][: config.VEC_K]
            vec_rank = {int(slice_rows[i]): rank for rank, i in enumerate(order)}

    # reciprocal-rank fusion
    fused: dict[int, float] = {}
    for rid, rank in fts_rank.items():
        fused[rid] = fused.get(rid, 0.0) + 1.0 / (config.RRF_K + rank + 1)
    for rid, rank in vec_rank.items():
        fused[rid] = fused.get(rid, 0.0) + 1.0 / (config.RRF_K + rank + 1)
    if not fused:
        db.close()
        return []
    candidates = sorted(fused, key=fused.get, reverse=True)[: config.RERANK_TOP]

    rows = db.execute(
        f"SELECT * FROM chunks WHERE rowid IN ({','.join('?' * len(candidates))})", candidates
    ).fetchall()
    db.close()
    by_rid = {r["rowid"]: dict(r) for r in rows}
    ordered = [by_rid[r] for r in candidates if r in by_rid]

    # cross-encoder rerank of the fused candidate set
    scores = embed.rerank(query, [(c["preamble"] + "\n" + c["text"])[:1500] for c in ordered])
    for c, s in zip(ordered, scores):
        c["rerank_score"] = float(s)
        c["entities"] = json.loads(c["entities"])
    ordered.sort(key=lambda c: c["rerank_score"], reverse=True)
    return ordered[:top_n]
