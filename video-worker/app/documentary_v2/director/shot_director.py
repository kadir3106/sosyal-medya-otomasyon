"""Map StoryBeat → explicit ShotRequirement(s). Story decides visuals."""
from __future__ import annotations

import re
from typing import Iterable

from app.documentary_v2.schemas import ShotRequirement, StoryBeat, VerifiedStory

IMPORTANT_ROLES = frozenset(
    {
        "HOOK",
        "ORIGIN",
        "PERSON",
        "REVEAL",
        "CORE_REVEAL",
        "EVIDENCE",
        "CONTRAST",
        "PAYOFF",
        "OWNERSHIP",
        "PROCESS",
        "LOCATION",
    }
)


def _role(raw: str) -> str:
    return (raw or "").strip().upper().replace(" ", "_")


def _importance(beat: StoryBeat) -> str:
    role = _role(beat.narrative_role)
    if role in IMPORTANT_ROLES or beat.story_function.upper() in IMPORTANT_ROLES:
        return "important"
    if role in {"SETUP", "CONTEXT", "DEVELOPMENT"}:
        return "supporting"
    return "supporting"


def _visual_purpose(beat: StoryBeat) -> str:
    explicit = (beat.visual_purpose or "").upper()
    if explicit in {
        "IDENTIFY_ENTITY", "SHOW_PERSON", "SHOW_PRODUCT", "SHOW_EVIDENCE",
        "SHOW_PROCESS", "SHOW_LOCATION", "EXPLAIN_RELATIONSHIP",
        "ESTABLISH_CONTEXT", "CREATE_PAYOFF",
    }:
        return explicit
    role = _role(beat.narrative_role)
    domain = (beat.semantic_domain or "").lower()
    concept = (beat.required_visual_concept or "").lower()
    ev = (beat.evidence_requirement or "").lower()
    if role in {"PERSON", "ORIGIN"} or "portrait" in concept or "founder" in concept:
        return "SHOW_PERSON"
    # Ownership / relationship → explanatory graphic path, NOT document-hunt SHOW_EVIDENCE
    if (
        role in {"OWNERSHIP"}
        or "ownership" in domain
        or "relation" in concept
        or "foundation owns" in concept
    ):
        return "EXPLAIN_RELATIONSHIP"
    if role in {"EVIDENCE"} or "evidence" in ev:
        if "ownership" in domain or "own" in concept:
            return "EXPLAIN_RELATIONSHIP"
        return "SHOW_EVIDENCE"
    if role == "PROCESS" or "manufactur" in concept or "assembly" in concept or "craft" in concept:
        return "SHOW_PROCESS"
    if role == "LOCATION" or "geneva" in concept or "city" in concept or "switzerland" in concept:
        return "SHOW_LOCATION"
    if "product" in concept or "watch" in concept or "crown" in concept or role == "REVEAL":
        return "SHOW_PRODUCT"
    if role == "HOOK":
        return "IDENTIFY_ENTITY"
    if role == "PAYOFF":
        return "CREATE_PAYOFF"
    return "ESTABLISH_CONTEXT"


def _evidence_role(beat: StoryBeat, purpose: str) -> str:
    ev = (beat.evidence_requirement or "").upper()
    if ev in {"EVIDENCE", "REQUIRED", "DOCUMENT", "EVIDENCE_REQUIRED"}:
        return "EVIDENCE_REQUIRED"
    if purpose == "SHOW_EVIDENCE":
        return "EVIDENCE_REQUIRED"
    if purpose == "EXPLAIN_RELATIONSHIP":
        return "EVIDENCE_REQUIRED"
    if purpose == "SHOW_PERSON" and _importance(beat) == "important":
        return "AUTHENTIC_CONTEXT_REQUIRED"
    if purpose in {"SHOW_PROCESS", "SHOW_PRODUCT", "SHOW_LOCATION", "IDENTIFY_ENTITY", "CREATE_PAYOFF"}:
        return "ILLUSTRATION_ACCEPTABLE"
    if purpose == "ESTABLISH_CONTEXT":
        return "ILLUSTRATION_ACCEPTABLE"
    return "DECORATIVE_NOT_ALLOWED"


def _motion(beat: StoryBeat, purpose: str) -> str:
    raw = (beat.motion_requirement or "").upper()
    if raw in {"REQUIRED", "PREFERRED", "OPTIONAL", "NOT_NEEDED"}:
        return raw
    if purpose == "SHOW_PROCESS":
        return "REQUIRED"
    if purpose in {"SHOW_LOCATION", "SHOW_PRODUCT"}:
        return "PREFERRED"
    if purpose in {"SHOW_PERSON", "SHOW_EVIDENCE", "EXPLAIN_RELATIONSHIP"}:
        return "NOT_NEEDED"
    return "OPTIONAL"


def _strict(beat: StoryBeat, purpose: str) -> bool:
    if purpose in {"SHOW_PERSON", "SHOW_EVIDENCE", "IDENTIFY_ENTITY"}:
        return True
    if purpose == "EXPLAIN_RELATIONSHIP":
        return False  # relationship often recovered via verified graphic
    if purpose == "SHOW_PROCESS":
        # Process B-roll may be authentic craft without brand logo on every frame
        return False
    if purpose in {"SHOW_PRODUCT", "CREATE_PAYOFF"} and beat.primary_entities and _importance(beat) == "important":
        return True
    return False


def _media_types(purpose: str, motion: str) -> list[str]:
    if purpose == "SHOW_PERSON":
        return ["archive_still", "stock_photo"]
    if purpose == "SHOW_EVIDENCE":
        return ["document", "archive_still", "motion_graphic"]
    if purpose == "EXPLAIN_RELATIONSHIP":
        # Prefer real context video first; motion graphic is recovery, not first search
        return ["stock_video", "stock_photo", "motion_graphic"]
    if purpose == "SHOW_PROCESS" or motion == "REQUIRED":
        return ["stock_video", "archive_video"]
    if purpose == "SHOW_LOCATION":
        return ["stock_video", "stock_photo"]
    if purpose in {"IDENTIFY_ENTITY", "SHOW_PRODUCT", "CREATE_PAYOFF", "ESTABLISH_CONTEXT"}:
        return ["stock_video", "stock_photo"]
    return ["stock_video", "stock_photo"]


def _forbidden(beat: StoryBeat, purpose: str) -> list[str]:
    base = list(beat.forbidden_visual_concepts or [])
    # Never encode Rolex-specific bans — domain-generic decorative fillers
    if purpose == "SHOW_EVIDENCE":
        base.extend(["generic luxury lifestyle", "champagne", "sports car", "penthouse"])
    return list(dict.fromkeys(base))


class DocumentaryShotDirector:
    """Professional-editor intent: what SHOULD be shown for this beat."""

    def plan_shots(
        self,
        story: VerifiedStory | None,
        beats: Iterable[StoryBeat],
    ) -> list[ShotRequirement]:
        out: list[ShotRequirement] = []
        for beat in beats:
            out.append(self.plan_shot_for_beat(story, beat))
        return out

    def plan_shot_for_beat(
        self,
        story: VerifiedStory | None,
        beat: StoryBeat,
    ) -> ShotRequirement:
        purpose = _visual_purpose(beat)
        evidence = _evidence_role(beat, purpose)
        motion = _motion(beat, purpose)
        entities = list(beat.primary_entities or [])
        concept = (
            beat.required_visual_concept
            or " ".join(entities)
            or beat.spoken_span[:80]
            or "scene"
        )
        # Reject vague fluff as sole concept
        vague = {"business footage", "luxury visual", "money visual", "cinematic"}
        if concept.strip().lower() in vague:
            concept = " ".join(entities) or beat.semantic_domain or concept

        subject = entities[0] if entities else (concept.split()[0] if concept else "")
        types = list(beat.preferred_media_types) if beat.preferred_media_types else _media_types(purpose, motion)
        importance = (
            beat.importance
            if beat.importance in {"important", "supporting", "fragment"}
            else _importance(beat)
        )
        # Process craft footage may be authentic without brand logo on every frame
        if purpose == "SHOW_PROCESS":
            req_entities: list[str] = []
            opt_entities = list(entities) + list(beat.secondary_entities or [])
        else:
            req_entities = list(entities)
            opt_entities = list(beat.secondary_entities or [])

        loc = ""
        concept_l = (concept or "").lower()
        if "swiss" in concept_l or "switzerland" in concept_l or "geneva" in concept_l:
            loc = "Switzerland"

        return ShotRequirement(
            shot_requirement_id=f"shotreq:{beat.beat_id}",
            beat_id=beat.beat_id,
            subject=subject,
            action=beat.story_function or purpose,
            location=loc,
            time_context="",
            required_entities=req_entities,
            optional_entities=opt_entities,
            required_visual_concept=concept,
            visual_purpose=purpose,
            evidence_role=evidence,
            preferred_media_type=types[0] if types else "",
            preferred_media_types=types,
            motion_requirement=motion,
            authenticity_requirement=beat.authenticity_requirement
            or ("AUTHENTIC_ARCHIVE" if purpose == "SHOW_PERSON" else ""),
            strict_entity_mode=_strict(beat, purpose),
            generation_allowed=purpose in {"EXPLAIN_RELATIONSHIP", "SHOW_EVIDENCE", "ESTABLISH_CONTEXT"},
            forbidden_visual_concepts=_forbidden(beat, purpose),
            search_intents=[],  # filled by query compiler
            fallback_ladder=["exact", "context", "archive", "motion_graphic", "generated", "review"],
            fallback_policy="no_generic_filler",
            avoid_concepts=list(beat.forbidden_visual_concepts or []),
            semantic_domain=beat.semantic_domain,
            narrative_role=beat.narrative_role,
            estimated_duration=beat.estimated_duration,
            importance=importance,
            claim_ids=list(beat.claim_ids or []),
        )
