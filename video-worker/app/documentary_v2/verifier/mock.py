"""Mock VisualVerifier — for offline unit tests / fixtures. Not production truth."""
from __future__ import annotations

from typing import Any

from app.documentary_v2.schemas import VisualPreviewBundle, VisualVerificationRequest
from app.documentary_v2.verifier.base import VisualVerifierProvider


class MockVisualVerifier(VisualVerifierProvider):
    """Returns a preloaded observation or derives a simple heuristic from request tags."""

    name = "mock"
    model = "mock-v1"

    def __init__(self, observation: dict | None = None, error: str | None = None) -> None:
        self.observation = observation
        self.error = error
        self.calls = 0

    def observe(
        self,
        request: VisualVerificationRequest,
        bundle: VisualPreviewBundle,
    ) -> dict[str, Any]:
        self.calls += 1
        if self.error:
            raise RuntimeError(self.error)
        if self.observation is not None:
            return dict(self.observation)
        # Fixture path tags in retrieval_context for tests
        tag = (request.retrieval_context or {}).get("fixture_tag") or ""
        return _observation_for_tag(tag, request, bundle)


def _observation_for_tag(
    tag: str,
    request: VisualVerificationRequest,
    bundle: VisualPreviewBundle,
) -> dict:
    motion = (bundle.technical or {}).get("motion_estimate") or "UNKNOWN_MOTION"
    if tag == "river_as_rolex":
        return {
            "visible_entities": [],
            "visible_objects": ["river", "rocks", "water"],
            "visible_actions": ["flowing"],
            "visible_setting": "rocky river outdoors",
            "visible_location": "wilderness river",
            "visible_text_summary": "",
            "motion_description": "water motion",
            "dominant_visual_concept": "river landscape",
            "entity_alignment": "NONE",
            "concept_alignment": "NONE",
            "action_alignment": "NONE",
            "location_alignment": "NONE",
            "entity_specificity": "UNRELATED",
            "motion_value": "NATURAL_SUBJECT_MOTION",
            "visual_role": "UNRELATED",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "HIGH",
            "contradictions": ["requested watch product; visible river"],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": True,
            "visual_supported_claims": [],
            "metadata_supported_claims": list(
                (request.retrieval_context or {}).get("metadata_claims") or ["rolex watch luxury"]
            ),
            "entity_presence_ratio": 0.0,
            "concept_presence_ratio": 0.0,
            "confidence": 0.92,
            "explanation_short": "Frames show river/rocks; no watch visible despite metadata.",
        }
    if tag == "bakery_as_rolex":
        return {
            "visible_entities": [],
            "visible_objects": ["bread", "bakery counter"],
            "visible_actions": ["baking"],
            "visible_setting": "bakery interior",
            "visible_location": "bakery",
            "visible_text_summary": "",
            "motion_description": "kitchen activity",
            "dominant_visual_concept": "bakery",
            "entity_alignment": "NONE",
            "concept_alignment": "NONE",
            "action_alignment": "NONE",
            "location_alignment": "NONE",
            "entity_specificity": "UNRELATED",
            "motion_value": "NATURAL_SUBJECT_MOTION",
            "visual_role": "UNRELATED",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "HIGH",
            "contradictions": ["requested watch; visible bakery"],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": True,
            "visual_supported_claims": [],
            "metadata_supported_claims": ["rolex"],
            "entity_presence_ratio": 0.0,
            "concept_presence_ratio": 0.0,
            "confidence": 0.9,
            "explanation_short": "Bakery visible; no watch.",
        }
    if tag == "actual_watch":
        return {
            "visible_entities": ["wristwatch"],
            "visible_objects": ["luxury chronograph watch", "metal bracelet"],
            "visible_actions": ["static product display"],
            "visible_setting": "studio product shot",
            "visible_location": "",
            "visible_text_summary": "",
            "motion_description": "slight camera move",
            "dominant_visual_concept": "wristwatch product",
            "entity_alignment": "STRONG",
            "concept_alignment": "STRONG",
            "action_alignment": "PARTIAL",
            "location_alignment": "UNKNOWN",
            "entity_specificity": "RELATED_CATEGORY",
            "motion_value": "MINIMAL_CAMERA_MOTION",
            "visual_role": "ILLUSTRATION",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "LOW",
            "contradictions": [],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": False,
            "visual_supported_claims": ["wristwatch visible"],
            "metadata_supported_claims": [],
            "entity_presence_ratio": 0.95,
            "concept_presence_ratio": 0.95,
            "confidence": 0.88,
            "explanation_short": "Clear wristwatch product visible across frames.",
        }
    if tag == "watch_sparse_metadata":
        return {
            "visible_entities": ["wristwatch"],
            "visible_objects": ["watch dial", "hands"],
            "visible_actions": [],
            "visible_setting": "close-up watch",
            "visible_location": "",
            "visible_text_summary": "",
            "motion_description": "static",
            "dominant_visual_concept": "watch close-up",
            "entity_alignment": "STRONG",
            "concept_alignment": "EXACT",
            "action_alignment": "UNKNOWN",
            "location_alignment": "UNKNOWN",
            "entity_specificity": "RELATED_CATEGORY",
            "motion_value": "STATIC_VIDEO",
            "visual_role": "ILLUSTRATION",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "LOW",
            "contradictions": [],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": False,
            "visual_supported_claims": ["watch product visible"],
            "metadata_supported_claims": [],
            "entity_presence_ratio": 1.0,
            "concept_presence_ratio": 1.0,
            "confidence": 0.85,
            "explanation_short": "Watch clearly visible despite sparse metadata.",
        }
    if tag == "temporal_flash":
        return {
            "visible_entities": ["wristwatch"],
            "visible_objects": ["watch briefly", "city traffic", "crowd"],
            "visible_actions": ["montage"],
            "visible_setting": "mixed montage",
            "visible_location": "city",
            "visible_text_summary": "",
            "motion_description": "fast cuts",
            "dominant_visual_concept": "city montage",
            "entity_alignment": "WEAK",
            "concept_alignment": "WEAK",
            "action_alignment": "NONE",
            "location_alignment": "PARTIAL",
            "entity_specificity": "UNRELATED",
            "motion_value": "FAST_MONTAGE",
            "visual_role": "GENERIC_CONTEXT",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "HIGH",
            "contradictions": [],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": False,
            "visual_supported_claims": ["brief watch flash"],
            "metadata_supported_claims": [],
            "entity_presence_ratio": 0.06,
            "concept_presence_ratio": 0.06,
            "confidence": 0.8,
            "explanation_short": "Watch appears only briefly; majority unrelated.",
        }
    if tag == "static_process":
        return {
            "visible_entities": [],
            "visible_objects": ["watch"],
            "visible_actions": [],
            "visible_setting": "still photo encoded as video",
            "visible_location": "",
            "visible_text_summary": "",
            "motion_description": "no subject motion",
            "dominant_visual_concept": "static watch photo",
            "entity_alignment": "PARTIAL",
            "concept_alignment": "PARTIAL",
            "action_alignment": "NONE",
            "location_alignment": "UNKNOWN",
            "entity_specificity": "RELATED_CATEGORY",
            "motion_value": "STATIC_VIDEO",
            "visual_role": "ILLUSTRATION",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "MEDIUM",
            "contradictions": [],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": False,
            "visual_supported_claims": ["static watch image"],
            "metadata_supported_claims": [],
            "entity_presence_ratio": 1.0,
            "concept_presence_ratio": 1.0,
            "confidence": 0.8,
            "explanation_short": "Static still; no manufacturing process motion.",
        }
    if tag == "generic_market_ownership":
        return {
            "visible_entities": [],
            "visible_objects": ["stock ticker", "trading floor"],
            "visible_actions": ["trading"],
            "visible_setting": "generic stock exchange",
            "visible_location": "",
            "visible_text_summary": "",
            "motion_description": "market activity",
            "dominant_visual_concept": "generic financial market",
            "entity_alignment": "NONE",
            "concept_alignment": "WEAK",
            "action_alignment": "PARTIAL",
            "location_alignment": "UNKNOWN",
            "entity_specificity": "GENERIC_CATEGORY",
            "motion_value": "NATURAL_SUBJECT_MOTION",
            "visual_role": "GENERIC_CONTEXT",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "HIGH",
            "contradictions": [],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": False,
            "visual_supported_claims": ["generic market footage"],
            "metadata_supported_claims": ["ownership"],
            "entity_presence_ratio": 0.0,
            "concept_presence_ratio": 0.2,
            "confidence": 0.75,
            "explanation_short": "Generic market B-roll; not ownership evidence.",
        }
    if tag == "person_archive":
        return {
            "visible_entities": ["historical person portrait"],
            "visible_objects": ["portrait photograph", "suit"],
            "visible_actions": [],
            "visible_setting": "archival portrait",
            "visible_location": "",
            "visible_text_summary": "",
            "motion_description": "static",
            "dominant_visual_concept": "archival portrait",
            "entity_alignment": "PARTIAL",
            "concept_alignment": "STRONG",
            "action_alignment": "UNKNOWN",
            "location_alignment": "UNKNOWN",
            "entity_specificity": "RELATED_CATEGORY",
            "motion_value": "STATIC_VIDEO",
            "visual_role": "AUTHENTIC_CONTEXT",
            "authenticity_support": "AUTHENTIC_ARCHIVE",
            "genericness": "LOW",
            "contradictions": [],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": False,
            "visual_supported_claims": ["archival portrait of a person"],
            "metadata_supported_claims": ["named person from file page"],
            "entity_presence_ratio": 1.0,
            "concept_presence_ratio": 1.0,
            "pixels_consistent_with_archival_portrait": True,
            "confidence": 0.7,
            "explanation_short": "Archival portrait consistent; identity via provenance not face ID.",
        }
    if tag == "anonymous_office_founder":
        return {
            "visible_entities": [],
            "visible_objects": ["office workers", "laptops"],
            "visible_actions": ["working"],
            "visible_setting": "modern office",
            "visible_location": "office",
            "visible_text_summary": "",
            "motion_description": "office activity",
            "dominant_visual_concept": "generic office",
            "entity_alignment": "NONE",
            "concept_alignment": "NONE",
            "action_alignment": "NONE",
            "location_alignment": "NONE",
            "entity_specificity": "UNRELATED",
            "motion_value": "NATURAL_SUBJECT_MOTION",
            "visual_role": "UNRELATED",
            "authenticity_support": "STOCK_ILLUSTRATION",
            "genericness": "HIGH",
            "contradictions": ["requested historical founder; modern office"],
            "forbidden_concept_hits": [],
            "metadata_visual_conflict": True,
            "visual_supported_claims": [],
            "metadata_supported_claims": ["founder"],
            "entity_presence_ratio": 0.0,
            "concept_presence_ratio": 0.0,
            "confidence": 0.86,
            "explanation_short": "Modern anonymous office; no founder portrait.",
        }
    # default uncertain
    return {
        "visible_entities": [],
        "visible_objects": [],
        "visible_actions": [],
        "visible_setting": "unclear",
        "visible_location": "",
        "visible_text_summary": "",
        "motion_description": motion,
        "dominant_visual_concept": "unknown",
        "entity_alignment": "UNKNOWN",
        "concept_alignment": "UNKNOWN",
        "action_alignment": "UNKNOWN",
        "location_alignment": "UNKNOWN",
        "entity_specificity": "UNKNOWN",
        "motion_value": motion if isinstance(motion, str) else "UNKNOWN_MOTION",
        "visual_role": "UNKNOWN",
        "authenticity_support": "UNKNOWN",
        "genericness": "UNKNOWN",
        "contradictions": [],
        "forbidden_concept_hits": [],
        "metadata_visual_conflict": False,
        "visual_supported_claims": [],
        "metadata_supported_claims": [],
        "entity_presence_ratio": None,
        "concept_presence_ratio": None,
        "confidence": 0.2,
        "explanation_short": "Insufficient visual determination.",
    }
