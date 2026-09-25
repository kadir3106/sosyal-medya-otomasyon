"""Topic-driven V2 review path contracts."""


def test_documentary_script_prompt_has_no_luxury_bias(monkeypatch):
    from app import script_gen

    seen = []

    def fake_llm(messages, api_key):
        seen.append(messages[0]["content"])
        return (
            '{"script":"The Aral Sea shrank after river diversion.",'
            '"title":"The Aral Sea","description":"A shrinking sea.",'
            '"tags":["history"]}',
            "fixture",
        )

    monkeypatch.setattr(script_gen, "_call_llm_with_fallback", fake_llm)
    data = script_gen.generate_script("Aral Sea", "fixture", style="documentary_review")
    assert data["script"].startswith("The Aral Sea")
    assert "Rolex" not in seen[0] and "Luxury Lifestyle" not in seen[0]
    assert "scene_stock_queries" not in data


def test_aral_fact_lookup_never_seeds_rolex(monkeypatch):
    from app.fact_verify import FactVerificationProvider
    from app.script_claims import ScriptClaim

    provider, titles = FactVerificationProvider(), []
    monkeypatch.setattr(provider, "_wikipedia_evidence", lambda title: titles.append(title) or {})
    monkeypatch.setattr(provider, "_wikipedia_search_extract", lambda query: None)
    claim = ScriptClaim("aral", "The Aral Sea shrank.", "historical", ["Aral Sea"], risk="HIGH", verification_required=True)
    provider.verify_claims([claim], topic="Aral Sea")
    assert not any("rolex" in title.lower() or "wilsdorf" in title.lower() for title in titles)


def test_final_script_claim_is_verified_again(monkeypatch):
    from app.documentary_v2 import review_story
    from app.fact_verify import VerificationResult
    from app.script_quality import ScriptQualityResult

    seen = []

    class Verifier:
        def verify_claims(self, claims, *, topic):
            seen.extend(c.text for c in claims)
            return [VerificationResult(c.claim_id, "supported", sources=[{"url": "https://example.test/aral"}]) for c in claims]

    monkeypatch.setattr(review_story, "generate_script", lambda *args, **kwargs: {"script": "The Aral Sea expanded.", "title": "Aral Sea"})
    monkeypatch.setattr(review_story, "refine_script", lambda *args, **kwargs: ScriptQualityResult("The Aral Sea expanded.", "The Aral Sea shrank in 1960.", story_consistency={"status": "PASS"}))
    prepared = review_story.prepare_review_story("Aral Sea", "fixture", verifier=Verifier())
    assert seen == ["The Aral Sea shrank in 1960."]
    assert prepared.story.final_script == seen[0]


def test_final_script_unknown_high_risk_blocks_review(monkeypatch):
    import pytest
    from app.documentary_v2 import review_story
    from app.fact_verify import VerificationResult
    from app.script_quality import ScriptQualityResult

    class Verifier:
        def verify_claims(self, claims, *, topic):
            return [VerificationResult(c.claim_id, "unknown") for c in claims]

    monkeypatch.setattr(review_story, "generate_script", lambda *args, **kwargs: {"script": "The Aral Sea expanded.", "title": "Aral Sea"})
    monkeypatch.setattr(review_story, "refine_script", lambda *args, **kwargs: ScriptQualityResult("The Aral Sea expanded.", "The Aral Sea shrank in 1960."))
    with pytest.raises(ValueError, match="unresolved high-risk final claim"):
        review_story.prepare_review_story("Aral Sea", "fixture", verifier=Verifier())


def test_aral_queries_do_not_contain_watch_terms():
    from app.documentary_v2.director.query_compiler import compile_search_intents
    from app.documentary_v2.schemas import ShotRequirement

    req = ShotRequirement(
        "sr:aral", "beat:aral", visual_purpose="SHOW_EVIDENCE",
        required_entities=["Aral Sea"], required_visual_concept="shrinking shoreline",
        semantic_domain="environment",
    )
    queries = [intent.query.lower() for intent in compile_search_intents(req)]
    assert not any(term in query for query in queries for term in ("watch", "foundation", "ownership"))


def test_beat_plan_preserves_exact_script_and_claims(monkeypatch):
    import json
    from app.documentary_v2 import beat_planner
    from app.documentary_v2.schemas import VerifiedClaim

    script = "The Aral Sea shrank. Fishing towns changed."
    claims = [VerifiedClaim("claim:aral", "The Aral Sea shrank.")]
    response = {"beats": [
        {"spoken_span": "The Aral Sea shrank.", "narrative_role": "HOOK", "primary_entities": ["Aral Sea"], "semantic_domain": "environment", "visual_purpose": "SHOW_EVIDENCE", "required_visual_concept": "shrinking shoreline", "claim_ids": ["invented"]},
        {"spoken_span": "Fishing towns changed.", "narrative_role": "PAYOFF", "primary_entities": [], "semantic_domain": "environment", "visual_purpose": "SHOW_PROCESS", "required_visual_concept": "fishing towns"},
    ]}
    monkeypatch.setattr(beat_planner, "_call_llm_with_fallback", lambda *args: (json.dumps(response), "fixture"))
    plan = beat_planner.plan_beats("Aral Sea", script, claims, "fixture")
    assert plan.gate == "PASS"
    assert " ".join(beat.spoken_span for beat in plan.beats) == script
    assert [beat.claim_ids for beat in plan.beats] == [["claim:aral"], []]
    assert plan.beats[0].visual_purpose == "SHOW_EVIDENCE"


def test_beat_plan_rejects_invented_entity_and_dropped_sentence(monkeypatch):
    import json
    from app.documentary_v2 import beat_planner

    script = "The Aral Sea shrank. Fishing towns changed."
    responses = [
        {"beats": [{"spoken_span": "The Aral Sea shrank.", "primary_entities": ["Rolex"]}, {"spoken_span": "Fishing towns changed."}]},
        {"beats": [{"spoken_span": "The Aral Sea shrank.", "primary_entities": ["Aral Sea"]}]},
    ]
    for response in responses:
        monkeypatch.setattr(beat_planner, "_call_llm_with_fallback", lambda *args: (json.dumps(response), "fixture"))
        plan = beat_planner.plan_beats("Aral Sea", script, [], "fixture")
        assert plan.gate == "REVIEW_REQUIRED"
        assert " ".join(beat.spoken_span for beat in plan.beats) == script


def _director_review_fixture(tmp_path, *, license="STOCK_LICENSED", policy="KNOWN_REUSABLE"):
    from PIL import Image
    from app.documentary_v2.director.pipeline import FixtureCandidate
    from app.documentary_v2.schemas import AssetProvenance, MediaCandidate, StoryBeat

    media = tmp_path / "watch.jpg"
    Image.new("RGB", (48, 48), (20, 20, 20)).save(media)
    provenance = AssetProvenance(
        provider="pexels", source_id="stock:1", source_url="https://example.test/watch",
        creator="Fixture Maker", license=license, license_policy=policy, stock=True,
    )
    candidate = MediaCandidate(
        "cand:review", provenance=provenance, query="Rolex watch",
        download_url="https://example.test/watch.jpg",
        preview_url="https://example.test/watch_thumb.jpg",
    )
    beat = StoryBeat(
        "beat:review", spoken_span="Rolex makes watches.", narrative_role="REVEAL",
        primary_entities=["Rolex"], semantic_domain="luxury_watch",
        required_visual_concept="Rolex watch",
    )
    return beat, {beat.beat_id: [FixtureCandidate(candidate, str(media), "actual_watch")]}


def test_director_budget_has_whole_job_limits():
    from app.documentary_v2.director.pipeline import DirectorBudget

    budget = DirectorBudget(max_total_searches=0, max_total_vlm=0, max_total_materializations=0)
    assert budget.max_total_vlm == 0


def test_director_zero_vlm_budget_records_stop(tmp_path):
    from app.documentary_v2.director.pipeline import DirectorBudget, run_director_plan
    from app.documentary_v2.verifier.mock import MockVisualVerifier

    beat, fixtures = _director_review_fixture(tmp_path)
    plan = run_director_plan(
        job_id="budget", topic="Rolex", story=None, beats=[beat], fixtures=fixtures,
        verifier_provider=MockVisualVerifier(), budget=DirectorBudget(max_total_vlm=0),
    )
    assert plan.diagnostics["vlm_calls"] == 0
    assert plan.diagnostics["budget_stop_reason"] == "total_vlm"


def test_selected_provenance_preserves_rights_and_creator(tmp_path):
    from app.documentary_v2.director.pipeline import run_director_plan
    from app.documentary_v2.verifier.mock import MockVisualVerifier

    beat, fixtures = _director_review_fixture(tmp_path)
    plan = run_director_plan(
        job_id="rights", topic="Rolex", story=None, beats=[beat], fixtures=fixtures,
        verifier_provider=MockVisualVerifier(),
    )
    assert plan.selections
    selection = plan.selections[0]
    source = plan.diagnostics["selected_provenance"][selection.asset_id]
    assert source["provider"] == "pexels"
    assert source["source_url"] == "https://example.test/watch"
    assert source["license"] == "STOCK_LICENSED"
    assert source["creator"] == "Fixture Maker"
    assert plan.diagnostics["selected_provenance"][selection.candidate_id] == source


def test_restricted_candidate_is_not_selected(tmp_path):
    from app.documentary_v2.director.pipeline import run_director_plan
    from app.documentary_v2.verifier.mock import MockVisualVerifier

    beat, fixtures = _director_review_fixture(tmp_path, license="RESTRICTED", policy="KNOWN_RESTRICTED")
    plan = run_director_plan(
        job_id="restricted", topic="Rolex", story=None, beats=[beat], fixtures=fixtures,
        verifier_provider=MockVisualVerifier(),
    )
    assert not plan.selections
