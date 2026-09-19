class AllPlatformsFailedError(Exception):
    """Bir /publish çağrısında yapılandırılmış tüm platformlar hata döndürdüğünde fırlatılır."""

    def __init__(self, job_id: str, results: list[dict]):
        super().__init__(f"All platforms failed for job {job_id}")
        self.job_id = job_id
        self.results = results
