"""Phase 1 regression: asset gate — query ≠ asset; bakery must reject."""

from app.director_gate import (
    AssetCandidate,
    evaluate_asset,
    scene_need_from_plan,
)
from app.director_planner import plan_scenes


FOUNDATION_SCENE = (
    "The Hans Wilsdorf Foundation owns every share, funneling billions "
    "back into the Rolex empire."
)


def _foundation_need():
    return scene_need_from_plan(
        queries=["Rolex hans wilsdorf foundation"],
        must_show=["Hans Wilsdorf", "Rolex", "Foundation"],
        required_entities=["Hans Wilsdorf", "Rolex"],
        avoid=[],  # defaults still apply inside gate
        scene_type="evidence",
        visual_intent=FOUNDATION_SCENE,
    )


def test_bakery_cookie_metadata_must_reject_for_wilsdorf_scene():
    """Real acceptance pipeline — bakery metadata cannot pass Foundation scene."""
    need = _foundation_need()
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
    assert gate.forbidden_hit is not None
    foodish = {
        "bakery", "baker", "cookie", "cookies", "cake", "pastry", "pastries",
        "dessert", "food", "icing", "frosting", "dough", "cooking", "restaurant",
    }
    assert gate.forbidden_hit in foodish


def test_cooking_food_url_slug_must_reject():
    need = _foundation_need()
    cand = AssetCandidate(
        provider="pixabay",
        asset_id="1",
        download_url="https://cdn.example/x.mp4",
        title="",
        tags="",
        description="",
        url="https://pixabay.com/videos/cooking-kitchen-food-meal-123/",
        user="",
    )
    gate = evaluate_asset(cand, need)
    assert gate.accepted is False
    assert gate.reason == "forbidden_concept"


def test_query_text_alone_is_not_acceptance_proof():
    """Scoring the search query string must not accept — no asset metadata."""
    need = _foundation_need()
    # Empty metadata: even if query would self-score 1.0 under old bug.
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
    gate = evaluate_asset(empty, need)
    assert gate.accepted is False
    assert gate.reason == "no_asset_metadata"


def test_positive_rolex_watchmaking_geneva_can_accept():
    need = _foundation_need()
    good = AssetCandidate(
        provider="pexels",
        asset_id="42",
        download_url="https://example.com/rolex.mp4",
        title="Rolex watchmaking atelier in Geneva",
        tags="Rolex, Hans Wilsdorf, watchmaking, Geneva, luxury watch",
        description="Close-up of a Rolex movement on a Swiss watchmaker bench",
        url="https://www.pexels.com/video/rolex-geneva-watchmaking-42/",
        user="WatchDocs",
    )
    gate = evaluate_asset(good, need)
    assert gate.accepted is True
    assert gate.entity_score > 0
    assert gate.relevance_score >= 0.45


def test_generic_business_meeting_rejected_for_entity_scene():
    need = _foundation_need()
    generic = AssetCandidate(
        provider="pexels",
        asset_id="7",
        download_url="https://example.com/meet.mp4",
        title="Corporate business meeting handshake",
        tags="business, meeting, office, success, money",
        description="Teamwork presentation in conference room",
        url="https://www.pexels.com/video/business-meeting-handshake-7/",
        user="CorpStock",
    )
    gate = evaluate_asset(generic, need)
    assert gate.accepted is False
    assert gate.reason in {"missing_required_entities", "below_threshold"}


def test_heuristic_plan_never_empties_must_show_or_avoid():
    doc = plan_scenes(
        scene_count=3,
        topic="Rolex",
        script=FOUNDATION_SCENE,
        api_key="",
        scene_stock_queries=[{"query": "Rolex hans wilsdorf foundation", "mode": "generic"}],
        visual_prompts=["Hans Wilsdorf Foundation headquarters"],
        visual_keywords=["Rolex", "Wilsdorf"],
    )
    for sc in doc.scenes:
        assert sc.must_show, "heuristic must_show must not be empty"
        assert sc.avoid, "heuristic avoid must not be empty"
        assert any("bakery" in a.lower() or "cookie" in a.lower() for a in sc.avoid)
