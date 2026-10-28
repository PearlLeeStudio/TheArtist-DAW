# Shared music API and MCP

The editor, TheVoyager, and future plugin clients use one TheArtist backend. Music Transformer inference, Meta score reading, arrangement rules, MIDI rendering, and the Meta spend ledger stay on that backend. A client sends music state and receives music state or a MIDI file; it does not copy models or music-generation rules.

The Streamable HTTP endpoint is `http://127.0.0.1:8000/mcp/`. FastAPI starts and stops the official MCP SDK session manager in its lifespan. The transport is stateless: each tool request carries its complete input. The current endpoint is intended for a local backend, with the SDK's localhost Host/Origin checks enabled. Bind it to loopback. Hosted authentication and remote deployment are separate work.

`GET /api/capabilities` and the MCP `capabilities` tool expose the same contract discovery result. Successful MCP results have:

```json
{"schemaVersion":"1.0","data":{}}
```

`structuredContent.data` contains the result. The text content is a short description, so large MIDI payloads are not duplicated. Clients must reject unsupported schema versions and MCP `isError: true`; a connection or tool failure does not trigger a hidden REST fallback.

| Tool | Shared contract / implementation | Notes |
|---|---|---|
| `capabilities` | Contract version, limits and implemented tools | No generation |
| `list_models` | `GET /api/models/list` | Availability only; does not load models |
| `list_genres` | `GET /api/genres/list` | Supported genre vocabulary |
| `get_genre_preset` | Existing genre tables | Key, BPM, meter, rhythm and instrument defaults |
| `generate_section` | `SectionGenerateRequest` → existing `/api/generate/section` response | Keep `source` and `modelUsed` visible |
| `build_song` | `SongGenerateRequest` → existing `/api/generate/song` response | Keep `model_used` and each track's `source` visible |
| `render_midi` | The same `ExportSpec` as `/api/export/midi` | Returns `mimeType`, `filename`, `byteLength`, `dataBase64` |
| `import_score` | The same request and review draft as `/api/import/score` | Explicit attachment confirmation; one bounded Meta call |
| `export_daw` | The same request as `/api/daw/open` | Explicit local side effect; opt-in required |

The request schemas are the application Pydantic models, advertised by `tools/list`. They are not separately maintained music formats. Section indices are zero based; export measures contain exactly two chord slots, with the actual resolved MIDI voicing for each chord. Score-import drafts preserve their raw chord counts until a user confirms the conversion to those two slots.

`build_song` produces one arrangement (`n_candidates=1`). Optional `seed` is a strict integer in `0..2^32-1`, passed to the shared generator and echoed in the response; seeded generation uses request-local randomness. Candidate fan-out is not implemented. Song planning and theory explanation are not advertised as tools. Existing rule-generation paths remain explicitly labeled `rules` / `rule`; they are never relabeled as model output. Meta failures remain errors.

Limits are 1 MiB of music JSON, 4 MiB of MIDI bytes, a 6 MiB result envelope, and a 12 MiB MCP request body. Score attachments are limited to one 8 MiB PDF/PNG/JPEG/WebP. A generated song has at most 64 bars; score imports allow 128 measures and MIDI export 512. MIDI uses 480 PPQ and the supplied meter, metadata, voicings, rhythm, swing, instruments, and mixer CC7 values.

The import tool requires `attachmentConfirmed: true`. This asserts that the user explicitly attached this score for reading by Meta. It accepts inline bytes, never filesystem paths or remote URLs. Do not gather journals, photographs, or other private files to supply it. The existing Meta timeout, one-turn policy, cost reservation, request ID and token logging apply unchanged.

`export_daw` writes a unique MIDI under `backend/.exports/` and opens Logic Pro or reveals the file for Ableton. It is annotated as a side effect and requires all three gates: server environment `THEARTIST_MCP_ALLOW_DAW=1`, per-call `confirmed: true` after the user's explicit request, and a direct loopback connection. Remote addresses and forwarded/proxied requests are rejected. Downloading MIDI has no such side effect and needs no opt-in.

## Thin clients

`backend/theartist_client/` provides an async Python adapter using the official MCP SDK. It only initializes the connection, calls tools, validates the versioned envelope, and decodes bounded MIDI. In an environment where that package and `mcp>=1.30,<2` are available:

```python
from theartist_client import ArtistClient

async def make_music():
    async with ArtistClient("http://127.0.0.1:8000/mcp/") as artist:
        capabilities = await artist.capabilities()
        song = await artist.build_song({"genre": "pop", "length_bars": 8})
        return song  # the existing SongGenerateResponse data, including source/model fields
```

TheVoyager validates this `build_song` data with its existing `SongResponse` model, then uses its own playback/render flow. Its thin adapter defaults to MCP (`THEARTIST_TRANSPORT=mcp`); `THEARTIST_TRANSPORT=rest` explicitly keeps the existing REST path. The constructor's `transport` argument overrides that environment choice. MCP sends only symbolic controls and the seed, without visit IDs or personal content. A future plugin can send its edited `ExportSpec` to `render_midi`, receive MIDI bytes, and import them through its host's own API. These are two clients of the same server, not two copies of the music engine. A native DAW plugin and host-specific project insertion are not implemented by this adapter.

An existing REST integration may explicitly select REST and continue using the same endpoints. Select the transport deliberately; never turn an MCP failure into an apparent success through an automatic REST retry.

Protocol tests use the real SDK client and server through an in-process ASGI transport. They exercise initialize, tool discovery, schema envelopes, MIDI round trips, errors and DAW gates without model/provider calls or launching applications. Actual Logic/Ableton import and plugin-host behavior still need user QA.

SDK reference: [official Python SDK, v1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x).
