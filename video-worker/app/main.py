import sys
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import asyncio
import contextlib
import json
import shutil
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.analytics import build_weekly_report
from app.catchup import mark_run_today, maybe_catch_up
from app.config import config
from app.daily_digest import run_digest_loop
from app.errors import AllPlatformsFailedError
from app.image_gen import generate_image_content, render_card
from app.joblog import log_event
from app.pitch_gen import generate_pitches
from app.pipeline import generate_video
from app.publish_log import append_publish_log
from app.publishers.linkedin import upload_to_linkedin
from app.publishers.meta import upload_to_facebook, upload_to_instagram
from app.publishers.pinterest import upload_to_pinterest
from app.publishers.threads import upload_to_threads
from app.publishers.tiktok import upload_to_tiktok
from app.publishers.x import upload_to_x, upload_video_to_x
from app.publishers.youtube import upload_to_youtube
from app.telegram_bot import run_poller, send_pitches_message
from app.topics import release_topic, select_next_topic
from app.trends import fetch_trends


def _is_configured(val) -> bool:
    return isinstance(val, str) and bool(val.strip())


def _run_generate_sync(topic: str | None = None):
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    mark_run_today(str(Path(config.MEDIA_DIR) / "last_video_run.txt"))
    return generate_video(job_id, topic=topic)


async def _run_catch_up() -> None:
    try:
        triggered = await maybe_catch_up(
            config.MEDIA_DIR,
            config.VIDEO_SCHEDULE_HOUR,
            config.IMAGE_SCHEDULE_HOUR,
            generate,
            generate_image,
        )
        if triggered:
            print(f"[main] Kaçan {triggered} üretimi yakalanıp tetiklendi.", flush=True)
    except Exception as exc:
        print(f"[main] Kaçan üretim yakalama hatası: {exc}", flush=True)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    tasks = []
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        offset_path = str(Path(config.MEDIA_DIR) / "telegram_offset.json")
        tasks.append(
            asyncio.create_task(
                run_poller(
                    config.TELEGRAM_BOT_TOKEN,
                    config.TELEGRAM_CHAT_ID,
                    config.MEDIA_DIR,
                    offset_path,
                    _run_publish,
                    _run_cleanup,
                    generate_fn=_run_generate_sync,
                )
            )
        )
    else:
        print("[main] TELEGRAM_BOT_TOKEN/CHAT_ID boş — onay dinleyici başlatılmadı.", flush=True)

    tasks.append(asyncio.create_task(_run_catch_up()))

    # Günlük özet: TELEGRAM kimlikleri varsa gün sonunda (DIGEST_HOUR) bir kez
    # "bugün yayınlananlar / bekleyen onay" mesajını gönderen zamanlayıcı.
    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        tasks.append(
            asyncio.create_task(
                run_digest_loop(
                    config.TELEGRAM_BOT_TOKEN,
                    config.TELEGRAM_CHAT_ID,
                    config.MEDIA_DIR,
                    config.DIGEST_HOUR,
                    str(Path(config.MEDIA_DIR) / "digest_sent.txt"),
                    interval_seconds=config.DIGEST_INTERVAL_SECONDS,
                )
            )
        )
    else:
        print("[main] TELEGRAM_BOT_TOKEN/CHAT_ID boş — günlük özet başlatılmadı.", flush=True)

    yield

    for task in tasks:
        task.cancel()
    for task in tasks:
        with contextlib.suppress(asyncio.CancelledError):
            await task


# docs/redoc/openapi kapalı: bu servis Cloudflare tüneliyle internete açık bir
# Caddy gateway'in arkasında (bkz. docker-compose.yml, caddy/Caddyfile) — gateway
# yalnızca GET /media/* geçiriyor, ama API şemasının kendisini dışarı sızdırmamak
# ek bir savunma katmanı.
app = FastAPI(
    title="video-worker",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    lifespan=_lifespan,
)


class GenerateRequest(BaseModel):
    topic: str | None = None


class PublishRequest(BaseModel):
    video_path: str = ""
    video_filename: str = ""
    thumbnail_path: str = ""
    title: str = ""
    description: str = ""
    tags: list[str] = []
    kind: str = "video"
    image_path: str = ""
    image_filename: str = ""
    caption: str = ""


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/discover-ideas")
def discover_ideas():
    """Gündemdeki trendleri tarar, 3 viral kurgu konsepti üretir ve Telegram'a butonlu sunar."""
    trends = fetch_trends(geo="TR" if config.VIDEO_LANG == "tr" else "US")
    pitches = generate_pitches(trends, api_key=config.OPENROUTER_API_KEY, lang=config.VIDEO_LANG)

    media_dir = Path(config.MEDIA_DIR)
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "pending_pitches.json").write_text(
        json.dumps(pitches, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        try:
            send_pitches_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, pitches)
        except Exception as exc:
            print(f"[main] Telegram fikir gönderme hatası: {exc}", flush=True)

    return {"status": "ok", "pitches": pitches}


@app.post("/generate")
async def generate(req: GenerateRequest | None = None):
    pending_path = Path(config.MEDIA_DIR) / "pending.json"
    if pending_path.is_file():
        raise HTTPException(
            status_code=409,
            detail=(
                "A video is already pending approval — resolve it via "
                "Telegram before generating a new one."
            ),
        )

    mark_run_today(str(Path(config.MEDIA_DIR) / "last_video_run.txt"))
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    topic = req.topic if req else None
    try:
        return await generate_video(job_id, topic=topic)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class RemotionRequest(BaseModel):
    topic: str | None = None
    mock: bool = False


@app.post("/render-remotion")
async def render_remotion_endpoint(req: RemotionRequest | None = None):
    """Remotion + Fal.ai + ElevenLabs hibrit video hattını tetikler."""
    from app.remotion_runner import run_remotion_pipeline

    topic = req.topic if req and req.topic else "The Silent Architecture of Power"
    mock = req.mock if req else False
    try:
        return await asyncio.to_thread(run_remotion_pipeline, topic, mock=mock)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/generate-image")
async def generate_image():
    pending_path = Path(config.MEDIA_DIR) / "pending.json"
    if pending_path.is_file():
        raise HTTPException(
            status_code=409,
            detail=(
                "A job is already pending approval — resolve it via "
                "Telegram before generating a new one."
            ),
        )

    mark_run_today(str(Path(config.MEDIA_DIR) / "last_image_run.txt"))
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    media_dir = Path(config.MEDIA_DIR)
    state_path = str(media_dir / "used_image_topics.json")
    topic = None
    try:
        topic = select_next_topic(config.IMAGE_TOPICS_PATH, state_path)
        content = generate_image_content(topic, api_key=config.OPENROUTER_API_KEY)

        image_filename = f"{job_id}.png"
        image_path = str(media_dir / image_filename)
        render_card(
            content["text"],
            brand_name=config.IMAGE_BRAND_NAME,
            accent=config.IMAGE_ACCENT,
            output_path=image_path,
        )

        result = {
            "job_id": job_id,
            "kind": "image",
            "image_path": image_path,
            "image_filename": image_filename,
            "topic": topic,
            "text": content["text"],
            "caption": content["caption"],
            "hashtags": content["hashtags"],
        }
        pending_path.write_text(json.dumps(result), encoding="utf-8")
        return result
    except Exception as exc:
        if topic:
            release_topic(topic, state_path)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/pending")
def get_pending():
    pending_path = Path(config.MEDIA_DIR) / "pending.json"
    if not pending_path.is_file():
        raise HTTPException(status_code=404, detail="no pending job")
    return json.loads(pending_path.read_text(encoding="utf-8"))


@app.get("/media/{filename}")
def get_media(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    if not (filename.endswith(".mp4") or filename.endswith(".png")):
        raise HTTPException(status_code=404, detail="not found")

    pending_path = Path(config.MEDIA_DIR) / "pending.json"
    if not pending_path.is_file():
        raise HTTPException(status_code=404, detail="not found")

    pending = json.loads(pending_path.read_text(encoding="utf-8"))
    if filename != pending.get("video_filename") and filename != pending.get(
        "image_filename"
    ):
        raise HTTPException(status_code=404, detail="not found")

    file_path = Path(config.MEDIA_DIR) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="not found")

    media_type = "image/png" if filename.endswith(".png") else "video/mp4"
    return FileResponse(str(file_path), media_type=media_type)


def _run_publish(payload: dict) -> dict:
    kind = payload.get("kind", "video")
    job_id = Path(payload.get("video_filename") or payload.get("image_filename") or "unknown").stem

    if kind == "image":
        results = [
            upload_to_x(
                payload.get("image_path", ""),
                payload.get("caption", ""),
                client_id=config.X_CLIENT_ID,
                client_secret=config.X_CLIENT_SECRET,
                refresh_token=config.X_REFRESH_TOKEN,
            ),
            upload_to_linkedin(
                payload.get("image_path", ""),
                payload.get("caption", ""),
                client_id=config.LINKEDIN_CLIENT_ID,
                client_secret=config.LINKEDIN_CLIENT_SECRET,
                refresh_token=config.LINKEDIN_REFRESH_TOKEN,
                author_urn=config.LINKEDIN_AUTHOR_URN,
            ),
        ]
        entry_title = payload.get("caption") or "Görsel gönderi"
        cleanup_path = payload.get("image_path", "")
    else:
        results = [
            upload_to_youtube(
                payload.get("video_path", ""),
                title=payload.get("title", ""),
                description=payload.get("description", ""),
                tags=payload.get("tags", []),
                client_id=config.YOUTUBE_CLIENT_ID,
                client_secret=config.YOUTUBE_CLIENT_SECRET,
                refresh_token=config.YOUTUBE_REFRESH_TOKEN,
                thumbnail_path=payload.get("thumbnail_path", ""),
            ),
            upload_to_tiktok(
                payload.get("video_path", ""),
                title=payload.get("title", ""),
                client_key=config.TIKTOK_CLIENT_KEY,
                client_secret=config.TIKTOK_CLIENT_SECRET,
                token_path=config.TIKTOK_TOKEN_PATH,
                audited=config.TIKTOK_AUDITED,
            ),
            upload_to_instagram(
                payload.get("video_filename", ""),
                caption=payload.get("description", ""),
                ig_user_id=config.META_IG_USER_ID,
                page_access_token=config.META_PAGE_ACCESS_TOKEN,
                tunnel_log_path=config.TUNNEL_LOG_PATH,
            ),
            upload_to_facebook(
                payload.get("video_path", ""),
                description=payload.get("description", ""),
                page_id=config.META_PAGE_ID,
                page_access_token=config.META_PAGE_ACCESS_TOKEN,
            ),
        ]
        if _is_configured(config.THREADS_USER_ID) and _is_configured(config.THREADS_ACCESS_TOKEN):
            results.append(
                upload_to_threads(
                    payload.get("video_filename", ""),
                    caption=f"{payload.get('title', '')}\n\n{payload.get('description', '')}",
                    threads_user_id=config.THREADS_USER_ID,
                    access_token=config.THREADS_ACCESS_TOKEN,
                    tunnel_log_path=config.TUNNEL_LOG_PATH,
                )
            )
        if _is_configured(config.X_REFRESH_TOKEN) and _is_configured(config.X_CLIENT_ID):
            results.append(
                upload_video_to_x(
                    payload.get("video_path", ""),
                    text=f"{payload.get('title', '')}\n\n{' '.join('#' + t for t in payload.get('tags', [])[:3])}",
                    client_id=config.X_CLIENT_ID,
                    client_secret=config.X_CLIENT_SECRET,
                    refresh_token=config.X_REFRESH_TOKEN,
                )
            )
        if _is_configured(config.PINTEREST_REFRESH_TOKEN) and _is_configured(config.PINTEREST_BOARD_ID):
            results.append(
                upload_to_pinterest(
                    payload.get("video_path", ""),
                    title=payload.get("title", ""),
                    description=payload.get("description", ""),
                    client_id=config.PINTEREST_CLIENT_ID,
                    client_secret=config.PINTEREST_CLIENT_SECRET,
                    refresh_token=config.PINTEREST_REFRESH_TOKEN,
                    board_id=config.PINTEREST_BOARD_ID,
                )
            )
        entry_title = payload.get("title", "")
        cleanup_path = payload.get("video_path", "")

    for r in results:
        log_event(
            job_id, "publish_result",
            platform=r["platform"], status=r["status"], error=r.get("error"),
        )

    entry = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "title": entry_title,
        "kind": kind,
        "platforms": {r["platform"]: r for r in results},
    }
    append_publish_log(str(Path(config.MEDIA_DIR) / "published_log.json"), entry)

    pending_path = Path(config.MEDIA_DIR) / "pending.json"
    any_success = any(r["status"] == "success" for r in results)

    if any_success:
        Path(cleanup_path).unlink(missing_ok=True)
        thumbnail_path = payload.get("thumbnail_path")
        if thumbnail_path:
            Path(thumbnail_path).unlink(missing_ok=True)
        pending_path.unlink(missing_ok=True)
        success_count = sum(1 for r in results if r["status"] == "success")
        log_event(job_id, "publish_complete", success_count=success_count, total=len(results))
        return {"results": results}

    # Tüm platformlar başarısız oldu: dosyayı kaybetme. failed/ altına taşı,
    # tam payload'ı sidecar JSON olarak sakla ki Telegram'daki "Tekrar dene"
    # butonu aynı işi yeniden deneyebilsin.
    log_event(job_id, "publish_all_failed", total=len(results))
    src = Path(cleanup_path) if cleanup_path else None
    if src and src.is_file():
        failed_dir = Path(config.MEDIA_DIR) / "failed"
        failed_dir.mkdir(parents=True, exist_ok=True)
        dest = failed_dir / src.name
        if src.resolve() != dest.resolve():
            shutil.move(str(src), str(dest))
        retry_payload = dict(payload)
        if kind == "image":
            retry_payload["image_path"] = str(dest)
        else:
            retry_payload["video_path"] = str(dest)
        (failed_dir / f"{job_id}.json").write_text(
            json.dumps(retry_payload, ensure_ascii=False), encoding="utf-8"
        )
    pending_path.unlink(missing_ok=True)
    raise AllPlatformsFailedError(job_id, results)


def _run_cleanup(filename: str) -> None:
    file_path = Path(config.MEDIA_DIR) / filename
    file_path.unlink(missing_ok=True)
    (Path(config.MEDIA_DIR) / "pending.json").unlink(missing_ok=True)


@app.post("/publish")
def publish(payload: PublishRequest):
    try:
        return _run_publish(payload.model_dump())
    except AllPlatformsFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/analytics/weekly")
def analytics_weekly():
    report = build_weekly_report(
        str(Path(config.MEDIA_DIR) / "published_log.json"),
        youtube_creds={
            "client_id": config.YOUTUBE_CLIENT_ID,
            "client_secret": config.YOUTUBE_CLIENT_SECRET,
            "refresh_token": config.YOUTUBE_REFRESH_TOKEN,
        },
        meta_creds={"page_access_token": config.META_PAGE_ACCESS_TOKEN},
    )
    return {"report": report}


@app.delete("/cleanup/{filename}")
def cleanup(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    _run_cleanup(filename)

    return {"status": "deleted", "filename": filename}
