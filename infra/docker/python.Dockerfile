# syntax=docker/dockerfile:1.7
# Shared image recipe for the API and the worker (CPU only; no PyTorch).
#   docker build -f infra/docker/python.Dockerfile --build-arg PACKAGE=pawguard-api    -t pawguard-api .
#   docker build -f infra/docker/python.Dockerfile --build-arg PACKAGE=pawguard-worker -t pawguard-worker .
FROM ghcr.io/astral-sh/uv:0.7.12 AS uv

FROM python:3.12.11-slim-bookworm AS build
ARG PACKAGE
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
# Build the virtualenv at its final path: uv virtualenvs are not relocatable (script shebangs are absolute).
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-install-workspace --package ${PACKAGE}
COPY services/api services/api
COPY services/worker services/worker
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package ${PACKAGE}

FROM python:3.12.11-slim-bookworm
# libgomp1: OpenMP runtime used by onnxruntime/opencv in the worker.
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 && rm -rf /var/lib/apt/lists/* \
    && useradd --system --uid 10001 --home-dir /app pawguard
WORKDIR /app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/services/api/alembic.ini /app/alembic.ini
COPY --from=build /app/services/api/migrations /app/migrations
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PAWGUARD_ENV_FILE=/dev/null
USER pawguard
EXPOSE 8000
CMD ["uvicorn", "pawguard_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", "--proxy-headers"]
