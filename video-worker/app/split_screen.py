import math
import random
import subprocess
from pathlib import Path

from app.config import config
from app.http_client import session
from app.render import get_audio_duration, _escape_for_filter, FPS, WIDTH, HEIGHT

SATISFYING_QUERIES = [
    "satisfying kinetic sand",
    "satisfying soap cutting",
    "satisfying 3d loop",
    "satisfying marble run",
    "satisfying fluid art",
    "satisfying colorful clay",
]


def fetch_satisfying_clip(output_path: Path, api_key: str = None) -> Path:
    """Pexels'ten hipnotize edici, tatmin edici bir alt video indirir."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.is_file() and output_path.stat().st_size > 500000:
        return output_path

    api_key = api_key or config.PEXELS_API_KEY
    query = random.choice(SATISFYING_QUERIES)

    try:
        resp = session.get(
            "https://api.pexels.com/videos/search",
            headers={"Authorization": api_key},
            params={"query": query, "per_page": 5},
            timeout=15,
        )
        if resp.status_code == 200:
            videos = resp.json().get("videos", [])
            if videos:
                vid = random.choice(videos[:3])
                files = vid.get("video_files", [])
                # En iyi HD dosyayı seç
                hd_file = next((f for f in files if f.get("quality") == "hd"), files[0])
                data = session.get(hd_file["link"], timeout=30).content
                output_path.write_bytes(data)
                return output_path
    except Exception as e:
        print(f"[split_screen] Satisfying klip indirme uyarısı: {e}")

    # Fallback 1: Yerel hazır hipnotik video varsa kopyala
    local_loop = Path(__file__).resolve().parent.parent / "data" / "satisfying_loop.mp4"
    if local_loop.is_file():
        import shutil
        shutil.copy(str(local_loop), str(output_path))
        return output_path

    # Fallback 2: Sentetik hipnotik dalga videosu üret (FFmpeg lavfi)
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "testsrc2=size=1080x960:rate=30",
        "-t", "10",
        "-c:v", "libx264",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return output_path


def render_split_screen_video(
    top_clip_path: str,
    bottom_clip_path: str,
    audio_path: str,
    sub_path: str,
    output_path: str,
    bgm_path: str | None = None,
    bgm_volume: float = 0.15,
) -> str:
    """
    Üst ve alt videoyu 1080x1920 Split-Screen olarak birleştirir:
    - Üst: 1080x960 (Hikaye / Gizem / Konu)
    - Alt: 1080x960 (Hipnotik ASMR / Satisfying hareket)
    - Tam ortada ince ayırıcı çizgi
    - Ortalanmış kelime kelime yanan karaoke altyazı
    """
    audio_dur = get_audio_duration(audio_path)
    escaped_sub = _escape_for_filter(sub_path)

    # Filtre zinciri:
    # [0:v] -> scale ve crop 1080x960 [top]
    # [1:v] -> scale ve crop 1080x960 [bottom]
    # [top][bottom]vstack -> 1080x1920
    # drawline/drawbox ile 4px ince neon ayırıcı çizgi
    escaped_sub = str(Path(sub_path)).replace("\\", "/")

    filter_complex = (
        f"[0:v]scale=1080:960:force_original_aspect_ratio=increase,"
        f"crop=1080:960,fps={FPS},setsar=1[top];"
        f"[1:v]scale=1080:960:force_original_aspect_ratio=increase,"
        f"crop=1080:960,fps={FPS},setsar=1[bottom];"
        f"[top][bottom]vstack=inputs=2[vstacked];"
        f"[vstacked]drawbox=x=0:y=958:w=1080:h=4:color=0x00E5FF@0.8:t=fill[vsplit];"
        f"[vsplit]subtitles='{escaped_sub}'[vfinal]"
    )

    inputs = [
        "-stream_loop", "-1", "-i", str(Path(top_clip_path)),
        "-stream_loop", "-1", "-i", str(Path(bottom_clip_path)),
        "-i", str(Path(audio_path)),
    ]

    if bgm_path:
        inputs += ["-i", str(Path(bgm_path))]
        audio_filter = (
            f"[2:a]volume=1.0[aspeech];"
            f"[3:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[abgm];"
            f"[aspeech][abgm]amix=inputs=2:duration=first:dropout_transition=2[afinal]"
        )
        filter_complex += f";{audio_filter}"
        audio_map = ["-map", "[afinal]"]
    else:
        audio_map = ["-map", "2:a:0"]

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vfinal]", *audio_map,
        "-t", str(audio_dur),
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "19",
        "-c:a", "aac", "-b:a", "192k",
        str(output_path),
    ]

    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(output_path)
