"""Phase 2.1 regressions — entity hygiene + semantic gate (real evaluate_asset)."""

from app.director_gate import (
    AssetCandidate,
    entity_phrase_in_blob,
    evaluate_asset,
    hygienize_entities,
    scene_need_from_plan,
)
from app.stock_media import extract_proper_phrases


def test_river_every_billion_must_reject():
    """Smoke RC: finance spoken + river/nature metadata must REJECT."""
    need = scene_need_from_plan(
        queries=["legal tax documents paperwork", "corporate filing exemption"],
        must_show=["Every"],  # pre-hygiene trap from old heuristic
        required_entities=["Every"],
        scene_type="document",
        visual_intent="Every billion in profit gets reinvested or donated tax-free.",
        narrative_role="document",
    )
    # Hygiene must drop "Every"
    assert "Every" not in need.required_entities
    assert "every" not in {e.lower() for e in need.required_entities}
    river = AssetCandidate(
        provider="pixabay",
        asset_id="14053",
        download_url="https://example.com/river.mp4",
        title="",
        tags=(
            "hometown, brook, and every flower, stream, river, streams, "
            "nature, landscape, the rural brook, cool, autumn, creek, morning"
        ),
        description="",
        url="https://pixabay.com/videos/id-14053/",
        user="KIMDAEJEUNG",
    )
    gate = evaluate_asset(river, need)
    assert gate.accepted is False
    assert gate.reason in {
        "semantic_conflict",
        "missing_required_entities",
        "below_threshold",
        "weak_concept_evidence",
        "insufficient_evidence",
    }


def test_bakery_foundation_still_rejects():
    need = scene_need_from_plan(
        queries=["Rolex hans wilsdorf foundation"],
        must_show=["Hans Wilsdorf", "Rolex", "Foundation"],
        required_entities=["Hans Wilsdorf", "Rolex"],
        avoid=[],
        scene_type="evidence",
        visual_intent=(
            "The Hans Wilsdorf Foundation owns every share, funneling billions "
            "back into the Rolex empire."
        ),
        narrative_role="entity_proof",
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


def test_false_entity_every_not_extracted():
    phrases = extract_proper_phrases(
        "Every billion in profit gets reinvested or donated tax-free."
    )
    assert "Every" not in phrases
    assert hygienize_entities(["Every", "Rolex"]) == ["Rolex"]


def test_token_boundary_every_not_in_every_flower():
    blob = "hometown, brook, and every flower, stream, river, nature"
    assert entity_phrase_in_blob("Every", blob) is False
    assert entity_phrase_in_blob("every", blob) is False
    # Real entity still matches with boundaries
    assert entity_phrase_in_blob("Rolex", "Elegant Rolex watch among petals") is True
    assert entity_phrase_in_blob("Hans Wilsdorf", "Hans Wilsdorf archive portrait") is True
    assert entity_phrase_in_blob("Hans", "handsome businessman portrait") is False


def test_positive_hans_wilsdorf_archive_accepts():
    need = scene_need_from_plan(
        queries=["Hans Wilsdorf portrait archive"],
        must_show=["Hans Wilsdorf"],
        required_entities=["Hans Wilsdorf"],
        visual_intent="Archive portrait of Hans Wilsdorf",
        narrative_role="entity_proof",
    )
    good = AssetCandidate(
        provider="pexels",
        asset_id="42",
        download_url="https://example.com/hw.mp4",
        title="Hans Wilsdorf archival portrait",
        tags="Hans Wilsdorf, founder, archive, Rolex history",
        description="Vintage portrait of Hans Wilsdorf",
        url="https://www.pexels.com/photo/hans-wilsdorf-42/",
        user="Archive",
    )
    gate = evaluate_asset(good, need)
    assert gate.accepted is True
    assert gate.entity_score > 0


def test_positive_rolex_watch_accepts():
    need = scene_need_from_plan(
        queries=["Rolex crown watch macro"],
        must_show=["Rolex"],
        required_entities=["Rolex"],
        visual_intent="Rolex product hero close-up",
        narrative_role="hook",
    )
    good = AssetCandidate(
        provider="pexels",
        asset_id="7",
        download_url="https://example.com/r.mp4",
        title="Rolex Datejust luxury watch close-up",
        tags="Rolex, watch, dial, luxury timepiece",
        description="Macro of a Rolex watch face",
        url="https://www.pexels.com/photo/rolex-datejust-7/",
        user="Watch",
    )
    gate = evaluate_asset(good, need)
    assert gate.accepted is True


def test_positive_geneva_location_accepts():
    need = scene_need_from_plan(
        queries=["Geneva Switzerland skyline"],
        must_show=["Geneva", "Switzerland"],
        required_entities=["Geneva"],
        visual_intent="Geneva location establishing shot",
        narrative_role="place",
    )
    good = AssetCandidate(
        provider="pexels",
        asset_id="9",
        download_url="https://example.com/g.mp4",
        title="Geneva Switzerland Lake Geneva skyline dusk",
        tags="Geneva, Switzerland, skyline, landmark, lake",
        description="Cityscape of Geneva at twilight",
        url="https://www.pexels.com/video/geneva-switzerland-9/",
        user="Travel",
    )
    gate = evaluate_asset(good, need)
    assert gate.accepted is True


def test_hans_wilsdorf_extracted_as_phrase():
    phrases = extract_proper_phrases(
        "Hans Wilsdorf transferred 100% into a private Swiss foundation."
    )
    joined = " ".join(phrases).lower()
    assert "hans wilsdorf" in joined or (
        "Hans Wilsdorf" in phrases
    )
    assert "Every" not in phrases
