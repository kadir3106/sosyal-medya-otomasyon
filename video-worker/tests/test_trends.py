from unittest.mock import patch, Mock
from app.trends import fetch_trends, FALLBACK_TRENDS
from app.pitch_gen import generate_pitches, FALLBACK_PITCHES


def test_fetch_trends_returns_fallback_on_network_error():
    with patch("app.trends.session.get", side_effect=Exception("network down")):
        trends = fetch_trends()
        assert len(trends) == 5
        assert trends == FALLBACK_TRENDS


def test_fetch_trends_parses_valid_xml():
    sample_xml = """<rss><channel>
        <item><title>Bitcoin Rekor Kırdı</title><description>Kripto para piyasaları yükselişte</description></item>
        <item><title>Yapay Zeka Zirvesi</title><description>Yeni modeller tanıtıldı</description></item>
    </channel></rss>"""
    mock_resp = Mock(status_code=200, content=sample_xml.encode("utf-8"))
    with patch("app.trends.session.get", return_value=mock_resp):
        trends = fetch_trends(max_count=2)
        assert len(trends) == 2
        assert trends[0]["title"] == "Bitcoin Rekor Kırdı"
        assert trends[1]["title"] == "Yapay Zeka Zirvesi"


def test_generate_pitches_returns_structured_ideas():
    fake_json = """[
        {"id": 1, "category": "komedi", "title": "T1", "hook": "H1", "topic": "Top1"},
        {"id": 2, "category": "merak", "title": "T2", "hook": "H2", "topic": "Top2"},
        {"id": 3, "category": "motivasyon", "title": "T3", "hook": "H3", "topic": "Top3"}
    ]"""
    with patch("app.pitch_gen._call_llm", return_value=fake_json):
        pitches = generate_pitches([{"title": "Trend A"}], api_key="test-key")
        assert len(pitches) == 3
        assert pitches[0]["title"] == "T1"
        assert pitches[1]["category"] == "merak"
        assert pitches[2]["hook"] == "H3"


def test_generate_pitches_falls_back_on_invalid_json():
    with patch("app.pitch_gen._call_llm", return_value="invalid-non-json"):
        pitches = generate_pitches([{"title": "Trend A"}], api_key="test-key")
        assert len(pitches) == 3
        assert pitches == FALLBACK_PITCHES
