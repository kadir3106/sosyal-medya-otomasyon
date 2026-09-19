import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_pending_returns_stored_job(tmp_path):
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps({"job_id": "job1", "title": "t"}), encoding="utf-8"
    )

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/pending")

    assert response.status_code == 200
    assert response.json() == {"job_id": "job1", "title": "t"}


def test_get_pending_returns_404_when_none(tmp_path):
    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/pending")

    assert response.status_code == 404


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_clears_pending_json(mock_yt, mock_tt, mock_ig, mock_fb, tmp_path):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(json.dumps({"job_id": "job123"}), encoding="utf-8")

    mock_yt.return_value = {"platform": "youtube", "status": "success"}
    mock_tt.return_value = {"platform": "tiktok", "status": "success"}
    mock_ig.return_value = {"platform": "instagram", "status": "success"}
    mock_fb.return_value = {"platform": "facebook", "status": "success"}

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.YOUTUBE_CLIENT_ID = ""
        mock_config.YOUTUBE_CLIENT_SECRET = ""
        mock_config.YOUTUBE_REFRESH_TOKEN = ""
        mock_config.TIKTOK_CLIENT_KEY = ""
        mock_config.TIKTOK_CLIENT_SECRET = ""
        mock_config.TIKTOK_TOKEN_PATH = ""
        mock_config.TIKTOK_AUDITED = False
        mock_config.META_IG_USER_ID = ""
        mock_config.META_PAGE_ACCESS_TOKEN = ""
        mock_config.TUNNEL_LOG_PATH = ""
        mock_config.META_PAGE_ID = ""
        client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job123.mp4",
                "title": "t",
                "description": "d",
                "tags": [],
            },
        )

    assert not pending_path.exists()


def test_cleanup_clears_pending_json(tmp_path):
    media_file = tmp_path / "reject-me.mp4"
    media_file.write_bytes(b"X")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(json.dumps({"job_id": "job1"}), encoding="utf-8")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        client.delete("/cleanup/reject-me.mp4")

    assert not pending_path.exists()
