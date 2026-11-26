"""Tests du flux Kafka, SANS Kafka : on appelle directement le simulateur et le consommateur."""
import json
from datetime import datetime, timezone
from itertools import islice

import pytest

from app.simulator import messages
from app.stream import DATASET_NAME, handle, parse_message

NOW = datetime(2026, 11, 16, 10, 0, tzinfo=timezone.utc)  # heure fixe, comme pour les fichiers
VALID = {
    "room": "A101",
    "measured_at": "2026-11-16T09:59:00+00:00",
    "co2_ppm": 712,
    "temperature_c": 20.8,
    "humidity_pct": 46.3,
}


def as_bytes(**changes) -> bytes:
    """Un message JSON valide, avec éventuellement un champ modifié."""
    return json.dumps({**VALID, **changes}).encode()


@pytest.mark.parametrize(
    ("raw", "reason"),
    [
        (b"capteur en panne", "Invalid message"),  # pas du JSON
        (b"[1, 2, 3]", "Invalid message"),  # du JSON, mais pas un objet
        (json.dumps({"room": "A101"}).encode(), "Invalid message"),  # champs manquants
        (as_bytes(co2_ppm=99999), "Invalid co2_ppm"),
        (as_bytes(humidity_pct=140), "Invalid humidity_pct"),
        (as_bytes(measured_at="2030-01-01T00:00:00+00:00"), "measured_at in the future"),
    ],
)
def test_parse_message_rejects(raw, reason):
    with pytest.raises(ValueError) as error:
        parse_message(raw, NOW)
    assert str(error.value) == reason


def test_parse_message_accepts():
    row = parse_message(as_bytes(), NOW)
    assert (row["room"], row["co2_ppm"], row["humidity_pct"]) == ("A101", 712, 46.3)


def test_thirty_simulated_messages(client):
    start = datetime(2026, 11, 16, 9, 0, tzinfo=timezone.utc)
    for _number, _key, value, _kind in islice(messages(start, 10), 30):
        handle(value, NOW)
    stream = next(d for d in client.get("/api/datasets").json() if d["name"] == DATASET_NAME)
    assert stream["measurement_count"] == 24
    [ingestion] = client.get(f"/api/datasets/{stream['id']}/ingestions").json()
    counters = ("rows_total", "rows_accepted", "rows_rejected", "rows_duplicate")
    assert tuple(ingestion[c] for c in counters) == (30, 24, 3, 3)
    assert ingestion["errors"] == [
        {"line": 5, "reason": "Invalid co2_ppm"},
        {"line": 15, "reason": "Invalid message"},
        {"line": 25, "reason": "Invalid humidity_pct"},
    ]