"""Documentary Engine V2 Stage B — provider fabric, provenance, dedup (fixture-based)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.documentary_v2.pipeline_mode import documentary_engine_v2_enabled, resolve_pipeline_mode
from app.documentary_v2.providers.acquisition import (
    acquire_candidates,
    build_attribution_manifest,
)
from app.documentary_v2.providers.base import map_license
from app.documentary_v2.providers.cache import SearchCache, cache_key
from app.documentary_v2.providers.dedup import (
    average_hash_bytes,
    binary_hash,
    compare_candidates,
    dedupe_candidates,
)
from app.documentary_v2.providers.internet_archive import InternetArchiveProvider
from app.documentary_v2.providers.materialize import (
    MaterializeError,
    assert_inside,
    materialize_candidate,
    safe_filename,
)
from app.documentary_v2.providers.mixkit import MixkitProvider
from app.documentary_v2.providers.pexels import PexelsProvider
from app.documentary_v2.providers.pixabay import PixabayProvider
from app.documentary_v2.providers.registry import MediaProviderRegistry, default_registry
from app.documentary_v2.providers.wikimedia import WikimediaProvider
from app.documentary_v2.schemas import (
    AssetProvenance,
    DuplicateKind,
    LicenseState,
    MediaAsset,
    MediaCandidate,
    MediaSearchRequest,
    PipelineMode,
    ProviderCapability,
    ProviderHealth,
)


@pytest.fixture(autouse=True)
def _v2_off(monkeypatch):
    monkeypatch.setenv("DOCUMENTARY_ENGINE_V2", "false")
    monkeypatch.setenv("DIRECTOR_ENABLED", "false")
    yield


def test_registry_returns_providers_by_capability():
    reg = default_registry()
    vids = reg.providers_for(ProviderCapability.VIDEO_SEARCH, include_disabled=True)
    names = [p.name for p in vids]
    assert "pexels" in names
    assert "pixabay" in names
    archives = reg.providers_for(ProviderCapability.ARCHIVE_SEARCH)
    assert any(p.name == "wikimedia" for p in archives)


def test_disabled_provider_not_queried(monkeypatch):
    monkeypatch.setenv("PEXELS_API_KEY", "")
    reg = MediaProviderRegistry(
        [PexelsProvider(api_key=""), PixabayProvider(api_key="test")]
    )
    enabled = [p.name for p in reg.providers_for(ProviderCapability.VIDEO_SEARCH)]
    assert "pexels" not in enabled
    assert "pixabay" in enabled

    req = MediaSearchRequest(
        query="rolex daytona", query_family="ENTITY_EXACT", result_limit=2
    )
    with patch.object(PixabayProvider, "search", return_value=[]) as mock_px:
        with patch.object(PexelsProvider, "search") as mock_pe:
            acquire_candidates(req, registry=reg, fetch_previews=False)
            mock_pe.assert_not_called()
            mock_px.assert_called_once()


def test_pexels_maps_to_canonical_candidate():
    prov = PexelsProvider(api_key="fake")
    row = {
        "provider": "pexels",
        "asset_id": 99,
        "download_url": "https://cdn.example/v.mp4",
        "provider_rank_score": 1.0,
        "metadata": {
            "url": "https://www.pexels.com/video/99/",
            "user": "Alice",
            "duration": 12,
            "width": 1080,
            "height": 1920,
            "id": 99,
        },
    }
    req = MediaSearchRequest(query="daytona chronograph", query_family="ENTITY_EXACT")
    cand = prov._map_row(row, req)
    assert cand.candidate_id == "cand:pexels:99"
    assert cand.provenance.creator == "Alice"
    assert cand.provenance.license == LicenseState.UNKNOWN.value
    assert cand.query_family == "ENTITY_EXACT"


def test_pixabay_maps_to_canonical_candidate():
    prov = PixabayProvider(api_key="fake")
    row = {
        "asset_id": 55,
        "download_url": "https://cdn.example/p.mp4",
        "metadata": {
            "user": "Bob",
            "page_url": "https://pixabay.com/videos/55/",
            "id": 55,
        },
    }
    cand = prov._map_row(
        row, MediaSearchRequest(query="q", query_family="ENTITY_ACTION")
    )
    assert cand.candidate_id == "cand:pixabay:55"
    assert cand.provenance.creator == "Bob"
    assert cand.provenance.license == "UNKNOWN"


def test_wikimedia_retains_license_metadata():
    prov = WikimediaProvider()
    row = {
        "title": "File:Test.jpg",
        "imageinfo": [
            {
                "url": "https://upload.wikimedia.org/test.jpg",
                "thumburl": "https://upload.wikimedia.org/thumb.jpg",
                "descriptionurl": "https://commons.wikimedia.org/wiki/File:Test.jpg",
                "width": 800,
                "height": 600,
                "user": "Uploader",
                "extmetadata": {
                    "LicenseShortName": {"value": "CC BY-SA 4.0"},
                    "LicenseUrl": {
                        "value": "https://creativecommons.org/licenses/by-sa/4.0/"
                    },
                    "Artist": {"value": "Jane Doe"},
                },
            }
        ],
    }
    cand = prov._map_row(
        row, MediaSearchRequest(query="historical bridge", query_family="ARCHIVE")
    )
    assert cand.provenance.archive is True
    assert cand.provenance.creator == "Jane Doe"
    assert cand.license_policy == "ATTRIBUTION_REQUIRED"
    assert cand.provenance.license_url.startswith("https://creativecommons.org")


def test_internet_archive_maps_when_valid():
    ia = InternetArchiveProvider()
    with patch.object(
        ia,
        "_metadata",
        return_value={
            "files": [
                {"name": "item_files.xml", "format": "Metadata", "size": 100},
                {"name": "clip_512kb.mp4", "format": "h.264", "size": 2_000_000},
                {"name": "huge_master.avi", "format": "MPEG4", "size": 900_000_000},
            ],
            "metadata": {"creator": "Public Domain Project", "licenseurl": ""},
        },
    ):
        doc = {
            "identifier": "testitem",
            "creator": "Public Domain Project",
            "licenseurl": "",
        }
        cand = ia._item_to_candidate(
            doc, MediaSearchRequest(query="apollo 11", query_family="ARCHIVE")
        )
    assert cand is not None
    assert "clip_512kb.mp4" in cand.download_url
    assert "huge_master.avi" not in cand.download_url
    assert cand.provenance.license == "UNKNOWN"
    assert cand.provenance.archive is True


def test_unknown_license_remains_unknown():
    state, policy = map_license(raw="")
    assert state == "UNKNOWN"
    assert policy == "UNKNOWN"


def test_creator_not_fabricated_on_wikipedia_pageimage():
    prov = WikimediaProvider()
    cand = prov._map_row(
        {
            "_wiki_person": {
                "asset_id": "wiki:abc",
                "download_url": "https://example/img.jpg",
                "page_url": "https://en.wikipedia.org/wiki/X",
            }
        },
        MediaSearchRequest(query="Person Name", query_family="ARCHIVE"),
    )
    assert cand.provenance.creator == ""
    assert cand.provenance.license == "UNKNOWN"


def _cand(provider, sid, url="", dl="", binary="", perceptual=""):
    return MediaCandidate(
        candidate_id=f"cand:{provider}:{sid}",
        provenance=AssetProvenance(
            provider=provider,
            source_id=str(sid),
            source_url=url,
            download_url=dl,
            license="UNKNOWN",
        ),
        download_url=dl,
        content_fingerprint=binary,
        perceptual_fingerprint=perceptual,
    )


def test_same_provider_source_id_dedups():
    a, b = _cand("pexels", "1"), _cand("pexels", "1", url="https://other")
    rel = compare_candidates(a, b)
    assert rel.kind == DuplicateKind.EXACT_DUPLICATE.value
    assert "same_source_id" in rel.evidence


def test_same_canonical_url_dedups():
    a = _cand("pexels", "1", url="https://Example.com/x/?utm=1")
    b = _cand("pixabay", "9", url="https://example.com/x")
    rel = compare_candidates(a, b)
    assert rel.kind == DuplicateKind.EXACT_DUPLICATE.value
    assert "same_url" in rel.evidence


def test_binary_hash_exact_duplicate(tmp_path: Path):
    f1 = tmp_path / "a.bin"
    f2 = tmp_path / "b.bin"
    f1.write_bytes(b"identical-bytes-123")
    f2.write_bytes(b"identical-bytes-123")
    h = binary_hash(f1)
    assert h == binary_hash(f2)
    a = _cand("pexels", "1", binary=h)
    b = _cand("pixabay", "2", binary=h)
    assert compare_candidates(a, b).kind == DuplicateKind.EXACT_DUPLICATE.value


def test_perceptual_likely_duplicate():
    data = b"\x00" * 100 + b"\xff" * 100
    ph = average_hash_bytes(data)
    a = _cand("pexels", "1", perceptual=ph)
    b = _cand("pixabay", "2", perceptual=ph)
    rel = compare_candidates(a, b)
    assert rel.kind == DuplicateKind.LIKELY_DUPLICATE.value
    assert "perceptual_similarity" in rel.evidence


def test_different_crops_not_auto_unique_source_claim():
    ph = "ahash:ffffffffffffffff"
    a = _cand("pexels", "10", perceptual=ph)
    b = _cand("pexels", "11", perceptual=ph)
    marked, _rels, counts = dedupe_candidates([a, b])
    assert counts.unique_candidate_count == 1
    assert marked[1].duplicate_kind == DuplicateKind.LIKELY_DUPLICATE.value
    assert counts.visual_information_unit_count == 0


def test_provider_failure_distinguished_from_zero_results():
    reg = MediaProviderRegistry([PexelsProvider(api_key="k")])
    req = MediaSearchRequest(query="q", job_id="j1")
    p = reg.get("pexels")
    p.set_health(ProviderHealth.RATE_LIMITED, "429")
    with patch.object(PexelsProvider, "search", side_effect=RuntimeError("RATE_LIMITED")):
        result = acquire_candidates(req, registry=reg, fetch_previews=False)
    assert result.events[0].status == ProviderHealth.RATE_LIMITED.value
    assert result.events[0].failure_reason
    assert result.events[0].raw_result_count == 0
    assert result.candidates == []


def test_provider_timeout_does_not_crash_registry():
    good = MagicMock()
    good.name = "pixabay"
    good.capabilities = frozenset({ProviderCapability.VIDEO_SEARCH})
    good.reliability = "stable"
    good.is_enabled.return_value = True
    good.supports = lambda cap: True
    good.health = ProviderHealth.AVAILABLE
    good.last_failure = ""
    good.search.return_value = [_cand("pixabay", "1", url="https://x/1")]
    good.set_health = MagicMock()

    reg = MediaProviderRegistry()
    reg.register(PexelsProvider(api_key="k"))
    reg.register(good)

    with patch.object(PexelsProvider, "search", side_effect=TimeoutError("timed out")):
        result = acquire_candidates(
            MediaSearchRequest(query="q", result_limit=2),
            registry=reg,
            fetch_previews=False,
        )
    assert any(e.provider == "pixabay" and e.raw_result_count == 1 for e in result.events)
    assert any(e.provider == "pexels" and e.failure_reason for e in result.events)


def test_rate_limited_state_recorded():
    p = PexelsProvider(api_key="k")
    p.set_health(ProviderHealth.RATE_LIMITED, "429")
    assert p.health == ProviderHealth.RATE_LIMITED


def test_search_cache_keys_include_provider_query_filter():
    k1 = cache_key("pexels", "Rolex", filters={"limit": 5, "orientation": "portrait"})
    k2 = cache_key("pexels", "Rolex", filters={"limit": 8, "orientation": "portrait"})
    k3 = cache_key("pixabay", "Rolex", filters={"limit": 5, "orientation": "portrait"})
    assert k1 != k2
    assert k1 != k3
    cache = SearchCache(ttl_sec=60)
    cache.set(k1, [{"ok": 1}])
    assert cache.get(k1) == [{"ok": 1}]


def test_untrusted_remote_filename_cannot_escape_job_directory(tmp_path: Path):
    name = safe_filename("cand:pexels:1", "https://evil.example/../../etc/passwd")
    assert ".." not in name
    dest = tmp_path / "media" / "selected" / name
    dest.parent.mkdir(parents=True)
    dest.write_bytes(b"x")
    assert_inside(tmp_path, dest)
    with pytest.raises(MaterializeError):
        assert_inside(tmp_path, Path("/tmp/escape.mp4"))


def test_invalid_downloaded_media_rejected(tmp_path: Path):
    cand = _cand("pexels", "1", dl="https://example.com/a.jpg")
    cand.provenance.media_type = "stock_photo"
    cand.provenance.download_url = "https://example.com/a.jpg"

    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.headers = {"Content-Type": "image/jpeg"}
    mock_resp.iter_content = MagicMock(return_value=[b"not-a-real-image"])
    mock_sess = MagicMock()
    mock_sess.get.return_value = mock_resp

    with pytest.raises(MaterializeError):
        materialize_candidate(cand, job_dir=tmp_path, session=mock_sess)


def test_preview_does_not_force_full_materialization():
    prov = PexelsProvider(api_key="k")
    cand = prov._map_row(
        {
            "asset_id": 1,
            "download_url": "https://cdn.example/full.mp4",
            "preview_url": "https://cdn.example/thumb.jpg",
            "metadata": {"url": "https://pexels.com/1", "user": "A", "id": 1},
        },
        MediaSearchRequest(query="q"),
    )
    prev = prov.get_preview(cand)
    assert prev.preview_url.endswith("thumb.jpg")
    assert prev.local_path == ""


def test_candidate_is_not_media_asset():
    c = _cand("pexels", "1")
    assert not isinstance(c, MediaAsset)


def test_query_family_survives_telemetry():
    reg = MediaProviderRegistry([PixabayProvider(api_key="k")])
    with patch.object(PixabayProvider, "search", return_value=[_cand("pixabay", "1")]):
        result = acquire_candidates(
            MediaSearchRequest(query="q", query_family="ENTITY_CONTEXT", job_id="j"),
            registry=reg,
            fetch_previews=False,
        )
    assert result.events[0].query_family == "ENTITY_CONTEXT"
    assert result.request.query_family == "ENTITY_CONTEXT"


def test_no_random_generic_fallback_executed():
    reg = MediaProviderRegistry([PexelsProvider(api_key="k")])
    with patch.object(PexelsProvider, "search", return_value=[]):
        result = acquire_candidates(
            MediaSearchRequest(query="obscure-entity-xyz", query_family="ENTITY_EXACT"),
            registry=reg,
            fetch_previews=False,
        )
    assert result.candidates == []
    assert result.unique_candidates == []


def test_v2_off_preserves_legacy_mode():
    assert documentary_engine_v2_enabled() is False
    assert resolve_pipeline_mode() == PipelineMode.LEGACY_STOCK


def test_pending_states_unchanged():
    from app import jobs as job_store

    assert "awaiting_approval" in job_store.JOB_STATES


def test_attribution_manifest_from_candidates():
    c = _cand("wikimedia", "x", url="https://commons/x")
    c.provenance.creator = "Artist"
    c.provenance.license = "CC_BY_SA"
    c.license_policy = "ATTRIBUTION_REQUIRED"
    entries = build_attribution_manifest([c])
    assert entries[0].creator == "Artist"
    assert entries[0].license_policy == "ATTRIBUTION_REQUIRED"


def test_mixkit_marked_degraded():
    m = MixkitProvider()
    assert m.reliability == "degraded"
    assert m.health == ProviderHealth.DEGRADED


def test_acquisition_example_pipeline_no_semantic_accept():
    rows = [
        {
            "asset_id": 1,
            "download_url": "https://cdn/a.mp4",
            "metadata": {"url": "https://pexels.com/1", "user": "A", "id": 1},
        },
        {
            "asset_id": 1,
            "download_url": "https://cdn/a.mp4",
            "metadata": {"url": "https://pexels.com/1", "user": "A", "id": 1},
        },
        {
            "asset_id": 2,
            "download_url": "https://cdn/b.mp4",
            "metadata": {"url": "https://pexels.com/2", "user": "B", "id": 2},
        },
    ]
    pexels = PexelsProvider(api_key="k")
    req = MediaSearchRequest(query="daytona", query_family="ENTITY_EXACT")
    mapped = [pexels._map_row(r, req) for r in rows]
    marked, _rels, counts = dedupe_candidates(mapped)
    assert counts.candidate_count == 3
    assert counts.unique_candidate_count == 2
    assert all(c.duplicate_kind for c in marked)
