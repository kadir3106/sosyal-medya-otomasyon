"""Conservative VLM prompt + structured observation schema."""
from __future__ import annotations

import json
from typing import Any

from app.documentary_v2.schemas import VisualPreviewBundle, VisualVerificationRequest
from app.documentary_v2.verifier.reason_codes import PROMPT_VERSION

OBSERVATION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": [
        "visible_entities",
        "visible_objects",
        "visible_setting",
        "dominant_visual_concept",
        "entity_alignment",
        "concept_alignment",
        "action_alignment",
        "location_alignment",
        "entity_specificity",
        "motion_value",
        "visual_role",
        "authenticity_support",
        "genericness",
        "metadata_visual_conflict",
        "visual_supported_claims",
        "metadata_supported_claims",
        "confidence",
        "explanation_short",
    ],
    "properties": {
        "visible_entities": {"type": "array", "items": {"type": "string"}},
        "visible_objects": {"type": "array", "items": {"type": "string"}},
        "visible_actions": {"type": "array", "items": {"type": "string"}},
        "visible_setting": {"type": "string"},
        "visible_location": {"type": "string"},
        "visible_text_summary": {"type": "string"},
        "visible_brand_names": {"type": "array", "items": {"type": "string"}},
        "motion_description": {"type": "string"},
        "dominant_visual_concept": {"type": "string"},
        "entity_alignment": {
            "type": "string",
            "enum": ["NONE", "WEAK", "PARTIAL", "STRONG", "EXACT", "UNKNOWN"],
        },
        "concept_alignment": {
            "type": "string",
            "enum": ["NONE", "WEAK", "PARTIAL", "STRONG", "EXACT", "UNKNOWN"],
        },
        "action_alignment": {
            "type": "string",
            "enum": ["NONE", "WEAK", "PARTIAL", "STRONG", "EXACT", "UNKNOWN"],
        },
        "location_alignment": {
            "type": "string",
            "enum": ["NONE", "WEAK", "PARTIAL", "STRONG", "EXACT", "UNKNOWN"],
        },
        "entity_specificity": {
            "type": "string",
            "enum": [
                "EXACT_ENTITY",
                "RELATED_CATEGORY",
                "GENERIC_CATEGORY",
                "UNRELATED",
                "UNKNOWN",
            ],
        },
        "motion_value": {
            "type": "string",
            "enum": [
                "STATIC_VIDEO",
                "MINIMAL_CAMERA_MOTION",
                "NATURAL_SUBJECT_MOTION",
                "PROCESS_MOTION",
                "FAST_MONTAGE",
                "UNKNOWN_MOTION",
            ],
        },
        "visual_role": {
            "type": "string",
            "enum": [
                "EVIDENCE",
                "AUTHENTIC_CONTEXT",
                "ILLUSTRATION",
                "GENERIC_CONTEXT",
                "UNRELATED",
                "UNKNOWN",
            ],
        },
        "authenticity_support": {
            "type": "string",
            "enum": [
                "AUTHENTIC_ARCHIVE",
                "AUTHENTIC_CURRENT",
                "SOURCE_DOCUMENT",
                "STOCK_ILLUSTRATION",
                "SYNTHETIC",
                "UNKNOWN",
            ],
        },
        "genericness": {
            "type": "string",
            "enum": ["LOW", "MEDIUM", "HIGH", "UNKNOWN"],
        },
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "forbidden_concept_hits": {"type": "array", "items": {"type": "string"}},
        "metadata_visual_conflict": {"type": "boolean"},
        "visual_supported_claims": {"type": "array", "items": {"type": "string"}},
        "metadata_supported_claims": {"type": "array", "items": {"type": "string"}},
        "entity_presence_ratio": {"type": ["number", "null"]},
        "concept_presence_ratio": {"type": ["number", "null"]},
        "pixels_consistent_with_archival_portrait": {"type": "boolean"},
        "preview_unusable": {"type": "boolean"},
        "confidence": {"type": "number"},
        "explanation_short": {"type": "string"},
    },
}


SYSTEM_PROMPT = f"""You are a visual verification judge for documentary media selection.
Prompt version: {PROMPT_VERSION}

RULES:
1. Judge ONLY what is visible in the provided frames/images.
2. Do NOT trust query wording, filenames, or retrieval metadata as visual truth.
3. Metadata is provided separately as retrieval_context — treat it as claims to check, not facts.
4. If metadata claims "Rolex watch" but frames show a river, set metadata_visual_conflict=true
   and visual_supported_claims=[] for the watch claim.
5. Do NOT infer named persons from captions alone. For portraits, you may note
   pixels_consistent_with_archival_portrait without fabricating facial identity.
6. Do NOT call footage EVIDENCE unless the visual itself functions as evidence
   (document, official record, clear primary visual proof). Decorative stock is ILLUSTRATION
   or GENERIC_CONTEXT.
7. Prefer UNKNOWN alignments and lower confidence over hallucination.
8. entity_presence_ratio / concept_presence_ratio: approximate fraction of sampled timeline
   where the entity/concept is visible (0..1). Brief flash in a long montage → low ratio.
9. Put every legible brand/model marking in visible_brand_names. In strict entity mode,
   a different brand or model marking is a contradiction, even when the object category matches.
10. Return ONLY valid JSON matching the schema. No markdown fences.
"""


def build_user_prompt(
    request: VisualVerificationRequest,
    bundle: VisualPreviewBundle,
    *,
    include_schema: bool = True,
    compact: bool = False,
) -> str:
    frame_meta = [
        {"timestamp_sec": f.timestamp_sec, "source": f.source}
        for f in bundle.frames
    ]
    payload = {
        "verification_intent": {
            "required_visual_concept": request.required_visual_concept,
            "semantic_domain": request.semantic_domain,
            "narrative_role": request.narrative_role,
            "required_entities": request.required_entities,
            "optional_entities": request.optional_entities,
            "required_action": request.required_action,
            "required_location": request.required_location,
            "motion_requirement": request.motion_requirement,
            "evidence_requirement": request.evidence_requirement,
            "authenticity_requirement": request.authenticity_requirement,
            "forbidden_visual_concepts": request.forbidden_visual_concepts,
            "strict_entity_mode": request.strict_entity_mode,
            "context_narration": request.context_narration,
        },
        "retrieval_context_NOT_visual_truth": request.retrieval_context,
        "preview": {
            "media_kind": bundle.media_kind,
            "duration_sec": bundle.duration_sec,
            "frame_count": len(bundle.frames),
            "frames": frame_meta,
            "technical": bundle.technical,
        },
    }
    if include_schema and not compact:
        payload["output_schema"] = OBSERVATION_SCHEMA
    if compact:
        return (
            "Analyze attached frames. Judge ONLY visible pixels. "
            "Do not trust retrieval_context as visual truth. "
            "If metadata claims a watch but frames show water/river, set "
            "metadata_visual_conflict=true and concept/entity alignments to NONE. "
            "Return JSON for the response schema only.\n"
            + json.dumps(payload, ensure_ascii=False)
        )
    return (
        "Analyze the attached frame images. Return JSON only.\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
    )


def validate_observation(data: dict) -> tuple[bool, str]:
    if not isinstance(data, dict):
        return False, "not_object"
    for key in OBSERVATION_SCHEMA["required"]:
        if key not in data:
            return False, f"missing:{key}"
    for field, enum_key in (
        ("entity_alignment", "entity_alignment"),
        ("concept_alignment", "concept_alignment"),
        ("genericness", "genericness"),
        ("visual_role", "visual_role"),
    ):
        allowed = OBSERVATION_SCHEMA["properties"][enum_key]["enum"]
        if str(data.get(field, "")).upper() not in allowed:
            # soft-normalize later; still require presence
            pass
    return True, ""


def parse_json_response(text: str) -> dict:
    import re

    raw = (text or "").strip()
    # Reasoning contamination must not reach JSON parser
    raw = re.sub(r"<think>[\s\S]*?</think>", "", raw, flags=re.I).strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.startswith("json"):
            raw = raw[4:].strip()
    # Extract outermost object if model wrapped text
    if raw and not raw.startswith("{"):
        start = raw.find("{")
        end = raw.rfind("}")
        if start >= 0 and end > start:
            raw = raw[start : end + 1]
    return json.loads(raw)
