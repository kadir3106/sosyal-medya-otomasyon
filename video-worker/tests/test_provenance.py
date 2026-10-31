"""Yayın kaydı ↔ üretim işi ↔ manifest zinciri.

Ölçülen kopukluk (düzeltme öncesi): yayın kaydı yalnızca
`published_at/title/kind/platforms` taşıyordu ve `job_id` yoktu. Üretimde her
iş için yazılan `DOCUMENTARY_ENGINE_V2_MANIFEST_<job_id>.json` hiçbir kayda
bağlanmıyordu; kod taramasında manifesği okuyan tüketici sayısı 0'dı. Sonuç:
"bu yayın hangi script, hangi medya, hangi model ve hangi onayla yapıldı?"
sorusu cevaplanamıyordu (Faz 1'in çıkış kriteri).
"""
from app import jobs as job_store
from app.documentary_v2.telemetry import (
    manifest_path,
    read_production_manifest,
    write_production_manifest,
)
from app.documentary_v2.schemas import ProductionManifest
from app.provenance import trace_publication
from app.publish_log import build_publish_entry, load_recent_entries


def _results():
    return [
        {"platform": "youtube", "status": "success", "video_id": "yt1"},
        {"platform": "x", "status": "error", "error": "boom"},
    ]


def test_entry_links_publication_to_job(tmp_path):
    entry = build_publish_entry(
        job_id="20261031-120000-abc123",
        title="Başlık",
        kind="video",
        results=_results(),
        approved_sha256="deadbeef",
        published_at="2026-10-31T12:00:00+00:00",
    )

    assert entry["job_id"] == "20261031-120000-abc123"
    assert entry["approved_sha256"] == "deadbeef"
    assert sorted(entry["platforms"]) == ["x", "youtube"]
    # platforms hâlâ tam sonucu taşıyor (analitik video_id'yi buradan okuyor).
    assert entry["platforms"]["youtube"]["video_id"] == "yt1"


def test_trace_completes_when_job_and_manifest_exist(tmp_path):
    job_id = "20261031-120000-abc123"
    entry = build_publish_entry(
        job_id=job_id, title="T", kind="video", results=_results(),
        approved_sha256="sha-abc",
    )
    job_store.create_job(
        tmp_path, job_id, state="done", topic="konu", title="T",
        payload={"video_sha256": "sha-abc", "final_script": "metin", "video_filename": "v.mp4"},
    )
    write_production_manifest(
        tmp_path, ProductionManifest(job_id=job_id, video_id="vid1", topic="konu")
    )

    trace = trace_publication(tmp_path, entry)

    assert trace["job_id"] == job_id
    assert trace["job"]["final_script"] == "metin"
    assert trace["manifest"] is not None
    assert trace["sha256_match"] is True
    assert trace["complete"] is True


def test_trace_flags_hash_mismatch(tmp_path):
    """Onaylanan dosya ile üretilen dosya farklıysa iz 'complete' olmamalı."""
    job_id = "job-hash"
    entry = build_publish_entry(
        job_id=job_id, title="T", kind="video", results=_results(),
        approved_sha256="approved-hash",
    )
    job_store.create_job(
        tmp_path, job_id, state="done", payload={"video_sha256": "different-hash"}
    )
    write_production_manifest(tmp_path, ProductionManifest(job_id=job_id, video_id="v"))

    trace = trace_publication(tmp_path, entry)

    assert trace["sha256_match"] is False
    assert trace["complete"] is False


def test_trace_without_job_id_is_incomplete_not_an_error(tmp_path):
    """Eski kayıtlarda job_id yok — bu bir hata değil, 'iz yok' bilgisi."""
    trace = trace_publication(tmp_path, {"published_at": "2026-08-01T00:00:00+00:00", "title": "eski"})

    assert trace["job_id"] is None
    assert trace["job"] is None
    assert trace["manifest"] is None
    assert trace["sha256_match"] is None
    assert trace["complete"] is False


def test_trace_handles_missing_manifest(tmp_path):
    """Manifest yazılmamış olabilir (legacy akış); iz yine de işi göstermeli."""
    job_id = "job-no-manifest"
    entry = build_publish_entry(
        job_id=job_id, title="T", kind="video", results=_results(), approved_sha256="h",
    )
    job_store.create_job(tmp_path, job_id, state="done", payload={"video_sha256": "h"})

    trace = trace_publication(tmp_path, entry)

    assert trace["job"] is not None
    assert trace["manifest"] is None
    assert trace["complete"] is False
    assert trace["manifest_path"].endswith(f"DOCUMENTARY_ENGINE_V2_MANIFEST_{job_id}.json")


def test_manifest_path_matches_where_the_writer_writes(tmp_path):
    """Yazıcı ve okuyucu ayrı adlandırırsa zincir sessizce kopar."""
    job_id = "job-name-check"
    written = write_production_manifest(
        tmp_path, ProductionManifest(job_id=job_id, video_id="v")
    )

    assert written == manifest_path(tmp_path, job_id)
    assert read_production_manifest(tmp_path, job_id) is not None


def test_read_manifest_returns_none_on_corrupt_file(tmp_path):
    target = manifest_path(tmp_path, "job-corrupt")
    target.write_text("{not json", encoding="utf-8")

    assert read_production_manifest(tmp_path, "job-corrupt") is None


def test_recent_entries_tolerates_legacy_and_broken_rows(tmp_path):
    """Filtre eski (job_id'siz) kayıtları düşürmemeli."""
    log = tmp_path / "log.json"
    log.write_text(
        '[{"published_at": "2026-09-02T09:00:00+00:00", "title": "legacy"},'
        ' {"published_at": "2026-08-01T09:00:00+00:00", "title": "eski"},'
        ' "bozuk-satir"]',
        encoding="utf-8",
    )

    entries = load_recent_entries(str(log), since_iso="2026-08-27T00:00:00+00:00")

    assert [e["title"] for e in entries] == ["legacy"]


def test_run_publish_records_job_id_end_to_end(tmp_path, monkeypatch):
    """Asıl iddia: gerçek yayın yolu job_id'yi kayda yazıyor mu?

    `_run_publish` üzerinden ölçmek şart — `build_publish_entry`'yi doğrudan
    test etmek, çağrının unutulduğu durumu kaçırırdı (asıl ölçülen kopukluk
    buydu).
    """
    import json

    from app import main as main_mod

    monkeypatch.setattr(main_mod.config, "MEDIA_DIR", str(tmp_path))
    video = tmp_path / "20261031-120000-abc123.mp4"
    video.write_bytes(b"x" * 512)

    for name, platform in (
        ("upload_to_youtube", "youtube"),
        ("upload_to_tiktok", "tiktok"),
        ("upload_to_instagram", "instagram"),
        ("upload_to_facebook", "facebook"),
        ("upload_to_threads", "threads"),
        ("upload_video_to_x", "x"),
        ("upload_to_pinterest", "pinterest"),
    ):
        monkeypatch.setattr(
            main_mod, name,
            lambda *a, _p=platform, **k: {"platform": _p, "status": "success"},
            raising=False,
        )

    from app.publish_log import file_sha256

    digest = file_sha256(str(video))
    main_mod._run_publish(
        {
            "video_path": str(video),
            "video_filename": video.name,
            "title": "Uçtan uca",
            "video_sha256": digest,
            "kind": "video",
        }
    )

    entries = json.loads((tmp_path / "published_log.json").read_text(encoding="utf-8"))
    last = entries[-1]
    # job_id dosya adından türetiliyor (`Path(...).stem`).
    assert last["job_id"] == "20261031-120000-abc123"
    assert last["approved_sha256"] == digest
    assert "youtube" in last["platforms"]
