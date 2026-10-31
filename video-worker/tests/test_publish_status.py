"""Timeout sonrası platform durum sorgusu (yol haritası Faz 4 kuralı).

Ölçülen boşluk (eklemeden önce): hiçbir yayıncıda durum sorgulayan fonksiyon
yoktu, dolayısıyla "timeout olduysa önce durumu sor" kuralı uygulanamıyordu.
`status="unknown"` tek savunmaydı: retry sunmuyorduk ama işi de kurtaramıyorduk.

Kök neden zamanlamaydı — platform kimliği ancak `upload_to_*` döndüğünde
elimize geçiyordu, timeout tam o anda oluşuyordu. `inflight` kaydı kimliği
üretildiği anda diske yazıyor.
"""
import pytest

from app import publish_status as ps
from app.publishers import publication_status


class _Resp:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


# --- inflight kaydı -----------------------------------------------------------


def test_inflight_roundtrip(tmp_path):
    ps.record_inflight(tmp_path, "job1", "tiktok", {"publish_id": "v_pub_1"})

    assert ps.read_inflight(tmp_path, "job1") == {"tiktok": {"publish_id": "v_pub_1"}}


def test_inflight_records_each_platform_separately(tmp_path):
    ps.record_inflight(tmp_path, "job1", "tiktok", {"publish_id": "v1"})
    ps.record_inflight(tmp_path, "job1", "youtube", {"video_id": "yt1"})

    stored = ps.read_inflight(tmp_path, "job1")
    assert stored["tiktok"]["publish_id"] == "v1"
    assert stored["youtube"]["video_id"] == "yt1"


def test_inflight_ignores_empty_identity(tmp_path):
    """Kimlik yoksa dosya oluşturup 'kayıt var' yanılsaması yaratmamalı."""
    ps.record_inflight(tmp_path, "job1", "tiktok", {})

    assert ps.read_inflight(tmp_path, "job1") == {}


def test_clear_inflight_removes_record(tmp_path):
    ps.record_inflight(tmp_path, "job1", "tiktok", {"publish_id": "v1"})
    ps.clear_inflight(tmp_path, "job1")

    assert ps.read_inflight(tmp_path, "job1") == {}


def test_read_inflight_survives_corrupt_file(tmp_path):
    path = tmp_path / "inflight" / "job1.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")

    assert ps.read_inflight(tmp_path, "job1") == {}


@pytest.fixture(autouse=True)
def _stub_credentials(monkeypatch):
    """Sorgu testlerinde token canlı üretiliyor (diske yazılmıyor)."""
    monkeypatch.setattr(
        ps, "_refresh_credentials", lambda platform: {"access_token": "tok"}
    )


# --- TikTok durum çözümleyici -------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("PUBLISH_COMPLETE", ps.PUBLISHED),
        ("FAILED", ps.FAILED),
        ("PROCESSING_UPLOAD", ps.PENDING),
        ("PROCESSING_DOWNLOAD", ps.PENDING),
        ("SEND_TO_USER_INBOX", ps.PENDING),
        ("SOMETHING_NEW", ps.UNKNOWN),
        ("", ps.UNKNOWN),
    ],
)
def test_tiktok_status_mapping(monkeypatch, raw, expected):
    monkeypatch.setattr(
        publication_status.session, "post",
        lambda *a, **k: _Resp(200, {"data": {"status": raw}, "error": {"code": "ok"}}),
    )

    status = publication_status.resolve_tiktok(
        {"publish_id": "v1", "access_token": "tok"}
    )

    assert status.state == expected, f"{raw} -> {status.state}"


def test_tiktok_published_carries_url(monkeypatch):
    monkeypatch.setattr(
        publication_status.session, "post",
        lambda *a, **k: _Resp(200, {"data": {
            "status": "PUBLISH_COMPLETE", "publicaly_available_post_id": ["123"],
        }}),
    )

    status = publication_status.resolve_tiktok({"publish_id": "v1", "access_token": "t"})

    assert status.is_published
    assert status.url == "https://www.tiktok.com/video/123"


def test_tiktok_failed_carries_reason(monkeypatch):
    monkeypatch.setattr(
        publication_status.session, "post",
        lambda *a, **k: _Resp(200, {"data": {
            "status": "FAILED", "fail_reason": "video_format_check_failed",
        }}),
    )

    status = publication_status.resolve_tiktok({"publish_id": "v1", "access_token": "t"})

    assert status.state == ps.FAILED
    assert "video_format_check_failed" in status.detail


def test_tiktok_http_error_is_unknown_not_published(monkeypatch):
    """API hatasında 'yayınlandı' demek operatörü yanıltır."""
    monkeypatch.setattr(
        publication_status.session, "post", lambda *a, **k: _Resp(503, {})
    )

    status = publication_status.resolve_tiktok({"publish_id": "v1", "access_token": "t"})

    assert status.state == ps.UNKNOWN


def test_tiktok_missing_identity_is_unknown():
    assert publication_status.resolve_tiktok({}).state == ps.UNKNOWN


# --- YouTube durum çözümleyici ------------------------------------------------


@pytest.mark.parametrize(
    "upload,processing,expected",
    [
        ("processed", "succeeded", ps.PUBLISHED),
        ("processed", "", ps.PUBLISHED),
        ("failed", "", ps.FAILED),
        ("uploaded", "processing", ps.PENDING),
        ("", "", ps.PENDING),
    ],
)
def test_youtube_status_mapping(monkeypatch, upload, processing, expected):
    payload = {"items": [{
        "status": {"uploadStatus": upload},
        "processingDetails": {"processingStatus": processing},
    }]}
    monkeypatch.setattr(
        publication_status.session, "get", lambda *a, **k: _Resp(200, payload)
    )

    status = publication_status.resolve_youtube(
        {"video_id": "yt1", "access_token": "t"}
    )

    assert status.state == expected, f"{upload}/{processing} -> {status.state}"


def test_youtube_missing_video_is_unknown(monkeypatch):
    """Kimliği biliyoruz ama video görünmüyor: 'failed' demek güvenli değil."""
    monkeypatch.setattr(
        publication_status.session, "get", lambda *a, **k: _Resp(200, {"items": []})
    )

    status = publication_status.resolve_youtube({"video_id": "yt1", "access_token": "t"})

    assert status.state == ps.UNKNOWN


# --- Ayrımcı: sorgu asla çağıranı düşürmemeli ---------------------------------


def test_query_returns_unknown_for_unsupported_platform(tmp_path):
    status = ps.query(tmp_path, "job1", "linkedin")

    assert status.state == ps.UNKNOWN
    assert "no status API" in status.detail


def test_query_without_inflight_identity_is_unknown(tmp_path):
    status = ps.query(tmp_path, "job1", "tiktok")

    assert status.state == ps.UNKNOWN
    assert "no inflight identity" in status.detail


def test_query_swallows_resolver_exception(tmp_path, monkeypatch):
    """Sorgu patlarsa yayın akışı çökmemeli; belirsizlik 'unknown' demektir."""
    ps.record_inflight(tmp_path, "job1", "tiktok", {"publish_id": "v1"})

    def boom(identity):
        raise RuntimeError("network down")

    monkeypatch.setitem(publication_status.RESOLVERS, "tiktok", boom)

    status = ps.query(tmp_path, "job1", "tiktok")

    assert status.state == ps.UNKNOWN
    assert "network down" in status.detail


def test_query_all_covers_every_platform(tmp_path, monkeypatch):
    ps.record_inflight(tmp_path, "job1", "tiktok", {"publish_id": "v1"})
    monkeypatch.setattr(
        publication_status.session, "post",
        lambda *a, **k: _Resp(200, {"data": {"status": "PUBLISH_COMPLETE"}}),
    )

    statuses = ps.query_all(tmp_path, "job1", ["tiktok", "linkedin"])

    assert [s.platform for s in statuses] == ["tiktok", "linkedin"]
    assert statuses[0].is_published
    assert statuses[1].state == ps.UNKNOWN


def test_inflight_never_persists_access_token(tmp_path):
    """Erişim token'ı diske YAZILMAMALI.

    Kimlik kaydı `media/` altında düz JSON olarak duruyor; token oraya
    yazılırsa sır dosyaya sızar (ve secret scan'in kapsamı dışında kalır).
    Token sorgu anında bellekte ekleniyor.
    """
    ps.record_inflight(
        tmp_path, "job1", "tiktok",
        {"publish_id": "v1", "access_token": "should-not-be-written"},
    )

    raw = (tmp_path / "inflight" / "job1.json").read_text(encoding="utf-8")
    assert "should-not-be-written" not in raw
    assert "access_token" not in raw
    assert ps.read_inflight(tmp_path, "job1")["tiktok"]["publish_id"] == "v1"


def test_query_works_without_stored_token_at_query_time(tmp_path, monkeypatch):
    """Token kayıtta olmasa bile sorgu çalışmalı (token canlı olarak ekleniyor)."""
    ps.record_inflight(tmp_path, "job1", "tiktok", {"publish_id": "v1"})
    seen = {}

    def fake_post(url, **kwargs):
        seen["headers"] = kwargs.get("headers", {})
        return _Resp(200, {"data": {"status": "PUBLISH_COMPLETE"}})

    monkeypatch.setattr(publication_status.session, "post", fake_post)
    monkeypatch.setattr(
        ps, "_refresh_credentials", lambda platform: {"access_token": "live"}
    )

    status = ps.query(tmp_path, "job1", "tiktok")

    assert status.is_published
    assert seen["headers"]["Authorization"] == "Bearer live"


def test_query_reports_unknown_when_credentials_unavailable(tmp_path, monkeypatch):
    """Token yenilenemezse bu 'yayınlanmadı' DEĞİL, 'bilinmiyor' demektir."""
    ps.record_inflight(tmp_path, "job1", "tiktok", {"publish_id": "v1"})
    monkeypatch.setattr(ps, "_refresh_credentials", lambda platform: None)

    status = ps.query(tmp_path, "job1", "tiktok")

    assert status.state == ps.UNKNOWN
    assert "credentials unavailable" in status.detail


# --- Yayın yoluna entegrasyon -------------------------------------------------
#
# Sorgu doğru olabilir ama `_run_publish`'e bağlanmamış olabilir; asıl iddia
# timeout dalı üzerinden ölçülüyor.


def _install_slow_publishers(monkeypatch, *, platform="x"):
    """Tüm yayıncıları, biri timeout'a düşecek şekilde sahtele."""
    import time as _time

    from app import main as main_mod

    def slow(*a, **k):
        _time.sleep(0.4)
        return {"platform": platform, "status": "success"}

    for name in (
        "upload_to_youtube",
        "upload_to_tiktok",
        "upload_to_instagram",
        "upload_to_facebook",
        "upload_to_threads",
        "upload_video_to_x",
        "upload_to_pinterest",
    ):
        monkeypatch.setattr(main_mod, name, slow, raising=False)


def test_timeout_recovered_when_platform_confirms_publication(tmp_path, monkeypatch):
    """Asıl kazanç: sorgu 'yayınlandı' derse iş başarıya döner.

    Önceki davranış: her zaman "bilinmiyor" hatası. Artık platform doğrularsa
    iş `done` olur ve operatör aynı videoyu ikinci kez yayınlamaz.
    """
    from unittest.mock import patch

    from app import main as main_mod
    from app import jobs as job_store

    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))
    video = tmp_path / "job-rec.mp4"
    video.write_bytes(b"x" * 512)
    _install_slow_publishers(monkeypatch)

    # Sorgu "yayınlandı" diyor.
    monkeypatch.setattr(
        main_mod.publish_status, "query_all",
        lambda media, job_id, platforms: [ps.PublishStatus("x", ps.PUBLISHED)],
    )
    monkeypatch.setattr(main_mod.publish_status, "clear_inflight", lambda *a, **k: None)

    from app.publish_log import file_sha256

    body = {
        "job_id": "job-rec",
        "video_path": str(video),
        "video_filename": video.name,
        "title": "Kurtarma",
        "video_sha256": file_sha256(str(video)),
        "kind": "video",
    }
    # Kalite kapısını atla: bu test durum sorgusunu ölçüyor, ffmpeg'i değil.
    monkeypatch.setattr(main_mod, "_verify_publishable_quality", lambda p, k: None)

    with patch("app.main._PUBLISH_TIMEOUT_SECONDS", 0.05):
        result = main_mod._run_publish(body)

    assert result["status_query"][0]["state"] == ps.PUBLISHED
    assert job_store.get_job(tmp_path, "job-rec")["state"] == "done"


def test_timeout_stays_unknown_when_query_cannot_confirm(tmp_path, monkeypatch):
    """Sorgu doğrulayamazsa belirsizlik sürer: retry sunulmaz, iş failed."""
    from unittest.mock import patch

    import pytest as _pytest

    from app import main as main_mod
    from app import jobs as job_store
    from app.errors import PublishOutcomeUnknownError

    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))
    video = tmp_path / "job-unk.mp4"
    video.write_bytes(b"x" * 512)
    _install_slow_publishers(monkeypatch)
    monkeypatch.setattr(
        main_mod.publish_status, "query_all",
        lambda media, job_id, platforms: [ps.PublishStatus("x", ps.UNKNOWN, "no identity")],
    )
    monkeypatch.setattr(main_mod, "_verify_publishable_quality", lambda p, k: None)

    from app.publish_log import file_sha256

    body = {
        "job_id": "job-unk",
        "video_path": str(video),
        "video_filename": video.name,
        "title": "Belirsiz",
        "video_sha256": file_sha256(str(video)),
        "kind": "video",
    }

    with patch("app.main._PUBLISH_TIMEOUT_SECONDS", 0.05):
        with _pytest.raises(PublishOutcomeUnknownError):
            main_mod._run_publish(body)

    assert job_store.get_job(tmp_path, "job-unk")["state"] == "failed"

