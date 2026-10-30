"""Stage G canary contracts."""

import json

import pytest

from app.documentary_v2.pipeline_mode import pipeline_mode_diagnostics, resolve_pipeline_mode
from app.documentary_v2.schemas import PipelineMode


def test_canary_mode_requires_explicit_opt_in(monkeypatch):
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2_CANARY", "true")
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "true")
    monkeypatch.setenv("DIRECTOR_ENABLED", "false")
    assert resolve_pipeline_mode() == PipelineMode.LEGACY_STOCK
    assert resolve_pipeline_mode(canary=True) == PipelineMode.DOCUMENTARY_V2_CANARY


def test_canary_diagnostics_are_explicit_only(monkeypatch):
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2_CANARY", "true")
    assert "canary" not in pipeline_mode_diagnostics()
    assert pipeline_mode_diagnostics(canary=True)["pipeline_mode"] == "DOCUMENTARY_V2_CANARY"


def test_publish_true_rejected_before_topic_work(monkeypatch, tmp_path):
    from app.documentary_v2 import review_runner

    monkeypatch.setattr(review_runner, "prepare_review_story", lambda *a, **k: pytest.fail("research started"))
    with pytest.raises(ValueError, match="publish"):
        review_runner.run_topic_review("Aral Sea", tmp_path, publish=True)


def test_publish_true_rejected_before_stage_f_work(tmp_path):
    from app.documentary_v2.assembly.orchestrator import run_stage_f_pipeline

    with pytest.raises(ValueError, match="publish"):
        run_stage_f_pipeline(
            topic="Aral Sea", script="Script", claims=[], media_dir=tmp_path,
            audio_path="missing.mp3", word_boundaries=[], caption_path="missing.ass",
            publish=True,
        )


def test_preflight_rejects_unsourced_story_before_tts(monkeypatch, tmp_path):
    from app.documentary_v2 import review_runner
    from app.documentary_v2.beat_planner import BeatPlan
    from app.documentary_v2.review_story import PreparedStory
    from app.documentary_v2.schemas import StoryBeat, VerifiedStory

    prepared = PreparedStory(
        VerifiedStory("story:aral", "Aral Sea", "draft", "final"), [], "Aral Sea",
        {"FactQualityGate": "REVIEW_REQUIRED", "StoryQualityGate": "PASS", "StoryConsistencyGate": "PASS"},
    )
    monkeypatch.setattr(review_runner.config, "OPENROUTER_API_KEY", "fixture")
    monkeypatch.setattr(review_runner.config, "GROQ_API_KEY", "fixture")
    monkeypatch.setattr(review_runner, "prepare_review_story", lambda *a, **k: prepared)
    monkeypatch.setattr(review_runner, "plan_beats", lambda *a, **k: BeatPlan([StoryBeat("b", "final")], "PASS", []))
    monkeypatch.setattr(review_runner, "synthesize_speech", lambda *a, **k: pytest.fail("TTS started"))
    result = review_runner.run_topic_review("Aral Sea", tmp_path, canary_preflight=True)
    assert result.error == "UNSUPPORTED_CENTRAL_CLAIM"
    assert result.metrics["failed_at"] == "preflight"
    assert result.metrics["source_assessment"]["status"] == "REJECT"


def test_preflight_rejects_uncovered_important_beat_before_tts(monkeypatch, tmp_path):
    from app.documentary_v2 import review_runner
    from app.documentary_v2.beat_planner import BeatPlan
    from app.documentary_v2.review_story import PreparedStory
    from app.documentary_v2.schemas import (
        BeatCoverageReport, DocumentaryDirectorPlan, ShotSelection, StoryBeat,
        VerifiedClaim, VerifiedStory,
    )

    beats = [StoryBeat("covered", "one", importance="important"), StoryBeat("missing", "two", importance="important")]
    prepared = PreparedStory(
        VerifiedStory("story:aral", "Aral Sea", "draft", "final"),
        [VerifiedClaim("claim", "fact", status="supported", evidence=[{"url": "https://example.org"}])],
        "Aral Sea", {"FactQualityGate": "PASS", "StoryQualityGate": "PASS", "StoryConsistencyGate": "PASS"},
    )
    director_plan = DocumentaryDirectorPlan(
        "plan:aral", selections=[ShotSelection("shot:covered", "covered")],
        coverage=[BeatCoverageReport("covered", "COVERED", "important"), BeatCoverageReport("missing", "UNCOVERED", "important")],
    )
    monkeypatch.setattr(review_runner.config, "OPENROUTER_API_KEY", "fixture")
    monkeypatch.setattr(review_runner.config, "GROQ_API_KEY", "fixture")
    monkeypatch.setattr(review_runner, "prepare_review_story", lambda *a, **k: prepared)
    monkeypatch.setattr(review_runner, "plan_beats", lambda *a, **k: BeatPlan(beats, "PASS", []))
    monkeypatch.setattr(review_runner, "run_director_plan", lambda **k: director_plan)
    monkeypatch.setattr(review_runner, "synthesize_speech", lambda *a, **k: pytest.fail("TTS started"))
    result = review_runner.run_topic_review("Aral Sea", tmp_path, canary_preflight=True)
    assert result.error == "TOPIC_PREFLIGHT_REJECT"
    assert result.metrics["failed_at"] == "preflight"


def test_preflight_without_vlm_key_stops_before_visual_acquisition(monkeypatch, tmp_path):
    from app.documentary_v2 import review_runner
    from app.documentary_v2.beat_planner import BeatPlan
    from app.documentary_v2.review_story import PreparedStory
    from app.documentary_v2.schemas import StoryBeat, VerifiedClaim, VerifiedStory

    prepared = PreparedStory(
        VerifiedStory("story:aral", "Aral Sea", "draft", "final"),
        [VerifiedClaim("claim", "fact", status="supported", evidence=[{"url": "https://example.org"}])],
        "Aral Sea", {"FactQualityGate": "PASS", "StoryQualityGate": "PASS", "StoryConsistencyGate": "PASS"},
    )
    monkeypatch.setattr(review_runner.config, "OPENROUTER_API_KEY", "fixture")
    monkeypatch.setattr(review_runner.config, "GROQ_API_KEY", "")
    monkeypatch.setattr(review_runner, "prepare_review_story", lambda *a, **k: prepared)
    monkeypatch.setattr(review_runner, "plan_beats", lambda *a, **k: BeatPlan([StoryBeat("b", "final")], "PASS", []))
    monkeypatch.setattr(review_runner, "run_director_plan", lambda **k: pytest.fail("director started"))
    monkeypatch.setattr(review_runner, "synthesize_speech", lambda *a, **k: pytest.fail("TTS started"))
    result = review_runner.run_topic_review("Aral Sea", tmp_path, canary_preflight=True)
    assert result.error == "VLM_UNAVAILABLE"
    assert result.metrics["failed_at"] == "preflight"


def test_suite_requires_five_distinct_story_types(tmp_path):
    from app.documentary_v2.canary import load_suite

    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps([
        {"topic": "A", "story_type": "named_company_ownership", "selection_rationale": "evidence", "dimensions": ["entity"]},
        {"topic": "B", "story_type": "named_company_ownership", "selection_rationale": "evidence", "dimensions": ["entity"]},
    ]), encoding="utf-8")
    with pytest.raises(ValueError, match="story_type"):
        load_suite(suite)


def test_failed_job_leaves_truthful_package(monkeypatch, tmp_path):
    from app.documentary_v2 import canary
    from app.documentary_v2.assembly.orchestrator import StageFResult

    monkeypatch.setattr(canary, "run_topic_review", lambda *a, **k: StageFResult(
        k["job_id"], a[0], error="TOPIC_PREFLIGHT_REJECT",
        metrics={"failed_at": "preflight", "source_assessment": {"status": "REJECT"}},
        gates={"FactQualityGate": "REVIEW_REQUIRED"},
    ))
    entry = {"topic": "A", "story_type": "named_company_ownership", "selection_rationale": "evidence", "dimensions": ["entity"]}
    job = canary.run_canary_job(entry, tmp_path, job_id="g_001", max_job_elapsed_sec=60)
    folder = tmp_path / "g_001"
    for kind in ("EDL", "MANIFEST", "TRACE", "ATTRIBUTION"):
        payload = json.loads((folder / f"DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_{kind}_g_001.json").read_text(encoding="utf-8"))
        assert payload["artifact_status"] == "NOT_PRODUCED"
        assert payload["failed_at"] == "preflight"
        assert payload["data"] is None
        assert payload["failure_clusters"] == ["STORY"]
    assert "Decision: NOT_RUN" in (folder / "DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_HUMAN_REVIEW_g_001.md").read_text(encoding="utf-8")
    assert not (folder / "DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_g_001.mp4").exists()
    assert job["job_id"] == "g_001"


def test_publish_true_rejected_before_canary_directory(tmp_path):
    from app.documentary_v2.canary import run_canary_job

    with pytest.raises(ValueError, match="publish"):
        run_canary_job({"topic": "A"}, tmp_path, job_id="g_001", max_job_elapsed_sec=60, publish=True)
    assert not (tmp_path / "g_001").exists()


def test_corrupt_stage_f_artifact_fails_job_without_inventing_edl(monkeypatch, tmp_path):
    from app.documentary_v2 import canary
    from app.documentary_v2.assembly.orchestrator import StageFResult

    broken = tmp_path / "broken.json"
    broken.write_text("{broken", encoding="utf-8")
    monkeypatch.setattr(canary, "run_topic_review", lambda *a, **k: StageFResult(
        k["job_id"], a[0], edl_path=str(broken),
    ))
    entry = {"topic": "A", "story_type": "named_company_ownership", "selection_rationale": "evidence", "dimensions": ["entity"]}
    job = canary.run_canary_job(entry, tmp_path, job_id="g_002", max_job_elapsed_sec=60)
    edl = json.loads((tmp_path / "g_002" / "DOCUMENTARY_ENGINE_V2_STAGE_G_CANARY_EDL_g_002.json").read_text(encoding="utf-8"))
    assert edl["artifact_status"] == "NOT_PRODUCED"
    assert edl["data"] is None
    assert "artifact_read_failed" in job["error"]


@pytest.mark.parametrize(("code", "cluster"), [
    ("WRONG_ENTITY", "ENTITY_SELECTION"),
    ("ARCHIVE_NOT_FOUND", "ARCHIVE_RETRIEVAL"),
    ("GENERIC_PROCESS_AS_EVIDENCE", "PROCESS_VISUAL"),
    ("SOURCE_URL_MISSING", "PROVENANCE"),
    ("CAPTION_END_EARLY", "CAPTION"),
    ("GRAPHIC_TEXT_TOO_SMALL", "GRAPHIC_DENSITY"),
    ("FROZEN_TAIL", "TIMELINE"),
    ("UNSUPPORTED_CENTRAL_CLAIM", "STORY"),
    ("VLM_RATE_LIMIT", "VLM_RATE_LIMIT"),
    ("GENERIC_FILLER", "GENERIC_BROLL"),
    ("other_failure", "UNCLASSIFIED"),
])
def test_failure_code_cluster_mapping(code, cluster):
    from app.documentary_v2.canary import classify_failures

    assert classify_failures([code]) == (cluster, [cluster])


def test_multiple_failure_clusters_preserved_with_priority():
    from app.documentary_v2.canary import classify_failures

    assert classify_failures(["VLM_RATE_LIMIT", "WRONG_ENTITY", "SOURCE_URL_MISSING"]) == (
        "ENTITY_SELECTION", ["ENTITY_SELECTION", "PROVENANCE", "VLM_RATE_LIMIT"],
    )


def test_incomplete_human_review_stays_pending(tmp_path):
    from app.documentary_v2.canary import read_human_review

    review = tmp_path / "review.md"
    review.write_text("Decision: PASS\nQuality: GOOD\nManual intervention required: NOT_RUN\n", encoding="utf-8")
    assert read_human_review(review)["completed"] is False


def test_wrong_entity_blocks_autonomous_evidence_even_with_human_pass(tmp_path):
    from app.documentary_v2.canary import evaluate_canary_job

    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"mp4")
    job = {
        "job_id": "g", "story_type": "named_company_ownership", "paths": {"mp4": str(mp4)},
        "error": None, "gates": {"FactQualityGate": "PASS"},
        "metrics": {"failure_codes": ["WRONG_ENTITY"]},
    }
    review = {"completed": True, "decision": "PASS", "quality": "GOOD", "manual_intervention_required": False, "findings": [], "dimensions": {}}
    evaluated = evaluate_canary_job(job, review)
    assert evaluated["counts_as_autonomous_evidence"] is False
    assert evaluated["primary_cluster"] == "ENTITY_SELECTION"


def test_manual_asset_injection_retains_quality_but_excludes_autonomy(tmp_path):
    from app.documentary_v2.canary import evaluate_canary_job

    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"mp4")
    job = {"job_id": "g", "story_type": "physical_process", "paths": {"mp4": str(mp4)}, "error": None, "gates": {}, "metrics": {}}
    review = {"completed": True, "decision": "PASS", "quality": "PREMIUM", "manual_intervention_required": True, "findings": [], "dimensions": {}}
    evaluated = evaluate_canary_job(job, review)
    assert evaluated["human_quality"] == "PREMIUM"
    assert evaluated["manual_intervention_required"] is True
    assert evaluated["counts_as_autonomous_evidence"] is False


def test_external_asset_without_source_url_blocks_acceptance(tmp_path):
    from app.documentary_v2.canary import evaluate_canary_job

    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"mp4")
    attribution = tmp_path / "attribution.json"
    attribution.write_text(json.dumps({"data": [{"internal": False, "license": "STOCK_LICENSED", "source_url": ""}]}), encoding="utf-8")
    job = {
        "job_id": "g", "story_type": "physical_process",
        "paths": {"mp4": str(mp4), "attribution": str(attribution)},
        "error": None, "gates": {"LicenseProvenanceGate": "PASS"}, "metrics": {},
    }
    review = {"completed": True, "decision": "PASS", "quality": "GOOD", "manual_intervention_required": False, "findings": [], "dimensions": {}}
    evaluated = evaluate_canary_job(job, review)
    assert evaluated["counts_as_autonomous_evidence"] is False
    assert evaluated["primary_cluster"] == "PROVENANCE"


def test_missing_mandatory_gate_cannot_be_accepted(tmp_path):
    from app.documentary_v2.canary import evaluate_canary_job

    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"mp4")
    attribution = tmp_path / "attribution.json"
    attribution.write_text(json.dumps({"data": [{"internal": True, "license": "INTERNAL"}]}), encoding="utf-8")
    job = {
        "job_id": "g", "story_type": "physical_process",
        "paths": {"mp4": str(mp4), "attribution": str(attribution)},
        "error": None, "gates": {"FactQualityGate": "PASS"}, "metrics": {},
    }
    review = {"completed": True, "decision": "PASS", "quality": "GOOD", "manual_intervention_required": False, "findings": [], "dimensions": {}}
    assert evaluate_canary_job(job, review)["counts_as_autonomous_evidence"] is False


def test_early_research_failure_does_not_fabricate_provenance_failure(tmp_path):
    from app.documentary_v2.canary import evaluate_canary_job

    attribution = tmp_path / "attribution.json"
    attribution.write_text(json.dumps({"artifact_status": "NOT_PRODUCED", "data": None}), encoding="utf-8")
    job = {
        "job_id": "g", "story_type": "physical_process", "paths": {"attribution": str(attribution)},
        "error": "text_llm_gateway_unavailable", "failed_at": "topic_review", "gates": {},
        "metrics": {"remote_vision_available": False},
    }
    review = {"completed": False, "decision": "NOT_RUN", "quality": "NOT_RUN", "manual_intervention_required": False, "findings": [], "dimensions": {}}
    evaluated = evaluate_canary_job(job, review)
    assert "PROVENANCE" not in evaluated["all_clusters"]
    assert evaluated["primary_cluster"] == "UNCLASSIFIED"


@pytest.mark.parametrize("code", [
    "GENERIC_PROCESS_AS_EVIDENCE", "SOURCE_URL_MISSING", "FROZEN_TAIL",
    "CAPTION_END_EARLY", "GENERIC_BROLL_DOMINANT", "VLM_RATE_LIMIT",
])
def test_hard_failure_codes_block_human_approved_job(tmp_path, code):
    from app.documentary_v2.canary import evaluate_canary_job

    mp4 = tmp_path / "video.mp4"
    mp4.write_bytes(b"mp4")
    job = {"job_id": "g", "story_type": "physical_process", "paths": {"mp4": str(mp4)}, "error": None,
           "gates": {"FactQualityGate": "PASS"}, "metrics": {"failure_codes": [code]}}
    review = {"completed": True, "decision": "PASS", "quality": "GOOD", "manual_intervention_required": False, "findings": [], "dimensions": {}}
    assert evaluate_canary_job(job, review)["counts_as_autonomous_evidence"] is False


def _accepted_job(job_id, story_type, quality="GOOD"):
    return {
        "job_id": job_id, "story_type": story_type, "topic": story_type,
        "counts_as_autonomous_evidence": True, "human_review_completed": True,
        "human_decision": "PASS", "human_quality": quality,
        "manual_intervention_required": False, "mp4_produced": True,
        "primary_cluster": "", "all_clusters": [], "failure_codes": [],
        "metrics": {}, "gates": {}, "paths": {},
    }


def test_aggregate_pass_needs_three_distinct_types_and_good_majority():
    from app.documentary_v2.canary import build_scorecard

    jobs = [_accepted_job("a", "named_company_ownership"),
            _accepted_job("b", "physical_process", "PREMIUM"),
            _accepted_job("c", "historical_location", "ACCEPTABLE")]
    assert build_scorecard(jobs, test_set_exhausted=True)["decision"] == "CANARY_PASS"
    jobs[2]["story_type"] = "physical_process"
    assert build_scorecard(jobs, test_set_exhausted=True)["decision"] == "CANARY_PARTIAL"
    jobs[2]["story_type"] = "historical_location"
    jobs[1]["human_quality"] = "ACCEPTABLE"
    assert build_scorecard(jobs, test_set_exhausted=True)["decision"] == "CANARY_PARTIAL"


def test_aggregate_excludes_manual_and_pending_jobs():
    from app.documentary_v2.canary import build_scorecard

    jobs = [_accepted_job("a", "named_company_ownership"), _accepted_job("b", "physical_process")]
    manual = _accepted_job("c", "historical_location")
    manual.update(manual_intervention_required=True, counts_as_autonomous_evidence=False)
    pending = _accepted_job("d", "abstract_financial_mechanism")
    pending.update(human_review_completed=False, human_decision="NOT_RUN", counts_as_autonomous_evidence=False)
    scorecard = build_scorecard(jobs + [manual, pending], test_set_exhausted=True)
    assert scorecard["decision"] == "CANARY_PARTIAL"
    assert scorecard["autonomous_accepted_count"] == 2
    assert scorecard["pending_human_count"] == 1
    assert scorecard["generalization_matrix"][2]["counts_as_autonomous_evidence"] is False
    assert "composite_score" not in scorecard


def test_aggregate_systemic_failure_beats_partial():
    from app.documentary_v2.canary import build_scorecard

    accepted = _accepted_job("a", "named_company_ownership")
    failures = [
        {**_accepted_job("b", "physical_process"), "counts_as_autonomous_evidence": False,
         "human_decision": "FAIL", "all_clusters": ["PROVENANCE"], "primary_cluster": "PROVENANCE"},
        {**_accepted_job("c", "historical_location"), "counts_as_autonomous_evidence": False,
         "human_decision": "FAIL", "all_clusters": ["PROVENANCE"], "primary_cluster": "PROVENANCE"},
    ]
    assert build_scorecard([accepted, *failures], test_set_exhausted=True)["decision"] == "CANARY_FAIL"


def test_cli_rejects_publish_before_job_creation(tmp_path):
    from scripts.stage_g_canary import main

    with pytest.raises(SystemExit):
        main(["--publish", "--output-root", str(tmp_path)])
    assert not list(tmp_path.iterdir())


def test_aggregate_writes_named_report_and_scorecard(tmp_path):
    from app.documentary_v2.canary import build_scorecard, write_aggregate

    report, scorecard = write_aggregate(build_scorecard([], test_set_exhausted=False), tmp_path)
    assert report.name == "DOCUMENTARY_ENGINE_V2_STAGE_G_REPORT.md"
    assert scorecard.name == "DOCUMENTARY_ENGINE_V2_STAGE_G_SCORECARD.json"
    assert json.loads(scorecard.read_text(encoding="utf-8"))["decision"] == "PENDING"


def test_aggregate_does_not_trust_stale_autonomy_flag():
    from app.documentary_v2.canary import build_scorecard

    jobs = [_accepted_job("a", "named_company_ownership"),
            _accepted_job("b", "physical_process"),
            _accepted_job("c", "historical_location")]
    jobs[2]["human_review_completed"] = False
    jobs[2]["human_decision"] = "NOT_RUN"
    assert build_scorecard(jobs, test_set_exhausted=True)["decision"] != "CANARY_PASS"


def test_safety_boundary_defect_prevents_aggregate_pass():
    from app.documentary_v2.canary import build_scorecard

    jobs = [_accepted_job("a", "named_company_ownership"),
            _accepted_job("b", "physical_process"),
            _accepted_job("c", "historical_location")]
    jobs.append({"job_id": "d", "story_type": "historical_founder_person", "safety_boundary_violation": "publishing_attempted", "counts_as_autonomous_evidence": False})
    assert build_scorecard(jobs, test_set_exhausted=True)["decision"] == "CANARY_FAIL"


def test_five_infrastructure_blocked_jobs_are_partial_not_engine_failure():
    from app.documentary_v2.canary import build_scorecard

    jobs = []
    for index, story_type in enumerate(sorted((
        "named_company_ownership", "historical_founder_person", "physical_process",
        "historical_location", "abstract_financial_mechanism",
    ))):
        job = _accepted_job(str(index), story_type)
        job.update(counts_as_autonomous_evidence=False, mp4_produced=False,
                   human_review_completed=False, human_decision="NOT_RUN",
                   infrastructure_blocked=True, primary_cluster="UNCLASSIFIED",
                   all_clusters=["UNCLASSIFIED"], error="text_llm_gateway_unavailable")
        jobs.append(job)
    scorecard = build_scorecard(jobs, test_set_exhausted=True)
    assert scorecard["decision"] == "CANARY_PARTIAL"
    assert scorecard["autonomous_accepted_count"] == 0
