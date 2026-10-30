"""Fal/Kling adapter — wraps existing ai_video_engine without rebuilding it.

Live calls gated by STAGE_E_LIVE_GENERATION=true. Default provider remains mock.
"""
from __future__ import annotations

from pathlib import Path

from app.documentary_v2.recovery.generation_base import (
    GeneratedVideoProvider,
    GenerationResult,
    ProviderCapabilities,
)
from app.documentary_v2.schemas import GeneratedVisualPlan


class FalKlingGeneratedVideoProvider(GeneratedVideoProvider):
    name = "fal_kling"

    def __init__(self) -> None:
        self.capabilities = ProviderCapabilities(
            provider_id="fal_kling",
            supports_text_to_video=True,
            max_duration_sec=5.0,
            aspect_ratios=["9:16", "16:9", "1:1"],
            resolutions=["1080x1920"],
            pricing_note="fal_kling_on_demand",
            estimated_usd_per_second=0.05,  # conservative placeholder
        )

    def estimate_cost(self, plan: GeneratedVisualPlan) -> float:
        dur = min(float(plan.duration or 4.0), self.capabilities.max_duration_sec)
        return round(dur * self.capabilities.estimated_usd_per_second, 4)

    def generate(self, plan: GeneratedVisualPlan, *, output_dir: str) -> GenerationResult:
        from app.config import config

        if not config.STAGE_E_LIVE_GENERATION:
            return GenerationResult(
                ok=False,
                provider=self.name,
                error="live_generation_disabled",
                estimated_cost_usd=self.estimate_cost(plan),
            )
        if not plan.generation_allowed:
            return GenerationResult(ok=False, provider=self.name, error="generation_not_allowed")
        if plan.evidence_prohibited is False:
            # Hard rule: this adapter never produces evidence footage
            return GenerationResult(
                ok=False,
                provider=self.name,
                error="adapter_refuses_evidence_role",
            )
        fal_key = getattr(config, "FAL_KEY", "") or ""
        if not fal_key:
            return GenerationResult(ok=False, provider=self.name, error="missing_FAL_KEY")

        est = self.estimate_cost(plan)
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{plan.plan_id.replace(':', '_')}_kling.mp4"

        from app.ai_video_engine import generate_kling_video_clip

        try:
            result_path = generate_kling_video_clip(
                prompt=plan.prompt,
                output_path=str(path),
                fal_key=fal_key,
                duration=min(5, max(3, int(plan.duration or 4))),
                aspect_ratio=plan.aspect_ratio or "9:16",
            )
        except Exception as exc:
            return GenerationResult(
                ok=False,
                provider=self.name,
                error=str(exc)[:300],
                estimated_cost_usd=est,
            )
        if not result_path:
            return GenerationResult(
                ok=False,
                provider=self.name,
                error="kling_returned_none",
                estimated_cost_usd=est,
            )
        return GenerationResult(
            ok=True,
            job_id=f"fal:{plan.plan_id}",
            status="succeeded",
            local_path=str(result_path),
            provider=self.name,
            model="kling-v2.5-turbo-pro",
            estimated_cost_usd=est,
            actual_cost_usd=est,
            duration_sec=float(plan.duration or 4),
            synthetic=True,
            evidence_prohibited=True,
        )


def build_generated_video_provider(name: str | None = None) -> GeneratedVideoProvider:
    from app.config import config
    from app.documentary_v2.recovery.generation_mock import MockGeneratedVideoProvider

    key = (name or config.GENERATED_VIDEO_PROVIDER or "mock").lower()
    if key in {"fal", "fal_kling", "kling"}:
        return FalKlingGeneratedVideoProvider()
    return MockGeneratedVideoProvider()
