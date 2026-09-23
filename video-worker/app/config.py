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
    # Default EN pool = dark wealth (niche lock). Trivia topics.json is remapped away.
    TOPICS_PATH = os.environ.get(
        "TOPICS_PATH", "/app/data/topics_dark_wealth.json"
    )
    # Guard: if .env still points at trivia topics.json, force dark wealth.
    _topics_name = Path(TOPICS_PATH).name.lower()
    if _topics_name in ("topics.json", "video_topics.json", "trivia.json") or "trivia" in _topics_name:
        TOPICS_PATH = str(Path(TOPICS_PATH).with_name("topics_dark_wealth.json"))
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
    PIXABAY_API_KEY = os.environ.get("PIXABAY_API_KEY", "")
    # Mixkit has no official API — optional HTML search fallback (no key).
    ENABLE_MIXKIT_STOCK = (
        os.environ.get("ENABLE_MIXKIT_STOCK", "true").lower() == "true"
    )
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
    # Görsel motoru (default = stok video + hafif Ken Burns; Fal opsiyonel):
    #   stock — Pexels → Pixabay → Mixkit (konu-anchored); render'da hafif zoompan
    #   flux_kenburns / hybrid_flux — Fal Flux stills + FFmpeg Ken Burns
    #   hybrid — opsiyonel: hook'ta 0–1 Kling, gövde Flux+Ken Burns
    #   kling — opt-in T2V (kota: KLING_MAX_SCENES), kalan Flux
    #   ai — Pollinations/Flux still path (legacy)
    VISUAL_ENGINE = os.environ.get("VISUAL_ENGINE", "stock")
    FAL_KEY = os.environ.get("FAL_KEY", "")
    # Stock engine primary path. true also lets Flux miss fall through to stock.
    ALLOW_STOCK_FALLBACK = (
        os.environ.get("ALLOW_STOCK_FALLBACK", "true").lower() == "true"
    )
    # Tek videoda Kling ile üretilecek en fazla sahne (yalnızca VISUAL_ENGINE=kling|hybrid).
    KLING_MAX_SCENES = int(os.environ.get("KLING_MAX_SCENES", "1"))
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
    # LLM waterfall: primary (OPENROUTER_MODEL) → secondary → fallback
    # Fallback default is airouter-safe (gemini-flash). OpenRouter :free ids
    # like google/gemma-4-31b-it:free are NOT listed by airouter and return 400.
    OPENROUTER_MODEL_SECONDARY = os.environ.get("OPENROUTER_MODEL_SECONDARY", "")
    OPENROUTER_MODEL_FALLBACK = os.environ.get(
        "OPENROUTER_MODEL_FALLBACK", "gemini-flash"
    )
    # Video formatı: 'cinematic' (lüks/belgesel tek ekran), 'split_screen' veya 'standard'
    VIDEO_FORMAT = os.environ.get("VIDEO_FORMAT", "cinematic")
    CINEMATIC_GRADE = os.environ.get("CINEMATIC_GRADE", "true").lower() == "true"
    # AI Director (creative plan → fetch). Default OFF — legacy VISUAL_ENGINE path unchanged.
    # Model choice is NOT done here; LLM calls go through LLM_API_URL (AI router).
    # Re-read env each access so tests / compose toggles are not stuck on import-time value.
    @property
    def DIRECTOR_ENABLED(self) -> bool:
        return os.environ.get("DIRECTOR_ENABLED", "false").lower() == "true"

    DIRECTOR_AI_IMAGE_MAX = int(os.environ.get("DIRECTOR_AI_IMAGE_MAX", "2"))
    DIRECTOR_RELEVANCE_MIN = float(os.environ.get("DIRECTOR_RELEVANCE_MIN", "0.2"))
    # Telegram günlük özet mesajı (bkz. app/daily_digest.py) — yerel saatle (TZ) karşılaştırılır.
    DIGEST_HOUR = int(os.environ.get("DIGEST_HOUR", "21"))
    DIGEST_INTERVAL_SECONDS = int(os.environ.get("DIGEST_INTERVAL_SECONDS", "300"))


config = Config()
