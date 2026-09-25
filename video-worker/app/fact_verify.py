"""Fact verification provider — evidence from web/reference sources (not AIRouter memory)."""
from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any
from urllib.parse import quote_plus

from app.http_client import session
from app.script_claims import ScriptClaim

logger = logging.getLogger(__name__)

_UA = "sosyal-medya-otomasyon/script-factcheck (local; documentary verification)"


@dataclass
class VerificationResult:
    claim_id: str
    status: str  # supported|partially_supported|unsupported|conflicting|unknown
    confidence: float = 0.0
    sources: list[dict] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


class FactVerificationProvider:
    """Fetch evidence snippets then score claim support.

    Uses Wikipedia (and light web search) as evidence — never treats LLM
    parametric memory as verification.
    """

    def verify_claims(
        self,
        claims: list[ScriptClaim],
        *,
        topic: str = "",
    ) -> list[VerificationResult]:
        # Cache only pages relevant to the requested topic and its claims.
        entity_cache: dict[str, dict] = {}
        seed_titles = []
        if topic:
            seed_titles.append(topic.split(":")[0].strip())
        for token in seed_titles:
            if len(token.split()) <= 6 and token[:1].isupper():
                k = token.lower()
                if k not in entity_cache:
                    entity_cache[k] = self._wikipedia_evidence(token) or {}

        for c in claims:
            if not c.verification_required:
                continue
            for e in c.entities or []:
                key = e.strip().lower()
                if key and key not in entity_cache and len(e.split()) <= 5:
                    entity_cache[key] = self._wikipedia_evidence(e) or {}

        results: list[VerificationResult] = []
        for c in claims:
            if not c.verification_required:
                results.append(
                    VerificationResult(
                        claim_id=c.claim_id,
                        status="supported",
                        confidence=0.9,
                        sources=[],
                        notes="rhetorical_or_low_risk_skip",
                    )
                )
                continue
            try:
                results.append(self._verify_one(c, entity_cache, topic=topic))
            except Exception as exc:
                logger.warning("verification failed for %s: %s", c.claim_id, exc)
                results.append(
                    VerificationResult(
                        claim_id=c.claim_id,
                        status="unknown",
                        confidence=0.0,
                        sources=[],
                        notes=f"verification_error:{exc}",
                    )
                )
        return results

    def _verify_one(
        self,
        claim: ScriptClaim,
        entity_cache: dict[str, dict],
        *,
        topic: str,
    ) -> VerificationResult:
        blobs: list[str] = []
        sources: list[dict] = []
        for e in claim.entities or []:
            ev = entity_cache.get(e.strip().lower()) or {}
            if ev.get("extract"):
                blobs.append(str(ev["extract"]))
                sources.append(
                    {
                        "title": ev.get("title"),
                        "url": ev.get("url"),
                        "provider": "wikipedia",
                    }
                )
        topic_key = topic.split(":")[0].strip().lower()
        claim_text = claim.text.lower()
        claim_entities = [e.strip().lower() for e in claim.entities or [] if e.strip()]
        if not blobs and topic_key and (not claim_entities or topic_key in claim_text):
            ev = entity_cache.get(topic_key) or {}
            if ev.get("extract"):
                blobs.append(str(ev["extract"]))
                sources.append(
                    {"title": ev.get("title"), "url": ev.get("url"), "provider": "wikipedia"}
                )
        if not blobs:
            extra = self._wikipedia_search_extract(
                " ".join((claim.entities or [])[:2]) or (topic.split(":")[0] if topic else claim.text[:60])
            )
            if extra and extra.get("extract"):
                blobs.append(str(extra["extract"]))
                sources.append(
                    {
                        "title": extra.get("title"),
                        "url": extra.get("url"),
                        "provider": "wikipedia",
                    }
                )

        if not blobs:
            return VerificationResult(
                claim_id=claim.claim_id,
                status="unknown",
                confidence=0.1,
                sources=sources,
                notes="no_evidence_fetched",
            )

        evidence = " ".join(blobs).lower()
        status, conf, notes = _score_against_evidence(claim, evidence)
        return VerificationResult(
            claim_id=claim.claim_id,
            status=status,
            confidence=conf,
            sources=sources[:5],
            notes=notes,
        )

    def _wikipedia_evidence(self, title: str) -> dict[str, Any] | None:
        title = (title or "").strip()
        if not title:
            return None
        try:
            # Resolve best page via search
            sr = session.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "list": "search",
                    "srsearch": title,
                    "srlimit": 3,
                    "format": "json",
                },
                headers={"User-Agent": _UA},
                timeout=8,
            )
            if sr.status_code != 200:
                return None
            hits = (sr.json().get("query") or {}).get("search") or []
            if not hits:
                return None
            page_title = hits[0].get("title") or title
            return self._wikipedia_extract(str(page_title))
        except Exception as exc:
            logger.info("wiki evidence miss (%s): %s", title, exc)
            return None

    def _wikipedia_search_extract(self, query: str) -> dict[str, Any] | None:
        return self._wikipedia_evidence(query)

    def _wikipedia_extract(self, page_title: str) -> dict[str, Any] | None:
        try:
            r = session.get(
                "https://en.wikipedia.org/w/api.php",
                params={
                    "action": "query",
                    "prop": "extracts|info",
                    "exintro": 1,
                    "explaintext": 1,
                    "titles": page_title,
                    "inprop": "url",
                    "format": "json",
                },
                headers={"User-Agent": _UA},
                timeout=8,
            )
            if r.status_code != 200:
                return None
            pages = (r.json().get("query") or {}).get("pages") or {}
            for _pid, page in pages.items():
                if str(_pid) == "-1":
                    continue
                extract = (page.get("extract") or "")[:2500]
                if not extract:
                    continue
                return {
                    "title": page.get("title") or page_title,
                    "extract": extract,
                    "url": page.get("fullurl")
                    or f"https://en.wikipedia.org/wiki/{quote_plus(page_title.replace(' ', '_'))}",
                }
        except Exception as exc:
            logger.info("wiki extract miss (%s): %s", page_title, exc)
        return None

    def research_replacement_facts(
        self,
        topic: str,
        *,
        purposes: list[str] | None = None,
        max_facts: int = 4,
        banned_markers: list[str] | None = None,
        intents: list | None = None,
    ) -> list[dict]:
        """Pull domain-locked Wikipedia facts — never ownership→Daytona drift.

        Never invents. Each fact carries source URL + domain_match_score.
        """
        from app.story_domains import (
            ReplacementIntent,
            build_replacement_intent,
            domain_match_score,
            infer_semantic_domain,
            wiki_titles_for_intent,
        )

        banned = [b.lower() for b in (banned_markers or []) if b]
        intent_list: list[ReplacementIntent] = list(intents or [])
        if not intent_list:
            # Derive from purposes / topic
            domain = infer_semantic_domain(topic, topic=topic)
            intent_list = [
                build_replacement_intent(
                    claim_id="topic",
                    text=topic,
                    topic=topic,
                )
            ]
            _ = purposes  # purposes absorbed into intent domains

        facts: list[dict] = []
        seen_text: set[str] = set()
        for intent in intent_list:
            titles = wiki_titles_for_intent(intent, topic=topic)
            for title in titles:
                ev = self._wikipedia_evidence(title) or {}
                extract = str(ev.get("extract") or "")
                if not extract:
                    continue
                # Skip clearly product-model pages for ownership intents
                page_title = str(ev.get("title") or title).lower()
                if intent.semantic_domain in {
                    "ownership",
                    "governance",
                    "corporate_structure",
                    "founder_history",
                    "finance",
                    "legal",
                }:
                    if any(
                        x in page_title
                        for x in ("daytona", "cosmograph", "submariner", "datejust", "gmt-master")
                    ):
                        continue
                for sent in re.split(r"(?<=[.!?])\s+", extract):
                    s = sent.strip()
                    if len(s.split()) < 6 or len(s.split()) > 32:
                        continue
                    low = s.lower()
                    key = low[:60]
                    if key in seen_text:
                        continue
                    if any(b and b in low for b in banned if len(b) > 12):
                        continue
                    if re.search(
                        r"\btax-free\b|\bentire market\b|\bchannels billions\b|\bsecretly\b",
                        low,
                    ):
                        continue
                    if re.search(
                        r"\b(auction|sold for|tennis|photographed|racing|sponsorship)\b",
                        low,
                    ):
                        continue
                    score = domain_match_score(s, intent)
                    if score < 0.5:
                        continue
                    # Extra: manufacturing vocabulary blocked for ownership intents
                    if intent.semantic_domain in {
                        "ownership",
                        "governance",
                        "corporate_structure",
                        "finance",
                        "legal",
                    } and re.search(
                        r"\b(daytona|cosmograph|self-winding|series introduced|hand-wound)\b",
                        low,
                    ):
                        continue
                    seen_text.add(key)
                    facts.append(
                        {
                            "text": s if s.endswith((".", "!", "?")) else s + ".",
                            "purpose": intent.desired_story_function or intent.semantic_domain,
                            "semantic_domain": infer_semantic_domain(s),
                            "intent_domain": intent.semantic_domain,
                            "domain_match_score": score,
                            "source": {
                                "title": ev.get("title"),
                                "url": ev.get("url"),
                                "provider": "wikipedia",
                            },
                            "verified": True,
                            "replacement_intent": intent.to_dict(),
                        }
                    )
                    if len(facts) >= max_facts:
                        return facts
        return facts


def _purpose_for_sentence(low: str, purposes: list[str]) -> str | None:
    mapping = {
        "ownership": r"\b(own|owned|ownership|foundation|trust|private|shareholder)\b",
        "history": r"\b(founded|founder|established|began|in \d{4}|born)\b",
        "person": r"\b(hans|wilsdorf|founder|chairman|ceo)\b",
        "contrast": r"\b(public|stock exchange|listed|ipo|privately)\b",
        "mechanism": r"\b(manufacture|movement|watch|production|swiss)\b",
        "scale": r"\b(largest|major|leading|worldwide|global)\b",
        "location": r"\b(geneva|switzerland|swiss|zurich)\b",
    }
    for p in purposes:
        pat = mapping.get(p)
        if pat and re.search(pat, low):
            return p
    # Accept any sentence with a year + proper content as history if requested
    if "history" in purposes and re.search(r"\b(1[89]\d{2}|20\d{2})\b", low):
        return "history"
    return None


def _score_against_evidence(claim: ScriptClaim, evidence: str) -> tuple[str, float, str]:
    """Heuristic support scoring — never invents support without evidence text."""
    text = (claim.text or "").lower()
    ctype = claim.claim_type

    # Numbers in claim must appear in evidence for strong support
    nums = re.findall(r"\b\d{4}\b|\b100\s*%|\b100%\b|\$?[\d,.]+\s*(?:billion|million)?", text)
    num_hits = 0
    for n in nums:
        token = re.sub(r"\s+", "", n.lower()).replace("%", "")
        if token and token in evidence.replace(" ", "").replace("%", ""):
            num_hits += 1
        elif n.strip() in evidence:
            num_hits += 1

    # Ownership / foundation language
    ownership_cues = ("foundation", "own", "shareholder", "trust", "wilsdorf")
    ownership_hit = sum(1 for c in ownership_cues if c in text and c in evidence)

    tax_cues = ("tax", "exempt", "charity", "nonprofit", "non-profit")
    tax_hit = sum(1 for c in tax_cues if c in text and c in evidence)

    # Absolute market-control rarely supportable from intro extracts
    if re.search(r"entire\s+(?:global\s+)?(?:luxury\s+)?market|controls?\s+the\s+entire", text):
        if "market" not in evidence or "entire" not in evidence:
            return "unsupported", 0.75, "absolute_market_control_not_in_evidence"

    # Absolute "no shareholders" without "public" is over-strong vs typical wiki wording
    if re.search(r"\bno shareholders\b|\bnot one\b|\bzero public equity\b", text):
        if "shareholder" in evidence or "privately" in evidence or "private" in evidence:
            if "public" in text:
                return "partially_supported", 0.6, "private_ownership_public_equity"
            return "partially_supported", 0.5, "soften_to_no_public_shareholders"
        return "unsupported", 0.65, "shareholder_absolute_not_in_evidence"

    if re.search(r"\bno board meetings\b|\bno external audits\b|operational opacity|absolute sovereignty|no public filings|no quarterly earnings|silent dominance|^zero\.?$", text):
        return "unsupported", 0.8, "governance_opacity_not_in_evidence"

    if re.search(r"\b100%\b", text) and "100%" not in evidence and "100 percent" not in evidence:
        if "foundation" in evidence and "own" in evidence:
            return "partially_supported", 0.5, "ownership_ok_percent_unverified"
        return "unsupported", 0.65, "percent_not_in_evidence"

    if re.search(r"\btotal control\b", text):
        if "foundation" in evidence and ("own" in evidence or "wilsdorf" in evidence):
            return "partially_supported", 0.55, "foundation_owns_soften_total_control"
        return "unknown", 0.35, "total_control_weak"

    if ctype == "tax" or "tax-free" in text or "tax free" in text:
        # Wikipedia often says charitable / foundation — "tax-free" as absolute is risky
        if "tax" in evidence and ("exempt" in evidence or "charit" in evidence):
            return "partially_supported", 0.55, "tax_language_present_soften_absolute"
        if tax_hit:
            return "partially_supported", 0.45, "weak_tax_overlap"
        return "unsupported", 0.7, "tax_claim_not_supported_by_evidence"

    if ctype in {"ownership", "corporate", "biographical", "historical"}:
        if ownership_hit >= 2 and (not nums or num_hits == len(nums)):
            return "supported", 0.8, "entity_ownership_aligned"
        if ownership_hit >= 1:
            if nums and num_hits < len(nums):
                return "partially_supported", 0.5, "ownership_ok_number_weak"
            return "partially_supported", 0.55, "partial_ownership_overlap"
        if nums and num_hits == 0:
            return "unsupported", 0.65, "number_not_in_evidence"
        return "unknown", 0.3, "insufficient_overlap"

    if ctype in {"financial", "numerical"}:
        if "billion" in text and "billion" not in evidence:
            return "unsupported", 0.7, "billion_not_in_evidence"
        if num_hits and ownership_hit:
            return "partially_supported", 0.5, "finance_partial"
        if num_hits:
            return "partially_supported", 0.45, "number_partial"
        return "unsupported", 0.6, "finance_unsupported"

    # Default
    token_hits = sum(
        1
        for w in re.findall(r"[a-z]{4,}", text)
        if w not in {"that", "with", "from", "this", "have", "into"} and w in evidence
    )
    if token_hits >= 4:
        return "partially_supported", 0.5, "lexical_overlap"
    if token_hits >= 2:
        return "unknown", 0.35, "weak_overlap"
    return "unsupported", 0.55, "no_meaningful_support"
