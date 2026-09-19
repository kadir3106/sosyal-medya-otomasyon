#!/usr/bin/env python3
"""X (Twitter) OAuth 2.0 PKCE yardımcısı: refresh token'ı tek komutla al.

ÖNKOŞUL (developer.x.com üzerinde):
  1. Proje oluştur, X API v2'yi seç (ücretsiz katman yeterli).
  2. App oluştur -> "User authentication settings" ayarla:
     - App permissions: Read and write
     - Type of App: Web App
     - Callback URI: http://localhost:8098/callback
     - Website URL: herhangi bir şey (örn. http://localhost)

Kullanım:
    python scripts/x_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>

Script kendi kanalından tweet atma yetkisi olan refresh token üretir
(Bearer Token POST atamaz — bu yüzden bu akış gerekli).
"""

import base64
import hashlib
import os
import re
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

REDIRECT_URI = "http://localhost:8098/callback"
AUTH_URL = "https://twitter.com/i/oauth2/authorize"
TOKEN_URL = "https://api.x.com/2/oauth2/token"
SCOPES = "tweet.read tweet.write users.read offline.access media.write"
CODE_VERIFIER = "sosyal_medya_otomasyon_twitter_oauth2_pkce_fixed_code_verifier_26"

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
            b"<h3>X yetkilendirmesi tamam.</h3><p>Bu pencereyi kapatip "
            b"terminaldeki scripte donebilirsin.</p>"
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


import urllib.parse


def _extract_code(val: str) -> str:
    val = val.strip()
    match = re.search(r"code=([^&\s]+)", val)
    if match:
        return urllib.parse.unquote(match.group(1))
    return val


def _wait_for_manual_input():
    try:
        val = input(
            "\n(Tarayici baglanti reddedildi dediyse, adres cubugundaki linki buraya yapistirip Enter'a basin):\n> "
        ).strip()
        if val:
            extracted = _extract_code(val)
            if extracted:
                captured["code"] = extracted
    except Exception:
        pass


def _get_env_creds():
    env_path = Path(__file__).resolve().parent.parent / ".env"
    cid, csec = "", ""
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("X_CLIENT_ID="):
                cid = line.split("=", 1)[1].strip()
            elif line.startswith("X_CLIENT_SECRET="):
                csec = line.split("=", 1)[1].strip()
    return cid, csec


def main() -> None:
    if len(sys.argv) == 3:
        client_id, client_secret = sys.argv[1], sys.argv[2]
    else:
        client_id, client_secret = _get_env_creds()

    if not client_id or not client_secret:
        print("HATA: Client ID ve Client Secret bulunamadı.")
        print("Kullanim: python scripts/x_oauth_helper.py <CLIENT_ID> <CLIENT_SECRET>")
        sys.exit(1)

    code_verifier = CODE_VERIFIER
    code_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest())
        .decode()
        .rstrip("=")
    )
    state = secrets.token_urlsafe(16)

    try:
        server = HTTPServer(("0.0.0.0", 8098), _Handler)
        def _serve():
            try:
                server.serve_forever()
            except Exception:
                pass
        threading.Thread(target=_serve, daemon=True).start()
        print("[1] Port 8098 yerel dinleyici baslatildi.")
    except Exception as e:
        print(f"Port 8098 dinlenemedi ({e}). Elle link yapistirma modu aktif.")
        server = None

    auth_url = (
        f"{AUTH_URL}?response_type=code"
        f"&client_id={client_id}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&scope={requests.utils.quote(SCOPES)}"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        "&code_challenge_method=S256"
    )
    print("[2] Tarayici aciliyor. X hesabinizla 'Authorize app' butonuna basin...")
    webbrowser.open(auth_url)
    print(f"Link elle acmak isterseniz:\n{auth_url}\n")

    threading.Thread(target=_wait_for_manual_input, daemon=True).start()

    print("[3] Yetki bekleniyor (300 saniye)...")
    for _ in range(300):
        if captured.get("code") or captured.get("error"):
            break
        time.sleep(1)

    if server:
        try:
            server.shutdown()
        except Exception:
            pass

    if captured.get("error"):
        print(f"\nHATA: {captured['error']}")
        sys.exit(1)

    code = captured.get("code")
    if not code:
        print("\nZaman asimi: Yetkilendirme kodu alinamadi.")
        sys.exit(1)

    print("\n[4] Kod alindi! X'ten refresh token isteniyor...")

    response = requests.post(
        TOKEN_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        auth=(client_id, client_secret),
        data={
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
    refresh_token = token_data.get('refresh_token')
    print("\n=== BAŞARILI ===")
    print(f"X_REFRESH_TOKEN={refresh_token}")

    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists() and refresh_token:
        text = env_path.read_text(encoding="utf-8")
        text = re.sub(r"X_CLIENT_ID=.*", f"X_CLIENT_ID={client_id}", text)
        text = re.sub(r"X_CLIENT_SECRET=.*", f"X_CLIENT_SECRET={client_secret}", text)
        text = re.sub(r"X_REFRESH_TOKEN=.*", f"X_REFRESH_TOKEN={refresh_token}", text)
        env_path.write_text(text, encoding="utf-8")
        print("[OK] .env dosyası otomatik güncellendi!")

    print("\nDocker servisini güncellemek için:")
    print("  docker compose up -d video-worker")


if __name__ == "__main__":
    main()
