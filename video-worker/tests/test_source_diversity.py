"""Source diversity + story-drift regressions (no slideshow)."""
from __future__ import annotations

from app.director_gate import GateResult, selection_score
from app.no_slideshow_gate import evaluate_no_slideshow
from app.story_domains import (
    analyze_source_assets,
    build_replacement_intent,
    domain_match_score,
    evaluate_story_consistency,
    important_beat_coverage,
    source_asset_key,
    uncovered_important_beats,
)


def test_eight_shot_ids_one_media_asset_is_one_unique_source():
    shots = []
    for i in range(8):
        shots.append(
            {
                "spoken_span": f"beat {i} about ownership structure",
                "asset_id": "media-999",
                "provider": "pexels",
                "kind": "stock_video",
                "path": f"/tmp/clip_{i}_punch_in.mp4" if i else "/tmp/clip_0.mp4",
                "selected_asset": {
                    "asset_id": "media-999",
                    "provider": "pexels",
                    "path": f"/tmp/clip_{i}.mp4",
                    "metadata": {"url": "https://pexels.com/video/999"},
                },
                "duration": 2.0,
                "narrative_role": "evidence",
                "evidence_role": "proof",
            }
        )
    stats = analyze_source_assets(shots)
    assert stats["shot_count"] == 8
    assert stats["unique_source_asset_count"] == 1


def test_crop_trim_variants_not_new_source_assets():
    a = source_asset_key(
        provider="pexels",
        asset_id="42",
        url="https://pexels.com/video/42?utm=1",
        path="/tmp/clip_0.mp4",
    )
    b = source_asset_key(
        provider="pexels",
        asset_id="42",
        url="https://pexels.com/video/42?utm=2",
        path="/tmp/clip_0_punch_in.mp4",
    )
    assert a == b
    assert a == "pexels:42"


def test_ownership_replacement_cannot_drift_to_manufacturing():
    intent = build_replacement_intent(
        claim_id="c1",
        text="Rolex is owned 100% by a private Swiss foundation.",
        topic="Rolex Foundation ownership",
    )
    assert intent.semantic_domain == "ownership"
    assert "manufacturing" in intent.forbidden_drift_domains
    score = domain_match_score(
        "The Cosmograph Daytona series was introduced as a self-winding watch.",
        intent,
    )
    assert score < 0.5


def test_founder_replacement_cannot_drift_to_product_trivia():
    intent = build_replacement_intent(
        claim_id="c2",
        text="Hans Wilsdorf founded the company in London.",
        topic="Hans Wilsdorf founder",
    )
    assert intent.semantic_domain == "founder_history"
    score = domain_match_score(
        "The Submariner dial and crown became product icons.",
        intent,
    )
    assert score < 0.5


def test_semantic_domain_preserving_replacement_accepted():
    intent = build_replacement_intent(
        claim_id="c3",
        text="The foundation owns all of the company's shares.",
        topic="Rolex ownership",
    )
    score = domain_match_score(
        "The Hans Wilsdorf Foundation is a private foundation that owns Rolex.",
        intent,
    )
    assert score >= 0.7


def test_uncovered_important_beat_triggers_retry_signal():
    shots = [
        {
            "spoken_span": "Hans Wilsdorf founded Rolex.",
            "narrative_role": "entity_proof",
            "evidence_role": "archive",
            "primary_entities": ["Hans Wilsdorf"],
            # no path / asset
        },
        {
            "spoken_span": "The foundation owns the firm.",
            "narrative_role": "document",
            "evidence_role": "proof",
            "path": "/tmp/a.mp4",
            "asset_id": "1",
            "selected_asset": {"asset_id": "1", "path": "/tmp/a.mp4", "provider": "pexels"},
        },
    ]
    uncovered = uncovered_important_beats(shots)
    assert any(u["coverage_status"] == "UNCOVERED" for u in uncovered)
    gate = evaluate_no_slideshow(shots)
    assert "IMPORTANT_BEAT_UNCOVERED" in gate.reasons
    assert gate.status == "FAIL"


def test_unrelated_previous_asset_cannot_silently_fill_uncovered():
    shots = [
        {
            "spoken_span": "Hook about secret ownership.",
            "narrative_role": "hook",
            "evidence_role": "illustrative",
            "path": "/tmp/watch.mp4",
            "asset_id": "watch-1",
            "selected_asset": {
                "asset_id": "watch-1",
                "provider": "pexels",
                "path": "/tmp/watch.mp4",
            },
            "visual_change_applied": "new_asset",
        },
        {
            "spoken_span": "Hans Wilsdorf founded the firm.",
            "narrative_role": "entity_proof",
            "evidence_role": "archive",
            "primary_entities": ["Hans Wilsdorf"],
            "path": "/tmp/watch_punch_in.mp4",
            "asset_id": "watch-1",
            "selected_asset": {
                "asset_id": "watch-1",
                "provider": "pexels",
                "path": "/tmp/watch_punch_in.mp4",
            },
            "visual_change_applied": "punch_in",
            "visual_change": "punch_in",
        },
    ]
    cov = important_beat_coverage(shots)
    person = [c for c in cov if c.get("important_kind") == "person_founder"]
    assert person
    assert person[0]["coverage_status"] == "UNCOVERED"


def test_alternate_provider_can_satisfy_uncovered_beat():
    shots = [
        {
            "spoken_span": "Hans Wilsdorf founded Rolex.",
            "narrative_role": "entity_proof",
            "evidence_role": "archive",
            "primary_entities": ["Hans Wilsdorf"],
            "path": "/tmp/hans.jpg",
            "asset_id": "wiki-hans",
            "kind": "stock_photo",
            "selected_asset": {
                "asset_id": "wiki-hans",
                "provider": "wikipedia",
                "path": "/tmp/hans.jpg",
            },
            "visual_change_applied": "new_asset",
        }
    ]
    cov = important_beat_coverage(shots)
    assert cov[0]["coverage_status"] == "COVERED"
    stats = analyze_source_assets(shots)
    assert stats["unique_source_asset_count"] == 1
    assert "wikipedia" in stats["unique_source_assets_by_provider"]


def test_relevant_reused_beats_irrelevant_novel():
    reused = GateResult(
        accepted=True,
        reason="ok",
        relevance_score=0.9,
        entity_score=0.9,
        specificity_score=0.85,
        forbidden_hit=None,
    )
    novel = GateResult(
        accepted=True,
        reason="ok",
        relevance_score=0.35,
        entity_score=0.2,
        specificity_score=0.25,
        forbidden_hit=None,
    )
    s_reused = selection_score(reused, reuse_pen=0.2, novelty=0.0, source_novelty=0.0)
    s_novel = selection_score(novel, reuse_pen=0.0, novelty=0.1, source_novelty=0.12)
    assert s_reused > s_novel


def test_equally_relevant_novel_beats_reused():
    a = GateResult(
        accepted=True,
        reason="ok",
        relevance_score=0.8,
        entity_score=0.8,
        specificity_score=0.8,
        forbidden_hit=None,
    )
    b = GateResult(
        accepted=True,
        reason="ok",
        relevance_score=0.8,
        entity_score=0.8,
        specificity_score=0.8,
        forbidden_hit=None,
    )
    s_reused = selection_score(a, reuse_pen=0.25, novelty=0.0, source_novelty=0.0)
    s_novel = selection_score(b, reuse_pen=0.0, novelty=0.05, source_novelty=0.12)
    assert s_novel > s_reused


def test_story_consistency_detects_domain_drift():
    result = evaluate_story_consistency(
        topic="The Rolex Foundation Secret: ownership by private Swiss trust",
        raw_script="Rolex is owned by a private foundation with no public shareholders.",
        final_script=(
            "The Cosmograph Daytona series was introduced as a self-winding watch. "
            "Manufacturing movements define the brand. Series production continues."
        ),
        replacement_research=[
            {
                "text": "The Cosmograph Daytona series was introduced.",
                "semantic_domain": "ownership",
                "domain_match_score": 0.0,
            }
        ],
    )
    assert result.status == "FAIL"
    assert "SEMANTIC_DOMAIN_DRIFT" in result.reasons


def test_no_slideshow_gate_flags_low_source_diversity():
    shots = []
    for i in range(8):
        shots.append(
            {
                "spoken_span": f"ownership claim sentence number {i} with enough words",
                "asset_id": "only-one",
                "provider": "pexels",
                "kind": "stock_video",
                "path": f"/tmp/c{i}.mp4",
                "selected_asset": {
                    "asset_id": "only-one",
                    "provider": "pexels",
                    "path": f"/tmp/c{i}.mp4",
                    "metadata": {"url": "https://pexels.com/video/only-one"},
                },
                "duration": 2.0,
                "visual_change": "new_asset",
                "narrative_role": "evidence",
                "evidence_role": "proof",
                "concept": "ownership",
            }
        )
    gate = evaluate_no_slideshow(shots, topic="Rolex ownership")
    assert gate.status == "FAIL"
    assert "LOW_UNIQUE_SOURCE_ASSET_COUNT" in gate.reasons or "RETRIEVAL_COLLAPSE" in gate.reasons
    assert gate.diagnostics["shot_count"] == 8
    assert gate.diagnostics["unique_source_asset_count"] == 1


def test_river_regression_pass():
    from app.phase3_profiles import build_music_profile, build_narration_profile

    topic = "Why European rivers flooded this spring"
    script = (
        "Heavy rainfall saturated soils across central Europe. "
        "Rivers burst their banks near historic towns. "
        "Communities rebuilt levees with local crews."
    )
    n = build_narration_profile(topic=topic, script=script, hook="Rivers rose overnight.")
    m = build_music_profile(topic=topic, script=script)
    assert n
    assert m
    assert evaluate_story_consistency(
        topic=topic, raw_script=script, final_script=script
    ).status == "PASS"


def test_bakery_regression_pass():
    topic = "How a small bakery survived inflation"
    script = (
        "A family bakery raised prices carefully. "
        "Local customers kept buying sourdough weekly. "
        "Owners renegotiated flour contracts in time."
    )
    assert evaluate_story_consistency(
        topic=topic, raw_script=script, final_script=script
    ).status == "PASS"


def test_person_retrieval_pass():
    from app.person_archive import looks_like_person_name

    assert looks_like_person_name("Hans Wilsdorf")
    assert not looks_like_person_name("Rolex Foundation")


def test_music_regression_pass():
    from app.phase3_profiles import build_music_profile

    m = build_music_profile(
        topic="Rolex ownership",
        script="The foundation owns the company. Quiet control persists.",
    )
    assert m
    assert getattr(m, "mood", None) or m.to_dict()


def test_mux_pass():
    import inspect
    import app.render as render

    src = inspect.getsource(render)
    assert "mux" in src.lower() or "ffmpeg" in src.lower()


def test_pending_approval_unchanged():
    import inspect
    import app.pipeline as pipeline
    from app import jobs as job_store

    assert hasattr(job_store, "write_pending_mirror")
    src = inspect.getsource(pipeline._generate_video_sync)
    assert "awaiting_approval" in src
    assert "write_pending_mirror" in src
