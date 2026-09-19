from unittest.mock import patch, MagicMock
from app.ai_video_engine import generate_video_scenes
from app.config import config


def _with_isolated_media(tmp_path):
    """Prompt hafızası gerçek video-output klasörüne yazmasın (test izolasyonu)."""
    return patch.object(config, "MEDIA_DIR", str(tmp_path))


def test_hybrid_visual_engine_uses_kling_for_hook_only(tmp_path):
    with patch.object(config, "FAL_KEY", "mock_fal_key"), \
         patch.object(config, "VISUAL_ENGINE", "hybrid"), \
         _with_isolated_media(tmp_path), \
         patch("app.ai_video_engine.generate_kling_video_clip") as mock_kling, \
         patch("app.stock_media.fetch_stock_clips") as mock_stock:

        mock_kling.return_value = str(tmp_path / "clip_0.mp4")
        mock_stock.return_value = [
            str(tmp_path / "clip_1.mp4"),
            str(tmp_path / "clip_2.mp4"),
        ]

        prompts = ["Scene 1 Hook", "Scene 2 Story", "Scene 3 Ending"]
        clips = generate_video_scenes(prompts, str(tmp_path), clip_duration=2.5)

        # Kling sadece 1 kez (ilk kanca sahnesi için) çağrılmalı
        assert mock_kling.call_count == 1
        assert mock_kling.call_args[0][0].startswith("Scene 1 Hook")

        # Kalan sahneler için gerçek hareketli stok video aranmalı (statik slayt yok!)
        assert mock_stock.call_count >= 1
        assert len(clips) == 3


def test_kling_engine_produces_multiple_scenes_up_to_cap(tmp_path):
    """'kling' modu seçildiğinde tek sahne değil, tavan kadar sahne Kling'den gelir."""
    with patch.object(config, "FAL_KEY", "mock_fal_key"), \
         patch.object(config, "VISUAL_ENGINE", "kling"), \
         patch.object(config, "KLING_MAX_SCENES", 2), \
         _with_isolated_media(tmp_path), \
         patch("app.ai_video_engine.generate_kling_video_clip") as mock_kling, \
         patch("app.stock_media.fetch_stock_clips") as mock_stock:

        mock_kling.side_effect = lambda prompt, path, key, **kw: path
        mock_stock.return_value = [str(tmp_path / "clip_2.mp4")]

        clips = generate_video_scenes(
            ["A", "B", "C"], str(tmp_path), target_count=3
        )

        assert mock_kling.call_count == 2  # tavan = 2
        assert len(clips) == 3


def test_short_prompt_list_is_expanded_to_target_count(tmp_path):
    """Prompt listesi kısa kalsa bile istenen sahne sayısı kadar klip üretilir.

    Eskiden liste kısa kalınca render klipleri başa sarıyordu (slayt hissi).
    """
    with patch.object(config, "FAL_KEY", ""), \
         patch.object(config, "VISUAL_ENGINE", "stock"), \
         _with_isolated_media(tmp_path), \
         patch("app.stock_media.fetch_stock_clips") as mock_stock:

        mock_stock.side_effect = lambda keywords, count, **kw: [
            str(tmp_path / f"c{i}.mp4") for i in range(count)
        ]

        clips = generate_video_scenes(
            ["Only one prompt"], str(tmp_path), target_count=6
        )

        # Stok katmanı 6 sahne ister: render'a yetecek kadar klip döner.
        assert mock_stock.call_args.kwargs["count"] == 6
        assert len(clips) == 6


def test_prompt_expansion_adds_distinct_camera_angles():
    """Aynı prompt tekrarlanırken farklı kamera açısı eklenir (aynı kare olmasın)."""
    from app.ai_video_engine import _expand_prompts

    expanded = _expand_prompts(["dark city"], 3)

    assert len(expanded) == 3
    assert expanded[0] == "dark city"
    assert len(set(expanded)) == 3  # hiçbiri birebir aynı değil


def test_repeated_prompts_get_refreshed_on_second_run(tmp_path):
    """Aynı prompt ikinci kez gelirse varyasyonla tazelenir (aynı görsel üretilmesin)."""
    from app.ai_video_engine import refresh_repeated_prompts

    state = str(tmp_path / "used_prompts.json")
    prompts = ["dark marble statue", "rainy city night"]

    first = refresh_repeated_prompts(prompts, state)
    assert first == prompts  # ilk kez: değişiklik yok

    second = refresh_repeated_prompts(prompts, state)
    assert second != first
    assert all(p.startswith(orig) for p, orig in zip(second, prompts))
    # Tazelenen prompt artık yeni bir parmak izi taşır (sonsuz döngü olmaz).
    third = refresh_repeated_prompts(prompts, state)
    assert third != second


def test_prompt_history_survives_corrupt_state_file(tmp_path):
    """Bozuk state dosyası üretimi durdurmaz, sıfırdan başlanır."""
    from app.ai_video_engine import refresh_repeated_prompts

    state = tmp_path / "used_prompts.json"
    state.write_text("{bozuk json", encoding="utf-8")

    assert refresh_repeated_prompts(["prompt"], str(state)) == ["prompt"]

