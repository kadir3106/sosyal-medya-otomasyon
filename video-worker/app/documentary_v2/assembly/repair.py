"""TargetedBeatRepair — patch failed beats; never auto-zoom as variety."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.documentary_v2.schemas import CriticFinding, EditDecisionList, ShotRequirement
from app.documentary_v2.recovery.engine import VisualRecoveryEngine
from app.documentary_v2.recovery.types import RecoveryStrategy


@dataclass
class RepairAction:
    beat_id: str
    finding_id: str
    issue_code: str
    strategy: str
    original_asset: str = ""
    new_asset: str = ""
    applied: bool = False
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


ZOOM_FORBIDDEN = True  # absolute rule


def map_issue_to_strategy(issue_code: str) -> str:
    code = (issue_code or "").upper()
    mapping = {
        "WRONG_ENTITY": "reacquire_exact_entity",
        "GENERIC_FILLER": "retrieval_or_recovery",
        "UNSUPPORTED_EVIDENCE_VISUAL": "evidence_motion_graphic",
        "VISUAL_DOES_NOT_SUPPORT_CLAIM": "evidence_motion_graphic",
        "GRAPHIC_UNREADABLE": "rerender_graphic",
        "CAPTION_BLOCKS_SUBJECT": "layout_adjustment",
        "MOTION_OPPORTUNITY_MISSED": "seek_real_motion",
        "STATIC_HOLD_TOO_LONG": "seek_second_viu_not_zoom",
        "SLIDESHOW_FEEL": "replace_with_real_motion_or_review",
        "SYNTHETIC_LOOKS_LIKE_EVIDENCE": "demote_synthetic_or_replace",
        "TRANSFORM_AS_FAKE_VARIETY": "remove_transform_diversity",
    }
    return mapping.get(code, "review_required")


class TargetedBeatRepair:
    def __init__(
        self,
        *,
        max_repairs_per_beat: int = 1,
        recovery: VisualRecoveryEngine | None = None,
    ) -> None:
        self.max_repairs_per_beat = max_repairs_per_beat
        self.recovery = recovery or VisualRecoveryEngine()
        self._beat_counts: dict[str, int] = {}

    def plan_repairs(
        self,
        findings: list[CriticFinding],
        *,
        important_only_high: bool = True,
    ) -> list[RepairAction]:
        actions: list[RepairAction] = []
        for f in findings:
            if important_only_high and f.severity != "HIGH":
                continue
            beat = f.beat_id or "unknown"
            if self._beat_counts.get(beat, 0) >= self.max_repairs_per_beat:
                continue
            strategy = map_issue_to_strategy(f.issue_code)
            if strategy == "seek_second_viu_not_zoom":
                # Explicitly forbid zoom repair
                strategy = "seek_second_viu_not_zoom"
            actions.append(
                RepairAction(
                    beat_id=beat,
                    finding_id=f.finding_id,
                    issue_code=f.issue_code,
                    strategy=strategy,
                    details={"severity": f.severity, "zoom_forbidden": ZOOM_FORBIDDEN},
                )
            )
            self._beat_counts[beat] = self._beat_counts.get(beat, 0) + 1
        return actions

    def apply_recovery_repair(
        self,
        action: RepairAction,
        req: ShotRequirement,
        *,
        claims: list | None = None,
        relationship_edges: list[dict] | None = None,
        output_dir: str = "",
        job_id: str = "",
    ) -> RepairAction:
        if action.strategy in {
            "evidence_motion_graphic",
            "retrieval_or_recovery",
            "rerender_graphic",
        }:
            rr = self.recovery.recover(
                req,
                failure_reason="EVIDENCE_NOT_FOUND",
                claims=claims or [],
                relationship_edges=relationship_edges,
                output_dir=output_dir,
                job_id=job_id,
                render=True,
                generate=False,
            )
            action.applied = bool(rr.artifact_path)
            action.new_asset = rr.artifact_path
            action.details["recovery"] = rr.to_dict()
            action.details["strategy_chosen"] = rr.strategy.value
            return action
        if action.strategy == "seek_second_viu_not_zoom":
            action.applied = False
            action.details["note"] = "no_automatic_zoom;REVIEW_REQUIRED_if_no_alt_viu"
            return action
        action.applied = False
        action.details["note"] = "manual_or_requery"
        return action

    def patch_edl_asset(
        self,
        edl: EditDecisionList,
        *,
        beat_id: str,
        new_path: str,
        synthetic: bool = True,
        source_kind: str = "motion_graphic",
    ) -> EditDecisionList:
        for d in edl.decisions:
            if d.beat_id == beat_id:
                action_asset = d.local_path
                d.local_path = new_path
                d.synthetic = synthetic
                d.source_kind = source_kind
                d.media_type = source_kind
                d.asset_id = f"repaired:{beat_id}"
                d.verification_ref = "repair"
                # keep timing
                _ = action_asset
        return edl
