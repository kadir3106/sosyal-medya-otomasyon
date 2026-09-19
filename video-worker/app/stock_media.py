import json
import math
import random
import re
import subprocess
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.config import config
from app.http_client import session

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"
PEXELS_PER_PAGE = 15
USED_CLIP_HISTORY_LIMIT = 200

# Pexels API key yokken kullanılan Pillow tabanlı animasyonlu arka plan ayarları.
FALLBACK_FPS = 12
FALLBACK_DURATION_SECONDS = 4
FALLBACK_SIZE = (1080, 1920)

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
    "and", "or", "but", "for", "with", "at", "by", "it", "this", "that",
    "their", "its", "as", "from", "than", "so", "we", "they", "you",
    # Bu yalnızca script_gen'in visual_keywords alanını atladığı nadir
    # durumlarda devreye giren bir yedek yol (bkz. pipeline.py) — asıl çözüm
    # LLM'in HER ZAMAN İngilizce visual_keywords üretmesi. Yine de Türkçe
    # script'ten çıkarım yapılırsa en azından bariz dolgu kelimeler elensin.
    "bir", "bu", "şu", "ile", "gibi", "için", "kadar", "daha", "çok", "ama",
    "veya", "her", "hem", "ne", "de", "da", "ki", "mi", "mı", "mu", "mü",
    "olan", "olarak", "olduğu", "sonra", "önce", "değil", "diye", "ise",
}


def extract_keywords(script: str, max_keywords: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z\u00C0-\u024F]+", script)
    seen = []
    for word in words:
        lower = word.lower()
        if lower in _STOPWORDS or len(lower) < 4:
            continue
        if lower not in seen:
            seen.append(lower)
        if len(seen) >= max_keywords:
            break
    return seen or ["nature"]


def _next_keyword(keywords: list[str], index: int) -> str:
    """Sıradaki arama kelimesini döner; aynı kelime asla art arda gelmez.

    Tek keyword'e yapışmak (veya aynı kelimeyi üst üste aramak) görsel
    çeşitliliği öldürüyordu; bu yüzden kelimeler sırayla döner ve tekrar
    durumunda bir sonrakine atlanır.
    """
    if not keywords:
        return "cinematic"
    if len(keywords) == 1:
        return keywords[0]
    position = index % len(keywords)
    if index > 0 and keywords[position] == keywords[(index - 1) % len(keywords)]:
        position = (position + 1) % len(keywords)
    return keywords[position]


def fetch_stock_clips(
    keywords: list[str],
    count: int,
    api_key: str,
    output_dir: str,
    state_path: str = None,
    start_index: int = 0,
) -> list[str]:
    """Pexels'ten stok klip indirir; API key yoksa animasyonlu fallback üretir."""
    if not api_key:
        return _generate_fallback_clips(count, output_dir)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    used_ids = _load_used_clip_ids(state_path) if state_path else set()
    newly_used_ids = []

    downloaded = []
    # Keyword'ler sırayla döner ama asla aynı keyword üst üste gelmez: tek
    # keyword'e yapışmak görsel çeşitliliği öldürüyordu.
    max_attempts = max(count * 3, 10)
    attempt = 0
    while len(downloaded) < count and attempt < max_attempts:
        keyword = _next_keyword(keywords, attempt)
        attempt += 1
        video_id, video_file_url = None, None
        try:
            video_id, video_file_url = _search_portrait_video(
                keyword, api_key, exclude_ids=used_ids.union(newly_used_ids)
            )
        except Exception as exc:
            print(f"[stock] '{keyword}' araması başarısız ({exc}); sıradaki kelimeye geçiliyor.")
            continue
        if video_file_url is None:
            continue

        clip_num = start_index + len(downloaded)
        clip_path = output / f"clip_{clip_num}.mp4"
        _download_file(video_file_url, clip_path)
        downloaded.append(str(clip_path))
        if video_id is not None:
            newly_used_ids.append(video_id)

    if not downloaded:
        # Pexels hiç klip döndürmezse (key geçersiz/kota dolu) üretimi kurtar.
        return _generate_fallback_clips(count, output_dir)

    if state_path and newly_used_ids:
        _save_used_clip_ids(state_path, used_ids.union(newly_used_ids))

    return downloaded


def _load_used_clip_ids(state_path: str) -> set:
    path = Path(state_path)
    if not path.is_file():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("used_ids", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_used_clip_ids(state_path: str, ids: set) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sınırsız büyümesin — en son kullanılan N tanesi yeterli "tekrar etme" hafızası.
    trimmed = list(ids)[-USED_CLIP_HISTORY_LIMIT:]
    path.write_text(json.dumps({"used_ids": trimmed}), encoding="utf-8")


def _generate_fallback_clips(
    count: int,
    output_dir: str,
    accent: str = None,
    size: tuple[int, int] = FALLBACK_SIZE,
    fps: int = FALLBACK_FPS,
    duration: int = FALLBACK_DURATION_SECONDS,
) -> list[str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    accent = accent or config.IMAGE_ACCENT
    frame_count = duration * fps

    clips = []
    for index in range(count):
        frame_dir = output / f"fallback_frames_{index}"
        frame_dir.mkdir(exist_ok=True)

        for frame_index in range(frame_count):
            image = _render_fallback_frame(
                frame_index, frame_count, index, count, accent, size
            )
            image.save(frame_dir / f"frame_{frame_index:04d}.png")

        clip_path = output / f"fallback_{index}.mp4"
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-framerate", str(fps),
                "-i", str(frame_dir / "frame_%04d.png"),
                "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
                "-pix_fmt", "yuv420p",
                str(clip_path),
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"fallback clip encode failed: {result.stderr[-800:]}")
        clips.append(str(clip_path))
        shutil.rmtree(frame_dir, ignore_errors=True)

    return clips


def _render_fallback_frame(
    frame_index: int,
    frame_count: int,
    clip_index: int,
    clip_count: int,
    accent: str,
    size: tuple[int, int],
) -> Image.Image:
    width, height = size
    accent_rgb = _hex_to_rgb(accent)
    phase = (frame_index / max(frame_count, 1)) * 2 * math.pi

    # 1xH degradeyi çizip genişlet (C tarafında hızlı).
    gradient = Image.new("RGB", (1, height))
    gd = ImageDraw.Draw(gradient)
    top = _mix(accent_rgb, (15, 23, 42), 0.75)  # accent -> koyu
    bottom = _mix(accent_rgb, (15, 23, 42), 0.35 + 0.25 * (0.5 + 0.5 * math.sin(phase)))
    for y in range(height):
        t = y / max(height - 1, 1)
        gd.point((0, y), fill=_mix(top, bottom, t))
    image = gradient.resize((width, height))

    # Yumuşak ışık lekeleri: küçük katmanda çiz, blur, büyüt (ucuz ve yumuşak).
    overlay = Image.new("RGBA", (width // 4, height // 4), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for blob in range(3):
        speed = 1.0 + blob * 0.6
        cx = 0.5 + 0.35 * math.sin(phase * speed + blob * 2.1 + clip_index * 1.7)
        cy = 0.5 + 0.30 * math.cos(phase * (speed * 0.8) + blob * 1.3)
        radius = (0.18 + 0.08 * math.sin(phase + blob)) * (width // 4)
        alpha = 46 + blob * 12
        color = accent_rgb if blob % 2 == 0 else (255, 255, 255)
        od.ellipse(
            (
                cx * (width // 4) - radius,
                cy * (height // 4) - radius,
                cx * (width // 4) + radius,
                cy * (height // 4) + radius,
            ),
            fill=color + (alpha,),
        )
    overlay = overlay.filter(ImageFilter.GaussianBlur(radius=width // 90))
    overlay = overlay.resize((width, height))
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    return image


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def _mix(
    color_a: tuple[int, int, int], color_b: tuple[int, int, int], t: float
) -> tuple[int, int, int]:
    return tuple(
        int(round(a + (b - a) * t)) for a, b in zip(color_a, color_b)
    )


def _search_portrait_video(keyword: str, api_key: str, exclude_ids: frozenset = frozenset()):
    """(video_id, indirme linki) döner. Video bulunamazsa (None, None)."""
    response = session.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={"query": keyword, "orientation": "portrait", "per_page": PEXELS_PER_PAGE},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    videos = data.get("videos", [])
    if not videos:
        return None, None

    # Aynı arama kelimesi için her zaman ilk sonucu almak, her videoda hep aynı
    # kliple bitmesine yol açıyordu. per_page=15 sonuç arasından, daha önce
    # kullanılmamış olanlar arasından rastgele seç; hepsi kullanılmışsa (havuz
    # tükenmiş) kısıtlamayı esnet — üretim asla bu yüzden durmasın.
    fresh_candidates = [v for v in videos if v.get("id") not in exclude_ids]
    video = random.choice(fresh_candidates or videos)

    video_files = video.get("video_files", [])
    portrait_files = [
        f for f in video_files if f.get("height", 0) > f.get("width", 0)
    ]
    candidates = portrait_files or video_files
    if not candidates:
        return video.get("id"), None

    # 1080x1920'ye upscale edildiği için en yüksek çözünürlüklü dosya seçilir.
    # Rastgele seçim bazen 360p'lik klibi getiriyor ve görüntü bulanıklaşıyordu.
    best = max(candidates, key=lambda f: f.get("height", 0) or 0)
    return video.get("id"), best.get("link")


def _download_file(url: str, destination: Path) -> None:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    destination.write_bytes(response.content)
