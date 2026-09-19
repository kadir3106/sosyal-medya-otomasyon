# Sosyal Medya Video Otomasyon Sistemi Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Günde 1 faceless kısa video (script→TTS→stok klip→FFmpeg render) üreten, Telegram üzerinden onay alan, onaylanınca YouTube Shorts + TikTok + Instagram Reels + Facebook Reels'e otomatik yükleyen ve haftalık performans raporu çıkaran, tamamen ücretsiz araçlarla çalışan bir otomasyon sistemi kurmak.

**Architecture:** Docker Compose ile 3 servis: `n8n` (zamanlama + Telegram onay arayüzü + orkestrasyon), `video-worker` (Python/FastAPI — script/TTS/render/platform-upload gibi tüm karmaşık ve test edilebilir mantık burada), `cloudflared` (Instagram'ın gerektirdiği geçici public video URL'i için Cloudflare Quick Tunnel, hesap gerektirmez). n8n ve video-worker `shared-media` adlı ortak bir Docker volume paylaşır.

**Tech Stack:** n8n (self-hosted), Python 3.12 + FastAPI + edge-tts + FFmpeg, Docker Compose, Cloudflare Tunnel (cloudflared), OpenRouter API, Pexels API, YouTube Data API v3, TikTok Content Posting API, Meta Graph API.

**Spec:** [docs/superpowers/specs/2026-09-03-sosyal-medya-video-otomasyon-design.md](../specs/2026-09-03-sosyal-medya-video-otomasyon-design.md)

## Deviations from spec (implementation-detail refinements, same approved architecture)

1. **Platform upload mantığı n8n Code node'ları yerine video-worker'da Python olarak yazılıyor.** Spec'in kendi gerekçesi ("karmaşık prosedürel mantık n8n'de test edilemez, video-worker'a taşınıyor") burada da geçerli: YouTube resumable upload, TikTok'un 24 saatte bir yenilenmesi gereken (ve her yenilemede rotasyona uğrayan) refresh token'ı, Meta'nın Instagram/Facebook için farklı upload protokolleri — hepsi pytest ile mock'lanarak test edilebilir Python kodu olarak yazılıyor. n8n hâlâ zamanlama + Telegram onayı + orkestrasyonu yapıyor, sadece HTTP çağrılarını tek tek n8n node'ları yerine video-worker'ın `/publish` endpoint'i üstleniyor. Container sayısı, maliyet, mimari prensip aynı kalıyor.
2. **Instagram Reels için `cloudflared` (Cloudflare Quick Tunnel) 3. servis olarak eklendi.** Instagram'ın Content Publishing API'si (Facebook Reels'in aksine) binary upload kabul etmiyor, sadece herkese açık bir `video_url` üzerinden video çekiyor. Quick Tunnel hesap/domain gerektirmez, `video-worker`'ın `/media` rotasını geçici ve rastgele bir `trycloudflare.com` adresinden dışarı açar.

## Global Constraints

- Dil: İngilizce (script, başlık, açıklama)
- Format: dikey 9:16, 1080x1920, faceless slideshow (AI script + TTS + stok klip + gömülü altyazı) — text-to-video AI modeli KULLANILMAZ
- Günde 1 video, aynı dosya 4 platforma paylaşılır (platform başına ayrı render yok)
- Tek aşamalı Telegram onayı — sadece final video onaya sunulur
- Bütçe: sıfıra yakın, sadece ücretsiz katmanlar
- TikTok: app audit onaylanana kadar `privacy_level=SELF_ONLY` (private) zorunlu
- Analiz: sadece performans raporu, otomatik konu seçimini etkilemiyor (v1)
- Kapsam dışı (v1): AI geri bildirim döngüsü, iki aşamalı onay, platform başına farklı format, X/Twitter

---

## Task 1: Proje iskeleti — Docker Compose + FastAPI skeleton

**Files:**
- Create: `docker-compose.yml`
- Create: `.env.example`
- Create: `.gitignore`
- Create: `video-worker/Dockerfile`
- Create: `video-worker/requirements.txt`
- Create: `video-worker/app/__init__.py`
- Create: `video-worker/app/main.py`
- Test: `video-worker/tests/test_main.py`
- Create: `video-worker/tests/__init__.py`
- Create: `README.md`

**Interfaces:**
- Produces: `app.main:app` (FastAPI instance) — sonraki tüm task'lar buraya route ekleyecek. `GET /health` → `{"status": "ok"}`.

- [ ] **Step 1: requirements.txt ve Dockerfile'ı yaz**

`video-worker/requirements.txt`:
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
requests==2.32.3
edge-tts==6.1.19
pytest==8.3.3
pytest-asyncio==0.24.0
httpx==0.27.2
```

`video-worker/Dockerfile`:
```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY tests ./tests

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Boş app skeleton'ı yaz (route yok, test'in fail etmesi için)**

`video-worker/app/__init__.py`: (boş dosya)

`video-worker/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="video-worker")
```

`video-worker/tests/__init__.py`: (boş dosya)

- [ ] **Step 3: Failing test'i yaz**

`video-worker/tests/test_main.py`:
```python
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_endpoint_returns_ok():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: docker-compose.yml'i yaz (n8n + video-worker + cloudflared + volume'ler)**

`docker-compose.yml`:
```yaml
services:
  n8n:
    image: n8nio/n8n:latest
    restart: unless-stopped
    ports:
      - "5678:5678"
    environment:
      - N8N_SECURE_COOKIE=false
      - GENERIC_TIMEZONE=Europe/Istanbul
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - VIDEO_WORKER_URL=http://video-worker:8000
    volumes:
      - n8n-data:/home/node/.n8n
      - shared-media:/data/media
    depends_on:
      - video-worker

  video-worker:
    build: ./video-worker
    restart: unless-stopped
    ports:
      - "8000:8000"
    environment:
      - MEDIA_DIR=/data/media
      - TUNNEL_LOG_PATH=/tunnel-logs/tunnel.log
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - PEXELS_API_KEY=${PEXELS_API_KEY}
      - YOUTUBE_CLIENT_ID=${YOUTUBE_CLIENT_ID}
      - YOUTUBE_CLIENT_SECRET=${YOUTUBE_CLIENT_SECRET}
      - YOUTUBE_REFRESH_TOKEN=${YOUTUBE_REFRESH_TOKEN}
      - TIKTOK_CLIENT_KEY=${TIKTOK_CLIENT_KEY}
      - TIKTOK_CLIENT_SECRET=${TIKTOK_CLIENT_SECRET}
      - TIKTOK_AUDITED=${TIKTOK_AUDITED}
      - META_IG_USER_ID=${META_IG_USER_ID}
      - META_PAGE_ID=${META_PAGE_ID}
      - META_PAGE_ACCESS_TOKEN=${META_PAGE_ACCESS_TOKEN}
    volumes:
      - shared-media:/data/media
      - tunnel-logs:/tunnel-logs
      - tiktok-token:/data/tiktok-token

  cloudflared:
    image: cloudflare/cloudflared:latest
    restart: unless-stopped
    command: tunnel --url http://video-worker:8000 --logfile /logs/tunnel.log
    volumes:
      - tunnel-logs:/logs
    depends_on:
      - video-worker

volumes:
  n8n-data:
  shared-media:
  tunnel-logs:
  tiktok-token:
```

`.env.example`:
```
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
OPENROUTER_API_KEY=
PEXELS_API_KEY=
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REFRESH_TOKEN=
TIKTOK_CLIENT_KEY=
TIKTOK_CLIENT_SECRET=
TIKTOK_AUDITED=false
META_IG_USER_ID=
META_PAGE_ID=
META_PAGE_ACCESS_TOKEN=
```

`.gitignore`:
```
.env
__pycache__/
*.pyc
.pytest_cache/
```

`README.md`:
```markdown
# Sosyal Medya Video Otomasyon Sistemi

Kurulum ve mimari için bkz. `docs/superpowers/specs/2026-09-03-sosyal-medya-video-otomasyon-design.md`.
Uygulama planı: `docs/superpowers/plans/2026-09-03-sosyal-medya-video-otomasyon.md`.

## Geliştirme

Testleri çalıştırmak için:
\`\`\`bash
docker compose build video-worker
docker compose run --rm video-worker pytest tests/ -v
\`\`\`

Tüm sistemi ayağa kaldırmak için `.env` dosyasını `.env.example`'dan kopyalayıp doldurun, sonra:
\`\`\`bash
docker compose up -d
\`\`\`
n8n arayüzü: http://localhost:5678
```

- [ ] **Step 5: Testin fail ettiğini doğrula**

Run: `docker compose build video-worker && docker compose run --rm video-worker pytest tests/test_main.py -v`
Expected: FAIL — `assert 404 == 200` (route yok)

- [ ] **Step 6: /health route'unu ekle**

`video-worker/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="video-worker")


@app.get("/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 7: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_main.py -v`
Expected: PASS

- [ ] **Step 8: n8n'in de ayakta kalktığını doğrula**

Run: `docker compose up -d n8n cloudflared` sonra `curl http://localhost:5678` (200 veya n8n login sayfası HTML'i dönmeli)

- [ ] **Step 9: Commit**

```bash
git add -A
git commit -m "chore: scaffold docker-compose + video-worker skeleton with health endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Konu seçim modülü

**Files:**
- Create: `video-worker/app/topics.py`
- Create: `video-worker/data/topics.json`
- Test: `video-worker/tests/test_topics.py`

**Interfaces:**
- Produces: `select_next_topic(topics_path: str, state_path: str) -> str` — kullanılmamış bir sonraki konuyu döner, state dosyasını günceller. Havuz tükenirse sıfırdan başlar.

- [ ] **Step 1: 50 konuluk topic havuzunu yaz**

`video-worker/data/topics.json`:
```json
[
  "Why flamingos stand on one leg",
  "The Great Emu War of 1932",
  "The world's shortest war: the Anglo-Zanzibar War",
  "Why the sky is blue",
  "Octopuses have three hearts",
  "The Mandela Effect explained",
  "Why cats purr",
  "The Voynich Manuscript mystery",
  "How bees communicate through dance",
  "The Dancing Plague of 1518",
  "Why we dream",
  "The lost city of Atlantis theories",
  "How black holes are formed",
  "The Great Molasses Flood of 1919",
  "Why yawning is contagious",
  "The Bermuda Triangle mystery",
  "How octopuses change color",
  "The Tunguska Event explosion",
  "Why we get goosebumps",
  "The Antikythera Mechanism, an ancient computer",
  "How volcanoes create new islands",
  "The Phantom Time Hypothesis",
  "Why zebras have stripes",
  "The destruction of the Library of Alexandria",
  "How glaciers carve valleys",
  "The Wow! Signal from space",
  "Why do we blush",
  "The lost colony of Roanoke",
  "How tornadoes form",
  "The strange science of deja vu",
  "Why honey never spoils",
  "The Nazca Lines mystery",
  "How the human brain stores memories",
  "Chernobyl's hidden facts",
  "Why cats always land on their feet",
  "The mysterious Baghdad Battery",
  "How rainbows are formed",
  "The Great Fire of London",
  "Why do onions make us cry",
  "The lost Amber Room treasure",
  "How sharks detect blood in water",
  "How coconuts spread across oceans",
  "Why time seems to speed up as we age",
  "The mystery of ball lightning",
  "How penguins survive in Antarctica",
  "The Trinity blast and the dawn of the atomic age",
  "Why we can't tickle ourselves",
  "Pompeii's final hours",
  "How migratory birds navigate using magnetism",
  "The strange physics of quicksand"
]
```

- [ ] **Step 2: Failing test'i yaz**

`video-worker/tests/test_topics.py`:
```python
import json
from app.topics import select_next_topic


def _write_topics(path, topics):
    path.write_text(json.dumps(topics), encoding="utf-8")


def test_selects_first_topic_when_state_empty(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B", "Topic C"])

    result = select_next_topic(str(topics_path), str(state_path))

    assert result == "Topic A"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == ["Topic A"]


def test_skips_already_used_topics(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B", "Topic C"])
    state_path.write_text(json.dumps({"used_topics": ["Topic A"]}), encoding="utf-8")

    result = select_next_topic(str(topics_path), str(state_path))

    assert result == "Topic B"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == ["Topic A", "Topic B"]


def test_resets_when_all_topics_used(tmp_path):
    topics_path = tmp_path / "topics.json"
    state_path = tmp_path / "state.json"
    _write_topics(topics_path, ["Topic A", "Topic B"])
    state_path.write_text(
        json.dumps({"used_topics": ["Topic A", "Topic B"]}), encoding="utf-8"
    )

    result = select_next_topic(str(topics_path), str(state_path))

    assert result == "Topic A"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["used_topics"] == ["Topic A"]
```

- [ ] **Step 3: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_topics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.topics'`

- [ ] **Step 4: Implementasyonu yaz**

`video-worker/app/topics.py`:
```python
import json
from pathlib import Path


def select_next_topic(topics_path: str, state_path: str) -> str:
    topics = json.loads(Path(topics_path).read_text(encoding="utf-8"))

    state_file = Path(state_path)
    if state_file.exists():
        state = json.loads(state_file.read_text(encoding="utf-8"))
        used = state.get("used_topics", [])
    else:
        used = []

    remaining = [t for t in topics if t not in used]
    if not remaining:
        used = []
        remaining = topics

    next_topic = remaining[0]
    used.append(next_topic)

    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(
        json.dumps({"used_topics": used}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    return next_topic
```

- [ ] **Step 5: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_topics.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add video-worker/app/topics.py video-worker/data/topics.json video-worker/tests/test_topics.py
git commit -m "feat: add topic selection module with 50-topic pool

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Config modülü + OpenRouter script üretimi

**Files:**
- Create: `video-worker/app/config.py`
- Create: `video-worker/app/script_gen.py`
- Test: `video-worker/tests/test_script_gen.py`

**Interfaces:**
- Produces: `config` (module-level `Config` instance in `app/config.py`) with attributes `MEDIA_DIR`, `TUNNEL_LOG_PATH`, `OPENROUTER_API_KEY`, `PEXELS_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`, `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_AUDITED` (bool), `TIKTOK_TOKEN_PATH`, `META_IG_USER_ID`, `META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN` — sonraki tüm task'lar bunu kullanacak.
- Produces: `generate_script(topic: str, api_key: str) -> dict` döner `{"script": str, "title": str, "description": str, "tags": list[str]}`. Geçersiz/eksik model yanıtında `ValueError` fırlatır.

- [ ] **Step 1: config.py'yi yaz (test gerektirmez — sadece env var okuma)**

`video-worker/app/config.py`:
```python
import os


class Config:
    MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/media")
    TUNNEL_LOG_PATH = os.environ.get("TUNNEL_LOG_PATH", "/tunnel-logs/tunnel.log")
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
    YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
    YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
    TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    TIKTOK_AUDITED = os.environ.get("TIKTOK_AUDITED", "false").lower() == "true"
    TIKTOK_TOKEN_PATH = os.environ.get(
        "TIKTOK_TOKEN_PATH", "/data/tiktok-token/token.json"
    )
    META_IG_USER_ID = os.environ.get("META_IG_USER_ID", "")
    META_PAGE_ID = os.environ.get("META_PAGE_ID", "")
    META_PAGE_ACCESS_TOKEN = os.environ.get("META_PAGE_ACCESS_TOKEN", "")


config = Config()
```

- [ ] **Step 2: Failing test'i yaz**

`video-worker/tests/test_script_gen.py`:
```python
import json
from unittest.mock import patch, Mock

from app.script_gen import generate_script


def _mock_response(content: str) -> Mock:
    mock_resp = Mock()
    mock_resp.raise_for_status = Mock()
    mock_resp.json.return_value = {"choices": [{"message": {"content": content}}]}
    return mock_resp


@patch("app.script_gen.requests.post")
def test_generate_script_parses_valid_json_response(mock_post):
    payload = {
        "script": "Flamingos stand on one leg to conserve body heat...",
        "title": "Why Flamingos Stand on One Leg",
        "description": "The surprising science behind it. #flamingo #nature #facts",
        "tags": ["flamingo", "nature", "biology", "facts", "animals"],
    }
    mock_post.return_value = _mock_response(json.dumps(payload))

    result = generate_script("Why flamingos stand on one leg", api_key="fake-key")

    assert result == payload
    called_kwargs = mock_post.call_args.kwargs
    assert called_kwargs["headers"]["Authorization"] == "Bearer fake-key"
    assert called_kwargs["json"]["model"] == "qwen/qwen3-coder:free"


@patch("app.script_gen.requests.post")
def test_generate_script_strips_markdown_fences(mock_post):
    payload = {"script": "s", "title": "t", "description": "d", "tags": ["a"]}
    fenced = "```json\n" + json.dumps(payload) + "\n```"
    mock_post.return_value = _mock_response(fenced)

    result = generate_script("Some topic", api_key="fake-key")

    assert result == payload


@patch("app.script_gen.requests.post")
def test_generate_script_raises_on_invalid_json(mock_post):
    mock_post.return_value = _mock_response("not json at all")

    try:
        generate_script("Some topic", api_key="fake-key")
        assert False, "expected ValueError"
    except ValueError:
        pass


@patch("app.script_gen.requests.post")
def test_generate_script_raises_on_missing_key(mock_post):
    incomplete = {"script": "s", "title": "t"}
    mock_post.return_value = _mock_response(json.dumps(incomplete))

    try:
        generate_script("Some topic", api_key="fake-key")
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 3: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_script_gen.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.script_gen'`

- [ ] **Step 4: Implementasyonu yaz**

`video-worker/app/script_gen.py`:
```python
import json
import re

import requests

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "qwen/qwen3-coder:free"

PROMPT_TEMPLATE = """You are writing a script for a short-form (30-45 second) \
faceless YouTube Shorts / TikTok / Instagram Reels video about: "{topic}"

Return ONLY a JSON object with these exact keys, no markdown fences, no extra text:
{{
  "script": "the narration script, 60-90 words, punchy and engaging, written to be read aloud",
  "title": "a short, curiosity-driven video title, under 60 characters",
  "description": "a 1-2 sentence video description including 3-5 relevant hashtags",
  "tags": ["list", "of", "5-8", "single-or-two-word", "tags"]
}}"""


def generate_script(topic: str, api_key: str) -> dict:
    response = requests.post(
        OPENROUTER_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": MODEL,
            "messages": [
                {"role": "user", "content": PROMPT_TEMPLATE.format(topic=topic)}
            ],
        },
        timeout=60,
    )
    response.raise_for_status()

    content = response.json()["choices"][0]["message"]["content"]
    content = _strip_markdown_fences(content)

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model returned invalid JSON: {content!r}") from exc

    for key in ("script", "title", "description", "tags"):
        if key not in data:
            raise ValueError(f"Model response missing required key '{key}': {data!r}")

    return data


def _strip_markdown_fences(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if match:
        return match.group(1)
    return text
```

- [ ] **Step 5: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_script_gen.py -v`
Expected: PASS (4 passed)

- [ ] **Step 6: Commit**

```bash
git add video-worker/app/config.py video-worker/app/script_gen.py video-worker/tests/test_script_gen.py
git commit -m "feat: add config module and OpenRouter script generation

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: TTS seslendirme (edge-tts)

**Files:**
- Create: `video-worker/app/tts.py`
- Create: `video-worker/pytest.ini`
- Test: `video-worker/tests/test_tts.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `async def synthesize_speech(text: str, output_path: str, voice: str = "en-US-GuyNeural") -> list[dict]` — MP3'ü `output_path`'e yazar, `[{"offset": int, "duration": int, "text": str}, ...]` (100-nanosaniye birimli) kelime zamanlama listesi döner. Task 6 (altyazı) bu listeyi tüketecek.

- [ ] **Step 1: pytest.ini'yi yaz (asyncio testleri için)**

`video-worker/pytest.ini`:
```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 2: Failing test'i yaz**

`video-worker/tests/test_tts.py`:
```python
from unittest.mock import patch

from app.tts import synthesize_speech


class _FakeCommunicate:
    def __init__(self, text, voice):
        self.text = text
        self.voice = voice

    async def stream(self):
        yield {"type": "audio", "data": b"AUDIOBYTES1"}
        yield {"type": "WordBoundary", "offset": 0, "duration": 5000000, "text": "Hello"}
        yield {"type": "audio", "data": b"AUDIOBYTES2"}
        yield {"type": "WordBoundary", "offset": 5000000, "duration": 4000000, "text": "world"}


@patch("app.tts.edge_tts.Communicate", _FakeCommunicate)
async def test_synthesize_speech_writes_audio_and_returns_word_boundaries(tmp_path):
    output_path = tmp_path / "speech.mp3"

    boundaries = await synthesize_speech("Hello world", str(output_path))

    assert output_path.read_bytes() == b"AUDIOBYTES1AUDIOBYTES2"
    assert boundaries == [
        {"offset": 0, "duration": 5000000, "text": "Hello"},
        {"offset": 5000000, "duration": 4000000, "text": "world"},
    ]


@patch("app.tts.edge_tts.Communicate", _FakeCommunicate)
async def test_synthesize_speech_uses_requested_voice(tmp_path):
    output_path = tmp_path / "speech.mp3"
    captured = {}

    class _CapturingCommunicate(_FakeCommunicate):
        def __init__(self, text, voice):
            super().__init__(text, voice)
            captured["voice"] = voice

    with patch("app.tts.edge_tts.Communicate", _CapturingCommunicate):
        await synthesize_speech("Hi", str(output_path), voice="en-GB-RyanNeural")

    assert captured["voice"] == "en-GB-RyanNeural"
```

- [ ] **Step 3: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_tts.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tts'`

- [ ] **Step 4: Implementasyonu yaz**

`video-worker/app/tts.py`:
```python
import edge_tts

DEFAULT_VOICE = "en-US-GuyNeural"


async def synthesize_speech(
    text: str, output_path: str, voice: str = DEFAULT_VOICE
) -> list[dict]:
    communicate = edge_tts.Communicate(text, voice)
    word_boundaries = []

    with open(output_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_file.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                word_boundaries.append(
                    {
                        "offset": chunk["offset"],
                        "duration": chunk["duration"],
                        "text": chunk["text"],
                    }
                )

    return word_boundaries
```

- [ ] **Step 5: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_tts.py -v`
Expected: PASS (2 passed)

- [ ] **Step 6: Commit**

```bash
git add video-worker/app/tts.py video-worker/pytest.ini video-worker/tests/test_tts.py
git commit -m "feat: add edge-tts speech synthesis with word boundary tracking

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5: Stok video klip çekme (Pexels)

**Files:**
- Create: `video-worker/app/stock_media.py`
- Test: `video-worker/tests/test_stock_media.py`

**Interfaces:**
- Produces: `extract_keywords(script: str, max_keywords: int = 5) -> list[str]` ve `fetch_stock_clips(keywords: list[str], count: int, api_key: str, output_dir: str) -> list[str]` (indirilen dosyaların lokal path listesi). Task 7 (render) bu path listesini tüketecek.

- [ ] **Step 1: Failing test'i yaz**

`video-worker/tests/test_stock_media.py`:
```python
from unittest.mock import patch, Mock

from app.stock_media import extract_keywords, fetch_stock_clips


def test_extract_keywords_filters_stopwords_and_short_words():
    script = "The flamingo stands on one leg to conserve body heat in cold water"
    keywords = extract_keywords(script, max_keywords=3)
    assert keywords == ["flamingo", "stands", "conserve"]


def test_extract_keywords_falls_back_to_nature_when_empty():
    assert extract_keywords("a to of in on", max_keywords=3) == ["nature"]


def _search_response(link):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "videos": [
            {
                "video_files": [
                    {"link": "https://example.com/landscape.mp4", "width": 1920, "height": 1080},
                    {"link": link, "width": 1080, "height": 1920},
                ]
            }
        ]
    }
    return resp


def _download_response(content):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.content = content
    return resp


@patch("app.stock_media.requests.get")
def test_fetch_stock_clips_downloads_portrait_file(mock_get, tmp_path):
    mock_get.side_effect = [
        _search_response("https://example.com/portrait.mp4"),
        _download_response(b"FAKEVIDEOBYTES"),
    ]

    result = fetch_stock_clips(
        ["flamingo"], count=1, api_key="fake-key", output_dir=str(tmp_path)
    )

    assert result == [str(tmp_path / "clip_0.mp4")]
    assert (tmp_path / "clip_0.mp4").read_bytes() == b"FAKEVIDEOBYTES"
    search_call = mock_get.call_args_list[0]
    assert search_call.kwargs["headers"]["Authorization"] == "fake-key"
    assert search_call.kwargs["params"]["query"] == "flamingo"


@patch("app.stock_media.requests.get")
def test_fetch_stock_clips_cycles_through_keywords(mock_get, tmp_path):
    mock_get.side_effect = [
        _search_response("https://example.com/a.mp4"),
        _download_response(b"A"),
        _search_response("https://example.com/b.mp4"),
        _download_response(b"B"),
    ]

    result = fetch_stock_clips(
        ["flamingo", "wetland"], count=2, api_key="fake-key", output_dir=str(tmp_path)
    )

    assert len(result) == 2
    queries = [
        c.kwargs["params"]["query"]
        for c in mock_get.call_args_list
        if "params" in c.kwargs
    ]
    assert queries == ["flamingo", "wetland"]
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_stock_media.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.stock_media'`

- [ ] **Step 3: Implementasyonu yaz**

`video-worker/app/stock_media.py`:
```python
import re
from pathlib import Path

import requests

PEXELS_SEARCH_URL = "https://api.pexels.com/videos/search"

_STOPWORDS = {
    "the", "a", "an", "is", "are", "was", "were", "to", "of", "in", "on",
    "and", "or", "but", "for", "with", "at", "by", "it", "this", "that",
    "their", "its", "as", "from", "than", "so", "we", "they", "you",
}


def extract_keywords(script: str, max_keywords: int = 5) -> list[str]:
    words = re.findall(r"[A-Za-z]+", script)
    seen = []
    for word in words:
        lower = word.lower()
        if lower in _STOPWORDS or len(lower) < 4:
            continue
        if lower not in seen:
            seen.append(lower)
        if len(seen) >= max_keywords:
            break
    return seen or ["nature"]


def fetch_stock_clips(
    keywords: list[str], count: int, api_key: str, output_dir: str
) -> list[str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    downloaded = []
    for index in range(count):
        keyword = keywords[index % len(keywords)]
        video_file_url = _search_portrait_video(keyword, api_key)
        if video_file_url is None:
            continue

        clip_path = output / f"clip_{index}.mp4"
        _download_file(video_file_url, clip_path)
        downloaded.append(str(clip_path))

    return downloaded


def _search_portrait_video(keyword: str, api_key: str):
    response = requests.get(
        PEXELS_SEARCH_URL,
        headers={"Authorization": api_key},
        params={"query": keyword, "orientation": "portrait", "per_page": 1},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    videos = data.get("videos", [])
    if not videos:
        return None

    video_files = videos[0].get("video_files", [])
    portrait_files = [
        f for f in video_files if f.get("height", 0) > f.get("width", 0)
    ]
    candidates = portrait_files or video_files
    if not candidates:
        return None

    return candidates[0]["link"]


def _download_file(url: str, destination: Path) -> None:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    destination.write_bytes(response.content)
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_stock_media.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add video-worker/app/stock_media.py video-worker/tests/test_stock_media.py
git commit -m "feat: add Pexels stock video fetching

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 6: Altyazı (SRT) üretimi

**Files:**
- Create: `video-worker/app/subtitles.py`
- Test: `video-worker/tests/test_subtitles.py`

**Interfaces:**
- Consumes: Task 4'ün `synthesize_speech()` çıktısı — `list[dict]` with keys `offset`, `duration`, `text` (100-nanosaniye birimli).
- Produces: `write_srt(word_boundaries: list[dict], output_path: str, words_per_cue: int = 3) -> str` — SRT dosyasını yazar, path'i döner. Task 7 (render) bu dosyayı FFmpeg'e verecek.

- [ ] **Step 1: Failing test'i yaz**

`video-worker/tests/test_subtitles.py`:
```python
from app.subtitles import write_srt


def test_write_srt_groups_words_into_cues(tmp_path):
    # offset/duration 100-nanosecond units: 10_000_000 == 1 second
    boundaries = [
        {"offset": 0, "duration": 10_000_000, "text": "Flamingos"},
        {"offset": 10_000_000, "duration": 10_000_000, "text": "stand"},
        {"offset": 20_000_000, "duration": 10_000_000, "text": "on"},
        {"offset": 30_000_000, "duration": 10_000_000, "text": "one"},
        {"offset": 40_000_000, "duration": 10_000_000, "text": "leg"},
    ]
    output_path = tmp_path / "subs.srt"

    result = write_srt(boundaries, str(output_path), words_per_cue=3)

    assert result == str(output_path)
    content = output_path.read_text(encoding="utf-8")
    assert content == (
        "1\n"
        "00:00:00,000 --> 00:00:03,000\n"
        "Flamingos stand on\n"
        "\n"
        "2\n"
        "00:00:03,000 --> 00:00:05,000\n"
        "one leg\n"
        "\n"
    )


def test_write_srt_handles_empty_boundaries(tmp_path):
    output_path = tmp_path / "subs.srt"

    result = write_srt([], str(output_path))

    assert result == str(output_path)
    assert output_path.read_text(encoding="utf-8") == ""


def test_write_srt_formats_hours_and_milliseconds(tmp_path):
    boundaries = [
        {"offset": 36_615_000_000, "duration": 5_000_000, "text": "late"},
    ]
    output_path = tmp_path / "subs.srt"

    write_srt(boundaries, str(output_path), words_per_cue=1)

    content = output_path.read_text(encoding="utf-8")
    assert "01:01:01,500 --> 01:01:02,000" in content
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_subtitles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.subtitles'`

- [ ] **Step 3: Implementasyonu yaz**

`video-worker/app/subtitles.py`:
```python
from pathlib import Path

# edge-tts reports offsets/durations in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000


def write_srt(
    word_boundaries: list[dict], output_path: str, words_per_cue: int = 3
) -> str:
    cues = []
    for start in range(0, len(word_boundaries), words_per_cue):
        group = word_boundaries[start : start + words_per_cue]
        cue_start = group[0]["offset"]
        cue_end = group[-1]["offset"] + group[-1]["duration"]
        text = " ".join(word["text"] for word in group)
        cues.append((cue_start, cue_end, text))

    lines = []
    for index, (start_ticks, end_ticks, text) in enumerate(cues, start=1):
        lines.append(str(index))
        lines.append(
            f"{_format_timestamp(start_ticks)} --> {_format_timestamp(end_ticks)}"
        )
        lines.append(text)
        lines.append("")

    content = "\n".join(lines)
    if content:
        content += "\n"

    Path(output_path).write_text(content, encoding="utf-8")
    return output_path


def _format_timestamp(ticks: int) -> str:
    total_ms = ticks // (TICKS_PER_SECOND // 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_subtitles.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add video-worker/app/subtitles.py video-worker/tests/test_subtitles.py
git commit -m "feat: add SRT subtitle generation from TTS word boundaries

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 7: FFmpeg render (klipler + ses + altyazı → 9:16 MP4)

**Files:**
- Create: `video-worker/app/render.py`
- Test: `video-worker/tests/test_render.py`

**Interfaces:**
- Consumes: Task 5'in `fetch_stock_clips()` path listesi, Task 4'ün MP3 çıktısı, Task 6'nın SRT çıktısı.
- Produces: `get_audio_duration(audio_path: str) -> float` ve `render_video(clip_paths: list[str], audio_path: str, srt_path: str, output_path: str, work_dir: str) -> str` — 1080x1920 MP4 üretir, path'i döner. Klip yoksa `ValueError`, FFmpeg hata verirse `RuntimeError` fırlatır.

- [ ] **Step 1: Failing test'i yaz**

`video-worker/tests/test_render.py`:
```python
from unittest.mock import patch, Mock

import pytest

from app.render import get_audio_duration, render_video


@patch("app.render.subprocess.run")
def test_get_audio_duration_parses_ffprobe_output(mock_run):
    mock_run.return_value = Mock(returncode=0, stdout="42.500000\n", stderr="")

    assert get_audio_duration("/tmp/speech.mp3") == 42.5

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "ffprobe"
    assert "/tmp/speech.mp3" in cmd


@patch("app.render.subprocess.run")
def test_get_audio_duration_raises_on_ffprobe_failure(mock_run):
    mock_run.return_value = Mock(returncode=1, stdout="", stderr="no such file")

    with pytest.raises(RuntimeError, match="ffprobe failed"):
        get_audio_duration("/tmp/missing.mp3")


def test_render_video_raises_when_no_clips(tmp_path):
    with pytest.raises(ValueError, match="at least one clip"):
        render_video(
            [],
            str(tmp_path / "a.mp3"),
            str(tmp_path / "s.srt"),
            str(tmp_path / "out.mp4"),
            str(tmp_path),
        )


@patch("app.render.get_audio_duration", return_value=30.0)
@patch("app.render.subprocess.run")
def test_render_video_builds_concat_list_and_runs_ffmpeg(
    mock_run, mock_duration, tmp_path
):
    mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
    clip_a = tmp_path / "clip_0.mp4"
    clip_b = tmp_path / "clip_1.mp4"
    clip_a.write_bytes(b"A")
    clip_b.write_bytes(b"B")
    output_path = tmp_path / "final.mp4"

    result = render_video(
        [str(clip_a), str(clip_b)],
        str(tmp_path / "speech.mp3"),
        str(tmp_path / "subs.srt"),
        str(output_path),
        str(tmp_path),
    )

    assert result == str(output_path)

    concat_file = tmp_path / "concat.txt"
    concat_content = concat_file.read_text(encoding="utf-8")
    assert f"file '{clip_a}'" in concat_content
    assert f"file '{clip_b}'" in concat_content

    cmd = mock_run.call_args.args[0]
    assert cmd[0] == "ffmpeg"
    assert "-shortest" in cmd
    joined = " ".join(cmd)
    assert "1080:1920" in joined
    assert "subtitles=" in joined
    assert str(output_path) in cmd


@patch("app.render.get_audio_duration", return_value=30.0)
@patch("app.render.subprocess.run")
def test_render_video_raises_on_ffmpeg_failure(mock_run, mock_duration, tmp_path):
    mock_run.return_value = Mock(returncode=1, stdout="", stderr="encoder not found")
    clip = tmp_path / "clip_0.mp4"
    clip.write_bytes(b"A")

    with pytest.raises(RuntimeError, match="ffmpeg failed"):
        render_video(
            [str(clip)],
            str(tmp_path / "speech.mp3"),
            str(tmp_path / "subs.srt"),
            str(tmp_path / "out.mp4"),
            str(tmp_path),
        )
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.render'`

- [ ] **Step 3: Implementasyonu yaz**

`video-worker/app/render.py`:
```python
import subprocess
from pathlib import Path

WIDTH = 1080
HEIGHT = 1920

SUBTITLE_STYLE = (
    "FontName=DejaVu Sans,FontSize=16,PrimaryColour=&H00FFFFFF,"
    "OutlineColour=&H00000000,BorderStyle=1,Outline=2,Shadow=0,"
    "Alignment=2,MarginV=180"
)


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def render_video(
    clip_paths: list[str],
    audio_path: str,
    srt_path: str,
    output_path: str,
    work_dir: str,
) -> str:
    if not clip_paths:
        raise ValueError("render_video needs at least one clip")

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    # Loop the clip list so the visuals outlast the narration; -shortest trims.
    audio_duration = get_audio_duration(audio_path)
    concat_file = work / "concat.txt"
    concat_lines = []
    # Each stock clip is typically 10-20s; repeat the list enough times to cover audio.
    repeats = max(1, int(audio_duration // (len(clip_paths) * 5)) + 1)
    for _ in range(repeats):
        for clip in clip_paths:
            concat_lines.append(f"file '{clip}'")
    concat_file.write_text("\n".join(concat_lines) + "\n", encoding="utf-8")

    escaped_srt = _escape_for_filter(srt_path)
    video_filter = (
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},"
        f"subtitles='{escaped_srt}':force_style='{SUBTITLE_STYLE}'"
    )

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(
        [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_file),
            "-i", audio_path,
            "-vf", video_filter,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-c:a", "aac", "-b:a", "128k",
            "-pix_fmt", "yuv420p",
            "-r", "30",
            "-shortest",
            output_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-2000:]}")

    return output_path


def _escape_for_filter(path: str) -> str:
    # ffmpeg filter args treat ':' and '\' specially inside quoted values.
    return path.replace("\\", "\\\\").replace(":", "\\:")
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_render.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add video-worker/app/render.py video-worker/tests/test_render.py
git commit -m "feat: add FFmpeg 9:16 video rendering with burned-in subtitles

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 8: Pipeline orkestrasyonu + `/generate` endpoint'i

**Files:**
- Create: `video-worker/app/pipeline.py`
- Modify: `video-worker/app/main.py`
- Test: `video-worker/tests/test_pipeline.py`
- Test: `video-worker/tests/test_generate_endpoint.py`

**Interfaces:**
- Consumes: `select_next_topic()` (Task 2), `generate_script()` (Task 3), `synthesize_speech()` (Task 4), `extract_keywords()` + `fetch_stock_clips()` (Task 5), `write_srt()` (Task 6), `render_video()` (Task 7), `config` (Task 3).
- Produces: `async def generate_video(job_id: str) -> dict` döner `{"job_id": str, "video_path": str, "video_filename": str, "topic": str, "title": str, "description": str, "tags": list[str]}`. Ayrıca `POST /generate` endpoint'i aynı dict'i JSON olarak döner; hata halinde HTTP 500 + `{"detail": "<mesaj>"}`.

- [ ] **Step 1: Failing pipeline test'ini yaz**

`video-worker/tests/test_pipeline.py`:
```python
from unittest.mock import patch, AsyncMock

from app.pipeline import generate_video


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_srt")
@patch("app.pipeline.fetch_stock_clips")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_runs_full_pipeline(
    mock_topic, mock_script, mock_tts, mock_clips, mock_srt, mock_render, tmp_path
):
    mock_topic.return_value = "Why flamingos stand on one leg"
    mock_script.return_value = {
        "script": "Flamingos conserve heat by standing on one leg.",
        "title": "Why Flamingos Stand on One Leg",
        "description": "Surprising science. #flamingo #facts",
        "tags": ["flamingo", "nature"],
    }
    mock_tts.return_value = [{"offset": 0, "duration": 10_000_000, "text": "Flamingos"}]
    mock_clips.return_value = ["/work/clip_0.mp4"]
    mock_srt.return_value = "/work/subs.srt"
    mock_render.side_effect = lambda *a, **k: a[3]

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        result = await generate_video("job123")

    assert result["job_id"] == "job123"
    assert result["topic"] == "Why flamingos stand on one leg"
    assert result["title"] == "Why Flamingos Stand on One Leg"
    assert result["description"] == "Surprising science. #flamingo #facts"
    assert result["tags"] == ["flamingo", "nature"]
    assert result["video_filename"] == "job123.mp4"
    assert result["video_path"] == str(tmp_path / "job123.mp4")

    mock_script.assert_called_once_with(
        "Why flamingos stand on one leg", api_key="or-key"
    )
    assert mock_clips.call_args.kwargs["api_key"] == "px-key"


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_srt")
@patch("app.pipeline.fetch_stock_clips", return_value=[])
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_raises_when_no_clips_downloaded(
    mock_topic, mock_script, mock_tts, mock_clips, mock_srt, mock_render, tmp_path
):
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "text", "title": "t", "description": "d", "tags": []
    }
    mock_tts.return_value = []
    mock_srt.return_value = "/work/subs.srt"

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        try:
            await generate_video("job456")
            assert False, "expected RuntimeError"
        except RuntimeError as exc:
            assert "no stock clips" in str(exc).lower()
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipeline'`

- [ ] **Step 3: pipeline.py'yi yaz**

`video-worker/app/pipeline.py`:
```python
import shutil
from pathlib import Path

from app.config import config
from app.render import render_video
from app.script_gen import generate_script
from app.stock_media import extract_keywords, fetch_stock_clips
from app.subtitles import write_srt
from app.topics import select_next_topic
from app.tts import synthesize_speech

TOPICS_PATH = "/app/data/topics.json"
CLIP_COUNT = 4


async def generate_video(job_id: str) -> dict:
    media_dir = Path(config.MEDIA_DIR)
    work_dir = media_dir / "work" / job_id
    work_dir.mkdir(parents=True, exist_ok=True)

    try:
        state_path = str(media_dir / "used_topics.json")
        topic = select_next_topic(TOPICS_PATH, state_path)

        script_data = generate_script(topic, api_key=config.OPENROUTER_API_KEY)

        audio_path = str(work_dir / "speech.mp3")
        word_boundaries = await synthesize_speech(script_data["script"], audio_path)

        srt_path = write_srt(word_boundaries, str(work_dir / "subs.srt"))

        keywords = extract_keywords(script_data["script"])
        clip_paths = fetch_stock_clips(
            keywords,
            count=CLIP_COUNT,
            api_key=config.PEXELS_API_KEY,
            output_dir=str(work_dir),
        )
        if not clip_paths:
            raise RuntimeError(
                f"Pexels returned no stock clips for keywords: {keywords}"
            )

        video_filename = f"{job_id}.mp4"
        video_path = str(media_dir / video_filename)
        render_video(clip_paths, audio_path, srt_path, video_path, str(work_dir))

        return {
            "job_id": job_id,
            "video_path": video_path,
            "video_filename": video_filename,
            "topic": topic,
            "title": script_data["title"],
            "description": script_data["description"],
            "tags": script_data["tags"],
        }
    finally:
        # Runs on both success and failure so a render/API error never leaves
        # half-downloaded clips or TTS audio behind on disk.
        shutil.rmtree(work_dir, ignore_errors=True)
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_pipeline.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: `/generate` endpoint testini yaz (failing)**

`video-worker/tests/test_generate_endpoint.py`:
```python
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.generate_video", new_callable=AsyncMock)
def test_generate_endpoint_returns_pipeline_result(mock_generate):
    mock_generate.return_value = {
        "job_id": "20260903-120000",
        "video_path": "/data/media/20260903-120000.mp4",
        "video_filename": "20260903-120000.mp4",
        "topic": "Why flamingos stand on one leg",
        "title": "Why Flamingos Stand on One Leg",
        "description": "Surprising science. #flamingo",
        "tags": ["flamingo"],
    }

    response = client.post("/generate")

    assert response.status_code == 200
    assert response.json()["video_filename"] == "20260903-120000.mp4"
    assert mock_generate.await_count == 1


@patch("app.main.generate_video", new_callable=AsyncMock)
def test_generate_endpoint_returns_500_on_pipeline_error(mock_generate):
    mock_generate.side_effect = RuntimeError("Pexels returned no stock clips")

    response = client.post("/generate")

    assert response.status_code == 500
    assert "no stock clips" in response.json()["detail"]
```

- [ ] **Step 6: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_generate_endpoint.py -v`
Expected: FAIL — `AttributeError: <module 'app.main'> does not have the attribute 'generate_video'`

- [ ] **Step 7: main.py'ye `/generate` endpoint'ini ekle**

`video-worker/app/main.py`:
```python
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException

from app.pipeline import generate_video

app = FastAPI(title="video-worker")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate():
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        return await generate_video(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
```

- [ ] **Step 8: Testlerin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/ -v`
Expected: PASS (tüm testler — Task 1-8 arası ~23 test)

- [ ] **Step 9: Commit**

```bash
git add video-worker/app/pipeline.py video-worker/app/main.py video-worker/tests/test_pipeline.py video-worker/tests/test_generate_endpoint.py
git commit -m "feat: add video generation pipeline orchestration and /generate endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 9: Cloudflare tunnel URL çözümleme + `/media/{filename}` public rota

**Files:**
- Create: `video-worker/app/tunnel.py`
- Modify: `video-worker/app/main.py`
- Test: `video-worker/tests/test_tunnel.py`
- Test: `video-worker/tests/test_media_endpoint.py`

**Interfaces:**
- Produces: `get_tunnel_url(log_path: str) -> str` — `cloudflared`'ın log dosyasından en güncel `https://*.trycloudflare.com` adresini döner, bulamazsa `RuntimeError`. Task 11 (Meta publisher) bunu Instagram'ın `video_url` parametresi için kullanacak.
- Produces: `GET /media/{filename}` — `config.MEDIA_DIR` içindeki dosyayı `video/mp4` olarak döner; path traversal veya bulunamayan dosyada 400/404.

- [ ] **Step 1: Failing tunnel testini yaz**

`video-worker/tests/test_tunnel.py`:
```python
import pytest

from app.tunnel import get_tunnel_url


def test_get_tunnel_url_extracts_url_from_log(tmp_path):
    log_path = tmp_path / "tunnel.log"
    log_path.write_text(
        "2026-09-03T09:00:00Z INF Starting tunnel\n"
        "2026-09-03T09:00:01Z INF |  https://random-words-here.trycloudflare.com  |\n",
        encoding="utf-8",
    )

    assert (
        get_tunnel_url(str(log_path))
        == "https://random-words-here.trycloudflare.com"
    )


def test_get_tunnel_url_returns_most_recent_when_multiple(tmp_path):
    log_path = tmp_path / "tunnel.log"
    log_path.write_text(
        "https://old-url.trycloudflare.com\nhttps://new-url.trycloudflare.com\n",
        encoding="utf-8",
    )

    assert get_tunnel_url(str(log_path)) == "https://new-url.trycloudflare.com"


def test_get_tunnel_url_raises_when_not_found(tmp_path):
    log_path = tmp_path / "tunnel.log"
    log_path.write_text("still starting up...\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="No trycloudflare.com URL"):
        get_tunnel_url(str(log_path))
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_tunnel.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tunnel'`

- [ ] **Step 3: tunnel.py'yi yaz**

`video-worker/app/tunnel.py`:
```python
import re
from pathlib import Path

TUNNEL_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def get_tunnel_url(log_path: str) -> str:
    content = Path(log_path).read_text(encoding="utf-8", errors="ignore")
    matches = TUNNEL_URL_PATTERN.findall(content)
    if not matches:
        raise RuntimeError(
            f"No trycloudflare.com URL found in tunnel log at {log_path}"
        )
    return matches[-1]
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_tunnel.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Failing `/media` endpoint testini yaz**

`video-worker/tests/test_media_endpoint.py`:
```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_media_returns_file_contents(tmp_path):
    media_file = tmp_path / "abc.mp4"
    media_file.write_bytes(b"VIDEOBYTES")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/abc.mp4")

    assert response.status_code == 200
    assert response.content == b"VIDEOBYTES"


def test_get_media_rejects_path_traversal():
    response = client.get("/media/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code in (400, 404)


def test_get_media_returns_404_for_missing_file(tmp_path):
    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/media/missing.mp4")

    assert response.status_code == 404
```

- [ ] **Step 6: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_media_endpoint.py -v`
Expected: FAIL — 404 for `/media/abc.mp4` (route yok)

- [ ] **Step 7: main.py'ye `/media/{filename}` rotasını ekle**

`video-worker/app/main.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from app.config import config
from app.pipeline import generate_video

app = FastAPI(title="video-worker")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate():
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        return await generate_video(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/media/{filename}")
def get_media(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    file_path = Path(config.MEDIA_DIR) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="not found")

    return FileResponse(str(file_path), media_type="video/mp4")
```

- [ ] **Step 8: Testlerin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/ -v`
Expected: PASS (tüm testler yeşil)

- [ ] **Step 9: Commit**

```bash
git add video-worker/app/tunnel.py video-worker/app/main.py video-worker/tests/test_tunnel.py video-worker/tests/test_media_endpoint.py
git commit -m "feat: add Cloudflare tunnel URL resolution and public /media route

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 10: YouTube publisher (resumable upload, unlisted)

**Files:**
- Create: `video-worker/app/publishers/__init__.py`
- Create: `video-worker/app/publishers/youtube.py`
- Create: `video-worker/tests/publishers/__init__.py`
- Test: `video-worker/tests/publishers/test_youtube.py`

**Interfaces:**
- Produces: `upload_to_youtube(video_path: str, title: str, description: str, tags: list[str], client_id: str, client_secret: str, refresh_token: str) -> dict` — başarıda `{"platform": "youtube", "status": "success", "video_id": str, "url": str}`, hatada `{"platform": "youtube", "status": "error", "error": str}` döner (asla exception fırlatmaz — Task 13'ün `/publish` endpoint'i her platformdan bağımsız sonuç toplayabilsin diye).

- [ ] **Step 1: Failing test'i yaz**

`video-worker/tests/publishers/__init__.py`: (boş dosya)

`video-worker/tests/publishers/test_youtube.py`:
```python
from unittest.mock import patch, Mock

from app.publishers.youtube import upload_to_youtube


def _token_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"access_token": "access-tok"}
    return resp


def _init_response(location):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.headers = {"Location": location}
    return resp


def _upload_response(video_id):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {"id": video_id}
    return resp


@patch("app.publishers.youtube.requests.put")
@patch("app.publishers.youtube.requests.post")
def test_upload_to_youtube_success(mock_post, mock_put, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_post.side_effect = [
        _token_response(),
        _init_response("https://upload.example.com/resumable/xyz"),
    ]
    mock_put.return_value = _upload_response("abc123")

    result = upload_to_youtube(
        str(video_path),
        title="Why Flamingos Stand on One Leg",
        description="desc",
        tags=["flamingo"],
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
    )

    assert result == {
        "platform": "youtube",
        "status": "success",
        "video_id": "abc123",
        "url": "https://youtube.com/shorts/abc123",
    }

    token_call = mock_post.call_args_list[0]
    assert token_call.kwargs["data"]["refresh_token"] == "rtoken"
    init_call = mock_post.call_args_list[1]
    assert init_call.kwargs["headers"]["Authorization"] == "Bearer access-tok"
    assert init_call.kwargs["json"]["status"]["privacyStatus"] == "unlisted"


@patch("app.publishers.youtube.requests.post")
def test_upload_to_youtube_returns_error_dict_on_failure(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    mock_post.side_effect = Exception("token refresh failed")

    result = upload_to_youtube(
        str(video_path),
        title="t",
        description="d",
        tags=[],
        client_id="cid",
        client_secret="csecret",
        refresh_token="rtoken",
    )

    assert result["platform"] == "youtube"
    assert result["status"] == "error"
    assert "token refresh failed" in result["error"]
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/publishers/test_youtube.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.publishers'`

- [ ] **Step 3: Implementasyonu yaz**

`video-worker/app/publishers/__init__.py`: (boş dosya)

`video-worker/app/publishers/youtube.py`:
```python
import os

import requests

TOKEN_URL = "https://oauth2.googleapis.com/token"
UPLOAD_URL = (
    "https://www.googleapis.com/upload/youtube/v3/videos"
    "?uploadType=resumable&part=snippet,status"
)


def upload_to_youtube(
    video_path: str,
    title: str,
    description: str,
    tags: list[str],
    client_id: str,
    client_secret: str,
    refresh_token: str,
) -> dict:
    try:
        access_token = get_access_token(client_id, client_secret, refresh_token)
        video_size = os.path.getsize(video_path)

        init_response = requests.post(
            UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
                "X-Upload-Content-Type": "video/mp4",
                "X-Upload-Content-Length": str(video_size),
            },
            json={
                "snippet": {
                    "title": title[:100],
                    "description": description,
                    "tags": tags,
                    "categoryId": "22",
                },
                "status": {"privacyStatus": "unlisted"},
            },
            timeout=30,
        )
        init_response.raise_for_status()
        upload_url = init_response.headers["Location"]

        with open(video_path, "rb") as video_file:
            upload_response = requests.put(
                upload_url,
                headers={"Content-Type": "video/mp4"},
                data=video_file,
                timeout=600,
            )
        upload_response.raise_for_status()
        video_id = upload_response.json()["id"]

        return {
            "platform": "youtube",
            "status": "success",
            "video_id": video_id,
            "url": f"https://youtube.com/shorts/{video_id}",
        }
    except Exception as exc:
        return {"platform": "youtube", "status": "error", "error": str(exc)}


def get_access_token(client_id: str, client_secret: str, refresh_token: str) -> str:
    response = requests.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["access_token"]
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/publishers/test_youtube.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add video-worker/app/publishers/__init__.py video-worker/app/publishers/youtube.py video-worker/tests/publishers/
git commit -m "feat: add YouTube resumable upload publisher

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 11: TikTok publisher (token refresh + rotation, FILE_UPLOAD)

TikTok'un access token'ı 24 saatte bir sona erer ve her yenilemede **refresh token da rotasyona uğrar** (eski refresh token geçersiz olur) — bu yüzden her upload öncesi yenilenip, yeni refresh token diskte kalıcı olarak güncellenmeli. `TIKTOK_AUDITED=false` olduğu sürece (bkz. Task 20) yükleme zorunlu olarak `SELF_ONLY` (private) olur.

**Files:**
- Create: `video-worker/app/publishers/tiktok.py`
- Test: `video-worker/tests/publishers/test_tiktok.py`

**Interfaces:**
- Consumes: `config.TIKTOK_TOKEN_PATH` içindeki `{"refresh_token": str}` JSON dosyası (Task 20'de manuel olarak ilk kez oluşturulacak).
- Produces: `upload_to_tiktok(video_path: str, title: str, client_key: str, client_secret: str, token_path: str, audited: bool = False) -> dict` — başarıda `{"platform": "tiktok", "status": "success", "publish_id": str, "privacy_level": str}`, hatada `{"platform": "tiktok", "status": "error", "error": str}`.

- [ ] **Step 1: Failing test'i yaz**

`video-worker/tests/publishers/test_tiktok.py`:
```python
import json
from unittest.mock import patch, Mock

from app.publishers.tiktok import upload_to_tiktok


def _refresh_response(access_token, new_refresh_token):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "expires_in": 86400,
    }
    return resp


def _init_response(publish_id, upload_url):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = {
        "data": {"publish_id": publish_id, "upload_url": upload_url}
    }
    return resp


def _ok_response():
    resp = Mock()
    resp.raise_for_status = Mock()
    return resp


@patch("app.publishers.tiktok.requests.put")
@patch("app.publishers.tiktok.requests.post")
def test_upload_to_tiktok_success_refreshes_and_rotates_token(
    mock_post, mock_put, tmp_path
):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps({"refresh_token": "old-refresh"}), encoding="utf-8"
    )

    mock_post.side_effect = [
        _refresh_response("access-tok", "new-refresh"),
        _init_response("pub123", "https://upload.tiktokapis.com/xyz"),
    ]
    mock_put.return_value = _ok_response()

    result = upload_to_tiktok(
        str(video_path),
        title="Why Flamingos Stand on One Leg",
        client_key="ckey",
        client_secret="csecret",
        token_path=str(token_path),
        audited=False,
    )

    assert result == {
        "platform": "tiktok",
        "status": "success",
        "publish_id": "pub123",
        "privacy_level": "SELF_ONLY",
    }

    stored = json.loads(token_path.read_text(encoding="utf-8"))
    assert stored["refresh_token"] == "new-refresh"

    refresh_call = mock_post.call_args_list[0]
    assert refresh_call.kwargs["data"]["refresh_token"] == "old-refresh"
    init_call = mock_post.call_args_list[1]
    assert init_call.kwargs["json"]["post_info"]["privacy_level"] == "SELF_ONLY"


@patch("app.publishers.tiktok.requests.put")
@patch("app.publishers.tiktok.requests.post")
def test_upload_to_tiktok_uses_public_privacy_when_audited(
    mock_post, mock_put, tmp_path
):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps({"refresh_token": "old-refresh"}), encoding="utf-8"
    )

    mock_post.side_effect = [
        _refresh_response("access-tok", "new-refresh"),
        _init_response("pub456", "https://upload.tiktokapis.com/abc"),
    ]
    mock_put.return_value = _ok_response()

    result = upload_to_tiktok(
        str(video_path),
        title="t",
        client_key="ckey",
        client_secret="csecret",
        token_path=str(token_path),
        audited=True,
    )

    assert result["privacy_level"] == "PUBLIC_TO_EVERYONE"


@patch("app.publishers.tiktok.requests.post")
def test_upload_to_tiktok_returns_error_dict_on_failure(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    token_path = tmp_path / "token.json"
    token_path.write_text(
        json.dumps({"refresh_token": "old-refresh"}), encoding="utf-8"
    )
    mock_post.side_effect = Exception("refresh failed")

    result = upload_to_tiktok(
        str(video_path),
        title="t",
        client_key="ckey",
        client_secret="csecret",
        token_path=str(token_path),
        audited=False,
    )

    assert result["platform"] == "tiktok"
    assert result["status"] == "error"
    assert "refresh failed" in result["error"]
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/publishers/test_tiktok.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.publishers.tiktok'`

- [ ] **Step 3: Implementasyonu yaz**

`video-worker/app/publishers/tiktok.py`:
```python
import json
import os
from pathlib import Path

import requests

TOKEN_REFRESH_URL = "https://open.tiktokapis.com/v2/oauth/token/"
INIT_UPLOAD_URL = "https://open.tiktokapis.com/v2/post/publish/video/init/"


def upload_to_tiktok(
    video_path: str,
    title: str,
    client_key: str,
    client_secret: str,
    token_path: str,
    audited: bool = False,
) -> dict:
    try:
        access_token = _refresh_access_token(client_key, client_secret, token_path)
        video_size = os.path.getsize(video_path)
        privacy_level = "PUBLIC_TO_EVERYONE" if audited else "SELF_ONLY"

        init_response = requests.post(
            INIT_UPLOAD_URL,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json; charset=UTF-8",
            },
            json={
                "post_info": {
                    "title": title[:150],
                    "privacy_level": privacy_level,
                    "disable_duet": False,
                    "disable_comment": False,
                    "disable_stitch": False,
                },
                "source_info": {
                    "source": "FILE_UPLOAD",
                    "video_size": video_size,
                    "chunk_size": video_size,
                    "total_chunk_count": 1,
                },
            },
            timeout=30,
        )
        init_response.raise_for_status()
        init_data = init_response.json()["data"]
        publish_id = init_data["publish_id"]
        upload_url = init_data["upload_url"]

        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()

        upload_response = requests.put(
            upload_url,
            headers={
                "Content-Type": "video/mp4",
                "Content-Range": f"bytes 0-{video_size - 1}/{video_size}",
            },
            data=video_bytes,
            timeout=600,
        )
        upload_response.raise_for_status()

        return {
            "platform": "tiktok",
            "status": "success",
            "publish_id": publish_id,
            "privacy_level": privacy_level,
        }
    except Exception as exc:
        return {"platform": "tiktok", "status": "error", "error": str(exc)}


def _refresh_access_token(
    client_key: str, client_secret: str, token_path: str
) -> str:
    stored = json.loads(Path(token_path).read_text(encoding="utf-8"))
    current_refresh_token = stored["refresh_token"]

    response = requests.post(
        TOKEN_REFRESH_URL,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": current_refresh_token,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    # TikTok rotates the refresh token on every use — persist the new one.
    Path(token_path).write_text(
        json.dumps({"refresh_token": data["refresh_token"]}), encoding="utf-8"
    )

    return data["access_token"]
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/publishers/test_tiktok.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add video-worker/app/publishers/tiktok.py video-worker/tests/publishers/test_tiktok.py
git commit -m "feat: add TikTok publisher with rotating refresh-token persistence

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 12: Meta publisher (Instagram Reels via tunnel URL, Facebook Reels via resumable upload)

Instagram, `video_url` üzerinden Meta'nın videoyu çekmesini gerektirir (Task 9'daki `/media` rotası + Task 9'daki tunnel URL burada birleşiyor). Facebook Reels ise doğrudan binary upload (resumable protokol) kabul eder, public URL gerekmez.

**Files:**
- Create: `video-worker/app/publishers/meta.py`
- Test: `video-worker/tests/publishers/test_meta.py`

**Interfaces:**
- Consumes: `get_tunnel_url()` (Task 9).
- Produces: `upload_to_instagram(video_filename: str, caption: str, ig_user_id: str, page_access_token: str, tunnel_log_path: str) -> dict` ve `upload_to_facebook(video_path: str, description: str, page_id: str, page_access_token: str) -> dict` — ikisi de `{"platform": ..., "status": "success"/"error", ...}` döner, exception fırlatmaz.

- [ ] **Step 1: Failing test'i yaz**

`video-worker/tests/publishers/test_meta.py`:
```python
from unittest.mock import patch, Mock

from app.publishers.meta import upload_to_instagram, upload_to_facebook


def _resp(json_data=None):
    resp = Mock()
    resp.raise_for_status = Mock()
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


@patch("app.publishers.meta.time.sleep")
@patch(
    "app.publishers.meta.get_tunnel_url",
    return_value="https://abc123.trycloudflare.com",
)
@patch("app.publishers.meta.requests.get")
@patch("app.publishers.meta.requests.post")
def test_upload_to_instagram_success(mock_post, mock_get, mock_tunnel, mock_sleep):
    mock_post.side_effect = [_resp({"id": "creation123"}), _resp({"id": "media456"})]
    mock_get.return_value = _resp({"status_code": "FINISHED"})

    result = upload_to_instagram(
        video_filename="job123.mp4",
        caption="Why flamingos stand on one leg #facts",
        ig_user_id="ig123",
        page_access_token="page-tok",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result == {
        "platform": "instagram",
        "status": "success",
        "media_id": "media456",
    }

    create_call = mock_post.call_args_list[0]
    assert (
        create_call.kwargs["data"]["video_url"]
        == "https://abc123.trycloudflare.com/media/job123.mp4"
    )
    assert create_call.kwargs["data"]["media_type"] == "REELS"


@patch("app.publishers.meta.time.sleep")
@patch(
    "app.publishers.meta.get_tunnel_url",
    return_value="https://abc123.trycloudflare.com",
)
@patch("app.publishers.meta.requests.get")
@patch("app.publishers.meta.requests.post")
def test_upload_to_instagram_polls_until_finished(
    mock_post, mock_get, mock_tunnel, mock_sleep
):
    mock_post.side_effect = [_resp({"id": "creation123"}), _resp({"id": "media456"})]
    mock_get.side_effect = [
        _resp({"status_code": "IN_PROGRESS"}),
        _resp({"status_code": "FINISHED"}),
    ]

    result = upload_to_instagram(
        video_filename="job123.mp4",
        caption="caption",
        ig_user_id="ig123",
        page_access_token="page-tok",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result["status"] == "success"
    assert mock_get.call_count == 2
    mock_sleep.assert_called_once()


@patch("app.publishers.meta.get_tunnel_url", side_effect=RuntimeError("no tunnel url"))
def test_upload_to_instagram_returns_error_when_tunnel_unavailable(mock_tunnel):
    result = upload_to_instagram(
        video_filename="job123.mp4",
        caption="caption",
        ig_user_id="ig123",
        page_access_token="page-tok",
        tunnel_log_path="/tunnel-logs/tunnel.log",
    )

    assert result["platform"] == "instagram"
    assert result["status"] == "error"
    assert "no tunnel url" in result["error"]


@patch("app.publishers.meta.requests.post")
def test_upload_to_facebook_success(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_post.side_effect = [
        _resp({"video_id": "vid789", "upload_url": "https://rupload.facebook.com/xyz"}),
        _resp({}),
        _resp({"success": True}),
    ]

    result = upload_to_facebook(
        str(video_path),
        description="Why flamingos stand on one leg",
        page_id="page123",
        page_access_token="page-tok",
    )

    assert result == {
        "platform": "facebook",
        "status": "success",
        "video_id": "vid789",
    }

    upload_call = mock_post.call_args_list[1]
    assert upload_call.kwargs["headers"]["Authorization"] == "OAuth page-tok"
    finish_call = mock_post.call_args_list[2]
    assert finish_call.kwargs["data"]["video_id"] == "vid789"
    assert finish_call.kwargs["data"]["upload_phase"] == "finish"


@patch("app.publishers.meta.requests.post")
def test_upload_to_facebook_returns_error_dict_on_failure(mock_post, tmp_path):
    video_path = tmp_path / "video.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    mock_post.side_effect = Exception("start phase failed")

    result = upload_to_facebook(
        str(video_path), description="d", page_id="page123", page_access_token="tok"
    )

    assert result["platform"] == "facebook"
    assert result["status"] == "error"
    assert "start phase failed" in result["error"]
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/publishers/test_meta.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.publishers.meta'`

- [ ] **Step 3: Implementasyonu yaz**

`video-worker/app/publishers/meta.py`:
```python
import os
import time

import requests

from app.tunnel import get_tunnel_url

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
POLL_INTERVAL_SECONDS = 5
POLL_TIMEOUT_SECONDS = 120


def upload_to_instagram(
    video_filename: str,
    caption: str,
    ig_user_id: str,
    page_access_token: str,
    tunnel_log_path: str,
) -> dict:
    try:
        tunnel_url = get_tunnel_url(tunnel_log_path)
        video_url = f"{tunnel_url}/media/{video_filename}"

        create_response = requests.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": page_access_token,
            },
            timeout=30,
        )
        create_response.raise_for_status()
        creation_id = create_response.json()["id"]

        _wait_until_ready(creation_id, page_access_token)

        publish_response = requests.post(
            f"{GRAPH_API_BASE}/{ig_user_id}/media_publish",
            data={"creation_id": creation_id, "access_token": page_access_token},
            timeout=30,
        )
        publish_response.raise_for_status()
        media_id = publish_response.json()["id"]

        return {"platform": "instagram", "status": "success", "media_id": media_id}
    except Exception as exc:
        return {"platform": "instagram", "status": "error", "error": str(exc)}


def _wait_until_ready(creation_id: str, access_token: str) -> None:
    deadline = time.monotonic() + POLL_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        status_response = requests.get(
            f"{GRAPH_API_BASE}/{creation_id}",
            params={"fields": "status_code", "access_token": access_token},
            timeout=30,
        )
        status_response.raise_for_status()
        status_code = status_response.json()["status_code"]

        if status_code == "FINISHED":
            return
        if status_code == "ERROR":
            raise RuntimeError(f"Instagram container {creation_id} failed processing")

        time.sleep(POLL_INTERVAL_SECONDS)

    raise RuntimeError(
        f"Instagram container {creation_id} timed out waiting to process"
    )


def upload_to_facebook(
    video_path: str,
    description: str,
    page_id: str,
    page_access_token: str,
) -> dict:
    try:
        video_size = os.path.getsize(video_path)

        start_response = requests.post(
            f"{GRAPH_API_BASE}/{page_id}/video_reels",
            data={"upload_phase": "start", "access_token": page_access_token},
            timeout=30,
        )
        start_response.raise_for_status()
        start_data = start_response.json()
        video_id = start_data["video_id"]
        upload_url = start_data["upload_url"]

        with open(video_path, "rb") as video_file:
            video_bytes = video_file.read()

        upload_response = requests.post(
            upload_url,
            headers={
                "Authorization": f"OAuth {page_access_token}",
                "offset": "0",
                "file_size": str(video_size),
            },
            data=video_bytes,
            timeout=600,
        )
        upload_response.raise_for_status()

        finish_response = requests.post(
            f"{GRAPH_API_BASE}/{page_id}/video_reels",
            data={
                "upload_phase": "finish",
                "video_id": video_id,
                "video_state": "PUBLISHED",
                "description": description,
                "access_token": page_access_token,
            },
            timeout=30,
        )
        finish_response.raise_for_status()

        return {"platform": "facebook", "status": "success", "video_id": video_id}
    except Exception as exc:
        return {"platform": "facebook", "status": "error", "error": str(exc)}
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/publishers/test_meta.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add video-worker/app/publishers/meta.py video-worker/tests/publishers/test_meta.py
git commit -m "feat: add Meta publisher for Instagram and Facebook Reels

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 13: `/publish` ve `/cleanup` endpoint'leri — dört platformu birleştiren orkestrasyon

**Files:**
- Modify: `video-worker/app/main.py`
- Test: `video-worker/tests/test_publish_endpoint.py`

**Interfaces:**
- Consumes: `upload_to_youtube` (Task 10), `upload_to_tiktok` (Task 11), `upload_to_instagram`/`upload_to_facebook` (Task 12).
- Produces: `POST /publish` — body `{"video_path": str, "video_filename": str, "title": str, "description": str, "tags": list[str]}`, döner `{"results": [dict, dict, dict, dict]}` (her platformdan bir sonuç, sırayla youtube/tiktok/instagram/facebook, başarı/hata bağımsız). Yayın denemesi bitince video dosyasını siler. `DELETE /cleanup/{filename}` — dosyayı `config.MEDIA_DIR`'dan siler, path traversal'da 400.

- [ ] **Step 1: Failing test'i yaz**

`video-worker/tests/test_publish_endpoint.py`:
```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_calls_all_four_publishers_and_deletes_file(
    mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_yt.return_value = {
        "platform": "youtube", "status": "success", "video_id": "y1", "url": "u"
    }
    mock_tt.return_value = {
        "platform": "tiktok", "status": "success", "publish_id": "t1",
        "privacy_level": "SELF_ONLY",
    }
    mock_ig.return_value = {
        "platform": "instagram", "status": "success", "media_id": "i1"
    }
    mock_fb.return_value = {
        "platform": "facebook", "status": "success", "video_id": "f1"
    }

    response = client.post(
        "/publish",
        json={
            "video_path": str(video_path),
            "video_filename": "job123.mp4",
            "title": "Why Flamingos Stand on One Leg",
            "description": "desc",
            "tags": ["flamingo"],
        },
    )

    assert response.status_code == 200
    results = response.json()["results"]
    assert len(results) == 4
    assert {r["platform"] for r in results} == {
        "youtube", "tiktok", "instagram", "facebook"
    }
    assert not video_path.exists()

    assert mock_yt.call_args.kwargs["title"] == "Why Flamingos Stand on One Leg"
    assert mock_tt.call_args.kwargs["title"] == "Why Flamingos Stand on One Leg"
    assert mock_ig.call_args.kwargs["caption"] == "desc"
    assert mock_fb.call_args.kwargs["description"] == "desc"


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_continues_when_one_platform_fails(
    mock_yt, mock_tt, mock_ig, mock_fb, tmp_path
):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_yt.return_value = {
        "platform": "youtube", "status": "error", "error": "quota exceeded"
    }
    mock_tt.return_value = {
        "platform": "tiktok", "status": "success", "publish_id": "t1",
        "privacy_level": "SELF_ONLY",
    }
    mock_ig.return_value = {
        "platform": "instagram", "status": "success", "media_id": "i1"
    }
    mock_fb.return_value = {
        "platform": "facebook", "status": "success", "video_id": "f1"
    }

    response = client.post(
        "/publish",
        json={
            "video_path": str(video_path),
            "video_filename": "job123.mp4",
            "title": "t",
            "description": "d",
            "tags": [],
        },
    )

    results = response.json()["results"]
    assert len(results) == 4
    youtube_result = next(r for r in results if r["platform"] == "youtube")
    assert youtube_result["status"] == "error"


def test_cleanup_deletes_file(tmp_path):
    media_file = tmp_path / "reject-me.mp4"
    media_file.write_bytes(b"X")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.delete("/cleanup/reject-me.mp4")

    assert response.status_code == 200
    assert not media_file.exists()


def test_cleanup_rejects_path_traversal():
    response = client.delete("/cleanup/..%2F..%2Fetc%2Fpasswd")
    assert response.status_code == 400
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_publish_endpoint.py -v`
Expected: FAIL — `404 Not Found` for `/publish` (route yok)

- [ ] **Step 3: main.py'ye `/publish` ve `/cleanup` endpoint'lerini ekle**

`video-worker/app/main.py`:
```python
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import config
from app.pipeline import generate_video
from app.publishers.meta import upload_to_facebook, upload_to_instagram
from app.publishers.tiktok import upload_to_tiktok
from app.publishers.youtube import upload_to_youtube

app = FastAPI(title="video-worker")


class PublishRequest(BaseModel):
    video_path: str
    video_filename: str
    title: str
    description: str
    tags: list[str] = []


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/generate")
async def generate():
    job_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    try:
        return await generate_video(job_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/media/{filename}")
def get_media(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    file_path = Path(config.MEDIA_DIR) / filename
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="not found")

    return FileResponse(str(file_path), media_type="video/mp4")


@app.post("/publish")
def publish(payload: PublishRequest):
    results = [
        upload_to_youtube(
            payload.video_path,
            title=payload.title,
            description=payload.description,
            tags=payload.tags,
            client_id=config.YOUTUBE_CLIENT_ID,
            client_secret=config.YOUTUBE_CLIENT_SECRET,
            refresh_token=config.YOUTUBE_REFRESH_TOKEN,
        ),
        upload_to_tiktok(
            payload.video_path,
            title=payload.title,
            client_key=config.TIKTOK_CLIENT_KEY,
            client_secret=config.TIKTOK_CLIENT_SECRET,
            token_path=config.TIKTOK_TOKEN_PATH,
            audited=config.TIKTOK_AUDITED,
        ),
        upload_to_instagram(
            payload.video_filename,
            caption=payload.description,
            ig_user_id=config.META_IG_USER_ID,
            page_access_token=config.META_PAGE_ACCESS_TOKEN,
            tunnel_log_path=config.TUNNEL_LOG_PATH,
        ),
        upload_to_facebook(
            payload.video_path,
            description=payload.description,
            page_id=config.META_PAGE_ID,
            page_access_token=config.META_PAGE_ACCESS_TOKEN,
        ),
    ]

    Path(payload.video_path).unlink(missing_ok=True)

    return {"results": results}


@app.delete("/cleanup/{filename}")
def cleanup(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=400, detail="invalid filename")

    file_path = Path(config.MEDIA_DIR) / filename
    file_path.unlink(missing_ok=True)

    return {"status": "deleted", "filename": filename}
```

- [ ] **Step 4: Testlerin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/ -v`
Expected: PASS (tüm testler yeşil — video-worker artık tamamlandı)

- [ ] **Step 5: Commit**

```bash
git add video-worker/app/main.py video-worker/tests/test_publish_endpoint.py
git commit -m "feat: add /publish and /cleanup endpoints wiring all four platform publishers

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 14: Bekleyen iş durumu — `pending.json` + `GET /pending`

n8n'de "günlük üretim" ve "Telegram onayı" iki AYRI workflow olacak (Task 15/16) — çünkü n8n'in Cron ve Telegram Trigger'ı aynı workflow içinde uzun süre "beklet" ile birleştirmek kırılgan. Bu iki workflow arasında video-worker, "şu an onay bekleyen iş budur" bilgisini `pending.json` dosyasıyla taşır.

**Files:**
- Modify: `video-worker/app/pipeline.py`
- Modify: `video-worker/app/main.py`
- Test: `video-worker/tests/test_pipeline_pending.py`
- Test: `video-worker/tests/test_pending_endpoint.py`

**Interfaces:**
- Produces: `GET /pending` — `config.MEDIA_DIR/pending.json` içeriğini JSON olarak döner, dosya yoksa 404. `/generate` artık aynı içeriği `pending.json`'a da yazıyor. `/publish` ve `/cleanup` işlem sonunda `pending.json`'ı siliyor.

- [ ] **Step 1: Failing pipeline testini yaz**

`video-worker/tests/test_pipeline_pending.py`:
```python
import json
from unittest.mock import patch, AsyncMock

from app.pipeline import generate_video


@patch("app.pipeline.render_video")
@patch("app.pipeline.write_srt")
@patch("app.pipeline.fetch_stock_clips")
@patch("app.pipeline.synthesize_speech", new_callable=AsyncMock)
@patch("app.pipeline.generate_script")
@patch("app.pipeline.select_next_topic")
async def test_generate_video_writes_pending_json(
    mock_topic, mock_script, mock_tts, mock_clips, mock_srt, mock_render, tmp_path
):
    mock_topic.return_value = "Topic"
    mock_script.return_value = {
        "script": "text", "title": "Title", "description": "Desc", "tags": ["a"]
    }
    mock_tts.return_value = [{"offset": 0, "duration": 1, "text": "x"}]
    mock_clips.return_value = ["/work/clip_0.mp4"]
    mock_srt.return_value = "/work/subs.srt"
    mock_render.side_effect = lambda *a, **k: a[3]

    with patch("app.pipeline.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.OPENROUTER_API_KEY = "or-key"
        mock_config.PEXELS_API_KEY = "px-key"
        result = await generate_video("job789")

    pending_path = tmp_path / "pending.json"
    assert pending_path.exists()
    assert json.loads(pending_path.read_text(encoding="utf-8")) == result
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_pipeline_pending.py -v`
Expected: FAIL — `pending.json` oluşturulmamış (`assert False`)

- [ ] **Step 3: pipeline.py'yi güncelle**

`video-worker/app/pipeline.py` — dosyanın başına `import json` ekle, `try` bloğunun sonundaki `return {...}` ifadesini değiştir (girinti aynı kalır, hâlâ `try` içinde — böylece `pending.json` sadece başarılı üretimde yazılır, `finally` bloğu `work_dir`'i her koşulda temizlemeye devam eder):
```python
        result = {
            "job_id": job_id,
            "video_path": video_path,
            "video_filename": video_filename,
            "topic": topic,
            "title": script_data["title"],
            "description": script_data["description"],
            "tags": script_data["tags"],
        }
        (media_dir / "pending.json").write_text(
            json.dumps(result), encoding="utf-8"
        )
        return result
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_pipeline_pending.py -v`
Expected: PASS

- [ ] **Step 5: Failing `/pending` endpoint testlerini yaz**

`video-worker/tests/test_pending_endpoint.py`:
```python
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_get_pending_returns_stored_job(tmp_path):
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(
        json.dumps({"job_id": "job1", "title": "t"}), encoding="utf-8"
    )

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/pending")

    assert response.status_code == 200
    assert response.json() == {"job_id": "job1", "title": "t"}


def test_get_pending_returns_404_when_none(tmp_path):
    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        response = client.get("/pending")

    assert response.status_code == 404


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_clears_pending_json(mock_yt, mock_tt, mock_ig, mock_fb, tmp_path):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(json.dumps({"job_id": "job123"}), encoding="utf-8")

    mock_yt.return_value = {"platform": "youtube", "status": "success"}
    mock_tt.return_value = {"platform": "tiktok", "status": "success"}
    mock_ig.return_value = {"platform": "instagram", "status": "success"}
    mock_fb.return_value = {"platform": "facebook", "status": "success"}

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.YOUTUBE_CLIENT_ID = ""
        mock_config.YOUTUBE_CLIENT_SECRET = ""
        mock_config.YOUTUBE_REFRESH_TOKEN = ""
        mock_config.TIKTOK_CLIENT_KEY = ""
        mock_config.TIKTOK_CLIENT_SECRET = ""
        mock_config.TIKTOK_TOKEN_PATH = ""
        mock_config.TIKTOK_AUDITED = False
        mock_config.META_IG_USER_ID = ""
        mock_config.META_PAGE_ACCESS_TOKEN = ""
        mock_config.TUNNEL_LOG_PATH = ""
        mock_config.META_PAGE_ID = ""
        client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job123.mp4",
                "title": "t",
                "description": "d",
                "tags": [],
            },
        )

    assert not pending_path.exists()


def test_cleanup_clears_pending_json(tmp_path):
    media_file = tmp_path / "reject-me.mp4"
    media_file.write_bytes(b"X")
    pending_path = tmp_path / "pending.json"
    pending_path.write_text(json.dumps({"job_id": "job1"}), encoding="utf-8")

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        client.delete("/cleanup/reject-me.mp4")

    assert not pending_path.exists()
```

- [ ] **Step 6: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_pending_endpoint.py -v`
Expected: FAIL — `404 Not Found` için `/pending` route'u henüz yok (test'in kendisi 404 beklediği için ilk iki test yanlışlıkla geçebilir ama son iki test `pending.json`'ın hâlâ var olduğunu görüp fail eder)

- [ ] **Step 7: main.py'ye `/pending` route'unu ekle ve publish/cleanup'ı güncelle**

`video-worker/app/main.py` — dosyanın başına `import json` ekle, aşağıdaki route'u ekle:
```python
@app.get("/pending")
def get_pending():
    pending_path = Path(config.MEDIA_DIR) / "pending.json"
    if not pending_path.is_file():
        raise HTTPException(status_code=404, detail="no pending job")
    return json.loads(pending_path.read_text(encoding="utf-8"))
```

`publish()` fonksiyonundaki dosya silme satırını genişlet:
```python
    Path(payload.video_path).unlink(missing_ok=True)
    (Path(config.MEDIA_DIR) / "pending.json").unlink(missing_ok=True)

    return {"results": results}
```

`cleanup()` fonksiyonuna ekle:
```python
    file_path = Path(config.MEDIA_DIR) / filename
    file_path.unlink(missing_ok=True)
    (Path(config.MEDIA_DIR) / "pending.json").unlink(missing_ok=True)

    return {"status": "deleted", "filename": filename}
```

- [ ] **Step 8: Testlerin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/ -v`
Expected: PASS — tüm video-worker testleri yeşil (video-worker artık tamamen bitti)

- [ ] **Step 9: Commit**

```bash
git add video-worker/app/pipeline.py video-worker/app/main.py video-worker/tests/test_pipeline_pending.py video-worker/tests/test_pending_endpoint.py
git commit -m "feat: persist pending job state for cross-workflow Telegram approval

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 15: Yayın geçmişi loglama + haftalık analiz raporu

**Files:**
- Create: `video-worker/app/publish_log.py`
- Create: `video-worker/app/analytics.py`
- Modify: `video-worker/app/main.py`
- Test: `video-worker/tests/test_publish_log.py`
- Test: `video-worker/tests/test_analytics.py`
- Test: `video-worker/tests/test_publish_logging.py`
- Test: `video-worker/tests/test_analytics_endpoint.py`

**Interfaces:**
- Produces: `append_publish_log(log_path: str, entry: dict) -> None`, `load_recent_entries(log_path: str, since_iso: str) -> list[dict]`.
- Produces: `build_weekly_report(log_path: str, youtube_creds: dict, meta_creds: dict) -> str` — Türkçe formatlanmış özet metin döner.
- Produces: `GET /analytics/weekly` → `{"report": str}`. `/publish` artık her çağrıda `{MEDIA_DIR}/published_log.json`'a bir kayıt ekliyor.

- [ ] **Step 1: Failing publish_log testini yaz**

`video-worker/tests/test_publish_log.py`:
```python
import json

from app.publish_log import append_publish_log, load_recent_entries


def test_append_publish_log_creates_file_when_missing(tmp_path):
    log_path = tmp_path / "log.json"

    append_publish_log(
        str(log_path), {"published_at": "2026-09-03T09:00:00+00:00", "title": "A"}
    )

    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert entries == [{"published_at": "2026-09-03T09:00:00+00:00", "title": "A"}]


def test_append_publish_log_appends_to_existing_file(tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps([{"published_at": "2026-09-01T09:00:00+00:00", "title": "Old"}]),
        encoding="utf-8",
    )

    append_publish_log(
        str(log_path), {"published_at": "2026-09-03T09:00:00+00:00", "title": "New"}
    )

    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(entries) == 2
    assert entries[1]["title"] == "New"


def test_load_recent_entries_filters_by_date(tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps(
            [
                {"published_at": "2026-08-20T09:00:00+00:00", "title": "TooOld"},
                {"published_at": "2026-09-02T09:00:00+00:00", "title": "Recent"},
            ]
        ),
        encoding="utf-8",
    )

    result = load_recent_entries(str(log_path), since_iso="2026-08-27T00:00:00+00:00")

    assert [e["title"] for e in result] == ["Recent"]


def test_load_recent_entries_returns_empty_when_file_missing(tmp_path):
    result = load_recent_entries(
        str(tmp_path / "missing.json"), since_iso="2026-08-27T00:00:00+00:00"
    )
    assert result == []
```

- [ ] **Step 2: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_publish_log.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.publish_log'`

- [ ] **Step 3: publish_log.py'yi yaz**

`video-worker/app/publish_log.py`:
```python
import json
from pathlib import Path


def append_publish_log(log_path: str, entry: dict) -> None:
    path = Path(log_path)
    if path.is_file():
        entries = json.loads(path.read_text(encoding="utf-8"))
    else:
        entries = []
    entries.append(entry)
    path.write_text(
        json.dumps(entries, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_recent_entries(log_path: str, since_iso: str) -> list[dict]:
    path = Path(log_path)
    if not path.is_file():
        return []
    entries = json.loads(path.read_text(encoding="utf-8"))
    return [e for e in entries if e["published_at"] >= since_iso]
```

- [ ] **Step 4: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_publish_log.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Failing analytics testini yaz**

`video-worker/tests/test_analytics.py`:
```python
import json
from datetime import datetime, timezone
from unittest.mock import patch, Mock

from app.analytics import build_weekly_report


def _resp(json_data):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = json_data
    return resp


def test_build_weekly_report_returns_message_when_no_entries(tmp_path):
    log_path = tmp_path / "log.json"

    report = build_weekly_report(
        str(log_path),
        youtube_creds={"client_id": "c", "client_secret": "s", "refresh_token": "r"},
        meta_creds={"page_access_token": "t"},
    )

    assert report == "Son 7 günde yayınlanan video yok."


@patch("app.analytics.requests.get")
@patch("app.analytics.get_youtube_access_token", return_value="yt-access-tok")
def test_build_weekly_report_includes_platform_stats(mock_token, mock_get, tmp_path):
    log_path = tmp_path / "log.json"
    log_path.write_text(
        json.dumps(
            [
                {
                    "published_at": datetime.now(timezone.utc).isoformat(),
                    "title": "Why Flamingos Stand on One Leg",
                    "platforms": {
                        "youtube": {
                            "platform": "youtube", "status": "success", "video_id": "yt1"
                        },
                        "instagram": {
                            "platform": "instagram", "status": "success", "media_id": "ig1"
                        },
                        "facebook": {
                            "platform": "facebook", "status": "success", "video_id": "fb1"
                        },
                        "tiktok": {
                            "platform": "tiktok", "status": "success",
                            "publish_id": "tt1", "privacy_level": "SELF_ONLY",
                        },
                    },
                }
            ]
        ),
        encoding="utf-8",
    )

    mock_get.side_effect = [
        _resp(
            {"items": [{"statistics": {"viewCount": "1000", "likeCount": "50", "commentCount": "5"}}]}
        ),
        _resp({"data": [{"name": "plays", "values": [{"value": 200}]}]}),
        _resp({"id": "fb1", "views": 75}),
    ]

    report = build_weekly_report(
        str(log_path),
        youtube_creds={"client_id": "c", "client_secret": "s", "refresh_token": "r"},
        meta_creds={"page_access_token": "t"},
    )

    assert "Why Flamingos Stand on One Leg" in report
    assert "1000 views" in report
    assert "200 plays" in report
    assert "TikTok" in report
```

- [ ] **Step 6: Testin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_analytics.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.analytics'`

- [ ] **Step 7: analytics.py'yi yaz**

`video-worker/app/analytics.py`:
```python
from datetime import datetime, timedelta, timezone

import requests

from app.publish_log import load_recent_entries
from app.publishers.youtube import get_access_token as get_youtube_access_token

YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"
GRAPH_API_BASE = "https://graph.facebook.com/v19.0"


def build_weekly_report(log_path: str, youtube_creds: dict, meta_creds: dict) -> str:
    since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
    entries = load_recent_entries(log_path, since_iso=since)

    if not entries:
        return "Son 7 günde yayınlanan video yok."

    lines = [f"📊 Haftalık Rapor ({len(entries)} video)\n"]
    for entry in entries:
        lines.append(f"🎬 {entry['title']}")
        platforms = entry.get("platforms", {})

        youtube = platforms.get("youtube")
        if youtube and youtube.get("status") == "success":
            stats = _fetch_youtube_stats(youtube["video_id"], youtube_creds)
            lines.append(
                f"  YouTube: {stats.get('views', '?')} views, "
                f"{stats.get('likes', '?')} likes, {stats.get('comments', '?')} comments"
            )

        instagram = platforms.get("instagram")
        if instagram and instagram.get("status") == "success":
            stats = _fetch_instagram_stats(instagram["media_id"], meta_creds)
            lines.append(
                f"  Instagram: {stats.get('plays', '?')} plays, "
                f"{stats.get('likes', '?')} likes, {stats.get('comments', '?')} comments"
            )

        facebook = platforms.get("facebook")
        if facebook and facebook.get("status") == "success":
            stats = _fetch_facebook_stats(facebook["video_id"], meta_creds)
            lines.append(f"  Facebook: {stats.get('views', '?')} views")

        tiktok = platforms.get("tiktok")
        if tiktok and tiktok.get("status") == "success":
            lines.append(
                f"  TikTok: {tiktok.get('privacy_level')} — istatistik için "
                "TikTok uygulamasını kontrol edin (Query API audit sonrası eklenecek)"
            )

        lines.append("")

    return "\n".join(lines)


def _fetch_youtube_stats(video_id: str, creds: dict) -> dict:
    access_token = get_youtube_access_token(
        creds["client_id"], creds["client_secret"], creds["refresh_token"]
    )
    response = requests.get(
        YOUTUBE_VIDEOS_URL,
        params={"part": "statistics", "id": video_id},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if not items:
        return {}
    stats = items[0]["statistics"]
    return {
        "views": stats.get("viewCount", "0"),
        "likes": stats.get("likeCount", "0"),
        "comments": stats.get("commentCount", "0"),
    }


def _fetch_instagram_stats(media_id: str, creds: dict) -> dict:
    response = requests.get(
        f"{GRAPH_API_BASE}/{media_id}/insights",
        params={
            "metric": "plays,likes,comments,shares,saved",
            "access_token": creds["page_access_token"],
        },
        timeout=30,
    )
    response.raise_for_status()
    result = {}
    for item in response.json().get("data", []):
        values = item.get("values", [])
        if values:
            result[item["name"]] = values[0].get("value", 0)
    return result


def _fetch_facebook_stats(video_id: str, creds: dict) -> dict:
    response = requests.get(
        f"{GRAPH_API_BASE}/{video_id}",
        params={"fields": "views", "access_token": creds["page_access_token"]},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()
```

- [ ] **Step 8: Testin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_analytics.py -v`
Expected: PASS (2 passed)

- [ ] **Step 9: `/publish`'in log tutmasını ve `/analytics/weekly` endpoint'ini test eden failing testleri yaz**

`video-worker/tests/test_publish_logging.py`:
```python
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.upload_to_facebook")
@patch("app.main.upload_to_instagram")
@patch("app.main.upload_to_tiktok")
@patch("app.main.upload_to_youtube")
def test_publish_appends_to_log(mock_yt, mock_tt, mock_ig, mock_fb, tmp_path):
    video_path = tmp_path / "job123.mp4"
    video_path.write_bytes(b"FAKEVIDEO")

    mock_yt.return_value = {
        "platform": "youtube", "status": "success", "video_id": "yt1"
    }
    mock_tt.return_value = {
        "platform": "tiktok", "status": "success", "publish_id": "tt1"
    }
    mock_ig.return_value = {
        "platform": "instagram", "status": "success", "media_id": "ig1"
    }
    mock_fb.return_value = {
        "platform": "facebook", "status": "success", "video_id": "fb1"
    }

    with patch("app.main.config") as mock_config:
        mock_config.MEDIA_DIR = str(tmp_path)
        mock_config.YOUTUBE_CLIENT_ID = ""
        mock_config.YOUTUBE_CLIENT_SECRET = ""
        mock_config.YOUTUBE_REFRESH_TOKEN = ""
        mock_config.TIKTOK_CLIENT_KEY = ""
        mock_config.TIKTOK_CLIENT_SECRET = ""
        mock_config.TIKTOK_TOKEN_PATH = ""
        mock_config.TIKTOK_AUDITED = False
        mock_config.META_IG_USER_ID = ""
        mock_config.META_PAGE_ACCESS_TOKEN = ""
        mock_config.TUNNEL_LOG_PATH = ""
        mock_config.META_PAGE_ID = ""
        client.post(
            "/publish",
            json={
                "video_path": str(video_path),
                "video_filename": "job123.mp4",
                "title": "Why Flamingos Stand on One Leg",
                "description": "d",
                "tags": [],
            },
        )

    log_path = tmp_path / "published_log.json"
    assert log_path.exists()
    entries = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(entries) == 1
    assert entries[0]["title"] == "Why Flamingos Stand on One Leg"
    assert entries[0]["platforms"]["youtube"]["video_id"] == "yt1"
```

`video-worker/tests/test_analytics_endpoint.py`:
```python
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@patch("app.main.build_weekly_report", return_value="📊 Haftalık Rapor...")
def test_analytics_weekly_returns_report(mock_report):
    response = client.get("/analytics/weekly")

    assert response.status_code == 200
    assert response.json() == {"report": "📊 Haftalık Rapor..."}
```

- [ ] **Step 10: Testlerin fail ettiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/test_publish_logging.py tests/test_analytics_endpoint.py -v`
Expected: FAIL — log dosyası oluşmuyor, `/analytics/weekly` 404

- [ ] **Step 11: main.py'yi güncelle**

Importlara ekle:
```python
from app.analytics import build_weekly_report
from app.publish_log import append_publish_log
```

`publish()` fonksiyonunda `results` listesinden hemen sonra, dosya silmeden önce:
```python
    entry = {
        "published_at": datetime.now(timezone.utc).isoformat(),
        "title": payload.title,
        "platforms": {r["platform"]: r for r in results},
    }
    append_publish_log(str(Path(config.MEDIA_DIR) / "published_log.json"), entry)

    Path(payload.video_path).unlink(missing_ok=True)
    (Path(config.MEDIA_DIR) / "pending.json").unlink(missing_ok=True)

    return {"results": results}
```

Yeni endpoint ekle:
```python
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
```

- [ ] **Step 12: Tüm testlerin geçtiğini doğrula**

Run: `docker compose run --rm video-worker pytest tests/ -v`
Expected: PASS — video-worker'ın tüm testleri yeşil (yaklaşık 50 test)

- [ ] **Step 13: Commit**

```bash
git add video-worker/app/publish_log.py video-worker/app/analytics.py video-worker/app/main.py video-worker/tests/test_publish_log.py video-worker/tests/test_analytics.py video-worker/tests/test_publish_logging.py video-worker/tests/test_analytics_endpoint.py
git commit -m "feat: add publish history logging and weekly analytics report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 16: n8n Workflow A — "Daily Video Pipeline" (üretim + Telegram onay isteği)

video-worker artık tamamlandı. Bu task'tan itibaren n8n arayüzünde (http://localhost:5678) elle workflow kurulacak — n8n workflow'ları kod deposunda tutulmadığı için (n8n kendi SQLite veritabanında saklar), her node'un tam ayarları burada adım adım verilmiştir. Bu workflow, `n8n` ve `video-worker` container'larının ayakta olmasını gerektirir.

**Ön koşul:** `docker compose up -d n8n video-worker cloudflared` çalıştırılmış ve `.env` içinde en azından `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `OPENROUTER_API_KEY`, `PEXELS_API_KEY` doldurulmuş olmalı (bkz. Task 19-20).

- [ ] **Step 1: n8n'de Telegram credential'ı oluştur**

http://localhost:5678 → Credentials → New → "Telegram API" ara → Access Token alanına `.env`'deki `TELEGRAM_BOT_TOKEN` değerini gir → Save, adını `Telegram - Otomasyon Bot` yap.

- [ ] **Step 2: Yeni workflow oluştur, adı "Daily Video Pipeline"**

- [ ] **Step 3: Schedule Trigger node'unu ekle**

Node type: `Schedule Trigger`
Ayarlar: Trigger Interval → **Days**, Days Between Triggers: `1`, Trigger at Hour: `9`, Trigger at Minute: `0`

- [ ] **Step 4: "Generate Video" HTTP Request node'unu ekle (Schedule Trigger'a bağla)**

Node type: `HTTP Request`, adı `Generate Video`
- Method: `POST`
- URL: `={{$env.VIDEO_WORKER_URL}}/generate`
- Options → Timeout: `300000`
- Settings sekmesi → **On Error: Continue (using error output)** — video-worker `/generate`'de hata (500) dönerse workflow durmasın, ayrı bir hata dalına düşsün (spec Bölüm 5: üretim hatası Telegram'a bildirilmeli).

- [ ] **Step 5: "Send Generation Error" Telegram node'unu ekle (Generate Video'nun hata çıkışına bağla)**

Node type: `Telegram`, adı `Send Generation Error`
- Credential: `Telegram - Otomasyon Bot`
- Resource: `Message`, Operation: `Send Message`
- Chat Id: `={{$env.TELEGRAM_CHAT_ID}}`
- Text: `=⚠️ Bugün video üretilemedi: {{$json.error?.message || $json.message || 'bilinmeyen hata'}}`

- [ ] **Step 6: "Download Video File" HTTP Request node'unu ekle (Generate Video'nun BAŞARI çıkışına bağla)**

Node type: `HTTP Request`, adı `Download Video File`
- Method: `GET`
- URL: `={{$env.VIDEO_WORKER_URL}}/media/{{$json.video_filename}}`
- Options → Response → Response Format: `File`
- Options → Response → Put Output File in Field: `data`

- [ ] **Step 7: "Send Approval Request" Telegram node'unu ekle (Download Video File'a bağla)**

Node type: `Telegram`, adı `Send Approval Request`
- Credential: `Telegram - Otomasyon Bot`
- Resource: `Message`
- Operation: `Send Video`
- Chat Id: `={{$env.TELEGRAM_CHAT_ID}}`
- Binary Data: açık (On)
- Input Binary Field: `data`
- Caption: `={{$('Generate Video').item.json.title}}\n\n{{$('Generate Video').item.json.description}}`
- Reply Markup: `Inline Keyboard`
  - Row 1, Button 1: Text `✅ Onayla`, Additional Fields → Callback Data: `approve`
  - Row 1, Button 2: Text `❌ Reddet`, Additional Fields → Callback Data: `reject`

- [ ] **Step 8: Workflow'u kaydet ve Active yap**

Sağ üstteki toggle'ı "Active" konumuna getir (aksi halde Schedule Trigger tetiklenmez).

- [ ] **Step 9: Manuel test — başarılı üretim akışı**

n8n arayüzünde "Execute Workflow" butonuna bas (Schedule Trigger'ı manuel tetikler).
Expected:
- Her node yeşil tik alır (~1-3 dakika sürebilir, script+TTS+render+stok video indirme içeriyor)
- Telegram'da video mesajı + başlık/açıklama + 2 buton görünür
- `docker compose exec video-worker cat /data/media/pending.json` komutu üretilen job'un JSON'unu gösterir

- [ ] **Step 10: Manuel test — üretim hatası akışı**

`.env`'de `PEXELS_API_KEY`'i geçici olarak bozuk bir değerle değiştir (`docker compose restart video-worker`), workflow'u tekrar elle çalıştır.
Expected: `Generate Video` node'u hata çıkışına düşer, Telegram'a "⚠️ Bugün video üretilemedi: ..." mesajı gelir. Testten sonra `PEXELS_API_KEY`'i doğru değerine geri al ve `docker compose restart video-worker` çalıştır.

- [ ] **Step 11: Commit**

n8n workflow'ları git'e otomatik yazılmaz (n8n kendi veritabanında tutar); ilerleme kaydı olarak README'ye not düş:

```bash
cat >> README.md << 'EOF'

## n8n Workflow'ları (manuel kurulum, http://localhost:5678 üzerinden)
- **Daily Video Pipeline** — Schedule Trigger (09:00) → Generate Video (hata → Send Generation Error) → Download Video File → Send Approval Request (Telegram, inline onay butonları)
EOF
git add README.md
git commit -m "docs: record Daily Video Pipeline n8n workflow setup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 17: n8n Workflow B — "Approval Handler" (Telegram callback → publish/cleanup)

**Files:** n8n arayüzünde manuel kurulum (kod deposu dosyası yok).

- [ ] **Step 1: Yeni workflow oluştur, adı "Approval Handler"**

- [ ] **Step 2: Telegram Trigger node'unu ekle**

Node type: `Telegram Trigger`
- Credential: `Telegram - Otomasyon Bot`
- Updates: `callback_query`

- [ ] **Step 3: "Acknowledge Callback" HTTP Request node'unu ekle (Telegram Trigger'a bağla)**

Telegram'ın buton üzerinde sonsuz "yükleniyor" göstermemesi için callback her zaman anında onaylanmalı — bunu n8n'in Telegram node'u yerine doğrudan Bot API ile yapıyoruz (sürüm bağımsız, garanti çalışır).

Node type: `HTTP Request`, adı `Acknowledge Callback`
- Method: `POST`
- URL: `=https://api.telegram.org/bot{{$env.TELEGRAM_BOT_TOKEN}}/answerCallbackQuery`
- Body Content Type: `JSON`
- Body: `={{ { callback_query_id: $json.callback_query.id } }}`

- [ ] **Step 4: "Is Approve" IF node'unu ekle (Acknowledge Callback'e bağla)**

Node type: `IF`, adı `Is Approve`
- Condition: String → `{{$json.callback_query.data}}` **equals** `approve`

- [ ] **Step 5: TRUE dalı — "Fetch Pending Job" HTTP Request node'unu ekle**

Node type: `HTTP Request`, adı `Fetch Pending Job`
- Method: `GET`
- URL: `={{$env.VIDEO_WORKER_URL}}/pending`

- [ ] **Step 6: TRUE dalı — "Publish" HTTP Request node'unu ekle (Fetch Pending Job'a bağla)**

Node type: `HTTP Request`, adı `Publish`
- Method: `POST`
- URL: `={{$env.VIDEO_WORKER_URL}}/publish`
- Body Content Type: `JSON`
- Body: `={{ { video_path: $json.video_path, video_filename: $json.video_filename, title: $json.title, description: $json.description, tags: $json.tags } }}`
- Options → Timeout: `300000`

- [ ] **Step 7: TRUE dalı — "Format Summary" Code node'unu ekle (Publish'e bağla)**

Node type: `Code`, adı `Format Summary`, Language: `JavaScript`
```javascript
const results = $input.first().json.results;
const lines = results.map((r) => {
  if (r.status === "success") {
    return `✅ ${r.platform}: başarılı`;
  }
  return `❌ ${r.platform}: ${r.error}`;
});
return [{ json: { summary: lines.join("\n") } }];
```

- [ ] **Step 8: TRUE dalı — "Send Summary" Telegram node'unu ekle (Format Summary'e bağla)**

Node type: `Telegram`, adı `Send Summary`
- Credential: `Telegram - Otomasyon Bot`
- Resource: `Message`, Operation: `Send Message`
- Chat Id: `={{$env.TELEGRAM_CHAT_ID}}`
- Text: `={{$json.summary}}`

- [ ] **Step 9: FALSE dalı — "Fetch Pending Job (Reject)" HTTP Request node'unu ekle (Is Approve'un FALSE çıkışına bağla)**

Node type: `HTTP Request`, adı `Fetch Pending Job (Reject)`
- Method: `GET`
- URL: `={{$env.VIDEO_WORKER_URL}}/pending`

- [ ] **Step 10: FALSE dalı — "Cleanup" HTTP Request node'unu ekle (Fetch Pending Job (Reject)'e bağla)**

Node type: `HTTP Request`, adı `Cleanup`
- Method: `DELETE`
- URL: `={{$env.VIDEO_WORKER_URL}}/cleanup/{{$json.video_filename}}`

- [ ] **Step 11: FALSE dalı — "Send Reject Notice" Telegram node'unu ekle (Cleanup'a bağla)**

Node type: `Telegram`, adı `Send Reject Notice`
- Credential: `Telegram - Otomasyon Bot`
- Resource: `Message`, Operation: `Send Message`
- Chat Id: `={{$env.TELEGRAM_CHAT_ID}}`
- Text: `❌ İptal edildi, yarın yeni video denenecek.`

- [ ] **Step 12: Workflow'u kaydet ve Active yap**

- [ ] **Step 13: Manuel test — onaylama akışı**

Task 16'daki "Daily Video Pipeline"ı elle bir kez daha çalıştırıp Telegram'a yeni bir onay mesajı düşür, mesajdaki **✅ Onayla** butonuna bas.
Expected:
- n8n'de "Approval Handler" workflow'u otomatik tetiklenir, tüm node'lar yeşil tik alır
- Telegram'da 4 platformun sonucunu özetleyen bir mesaj gelir (ilk denemede TikTok/Instagram/Facebook/YouTube kimlik bilgileri henüz girilmediyse hepsi ❌ hata gösterir — bu normaldir, kimlik bilgileri Task 20-22'de eklenecek)
- `docker compose exec video-worker ls /data/media` içinde video dosyası ve `pending.json` artık yok

- [ ] **Step 14: Manuel test — reddetme akışı**

Workflow A'yı tekrar elle çalıştır, bu sefer **❌ Reddet** butonuna bas.
Expected: Telegram'da "İptal edildi" mesajı gelir, `docker compose exec video-worker ls /data/media` içinde video dosyası ve `pending.json` yok.

- [ ] **Step 15: Commit**

```bash
cat >> README.md << 'EOF'
- **Approval Handler** — Telegram Trigger (callback_query) → Acknowledge Callback → Is Approve? → [true: Fetch Pending Job → Publish → Format Summary → Send Summary] / [false: Fetch Pending Job (Reject) → Cleanup → Send Reject Notice]
EOF
git add README.md
git commit -m "docs: record Approval Handler n8n workflow setup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 18: n8n Workflow C — "Weekly Analytics Report"

**Files:** n8n arayüzünde manuel kurulum.

- [ ] **Step 1: Yeni workflow oluştur, adı "Weekly Analytics Report"**

- [ ] **Step 2: Schedule Trigger node'unu ekle**

Node type: `Schedule Trigger`
- Trigger Interval: `Weeks`, Trigger on Weekday: `Monday`, Trigger at Hour: `10`, Trigger at Minute: `0`

- [ ] **Step 3: "Fetch Weekly Report" HTTP Request node'unu ekle (Schedule Trigger'a bağla)**

Node type: `HTTP Request`, adı `Fetch Weekly Report`
- Method: `GET`
- URL: `={{$env.VIDEO_WORKER_URL}}/analytics/weekly`
- Options → Timeout: `60000`

- [ ] **Step 4: "Send Report" Telegram node'unu ekle (Fetch Weekly Report'a bağla)**

Node type: `Telegram`, adı `Send Report`
- Credential: `Telegram - Otomasyon Bot`
- Resource: `Message`, Operation: `Send Message`
- Chat Id: `={{$env.TELEGRAM_CHAT_ID}}`
- Text: `={{$json.report}}`

- [ ] **Step 5: Workflow'u kaydet ve Active yap**

- [ ] **Step 6: Manuel test**

"Execute Workflow" ile elle tetikle.
Expected: Telegram'a "Son 7 günde yayınlanan video yok." (henüz hiç video yayınlanmadıysa) veya gerçek istatistik özeti içeren bir mesaj gelir.

- [ ] **Step 7: Commit**

```bash
cat >> README.md << 'EOF'
- **Weekly Analytics Report** — Schedule Trigger (Pazartesi 10:00) → Fetch Weekly Report → Send Report (Telegram)
EOF
git add README.md
git commit -m "docs: record Weekly Analytics Report n8n workflow setup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 19: Telegram bot chat_id doğrulama

**Files:** Modify: `.env` (kod deposuna girmez, `.gitignore`'da).

- [ ] **Step 1: Bot'a bir mesaj gönder**

Telegram'da BotFather'dan aldığın bot'u ara, `/start` yaz ve gönder.

- [ ] **Step 2: chat_id'yi getUpdates ile öğren**

Run:
```bash
curl "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/getUpdates"
```
Yanıttaki `"message":{"chat":{"id": <SAYI>, ...}}` alanındaki sayı senin `TELEGRAM_CHAT_ID`'in.

- [ ] **Step 3: .env dosyasını doldur**

`.env.example`'ı `.env` olarak kopyala, `TELEGRAM_BOT_TOKEN` ve `TELEGRAM_CHAT_ID` alanlarını doldur.

- [ ] **Step 4: Doğrula**

Run:
```bash
curl -X POST "https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/sendMessage" -d "chat_id=<TELEGRAM_CHAT_ID>&text=test"
```
Expected: Telegram'da bot'tan "test" mesajı gelir.

---

## Task 20: Pexels API key

- [ ] **Step 1: API key al**

https://www.pexels.com/api/ → "Get Started" → ücretsiz hesap oluştur/giriş yap → API key otomatik üretilir (onay beklemeye gerek yok, anında aktif).

- [ ] **Step 2: .env'e ekle**

`.env` dosyasında `PEXELS_API_KEY` değerini doldur.

- [ ] **Step 3: Doğrula**

Run:
```bash
curl -H "Authorization: <PEXELS_API_KEY>" "https://api.pexels.com/videos/search?query=nature&per_page=1"
```
Expected: JSON içinde bir `"videos"` dizisi döner (200 OK).

---

## Task 21: YouTube OAuth kurulumu

**Bilinen risk:** Google, OAuth consent screen'i "Testing" durumundaki uygulamalarda `youtube.upload` gibi hassas kapsamlar için verilen refresh token'ları **7 gün sonra geçersiz kılar**. Günlük otomasyon bunu tolere edemez — bu yüzden aşağıdaki adımlarda uygulamanın doğrulama (verification) sürecine gönderilmesi de var. Doğrulama onaylanana kadar (birkaç gün-birkaç hafta sürebilir) test modunda 7 günde bir elle yeniden yetkilendirme gerekir; bu süre boyunca YouTube adımı `/publish` çağrısında hata dönebilir, diğer 3 platform etkilenmez (`/publish` platform bağımsız çalışıyor, bkz. Task 13).

- [ ] **Step 1: Google Cloud projesini oluştur ve API'yi etkinleştir**

https://console.cloud.google.com/ → yeni proje oluştur (örn. "sosyal-medya-otomasyon") → "APIs & Services" → "Library" → "YouTube Data API v3" ara → Enable.

- [ ] **Step 2: OAuth consent screen'i yapılandır**

"APIs & Services" → "OAuth consent screen" → User Type: External → App name, user support email, developer contact email doldur → Scopes adımında "Add or Remove Scopes" ile şunları ekle:
- `https://www.googleapis.com/auth/youtube.upload`
- `https://www.googleapis.com/auth/youtube.readonly`

Test users adımına kendi Google hesabını ekle (verification onaylanana kadar hemen test edebilmek için).

- [ ] **Step 3: OAuth Client ID oluştur**

"APIs & Services" → "Credentials" → "Create Credentials" → "OAuth client ID" → Application type: **Desktop app** → oluştur → Client ID ve Client Secret'ı kopyala, `.env`'de `YOUTUBE_CLIENT_ID` ve `YOUTUBE_CLIENT_SECRET`'a yaz.

- [ ] **Step 4: İlk refresh token'ı al (yerel, tek seferlik)**

Aşağıdaki URL'i tarayıcıda aç (CLIENT_ID'yi kendi değerinle değiştir):
```
https://accounts.google.com/o/oauth2/v2/auth?client_id=<YOUTUBE_CLIENT_ID>&redirect_uri=urn:ietf:wg:oauth:2.0:oob&response_type=code&access_type=offline&prompt=consent&scope=https://www.googleapis.com/auth/youtube.upload%20https://www.googleapis.com/auth/youtube.readonly
```
Google seni test kullanıcı olarak izin ekranına yönlendirir, onaylayınca bir **authorization code** gösterir. Sonra:
```bash
curl -X POST https://oauth2.googleapis.com/token \
  -d "code=<ALDIĞIN_CODE>" \
  -d "client_id=<YOUTUBE_CLIENT_ID>" \
  -d "client_secret=<YOUTUBE_CLIENT_SECRET>" \
  -d "redirect_uri=urn:ietf:wg:oauth:2.0:oob" \
  -d "grant_type=authorization_code"
```
Yanıttaki `refresh_token` değerini `.env`'de `YOUTUBE_REFRESH_TOKEN`'a yaz.

- [ ] **Step 5: Doğrula**

Run:
```bash
docker compose restart video-worker
docker compose exec video-worker python -c "from app.publishers.youtube import get_access_token; from app.config import config; print(get_access_token(config.YOUTUBE_CLIENT_ID, config.YOUTUBE_CLIENT_SECRET, config.YOUTUBE_REFRESH_TOKEN)[:10])"
```
Expected: bir access token'ın ilk 10 karakteri yazdırılır (hata yok).

- [ ] **Step 6: Doğrulama (verification) başvurusunu yap**

"OAuth consent screen" → "Publish App" → Google verification sürecini başlat (basit bir gizlilik politikası sayfası URL'i istenecek — statik bir HTML sayfası yeterli, barındırmak için mevcut `scrollytelling-engine` altyapın veya GitHub Pages kullanılabilir). Onaylanınca 7 günlük kısıtlama kalkar.

---

## Task 22: TikTok Developer app + audit başvurusu

**Bilinen risk (spec Bölüm 3.3'te de belirtildi):** Audit onaylanana kadar TikTok'a yüklenen videolar `SELF_ONLY` (private) kalır. Audit süresi TikTok'un elinde, garantili değil — bu yüzden başvuru olabildiğince erken yapılmalı.

- [ ] **Step 1: Developer hesabı ve app oluştur**

https://developers.tiktok.com/ → giriş yap/kayıt ol → "Manage apps" → "Create an app" → app adı gir, platform: Web.

- [ ] **Step 2: Content Posting API ürününü ekle**

App detay sayfasında "Add products" → "Content Posting API" ekle. `video.publish` ve `video.upload` scope'larını iste.

- [ ] **Step 3: Client key/secret'ı .env'e ekle**

App'in "Basic Information" sekmesinden Client Key ve Client Secret'ı kopyala, `.env`'de `TIKTOK_CLIENT_KEY` ve `TIKTOK_CLIENT_SECRET`'a yaz. `TIKTOK_AUDITED=false` olarak bırak.

- [ ] **Step 4: İlk refresh token'ı al (sandbox/kendi hesabınla OAuth)**

TikTok'un OAuth yetkilendirme URL'ini tarayıcıda aç:
```
https://www.tiktok.com/v2/auth/authorize?client_key=<TIKTOK_CLIENT_KEY>&scope=video.publish,video.upload&response_type=code&redirect_uri=<APP'DE_TANIMLI_REDIRECT_URI>&state=setup
```
Dönen `code` ile:
```bash
curl -X POST https://open.tiktokapis.com/v2/oauth/token/ \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "client_key=<TIKTOK_CLIENT_KEY>&client_secret=<TIKTOK_CLIENT_SECRET>&code=<ALDIĞIN_CODE>&grant_type=authorization_code&redirect_uri=<APP'DE_TANIMLI_REDIRECT_URI>"
```
Yanıttaki `refresh_token`'ı bir dosyaya yaz:

```bash
docker compose up -d video-worker
docker compose exec video-worker sh -c 'echo "{\"refresh_token\": \"<ALDIĞIN_REFRESH_TOKEN>\"}" > /data/tiktok-token/token.json'
```

- [ ] **Step 5: Doğrula**

Run:
```bash
docker compose exec video-worker python -c "from app.publishers.tiktok import _refresh_access_token; from app.config import config; print(_refresh_access_token(config.TIKTOK_CLIENT_KEY, config.TIKTOK_CLIENT_SECRET, config.TIKTOK_TOKEN_PATH)[:10])"
```
Expected: bir access token'ın ilk 10 karakteri yazdırılır. `docker compose exec video-worker cat /data/tiktok-token/token.json` içindeki `refresh_token`'ın değiştiğini (rotasyona uğradığını) doğrula.

- [ ] **Step 6: Audit başvurusunu yap**

App detay sayfasında "Submit for review" / audit başvurusunu yap, kullanım amacını (kişisel otomasyon, faceless içerik kanalı) açıkça belirt. Onaylanınca `.env`'de `TIKTOK_AUDITED=true` yap ve `docker compose restart video-worker` çalıştır.

---

## Task 23: Meta Developer app + Instagram Business bağlantısı

- [ ] **Step 1: Instagram hesabını Business/Creator hesabına çevir**

Instagram mobil uygulaması → Ayarlar → Hesap türü → "Profesyonel hesaba geç" → Business seç → bir Facebook Sayfası'na bağla (yoksa yeni bir Sayfa oluşturulur).

- [ ] **Step 2: Meta Developer app oluştur**

https://developers.facebook.com/ → "My Apps" → "Create App" → Type: Business → app adı gir.

- [ ] **Step 3: Instagram Graph API + izinleri ekle**

App Dashboard → "Add Product" → "Instagram Graph API" ekle. App'in kendi hesabına (senin hesabına) rolü zaten var olduğu için (App geliştiricisisin), Development modunda `instagram_content_publish`, `pages_read_engagement`, `pages_show_list` izinleriyle kendi hesabına yükleme yapılabilir — App Review'a gerek yok (spec Bölüm 3.4'te belirtildiği gibi).

- [ ] **Step 4: Page Access Token ve ID'leri al**

Graph API Explorer (https://developers.facebook.com/tools/explorer/) → App'ini seç → kullanıcı token'ı al → şu isteği çalıştır:
```
GET /me/accounts
```
Yanıttan `page_id` ve o sayfanın `access_token`'ını al (bu, uzun ömürlü bir Page Access Token'dır — Sayfa rolün olduğu sürece sona ermez). Sonra:
```
GET /{page_id}?fields=instagram_business_account
```
Yanıttan `instagram_business_account.id` değerini al.

- [ ] **Step 5: .env'e ekle**

`META_PAGE_ID`, `META_PAGE_ACCESS_TOKEN`, `META_IG_USER_ID` alanlarını doldur.

- [ ] **Step 6: Doğrula**

Run:
```bash
docker compose restart video-worker cloudflared
curl "https://graph.facebook.com/v19.0/<META_PAGE_ID>?fields=name&access_token=<META_PAGE_ACCESS_TOKEN>"
```
Expected: Sayfa adını içeren JSON döner (200 OK).

---

## Task 24: Uçtan uca duman testi (smoke test)

**Files:** Yok — tüm sistemin gerçek kimlik bilgileriyle bütünlük testi.

- [ ] **Step 1: Tüm .env alanlarının dolu olduğunu doğrula**

Run:
```bash
docker compose config | grep -A 20 "video-worker:" 
```
`.env`'de boş kalan bir alan varsa doldur (Task 19-23).

- [ ] **Step 2: Tüm sistemi ayağa kaldır**

```bash
docker compose up -d --build
docker compose ps
```
Expected: `n8n`, `video-worker`, `cloudflared` üçü de `running`/`healthy` durumda.

- [ ] **Step 3: cloudflared tünelinin çalıştığını doğrula**

```bash
docker compose exec video-worker python -c "from app.tunnel import get_tunnel_url; from app.config import config; print(get_tunnel_url(config.TUNNEL_LOG_PATH))"
```
Expected: `https://<random>.trycloudflare.com` yazdırılır.

- [ ] **Step 4: "Daily Video Pipeline"ı gerçek kimlik bilgileriyle elle tetikle**

n8n arayüzünde workflow'u "Execute Workflow" ile çalıştır. Telegram'da video + onay butonları gelene kadar bekle (script+TTS+stok video+render nedeniyle birkaç dakika sürebilir).

- [ ] **Step 5: Onayla ve tüm platformları doğrula**

**✅ Onayla** butonuna bas. Telegram'daki özet mesajında 4 platformun hepsi ✅ göstermeli (TikTok audit henüz onaylanmadıysa `SELF_ONLY` ile başarılı sayılır, bu beklenen davranıştır). Her platformu ayrıca elle kontrol et:
- YouTube Studio → İçerik → video "Unlisted" olarak görünmeli
- TikTok uygulaması → Profil → video görünmeli (audit onaylanmadıysa sadece sana görünür)
- Instagram → profil → Reels sekmesinde video görünmeli
- Facebook Sayfası → Reels sekmesinde video görünmeli

- [ ] **Step 6: "Weekly Analytics Report"ı elle tetikle**

n8n'de workflow'u "Execute Workflow" ile çalıştır.
Expected: Telegram'a az önce yayınlanan videonun başlığını ve (Facebook/Instagram/YouTube istatistikleri henüz oluşmamışsa `?` gösterebilir, birkaç saat sonra tekrar denendiğinde gerçek sayılar gelir) platform bazlı istatistiklerini içeren bir rapor gelir.

- [ ] **Step 7: Disk temizliğini doğrula**

```bash
docker compose exec video-worker ls -la /data/media
```
Expected: `used_topics.json` ve `published_log.json` dışında kalıcı dosya yok (video dosyası ve `pending.json` yayın sonrası silindi).

- [ ] **Step 8: Sistemi kalıcı çalışır bırak**

Tüm adımlar başarılıysa sistem artık günlük 09:00'da otomatik çalışacak, Telegram'dan onay bekleyecek, onaylanınca 4 platforma yükleyecek, haftalık Pazartesi 10:00'da rapor gönderecek şekilde kuruldu. `docker compose ps` ile üç container'ın da `restart: unless-stopped` ile kalıcı çalıştığını bir kez daha teyit et.

- [ ] **Step 9: Son commit**

```bash
git add -A
git commit -m "docs: complete end-to-end smoke test, system live

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```
