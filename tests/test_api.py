from dataclasses import dataclass

from fastapi.testclient import TestClient
import pytest

from f1engine import api, leaderboard, models


client = TestClient(api.app)


@dataclass
class Prediction:
    estimate: float
    reliable: bool


def test_health():
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("prediction", "expected"),
    [
        ({"estimate": 0.2, "reliable": True}, {"estimate": 0.2, "reliable": True}),
        (Prediction(0.2, True), {"estimate": 0.2, "reliable": True}),
    ],
)
def test_degradation_serializes_dict_or_dataclass(monkeypatch, prediction, expected):
    calls = []

    def fake_predict(circuit, compound, tyre_life):
        calls.append((circuit, compound, tyre_life))
        return prediction

    monkeypatch.setattr(models, "predict_degradation", fake_predict)

    response = client.get(
        "/degradation",
        params={"circuit": "Monza", "compound": "MEDIUM", "tyre_life": 5},
    )

    assert response.status_code == 200
    assert response.json() == expected
    assert calls == [("Monza", "MEDIUM", 5)]


def test_leaderboard_uses_valkey_top_n(monkeypatch):
    calls = []
    expected = [("VER", 92.5), ("LEC", 93.1)]

    def fake_top_n(year, round_number, n):
        calls.append((year, round_number, n))
        return expected

    monkeypatch.setattr(leaderboard, "top_n", fake_top_n)

    response = client.get("/leaderboard/2024/1", params={"n": 2})

    assert response.status_code == 200
    assert response.json() == [["VER", 92.5], ["LEC", 93.1]]
    assert calls == [(2024, 1, 2)]
