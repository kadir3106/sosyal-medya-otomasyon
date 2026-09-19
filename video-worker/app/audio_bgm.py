import os
import random
import subprocess
from pathlib import Path


def get_or_create_bgm(bgm_dir: str, duration_seconds: float = 60.0) -> str | None:
    """Klasördeki telifsiz BGM parçalarından birini döner.

    Klasörde hiç müzik yoksa ffmpeg ile otomatik hafif bir lofi/ambient
    arka plan tonu üreterek videonun sessiz kalmasını önler.
    """
    path = Path(bgm_dir)
    path.mkdir(parents=True, exist_ok=True)

    tracks = list(path.glob("*.mp3")) + list(path.glob("*.wav"))
    if tracks:
        return str(random.choice(tracks))

    # Klasör boşsa hafif bir ambient sentetik parça üret
    default_bgm = path / "default_ambient.mp3"
    if default_bgm.is_file():
        return str(default_bgm)

    try:
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi",
            "-i", f"aevalsrc=sin(130*2*PI*t)*0.03+sin(196*2*PI*t)*0.03+sin(261*2*PI*t)*0.02:s=44100:d={int(duration_seconds) + 10}",
            "-c:a", "libmp3lame",
            "-b:a", "128k",
            str(default_bgm),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and default_bgm.is_file():
            return str(default_bgm)
    except Exception:
        pass

    return None
