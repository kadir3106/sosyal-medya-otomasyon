"""Phase 2.2 — specificity ranking, reuse penalty, hook fade."""

from app.director_gate import (
    AssetCandidate,
    asset_fingerprint,
    evaluate_asset,
    reuse_penalty,
    scene_need_from_plan,
    selection_score,
)
from app.director_types import VisualBeat
from app.subtitles import write_ass
from app.director_gate import compute_specificity_score


def test_hans_portrait_outranks_rolex_storefront():
    need = scene_need_from_plan(
        queries=["Hans Wilsdorf portrait archive"],
        must_show=["Hans Wilsdorf"],
        required_entities=["Hans Wilsdorf"],
        visual_intent="Archive portrait of Hans Wilsdorf",
        narrative_role="entity_proof",
    )
    store = AssetCandidate(
        provider="pexels",
        asset_id="store1",
        download_url="https://example.com/store.mp4",
        title="Illuminated Bucherer Rolex building at night",
        tags="Rolex, storefront, boutique, building, illuminated",
        description="Luxury Rolex store facade",
        url="https://www.pexels.com/photo/rolex-store-1/",
    )
    portrait = AssetCandidate(
        provider="pexels",
        asset_id="hw1",
        download_url="https://example.com/hw.mp4",
        title="Hans Wilsdorf archival portrait",
        tags="Hans Wilsdorf, founder, archive, Rolex history, portrait",
        description="Vintage portrait of Hans Wilsdorf",
        url="https://www.pexels.com/photo/hans-wilsdorf-1/",
    )
    g_store = evaluate_asset(store, need)
    g_port = evaluate_asset(portrait, need)
    # Store must not win a person-entity moment.
    assert g_port.accepted is True
    assert g_port.specificity_score > 0.7
    if g_store.accepted:
        assert selection_score(g_port) > selection_score(g_store)
    else:
        assert g_store.reason in {
            "missing_required_entities",
            "low_specificity",
            "weak_concept_evidence",
            "below_threshold",
        }


def test_reuse_penalty_prefers_fresh_asset():
    need = scene_need_from_plan(
        queries=["Rolex watch macro"],
        must_show=["Rolex"],
        required_entities=["Rolex"],
        visual_intent="Rolex product hero",
        narrative_role="hook",
    )
    a = AssetCandidate(
        provider="pexels_photo",
        asset_id="111",
        download_url="https://example.com/a.jpg",
        title="Rolex Submariner close-up dial",
        tags="Rolex, watch, dial, luxury",
        description="Macro Rolex watch",
        url="https://www.pexels.com/photo/111/",
    )
    c = AssetCandidate(
        provider="pexels_photo",
        asset_id="222",
        download_url="https://example.com/c.jpg",
        title="Rolex Datejust luxury watch on wrist",
        tags="Rolex, watch, timepiece, luxury",
        description="Rolex Datejust product shot",
        url="https://www.pexels.com/photo/222/",
    )
    g_a = evaluate_asset(a, need)
    g_c = evaluate_asset(c, need)
    assert g_a.accepted and g_c.accepted
    fp_a = asset_fingerprint(provider=a.provider, asset_id=a.asset_id, url=a.url)
    # After A was just used, C should outrank repeated A.
    recent = [fp_a]
    score_a = selection_score(g_a, reuse_pen=reuse_penalty(fp_a, recent))
    score_c = selection_score(
        g_c,
        reuse_pen=reuse_penalty(
            asset_fingerprint(provider=c.provider, asset_id=c.asset_id, url=c.url),
            recent,
        ),
    )
    assert score_c > score_a


def test_entity_first_queries_prefer_portrait_for_person():
    beat = VisualBeat(
        index=0,
        scene_index=0,
        spoken_span="Hans Wilsdorf founded the company",
        concept="founder",
        primary_entities=["Hans Wilsdorf"],
        visual_intent="Archive portrait",
        search_queries=["Rolex storefront Lucerne"],
        shot_type="archival",
    )
    qs = beat.entity_first_queries(topic="The Rolex Foundation Secret long headline here")
    assert any("portrait" in q.lower() for q in qs[:3])
    assert qs[0].lower().startswith("hans wilsdorf")


def test_hook_fades_and_caps_duration(tmp_path):
    boundaries = [
        {"offset": 0, "duration": 5_000_000, "text": "Hello"},
        {"offset": 5_000_000, "duration": 5_000_000, "text": "World"},
    ]
    out = tmp_path / "h.ass"
    write_ass(
        boundaries,
        str(out),
        hook_text="ZERO TAX EMPIRE",
        hook_seconds=2.5,
        karaoke_start_seconds=0.0,
    )
    content = out.read_text(encoding="utf-8")
    assert r"\fad(" in content
    # Cap ≤ 1.8s even if caller asked for 2.5
    assert "0:00:01.80,Hook," in content or "0:00:01.60,Hook," in content
    assert "ZERO TAX" in content.upper() or "TAX EMPIRE" in content.upper()


def test_hook_skipped_when_duplicates_vo(tmp_path):
    boundaries = [
        {"offset": 0, "duration": 8_000_000, "text": "Rolex"},
        {"offset": 8_000_000, "duration": 8_000_000, "text": "Foundation"},
        {"offset": 16_000_000, "duration": 8_000_000, "text": "Secret"},
    ]
    out = tmp_path / "dup.ass"
    write_ass(
        boundaries,
        str(out),
        hook_text="The Rolex Foundation Secret",
        hook_seconds=1.6,
        karaoke_start_seconds=0.0,
    )
    content = out.read_text(encoding="utf-8")
    # Static Hook dialogue should be suppressed; karaoke still present.
    assert ",Hook," not in content
    assert "ROLEX" in content.upper()


def test_specificity_person_portrait_vs_store():
    need = scene_need_from_plan(
        queries=["Hans Wilsdorf"],
        required_entities=["Hans Wilsdorf"],
        visual_intent="Hans Wilsdorf founder portrait",
        narrative_role="entity_proof",
    )
    port_blob = "Hans Wilsdorf archival portrait founder Rolex history"
    store_blob = "Illuminated Rolex storefront boutique building"  # no Hans
    sp = compute_specificity_score(
        need, port_blob, entities=["Hans Wilsdorf"], entity_score=1.0
    )
    ss = compute_specificity_score(
        need, store_blob, entities=["Hans Wilsdorf"], entity_score=0.0
    )
    assert sp > ss
    assert sp >= 0.85
