import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_appends_to_log(mock_yt, mock_tt, mock_ig, mock_fb, tmp_path):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_yt.return_value = {
        "platform": "youtube", "status": "success", "video_id": "yt1"
    }
    mock_tt.return_value = {
        "platform": "tiktok", "status": "success", "publish_id": "tt1"
    }
    mock_ig.return_value = {
        "platform": "instagram", "status": "success", "media_id": "ig1"
    }
    mock_fb.return_value = {
        "platform": "facebook", "status": "success", "video_id": "fb1"
    }

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
                "title": "Why Flamingos Stand on One Leg",
                "description": "d",
                "tags": [],
            },
        )

    log_path = tmp_path / "published_log.json"
    assert log_path.exists()
    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["title"] == "Why Flamingos Stand on One Leg"
    assert entries[0]["platforms"]["youtube"]["video_id"] == "yt1"
