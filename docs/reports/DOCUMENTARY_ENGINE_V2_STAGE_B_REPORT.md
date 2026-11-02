# Documentary Engine V2 — Stage B Report

**Status:** COMPLETE — candidate acquisition fabric only. No Stage C+.  
**Date:** 2026-09-24  
**Flag default:** `DOCUMENTARY_ENGINE_V2=false` (unchanged)  
**Behavioral change to production render/TTS/captions/publish:** NONE

---

## Summary

Stage B adds a **multi-source candidate acquisition layer**:

`MediaSearchRequest` → provider registry → `MediaCandidate[]` → dedup → `PreviewReference[]`

**SEARCH RESULT ≠ SELECTED SHOT.** No VisualVerifier. No semantic acceptance. No random generic query fallbacks (`luxury` / `money` / `nature`).

---

## Provider architecture

```
documentary_v2/providers/
  base.py              MediaProvider ABC, license map, health classify
  registry.py          MediaProviderRegistry + priority by capability
  acquisition.py       acquire_candidates() orchestrator
  cache.py             search metadata cache (TTL, no secrets)
  dedup.py             EXACT / LIKELY / UNIQUE + fingerprints
  materialize.py       safe download + integrity (selected only)
  pexels.py            wraps stock_media Pexels helpers
  pixabay.py           wraps stock_media Pixabay helpers
  wikimedia.py         Commons imageinfo + optional Wikipedia pageimage
  internet_archive.py  advancedsearch + metadata file pick
  mixkit.py            HTML scrape — DEGRADED, not default-equal
```

Canonical Stage A types reused/extended: `MediaCandidate`, `MediaAsset`, `AssetProvenance`.

New Stage B schema types: `MediaSearchRequest`, `PreviewReference`, `ProviderCapability`, `ProviderHealth`, `QueryFamily`, `LicensePolicy`, `DuplicateKind`, `DuplicateRelation`, `AcquisitionCounts`, `ProviderSearchEvent`, `AttributionEntry`.

---

## Providers implemented / wrapped

| Provider | Role | Reliability | Notes |
|----------|------|-------------|-------|
| **Pexels** | Stock video/image discovery | stable | Wraps `_list_pexels_video_candidates`; photos via API; license **UNKNOWN** unless raw present (not invented from brand) |
| **Pixabay** | Secondary stock video | stable | Wraps `_list_pixabay_video_candidates` |
| **Wikimedia** | Archive/people/docs stills | stable | Commons `imageinfo` + extmetadata (license, artist, URLs); pageimage fallback does **not** fabricate creator/license |
| **Internet Archive** | Historical/archive | experimental | Bounded search; file pick by format/size — **not** first MP4 |
| **Mixkit** | Optional scrape | **degraded** | Classified clearly; HTML scrape; license UNKNOWN; not equal first-class |

Legacy `stock_media.fetch_stock_clips` / Director paths **unchanged**. Stage B is additive; production still uses legacy when V2 is OFF.

---

## Capabilities

| Capability | Providers (priority order) |
|------------|----------------------------|
| VIDEO_SEARCH | pexels → pixabay → internet_archive → mixkit |
| IMAGE_SEARCH | pexels → wikimedia → internet_archive → pixabay |
| ARCHIVE_SEARCH | wikimedia → internet_archive |
| DOCUMENT_SEARCH | wikimedia |
| PREVIEW_* / LICENSE_* / ATTRIBUTION_* | as declared per adapter |

`registry.providers_for(capability=..., archive_preference=...)` — no if/else sprawl in callers.

---

## Provider health behavior

States: `AVAILABLE` | `DEGRADED` | `UNAVAILABLE` | `RATE_LIMITED` | `AUTH_MISSING`

- Missing API key → `AUTH_MISSING`; provider skipped (not queried)
- HTTP 429 → `RATE_LIMITED`
- Timeout / 5xx → `DEGRADED` / `UNAVAILABLE`
- **Failure ≠ zero results:** `ProviderSearchEvent.failure_reason` set; empty success stays `AVAILABLE` with `raw_result_count=0`
- One provider exception does **not** crash acquisition

---

## Provenance model

Every candidate carries `AssetProvenance` (+ candidate-level preview/download URLs):

provider, source_id, source_url, preview_url, download_url, creator, creator_url, license, license_url, license_raw, license_policy, attribution, media_type, duration/dimensions, archive/stock/synthetic, retrieved_at.

**Never fabricate** license/creator. Empty → `UNKNOWN`.

---

## License normalization

| Policy | Meaning |
|--------|---------|
| KNOWN_REUSABLE | CC0 / PD / explicit reusable |
| ATTRIBUTION_REQUIRED | CC-BY / CC-BY-SA |
| KNOWN_RESTRICTED | all-rights / proprietary signals |
| UNKNOWN | missing or unmapped raw text |

Raw provider string preserved in `license_raw`. Provider name alone never implies rights.

---

## Preview strategy

- `PreviewReference` from `get_preview()` — URL/thumb only
- Does **not** download full media
- Materialization is explicit: `materialize_candidate` → `jobs/{job_id}/media/selected/`
- Candidate metadata may live conceptually under `media/candidates/` (search cache); selected downloads only after choice

---

## Dedup strategy

Evidence ladder:

1. same provider + source_id → `EXACT_DUPLICATE`
2. same canonical URL / download URL → `EXACT_DUPLICATE`
3. same binary SHA-256 → `EXACT_DUPLICATE`
4. perceptual aHash distance ≤ 5 → `LIKELY_DUPLICATE` (confidence)
5. else → `UNIQUE`

Uncertain pairs are **not** auto-merged.

**Counts kept distinct:**

- `search_result_count` / `candidate_count`
- `unique_candidate_count` / `unique_source_asset_count`
- `materialized_asset_count`
- `visual_information_unit_count` = **0** in Stage B (Stage C owns VIU)

---

## Cache strategy

`cache_key(provider, normalized_query, filters)` → SHA-256 prefix.  
In-memory + optional disk TTL (default 1h). No secrets stored.

---

## Materialization safety

- Timeouts, max size (80MB default), stream write + `.partial` cleanup
- Sanitized filenames; `assert_inside(job_dir)` blocks path escape
- Post-download: non-zero size; PIL verify for images; ffprobe when available for video
- Technical validity ≠ semantic validity

---

## Attribution manifest

`build_attribution_manifest([...])` → creator / license / URLs for candidates or assets.  
Not burned into video yet.

---

## Example flow (no semantic accept)

```text
MediaSearchRequest(
  query="Rolex Daytona chronograph",
  query_family="ENTITY_EXACT",
  preferred_media_types=["stock_video"],
  result_limit=3,
)
  → Pexels/Pixabay search (auth permitting)
  → MediaCandidate[] with UNKNOWN license unless raw present
  → dedupe (same id/url collapsed)
  → PreviewReference[] (thumbs / preview URLs)
  → semantic_acceptance = NOT_RUN
```

---

## Tests

**Unit (fixtures / mocks — no live net required):**  
`tests/test_documentary_v2_stage_b.py` — covers required items 1–26 (registry, mapping, provenance, dedup, failure vs empty, cache keys, path escape, invalid media, preview≠materialize, query_family, no random fallback, V2 OFF, pending states).

**Regression:** Stage A + Stage B + render/director/no_slideshow/script_quality/source_diversity/beat_recovery → **152 passed**.

**Live smoke:** `tests/test_documentary_v2_stage_b_live_smoke.py`  
Gate: `STAGE_B_LIVE_SMOKE=true`. Intents: person / product / location / historical.  
Executed this session: **passed** (providers responded without crashing; no visual-match claims).

**NO PUBLISH.**

---

## Live smoke results

| Intent | Outcome |
|--------|---------|
| named person (Marie Curie) | Acquisition completed; archive preference routed to Wikimedia/IA |
| product (Rolex Daytona) | Stock providers queried when keys present |
| location (Golden Gate) | Multi-provider candidate pass |
| historical (Apollo 11) | Archive-oriented providers |

Details vary with credentials/rate limits; failures recorded as health events, not silent zeros.

---

## Known limitations

1. Pexels/Pixabay video APIs rarely return machine-readable license → often `UNKNOWN` (correct, not invented).
2. Mixkit remains scrape-only / DEGRADED.
3. Internet Archive file selection is heuristic — Stage C must still verify meaning.
4. Perceptual hash is simple aHash — not perfect cross-provider crop matching.
5. Stage B is **not wired** into production `pipeline.py` generate path (V2 OFF; no behavior change). Call `acquire_candidates` explicitly for V2 work.
6. Wikipedia pageimage path intentionally leaves creator/license empty/UNKNOWN.

---

## Stage C prerequisites

Stage C (VisualVerifier) can assume:

- Multiple source-aware, license-aware, deduped, previewable `MediaCandidate`s
- `PreviewReference` URLs without full download
- Explicit materialize-on-select API
- Telemetry events with query_family + provider status
- Clear separation: unique **source** ≠ unique **visual information**

Stage C must implement pixel/video inspection and must not treat search ranking as truth.

---

## STOP

Stage B complete. **Do not start** VisualVerifier, multimodal embeddings, Shot Director rewrite, Remotion, AI video, EDL rewrite, or FinalVideoCritic until human approval.
