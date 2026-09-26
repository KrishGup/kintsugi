# Kintsugi — API + web UI + OpenSCAD toolchain in one container.
#   docker build -t kintsugi .
#   docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... -v kintsugi-data:/data kintsugi
#
# Everything the app writes lives under /data (KIN_DATA_DIR): sessions in /data/sessions, the settings file at /data/.env.
# Mount a volume (docker) or an Azure Files share (Container Apps / App Service) there and the container is stateless.
# See docs/DEPLOY-AZURE.md for the Azure stack and every environment variable.

# ---- web build --------------------------------------------------------------------------------------------------
FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
RUN npm run build

# ---- runtime ----------------------------------------------------------------------------------------------------
FROM python:3.11-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 \
    KIN_DATA_DIR=/data KIN_SESSIONS_DIR=/data/sessions KIN_ENV_FILE=/data/.env \
    KIN_HOST=0.0.0.0 KIN_PORT=8000 KIN_PROXY_HEADERS=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        openscad xvfb git curl ca-certificates tini libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    # sessions on a mounted share are owned by whoever mounted it; git must not refuse them
    && git config --system --add safe.directory '*' \
    && git config --system user.email kintsugi@local && git config --system user.name kintsugi
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY kintsugi ./kintsugi
COPY templates ./templates
COPY vendor ./vendor
COPY eval/specs ./eval/specs
RUN pip install -e .
COPY --from=web /web/dist ./web/dist
RUN mkdir -p /data/sessions && chmod -R a+rwX /data
EXPOSE 8000
# liveness for docker / compose; Azure uses its own probes on the same path (see the bicep)
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1
# tini reaps the OpenSCAD / xvfb children a cancelled compile leaves behind
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["kin", "serve", "--host", "0.0.0.0", "--port", "8000"]
