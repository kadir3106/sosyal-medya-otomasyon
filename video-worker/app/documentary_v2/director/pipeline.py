"""Stage D director pipeline — StoryBeat → selection → coverage → recovery.

Isolated: not wired into /generate. No render. No publish.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.documentary_v2.director.coverage import compute_coverage
from app.documentary_v2.director.query_compiler import compile_search_intents
from app.documentary_v2.director.ranker import RankerContext, rank_candidates, source_key
from app.documentary_v2.director.recovery import BeatRecoveryEngine, diagnose_failure
from app.documentary_v2.director.shot_director import DocumentaryShotDirector
from app.documentary_v2.director.viu import build_viu, is_new_viu
from app.documentary_v2.providers.acquisition import acquire_candidates
from app.documentary_v2.providers.materialize import MaterializeError, materialize_candidate
from app.documentary_v2.providers.registry import MediaProviderRegistry, default_registry
from app.documentary_v2.schemas import (
    DocumentaryDirectorPlan,
    GeneratedVisualPlan,
    MediaCandidate,
    MediaSearchRequest,
    MotionGraphicPlan,
    LicensePolicy,
    LicenseState,
    ShotRequirement,
    ShotSelection,
    StoryBeat,
    VerifiedStory,
    VisualVerification,
    VisualVerificationRequest,
)
from app.documentary_v2.verifier.prefilter import cheap_prefilter
from app.documentary_v2.verifier.service import verify_candidate


@dataclass
class FixtureCandidate:
    """Offline test injection: candidate + local media + fixture_tag for mock VLM."""

    candidate: MediaCandidate
    media_path: str
    fixture_tag: str = ""
    trusted_person_provenance: bool = False


@dataclass
class DirectorBudget:
    max_vlm_per_shot: int = 5
    max_recovery_attempts: int = 2
    max_search_intents_per_shot: int = 4
    max_total_searches: int = 12
    max_total_vlm: int = 12
    max_total_materializations: int = 12
    max_elapsed_sec: float = 180.0


def _vv_request(req: ShotRequirement, cand: MediaCandidate, *, fixture_tag: str = "", **extra) -> VisualVerificationRequest:
    return VisualVerificationRequest(
        verification_id=f"vv:{cand.candidate_id}",
        job_id=extra.get("job_id", ""),
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        candidate_id=cand.candidate_id,
        required_visual_concept=req.required_visual_concept,
        semantic_domain=req.semantic_domain,
        narrative_role=req.narrative_role,
        required_entities=list(req.required_entities),
        optional_entities=list(req.optional_entities),
        required_action=req.action if req.visual_purpose == "SHOW_PROCESS" else "",
        required_location=req.location,
        motion_requirement=req.motion_requirement,
        evidence_requirement="EVIDENCE"
        if req.evidence_role == "EVIDENCE_REQUIRED"
        else req.evidence_role,
        authenticity_requirement=req.authenticity_requirement,
        preferred_media_type=req.preferred_media_type,
        forbidden_visual_concepts=list(req.forbidden_visual_concepts),
        strict_entity_mode=req.strict_entity_mode,
        context_narration="",
        retrieval_context={
            "query": cand.query,
            "provider": cand.provenance.provider,
            "source_url": cand.provenance.source_url,
            "metadata_claims": [cand.query, cand.provenance.source_url],
            "fixture_tag": fixture_tag,
            "trusted_person_provenance": extra.get("trusted_person_provenance", False),
        },
    )


def run_director_plan(
    *,
    job_id: str,
    topic: str,
    story: VerifiedStory | None,
    beats: list[StoryBeat],
    registry: MediaProviderRegistry | None = None,
    verifier_provider: Any = None,
    fixtures: dict[str, list[FixtureCandidate]] | None = None,
    live_acquire: bool = False,
    materialize: bool = False,
    budget: DirectorBudget | None = None,
    work_dir: Path | str | None = None,
) -> DocumentaryDirectorPlan:
    """
    Full Stage D flow.

    fixtures: beat_id → candidates (offline / dry-run without network)
    live_acquire: if True and no fixtures, call Stage B providers
    materialize: if True with live_acquire+work_dir, download candidates before VLM
                 (required for Stage F real assembly; Stage D dry-run keeps False)
    """
    budget = budget or DirectorBudget()
    started = time.monotonic()
    director = DocumentaryShotDirector()
    recovery_engine = BeatRecoveryEngine(max_attempts=budget.max_recovery_attempts)
    reg = registry or default_registry()
    ctx = RankerContext()
    seen_viu: set[str] = set()
    reuse_counts: dict[str, int] = {}
    asset_paths: dict[str, str] = {}
    work = Path(work_dir) if work_dir else None
    if materialize and work is not None:
        work.mkdir(parents=True, exist_ok=True)

    plan = DocumentaryDirectorPlan(
        plan_id=f"plan:{job_id or uuid.uuid4().hex[:10]}",
        job_id=job_id,
        video_id=job_id,
        topic=topic,
        story=story.to_dict() if story else None,
        beats=list(beats),
    )

    shot_reqs = director.plan_shots(story, beats)
    plan.shot_requirements = shot_reqs

    diagnostics = {
        "vlm_calls": 0,
        "search_calls": 0,
        "materialize_attempts": 0,
        "budget_stop_reason": "",
        "selected_provenance": {},
        "prefilter_rejects": 0,
        "materialize_ok": 0,
        "materialize_fail": 0,
        "accept": 0,
        "reject": 0,
        "uncertain": 0,
        "generic_filler_selected": 0,
        "river_selected": False,
        "bakery_selected": False,
        "remote_vlm_validated": False,
        "asset_paths": asset_paths,
    }

    def budget_exhausted(kind: str) -> bool:
        reason = ""
        if time.monotonic() - started >= budget.max_elapsed_sec:
            reason = "elapsed"
        elif kind == "search" and diagnostics["search_calls"] >= budget.max_total_searches:
            reason = "total_searches"
        elif kind == "vlm" and diagnostics["vlm_calls"] >= budget.max_total_vlm:
            reason = "total_vlm"
        elif kind == "materialize" and diagnostics["materialize_attempts"] >= budget.max_total_materializations:
            reason = "total_materializations"
        if reason and not diagnostics["budget_stop_reason"]:
            diagnostics["budget_stop_reason"] = reason
        return bool(reason)

    for req in shot_reqs:
        intents = compile_search_intents(req)[: budget.max_search_intents_per_shot]
        plan.search_intents.extend(intents)

        pool: list[FixtureCandidate | tuple[MediaCandidate, str, str]] = []
        acq_summary: dict[str, Any] = {
            "beat_id": req.beat_id,
            "shot_requirement_id": req.shot_requirement_id,
            "intents": [i.to_dict() for i in intents],
            "candidates": 0,
            "providers": [],
        }

        if fixtures and req.beat_id in fixtures:
            pool = list(fixtures[req.beat_id])
            acq_summary["candidates"] = len(pool)
            acq_summary["mode"] = "fixture"
        elif live_acquire:
            for intent in intents:
                if budget_exhausted("search"):
                    break
                diagnostics["search_calls"] += 1
                mreq = MediaSearchRequest(
                    query=intent.query,
                    query_family=intent.query_family,
                    target_entities=list(intent.target_entities),
                    target_concept=intent.target_concept,
                    semantic_domain=intent.semantic_domain or req.semantic_domain,
                    preferred_media_types=list(intent.preferred_media_types),
                    archive_preference=intent.archive_preference,
                    result_limit=budget.max_vlm_per_shot,
                    job_id=job_id,
                    beat_id=req.beat_id,
                    shot_requirement_id=req.shot_requirement_id,
                )
                result = acquire_candidates(mreq, registry=reg, fetch_previews=True)
                acq_summary["providers"].extend(
                    [e.provider for e in result.events]
                )
                for c in result.unique_candidates:
                    # Lazy materialize at verify time — avoid downloading entire search pools
                    pool.append((c, "", intent.query_family))
            acq_summary["candidates"] = len(pool)
            acq_summary["mode"] = "live_materialize" if materialize else "live"
        else:
            acq_summary["mode"] = "empty"
            acq_summary["candidates"] = 0

        plan.acquisition_summaries.append(acq_summary)

        # Prefer video candidates when shot asks for motion / stock_video
        prefer_video = any(
            t in {"stock_video", "archive_video", "video"}
            for t in (req.preferred_media_types or [])
        ) or (req.motion_requirement or "").upper() in {"REQUIRED", "PREFERRED"}

        def _pool_sort_key(item) -> tuple:
            if isinstance(item, FixtureCandidate):
                cand = item.candidate
                path = (item.media_path or "").lower()
                url = (cand.download_url or cand.preview_url or "").lower()
            else:
                cand = item[0]
                path = ""
                url = (cand.download_url or cand.preview_url or "").lower()
            provider = (cand.provenance.provider or "").lower()
            is_vid = any(ext in path or ext in url for ext in (".mp4", ".webm", ".mov", "/video"))
            # Prefer stock (pexels/pixabay/mixkit) over internet_archive dumps
            prov_rank = 0 if provider in {"pexels", "pixabay", "mixkit"} else (1 if provider == "wikimedia" else 2)
            if prefer_video:
                return (0 if is_vid else 1, prov_rank, url)
            return (0 if not is_vid else 1, prov_rank, url)

        pool = sorted(pool, key=_pool_sort_key)

        pairs: list[tuple[MediaCandidate, VisualVerification]] = []
        verified = 0
        for item in pool:
            if budget_exhausted("vlm"):
                break
            if isinstance(item, FixtureCandidate):
                cand, media_path, tag = item.candidate, item.media_path, item.fixture_tag
                trusted = item.trusted_person_provenance
                if media_path:
                    asset_paths[cand.candidate_id] = media_path
            else:
                cand, media_path, tag = item[0], item[1], ""
                trusted = False

            if (
                cand.provenance.license_policy == LicensePolicy.KNOWN_RESTRICTED.value
                or cand.provenance.license in {LicenseState.RESTRICTED.value, LicenseState.PROPRIETARY.value}
            ):
                diagnostics.setdefault("restricted_rejects", 0)
                diagnostics["restricted_rejects"] += 1
                continue

            cand.shot_requirement_id = req.shot_requirement_id
            vv_req = _vv_request(
                req, cand, fixture_tag=tag, job_id=job_id, trusted_person_provenance=trusted
            )
            pf = cheap_prefilter(cand, vv_req)
            if not pf.accepted:
                diagnostics["prefilter_rejects"] += 1
                continue
            if verified >= budget.max_vlm_per_shot:
                break
            if not media_path and materialize and work is not None:
                if budget_exhausted("materialize"):
                    break
                # Prefer shorter stock over multi-minute archive dumps for Stage F speed
                provider = (cand.provenance.provider or "").lower()
                url = (cand.download_url or "").lower()
                if provider == "internet_archive" and prefer_video:
                    # Defer IA until stock exhausted — skip when we still have unused stock slots
                    if verified < budget.max_vlm_per_shot - 1:
                        continue
                try:
                    diagnostics["materialize_attempts"] += 1
                    asset = materialize_candidate(cand, job_dir=work)
                    media_path = asset.local_path
                    # Skip multi-minute dumps for VLM (keep file but don't verify now)
                    try:
                        from app.documentary_v2.verifier.sampler import _ffprobe_duration

                        dur = _ffprobe_duration(Path(media_path)) or 0.0
                        if dur > 90.0 and prefer_video:
                            diagnostics["materialize_ok"] += 1
                            diagnostics.setdefault("skipped_long_video", 0)
                            diagnostics["skipped_long_video"] += 1
                            asset_paths[cand.candidate_id] = media_path
                            media_path = ""
                            continue
                    except Exception:
                        pass
                    asset_paths[cand.candidate_id] = media_path
                    if asset.asset_id:
                        asset_paths[asset.asset_id] = media_path
                    diagnostics["materialize_ok"] += 1
                except (MaterializeError, Exception):
                    diagnostics["materialize_fail"] += 1
                    media_path = ""
            if not media_path:
                # Live path without materialize in Stage D dry-run: skip VLM
                continue
            if budget_exhausted("vlm"):
                break
            diagnostics["vlm_calls"] += 1
            ver = verify_candidate(
                vv_req,
                media_path=media_path,
                provider=verifier_provider,
                work_dir=work_dir,
                use_cache=False if work_dir is None else True,
            )
            verified += 1
            d = (ver.decision or "").upper()
            if d == "ACCEPT":
                diagnostics["accept"] += 1
            elif d == "REJECT":
                diagnostics["reject"] += 1
            else:
                diagnostics["uncertain"] += 1
            plan.verifications.append(ver.to_dict())
            pairs.append((cand, ver))

        ranked = rank_candidates(req, pairs, ctx)
        plan.ranked.extend(ranked)

        selection: ShotSelection | None = None
        chosen_ver: VisualVerification | None = None
        chosen_cand: MediaCandidate | None = None
        why_lost: list[str] = []

        eligible = [r for r in ranked if r.eligible]
        for r in ranked:
            if not r.eligible:
                why_lost.append(
                    f"{r.candidate_id}: hard_fail={r.hard_fail_reasons} decision={r.decision}"
                )

        if eligible:
            top = eligible[0]
            for cand, ver in pairs:
                if cand.candidate_id == top.candidate_id:
                    chosen_cand, chosen_ver = cand, ver
                    break
            if chosen_cand and chosen_ver:
                sk = source_key(chosen_cand)
                reuse_counts[sk] = reuse_counts.get(sk, 0) + 1
                viu = build_viu(
                    beat_id=req.beat_id,
                    candidate=chosen_cand,
                    req=req,
                    verification=chosen_ver,
                )
                new_viu = is_new_viu(viu, seen_viu)
                seen_viu.add(viu.visual_information_id.replace("viu:", ""))
                plan.visual_information_units.append(viu)
                ctx.used_source_keys.add(sk)

                # Detect forbidden filler selections (diagnostics)
                blob = " ".join(
                    chosen_ver.visible_objects
                    + [chosen_ver.dominant_visual_concept, chosen_ver.visible_setting]
                ).lower()
                if "river" in blob:
                    diagnostics["river_selected"] = True
                if "bakery" in blob or "bread" in blob:
                    diagnostics["bakery_selected"] = True
                if chosen_ver.genericness == "HIGH" and chosen_ver.evidence_value in {
                    "GENERIC_CONTEXT",
                    "UNRELATED",
                }:
                    diagnostics["generic_filler_selected"] += 1

                selection = ShotSelection(
                    shot_id=f"shot:{req.beat_id}:0",
                    beat_id=req.beat_id,
                    asset_id=viu.asset_id,
                    candidate_id=chosen_cand.candidate_id,
                    visual_information_id=viu.visual_information_id,
                    shot_requirement_id=req.shot_requirement_id,
                    verification_id=chosen_ver.verification_id,
                    selection_reason="hard_pass+best_soft_score",
                    why_selected=(
                        f"purpose={req.visual_purpose}; entity={chosen_ver.entity_alignment}; "
                        f"concept={chosen_ver.concept_alignment}; evidence={chosen_ver.evidence_value}; "
                        f"novelty={'new' if new_viu else 'reuse_viu'}; score={top.soft_score:.3f}"
                    ),
                    why_alternatives_lost=why_lost[:8],
                    score_breakdown=dict(top.score_breakdown),
                    hard_requirements_satisfied=[
                        x
                        for x in [
                            "entity" if chosen_ver.entity_alignment in {"STRONG", "EXACT", "PARTIAL"} else "",
                            "concept" if chosen_ver.concept_alignment in {"STRONG", "EXACT", "PARTIAL"} else "",
                            "motion" if req.motion_requirement != "REQUIRED" or chosen_ver.motion_value not in {"STATIC_VIDEO"} else "",
                        ]
                        if x
                    ],
                    source_novelty=top.score_breakdown.get("source_novelty"),
                    reuse_count=reuse_counts[sk],
                    visual_purpose=req.visual_purpose,
                    start_time=None,
                    end_time=None,
                )
                plan.selections.append(selection)
                provenance = chosen_cand.provenance.to_dict()
                diagnostics["selected_provenance"][selection.asset_id] = provenance
                diagnostics["selected_provenance"][selection.candidate_id] = provenance
                # Ensure EDL can resolve selected media
                sel_path = asset_paths.get(chosen_cand.candidate_id) or asset_paths.get(viu.asset_id)
                if sel_path:
                    asset_paths[viu.asset_id] = sel_path
                    asset_paths[f"beat:{req.beat_id}"] = sel_path
                    asset_paths[req.beat_id] = sel_path

        failure = ""
        if not selection:
            failure = diagnose_failure(
                candidate_count=acq_summary["candidates"],
                verifications=[v for v in plan.verifications if v.get("beat_id") == req.beat_id][-5:],
                prefilter_rejects=0,
            )
            cov = compute_coverage(req, None, chosen_ver, failure_reason=failure)
            # Recovery for important / uncovered
            if req.importance == "important" or cov.status == "UNCOVERED":
                attempt = recovery_engine.recover(
                    req,
                    failure_reason=failure,
                    claim_ids=list((story.claim_ids if story else []) or []),
                    attempt_index=0,
                )
                plan.recovery_attempts.append(attempt.to_dict())
                cov.recovery_attempts.append(attempt.to_dict())
                if attempt.motion_graphic_plan:
                    plan.motion_graphic_plans.append(attempt.motion_graphic_plan)
                    # Evidence placeholder → PARTIAL coverage conceptually
                    cov.status = "PARTIAL"
                    cov.failure_reason = failure
                    cov.missing_requirements = ["real_media"]
                if attempt.generated_visual_plan:
                    # Ensure evidence_prohibited
                    g = attempt.generated_visual_plan
                    plan.generated_visual_plans.append(g)
                    cov.status = "PARTIAL"
                if attempt.review_required and not attempt.motion_graphic_plan:
                    cov.status = "UNCOVERED"
            plan.coverage.append(cov)
        else:
            cov = compute_coverage(req, selection, chosen_ver, failure_reason="")
            # Duplicate reuse of one product clip across many important concepts → expose missing
            if (
                selection.reuse_count > 1
                and req.importance == "important"
                and req.visual_purpose
                not in {
                    "SHOW_PRODUCT",
                    "IDENTIFY_ENTITY",
                }
            ):
                # Same asset reused for non-product important beat → partial if VIU not new purpose
                if selection.source_novelty is not None and selection.source_novelty < 0.5:
                    cov.status = "PARTIAL"
                    cov.missing_requirements.append("distinct_visual_information")
                    cov.failure_reason = "SOURCE_REUSE_WITHOUT_NEW_VIU"
            plan.coverage.append(cov)

    # Coverage totals
    covered = sum(1 for c in plan.coverage if c.status == "COVERED")
    partial = sum(1 for c in plan.coverage if c.status == "PARTIAL")
    uncovered = sum(1 for c in plan.coverage if c.status == "UNCOVERED")
    diagnostics.update(
        {
            "shot_requirements": len(plan.shot_requirements),
            "selected_shots": len(plan.selections),
            "unique_source_assets": len(ctx.used_source_keys),
            "unique_vius": len({v.visual_information_id for v in plan.visual_information_units}),
            "covered_beats": covered,
            "partial_beats": partial,
            "uncovered_beats": uncovered,
            "recovery_attempts": len(plan.recovery_attempts),
            "motion_graphic_plans": len(plan.motion_graphic_plans),
            "generated_visual_plans": len(plan.generated_visual_plans),
        }
    )
    plan.diagnostics = diagnostics
    return plan
