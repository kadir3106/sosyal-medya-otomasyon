import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_media_returns_file_contents_when_pending_matches(tmp_path):
    media_file = tmp_path / "abc.mp4"
    media_file.write_bytes(b"VIDEOBYTES")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps({"job_id": "abc", "video_filename": "abc.mp4"}),
        encoding="utf-8",
    )

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/abc.mp4")

    assert response.status_code == 200
    assert response.content == b"VIDEOBYTES"


def test_get_media_rejects_path_traversal():
    response = client.get("/media/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)


def test_get_media_returns_404_for_missing_file(tmp_path):
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps({"job_id": "missing", "video_filename": "missing.mp4"}),
        encoding="utf-8",
    )

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/missing.mp4")

    assert response.status_code == 404


def test_get_media_rejects_non_mp4_filename(tmp_path):
    other_file = tmp_path / "used_topics.json"
    other_file.write_text("{}", encoding="utf-8")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps({"job_id": "abc", "video_filename": "abc.mp4"}),
        encoding="utf-8",
    )

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/used_topics.json")

    assert response.status_code == 404


def test_get_media_rejects_mp4_not_matching_pending(tmp_path):
    media_file = tmp_path / "other-job.mp4"
    media_file.write_bytes(b"VIDEOBYTES")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps({"job_id": "abc", "video_filename": "abc.mp4"}),
        encoding="utf-8",
    )

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/other-job.mp4")

    assert response.status_code == 404


def test_get_media_returns_404_when_no_pending_json(tmp_path):
    media_file = tmp_path / "abc.mp4"
    media_file.write_bytes(b"VIDEOBYTES")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/abc.mp4")

    assert response.status_code == 404
