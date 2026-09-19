from unittest.mock import patch, Mock
from pathlib import Path
from app.audio_bgm import get_or_create_bgm


def test_get_or_create_bgm_returns_existing_track(tmp_path):
    track = tmp_path / "chill_lofi.mp3"
    track.write_bytes(b"MP3DATA")

    result = get_or_create_bgm(str(tmp_path))
    assert result == str(track)


@patch("app.audio_bgm.subprocess.run")
def test_get_or_create_bgm_synthesizes_ambient_when_empty(mock_run, tmp_path):
    def fake_run(cmd, **kwargs):
        # cmd[-1] is the output file
        Path(cmd[-1]).write_bytes(b"SYNTH_BGM")
        return Mock(returncode=0)

    mock_run.side_effect = fake_run

    result = get_or_create_bgm(str(tmp_path))
    assert result is not None
    assert result.endswith("default_ambient.mp3")
    assert mock_run.called
