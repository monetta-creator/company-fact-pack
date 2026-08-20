"""Throttled HTTP: per-host token buckets, retries with backoff, atomic downloads."""

from __future__ import annotations

import hashlib
import random
import tempfile
import threading
import time
from pathlib import Path

import httpx

from . import config

RETRYABLE = {429, 500, 502, 503, 504}


def _host_key(host: str) -> str:
    return "sec.gov" if host.endswith("sec.gov") else host


class _Bucket:
    def __init__(self, rate: float):
        self.rate = rate
        self.allow = rate
        self.last = time.monotonic()
        self.lock = threading.Lock()

    def take(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self.allow = min(self.rate, self.allow + (now - self.last) * self.rate)
                self.last = now
                if self.allow >= 1:
                    self.allow -= 1
                    return
                wait = (1 - self.allow) / self.rate
            time.sleep(wait)


_buckets: dict[str, _Bucket] = {}
_buckets_lock = threading.Lock()


def _bucket(host: str) -> _Bucket:
    key = _host_key(host)
    with _buckets_lock:
        if key not in _buckets:
            rate = config.RATE_LIMITS.get(key, config.RATE_LIMITS["default"])
            _buckets[key] = _Bucket(rate)
        return _buckets[key]


_client = httpx.Client(
    headers={"User-Agent": config.EDGAR_UA, "Accept-Encoding": "gzip, deflate"},
    timeout=httpx.Timeout(60.0, connect=20.0),
    follow_redirects=True,
)


def get(url: str, *, retries: int = 4, **kw) -> httpx.Response:
    host = httpx.URL(url).host
    last: Exception | None = None
    for attempt in range(retries + 1):
        _bucket(host).take()
        try:
            resp = _client.get(url, **kw)
            if resp.status_code in RETRYABLE:
                last = httpx.HTTPStatusError(
                    f"{resp.status_code} for {url}", request=resp.request, response=resp
                )
            else:
                resp.raise_for_status()
                return resp
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
        time.sleep(min(60, (2**attempt) + random.random()))
    raise last  # type: ignore[misc]


def get_json(url: str, **kw):
    return get(url, **kw).json()


def download(url: str, dest: Path, *, retries: int = 4) -> tuple[str, int]:
    """Stream to a temp file, atomic rename. Returns (sha256, size)."""
    host = httpx.URL(url).host
    dest.parent.mkdir(parents=True, exist_ok=True)
    last: Exception | None = None
    for attempt in range(retries + 1):
        _bucket(host).take()
        try:
            h = hashlib.sha256()
            size = 0
            with _client.stream("GET", url) as resp:
                if resp.status_code in RETRYABLE:
                    raise httpx.HTTPStatusError(
                        f"{resp.status_code} for {url}", request=resp.request, response=resp
                    )
                resp.raise_for_status()
                with tempfile.NamedTemporaryFile(dir=dest.parent, delete=False) as tmp:
                    for chunk in resp.iter_bytes(65536):
                        h.update(chunk)
                        size += len(chunk)
                        tmp.write(chunk)
                    tmp_path = Path(tmp.name)
            tmp_path.replace(dest)
            return h.hexdigest(), size
        except (httpx.TransportError, httpx.HTTPStatusError) as e:
            last = e
            try:  # never leave multi-GB partial temp files behind (they can fill the disk)
                if "tmp_path" in dir() and tmp_path.exists():
                    tmp_path.unlink()
            except OSError:
                pass
            time.sleep(min(60, (2**attempt) + random.random()))
    raise last  # type: ignore[misc]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()
