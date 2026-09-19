import dotenv from "dotenv";
import path from "path";
import { LLMGeneratedScript, LLMGeneratedScriptSchema } from "../src/types";

// Load root .env
dotenv.config({ path: path.resolve(process.cwd(), "../.env") });
dotenv.config();

const OPENROUTER_API_KEY = process.env.OPENROUTER_API_KEY || "";
const OPENROUTER_MODEL = process.env.OPENROUTER_MODEL || "groq/qwen/qwen3.8-27b";

export async function generateScriptWithLLM(
  topic: string,
  options?: { mock?: boolean }
): Promise<LLMGeneratedScript> {
  if (options?.mock || !OPENROUTER_API_KEY) {
    console.log("[LLM] Using high-retention mock script payload for:", topic);
    return {
      topic,
      hook: "The truly wealthy never raise their voice.",
      scenes: [
        {
          sceneIndex: 0,
          voiceoverText: "The truly wealthy never raise their voice.",
          estimatedDurationSeconds: 3.5,
          falVisualPrompt:
            "Cinematic 9:16 vertical shot of an ultra high-end penthouse overlooking Monaco at dusk, crystal glass of vintage whiskey on marble table, 8k resolution, photorealistic, luxury aesthetic, anamorphic lens, moody lighting",
        },
        {
          sceneIndex: 1,
          voiceoverText: "Power doesn't need to shout to command the entire room.",
          estimatedDurationSeconds: 4.0,
          falVisualPrompt:
            "Cinematic vertical shot of tailored bespoke midnight blue suit, subtle Patek Philippe timepiece gleaming in warm amber interior lighting, executive boardroom, cinematic depth of field, 8k",
        },
        {
          sceneIndex: 2,
          voiceoverText: "Control your emotions, or someone else will control your future.",
          estimatedDurationSeconds: 4.0,
          falVisualPrompt:
            "High-angle vertical drone shot of a sleek black Rolls Royce Phantom gliding silently through rainy Tokyo streets at midnight, golden neon reflections on wet asphalt, cinematic slow motion",
        },
        {
          sceneIndex: 3,
          voiceoverText: "Silence is not weakness. It is ultimate authority.",
          estimatedDurationSeconds: 3.5,
          falVisualPrompt:
            "Close-up vertical shot of stoic man in luxury dark cashmere coat looking calmly towards camera, cinematic rim light, dark opulent palace background, 35mm film grain, 8k",
        },
      ],
    };
  }

  const systemPrompt = `You are an elite short-form video director and viral scriptwriter for luxury, wealth psychology, and modern stoicism niches (PeakMotivation, Hormozi style).
Generate a tight, viral, high-retention 15-second video script structured strictly in 4 scenes:
Scene 0: Hook (shocking contrast or controversial truth)
Scene 1: Tension / Reality check
Scene 2: Stoic / Elite mindset shift
Scene 3: Punchy closing power rule.

Each scene MUST include:
- sceneIndex (number 0 to 3)
- voiceoverText (short, punchy spoken English)
- estimatedDurationSeconds (between 3.0 and 4.5 seconds)
- falVisualPrompt (ultra-detailed visual prompt for Fal.ai video model, vertical 9:16 aspect ratio, cinematic lighting, 8k, photorealistic, luxury aesthetic).

Respond ONLY with valid JSON matching this exact structure:
{
  "topic": "${topic}",
  "hook": "string",
  "scenes": [
    {
      "sceneIndex": 0,
      "voiceoverText": "string",
      "estimatedDurationSeconds": 3.5,
      "falVisualPrompt": "string"
    }
  ]
}`;

  console.log(`[LLM] Querying OpenRouter (${OPENROUTER_MODEL}) for topic: "${topic}"...`);

  const response = await fetch("https://openrouter.ai/api/v1/chat/completions", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${OPENROUTER_API_KEY}`,
      "Content-Type": "application/json",
      "HTTP-Referer": "https://github.com/remotion-pipeline",
      "X-Title": "Hybrid Video Pipeline",
    },
    body: JSON.stringify({
      model: OPENROUTER_MODEL,
      messages: [
        { role: "system", content: systemPrompt },
        { role: "user", content: `Create a viral short video script on: "${topic}"` },
      ],
      temperature: 0.7,
      response_format: { type: "json_object" },
    }),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`OpenRouter API error (${response.status}): ${errorText}`);
  }

  const data = await response.json();
  const rawContent = data.choices?.[0]?.message?.content || "{}";
  const parsed = JSON.parse(rawContent);

  return LLMGeneratedScriptSchema.parse(parsed);
}
