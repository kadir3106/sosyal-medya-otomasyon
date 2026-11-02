# Sızıntı temizliği — döndürme rehberi ve geçmiş yeniden yazımı

> Bu belge **yıkıcı işlem** talimatları içerir. Hiçbir komut bu belgeyi yazan ajan tarafından çalıştırılmadı; sırayla sizin onayınızla koşulmalıdır.
>
> Ölçüm tarihi: **2026-11-02**, branch `cursor/hybrid-flux-architecture`.

## 1. Ne sızdı (ölçülmüş)

| Kalem | Konum | Neden tehlikeli |
| --- | --- | --- |
| `video-output/tiktok_session/` | **1015 dosya**, 2 commit | Chromium profili: `Network/Cookies`, `Login Data`, `Local State`, `Web Data`. TikTok oturum çerezleri = hesabı ele geçirme. |
| `backups/otomasyon-yedek-2026-09-05.tar.gz` | 1 dosya, 889 KB, commit `a3682ba` | İçinde **iç içe `n8n-data.tar`** (5.7 MB) var: |
| └ `n8n-data.tar` → `./database.sqlite` | 1.5 MB + 4.1 MB `-wal` | n8n'in tüm credential deposu. |
| └ `n8n-data.tar` → `./config` | 56 bayt | **`encryptionKey` (32 karakter)** — n8n credential'larını çözen anahtar. Veritabanı tek başına sızdıysa şifreli; bu anahtarla birlikte **düz metin**. |
| └ `media/used_topics.json`, `used_image_topics.json` | 2 dosya | Sır değil, ama iş verisi. |

`.env` **hiç commit edilmedi** (`.gitignore:2`). Yerel diskte 9 dolu anahtar var.

**Sonuç:** Bu tek arşiv, n8n üzerinden yönetilen **her** kimlik bilgisini açığa çıkarmış sayılmalıdır.

## 2. Döndürme listesi (sırayla)

Her satır: ne yapılacak → nereden → doğrulama. Değerleri bu dosyaya **yazmayın**.

### 2.1 Önce n8n anahtarı (en kritik)

`encryptionKey` + `database.sqlite` birlikte sızdığı için, n8n'de duran bütün credential'lar açık kabul edilir.

1. n8n'i durdurun: `docker compose stop n8n`
2. n8n arayüzünde tüm credential'ları tek tek **silin ve yeniden girin** (yeni API anahtarlarıyla)
3. n8n'i **temiz bir volume** ile yeniden kurun: `docker compose down -v n8n` (⚠️ volume silinir)
4. n8n'i açıp yeniden kurun, workflow'ları içe aktarın

> Anahtarı değiştirip veritabanını korumak çalışmaz: n8n eski anahtarla şifrelenmiş credential'ları okuyamaz. Doğru sıra "credential'ları yenile → volume'u sıfırla".

### 2.2 TikTok

1. TikTok → Settings → Security → **Log out of all devices**
2. Aynı hesapta şifreyi de değiştirin (oturum çerezi tek başına yeterliydi, ama savunma derinliği).
3. Tarayıcı oturumu gerekiyorsa yeniden üretin: `python scripts/refresh_tiktok_session.py`
4. TikTok Developer panelinden **PKCE/OAuth token'larını** iptal edin (`TIKTOK_CLIENT_KEY`/`SECRET` uygulaması).

### 2.3 Google / YouTube

`YOUTUBE_REFRESH_TOKEN` yapılandırılmış (`.env`). n8n credential'ları arasında da bulunmuş olabilir.

1. https://myaccount.google.com/permissions → projeye erişimi **kaldır**
2. Google Cloud Console → APIs & Services → Credentials → OAuth client → **reset secret**
3. Yeni refresh token alın ve `.env`'e yazın.

### 2.4 Meta / Facebook

`META_PAGE_ACCESS_TOKEN` yapılandırılmış.

1. https://developers.facebook.com/tools/debug/accesstoken/ → **Debug** → token'ı görüp iptal edin
2. Business Settings → System Users → token'ı **revoke** edip yeniden üretin

### 2.5 X (Twitter)

`X_REFRESH_TOKEN` yapılandırılmış.

1. https://developer.x.com/en/portal/dashboard → uygulamanız → **Keys and tokens** → *Revoke* (access token + secret, refresh token)
2. Yeniden üretin

### 2.6 Telegram bot

`TELEGRAM_BOT_TOKEN` yapılandırılmış.

1. [@BotFather](https://t.me/BotFather) → `/mybots` → botunuz → **API Token** → *Revoke current token*
2. Yeni token'ı `.env`'e yazın

### 2.7 FAL (görsel üretim)

`FAL_KEY` yapılandırılmış.

1. https://fal.ai/dashboard/keys → anahtarı **sil** → yeni anahtar üretin

### 2.8 n8n arayüz şifresi

`N8N_PASSWORD` `.env`'de. n8n volume'u sıfırlanınca zaten yeniden kurulacak; yeni ve farklı bir şifre belirleyin.

### 2.9 Diğerleri

`.env`'de boş olsa da olası: `OPENROUTER_API_KEY`, `ELEVENLABS_API_KEY`, `PEXELS_API_KEY`, `GROQ_API_KEY`. n8n credential'larında bulunmuş olabilirler — panelden kontrol edip döndürün.

## 3. Geçmişten silme (`git filter-repo`)

### 3.1 Ön koşullar

```powershell
python -m pip install git-filter-repo
git filter-repo --version        # kuruldu mu
```

> `git-filter-repo` bu makinede **kurulu değildi** (ölçüldü: `git: 'filter-repo' is not a git command`). Kurulum zorunlu.

### 3.2 Yedek alın (zorunlu — geri dönüş yolu budur)

```powershell
cd c:\Projects\sosyal-medya-otomasyon
git bundle create ..\sosyal-medya-YEDEK-$(Get-Date -Format yyyyMMdd-HHmm).bundle --all
```

Geri dönmek gerekirse: `git clone ..\sosyal-medya-YEDEK-*.bundle geri-donus`

### 3.3 Ekip uyarısı

Geçmiş yeniden yazıldığında **tüm commit hash'leri değişir**. Bu branch'i klonlamış herkes yeniden klonlamalı; açık PR varsa kapanır. Tek başınıza çalışıyorsanız sorun yok.

### 3.4 Silme

Silmek istediğimiz yollar (ikisi de bugün gitignore'lu, ama geçmişte var):

```
video-output/tiktok_session/
backups/otomasyon-yedek-2026-09-05.tar.gz
```

```powershell
cd c:\Projects\sosyal-medya-otomasyon
git filter-repo --invert-paths `
  --path video-output/tiktok_session `
  --path backups/otomasyon-yedek-2026-09-05.tar.gz `
  --force
```

> `--path` bir dizini hedeflediğinde altındaki her şeyi siler. `--use-base-name` **kullanmayın** — aynı ada sahip başka dizinleri de siler.

### 3.5 Doğrulama (silme gerçekten oldu mu)

```powershell
# Oturum dosyası kalmadı mı? 0 dönmeli
(git log --all --pretty=format: --name-only -- 'video-output/tiktok_session/*' | Where-Object { $_ }).Count

# Yedek arşiv kaldı mı? 0 dönmeli
(git rev-list --all --objects | Select-String 'otomasyon-yedek').Count

# Tarayıcı da doğrulasın
python scripts/secret_scan.py --history
```

### 3.6 Baseline'ı boşaltın

```powershell
python scripts/secret_scan.py --history --update-baseline
```

Beklenen: `0 bulgu`. `scripts/secret_scan_baseline.json` içindeki `accepted` dizisi boşalır.

> ⚠️ Baseline'ı **geçmiş temizlenmeden** boşaltmayın: tarayıcı aynı 15 bulguyu "YENİ" diye raporlar ve CI kırmızıya döner. Sıra önemlidir: önce `filter-repo`, sonra baseline.

### 3.7 Yayınlama (force-push)

```powershell
git push --force-with-lease origin cursor/hybrid-flux-architecture
```

`--force-with-lease` kullanın, `--force` değil: biri siz yokken push yaptıysa işlemi durdurur.

> **Branch koruması** varsa force-push reddedilir. O durumda GitHub → Settings → Branches → korumayı geçici kaldırın, push edin, geri açın.

### 3.8 Eski nesneleri atın (önerilir)

```powershell
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

GitHub tarafında eski commit'ler erişilemez olsa da **nesne olarak kalır**; GitHub Support'tan GC talep etmeden tamamen silinmez. Depo public idiyse sızan değerleri "artık erişilemez" saymak yeterli **değildir** — bu yüzden Bölüm 2 (döndürme) zorunlu, Bölüm 3 (silme) hijyendir.

## 4. Sıra özeti (kritik)

1. **Bölüm 2 — döndürme.** Sızıntı zaten public'ti; silmek onu geri almaz. Döndürme asıl güvenlik işidir.
2. **Bölüm 3 — geçmiş silme.** Hijyen; tekrarını engeller.
3. **Bölüm 3.6 — baseline boşaltma.** En son.
4. **CI yeşil mi:** `lint`, `secret-scan`, `history-scan`, `test`.

## 5. Bunu bir daha yaşamamak için (hâlihazırda yapıldı)

| Önlem | Durum |
| --- | --- |
| `.gitignore` oturum/arşiv yollarını kapsıyor | ✅ |
| Sır tarayıcısı **geçmişi** tarıyor (`--history`) | ✅ madde 26 |
| Yol tabanlı dedektörler (tarayıcı profili, `.env`, arşiv) | ✅ madde 26 + 29.7 |
| Commit edilmiş **arşivler açılıp** taranıyor | ✅ madde 29.7 |
| CI'da `history-scan` işi (`fetch-depth: 0`) | ✅ |
| Baseline: yeni sızıntıyı yakalar, bilineni susturur | ✅ |

**Kalan risk:** tarayıcı arşivleri açıyor ama **özyinelemeli değil** — bir `.tar.gz` içindeki başka bir arşivi açmıyor. Bu yedekte iç arşiv `n8n-data.tar` idi ve yalnızca elle açıldı, yani `database.sqlite` + `encryptionKey` otomatik taranmadı. Yeni bir kör nokta sınıfı olarak kayıtlı; gerekirse `read_archive_texts`'e derinlik sınırlı özyineleme eklenmeli.
