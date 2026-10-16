FROM postgres:16-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY deploy/backup/requirements.lock ./requirements.lock
RUN uv venv --python /usr/bin/python3 /opt/backup \
    && uv pip sync --python /opt/backup/bin/python --require-hashes requirements.lock
COPY people-gator-api/src/people_gator_api/backup ./people_gator_api/backup
ENV PATH="/opt/backup/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
USER 10001:10001
ENTRYPOINT ["python", "-m", "people_gator_api.backup"]
