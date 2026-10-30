"""GeneratedVideoProvider — vendor-neutral generation abstraction."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from app.documentary_v2.schemas import GeneratedVisualPlan


@dataclass
class ProviderCapabilities:
    provider_id: str
    supports_text_to_video: bool = True
    supports_image_to_video: bool = False
    max_duration_sec: float = 5.0
    aspect_ratios: list[str] = field(default_factory=lambda: ["9:16", "16:9", "1:1"])
    resolutions: list[str] = field(default_factory=lambda: ["1080x1920"])
    pricing_note: str = ""
    estimated_usd_per_second: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GenerationResult:
    ok: bool
    job_id: str = ""
    status: str = ""  # queued|running|succeeded|failed
    local_path: str = ""
    remote_url: str = ""
    provider: str = ""
    model: str = ""
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    duration_sec: float | None = None
    error: str = ""
    synthetic: bool = True
    evidence_prohibited: bool = True
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class GeneratedVideoProvider(ABC):
    name: str = ""
    capabilities: ProviderCapabilities

    @abstractmethod
    def estimate_cost(self, plan: GeneratedVisualPlan) -> float:
        ...

    @abstractmethod
    def generate(self, plan: GeneratedVisualPlan, *, output_dir: str) -> GenerationResult:
        ...

    def get_status(self, job_id: str) -> GenerationResult:
        return GenerationResult(ok=False, job_id=job_id, status="unknown", error="not_implemented")

    def materialize(self, result: GenerationResult, *, output_path: str) -> GenerationResult:
        return result
