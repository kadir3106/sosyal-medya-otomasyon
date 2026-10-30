"""Stage F — EDL / timeline / assembly / critic / repair.

Isolated from default /generate. Enable only via STAGE_F_RUN / explicit orchestrator.
DOCUMENTARY_ENGINE_V2 remains OFF by default.
"""

from app.documentary_v2.assembly.timeline import compile_edl
from app.documentary_v2.assembly.orchestrator import run_stage_f_pipeline

__all__ = ["compile_edl", "run_stage_f_pipeline"]
