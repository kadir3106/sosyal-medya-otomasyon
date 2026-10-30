"""Stage C VisualVerifier — pixels must verify; metadata may only propose."""

from app.documentary_v2.verifier.service import verify_candidate, verify_shortlist
from app.documentary_v2.verifier.base import VisualVerifierProvider

__all__ = [
    "VisualVerifierProvider",
    "verify_candidate",
    "verify_shortlist",
]
