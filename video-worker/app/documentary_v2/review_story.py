"""Prepare an evidence-bound story from the exact final narration."""
from __future__ import annotations

from dataclasses import dataclass, field

from app.fact_verify import FactVerificationProvider
from app.script_claims import extract_claims
from app.script_gen import generate_script
from app.script_quality import refine_script
from app.documentary_v2.schemas import VerifiedClaim, VerifiedStory


@dataclass
class PreparedStory:
    story: VerifiedStory
    claims: list[VerifiedClaim]
    title: str
    gates: dict[str, str]
    reasons: list[str] = field(default_factory=list)


def prepare_review_story(
    topic: str, api_key: str, *, verifier: FactVerificationProvider | None = None
) -> PreparedStory:
    topic = topic.strip()
    if not topic:
        raise ValueError("topic is empty")
    verifier = verifier or FactVerificationProvider()
    draft = generate_script(topic, api_key, style="documentary_review")
    quality = refine_script(draft["script"], topic=topic, verifier=verifier)
    final = quality.final_script.strip()
    if not final:
        raise ValueError("verified script is empty")

    factual = [c for c in extract_claims(final, topic=topic) if c.verification_required]
    results = {v.claim_id: v for v in verifier.verify_claims(factual, topic=topic)}
    claims: list[VerifiedClaim] = []
    for claim in factual:
        result = results.get(claim.claim_id)
        status = result.status if result else "unknown"
        sources = list(result.sources) if result else []
        if claim.risk == "HIGH" and (status != "supported" or not sources):
            raise ValueError(f"unresolved high-risk final claim: {claim.claim_id}")
        claims.append(
            VerifiedClaim(claim.claim_id, claim.text, claim.claim_type, claim.risk, status, sources)
        )

    gates = {
        "FactQualityGate": "PASS" if factual and all(c.status == "supported" and c.evidence for c in claims) else "REVIEW_REQUIRED",
        "StoryQualityGate": "PASS" if not quality.review_required and not quality.quality_checks.get("story_flags") and not quality.quality_checks.get("linguistic_issues") else "REVIEW_REQUIRED",
        "StoryConsistencyGate": str(quality.story_consistency.get("status") or "NOT_RUN"),
    }
    story = VerifiedStory(
        f"story:{topic}", topic, draft["script"], final,
        hook=quality.hook, claim_ids=[c.claim_id for c in claims],
    )
    return PreparedStory(story, claims, str(draft["title"]), gates)
