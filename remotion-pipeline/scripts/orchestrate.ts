import path from "path";
import fs from "fs";
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { generateScriptWithLLM } from "./llm_client";
import { synthesizeVoiceWithTimestamps } from "./elevenlabs_client";
import { generateAllSceneAssets } from "./fal_client";
import { VideoCompositionProps, SceneItem } from "../src/types";

async function runPipeline() {
  const args = process.argv.slice(2);
  const isMock = args.includes("--mock");
  const topicArg = args.find((a) => a.startsWith("--topic="))?.split("=")[1];
  const topic = topicArg || "The Silent Architecture of Power";

  console.log("==========================================================");
  console.log(" HYBRID AI VIDEO GENERATION PIPELINE (Fal + Eleven + Remotion)");
  console.log(` Mode: ${isMock ? "MOCK (Fast Dry-Run)" : "PRODUCTION (Live APIs)"}`);
  console.log(` Topic: "${topic}"`);
  console.log("==========================================================\n");

  const projectRoot = process.cwd();
  const publicDir = path.resolve(projectRoot, "public");
  const audioDir = path.resolve(publicDir, "audio");
  const clipsDir = path.resolve(publicDir, "clips");
  const outputDir = path.resolve(projectRoot, "../video-output");

  fs.mkdirSync(audioDir, { recursive: true });
  fs.mkdirSync(clipsDir, { recursive: true });
  fs.mkdirSync(outputDir, { recursive: true });

  // ----------------------------------------------------
  // STEP 1: Scene Scripting & Data Payload (LLM)
  // ----------------------------------------------------
  console.log("[STEP 1/5] Generating Scene Script with LLM...");
  const scriptData = await generateScriptWithLLM(topic, { mock: isMock });
  console.log(`✔ Generated ${scriptData.scenes.length} scenes.`);
  console.log(`  Hook: "${scriptData.hook}"\n`);

  // ----------------------------------------------------
  // STEP 2: Audio & Timestamps Generation (ElevenLabs)
  // ----------------------------------------------------
  console.log("[STEP 2/5] Synthesizing Voiceover & Extracting Word Timestamps...");
  const fullVoiceoverText = scriptData.scenes.map((s) => s.voiceoverText).join(" ");
  const timestamp = Date.now();
  const audioFilePath = path.join(audioDir, `voiceover_${timestamp}.mp3`);

  const ttsResult = await synthesizeVoiceWithTimestamps(fullVoiceoverText, audioFilePath, {
    mock: isMock,
  });
  console.log(`✔ Spoken duration: ${ttsResult.durationSeconds}s, Words: ${ttsResult.words.length}\n`);

  // ----------------------------------------------------
  // STEP 3: Asset Generation (Fal.ai Video/Image API)
  // ----------------------------------------------------
  console.log("[STEP 3/5] Generating Visual Assets with Fal.ai (Kling / Minimax)...");
  const visualAssets = await generateAllSceneAssets(scriptData.scenes, clipsDir, {
    mock: isMock,
  });
  console.log(`✔ Generated ${visualAssets.length} scene assets.\n`);

  // ----------------------------------------------------
  // STEP 4: Payload Assembly & Duration Sync
  // ----------------------------------------------------
  console.log("[STEP 4/5] Assembling Remotion VideoCompositionProps...");

  const scenes: SceneItem[] = scriptData.scenes.map((s, idx) => {
    const asset = visualAssets.find((a) => a.sceneIndex === s.sceneIndex);
    return {
      index: s.sceneIndex,
      text: s.voiceoverText,
      visualPrompt: s.falVisualPrompt,
      durationSeconds: s.estimatedDurationSeconds,
      assetUrl: isMock ? undefined : asset?.assetUrl,
      assetType: "video",
    };
  });

  const compositionProps: VideoCompositionProps = {
    title: topic,
    fps: 30,
    scenes,
    audioUrl: isMock ? "" : ttsResult.audioPath,
    words: ttsResult.words,
    theme: {
      accentColor: "#D4AF37", // Metallic Luxury Gold
      secondaryColor: "#38BDF8", // Ice Blue Accent
      textColor: "#FFFFFF",
      badgeBg: "rgba(8, 8, 12, 0.85)",
      brandName: "PEAK MOTIVATION",
      fontFamily: "system-ui, -apple-system, sans-serif",
    },
  };

  const inputPropsPath = path.join(publicDir, "inputProps.json");
  fs.writeFileSync(inputPropsPath, JSON.stringify(compositionProps, null, 2));
  console.log(`✔ Saved dynamic props to: ${inputPropsPath}\n`);

  // ----------------------------------------------------
  // STEP 5: Programmatic Composition & Rendering (Remotion)
  // ----------------------------------------------------
  console.log("[STEP 5/5] Executing Headless Remotion Render...");

  const entryPoint = path.resolve(projectRoot, "src/index.ts");
  console.log("-> Bundling Remotion React project...");
  const bundleLocation = await bundle({
    entryPoint,
    webpackOverride: (config) => config,
  });

  const composition = await selectComposition({
    serveUrl: bundleLocation,
    id: "LuxuryShort",
    inputProps: compositionProps,
  });

  const outputFileName = `remotion_${timestamp}.mp4`;
  const finalOutputPath = path.join(outputDir, outputFileName);

  console.log(`-> Rendering ${composition.durationInFrames} frames (1080x1920 @ 30fps) to:`);
  console.log(`   ${finalOutputPath}\n`);

  let lastReportedPercent = -1;

  await renderMedia({
    composition,
    serveUrl: bundleLocation,
    codec: "h264",
    outputLocation: finalOutputPath,
    inputProps: compositionProps,
    onProgress: ({ renderedFrames, encodedFrames }) => {
      const progress = Math.round((encodedFrames / composition.durationInFrames) * 100);
      if (progress % 10 === 0 && progress !== lastReportedPercent) {
        lastReportedPercent = progress;
        console.log(`   [Render Progress] ${progress}% (${encodedFrames}/${composition.durationInFrames} frames)`);
      }
    },
  });

  console.log("\n==========================================================");
  console.log(" VIDEO GENERATION PIPELINE COMPLETED SUCCESSFULLY! ");
  console.log(` Final Video Path: ${finalOutputPath}`);
  console.log("==========================================================");
}

runPipeline().catch((err) => {
  console.error("\n❌ Pipeline execution failed:", err);
  process.exit(1);
});
