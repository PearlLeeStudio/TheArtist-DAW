# Human listening comparisons

Open [planner comparison](blind.html) or [chorus comparison](chorus-blind.html)
in a browser. Each has three pairs, randomized A/B order per page load and
identical simple harmony/bass voices. Drums are omitted. These pages contain
no arm labels, tracking or upload destination. **No human responses have been
collected; no musical preference result is claimed.**

The planner pairs use the existing seed-1380 MIDI samples: new pop, new jazz
and A-minor hip-hop completion, with the same eight-bar sketch in the last pair.
The final first-ranked suggestions and slash bass are preserved. Their canonical
octave-4 voicings differ from the editor's interactive voicing choices; the
original MIDI filenames reveal planner names and should not be sent to blind listeners.
The chorus pairs
use seed 17 from the [OMT-on benchmark](../../../speed/chorus-memory.md).
The rendering is intentionally the same for both arms; it is not a test of
the application's sound library or a blinded comparison of every pipeline stage.

Ask independent musicians to listen with consistent headphones/volume and rate
flow, returning sections, ending and willingness to use each version. Collect
the downloaded JSON files privately. The playback-completion flags record only
whether audio ran to the end, not attention. Use at least three listeners for
an exploratory comparison and report the sample size and missing listens.
Do not treat several pairs from one listener as independent people.

For editing effort, separately give each musician the same original sketch and
target. Counterbalance workflow order, time the active work until they decide
the sketch is usable, count changed chord slots and retain their actual output.
Listening-page elapsed time is not a substitute for that task. No editing-time
or correction-count results exist yet.

The [pack builder](../../../../agent/listening_pack.py) creates the HTML and a
separate private answer key from `--midi-dir` or `--benchmark`. Keep the key away
from listeners. Use new absolute paths for `--out` and `--private-key`.
After collecting real responses, run:

```sh
uv run --directory /absolute/TheArtist-DAW/backend python /absolute/TheArtist-DAW/agent/listening_results.py --private-key /absolute/private/key.json --responses /absolute/private/person1.json /absolute/private/person2.json --out /absolute/private/summary.json
```

The collector rejects missing/out-of-range ratings, unknown clips, duplicated
participants and mismatched comparisons. Only aggregates should be considered
for publication, with participants' permission; comments and codes remain private.
