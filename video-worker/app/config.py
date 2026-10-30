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

    # Documentary Engine V2 — Stage A: schemas/telemetry only. Default OFF.
    # When true later (Stage B+), production uses V2 path; Stage A never executes V2.
    @property
    def DOCUMENTARY_ENGINE_V2(self) -> bool:
        return os.environ.get("DOCUMENTARY_ENGINE_V2", "false").lower() == "true"

    # Stage C VisualVerifier — isolated; default OFF; not wired to /generate.
    @property
    def VISUAL_VERIFIER_ENABLED(self) -> bool:
        return os.environ.get("VISUAL_VERIFIER_ENABLED", "false").lower() == "true"

    VISUAL_VERIFIER_PROVIDER = os.environ.get("VISUAL_VERIFIER_PROVIDER", "mock")
    VISUAL_VERIFIER_MODEL = os.environ.get("VISUAL_VERIFIER_MODEL", "")
    VISUAL_VERIFIER_FALLBACK_PROVIDER = os.environ.get(
        "VISUAL_VERIFIER_FALLBACK_PROVIDER", ""
    )
    VISUAL_VERIFIER_TIMEOUT = float(os.environ.get("VISUAL_VERIFIER_TIMEOUT", "45"))
    VISUAL_VERIFIER_MAX_CANDIDATES = int(
        os.environ.get("VISUAL_VERIFIER_MAX_CANDIDATES", "5")
    )
    VISUAL_VERIFIER_MAX_FRAMES = int(os.environ.get("VISUAL_VERIFIER_MAX_FRAMES", "7"))
    VISUAL_VERIFIER_CACHE = (
        os.environ.get("VISUAL_VERIFIER_CACHE", "true").lower() == "true"
    )
    VISUAL_VERIFIER_PROMPT_VERSION = os.environ.get(
        "VISUAL_VERIFIER_PROMPT_VERSION", "visual-verifier-v1"
    )
    # Stage D.1: direct_groq | gateway | auto (prefer GROQ_API_KEY for vision)
    VISUAL_VERIFIER_TRANSPORT = os.environ.get("VISUAL_VERIFIER_TRANSPORT", "auto")
    GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
    GROQ_API_URL = os.environ.get(
        "GROQ_API_URL", "https://api.groq.com/openai/v1/chat/completions"
    )

    # Stage E recovery budgets — conservative defaults; V2 OFF; no auto spend.
    RECOVERY_MAX_ATTEMPTS_PER_BEAT = int(
        os.environ.get("RECOVERY_MAX_ATTEMPTS_PER_BEAT", "3")
    )
    RECOVERY_MAX_MOTION_GRAPHIC_RENDERS = int(
        os.environ.get("RECOVERY_MAX_MOTION_GRAPHIC_RENDERS", "4")
    )
    RECOVERY_MAX_AI_GENERATION_CALLS = int(
        os.environ.get("RECOVERY_MAX_AI_GENERATION_CALLS", "1")
    )
    RECOVERY_MAX_GENERATION_COST_PER_VIDEO = float(
        os.environ.get("RECOVERY_MAX_GENERATION_COST_PER_VIDEO", "0.50")
    )
    RECOVERY_MAX_GENERATION_COST_PER_BEAT = float(
        os.environ.get("RECOVERY_MAX_GENERATION_COST_PER_BEAT", "0.25")
    )
    STAGE_E_LIVE_GENERATION = (
        os.environ.get("STAGE_E_LIVE_GENERATION", "false").lower() == "true"
    )
    GENERATED_VIDEO_PROVIDER = os.environ.get(
        "GENERATED_VIDEO_PROVIDER", "mock"
    )  # mock|fal_kling

    # Stage F — EDL assembly / critic / repair (V2 still OFF by default)
    MAX_FINAL_REPAIR_PASSES = int(os.environ.get("MAX_FINAL_REPAIR_PASSES", "2"))
    MAX_REPAIRS_PER_BEAT = int(os.environ.get("MAX_REPAIRS_PER_BEAT", "1"))
    MAX_EXTRA_VLM_CALLS = int(os.environ.get("MAX_EXTRA_VLM_CALLS", "12"))
    MAX_EXTRA_GENERATION_COST = float(os.environ.get("MAX_EXTRA_GENERATION_COST", "0.25"))
    STAGE_F_RUN = os.environ.get("STAGE_F_RUN", "false").lower() == "true"
    FINAL_CRITIC_ENABLED = (
        os.environ.get("FINAL_CRITIC_ENABLED", "true").lower() == "true"
    )

    DIRECTOR_AI_IMAGE_MAX = int(os.environ.get("DIRECTOR_AI_IMAGE_MAX", "2"))
    DIRECTOR_RELEVANCE_MIN = float(os.environ.get("DIRECTOR_RELEVANCE_MIN", "0.2"))
    # Phase 3 audio/captions/music/retention — rollback with *_ENABLED=false.
    @property
    def PHASE3_AUDIO_ENABLED(self) -> bool:
        return os.environ.get("PHASE3_AUDIO_ENABLED", "true").lower() == "true"

    @property
    def PHASE3_CAPTIONS_ENABLED(self) -> bool:
        return os.environ.get("PHASE3_CAPTIONS_ENABLED", "true").lower() == "true"

    @property
    def PHASE3_MUSIC_ENABLED(self) -> bool:
        return os.environ.get("PHASE3_MUSIC_ENABLED", "true").lower() == "true"

    @property
    def PHASE3_RETENTION_ENABLED(self) -> bool:
        return os.environ.get("PHASE3_RETENTION_ENABLED", "true").lower() == "true"

    @property
    def PHASE3_HOOK_TITLE_ENABLED(self) -> bool:
        # Phase 3.1 default OFF — karaoke/narration carries the hook.
        return os.environ.get("PHASE3_HOOK_TITLE_ENABLED", "false").lower() == "true"

    ELEVENLABS_STABILITY = os.environ.get("ELEVENLABS_STABILITY", "")
    ELEVENLABS_SIMILARITY = os.environ.get("ELEVENLABS_SIMILARITY", "")
    ELEVENLABS_STYLE = os.environ.get("ELEVENLABS_STYLE", "")
    # Telegram günlük özet mesajı (bkz. app/daily_digest.py) — yerel saatle (TZ) karşılaştırılır.
    DIGEST_HOUR = int(os.environ.get("DIGEST_HOUR", "21"))
    DIGEST_INTERVAL_SECONDS = int(os.environ.get("DIGEST_INTERVAL_SECONDS", "300"))


config = Config()
