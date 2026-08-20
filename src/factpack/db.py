"""Compiled-artifact access: factpack.db (SQLite) + vectors.npz (aligned embeddings).

At this corpus's scale (~50k chunks) exact filtered KNN is a masked numpy dot —
simpler and strictly more correct under metadata filters (D2) than ANN post-filtering.
"""

from __future__ import annotations

import functools
import sqlite3

import numpy as np

from . import config


def connect(path=None) -> sqlite3.Connection:
    db = sqlite3.connect(path or config.DB_PATH)
    db.row_factory = sqlite3.Row
    return db


@functools.cache
def vectors() -> tuple[np.ndarray, np.ndarray]:
    """-> (embeddings [n,dim] float32 L2-normalized, rowids [n] int64)"""
    data = np.load(config.VECTORS_NPZ)
    return data["embeddings"], data["rowids"]
