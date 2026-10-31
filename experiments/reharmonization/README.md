# Reharmonization selector comparison

This offline experiment compares four ways to select **three** sparse alternatives
from the same mathematical search pool. It does not change the frontend, train a
model, compare unrestricted full-passage generators, or establish listening quality.

The [Korean synthesis](../../docs/reharmonization-evaluation.md) explains the
completed evidence, recommendation ranks, eight-position deduplication, and the
distinction between genre adapters and the F-series checkpoints.

## Fixed comparison

| Condition | Selection path | Own-model score available to Meta |
| --- | --- | --- |
| Local | F4 ranks the shared pool; take its first three | No Meta call |
| Meta | Standard Muse Spark chooses three from the same pool | No |
| Hybrid 1 | F4 scores the pool; Muse Spark chooses three | Yes |
| Hybrid 2 | Reuse the actual Hybrid 1 result, original context and scored pool; Muse Spark reviews once | Yes |

All conditions use the same three mathematical search families, substitution
limits, convention priors, input key, four-bar context and selected middle bar.
At most two of the eight chord slots may change. Genre is not an input. Hybrid 2
can retain good first-pass choices; it is not forced to make changes and does not
apply substitutions on top of an already modified passage. Its reported total
cost includes its shared first pass; the ledger bills that first pass only once.
The production agent's dynamic function-calling loop is not timed by this experiment.

## Real paired material

Source: Row, Tang and Fazekas, [JAZZVAR](https://zenodo.org/records/11264676),
with [paper](https://arxiv.org/abs/2307.09670). The release API identifies the data
license as **CC BY-NC-SA 2.0**. Downloaded MIDI, derived musical inputs, detailed
candidate outputs and the spend ledger stay in the ignored `.cache/` directory;
the corpus is not redistributed or added to training or product deployment.

The published archive contains 505 metadata rows. The conservative conversion
retains 67 distinct eligible originals across 16 normalized tune identities.
Before any paid calls, a fixed hash ordering and tune-balanced round robin select
42 original/performance pairs, at most three passages per tune. This gives up to
504 candidate positions (42 × 4 × 3); identical musical candidates across methods
are deduplicated during judging and must not be counted as independent outputs.

Original MIDI must have a separate labeled melody track, or a separate highest
monophonic track, and accompaniment whose pitch-class set matches a supported
chord exactly. The actual bass resolves root-position ambiguities; ambiguous
inversions and unsupported combinations are excluded, not silently simplified.
Two half-bar anchors per bar discard finer harmonic rhythm. Exclusion records and
source hashes are retained. Track-title casing and recording suffixes are grouped
as the same tune; transpositions and repeated windows are not independent songs.
The 40 main passages cover 29 major-key and 11 minor-key examples. In 11 passages,
both selected half-bars originally contain the same chord. Every selected bar has
some melody evidence. Melody-track identification and source key annotations were
not independently checked by human transcribers; the inferred track rule can err.

Performance exports have inconsistent meter and timing metadata. They are used
only as a transposed **whole-excerpt pitch-class profile**, with no claimed beat
alignment or expert chord labels. Original/performance pairs can differ through
ornamentation, voicing and interpretation as well as reharmonization. Profile
similarity is a secondary descriptive measure, not correctness or preference.

## Evaluation specified before paid execution

- Primary automated assessment: mean of the three candidates' anonymous Meta
  rubric scores, averaged across two shuffled presentations. Four equally weighted
  0–4 dimensions: harmonic continuity, melody compatibility, useful change and
  retained identity. Also report first-ranked, best-of-three and worst-of-three;
  best-of-three is an oracle view, not the primary result.
- The judge sees original chords, original melody-duration profiles and anonymous
  versions, with no method names, model scores, convention scores, title or artist.
  Identical versions receive the same rating within a presentation. An unchanged
  original and a fixed semitone perturbation serve as controls. Order sensitivity
  and control behavior are reported. Meta judging its own selections is a potential
  bias, not independent human validation.
- Mechanical checks: selected-slot preservation, change bounds, parser validity,
  candidate diversity and failure rate. Deterministic motion and strict melody
  chord-tone support are descriptive proxies; tensions and passing tones are not
  automatically errors. Dense chords may raise chord-tone support artificially.
- F1 evaluates the same candidates as a secondary learned measure; F4 selects the
  local arm. Shared training ancestry or corpus overlap may bias both, so this is
  not a fully independent held-out quality test.
- Tune-balanced means and paired bootstrap intervals resample tune groups, not
  individual correlated windows. Failures remain in the report. Comparisons using
  only common successful cases are labeled separately from completion coverage.
  Six pairwise intervals are exploratory and not adjusted for multiple comparisons.
  If the leading method's advantage is unstable across orderings/metrics or its
  paired interval overlaps zero, report that there is no clear quality winner.
  Do not select a frontend design automatically from this experiment.

The first two passages form a pilot; the remaining 40 form the main batch. A
protocol change after the pilot must be recorded and pilot results kept separate.
The frozen dataset digest connects the batches. Standard `muse-spark-1.3` only,
60-second call timeout, at most five paid calls per case, two concurrent cases,
$0.12 reservation cap per request and one persistent **$10 total ledger**.
No format retries, success fallback, or paid rerun to replace an unfavorable result.

The pilot's 2,048-token selection and 3,000-token judge limits caused one selection
and one judgment to exhaust output tokens, including reasoning. Its ten calls cost
$0.11096150 and are retained as pilot evidence. Main protocol version 2 uses
4,096 and 8,192 output-token caps respectively, with low reasoning effort; the
pilot's two passages are excluded from the 40-passage main comparison. The total
ledger cap includes both batches.
Costs are calculated from returned token usage using the project's Standard rates
of $1.25 input, $0.15 cached input and $4.25 output per million tokens; they are
ledger measurements rather than a reconciled provider invoice. Temperature and
top-p are left at provider defaults. These two judge calls therefore vary in both
presentation order and sampling, which cannot be separated by this experiment.

## Rank-gap follow-up

After inspecting the main result, the user requested one additional complete
repeat and a comparison of recommendation positions 1–2 and 2–3, then proposed
retaining the first two candidates from each method (eight positions). Run the
same 40 passages once more with the same pools, prompts, presentation seeds,
model settings and two judgments per passage. No previous result is replaced.
The repeat adds at most 200 calls under the same $10 ledger. It tests stochastic
repeatability on the same songs, not generalization to 40 new passages.

The follow-up reports original, repeat and combined rank means, signed adjacent
gaps, ties and reversals. Recommendations retain the selector's order; do not
re-sort by judge score and call that recommendation accuracy. Average repeats
within each passage, then passages within each tune, and bootstrap tune groups.
Also report the eight-position union after musical deduplication, and how often
excluding third choices loses the highest automated score from all 12 positions.
That last measure is an oracle coverage check, not achieved user preference.
Original-rank findings are post-hoc; the repeat is a targeted follow-up rather
than an independently preregistered or human-listening evaluation. Product UI
changes remain deferred.

The F4 repeat was interrupted after 13 fully recorded passages when the user
reconsidered the local checkpoint. Its partial results and raw responses are
preserved separately; it is not a completed 40-passage replication. Two active
requests lost their returned usage on termination. Their combined $0.07258325
reservation ceiling is accounted conservatively, not described as measured spend.
Subsequent runs finish an active API call on SIGINT/SIGTERM and stop before
starting another paid call.

An F1 v2 (`ft_f1_v2`) comparison was started while model terminology was being
clarified, then stopped gracefully when the user explicitly selected **F2 and
F3**. Its partial records remain separate. The complete follow-up runs F2 and F3
each on the same 40 passages and four conditions. F1, F1 v2, F2, F3 and F4
were first scored locally against the frozen pools; changed-chord tone counts,
altered-quality rates and melody support are descriptive, not listening ratings.
F1 v2 is the selection-corrected jazz adaptation; the v1 F1 reference checkpoint
is weight-identical to the pop baseline. These are changed-model experiments,
not identical repetitions or additional independent songs. Keep each model's
rank and coverage results separate from the F4 batch. The same prompts,
call limits, dataset, mathematical search and $10 shared ledger remain in use.
F2 and F3 run concurrently with one case worker each, retaining the overall
limit of two simultaneous cases. Neither changes product defaults or UI.

## Reproduction

[`reharm_eval_data.py`](../../agent/reharm_eval_data.py) validates the official ZIP
MD5 `7084a3c7bca5126880f9c24aac41fd3a`, extracts in memory and freezes the cases.
Its CLI takes absolute `--backend`, `--archive` and `--output` paths, with optional
`--maximum` (48 by default). Rebuilding from the original archive reproduces the
same 42 cases and exclusions. The frozen input SHA-256 is
`74e36a2caf0d4616115d481942b7980a9a32d225c5b35771143ab73912a48e34`.
The search/scoring core is revision `ec9ca4c551a2c291f61de2b59436154d895f053b`.
Local checkpoint SHA-256 values (weights are not redistributed here):

| Role | Checkpoint | SHA-256 |
| --- | --- | --- |
| Selector | `ft_f4` / `ft_jazz_pop29/best.pt` | `453265f5e8f76ac150674be4d4d74eecad89d20e743b0e6e5e38ce60366a8794` |
| Secondary scorer | `ft_f1` / `ft_jazz_pop80/best.pt` | `db9c09d5e1c8a5cee33cb391174c41316bbb4f21e807b345cc9933debe52078c` |
| Follow-up selector | `ft_f2` / `ft_jazz_pop67/best.pt` | `f9aebcae5294c331aab43c509af698062f9bc7e50fb06e92280ee93126491d7b` |
| Follow-up selector | `ft_f3` / `ft_jazz_pop50/best.pt` | `5fc8c443f4225e979d89e5c401c05ff8099d9e10ed717e794c126e750e02874c` |

[`compare_reharmonization.py`](../../agent/compare_reharmonization.py) accepts absolute
`--backend`, `--dataset`, `--output`, `--ledger` and `--raw` paths, plus `--offset`,
`--limit` and `--workers`. Existing outputs are refused. Run through the project's
development wrapper with `MODEL_API_KEY` supplied in the environment.
`--model-key` explicitly overrides the local/hybrid scorer while preserving the
frozen musical dataset. SIGINT/SIGTERM requests a graceful stop after active
requests settle; unstarted cases and cancelled stages remain visible.

[`report_reharmonization.py`](../../agent/report_reharmonization.py) takes absolute
`--input`, `--summary`, `--markdown` and `--html` paths. It makes no model call and
refuses to overwrite existing outputs. The JSON/Markdown summarize numerical
evidence; keep the detailed HTML in `.cache/` because it contains derived musical
material. Raw requests, completions, request IDs and token usage remain available
locally for auditing.

[`rank_reharmonization.py`](../../agent/rank_reharmonization.py) accepts `--original`,
`--summary` and `--markdown`, optionally `--repeat` for an identical-input repeat
or `--comparison` for a changed local checkpoint. Both require absolute paths.
It verifies preserved inputs/pools, keeps changed-model results separate, and
computes signed recommendation-position gaps and deduplicated top-two coverage.
[`probe_reharm_models.py`](../../agent/probe_reharm_models.py) performs the local
checkpoint probe with `--backend`, `--input` and `--output`; detailed output
contains musical data and belongs in `.cache/`. It makes no API call.

The completed [F4 main results and interpretation](results.md) cover all 40 passages:
480 candidate positions, 225 distinct versions, 200 successful main calls. The
[usage audit](calls.json) retains all 210 pilot/main calls, including the pilot's
two failures; their returned-usage cost is $2.46504555.

## Follow-up evidence and interpretation

- [F4 rank gaps and partial repeat](f4-rank-results.md): original 40 passages;
  13 completed repeat passages. The paired combined table covers only those 13.
- [F2 results](f2-results.md) and [F3 results](f3-results.md): each completed all
  40 passages and 200 actual calls, with no selection or judgment failure.
  Their 480 candidate positions contain 216 and 214 distinct versions respectively.
- [F2/F3 recommendation ranks](f2-f3-rank-results.md), with [numerical records](f2-f3-rank-summary.json):
  all first-two F2-minus-F3 intervals cross zero. The F4 hybrid second-versus-third
  gap does not clearly replicate. First-two unions retain the all-12 oracle best
  in 35/40 passages per model, averaging 4.021 and 3.896 distinct alternatives.
  **Deduplicating all three choices from each method first** retains only 4–8
  alternatives for F2 and 3–8 for F3; all evaluated options fit within eight cards
  in every tested passage. F4's corresponding range is 4–7. This needs no extra
  generation call and preserves the evaluated third choices, but is not a
  guarantee for future inputs or a product implementation.
- [Local-checkpoint descriptive probe](local-model-probe-summary.json): identical
  frozen pools, actual local weights, no API calls and no listening-quality claim.
- [Follow-up usage audit](followup-calls.json): all 502 additional calls, including
  75 in the interrupted F4 repeat and 27 in the interrupted F1 v2 run. F1 v2 has
  five complete cases, one partially completed case and 34 not started.

F2 returned-usage cost is $2.29170940; F3 is $2.30101735. Across all 712 calls,
known returned-usage cost is **$8.24515680**. The two interrupted F4 requests add
an unknown-usage reservation ceiling of **$0.07258325**, giving conservative
ledger accounting of **$8.31774005**, with no outstanding reservation. F2's own
summary captured the shared ledger while F3 was still running; the follow-up
audit is the final combined ledger state. Audit exports whitelist billing fields
and match raw-response request IDs, retaining no prompts, source MIDI or timestamps.

No frontend change is made by these experiments. Validation: full backend suite
`Ran 609 tests ... OK`, report checks 9 and rank checks 6 pass; frontend build,
lint and `import app.main: ok` pass. The existing bundle-size warning remains.
