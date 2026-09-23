import json
import random
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path

import requests

from app.config import config
from app.errors import FalAuthBillingError
from app.http_client import session

MOTION_PATTERNS = ["zoom_in", "zoom_out", "zoom_in", "zoom_out"]
PEXELS_PHOTO_SEARCH_URL = "https://api.pexels.com/v1/search"

FAL_FLUX_ENDPOINT = "https://queue.fal.run/fal-ai/flux/schnell"
FLUX_POLL_ATTEMPTS = 40
FLUX_POLL_INTERVAL_SECONDS = 2

DARK_WEALTH_STYLE = (
    "Dark Wealth cinematic still, old-money aesthetic, chiaroscuro lighting, "
    "deep shadows, muted gold accents, photorealistic 9:16 vertical frame, "
    "no text, no watermark, no logo overlay"
)

_AUTH_BILLING_MARKERS = (
    "exhausted balance",
    "user is locked",
    "insufficient credit",
    "insufficient balance",
    "payment required",
    "billing",
    "unauthorized",
    "forbidden",
    "invalid key",
    "invalid api key",
    "authentication",
    "not authenticated",
    "access denied",
)


def _safe_response_text(resp) -> str:
    try:
        return (resp.text or "")[:400]
    except Exception:
        return ""


def _is_fal_auth_billing(status_code: int | None, body_text: str = "") -> bool:
    if status_code in (401, 402, 403):
        return True
    lower = (body_text or "").lower()
    return any(m in lower for m in _AUTH_BILLING_MARKERS)


def _raise_if_fal_auth(resp, context: str) -> None:
    status = getattr(resp, "status_code", None)
    body = _safe_response_text(resp)
    if _is_fal_auth_billing(status, body):
        raise FalAuthBillingError(
            f"Fal Flux {context}: HTTP {status}",
            status_code=status,
            detail=body,
        )


def build_flux_prompt(
    prompt: str,
    topic: str = "",
    concrete_nouns: list[str] | None = None,
    keyword_hint: str | None = None,
    scene_index: int = 0,
) -> str:
    """Topic-anchored Flux prompt with Dark Wealth / old-money aesthetic."""
    from app.stock_media import prompt_concrete_terms, topic_anchor_terms

    nouns = [n.strip() for n in (concrete_nouns or []) if isinstance(n, str) and n.strip()]
    if not nouns:
        nouns = prompt_concrete_terms(prompt, max_terms=4)
    anchors = topic_anchor_terms(topic, max_terms=3)
    # concrete_nouns + keyword first; topic title words only fill gaps (avoid "Secret"/"Foundation" crowding).
    subject_bits: list[str] = []
    for term in nouns + ([keyword_hint.strip()] if keyword_hint else []) + anchors:
        if not term:
            continue
        if term.lower() not in {b.lower() for b in subject_bits}:
            subject_bits.append(term)
        if len(subject_bits) >= 5:
            break

    base = (prompt or "").strip()
    subject = ", ".join(subject_bits[:5])
    # Rotate slight framing cues so scenes don't look identical.
    framings = (
        "tight macro detail",
        "wide establishing, shallow depth of field",
        "low-angle hero composition",
        "overhead still life arrangement",
    )
    framing = framings[scene_index % len(framings)]
    parts = [p for p in (subject, base, framing, DARK_WEALTH_STYLE) if p]
    return ", ".join(parts)[:900]


def _fetch_pexels_photo(query: str, api_key: str, output_path: Path) -> bool:
    """Pexels HD photo — yalnız ALLOW_STOCK_FALLBACK=true iken çağrılmalı."""
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
                photo = random.choice(photos[:3])
                img_url = (
                    photo["src"].get("large2x")
                    or photo["src"].get("original")
                    or photo["src"].get("large")
                )
                if img_url:
                    img_data = session.get(img_url, timeout=20).content
                    if len(img_data) > 1024:
                        output_path.write_bytes(img_data)
                        return True
    except Exception as e:
        print(f"[ai_visuals] Pexels photo fallback uyarısı ({query}): {e}")
    return False


def generate_fal_flux_image(
    prompt: str,
    output_path: Path,
    fal_key: str,
    width: int = 768,
    height: int = 1344,
) -> Path | None:
    """Fal.ai Flux Schnell still. Auth/billing → FalAuthBillingError; transient → None."""
    if not fal_key:
        return None

    headers = {
        "Authorization": f"Key {fal_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "image_size": {"width": width, "height": height},
        "num_images": 1,
        "num_inference_steps": 4,
        "enable_safety_checker": True,
    }

    try:
        resp = session.post(FAL_FLUX_ENDPOINT, headers=headers, json=payload, timeout=30)
        _raise_if_fal_auth(resp, "queue submit")
        resp.raise_for_status()
        data = resp.json()
        request_id = data.get("request_id")
        status_url = data.get("status_url") or (
            f"https://queue.fal.run/fal-ai/flux/schnell/requests/{request_id}/status"
        )
        response_url = data.get("response_url") or (
            f"https://queue.fal.run/fal-ai/flux/schnell/requests/{request_id}"
        )

        for _ in range(FLUX_POLL_ATTEMPTS):
            time.sleep(FLUX_POLL_INTERVAL_SECONDS)
            s_resp = session.get(status_url, headers=headers, timeout=15)
            _raise_if_fal_auth(s_resp, "status poll")
            s_data = s_resp.json()
            status = s_data.get("status")
            if status == "COMPLETED":
                r_resp = session.get(response_url, headers=headers, timeout=20)
                _raise_if_fal_auth(r_resp, "result fetch")
                images = r_resp.json().get("images") or []
                img_url = images[0].get("url") if images else None
                if img_url:
                    img_bytes = session.get(img_url, timeout=60).content
                    if len(img_bytes) > 2048:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        output_path.write_bytes(img_bytes)
                        return output_path
                return None
            if status in ("FAILED", "CANCELLED"):
                detail = json.dumps(s_data, ensure_ascii=False)[:400]
                if _is_fal_auth_billing(None, detail):
                    raise FalAuthBillingError(
                        "Fal Flux queue FAILED with auth/billing signal",
                        status_code=None,
                        detail=detail,
                    )
                print(f"[ai_visuals] Fal Flux failed: {s_data}", flush=True)
                return None
    except FalAuthBillingError:
        raise
    except requests.HTTPError as e:
        resp = e.response
        status = getattr(resp, "status_code", None) if resp is not None else None
        body = _safe_response_text(resp) if resp is not None else ""
        if _is_fal_auth_billing(status, body):
            raise FalAuthBillingError(
                f"Fal Flux HTTPError: HTTP {status}",
                status_code=status,
                detail=body,
            ) from e
        print(f"[ai_visuals] Fal Flux geçici HTTP ({e})", flush=True)
        return None
    except (requests.Timeout, requests.ConnectionError) as e:
        print(f"[ai_visuals] Fal Flux ağ/timeout ({e})", flush=True)
        return None
    except Exception as e:
        print(f"[ai_visuals] Fal Flux hata ({e})", flush=True)
        return None

    print("[ai_visuals] Fal Flux zaman aşımı", flush=True)
    return None


def _generate_pollinations_image(
    prompt: str, output_path: Path, width: int, height: int
) -> Path | None:
    short_prompt = " ".join(prompt.strip().split()[:24])
    encoded_prompt = urllib.parse.quote(short_prompt)
    seed = random.randint(1, 999999)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width={width}&height={height}&model=flux&nologo=true&seed={seed}"
    )
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
        print(f"[ai_visuals] Pollinations meşgul ({short_prompt[:40]}): {e}")
    return None


def _generate_gradient_fallback(prompt: str, output_path: Path, width: int, height: int) -> Path:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), color=(12, 14, 18))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        shade = 12 + int(18 * (y / max(height, 1)))
        draw.line([(0, y), (width, y)], fill=(shade, shade + 2, shade + 6))
    draw.text((width // 8, height // 2), (prompt or "")[:36], fill=(200, 190, 170))
    img.save(str(output_path))
    return output_path


def generate_ai_image(
    prompt: str,
    output_path: Path,
    width: int = 768,
    height: int = 1344,
    prefer_fal: bool = True,
) -> Path:
    """Flux still üretir. Fal auth/billing → yükseltilir. Sessiz Pexels yok (kapılı)."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fal_key = getattr(config, "FAL_KEY", "") or ""
    if prefer_fal and fal_key:
        fal_path = generate_fal_flux_image(prompt, output_path, fal_key, width, height)
        if fal_path:
            return fal_path

    # Free Pollinations soft-fallback (not stock B-roll).
    poll = _generate_pollinations_image(prompt, output_path, width, height)
    if poll:
        return poll

    # Explicit stock photo only when gated on.
    if getattr(config, "ALLOW_STOCK_FALLBACK", False):
        search_terms = " ".join(
            [
                w
                for w in prompt.split()
                if w.lower()
                not in (
                    "cinematic",
                    "photorealistic",
                    "8k",
                    "moody",
                    "dramatic",
                    "dark",
                    "wealth",
                )
            ][:4]
        )
        if _fetch_pexels_photo(
            search_terms or "swiss watch craftsmanship",
            config.PEXELS_API_KEY,
            output_path,
        ):
            return output_path

    return _generate_gradient_fallback(prompt, output_path, width, height)


def image_to_motion_clip(
    image_path: Path,
    output_clip_path: Path,
    duration: float = 2.5,
    motion_type: str = "zoom_in",
    fps: int = 25,
) -> Path:
    """Statik görseli yumuşak Ken Burns (yavaş zoom in/out) ile 1080x1920 videoya çevirir."""
    output_clip_path = Path(output_clip_path)
    output_clip_path.parent.mkdir(parents=True, exist_ok=True)

    frames = max(int(duration * fps), 1)
    # Soft Ken Burns — slow zoom (slideshow hissini azaltır, agresif pan yok).
    if motion_type == "zoom_out":
        vf_zoom = (
            f"zoompan=z='if(lte(zoom,1.0),1.12,max(1.001,zoom-0.0008))':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps}"
        )
    elif motion_type == "punch_in":
        # Faster push for attention beats without a new download.
        vf_zoom = (
            f"zoompan=z='min(zoom+0.0016,1.28)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps}"
        )
    else:  # zoom_in (default) and any unknown → soft zoom in
        vf_zoom = (
            f"zoompan=z='min(zoom+0.0008,1.12)':"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1920:fps={fps}"
        )

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
    prefer_fal: bool = True,
) -> list[str]:
    """Sahne stilleri → soft Ken Burns klipler. FalAuthBillingError yükseltilir."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    clips = []
    for offset, prompt in enumerate(prompts):
        idx = start_index + offset
        img_path = out / f"scene_{idx}.jpg"
        clip_path = out / f"clip_{idx}.mp4"

        generate_ai_image(prompt, img_path, prefer_fal=prefer_fal)

        motion = MOTION_PATTERNS[idx % len(MOTION_PATTERNS)]
        image_to_motion_clip(img_path, clip_path, duration=clip_duration, motion_type=motion)
        clips.append(str(clip_path))

    return clips
