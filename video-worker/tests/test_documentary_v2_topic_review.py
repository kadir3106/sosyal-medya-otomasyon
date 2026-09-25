"""Topic-driven V2 review path contracts."""


def test_documentary_script_prompt_has_no_luxury_bias(monkeypatch):
    from app import script_gen

    seen = []

    def fake_llm(messages, api_key):
        seen.append(messages[0]["content"])
        return (
            '{"script":"The Aral Sea shrank after river diversion.",'
            '"title":"The Aral Sea","description":"A shrinking sea.",'
            '"tags":["history"]}',
            "fixture",
        )

    monkeypatch.setattr(script_gen, "_call_llm_with_fallback", fake_llm)
    data = script_gen.generate_script("Aral Sea", "fixture", style="documentary_review")
    assert data["script"].startswith("The Aral Sea")
    assert "Rolex" not in seen[0] and "Luxury Lifestyle" not in seen[0]
    assert "scene_stock_queries" not in data
