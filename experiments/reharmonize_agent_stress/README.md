# Expanded product-agent reliability protocol

This evaluation exercises the existing Reharmonize product agent with the same
F1 checkpoint, prompts, tool definitions, candidate generation and scorer. It
adds no product feature or runtime configuration change. Muse requests searches,
the tools construct bounded candidates and F1 scores their musical context, Muse
offers three alternatives, and the musician retains the final choice in the app.

## Frozen design

- 640 new authored passages: 80 in each of `auto`, `ionian`, `dorian`, `phrygian`,
  `lydian`, `mixolydian`, `aeolian` and `locrian`.
- Within each mode, major/minor key, simple/complex chords and change limits 1–4
  are fully crossed, with five cases per cell. Context length, meter, absolute
  measure offsets, empty unselected slots and selection shape also vary.
- Six scheduled repeats per new passage, per provider.
- 40 existing passages have ten scheduled repeats per provider: the earlier
  `g-minor-03` timeout and 39 other inputs chosen by request-hash order. This is
  explicitly post-hoc regression evidence, not new songs.
- Total schedule: **8,480 executions**, 4,240 each on Muse Spark Open/Baseten and
  Muse Spark 1.3/Meta Standard. The previous 880 executions remain separate.
- Estimated new accounting from previous observed costs: **$97.83**. Combined
  hard allocation **$120**: two Open workers at $20 each and two Meta workers at
  $40 each. These are separate services and billing accounts, not one shared
  provider credit balance. Invoice credits are not inferred from token usage.
- At most four evaluation processes, two per provider. Stop after 21 elapsed
  hours, before additional paid attempts, to leave time for reporting. Independent
  worker caps sum to $120; fresh batch caps come only from each worker's remaining
  allocation. Unknown usage retains its full reservation. No replacement runs.

[Inputs](inputs.json), [design and source hashes](design.json), and
[offline search-capacity inspection](preflight.json) are frozen before paid
execution. The input-only preparation in [preparation/](preparation/) is retained:
its initial change-limit assignment was coupled to key mode and complexity.
Before any paid output, the allocation was corrected to cross these factors;
chords, selections and case membership were not filtered by search outcomes.
Preparation files are not executed results.

The unchanged mathematical search has at least three distinct patches for
671/680 inputs. Nine explicit-mode cases have fewer. They stay in the complete
schedule and denominator. Capacity-conditioned results, if reported, are labeled
separately; an impossible three-choice offer does not become a model success.

## Measurements and limits

The original mechanical checks are retained, with an additional check that
every changed chord satisfies an explicitly requested mode. Report completion,
three unique musical alternatives, selected-region preservation, valid addresses
and before-values, change limits, input immutability, actual search feedback and
F1 scores, repeated-offer overlap, latency, requests, tokens, costs, retries and
all failures. Repeated runs are grouped by passage. Candidate agreement and F1
scores are descriptive measures, not listening preference or musical superiority.

These are authored engineering fixtures with related harmonic templates, not a
representative corpus of independent songs. Full requests can contain 512 bars;
the existing agent/scorer sees its unchanged context window of at most 24 bars.
Two concurrent evaluation processes per provider and uncontrolled provider cache
conditions limit timing comparisons. This is not a hosted throughput test.
Browser use, user application, MIDI export and DAW playback are outside this
campaign. Listening research is planned separately for a paper.

## Evidence handling

The [campaign runner](tools/campaign.py) imports the preserved first evaluator's
observation and audit helpers. Each batch retains complete requests, replies,
tool feedback, provider request IDs when returned, usage ledgers and errors.
Raw traces use JSON compressed with gzip with a zero header timestamp; accounting
ledgers remove work timestamps. No keys or model weights are published. Existing
evidence is never overwritten. No paid restart or failed-run replacement is
permitted by the runner.

The [offline tests](tools/test_campaign.py) cover schedule partitioning, crossed
input cells, the added mode check, budget isolation, cancellation and failures.
Use the installed backend Python environment and absolute paths; in the owner's
checkout use the approved `dev.sh py` wrapper with bytecode writes disabled.

Code remains MIT. The author's weights and training data remain CC BY-NC 4.0.
No claim is made about prize probability or combining awards.
