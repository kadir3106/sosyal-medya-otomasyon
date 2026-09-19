import os
import random
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from app.config import config
from app.http_client import session

MOTION_PATTERNS = ["zoom_in", "pan_right", "zoom_out", "pan_left"]
PEXELS_PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"


def _fetch_pexels_photo(query: str, api_key: str, output_path: Path) -> bool:
    """Pexels'ten konuya uygun yüksek çözünürlüklü dikey fotoğraf indirir."""
    if not api_key:
        return False
    try:
        resp = session.get(
            PEXELS_PHOTO_SEARCH_URL,
            headers={"Authorization": api_key},
            params={"query": query, "orientation": "portrait", "per_page": 5},
            timeout=15,
        )
        if resp.status_code == 200:
            photos = resp.json().get("photos", [])
            if photos:
                # Rastgele veya en iyi fotoğrafı seç
                photo = random.choice(photos[:3])
                img_url = photo["src"].get("large2x") or photo["src"].get("original") or photo["src"].get("large")
                if img_url:
                    img_data = session.get(img_url, timeout=20).content
                    if len(img_data) > 1024:
                        output_path.write_bytes(img_data)
                        return True
    except Exception as e:
        print(f"[ai_visuals] Pexels photo fallback uyarısı ({query}): {e}")
    return False


def generate_ai_image(prompt: str, output_path: Path, width: int = 720, height: int = 1280) -> Path:
    """Metin promptundan FLUX.1 modeli ile görsel indirir; meşgulse Pexels HD fotoğrafına düşer."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Pollinations FLUX.1 dene (kısa ve odaklı prompt)
    short_prompt = " ".join(prompt.strip().split()[:8])
    encoded_prompt = urllib.parse.quote(short_prompt)
    seed = random.randint(1, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=flux&nologo=true&seed={seed}"

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
    )

    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read()
            if len(data) > 2048:
                output_path.write_bytes(data)
                return output_path
    except Exception as e:
        print(f"[ai_visuals] Pollinations meşgul ({short_prompt}), Pexels HD fotoğrafına geçiliyor: {e}")

    # 2. Pexels HD Fotoğraf Arama Fallback
    search_terms = " ".join([w for w in short_prompt.split() if w.lower() not in ("cinematic", "photorealistic", "8k", "moody", "dramatic")][:3])
    if _fetch_pexels_photo(search_terms or "mystery", config.PEXELS_API_KEY, output_path):
        return output_path

    # 3. Son Çare: Sinematik degrade arka plan üret
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (width, height), color=(15, 20, 28))
    draw = ImageDraw.Draw(img)
    draw.text((width // 4, height // 2), short_prompt[:30], fill=(220, 220, 220))
    img.save(str(output_path))
    return output_path


def image_to_motion_clip(
    image_path: Path,
    output_clip_path: Path,
    duration: float = 2.5,
    motion_type: str = "zoom_in",
    fps: int = 25,
) -> Path:
    """Statik görseli FFmpeg Ken Burns zoompan filtresiyle akıcı 1080x1920 dikey videoya dönüştürür."""
    output_clip_path = Path(output_clip_path)
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)

    frames = int(duration * fps)

    if motion_type == "zoom_in":
        vf_zoom = f"zoompan=z='min(zoom+0.0015,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps}"
    elif motion_type == "zoom_out":
        vf_zoom = f"zoompan=z='if(lte(zoom,1.0),1.2,max(1.001,zoom-0.0015))':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps}"
    elif motion_type == "pan_right":
        vf_zoom = f"zoompan=z='1.15':x='if(lte(on,1),(iw-iw/zoom)/2,min((iw-iw/zoom),x+1))':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps}"
    else:  # pan_left
        vf_zoom = f"zoompan=z='1.15':x='if(lte(on,1),(iw-iw/zoom)/2,max(0,x-1))':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps}"

    vf = f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,{vf_zoom}"

    cmd = [
        "ffmpeg",
        "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        "-preset", "veryfast",
        str(output_clip_path),
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_clip_path


def generate_ai_scene_clips(
    prompts: list[str],
    output_dir: str,
    clip_duration: float = 2.5,
    start_index: int = 0,
) -> list[str]:
    """Tüm senaryo sahneleri için görsel çeker ve Ken Burns hareketli kliplere çevirir.

    `start_index`: dosya adlandırmasının başlayacağı numara. Zaten üretilmiş
    kliplerin (Kling/stok) üzerine yazılmasını önler.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    clips = []
    for offset, prompt in enumerate(prompts):
        idx = start_index + offset
        img_path = out / f"scene_{idx}.jpg"
        clip_path = out / f"clip_{idx}.mp4"

        # 1. Görseli oluştur/indir
        generate_ai_image(prompt, img_path)

        # 2. Hareketi çeşitlendir (zoom_in, pan_right, zoom_out, pan_left)
        motion = MOTION_PATTERNS[idx % len(MOTION_PATTERNS)]
        image_to_motion_clip(img_path, clip_path, duration=clip_duration, motion_type=motion)
        clips.append(str(clip_path))

    return clips
