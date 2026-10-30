"""Map structured VLM observation → ACCEPT/REJECT/UNCERTAIN. UNKNOWN ≠ ACCEPT."""
from __future__ import annotations

from typing import Any

from app.documentary_v2.schemas import VisualVerification, VisualVerificationRequest
from app.documentary_v2.verifier import reason_codes as RC


_ALIGN_RANK = {
    "NONE": 0,
    "WEAK": 1,
    "PARTIAL": 2,
    "STRONG": 3,
    "EXACT": 4,
    "UNKNOWN": -1,
}


def _norm_align(v: Any) -> str:
    s = str(v or "UNKNOWN").upper()
    return s if s in _ALIGN_RANK else "UNKNOWN"


def _entity_key(value: Any) -> str:
    return "".join(ch for ch in str(value or "").casefold() if ch.isalnum())


def apply_decision(
    request: VisualVerificationRequest,
    observation: dict,
    *,
    verification_id: str,
    motion_estimate: str = "UNKNOWN_MOTION",
    preview_frame_count: int = 0,
    preview_duration_sec: float | None = None,
) -> VisualVerification:
    """Deterministic policy over VLM-structured fields — never ACCEPT on UNKNOWN."""
    codes: list[str] = []
    entity_al = _norm_align(observation.get("entity_alignment"))
    concept_al = _norm_align(observation.get("concept_alignment"))
    action_al = _norm_align(observation.get("action_alignment"))
    location_al = _norm_align(observation.get("location_alignment"))
    specificity = str(
        observation.get("entity_specificity") or "UNKNOWN"
    ).upper()
    genericness = str(observation.get("genericness") or "UNKNOWN").upper()
    visual_role = str(
        observation.get("visual_role")
        or observation.get("evidence_value")
        or "UNKNOWN"
    ).upper()
    authenticity = str(
        observation.get("authenticity_support") or "UNKNOWN"
    ).upper()
    motion = str(
        observation.get("motion_value") or motion_estimate or "UNKNOWN_MOTION"
    ).upper()
    contradictions = list(observation.get("contradictions") or [])
    forbidden_hits = list(observation.get("forbidden_concept_hits") or [])
    meta_conflict = bool(observation.get("metadata_visual_conflict"))
    entity_ratio = observation.get("entity_presence_ratio")
    concept_ratio = observation.get("concept_presence_ratio")
    try:
        entity_ratio = float(entity_ratio) if entity_ratio is not None else None
    except (TypeError, ValueError):
        entity_ratio = None
    try:
        concept_ratio = float(concept_ratio) if concept_ratio is not None else None
    except (TypeError, ValueError):
        concept_ratio = None

    visible_entities = list(observation.get("visible_entities") or [])
    visible_brands = list(observation.get("visible_brand_names") or [])
    visible_objects = list(observation.get("visible_objects") or [])
    visible_actions = list(observation.get("visible_actions") or [])
    visible_setting = str(observation.get("visible_setting") or "")
    dominant = str(observation.get("dominant_visual_concept") or "")
    conf = observation.get("confidence")
    try:
        conf = float(conf) if conf is not None else None
    except (TypeError, ValueError):
        conf = None

    required_keys = [_entity_key(value) for value in request.required_entities]
    concept_key = _entity_key(request.required_visual_concept)
    exact_product_beat = bool(
        request.strict_entity_mode
        and required_keys
        and any(key and key in concept_key for key in required_keys)
    )
    conflicting_brands = [
        brand
        for brand in visible_brands
        if _entity_key(brand)
        and not any(
            required and (
                required in _entity_key(brand) or _entity_key(brand) in required
            )
            for required in required_keys
        )
    ]
    wrong_entity = bool(exact_product_beat and conflicting_brands)

    # Reason code accumulation
    if entity_al in {"STRONG", "EXACT"}:
        codes.append(RC.ENTITY_MATCH)
    elif entity_al == "NONE" and request.required_entities:
        codes.append(RC.ENTITY_NOT_VISIBLE)
    elif entity_al in {"WEAK", "PARTIAL", "UNKNOWN"} and request.required_entities:
        codes.append(RC.ENTITY_AMBIGUOUS)

    if concept_al in {"STRONG", "EXACT"}:
        codes.append(RC.CONCEPT_MATCH)
    elif concept_al == "NONE":
        codes.append(RC.CONCEPT_MISMATCH)

    if request.required_action:
        if action_al in {"STRONG", "EXACT", "PARTIAL"}:
            codes.append(RC.ACTION_MATCH)
        elif action_al in {"NONE", "UNKNOWN"}:
            codes.append(RC.ACTION_MISSING)

    if request.required_location:
        if location_al in {"STRONG", "EXACT"}:
            codes.append(RC.LOCATION_MATCH)
        elif location_al == "NONE":
            codes.append(RC.LOCATION_MISMATCH)

    if meta_conflict:
        codes.append(RC.METADATA_VISUAL_CONFLICT)
    if contradictions:
        codes.append(RC.VISUAL_CONTRADICTION)
    if forbidden_hits:
        codes.append(RC.WRONG_DOMAIN)
    if wrong_entity:
        codes.append(RC.WRONG_ENTITY)
    if genericness == "HIGH":
        codes.append(RC.GENERIC_BROLL)
    if visual_role in {"ILLUSTRATION", "GENERIC_CONTEXT"}:
        codes.append(RC.ILLUSTRATIVE_ONLY)
    if visual_role == "EVIDENCE":
        codes.append(RC.EVIDENCE_VISUAL)
    if motion in {"NATURAL_SUBJECT_MOTION", "PROCESS_MOTION", "FAST_MONTAGE"}:
        codes.append(RC.MOTION_PRESENT)

    motion_req = (request.motion_requirement or "").upper()
    if motion_req in {"PROCESS", "PROCESS_MOTION", "NATURAL", "REQUIRED", "MOTION"}:
        if motion in {"STATIC_VIDEO", "MINIMAL_CAMERA_MOTION"}:
            codes.append(RC.MOTION_REQUIRED_BUT_STATIC)

    if entity_ratio is not None and entity_ratio < 0.25 and request.required_entities:
        codes.append(RC.TEMPORAL_WEAK_COVERAGE)
    if concept_ratio is not None and concept_ratio < 0.25:
        codes.append(RC.TEMPORAL_WEAK_COVERAGE)

    # Person provenance support (trusted archive + portrait consistency)
    retrieval = request.retrieval_context or {}
    if (
        retrieval.get("trusted_person_provenance")
        and observation.get("pixels_consistent_with_archival_portrait")
        and request.strict_entity_mode
    ):
        codes.append(RC.PERSON_PROVENANCE_SUPPORTED)
        if entity_al in {"UNKNOWN", "WEAK"}:
            entity_al = "PARTIAL"

    # Decision policy
    decision = RC.DECISION_UNCERTAIN
    reject_hard = False
    accept_ok = False

    if RC.PREVIEW_UNUSABLE in codes or observation.get("preview_unusable"):
        decision = RC.DECISION_UNCERTAIN
        codes.append(RC.PREVIEW_UNUSABLE)
    elif wrong_entity:
        reject_hard = True
    elif meta_conflict and concept_al in {"NONE", "WEAK", "UNKNOWN"}:
        reject_hard = True
    elif RC.VISUAL_CONTRADICTION in codes and concept_al != "STRONG":
        reject_hard = True
    elif RC.CONCEPT_MISMATCH in codes and entity_al in {"NONE", "UNKNOWN", "WEAK"}:
        reject_hard = True
    elif RC.MOTION_REQUIRED_BUT_STATIC in codes:
        reject_hard = True
    elif (
        request.strict_entity_mode
        and request.required_entities
        and entity_al in {"NONE", "UNKNOWN"}
        and RC.PERSON_PROVENANCE_SUPPORTED not in codes
    ):
        # Fail closed for strict entities
        if entity_al == "NONE":
            reject_hard = True
        else:
            decision = RC.DECISION_UNCERTAIN
            codes.append(RC.INSUFFICIENT_VISUAL_EVIDENCE)
    elif (
        request.evidence_requirement.upper()
        in {
            "EVIDENCE",
            "REQUIRED",
            "DOCUMENT",
            "ENTITY_FOOTAGE",
            "AUTHENTIC_CONTEXT",
            "AUTHENTIC_CONTEXT_REQUIRED",
        }
        and visual_role in {"GENERIC_CONTEXT", "ILLUSTRATION", "UNRELATED"}
    ):
        codes.append(RC.ILLUSTRATIVE_ONLY)
        reject_hard = True
    else:
        # Accept only with positive visual support
        entity_ok = (
            not request.required_entities
            or entity_al in {"STRONG", "EXACT"}
            or (
                RC.PERSON_PROVENANCE_SUPPORTED in codes
                and entity_al in {"PARTIAL", "STRONG", "EXACT"}
            )
        )
        # Strict entity: generic category is not enough — unless trusted person provenance
        if request.strict_entity_mode and specificity in {
            "GENERIC_CATEGORY",
            "RELATED_CATEGORY",
            "UNRELATED",
        }:
            if RC.PERSON_PROVENANCE_SUPPORTED in codes and concept_al in {
                "STRONG",
                "EXACT",
                "PARTIAL",
            }:
                entity_ok = True
            elif specificity != "EXACT_ENTITY" and entity_al not in {"EXACT", "STRONG"}:
                entity_ok = False
                if specificity == "GENERIC_CATEGORY":
                    codes.append(RC.GENERIC_BROLL)
                decision = RC.DECISION_UNCERTAIN
                codes.append(RC.INSUFFICIENT_VISUAL_EVIDENCE)

        concept_ok = concept_al in {"STRONG", "EXACT", "PARTIAL"}
        location_ok = (
            not request.required_location
            or location_al in {"STRONG", "EXACT", "PARTIAL"}
        )
        motion_ok = RC.MOTION_REQUIRED_BUT_STATIC not in codes
        temporal_ok = RC.TEMPORAL_WEAK_COVERAGE not in codes or not request.strict_entity_mode

        if (
            entity_ok
            and concept_ok
            and location_ok
            and motion_ok
            and temporal_ok
            and not meta_conflict
            and not forbidden_hits
        ):
            # Still fail closed if alignments are UNKNOWN
            if entity_al == "UNKNOWN" and request.required_entities:
                decision = RC.DECISION_UNCERTAIN
                codes.append(RC.INSUFFICIENT_VISUAL_EVIDENCE)
            elif concept_al == "UNKNOWN":
                decision = RC.DECISION_UNCERTAIN
                codes.append(RC.INSUFFICIENT_VISUAL_EVIDENCE)
            else:
                accept_ok = True

    if reject_hard:
        decision = RC.DECISION_REJECT
    elif accept_ok:
        decision = RC.DECISION_ACCEPT
    elif decision != RC.DECISION_UNCERTAIN:
        decision = RC.DECISION_UNCERTAIN

    # Deduplicate reason codes preserving order
    seen = set()
    uniq_codes = []
    for c in codes:
        if c not in seen:
            seen.add(c)
            uniq_codes.append(c)

    explanation = str(observation.get("explanation_short") or "")[:400]
    if not explanation:
        explanation = f"decision={decision}; entity={entity_al}; concept={concept_al}"

    return VisualVerification(
        verification_id=verification_id,
        candidate_id=request.candidate_id,
        shot_requirement_id="",
        job_id=request.job_id,
        beat_id=request.beat_id,
        shot_id=request.shot_id,
        decision=decision,
        status=decision,
        confidence=conf,
        visible_entities=visible_entities,
        visible_objects=visible_objects,
        visible_actions=visible_actions,
        visible_setting=visible_setting,
        visible_action=", ".join(visible_actions),
        visible_location=str(observation.get("visible_location") or visible_setting),
        visible_text_summary=str(observation.get("visible_text_summary") or ""),
        motion_description=str(observation.get("motion_description") or motion),
        dominant_visual_concept=dominant,
        entity_alignment=entity_al,
        concept_alignment=concept_al,
        action_alignment=action_al,
        location_alignment=location_al,
        entity_specificity=specificity,
        motion_value=motion,
        evidence_value=visual_role,
        authenticity_support=authenticity,
        genericness=genericness,
        contradictions=contradictions,
        forbidden_concept_hits=forbidden_hits,
        metadata_visual_conflict=meta_conflict,
        metadata_supported_claims=list(observation.get("metadata_supported_claims") or []),
        visual_supported_claims=list(observation.get("visual_supported_claims") or []),
        entity_presence_ratio=entity_ratio,
        concept_presence_ratio=concept_ratio,
        reason_codes=uniq_codes,
        explanation_short=explanation,
        supports_narration=decision == RC.DECISION_ACCEPT,
        generic_filler=genericness == "HIGH",
        contradiction=bool(contradictions) or meta_conflict,
        evidence_vs_illustration=visual_role,
        preview_frame_count=preview_frame_count,
        preview_duration_sec=preview_duration_sec,
        prompt_version=RC.PROMPT_VERSION,
        details={"observation": observation, "conflicting_visible_brands": conflicting_brands},
    )
