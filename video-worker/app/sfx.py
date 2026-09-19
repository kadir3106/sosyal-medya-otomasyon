import re
import subprocess
from pathlib import Path


def create_whoosh_sound(output_path: str) -> str:
    """Yumuşak, sinematik sahne geçiş sesi (whoosh) sentezler."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1000:
        return str(out)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anoisesrc=d=0.35:c=pink:r=44100,volume=0.3",
        "-af", "afade=t=in:ss=0:d=0.15,afade=t=out:st=0.15:d=0.2",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(out)


def create_cash_sound(output_path: str) -> str:
    """Para / Dolar / Zenginlik kelimeleri için tiz altın/kasa çınlaması efekti sentezler."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1000:
        return str(out)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=f=1760:d=0.22,volume=0.25,afade=t=out:st=0.06:d=0.16",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(out)


def create_bass_impact(output_path: str) -> str:
    """Yasak / Kara liste / Tehlike kelimeleri için derin sub-bass darbesi sentezler."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1000:
        return str(out)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "sine=f=52:d=0.55,volume=0.45,afade=t=in:ss=0:d=0.04,afade=t=out:st=0.15:d=0.4",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(out)


def create_shutter_snap(output_path: str) -> str:
    """Kural / Kanun / Belge / İmza kelimeleri için keskin mekanik klik/fotoğraf efekti sentezler."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.stat().st_size > 1000:
        return str(out)

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", "anoisesrc=d=0.09:c=white:r=44100,volume=0.35,highpass=f=2500,afade=t=out:st=0.02:d=0.07",
        str(out),
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return str(out)


KEYWORD_TRIGGERS = {
    "cash": {
        "words": {
            "dollar", "dollars", "cash", "money", "rich", "billion", "billionaire",
            "billionaires", "million", "millions", "fortune", "expensive", "buy",
            "buys", "price", "gold", "wealth", "wealthy", "paid", "worth", "cost", "costs"
        },
        "creator": create_cash_sound,
        "filename": "sfx_cash.wav",
        "volume": 0.22,
        "cooldown": 3.5,
    },
    "impact": {
        "words": {
            "banned", "blacklist", "blacklisted", "forbidden", "secret", "secrets",
            "never", "kicked", "trapped", "danger", "scam", "lie", "vanished",
            "refused", "punished", "illegal", "impossible", "ban", "bans"
        },
        "creator": create_bass_impact,
        "filename": "sfx_impact.wav",
        "volume": 0.35,
        "cooldown": 3.0,
    },
    "shutter": {
        "words": {
            "rule", "rules", "law", "laws", "contract", "signed", "history",
            "document", "documents", "camera", "photo", "paper", "proof", "code"
        },
        "creator": create_shutter_snap,
        "filename": "sfx_shutter.wav",
        "volume": 0.25,
        "cooldown": 3.0,
    },
}


def build_smart_sfx_track(
    total_duration: float,
    clip_duration: float,
    output_path: str,
    sfx_dir: str,
    transition_times: list[float] | None = None,
    word_boundaries: list[dict] | None = None,
) -> str | None:
    sfx_events = []

    whoosh_path = create_whoosh_sound(str(Path(sfx_dir) / "whoosh.wav"))
    if transition_times is None:
        transition_times = []
        t = clip_duration
        while t < total_duration - 1.0:
            transition_times.append(round(t, 2))
            t += clip_duration

    for t_sec in transition_times:
        if 0.2 < t_sec < total_duration - 0.3:
            sfx_events.append((whoosh_path, round(t_sec, 2), 0.22))

    if word_boundaries:
        last_triggered = {cat: -99.0 for cat in KEYWORD_TRIGGERS}

        for wb in word_boundaries:
            raw_text = wb.get("text", "")
            clean_word = re.sub(r"[^\w]", "", raw_text).lower()
            start_time = float(wb.get("start", wb.get("start_time", 0.0)))

            if start_time < 0.2 or start_time > total_duration - 0.5:
                continue

            for cat, cfg in KEYWORD_TRIGGERS.items():
                if clean_word in cfg["words"]:
                    if start_time - last_triggered[cat] >= cfg["cooldown"]:
                        sfx_file = cfg["creator"](str(Path(sfx_dir) / cfg["filename"]))
                        sfx_events.append((sfx_file, round(start_time, 2), cfg["volume"]))
                        last_triggered[cat] = start_time
                        break

    if not sfx_events:
        return None

    sfx_events.sort(key=lambda x: x[1])
    sfx_events = sfx_events[:25]

    inputs = []
    filter_parts = []
    for i, (fpath, t_sec, vol) in enumerate(sfx_events):
        delay_ms = int(t_sec * 1000)
        inputs += ["-i", fpath]
        filter_parts.append(f"[{i}:a]adelay={delay_ms}|{delay_ms},volume={vol}[sfx{i}]")

    mix_inputs = "".join(f"[sfx{i}]" for i in range(len(sfx_events)))
    filter_complex = ";".join(filter_parts) + f";{mix_inputs}amix=inputs={len(sfx_events)}:duration=longest[sfxfinal]"

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[sfxfinal]",
        "-t", str(total_duration),
        str(output_path),
    ]

    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return str(output_path)
    except Exception as e:
        print(f"[sfx] Akıllı SFX miks uyarısı: {e}")
        return None


def build_sfx_track(
    total_duration: float,
    clip_duration: float,
    output_path: str,
    sfx_dir: str,
    transition_times: list[float] | None = None,
    word_boundaries: list[dict] | None = None,
) -> str | None:
    return build_smart_sfx_track(
        total_duration=total_duration,
        clip_duration=clip_duration,
        output_path=output_path,
        sfx_dir=sfx_dir,
        transition_times=transition_times,
        word_boundaries=word_boundaries,
    )
