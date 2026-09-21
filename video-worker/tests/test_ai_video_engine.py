from unittest.mock import patch, MagicMock
import pytest
import requests

from app.ai_video_engine import (
    generate_video_scenes,
    generate_kling_video_clip,
    is_kling_auth_or_billing_failure,
    _normalize_engine,
)
from app.config import config
from app.errors import KlingAuthBillingError, FalAuthBillingError


def _with_isolated_media(tmp_path):
    """Prompt hafızası gerçek video-output klasörüne yazmasın (test izolasyonu)."""
    return patch.object(config, "MEDIA_DIR", str(tmp_path))


def test_normalize_engine_aliases():
    assert _normalize_engine("hybrid_flux") == "flux_kenburns"
    assert _normalize_engine("flux") == "flux_kenburns"
    assert _normalize_engine("FLUX_KENBURNS") == "flux_kenburns"
    assert _normalize_engine("hybrid") == "hybrid"
    assert _normalize_engine("kling") == "kling"


def test_flux_kenburns_default_never_calls_kling_or_stock(tmp_path):
    """Default engine: Flux+Ken Burns only; Kling/Pexels not required for success."""
    with patch.object(config, "FAL_KEY", "mock_fal_key"), \
         patch.object(config, "VISUAL_ENGINE", "flux_kenburns"), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch("app.ai_video_engine.generate_kling_video_clip") as mock_kling, \
         patch("app.stock_media.fetch_stock_clips") as mock_stock, \
         patch("app.ai_video_engine.generate_ai_scene_clips") as mock_ai:

        mock_ai.side_effect = lambda prompts, output_dir, **kw: [
            str(tmp_path / f"clip_{kw.get('start_index', 0)}.mp4")
        ]
        stats = {}
        clips = generate_video_scenes(
            ["Rolex crown macro", "Swiss vault door", "Geneva bench"],
            str(tmp_path),
            target_count=3,
            topic="Rolex Swiss trust",
            concrete_nouns=["Rolex", "vault", "Geneva"],
            stats_out=stats,
        )

        assert len(clips) == 3
        assert mock_kling.call_count == 0
        mock_stock.assert_not_called()
        assert mock_ai.call_count == 3
        assert all(s["source"] == "flux_kenburns" for s in stats["scene_relevance"])
        assert stats["kling_scenes"] == 0


def test_hybrid_flux_alias_uses_flux_path(tmp_path):
    with patch.object(config, "FAL_KEY", ""), \
         patch.object(config, "VISUAL_ENGINE", "hybrid_flux"), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch("app.ai_video_engine.generate_kling_video_clip") as mock_kling, \
         patch("app.ai_video_engine.generate_ai_scene_clips") as mock_ai:

        mock_ai.side_effect = lambda prompts, output_dir, **kw: [
            str(tmp_path / f"c{kw.get('start_index', 0)}.mp4")
        ]
        clips = generate_video_scenes(["A", "B"], str(tmp_path), target_count=2)
        assert len(clips) == 2
        mock_kling.assert_not_called()


def test_hybrid_opt_in_uses_kling_for_hook_then_flux(tmp_path):
    with patch.object(config, "FAL_KEY", "mock_fal_key"), \
         patch.object(config, "VISUAL_ENGINE", "hybrid"), \
         patch.object(config, "KLING_MAX_SCENES", 1), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch("app.ai_video_engine.generate_kling_video_clip") as mock_kling, \
         patch("app.stock_media.fetch_stock_clips") as mock_stock, \
         patch("app.ai_video_engine.generate_ai_scene_clips") as mock_ai:

        mock_kling.return_value = str(tmp_path / "clip_0.mp4")
        mock_ai.side_effect = lambda prompts, output_dir, **kw: [
            str(tmp_path / f"clip_{kw.get('start_index', 0)}.mp4")
        ]

        prompts = ["Scene 1 Hook", "Scene 2 Story", "Scene 3 Ending"]
        clips = generate_video_scenes(prompts, str(tmp_path), clip_duration=2.5)

        assert mock_kling.call_count == 1
        assert mock_kling.call_args[0][0].startswith("Scene 1 Hook")
        mock_stock.assert_not_called()
        assert mock_ai.call_count == 2
        assert len(clips) == 3


def test_kling_engine_produces_multiple_scenes_up_to_cap(tmp_path):
    """'kling' modu seçildiğinde tavan kadar sahne Kling'den, kalan Flux."""
    with patch.object(config, "FAL_KEY", "mock_fal_key"), \
         patch.object(config, "VISUAL_ENGINE", "kling"), \
         patch.object(config, "KLING_MAX_SCENES", 2), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch("app.ai_video_engine.generate_kling_video_clip") as mock_kling, \
         patch("app.ai_video_engine.generate_ai_scene_clips") as mock_ai:

        mock_kling.side_effect = lambda prompt, path, key, **kw: path
        mock_ai.side_effect = lambda prompts, output_dir, **kw: [
            str(tmp_path / f"ai_{kw.get('start_index', 0)}.mp4")
        ]

        clips = generate_video_scenes(
            ["A", "B", "C"], str(tmp_path), target_count=3
        )

        assert mock_kling.call_count == 2
        assert mock_ai.call_count == 1
        assert len(clips) == 3


def test_stock_engine_expands_to_target_count(tmp_path):
    with patch.object(config, "FAL_KEY", ""), \
         patch.object(config, "VISUAL_ENGINE", "stock"), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch("app.stock_media.fetch_stock_clips") as mock_stock:

        n = {"i": 0}

        def _one_clip(keywords, count, **kw):
            path = str(tmp_path / f"c{n['i']}.mp4")
            n["i"] += 1
            return [path]

        mock_stock.side_effect = _one_clip

        clips = generate_video_scenes(
            ["Only one prompt"], str(tmp_path), target_count=6, topic="Rolex Swiss"
        )

        assert mock_stock.call_count == 6
        assert all(c.kwargs.get("count") == 1 for c in mock_stock.call_args_list)
        assert all(c.kwargs.get("allow_used_id_reuse") is False for c in mock_stock.call_args_list)
        assert len(clips) == 6


def test_flux_miss_does_not_silent_pexels_when_stock_gated(tmp_path):
    """ALLOW_STOCK_FALLBACK=false → Flux boşsa Pexels çağrılmaz."""
    with patch.object(config, "FAL_KEY", ""), \
         patch.object(config, "VISUAL_ENGINE", "flux_kenburns"), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch("app.stock_media.fetch_stock_clips") as mock_stock, \
         patch("app.ai_video_engine.generate_ai_scene_clips", return_value=[]):

        stats = {}
        clips = generate_video_scenes(
            ["Rolex crown"],
            str(tmp_path),
            target_count=2,
            topic="Rolex",
            stats_out=stats,
        )
        assert clips == []
        mock_stock.assert_not_called()


def test_prompt_expansion_adds_distinct_camera_angles():
    from app.ai_video_engine import _expand_prompts

    expanded = _expand_prompts(["dark city"], 3)

    assert len(expanded) == 3
    assert expanded[0] == "dark city"
    assert len(set(expanded)) == 3


def test_repeated_prompts_get_refreshed_on_second_run(tmp_path):
    from app.ai_video_engine import refresh_repeated_prompts

    state = str(tmp_path / "used_prompts.json")
    prompts = ["dark marble statue", "rainy city night"]

    first = refresh_repeated_prompts(prompts, state)
    assert first == prompts

    second = refresh_repeated_prompts(prompts, state)
    assert second != first
    assert all(p.startswith(orig) for p, orig in zip(second, prompts))
    third = refresh_repeated_prompts(prompts, state)
    assert third != second


def test_prompt_history_survives_corrupt_state_file(tmp_path):
    from app.ai_video_engine import refresh_repeated_prompts

    state = tmp_path / "used_prompts.json"
    state.write_text("{bozuk json", encoding="utf-8")

    assert refresh_repeated_prompts(["prompt"], str(state)) == ["prompt"]


def test_is_kling_auth_or_billing_failure_codes_and_body():
    assert is_kling_auth_or_billing_failure(401, "")
    assert is_kling_auth_or_billing_failure(403, "")
    assert is_kling_auth_or_billing_failure(402, "")
    assert is_kling_auth_or_billing_failure(
        500, '{"detail":"User is locked. Reason: Exhausted balance"}'
    )
    assert not is_kling_auth_or_billing_failure(503, "upstream overload")
    assert not is_kling_auth_or_billing_failure(None, "render timed out")


def test_generate_kling_clip_raises_on_http_403(tmp_path):
    resp = MagicMock()
    resp.status_code = 403
    resp.text = '{"detail":"User is locked. Reason: Exhausted balance"}'

    with patch("app.ai_video_engine.session") as mock_session:
        mock_session.post.return_value = resp
        with pytest.raises(KlingAuthBillingError) as ei:
            generate_kling_video_clip("prompt", str(tmp_path / "out.mp4"), "fake-key")
        assert ei.value.status_code == 403
        assert "Exhausted" in ei.value.detail or "locked" in ei.value.detail.lower()


def test_generate_kling_clip_soft_fails_on_timeout(tmp_path):
    with patch("app.ai_video_engine.session") as mock_session:
        mock_session.post.side_effect = requests.Timeout("timed out")
        assert (
            generate_kling_video_clip("prompt", str(tmp_path / "out.mp4"), "fake-key")
            is None
        )


def test_generate_kling_clip_soft_fails_on_http_503(tmp_path):
    resp = MagicMock()
    resp.status_code = 503
    resp.text = "service unavailable"
    http_err = requests.HTTPError(response=resp)
    resp.raise_for_status.side_effect = http_err

    with patch("app.ai_video_engine.session") as mock_session:
        mock_session.post.return_value = resp
        assert (
            generate_kling_video_clip("prompt", str(tmp_path / "out.mp4"), "fake-key")
            is None
        )


def test_hybrid_kling_403_does_not_call_pexels(tmp_path):
    """hybrid + Kling 403: Pexels catch-all YOK; hata yükselir."""
    with patch.object(config, "FAL_KEY", "mock_fal_key"), \
         patch.object(config, "VISUAL_ENGINE", "hybrid"), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch(
             "app.ai_video_engine.generate_kling_video_clip",
             side_effect=KlingAuthBillingError(
                 "forbidden", status_code=403, detail="Exhausted balance"
             ),
         ), \
         patch("app.stock_media.fetch_stock_clips") as mock_stock, \
         patch("app.ai_video_engine.generate_ai_scene_clips") as mock_ai:

        with pytest.raises(KlingAuthBillingError):
            generate_video_scenes(
                ["Hook", "Body", "End"], str(tmp_path), target_count=3
            )

        mock_stock.assert_not_called()
        mock_ai.assert_not_called()


def test_flux_auth_403_propagates_as_fal_error(tmp_path):
    with patch.object(config, "FAL_KEY", "mock_fal_key"), \
         patch.object(config, "VISUAL_ENGINE", "flux_kenburns"), \
         patch.object(config, "ALLOW_STOCK_FALLBACK", False), \
         _with_isolated_media(tmp_path), \
         patch(
             "app.ai_video_engine.generate_ai_scene_clips",
             side_effect=FalAuthBillingError(
                 "flux forbidden", status_code=403, detail="Exhausted balance"
             ),
         ), \
         patch("app.stock_media.fetch_stock_clips") as mock_stock:

        with pytest.raises(FalAuthBillingError):
            generate_video_scenes(["Hook"], str(tmp_path), target_count=1)
        mock_stock.assert_not_called()
