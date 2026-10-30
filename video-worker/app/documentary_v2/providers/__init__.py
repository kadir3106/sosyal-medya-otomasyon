"""Stage B media provider fabric — candidate acquisition only."""

from app.documentary_v2.providers.acquisition import acquire_candidates
from app.documentary_v2.providers.registry import (
    MediaProviderRegistry,
    default_registry,
)

__all__ = [
    "MediaProviderRegistry",
    "acquire_candidates",
    "default_registry",
]
