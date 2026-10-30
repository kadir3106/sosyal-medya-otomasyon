"""Synthetic suitability classifier — communication first, never fake evidence."""
from __future__ import annotations

from app.documentary_v2.recovery.types import SyntheticSuitability
from app.documentary_v2.schemas import ShotRequirement


def classify_synthetic_suitability(req: ShotRequirement) -> SyntheticSuitability:
    purpose = (req.visual_purpose or "").upper()
    evidence = (req.evidence_role or "").upper()
    domain = (req.semantic_domain or "").lower()
    concept = (req.required_visual_concept or "").lower()

    # Legal / ownership evidence cannot be satisfied by synthetic video
    if evidence in {"EVIDENCE_REQUIRED", "EVIDENCE"} or purpose in {
        "SHOW_EVIDENCE",
        "EXPLAIN_RELATIONSHIP",
    }:
        if "ownership" in domain or "legal" in domain or "trust" in domain:
            return SyntheticSuitability.UNSAFE_AS_SYNTHETIC_EVIDENCE
        if purpose == "EXPLAIN_RELATIONSHIP":
            return SyntheticSuitability.UNSAFE_AS_SYNTHETIC_EVIDENCE

    # Named person factual / historical action → real media required
    if purpose == "SHOW_PERSON" or req.strict_entity_mode:
        return SyntheticSuitability.REAL_MEDIA_REQUIRED

    if any(k in concept for k in ("historical", "archive", "founded in", "war", "treaty")):
        return SyntheticSuitability.ILLUSTRATIVE_ONLY

    # Authentic process strongly prefers real footage
    if purpose == "SHOW_PROCESS":
        if req.generation_allowed:
            return SyntheticSuitability.ILLUSTRATIVE_ONLY
        return SyntheticSuitability.REAL_MEDIA_REQUIRED

    if purpose in {"SHOW_PRODUCT", "IDENTIFY_ENTITY"} and req.strict_entity_mode:
        return SyntheticSuitability.REAL_MEDIA_REQUIRED

    # Abstract / conceptual illustration
    if purpose in {"ESTABLISH_CONTEXT", "CREATE_PAYOFF"} or "abstract" in concept:
        return SyntheticSuitability.SAFE_FOR_SYNTHETIC

    if req.generation_allowed and evidence in {
        "",
        "ILLUSTRATION_ACCEPTABLE",
        "ILLUSTRATIVE",
    }:
        return SyntheticSuitability.SAFE_FOR_SYNTHETIC

    return SyntheticSuitability.ILLUSTRATIVE_ONLY


def may_plan_synthetic_video(req: ShotRequirement) -> bool:
    """Whether a GeneratedVisualPlan may be created (still must re-verify)."""
    suit = classify_synthetic_suitability(req)
    if suit == SyntheticSuitability.REAL_MEDIA_REQUIRED:
        return False
    if suit == SyntheticSuitability.UNSAFE_AS_SYNTHETIC_EVIDENCE:
        return False
    if not req.generation_allowed and suit != SyntheticSuitability.SAFE_FOR_SYNTHETIC:
        return False
    return True
