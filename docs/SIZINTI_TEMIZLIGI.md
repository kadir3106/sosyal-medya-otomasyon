# Sızıntı temizliği — döndürme rehberi ve geçmiş yeniden yazımı

> Ölçüm tarihi: **2026-11-02**, branch `cursor/hybrid-flux-architecture`.
>
> **Durum: Bölüm 3 (geçmiş yeniden yazımı) ve 3.6 (baseline) UYGULANDI.** Bölüm 2 (döndürme) **sizin** yapmanız gereken tek iş — panele giriş ve anahtar iptali gerektirdiği için ajan tarafından yapılmadı.
>
> Uygulananların kanıtı Bölüm 3.9'da.

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

### 2.1 Önce n8n anahtarı (ölçülmüş: 1 credential)

`encryptionKey` + `database.sqlite` birlikte sızdı, yani o tek credential **çözülebilir** durumda.

**Ölçüm (2026-11-02):** arşiv açıldı, `database.sqlite` + `database.sqlite-wal` + `config` **birlikte** okundu.

| Kalem | Değer |
| --- | --- |
| `credentials_entity` (yalnızca .sqlite) | **0** — yanıltıcı |
| `credentials_entity` (WAL dahil) | **1** |
| Credential | `Telegram - Otomasyon Bot`, tip `telegramApi` |
| `workflow_entity` | 0 (workflow yok) |
| `variables` | 0 |
| `user` | 1 (sahip hesabı) |
| `settings` | 4-5 (sadece chat/ldap/banner bayrakları) |
| `oauth_*`, `user_api_keys`, `secrets_provider_*` | hepsi 0 |

> ⚠️ `database.sqlite` tek başına açılırsa **0** credential görünür — n8n `journal_mode=wal` ile çalışıyor ve asıl veri `database.sqlite-wal` içinde. Yanlış dosyayı okumak "sızıntı yok" gibi görünür.

**Şifreleme gerçekten çözüldü (iddia değil, test):** `data` alanı base64 → `Salted__` (OpenSSL başlığı) + salt + AES-256-CBC gövdesi. `encryptionKey` doğrudan parola olarak `EVP_BytesToKey`'e verildiğinde `{"accessToken": ...}` JSON'u çıktı. Yani anahtar + veritabanı = **düz metin**.

1. n8n'i durdurun: `docker compose stop n8n`
2. BotFather → botunuz → **API Token → Revoke current token** → yeni token
3. Yeni token'ı `.env`'e yazın
4. n8n'i **temiz bir volume** ile yeniden kurun: `docker compose down -v n8n` (⚠️ volume silinir)

> n8n'de yeniden girilecek **başka credential yok** (tablo 0). Ama eski `encryptionKey` + veritabanı `backups/` klasöründe **hâlâ diskte** — bunları da silin, yoksa aynı sır okunabilir kalır.

### 2.1b TikTok tarayıcı oturumu (ölçülmüş: 1096 dosya)

`video-output/tiktok_session/` **git'ten çıktı ama diskte duruyor** (`1096` dosya). İçinde `Default/Network/Cookies` ve `Default/Login Data` var.

1. TikTok → Settings → Security → **Log out of all devices**
2. Şifreyi de değiştirin
3. Yerel profili silin: `Remove-Item video-output/tiktok_session -Recurse -Force`
4. Gerekiyorsa yeniden üretin: `python scripts/refresh_tiktok_session.py`


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

Silinen yollar — **belgede ilk yazılan 2 yol değil, 5 yol** çıktı. Ölçüm sırasında `.tiktok_pkce.json` (`code_verifier`, kimlik doğrulama artefaktı) ve ekran görüntüleri de geçmişte bulundu; ikinci bir yeniden yazım gerekmesin diye tek geçişte çıkarıldı.

```
video-output/tiktok_session/                       (1015 dosya)
backups/otomasyon-yedek-2026-09-05.tar.gz          (889 KB, n8n encryptionKey)
.tiktok_pkce.json                                  (PKCE code_verifier)
video-output/tiktok_*.png                          (13 ekran görüntüsü, HEAD'de takipliydi)
```

```powershell
cd c:\Projects\sosyal-medya-otomasyon

# 1) YEDEK — atlanmaz. 131 MB, "is okay", 8 ref doğrulandı.
git bundle create ..\sosyal-medya-otomasyon-YEDEK.bundle --all
git bundle verify ..\sosyal-medya-otomasyon-YEDEK.bundle

# 2) filter-repo (pip ile kurulur; bu makinede kurulu değildi)
python -m pip install git-filter-repo

# 3) Yeniden yazım
python -m git_filter_repo --invert-paths `
  --path video-output/tiktok_session `
  --path backups/otomasyon-yedek-2026-09-05.tar.gz `
  --path .tiktok_pkce.json `
  --path-glob 'video-output/tiktok_*.png' `
  --force

# 4) origin'i geri ekle (filter-repo siler — normal davranış)
git remote add origin https://github.com/kadir3106/sosyal-medya-otomasyon.git
```

> `--path` bir dizini hedeflediğinde altındaki her şeyi siler. `--use-base-name` **kullanmayın** — aynı ada sahip başka dizinleri de siler.
>
> `--path-glob` yerine `--path` + joker kullanılamaz; 13 PNG için glob şart.


### 3.5 Doğrulama (silme gerçekten oldu mu)

```powershell
# Oturum dosyası kalmadı mı? 0 dönmeli
(git log --all --pretty=format: --name-only -- 'video-output/tiktok_session/' | Where-Object { $_ }).Count

# Yedek arşiv kaldı mı? 0 dönmeli
(git rev-list --all --objects | Select-String 'otomasyon-yedek').Count

# PKCE ve ekran görüntüleri
(git log --all --pretty=format: --name-only -- '.tiktok_pkce.json' | Where-Object { $_ }).Count
(git log --all --pretty=format: --name-only -- 'video-output/tiktok_*.png' | Where-Object { $_ }).Count

# Tarayıcı da doğrulasın (ikisi de 0 dönmeli)
python scripts/secret_scan.py;           "cikis: $LASTEXITCODE"
python scripts/secret_scan.py --history; "cikis: $LASTEXITCODE"
```

### 3.6 Baseline'ı güncelleyin

```powershell
python scripts/secret_scan.py --history --update-baseline
```

**Beklenti "0 bulgu" DEĞİL.** Bu belgenin ilk sürümü `accepted` dizisinin tamamen boşalacağını yazıyordu; ölçüm bunu **yanlışladı**:

| | Önce | Sonra |
| --- | --- | --- |
| Geçmiş bulgusu | 15 | **9** |
| Baseline girdisi | 15 | **8** |
| Bulgu türü | 6 yol + 9 içerik | **0 yol + 9 içerik** |
| Baseline'daki yol | 6 (5'i sızıntı + 1 tarayıcının kendi testi) | **2 (yalnızca test dosyası)** |

Sıfırlanmayan 9 bulgu tarayıcının **kendi test fixture'larıdır**: `video-worker/tests/test_secret_scan.py` ve `test_secret_scan_history.py` içindeki `_fake("sk-")`, `"sk-" + "A" * 30`, `sk-your_key_here_placeholder` gibi **sahte** değerler. Bunlar kalmalı — tarayıcının kendini test etmesi için gerekli.

Yeniden üretim **bayat girdileri de attı**: eski baseline artık var olmayan 6 yolu "kabul edilmiş" saymaya devam ediyordu. Bu sessiz bir riskti — `--update-baseline` yerine elle düzenleseydik, aynı yollarda **yeni** bir sızıntı çıksa yutulurdu.


> ⚠️ Baseline'ı **geçmiş temizlenmeden** güncellemeyin: tarayıcı aynı 15 bulguyu "YENİ" diye raporlar ve CI kırmızıya döner. Sıra önemlidir: önce `filter-repo`, sonra baseline.

### 3.7 Yayınlama (force-push)

```powershell
git fetch origin
git push --force origin cursor/hybrid-flux-architecture
```

`--force-with-lease` **tercih edilir**, ama yeniden yazımdan sonra çalışmaz: lease `refs/remotes/origin/*` üzerinden karşılaştırma yapar ve filter-repo uzak izleme ref'lerini sildi. Bu yüzden `git fetch origin` ile uzakta sizden habersiz commit olmadığını **elle** doğrulayıp `--force` kullanın.

> **Branch koruması** varsa force-push reddedilir. O durumda GitHub → Settings → Branches → korumayı geçici kaldırın, push edin, geri açın.

### 3.8 Eski nesneleri atın (önerilir)

```powershell
git reflog expire --expire=now --all
git gc --prune=now --aggressive
```

GitHub tarafında eski commit'ler erişilemez olsa da **nesne olarak kalır**; GitHub Support'tan GC talep etmeden tamamen silinmez. Depo public idiyse sızan değerleri "artık erişilemez" saymak yeterli **değildir** — bu yüzden Bölüm 2 (döndürme) zorunlu, Bölüm 3 (silme) hijyendir.

### 3.9 Uygulama kanıtı (2026-11-02, bu makinede koşuldu)

| Adım | Sonuç |
| --- | --- |
| `git bundle create --all` | 131 MB, `verify` → **"is okay"**, 8 ref |
| `git-filter-repo` kurulumu | `2.47.0` (makinede yoktu, pip ile kuruldu) |
| Yeniden yazım | 73 commit → **73 commit** (yalnızca yollar silindi), 0.82 sn |
| Commit hash'i | `c09ee1c` → **`9763f25`** (tüm geçmiş değişti — beklenen) |
| `origin` | filter-repo sildi, elle geri eklendi |
| 4 yol kontrolü | hepsi **0** |
| `secret_scan` | 757 dosya temiz, çıkış **0** |
| `secret_scan --history` | 9 bulgu / 0 yol / **0 YENİ**, çıkış **0** |
| `pytest -q` | **808 passed, 3 skipped** |
| HEAD'de kalan eşleşme | yalnızca `scripts/refresh_tiktok_session.py` (meşru script) |
| Uzak `tiktok_session` (API) | **404** |
| Uzak `backups/` (API) | yalnızca `.gitkeep` |
| Tüm dallar force-push | `main` `d815276`→`e8c7178`, feature `c09ee1c`→`77b2caf`, kling + visual-relevance yeni |
| CI (`41405401882`, yeniden koşu) | **4/4 yeşil:** lint, test, secret-scan, history-scan |

Yeniden yazım sırasında hangi yolların çıktığı **ölçümle** belirlendi, tahminle değil: `git log --all --name-only` ile tüm geçmişteki benzersiz yollar süzüldü. Belgede ilk yazılan 2 yol eksikti; `.tiktok_pkce.json` ve 13 PNG de bulundu.

> Fotoğraf/ekran görüntüsü yolları `--path-glob 'video-output/tiktok_*.png'` ile silindi. `--path` joker kabul etmez.
>
> `git_filter_repo` doğrudan çalışmazsa `python -m git_filter_repo` kullanın (Windows'ta PATH'e güvenmeyin).

### 3.10 Tek dalı yeniden yazmak YETMEZ (bu turda yaşandı)

İlk `filter-repo` yalnızca yerel repoyu yeniden yazdı. `--all` kullandım, ama **sonra yalnızca `cursor/hybrid-flux-architecture` push edildi**. Sonuç:

- Feature branch temizlendi (`77b2caf`), CI'a gitti,
- ama `main` **hâlâ `d815276`** = eski geçmiş, sızıntı yerinde,
- CI `actions/checkout` (tüm dalları çeker) + `fetch-depth: 0` ile eski `main`'i gördü,
- **`history-scan` kırmızı:** `15 bulgu (6 yol, 9 içerik); 6 YENİ`.

Bu ilk bakışta "düzeltme işe yaramadı" gibi görünüyor; aslında düzeltme doğruydu, **yayını eksikti**.

```powershell
# Yerelde hangi dallar var ve hepsi temiz mi?
git for-each-ref --format='%(refname:short) %(objectname:short)' refs/heads
# Uzakta hangi dallar var? (yerel liste yanıltır)
gh api 'repos/<owner>/<repo>/branches' --jq '.[] | .name + " = " + .commit.sha'
```

Sonra **her** dalı force-push edin:

```powershell
git push --force origin main
git push --force origin <diger-dallar>
```

Doğrulama (hepsi 0 dönmeli):

```powershell
foreach ($b in 'main','cursor/hybrid-flux-architecture') {
  "$b : " + @(git log $b --pretty=format: --name-only -- 'video-output/tiktok_session/' | Where-Object { $_ }).Count
}
```

Push'tan sonra başarısız CI koşusunu yeniden tetikleyin (`gh run rerun <id>`); `history-scan` bu kez tüm dallarda temiz geçmiş görür.

> **Not:** `main`'de `.github/` yok (CI yalnızca feature branch'te tanımlı), o yüzden `main`'e push CI **tetiklemez**. Doğrulama için feature branch'in koşusunu yeniden çalıştırın — `fetch-depth: 0` ile `main`'i de görür.

### 3.11 Yerel yedeği güvene alın, sonra silin

`git bundle` yedeği (131 MB) **sızıntılı nesneleri taşır**: `tiktok_session` profili, `n8n encryptionKey` içeren tarball. Bir yedek dizininizde durması, temizlediğiniz şeyi yeniden yaymanın en kolay yoludur.

```powershell
# Yeniden yazımın doğru olduğunu teyit ettikten SONRA:
git reflog expire --expire=now --all
git gc --prune=now --aggressive
# bundle'ı şifreli bir arşive taşıyın veya silin
```


## 4. Sıra özeti (kritik)

1. **Bölüm 2 — döndürme.** Sızıntı zaten public'ti; silmek onu geri almaz. Döndürme asıl güvenlik işidir. ❌ **Yapılmadı — sizin yapmanız gerek.**
2. **Bölüm 3 — geçmiş silme.** Hijyen; tekrarını engeller. ✅ **Yapıldı** (3.9).
3. **Bölüm 3.10 — tüm dalları yayınlama.** ✅ **Yapıldı** (bu adım ilk turda atlanmıştı, CI yakaladı).
4. **Bölüm 3.6 — baseline.** ✅ **Yapıldı** (15 → 8).
5. **CI yeşil mi:** `lint`, `secret-scan`, `history-scan`, `test`. ✅ **4/4.**

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
