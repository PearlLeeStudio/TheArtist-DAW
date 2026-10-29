# Import evaluation

Four self-authored score fixtures were processed with real Standard `muse-spark-1.3`
requests. All requests completed, but the PNG chord reading failed. These small
fixtures verify request flow and expose limitations; they are not an accuracy benchmark.

| Fixture | Reader | Exact chords | Calls | Cost (USD) |
| --- | --- | --- | --- | --- |
| C-major vector PDF, 1 bar | Local notes + Meta harmony/form | 1/1 | 2 | 0.00527425 |
| F-major vector PDF, 1 bar | Local notes + Meta harmony/form | 1/1 | 2 | 0.00514250 |
| C8 → F8 → C4 vector PDF, 20 bars | Local notes + Meta harmony/form | 20/20 | 3 | 0.01879005 |
| Notes-only PNG, 4 bars | Full file (Meta) | **1/4** | 1 | 0.01775275 |
| Total | | | 8 | 0.04695955 |

The 20-bar PDF contains the actual twenty source pages, assembled from the two
original single-bar vector fixtures. Both harmony requests received the complete
twenty-bar synopsis: the first reviewed bars 1–8, the second bars 9–16. Bars 17–20
retained their local analysis and are reported as unreviewed by Meta. The form
request received all twenty bars. The final 20/20 result therefore includes four
locally analyzed bars, not twenty Meta-reviewed bars.

Form interpretation is reported separately from chord reading. The one-bar fixtures
produced no sections. The twenty-bar fixture produced three inferred, neutral
`Section` ranges of 8/8/4 bars, following the harmonic and meter changes. Their
musical function remained `null`; no unsupported Intro or Verse label was forced.
These fixtures contain no printed section headings or authoritative song-form labels,
so this evaluation does not assign a song-form accuracy score.

The PNG's written notes support **C–Am–Dm–G7**. Meta returned **C–G–F–C**, with
incorrect note evidence and high confidence for the three wrong bars. Its single
inferred section also describes that incorrect progression. Key and bar count were
correct, but successful transport, a valid response, and model confidence do not
establish optical accuracy. Full-file reading remains a draft requiring score review.
No additional retry was made to select a better result.

## Artifacts

- `results.json`: normalized responses, exact text requests, request IDs, token usage,
  costs, separate chord comparisons and form suggestions. Attachment bytes are omitted
  from the request log; fixture hashes identify the inputs.
- `context-20.pdf`: the self-authored twenty-bar source used in this run.
- `run.py`: paid evaluation runner; never imported by the unit-test suite.
- Original source fixtures: `backend/tests/fixtures/vector-score-c.pdf`,
  `vector-score-f.pdf`, and `notes-only.png`. No user scores were used.

## Reproduce

Use the backend Python environment and configure `MODEL_API_KEY` for the Meta
Standard API. The runner makes real paid requests. Pass absolute paths and keep the
ledger outside the public repository. Its default batch cap is $3, with a hard
runner maximum of $10; the product's individual request limits also apply.

```sh
python /absolute/path/TheArtist-DAW/experiments/import_eval/run.py \
  --backend /absolute/path/TheArtist-DAW/backend \
  --fixture-c /absolute/path/TheArtist-DAW/backend/tests/fixtures/vector-score-c.pdf \
  --fixture-f /absolute/path/TheArtist-DAW/backend/tests/fixtures/vector-score-f.pdf \
  --fixture-png /absolute/path/TheArtist-DAW/backend/tests/fixtures/notes-only.png \
  --context-pdf /absolute/path/evaluation/context-20.pdf \
  --ledger /absolute/path/private/import-eval-ledger.json \
  --output /absolute/path/evaluation/results.json \
  --budget-usd 3
```

Create the destination directories first. Existing result files are never overwritten.
Use `--case vector-c`, `--case vector-f`, `--case context-20`, or `--case notes-png`
to select a subset. Exit code 1 indicates a request or pipeline failure; exit code 2
indicates a completed pipeline with a chord/key/bar-count mismatch. Exit code 0 does
not validate musical form, which remains unscored. Repeated model outputs may vary.
