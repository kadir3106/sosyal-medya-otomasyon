import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.render_card")
@patch("app.main.generate_image_content")
@patch("app.main.select_next_topic")
def test_generate_image_creates_pending_job(mock_topic, mock_content, mock_render, tmp_path):
    mock_topic.return_value = "Balın neden hiç bozulmadığı"
    mock_content.return_value = {
        "text": "Bal hiç bozulmaz.",
        "caption": "Bunu biliyor muydunuz? #bal #bilgi",
        "hashtags": ["bal", "bilgi"],
    }

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.IMAGE_TOPICS_PATH = str(tmp_path / "image_topics.json")
        (tmp_path / "image_topics.json").write_text(
            json.dumps(["Balın neden hiç bozulmadığı"]), encoding="utf-8"
        )
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"

        response = client.post("/generate-image")

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "image"
    assert body["image_filename"].endswith(".png")
    assert body["topic"] == "Balın neden hiç bozulmadığı"

    pending = json.loads((tmp_path / "pending.json").read_text(encoding="utf-8"))
    assert pending["kind"] == "image"
    assert pending["caption"] == "Bunu biliyor muydunuz? #bal #bilgi"

    mock_render.assert_called_once()
    assert mock_render.call_args.kwargs["brand_name"] == "KALI"


@patch("app.main.render_card")
@patch("app.main.generate_image_content")
@patch("app.main.select_next_topic")
@patch("app.main.release_topic")
def test_generate_image_releases_topic_on_failure(
    mock_release, mock_topic, mock_content, mock_render, tmp_path
):
    mock_topic.return_value = "Topic X"
    mock_content.side_effect = ValueError("LLM bozuk JSON döndürdü")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.IMAGE_TOPICS_PATH = str(tmp_path / "image_topics.json")
        (tmp_path / "image_topics.json").write_text(
            json.dumps(["Topic X"]), encoding="utf-8"
        )
        mock_config.OPENROUTER_API_KEY = "or-key"

        response = client.post("/generate-image")

    assert response.status_code == 500
    assert not (tmp_path / "pending.json").exists()
    mock_release.assert_called_once_with(
        "Topic X", str(tmp_path / "used_image_topics.json")
    )


def test_generate_image_rejects_when_pending_exists(tmp_path):
    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        (tmp_path / "pending.json").write_text("{}", encoding="utf-8")

        response = client.post("/generate-image")

    assert response.status_code == 409
