from pathlib import Path
import re

# edge-tts reports offsets/durations in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000

# 1080x1920 (9:16) tuvale göre: lüks/sinematik koyu arka planlara uygun,
# kalın gölgeli, güvenli alanda (safe zone - 480px) konumlu zarif stil.
# Renkler ASS formatında &HAABBGGRR&:
# Beyaz: &H00F8F9FA&, Altın Vurgu: &H0000D7FF& (Gold #FFD700)
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,90,&H00F8F9FA&,&H0000D7FF&,&H000D0D0D&,&H90000000,-1,0,0,0,100,100,1,0,1,6,3,2,60,60,480,1
Style: Hook,DejaVu Sans,78,&H00F8F9FA&,&H0000D7FF&,&H000D0D0D&,&H90000000,-1,0,0,0,100,100,1.5,0,1,8,4,8,70,70,280,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Viral videolarda tutundurmayı artıran anahtar kelime - emoji eşleştirmeleri
_EMOJI_KEYWORDS = {
    ("para", "money", "dolar", "zengin", "kazan", "milyon", "finans"): "💰",
    ("hızlı", "roket", "uzay", "evren", "mars", "space", "fast"): "🚀",
    ("beyin", "akıl", "fikir", "düşün", "hafıza", "brain"): "🧠",
    ("şok", "inanılmaz", "şaşırtıcı", "gizli", "sır", "shock"): "🤯",
    ("ateş", "trend", "popüler", "sıcak", "fire"): "🔥",
    ("dünya", "global", "gezegen", "okyanus", "earth"): "🌍",
    ("zaman", "saat", "dakika", "tarih", "time"): "⏳",
    ("korku", "tehlike", "ölüm", "dikkat", "danger"): "⚠️",
    ("başarı", "hedef", "güç", "odak", "zafer", "win"): "🏆",
    ("komedi", "komik", "kahkaha", "şaka", "gülme"): "😂",
}


def _get_word_emoji(raw_text: str) -> str:
    clean = re.sub(r"[^\w\s]", "", raw_text.lower())
    for keywords, emoji in _EMOJI_KEYWORDS.items():
        if any(kw in clean for kw in keywords):
            return f" {emoji}"
    return ""


def write_ass(
    word_boundaries: list[dict],
    output_path: str,
    words_per_cue: int = 2,
    highlight: bool = False,
    add_emojis: bool = False,
    hook_text: str | None = None,
    hook_seconds: float = 2.5,
    karaoke_start_seconds: float = 0.0,
    hook_max_words: int = 0,
) -> str:
    """Kelime zamanlamalarından modern ASS altyazı üretir.

    highlight=True olduğunda konuşulan kelimeyi parlak sarı (&H0000FFFF) renkle
    öne çıkaran dinamik karaoke kurgusu üretir; highlight=False geriye dönük
    uyumluluk için düz 2 kelimelik grupları korur.

    hook_text: kısa punch overlay (üst). Phase 2.2: max ~1.5–2.0s + fade-out;
    VO ile yüksek örtüşmede static title atlanır (karaoke taşır).
    karaoke_start_seconds: karaoke bu saniyeden önce başlamaz.
    hook_max_words: >0 ise hook metnini kısaltır (uzun statik paragraf yok).
    """
    lines = [ASS_HEADER]
    if hook_text and hook_text.strip():
        punch = hook_text.strip()
        if hook_max_words and hook_max_words > 0:
            punch = " ".join(punch.split()[:hook_max_words])
        # Skip static title when it mostly duplicates the opening VO / karaoke.
        if not _hook_duplicates_opening_vo(punch, word_boundaries):
            wrapped = _wrap_hook_line(punch, max_len=28)
            # Cap display; fade out so logo/product focal point isn't covered long.
            secs = min(max(float(hook_seconds), 0.8), 1.8)
            end_ticks = int(secs * TICKS_PER_SECOND)
            # Soft fade-in/out (ASS \fad ms_in, ms_out).
            fad = r"{\fad(120,450)}"
            lines.append(
                f"Dialogue: 1,0:00:00.00,{_format_timestamp(end_ticks)},"
                f"Hook,,0,0,0,,{fad}{wrapped}\n"
            )
    karaoke_start_ticks = int(max(karaoke_start_seconds, 0.0) * TICKS_PER_SECOND)
    if not word_boundaries:
        Path(output_path).write_text("".join(lines), encoding="utf-8")
        return output_path

    for start in range(0, len(word_boundaries), words_per_cue):
        group = word_boundaries[start : start + words_per_cue]
        cue_start = group[0]["offset"]
        cue_end = group[-1]["offset"] + group[-1]["duration"]
        # Skip karaoke that would stack under the hook punch overlay.
        if cue_end <= karaoke_start_ticks:
            continue
        if cue_start < karaoke_start_ticks:
            cue_start = karaoke_start_ticks

        if not highlight:
            escaped_words = [_escape_ass_text(w["text"]) for w in group]
            cue_text = " ".join(escaped_words)
            if add_emojis:
                for w in group:
                    em = _get_word_emoji(w["text"])
                    if em:
                        cue_text += em
                        break
            lines.append(
                f"Dialogue: 0,{_format_timestamp(cue_start)},{_format_timestamp(cue_end)},"
                f"Default,,0,0,0,,{cue_text}\n"
            )
        else:
            # Dinamik kelime vurgulama: gruptaki her kelime konuşulurken sarı parlar
            for i, active_word in enumerate(group):
                w_start = active_word["offset"]
                w_end = active_word["offset"] + active_word["duration"]
                # Son kelime grubu sonuna kadar uzasın
                if i == len(group) - 1:
                    w_end = max(w_end, cue_end)
                if w_end <= karaoke_start_ticks:
                    continue
                if w_start < karaoke_start_ticks:
                    w_start = karaoke_start_ticks

                styled_parts = []
                for j, w in enumerate(group):
                    w_text = _escape_ass_text(w["text"]).upper()
                    if j == i:
                        # Aktif konuşulan kelime: Zengin altın vurgu (&H0000D7FF&)
                        styled_parts.append(f"{{\\c&H0000D7FF&}}{w_text}{{\\c&H00F8F9FA&}}")
                    else:
                        styled_parts.append(w_text)

                text_line = " ".join(styled_parts)
                if add_emojis:
                    em = _get_word_emoji(active_word["text"])
                    if em:
                        text_line += em

                lines.append(
                    f"Dialogue: 0,{_format_timestamp(w_start)},{_format_timestamp(w_end)},"
                    f"Default,,0,0,0,,{text_line}\n"
                )

    Path(output_path).write_text("".join(lines), encoding="utf-8")
    return output_path


def _hook_duplicates_opening_vo(
    hook: str, word_boundaries: list[dict], *, overlap: float = 0.55
) -> bool:
    """True when hook mostly repeats the first spoken words (karaoke carries it)."""
    if not hook or not word_boundaries:
        return False
    stop = {
        "a",
        "an",
        "the",
        "is",
        "isn't",
        "are",
        "was",
        "it",
        "its",
        "of",
        "and",
        "to",
        "in",
        "for",
        "with",
    }
    hook_toks = {
        w.lower().strip(".,:;!?")
        for w in hook.split()
        if w.lower().strip(".,:;!?") not in stop and len(w) > 1
    }
    vo = " ".join(str(w.get("text") or "") for w in word_boundaries[:8])
    vo_toks = {
        w.lower().strip(".,:;!?")
        for w in vo.split()
        if w.lower().strip(".,:;!?") not in stop and len(w) > 1
    }
    if not hook_toks or not vo_toks:
        return False
    return (len(hook_toks & vo_toks) / len(hook_toks)) >= overlap


def _escape_ass_text(text: str) -> str:
    # ASS metin alanında \, {, } özel anlam taşır
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _wrap_hook_line(text: str, max_len: int = 42) -> str:
    """Soft-wrap hook for ASS (\\N). Escape ASS specials."""
    words = text.split()
    if not words:
        return ""
    lines: list[str] = []
    current: list[str] = []
    for w in words:
        trial = (" ".join(current + [w])).strip()
        if current and len(trial) > max_len:
            lines.append(_escape_ass_text(" ".join(current)))
            current = [w]
        else:
            current.append(w)
    if current:
        lines.append(_escape_ass_text(" ".join(current)))
    # Max 3 lines on screen for the hook card
    return "\\N".join(lines[:3])


def _format_timestamp(ticks: int) -> str:
    # ASS zaman biçimi: H:MM:SS.CC (santisaniye, ondalık 2 hane)
    total_cs = ticks // (TICKS_PER_SECOND // 100)
    hours, remainder = divmod(total_cs, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"

