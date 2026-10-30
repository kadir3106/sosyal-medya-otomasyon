"""Storyboard coverage + visual information identity (storytelling correction).

A crop/zoom on the same asset is NOT new visual information.
Diversity is measured by visual_information_id changes, not transform count.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from typing import Any


MOTION_CONCEPTS = frozenset(
    {
        "finance",
        "location",
        "manufacturing",
        "factory",
        "market",
        "city",
        "machinery",
        "vehicle",
        "crowd",
        "product_operation",
        "historical_footage",
    }
)


@dataclass
class StoryBeatSpec:
    """Decision-first beat: what to SEE before any search."""

    spoken_span: str
    narrative_role: str
    primary_entity: str = ""
    factual_claim_id: str = ""
    required_visual_concept: str = ""
    preferred_media_type: str = "stock_video"
    evidence_role: str = "illustrative"  # proof|archive|document|location|product|contrast|atmosphere
    fallback_ladder: list[str] = field(default_factory=list)
    visual_information_id: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def compute_visual_information_id(
    *,
    asset_id: str | None = None,
    entity: str = "",
    concept: str = "",
    evidence_role: str = "",
    required_visual_concept: str = "",
    media_kind: str = "",
) -> str:
    """Stable id for 'what the viewer learns visually'.

    Same underlying photo with a different crop shares this id when
    asset_id is present. Different assets with the same coarse concept
    still get distinct ids when asset_id differs.
    """
    aid = (asset_id or "").strip()
    if aid:
        # Asset-bound: crop/zoom cannot mint a new id
        base = f"asset:{aid}"
        return hashlib.sha1(base.encode()).hexdigest()[:12]

    # Pre-retrieval / decision id (storyboard before fetch)
    parts = [
        (entity or "").strip().lower()[:40],
        (required_visual_concept or concept or "").strip().lower()[:40],
        (evidence_role or "").strip().lower()[:24],
        (media_kind or "").strip().lower()[:16],
    ]
    key = "|".join(p for p in parts if p) or "generic"
    return hashlib.sha1(f"decision:{key}".encode()).hexdigest()[:12]


def same_visual_information(a: str, b: str) -> bool:
    return bool(a) and bool(b) and a == b


def prefers_video_for_concept(concept: str, narrative_role: str = "") -> bool:
    c = (concept or "").lower()
    r = (narrative_role or "").lower()
    if r in {"place", "money"}:
        return True
    if any(m in c for m in MOTION_CONCEPTS):
        return True
    if re.search(r"\b(factory|manufactur|market|exchange|city|crowd|machine)\b", c):
        return True
    return False


def enrich_beat_dict(beat: dict) -> dict:
    """Add storytelling fields onto a beat/word_to_visual dict."""
    b = dict(beat or {})
    ents = b.get("primary_entities") or b.get("entities") or []
    entity = ""
    if isinstance(ents, list) and ents:
        entity = str(ents[0])
    concept = str(b.get("concept") or "")
    role = str(b.get("narrative_role") or "")
    evidence = str(b.get("evidence_role") or _infer_evidence_role(concept, role, str(b.get("spoken_span") or "")))
    required = str(
        b.get("required_visual_concept")
        or b.get("visual_intent")
        or _required_concept(entity, concept, role, evidence)
    )
    b["evidence_role"] = evidence
    b["required_visual_concept"] = required[:200]
    b.setdefault("factual_claim_id", b.get("claim_id") or "")
    aid = b.get("asset_id") or (b.get("selected_asset") or {}).get("asset_id")
    kind = str(b.get("media_kind") or b.get("kind") or "")
    b["visual_information_id"] = compute_visual_information_id(
        asset_id=str(aid) if aid else None,
        entity=entity,
        concept=concept,
        evidence_role=evidence,
        required_visual_concept=required,
        media_kind=kind,
    )
    return b


def _infer_evidence_role(concept: str, role: str, span: str) -> str:
    low = f"{concept} {role} {span}".lower()
    if role == "entity_proof" or "person" in concept or re.search(r"\b(founder|portrait|archive)\b", low):
        return "archive"
    if role == "document" or re.search(r"\b(document|filing|charter|deed|legal)\b", low):
        return "document"
    if role == "place" or re.search(r"\b(geneva|swiss|city|location)\b", low):
        return "location"
    if role == "money" or re.search(r"\b(finance|market|exchange|vault)\b", low):
        return "contrast"
    if "ownership" in concept or "foundation" in low or "trust" in low:
        return "proof"
    if role == "hook":
        return "product"
    return "illustrative"


def _required_concept(entity: str, concept: str, role: str, evidence: str) -> str:
    if evidence == "archive" and entity:
        return f"{entity} archive portrait"
    if evidence == "document":
        return "ownership or legal document evidence"
    if evidence == "location":
        return f"{entity or concept} location establishing shot"
    if evidence == "contrast":
        return "public market / exchange contrast"
    if evidence == "proof" and entity:
        return f"{entity} institutional ownership evidence"
    if evidence == "product":
        return f"{entity or 'brand'} product hero"
    return (concept or role or "documentary detail").replace("_", " ")


@dataclass
class StoryboardCoverage:
    beat_count: int = 0
    beats_with_unique_visual_information: int = 0
    beats_using_real_video: int = 0
    beats_using_archive: int = 0
    beats_using_documents: int = 0
    beats_using_same_asset_transform_only: int = 0
    uncovered_beats: list[str] = field(default_factory=list)
    unique_source_assets: int = 0
    unique_visual_information_units: int = 0
    review_recommended: bool = False
    review_reasons: list[str] = field(default_factory=list)
    beats: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def analyze_storyboard_coverage(word_to_visual: list[dict]) -> StoryboardCoverage:
    """Transparent diagnostics — no single magic percentage gate."""
    from app.story_domains import source_asset_key

    enriched = [enrich_beat_dict(b) for b in (word_to_visual or [])]
    vids: list[str] = []
    assets: set[str] = set()
    video_n = 0
    archive_n = 0
    doc_n = 0
    transform_only = 0
    uncovered: list[str] = []

    prev_vid = ""
    prev_asset = ""
    for b in enriched:
        vid = str(b.get("visual_information_id") or "")
        sel = b.get("selected_asset") or {}
        provider = str(sel.get("provider") or b.get("provider") or "")
        raw_aid = sel.get("asset_id") if sel.get("asset_id") is not None else b.get("asset_id")
        url = str((sel.get("metadata") or {}).get("url") or b.get("url") or "")
        path = str(sel.get("path") or b.get("path") or "")
        aid = source_asset_key(
            provider=provider,
            asset_id=str(raw_aid) if raw_aid is not None else None,
            url=url,
            path=path,
        ) or str(raw_aid or "")
        kind = str(b.get("media_kind") or b.get("kind") or "").lower()
        evidence = str(b.get("evidence_role") or "")
        vc = str(b.get("visual_change") or b.get("visual_change_applied") or "").lower()

        if vid:
            vids.append(vid)
        if aid:
            assets.add(aid)
        if "video" in kind or (path.endswith(".mp4") or path.endswith(".webm")):
            video_n += 1
        if evidence == "archive" or "archive" in str(b.get("concept") or "").lower():
            archive_n += 1
        if evidence == "document":
            doc_n += 1

        same_asset_transform = bool(
            aid
            and prev_asset
            and aid == prev_asset
            and vc in {"punch_in", "crop_zoom", "archive_motion", "reuse_with_motion"}
        ) or (
            vid
            and prev_vid
            and vid == prev_vid
            and vc in {"punch_in", "crop_zoom", "archive_motion", "reuse_with_motion"}
        )
        if same_asset_transform:
            transform_only += 1

        if not path and not raw_aid and not b.get("selected_asset"):
            # Rhetorical fragments are not "important uncovered beats"
            role = str(b.get("evidence_role") or "")
            span = str(b.get("spoken_span") or "")
            if role in {"proof", "archive", "document", "location", "contrast", "product"} or len(
                span.split()
            ) >= 5:
                uncovered.append(span[:80] or str(b.get("required_visual_concept") or "beat"))

        prev_vid = vid or prev_vid
        prev_asset = aid or prev_asset

    unique_vids = len(set(vids))
    cov = StoryboardCoverage(
        beat_count=len(enriched),
        beats_with_unique_visual_information=unique_vids,
        beats_using_real_video=video_n,
        beats_using_archive=archive_n,
        beats_using_documents=doc_n,
        beats_using_same_asset_transform_only=transform_only,
        uncovered_beats=uncovered,
        unique_source_assets=len(assets),
        unique_visual_information_units=unique_vids,
        beats=[{
            "spoken_span": b.get("spoken_span"),
            "required_visual_concept": b.get("required_visual_concept"),
            "evidence_role": b.get("evidence_role"),
            "visual_information_id": b.get("visual_information_id"),
            "asset_id": b.get("asset_id") or (b.get("selected_asset") or {}).get("asset_id"),
            "source_asset_key": source_asset_key(
                provider=str((b.get("selected_asset") or {}).get("provider") or b.get("provider") or ""),
                asset_id=str(
                    (b.get("selected_asset") or {}).get("asset_id")
                    if (b.get("selected_asset") or {}).get("asset_id") is not None
                    else b.get("asset_id") or ""
                )
                or None,
                url=str(((b.get("selected_asset") or {}).get("metadata") or {}).get("url") or ""),
                path=str((b.get("selected_asset") or {}).get("path") or b.get("path") or ""),
            ),
            "media_kind": b.get("media_kind") or b.get("kind"),
            "visual_change": b.get("visual_change") or b.get("visual_change_applied"),
            "narrative_role": b.get("narrative_role"),
        } for b in enriched],
    )

    reasons: list[str] = []
    if cov.beat_count >= 3 and transform_only >= max(2, cov.beat_count // 2):
        reasons.append("too_many_same_asset_transforms")
    if uncovered:
        reasons.append("important_beats_uncovered")
    if cov.beat_count >= 3 and unique_vids <= 1:
        reasons.append("no_meaningful_visual_progression")
    if cov.beat_count >= 4 and video_n == 0 and archive_n == 0:
        reasons.append("no_video_or_archive_shots")
    if cov.beat_count >= 6 and len(assets) <= 1:
        reasons.append("low_unique_source_asset_count")
    cov.review_reasons = reasons
    cov.review_recommended = bool(reasons)
    return cov


def storyboard_before_retrieval(script: str, topic: str = "") -> list[StoryBeatSpec]:
    """DECISION → SOURCE: decide required visuals from final script before fetch.

    Lightweight semantic split (no LLM required for tests / offline).
    """
    from app.director_planner import _split_semantic_chunks, _beat_from_chunk

    chunks = _split_semantic_chunks(script or "")
    if not chunks:
        chunks = [script or topic or "scene"]
    # Cap to a documentary arc of ~4–7 beats
    if len(chunks) > 7:
        # Pack: keep first, merge middle, keep last pair
        head = chunks[:2]
        mid = [" ".join(chunks[2:-2])] if len(chunks) > 4 else chunks[2:-1]
        tail = chunks[-2:]
        chunks = [c for c in (head + mid + tail) if c][:7]

    specs: list[StoryBeatSpec] = []
    for i, chunk in enumerate(chunks):
        vb = _beat_from_chunk(
            chunk,
            index=i,
            scene_index=0,
            topic=topic,
            base_avoid=[],
            entities=[],
        )
        evidence = _infer_evidence_role(vb.concept, vb.narrative_role, chunk)
        entity = (vb.primary_entities[0] if vb.primary_entities else "") or ""
        required = _required_concept(entity, vb.concept, vb.narrative_role, evidence)
        preferred = "stock_photo" if evidence in {"archive", "document"} else "stock_video"
        if prefers_video_for_concept(vb.concept, vb.narrative_role):
            preferred = "stock_video"
        if evidence == "archive":
            preferred = "stock_photo"
        vid = compute_visual_information_id(
            entity=entity,
            concept=vb.concept,
            evidence_role=evidence,
            required_visual_concept=required,
            media_kind=preferred,
        )
        specs.append(
            StoryBeatSpec(
                spoken_span=chunk[:240],
                narrative_role=vb.narrative_role,
                primary_entity=entity,
                factual_claim_id="",
                required_visual_concept=required,
                preferred_media_type=preferred,
                evidence_role=evidence,
                fallback_ladder=list(vb.fallback_ladder) or ["stock_photo", "stock_video"],
                visual_information_id=vid,
            )
        )
    return specs
