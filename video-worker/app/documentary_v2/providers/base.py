"""MediaProvider contract + shared helpers."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from app.documentary_v2.schemas import (
    AssetProvenance,
    LicensePolicy,
    LicenseState,
    MediaAsset,
    MediaCandidate,
    MediaSearchRequest,
    PreviewReference,
    ProviderCapability,
    ProviderHealth,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def candidate_id(provider: str, source_id: str) -> str:
    return f"cand:{provider}:{source_id}"


def normalize_url(url: str) -> str:
    u = (url or "").strip().split("?")[0].rstrip("/")
    return u.lower()


class MediaProvider(ABC):
    """Search ≠ select. Providers return candidates only."""

    name: str = ""
    capabilities: frozenset[ProviderCapability] = frozenset()
    reliability: str = "stable"  # stable|degraded|experimental
    enabled_by_default: bool = True

    def __init__(self) -> None:
        self._health = ProviderHealth.AVAILABLE
        self._last_failure = ""

    @property
    def health(self) -> ProviderHealth:
        return self._health

    @property
    def last_failure(self) -> str:
        return self._last_failure

    def set_health(self, status: ProviderHealth, reason: str = "") -> None:
        self._health = status
        self._last_failure = reason

    def supports(self, capability: ProviderCapability) -> bool:
        return capability in self.capabilities

    def is_enabled(self) -> bool:
        return True

    @abstractmethod
    def search(self, request: MediaSearchRequest) -> list[MediaCandidate]:
        ...

    def get_preview(self, candidate: MediaCandidate) -> PreviewReference:
        return PreviewReference(
            candidate_id=candidate.candidate_id,
            preview_url=candidate.preview_url or candidate.provenance.preview_url,
            preview_kind=(
                "video_preview"
                if "video" in (candidate.provenance.media_type or "")
                else "image_thumb"
            ),
            width=candidate.provenance.width,
            height=candidate.provenance.height,
            duration_sec=candidate.provenance.duration,
        )

    def get_provenance(self, candidate: MediaCandidate) -> AssetProvenance:
        return candidate.provenance

    def materialize(
        self,
        candidate: MediaCandidate,
        *,
        dest_dir: str,
        quality: str = "default",
    ) -> MediaAsset:
        raise NotImplementedError(
            f"{self.name}: use providers.materialize.materialize_candidate"
        )


def map_license(
    *,
    raw: str = "",
    provider_hint: str = "",
) -> tuple[str, str]:
    """Return (LicenseState value, LicensePolicy value). Never invent rights."""
    text = (raw or "").strip()
    if not text:
        return LicenseState.UNKNOWN.value, LicensePolicy.UNKNOWN.value
    low = text.lower()
    if low in {"cc0", "public domain", "pd", "publicdomain"}:
        return (
            LicenseState.CC0.value if "cc0" in low else LicenseState.PUBLIC_DOMAIN.value,
            LicensePolicy.KNOWN_REUSABLE.value,
        )
    if "cc-by-sa" in low or "cc by-sa" in low or "cc_by_sa" in low:
        return LicenseState.CC_BY_SA.value, LicensePolicy.ATTRIBUTION_REQUIRED.value
    if "cc-by" in low or "cc by" in low or "attribution" in low:
        return LicenseState.CC_BY.value, LicensePolicy.ATTRIBUTION_REQUIRED.value
    if any(x in low for x in ("all rights", "restricted", "copyright", "proprietary")):
        return LicenseState.RESTRICTED.value, LicensePolicy.KNOWN_RESTRICTED.value
    if provider_hint in {"pexels", "pixabay"} and not text:
        # Provider TOS exists but we do not invent STOCK_LICENSED without evidence
        return LicenseState.UNKNOWN.value, LicensePolicy.UNKNOWN.value
    if text.upper() in {s.value for s in LicenseState}:
        state = text.upper()
        if state in {LicenseState.CC0.value, LicenseState.PUBLIC_DOMAIN.value}:
            return state, LicensePolicy.KNOWN_REUSABLE.value
        if state in {LicenseState.CC_BY.value, LicenseState.CC_BY_SA.value}:
            return state, LicensePolicy.ATTRIBUTION_REQUIRED.value
        if state == LicenseState.STOCK_LICENSED.value:
            return state, LicensePolicy.KNOWN_REUSABLE.value
        if state in {LicenseState.RESTRICTED.value, LicenseState.PROPRIETARY.value}:
            return state, LicensePolicy.KNOWN_RESTRICTED.value
        return state, LicensePolicy.UNKNOWN.value
    return LicenseState.UNKNOWN.value, LicensePolicy.UNKNOWN.value


def classify_http_failure(exc: BaseException, status_code: int | None = None) -> tuple[ProviderHealth, str]:
    msg = str(exc)[:200]
    code = status_code
    if code is None and hasattr(exc, "response") and getattr(exc, "response") is not None:
        try:
            code = int(exc.response.status_code)
        except Exception:
            code = None
    if code == 401 or code == 403:
        return ProviderHealth.AUTH_MISSING, msg or f"http_{code}"
    if code == 429:
        return ProviderHealth.RATE_LIMITED, msg or "rate_limited"
    if code and code >= 500:
        return ProviderHealth.DEGRADED, msg or f"http_{code}"
    if "timeout" in msg.lower() or "timed out" in msg.lower():
        return ProviderHealth.DEGRADED, msg or "timeout"
    return ProviderHealth.UNAVAILABLE, msg or "error"


def empty_provenance(**kwargs: Any) -> AssetProvenance:
    kwargs.setdefault("retrieved_at", utc_now())
    return AssetProvenance(**kwargs)
