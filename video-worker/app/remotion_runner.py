import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from app.config import config


def update_pipeline_status(status: str, progress: int, details: str, topic: str = ""):
    """MİKO ve Telegram için canlı durum dosyasını günceller."""
    status_file = Path(config.MEDIA_DIR) / "pipeline_status.json"
    data = {
        "status": status,
        "progress": progress,
        "details": details,
        "topic": topic,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        status_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def run_remotion_pipeline(topic: str, mock: bool = False) -> dict:
    """
    Remotion + Fal.ai + ElevenLabs video üretim hattını çalıştırır.
    Biten videoyu hazırlar, pending.json kaydeder ve video verisini döner.
    """
    repo_root = Path(config.MEDIA_DIR).resolve().parent
    remotion_dir = repo_root / "remotion-pipeline"

    if not remotion_dir.is_dir():
        raise FileNotFoundError(f"remotion-pipeline dizini bulunamadı: {remotion_dir}")

    update_pipeline_status("running", 10, "Senaryo ve seslendirme hazırlanıyor...", topic=topic)

    cmd = ["npm.cmd" if os.name == "nt" else "npm", "run", "orchestrate"]
    if mock:
        cmd.append("orchestrate:mock")
    else:
        cmd.extend(["--", f"--topic={topic}"])

    print(f"[remotion_runner] Komut çalıştırılıyor: {' '.join(cmd)} (dizin: {remotion_dir})", flush=True)

    update_pipeline_status("running", 35, "Fal.ai ve Remotion 9:16 render aşamasında...", topic=topic)

    process = subprocess.Popen(
        cmd,
        cwd=str(remotion_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output_lines = []
    latest_video_path = None

    for line in iter(process.stdout.readline, ""):
        clean_line = line.strip()
        if clean_line:
            output_lines.append(clean_line)
            if "[Render Progress]" in clean_line:
                print(f"[remotion_runner] {clean_line}", flush=True)
                # İlerlemeyi parse et
                try:
                    pct = int(clean_line.split("%")[0].split()[-1])
                    update_pipeline_status("rendering", pct, f"Remotion render ediliyor (%{pct})...", topic=topic)
                except Exception:
                    pass
            elif "Final Video Path:" in clean_line:
                latest_video_path = clean_line.split("Final Video Path:", 1)[1].strip()

    process.stdout.close()
    return_code = process.wait()

    if return_code != 0:
        error_tail = "\n".join(output_lines[-10:])
        update_pipeline_status("failed", 0, f"Render hatası: {error_tail[:80]}", topic=topic)
        raise RuntimeError(f"Remotion pipeline başarısız oldu (kod {return_code}):\n{error_tail}")

    # En son üretilen MP4 dosyasını bul (eğer çıktı satırında parse edilemediyse)
    if not latest_video_path or not Path(latest_video_path).is_file():
        media_dir = Path(config.MEDIA_DIR)
        remotion_files = sorted(
            media_dir.glob("remotion_*.mp4"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if remotion_files:
            latest_video_path = str(remotion_files[0])
        else:
            raise FileNotFoundError("Üretilen remotion_*.mp4 dosyası bulunamadı.")

    job_id = f"remotion_{int(time.time())}"
    title = f"{topic} | The Silent Rules of Power"
    description = (
        f"{topic}\n\n"
        "Master the unspoken dynamics of status, wealth, and stoic control.\n\n"
        "#Luxury #DarkWealth #Motivation #Stoicism #Shorts #Success"
    )
    tags = ["luxury", "motivation", "wealth", "stoicism", "shorts", "success"]

    # Onay mekanizması için pending.json kaydet
    pending_payload = {
        "job_id": job_id,
        "kind": "video",
        "video_path": str(latest_video_path),
        "video_filename": Path(latest_video_path).name,
        "thumbnail_path": "",
        "title": title,
        "description": description,
        "tags": tags,
        "topic": topic,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }

    pending_file = Path(config.MEDIA_DIR) / "pending.json"
    pending_file.write_text(json.dumps(pending_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    update_pipeline_status("completed", 100, "Video hazır! Telegram onayı bekleniyor.", topic=topic)

    return pending_payload
