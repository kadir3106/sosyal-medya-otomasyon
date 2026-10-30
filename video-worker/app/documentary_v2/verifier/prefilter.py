"""Cheap deterministic prefilter before expensive VLM (Phase 2 gate role)."""
from __future__ import annotations

from dataclasses import dataclass

from app.documentary_v2.schemas import MediaCandidate, VisualVerificationRequest


@dataclass
class PrefilterResult:
    accepted: bool
    score: float
    reason: str = ""

    def to_dict(self) -> dict:
        return {"accepted": self.accepted, "score": self.score, "reason": self.reason}


def cheap_prefilter(
    candidate: MediaCandidate,
    request: VisualVerificationRequest,
    *,
    min_score: float = 0.05,
) -> PrefilterResult:
    """Lightweight text overlap — NOT visual truth. Rejects only obvious empty junk."""
    blob = " ".join(
        [
            candidate.query,
            candidate.provenance.source_url,
            candidate.provenance.creator,
            " ".join(request.required_entities),
            request.required_visual_concept,
            request.semantic_domain,
        ]
    ).lower()
    tokens = [
        t
        for t in (request.required_visual_concept + " " + " ".join(request.required_entities))
        .lower()
        .replace(",", " ")
        .split()
        if len(t) > 2
    ]
    if not tokens:
        return PrefilterResult(accepted=True, score=0.5, reason="no_tokens")
    hits = sum(1 for t in tokens if t in blob)
    score = hits / max(len(tokens), 1)
    # Soft: do not drop on weak metadata — Stage C pixels decide
    # Only drop if candidate has zero download/preview path
    if not (candidate.download_url or candidate.preview_url or candidate.provenance.download_url):
        return PrefilterResult(accepted=False, score=0.0, reason="no_media_url")
    return PrefilterResult(
        accepted=True,
        score=max(score, min_score),
        reason="pass_to_visual_verifier",
    )
