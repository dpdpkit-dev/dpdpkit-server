# dpdpkit-server image: dpdpkit-fastapi plus uvicorn, running as a non-root user on a read-only file system.
#   docker run --read-only --tmpfs /tmp -p 8000:8000 ghcr.io/dpdpkit-dev/server
FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# --pre: the dpdpkit packages are alphas until 0.5 ships.
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --pre ".[postgres]"

FROM python:3.12-slim
ENV PATH=/opt/venv/bin:$PATH \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
COPY --from=build /opt/venv /opt/venv
# Fixed numeric UID/GID so Kubernetes runAsNonRoot can verify it. No home directory, no writable paths.
RUN groupadd --gid 10001 dpdpkit \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin dpdpkit
USER 10001:10001
WORKDIR /tmp
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD ["python", "-c", "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/healthz', timeout=2)"]
ENTRYPOINT ["python", "-m", "dpdpkit.server"]
