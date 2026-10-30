"""ShotCandidateRanker — hard constraints first, then soft explainable scores."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.documentary_v2.schemas import (
    MediaCandidate,
    RankedCandidate,
    ShotRequirement,
    VisualVerification,
)
from app.documentary_v2.verifier.reason_codes import (
    DECISION_ACCEPT,
    DECISION_REJECT,
    DECISION_UNCERTAIN,
)


# Soft weights (centralized, explainable)
SOFT_WEIGHTS = {
    "entity_alignment": 0.22,
    "concept_alignment": 0.22,
    "action_alignment": 0.10,
    "location_alignment": 0.10,
    "evidence_value": 0.12,
    "motion_suitability": 0.08,
    "genericness_penalty": 0.08,
    "source_novelty": 0.05,
    "confidence": 0.03,
}

_ALIGN = {"NONE": 0.0, "WEAK": 0.25, "PARTIAL": 0.55, "STRONG": 0.85, "EXACT": 1.0, "UNKNOWN": 0.15}


def _align(v: str) -> float:
    return _ALIGN.get((v or "UNKNOWN").upper(), 0.15)


@dataclass
class RankerContext:
    used_source_keys: set[str] = field(default_factory=set)
    used_viu_keys: set[str] = field(default_factory=set)


def source_key(candidate: MediaCandidate) -> str:
    p = candidate.provenance
    if p.provider and p.source_id:
        return f"{p.provider}:{p.source_id}".lower()
    if candidate.content_fingerprint:
        return f"fp:{candidate.content_fingerprint}"
    return candidate.candidate_id.lower()


def hard_constraints(
    req: ShotRequirement,
    verification: VisualVerification,
) -> tuple[bool, list[str]]:
    """Return (pass, fail_reasons). Wrong entity cannot be rescued by beauty."""
    fails: list[str] = []
    decision = (verification.decision or verification.status or "").upper()
    if decision == DECISION_REJECT:
        fails.append("VERIFIER_REJECT")
    if decision == DECISION_UNCERTAIN and req.strict_entity_mode:
        fails.append("STRICT_UNCERTAIN")
    if decision == DECISION_UNCERTAIN and req.importance == "important" and req.evidence_role == "EVIDENCE_REQUIRED":
        fails.append("STRICT_UNCERTAIN")

    if req.required_entities:
        if verification.entity_alignment in {"NONE"}:
            fails.append("REQUIRED_ENTITY_MISMATCH")
        if verification.metadata_visual_conflict and verification.entity_alignment in {
            "NONE",
            "WEAK",
            "UNKNOWN",
        }:
            fails.append("METADATA_VISUAL_CONFLICT")

    if verification.contradictions and verification.concept_alignment in {"NONE", "WEAK"}:
        fails.append("VISUAL_CONTRADICTION")

    if verification.forbidden_concept_hits:
        fails.append("FORBIDDEN_CONCEPT")

    if req.evidence_role == "EVIDENCE_REQUIRED":
        if verification.evidence_value in {
            "ILLUSTRATION",
            "GENERIC_CONTEXT",
            "UNRELATED",
        }:
            fails.append("EVIDENCE_REQUIRED_BUT_DECORATIVE")

    if req.motion_requirement == "REQUIRED":
        if verification.motion_value in {"STATIC_VIDEO", "MINIMAL_CAMERA_MOTION"}:
            fails.append("MOTION_REQUIRED_BUT_STATIC")

    if "LICENSE_BLOCKED" in (verification.reason_codes or []):
        fails.append("LICENSE_BLOCKED")

    # UNCERTAIN without ACCEPT is not eligible for auto-select on strict
    eligible_decision = decision == DECISION_ACCEPT
    if not eligible_decision and req.evidence_role == "ILLUSTRATION_ACCEPTABLE" and not req.strict_entity_mode:
        # Low-risk illustrative: UNCERTAIN may compete only as soft fallback later
        pass

    hard_pass = not fails and eligible_decision
    return hard_pass, fails


def soft_score(
    req: ShotRequirement,
    candidate: MediaCandidate,
    verification: VisualVerification,
    ctx: RankerContext,
) -> tuple[float, dict]:
    breakdown: dict[str, float] = {}
    breakdown["entity_alignment"] = _align(verification.entity_alignment)
    breakdown["concept_alignment"] = _align(verification.concept_alignment)
    breakdown["action_alignment"] = _align(verification.action_alignment)
    breakdown["location_alignment"] = _align(verification.location_alignment)

    ev = (verification.evidence_value or "").upper()
    if req.evidence_role == "EVIDENCE_REQUIRED":
        breakdown["evidence_value"] = 1.0 if ev == "EVIDENCE" else (0.4 if ev == "AUTHENTIC_CONTEXT" else 0.0)
    else:
        breakdown["evidence_value"] = 0.7 if ev in {"ILLUSTRATION", "AUTHENTIC_CONTEXT", "EVIDENCE"} else 0.3

    motion = (verification.motion_value or "").upper()
    if req.motion_requirement == "REQUIRED":
        breakdown["motion_suitability"] = (
            1.0
            if motion in {"PROCESS_MOTION", "NATURAL_SUBJECT_MOTION"}
            else (0.2 if motion == "FAST_MONTAGE" else 0.0)
        )
    elif req.motion_requirement == "NOT_NEEDED":
        # Still OK — don't punish static
        breakdown["motion_suitability"] = 0.8 if motion in {"STATIC_VIDEO", "MINIMAL_CAMERA_MOTION", "UNKNOWN_MOTION"} else 0.7
    else:
        breakdown["motion_suitability"] = 0.6 if motion != "STATIC_VIDEO" else 0.4

    gen = (verification.genericness or "UNKNOWN").upper()
    breakdown["genericness_penalty"] = {"LOW": 1.0, "MEDIUM": 0.55, "HIGH": 0.1, "UNKNOWN": 0.4}.get(gen, 0.4)

    sk = source_key(candidate)
    novelty = 1.0 if sk not in ctx.used_source_keys else 0.25
    breakdown["source_novelty"] = novelty
    breakdown["confidence"] = float(verification.confidence or 0.5)

    total = 0.0
    for k, w in SOFT_WEIGHTS.items():
        total += w * float(breakdown.get(k, 0.0))
    return total, breakdown


def rank_candidates(
    req: ShotRequirement,
    pairs: list[tuple[MediaCandidate, VisualVerification]],
    ctx: RankerContext | None = None,
) -> list[RankedCandidate]:
    ctx = ctx or RankerContext()
    ranked: list[RankedCandidate] = []
    for cand, ver in pairs:
        hard_ok, fails = hard_constraints(req, ver)
        score, breakdown = soft_score(req, cand, ver, ctx)
        ranked.append(
            RankedCandidate(
                candidate_id=cand.candidate_id,
                verification_id=ver.verification_id,
                eligible=hard_ok,
                hard_pass=hard_ok,
                hard_fail_reasons=fails,
                soft_score=score if hard_ok else -1.0,
                score_breakdown=breakdown,
                decision=ver.decision or ver.status,
            )
        )
    # Eligible first by soft score; ineligible last
    ranked.sort(key=lambda r: (0 if r.eligible else 1, -r.soft_score))
    for i, r in enumerate(ranked):
        r.rank = i + 1
    return ranked
