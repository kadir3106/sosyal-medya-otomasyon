# Documentary Engine V2 — Stage F Report

**Date:** 2026-09-25T08:38:15
**Job:** `sf20260925-083746_55d45a`
**Topic:** Who really owns Rolex?
**DOCUMENTARY_ENGINE_V2 default:** OFF
**Publish:** NO
**Human review:** REQUIRED before any Stage completion claim

## FINAL VERIFIED SCRIPT

Rolex is not a normal company. Hans Wilsdorf founded the brand in the early twentieth century. Today a private foundation owns Rolex, not public shareholders. That ownership structure keeps control inside the Wilsdorf foundation. The watches are still made in Switzerland with deliberate craftsmanship. So the crown on the dial marks a foundation-owned empire, not a public ticker.

## STORY BEATS

```json
[
  {
    "beat_id": "beat:0:hook",
    "spoken_span": "Rolex is not a normal company.",
    "narrative_role": "hook",
    "primary_entities": [
      "Rolex"
    ],
    "secondary_entities": [],
    "semantic_domain": "luxury_watch",
    "claim_ids": [],
    "story_function": "",
    "required_visual_concept": "Rolex luxury watch close-up crown dial",
    "motion_requirement": "",
    "evidence_requirement": "",
    "authenticity_requirement": "",
    "preferred_media_types": [],
    "forbidden_visual_concepts": [],
    "estimated_duration": 3.0,
    "fallback_policy": "",
    "importance": "important",
    "start_time": null,
    "end_time": null
  },
  {
    "beat_id": "beat:1:person",
    "spoken_span": "Hans Wilsdorf founded the brand in the early twentieth century.",
    "narrative_role": "person",
    "primary_entities": [
      "Hans Wilsdorf"
    ],
    "secondary_entities": [],
    "semantic_domain": "person_history",
    "claim_ids": [],
    "story_function": "",
    "required_visual_concept": "Hans Wilsdorf founder portrait historical",
    "motion_requirement": "",
    "evidence_requirement": "",
    "authenticity_requirement": "",
    "preferred_media_types": [],
    "forbidden_visual_concepts": [],
    "estimated_duration": 4.0,
    "fallback_policy": "",
    "importance": "important",
    "start_time": null,
    "end_time": null
  },
  {
    "beat_id": "beat:2:ownership",
    "spoken_span": "Today a private foundation owns Rolex, not public shareholders.",
    "narrative_role": "ownership",
    "primary_entities": [
      "Rolex",
      "Hans Wilsdorf Foundation"
    ],
    "secondary_entities": [],
    "semantic_domain": "luxury_watch_ownership",
    "claim_ids": [],
    "story_function": "",
    "required_visual_concept": "foundation ownership relationship Rolex",
    "motion_requirement": "",
    "evidence_requirement": "EVIDENCE_REQUIRED",
    "authenticity_requirement": "",
    "preferred_media_types": [],
    "forbidden_visual_concepts": [],
    "estimated_duration": 4.5,
    "fallback_policy": "",
    "importance": "important",
    "start_time": null,
    "end_time": null
  },
  {
    "beat_id": "beat:3:reveal",
    "spoken_span": "That ownership structure keeps control inside the Wilsdorf foundation.",
    "narrative_role": "reveal",
    "primary_entities": [
      "Hans Wilsdorf Foundation",
      "Rolex"
    ],
    "secondary_entities": [],
    "semantic_domain": "luxury_watch_ownership",
    "claim_ids": [],
    "story_function": "",
    "required_visual_concept": "Wilsdorf foundation controls Rolex",
    "motion_requirement": "",
    "evidence_requirement": "EVIDENCE_REQUIRED",
    "authenticity_requirement": "",
    "preferred_media_types": [],
    "forbidden_visual_concepts": [],
    "estimated_duration": 4.0,
    "fallback_policy": "",
    "importance": "important",
    "start_time": null,
    "end_time": null
  },
  {
    "beat_id": "beat:4:process",
    "spoken_span": "The watches are still made in Switzerland with deliberate craftsmanship.",
    "narrative_role": "process",
    "primary_entities": [
      "Rolex"
    ],
    "secondary_entities": [],
    "semantic_domain": "process",
    "claim_ids": [],
    "story_function": "",
    "required_visual_concept": "Swiss watchmaking manufacturing craftsmanship Geneva",
    "motion_requirement": "REQUIRED",
    "evidence_requirement": "",
    "authenticity_requirement": "",
    "preferred_media_types": [],
    "forbidden_visual_concepts": [],
    "estimated_duration": 4.5,
    "fallback_policy": "",
    "importance": "important",
    "start_time": null,
    "end_time": null
  },
  {
    "beat_id": "beat:5:payoff",
    "spoken_span": "So the crown on the dial marks a foundation-owned empire, not a public ticker.",
    "narrative_role": "payoff",
    "primary_entities": [
      "Rolex"
    ],
    "secondary_entities": [],
    "semantic_domain": "luxury_watch",
    "claim_ids": [],
    "story_function": "",
    "required_visual_concept": "Rolex crown logo dial close-up",
    "motion_requirement": "",
    "evidence_requirement": "",
    "authenticity_requirement": "",
    "preferred_media_types": [],
    "forbidden_visual_concepts": [],
    "estimated_duration": 4.0,
    "fallback_policy": "",
    "importance": "important",
    "start_time": null,
    "end_time": null
  }
]
```

## SHOT REQUIREMENTS / SELECTIONS

```json
[
  {
    "shot_id": "shot:beat:0:hook:0",
    "beat_id": "beat:0:hook",
    "asset_id": "cand:pexels:3809175",
    "candidate_id": "cand:pexels:3809175",
    "visual_information_id": "viu:rolex:crown",
    "shot_requirement_id": "",
    "verification_id": "",
    "selection_reason": "",
    "why_selected": "human_inspected_targeted_repair;file=cand_pexels_3809175.jpeg",
    "why_alternatives_lost": [],
    "score_breakdown": {},
    "hard_requirements_satisfied": [],
    "source_novelty": null,
    "reuse_count": 0,
    "visual_purpose": "SHOW_PRODUCT",
    "start_time": null,
    "end_time": null
  },
  {
    "shot_id": "shot:beat:1:person:0",
    "beat_id": "beat:1:person",
    "asset_id": "cand:commons:hans_wilsdorf",
    "candidate_id": "cand:commons:hans_wilsdorf",
    "visual_information_id": "viu:founder:portrait",
    "shot_requirement_id": "",
    "verification_id": "",
    "selection_reason": "",
    "why_selected": "human_inspected_targeted_repair;file=hans_wilsdorf.jpg",
    "why_alternatives_lost": [],
    "score_breakdown": {},
    "hard_requirements_satisfied": [],
    "source_novelty": null,
    "reuse_count": 0,
    "visual_purpose": "SHOW_PERSON",
    "start_time": null,
    "end_time": null
  },
  {
    "shot_id": "shot:beat:4:process:0",
    "beat_id": "beat:4:process",
    "asset_id": "cand:pexels:8322145",
    "candidate_id": "cand:pexels:8322145",
    "visual_information_id": "viu:watchmaker:process",
    "shot_requirement_id": "",
    "verification_id": "",
    "selection_reason": "",
    "why_selected": "human_inspected_targeted_repair;file=watchmaker_8322145_hd.mp4",
    "why_alternatives_lost": [],
    "score_breakdown": {},
    "hard_requirements_satisfied": [],
    "source_novelty": null,
    "reuse_count": 0,
    "visual_purpose": "SHOW_PROCESS",
    "start_time": null,
    "end_time": null
  },
  {
    "shot_id": "shot:beat:5:payoff:0",
    "beat_id": "beat:5:payoff",
    "asset_id": "cand:pexels:17197593",
    "candidate_id": "cand:pexels:17197593",
    "visual_information_id": "viu:rolex:payoff",
    "shot_requirement_id": "",
    "verification_id": "",
    "selection_reason": "",
    "why_selected": "human_inspected_targeted_repair;file=rolex_17197593_hd.mp4",
    "why_alternatives_lost": [],
    "score_breakdown": {},
    "hard_requirements_satisfied": [],
    "source_novelty": null,
    "reuse_count": 0,
    "visual_purpose": "SHOW_PRODUCT",
    "start_time": null,
    "end_time": null
  }
]
```

## WHY EACH SHOT WAS SELECTED

- `beat:0:hook` → cand:pexels:3809175: human_inspected_targeted_repair;file=cand_pexels_3809175.jpeg
- `beat:1:person` → cand:commons:hans_wilsdorf: human_inspected_targeted_repair;file=hans_wilsdorf.jpg
- `beat:4:process` → cand:pexels:8322145: human_inspected_targeted_repair;file=watchmaker_8322145_hd.mp4
- `beat:5:payoff` → cand:pexels:17197593: human_inspected_targeted_repair;file=rolex_17197593_hd.mp4

## RECOVERY ASSETS

{
  "beat:2:ownership": "video-output\\work\\sf20260925-083746_55d45a\\jobs\\sf20260925-083746_55d45a\\recovery\\motion\\mg_rel_d5ed387fdb.mp4",
  "beat:3:reveal": "video-output\\work\\sf20260925-083746_55d45a\\jobs\\sf20260925-083746_55d45a\\recovery\\motion\\mg_tl_d6d1343ed0.mp4"
}

## GATES

- **TechnicalRenderQA:** PASS
- **FinalVideoQualityGate:** REVIEW_REQUIRED
- **FactQualityGate:** PASS
- **StoryQualityGate:** PASS
- **StoryConsistencyGate:** PASS
- **VisualCoverageGate:** PASS
- **NoSlideshowQualityGate:** REVIEW_REQUIRED
- **LicenseProvenanceGate:** REVIEW_REQUIRED

## MEDIA CLASS BREAKDOWN

- Duration: 25.5
- Beats: 6  Shots: 6
- Unique assets: 6  Unique VIUs: 6
- By class: `{"real_entity_video": 0, "archive_video": 0, "stock_video": 2, "motion_graphic": 2, "synthetic_video": 0, "archive_still": 2, "evidence_document": 0}`
- Seconds by class: `{"real_entity_video": 0.0, "archive_video": 0.0, "stock_video": 8.59, "motion_graphic": 8.9, "synthetic_video": 0.0, "archive_still": 7.12, "evidence_document": 0.0}`
- Same-asset multi-beat: 0
- Uncovered important: []

## TECHNICAL RENDER QA

```json
{
  "ok": true,
  "reasons": [],
  "width": 1080,
  "height": 1920,
  "fps": 30.0,
  "duration_sec": 25.5,
  "has_video": true,
  "has_audio": true,
  "details": {
    "format": "mov,mp4,m4a,3gp,3g2,mj2",
    "size": 7346092,
    "video_duration_sec": 25.5,
    "audio_duration_sec": 25.488
  }
}
```

## FINAL VIDEO CRITIC

- Decision: **REVIEW_REQUIRED**
- Provider/model: direct_groq / qwen/qwen3.8-27b
- Notes: critic_vlm_error:RATE_LIMITED
- HIGH/MED/LOW: 0/0/0
- VLM calls: 1  cost≈None


## REPAIR ATTEMPTS

```json
[]
```

## ARTIFACTS

- MP4: `video-output\DOCUMENTARY_ENGINE_V2_STAGE_F_REAL_sf20260925-083746_55d45a.mp4`
- EDL: `video-output\DOCUMENTARY_ENGINE_V2_STAGE_F_EDL_sf20260925-083746_55d45a.json`
- Manifest: `video-output\DOCUMENTARY_ENGINE_V2_STAGE_F_MANIFEST_sf20260925-083746_55d45a.json`
- Trace: `video-output\DOCUMENTARY_ENGINE_V2_STAGE_F_TRACE_sf20260925-083746_55d45a.json`
- Attribution: `video-output\DOCUMENTARY_ENGINE_V2_STAGE_F_ATTRIBUTION_sf20260925-083746_55d45a.json`

## TESTS

- Stage F and subtitle regression tests run in this targeted repair.

## COST / LIMITATIONS

- Direct Groq was **RATE_LIMITED** during this completion pass; director re-verify skipped.
- Hook still came from earlier Pexels acquisition; founder portrait from Commons; process/payoff from Pexels.
- New selections were human-inspected; this is a curated regression case, not proof of general automatic selection.
- FinalVideoCritic attempted; if rate-limited → REVIEW_REQUIRED (not auto-PASS).
- TTS used Edge Neural (ElevenLabs quota exceeded).
- DOCUMENTARY_ENGINE_V2 remains OFF. No publish. No MİKO. No global enable.

## STOP

Human must watch the MP4. Automated QA is support, not creative authority.
