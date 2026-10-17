"""GitHub GraphQL client: disk cache, rate-limit sleep, retry with backoff."""
import datetime as dt
import hashlib
import json
import logging
import time

import httpx

from .. import config

log = logging.getLogger(__name__)
URL = "https://api.github.com/graphql"
CACHE_DIR = config.CACHE / "github"
STATS = {"hits": 0, "misses": 0, "retries": 0}
_client = httpx.Client(timeout=httpx.Timeout(90.0, connect=15.0))


class GqlError(Exception):
    """Persistent failure (timeouts, 5xx) — callers halve the batch and retry."""


def _sleep_for_rate(data: dict | None) -> None:
    rl = (data or {}).get("rateLimit") or {}
    if rl.get("remaining") is not None and rl["remaining"] < 50:
        reset = dt.datetime.fromisoformat(rl["resetAt"].replace("Z", "+00:00"))
        wait = max(1.0, (reset - dt.datetime.now(dt.UTC)).total_seconds() + 2)
        log.warning("GraphQL rate limit low (%s); sleeping %.0fs", rl["remaining"], wait)
        time.sleep(wait)


def post(query: str, variables: dict | None = None, use_cache: bool = True, max_retries: int = 5) -> tuple[dict, list]:
    """-> (data, errors). NOT_FOUND aliases come back as None in data."""
    key = hashlib.sha1((query + json.dumps(variables or {}, sort_keys=True)).encode()).hexdigest()
    path = CACHE_DIR / f"{key}.json"
    if use_cache and path.exists():
        STATS["hits"] += 1
        body = json.loads(path.read_text())
        return body.get("data") or {}, body.get("errors") or []
    STATS["misses"] += 1
    headers = {"Authorization": f"bearer {config.GITHUB_TOKEN}"}
    for attempt in range(max_retries):
        try:
            r = _client.post(URL, json={"query": query, "variables": variables or {}}, headers=headers)
        except httpx.TimeoutException:
            STATS["retries"] += 1
            if attempt >= 1:  # a query that times out twice is too big: let the caller split it
                raise GqlError("timeout")
            continue
        if r.status_code in (502, 503, 504) or (r.status_code == 403 and "secondary" in r.text.lower()) \
                or r.status_code == 429:
            STATS["retries"] += 1
            wait = float(r.headers.get("Retry-After") or 2 ** attempt * 2)
            log.warning("GraphQL %s, retry in %.0fs", r.status_code, wait)
            if r.status_code in (502, 504) and attempt >= 1:
                raise GqlError(f"http {r.status_code}")
            time.sleep(wait)
            continue
        r.raise_for_status()
        body = r.json()
        errors = body.get("errors") or []
        for e in errors:
            if e.get("type") != "NOT_FOUND":
                log.info("GraphQL error: %s", e.get("message"))
        if body.get("data") is None:
            raise GqlError(f"no data: {errors[:1]}")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(body))
        _sleep_for_rate(body["data"])
        return body["data"], errors
    raise GqlError("retries exhausted")


def batched(items: list, size: int, build, use_cache: bool = True):
    """Yield (chunk, data) for every chunk; halves the chunk size on persistent failures."""
    i = 0
    while i < len(items):
        chunk = items[i:i + size]
        try:
            data, _ = post(build(chunk), use_cache=use_cache)
        except GqlError as e:
            if len(chunk) == 1:
                log.warning("giving up on %s: %s", chunk[0], e)
                yield chunk, {}
                i += 1
                continue
            half = max(1, len(chunk) // 2)
            log.warning("batch of %d failed (%s); halving", len(chunk), e)
            yield from batched(chunk[:half], half, build, use_cache)
            yield from batched(chunk[half:], half, build, use_cache)
            i += len(chunk)
            continue
        yield chunk, data
        i += len(chunk)
