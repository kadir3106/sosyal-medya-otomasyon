#!/usr/bin/env python3
"""TikTok Content Posting API OAuth 2.0 yardımcısı: refresh token'ı tek komutla al.

ÖNKOŞUL (developers.tiktok.com üzerinde):
  1. App oluştur, Platform: Web seç.
  2. "Content Posting API" ürününü ekle, video.publish + video.upload scope'larını iste.
  3. Redirect URI: http://localhost:8098/callback

Kullanım:
    python scripts/tiktok_oauth_helper.py <CLIENT_KEY> <CLIENT_SECRET>

TikTok'un diğer platformlardan farkı: refresh token .env'e değil, video-worker
container'ının /data/tiktok-token/token.json dosyasına yazılıyor — çünkü kod
onu her kullanımda otomatik rotasyona uğratıyor (bkz. app/publishers/tiktok.py).
Bu script token'ı alıp DOĞRUDAN çalışan container'a yazar; video-worker'ın
`docker compose up -d` ile ayakta olması gerekir.
"""

import json
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

REDIRECT_URI = "https://localhost:8098/callback"
AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
SCOPES = "video.publish,video.upload"

captured = {}


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        query = parse_qs(urlparse(self.path).query)
        captured["code"] = query.get("code", [""])[0]
        captured["error"] = query.get("error", [""])[0]
        body = (
            b"<h3>TikTok yetkilendirmesi tamam.</h3><p>Bu pencereyi kapatip "
            b"terminaldeki scripte donebilirsin.</p>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def _wait_for_manual_input():
    try:
        val = input(
            "\n(Tarayıcıda onay verdikten sonra adres çubuğundaki tam URL'yi veya ?code= kodunu buraya yapıştırabilirsiniz):\n> "
        ).strip()
        if val:
            if "code=" in val:
                query = parse_qs(urlparse(val).query or val)
                captured["code"] = query.get("code", [val])[0]
            else:
                captured["code"] = val
    except Exception:
        pass


def main() -> None:
    client_key = sys.argv[1] if len(sys.argv) > 1 else ""
    client_secret = sys.argv[2] if len(sys.argv) > 2 else ""

    if not client_key or not client_secret:
        # .env dosyasından dene
        try:
            sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))
            from app.config import config
            client_key = config.TIKTOK_CLIENT_KEY
            client_secret = config.TIKTOK_CLIENT_SECRET
        except Exception as e:
            print(f"Config okuma hatası: {e}")

    if not client_key or not client_secret:
        print("Kullanım: python scripts/tiktok_oauth_helper.py <CLIENT_KEY> <CLIENT_SECRET>")
        print("veya .env dosyasında TIKTOK_CLIENT_KEY ve TIKTOK_CLIENT_SECRET tanımlayın.")
        sys.exit(1)

    print(f"TikTok Client Key: {client_key}")

    try:
        server = HTTPServer(("localhost", 8098), _Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    except Exception:
        server = None

    # TikTok v2 zorunlu PKCE üretimi
    import base64
    import hashlib
    import secrets

    code_verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(code_verifier.encode("utf-8")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")

    auth_url = (
        f"{AUTH_URL}?client_key={client_key}"
        f"&scope={requests.utils.quote(SCOPES)}"
        f"&response_type=code"
        f"&redirect_uri={requests.utils.quote(REDIRECT_URI, safe='')}"
        f"&state=setup"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
    )
    print("Tarayıcı açılıyor. TikTok hesabınla yetkilendir...")
    webbrowser.open(auth_url)
    print(f"Elle açmak istersen:\n{auth_url}\n")

    threading.Thread(target=_wait_for_manual_input, daemon=True).start()

    for _ in range(180):
        if "code" in captured or "error" in captured:
            break
        time.sleep(1)
    if server:
        server.shutdown()

    if captured.get("error"):
        print(f"HATA: {captured['error']}")
        sys.exit(1)
    code = captured.get("code")
    if not code:
        print("3 dakika içinde yetkilendirme alınamadı.")
        sys.exit(1)

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        timeout=30,
    )
    if response.status_code != 200:
        print(f"HATA: {response.status_code} {response.text[:400]}")
        sys.exit(1)

    token_data = response.json()
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        print(f"HATA: yanıtta refresh_token yok: {response.text[:400]}")
        sys.exit(1)

    print("\n=== BAŞARILI ===")
    print(f"Refresh token alındı (ilk 10 karakter): {refresh_token[:10]}...")

    token_json = json.dumps({"refresh_token": refresh_token}, indent=2)
    
    # Yerel dosyalara kaydet
    root_dir = Path(__file__).resolve().parent.parent
    local_paths = [
        root_dir / ".tiktok_token.json",
        root_dir / "video-output" / "tiktok_token.json",
    ]
    for lp in local_paths:
        try:
            lp.parent.mkdir(parents=True, exist_ok=True)
            lp.write_text(token_json, encoding="utf-8")
            print(f"Token yerel dosyaya kaydedildi: {lp}")
        except Exception as e:
            print(f"Dosyaya yazılamadı: {lp}: {e}")

    # Docker varsa container içine de yazmayı dene
    try:
        write_result = subprocess.run(
            [
                "docker", "compose", "exec", "-T", "video-worker",
                "sh", "-c", "mkdir -p /data/tiktok-token && cat > /data/tiktok-token/token.json",
            ],
            input=token_json,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if write_result.returncode == 0:
            print("token.json video-worker container'ına da yazıldı.")
    except Exception:
        pass


if __name__ == "__main__":
    main()
