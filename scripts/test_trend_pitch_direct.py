import os
import sys
from pathlib import Path

# Add video-worker to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from app.config import config
from app.trends import fetch_trends
from app.pitch_gen import generate_pitches

def main():
    lang = config.VIDEO_LANG or "en"
    geo = "US" if lang == "en" else "TR"
    print(f"🌍 Trends taranıyor (Bölge: {geo}, Dil: {lang})...")
    trends = fetch_trends(geo=geo, max_count=5)
    print(f"✅ {len(trends)} trend bulundu:")
    for t in trends:
        print(f"  - {t.get('title')}: {t.get('description')[:60]}...")

    print("\n🤖 Viral pitch konseptleri üretiliyor (OpenRouter LLM)...")
    pitches = generate_pitches(trends, api_key=config.OPENROUTER_API_KEY, lang=lang)

    print("\n🎯 ÜRETİLEN 3 VİRAL KONSEPT:")
    print("=" * 60)
    for p in pitches:
        cat = p.get("category_label", p.get("category"))
        print(f"[{cat}] {p.get('title')}")
        print(f"  🎯 Hook: \"{p.get('hook')}\"")
        print(f"  📌 Topic: {p.get('topic')}\n")
    print("=" * 60)

if __name__ == "__main__":
    main()
