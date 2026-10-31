"""ffmpeg yokmuş gibi davranıp guard'ın gerçekten devreye girdiğini kanıtla.

`HAS_FFMPEG`'i False'a çekip hedeflenen bir testi koşuyoruz. Guard çalışmazsa
test ham `FileNotFoundError: 'ffmpeg'` ile ERROR/FAILED olur — ki CI'da tam
olarak bu oldu (run 41228709572, 15 test).
"""
import subprocess
import sys
from pathlib import Path

VIDEO_WORKER = Path(__file__).resolve().parent.parent

# conftest yüklenirken HAS_FFMPEG hesaplanır; plugin olarak araya girip
# hesaplanmasını engelliyoruz.
_PLUGIN = """
import shutil
shutil.which = lambda name, *a, **k: None
"""


def _run(target: str):
    plugin = VIDEO_WORKER / "_no_ffmpeg_plugin.py"
    plugin.write_text(_PLUGIN, encoding="utf-8")
    try:
        return subprocess.run(
            [
                sys.executable, "-m", "pytest", target, "-q", "--no-header",
                "-p", "no:cacheprovider", "-p", "_no_ffmpeg_plugin",
            ],
            cwd=str(VIDEO_WORKER), capture_output=True, text=True, timeout=180,
        )
    finally:
        plugin.unlink(missing_ok=True)


def test_guard_actually_skips_when_ffmpeg_is_absent():
    """Guard devrede: hedeflenen test SKIP olmalı, ERROR/FAILED değil."""
    result = _run("tests/test_pipeline_pending.py::test_generate_video_writes_pending_json")
    out = result.stdout + result.stderr

    assert "FileNotFoundError" not in out, out[-3000:]
    assert "skipped" in out, out[-3000:]
    assert result.returncode == 0, out[-3000:]


def test_guard_leaves_unrelated_tests_running():
    """Guard fazla geniş değil: hedef dışı bir test yine koşmalı (skip olmamalı)."""
    result = _run("tests/test_ffmpeg_guard.py::test_needs_ffmpeg_does_not_hide_unrelated_tests")
    out = result.stdout + result.stderr

    assert result.returncode == 0, out[-3000:]
    assert "1 passed" in out, out[-3000:]
    assert "skipped" not in out, out[-3000:]
