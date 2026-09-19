"""
En üst seviye video üretim demosu:
- Derin Christopher sesi
- FLUX.1 / Fal AI sinematik görsel akışı
- FFmpeg Ken Burns 3D kamera süzülüşü (zoom-in, pan-right, zoom-out)
- Sahne geçişlerinde SFX (Whoosh ses efektleri)
- Arka planda ducking ile mikslenen gerilim bas müziği
- CapCut stili kelime kelime yanan sarı karaoke altyazı
- Tam SEO paketleme (Title, Description, Tags)
"""
import asyncio
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.config import config
from app.tts import synthesize_speech
from app.subtitles import write_ass
from app.ai_video_engine import generate_video_scenes
from app.audio_bgm import get_or_create_bgm
from app.render import (
    get_audio_duration,
    plan_scene_schedule,
    render_video,
    scene_transition_times,
)
from app.sfx import build_sfx_track

SCENE_CLIP_DURATION = 2.2
SCENE_XFADE_DURATION = 0.4

STORY = {
    "title": "The Simulation Glitch Nobody Can Explain",
    "description": "In 2014, thousands of people in California looked up and saw two suns in the sky. Scientists called it an optical illusion, but what if reality just glitched? #shorts #mystery #simulation #glitch #unsolved",
    "tags": ["simulation", "glitch", "matrix", "mystery", "shorts", "unsolved", "science"],
    "script": (
        "In 2014, thousands of people across California looked up and saw two suns shining in the sky. "
        "Cell phone cameras flooded the internet, showing two identical burning orbs side by side. "
        "Scientists rushed to call it an atmospheric reflection, but pilots at 30 thousand feet confirmed seeing both spheres. "
        "Three hours later, the second sun simply vanished without a sound. "
        "Was it really a natural illusion, or did the simulation just drop a frame? What do you think?"
    ),
    "prompts": [
        "crowd of people on city street looking up at sky in shock, pointing phones, golden hour dramatic cinematic lighting 8k",
        "surreal sky with two glowing suns side by side over mountains, photorealistic atmospheric phenomena cinematic 8k",
        "commercial airline cockpit view flying through clouds looking at two suns on the horizon, ultra realistic 35mm film",
        "close up of a vintage radar screen in air traffic control room glowing green with unidentified dual blips in darkness",
        "dramatic digital matrix glitch in cloudy sky, binary code dissolving through reality, moody cinematic depth of field"
    ]
}


async def main():
    print("=" * 65)
    print("🚀 SÜPER KALİTE VİDEO MOTORU (AI + KEN BURNS + SFX WHOOSH) ÇALIŞIYOR...")
    print(f"🎬 Başlık: {STORY['title']}")
    print(f"🏷️ Etiketler: {', '.join(STORY['tags'])}")
    print("=" * 65)

    work_dir = Path("video-output/work/top_tier_simulation")
    work_dir.mkdir(parents=True, exist_ok=True)
    out_video = Path("video-output/top_tier_simulation.mp4")

    # 1. Seslendirme (Christopher - Derin, merak uyandıran ses)
    speech_path = str(work_dir / "speech.mp3")
    print("\n🎙️ [1/6] Karizmatik derin anlatıcı sesi üretiliyor (+7% tempo)...")
    boundaries = await synthesize_speech(
        STORY["script"],
        speech_path,
        voice="en-US-ChristopherNeural",
        rate="+7%"
    )
    print(f"✅ Seslendirme tamamlandı: {len(boundaries)} kelime")

    # 2. Dinamik Sarı Karaoke Altyazı
    sub_path = str(work_dir / "subs.ass")
    print("\n✨ [2/6] CapCut stili kelime kelime sarı parlayan altyazı oluşturuluyor...")
    write_ass(boundaries, sub_path, words_per_cue=2, highlight=True, add_emojis=True)
    print("✅ Altyazı hazır.")

    # 3. AI Sahne Klipleri (Fal.ai / FLUX + Ken Burns)
    # Sahne sayısı ses süresinden gelir: sabit 5 sahne, uzun anlatımda
    # görüntülerin başa sarılmasına (slayt hissine) yol açıyordu.
    audio_duration = get_audio_duration(speech_path)
    durations = plan_scene_schedule(
        audio_duration,
        base_duration=SCENE_CLIP_DURATION,
        xfade_duration=SCENE_XFADE_DURATION,
    )
    scene_count = len(durations)
    print(f"\n🎨 [3/6] {scene_count} sahne çiziliyor ve sinematik kamera hareketi veriliyor...")
    print(f"   Ses: {audio_duration:.1f} sn -> {scene_count} sahne (tekrar yok)")
    clips = generate_video_scenes(
        STORY["prompts"],
        str(work_dir),
        clip_duration=SCENE_CLIP_DURATION,
        target_count=scene_count,
    )
    print(f"✅ {len(clips)} adet sinematik 1080x1920 klip hazır.")

    # 4. SFX: Sahne Geçişlerine Whoosh Ses Efektleri (gerçek geçiş anlarına senkron)
    print("\n🔊 [4/6] Sahne geçişleri için sinematik Whoosh ses efektleri yerleştiriliyor...")
    sfx_track = build_sfx_track(
        total_duration=audio_duration,
        clip_duration=SCENE_CLIP_DURATION,
        output_path=str(work_dir / "sfx_track.wav"),
        sfx_dir="video-output/audio/sfx",
        transition_times=scene_transition_times(durations, SCENE_XFADE_DURATION),
    )
    if sfx_track:
        print(f"✅ Whoosh geçiş efektleri kanalı oluşturuldu: {sfx_track}")
    else:
        print("ℹ️ SFX geçişi atlandı.")

    # 5. Gerilim / Gizem Arka Plan Müziği
    bgm_path = get_or_create_bgm("video-output/audio/bgm")
    print(f"\n🎵 [5/6] Sinematik gerilim tonu bağlandı: {bgm_path}")

    # 6. FFmpeg ile Son Render (Görseller + SFX + BGM + Ses + Altyazı)
    print(f"\n⚡ [6/6] Final video render ediliyor -> {out_video}")
    render_video(
        clips,
        speech_path,
        sub_path,
        str(out_video),
        work_dir=str(work_dir),
        bgm_path=bgm_path,
        clip_duration=SCENE_CLIP_DURATION,
        xfade_duration=SCENE_XFADE_DURATION,
        sfx_path=sfx_track,
        cinematic_grade=config.CINEMATIC_GRADE,
    )

    # Otomatik Kapak Resmi (Thumbnail)
    thumb_path = Path("video-output/top_tier_simulation_thumb.png")
    os.system(f'ffmpeg -y -ss 00:00:03 -i "{out_video}" -vframes 1 -q:v 2 "{thumb_path}" >nul 2>&1')

    print("\n" + "=" * 65)
    print("🏆 SÜPER KALİTE VİDEO BAŞARIYLA TAMAMLANDI!")
    print(f"📁 Video: {out_video.resolve()}")
    print(f"🖼️ Kapak: {thumb_path.resolve()}")
    print("=" * 65)


if __name__ == "__main__":
    asyncio.run(main())
