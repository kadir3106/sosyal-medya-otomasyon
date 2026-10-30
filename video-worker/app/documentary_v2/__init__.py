"""Documentary Engine V2 package (Stage A: schemas + telemetry + flag)."""

from app.documentary_v2.pipeline_mode import (
    V2_EXECUTION_ACTIVE,
    documentary_engine_v2_enabled,
    pipeline_mode_diagnostics,
    resolve_pipeline_mode,
    warn_if_legacy_stock,
)
from app.documentary_v2.schemas import (
    SCHEMA_VERSION,
    PipelineMode,
    ProductionManifest,
)
from app.documentary_v2.telemetry import emit_legacy_job_manifest

__all__ = [
    "SCHEMA_VERSION",
    "PipelineMode",
    "ProductionManifest",
    "V2_EXECUTION_ACTIVE",
    "documentary_engine_v2_enabled",
    "pipeline_mode_diagnostics",
    "resolve_pipeline_mode",
    "warn_if_legacy_stock",
    "emit_legacy_job_manifest",
]
