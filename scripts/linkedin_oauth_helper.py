#!/usr/bin/env python3
"""LinkedIn OAuth 2.0 yardımcısı: refresh token + author URN tek komutla.

ÖNKOŞUL (developer.linkedin.com üzerinde):
  1. App oluştur.
  2. "Products" bölümünde "Share on LinkedIn" ürününü EKLE (onay gerekebilir —
     onsuz post atamazsın; onay birkaç gün sürebilir, en erken başvur).
  3. Auth sekmesinde: OAuth 2.0 scopes -> openid, profile, email, w_member_social
  4. Redirect URLs'e ekle: http://localhost:8098/callback

Kullanım:
    python scripts/linkedin_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>
"""

import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

REDIRECT_URI = "http://localhost:8098/callback"
AUTH_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"
SCOPES = "openid profile email w_member_social"

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
            b"<h3>LinkedIn yetkilendirmesi tamam.</h3><p>Bu pencereyi kapatip "
            b"terminaldeki scripte donebilirsin.</p>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def main() -> None:
    if len(sys.argv) != 3:
        print("Kullanım: python scripts/linkedin_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>")
        sys.exit(1)

    client_id, client_secret = sys.argv[1], sys.argv[2]

    server = HTTPServer(("localhost", 8098), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    auth_url = (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={requests.utils.quote(SCOPES)}"
    )
    print("Tarayıcı açılıyor. LinkedIn hesabınla izin ver...")
    webbrowser.open(auth_url)
    print(f"Elle açmak istersen:\n{auth_url}\n")

    for _ in range(300):
        if captured.get("code") or captured.get("error"):
            break
        time.sleep(1)
    server.shutdown()

    if captured.get("error"):
        print(f"HATA: {captured['error']}")
        sys.exit(1)
    code = captured.get("code")
    if not code:
        print("2 dakika içinde yetkilendirme alınamadı.")
        sys.exit(1)

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=30,
    )
    if response.status_code != 200:
        print(f"HATA: {response.status_code} {response.text[:400]}")
        sys.exit(1)

    token_data = response.json()
    refresh_token = token_data.get("refresh_token", "")
    access_token = token_data.get("access_token", "")

    person_id = ""
    if access_token:
        try:
            userinfo = requests.get(
                "https://api.linkedin.com/v2/userinfo",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=30,
            )
            if userinfo.status_code == 200:
                person_id = userinfo.json().get("sub", "")
        except Exception:
            pass

    author_urn = f"urn:li:person:{person_id}" if person_id else ""

    print("\n=== BAŞARILI ===")
    print(f"LINKEDIN_REFRESH_TOKEN={refresh_token}")
    if author_urn:
        print(f"LINKEDIN_AUTHOR_URN={author_urn}")

    # Otomatik .env güncelleme
    import re
    from pathlib import Path
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        text = env_path.read_text(encoding="utf-8")
        text = re.sub(r"LINKEDIN_CLIENT_ID=.*", f"LINKEDIN_CLIENT_ID={client_id}", text)
        text = re.sub(r"LINKEDIN_CLIENT_SECRET=.*", f"LINKEDIN_CLIENT_SECRET={client_secret}", text)
        if refresh_token:
            text = re.sub(r"LINKEDIN_REFRESH_TOKEN=.*", f"LINKEDIN_REFRESH_TOKEN={refresh_token}", text)
        if author_urn:
            text = re.sub(r"LINKEDIN_AUTHOR_URN=.*", f"LINKEDIN_AUTHOR_URN={author_urn}", text)
        env_path.write_text(text, encoding="utf-8")
        print("[OK] .env dosyası otomatik güncellendi!")

    print("\nDocker servisini güncellemek için:")
    print("  docker compose up -d video-worker")


if __name__ == "__main__":
    main()
