# TheArtist backend

FastAPI services shared by the editor and local MCP clients. Install and run from
the complete repository, because inference also uses `ai/` and model checkpoints.
See the [project setup](../README.md#getting-started), [API contracts](../API_SPEC.md)
and [MCP guide](../docs/mcp.md).

```sh
uv sync --frozen --directory /absolute/path/TheArtist-DAW/backend
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python /absolute/path/TheArtist-DAW/backend/scripts/setup_omt.py
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python /absolute/path/TheArtist-DAW/model/_download.py --smoke
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend uvicorn app.main:app --reload
```

`--smoke` downloads F1 only. Omit it for all 18 released checkpoints/adapters.
Missing checkpoints produce explicitly labeled rule results; an HTTP 200 alone
does not prove that the Music Transformer ran. Check `source` and `modelUsed`.

Set server variables in your terminal or hosting environment; the app does not
automatically load a `.env` file. [The template](../deploy/env.example) documents
Meta, source, warmup, spend-limit and CORS settings. Never put provider keys into
frontend configuration. Standard Meta calls read `MODEL_API_KEY`.

OMT retrieval defaults on after setup, Berklee off. Retrieval is local and does
not call an embedding model or explanation LLM. `/api/capabilities` reports
source readiness; see [theory retrieval](../docs/theory-retrieval.md). Historical
Chroma/SentenceTransformers research dependencies remain in the environment but
are not loaded by product retrieval.

`THEARTIST_PUBLIC_HOST=1` disables local DAW operations, manual model warmup and
MCP, and rejects whole-file Meta import. It retains local import and bounded Meta
assist with per-session/daily spend limits. This flag is not authentication or a
complete internet deployment configuration. A hosted frontend needs a same-origin
`/api` reverse proxy or an appropriate API deployment; Vite's proxy is development-only.

```sh
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python -m unittest discover -s tests -t .
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python -c "import app.main; print('import app.main: ok')"
```

External model quality, live audio and DAW behavior have separate
[evaluation](../docs/evaluation.md) and [manual checks](../docs/manual-checks.md).
