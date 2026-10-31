FROM node:26.13.0-bookworm-slim AS frontend
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
COPY deploy/runtime/pyproject.toml deploy/runtime/uv.lock /app/deploy/runtime/
RUN uv sync --frozen --no-dev --no-cache --directory /app/deploy/runtime
ENV PATH="/app/deploy/runtime/.venv/bin:$PATH" \
    THEARTIST_PUBLIC_HOST=1 THEARTIST_SERVE_FRONTEND=1 THEARTIST_META_ENABLED=0 \
    THEARTIST_DISABLE_RAG=0 THEARTIST_RAG_OMT_ENABLED=1 THEARTIST_RAG_BERKLEE_ENABLED=0 \
    THEARTIST_WARMUP=1 THEARTIST_WARMUP_KEYS="" THEARTIST_META_LEDGER=/data/meta_ledger.json \
    THEARTIST_JUDGE_LEDGER=/data/judge_ledger.json PORT=7860 \
    OMP_NUM_THREADS=2 MKL_NUM_THREADS=2
# Cache the large public assets independently of application and documentation edits.
COPY model/_download.py /app/model/_download.py
RUN python /app/model/_download.py && rm -rf /root/.cache/huggingface
COPY ai/rag/omt.py ai/rag/omt_manifest.json /app/ai/rag/
COPY backend/scripts/setup_omt.py /app/backend/scripts/setup_omt.py
RUN python /app/backend/scripts/setup_omt.py
RUN mkdir -p /data /app/backend/.exports \
    && useradd --uid 1000 --create-home artist \
    && chown artist:artist /data /app/backend/.exports
COPY . /app
COPY --from=frontend /app/frontend/dist /app/frontend/dist
USER artist
EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:7860/api/health', timeout=4)"
CMD ["python", "/app/deploy/serve.py"]
