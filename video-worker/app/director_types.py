"""AI Director shared types — scenes + visual beats (Phase 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# Implemented now (retrieval). Reserved kinds are accepted in plans but map to
# stock_photo / ai_image until Phase 2+ providers land — never invent assets.
ALLOWED_KINDS = (
    "stock_video",
    "stock_photo",
    "ai_image",
)

# Future-facing labels for storyboard JSON (normalized into ALLOWED_KINDS).
KIND_ALIASES = {
    "archive_photo": "stock_photo",
    "archive_still": "stock_photo",
    "document": "stock_photo",
    "chart": "ai_image",
    "stat_graphic": "ai_image",
    "map": "stock_photo",
    "kinetic_typography": "ai_image",
    "ai_video": "ai_image",  # controlled still+KB until AI video wired
}

# Visual change without requiring a new download (priority: relevance > new clip).
VISUAL_CHANGE_REUSE = frozenset(
    {"punch_in", "crop_zoom", "archive_motion", "reuse_with_motion"}
)
VISUAL_CHANGE_NEW = "new_asset"

# Priority (never sacrifice earlier for later):
# semantic relevance > entity accuracy > visual storytelling > pacing > visual variety
DIRECTOR_PRIORITY = (
    "semantic_relevance",
    "entity_accuracy",
    "visual_storytelling",
    "pacing",
    "visual_variety",
)


@dataclass
class VisualBeat:
    """One visual idea that should verify spoken content (entity-first)."""

    index: int
    spoken_span: str = ""
    duration_hint: float | None = None
    concept: str = ""
    narrative_role: str = "evidence"  # hook | evidence | entity_proof | money | place | document | cta
    primary_entities: list[str] = field(default_factory=list)
    visual_intent: str = ""
    preferred_media: list[str] = field(default_factory=list)
    must_show: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    search_queries: list[str] = field(default_factory=list)
    shot_type: str = "insert"  # hero_closeup | insert | wide | archival | graphic | reveal
    motion: str = "slow_push"  # static_kb | slow_push | hold | punch_in
    overlay_intent: str = "none"  # none | punch_word | number
    fallback_ladder: list[str] = field(default_factory=list)
    confidence: float = 0.5
    allow_ai_generation: bool = False
    scene_index: int = 0
    # new_asset | punch_in | crop_zoom | archive_motion | reuse_with_motion
    visual_change: str = VISUAL_CHANGE_NEW
    # Phase 3 reserved — storyboard may carry cues; audio pipeline unchanged in Phase 2.
    audio_cue: str = ""
    emphasis_cue: str = ""

    def kind_chain(self) -> list[str]:
        ordered: list[str] = []
        for raw in list(self.preferred_media) + list(self.fallback_ladder):
            k = KIND_ALIASES.get((raw or "").strip().lower(), (raw or "").strip().lower())
            if k in ALLOWED_KINDS and k not in ordered:
                ordered.append(k)
        if not ordered:
            ordered = ["stock_video", "stock_photo"]
        if self.allow_ai_generation and "ai_image" not in ordered:
            ordered.append("ai_image")
        # Entity beats: prefer photo/archive before generic video filler
        if self.primary_entities and ordered[0] == "stock_video":
            if "stock_photo" in ordered:
                ordered.remove("stock_photo")
                ordered.insert(0, "stock_photo")
        return ordered

    def entity_first_queries(self, topic: str = "") -> list[str]:
        """exact entity → entity+context → planned queries (retrieval order)."""
        seen: set[str] = set()
        out: list[str] = []

        def add(q: str) -> None:
            qq = (q or "").strip()
            key = qq.lower()
            if qq and key not in seen:
                seen.add(key)
                out.append(qq)

        ents = list(self.primary_entities) or list(self.must_show)
        for e in ents:
            # Person-like multi-word: archive/portrait before generic brand B-roll.
            if len(e.split()) >= 2:
                add(f"{e} portrait archive")
                add(f"{e} founder portrait")
                add(f"{e} historical archive")
            add(e)
            ctx = " ".join(
                x for x in (self.concept, self.shot_type.replace("_", " ")) if x
            ).strip()
            if ctx:
                add(f"{e} {ctx}")
            # Avoid pasting the full long topic onto entity queries (pollution).
            topic_bits = [w for w in (topic or "").split() if len(w) > 2][:3]
            if topic_bits and topic.lower() not in e.lower():
                add(f"{e} {' '.join(topic_bits)}")
        for q in self.search_queries:
            add(q)
        if self.visual_intent:
            add(self.visual_intent[:90])
        # Short topic only as last-resort filler — not the full headline.
        if topic and len(topic.split()) <= 6:
            add(topic)
        return out

    def resolve_duration_hint(self, default: float = 1.6) -> float:
        """Micro-pacing: prefer ~1.2–2.0s; no hard cap — hero/reveal may run longer.

        Prevents a single generic stock clip from idling 4–5s without meaning.
        Never invents ungated assets to fill time.
        """
        heroish = self.shot_type in {"hero_closeup", "reveal"} or self.narrative_role == "hook"
        hint = self.duration_hint
        if hint is None:
            return 2.4 if heroish else float(default)
        try:
            d = float(hint)
        except (TypeError, ValueError):
            return 2.4 if heroish else float(default)
        d = max(0.8, d)
        if heroish:
            # Soft upper bound only — storytelling may hold longer than micro beats.
            return min(d, 4.0)
        # Generic / non-entity: keep micro-paced so we don't park on filler.
        if not self.primary_entities and self.narrative_role in {
            "evidence",
            "atmosphere",
        }:
            return min(max(d, 1.2), 2.0)
        return min(max(d, 1.2), 2.8)

    def wants_reuse_visual_change(self) -> bool:
        return (self.visual_change or "").strip().lower() in VISUAL_CHANGE_REUSE

    def word_to_visual_skeleton(self) -> dict[str, Any]:
        """Loggable spoken → concept/entity → intent chain (asset filled at fetch)."""
        return {
            "spoken_span": self.spoken_span[:160],
            "concept": self.concept,
            "entities": list(self.primary_entities or self.must_show),
            "visual_intent": self.visual_intent[:240],
            "search_queries": self.search_queries[:4],
            "shot_type": self.shot_type,
            "visual_change": self.visual_change,
            "duration_hint": self.resolve_duration_hint(),
            "confidence": self.confidence,
            "audio_cue": self.audio_cue or None,
            "emphasis_cue": self.emphasis_cue or None,
        }

    def to_meta(self) -> dict[str, Any]:
        return {
            "beat": self.index,
            "scene_index": self.scene_index,
            "spoken_span": self.spoken_span[:120],
            "concept": self.concept,
            "narrative_role": self.narrative_role,
            "primary_entities": self.primary_entities,
            "visual_intent": self.visual_intent[:200],
            "preferred_media": self.preferred_media,
            "must_show": self.must_show,
            "shot_type": self.shot_type,
            "motion": self.motion,
            "overlay_intent": self.overlay_intent,
            "visual_change": self.visual_change,
            "confidence": self.confidence,
            "search_queries": self.search_queries[:4],
            "duration_hint": self.duration_hint,
            "resolved_duration": self.resolve_duration_hint(),
            "audio_cue": self.audio_cue or None,
            "emphasis_cue": self.emphasis_cue or None,
        }


@dataclass
class ScenePlan:
    """Time slot on the timeline; may contain one or more visual beats."""

    index: int
    scene_type: str
    visual_intent: str
    preferred_kinds: list[str]
    search_queries: list[str]
    backup_kinds: list[str] = field(default_factory=list)
    backup_queries: list[str] = field(default_factory=list)
    must_show: list[str] = field(default_factory=list)
    avoid: list[str] = field(default_factory=list)
    required_entities: list[str] = field(default_factory=list)
    allow_ai_generation: bool = False
    beats: list[VisualBeat] = field(default_factory=list)

    def kind_chain(self) -> list[str]:
        ordered: list[str] = []
        for k in list(self.preferred_kinds) + list(self.backup_kinds):
            kk = KIND_ALIASES.get((k or "").strip().lower(), (k or "").strip().lower())
            if kk in ALLOWED_KINDS and kk not in ordered:
                ordered.append(kk)
        if not ordered:
            ordered = ["stock_video", "stock_photo"]
        if self.allow_ai_generation and "ai_image" not in ordered:
            ordered.append("ai_image")
        return ordered

    def query_chain(self) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for q in list(self.search_queries) + list(self.backup_queries):
            qq = (q or "").strip()
            key = qq.lower()
            if qq and key not in seen:
                seen.add(key)
                out.append(qq)
        return out

    def ensure_beats(self) -> list[VisualBeat]:
        """At least one beat derived from scene fields."""
        if self.beats:
            return self.beats
        beat = VisualBeat(
            index=0,
            scene_index=self.index,
            spoken_span=self.visual_intent[:160],
            concept=self.scene_type,
            narrative_role="hook" if self.index == 0 else "evidence",
            primary_entities=list(self.required_entities or self.must_show),
            visual_intent=self.visual_intent,
            preferred_media=list(self.preferred_kinds),
            must_show=list(self.must_show),
            avoid=list(self.avoid),
            search_queries=list(self.search_queries),
            shot_type="hero_closeup" if self.index == 0 else "insert",
            duration_hint=2.4 if self.index == 0 else 1.6,
            visual_change=VISUAL_CHANGE_NEW,
            allow_ai_generation=self.allow_ai_generation,
            confidence=0.4,
        )
        self.beats = [beat]
        return self.beats


@dataclass
class HookDirectorPlan:
    """First 0–3s: short punch overlay + karaoke delay (no long static paragraph)."""

    overlay_text: str = ""
    hook_seconds: float = 1.8
    karaoke_start_seconds: float = 1.8
    hero_shot: str = "hero_closeup"
    motion: str = "slow_push"

    def to_meta(self) -> dict[str, Any]:
        return {
            "overlay_text": self.overlay_text,
            "hook_seconds": self.hook_seconds,
            "karaoke_start_seconds": self.karaoke_start_seconds,
            "hero_shot": self.hero_shot,
            "motion": self.motion,
        }


@dataclass
class ScenePlanDocument:
    scenes: list[ScenePlan]
    hook: HookDirectorPlan | None = None

    def all_beats(self) -> list[VisualBeat]:
        beats: list[VisualBeat] = []
        for sc in self.scenes:
            for b in sc.ensure_beats():
                beats.append(b)
        return beats

    def to_meta(self) -> list[dict[str, Any]]:
        rows = []
        for s in self.scenes:
            rows.append(
                {
                    "scene": s.index,
                    "scene_type": s.scene_type,
                    "visual_intent": s.visual_intent[:200],
                    "preferred_kinds": s.preferred_kinds,
                    "search_queries": s.search_queries,
                    "must_show": s.must_show,
                    "avoid": s.avoid[:12],
                    "required_entities": s.required_entities,
                    "allow_ai_generation": s.allow_ai_generation,
                    "beats": [b.to_meta() for b in s.ensure_beats()],
                }
            )
        return rows

    def hook_meta(self) -> dict[str, Any] | None:
        return self.hook.to_meta() if self.hook else None
