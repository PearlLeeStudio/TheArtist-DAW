# Reharmonization selector comparison

This offline experiment compares four ways to select **three** sparse alternatives
from the same mathematical search pool. It does not change the frontend, train a
model, compare unrestricted full-passage generators, or establish listening quality.

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

[`compare_reharmonization.py`](../../agent/compare_reharmonization.py) accepts absolute
`--backend`, `--dataset`, `--output`, `--ledger` and `--raw` paths, plus `--offset`,
`--limit` and `--workers`. Existing outputs are refused. Run through the project's
development wrapper with `MODEL_API_KEY` supplied in the environment.

[`report_reharmonization.py`](../../agent/report_reharmonization.py) takes absolute
`--input`, `--summary`, `--markdown` and `--html` paths. It makes no model call and
refuses to overwrite existing outputs. The JSON/Markdown summarize numerical
evidence; keep the detailed HTML in `.cache/` because it contains derived musical
material. Raw requests, completions, request IDs and token usage remain available
locally for auditing.

The completed [main results and interpretation](results.md) cover all 40 passages:
480 candidate positions, 225 distinct versions, 200 successful main calls. The
[usage audit](calls.json) retains all 210 pilot/main calls, including the pilot's
two failures. Total ledger cost is $2.46504555, with no outstanding reservation.
No frontend change is made by this experiment.
