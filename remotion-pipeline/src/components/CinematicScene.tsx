import React from "react";
import {
  Video,
  Img,
  useCurrentFrame,
  useVideoConfig,
  interpolate,
  Easing,
} from "remotion";
import { SceneItem } from "../types";

interface CinematicSceneProps {
  scene: SceneItem;
  durationInFrames: number;
}

export const CinematicScene: React.FC<CinematicSceneProps> = ({
  scene,
  durationInFrames,
}) => {
  const frame = useCurrentFrame();
  const { width, height } = useVideoConfig();

  // Dynamic Ken Burns Zoom and Subtle Pan
  const scale = interpolate(
    frame,
    [0, durationInFrames],
    [1.0, 1.12],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
      easing: Easing.out(Easing.cubic),
    }
  );

  const translateY = interpolate(
    frame,
    [0, durationInFrames],
    [0, -25],
    {
      extrapolateLeft: "clamp",
      extrapolateRight: "clamp",
    }
  );

  return (
    <div
      style={{
        width,
        height,
        position: "relative",
        overflow: "hidden",
        backgroundColor: "#050507",
      }}
    >
      {/* Visual Asset Layer */}
      <div
        style={{
          width: "100%",
          height: "100%",
          transform: `scale(${scale}) translateY(${translateY}px)`,
          transformOrigin: "center center",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        {scene.assetUrl ? (
          scene.assetType === "video" ? (
            <Video
              src={scene.assetUrl}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
              }}
              muted
            />
          ) : (
            <Img
              src={scene.assetUrl}
              style={{
                width: "100%",
                height: "100%",
                objectFit: "cover",
              }}
            />
          )
        ) : (
          /* Placeholder aesthetic for mock/dry-run */
          <div
            style={{
              width: "100%",
              height: "100%",
              background:
                "linear-gradient(135deg, #0d0e15 0%, #161a29 50%, #08080c 100%)",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: 60,
              textAlign: "center",
            }}
          >
            <div
              style={{
                color: "#D4AF37",
                fontSize: 32,
                fontWeight: 800,
                letterSpacing: "0.2em",
                marginBottom: 20,
              }}
            >
              SCENE {scene.index + 1}
            </div>
            <div
              style={{
                color: "rgba(255,255,255,0.7)",
                fontSize: 24,
                maxWidth: 700,
                lineHeight: 1.5,
              }}
            >
              "{scene.visualPrompt}"
            </div>
          </div>
        )}
      </div>

      {/* Cinematic Lighting & Dark Vignette */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background:
            "radial-gradient(circle at center, rgba(0,0,0,0) 40%, rgba(0,0,0,0.65) 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Bottom Gradient for Subtitle Contrast */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          bottom: 0,
          height: 600,
          background:
            "linear-gradient(to top, rgba(0,0,0,0.85) 0%, rgba(0,0,0,0) 100%)",
          pointerEvents: "none",
        }}
      />

      {/* Top Gradient for Title/Brand Contrast */}
      <div
        style={{
          position: "absolute",
          left: 0,
          right: 0,
          top: 0,
          height: 300,
          background:
            "linear-gradient(to bottom, rgba(0,0,0,0.7) 0%, rgba(0,0,0,0) 100%)",
          pointerEvents: "none",
        }}
      />
    </div>
  );
};
