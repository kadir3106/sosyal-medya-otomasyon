import asyncio
import os
import sys
import subprocess
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.tts import synthesize_speech
from app.subtitles import write_ass
from app.ai_visuals import generate_ai_image, image_to_motion_clip
from app.render import render_video

SCRIPT_TEXT = (
    "Hello little friends! Meet Barnaby, the tiny baby dino! "
    "Barnaby loves sweet red strawberries and sunny days. "
    "When Barnaby is happy, he wiggles his little tail! "
    "Can you wiggle like Barnaby? Wiggle wiggle wiggle! Yay! Good job!"
)

PROMPTS = [
    "cute 3d animated baby dinosaur waving hand hello, pixar disney animation style, big sparkly friendly eyes, happy smile, sunny green meadow with colorful flowers, bright pastel colors, 8k octane render",
    "cute 3d animated baby dinosaur eating a giant juicy red strawberry, adorable happy chewing face, sunny afternoon, pixar 3d animation, vibrant joyful colors, 8k render",
    "cute 3d animated baby dinosaur dancing and jumping happily with little sparkles and confetti, cheerful rainbow background, pixar 3d render, ultra quality",
]


async def main():
    print("=" * 60)
    print("🧸 COCOMELON / PIXAR 3D KIDS VİDEO MOTORU ÇALIŞIYOR...")
    print("=" * 60)

    work_dir = Path("video-output/work/cocomelon_demo")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_video = Path("video-output/cocomelon_kids_demo.mp4")

    # 1. Neşeli Çocuk Seslendirmesi (en-US-AnaNeural)
    print("\n👶 [1/4] Neşeli çocuk anlatıcı sesi üretiliyor (en-US-AnaNeural)...")
    speech_path = str(work_dir / "speech.mp3")
    boundaries = await synthesize_speech(
        SCRIPT_TEXT,
        speech_path,
        voice="en-US-AnaNeural",
        rate="+5%",
    )
    print(f"✅ Çocuk sesi hazır: {len(boundaries)} kelime")

    # 2. Renkli, Neşeli Baloncuk Altyazı
    print("\n🎈 [2/4] Çocuklara özel renkli altyazı hazırlanıyor...")
    sub_path = str(work_dir / "subs.ass")
    write_ass(boundaries, sub_path, words_per_cue=2, highlight=True, add_emojis=True)

    # 3. 3D Pixar Sevimli Karakter Sahneleri (FLUX.1 3D Pixar)
    print("\n🦖 [3/4] 3D Pixar bebek dinozor sahneleri üretiliyor...")
    clip_paths = []
    motions = ["zoom_in", "pan_right", "zoom_out"]
    for idx, prompt in enumerate(PROMPTS):
        img_path = work_dir / f"scene_{idx}.jpg"
        clip_path = work_dir / f"clip_{idx}.mp4"
        print(f"   -> Sahne {idx + 1}/3 çiziliyor...")
        generate_ai_image(prompt, img_path)
        image_to_motion_clip(img_path, clip_path, duration=5.0, motion_type=motions[idx % len(motions)])
        clip_paths.append(str(clip_path))

    # 4. Neşeli Fon Müziği ile Birleştirme
    print("\n🎵 [4/4] Neşeli çocuk fon müziği ile tam 1080x1920 dikey render alınıyor...")
    bgm_path = "video-output/playful_tune.mp3"
    
    render_video(
        clip_paths,
        speech_path,
        sub_path,
        str(out_video),
        str(work_dir),
        clip_duration=4.5,
        xfade_duration=0.5,
        bgm_path=bgm_path,
        bgm_volume=0.25,
    )

    thumb_path = Path("video-output/cocomelon_kids_thumb.png")
    os.system(f'ffmpeg -y -ss 00:00:02 -i "{out_video}" -vframes 1 -q:v 2 "{thumb_path}" >nul 2>&1')

    print("\n" + "=" * 60)
    print("🎉 COCOMELON / PIXAR TARZI VİRAL ÇOCUK VİDEOSU TAMAMLANDI!")
    print(f"📁 Video: {out_video.resolve()}")
    print(f"🖼️ Kapak: {thumb_path.resolve()}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
