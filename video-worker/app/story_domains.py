"""Semantic domain lock + story consistency (prevent ownership→manufacturing drift)."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any


SEMANTIC_DOMAINS = (
    "ownership",
    "governance",
    "founder_history",
    "corporate_structure",
    "finance",
    "manufacturing",
    "product",
    "location",
    "market",
    "legal",
    "timeline",
    "person",
    "contrast",
    "rhetorical",
)

# Domains that must not silently replace each other
_DRIFT_PAIRS = {
    "ownership": frozenset({"manufacturing", "product"}),
    "governance": frozenset({"manufacturing", "product"}),
    "corporate_structure": frozenset({"manufacturing", "product"}),
    "founder_history": frozenset({"manufacturing", "product", "market"}),
    "finance": frozenset({"manufacturing", "product"}),
    "legal": frozenset({"manufacturing", "product"}),
    "market": frozenset({"manufacturing", "product"}),
}


@dataclass
class ReplacementIntent:
    original_claim_id: str
    narrative_role: str
    semantic_domain: str
    primary_entities: list[str] = field(default_factory=list)
    desired_story_function: str = ""
    forbidden_drift_domains: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def infer_semantic_domain(text: str, *, topic: str = "") -> str:
    low = f"{text or ''} {topic or ''}".lower()
    if re.search(r"\b(own|owned|ownership|shareholder|foundation|trust|100%|fully owned)\b", low):
        return "ownership"
    if re.search(r"\b(governance|board|control|charter|nonprofit|non-profit)\b", low):
        return "governance"
    if re.search(r"\b(founder|founded|born|wilsdorf|biography|origin)\b", low):
        return "founder_history"
    if re.search(r"\b(ipo|listed|public|private company|corporate structure|stock exchange)\b", low):
        return "corporate_structure"
    if re.search(r"\b(tax|revenue|billion|profit|finance|vault)\b", low):
        return "finance"
    if re.search(r"\b(legal|lawsuit|exemption|filing|deed)\b", low):
        return "legal"
    if re.search(r"\b(manufacture|manufacturing|factory|movement|assembly|series|daytona|cosmograph)\b", low):
        return "manufacturing"
    if re.search(r"\b(watch|product|dial|crown|model)\b", low) and "foundation" not in low:
        return "product"
    if re.search(r"\b(geneva|switzerland|swiss|zurich|london|city)\b", low):
        return "location"
    if re.search(r"\b(market|racing|sponsorship|tennis)\b", low):
        return "market"
    if re.search(r"\b(in \d{4}|since \d{4}|timeline)\b", low):
        return "timeline"
    if re.search(r"\b(hans|person|portrait)\b", low):
        return "person"
    if "?" in (text or ""):
        return "rhetorical"
    return "corporate_structure"


def build_replacement_intent(
    *,
    claim_id: str,
    text: str,
    topic: str = "",
    entities: list[str] | None = None,
) -> ReplacementIntent:
    domain = infer_semantic_domain(text, topic=topic)
    forbidden = sorted(_DRIFT_PAIRS.get(domain, frozenset()))
    # Always forbid product/manufacturing drift when topic is ownership/foundation
    tlow = (topic or "").lower()
    if any(k in tlow for k in ("foundation", "ownership", "shareholder", "trust", "wilsdorf")):
        if domain in {"ownership", "governance", "corporate_structure", "founder_history", "finance", "legal"}:
            forbidden = sorted(set(forbidden) | {"manufacturing", "product", "market"})
    function = {
        "ownership": "ownership",
        "governance": "power",
        "founder_history": "history",
        "corporate_structure": "contrast",
        "finance": "scale",
        "legal": "mechanism",
        "location": "location",
        "person": "history",
    }.get(domain, "contrast")
    return ReplacementIntent(
        original_claim_id=claim_id,
        narrative_role=domain if domain != "rhetorical" else "payoff",
        semantic_domain=domain,
        primary_entities=list(entities or [])[:4],
        desired_story_function=function,
        forbidden_drift_domains=forbidden,
    )


def domain_match_score(candidate_text: str, intent: ReplacementIntent) -> float:
    """1.0 = same domain; 0.0 = forbidden drift."""
    cand = infer_semantic_domain(candidate_text)
    if cand in set(intent.forbidden_drift_domains):
        return 0.0
    if cand == intent.semantic_domain:
        return 1.0
    # Soft neighbors
    neighbors = {
        "ownership": {"governance", "corporate_structure", "legal", "founder_history"},
        "governance": {"ownership", "corporate_structure", "legal"},
        "founder_history": {"person", "timeline", "ownership", "location"},
        "corporate_structure": {"ownership", "market", "governance", "contrast"},
        "finance": {"ownership", "corporate_structure"},
        "location": {"founder_history", "corporate_structure"},
        "person": {"founder_history"},
        "legal": {"ownership", "governance"},
    }
    if cand in neighbors.get(intent.semantic_domain, set()):
        return 0.7
    if cand == "rhetorical":
        return 0.2
    return 0.15


def wiki_titles_for_intent(intent: ReplacementIntent, topic: str = "") -> list[str]:
    """Query-intent scoped Wikipedia titles — never Daytona for ownership."""
    titles: list[str] = []
    ents = list(intent.primary_entities)
    tlow = (topic or "").lower()
    domain = intent.semantic_domain

    if domain in {"ownership", "governance", "corporate_structure", "legal", "finance"}:
        titles.extend(
            [
                "Hans Wilsdorf Foundation",
                "Hans Wilsdorf",
            ]
        )
        # Prefer entity pages that are NOT product-model articles
        for e in ents:
            el = (e or "").lower()
            if e and "daytona" not in el and "cosmograph" not in el and el != "rolex":
                titles.insert(0, e)
        # Rolex main page is product-heavy — only as last resort after foundation
        titles.append("Rolex")
    elif domain in {"founder_history", "person"}:
        titles.extend(["Hans Wilsdorf", "Hans Wilsdorf Foundation"])
    elif domain == "location":
        titles.extend(["Geneva", "Switzerland", "Rolex"])
    else:
        # Generic: brand from topic, not product pages
        brand = next(
            (
                w
                for w in re.findall(r"[A-Za-z][A-Za-z\-]+", topic or "")
                if w[:1].isupper() and w.lower() not in {"the", "how", "secret"}
            ),
            "",
        )
        if brand and brand.lower() not in {"daytona", "cosmograph"}:
            titles.append(brand)

    if "foundation" in tlow or "wilsdorf" in tlow or "ownership" in tlow:
        titles = ["Hans Wilsdorf Foundation", "Hans Wilsdorf"] + [
            t for t in titles if t not in {"Hans Wilsdorf Foundation", "Hans Wilsdorf"}
        ]

    # Dedup
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        k = (t or "").strip().lower()
        if not k or k in seen:
            continue
        # Hard ban product article titles for ownership intents
        if domain in {"ownership", "governance", "corporate_structure", "founder_history", "finance", "legal"}:
            if any(x in k for x in ("daytona", "cosmograph", "submariner", "datejust", "gmt")):
                continue
        seen.add(k)
        out.append(t.strip())
    return out[:6]


@dataclass
class StoryConsistencyResult:
    status: str  # PASS | REVIEW_REQUIRED | FAIL
    reasons: list[str] = field(default_factory=list)
    drift_pairs: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def evaluate_story_consistency(
    *,
    topic: str,
    raw_script: str,
    final_script: str,
    replacement_research: list[dict] | None = None,
) -> StoryConsistencyResult:
    topic_domain = infer_semantic_domain(topic + " " + (raw_script or "")[:200], topic=topic)
    final_domain = infer_semantic_domain(final_script or "", topic=topic)
    reasons: list[str] = []
    drifts: list[dict] = []

    forbidden = _DRIFT_PAIRS.get(topic_domain, frozenset())
    if final_domain in forbidden:
        reasons.append("SEMANTIC_DOMAIN_DRIFT")
        drifts.append({"from": topic_domain, "to": final_domain, "where": "final_script"})

    for fact in replacement_research or []:
        intent_domain = str(fact.get("semantic_domain") or topic_domain)
        text = str(fact.get("text") or "")
        cand = infer_semantic_domain(text)
        score = float(fact.get("domain_match_score") or domain_match_score(
            text,
            ReplacementIntent(
                original_claim_id="",
                narrative_role=intent_domain,
                semantic_domain=intent_domain,
                forbidden_drift_domains=sorted(_DRIFT_PAIRS.get(intent_domain, frozenset())),
            ),
        ))
        if score < 0.5 or cand in _DRIFT_PAIRS.get(intent_domain, frozenset()):
            reasons.append("SEMANTIC_DOMAIN_DRIFT")
            drifts.append(
                {
                    "from": intent_domain,
                    "to": cand,
                    "where": "replacement_fact",
                    "text": text[:120],
                    "score": score,
                }
            )

    # Topic about foundation/ownership but final dominated by manufacturing vocabulary
    tlow = (topic or "").lower()
    flow = (final_script or "").lower()
    if any(k in tlow for k in ("foundation", "ownership", "shareholder", "trust")):
        mfg_hits = len(re.findall(r"\b(daytona|cosmograph|series|self-winding|movement|manufacture)\b", flow))
        own_hits = len(re.findall(r"\b(foundation|own|owned|trust|shareholder|wilsdorf|private)\b", flow))
        if mfg_hits >= 3 and own_hits == 0:
            reasons.append("SEMANTIC_DOMAIN_DRIFT")
            drifts.append({"from": "ownership", "to": "manufacturing", "where": "arc_collapse"})

    reasons = list(dict.fromkeys(reasons))
    if "SEMANTIC_DOMAIN_DRIFT" in reasons and drifts:
        status = "FAIL"
    elif reasons:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS"
    return StoryConsistencyResult(status=status, reasons=reasons, drift_pairs=drifts)


def source_asset_key(
    *,
    provider: str = "",
    asset_id: str | None = None,
    url: str = "",
    path: str = "",
) -> str:
    """Canonical unique source asset identity (crop/trim do not mint new keys)."""
    aid = (asset_id or "").strip()
    if provider and aid:
        return f"{provider}:{aid}"
    if aid:
        return f"id:{aid}"
    url = (url or "").strip().split("?")[0]
    if url:
        return f"url:{url}"
    path = (path or "").strip().replace("\\", "/")
    if path:
        # Strip transform suffixes like _punch_in
        base = re.sub(r"_(?:punch_in|crop_zoom|kb|motion)\d*\.", ".", path)
        return f"path:{base}"
    return ""


def analyze_source_assets(word_to_visual: list[dict]) -> dict[str, Any]:
    reuse: dict[str, int] = {}
    by_provider: dict[str, set[str]] = {}
    by_entity: dict[str, set[str]] = {}
    by_beat: dict[str, str] = {}
    keys: list[str] = []
    for i, b in enumerate(word_to_visual or []):
        sel = b.get("selected_asset") or {}
        provider = str(sel.get("provider") or b.get("provider") or "")
        aid = sel.get("asset_id") if sel.get("asset_id") is not None else b.get("asset_id")
        url = str((sel.get("metadata") or {}).get("url") or b.get("url") or "")
        path = str(sel.get("path") or b.get("path") or "")
        key = source_asset_key(provider=provider, asset_id=str(aid) if aid is not None else None, url=url, path=path)
        if not key:
            continue
        keys.append(key)
        reuse[key] = reuse.get(key, 0) + 1
        by_provider.setdefault(provider or "unknown", set()).add(key)
        ents = b.get("primary_entities") or b.get("entities") or []
        ent0 = str(ents[0]) if ents else "none"
        by_entity.setdefault(ent0, set()).add(key)
        by_beat[str(b.get("beat") if b.get("beat") is not None else i)] = key
    unique = sorted(set(keys))
    return {
        "shot_count": len(word_to_visual or []),
        "unique_source_asset_count": len(unique),
        "unique_source_assets": unique,
        "reuse_count_per_asset": reuse,
        "reused_source_assets": sorted(k for k, n in reuse.items() if n > 1),
        "unique_source_assets_by_provider": {k: sorted(v) for k, v in by_provider.items()},
        "unique_source_assets_by_entity": {k: sorted(v) for k, v in by_entity.items()},
        "unique_source_assets_by_beat": by_beat,
    }


IMPORTANT_ROLES = frozenset(
    {"hook", "entity_proof", "document", "money", "place", "cta", "evidence"}
)

# Spec §8 important beat kinds
IMPORTANT_BEAT_KINDS = (
    "hook",
    "person_founder",
    "core_reveal",
    "evidence",
    "major_contrast",
    "payoff",
)


@dataclass
class BeatResearchRequirement:
    beat_id: str
    narrative_role: str
    semantic_domain: str
    required_fact_type: str
    required_entity: str = ""
    evidence_needed: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def classify_important_beat_kind(b: dict, *, index: int = 0) -> str | None:
    """Map a beat to hook / person_founder / core_reveal / evidence / major_contrast / payoff."""
    role = str(b.get("narrative_role") or "").lower()
    evidence = str(b.get("evidence_role") or "").lower()
    span = str(b.get("spoken_span") or "").lower()
    if index == 0 or role == "hook":
        return "hook"
    if role == "entity_proof" or evidence == "archive" or re.search(
        r"\b(founder|hans|wilsdorf|portrait|born)\b", span
    ):
        return "person_founder"
    if evidence in {"proof", "document"} or role == "document" or re.search(
        r"\b(foundation|owns?|owned|trust|shareholder|charter)\b", span
    ):
        return "core_reveal" if evidence != "document" else "evidence"
    if role == "document" or evidence == "document":
        return "evidence"
    if role in {"money", "place"} or evidence in {"contrast", "location"} or re.search(
        r"\b(public|private|ipo|exchange|versus|unlike)\b", span
    ):
        return "major_contrast"
    if role == "cta" or "?" in span:
        return "payoff"
    if role == "evidence" or evidence in {"product", "illustrative"}:
        return "evidence"
    if index == 0:
        return "hook"
    return None


def build_beat_research_requirement(b: dict, *, index: int = 0, topic: str = "") -> BeatResearchRequirement | None:
    kind = classify_important_beat_kind(b, index=index)
    if not kind:
        return None
    span = str(b.get("spoken_span") or "")
    ents = b.get("primary_entities") or b.get("entities") or []
    domain = infer_semantic_domain(span, topic=topic)
    fact_type = {
        "hook": "hook_claim",
        "person_founder": "founder_biography",
        "core_reveal": "ownership_structure",
        "evidence": "documentary_evidence",
        "major_contrast": "public_private_contrast",
        "payoff": "rhetorical_close",
    }.get(kind, "supporting_fact")
    return BeatResearchRequirement(
        beat_id=str(b.get("beat") if b.get("beat") is not None else index),
        narrative_role=kind,
        semantic_domain=domain,
        required_fact_type=fact_type,
        required_entity=str(ents[0]) if ents else "",
        evidence_needed=str(b.get("required_visual_concept") or b.get("evidence_role") or kind),
    )


def important_beat_coverage(word_to_visual: list[dict]) -> list[dict]:
    out = []
    seen_kinds: set[str] = set()
    for i, b in enumerate(word_to_visual or []):
        kind = classify_important_beat_kind(b, index=i)
        role = str(b.get("narrative_role") or "")
        evidence = str(b.get("evidence_role") or "")
        important = kind is not None or role in IMPORTANT_ROLES or i == 0
        if not important:
            continue
        sel = b.get("selected_asset") or {}
        covered = bool(sel.get("path") or b.get("path") or sel.get("asset_id") or b.get("asset_id"))
        status = "COVERED" if covered else "UNCOVERED"
        vc = str(b.get("visual_change_applied") or b.get("visual_change") or "")
        if covered and vc in {"punch_in", "crop_zoom", "reuse_with_motion", "archive_motion"}:
            # Reuse-only for an important beat is at best partial
            status = "PARTIAL"
        # Unrelated prior asset filling a new important kind → UNCOVERED for retry
        if (
            covered
            and kind
            and kind not in seen_kinds
            and vc in {"punch_in", "crop_zoom", "reuse_with_motion"}
            and kind in {"person_founder", "core_reveal", "evidence", "major_contrast"}
        ):
            status = "UNCOVERED"
        if kind:
            seen_kinds.add(kind)
        out.append(
            {
                "beat_index": i,
                "spoken_span": str(b.get("spoken_span") or "")[:120],
                "narrative_role": role,
                "important_kind": kind or role,
                "evidence_role": evidence,
                "coverage_status": status,
                "semantic_domain": infer_semantic_domain(str(b.get("spoken_span") or "")),
            }
        )
    return out


def uncovered_important_beats(word_to_visual: list[dict]) -> list[dict]:
    return [
        c
        for c in important_beat_coverage(word_to_visual)
        if c.get("coverage_status") == "UNCOVERED"
    ]
