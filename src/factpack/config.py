"""Every constant in one place. Doctrine caps live here so tests can assert them."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "corpus"
BUILD = ROOT / "build"
CACHE = BUILD / "cache"
STATUS = BUILD / "status"
ENRICH_CACHE = BUILD / "enrich-cache"
PACKETS = BUILD / "packets"
DB_PATH = BUILD / "factpack.db"
COST_DB = BUILD / "cost.sqlite"
SCHEMAS = ROOT / "schemas"
VECTORS_NPZ = BUILD / "vectors.npz"  # fallback if sqlite-vec can't load

# SEC fair-access policy requires a declared contact; goes only to government APIs.
EDGAR_UA = "Kevin Michel monettacollective@gmail.com"

# Requests/second. All *.sec.gov hosts share one bucket, kept under the 10/s limit.
RATE_LIMITS = {"sec.gov": 8.0, "default": 2.0}

# Raw files above this stay in build/cache with their SHA-256 recorded in the manifest.
RAW_COMMIT_MAX_BYTES = 25 * 1024 * 1024
RAW_COMMIT_EXCEPTIONS: dict[str, int] = {}  # doc_id -> per-file ceiling, hard max 90MB

MODEL_HAIKU = "haiku"
MODEL_SONNET = "sonnet"
MODEL_CONCURRENCY = 5  # concurrent `claude -p` processes; wrapper backs off on rate errors

EMBED_MODEL = "BAAI/bge-small-en-v1.5"
EMBED_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "
EMBED_DIM = 384
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANK_MODEL_QUALITY = "BAAI/bge-reranker-base"  # opt-in via FACTPACK_RERANKER=quality

# Chunking (D1). Tokens approximated as chars/4; tables are never split regardless of size.
CHUNK_TARGET_TOKENS = 650
CHUNK_MAX_TOKENS = 900
CHUNK_MIN_TOKENS = 120
CHUNK_OVERLAP_TOKENS = 80

# Retrieval (D4)
FTS_K = 200
VEC_K = 200
RRF_K = 60
RERANK_TOP = 200
PACK_N = 12

# Deep-loop caps (D7) — enforced by the Python loop, a runaway is structurally impossible.
MAX_ROUNDS = 4
MAX_CALLS_PER_ROUND = 6
RESULT_CAP_CHARS = 2_000
TOTAL_TOOL_CHARS = 48_000
INPUT_TOKEN_CAP = 50_000
WALL_CLOCK_CAP_S = 300

# Identifier seeds (verified against EDGAR/FDIC 2026-08-19); the entity spine cites sources.
CIK = {
    "cof": "0000927628",
    "dfs": "0001393612",
    "comet": "0001163321",   # Capital One Multi-asset Execution Trust
    "dcent": "0001407200",   # Discover Card Execution Note Trust
}
FDIC_CERT = {"cona": "4297", "cobna": "33954", "discover-bank": "5649"}
