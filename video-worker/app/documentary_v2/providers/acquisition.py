"""Candidate acquisition orchestrator — SEARCH only, no semantic accept, no random fallback."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.documentary_v2.providers.base import MediaProvider
from app.documentary_v2.providers.dedup import dedupe_candidates
from app.documentary_v2.providers.materialize import materialize_candidate
from app.documentary_v2.providers.registry import MediaProviderRegistry, default_registry
from app.documentary_v2.schemas import (
    AcquisitionCounts,
    AttributionEntry,
    DuplicateRelation,
    MediaAsset,
    MediaCandidate,
    MediaSearchRequest,
    PreviewReference,
    ProviderCapability,
    ProviderHealth,
    ProviderSearchEvent,
)


@dataclass
class AcquisitionResult:
    request: MediaSearchRequest
    candidates: list[MediaCandidate] = field(default_factory=list)
    unique_candidates: list[MediaCandidate] = field(default_factory=list)
    relations: list[DuplicateRelation] = field(default_factory=list)
    counts: AcquisitionCounts = field(default_factory=AcquisitionCounts)
    events: list[ProviderSearchEvent] = field(default_factory=list)
    previews: list[PreviewReference] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "request": self.request.to_dict(),
            "candidates": [c.to_dict() for c in self.candidates],
            "unique_candidates": [c.to_dict() for c in self.unique_candidates],
            "relations": [r.to_dict() for r in self.relations],
            "counts": self.counts.to_dict(),
            "events": [e.to_dict() for e in self.events],
            "previews": [p.to_dict() for p in self.previews],
            # Explicit: Stage B never claims visual relevance
            "semantic_acceptance": "NOT_RUN",
            "note": "SEARCH RESULT != SELECTED SHOT. Stage C VisualVerifier decides relevance.",
        }


def _capability_for(request: MediaSearchRequest) -> ProviderCapability:
    if request.archive_preference:
        return ProviderCapability.ARCHIVE_SEARCH
    types = [t.lower() for t in (request.preferred_media_types or [])]
    if any(t in {"stock_photo", "image", "photo", "archive_still", "document"} for t in types):
        if any(t == "document" for t in types):
            return ProviderCapability.DOCUMENT_SEARCH
        return ProviderCapability.IMAGE_SEARCH
    return ProviderCapability.VIDEO_SEARCH


def acquire_candidates(
    request: MediaSearchRequest,
    *,
    registry: MediaProviderRegistry | None = None,
    providers: list[str] | None = None,
    fetch_previews: bool = True,
) -> AcquisitionResult:
    """
    Multi-source candidate acquisition.

    - Does NOT run random generic fallbacks (luxury/money/nature).
    - Distinguishes provider failure from zero results.
    - Does NOT claim visual relevance.
    """
    reg = registry or default_registry()
    cap = _capability_for(request)
    targets = reg.providers_for(
        cap,
        semantic_domain=request.semantic_domain,
        archive_preference=request.archive_preference,
    )
    if providers:
        allow = set(providers)
        targets = [p for p in targets if p.name in allow]

    all_cands: list[MediaCandidate] = []
    events: list[ProviderSearchEvent] = []

    for provider in targets:
        if not provider.is_enabled():
            events.append(
                ProviderSearchEvent(
                    provider=provider.name,
                    job_id=request.job_id,
                    beat_id=request.beat_id,
                    shot_id=request.shot_id,
                    query=request.query,
                    query_family=request.query_family,
                    status=ProviderHealth.UNAVAILABLE.value,
                    failure_reason="disabled",
                    raw_result_count=0,
                )
            )
            continue

        t0 = time.perf_counter()
        try:
            hits = provider.search(request)
            latency = (time.perf_counter() - t0) * 1000
            # Zero results with AVAILABLE health is legitimate empty
            status = provider.health.value
            events.append(
                ProviderSearchEvent(
                    provider=provider.name,
                    job_id=request.job_id,
                    beat_id=request.beat_id,
                    shot_id=request.shot_id,
                    query=request.query,
                    query_family=request.query_family,
                    latency_ms=latency,
                    raw_result_count=len(hits),
                    status=status,
                    failure_reason="" if hits or status == ProviderHealth.AVAILABLE.value else provider.last_failure,
                    candidate_ids=[c.candidate_id for c in hits],
                )
            )
            all_cands.extend(hits)
        except Exception as exc:
            latency = (time.perf_counter() - t0) * 1000
            status = provider.health.value
            if status == ProviderHealth.AVAILABLE.value:
                status = ProviderHealth.UNAVAILABLE.value
                provider.set_health(ProviderHealth.UNAVAILABLE, str(exc)[:160])
            events.append(
                ProviderSearchEvent(
                    provider=provider.name,
                    job_id=request.job_id,
                    beat_id=request.beat_id,
                    shot_id=request.shot_id,
                    query=request.query,
                    query_family=request.query_family,
                    latency_ms=latency,
                    raw_result_count=0,
                    status=status,
                    failure_reason=str(exc)[:200],
                    candidate_ids=[],
                )
            )
            # Continue — one provider failure must not crash acquisition
            continue

    marked, relations, counts = dedupe_candidates(all_cands)
    unique = [c for c in marked if c.duplicate_kind == "UNIQUE"]
    for ev in events:
        if ev.candidate_ids:
            ev.deduped_result_count = sum(
                1 for c in unique if c.candidate_id in ev.candidate_ids
            )

    previews: list[PreviewReference] = []
    if fetch_previews:
        by_name = {p.name: p for p in reg.all()}
        for c in unique[: request.result_limit * 2]:
            prov_name = c.provenance.provider
            # wikipedia_pageimage maps under wikimedia adapter
            p = by_name.get(prov_name) or by_name.get("wikimedia")
            if p:
                previews.append(p.get_preview(c))
            else:
                previews.append(
                    PreviewReference(
                        candidate_id=c.candidate_id,
                        preview_url=c.preview_url or c.provenance.preview_url,
                    )
                )

    return AcquisitionResult(
        request=request,
        candidates=marked,
        unique_candidates=unique,
        relations=relations,
        counts=counts,
        events=events,
        previews=previews,
    )


def build_attribution_manifest(assets: list[MediaAsset | MediaCandidate]) -> list[AttributionEntry]:
    entries: list[AttributionEntry] = []
    for item in assets:
        if isinstance(item, MediaAsset):
            prov = item.provenance
            entries.append(
                AttributionEntry(
                    asset_id=item.asset_id,
                    provider=prov.provider,
                    source_url=prov.source_url,
                    creator=prov.creator,
                    creator_url=getattr(prov, "creator_url", "") or "",
                    license=prov.license,
                    license_url=getattr(prov, "license_url", "") or "",
                    license_policy=getattr(prov, "license_policy", "UNKNOWN") or "UNKNOWN",
                    attribution_text=prov.attribution,
                )
            )
        else:
            prov = item.provenance
            entries.append(
                AttributionEntry(
                    candidate_id=item.candidate_id,
                    provider=prov.provider,
                    source_url=prov.source_url,
                    creator=prov.creator,
                    creator_url=item.creator_url or getattr(prov, "creator_url", "") or "",
                    license=prov.license,
                    license_url=item.license_url or getattr(prov, "license_url", "") or "",
                    license_policy=item.license_policy or "UNKNOWN",
                    attribution_text=prov.attribution,
                )
            )
    return entries


def materialize_selected(
    candidate: MediaCandidate,
    *,
    job_dir: Path | str,
) -> MediaAsset:
    """Final download for ONE chosen candidate (after Stage C later)."""
    return materialize_candidate(candidate, job_dir=job_dir)
