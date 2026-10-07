FROM ghcr.io/astral-sh/uv:python3.14-trixie
WORKDIR /app

ENV UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project
COPY src/ ./src/
COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY --chmod=755 scripts/container-entrypoint.sh ./scripts/container-entrypoint.sh
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["/app/scripts/container-entrypoint.sh"]
CMD ["api"]
