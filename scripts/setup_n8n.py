#!/usr/bin/env python3
"""n8n kurulum scripti: owner hesabı, Telegram credential'ı ve 3 workflow'u kurar.

Kullanım (proje kökünden):
    python scripts/setup_n8n.py

Gereksinim: docker compose up -d çalışmış ve n8n http://localhost:5678 adresinde
ayakta olmalı. TELEGRAM_BOT_TOKEN .env içinde doluysa credential otomatik
oluşturulur ve workflow'lar aktive edilir.
"""

import json
import os
import secrets
import sys
import time
from pathlib import Path

import requests

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
N8N_URL = os.environ.get("N8N_URL", "http://localhost:5678")
API = f"{N8N_URL}/api/v1"
WORKFLOWS_DIR = ROOT / "n8n-workflows"
CRED_PLACEHOLDER = "__TELEGRAM_CRED_ID__"
CRED_NAME = "Telegram - Otomasyon Bot"


def load_env() -> dict:
    env = {}
    env_path = ROOT / ".env"
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def wait_health(timeout: int = 120) -> None:
    for _ in range(timeout):
        try:
            if requests.get(f"{N8N_URL}/healthz", timeout=2).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(2)
    raise RuntimeError("n8n healthz yanıt vermedi. 'docker compose up -d' çalıştırdın mı?")


def ensure_auth(session: requests.Session, email: str, password: str) -> None:
    r = session.get(f"{API}/workflows")
    if r.status_code == 200:
        print("[n8n] API açık, owner kurulumu gerekmedi.")
        return

    # n8n >= 2.x: kurulum ve giriş /rest/ altında
    setup_resp = session.post(
        f"{N8N_URL}/rest/owner/setup",
        json={
            "email": email,
            "firstName": "Admin",
            "lastName": "Admin",
            "password": password,
        },
    )
    if setup_resp.status_code in (200, 201):
        print("[n8n] Owner hesabı oluşturuldu.")
    elif setup_resp.status_code == 400 and "already" in setup_resp.text.lower():
        print("[n8n] Owner zaten kurulu, giriş yapılıyor.")
    elif setup_resp.status_code == 404:
        # Eski sürüm fallback'i
        setup_resp = session.post(
            f"{API}/owner/setup",
            json={
                "email": email,
                "firstName": "Admin",
                "lastName": "Admin",
                "password": password,
            },
        )
        if setup_resp.status_code not in (200, 201):
            print(f"[n8n] owner/setup beklenmedik yanıt: {setup_resp.status_code}")
            print(setup_resp.text[:400])
    else:
        print(f"[n8n] owner/setup beklenmedik yanıt: {setup_resp.status_code}")
        print(setup_resp.text[:400])

    login_resp = session.post(
        f"{N8N_URL}/rest/login",
        json={"emailOrLdapLoginId": email, "password": password},
    )
    if login_resp.status_code != 200:
        raise RuntimeError(
            f"n8n login başarısız: {login_resp.status_code} {login_resp.text[:300]}"
        )
    print("[n8n] Giriş yapıldı.")


def ensure_telegram_credential(
    session: requests.Session, token: str
) -> str | None:
    creds = session.get(f"{API}/credentials").json().get("data", [])
    for cred in creds:
        if cred.get("name") == CRED_NAME:
            print(f"[n8n] Telegram credential zaten var (id={cred['id']}).")
            return cred["id"]

    if not token:
        print("[n8n] TELEGRAM_BOT_TOKEN .env içinde boş — credential atlanıyor.")
        return None

    resp = session.post(
        f"{API}/credentials",
        json={
            "name": CRED_NAME,
            "type": "telegramApi",
            "data": {"accessToken": token},
        },
    )
    if resp.status_code not in (200, 201):
        print(f"[n8n] Credential oluşturulamadı: {resp.status_code} {resp.text[:300]}")
        return None
    cred_id = resp.json()["id"]
    print(f"[n8n] Telegram credential oluşturuldu (id={cred_id}).")
    return cred_id


def import_workflow(
    session: requests.Session, path: Path, cred_id: str | None
) -> dict | None:
    data = json.loads(path.read_text(encoding="utf-8"))
    data.pop("active", None)  # import/update body'sinde active read-only

    needs_cred = CRED_PLACEHOLDER in json.dumps(data)
    if needs_cred and cred_id:
        data = json.loads(json.dumps(data).replace(CRED_PLACEHOLDER, cred_id))
    elif needs_cred and not cred_id:
        for node in data.get("nodes", []):
            node.pop("credentials", None)

    # Aynı isimde workflow varsa güncelle (idempotent kurulum)
    existing = session.get(f"{API}/workflows", params={"limit": 200})
    if existing.status_code != 200:
        print(f"  [hata] workflow listesi alınamadı: {existing.status_code}")
        return None
    target = next(
        (w for w in existing.json().get("data", []) if w.get("name") == data["name"]),
        None,
    )
    if target:
        resp = session.put(f"{API}/workflows/{target['id']}", json=data)
        action = "güncellendi"
        wf_id = target["id"]
    else:
        resp = session.post(f"{API}/workflows", json=data)
        action = "import edildi"
        wf_id = resp.json().get("id") if resp.status_code in (200, 201) else None

    if resp.status_code not in (200, 201):
        print(f"  [hata] {data['name']} {action} olamadı: {resp.status_code} {resp.text[:400]}")
        return None
    print(f"  [ok] {data['name']} {action} (id={wf_id}).")

    if needs_cred and not cred_id:
        print(f"  [bilgi] {data['name']}: credential yok — aktifleştirilmedi. Token ekleyip scripti tekrar çalıştır.")
        return None

    act_resp = session.patch(f"{API}/workflows/{wf_id}", json={"active": True})
    if act_resp.status_code not in (200, 201):
        act_resp = session.post(f"{API}/workflows/{wf_id}/activate")
    if act_resp.status_code in (200, 201):
        print(f"  [ok] {data['name']} AKTİF.")
    else:
        print(f"  [uyarı] {data['name']} aktive edilemedi: {act_resp.status_code} {act_resp.text[:300]}")
    return resp.json()


def main() -> None:
    env = load_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = env.get("TELEGRAM_CHAT_ID", "")
    email = env.get("N8N_EMAIL", "admin@local.dev")
    password = env.get("N8N_PASSWORD")
    if not password:
        # Sabit varsayılan şifre yok — ilk kurulumda rastgele üretilir
        # ve .env'e kalıcı olarak kaydedilir (sonraki çalıştırmalarda aynısı kullanılır).
        password = secrets.token_urlsafe(12)
        env_path = ROOT / ".env"
        with env_path.open("a", encoding="utf-8") as fh:
            fh.write(f"N8N_PASSWORD={password}\n")
        print(f"[n8n] Rastgele admin şifresi üretildi ve .env'e kaydedildi.")

    print("== n8n kurulumu başlıyor ==")
    if not chat_id:
        print("[uyarı] TELEGRAM_CHAT_ID boş — workflow'lar aktif olsa da mesaj gidemez.")
        print("        Önce bot'a /start gönder, sonra: python scripts/get_chat_id.py")

    wait_health()
    session = requests.Session()
    ensure_auth(session, email, password)
    cred_id = ensure_telegram_credential(session, token)

    print("[n8n] Workflow'lar import ediliyor...")
    for wf_file in sorted(WORKFLOWS_DIR.glob("*.json")):
        import_workflow(session, wf_file, cred_id)

    print("\n== Tamam ==")
    print(f"n8n arayüzü: {N8N_URL}  (email: {email}, şifre: {password})")
    print("(Şifre .env içindeki N8N_PASSWORD değeridir — başka birine gösterme.)")
    if not token:
        print("Hatırlatma: TELEGRAM_BOT_TOKEN'i .env'e ekleyip bu scripti tekrar çalıştır.")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"HATA: {exc}")
        sys.exit(1)
