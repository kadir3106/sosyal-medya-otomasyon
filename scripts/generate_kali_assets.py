#!/usr/bin/env python3
"""KALI marka varlıklarını üretir.

Üretilenler:
  - logo_kali_1080.png   : KALI logosu (siyah zemin + mavi K, glow efektli)
  - logo_kali_512.png    : profil fotoğrafı boyutu
  - kart_kali_*.png      : KALI bilgi kartı (üretimdeki render motoruyla)
  - kart_ferah_kebap.png : demo müşteri kartı (restoran nişi)
  - kart_fitzone.png     : demo müşteri kartı (fitness nişi)
  - kart_latte_lab.png   : demo müşteri kartı (kafe nişi)
  - satis_mockup.png     : satış sayfası için 3 kartlı mockup

Çıktı klasörü: ~/Documents/kali_system/assets
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "video-worker"))

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.image_gen import FONT_CANDIDATES, render_card

OUTPUT_DIR = Path.home() / "Documents" / "kali_system" / "assets"

ACCENT = "#38BDF8"
DARK = "#0F172A"
LIGHT = "#E2E8F0"


def load_font(size: int):
    for path in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


def make_logo(size: int = 1080) -> Image.Image:
    image = Image.new("RGB", (size, size), DARK)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    font_k = load_font(int(size * 0.60))
    glow_draw.text(
        (size / 2, size * 0.44), "K",
        fill=(56, 189, 248, 130), font=font_k, anchor="mm",
    )
    glow = glow.filter(ImageFilter.GaussianBlur(size * 0.05))
    image = Image.alpha_composite(image.convert("RGBA"), glow).convert("RGB")

    draw = ImageDraw.Draw(image)
    draw.text(
        (size / 2, size * 0.44), "K", fill=ACCENT, font=font_k, anchor="mm"
    )
    draw.line(
        (size * 0.30, size * 0.68, size * 0.70, size * 0.68),
        fill=ACCENT, width=max(3, size // 180),
    )
    font_word = load_font(int(size * 0.085))
    draw.text(
        (size / 2, size * 0.80), "K A L I", fill=LIGHT, font=font_word, anchor="mm"
    )
    return image


def make_mockup(card_paths: list[Path], title: str) -> Image.Image:
    width, height = 1320, 560
    canvas = Image.new("RGB", (width, height), DARK)
    draw = ImageDraw.Draw(canvas)

    font_title = load_font(56)
    font_sub = load_font(30)
    draw.text((width / 2, 64), title, fill=ACCENT, font=font_title, anchor="mm")
    draw.text(
        (width / 2, 126),
        "Günde 1 video + 1 görsel — tamamen otomatik",
        fill="#64748B", font=font_sub, anchor="mm",
    )

    card_size = 360
    gap = 40
    total = card_size * len(card_paths) + gap * (len(card_paths) - 1)
    x = (width - total) / 2
    y = 170
    for path in card_paths:
        card = Image.open(path).resize((card_size, card_size))
        canvas.paste(card, (int(x), y))
        x += card_size + gap
    return canvas


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    logo_1080 = make_logo(1080)
    logo_path = OUTPUT_DIR / "logo_kali_1080.png"
    logo_1080.save(logo_path, format="PNG")
    logo_1080.resize((512, 512)).save(OUTPUT_DIR / "logo_kali_512.png", format="PNG")
    print(f"[ok] {logo_path}")

    cards = [
        (
            "kart_kali_bilgi.png", "KALI", ACCENT,
            "Yapay zekâ artık sosyal medyanızı yönetiyor — günde 1 video "
            "+ 1 görsel, tamamen otomatik üretilir.",
        ),
        (
            "kart_ferah_kebap.png", "Ferah Kebap", "#F59E0B",
            "Adana kebabın sırrı: közde pişirme ve dinlendirilmiş et. "
            "40 yıldır aynı usta, aynı lezzet.",
        ),
        (
            "kart_fitzone.png", "FitZone", "#34D399",
            "Haftada 3 gün 45 dakika egzersiz, kalp hastalığı riskini "
            "%30 azaltır. Bugün başla.",
        ),
        (
            "kart_latte_lab.png", "Latte Lab", "#C08457",
            "Kahvenizi 60°C'nin altında için — aromalar yanmadan, "
            "damakta kalsın.",
        ),
    ]

    saved = []
    for filename, brand, accent, text in cards:
        path = OUTPUT_DIR / filename
        render_card(text, brand_name=brand, accent=accent, output_path=str(path))
        saved.append(path)
        print(f"[ok] {path}")

    mockup = make_mockup(
        [OUTPUT_DIR / "kart_ferah_kebap.png",
         OUTPUT_DIR / "kart_fitzone.png",
         OUTPUT_DIR / "kart_latte_lab.png"],
        title="KALI — AI Sosyal Medya Otomasyonu",
    )
    mockup_path = OUTPUT_DIR / "satis_mockup.png"
    mockup.save(mockup_path, format="PNG")
    print(f"[ok] {mockup_path}")

    print(f"\nToplam {len(saved) + 3} dosya: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
