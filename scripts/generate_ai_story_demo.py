"""
Yeni AI Görsel Motoru (FLUX.1 + FFmpeg Ken Burns) ile ilk gerçek gizem/hikaye
videosunu uçtan uca render eden script.
"""
import asyncio
import os
import sys
from pathlib import Path

# Proje kök dizinini sys.path'e ekle
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.config import config
from app.tts import synthesize_speech
from app.subtitles import write_ass
from app.ai_visuals import generate_ai_scene_clips
from app.audio_bgm import get_or_create_bgm
from app.render import render_video

STORY = {
    "title": "The Mystery of D.B. Cooper",
    "script": (
        "In 1971, a man in a black suit boarded a Boeing 727 with a briefcase. "
        "He handed the flight attendant a note claiming he had a bomb, demanding 200 thousand dollars. "
        "After getting the cash, he ordered the plane into a freezing thunderstorm. "
        "At ten thousand feet, he opened the back door and jumped into the pitch black sky with a parachute. "
        "Fifty years later, the FBI closed the file. He was never found. What do you think happened to him?"
    ),
    "prompts": [
        "cinematic 8k photorealistic close up of a mysterious man in a black suit and dark sunglasses sitting in an airplane cabin at night, 1970s vintage aesthetic, moody lighting",
        "vintage handwritten ransom note on airplane seat next to a leather briefcase overflowing with dollar bills, dramatic shadows, 35mm film look",
        "aerial shot of a commercial airliner flying through a dark violent thunderstorm at night with lightning illuminating the storm clouds, cinematic 8k",
        "dramatic silhouette of a parachutist jumping from the open rear stairs of an airplane into freezing darkness, rain and fog, cinematic action",
        "dark moody FBI investigation room, cold lamp glowing over classified cold case folders stamped TOP SECRET, volumetric dust and smoke"
    ]
}


async def main():
    print("=" * 60)
    print("🚀 FLUX.1 AI GÖRSEL & KEN BURNS SİNEMATİK MOTORU ÇALIŞIYOR...")
    print(f"🎬 Konu: {STORY['title']}")
    print("=" * 60)

    work_dir = Path("video-output/work/ai_story_db_cooper")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_video = Path("video-output/ai_story_db_cooper.mp4")

    # 1. Seslendirme (Christopher - Derin Belgesel Sesi)
    speech_path = str(work_dir / "speech.mp3")
    print("\n🎙️ [1/5] Derin belgesel sesi sentezleniyor (en-US-ChristopherNeural)...")
    boundaries = await synthesize_speech(
        STORY["script"],
        speech_path,
        voice="en-US-ChristopherNeural",
        rate="+6%"
    )
    print(f"✅ Ses hazır: {len(boundaries)} kelime")

    # 2. Dinamik Sarı Karaoke Altyazı
    sub_path = str(work_dir / "subs.ass")
    print("\n✨ [2/5] CapCut stili kelime kelime sarı parlayan altyazı üretiliyor...")
    write_ass(boundaries, sub_path, words_per_cue=2, highlight=True, add_emojis=True)
    print("✅ Altyazı hazır.")

    # 3. FLUX.1 ile Özel AI Görselleri & Ken Burns Kamera Hareketi
    print("\n🎨 [3/5] FLUX.1 yapay zekası senaryonun 5 sahnesini çiziyor ve kamerayı hareketlendiriyor...")
    clips = generate_ai_scene_clips(STORY["prompts"], str(work_dir), clip_duration=5.0)
    print(f"✅ {len(clips)} adet sinematik 1080x1920 AI klip üretildi:")
    for c in clips:
        print(f"   - {c}")

    # 4. Derin Gerilim / Gizem Arka Plan Tonu
    bgm_path = get_or_create_bgm("video-output/audio/bgm")
    print(f"\n🎵 [4/5] Sinematik gerilim tonu bağlandı: {bgm_path}")

    # 5. FFmpeg ile Birleştirme
    print(f"\n⚡ [5/5] Tam video render ediliyor -> {out_video}")
    render_video(
        clips,
        speech_path,
        sub_path,
        str(out_video),
        work_dir=str(work_dir),
        bgm_path=bgm_path,
        clip_duration=5.0,
        xfade_duration=0.5,
    )

    # Küçük resim (thumbnail) al
    thumb_path = Path("video-output/ai_story_db_cooper_thumb.png")
    os.system(f'ffmpeg -y -ss 00:00:02 -i "{out_video}" -vframes 1 -q:v 2 "{thumb_path}" >nul 2>&1')

    print("\n" + "=" * 60)
    print("🏆 YENİ NESİL AI VİDEO BAŞARIYLA TAMAMLANDI!")
    print(f"📁 Video: {out_video.resolve()}")
    print(f"🖼️ Kapak: {thumb_path.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
