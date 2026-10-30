"""Pexels MediaProvider — wraps stock_media search helpers; no download-all."""
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
    LicenseState,
    MediaCandidate,
    MediaSearchRequest,
    MediaType,
    PreviewReference,
    ProviderCapability,
    ProviderHealth,
)


class PexelsProvider(MediaProvider):
    name = "pexels"
    capabilities = frozenset(
        {
            ProviderCapability.VIDEO_SEARCH,
            ProviderCapability.IMAGE_SEARCH,
            ProviderCapability.PREVIEW_VIDEO,
            ProviderCapability.PREVIEW_IMAGE,
            ProviderCapability.ATTRIBUTION_METADATA,
        }
    )
    reliability = "stable"

    def __init__(self, api_key: str | None = None, cache: SearchCache | None = None) -> None:
        super().__init__()
        self.api_key = api_key if api_key is not None else os.environ.get("PEXELS_API_KEY", "")
        self.cache = cache or SearchCache()

    def is_enabled(self) -> bool:
        return bool(self.api_key)

    def search(self, request: MediaSearchRequest) -> list[MediaCandidate]:
        if not self.api_key:
            self.set_health(ProviderHealth.AUTH_MISSING, "PEXELS_API_KEY missing")
            raise RuntimeError("AUTH_MISSING:PEXELS_API_KEY")

        want_image = any(
            t in {"stock_photo", "image", "photo"} for t in (request.preferred_media_types or [])
        )
        key = cache_key(
            self.name,
            request.query,
            filters={
                "limit": request.result_limit,
                "orientation": request.orientation,
                "kind": "image" if want_image else "video",
                "domain": request.semantic_domain,
            },
        )
        cached = self.cache.get(key)
        if cached is not None:
            return [self._from_cached(c) for c in cached]

        t0 = time.perf_counter()
        try:
            if want_image:
                rows = self._search_photos(request)
            else:
                rows = self._search_videos(request)
            self.set_health(ProviderHealth.AVAILABLE)
        except Exception as exc:
            status, reason = classify_http_failure(exc)
            self.set_health(status, reason)
            raise

        _ = (time.perf_counter() - t0) * 1000
        out = [self._map_row(r, request) for r in rows]
        self.cache.set(key, [c.to_dict() for c in out])
        return out

    def _from_cached(self, d: dict) -> MediaCandidate:
        from app.documentary_v2.schemas import AssetProvenance

        prov = AssetProvenance.from_dict(d.get("provenance") or {})
        return MediaCandidate(
            candidate_id=str(d.get("candidate_id") or ""),
            shot_requirement_id=str(d.get("shot_requirement_id") or ""),
            provenance=prov,
            query=str(d.get("query") or ""),
            query_family=str(d.get("query_family") or ""),
            prefilter_score=d.get("prefilter_score"),
            preview_url=str(d.get("preview_url") or ""),
            download_url=str(d.get("download_url") or ""),
            creator_url=str(d.get("creator_url") or ""),
            license_raw=str(d.get("license_raw") or ""),
            license_policy=str(d.get("license_policy") or LicenseState.UNKNOWN.value),
            duplicate_kind=str(d.get("duplicate_kind") or "UNIQUE"),
        )

    def _search_videos(self, request: MediaSearchRequest) -> list[dict]:
        from app.stock_media import _list_pexels_video_candidates

        return _list_pexels_video_candidates(
            request.query,
            self.api_key,
            exclude_ids=set(),
            limit=request.result_limit,
        )

    def _search_photos(self, request: MediaSearchRequest) -> list[dict]:
        from app.http_client import session

        params = {
            "query": request.query,
            "per_page": min(request.result_limit, 15),
        }
        if request.orientation in {"portrait", "landscape", "square"}:
            params["orientation"] = request.orientation
        resp = session.get(
            "https://api.pexels.com/v1/search",
            headers={"Authorization": self.api_key},
            params=params,
            timeout=30,
        )
        if resp.status_code == 429:
            self.set_health(ProviderHealth.RATE_LIMITED, "pexels_429")
            raise RuntimeError("RATE_LIMITED")
        resp.raise_for_status()
        photos = resp.json().get("photos") or []
        out = []
        for p in photos[: request.result_limit]:
            src = p.get("src") or {}
            out.append(
                {
                    "provider": "pexels",
                    "asset_id": p.get("id"),
                    "download_url": src.get("large2x") or src.get("large") or src.get("original"),
                    "preview_url": src.get("medium") or src.get("small") or src.get("tiny"),
                    "metadata": {
                        "url": p.get("url") or "",
                        "user": p.get("photographer") or "",
                        "creator_url": p.get("photographer_url") or "",
                        "width": p.get("width"),
                        "height": p.get("height"),
                        "id": p.get("id"),
                    },
                    "kind": "photo",
                }
            )
        return out

    def _map_row(self, row: dict, request: MediaSearchRequest) -> MediaCandidate:
        meta = row.get("metadata") or {}
        sid = str(row.get("asset_id") or meta.get("id") or "")
        kind = row.get("kind") or "video"
        media_type = (
            MediaType.STOCK_PHOTO.value if kind == "photo" else MediaType.STOCK_VIDEO.value
        )
        # Pexels does not return machine-readable license on video API — UNKNOWN
        lic_state, lic_policy = map_license(raw=str(meta.get("license") or ""))
        creator = str(meta.get("user") or meta.get("photographer") or "")
        preview = str(row.get("preview_url") or meta.get("preview_url") or "")
        download = str(row.get("download_url") or "")
        source_url = str(meta.get("url") or meta.get("page_url") or "")
        prov = empty_provenance(
            provider=self.name,
            source_id=sid,
            source_url=source_url,
            download_url=download,
            preview_url=preview,
            media_type=media_type,
            duration=float(meta["duration"]) if meta.get("duration") is not None else None,
            width=int(meta["width"]) if meta.get("width") is not None else None,
            height=int(meta["height"]) if meta.get("height") is not None else None,
            creator=creator,
            creator_url=str(meta.get("creator_url") or ""),
            license=lic_state,
            license_raw=str(meta.get("license") or ""),
            license_policy=lic_policy,
            attribution=creator,
            stock=True,
            archive=False,
            synthetic=False,
            retrieved_at=utc_now(),
        )
        return MediaCandidate(
            candidate_id=candidate_id(self.name, sid),
            shot_requirement_id=request.shot_requirement_id,
            provenance=prov,
            query=request.query,
            query_family=request.query_family,
            prefilter_score=row.get("provider_rank_score"),
            preview_url=preview,
            download_url=download,
            creator_url=prov.creator_url,
            license_raw=prov.license_raw,
            license_policy=lic_policy,
        )

    def get_preview(self, candidate: MediaCandidate) -> PreviewReference:
        return PreviewReference(
            candidate_id=candidate.candidate_id,
            preview_url=candidate.preview_url or candidate.provenance.preview_url,
            preview_kind=(
                "image_thumb"
                if "photo" in (candidate.provenance.media_type or "")
                else "video_preview"
            ),
            width=candidate.provenance.width,
            height=candidate.provenance.height,
            duration_sec=candidate.provenance.duration,
        )
