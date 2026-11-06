import pytest

from f1engine import leaderboard


class FakeSortedSetClient:
    """Small in-memory sorted-set stand-in for Valkey unit tests."""

    def __init__(self):
        self.values = {}

    def zadd(self, key, mapping, lt=False, ch=False):
        members = self.values.setdefault(key, {})
        changed = 0
        for member, score in mapping.items():
            old_score = members.get(member)
            if old_score is None or (lt and score < old_score):
                members[member] = score
                changed += 1
        return changed

    def zrange(self, key, start, end, withscores=False):
        members = sorted(
            self.values.get(key, {}).items(),
            key=lambda item: (item[1], item[0]),
        )
        selected = members[start : end + 1]
        return selected if withscores else [member for member, _ in selected]

    def zrank(self, key, member):
        members = sorted(
            self.values.get(key, {}).items(),
            key=lambda item: (item[1], item[0]),
        )
        for index, (candidate, _) in enumerate(members):
            if candidate == member:
                return index
        return None


def test_update_from_lap_keeps_only_improved_time(monkeypatch):
    client = FakeSortedSetClient()
    monkeypatch.setattr(leaderboard, "get_cache_client", lambda: client)

    assert leaderboard.update_from_lap(2024, 1, "VER", 92.5) is True
    assert leaderboard.update_from_lap(2024, 1, "VER", 93.0) is False
    assert leaderboard.update_from_lap(2024, 1, "VER", 92.1) is True

    assert leaderboard.top_n(2024, 1) == [("VER", 92.1)]
    assert leaderboard.rank_of(2024, 1, "VER") == 0
    assert leaderboard.rank_of(2024, 1, "LEC") is None


def test_leaderboard_key_and_invalid_lap_time(monkeypatch):
    client = FakeSortedSetClient()
    monkeypatch.setattr(leaderboard, "get_cache_client", lambda: client)

    assert leaderboard.leaderboard_key(2024, 1) == "f1:leaderboard:2024:1"
    with pytest.raises(ValueError, match="positive finite number"):
        leaderboard.update_from_lap(2024, 1, "VER", float("nan"))
