"""Claim extraction + risk classification for short-form documentary scripts."""
from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|(?<=;)\s+")
_NUMBER_RE = re.compile(
    r"\$[\d,.]+|\b\d+(?:\.\d+)?\s*%|\b\d{4}\b|\b\d+(?:\.\d+)?\s*"
    r"(?:billion|million|trillion|percent)\b|\b100%\b|\bzero\b",
    re.I,
)
_ABSOLUTE_RE = re.compile(
    r"\b(never|always|all|none|every|entire|completely|totally|"
    r"no\s+shareholders?|zero\s+shareholders?|100%|entire\s+market|"
    r"not\s+one|zero\s+public|total\s+control|absolute\s+sovereignty|"
    r"no\s+board|no\s+external|operational\s+opacity|"
    r"no\s+public\s+filings?|no\s+quarterly|silent\s+dominance|"
    r"^zero\.?$)\b",
    re.I,
)
_TAX_LEGAL_RE = re.compile(
    r"\b(tax[- ]?free|tax[- ]?exempt|taxes?|legal|lawsuit|illegal|"
    r"exemption|charter|nonprofit|non[- ]profit|audit|audits)\b",
    re.I,
)
_OWNERSHIP_RE = re.compile(
    r"\b(own(?:s|ed|ership)?|shareholders?|shares?|foundation|trust|"
    r"locked|transferred|controls?|controlling|equity|sovereignty)\b",
    re.I,
)
_FINANCE_RE = re.compile(
    r"\b(billion|million|revenue|profit|reserves?|wealth|channels?)\b",
    re.I,
)
_BIO_RE = re.compile(
    r"\b(founded|founder|born|died|invented|created|transferred)\b",
    re.I,
)
_HISTORY_RE = re.compile(r"\b(in\s+\d{4}|since\s+\d{4}|by\s+\d{4}|\d{4})\b", re.I)
_RHETORICAL_RE = re.compile(
    r"\b(amateurs?\s+(?:think|build)|elites?\s+|real\s+power|"
    r"quietly\.|watch\s+this|here's\s+why)\b",
    re.I,
)
_PROPER_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\b")


CLAIM_TYPES = (
    "historical",
    "ownership",
    "financial",
    "legal",
    "tax",
    "corporate",
    "biographical",
    "numerical",
    "geographical",
    "product",
    "opinion_rhetorical",
)


@dataclass
class ScriptClaim:
    claim_id: str
    text: str
    claim_type: str
    entities: list[str] = field(default_factory=list)
    importance: str = "medium"  # low|medium|high
    risk: str = "LOW"  # LOW|MEDIUM|HIGH
    verification_required: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def extract_claims(script: str, *, topic: str = "") -> list[ScriptClaim]:
    """Split narration into factual vs rhetorical claims (heuristic, no LLM)."""
    text = " ".join((script or "").split())
    if not text:
        return []
    parts = [p.strip() for p in _SENTENCE_SPLIT.split(text) if p and p.strip()]
    if not parts:
        parts = [text]

    claims: list[ScriptClaim] = []
    for i, sent in enumerate(parts):
        ctype, risk, importance, need_v = classify_sentence(sent, topic=topic)
        ents = _entities_in(sent, topic=topic)
        cid = hashlib.sha1(f"{i}:{sent}".encode()).hexdigest()[:10]
        claims.append(
            ScriptClaim(
                claim_id=cid,
                text=sent,
                claim_type=ctype,
                entities=ents,
                importance=importance,
                risk=risk,
                verification_required=need_v,
            )
        )
    return claims


def classify_sentence(sent: str, *, topic: str = "") -> tuple[str, str, str, bool]:
    """Return (claim_type, risk, importance, verification_required)."""
    s = sent or ""
    low = s.lower()

    # Ownership / tax / numbers always win over rhetoric heuristics
    has_ownership = bool(_OWNERSHIP_RE.search(s))
    has_tax_legal = bool(_TAX_LEGAL_RE.search(s))
    has_number = bool(_NUMBER_RE.search(s))
    has_absolute = bool(_ABSOLUTE_RE.search(s))

    # Pure rhetorical / editorial → skip verification only if no factual markers
    if _RHETORICAL_RE.search(s) and not (has_number or has_tax_legal or has_ownership or has_absolute):
        return "opinion_rhetorical", "LOW", "low", False

    # Short aphorism without factual markers
    words = s.split()
    if (
        len(words) <= 6
        and not has_number
        and not has_ownership
        and not has_tax_legal
        and not has_absolute
    ):
        if not any(c.isupper() for c in s[1:]):
            return "opinion_rhetorical", "LOW", "low", False

    ctype = "corporate"
    if has_tax_legal and "tax" in low:
        ctype = "tax"
    elif has_tax_legal:
        ctype = "legal"
    elif has_ownership:
        ctype = "ownership"
    elif has_number or _FINANCE_RE.search(s):
        ctype = "financial" if _FINANCE_RE.search(s) else "numerical"
    elif _BIO_RE.search(s) and _PROPER_RE.search(s):
        ctype = "biographical"
    elif _HISTORY_RE.search(s):
        ctype = "historical"
    elif re.search(r"\b(swiss|geneva|zurich|switzerland)\b", low):
        ctype = "geographical"
    elif re.search(r"\b(watch|product|brand)\b", low):
        ctype = "product"
    elif has_absolute and len(words) <= 8:
        # Absolute fragments like "Not one." / "No board meetings."
        ctype = "corporate"

    risk = "LOW"
    if ctype in {"tax", "legal"} or has_tax_legal:
        risk = "HIGH"
    elif has_number or has_absolute:
        risk = "HIGH"
    elif ctype in {"ownership", "financial", "biographical", "historical", "corporate"}:
        risk = "HIGH" if has_absolute or has_number else "MEDIUM"
    elif ctype == "opinion_rhetorical":
        risk = "LOW"

    importance = "high" if risk == "HIGH" else ("medium" if risk == "MEDIUM" else "low")
    need_v = risk in {"HIGH", "MEDIUM"} and ctype != "opinion_rhetorical"
    # Absolute corporate fragments always need verification
    if has_absolute and ctype != "opinion_rhetorical":
        need_v = True
        if risk == "LOW":
            risk = "HIGH"
            importance = "high"
    return ctype, risk, importance, need_v


def _entities_in(sent: str, *, topic: str = "") -> list[str]:
    stop = {
        "the", "this", "that", "when", "who", "what", "not", "zero", "just",
        "can", "role", "founder", "owner", "company", "brand", "complete",
        "absolute", "amateurs", "elites",
    }
    found = [m.group(1) for m in _PROPER_RE.finditer(sent or "")]
    topic_bits = [w for w in (topic or "").split() if w[:1].isupper()]
    for b in topic_bits[:2]:
        if b.lower() in (sent or "").lower() and b not in found:
            found.append(b)
    out: list[str] = []
    for e in found:
        if e.lower() in stop:
            continue
        if e.lower() not in {x.lower() for x in out}:
            out.append(e)
    return out[:6]
