# "Slayt Gibi Tekrar" Sorunu — Teşhis ve Çözüm (15 Eylül 2026)

## Sorun

Üretilen videolar slayt gösterisi gibi hissettiriyor: aynı görüntüler tekrar tekrar
ekrana dönüyor, ritim tek düze, kesmeler monoton.

## Teşhis — ölçülmüş kök neden

Tahmin değil; gerçek üretim çıktısından ölçtüm (`video-output/work/rolex_dark_wealth/`):

| Ölçüm | Değer |
|---|---|
| `speech.mp3` (TTS) | **30.888 sn** |
| Üretilen klip | **6 adet** |
| `render.py` sahne süresi | 2.2 sn |
| Geçiş (xfade) | 0.4 sn |
| Ekranda görünür süre/klip | 1.8 sn |
| **Gereken sahne** | `ceil((30.888-0.4)/1.8)` = **17** |
| **Tekrar oranı** | 17 ÷ 6 = **2.83x** |

**Her görüntü ortalama 3 kez gösteriliyordu.** Kök neden `render.py`'deki ham döngü:

```python
# ESKİ KOD — klipler bitince başa sarıyordu
while len(repeated) < clip_count:
    repeated.extend(clip_paths)
```

Üretim (sabit 6 sahne) ile render'ın ihtiyacı (ses süresinden hesaplanan 17) arasında
**hiçbir senkron yoktu**.

### Eşlik eden 6 sebep

1. **Sahne sayısı sabit**: `script_gen.py` promptu "6 adet kronolojik prompt" istiyordu;
   `CLIP_COUNT = 10` de sabitti. TTS 30 sn üretince yetmiyordu.
2. **Stok videolar 2.2 sn'ye trim ediliyordu**: 6 klip × 1.8 sn = **10.8 sn gerçek
   görüntü**, kalan **20 sn tekrar**.
3. **Geçişler hep aynı**: sadece `fade`. 17 kesim boyunca aynı geçiş = monoton ritim.
4. **Film grain sabit** (`noise=alls=6`): her sahnede aynı doku → gözle görülür tekrar.
5. **`VISUAL_ENGINE=kling` çalışmıyordu**: `ai_video_engine.py` her modda yalnızca
   `prompts[0]` için Kling çağırıyordu; `kling` seçilse bile kalanı stok videoya düşüyordu.
6. **AI görsel yolunda tekrar koruması yoktu**: `used_clips.json` sadece stok yol için
   vardı; `scene_N.jpg` (Ken Burns) yolu aynı promptu tekrar üretiyordu.

### Kritik uyarı

Bu davranış **teste yazılmıştı**: `test_render.py` içinde
`[a,b] döngüsü [a,b,a,b,a,b,a]` beklentisi vardı. Yani "klibi başa sar" davranışı
bilerek kilitlenmişti — testleri güncellemeden yapılan düzeltme "çalışıyor" görünen
bir yalan olurdu.

---

## Çözüm

### Faz 1 — Tekrar döngüsü kökten kaldırıldı

- `plan_scene_schedule()`: sahne sayısı **ses süresinden** hesaplanır. Kimse başa sarılmaz.
- `build_scene_sources()`: ham döngü yerine **adil dağıtım** — en az kullanılan klip
  seçilir ve **aynı klip asla arka arkaya gelmez**.
- Tekrar kullanılan klip **farklı bir saniyesinden** başlatılır (`-ss` ile), yani aynı
  klip bile yeni kare gösterir.
- `clip_reuse_ratio()` + `stats_out`: tekrar oranı ölçülür, `render_done` log'una girer.

### Faz 2 — Sahne üretimi süreye bağlandı

- `script_gen.py` promptu: "*sabit 6 değil, script'in HER CÜMLESİ için 1 sahne
  (10-16 prompt). Her prompt FARKLI mekan/özne/açı/kamera hareketi içersin.*"
- `ai_video_engine.generate_video_scenes(target_count=...)`: istenen sahne sayısı kadar
  görsel üretir; prompt listesi kısaysa **farklı kamera açıları** türetir.
- `kling` modu düzeltildi: tüm sahneler için Kling çağrılır (`KLING_MAX_SCENES` tavanı ile,
  varsayılan 3). `hybrid` modu hook sahnesini Kling'den alır.
- `stock_media.py`: aynı keyword asla art arda gelmez (`_next_keyword`); arama başarısız
  olursa bir sonraki kelimeye geçer.
- **En yüksek çözünürlüklü** dosya seçilir (rastgele seçim 360p klibi getirip görüntüyü
  bulanıklaştırıyordu).
- `refresh_repeated_prompts()` + `used_prompts.json`: AI promptları için tekrar hafızası.

### Faz 3 — Slayt hissini kıran dinamik kurgu

- **Değişken ritim**: kanca 1.6 sn (hızlı), anlatı 2.2 sn, kapanış 2.6 sn.
- **Geçiş çeşitliliği**: `fade, circleopen, smoothleft, fadeblack, dissolve` sırayla.
- **Sahne başına değişen doku**: grain şiddeti (4-6) ve vinyet açısı sahneye göre değişir.
- **SFX senkronu düzeltildi**: `build_sfx_track(transition_times=...)` artık render'ın
  hesapladığı gerçek geçiş anlarını alır. Eski kod sabit 2.5 sn varsayıyordu ve render
  2.2 sn kullanıyordu → whoosh'lar görüntüden **0.3 sn kayıktı**.
- Çıktı süresi tam ses süresine oturtulur (fazlalık `-shortest` ile kesilmiyor).
- `tpad` filtresi: `-ss` ile kısaltılan kaynakta bile sahne süresi dolar.

### Faz 4 — Kalite kapısı (bir daha olmasın)

- `pipeline.py`: `clip_reuse_ratio > 1.35` ise `quality_warning` log'u + UYARI basılır.
- Sonuç `pending.json`'a `quality` bloğu ekler: `scene_count`, `clip_count`,
  `clip_reuse_ratio`, `engine`, gerekirse `warning`.
- n8n Telegram onay mesajı bu bilgiyi gösterir:
  `⚙️ 18 sahne · tekrar 1.0x · stock motor` + gerekirse `⚠️ TEKRAR YÜKSEK`.

### Ek: eksik klip senaryosu

Klip sayısı yetmediğinde (stok kota dolu / Kling düştü) sahne sayısı
`MAX_CLIP_REUSE_TARGET` (2.0x) tavanına çekilir — 4 klip + 30 sn ses:
18 sahne (4.5x tekrar) yerine **8 sahne (2.0x)**. Sahne süreleri `MAX_SCENE_DURATION`
(6.0 sn) sınırını aşmaz, çünkü 10 sn'lik donuk kare tekrar eden görüntüden daha kötüdür.

---

## Sonuç — ölçülmüş önce/sonra

`python scripts/verify_no_slideshow.py` (gerçek ffmpeg ile üretir, exit 0):

| | Önce | Sonra |
|---|---|---|
| Sahne sayısı | 6 (sabit) | **18** (ses süresinden) |
| **Tekrar oranı** | **2.83x** | **1.0x** |
| Geçiş çeşidi | 1 (`fade`) | 5 |
| Ritim | Sabit 2.2 sn | 1.6 / 2.2 / 2.6 sn |
| Çıktı süresi | — | 30.90 sn (ses ile birebir) |
| Çözünürlük | 1080x1920 | 1080x1920 (927 kare) |

Eksik klip senaryosu: 4 klip + 30 sn ses → 8 sahne, tekrar **2.0x** (eski davranış 4.5x),
aynı klip arka arkaya gelmiyor, tekrar eden klip farklı andan kesiliyor.

---

## Değişen dosyalar

**Uygulama**
- `video-worker/app/render.py` — sahne planı, adil kaynak dağıtımı, değişken ritim,
  çeşitli geçişler, sahne başına doku, `stats_out`, `scene_transition_times()`
- `video-worker/app/pipeline.py` — dinamik sahne sayısı, SFX senkronu, kalite kapısı
- `video-worker/app/ai_video_engine.py` — `target_count`, kling modu düzeltmesi,
  `KLING_MAX_SCENES`, prompt tekrar hafızası, Kling zaman aşımı
- `video-worker/app/ai_visuals.py` — `generate_ai_scene_clips(start_index=...)`
- `video-worker/app/stock_media.py` — keyword tekrarı, en yüksek çözünürlük, hata toleransı
- `video-worker/app/script_gen.py` — cümle bazlı sahne promptu (EN + TR)
- `video-worker/app/sfx.py` — `transition_times` parametresi
- `video-worker/app/config.py` — `KLING_MAX_SCENES`
- `n8n-workflows/workflow_a_daily_video_pipeline.json` — onay mesajında kalite bilgisi

**Testler (165 geçiyor)**
- `tests/test_render.py` — sahne planı, adil dağıtım, `-ss` kullanımı, tekrar oranı,
  eksik klip tavanı, geçiş zamanları
- `tests/test_ai_video_engine.py` — kling modu, `target_count`, prompt tazeleme,
  bozuk state toleransı
- `tests/test_pipeline.py` — süreye bağlı sahne planı, kalite kapısı uyarısı

**Doğrulama / demo**
- `scripts/verify_no_slideshow.py` — gerçek ffmpeg ile önce/sonra ölçümü (yeni)
- `scripts/generate_stoic_demo.py`, `scripts/generate_top_tier_demo.py` — eski sabit
  varsayımlardan dinamik plana geçirildi

**Yapılandırma**
- `.env.example` — `KLING_MAX_SCENES`

---

## Nasıl doğrularım?

```bash
# 1. Testler
cd video-worker && python -m pytest tests -q

# 2. Gerçek ffmpeg ile önce/sonra ölçümü (video üretir, ~1 dk)
python scripts/verify_no_slideshow.py

# 3. Üretimde kalite bilgisini gör
docker compose logs video-worker | grep -E "scene_plan|render_done|quality_warning"
```

Gerçek bir video üretiminde `scene_plan` log'unda `audio_seconds` ve `scene_count`
görünür; `render_done` satırında `clip_reuse_ratio` **1.0** olmalıdır. Telegram'daki
onay mesajı da bu değerleri gösterir.
