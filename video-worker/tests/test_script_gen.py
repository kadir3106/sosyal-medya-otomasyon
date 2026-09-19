import importlib
import json
from unittest.mock import patch, Mock

import app.config as config_module
import app.script_gen as script_gen_module
from app.script_gen import DEFAULT_MODEL, generate_script, MODEL


def _mock_response(content: str) -> Mock:
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return mock_resp


@patch("app.script_gen.session.post")
def test_generate_script_parses_valid_json_response(mock_post):
    payload = {
        "script": "Flamingos stand on one leg to conserve body heat...",
        "title": "Why Flamingos Stand on One Leg",
        "description": "The surprising science behind it. #flamingo #nature #facts",
        "tags": ["flamingo", "nature", "biology", "facts", "animals"],
    }
    mock_post.return_value = _mock_response(json.dumps(payload))

    result = generate_script("Why flamingos stand on one leg", api_key="fake-key")

    assert result == payload
    called_kwargs = mock_post.call_args.kwargs
    assert called_kwargs["headers"]["Authorization"] == "Bearer fake-key"
    # Çalışma anında çözümlenen model (env varsa o, yoksa DEFAULT_MODEL) gönderilmeli
    assert called_kwargs["json"]["model"] == MODEL


@patch("app.script_gen.session.post")
def test_generate_script_strips_markdown_fences(mock_post):
    payload = {"script": "s", "title": "t", "description": "d", "tags": ["a"]}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    mock_post.return_value = _mock_response(fenced)

    result = generate_script("Some topic", api_key="fake-key")

    assert result == payload


@patch("app.script_gen.session.post")
def test_generate_script_raises_on_invalid_json(mock_post):
    mock_post.return_value = _mock_response("not json at all")

    try:
        generate_script("Some topic", api_key="fake-key")
        assert False, "expected ValueError"
    except ValueError:
        pass


@patch("app.script_gen.session.post")
def test_generate_script_raises_on_missing_key(mock_post):
    incomplete = {"script": "s", "title": "t"}
    mock_post.return_value = _mock_response(json.dumps(incomplete))

    try:
        generate_script("Some topic", api_key="fake-key")
        assert False, "expected ValueError"
    except ValueError:
        pass


@patch("app.script_gen.session.post")
def test_generate_script_uses_turkish_template_when_lang_tr(mock_post):
    from app.script_gen import PROMPT_TEMPLATE_TR

    payload = {"script": "s", "title": "t", "description": "d", "tags": ["a"]}
    mock_post.return_value = _mock_response(json.dumps(payload))

    generate_script("Zürafaların ses telleri", api_key="fake-key", lang="tr")

    content = mock_post.call_args.kwargs["json"]["messages"][0]["content"]
    assert content == PROMPT_TEMPLATE_TR.format(topic="Zürafaların ses telleri")


@patch("app.script_gen.session.post")
def test_generate_script_retries_once_when_script_too_long(mock_post):
    long_payload = {
        "script": "word " * 120,
        "title": "t",
        "description": "d",
        "tags": ["a"],
    }
    short_payload = {"script": "short", "title": "t", "description": "d", "tags": ["a"]}
    mock_post.side_effect = [
        _mock_response(json.dumps(long_payload)),
        _mock_response(json.dumps(short_payload)),
    ]

    result = generate_script("Some topic", api_key="fake-key")

    assert result["script"] == "short"
    assert mock_post.call_count == 2
    second_messages = mock_post.call_args.kwargs["json"]["messages"]
    assert second_messages[-1]["content"].startswith("Too long")


def test_default_model_is_pinned_when_env_unset(monkeypatch):
    # .env'den gelen OPENROUTER_MODEL ortam değerinden bağımsız olarak,
    # env boşken sabitlenmiş varsayılana düşülmeli.
    monkeypatch.setenv("OPENROUTER_MODEL", "")
    importlib.reload(config_module)
    sg = importlib.reload(script_gen_module)

    assert sg.DEFAULT_MODEL == "google/gemma-4-31b-it:free"
    assert sg.MODEL == sg.DEFAULT_MODEL


def test_model_env_override(monkeypatch):
    monkeypatch.setenv("OPENROUTER_MODEL", "minimax/minimax-m2.7:free")
    importlib.reload(config_module)
    sg = importlib.reload(script_gen_module)

    assert sg.MODEL == "minimax/minimax-m2.7:free"
