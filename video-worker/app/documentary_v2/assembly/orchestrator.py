"""Stage F orchestrator — VerifiedStory → EDL → render → critic → repair → review package.

Explicit entry only. Does not enable DOCUMENTARY_ENGINE_V2 globally.
Does not publish.
"""
from __future__ import annotations

import json
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from app.documentary_v2.assembly.attribution import build_attribution_manifest
from app.documentary_v2.assembly.edl_render import render_from_edl
from app.documentary_v2.assembly.final_critic import FinalVideoCritic
from app.documentary_v2.assembly.repair import TargetedBeatRepair
from app.documentary_v2.assembly.technical_qa import technical_qa
from app.documentary_v2.assembly.timeline import compile_edl, edl_metrics
from app.documentary_v2.director.pipeline import DirectorBudget, run_director_plan
from app.documentary_v2.recovery.engine import VisualRecoveryEngine
from app.documentary_v2.schemas import (
    DocumentaryDirectorPlan,
    FinalVideoCritique,
    ShotRequirement,
    StoryBeat,
    VerifiedClaim,
    VerifiedStory,
)
from app.render import get_audio_duration


@dataclass
class StageFResult:
    job_id: str
    topic: str
    output_mp4: str = ""
    edl_path: str = ""
    manifest_path: str = ""
    trace_path: str = ""
    attribution_path: str = ""
    report_path: str = ""
    critique: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    gates: dict = field(default_factory=dict)
    repairs: list[dict] = field(default_factory=list)
    publish: bool = False
    v2_enabled_default: bool = False
    error: str = ""
    script: str = ""
    beats: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _write_json(path: Path, payload: Any) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False)[:800000], encoding="utf-8")
    return str(path)


def no_slideshow_gate(metrics: dict, edl: Any) -> str:
    """Flag low native-motion coverage for human review, never infer motion from zooms."""
    if metrics.get("unique_vius", 0) < 1:
        return "FAIL"
    decisions = edl.decisions or []
    if not decisions:
        return "FAIL"
    real_seconds = sum(
        float((metrics.get("seconds_by_class") or {}).get(kind, 0))
        for kind in ("real_entity_video", "archive_video", "stock_video")
    )
    total_seconds = max(float(d.end_time) for d in decisions)
    first_real_motion = min(
        (float(d.start_time) for d in decisions
         if not d.synthetic and "video" in (d.media_type or "").lower()),
        default=float("inf"),
    )
    if real_seconds / max(total_seconds, 1.0) < 0.4 or first_real_motion > 8.0:
        return "REVIEW_REQUIRED"
    return "PASS"


def _license_gate(attribution: list[dict]) -> str:
    rights = [str(entry.get("license") or "UNKNOWN") for entry in attribution]
    if any(right in {"RESTRICTED", "PROPRIETARY"} for right in rights):
        return "FAIL"
    if not rights or any(right not in {"INTERNAL", "STOCK_LICENSED", "PUBLIC_DOMAIN", "CC0"} for right in rights):
        return "REVIEW_REQUIRED"
    return "PASS"


def _beats_from_script(script: str, topic: str) -> list[StoryBeat]:
    """Neutral compatibility fallback; caller must keep BeatPlanGate unverified."""
    parts = [part for part in re.split(r"(?<=[.!?])\s+", script.strip()) if part]
    roles = ["hook", "setup", "development", "evidence", "reveal", "payoff"]
    beats: list[StoryBeat] = []
    for i, text in enumerate(parts):
        role = roles[min(i, len(roles) - 1)]
        importance = "important" if role in {"hook", "evidence", "reveal", "payoff"} else "supporting"
        beats.append(
            StoryBeat(
                beat_id=f"beat:{i}:{role}",
                spoken_span=text,
                narrative_role=role,
                required_visual_concept=text[:80],
                semantic_domain="unknown",
                primary_entities=[],
                importance=importance,
                estimated_duration=max(1.8, min(4.5, len(text.split()) * 0.35)),
            )
        )
    if not beats:
        beats.append(
            StoryBeat(
                beat_id="beat:0:hook",
                spoken_span=topic,
                narrative_role="hook",
                required_visual_concept=topic,
                importance="important",
            )
        )
    return beats


def run_stage_f_pipeline(
    *,
    topic: str,
    script: str,
    claims: list[VerifiedClaim],
    media_dir: str | Path,
    job_id: str | None = None,
    audio_path: str,
    word_boundaries: list[dict],
    caption_path: str,
    bgm_path: str | None = None,
    bgm_volume: float = 0.12,
    provenance_by_asset: dict[str, dict] | None = None,
    director_plan: DocumentaryDirectorPlan | None = None,
    asset_paths: dict[str, str] | None = None,
    recovery_paths: dict[str, str] | None = None,
    relationship_edges: list[dict] | None = None,
    story_gates: dict[str, str] | None = None,
    beat_plan_gate: str = "NOT_RUN",
    timeline_events: list[dict] | None = None,
    critic_frame_budget: int = 3,
    run_critic: bool = True,
    run_repair: bool = True,
    live_acquire: bool = False,
    materialize: bool = False,
    verifier_provider: Any = None,
    director_budget: DirectorBudget | None = None,
    beats: list[StoryBeat] | None = None,
    fixtures: dict | None = None,
) -> StageFResult:
    """Assemble review package from prepared audio + director plan / assets."""
    from app.config import config

    t0 = time.perf_counter()
    jid = job_id or f"sf_{uuid.uuid4().hex[:10]}"
    media = Path(media_dir)
    work = media / "work" / jid
    work.mkdir(parents=True, exist_ok=True)
    out_mp4 = media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_REAL_{jid}.mp4"

    result = StageFResult(
        job_id=jid, topic=topic, publish=False, v2_enabled_default=False, script=script
    )
    result.gates["FinalVideoQualityGate"] = "NOT_RUN"
    for name in ("FactQualityGate", "StoryQualityGate", "StoryConsistencyGate"):
        result.gates[name] = (story_gates or {}).get(name, "NOT_RUN")
    result.gates["BeatPlanGate"] = beat_plan_gate

    story = VerifiedStory(
        story_id=f"story:{jid}",
        topic=topic,
        final_script=script,
        raw_script=script,
        claim_ids=[c.claim_id for c in claims],
    )
    beats = list(beats) if beats else _beats_from_script(script, topic)
    result.beats = [b.to_dict() for b in beats]

    if director_plan is None:
        director_plan = run_director_plan(
            job_id=jid,
            topic=topic,
            story=story,
            beats=beats,
            live_acquire=live_acquire and not fixtures,
            materialize=materialize and live_acquire and not fixtures,
            work_dir=work / "director",
            verifier_provider=verifier_provider,
            budget=director_budget or DirectorBudget(max_vlm_per_shot=3, max_search_intents_per_shot=2),
            fixtures=fixtures,
        )

    recovery_paths = dict(recovery_paths or {})
    asset_paths = dict(asset_paths or {})
    # Seed from director materialize map
    for k, v in (director_plan.diagnostics or {}).get("asset_paths", {}).items():
        if v and Path(v).is_file():
            asset_paths.setdefault(k, v)

    eng = VisualRecoveryEngine()
    cov_by_beat = {c.beat_id: c for c in (director_plan.coverage or [])}
    for beat in beats:
        cov = cov_by_beat.get(beat.beat_id)
        has_sel = any(s.beat_id == beat.beat_id for s in (director_plan.selections or []))
        if has_sel and cov and cov.status == "COVERED":
            continue
        if beat.beat_id in recovery_paths:
            continue
        # Prefer recovery for uncovered / partial important beats
        if has_sel and cov and cov.status == "COVERED":
            continue
        if has_sel and beat.importance != "important":
            continue
        req = next(
            (s for s in (director_plan.shot_requirements or []) if s.beat_id == beat.beat_id),
            None,
        )
        if req is None:
            req = ShotRequirement(
                shot_requirement_id=f"sr:{beat.beat_id}",
                beat_id=beat.beat_id,
                visual_purpose="EXPLAIN_RELATIONSHIP"
                if "own" in (beat.spoken_span or "").lower() or beat.semantic_domain.endswith("ownership")
                else "ESTABLISH_CONTEXT",
                semantic_domain=beat.semantic_domain,
                required_entities=list(beat.primary_entities),
                required_visual_concept=beat.required_visual_concept,
                evidence_role="EVIDENCE_REQUIRED"
                if beat.narrative_role in {"evidence", "reveal"}
                else "ILLUSTRATION_ACCEPTABLE",
                claim_ids=list(beat.claim_ids),
                estimated_duration=beat.estimated_duration,
                importance=beat.importance,
            )
        # Skip recovery if we already have a real selected asset for this beat
        if has_sel and asset_paths.get(beat.beat_id):
            continue
        rr = eng.recover(
            req,
            failure_reason="EVIDENCE_NOT_FOUND"
            if req.visual_purpose in {"EXPLAIN_RELATIONSHIP", "SHOW_EVIDENCE"}
            else "NO_CANDIDATES",
            claims=claims,
            relationship_edges=relationship_edges,
            timeline_events=list(timeline_events or []),
            output_dir=work,
            job_id=jid,
            render=True,
            generate=False,
        )
        if rr.artifact_path:
            recovery_paths[beat.beat_id] = rr.artifact_path
            if rr.motion_graphic_plan:
                director_plan.motion_graphic_plans.append(rr.motion_graphic_plan)

    narration_dur = get_audio_duration(audio_path)
    edl = compile_edl(
        director_plan,
        narration_duration_sec=narration_dur,
        word_boundaries=word_boundaries,
        asset_paths=asset_paths,
        recovery_paths=recovery_paths,
        job_id=jid,
        video_id=jid,
    )
    if not edl.decisions:
        result.error = "empty_edl"
        result.gates["TechnicalRenderQA"] = "FAIL"
        result.edl_path = _write_json(
            media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_EDL_{jid}.json", edl.to_dict()
        )
        return result

    if provenance_by_asset is None:
        provenance_by_asset = (director_plan.diagnostics or {}).get("selected_provenance") or {}
    attribution = build_attribution_manifest(edl, provenance_by_asset=provenance_by_asset)
    result.gates["LicenseProvenanceGate"] = _license_gate(attribution)
    rendered_beats = {decision.beat_id for decision in edl.decisions}
    uncovered = [
        beat.beat_id for beat in beats
        if beat.importance == "important"
        and (beat.beat_id not in rendered_beats or getattr(cov_by_beat.get(beat.beat_id), "status", "UNCOVERED") != "COVERED")
    ]
    result.metrics["uncovered_important_beats"] = uncovered
    result.gates["VisualCoverageGate"] = "PASS" if not uncovered and len(rendered_beats) == len(beats) else "REVIEW_REQUIRED"
    if result.gates["LicenseProvenanceGate"] == "FAIL":
        result.error = "restricted_license"
        result.edl_path = _write_json(media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_EDL_{jid}.json", edl.to_dict())
        result.attribution_path = _write_json(media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_ATTRIBUTION_{jid}.json", attribution)
        return result

    try:
        manifest = render_from_edl(
            edl,
            audio_path=audio_path,
            caption_path=caption_path,
            output_path=str(out_mp4),
            work_dir=str(work / "ffmpeg"),
            bgm_path=bgm_path,
            bgm_volume=bgm_volume,
            duck_bgm=True,
            loudnorm=True,
        )
    except Exception as exc:
        result.error = f"render_failed:{exc}"[:500]
        result.gates["TechnicalRenderQA"] = "FAIL"
        result.edl_path = _write_json(
            media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_EDL_{jid}.json", edl.to_dict()
        )
        return result

    result.output_mp4 = str(out_mp4)
    manifest_dict = manifest.to_dict()
    tqa = technical_qa(str(out_mp4), expected_duration=narration_dur)
    result.gates["TechnicalRenderQA"] = "PASS" if tqa.ok else "FAIL"
    result.metrics["technical_qa"] = tqa.to_dict()
    if not tqa.ok:
        result.error = f"technical_qa_failed:{tqa.reasons}"
    metrics = edl_metrics(edl)
    result.metrics.update(metrics)
    result.metrics["duration"] = tqa.duration_sec
    result.metrics["beat_count"] = len(beats)
    result.metrics["generic_filler"] = int(
        (director_plan.diagnostics or {}).get("generic_filler_selected") or 0
    )

    critique: FinalVideoCritique | None = None
    repairs: list[dict] = []
    if run_critic and tqa.ok and config.FINAL_CRITIC_ENABLED:
        critic = FinalVideoCritic(transport="direct_groq")
        critique = critic.critique(
            str(out_mp4),
            plan=director_plan,
            edl=edl,
            story_text=script,
            work_dir=work / "critic_frames",
            max_frames=max(1, min(critic_frame_budget, 3)),
        )
        result.critique = critique.to_dict()
        result.gates["FinalVideoQualityGate"] = critique.decision

        if (
            run_repair
            and critique.decision in {"FAIL", "REVIEW_REQUIRED"}
            and any(f.severity == "HIGH" for f in critique.findings)
        ):
            repairer = TargetedBeatRepair(max_repairs_per_beat=config.MAX_REPAIRS_PER_BEAT)
            actions = repairer.plan_repairs(critique.findings)
            passes = 0
            for action in actions:
                if passes >= config.MAX_FINAL_REPAIR_PASSES:
                    break
                req = next(
                    (s for s in director_plan.shot_requirements or [] if s.beat_id == action.beat_id),
                    ShotRequirement(
                        shot_requirement_id=f"sr:repair:{action.beat_id}",
                        beat_id=action.beat_id,
                        visual_purpose="EXPLAIN_RELATIONSHIP",
                        semantic_domain=next((b.semantic_domain for b in beats if b.beat_id == action.beat_id), "unknown"),
                        claim_ids=next((list(b.claim_ids) for b in beats if b.beat_id == action.beat_id), []),
                        importance="important",
                    ),
                )
                # Capture original asset from EDL
                for d in edl.decisions:
                    if d.beat_id == action.beat_id:
                        action.original_asset = d.local_path
                        break
                action = repairer.apply_recovery_repair(
                    action,
                    req,
                    claims=claims,
                    relationship_edges=relationship_edges,
                    output_dir=str(work),
                    job_id=jid,
                )
                repairs.append(action.to_dict())
                if action.applied and action.new_asset:
                    edl = repairer.patch_edl_asset(
                        edl, beat_id=action.beat_id, new_path=action.new_asset
                    )
                    passes += 1
            if passes:
                out2 = media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_REAL_{jid}_repaired.mp4"
                manifest = render_from_edl(
                    edl,
                    audio_path=audio_path,
                    caption_path=caption_path,
                    output_path=str(out2),
                    work_dir=str(work / "ffmpeg_r"),
                    bgm_path=bgm_path,
                )
                manifest_dict = manifest.to_dict()
                result.output_mp4 = str(out2)
                critique = critic.critique(
                    str(out2),
                    plan=director_plan,
                    edl=edl,
                    story_text=script,
                    work_dir=work / "critic_frames_r",
                    max_frames=max(1, min(critic_frame_budget, 3)),
                )
                result.critique = critique.to_dict()
                result.gates["FinalVideoQualityGate"] = critique.decision

    result.repairs = repairs
    result.gates.setdefault("NoSlideshowQualityGate", no_slideshow_gate(metrics, edl))
    attribution = build_attribution_manifest(edl, provenance_by_asset=provenance_by_asset)
    result.gates["LicenseProvenanceGate"] = _license_gate(attribution)
    result.edl_path = _write_json(media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_EDL_{jid}.json", edl.to_dict())
    result.manifest_path = _write_json(
        media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_MANIFEST_{jid}.json", manifest_dict
    )
    result.attribution_path = _write_json(
        media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_ATTRIBUTION_{jid}.json", attribution
    )
    crit = result.critique or {}
    findings = crit.get("findings") or []
    result.metrics["critic"] = {
        "decision": crit.get("decision"),
        "high": sum(1 for f in findings if f.get("severity") == "HIGH"),
        "medium": sum(1 for f in findings if f.get("severity") == "MEDIUM"),
        "low": sum(1 for f in findings if f.get("severity") == "LOW"),
        "vlm_calls": crit.get("vlm_calls"),
        "latency_ms": crit.get("latency_ms"),
        "estimated_cost_usd": crit.get("estimated_cost_usd"),
        "repaired": sum(1 for r in repairs if r.get("applied")),
        "unresolved_high": sum(
            1
            for f in findings
            if f.get("severity") == "HIGH"
            and not any(
                r.get("applied") and r.get("beat_id") == f.get("beat_id") for r in repairs
            )
        ),
    }
    trace = {
        "job_id": jid,
        "topic": topic,
        "script": script,
        "beats": [b.to_dict() for b in beats],
        "shot_requirements": [s.to_dict() for s in (director_plan.shot_requirements or [])],
        "selections": [s.to_dict() for s in (director_plan.selections or [])],
        "director_diagnostics": director_plan.diagnostics,
        "coverage": [c.to_dict() for c in (director_plan.coverage or [])],
        "edl_metrics": metrics,
        "gates": result.gates,
        "critique": result.critique,
        "repairs": repairs,
        "elapsed_ms": (time.perf_counter() - t0) * 1000,
        "publish": False,
        "documentary_engine_v2_default": False,
    }
    result.trace_path = _write_json(media / f"DOCUMENTARY_ENGINE_V2_STAGE_F_TRACE_{jid}.json", trace)
    result.metrics["elapsed_ms"] = trace["elapsed_ms"]
    return result
