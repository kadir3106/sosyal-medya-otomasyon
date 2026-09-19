"""
YouTube Resmi Banner Standartlarına (2560x1440) %100 Uyumlu Banner Üretici
YouTube Güvenli Alan (Safe Area): 1546 x 423 piksel (Tam Ortada).
Bu alan Mobil, Tablet, Laptop ve Masaüstü ekranların hepsinde eksiksiz ve kırpılmadan görünür.
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from pathlib import Path
import math

CANVAS_WIDTH = 2560
CANVAS_HEIGHT = 1440

# Safe Area: Mobil ve Masaüstünde görünen garanti alan
SAFE_WIDTH = 1546
SAFE_HEIGHT = 423
SAFE_TOP = (CANVAS_HEIGHT - SAFE_HEIGHT) // 2      # 508
SAFE_BOTTOM = SAFE_TOP + SAFE_HEIGHT             # 931
SAFE_LEFT = (CANVAS_WIDTH - SAFE_WIDTH) // 2       # 507
SAFE_RIGHT = SAFE_LEFT + SAFE_WIDTH              # 2053

def create_banner():
    # 1. 2560x1440 Koyu Lüks Mermer / Obsidian Arka Plan Oluştur
    avatar_path = Path(r"c:\Projects\sosyal-medya-otomasyon\video-output\branding\peak_motivation_avatar.jpg")
    
    if avatar_path.exists():
        src_img = Image.open(avatar_path).convert("RGBA")
    else:
        src_img = Image.new("RGBA", (1024, 1024), (10, 12, 16, 255))
        
    # Arka planı 2560x1440 boyutuna sinematik olarak doldur (koyu gradyan ve lüks doku)
    bg = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (8, 9, 12, 255))
    
    # Kaynak avatarı büyütüp koyulaştırarak ve bulanıklaştırarak arka plan dokusu yap
    bg_texture = src_img.resize((CANVAS_WIDTH, CANVAS_WIDTH)).filter(ImageFilter.GaussianBlur(30))
    # Ortala
    y_off = (CANVAS_WIDTH - CANVAS_HEIGHT) // 2
    bg.paste(bg_texture.crop((0, y_off, CANVAS_WIDTH, y_off + CANVAS_HEIGHT)), (0, 0))
    
    # Karartma katmanı uygula (yazılar ve logo parlasın)
    dimmer = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (5, 6, 8, 180))
    bg = Image.alpha_composite(bg, dimmer)
    
    # 2. Ortadaki Güvenli Alana (Safe Zone) Logoyu ve Tipografiyi Yerleştir
    draw = ImageDraw.Draw(bg)
    
    # Altın Işık Halesi (Safe zone ortasına hafif altın ışıltı)
    glow = Image.new("RGBA", (CANVAS_WIDTH, CANVAS_HEIGHT), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    center_y = CANVAS_HEIGHT // 2
    center_x = CANVAS_WIDTH // 2
    
    for r in range(260, 50, -15):
        alpha = int(25 * (1 - r / 260))
        glow_draw.ellipse(
            (center_x - r * 2, center_y - r - 30, center_x + r * 2, center_y + r + 30),
            fill=(212, 175, 55, alpha)
        )
    glow = glow.filter(ImageFilter.GaussianBlur(25))
    bg = Image.alpha_composite(bg, glow)
    draw = ImageDraw.Draw(bg)
    
    # Taç / Tepe Logosunu Avatar'dan kırpıp temizle ve tam merkeze yerleştir
    # Avatar 1024x1024, taç genelde merkezde (250..750)
    crown_crop = src_img.crop((260, 260, 764, 680))
    crown_h = 160
    crown_w = int(crown_crop.width * (crown_h / crown_crop.height))
    crown_resized = crown_crop.resize((crown_w, crown_h), Image.Resampling.LANCZOS)
    
    crown_x = (CANVAS_WIDTH - crown_w) // 2
    crown_y = center_y - 155
    bg.paste(crown_resized, (crown_x, crown_y), crown_resized if "A" in crown_resized.getbands() else None)
    
    # 3. Tipografi (Safe Zone sınırları içine tam sığacak boyutlar)
    font_title_path = r"C:\Windows\Fonts\arialbd.ttf"
    font_sub_path = r"C:\Windows\Fonts\segoeuib.ttf"
    
    font_title = ImageFont.truetype(font_title_path, 82)
    font_sub = ImageFont.truetype(font_sub_path, 28)
    font_badge = ImageFont.truetype(font_sub_path, 22)
    
    title_text = "PEAK MOTIVATION"
    sub_text = "UNVEILING CORPORATE SECRETS & DARK WEALTH"
    badge_text = "• DAILY SHORTS AT 18:30 •"
    
    # Başlık Metni
    t_bbox = draw.textbbox((0, 0), title_text, font=font_title)
    t_w = t_bbox[2] - t_bbox[0]
    t_x = (CANVAS_WIDTH - t_w) // 2
    t_y = center_y + 15
    
    # Altın metalik gölge ve parlak beyaz-altın yazı
    draw.text((t_x + 2, t_y + 3), title_text, font=font_title, fill=(0, 0, 0, 220))
    draw.text((t_x, t_y), title_text, font=font_title, fill=(245, 245, 250, 255))
    
    # Alt Başlık
    s_bbox = draw.textbbox((0, 0), sub_text, font=font_sub)
    s_w = s_bbox[2] - s_bbox[0]
    s_x = (CANVAS_WIDTH - s_w) // 2
    s_y = t_y + 92
    draw.text((s_x, s_y), sub_text, font=font_sub, fill=(212, 175, 55, 240))
    
    # İnce Alt Çizgi Süslemesi
    line_y = s_y + 42
    line_w = 400
    draw.line((center_x - line_w // 2, line_y, center_x + line_w // 2, line_y), fill=(212, 175, 55, 120), width=2)
    
    # Badge Metni
    b_bbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    b_w = b_bbox[2] - b_bbox[0]
    b_x = (CANVAS_WIDTH - b_w) // 2
    b_y = line_y + 10
    draw.text((b_x, b_y), badge_text, font=font_badge, fill=(180, 185, 195, 220))
    
    # RGB'ye çevir ve kaydet
    final_banner = bg.convert("RGB")
    
    out_branding = Path(r"c:\Projects\sosyal-medya-otomasyon\video-output\branding\peak_motivation_banner.jpg")
    out_desktop = Path(r"C:\Users\Victus\Desktop\peak_motivation_banner.jpg")
    
    final_banner.save(out_branding, quality=95)
    final_banner.save(out_desktop, quality=95)
    print("SUCCESS: Resmi YouTube Banner'i basariyla uretildi: 2560x1440")
    print(f"Kayit yeri: {out_desktop}")

if __name__ == "__main__":
    create_banner()
