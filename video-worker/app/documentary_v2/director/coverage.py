"""Beat coverage after selection."""
from __future__ import annotations

from app.documentary_v2.schemas import (
    BeatCoverageReport,
    ShotRequirement,
    ShotSelection,
    VisualVerification,
)


def compute_coverage(
    req: ShotRequirement,
    selection: ShotSelection | None,
    verification: VisualVerification | None,
    *,
    failure_reason: str = "",
) -> BeatCoverageReport:
    if selection and verification and (verification.decision or "").upper() == "ACCEPT":
        missing = []
        satisfied = [req.required_visual_concept] if req.required_visual_concept else []
        if req.required_entities and verification.entity_alignment in {"NONE", "WEAK", "UNKNOWN"}:
            missing.append("entity")
        if req.motion_requirement == "REQUIRED" and verification.motion_value in {
            "STATIC_VIDEO",
            "MINIMAL_CAMERA_MOTION",
        }:
            missing.append("motion")
        if req.evidence_role == "EVIDENCE_REQUIRED" and verification.evidence_value != "EVIDENCE":
            missing.append("evidence")
        status = "PARTIAL" if missing else "COVERED"
        return BeatCoverageReport(
            beat_id=req.beat_id,
            status=status,
            importance=req.importance,
            selected_shot_ids=[selection.shot_id],
            required_concepts_satisfied=satisfied,
            missing_requirements=missing,
            verification_confidence=verification.confidence,
            evidence_coverage=verification.evidence_value,
            motion_coverage=verification.motion_value,
            failure_reason="" if status == "COVERED" else (failure_reason or "PARTIAL_REQUIREMENTS"),
        )
    return BeatCoverageReport(
        beat_id=req.beat_id,
        status="UNCOVERED",
        importance=req.importance,
        selected_shot_ids=[],
        required_concepts_satisfied=[],
        missing_requirements=["selection"],
        verification_confidence=verification.confidence if verification else None,
        evidence_coverage="",
        motion_coverage="",
        failure_reason=failure_reason or "NO_VALID_SELECTION",
    )
