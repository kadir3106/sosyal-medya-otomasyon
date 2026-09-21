class AllPlatformsFailedError(Exception):
    """Bir /publish çağrısında yapılandırılmış tüm platformlar hata döndürdüğünde fırlatılır."""

    def __init__(self, job_id: str, results: list[dict]):
        super().__init__(f"All platforms failed for job {job_id}")
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
