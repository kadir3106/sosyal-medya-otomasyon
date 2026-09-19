"""Faz 1-4 doğrulama: 'slayt gibi tekrar' sorununun gerçekten bittiğini ÖLÇER.

Gerçek ffmpeg ile üretir: 30 sn ses + 6 farklı kısa klip -> render.
Eski davranışta 6 klip 17 kez kullanılıyordu (2.83x tekrar). Yeni davranışta
sahne sayısı ses süresinden gelir ve tekrar oranı 1.0'a iner.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "video-worker"))

from app.render import (  # noqa: E402
    clip_reuse_ratio,
    get_audio_duration,
    plan_scene_schedule,
    render_video,
    scene_transition_times,
)

WIDTH, HEIGHT, FPS = 1080, 1920, 30
DURATION = 30.9


def make_clip(path: Path, color: str, seconds: float = 5.0) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"color=c={color}:s={WIDTH}x{HEIGHT}:d={seconds}:r={FPS}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "ultrafast",
            str(path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def distinct_colors(count: int) -> list[str]:
    """Her sahne için gözle ayırt edilebilir farklı renk üretir."""
    return [f"0x{hue:02x}{255 - hue:02x}80" for hue in range(0, 255, max(1, 255 // count))][:count]


def make_audio(path: Path, seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", f"anoisesrc=d={seconds}:c=pink:r=44100",
            str(path),
        ],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def make_subs(path: Path) -> None:
    path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
        "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        "Style: Default,DejaVu Sans,90,&H00F8F9FA&,&H0000D7FF&,&H000D0D0D&,"
        "&H90000000,-1,0,0,0,100,100,1,0,1,6,3,2,60,60,480,1\n\n"
        "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text\n"
        "Dialogue: 0,0:00:00.00,0:00:30.00,Default,,0,0,0,,DOGRULAMA TESTI\n",
        encoding="utf-8",
    )


def probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(out.stdout.strip())


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)

        audio = work / "speech.mp3"
        make_audio(audio, DURATION)
        subs = work / "subs.ass"
        make_subs(subs)

        actual_audio = get_audio_duration(str(audio))

        # --- ESKİ DAVRANIŞ SİMÜLASYONU (kanıtlanmış kök neden) ---
        # Eski kod sabit 6 sahne üretiyordu, render ise ceil((d-0.4)/1.8) klip ister.
        old_clip_count = 6
        old_needed = -(-int(actual_audio * 1000 - 400) // 1800)
        old_ratio = clip_reuse_ratio(
            [f"clip_{i}.mp4" for i in range(old_clip_count)], old_needed
        )

        # --- YENİ DAVRANIŞ ---
        # Pipeline artık sahne sayısını ses süresinden hesaplayıp O KADAR klip ister.
        durations = plan_scene_schedule(
            actual_audio, base_duration=2.2, xfade_duration=0.4
        )
        scene_count = len(durations)
        colors = distinct_colors(scene_count)

        clips = []
        for i, color in enumerate(colors):
            p = work / f"clip_{i}.mp4"
            make_clip(p, color)
            clips.append(str(p))

        transitions = scene_transition_times(durations, 0.4)

        sfx = work / "sfx.wav"
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i", "anoisesrc=d=0.35:c=pink:r=44100",
             "-af", "afade=t=in:ss=0:d=0.15,afade=t=out:st=0.15:d=0.2", str(sfx)],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        bgm = work / "bgm.mp3"
        make_audio(bgm, 5.0)

        out = work / "final.mp4"
        stats: dict = {}
        render_video(
            clips, str(audio), str(subs), str(out), str(work),
            clip_duration=2.2, xfade_duration=0.4,
            bgm_path=str(bgm), bgm_volume=0.12,
            cinematic_grade=True, sfx_path=str(sfx), apply_zoompan=False,
            stats_out=stats,
        )

        out_duration = probe_duration(out)
        video_stream = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "v",
             "-show_entries", "stream=width,height,nb_frames",
             "-of", "default=noprint_wrappers=1", str(out)],
            capture_output=True, text=True, check=True,
        ).stdout.strip().replace("\n", " ")

        print("=" * 64)
        print("ESKI DAVRANIS (kanitlanan kok neden)")
        print("=" * 64)
        print(f"  ses suresi            : {actual_audio:.2f} sn")
        print(f"  uretilen klip         : {old_clip_count} (script '6 prompt' istiyordu)")
        print(f"  gereken sahne (2.2sn) : {old_needed}")
        print(f"  TEKRAR ORANI          : {old_ratio}x  <-- slayt hissi")

        print()
        print("=" * 64)
        print("YENI DAVRANIS (uygulanan kurgu motoru)")
        print("=" * 64)
        print(f"  ritim plani           : {[round(d, 2) for d in durations]}")
        print(f"  sahne sayisi          : {stats['scene_count']} (= istenen klip sayisi)")
        print(f"  TEKRAR ORANI          : {stats['clip_reuse_ratio']}x")
        print(f"  gecis sayisi          : {len(transitions)} (efektler sirayla degisir)")
        print(f"  sfx zamanlari (ilk 5) : {transitions[:5]}")
        print(f"  cikti suresi          : {out_duration:.2f} sn")
        print(f"  video akisi           : {video_stream}")

        checks = [
            (f"Tekrar orani 1.0x (eski: {old_ratio}x)",
             stats["clip_reuse_ratio"] == 1.0),
            ("Sahne sayisi ses suresine yetiyor", stats["scene_count"] >= 15),
            ("Cikti suresi ses ile uyumlu (<0.5 sn fark)",
             abs(out_duration - actual_audio) < 0.5),
            ("Her klip en fazla 1 kez kullanildi (tekrar yok)",
             stats["clip_reuse_ratio"] <= 1.0),
            ("Eski tekrar oranindan cok daha iyi",
             stats["clip_reuse_ratio"] < old_ratio),
        ]
        print()
        ok = True
        for label, passed in checks:
            print(f"  [{'OK' if passed else 'FAIL'}] {label}")
            ok = ok and passed

        # --- EK SENARYO: klip yetmezse ne olur? (ham dongu OLMAMALI) ---
        print()
        print("=" * 64)
        print("EKSIK KLIP SENARYOSU (stok kota dolu / Kling dustu)")
        print("=" * 64)
        few = clips[:4]
        fallback_stats: dict = {}
        fb_out = work / "fallback.mp4"
        render_video(
            few, str(audio), str(subs), str(fb_out), str(work),
            clip_duration=2.2, xfade_duration=0.4,
            cinematic_grade=False, apply_zoompan=False,
            stats_out=fallback_stats,
        )
        fb_ratio = fallback_stats["clip_reuse_ratio"]
        # Kaynaklar arka arkaya ayni olmamali (eski [a,b,a,b] davranisi).
        from app.render import build_scene_sources
        order = [p for p, _ in build_scene_sources(few, fallback_stats["scene_count"])]
        no_adjacent = all(order[i] != order[i + 1] for i in range(len(order) - 1))
        seek_used = any(s > 0 for _, s in build_scene_sources(few, fallback_stats["scene_count"]))

        print(f"  klip sayisi           : {len(few)}")
        print(f"  sahne sayisi          : {fallback_stats['scene_count']}")
        print(f"  tekrar orani          : {fb_ratio}x (ham dongu yerine adil dagitim)")
        print(f"  arka arkaya ayni klip : {not no_adjacent}")
        print(f"  farkli andan kesim    : {seek_used}")
        print()
        fb_checks = [
            ("Ayni klip arka arkaya gelmiyor", no_adjacent),
            ("Tekrar eden klip farkli andan kesiliyor", seek_used),
            ("Tekrar orani tavanda kaliyor (<=2x)", fb_ratio <= 2.0),
        ]
        for label, passed in fb_checks:
            print(f"  [{'OK' if passed else 'FAIL'}] {label}")
            ok = ok and passed

        print()
        print(f"SONUC: {'TUM KONTROLLER GECTI' if ok else 'BASARISIZ'}")
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
