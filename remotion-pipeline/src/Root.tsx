import React from "react";
import { Composition } from "remotion";
import { LuxuryShortComposition } from "./Composition";
import { VideoCompositionProps, VideoCompositionPropsSchema } from "./types";

const defaultProps: VideoCompositionProps = {
  title: "The Silent Architecture of Power",
  fps: 30,
  theme: {
    accentColor: "#D4AF37",
    secondaryColor: "#38BDF8",
    textColor: "#FFFFFF",
    badgeBg: "rgba(8, 8, 12, 0.85)",
    brandName: "PEAK MOTIVATION",
    fontFamily: "sans-serif",
  },
  audioUrl: "",
  scenes: [
    {
      index: 0,
      text: "The truly wealthy never raise their voice.",
      visualPrompt:
        "Cinematic slow motion shot of an ultra high-end penthouse overlooking Monaco at dusk, crystal glass of vintage whiskey on marble table, 8k resolution, photorealistic, luxury aesthetic",
      durationSeconds: 3.5,
      assetType: "video",
    },
    {
      index: 1,
      text: "Power doesn't need to shout to command the room.",
      visualPrompt:
        "Tailored bespoke midnight blue suit, subtle Patek Philippe timepiece gleaming in warm amber interior lighting, executive boardroom at top floor, cinematic depth of field",
      durationSeconds: 4.0,
      assetType: "video",
    },
    {
      index: 2,
      text: "Control your emotions, or someone else will control you.",
      visualPrompt:
        "High-angle drone shot of a black Rolls Royce Phantom gliding silently through rainy Tokyo streets at midnight, neon reflections on wet asphalt",
      durationSeconds: 3.5,
      assetType: "video",
    },
  ],
  words: [
    { word: "THE", start: 0.1, end: 0.35 },
    { word: "TRULY", start: 0.36, end: 0.8 },
    { word: "WEALTHY", start: 0.81, end: 1.4 },
    { word: "NEVER", start: 1.45, end: 1.9 },
    { word: "RAISE", start: 1.95, end: 2.4 },
    { word: "THEIR", start: 2.45, end: 2.7 },
    { word: "VOICE.", start: 2.75, end: 3.4 },

    { word: "POWER", start: 3.6, end: 4.1 },
    { word: "DOESN'T", start: 4.15, end: 4.6 },
    { word: "NEED", start: 4.65, end: 4.95 },
    { word: "TO", start: 5.0, end: 5.2 },
    { word: "SHOUT", start: 5.25, end: 5.8 },
    { word: "TO", start: 5.85, end: 6.0 },
    { word: "COMMAND", start: 6.05, end: 6.7 },
    { word: "THE", start: 6.75, end: 7.0 },
    { word: "ROOM.", start: 7.05, end: 7.45 },

    { word: "CONTROL", start: 7.6, end: 8.2 },
    { word: "YOUR", start: 8.25, end: 8.5 },
    { word: "EMOTIONS,", start: 8.55, end: 9.3 },
    { word: "OR", start: 9.35, end: 9.6 },
    { word: "SOMEONE", start: 9.65, end: 10.1 },
    { word: "ELSE", start: 10.15, end: 10.45 },
    { word: "WILL", start: 10.5, end: 10.7 },
    { word: "CONTROL", start: 10.75, end: 11.2 },
    { word: "YOU.", start: 11.25, end: 11.8 },
  ],
};

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="LuxuryShort"
      component={LuxuryShortComposition}
      durationInFrames={330}
      fps={30}
      width={1080}
      height={1920}
      schema={VideoCompositionPropsSchema}
      defaultProps={defaultProps}
      calculateMetadata={({ props }) => {
        const fps = props.fps || 30;
        const totalDuration = props.scenes.reduce(
          (sum, s) => sum + (s.durationSeconds || 0),
          0
        );
        const lastWord = props.words?.[props.words.length - 1];
        const audioDuration = lastWord ? lastWord.end + 0.5 : 0;
        const effectiveDuration = Math.max(totalDuration, audioDuration, 5);

        return {
          durationInFrames: Math.round(effectiveDuration * fps),
          fps,
          width: 1080,
          height: 1920,
        };
      }}
    />
  );
};
