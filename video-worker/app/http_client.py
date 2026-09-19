import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Geçici ağ hataları (429/5xx, bağlantı kopması) için üstel backoff'lu otomatik
# yeniden deneme. Ücretsiz OpenRouter modellerinde 429 rutin; bu olmadan tek bir
# geçici hata o günün tüm üretimini/yayınını iptal ediyordu.
#
# TikTok'un refresh-token akışı (app/publishers/tiktok.py) BUNU KULLANMIYOR —
# TikTok refresh token'ı her kullanımda rotasyona uğratıyor. Sunucu isteği
# başarıyla işleyip yanıt ağda kaybolursa, bir retry artık geçersiz olan eski
# refresh_token'ı tekrar gönderir ve hesabı kalıcı olarak kilitler; TikTok
# çağrıları bu yüzden ham `requests` ile yapılmaya devam ediyor.
_retry = Retry(
    total=3,
    backoff_factor=1.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=("GET", "POST", "PUT", "DELETE"),
    respect_retry_after_header=True,
)

session = requests.Session()
session.mount("https://", HTTPAdapter(max_retries=_retry))
session.mount("http://", HTTPAdapter(max_retries=_retry))
