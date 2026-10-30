"""Pipeline mode resolution + startup diagnostics (Stage A)."""
from __future__ import annotations

import logging
import os

from app.documentary_v2.schemas import PipelineMode

logger = logging.getLogger(__name__)

# Stage A: V2 execution path is NOT active yet. Flag may be true for dry-run
# diagnostics only; production still uses legacy stock/director.
V2_EXECUTION_ACTIVE = False


def documentary_engine_v2_enabled() -> bool:
    return os.environ.get("DOCUMENTARY_ENGINE_V2", "false").lower() == "true"


def director_enabled() -> bool:
    return os.environ.get("DIRECTOR_ENABLED", "false").lower() == "true"


def resolve_pipeline_mode(
    *,
    documentary_v2: bool | None = None,
    director: bool | None = None,
    visual_engine: str | None = None,
    canary: bool = False,
) -> PipelineMode:
    """Explicit mode for every job — no silent ambiguity.

    DOCUMENTARY_V2 is returned only when the flag is on AND Stage execution
    is active. Stage A keeps V2_EXECUTION_ACTIVE=False so mode stays LEGACY_*.
    """
    if canary:
        return PipelineMode.DOCUMENTARY_V2_CANARY

    v2 = documentary_engine_v2_enabled() if documentary_v2 is None else documentary_v2
    dir_on = director_enabled() if director is None else director
    _ = visual_engine  # reserved for future LEGACY_AI_* modes

    if v2 and V2_EXECUTION_ACTIVE:
        return PipelineMode.DOCUMENTARY_V2
    if dir_on:
        return PipelineMode.LEGACY_DIRECTOR
    return PipelineMode.LEGACY_STOCK


def warn_if_legacy_stock(*, mode: PipelineMode | None = None) -> None:
    mode = mode or resolve_pipeline_mode()
    if mode == PipelineMode.LEGACY_STOCK:
        logger.warning(
            "DOCUMENTARY_ENGINE_V2 disabled (or V2 path inactive). "
            "Current production path = LEGACY_STOCK. "
            "This path does not use V2 VisualVerifier / EDL / FinalVideoCritic."
        )
        print(
            "WARNING: DOCUMENTARY_ENGINE_V2 disabled. "
            "Current production path = LEGACY_STOCK. "
            "This path does not use V2 VisualVerifier / EDL / FinalVideoCritic.",
            flush=True,
        )
    elif mode == PipelineMode.LEGACY_DIRECTOR:
        logger.info(
            "Production path = LEGACY_DIRECTOR "
            "(DOCUMENTARY_ENGINE_V2 execution not active)."
        )
    if documentary_engine_v2_enabled() and not V2_EXECUTION_ACTIVE:
        logger.warning(
            "DOCUMENTARY_ENGINE_V2=true but Stage A has no V2 execution path; "
            "falling through to %s.",
            mode.value,
        )


def pipeline_mode_diagnostics(*, canary: bool = False) -> dict:
    mode = resolve_pipeline_mode(canary=canary)
    return {
        "pipeline_mode": mode.value,
        "documentary_engine_v2": documentary_engine_v2_enabled(),
        "documentary_engine_v2_execution_active": V2_EXECUTION_ACTIVE,
        "director_enabled": director_enabled(),
        "visual_engine": os.environ.get("VISUAL_ENGINE", "stock"),
        "schema_version": "1",
        "pipeline_version": (
            "documentary-v2" if mode == PipelineMode.DOCUMENTARY_V2 else "legacy"
        ),
    }
