import React from "react";
import { Sequence, Audio, useVideoConfig } from "remotion";
import { VideoCompositionProps } from "./types";
import { CinematicScene } from "./components/CinematicScene";
import { KineticSubtitles } from "./components/KineticSubtitles";
import { LuxuryWatermark } from "./components/LuxuryWatermark";

export const LuxuryShortComposition: React.FC<VideoCompositionProps> = ({
  title,
  scenes,
  audioUrl,
  words,
  theme,
}) => {
  const { fps } = useVideoConfig();

  let currentStartFrame = 0;
  const sceneSequences = scenes.map((scene) => {
    const durationInFrames = Math.max(1, Math.round(scene.durationSeconds * fps));
    const startFrame = currentStartFrame;
    currentStartFrame += durationInFrames;

    return {
      scene,
      startFrame,
      durationInFrames,
    };
  });

  return (
    <div
      style={{
        width: "100%",
        height: "100%",
        backgroundColor: "#000000",
        position: "relative",
      }}
    >
      {/* 1. Visual Sequences */}
      {sceneSequences.map(({ scene, startFrame, durationInFrames }) => (
        <Sequence
          key={`scene-${scene.index}`}
          from={startFrame}
          durationInFrames={durationInFrames}
        >
          <CinematicScene scene={scene} durationInFrames={durationInFrames} />
        </Sequence>
      ))}

      {/* 2. Top Watermark & Progress */}
      <LuxuryWatermark brandName={theme.brandName} theme={theme} />

      {/* 3. Word-Synchronized Kinetic Typography */}
      <KineticSubtitles words={words} theme={theme} />

      {/* 4. Spoken Voiceover Audio */}
      {audioUrl && <Audio src={audioUrl} />}
    </div>
  );
};
