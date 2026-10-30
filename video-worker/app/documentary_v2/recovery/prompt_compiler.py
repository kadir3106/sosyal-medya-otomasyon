"""Compile ShotRequirement → generation prompt (never raw narration dump)."""
from __future__ import annotations

from app.documentary_v2.recovery.synthetic_policy import classify_synthetic_suitability
from app.documentary_v2.recovery.types import SyntheticSuitability
from app.documentary_v2.schemas import GeneratedVisualPlan, ShotRequirement, VerifiedStory
import uuid


def compile_generated_visual_plan(
    req: ShotRequirement,
    *,
    story: VerifiedStory | None = None,
    justification: str = "",
    cost_ceiling_usd: float = 0.25,
) -> GeneratedVisualPlan | None:
    suit = classify_synthetic_suitability(req)
    if suit in {
        SyntheticSuitability.REAL_MEDIA_REQUIRED,
        SyntheticSuitability.UNSAFE_AS_SYNTHETIC_EVIDENCE,
    }:
        return None
    if not req.generation_allowed and suit != SyntheticSuitability.SAFE_FOR_SYNTHETIC:
        return None

    subject = req.subject or (req.required_entities[0] if req.required_entities else "subject")
    action = req.action or "subtle motion"
    environment = req.location or "neutral cinematic environment"
    forbidden = list(req.forbidden_visual_concepts or []) + [
        "fake logos",
        "fake legal documents",
        "fake historical documents",
        "readable forged text",
        "photoreal celebrity face impersonation",
    ]
    factual = [
        "Do not invent brand marks",
        "Do not depict undocumented historical actions as real",
        "Illustrative only — not archive footage",
    ]
    prompt = (
        f"Vertical 9:16 cinematic illustration. Subject: {subject}. "
        f"Action: {action}. Environment: {environment}. "
        f"Camera: {req.visual_purpose or 'slow push-in'}, shallow depth, documentary grade lighting. "
        f"Motion: natural subtle subject/camera motion. "
        f"Style: restrained, high contrast, no text overlays, no watermarks, no logos. "
        f"Concept: {req.required_visual_concept}. "
        "Clearly illustrative synthetic imagery, not archival documentary evidence."
    )
    if story and story.topic:
        prompt += f" Topic context (mood only): {story.topic[:80]}."

    return GeneratedVisualPlan(
        plan_id=f"gen:{uuid.uuid4().hex[:10]}",
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        prompt=prompt,
        visual_purpose=req.visual_purpose,
        subject=subject,
        action=action,
        environment=environment,
        camera_intent="slow cinematic push-in",
        motion_intent="subtle natural motion",
        style_constraints=["vertical", "no_text", "no_logos", "documentary_grade"],
        factual_constraints=factual,
        forbidden_content=forbidden,
        generation_allowed=True,
        synthetic=True,
        evidence_prohibited=True,
        synthetic_disclosure=suit.value,
        claim_ids=list(req.claim_ids or []),
        duration=min(float(req.estimated_duration or 4.0), 5.0),
        aspect_ratio="9:16",
        cost_ceiling_usd=cost_ceiling_usd,
        generation_justification=justification or "uncovered_beat_illustrative_recovery",
        recovery_strategy="SYNTHETIC_VIDEO",
    )
