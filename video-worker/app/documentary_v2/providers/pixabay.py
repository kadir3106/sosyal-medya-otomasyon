"""Pixabay MediaProvider — secondary stock discovery."""
from __future__ import annotations

import os
import time

from app.documentary_v2.providers.base import (
    MediaProvider,
    candidate_id,
    classify_http_failure,
    empty_provenance,
    map_license,
    utc_now,
)
from app.documentary_v2.providers.cache import SearchCache, cache_key
from app.documentary_v2.schemas import (
    MediaCandidate,
    MediaSearchRequest,
    MediaType,
    PreviewReference,
    ProviderCapability,
    ProviderHealth,
)


class PixabayProvider(MediaProvider):
    name = "pixabay"
    capabilities = frozenset(
        {
            ProviderCapability.VIDEO_SEARCH,
            ProviderCapability.IMAGE_SEARCH,
            ProviderCapability.PREVIEW_VIDEO,
            ProviderCapability.PREVIEW_IMAGE,
            ProviderCapability.ATTRIBUTION_METADATA,
            ProviderCapability.LICENSE_METADATA,
        }
    )
    reliability = "stable"

    def __init__(self, api_key: str | None = None, cache: SearchCache | None = None) -> None:
        super().__init__()
        self.api_key = api_key if api_key is not None else os.environ.get("PIXABAY_API_KEY", "")
        self.cache = cache or SearchCache()

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, request: MediaSearchRequest) -> list[MediaCandidate]:
        if not self.api_key:
            self.set_health(ProviderHealth.AUTH_MISSING, "PIXABAY_API_KEY missing")
            raise RuntimeError("AUTH_MISSING:PIXABAY_API_KEY")

        key = cache_key(
            self.name,
            request.query,
            filters={"limit": request.result_limit, "orientation": request.orientation},
        )
        cached = self.cache.get(key)
        if cached is not None:
            from app.documentary_v2.schemas import AssetProvenance

            out = []
            for d in cached:
                prov = AssetProvenance.from_dict(d.get("provenance") or {})
                out.append(
                    MediaCandidate(
                        candidate_id=str(d["candidate_id"]),
                        provenance=prov,
                        query=str(d.get("query") or ""),
                        query_family=str(d.get("query_family") or ""),
                        preview_url=str(d.get("preview_url") or ""),
                        download_url=str(d.get("download_url") or ""),
                        license_raw=str(d.get("license_raw") or ""),
                        license_policy=str(d.get("license_policy") or "UNKNOWN"),
                    )
                )
            return out

        try:
            from app.stock_media import _list_pixabay_video_candidates

            rows = _list_pixabay_video_candidates(
                request.query,
                self.api_key,
                exclude_ids=set(),
                limit=request.result_limit,
            )
            self.set_health(ProviderHealth.AVAILABLE)
        except Exception as exc:
            status, reason = classify_http_failure(exc)
            self.set_health(status, reason)
            raise

        out = [self._map_row(r, request) for r in rows]
        self.cache.set(key, [c.to_dict() for c in out])
        return out

    def _map_row(self, row: dict, request: MediaSearchRequest) -> MediaCandidate:
        meta = row.get("metadata") or {}
        sid = str(row.get("asset_id") or meta.get("id") or "")
        # Pixabay Content License — preserve raw if present; else UNKNOWN
        raw_lic = str(meta.get("license") or "")
        lic_state, lic_policy = map_license(raw=raw_lic)
        download = str(row.get("download_url") or "")
        preview = str(row.get("preview_url") or meta.get("preview_url") or "")
        if not preview and meta.get("picture_id"):
            preview = f"https://i.vimeocdn.com/video/{meta.get('picture_id')}_295x166.jpg"
        creator = str(meta.get("user") or "")
        source_url = str(meta.get("url") or meta.get("page_url") or "")
        prov = empty_provenance(
            provider=self.name,
            source_id=sid,
            source_url=source_url,
            download_url=download,
            preview_url=preview if isinstance(preview, str) else "",
            media_type=MediaType.STOCK_VIDEO.value,
            creator=creator,
            license=lic_state,
            license_raw=raw_lic,
            license_policy=lic_policy,
            attribution=creator,
            stock=True,
            retrieved_at=utc_now(),
        )
        return MediaCandidate(
            candidate_id=candidate_id(self.name, sid),
            shot_requirement_id=request.shot_requirement_id,
            provenance=prov,
            query=request.query,
            query_family=request.query_family,
            prefilter_score=row.get("provider_rank_score"),
            preview_url=prov.preview_url,
            download_url=download,
            license_raw=raw_lic,
            license_policy=lic_policy,
        )

    def get_preview(self, candidate: MediaCandidate) -> PreviewReference:
        return PreviewReference(
            candidate_id=candidate.candidate_id,
            preview_url=candidate.preview_url or candidate.provenance.preview_url,
            preview_kind="video_preview",
            width=candidate.provenance.width,
            height=candidate.provenance.height,
            duration_sec=candidate.provenance.duration,
        )
