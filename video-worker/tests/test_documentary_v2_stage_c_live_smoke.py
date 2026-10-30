"""Optional live VisualVerifier smoke — STAGE_C_LIVE_SMOKE=true.

Uses Stage B acquisition when keys exist, else skips gracefully.
NO RENDER. NO PUBLISH. NO production wiring.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from app.documentary_v2.providers.acquisition import acquire_candidates
from app.documentary_v2.providers.materialize import MaterializeError, materialize_candidate
from app.documentary_v2.providers.registry import default_registry
from app.documentary_v2.schemas import MediaSearchRequest, QueryFamily, VisualVerificationRequest
from app.documentary_v2.verifier.remote_vlm import RemoteVLMVerifier
from app.documentary_v2.verifier.service import verify_candidate

pytestmark = pytest.mark.live_smoke


INTENTS = [
    (
        MediaSearchRequest(
            query="Rolex Daytona chronograph wristwatch",
            query_family=QueryFamily.ENTITY_EXACT.value,
            preferred_media_types=["stock_video", "stock_photo"],
            result_limit=3,
            job_id="c-smoke-product",
        ),
        VisualVerificationRequest(
            verification_id="vv:smoke:product",
            job_id="c-smoke-product",
            required_visual_concept="Rolex or luxury chronograph wristwatch",
            required_entities=["watch"],
            strict_entity_mode=False,
            semantic_domain="luxury_watch",
        ),
    ),
    (
        MediaSearchRequest(
            query="Marie Curie portrait",
            query_family=QueryFamily.ARCHIVE.value,
            preferred_media_types=["archive_still", "stock_photo"],
            archive_preference=True,
            target_entities=["Marie Curie"],
            result_limit=3,
            job_id="c-smoke-person",
        ),
        VisualVerificationRequest(
            verification_id="vv:smoke:person",
            job_id="c-smoke-person",
            required_visual_concept="historical person portrait",
            required_entities=["Marie Curie"],
            strict_entity_mode=True,
            retrieval_context={"trusted_person_provenance": True},
        ),
    ),
]


@pytest.mark.skipif(
    os.environ.get("STAGE_C_LIVE_SMOKE", "").lower() != "true",
    reason="Set STAGE_C_LIVE_SMOKE=true for live VLM smoke",
)
def test_live_visual_verification_smoke(tmp_path: Path):
    verifier = RemoteVLMVerifier()
    if not verifier.available:
        pytest.skip("No VLM credentials (OPENROUTER_API_KEY / LLM_API_URL)")

    reports = []
    for search_req, vv_req in INTENTS:
        acq = acquire_candidates(search_req, registry=default_registry(), fetch_previews=True)
        # Prefer candidates with download/preview URLs
        cands = [
            c
            for c in acq.unique_candidates
            if c.download_url or c.preview_url or c.provenance.download_url
        ][:2]
        for cand in cands:
            job = tmp_path / search_req.job_id
            job.mkdir(parents=True, exist_ok=True)
            url = cand.preview_url or cand.download_url or cand.provenance.preview_url
            # Prefer preview URL for cost — download preview into job dir via materialize if needed
            local = None
            try:
                # Use preview URL as download for smoke when available
                if cand.preview_url and not cand.download_url:
                    cand.download_url = cand.preview_url
                    cand.provenance.download_url = cand.preview_url
                asset = materialize_candidate(cand, job_dir=job, max_bytes=15 * 1024 * 1024)
                local = asset.local_path
            except MaterializeError as exc:
                reports.append(
                    {
                        "candidate_id": cand.candidate_id,
                        "error": str(exc),
                        "decision": "UNCERTAIN",
                    }
                )
                continue
            req = VisualVerificationRequest(
                verification_id=f"vv:{cand.candidate_id}",
                job_id=vv_req.job_id,
                candidate_id=cand.candidate_id,
                required_visual_concept=vv_req.required_visual_concept,
                required_entities=list(vv_req.required_entities),
                strict_entity_mode=vv_req.strict_entity_mode,
                semantic_domain=vv_req.semantic_domain,
                retrieval_context={
                    **(vv_req.retrieval_context or {}),
                    "query": cand.query,
                    "provider": cand.provenance.provider,
                    "source_url": cand.provenance.source_url,
                    "metadata_claims": [cand.query, cand.provenance.source_url],
                },
            )
            result = verify_candidate(
                req,
                media_path=local,
                provider=verifier,
                work_dir=job / "vv",
                use_cache=True,
            )
            reports.append(
                {
                    "candidate_id": cand.candidate_id,
                    "provider": cand.provenance.provider,
                    "metadata": {
                        "query": cand.query,
                        "source_url": cand.provenance.source_url,
                    },
                    "visible_summary": result.visible_text_summary
                    or result.dominant_visual_concept,
                    "visible_objects": result.visible_objects,
                    "decision": result.decision,
                    "confidence": result.confidence,
                    "reason_codes": result.reason_codes,
                    "latency_ms": result.latency_ms,
                    "preview_frame_count": result.preview_frame_count,
                    "cache_hit": result.cache_hit,
                    "verifier_model": result.verifier_model,
                }
            )

    assert reports, "no candidates verified"
    # Never ACCEPT solely from transport failure mishandling — decisions must be valid
    for r in reports:
        if "error" not in r:
            assert r["decision"] in {"ACCEPT", "REJECT", "UNCERTAIN"}

    out = os.environ.get("MEDIA_DIR")
    if out:
        Path(out).joinpath("DOCUMENTARY_ENGINE_V2_STAGE_C_LIVE_SMOKE.json").write_text(
            json.dumps(reports, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
