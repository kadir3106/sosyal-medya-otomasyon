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

**Sonuç:** Arşiv **çözülebilir** durumda ve içindeki tek credential **hâlâ geçerli**. Ama kapsam sanıldığından dar: n8n deposunda **1** credential, **0** workflow, **0** variable var (Bölüm 2.1'deki 130 tabloluk tarama). Yani "n8n üzerinden yönetilen her şey sızdı" **doğru değil** — Google/Meta/X/OpenRouter anahtarları `.env`'de yaşıyor, bu arşivde değil. Sızan üç şey: bot token'ı, n8n sahip parolası, TikTok oturumu.

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

**Şifreleme gerçekten çözüldü — üçüncü ölçüm, ilk tutan.** n8n'in kendi `CipherAes256CBC` uygulaması (`packages/core/src/encryption/aes-256-cbc.ts`) birebir uygulandı:

```
format   : base64( "Salted__" || salt(8 bayt) || AES-256-CBC(gövde) )
anahtar  : password = encryptionKey || salt          # 'binary' kodlama
           h1 = md5(password);  h2 = md5(h1 || password)
           iv = md5(h2 || password);  derivedKey = h1 || h2   # 32 bayt
```

Sonuç: `{"accessToken": "<46 karakter>"}` — **JSON çıktı, ilk denemede.**

> İki önceki ölçüm yanlıştı ve ikisi de aynı hatayı yapıyordu: base64 gövdesinin **ilk 16 baytını IV** sanıp kalanını şifreli metin sayıyorlardı. n8n formatında 8–16 arası **salt**tır, şifreli metin 16'dan başlar. Tuzu `getKeyAndIv`'ye vermek yerine IV olarak kullanmak, hangi anahtar türetmesi denenirse denensin (26 kombinasyon, md5/kırpılmış hash/16-32 bayt önek/ECB-CBC-CFB-OFB-CTR-GCM) yalnızca %30-46 yazdırılabilir çöp üretir. "Çözülemedi" sonucu **algoritmanın değil, benim ayrıştırmamın** hatasıydı.

**Sızan değerler hâlâ geçerli (ölçüldü, 2026-11-02):**

| Sır | Kanıt | Durum |
| --- | --- | --- |
| Telegram bot token (`accessToken`, 46 kar., fp `772d64de`) → `@mkadirmotivasyon_bot` | `getMe` → **HTTP 200** (bot yanıt veriyor) | ❗ **geçerli** |
| n8n sahip hesabı `admin@local.dev` | `user.password` bcrypt (`$2a$10$…`, 60 kar.) — `.env`'deki **mevcut** `N8N_PASSWORD` ile `checkpw` = **True** | ❗ **geçerli** |
| TikTok `sessionid` / `sid_guard` | 27 `.tiktok.com` çerezi, 20 `HttpOnly`; `sessionid` → **2027-03-16**, `sid_guard` → **2027-09-12** | ❗ **geçerli** |

> **`.env`'deki token bu değil.** Ayrı ölçüm: `.env TELEGRAM_BOT_TOKEN` → fp `e6094742` → `@kadir_shorts_studio_bot`. İki token **iki ayrı bota** ait ve ikisi de HTTP 200. Yani sızan bot prodüksiyon botu **değil**; `.env`'i değiştirmek gerekmiyor, hatta **zararlı** (çalışan botu bozar). Ayrıntı: Bölüm 2.6.

**Kapsam tam tarandı (130 tablo):** tüm metin kolonlarında `Salted__` blobu arandı → yalnızca **1** tane var, `credentials_entity.data`. `deployment_key` (4 satır), `execution_data`, `workflow_entity`, `variables`, `user_api_keys`, `oauth_*`, `secrets_provider_*` → hepsi temiz. Yani Google/Meta/X/OpenRouter token'ları bu arşivde **yok**; `.env`'dekiler bu sızıntıdan bağımsız.

1. n8n çalışıyorsa durdurun: `docker compose stop n8n`
   > Bu makinede Docker motoru **çalışmıyor** (Docker Desktop kurulu değil / `dockerDesktopLinuxEngine` yok) — ölçüldü. Yani bu adım atlanabilir; aşağıdaki panel işleri etkilenmez.
2. BotFather → **`@mkadirmotivasyon_bot`** → **API Token → Revoke current token**
   > `.env`'deki `@kadir_shorts_studio_bot` **değil**. Yeni token üretmek gerekmiyor; iptal yeterli.
3. **n8n sahip parolasını değiştirin** — bcrypt hash'i sızdı ve mevcut parolayla eşleşiyor. Parola değişene kadar aynı arşiv n8n'e giriş demektir.
4. n8n'i **temiz bir volume** ile yeniden kurun (yalnızca n8n'i yeniden kullanacaksanız): `docker compose down -v n8n` (⚠️ volume silinir)

> n8n'de yeniden girilecek **başka credential yok** (tablo 0). Ama eski `encryptionKey` + veritabanı `backups/` klasöründe **hâlâ diskte** — bunları da silin, yoksa aynı sır okunabilir kalır.

### 2.1b TikTok tarayıcı oturumu (ölçülmüş: 1015 dosya, 27 çerez)

`video-output/tiktok_session/` **git'ten çıktı ama diskte duruyor** — 148.3 MB, 1015 dosya. İçinde `Default/Network/Cookies`, `Login Data` (41 KB), `Local State` (4.8 KB), `Web Data` (170 KB).

**Çerez ölçümü (değerler okunmadı, yalnızca meta veri):**

| Kalem | Değer |
| --- | --- |
| Toplam çerez / TikTok | 28 / **27** (hepsi `.tiktok.com`) |
| Kalıcı / oturum çerezi | 27 / 0 — tarayıcı kapansa da geçerli |
| `HttpOnly` / `Secure` | 20 / 18 |
| `sessionid`, `sessionid_ss`, `sid_tt`, `uid_tt`, `uid_tt_ss` | bitiş **2027-03-16 17:43** |
| `sid_guard` | bitiş **2027-09-12 17:43** |

> Yani oturum "eski" değil: bugünden **~4.5 ay** daha geçerli bir `sessionid` var. Çerezler Chromium'un DPAPI/AES-GCM korumasıyla şifreli ama `Local State` de aynı profilde olduğu için aynı makinede **birlikte** açılabilir — arşivin n8n için geçerli olan mantığı burada da geçerli.

**Çerez meta verisi yetmedi, oturum canlı olarak da denendi (2026-11-02):** profil
kopyalanıp (asıl profil yazmaya karşı korunarak) headless Chromium ile
`https://www.tiktok.com/` açıldı → giriş duvarı **yok**, `sessionid`,
`sessionid_ss`, `sid_tt` çerezleri mevcut, sayfa normal akışta yüklendi. Yani
çerezler yalnızca "süresi geçmemiş" değil, **çalışır durumda**. Bu, iptal adımının
atlanabilir olmadığını kanıtlar.

1. **Telefonda TikTok uygulaması** → Profil → ☰ → Settings and privacy → **Security and login** → **Log out of all devices**
   > Web'de yok — Bölüm 2.1c'de ölçüldü. Yalnızca şifre değiştirmek yetmez;
   > `sid_guard` sunucu tarafında iptal edilmeli.
2. Şifreyi de değiştirin (aynı menü: **Password**)
3. **Bu sıradan sonra** yerel profili silin: `Remove-Item video-output/tiktok_session -Recurse -Force`

   > ⚠️ **Silmeden önce döndürün.** Bu profil prodüksiyonda kullanılıyor: `docker-compose.yml:76` `TIKTOK_SESSION_DIR=/data/tiktok-session` ile `scripts/refresh_tiktok_session.py --upload` üzerinden konteynere aktarılıyor. Döndürmeden silmek yayını durdurur. Sıra: **iptal → şifre → sil → yeniden üret.**
4. Gerekiyorsa yeniden üretin: `python scripts/refresh_tiktok_session.py --upload`

### 2.1c Bu adımlar betikle yapılabilir mi? (denendi — 2026-11-02)

Kısa cevap: **hayır, üçü de.** Üçü de tek tek denendi, sonuç aşağıda. Bu bölüm
"acaba otomatikleştirebilir miyiz" sorusunun her turda yeniden sorulmasını
önlemek için var.

| Adım | Panel | Otomatik? | Neden yapılamadı (ölçüm) |
| --- | --- | --- | --- |
| Telegram token iptali | BotFather → `/revoke` | ❌ | `.env`'de `api_id`, `api_hash`, `phone`, session-string **hiçbiri yok** → kullanıcı oturumu yok. Bot API'de "kendi token'ını iptal et" metodu da yok. |
| n8n parola değişimi | n8n UI → Settings → Users | ❌ | n8n yalnızca `localhost:5678`'de tanımlı ve **Docker motoru bu makinede çalışmıyor** — servis ayakta değil, parolanın değiştirileceği arayüz yok. |
| TikTok oturum iptali | **Mobil uygulama** → Settings → Security | ❌ | Oturum bu makinede **geçerli** (2.1b'de canlı olarak doğrulandı) ama web `/setting` sayfasında `log out` / `device` / `password` / `security` / `2fa` kelimelerinin **hiçbiri yok** — bölüm masaüstü web'de mevcut değil. |

TikTok web ayarlarının tam envanteri (headless Chromium, geçerli oturumla
açıldı): `Manage account`, `Privacy`, `Push notifications`, `Business
verification`, `Ads`, `Screen time`, `Content preferences`, `Family Pairing`,
`Accessibility`. **Güvenlik/oturum sekmesi yok.**

> Yani `scripts/verify_leak_rotation.py` yalnızca **ölçer**, döndürme yapmaz. O
> yüzden betik her çalıştığında açık kalan kalemler için panel adını ve
> "otomatik: HAYIR" hükmünü de yazdırır.



### 2.3 Google / YouTube

`YOUTUBE_REFRESH_TOKEN` yapılandırılmış (`.env`). **Ölçüm: bu arşivde Google/YouTube token'ı yok** — 130 tabloda tek bir şifreli blob bile YouTube'a ait değil (tek blob `telegramApi`). Yani aşağıdaki adımlar bu sızıntı için **zorunlu değil**; yalnızca genel hijyen olarak duruyor.

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

### 2.6 Telegram bot — **iki ayrı bot var, karıştırmayın**

Ölçüm (2026-11-02): sızan token ile `.env`'deki token **aynı değil**, ve ikisi de canlı:

| Token | Bot | Durum | Ne yapılmalı |
| --- | --- | --- | --- |
| Sızan (n8n arşivindeki `accessToken`, fp `772d64de`) | `@mkadirmotivasyon_bot` | HTTP 200 — **canlı** | ❗ BotFather'da **iptal et** |
| `.env`'deki `TELEGRAM_BOT_TOKEN` (fp `e6094742`) | `@kadir_shorts_studio_bot` | HTTP 200 — **canlı** | ✅ **DOKUNMAYIN** |

> ⚠️ Bu bölümün önceki hâli "yeni token'ı `.env`'e yazın" diyordu. **Bu yanlıştı ve çalışan botu bozardı.** Sızan bot prodüksiyon botu değil; `.env`'deki token sızmamış ve hâlâ geçerli. `.env`'e dokunmak gerekmez.

1. [@BotFather](https://t.me/BotFather) → `/mybots` → **`@mkadirmotivasyon_bot`** (`.env`'deki botu değil) → **API Token** → *Revoke current token*
2. İptal sonrası doğrulama: aşağıdaki betik `HTTP 401` dönmelidir

```powershell
# Sizan token gercekten oldu mu? (arsivden okuyup getMe cagirir)
python scripts/verify_leak_rotation.py --telegram
```

3. **`.env`'i değiştirmeyin.** Yeni token gerekmiyor; iptal yeterli. Botu silmek istiyorsanız BotFather → *Delete Bot* de dönmeyi imkânsız kılar.

> Aynı token `.env`'de `@kadir_shorts_studio_bot` için de kullanılmıyor mu diye kontrol edildi: hayır, iki ayrı değer (fp `772d64de` ≠ `e6094742`).

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

### 3.11 Yerel yedeği güvene alın (mühürleyin), sonra ölçün

`git bundle` yedeği (131 MB) **sızıntılı nesneleri taşır**: `tiktok_session` profili, `n8n encryptionKey` içeren tarball. Bir yedek dizininizde durması, temizlediğiniz şeyi yeniden yaymanın en kolay yoludur.

**Silmeyin — mühürleyin.** Silmek iki şeyi geri getirilemez biçimde yok eder: bundle, geçmişi geri almanın tek yolu (`git clone yedek.bundle`); tarball ise `verify_leak_rotation.py`'nin ölçüm aracı (silinirse betik çıkış kodu **2** verir).

```powershell
# Yeniden yazımın doğru olduğunu teyit ettikten SONRA:
git reflog expire --expire=now --all
git gc --prune=now --aggressive

# 1) Mühürle. Parola BİR KEZ stderr'e basılır — parola yöneticinize kaydedin.
python scripts/seal_leak_copies.py --generate-key `
    --path ..\sosyal-medya-otomasyon-YEDEK.bundle --seal --delete-originals
python scripts/seal_leak_copies.py --generate-key `
    --path backups\otomasyon-yedek-2026-09-05.tar.gz --seal --delete-originals

# 2) Ölç: artık "MÜHÜRLÜ" demeli, "HALA DISKTE" dememeli.
python scripts/verify_leak_rotation.py

# Geri dönmek gerekirse (parola ile):
python scripts/seal_leak_copies.py --open `
    --path ..\sosyal-medya-otomasyon-YEDEK.bundle.sealed --out geri-donus.bundle
```

Mühürleme AES-256-GCM + scrypt(n=2¹⁴). Betik **silmeden önce geri açıp bayt bayt karşılaştırır** — "yazdım" demek "okunabilir" demek değildir.

Ölçüm (2026-11-02) — mühürlemenin gerçekten sır sakladığı kanıtlandı:

| Dosya | `json_secret_field` bulgusu |
| --- | --- |
| `otomasyon-yedek-2026-09-05.tar.gz` | **1** (`./config` içinde `encryptionKey`) |
| aynı dosyanın `.sealed` hâli | **0** — arşiv olarak bile açılmıyor |

> **Parolayı kaybederseniz** mühürlü dosya silinmiş sayılır. Parolayı `.sealed` dosyasının yanına **koymayın** — aynı diski kaybetmek ikisini birden götürür.



## 4. Sıra özeti (kritik)

1. **Bölüm 2 — döndürme.** Sızıntı zaten public'ti; silmek onu geri almaz. Döndürme asıl güvenlik işidir. ❌ **Yapılmadı — sizin yapmanız gerek.** Ölçülen üç canlı sır, sırayla:
   1. **Telegram bot token'ı** → `@mkadirmotivasyon_bot` için BotFather'da revoke. En yüksek öncelik: token **hâlâ HTTP 200** dönüyor, yani bugün çalışıyor. ⚠️ `.env`'deki `@kadir_shorts_studio_bot` token'ı **değil** (fp `772d64de` ≠ `e6094742`) — yanlış botu iptal etmek prodüksiyonu bozar.
   2. **n8n sahip parolası** (`admin@local.dev`) → bcrypt hash sızdı ve **mevcut parolayla eşleşiyor**; parola değişene kadar arşiv n8n'e giriş demektir.
   3. **TikTok oturumu** → *log out of all devices*. `sessionid` **2027-03-16**'ya kadar geçerli.

   Google/Meta/X/OpenRouter anahtarları bu arşivde **yok** (130 tablo tarandı) — onlar için ek iş yok.

   **Durumu ölçmek için:** `python scripts/verify_leak_rotation.py` — 0 = hepsi etkisiz, 1 = açık var, 2 = ölçülemedi. Her adımdan sonra çalıştırın; panelde yapılan işi tahmin etmek yerine doğrular. Betiğin **kendi testleri** de artık CI'da gerçekten koşuyor: `cryptography`/`bcrypt` hiçbir requirements'ta olmadığı için 4 test `importorskip` ile sessizce atlanıyordu (ölçüldü: 7 passed, 4 skipped) — yani sır çözme yolunun hiç çalışmadığı bir CI'da "yeşil" görüntüsü alınıyordu. `video-worker/requirements-verify.txt` eklendi ve test job'ı atlama sayısı 3'ü geçerse **kırmızıya dönüyor**.
2. **Bölüm 3 — geçmiş silme.** Hijyen; tekrarını engeller. ✅ **Yapıldı** (3.9).
3. **Bölüm 3.10 — tüm dalları yayınlama.** ✅ **Yapıldı** (bu adım ilk turda atlanmıştı, CI yakaladı).
4. **Bölüm 3.6 — baseline.** ✅ **Yapıldı** (15 → 8).
5. **CI yeşil mi:** `lint`, `secret-scan`, `history-scan`, `test`. ✅ **4/4.** `test` artık 3 skip ile (şifreleme testleri dahil) koşuyor.

## 5. Bunu bir daha yaşamamak için (hâlihazırda yapıldı)

| Önlem | Durum |
| --- | --- |
| `.gitignore` oturum/arşiv yollarını kapsıyor | ✅ |
| Sır tarayıcısı **geçmişi** tarıyor (`--history`) | ✅ madde 26 |
| Yol tabanlı dedektörler (tarayıcı profili, `.env`, arşiv) | ✅ madde 26 + 29.7 |
| Commit edilmiş **arşivler açılıp** taranıyor | ✅ madde 29.7 |
| **İç içe arşivler** de açılıyor (`MAX_ARCHIVE_DEPTH=3`) | ✅ madde 31 |
| Derinlik sınırına takılan arşiv **bulgu** olarak raporlanıyor | ✅ madde 31 |
| Arşiv **içindeki** `Cookies`/`Login Data` yolu da yakalanıyor | ✅ madde 31 |
| JSON alan sırları (`"encryptionKey":"..."`) yakalanıyor | ✅ madde 31 |
| Disk üzerindeki yedek kopyaları ölçülüyor (`.gitignore` dışı) | ✅ madde 31 |
| Yedek kopyalar **mühürlenebiliyor** (AES-256-GCM, geri dönüşlü) | ✅ madde 32 |
| Adı farklı yedekler de taranıyor (venv/node_modules hariç) | ✅ madde 32 |
| Canlı oturum dizini raporlanıyor, silinmiyor | ✅ madde 32 |
| CI'da `history-scan` işi (`fetch-depth: 0`) | ✅ |
| Baseline: yeni sızıntıyı yakalar, bilineni susturur | ✅ |

### 5.1 Kapatılan kör nokta: özyinelemesiz arşiv taraması

Ölçüm (2026-11-02) — bu artık **kapalı**:

| Katman | Önce | Sonra |
| --- | --- | --- |
| `backups/*.tar.gz` → `n8n-data.tar` | iç arşiv **hiç açılmıyordu** | açılıyor (2 katman) |
| `./config` (56 B, `encryptionKey`) | **0 bulgu** üretiyordu | `json_secret_field` yakalıyor |
| Arşiv içindeki `Cookies`/`Login Data` | görünmüyordu | `browser_cookies` bulgusu |
| Derinlik sınırı aşımı | sessizce atlanıyordu | `nested_archive_unopened` bulgusu |

**Neden `json_secret_field` gerekti:** mevcut `assigned_secret` deseni Python
atamasına (`KEY = "..."`) bakıyor ve JSON biçimini kaçırıyordu. Gerçek dosya
56 bayttı; n8n'in tüm credential deposunu çözen anahtar buydu.

**Yanlış alarm kontrolü:** yeni desen iki test dosyasını kırmızıya döndürdü.
İkisi de gerçek sır değil, testin "sızmamalı" demek için kullandığı yer tutucu
(`SHOULD_NOT_APPEAR_IN_SCHEMA`, `should-not-be-written`). Bunları baseline'a
yazmak yanlış olurdu — baseline *gerçek* bulgu demek. Bu yüzden dar bir
`SENTINEL_SUBSTRINGS` listesi eklendi (desen zayıflatılmadı).

### 5.2 `.gitignore` dışındaki kopyalar — tarayıcı göremez

`*.tar.gz` ve `*.bundle` `.gitignore`'da. Bu doğru (yoksa 130 MB'lık bundle ve
5.7 MB'lık n8n veritabanı commit'lenebilirdi), ama **bu dosyalardaki sır ne
`--history` ne HEAD taraması tarafından görülür**. Bu yüzden ayrı bir ölçüm var:

> **Düzeltme (2026-11-02):** bu bölüm önce "`*.bundle` `.gitignore`'da" diyordu —
> **yanlıştı**. `git check-ignore` ile ölçüldü: `*.bundle` ve `*.sealed` hiçbir
> kurala uymuyordu, yani mühürleme çıktısı ve bundle commit'lenebilir durumdaydı.
> İkisi de eklendi (`.gitignore`). Bu, `CAPABILITIES`'in ölçmediği bir boşluktu:
> betik sır *değerini* arıyordu, sır *taşıyan dosyanın* depoya girebilir olmasını
> değil.


```powershell
python scripts/verify_leak_rotation.py     # "Disk üzerindeki yedek kopyaları" bölümü
```

Diskteki bundle içinde ölçülen (2026-11-02):

| Nesne | Ölçüm |
| --- | --- |
| `video-output/tiktok_session/` | **941 nesne** (tüm Chromium profili) |
| `Network/Cookies` | `sessionid`, `sessionid_ss`, `sid_tt`, `uid_tt` |
| Çerez son kullanma | **2027-03-16** — yani hâlâ geçerli |

Silme **bilinçli olarak otomatikleştirilmedi**: bundle, geçmişi geri almanın
tek yolu (`git clone` ile dönüş). Yanlış anda çalışan bir betik geri
getirilemez veri kaybı demek. Karar operatörün; betik yalnızca varlığını ölçer
ve `CAPABILITIES` tablosunda bunu gerekçesiyle listeler.

### 5.3 Mühürleme — silmeden sırrı kapatmak

Silme ile mühürleme arasındaki fark, "geri dönüş var mı" sorusudur. Mühürleme
AES-256-GCM + scrypt(n=2¹⁴) kullanır; dosya diskte kalır, okunamaz olur.

Ölçülen (2026-11-02):

| Kontrol | Sonuç |
| --- | --- |
| 441 556 B tarball → `.sealed` | 441 609 B (53 B başlık + 16 B GCM tag) |
| Geri açma | aynı SHA-256 (`9c6f268de18fc52e`) |
| Orijinalin `json_secret_field` bulgusu | 1 |
| `.sealed` hâlinin bulgusu | **0** — arşiv olarak bile açılmıyor |
| Yanlış parola | çıkış 1, hata, çıktı yazılmaz |
| Kurcalanmış şifreli metin | reddedilir (GCM tag tutmaz) |

**Neden geri açıp karşılaştırıyor:** "yazdım" demek "okunabilir" demek değil.
`seal_file()` mühürler → diskten geri okur → açar → SHA-256 karşılaştırır →
**ancak o zaman** kaynağı siler. Bu sıra testle kilitli
(`test_seal_file_verifies_before_deleting`).

**Neden parola hiçbir yere yazılmıyor:** `.sealed` dosyasının yanına konan bir
parola dosyası, mühürlemeyi süs haline getirir — aynı disk kaybedilince sır da
parola da gider, ya da tam tersi ikisi birden bulunur.

**Doğrulayıcı ayrımı biliyor:** `check_stray_copies()` mühürlü kopyayı ✅ sayar,
ama `.sealed` **ve** düz kopya birlikte duruyorsa uyarır — çünkü
`--delete-originals` unutulduğunda sır hâlâ okunabilir.

**Kalan risk:** mühürlü arşivin parolası kaybolursa dosya silinmiş sayılır.
Bu, silmeye göre bir kazanç değil; ama parolayı parola yöneticisinde tutmak
koşuluyla geri dönüş korunur.

### 5.4 Bilinmeyen kopyalar ve canlı oturum

Sabit yol listesi yetmiyordu: doğrulayıcı yalnız iki bilinen dosyayı sayıyordu,
yani kullanıcı yedeği `yedek-2.bundle` diye kopyalasa "temiz" derdi. Bu yüzden
ikinci bir katman var — `discover_stray_copies()` verilen köklerin altında **adı
ne olursa olsun** `.bundle` / `.tar.gz` / `.tgz` / `.tar.xz` arıyor.

Ölçüm (2026-11-02): `C:\Projects` altında venv içinde `dateutil-zoneinfo.tar.gz`
bulundu. Yani sonek taraması tek başına **yanlış pozitif** üretir. Bu yüzden
`venv`, `.venv`, `site-packages`, `node_modules`, `__pycache__`, `.git`,
`dist`, `build` atlanıyor ve derinlik 4 ile sınırlı.

> **Kendi ölçüm hatam:** "gitignore kapsıyor mu" sorusunu
> `if (git check-ignore -q ...)` ile sordum ve "HAYIR" aldım. Yanlıştı — `-q`
> çıktı üretmiyor, PowerShell `if` ise **çıktıya** bakıyor, çıkış koduna değil.
> Çıkış kodunu kullanınca doğru sonuç: `video-output/tiktok_session` ✅
> yok sayılıyor. Betiklerde okuma yaparken `$LASTEXITCODE` kullanın.

**Canlı oturum dizini** (`video-output/tiktok_session`, 1015 dosya / 148 MB)
ayrı raporlanıyor ve **silinmiyor**: prodüksiyon onu kullanıyor ve
`--tiktok` ölçümü oturumun canlı olduğunu doğruladı. Mühürlemek de yanlış olur —
çalışan oturumu bozar. Döndürme (mobil uygulamada *log out of all devices*)
tamamlandıktan **sonra** silinebilir.

| Kalem | Durum |
| --- | --- |
| Bilinen 2 yedek (bundle + tarball) | ❌ açık — mühürlenmeli |
| Adı farklı arşivler | ✅ taramayla bulunuyor (venv hariç) |
| `tiktok_session` (canlı) | ⚠️ görünür, silinmez, döndürme sonrası silinir |

**Kalan risk:** arşiv taraması özyinelemeli, ama derinlik 3 ile sınırlı.
Daha derin bir yedek `nested_archive_unopened` bulgusu üretir — yani sessiz
kalmaz, ama **elle açılması** gerekir.

### 5.5 Test dosyalarının kendi sağlığı

Bu iş sırasında test düzenlemelerinde **üç kez** aynı hata oluştu: yeni bir test,
var olan bir testin gövdesinin **ortasına** eklendi. Sonuçlar:

| Dosya | Ne oldu | Neden fark edilmedi |
| --- | --- | --- |
| `test_seal_leak_copies.py` | Gövdeye yetim bir `docstring` + `with` bloğu yapıştı; `test_not_a_sealed_file_rejected` kayboldu | Test geçiyordu — yetim blok bir docstring'e dönüşmüştü, sözdizimi geçerli |
| `test_verify_leak_rotation.py` | `test_tiktok_verdict_*` **iki kez** tanımlandı, ilki `con.execute` satırında kesildi | Python ikinci tanım ilkini ezip geçti; assert'siz ölü kod kaldı, suite yeşil kaldı |

Ortak özellik: **suite yeşil kalıyor**. "Testler geçiyor" bu sınıfı yakalamıyor,
çünkü hata testin *çalışmasını* değil *varlığını* bozuyor.

Bu yüzden `video-worker/tests/test_test_suite_hygiene.py` eklendi — dört yapısal
kapı (`ast` tabanlı, kod çalıştırmadan):

| Kapı | Yakaladığı |
| --- | --- |
| `test_no_duplicate_test_names` | Aynı isimli iki test = biri sessizce ölü |
| `test_no_test_function_is_empty` | Gövdesi yalnız docstring → hiçbir şey ölçmez, hep yeşil |
| `test_no_orphan_statements_after_test_function` | Tek gövdede **iki docstring** = yapıştırmanın kesin imzası |
| `test_every_test_module_imports` | Geçerli Python ama import edilemeyen dosya |

Kapıların gerçekten çalıştığı **kanıtlandı**: dört kasıtlı hata içeren geçici bir
dosyayla koşuldu, üç dedektör de dosya::test + satır numarasıyla kırmızıya döndü
(`3 failed, 1 passed`). Sonra geçici dosya silindi.






