# OtoGaleri Avcı Botu — ortak imaj (API, Streamlit ve worker aynı imajdan çalışır)
# ===============================================================================
# Otoplus / Otokoç / Arabam.com scraper'ları yalnızca HTTP (curl_cffi) kullanır.
# VavaCars headless Chrome ister; chromium imaja dahildir ama UC mode bazı konteyner
# ortamlarında güvenilir olmayabilir (README → "Bulut dağıtımı").

FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CHROME_BIN=/usr/bin/chromium \
    OTOGALERI_LOG_FILE=/tmp/otogaleri_log.txt \
    OTOGALERI_DESKTOP_NOTIFICATIONS=false

RUN apt-get update && apt-get install -y --no-install-recommends \
        chromium libnss3 libxss1 libasound2 libgbm1 fonts-liberation curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# root olmayan kullanıcı
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/health || exit 1

# Varsayılan: REST API. Streamlit ve worker için compose dosyası komutu ezer.
CMD ["python", "-m", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
