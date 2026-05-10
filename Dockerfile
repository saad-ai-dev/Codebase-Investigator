FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /bin/bash appuser

COPY pyproject.toml README.md /app/
COPY src /app/src
COPY docker/entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN pip install -e . \
    && chmod +x /usr/local/bin/docker-entrypoint.sh \
    && mkdir -p /app/.investigator \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

VOLUME ["/app/.investigator"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python3 -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/api/health', timeout=3).read()"

ENTRYPOINT ["docker-entrypoint.sh"]
