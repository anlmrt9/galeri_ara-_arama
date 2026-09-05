# OtoGaleri Avcı Botu - ortak imaj (API + Streamlit)
# ==================================================
# Not: Otoplus/Otokoç scraper'ları (curl_cffi) bu imajda sorunsuz çalışır.
# VavaCars/Arabam scraper'ları seleniumbase + Chrome gerektirir; aşağıda
# chromium kurulur ama headless "UC mode" konteynerde her ortamda güvenilir
# çalışmayabilir (README'deki "Bulut Dağıtımı" notuna bakın).

FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# curl_cffi (libcurl) + chromium bağımlılıkları
RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium \
        libnss3 libxss1 libasound2 libgbm1 fonts-liberation \
        curl \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Konteynerde yazılabilir log yolu
ENV OTOGALERI_LOG_FILE=/tmp/otogaleri_log.txt

EXPOSE 8000 8501

# Varsayılan: REST API. Streamlit için compose'daki "web" servisi komutu ezer.
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
