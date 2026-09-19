import pytest
from unittest.mock import patch

from app.tts import synthesize_speech


@pytest.fixture(autouse=True)
def _isolate_edge_tts():
    with patch("app.tts.config.ELEVENLABS_API_KEY", None):
        yield


class _FakeCommunicate:
    def __init__(self, text, voice, **kwargs):
        self.text = text
        self.voice = voice
        self.kwargs = kwargs

    async def stream(self):
        yield {"type": "audio", "data": b"AUDIOBYTES1"}
        yield {"type": "WordBoundary", "offset": 0, "duration": 5000000, "text": "Hello"}
        yield {"type": "audio", "data": b"AUDIOBYTES2"}
        yield {"type": "WordBoundary", "offset": 5000000, "duration": 4000000, "text": "world"}


@patch("app.tts.edge_tts.Communicate", _FakeCommunicate)
async def test_synthesize_speech_writes_audio_and_returns_word_boundaries(tmp_path):
    output_path = tmp_path / "speech.mp3"

    boundaries = await synthesize_speech("Hello world", str(output_path))

    assert output_path.read_bytes() == b"AUDIOBYTES1AUDIOBYTES2"
    assert boundaries == [
        {"offset": 0, "duration": 5000000, "text": "Hello"},
        {"offset": 5000000, "duration": 4000000, "text": "world"},
    ]


@patch("app.tts.edge_tts.Communicate", _FakeCommunicate)
async def test_synthesize_speech_uses_requested_voice(tmp_path):
    output_path = tmp_path / "speech.mp3"
    captured = {}

    class _CapturingCommunicate(_FakeCommunicate):
        def __init__(self, text, voice, **kwargs):
            super().__init__(text, voice, **kwargs)
            captured["voice"] = voice

    with patch("app.tts.edge_tts.Communicate", _CapturingCommunicate):
        await synthesize_speech("Hi", str(output_path), voice="en-GB-RyanNeural")

    assert captured["voice"] == "en-GB-RyanNeural"


@patch("app.tts.edge_tts.Communicate", _FakeCommunicate)
async def test_synthesize_speech_requests_word_boundaries(tmp_path):
    output_path = tmp_path / "speech.mp3"
    captured = {}

    class _CapturingCommunicate(_FakeCommunicate):
        def __init__(self, text, voice, **kwargs):
            super().__init__(text, voice, **kwargs)
            captured["kwargs"] = kwargs

    with patch("app.tts.edge_tts.Communicate", _CapturingCommunicate):
        await synthesize_speech("Hi", str(output_path))

    # edge-tts >= 7 varsayılanı SentenceBoundary — altyazılar için bu şart
    assert captured["kwargs"] == {"boundary": "WordBoundary"}


@patch("app.tts.edge_tts.Communicate", _FakeCommunicate)
async def test_synthesize_speech_passes_rate_when_specified(tmp_path):
    output_path = tmp_path / "speech.mp3"
    captured = {}

    class _CapturingCommunicate(_FakeCommunicate):
        def __init__(self, text, voice, **kwargs):
            super().__init__(text, voice, **kwargs)
            captured["kwargs"] = kwargs

    with patch("app.tts.edge_tts.Communicate", _CapturingCommunicate):
        await synthesize_speech("Hi", str(output_path), rate="+15%")

    assert captured["kwargs"] == {"boundary": "WordBoundary", "rate": "+15%"}



class _NoBoundaryCommunicate:
    def __init__(self, text, voice, **kwargs):
        pass

    async def stream(self):
        yield {"type": "audio", "data": b"AUDIO"}
        # SentenceBoundary varsayılan davranışını simüle et
        yield {"type": "SentenceBoundary", "offset": 0, "duration": 100, "text": "x"}


@patch("app.tts.edge_tts.Communicate", _NoBoundaryCommunicate)
async def test_synthesize_speech_raises_when_no_word_boundaries(tmp_path):
    output_path = tmp_path / "speech.mp3"

    with pytest.raises(RuntimeError, match="WordBoundary"):
        await synthesize_speech("Hello", str(output_path))


async def test_synthesize_speech_uses_elevenlabs_when_configured(tmp_path):
    output_path = tmp_path / "speech.mp3"
    fake_words = [{"offset": 0, "duration": 5000000, "text": "Hello"}]
    meta: dict = {}

    with patch("app.tts.config.ELEVENLABS_API_KEY", "fake-key"), \
         patch("app.tts._synthesize_elevenlabs", return_value=fake_words) as mock_eleven:
        res = await synthesize_speech("Hello", str(output_path), meta_out=meta)
        assert res == fake_words
        mock_eleven.assert_called_once()
    assert meta["provider"] == "elevenlabs"


@patch("app.tts.edge_tts.Communicate", _FakeCommunicate)
async def test_synthesize_speech_meta_out_reports_edge_when_no_key(tmp_path):
    output_path = tmp_path / "speech.mp3"
    meta: dict = {}
    with patch("app.tts.config.ELEVENLABS_API_KEY", ""):
        await synthesize_speech("Hello world", str(output_path), meta_out=meta)
    assert meta["provider"] == "edge"
    assert meta["edge_reason"] == "missing_key"