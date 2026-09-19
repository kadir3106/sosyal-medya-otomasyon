import json
from unittest.mock import Mock, patch

from app.image_gen import generate_image_content, render_card


def _mock_response(content: str) -> Mock:
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return mock_resp


@patch("app.image_gen.session.post")
def test_generate_image_content_parses_valid_json(mock_post):
    payload = {
        "text": "Bal hiç bozulmaz; 3000 yıllık bal bile yenebilir.",
        "caption": "Bunu biliyor muydunuz? #bal #bilgi #ilginç",
        "hashtags": ["bal", "bilgi", "ilginc"],
    }
    mock_post.return_value = _mock_response(json.dumps(payload))

    result = generate_image_content("Balın neden hiç bozulmadığı", api_key="fake-key")

    assert result == payload
    assert mock_post.call_args.kwargs["headers"]["Authorization"] == "Bearer fake-key"


@patch("app.image_gen.session.post")
def test_generate_image_content_strips_markdown_fences(mock_post):
    payload = {"text": "t", "caption": "c", "hashtags": ["a"]}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    mock_post.return_value = _mock_response(fenced)

    result = generate_image_content("konu", api_key="fake-key")

    assert result == payload


@patch("app.image_gen.session.post")
def test_generate_image_content_raises_on_invalid_json(mock_post):
    mock_post.return_value = _mock_response("not json at all")

    try:
        generate_image_content("konu", api_key="fake-key")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_render_card_creates_png_with_turkish_text(tmp_path):
    output = str(tmp_path / "kart.png")

    result = render_card(
        "Bal hiç bozulmaz; 3000 yıllık bal bile yenebilir.",
        brand_name="KALI",
        accent="#38BDF8",
        output_path=output,
    )

    assert result == output
    content = open(output, "rb").read()
    assert content[:8] == b"\x89PNG\r\n\x1a\n"  # PNG imzası
    assert len(content) > 1000


def test_render_card_wraps_long_text(tmp_path):
    output = str(tmp_path / "uzun.png")

    render_card(
        "Bu oldukça uzun bir metindir ve kelime kaydırma mekanizmasının "
        "doğru çalışıp çalışmadığını test etmek için yazılmıştır " * 3,
        brand_name="KALI",
        accent="#38BDF8",
        output_path=output,
    )

    assert open(output, "rb").read(8) == b"\x89PNG\r\n\x1a\n"
