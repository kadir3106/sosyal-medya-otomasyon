from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.build_weekly_report", return_value="📊 Haftalık Rapor...")
def test_analytics_weekly_returns_report(mock_report):
    response = client.get("/analytics/weekly")

    assert response.status_code == 200
    assert response.json() == {"report": "📊 Haftalık Rapor..."}
