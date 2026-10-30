"""VisualVerifierProvider abstraction — model-agnostic."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from app.documentary_v2.schemas import VisualPreviewBundle, VisualVerificationRequest


class VisualVerifierProvider(ABC):
    name: str = ""
    model: str = ""

    @abstractmethod
    def observe(
        self,
        request: VisualVerificationRequest,
        bundle: VisualPreviewBundle,
    ) -> dict[str, Any]:
        """Return structured observation dict (not final ACCEPT/REJECT)."""
        ...

    @property
    def available(self) -> bool:
        return True
