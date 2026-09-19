import subprocess
from pathlib import Path
from unittest.mock import patch, Mock

from app.ai_visuals import (
    generate_ai_image,
    image_to_motion_clip,
    generate_ai_scene_clips,
)


@patch("urllib.request.urlopen")
def test_generate_ai_image_success(mock_urlopen, tmp_path):
    mock_resp = Mock()
    mock_resp.read.return_value = b"fake-image-bytes" * 100
    mock_resp.__enter__ = Mock(return_value=mock_resp)
    mock_resp.__exit__ = Mock(return_value=False)
    mock_urlopen.return_value = mock_resp

    target = tmp_path / "test.jpg"
    res = generate_ai_image("dark cinematic street", target)

    assert res == target
    assert target.exists()
    assert len(target.read_bytes()) > 100


@patch("urllib.request.urlopen")
def test_generate_ai_image_fallback_on_error(mock_urlopen, tmp_path):
    mock_urlopen.side_effect = Exception("Network timeout")

    target = tmp_path / "fallback.jpg"
    res = generate_ai_image("dark cinematic street", target)

    assert res == target
    assert target.exists()
    assert target.stat().st_size > 0


@patch("subprocess.run")
def test_image_to_motion_clip_runs_ffmpeg(mock_run, tmp_path):
    img = tmp_path / "img.jpg"
    img.write_bytes(b"dummy")
    clip = tmp_path / "clip.mp4"

    res = image_to_motion_clip(img, clip, duration=2.5, motion_type="zoom_in")

    assert res == clip
    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert cmd[0] == "ffmpeg"
    assert "zoompan" in " ".join(cmd)


@patch("app.ai_visuals.generate_ai_image")
@patch("app.ai_visuals.image_to_motion_clip")
def test_generate_ai_scene_clips(mock_motion, mock_gen, tmp_path):
    prompts = ["prompt 1", "prompt 2", "prompt 3"]
    clips = generate_ai_scene_clips(prompts, str(tmp_path), clip_duration=2.5)

    assert len(clips) == 3
    assert mock_gen.call_count == 3
    assert mock_motion.call_count == 3
