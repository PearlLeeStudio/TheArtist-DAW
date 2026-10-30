# Returning choruses with default OMT retrieval

Full form now offers **Keep the theme** (the UI default) or **New progression**.
Keep the theme takes the first complete, same-length chorus from the locked
sketch, otherwise the first generated chorus. It retains that progression and
adapts only the planned cadence. Unsupported or incomplete material is not reused.
Changing the generated source during the bounded judge loop refreshes its
dependent choruses. Different-length choruses are generated separately.

Reused sections carry `source: reuse`, a source-bar/model reference and the exact
retained/changed slots. They are not counted as freshly generated neural slots.
The API defaults to `chorusMode: new` when the field is omitted, preserving old
clients; the current form dialog sends the musician's explicit choice.

## Local paired measurement

Actual F1, CPU, four Torch threads, OMT ready, Berklee disabled; three 64-bar
genre-template conditions, seeds 17–21, alternating mode order, both modes
warmed first. Model loading, Meta, network, browser and audio are excluded.
The changed later context is intentional, so this is not an identical-output
optimization. [Raw samples and paired traces](chorus-memory.json) and the
[runner](../../backend/scripts/experience_benchmark.py) are included.

| Case | New p50 / p95 (ms) | Reuse p50 / p95 (ms) | p50 reduction |
|---|---:|---:|---:|
| Pop, C major | 2,302.9 / 2,306.3 | 1,679.9 / 1,699.3 | 27.0% |
| Pop, A minor | 2,275.8 / 2,333.2 | 1,698.4 / 1,713.5 | 25.4% |
| Rock, E major | 2,285.9 / 2,334.8 | 1,687.5 / 1,716.1 | 26.2% |

Each reuse run generated seven sections and reused two choruses (sixteen bars).
All recorded retained slots matched their source; zero or two of the thirty-two
reused slots changed at endings. Five samples per condition are descriptive,
not a population latency estimate. This proves the reuse behavior and fewer
local generation calls; it does not prove better music. The
[blind comparison](../agent_eval/fixed-seed/listening/chorus-blind.html) is ready
for human responses; none have been collected.

Three [live Standard Meta plans](../meta/chorus-reuse-smoke.json) also completed
with actual F1, OMT and two reused choruses each. Total spend was $0.058221 with
zero outstanding reservations. Source regeneration refreshed its later choruses.
All three final judge decisions still requested regeneration, mainly for
out-of-key harmony. Thus successful execution and chorus identity do **not**
establish broad musical improvement or judge acceptance.

## Browser timing instrumentation

Open the app with `?measurePerformance=1`. The optional
`window.theArtistPerformance.samples()`, `.summary()` and `.clear()` console
methods expose at most 200 in-memory samples. No names, score content, work dates
or telemetry requests are recorded. Successful p50/p95 and unsuccessful counts
are separate. Clear between controlled runs and retain the raw samples.

| Sample | Measured boundary |
|---|---|
| `import.review` | Analyze click to review-ready result; grouped by Reader |
| `generate.result`, `section.result` | Request start to complete result, before audition |
| `form.result` | Full-form request to completed trace; grouped by planner |
| `instrument.ready` | Sample preparation, grouped by cold/warm cached load |
| `play.transport` | Playback start request to transport scheduling, grouped by AudioContext state |

Sample/transport readiness is **not acoustic first sound**. Prefetch can make
selection warm, but these counters do not prove zero switching delay. Browser
cold/warm distributions, audio-device latency and external Meta latency remain
unmeasured; report them separately when available.
