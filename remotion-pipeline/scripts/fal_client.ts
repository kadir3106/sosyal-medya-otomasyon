import fs from "fs";
import path from "path";
import dotenv from "dotenv";

// Load root .env
dotenv.config({ path: path.resolve(process.cwd(), "../.env") });
dotenv.config();

const FAL_KEY = process.env.FAL_KEY || "";
const FAL_KLING_ENDPOINT = "https://queue.fal.run/fal-ai/kling-video/v2.5-turbo/pro/text-to-video";

export interface FalVideoResult {
  sceneIndex: number;
  assetUrl: string;
  assetType: "video" | "image";
}

async function sleep(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function generateFalVideoClip(
  prompt: string,
  outputFile: string,
  options?: {
    mock?: boolean;
    duration?: number;
    aspectRatio?: string;
  }
): Promise<string> {
  const duration = options?.duration || 5;
  const aspectRatio = options?.aspectRatio || "9:16";

  if (options?.mock || !FAL_KEY) {
    console.log(`[Fal.ai] (Mock Mode) Simulating clip generation for prompt: "${prompt.slice(0, 40)}..."`);
    fs.mkdirSync(path.dirname(outputFile), { recursive: true });
    // Write empty or marker file for mock
    if (!fs.existsSync(outputFile)) {
      fs.writeFileSync(outputFile, Buffer.from([]));
    }
    return outputFile;
  }

  console.log(`[Fal.ai] Submitting prompt to Kling Video API: "${prompt.slice(0, 60)}..."`);

  const headers = {
    Authorization: `Key ${FAL_KEY}`,
    "Content-Type": "application/json",
  };

  const payload = {
    prompt,
    duration: String(duration),
    aspect_ratio: aspectRatio,
  };

  const submitRes = await fetch(FAL_KLING_ENDPOINT, {
    method: "POST",
    headers,
    body: JSON.stringify(payload),
  });

  if (!submitRes.ok) {
    const errText = await submitRes.text();
    throw new Error(`Fal.ai Kling queue error (${submitRes.status}): ${errText}`);
  }

  const queueData = await submitRes.json();
  const requestId = queueData.request_id;
  const statusUrl =
    queueData.status_url ||
    `https://queue.fal.run/fal-ai/kling-video/requests/${requestId}/status`;
  const responseUrl =
    queueData.response_url ||
    `https://queue.fal.run/fal-ai/kling-video/requests/${requestId}`;

  console.log(`[Fal.ai] Job enqueued (request_id: ${requestId}). Polling GPU progress...`);

  const maxAttempts = 60; // Up to 5 minutes
  for (let attempt = 1; attempt <= maxAttempts; attempt++) {
    await sleep(5000);
    const statusRes = await fetch(statusUrl, { headers });
    if (!statusRes.ok) continue;

    const statusData = await statusRes.json();
    const status = statusData.status;

    if (attempt % 3 === 0 || status === "COMPLETED") {
      console.log(`[Fal.ai] GPU Status: ${status} (${attempt * 5}s elapsed)`);
    }

    if (status === "COMPLETED") {
      const finalRes = await fetch(responseUrl, { headers });
      const finalData = await finalRes.json();
      const videoUrl = finalData.video?.url;

      if (!videoUrl) {
        throw new Error("[Fal.ai] Completed response missing video URL");
      }

      console.log(`[Fal.ai] Downloading generated video from: ${videoUrl}`);
      const videoRes = await fetch(videoUrl);
      const videoBuffer = Buffer.from(await videoRes.arrayBuffer());

      fs.mkdirSync(path.dirname(outputFile), { recursive: true });
      fs.writeFileSync(outputFile, videoBuffer);
      console.log(`[Fal.ai] Video saved to ${outputFile} (${videoBuffer.length} bytes)`);
      return outputFile;
    }

    if (status === "FAILED" || status === "CANCELLED") {
      throw new Error(`[Fal.ai] Video generation failed: ${JSON.stringify(statusData)}`);
    }
  }

  throw new Error("[Fal.ai] Generation timed out after 5 minutes.");
}

export async function generateAllSceneAssets(
  scenes: Array<{ sceneIndex: number; falVisualPrompt: string; estimatedDurationSeconds: number }>,
  clipsDir: string,
  options?: { mock?: boolean }
): Promise<FalVideoResult[]> {
  const results: FalVideoResult[] = [];

  for (const scene of scenes) {
    const filename = `scene_${scene.sceneIndex}.mp4`;
    const outputPath = path.join(clipsDir, filename);

    console.log(`\n--- Generating Scene ${scene.sceneIndex + 1}/${scenes.length} ---`);
    await generateFalVideoClip(scene.falVisualPrompt, outputPath, {
      mock: options?.mock,
      duration: 5,
    });

    results.push({
      sceneIndex: scene.sceneIndex,
      assetUrl: outputPath,
      assetType: "video",
    });
  }

  return results;
}
