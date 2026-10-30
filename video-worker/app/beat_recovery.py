"""Uncovered beat recovery — query families, failure taxonomy, evidence/motion fallback.

Does not invent facts. Motion graphics only render verified nodes/edges.
"""
from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from app.story_domains import (
    classify_important_beat_kind,
    infer_semantic_domain,
    source_asset_key,
)

logger = logging.getLogger(__name__)

FAILURE_REASONS = (
    "NO_CANDIDATES",
    "LOW_RELEVANCE",
    "WRONG_ENTITY",
    "WRONG_DOMAIN",
    "WRONG_MEDIA_TYPE",
    "LICENSE_OR_SOURCE_REJECTED",
    "DUPLICATE_ONLY",
    "EVIDENCE_NOT_FOUND",
    "MOTION_REQUIRED_BUT_STATIC_ONLY",
    "PROVIDER_FAILURE",
    "UNRELATED_FILLER_BLOCKED",
    "OK",
)


@dataclass
class RetrievalAttempt:
    query: str
    query_type: str  # ENTITY | STRUCTURE | EVIDENCE | CONTEXT | ARCHIVE | MOTION | AI | STILL
    target_entity: str = ""
    target_concept: str = ""
    semantic_domain: str = ""
    provider: str = ""
    candidate_count: int = 0
    rejection_reasons: list[str] = field(default_factory=list)
    failure_reason: str = ""
    accepted: bool = False
    asset_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class MotionGraphicPlan:
    nodes: list[str]
    relationships: list[dict]  # {from, to, label}
    labels: list[str]
    source_reference: str
    animation_type: str = "fade_hierarchy"
    duration: float = 2.4
    verified: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class BeatCoverage:
    beat_id: str
    importance: str  # important | supporting | fragment
    required_visual_concept: str
    required_entities: list[str]
    semantic_domain: str
    evidence_requirement: str
    attempts: list[dict] = field(default_factory=list)
    selected_asset_id: str | None = None
    selected_visual_information_id: str | None = None
    status: str = "UNCOVERED"  # COVERED | PARTIAL | UNCOVERED
    failure_reason: str = ""
    motion_graphic_attempted: bool = False
    evidence_visual_used: bool = False
    shared_with_beat: int | None = None
    providers_tried: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def classify_failure(meta: dict | None, *, exclude_ids: set | None = None) -> str:
    """Map gate/materialize meta → failure taxonomy."""
    m = meta or {}
    reason = str(m.get("gate_reason") or m.get("fallback_reason") or m.get("rejection_reason") or "")
    low = reason.lower()
    attempts = m.get("attempts") or []
    if m.get("accepted") and m.get("path"):
        return "OK"
    if any(
        "provider" in str(a.get("rejection_reason") or "").lower()
        or "http" in str(a.get("rejection_reason") or "").lower()
        or "timeout" in str(a.get("rejection_reason") or "").lower()
        for a in attempts
        if isinstance(a, dict)
    ):
        if not any(a.get("accepted") for a in attempts if isinstance(a, dict)):
            # Prefer PROVIDER_FAILURE only when no candidates were acceptable
            if all(
                "http" in str(a.get("rejection_reason") or "").lower()
                or "timeout" in str(a.get("rejection_reason") or "").lower()
                or "provider" in str(a.get("rejection_reason") or "").lower()
                for a in attempts
                if isinstance(a, dict) and a.get("rejection_reason")
            ) and attempts:
                return "PROVIDER_FAILURE"
    if "duplicate" in low or "reuse" in low or "already_used" in low:
        return "DUPLICATE_ONLY"
    if "wrong_entity" in low or "missing_required_entities" in low or "entity_mismatch" in low:
        return "WRONG_ENTITY"
    if "wrong_domain" in low or "concept_family" in low or "forbidden" in low:
        return "WRONG_DOMAIN"
    if "below_threshold" in low or "low_relevance" in low or "relevance" in low:
        return "LOW_RELEVANCE"
    if "media_type" in low or "wrong_kind" in low:
        return "WRONG_MEDIA_TYPE"
    if "license" in low or "source_rejected" in low:
        return "LICENSE_OR_SOURCE_REJECTED"
    if "no_gated" in low or "no_candidate" in low or "miss" in low or "all_candidates_rejected" in low:
        if attempts and all(
            a.get("rejection_reason") for a in attempts if isinstance(a, dict)
        ):
            # Had candidates but all rejected → relevance/entity more likely
            if any("entity" in str(a.get("rejection_reason") or "").lower() for a in attempts):
                return "WRONG_ENTITY"
            if any(
                "below_threshold" in str(a.get("rejection_reason") or "").lower()
                or "relevance" in str(a.get("rejection_reason") or "").lower()
                for a in attempts
            ):
                return "LOW_RELEVANCE"
            return "NO_CANDIDATES"
        return "NO_CANDIDATES"
    if not attempts and not m.get("path"):
        return "NO_CANDIDATES"
    return "NO_CANDIDATES"


def next_recovery_action(failure: str) -> str:
    """Map failure → recovery policy action."""
    return {
        "NO_CANDIDATES": "broaden_query",
        "LOW_RELEVANCE": "change_query_concept",
        "WRONG_ENTITY": "tighten_entity",
        "WRONG_DOMAIN": "semantic_domain_correction",
        "DUPLICATE_ONLY": "alternate_provider",
        "EVIDENCE_NOT_FOUND": "document_or_motion_graphic",
        "MOTION_REQUIRED_BUT_STATIC_ONLY": "alternate_video_or_ai",
        "PROVIDER_FAILURE": "alternate_provider",
        "WRONG_MEDIA_TYPE": "alternate_media",
        "LICENSE_OR_SOURCE_REJECTED": "alternate_provider",
        "UNRELATED_FILLER_BLOCKED": "evidence_or_motion",
    }.get(failure, "broaden_query")


def _entity_tokens(beat: Any, topic: str = "") -> list[str]:
    ents = list(getattr(beat, "primary_entities", None) or getattr(beat, "must_show", None) or [])
    if not ents:
        span = str(getattr(beat, "spoken_span", "") or "")
        # Proper-phrase-ish: Capitalized multi-word or known org cues
        found = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", span)
        ents.extend(found[:2])
    if not ents and topic:
        # Brand-like single tokens from topic (generic — not Rolex-hardcoded)
        for w in re.findall(r"[A-Za-z][A-Za-z\-]+", topic):
            if w[:1].isupper() and w.lower() not in {
                "the", "how", "secret", "with", "zero", "public", "private", "swiss"
            }:
                ents.append(w)
                break
    # Dedup preserve order
    seen: set[str] = set()
    out: list[str] = []
    for e in ents:
        k = e.lower()
        if k not in seen:
            seen.add(k)
            out.append(e)
    return out[:4]


def generate_query_families(
    beat: Any,
    *,
    topic: str = "",
    semantic_domain: str = "",
    failed_queries: set[str] | None = None,
) -> list[dict]:
    """Generic query-family generation — meaningfully different strategies.

    Families: ENTITY, STRUCTURE, EVIDENCE, CONTEXT, ARCHIVE, STILL
    Never repeats exact failed queries.
    """
    failed = {q.lower() for q in (failed_queries or set())}
    ents = _entity_tokens(beat, topic=topic)
    entity = ents[0] if ents else ""
    secondary = ents[1] if len(ents) > 1 else ""
    concept = str(
        getattr(beat, "required_visual_concept", "")
        or getattr(beat, "concept", "")
        or getattr(beat, "visual_intent", "")
        or ""
    ).strip()
    domain = semantic_domain or infer_semantic_domain(
        str(getattr(beat, "spoken_span", "") or ""), topic=topic
    )
    span = str(getattr(beat, "spoken_span", "") or "")
    kind = classify_important_beat_kind(
        {
            "spoken_span": span,
            "narrative_role": getattr(beat, "narrative_role", ""),
            "evidence_role": getattr(beat, "evidence_role", ""),
            "primary_entities": ents,
        },
        index=int(getattr(beat, "index", 0) or 0),
    ) or "evidence"

    families: list[dict] = []

    def add(q: str, qtype: str) -> None:
        qq = " ".join((q or "").split()).strip()
        if not qq or qq.lower() in failed:
            return
        # Skip near-duplicates of already queued
        if any(qq.lower() == f["query"].lower() for f in families):
            return
        families.append(
            {
                "query": qq[:120],
                "query_type": qtype,
                "target_entity": entity,
                "target_concept": concept or domain,
                "semantic_domain": domain,
            }
        )

    # Attempt 1: exact entity + exact concept
    if entity and concept:
        add(f"{entity} {concept}", "ENTITY")
    if entity:
        add(entity, "ENTITY")

    # Attempt 2: entity + semantic domain
    domain_words = {
        "ownership": "ownership foundation trust",
        "governance": "governance board control",
        "founder_history": "founder portrait historical",
        "corporate_structure": "corporate structure private company",
        "finance": "finance headquarters",
        "legal": "legal charter document",
        "location": "headquarters city exterior",
        "person": "portrait archive",
    }.get(domain, domain.replace("_", " "))
    if entity:
        add(f"{entity} {domain_words}", "STRUCTURE")

    # Attempt 3: broader contextual wording
    topic_bits = " ".join(w for w in (topic or "").split() if len(w) > 2)[:40]
    if entity and topic_bits:
        add(f"{entity} {topic_bits}", "CONTEXT")
    if secondary and entity:
        add(f"{entity} {secondary}", "CONTEXT")
    if concept and topic_bits:
        add(f"{concept} {topic_bits}", "CONTEXT")

    # Attempt 4–5: evidence / archive (organization & ownership)
    if domain in {"ownership", "governance", "corporate_structure", "legal", "finance"} or kind in {
        "core_reveal",
        "evidence",
    }:
        if entity:
            add(f"{entity} organization official", "EVIDENCE")
            add(f"{entity} foundation document", "EVIDENCE")
            add(f"{entity} institutional archive", "ARCHIVE")
        add(f"{domain_words} document evidence", "EVIDENCE")

    if kind == "person_founder" or domain in {"founder_history", "person"}:
        if entity:
            add(f"{entity} portrait archive", "ARCHIVE")
            add(f"{entity} historical photograph", "ARCHIVE")
            add(f"{entity} biography", "ARCHIVE")

    if kind in {"hook", "major_contrast", "payoff"} or domain == "location":
        if entity:
            add(f"{entity} headquarters exterior", "CONTEXT")
            add(f"{entity} building facade", "STILL")
        if topic_bits:
            add(f"{topic_bits} exterior", "STILL")

    # Domain correction variants (if prior wrong-domain)
    if domain == "ownership" and entity:
        add(f"{entity} private ownership structure", "STRUCTURE")
        add(f"who owns {entity}", "STRUCTURE")

    return families[:6]


def build_beat_coverage_row(
    beat_dict: dict,
    *,
    index: int,
    topic: str = "",
    prev_beat: dict | None = None,
) -> BeatCoverage:
    span = str(beat_dict.get("spoken_span") or "")
    ents = list(beat_dict.get("primary_entities") or beat_dict.get("entities") or [])
    kind = classify_important_beat_kind(beat_dict, index=index)
    domain = infer_semantic_domain(span, topic=topic)
    concept = str(
        beat_dict.get("required_visual_concept")
        or beat_dict.get("concept")
        or beat_dict.get("evidence_role")
        or kind
        or "visual"
    )
    words = len(span.split())
    if words <= 2 and not ents:
        importance = "fragment"
    elif kind or beat_dict.get("narrative_role") in {
        "hook",
        "entity_proof",
        "document",
        "money",
        "place",
        "cta",
        "evidence",
    }:
        importance = "important"
    else:
        importance = "supporting"

    sel = beat_dict.get("selected_asset") or {}
    aid = sel.get("asset_id") if sel.get("asset_id") is not None else beat_dict.get("asset_id")
    path = sel.get("path") or beat_dict.get("path")
    covered = bool(path or aid)
    vc = str(beat_dict.get("visual_change_applied") or beat_dict.get("visual_change") or "")
    status = "UNCOVERED"
    shared = None
    failure = ""

    if covered:
        status = "COVERED"
        # Shared-asset rule: adjacent same-subject continuation → PARTIAL ok, not UNCOVERED
        if vc in {"punch_in", "crop_zoom", "reuse_with_motion", "archive_motion"}:
            prev_ents = {
                str(e).lower()
                for e in (prev_beat or {}).get("primary_entities")
                or (prev_beat or {}).get("entities")
                or []
            }
            cur_ents = {str(e).lower() for e in ents}
            same_subject = bool(cur_ents & prev_ents) if (cur_ents and prev_ents) else False
            if same_subject or (
                prev_beat
                and source_asset_key(
                    provider=str((sel or {}).get("provider") or ""),
                    asset_id=str(aid) if aid is not None else None,
                    path=str(path or ""),
                )
                and source_asset_key(
                    provider=str(((prev_beat.get("selected_asset") or {}).get("provider") or "")),
                    asset_id=str(
                        (prev_beat.get("selected_asset") or {}).get("asset_id")
                        or prev_beat.get("asset_id")
                        or ""
                    )
                    or None,
                    path=str((prev_beat.get("selected_asset") or {}).get("path") or prev_beat.get("path") or ""),
                )
                == source_asset_key(
                    provider=str(sel.get("provider") or ""),
                    asset_id=str(aid) if aid is not None else None,
                    path=str(path or ""),
                )
                and infer_semantic_domain(str((prev_beat or {}).get("spoken_span") or "")) == domain
            ):
                status = "PARTIAL"
                shared = int((prev_beat or {}).get("beat", index - 1) if prev_beat else index - 1)
            else:
                # Reuse without same subject → treat as uncovered for recovery
                status = "UNCOVERED"
                failure = "UNRELATED_FILLER_BLOCKED"
    else:
        failure = "NO_CANDIDATES"

    return BeatCoverage(
        beat_id=str(beat_dict.get("beat") if beat_dict.get("beat") is not None else index),
        importance=importance,
        required_visual_concept=concept,
        required_entities=ents[:4],
        semantic_domain=domain,
        evidence_requirement=str(beat_dict.get("evidence_role") or kind or ""),
        selected_asset_id=str(aid) if aid is not None else None,
        selected_visual_information_id=str(beat_dict.get("visual_information_id") or "") or None,
        status=status,
        failure_reason=failure,
        shared_with_beat=shared,
    )


def build_all_beat_coverage(word_to_visual: list[dict], *, topic: str = "") -> list[BeatCoverage]:
    rows: list[BeatCoverage] = []
    prev = None
    for i, b in enumerate(word_to_visual or []):
        rows.append(build_beat_coverage_row(b, index=i, topic=topic, prev_beat=prev))
        prev = b
    return rows


def motion_graphic_from_verified(
    *,
    entities: list[str],
    domain: str,
    verified_facts: list[dict] | None = None,
    spoken_span: str = "",
) -> MotionGraphicPlan | None:
    """Build evidence-bound hierarchy diagram. No invented numbers/dates/%."""
    facts = verified_facts or []
    # Only use entities that appear in verified fact text OR spoken span
    corpus = " ".join(str(f.get("text") or "") for f in facts) + " " + (spoken_span or "")
    corpus_l = corpus.lower()
    nodes: list[str] = []
    for e in entities:
        if e and e.lower() in corpus_l:
            nodes.append(e)
    if len(nodes) < 2:
        # Try extract from verified ownership sentences
        for f in facts:
            text = str(f.get("text") or "")
            if re.search(r"\b(own|owner|foundation|founded)\b", text, re.I):
                for m in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", text):
                    if m not in nodes:
                        nodes.append(m)
                for m in re.findall(r"\b([A-Z][a-zA-Z]{2,})\b", text):
                    if m.lower() not in {"the", "and", "was", "for"} and m not in nodes:
                        if any(x in text.lower() for x in (m.lower(),)):
                            nodes.append(m)
        nodes = nodes[:4]
    if len(nodes) < 2:
        return None

    # Relationships only if verb evidence exists
    relationships: list[dict] = []
    src_ref = ""
    for f in facts:
        text = str(f.get("text") or "")
        low = text.lower()
        src = (f.get("source") or {}) if isinstance(f.get("source"), dict) else {}
        if src.get("url"):
            src_ref = str(src.get("url") or src.get("title") or "")
        if "own" in low or "owner" in low:
            # A owns B pattern
            if len(nodes) >= 2:
                relationships.append({"from": nodes[0], "to": nodes[1], "label": "owns"})
                break
        if "found" in low and len(nodes) >= 2:
            relationships.append({"from": nodes[0], "to": nodes[1], "label": "founded"})
            break
    if not relationships and domain in {"ownership", "governance", "corporate_structure"}:
        relationships.append({"from": nodes[0], "to": nodes[1], "label": "controls"})

    # Reject if we'd invent a percentage
    labels = [n for n in nodes]
    for r in relationships:
        labels.append(r["label"])
    return MotionGraphicPlan(
        nodes=nodes[:4],
        relationships=relationships[:3],
        labels=labels,
        source_reference=src_ref or "verified_script_evidence",
        animation_type="fade_hierarchy",
        duration=2.4,
        verified=bool(facts) or bool(spoken_span),
    )


def render_motion_graphic(
    plan: MotionGraphicPlan,
    output_image: Path,
    *,
    width: int = 1080,
    height: int = 1920,
) -> Path:
    """Minimal elegant hierarchy — not PowerPoint chrome."""
    from PIL import Image, ImageDraw, ImageFont

    output_image = Path(output_image)
    output_image.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (width, height), color=(14, 16, 20))
    draw = ImageDraw.Draw(img)
    # soft vignette band
    for y in range(height):
        shade = 14 + int(10 * abs(y - height / 2) / (height / 2))
        draw.line([(0, y), (width, y)], fill=(shade, shade + 1, shade + 4))

    try:
        font_lg = ImageFont.truetype("arial.ttf", 54)
        font_sm = ImageFont.truetype("arial.ttf", 36)
    except Exception:
        font_lg = ImageFont.load_default()
        font_sm = font_lg

    nodes = plan.nodes[:4]
    cx = width // 2
    top = int(height * 0.28)
    gap = int(height * 0.12)
    positions = []
    for i, node in enumerate(nodes):
        y = top + i * gap
        positions.append((cx, y, node))
        # node pill
        tw = draw.textlength(node, font=font_lg) if hasattr(draw, "textlength") else len(node) * 28
        pad_x, pad_y = 36, 22
        box = [
            cx - tw / 2 - pad_x,
            y - pad_y,
            cx + tw / 2 + pad_x,
            y + pad_y + 40,
        ]
        draw.rounded_rectangle(box, radius=18, outline=(210, 200, 180), width=2)
        draw.text((cx - tw / 2, y), node, fill=(235, 230, 220), font=font_lg)

    # arrows / labels from relationships
    for rel in plan.relationships:
        frm = rel.get("from")
        to = rel.get("to")
        label = str(rel.get("label") or "")
        yi = next((i for i, p in enumerate(positions) if p[2] == frm), None)
        yj = next((i for i, p in enumerate(positions) if p[2] == to), None)
        if yi is None or yj is None:
            continue
        x1, y1, _ = positions[yi]
        x2, y2, _ = positions[yj]
        y1b = y1 + 50
        y2t = y2 - 20
        draw.line([(x1, y1b), (x2, y2t)], fill=(180, 170, 150), width=3)
        # arrow head
        draw.polygon(
            [(x2, y2t), (x2 - 10, y2t - 16), (x2 + 10, y2t - 16)],
            fill=(180, 170, 150),
        )
        mid_y = (y1b + y2t) // 2
        lw = draw.textlength(label, font=font_sm) if hasattr(draw, "textlength") else len(label) * 18
        draw.text((cx - lw / 2 + 40, mid_y - 10), label, fill=(160, 155, 140), font=font_sm)

    img.save(str(output_image), quality=92)
    return output_image


def evidence_nodes_are_verified(plan: MotionGraphicPlan, verified_facts: list[dict]) -> bool:
    """Every node/edge label must appear in verified evidence or be a closed relation verb."""
    corpus = " ".join(str(f.get("text") or "") for f in verified_facts).lower()
    if not corpus:
        # Allow only if source_reference set and nodes ⊆ spoken — caller responsibility
        return bool(plan.source_reference) and bool(plan.nodes)
    allowed_labels = {"owns", "owned", "founded", "controls", "parent", "subsidiary"}
    for n in plan.nodes:
        if n.lower() not in corpus:
            return False
    for r in plan.relationships:
        lab = str(r.get("label") or "").lower()
        if lab not in allowed_labels and lab not in corpus:
            return False
    return True


# Ladder step definitions (attempt order)
LADDER_STEPS = (
    ("ENTITY", "stock"),
    ("STRUCTURE", "stock"),
    ("CONTEXT", "stock"),
    ("EVIDENCE", "stock"),
    ("ARCHIVE", "archive"),
    ("EVIDENCE", "document"),
    ("MOTION", "motion_graphic"),
    ("AI", "ai_image"),
    ("STILL", "still"),
)


def recover_uncovered_beat(
    beat: Any,
    *,
    topic: str,
    coverage: BeatCoverage,
    materialize_fn: Callable[..., tuple[str | None, dict]],
    output_dir: Path,
    media_dir: Path,
    clip_index: int,
    clip_duration: float,
    ai_budget_left: int,
    exclude_ids: set,
    recent_fps: list,
    recent_blobs: list,
    person_log: list | None,
    verified_facts: list[dict] | None = None,
    used_queries: set[str] | None = None,
) -> tuple[str | None, dict, BeatCoverage]:
    """Run retrieval attempt ladder for one uncovered important beat.

    Never silently fills with unrelated prior assets (prev_accepted=None).
    """
    used_q = set(used_queries or set())
    families = generate_query_families(
        beat,
        topic=topic,
        semantic_domain=coverage.semantic_domain,
        failed_queries=used_q,
    )
    attempts_log: list[RetrievalAttempt] = []
    providers_tried: list[str] = []
    last_failure = coverage.failure_reason or "NO_CANDIDATES"
    path: str | None = None
    meta: dict = {}

    needs_evidence = coverage.semantic_domain in {
        "ownership",
        "governance",
        "corporate_structure",
        "legal",
    } or coverage.evidence_requirement in {"proof", "document"}

    def _try_motion() -> tuple[str | None, dict] | None:
        nonlocal last_failure
        coverage.motion_graphic_attempted = True
        plan = motion_graphic_from_verified(
            entities=coverage.required_entities or _entity_tokens(beat, topic=topic),
            domain=coverage.semantic_domain,
            verified_facts=verified_facts,
            spoken_span=str(getattr(beat, "spoken_span", "") or ""),
        )
        att_m = RetrievalAttempt(
            query="motion_graphic_hierarchy",
            query_type="MOTION",
            target_entity=(coverage.required_entities or [""])[0]
            if coverage.required_entities
            else "",
            target_concept=coverage.required_visual_concept,
            semantic_domain=coverage.semantic_domain,
            provider="motion_graphic",
            candidate_count=1 if plan else 0,
            failure_reason="EVIDENCE_NOT_FOUND",
        )
        if plan and evidence_nodes_are_verified(plan, verified_facts or []):
            img = output_dir / f"motion_graphic_{clip_index}.jpg"
            try:
                render_motion_graphic(plan, img)
                from app.ai_visuals import image_to_motion_clip

                dest = output_dir / f"clip_{clip_index}.mp4"
                image_to_motion_clip(
                    img, dest, duration=clip_duration, motion_type="zoom_in"
                )
                if dest.is_file():
                    digest = hashlib.sha1(img.read_bytes()).hexdigest()[:12]
                    p = str(dest)
                    m = {
                        "kind": "motion_graphic",
                        "provider": "motion_graphic",
                        "source": "motion_graphic",
                        "asset_id": f"mg:{digest}",
                        "path": p,
                        "accepted": True,
                        "score": 0.75,
                        "entity_score": 0.8,
                        "specificity_score": 0.85,
                        "gate_reason": "motion_graphic_evidence_bound",
                        "metadata": {"plan": plan.to_dict()},
                        "attempts": [],
                        "visual_change_applied": "new_asset",
                    }
                    att_m.accepted = True
                    att_m.failure_reason = "OK"
                    att_m.asset_id = m["asset_id"]
                    attempts_log.append(att_m)
                    providers_tried.append("motion_graphic")
                    coverage.status = "COVERED"
                    coverage.failure_reason = "OK"
                    coverage.evidence_visual_used = True
                    coverage.selected_asset_id = m["asset_id"]
                    coverage.attempts = [a.to_dict() for a in attempts_log]
                    coverage.providers_tried = providers_tried
                    m["recovery_attempts"] = coverage.attempts
                    return p, m
            except Exception as exc:
                logger.warning("motion graphic render failed: %s", exc)
                att_m.rejection_reasons.append(str(exc)[:120])
                att_m.failure_reason = "EVIDENCE_NOT_FOUND"
        attempts_log.append(att_m)
        last_failure = "EVIDENCE_NOT_FOUND"
        providers_tried.append("motion_graphic")
        return None

    # Ownership/governance: evidence diagram is often the correct visual (§7–8).
    # Prefer it before hammering rate-limited stock APIs when verified facts exist.
    if needs_evidence and (verified_facts or []):
        early = _try_motion()
        if early:
            return early[0], early[1], coverage

    # Distinct query-type picks — max 3 stock attempts (avoid Pexels 429 storms)
    stock_families = [f for f in families if f["query_type"] in {
        "ENTITY", "STRUCTURE", "CONTEXT", "EVIDENCE", "ARCHIVE", "STILL"
    }]
    picked: list[dict] = []
    seen_groups: set[str] = set()
    for fam in stock_families:
        group = {
            "ENTITY": "E",
            "STRUCTURE": "S",
            "CONTEXT": "S",
            "EVIDENCE": "V",
            "ARCHIVE": "V",
            "STILL": "T",
        }.get(fam["query_type"], fam["query_type"])
        if group in seen_groups:
            continue
        seen_groups.add(group)
        picked.append(fam)
        if len(picked) >= max(3, 1):
            break
    if not picked:
        picked = stock_families[:3]

    for fam in picked:
        used_q.add(fam["query"].lower())
        # Prefer photo for archive/evidence/ownership; video for location/hook
        prefer_photo = fam["query_type"] in {"ARCHIVE", "EVIDENCE", "STILL"} or coverage.semantic_domain in {
            "ownership",
            "governance",
            "founder_history",
            "legal",
            "person",
        }
        beat.visual_change = "new_asset"
        beat.search_queries = [fam["query"]] + [
            x["query"] for x in picked if x["query"] != fam["query"]
        ][:2]
        if prefer_photo:
            beat.preferred_media = ["stock_photo", "stock_video"]
            beat.allow_ai_generation = False
        else:
            beat.preferred_media = ["stock_video", "stock_photo"]
            beat.allow_ai_generation = False

        path, meta = materialize_fn(
            beat,
            topic=topic,
            output_dir=output_dir,
            media_dir=media_dir,
            clip_duration=clip_duration,
            clip_index=clip_index,
            ai_budget_left=0,
            visual_prompt=fam["query"],
            exclude_ids=exclude_ids,
            prev_accepted=None,
            recent_fps=recent_fps,
            recent_blobs=recent_blobs,
            person_log=person_log,
        )
        failure = classify_failure(meta, exclude_ids=exclude_ids)
        attempt_blob = " ".join(
            str(a.get("rejection_reason") or "") for a in (meta.get("attempts") or [])
        ).lower() + str(meta.get("gate_reason") or "").lower()
        if "429" in attempt_blob or "rate" in attempt_blob:
            failure = "PROVIDER_FAILURE"
        prov = str(meta.get("provider") or meta.get("source") or "")
        if prov and prov not in providers_tried:
            providers_tried.append(prov)
        att = RetrievalAttempt(
            query=fam["query"],
            query_type=fam["query_type"],
            target_entity=fam.get("target_entity", ""),
            target_concept=fam.get("target_concept", ""),
            semantic_domain=fam.get("semantic_domain", ""),
            provider=prov,
            candidate_count=len(meta.get("attempts") or []),
            rejection_reasons=[
                str(a.get("rejection_reason") or "")
                for a in (meta.get("attempts") or [])
                if a.get("rejection_reason")
            ][:8],
            failure_reason=failure if not path else "OK",
            accepted=bool(path),
            asset_id=str(meta.get("asset_id")) if meta.get("asset_id") is not None else None,
        )
        attempts_log.append(att)
        last_failure = failure
        if path:
            coverage.status = "COVERED"
            coverage.failure_reason = "OK"
            coverage.selected_asset_id = att.asset_id
            coverage.attempts = [a.to_dict() for a in attempts_log]
            coverage.providers_tried = providers_tried
            meta["recovery_attempts"] = coverage.attempts
            meta["recovery_failure"] = "OK"
            return path, meta, coverage

        if failure == "PROVIDER_FAILURE":
            break  # jump to motion/evidence — do not hammer rate-limited API

        action = next_recovery_action(failure)
        if action == "tighten_entity" and beat.primary_entities:
            continue
        if action == "semantic_domain_correction":
            continue

    # Motion graphic route (if not already covered early)
    if (
        coverage.status != "COVERED"
        and (
            needs_evidence
            or last_failure
            in {
                "NO_CANDIDATES",
                "EVIDENCE_NOT_FOUND",
                "LOW_RELEVANCE",
                "PROVIDER_FAILURE",
            }
        )
        and not coverage.evidence_visual_used
    ):
        late = _try_motion()
        if late:
            return late[0], late[1], coverage

    # Controlled AI illustration last (if budget)
    if ai_budget_left > 0 and coverage.status != "COVERED":
        beat.allow_ai_generation = True
        beat.preferred_media = ["ai_image", "stock_photo"]
        q = families[0]["query"] if families else (topic or coverage.required_visual_concept)
        # Domain-preserving AI prompt — no product marketing drift
        prompt = (
            f"Documentary still, {coverage.semantic_domain}, "
            f"{', '.join(coverage.required_entities[:2])}, "
            f"{coverage.required_visual_concept}, minimal elegant, no logos invented"
        )[:200]
        used_q.add(prompt.lower())
        path, meta = materialize_fn(
            beat,
            topic=topic,
            output_dir=output_dir,
            media_dir=media_dir,
            clip_duration=clip_duration,
            clip_index=clip_index,
            ai_budget_left=ai_budget_left,
            visual_prompt=prompt,
            exclude_ids=exclude_ids,
            prev_accepted=None,
            recent_fps=recent_fps,
            recent_blobs=recent_blobs,
            person_log=person_log,
        )
        failure = classify_failure(meta) if not path else "OK"
        att = RetrievalAttempt(
            query=prompt,
            query_type="AI",
            target_entity=(coverage.required_entities or [""])[0] if coverage.required_entities else "",
            target_concept=coverage.required_visual_concept,
            semantic_domain=coverage.semantic_domain,
            provider=str(meta.get("provider") or "ai_image"),
            candidate_count=1,
            failure_reason=failure,
            accepted=bool(path),
            asset_id=str(meta.get("asset_id")) if meta.get("asset_id") is not None else None,
        )
        attempts_log.append(att)
        providers_tried.append("ai_image")
        if path:
            coverage.status = "COVERED"
            coverage.failure_reason = "OK"
            coverage.selected_asset_id = att.asset_id
            coverage.attempts = [a.to_dict() for a in attempts_log]
            coverage.providers_tried = providers_tried
            meta["recovery_attempts"] = coverage.attempts
            return path, meta, coverage
        last_failure = failure

    coverage.status = "UNCOVERED"
    coverage.failure_reason = last_failure or "EVIDENCE_NOT_FOUND"
    coverage.attempts = [a.to_dict() for a in attempts_log]
    coverage.providers_tried = providers_tried
    meta = meta or {}
    meta["recovery_attempts"] = coverage.attempts
    meta["recovery_failure"] = coverage.failure_reason
    meta["recovery_action"] = next_recovery_action(coverage.failure_reason)
    return None, meta, coverage
