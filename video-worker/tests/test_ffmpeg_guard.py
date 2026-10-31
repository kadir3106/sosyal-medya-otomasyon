"""ffmpeg yokluğunda paket davranışı.

Ölçüm: CI'ın ilk gerçek koşusu (run 41228709572) 15 testi
`FileNotFoundError: [Errno 2] No such file or directory: 'ffmpeg'` ile düşürdü.
Sebep kod değil ortamdı: ubuntu-latest imajında ffmpeg yok — ve CI dosyasındaki
yorum bunun tersini söylüyordu ("ffmpeg/ffprobe are preinstalled on ubuntu-latest").
Yorum yanlış olduğu için hata ancak CI gerçekten koşunca göründü.

Bu testler, ffmpeg olmadığında testlerin *açık sebeple* atlandığını doğruluyor;
ham traceback yerine okunur bir mesaj çıkmalı.
"""
import importlib.util
from pathlib import Path

from app import publish_quality

VIDEO_WORKER = Path(__file__).resolve().parent.parent


def _load_conftest():
    """conftest'i pytest dışından yükle (kararı saf fonksiyon olarak sınamak için)."""
    spec = importlib.util.spec_from_file_location(
        "_conftest_probe", VIDEO_WORKER / "tests" / "conftest.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_conftest_exposes_a_single_ffmpeg_flag():
    """`HAS_FFMPEG` tek kaynak olmalı; her test dosyası kendi kontrolünü yazmasın."""
    conftest = _load_conftest()

    assert isinstance(conftest.HAS_FFMPEG, bool)
    assert callable(conftest.needs_ffmpeg)


def test_needs_ffmpeg_matches_the_files_measured_as_failing():
    """Guard listesi CI'da gerçekten düşen 15 testin dosyalarıyla sınırlı olmalı.

    Fazla geniş liste işe yarar testleri sessizce gizler; fazla dar liste CI'ı
    kırmızı bırakır. Liste, run 41228709572'nin `FAILED tests/...` satırlarından
    okundu.
    """
    conftest = _load_conftest()

    assert conftest.needs_ffmpeg(
        "tests/test_pipeline.py::test_generate_video_runs_full_pipeline"
    )
    assert conftest.needs_ffmpeg(
        "tests/test_pipeline_pending.py::test_generate_video_writes_pending_json"
    )
    assert conftest.needs_ffmpeg(
        "tests/test_documentary_v2_stage_f.py::test_edl_render_and_technical_qa"
    )


def test_needs_ffmpeg_does_not_hide_unrelated_tests():
    """Mock'lanmış / saf-mantık testleri asla guard'a takılmamalı."""
    conftest = _load_conftest()

    assert not conftest.needs_ffmpeg("tests/test_topics.py::test_pick_topic")
    assert not conftest.needs_ffmpeg("tests/test_jsonstore.py::test_atomic_write")
    assert not conftest.needs_ffmpeg("tests/test_ffmpeg_guard.py::test_anything")


def test_quality_gate_degrades_softly_without_ffprobe(monkeypatch, tmp_path):
    """Kalite kapısı ölçemiyorsa yayını BLOKLAMAMALI (bilinçli yumuşak tasarım).

    `publish_quality` modül düzeyinde `shutil` import etmiyor; `_probe` içindeki
    `subprocess.check_output`'u hedefliyoruz.
    """
    video = tmp_path / "v.mp4"
    video.write_bytes(b"x" * 64)

    def _boom(*args, **kwargs):
        raise FileNotFoundError("ffprobe")

    monkeypatch.setattr(publish_quality.subprocess, "check_output", _boom)

    verdict = publish_quality.evaluate(video)

    assert verdict.ok is True
    assert verdict.reason == "probe_unavailable"
    assert verdict.checks["probe"] == "unknown"
