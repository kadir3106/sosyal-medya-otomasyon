#!/usr/bin/env python3
"""Pinterest API v5 OAuth yardımcısı: refresh token + board ID tek komutla.

ÖNKOŞUL (developers.pinterest.com üzerinde):
  1. Bir App oluşturun.
  2. Redirect URIs kısmına ekleyin: http://localhost:8099/callback
  3. Gerekli Scopes: boards:read,pins:read,pins:write

Kullanım:
    python scripts/pinterest_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>
"""

import base64
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

import requests

REDIRECT_URI = "http://localhost:8099/callback"
AUTH_URL = "https://www.pinterest.com/oauth/"
TOKEN_URL = "https://api.pinterest.com/v5/oauth/token"
BOARDS_URL = "https://api.pinterest.com/v5/boards"
SCOPES = "boards:read,pins:read,pins:write"

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
            b"<h3>Pinterest yetkilendirmesi basarili!</h3><p>Bu pencereyi kapatip "
            b"terminale donebilirsiniz.</p>"
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
        print("Kullanim: python scripts/pinterest_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>")
        sys.exit(1)

    client_id, client_secret = sys.argv[1], sys.argv[2]

    server = HTTPServer(("localhost", 8099), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    auth_url = (
        f"{AUTH_URL}?client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&response_type=code"
        f"&scope={SCOPES}"
    )

    print("\n" + "=" * 60)
    print("📌 Pinterest OAuth 2.0 Kurulumu")
    print("=" * 60)
    print(f"Tarayici aciliyor...\nAcilmazsa linke tiklayin:\n{auth_url}\n")
    webbrowser.open(auth_url)

    print("Tarayicida 'Yetkilendir' butonuna basmaniz bekleniyor...")
    start = time.time()
    while "code" not in captured and "error" not in captured:
        if time.time() - start > 120:
            print("❌ Zaman asimi (2 dakika doldu).")
            sys.exit(1)
        time.sleep(1)

    if "error" in captured:
        print(f"❌ Pinterest hata verdi: {captured['error']}")
        sys.exit(1)

    auth_code = captured["code"]
    print("✅ Yetkilendirme kodu alindi. Token takasi yapiliyor...")

    auth_header = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    res = requests.post(
        TOKEN_URL,
        headers={
            "Authorization": f"Basic {auth_header}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": auth_code,
            "redirect_uri": REDIRECT_URI,
        },
        timeout=30,
    )

    if not res.ok:
        print(f"❌ Token takasi basarisiz ({res.status_code}): {res.text}")
        sys.exit(1)

    data = res.json()
    refresh_token = data.get("refresh_token")
    access_token = data.get("access_token")

    print("\n🎉 BASARILI!")
    print(f"PINTEREST_REFRESH_TOKEN={refresh_token}")

    # Mevcut panoları (Boards) çek
    print("\nMevcut panolariniz listeleniyor...")
    boards_res = requests.get(
        BOARDS_URL,
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if boards_res.ok:
        boards = boards_res.json().get("items", [])
        if boards:
            print("Bulunan Panolar:")
            for b in boards:
                print(f"  - {b.get('name')}: ID -> {b.get('id')}")
            first_board = boards[0].get("id")
            print(f"\nOnerilen .env degeri: PINTEREST_BOARD_ID={first_board}")
        else:
            print("⚠️ Hesabinizda hic pano bulunamadi. Pinterest'te bir pano olusturup ID'sini ekleyin.")

    print("\n.env dosyaniza su satirlari ekleyin:")
    print(f"PINTEREST_CLIENT_ID={client_id}")
    print(f"PINTEREST_CLIENT_SECRET={client_secret}")
    print(f"PINTEREST_REFRESH_TOKEN={refresh_token}")


if __name__ == "__main__":
    main()
