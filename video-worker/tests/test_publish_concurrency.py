"""Legacy/DB-satırsız yayın yolunda çift /publish yarışı.

`/publish` senkron `def` olduğu için FastAPI onu threadpool'da çalıştırır: iki
istek gerçekten paraleldir. `claim_for_publish` bilinmeyen iş için önce
`SELECT` ile karar veriyordu (denetle-ve-yaz); iki istek de geçip aynı videoyu
iki kez kamuya açık yayınlıyordu. Ölçüm: 2 başarılı yayın, 8 yükleme.

Artık satır koşullu INSERT ile talep ediliyor ve birincil anahtar hakem.
"""
import tempfile
import threading
import time
from pathlib import Path

from app import jobs as job_store
from app import main as main_mod

MEDIA = Path(tempfile.mkdtemp(prefix="publish-race-"))


def _payload(video):
    return {
        "video_path": str(video),
        "video_filename": video.name,
        "title": "Legacy",
        "kind": "video",
    }


def _install_fakes(monkeypatch, uploads, lock):
    """Gerçek yayıncıların sözleşmesini taklit et: platform/status alanları.

    Koşullu platformlar (threads/x/pinterest) da sahteleniyor: `.env`'de kimlik
    varsa gerçek yayıncı çağrılır ve test ağa çıkardı (ölçüldü: api.x.com 400).
    """
    called = []

    def make(platform):
        def fake(*args, **kwargs):
            with lock:
                uploads.append(platform)
            time.sleep(0.2)  # ağ gecikmesi: yarışın görünmesi için
            return {"platform": platform, "status": "success"}

        return fake

    for name, platform in (
        ("upload_to_youtube", "youtube"),
        ("upload_to_tiktok", "tiktok"),
        ("upload_to_instagram", "instagram"),
        ("upload_to_facebook", "facebook"),
        ("upload_to_threads", "threads"),
        ("upload_video_to_x", "x"),
        ("upload_to_pinterest", "pinterest"),
    ):
        monkeypatch.setattr(main_mod, name, make(platform), raising=False)
        called.append(name)
    assert len(called) == 7


def _race(payload, n=2):
    """n eşzamanlı /publish; sonuçları ('ok' | hata adı) olarak döndürür."""
    results = []
    lock = threading.Lock()

    def worker():
        try:
            main_mod._run_publish(payload)
            outcome = "ok"
        except Exception as exc:  # noqa: BLE001 - ölçüm: hangi hata çıktığını istiyoruz
            outcome = type(exc).__name__
        with lock:
            results.append(outcome)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def test_concurrent_publish_of_unknown_job_uploads_once(tmp_path, monkeypatch):
    """DB satırı olmayan (legacy/curl) iş: aynı anda 2 yayın -> tek yükleme."""
    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))
    video = tmp_path / "legacy-123.mp4"
    video.write_bytes(b"x" * 1024)

    uploads, lock = [], threading.Lock()
    _install_fakes(monkeypatch, uploads, lock)

    results = _race(_payload(video))

    assert results.count("ok") == 1, f"çift kamuya açık yayın: {results}"
    assert "AlreadyPublishedError" in results
    # Tek yayın: platform başına 1 yükleme. Çift yayında her platform 2 kez çağrılır.
    per_platform = {p: uploads.count(p) for p in set(uploads)}
    assert set(per_platform.values()) == {1}, per_platform
    assert len(uploads) >= 4, uploads


def test_concurrent_publish_of_known_job_uploads_once(tmp_path, monkeypatch):
    """DB satırı olan iş: zaten atomikti (UPDATE ... WHERE state NOT IN)."""
    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))
    video = tmp_path / "job-abc.mp4"
    video.write_bytes(b"x" * 1024)
    # Kurulum thread dışında: create_job UPSERT olduğu için içeride çağrılırsa
    # 'publishing' durumunu geri alır ve yarışı sahte biçimde açar.
    job_store.create_job(tmp_path, "job-abc", kind="video", state="awaiting_approval")

    uploads, lock = [], threading.Lock()
    _install_fakes(monkeypatch, uploads, lock)

    results = _race(_payload(video))

    assert results.count("ok") == 1, results
    per_platform = {p: uploads.count(p) for p in set(uploads)}
    assert set(per_platform.values()) == {1}, per_platform


def test_unknown_job_claim_creates_row_so_it_can_be_tracked(tmp_path):
    """Talep edilen bilinmeyen iş artık izlenebilir: 'publishing' satırı oluşur."""
    assert job_store.claim_for_publish(tmp_path, "legacy-999", kind="image") is True

    row = job_store.get_job(tmp_path, "legacy-999")
    assert row is not None
    assert row["state"] == "publishing"
    assert row["kind"] == "image"
    # Aynı iş için ikinci talep reddedilmeli.
    assert job_store.claim_for_publish(tmp_path, "legacy-999") is False


def test_crashed_publish_does_not_lock_generate_forever(tmp_path, monkeypatch):
    """Beklenmeyen çökme satırı 'publishing'de bırakıp /generate'i kilitlememeli."""
    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))
    video = tmp_path / "legacy-crash.mp4"
    video.write_bytes(b"x" * 1024)

    def boom(*args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(main_mod, "upload_to_youtube", boom)
    monkeypatch.setattr(main_mod, "upload_to_tiktok", boom)
    monkeypatch.setattr(main_mod, "upload_to_instagram", boom)
    monkeypatch.setattr(main_mod, "upload_to_facebook", boom)
    # ThreadPoolExecutor istisnaları sonuç sözlüğüne çeviriyor; bu yüzden
    # log/append aşamasında patlatıyoruz — yani gerçekten "beklenmeyen" bir yol.
    monkeypatch.setattr(
        main_mod, "append_publish_log", boom, raising=False
    )

    try:
        main_mod._run_publish(_payload(video))
    except Exception:  # noqa: BLE001 - çökme bekleniyor
        pass

    row = job_store.get_job(tmp_path, "legacy-crash")
    assert row is not None, "bilinmeyen iş satırı oluşmalıydı"
    # 'publishing' kalsaydı has_blocking_job True döner ve /generate 409 verirdi.
    assert row["state"] == "failed", row["state"]
    assert job_store.has_blocking_job(tmp_path) is False
