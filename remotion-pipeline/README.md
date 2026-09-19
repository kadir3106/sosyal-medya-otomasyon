# Hybrid AI Video Generation Pipeline (Fal.ai + ElevenLabs + Remotion)

An automated programmatic video generation pipeline engineered for 9:16 vertical short-form platforms (YouTube Shorts, Instagram Reels, TikTok) in luxury, wealth psychology, and modern stoicism niches.

## Architecture & Integration Flow

1. **Scene Scripting & Prompt Engineering (LLM)**:
   - Uses OpenRouter (`groq/qwen/qwen3.8-27b`) to generate a strict JSON payload matching `LLMGeneratedScriptSchema`.
   - Generates 4-stage retention structure: Hook (0-3s), Tension, Paradigm Shift, and Power Rule.
   - Formulates hyper-realistic visual prompts tailored for Fal.ai video models (Kling, Minimax, Flux) with cinematic lighting and luxury aesthetic.

2. **Studio Audio & Word-Level Timestamps (ElevenLabs)**:
   - Sends voiceover script to ElevenLabs `/v1/text-to-speech/{voice_id}/with-timestamps` API using the George / Deep Storyteller model.
   - Parses character-level alignments into millisecond-accurate word boundaries (`words.json`).

3. **Cinematic Visual Asset Generation (Fal.ai API)**:
   - Programmatically dispatches text-to-video prompts to Fal.ai queue (`fal-ai/kling-video/v2.5-turbo/pro/text-to-video`).
   - Polls queue status and downloads 9:16 HD MP4 clips into `public/clips/`.

4. **Programmatic Composition & Headless Rendering (Remotion React)**:
   - Master composition `LuxuryShort` (`src/Root.tsx`) rendered at 1080x1920 (9:16) @ 30fps.
   - **Kinetic Typography Engine**: Real-time word-synchronized typography with active word spring pop-in and glowing gold highlights (`#D4AF37`) inside dark translucent frosted glass badges.
   - **Cinematic Scene Motion**: Ken Burns subtle zoom and pan transitions, dark vignette, and contrast grading.
   - Headless export via `@remotion/renderer` saving production MP4 directly to `video-output/`.

---

## Quick Start

### 1. Interactive Remotion Studio (Web Preview)
Preview and scrub through the video timeline interactively in your browser:
```bash
npm run dev
```

### 2. Fast Dry-Run (Mock Mode)
Test the entire TypeScript orchestration, timeline calculations, Remotion bundler, and video rendering without consuming API credits:
```bash
npm run orchestrate:mock
```

### 3. Full Production Video Generation (Live APIs)
Execute the complete pipeline with live OpenRouter LLM script generation, ElevenLabs studio voice synthesis, Fal.ai Kling AI video rendering, and Remotion compilation:
```bash
npm run orchestrate -- --topic="The Silent Architecture of Power"
```

---

## Output
Rendered videos are exported automatically to:
`../video-output/remotion_<timestamp>.mp4`
