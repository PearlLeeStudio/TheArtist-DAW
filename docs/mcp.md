# Shared music API and MCP

The editor, TheVoyager, and future plugin clients use one TheArtist backend. Music Transformer inference, Meta score reading, arrangement rules, MIDI rendering, and the Meta spend ledger stay on that backend. A client sends music state and receives music state or a MIDI file; it does not copy models or music-generation rules.

The Streamable HTTP endpoint is `http://127.0.0.1:8000/mcp/`. FastAPI starts and stops the official MCP SDK session manager in its lifespan. The transport is stateless: each tool request carries its complete input. The endpoint is intended for a local backend, with the SDK's localhost Host/Origin checks enabled. Bind it to loopback. `THEARTIST_PUBLIC_HOST=1` does not mount MCP; authenticated remote MCP deployment is not implemented.

`GET /api/capabilities` and the MCP `capabilities` tool expose the same contract discovery result. Successful MCP results have:

```json
{"schemaVersion":"1.0","data":{}}
```

`structuredContent.data` contains the result. The text content is a short description, so large MIDI payloads are not duplicated. Clients must reject unsupported schema versions and MCP `isError: true`; a connection or tool failure does not trigger a hidden REST fallback.

The server exposes these 11 tools:

| Tool | Shared contract / implementation | Notes |
|---|---|---|
| `capabilities` | Contract version, limits and implemented tools | No generation |
| `list_models` | `GET /api/models/list` | Availability only; does not load models |
| `list_genres` | `GET /api/genres/list` | Supported genre vocabulary |
| `get_genre_preset` | Existing genre tables | Key, BPM, meter, rhythm and instrument defaults |
| `generate_section` | `SectionGenerateRequest` → existing `/api/generate/section` response | Keep `source` and `modelUsed` visible |
| `build_song` | `SongGenerateRequest` → existing `/api/generate/song` response | Keep `model_used` and each track's `source` visible |
| `render_midi` | The same `ExportSpec` as `/api/export/midi` | Returns `mimeType`, `filename`, `byteLength`, `dataBase64` |
| `import_score` | The same request and review draft as `/api/import/score` | Local by default; attachment confirmation, bounded whole-context Meta assist, or explicit full-file Meta reading |
| `export_daw` | The same request as `/api/daw/open` | Explicit local side effect; opt-in required |
| `plan_song` | `PlanRequest` → the plan and its trace, as `/api/plan/song` without the generation step | Muse Spark plans, `validate_plan` checks, at most two revisions; a Meta failure is a tool error with the request ids and spend, never a plan-shaped fallback |
| `validate_plan` | A plan and its `PlanRequest` → `{ok, errors}` | Code only, no model call |

The request schemas are the application Pydantic models, advertised by `tools/list`. They are not separately maintained music formats. Section indices are zero based; export measures contain exactly two chord slots, with the actual resolved MIDI voicing for each chord. Score-import drafts preserve their raw chord counts until a user confirms the conversion to those two slots.

`build_song` produces one arrangement (`n_candidates=1`) and echoes its optional
`seed`. `generate_section` and `plan_song` also accept an optional strict integer
seed in `0..4294967295`; booleans, strings and fractional numbers are rejected.
Section generation uses request-local neural or rule randomness. The REST complete-form
run derives separate section/regeneration seeds from `PlanRequest.seed`; it does
not seed Muse Spark planning or judgment. MCP `plan_song` produces no chords, so
a client following it with `generate_section` must supply that call's seed itself.
The same checkpoint, device, runtime and inputs are needed for reproducibility;
cross-device identity is not guaranteed. Null remains stochastic.

`capabilities.data.rag` reports source readiness independently of Meta availability.
`generate_section` may return `explanations` containing labeled source excerpts
with `kind: "source_excerpt"` and their `citation`; clients should retain author,
editor, source, license and modification notices when displaying them. This is
local OMT retrieval, enabled after setup, with Berklee off by default. See
[theory retrieval](theory-retrieval.md) for source controls and limitations.

Candidate fan-out is not implemented. Theory explanation is not an MCP tool;
Second-ear review is REST only. Existing rule-generation paths remain explicitly
labeled `rules` / `rule`. Meta failures remain errors.

Limits are 1 MiB of music JSON, 4 MiB of MIDI bytes, a 6 MiB result envelope, and a 12 MiB MCP request body. Score attachments are limited to one 8 MiB PDF/PNG/JPEG/WebP. A generated song has at most 64 bars; local score reading allows 512 written measures, full-file Meta reading 128, and MIDI export 512. MIDI uses 480 PPQ and the supplied meter, metadata, voicings, rhythm, swing, instruments, and mixer CC7 values.

`THEARTIST_META_ENABLED=0` on the server turns every Meta-backed path off: the
`capabilities` result then reports `meta.enabled: false`. Any attempted Meta call
fails as disabled (HTTP 503 on REST, an error result on MCP). An auto request
requiring no Meta work may still finish locally. Local reading, Music Transformer
generation and export keep working.

The import tool requires `attachmentConfirmed: true`. This asserts that the user explicitly attached this score for analysis. It accepts inline bytes, never filesystem paths or remote URLs. Do not gather journals, photographs, or other private files to supply it. `engine: "local"` is the request default and calls no model. The editor's Use Meta model checkbox is off by default and selects `verified` when checked; only Analyze score starts work. MCP clients choose their engine explicitly.

The same import request supports `mode: "chord_symbols"` (default, printed transcription)
and explicit `mode: "infer_harmony"` (notes-based interpretation). Preserve the echoed
mode, `analysisSource` (`local`, `meta`, `mixed`) and every measure's `chordBasis`,
`confidence`, `note`, read `notes`/`bassNotes`, `noChord`, source meter and `needsReview`.
Local results have a null model/request ID; mixed results retain provider metadata
per assisted bar. With `auto` and `infer_harmony`, each harmony batch receives the
complete ordered score synopsis, including key/meter, printed versus inferred
chords, pitch classes and known sections. All inferred bars are eligible, even
confident local results; printed chords and N.C. stay intact. At most two batches
of eight bars and 512 notes each are reviewed. Unreviewed bars retain their local
analysis and are identified as unreviewed.

One additional form request uses the complete updated synopsis and fills only
uncovered ranges, preserving existing sections even when their type is null.
Its proposals use `basis: "inferred"` and evidence; uncertain functions may remain
null, and an empty proposal is valid. Preserve `formAnalysis: {model, requestId,
sectionsProposed}` when present, including a zero count. This separate call is not
implied by the per-bar harmony request IDs.

The full synopsis is limited to 512 bars and 40 KiB, with no truncation. Each
assist/form call allows 64 KiB serialized input, 45 seconds, 4096 completion
tokens and $0.10; the combined import has at most three calls and a $0.30 admission.
Unsupported local files fail with no Meta request; `auto` never silently sends the
whole attachment. Full-file `meta` is a separate selection with one 75-second,
8192-token, $1.35 call, returning harmony and form together.

`meta.fullFileScoreImport` reports whether that explicit full-file option is
available: enabled, configured, Standard `muse-spark-1.3`, and either a non-public
host or explicit `THEARTIST_PUBLIC_META_READER=1`.
Clients should treat an absent field as unavailable. The public REST server
rejects full-file imports with 403 unless opted in, while retaining local and bounded assist.
Configuration, budget and provider errors do not become local-looking successes.
Request IDs, usage and costs are ledgered; per-request settlement excludes other
callers' concurrent costs. A guarded open-weight JSON retry counts both attempts
in its calling operation's cost; Standard Meta does not retry malformed output.

Inferred harmony and form require review, and do not import melody performance
tracks. See [score analysis](score-analysis.md) and the
[real fixture evaluation](../experiments/import_eval/README.md), including its PNG
reading failure, for coverage and accuracy limits.

The cooperative cancellation path belongs to REST `/api/plan/song/stream`:
disconnect stops later calls and section generation, while an already-running
bounded call finishes and settles its cost. Closing a client does not undo that
charge. MCP `plan_song` returns a non-streaming planning trace; it does not expose
the editor's streaming generation/cancellation workflow.

`export_daw` writes a unique MIDI under `backend/.exports/` and opens Logic Pro or reveals the file for Ableton. It is annotated as a side effect and requires all three gates: server environment `THEARTIST_MCP_ALLOW_DAW=1`, per-call `confirmed: true` after the user's explicit request, and a direct loopback connection. Remote addresses and forwarded/proxied requests are rejected. Downloading MIDI has no such side effect and needs no opt-in.

## Voyager on a shared host

The public [Voyager project](https://voyager.pearlleestudio.co) currently plays
pre-generated audio. Its Python adapter already defaults to MCP, but the website
does not yet invoke that pipeline to generate a new song.

TheArtist's Docker image includes this MCP server and SDK. The prepared Compose
configuration starts the public REST service and Caddy, not a Voyager worker;
`THEARTIST_PUBLIC_HOST=1` keeps `/mcp/` unmounted. Packaging the code in an image
does not enable a remote endpoint.

To add browser-triggered music, Voyager needs a request/job endpoint and its own
rendering service: browser → Voyager job → shared Artist `build_song` → arrangement
→ Voyager audio renderer/storage → audio URL for the browser. A separate Voyager
container can share the same VM without duplicating the 18 music models. Images,
journals, API keys and generated audio are not part of the public source/image.
The source can remain private while the user-facing website is public.

Two explicit transports are possible. REST can use the existing public music API.
For MCP, an authenticated remote endpoint or a restricted internal endpoint must
first be implemented, preserving public-host restrictions and the single shared
model process. Neither exists in the prepared deployment yet. Do not enable all
local-only routes merely to make `/mcp/` reachable, and do not retry through REST
automatically after an MCP error.

The 18-model CPU capacity probe covers symbolic music generation, not a separate
vision model or concurrent audio rendering. An event-specific Voyager extension
can use the permitted Meta API for interpretation; that integration still needs
implementation and evaluation before a live end-to-end claim.

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

Protocol tests use the real SDK client and server through an in-process ASGI transport. They exercise initialize, tool discovery, schema envelopes, MIDI round trips, errors and DAW gates without model/provider calls or launching applications. A sixteen-bar Logic MIDI handoff was observed separately; detailed playback, GM/controller interpretation, Ableton and Scripter host checks remain in the [manual checklist](manual-checks.md).

SDK reference: [official Python SDK, v1.x](https://github.com/modelcontextprotocol/python-sdk/tree/v1.x).
