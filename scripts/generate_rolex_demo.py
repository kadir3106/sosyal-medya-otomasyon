import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.tts import synthesize_speech
from app.subtitles import write_ass
from app.ai_visuals import generate_ai_image, image_to_motion_clip
from app.audio_bgm import get_or_create_bgm
from app.render import render_video

SCRIPT_TEXT = (
    "Rolex is not a luxury watch company. "
    "In fact, legally, Rolex doesn't even exist as a for-profit corporation. "
    "It is one hundred percent owned by a private charity in Geneva, paying zero corporate taxes. "
    "They don't sell watches; they sell an artificial waiting list. "
    "They manufacture scarcity to make millionaires beg to spend thirty thousand dollars on steel. "
    "It is the greatest psychological illusion in capitalist history. "
    "Would you wait three years for a watch?"
)

PROMPTS = [
    "extreme macro close up of luxury gold Rolex watch dial, sweeping second hand, dark luxury studio lighting, 8k cinematic photorealistic, chiaroscuro",
    "confidential Swiss legal documents with wax seal, dimly lit antique mahogany desk in Geneva, dramatic noir lighting, 35mm film",
    "high security Swiss bank vault with gold bars and private deposit boxes, dark moody cinematic shadows, 8k",
    "exclusive luxury boutique window at night, empty velvet display case showing artificial scarcity, moody neon reflections",
    "powerful billionaire silhouette in bespoke black suit overlooking Manhattan penthouse at night, cinematic dramatic lighting",
    "antique ticking clock mechanism gears moving, macro shot, dramatic gold and black atmosphere, 8k masterpiece",
]


async def main():
    print("=" * 65)
    print("🎩 DARK WEALTH & BUSINESS SECRETS MOTORU ÇALIŞIYOR...")
    print("🎬 Başlık: The Rolex Illusion (Why Rolex Doesn't Sell Watches)")
    print("=" * 65)

    work_dir = Path("video-output/work/rolex_dark_wealth")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_video = Path("video-output/rolex_dark_wealth_demo.mp4")

    # 1. Sinematik Derin Anlatıcı Sesi (Christopher)
    print("\n🎙️ [1/5] Sinematik belgesel seslendirmesi (en-US-ChristopherNeural)...")
    speech_path = str(work_dir / "speech.mp3")
    boundaries = await synthesize_speech(
        SCRIPT_TEXT,
        speech_path,
        voice="en-US-ChristopherNeural",
        rate="+4%",
    )
    print(f"✅ Ses hazır: {len(boundaries)} kelime")

    # 2. Lüks Altın Vurgulu Altyazı
    print("\n✨ [2/5] Lüks altın vurgulu aktif karaoke altyazı hazırlanıyor...")
    sub_path = str(work_dir / "subs.ass")
    write_ass(boundaries, sub_path, words_per_cue=2, highlight=True, add_emojis=False)

    # 3. 6 Sahnelik Sinematik Dark Noir Görselleri (FLUX.1 + 3D Kamera)
    print("\n📸 [3/5] 6 sahne için lüks ve gizemli sinematik çekimler üretiliyor...")
    clip_paths = []
    motions = ["zoom_in", "pan_right", "zoom_out", "pan_left", "zoom_in", "zoom_out"]
    for idx, prompt in enumerate(PROMPTS):
        img_path = work_dir / f"scene_{idx}.jpg"
        clip_path = work_dir / f"clip_{idx}.mp4"
        print(f"   -> [{idx+1}/6] Çiziliyor: {prompt[:50]}...")
        generate_ai_image(prompt, img_path)
        image_to_motion_clip(img_path, clip_path, duration=5.0, motion_type=motions[idx])
        clip_paths.append(str(clip_path))

    # 4. Derin Gerilim / Gizem Fon Müziği
    print("\n🎵 [4/5] Sinematik karanlık ambient gerilim müziği bağlanıyor...")
    bgm_path = get_or_create_bgm("video-output/audio/bgm")

    # 5. Tam Ekran 1080x1920 Kurgu
    print("\n⚡ [5/5] Tam ekran 1080x1920 Netflix kalitesinde render alınıyor...")
    render_video(
        clip_paths,
        speech_path,
        sub_path,
        str(out_video),
        str(work_dir),
        clip_duration=4.2,
        xfade_duration=0.6,
        bgm_path=bgm_path,
        bgm_volume=0.18,
    )

    thumb_path = Path("video-output/rolex_dark_wealth_thumb.png")
    os.system(f'ffmpeg -y -ss 00:00:04 -i "{out_video}" -vframes 1 -q:v 2 "{thumb_path}" >nul 2>&1')

    print("\n" + "=" * 65)
    print("🏆 DARK WEALTH VİRAL BELGESEL BAŞARIYLA TAMAMLANDI!")
    print(f"📁 Video: {out_video.resolve()}")
    print(f"🖼️ Kapak: {thumb_path.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
