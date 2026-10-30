# Runtime performance

The attention cache reuses prior token computations without changing weights,
sampling settings, candidate count, ranking, song-form rules or voicing. It is
request-local and is rebuilt when the context window slides, preserving the
original cropped-context behavior. Training and prefix tuning use the existing
uncached path. Set `THEARTIST_DISABLE_KV_CACHE=1` to compare or roll back inference.

## Local generation

CPU, Darwin arm64, four Torch threads. Medians of three paired runs with seeds
17–19, after one warmup per mode. Each chord request generates all three
candidates and includes ranking and voicing. Checkpoint loading, HTTP/browser
time, Meta planning/judging and RAG are excluded. Timing order alternates.

| Request | Before | After | Speedup |
|---|---:|---:|---:|
| F1, 8 bars | 389 ms | 208 ms | 1.87× |
| F1, 32 bars | 2,210 ms | 836 ms | 2.64× |
| F1, 64 bars | 7,183 ms | 1,846 ms | 3.89× |
| F4, 8 bars | 293 ms | 170 ms | 1.73× |
| F4, 32 bars | 1,453 ms | 658 ms | 2.21× |
| F4, 64 bars | 3,827 ms | 1,359 ms | 2.82× |
| Rock LoRA, 8 bars | 447 ms | 243 ms | 1.84× |
| Rock LoRA, 32 bars | 2,449 ms | 951 ms | 2.57× |
| Rock LoRA, 64 bars | 7,519 ms | 1,960 ms | 3.84× |
| Complete Song Form, 32 bars, genre template + F1 | 2,385 ms | 993 ms | 2.40× |

All 30 pairs have identical musical results and provenance after excluding
generated IDs and elapsed-time fields. Raw samples and output hashes are in
[inference_cache.json](inference_cache.json). Reproduce with RAG explicitly disabled (the product now defaults OMT on):

```sh
THEARTIST_DISABLE_RAG=1 uv run --frozen --directory /absolute/path/TheArtist-DAW/backend python -m scripts.inference_benchmark --out /absolute/path/benchmark.json
```
The three installed checkpoints were loaded locally; no model or API download
is part of the measurement. This sample establishes preserved results on these
inputs, not better musical quality or bitwise equivalence on every device.

## Import Source

Stem positions, flag/dot lists and shared beam durations are reused within a
page. Decoded scores use an in-process LRU cache of at most four entries and
8 MiB of serialized results, with a five-minute TTL checked on access. No PDF
bytes or disk cache are retained. Keys include the PDF digest and parsing limits;
each caller gets an independent score. Errors are not cached.

Five paired runs in a warm Python process include PDF decoding and local harmony
analysis. The large local fixture has 24 pages, 465 measures and 5,829 notes;
its content, title and filename are excluded from the repository.

| Local import | Before | First parse after change | Reused document |
|---|---:|---:|---:|
| Synthetic one-bar PDF | 1.568 ms | 1.620 ms | 0.189 ms |
| Large vector score | 1,565 ms | 1,485 ms | 159 ms |

The small cold case has no improvement. The large cold case improves about 5%;
the repeated case about 9.8×. Parsed notes, durations, warnings and final local
analysis match the baseline. Raw timings are in [score_import.json](score_import.json).
The large private fixture is not distributed, so its measurement cannot be
reproduced from a clean public checkout.

Meta assist also benefits within its first import: local analysis and note
assistance previously decoded the same PDF independently. The second read now
reuses the parsed score. Its two independent eight-bar harmony reviews run
concurrently against the same frozen synopsis. Form analysis still waits for
their results. Request context and thread-safe cost totals cover both workers,
including failure; the three-call/$0.30 upper bound and per-call timeouts remain.
Both reviews may already be in flight when one fails. No live Meta latency or
output-quality improvement is claimed for this scheduling change.

## Play

After the first Play gesture, browsing an instrument family preloads up to two
instruments at a time. Pointer entry or keyboard focus on a specific sound
starts its load immediately, sharing the same instance with selection and
playback. Browsing another family drops stale queued work. The selected sound
does not wait behind background work. Completed foreground loads clear their
timeout timers.

Tests use controlled sample promises and verify gesture gating, coalesced loads,
queue bounds, stale-family replacement, foreground priority, readiness, separate
layer routing, timeout and failure handling. UI layout, samples, levels and note
scheduling are unchanged. A sample already loaded needs no additional download
on selection; a first uncached network load can still take time. Browser network
latency and audible switching were not measured, so zero-delay playback is not
claimed.

## Quality and remaining work

These measurements used **RAG off**. The product has since gained default-on
[local OMT retrieval](../../docs/theory-retrieval.md), with Berklee disabled and
no additional embedding or explanation model. The old Snowflake/Chroma/Gemma
research path remains outside the product. The timing table is a controlled
KV-cache comparison, not a benchmark of the current end-to-end default. A broader
OMT-on/off quality and latency comparison, live Meta import timing, and audible
instrument-switch timing remain unmeasured.
