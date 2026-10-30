"""Phase 3.1/3.2 — RetentionEvent V2 + visual-information hold / contextual cutaway."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


_CLAIM_RE = re.compile(
    r"\b(tax|taxes|tax[- ]?free|reserve|reserves|vault|billion|million|"
    r"shareholder|shareholders|ownership|owned|foundation|trust|nonprofit|"
    r"non[- ]profit|charity|exemption|document|legal|zero|100%|percent)\b",
    re.I,
)
_NUMBER_RE = re.compile(r"\$|\bbillion|\bmillion|\bpercent|\b%|\bzero\b|\b100%\b", re.I)
_PRODUCT_RE = re.compile(
    r"\b(watch|watches|rolex|dial|bracelet|luxury\s+product|boxed)\b", re.I
)


@dataclass
class RetentionEvent:
    timestamp: float
    reason: str
    event_type: str
    source_beat: int
    importance: float = 0.5
    asset_change_required: bool = False
    transform: str = ""  # punch_in | crop_zoom | archive_motion | ""
    spoken_span: str = ""
    semantic_reason: str = ""
    old_visual: str = ""
    new_visual: str = ""
    selection_reason: str = ""
    cutaway_queries: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def visual_info_key(beat: dict) -> str:
    """Coarse visual-information identity (not crop/zoom).

    Prefer explicit visual_information_id when present. Zoom/punch alone
    does not change this key.
    """
    explicit = str(beat.get("visual_information_id") or "").strip()
    if explicit:
        return f"vid:{explicit}"
    span = str(beat.get("spoken_span") or beat.get("visual_intent") or "")
    concept = str(beat.get("concept") or "").lower()
    role = str(beat.get("narrative_role") or "").lower()
    ents = [str(e).lower() for e in (beat.get("entities") or beat.get("primary_entities") or [])]
    low = f"{span} {concept} {role} {' '.join(ents)}".lower()

    if any(_looks_person_entity(e) for e in (beat.get("entities") or beat.get("primary_entities") or [])):
        return "person_archive"
    if re.search(r"\b(tax|document|legal|filing|charter|deed)\b", low):
        return "document_legal"
    if re.search(r"\b(vault|reserve|bank|finance|billion|wealth|gold)\b", low):
        return "finance_reserve"
    if re.search(r"\b(foundation|trust|ownership|shareholder|nonprofit|non-profit)\b", low):
        return "ownership_structure"
    if re.search(r"\b(geneva|swiss|switzerland|zurich|city|district)\b", low):
        return "place_context"
    if _PRODUCT_RE.search(low) or "luxury" in concept or role in {"hook", "evidence"}:
        # Product / brand hero — many Rolex box shots share this bucket
        brand = next((e for e in ents if e and "foundation" not in e and " " not in e), "")
        return f"product_hero:{brand or 'brand'}"
    return f"generic:{role or concept or 'beat'}"


def spoken_claim_shift(prev: dict, cur: dict) -> str | None:
    """Return semantic reason if narration introduces a new claim family."""
    prev_key = visual_info_key(prev) if prev else ""
    cur_key = visual_info_key(cur)
    if prev_key and cur_key and prev_key != cur_key:
        if cur_key.startswith("finance") or cur_key == "document_legal":
            return "new_financial_or_document_claim"
        if cur_key == "ownership_structure":
            return "new_ownership_claim"
        if cur_key == "person_archive":
            return "named_person_introduction"
        if cur_key == "place_context":
            return "place_context_shift"
        return "semantic_concept_shift"

    cur_span = str(cur.get("spoken_span") or "").lower()
    prev_span = str(prev.get("spoken_span") or "").lower() if prev else ""
    if _CLAIM_RE.search(cur_span) and not _CLAIM_RE.search(prev_span):
        return "new_factual_claim"
    if _NUMBER_RE.search(cur_span) and not _NUMBER_RE.search(prev_span):
        return "important_number"
    return None


def cutaway_queries_for_beat(beat: dict) -> list[str]:
    """Generic concept → search queries (no brand hardcodes)."""
    span = str(beat.get("spoken_span") or beat.get("visual_intent") or "")
    low = span.lower()
    q: list[str] = []
    if re.search(r"\b(tax|tax[- ]?free|exemption)\b", low):
        q += ["tax documents paperwork desk", "corporate tax exemption filing"]
    if re.search(r"\b(reserve|reserves|vault|gold)\b", low):
        q += ["bank vault gold reserves", "secure financial vault"]
    if re.search(r"\b(billion|million|wealth|revenue)\b", low):
        q += ["financial wealth reserves cinematic", "swiss bank finance night"]
    if re.search(r"\b(foundation|trust|ownership|shareholder)\b", low):
        q += ["foundation ownership documents", "private trust legal charter"]
    if re.search(r"\b(geneva|swiss|switzerland)\b", low):
        q += ["Geneva financial district dusk", "Swiss bank building exterior"]
    if not q:
        q = [span[:80] or "cinematic documentary detail"]
    # Dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for item in q:
        k = item.lower()
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out[:4]


def _looks_person_entity(name: str) -> bool:
    parts = [p for p in re.split(r"\s+", (name or "").strip()) if p]
    if len(parts) < 2:
        return False
    org = {"foundation", "company", "corp", "inc", "ltd", "bank", "trust", "group"}
    place = {"street", "avenue", "road", "park", "square"}
    if any(p.lower().rstrip(".,") in org | place for p in parts):
        return False
    return all(p[:1].isupper() for p in parts if p.isalpha())


def plan_retention_events(
    word_to_visual: list[dict],
    *,
    scene_durations: list[float] | None = None,
    max_events: int = 6,
) -> list[RetentionEvent]:
    """Plan semantic retention events — visual-info hold ≠ asset duration."""
    events: list[RetentionEvent] = []
    if not word_to_visual:
        return events

    t = 0.0
    seen_persons: set[str] = set()
    last_asset: str | None = None
    last_transform_t = -99.0
    hold_start = 0.0
    hold_info: str | None = None
    prev_beat: dict | None = None

    for i, beat in enumerate(word_to_visual):
        dur = float(beat.get("duration") or 0) or (
            float((scene_durations or [0])[min(i, len(scene_durations or []) - 1) or 0])
            if scene_durations
            else 2.0
        )
        if dur <= 0:
            dur = 2.0
        span = str(beat.get("spoken_span") or "")
        ents = [str(e) for e in (beat.get("entities") or beat.get("primary_entities") or [])]
        sel = beat.get("selected_asset") or {}
        aid = str(sel.get("asset_id") or sel.get("path") or "") or None
        info = visual_info_key(beat)
        low = span.lower()
        vc = str(beat.get("visual_change") or "").lower()

        # Person introduction
        for e in ents:
            key = e.lower().strip()
            if key and _looks_person_entity(e) and key not in seen_persons:
                seen_persons.add(key)
                events.append(
                    RetentionEvent(
                        timestamp=round(t + 0.05, 3),
                        reason="named_person_introduction",
                        event_type="archive_reveal",
                        source_beat=i,
                        importance=0.9,
                        asset_change_required=True,
                        spoken_span=span[:160],
                        semantic_reason="named_person_introduction",
                        old_visual=hold_info or "",
                        new_visual="person_archive",
                        selection_reason="entity_portrait_priority",
                    )
                )

        # Number / financial claim → emphasis (same-asset ok)
        if _NUMBER_RE.search(low):
            events.append(
                RetentionEvent(
                    timestamp=round(t + min(dur * 0.35, 0.8), 3),
                    reason="financial_scale_claim",
                    event_type="number_emphasis",
                    source_beat=i,
                    importance=0.7,
                    asset_change_required=False,
                    transform="punch_in",
                    spoken_span=span[:160],
                    semantic_reason="important_number",
                    old_visual=info,
                    new_visual=info,
                    selection_reason="number_emphasis_same_asset",
                )
            )

        # Visual-information hold (NOT asset_id alone).
        # Measure hold BEFORE resetting when info key changes.
        if info and info == hold_info:
            hold_len = (t + dur) - hold_start
            info_changed = False
        else:
            hold_len = (t - hold_start) if hold_info else 0.0
            info_changed = True

        shift = spoken_claim_shift(prev_beat, beat) if i > 0 else None
        # Long same visual-info then NEW claim → contextual cutaway
        prior_hold = hold_len if not info_changed else hold_len
        if (
            i > 0
            and prior_hold >= 2.5
            and shift
            and shift not in {"named_person_introduction"}
            and (t - last_transform_t) >= 2.0
        ):
            queries = cutaway_queries_for_beat(beat)
            events.append(
                RetentionEvent(
                    timestamp=round(t + 0.1, 3),
                    reason=shift,
                    event_type="contextual_cutaway",
                    source_beat=i,
                    importance=0.82,
                    asset_change_required=True,
                    transform="",
                    spoken_span=span[:160],
                    semantic_reason=shift,
                    old_visual=str(prev_beat and visual_info_key(prev_beat) or hold_info or ""),
                    new_visual=info,
                    selection_reason="semantic_cutaway_requires_gate",
                    cutaway_queries=queries,
                )
            )
            last_transform_t = t
            hold_start = t
            hold_info = info
        elif info_changed:
            hold_info = info
            hold_start = t
            hold_len = dur
        else:
            # continuing same info
            pass

        # Same asset composition change — zoom alone is NOT new information;
        # only allow when hold is long AND no cutaway already planned for beat.
        if (
            aid
            and last_asset
            and aid == last_asset
            and i > 0
            and hold_len >= 3.5
            and (t - last_transform_t) >= 2.4
            and not any(e.source_beat == i and e.event_type == "contextual_cutaway" for e in events)
            and vc not in {"punch_in", "crop_zoom"}  # already transforming ≠ new info
        ):
            events.append(
                RetentionEvent(
                    timestamp=round(t, 3),
                    reason="long_hold_composition_only",
                    event_type="controlled_punch_in",
                    source_beat=i,
                    importance=0.55,
                    asset_change_required=False,
                    transform="punch_in",
                    spoken_span=span[:160],
                    semantic_reason="long_visual_info_hold",
                    old_visual=info,
                    new_visual=info,
                    selection_reason="same_asset_controlled_punch_in",
                )
            )
            last_transform_t = t
            hold_start = t

        last_asset = aid or last_asset
        prev_beat = beat
        t += dur

    # Cap + anti-spam
    events.sort(key=lambda e: (-e.importance, e.timestamp))
    kept: list[RetentionEvent] = []
    last_t = -99.0
    transform_count = 0
    cutaway_count = 0
    for e in events:
        if e.event_type == "contextual_cutaway":
            if cutaway_count >= 2:
                continue
            if e.timestamp - last_t < 2.0 and kept:
                continue
            kept.append(e)
            last_t = e.timestamp
            cutaway_count += 1
            if len(kept) >= max_events:
                break
            continue
        if e.transform and transform_count >= 1:
            # Storytelling correction: at most ONE same-asset transform event.
            # Fake retention via zoom spam is forbidden.
            if e.asset_change_required:
                kept.append(e)
            continue
        if e.timestamp - last_t < 1.8 and e.transform:
            continue
        kept.append(e)
        last_t = e.timestamp
        if e.transform and not e.asset_change_required:
            transform_count += 1
        if len(kept) >= max_events:
            break
    kept.sort(key=lambda e: e.timestamp)
    return kept


def apply_retention_transforms_to_beats(
    word_to_visual: list[dict],
    events: list[RetentionEvent],
) -> list[dict]:
    """Mark beats that should reuse prior asset with visual_change (no new download)."""
    by_beat: dict[int, RetentionEvent] = {}
    for e in events:
        if e.transform and not e.asset_change_required:
            prev = by_beat.get(e.source_beat)
            if prev is None or e.importance >= prev.importance:
                by_beat[e.source_beat] = e
    out = []
    for i, beat in enumerate(word_to_visual):
        b = dict(beat)
        ev = by_beat.get(i)
        if ev and i > 0:
            b["visual_change"] = ev.transform
            b["retention_event"] = ev.to_dict()
            b["force_visual_change_reuse"] = True
        out.append(b)
    return out


def apply_retention_to_visual_beats(
    beats: list,
    events: list[RetentionEvent],
) -> None:
    """Mutate VisualBeat from retention plan (pre-fetch).

    Important distinct beats (person / ownership / contrast) MUST NOT be forced
    onto same-asset punch-in reuse — that collapses source diversity.
    """
    by_beat: dict[int, RetentionEvent] = {}
    for e in events:
        prev = by_beat.get(e.source_beat)
        if prev is None or e.importance >= prev.importance:
            by_beat[e.source_beat] = e

    last_tf = ""
    for i, beat in enumerate(beats):
        ev = by_beat.get(i)
        if not ev:
            continue

        if ev.event_type == "contextual_cutaway" and ev.asset_change_required:
            beat.visual_change = "new_asset"
            beat.motion = "slow_push"
            if ev.cutaway_queries:
                # Prepend cutaway queries — still entity-first via must_show
                merged = list(ev.cutaway_queries) + list(beat.search_queries or [])
                seen: set[str] = set()
                beat.search_queries = []
                for q in merged:
                    k = q.lower()
                    if k not in seen:
                        seen.add(k)
                        beat.search_queries.append(q)
                beat.search_queries = beat.search_queries[:4]
            if beat.narrative_role in {"hook", "evidence"} and ev.semantic_reason:
                if "finance" in ev.semantic_reason or "ownership" in ev.semantic_reason:
                    beat.narrative_role = "money" if "finance" in ev.semantic_reason else "document"
            continue

        if not ev.transform or ev.asset_change_required or i <= 0:
            continue

        # Never force same-asset transform onto important distinct roles
        role = str(getattr(beat, "narrative_role", "") or "")
        evidence = str(getattr(beat, "evidence_role", "") or "")
        if role in {
            "hook",
            "entity_proof",
            "document",
            "money",
            "place",
            "cta",
        } or evidence in {"archive", "proof", "document", "location", "contrast"}:
            beat.visual_change = "new_asset"
            continue

        tf = (ev.transform or "").strip().lower()
        if last_tf == "punch_in" and tf == "crop_zoom":
            continue
        beat.visual_change = tf or beat.visual_change
        beat.motion = tf or beat.motion
        last_tf = tf


def longest_unchanged_interval(word_to_visual: list[dict]) -> float:
    """Longest contiguous time with the same visual-information key."""
    best = 0.0
    cur = 0.0
    prev = None
    for b in word_to_visual:
        key = visual_info_key(b)
        dur = float(b.get("duration") or 0) or 0.0
        if key and key == prev:
            cur += dur
        else:
            best = max(best, cur)
            cur = dur if key else 0.0
            prev = key
    return max(best, cur)


def longest_same_asset_interval(word_to_visual: list[dict]) -> float:
    best = 0.0
    cur = 0.0
    prev = None
    for b in word_to_visual:
        aid = ((b.get("selected_asset") or {}).get("asset_id")) or None
        dur = float(b.get("duration") or 0) or 0.0
        if aid and aid == prev:
            cur += dur
        else:
            best = max(best, cur)
            cur = dur if aid else 0.0
            prev = aid
    return max(best, cur)
