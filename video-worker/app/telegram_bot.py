import asyncio
import json
from pathlib import Path
from typing import Callable

import requests

from app import jobs as job_store
from app.errors import AllPlatformsFailedError

API_URL = "https://api.telegram.org/bot{token}/{method}"
POLL_TIMEOUT_SECONDS = 25
REQUEST_TIMEOUT_SECONDS = POLL_TIMEOUT_SECONDS + 10


def _call(token: str, method: str, **params) -> dict:
    response = requests.post(
        API_URL.format(token=token, method=method),
        json=params,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def send_message(token: str, chat_id: str, text: str, reply_markup: dict = None) -> None:
    params = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        params["reply_markup"] = reply_markup
    _call(token, "sendMessage", **params)


def send_video(token: str, chat_id: str, video_path: str, caption: str = "", reply_markup: dict = None) -> dict:
    url = API_URL.format(token=token, method="sendVideo")
    data = {"chat_id": chat_id, "caption": caption, "parse_mode": "Markdown"}
    if reply_markup:
        data["reply_markup"] = json.dumps(reply_markup)
    with open(video_path, "rb") as vf:
        response = requests.post(url, data=data, files={"video": vf}, timeout=120)
    response.raise_for_status()
    return response.json()


def send_pitches_message(token: str, chat_id: str, pitches: list[dict]) -> None:
    lines = ["💡 *Günün Viral Video Fikirleri (Trend Gündem)*\n"]
    row1 = []
    for p in pitches:
        pid = p.get("id")
        cat = p.get("category_label", p.get("category", "Fikir"))
        title = p.get("title", "")
        hook = p.get("hook", "")
        lines.append(f"{pid}️⃣ *{cat}*\n📌 *{title}*\n🎯 _\"{hook}\"_\n")
        row1.append({"text": f"{pid}️⃣ {cat}", "callback_data": f"pitch:{pid}"})

    lines.append("Hangi kurguyu üretelim? Aşağıdaki butonlardan birini seç:")
    reply_markup = {
        "inline_keyboard": [
            row1,
            [{"text": "🎲 Rastgele Birini Üret", "callback_data": "pitch:random"}],
        ]
    }
    send_message(token, chat_id, "\n".join(lines), reply_markup=reply_markup)


def answer_callback_query(token: str, callback_query_id: str) -> None:
    _call(token, "answerCallbackQuery", callback_query_id=callback_query_id)


def get_updates(token: str, offset: int, timeout: int) -> dict:
    return _call(
        token,
        "getUpdates",
        offset=offset,
        timeout=timeout,
        allowed_updates=["callback_query", "message"],
    )


def _load_offset(offset_path: str) -> int:
    path = Path(offset_path)
    if not path.is_file():
        return 0
    return json.loads(path.read_text(encoding="utf-8")).get("offset", 0)


def _save_offset(offset_path: str, offset: int) -> None:
    Path(offset_path).write_text(json.dumps({"offset": offset}), encoding="utf-8")


def _format_summary(title: str, results: list[dict]) -> str:
    lines = [f'📤 "{title}"', ""]
    for result in results:
        if result["status"] == "success":
            lines.append(f"✅ {result['platform']}: başarılı")
        else:
            lines.append(f"❌ {result['platform']}: {result.get('error', 'hata')}")
    return "\n".join(lines)


def _retry_keyboard(job_id: str) -> dict:
    return {"inline_keyboard": [[{"text": "🔁 Tekrar dene", "callback_data": f"retry:{job_id}"}]]}


def handle_callback(
    data: str,
    media_dir: str,
    token: str,
    chat_id: str,
    publish_fn: Callable[[dict], dict],
    cleanup_fn: Callable[[str], None],
    generate_fn: Callable[[str], dict] | None = None,
) -> None:
    """Bir Telegram callback_query.data değerini işler ve sonucu chat'e bildirir."""
    if data == "approve":
        pending = job_store.read_pending_payload(media_dir)
        if not pending:
            send_message(token, chat_id, "Bekleyen iş yok.")
            return
        _publish_and_report(pending, token, chat_id, publish_fn)
        return

    if data == "reject":
        pending = job_store.read_pending_payload(media_dir)
        if not pending:
            send_message(token, chat_id, "Bekleyen iş yok.")
            return
        filename = pending.get("video_filename") or pending.get("image_filename", "")
        cleanup_fn(filename)
        send_message(token, chat_id, "❌ İptal edildi, yeni içerik beklenecek.")
        return

    if data.startswith("pitch:"):
        choice = data.split(":", 1)[1]
        pitches_file = Path(media_dir) / "pending_pitches.json"
        if not pitches_file.is_file():
            send_message(token, chat_id, "⚠️ Bekleyen fikir listesi bulunamadı.")
            return

        try:
            pitches = json.loads(pitches_file.read_text(encoding="utf-8"))
        except Exception:
            pitches = []

        selected = None
        if choice == "random" and pitches:
            import random
            selected = random.choice(pitches)
        else:
            for p in pitches:
                if str(p.get("id")) == choice:
                    selected = p
                    break

        if not selected:
            send_message(token, chat_id, f"⚠️ Seçilen fikir (#{choice}) bulunamadı.")
            return

        title = selected.get("title", "Seçilen Kurgu")
        topic = selected.get("topic", title)
        category_label = selected.get("category_label", "Kurgu")

        send_message(
            token,
            chat_id,
            f"🎬 *{category_label}* seçildi!\n"
            f"📌 *Başlık:* {title}\n\n"
            f"⏳ Video render ediliyor (tahmini 30 sn)...",
        )

        if generate_fn:
            try:
                import asyncio
                import inspect

                def _deliver(res):
                    if not isinstance(res, dict):
                        return
                    from app.pipeline import format_approval_caption

                    video_path = res.get("video_path")
                    caption = format_approval_caption(res)
                    keyboard = {
                        "inline_keyboard": [
                            [
                                {"text": "✅ Onayla & Yayınla", "callback_data": "approve"},
                                {"text": "❌ Reddet", "callback_data": "reject"},
                            ]
                        ]
                    }
                    if video_path and Path(video_path).is_file():
                        send_video(token, chat_id, video_path, caption=caption, reply_markup=keyboard)
                    else:
                        send_message(token, chat_id, f"✅ Video hazır: {res.get('title')}", reply_markup=keyboard)

                if inspect.iscoroutinefunction(generate_fn):
                    coro = generate_fn(topic)
                else:
                    res_raw = generate_fn(topic)
                    coro = res_raw if inspect.iscoroutine(res_raw) else None
                    if coro is None:
                        _deliver(res_raw)

                if coro is not None:
                    try:
                        loop = asyncio.get_running_loop()
                        async def _task():
                            try:
                                r = await coro
                                _deliver(r)
                            except Exception as e:
                                send_message(token, chat_id, f"❌ Video üretilirken hata oluştu: {e}")
                        loop.create_task(_task())
                    except RuntimeError:
                        result = asyncio.run(coro)
                        _deliver(result)
            except Exception as exc:
                send_message(token, chat_id, f"❌ Video üretilirken hata oluştu: {exc}")
        return

    if data.startswith("retry:"):
        job_id = data.split(":", 1)[1]
        sidecar = Path(media_dir) / "failed" / f"{job_id}.json"
        if not sidecar.is_file():
            send_message(token, chat_id, "Bu iş artık bulunamadı (silinmiş olabilir).")
            return
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
        sidecar.unlink(missing_ok=True)
        _publish_and_report(payload, token, chat_id, publish_fn, prefix="🔁 ")
        return

    send_message(token, chat_id, f"Bilinmeyen işlem: {data}")


def _publish_and_report(
    payload: dict,
    token: str,
    chat_id: str,
    publish_fn: Callable[[dict], dict],
    prefix: str = "",
) -> None:
    title = payload.get("title") or payload.get("caption", "")
    try:
        result = publish_fn(payload)
    except AllPlatformsFailedError as exc:
        lines = [f'❌ "{title}" — tüm platformlar başarısız.']
        lines += [f"  {r['platform']}: {r.get('error', 'hata')}" for r in exc.results]
        send_message(token, chat_id, "\n".join(lines), reply_markup=_retry_keyboard(exc.job_id))
        return
    send_message(token, chat_id, prefix + _format_summary(title, result["results"]))


def _extract_topic_from_text(text: str) -> str:
    """Kullanıcının doğal konuşma metninden video konusunu ayıklar."""
    import re
    patterns = [
        r"^(?:bana|lütfen|hadi)?\s*(.+?)\s*(?:hakkında|ile ilgili|konulu|temalı)\s+(?:bir\s+)?(?:video|short|shorts|reels)?\s*(?:yap|üret|hazırla|çek|patlat|kurgula|render et|render al)?\.?$",
        r"^(?:bana|lütfen|hadi)?\s*(?:bir\s+)?(?:video|short|shorts|reels)\s+(?:yap|üret|hazırla|çek|patlat)\s*[:,-]?\s*(.+)$",
        r"^(?:remotion|video)\s+(?:ile\s+)?(?:yap|üret)?\s*[:,-]?\s*(.+)$",
    ]
    for pat in patterns:
        m = re.match(pat, text, re.IGNORECASE)
        if m and m.group(1):
            extracted = m.group(1).strip(" \"'.,:;-")
            if len(extracted) > 2:
                return extracted.capitalize()

    stopwords = {
        "bana", "bir", "video", "videolar", "short", "shorts", "reels",
        "yap", "yapalım", "üret", "üretelim", "hazırla", "çek", "çekelim",
        "patlat", "hakkında", "ile", "ilgili", "konulu", "lütfen", "hadi",
        "render", "remotion", "et", "al"
    }
    words = text.split()
    filtered = [w for w in words if w.lower().strip(".,?!:;") not in stopwords]
    if filtered:
        return " ".join(filtered).strip(" \"'.,:;-").capitalize()
    return ""


def parse_natural_intent(text: str) -> dict:
    """Kullanıcının yazdığı metinden niyeti (intent) ve parametreleri çıkarır."""
    t = text.strip()
    t_lower = t.lower()

    if any(w in t_lower for w in ["yayınla", "yayinla", "onayla", "at gitsin", "paylaş", "paylas", "gönder", "gonder"]):
        return {"intent": "approve"}

    if any(w in t_lower for w in ["iptal", "reddet", "sil", "beğenmedim", "begenmedim", "vazgeç", "vazgec", "olmadı"]):
        return {"intent": "reject"}

    if any(w in t_lower for w in ["durum", "ne durumdayız", "ne durumdayiz", "kuyruk", "rapor", "istatistik", "bitti mi", "hazır mı", "hazir mi", "/status"]):
        return {"intent": "status"}

    if any(w in t_lower for w in ["fikir", "trend", "ne çekelim", "ne cekelim", "öneri", "oneri", "konsept", "/ideas", "/pitch"]):
        return {"intent": "ideas"}

    video_triggers = [
        "video", "short", "shorts", "reels", "üret", "uret", "hazırla", "hazirla",
        "çek", "cek", "yap", "patlat", "kurgula", "render", "remotion", "/video", "/remotion"
    ]
    if any(w in t_lower for w in video_triggers):
        topic = _extract_topic_from_text(t)
        engine = "remotion" if "remotion" in t_lower else "auto"
        return {"intent": "generate_video", "topic": topic, "engine": engine}

    if any(w in t_lower for w in ["selam", "merhaba", "yardım", "yardim", "neler yapabilirsin", "komutlar", "hey", "miko", "/start", "/help"]):
        return {"intent": "greeting"}

    if len(t) >= 4 and len(t.split()) <= 6:
        return {"intent": "generate_video", "topic": t, "engine": "auto"}

    return {"intent": "chat", "text": t}


async def handle_natural_message(
    text: str,
    token: str,
    chat_id: str,
    media_dir: str,
    publish_fn: Callable[[dict], dict],
    cleanup_fn: Callable[[str], None],
    generate_fn: Callable[[str], dict] | None = None,
) -> None:
    """Telegram'a yazılan doğal metinleri işler."""
    intent_data = parse_natural_intent(text)
    intent = intent_data.get("intent")

    if intent == "approve":
        pending = job_store.read_pending_payload(media_dir)
        if not pending:
            send_message(token, chat_id, "ℹ️ Şu an onay bekleyen herhangi bir video bulunmuyor.")
            return
        _publish_and_report(pending, token, chat_id, publish_fn)
        return

    if intent == "reject":
        pending = job_store.read_pending_payload(media_dir)
        if not pending:
            send_message(token, chat_id, "ℹ️ İptal edilecek bir video bulunmuyor.")
            return
        filename = pending.get("video_filename") or pending.get("image_filename", "")
        cleanup_fn(filename)
        send_message(token, chat_id, "❌ Mevcut video iptal edildi ve silindi. Yeni bir konu başlatabilirsin.")
        return

    if intent == "status":
        lines = ["📊 *Otonom Video Üretim Hattı Durumu:*\n"]
        status_file = Path(media_dir) / "pipeline_status.json"
        if status_file.is_file():
            try:
                st = json.loads(status_file.read_text(encoding="utf-8"))
                lines.append(f"• Son Süreç: *{st.get('details', 'Boşta')}* (%{st.get('progress', 0)})")
                if st.get("topic"):
                    lines.append(f"• Aktif Konu: *{st.get('topic')}*")
            except Exception:
                pass

        pending = job_store.read_pending_payload(media_dir)
        if pending:
            lines.append(f"\n⏳ *Onay Bekleyen Video:* {pending.get('title')}")
            lines.append("Yayınlamak için *'Yayınla'* veya *'İptal'* yazabilirsin.")
        else:
            lines.append("\n✅ Onay bekleyen iş yok, sistem yeni üretime hazır.")

        send_message(token, chat_id, "\n".join(lines))
        return

    if intent == "ideas":
        send_message(token, chat_id, "🔍 Gündemdeki viral trendler taranıyor, lütfen bekle...")
        from app.trends import fetch_trends
        from app.pitch_gen import generate_pitches
        from app.config import config

        trends = fetch_trends(geo="TR" if config.VIDEO_LANG == "tr" else "US")
        pitches = generate_pitches(trends, api_key=config.OPENROUTER_API_KEY, lang=config.VIDEO_LANG)
        (Path(media_dir) / "pending_pitches.json").write_text(
            json.dumps(pitches, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        send_pitches_message(token, chat_id, pitches)
        return

    if intent == "generate_video":
        topic = intent_data.get("topic")
        if not topic:
            topics_file = Path(media_dir).parent / "video-worker" / "data" / "topics_dark_wealth.json"
            if topics_file.is_file():
                try:
                    pool = json.loads(topics_file.read_text(encoding="utf-8"))
                    used_f = Path(media_dir) / "used_topics.json"
                    used = json.loads(used_f.read_text(encoding="utf-8")).get("used_topics", []) if used_f.is_file() else []
                    rem = [t for t in pool if t not in used]
                    topic = rem[0] if rem else "The Silent Architecture of Power"
                except Exception:
                    topic = "The Silent Architecture of Power"
            else:
                topic = "The Silent Architecture of Power"

        if pending_path.is_file():
            try:
                p = json.loads(pending_path.read_text(encoding="utf-8"))
                send_message(
                    token,
                    chat_id,
                    f"⚠️ Zaten onay bekleyen bir video var: *\"{p.get('title')}\"*\n\n"
                    "Yeni bir video üretmeden önce mevcut videoyu onaylamak için *'Yayınla'* veya iptal etmek için *'İptal'* yazabilirsin.",
                )
                return
            except Exception:
                pass

        send_message(
            token,
            chat_id,
            f"🎬 Harika bir fikir!\n\n"
            f"📌 *Konu:* {topic}\n"
            f"⚡ *Motor:* Remotion 9:16 Kinetik Tipografi & Fal.ai\n\n"
            f"⏳ Senaryo hazırlanıyor, ses sentezleniyor ve render alınıyor...\n"
            f"Video hazır olduğunda doğrudan buraya göndereceğim!",
        )

        async def _run_bg():
            try:
                from app.remotion_runner import run_remotion_pipeline
                res = await asyncio.to_thread(run_remotion_pipeline, topic)
                video_path = res.get("video_path")
                caption = (
                    f"🎬 *{res.get('title', topic)}*\n\n"
                    f"{res.get('description', '')}\n\n"
                    f"Video hazır! Yayınlamak istiyor musun?"
                )
                keyboard = {
                    "inline_keyboard": [
                        [
                            {"text": "🚀 Onayla & Yayınla", "callback_data": "approve"},
                            {"text": "❌ İptal Et", "callback_data": "reject"},
                        ]
                    ]
                }
                if video_path and Path(video_path).is_file():
                    send_video(token, chat_id, video_path, caption=caption, reply_markup=keyboard)
                else:
                    send_message(token, chat_id, f"✅ Video üretildi: {res.get('title')}", reply_markup=keyboard)
            except Exception as exc:
                print(f"[telegram_bot] Doğal mesaj render hatası: {exc}", flush=True)
                send_message(token, chat_id, f"❌ Video üretilirken hata oluştu: {exc}")

        loop = asyncio.get_running_loop()
        loop.create_task(_run_bg())
        return

    # Greeting / Chat
    send_message(
        token,
        chat_id,
        "👋 Merhaba! Ben senin otonom video üretim asistanınım.\n\n"
        "Bana doğrudan doğal Türkçe konuşarak talimat verebilirsin:\n\n"
        "• *'Bana lüks saatler hakkında bir video yap'*\n"
        "• *'Hermès Birkin ile ilgili bir short patlat'*\n"
        "• *'Durum nedir?'*\n"
        "• *'Günün viral trend fikirlerini getir'*\n"
        "• *'Yayınla'* veya *'İptal'*",
    )


async def run_poller(
    token: str,
    chat_id: str,
    media_dir: str,
    offset_path: str,
    publish_fn: Callable[[dict], dict],
    cleanup_fn: Callable[[str], None],
    generate_fn: Callable[[str], dict] | None = None,
) -> None:
    """Telegram onay butonlarını ve doğal konuşma mesajlarını dinler."""
    try:
        await asyncio.to_thread(_call, token, "deleteWebhook")
    except Exception as exc:
        print(f"[telegram_bot] deleteWebhook uyarısı: {exc}", flush=True)

    offset = _load_offset(offset_path)
    print(f"[telegram_bot] Dinleyici başladı (offset={offset}).", flush=True)

    while True:
        try:
            response = await asyncio.to_thread(get_updates, token, offset, POLL_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            body = getattr(getattr(exc, "response", None), "text", "")
            print(f"[telegram_bot] getUpdates hatası: {exc} | Detay: {body}", flush=True)
            await asyncio.sleep(5)
            continue

        for update in response.get("result", []):
            offset = update["update_id"] + 1
            _save_offset(offset_path, offset)

            # 1. Buton tıklaması (callback_query)
            callback_query = update.get("callback_query")
            if callback_query:
                if str(callback_query["message"]["chat"]["id"]) != str(chat_id):
                    continue
                try:
                    answer_callback_query(token, callback_query["id"])
                except Exception as exc:
                    print(f"[telegram_bot] answerCallbackQuery hatası: {exc}", flush=True)

                try:
                    handle_callback(
                        callback_query["data"],
                        media_dir,
                        token,
                        chat_id,
                        publish_fn,
                        cleanup_fn,
                        generate_fn,
                    )
                except Exception as exc:
                    print(f"[telegram_bot] callback işleme hatası: {exc}", flush=True)
                    try:
                        send_message(token, chat_id, f"⚠️ İşlem hatası: {exc}")
                    except Exception:
                        pass
                continue

            # 2. Doğal Metin Mesajı
            message = update.get("message")
            if message:
                if str(message.get("chat", {}).get("id")) != str(chat_id):
                    continue
                text = message.get("text", "").strip()
                if text:
                    try:
                        await handle_natural_message(
                            text=text,
                            token=token,
                            chat_id=chat_id,
                            media_dir=media_dir,
                            publish_fn=publish_fn,
                            cleanup_fn=cleanup_fn,
                            generate_fn=generate_fn,
                        )
                    except Exception as exc:
                        print(f"[telegram_bot] handle_natural_message hatası: {exc}", flush=True)
                        try:
                            send_message(token, chat_id, f"⚠️ Bir hata oluştu: {exc}")
                        except Exception:
                            pass


