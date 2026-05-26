FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Europe/Madrid

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        tzdata \
        ca-certificates \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libc6 \
        libcairo2 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libexpat1 \
        libfontconfig1 \
        libgbm1 \
        libglib2.0-0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxext6 \
        libxfixes3 \
        libxrandr2 \
        libxrender1 \
        libxshmfence1 \
        libxss1 \
        libxtst6 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --only-shell chromium

COPY config.py .
COPY main.py .
COPY bot/ ./bot/
COPY dashboard/ ./dashboard/
COPY data/ ./data/

EXPOSE 5000

CMD ["python", "main.py"]
