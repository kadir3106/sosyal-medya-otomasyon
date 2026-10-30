"""No-slideshow story engine regressions."""
from __future__ import annotations

from unittest.mock import MagicMock

from app.no_slideshow_gate import evaluate_no_slideshow, visual_information_units_from_shots
from app.script_quality import narrative_purpose, refine_script, rebuild_draft_with_replacements
from app.storyboard import (
    compute_visual_information_id,
    storyboard_before_retrieval,
)


def test_five_zooms_one_still_one_visual_information_unit():
    aid = "photo-123"
    ids = [
        compute_visual_information_id(asset_id=aid, concept="product", evidence_role="product")
        for _ in range(5)
    ]
    assert len(set(ids)) == 1


def test_crop_pan_same_still_not_diverse():
    a = compute_visual_information_id(asset_id="x1", concept="a", evidence_role="product")
    b = compute_visual_information_id(asset_id="x1", concept="a", evidence_role="product")
    assert a == b


def test_new_relevant_video_new_visual_information():
    a = compute_visual_information_id(asset_id="v1", media_kind="stock_video")
    b = compute_visual_information_id(asset_id="v2", media_kind="stock_video")
    assert a != b


def test_motion_capable_prefers_video_in_storyboard():
    specs = storyboard_before_retrieval(
        "In Geneva the markets move capital through Swiss banks.",
        topic="Swiss finance",
    )
    assert specs
    placeish = [s for s in specs if s.evidence_role in {"location", "contrast"} or "geneva" in s.spoken_span.lower()]
    assert placeish
    assert any(s.preferred_media_type == "stock_video" for s in placeish)


def test_historical_person_may_use_archive_still():
    specs = storyboard_before_retrieval(
        "Founder Hans Wilsdorf built the company in the early twentieth century.",
        topic="Rolex",
    )
    person = [s for s in specs if s.evidence_role == "archive" or "Hans" in s.spoken_span]
    assert person
    assert any(s.preferred_media_type == "stock_photo" for s in person)


def test_document_beat_may_use_document_still():
    specs = storyboard_before_retrieval(
        "The legal charter and tax filing documents define the structure.",
        topic="Company",
    )
    docs = [s for s in specs if s.evidence_role == "document" or "document" in s.required_visual_concept]
    assert docs


def test_no_slideshow_gate_detects_fake_variety():
    shots = []
    for i in range(4):
        shots.append(
            {
                "spoken_span": f"claim {i}",
                "asset_id": "same-photo",
                "kind": "stock_photo",
                "path": "/tmp/a.jpg",
                "duration": 2.0,
                "visual_change": "punch_in",
                "force_visual_change_reuse": True,
                "concept": "product",
                "narrative_role": "evidence",
                "evidence_role": "product",
            }
        )
    gate = evaluate_no_slideshow(shots, retention_events=[
        {"event_type": "controlled_punch_in", "asset_change_required": False},
        {"event_type": "controlled_punch_in", "asset_change_required": False},
    ])
    assert gate.status in {"FAIL", "REVIEW_REQUIRED"}
    assert gate.reasons


def test_no_slideshow_gate_allows_legitimate_archive_story():
    shots = [
        {
            "spoken_span": "Hans Wilsdorf founded the firm.",
            "asset_id": "hans-1",
            "kind": "stock_photo",
            "path": "/tmp/hans.jpg",
            "duration": 2.5,
            "visual_change": "new_asset",
            "concept": "person_archive",
            "narrative_role": "entity_proof",
            "evidence_role": "archive",
            "primary_entities": ["Hans Wilsdorf"],
        },
        {
            "spoken_span": "The foundation owns the company.",
            "asset_id": "doc-1",
            "kind": "stock_photo",
            "path": "/tmp/doc.jpg",
            "duration": 2.5,
            "visual_change": "new_asset",
            "concept": "ownership",
            "narrative_role": "document",
            "evidence_role": "document",
            "primary_entities": ["Foundation"],
        },
        {
            "spoken_span": "Geneva remains the home base.",
            "asset_id": "vid-1",
            "kind": "stock_video",
            "path": "/tmp/geneva.mp4",
            "duration": 3.0,
            "visual_change": "new_asset",
            "concept": "location",
            "narrative_role": "place",
            "evidence_role": "location",
        },
    ]
    gate = evaluate_no_slideshow(shots)
    assert gate.status in {"PASS", "REVIEW_REQUIRED"}
    assert "TRANSFORM_AS_FAKE_VARIETY" not in gate.reasons


def test_visual_information_units_dedupe_crops():
    shots = [
        {"asset_id": "a", "kind": "stock_photo", "concept": "x", "evidence_role": "product"},
        {"asset_id": "a", "kind": "stock_photo", "concept": "x", "evidence_role": "product", "visual_change": "punch_in"},
    ]
    units = visual_information_units_from_shots(shots)
    assert len(units) == 1


def test_storyboard_before_retrieval_exists():
    specs = storyboard_before_retrieval(
        "The Hans Wilsdorf Foundation owns Rolex. Amateurs chase IPO liquidity.",
        topic="Rolex",
    )
    assert specs
    assert all(s.required_visual_concept for s in specs)


def test_unsupported_claim_triggers_replacement_research():
    from app.fact_verify import FactVerificationProvider, VerificationResult
    from app.script_claims import ScriptClaim

    class Stub(FactVerificationProvider):
        def verify_claims(self, claims, *, topic=""):
            out = []
            for c in claims:
                if not c.verification_required:
                    out.append(VerificationResult(claim_id=c.claim_id, status="supported", notes="skip"))
                else:
                    out.append(
                        VerificationResult(
                            claim_id=c.claim_id,
                            status="unsupported",
                            confidence=0.8,
                            sources=[{"title": "wiki", "url": "https://example.com"}],
                        )
                    )
            return out

        def research_replacement_facts(self, topic, *, purposes=None, max_facts=4, banned_markers=None, intents=None):
            return [
                {
                    "text": "The Hans Wilsdorf Foundation is a private foundation that owns Rolex.",
                    "purpose": "ownership",
                    "semantic_domain": "ownership",
                    "intent_domain": "ownership",
                    "domain_match_score": 1.0,
                    "source": {"title": "Rolex", "url": "https://en.wikipedia.org/wiki/Rolex", "provider": "wikipedia"},
                    "verified": True,
                }
            ]

    raw = (
        "Rolex channels billions tax-free into Swiss vaults. "
        "Real power moves quietly."
    )
    result = refine_script(raw, topic="Rolex", verifier=Stub(), skip_llm_edit=True)
    assert result.replacement_research
    assert any(f.get("verified") for f in result.replacement_research)
    assert "tax-free" not in result.final_script.lower()
    assert len(result.final_script.split()) >= 10


def test_replacement_requires_evidence_flag():
    facts = rebuild_draft_with_replacements(
        "Quiet power.",
        [{"text": "The foundation owns the company.", "purpose": "ownership", "verified": True}],
        min_words=12,
    )
    assert "foundation owns" in facts.lower()


def test_verification_attempts_research_before_collapse():
    from app.fact_verify import FactVerificationProvider, VerificationResult

    calls = {"research": 0}

    class Stub(FactVerificationProvider):
        def verify_claims(self, claims, *, topic=""):
            return [
                VerificationResult(
                    claim_id=c.claim_id,
                    status="unsupported" if c.verification_required else "supported",
                    sources=[{"url": "https://example.com"}],
                )
                for c in claims
            ]

        def research_replacement_facts(self, topic, *, purposes=None, max_facts=4, banned_markers=None, intents=None):
            calls["research"] += 1
            return []

    refine_script(
        "Rolex controls the entire market with 100% tax-free billions.",
        topic="Rolex",
        verifier=Stub(),
        skip_llm_edit=True,
    )
    assert calls["research"] == 1


def test_narrative_purpose_tags():
    assert narrative_purpose("The foundation owns Rolex.") == "ownership"
    assert narrative_purpose("Hans Wilsdorf founded the firm in 1905.") == "history"


def test_pending_approval_unchanged():
    import inspect
    import app.pipeline as pipeline
    from app import jobs as job_store

    assert hasattr(job_store, "write_pending_mirror")
    src = inspect.getsource(pipeline._generate_video_sync)
    assert "awaiting_approval" in src
    assert "write_pending_mirror" in src
