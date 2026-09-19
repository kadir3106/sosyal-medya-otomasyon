import { Config } from "@remotion/cli/config";

// Configure Remotion rendering settings for 9:16 vertical short-form video
Config.setVideoImageFormat("jpeg");
Config.setOverwriteOutput(true);
Config.setChromiumOpenGlRenderer("angle");
Config.setConcurrency(2);
