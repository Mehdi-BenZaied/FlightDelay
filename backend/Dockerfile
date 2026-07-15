# syntax=docker/dockerfile:1

# =========================================================
# Stage 1: Build Python dependencies
# =========================================================
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

# Build tools needed by Python, PostgreSQL and ML packages
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create an isolated Python environment
RUN python -m venv /opt/venv

# Copy requirements separately to improve Docker cache usage
COPY backend/requirements.txt ./requirements.txt

# Install project dependencies
#
# gevent and gevent-websocket are installed explicitly so run.py can use:
#   from gevent import monkey
RUN python -m pip install --upgrade pip setuptools wheel \
    && python -m pip install --no-cache-dir -r requirements.txt \
    && python -m pip install --no-cache-dir \
        gevent \
        gevent-websocket

# Fail the build immediately if important imports are unavailable
RUN python -c "import gevent; print('gevent installed:', gevent.__version__)" \
    && python -c "import flask; import xgboost; import shap; print('Core dependencies installed')"


# =========================================================
# Stage 2: Runtime image
# =========================================================
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app" \
    PORT="5000" \
    FLASK_DEBUG="false" \
    MODEL_PATH="/app/ml/models/v1_model.json" \
    FLIGHT_DATA_PATH="/app/datasets/flight_data.csv"

WORKDIR /app

# Install only libraries needed while the application is running
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        curl \
        libgomp1 \
        libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system appgroup \
    && useradd \
        --system \
        --gid appgroup \
        --create-home \
        appuser

# Copy the Python virtual environment from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy backend source files directly into /app
COPY --chown=appuser:appgroup backend/ /app/

# Copy the ML package and trained models
COPY --chown=appuser:appgroup ml/ /app/ml/

# Copy the analytics dataset
COPY --chown=appuser:appgroup data/ /app/datasets/

# Validate required runtime files and create writable database directory
RUN test -f /app/run.py \
    && test -f /app/analytics.py \
    && test -f /app/ml/models/v1_model.json \
    && test -f /app/datasets/flight_data.csv \
    && mkdir -p /app/data \
    && chown -R appuser:appgroup /app/data

# Run the application without root privileges
USER appuser

EXPOSE 5000

HEALTHCHECK \
    --interval=15s \
    --timeout=5s \
    --start-period=60s \
    --retries=5 \
    CMD curl --fail --silent --show-error \
        http://localhost:5000/health || exit 1

CMD ["python", "run.py"]