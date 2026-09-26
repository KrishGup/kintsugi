# Kintsugi — API + web UI + OpenSCAD toolchain in one container.
#   docker build -t kintsugi .
#   docker run -p 8000:8000 -e OPENAI_API_KEY=sk-... -v kintsugi-sessions:/data/sessions kintsugi

FROM node:22-bookworm-slim AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.11-slim-bookworm
ENV DEBIAN_FRONTEND=noninteractive PIP_NO_CACHE_DIR=1 PYTHONUNBUFFERED=1 \
    KIN_SESSIONS_DIR=/data/sessions KIN_HOST=0.0.0.0 KIN_PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends openscad xvfb git curl ca-certificates libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY kintsugi ./kintsugi
COPY templates ./templates
COPY vendor ./vendor
COPY eval/specs ./eval/specs
RUN pip install -e .
COPY --from=web /web/dist ./web/dist
RUN mkdir -p /data/sessions
EXPOSE 8000
CMD ["kin", "serve", "--host", "0.0.0.0", "--port", "8000"]
