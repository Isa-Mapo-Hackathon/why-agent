# ---------- Stage 1: Next.js frontend build ----------
FROM node:20-alpine AS frontend-builder
WORKDIR /app
COPY client/frontend/package.json client/frontend/package-lock.json* ./
RUN npm install
COPY client/frontend/ .
RUN npm run build

# ---------- Stage 2: Python deps ----------
FROM python:3.12-slim AS python-deps
RUN pip install --no-cache-dir uv
WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --extra server

# ---------- Stage 3: Runtime ----------
FROM python:3.12-slim AS runtime

# Install nginx, supervisor, Node.js runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
        nginx supervisor curl ca-certificates gnupg \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python venv
COPY --from=python-deps /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONPATH=/app

# Application code
COPY agent/               /app/agent/
COPY client/backend/      /app/client/backend/
COPY client/__init__.py   /app/client/__init__.py
COPY data/semantic_layer.yml /app/data/semantic_layer.yml
COPY replays/             /app/replays/
COPY streamlit_app.py     /app/streamlit_app.py

# Next.js standalone runtime + static assets
COPY --from=frontend-builder /app/.next/standalone/   /app/client/frontend/
COPY --from=frontend-builder /app/.next/static        /app/client/frontend/.next/static
COPY --from=frontend-builder /app/public              /app/client/frontend/public

# Config
COPY docker/nginx.conf       /etc/nginx/nginx.conf
COPY docker/supervisord.conf /etc/supervisord.conf
COPY docker/entrypoint.sh    /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Create parquet dir and non-root user
RUN mkdir -p /app/data/parquet \
    && useradd -m -u 1000 appuser \
    && chown -R appuser:appuser /app /var/log/nginx /var/lib/nginx \
    && mkdir -p /run && touch /run/nginx.pid && chown appuser /run/nginx.pid

USER appuser

# Defaults — override with HF Spaces secrets
ENV MODEL_BACKEND=replay \
    PARQUET_DIR=/app/data/parquet \
    SEMANTIC_LAYER_PATH=/app/data/semantic_layer.yml

EXPOSE 7860
ENTRYPOINT ["/entrypoint.sh"]
