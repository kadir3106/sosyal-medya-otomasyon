import json
import math
import random
import re
import subprocess
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.config import config
from app.http_client import session

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PIXABAY_SEARCH_URL = "https://pixabay.com/api/videos/"
MIXKIT_SEARCH_URL = "https://mixkit.co/free-stock-video/{slug}/"
PEXELS_PER_PAGE = 15
PIXABAY_PER_PAGE = 15
USED_CLIP_HISTORY_LIMIT = 200
_MIXKIT_UA = {"User-Agent": "sosyal-medya-otomasyon/1.0 (+stock-fallback)"}
_MIXKIT_MP4_RE = re.compile(
    r"https://(?:assets|cdn)\.mixkit\.co/videos/[^\s\"'<>]+\.mp4",
    re.IGNORECASE,
)

# Pexels API key yokken kullanılan Pillow tabanlı animasyonlu arka plan ayarları.
FALLBACK_FPS = 12
FALLBACK_DURATION_SECONDS = 4
FALLBACK_SIZE = (1080, 1920)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
    "and", "or", "but", "for", "with", "at", "by", "it", "this", "that",
    "their", "its", "as", "from", "than", "so", "we", "they", "you",
    # Bu yalnızca script_gen'in visual_keywords alanını atladığı nadir
    # durumlarda devreye giren bir yedek yol (bkz. pipeline.py) — asıl çözüm
    # LLM'in HER ZAMAN İngilizce visual_keywords üretmesi. Yine de Türkçe
    # script'ten çıkarım yapılırsa en azından bariz dolgu kelimeler elensin.
    "bir", "bu", "şu", "ile", "gibi", "için", "kadar", "daha", "çok", "ama",
    "veya", "her", "hem", "ne", "de", "da", "ki", "mi", "mı", "mu", "mü",
    "olan", "olarak", "olduğu", "sonra", "önce", "değil", "diye", "ise",
}

# Generic wealth / cinematic fluff — alone these pull unrelated Pexels B-roll
# (city lights, handshake, yacht) that have zero link to a concrete topic.
_GENERIC_STOCK_TERMS = {
    "luxury", "business", "money", "wealth", "success", "rich", "power",
    "cinematic", "dramatic", "photorealistic", "vertical", "camera",
    "dolly", "zoom", "angle", "lighting", "detail", "unreal", "engine",
    "8k", "shot", "footage", "moody", "dark", "golden", "premium",
    "lifestyle", "motivation", "nature", "abstract", "background",
}

_PROMPT_NOISE = _GENERIC_STOCK_TERMS | {
    "close-up", "closeup", "macro", "wide", "establishing", "slow",
    "push", "tracking", "overhead", "profile", "rear", "medium",
}

# Domain expanders — map sentence intent → Pexels-friendly concrete nouns.
_MODE_QUERY_SEEDS: dict[str, tuple[str, ...]] = {
    "watchmaking": (
        "luxury watchmaker magnifying glass",
        "mechanical watch gears close up",
        "swiss watch assembly bench",
    ),
    "finance_docs": (
        "signing legal contract documents",
        "notary stamp corporate papers",
        "legal documents on desk",
    ),
    "vault": (
        "swiss bank vault door",
        "secure private vault interior",
        "luxury safe deposit box",
    ),
    "chart": (
        "stock market chart on screen",
        "financial graph trading monitor",
        "equity candlestick chart display",
    ),
    "boardroom": (
        "corporate boardroom mahogany table",
        "executive meeting glass office",
        "empty luxury boardroom interior",
    ),
    "diamond": (
        "diamond engagement ring price tag",
        "loose rough diamond vs polished gem",
        "diamond vault security trays",
    ),
}

_MODE_TRIGGERS: dict[str, tuple[str, ...]] = {
    "watchmaking": (
        "watch", "watchmaker", "rolex", "crown", "gear", "loupe", "submariner",
        "daytona", "horolog", "craft", "mechanism", "dial", "bezel",
    ),
    "finance_docs": (
        "trust", "foundation", "shareholder", "ownership", "legal", "document",
        "contract", "paper", "deed", "notary", "charter", "statute", "tax",
    ),
    "vault": ("vault", "safe", "bank", "geneva", "swiss", "deposit", "strongroom"),
    "chart": (
        "stock", "share", "equity", "chart", "graph", "market", "trading",
        "ticker", "ipo", "dividend",
    ),
    "boardroom": ("board", "boardroom", "director", "executive", "meeting", "office"),
    "diamond": (
        "diamond", "debeers", "de beers", "engagement", "ring", "gem", "cartel",
        "kimberley", "brilliant", "carat",
    ),
}

# Reject B-roll whose URL/title smells like unrelated stock when we need craft/finance.
_IRRELEVANT_SLUG_TOKENS = frozenset({
    "construction", "excavator", "bulldozer", "building-site", "construction-site",
    "concrete-mixer", "crane", "scaffold", "worker-helmet", "hard-hat",
    "busy-street", "traffic-jam", "pedestrian-crowd", "shopping-mall",
    "gym", "workout", "beach", "surf", "cooking", "kitchen-food",
    "football", "soccer", "basketball", "party-crowd", "concert",
})

_MIN_VIDEO_LONG_EDGE = 720
_VALID_MODES = frozenset(_MODE_QUERY_SEEDS.keys()) | {"generic", "diamond"}

# Particles that look like stopwords but belong in brand names (De Beers, Van Cleef).
_NAME_PARTICLES = frozenset({
    "de", "van", "von", "la", "le", "di", "da", "del", "der", "du", "st", "mc", "mac",
})
_TITLE_NOISE = frozenset({
    "the", "how", "why", "what", "when", "where", "who", "a", "an", "and", "or",
    "for", "with", "from", "into", "that", "this", "these", "those",
})
_PARTICLE_BRAND_RE = re.compile(
    r"\b((?:De|Van|Von|La|Le|Di|Del|Du|Mc|Mac|St)\s+[A-Z][A-Za-z]+)\b"
)
_CAP_WORD_RE = re.compile(r"\b([A-Z][A-Za-z]{2,})\b")


def extract_proper_phrases(text: str) -> list[str]:
    """Keep multi-word brands intact (De Beers, Hans Wilsdorf, Van Cleef)."""
    if not text:
        return []
    found: list[str] = []
    # Particle brands first so "The De Beers" never becomes "The De".
    for match in _PARTICLE_BRAND_RE.finditer(text):
        phrase = match.group(1).strip()
        if phrase.lower() not in {f.lower() for f in found}:
            found.append(phrase)
    for match in _CAP_WORD_RE.finditer(text):
        word = match.group(1).strip()
        low = word.lower()
        if low in _TITLE_NOISE or low in _STOPWORDS or low in _GENERIC_STOCK_TERMS:
            continue
        # Skip second half of an already-captured brand ("Beers" after "De Beers")
        if any(low == f.lower().split()[-1] and len(f.split()) > 1 for f in found):
            continue
        if low not in {f.lower() for f in found}:
            found.append(word)
    return found


def extract_keywords(script: str, max_keywords: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z\u00C0-\u024F]+", script)
    seen = []
    for word in words:
        lower = word.lower()
        if lower in _STOPWORDS or len(lower) < 4:
            continue
        if lower not in seen:
            seen.append(lower)
        if len(seen) >= max_keywords:
            break
    return seen or ["nature"]


def topic_anchor_terms(topic: str, max_terms: int = 4) -> list[str]:
    """Concrete nouns/proper names from the topic (e.g. De Beers, Rolex, Swiss)."""
    if not topic:
        return []
    anchors: list[str] = []
    # Brands first — never split "De Beers" into stopword "de" + "Beers".
    for phrase in extract_proper_phrases(topic):
        if phrase.lower() not in {a.lower() for a in anchors}:
            anchors.append(phrase)
        if len(anchors) >= max_terms:
            return anchors[:max_terms]

    words = re.findall(r"[A-Za-z\u00C0-\u024F]+", topic)
    i = 0
    while i < len(words) and len(anchors) < max_terms:
        word = words[i]
        lower = word.lower()
        # Particle + Capital → keep as one brand token
        if (
            lower in _NAME_PARTICLES
            and i + 1 < len(words)
            and words[i + 1][:1].isupper()
        ):
            brand = f"{word} {words[i + 1]}"
            if brand.lower() not in {a.lower() for a in anchors}:
                anchors.append(brand)
            i += 2
            continue
        if lower in _STOPWORDS or lower in _GENERIC_STOCK_TERMS or lower in _TITLE_NOISE:
            i += 1
            continue
        if len(lower) < 3 and not word[:1].isupper():
            i += 1
            continue
        # Skip second half of an already-captured brand ("Beers" after "De Beers")
        covered = any(
            lower == a.lower().split()[-1] and len(a.split()) > 1 for a in anchors
        )
        if covered:
            i += 1
            continue
        token = lower if word.islower() else word
        if token.lower() not in {a.lower() for a in anchors}:
            anchors.append(token)
        i += 1
    return anchors[:max_terms]


def prompt_concrete_terms(prompt: str, max_terms: int = 3) -> list[str]:
    """Strip cinematic fluff; keep subject nouns for Pexels search."""
    if not prompt:
        return []
    # Prefer intact brands inside the prompt.
    kept: list[str] = []
    for phrase in extract_proper_phrases(prompt):
        if phrase.lower() not in {k.lower() for k in kept}:
            kept.append(phrase)
        if len(kept) >= max_terms:
            return kept
    words = [
        w.strip(".,:;'\"()-")
        for w in prompt.replace(",", " ").split()
    ]
    for word in words:
        lower = word.lower()
        if len(lower) < 4 or lower in _PROMPT_NOISE or lower in _STOPWORDS:
            continue
        if any(lower == k.lower().split()[-1] and len(k.split()) > 1 for k in kept):
            continue
        if lower not in {k.lower() for k in kept}:
            kept.append(lower)
        if len(kept) >= max_terms:
            break
    return kept


def detect_visual_mode(text: str) -> str:
    """Pick watchmaking / finance_docs / vault / chart / boardroom from sentence text."""
    low = (text or "").lower()
    if not low:
        return "generic"
    scores: dict[str, int] = {}
    for mode, triggers in _MODE_TRIGGERS.items():
        scores[mode] = sum(1 for t in triggers if t in low)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "generic"


def _split_script_sentences(script: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", (script or "").strip())
    return [p.strip() for p in parts if p.strip()]


def _clean_query_phrase(raw: str, topic: str = "") -> str:
    """Collapse commas/slashes; drop fluff; keep brand phrases (De Beers)."""
    if not raw:
        return ""
    # Protect known brands from the topic + raw text before token filtering.
    protected: list[str] = []
    for phrase in extract_proper_phrases(f"{topic} {raw}"):
        if phrase.lower() not in {p.lower() for p in protected}:
            protected.append(phrase)

    text = raw.replace(",", " ").replace("/", " ").replace("|", " ")
    # Soft-normalize "de beers" → use protected casing when topic has De Beers
    low_text = text.lower()
    for phrase in protected:
        if phrase.lower() in low_text:
            # Mark as already included via protected list
            pass

    words: list[str] = []
    tokens = [w.strip(".,:;'\"()-") for w in text.split()]
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if not token:
            i += 1
            continue
        low = token.lower()
        # Particle + next capital/name → keep as brand
        if (
            low in _NAME_PARTICLES
            and i + 1 < len(tokens)
            and tokens[i + 1]
            and (tokens[i + 1][:1].isupper() or tokens[i + 1].lower() == "beers")
        ):
            brand = f"{token} {tokens[i + 1]}"
            # Prefer canonical casing from protected list
            for p in protected:
                if p.lower() == brand.lower():
                    brand = p
                    break
            if brand.lower() not in {w.lower() for w in words}:
                words.append(brand)
            i += 2
            continue
        if low in _STOPWORDS or low in _GENERIC_STOCK_TERMS:
            i += 1
            continue
        if len(low) < 3 and not token[:1].isupper():
            i += 1
            continue
        # Skip orphan second half of a protected brand already present
        if any(low == p.lower().split()[-1] and len(p.split()) > 1 for p in words + protected):
            # Only skip if the full brand is already in words
            if any(len(w.split()) > 1 and w.lower().endswith(low) for w in words):
                i += 1
                continue
            # Or if we'll inject protected brand later
            if any(p.lower().endswith(low) and len(p.split()) > 1 for p in protected):
                i += 1
                continue
        if low not in {x.lower() for x in words}:
            words.append(token)
        i += 1

    # Ensure at least one protected brand from topic survives
    for p in protected:
        if p.lower() not in {w.lower() for w in words}:
            # Only inject if brand appears in raw or topic-related
            if p.lower() in low_text or p.lower() in (topic or "").lower():
                words.insert(0, p)
                break

    return " ".join(words[:8]).strip()


def enrich_stock_query(query: str, topic: str = "", mode: str = "generic") -> str:
    """Ensure query has concrete nouns; inject domain seeds when thin/generic."""
    mode = mode if mode in _VALID_MODES else detect_visual_mode(f"{query} {topic}")
    cleaned = _clean_query_phrase(query, topic=topic)
    anchors = topic_anchor_terms(topic, max_terms=2)

    parts: list[str] = []
    # Prefer full brand anchors first (De Beers before diamond…).
    for a in anchors:
        if a.lower() not in {p.lower() for p in parts}:
            parts.append(a)

    if cleaned:
        remaining = cleaned
        for a in anchors:
            remaining = re.sub(re.escape(a), " ", remaining, count=1, flags=re.IGNORECASE)
        for w in remaining.split():
            # Drop orphan "Beers" if "De Beers" already present
            if any(
                len(p.split()) > 1 and w.lower() == p.lower().split()[-1]
                for p in parts
            ):
                continue
            if w.lower() not in {p.lower() for p in parts}:
                parts.append(w)

    meaningful = [p for p in parts if p.lower() not in _GENERIC_STOCK_TERMS]
    if len(meaningful) < 3 and mode in _MODE_QUERY_SEEDS:
        seed = _MODE_QUERY_SEEDS[mode][
            hash(cleaned or topic or mode) % len(_MODE_QUERY_SEEDS[mode])
        ]
        for w in seed.split():
            if w.lower() not in {p.lower() for p in parts}:
                parts.append(w)

    out = " ".join(parts[:8]).strip()
    out = re.sub(r"\b(De Beers)\s+Beers\b", r"\1", out, flags=re.IGNORECASE)
    # Drop orphan Beers / Cleef when full brand already present
    for brand in ("De Beers", "Van Cleef"):
        if brand.lower() in out.lower():
            tail = brand.split()[-1]
            out = re.sub(
                rf"(?<!{re.escape(brand.split()[0].lower())} )\b{re.escape(tail)}\b",
                "",
                out,
                flags=re.IGNORECASE,
            )
            # safer explicit cleanup:
            out = re.sub(rf"\b{re.escape(brand)}\b(?:\s+{re.escape(tail)})+", brand, out, flags=re.IGNORECASE)
            out = re.sub(rf"\b{re.escape(brand)}\b", brand, out, flags=re.IGNORECASE)
            # remove leftover lone tail tokens not preceded by particle
            parts2 = []
            toks = out.split()
            i = 0
            while i < len(toks):
                if (
                    toks[i].lower() == tail.lower()
                    and (i == 0 or toks[i - 1].lower() != brand.split()[0].lower())
                ):
                    i += 1
                    continue
                parts2.append(toks[i])
                i += 1
            out = " ".join(parts2)
    out = re.sub(r"\s+", " ", out).strip()
    if not out or out.lower() in _GENERIC_STOCK_TERMS:
        seed = _MODE_QUERY_SEEDS.get(mode, ("swiss watch craftsmanship",))[0]
        out = _clean_query_phrase(f"{' '.join(anchors)} {seed}".strip(), topic=topic) or seed
    return out


def normalize_scene_stock_queries(
    raw,
    *,
    script: str = "",
    topic: str = "",
    visual_prompts: list | None = None,
    visual_keywords: list | None = None,
    target_count: int | None = None,
) -> list[dict]:
    """Normalize LLM scene_stock_queries → [{query, mode}, ...].

    Derives from script sentences when LLM omits or under-delivers.
    """
    visual_prompts = visual_prompts or []
    visual_keywords = visual_keywords or []
    sentences = _split_script_sentences(script)
    n = target_count or max(len(sentences), len(visual_prompts), 4)

    parsed: list[dict] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str) and item.strip():
                mode = detect_visual_mode(f"{item} {topic}")
                parsed.append(
                    {
                        "query": enrich_stock_query(item, topic=topic, mode=mode),
                        "mode": mode,
                    }
                )
            elif isinstance(item, dict):
                q = (item.get("query") or item.get("q") or "").strip()
                mode = (item.get("mode") or "").strip().lower() or detect_visual_mode(
                    f"{q} {topic}"
                )
                if mode not in _VALID_MODES:
                    mode = detect_visual_mode(f"{q} {topic}")
                if q:
                    parsed.append(
                        {
                            "query": enrich_stock_query(q, topic=topic, mode=mode),
                            "mode": mode,
                        }
                    )

    # Fill / replace thin entries from sentence-aligned derivation.
    derived: list[dict] = []
    for i in range(n):
        sentence = sentences[i] if i < len(sentences) else ""
        prompt = visual_prompts[i] if i < len(visual_prompts) else ""
        hint = visual_keywords[i % len(visual_keywords)] if visual_keywords else ""
        base_text = sentence or prompt or hint or topic
        mode = detect_visual_mode(f"{base_text} {topic}")
        # Prefer concrete nouns from the sentence itself.
        phrase = _clean_query_phrase(sentence) or _clean_query_phrase(prompt) or hint
        derived.append(
            {
                "query": enrich_stock_query(phrase or topic, topic=topic, mode=mode),
                "mode": mode,
            }
        )

    out: list[dict] = []
    for i in range(n):
        if i < len(parsed) and len(parsed[i]["query"].split()) >= 3:
            out.append(parsed[i])
        else:
            out.append(derived[i] if i < len(derived) else derived[-1])
    return out


def resolve_scene_queries(
    *,
    scene_count: int,
    topic: str,
    script: str = "",
    scene_stock_queries: list | None = None,
    visual_prompts: list | None = None,
    visual_keywords: list | None = None,
) -> list[str]:
    """Final per-scene search strings for Pexels/Pixabay/Mixkit."""
    scenes = normalize_scene_stock_queries(
        scene_stock_queries,
        script=script,
        topic=topic,
        visual_prompts=visual_prompts,
        visual_keywords=visual_keywords,
        target_count=scene_count,
    )
    queries: list[str] = []
    for i in range(scene_count):
        sc = scenes[i % len(scenes)]
        # Prefer LLM/enriched query as-is; only lightly re-anchor.
        q = enrich_stock_query(sc["query"], topic=topic, mode=sc.get("mode", "generic"))
        queries.append(q)
    return queries


def build_scene_search_query(
    topic: str,
    prompt: str = "",
    keyword_hint: str | None = None,
    scene_index: int = 0,
    scene_query: str | None = None,
    mode: str | None = None,
) -> str:
    """Per-scene stock query — prefer rich scene_query over stacked topic crumbs."""
    # LLM / resolver already produced a multi-term query → trust + enrich.
    if scene_query and len(_clean_query_phrase(scene_query).split()) >= 3:
        return enrich_stock_query(
            scene_query,
            topic=topic,
            mode=mode or detect_visual_mode(f"{scene_query} {topic}"),
        )

    anchors = topic_anchor_terms(topic)
    concrete = prompt_concrete_terms(prompt)
    hint = (keyword_hint or "").strip()
    hint_l = hint.lower()
    resolved_mode = mode or detect_visual_mode(f"{prompt} {hint} {topic}")

    parts: list[str] = []
    # If hint is already a rich phrase, lead with it.
    if hint and len(_clean_query_phrase(hint).split()) >= 3:
        return enrich_stock_query(hint, topic=topic, mode=resolved_mode)

    if anchors:
        rotated = anchors[scene_index % len(anchors) :] + anchors[: scene_index % len(anchors)]
        parts.extend(rotated[:2])
    for term in concrete:
        if term.lower() not in {p.lower() for p in parts}:
            parts.append(term)
        if len(parts) >= 4:
            break
    if hint and hint_l not in _GENERIC_STOCK_TERMS and hint_l not in {p.lower() for p in parts}:
        parts.append(hint)

    query = " ".join(parts[:5]).strip()
    return enrich_stock_query(query or topic, topic=topic, mode=resolved_mode)


def _query_tokens(query: str) -> set[str]:
    return {
        w.lower()
        for w in re.findall(r"[a-zA-Z]{3,}", query or "")
        if w.lower() not in _STOPWORDS and w.lower() not in _GENERIC_STOCK_TERMS
    }


def _blob_has_irrelevant(blob: str) -> bool:
    low = (blob or "").lower()
    return any(tok in low for tok in _IRRELEVANT_SLUG_TOKENS)


def _score_stock_candidate(blob: str, query: str) -> float:
    """Higher = better topical match; negative = hard reject."""
    if _blob_has_irrelevant(blob) and not any(
        t in blob.lower() for t in ("watch", "rolex", "bank", "vault", "document", "chart")
    ):
        return -10.0
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0
    low = blob.lower()
    hits = sum(1 for t in tokens if t in low)
    return hits / max(len(tokens), 1)


def _pick_quality_video_file(video_files: list) -> dict | None:
    """Prefer portrait HD; accept landscape only if long edge ≥ 720 (croppable)."""
    if not video_files:
        return None
    scored = []
    for f in video_files:
        w = int(f.get("width") or 0)
        h = int(f.get("height") or 0)
        if max(w, h) < _MIN_VIDEO_LONG_EDGE:
            continue
        portrait = 1 if h > w else 0
        scored.append((portrait, h * w, f))
    if not scored:
        return None
    scored.sort(key=lambda x: (x[0], x[1]), reverse=True)
    return scored[0][2]


def _next_keyword(keywords: list[str], index: int) -> str:
    """Sıradaki arama kelimesini döner; aynı kelime asla art arda gelmez.

    Tek keyword'e yapışmak (veya aynı kelimeyi üst üste aramak) görsel
    çeşitliliği öldürüyordu; bu yüzden kelimeler sırayla döner ve tekrar
    durumunda bir sonrakine atlanır.
    """
    if not keywords:
        return "cinematic"
    if len(keywords) == 1:
        return keywords[0]
    position = index % len(keywords)
    if index > 0 and keywords[position] == keywords[(index - 1) % len(keywords)]:
        position = (position + 1) % len(keywords)
    return keywords[position]


def _clip_id(provider: str, raw_id) -> str:
    return f"{provider}:{raw_id}"


def _ids_match_exclude(provider: str, raw_id, exclude_ids: set) -> bool:
    """True if this clip was already used (supports legacy bare Pexels ints)."""
    if raw_id is None:
        return False
    prefixed = _clip_id(provider, raw_id)
    if prefixed in exclude_ids:
        return True
    # Legacy used_clips.json stored bare Pexels numeric ids.
    if provider == "pexels" and (raw_id in exclude_ids or str(raw_id) in exclude_ids):
        return True
    return False


def fetch_stock_clips(
    keywords: list[str],
    count: int,
    api_key: str,
    output_dir: str,
    state_path: str = None,
    start_index: int = 0,
    topic: str = "",
    allow_used_id_reuse: bool = False,
    fallback_on_empty: bool = True,
    meta_out: dict | None = None,
    pixabay_api_key: str = "",
    enable_mixkit: bool | None = None,
) -> list[str]:
    """Stok klip indirir: Pexels → Pixabay → Mixkit.

    `allow_used_id_reuse=False` (default): when every hit is already in
    `used_clips.json`, skip that query instead of silently re-shipping the
    same unrelated wealth stock (root cause of topic-mismatched videos).
    """
    if enable_mixkit is None:
        enable_mixkit = bool(getattr(config, "ENABLE_MIXKIT_STOCK", True))
    pixabay_api_key = pixabay_api_key or str(
        getattr(config, "PIXABAY_API_KEY", "") or ""
    )

    meta = {
        "queries": [],
        "providers": [],
        "scene_relevance": [],
        "fresh_downloads": 0,
        "cache_reuse_downloads": 0,
        "attempts": 0,
    }

    has_any_provider = bool(api_key) or bool(pixabay_api_key) or enable_mixkit
    if not has_any_provider:
        if meta_out is not None:
            meta_out.update(meta)
            meta_out["fallback"] = "no_api_key"
        return _generate_fallback_clips(count, output_dir) if fallback_on_empty else []

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    used_ids = _load_used_clip_ids(state_path) if state_path else set()
    newly_used_ids = []

    downloaded = []
    max_attempts = max(count * 4, 12)
    attempt = 0
    while len(downloaded) < count and attempt < max_attempts:
        raw = _next_keyword(keywords, attempt)
        keyword = (
            build_scene_search_query(topic, prompt=raw, keyword_hint=raw, scene_index=attempt)
            if topic
            else raw
        )
        attempt += 1
        meta["attempts"] = attempt
        meta["queries"].append(keyword)

        exclude = used_ids.union(newly_used_ids)
        hit = _search_stock_waterfall(
            keyword,
            pexels_key=api_key,
            pixabay_key=pixabay_api_key,
            enable_mixkit=enable_mixkit,
            exclude_ids=exclude,
            allow_used_id_reuse=allow_used_id_reuse,
        )
        if hit is None:
            print(
                f"[stock] '{keyword}' — no fresh clip from Pexels/Pixabay/Mixkit; next.",
                flush=True,
            )
            continue

        provider, video_id, video_file_url, reused = hit
        clip_num = start_index + len(downloaded)
        clip_path = output / f"clip_{clip_num}.mp4"
        _download_file(video_file_url, clip_path)
        downloaded.append(str(clip_path))
        meta["providers"].append(provider)
        meta["scene_relevance"].append(
            {
                "scene": len(downloaded) - 1,
                "source": provider,
                "query": keyword,
            }
        )
        if reused:
            meta["cache_reuse_downloads"] += 1
        else:
            meta["fresh_downloads"] += 1
        if video_id is not None:
            newly_used_ids.append(_clip_id(provider, video_id))

    if not downloaded:
        if meta_out is not None:
            meta_out.update(meta)
            meta_out["fallback"] = "stock_empty"
        if fallback_on_empty:
            return _generate_fallback_clips(count, output_dir)
        return []

    if state_path and newly_used_ids:
        _save_used_clip_ids(state_path, used_ids.union(newly_used_ids))

    if meta_out is not None:
        total = len(downloaded)
        meta["clip_count"] = total
        meta["stock_cache_reuse_ratio"] = (
            round(meta["cache_reuse_downloads"] / total, 3) if total else 0.0
        )
        meta_out.update(meta)

    return downloaded


def _search_stock_waterfall(
    keyword: str,
    *,
    pexels_key: str,
    pixabay_key: str,
    enable_mixkit: bool,
    exclude_ids: set,
    allow_used_id_reuse: bool,
) -> tuple[str, object, str, bool] | None:
    """Return (provider, id, url, reused) or None."""
    providers = []
    if pexels_key:
        providers.append("pexels")
    if pixabay_key:
        providers.append("pixabay")
    if enable_mixkit:
        providers.append("mixkit")

    for provider in providers:
        try:
            if provider == "pexels":
                vid, url, reused = _search_portrait_video(
                    keyword,
                    pexels_key,
                    exclude_ids=exclude_ids,
                    allow_used_id_reuse=allow_used_id_reuse,
                )
            elif provider == "pixabay":
                vid, url, reused = _search_pixabay_video(
                    keyword,
                    pixabay_key,
                    exclude_ids=exclude_ids,
                    allow_used_id_reuse=allow_used_id_reuse,
                )
            else:
                vid, url, reused = _search_mixkit_video(
                    keyword,
                    exclude_ids=exclude_ids,
                    allow_used_id_reuse=allow_used_id_reuse,
                )
        except Exception as exc:
            print(f"[stock/{provider}] '{keyword}' failed ({exc}); next provider.", flush=True)
            continue
        if url:
            return provider, vid, url, reused
    return None


def _load_used_clip_ids(state_path: str) -> set:
    path = Path(state_path)
    if not path.is_file():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("used_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_used_clip_ids(state_path: str, ids: set) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sınırsız büyümesin — en son kullanılan N tanesi yeterli "tekrar etme" hafızası.
    trimmed = list(ids)[-USED_CLIP_HISTORY_LIMIT:]
    path.write_text(json.dumps({"used_ids": trimmed}), encoding="utf-8")


def _generate_fallback_clips(
    count: int,
    output_dir: str,
    accent: str = None,
    size: tuple[int, int] = FALLBACK_SIZE,
    fps: int = FALLBACK_FPS,
    duration: int = FALLBACK_DURATION_SECONDS,
) -> list[str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    accent = accent or config.IMAGE_ACCENT
    frame_count = duration * fps

    clips = []
    for index in range(count):
        frame_dir = output / f"fallback_frames_{index}"
        frame_dir.mkdir(exist_ok=True)

        for frame_index in range(frame_count):
            image = _render_fallback_frame(
                frame_index, frame_count, index, count, accent, size
            )
            image.save(frame_dir / f"frame_{frame_index:04d}.png")

        clip_path = output / f"fallback_{index}.mp4"
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(frame_dir / "frame_%04d.png"),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-pix_fmt", "yuv420p",
                str(clip_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"fallback clip encode failed: {result.stderr[-800:]}")
        clips.append(str(clip_path))
        shutil.rmtree(frame_dir, ignore_errors=True)

    return clips


def _render_fallback_frame(
    frame_index: int,
    frame_count: int,
    clip_index: int,
    clip_count: int,
    accent: str,
    size: tuple[int, int],
) -> Image.Image:
    width, height = size
    accent_rgb = _hex_to_rgb(accent)
    phase = (frame_index / max(frame_count, 1)) * 2 * math.pi

    # 1xH degradeyi çizip genişlet (C tarafında hızlı).
    gradient = Image.new("RGB", (1, height))
    gd = ImageDraw.Draw(gradient)
    top = _mix(accent_rgb, (15, 23, 42), 0.75)  # accent -> koyu
    bottom = _mix(accent_rgb, (15, 23, 42), 0.35 + 0.25 * (0.5 + 0.5 * math.sin(phase)))
    for y in range(height):
        t = y / max(height - 1, 1)
        gd.point((0, y), fill=_mix(top, bottom, t))
    image = gradient.resize((width, height))

    # Yumuşak ışık lekeleri: küçük katmanda çiz, blur, büyüt (ucuz ve yumuşak).
    overlay = Image.new("RGBA", (width // 4, height // 4), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for blob in range(3):
        speed = 1.0 + blob * 0.6
        cx = 0.5 + 0.35 * math.sin(phase * speed + blob * 2.1 + clip_index * 1.7)
        cy = 0.5 + 0.30 * math.cos(phase * (speed * 0.8) + blob * 1.3)
        radius = (0.18 + 0.08 * math.sin(phase + blob)) * (width // 4)
        alpha = 46 + blob * 12
        color = accent_rgb if blob % 2 == 0 else (255, 255, 255)
        od.ellipse(
            (
                cx * (width // 4) - radius,
                cy * (height // 4) - radius,
                cx * (width // 4) + radius,
                cy * (height // 4) + radius,
            ),
            fill=color + (alpha,),
        )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=width // 90))
    overlay = overlay.resize((width, height))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    return image


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _mix(
    color_a: tuple[int, int, int], color_b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return tuple(
        int(round(a + (b - a) * t)) for a, b in zip(color_a, color_b)
    )


def _search_portrait_video(
    keyword: str,
    api_key: str,
    exclude_ids: frozenset = frozenset(),
    allow_used_id_reuse: bool = False,
):
    """(video_id, download_url, reused_from_used_ids) — miss → (None, None, False).

    Scores candidates against the query; rejects irrelevant construction/street
    slugs; requires HD (long edge ≥ 720) and prefers portrait.
    """
    response = session.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={"query": keyword, "orientation": "portrait", "per_page": PEXELS_PER_PAGE},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    videos = data.get("videos", [])
    if not videos:
        # Retry without orientation lock — then crop landscape HD.
        response = session.get(
            PEXELS_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": keyword, "per_page": PEXELS_PER_PAGE},
            timeout=30,
        )
        response.raise_for_status()
        videos = response.json().get("videos", [])
    if not videos:
        return None, None, False

    exclude = set(exclude_ids)
    ranked = []
    for v in videos:
        if _ids_match_exclude("pexels", v.get("id"), exclude) and not allow_used_id_reuse:
            continue
        blob = " ".join(
            str(x)
            for x in (
                v.get("url"),
                v.get("image"),
                (v.get("user") or {}).get("name"),
                keyword,
            )
            if x
        )
        # Prefer URL slug relevance; Pexels rarely returns tags.
        score = _score_stock_candidate(str(v.get("url") or ""), keyword)
        if score < 0:
            continue
        file_meta = _pick_quality_video_file(v.get("video_files") or [])
        if not file_meta or not file_meta.get("link"):
            continue
        reused = _ids_match_exclude("pexels", v.get("id"), exclude)
        ranked.append((score, 1 if (file_meta.get("height") or 0) > (file_meta.get("width") or 0) else 0, v, file_meta, reused))

    if not ranked:
        return None, None, False

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    # Among top scorers, pick randomly from the best score tier (diversity).
    best_score = ranked[0][0]
    top = [r for r in ranked if r[0] >= best_score - 0.01][:5]
    _, _, video, file_meta, reused = random.choice(top)
    return video.get("id"), file_meta.get("link"), reused


def _search_pixabay_video(
    keyword: str,
    api_key: str,
    exclude_ids: frozenset = frozenset(),
    allow_used_id_reuse: bool = False,
):
    """Pixabay video API — (id, url, reused). Prefers tall/portrait HD + relevance."""
    response = session.get(
        PIXABAY_SEARCH_URL,
        params={
            "key": api_key,
            "q": keyword[:100],
            "video_type": "film",
            "per_page": PIXABAY_PER_PAGE,
            "safesearch": "true",
        },
        timeout=30,
    )
    response.raise_for_status()
    hits = response.json().get("hits") or []
    if not hits:
        return None, None, False

    exclude = set(exclude_ids)
    ranked = []
    for h in hits:
        if _ids_match_exclude("pixabay", h.get("id"), exclude) and not allow_used_id_reuse:
            continue
        blob = " ".join(
            str(x)
            for x in (h.get("tags"), h.get("pageURL"), h.get("user"), keyword)
            if x
        )
        score = _score_stock_candidate(blob, keyword)
        if score < 0:
            continue
        videos = h.get("videos") or {}
        variants = []
        for size_name in ("large", "medium", "small", "tiny"):
            v = videos.get(size_name) or {}
            if v.get("url"):
                variants.append(v)
        file_meta = _pick_quality_video_file(
            [
                {
                    "url": v.get("url"),
                    "link": v.get("url"),
                    "width": v.get("width"),
                    "height": v.get("height"),
                }
                for v in variants
            ]
        )
        if not file_meta:
            continue
        link = file_meta.get("link") or file_meta.get("url")
        if not link:
            continue
        reused = _ids_match_exclude("pixabay", h.get("id"), exclude)
        portrait = 1 if (file_meta.get("height") or 0) > (file_meta.get("width") or 0) else 0
        ranked.append((score, portrait, h, link, reused))

    if not ranked:
        return None, None, False

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    best_score = ranked[0][0]
    top = [r for r in ranked if r[0] >= best_score - 0.01][:5]
    _, _, hit, link, reused = random.choice(top)
    return hit.get("id"), link, reused


def _search_mixkit_video(
    keyword: str,
    exclude_ids: frozenset = frozenset(),
    allow_used_id_reuse: bool = False,
):
    """Best-effort Mixkit HTML search (no official API). Soft-fails to None."""
    slug = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-") or "cinematic"
    url = MIXKIT_SEARCH_URL.format(slug=slug)
    response = session.get(url, headers=_MIXKIT_UA, timeout=30)
    if response.status_code == 404:
        # Broader tag page
        response = session.get(
            "https://mixkit.co/free-stock-video/",
            headers=_MIXKIT_UA,
            params={"q": keyword},
            timeout=30,
        )
    response.raise_for_status()
    html = response.text or ""
    urls = list(dict.fromkeys(_MIXKIT_MP4_RE.findall(html)))
    if not urls:
        return None, None, False

    exclude = set(exclude_ids)
    fresh = []
    for u in urls:
        clip_key = u.rsplit("/", 1)[-1].replace(".mp4", "")
        if not _ids_match_exclude("mixkit", clip_key, exclude):
            fresh.append((clip_key, u))

    reused = False
    if fresh:
        clip_key, chosen = random.choice(fresh)
    elif allow_used_id_reuse:
        chosen = random.choice(urls)
        clip_key = chosen.rsplit("/", 1)[-1].replace(".mp4", "")
        reused = True
    else:
        return None, None, False

    return clip_key, chosen, reused


def _download_file(url: str, destination: Path) -> None:
    kwargs = {"timeout": 60}
    if "mixkit.co" in (url or ""):
        kwargs["headers"] = _MIXKIT_UA
    response = session.get(url, **kwargs)
    response.raise_for_status()
    destination.write_bytes(response.content)
