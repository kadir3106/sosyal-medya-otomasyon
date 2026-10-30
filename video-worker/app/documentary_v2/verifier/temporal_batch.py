"""Temporal frame batching + conservative aggregation for image-limited VLMs."""
from __future__ import annotations

from typing import Any

from app.documentary_v2.schemas import PreviewFrame


def plan_temporal_batches(
    frames: list[PreviewFrame],
    *,
    max_images_per_request: int,
) -> list[list[PreviewFrame]]:
    """Deterministic temporal grouping that preserves coverage without silent truncate.

    Example (max=3, 6 frames):
      Batch A: indices 0,2,4
      Batch B: indices 1,3,5
    """
    if max_images_per_request < 1:
        raise ValueError("max_images_per_request must be >= 1")
    if not frames:
        return []
    if len(frames) <= max_images_per_request:
        return [list(frames)]

    # Number of batches = ceil(n / max); interleave by stride
    n = len(frames)
    batch_count = (n + max_images_per_request - 1) // max_images_per_request
    batches: list[list[PreviewFrame]] = [[] for _ in range(batch_count)]
    for i, fr in enumerate(frames):
        batches[i % batch_count].append(fr)
    # Drop empty (shouldn't happen)
    return [b for b in batches if b]


def _norm_align(v: Any) -> str:
    s = str(v or "UNKNOWN").upper()
    allowed = {"NONE", "WEAK", "PARTIAL", "STRONG", "EXACT", "UNKNOWN"}
    return s if s in allowed else "UNKNOWN"


_ALIGN_RANK = {
    "NONE": 0,
    "WEAK": 1,
    "PARTIAL": 2,
    "STRONG": 3,
    "EXACT": 4,
    "UNKNOWN": -1,
}


def _min_align(values: list[str]) -> str:
    """Conservative: weakest non-UNKNOWN if any positive evidence exists separately."""
    norms = [_norm_align(v) for v in values]
    known = [a for a in norms if a != "UNKNOWN"]
    if not known:
        return "UNKNOWN"
    return min(known, key=lambda a: _ALIGN_RANK[a])


def _max_align(values: list[str]) -> str:
    norms = [_norm_align(v) for v in values]
    known = [a for a in norms if a != "UNKNOWN"]
    if not known:
        return "UNKNOWN"
    return max(known, key=lambda a: _ALIGN_RANK[a])


def aggregate_temporal_observations(
    batch_results: list[dict[str, Any]],
    *,
    total_frame_count: int,
    batch_frame_counts: list[int] | None = None,
) -> dict[str, Any]:
    """Combine batch observations without blind averaging into ACCEPT.

    Dominant temporal semantics win. Brief entity flash → low presence ratio.
    """
    if not batch_results:
        raise ValueError("empty batch_results")
    if len(batch_results) == 1:
        out = dict(batch_results[0])
        out.setdefault("_temporal", {"batches": 1, "total_frames": total_frame_count})
        return out

    counts = batch_frame_counts or [1] * len(batch_results)
    total_w = max(1, sum(counts))

    def _union_str(key: str) -> list[str]:
        seen: list[str] = []
        for br in batch_results:
            for item in br.get(key) or []:
                s = str(item).strip()
                if s and s not in seen:
                    seen.append(s)
        return seen

    # Presence: weight by frames where concept/entity was aligned STRONG/EXACT/PARTIAL
    entity_hits = 0.0
    concept_hits = 0.0
    for br, w in zip(batch_results, counts):
        ea = _norm_align(br.get("entity_alignment"))
        ca = _norm_align(br.get("concept_alignment"))
        er = br.get("entity_presence_ratio")
        cr = br.get("concept_presence_ratio")
        try:
            er_f = float(er) if er is not None else (1.0 if ea in {"STRONG", "EXACT", "PARTIAL"} else 0.0)
        except (TypeError, ValueError):
            er_f = 0.0
        try:
            cr_f = float(cr) if cr is not None else (1.0 if ca in {"STRONG", "EXACT", "PARTIAL"} else 0.0)
        except (TypeError, ValueError):
            cr_f = 0.0
        entity_hits += er_f * w
        concept_hits += cr_f * w

    entity_ratio = entity_hits / total_w
    concept_ratio = concept_hits / total_w

    # Alignments: max shows any evidence; decision layer uses presence ratios for temporal weak
    entity_al = _max_align([br.get("entity_alignment") for br in batch_results])
    concept_al = _max_align([br.get("concept_alignment") for br in batch_results])
    # If only a minority of timeline supports entity, demote alignment for reporting honesty
    if entity_ratio < 0.34 and entity_al in {"STRONG", "EXACT"}:
        entity_al = "PARTIAL" if entity_ratio >= 0.15 else "WEAK"
    if concept_ratio < 0.34 and concept_al in {"STRONG", "EXACT"}:
        concept_al = "PARTIAL" if concept_ratio >= 0.15 else "WEAK"

    contradictions = _union_str("contradictions")
    # Cross-batch conflict: different dominant concepts
    dominants = [
        str(br.get("dominant_visual_concept") or "").strip().lower()
        for br in batch_results
        if str(br.get("dominant_visual_concept") or "").strip()
    ]
    unique_dom = list(dict.fromkeys(dominants))
    if len(unique_dom) > 1:
        contradictions.append(
            f"temporal_mixed_dominants:{'|'.join(unique_dom[:4])}"
        )

    meta_conflict = any(bool(br.get("metadata_visual_conflict")) for br in batch_results)
    # Prefer most specific non-UNKNOWN specificity when mixed
    specs = [str(br.get("entity_specificity") or "UNKNOWN").upper() for br in batch_results]
    specificity = "UNKNOWN"
    for pref in ("EXACT_ENTITY", "RELATED_CATEGORY", "GENERIC_CATEGORY", "UNRELATED", "UNKNOWN"):
        if pref in specs:
            # If any UNRELATED and any EXACT → conflict already in contradictions
            specificity = pref
            break
    if "UNRELATED" in specs and any(s in specs for s in ("EXACT_ENTITY", "RELATED_CATEGORY")):
        contradictions.append("temporal_specificity_conflict")
        specificity = "UNRELATED"
        meta_conflict = True

    # Dominant: pick concept from batch with highest concept presence weight
    best_i = max(
        range(len(batch_results)),
        key=lambda i: float(batch_results[i].get("concept_presence_ratio") or 0.0) * counts[i],
    )
    dominant = str(batch_results[best_i].get("dominant_visual_concept") or "")

    confs = []
    for br in batch_results:
        try:
            confs.append(float(br.get("confidence")))
        except (TypeError, ValueError):
            pass
    # Conservative confidence: min, not mean
    confidence = min(confs) if confs else 0.0

    genericness_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "UNKNOWN": -1}
    gens = [str(br.get("genericness") or "UNKNOWN").upper() for br in batch_results]
    known_g = [g for g in gens if g in genericness_rank and g != "UNKNOWN"]
    genericness = max(known_g, key=lambda g: genericness_rank[g]) if known_g else "UNKNOWN"

    visual_roles = [str(br.get("visual_role") or "UNKNOWN").upper() for br in batch_results]
    # Prefer UNRELATED/GENERIC if present alongside EVIDENCE → not evidence overall
    if "UNRELATED" in visual_roles:
        visual_role = "UNRELATED"
    elif "GENERIC_CONTEXT" in visual_roles and "EVIDENCE" not in visual_roles:
        visual_role = "GENERIC_CONTEXT"
    elif "ILLUSTRATION" in visual_roles:
        visual_role = "ILLUSTRATION"
    else:
        visual_role = visual_roles[best_i]

    out: dict[str, Any] = {
        "visible_entities": _union_str("visible_entities"),
        "visible_objects": _union_str("visible_objects"),
        "visible_actions": _union_str("visible_actions"),
        "visible_setting": str(batch_results[best_i].get("visible_setting") or ""),
        "visible_location": str(batch_results[best_i].get("visible_location") or ""),
        "visible_text_summary": str(batch_results[best_i].get("visible_text_summary") or ""),
        "motion_description": str(batch_results[best_i].get("motion_description") or ""),
        "dominant_visual_concept": dominant,
        "entity_alignment": entity_al,
        "concept_alignment": concept_al,
        "action_alignment": _min_align([br.get("action_alignment") for br in batch_results]),
        "location_alignment": _min_align([br.get("location_alignment") for br in batch_results]),
        "entity_specificity": specificity,
        "motion_value": str(batch_results[best_i].get("motion_value") or "UNKNOWN_MOTION"),
        "visual_role": visual_role,
        "authenticity_support": str(
            batch_results[best_i].get("authenticity_support") or "UNKNOWN"
        ),
        "genericness": genericness,
        "contradictions": contradictions,
        "forbidden_concept_hits": _union_str("forbidden_concept_hits"),
        "metadata_visual_conflict": meta_conflict,
        "visual_supported_claims": _union_str("visual_supported_claims"),
        "metadata_supported_claims": _union_str("metadata_supported_claims"),
        "entity_presence_ratio": round(entity_ratio, 4),
        "concept_presence_ratio": round(concept_ratio, 4),
        "pixels_consistent_with_archival_portrait": any(
            bool(br.get("pixels_consistent_with_archival_portrait")) for br in batch_results
        ),
        "preview_unusable": all(bool(br.get("preview_unusable")) for br in batch_results),
        "confidence": confidence,
        "explanation_short": (
            f"temporal_aggregate batches={len(batch_results)} frames={total_frame_count}; "
            + str(batch_results[best_i].get("explanation_short") or "")
        )[:400],
        "_temporal": {
            "batches": len(batch_results),
            "total_frames": total_frame_count,
            "batch_frame_counts": list(counts),
            "entity_presence_ratio": round(entity_ratio, 4),
            "concept_presence_ratio": round(concept_ratio, 4),
            "dominants": unique_dom,
        },
    }
    return out
