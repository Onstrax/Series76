# Single image used by BOTH the api and worker processes (Req 1.4).
# No secret or KEK is ever baked in — all config comes from the environment at
# runtime (Req 12.6). The migration step (see docker-compose) runs before serve.
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# System deps kept minimal; psycopg[binary] ships its own libpq.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install the project (pinned deps come from pyproject). Copy metadata first
# for layer caching, then the source.
COPY pyproject.toml README.md ./
COPY src ./src
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini

RUN pip install --upgrade pip \
    && pip install .

# Default command is overridden per-service in docker-compose.
# api:    uvicorn series76_api.app:create_app --factory --host 0.0.0.0 --port 8000
# worker: python -m series76_api.worker   (worker entrypoint arrives in Half B)
CMD ["python", "-c", "import series76_api; print(series76_api.__version__)"]
