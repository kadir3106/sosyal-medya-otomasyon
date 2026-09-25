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
