"""Phase 3 audio / captions / music / SFX regression tests."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch, Mock

import pytest

from app.audio_bgm import get_or_create_bgm
from app.phase3_profiles import (
    build_music_profile,
    build_narration_profile,
    looks_vocal_track,
)
from app.sfx import build_smart_sfx_track
from app.subtitles import (
    TICKS_PER_SECOND,
    _chunk_boundaries_phase3,
    _hook_duplicates_opening_vo,
    first_caption_start_seconds,
    write_ass,
)


def _wb(words: list[tuple[str, float, float]]) -> list[dict]:
    """(text, start_s, dur_s) → offset tick boundaries."""
    out = []
    for text, start, dur in words:
        out.append(
            {
                "text": text,
                "offset": int(start * TICKS_PER_SECOND),
                "duration": int(dur * TICKS_PER_SECOND),
            }
        )
    return out


def test_caption_starts_near_narration_start(tmp_path):
    wb = _wb([("Rolex", 0.05, 0.3), ("owns", 0.4, 0.2), ("everything", 0.7, 0.4)])
    out = tmp_path / "subs.ass"
    write_ass(wb, str(out), highlight=True, phase3=True, karaoke_start_seconds=0.0)
    text = out.read_text(encoding="utf-8")
    assert "Dialogue: 0," in text
    assert first_caption_start_seconds(wb) < 0.2


def test_caption_chunking_not_single_giant_block():
    words = [(f"Word{i}", i * 0.25, 0.2) for i in range(12)]
    wb = _wb(words)
    chunks = _chunk_boundaries_phase3(wb, max_words=4, max_seconds=1.35)
    assert len(chunks) >= 3
    # Soft pull for prepositions may go +2; hard ceiling still small.
    assert all(len(c) <= 6 for c in chunks)


def test_hook_duplicate_overlay_skipped(tmp_path):
    wb = _wb(
        [
            ("Rolex", 0.0, 0.3),
            ("doesn't", 0.3, 0.2),
            ("have", 0.5, 0.2),
            ("a", 0.7, 0.1),
            ("single", 0.8, 0.25),
            ("shareholder", 1.1, 0.4),
        ]
    )
    out = tmp_path / "subs.ass"
    write_ass(
        wb,
        str(out),
        hook_text="Rolex doesn't have a single shareholder",
        hook_seconds=1.5,
        hook_max_words=8,
        phase3=True,
        highlight=True,
    )
    text = out.read_text(encoding="utf-8")
    assert ",Hook,," not in text
    assert _hook_duplicates_opening_vo(
        "Rolex doesn't have a single shareholder", wb
    )


def test_instrumental_preference_rejects_vocal_named_tracks(tmp_path):
    vocal = tmp_path / "pop_vocals_chorus.mp3"
    ambient = tmp_path / "dark_ambient_cinematic.mp3"
    vocal.write_bytes(b"ID3")
    ambient.write_bytes(b"ID3")
    assert looks_vocal_track(vocal.name)
    chosen = get_or_create_bgm(
        str(tmp_path), vocals_allowed=False, prefer_instrumental=True
    )
    assert chosen is not None
    assert "vocal" not in Path(chosen).name.lower()


def test_music_profile_disallows_vocals_by_default():
    mp = build_music_profile(topic="Rolex Foundation Secret", script="tax-exempt trust")
    assert mp.vocals_allowed is False
    assert mp.bgm_volume < 0.15


def test_narration_profile_emphasis_includes_entities():
    np = build_narration_profile(
        topic="Hans Wilsdorf Foundation Rolex",
        script="Rolex is owned by the Hans Wilsdorf Foundation in Switzerland.",
        hook="Rolex has zero shareholders",
    )
    blob = " ".join(np.emphasis).lower()
    assert "rolex" in blob or "Rolex" in np.emphasis
    assert any("wilsdorf" in e.lower() for e in np.emphasis)


def test_sfx_uses_offset_ticks_not_start_key(tmp_path):
    whoosh = tmp_path / "whoosh.wav"
    cash = tmp_path / "sfx_cash.wav"
    whoosh.write_bytes(b"RIFF....")
    cash.write_bytes(b"RIFF....")
    wb = [{"text": "billion", "offset": int(2.5 * TICKS_PER_SECOND), "duration": 2000000}]
    with patch("app.sfx.create_whoosh_sound", return_value=str(whoosh)):
        with patch("app.sfx.KEYWORD_TRIGGERS", {
            "cash": {
                "words": {"billion"},
                "creator": lambda p: str(cash),
                "filename": "sfx_cash.wav",
                "volume": 0.22,
                "cooldown": 0.5,
            }
        }):
            with patch("app.sfx.subprocess.run") as run:
                run.return_value = Mock(returncode=0)
                out = build_smart_sfx_track(
                    total_duration=10.0,
                    clip_duration=2.2,
                    output_path=str(tmp_path / "sfx.wav"),
                    sfx_dir=str(tmp_path),
                    transition_times=[],
                    word_boundaries=wb,
                    phase3=True,
                    max_whoosh=0,
                )
                assert out is not None
                cmd = run.call_args.args[0]
                joined = " ".join(cmd)
                # 2.5s → adelay 2500ms
                assert "adelay=2500|2500" in joined


def test_render_duck_bgm_uses_sidechain(tmp_path):
    from app.render import render_video

    clip = tmp_path / "c.mp4"
    clip.write_bytes(b"A")
    bgm = tmp_path / "b.mp3"
    bgm.write_bytes(b"B")
    (tmp_path / "subs.ass").write_text("[Script Info]\n", encoding="utf-8")
    with patch("app.render.get_audio_duration", return_value=4.0):
        with patch("app.render.subprocess.run") as run:
            run.return_value = Mock(returncode=0, stdout="", stderr="")
            stats = {}
            render_video(
                [str(clip)],
                str(tmp_path / "a.mp3"),
                str(tmp_path / "subs.ass"),
                str(tmp_path / "out.mp4"),
                str(tmp_path),
                bgm_path=str(bgm),
                bgm_volume=0.1,
                cinematic_grade=False,
                apply_zoompan=False,
                duck_bgm=True,
                stats_out=stats,
            )
            joined = " ".join(run.call_args.args[0])
            assert "sidechaincompress" in joined
            assert stats.get("duck_bgm") is True


def test_phase2_river_bakery_still_importable():
    """Phase 2 gate regressions remain importable / callable (suite runs separately)."""
    from app.director_gate import DEFAULT_FORBIDDEN_CONCEPTS

    assert "river" in DEFAULT_FORBIDDEN_CONCEPTS or "bakery" in DEFAULT_FORBIDDEN_CONCEPTS
    assert "bakery" in DEFAULT_FORBIDDEN_CONCEPTS
