import json
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.generate_video", new_callable=AsyncMock)
def test_generate_endpoint_returns_pipeline_result(mock_generate, tmp_path):
    mock_generate.return_value = {
        "job_id": "20260903-120000",
        "video_path": str(tmp_path / "20260903-120000.mp4"),
        "video_filename": "20260903-120000.mp4",
        "topic": "Why flamingos stand on one leg",
        "title": "Why Flamingos Stand on One Leg",
        "description": "Surprising science. #flamingo",
        "tags": ["flamingo"],
    }

    with patch("app.main.config.MEDIA_DIR", str(tmp_path)):
        response = client.post("/generate")

    assert response.status_code == 200
    assert response.json()["video_filename"] == "20260903-120000.mp4"
    assert mock_generate.await_count == 1


@patch("app.main.generate_video", new_callable=AsyncMock)
def test_generate_endpoint_returns_500_on_pipeline_error(mock_generate, tmp_path):
    mock_generate.side_effect = RuntimeError("Pexels returned no stock clips")

    with patch("app.main.config.MEDIA_DIR", str(tmp_path)):
        response = client.post("/generate")

    assert response.status_code == 500
    assert "no stock clips" in response.json()["detail"]


@patch("app.main.generate_video", new_callable=AsyncMock)
def test_generate_endpoint_returns_409_when_pending_already_exists(
    mock_generate, tmp_path
):
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps({"job_id": "prior-job", "video_filename": "prior-job.mp4"}),
        encoding="utf-8",
    )

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.post("/generate")

    assert response.status_code == 409
    assert "pending approval" in response.json()["detail"]
    mock_generate.assert_not_called()


@patch("app.main.send_pitches_message")
@patch("app.main.generate_pitches")
@patch("app.main.fetch_trends")
def test_discover_ideas_endpoint(mock_trends, mock_pitches, mock_send_tg, tmp_path):
    mock_trends.return_value = [{"title": "Trend A", "description": "Desc A"}]
    mock_pitches.return_value = [
        {"id": 1, "title": "Pitch 1", "hook": "H1", "topic": "Top 1", "category_label": "😂 Komedi"}
    ]

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "key"
        mock_config.VIDEO_LANG = "tr"
        mock_config.TELEGRAM_BOT_TOKEN = "tok"
        mock_config.TELEGRAM_CHAT_ID = "123"

        response = client.post("/discover-ideas")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert len(response.json()["pitches"]) == 1
    assert (tmp_path / "pending_pitches.json").is_file()
    assert mock_send_tg.called

