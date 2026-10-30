from pathlib import Path
import re

# edge-tts reports offsets/durations in 100-nanosecond ticks.
TICKS_PER_SECOND = 10_000_000

# 1080x1920 (9:16) — Default karaoke mid-lower safe zone (TikTok/Reels UI).
# MarginV larger = higher from bottom. 440 keeps above bottom chrome, below mid.
ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,DejaVu Sans,84,&H00F8F9FA&,&H0000D7FF&,&H000D0D0D&,&H90000000,-1,0,0,0,100,100,1,0,1,5,2,2,70,70,440,1
Style: Hook,DejaVu Sans,72,&H00F8F9FA&,&H0000D7FF&,&H000D0D0D&,&H90000000,-1,0,0,0,100,100,1.5,0,1,6,3,8,70,70,260,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

# Legacy header (Phase 2 freeze path when PHASE3_CAPTIONS_ENABLED=false)
ASS_HEADER_LEGACY = """[Script Info]
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


def _normalize_emphasis(words: list[str] | None) -> set[str]:
    out: set[str] = set()
    for w in words or []:
        tok = re.sub(r"[^\w$]", "", str(w)).lower()
        if len(tok) >= 2:
            out.add(tok)
        # multi-word: also add last token
        for part in str(w).split():
            p = re.sub(r"[^\w$]", "", part).lower()
            if len(p) >= 2:
                out.add(p)
    return out


def _is_emphasis_word(text: str, emphasis: set[str]) -> bool:
    if not emphasis:
        return False
    tok = re.sub(r"[^\w$]", "", text).lower()
    if tok in emphasis:
        return True
    # $12B style
    if "$" in text and any(e.startswith("$") or e.isdigit() for e in emphasis):
        return True
    return False


# Function words that must not start/end orphan caption fragments alone.
_PREPOSITIONS = frozenset(
    {
        "into", "onto", "from", "with", "without", "about", "under", "over",
        "after", "before", "between", "among", "through", "during", "toward",
        "towards", "across", "against", "within", "along", "around",
        "a", "an", "the", "of", "to", "in", "on", "for", "at", "by", "as",
    }
)


def _chunk_boundaries_phase3(
    word_boundaries: list[dict],
    *,
    max_words: int = 5,
    max_seconds: float = 1.6,
    min_words: int = 2,
) -> list[list[dict]]:
    """Semantic phrase chunks — exact transcript text preserved; grouping only.

    Prefer punctuation / clause boundaries; never orphan a dangling preposition
    fragment like \"ROLEX INTO A PRIVATE\"; keep proper nouns and $ amounts together.
    """
    if not word_boundaries:
        return []

    texts = [str(w.get("text") or "") for w in word_boundaries]
    n = len(word_boundaries)

    def is_proper_pair(i: int) -> bool:
        if i + 1 >= n:
            return False
        a, b = texts[i], texts[i + 1]
        # Capitalized consecutive tokens (person/place names)
        if a[:1].isupper() and b[:1].isupper() and a.isalpha() and b.replace("-", "").isalpha():
            return True
        return False

    def is_money_pair(i: int) -> bool:
        if i + 1 >= n:
            return False
        a, b = texts[i].lower(), texts[i + 1].lower().rstrip(".,")
        if a.startswith("$"):
            return True
        if a.replace(",", "").replace(".", "").isdigit() and b in {
            "billion", "million", "trillion", "percent", "%", "dollars", "dollar"
        }:
            return True
        return False

    def ends_clause(tok: str) -> bool:
        return tok.rstrip().endswith((".", "!", "?", ";", ":"))

    def soft_break(tok: str) -> bool:
        return tok.rstrip().endswith(",")

    chunks: list[list[dict]] = []
    i = 0
    while i < n:
        cur: list[dict] = []
        start_off = int(word_boundaries[i].get("offset") or 0)
        while i < n:
            # Don't split a proper noun / money unit across chunks
            if cur and (is_proper_pair(i - 1) or is_money_pair(i - 1)):
                cur.append(word_boundaries[i])
                i += 1
                if ends_clause(texts[i - 1]):
                    break
                continue

            cur.append(word_boundaries[i])
            tok = texts[i]
            i += 1
            off = int(word_boundaries[i - 1].get("offset") or 0)
            dur_s = (off - start_off) / TICKS_PER_SECOND

            if ends_clause(tok) and len(cur) >= 1:
                break
            if soft_break(tok) and len(cur) >= min_words:
                break
            if len(cur) >= max_words or dur_s >= max_seconds:
                if i < n and (is_proper_pair(i - 1) or is_money_pair(i - 1)):
                    continue
                last = texts[i - 1].lower().rstrip(".,:;!?")
                if last in _PREPOSITIONS and i < n and len(cur) < max_words + 2:
                    cur.append(word_boundaries[i])
                    i += 1
                break

        if chunks and len(cur) == 1:
            chunks[-1].extend(cur)
            continue
        chunks.append(cur)

    merged: list[list[dict]] = []
    for ch in chunks:
        if not ch:
            continue
        first = str(ch[0].get("text") or "").lower().rstrip(".,:;!?")
        if merged and first in _PREPOSITIONS and len(ch) <= 3:
            merged[-1].extend(ch)
        elif merged and len(ch) == 1 and first in _PREPOSITIONS:
            merged[-1].extend(ch)
        else:
            merged.append(ch)
    return merged


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
    *,
    phase3: bool = False,
    emphasis_words: list[str] | None = None,
    script_text: str | None = None,
    timeline_end_seconds: float | None = None,
) -> str:
    """Kelime zamanlamalarından modern ASS altyazı üretir.

    phase3=True: semantic chunks, selective emphasis, safe-zone styles,
    shorter hook fad, karaoke from VO start (karaoke_start_seconds honored).
    """
    header = ASS_HEADER if phase3 else ASS_HEADER_LEGACY
    lines = [header]
    emphasis = _normalize_emphasis(emphasis_words) if phase3 else set()

    # Phase 3.1: full static top title OFF by default — karaoke carries the hook.
    # Only emit Hook style when explicitly provided AND not duplicating VO.
    if hook_text and hook_text.strip():
        punch = hook_text.strip()
        if hook_max_words and hook_max_words > 0:
            punch = " ".join(punch.split()[:hook_max_words])
        if phase3 and _is_marketing_title_overlay(punch):
            punch = ""
        if punch and not _hook_duplicates_opening_vo(punch, word_boundaries):
            wrapped = _wrap_hook_line(punch, max_len=24 if phase3 else 28)
            secs = min(max(float(hook_seconds), 0.8), 1.2 if phase3 else 1.8)
            end_ticks = int(secs * TICKS_PER_SECOND)
            fad = r"{\fad(80,280)}" if phase3 else r"{\fad(120,450)}"
            lines.append(
                f"Dialogue: 1,0:00:00.00,{_format_timestamp(end_ticks)},"
                f"Hook,,0,0,0,,{fad}{wrapped}\n"
            )

    karaoke_start_ticks = int(max(karaoke_start_seconds, 0.0) * TICKS_PER_SECOND)
    if not word_boundaries:
        Path(output_path).write_text("".join(lines), encoding="utf-8")
        return output_path

    # TTS boundaries often omit punctuation. Restore only when the token stream
    # exactly matches the supplied narration; otherwise preserve original words.
    if script_text:
        script_words = script_text.split()
        clean = lambda value: re.sub(r"[^\w]", "", str(value).casefold())
        if len(script_words) == len(word_boundaries) and all(
            clean(token) == clean(word.get("text", ""))
            for token, word in zip(script_words, word_boundaries)
        ):
            word_boundaries = [
                {**word, "text": token}
                for token, word in zip(script_words, word_boundaries)
            ]

    if phase3:
        groups = _chunk_boundaries_phase3(word_boundaries)
    else:
        groups = [
            word_boundaries[i : i + words_per_cue]
            for i in range(0, len(word_boundaries), words_per_cue)
        ]

    timeline_end_ticks = (
        int(max(0.0, float(timeline_end_seconds)) * TICKS_PER_SECOND)
        if timeline_end_seconds is not None
        else 0
    )
    for group_index, group in enumerate(groups):
        if not group:
            continue
        cue_start = group[0]["offset"]
        cue_end = group[-1]["offset"] + group[-1]["duration"]
        if group_index == len(groups) - 1 and timeline_end_ticks > cue_end:
            cue_end = timeline_end_ticks
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
            continue

        # Karaoke: Phase 3 only gold-flash emphasis words; others stay white.
        for i, active_word in enumerate(group):
            w_start = active_word["offset"]
            w_end = active_word["offset"] + active_word["duration"]
            if i == len(group) - 1:
                w_end = max(w_end, cue_end)
            if w_end <= karaoke_start_ticks:
                continue
            if w_start < karaoke_start_ticks:
                w_start = karaoke_start_ticks

            styled_parts = []
            for j, w in enumerate(group):
                w_text = _escape_ass_text(w["text"]).upper()
                flash = j == i and (
                    not phase3 or _is_emphasis_word(str(w.get("text") or ""), emphasis)
                )
                if flash:
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


def extend_ass_to_duration(path: str, duration_seconds: float) -> float:
    """Extend only the final cue so scheduled captions cover the audio clock."""
    target_ticks = int(max(0.0, float(duration_seconds)) * TICKS_PER_SECOND)
    source = Path(path)
    if not source.is_file():
        return 0.0
    lines = source.read_text(encoding="utf-8").splitlines(keepends=True)
    dialogue_indexes = [i for i, line in enumerate(lines) if line.startswith("Dialogue:")]
    if not dialogue_indexes:
        return 0.0
    index = dialogue_indexes[-1]
    parts = lines[index].rstrip("\r\n").split(",", 3)
    if len(parts) < 4:
        return 0.0
    current_ticks = _parse_timestamp(parts[2])
    if target_ticks > current_ticks:
        parts[2] = _format_timestamp(target_ticks)
        newline = "\r\n" if lines[index].endswith("\r\n") else "\n"
        lines[index] = ",".join(parts) + newline
        source.write_text("".join(lines), encoding="utf-8")
        current_ticks = target_ticks
    return current_ticks / TICKS_PER_SECOND


def _is_marketing_title_overlay(hook: str) -> bool:
    """Generic detector for static title cards that compete with karaoke.

    Not a brand blacklist — catches ALL-CAPS / \"THE … SECRET\" style overlays
    that duplicate what narration+captions already communicate.
    """
    words = [w for w in (hook or "").split() if w]
    if not words:
        return True
    if len(words) <= 6 and all(w.isupper() or not w.isalpha() for w in words):
        return True
    low = " ".join(words).lower()
    if low.startswith("the ") and any(
        t in low for t in (" secret", " truth", " mystery", " rule", " code")
    ):
        return True
    return False


def _hook_duplicates_opening_vo(
    hook: str, word_boundaries: list[dict], *, overlap: float = 0.45
) -> bool:
    """True when hook mostly repeats the first spoken words (karaoke carries it)."""
    if not hook or not word_boundaries:
        return False
    stop = {
        "a", "an", "the", "is", "isn't", "are", "was", "it", "its",
        "of", "and", "to", "in", "for", "with",
    }
    hook_toks = {
        w.lower().strip(".,:;!?")
        for w in hook.split()
        if w.lower().strip(".,:;!?") not in stop and len(w) > 1
    }
    vo = " ".join(str(w.get("text") or "") for w in word_boundaries[:10])
    vo_toks = {
        w.lower().strip(".,:;!?")
        for w in vo.split()
        if w.lower().strip(".,:;!?") not in stop and len(w) > 1
    }
    if not hook_toks or not vo_toks:
        return False
    return (len(hook_toks & vo_toks) / len(hook_toks)) >= overlap


def _escape_ass_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def _wrap_hook_line(text: str, max_len: int = 42) -> str:
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
    return "\\N".join(lines[:2 if max_len <= 24 else 3])


def _format_timestamp(ticks: int) -> str:
    total_cs = ticks // (TICKS_PER_SECOND // 100)
    hours = total_cs // 360000
    minutes = (total_cs % 360000) // 6000
    seconds = (total_cs % 6000) // 100
    centis = total_cs % 100
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centis:02d}"


def _parse_timestamp(value: str) -> int:
    hours, minutes, seconds = value.strip().split(":")
    return int(round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * TICKS_PER_SECOND))


def first_caption_start_seconds(word_boundaries: list[dict]) -> float:
    if not word_boundaries:
        return 0.0
    return max(0.0, int(word_boundaries[0].get("offset") or 0) / TICKS_PER_SECOND)


def retune_ass_caption_style(
    path: str,
    *,
    font_size: int,
    outline: int,
    margin_v: int,
) -> None:
    """Adjust only the Default ASS style while preserving every caption cue."""
    source = Path(path)
    lines = source.read_text(encoding="utf-8-sig").splitlines()
    for index, line in enumerate(lines):
        if not line.startswith("Style: Default,"):
            continue
        fields = line.split(",")
        if len(fields) < 23:
            raise ValueError("invalid_ass_default_style")
        fields[2] = str(int(font_size))
        fields[17] = str(int(outline))
        fields[21] = str(int(margin_v))
        lines[index] = ",".join(fields)
        source.write_text("\n".join(lines) + "\n", encoding="utf-8-sig")
        return
    raise ValueError("missing_ass_default_style")
