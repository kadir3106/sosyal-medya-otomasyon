"""AI Director planner — storyboard + scenes via AI router (LLM_API_URL).

Does not choose models; uses the same gateway client as script_gen.
Phase 2: visual beats under scenes + Hook Director plan.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.director_types import (
    ALLOWED_KINDS,
    KIND_ALIASES,
    HookDirectorPlan,
    ScenePlan,
    ScenePlanDocument,
    VisualBeat,
)
from app.script_gen import _call_llm_with_fallback

logger = logging.getLogger(__name__)

PLANNER_SYSTEM = """You are a short-form Vertical 9:16 dark-luxury mini-documentary director.
Split the narration into visual beats so viewers SEE key concepts as they are spoken
(entity-first: brand, person, foundation, money, place, tax/document).

PRIORITY (never sacrifice an earlier item for a later one):
1) semantic relevance  2) entity accuracy  3) visual storytelling
4) pacing  5) visual variety
Never fill time with unrelated/generic stock just to hit a cut rate.

Return ONLY valid JSON (no markdown) with keys:
  "hook": {
    "overlay_text": short punch phrase max 6 words (NOT a long paragraph),
    "hook_seconds": number 1.2-2.5,
    "karaoke_start_seconds": same or slightly after hook end (avoid overlap),
    "hero_shot": "hero_closeup"|"wide"|"archival",
    "motion": "slow_push"|"static_kb"|"hold"|"punch_in"
  },
  "scenes": [ ... exactly scene_count items ... ]

Each scene object:
  index, scene_type, visual_intent (1-2 sentences),
  preferred_kinds (from: stock_video, stock_photo, ai_image,
    archive_photo, document, chart, map, kinetic_typography),
  search_queries (2-4 English phrases with brand/person names),
  backup_plan: { preferred_kinds, search_queries },
  must_show, avoid, required_entities, allow_ai_generation,
  visual_beats: [ 1-4 beats per scene when concepts change ]

Each visual_beat:
  spoken_span, duration_hint (optional; prefer ~1.2-2.0s; longer only for hero/reveal),
  concept, narrative_role (hook|evidence|entity_proof|money|place|document|cta),
  primary_entities, visual_intent, preferred_media, must_show, avoid,
  search_queries, shot_type, motion, overlay_intent (none|punch_word|number),
  visual_change (new_asset|punch_in|crop_zoom|archive_motion|reuse_with_motion),
  fallback_ladder, confidence (0-1), allow_ai_generation,
  audio_cue (optional string for Phase 3 SFX — do not require audio now),
  emphasis_cue (optional string for Phase 3 — do not require audio now)

Rules:
- Do NOT pick LLM model names or invent API providers.
- Prefer real stock/archive over AI. allow_ai_generation only when stock cannot show it.
- Never use meme/reaction as default style.
- Entity beats must keep exact names in search_queries (e.g. Hans Wilsdorf, not "businessman").
- Money/billions → financial visual; places → location; tax/document → document/mechanism visual.
- visual_change: prefer punch_in/crop_zoom on the SAME good asset when attention shifts
  but the entity is unchanged — a new download is NOT required for every beat.
- Do NOT park one generic stock clip for 4–5 empty seconds.
- Hook overlay must NOT duplicate karaoke wording at the same time.
"""

# Concept cues for heuristic beat segmentation (not hard word-count chops).
_MONEY_RE = re.compile(
    r"\b(billion|billions|million|millions|dollar|dollars|wealth|fortune|revenue|value)\b",
    re.I,
)
_PLACE_RE = re.compile(
    r"\b(switzerland|swiss|geneva|london|paris|new york|zurich)\b", re.I
)
_PERSON_RE = re.compile(
    r"\b(hans\s+wilsdorf|wilsdorf|[A-Z][a-z]+\s+[A-Z][a-z]+)\b"
)
_ORG_RE = re.compile(
    r"\b(foundation|foundation'?s|ownership|owns|shares?|empire)\b", re.I
)
_DOC_RE = re.compile(
    r"\b(tax|taxes|exemption|document|documents|legal|charter|contract|filing)\b",
    re.I,
)


def _normalize_kinds(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        k = str(item or "").strip().lower()
        k = KIND_ALIASES.get(k, k)
        if k in ALLOWED_KINDS and k not in out:
            out.append(k)
    return out


def _normalize_str_list(raw: Any, limit: int = 6) -> list[str]:
    if not isinstance(raw, list):
        return []
    from app.director_gate import hygienize_entities

    out: list[str] = []
    for item in raw:
        s = str(item or "").strip()
        if s and s.lower() not in {x.lower() for x in out}:
            out.append(s)
        if len(out) >= limit * 2:
            break
    return hygienize_entities(out, limit=limit)


def _parse_visual_beat(raw: dict, *, index: int, scene_index: int) -> VisualBeat:
    preferred = _normalize_kinds(raw.get("preferred_media") or raw.get("preferred_kinds"))
    ladder = _normalize_kinds(raw.get("fallback_ladder"))
    ents = _normalize_str_list(
        raw.get("primary_entities") or raw.get("must_show"), limit=6
    )
    must = _normalize_str_list(raw.get("must_show") or ents, limit=6)
    queries = _normalize_str_list(raw.get("search_queries"), limit=4)
    if not queries and ents:
        queries = [ents[0]]
    try:
        conf = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        conf = 0.5
    dur = raw.get("duration_hint")
    try:
        duration_hint = float(dur) if dur is not None else None
    except (TypeError, ValueError):
        duration_hint = None
    return VisualBeat(
        index=index,
        scene_index=scene_index,
        spoken_span=str(raw.get("spoken_span") or "").strip()[:240],
        duration_hint=duration_hint,
        concept=str(raw.get("concept") or "").strip()[:80],
        narrative_role=str(raw.get("narrative_role") or "evidence").strip()[:32],
        primary_entities=ents,
        visual_intent=str(raw.get("visual_intent") or "").strip()[:400],
        preferred_media=preferred or ["stock_video", "stock_photo"],
        must_show=must,
        avoid=_normalize_str_list(raw.get("avoid"), limit=12),
        search_queries=queries,
        shot_type=str(raw.get("shot_type") or "insert").strip()[:32],
        motion=str(raw.get("motion") or "slow_push").strip()[:32],
        overlay_intent=str(raw.get("overlay_intent") or "none").strip()[:32],
        fallback_ladder=ladder,
        confidence=max(0.0, min(1.0, conf)),
        allow_ai_generation=bool(raw.get("allow_ai_generation")),
        visual_change=str(raw.get("visual_change") or "new_asset").strip()[:32]
        or "new_asset",
        audio_cue=str(raw.get("audio_cue") or "").strip()[:64],
        emphasis_cue=str(raw.get("emphasis_cue") or "").strip()[:64],
    )


def parse_hook_plan(raw: Any, *, topic: str = "", script: str = "") -> HookDirectorPlan:
    """Punch overlay + karaoke delay; never a long static paragraph."""
    if not isinstance(raw, dict):
        raw = {}
    text = str(raw.get("overlay_text") or "").strip()
    if not text:
        text = _default_hook_overlay(topic=topic, script=script)
    words = text.split()
    if len(words) > 6:
        text = " ".join(words[:6])
    try:
        hook_seconds = float(raw.get("hook_seconds", 1.8))
    except (TypeError, ValueError):
        hook_seconds = 1.8
    hook_seconds = max(1.0, min(2.8, hook_seconds))
    try:
        karaoke_start = float(raw.get("karaoke_start_seconds", 0.0))
    except (TypeError, ValueError):
        karaoke_start = 0.0
    # Phase 2.1: karaoke follows VO from t=0; hook punch uses separate ASS style/layout.
    karaoke_start = max(0.0, min(karaoke_start, 0.5))
    return HookDirectorPlan(
        overlay_text=text,
        hook_seconds=hook_seconds,
        karaoke_start_seconds=karaoke_start,
        hero_shot=str(raw.get("hero_shot") or "hero_closeup").strip()[:32],
        motion=str(raw.get("motion") or "slow_push").strip()[:32],
    )


def _default_hook_overlay(*, topic: str, script: str) -> str:
    # Prefer topic brand punch; fall back to first 6 script words.
    topic_words = (topic or "").strip().split()
    if topic_words:
        return " ".join(topic_words[:4])
    script_words = (script or "").strip().split()
    return " ".join(script_words[:6]) if script_words else "Watch this"


def parse_scene_plan_document(
    data: dict,
    scene_count: int,
    *,
    topic: str = "",
    script: str = "",
) -> ScenePlanDocument:
    """Validate/normalize planner JSON into ScenePlanDocument (pads/truncates)."""
    raw_scenes = data.get("scenes") if isinstance(data, dict) else None
    if not isinstance(raw_scenes, list):
        raw_scenes = []

    by_index: dict[int, dict] = {}
    for i, sc in enumerate(raw_scenes):
        if not isinstance(sc, dict):
            continue
        try:
            idx = int(sc.get("index", i))
        except (TypeError, ValueError):
            idx = i
        by_index[idx] = sc

    scenes: list[ScenePlan] = []
    for i in range(scene_count):
        sc = by_index.get(i) or (
            raw_scenes[i]
            if i < len(raw_scenes) and isinstance(raw_scenes[i], dict)
            else {}
        )
        backup = sc.get("backup_plan") if isinstance(sc.get("backup_plan"), dict) else {}
        kinds = _normalize_kinds(sc.get("preferred_kinds"))
        queries = _normalize_str_list(sc.get("search_queries"), limit=4)
        if not kinds:
            kinds = ["stock_video", "stock_photo"]
        if not queries:
            intent = str(sc.get("visual_intent") or "").strip()
            queries = [intent[:80]] if intent else [f"scene {i} cinematic detail"]
        must = _normalize_str_list(sc.get("must_show"), limit=6)
        required = _normalize_str_list(
            sc.get("required_entities") or sc.get("must_show"), limit=6
        )
        avoid = _normalize_str_list(sc.get("avoid"), limit=12)
        beats_raw = sc.get("visual_beats") or sc.get("beats")
        beats: list[VisualBeat] = []
        if isinstance(beats_raw, list):
            for bi, br in enumerate(beats_raw):
                if isinstance(br, dict):
                    beats.append(_parse_visual_beat(br, index=bi, scene_index=i))
        scene = ScenePlan(
            index=i,
            scene_type=str(sc.get("scene_type") or "atmosphere").strip()[:64],
            visual_intent=str(sc.get("visual_intent") or queries[0]).strip()[:400],
            preferred_kinds=kinds,
            search_queries=queries,
            backup_kinds=_normalize_kinds(backup.get("preferred_kinds")),
            backup_queries=_normalize_str_list(backup.get("search_queries"), limit=4),
            must_show=must,
            avoid=avoid,
            required_entities=required,
            allow_ai_generation=bool(sc.get("allow_ai_generation")),
            beats=beats,
        )
        if not scene.beats:
            scene.ensure_beats()
        # Inherit scene avoid onto beats that forgot avoid (Phase 1 gate).
        for b in scene.beats:
            if not b.avoid and avoid:
                b.avoid = list(avoid)
            if not b.must_show and (must or required):
                b.must_show = list(must or required)
            if not b.primary_entities and required:
                b.primary_entities = list(required)
        scenes.append(scene)

    hook = parse_hook_plan(
        data.get("hook") if isinstance(data, dict) else None,
        topic=topic,
        script=script,
    )
    # Align first beat with hook hero when present
    if scenes and scenes[0].beats:
        b0 = scenes[0].beats[0]
        if not b0.shot_type or b0.shot_type == "insert":
            b0.shot_type = hook.hero_shot
        b0.motion = hook.motion or b0.motion
        if b0.narrative_role == "evidence":
            b0.narrative_role = "hook"

    return ScenePlanDocument(scenes=scenes, hook=hook)


def _split_semantic_chunks(text: str) -> list[str]:
    """Split on sentence / clause boundaries — not fixed word counts."""
    text = (text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|(?<=;)\s+|(?<=—)\s+|(?<=–)\s+", text)
    chunks = [p.strip() for p in parts if p and p.strip()]
    return chunks or [text]


def _beat_from_chunk(
    chunk: str,
    *,
    index: int,
    scene_index: int,
    topic: str,
    base_avoid: list[str],
    entities: list[str],
) -> VisualBeat:
    low = chunk.lower()
    ents = [e for e in entities if e.lower() in low][:4]
    if not ents:
        from app.stock_media import extract_proper_phrases

        ents = extract_proper_phrases(chunk)[:3] or (
            [topic] if topic and topic.lower() in low else []
        )

    narrative = "evidence"
    shot = "insert"
    preferred = ["stock_video", "stock_photo"]
    intent = chunk[:200]
    concept = "detail"
    overlay = "none"
    queries: list[str] = []

    if scene_index == 0 and index == 0:
        narrative = "hook"
        shot = "hero_closeup"
        concept = "hero"
        preferred = ["stock_photo", "stock_video"]
    if ents:
        narrative = "entity_proof"
        concept = ents[0]
        queries = [ents[0], f"{ents[0]} {topic}".strip()]
        preferred = ["stock_photo", "stock_video"]  # archive/entity bias
        intent = f"Exact visual proof of {', '.join(ents)}"
    if _PERSON_RE.search(chunk) or any("wilsdorf" in e.lower() for e in ents):
        narrative = "entity_proof"
        concept = "founder_archive"
        shot = "archival"
        preferred = ["stock_photo", "stock_video"]
        queries = (ents[:1] or ["Hans Wilsdorf"]) + ["Hans Wilsdorf portrait archive"]
        intent = "Archive / real-world portrait of the named person — not generic businessman"
    if _ORG_RE.search(chunk):
        concept = "ownership"
        queries = queries or ["foundation ownership headquarters", topic]
        intent = "Foundation / ownership context visual"
    if _MONEY_RE.search(chunk):
        narrative = "money"
        concept = "finance"
        overlay = "number"
        preferred = ["stock_video", "stock_photo", "ai_image"]
        queries = ["luxury finance wealth billions", "gold vault money value"]
        intent = "Financial / value visualization for billions/wealth"
        shot = "graphic"
    if _PLACE_RE.search(chunk):
        narrative = "place"
        concept = "location"
        preferred = ["stock_photo", "stock_video"]
        m = _PLACE_RE.search(chunk)
        place = m.group(0) if m else "Switzerland"
        queries = [f"{place} cityscape", f"{place} landmark"]
        intent = f"Location visual: {place}"
    if _DOC_RE.search(chunk):
        narrative = "document"
        concept = "tax_document"
        preferred = ["stock_photo", "stock_video", "ai_image"]
        queries = [
            "legal tax documents paperwork",
            "corporate filing exemption documents",
        ]
        intent = "Document / tax / legal mechanism visual — not generic office filler"
        shot = "graphic"
        overlay = "punch_word"

    if not queries:
        queries = [chunk[:80], topic] if topic else [chunk[:80]]

    must = list(ents) or ([topic] if topic else [])
    from app.director_gate import hygienize_entities

    must = hygienize_entities(must) or ([topic] if topic else ["subject"])
    ents = hygienize_entities(list(ents) or list(must[:2]))
    return VisualBeat(
        index=index,
        scene_index=scene_index,
        spoken_span=chunk[:240],
        duration_hint=2.4 if shot == "hero_closeup" else 1.6,
        concept=concept,
        narrative_role=narrative,
        primary_entities=list(ents) or list(must[:2]),
        visual_intent=intent[:400],
        preferred_media=preferred,
        must_show=must,
        avoid=list(base_avoid),
        search_queries=queries[:4],
        shot_type=shot,
        motion="slow_push",
        overlay_intent=overlay,
        visual_change="new_asset",
        fallback_ladder=["stock_photo", "ai_image"]
        if narrative == "entity_proof"
        else ["stock_video", "stock_photo"],
        confidence=0.55 if ents else 0.4,
        allow_ai_generation=(narrative in {"money", "document", "evidence"} and not ents),
        audio_cue="",
        emphasis_cue="number_hit" if overlay == "number" else "",
    )


def _heuristic_beats_for_scene(
    *,
    scene_index: int,
    intent: str,
    topic: str,
    script_chunk: str,
    base_avoid: list[str],
    entities: list[str],
) -> list[VisualBeat]:
    text = (script_chunk or intent or topic or "").strip()
    chunks = _split_semantic_chunks(text)
    # Cap: prefer 1–3 beats per scene (semantic), not word-count spam.
    if len(chunks) > 3:
        # Merge tiny tails into previous when over-segmented
        merged: list[str] = []
        for c in chunks:
            if merged and len(c.split()) < 4:
                merged[-1] = f"{merged[-1]} {c}".strip()
            else:
                merged.append(c)
        chunks = merged[:3]
    if not chunks:
        chunks = [intent or topic or "scene"]
    beats = [
        _beat_from_chunk(
            c,
            index=i,
            scene_index=scene_index,
            topic=topic,
            base_avoid=base_avoid,
            entities=entities,
        )
        for i, c in enumerate(chunks)
    ]
    # Same entity across consecutive beats → visual change without new download.
    for i in range(1, len(beats)):
        prev_e = {e.lower() for e in beats[i - 1].primary_entities}
        cur_e = {e.lower() for e in beats[i].primary_entities}
        if prev_e and cur_e and (prev_e & cur_e):
            beats[i].visual_change = "punch_in"
            beats[i].motion = "punch_in"
            beats[i].audio_cue = beats[i].audio_cue or "whoosh_soft"
    return beats


def _heuristic_plan(
    *,
    scene_count: int,
    topic: str,
    script: str,
    scene_stock_queries: list | None,
    visual_prompts: list | None,
    visual_keywords: list | None,
) -> ScenePlanDocument:
    """Offline fallback if LLM plan fails — entity-first beats + safety nets."""
    from app.director_gate import DEFAULT_FORBIDDEN_CONCEPTS
    from app.stock_media import extract_proper_phrases, resolve_scene_queries, topic_anchor_terms

    queries = resolve_scene_queries(
        scene_count=scene_count,
        topic=topic,
        script=script,
        scene_stock_queries=scene_stock_queries,
        visual_prompts=visual_prompts or [],
        visual_keywords=visual_keywords,
    )
    prompts = list(visual_prompts or [])
    entities = extract_proper_phrases(f"{topic}. {script}")[:8]
    if not entities:
        entities = topic_anchor_terms(topic, max_terms=4)
    base_avoid = sorted(DEFAULT_FORBIDDEN_CONCEPTS)[:24]
    script_chunks = _split_semantic_chunks(script)
    # Distribute script chunks across scenes without fixed word chops.
    if not script_chunks:
        script_chunks = [script or topic]
    scenes: list[ScenePlan] = []
    for i in range(scene_count):
        q = queries[i] if i < len(queries) else topic
        intent = prompts[i] if i < len(prompts) else q
        chunk = (
            script_chunks[i]
            if i < len(script_chunks)
            else script_chunks[i % len(script_chunks)]
        )
        scene_entities = extract_proper_phrases(str(intent) + " " + chunk)[:4] or list(
            entities[:3]
        )
        if i % 3 == 2:
            kinds = ["stock_photo", "stock_video", "ai_image"]
        else:
            kinds = ["stock_video", "stock_photo"]
        beats = _heuristic_beats_for_scene(
            scene_index=i,
            intent=str(intent),
            topic=topic,
            script_chunk=chunk,
            base_avoid=base_avoid,
            entities=list(entities),
        )
        scenes.append(
            ScenePlan(
                index=i,
                scene_type="hook" if i == 0 else "evidence",
                visual_intent=str(intent)[:400],
                preferred_kinds=kinds,
                search_queries=[q, topic]
                if topic and topic.lower() not in q.lower()
                else [q],
                backup_kinds=["stock_photo", "ai_image"],
                backup_queries=[topic] if topic else [],
                must_show=list(scene_entities) or ([topic] if topic else ["subject"]),
                required_entities=list(scene_entities) or ([topic] if topic else []),
                avoid=list(base_avoid),
                allow_ai_generation=(i % 3 == 2) or bool(scene_entities),
                beats=beats,
            )
        )
    hook = parse_hook_plan({}, topic=topic, script=script)
    return ScenePlanDocument(scenes=scenes, hook=hook)


def plan_scenes(
    *,
    scene_count: int,
    topic: str,
    script: str,
    api_key: str,
    scene_stock_queries: list | None = None,
    visual_prompts: list | None = None,
    visual_keywords: list | None = None,
    concrete_nouns: list | None = None,
) -> ScenePlanDocument:
    """One batch creative storyboard. Model string comes from env waterfall → AI router."""
    if scene_count < 1:
        return ScenePlanDocument(scenes=[])

    user_payload = {
        "topic": topic,
        "scene_count": scene_count,
        "script": script,
        "scene_stock_queries": scene_stock_queries or [],
        "visual_prompts": (visual_prompts or [])[:scene_count],
        "visual_keywords": visual_keywords or [],
        "concrete_nouns": concrete_nouns or [],
        "style": "dark-luxury mini documentary — fast-paced, premium, cinematic",
    }
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM},
        {
            "role": "user",
            "content": (
                f"Produce a visual storyboard for exactly {scene_count} scenes "
                f"with semantic visual_beats (not fixed word chops).\n"
                f"Context JSON:\n{json.dumps(user_payload, ensure_ascii=False)}"
            ),
        },
    ]

    if not (api_key or "").strip():
        logger.warning("Director planner: empty API key — heuristic storyboard")
        return _heuristic_plan(
            scene_count=scene_count,
            topic=topic,
            script=script,
            scene_stock_queries=scene_stock_queries,
            visual_prompts=visual_prompts,
            visual_keywords=visual_keywords,
        )

    try:
        raw, used_model = _call_llm_with_fallback(messages, api_key)
        data = _parse_director_json(raw)
        doc = parse_scene_plan_document(
            data, scene_count, topic=topic, script=script
        )
        logger.info(
            "Director storyboard ok model=%s scenes=%s beats=%s (gateway/env, not Director)",
            used_model,
            scene_count,
            len(doc.all_beats()),
        )
        return doc
    except Exception as exc:
        logger.warning("Director planner LLM failed (%s); heuristic storyboard", exc)
        return _heuristic_plan(
            scene_count=scene_count,
            topic=topic,
            script=script,
            scene_stock_queries=scene_stock_queries,
            visual_prompts=visual_prompts,
            visual_keywords=visual_keywords,
        )


def _parse_director_json(raw: str) -> dict:
    """Parse Director storyboard JSON — must NOT require script_gen 'script' key."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()
    # Find outermost JSON object
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Director response missing JSON object")
    data = json.loads(text[start : end + 1])
    if not isinstance(data, dict):
        raise ValueError("Director JSON root must be object")
    if "scenes" not in data and "hook" not in data:
        raise ValueError("Director JSON missing scenes/hook")
    return data


def score_candidate_text(
    blob: str,
    *,
    queries: list[str],
    must_show: list[str] | None = None,
    avoid: list[str] | None = None,
) -> float:
    """Deterministic relevance; reuses stock scoring ideas without network."""
    from app.stock_media import _blob_has_irrelevant, _score_stock_candidate

    text = blob or ""
    for token in avoid or []:
        if token and token.lower() in text.lower():
            return -10.0
    if _blob_has_irrelevant(text):
        return -5.0
    best = 0.0
    for q in queries or [""]:
        best = max(best, _score_stock_candidate(text, q))
    must_hits = 0
    must = [m for m in (must_show or []) if m]
    if must:
        low = text.lower()
        must_hits = sum(1 for m in must if m.lower() in low)
        best += 0.15 * must_hits
    return best
