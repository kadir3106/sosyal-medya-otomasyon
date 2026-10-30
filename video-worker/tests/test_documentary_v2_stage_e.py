"""Stage E — Visual Recovery Generation Layer tests (offline; no publish/render full doc)."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app.documentary_v2.pipeline_mode import documentary_engine_v2_enabled
from app.documentary_v2.recovery.budgets import RecoveryBudget
from app.documentary_v2.recovery.engine import VisualRecoveryEngine
from app.documentary_v2.recovery.generation_fal import build_generated_video_provider
from app.documentary_v2.recovery.generation_mock import MockGeneratedVideoProvider
from app.documentary_v2.recovery.motion_plans import (
    MotionGraphicPlanError,
    build_document_highlight_plan,
    build_evidence_card_plan,
    build_relationship_graph_plan,
    build_timeline_plan,
    build_counter_plan,
)
from app.documentary_v2.recovery.planner import choose_recovery_strategy
from app.documentary_v2.recovery.prompt_compiler import compile_generated_visual_plan
from app.documentary_v2.recovery.renderer import MotionGraphicRenderer
from app.documentary_v2.recovery.synthetic_policy import classify_synthetic_suitability
from app.documentary_v2.recovery.types import RecoveryStrategy, SyntheticSuitability
from app.documentary_v2.schemas import (
    ShotRequirement,
    VerifiedClaim,
    VisualVerification,
)


@pytest.fixture(autouse=True)
def _v2_off(monkeypatch):
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "false")
    monkeypatch.setenv("STAGE_E_LIVE_GENERATION", "false")


def _claim(cid: str, text: str, **kw) -> VerifiedClaim:
    return VerifiedClaim(
        claim_id=cid,
        text=text,
        status=kw.get("status", "supported"),
        claim_type=kw.get("claim_type", ""),
        evidence=kw.get("evidence", [{"evidence_id": f"{cid}:ev0", "source": "fixture"}]),
        semantic_domain=kw.get("semantic_domain", "luxury_watch_ownership"),
    )


def _req(**kw) -> ShotRequirement:
    base = dict(
        shot_requirement_id="sr:1",
        beat_id="beat:1",
        subject="Rolex",
        required_visual_concept="ownership relationship",
        visual_purpose="EXPLAIN_RELATIONSHIP",
        semantic_domain="luxury_watch_ownership",
        required_entities=["Hans Wilsdorf", "Rolex"],
        evidence_role="EVIDENCE_REQUIRED",
        claim_ids=["c1"],
        estimated_duration=3.0,
    )
    base.update(kw)
    return ShotRequirement(**base)


def test_v2_stays_off():
    assert documentary_engine_v2_enabled() is False


def test_motion_graphic_requires_semantic_purpose():
    d = choose_recovery_strategy(
        _req(visual_purpose="EXPLAIN_RELATIONSHIP"),
        failure_reason="EVIDENCE_NOT_FOUND",
        claims=[_claim("c1", "Hans Wilsdorf founded Rolex; foundation owns the company")],
    )
    assert d.strategy == RecoveryStrategy.MOTION_GRAPHIC
    assert d.primitive == "RelationshipGraph"


def test_relationship_edge_requires_evidence():
    req = _req()
    claims = [_claim("c1", "Foundation owns Rolex")]
    with pytest.raises(MotionGraphicPlanError):
        build_relationship_graph_plan(
            req,
            edges=[{"from": "A", "to": "B", "label": "owns", "claim_id": "missing", "evidence_id": "x"}],
            claims=claims,
        )
    plan = build_relationship_graph_plan(
        req,
        edges=[
            {
                "from": "Hans Wilsdorf",
                "to": "Foundation",
                "label": "founded",
                "claim_id": "c1",
                "evidence_id": "c1:ev0",
            },
            {
                "from": "Foundation",
                "to": "Rolex",
                "label": "owns",
                "claim_id": "c1",
                "evidence_id": "c1:ev0",
            },
        ],
        claims=claims,
    )
    assert plan.verified
    assert all(e.get("claim_id") and e.get("evidence_id") for e in plan.relationships)


def test_timeline_date_requires_evidence():
    req = _req(visual_purpose="SHOW_EVIDENCE", required_visual_concept="company timeline")
    claims = [_claim("c2", "Rolex was founded in 1905 in London", claim_type="date")]
    with pytest.raises(MotionGraphicPlanError):
        build_timeline_plan(
            req,
            events=[{"date": "1999", "label": "invented", "claim_id": "c2", "evidence_id": "c2:ev0"}],
            claims=claims,
        )
    plan = build_timeline_plan(
        req,
        events=[{"date": "1905", "label": "Founded", "claim_id": "c2", "evidence_id": "c2:ev0"}],
        claims=claims,
    )
    assert plan.primitive == "Timeline"


def test_document_highlight_cannot_fabricate():
    req = _req(visual_purpose="SHOW_EVIDENCE")
    with pytest.raises(MotionGraphicPlanError):
        build_document_highlight_plan(
            req, document_asset_id="", claim_ids=["c1"], evidence_ids=["c1:ev0"]
        )


def test_evidence_card_explanatory_not_official():
    plan = build_evidence_card_plan(
        _req(),
        claims=[_claim("c1", "The foundation owns Rolex")],
    )
    assert plan.explanatory_only is True
    assert "not an official" in str(plan.style.get("disclaimer", "")).lower()


def test_number_requires_verified_claim():
    claim = _claim("c3", "Private ownership is 100 percent")
    with pytest.raises(MotionGraphicPlanError):
        build_counter_plan(_req(), claim=claim, display_value="50%")
    plan = build_counter_plan(_req(), claim=claim, display_value="100")
    assert plan.number_claim_id == "c3"


def test_synthetic_never_auto_evidence():
    req = _req(
        visual_purpose="EXPLAIN_RELATIONSHIP",
        evidence_role="EVIDENCE_REQUIRED",
        generation_allowed=True,
    )
    suit = classify_synthetic_suitability(req)
    assert suit == SyntheticSuitability.UNSAFE_AS_SYNTHETIC_EVIDENCE
    assert compile_generated_visual_plan(req) is None


def test_unsafe_historical_person_blocked():
    req = _req(
        visual_purpose="SHOW_PERSON",
        required_entities=["Hans Wilsdorf"],
        strict_entity_mode=True,
        generation_allowed=True,
        evidence_role="AUTHENTIC_CONTEXT_REQUIRED",
    )
    assert classify_synthetic_suitability(req) == SyntheticSuitability.REAL_MEDIA_REQUIRED
    d = choose_recovery_strategy(req, failure_reason="NO_CANDIDATES", claims=[])
    assert d.strategy in {RecoveryStrategy.ARCHIVE_MEDIA, RecoveryStrategy.ARCHIVAL_STILL}


def test_generated_provider_replaceable():
    mock = build_generated_video_provider("mock")
    fal = build_generated_video_provider("fal_kling")
    assert mock.name == "mock"
    assert fal.name == "fal_kling"


def test_paid_generation_disabled_by_default(tmp_path: Path):
    from app.documentary_v2.recovery.generation_fal import FalKlingGeneratedVideoProvider

    p = FalKlingGeneratedVideoProvider()
    plan = compile_generated_visual_plan(
        _req(
            visual_purpose="ESTABLISH_CONTEXT",
            generation_allowed=True,
            evidence_role="ILLUSTRATION_ACCEPTABLE",
            semantic_domain="abstract",
            required_visual_concept="abstract mechanism",
        )
    )
    assert plan is not None
    res = p.generate(plan, output_dir=str(tmp_path))
    assert res.ok is False
    assert "live_generation_disabled" in res.error


def test_generation_cost_ceiling(tmp_path: Path):
    budget = RecoveryBudget(
        live_generation=True,
        max_ai_generation_calls=5,
        max_generation_cost_per_video=0.01,
        max_generation_cost_per_beat=0.01,
    )
    ok, why = budget.can_generate(beat_id="b1", estimated_cost=0.5)
    assert ok is False
    assert why == "max_generation_cost_per_video"


def test_generated_must_pass_verifier(tmp_path: Path):
    def reject_verify(req, media_path):
        return VisualVerification(
            verification_id="x",
            decision="REJECT",
            status="REJECT",
            reason_codes=["CONCEPT_MISMATCH"],
        )

    eng = VisualRecoveryEngine(
        budget=RecoveryBudget(live_generation=True, max_ai_generation_calls=2),
        generator=MockGeneratedVideoProvider(),
        verify_fn=reject_verify,
    )
    req = _req(
        visual_purpose="ESTABLISH_CONTEXT",
        generation_allowed=True,
        evidence_role="ILLUSTRATION_ACCEPTABLE",
        semantic_domain="abstract_concept",
        required_visual_concept="abstract mechanism gears",
        required_entities=[],
    )
    rr = eng.recover(
        req,
        failure_reason="NO_CANDIDATES",
        claims=[],
        output_dir=tmp_path,
        job_id="j1",
        generate=True,
    )
    assert rr.strategy == RecoveryStrategy.SYNTHETIC_VIDEO
    assert rr.generation and rr.generation.ok
    assert rr.selected is False


def test_real_media_beats_generation():
    d = choose_recovery_strategy(
        _req(visual_purpose="SHOW_PROCESS", generation_allowed=True),
        failure_reason="NO_CANDIDATES",
        has_strong_real_video=True,
    )
    assert d.strategy == RecoveryStrategy.REAL_MEDIA


def test_ownership_uses_relationship(tmp_path: Path):
    claims = [_claim("c1", "Hans Wilsdorf founded Rolex; foundation owns company")]
    edges = [
        {
            "from": "Hans Wilsdorf",
            "to": "Foundation",
            "label": "founded",
            "claim_id": "c1",
            "evidence_id": "c1:ev0",
        },
        {
            "from": "Foundation",
            "to": "Rolex",
            "label": "owns",
            "claim_id": "c1",
            "evidence_id": "c1:ev0",
        },
    ]
    eng = VisualRecoveryEngine()
    rr = eng.recover(
        _req(),
        failure_reason="EVIDENCE_NOT_FOUND",
        claims=claims,
        relationship_edges=edges,
        output_dir=tmp_path,
        job_id="own1",
        render=True,
        generate=False,
    )
    assert rr.strategy == RecoveryStrategy.MOTION_GRAPHIC
    assert rr.motion_graphic_plan and rr.motion_graphic_plan.primitive == "RelationshipGraph"
    assert rr.render and rr.render.ok
    assert Path(rr.artifact_path).is_file()
    assert rr.selected is True


def test_founder_prefers_archive():
    d = choose_recovery_strategy(
        _req(
            visual_purpose="SHOW_PERSON",
            required_entities=["Hans Wilsdorf"],
            strict_entity_mode=True,
            semantic_domain="biography",
        ),
        failure_reason="NO_CANDIDATES",
        has_archive_portrait=True,
    )
    assert d.strategy == RecoveryStrategy.ARCHIVAL_STILL


def test_process_prefers_real_motion():
    d = choose_recovery_strategy(
        _req(
            visual_purpose="SHOW_PROCESS",
            required_visual_concept="watch manufacturing",
            generation_allowed=False,
            evidence_role="AUTHENTIC_CONTEXT_REQUIRED",
        ),
        failure_reason="MOTION_NOT_FOUND",
    )
    assert d.strategy == RecoveryStrategy.REAL_MEDIA


def test_no_generic_filler_strategy():
    d = choose_recovery_strategy(
        _req(visual_purpose="SHOW_EVIDENCE", claim_ids=[], required_entities=[]),
        failure_reason="ONLY_GENERIC_CONTEXT_FOUND",
        claims=[],
    )
    assert d.strategy == RecoveryStrategy.UNCOVERED


def test_renderer_safe_areas_and_file(tmp_path: Path):
    claims = [_claim("c1", "Foundation owns Rolex")]
    plan = build_relationship_graph_plan(
        _req(),
        edges=[
            {
                "from": "Foundation",
                "to": "Rolex",
                "label": "owns",
                "claim_id": "c1",
                "evidence_id": "c1:ev0",
            }
        ],
        claims=claims,
        duration=1.5,
    )
    rr = MotionGraphicRenderer().render(plan, output_dir=tmp_path, job_id="t1")
    assert rr.ok
    assert rr.width == 1080 and rr.height == 1920
    assert rr.qa.get("ok") is True
    assert Path(rr.path).stat().st_size > 1000
    assert rr.provenance.get("evidence_role") == "EXPLANATORY"


def test_abstract_synthetic_may_be_planned():
    req = _req(
        visual_purpose="ESTABLISH_CONTEXT",
        required_visual_concept="abstract mechanism",
        generation_allowed=True,
        evidence_role="ILLUSTRATION_ACCEPTABLE",
        semantic_domain="abstract",
        required_entities=[],
    )
    suit = classify_synthetic_suitability(req)
    assert suit == SyntheticSuitability.SAFE_FOR_SYNTHETIC
    plan = compile_generated_visual_plan(req)
    assert plan and plan.evidence_prohibited is True
