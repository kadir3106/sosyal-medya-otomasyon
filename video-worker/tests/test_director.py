"""AI Director unit tests — plan parse, heuristic, flag default."""

from app.config import config
from app.director_planner import (
    parse_scene_plan_document,
    plan_scenes,
    score_candidate_text,
)
from app.director_types import ScenePlan


def test_director_enabled_defaults_off(monkeypatch):
    monkeypatch.delenv("DIRECTOR_ENABLED", raising=False)
    assert config.DIRECTOR_ENABLED is False


def test_parse_scene_plan_pads_and_normalizes_kinds():
    raw = {
        "scenes": [
            {
                "index": 0,
                "scene_type": "hook",
                "visual_intent": "Rolex crown close-up",
                "preferred_kinds": ["stock_video", "bogus", "stock_photo"],
                "search_queries": ["Rolex crown watch"],
                "backup_plan": {
                    "preferred_kinds": ["ai_image"],
                    "search_queries": ["luxury watch face"],
                },
                "allow_ai_generation": True,
            }
        ]
    }
    doc = parse_scene_plan_document(raw, scene_count=3)
    assert len(doc.scenes) == 3
    assert doc.scenes[0].preferred_kinds == ["stock_video", "stock_photo"]
    assert "ai_image" in doc.scenes[0].kind_chain()
    assert doc.scenes[1].preferred_kinds  # padded heuristic defaults
    assert doc.scenes[2].index == 2


def test_scene_plan_kind_chain_dedupes():
    sc = ScenePlan(
        index=0,
        scene_type="evidence",
        visual_intent="vault door",
        preferred_kinds=["stock_video", "stock_video", "stock_photo"],
        search_queries=["swiss bank vault door"],
        backup_kinds=["stock_photo", "ai_image"],
        allow_ai_generation=False,
    )
    assert sc.kind_chain() == ["stock_video", "stock_photo", "ai_image"]


def test_score_candidate_rejects_avoid_token():
    score = score_candidate_text(
        "casino chips roulette",
        queries=["swiss vault"],
        avoid=["casino"],
    )
    assert score < 0


def test_heuristic_plan_without_api_key():
    doc = plan_scenes(
        scene_count=4,
        topic="De Beers diamond monopoly",
        script="De Beers controlled diamond supply for decades.",
        api_key="",
        scene_stock_queries=[
            {"query": "De Beers diamond rough stones", "mode": "diamond"},
            {"query": "diamond exchange trading floor", "mode": "finance_docs"},
        ],
        visual_prompts=["diamond vault", "bourse floor"],
        visual_keywords=["diamond", "vault"],
    )
    assert len(doc.scenes) == 4
    kinds_used = {k for s in doc.scenes for k in s.preferred_kinds}
    assert "stock_video" in kinds_used
    # Not every scene identical kind-only stock_video preference list
    assert any("stock_photo" in s.preferred_kinds for s in doc.scenes)
