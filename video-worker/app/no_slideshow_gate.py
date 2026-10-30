"""No-Slideshow Quality Gate — motion/zoom is not visual information."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.story_domains import (
    analyze_source_assets,
    important_beat_coverage,
    uncovered_important_beats,
)
from app.storyboard import analyze_storyboard_coverage, enrich_beat_dict


@dataclass
class NoSlideshowGateResult:
    status: str  # PASS | REVIEW_REQUIRED | FAIL
    reasons: list[str] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_no_slideshow(
    word_to_visual: list[dict],
    *,
    retention_events: list[dict] | None = None,
    topic: str = "",
    story_consistency: dict | None = None,
    beat_coverage: list[dict] | None = None,
    recovery_log: list[dict] | None = None,
) -> NoSlideshowGateResult:
    """Analyze whether the edit is a mini-documentary vs animated photo album."""
    from app.beat_recovery import build_all_beat_coverage

    cov = analyze_storyboard_coverage(word_to_visual or [])
    enriched = [enrich_beat_dict(b) for b in (word_to_visual or [])]
    events = retention_events or []
    source = analyze_source_assets(word_to_visual or [])
    coverage_rows = beat_coverage or [
        c.to_dict() for c in build_all_beat_coverage(word_to_visual or [], topic=topic)
    ]
    # Prefer new BeatCoverage objects; fall back to legacy important_beat_coverage
    if not beat_coverage:
        coverage_rows_legacy = important_beat_coverage(word_to_visual or [])
        uncovered = uncovered_important_beats(word_to_visual or [])
    else:
        coverage_rows_legacy = coverage_rows
        uncovered = [
            c
            for c in coverage_rows
            if c.get("importance") == "important" and c.get("status") == "UNCOVERED"
        ]

    real_video = 0
    archive_still = 0
    other_still = 0
    transform_only = 0
    total_dur = 0.0
    still_dur = 0.0
    video_dur = 0.0
    transform_dur = 0.0

    for b in enriched:
        dur = float(b.get("duration") or b.get("resolved_duration") or 1.6)
        total_dur += dur
        kind = str(b.get("media_kind") or b.get("kind") or "").lower()
        path = str(
            b.get("path")
            or (b.get("selected_asset") or {}).get("path")
            or ""
        ).lower()
        evidence = str(b.get("evidence_role") or "")
        vc = str(b.get("visual_change") or b.get("visual_change_applied") or "").lower()
        is_video = "video" in kind or path.endswith((".mp4", ".webm", ".mov"))
        if is_video:
            real_video += 1
            video_dur += dur
        else:
            if evidence == "archive" or "archive" in str(b.get("concept") or "").lower():
                archive_still += 1
            else:
                other_still += 1
            still_dur += dur
        if vc in {"punch_in", "crop_zoom", "archive_motion", "reuse_with_motion"}:
            if str(b.get("visual_change") or "") != "new_asset" or b.get(
                "force_visual_change_reuse"
            ):
                transform_only += 1
                transform_dur += dur

    same_still_events = sum(
        1
        for e in events
        if isinstance(e, dict)
        and e.get("event_type") == "controlled_punch_in"
        and not e.get("asset_change_required")
    )

    reasons: list[str] = []
    if cov.beat_count >= 3 and cov.unique_visual_information_units <= 1:
        reasons.append("INSUFFICIENT_VISUAL_INFORMATION")
    if cov.beats_using_same_asset_transform_only >= 2 or same_still_events >= 2:
        reasons.append("TRANSFORM_AS_FAKE_VARIETY")
    if transform_only >= max(2, (cov.beat_count or 1) // 2) and real_video == 0:
        reasons.append("EXCESSIVE_SAME_STILL_REUSE")
    if uncovered:
        reasons.append("IMPORTANT_BEAT_UNCOVERED")
    elif not beat_coverage and cov.uncovered_beats:
        important_uncovered = [
            u for u in cov.uncovered_beats if len(str(u).split()) >= 5
        ]
        if important_uncovered:
            reasons.append("IMPORTANT_BEAT_UNCOVERED")

    uniq = int(source.get("unique_source_asset_count") or 0)
    shots = int(source.get("shot_count") or cov.beat_count or 0)
    if shots >= 6 and uniq <= 1:
        reasons.append("LOW_UNIQUE_SOURCE_ASSET_COUNT")
    elif shots >= 4 and uniq <= 1 and cov.unique_visual_information_units <= 2:
        reasons.append("LOW_UNIQUE_SOURCE_ASSET_COUNT")
    reused = source.get("reused_source_assets") or []
    reuse_map = source.get("reuse_count_per_asset") or {}
    max_reuse = max(reuse_map.values()) if reuse_map else 0
    if shots >= 5 and max_reuse >= max(4, shots - 1):
        reasons.append("EXCESSIVE_SOURCE_REUSE")
    if shots >= 5 and uniq <= 1 and max_reuse >= shots - 1:
        reasons.append("RETRIEVAL_COLLAPSE")

    sc = story_consistency or {}
    if sc.get("status") == "FAIL" or "SEMANTIC_DOMAIN_DRIFT" in (sc.get("reasons") or []):
        reasons.append("SEMANTIC_DOMAIN_DRIFT")

    motion_roles = {"money", "place"}
    motion_beats = [
        b
        for b in enriched
        if str(b.get("narrative_role") or "") in motion_roles
        or any(
            x in str(b.get("concept") or "").lower()
            for x in ("finance", "location", "market", "manufactur")
        )
    ]
    if motion_beats and all(
        "video"
        not in str(b.get("media_kind") or b.get("kind") or "").lower()
        and not str((b.get("selected_asset") or {}).get("path") or "")
        .lower()
        .endswith((".mp4", ".webm"))
        for b in motion_beats
    ):
        reasons.append("MOTION_OPPORTUNITY_MISSED")

    generic = sum(
        1
        for b in enriched
        if str(b.get("evidence_role") or "") == "illustrative"
        and not (b.get("primary_entities") or b.get("entities"))
    )
    if cov.beat_count >= 4 and generic >= cov.beat_count - 1:
        reasons.append("GENERIC_BROLL_OVERUSE")

    archival_ok = (
        archive_still >= 1
        and cov.unique_visual_information_units >= 2
        and uniq >= 2
        and "TRANSFORM_AS_FAKE_VARIETY" not in reasons
        and "EXCESSIVE_SAME_STILL_REUSE" not in reasons
        and "LOW_UNIQUE_SOURCE_ASSET_COUNT" not in reasons
        and "RETRIEVAL_COLLAPSE" not in reasons
    )
    if archival_ok and "MOTION_OPPORTUNITY_MISSED" in reasons and real_video == 0:
        reasons = [r for r in reasons if r != "MOTION_OPPORTUNITY_MISSED"]

    hard = {
        "INSUFFICIENT_VISUAL_INFORMATION",
        "TRANSFORM_AS_FAKE_VARIETY",
        "EXCESSIVE_SAME_STILL_REUSE",
        "IMPORTANT_BEAT_UNCOVERED",
        "LOW_UNIQUE_SOURCE_ASSET_COUNT",
        "EXCESSIVE_SOURCE_REUSE",
        "RETRIEVAL_COLLAPSE",
        "SEMANTIC_DOMAIN_DRIFT",
    }
    soft = {"MOTION_OPPORTUNITY_MISSED", "GENERIC_BROLL_OVERUSE"}

    reasons = list(dict.fromkeys(reasons))

    if any(r in hard for r in reasons):
        status = "FAIL"
    elif any(r in soft for r in reasons):
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"

    if (
        status == "FAIL"
        and archival_ok
        and reasons == ["INSUFFICIENT_VISUAL_INFORMATION"]
        and cov.unique_visual_information_units >= 2
    ):
        status = "PASS"
        reasons = []

    # Rich per-beat uncovered diagnostics (recovery attempts + why stopped)
    uncovered_detail = []
    for c in coverage_rows:
        if c.get("importance") == "important" and c.get("status") == "UNCOVERED":
            uncovered_detail.append(
                {
                    "beat_id": c.get("beat_id"),
                    "semantic_domain": c.get("semantic_domain"),
                    "required_visual_concept": c.get("required_visual_concept"),
                    "required_entities": c.get("required_entities"),
                    "status": c.get("status"),
                    "attempts": len(c.get("attempts") or []),
                    "attempt_detail": c.get("attempts") or [],
                    "last_failure": c.get("failure_reason"),
                    "motion_graphic_attempted": c.get("motion_graphic_attempted"),
                    "evidence_visual_used": c.get("evidence_visual_used"),
                    "providers_tried": c.get("providers_tried") or [],
                    "reason": (
                        f"insufficient verified visual representation"
                        if c.get("failure_reason") in {"EVIDENCE_NOT_FOUND", "NO_CANDIDATES"}
                        else c.get("failure_reason")
                    ),
                }
            )

    # Important uncovered after recovery → never silent PASS
    if uncovered_detail and status == "PASS":
        status = "REVIEW_REQUIRED"
        if "IMPORTANT_BEAT_UNCOVERED" not in reasons:
            reasons.append("IMPORTANT_BEAT_UNCOVERED")

    diagnostics = {
        **cov.to_dict(),
        "real_video_shots": real_video,
        "archive_still_shots": archive_still,
        "other_still_shots": other_still,
        "same_still_transform_events": same_still_events,
        "static_visual_seconds": round(still_dur, 2),
        "motion_visual_seconds": round(video_dur, 2),
        "same_still_transform_seconds": round(transform_dur, 2),
        "total_seconds": round(total_dur, 2),
        "topic": topic[:120],
        "shot_count": shots,
        "unique_source_asset_count": uniq,
        "unique_source_assets": source.get("unique_source_assets"),
        "unique_source_assets_by_provider": source.get(
            "unique_source_assets_by_provider"
        ),
        "unique_source_assets_by_entity": source.get("unique_source_assets_by_entity"),
        "unique_source_assets_by_beat": source.get("unique_source_assets_by_beat"),
        "reused_source_assets": reused,
        "reuse_count_per_asset": reuse_map,
        "important_beat_coverage": coverage_rows_legacy,
        "beat_coverage": coverage_rows,
        "uncovered_important_beats": uncovered,
        "uncovered_beat_detail": uncovered_detail,
        "recovery_log": recovery_log or [],
        "story_consistency": sc,
    }
    return NoSlideshowGateResult(status=status, reasons=reasons, diagnostics=diagnostics)


def visual_information_units_from_shots(shots: list[dict]) -> list[dict]:
    """Build VisualInformationUnit list; crop/zoom variants share id via asset_id."""
    units: list[dict] = []
    seen: set[str] = set()
    for b in shots or []:
        e = enrich_beat_dict(b)
        vid = str(e.get("visual_information_id") or "")
        if not vid or vid in seen:
            continue
        seen.add(vid)
        units.append(
            {
                "id": vid,
                "source_asset_id": e.get("asset_id")
                or (e.get("selected_asset") or {}).get("asset_id"),
                "entity": (e.get("primary_entities") or e.get("entities") or [None])[0]
                if (e.get("primary_entities") or e.get("entities"))
                else "",
                "concept": e.get("concept"),
                "action": e.get("required_visual_concept"),
                "evidence_role": e.get("evidence_role"),
                "media_type": e.get("media_kind") or e.get("kind"),
                "authenticity": "archive"
                if e.get("evidence_role") == "archive"
                else "stock_or_other",
                "beat_id": e.get("beat") if e.get("beat") is not None else e.get("index"),
            }
        )
    return units
