import hashlib
import json
import time
from pathlib import Path

import requests

from app.config import config
from app.errors import FalAuthBillingError, KlingAuthBillingError
from app.http_client import session
from app.ai_visuals import generate_ai_scene_clips, build_flux_prompt

FAL_KLING_ENDPOINT = "https://queue.fal.run/fal-ai/kling-video/v2.5-turbo/pro/text-to-video"

# 'hybrid' (opt-in) modunda Kling ile üretilecek sahne sayısı (ilk sahneler = kanca).
KLING_HYBRID_SCENES = 1

# Kling kuyruğu için bekleme ayarları: 80 x 5 sn = en fazla ~6.5 dakika.
KLING_POLL_ATTEMPTS = 80
KLING_POLL_INTERVAL_SECONDS = 5

USED_PROMPT_HISTORY_LIMIT = 300
PROMPT_HISTORY_FILENAME = "used_prompts.json"

# Flux+Ken Burns varsayılan motor ve alias'ları.
FLUX_ENGINES = frozenset({"flux_kenburns", "hybrid_flux", "flux", "ai"})
KLING_OPT_IN_ENGINES = frozenset({"kling", "hybrid"})

# Auth/billing sinyalleri — HTTP 401/403 dışında body'de de görülebilir (402, FAILED).
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


def is_kling_auth_or_billing_failure(
    status_code: int | None,
    body_text: str = "",
) -> bool:
    """401/403/402 veya body'deki bakiye/yetki ifadeleri → hard-fail (stok yok)."""
    if status_code in (401, 402, 403):
        return True
    lower = (body_text or "").lower()
    return any(marker in lower for marker in _AUTH_BILLING_MARKERS)


# Flux / genel Fal için aynı sınıflandırıcı.
is_fal_auth_or_billing_failure = is_kling_auth_or_billing_failure


def _raise_if_auth_billing(resp, context: str) -> None:
    """HTTP yanıtı auth/billing ise FalAuthBillingError fırlatır."""
    status = getattr(resp, "status_code", None)
    body = _safe_response_text(resp)
    if is_fal_auth_or_billing_failure(status, body):
        raise FalAuthBillingError(
            f"Fal {context}: HTTP {status}",
            status_code=status,
            detail=body,
        )


def generate_kling_video_clip(
    prompt: str,
    output_path: str,
    fal_key: str,
    duration: int = 5,
    aspect_ratio: str = "9:16",
) -> str | None:
    """Fal.ai Kling T2V. Auth/billing → FalAuthBillingError; geçici → None."""
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
        resp = session.post(FAL_KLING_ENDPOINT, headers=headers, json=payload, timeout=30)
        _raise_if_auth_billing(resp, "kling queue submit")
        resp.raise_for_status()
        data = resp.json()
        request_id = data.get("request_id")
        status_url = data.get("status_url") or (
            f"https://queue.fal.run/fal-ai/kling-video/requests/{request_id}/status"
        )
        response_url = data.get("response_url") or (
            f"https://queue.fal.run/fal-ai/kling-video/requests/{request_id}"
        )

        for attempt in range(KLING_POLL_ATTEMPTS):
            time.sleep(KLING_POLL_INTERVAL_SECONDS)
            s_resp = session.get(status_url, headers=headers, timeout=15)
            _raise_if_auth_billing(s_resp, "kling status poll")
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
                _raise_if_auth_billing(r_resp, "kling result fetch")
                video_url = r_resp.json().get("video", {}).get("url")
                if video_url:
                    clip_bytes = session.get(video_url, timeout=60).content
                    Path(output_path).write_bytes(clip_bytes)
                    return output_path
            elif status in ("FAILED", "CANCELLED"):
                detail = json.dumps(s_data, ensure_ascii=False)[:400]
                if is_fal_auth_or_billing_failure(None, detail):
                    raise FalAuthBillingError(
                        "Kling/Fal queue FAILED with auth/billing signal",
                        status_code=None,
                        detail=detail,
                    )
                print(f"[kling] Üretim başarısız: {s_data}", flush=True)
                break
    except (FalAuthBillingError, KlingAuthBillingError):
        raise
    except requests.HTTPError as e:
        resp = e.response
        status = getattr(resp, "status_code", None) if resp is not None else None
        body = _safe_response_text(resp) if resp is not None else ""
        if is_fal_auth_or_billing_failure(status, body):
            raise FalAuthBillingError(
                f"Kling/Fal HTTPError: HTTP {status}",
                status_code=status,
                detail=body,
            ) from e
        print(
            f"[kling] Fal.ai Kling API geçici HTTP hatası ({e}) — soft-fail.",
            flush=True,
        )
        return None
    except (requests.Timeout, requests.ConnectionError) as e:
        print(f"[kling] Fal.ai Kling ağ/timeout hatası ({e}) — soft-fail.", flush=True)
        return None
    except Exception as e:
        print(f"[kling] Fal.ai Kling API hatası ({e}) — soft-fail.", flush=True)
        return None

    print(
        f"[kling] {KLING_POLL_ATTEMPTS * KLING_POLL_INTERVAL_SECONDS} sn içinde "
        "yanıt gelmedi — soft-fail.",
        flush=True,
    )
    return None


def _normalize_engine(raw: str) -> str:
    engine = (raw or "flux_kenburns").strip().lower()
    if engine in ("hybrid_flux", "flux"):
        return "flux_kenburns"
    return engine


def _stock_allowed() -> bool:
    return bool(getattr(config, "ALLOW_STOCK_FALLBACK", False))


def generate_video_scenes(
    prompts: list[str],
    output_dir: str,
    clip_duration: float = 2.5,
    target_count: int | None = None,
    topic: str = "",
    visual_keywords: list[str] | None = None,
    concrete_nouns: list[str] | None = None,
    stats_out: dict | None = None,
) -> list[str]:
    """Sahne üretim motoru — varsayılan: Flux stills + Ken Burns.

    Engines:
      flux_kenburns / hybrid_flux — Flux+Ken Burns; Kling yok; stok yalnız ALLOW_STOCK_FALLBACK
      hybrid — opt-in: hook Kling (kota) + gövde Flux; auth fail → hard-fail
      kling — opt-in T2V; kalan Flux
      stock — açık Pexels yolu
      ai — legacy Pollinations/Flux still path

    FalAuthBillingError: 401/402/403/billing → yükseltilir; sessiz Pexels YOK.
    """
    from app.stock_media import build_scene_search_query

    fal_key = config.FAL_KEY
    engine = _normalize_engine(config.VISUAL_ENGINE)
    clips: list[str] = []
    scene_log: list[dict] = []

    wanted = max(target_count or len(prompts), 1)
    prompts = refresh_repeated_prompts(
        prompts, str(Path(config.MEDIA_DIR) / PROMPT_HISTORY_FILENAME)
    )
    expanded = _expand_prompts(prompts, wanted)
    kw_hints = list(visual_keywords or [])
    nouns = list(concrete_nouns or [])

    # --- 1) Opsiyonel Kling kotası (yalnızca hybrid / kling) ---
    kling_cap = max(int(getattr(config, "KLING_MAX_SCENES", KLING_HYBRID_SCENES)), 0)
    kling_quota = 0
    if fal_key and engine == "kling":
        kling_quota = min(wanted, kling_cap)
    elif fal_key and engine == "hybrid":
        kling_quota = min(KLING_HYBRID_SCENES, wanted, kling_cap)

    kling_used = 0
    for idx in range(kling_quota):
        clip_path = str(Path(output_dir) / f"clip_{idx}.mp4")
        query = build_scene_search_query(
            topic,
            prompt=expanded[idx],
            keyword_hint=kw_hints[idx % len(kw_hints)] if kw_hints else None,
            scene_index=idx,
        )
        # Auth/billing burada yükselir — stok döngüsüne girilmez.
        kling_res = generate_kling_video_clip(expanded[idx], clip_path, fal_key)
        if not kling_res:
            break
        clips.append(kling_res)
        kling_used += 1
        scene_log.append(
            {
                "scene": idx,
                "source": "kling",
                "query": query,
                "prompt_excerpt": expanded[idx][:120],
            }
        )

    # --- 2) Kalan sahneler: Flux+Ken Burns (default); stok yalnız kapı açıkken ---
    stock_meta_total = {
        "fresh_downloads": 0,
        "cache_reuse_downloads": 0,
        "queries": [],
    }
    # hybrid/kling soft-miss sonrası da Flux; stock yalnız ALLOW_STOCK_FALLBACK veya engine=stock.
    prefer_flux = engine != "stock"

    while len(clips) < wanted:
        idx = len(clips)
        prompt = expanded[idx]
        hint = kw_hints[idx % len(kw_hints)] if kw_hints else None
        query = build_scene_search_query(
            topic, prompt=prompt, keyword_hint=hint, scene_index=idx
        )
        flux_prompt = build_flux_prompt(
            prompt,
            topic=topic,
            concrete_nouns=nouns,
            keyword_hint=hint,
            scene_index=idx,
        )
        print(
            f"[visual] scene={idx} relevance_query={query!r} engine={engine}",
            flush=True,
        )

        filled = False

        # 2a) Flux / AI Ken Burns (birincil yol — Kling başarısı için zorunlu değil)
        if prefer_flux:
            ai_clips = generate_ai_scene_clips(
                [flux_prompt],
                output_dir,
                clip_duration=clip_duration,
                start_index=idx,
                prefer_fal=True,
            )
            if ai_clips:
                clips.extend(ai_clips)
                scene_log.append(
                    {
                        "scene": idx,
                        "source": "flux_kenburns",
                        "query": query,
                        "prompt_excerpt": flux_prompt[:120],
                    }
                )
                filled = True

        # 2b) Stock — yalnız engine=stock VEYA ALLOW_STOCK_FALLBACK=true (son çare)
        if not filled and (engine == "stock" or _stock_allowed()):
            from app.stock_media import fetch_stock_clips

            scene_meta: dict = {}
            stock_clips = fetch_stock_clips(
                [query],
                count=1,
                api_key=config.PEXELS_API_KEY,
                output_dir=output_dir,
                state_path=str(Path(config.MEDIA_DIR) / "used_clips.json"),
                start_index=idx,
                topic=topic,
                allow_used_id_reuse=False,
                fallback_on_empty=False,
                meta_out=scene_meta,
            )
            stock_meta_total["queries"].extend(scene_meta.get("queries") or [query])
            stock_meta_total["fresh_downloads"] += int(scene_meta.get("fresh_downloads") or 0)
            stock_meta_total["cache_reuse_downloads"] += int(
                scene_meta.get("cache_reuse_downloads") or 0
            )
            if stock_clips:
                clips.extend(stock_clips)
                scene_log.append(
                    {
                        "scene": idx,
                        "source": "pexels",
                        "query": query,
                        "prompt_excerpt": prompt[:120],
                    }
                )
                filled = True

        # 2c) Flux miss → kalan Kling bütçesi (yalnızca opt-in hybrid/kling)
        if not filled:
            extra_kling_ok = (
                fal_key
                and engine in KLING_OPT_IN_ENGINES
                and kling_used < kling_cap
            )
            if extra_kling_ok:
                clip_path = str(Path(output_dir) / f"clip_{idx}.mp4")
                kling_res = generate_kling_video_clip(prompt, clip_path, fal_key)
                if kling_res:
                    clips.append(kling_res)
                    kling_used += 1
                    scene_log.append(
                        {
                            "scene": idx,
                            "source": "kling_stock_miss",
                            "query": query,
                            "prompt_excerpt": prompt[:120],
                        }
                    )
                    filled = True

        if not filled:
            print(
                f"[visual] scene={idx} için Flux/Kling/stok başarısız; zincir kırılıyor "
                f"(ALLOW_STOCK_FALLBACK={_stock_allowed()}).",
                flush=True,
            )
            break

    # --- 3) Hiç klip yoksa Flux ile kurtar (Pexels emergency YOK) ---
    if not clips and wanted > 0 and engine != "stock":
        rescue_prompts = [
            build_flux_prompt(p, topic=topic, concrete_nouns=nouns, scene_index=i)
            for i, p in enumerate(expanded)
        ]
        clips.extend(
            generate_ai_scene_clips(
                rescue_prompts,
                output_dir,
                clip_duration=clip_duration,
                start_index=0,
                prefer_fal=True,
            )
        )
        for i, p in enumerate(rescue_prompts[: len(clips)]):
            scene_log.append(
                {
                    "scene": i,
                    "source": "flux_kenburns_emergency",
                    "query": build_scene_search_query(topic, prompt=p, scene_index=i),
                    "prompt_excerpt": p[:120],
                }
            )

    stock_total = (
        stock_meta_total["fresh_downloads"] + stock_meta_total["cache_reuse_downloads"]
    )
    stock_cache_reuse_ratio = (
        round(stock_meta_total["cache_reuse_downloads"] / stock_total, 3)
        if stock_total
        else 0.0
    )
    if stats_out is not None:
        stats_out.update(
            {
                "scene_relevance": scene_log,
                "stock_cache_reuse_ratio": stock_cache_reuse_ratio,
                "kling_scenes": kling_used,
                "stock_queries": stock_meta_total["queries"],
                "engine_effective": engine,
            }
        )

    return clips


def _prompt_to_keywords(prompt: str) -> str:
    """Sinematik AI prompt'undan anlamlı Pexels arama terimleri çıkarır."""
    from app.stock_media import build_scene_search_query, prompt_concrete_terms

    concrete = prompt_concrete_terms(prompt, max_terms=3)
    if concrete:
        return " ".join(concrete)
    return build_scene_search_query("", prompt=prompt)


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
    """Daha önce üretilmiş sahne promptlarını varyasyonla tazeler."""
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
