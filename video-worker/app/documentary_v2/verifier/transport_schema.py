"""Provider-safe JSON schemas for Groq structured vision (transport only).

Canonical domain model remains OBSERVATION_SCHEMA / VisualVerification.
Transport schemas avoid null-unions / optional holes that break strict-ish JSON schema.
"""
from __future__ import annotations

from typing import Any

# Probe A canary — tiny schema
CANARY_OBJECT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "contains_watch": {"type": "boolean"},
        "contains_river": {"type": "boolean"},
        "contains_bakery": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": [
        "contains_watch",
        "contains_river",
        "contains_bakery",
        "summary",
    ],
    "additionalProperties": False,
}

# Probe B — three-frame temporal
TEMPORAL_TINY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "dominant_content": {"type": "string"},
        "relevant_frame_indices": {
            "type": "array",
            "items": {"type": "integer"},
        },
        "contradictions": {
            "type": "array",
            "items": {"type": "string"},
        },
        "decision": {
            "type": "string",
            "enum": ["ACCEPT", "REJECT", "UNCERTAIN"],
        },
    },
    "required": [
        "dominant_content",
        "relevant_frame_indices",
        "contradictions",
        "decision",
    ],
    "additionalProperties": False,
}

_ALIGN_ENUM = ["NONE", "WEAK", "PARTIAL", "STRONG", "EXACT", "UNKNOWN"]
_SPEC_ENUM = [
    "EXACT_ENTITY",
    "RELATED_CATEGORY",
    "GENERIC_CATEGORY",
    "UNRELATED",
    "UNKNOWN",
]
_MOTION_ENUM = [
    "STATIC_VIDEO",
    "MINIMAL_CAMERA_MOTION",
    "NATURAL_SUBJECT_MOTION",
    "PROCESS_MOTION",
    "FAST_MONTAGE",
    "UNKNOWN_MOTION",
]
_ROLE_ENUM = [
    "EVIDENCE",
    "AUTHENTIC_CONTEXT",
    "ILLUSTRATION",
    "GENERIC_CONTEXT",
    "UNRELATED",
    "UNKNOWN",
]
_AUTH_ENUM = [
    "AUTHENTIC_ARCHIVE",
    "AUTHENTIC_CURRENT",
    "SOURCE_DOCUMENT",
    "STOCK_ILLUSTRATION",
    "SYNTHETIC",
    "UNKNOWN",
]
_GENERIC_ENUM = ["LOW", "MEDIUM", "HIGH", "UNKNOWN"]

# Full visual verification — provider transport (no null unions)
VISUAL_TRANSPORT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "visible_entities": {"type": "array", "items": {"type": "string"}},
        "visible_objects": {"type": "array", "items": {"type": "string"}},
        "visible_actions": {"type": "array", "items": {"type": "string"}},
        "visible_setting": {"type": "string"},
        "visible_location": {"type": "string"},
        "visible_text_summary": {"type": "string"},
        "motion_description": {"type": "string"},
        "dominant_visual_concept": {"type": "string"},
        "entity_alignment": {"type": "string", "enum": _ALIGN_ENUM},
        "concept_alignment": {"type": "string", "enum": _ALIGN_ENUM},
        "action_alignment": {"type": "string", "enum": _ALIGN_ENUM},
        "location_alignment": {"type": "string", "enum": _ALIGN_ENUM},
        "entity_specificity": {"type": "string", "enum": _SPEC_ENUM},
        "motion_value": {"type": "string", "enum": _MOTION_ENUM},
        "visual_role": {"type": "string", "enum": _ROLE_ENUM},
        "authenticity_support": {"type": "string", "enum": _AUTH_ENUM},
        "genericness": {"type": "string", "enum": _GENERIC_ENUM},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "forbidden_concept_hits": {"type": "array", "items": {"type": "string"}},
        "metadata_visual_conflict": {"type": "boolean"},
        "visual_supported_claims": {"type": "array", "items": {"type": "string"}},
        "metadata_supported_claims": {"type": "array", "items": {"type": "string"}},
        "entity_presence_ratio": {"type": "number"},
        "concept_presence_ratio": {"type": "number"},
        "pixels_consistent_with_archival_portrait": {"type": "boolean"},
        "preview_unusable": {"type": "boolean"},
        "confidence": {"type": "number"},
        "explanation_short": {"type": "string"},
    },
    "required": [
        "visible_entities",
        "visible_objects",
        "visible_actions",
        "visible_setting",
        "visible_location",
        "visible_text_summary",
        "motion_description",
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
        "contradictions",
        "forbidden_concept_hits",
        "metadata_visual_conflict",
        "visual_supported_claims",
        "metadata_supported_claims",
        "entity_presence_ratio",
        "concept_presence_ratio",
        "pixels_consistent_with_archival_portrait",
        "preview_unusable",
        "confidence",
        "explanation_short",
    ],
    "additionalProperties": False,
}


def response_format_json_schema(
    schema: dict[str, Any],
    *,
    name: str = "visual_result",
    strict: bool = True,
) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": strict,
            "schema": schema,
        },
    }


def response_format_json_object() -> dict[str, Any]:
    return {"type": "json_object"}


def transport_to_observation(data: dict[str, Any]) -> dict[str, Any]:
    """Normalize transport JSON into canonical observation dict."""
    out = dict(data)
    # Drop internal keys
    out.pop("_temporal", None)
    for k in (
        "entity_presence_ratio",
        "concept_presence_ratio",
        "confidence",
    ):
        if k in out and out[k] is None:
            out[k] = 0.0
    for k in (
        "pixels_consistent_with_archival_portrait",
        "preview_unusable",
        "metadata_visual_conflict",
    ):
        if k not in out:
            out[k] = False
    for k in (
        "visible_entities",
        "visible_objects",
        "visible_actions",
        "contradictions",
        "forbidden_concept_hits",
        "visual_supported_claims",
        "metadata_supported_claims",
    ):
        if k not in out or out[k] is None:
            out[k] = []
    return out
