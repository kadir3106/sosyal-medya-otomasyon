# AI Director Plan (uygulama — kilitli kararlar)

> **Durum:** uygulandı (flag arkasında). `DIRECTOR_ENABLED` default **false**.  
> **İsim:** model omurgası her yerde **AI router**.

---

## Kilitlenen kararlar (Patron)

1. İsim: **AI router** — tek yazım.
2. `DIRECTOR_ENABLED` **başlangıçta kapalı** — mevcut üretim bozulmaz.
3. Yeni mimari = Director’lı hedef yol. Eski `VISUAL_ENGINE` dalı **silinmedi**.
4. AI Director **model seçmez**. Plan LLM’si `LLM_API_URL` → AI router.
5. Telegram onay video-worker’da. MİKO yalnız status + tetik; onayı atlamaz.

---

## Kod haritası

| Dosya | Rol |
|-------|-----|
| `config.py` | `DIRECTOR_ENABLED` (false), `DIRECTOR_AI_IMAGE_MAX`, `DIRECTOR_RELEVANCE_MIN` |
| `director_types.py` | `ScenePlan`, kinds |
| `director_planner.py` | Tek batch plan (script_gen LLM client → AI router) |
| `director.py` | plan → stock_video / stock_photo / ai_image fetch |
| `pipeline.py` | `director_on` ise Director; değilse legacy dal |

Açmak: `.env` → `DIRECTOR_ENABLED=true` (sonra `docker compose up -d --build video-worker`).
