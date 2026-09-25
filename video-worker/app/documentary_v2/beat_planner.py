"""Convert final narration to validated, evidence-linked visual beats."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.documentary_v2.schemas import StoryBeat, VerifiedClaim
from app.script_gen import _call_llm_with_fallback


@dataclass
class BeatPlan:
    beats: list[StoryBeat]
    gate: str
    reasons: list[str]


def _exact_spans(script: str, spans: list[str]) -> bool:
    cursor = 0
    for span in spans:
        if not span:
            return False
        start = script.find(span, cursor)
        if start < 0 or script[cursor:start].strip():
            return False
        cursor = start + len(span)
    return bool(spans) and not script[cursor:].strip()


def _claim_ids(span: str, claims: list[VerifiedClaim]) -> list[str]:
    return [claim.claim_id for claim in claims if claim.text == span]


def _fallback_beats(script: str, claims: list[VerifiedClaim]) -> BeatPlan:
    spans = [span for span in re.split(r"(?<=[.!?])\s+", script.strip()) if span]
    beats = [
        StoryBeat(
            beat_id=f"beat:{index}", spoken_span=span,
            narrative_role="development", semantic_domain="unknown",
            required_visual_concept=span, claim_ids=_claim_ids(span, claims),
            importance="important",
        )
        for index, span in enumerate(spans)
    ]
    return BeatPlan(beats, "REVIEW_REQUIRED", ["structured_beat_plan_unavailable"])


def plan_beats(topic: str, script: str, claims: list[VerifiedClaim], api_key: str) -> BeatPlan:
    if not script.strip():
        raise ValueError("final script is empty")
    prompt = (
        "Plan visual beats for a mini-documentary. Return JSON with a beats array. "
        "Each beat must have an exact contiguous spoken_span copied from the script, "
        "narrative_role, primary_entities, semantic_domain, visual_purpose, "
        "required_visual_concept, motion_requirement, and evidence_requirement. "
        "Do not add entities or alter/drop narration. Do not infer evidence. "
        f"Topic: {topic}\nScript: {script}"
    )
    try:
        content, _ = _call_llm_with_fallback([{"role": "user", "content": prompt}], api_key)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.DOTALL)
        rows = json.loads(cleaned)["beats"]
        if not isinstance(rows, list):
            raise ValueError("beat list missing")
        spans = [row["spoken_span"] for row in rows]
        if not _exact_spans(script, spans):
            raise ValueError("beat spans do not cover final script")
        beats = []
        for index, row in enumerate(rows):
            span = spans[index]
            entities = row.get("primary_entities") or []
            if not isinstance(entities, list) or any(
                not isinstance(entity, str) or entity.lower() not in f"{topic} {span}".lower()
                for entity in entities
            ):
                raise ValueError("beat invented an entity")
            beats.append(
                StoryBeat(
                    beat_id=f"beat:{index}", spoken_span=span,
                    narrative_role=str(row.get("narrative_role") or "development"),
                    primary_entities=entities,
                    semantic_domain=str(row.get("semantic_domain") or "unknown"),
                    visual_purpose=str(row.get("visual_purpose") or ""),
                    required_visual_concept=str(row.get("required_visual_concept") or span),
                    motion_requirement=str(row.get("motion_requirement") or ""),
                    evidence_requirement=str(row.get("evidence_requirement") or ""),
                    claim_ids=_claim_ids(span, claims), importance="important",
                )
            )
        return BeatPlan(beats, "PASS", [])
    except (KeyError, TypeError, ValueError, IndexError, RuntimeError):
        return _fallback_beats(script, claims)
