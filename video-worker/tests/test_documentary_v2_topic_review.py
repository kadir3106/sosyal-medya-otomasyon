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


def test_fallback_beats_are_not_rolex():
    from app.documentary_v2.assembly.orchestrator import _beats_from_script

    beats = _beats_from_script("The Aral Sea shrank. Fishing towns changed.", "Aral Sea")
    assert all("luxury_watch" not in beat.semantic_domain for beat in beats)
    assert all("Rolex" not in beat.primary_entities for beat in beats)
    assert " ".join(beat.spoken_span for beat in beats) == "The Aral Sea shrank. Fishing towns changed."


def _mock_stage_f(monkeypatch, tmp_path, *, license="UNKNOWN", coverage="COVERED"):
    from app.documentary_v2.assembly import orchestrator
    from app.documentary_v2.assembly.technical_qa import TechnicalQAResult
    from app.documentary_v2.schemas import (
        BeatCoverageReport, DocumentaryDirectorPlan, EditDecision,
        EditDecisionList, RenderManifest, ShotSelection, StoryBeat,
    )

    beat = StoryBeat("beat:test", spoken_span="The Aral Sea shrank.", importance="important")
    plan = DocumentaryDirectorPlan(
        "plan:test", beats=[beat],
        selections=[ShotSelection("shot:test", beat.beat_id, asset_id="asset:test", candidate_id="cand:test")],
        coverage=[BeatCoverageReport(beat.beat_id, status=coverage, importance="important")],
        diagnostics={"selected_provenance": {"asset:test": {"provider": "fixture", "license": license}}},
    )
    edl = EditDecisionList("edl:test", "job:test", "job:test", decisions=[
        EditDecision("shot:test", beat.beat_id, asset_id="asset:test", media_type="stock_video", source_kind="stock", local_path="fixture.mp4", start_time=0, end_time=2),
    ])
    monkeypatch.setattr(orchestrator, "get_audio_duration", lambda path: 2.0)
    monkeypatch.setattr(orchestrator, "compile_edl", lambda *args, **kwargs: edl)
    monkeypatch.setattr(orchestrator, "render_from_edl", lambda *args, **kwargs: RenderManifest("render:test", "job:test", "job:test"))
    monkeypatch.setattr(orchestrator, "technical_qa", lambda *args, **kwargs: TechnicalQAResult(True, duration_sec=2.0))
    monkeypatch.setattr(orchestrator, "edl_metrics", lambda edl: {"unique_vius": 1, "seconds_by_class": {"stock_video": 2.0}})
    return orchestrator, plan, beat


def test_stage_f_gate_defaults_are_not_pass(monkeypatch, tmp_path):
    orchestrator, plan, beat = _mock_stage_f(monkeypatch, tmp_path)
    result = orchestrator.run_stage_f_pipeline(
        topic="Aral Sea", script=beat.spoken_span, claims=[], media_dir=tmp_path,
        job_id="defaults", audio_path="fixture.wav", word_boundaries=[], caption_path="fixture.ass",
        director_plan=plan, beats=[beat], run_critic=False,
    )
    assert result.gates["FactQualityGate"] == "NOT_RUN"
    assert result.gates["StoryQualityGate"] == "NOT_RUN"
    assert result.gates["StoryConsistencyGate"] == "NOT_RUN"
    assert result.gates["BeatPlanGate"] == "NOT_RUN"
    assert result.gates["FinalVideoQualityGate"] == "NOT_RUN"
    assert result.gates["LicenseProvenanceGate"] == "REVIEW_REQUIRED"


def test_stage_f_gate_uses_real_story_and_rights(monkeypatch, tmp_path):
    orchestrator, plan, beat = _mock_stage_f(monkeypatch, tmp_path, license="RESTRICTED", coverage="PARTIAL")
    result = orchestrator.run_stage_f_pipeline(
        topic="Aral Sea", script=beat.spoken_span, claims=[], media_dir=tmp_path,
        job_id="real-gates", audio_path="fixture.wav", word_boundaries=[], caption_path="fixture.ass",
        director_plan=plan, beats=[beat], run_critic=False,
        story_gates={"FactQualityGate": "PASS", "StoryQualityGate": "REVIEW_REQUIRED", "StoryConsistencyGate": "PASS"},
        beat_plan_gate="REVIEW_REQUIRED",
    )
    assert result.gates["FactQualityGate"] == "PASS"
    assert result.gates["StoryQualityGate"] == "REVIEW_REQUIRED"
    assert result.gates["BeatPlanGate"] == "REVIEW_REQUIRED"
    assert result.gates["VisualCoverageGate"] == "REVIEW_REQUIRED"
    assert result.gates["LicenseProvenanceGate"] == "FAIL"


def test_stage_f_restricted_rights_block_render(monkeypatch, tmp_path):
    orchestrator, plan, beat = _mock_stage_f(monkeypatch, tmp_path, license="RESTRICTED")
    monkeypatch.setattr(orchestrator, "render_from_edl", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("restricted asset was rendered")))
    result = orchestrator.run_stage_f_pipeline(
        topic="Aral Sea", script=beat.spoken_span, claims=[], media_dir=tmp_path,
        job_id="restricted-render", audio_path="fixture.wav", word_boundaries=[], caption_path="fixture.ass",
        director_plan=plan, beats=[beat], run_critic=False,
    )
    assert result.error == "restricted_license"
    assert result.gates["LicenseProvenanceGate"] == "FAIL"
    assert not result.output_mp4


def test_stage_f_render_timeout_is_failed_package(monkeypatch, tmp_path):
    import subprocess

    orchestrator, plan, beat = _mock_stage_f(monkeypatch, tmp_path)
    monkeypatch.setattr(orchestrator, "render_from_edl", lambda *args, **kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("ffmpeg", 1)))
    result = orchestrator.run_stage_f_pipeline(
        topic="Aral Sea", script=beat.spoken_span, claims=[], media_dir=tmp_path,
        job_id="timeout", audio_path="fixture.wav", word_boundaries=[], caption_path="fixture.ass",
        director_plan=plan, beats=[beat], run_critic=False,
    )
    assert result.error.startswith("render_failed:")
    assert not result.output_mp4
    assert result.gates["TechnicalRenderQA"] == "FAIL"


def test_stage_f_critic_never_exceeds_three_frames(monkeypatch, tmp_path):
    from app.config import config
    from app.documentary_v2.schemas import FinalVideoCritique

    orchestrator, plan, beat = _mock_stage_f(monkeypatch, tmp_path, license="STOCK_LICENSED")
    seen = []

    class Critic:
        def __init__(self, **kwargs):
            pass

        def critique(self, *args, **kwargs):
            seen.append(kwargs["max_frames"])
            return FinalVideoCritique("critic:test", decision="PASS")

    monkeypatch.setattr(config, "FINAL_CRITIC_ENABLED", True)
    monkeypatch.setattr(orchestrator, "FinalVideoCritic", Critic)
    result = orchestrator.run_stage_f_pipeline(
        topic="Aral Sea", script=beat.spoken_span, claims=[], media_dir=tmp_path,
        job_id="critic-budget", audio_path="fixture.wav", word_boundaries=[], caption_path="fixture.ass",
        director_plan=plan, beats=[beat], run_critic=True, run_repair=False, critic_frame_budget=10,
    )
    assert seen == [3]
    assert result.gates["FinalVideoQualityGate"] == "PASS"


def test_edl_renderer_passes_timeout_to_ffmpeg(monkeypatch, tmp_path):
    import subprocess
    import pytest
    from app.documentary_v2.assembly import edl_render
    from app.documentary_v2.schemas import EditDecision, EditDecisionList

    still = tmp_path / "still.png"
    still.write_bytes(b"fixture")
    edl = EditDecisionList("edl:timeout", "job:timeout", "job:timeout", decisions=[
        EditDecision("shot:1", "beat:1", local_path=str(still), start_time=0, end_time=2),
    ])
    monkeypatch.setattr(edl_render, "get_audio_duration", lambda path: 2.0)

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 7.0
        raise subprocess.TimeoutExpired("ffmpeg", 7.0)

    monkeypatch.setattr(edl_render.subprocess, "run", timeout)
    with pytest.raises(subprocess.TimeoutExpired):
        edl_render.render_from_edl(
            edl, audio_path="fixture.wav", caption_path="fixture.ass",
            output_path=str(tmp_path / "out.mp4"), work_dir=str(tmp_path / "render"),
            render_timeout_sec=7.0,
        )


def test_automated_verdict_requires_every_mandatory_gate():
    from app.documentary_v2.review_runner import MANDATORY_GATES, automated_verdict

    gates = {name: "PASS" for name in MANDATORY_GATES}
    assert automated_verdict(gates) == "PASS"
    gates["FinalVideoQualityGate"] = "NOT_RUN"
    assert automated_verdict(gates) == "REVIEW_REQUIRED"
    gates["LicenseProvenanceGate"] = "FAIL"
    assert automated_verdict(gates) == "FAIL"


def _mock_review_runner(monkeypatch, *, create_audio=True, create_captions=True, stage_f_gates=None, stage_f_metrics=None):
    from pathlib import Path
    from app.documentary_v2 import review_runner
    from app.documentary_v2.assembly.orchestrator import StageFResult
    from app.documentary_v2.beat_planner import BeatPlan
    from app.documentary_v2.review_story import PreparedStory
    from app.documentary_v2.schemas import StoryBeat, VerifiedStory

    script = "The Aral Sea shrank in 1960."
    prepared = PreparedStory(
        VerifiedStory("story:aral", "Aral Sea", "Draft changed.", script), [], "Aral Sea",
        {"FactQualityGate": "PASS", "StoryQualityGate": "PASS", "StoryConsistencyGate": "PASS"},
    )
    beat_plan = BeatPlan([StoryBeat("beat:aral", spoken_span=script, importance="important")], "PASS", [])
    calls = {}
    monkeypatch.setattr(review_runner.config, "OPENROUTER_API_KEY", "fixture")
    monkeypatch.setattr(review_runner.config, "GROQ_API_KEY", "fixture")
    monkeypatch.setattr(review_runner, "prepare_review_story", lambda *args, **kwargs: prepared)
    monkeypatch.setattr(review_runner, "plan_beats", lambda *args, **kwargs: beat_plan)

    async def tts(text, output_path, **kwargs):
        calls["tts_text"] = text
        if create_audio:
            Path(output_path).write_bytes(b"audio")
        return [{"text": "The", "start": 0, "end": 1}]

    def captions(words, output_path, **kwargs):
        if create_captions:
            Path(output_path).write_text("[Script Info]\n", encoding="utf-8")
        calls["caption_script"] = kwargs.get("script_text")
        return output_path

    def stage_f(**kwargs):
        calls["stage_f"] = kwargs
        return StageFResult(
            kwargs["job_id"], kwargs["topic"], output_mp4=str(Path(kwargs["media_dir"]) / "review.mp4"),
            gates=stage_f_gates or {name: "PASS" for name in review_runner.MANDATORY_GATES},
            metrics=stage_f_metrics or {},
        )

    monkeypatch.setattr(review_runner, "synthesize_speech", tts)
    monkeypatch.setattr(review_runner, "write_ass", captions)
    monkeypatch.setattr(review_runner, "get_or_create_bgm", lambda *args, **kwargs: None)
    monkeypatch.setattr(review_runner, "run_stage_f_pipeline", stage_f)
    return review_runner, calls, script


def test_runner_blank_topic_stops_before_tts(tmp_path):
    from app.documentary_v2.review_runner import run_topic_review

    result = run_topic_review(" ", tmp_path, job_id="blank")
    assert result.error == "empty_topic"
    assert result.metrics["automated_verdict"] == "FAIL"
    assert result.report_path


def test_runner_uses_exact_final_script_and_review_only(monkeypatch, tmp_path):
    from pathlib import Path

    review_runner, calls, script = _mock_review_runner(monkeypatch)
    result = review_runner.run_topic_review("Aral Sea", tmp_path, job_id="review-test")
    assert calls["tts_text"] == script
    assert calls["caption_script"] == script
    assert calls["stage_f"]["live_acquire"] is True
    assert calls["stage_f"]["materialize"] is True
    assert calls["stage_f"]["story_gates"]["FactQualityGate"] == "PASS"
    assert calls["stage_f"]["beat_plan_gate"] == "PASS"
    assert calls["stage_f"]["beats"][0].spoken_span == script
    assert result.publish is False
    assert result.metrics["automated_verdict"] == "PASS"
    assert "Slideshow hissi" in Path(result.report_path).read_text(encoding="utf-8")


def test_runner_missing_audio_returns_failed_report(monkeypatch, tmp_path):
    review_runner, calls, _ = _mock_review_runner(monkeypatch, create_audio=False)
    result = review_runner.run_topic_review("Aral Sea", tmp_path, job_id="no-audio")
    assert result.error == "missing_audio_or_captions"
    assert result.metrics["automated_verdict"] == "FAIL"
    assert "stage_f" not in calls


def test_runner_missing_caption_returns_failed_report(monkeypatch, tmp_path):
    review_runner, calls, _ = _mock_review_runner(monkeypatch, create_captions=False)
    result = review_runner.run_topic_review("Aral Sea", tmp_path, job_id="no-caption")
    assert result.error == "missing_audio_or_captions"
    assert result.metrics["automated_verdict"] == "FAIL"
    assert "stage_f" not in calls


def test_runner_critic_outage_requires_review(monkeypatch, tmp_path):
    from app.documentary_v2.review_runner import MANDATORY_GATES

    gates = {name: "PASS" for name in MANDATORY_GATES}
    gates["FinalVideoQualityGate"] = "REVIEW_REQUIRED"
    review_runner, _, _ = _mock_review_runner(monkeypatch, stage_f_gates=gates)
    result = review_runner.run_topic_review("Aral Sea", tmp_path, job_id="critic-outage")
    assert result.metrics["automated_verdict"] == "REVIEW_REQUIRED"


def test_runner_exhausted_visual_budget_requires_review(monkeypatch, tmp_path):
    review_runner, _, _ = _mock_review_runner(
        monkeypatch, stage_f_metrics={"director_budget_stop_reason": "total_vlm"}
    )
    result = review_runner.run_topic_review("Aral Sea", tmp_path, job_id="budget-stop")
    assert result.metrics["automated_verdict"] == "REVIEW_REQUIRED"


def test_runner_missing_vision_key_requires_review(monkeypatch, tmp_path):
    review_runner, _, _ = _mock_review_runner(monkeypatch)
    monkeypatch.setattr(review_runner.config, "GROQ_API_KEY", "")
    result = review_runner.run_topic_review("Aral Sea", tmp_path, job_id="no-vision")
    assert result.metrics["automated_verdict"] == "REVIEW_REQUIRED"


def test_cross_topic_queries_and_evidence_stay_isolated(monkeypatch):
    from app.fact_verify import FactVerificationProvider
    from app.script_claims import ScriptClaim
    from app.documentary_v2.director.query_compiler import compile_search_intents
    from app.documentary_v2.schemas import ShotRequirement

    for topic in ("Aral Sea", "Panama Canal", "Rolex"):
        titles = []
        provider = FactVerificationProvider()
        monkeypatch.setattr(provider, "_wikipedia_evidence", lambda title: titles.append(title) or {})
        monkeypatch.setattr(provider, "_wikipedia_search_extract", lambda query: None)
        provider.verify_claims([ScriptClaim("c", f"{topic} changed.", "historical", [topic], risk="HIGH", verification_required=True)], topic=topic)
        req = ShotRequirement("sr:test", "beat:test", visual_purpose="SHOW_EVIDENCE", required_entities=[topic], required_visual_concept=f"{topic} evidence")
        queries = [intent.query for intent in compile_search_intents(req)]
        if topic != "Rolex":
            assert not any("Rolex" in value or "Wilsdorf" in value for value in titles + queries)
        assert topic in titles
