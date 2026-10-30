"""Recovery strategy + synthetic suitability enums."""
from __future__ import annotations

from enum import Enum


class RecoveryStrategy(str, Enum):
    REAL_MEDIA = "REAL_MEDIA"
    ARCHIVE_MEDIA = "ARCHIVE_MEDIA"
    DOCUMENT_EVIDENCE = "DOCUMENT_EVIDENCE"
    MOTION_GRAPHIC = "MOTION_GRAPHIC"
    SYNTHETIC_VIDEO = "SYNTHETIC_VIDEO"
    SYNTHETIC_IMAGE = "SYNTHETIC_IMAGE"
    ARCHIVAL_STILL = "ARCHIVAL_STILL"
    UNCOVERED = "UNCOVERED"


class SyntheticSuitability(str, Enum):
    SAFE_FOR_SYNTHETIC = "SAFE_FOR_SYNTHETIC"
    ILLUSTRATIVE_ONLY = "ILLUSTRATIVE_ONLY"
    UNSAFE_AS_SYNTHETIC_EVIDENCE = "UNSAFE_AS_SYNTHETIC_EVIDENCE"
    REAL_MEDIA_REQUIRED = "REAL_MEDIA_REQUIRED"


MOTION_PRIMITIVES = (
    "RelationshipGraph",
    "Timeline",
    "MapHighlight",
    "DocumentHighlight",
    "EvidenceCard",
    "Counter",
    "Comparison",
    "EntityFlow",
    "QuoteEvidence",
)
