import subprocess
from pathlib import Path

WIDTH = 1080
HEIGHT = 1920

# Ken Burns (zoompan) ayarları — görsel hareketsiz stock klipleri canlandırır.
# z: 1.0 -> 1.0 + ZOOM_MAX (kademeli yaklaşma); x/y merkezden hafif kayarak
# "sinematik" his verir. Yüksek çözünürlüklü kaynağa ihtiyaç duyar; zoompan
# çıktıyı WIDTH x HEIGHT yapar (s:x:y çıktı boyutu), o yüzden öncesinde
# upsample edip sonra zoompan'dan geçirmek en net sonucu verir.
FPS = 30
CLIP_DURATION = 5.0          # her klibin ekranda kalma süresi (sn) — varsayılan
XFADE_DURATION = 0.8         # kesişme (crossfade) süresi (sn) — varsayılan
ZOOM_MAX = 0.08              # toplam zoom büyümesi (1.0 -> 1.08)

# --- Ritim eğrisi -----------------------------------------------------------
# Sabit sahne süresi videoyu "slayt gösterisi" gibi hissettirir. Kanca hızlı
# kesilir (dikkat), orta bölüm normal nefes alır, final sahnesi geniş kalır.
RHYTHM_FAST_DURATION = 1.6
RHYTHM_FAST_SLOTS = 3
RHYTHM_TAIL_DURATION = 2.6
RHYTHM_TAIL_SLOTS = 2

# Hiçbir sahne bundan kısa olamaz (göz takip edemez, "titreme" hissi verir).
MIN_SCENE_DURATION = 1.2

# Kesişme efektleri sırayla değişir — tek tip geçiş monotonluk yaratır.
XFADE_TRANSITIONS = ("fade", "circleopen", "smoothleft", "fadeblack", "dissolve")

# Bir klip tekrar kullanılmak zorunda kalırsa, aynı kareler yerine klibin
# farklı bir anından kesilir (sn cinsinden ileri sarma adımları).
CLIP_SEEK_STEPS = (0.0, 1.2, 2.4, 3.6)

IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp")

# Eldeki klip sayısı yetmediğinde kabul edilen en yüksek tekrar oranı. Bu sınır 1.0
# tutularak aynı görüntünün videonun ikinci yarısında tekrar dönmesi (slayt hissi) kesinlikle önlenir.
MAX_CLIP_REUSE_TARGET = 1.0

# Tek sahnenin kalabileceği en uzun süre. Klip yetmediğinde sahne sayısını kısmak
# için süreler esnetilir. Üst sınır stok kliplerin tipik uzunluğuna (~5 sn) yakın
# tutulur: aynı görüntüyü 4 kez tekrarlamaktansa tek bir gerçek planı uzun göstermek
# yeğdir, ama 8 sn'lik donuk kare de kabul edilemez.
MAX_SCENE_DURATION = 6.0


def get_audio_duration(audio_path: str) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            audio_path,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


def _normalize_filter() -> str:
    """Her input'u ortak formata getirir: 30fps, 1080x1920, SAR 1:1."""
    chain = (
        f"fps={FPS},"
        f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,"
        f"crop={WIDTH}:{HEIGHT},setsar=1"
    )
    return chain


def _zoompan_filter(clip_duration: float = CLIP_DURATION) -> str:
    """Ken Burns for STILLS only: gradual zoom via zoompan.

    d=1: one output frame per input frame (no slow-mo). Do NOT use this on
    live stock video — zoompan freezes frame 0 into a slideshow.
    """
    zoom_step = ZOOM_MAX / (clip_duration * FPS)
    max_zoom = 1 + ZOOM_MAX
    return (
        f"zoompan=z='min(zoom+{zoom_step:.6f},{max_zoom})':"
        f"d=1:"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
        f"s={WIDTH}x{HEIGHT}:fps={FPS}"
    )


def _live_kenburns_filter(duration: float) -> str:
    """Subtle zoom-in on motion video (stock clips) without freezing frames.

    Scales each frame by up to ZOOM_MAX over the scene, then center-crops
    back to 1080x1920. Uses scale eval=frame — not zoompan.
    """
    d = max(float(duration), 0.01)
    return (
        f"scale=w='iw*(1+{ZOOM_MAX}*min(t/{d:.3f}\\,1))':"
        f"h='ih*(1+{ZOOM_MAX}*min(t/{d:.3f}\\,1))':eval=frame,"
        f"crop={WIDTH}:{HEIGHT}:(in_w-{WIDTH})/2:(in_h-{HEIGHT})/2"
    )


def _xfade_chain_filter(
    labeled: list[str],
    durations: list[float] | None = None,
    xfade_duration: float = XFADE_DURATION,
    transitions: tuple[str, ...] = XFADE_TRANSITIONS,
) -> str:
    """[v0][v1]... girişlerini xfade ile zincirleyip [vout] üretir.

    `durations` her klibin KENDİ süresidir (değişken ritim). Offset kümülatiftir:
    i. geçiş, kendinden önceki tüm kliplerin görünür süreleri toplamına oturur.
    Geçiş efekti her kesimde değişir; tek tip geçiş monotonluk yaratır.
    """
    if len(labeled) == 1:
        return f"{labeled[0]}[vout]"
    if durations is None:
        durations = [CLIP_DURATION] * len(labeled)

    parts = []
    prev = labeled[0]
    last_index = len(labeled) - 1
    offset = 0.0
    for i in range(1, len(labeled)):
        out_label = "vout" if i == last_index else f"vx{i}"
        offset += durations[i - 1] - xfade_duration
        transition = transitions[(i - 1) % len(transitions)]
        parts.append(
            f"[{prev}][{labeled[i]}]xfade=transition={transition}:"
            f"duration={xfade_duration}:offset={round(offset, 3)},fps={FPS}[{out_label}]"
        )
        prev = out_label
    return ";".join(parts)


def _covered_duration(durations: list[float], xfade_duration: float) -> float:
    """Sahne listesinin (kesişmeler düşülmüş) ekranda kapladığı toplam süre."""
    if not durations:
        return 0.0
    return sum(durations) - xfade_duration * (len(durations) - 1)


def plan_scene_schedule(
    audio_duration: float,
    base_duration: float = CLIP_DURATION,
    xfade_duration: float = XFADE_DURATION,
    max_scenes: int | None = None,
) -> list[float]:
    """Ses süresini kaplayacak sahne sürelerini ritmik olarak üretir.

    ESKİ DAVRANIŞ: sahne sayısı sabitti (6) ve render eksik kalanı başa sararak
    tamamlıyordu -> her görüntü ortalama 3 kez ekrana geliyordu ("slayt" hissi).

    YENİ DAVRANIŞ: sahne sayısı ses süresinden hesaplanır; kimse başa sarılmaz.
    Süreler de tek düze değil: kanca hızlı kesilir (dikkat), orta bölüm nefes
    alır, final sahnesi geniş kalır — kesme ritmi videoya "kurgu" hissi verir.

    `max_scenes`: eldeki klip sayısı yetmediğinde sahne sayısını sınırlar. Aynı
    klibi 10 kez göstermek ("slayt") yerine daha az sahne kullanıp her sahneyi
    uzatmak yeğdir — bu yüzden süreler bu tavana sığacak şekilde esnetilir.
    """
    if audio_duration <= 0:
        return [max(base_duration, 0.5)]

    def build(base: float) -> list[float]:
        durations: list[float] = []
        while True:
            index = len(durations)
            fast = index < RHYTHM_FAST_SLOTS
            durations.append(RHYTHM_FAST_DURATION if fast else base)
            if _covered_duration(durations, xfade_duration) >= audio_duration:
                break

        # Final sahne(ler) geniş kalsın: kapanış cümlesi nefes alsın.
        tail_start = max(len(durations) - RHYTHM_TAIL_SLOTS, RHYTHM_FAST_SLOTS)
        for i in range(tail_start, len(durations)):
            durations[i] = max(durations[i], RHYTHM_TAIL_DURATION)

        # Son sahneyi tam ses süresine oturt: video ne uzun ne kısa kalsın
        # (fazlalık `-shortest` ile kesilip boşa render ediliyordu).
        overshoot = _covered_duration(durations, xfade_duration) - audio_duration
        if overshoot > 0:
            durations[-1] = max(MIN_SCENE_DURATION, durations[-1] - overshoot)
        return durations

    durations = build(base_duration)

    # Klip sayısı yetmiyorsa sahne sayısını tavana indirmeyi dene: aynı görüntünün
    # defalarca dönmesindense daha az ama daha uzun sahneler yeğdir. Sahne süresi
    # MAX_SCENE_DURATION'ı aşacaksa bu denemeden vazgeçilir — 10 sn donuk kare,
    # tekrar eden görüntüden daha kötüdür (o durumda kalite kapısı uyarı verir).
    if max_scenes and len(durations) > max_scenes:
        base = base_duration
        best = durations
        while base < MAX_SCENE_DURATION:
            base += 0.1
            candidate = build(base)
            if len(candidate) <= max_scenes:
                return candidate
            if len(candidate) < len(best):
                best = candidate
        return best

    return durations


def build_scene_sources(clip_paths: list[str], needed: int) -> list[tuple[str, float]]:
    """(klip yolu, klibin içinden başlanacak saniye) listesi üretir.

    Klip sayısı yetmediğinde eski davranış klipleri ham bir döngüyle başa
    sarmaktı: aynı klipler aynı karelerle art arda dönüyordu. Yeni davranış:
    - En az kullanılan klip seçilir, bir öncekiyle AYNI klip asla arka arkaya
      gelmez (sıçrama hissi = "slayt" hissi).
    - Tekrar kullanılan her klip, farklı bir saniyesinden başlatılır; aynı klip
      bile bambaşka bir kare gösterir.
    """
    if not clip_paths or needed <= 0:
        return []

    counts = dict.fromkeys(clip_paths, 0)
    sources: list[tuple[str, float]] = []
    previous: str | None = None

    for _ in range(needed):
        order = sorted(clip_paths, key=lambda c: (counts[c], clip_paths.index(c)))
        chosen = next((c for c in order if c != previous), order[0])
        seek = CLIP_SEEK_STEPS[counts[chosen] % len(CLIP_SEEK_STEPS)]
        sources.append((chosen, float(seek)))
        counts[chosen] += 1
        previous = chosen

    return sources


def scene_transition_times(
    durations: list[float], xfade_duration: float = XFADE_DURATION
) -> list[float]:
    """Her kesme (xfade) anının video içindeki başlangıç saniyeleri.

    SFX whoosh'ları bu anlara oturtulur; böylece ses efekti görüntüyle tam
    senkron olur (eski kod sabit `clip_duration` varsayıyordu ve değişken
    ritimde kayıyordu).
    """
    times = []
    offset = 0.0
    for i in range(1, len(durations)):
        offset += durations[i - 1] - xfade_duration
        times.append(round(offset, 2))
    return times


def clip_reuse_ratio(clip_paths: list[str], needed: int) -> float:
    """Görüntü kaynaklarının kaç kez tekrar kullanıldığı (1.0 = hiç tekrar yok)."""
    if not clip_paths:
        return 0.0
    return round(needed / len(clip_paths), 2)


def _grade_ops(variant: int) -> str:
    """Sinematik kontrast, derin siyahlar, lüks vinyet ve film dokusu.

    `variant` her sahnede farklı bir tam sayı alır: grain şiddeti ve vinyet
    açısı değişir. Böylece aynı doku videonun tamamında tekrar etmez
    (tek doku = gözle görülür "aynı sahne" hissi).
    """
    grain = 4 + (variant % 3)
    return (
        "eq=contrast=1.12:brightness=-0.02:saturation=1.18,"
        f"vignette=PI/{4 + (variant % 3)},"
        f"noise=alls={grain}:allf=t+u"
    )


def render_video(
    clip_paths: list[str],
    audio_path: str,
    srt_path: str,
    output_path: str,
    work_dir: str,
    clip_duration: float = CLIP_DURATION,
    xfade_duration: float = XFADE_DURATION,
    bgm_path: str | None = None,
    bgm_volume: float = 0.15,
    cinematic_grade: bool = True,
    sfx_path: str | None = None,
    apply_zoompan: bool = True,
    max_scenes: int | None = None,
    stats_out: dict | None = None,
) -> str:
    if not clip_paths:
        raise ValueError("render_video needs at least one clip")

    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    audio_duration = get_audio_duration(audio_path)

    # Sahne planı ses süresinden türetilir: eksik kalanı başa sarmak YOK.
    # Hızlı ritimli (kısa klip, clip_duration <= 2.5) kurguda eldeki klip sayısı çok azsa
    # aşırı slayt tekrarını önlemek için sahne sayısı tavana çekilir (en fazla MAX_CLIP_REUSE_TARGET kez kullanım).
    effective_max_scenes = max_scenes
    if effective_max_scenes is None and clip_duration <= 2.5:
        effective_max_scenes = max(int(len(clip_paths) * MAX_CLIP_REUSE_TARGET), 1)

    durations = plan_scene_schedule(
        audio_duration,
        base_duration=clip_duration,
        xfade_duration=xfade_duration,
        max_scenes=effective_max_scenes,
    )
    sources = build_scene_sources(clip_paths, len(durations))
    reuse = clip_reuse_ratio(clip_paths, len(sources))
    if stats_out is not None:
        stats_out.update(
            {
                "scene_count": len(sources),
                "clip_count": len(clip_paths),
                "clip_reuse_ratio": reuse,
                "audio_duration": round(audio_duration, 2),
            }
        )

    # Her input için normalize + sabit süre (trim) filtresi.
    # STILLS → zoompan Ken Burns. LIVE stock video → scale/crop Ken Burns
    # (zoompan freezes frame 0 — never apply it to motion clips).
    normalize = _normalize_filter()
    zoompan = _zoompan_filter(clip_duration=clip_duration)
    inputs: list[str] = []
    filter_parts: list[str] = []
    labels: list[str] = []
    for i, (clip, seek) in enumerate(sources):
        is_image = Path(clip).suffix.lower() in IMAGE_SUFFIXES
        # Klibin farklı bir anından başla (tekrar kullanımda bile yeni kare).
        if seek > 0 and not is_image:
            inputs += ["-ss", f"{seek:.2f}", "-i", clip]
        else:
            inputs += ["-i", clip]

        label = f"[v{i}]"
        scene_duration = durations[i]
        # tpad: kısa/seek edilmiş kaynakta bile trim'in dolmasını garanti eder.
        tail = (
            f"trim=duration={scene_duration},setpts=PTS-STARTPTS,"
            f"tpad=stop_mode=clone:stop_duration={scene_duration},"
            f"trim=duration={scene_duration},setpts=PTS-STARTPTS,fps={FPS}"
        )
        if is_image:
            chain = f"[{i}:v]{normalize},{zoompan},{tail}"
        elif apply_zoompan:
            live_kb = _live_kenburns_filter(scene_duration)
            chain = f"[{i}:v]{normalize},{live_kb},{tail}"
        else:
            # Native motion preserved (no Ken Burns).
            chain = f"[{i}:v]{normalize},{tail}"
        if cinematic_grade:
            # Sahne başına farklı doku: aynı grain/vinyet tekrarı kırılır.
            chain += f",{_grade_ops(i)}"
        filter_parts.append(f"{chain},format=yuv420p{label}")
        labels.append(f"v{i}")

    # xfade ile zincirle (her geçişte farklı efekt, kümülatif offset).
    filter_parts.append(
        _xfade_chain_filter(
            labels, durations=durations, xfade_duration=xfade_duration
        )
    )

    # Alt yazıyı en son (net ve parlak kalacak şekilde) uygula.
    escaped_srt = _escape_for_filter(srt_path)
    filter_parts.append(f"[vout]subtitles='{escaped_srt}'[vfinal]")

    # Audio inputları:
    video_input_count = len(sources)
    inputs += ["-i", audio_path]

    audio_layers = [f"[{video_input_count}:a]volume=1.0[aspeech]"]
    mix_sources = ["[aspeech]"]

    next_audio_idx = video_input_count + 1

    if sfx_path and Path(sfx_path).is_file():
        inputs += ["-i", sfx_path]
        audio_layers.append(f"[{next_audio_idx}:a]volume=0.35[asfx]")
        mix_sources.append("[asfx]")
        next_audio_idx += 1

    if bgm_path and Path(bgm_path).is_file():
        inputs += ["-i", bgm_path]
        audio_layers.append(
            f"[{next_audio_idx}:a]volume={bgm_volume},aloop=loop=-1:size=2e+09[abgm]"
        )
        mix_sources.append("[abgm]")
        next_audio_idx += 1

    if len(mix_sources) > 1:
        mix_str = "".join(mix_sources)
        audio_layers.append(
            f"{mix_str}amix=inputs={len(mix_sources)}:duration=first:dropout_transition=2[afinal]"
        )
        filter_parts.extend(audio_layers)
        audio_map = ["-map", "[afinal]"]
    else:
        audio_map = ["-map", f"{video_input_count}:a:0"]

    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vfinal]", *audio_map,
        "-c:v", "libx264", "-preset", "medium", "-crf", "18",
        "-c:a", "aac", "-b:a", "128k",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-shortest",
        output_path,
    ]

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {result.stderr[-2000:]}")

    return output_path


def _escape_for_filter(path: str) -> str:
    # ffmpeg filter args treat ':' and '\' specially inside quoted values.
    return path.replace("\\", "\\\\").replace(":", "\\:")

