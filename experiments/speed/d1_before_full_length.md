# Chord-generation speed probe

Per cell: 2 recorded and 1 warm-up runs; key C major, context bars 0, section type none, seed 0; created 2026-10-27T16:05:26+00:00.

| genre | bars | model | p50 ms | p95 ms | composing share | ranking share |
|---|---:|---|---:|---:|---:|---:|
| pop | 8 | ft_f1 | 432.4 | 432.7 | 94.4% | 5.6% |
| pop | 32 | ft_f1 | 1659.7 | 1808.7 | 94.7% | 5.3% |
| pop | 64 | ft_f1 | 1871.6 | 2192.6 | 90.5% | 9.5% |
| jazz | 8 | ft_f4 | 457.7 | 467.9 | 93.8% | 6.1% |
| jazz | 32 | ft_f4 | 2494.1 | 2626.3 | 95.5% | 4.4% |
| jazz | 64 | ft_f4 | 5695.8 | 6399.2 | 95.7% | 4.3% |

A stage runs from its on_phase event to the next event or the return; a share is the median over the recorded runs of stage time / wall time.

Model load, once per model and outside the timed runs: ft_f1 198 ms, ft_f4 199 ms.

Notes:

- pop x 32 bars: sampling passes returned 14 to 32 bars (median 22) of 32 requested; the service pads the rest.
- pop x 64 bars: sampling passes returned 14 to 40 bars (median 22) of 64 requested; the service pads the rest.
- jazz x 64 bars: sampling passes returned 30 to 64 bars (median 64) of 64 requested; the service pads the rest.

## Environment

    torch                            2.13.0
    torch threads                    4 (interop 10)
    device                           cpu
    platform.machine                 arm64
    platform.processor               arm
    python                           3.12.13
    service modules                  torch yes, peft yes, physics_rerank yes, rag yes
    THEARTIST_DISABLE_RAG            1
    THEARTIST_DISABLE_R2_RERANK      (unset)
    THEARTIST_DISABLE_EXPLANATIONS   (unset)
    THEARTIST_DISABLE_VOICE_LEADING  (unset)
