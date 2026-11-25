FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/backend

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10002 vortexen \
    && useradd --system --uid 10002 --gid 10002 --home-dir /home/vortexen --create-home vortexen

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY extraction_engine /app/extraction_engine
COPY backend /app/backend

RUN mkdir -p /data/uploads /app/backend/staticfiles \
    && chown -R 10002:10002 /app /data/uploads

WORKDIR /app/backend
USER 10002:10002

RUN python manage.py collectstatic --noinput || true

EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "2", "--timeout", "300", "--graceful-timeout", "30", "--max-requests", "500", "--max-requests-jitter", "50"]
