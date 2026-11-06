import json

import pytest

from f1engine import cache


class FakeCacheClient:
    """Tiny in-memory stand-in for Valkey in unit tests."""

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex):
        self.values[key] = value
        return True

    def scan_iter(self, match):
        prefix = match.removesuffix("*")
        return (key for key in list(self.values) if key.startswith(prefix))

    def delete(self, key):
        return int(self.values.pop(key, None) is not None)


def test_cache_aside_reports_miss_then_hit(monkeypatch):
    client = FakeCacheClient()
    monkeypatch.setattr(cache, "get_cache_client", lambda: client)
    calls = []

    def compute():
        calls.append("computed")
        return [{"driver_code": "VER", "slope": 0.02}]

    first_value, first_status = cache.cache_aside(
        "f1:deg:2024:Bahrain Grand Prix:SOFT",
        ttl_seconds=300,
        compute=compute,
    )
    second_value, second_status = cache.cache_aside(
        "f1:deg:2024:Bahrain Grand Prix:SOFT",
        ttl_seconds=300,
        compute=compute,
    )

    assert first_status == "miss"
    assert second_status == "hit"
    assert first_value == second_value
    assert calls == ["computed"]


def test_degradation_key_and_prefix_deletion(monkeypatch):
    client = FakeCacheClient()
    client.values["f1:deg:2024:Bahrain:SOFT"] = json.dumps([1])
    client.values["f1:deg:2024:Bahrain:HARD"] = json.dumps([2])
    client.values["f1:other:2024"] = json.dumps([3])
    monkeypatch.setattr(cache, "get_cache_client", lambda: client)

    assert cache.degradation_cache_key(2024, "Bahrain", "soft") == (
        "f1:deg:2024:Bahrain:SOFT"
    )
    assert cache.delete_by_prefix("f1:deg:2024:") == 2
    assert list(client.values) == ["f1:other:2024"]


def test_cache_aside_rejects_non_positive_ttl(monkeypatch):
    monkeypatch.setattr(cache, "get_cache_client", lambda: FakeCacheClient())

    with pytest.raises(ValueError, match="positive integer"):
        cache.cache_aside("key", 0, lambda: "value")
