# ASETS API — production image (Cloud Run)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    LOCAL_STORAGE_DIR=/data/receipts

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-prod.txt .
RUN pip install --no-cache-dir -r requirements-prod.txt

COPY server.py crypto.py ./
COPY db ./db
COPY hmrc ./hmrc
COPY legal ./legal

# Receipt images when STORAGE_BACKEND=local. On Cloud Run this is a
# mounted Cloud Storage bucket (see scripts/deploy_cloudrun.sh) because
# the container filesystem is ephemeral.
RUN mkdir -p /data/receipts && useradd -m -u 10001 asets && chown -R asets /data /app
USER asets

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/api/health" || exit 1

CMD ["sh", "-c", "exec uvicorn server:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
