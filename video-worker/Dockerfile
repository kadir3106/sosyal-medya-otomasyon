# BASE: varsayılan python:3.12-slim; apt aynası yavaşken mevcut imajın
# üzerine hızlı build için --build-arg BASE=<mevcut imaj> INSTALL_FFMPEG=0
# ile geçilebilir (ffmpeg zaten mevcut imajda kuruluysa).
ARG BASE=python:3.12-slim
ARG INSTALL_FFMPEG=1
FROM ${BASE}

# ARG'lar FROM'dan önce sadece FROM'un kendisi için (${BASE}) görünür — build
# stage'inin İÇİNDE kullanılacaksa FROM'dan SONRA yeniden bildirilmesi şart,
# yoksa aşağıdaki $INSTALL_FFMPEG boş string olur ve if hep false döner
# (ffmpeg hiç kurulmaz, ama build hatasız biter — sessizce bozuk bir imaj
# üretir). Bu proje bu hatayı gerçekten yaşadı: video-worker aylarca
# ffmpeg'siz build edildi, testler subprocess.run'ı mockladığı için bu hiç
# fark edilmedi.
ARG INSTALL_FFMPEG

# Font kurulumu yok — görsel kartlar Pillow'un gömülü DejaVuSans fontunu
# kullanır (Pillow >= 10, Türkçe karakter desteği dahil).
RUN if [ "$INSTALL_FFMPEG" = "1" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        && rm -rf /var/lib/apt/lists/*; \
    fi

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY data ./data
COPY tests ./tests
COPY pytest.ini .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
