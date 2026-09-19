#!/usr/bin/env python3
"""YouTube OAuth yardımcısı: refresh token'ı tek komutla al.

Kullanım:
    python scripts/youtube_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>

1. Tarayıcıda Google izin ekranı açılır, onay ver.
2. Gösterilen authorization code'u buraya yapıştır.
3. Script refresh token'ı yazdırır -> .env içindeki YOUTUBE_REFRESH_TOKEN'a yaz.

Not: OAuth consent screen "Testing" modundaysa refresh token 7 GÜN sonra
geçersiz olur; Google Cloud'da app'i doğrulamaya (verification) gönder ve
"Publishing" yapana kadar haftada bir bu scripti tekrar çalıştır.
"""

import os
import re
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

SCOPES = (
    "https://www.googleapis.com/auth/youtube.upload "
    "https://www.googleapis.com/auth/youtube.readonly "
    "https://www.googleapis.com/auth/youtube.force-ssl "
    "https://www.googleapis.com/auth/youtube "
    "https://www.googleapis.com/auth/userinfo.email"
)
REDIRECT_URI = "http://127.0.0.1:8098"
TOKEN_URL = "https://oauth2.googleapis.com/token"

captured = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if "favicon.ico" in self.path:
            self.send_response(204)
            self.end_headers()
            return
        query = parse_qs(urlparse(self.path).query)
        code = query.get("code", [""])[0]
        error = query.get("error", [""])[0]
        if code:
            captured["code"] = code
        if error:
            captured["error"] = error
        body = (
            b"<html><body style='font-family:sans-serif;text-align:center;padding:50px;'>"
            b"<h2 style='color:#16a34a;'>&#10004; YouTube Yetkilendirmesi Basarili!</h2>"
            b"<p>Token alindi ve .env dosyaniza kaydediliyor. Bu sekmeyi kapatabilirsiniz.</p>"
            b"</body></html>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def save_to_env(client_id: str, client_secret: str, refresh_token: str) -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    text = env_path.read_text(encoding="utf-8")
    text = re.sub(r"YOUTUBE_CLIENT_ID=.*", f"YOUTUBE_CLIENT_ID={client_id}", text)
    text = re.sub(r"YOUTUBE_CLIENT_SECRET=.*", f"YOUTUBE_CLIENT_SECRET={client_secret}", text)
    text = re.sub(r"YOUTUBE_REFRESH_TOKEN=.*", f"YOUTUBE_REFRESH_TOKEN={refresh_token}", text)
    env_path.write_text(text, encoding="utf-8")
    print("\n[OK] .env dosyasi otomatik guncellendi!")


def main() -> None:
    client_id = sys.argv[1] if len(sys.argv) > 1 else ""
    client_secret = sys.argv[2] if len(sys.argv) > 2 else ""

    if not client_id or not client_secret:
        env_path = Path(__file__).resolve().parent.parent / ".env"
        if env_path.exists():
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if line.startswith("YOUTUBE_CLIENT_ID="):
                    client_id = line.split("=", 1)[1].strip().strip('"').strip("'")
                elif line.startswith("YOUTUBE_CLIENT_SECRET="):
                    client_secret = line.split("=", 1)[1].strip().strip('"').strip("'")

    if not client_id or not client_secret:
        print("Kullanim: python scripts/youtube_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>")
        sys.exit(1)

    server = None
    port = 8090
    for p in [8090, 8080, 8765, 8888, 8098]:
        try:
            server = HTTPServer(("127.0.0.1", p), _Handler)
            port = p
            threading.Thread(target=server.serve_forever, daemon=True).start()
            print(f"Port {port} yerel dinleyici baslatildi.")
            break
        except Exception:
            continue

    redirect_uri = f"http://127.0.0.1:{port}"

    auth_url = (
        "https://accounts.google.com/o/oauth2/v2/auth"
        f"?client_id={client_id}"
        f"&redirect_uri={requests.utils.quote(redirect_uri, safe='')}"
        "&response_type=code"
        "&access_type=offline"
        "&prompt=select_account consent"
        f"&scope={requests.utils.quote(SCOPES)}"
    )
    print("Tarayici aciliyor. Google hesabinizla izin verin...")
    webbrowser.open(auth_url)
    print(f"Yetkilendirme linki:\n{auth_url}\n")
    print("Yetkilendirme bekleniyor...")

    def _manual_input():
        try:
            val = input("\n(Opsiyonel) Tarayicidaki yonlendirilen adres cubugundaki linki buraya yapistirabilirsiniz: ").strip()
            if "code=" in val:
                query = parse_qs(urlparse(val).query)
                captured["code"] = query.get("code", [""])[0]
            elif val:
                captured["code"] = val
        except Exception:
            pass

    threading.Thread(target=_manual_input, daemon=True).start()

    for _ in range(300):
        if captured.get("code") or captured.get("error"):
            break
        time.sleep(1)

    if captured.get("error"):
        print(f"\nHATA: {captured['error']}")
        sys.exit(1)

    code = captured.get("code")
    if not code:
        print("\nZaman asimi: 5 dakika icinde onay gelmedi.")
        sys.exit(1)

    print("\n[OK] Onay kodu alindi. Google'dan refresh token isteniyor...")
    response = requests.post(
        TOKEN_URL,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=30,
    )
    if response.status_code != 200:
        print(f"HATA: {response.status_code} {response.text}")
        sys.exit(1)

    token_data = response.json()
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        print(f"UYARI: Google refresh token dondurmedi (hesap zaten bagli olabilir): {token_data}")
        sys.exit(1)

    print("\n=== BASARILI ===")
    print(f"YOUTUBE_REFRESH_TOKEN={refresh_token}")
    save_to_env(client_id, client_secret, refresh_token)
    print("Docker servisini guncellemek icin:")
    print("  docker compose up -d video-worker")


if __name__ == "__main__":
    main()
