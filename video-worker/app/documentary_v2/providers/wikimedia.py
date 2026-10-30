"""Wikimedia Commons / Wikipedia archive-oriented provider."""
from __future__ import annotations

import hashlib
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

_UA = {"User-Agent": "sosyal-medya-otomasyon/documentary-v2-stage-b (wikimedia)"}


class WikimediaProvider(MediaProvider):
    """Commons + Wikipedia pageimages. Ranking ≠ visual relevance (Stage C)."""

    name = "wikimedia"
    capabilities = frozenset(
        {
            ProviderCapability.IMAGE_SEARCH,
            ProviderCapability.ARCHIVE_SEARCH,
            ProviderCapability.DOCUMENT_SEARCH,
            ProviderCapability.PREVIEW_IMAGE,
            ProviderCapability.LICENSE_METADATA,
            ProviderCapability.ATTRIBUTION_METADATA,
        }
    )
    reliability = "stable"

    def __init__(self, cache: SearchCache | None = None) -> None:
        super().__init__()
        self.cache = cache or SearchCache()

    def is_enabled(self) -> bool:
        return True

    def search(self, request: MediaSearchRequest) -> list[MediaCandidate]:
        key = cache_key(
            self.name,
            request.query,
            filters={"limit": request.result_limit, "entities": request.target_entities},
        )
        cached = self.cache.get(key)
        if cached is not None:
            from app.documentary_v2.schemas import AssetProvenance

            return [
                MediaCandidate(
                    candidate_id=str(d["candidate_id"]),
                    provenance=AssetProvenance.from_dict(d.get("provenance")),
                    query=str(d.get("query") or ""),
                    query_family=str(d.get("query_family") or ""),
                    preview_url=str(d.get("preview_url") or ""),
                    download_url=str(d.get("download_url") or ""),
                    license_raw=str(d.get("license_raw") or ""),
                    license_policy=str(d.get("license_policy") or "UNKNOWN"),
                )
                for d in cached
            ]

        t0 = time.perf_counter()
        try:
            rows = self._commons_search(request.query, limit=request.result_limit)
            if not rows and request.target_entities:
                # Fallback to Wikipedia pageimage for named entities only
                from app.person_archive import fetch_wikipedia_person_image

                for ent in request.target_entities[:3]:
                    meta = fetch_wikipedia_person_image(ent)
                    if meta:
                        rows.append({"_wiki_person": meta})
            self.set_health(ProviderHealth.AVAILABLE)
        except Exception as exc:
            status, reason = classify_http_failure(exc)
            self.set_health(status, reason)
            raise
        _ = (time.perf_counter() - t0) * 1000

        out = [self._map_row(r, request) for r in rows]
        self.cache.set(key, [c.to_dict() for c in out])
        return out

    def _commons_search(self, query: str, *, limit: int) -> list[dict]:
        from app.http_client import session

        # 1) search file titles
        sr = session.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srnamespace": 6,  # File
                "srlimit": min(limit, 10),
                "format": "json",
            },
            headers=_UA,
            timeout=20,
        )
        if sr.status_code == 429:
            self.set_health(ProviderHealth.RATE_LIMITED, "commons_429")
            raise RuntimeError("RATE_LIMITED")
        sr.raise_for_status()
        hits = (sr.json().get("query") or {}).get("search") or []
        titles = [h.get("title") for h in hits if h.get("title")]
        if not titles:
            return []

        # 2) imageinfo for license + urls
        ii = session.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action": "query",
                "titles": "|".join(titles[:limit]),
                "prop": "imageinfo",
                "iiprop": "url|size|mime|extmetadata|user",
                "iiurlwidth": 640,
                "format": "json",
            },
            headers=_UA,
            timeout=25,
        )
        ii.raise_for_status()
        pages = (ii.json().get("query") or {}).get("pages") or {}
        return list(pages.values())

    def _map_row(self, row: dict, request: MediaSearchRequest) -> MediaCandidate:
        if row.get("_wiki_person"):
            meta = row["_wiki_person"]
            sid = str(meta.get("asset_id") or "")
            # Do NOT fabricate Commons license from Wikipedia pageimage
            lic_state, lic_policy = LicenseState.UNKNOWN.value, "UNKNOWN"
            prov = empty_provenance(
                provider="wikipedia_pageimage",
                source_id=sid,
                source_url=str(meta.get("page_url") or ""),
                download_url=str(meta.get("download_url") or ""),
                preview_url=str(meta.get("download_url") or ""),
                media_type=MediaType.ARCHIVE_STILL.value,
                creator="",  # unknown from pageimages alone
                license=lic_state,
                license_raw="",
                license_policy=lic_policy,
                attribution="",  # do not fabricate "Wikipedia/Wikimedia" as creator
                archive=True,
                stock=False,
                retrieved_at=utc_now(),
            )
            return MediaCandidate(
                candidate_id=candidate_id("wikipedia_pageimage", sid),
                shot_requirement_id=request.shot_requirement_id,
                provenance=prov,
                query=request.query,
                query_family=request.query_family or "ARCHIVE",
                preview_url=prov.preview_url,
                download_url=prov.download_url,
                license_policy=lic_policy,
            )

        info = (row.get("imageinfo") or [{}])[0]
        ext = info.get("extmetadata") or {}
        def _ext(key: str) -> str:
            v = ext.get(key) or {}
            return str(v.get("value") or "").strip()

        title = str(row.get("title") or "")
        sid = hashlib.sha1(title.encode()).hexdigest()[:16]
        license_raw = _ext("LicenseShortName") or _ext("License")
        artist = _ext("Artist")
        # Strip HTML from artist if present
        if "<" in artist:
            import re

            artist = re.sub(r"<[^>]+>", "", artist).strip()
        lic_state, lic_policy = map_license(raw=license_raw)
        license_url = _ext("LicenseUrl")
        description = _ext("ImageDescription")
        if "<" in description:
            import re

            description = re.sub(r"<[^>]+>", "", description).strip()[:300]

        download = str(info.get("url") or "")
        preview = str(info.get("thumburl") or download)
        page_url = str(info.get("descriptionurl") or "")
        creator = artist or str(info.get("user") or "")

        prov = empty_provenance(
            provider=self.name,
            source_id=sid,
            source_url=page_url,
            download_url=download,
            preview_url=preview,
            media_type=MediaType.ARCHIVE_STILL.value,
            width=int(info["width"]) if info.get("width") is not None else None,
            height=int(info["height"]) if info.get("height") is not None else None,
            creator=creator,
            license=lic_state,
            license_url=license_url,
            license_raw=license_raw,
            license_policy=lic_policy,
            attribution=f"{creator} / {license_raw}".strip(" /") if creator or license_raw else "",
            archive=True,
            stock=False,
            retrieved_at=utc_now(),
        )
        return MediaCandidate(
            candidate_id=candidate_id(self.name, sid),
            shot_requirement_id=request.shot_requirement_id,
            provenance=prov,
            query=request.query,
            query_family=request.query_family or "ARCHIVE",
            preview_url=preview,
            download_url=download,
            license_url=license_url,
            license_raw=license_raw,
            license_policy=lic_policy,
        )

    def get_preview(self, candidate: MediaCandidate) -> PreviewReference:
        return PreviewReference(
            candidate_id=candidate.candidate_id,
            preview_url=candidate.preview_url or candidate.provenance.preview_url,
            preview_kind="image_thumb",
            width=candidate.provenance.width,
            height=candidate.provenance.height,
        )
