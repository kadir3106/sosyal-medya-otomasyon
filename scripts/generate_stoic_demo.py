import asyncio
import os
import sys
import subprocess
from pathlib import Path

# Add video-worker to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.config import config
from app.stock_media import fetch_stock_clips
from app.tts import synthesize_speech
from app.subtitles import write_ass
from app.render import get_audio_duration, plan_scene_schedule, render_video
from app.image_gen import render_card

SCENE_CLIP_DURATION = 2.2
SCENE_XFADE_DURATION = 0.4

async def main():
    print("🔥 DARK STOIC & MOTIVATION VİDEO ÜRETİMİ BAŞLIYOR...")
    job_id = "stoic_power_demo"
    media_dir = Path(__file__).resolve().parent.parent / "video-output"
    media_dir.mkdir(parents=True, exist_ok=True)
    work_dir = media_dir / "work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    # 1. Senaryo (Dark Stoic Viral Hook)
    title = "Marcus Aurelius Rule On Disrespect"
    script = (
        "Marcus Aurelius had one brutal rule when someone disrespects you. "
        "Never react with anger. An emotional reaction proves that their words hold power over you. "
        "Instead, look them in the eyes and stay completely silent. "
        "Your silence is not weakness; it is a mirror reflecting their insecurity. "
        "Stay calm, stay dangerous. Drop a 100 below if you agree."
    )
    description = "Marcus Aurelius brutal stoic rule on disrespect. Master your emotions. #stoic #discipline #motivation #stoicism #mindset"
    tags = ["stoic", "discipline", "mindset", "motivation", "quotes", "focus", "marcusaurelius"]

    print(f"🎬 Başlık: {title}")
    print(f"📝 Senaryo: {script}\n")

    # 2. Derin ve Maskülen Christopher Sesi
    voice = "en-US-ChristopherNeural"
    audio_path = str(work_dir / "speech.mp3")
    print(f"🎙️ Seslendirme üretiliyor ({voice}, +8% tempo)...")
    word_boundaries = await synthesize_speech(script, audio_path, voice=voice, rate="+8%")

    # 3. Dinamik Sarı Vurgulu Altyazı
    print("✨ Dinamik karaoke altyazı hazırlanıyor...")
    subtitle_path = write_ass(
        word_boundaries,
        str(work_dir / "subs.ass"),
        words_per_cue=2,
        highlight=True,
        add_emojis=True,
    )

    # 4. Karanlık & Sinematik B-Roll Klipleri
    keywords = [
        "marble roman statue dark",
        "boxer training shadows",
        "rain dark city night",
        "lion face close up dark",
        "man suit silhouette window",
        "fire embers dark black",
    ]
    print(f"🎥 Pexels'ten sinematik B-roll klipleri çekiliyor: {keywords}...")
    # Sahne sayısı ses süresinden gelir: eksik kalanı başa sarmak yok.
    audio_duration = get_audio_duration(audio_path)
    scene_count = len(
        plan_scene_schedule(
            audio_duration,
            base_duration=SCENE_CLIP_DURATION,
            xfade_duration=SCENE_XFADE_DURATION,
        )
    )
    print(f"   Ses: {audio_duration:.1f} sn -> {scene_count} sahne")
    clip_paths = fetch_stock_clips(
        keywords,
        count=scene_count,
        api_key=config.PEXELS_API_KEY,
        output_dir=str(work_dir),
        state_path=str(media_dir / "used_clips.json"),
    )
    print(f"✅ {len(clip_paths)} adet HD klip indirildi.")

    # 5. Derin Sinematik Atmosfer Müziği (Sub-bass drone)
    bgm_path = str(media_dir / "audio" / "bgm" / "dark_stoic_ambient.mp3")
    Path(bgm_path).parent.mkdir(parents=True, exist_ok=True)
    if not Path(bgm_path).is_file():
        print("🎵 Sinematik karanlık bas tonu sentezleniyor...")
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", "aevalsrc=sin(55*2*PI*t)*0.08+sin(110*2*PI*t)*0.05+sin(165*2*PI*t)*0.03:s=44100:d=45",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            bgm_path,
        ]
        subprocess.run(cmd, capture_output=True)

    # 6. Render
    output_video = str(media_dir / f"{job_id}.mp4")
    print("⚡ Video render ediliyor (değişken ritim, çeşitli geçişler ve BGM)...")
    render_video(
        clip_paths,
        audio_path,
        subtitle_path,
        output_video,
        str(work_dir),
        clip_duration=SCENE_CLIP_DURATION,
        xfade_duration=SCENE_XFADE_DURATION,
        bgm_path=bgm_path,
        bgm_volume=0.20,
        apply_zoompan=False,
    )

    # 7. Kapak Kartı
    thumb_path = str(media_dir / f"{job_id}_thumb.png")
    render_card(title, brand_name="STOIC MIND", accent="#F59E0B", output_path=thumb_path)

    print("\n" + "=" * 60)
    print("🏆 DARK STOIC VİDEO BAŞARIYLA TAMAMLANDI!")
    print(f"📁 Video: {output_video}")
    print(f"🖼️ Kapak: {thumb_path}")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
