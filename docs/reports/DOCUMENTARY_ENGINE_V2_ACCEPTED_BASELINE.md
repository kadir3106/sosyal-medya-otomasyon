# Documentary Engine V2 F.1.1 baseline for Stage G

- Reference job: `sf1120260928-185746_d79a71`
- Reference MP4: `video-worker/video-output/DOCUMENTARY_ENGINE_V2_STAGE_F11_REAL_sf1120260928-185746_d79a71.mp4`
- MP4 SHA-256 at Stage G start: `E0EA96684CE948A50AB9421519265E78A95865E4D037AF932B635FBA0C3E2CB1`
- Stage G design approval date: 2026-09-29.
- Formal full-MP4 human acceptance date and decision: `NOT_EVIDENCED`. The existing F.1.1 report says `REVIEW_REQUIRED` and calls for complete human playback; this baseline does not convert that into a human PASS.
- Focused F.1.1 tests reported: 15/15; impacted Stage C/F/F.1 tests reported: 49/49. The repository-wide run was interrupted and has no final PASS summary.
- Known LOW issues carried from the Stage G design: generic opening wording and sparse final portion of the ownership-history graphic.

## Stage G regression invariants

- Do not move, overwrite, edit, or reinterpret the reference MP4, its Stage F.1.1 report, or lineage.
- Canary mode requires an explicit `canary=True`; normal production modes stay unchanged.
- Stage G never publishes or enables global V2 and never calls production routing, `/generate`, queues, schedulers, or publisher entry points.
- Failed canaries retain truthful EDL, manifest, trace, attribution, and human-review diagnostics without invented provenance or human findings.
- Wrong entity, misleading evidence, unsafe provenance, timeline/caption failure, slideshow dominance, and VLM unavailability/rate limit remain fail closed.
- Only completed human reviews of autonomous jobs may count toward the three-distinct-story-type PASS condition.
