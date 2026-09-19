import { z } from "zod";

export const SceneItemSchema = z.object({
  index: z.number(),
  text: z.string(),
  visualPrompt: z.string(),
  durationSeconds: z.number().positive(),
  assetUrl: z.string().optional(),
  assetType: z.enum(["video", "image"]).default("video"),
});

export type SceneItem = z.infer<typeof SceneItemSchema>;

export const WordTimestampSchema = z.object({
  word: z.string(),
  start: z.number(), // in seconds
  end: z.number(),   // in seconds
});

export type WordTimestamp = z.infer<typeof WordTimestampSchema>;

export const ThemeTokensSchema = z.object({
  accentColor: z.string().default("#D4AF37"), // Metallic Luxury Gold
  secondaryColor: z.string().default("#38BDF8"), // Cyan/Ice Accent
  textColor: z.string().default("#FFFFFF"),
  badgeBg: z.string().default("rgba(8, 8, 10, 0.82)"),
  brandName: z.string().default("PEAK MOTIVATION"),
  fontFamily: z.string().default("system-ui, -apple-system, sans-serif"),
});

export type ThemeTokens = z.infer<typeof ThemeTokensSchema>;

export const VideoCompositionPropsSchema = z.object({
  title: z.string().default("Unlocking Elite Power"),
  scenes: z.array(SceneItemSchema),
  audioUrl: z.string(),
  words: z.array(WordTimestampSchema).default([]),
  theme: ThemeTokensSchema.default({}),
  fps: z.number().default(30),
});

export type VideoCompositionProps = z.infer<typeof VideoCompositionPropsSchema>;

export const LLMGeneratedScriptSchema = z.object({
  topic: z.string(),
  hook: z.string(),
  scenes: z.array(
    z.object({
      sceneIndex: z.number(),
      voiceoverText: z.string(),
      estimatedDurationSeconds: z.number(),
      falVisualPrompt: z.string(),
    })
  ),
});

export type LLMGeneratedScript = z.infer<typeof LLMGeneratedScriptSchema>;
