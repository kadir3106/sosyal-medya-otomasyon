"""Mock GeneratedVideoProvider — no spend; deterministic offline artifact."""
from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from app.documentary_v2.recovery.generation_base import (
    GeneratedVideoProvider,
    GenerationResult,
    ProviderCapabilities,
)
from app.documentary_v2.schemas import GeneratedVisualPlan


class MockGeneratedVideoProvider(GeneratedVideoProvider):
    name = "mock"

    def __init__(self) -> None:
        self.capabilities = ProviderCapabilities(
            provider_id="mock",
            supports_text_to_video=True,
            max_duration_sec=5.0,
            pricing_note="free_mock",
            estimated_usd_per_second=0.0,
        )
        self.calls = 0

    def estimate_cost(self, plan: GeneratedVisualPlan) -> float:
        return 0.0

    def generate(self, plan: GeneratedVisualPlan, *, output_dir: str) -> GenerationResult:
        self.calls += 1
        if not plan.generation_allowed:
            return GenerationResult(
                ok=False,
                provider=self.name,
                error="generation_not_allowed",
                evidence_prohibited=True,
            )
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{plan.plan_id.replace(':', '_')}_mock.mp4"
        # Tiny valid vertical clip — clearly synthetic illustration marker
        frames_dir = out / f"_frames_{plan.plan_id.replace(':', '_')}"
        frames_dir.mkdir(exist_ok=True)
        duration = min(float(plan.duration or 2.0), 3.0)
        fps = 24
        n = max(12, int(duration * fps))
        for i in range(n):
            img = Image.new("RGB", (720, 1280), (12, 14, 22))
            d = ImageDraw.Draw(img)
            d.text((40, 80), "SYNTHETIC ILLUSTRATION", fill=(200, 180, 80))
            d.text((40, 140), (plan.subject or plan.visual_purpose or "concept")[:40], fill=(230, 230, 230))
            d.text((40, 1100), "NOT DOCUMENTARY EVIDENCE", fill=(160, 160, 170))
            img.save(frames_dir / f"f_{i:04d}.png")
        cmd = [
            "ffmpeg", "-y", "-framerate", str(fps),
            "-i", str(frames_dir / "f_%04d.png"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-t", str(duration),
            str(path),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        for p in frames_dir.glob("*"):
            p.unlink(missing_ok=True)
        frames_dir.rmdir()
        if proc.returncode != 0:
            return GenerationResult(ok=False, provider=self.name, error="ffmpeg_failed")
        return GenerationResult(
            ok=True,
            job_id=f"mock:{plan.plan_id}",
            status="succeeded",
            local_path=str(path),
            provider=self.name,
            model="mock-v1",
            estimated_cost_usd=0.0,
            actual_cost_usd=0.0,
            duration_sec=duration,
            synthetic=True,
            evidence_prohibited=True,
            details={"prompt_excerpt": (plan.prompt or "")[:120]},
        )
