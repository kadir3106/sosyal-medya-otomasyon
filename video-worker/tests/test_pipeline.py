from unittest.mock import patch, AsyncMock

from app.pipeline import generate_video


@patch("app.pipeline.render_card")
@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_runs_full_pipeline(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render,
    mock_thumb, tmp_path
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

    mock_script.assert_called_once_with(
        "Why flamingos stand on one leg", api_key="or-key", lang="en"
    )
    assert mock_clips.call_args.kwargs["api_key"] == "px-key"


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_plans_scenes_from_audio_duration(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, tmp_path
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
        mock_config.VIDEO_FORMAT = "cinematic"
        mock_config.CINEMATIC_GRADE = True
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        with patch("app.pipeline.get_audio_duration", return_value=30.9):
            await generate_video("job_scenes")

    # 30.9 sn ses + 2.2 sn taban kurgu -> 15 sahne (sabit 10 değil).
    requested = mock_clips.call_args.kwargs["count"]
    assert requested >= 14
    # Render'a aynı sahne sayısı bildirilir (üretim ile kurgu senkron).
    assert mock_render.call_args.kwargs["clip_duration"] == 2.2
    assert mock_render.call_args.kwargs["xfade_duration"] == 0.4


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=["/work/clip_0.mp4"])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_flags_high_clip_reuse(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, tmp_path
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


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_ass")
@patch("app.pipeline.fetch_stock_clips", return_value=["/work/clip_0.mp4"])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_no_warning_when_reuse_is_clean(
    mock_topic, mock_script, mock_tts, mock_clips, mock_subtitle, mock_render, tmp_path
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
        try:
            await generate_video("job456")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "no stock clips" in str(exc).lower()


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
    mock_ai_img, mock_motion, mock_fetch_sat, mock_split_render, tmp_path
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
        mock_config.IMAGE_BRAND_NAME = "KALI"
        mock_config.IMAGE_ACCENT = "#38BDF8"
        mock_config.BGM_DIR = ""
        result = await generate_video("split123")

    assert result["job_id"] == "split123"
    assert result["title"] == "Never Whistle at Night"
    assert result["video_filename"] == "split123.mp4"
    mock_split_render.assert_called_once()
    mock_ai_img.assert_called_once()
    mock_fetch_sat.assert_called_once()

