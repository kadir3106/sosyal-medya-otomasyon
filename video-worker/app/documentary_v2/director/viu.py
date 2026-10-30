"""VisualInformationUnit — semantic units, not crop/zoom variants."""
from __future__ import annotations

import hashlib

from app.documentary_v2.schemas import (
    MediaCandidate,
    ShotRequirement,
    VisualInformationUnit,
    VisualVerification,
)


def viu_semantic_key(
    *,
    entity: str,
    concept: str,
    action: str,
    evidence_role: str,
    setting: str = "",
) -> str:
    raw = "|".join(
        [
            (entity or "").strip().lower(),
            (concept or "").strip().lower(),
            (action or "").strip().lower(),
            (evidence_role or "").strip().lower(),
            (setting or "").strip().lower()[:40],
        ]
    )
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def build_viu(
    *,
    beat_id: str,
    candidate: MediaCandidate,
    req: ShotRequirement,
    verification: VisualVerification,
) -> VisualInformationUnit:
    entity = (
        (verification.visible_entities[0] if verification.visible_entities else "")
        or (req.required_entities[0] if req.required_entities else "")
    )
    concept = verification.dominant_visual_concept or req.required_visual_concept
    action = (
        verification.visible_actions[0] if verification.visible_actions else ""
    ) or req.action
    evidence = verification.evidence_value or req.evidence_role
    key = viu_semantic_key(
        entity=entity,
        concept=concept,
        action=action,
        evidence_role=evidence,
        setting=verification.visible_setting,
    )
    # Crop/zoom of same content → same key (no path/resolution in key)
    return VisualInformationUnit(
        visual_information_id=f"viu:{key}",
        asset_id=f"asset:{candidate.provenance.provider}:{candidate.provenance.source_id}",
        entity=entity,
        concept=concept,
        action=action,
        evidence_role=evidence,
        media_type=candidate.provenance.media_type,
        authenticity=verification.authenticity_support,
        beat_id=beat_id,
    )


def is_new_viu(viu: VisualInformationUnit, seen_keys: set[str]) -> bool:
    key = viu.visual_information_id.replace("viu:", "")
    return key not in seen_keys
