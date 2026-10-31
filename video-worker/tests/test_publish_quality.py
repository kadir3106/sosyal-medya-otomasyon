"""Yayın öncesi teknik kalite kapısı.

Ölçüm (kapı eklenmeden önce): `_run_publish` videoyu hiç açmıyordu, yalnızca
onay hash'ini karşılaştırıyordu. Diskte süresi 0, sesi boş veya yarım yazılmış
bir MP4 onaylandığı sürece yayınlanabiliyordu — yol haritası hedefi
"sessiz/bozuk video yayını = 0" garanti değildi.

Gerçek medyayla ölçülen davranış (ffmpeg/ffprobe host'ta var):

    sesli video (440 Hz tone)   -> ok=True   -21.1 dB
    sessiz video (boş ses)      -> ok=False  audio_silent      -91.0 dB
    ses akışı yok               -> ok=False  no_audio_stream
    1 sn video                  -> ok=False  too_short
    bozuk dosya                 -> ok=True   probe_unavailable  (yumuşak)
    dosya yok                   -> ok=False  video_missing
"""
import subprocess

import pytest

from app import publish_quality as q


def _has_ffmpeg() -> bool:
    import shutil

    return shutil.which("ffmpeg") is not None and shutil.which("ffprobe") is not None


requires_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg/ffprobe yok")


def _make(path, *, seconds=4, audio="tone"):
    """tone | silent | none — gerçek medya üretir."""
    cmd = [
        "ffmpeg", "-y", "-v", "error",
        "-f", "lavfi", "-i", f"color=c=blue:s=320x568:d={seconds}",
    ]
    if audio == "tone":
        cmd += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}"]
        cmd += ["-shortest", "-c:a", "aac"]
    elif audio == "silent":
        cmd += ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono", "-t", str(seconds)]
        cmd += ["-shortest", "-c:a", "aac"]
    cmd += ["-c:v", "libx264", "-pix_fmt", "yuv420p", str(path)]
    subprocess.run(cmd, check=True, capture_output=True)


@requires_ffmpeg
def test_accepts_video_with_real_audio(tmp_path):
    video = tmp_path / "ok.mp4"
    _make(video, audio="tone")

    verdict = q.evaluate(video)

    assert verdict.ok is True, verdict
    assert verdict.has_audio_stream is True
    assert verdict.duration_sec == pytest.approx(4.0, abs=0.3)


@requires_ffmpeg
def test_rejects_silent_audio_track(tmp_path):
    """Asıl regresyon: ses akışı var ama tamamen boş -> sessiz video."""
    video = tmp_path / "silent.mp4"
    _make(video, audio="silent")

    verdict = q.evaluate(video)

    assert verdict.ok is False
    assert verdict.reason == "audio_silent"
    assert verdict.mean_volume_db is not None and verdict.mean_volume_db < -60


@requires_ffmpeg
def test_rejects_video_without_audio_stream(tmp_path):
    video = tmp_path / "noaudio.mp4"
    _make(video, audio="none")

    verdict = q.evaluate(video)

    assert verdict.ok is False
    assert verdict.reason == "no_audio_stream"


@requires_ffmpeg
def test_rejects_too_short_video(tmp_path):
    video = tmp_path / "short.mp4"
    _make(video, seconds=1, audio="tone")

    verdict = q.evaluate(video)

    assert verdict.ok is False
    assert verdict.reason == "too_short"


def test_rejects_missing_file(tmp_path):
    verdict = q.evaluate(tmp_path / "missing.mp4")

    assert verdict.ok is False
    assert verdict.reason == "video_missing"


def test_unreadable_container_is_not_blocked(tmp_path):
    """Ölçemiyorsak engellemiyoruz: ffprobe olmayan ortamda yayın durmamalı."""
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")

    verdict = q.evaluate(broken)

    assert verdict.ok is True
    assert verdict.reason == "probe_unavailable"


def test_unreadable_container_flags_bgm_silence(tmp_path):
    broken = tmp_path / "broken.mp4"
    broken.write_bytes(b"not a video")

    verdict = q.evaluate(broken, bgm_silence=True)

    assert verdict.ok is True
    assert verdict.checks["bgm_silence"] == "silent"


@requires_ffmpeg
def test_bgm_silence_does_not_block_when_audio_exists(tmp_path):
    """BGM yok ama ses var (sentetik ambient/konuşma): yayın durmamalı."""
    video = tmp_path / "tone.mp4"
    _make(video, audio="tone")

    verdict = q.evaluate(video, bgm_silence=True)

    assert verdict.ok is True
    assert verdict.reason == "audio_present_bgm_missing"
    assert verdict.checks["bgm_silence"] == "silent"


def test_verdict_serializes_for_logging():
    verdict = q.QualityVerdict(ok=False, reason="too_short", duration_sec=1.0)

    payload = verdict.to_dict()

    assert payload["ok"] is False
    assert payload["reason"] == "too_short"
    assert payload["checks"] == {}


# --- Yayın yoluna entegrasyon -------------------------------------------------
#
# Kapının kendisi doğru olabilir ama `_run_publish`'e bağlanmamış olabilir; bu
# yüzden asıl iddia yayın yolu üzerinden ölçülüyor.


def _fake_publishers(monkeypatch, calls):
    from app import main as main_mod

    for name, platform in (
        ("upload_to_youtube", "youtube"),
        ("upload_to_tiktok", "tiktok"),
        ("upload_to_instagram", "instagram"),
        ("upload_to_facebook", "facebook"),
        ("upload_to_threads", "threads"),
        ("upload_video_to_x", "x"),
        ("upload_to_pinterest", "pinterest"),
    ):
        def fake(*a, _p=platform, **k):
            calls.append(_p)
            return {"platform": _p, "status": "success"}

        monkeypatch.setattr(main_mod, name, fake, raising=False)


@requires_ffmpeg
def test_publish_rejects_silent_video_and_keeps_job_claimable(tmp_path, monkeypatch):
    """Sessiz video: yayın olmamalı, iş 'publishing'de kilitlenmemeli."""
    from app import main as main_mod
    from app.errors import QualityGateError
    from app.publish_log import file_sha256

    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))

    video = tmp_path / "20261031-120000-quiet.mp4"
    _make(video, audio="silent")
    calls = []
    _fake_publishers(monkeypatch, calls)

    payload = {
        "job_id": "20261031-120000-quiet",
        "video_path": str(video),
        "video_filename": video.name,
        "title": "Sessiz",
        "video_sha256": file_sha256(str(video)),
        "kind": "video",
    }

    with pytest.raises(QualityGateError) as excinfo:
        main_mod._run_publish(payload)

    assert excinfo.value.reason == "audio_silent"
    assert calls == [], "reddedilen video için hiçbir platform çağrılmamalı"
    # Claim tüketilmedi: satır oluşmadı ya da publishable kaldı.
    from app import jobs as job_store

    row = job_store.get_job(tmp_path, payload["job_id"])
    assert row is None or row["state"] != "publishing"
    assert job_store.has_blocking_job(tmp_path) is False


@requires_ffmpeg
def test_publish_accepts_healthy_video(tmp_path, monkeypatch):
    """Kapı sağlıklı videoyu engellememeli (yanlış pozitif testi)."""
    from app import main as main_mod
    from app.publish_log import file_sha256

    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))

    video = tmp_path / "20261031-120000-good.mp4"
    _make(video, audio="tone")
    calls = []
    _fake_publishers(monkeypatch, calls)

    main_mod._run_publish(
        {
            "job_id": "20261031-120000-good",
            "video_path": str(video),
            "video_filename": video.name,
            "title": "Sağlıklı",
            "video_sha256": file_sha256(str(video)),
            "kind": "video",
        }
    )

    assert calls, "sağlıklı video yayınlanmalıydı"


def test_image_kind_skips_the_gate(tmp_path, monkeypatch):
    """Görsel kartlarda ses akışı beklenmiyor: kapı atlanmalı."""
    from app import main as main_mod

    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))
    image = tmp_path / "card.png"
    image.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 100)

    calls = []
    for name, platform in (("upload_to_x", "x"), ("upload_to_linkedin", "linkedin")):
        def fake(*a, _p=platform, **k):
            calls.append(_p)
            return {"platform": _p, "status": "success"}

        monkeypatch.setattr(main_mod, name, fake, raising=False)

    main_mod._run_publish(
        {
            "job_id": "20261031-120000-card",
            "image_path": str(image),
            "image_filename": image.name,
            "caption": "Kart",
            "kind": "image",
        }
    )

    assert calls, "görsel yayınlanmalıydı"
