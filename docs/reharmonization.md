# Contextual chord alternatives

Select existing chords in the score, open **Input → Generate → Reharmonize**, and
choose **Find 3 alternatives**. Each candidate changes at most one chord by default;
the optional limit permits two. Empty slots and unselected chords stay untouched.
Genre is not a search objective, and changing the checkpoint in Reharmonize does
not change the song's genre or playback arrangement.

The Original/A/B/C comparison appears between the selected passage and the next
measure. Click A, B, or C to put that version directly on the staff, then use the
existing Play controls. The three choices remain visible across candidate changes,
Original restoration, and navigation to the Play panel. Every preview starts from
the captured original, so A's changes never leak into B. **Keep current & close**
closes the comparison and retains the version on the score. This comparison is an
editor session, not a saved-project version history; reloading the page clears it.

## How candidates are made

1. Muse Spark invokes native `search_substitutions` function tools for at least two
   harmonic families: shared tones, parallel-mode color, or dominant approaches.
2. A bounded deterministic search enumerates sparse patches inside the selection.
   It prunes using shared pitch classes, a symmetric nearest-pitch-class distance
   across neighboring chords, circular bass motion, and parallel scale membership.
   An explicitly selected mode constrains every proposed chord to that scale.
3. The selected Music Transformer scores the shortlists in written order, retaining
   up to eight preceding and eight following measures. Its score includes target
   chords and known later chords. This is causal sequence reranking, not a new
   bidirectional infilling model or explicit modal conditioning. Slash bass is
   evaluated mathematically; the trained tokenizer has no bass tokens.
4. Meta compares returned facts, can explore the remaining family, and calls
   `offer_candidates` with three distinct IDs. It cannot invent an output chord,
   change the score, or call arbitrary functions. The frontend applies the chosen
   sparse patch only after the composer's click.

Pitch-class distance is a heuristic, not measured voice leading or listening
quality. Mode labels describe compatibility with parallel scales of the stated
tonic, not detected modes. The input is chord-symbol context; no melody validation
or audio listening is claimed. Unsupported chord qualities fail explicitly rather
than silently dropping tensions. Original chord objects and voicings are retained.

## API and limits

`POST /api/reharmonize` accepts `key`, `timeSignature`, consecutive `context` bars
with two chord slots, `selectedSlots`, `modelKey`, `maxChanges` (1 or 2), and `mode`
(`auto` or one of the seven diatonic modes). A selection may span eight measures
and contain sixteen occupied slots; input context is limited to 256 measures.

The response contains three `candidates` with address/before/after patches and
computed metrics, `modelUsed`, `contextMeasures`, `metaModel`, `requestIds`,
`costUsd`, and `toolCalls`. Scores are ranking signals, not quality probabilities.
Selection and context edits during a request invalidate its result. Later edits
block stale candidate application; Original may still restore an untouched target
range without removing edits outside it.

Only Meta Standard `muse-spark-1.3` is used. Native calls follow the
[Meta function-calling protocol](https://dev.meta.ai/docs/cookbook/tool-function-calling),
including `tool_choice: auto` and paired assistant/tool messages. Each search is
bounded by four API turns, six function calls, three distinct family searches,
six shortlisted candidates per family, a 30-second per-call timeout, a 100-second
loop deadline, 1,600 output tokens per call, and a $0.15 request reservation cap.
The existing persistent ledger records request IDs, tokens and costs, including
failures; public session and daily limits also apply. Missing models, invalid tool
output, timeout, and budget exhaustion return errors with no success fallback.

## Evidence

The [synthetic progression record](../experiments/meta/reharmonize_smoke.json)
uses a self-authored three-bar sequence with F4 and actual Meta responses. Three API
requests executed three family searches and a final candidate choice, costing
$0.021142. The alternatives each change one selected slot. This demonstrates the
tool/model integration on one fixture; it is not a listening study.

Tests cover sparse bounds, both neighboring chords, modes, tensions and slash
basses, validated native calls, spending on failures, persistent A/B/C transitions,
exact Original restoration, stale edits, and the actual staff/comparison markup.
Browser interaction and audible playback of the complete comparison remain manual
checks; automated transition tests do not establish audio quality.
