import base64
import edge_tts
from pathlib import Path

from app.config import config
from app.http_client import session

DEFAULT_VOICE = "en-US-GuyNeural"
DEFAULT_ELEVEN_VOICE = "JBFqnCBsd6RMkjVDRZzb"  # George / Deep Storyteller


def _synthesize_elevenlabs(
    text: str, output_path: str, api_key: str, voice_id: str | None = None
) -> list[dict] | None:
    """ElevenLabs with-timestamps API ile stüdyo seslendirmesi ve kelime hizalaması alır."""
    voice = voice_id or config.ELEVENLABS_VOICE_ID or DEFAULT_ELEVEN_VOICE
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}/with-timestamps"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {
            "stability": 0.55,
            "similarity_boost": 0.80,
            "style": 0.25,
            "use_speaker_boost": True,
        },
    }

    try:
        resp = session.post(url, headers=headers, json=payload, timeout=45)
        if resp.status_code != 200:
            print(f"[tts] ElevenLabs API yanıtı ({resp.status_code}): {resp.text[:100]} - edge-tts'e düşülüyor.")
            return None

        data = resp.json()
        audio_b64 = data.get("audio_base64")
        if not audio_b64:
            return None

        Path(output_path).write_bytes(base64.b64decode(audio_b64))

        # Karakter zamanlamalarından kelime sınırlarını oluştur
        alignment = data.get("alignment") or {}
        chars = alignment.get("characters", [])
        starts = alignment.get("character_start_times_seconds", [])
        ends = alignment.get("character_end_times_seconds", [])

        word_boundaries = []
        current_word = []
        w_start = 0.0
        w_end = 0.0

        for char, start_s, end_s in zip(chars, starts, ends):
            if char.isspace():
                if current_word:
                    w_text = "".join(current_word)
                    word_boundaries.append({
                        "offset": int(w_start * 10_000_000),
                        "duration": int(max(0.05, w_end - w_start) * 10_000_000),
                        "text": w_text,
                    })
                    current_word = []
            else:
                if not current_word:
                    w_start = start_s
                w_end = end_s
                current_word.append(char)

        if current_word:
            w_text = "".join(current_word)
            word_boundaries.append({
                "offset": int(w_start * 10_000_000),
                "duration": int(max(0.05, w_end - w_start) * 10_000_000),
                "text": w_text,
            })

        if word_boundaries:
            print(f"[tts] ElevenLabs stüdyo seslendirmesi başarıyla üretildi ({len(word_boundaries)} kelime senkronu).", flush=True)
            return word_boundaries
    except Exception as exc:
        print(f"[tts] ElevenLabs çağrı hatası ({exc}) - edge-tts'e geçiliyor.")

    return None


async def synthesize_speech(
    text: str,
    output_path: str,
    voice: str = DEFAULT_VOICE,
    rate: str | None = None,
    meta_out: dict | None = None,
) -> list[dict]:
    """Synthesize speech; optionally fill meta_out with provider telemetry.

    meta_out keys when provided:
      - provider: "elevenlabs" | "edge"
      - edge_reason: set when Edge is used (missing_key | elevenlabs_failed)
    """
    # 1. ElevenLabs API anahtarı tanımlıysa öncelikle sinematik ses üretmeyi dene
    if config.ELEVENLABS_API_KEY:
        eleven_words = _synthesize_elevenlabs(
            text, output_path, config.ELEVENLABS_API_KEY, config.ELEVENLABS_VOICE_ID
        )
        if eleven_words:
            if meta_out is not None:
                meta_out["provider"] = "elevenlabs"
            return eleven_words
        edge_reason = "elevenlabs_failed"
        print(
            "[tts] UYARI: ElevenLabs başarısız — Edge Neural fallback "
            "(kalite yolu için ElevenLabs gerekir).",
            flush=True,
        )
    else:
        edge_reason = "missing_key"
        print(
            "[tts] UYARI: ELEVENLABS_API_KEY yok — Edge Neural kullanılıyor "
            "(robotik / slop riski). Kalite barı için ElevenLabs ayarlayın.",
            flush=True,
        )

    # 2. edge-tts fallback (veya varsayılan ücretsiz motor)
    kwargs = {"boundary": "WordBoundary"}
    if rate:
        kwargs["rate"] = rate
    communicate = edge_tts.Communicate(text, voice, **kwargs)
    word_boundaries = []

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append(
                    {
                        "offset": chunk["offset"],
                        "duration": chunk["duration"],
                        "text": chunk["text"],
                    }
                )

    if not word_boundaries:
        raise RuntimeError(
            "TTS kelime sınırı döndürmedi (WordBoundary boş) — "
            "altyazısız video üretilmesine izin verilmiyor"
        )

    if meta_out is not None:
        meta_out["provider"] = "edge"
        meta_out["edge_reason"] = edge_reason
    return word_boundaries

