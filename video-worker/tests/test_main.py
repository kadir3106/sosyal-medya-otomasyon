from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_tokens_reports_platforms_without_network():
    response = client.get("/health/tokens")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert "platforms" in body
    assert "missing" in body
    for name in (
        "youtube",
        "tiktok",
        "instagram",
        "facebook",
        "threads",
        "x",
        "linkedin",
        "pinterest",
    ):
        assert name in body["platforms"]
        assert isinstance(body["platforms"][name], bool)
