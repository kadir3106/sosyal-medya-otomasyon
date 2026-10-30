"""Internet Archive — bounded discovery + sensible file pick (not first MP4)."""
from __future__ import annotations

import time
from typing import Any

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

_UA = {"User-Agent": "sosyal-medya-otomasyon/documentary-v2-stage-b (archive.org)"}
_VIDEO_EXTS = {".mp4", ".webm", ".ogv", ".avi", ".mkv", ".mov"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff"}


class InternetArchiveProvider(MediaProvider):
    name = "internet_archive"
    capabilities = frozenset(
        {
            ProviderCapability.ARCHIVE_SEARCH,
            ProviderCapability.VIDEO_SEARCH,
            ProviderCapability.IMAGE_SEARCH,
            ProviderCapability.PREVIEW_IMAGE,
            ProviderCapability.LICENSE_METADATA,
            ProviderCapability.ATTRIBUTION_METADATA,
        }
    )
    reliability = "experimental"

    def __init__(self, cache: SearchCache | None = None) -> None:
        super().__init__()
        self.cache = cache or SearchCache()

    def is_enabled(self) -> bool:
        return True

    def search(self, request: MediaSearchRequest) -> list[MediaCandidate]:
        key = cache_key(
            self.name,
            request.query,
            filters={"limit": request.result_limit, "media": request.preferred_media_types},
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
            items = self._advanced_search(request.query, rows=min(request.result_limit, 5))
            out: list[MediaCandidate] = []
            for item in items:
                cand = self._item_to_candidate(item, request)
                if cand:
                    out.append(cand)
            self.set_health(ProviderHealth.AVAILABLE)
        except Exception as exc:
            status, reason = classify_http_failure(exc)
            self.set_health(status, reason)
            raise
        _ = (time.perf_counter() - t0) * 1000
        self.cache.set(key, [c.to_dict() for c in out])
        return out

    def _advanced_search(self, query: str, *, rows: int) -> list[dict]:
        from app.http_client import session

        # Prefer movies/image mediatype; do not invent results
        q = f"({query}) AND (mediatype:movies OR mediatype:image)"
        resp = session.get(
            "https://archive.org/advancedsearch.php",
            params={
                "q": q,
                "fl[]": ["identifier", "title", "mediatype", "licenseurl", "creator"],
                "rows": rows,
                "page": 1,
                "output": "json",
            },
            headers=_UA,
            timeout=25,
        )
        if resp.status_code == 429:
            self.set_health(ProviderHealth.RATE_LIMITED, "ia_429")
            raise RuntimeError("RATE_LIMITED")
        resp.raise_for_status()
        docs = ((resp.json().get("response") or {}).get("docs")) or []
        return docs

    def _metadata(self, identifier: str) -> dict:
        from app.http_client import session

        resp = session.get(
            f"https://archive.org/metadata/{identifier}",
            headers=_UA,
            timeout=25,
        )
        resp.raise_for_status()
        return resp.json() or {}

    def _pick_file(self, files: list[dict], *, prefer_video: bool) -> dict | None:
        """Choose a plausible rendition — never blindly first MP4."""
        scored: list[tuple[int, dict]] = []
        for f in files or []:
            name = str(f.get("name") or "")
            low = name.lower()
            fmt = str(f.get("format") or "").lower()
            size = int(f.get("size") or 0)
            # Skip derivatives that are clearly thumbnails / indexes
            if any(x in low for x in ("__ia_thumb", ".xml", ".sqlite", ".gz", "files.xml")):
                continue
            ext = "." + low.rsplit(".", 1)[-1] if "." in low else ""
            score = 0
            if prefer_video and (ext in _VIDEO_EXTS or "mpeg" in fmt or "h.264" in fmt):
                score += 50
                if "h.264" in fmt or ext == ".mp4":
                    score += 20
                if 500_000 < size < 40_000_000:
                    score += 10
                if "512kb" in low or "256kb" in low:
                    score += 5  # prefer smaller preview-ish
            elif (not prefer_video) and (ext in _IMAGE_EXTS or "jpeg" in fmt or "png" in fmt):
                score += 40
                if "thumb" in low:
                    score += 5
            if score > 0:
                scored.append((score, f))
        if not scored:
            return None
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]

    def _item_to_candidate(
        self, doc: dict, request: MediaSearchRequest
    ) -> MediaCandidate | None:
        ident = str(doc.get("identifier") or "")
        if not ident:
            return None
        meta = self._metadata(ident)
        files = meta.get("files") or []
        md = meta.get("metadata") or {}
        prefer_video = not any(
            t in {"stock_photo", "image", "photo"} for t in (request.preferred_media_types or [])
        )
        chosen = self._pick_file(files, prefer_video=prefer_video)
        if not chosen:
            # try opposite media
            chosen = self._pick_file(files, prefer_video=not prefer_video)
        if not chosen:
            return None

        name = str(chosen.get("name") or "")
        download = f"https://archive.org/download/{ident}/{name}"
        preview = f"https://archive.org/services/img/{ident}"
        license_url = ""
        if isinstance(doc.get("licenseurl"), list):
            license_url = str((doc.get("licenseurl") or [""])[0] or "")
        else:
            license_url = str(doc.get("licenseurl") or md.get("licenseurl") or "")
        raw_lic = license_url or str(md.get("license") or "")
        lic_state, lic_policy = map_license(raw=raw_lic)
        if not raw_lic:
            lic_state, lic_policy = LicenseState.UNKNOWN.value, "UNKNOWN"

        creator = ""
        cr = doc.get("creator") or md.get("creator") or ""
        if isinstance(cr, list):
            creator = str(cr[0] or "")
        else:
            creator = str(cr or "")

        media_type = (
            MediaType.ARCHIVE_VIDEO.value if prefer_video else MediaType.ARCHIVE_STILL.value
        )
        if name.lower().rsplit(".", 1)[-1] in {e[1:] for e in _IMAGE_EXTS}:
            media_type = MediaType.ARCHIVE_STILL.value

        sid = f"{ident}/{name}"
        prov = empty_provenance(
            provider=self.name,
            source_id=sid,
            source_url=f"https://archive.org/details/{ident}",
            download_url=download,
            preview_url=preview,
            media_type=media_type,
            creator=creator,
            license=lic_state,
            license_url=license_url,
            license_raw=raw_lic,
            license_policy=lic_policy,
            attribution=creator,
            archive=True,
            stock=False,
            retrieved_at=utc_now(),
        )
        return MediaCandidate(
            candidate_id=candidate_id(self.name, sid.replace("/", "_")),
            shot_requirement_id=request.shot_requirement_id,
            provenance=prov,
            query=request.query,
            query_family=request.query_family or "ARCHIVE",
            preview_url=preview,
            download_url=download,
            license_url=license_url,
            license_raw=raw_lic,
            license_policy=lic_policy,
        )

    def get_preview(self, candidate: MediaCandidate) -> PreviewReference:
        return PreviewReference(
            candidate_id=candidate.candidate_id,
            preview_url=candidate.preview_url or candidate.provenance.preview_url,
            preview_kind="image_thumb",
        )
