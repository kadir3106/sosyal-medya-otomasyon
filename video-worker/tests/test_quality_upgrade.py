"""Analytics memory stub + Flux default / stock gate smoke."""

import importlib

from app.analytics_memory import (
    format_hook_memory_context,
    load_winning_hooks,
    pick_hook_alternative,
    store_winning_hook,
)
from app.ai_visuals import build_flux_prompt


def test_config_default_visual_engine_is_stock(monkeypatch):
    monkeypatch.delenv("VISUAL_ENGINE", raising=False)
    monkeypatch.delenv("ALLOW_STOCK_FALLBACK", raising=False)
    monkeypatch.delenv("TOPICS_PATH", raising=False)
    import app.config as config_module

    importlib.reload(config_module)
    assert config_module.Config.VISUAL_ENGINE == "stock"
    assert config_module.Config.ALLOW_STOCK_FALLBACK is True
    assert config_module.Config.TOPICS_PATH.endswith("topics_dark_wealth.json")


def test_config_remaps_trivia_topics_path(monkeypatch):
    monkeypatch.setenv("TOPICS_PATH", "/app/data/topics.json")
    import app.config as config_module

    importlib.reload(config_module)
    assert config_module.Config.TOPICS_PATH.endswith("topics_dark_wealth.json")


def test_winning_hooks_stub_store_load_and_pick(tmp_path):
    store_winning_hook(
        "A Swiss trust owns every crown.",
        topic="Rolex",
        title="Who Owns Rolex?",
        job_id="job-1",
        media_dir=tmp_path,
    )
    hooks = load_winning_hooks(tmp_path)
    assert len(hooks) == 1
    assert hooks[0]["hook"].startswith("A Swiss")

    ctx = format_hook_memory_context(tmp_path)
    assert "Historical Winning Hooks" in ctx
    assert "Swiss trust" in ctx

    picked = pick_hook_alternative(
        [
            "A Swiss trust owns every crown.",
            "Rolex has no public shareholders.",
        ],
        media_dir=tmp_path,
    )
    assert picked == "Rolex has no public shareholders."


def test_build_flux_prompt_anchors_rolex_nouns():
    prompt = build_flux_prompt(
        "macro of crown logo on steel bezel",
        topic="The Rolex Foundation Secret: How Rolex is owned 100% by a private Swiss trust",
        concrete_nouns=["Rolex", "Swiss trust", "crown", "Geneva vault"],
        scene_index=0,
    )
    lower = prompt.lower()
    assert "rolex" in lower
    assert "luxury business" not in lower
    assert "chiaroscuro" in lower or "old-money" in lower or "dark" in lower
