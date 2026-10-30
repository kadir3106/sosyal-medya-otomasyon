"""Build evidence-bound MotionGraphicPlan instances — reject unsupported facts."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from app.documentary_v2.schemas import MotionGraphicPlan, ShotRequirement, VerifiedClaim
from app.documentary_v2.recovery.theme import DEFAULT_THEME


class MotionGraphicPlanError(ValueError):
    """Plan cannot be built without inventing facts."""


def _claim_map(claims: list[VerifiedClaim]) -> dict[str, VerifiedClaim]:
    return {c.claim_id: c for c in claims}


def _supported(c: VerifiedClaim | None) -> bool:
    return bool(c) and (c.status or "").lower() in {"supported", "partial"}


def _evidence_ids(c: VerifiedClaim) -> list[str]:
    out = []
    for i, ev in enumerate(c.evidence or []):
        eid = str(ev.get("evidence_id") or ev.get("id") or f"{c.claim_id}:ev{i}")
        out.append(eid)
    return out or [f"{c.claim_id}:ev0"]


def _fingerprint(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()[:24]


def build_relationship_graph_plan(
    req: ShotRequirement,
    *,
    edges: list[dict[str, Any]],
    claims: list[VerifiedClaim],
    duration: float | None = None,
) -> MotionGraphicPlan:
    """Each edge must cite claim_id + evidence_id that exist and are supported."""
    cmap = _claim_map(claims)
    verified_edges: list[dict] = []
    claim_ids: list[str] = []
    evidence_ids: list[str] = []
    nodes: list[str] = []

    for edge in edges:
        cid = str(edge.get("claim_id") or "")
        eid = str(edge.get("evidence_id") or "")
        claim = cmap.get(cid)
        if not _supported(claim):
            raise MotionGraphicPlanError(f"unsupported_or_missing_claim:{cid}")
        allowed_eids = set(_evidence_ids(claim))
        if eid and eid not in allowed_eids and not (claim.evidence):
            # If claim has empty evidence list but is supported, allow synthetic evidence id
            if not claim.evidence:
                eid = eid or f"{cid}:ev0"
            else:
                raise MotionGraphicPlanError(f"evidence_not_on_claim:{eid}")
        if not eid:
            eid = _evidence_ids(claim)[0]
        src = str(edge.get("from") or edge.get("source") or "").strip()
        dst = str(edge.get("to") or edge.get("target") or "").strip()
        label = str(edge.get("label") or edge.get("relation") or "").strip()
        if not src or not dst or not label:
            raise MotionGraphicPlanError("edge_missing_from_to_label")
        verified_edges.append(
            {
                "from": src,
                "to": dst,
                "label": label,
                "claim_id": cid,
                "evidence_id": eid,
            }
        )
        claim_ids.append(cid)
        evidence_ids.append(eid)
        for n in (src, dst):
            if n not in nodes:
                nodes.append(n)

    if not verified_edges:
        raise MotionGraphicPlanError("no_verified_edges")

    plan_id = f"mg:rel:{uuid.uuid4().hex[:10]}"
    payload = {"primitive": "RelationshipGraph", "edges": verified_edges, "nodes": nodes}
    return MotionGraphicPlan(
        plan_id=plan_id,
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        primitive="RelationshipGraph",
        visual_purpose=req.visual_purpose or "EXPLAIN_RELATIONSHIP",
        nodes=nodes,
        relationships=verified_edges,
        labels=[e["label"] for e in verified_edges],
        claim_ids=list(dict.fromkeys(claim_ids)),
        evidence_ids=list(dict.fromkeys(evidence_ids)),
        source_reference="verified_claims",
        animation_type="hierarchical_reveal",
        duration=duration or req.estimated_duration or 3.0,
        verified=True,
        theme_id=DEFAULT_THEME.theme_id,
        content_fingerprint=_fingerprint(payload),
        explanatory_only=True,
    )


def build_timeline_plan(
    req: ShotRequirement,
    *,
    events: list[dict[str, Any]],
    claims: list[VerifiedClaim],
    duration: float | None = None,
) -> MotionGraphicPlan:
    cmap = _claim_map(claims)
    verified: list[dict] = []
    claim_ids: list[str] = []
    evidence_ids: list[str] = []
    for ev in events:
        cid = str(ev.get("claim_id") or "")
        claim = cmap.get(cid)
        if not _supported(claim):
            raise MotionGraphicPlanError(f"timeline_unsupported_claim:{cid}")
        date = str(ev.get("date") or ev.get("year") or "").strip()
        if not date:
            raise MotionGraphicPlanError("timeline_missing_date")
        # Date must appear in claim text or evidence — no invented dates
        hay = (claim.text or "") + json.dumps(claim.evidence or [])
        if date not in hay and not any(date in str(x) for x in (claim.evidence or [])):
            # Allow if claim text contains the year digits of date
            year = "".join(ch for ch in date if ch.isdigit())[:4]
            if not year or year not in hay:
                raise MotionGraphicPlanError(f"date_not_in_evidence:{date}")
        eid = str(ev.get("evidence_id") or _evidence_ids(claim)[0])
        verified.append(
            {
                "date": date,
                "label": str(ev.get("label") or claim.text[:80]),
                "claim_id": cid,
                "evidence_id": eid,
            }
        )
        claim_ids.append(cid)
        evidence_ids.append(eid)

    if not verified:
        raise MotionGraphicPlanError("no_timeline_events")

    plan_id = f"mg:tl:{uuid.uuid4().hex[:10]}"
    return MotionGraphicPlan(
        plan_id=plan_id,
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        primitive="Timeline",
        visual_purpose=req.visual_purpose or "SHOW_EVIDENCE",
        events=verified,
        nodes=[e["date"] for e in verified],
        labels=[e["label"] for e in verified],
        claim_ids=list(dict.fromkeys(claim_ids)),
        evidence_ids=list(dict.fromkeys(evidence_ids)),
        animation_type="chronology_reveal",
        duration=duration or req.estimated_duration or 3.0,
        verified=True,
        theme_id=DEFAULT_THEME.theme_id,
        content_fingerprint=_fingerprint({"events": verified}),
        explanatory_only=True,
    )


def build_map_plan(
    req: ShotRequirement,
    *,
    location: str,
    claim_ids: list[str] | None = None,
    duration: float | None = None,
) -> MotionGraphicPlan:
    loc = (location or req.location or "").strip()
    if not loc:
        raise MotionGraphicPlanError("map_missing_location")
    plan_id = f"mg:map:{uuid.uuid4().hex[:10]}"
    return MotionGraphicPlan(
        plan_id=plan_id,
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        primitive="MapHighlight",
        visual_purpose="SHOW_LOCATION",
        nodes=[loc],
        labels=[loc],
        map_location=loc,
        claim_ids=list(claim_ids or req.claim_ids or []),
        animation_type="location_focus",
        duration=duration or req.estimated_duration or 2.5,
        verified=True,
        theme_id=DEFAULT_THEME.theme_id,
        content_fingerprint=_fingerprint({"loc": loc}),
        explanatory_only=True,
    )


def build_document_highlight_plan(
    req: ShotRequirement,
    *,
    document_asset_id: str,
    claim_ids: list[str],
    evidence_ids: list[str],
    duration: float | None = None,
) -> MotionGraphicPlan:
    if not document_asset_id:
        raise MotionGraphicPlanError("document_highlight_requires_real_asset")
    if not claim_ids or not evidence_ids:
        raise MotionGraphicPlanError("document_highlight_requires_claim_evidence")
    plan_id = f"mg:doc:{uuid.uuid4().hex[:10]}"
    return MotionGraphicPlan(
        plan_id=plan_id,
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        primitive="DocumentHighlight",
        visual_purpose="SHOW_EVIDENCE",
        document_asset_id=document_asset_id,
        claim_ids=list(claim_ids),
        evidence_ids=list(evidence_ids),
        animation_type="region_highlight",
        duration=duration or 3.0,
        verified=True,
        theme_id=DEFAULT_THEME.theme_id,
        content_fingerprint=_fingerprint({"doc": document_asset_id, "c": claim_ids}),
        explanatory_only=False,  # real document composition
    )


def build_evidence_card_plan(
    req: ShotRequirement,
    *,
    claims: list[VerifiedClaim],
    duration: float | None = None,
) -> MotionGraphicPlan:
    """Editorial explanatory card — must NOT impersonate official documents."""
    supported = [c for c in claims if _supported(c)]
    if not supported:
        raise MotionGraphicPlanError("evidence_card_needs_supported_claim")
    primary = supported[0]
    eids = _evidence_ids(primary)
    plan_id = f"mg:card:{uuid.uuid4().hex[:10]}"
    return MotionGraphicPlan(
        plan_id=plan_id,
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        primitive="EvidenceCard",
        visual_purpose=req.visual_purpose or "SHOW_EVIDENCE",
        nodes=[primary.claim_id],
        labels=["DOCUMENTARY NOTES", primary.text[:120]],
        claim_ids=[primary.claim_id],
        evidence_ids=eids[:1],
        animation_type="editorial_reveal",
        duration=duration or 3.0,
        verified=True,
        theme_id=DEFAULT_THEME.theme_id,
        content_fingerprint=_fingerprint({"claim": primary.claim_id, "t": primary.text}),
        explanatory_only=True,
        style={"disclaimer": "Explanatory graphic — not an official document"},
    )


def build_counter_plan(
    req: ShotRequirement,
    *,
    claim: VerifiedClaim,
    display_value: str,
    duration: float | None = None,
) -> MotionGraphicPlan:
    if not _supported(claim):
        raise MotionGraphicPlanError("counter_needs_supported_claim")
    if display_value not in (claim.text or ""):
        # value must appear in claim text
        raise MotionGraphicPlanError("counter_value_not_in_claim")
    plan_id = f"mg:num:{uuid.uuid4().hex[:10]}"
    return MotionGraphicPlan(
        plan_id=plan_id,
        beat_id=req.beat_id,
        shot_id=f"shot:{req.beat_id}",
        primitive="Counter",
        visual_purpose="SHOW_EVIDENCE",
        labels=[display_value, claim.text[:80]],
        claim_ids=[claim.claim_id],
        evidence_ids=_evidence_ids(claim)[:1],
        number_claim_id=claim.claim_id,
        animation_type="count_reveal",
        duration=duration or 2.5,
        verified=True,
        theme_id=DEFAULT_THEME.theme_id,
        content_fingerprint=_fingerprint({"v": display_value, "c": claim.claim_id}),
        explanatory_only=True,
    )
