"""AI Director V2 Phase 2 — visual beats, hook director, entity-first intents."""

from app.director_gate import (
    AssetCandidate,
    evaluate_asset,
    scene_need_from_plan,
)
from app.director_planner import (
    parse_hook_plan,
    parse_scene_plan_document,
    plan_scenes,
)
from app.director_types import VisualBeat
from app.subtitles import write_ass


ROLEX_SCRIPT = (
    "Rolex is not owned by a family dynasty. "
    "Hans Wilsdorf built the brand, then left it to a Foundation. "
    "That Foundation funnels billions back into Switzerland."
)


def test_scene_can_contain_multiple_visual_beats():
    raw = {
        "hook": {"overlay_text": "Rolex owns itself", "hook_seconds": 1.6},
        "scenes": [
            {
                "index": 0,
                "scene_type": "hook",
                "visual_intent": "Rolex crown + ownership reveal",
                "preferred_kinds": ["stock_photo", "stock_video"],
                "search_queries": ["Rolex crown logo"],
                "must_show": ["Rolex"],
                "visual_beats": [
                    {
                        "spoken_span": "Rolex is not owned",
                        "concept": "Rolex",
                        "narrative_role": "hook",
                        "primary_entities": ["Rolex"],
                        "visual_intent": "Rolex product / crown hero",
                        "preferred_media": ["stock_photo"],
                        "must_show": ["Rolex"],
                        "search_queries": ["Rolex crown watch"],
                        "shot_type": "hero_closeup",
                        "confidence": 0.9,
                    },
                    {
                        "spoken_span": "Hans Wilsdorf built the brand",
                        "concept": "founder",
                        "narrative_role": "entity_proof",
                        "primary_entities": ["Hans Wilsdorf"],
                        "visual_intent": "Archive portrait of Hans Wilsdorf",
                        "preferred_media": ["archive_photo", "stock_photo"],
                        "must_show": ["Hans Wilsdorf"],
                        "search_queries": ["Hans Wilsdorf portrait"],
                        "shot_type": "archival",
                        "confidence": 0.85,
                    },
                ],
            }
        ],
    }
    doc = parse_scene_plan_document(raw, scene_count=1, topic="Rolex", script=ROLEX_SCRIPT)
    assert len(doc.scenes) == 1
    beats = doc.scenes[0].beats
    assert len(beats) >= 2
    assert beats[0].primary_entities == ["Rolex"]
    assert beats[1].primary_entities == ["Hans Wilsdorf"]
    # archive_photo alias → stock_photo for retrieval
    assert "stock_photo" in beats[1].kind_chain()


def test_rolex_entity_beat_is_entity_aware():
    doc = plan_scenes(
        scene_count=2,
        topic="Rolex",
        script=ROLEX_SCRIPT,
        api_key="",
        visual_prompts=["Rolex crown close-up", "Hans Wilsdorf Foundation"],
        visual_keywords=["Rolex", "Wilsdorf"],
    )
    all_beats = doc.all_beats()
    assert len(all_beats) >= 2
    rolexish = [
        b
        for b in all_beats
        if any("rolex" in e.lower() for e in (b.primary_entities + b.must_show + b.search_queries))
    ]
    assert rolexish, "expected at least one Rolex entity-aware beat"
    q0 = rolexish[0].entity_first_queries(topic="Rolex")
    assert q0[0].lower().startswith("rolex") or "rolex" in q0[0].lower()


def test_hans_wilsdorf_beat_archive_oriented():
    doc = plan_scenes(
        scene_count=3,
        topic="Rolex",
        script=ROLEX_SCRIPT,
        api_key="",
        visual_prompts=[
            "Rolex watch",
            "Hans Wilsdorf founded Rolex then left ownership to a Foundation.",
            "billions in Switzerland",
        ],
    )
    wilsdorf_beats = [
        b
        for b in doc.all_beats()
        if "wilsdorf" in (b.spoken_span + b.visual_intent + " ".join(b.primary_entities)).lower()
        or "wilsdorf" in " ".join(b.search_queries).lower()
    ]
    assert wilsdorf_beats
    b = wilsdorf_beats[0]
    assert b.shot_type in {"archival", "insert", "hero_closeup"}
    assert "businessman" not in " ".join(b.search_queries).lower()
    blob = " ".join(b.search_queries + [b.visual_intent]).lower()
    assert "wilsdorf" in blob or "archive" in blob or "portrait" in blob


def test_billions_money_visual_intent():
    doc = plan_scenes(
        scene_count=2,
        topic="Rolex",
        script="The Foundation funnels billions back into the empire.",
        api_key="",
        visual_prompts=["Foundation ownership", "billions of dollars wealth"],
    )
    money = [b for b in doc.all_beats() if b.narrative_role == "money" or b.concept == "finance"]
    if not money:
        money = [
            b
            for b in doc.all_beats()
            if "billion" in b.spoken_span.lower()
            or "finance" in b.visual_intent.lower()
            or "wealth" in " ".join(b.search_queries).lower()
        ]
    assert money
    assert any(
        any(tok in " ".join(b.search_queries + [b.visual_intent]).lower() for tok in ("finance", "wealth", "billion", "gold", "vault", "money"))
        for b in money
    )


def test_hook_director_special_hero_plan():
    hook = parse_hook_plan(
        {
            "overlay_text": "Rolex owns itself completely forever and always somehow",
            "hook_seconds": 1.7,
            "hero_shot": "hero_closeup",
            "motion": "slow_push",
        },
        topic="Rolex",
        script=ROLEX_SCRIPT,
    )
    assert len(hook.overlay_text.split()) <= 6
    assert hook.hero_shot == "hero_closeup"
    # Phase 2.1: karaoke not delayed behind hook
    assert hook.karaoke_start_seconds <= 0.5


def test_hook_overlay_subtitle_conflict_prevention(tmp_path):
    """Phase 2.1: karaoke starts with VO (t=0); hook uses separate style/layout."""
    # edge-tts ticks: 10_000_000 = 1 second
    boundaries = [
        {"text": "Rolex", "offset": 0, "duration": 5_000_000},
        {"text": "owns", "offset": 5_000_000, "duration": 4_000_000},
        {"text": "itself", "offset": 9_000_000, "duration": 5_000_000},
        {"text": "today", "offset": 20_000_000, "duration": 4_000_000},
    ]
    out = tmp_path / "hook.ass"
    write_ass(
        boundaries,
        str(out),
        words_per_cue=2,
        highlight=True,
        # Distinct punch (not a VO duplicate) — Phase 2.2 skips exact VO echo.
        hook_text="ZERO TAX EMPIRE",
        hook_seconds=1.5,
        karaoke_start_seconds=0.0,
        hook_max_words=6,
    )
    text = out.read_text(encoding="utf-8")
    dialogue_lines = [ln for ln in text.splitlines() if ln.startswith("Dialogue:")]
    hook_lines = [ln for ln in dialogue_lines if ",Hook,," in ln]
    default_lines = [ln for ln in dialogue_lines if ",Default,," in ln]
    assert len(hook_lines) == 1
    assert r"\fad(" in hook_lines[0]
    assert default_lines, "karaoke must start from VO beginning"
    # First default cue should start at/near 0 — not delayed to 1.8s
    first_default = default_lines[0]
    start = first_default.split(",")[1]
    assert start.startswith("0:00:00.")


def test_bakery_still_rejected_for_visual_beat_need():
    need = scene_need_from_plan(
        queries=["Hans Wilsdorf Foundation Rolex"],
        must_show=["Hans Wilsdorf", "Rolex"],
        required_entities=["Hans Wilsdorf", "Rolex"],
        avoid=[],
        scene_type="entity_proof",
        visual_intent="Archive proof of Hans Wilsdorf Foundation ownership",
    )
    bakery = AssetCandidate(
        provider="pexels",
        asset_id="999",
        download_url="https://example.com/bakery.mp4",
        title="Fresh cookies at the bakery counter",
        tags="bakery, cookie, pastry, food, dessert",
        description="Pastry chef icing a cake",
        url="https://www.pexels.com/video/bakery-cookies-pastry-999/",
        user="FoodStudio",
    )
    gate = evaluate_asset(bakery, need)
    assert gate.accepted is False
    assert gate.reason == "forbidden_concept"


def test_llm_storyboard_failure_safe_heuristic_fallback():
    doc = plan_scenes(
        scene_count=3,
        topic="Rolex",
        script=ROLEX_SCRIPT,
        api_key="",  # forces heuristic
    )
    assert len(doc.scenes) == 3
    assert doc.hook is not None
    assert doc.hook.overlay_text
    for sc in doc.scenes:
        assert sc.must_show
        assert sc.avoid
        assert sc.ensure_beats()
        assert any("bakery" in a.lower() or "cookie" in a.lower() for a in sc.avoid)


def test_visual_beat_candidates_pass_phase1_gate():
    """Entity-first queries still evaluate asset metadata, not the query string."""
    beat = VisualBeat(
        index=0,
        scene_index=0,
        spoken_span="Hans Wilsdorf Foundation",
        primary_entities=["Hans Wilsdorf", "Rolex"],
        must_show=["Hans Wilsdorf", "Rolex"],
        avoid=["bakery", "cookie"],
        search_queries=["Hans Wilsdorf Rolex foundation"],
        visual_intent="Archive Hans Wilsdorf",
        narrative_role="entity_proof",
    )
    need = scene_need_from_plan(
        queries=beat.entity_first_queries(topic="Rolex"),
        must_show=beat.must_show,
        avoid=beat.avoid,
        required_entities=beat.primary_entities,
        scene_type=beat.narrative_role,
        visual_intent=beat.visual_intent,
    )
    empty = AssetCandidate(
        provider="pexels",
        asset_id="1",
        download_url="https://example.com/x.mp4",
        title="",
        tags="",
        description="",
        url="",
        user="",
    )
    assert evaluate_asset(empty, need).accepted is False
    good = AssetCandidate(
        provider="pexels",
        asset_id="42",
        download_url="https://example.com/rolex.mp4",
        title="Rolex watchmaking atelier in Geneva",
        tags="Rolex, Hans Wilsdorf, watchmaking, Geneva",
        description="Hans Wilsdorf era Rolex workshop",
        url="https://www.pexels.com/video/rolex-geneva-42/",
        user="WatchDocs",
    )
    assert evaluate_asset(good, need).accepted is True


def test_entity_first_query_ladder_order():
    beat = VisualBeat(
        index=0,
        primary_entities=["Hans Wilsdorf"],
        concept="founder",
        search_queries=["swiss watchmaker workshop"],
        visual_intent="portrait archive",
    )
    qs = beat.entity_first_queries(topic="Rolex")
    # Phase 2.2: person entity leads with archive/portrait specificity queries.
    assert qs[0].lower().startswith("hans wilsdorf")
    assert any("portrait" in q.lower() for q in qs[:3])
    assert any("swiss watchmaker" in q.lower() for q in qs)


def test_micro_pacing_duration_prefers_short_generic_allows_hero_long():
    generic = VisualBeat(
        index=1,
        narrative_role="evidence",
        primary_entities=[],
        duration_hint=5.0,
    )
    assert generic.resolve_duration_hint() <= 2.0
    hero = VisualBeat(
        index=0,
        narrative_role="hook",
        shot_type="hero_closeup",
        primary_entities=["Rolex"],
        duration_hint=3.2,
    )
    assert hero.resolve_duration_hint() >= 2.4
    assert hero.resolve_duration_hint() <= 4.0


def test_word_to_visual_skeleton_is_loggable():
    beat = VisualBeat(
        index=0,
        spoken_span="Hans Wilsdorf built the brand",
        concept="founder",
        primary_entities=["Hans Wilsdorf"],
        visual_intent="Archive portrait",
        search_queries=["Hans Wilsdorf portrait"],
        audio_cue="whoosh_soft",
        emphasis_cue="",
    )
    chain = beat.word_to_visual_skeleton()
    assert chain["spoken_span"].startswith("Hans Wilsdorf")
    assert chain["entities"] == ["Hans Wilsdorf"]
    assert chain["visual_intent"]
    assert chain["audio_cue"] == "whoosh_soft"


def test_same_entity_consecutive_beats_prefer_punch_in_not_new_download():
    doc = plan_scenes(
        scene_count=1,
        topic="Rolex",
        script="Rolex crowns the wrist. Rolex keeps the crown.",
        api_key="",
        visual_prompts=["Rolex crown macro Rolex crown detail"],
    )
    beats = doc.scenes[0].ensure_beats()
    if len(beats) >= 2:
        same = (
            set(e.lower() for e in beats[0].primary_entities)
            & set(e.lower() for e in beats[1].primary_entities)
        )
        if same:
            assert beats[1].wants_reuse_visual_change()


def test_tax_document_concept_maps_to_document_intent():
    doc = plan_scenes(
        scene_count=1,
        topic="Rolex",
        script="Rolex enjoys a remarkable tax exemption on its Swiss documents.",
        api_key="",
        visual_prompts=["Rolex tax exemption legal documents"],
    )
    beats = doc.all_beats()
    docish = [
        b
        for b in beats
        if b.narrative_role == "document"
        or "tax" in b.concept.lower()
        or "document" in " ".join(b.search_queries).lower()
        or "tax" in b.visual_intent.lower()
    ]
    assert docish


def test_audio_cue_fields_parsed_but_do_not_require_audio_pipeline():
    raw = {
        "scenes": [
            {
                "index": 0,
                "visual_intent": "Rolex",
                "preferred_kinds": ["stock_photo"],
                "search_queries": ["Rolex"],
                "visual_beats": [
                    {
                        "spoken_span": "Rolex",
                        "primary_entities": ["Rolex"],
                        "search_queries": ["Rolex"],
                        "audio_cue": "whoosh_soft",
                        "emphasis_cue": "brand_hit",
                    }
                ],
            }
        ]
    }
    doc = parse_scene_plan_document(raw, scene_count=1, topic="Rolex")
    b = doc.scenes[0].beats[0]
    assert b.audio_cue == "whoosh_soft"
    assert b.emphasis_cue == "brand_hit"
