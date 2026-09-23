"""Asset quality gate — query relevance ≠ asset relevance.

Phase 2.1: token/phrase entity evidence, entity hygiene, concept-family
compatibility. Never treats search query string as proof of asset match.
Unknown / weak evidence ≠ relevant (fail closed on entity-specific beats).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

# General hard-negatives (not brand-specific). Food/bakery etc.
DEFAULT_FORBIDDEN_CONCEPTS: frozenset[str] = frozenset(
    {
        "bakery",
        "baker",
        "cookie",
        "cookies",
        "cake",
        "cakes",
        "pastry",
        "pastries",
        "dessert",
        "desserts",
        "cupcake",
        "doughnut",
        "donut",
        "bread",
        "baking",
        "bake",
        "icing",
        "frosting",
        "dough",
        "flour",
        "chef",
        "cooking",
        "cook",
        "kitchen-food",
        "kitchen_food",
        "restaurant",
        "cafe",
        "café",
        "food",
        "foods",
        "meal",
        "recipe",
        "cuisine",
        "pizza",
        "burger",
        "sushi",
        "grocery",
        "supermarket-food",
        "construction",
        "excavator",
        "bulldozer",
        "gym",
        "workout",
        "beach",
        "surf",
        "football",
        "soccer",
        "basketball",
        "party-crowd",
        "concert",
    }
)

GENERIC_ONLY_TOKENS: frozenset[str] = frozenset(
    {
        "business",
        "meeting",
        "handshake",
        "office",
        "corporate",
        "money",
        "cash",
        "finance",
        "luxury",
        "lifestyle",
        "success",
        "teamwork",
        "presentation",
        "conference",
    }
)

# Sentence-start / closed-class — never entities (hygiene; not Rolex-specific).
NON_ENTITY_WORDS: frozenset[str] = frozenset(
    {
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "they",
        "them",
        "their",
        "it",
        "its",
        "we",
        "you",
        "he",
        "she",
        "his",
        "her",
        "every",
        "each",
        "any",
        "some",
        "all",
        "no",
        "not",
        "and",
        "or",
        "but",
        "for",
        "with",
        "from",
        "into",
        "how",
        "why",
        "what",
        "when",
        "where",
        "who",
        "whom",
        "which",
        # Value/quantity concepts — not named entities
        "billion",
        "billions",
        "million",
        "millions",
        "thousand",
        "thousands",
        "percent",
        "percentage",
        "zero",
        "one",
        "two",
        "three",
        "hundred",
        "amateurs",
        "elite",
        "founders",  # alone too weak; "Hans Wilsdorf" kept as phrase
    }
)

# Generic concept families (domain-agnostic). Conflict = reject even if token hit.
CONCEPT_FAMILY_LEXICON: dict[str, frozenset[str]] = {
    "finance": frozenset(
        {
            "billion",
            "billions",
            "million",
            "profit",
            "revenue",
            "shareholder",
            "shareholders",
            "ownership",
            "owns",
            "equity",
            "dividend",
            "dividends",
            "finance",
            "financial",
            "wealth",
            "money",
            "cash",
            "vault",
            "bank",
            "tax",
            "taxes",
            "exemption",
            "investment",
            "investor",
            "stock",
            "stocks",
            "market",
            "earnings",
            "quarterly",
        }
    ),
    "ownership": frozenset(
        {
            "ownership",
            "owns",
            "owned",
            "shareholder",
            "shareholders",
            "foundation",
            "trust",
            "equity",
            "controlling",
            "control",
            "perpetual",
        }
    ),
    "luxury_product": frozenset(
        {
            "watch",
            "watches",
            "watchmaker",
            "watchmaking",
            "timepiece",
            "crown",
            "bezel",
            "dial",
            "movement",
            "luxury",
            "boutique",
            "rolex",
            "submariner",
            "daytona",
            "datejust",
        }
    ),
    "person_archive": frozenset(
        {
            "portrait",
            "founder",
            "founders",
            "archive",
            "archival",
            "historical",
            "vintage",
            "biography",
            "person",
            "gentleman",
        }
    ),
    "geography": frozenset(
        {
            "switzerland",
            "swiss",
            "geneva",
            "zurich",
            "cityscape",
            "skyline",
            "landmark",
            "lake",
            "alps",
            "europe",
            "location",
            "country",
        }
    ),
    "document": frozenset(
        {
            "document",
            "documents",
            "legal",
            "contract",
            "contracts",
            "filing",
            "paperwork",
            "charter",
            "deed",
            "seal",
            "stamp",
            "notary",
            "tax",
            "exemption",
        }
    ),
    "nature": frozenset(
        {
            "river",
            "stream",
            "streams",
            "brook",
            "creek",
            "nature",
            "landscape",
            "flower",
            "flowers",
            "petal",
            "petals",
            "forest",
            "mountain",
            "waterfall",
            "rock",
            "rocks",
            "rural",
            "autumn",
            "hometown",
            "countryside",
        }
    ),
    "food": frozenset(
        {
            "bakery",
            "cookie",
            "cookies",
            "cake",
            "pastry",
            "food",
            "cooking",
            "restaurant",
            "dessert",
            "bread",
            "chef",
        }
    ),
}

# If need has any of left and asset has any of right → hard conflict.
CONCEPT_CONFLICT_PAIRS: tuple[tuple[frozenset[str], frozenset[str]], ...] = (
    (frozenset({"finance", "ownership", "document"}), frozenset({"nature", "food"})),
    (frozenset({"person_archive"}), frozenset({"nature", "food"})),
    (frozenset({"luxury_product"}), frozenset({"food"})),
    (frozenset({"geography"}), frozenset({"food"})),
)

_ENTITY_MIN = 0.45
_GENERIC_MIN = 0.25
_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_ENTITY_TOKEN_RE = re.compile(r"[a-z0-9]+", re.I)


@dataclass
class AssetCandidate:
    """Provider hit with whatever metadata actually exists (no invention)."""

    provider: str
    asset_id: str | None = None
    download_url: str | None = None
    title: str = ""
    tags: str = ""
    description: str = ""
    url: str = ""
    user: str = ""
    kind: str = "stock_video"
    extra: dict[str, Any] = field(default_factory=dict)

    def metadata_blob(self) -> str:
        parts = [
            self.title,
            self.tags,
            self.description,
            self.url,
            self.user,
            " ".join(str(v) for v in self.extra.values() if v),
        ]
        return " ".join(p for p in parts if p).strip()


@dataclass
class SceneNeed:
    """Minimal need contract for gate (Phase 1 — not full storyboard)."""

    queries: list[str] = field(default_factory=list)
    must_show: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    required_entities: list[str] = field(default_factory=list)
    scene_type: str = ""
    visual_intent: str = ""
    entity_specific: bool = False
    narrative_role: str = ""


@dataclass
class GateResult:
    accepted: bool
    relevance_score: float
    entity_score: float
    reason: str
    forbidden_hit: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    specificity_score: float = 0.0


# Cues that make an entity beat *specific* vs merely on-topic brand B-roll.
_PERSON_SPECIFIC_CUES = frozenset(
    {
        "portrait",
        "portraits",
        "archive",
        "archival",
        "founder",
        "founders",
        "historical",
        "vintage",
        "biography",
        "photograph",
        "photo",
        "bust",
        "statue",
    }
)
_GENERIC_BRAND_BROLL = frozenset(
    {
        "storefront",
        "store",
        "shop",
        "boutique",
        "building",
        "facade",
        "façade",
        "illuminated",
        "street",
        "cityscape",
    }
)
_DOC_SPECIFIC_CUES = frozenset(
    {
        "document",
        "documents",
        "paperwork",
        "contract",
        "deed",
        "charter",
        "filing",
        "legal",
        "seal",
        "certificate",
        "ledger",
        "foundation",
        "trust",
    }
)


def asset_fingerprint(
    *,
    provider: str | None = None,
    asset_id: str | None = None,
    url: str | None = None,
    download_url: str | None = None,
) -> str:
    """Stable id for reuse tracking (provider+id, else canonical URL)."""
    pid = str(provider or "").strip().lower()
    aid = str(asset_id or "").strip().lower()
    if pid and aid:
        return f"{pid}:{aid}"
    for u in (url, download_url):
        s = str(u or "").strip().lower().split("?")[0].rstrip("/")
        if s:
            return f"url:{s}"
    return ""


def compute_specificity_score(
    need: SceneNeed,
    blob: str,
    *,
    entities: Sequence[str],
    entity_score: float,
) -> float:
    """How specific the asset is to *this* beat — not just topical relevance.

    Person entity + archive portrait ≫ same brand storefront.
    Explained by entity phrase hits + intent-aligned cue families.
    """
    blob_l = (blob or "").lower()
    toks = _tokens(blob_l)
    need_text = " ".join(
        [
            need.visual_intent or "",
            need.scene_type or "",
            need.narrative_role or "",
            " ".join(entities),
        ]
    )
    need_fams = detect_concept_families(need_text)
    asset_fams = detect_concept_families(blob_l)

    personish = bool(need_fams & {"person_archive"}) or any(
        len(str(e).split()) >= 2 for e in entities
    )
    locish = bool(need_fams & {"geography"}) or any(
        e.lower() in {"geneva", "switzerland", "swiss", "zurich"}
        for e in entities
    )
    docish = bool(need_fams & {"document", "ownership", "finance"})

    score = 0.35 * float(entity_score)

    if personish and entities:
        has_person_phrase = any(entity_phrase_in_blob(e, blob_l) for e in entities)
        has_person_cue = bool(toks & _PERSON_SPECIFIC_CUES) or (
            "person_archive" in asset_fams
        )
        generic_broll = bool(toks & _GENERIC_BRAND_BROLL) and not has_person_cue
        if has_person_phrase and has_person_cue:
            score = max(score, 0.92)
        elif has_person_phrase and not generic_broll:
            score = max(score, 0.7)
        elif generic_broll and not has_person_phrase:
            score = min(score, 0.25)
        elif generic_broll:
            score = min(score, 0.35)

    if locish:
        if "geography" in asset_fams and entity_score > 0:
            score = max(score, 0.8)
        elif toks & _GENERIC_BRAND_BROLL and entity_score <= 0:
            score = min(score, 0.3)

    if docish:
        if toks & _DOC_SPECIFIC_CUES or "document" in asset_fams:
            score = max(score, 0.75 + 0.15 * entity_score)
        elif "luxury_product" in asset_fams and not (toks & _DOC_SPECIFIC_CUES):
            score = min(score, 0.4)

    if not personish and entity_score > 0 and "luxury_product" in asset_fams:
        score = max(score, 0.65 + 0.2 * entity_score)

    return max(0.0, min(1.0, score))


def reuse_penalty(fingerprint: str, recent: Sequence[str], *, window: int = 3) -> float:
    """Exact recent duplicate → strong penalty; older in window → milder."""
    fp = (fingerprint or "").strip()
    if not fp or not recent:
        return 0.0
    tail = [r for r in list(recent)[-window:] if r]
    if not tail:
        return 0.0
    if tail[-1] == fp:
        return 0.9
    if fp in tail:
        return 0.55
    return 0.0


def novelty_bonus(
    blob: str,
    recent_blobs: Sequence[str],
) -> float:
    """Reward assets whose concept families differ from recent selections."""
    if not recent_blobs:
        return 0.15
    cur = detect_concept_families(blob or "")
    if not cur:
        return 0.0
    prev: set[str] = set()
    for b in recent_blobs[-3:]:
        prev |= detect_concept_families(b or "")
    if not prev:
        return 0.1
    new = cur - prev
    if new:
        return min(0.2, 0.08 * len(new))
    return -0.05


def selection_score(
    gate: GateResult,
    *,
    reuse_pen: float = 0.0,
    novelty: float = 0.0,
) -> float:
    """Rank accepted candidates: relevance + specificity − reuse + novelty."""
    if not gate.accepted:
        return -1.0
    return (
        0.40 * gate.relevance_score
        + 0.45 * gate.specificity_score
        + 0.15 * max(novelty, 0.0)
        - reuse_pen
        + min(novelty, 0.0)  # apply small negative novelty too
    )


def build_metadata_blob(meta: dict[str, Any] | None) -> str:
    if not meta:
        return ""
    keys = (
        "title",
        "tags",
        "description",
        "url",
        "user",
        "alt",
        "slug",
        "page_url",
        "photographer",
    )
    parts = [str(meta.get(k) or "") for k in keys]
    return " ".join(p for p in parts if p).strip()


def candidate_from_meta(
    *,
    provider: str,
    download_url: str | None,
    asset_id: Any = None,
    kind: str = "stock_video",
    meta: dict[str, Any] | None = None,
) -> AssetCandidate:
    m = meta or {}
    return AssetCandidate(
        provider=provider,
        asset_id=str(asset_id) if asset_id is not None else None,
        download_url=download_url,
        title=str(m.get("title") or ""),
        tags=str(m.get("tags") or ""),
        description=str(m.get("description") or m.get("alt") or ""),
        url=str(m.get("url") or m.get("page_url") or ""),
        user=str(m.get("user") or m.get("photographer") or ""),
        kind=kind,
        extra={
            k: v
            for k, v in m.items()
            if k
            not in {
                "title",
                "tags",
                "description",
                "alt",
                "url",
                "page_url",
                "user",
                "photographer",
            }
            and v
        },
    )


def _tokens(text: str) -> set[str]:
    return {w.lower() for w in _WORD_RE.findall(text or "")}


def is_non_entity_token(word: str) -> bool:
    w = (word or "").strip().lower()
    return (not w) or w in NON_ENTITY_WORDS or len(w) < 2


def hygienize_entities(raw: Sequence[str] | None, *, limit: int = 6) -> list[str]:
    """Drop closed-class / value words; keep multi-word phrases; dedupe."""
    out: list[str] = []
    seen: set[str] = set()
    for item in raw or []:
        s = " ".join(str(item or "").split()).strip()
        if not s:
            continue
        parts = s.split()
        # Drop if every token is non-entity (e.g. "Every", "The")
        if all(is_non_entity_token(p) for p in parts):
            continue
        # Strip leading/trailing non-entity tokens from phrases
        while parts and is_non_entity_token(parts[0]):
            parts = parts[1:]
        while parts and is_non_entity_token(parts[-1]):
            parts = parts[:-1]
        if not parts or all(is_non_entity_token(p) for p in parts):
            continue
        cleaned = " ".join(parts)
        key = cleaned.lower()
        if key in seen:
            continue
        # Prefer keeping longer phrase; skip if subsumed by existing longer
        if any(key != e.lower() and key in e.lower().split() for e in out):
            continue
        # Remove shorter fragments already covered by this phrase
        out = [e for e in out if e.lower() not in key.split() or e.lower() == key]
        if key not in {e.lower() for e in out}:
            out.append(cleaned)
            seen.add(key)
        if len(out) >= limit:
            break
    return out


def entity_phrase_in_blob(entity: str, blob: str) -> bool:
    """Token/phrase boundary match — NOT raw substring (every ∉ every flower)."""
    ent = " ".join((entity or "").split()).strip().lower()
    if not ent or is_non_entity_token(ent):
        return False
    text = (blob or "").lower()
    # Normalize separators so tags "hans, wilsdorf" still match phrase.
    norm = re.sub(r"[,;/|]+", " ", text)
    norm = re.sub(r"\s+", " ", norm)
    parts = ent.split()
    if len(parts) == 1:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(parts[0])}(?![a-z0-9])", norm))
    # Multi-word: adjacent tokens in order (allow single filler between? no — strict adjacent)
    pattern = r"(?<![a-z0-9])" + r"\s+".join(re.escape(p) for p in parts) + r"(?![a-z0-9])"
    return bool(re.search(pattern, norm))


def detect_concept_families(text: str) -> set[str]:
    toks = _tokens(text)
    families: set[str] = set()
    for fam, lex in CONCEPT_FAMILY_LEXICON.items():
        if toks & lex:
            families.add(fam)
    return families


def concept_families_conflict(need_families: set[str], asset_families: set[str]) -> str | None:
    for need_side, asset_side in CONCEPT_CONFLICT_PAIRS:
        if need_families & need_side and asset_families & asset_side:
            return f"{sorted(need_families & need_side)} vs {sorted(asset_families & asset_side)}"
    return None


def _forbidden_hit(blob_low: str, forbidden: Sequence[str]) -> str | None:
    for tok in forbidden:
        t = (tok or "").strip().lower()
        if not t:
            continue
        if " " in t or "-" in t:
            if t in blob_low:
                return t
        else:
            if re.search(rf"(?<![a-z]){re.escape(t)}(?![a-z])", blob_low):
                return t
    return None


def evaluate_asset(
    candidate: AssetCandidate | dict[str, Any],
    need: SceneNeed,
    *,
    min_score: float | None = None,
) -> GateResult:
    """Accept/reject using candidate metadata only — never the search query alone."""
    if isinstance(candidate, dict):
        cand = candidate_from_meta(
            provider=str(candidate.get("provider") or "unknown"),
            download_url=candidate.get("download_url") or candidate.get("url"),
            asset_id=candidate.get("asset_id") or candidate.get("id"),
            kind=str(candidate.get("kind") or "stock_video"),
            meta=candidate.get("metadata") or candidate,
        )
    else:
        cand = candidate

    blob = cand.metadata_blob()
    if not blob:
        return GateResult(
            accepted=False,
            relevance_score=0.0,
            entity_score=0.0,
            reason="no_asset_metadata",
            details={"provider": cand.provider},
        )

    blob_low = blob.lower()
    forbidden = list(DEFAULT_FORBIDDEN_CONCEPTS) + [
        a for a in (need.avoid or []) if a
    ]
    hit = _forbidden_hit(blob_low, forbidden)
    if hit:
        return GateResult(
            accepted=False,
            relevance_score=-10.0,
            entity_score=0.0,
            reason="forbidden_concept",
            forbidden_hit=hit,
            details={"provider": cand.provider, "blob_excerpt": blob[:160]},
        )

    entities = hygienize_entities(
        list(need.required_entities or []) or list(need.must_show or [])
    )
    entity_specific = bool(need.entity_specific or entities)

    entity_hits = sum(1 for e in entities if entity_phrase_in_blob(e, blob))
    entity_score = (entity_hits / len(entities)) if entities else 0.0

    need_text = " ".join(
        [
            need.visual_intent or "",
            need.scene_type or "",
            need.narrative_role or "",
            " ".join(entities),
            " ".join(need.must_show or []),
        ]
    )
    # Do NOT fold enriched search queries into family detection — topic strings like
    # "How Rolex is owned…" would paint every beat as ownership and conflict with
    # valid Rolex product B-roll that mentions "nature" in alt text.
    need_families = detect_concept_families(need_text)
    asset_families = detect_concept_families(blob)
    conflict = concept_families_conflict(need_families, asset_families)
    if conflict:
        return GateResult(
            accepted=False,
            relevance_score=0.0,
            entity_score=entity_score,
            reason="semantic_conflict",
            details={
                "provider": cand.provider,
                "conflict": conflict,
                "need_families": sorted(need_families),
                "asset_families": sorted(asset_families),
                "blob_excerpt": blob[:160],
            },
        )

    query_tokens: set[str] = set()
    for q in need.queries or []:
        query_tokens |= _tokens(q)
    query_tokens -= GENERIC_ONLY_TOKENS
    query_tokens -= NON_ENTITY_WORDS
    blob_tokens = _tokens(blob)
    if query_tokens:
        topical = len(query_tokens & blob_tokens) / max(len(query_tokens), 1)
    else:
        topical = 0.0

    # Compatible family overlap as weak positive signal (not query self-score).
    family_overlap = need_families & asset_families
    family_boost = 0.15 if family_overlap else 0.0

    generic_only = bool(blob_tokens) and blob_tokens <= (
        GENERIC_ONLY_TOKENS | _tokens("the and for with")
    )

    # Entity-specific: missing entities → reject (unknown ≠ relevant).
    if entity_specific and entities and entity_hits == 0:
        return GateResult(
            accepted=False,
            relevance_score=topical,
            entity_score=0.0,
            reason="missing_required_entities",
            details={
                "provider": cand.provider,
                "required": entities,
                "topical": round(topical, 3),
                "blob_excerpt": blob[:160],
            },
        )

    # Entity match alone is not enough without topical/family support when
    # the beat carries a strong non-product concept (finance/document/ownership).
    strong_need = need_families & {"finance", "ownership", "document", "person_archive"}
    if entity_specific and entity_hits > 0 and strong_need and not family_overlap:
        # Pure incidental entity token with conflicting or empty asset concepts
        if topical < 0.2 and not (asset_families & strong_need):
            return GateResult(
                accepted=False,
                relevance_score=topical,
                entity_score=entity_score,
                reason="weak_concept_evidence",
                details={
                    "provider": cand.provider,
                    "need_families": sorted(need_families),
                    "asset_families": sorted(asset_families),
                    "blob_excerpt": blob[:160],
                },
            )

    relevance = 0.50 * topical + 0.35 * entity_score + 0.15 * (
        1.0 if family_overlap else 0.0
    )
    relevance = min(1.0, relevance + family_boost * 0.0)  # family already in mix
    if generic_only and entity_specific:
        relevance *= 0.3

    threshold = (
        min_score
        if min_score is not None
        else (_ENTITY_MIN if entity_specific else _GENERIC_MIN)
    )

    specificity = compute_specificity_score(
        need, blob, entities=entities, entity_score=entity_score
    )

    if relevance < threshold:
        return GateResult(
            accepted=False,
            relevance_score=relevance,
            entity_score=entity_score,
            specificity_score=specificity,
            reason="below_threshold",
            details={
                "provider": cand.provider,
                "threshold": threshold,
                "topical": round(topical, 3),
                "blob_excerpt": blob[:160],
            },
        )

    # Final fail-closed: entity-specific still needs either entity evidence or
    # compatible family evidence — never accept on topical crumbs alone.
    if entity_specific and entity_hits == 0 and not family_overlap:
        return GateResult(
            accepted=False,
            relevance_score=relevance,
            entity_score=entity_score,
            specificity_score=specificity,
            reason="insufficient_evidence",
            details={"provider": cand.provider, "blob_excerpt": blob[:160]},
        )

    # Named-entity person moment: reject generic brand storefront when no
    # person-specific cues — prefer miss over wrong specificity.
    personish = bool(need_families & {"person_archive"}) or any(
        len(e.split()) >= 2 for e in entities
    )
    if (
        personish
        and entity_specific
        and specificity < 0.45
        and (_tokens(blob) & _GENERIC_BRAND_BROLL)
        and not (_tokens(blob) & _PERSON_SPECIFIC_CUES)
    ):
        return GateResult(
            accepted=False,
            relevance_score=relevance,
            entity_score=entity_score,
            specificity_score=specificity,
            reason="low_specificity",
            details={
                "provider": cand.provider,
                "blob_excerpt": blob[:160],
                "hint": "person_entity_prefers_archive_portrait",
            },
        )

    return GateResult(
        accepted=True,
        relevance_score=relevance,
        entity_score=entity_score,
        specificity_score=specificity,
        reason="accepted",
        details={
            "provider": cand.provider,
            "topical": round(topical, 3),
            "threshold": threshold,
            "need_families": sorted(need_families),
            "asset_families": sorted(asset_families),
            "specificity": round(specificity, 3),
        },
    )


def scene_need_from_plan(
    *,
    queries: list[str],
    must_show: list[str] | None = None,
    avoid: list[str] | None = None,
    required_entities: list[str] | None = None,
    scene_type: str = "",
    visual_intent: str = "",
    narrative_role: str = "",
) -> SceneNeed:
    raw_ents = list(required_entities or must_show or [])
    ents = hygienize_entities(raw_ents)
    must = hygienize_entities(must_show) if must_show else list(ents)
    return SceneNeed(
        queries=list(queries or []),
        must_show=must,
        avoid=list(avoid or []),
        required_entities=ents,
        scene_type=scene_type,
        visual_intent=visual_intent,
        entity_specific=bool(ents),
        narrative_role=narrative_role or "",
    )
