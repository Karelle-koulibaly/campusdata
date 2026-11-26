"""Préparation commune aux tests : base campus_test vidée avant chaque test."""
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

# Sécurité : refuser de lancer les tests ailleurs que sur une base *_test.
assert os.environ["DATABASE_URL"].endswith("_test"), "DATABASE_URL doit cibler campus_test"

from app.database import engine  # noqa: E402
from app.main import app  # noqa: E402

DATA = Path(__file__).resolve().parents[2] / "data"


@pytest.fixture(autouse=True)
def clean_database():
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE datasets CASCADE"))


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def dataset_id(client):
    return client.post("/api/datasets", json={"name": "Jeu de test"}).json()["id"]


def upload(client, dataset_id, filename):
    """Déposer un fichier de data/ et renvoyer la réponse."""
    return client.post(
        f"/api/datasets/{dataset_id}/ingestions?filename={filename}",
        content=(DATA / filename).read_bytes(),
        headers={"Content-Type": "text/csv"},
    )