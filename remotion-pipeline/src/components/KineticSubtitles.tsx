import React from "react";
import { useCurrentFrame, useVideoConfig, spring } from "remotion";
import { WordTimestamp, ThemeTokens } from "../types";

interface SubtitleProps {
  words: WordTimestamp[];
  theme: ThemeTokens;
}

export const KineticSubtitles: React.FC<SubtitleProps> = ({ words, theme }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const currentTime = frame / fps;

  if (!words || words.length === 0) {
    return null;
  }

  // Find the active word based on currentTime
  const activeIndex = words.findIndex(
    (w) => currentTime >= w.start && currentTime <= w.end
  );

  // Fallback: if between words, check if we're near the last spoken word
  let targetIndex = activeIndex;
  if (targetIndex === -1) {
    targetIndex = words.findIndex((w) => currentTime < w.start);
    if (targetIndex > 0) {
      const prevWord = words[targetIndex - 1];
      if (currentTime - prevWord.end < 0.4) {
        targetIndex = targetIndex - 1;
      } else {
        targetIndex = -1;
      }
    } else if (targetIndex === -1 && words.length > 0) {
      const lastWord = words[words.length - 1];
      if (currentTime - lastWord.end < 0.8) {
        targetIndex = words.length - 1;
      }
    }
  }

  if (targetIndex === -1) {
    return null;
  }

  // Window of words: 3 words centered or sliding around the active index
  const windowSize = 3;
  const chunkStart = Math.floor(targetIndex / windowSize) * windowSize;
  const currentChunk = words.slice(chunkStart, chunkStart + windowSize);

  return (
    <div
      style={{
        position: "absolute",
        bottom: 340,
        left: 0,
        right: 0,
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        padding: "0 40px",
        pointerEvents: "none",
        zIndex: 50,
      }}
    >
      <div
        style={{
          display: "flex",
          flexWrap: "wrap",
          justifyContent: "center",
          alignItems: "center",
          gap: "14px 18px",
          background: theme.badgeBg,
          padding: "16px 28px",
          borderRadius: 24,
          boxShadow: "0 20px 50px rgba(0,0,0,0.7), inset 0 0 1px rgba(255,255,255,0.2)",
          backdropFilter: "blur(14px)",
          border: "1px solid rgba(255, 215, 0, 0.2)",
          maxWidth: "85%",
        }}
      >
        {currentChunk.map((w, idx) => {
          const absoluteIndex = chunkStart + idx;
          const isActive = absoluteIndex === targetIndex;

          const wordStartFrame = Math.round(w.start * fps);
          const wordFrameProgress = Math.max(0, frame - wordStartFrame);

          // Spring pop animation when active
          const scale = isActive
            ? spring({
                frame: wordFrameProgress,
                fps,
                config: { damping: 12, stiffness: 220, mass: 0.5 },
              }) * 0.15 + 1.05
            : 1.0;

          return (
            <span
              key={`${w.word}-${absoluteIndex}`}
              style={{
                fontFamily: theme.fontFamily,
                fontWeight: 900,
                fontSize: 52,
                textTransform: "uppercase",
                letterSpacing: "0.04em",
                color: isActive ? theme.accentColor : theme.textColor,
                transform: `scale(${scale})`,
                transition: "color 0.1s ease",
                textShadow: isActive
                  ? `0 0 25px ${theme.accentColor}88, 0 4px 10px rgba(0,0,0,0.9)`
                  : "0 4px 10px rgba(0,0,0,0.8)",
                display: "inline-block",
              }}
            >
              {w.word}
            </span>
          );
        })}
      </div>
    </div>
  );
};
