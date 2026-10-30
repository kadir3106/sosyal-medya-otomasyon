"""Visual verification service — sample → cache → VLM → validate → decision."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.documentary_v2.schemas import (
    MediaCandidate,
    VisualPreviewBundle,
    VisualVerification,
    VisualVerificationRequest,
)
from app.documentary_v2.verifier.base import VisualVerifierProvider
from app.documentary_v2.verifier.cache import VerificationCache, verification_cache_key
from app.documentary_v2.verifier.decision import apply_decision
from app.documentary_v2.verifier.mock import MockVisualVerifier
from app.documentary_v2.verifier.prefilter import cheap_prefilter
from app.documentary_v2.verifier.reason_codes import (
    DECISION_UNCERTAIN,
    PREVIEW_UNUSABLE,
    PROMPT_VERSION,
    VLM_INVALID_RESPONSE,
    VLM_UNAVAILABLE,
)
from app.documentary_v2.verifier.sampler import build_preview_bundle


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_verifier_from_config(
    override: VisualVerifierProvider | None = None,
) -> VisualVerifierProvider:
    if override is not None:
        return override
    from app.config import config

    name = (config.VISUAL_VERIFIER_PROVIDER or "mock").lower()
    if name in {"mock", "fixture"}:
        return MockVisualVerifier()
    if name in {"remote_vlm", "remote", "openai", "openrouter", "airouter"}:
        from app.documentary_v2.verifier.remote_vlm import RemoteVLMVerifier

        primary = RemoteVLMVerifier(timeout=config.VISUAL_VERIFIER_TIMEOUT)
        fb = (config.VISUAL_VERIFIER_FALLBACK_PROVIDER or "").lower()
        if fb == "mock":
            return _FallbackVerifier(primary, MockVisualVerifier())
        return primary
    return MockVisualVerifier()


class _FallbackVerifier(VisualVerifierProvider):
    name = "fallback"

    def __init__(self, primary: VisualVerifierProvider, secondary: VisualVerifierProvider) -> None:
        self.primary = primary
        self.secondary = secondary
        self.model = getattr(primary, "model", "") or getattr(secondary, "model", "")

    def observe(self, request, bundle):
        try:
            if self.primary.available:
                return self.primary.observe(request, bundle)
        except Exception:
            pass
        return self.secondary.observe(request, bundle)


def verify_candidate(
    request: VisualVerificationRequest,
    *,
    media_path: Path | str,
    media_kind: str = "",
    provider: VisualVerifierProvider | None = None,
    cache: VerificationCache | None = None,
    work_dir: Path | str | None = None,
    use_cache: bool | None = None,
) -> VisualVerification:
    from app.config import config

    verifier = build_verifier_from_config(provider)
    max_frames = int(config.VISUAL_VERIFIER_MAX_FRAMES)
    t0 = time.perf_counter()
    vid = request.verification_id or f"vv:{uuid.uuid4().hex[:12]}"

    bundle = build_preview_bundle(
        media_path,
        candidate_id=request.candidate_id,
        media_kind=media_kind,
        max_frames=max_frames,
        work_dir=work_dir,
    )
    if not bundle.frames:
        result = VisualVerification(
            verification_id=vid,
            candidate_id=request.candidate_id,
            job_id=request.job_id,
            beat_id=request.beat_id,
            shot_id=request.shot_id,
            decision=DECISION_UNCERTAIN,
            status=DECISION_UNCERTAIN,
            reason_codes=[PREVIEW_UNUSABLE],
            explanation_short="No usable preview frames.",
            verifier_provider=verifier.name,
            verifier_model=getattr(verifier, "model", ""),
            latency_ms=(time.perf_counter() - t0) * 1000,
            verified_at=_utc_now(),
        )
        return result

    cache_enabled = config.VISUAL_VERIFIER_CACHE if use_cache is None else use_cache
    cache_obj = cache
    if cache_enabled and cache_obj is None:
        root = None
        if request.job_id:
            root = Path(work_dir or ".") / "verification_cache"
        cache_obj = VerificationCache(root=root)

    key = verification_cache_key(
        content_fingerprint=bundle.content_fingerprint or request.candidate_id,
        intent_signature=request.intent_signature(),
        verifier_provider=verifier.name,
        verifier_model=getattr(verifier, "model", "") or "",
        prompt_version=PROMPT_VERSION,
    )
    if cache_obj:
        hit = cache_obj.get(key)
        if hit:
            hit.cache_hit = True
            hit.latency_ms = (time.perf_counter() - t0) * 1000
            return hit

    motion_est = str((bundle.technical or {}).get("motion_estimate") or "UNKNOWN_MOTION")
    try:
        observation = verifier.observe(request, bundle)
    except Exception as exc:
        msg = str(exc)
        code = VLM_UNAVAILABLE if "UNAVAILABLE" in msg else VLM_INVALID_RESPONSE
        if "RATE_LIMIT" in msg.upper():
            code = VLM_UNAVAILABLE
        result = VisualVerification(
            verification_id=vid,
            candidate_id=request.candidate_id,
            job_id=request.job_id,
            beat_id=request.beat_id,
            shot_id=request.shot_id,
            decision=DECISION_UNCERTAIN,
            status=DECISION_UNCERTAIN,
            reason_codes=[code],
            explanation_short=msg[:300],
            verifier_provider=verifier.name,
            verifier_model=getattr(verifier, "model", ""),
            preview_frame_count=len(bundle.frames),
            preview_duration_sec=bundle.duration_sec,
            latency_ms=(time.perf_counter() - t0) * 1000,
            verified_at=_utc_now(),
            details={"error": msg[:300]},
        )
        return result

    result = apply_decision(
        request,
        observation,
        verification_id=vid,
        motion_estimate=motion_est,
        preview_frame_count=len(bundle.frames),
        preview_duration_sec=bundle.duration_sec,
    )
    result.verifier_provider = verifier.name
    result.verifier_model = getattr(verifier, "model", "")
    result.latency_ms = (time.perf_counter() - t0) * 1000
    result.verified_at = _utc_now()
    result.cache_hit = False
    result.details["preview"] = {
        "frame_count": len(bundle.frames),
        "timestamps": [f.timestamp_sec for f in bundle.frames],
        "motion_estimate": motion_est,
    }

    if cache_obj and result.decision in {"ACCEPT", "REJECT", "UNCERTAIN"}:
        # Cache UNCERTAIN from VLM judgment, but not transport failures already returned
        if VLM_UNAVAILABLE not in result.reason_codes:
            cache_obj.set(key, result)
    return result


def verify_shortlist(
    request_template: VisualVerificationRequest,
    candidates: list[tuple[MediaCandidate, Path | str]],
    *,
    provider: VisualVerifierProvider | None = None,
    max_candidates: int | None = None,
    work_dir: Path | str | None = None,
) -> list[VisualVerification]:
    """Prefilter → budgeted VisualVerifier. Does NOT select final shot (Stage D)."""
    from app.config import config

    limit = max_candidates if max_candidates is not None else config.VISUAL_VERIFIER_MAX_CANDIDATES
    results: list[VisualVerification] = []
    verified = 0
    for cand, path in candidates:
        req = VisualVerificationRequest(
            verification_id=f"vv:{cand.candidate_id}",
            job_id=request_template.job_id,
            beat_id=request_template.beat_id,
            shot_id=request_template.shot_id,
            candidate_id=cand.candidate_id,
            required_visual_concept=request_template.required_visual_concept,
            semantic_domain=request_template.semantic_domain,
            narrative_role=request_template.narrative_role,
            required_entities=list(request_template.required_entities),
            optional_entities=list(request_template.optional_entities),
            required_action=request_template.required_action,
            required_location=request_template.required_location,
            motion_requirement=request_template.motion_requirement,
            evidence_requirement=request_template.evidence_requirement,
            authenticity_requirement=request_template.authenticity_requirement,
            preferred_media_type=request_template.preferred_media_type,
            forbidden_visual_concepts=list(request_template.forbidden_visual_concepts),
            strict_entity_mode=request_template.strict_entity_mode,
            context_narration=request_template.context_narration,
            retrieval_context={
                **(request_template.retrieval_context or {}),
                "query": cand.query,
                "provider": cand.provenance.provider,
                "source_url": cand.provenance.source_url,
                "metadata_claims": [
                    cand.query,
                    cand.provenance.source_url,
                ],
            },
        )
        pf = cheap_prefilter(cand, req)
        if not pf.accepted:
            results.append(
                VisualVerification(
                    verification_id=req.verification_id,
                    candidate_id=cand.candidate_id,
                    decision=DECISION_UNCERTAIN,
                    status=DECISION_UNCERTAIN,
                    reason_codes=[PREVIEW_UNUSABLE],
                    explanation_short=pf.reason,
                    job_id=req.job_id,
                )
            )
            continue
        if verified >= limit:
            break
        results.append(
            verify_candidate(
                req,
                media_path=path,
                provider=provider,
                work_dir=work_dir,
            )
        )
        verified += 1
    return results
