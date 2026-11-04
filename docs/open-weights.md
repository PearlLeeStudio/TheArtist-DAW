# Meta open weights in TheArtist

Meta open weights direct harmonic search inside the score-to-DAW workflow.
This page connects that role to a saved decision, the tools and own-model scores
it uses, the musician's final choice, and the separate reliability measurements.

## What runs on open weights

The product's LLM work is split into roles. The **judge role** and the **agent
role** run on Meta's open-weight **Muse Spark Open** (`meta-models/muse-spark-open-1026`),
served by Baseten at `https://inference.baseten.co/v1`. The hosted demo
([artist-daw.pearlleestudio.co](https://artist-daw.pearlleestudio.co)) has run
the judge this way since the evening of 2026-11-03 and the Reharmonize agent since
2026-11-04, and keeps both that way through the judging window.

| Feature | What the open-weight model decides | Code |
|---|---|---|
| **Second ear** (after Generate) | picks one of the A/B/C candidates on facts the analyzer computed (chords outside the key, repetition of the previous section, mean Sethares roughness, changed slots, rules-written slots); each reason is checked against the analyzer's value and marked *analyzer confirmed* or *model statement* | [review.py](../backend/app/services/review.py) |
| **Complete the form → Music Transformer + Meta review** | one observe-then-act judgment per pass over the generated sections, at most two passes, sending back at most two sections for regeneration | [planner.py](../backend/app/services/planner.py) |
| **Reharmonize** (agent role) | drives the substitution search: chooses which families to search, calls `search_substitutions` and `offer_candidates` as checked strict-JSON tool turns (at most 4 turns, 6 calls, 100 s), and offers three contrasting alternatives that the Music Transformer scored in context | [reharmonize_agent.py](../backend/app/services/reharmonize_agent.py) |

The other roles stay on Standard **Muse Spark 1.3** through the Meta Model API:
reading a score PDF or image, and planning and writing the song form. [Which model does what](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/main/README.md#hackathon-work-and-where-meta-is-used).

## Follow one recorded Reharmonize decision

The design assigns Meta the search and offer decisions, the author's Music
Transformer the contextual likelihood scores, and application code the bounded
candidate construction and validation. This supports the musician's task:
exploring sparse harmonic changes in an existing sketch before taking editable
accompaniment into a DAW. The musician retains the apply decision.

The example below is the **first saved execution** in
[`open-a/results.json`](../experiments/reharmonize_agent_eval/open-a/results.json),
`caseId: major-01`, `repeat: 1` (`runs[0]`). It was selected by file order to
illustrate the mechanism, not ranked by musical quality. The provider is Baseten,
and every reply identifies `meta-models/muse-spark-open-1026`.

Input: `C G | Am F | Dm G | C C`, C major, 4/4. The selected chords are `Am F`
in the second bar; each alternative may change at most one selected slot.

| Step | Recorded action | What can be checked |
|---|---|---|
| 1. Meta chooses the first searches | `search_substitutions({"families":["common_tones","modal"]})` | The reply's tool arguments specify the families; the following request contains their candidates and F1 scores |
| 2. Meta requests another family after receiving feedback | `search_substitutions({"families":["dominant"]})` | The next model request includes this additional search's feedback alongside the earlier candidates |
| 3. Meta selects the offer | `offer_candidates({"candidateIds":["3:A7","2:Am7","3:Dm7b5"]})` | All three complete candidate bodies match saved search feedback; each changes one selected slot |
| 4. Product hands the choice to the musician | Three alternatives are returned with `selection: "meta"`, model identity and three request IDs | The evaluator verifies the returned offer. Audition, Apply and MIDI export belong to the [product workflow](arrangement-workflow.md), outside this execution test |

| Offered edit | Search family | F1 context score | Score rank among the 16 unique candidate IDs in saved feedback |
|---|---|---:|---:|
| `F → A7` | Dominant | −2.58818 | 1 |
| `Am → Am7` | Common tones | −2.66389 | 2 |
| `F → Dm7b5` | Modal | −3.85039 | 10 |

The offer gives the musician one edit from each of three search families while
keeping the unselected harmony intact.

The observed offer differs from taking the top three F1 scores, which would have
included `F → Dm7`. This demonstrates a selection decision beyond a scalar sort;
it does not establish a better-sounding choice or an advantage over the current
local selector, which also uses family/root diversity. The saved feedback proves
the scores were supplied to Meta, not how much each score caused its decision.
F1 scores are conditional log likelihoods, not quality probabilities.

The run passed all saved execution and constraint checks in 10.666 seconds.
Returned usage gives a configured-price estimate of $0.01059180, not a reconciled
charge. The three request IDs and per-call usage are preserved in the source row.
The [paired report](../experiments/reharmonize_agent_eval/extended-summary.md#model-role-visible-in-the-saved-traces)
checks the same feedback-to-offer relationship across all 440 Open executions;
the example is not a substitute for those complete denominators and failures.

**What this establishes.** Meta performs inspectable search and offer decisions
inside the existing product, while the own model and deterministic tools provide
distinct services. Reliability runs test whether that division of work completes
under stated constraints. The [fixed-pool selector comparison](model-comparison.md#reharmonize-same-passages-three-selection-methods)
provides separate exploratory baseline evidence. Neither study establishes that
Meta is indispensable, superior to every current local selector, or preferred by
listeners. Listening research is planned separately for a paper.

## How to verify it

**On the screen.** Every judge result prints its provider, model, request id and
cost. With the judge on open weights, the result line of a Second ear review and
of each judgment in Complete the form reads

```text
baseten meta-models/muse-spark-open-1026 · <request id> · $<cost>
```

Under the Reharmonize cards the yellow box reads `Meta meta-models/muse-spark-open-1026
chose these alternatives` and **Run details** list every call with its request id and
cost; `Picked without Meta` names the reason when Meta could not take the request, and
a failed search says `Meta search failed` with the provider's status.

On the live app: choose a **Genre**, drag across a few bars, **Generate**, then
**Second ear**. The result line names the provider and model. For the agent, select
one to four chords and **Reharmonize**: the yellow box and Run details name the model. A failed call is
shown as a failure with the provider's status; it is never turned into a result
that looks like success.

**In the API.** The same fields are in the responses: `provider`, `model`,
`requestId` and `costUsd` on a review result, on every call of a plan trace
(`calls.*.provider`, `calls.*.model`, `calls.*.requestId`), and `metaModel`,
`requestIds`, `toolCalls`, `costUsd` and `selection` on a Reharmonize result.

**On the server.** The judge role has its own ledger (`THEARTIST_JUDGE_LEDGER`)
with one line per request: request id (Baseten's `x-baseten-request-id` header),
prompt and completion tokens, settled cost and latency. Its cap is
`THEARTIST_JUDGE_BUDGET_USD` (default $10), separate from the Muse Spark ledger.
The agent role has the same: `THEARTIST_AGENT_LEDGER` and `THEARTIST_AGENT_BUDGET_USD`.

**How it is switched.** Four lines in the server environment move the judge role
to open weights and five move the agent; nothing else changes and no code is rebuilt
([runtime settings](../deploy/env.example)):

```bash
LLM_JUDGE_PROVIDER=baseten            # base URL and model default to Baseten's
LLM_JUDGE_API_KEY=...                 # Baseten API key, server side only
LLM_JUDGE_REASONING_EFFORT=low        # the setting the comparison used
THEARTIST_JUDGE_BUDGET_USD=10         # the judge's own cap
LLM_AGENT_PROVIDER=baseten            # the Reharmonize agent role
LLM_AGENT_API_KEY=...
LLM_AGENT_REASONING_EFFORT=low
THEARTIST_AGENT_BUDGET_USD=10         # the agent's own cap
THEARTIST_AGENT_LEDGER=/data/agent_ledger.json
```

Leaving `LLM_JUDGE_PROVIDER` or `LLM_AGENT_PROVIDER` empty makes that role the
default Muse Spark client.
The client is the same OpenAI-compatible transport for both providers
([llm.py](../backend/app/services/llm.py)); Baseten's list price for Muse Spark Open
is built in, so the worst-case cost reservation and the ledger work the same way.
Because an open-weight endpoint does not enforce the JSON schema server-side, a
reply that fails the schema gets one guarded retry, and the reservation for a
judge call on open weights is doubled to cover it ([review.py](../backend/app/services/review.py)).

**First hosted review on open weights** (2026-11-03): request
`54ca701a1a106f7d176838a17f443fb7df547`, $0.0045, 5.4 s, both reasons confirmed by
the analyzer ([record](../HACKATHON.md), row 127).

**First hosted Reharmonize searches on open weights** (2026-11-04): the README's
Amazing Grace bars 5–8 request, three times in a row right after the switch. Each
search completed `search_substitutions → search_substitutions → offer_candidates`
with three candidates (G7 / D7♭9 / A♭7♯11; G7 / Gmaj7 / D7♭9; G7 / D7♭9 / A♭7♯11),
at $0.0121, $0.0096 and $0.0048 and 11.5, 9.3 and 7.7 s, every request id recorded
([record](../experiments/meta/reharmonize_open_weights_live.json)).

## How it was measured

**Expanded mode and constraint coverage: all 8,480 scheduled rows started.** The
[frozen protocol](../experiments/reharmonize_agent_stress/README.md) exercises the
same product agent and real F1 checkpoint across 640 new authored inputs and 40
existing regression inputs. Requested mode, key mode, chord complexity and change
limit form 128 planned condition cells. Repeated executions are not new songs.

| Expanded execution measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |
|---|---:|---:|
| Passed / started | **4,186 / 4,240** | **4,144 / 4,240** |
| Failed / operator-cancelled | 54 / 0 | 95 / 1 |
| Planned but not started | 0 | 0 |
| Inputs passing every scheduled repeat | 671 / 680 | 635 / 680 |
| Offered candidates matching tool feedback, with finite F1 scores | 12,558 / 12,558 | 12,432 / 12,432 |
| HTTP attempts / extra attempts within tool turns | 12,504 / 10 | 12,779 / 0 |
| p50 / p95 seconds, all started runs | 5.259 / 8.239 | 15.553 / 26.903 |
| Configured-price estimate from returned usage | $28.04348590 | $52.30077735 |
| Unknown-usage reservation | $0 | $0.91077275 |
| Total nominal accounting | $28.04348590 | $53.21155010 |

Both providers retain 54 failures: six repeats of each of nine inputs whose
candidate shortage was detected before paid execution. Spark 1.3 additionally
records 27 timeouts, 13 tool-call response failures, one HTTP 503 and one original
operator cancellation. Every passing run completed the offer with three distinct
applied versions while preserving unselected chords and respecting change limits.
Both providers reached all 128 cells with at least two distinct inputs each started
at least twice; all 40 regression inputs also completed their repeat schedules.

The operator initially stopped Spark after 1,716 executions during a scope review.
After the participant explicitly requested completion, only the original 2,524
unstarted rows were continued. All prior outcomes, including 42 failures and one
cancellation, remain unchanged; no failed or cancelled run was replaced. The
[partial report](../experiments/reharmonize_agent_stress/summary.md) and stop record
remain available. This was a post-hoc stop and continuation, not a preregistered
statistical rule. The final paired set contains all 4,240 case/repeat rows per arm.

Combined nominal accounting is **$81.25503600**, including the unknown-usage
reservation. This is not a paid invoice or measured credit deduction. The
[completion report](../experiments/reharmonize_agent_stress/completion-summary.md) and
[numeric evidence](../experiments/reharmonize_agent_stress/completion-summary.json) retain raw
requests, tool feedback, responses, IDs, usage, retries and failures. Product code,
UX, prompts, search, scoring, candidate generation and runtime settings are unchanged.
The study stops at the returned offer and does not test browser interaction,
application, MIDI export or DAW playback. Related authored templates, repeat
dependence and provider/cache differences limit generalization. The temporal break
and smaller continuation accounting batches can affect timing and cache behavior;
this is not an isolated model-capability or musical-quality ranking. Listening research
is planned separately for a paper.

The studies below retain their separate tasks, inputs and denominators. Provider
request IDs and usage are kept where returned; missing values after a timeout
remain explicitly unknown.

**Reharmonize product agent, 440 executions per model**
([paired report](../experiments/reharmonize_agent_eval/extended-summary.md),
[full evidence](../experiments/reharmonize_agent_eval/extended-summary.json),
[protocol and tools](../experiments/reharmonize_agent_eval/README.md)):
220 authored passages, two repeats per provider, using the same unchanged agent,
real F1 checkpoint and constraints. Meta chooses which searches to request, the
search tools construct bounded candidates and F1 scores them in context, and Meta
selects the final three through `offer_candidates`. The musician chooses what to
apply in the product; this evaluation stops at the agent's returned offer.

| Product-agent measurement | Muse Spark Open / Baseten | Muse Spark 1.3 / Meta Standard |
|---|---:|---:|
| All execution and constraint checks passed | **440/440** | **439/440** |
| Passages passing both repeats | 220/220 | 219/220 |
| Offered candidates matching saved search feedback, with F1 scores | 1,320/1,320 | 1,317/1,317 |
| HTTP attempts / retries | 1,294 / 0 | 1,319 / 0 |
| p50 / p95 seconds | 5.423 / 8.724 | 17.609 / 30.449 |
| Returned-usage cost | $3.41593040 | $6.70197475 |
| Unknown-usage reservation | $0 | $0.03380800 |

The one failure is a Spark 1.3 API timeout before the final offer. It remains in
all scheduled-run denominators; there was no replacement paid run. Checks cover
three distinct applied chord versions, valid addresses and original values,
selection preservation, change limits and input immutability. The model's 1,320
Open proposals all match actual search feedback with finite F1 scores.

These are **in-process product-agent executions**, not browser or DAW trials,
listener preferences, or an isolated model-capability comparison. The two
existing provider adapters and cache conditions differ. The authored fixtures
use related harmonic templates; repeats are not independent songs. Full requests
reach 512 bars, while the unchanged agent/scorer context remains at most 24 bars.
The earlier hosted evidence remains three repeats of one Amazing Grace passage.
The separate 60 Second-ear reviews below are not pooled into this completion rate.

**Second ear, 60 reviews per model** ([report](../experiments/review_eval/summary.md),
[open-weight results](../experiments/review_eval/results-openweight.json),
[Muse Spark results](../experiments/review_eval/results-meta.json)): 20 A/B/C lists
from a planner run, each shown in its three cyclic orders.

| | Muse Spark 1.3 | Muse Spark Open on Baseten |
|---|---:|---:|
| Completed reviews, valid JSON, no retry | 60/60 | 60/60 |
| Reasons that cite an analyzer value at the analyzer's value | 115/115 | 112/112 |
| Most in-key candidate picked in genres that stay in key | 33/36 | 33/36 |
| Same candidate in all three orders | 17/20 | 16/20 |
| Same pick as Muse Spark | — | **52/60** |
| Cost per review · p50 latency | $0.0041 · 2.8 s | **$0.0028 · 2.1 s** |

**Reading chords from notes, 640 slots** ([report](../experiments/harmony_eval/summary.md),
[open-weight results](../experiments/harmony_eval/results-real-songs-openweight.json)):
40 real progressions in 13 genres rendered as notes in six voicing variants, the
same task the product's note interpretation uses.

| | Local analyzer | Muse Spark 1.3 | Muse Spark Open (effort high) |
|---|---:|---:|---:|
| Exact where answered | 95.4% | 89.5% | **89.4%** |
| Coverage | 81.6% | 100% | 82.5% |
| Exact over all 640 slots | 77.8% | **89.5%** | 73.8% |
| Calls · failed | 0 | 40 · 0 | 40 · 7 (4 length limit, 3 harmony validation) |
| p50 per call · total cost | — | 5.1 s · $0.34 | 8.0 s · $0.63 |

Where Muse Spark Open answered, it was as exact as Muse Spark; the lost calls put
its overall agreement below the local analyzer. That is why the product ships
reading and planning on Muse Spark 1.3 and the judge on open weights: the judge is
the role where the open weights matched the hosted model's choices at lower cost
and latency. The Reharmonize agent joined it on the hosted demo on 2026-11-04 after
the three recorded searches above; its blinded comparison was run on Muse Spark 1.3.

## What does not run on open weights

- **The blinded fixed-pool Reharmonize selector comparison.** The agent is its own client role (`LLM_AGENT_*`):
  off Meta Standard the two tools are stated in the system message and each turn is
  one checked strict-JSON call, and the hosted demo runs it on Muse Spark Open
  (above). The blinded selector comparison, however, was run with the agent on Muse
  Spark 1.3; `agent/compare_reharmonization.py --selector-provider baseten` runs it
  on open weights with the blinded judge still on Muse Spark, and no such number is
  claimed for that fixed-pool study. The 880-run product-agent reliability
  comparison above is a separate measured experiment. Run details name the model
  either way.
- **Score reading.** The whole-file PDF/image reading uses the Meta Model API.
- **Listening quality.** No listening study was run; "same pick" and
  "reasons confirmed" are agreement and consistency measures, not preference.

If Baseten is unavailable during judging, Second ear, the hybrid form review and
Reharmonize show that failure with the provider's status; Generate, Import and
Muse Spark only continue on Muse Spark 1.3.
