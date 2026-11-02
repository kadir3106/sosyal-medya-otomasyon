"""pending.json: yarım yazma, bozuk dosya ve eşzamanlı silme (madde 30).

`pending.json` public bir dosya: catchup, daily_digest, telegram_bot, `/pending`
ve `/media` hepsi okuyor. Bu yüzden yarısı yazılmış bir dosya yalnızca bir log
satırı değil, onay akışının görünmez şekilde kaybolması demek.
"""

import json
import threading
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app import jobs as job_store
from app.daily_digest import build_daily_digest
from app.main import app

client = TestClient(app)


def test_write_pending_mirror_never_exposes_partial_json(tmp_path):
    """Düz `write_text` dosyayı önce sıfırlıyordu; eşzamanlı okuyucu yarım JSON gördü.

    Ölçüm (düzeltme öncesi, Windows): 3000 ardışık yazma sırasında 682 okumanın
    392'si (%57) JSONDecodeError verdi. Boş gövde `read_pending_payload`'ı
    `None`'a düşürüyor, yani /pending 404 dönüyor ve Telegram "bekleyen iş yok"
    sanıyor — oysa gerçek onay hâlâ kurulu.
    """
    payload = {"job_id": "j", "title": "T" * 200, "description": "D" * 2000}
    job_store.write_pending_mirror(tmp_path, payload)

    failures: list[str] = []
    observations = [0]
    lock = threading.Lock()
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            try:
                # Gerçek üretim okuyucusu: kilit + atomik yazıcı arkasındaki yol.
                data = job_store.read_pending_payload(tmp_path)
                if data is not None and "job_id" not in data:
                    with lock:
                        failures.append(f"beklenmeyen icerik: {data!r}"[:100])
                with lock:
                    observations[0] += 1
            except FileNotFoundError:
                # Atomik değiştirme sırasında dosya bir an görünmeyebilir.
                pass
            except (json.JSONDecodeError, ValueError) as exc:
                with lock:
                    failures.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=reader, daemon=True) for _ in range(4)]
    for thread in threads:
        thread.start()
    try:
        for i in range(300):
            job_store.write_pending_mirror(tmp_path, {**payload, "job_id": f"j{i}"})
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=5)

    assert observations[0] > 0, "okuyucu hiç okuma yapmadı — test boş yere geçiyor"
    assert failures == [], f"{len(failures)} bozuk okuma: {failures[:3]}"



def test_corrupt_pending_json_is_quarantined_and_read_as_absent(tmp_path):
    """Bozuk dosya 500 üretmek yerine karantinaya alınır.

    Önce: `/pending` ve `/media` her istekte aynı bozuk baytları yeniden
    ayrıştırıp 500 dönüyordu (ölçüldü: ikisi de 500); tek çıkış yolu elle
    silmekti.
    """
    (tmp_path / "pending.json").write_text('{"job_id": "leg', encoding="utf-8")

    assert job_store.read_pending_payload(tmp_path) is None
    assert not (tmp_path / "pending.json").exists()
    assert (
        tmp_path / "pending.json.corrupt"
    ).read_text(encoding="utf-8") == '{"job_id": "leg'


def test_invalid_utf8_pending_json_is_quarantined(tmp_path):
    """Yarım çok baytlı karakter `UnicodeDecodeError` verir — bu da yakalanmalı.

    `jsonstore.read_json` yalnızca JSONDecodeError'ı yakalıyor ve dosyayı yerinde
    bırakıyor; pending.json için bu "kalıcı 500" demek olurdu.
    """
    (tmp_path / "pending.json").write_bytes(b'{"title": "Kali\xff\xfe"}')

    assert job_store.read_pending_payload(tmp_path) is None
    assert not (tmp_path / "pending.json").exists()
    assert (tmp_path / "pending.json.corrupt").exists()


def test_json_array_pending_payload_is_treated_as_absent(tmp_path):
    """Geçerli JSON ama nesne değil: eski kod `.get` çağrısında çökerdi."""
    (tmp_path / "pending.json").write_text("[1, 2]", encoding="utf-8")

    assert job_store.read_pending_payload(tmp_path) is None


def test_get_pending_returns_404_for_corrupt_file(tmp_path):
    (tmp_path / "pending.json").write_text('{"job_id": "leg', encoding="utf-8")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/pending")

    assert response.status_code == 404


def test_get_media_returns_404_for_corrupt_pending(tmp_path):
    (tmp_path / "x.mp4").write_bytes(b"VIDEO")
    (tmp_path / "pending.json").write_text('{"job_id": "leg', encoding="utf-8")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/x.mp4")

    assert response.status_code == 404


def test_daily_digest_survives_corrupt_pending(tmp_path):
    """Özet mesajı bozuk yüzünden hiç gönderilmemesi de bir sessiz kayıp."""
    (tmp_path / "pending.json").write_text('{"title": ', encoding="utf-8")

    message = build_daily_digest(str(tmp_path))

    assert "Bekleyen onay yok." in message


def test_daily_digest_reports_pending_from_mirror(tmp_path):
    """Paylaşılan okuyucu gerçek yükü hâlâ bulmalı (aşırı karantinaya alma nöbeti)."""
    (tmp_path / "pending.json").write_text(
        json.dumps({"job_id": "p1", "title": "Taslak Video"}), encoding="utf-8"
    )

    message = build_daily_digest(str(tmp_path))

    assert "Taslak Video" in message


def test_write_pending_mirror_still_raises_when_replace_really_fails(
    tmp_path, monkeypatch
):
    """Retry körlemesine yutmamalı: dosya gerçekten kilitliyse çağıran duymalı."""
    calls = []

    def fake_write_atomic(path, payload):
        calls.append(path)
        raise PermissionError("file is locked by another process")

    monkeypatch.setattr(job_store, "write_atomic", fake_write_atomic)
    monkeypatch.setattr(job_store.time, "sleep", lambda _delay: None)

    with pytest.raises(PermissionError):
        job_store.write_pending_mirror(tmp_path, {"job_id": "j1"})

    assert len(calls) == 10, f"10 deneme beklenirdi, {len(calls)} yapıldı"


def test_unlink_with_retry_tolerates_concurrent_delete(tmp_path):
    """Eşzamanlı silmede kaybeden thread Windows'ta PermissionError alıyordu."""
    hits = 0
    for _ in range(10):
        target = tmp_path / "pending.json"
        target.write_text("{}", encoding="utf-8")
        errors: list[str] = []
        lock = threading.Lock()
        barrier = threading.Barrier(8)

        def worker():
            try:
                barrier.wait(timeout=5)
                job_store._unlink_with_retry(target)
            except Exception as exc:  # noqa: BLE001 - hangi hata çıktığını istiyoruz
                with lock:
                    errors.append(f"{type(exc).__name__}: {exc}")

        threads = [threading.Thread(target=worker) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert not target.exists()
        if errors:
            hits += 1

    assert hits == 0, f"{hits}/10 denemede eşzamanlı silme hata verdi"


def test_unlink_with_retry_still_raises_when_delete_really_fails(tmp_path, monkeypatch):
    target = tmp_path / "pending.json"
    target.write_text("{}", encoding="utf-8")

    def fake_unlink(self, missing_ok=False):
        raise PermissionError("file is locked by another process")

    monkeypatch.setattr(Path, "unlink", fake_unlink)
    monkeypatch.setattr(job_store.time, "sleep", lambda _delay: None)

    with pytest.raises(PermissionError):
        job_store._unlink_with_retry(target, attempts=2)



def test_write_pending_mirror_leaves_no_temp_files(tmp_path):
    """Atomik yazıcı geçici dosya bırakmamalı (media dizini `/media` ile dışa açık)."""
    job_store.write_pending_mirror(tmp_path, {"job_id": "j1"})

    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "pending.json"]
    assert leftovers == [], f"geçici dosya kaldı: {leftovers}"
