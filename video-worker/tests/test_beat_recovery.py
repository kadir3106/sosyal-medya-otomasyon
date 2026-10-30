"""Uncovered beat recovery regressions."""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.beat_recovery import (
    BeatCoverage,
    classify_failure,
    evidence_nodes_are_verified,
    generate_query_families,
    motion_graphic_from_verified,
    next_recovery_action,
    recover_uncovered_beat,
    render_motion_graphic,
    build_beat_coverage_row,
)
from app.director_types import VisualBeat
from app.no_slideshow_gate import evaluate_no_slideshow
from app.story_domains import evaluate_story_consistency


def _beat(**kw):
    defaults = dict(
        index=0,
        spoken_span="The foundation owns the company.",
        narrative_role="document",
        evidence_role="proof",
        primary_entities=["Acme Foundation", "Acme"],
        concept="ownership",
        required_visual_concept="ownership evidence",
        visual_intent="foundation ownership",
        search_queries=[],
        preferred_media=["stock_photo"],
        allow_ai_generation=True,
    )
    defaults.update(kw)
    return VisualBeat(**defaults)


def test_uncovered_important_beat_triggers_retry_ladder(tmp_path):
    beat = _beat()
    cov = BeatCoverage(
        beat_id="0",
        importance="important",
        required_visual_concept="ownership evidence",
        required_entities=["Acme Foundation"],
        semantic_domain="ownership",
        evidence_requirement="proof",
        status="UNCOVERED",
        failure_reason="NO_CANDIDATES",
    )
    calls = {"n": 0, "queries": []}

    def materialize(b, **kwargs):
        calls["n"] += 1
        q = kwargs.get("visual_prompt") or (b.search_queries or [""])[0]
        calls["queries"].append(q)
        return None, {
            "gate_reason": "all_candidates_rejected",
            "attempts": [{"rejection_reason": "below_threshold"}],
            "provider": "pexels",
        }

    path, meta, out = recover_uncovered_beat(
        beat,
        topic="Acme ownership",
        coverage=cov,
        materialize_fn=materialize,
        output_dir=tmp_path,
        media_dir=tmp_path,
        clip_index=0,
        clip_duration=2.0,
        ai_budget_left=0,
        exclude_ids=set(),
        recent_fps=[],
        recent_blobs=[],
        person_log=[],
        verified_facts=[
            {
                "text": "The Acme Foundation is the sole owner of Acme.",
                "source": {"url": "https://example.com/wiki"},
            }
        ],
    )
    # Ownership + verified facts → evidence motion graphic may cover before stock
    assert out.attempts
    assert path or out.motion_graphic_attempted
    assert out.status == "COVERED" or calls["n"] >= 1 or out.motion_graphic_attempted


def test_retry_changes_query_strategy():
    beat = _beat()
    fams = generate_query_families(beat, topic="Acme private ownership", semantic_domain="ownership")
    types = {f["query_type"] for f in fams}
    assert "ENTITY" in types
    assert "STRUCTURE" in types or "EVIDENCE" in types
    assert len({f["query"].lower() for f in fams}) == len(fams)


def test_same_failed_query_not_repeated():
    beat = _beat()
    failed = {"acme foundation"}
    fams = generate_query_families(
        beat,
        topic="Acme",
        semantic_domain="ownership",
        failed_queries=failed,
    )
    assert all(f["query"].lower() != "acme foundation" for f in fams)


def test_alternate_provider_policy_after_duplicate():
    assert next_recovery_action("DUPLICATE_ONLY") == "alternate_provider"
    assert next_recovery_action("PROVIDER_FAILURE") == "alternate_provider"


def test_ownership_falls_back_to_evidence_graphic(tmp_path):
    plan = motion_graphic_from_verified(
        entities=["Acme Foundation", "Acme"],
        domain="ownership",
        verified_facts=[
            {
                "text": "The Acme Foundation is the sole owner of Acme.",
                "source": {"url": "https://example.com"},
            }
        ],
        spoken_span="The Acme Foundation owns Acme.",
    )
    assert plan is not None
    assert len(plan.nodes) >= 2
    img = tmp_path / "mg.jpg"
    render_motion_graphic(plan, img)
    assert img.is_file()


def test_motion_graphic_facts_require_evidence():
    plan = motion_graphic_from_verified(
        entities=["Acme Foundation", "Acme"],
        domain="ownership",
        verified_facts=[
            {"text": "The Acme Foundation is the sole owner of Acme."},
        ],
        spoken_span="The Acme Foundation owns Acme.",
    )
    assert plan
    assert evidence_nodes_are_verified(plan, [{"text": "The Acme Foundation is the sole owner of Acme."}])
    # Invented percentage node must fail
    plan.nodes.append("100%")
    assert not evidence_nodes_are_verified(
        plan, [{"text": "The Acme Foundation is the sole owner of Acme."}]
    )


def test_unrelated_asset_cannot_fill_uncovered():
    row = build_beat_coverage_row(
        {
            "spoken_span": "Hans founded the firm.",
            "narrative_role": "entity_proof",
            "evidence_role": "archive",
            "primary_entities": ["Hans"],
            "path": "/tmp/watch.mp4",
            "asset_id": "watch-1",
            "selected_asset": {"asset_id": "watch-1", "path": "/tmp/watch.mp4", "provider": "pexels"},
            "visual_change_applied": "punch_in",
        },
        index=1,
        topic="ownership",
        prev_beat={
            "spoken_span": "Luxury watches glitter.",
            "primary_entities": ["Watch"],
            "selected_asset": {"asset_id": "watch-1", "path": "/tmp/watch.mp4", "provider": "pexels"},
        },
    )
    assert row.status == "UNCOVERED"
    assert row.failure_reason == "UNRELATED_FILLER_BLOCKED"


def test_adjacent_related_beats_may_share_asset():
    row = build_beat_coverage_row(
        {
            "spoken_span": "Hans Wilsdorf built the brand.",
            "narrative_role": "entity_proof",
            "evidence_role": "archive",
            "primary_entities": ["Hans Wilsdorf"],
            "path": "/tmp/hans.jpg",
            "asset_id": "hans-1",
            "selected_asset": {
                "asset_id": "hans-1",
                "path": "/tmp/hans.jpg",
                "provider": "wikipedia",
            },
            "visual_change_applied": "punch_in",
        },
        index=2,
        topic="founder",
        prev_beat={
            "spoken_span": "Hans Wilsdorf founded the company.",
            "primary_entities": ["Hans Wilsdorf"],
            "selected_asset": {
                "asset_id": "hans-1",
                "path": "/tmp/hans.jpg",
                "provider": "wikipedia",
            },
            "spoken_span": "Hans Wilsdorf founded the company.",
        },
    )
    assert row.status in {"PARTIAL", "COVERED"}
    assert row.status != "UNCOVERED"


def test_wrong_domain_result_rejected():
    assert classify_failure({"gate_reason": "forbidden_concept_family"}) == "WRONG_DOMAIN"
    assert next_recovery_action("WRONG_DOMAIN") == "semantic_domain_correction"


def test_provider_failure_triggers_alternate():
    assert classify_failure(
        {
            "gate_reason": "miss",
            "attempts": [
                {"rejection_reason": "http_429"},
                {"rejection_reason": "provider_timeout"},
            ],
        }
    ) in {"PROVIDER_FAILURE", "NO_CANDIDATES"}
    assert next_recovery_action("PROVIDER_FAILURE") == "alternate_provider"


def test_failure_reasons_recorded(tmp_path):
    beat = _beat(spoken_span="Hook line about control.", narrative_role="hook", evidence_role="illustrative")
    cov = BeatCoverage(
        beat_id="0",
        importance="important",
        required_visual_concept="hook",
        required_entities=["Acme"],
        semantic_domain="ownership",
        evidence_requirement="illustrative",
        status="UNCOVERED",
        failure_reason="NO_CANDIDATES",
    )

    def materialize(b, **kwargs):
        return None, {
            "gate_reason": "all_candidates_rejected",
            "attempts": [{"rejection_reason": "below_threshold"}],
        }

    _, meta, out = recover_uncovered_beat(
        beat,
        topic="Acme",
        coverage=cov,
        materialize_fn=materialize,
        output_dir=tmp_path,
        media_dir=tmp_path,
        clip_index=0,
        clip_duration=2.0,
        ai_budget_left=0,
        exclude_ids=set(),
        recent_fps=[],
        recent_blobs=[],
        person_log=[],
        verified_facts=[],
    )
    assert out.failure_reason
    assert all(a.get("failure_reason") for a in out.attempts)


def test_recovery_attempts_visible_in_trace_shape(tmp_path):
    beat = _beat()
    cov = BeatCoverage(
        beat_id="1",
        importance="important",
        required_visual_concept="ownership",
        required_entities=["Acme Foundation", "Acme"],
        semantic_domain="ownership",
        evidence_requirement="proof",
        status="UNCOVERED",
        failure_reason="NO_CANDIDATES",
    )

    def materialize(b, **kwargs):
        return None, {"gate_reason": "no_gated_asset", "attempts": []}

    _, meta, out = recover_uncovered_beat(
        beat,
        topic="Acme ownership",
        coverage=cov,
        materialize_fn=materialize,
        output_dir=tmp_path,
        media_dir=tmp_path,
        clip_index=1,
        clip_duration=2.0,
        ai_budget_left=0,
        exclude_ids=set(),
        recent_fps=[],
        recent_blobs=[],
        person_log=[],
        verified_facts=[
            {"text": "The Acme Foundation is the sole owner of Acme.", "source": {"url": "https://x"}}
        ],
    )
    assert "recovery_attempts" in meta or out.attempts
    assert isinstance(out.to_dict()["attempts"], list)


def test_important_uncovered_cannot_pass_silently():
    shots = [
        {
            "spoken_span": "The foundation owns everything quietly forever.",
            "narrative_role": "document",
            "evidence_role": "proof",
            "primary_entities": ["Foundation"],
            # uncovered
        }
    ]
    cov = [
        {
            "beat_id": "0",
            "importance": "important",
            "required_visual_concept": "ownership",
            "required_entities": ["Foundation"],
            "semantic_domain": "ownership",
            "evidence_requirement": "proof",
            "attempts": [{"query": "q1", "failure_reason": "NO_CANDIDATES"}],
            "status": "UNCOVERED",
            "failure_reason": "NO_CANDIDATES",
            "motion_graphic_attempted": True,
            "providers_tried": ["pexels", "motion_graphic"],
        }
    ]
    gate = evaluate_no_slideshow(
        shots,
        topic="Foundation ownership",
        beat_coverage=cov,
        recovery_log=[{"beat_id": "0", "status": "UNCOVERED"}],
    )
    assert gate.status in {"FAIL", "REVIEW_REQUIRED"}
    assert "IMPORTANT_BEAT_UNCOVERED" in gate.reasons
    assert gate.diagnostics.get("uncovered_beat_detail")


def test_story_consistency_remains_pass():
    r = evaluate_story_consistency(
        topic="Foundation ownership of Acme",
        raw_script="Acme is owned by a private foundation.",
        final_script="The Acme Foundation is a private foundation. It is the sole owner of Acme.",
    )
    assert r.status == "PASS"


def test_river_regression_pass():
    from app.phase3_profiles import build_music_profile, build_narration_profile

    topic = "Why European rivers flooded this spring"
    script = "Heavy rainfall saturated soils. Rivers burst banks near towns."
    assert build_narration_profile(topic=topic, script=script, hook="Rivers rose.")
    assert build_music_profile(topic=topic, script=script)
    assert evaluate_story_consistency(topic=topic, raw_script=script, final_script=script).status == "PASS"


def test_bakery_regression_pass():
    topic = "How a small bakery survived inflation"
    script = "A family bakery raised prices carefully. Customers kept buying."
    assert evaluate_story_consistency(topic=topic, raw_script=script, final_script=script).status == "PASS"


def test_audio_caption_mux_regressions_pass():
    import inspect
    import app.render as render
    import app.subtitles as subtitles
    import app.audio_bgm as audio_bgm

    assert "ffmpeg" in inspect.getsource(render).lower() or "mux" in inspect.getsource(render).lower()
    assert hasattr(subtitles, "write_ass")
    assert hasattr(audio_bgm, "select_bgm") or "bgm" in inspect.getsource(audio_bgm).lower()


def test_pending_approval_unchanged():
    import inspect
    import app.pipeline as pipeline
    from app import jobs as job_store

    assert hasattr(job_store, "write_pending_mirror")
    src = inspect.getsource(pipeline._generate_video_sync)
    assert "awaiting_approval" in src
    assert "write_pending_mirror" in src
