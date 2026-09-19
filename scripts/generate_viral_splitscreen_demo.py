"""
Dünyanın en yüksek retention oranına sahip 'Split-Screen' (İkili Hipnotik Ekran)
viral videosunu render eden script:
- Üst Ekran: 1080x960 Gerçek / Gizemli Görsel Hikaye
- Alt Ekran: 1080x960 Hipnotik ASMR / Satisfying Hareket
- Ortada: İnce Neon Çizgi + CapCut stili Kelime Kelime Sarı Parlayan Karaoke Altyazı
- Ses: Tok, derin anlatıcı + arka planda gerilim bas tonu
"""
import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.tts import synthesize_speech
from app.subtitles import write_ass
from app.split_screen import fetch_satisfying_clip, render_split_screen_video
from app.audio_bgm import get_or_create_bgm
from app.ai_visuals import generate_ai_image, image_to_motion_clip

STORY = {
    "title": "Why You Should Never Whistle at Night in the Woods",
    "script": (
        "Old hunters have one golden rule they never break: never whistle at night in the deep woods. "
        "They say sound travels differently in the dark, but that is not the real reason. "
        "Whistling mimics a distress call of wounded prey. "
        "In the shadows, predators and things without names do not run away from a whistle; they stalk towards it. "
        "If you ever hear a whistle back, run. Have you ever heard it?"
    ),
    "top_prompt": "dark foggy forest at night, moonlight breaking through tall pine trees, mysterious silhouette in mist, cinematic 8k photorealistic"
}


async def main():
    print("=" * 65)
    print("🚀 VIRAL SPLIT-SCREEN (HİPNOTİK İKİLİ EKRAN) MOTORU ÇALIŞIYOR...")
    print(f"🎬 Başlık: {STORY['title']}")
    print("=" * 65)

    work_dir = Path("video-output/work/split_screen_demo")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_video = Path("video-output/viral_splitscreen_demo.mp4")

    # 1. Seslendirme (Christopher - Derin, tüyleri diken diken eden fısıltı/anlatım)
    speech_path = str(work_dir / "speech.mp3")
    print("\n🎙️ [1/5] Gerilim anlatıcı sesi üretiliyor (en-US-ChristopherNeural)...")
    boundaries = await synthesize_speech(
        STORY["script"],
        speech_path,
        voice="en-US-ChristopherNeural",
        rate="+5%"
    )
    print(f"✅ Ses hazır: {len(boundaries)} kelime")

    # 2. Dinamik Sarı Karaoke Altyazı (Ortaya yakın güvenli bölge)
    sub_path = str(work_dir / "subs.ass")
    print("\n✨ [2/5] CapCut stili kelime kelime sarı parlayan altyazı üretiliyor...")
    write_ass(boundaries, sub_path, words_per_cue=2, highlight=True, add_emojis=True)
    print("✅ Altyazı hazır.")

    # 3. Üst Ekran Videosu (1080x960 Karanlık Orman Sisi - AI + Ken Burns)
    print("\n🌲 [3/5] Üst ekran için sinematik sahne üretiliyor...")
    top_img = work_dir / "top_scene.jpg"
    top_clip = work_dir / "top_clip.mp4"
    generate_ai_image(STORY["top_prompt"], top_img)
    image_to_motion_clip(top_img, top_clip, duration=6.0, motion_type="zoom_in")
    print(f"✅ Üst video hazır: {top_clip}")

    # 4. Alt Ekran Videosu (1080x960 Hipnotik ASMR / Satisfying Loop)
    print("\n🔮 [4/5] Alt ekran için hipnotik satisfying video indiriliyor...")
    bottom_clip = work_dir / "satisfying_bottom.mp4"
    fetch_satisfying_clip(bottom_clip)
    print(f"✅ Alt satisfying video hazır: {bottom_clip}")

    # 5. Arka Plan Gerilim Tonu
    bgm_path = get_or_create_bgm("video-output/audio/bgm")
    print(f"\n🎵 [5/5] Sinematik gerilim tonu bağlandı: {bgm_path}")

    # 6. FFmpeg ile Split-Screen Birleştirme
    print(f"\n⚡ Tam 1080x1920 Split-Screen render ediliyor -> {out_video}")
    render_split_screen_video(
        str(top_clip),
        str(bottom_clip),
        speech_path,
        sub_path,
        str(out_video),
        bgm_path=bgm_path,
        bgm_volume=0.18,
    )

    thumb_path = Path("video-output/viral_splitscreen_thumb.png")
    os.system(f'ffmpeg -y -ss 00:00:04 -i "{out_video}" -vframes 1 -q:v 2 "{thumb_path}" >nul 2>&1')

    print("\n" + "=" * 65)
    print("🏆 VİRAL SPLIT-SCREEN VİDEO BAŞARIYLA TAMAMLANDI!")
    print(f"📁 Video: {out_video.resolve()}")
    print(f"🖼️ Kapak: {thumb_path.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
