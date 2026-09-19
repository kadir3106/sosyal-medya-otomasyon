#!/usr/bin/env python3
"""Telegram bot chat_id'sini getUpdates ile bulur.

Kullanım:
    1. Telegram'da botuna /start mesajı gönder.
    2. python scripts/get_chat_id.py
    3. Çıkan sayıyı .env içindeki TELEGRAM_CHAT_ID alanına yaz.
    4. docker compose restart n8n
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_token() -> str:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        print("HATA: .env dosyası yok.")
        sys.exit(1)
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            value = line.split("=", 1)[1].strip()
            if value:
                return value
            print("HATA: TELEGRAM_BOT_TOKEN .env içinde boş.")
            sys.exit(1)
    print("HATA: TELEGRAM_BOT_TOKEN .env içinde bulunamadı.")
    sys.exit(1)


def main() -> None:
    token = load_token()
    print("Bot'a /start mesajı gönderdiysen bekleniyor (en fazla 60 sn)...")
    for _ in range(30):
        url = f"https://api.telegram.org/bot{token}/getUpdates"
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = json.load(resp)
        except Exception as exc:
            print(f"HATA: {exc}")
            sys.exit(1)

        chat_ids = set()
        for update in data.get("result", []):
            for key in ("message", "edited_message"):
                obj = update.get(key)
                if obj and "chat" in obj:
                    chat_ids.add(obj["chat"]["id"])
            callback = update.get("callback_query")
            if callback and callback.get("message", {}).get("chat", {}).get("id"):
                chat_ids.add(callback["message"]["chat"]["id"])

        if chat_ids:
            print("\nCHAT_ID bulundu:")
            for cid in sorted(chat_ids):
                print(f"  {cid}")
            print("\nBunu .env dosyasındaki TELEGRAM_CHAT_ID alanına yaz, sonra:")
            print("  docker compose restart n8n")
            return
        time.sleep(2)

    print("60 sn içinde güncelleme bulunamadı. Bot'a /start gönderip tekrar dene.")


if __name__ == "__main__":
    main()
