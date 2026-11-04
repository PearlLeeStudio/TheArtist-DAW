# Local, Meta and hybrid: Reharmonize and Import Score

The recorded comparisons show a benefit from Meta on specific tasks. In
Reharmonize, the one-pass hybrid scored above the own-model-only selector in all
three checkpoint runs. In note-to-chord interpretation, Meta answered more slots
and achieved higher overall exact agreement than the local analyzer. In a separate
five-PDF diagnostic, the one-pass hybrid completed more files than either reader
alone. These are different measurements; they are not one overall music score.

This report consolidates existing results without new paid calls. It distinguishes
the evaluated implementations from the current editor. All Meta-only arms below
use Standard `muse-spark-1.3`, not Muse Spark Open or a Contributor model.

## What the three conditions mean

For the **actual product tool loop**, see the separate
[220-passage, 880-execution comparison](../experiments/reharmonize_agent_eval/extended-summary.md):
Muse Spark Open passed 440/440 runs and Spark 1.3 passed 439/440 with the same F1
scorer, frozen requests and constraints. That measures execution reliability, not
the fixed-pool selector scores below or a contest between F1 and Muse.

The [completed expanded product-agent report](../experiments/reharmonize_agent_stress/completion-summary.md)
adds requested-mode and constraint coverage without changing the product. Both
providers started all 4,240 original case/repeat rows across 680 authored inputs
and 128 condition cells. Open passed 4,186; Spark 1.3 passed 4,144. Both retain 54
failures on nine inputs identified as capacity-limited before paid calls. Spark
also retains 27 timeouts, 13 tool-call response failures, one HTTP 503 and one
operator cancellation. After a post-hoc stop at 1,716 Spark executions, the
participant explicitly requested finishing only the 2,524 unstarted rows; no prior
outcome was replaced. The [partial report](../experiments/reharmonize_agent_stress/summary.md)
is preserved. Nominal accounting is Baseten $28.04348590 and Meta $53.21155010,
combined **$81.25503600**, including $0.91077275 reserved for unknown usage;
it is not reconciled billing. The temporal break, smaller continuation batches
and provider/cache differences limit timing comparisons. This is execution and
constraint evidence on authored fixtures, not a replacement for the fixed-pool
comparison below or a musical-quality ranking.

| Task | Local / own model | Meta only | Hybrid |
|---|---|---|---|
| Reharmonize | The author's Music Transformer ranks a fixed mathematical substitution pool by conditional likelihood | Muse Spark chooses three alternatives from the same pool, without Transformer scores | Muse Spark chooses from the same pool with Transformer scores visible; `hybrid1` is one selection pass |
| Import: notes → chords | Deterministic duration/bass/voice-aware harmony analyzer; no Music Transformer in this benchmark | Muse Spark interprets the same extracted/generated notes and supplied key | Historical `auto`: keep local answers and ask Meta only about bars left without chords |
| Import: original PDF → score | Vector-PDF reader → local harmony analyzer → optional F1 completion of unresolved note-bearing bars | Muse Spark reads the original PDF once | Historical `hybrid1`: original PDF plus local reading → one Meta call → deterministic comparison |

**Import's local reader is not the Music Transformer.** The Transformer scores
Reharmonize candidates and can propose missing harmony after local score reading;
it does not recognize PDF glyphs. The notes benchmark therefore cannot establish
“Meta beats F1 at reading PDFs.”

## Reharmonize: same passages, three selection methods

Each checkpoint run uses the same **40 four-bar passages from 16 JAZZVAR tune
groups**, with eight half-bar chord slots per passage and at most two changed
slots. Every selector receives the same validated pool of 11–18 mathematical
candidates and returns three distinct choices. The Meta selector receives chord
context, not audio or melody; the judge additionally receives melody pitch-class
duration profiles.

The judge is Muse Spark with method names and selector scores hidden. It rates
continuity, melody fit, useful change and retained identity from **0 to 4**, in
two shuffled presentation orders. The reported score averages all three offered
candidates and both judgments, then balances tune groups; it is not the best
candidate's score or a percentage accuracy.

| Own-model checkpoint | Local only | Meta only | Hybrid, one pass | Hybrid − local |
|---|---:|---:|---:|---:|
| F4, original run | 2.464 | **2.671** | 2.624 | +0.160 |
| F2, follow-up | 2.516 | 2.589 | **2.688** | +0.172 |
| F3, follow-up | 2.524 | 2.565 | **2.644** | +0.120 |

All three methods completed 40/40 passages in each run. The three rows repeat
the same material, so they are not 120 independent test passages. Meta-only sees
no checkpoint score; its differences between runs reflect stochastic selection
and judgment, not an F2/F3/F4 input.

For F4, Meta − local is **+0.208/4**, with a paired 95% tune-bootstrap interval
of **[+0.042, +0.379]**. Hybrid − local is **+0.160/4**, interval
**[+0.032, +0.302]**. Meta − hybrid is only **+0.048/4**, interval
**[−0.026, +0.131]**, so that run does not establish a winner between Meta and
hybrid. Hybrid − local intervals are also positive for F2 **[+0.018, +0.322]**
and F3 **[+0.024, +0.224]**. These are exploratory intervals without a correction
for multiple comparisons.

### Selection time and cost

| F4 condition | Mean seconds per passage | Mean API cost per passage |
|---|---:|---:|
| Local only | 0.132 | $0 |
| Meta only | 7.503 | $0.01119 |
| Hybrid, one pass | 7.293 | $0.01112 |

These tune-balanced means include local search/scoring as applicable and exclude
the evaluation judge. They are offline selector measurements, not the production
agent's tool-loop or browser latency. The full F4 experiment, including the
two-pass arm and judges, used **200 calls / $2.35408405**. A separate ten-call
pilot cost $0.11096150; the combined ledger is **210 calls / $2.46504555**.
F2 and F3 used 200 calls each, costing $2.29170940 and $2.30101735 respectively.

A second hybrid pass reached 2.649 / 2.718 / 2.662 for F4 / F2 / F3, but its
paired interval against the first pass includes zero in every run. For F4 it
changed the candidate set in only 5/40 cases while nearly doubling selection
time and cost. It is retained as an ablation, not a fourth main mode.

### What transfers to the editor

The current Reharmonize agent lets Meta call `search_substitutions`, inspect
Music Transformer context scores and finish with `offer_candidates`. It is
bounded to four model turns, six tool calls and 100 seconds, and offers three
patches for the musician to audition and apply. The UI permits one to four
changed chords, broader than the experiment's two-change cap.

When Meta is disabled or unavailable under the supported local-recovery cases,
the current local selector preserves family/root diversity and says **picked
without Meta**. The experiment's local arm simply took the top three by model
likelihood. That newer local selector has not been measured in this comparison.
The scores support Meta's contribution against the recorded baseline, not a
measured advantage over every current fallback or every checkpoint.

The same model family selects and judges, so correlated preferences remain even
with blinded names. Local and Meta also have different selection objectives:
likelihood versus explicitly requested contrasting alternatives. No human
listening preference, full melodic phrasing or expert ground-truth
reharmonization was measured.

Records: [protocol](../experiments/reharmonization/README.md),
[F4 results](../experiments/reharmonization/results.md),
[F4 numeric summary](../experiments/reharmonization/summary.json),
[F2 results](../experiments/reharmonization/f2-results.md),
[F3 results](../experiments/reharmonization/f3-results.md),
[Korean interpretation](reharmonization-evaluation.md).
Implementation: [experiment](../agent/compare_reharmonization.py),
[search and own-model scorer](../backend/app/services/reharmonize.py),
[product agent](../backend/app/services/reharmonize_agent.py).

## Import A: chord interpretation from the same notes

This isolates harmonic interpretation from PDF recognition. **40 eight-bar
excerpts from 40 held-out songs across 13 genres** produce **640 chord slots**.
The product's voicing code realizes the progressions as notes in six variants,
including rootless voicings, inversions and melody tones. Every engine gets the
same notes and key; none gets the printed chord symbols. These are real
progressions rendered by code, not 40 independently engraved PDFs.

“Exact” in this scorer requires agreement on root, triad, seventh and bass.
It does not independently check every ninth/eleventh/thirteenth extension.
An unanswered slot counts as wrong in the overall column. Coverage means a
proposal exists; “exact where answered” excludes unanswered slots.

| Condition | Exact, all 640 slots | Coverage | Exact where answered | Paid calls | Total API cost |
|---|---:|---:|---:|---:|---:|
| Local analyzer | 77.8% | 81.6% | **95.4%** | 0 | $0 |
| Meta only | **89.5%** | **100.0%** | 89.5% | 40 | $0.3380 |
| Hybrid, unresolved-only assist | 83.9% | 95.3% | 88.0% | 6 | $0.0501 |
| Meta open weights (Muse Spark Open, Baseten, effort high) | 73.8% | 82.5% | 89.4% | 40 (7 failed) | $0.6329 |

Meta improves overall exact agreement by **11.7 percentage points** over local;
the hybrid improves it by **6.1 points** with fewer paid calls. Local is more
precise on the subset it answers. Rootless exact agreement rises from 0% local
to 47.3% Meta, while inversions fall from 100% local to 96.9% Meta. More answers
do not guarantee a correct interpretation of every bar.

Muse Spark Open, given the same notes through the open-weight endpoint, is as exact as
Muse Spark where it answers (89.4% against 89.5%) but lost 7 of 40 calls (3 replies
failed harmony validation, 4 hit the length limit), which leaves 17.5% of the slots
unanswered and its overall exact agreement below the local analyzer. Its median call
is 8.0 s against Meta's 5.1 s. Rootless voicings are its weakest variant (23.2% exact
overall), as they are for every engine.

Meta's median call time is 5.079 seconds and the hybrid's Meta-call median is
6.274 seconds. A model call covers up to eight bars; local timing is per bar.
Those units must not be presented as a like-for-like whole-file speed comparison.

The additional 42 synthetic scores scored **77.6% / 79.9% / 78.9%** for local /
Meta / hybrid, and 73.1% for Muse Spark Open. On one private real score, 37 eligible bars (74 slots) scored
**18.9% / 29.7% / 21.6%**, and Muse Spark Open 0.0%. That real-score row uses already-read notes too, with
estimated timing in most bars; it is not a whole-file vision accuracy score.
Only aggregates are public. The source score and private test corpus are not
redistributed.

The historical hybrid asked Meta only about empty local bars. The current API
`engine: "auto"` reviews inferred as well as unresolved harmony with whole-score
context. The editor's **Use Meta model** checkbox instead uses `verified`, which
reads the original file. Neither current path has been rerun in this benchmark.

Records: [full metrics and limitations](../experiments/harmony_eval/summary.md),
[local JSON](../experiments/harmony_eval/results-real-songs-local.json),
[Meta JSON](../experiments/harmony_eval/results-real-songs-meta.json),
[hybrid JSON](../experiments/harmony_eval/results-real-songs-auto.json),
[open-weight JSON](../experiments/harmony_eval/results-real-songs-openweight.json).
Implementation: [metrics](../backend/scripts/harmony_eval/metrics.py),
[Meta note interpretation](../backend/app/services/harmony_meta.py),
[current bounded assist](../backend/app/services/score_assistance.py).

## Import B: original PDF to a complete score

Five diagnostic PDFs test the complete reader: three author-created vector
fixtures, Mozart K.2 and Bach BWV 846 editions from Mutopia. The three fixtures
have seven bars with known chord answers and eight bars with known pitch-class
sets. The real editions have structural references, but no expert chord labels
for calculating real-song chord accuracy.

| Condition | Completed files | Fixture chord bars matched | Fixture note sets matched | Mean seconds per file | Cost across five inputs |
|---|---:|---:|---:|---:|---:|
| Local reader + optional F1 | 3/5 | 7/7 | 8/8 | 0.592 | $0 |
| Meta only | 3/5 | 6/7 | 4/8 | 26.203 | $0.10659 |
| Hybrid, one pass | **4/5** | 7/7 | 8/8 | 24.507 | $0.09157 |

The hybrid completed Mozart where local reading was unsupported and retained
local fixture evidence where Meta failed or differed. All methods failed to
complete Bach; Meta exhausted the experiment's 8,192-output-token allowance.
Including Bach's 35 reference note bars gives **8/43 / 4/43 / 8/43** matches,
which mixes coverage and reading failure and is not precision on returned notes.
Times include failures. With only five heterogeneous inputs and one run per
condition, these are diagnostic counts, not a general PDF success-rate estimate.

The second hybrid review completed only 3/5 files. Its $0.16519 includes the
shared first pass, so costs must not be added twice. The actual four-arm batch
used **14 calls / $0.27177955**. No failed case was selectively retried to improve
the table.

### Current Import behavior versus that experiment

For a supported PDF with resolved key and meter, the editor opens the local
reading first. With **Use Meta model** enabled, an independent full-file Meta
reading runs in the background. The editor flags disagreements and fills only
still-empty, untouched bars; it does not replace visible chords or intervening
user edits. Unaligned bar counts are reported instead of merged. Images need
Meta; an unsupported local PDF can use Meta directly through the verified path.

The current file reader allows one call, **150 seconds and 32,768 output tokens**,
with a default $1.50 request cap. It does not automatically retry. The historical
hybrid supplied the local reading to Meta; the current verified path compares
independent readings. The five-file table predates both that flow and the larger
output allowance, so it is not a measured success rate for the current checkbox.

The local path may use F1 to fill at most eight unresolved note-bearing bars in a
score of at most 128 bars, with known key and meter. These are low-confidence
inferred proposals, not recovered printed symbols. A successfully read local
score over the Meta bar limit opens locally. If Meta fails but local succeeds,
the interface explicitly reports **“Meta reading was unavailable. The local
reader recovered this score.”** Its provenance remains local.

Records: [four-reader comparison and sources](score-reader-comparison.md),
[responses, failures and usage](../experiments/external_eval/four-reader-results.json).
Implementation: [experiment](../agent/compare_score_readers.py),
[verified reader](../backend/app/services/score_verification.py),
[F1 completion](../backend/app/services/score_completion.py),
[editor merge rules](../frontend/src/engine/importReview.ts).

Dollar figures above are recorded API costs, not compute/hosting costs or future
price guarantees. Runtime dollar limits depend on deployment settings; explicit
unlimited mode bypasses dollar caps while time/call bounds, usage accounting and
the configured credit stop line remain active. See [deployment](../deploy/README.md).
