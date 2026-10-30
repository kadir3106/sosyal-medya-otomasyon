"""Script quality layer: claim decisions, linguistic guards, batch quality editor."""
from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from app.config import config
from app.fact_verify import FactVerificationProvider, VerificationResult
from app.http_client import session
from app.script_claims import ScriptClaim, extract_claims

logger = logging.getLogger(__name__)

# Approximate English words-per-minute for TTS pacing (pipeline short-form).
_DEFAULT_WPM = 155.0
_TARGET_DURATION_SEC = (22.0, 38.0)  # keep short-form documentary length


@dataclass
class ClaimDecision:
    claim_id: str
    action: str  # keep|soften|remove|replace
    reason: str
    original: str
    rewritten: str | None = None
    evidence_status: str = "unknown"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScriptQualityResult:
    raw_script: str
    final_script: str
    claims: list[dict] = field(default_factory=list)
    verification_summary: dict = field(default_factory=dict)
    claim_decisions: list[dict] = field(default_factory=list)
    quality_checks: dict = field(default_factory=dict)
    estimated_duration: float = 0.0
    hook: str = ""
    loop_strategy: str = "optional_seamless"
    llm_calls: int = 0
    search_calls: int = 0
    verification_outage: bool = False
    review_required: bool = False
    replacement_research: list[dict] = field(default_factory=list)
    rejected_claims: list[dict] = field(default_factory=list)
    replacement_intents: list[dict] = field(default_factory=list)
    story_consistency: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


_INCOMPLETE_RE = re.compile(
    r"^(?:founder|owner|ceo|company|brand)\s+[A-Z][\w\s]{0,40}"
    r"(?:locked|owns|controls?)\s+(?:\d+%|100%|billions?)\.?$",
    re.I,
)
_NOUN_STACK_RE = re.compile(
    r"\b(?:real\s+estate\s+amateurs|fast\s+cash\s+elites|"
    r"companies\s+for\s+fast\s+cash)\b",
    re.I,
)
_DANGLING_RE = re.compile(
    r"^(?:for\s+\w+\s+\w+|quietly|meanwhile|instead)\s+\w+\s*$",
    re.I,
)


def estimate_duration_sec(script: str, *, wpm: float = _DEFAULT_WPM) -> float:
    words = len((script or "").split())
    if wpm <= 0:
        wpm = _DEFAULT_WPM
    return round(words / wpm * 60.0, 2)


def linguistic_quality_issues(script: str) -> list[str]:
    """Detect incomplete / unnatural spoken-English problems (not blacklist)."""
    issues: list[str] = []
    text = " ".join((script or "").split())
    if not text:
        return ["empty_script"]
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    for s in sentences:
        words = s.split()
        # incomplete clause / fragment without finite verb
        has_verb = bool(
            re.search(
                r"\b(is|are|was|were|has|have|had|owns?|owned|controls?|"
                r"locked|built|builds|channels?|moved|moves|founded|"
                r"transferred|creates?|created|became|becomes)\b",
                s,
                re.I,
            )
        )
        if len(words) >= 3 and not has_verb and not s.endswith("?"):
            issues.append(f"missing_verb:{s[:60]}")
        if _INCOMPLETE_RE.match(s) or (len(words) <= 8 and re.search(r"locked\s+100%", s, re.I)):
            issues.append(f"incomplete_clause:{s[:60]}")
        if _NOUN_STACK_RE.search(s):
            issues.append(f"noun_stacking:{s[:60]}")
        if _DANGLING_RE.match(s):
            issues.append(f"dangling_phrase:{s[:60]}")
        # subject-less compressed claim
        if re.match(r"^(?:channels?|locks?|controls?)\s+", s, re.I) and len(words) < 10:
            issues.append(f"missing_subject:{s[:60]}")
    # repeated openers
    openers = [s.split()[0].lower() for s in sentences if s.split()]
    if len(openers) >= 3 and len(set(openers)) == 1:
        issues.append("repeated_sentence_structure")
    return issues


def decide_claims(
    claims: list[ScriptClaim],
    verifications: list[VerificationResult],
    *,
    outage: bool = False,
) -> list[ClaimDecision]:
    by_id = {v.claim_id: v for v in verifications}
    decisions: list[ClaimDecision] = []
    for c in claims:
        v = by_id.get(c.claim_id)
        status = (v.status if v else "unknown")
        if not c.verification_required:
            decisions.append(
                ClaimDecision(
                    claim_id=c.claim_id,
                    action="keep",
                    reason="rhetorical_or_low_risk",
                    original=c.text,
                    rewritten=None,
                    evidence_status=status,
                )
            )
            continue

        if outage and c.risk == "HIGH":
            decisions.append(
                ClaimDecision(
                    claim_id=c.claim_id,
                    action="remove",
                    reason="verification_outage_fail_closed",
                    original=c.text,
                    rewritten=None,
                    evidence_status="unknown",
                )
            )
            continue

        if status == "supported":
            decisions.append(
                ClaimDecision(
                    claim_id=c.claim_id,
                    action="keep",
                    reason="supported_by_evidence",
                    original=c.text,
                    rewritten=None,
                    evidence_status=status,
                )
            )
        elif status == "partially_supported":
            soft = _soften_locally(c.text, c.claim_type)
            if not soft.strip():
                decisions.append(
                    ClaimDecision(
                        claim_id=c.claim_id,
                        action="remove",
                        reason="partial_softened_to_empty",
                        original=c.text,
                        rewritten=None,
                        evidence_status=status,
                    )
                )
            else:
                decisions.append(
                    ClaimDecision(
                        claim_id=c.claim_id,
                        action="soften",
                        reason="partial_evidence",
                        original=c.text,
                        rewritten=soft,
                        evidence_status=status,
                    )
                )
        elif status in {"unsupported", "conflicting"}:
            decisions.append(
                ClaimDecision(
                    claim_id=c.claim_id,
                    action="remove",
                    reason=f"{status}_high_or_medium_risk"
                    if c.risk in {"HIGH", "MEDIUM"}
                    else f"{status}",
                    original=c.text,
                    rewritten=None,
                    evidence_status=status,
                )
            )
        else:  # unknown
            if c.risk == "HIGH":
                decisions.append(
                    ClaimDecision(
                        claim_id=c.claim_id,
                        action="remove",
                        reason="unknown_high_risk_fail_closed",
                        original=c.text,
                        rewritten=None,
                        evidence_status=status,
                    )
                )
            else:
                soft = _soften_locally(c.text, c.claim_type)
                decisions.append(
                    ClaimDecision(
                        claim_id=c.claim_id,
                        action="soften",
                        reason="unknown_medium_soften",
                        original=c.text,
                        rewritten=soft,
                        evidence_status=status,
                    )
                )
    return decisions


def _soften_locally(text: str, claim_type: str) -> str:
    t = text
    replacements = [
        (r"\btax-free\b", "through a charitable foundation structure"),
        (r"\btax free\b", "through a charitable foundation structure"),
        (r"\bchannels billions\b", "channels significant profits"),
        (r"\bbillions\b", "large reserves"),
        (r"\bowns 100%\s+privately\b", "owns the company privately"),
        (r"\bowns 100%\b", "owns"),
        (r"\bholds 100%\s+control\b", "owns the company"),
        (r"\b100%\s+control\b", "private ownership"),
        (r"\bholds 100%\b", "owns"),
        (r"\b100%\b", "full ownership"),
        (r"\bhas no shareholders\b", "has no public shareholders"),
        (r"\bno shareholders?\b", "no public shareholders"),
        (r"\bzero shareholders?\b", "no public shareholders"),
        (r"\bzero public equity\b", "no public equity listing"),
        (r"^zero\.?$", ""),
        (r"\bzero\.?\b", ""),
        (r"\bnot one\.?\b", ""),
        (r"\bholds total control\b", "owns the company"),
        (r"\btotal control\b", "private ownership"),
        (r"\babsolute sovereignty\b", "unusual independence"),
        (r"\bno board meetings\.?\b", ""),
        (r"\bno external audits\.?\b", ""),
        (r"\bcomplete operational opacity\.?\b", ""),
        (r"\bno public filings\.?\b", ""),
        (r"\bno quarterly earnings\.?\b", ""),
        (r"\bjust absolute,?\s*silent dominance\.?\b", ""),
        (r"\bsilent dominance\.?\b", ""),
        (r"\bcontrols? the entire(?: global)?(?: luxury)? market\b", "is a major force in luxury watches"),
        (r"\bentire market\b", "luxury watch market"),
        (r"\bquietly\b", ""),
        (r"\blocked\b", "transferred"),
    ]
    for pat, rep in replacements:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t).strip(" .,;")
    if not t:
        return ""
    if not t.endswith((".", "!", "?")):
        t += "."
    return t


def apply_decisions_to_script(raw: str, decisions: list[ClaimDecision]) -> str:
    """Apply keep/soften/remove at sentence level; preserve order."""
    text = " ".join((raw or "").split())
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    by_orig = {d.original.strip(): d for d in decisions}
    out: list[str] = []
    for s in sentences:
        d = by_orig.get(s)
        if not d:
            # fuzzy: match by start
            d = next((x for x in decisions if x.original.strip() == s), None)
        if not d:
            out.append(s)
            continue
        if d.action == "remove":
            continue
        if d.action in {"soften", "replace"}:
            if d.rewritten and d.rewritten.strip():
                out.append(d.rewritten.strip())
            continue
        out.append(s)
    result = " ".join(out)
    result = re.sub(r"\s{2,}", " ", result).strip()
    return result


_EDITOR_SYSTEM = (
    "You are a short-form documentary script editor. "
    "Return ONLY valid JSON with keys: final_script, hook, loop_strategy, notes. "
    "Rules: natural spoken English; short complete sentences; no essay style; "
    "do NOT invent new facts, numbers, tax claims, ownership percentages, or scandals; "
    "do NOT strengthen claims beyond the allowed facts provided; "
    "prefer a clear ending over a forced incomplete loop; "
    "keep approximately the same length (do not pad)."
)


def batch_quality_edit(
    draft: str,
    *,
    topic: str,
    allowed_facts: list[str],
    banned_strengthen: list[str],
    target_words: int,
) -> tuple[str, str, str, int]:
    """Single LLM batch edit. Returns (script, hook, loop_strategy, llm_calls)."""
    if not draft.strip():
        return draft, "", "none", 0
    from app.script_gen import OPENROUTER_URL, MODEL as SCRIPT_MODEL

    api_url = OPENROUTER_URL
    model = getattr(config, "OPENROUTER_MODEL", "") or SCRIPT_MODEL or "gemini-flash"
    timeout = int(getattr(config, "LLM_TIMEOUT", 60) or 60)

    payload = {
        "model": model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": _EDITOR_SYSTEM},
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "topic": topic,
                        "draft_script": draft,
                        "allowed_facts": allowed_facts[:20],
                        "do_not_strengthen_beyond": banned_strengthen[:20],
                        "target_word_count": target_words,
                        "style": "spoken_short_form_documentary",
                        "response_shape": {
                            "final_script": "string",
                            "hook": "string",
                            "loop_strategy": "string",
                            "notes": "string",
                        },
                    }
                ),
            },
        ],
    }
    headers = {}
    api_key = getattr(config, "OPENROUTER_API_KEY", "") or ""
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        r = session.post(api_url, json=payload, headers=headers or None, timeout=timeout)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        if isinstance(content, str):
            content = content.strip()
            if content.startswith("```"):
                content = re.sub(r"^```(?:json)?\s*", "", content)
                content = re.sub(r"\s*```$", "", content)
            data = json.loads(content)
        else:
            data = content
        final = str(data.get("final_script") or draft).strip()
        hook = str(data.get("hook") or "").strip()
        loop = str(data.get("loop_strategy") or "optional_seamless").strip()
        # Claim-discipline: reject editor output that reintroduces banned strengthens
        if _editor_strengthened(final, banned_strengthen, draft):
            logger.warning("editor strengthened claims — falling back to draft")
            final = draft
        final = _local_repair(final)
        return final, hook or (final.split(".")[0] + "."), loop, 1
    except Exception as exc:
        logger.warning("quality editor LLM failed: %s", exc)
        repaired = _local_repair(draft)
        hook = repaired.split(".")[0].strip() + "." if repaired else ""
        return repaired, hook, "optional_seamless", 0

def _editor_strengthened(final: str, banned: list[str], draft: str) -> bool:
    fl = final.lower()
    dl = draft.lower()
    strength_markers = (
        "tax-free",
        "tax free",
        "entire market",
        "entire global",
        "100%",
        "billions",
        "no shareholders",
        "zero shareholders",
        "controls the entire",
    )
    for m in strength_markers:
        if m in fl and m not in dl:
            return True
    for b in banned:
        bl = (b or "").lower().strip()
        if len(bl) < 8:
            continue
        if bl in fl and bl not in dl:
            return True
    return False


def _local_repair(script: str) -> str:
    """Fix obvious fragment issues without LLM."""
    text = " ".join((script or "").split())
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    fixed: list[str] = []
    for s in sentences:
        issues = linguistic_quality_issues(s)
        if any(i.startswith(("incomplete_clause", "missing_verb", "missing_subject")) for i in issues):
            # Drop irreparable fragments rather than publish them
            continue
        if any(i.startswith("noun_stacking") for i in issues):
            s = re.sub(
                r"real estate amateurs build",
                "amateurs chase real estate flips",
                s,
                flags=re.I,
            )
            s = re.sub(
                r"companies for fast cash elites",
                "companies built for short-term cash",
                s,
                flags=re.I,
            )
        if not s.endswith((".", "!", "?")):
            s += "."
        fixed.append(s)
    return " ".join(fixed).strip()


def _strip_residual_absolutes(script: str) -> str:
    """Fail-closed polish: never leave tax-free / 100% / entire-market in final."""
    t = script or ""
    kills = [
        (r"\btax-free\b", "foundation-structured"),
        (r"\bone hundred percent\b", "fully"),
        (r"\bhundred percent\b", "fully"),
        (r"\b100%\b", ""),
        (r"\bentire(?:\s+global)?(?:\s+luxury)?\s+market\b", "luxury watch market"),
        (r"\bchannels billions\b", "channels profits"),
        (r"\bbillions\b", "reserves"),
        (r"\bno shareholders\b", "no public shareholders"),
        (r"\babsolute ownership\b", "private ownership"),
        (r"\btotal control\b", "private ownership"),
        (r"\bowns it all\b", "owns the company"),
        (r"\bno dilution\.?\b", "Private ownership stays concentrated."),
    ]
    for pat, rep in kills:
        t = re.sub(pat, rep, t, flags=re.I)
    t = re.sub(r"\s{2,}", " ", t)
    t = re.sub(r"\s+\.", ".", t)
    return t.strip()


def enforce_length(script: str, *, target_sec: float | None = None) -> str:
    lo, hi = _TARGET_DURATION_SEC
    target = target_sec if target_sec is not None else (lo + hi) / 2.0
    words = script.split()
    max_words = max(40, int(target / 60.0 * _DEFAULT_WPM * 1.15))
    min_words = max(25, int(lo / 60.0 * _DEFAULT_WPM * 0.85))
    if len(words) > max_words:
        # Trim whole sentences from the end (keep hook)
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", script) if s.strip()]
        kept: list[str] = []
        count = 0
        for s in sentences:
            w = len(s.split())
            if kept and count + w > max_words:
                break
            kept.append(s)
            count += w
        script = " ".join(kept)
    # Don't pad if short — short is fine within band
    _ = min_words
    return script.strip()


def narrative_purpose(text: str) -> str:
    low = (text or "").lower()
    if re.search(r"\b(founder|founded|born|established)\b", low):
        return "history"
    if re.search(r"\b(own|ownership|foundation|trust|shareholder|ipo)\b", low):
        return "ownership"
    if re.search(r"\b(billion|million|revenue|profit|tax)\b", low):
        return "scale"
    if re.search(r"\b(secret|quietly|nobody|hidden)\b", low):
        return "mystery"
    if re.search(r"\b(swiss|geneva|zurich)\b", low):
        return "location"
    if "?" in (text or ""):
        return "payoff"
    return "contrast"


def rebuild_draft_with_replacements(
    draft: str,
    replacements: list[dict],
    *,
    min_words: int,
) -> str:
    """Append evidence-backed replacement sentences until length floor (no fabrication)."""
    text = " ".join((draft or "").split()).strip()
    words = text.split()
    if len(words) >= min_words or not replacements:
        return text
    used = set(text.lower().split())
    extras: list[str] = []
    for fact in replacements:
        sent = str(fact.get("text") or "").strip()
        if not sent:
            continue
        # Skip near-duplicates
        key = sent.lower()[:40]
        if key in text.lower() or any(key in e.lower() for e in extras):
            continue
        # Soften residual absolutes in replacement text too
        sent = _strip_residual_absolutes(sent)
        if not sent or len(sent.split()) < 5:
            continue
        extras.append(sent)
        words = (text + " " + " ".join(extras)).split()
        if len(words) >= min_words:
            break
    if not extras:
        return text
    # Prefer HOOK-ish structure: keep draft then verified evidence then leave rhetorical if present
    parts = [text] if text else []
    parts.extend(extras)
    out = " ".join(p for p in parts if p).strip()
    _ = used
    return out


def refine_script(
    raw_script: str,
    *,
    topic: str = "",
    verifier: FactVerificationProvider | None = None,
    skip_llm_edit: bool = False,
) -> ScriptQualityResult:
    """Full pipeline: extract → verify → decide → replace research → edit → guards."""
    raw = " ".join((raw_script or "").split())
    claims = extract_claims(raw, topic=topic)
    verifier = verifier or FactVerificationProvider()
    outage = False
    verifications: list[VerificationResult] = []
    search_calls = 0
    try:
        verifications = verifier.verify_claims(claims, topic=topic)
        search_calls = sum(1 for c in claims if c.verification_required)
    except Exception as exc:
        logger.error("verification provider outage: %s", exc)
        outage = True
        verifications = [
            VerificationResult(claim_id=c.claim_id, status="unknown", notes="outage")
            for c in claims
        ]

    high_unknown = [
        c
        for c in claims
        if c.risk == "HIGH"
        and c.verification_required
        and any(
            v.claim_id == c.claim_id and v.status == "unknown" and not v.sources
            for v in verifications
        )
    ]
    if high_unknown and all(
        not v.sources for v in verifications if v.claim_id in {c.claim_id for c in high_unknown}
    ):
        outage = outage or any(
            "verification_error" in (v.notes or "") or v.notes == "no_evidence_fetched"
            for v in verifications
            if any(c.claim_id == v.claim_id and c.risk == "HIGH" for c in claims)
        )

    decisions = decide_claims(claims, verifications, outage=outage)
    draft = apply_decisions_to_script(raw, decisions)
    # Drop incomplete fragments early so we measure real story mass
    draft = _local_repair(draft)

    rejected = [
        {
            "text": d.original,
            "reason": d.reason,
            "purpose": narrative_purpose(d.original),
            "evidence_status": d.evidence_status,
        }
        for d in decisions
        if d.action == "remove"
    ]

    # Replacement research when story collapsed or important claims removed
    from app.story_domains import (
        build_replacement_intent,
        evaluate_story_consistency,
    )

    lo, hi = _TARGET_DURATION_SEC
    min_words = max(40, int(lo / 60.0 * _DEFAULT_WPM * 0.9))
    target_words = max(min_words, int(((lo + hi) / 2) / 60.0 * _DEFAULT_WPM))
    replacement_research: list[dict] = []
    replacement_intents: list[dict] = []
    researched = False
    # Always attempt replacement research when draft is thin OR claims removed
    if rejected or len(draft.split()) < min_words:
        intents = [
            build_replacement_intent(
                claim_id=f"rej_{i}",
                text=str(r.get("text") or ""),
                topic=topic,
            )
            for i, r in enumerate(rejected)
        ]
        if not intents:
            intents = [
                build_replacement_intent(
                    claim_id="topic",
                    text=topic or draft[:200],
                    topic=topic,
                )
            ]
        replacement_intents = [it.to_dict() for it in intents]
        purposes = list(
            {
                narrative_purpose(r["text"])
                for r in rejected
            }
            | {it.desired_story_function for it in intents}
            | {it.semantic_domain for it in intents}
        )
        try:
            replacement_research = verifier.research_replacement_facts(
                topic,
                purposes=purposes,
                max_facts=6,
                banned_markers=[r["text"] for r in rejected],
                intents=intents,
            )
            # Drop any residual domain-mismatched facts (defense in depth)
            replacement_research = [
                f
                for f in replacement_research
                if float(f.get("domain_match_score") or 0) >= 0.5
            ]
            researched = True
            search_calls += 1
        except Exception as exc:
            logger.warning("replacement research failed: %s", exc)
            researched = True  # attempt happened
        if replacement_research:
            draft = rebuild_draft_with_replacements(
                draft, replacement_research, min_words=min_words
            )
            # Mark replace decisions for trace
            for fact in replacement_research:
                decisions.append(
                    ClaimDecision(
                        claim_id=f"repl_{len(decisions)}",
                        action="replace",
                        reason=f"evidence_backed_{fact.get('purpose')}_domain_{fact.get('intent_domain')}",
                        original="",
                        rewritten=str(fact.get("text") or ""),
                        evidence_status="supported",
                    )
                )

    allowed = [
        d.rewritten or d.original
        for d in decisions
        if d.action in {"keep", "soften", "replace"} and (d.rewritten or d.original)
    ]
    banned = [d.original for d in decisions if d.action == "remove" and d.original]

    llm_calls = 0
    hook = ""
    loop = "optional_seamless"
    if skip_llm_edit:
        final = _local_repair(draft)
        hook = (final.split(".")[0] + ".") if final else ""
    else:
        final, hook, loop, llm_calls = batch_quality_edit(
            draft,
            topic=topic,
            allowed_facts=allowed,
            banned_strengthen=banned,
            target_words=target_words,
        )

    final = enforce_length(final)
    # If still thin after edit, re-inject verified replacements (no invention)
    if len(final.split()) < min_words and replacement_research:
        final = rebuild_draft_with_replacements(
            final, replacement_research, min_words=min_words
        )
        final = _local_repair(final)
    final = _strip_residual_absolutes(final)
    issues = linguistic_quality_issues(final)
    if issues:
        final = _local_repair(final)
        issues = linguistic_quality_issues(final)

    if loop and "force" in loop.lower():
        loop = "optional_seamless"
    if final and not final.endswith((".", "!", "?")):
        final = final.rstrip(",;:") + "."
        loop = "clean_ending"

    review_required = outage and any(
        c.risk == "HIGH" and c.verification_required for c in claims
    )
    if len(final.split()) < min_words and researched and not replacement_research:
        review_required = True

    # Story quality soft check
    story_flags: list[str] = []
    if len(final.split()) < min_words:
        story_flags.append("below_target_duration")
    if not any(c.claim_type != "opinion_rhetorical" for c in claims if c.text in final):
        # at least one factual-ish sentence present via replacements
        if not replacement_research:
            story_flags.append("weak_factual_spine")
    if "?" not in final and len(final.split(".")) < 3:
        story_flags.append("thin_arc")

    consistency = evaluate_story_consistency(
        topic=topic,
        raw_script=raw,
        final_script=final,
        replacement_research=replacement_research,
    )
    if consistency.status == "FAIL":
        review_required = True
        story_flags.append("semantic_domain_drift")
        # Strip drifted manufacturing/product sentences from final when topic is ownership
        from app.story_domains import infer_semantic_domain

        topic_dom = infer_semantic_domain(topic + " " + raw[:200], topic=topic)
        if topic_dom in {
            "ownership",
            "governance",
            "corporate_structure",
            "founder_history",
            "finance",
            "legal",
        }:
            kept_sents = []
            for sent in re.split(r"(?<=[.!?])\s+", final):
                s = sent.strip()
                if not s:
                    continue
                d = infer_semantic_domain(s, topic=topic)
                if d in {"manufacturing", "product"} and "foundation" not in s.lower():
                    continue
                # Hard lexical ban regardless of domain classifier
                if re.search(
                    r"\b(daytona|cosmograph|self-winding|hand-wound|series introduced|"
                    r"in-house to Rolex|four distinct generations)\b",
                    s,
                    re.I,
                ):
                    continue
                kept_sents.append(s)
            if kept_sents:
                final = " ".join(kept_sents)
                if not final.endswith((".", "!", "?")):
                    final = final.rstrip(",;:") + "."
            # Re-inject domain-locked replacements if strip emptied the spine
            safe_facts = [
                f
                for f in replacement_research
                if float(f.get("domain_match_score") or 0) >= 0.5
                and infer_semantic_domain(str(f.get("text") or ""))
                not in {"manufacturing", "product"}
            ]
            if len(final.split()) < min_words and safe_facts:
                final = rebuild_draft_with_replacements(
                    final, safe_facts, min_words=min_words
                )
                final = _local_repair(final)
            # Re-check after strip + reinject
            consistency = evaluate_story_consistency(
                topic=topic,
                raw_script=raw,
                final_script=final,
                replacement_research=safe_facts or replacement_research,
            )
            if consistency.status == "PASS":
                story_flags = [f for f in story_flags if f != "semantic_domain_drift"]
                # Clear drift-only review; keep outage / high-risk review
                review_required = bool(
                    outage
                    and any(c.risk == "HIGH" and c.verification_required for c in claims)
                ) or (len(final.split()) < min_words and researched and not safe_facts)
            else:
                review_required = True

    v_summary = {
        "total_claims": len(claims),
        "verification_required": sum(1 for c in claims if c.verification_required),
        "by_status": _count_status(verifications),
        "outage": outage,
        "decisions": _count_actions(decisions),
        "replacement_facts": len(replacement_research),
        "research_attempted": researched,
        "story_consistency": consistency.status,
    }

    return ScriptQualityResult(
        raw_script=raw,
        final_script=final,
        claims=[c.to_dict() for c in claims],
        verification_summary=v_summary,
        claim_decisions=[d.to_dict() for d in decisions],
        quality_checks={
            "linguistic_issues": issues,
            "estimated_words": len(final.split()),
            "hook": hook,
            "loop_strategy": loop,
            "story_flags": story_flags,
            "min_words_target": min_words,
            "story_consistency": consistency.to_dict(),
        },
        estimated_duration=estimate_duration_sec(final),
        hook=hook,
        loop_strategy=loop,
        llm_calls=llm_calls,
        search_calls=search_calls,
        verification_outage=outage,
        review_required=review_required,
        replacement_research=replacement_research,
        rejected_claims=rejected,
        replacement_intents=replacement_intents,
        story_consistency=consistency.to_dict(),
    )


def _count_status(vs: list[VerificationResult]) -> dict[str, int]:
    out: dict[str, int] = {}
    for v in vs:
        out[v.status] = out.get(v.status, 0) + 1
    return out


def _count_actions(ds: list[ClaimDecision]) -> dict[str, int]:
    out: dict[str, int] = {}
    for d in ds:
        out[d.action] = out.get(d.action, 0) + 1
    return out


def merge_into_script_dict(script: dict[str, Any], quality: ScriptQualityResult) -> dict[str, Any]:
    """Update existing script payload for TTS/downstream compatibility."""
    out = dict(script or {})
    out["script"] = quality.final_script
    out["raw_script"] = quality.raw_script
    out["final_script"] = quality.final_script
    out["hook"] = quality.hook or out.get("hook") or ""
    # Keep title/description/tags from original generation
    out["script_quality"] = quality.to_dict()
    out["estimated_duration"] = quality.estimated_duration
    out["loop_strategy"] = quality.loop_strategy
    if quality.review_required:
        out["review_required"] = True
        out["review_reason"] = "script_verification_outage_or_high_risk_unknown"
    return out
