# Chord-generation speed probe

Per cell: 2 recorded and 1 warm-up runs; key C major, context bars 0, section type none, seed 0; created 2026-10-27T16:43:18+00:00.

| genre | bars | model | p50 ms | p95 ms | composing share | ranking share |
|---|---:|---|---:|---:|---:|---:|
| pop | 8 | ft_f1 | 386.3 | 391.0 | 94.0% | 6.0% |
| pop | 32 | ft_f1 | 2215.4 | 2218.4 | 96.0% | 4.0% |
| pop | 64 | ft_f1 | 6745.0 | 6779.0 | 98.0% | 2.1% |
| jazz | 8 | ft_f4 | 280.0 | 291.3 | 90.9% | 9.1% |
| jazz | 32 | ft_f4 | 1396.6 | 1422.9 | 91.4% | 8.6% |
| jazz | 64 | ft_f4 | 3839.6 | 3870.3 | 94.2% | 5.8% |

A stage runs from its on_phase event to the next event or the return; a share is the median over the recorded runs of stage time / wall time.

Model load, once per model and outside the timed runs: ft_f1 110 ms, ft_f4 107 ms.

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
