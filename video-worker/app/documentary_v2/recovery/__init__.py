"""Stage E — Visual Recovery Generation Layer.

Isolated from /generate. V2 remains OFF. No full documentary render / publish.
"""

from app.documentary_v2.recovery.engine import VisualRecoveryEngine, RecoveryResult
from app.documentary_v2.recovery.types import RecoveryStrategy, SyntheticSuitability

__all__ = [
    "VisualRecoveryEngine",
    "RecoveryResult",
    "RecoveryStrategy",
    "SyntheticSuitability",
]
