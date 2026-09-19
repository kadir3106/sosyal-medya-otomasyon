import os
from pathlib import Path
from dotenv import load_dotenv

# .env dosyasını yükle (hem uygulama hem testler için).
# docker-compose ortam değişkenleri zaten os.environ'da olduğundan
# bu sadece yerel çalıştırmalarda .env'i doldurur; mevcut env'i EZMEZ.
# Önce proje kökündeki .env aranır (docker-compose.yml ile aynı dizin),
# yoksa video-worker/.env'e düşülür.
_env_candidates = [
    Path(__file__).resolve().parent.parent.parent / ".env",   # repo kökü
    Path(__file__).resolve().parent.parent / ".env",          # video-worker/ (konteyner mount)
]
for _p in _env_candidates:
    if _p.exists():
        _override = "PYTEST_CURRENT_TEST" not in os.environ
        load_dotenv(dotenv_path=str(_p), override=_override)
        break





class Config:
    MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/media")
    TUNNEL_LOG_PATH = os.environ.get("TUNNEL_LOG_PATH", "/tunnel-logs/tunnel.log")
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    # n8n'in cron saatleriyle (docker-compose.yml -> n8n-workflows) eşleşmeli —
    # kaçan-cron yakalama (app/catchup.py) bu saatleri referans alıyor.
    VIDEO_SCHEDULE_HOUR = int(os.environ.get("VIDEO_SCHEDULE_HOUR", "9"))
    IMAGE_SCHEDULE_HOUR = int(os.environ.get("IMAGE_SCHEDULE_HOUR", "12"))
    # Default EN pool = dark wealth (niche lock). Trivia topics.json is opt-in.
    TOPICS_PATH = os.environ.get(
        "TOPICS_PATH", "/app/data/topics_dark_wealth.json"
    )
    TOPICS_PATH_TR = os.environ.get("TOPICS_PATH_TR", "/app/data/video_topics_tr.json")
    VIDEO_LANG = os.environ.get("VIDEO_LANG", "en")
    VIDEO_VOICE = os.environ.get("VIDEO_VOICE", "")
    VIDEO_VOICE_RATE = os.environ.get("VIDEO_VOICE_RATE", "+12%")
    BGM_DIR = os.environ.get("BGM_DIR", "/app/data/audio/bgm")
    IMAGE_TOPICS_PATH = os.environ.get("IMAGE_TOPICS_PATH", "/app/data/image_topics.json")
    IMAGE_BRAND_NAME = os.environ.get("IMAGE_BRAND_NAME", "KALI")
    IMAGE_ACCENT = os.environ.get("IMAGE_ACCENT", "#38BDF8")
    OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
    OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "")
    LLM_API_URL = os.environ.get("LLM_API_URL", "")
    X_CLIENT_ID = os.environ.get("X_CLIENT_ID", "")
    X_CLIENT_SECRET = os.environ.get("X_CLIENT_SECRET", "")
    X_REFRESH_TOKEN = os.environ.get("X_REFRESH_TOKEN", "")
    LINKEDIN_CLIENT_ID = os.environ.get("LINKEDIN_CLIENT_ID", "")
    LINKEDIN_CLIENT_SECRET = os.environ.get("LINKEDIN_CLIENT_SECRET", "")
    LINKEDIN_REFRESH_TOKEN = os.environ.get("LINKEDIN_REFRESH_TOKEN", "")
    LINKEDIN_AUTHOR_URN = os.environ.get("LINKEDIN_AUTHOR_URN", "")
    PEXELS_API_KEY = os.environ.get("PEXELS_API_KEY", "")
    YOUTUBE_CLIENT_ID = os.environ.get("YOUTUBE_CLIENT_ID", "")
    YOUTUBE_CLIENT_SECRET = os.environ.get("YOUTUBE_CLIENT_SECRET", "")
    YOUTUBE_REFRESH_TOKEN = os.environ.get("YOUTUBE_REFRESH_TOKEN", "")
    YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY", "")
    TIKTOK_CLIENT_KEY = os.environ.get("TIKTOK_CLIENT_KEY", "")
    TIKTOK_CLIENT_SECRET = os.environ.get("TIKTOK_CLIENT_SECRET", "")
    TIKTOK_AUDITED = os.environ.get("TIKTOK_AUDITED", "false").lower() == "true"
    TIKTOK_TOKEN_PATH = os.environ.get(
        "TIKTOK_TOKEN_PATH", "/data/tiktok-token/token.json"
    )
    META_IG_USER_ID = os.environ.get("META_IG_USER_ID", "")
    META_PAGE_ID = os.environ.get("META_PAGE_ID", "")
    META_PAGE_ACCESS_TOKEN = os.environ.get("META_PAGE_ACCESS_TOKEN", "")
    THREADS_USER_ID = os.environ.get("THREADS_USER_ID", "")
    THREADS_ACCESS_TOKEN = os.environ.get("THREADS_ACCESS_TOKEN", "")
    PINTEREST_CLIENT_ID = os.environ.get("PINTEREST_CLIENT_ID", "")
    PINTEREST_CLIENT_SECRET = os.environ.get("PINTEREST_CLIENT_SECRET", "")
    PINTEREST_REFRESH_TOKEN = os.environ.get("PINTEREST_REFRESH_TOKEN", "")
    PINTEREST_BOARD_ID = os.environ.get("PINTEREST_BOARD_ID", "")
    # Görsel motoru: 'hybrid' (Hook sahnesi Kling AI, diğerleri FLUX), 'kling', 'ai' veya 'stock'
    VISUAL_ENGINE = os.environ.get("VISUAL_ENGINE", "hybrid")
    FAL_KEY = os.environ.get("FAL_KEY", "")
    # Tek videoda Kling ile üretilecek en fazla sahne. Kling sahne başına
    # dakikalar sürüyor; tüm sahneleri Kling'e vermek üretimi saatlerce
    # kilitleyip kotayı yakardı. Kalan sahneler stok HD videodan gelir.
    KLING_MAX_SCENES = int(os.environ.get("KLING_MAX_SCENES", "3"))
    ELEVENLABS_API_KEY = os.environ.get("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID = os.environ.get("ELEVENLABS_VOICE_ID", "")
    ENABLE_SFX = os.environ.get("ENABLE_SFX", "true").lower() == "true"
    # Keyword emoji on ASS captions — off for cinematic / luxury (template smell).
    ENABLE_SUBTITLE_EMOJIS = (
        os.environ.get("ENABLE_SUBTITLE_EMOJIS", "false").lower() == "true"
    )
    # YouTube analitiğinden kazanan hook/konuları LLM promptuna enjekte et.
    ENABLE_ANALYTICS_MEMORY = (
        os.environ.get("ENABLE_ANALYTICS_MEMORY", "false").lower() == "true"
    )
    # LLM waterfall: primary (OPENROUTER_MODEL) → secondary → free fallback
    OPENROUTER_MODEL_SECONDARY = os.environ.get("OPENROUTER_MODEL_SECONDARY", "")
    OPENROUTER_MODEL_FALLBACK = os.environ.get(
        "OPENROUTER_MODEL_FALLBACK", "google/gemma-4-31b-it:free"
    )
    # Video formatı: 'cinematic' (lüks/belgesel tek ekran), 'split_screen' veya 'standard'
    VIDEO_FORMAT = os.environ.get("VIDEO_FORMAT", "cinematic")
    CINEMATIC_GRADE = os.environ.get("CINEMATIC_GRADE", "true").lower() == "true"
    # Telegram günlük özet mesajı (bkz. app/daily_digest.py) — yerel saatle (TZ) karşılaştırılır.
    DIGEST_HOUR = int(os.environ.get("DIGEST_HOUR", "21"))
    DIGEST_INTERVAL_SECONDS = int(os.environ.get("DIGEST_INTERVAL_SECONDS", "300"))


config = Config()
