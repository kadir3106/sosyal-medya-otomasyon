"""MediaProviderRegistry — capability routing without if/else sprawl."""
from __future__ import annotations

from app.documentary_v2.providers.base import MediaProvider
from app.documentary_v2.providers.internet_archive import InternetArchiveProvider
from app.documentary_v2.providers.mixkit import MixkitProvider
from app.documentary_v2.providers.pexels import PexelsProvider
from app.documentary_v2.providers.pixabay import PixabayProvider
from app.documentary_v2.providers.wikimedia import WikimediaProvider
from app.documentary_v2.schemas import ProviderCapability, ProviderHealth


# Priority per capability (first = preferred)
_PRIORITY: dict[ProviderCapability, tuple[str, ...]] = {
    ProviderCapability.VIDEO_SEARCH: ("pexels", "pixabay", "internet_archive", "mixkit"),
    ProviderCapability.IMAGE_SEARCH: ("pexels", "wikimedia", "internet_archive", "pixabay"),
    ProviderCapability.ARCHIVE_SEARCH: ("wikimedia", "internet_archive"),
    ProviderCapability.DOCUMENT_SEARCH: ("wikimedia",),
    ProviderCapability.PREVIEW_VIDEO: ("pexels", "pixabay", "internet_archive", "mixkit"),
    ProviderCapability.PREVIEW_IMAGE: ("pexels", "wikimedia", "internet_archive"),
    ProviderCapability.LICENSE_METADATA: ("wikimedia", "internet_archive", "pixabay"),
    ProviderCapability.ATTRIBUTION_METADATA: (
        "wikimedia",
        "internet_archive",
        "pexels",
        "pixabay",
    ),
}


class MediaProviderRegistry:
    def __init__(self, providers: list[MediaProvider] | None = None) -> None:
        self._providers: dict[str, MediaProvider] = {}
        for p in providers or []:
            self.register(p)

    def register(self, provider: MediaProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, name: str) -> MediaProvider | None:
        return self._providers.get(name)

    def all(self) -> list[MediaProvider]:
        return list(self._providers.values())

    def enabled(self) -> list[MediaProvider]:
        return [p for p in self._providers.values() if p.is_enabled()]

    def status(self) -> dict[str, dict]:
        out = {}
        for name, p in self._providers.items():
            out[name] = {
                "enabled": p.is_enabled(),
                "health": p.health.value,
                "reliability": p.reliability,
                "capabilities": [c.value for c in p.capabilities],
                "last_failure": p.last_failure,
            }
        return out

    def providers_for(
        self,
        capability: ProviderCapability,
        *,
        semantic_domain: str = "",
        archive_preference: bool = False,
        include_disabled: bool = False,
    ) -> list[MediaProvider]:
        """Return enabled providers supporting capability, ordered by priority."""
        _ = semantic_domain  # reserved for future domain bias
        names = list(_PRIORITY.get(capability, ()))
        if archive_preference:
            # Prefer archive providers first when requested
            archive_first = [n for n in ("wikimedia", "internet_archive") if n in names]
            rest = [n for n in names if n not in archive_first]
            names = archive_first + rest

        result: list[MediaProvider] = []
        for name in names:
            p = self._providers.get(name)
            if not p:
                continue
            if not p.supports(capability):
                continue
            if not include_disabled and not p.is_enabled():
                continue
            result.append(p)
        # Also include any registered provider with capability not in priority list
        for p in self._providers.values():
            if p in result:
                continue
            if not p.supports(capability):
                continue
            if not include_disabled and not p.is_enabled():
                continue
            result.append(p)
        return result


def default_registry() -> MediaProviderRegistry:
    reg = MediaProviderRegistry()
    for p in (
        PexelsProvider(),
        PixabayProvider(),
        WikimediaProvider(),
        InternetArchiveProvider(),
        MixkitProvider(),
    ):
        reg.register(p)
    return reg
