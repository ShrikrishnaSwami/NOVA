FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN python -m pip install --no-cache-dir "nats-py>=2.9,<3.0" \
    && useradd --create-home --uid 10001 nova

COPY --chown=nova:nova src/nova /app/src/nova

USER nova

CMD ["python", "-m", "nova.distributed.worker"]
