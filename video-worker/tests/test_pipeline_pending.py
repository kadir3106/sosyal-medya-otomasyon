import json
from unittest.mock import patch, AsyncMock

from app.pipeline import generate_video


@patch("app.pipeline.render_card")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_writes_pending_json(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render,
    mock_thumb, tmp_path
):
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "text", "title": "Title", "description": "Desc", "tags": ["a"]
    }
    mock_tts.return_value = [{"offset": 0, "duration": 1, "text": "x"}]
    mock_clips.return_value = ["/work/clip_0.mp4"]
    mock_subtitle.return_value = "/work/subs.ass"
    mock_render.side_effect = lambda *a, **k: a[3]

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        result = await generate_video("job789")

    pending_path = tmp_path / "pending.json"
    assert pending_path.exists()
    assert json.loads(pending_path.read_text(encoding="utf-8")) == result
