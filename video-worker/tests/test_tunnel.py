import pytest

from app.tunnel import get_tunnel_url


def test_get_tunnel_url_extracts_url_from_log(tmp_path):
    log_path = tmp_path / "tunnel.log"
    log_path.write_text(
        "2026-09-03T09:00:00Z INF Starting tunnel\n"
        "2026-09-03T09:00:01Z INF |  https://random-words-here.trycloudflare.com  |\n",
        encoding="utf-8",
    )

    assert (
        get_tunnel_url(str(log_path))
        == "https://random-words-here.trycloudflare.com"
    )


def test_get_tunnel_url_returns_most_recent_when_multiple(tmp_path):
    log_path = tmp_path / "tunnel.log"
    log_path.write_text(
        "https://old-url.trycloudflare.com\nhttps://new-url.trycloudflare.com\n",
        encoding="utf-8",
    )

    assert get_tunnel_url(str(log_path)) == "https://new-url.trycloudflare.com"


def test_get_tunnel_url_raises_when_not_found(tmp_path):
    log_path = tmp_path / "tunnel.log"
    log_path.write_text("still starting up...\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="No trycloudflare.com URL"):
        get_tunnel_url(str(log_path))
