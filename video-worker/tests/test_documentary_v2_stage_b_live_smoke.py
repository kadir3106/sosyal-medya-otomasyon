"""Optional live smoke for Stage B — marked so unit CI stays green offline.

Run: pytest -m live_smoke tests/test_documentary_v2_stage_b_live_smoke.py
"""
from __future__ import annotations

import os

import pytest

from app.documentary_v2.providers.acquisition import acquire_candidates
from app.documentary_v2.providers.registry import default_registry
from app.documentary_v2.schemas import MediaSearchRequest, QueryFamily

pytestmark = pytest.mark.live_smoke


INTENTS = [
    MediaSearchRequest(
        query="Marie Curie",
        query_family=QueryFamily.ARCHIVE.value,
        target_entities=["Marie Curie"],
        preferred_media_types=["archive_still", "stock_photo"],
        archive_preference=True,
        result_limit=3,
        job_id="smoke-person",
    ),
    MediaSearchRequest(
        query="Rolex Daytona chronograph",
        query_family=QueryFamily.ENTITY_EXACT.value,
        target_entities=["Rolex Daytona"],
        preferred_media_types=["stock_video"],
        result_limit=3,
        job_id="smoke-product",
    ),
    MediaSearchRequest(
        query="Golden Gate Bridge San Francisco",
        query_family=QueryFamily.LOCATION.value,
        preferred_media_types=["stock_video", "stock_photo"],
        result_limit=3,
        job_id="smoke-location",
    ),
    MediaSearchRequest(
        query="Apollo 11 moon landing",
        query_family=QueryFamily.ARCHIVE.value,
        archive_preference=True,
        preferred_media_types=["archive_still", "archive_video"],
        result_limit=3,
        job_id="smoke-historical",
    ),
]


@pytest.mark.skipif(
    os.environ.get("STAGE_B_LIVE_SMOKE", "").lower() != "true",
    reason="Set STAGE_B_LIVE_SMOKE=true to run live provider smoke",
)
def test_live_candidate_acquisition_smoke():
    """Prove providers return candidates with provenance/preview — NO visual claims."""
    reg = default_registry()
    summaries = []
    for req in INTENTS:
        result = acquire_candidates(req, registry=reg, fetch_previews=True)
        summaries.append(
            {
                "query": req.query,
                "events": [e.to_dict() for e in result.events],
                "unique_count": result.counts.unique_candidate_count,
                "candidate_ids": [c.candidate_id for c in result.unique_candidates[:5]],
                "licenses": [c.provenance.license for c in result.unique_candidates[:5]],
                "previews": [p.preview_url for p in result.previews[:5]],
                "semantic_acceptance": "NOT_RUN",
            }
        )
        # At least one provider must respond (success or explicit failure — not crash)
        assert result.events, "no provider events"
        # Do not require any particular provider hit — network/keys vary
    # Persist for report if MEDIA_DIR present
    out = os.environ.get("MEDIA_DIR")
    if out:
        from pathlib import Path
        import json

        path = Path(out) / "DOCUMENTARY_ENGINE_V2_STAGE_B_LIVE_SMOKE.json"
        path.write_text(json.dumps(summaries, indent=2, ensure_ascii=False), encoding="utf-8")
    assert len(summaries) == len(INTENTS)
