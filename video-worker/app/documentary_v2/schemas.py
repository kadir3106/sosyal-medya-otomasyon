"""Documentary Engine V2 — canonical schemas (Stage A).

Stable contracts for later stages. Stage A does not change production visuals.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


SCHEMA_VERSION = "1"
PIPELINE_VERSION_V2 = "documentary-v2"
PIPELINE_VERSION_LEGACY = "legacy"


class PipelineMode(str, Enum):
    LEGACY_STOCK = "LEGACY_STOCK"
    LEGACY_DIRECTOR = "LEGACY_DIRECTOR"
    DOCUMENTARY_V2 = "DOCUMENTARY_V2"


class LicenseState(str, Enum):
    """Unknown must never be silently treated as reusable."""

    UNKNOWN = "UNKNOWN"
    PUBLIC_DOMAIN = "PUBLIC_DOMAIN"
    CC0 = "CC0"
    CC_BY = "CC_BY"
    CC_BY_SA = "CC_BY_SA"
    STOCK_LICENSED = "STOCK_LICENSED"
    PROPRIETARY = "PROPRIETARY"
    RESTRICTED = "RESTRICTED"


class MediaType(str, Enum):
    STOCK_VIDEO = "stock_video"
    ARCHIVE_VIDEO = "archive_video"
    STOCK_PHOTO = "stock_photo"
    ARCHIVE_STILL = "archive_still"
    DOCUMENT = "document"
    MOTION_GRAPHIC = "motion_graphic"
    GENERATED_VIDEO = "generated_video"
    GENERATED_STILL = "generated_still"
    OTHER = "other"


class AssetOrigin(str, Enum):
    STOCK = "stock"
    ARCHIVE = "archive"
    EVIDENCE = "evidence"
    GENERATED = "generated"
    MOTION_GRAPHIC = "motion_graphic"
    UNKNOWN = "unknown"


class GateResult(str, Enum):
    PASS = "PASS"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"


# ── Stage B: acquisition / license / dedup ─────────────────────────────


class ProviderCapability(str, Enum):
    VIDEO_SEARCH = "VIDEO_SEARCH"
    IMAGE_SEARCH = "IMAGE_SEARCH"
    ARCHIVE_SEARCH = "ARCHIVE_SEARCH"
    DOCUMENT_SEARCH = "DOCUMENT_SEARCH"
    PREVIEW_VIDEO = "PREVIEW_VIDEO"
    PREVIEW_IMAGE = "PREVIEW_IMAGE"
    LICENSE_METADATA = "LICENSE_METADATA"
    ATTRIBUTION_METADATA = "ATTRIBUTION_METADATA"


class ProviderHealth(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    AUTH_MISSING = "AUTH_MISSING"


class QueryFamily(str, Enum):
    ENTITY_EXACT = "ENTITY_EXACT"
    ENTITY_ACTION = "ENTITY_ACTION"
    ENTITY_CONTEXT = "ENTITY_CONTEXT"
    LOCATION = "LOCATION"
    ARCHIVE = "ARCHIVE"
    EVIDENCE = "EVIDENCE"
    DOCUMENT = "DOCUMENT"
    CONCEPTUAL = "CONCEPTUAL"


class LicensePolicy(str, Enum):
    """Normalized reuse policy — raw provider license string is preserved separately."""

    KNOWN_REUSABLE = "KNOWN_REUSABLE"
    KNOWN_RESTRICTED = "KNOWN_RESTRICTED"
    ATTRIBUTION_REQUIRED = "ATTRIBUTION_REQUIRED"
    UNKNOWN = "UNKNOWN"


class DuplicateKind(str, Enum):
    EXACT_DUPLICATE = "EXACT_DUPLICATE"
    LIKELY_DUPLICATE = "LIKELY_DUPLICATE"
    UNIQUE = "UNIQUE"
    UNKNOWN = "UNKNOWN"


@dataclass
class PreviewReference:
    """Cheap preview for Stage C — not a materialized MediaAsset."""

    candidate_id: str
    preview_url: str = ""
    preview_kind: str = ""  # image_thumb|video_preview|bounded_sample
    width: int | None = None
    height: int | None = None
    duration_sec: float | None = None
    local_path: str = ""  # only if a tiny sample was cached

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MediaSearchRequest:
    query: str
    query_family: str = ""
    target_entities: list[str] = field(default_factory=list)
    target_concept: str = ""
    semantic_domain: str = ""
    preferred_media_types: list[str] = field(default_factory=list)
    motion_requirement: str = ""
    authenticity_requirement: str = ""
    archive_preference: bool = False
    min_duration: float | None = None
    max_duration: float | None = None
    orientation: str = ""  # portrait|landscape|any
    result_limit: int = 8
    license_policy: str = LicensePolicy.UNKNOWN.value
    job_id: str = ""
    beat_id: str = ""
    shot_id: str = ""
    shot_requirement_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DuplicateRelation:
    left_candidate_id: str
    right_candidate_id: str
    kind: str = DuplicateKind.UNKNOWN.value
    confidence: float = 0.0
    evidence: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AcquisitionCounts:
    """Keep source uniqueness distinct from visual-information uniqueness."""

    search_result_count: int = 0
    candidate_count: int = 0
    unique_candidate_count: int = 0
    materialized_asset_count: int = 0
    unique_source_asset_count: int = 0
    visual_information_unit_count: int = 0  # Stage C fills; Stage B leaves 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ProviderSearchEvent:
    provider: str
    job_id: str = ""
    beat_id: str = ""
    shot_id: str = ""
    query: str = ""
    query_family: str = ""
    latency_ms: float | None = None
    raw_result_count: int = 0
    deduped_result_count: int = 0
    status: str = ProviderHealth.AVAILABLE.value
    failure_reason: str = ""
    candidate_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AttributionEntry:
    asset_id: str = ""
    candidate_id: str = ""
    provider: str = ""
    source_url: str = ""
    creator: str = ""
    creator_url: str = ""
    license: str = LicenseState.UNKNOWN.value
    license_url: str = ""
    license_policy: str = LicensePolicy.UNKNOWN.value
    attribution_text: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _as_dict(obj: Any) -> Any:
    if obj is None:
        return None
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "to_dict"):
        return obj.to_dict()
    if isinstance(obj, list):
        return [_as_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _as_dict(v) for k, v in obj.items()}
    return obj


@dataclass
class AssetProvenance:
    provider: str = ""
    source_id: str = ""
    source_url: str = ""
    download_url: str = ""
    preview_url: str = ""
    media_type: str = MediaType.OTHER.value
    duration: float | None = None
    width: int | None = None
    height: int | None = None
    creator: str = ""
    creator_url: str = ""
    license: str = LicenseState.UNKNOWN.value
    license_url: str = ""
    license_raw: str = ""
    license_policy: str = "UNKNOWN"
    attribution: str = ""
    synthetic: bool = False
    archive: bool = False
    stock: bool = False
    content_fingerprint: str = ""
    retrieved_at: str = ""  # ISO-8601 UTC

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict | None) -> "AssetProvenance":
        d = d or {}
        lic = str(d.get("license") or LicenseState.UNKNOWN.value)
        if not lic.strip():
            lic = LicenseState.UNKNOWN.value
        return cls(
            provider=str(d.get("provider") or ""),
            source_id=str(d.get("source_id") or d.get("asset_id") or ""),
            source_url=str(d.get("source_url") or d.get("url") or ""),
            download_url=str(d.get("download_url") or ""),
            preview_url=str(d.get("preview_url") or ""),
            media_type=str(d.get("media_type") or d.get("kind") or MediaType.OTHER.value),
            duration=float(d["duration"]) if d.get("duration") is not None else None,
            width=int(d["width"]) if d.get("width") is not None else None,
            height=int(d["height"]) if d.get("height") is not None else None,
            creator=str(d.get("creator") or d.get("user") or d.get("photographer") or ""),
            creator_url=str(d.get("creator_url") or ""),
            license=lic,
            license_url=str(d.get("license_url") or ""),
            license_raw=str(d.get("license_raw") or ""),
            license_policy=str(d.get("license_policy") or "UNKNOWN"),
            attribution=str(d.get("attribution") or ""),
            synthetic=bool(d.get("synthetic")),
            archive=bool(d.get("archive")),
            stock=bool(d.get("stock", not d.get("synthetic") and not d.get("archive"))),
            content_fingerprint=str(d.get("content_fingerprint") or d.get("fingerprint") or ""),
            retrieved_at=str(d.get("retrieved_at") or ""),
        )


@dataclass
class ResearchPack:
    topic: str = ""
    sources: list[dict] = field(default_factory=list)
    notes: str = ""
    research_pack_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerifiedClaim:
    claim_id: str
    text: str
    claim_type: str = ""
    risk: str = ""
    status: str = "unknown"  # supported|unsupported|partial|unknown
    evidence: list[dict] = field(default_factory=list)
    narrative_role: str = ""
    semantic_domain: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VerifiedStory:
    story_id: str
    topic: str
    raw_script: str = ""
    final_script: str = ""
    hook: str = ""
    setup: str = ""
    development: str = ""
    reveal: str = ""
    evidence: str = ""
    payoff: str = ""
    loop: str = ""
    claim_ids: list[str] = field(default_factory=list)
    estimated_duration_sec: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class StoryBeat:
    beat_id: str
    spoken_span: str = ""
    narrative_role: str = ""
    primary_entities: list[str] = field(default_factory=list)
    secondary_entities: list[str] = field(default_factory=list)
    semantic_domain: str = ""
    claim_ids: list[str] = field(default_factory=list)
    story_function: str = ""
    required_visual_concept: str = ""
    visual_purpose: str = ""
    motion_requirement: str = ""
    evidence_requirement: str = ""
    authenticity_requirement: str = ""
    preferred_media_types: list[str] = field(default_factory=list)
    forbidden_visual_concepts: list[str] = field(default_factory=list)
    estimated_duration: float | None = None
    fallback_policy: str = ""
    importance: str = "supporting"  # important|supporting|fragment
    start_time: float | None = None  # joinable timeline (sec)
    end_time: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ShotRequirement:
    shot_requirement_id: str
    beat_id: str
    subject: str = ""
    action: str = ""
    location: str = ""
    time_context: str = ""
    required_entities: list[str] = field(default_factory=list)
    optional_entities: list[str] = field(default_factory=list)
    required_visual_concept: str = ""
    visual_purpose: str = ""  # IDENTIFY_ENTITY|SHOW_PERSON|SHOW_PRODUCT|...
    evidence_role: str = ""  # EVIDENCE_REQUIRED|AUTHENTIC_CONTEXT_REQUIRED|ILLUSTRATION_ACCEPTABLE|DECORATIVE_NOT_ALLOWED
    preferred_media_type: str = ""
    preferred_media_types: list[str] = field(default_factory=list)
    motion_requirement: str = ""  # REQUIRED|PREFERRED|OPTIONAL|NOT_NEEDED
    authenticity_requirement: str = ""
    strict_entity_mode: bool = False
    generation_allowed: bool = False
    forbidden_visual_concepts: list[str] = field(default_factory=list)
    search_intents: list[str] = field(default_factory=list)
    fallback_ladder: list[str] = field(default_factory=list)
    fallback_policy: str = ""
    avoid_concepts: list[str] = field(default_factory=list)
    semantic_domain: str = ""
    narrative_role: str = ""
    estimated_duration: float | None = None
    importance: str = "supporting"  # important|supporting|fragment
    claim_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SearchIntent:
    intent_id: str
    beat_id: str
    shot_requirement_id: str
    query: str
    query_family: str = ""
    semantic_domain: str = ""
    target_concept: str = ""
    target_entities: list[str] = field(default_factory=list)
    preferred_media_types: list[str] = field(default_factory=list)
    archive_preference: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MediaCandidate:
    candidate_id: str
    shot_requirement_id: str = ""
    provenance: AssetProvenance = field(default_factory=AssetProvenance)
    query: str = ""
    query_family: str = ""
    prefilter_score: float | None = None
    rejection_reason: str = ""
    # Stage B acquisition extras (still a candidate — not an asset)
    preview_url: str = ""
    download_url: str = ""
    creator_url: str = ""
    license_url: str = ""
    license_raw: str = ""
    license_policy: str = "UNKNOWN"
    duplicate_kind: str = "UNIQUE"
    duplicate_of: str = ""
    content_fingerprint: str = ""
    perceptual_fingerprint: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = self.provenance.to_dict()
        return d


@dataclass
class MediaAsset:
    asset_id: str
    provenance: AssetProvenance = field(default_factory=AssetProvenance)
    local_path: str = ""
    origin: str = AssetOrigin.UNKNOWN.value
    visual_information_id: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["provenance"] = self.provenance.to_dict()
        return d


@dataclass
class VisualVerification:
    """Stage C VisualVerifier result — pixels decide, metadata may only propose."""

    verification_id: str
    candidate_id: str = ""
    asset_id: str = ""
    shot_requirement_id: str = ""
    job_id: str = ""
    beat_id: str = ""
    shot_id: str = ""
    # ACCEPT | REJECT | UNCERTAIN | NOT_RUN
    decision: str = "NOT_RUN"
    status: str = "NOT_RUN"  # alias of decision for Stage A compat
    confidence: float | None = None
    # Pixel observations (what is ACTUALLY visible)
    visible_entities: list[str] = field(default_factory=list)
    visible_objects: list[str] = field(default_factory=list)
    visible_actions: list[str] = field(default_factory=list)
    visible_setting: str = ""
    visible_action: str = ""  # Stage A compat
    visible_location: str = ""
    visible_text_summary: str = ""
    motion_description: str = ""
    dominant_visual_concept: str = ""
    # Alignments: NONE|WEAK|PARTIAL|STRONG|EXACT|UNKNOWN
    entity_alignment: str = "UNKNOWN"
    concept_alignment: str = "UNKNOWN"
    action_alignment: str = "UNKNOWN"
    location_alignment: str = "UNKNOWN"
    # Product/company hierarchy: EXACT_ENTITY|RELATED_CATEGORY|GENERIC_CATEGORY|UNRELATED|UNKNOWN
    entity_specificity: str = "UNKNOWN"
    motion_value: str = "UNKNOWN"  # STATIC_VIDEO|MINIMAL_CAMERA_MOTION|...
    evidence_value: str = "UNKNOWN"  # EVIDENCE|AUTHENTIC_CONTEXT|ILLUSTRATION|...
    authenticity_support: str = "UNKNOWN"
    genericness: str = "UNKNOWN"  # LOW|MEDIUM|HIGH|UNKNOWN
    contradictions: list[str] = field(default_factory=list)
    forbidden_concept_hits: list[str] = field(default_factory=list)
    metadata_visual_conflict: bool = False
    metadata_supported_claims: list[str] = field(default_factory=list)
    visual_supported_claims: list[str] = field(default_factory=list)
    entity_presence_ratio: float | None = None  # approx 0..1
    concept_presence_ratio: float | None = None
    reason_codes: list[str] = field(default_factory=list)
    explanation_short: str = ""
    supports_narration: bool | None = None
    generic_filler: bool | None = None
    contradiction: bool | None = None
    evidence_vs_illustration: str = ""
    notes: str = ""
    # Verifier provider meta (no secrets)
    verifier_provider: str = ""
    verifier_model: str = ""
    preview_frame_count: int = 0
    preview_duration_sec: float | None = None
    latency_ms: float | None = None
    cache_hit: bool = False
    estimated_cost: float | None = None
    schema_version: str = SCHEMA_VERSION
    prompt_version: str = "visual-verifier-v1"
    verified_at: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Keep status mirrored for older consumers
        if self.decision and self.decision != "NOT_RUN":
            d["status"] = self.decision
        return d


@dataclass
class VisualVerificationRequest:
    verification_id: str
    job_id: str = ""
    beat_id: str = ""
    shot_id: str = ""
    candidate_id: str = ""
    required_visual_concept: str = ""
    semantic_domain: str = ""
    narrative_role: str = ""
    required_entities: list[str] = field(default_factory=list)
    optional_entities: list[str] = field(default_factory=list)
    required_action: str = ""
    required_location: str = ""
    motion_requirement: str = ""
    evidence_requirement: str = ""
    authenticity_requirement: str = ""
    preferred_media_type: str = ""
    forbidden_visual_concepts: list[str] = field(default_factory=list)
    strict_entity_mode: bool = False
    context_narration: str = ""
    # Retrieval context — NEVER treated as visual truth
    retrieval_context: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    def intent_signature(self) -> str:
        import hashlib
        import json

        payload = {
            "concept": self.required_visual_concept,
            "domain": self.semantic_domain,
            "entities": sorted(self.required_entities),
            "action": self.required_action,
            "location": self.required_location,
            "motion": self.motion_requirement,
            "evidence": self.evidence_requirement,
            "forbidden": sorted(self.forbidden_visual_concepts),
            "strict": self.strict_entity_mode,
        }
        raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(raw.encode()).hexdigest()[:24]


@dataclass
class PreviewFrame:
    timestamp_sec: float
    path: str = ""
    perceptual_hash: str = ""
    source: str = ""  # uniform|scene_change|thumbnail

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class VisualPreviewBundle:
    candidate_id: str
    media_kind: str = "image"  # image|video
    duration_sec: float | None = None
    width: int | None = None
    height: int | None = None
    frames: list[PreviewFrame] = field(default_factory=list)
    preview_clip_path: str = ""
    content_fingerprint: str = ""
    technical: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "candidate_id": self.candidate_id,
            "media_kind": self.media_kind,
            "duration_sec": self.duration_sec,
            "width": self.width,
            "height": self.height,
            "frames": [f.to_dict() for f in self.frames],
            "preview_clip_path": self.preview_clip_path,
            "content_fingerprint": self.content_fingerprint,
            "technical": dict(self.technical),
        }


@dataclass
class VisualInformationUnit:
    visual_information_id: str
    asset_id: str = ""
    entity: str = ""
    concept: str = ""
    action: str = ""
    evidence_role: str = ""
    media_type: str = ""
    authenticity: str = ""
    beat_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ShotSelection:
    shot_id: str
    beat_id: str
    asset_id: str = ""
    candidate_id: str = ""
    visual_information_id: str = ""
    shot_requirement_id: str = ""
    verification_id: str = ""
    selection_reason: str = ""
    why_selected: str = ""
    why_alternatives_lost: list[str] = field(default_factory=list)
    score_breakdown: dict = field(default_factory=dict)
    hard_requirements_satisfied: list[str] = field(default_factory=list)
    source_novelty: float | None = None
    reuse_count: int = 0
    visual_purpose: str = ""
    start_time: float | None = None
    end_time: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BeatCoverageReport:
    beat_id: str
    status: str = "UNCOVERED"  # COVERED|PARTIAL|UNCOVERED
    importance: str = "supporting"
    selected_shot_ids: list[str] = field(default_factory=list)
    required_concepts_satisfied: list[str] = field(default_factory=list)
    missing_requirements: list[str] = field(default_factory=list)
    verification_confidence: float | None = None
    evidence_coverage: str = ""
    motion_coverage: str = ""
    failure_reason: str = ""
    recovery_attempts: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RankedCandidate:
    candidate_id: str
    verification_id: str = ""
    eligible: bool = False
    hard_pass: bool = False
    hard_fail_reasons: list[str] = field(default_factory=list)
    soft_score: float = 0.0
    score_breakdown: dict = field(default_factory=dict)
    decision: str = ""
    rank: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DocumentaryDirectorPlan:
    """Stage D output — planning/selection only; no final render."""

    plan_id: str
    job_id: str = ""
    video_id: str = ""
    topic: str = ""
    story: dict | None = None
    beats: list[StoryBeat] = field(default_factory=list)
    shot_requirements: list[ShotRequirement] = field(default_factory=list)
    search_intents: list[SearchIntent] = field(default_factory=list)
    acquisition_summaries: list[dict] = field(default_factory=list)
    verifications: list[dict] = field(default_factory=list)
    ranked: list[RankedCandidate] = field(default_factory=list)
    selections: list[ShotSelection] = field(default_factory=list)
    visual_information_units: list[VisualInformationUnit] = field(default_factory=list)
    coverage: list[BeatCoverageReport] = field(default_factory=list)
    recovery_attempts: list[dict] = field(default_factory=list)
    motion_graphic_plans: list[MotionGraphicPlan] = field(default_factory=list)
    generated_visual_plans: list[GeneratedVisualPlan] = field(default_factory=list)
    diagnostics: dict = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    pipeline_version: str = "documentary-v2-stage-d"

    def to_dict(self) -> dict:
        return {
            "plan_id": self.plan_id,
            "job_id": self.job_id,
            "video_id": self.video_id,
            "topic": self.topic,
            "story": self.story,
            "beats": [b.to_dict() for b in self.beats],
            "shot_requirements": [s.to_dict() for s in self.shot_requirements],
            "search_intents": [s.to_dict() for s in self.search_intents],
            "acquisition_summaries": list(self.acquisition_summaries),
            "verifications": list(self.verifications),
            "ranked": [r.to_dict() for r in self.ranked],
            "selections": [s.to_dict() for s in self.selections],
            "visual_information_units": [v.to_dict() for v in self.visual_information_units],
            "coverage": [c.to_dict() for c in self.coverage],
            "recovery_attempts": list(self.recovery_attempts),
            "motion_graphic_plans": [m.to_dict() for m in self.motion_graphic_plans],
            "generated_visual_plans": [g.to_dict() for g in self.generated_visual_plans],
            "diagnostics": dict(self.diagnostics),
            "schema_version": self.schema_version,
            "pipeline_version": self.pipeline_version,
        }


@dataclass
class MotionGraphicPlan:
    """Evidence-bound motion graphic plan (Stage E expands Stage A skeleton)."""

    plan_id: str
    beat_id: str = ""
    shot_id: str = ""
    primitive: str = ""  # RelationshipGraph|Timeline|MapHighlight|DocumentHighlight|EvidenceCard|Counter|Comparison|EntityFlow|QuoteEvidence
    visual_purpose: str = ""
    nodes: list[str] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)  # must include claim_id+evidence_id per edge
    events: list[dict] = field(default_factory=list)  # timeline events with claim_id/evidence_id
    labels: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    source_reference: str = ""
    animation_type: str = ""
    duration: float | None = None
    verified: bool = False
    theme_id: str = "documentary_cinematic_v1"
    width: int = 1080
    height: int = 1920
    fps: int = 30
    caption_safe: dict = field(default_factory=lambda: {
        "top": 0.08, "bottom": 0.22, "left": 0.06, "right": 0.06
    })
    recovery_strategy: str = "MOTION_GRAPHIC"
    renderer: str = "internal_motion_graphics"
    template_version: str = "mg-v1"
    content_fingerprint: str = ""
    map_location: str = ""
    document_asset_id: str = ""  # required for DocumentHighlight
    number_claim_id: str = ""  # required for Counter
    explanatory_only: bool = True  # never impersonates official docs
    style: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class GeneratedVisualPlan:
    """Synthetic visual plan — never auto-trusted as documentary evidence."""

    plan_id: str
    beat_id: str = ""
    shot_id: str = ""
    prompt: str = ""
    visual_purpose: str = ""
    subject: str = ""
    action: str = ""
    environment: str = ""
    camera_intent: str = ""
    motion_intent: str = ""
    style_constraints: list[str] = field(default_factory=list)
    factual_constraints: list[str] = field(default_factory=list)
    forbidden_content: list[str] = field(default_factory=list)
    generation_allowed: bool = False
    synthetic: bool = True
    evidence_prohibited: bool = True
    synthetic_disclosure: str = "ILLUSTRATIVE_ONLY"  # SAFE_FOR_SYNTHETIC|ILLUSTRATIVE_ONLY|UNSAFE_AS_SYNTHETIC_EVIDENCE|REAL_MEDIA_REQUIRED
    provider: str = ""
    model: str = ""
    provider_preference: str = ""
    claim_ids: list[str] = field(default_factory=list)
    duration: float = 4.0
    aspect_ratio: str = "9:16"
    cost_ceiling_usd: float = 0.0
    estimated_cost_usd: float | None = None
    generation_justification: str = ""
    recovery_strategy: str = "SYNTHETIC_VIDEO"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RecoveryTelemetryEvent:
    """Stage E recovery telemetry — for future analytics, not conclusions."""

    beat_id: str
    shot_id: str = ""
    job_id: str = ""
    recovery_strategy: str = ""
    original_failure_reason: str = ""
    motion_graphic_plan_id: str = ""
    generated_visual_plan_id: str = ""
    provider: str = ""
    estimated_cost_usd: float | None = None
    actual_cost_usd: float | None = None
    latency_ms: float | None = None
    verification_decision: str = ""
    selected: bool = False
    claim_ids: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    artifact_path: str = ""
    synthetic_classification: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EditDecision:
    """Single timeline slot — renderer executes; does not invent selection."""

    shot_id: str
    beat_id: str
    edit_id: str = ""
    asset_id: str = ""
    visual_information_id: str = ""
    media_type: str = ""
    source_kind: str = ""  # stock|archive|generated|motion_graphic|document
    local_path: str = ""
    start_time: float = 0.0
    end_time: float = 0.0
    duration: float = 0.0
    source_in: float | None = None
    source_out: float | None = None
    fit_mode: str = "cover"  # cover|contain
    crop_policy: str = "safe_center"
    motion_policy: str = "preserve_native"  # preserve_native|subtle_push|none
    transition_in: str = "cut"
    transition_out: str = "cut"
    transition: str = "cut"  # Stage A compat
    visual_purpose: str = ""
    narrative_role: str = ""
    caption_safe_area: str = "bottom_reserved"
    evidence_role: str = ""
    synthetic: bool = False
    provenance_ref: str = ""
    verification_ref: str = ""
    audio_relationship: str = "under_narration"
    importance: str = "supporting"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EditDecisionList:
    edl_id: str
    job_id: str
    video_id: str
    decisions: list[EditDecision] = field(default_factory=list)
    total_duration_sec: float | None = None
    narration_duration_sec: float | None = None
    schema_version: str = SCHEMA_VERSION
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "edl_id": self.edl_id,
            "job_id": self.job_id,
            "video_id": self.video_id,
            "decisions": [d.to_dict() for d in self.decisions],
            "total_duration_sec": self.total_duration_sec,
            "narration_duration_sec": self.narration_duration_sec,
            "schema_version": self.schema_version,
            "notes": list(self.notes),
        }


@dataclass
class RenderManifest:
    render_id: str
    job_id: str
    video_id: str
    output_path: str = ""
    resolution: str = "1080x1920"
    fps: float | None = 30.0
    duration_sec: float | None = None
    edl_id: str = ""
    edl: dict = field(default_factory=dict)
    audio_narration_path: str = ""
    audio_bgm_path: str = ""
    audio_sfx_path: str = ""
    caption_path: str = ""
    asset_paths: list[str] = field(default_factory=list)
    recovery_asset_paths: list[str] = field(default_factory=list)
    music_track_id: str = ""
    music_mood: str = ""
    music_license: str = ""
    vocals_verified: bool = True
    duck_bgm: bool = True
    loudnorm: bool = True
    bgm_volume: float = 0.12
    transitions: list[str] = field(default_factory=list)
    provenance_refs: list[str] = field(default_factory=list)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class CriticFinding:
    finding_id: str
    start_sec: float
    end_sec: float
    beat_id: str = ""
    severity: str = "LOW"  # HIGH|MEDIUM|LOW
    issue_code: str = ""
    observation: str = ""
    recommended_repair: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FinalVideoCritique:
    critique_id: str
    job_id: str = ""
    video_path: str = ""
    decision: str = "REVIEW_REQUIRED"  # PASS|REVIEW_REQUIRED|FAIL
    findings: list[CriticFinding] = field(default_factory=list)
    dimensions: dict = field(default_factory=dict)
    latency_ms: float | None = None
    vlm_calls: int = 0
    estimated_cost_usd: float | None = None
    model: str = ""
    provider: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "critique_id": self.critique_id,
            "job_id": self.job_id,
            "video_path": self.video_path,
            "decision": self.decision,
            "findings": [f.to_dict() for f in self.findings],
            "dimensions": dict(self.dimensions),
            "latency_ms": self.latency_ms,
            "vlm_calls": self.vlm_calls,
            "estimated_cost_usd": self.estimated_cost_usd,
            "model": self.model,
            "provider": self.provider,
            "notes": self.notes,
        }


@dataclass
class BeatTelemetry:
    beat_id: str
    job_id: str
    video_id: str
    start_time: float | None = None
    end_time: float | None = None
    narrative_role: str = ""
    semantic_domain: str = ""
    entities: list[str] = field(default_factory=list)
    claim_ids: list[str] = field(default_factory=list)
    spoken_span: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ShotTelemetry:
    shot_id: str
    beat_id: str
    job_id: str
    video_id: str
    asset_id: str = ""
    visual_information_id: str = ""
    provider: str = ""
    media_type: str = ""
    origin: str = ""  # stock|archive|generated|motion_graphic
    synthetic: bool = False
    archive: bool = False
    stock: bool = False
    license: str = LicenseState.UNKNOWN.value
    source_url: str = ""
    start_time: float | None = None
    end_time: float | None = None
    reuse_count: int = 0
    verification_status: str = "NOT_RUN"
    verification_confidence: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ModelCallTelemetry:
    call_id: str
    job_id: str
    video_id: str
    stage: str = ""
    provider: str = ""
    model: str = ""
    latency_ms: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    estimated_cost: float | None = None
    fallback_depth: int = 0
    status: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        # Never allow secret-like keys to sneak in via extras
        return d


@dataclass
class QualityTelemetry:
    gate: str
    result: str = GateResult.NOT_RUN.value
    reason_codes: list[str] = field(default_factory=list)
    beat_ids: list[str] = field(default_factory=list)
    shot_ids: list[str] = field(default_factory=list)
    confidence: float | None = None
    details: dict = field(default_factory=dict)
    job_id: str = ""
    video_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class RenderTelemetry:
    job_id: str
    video_id: str
    duration_sec: float | None = None
    fps: float | None = None
    resolution: str = ""
    render_time_sec: float | None = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    job_id: str
    video_id: str
    gates: list[QualityTelemetry] = field(default_factory=list)
    overall: str = GateResult.NOT_RUN.value
    notes: str = ""

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "video_id": self.video_id,
            "overall": self.overall,
            "notes": self.notes,
            "gates": [g.to_dict() for g in self.gates],
        }


@dataclass
class ProductionManifest:
    """Joinable production package for future MİKO analytics (consume later)."""

    job_id: str
    video_id: str
    topic: str = ""
    content_category: str = ""
    platform_targets: list[str] = field(default_factory=list)
    duration_sec: float | None = None
    created_at: str = ""
    pipeline_mode: str = PipelineMode.LEGACY_STOCK.value
    documentary_engine_v2: bool = False
    pipeline_version: str = PIPELINE_VERSION_LEGACY
    schema_version: str = SCHEMA_VERSION
    research: ResearchPack | None = None
    story: VerifiedStory | None = None
    claims: list[VerifiedClaim] = field(default_factory=list)
    beats: list[StoryBeat] = field(default_factory=list)
    shot_requirements: list[ShotRequirement] = field(default_factory=list)
    assets: list[MediaAsset] = field(default_factory=list)
    visual_information_units: list[VisualInformationUnit] = field(default_factory=list)
    shot_selections: list[ShotSelection] = field(default_factory=list)
    beat_telemetry: list[BeatTelemetry] = field(default_factory=list)
    shot_telemetry: list[ShotTelemetry] = field(default_factory=list)
    model_calls: list[ModelCallTelemetry] = field(default_factory=list)
    quality: list[QualityTelemetry] = field(default_factory=list)
    render_telemetry: RenderTelemetry | None = None
    edl: EditDecisionList | None = None
    render_manifest: RenderManifest | None = None
    quality_report: QualityReport | None = None

    def to_dict(self) -> dict:
        return {
            "job_id": self.job_id,
            "video_id": self.video_id,
            "topic": self.topic,
            "content_category": self.content_category,
            "platform_targets": list(self.platform_targets),
            "duration_sec": self.duration_sec,
            "created_at": self.created_at,
            "pipeline_mode": self.pipeline_mode,
            "documentary_engine_v2": self.documentary_engine_v2,
            "pipeline_version": self.pipeline_version,
            "schema_version": self.schema_version,
            "research": self.research.to_dict() if self.research else None,
            "story": self.story.to_dict() if self.story else None,
            "claims": [c.to_dict() for c in self.claims],
            "beats": [b.to_dict() for b in self.beats],
            "shot_requirements": [s.to_dict() for s in self.shot_requirements],
            "assets": [a.to_dict() for a in self.assets],
            "visual_information_units": [v.to_dict() for v in self.visual_information_units],
            "shot_selections": [s.to_dict() for s in self.shot_selections],
            "beat_telemetry": [b.to_dict() for b in self.beat_telemetry],
            "shot_telemetry": [s.to_dict() for s in self.shot_telemetry],
            "model_calls": [m.to_dict() for m in self.model_calls],
            "quality": [q.to_dict() for q in self.quality],
            "render_telemetry": self.render_telemetry.to_dict() if self.render_telemetry else None,
            "edl": self.edl.to_dict() if self.edl else None,
            "render_manifest": self.render_manifest.to_dict() if self.render_manifest else None,
            "quality_report": self.quality_report.to_dict() if self.quality_report else None,
        }

    @staticmethod
    def assert_no_secrets(payload: dict) -> list[str]:
        """Return list of suspicious keys if any secret-like fields leaked."""
        banned = (
            "api_key",
            "apikey",
            "access_token",
            "refresh_token",
            "secret",
            "password",
            "authorization",
            "bearer",
        )
        found: list[str] = []

        def walk(obj: Any, path: str = "") -> None:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    lk = str(k).lower()
                    p = f"{path}.{k}" if path else str(k)
                    if any(b in lk for b in banned):
                        found.append(p)
                    walk(v, p)
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    walk(v, f"{path}[{i}]")

        walk(payload)
        return found
