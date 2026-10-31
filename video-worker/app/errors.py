class AllPlatformsFailedError(Exception):
    """Bir /publish çağrısında yapılandırılmış tüm platformlar hata döndürdüğünde fırlatılır."""

    def __init__(self, job_id: str, results: list[dict]):
        super().__init__(f"All platforms failed for job {job_id}")
        self.job_id = job_id
        self.results = results


class AlreadyPublishedError(Exception):
    """Aynı iş için ikinci /publish — yayın public ve geri alınamaz, bu yüzden reddedilir."""

    def __init__(self, job_id: str, state: str = ""):
        super().__init__(f"Job {job_id} is already {state or 'published/publishing'}")
        self.job_id = job_id
        self.state = state


class ArtifactChangedError(Exception):
    """Onaylanan dosya yayından önce değişti veya kayboldu — onay geçersiz."""

    def __init__(self, job_id: str, reason: str):
        super().__init__(f"Job {job_id}: approved artifact invalid ({reason})")
        self.job_id = job_id
        self.reason = reason


class QualityGateError(Exception):
    """Video yayınlanabilir teknik kalitede değil (sessiz, çok kısa, akış yok).

    Yayın claim'inden ÖNCE fırlatılır: reddedilen dosya claim'i tüketmemeli,
    yoksa iş 'publishing'de kalıp /generate'i kilitler. Operatörün retry
    butonu yeniden üretim yapmalı — aynı dosyayı tekrar göndermek aynı sonucu
    verir.
    """

    def __init__(self, job_id: str, reason: str):
        super().__init__(f"Job {job_id}: quality gate rejected ({reason})")
        self.job_id = job_id
        self.reason = reason


class PublishOutcomeUnknownError(Exception):
    """Yükleme zaman aşımına uğradı; platformda yayınlanmış olabilir.

    Bilinçli olarak AllPlatformsFailedError'dan ayrı: bu durumda retry sunmak
    aynı videoyu iki kez yayınlar, o yüzden çağıranlar retry önermemeli.
    """

    def __init__(self, job_id: str, results: list[dict]):
        super().__init__(f"Publish outcome unknown for job {job_id}")
        self.job_id = job_id
        self.results = results


class FalAuthBillingError(Exception):
    """Fal.ai (Flux/Kling) 401/403 veya bakiye/yetki hatası — stok fallback yasak, job hard-fail."""

    def __init__(
        self,
        message: str = "Fal auth or billing failure",
        *,
        status_code: int | None = None,
        detail: str = "",
    ):
        super().__init__(message)
        self.status_code = status_code
        self.detail = (detail or "")[:400]


# Geriye dönük alias — önceki hard-fail patch / testler KlingAuthBillingError kullanır.
KlingAuthBillingError = FalAuthBillingError
