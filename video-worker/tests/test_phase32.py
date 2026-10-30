"""Phase 3.2 — vocal BGM enforcement + visual-info cutaway regressions."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from app.audio_bgm import get_or_create_bgm
from app.director_gate import DEFAULT_FORBIDDEN_CONCEPTS, AssetCandidate, evaluate_asset, scene_need_from_plan
from app.person_archive import looks_like_person_name
from app.phase3_profiles import (
    build_music_profile,
    looks_instrumental_track,
    looks_vocal_track,
    track_has_vocal_metadata,
)
from app.phase3_retention import (
    cutaway_queries_for_beat,
    plan_retention_events,
    spoken_claim_shift,
    visual_info_key,
)
from app.subtitles import TICKS_PER_SECOND, _chunk_boundaries_phase3


def test_vocals_allowed_false_rejects_known_vocal_track(tmp_path):
    vocal = tmp_path / "jpop_girl_vocals_chorus.mp3"
    ambient = tmp_path / "dark_cinematic_ambient.mp3"
    vocal.write_bytes(b"ID3fake")
    ambient.write_bytes(b"ID3fake")
    assert looks_vocal_track(vocal.name)
    sel = {}
    chosen = get_or_create_bgm(
        str(tmp_path),
        vocals_allowed=False,
        prefer_instrumental=True,
        mood="dark_luxury",
        selection_out=sel,
    )
    assert chosen is not None
    assert "vocal" not in Path(chosen).name.lower()
    assert "ambient" in Path(chosen).name.lower()
    assert any(r["reason"] == "vocal_signal" for r in sel.get("rejected_tracks") or [])


def test_instrumental_track_accepted(tmp_path):
    track = tmp_path / "financial_documentary_score.mp3"
    track.write_bytes(b"ID3")
    assert looks_instrumental_track(track.name)
    chosen = get_or_create_bgm(
        str(tmp_path), vocals_allowed=False, prefer_instrumental=True, mood="financial_documentary"
    )
    assert chosen == str(track)


def test_ambiguous_vocal_status_safe_fallback(tmp_path):
    """Untitled track without instrumental cues → reject; synthetic ambient or silence."""
    mystery = tmp_path / "track01.mp3"
    mystery.write_bytes(b"ID3")
    sel = {}
    with patch("app.audio_bgm._ensure_synthetic_ambient", return_value=tmp_path / "default_ambient.mp3"):
        (tmp_path / "default_ambient.mp3").write_bytes(b"ID3" + b"\x00" * 2000)
        chosen = get_or_create_bgm(
            str(tmp_path),
            vocals_allowed=False,
            prefer_instrumental=True,
            allow_silence=True,
            selection_out=sel,
        )
    assert "track01" not in str(chosen or "")
    assert any(
        r.get("reason") == "ambiguous_not_verified_instrumental"
        for r in sel.get("rejected_tracks") or []
    )


def test_no_valid_instrumental_allows_silence(tmp_path):
    vocal = tmp_path / "pop_song_lyrics.mp3"
    vocal.write_bytes(b"ID3")
    sel = {}
    with patch("app.audio_bgm._ensure_synthetic_ambient", return_value=None):
        chosen = get_or_create_bgm(
            str(tmp_path),
            vocals_allowed=False,
            prefer_instrumental=True,
            allow_silence=True,
            selection_out=sel,
        )
    assert chosen is None
    assert sel.get("reason") in {"silence_no_safe_instrumental", "no_bgm"}


def test_vocal_metadata_tags_rejected():
    assert track_has_vocal_metadata({"title": "Night Song", "genre": "J-Pop vocals"})
    assert not track_has_vocal_metadata({"title": "default_ambient_instrumental", "genre": "instrumental ambient"})


def test_music_profile_vocals_disallowed_for_finance_topic():
    mp = build_music_profile(
        topic="The Foundation Secret: private Swiss trust",
        script="tax-free reserves and zero shareholders",
    )
    assert mp.vocals_allowed is False
    assert mp.mood in {"financial_documentary", "dark_luxury"}


def test_semantic_new_claim_triggers_contextual_cutaway():
    beats = [
        {
            "spoken_span": "Rolex boxed watch luxury product",
            "entities": ["Rolex"],
            "concept": "hero",
            "narrative_role": "hook",
            "duration": 3.0,
            "selected_asset": {"asset_id": "a1"},
        },
        {
            "spoken_span": "Rolex dial closeup luxury",
            "entities": ["Rolex"],
            "concept": "detail",
            "narrative_role": "evidence",
            "duration": 3.0,
            "selected_asset": {"asset_id": "a2"},  # different asset, SAME visual info
        },
        {
            "spoken_span": "They funnel billions into tax-free Swiss reserves",
            "entities": ["Swiss reserves"],
            "concept": "finance",
            "narrative_role": "money",
            "duration": 2.5,
            "selected_asset": {"asset_id": "a2"},
        },
    ]
    # Same product_hero info across first two
    assert visual_info_key(beats[0]).startswith("product_hero")
    assert visual_info_key(beats[1]).startswith("product_hero")
    assert visual_info_key(beats[0]) == visual_info_key(beats[1])
    assert spoken_claim_shift(beats[1], beats[2])
    events = plan_retention_events(beats)
    cut = [e for e in events if e.event_type == "contextual_cutaway"]
    assert cut
    assert cut[0].asset_change_required is True
    assert cut[0].cutaway_queries
    assert cut[0].semantic_reason


def test_unrelated_cutaway_queries_are_claim_derived_not_random():
    beat = {
        "spoken_span": "tax-free Swiss reserves",
        "entities": [],
        "narrative_role": "money",
    }
    qs = " ".join(cutaway_queries_for_beat(beat)).lower()
    assert "vault" in qs or "tax" in qs or "finance" in qs or "reserve" in qs
    assert "sports car" not in qs
    assert "yacht" not in qs


def test_same_asset_zoom_alone_not_always_new_information():
    beats = [
        {
            "spoken_span": "Rolex watch box",
            "entities": ["Rolex"],
            "narrative_role": "hook",
            "duration": 2.0,
            "visual_change": "new_asset",
            "selected_asset": {"asset_id": "x"},
        },
        {
            "spoken_span": "Rolex watch box again",
            "entities": ["Rolex"],
            "narrative_role": "evidence",
            "duration": 2.0,
            "visual_change": "punch_in",  # zoom only
            "selected_asset": {"asset_id": "x"},
        },
    ]
    # No claim shift → may get composition event only if hold long enough;
    # punch_in already set means we should NOT treat zoom as information reset.
    assert visual_info_key(beats[0]) == visual_info_key(beats[1])
    events = plan_retention_events(beats)
    # No contextual_cutaway without semantic shift
    assert not any(e.event_type == "contextual_cutaway" for e in events)


def test_entity_portrait_and_person_name_still_pass():
    assert looks_like_person_name("Hans Wilsdorf")
    assert not looks_like_person_name("Wall Street")
    need = scene_need_from_plan(
        queries=["Hans Wilsdorf portrait"],
        must_show=["Hans Wilsdorf"],
        required_entities=["Hans Wilsdorf"],
        visual_intent="Archive portrait",
        narrative_role="entity_proof",
    )
    portrait = AssetCandidate(
        provider="wikipedia_pageimage",
        asset_id="wiki:hans",
        download_url="https://example.com/h.jpg",
        title="Hans Wilsdorf",
        tags="portrait archive historical Hans Wilsdorf",
        description="Portrait of Hans Wilsdorf",
        url="https://en.wikipedia.org/wiki/Hans_Wilsdorf",
        user="Wikipedia",
        kind="stock_photo",
    )
    assert evaluate_asset(portrait, need).accepted


def test_river_bakery_anti_rep_still_pass():
    assert "bakery" in DEFAULT_FORBIDDEN_CONCEPTS
    need = scene_need_from_plan(
        queries=["Rolex billions finance"],
        must_show=["Rolex"],
        visual_intent="Financial scale",
        narrative_role="money",
    )
    river = AssetCandidate(
        provider="pexels",
        asset_id="1",
        download_url="https://example.com/r.mp4",
        title="Peaceful river flowing",
        tags="river, stream, nature",
        description="river nature brook",
        url="https://pexels.com/1",
        user="n",
        kind="stock_video",
    )
    assert evaluate_asset(river, need).accepted is False


def test_captions_regression_exact_transcript():
    words = [
        {"text": "turned", "offset": 0, "duration": 2_000_000},
        {"text": "Rolex", "offset": 2_000_000, "duration": 2_000_000},
        {"text": "into", "offset": 4_000_000, "duration": 2_000_000},
        {"text": "a", "offset": 6_000_000, "duration": 1_000_000},
        {"text": "private", "offset": 7_000_000, "duration": 2_000_000},
        {"text": "foundation", "offset": 9_000_000, "duration": 3_000_000},
    ]
    chunks = _chunk_boundaries_phase3(words)
    flat = [w["text"] for c in chunks for w in c]
    assert flat == [w["text"] for w in words]


def test_mux_duration_helper_importable():
    from app.render import render_video

    assert callable(render_video)


def test_pending_approval_unchanged():
    from app import pipeline

    src = open(pipeline.__file__, encoding="utf-8").read()
    assert "pending" in src.lower()
