FROM node:25.9.0-bookworm-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json /app/frontend/
RUN npm ci
COPY frontend/ /app/frontend/
RUN npm run build

FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.11.16 /uv /usr/local/bin/uv
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/README.md /app/backend/
RUN uv sync --frozen --no-dev --directory /app/backend
COPY . /app
COPY --from=frontend /app/frontend/dist /app/frontend/dist
ENV PATH="/app/backend/.venv/bin:$PATH" \
    THEARTIST_PUBLIC_HOST=1 THEARTIST_SERVE_FRONTEND=1 THEARTIST_META_ENABLED=0 \
    THEARTIST_DISABLE_RAG=0 THEARTIST_RAG_OMT_ENABLED=1 THEARTIST_RAG_BERKLEE_ENABLED=0 \
    THEARTIST_WARMUP_KEYS=ft_f1 THEARTIST_META_LEDGER=/data/meta_ledger.json \
    THEARTIST_JUDGE_LEDGER=/data/judge_ledger.json PORT=7860
RUN python /app/backend/scripts/setup_omt.py \
    && python /app/model/_download.py --smoke \
    && mkdir -p /data \
    && useradd --uid 1000 --create-home artist \
    && chown -R artist:artist /data /app
USER artist
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=4)"
CMD ["python", "/app/deploy/serve.py"]
