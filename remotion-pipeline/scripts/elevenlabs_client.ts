import fs from "fs";
import path from "path";
import dotenv from "dotenv";
import { WordTimestamp } from "../src/types";

// Load root .env
dotenv.config({ path: path.resolve(process.cwd(), "../.env") });
dotenv.config();

const ELEVENLABS_API_KEY = process.env.ELEVENLABS_API_KEY || "";
const DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"; // George / Deep Storyteller

interface ElevenLabsAlignmentResponse {
  audio_base64: string;
  alignment: {
    characters: string[];
    character_start_times_seconds: number[];
    character_end_times_seconds: number[];
  };
}

export function parseAlignmentToWords(alignment: ElevenLabsAlignmentResponse["alignment"]): WordTimestamp[] {
  const chars = alignment.characters || [];
  const starts = alignment.character_start_times_seconds || [];
  const ends = alignment.character_end_times_seconds || [];

  const words: WordTimestamp[] = [];
  let currentWord: string[] = [];
  let wordStart = 0;
  let wordEnd = 0;

  for (let i = 0; i < chars.length; i++) {
    const char = chars[i];
    const s = starts[i];
    const e = ends[i];

    if (/\s/.test(char)) {
      if (currentWord.length > 0) {
        words.push({
          word: currentWord.join(""),
          start: Number(wordStart.toFixed(2)),
          end: Number(wordEnd.toFixed(2)),
        });
        currentWord = [];
      }
    } else {
      if (currentWord.length === 0) {
        wordStart = s;
      }
      wordEnd = e;
      currentWord.push(char);
    }
  }

  if (currentWord.length > 0) {
    words.push({
      word: currentWord.join(""),
      start: Number(wordStart.toFixed(2)),
      end: Number(wordEnd.toFixed(2)),
    });
  }

  return words;
}

export async function synthesizeVoiceWithTimestamps(
  fullScriptText: string,
  outputAudioPath: string,
  options?: { mock?: boolean; voiceId?: string }
): Promise<{ audioPath: string; words: WordTimestamp[]; durationSeconds: number }> {
  const voiceId = options?.voiceId || DEFAULT_VOICE_ID;

  if (options?.mock || !ELEVENLABS_API_KEY) {
    console.log("[ElevenLabs] Running in mock mode: Generating simulated timestamps.");
    // Simulate words and timestamps
    const rawWords = fullScriptText.split(/\s+/).filter(Boolean);
    let currentTime = 0.2;
    const words: WordTimestamp[] = rawWords.map((w) => {
      const duration = Math.max(0.2, Math.min(0.65, w.length * 0.075));
      const item: WordTimestamp = {
        word: w.toUpperCase(),
        start: Number(currentTime.toFixed(2)),
        end: Number((currentTime + duration).toFixed(2)),
      };
      currentTime += duration + 0.08;
      return item;
    });

    const totalDuration = Number((currentTime + 0.5).toFixed(2));
    // If output file doesn't exist, create an empty or placeholder file so remotion doesn't crash
    if (!fs.existsSync(outputAudioPath)) {
      fs.mkdirSync(path.dirname(outputAudioPath), { recursive: true });
      fs.writeFileSync(outputAudioPath, Buffer.from([]));
    }

    return {
      audioPath: outputAudioPath,
      words,
      durationSeconds: totalDuration,
    };
  }

  console.log(`[ElevenLabs] Synthesizing speech with studio voice (${voiceId})...`);

  const url = `https://api.elevenlabs.io/v1/text-to-speech/${voiceId}/with-timestamps`;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "xi-api-key": ELEVENLABS_API_KEY,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      text: fullScriptText,
      model_id: "eleven_multilingual_v2",
      voice_settings: {
        stability: 0.55,
        similarity_boost: 0.8,
        style: 0.25,
        use_speaker_boost: true,
      },
    }),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`ElevenLabs API error (${response.status}): ${errText}`);
  }

  const data = (await response.json()) as ElevenLabsAlignmentResponse;
  const audioBuffer = Buffer.from(data.audio_base64, "base64");

  fs.mkdirSync(path.dirname(outputAudioPath), { recursive: true });
  fs.writeFileSync(outputAudioPath, audioBuffer);
  console.log(`[ElevenLabs] Audio saved to: ${outputAudioPath} (${audioBuffer.length} bytes)`);

  const words = parseAlignmentToWords(data.alignment);
  const lastWord = words[words.length - 1];
  const durationSeconds = lastWord ? lastWord.end + 0.6 : 10;

  console.log(`[ElevenLabs] Alignment parsed: ${words.length} synchronized words.`);
  return {
    audioPath: outputAudioPath,
    words,
    durationSeconds,
  };
}
