"""All model calls go through here: `claude -p` headless, metered (D10), schema-constrained.

No API key in this setup — calls ride the user's Claude subscription via the CLI.
Every call writes an ai_cost_log row with the CLI's own total_cost_usd frozen at call
time; metering failures never break the call (Atlas recordApiCall contract).
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import config, schemas as _schemas  # noqa: F401  (import keeps registry warm)
from jsonschema import Draft202012Validator

_LIMIT_RE = re.compile(r"(usage|rate)\s*limit|limit (reached|exceeded)|overloaded", re.I)


class ModelError(RuntimeError):
    pass


class UsageLimitError(ModelError):
    """Subscription/rate exhaustion — callers may quarantine work and continue."""


@dataclass
class ModelResult:
    text: str
    json: dict | list | None
    usage: dict
    cost_usd: float
    wall_ms: int
    session_id: str
    model: str
    feature: str = ""
    meta: dict = field(default_factory=dict)


_backoff_lock = threading.Lock()
_backoff_until = 0.0


def _respect_backoff() -> None:
    wait = _backoff_until - time.monotonic()
    if wait > 0:
        time.sleep(wait)


def _trip_backoff(seconds: float) -> None:
    global _backoff_until
    with _backoff_lock:
        _backoff_until = max(_backoff_until, time.monotonic() + seconds)


def _run_cli(prompt: str, *, system: str | None, model: str, timeout_s: int) -> dict:
    cmd = [
        "claude", "-p",
        "--output-format", "json",
        "--model", model,
        "--tools", "",
        "--no-session-persistence",
    ]
    if system:
        cmd += ["--system-prompt", system]
    env = {k: v for k, v in os.environ.items()
           if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    proc = subprocess.run(
        cmd, input=prompt, capture_output=True, text=True, timeout=timeout_s, env=env
    )
    out = proc.stdout.strip()
    if not out:
        raise ModelError(f"empty CLI output (rc={proc.returncode}): {proc.stderr[:500]}")
    try:
        return json.loads(out)
    except json.JSONDecodeError as e:
        raise ModelError(f"unparseable CLI envelope: {out[:500]}") from e


def _extract_json(text: str):
    """Strip fences, take the outermost {...} or [...] slice, parse."""
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.M)
    for open_c, close_c in (("{", "}"), ("[", "]")):
        start = t.find(open_c)
        end = t.rfind(close_c)
        if start != -1 and end > start:
            try:
                return json.loads(t[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ModelError(f"no parseable JSON in model output: {text[:300]}")


def call(prompt: str, *, feature: str, system: str | None = None,
         model: str = config.MODEL_HAIKU, schema: dict | None = None,
         timeout_s: int = 240, retries: int = 3, meta: dict | None = None) -> ModelResult:
    if schema is not None:
        prompt = (
            f"{prompt}\n\nRespond with ONLY a JSON value matching this JSON Schema — "
            f"no prose, no code fences:\n{json.dumps(schema)}"
        )
    attempt = 0
    repair_used = False
    current_prompt = prompt
    while True:
        _respect_backoff()
        t0 = time.monotonic()
        try:
            env = _run_cli(current_prompt, system=system, model=model, timeout_s=timeout_s)
        except (ModelError, subprocess.TimeoutExpired) as e:
            attempt += 1
            if attempt > retries:
                raise ModelError(f"[{feature}] CLI failed after {retries} retries: {e}") from e
            time.sleep(min(30, 2 ** (attempt + 1)))
            continue

        text = str(env.get("result") or "")
        if env.get("is_error"):
            if _LIMIT_RE.search(text):
                _trip_backoff(60)
                attempt += 1
                if attempt > retries:
                    raise UsageLimitError(f"[{feature}] {text[:300]}")
                time.sleep(min(120, 15 * attempt))
                continue
            attempt += 1
            if attempt > retries:
                raise ModelError(f"[{feature}] CLI error result: {text[:300]}")
            time.sleep(min(30, 2 ** (attempt + 1)))
            continue

        result = ModelResult(
            text=text,
            json=None,
            usage=env.get("usage") or {},
            cost_usd=float(env.get("total_cost_usd") or 0.0),
            wall_ms=int(env.get("duration_ms") or (time.monotonic() - t0) * 1000),
            session_id=str(env.get("session_id") or ""),
            model=model,
            feature=feature,
            meta=meta or {},
        )
        _record(result)

        if schema is None:
            return result
        try:
            parsed = _extract_json(text)
            errs = list(Draft202012Validator(schema).iter_errors(parsed))
            if errs:
                raise ModelError(f"schema violation: {errs[0].message}")
            result.json = parsed
            return result
        except ModelError as e:
            if repair_used:
                raise ModelError(f"[{feature}] invalid JSON after repair retry: {e}") from e
            repair_used = True
            current_prompt = (
                f"{prompt}\n\nYour previous response was invalid ({e}). "
                f"Return ONLY the corrected JSON value."
            )


def map_calls(items, fn, *, concurrency: int = config.MODEL_CONCURRENCY):
    """Run fn(item) -> value across items with bounded concurrency.
    Returns a list aligned with items; a UsageLimitError propagates (callers decide),
    other per-item exceptions become None with the error recorded on stderr."""
    results = [None] * len(items)

    def worker(i, item):
        try:
            results[i] = fn(item)
        except UsageLimitError:
            raise
        except Exception as e:  # noqa: BLE001 — isolation: one bad item never kills the batch
            print(f"[model.map_calls] item {i} failed: {e}")

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(worker, i, item) for i, item in enumerate(items)]
        for f in futures:
            f.result()
    return results


_cost_lock = threading.Lock()


def _record(r: ModelResult) -> None:
    try:
        config.BUILD.mkdir(exist_ok=True)
        with _cost_lock, sqlite3.connect(config.COST_DB, timeout=30) as db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS ai_cost_log (
                    id INTEGER PRIMARY KEY, ts TEXT DEFAULT CURRENT_TIMESTAMP,
                    feature TEXT, model TEXT,
                    input_tokens INT, output_tokens INT,
                    cache_read_tokens INT, cache_creation_tokens INT,
                    wall_ms INT, cost_usd REAL, meta TEXT)"""
            )
            u = r.usage
            db.execute(
                "INSERT INTO ai_cost_log (feature, model, input_tokens, output_tokens,"
                " cache_read_tokens, cache_creation_tokens, wall_ms, cost_usd, meta)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    r.feature, r.model,
                    u.get("input_tokens", 0), u.get("output_tokens", 0),
                    u.get("cache_read_input_tokens", 0), u.get("cache_creation_input_tokens", 0),
                    r.wall_ms, r.cost_usd, json.dumps(r.meta),
                ),
            )
    except Exception as e:  # noqa: BLE001 — metering must never break the call
        print(f"[model._record] metering failed (ignored): {e}")


def cost_rollup() -> list[tuple]:
    """(feature, calls, input_tokens, output_tokens, cost_usd) per feature + total."""
    if not config.COST_DB.exists():
        return []
    with sqlite3.connect(config.COST_DB) as db:
        rows = db.execute(
            "SELECT feature, COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd)"
            " FROM ai_cost_log GROUP BY feature ORDER BY SUM(cost_usd) DESC"
        ).fetchall()
        total = db.execute(
            "SELECT 'TOTAL', COUNT(*), SUM(input_tokens), SUM(output_tokens), SUM(cost_usd)"
            " FROM ai_cost_log"
        ).fetchone()
    return rows + [total]
