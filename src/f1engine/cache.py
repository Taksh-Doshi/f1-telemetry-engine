"""Small JSON cache helpers backed by the project's Valkey service."""

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, TypeVar

from dotenv import load_dotenv
from redis import Redis


PROJECT_ROOT = Path(__file__).resolve().parents[2]
T = TypeVar("T")


@lru_cache(maxsize=1)
def get_cache_client() -> Redis:
    """Create a Valkey client using VALKEY_URL from the project .env."""
    load_dotenv(PROJECT_ROOT / ".env")
    valkey_url = os.getenv("VALKEY_URL")
    if not valkey_url:
        raise RuntimeError(
            f"VALKEY_URL is not set. Add it to {PROJECT_ROOT / '.env'} "
            "or the process environment."
        )
    return Redis.from_url(valkey_url, decode_responses=True)


def cache_aside(
    key: str,
    ttl_seconds: int,
    compute: Callable[[], T],
) -> tuple[T, str]:
    """Return cached JSON when present, otherwise compute and cache the value."""
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be a positive integer")

    client = get_cache_client()
    cached_json = client.get(key)
    if cached_json is not None:
        return json.loads(cached_json), "hit"

    value = compute()
    client.set(key, json.dumps(value), ex=ttl_seconds)
    return value, "miss"


def delete_by_prefix(prefix: str) -> int:
    """Delete matching cache keys using incremental SCAN rather than KEYS."""
    if not prefix:
        raise ValueError("prefix cannot be empty")

    client = get_cache_client()
    deleted_count = 0
    for key in client.scan_iter(match=f"{prefix}*"):
        deleted_count += int(client.delete(key))
    return deleted_count


def degradation_cache_key(year: int, circuit: str, compound: str) -> str:
    """Build the documented per-circuit, per-compound degradation key."""
    return f"f1:deg:{year}:{circuit}:{compound.upper()}"


def cached_degradation_slopes(
    year: int,
    circuit: str,
    compound: str,
    compute: Callable[[], list[dict[str, Any]]],
    ttl_seconds: int = 3600,
) -> tuple[list[dict[str, Any]], str]:
    """Cache degradation-slope rows using the project's standard key format."""
    key = degradation_cache_key(year, circuit, compound)
    return cache_aside(key, ttl_seconds, compute)
