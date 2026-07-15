# syntax=docker/dockerfile:1

# ------------------------------------------------------------
# Python dependencies builder
# ------------------------------------------------------------
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN apt-get update \
    && apt-get install \
        --yes \
        --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv

COPY backend/requirements.txt /build/requirements.txt

RUN python -m pip install \
        --upgrade \
        pip \
        setuptools \
        wheel \
    && python -m pip install \
        --requirement /build/requirements.txt


# ------------------------------------------------------------
# Runtime image
# ------------------------------------------------------------
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH" \
    PORT=5000 \
    MODEL_PATH="/app/ml/models/v1_model.json" \
    FLIGHT_DATA_PATH="/app/datasets/flight_data.csv"

WORKDIR /app

RUN apt-get update \
    && apt-get install \
        --yes \
        --no-install-recommends \
        curl \
        libgomp1 \
        libpq5 \
    && rm -rf /var/lib/apt/lists/*

RUN groupadd \
        --system \
        appgroup \
    && useradd \
        --system \
        --gid appgroup \
        --home-dir /app \
        --shell /usr/sbin/nologin \
        appuser

COPY --from=builder /opt/venv /opt/venv

COPY --chown=appuser:appgroup backend/ /app/
COPY --chown=appuser:appgroup ml/ /app/ml/
COPY --chown=appuser:appgroup data/ /app/datasets/

RUN mkdir -p /app/data \
    && chown -R appuser:appgroup /app/data \
    && test -f /app/run.py \
    && test -f /app/analytics.py \
    && test -f /app/app/core/config.py \
    && test -f /app/ml/models/v1_model.json \
    && test -f /app/datasets/flight_data.csv

USER appuser

EXPOSE 5000
EXPOSE 8050

HEALTHCHECK \
    --interval=15s \
    --timeout=10s \
    --start-period=60s \
    --retries=12 \
    CMD curl \
        --fail \
        --silent \
        --show-error \
        http://127.0.0.1:5000/health \
        || exit 1

CMD ["python", "run.py"]