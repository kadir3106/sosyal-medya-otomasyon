"""Stage F.1 regressions from the human-reviewed Rolex render."""
from __future__ import annotations

import subprocess
import wave
from pathlib import Path

import pytest
from PIL import Image

from app.documentary_v2.assembly import orchestrator
from app.documentary_v2.assembly.orchestrator import _license_gate, no_slideshow_gate
from app.documentary_v2.assembly.technical_qa import technical_qa
from app.documentary_v2.assembly.timeline import compile_edl, edl_metrics
from app.documentary_v2.director.shot_director import DocumentaryShotDirector
from app.documentary_v2.recovery.renderer import render_frame
from app.documentary_v2.recovery.theme import DEFAULT_THEME
from app.documentary_v2.schemas import (
    BeatCoverageReport,
    DocumentaryDirectorPlan,
    EditDecision,
    EditDecisionList,
    MotionGraphicPlan,
    ShotSelection,
    StoryBeat,
    VisualVerificationRequest,
)
from app.documentary_v2.verifier.decision import apply_decision
from app import subtitles
from app.subtitles import write_ass


def _strict_rolex_request() -> VisualVerificationRequest:
    return VisualVerificationRequest(
        verification_id="verify:rolex",
        beat_id="beat:rolex",
        candidate_id="candidate:watch",
        required_visual_concept="Rolex crown dial",
        required_entities=["Rolex"],
        strict_entity_mode=True,
        evidence_requirement="EVIDENCE",
    )


def _positive_observation(**overrides) -> dict:
    value = {
        "entity_alignment": "STRONG",
        "concept_alignment": "STRONG",
        "action_alignment": "STRONG",
        "location_alignment": "STRONG",
        "entity_specificity": "EXACT_ENTITY",
        "genericness": "LOW",
        "visual_role": "EVIDENCE",
        "authenticity_support": "AUTHENTIC_CURRENT",
        "motion_value": "NATURAL_SUBJECT_MOTION",
        "contradictions": [],
        "forbidden_concept_hits": [],
        "metadata_visual_conflict": False,
        "visible_entities": ["Rolex"],
        "visible_objects": ["watch"],
        "visible_actions": [],
        "visible_setting": "studio",
        "visible_text_summary": "ROLEX",
        "visible_brand_names": ["Rolex"],
        "confidence": 0.95,
    }
    value.update(overrides)
    return value


@pytest.mark.parametrize(
    ("brands", "visible_text"),
    [(["Omega"], "OMEGA Speedmaster"), (["SL Quartz"], "SL QUARTZ")],
)
def test_strict_rolex_beat_rejects_conflicting_visible_brand(brands, visible_text):
    result = apply_decision(
        _strict_rolex_request(),
        _positive_observation(
            visible_brand_names=brands,
            visible_text_summary=visible_text,
        ),
        verification_id="verify:conflict",
    )
    assert result.decision == "REJECT"
    assert "WRONG_ENTITY" in result.reason_codes


def test_named_important_process_keeps_entity_requirement_and_strict_mode():
    requirement = DocumentaryShotDirector().plan_shot_for_beat(
        None,
        StoryBeat(
            "beat:rolex-process",
            spoken_span="The watches are still made in Switzerland with deliberate craftsmanship.",
            narrative_role="process",
            primary_entities=["Rolex"],
            required_visual_concept="Rolex Swiss manufacturing craftsmanship",
            importance="important",
            motion_requirement="REQUIRED",
        ),
    )

    assert requirement.required_entities == ["Rolex"]
    assert requirement.strict_entity_mode is True
    assert requirement.evidence_role == "AUTHENTIC_CONTEXT_REQUIRED"


def test_entity_footage_requirement_rejects_illustration_even_when_entity_alignment_is_strong():
    request = _strict_rolex_request()
    request.evidence_requirement = "ENTITY_FOOTAGE"
    result = apply_decision(
        request,
        _positive_observation(
            visual_role="ILLUSTRATION",
            authenticity_support="STOCK_ILLUSTRATION",
        ),
        verification_id="verify:illustration",
    )

    assert result.decision == "REJECT"
    assert "ILLUSTRATIVE_ONLY" in result.reason_codes


def test_caption_style_retune_preserves_dialogue_text_and_timing(tmp_path):
    path = tmp_path / "captions.ass"
    write_ass(
        [
            {"text": "Rolex", "offset": 0, "duration": 5_000_000},
            {"text": "craftsmanship.", "offset": 5_000_000, "duration": 5_000_000},
        ],
        str(path),
        phase3=True,
        script_text="Rolex craftsmanship.",
        timeline_end_seconds=1.0,
    )
    before = [line for line in path.read_text(encoding="utf-8-sig").splitlines() if line.startswith("Dialogue:")]

    assert hasattr(subtitles, "retune_ass_caption_style")
    subtitles.retune_ass_caption_style(str(path), font_size=76, outline=4, margin_v=420)

    content = path.read_text(encoding="utf-8-sig")
    after = [line for line in content.splitlines() if line.startswith("Dialogue:")]
    assert "Style: Default,DejaVu Sans,76," in content
    assert before == after


def test_founder_important_beat_cannot_pass_when_uncovered():
    beat = StoryBeat(
        "beat:founder",
        spoken_span="Hans Wilsdorf founded Rolex.",
        primary_entities=["Hans Wilsdorf"],
        importance="important",
    )
    coverage = {
        beat.beat_id: BeatCoverageReport(
            beat.beat_id,
            status="UNCOVERED",
            importance="important",
            failure_reason="NO_VERIFIED_ARCHIVE",
        )
    }
    assert orchestrator._visual_coverage_gate([beat], coverage, set()) == "REVIEW_REQUIRED"


def test_internal_claim_ids_are_not_drawn_on_motion_graphics(monkeypatch):
    drawn: list[str] = []
    from PIL import ImageDraw

    original = ImageDraw.ImageDraw.text

    def record(self, xy, text, *args, **kwargs):
        drawn.append(str(text))
        return original(self, xy, text, *args, **kwargs)

    monkeypatch.setattr(ImageDraw.ImageDraw, "text", record)
    render_frame(
        MotionGraphicPlan(
            plan_id="mg:claims",
            primitive="EvidenceCard",
            labels=["Ownership", "A foundation owns Rolex"],
            claim_ids=["c:ownership", "c:founder"],
        ),
        DEFAULT_THEME,
        1.0,
    )
    assert drawn
    assert not any("c:ownership" in text or "c:founder" in text for text in drawn)


def test_motion_graphic_keeps_caption_band_clear():
    image = render_frame(
        MotionGraphicPlan(
            plan_id="mg:safe",
            primitive="EvidenceCard",
            labels=["Ownership", "A foundation owns Rolex"],
            claim_ids=["c:ownership"],
        ),
        DEFAULT_THEME,
        1.0,
    )
    band = image.crop((0, int(image.height * 0.70), image.width, image.height))
    assert not any(sum(pixel[:3]) > 500 for pixel in band.get_flattened_data())


@pytest.mark.parametrize(
    "plan",
    [
        MotionGraphicPlan(
            plan_id="mg:ownership-density",
            primitive="RelationshipGraph",
            nodes=["Hans Wilsdorf Foundation", "Rolex"],
            relationships=[
                {
                    "from": "Hans Wilsdorf Foundation",
                    "to": "Rolex",
                    "label": "owns",
                    "claim_id": "c:ownership",
                    "evidence_id": "ev:own",
                }
            ],
        ),
        MotionGraphicPlan(
            plan_id="mg:timeline-density",
            primitive="Timeline",
            events=[
                {"date": "1945", "label": "Foundation created"},
                {"date": "1960", "label": "Became Rolex owner"},
            ],
        ),
    ],
)
def test_ownership_graphics_are_not_mobile_sparse(plan):
    image = render_frame(plan, DEFAULT_THEME, 1.0)
    informative_pixels = sum(
        1 for pixel in image.get_flattened_data() if sum(pixel[:3]) > 180
    )
    assert informative_pixels >= 20_000


def test_last_visual_pts_reaches_narration_end(tmp_path):
    image_path = tmp_path / "payoff.jpg"
    Image.new("RGB", (640, 360), (20, 20, 20)).save(image_path)
    beat = StoryBeat(
        "beat:payoff",
        spoken_span="Rolex closes the story.",
        narrative_role="payoff",
        importance="important",
    )
    plan = DocumentaryDirectorPlan(
        "plan:payoff",
        beats=[beat],
        selections=[
            ShotSelection(
                "shot:payoff",
                beat.beat_id,
                asset_id="asset:payoff",
                candidate_id="asset:payoff",
                visual_information_id="viu:payoff",
            )
        ],
    )
    words = [
        {"text": text, "offset": i * 10_000_000, "duration": 5_000_000}
        for i, text in enumerate("Rolex closes the story".split())
    ]
    edl = compile_edl(
        plan,
        narration_duration_sec=5.0,
        word_boundaries=words,
        asset_paths={"asset:payoff": str(image_path)},
    )
    assert edl.decisions[-1].end_time >= 4.98
    assert edl.total_duration_sec >= 4.98


def test_last_caption_end_reaches_narration_end(tmp_path):
    words = [
        {"text": text, "offset": i * 10_000_000, "duration": 5_000_000}
        for i, text in enumerate("Rolex closes the story".split())
    ]
    path = tmp_path / "captions.ass"
    write_ass(
        words,
        str(path),
        phase3=True,
        script_text="Rolex closes the story.",
        timeline_end_seconds=5.0,
    )
    final = [line for line in path.read_text(encoding="utf-8").splitlines() if line.startswith("Dialogue:")][-1]
    assert ",0:00:05.00," in final


def test_unknown_license_and_blank_source_never_pass():
    assert _license_gate([{"license": "UNKNOWN", "source_url": ""}]) == "REVIEW_REQUIRED"


def test_transform_only_reuse_does_not_create_new_vius():
    decisions = [
        EditDecision(
            f"shot:{i}",
            f"beat:{i}",
            asset_id="same:still",
            visual_information_id=f"viu:fake:{i}",
            media_type="archive_still",
            source_kind="archive",
            start_time=float(i),
            end_time=float(i + 1),
            duration=1.0,
            motion_policy="subtle_push",
        )
        for i in range(3)
    ]
    metrics = edl_metrics(EditDecisionList("edl:reuse", "job", "video", decisions=decisions))
    assert metrics["unique_vius"] == 1


def test_rendered_frozen_final_frame_is_reported(tmp_path):
    video = tmp_path / "frozen.mp4"
    still = tmp_path / "still.png"
    audio = tmp_path / "silence.wav"
    Image.new("RGB", (1080, 1920), (0, 0, 0)).save(still)
    with wave.open(str(audio), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(8_000)
        wav.writeframes(b"\0\0" * 8_000 * 4)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(still),
            "-i",
            str(audio),
            "-t",
            "4",
            "-c:v",
            "libx264",
            "-c:a",
            "aac",
            str(video),
        ],
        check=True,
        capture_output=True,
    )
    qa = technical_qa(str(video), expected_duration=4.0)
    assert qa.details["longest_freeze_sec"] >= 3.8
    assert qa.details["tail_freeze_sec"] >= 3.8
    edl = EditDecisionList(
        "edl:frozen",
        "job",
        "video",
        decisions=[
            EditDecision(
                "shot:one",
                "beat:one",
                asset_id="asset:one",
                visual_information_id="viu:one",
                media_type="stock_video",
                source_kind="stock",
                start_time=0,
                end_time=4,
                duration=4,
            )
        ],
    )
    assert no_slideshow_gate(
        {
            "unique_vius": 1,
            "seconds_by_class": {"stock_video": 4.0},
        },
        edl,
        rendered_diagnostics=qa.details,
    ) != "PASS"
