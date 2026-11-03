# TheArtist backend

FastAPI arrangement services shared by the editor and local MCP clients: score
reading, harmonic generation and revision, form planning, accompaniment and
editable MIDI delivery. [The workflow guide](../docs/arrangement-workflow.md)
shows how these services connect in the editor. Install and run from
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
Generation can produce explicitly labeled rule results when checkpoints are
missing; Reharmonize requires the selected model and reports an error instead.
An HTTP 200 alone does not prove that the Music Transformer ran. Check `source`
and `modelUsed` on generation responses.

`POST /api/reharmonize` returns three contextual patches, each changing at most
1–4 selected existing chords. Meta chooses among bounded searches scored by the
Music Transformer. The endpoint never applies edits. Browser Origin/Alter 1–3
preview, combination and Apply own that transition. Accompaniment and MIDI rendering use
the resulting score plus explicit playback settings; they are rule-based parts.

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
MCP. Whole-file Meta import requires `THEARTIST_PUBLIC_META_READER=1` as well as
usable Meta configuration and enough session/daily budget for its default $1.50 reservation.
Local import and bounded Meta assist remain available. This flag is not authentication or a
complete internet deployment configuration. The [single-origin launcher](../deploy/README.md)
serves the built frontend after API routes; separate hosting needs a suitable
`/api` reverse proxy. Vite's proxy is development-only.

The editor defaults to local reading and keeps Analyze as the explicit trigger.
Its **Use Meta model** checkbox sends `engine: "verified"`: one original-file
Meta call alongside local analysis, followed by comparison or explicitly labeled local
recovery when Meta fails. `score_verification.py` preserves printed local
symbols/N.C., flags disagreement, and reports unavailable local comparison.
The direct `meta` and bounded `auto` API modes remain supported.

```sh
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python -m unittest discover -s tests -t .
uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python -c "import app.main; print('import app.main: ok')"
```

External model quality, live audio and DAW behavior have separate
[evaluation](../docs/evaluation.md) and [manual checks](../docs/manual-checks.md).
