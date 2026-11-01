# Evaluation evidence

Numbers behind the product's claims, with their conditions and what they do not
show. The [README](../README.md#evidence) keeps a shorter table.

## Recorded evaluations

Each row is a recorded run whose calls, costs and failures are kept in the
linked file. Automatic judge scores and reconstruction agreement are component
evidence, not listener preference, and no row is a listening study.

| Evaluation | Material | Result | Record |
|---|---|---|---|
| Reharmonization selectors: F4 / Meta only / one-pass hybrid / two-pass hybrid | JAZZVAR, 40 passages in 16 tune groups; 200 Meta calls, $2.465, no failure in the main run | Blinded automatic judge (Muse Spark, the same model family as the Meta selector) means 2.464 / 2.671 / 2.624 / 2.649 on a 4-point scale; no clear winner among Meta and the hybrids; the second pass changes the candidate set in 5/40 passages at about twice the time and cost | [protocol](../experiments/reharmonization/README.md), [results](../experiments/reharmonization/results.md) |
| F2 vs F3 checkpoints in the same four selectors | Same 40 passages, 200 successful calls per model | The first-two-candidate F2−F3 difference includes 0 in all four methods; each method's top-2 union keeps the all-twelve best in 35/40; deduplicating all top-3 lists leaves at most 8 versions per passage | [Korean synthesis](reharmonization-evaluation.md), [paired ranks](../experiments/reharmonization/f2-f3-rank-results.md) |
| Full-form planner with fixed seeds, Muse plan + F1 vs template | 20 requests × 3 seeds = 60 pairs; 152 calls, $1.02 | Structure and length pass 60/60 on both sides; section-type variety 2.75 → 3.48; out-of-key slots in diatonic genres 19.4% → 14.7%; rule-corrected slots 22.4% → 19.8%; the final judge still asked for regeneration in 21/60 | [comparison](../experiments/agent_eval/fixed-seed/comparison.md) |
| Second ear: a judge picks one of A/B/C | 20 candidate lists from the planner run, each in 3 orders: 60 reviews per judge; Muse Spark $0.244, Muse Spark Open on Baseten $0.168 | Reasons confirmed by the analyzer 115/115 (Muse Spark) and 112/112 (Muse Spark Open); in genres that stay in key both picked the most in-key candidate in 33/36 reviews (R1 pick 67%); same pick in all three orders 17/20 and 16/20; Muse Spark Open agreed with Muse Spark in 52/60 at $0.0028 vs $0.0041 per review (p50 2.1 s vs 2.8 s) | [Second-ear evaluation](../experiments/review_eval/summary.md) |
| Chord reading from notes: local analyzer / Muse Spark / local-then-Meta / Muse Spark Open | 40 eight-bar excerpts of real progressions (private test split, aggregates only) realized as notes in six voicing variants, 640 slots; 42 synthetic scores; one real score PDF; Muse Spark 40 calls, $0.338 | Exact on real songs: local 77.8%, Muse Spark 89.5% (coverage 100% vs 81.6%), local-then-Meta 83.9% for $0.050 in 6 calls, Muse Spark Open 73.8%; local is more precise where it answers (95.4% vs 89.5%) but reads no rootless voicing (0% vs 47.3%). Synthetic 77.6 / 79.9 / 78.9%; the real PDF 18.9 / 29.7 / 21.6%. Local-then-Meta is the earlier unresolved-only assist rule; the current whole-context assist is not part of this run | [harmony evaluation](../experiments/harmony_eval/summary.md) |
| Score readers: local / Meta / hybrid ×1 / hybrid ×2 | 5 PDFs; 14 calls, $0.272 | Completed readings 3/5, 3/5, 4/5, 3/5; the second pass is not always better; Bach hit the output-token limit | [four-reader comparison](score-reader-comparison.md) |
| Import on the author's fixtures | A 20-bar vector score; a notes-only PNG; 8 calls, $0.047 | 20/20 chords (16 Meta-reviewed, 4 local) and 8/8/4-bar sections; the PNG matched 1/4 chords and reported wrong note evidence with high confidence | [import evaluation](../experiments/import_eval/README.md) |
| Import on published editions | 8 Mutopia PDFs (7 works); 3 Meta readings, $0.076 | Local reader 0/8; Meta matched bar count, key and meter for Bach, Mozart and Schumann, but Bach bars 1–32 pitch sets matched 8/32 (Jaccard 48.93%) | [external evaluation](../experiments/external_eval/README.md) |
| Mozart continuation (DCML annotations) | 12 movements, first 4 bars → next 4, seeds 17–19; 36 F1 requests, 108 candidates | First-candidate pitch-set match 13.54%, below hold-last 27.08% and tonic 46.88% | [external evaluation](../experiments/external_eval/README.md) |
| Own-model speed with the attention cache | CPU, 4 threads; F1 / F4 / Rock LoRA at 8, 32 and 64 bars; 30 seed-matched pairs | Identical outputs and provenance; 1.73–3.89× faster; F1 64 bars 7.18 → 1.85 s; 32-bar template Song Form 2.39 → 0.99 s | [runtime performance](../experiments/speed/runtime-performance.md) |
| Model loading and hosted Reharmonize | Three-model local load; hosted Reharmonize, three requests per version | Loading 0.471 → 0.080 s with identical logits; hosted median 13.828 → 10.358 s | [runtime performance](../experiments/speed/runtime-performance.md) |
| Returning-chorus reuse | 64 bars, 3 conditions × 5 seeds, OMT on | p50 2.276–2.303 s → 1.680–1.698 s (about 25–27% less); the reused chorus slots match exactly | [chorus memory](../experiments/speed/chorus-memory.md) |
| Local PDF reading cache | 24-page, 465-bar PDF, 5 repetitions | First reading and harmony analysis median 1.565 → 1.485 s; cached reuse 0.159 s; parsing and analysis identical | [runtime performance](../experiments/speed/runtime-performance.md) |

Not measured: listener preference, composer editing time, or end-to-end latency
with the default OMT retrieval on. [Evaluation framing](evaluation.md) explains
which question each number answers.

## Score reading and import records

The [local analysis implementation](score-analysis.md) separates PDF glyph
reading from duration/bass/voice-aware chord and Roman-numeral analysis. Original
[treble](../experiments/local/vector-score-c.json) and
[bass](../experiments/local/vector-score-f.json) PDF fixtures exercise the complete
local path without an API call. Font encodings, unclear rhythm, octave markings
and ambiguous harmony still require review. Earlier direct-vision
[Meta trials](../experiments/meta/note_harmony_first_attempt.json) contain pitch errors;
they are retained as failures, not an accuracy claim.

The [real Meta smoke record](../experiments/meta/score_import_smoke.json) matched all
eight symbols and both explicit sections in an original four-bar PNG fixture:
5.62 seconds, $0.007285. It is one simple example, not a score-recognition benchmark.
Meta import errors stay visible and each call has a timeout, cost reservation and
usage/request-ID record. Set `MODEL_API_KEY` on the backend for this feature.
The [whole-score Import evaluation](../experiments/import_eval/README.md) includes
both successes and failures: the twenty-bar vector case retained 20/20 correct
chords (sixteen Meta-reviewed, four local) and inferred 8/8/4-bar neutral sections;
the notes-only PNG matched only 1/4 chords. These fixtures are not an accuracy benchmark.

The [external-score evaluation](../experiments/external_eval/README.md) adds eight
published Mutopia editions: **0/8 supported by the local reader**. Three explicit
Meta readings matched bar count/key/meter, but Bach note-evidence sets matched only
8/32 bars. A separate twelve-movement Mozart continuation comparison found F1
candidate A pitch-set agreement of 13.54%, below hold-last (27.08%) and tonic
(46.88%) baselines. Reconstruction agreement is not listener preference; these
results do not establish musical superiority or general score-reading accuracy.
