"""Stage C VisualVerifier — offline unit tests (no live VLM required)."""
from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from app.documentary_v2.pipeline_mode import documentary_engine_v2_enabled, resolve_pipeline_mode
from app.documentary_v2.schemas import (
    AssetProvenance,
    MediaCandidate,
    PipelineMode,
    PreviewFrame,
    VisualPreviewBundle,
    VisualVerificationRequest,
)
from app.documentary_v2.verifier.cache import VerificationCache, verification_cache_key
from app.documentary_v2.verifier.decision import apply_decision
from app.documentary_v2.verifier.frame_dedup import dedupe_frames
from app.documentary_v2.verifier.mock import MockVisualVerifier
from app.documentary_v2.verifier.prefilter import cheap_prefilter
from app.documentary_v2.verifier.reason_codes import (
    CONCEPT_MISMATCH,
    DECISION_ACCEPT,
    DECISION_REJECT,
    DECISION_UNCERTAIN,
    ILLUSTRATIVE_ONLY,
    METADATA_VISUAL_CONFLICT,
    MOTION_REQUIRED_BUT_STATIC,
    PERSON_PROVENANCE_SUPPORTED,
    TEMPORAL_WEAK_COVERAGE,
    VLM_INVALID_RESPONSE,
    VLM_UNAVAILABLE,
)
from app.documentary_v2.verifier.sampler import estimate_motion_class, uniform_timestamps
from app.documentary_v2.verifier.service import verify_candidate


@pytest.fixture(autouse=True)
def _flags_off(monkeypatch):
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "false")
    monkeypatch.setenv("VISUAL_VERIFIER_ENABLED", "false")
    monkeypatch.setenv("DIRECTOR_ENABLED", "false")
    yield


def _img(path: Path, color=(10, 80, 160)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (64, 64), color).save(path)
    return path


def _req(**kwargs) -> VisualVerificationRequest:
    base = dict(
        verification_id="vv:test",
        job_id="job-c",
        candidate_id="cand:test:1",
        required_visual_concept="Rolex watch",
        semantic_domain="luxury_watch",
        required_entities=["Rolex"],
        strict_entity_mode=True,
    )
    base.update(kwargs)
    return VisualVerificationRequest(**base)


def test_v2_and_verifier_off_by_default():
    assert documentary_engine_v2_enabled() is False
    assert resolve_pipeline_mode() == PipelineMode.LEGACY_STOCK


def test_metadata_attack_river_rejects(tmp_path: Path):
    """METADATA says Rolex; PIXELS are river → REJECT."""
    media = _img(tmp_path / "rolex_luxury_watch.jpg", (30, 90, 180))
    req = _req(
        retrieval_context={
            "fixture_tag": "river_as_rolex",
            "metadata_claims": ["Rolex luxury watch"],
            "query": "Rolex luxury watch",
            "filename": "rolex_luxury_watch.jpg",
        }
    )
    result = verify_candidate(
        req,
        media_path=media,
        media_kind="image",
        provider=MockVisualVerifier(),
        use_cache=False,
    )
    assert result.decision == DECISION_REJECT
    assert METADATA_VISUAL_CONFLICT in result.reason_codes
    assert CONCEPT_MISMATCH in result.reason_codes or result.concept_alignment == "NONE"
    assert result.visual_supported_claims == []
    assert result.metadata_visual_conflict is True


def test_visual_positive_sparse_metadata_accepts(tmp_path: Path):
    media = _img(tmp_path / "img.jpg", (200, 180, 40))
    req = _req(
        strict_entity_mode=False,
        required_entities=["watch"],
        retrieval_context={"fixture_tag": "watch_sparse_metadata", "metadata_claims": []},
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert result.decision == DECISION_ACCEPT
    assert result.concept_alignment in {"STRONG", "EXACT"}
    assert "watch" in " ".join(result.visual_supported_claims).lower() or result.visible_entities


def test_bakery_negative(tmp_path: Path):
    media = _img(tmp_path / "x.jpg")
    req = _req(retrieval_context={"fixture_tag": "bakery_as_rolex"})
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert result.decision == DECISION_REJECT


def test_temporal_weak_coverage_not_strong(tmp_path: Path):
    media = _img(tmp_path / "x.jpg")
    req = _req(
        strict_entity_mode=True,
        retrieval_context={"fixture_tag": "temporal_flash"},
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert TEMPORAL_WEAK_COVERAGE in result.reason_codes
    assert result.decision != DECISION_ACCEPT
    assert (result.entity_presence_ratio or 0) < 0.25


def test_static_mp4_process_motion_required(tmp_path: Path):
    media = _img(tmp_path / "still.jpg")
    req = _req(
        motion_requirement="PROCESS_MOTION",
        strict_entity_mode=False,
        required_entities=[],
        required_visual_concept="watch manufacturing",
        retrieval_context={"fixture_tag": "static_process"},
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert MOTION_REQUIRED_BUT_STATIC in result.reason_codes
    assert result.decision == DECISION_REJECT


def test_ownership_generic_market_not_evidence(tmp_path: Path):
    media = _img(tmp_path / "market.jpg")
    req = _req(
        required_visual_concept="company ownership evidence",
        required_entities=["Acme Corp"],
        evidence_requirement="EVIDENCE",
        strict_entity_mode=True,
        retrieval_context={"fixture_tag": "generic_market_ownership"},
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert result.decision == DECISION_REJECT
    assert ILLUSTRATIVE_ONLY in result.reason_codes or result.evidence_value in {
        "GENERIC_CONTEXT",
        "ILLUSTRATION",
    }
    assert result.evidence_value != "EVIDENCE"


def test_person_provenance_supported(tmp_path: Path):
    media = _img(tmp_path / "portrait.jpg", (80, 60, 40))
    req = _req(
        required_visual_concept="historical founder portrait",
        required_entities=["Hans Wilsdorf"],
        strict_entity_mode=True,
        retrieval_context={
            "fixture_tag": "person_archive",
            "trusted_person_provenance": True,
        },
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert PERSON_PROVENANCE_SUPPORTED in result.reason_codes
    assert result.decision in {DECISION_ACCEPT, DECISION_UNCERTAIN}
    assert result.decision != DECISION_REJECT


def test_founder_anonymous_office_rejects(tmp_path: Path):
    media = _img(tmp_path / "office.jpg")
    req = _req(
        required_visual_concept="founder portrait",
        required_entities=["Hans Wilsdorf"],
        strict_entity_mode=True,
        retrieval_context={"fixture_tag": "anonymous_office_founder"},
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert result.decision == DECISION_REJECT


def test_vlm_unavailable_is_uncertain_not_accept(tmp_path: Path):
    media = _img(tmp_path / "x.jpg")
    req = _req()
    result = verify_candidate(
        req,
        media_path=media,
        media_kind="image",
        provider=MockVisualVerifier(error="VLM_UNAVAILABLE: down"),
        use_cache=False,
    )
    assert result.decision == DECISION_UNCERTAIN
    assert VLM_UNAVAILABLE in result.reason_codes or VLM_INVALID_RESPONSE in result.reason_codes


def test_vlm_invalid_json_uncertain(tmp_path: Path):
    class Bad(MockVisualVerifier):
        def observe(self, request, bundle):
            raise RuntimeError("VLM_INVALID_RESPONSE: missing:entity_alignment")

    media = _img(tmp_path / "x.jpg")
    result = verify_candidate(
        _req(), media_path=media, media_kind="image", provider=Bad(), use_cache=False
    )
    assert result.decision == DECISION_UNCERTAIN
    assert VLM_INVALID_RESPONSE in result.reason_codes


def test_unknown_alignment_not_accept():
    req = _req(strict_entity_mode=True)
    obs = {
        "visible_entities": [],
        "visible_objects": ["something"],
        "visible_actions": [],
        "visible_setting": "?",
        "dominant_visual_concept": "?",
        "entity_alignment": "UNKNOWN",
        "concept_alignment": "UNKNOWN",
        "action_alignment": "UNKNOWN",
        "location_alignment": "UNKNOWN",
        "entity_specificity": "UNKNOWN",
        "motion_value": "UNKNOWN_MOTION",
        "visual_role": "UNKNOWN",
        "authenticity_support": "UNKNOWN",
        "genericness": "UNKNOWN",
        "contradictions": [],
        "forbidden_concept_hits": [],
        "metadata_visual_conflict": False,
        "visual_supported_claims": [],
        "metadata_supported_claims": [],
        "confidence": 0.1,
        "explanation_short": "unclear",
    }
    v = apply_decision(req, obs, verification_id="v1")
    assert v.decision != DECISION_ACCEPT


def test_cache_keyed_by_intent_and_fingerprint(tmp_path: Path):
    k1 = verification_cache_key(
        content_fingerprint="abc",
        intent_signature="intent-rolex",
        verifier_provider="mock",
        verifier_model="mock-v1",
    )
    k2 = verification_cache_key(
        content_fingerprint="abc",
        intent_signature="intent-landscape",
        verifier_provider="mock",
        verifier_model="mock-v1",
    )
    assert k1 != k2
    cache = VerificationCache(root=tmp_path / "c")
    media = _img(tmp_path / "m.jpg")
    req = _req(retrieval_context={"fixture_tag": "river_as_rolex"})
    r1 = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), cache=cache
    )
    assert r1.cache_hit is False
    r2 = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), cache=cache
    )
    assert r2.cache_hit is True
    assert r2.decision == r1.decision


def test_frame_dedup_reduces_near_identical():
    frames = [
        PreviewFrame(0.0, perceptual_hash="ahash:ffffffffffffffff"),
        PreviewFrame(0.5, perceptual_hash="ahash:fffffffffffffffe"),
        PreviewFrame(1.0, perceptual_hash="ahash:0000000000000000"),
    ]
    out = dedupe_frames(frames, max_hamming=4)
    assert len(out) == 2


def test_uniform_timestamps_not_only_first_middle():
    ts = uniform_timestamps(8.0, 5)
    assert len(ts) == 5
    assert ts[0] > 0
    assert ts[-1] < 8.0
    assert ts[0] != ts[-1]


def test_estimate_static_motion():
    frames = [
        PreviewFrame(0.0, perceptual_hash="ahash:aaaaaaaaaaaaaaaa"),
        PreviewFrame(1.0, perceptual_hash="ahash:aaaaaaaaaaaaaaaa"),
        PreviewFrame(2.0, perceptual_hash="ahash:aaaaaaaaaaaaaaab"),
    ]
    assert estimate_motion_class(frames, duration=3.0) in {
        "STATIC_VIDEO",
        "MINIMAL_CAMERA_MOTION",
    }


def test_intent_signature_changes_with_entity():
    a = _req(required_entities=["Rolex"]).intent_signature()
    b = _req(required_entities=["Hans Wilsdorf"]).intent_signature()
    assert a != b


def test_cheap_prefilter_not_visual_truth():
    cand = MediaCandidate(
        candidate_id="c1",
        provenance=AssetProvenance(provider="pexels"),
        download_url="https://example/x.mp4",
        query="river nature",
    )
    req = _req()
    pf = cheap_prefilter(cand, req)
    # Weak metadata still passes to VisualVerifier
    assert pf.accepted is True


def test_pending_unchanged_no_publish():
    from app import jobs as job_store

    assert "awaiting_approval" in job_store.JOB_STATES
    assert documentary_engine_v2_enabled() is False


def test_example_negative_trace(tmp_path: Path):
    media = _img(tmp_path / "rolex_watch_luxury.mp4.jpg")
    req = _req(
        retrieval_context={
            "fixture_tag": "river_as_rolex",
            "metadata_claims": ["Rolex", "luxury", "watch"],
            "query": "Rolex Hans Wilsdorf",
        }
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    trace = {
        "intent": req.required_visual_concept,
        "candidate_id": req.candidate_id,
        "metadata": req.retrieval_context.get("metadata_claims"),
        "visible": result.visible_objects,
        "entity_alignment": result.entity_alignment,
        "concept_alignment": result.concept_alignment,
        "genericness": result.genericness,
        "metadata_visual_conflict": result.metadata_visual_conflict,
        "decision": result.decision,
        "reason_codes": result.reason_codes,
    }
    assert trace["decision"] == DECISION_REJECT
    assert trace["metadata_visual_conflict"] is True


def test_example_positive_trace(tmp_path: Path):
    media = _img(tmp_path / "watch.jpg", (220, 200, 50))
    req = _req(
        strict_entity_mode=False,
        required_entities=["watch"],
        retrieval_context={"fixture_tag": "actual_watch"},
    )
    result = verify_candidate(
        req, media_path=media, media_kind="image", provider=MockVisualVerifier(), use_cache=False
    )
    assert result.decision == DECISION_ACCEPT
    assert result.entity_alignment in {"STRONG", "EXACT", "PARTIAL"}
