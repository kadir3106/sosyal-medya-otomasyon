"""VisualRecoveryEngine — orchestrate strategy → plan → render/generate → re-verify."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.documentary_v2.recovery.budgets import RecoveryBudget
from app.documentary_v2.recovery.generation_base import GeneratedVideoProvider, GenerationResult
from app.documentary_v2.recovery.generation_fal import build_generated_video_provider
from app.documentary_v2.recovery.motion_plans import (
    MotionGraphicPlanError,
    build_evidence_card_plan,
    build_map_plan,
    build_relationship_graph_plan,
    build_timeline_plan,
)
from app.documentary_v2.recovery.planner import RecoveryDecision, choose_recovery_strategy
from app.documentary_v2.recovery.prompt_compiler import compile_generated_visual_plan
from app.documentary_v2.recovery.renderer import MotionGraphicRenderer, MotionGraphicRenderResult
from app.documentary_v2.recovery.types import RecoveryStrategy
from app.documentary_v2.schemas import (
    GeneratedVisualPlan,
    MotionGraphicPlan,
    RecoveryTelemetryEvent,
    ShotRequirement,
    VerifiedClaim,
    VerifiedStory,
    VisualVerification,
    VisualVerificationRequest,
)


@dataclass
class RecoveryResult:
    strategy: RecoveryStrategy
    reason: str
    review_required: bool = False
    motion_graphic_plan: MotionGraphicPlan | None = None
    generated_visual_plan: GeneratedVisualPlan | None = None
    render: MotionGraphicRenderResult | None = None
    generation: GenerationResult | None = None
    verification: VisualVerification | None = None
    selected: bool = False
    artifact_path: str = ""
    telemetry: RecoveryTelemetryEvent | None = None
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "strategy": self.strategy.value,
            "reason": self.reason,
            "review_required": self.review_required,
            "motion_graphic_plan": self.motion_graphic_plan.to_dict()
            if self.motion_graphic_plan
            else None,
            "generated_visual_plan": self.generated_visual_plan.to_dict()
            if self.generated_visual_plan
            else None,
            "render": {
                "ok": self.render.ok,
                "path": self.render.path,
                "error": self.render.error,
                "provenance": self.render.provenance,
            }
            if self.render
            else None,
            "generation": self.generation.to_dict() if self.generation else None,
            "verification": self.verification.to_dict() if self.verification else None,
            "selected": self.selected,
            "artifact_path": self.artifact_path,
            "telemetry": self.telemetry.to_dict() if self.telemetry else None,
            "details": dict(self.details),
        }


class VisualRecoveryEngine:
    """High-quality recovery — never random B-roll / luxury filler."""

    def __init__(
        self,
        *,
        budget: RecoveryBudget | None = None,
        renderer: MotionGraphicRenderer | None = None,
        generator: GeneratedVideoProvider | None = None,
        verify_fn: Callable[..., VisualVerification] | None = None,
    ) -> None:
        self.budget = budget or RecoveryBudget.from_config()
        self.renderer = renderer or MotionGraphicRenderer()
        self.generator = generator or build_generated_video_provider()
        self.verify_fn = verify_fn

    def recover(
        self,
        req: ShotRequirement,
        *,
        failure_reason: str,
        claims: list[VerifiedClaim] | None = None,
        story: VerifiedStory | None = None,
        relationship_edges: list[dict] | None = None,
        timeline_events: list[dict] | None = None,
        document_asset_id: str = "",
        has_archive_portrait: bool = False,
        has_strong_real_video: bool = False,
        output_dir: str | Path = "",
        job_id: str = "",
        render: bool = True,
        generate: bool = True,
    ) -> RecoveryResult:
        t0 = time.perf_counter()
        claims = claims or []
        decision = choose_recovery_strategy(
            req,
            failure_reason=failure_reason,
            claims=claims,
            has_document_asset=bool(document_asset_id),
            has_archive_portrait=has_archive_portrait,
            has_strong_real_video=has_strong_real_video,
        )

        if decision.strategy == RecoveryStrategy.REAL_MEDIA:
            return self._finish(
                RecoveryResult(
                    strategy=decision.strategy,
                    reason=decision.reason,
                    details={"action": "prefer_real_media_requery"},
                ),
                req,
                failure_reason,
                t0,
                job_id,
            )

        if decision.strategy in {
            RecoveryStrategy.ARCHIVE_MEDIA,
            RecoveryStrategy.ARCHIVAL_STILL,
        }:
            return self._finish(
                RecoveryResult(
                    strategy=decision.strategy,
                    reason=decision.reason,
                    details={"action": "archive_requery", "prefer_archive": True},
                ),
                req,
                failure_reason,
                t0,
                job_id,
            )

        if decision.strategy == RecoveryStrategy.UNCOVERED:
            return self._finish(
                RecoveryResult(
                    strategy=decision.strategy,
                    reason=decision.reason,
                    review_required=True,
                ),
                req,
                failure_reason,
                t0,
                job_id,
            )

        out = Path(output_dir or ".")
        result = RecoveryResult(strategy=decision.strategy, reason=decision.reason)

        if decision.strategy in {
            RecoveryStrategy.MOTION_GRAPHIC,
            RecoveryStrategy.DOCUMENT_EVIDENCE,
        }:
            try:
                plan = self._build_motion_plan(
                    req,
                    decision,
                    claims=claims,
                    relationship_edges=relationship_edges,
                    timeline_events=timeline_events,
                    document_asset_id=document_asset_id,
                )
            except MotionGraphicPlanError as exc:
                return self._finish(
                    RecoveryResult(
                        strategy=RecoveryStrategy.UNCOVERED,
                        reason=f"motion_plan_rejected:{exc}",
                        review_required=True,
                    ),
                    req,
                    failure_reason,
                    t0,
                    job_id,
                )
            result.motion_graphic_plan = plan
            if render and self.budget.can_render_motion():
                rr = self.renderer.render(plan, output_dir=out, job_id=job_id)
                result.render = rr
                self.budget.record_motion()
                if rr.ok:
                    result.artifact_path = rr.path
                    vv = self._reverify(req, rr.path, synthetic_explanatory=True)
                    result.verification = vv
                    if vv and vv.decision == "ACCEPT":
                        result.selected = True
                    elif vv and vv.decision == "REJECT":
                        result.selected = False
                        result.details["reject"] = "verification_rejected"
                    else:
                        # Explanatory graphics: structural verification primary;
                        # VLM UNCERTAIN does not auto-select as evidence footage
                        result.selected = bool(rr.ok and plan.verified and plan.explanatory_only)
                        if result.selected and vv:
                            result.details["selection_mode"] = "structural_explanatory"
                else:
                    result.review_required = True
                    result.details["render_error"] = rr.error
            elif render and not self.budget.can_render_motion():
                result.review_required = True
                result.details["budget"] = "max_motion_graphic_renders"
            return self._finish(result, req, failure_reason, t0, job_id, plan_ids=True)

        if decision.strategy in {
            RecoveryStrategy.SYNTHETIC_VIDEO,
            RecoveryStrategy.SYNTHETIC_IMAGE,
        }:
            gen_plan = compile_generated_visual_plan(
                req,
                story=story,
                justification=decision.reason,
                cost_ceiling_usd=self.budget.max_generation_cost_per_beat,
            )
            if gen_plan is None:
                return self._finish(
                    RecoveryResult(
                        strategy=RecoveryStrategy.UNCOVERED,
                        reason="synthetic_blocked_by_policy",
                        review_required=True,
                    ),
                    req,
                    failure_reason,
                    t0,
                    job_id,
                )
            est = self.generator.estimate_cost(gen_plan)
            gen_plan.estimated_cost_usd = est
            result.generated_visual_plan = gen_plan
            ok_budget, why = self.budget.can_generate(beat_id=req.beat_id, estimated_cost=est)
            if not generate:
                result.details["generation_skipped"] = "generate_flag_false"
                return self._finish(result, req, failure_reason, t0, job_id, plan_ids=True)
            if not ok_budget:
                result.review_required = True
                result.details["budget"] = why
                return self._finish(result, req, failure_reason, t0, job_id, plan_ids=True)

            gen_dir = out / "jobs" / job_id / "recovery" / "generated" if job_id else out / "recovery" / "generated"
            gr = self.generator.generate(gen_plan, output_dir=str(gen_dir))
            result.generation = gr
            self.budget.record_generation(beat_id=req.beat_id, cost=float(gr.actual_cost_usd or est or 0))
            if not gr.ok:
                result.review_required = True
                result.details["generation_error"] = gr.error
                return self._finish(result, req, failure_reason, t0, job_id, plan_ids=True)

            result.artifact_path = gr.local_path
            vv = self._reverify(req, gr.local_path, synthetic_explanatory=True)
            result.verification = vv
            # Generated media MUST pass VisualVerifier to be selected
            if vv and vv.decision == "ACCEPT":
                result.selected = True
            else:
                result.selected = False
                result.details["reject"] = "generated_failed_visual_verifier"
            return self._finish(result, req, failure_reason, t0, job_id, plan_ids=True)

        return self._finish(
            RecoveryResult(
                strategy=RecoveryStrategy.UNCOVERED,
                reason="unhandled_strategy",
                review_required=True,
            ),
            req,
            failure_reason,
            t0,
            job_id,
        )

    def _build_motion_plan(
        self,
        req: ShotRequirement,
        decision: RecoveryDecision,
        *,
        claims: list[VerifiedClaim],
        relationship_edges: list[dict] | None,
        timeline_events: list[dict] | None,
        document_asset_id: str,
    ) -> MotionGraphicPlan:
        prim = decision.primitive or "EvidenceCard"
        if prim == "RelationshipGraph":
            edges = relationship_edges or []
            if not edges and claims:
                # Derive a minimal edge from first supported ownership-like claim if entities exist
                ents = list(req.required_entities) or [req.subject or "Entity"]
                c0 = next(
                    (c for c in claims if (c.status or "").lower() in {"supported", "partial"}),
                    None,
                )
                if c0 and len(ents) >= 1:
                    edges = [
                        {
                            "from": ents[0],
                            "to": ents[1] if len(ents) > 1 else "Foundation/Trust",
                            "label": "related_to",
                            "claim_id": c0.claim_id,
                            "evidence_id": f"{c0.claim_id}:ev0",
                        }
                    ]
            return build_relationship_graph_plan(req, edges=edges, claims=claims)
        if prim == "Timeline":
            return build_timeline_plan(req, events=timeline_events or [], claims=claims)
        if prim == "MapHighlight":
            return build_map_plan(req, location=req.location or "")
        if prim == "DocumentHighlight":
            from app.documentary_v2.recovery.motion_plans import build_document_highlight_plan

            cids = [c.claim_id for c in claims if (c.status or "").lower() in {"supported", "partial"}]
            return build_document_highlight_plan(
                req,
                document_asset_id=document_asset_id,
                claim_ids=cids[:1] or list(req.claim_ids or []),
                evidence_ids=[f"{cids[0]}:ev0"] if cids else ["ev0"],
            )
        return build_evidence_card_plan(req, claims=claims)

    def _reverify(
        self,
        req: ShotRequirement,
        media_path: str,
        *,
        synthetic_explanatory: bool,
    ) -> VisualVerification | None:
        if not media_path or not Path(media_path).is_file():
            return None
        if self.verify_fn is None:
            # Structural pass for explanatory graphics when no verifier injected
            from app.documentary_v2.schemas import VisualVerification

            return VisualVerification(
                verification_id=f"vv:recovery:{req.beat_id}",
                candidate_id=f"recovery:{req.beat_id}",
                decision="ACCEPT" if synthetic_explanatory else "UNCERTAIN",
                status="ACCEPT" if synthetic_explanatory else "UNCERTAIN",
                reason_codes=["EVIDENCE_VISUAL"] if synthetic_explanatory else ["VLM_UNAVAILABLE"],
                explanation_short="structural_explanatory_recovery"
                if synthetic_explanatory
                else "no_verifier_injected",
                verifier_provider="recovery_structural",
                details={"synthetic_explanatory": synthetic_explanatory},
            )
        vv_req = VisualVerificationRequest(
            verification_id=f"vv:recovery:{req.beat_id}",
            beat_id=req.beat_id,
            shot_id=f"shot:{req.beat_id}",
            candidate_id=f"recovery:{req.beat_id}",
            required_visual_concept=req.required_visual_concept,
            semantic_domain=req.semantic_domain,
            narrative_role=req.narrative_role,
            required_entities=list(req.required_entities),
            evidence_requirement="ILLUSTRATION"
            if synthetic_explanatory
            else req.evidence_role,
            forbidden_visual_concepts=list(req.forbidden_visual_concepts),
            strict_entity_mode=False if synthetic_explanatory else req.strict_entity_mode,
            retrieval_context={"recovery": True, "synthetic_explanatory": synthetic_explanatory},
        )
        return self.verify_fn(vv_req, media_path=media_path)

    def _finish(
        self,
        result: RecoveryResult,
        req: ShotRequirement,
        failure_reason: str,
        t0: float,
        job_id: str,
        plan_ids: bool = False,
    ) -> RecoveryResult:
        latency = (time.perf_counter() - t0) * 1000
        result.telemetry = RecoveryTelemetryEvent(
            beat_id=req.beat_id,
            shot_id=f"shot:{req.beat_id}",
            job_id=job_id,
            recovery_strategy=result.strategy.value,
            original_failure_reason=failure_reason,
            motion_graphic_plan_id=result.motion_graphic_plan.plan_id
            if result.motion_graphic_plan
            else "",
            generated_visual_plan_id=result.generated_visual_plan.plan_id
            if result.generated_visual_plan
            else "",
            provider=(
                (result.generation.provider if result.generation else "")
                or (result.render.renderer if result.render else "")
            ),
            estimated_cost_usd=(
                result.generated_visual_plan.estimated_cost_usd
                if result.generated_visual_plan
                else 0.0
            ),
            actual_cost_usd=(
                result.generation.actual_cost_usd if result.generation else 0.0
            ),
            latency_ms=latency,
            verification_decision=result.verification.decision if result.verification else "",
            selected=result.selected,
            claim_ids=list(
                (result.motion_graphic_plan.claim_ids if result.motion_graphic_plan else None)
                or (result.generated_visual_plan.claim_ids if result.generated_visual_plan else [])
                or req.claim_ids
                or []
            ),
            evidence_ids=list(
                result.motion_graphic_plan.evidence_ids if result.motion_graphic_plan else []
            ),
            artifact_path=result.artifact_path,
            synthetic_classification=(
                result.generated_visual_plan.synthetic_disclosure
                if result.generated_visual_plan
                else ("EXPLANATORY_GRAPHIC" if result.motion_graphic_plan else "")
            ),
            details=dict(result.details),
        )
        return result
