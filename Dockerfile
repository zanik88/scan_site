FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Системные зависимости:
#   - gcc / libpq-dev: для psycopg2
#   - fonts-dejavu-core: для кириллицы в PDF (если будешь делать PDF)
#   - docker.io: клиент Docker для сканера образов
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        fonts-dejavu-core \
        docker.io \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/generated_reports

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health', timeout=3)" || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
