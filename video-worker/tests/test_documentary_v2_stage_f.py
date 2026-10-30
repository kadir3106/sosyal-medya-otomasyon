"""Stage F — EDL / timeline / assembly / critic / repair (offline unit tests)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.documentary_v2.assembly.attribution import build_attribution_manifest
from app.documentary_v2.assembly.edl_render import render_from_edl
from app.documentary_v2.assembly.orchestrator import no_slideshow_gate
from app.documentary_v2.assembly.repair import TargetedBeatRepair, map_issue_to_strategy
from app.documentary_v2.assembly.technical_qa import technical_qa
from app.documentary_v2.assembly.timeline import _allocate_beat_windows, compile_edl, edl_metrics
from app.documentary_v2.pipeline_mode import documentary_engine_v2_enabled
from app.documentary_v2.schemas import (
    CriticFinding,
    DocumentaryDirectorPlan,
    EditDecision,
    EditDecisionList,
    ShotRequirement,
    ShotSelection,
    StoryBeat,
)
from app.subtitles import write_ass


@pytest.fixture(autouse=True)
def _v2_off(monkeypatch):
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "false")
    monkeypatch.setenv("STAGE_F_RUN", "false")


def _img(path: Path, color=(40, 40, 60)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (640, 360), color).save(path)
    return path


def _plan(beats, selections=None, assets=None) -> DocumentaryDirectorPlan:
    return DocumentaryDirectorPlan(
        plan_id="plan:test",
        job_id="job_test",
        video_id="job_test",
        topic="Rolex",
        beats=beats,
        selections=selections or [],
        shot_requirements=[
            ShotRequirement(
                shot_requirement_id=f"sr:{b.beat_id}",
                beat_id=b.beat_id,
                visual_purpose="SHOW_PRODUCT" if i == 0 else "EXPLAIN_RELATIONSHIP",
                required_visual_concept=b.required_visual_concept,
                importance=b.importance,
            )
            for i, b in enumerate(beats)
        ],
    )


def test_v2_stays_off_by_default():
    assert documentary_engine_v2_enabled() is False


def test_compile_edl_follows_narration_clock(tmp_path):
    a = _img(tmp_path / "a.jpg", (10, 10, 10))
    b = _img(tmp_path / "b.jpg", (80, 80, 20))
    beats = [
        StoryBeat(
            beat_id="beat:0:hook",
            spoken_span="Rolex is not what you think",
            narrative_role="hook",
            required_visual_concept="Rolex watch",
            importance="important",
            estimated_duration=2.0,
        ),
        StoryBeat(
            beat_id="beat:1:evidence",
            spoken_span="A foundation owns the company",
            narrative_role="evidence",
            required_visual_concept="ownership",
            importance="important",
            estimated_duration=3.0,
        ),
    ]
    sels = [
        ShotSelection(
            shot_id="s0",
            beat_id="beat:0:hook",
            asset_id="asset:a",
            candidate_id="cand:a",
            visual_information_id="viu:a",
            visual_purpose="SHOW_PRODUCT",
        ),
        ShotSelection(
            shot_id="s1",
            beat_id="beat:1:evidence",
            asset_id="asset:b",
            candidate_id="cand:b",
            visual_information_id="viu:b",
            visual_purpose="EXPLAIN_RELATIONSHIP",
        ),
    ]
    plan = _plan(beats, sels)
    edl = compile_edl(
        plan,
        narration_duration_sec=5.0,
        asset_paths={"cand:a": str(a), "cand:b": str(b)},
        job_id="job_test",
        video_id="job_test",
    )
    assert len(edl.decisions) == 2
    assert edl.decisions[0].transition == "cut"
    assert abs(edl.total_duration_sec - 5.0) < 0.2
    assert edl.decisions[0].end_time <= edl.decisions[1].start_time + 0.05
    m = edl_metrics(edl)
    assert m["unique_source_assets"] == 2
    assert m["unique_vius"] == 2


def test_one_beat_can_have_multiple_shots(tmp_path):
    paths = [
        _img(tmp_path / f"h{i}.jpg", (20 * i, 30, 40)) for i in range(3)
    ]
    beat = StoryBeat(
        beat_id="beat:0:hook",
        spoken_span="Fast hook with three meaningful looks",
        narrative_role="hook",
        required_visual_concept="Rolex",
        importance="important",
        estimated_duration=4.0,
    )
    sels = [
        ShotSelection(
            shot_id=f"s{i}",
            beat_id="beat:0:hook",
            asset_id=f"asset:{i}",
            candidate_id=f"cand:{i}",
            visual_information_id=f"viu:{i}",
        )
        for i in range(3)
    ]
    plan = _plan([beat], sels)
    edl = compile_edl(
        plan,
        narration_duration_sec=4.0,
        asset_paths={f"cand:{i}": str(paths[i]) for i in range(3)},
        job_id="j",
        video_id="j",
    )
    assert len(edl.decisions) == 3
    assert abs(sum(d.duration for d in edl.decisions) - 4.0) < 0.15


def test_recovery_asset_enters_edl_like_normal(tmp_path):
    g = _img(tmp_path / "graph.png", (5, 5, 80))
    beat = StoryBeat(
        beat_id="beat:own",
        spoken_span="The foundation owns Rolex",
        narrative_role="evidence",
        required_visual_concept="ownership",
        importance="important",
    )
    plan = _plan([beat], [])
    edl = compile_edl(
        plan,
        narration_duration_sec=3.0,
        recovery_paths={"beat:own": str(g)},
        job_id="j",
        video_id="j",
    )
    assert len(edl.decisions) == 1
    assert edl.decisions[0].synthetic is True or "recovery" in edl.decisions[0].media_type
    assert edl.decisions[0].local_path == str(g)


def test_zoom_forbidden_as_repair_strategy():
    assert map_issue_to_strategy("STATIC_HOLD_TOO_LONG") == "seek_second_viu_not_zoom"
    repairer = TargetedBeatRepair()
    actions = repairer.plan_repairs(
        [
            CriticFinding(
                finding_id="f1",
                start_sec=1.0,
                end_sec=3.0,
                beat_id="beat:1",
                severity="HIGH",
                issue_code="STATIC_HOLD_TOO_LONG",
            )
        ]
    )
    assert actions
    assert actions[0].strategy == "seek_second_viu_not_zoom"
    out = repairer.apply_recovery_repair(
        actions[0],
        ShotRequirement(shot_requirement_id="sr", beat_id="beat:1"),
    )
    assert out.applied is False
    assert "zoom" in str(out.details.get("note", "")).lower() or out.details.get("zoom_forbidden") is not False


def test_edl_render_and_technical_qa(tmp_path):
    import subprocess

    # Tiny silent narration
    audio = tmp_path / "nar.wav"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2.5",
            "-ac", "1", str(audio),
        ],
        capture_output=True,
        check=True,
    )
    cap = tmp_path / "cap.ass"
    cap.write_text(
        "[Script Info]\nScriptType: v4.00+\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,2,0,2,40,40,80,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:02.00,Default,,0,0,0,,Test caption\n",
        encoding="utf-8",
    )
    img = _img(tmp_path / "still.jpg")
    edl = EditDecisionList(
        edl_id="edl:t",
        job_id="j",
        video_id="j",
        decisions=[
            EditDecision(
                edit_id="e1",
                shot_id="s1",
                beat_id="b1",
                asset_id="a1",
                visual_information_id="viu:1",
                media_type="archive_still",
                source_kind="archive",
                local_path=str(img),
                start_time=0.0,
                end_time=2.5,
                duration=2.5,
                motion_policy="subtle_push",
                transition="cut",
            )
        ],
        total_duration_sec=2.5,
        narration_duration_sec=2.5,
    )
    out = tmp_path / "out.mp4"
    manifest = render_from_edl(
        edl,
        audio_path=str(audio),
        caption_path=str(cap),
        output_path=str(out),
        work_dir=str(tmp_path / "ff"),
        bgm_path=None,
        loudnorm=False,
    )
    assert out.is_file()
    assert manifest.resolution == "1080x1920"
    qa = technical_qa(str(out), expected_duration=2.5, duration_tol=1.0)
    assert qa.has_video and qa.has_audio
    assert qa.ok, qa.reasons
    attr = build_attribution_manifest(edl)
    assert attr and attr[0]["license"] == "UNKNOWN"


def test_repair_patch_edl(tmp_path):
    old = _img(tmp_path / "old.jpg", (1, 1, 1))
    new = _img(tmp_path / "new.jpg", (200, 10, 10))
    edl = EditDecisionList(
        edl_id="e",
        job_id="j",
        video_id="j",
        decisions=[
            EditDecision(
                edit_id="e1",
                shot_id="s1",
                beat_id="beat:x",
                asset_id="old",
                local_path=str(old),
                start_time=0,
                end_time=2,
                duration=2,
            )
        ],
    )
    patched = TargetedBeatRepair().patch_edl_asset(edl, beat_id="beat:x", new_path=str(new))
    assert patched.decisions[0].local_path == str(new)
    assert patched.decisions[0].synthetic is True


def test_technical_qa_rejects_short_video_stream(tmp_path):
    import subprocess

    out = tmp_path / "short_picture.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-c:a", "aac", str(out),
        ],
        capture_output=True,
        check=True,
    )
    qa = technical_qa(str(out), expected_duration=2.0)
    assert not qa.ok
    assert any("stream_duration_mismatch" in reason for reason in qa.reasons)


def test_edl_render_rejects_uncovered_timeline_gap(tmp_path):
    image = _img(tmp_path / "shot.jpg")
    edl = EditDecisionList(
        edl_id="edl:gap", job_id="j", video_id="j",
        decisions=[
            EditDecision(edit_id="one", shot_id="one", beat_id="b1", asset_id="a1",
                         local_path=str(image), start_time=0, end_time=1, duration=1),
            EditDecision(edit_id="two", shot_id="two", beat_id="b2", asset_id="a2",
                         local_path=str(image), start_time=2, end_time=3, duration=1),
        ],
    )
    with pytest.raises(ValueError, match="edl_timeline_gap"):
        render_from_edl(edl, audio_path="unused", caption_path="unused",
                        output_path=str(tmp_path / "out.mp4"), work_dir=str(tmp_path))


def test_beat_windows_follow_spoken_word_boundaries():
    beats = [
        StoryBeat(beat_id="a", spoken_span="A short hook.", narrative_role="hook"),
        StoryBeat(beat_id="b", spoken_span="A much longer second beat.", narrative_role="evidence"),
    ]
    words = [
        {"text": text, "offset": int(start * 10_000_000), "duration": 2_000_000}
        for text, start in zip(
            ["A", "short", "hook", "A", "much", "longer", "second", "beat"],
            [0.1, 0.4, 0.8, 2.1, 2.5, 3.0, 3.7, 4.4],
        )
    ]
    windows = _allocate_beat_windows(beats, 5.0, words)
    assert windows == [(0.0, 2.1), (2.1, 5.0)]


def test_stage_f_captions_restore_sentence_and_avoid_orphan_word(tmp_path):
    words = [
        {"text": text, "offset": i * 3_000_000, "duration": 2_500_000}
        for i, text in enumerate("Rolex is not a normal company".split())
    ]
    path = tmp_path / "captions.ass"
    write_ass(words, str(path), phase3=True,
              script_text="Rolex is not a normal company.")
    cues = [line for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("Dialogue:")]
    assert len(cues) == 1
    assert cues[0].endswith("Rolex is not a normal company.")


def test_no_slideshow_gate_reviews_long_static_opening():
    edl = EditDecisionList(
        edl_id="e", job_id="j", video_id="j",
        decisions=[
            EditDecision(edit_id="still", shot_id="still", beat_id="a", asset_id="a",
                         start_time=0, end_time=10, duration=10,
                         media_type="archive_still", source_kind="archive"),
            EditDecision(edit_id="motion", shot_id="motion", beat_id="b", asset_id="b",
                         start_time=10, end_time=15, duration=5,
                         media_type="stock_video", source_kind="stock"),
        ],
    )
    metrics = {"shot_count": 2, "unique_vius": 2,
               "by_class": {"archive_still": 1, "stock_video": 1},
               "seconds_by_class": {"archive_still": 10, "stock_video": 5}}
    assert no_slideshow_gate(metrics, edl) == "REVIEW_REQUIRED"


def test_technical_qa_rejects_clipping_audio(tmp_path):
    import subprocess

    out = tmp_path / "clipped.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", "color=c=black:s=1080x1920:r=30:d=1",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
         "-af", "volume=16", "-c:v", "libx264", "-c:a", "aac", str(out)],
        capture_output=True, check=True,
    )
    qa = technical_qa(str(out), expected_duration=1.0)
    assert not qa.ok
    assert any("audio_true_peak_high" in reason for reason in qa.reasons)
