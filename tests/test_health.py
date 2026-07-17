from fastapi.testclient import TestClient

from memory_ai.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/health")

    assert response.status_code == 200


def test_health_returns_expected_body() -> None:
    response = client.get("/health")

    assert response.json() == {"status": "ok"}


def test_health_rejects_post() -> None:
    response = client.post("/health")

    assert response.status_code == 405
