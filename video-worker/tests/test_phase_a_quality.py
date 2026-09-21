"""Phase A: niche lock, hook/TTS telemetry, approval caption, emoji flag."""

import json
from unittest.mock import AsyncMock, patch

from app.config import Config
from app.pipeline import _extract_hook, format_approval_caption, generate_video


def test_config_default_topics_path_is_dark_wealth():
    assert Config.TOPICS_PATH.endswith("topics_dark_wealth.json")
    assert Config.TOPICS_PATH_TR.endswith("video_topics_tr.json")


def test_config_subtitle_emojis_default_off():
    assert Config.ENABLE_SUBTITLE_EMOJIS is False


def test_extract_hook_takes_first_sentence():
    script = "They refused my cash. Then they named a price you cannot see."
    assert _extract_hook(script) == "They refused my cash."


def test_extract_hook_truncates_long_opening():
    words = " ".join(f"w{i}" for i in range(20))
    hook = _extract_hook(words, max_words=8)
    assert hook == "w0 w1 w2 w3 w4 w5 w6 w7…"


def test_format_approval_caption_includes_hook_tts_reuse():
    caption = format_approval_caption(
        {
            "title": "Why They Refused",
            "description": "Hidden price. #DarkWealth",
            "quality": {
                "hook": "They refused my cash.",
                "clip_reuse_ratio": 1.0,
                "tts": "elevenlabs",
                "engine": "hybrid",
            },
        }
    )
    assert "Why They Refused" in caption
    assert "They refused my cash." in caption
    assert "tekrar 1.0x" in caption
    assert "TTS `elevenlabs`" in caption
    assert "hybrid" in caption
    assert "onaylıyor musun" in caption.lower()


def test_format_approval_caption_flags_edge_and_reuse():
    edge = format_approval_caption(
        {
            "title": "T",
            "description": "D",
            "quality": {"hook": "H", "tts": "edge", "warning": "tts_edge_fallback", "engine": "stock"},
        }
    )
    assert "Edge TTS" in edge

    reuse = format_approval_caption(
        {
            "title": "T",
            "description": "D",
            "quality": {
                "hook": "H",
                "tts": "elevenlabs",
                "clip_reuse_ratio": 2.0,
                "warning": "clip_reuse_ratio_high",
                "engine": "stock",
            },
        }
    )
    assert "TEKRAR YÜKSEK" in reuse


@patch("app.pipeline._notify_telegram_awaiting_approval")
@patch("app.pipeline.render_card")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=["/work/clip_0.mp4"])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_persists_quality_telemetry(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, mock_thumb, mock_tg, tmp_path
):
    mock_topic.return_value = "Wealth Topic"
    mock_script.return_value = {
        "script": "They refused my cash at the counter. Status is the real product.",
        "title": "Why They Refused",
        "description": "Hidden. #DarkWealth",
        "tags": ["wealth"],
        "visual_prompts": ["Rolex crown macro chiaroscuro"],
        "concrete_nouns": ["Rolex", "crown"],
    }

    async def _tts(text, path, voice=None, rate=None, meta_out=None):
        if meta_out is not None:
            meta_out["provider"] = "elevenlabs"
        return [{"offset": 0, "duration": 10_000_000, "text": "They"}]

    mock_tts.side_effect = _tts
    mock_subtitle.return_value = "/work/subs.ass"

    def fake_render(*args, **kwargs):
        stats = kwargs.get("stats_out")
        if stats is not None:
            stats.update(
                {
                    "scene_count": 10,
                    "clip_count": 10,
                    "clip_reuse_ratio": 1.0,
                    "audio_duration": 22.0,
                }
            )
        return args[3]

    mock_render.side_effect = fake_render

    with patch("app.pipeline.config") as mock_config, \
         patch(
             "app.ai_video_engine.generate_video_scenes",
             return_value=["/work/clip_0.mp4"],
         ):
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.ENABLE_SFX = False
        mock_config.ENABLE_SUBTITLE_EMOJIS = False
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.VISUAL_ENGINE = "flux_kenburns"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.CINEMATIC_GRADE = True
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        mock_config.VIDEO_LANG = "en"
        mock_config.VIDEO_VOICE = ""
        mock_config.VIDEO_VOICE_RATE = "+0%"
        mock_config.TOPICS_PATH = "/app/data/topics_dark_wealth.json"
        mock_config.TOPICS_PATH_TR = "/app/data/video_topics_tr.json"
        mock_config.ENABLE_ANALYTICS_MEMORY = False
        with patch("app.pipeline.get_audio_duration", return_value=22.0):
            result = await generate_video("job_qa")

    q = result["quality"]
    assert q["hook"].startswith("They refused my cash")
    assert q["tts"] == "elevenlabs"
    assert q["engine"] == "flux_kenburns"
    assert q["clip_reuse_ratio"] == 1.0
    assert "warning" not in q

    pending = json.loads((tmp_path / "pending.json").read_text(encoding="utf-8"))
    assert pending["quality"]["tts"] == "elevenlabs"
    assert pending["quality"]["hook"]

    # Subtitles: emoji flag off
    assert mock_subtitle.call_args.kwargs["add_emojis"] is False


@patch("app.pipeline._notify_telegram_awaiting_approval")
@patch("app.pipeline.render_card")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=["/work/clip_0.mp4"])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_marks_edge_tts_warning(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, mock_thumb, mock_tg, tmp_path
):
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "Short hook sentence here for preview.",
        "title": "T",
        "description": "D",
        "tags": [],
    }

    async def _tts(text, path, voice=None, rate=None, meta_out=None):
        if meta_out is not None:
            meta_out["provider"] = "edge"
            meta_out["edge_reason"] = "missing_key"
        return [{"offset": 0, "duration": 1, "text": "Short"}]

    mock_tts.side_effect = _tts
    mock_subtitle.return_value = "/work/subs.ass"

    def fake_render(*args, **kwargs):
        stats = kwargs.get("stats_out")
        if stats is not None:
            stats.update(
                {"scene_count": 5, "clip_count": 5, "clip_reuse_ratio": 1.0, "audio_duration": 12.0}
            )
        return args[3]

    mock_render.side_effect = fake_render

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.ENABLE_SFX = False
        mock_config.ENABLE_SUBTITLE_EMOJIS = False
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.VISUAL_ENGINE = "stock"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.CINEMATIC_GRADE = True
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        mock_config.VIDEO_LANG = "en"
        mock_config.VIDEO_VOICE = ""
        mock_config.VIDEO_VOICE_RATE = "+12%"
        mock_config.ENABLE_ANALYTICS_MEMORY = False
        with patch("app.pipeline.get_audio_duration", return_value=12.0):
            result = await generate_video("job_edge")

    assert result["quality"]["tts"] == "edge"
    assert result["quality"]["warning"] == "tts_edge_fallback"
