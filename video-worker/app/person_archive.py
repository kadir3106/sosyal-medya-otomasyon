"""Phase 3.1 — generic person archive retrieval + validated cache.

No brand/person hardcodes. Wikipedia/Commons pageimage only (no scraping farm).
Wrong person → fail-closed (gate rejects).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from app.director_gate import AssetCandidate, evaluate_asset
from app.http_client import session

logger = logging.getLogger(__name__)

_ORG_TOKENS = frozenset(
    {
        "foundation", "company", "corp", "corporation", "inc", "ltd", "llc",
        "bank", "trust", "group", "agency", "institute", "university",
    }
)
_PLACE_TOKENS = frozenset(
    {
        "street", "avenue", "road", "boulevard", "park", "square", "plaza",
        "bridge", "river", "lake", "ocean", "sea", "mountain", "island",
        "valley", "district", "quarter", "city", "town", "village",
    }
)


_TITLE_PREFIXES = frozenset(
    {
        "founder", "co-founder", "ceo", "chairman", "president", "sir", "dr",
        "mr", "mrs", "ms", "lord", "lady",
    }
)


def looks_like_person_name(entity: str) -> bool:
    parts = [p for p in re.split(r"\s+", (entity or "").strip()) if p]
    # Drop leading titles: "Founder Hans Wilsdorf" → "Hans Wilsdorf"
    while parts and parts[0].lower().rstrip(".,") in _TITLE_PREFIXES:
        parts = parts[1:]
    if len(parts) < 2 or len(parts) > 4:
        return False
    if any(p.lower().rstrip(".,") in _ORG_TOKENS for p in parts):
        return False
    if any(p.lower().rstrip(".,") in _PLACE_TOKENS for p in parts):
        return False
    alpha = [p for p in parts if p.isalpha() or (p.replace("-", "").isalpha())]
    if len(alpha) < 2:
        return False
    return all(p[:1].isupper() for p in alpha)


def normalize_person_key(entity: str) -> str:
    parts = [p for p in re.split(r"\s+", (entity or "").strip()) if p]
    while parts and parts[0].lower().rstrip(".,") in _TITLE_PREFIXES:
        parts = parts[1:]
    return re.sub(r"\s+", " ", " ".join(parts).strip().lower())


def person_query_name(entity: str) -> str:
    """Display/search name without leading titles."""
    parts = [p for p in re.split(r"\s+", (entity or "").strip()) if p]
    while parts and parts[0].lower().rstrip(".,") in _TITLE_PREFIXES:
        parts = parts[1:]
    return " ".join(parts).strip()


def _cache_path(media_dir: Path) -> Path:
    return media_dir / "person_asset_cache.json"


def load_person_cache(media_dir: Path | str) -> dict[str, Any]:
    path = _cache_path(Path(media_dir))
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_person_cache(media_dir: Path | str, cache: dict[str, Any]) -> None:
    path = _cache_path(Path(media_dir))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, ensure_ascii=False)[:400000], encoding="utf-8")


def fetch_wikipedia_person_image(entity: str) -> dict[str, Any] | None:
    """Resolve a page image for a person-like entity via MediaWiki API."""
    title = person_query_name(entity) or (entity or "").strip()
    if not title or not looks_like_person_name(title):
        return None
    try:
        # 1) Search for best page title
        sr = session.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "list": "search",
                "srsearch": title,
                "srlimit": 3,
                "format": "json",
            },
            headers={"User-Agent": "sosyal-medya-otomasyon/phase31 (person-archive)"},
            timeout=12,
        )
        if sr.status_code != 200:
            return None
        hits = (sr.json().get("query") or {}).get("search") or []
        if not hits:
            return None
        # Prefer title that contains both name tokens
        tokens = [t.lower() for t in title.split()]
        page_title = hits[0].get("title") or title
        for h in hits:
            ht = str(h.get("title") or "").lower()
            if all(tok in ht for tok in tokens[:2]):
                page_title = h.get("title") or page_title
                break

        # 2) Page image
        pi = session.get(
            "https://en.wikipedia.org/w/api.php",
            params={
                "action": "query",
                "titles": page_title,
                "prop": "pageimages|info",
                "pithumbsize": 1280,
                "inprop": "url",
                "format": "json",
            },
            headers={"User-Agent": "sosyal-medya-otomasyon/phase31 (person-archive)"},
            timeout=12,
        )
        if pi.status_code != 200:
            return None
        pages = (pi.json().get("query") or {}).get("pages") or {}
        for _pid, page in pages.items():
            if str(_pid) == "-1":
                continue
            thumb = page.get("thumbnail") or {}
            src = thumb.get("source")
            if not src:
                continue
            pt = str(page.get("title") or page_title)
            # Soft identity check: page title should share name tokens
            pt_l = pt.lower()
            if not all(tok in pt_l for tok in tokens[:2]):
                continue
            return {
                "title": pt,
                "download_url": str(src).split("?")[0],
                "page_url": str(page.get("fullurl") or f"https://en.wikipedia.org/wiki/{pt.replace(' ', '_')}"),
                "provider": "wikipedia_pageimage",
                "asset_id": f"wiki:{hashlib.sha1(pt.encode()).hexdigest()[:12]}",
                "attribution": "Wikipedia/Wikimedia",
                "alt": f"Archive portrait related to {pt}",
                "description": f"Wikipedia page image for {pt}",
                "tags": f"portrait archive historical {pt}",
            }
    except Exception as exc:
        logger.info("wikipedia person image miss (%s): %s", title, exc)
    return None


def try_cached_or_fetch_person_image(
    entity: str,
    *,
    media_dir: Path | str,
    need,
    attempts: list | None = None,
) -> tuple[AssetCandidate | None, dict[str, Any] | None, Any]:
    """Return gated candidate for a person entity (cache → Wikipedia)."""
    from app.director_gate import GateResult  # type hint soft

    key = normalize_person_key(entity)
    if not key or not looks_like_person_name(entity):
        return None, None, None

    cache = load_person_cache(media_dir)
    entry = cache.get(key)
    meta = None
    if entry and entry.get("download_url") and entry.get("entity_key") == key:
        meta = dict(entry)
    else:
        meta = fetch_wikipedia_person_image(entity)
        if meta:
            meta["entity_key"] = key
            meta["validated"] = False

    if not meta or not meta.get("download_url"):
        return None, None, None

    cand = AssetCandidate(
        provider=str(meta.get("provider") or "wikipedia_pageimage"),
        asset_id=str(meta.get("asset_id") or ""),
        download_url=str(meta["download_url"]),
        title=str(meta.get("alt") or meta.get("title") or entity),
        tags=str(meta.get("tags") or f"portrait archive {entity}"),
        description=str(meta.get("description") or meta.get("title") or entity),
        url=str(meta.get("page_url") or ""),
        user=str(meta.get("attribution") or "Wikipedia"),
        kind="stock_photo",
    )
    gate = evaluate_asset(cand, need)
    if attempts is not None:
        attempts.append(
            {
                "kind": "person_archive",
                "query": entity,
                "provider": cand.provider,
                "asset_id": cand.asset_id,
                "metadata_excerpt": cand.metadata_blob()[:180],
                "relevance_score": gate.relevance_score,
                "entity_score": gate.entity_score,
                "specificity_score": gate.specificity_score,
                "rejection_reason": None if gate.accepted else gate.reason,
                "source": "person_cache" if entry else "wikipedia",
            }
        )
    if not gate.accepted:
        return None, meta, gate

    # Cache only validated accepts for this entity key
    meta["validated"] = True
    meta["entity_key"] = key
    cache[key] = {
        k: meta[k]
        for k in (
            "entity_key",
            "title",
            "download_url",
            "page_url",
            "provider",
            "asset_id",
            "attribution",
            "alt",
            "description",
            "tags",
            "validated",
        )
        if k in meta
    }
    try:
        save_person_cache(media_dir, cache)
    except Exception:
        pass
    return cand, meta, gate
