"""Mixkit — HTML scrape. Marked DEGRADED; not equal-reliability first-class."""
from __future__ import annotations

import os

from app.documentary_v2.providers.base import (
    MediaProvider,
    candidate_id,
    empty_provenance,
    utc_now,
)
from app.documentary_v2.schemas import (
    LicenseState,
    MediaCandidate,
    MediaSearchRequest,
    MediaType,
    PreviewReference,
    ProviderCapability,
    ProviderHealth,
)


class MixkitProvider(MediaProvider):
    name = "mixkit"
    capabilities = frozenset(
        {
            ProviderCapability.VIDEO_SEARCH,
            ProviderCapability.PREVIEW_VIDEO,
        }
    )
    reliability = "degraded"  # HTML scrape — no stable API
    enabled_by_default = False

    def __init__(self) -> None:
        super().__init__()
        self.set_health(ProviderHealth.DEGRADED, "html_scrape_no_official_api")

    def is_enabled(self) -> bool:
        return os.environ.get("ENABLE_MIXKIT_STOCK", "true").lower() == "true"

    def search(self, request: MediaSearchRequest) -> list[MediaCandidate]:
        """Best-effort scrape via stock_media helper — license UNKNOWN always."""
        if not self.is_enabled():
            self.set_health(ProviderHealth.UNAVAILABLE, "disabled")
            return []
        try:
            from app.stock_media import _search_mixkit_video_meta

            vid, url, _reused, meta = _search_mixkit_video_meta(
                request.query, exclude_ids=set(), allow_used_id_reuse=True
            )
            if not vid or not url:
                self.set_health(ProviderHealth.DEGRADED, "no_scrape_hits")
                return []
            sid = str(vid)
            prov = empty_provenance(
                provider=self.name,
                source_id=sid,
                source_url=str((meta or {}).get("url") or ""),
                download_url=url,
                preview_url="",  # scrape does not yield reliable preview
                media_type=MediaType.STOCK_VIDEO.value,
                creator="",  # never fabricate
                license=LicenseState.UNKNOWN.value,
                license_raw="",
                license_policy="UNKNOWN",
                stock=True,
                retrieved_at=utc_now(),
            )
            self.set_health(ProviderHealth.DEGRADED, "html_scrape")
            return [
                MediaCandidate(
                    candidate_id=candidate_id(self.name, sid),
                    shot_requirement_id=request.shot_requirement_id,
                    provenance=prov,
                    query=request.query,
                    query_family=request.query_family,
                    download_url=url,
                    license_policy="UNKNOWN",
                )
            ]
        except Exception as exc:
            self.set_health(ProviderHealth.UNAVAILABLE, str(exc)[:120])
            raise

    def get_preview(self, candidate: MediaCandidate) -> PreviewReference:
        return PreviewReference(
            candidate_id=candidate.candidate_id,
            preview_url=candidate.download_url,  # no cheap preview — caller may skip
            preview_kind="video_preview",
        )
