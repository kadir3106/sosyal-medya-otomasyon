import hashlib
import json
import time
from pathlib import Path

from app.config import config
from app.http_client import session
from app.ai_visuals import generate_ai_scene_clips

FAL_KLING_ENDPOINT = "https://queue.fal.run/fal-ai/kling-video/v2.5-turbo/pro/text-to-video"

# 'hybrid' modunda Kling ile üretilecek sahne sayısı (ilk sahneler = kanca).
# Kling pahalı/yavaş; tüm sahneleri Kling yapmak yerine en kritik ilk sahneler
# gerçek AI video, kalanı stok HD video olur.
KLING_HYBRID_SCENES = 1

# Kling kuyruğu için bekleme ayarları: 80 x 5 sn = en fazla ~6.5 dakika.
# Süre aşılırsa üretim sonsuza kadar bloklanmaz, stok videoya düşülür.
KLING_POLL_ATTEMPTS = 80
KLING_POLL_INTERVAL_SECONDS = 5

# AI görsel promptlarının tekrar hafızası (bkz. refresh_repeated_prompts).
USED_PROMPT_HISTORY_LIMIT = 300
PROMPT_HISTORY_FILENAME = "used_prompts.json"


def generate_kling_video_clip(
    prompt: str,
    output_path: str,
    fal_key: str,
    duration: int = 5,
    aspect_ratio: str = "9:16",
) -> str | None:
    """Fal.ai üzerinden Kling AI Text-to-Video motoru ile gerçek hareketli 9:16 dikey klip üretir."""
    if not fal_key:
        return None

    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "duration": str(duration),
        "aspect_ratio": aspect_ratio,
    }

    try:
        # Kuyruğa gönder
        resp = session.post(FAL_KLING_ENDPOINT, headers=headers, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        request_id = data.get("request_id")
        status_url = data.get("status_url") or f"https://queue.fal.run/fal-ai/kling-video/requests/{request_id}/status"
        response_url = data.get("response_url") or f"https://queue.fal.run/fal-ai/kling-video/requests/{request_id}"

        # Sonuç hazır olana kadar bekle (Kling GPU üretimi 3-5 dakika sürebilir)
        for attempt in range(KLING_POLL_ATTEMPTS):
            time.sleep(KLING_POLL_INTERVAL_SECONDS)
            s_resp = session.get(status_url, headers=headers, timeout=15)
            s_data = s_resp.json()
            status = s_data.get("status")
            if attempt % 6 == 0:
                print(
                    f"[kling] GPU render sürüyor "
                    f"({attempt * KLING_POLL_INTERVAL_SECONDS} sn, durum: {status})...",
                    flush=True,
                )
            if status == "COMPLETED":
                r_resp = session.get(response_url, headers=headers, timeout=20)
                video_url = r_resp.json().get("video", {}).get("url")
                if video_url:
                    clip_bytes = session.get(video_url, timeout=60).content
                    Path(output_path).write_bytes(clip_bytes)
                    return output_path
            elif status in ("FAILED", "CANCELLED"):
                print(f"[kling] Üretim başarısız: {s_data}", flush=True)
                break
    except Exception as e:
        print(f"[kling] Fal.ai Kling API hatası ({e}) - stok videoya düşülüyor.", flush=True)
        return None

    # Zaman aşımı: kuyrukta takılı kaldı, sonsuza kadar beklemek yerine devam et.
    print(
        f"[kling] {KLING_POLL_ATTEMPTS * KLING_POLL_INTERVAL_SECONDS} sn içinde "
        "yanıt gelmedi - stok videoya düşülüyor.",
        flush=True,
    )
    return None


def generate_video_scenes(
    prompts: list[str],
    output_dir: str,
    clip_duration: float = 2.5,
    target_count: int | None = None,
) -> list[str]:
    """
    Akıllı Sahne Üretim Motoru:
    Her sahne için benzersiz, gerçek 1080p dikey hareketli video üretir/indirir.
    Asla aynı klibi tekrar ettirmez veya üzerine yazmaz.

    `target_count`: render'ın ihtiyaç duyduğu sahne sayısı. Prompt listesi bundan
    kısaysa aynı promptlardan farklı kamera açıları türetilerek istenen sayıya
    tamamlanır — eskiden liste kısa kaldığında render klipleri başa sarıyordu.
    """
    fal_key = config.FAL_KEY
    engine = config.VISUAL_ENGINE.lower()
    clips = []
    from app.stock_media import fetch_stock_clips

    wanted = max(target_count or len(prompts), 1)
    # Aynı prompt her gün aynı görseli üretmesin: tekrar edenler tazelenir.
    prompts = refresh_repeated_prompts(
        prompts, str(Path(config.MEDIA_DIR) / PROMPT_HISTORY_FILENAME)
    )
    expanded = _expand_prompts(prompts, wanted)

    # 1. Kling Video: 'kling' modunda tüm sahneler (maliyet tavanına kadar),
    #    'hybrid' modunda sadece kanca. (Eski kod her iki modda da yalnızca 1
    #    sahne üretiyordu — 'kling' seçilse bile kalanlar stok videoya düşüyordu.)
    kling_cap = max(int(getattr(config, "KLING_MAX_SCENES", KLING_HYBRID_SCENES)), 0)
    kling_quota = 0
    if fal_key and engine == "kling":
        kling_quota = min(wanted, kling_cap)
    elif fal_key and engine == "hybrid":
        kling_quota = min(KLING_HYBRID_SCENES, wanted, kling_cap)

    for idx in range(kling_quota):
        clip_path = str(Path(output_dir) / f"clip_{idx}.mp4")
        kling_res = generate_kling_video_clip(expanded[idx], clip_path, fal_key)
        if not kling_res:
            break  # Kling düştüyse kalanını stokla doldur
        clips.append(kling_res)

    # 2. Kalan tüm sahneler için Pexels'ten FARKLI dikey HD hareketli videolar indir
    needed_count = wanted - len(clips)
    if needed_count > 0:
        remaining_prompts = expanded[len(clips):]
        keywords = [_prompt_to_keywords(p) for p in remaining_prompts]

        stock_clips = fetch_stock_clips(
            keywords,
            count=needed_count,
            api_key=config.PEXELS_API_KEY,
            output_dir=output_dir,
            state_path=str(Path(config.MEDIA_DIR) / "used_clips.json"),
            start_index=len(clips),
        )
        clips.extend(stock_clips)

    # 3. Hiç klip bulunamadıysa (stok/kling tamamen başarısız) AI görsel + Ken Burns ile kurtar.
    # Elde en az 1 gerçek video klip varsa statik görsele düşülmez; render.py'nin
    # build_scene_sources'ı (farklı seek saniyeleriyle) akıcı videoyu korur.
    if not clips and wanted > 0:
        clips.extend(
            generate_ai_scene_clips(
                expanded,
                output_dir,
                clip_duration=clip_duration,
                start_index=0,
            )
        )

    return clips


def _prompt_to_keywords(prompt: str) -> str:
    """Sinematik AI prompt'undan anlamlı Pexels arama terimleri çıkarır."""
    noise = {
        "cinematic", "dramatic", "photorealistic", "vertical", "camera",
        "dolly", "zoom", "angle", "lighting", "detail", "unreal", "engine",
        "8k", "shot", "footage",
    }
    words = [
        w.strip(".,:;")
        for w in prompt.replace(",", " ").split()
        if len(w) > 3 and w.lower().strip(".,:;") not in noise
    ]
    return " ".join(words[:3]) or "luxury business"


def _expand_prompts(prompts: list[str], wanted: int) -> list[str]:
    """Sahne promptlarını istenen sayıya tamamlar (eksikse açı varyasyonu ekler)."""
    if not prompts:
        return [f"cinematic vertical scene {i + 1}" for i in range(wanted)]

    angles = (
        "wide establishing shot",
        "low angle close-up",
        "overhead top-down view",
        "slow dolly-in medium shot",
        "profile side view",
        "rear tracking shot",
    )
    expanded = list(prompts)
    index = 0
    while len(expanded) < wanted:
        base = prompts[index % len(prompts)]
        expanded.append(f"{base}, {angles[(index // len(prompts)) % len(angles)]}")
        index += 1
    return expanded[:wanted]


def _prompt_fingerprint(prompt: str) -> str:
    """Prompt'un normalize edilmiş parmak izi (büyük/küçük harf ve boşluk duyarsız)."""
    normalized = " ".join(prompt.lower().split())
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:16]


def _load_used_prompts(state_path: str) -> set[str]:
    path = Path(state_path)
    if not path.is_file():
        return set()
    try:
        return set(json.loads(path.read_text(encoding="utf-8")).get("used", []))
    except (json.JSONDecodeError, OSError):
        return set()


def _save_used_prompts(state_path: str, fingerprints: set[str]) -> None:
    path = Path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = list(fingerprints)[-USED_PROMPT_HISTORY_LIMIT:]
    path.write_text(json.dumps({"used": trimmed}), encoding="utf-8")


def refresh_repeated_prompts(prompts: list[str], state_path: str) -> list[str]:
    """Daha önce üretilmiş sahne promptlarını varyasyonla tazeler.

    Aynı prompt her gün aynı görseli üretiyordu (AI görsel yolu için tekrar
    koruması yoktu; stok yolda `used_clips.json` vardı). Havuz tükendiğinde
    (tüm promptlar kullanılmışsa) varyasyon eklenerek yeni kare üretilir.
    """
    if not prompts:
        return prompts

    used = _load_used_prompts(state_path)
    variations = (
        "different color palette, alternate framing",
        "unseen time of day, opposite camera direction",
        "new location, distinct texture and mood",
        "fresh composition, wider lens and new foreground",
    )

    refreshed = []
    for prompt in prompts:
        fingerprint = _prompt_fingerprint(prompt)
        if fingerprint in used:
            # Kullanılmamış bir varyasyon seç: deterministik seçim her gün aynı
            # sonucu verip görseli yine tekrarlatıyordu.
            candidates = [f"{prompt}, {v}" for v in variations]
            fresh = next(
                (c for c in candidates if _prompt_fingerprint(c) not in used),
                f"{prompt}, variation {len(used)}",
            )
            prompt = fresh
            fingerprint = _prompt_fingerprint(prompt)
        refreshed.append(prompt)
        used.add(fingerprint)

    _save_used_prompts(state_path, used)
    return refreshed

