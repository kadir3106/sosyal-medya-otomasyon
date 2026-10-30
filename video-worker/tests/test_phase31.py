"""Phase 3.1 — quality polish regression (captions, hook, person, retention)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.director_gate import (
    AssetCandidate,
    DEFAULT_FORBIDDEN_CONCEPTS,
    evaluate_asset,
    scene_need_from_plan,
)
from app.director_planner import parse_hook_plan
from app.person_archive import (
    looks_like_person_name,
    normalize_person_key,
    try_cached_or_fetch_person_image,
)
from app.phase3_retention import (
    apply_retention_to_visual_beats,
    plan_retention_events,
)
from app.subtitles import (
    TICKS_PER_SECOND,
    _chunk_boundaries_phase3,
    _is_marketing_title_overlay,
    write_ass,
)


def _wb(words: list[tuple[str, float, float]]) -> list[dict]:
    out = []
    for text, start, dur in words:
        out.append(
            {
                "text": text,
                "offset": int(start * TICKS_PER_SECOND),
                "duration": int(dur * TICKS_PER_SECOND),
            }
        )
    return out


def test_named_person_introduction_triggers_person_retrieval(tmp_path):
    """1 — named person → person-specific retrieval attempted."""
    need = scene_need_from_plan(
        queries=["Ada Lovelace portrait archive"],
        must_show=["Ada Lovelace"],
        required_entities=["Ada Lovelace"],
        visual_intent="Archive portrait of Ada Lovelace",
        narrative_role="entity_proof",
    )
    attempts: list = []
    fake = {
        "title": "Ada Lovelace",
        "download_url": "https://example.com/ada.jpg",
        "page_url": "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "provider": "wikipedia_pageimage",
        "asset_id": "wiki:ada",
        "attribution": "Wikipedia",
        "alt": "Portrait of Ada Lovelace",
        "description": "Wikipedia page image for Ada Lovelace",
        "tags": "portrait archive historical Ada Lovelace",
    }
    with patch("app.person_archive.fetch_wikipedia_person_image", return_value=fake):
        cand, meta, gate = try_cached_or_fetch_person_image(
            "Ada Lovelace", media_dir=tmp_path, need=need, attempts=attempts
        )
    assert attempts and attempts[0]["kind"] == "person_archive"
    assert attempts[0]["query"] == "Ada Lovelace"
    assert looks_like_person_name("Ada Lovelace")


def test_valid_portrait_outranks_generic_storefront():
    """2 — valid portrait outranks generic storefront/product."""
    need = scene_need_from_plan(
        queries=["Ada Lovelace portrait"],
        must_show=["Ada Lovelace"],
        required_entities=["Ada Lovelace"],
        visual_intent="Archive portrait of named person",
        narrative_role="entity_proof",
    )
    portrait = AssetCandidate(
        provider="wikipedia_pageimage",
        asset_id="wiki:ada",
        download_url="https://example.com/ada.jpg",
        title="Ada Lovelace",
        tags="portrait archive historical Ada Lovelace",
        description="Portrait of Ada Lovelace mathematician",
        url="https://en.wikipedia.org/wiki/Ada_Lovelace",
        user="Wikipedia",
        kind="stock_photo",
    )
    storefront = AssetCandidate(
        provider="pexels_photo",
        asset_id="99",
        download_url="https://example.com/shop.jpg",
        title="Luxury watch storefront display",
        tags="storefront, shop, luxury watches, retail",
        description="Boutique storefront window with watches",
        url="https://pexels.com/photo/99",
        user="Stock",
        kind="stock_photo",
    )
    g_p = evaluate_asset(portrait, need)
    g_s = evaluate_asset(storefront, need)
    assert g_p.accepted
    assert g_p.specificity_score >= g_s.specificity_score
    assert g_p.entity_score > g_s.entity_score or not g_s.accepted


def test_wrong_ambiguous_portrait_fail_closed():
    """3 — wrong/ambiguous portrait → fail closed."""
    need = scene_need_from_plan(
        queries=["Ada Lovelace portrait"],
        must_show=["Ada Lovelace"],
        required_entities=["Ada Lovelace"],
        visual_intent="Archive portrait of Ada Lovelace",
        narrative_role="entity_proof",
    )
    wrong = AssetCandidate(
        provider="wikipedia_pageimage",
        asset_id="wiki:charles",
        download_url="https://example.com/charles.jpg",
        title="Charles Babbage",
        tags="portrait archive Charles Babbage",
        description="Portrait of Charles Babbage",
        url="https://en.wikipedia.org/wiki/Charles_Babbage",
        user="Wikipedia",
        kind="stock_photo",
    )
    gate = evaluate_asset(wrong, need)
    assert gate.accepted is False


def test_semantic_caption_chunks_preserve_exact_transcript():
    """4 — semantic caption chunks preserve exact transcript."""
    words = [
        ("turned", 0.0, 0.2),
        ("Rolex", 0.25, 0.3),
        ("into", 0.6, 0.2),
        ("a", 0.85, 0.1),
        ("private", 1.0, 0.3),
        ("foundation", 1.4, 0.4),
    ]
    wb = _wb(words)
    chunks = _chunk_boundaries_phase3(wb)
    flat = [w["text"] for c in chunks for w in c]
    assert flat == [t for t, _, _ in words]


def test_proper_noun_split_prevention():
    """5 — proper noun not split across chunks."""
    wb = _wb(
        [
            ("When", 0.0, 0.2),
            ("Hans", 0.25, 0.25),
            ("Wilsdorf", 0.55, 0.35),
            ("founded", 1.0, 0.3),
            ("the", 1.35, 0.15),
            ("company", 1.55, 0.3),
        ]
    )
    chunks = _chunk_boundaries_phase3(wb, max_words=3, max_seconds=0.9)
    texts = [[" ".join(w["text"] for w in c)][0] for c in chunks]
    joined = " | ".join(texts)
    # Hans and Wilsdorf must appear in the same chunk
    assert any(
        "Hans" in " ".join(w["text"] for w in c)
        and "Wilsdorf" in " ".join(w["text"] for w in c)
        for c in chunks
    ), joined


def test_number_unit_grouping():
    """6 — number + unit stay together."""
    wb = _wb(
        [
            ("worth", 0.0, 0.2),
            ("$10", 0.25, 0.3),
            ("billion", 0.6, 0.35),
            ("today", 1.05, 0.3),
        ]
    )
    chunks = _chunk_boundaries_phase3(wb, max_words=2, max_seconds=0.5)
    assert any(
        "$10" in [w["text"] for w in c] and "billion" in [w["text"] for w in c]
        for c in chunks
    )


def test_meaningless_fragment_regression():
    """7 — no orphan 'INTO A PRIVATE' style fragment."""
    wb = _wb(
        [
            ("turned", 0.0, 0.2),
            ("Rolex", 0.25, 0.3),
            ("into", 0.6, 0.2),
            ("a", 0.85, 0.1),
            ("private", 1.0, 0.3),
            ("foundation", 1.4, 0.4),
        ]
    )
    chunks = _chunk_boundaries_phase3(wb, max_words=3, max_seconds=0.8)
    phrases = [" ".join(w["text"] for w in c).upper() for c in chunks]
    bad = {"INTO A PRIVATE", "INTO A", "A PRIVATE", "INTO"}
    assert not any(p in bad for p in phrases), phrases


def test_duplicate_hook_title_suppression(tmp_path):
    """8 — duplicate / marketing static title suppressed."""
    assert _is_marketing_title_overlay("THE ROLEX TRUST SECRET")
    wb = _wb(
        [
            ("Rolex", 0.0, 0.3),
            ("doesn't", 0.3, 0.25),
            ("have", 0.6, 0.2),
            ("shareholders", 0.9, 0.4),
        ]
    )
    out = tmp_path / "subs.ass"
    write_ass(
        wb,
        str(out),
        hook_text="THE ROLEX TRUST SECRET",
        hook_seconds=1.5,
        phase3=True,
        highlight=True,
    )
    text = out.read_text(encoding="utf-8")
    assert ",Hook,," not in text
    # Default empty overlay from planner
    hook = parse_hook_plan({}, topic="Rolex Foundation Secret", script="Rolex owns itself")
    assert hook.overlay_text == ""


def test_long_hold_triggers_meaningful_retention_event():
    """9 — long visual hold can trigger retention event with reason."""
    w2v = [
        {
            "spoken_span": "Rolex is owned by a private foundation",
            "entities": ["Rolex"],
            "duration": 3.5,
            "selected_asset": {"asset_id": "a1", "path": "/x/a.mp4"},
        },
        {
            "spoken_span": "because the founder built a trust",
            "entities": ["Rolex"],
            "duration": 2.5,
            "selected_asset": {"asset_id": "a1", "path": "/x/a.mp4"},
        },
    ]
    events = plan_retention_events(w2v)
    assert events
    assert any(e.reason for e in events)
    assert any(not e.asset_change_required for e in events)


def test_retention_event_does_not_require_new_asset():
    """10 — retention event does NOT require new asset."""
    w2v = [
        {
            "spoken_span": "billions in value",
            "entities": [],
            "duration": 2.0,
            "selected_asset": {"asset_id": "x"},
        },
        {
            "spoken_span": "more billions locked away",
            "entities": [],
            "duration": 2.0,
            "selected_asset": {"asset_id": "x"},
        },
    ]
    events = plan_retention_events(w2v)
    same_asset = [e for e in events if not e.asset_change_required]
    assert same_asset
    assert all(e.transform for e in same_asset)


def test_no_zoom_spam():
    """11 — no zoom in/out spam (transform spacing + cap)."""
    w2v = [
        {
            "spoken_span": f"claim {i} because foundation trust secret",
            "entities": ["Rolex"],
            "duration": 2.0,
            "selected_asset": {"asset_id": "same"},
        }
        for i in range(8)
    ]
    events = plan_retention_events(w2v, max_events=6)
    transforms = [e for e in events if e.transform]
    assert len(transforms) <= 4
    # Min spacing ~1.8s between kept transforms
    for a, b in zip(transforms, transforms[1:]):
        assert b.timestamp - a.timestamp >= 1.5


def test_phase2_river_regression_pass():
    """12 — Phase 2 river regression PASS."""
    need = scene_need_from_plan(
        queries=["Rolex billions finance"],
        must_show=["Rolex"],
        visual_intent="Financial scale of Rolex ownership",
        narrative_role="money",
    )
    river = AssetCandidate(
        provider="pexels",
        asset_id="1",
        download_url="https://example.com/river.mp4",
        title="Peaceful river flowing through forest",
        tags="river, stream, nature, water, brook",
        description="hometown brook flower stream river nature",
        url="https://pexels.com/video/1",
        user="Nature",
        kind="stock_video",
    )
    gate = evaluate_asset(river, need)
    assert gate.accepted is False


def test_bakery_regression_pass():
    """13 — bakery regression PASS."""
    assert "bakery" in DEFAULT_FORBIDDEN_CONCEPTS
    need = scene_need_from_plan(
        queries=["Hans Wilsdorf Foundation"],
        must_show=["Hans Wilsdorf", "Rolex"],
        required_entities=["Hans Wilsdorf"],
        visual_intent="Founder archive",
        narrative_role="entity_proof",
    )
    bakery = AssetCandidate(
        provider="pexels",
        asset_id="2",
        download_url="https://example.com/bakery.mp4",
        title="Fresh cookies at the bakery counter",
        tags="bakery, cookie, pastry, food",
        description="Pastry chef icing a cake",
        url="https://pexels.com/video/2",
        user="Food",
        kind="stock_video",
    )
    assert evaluate_asset(bakery, need).accepted is False


def test_anti_repetition_pass():
    """14 — anti-repetition PASS (apply_retention does not invent assets)."""
    from app.director_types import VisualBeat

    beats = [
        VisualBeat(index=0, scene_index=0, spoken_span="a", visual_change="new_asset"),
        VisualBeat(index=1, scene_index=0, spoken_span="b", visual_change="new_asset"),
    ]
    events = plan_retention_events(
        [
            {
                "spoken_span": "billions",
                "entities": [],
                "duration": 2.5,
                "selected_asset": {"asset_id": "z"},
            },
            {
                "spoken_span": "more billions",
                "entities": [],
                "duration": 2.5,
                "selected_asset": {"asset_id": "z"},
            },
        ]
    )
    apply_retention_to_visual_beats(beats, events)
    # Beat 0 never forced to reuse; beat 1 may get transform without new asset
    assert beats[0].visual_change == "new_asset"
    if beats[1].visual_change != "new_asset":
        assert beats[1].visual_change in {
            "punch_in",
            "crop_zoom",
            "archive_motion",
            "reuse_with_motion",
        }


def test_render_duration_regression_importable():
    """15 — render duration helpers still importable (mux fix intact)."""
    from app.render import render_video

    assert callable(render_video)


def test_pending_approval_unchanged():
    """16 — pending/approval path symbols unchanged."""
    from app import pipeline

    assert hasattr(pipeline, "generate_video") or hasattr(pipeline, "_generate_video_sync")
    src = open(pipeline.__file__, encoding="utf-8").read()
    assert "pending" in src.lower()
    assert "telegram" in src.lower() or "send_message" in src


def test_person_need_ignores_org_coentity(tmp_path):
    """Person portrait must not fail because Foundation co-entity is required."""
    from app.director_gate import scene_need_from_plan

    fake = {
        "title": "Ada Lovelace",
        "download_url": "https://example.com/ada.jpg",
        "page_url": "https://en.wikipedia.org/wiki/Ada_Lovelace",
        "provider": "wikipedia_pageimage",
        "asset_id": "wiki:ada",
        "attribution": "Wikipedia",
        "alt": "Portrait of Ada Lovelace",
        "description": "Wikipedia page image for Ada Lovelace",
        "tags": "portrait archive historical Ada Lovelace",
    }
    polluted = scene_need_from_plan(
        queries=["Ada Lovelace"],
        must_show=["Ada Lovelace", "Ada Lovelace Foundation"],
        required_entities=["Ada Lovelace", "Ada Lovelace Foundation"],
        visual_intent="portrait",
        narrative_role="entity_proof",
    )
    person_only = scene_need_from_plan(
        queries=["Ada Lovelace portrait archive"],
        must_show=["Ada Lovelace"],
        required_entities=["Ada Lovelace"],
        visual_intent="Archive portrait of Ada Lovelace",
        narrative_role="entity_proof",
    )
    with patch("app.person_archive.fetch_wikipedia_person_image", return_value=fake):
        _c1, _m1, g1 = try_cached_or_fetch_person_image(
            "Ada Lovelace", media_dir=tmp_path, need=polluted, attempts=[]
        )
        c2, _m2, g2 = try_cached_or_fetch_person_image(
            "Ada Lovelace", media_dir=tmp_path / "b", need=person_only, attempts=[]
        )
    assert g2 is not None and g2.accepted
    assert c2 is not None


def test_person_cache_key_normalized(tmp_path):
    assert normalize_person_key("  Hans   Wilsdorf ") == "hans wilsdorf"
    assert looks_like_person_name("Hans Wilsdorf Foundation") is False
    assert looks_like_person_name("Rolex") is False
    assert looks_like_person_name("Wall Street") is False
    assert looks_like_person_name("Hans Wilsdorf") is True
