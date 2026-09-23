from unittest.mock import patch, AsyncMock

import pytest

from app.pipeline import generate_video


@patch("app.pipeline._notify_telegram_awaiting_approval")
@patch("app.pipeline.render_card")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_runs_full_pipeline(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render,
    mock_thumb, mock_tg, tmp_path
):
    mock_topic.return_value = "Why flamingos stand on one leg"
    mock_script.return_value = {
        "script": "Flamingos conserve heat by standing on one leg.",
        "title": "Why Flamingos Stand on One Leg",
        "description": "Surprising science. #flamingo #facts",
        "tags": ["flamingo", "nature"],
    }
    mock_tts.return_value = [{"offset": 0, "duration": 10_000_000, "text": "Flamingos"}]
    mock_clips.return_value = ["/work/clip_0.mp4"]
    mock_subtitle.return_value = "/work/subs.ass"
    mock_render.side_effect = lambda *a, **k: a[3]

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.PIXABAY_API_KEY = ""
        mock_config.ENABLE_MIXKIT_STOCK = False
        mock_config.VISUAL_ENGINE = "stock"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.ENABLE_SFX = False
        mock_config.ENABLE_ANALYTICS_MEMORY = False
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.CINEMATIC_GRADE = True
        mock_config.BGM_DIR = ""
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.TELEGRAM_BOT_TOKEN = ""
        mock_config.TELEGRAM_CHAT_ID = ""
        result = await generate_video("job123")

    assert result["job_id"] == "job123"
    assert result["topic"] == "Why flamingos stand on one leg"
    assert result["title"] == "Why Flamingos Stand on One Leg"
    assert result["description"] == "Surprising science. #flamingo #facts"
    assert result["tags"] == ["flamingo", "nature"]
    assert result["video_filename"] == "job123.mp4"
    assert result["video_path"] == str(tmp_path / "job123.mp4")
    assert result["thumbnail_path"] == str(tmp_path / "job123_thumb.png")
    mock_thumb.assert_called_once_with(
        "Why Flamingos Stand on One Leg",
        brand_name=mock_config.IMAGE_BRAND_NAME,
        accent=mock_config.IMAGE_ACCENT,
        output_path=str(tmp_path / "job123_thumb.png"),
    )
    mock_tg.assert_called_once()

    assert mock_script.call_args.args[0] == "Why flamingos stand on one leg"
    assert mock_script.call_args.kwargs["api_key"] == "or-key"
    assert mock_script.call_args.kwargs["lang"] == "en"
    assert mock_clips.call_args.kwargs["api_key"] == "px-key"
    assert mock_render.call_args.kwargs.get("apply_zoompan") is False



@patch("app.pipeline._notify_telegram_awaiting_approval")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_plans_scenes_from_audio_duration(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, mock_tg, tmp_path
):
    """Sahne sayısı sabit değil, ses süresinden hesaplanır ve klipler o sayıda istenir."""
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "text", "title": "t", "description": "d", "tags": []
    }
    mock_tts.return_value = [{"offset": 0, "duration": 10_000_000, "text": "t"}]
    mock_clips.return_value = ["/work/clip_0.mp4"]
    mock_subtitle.return_value = "/work/subs.ass"
    mock_render.side_effect = lambda *a, **k: a[3]

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.ENABLE_SFX = False
        mock_config.VISUAL_ENGINE = "stock"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.CINEMATIC_GRADE = True
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        with patch("app.pipeline.get_audio_duration", return_value=30.9):
            await generate_video("job_scenes")

    requested = mock_clips.call_args.kwargs["count"]
    # Stock path caps at STOCK_MAX_SCENES (8); still duration-driven within that cap.
    assert 1 <= requested <= 8
    assert mock_render.call_args.kwargs["clip_duration"] == 2.2
    assert mock_render.call_args.kwargs["xfade_duration"] == 0.4


@patch("app.pipeline._notify_telegram_awaiting_approval")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=["/work/clip_0.mp4"])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_flags_high_clip_reuse(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, mock_tg, tmp_path
):
    """Tekrar oranı yüksekse sonuç uyarı taşır: slayt hissi sessizce gizlenmez."""
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "text", "title": "t", "description": "d", "tags": []
    }
    mock_tts.return_value = [{"offset": 0, "duration": 10_000_000, "text": "t"}]
    mock_subtitle.return_value = "/work/subs.ass"

    def fake_render(*args, **kwargs):
        stats = kwargs.get("stats_out")
        if stats is not None:
            stats.update(
                {
                    "scene_count": 15,
                    "clip_count": 1,
                    "clip_reuse_ratio": 15.0,
                    "audio_duration": 30.9,
                }
            )
        return args[3]

    mock_render.side_effect = fake_render

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.ENABLE_SFX = False
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.VISUAL_ENGINE = "stock"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.CINEMATIC_GRADE = True
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        with patch("app.pipeline.get_audio_duration", return_value=30.9):
            result = await generate_video("job_reuse")

    quality = result["quality"]
    assert quality["clip_reuse_ratio"] == 15.0
    assert quality["scene_count"] == 15
    assert quality["warning"] == "clip_reuse_ratio_high"


@patch("app.pipeline._notify_telegram_awaiting_approval")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=["/work/clip_0.mp4"])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_no_warning_when_reuse_is_clean(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, mock_tg, tmp_path
):
    """Tekrar oranı düşükse (1.0x) kalite uyarısı yok."""
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "text", "title": "t", "description": "d", "tags": []
    }
    mock_tts.return_value = [{"offset": 0, "duration": 10_000_000, "text": "t"}]
    mock_subtitle.return_value = "/work/subs.ass"

    def fake_render(*args, **kwargs):
        stats = kwargs.get("stats_out")
        if stats is not None:
            stats.update(
                {
                    "scene_count": 15,
                    "clip_count": 15,
                    "clip_reuse_ratio": 1.0,
                    "audio_duration": 30.9,
                }
            )
        return args[3]

    mock_render.side_effect = fake_render

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.ENABLE_SFX = False
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.VISUAL_ENGINE = "stock"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.CINEMATIC_GRADE = True
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        with patch("app.pipeline.get_audio_duration", return_value=30.9):
            result = await generate_video("job_clean")

    quality = result["quality"]
    assert quality["clip_reuse_ratio"] == 1.0
    assert "warning" not in quality


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=[])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
@patch("app.pipeline.release_topic")
async def test_generate_video_releases_topic_on_failure(
    mock_release, mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, tmp_path
):
    mock_topic.return_value = "Topic X"
    mock_script.return_value = {
        "script": "text", "title": "t", "description": "d", "tags": []
    }
    mock_tts.return_value = []

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.VISUAL_ENGINE = "stock"
        mock_config.ALLOW_STOCK_FALLBACK = False
        try:
            await generate_video("job456")
            assert False, "expected RuntimeError"
        except RuntimeError:
            pass

    mock_release.assert_called_once_with(
        "Topic X", str(tmp_path / "used_topics.json")
    )


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=[])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_raises_when_no_clips_downloaded(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, tmp_path
):
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "text", "title": "t", "description": "d", "tags": []
    }
    mock_tts.return_value = []
    mock_subtitle.return_value = "/work/subs.ass"

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.VISUAL_ENGINE = "stock"
        mock_config.ALLOW_STOCK_FALLBACK = False
        try:
            await generate_video("job456")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "no stock clips" in str(exc).lower() or "could be generated" in str(exc).lower()


@patch("app.pipeline._notify_telegram_awaiting_approval")
@patch("app.split_screen.render_split_screen_video")
@patch("app.split_screen.fetch_satisfying_clip")
@patch("app.ai_visuals.image_to_motion_clip")
@patch("app.ai_visuals.generate_ai_image")
@patch("app.pipeline.render_card")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_split_screen_format(
    mock_topic, mock_script, mock_tts, mock_subtitle, mock_card,
    mock_ai_img, mock_motion, mock_fetch_sat, mock_split_render, mock_tg, tmp_path
):
    mock_topic.return_value = "Split Screen Story"
    mock_script.return_value = {
        "script": "Mysterious story",
        "title": "Never Whistle at Night",
        "description": "Scary story",
        "tags": ["mystery"],
        "visual_prompts": ["dark forest"],
    }
    mock_tts.return_value = [{"offset": 0, "duration": 10_000_000, "text": "Mysterious"}]
    mock_subtitle.return_value = "/work/subs.ass"
    mock_split_render.side_effect = lambda *a, **k: a[4]

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.VIDEO_FORMAT = "split_screen"
        mock_config.VISUAL_ENGINE = "flux_kenburns"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.FAL_KEY = ""
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        mock_config.ENABLE_SFX = False
        result = await generate_video("split123")

    assert result["job_id"] == "split123"
    assert result["title"] == "Never Whistle at Night"
    assert result["video_filename"] == "split123.mp4"
    mock_split_render.assert_called_once()
    mock_ai_img.assert_called_once()
    mock_fetch_sat.assert_called_once()
    mock_tg.assert_called_once()


@patch("app.pipeline.write_ass")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_hard_fails_on_kling_auth_billing(
    mock_topic, mock_script, mock_tts, mock_subtitle, tmp_path
):
    """Fal 403 → job failed + kling_auth_or_billing_fail log + Telegram; Pexels yok."""
    from app import jobs as job_store
    from app.errors import KlingAuthBillingError
    from app.pipeline import KLING_AUTH_BILLING_TELEGRAM

    mock_topic.return_value = "Rolex Swiss Vault"
    mock_script.return_value = {
        "script": "Trust takes decades.",
        "title": "Rolex Trust",
        "description": "d",
        "tags": ["rolex"],
        "visual_prompts": ["rolex vault swiss"],
        "concrete_nouns": ["Rolex", "vault", "Swiss"],
    }
    mock_tts.return_value = [{"offset": 0, "duration": 10_000_000, "text": "Trust"}]
    mock_subtitle.return_value = "/work/subs.ass"

    with patch("app.pipeline.config") as mock_config, \
         patch("app.pipeline.get_audio_duration", return_value=12.0), \
         patch(
             "app.ai_video_engine.generate_video_scenes",
             side_effect=KlingAuthBillingError(
                 "forbidden", status_code=403, detail="Exhausted balance"
             ),
         ) as mock_scenes, \
         patch("app.pipeline.log_event") as mock_log, \
         patch("app.telegram_bot.send_message") as mock_tg, \
         patch("app.pipeline.fetch_stock_clips") as mock_stock:

        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        mock_config.ENABLE_SFX = False
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.VISUAL_ENGINE = "hybrid"
        mock_config.ALLOW_STOCK_FALLBACK = False
        mock_config.TELEGRAM_BOT_TOKEN = "tok"
        mock_config.TELEGRAM_CHAT_ID = "chat"
        mock_config.BGM_DIR = ""
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"

        with pytest.raises(KlingAuthBillingError):
            await generate_video("job_kling_403")

    mock_scenes.assert_called_once()
    mock_stock.assert_not_called()
    stages = [c.args[1] for c in mock_log.call_args_list if len(c.args) > 1]
    assert "kling_auth_or_billing_fail" in stages
    assert mock_tg.called
    assert KLING_AUTH_BILLING_TELEGRAM in mock_tg.call_args.args[2]
    job = job_store.get_job(tmp_path, "job_kling_403")
    assert job is not None
    assert job["state"] == "failed"
