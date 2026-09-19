import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import { ThemeTokens } from "../types";

interface LuxuryWatermarkProps {
  brandName: string;
  theme: ThemeTokens;
}

export const LuxuryWatermark: React.FC<LuxuryWatermarkProps> = ({
  brandName,
  theme,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();

  const progress = Math.min(1, Math.max(0, frame / durationInFrames));

  return (
    <>
      {/* Top Progress Bar */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 6,
          backgroundColor: "rgba(255, 255, 255, 0.1)",
          zIndex: 100,
        }}
      >
        <div
          style={{
            height: "100%",
            width: `${progress * 100}%`,
            background: `linear-gradient(90deg, ${theme.accentColor}, #FFF8DC)`,
            boxShadow: `0 0 10px ${theme.accentColor}`,
          }}
        />
      </div>

      {/* Brand Header */}
      <div
        style={{
          position: "absolute",
          top: 80,
          left: 0,
          right: 0,
          display: "flex",
          justifyContent: "center",
          alignItems: "center",
          zIndex: 90,
          pointerEvents: "none",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            padding: "8px 22px",
            borderRadius: 30,
            background: "rgba(10, 10, 14, 0.6)",
            backdropFilter: "blur(8px)",
            border: "1px solid rgba(212, 175, 55, 0.25)",
          }}
        >
          <span
            style={{
              color: theme.accentColor,
              fontSize: 16,
              fontWeight: 900,
            }}
          >
            ◆
          </span>
          <span
            style={{
              fontFamily: theme.fontFamily,
              color: "#FFFFFF",
              fontSize: 18,
              fontWeight: 800,
              letterSpacing: "0.22em",
              textTransform: "uppercase",
            }}
          >
            {brandName}
          </span>
          <span
            style={{
              color: theme.accentColor,
              fontSize: 16,
              fontWeight: 900,
            }}
          >
            ◆
          </span>
        </div>
      </div>
    </>
  );
};
