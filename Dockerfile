FROM ghcr.io/astral-sh/uv:0.12.19@sha256:04d046b13e60d6bcec73cbc5e1cad25d680dea90c8573340950a0ac2d1aef424 AS uv
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS base

COPY --from=uv /uv /uvx /bin/
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY pyproject.toml uv.lock ./

FROM base AS runtime
RUN uv sync --frozen --no-dev --no-install-project \
    && groupadd --gid 10001 fieldops \
    && useradd --uid 10001 --gid fieldops --no-create-home fieldops
COPY fieldops/ fieldops/
COPY alembic.ini ./
COPY migrations/ migrations/
USER 10001:10001
EXPOSE 8000
CMD ["python", "-m", "fieldops"]

FROM base AS test-dependencies
RUN uv sync --frozen --no-install-project

FROM test-dependencies AS test
COPY fieldops/ fieldops/
COPY alembic.ini ./
COPY migrations/ migrations/
COPY tests/ tests/
COPY test_support/ test_support/
CMD ["python", "-m", "test_support.runner", "backend"]

FROM test-dependencies AS browser
RUN apt-get update && apt-get install -y --no-install-recommends libatomic1 \
    && python -m playwright install --with-deps chromium
COPY fieldops/ fieldops/
COPY alembic.ini ./
COPY migrations/ migrations/
COPY test_support/ test_support/
COPY browser_tests/ browser_tests/
CMD ["python", "-m", "test_support.runner", "browser"]
