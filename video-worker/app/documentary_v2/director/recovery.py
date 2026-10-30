"""Beat recovery — failure-aware, no generic filler, no story drift.

Stage E: delegates semantic MOTION_GRAPHIC / SYNTHETIC decisions to VisualRecoveryEngine
when claims/context are provided. Still never fills with luxury B-roll.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.documentary_v2.schemas import (
    GeneratedVisualPlan,
    MotionGraphicPlan,
    SearchIntent,
    ShotRequirement,
    QueryFamily,
    VerifiedClaim,
)
from app.documentary_v2.director.query_compiler import compile_search_intents

FAILURE_CODES = (
    "NO_CANDIDATES",
    "ALL_DUPLICATES",
    "LOW_VISUAL_RELEVANCE",
    "WRONG_ENTITY",
    "WRONG_DOMAIN",
    "ACTION_NOT_VISIBLE",
    "LOCATION_NOT_SUPPORTED",
    "EVIDENCE_NOT_FOUND",
    "MOTION_NOT_FOUND",
    "LICENSE_BLOCKED",
    "PROVIDER_FAILURE",
    "VERIFIER_UNAVAILABLE",
    "ONLY_GENERIC_CONTEXT_FOUND",
    "ONLY_UNCERTAIN_CANDIDATES",
)


@dataclass
class RecoveryAttempt:
    beat_id: str
    failure_reason: str
    action: str
    details: dict = field(default_factory=dict)
    new_intents: list[SearchIntent] = field(default_factory=list)
    motion_graphic_plan: MotionGraphicPlan | None = None
    generated_visual_plan: GeneratedVisualPlan | None = None
    review_required: bool = False
    recovery_strategy: str = ""
    artifact_path: str = ""
    selected: bool = False

    def to_dict(self) -> dict:
        return {
            "beat_id": self.beat_id,
            "failure_reason": self.failure_reason,
            "action": self.action,
            "details": dict(self.details),
            "new_intents": [i.to_dict() for i in self.new_intents],
            "motion_graphic_plan": self.motion_graphic_plan.to_dict()
            if self.motion_graphic_plan
            else None,
            "generated_visual_plan": self.generated_visual_plan.to_dict()
            if self.generated_visual_plan
            else None,
            "review_required": self.review_required,
            "recovery_strategy": self.recovery_strategy,
            "artifact_path": self.artifact_path,
            "selected": self.selected,
        }


def diagnose_failure(
    *,
    candidate_count: int,
    verifications: list[dict],
    prefilter_rejects: int = 0,
    provider_failures: int = 0,
) -> str:
    if provider_failures and candidate_count == 0:
        return "PROVIDER_FAILURE"
    if candidate_count == 0:
        return "NO_CANDIDATES"
    decisions = [str(v.get("decision") or "").upper() for v in verifications]
    if any("VLM_UNAVAILABLE" in (v.get("reason_codes") or []) for v in verifications):
        return "VERIFIER_UNAVAILABLE"
    if decisions and all(d == "UNCERTAIN" for d in decisions):
        return "ONLY_UNCERTAIN_CANDIDATES"
    if decisions and all(d == "REJECT" for d in decisions):
        codes = []
        for v in verifications:
            codes.extend(v.get("reason_codes") or [])
        joined = " ".join(codes)
        if "ILLUSTRATIVE_ONLY" in joined or "EVIDENCE_REQUIRED" in joined:
            return "EVIDENCE_NOT_FOUND"
        if "MOTION_REQUIRED_BUT_STATIC" in joined:
            return "MOTION_NOT_FOUND"
        if "ENTITY_NOT_VISIBLE" in joined or "REQUIRED_ENTITY" in joined:
            return "WRONG_ENTITY"
        if "WRONG_DOMAIN" in joined or "CONCEPT_MISMATCH" in joined:
            return "WRONG_DOMAIN"
        if "GENERIC_BROLL" in joined:
            return "ONLY_GENERIC_CONTEXT_FOUND"
        return "LOW_VISUAL_RELEVANCE"
    if candidate_count > 0 and not verifications and prefilter_rejects >= candidate_count:
        return "ALL_DUPLICATES"
    return "LOW_VISUAL_RELEVANCE"


class BeatRecoveryEngine:
    """Bounded recovery. Never fills with unrelated prior assets or luxury filler."""

    def __init__(self, *, max_attempts: int = 3) -> None:
        self.max_attempts = max_attempts

    def recover(
        self,
        req: ShotRequirement,
        *,
        failure_reason: str,
        claim_ids: list[str] | None = None,
        attempt_index: int = 0,
        claims: list[VerifiedClaim] | None = None,
        relationship_edges: list[dict] | None = None,
        output_dir: str = "",
        job_id: str = "",
        execute_stage_e: bool = False,
    ) -> RecoveryAttempt:
        if attempt_index >= self.max_attempts:
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action="REVIEW_REQUIRED",
                review_required=True,
                recovery_strategy="UNCOVERED",
                details={"note": "recovery budget exhausted"},
            )

        domain = req.semantic_domain
        entity = (req.required_entities or [req.subject] or [""])[0]

        if failure_reason == "VERIFIER_UNAVAILABLE":
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action="DO_NOT_DOWNGRADE_TO_METADATA",
                review_required=True,
                recovery_strategy="UNCOVERED",
                details={"note": "pixels required; metadata cannot substitute"},
            )

        if execute_stage_e and failure_reason in {
            "EVIDENCE_NOT_FOUND",
            "ONLY_GENERIC_CONTEXT_FOUND",
            "NO_CANDIDATES",
            "MOTION_NOT_FOUND",
            "LOW_VISUAL_RELEVANCE",
        }:
            from app.documentary_v2.recovery.engine import VisualRecoveryEngine

            eng = VisualRecoveryEngine()
            rr = eng.recover(
                req,
                failure_reason=failure_reason,
                claims=claims or [],
                relationship_edges=relationship_edges,
                output_dir=output_dir or ".",
                job_id=job_id,
                render=bool(output_dir),
                generate=False,
            )
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action=f"STAGE_E:{rr.strategy.value}",
                motion_graphic_plan=rr.motion_graphic_plan,
                generated_visual_plan=rr.generated_visual_plan,
                review_required=rr.review_required,
                recovery_strategy=rr.strategy.value,
                artifact_path=rr.artifact_path,
                selected=rr.selected,
                details={
                    "preserved_domain": domain,
                    "stage_e": rr.to_dict(),
                    "claim_ids": claim_ids or [],
                },
            )

        if failure_reason == "WRONG_ENTITY":
            intents = [
                SearchIntent(
                    intent_id=f"recovery:{req.shot_requirement_id}:ENTITY_EXACT",
                    beat_id=req.beat_id,
                    shot_requirement_id=req.shot_requirement_id,
                    query=entity,
                    query_family=QueryFamily.ENTITY_EXACT.value,
                    semantic_domain=domain,
                    target_concept=req.required_visual_concept,
                    target_entities=list(req.required_entities),
                    preferred_media_types=list(req.preferred_media_types),
                    archive_preference=req.visual_purpose == "SHOW_PERSON",
                )
            ]
            if req.visual_purpose == "SHOW_PERSON":
                intents.append(
                    SearchIntent(
                        intent_id=f"recovery:{req.shot_requirement_id}:ARCHIVE",
                        beat_id=req.beat_id,
                        shot_requirement_id=req.shot_requirement_id,
                        query=f"{entity} archival portrait",
                        query_family=QueryFamily.ARCHIVE.value,
                        semantic_domain=domain,
                        target_entities=list(req.required_entities),
                        preferred_media_types=["archive_still"],
                        archive_preference=True,
                    )
                )
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action="ENTITY_SPECIFIC_REQUERY",
                new_intents=intents,
                recovery_strategy="ARCHIVE_MEDIA"
                if req.visual_purpose == "SHOW_PERSON"
                else "REAL_MEDIA",
                details={"preserved_domain": domain},
            )

        if failure_reason in {"EVIDENCE_NOT_FOUND", "ONLY_GENERIC_CONTEXT_FOUND"}:
            plan = MotionGraphicPlan(
                plan_id=f"mg:{req.beat_id}",
                beat_id=req.beat_id,
                primitive="RelationshipGraph",
                visual_purpose=req.visual_purpose or "EXPLAIN_RELATIONSHIP",
                nodes=list(req.required_entities) or [req.subject or "entity"],
                relationships=[],
                labels=[req.required_visual_concept or "evidence"],
                claim_ids=list(claim_ids or []),
                evidence_ids=[],
                source_reference="verified_claims",
                animation_type="fade_hierarchy",
                duration=req.estimated_duration or 2.5,
                verified=False,
            )
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action="MOTION_GRAPHIC_PLACEHOLDER",
                motion_graphic_plan=plan,
                recovery_strategy="MOTION_GRAPHIC",
                details={"preserved_domain": domain, "evidence_refs": claim_ids or []},
            )

        if failure_reason == "MOTION_NOT_FOUND":
            intents = [
                SearchIntent(
                    intent_id=f"recovery:{req.shot_requirement_id}:MOTION",
                    beat_id=req.beat_id,
                    shot_requirement_id=req.shot_requirement_id,
                    query=f"{entity} {req.required_visual_concept} process video".strip(),
                    query_family=QueryFamily.ENTITY_ACTION.value,
                    semantic_domain=domain,
                    target_entities=list(req.required_entities),
                    preferred_media_types=["stock_video"],
                )
            ]
            gen = None
            if req.generation_allowed:
                from app.documentary_v2.recovery.prompt_compiler import compile_generated_visual_plan

                gen = compile_generated_visual_plan(
                    req, justification="motion_not_found_illustrative"
                )
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action="ALTERNATE_VIDEO_PROVIDER_OR_GENERATED_PLACEHOLDER",
                new_intents=intents,
                generated_visual_plan=gen,
                recovery_strategy="SYNTHETIC_VIDEO" if gen else "REAL_MEDIA",
                details={
                    "preserved_domain": domain,
                    "evidence_prohibited": True,
                    "synthetic": True,
                },
            )

        if failure_reason in {"NO_CANDIDATES", "WRONG_DOMAIN", "LOW_VISUAL_RELEVANCE"}:
            extras = compile_search_intents(req)
            filtered = [i for i in extras if i.semantic_domain == domain or not domain]
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action="ALTERNATE_QUERY_FAMILY",
                new_intents=filtered[:3],
                recovery_strategy="REAL_MEDIA",
                details={"preserved_domain": domain},
            )

        if failure_reason == "LICENSE_BLOCKED":
            return RecoveryAttempt(
                beat_id=req.beat_id,
                failure_reason=failure_reason,
                action="ALTERNATE_PROVIDER",
                details={"preserved_domain": domain},
                recovery_strategy="REAL_MEDIA",
                new_intents=compile_search_intents(req)[:2],
            )

        return RecoveryAttempt(
            beat_id=req.beat_id,
            failure_reason=failure_reason,
            action="REVIEW_REQUIRED",
            review_required=True,
            recovery_strategy="UNCOVERED",
            details={"preserved_domain": domain},
        )
