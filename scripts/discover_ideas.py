#!/usr/bin/env python3
"""Gündemdeki trendleri tarar, 3 viral kurgu konsepti üretir ve Telegram'a gönderir."""

import json
import os
import sys
from pathlib import Path

# UTF-8 stdout
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# Add video-worker to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

import requests
from app.config import config
from app.trends import fetch_trends
from app.pitch_gen import generate_pitches
from app.telegram_bot import send_pitches_message

URL = "http://localhost:8000/discover-ideas"


def run_direct():
    """Server ayakta değilse doğrudan Python fonksiyonlarıyla çalışır."""
    lang = config.VIDEO_LANG or "en"
    geo = "TR" if lang == "tr" else "US"
    trends = fetch_trends(geo=geo)
    pitches = generate_pitches(trends, api_key=config.OPENROUTER_API_KEY, lang=lang)

    media_dir = Path(config.MEDIA_DIR)
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "pending_pitches.json").write_text(
        json.dumps(pitches, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    if config.TELEGRAM_BOT_TOKEN and config.TELEGRAM_CHAT_ID:
        send_pitches_message(config.TELEGRAM_BOT_TOKEN, config.TELEGRAM_CHAT_ID, pitches)
        print("📱 Fikirler Telegram botuna interaktif butonlarla gönderildi!")
    else:
        print("⚠️ Telegram token veya chat ID bulunamadı.")

    return pitches


def main():
    print("🔍 Gündem trendleri taranıyor ve 3 viral konsept üretiliyor...")
    pitches = None
    try:
        resp = requests.post(URL, timeout=10)
        if resp.status_code == 200:
            pitches = resp.json().get("pitches", [])
            print("✅ Sunucu üzerinden Telegram'a gönderildi!")
    except Exception:
        # Sunucu çalışmıyorsa direkt çalıştır
        print("⚡ Doğrudan motor çalıştırılıyor...")
        pitches = run_direct()

    if pitches:
        print("-" * 55)
        for p in pitches:
            cat = p.get("category_label", p.get("category"))
            print(f"[{cat}] {p.get('title')}")
            print(f"   Kanca: \"{p.get('hook')}\"")
        print("-" * 55)
        print("📲 Telegram'ına bakabilir, istediğin fikrin butonuna basabilirsin!")


if __name__ == "__main__":
    main()
