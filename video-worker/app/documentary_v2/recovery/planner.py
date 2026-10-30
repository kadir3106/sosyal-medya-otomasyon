"""Semantic recovery strategy selection — not 'search failed ⇒ random B-roll'."""
from __future__ import annotations

from dataclasses import dataclass

from app.documentary_v2.recovery.synthetic_policy import (
    classify_synthetic_suitability,
    may_plan_synthetic_video,
)
from app.documentary_v2.recovery.types import RecoveryStrategy, SyntheticSuitability
from app.documentary_v2.schemas import ShotRequirement, VerifiedClaim


@dataclass
class RecoveryDecision:
    strategy: RecoveryStrategy
    reason: str
    primitive: str = ""  # motion graphic primitive if applicable
    synthetic_suitability: SyntheticSuitability | None = None
    prefer_archive: bool = False


def choose_recovery_strategy(
    req: ShotRequirement,
    *,
    failure_reason: str,
    claims: list[VerifiedClaim] | None = None,
    has_document_asset: bool = False,
    has_archive_portrait: bool = False,
    has_strong_real_video: bool = False,
) -> RecoveryDecision:
    """Choose recovery by visual purpose + evidence — never generic filler."""
    if has_strong_real_video:
        return RecoveryDecision(
            strategy=RecoveryStrategy.REAL_MEDIA,
            reason="strong_authentic_footage_available",
        )

    purpose = (req.visual_purpose or "").upper()
    claims = claims or []
    suit = classify_synthetic_suitability(req)

    if failure_reason == "VERIFIER_UNAVAILABLE":
        return RecoveryDecision(
            strategy=RecoveryStrategy.UNCOVERED,
            reason="pixels_required_verifier_unavailable",
            synthetic_suitability=suit,
        )

    # Person / founder → archival still, never fake talking person
    if purpose == "SHOW_PERSON" or (
        req.strict_entity_mode and "person" in (req.preferred_media_type or "")
    ):
        if has_archive_portrait:
            return RecoveryDecision(
                strategy=RecoveryStrategy.ARCHIVAL_STILL,
                reason="authentic_archive_portrait",
                prefer_archive=True,
                synthetic_suitability=SyntheticSuitability.REAL_MEDIA_REQUIRED,
            )
        return RecoveryDecision(
            strategy=RecoveryStrategy.ARCHIVE_MEDIA,
            reason="person_requires_archive_not_synthetic",
            prefer_archive=True,
            synthetic_suitability=SyntheticSuitability.REAL_MEDIA_REQUIRED,
        )

    # Ownership / relationship evidence → motion graphic with verified edges
    if purpose == "EXPLAIN_RELATIONSHIP" or (
        "ownership" in (req.semantic_domain or "").lower()
        and purpose in {"SHOW_EVIDENCE", "EXPLAIN_RELATIONSHIP", ""}
    ):
        # Reveal beat with dated claims → Timeline (avoid duplicate relationship cards)
        if (req.narrative_role or "").lower() in {"reveal", "payoff"} and _has_dated_claims(claims):
            return RecoveryDecision(
                strategy=RecoveryStrategy.MOTION_GRAPHIC,
                reason="verified_dated_ownership_arc",
                primitive="Timeline",
                synthetic_suitability=suit,
            )
        if _has_relationship_evidence(claims, req):
            return RecoveryDecision(
                strategy=RecoveryStrategy.MOTION_GRAPHIC,
                reason="verified_relationship_for_evidence_graphic",
                primitive="RelationshipGraph",
                synthetic_suitability=suit,
            )
        return RecoveryDecision(
            strategy=RecoveryStrategy.UNCOVERED,
            reason="relationship_lacks_verified_edges",
            synthetic_suitability=suit,
        )

    # Evidence / document
    if purpose == "SHOW_EVIDENCE" or (req.evidence_role or "").upper() in {
        "EVIDENCE_REQUIRED",
        "EVIDENCE",
    }:
        if has_document_asset:
            return RecoveryDecision(
                strategy=RecoveryStrategy.DOCUMENT_EVIDENCE,
                reason="real_document_asset",
                primitive="DocumentHighlight",
                synthetic_suitability=suit,
            )
        if claims:
            return RecoveryDecision(
                strategy=RecoveryStrategy.MOTION_GRAPHIC,
                reason="explanatory_evidence_card_not_fake_document",
                primitive="EvidenceCard",
                synthetic_suitability=suit,
            )
        return RecoveryDecision(
            strategy=RecoveryStrategy.UNCOVERED,
            reason="no_verified_evidence_for_graphic",
            synthetic_suitability=suit,
        )

    # Location
    if purpose == "SHOW_LOCATION" or req.location:
        return RecoveryDecision(
            strategy=RecoveryStrategy.MOTION_GRAPHIC,
            reason="geographical_narrative_map",
            primitive="MapHighlight",
            synthetic_suitability=suit,
        )

    # Timeline / historical date
    if _looks_like_timeline(req, claims):
        if _has_dated_claims(claims):
            return RecoveryDecision(
                strategy=RecoveryStrategy.MOTION_GRAPHIC,
                reason="verified_dated_events",
                primitive="Timeline",
                synthetic_suitability=suit,
            )
        return RecoveryDecision(
            strategy=RecoveryStrategy.UNCOVERED,
            reason="timeline_without_verified_dates",
            synthetic_suitability=suit,
        )

    # Numbers / counter
    if _looks_like_number(req, claims):
        if _has_numeric_claim(claims):
            return RecoveryDecision(
                strategy=RecoveryStrategy.MOTION_GRAPHIC,
                reason="verified_numeric_claim",
                primitive="Counter",
                synthetic_suitability=suit,
            )
        return RecoveryDecision(
            strategy=RecoveryStrategy.UNCOVERED,
            reason="number_without_verified_claim",
            synthetic_suitability=suit,
        )

    # Process — real video preferred; map/context graphic only as last explanatory hold
    if purpose == "SHOW_PROCESS":
        if may_plan_synthetic_video(req) and req.generation_allowed:
            return RecoveryDecision(
                strategy=RecoveryStrategy.SYNTHETIC_VIDEO,
                reason="process_uncovered_illustrative_synthetic_only",
                synthetic_suitability=suit,
            )
        if req.location or any(
            k in (req.required_visual_concept or "").lower()
            for k in ("swiss", "geneva", "switzerland", "factory")
        ):
            return RecoveryDecision(
                strategy=RecoveryStrategy.MOTION_GRAPHIC,
                reason="process_uncovered_location_context_map",
                primitive="MapHighlight",
                synthetic_suitability=suit,
            )
        return RecoveryDecision(
            strategy=RecoveryStrategy.REAL_MEDIA,
            reason="process_requires_real_motion_requery",
            synthetic_suitability=SyntheticSuitability.REAL_MEDIA_REQUIRED,
        )

    # Product / payoff — explanatory card over empty black if claims exist
    if purpose in {"SHOW_PRODUCT", "CREATE_PAYOFF", "IDENTIFY_ENTITY"} and claims:
        return RecoveryDecision(
            strategy=RecoveryStrategy.MOTION_GRAPHIC,
            reason="explanatory_graphic_over_generic_broll",
            primitive="EvidenceCard",
            synthetic_suitability=suit,
        )

    # Abstract illustrative
    if suit == SyntheticSuitability.SAFE_FOR_SYNTHETIC and may_plan_synthetic_video(req):
        return RecoveryDecision(
            strategy=RecoveryStrategy.SYNTHETIC_VIDEO,
            reason="abstract_safe_for_synthetic_illustration",
            synthetic_suitability=suit,
        )

    # Fall through: try evidence card / entity flow if claims exist
    if claims and purpose in {"ESTABLISH_CONTEXT", "CREATE_PAYOFF", ""}:
        return RecoveryDecision(
            strategy=RecoveryStrategy.MOTION_GRAPHIC,
            reason="explanatory_graphic_over_generic_broll",
            primitive="EvidenceCard",
            synthetic_suitability=suit,
        )

    return RecoveryDecision(
        strategy=RecoveryStrategy.UNCOVERED,
        reason=f"no_suitable_recovery_for_{failure_reason}",
        synthetic_suitability=suit,
    )


def _has_relationship_evidence(claims: list[VerifiedClaim], req: ShotRequirement) -> bool:
    for c in claims:
        if (c.status or "").lower() not in {"supported", "partial"}:
            continue
        blob = f"{c.text} {c.claim_type} {c.narrative_role}".lower()
        if any(k in blob for k in ("own", "found", "creat", "control", "subsidiar", "trust")):
            return True
        if c.evidence:
            return True
    # Allow explicit claim_ids on shot even if claim objects sparse
    return bool(req.claim_ids) and bool(claims)


def _looks_like_timeline(req: ShotRequirement, claims: list[VerifiedClaim]) -> bool:
    blob = f"{req.required_visual_concept} {req.time_context} {req.action}".lower()
    if any(k in blob for k in ("timeline", "history", "founded", "year", "decade", "chronolog")):
        return True
    return any("date" in (c.claim_type or "").lower() for c in claims)


def _has_dated_claims(claims: list[VerifiedClaim]) -> bool:
    for c in claims:
        if (c.status or "").lower() not in {"supported", "partial"}:
            continue
        text = c.text or ""
        if any(ch.isdigit() for ch in text) and any(
            y in text for y in ("19", "20", "18")
        ):
            return True
        for ev in c.evidence or []:
            if ev.get("date") or ev.get("year"):
                return True
    return False


def _looks_like_number(req: ShotRequirement, claims: list[VerifiedClaim]) -> bool:
    blob = f"{req.required_visual_concept} {req.subject}".lower()
    return any(k in blob for k in ("percent", "%", "billion", "million", "revenue", "share", "number"))


def _has_numeric_claim(claims: list[VerifiedClaim]) -> bool:
    for c in claims:
        if (c.status or "").lower() not in {"supported", "partial"}:
            continue
        if any(ch.isdigit() for ch in (c.text or "")):
            return True
    return False
