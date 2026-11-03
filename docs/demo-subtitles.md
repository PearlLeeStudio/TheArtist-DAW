# Demo copy

## Creator

JinJu Lee · PearlLeeStudio

## Project

**TheArtist**

From score/chord editor to AI reharmonization agent.

## Demo captions

### Import

Import a score PDF as editable chords.

The local reader opens it right away.

Muse Spark finishes its background check. A confirmation appears above the score.

The imported song keeps its length and sections while you revise its harmony.

### Player

Redesigned the player UX: switch parts, set the mix and hear the arrangement take shape.

### Reharmonize

Reharmonize up to four chords, with three alternatives to compare.

Muse Spark decides what to search and calls the search tools.

My Music Transformer scores each change against the surrounding harmony;
Muse Spark offers three contrasting alternatives.

Run details show muse-spark-1.3, its tool calls, request IDs, cost and time.

Compare and combine the alternatives. Apply the changes you want to keep.

### Score PDF export

Let's check the chord chart. Export the harmonic score as a PDF.

### Logic Pro export

Open Harmony, Bass and Drums in Logic Pro as editable MIDI.

Unleash your creativity in your DAW.

## Built for this hackathon

- **Muse Spark 1.3** — Score reading, song-form planning and tool-driven reharmonization.
- **Muse Spark Open on Baseten** — Second ear candidate selection and hybrid song-form review.
- **Workflow** — Score import, redesigned player UX, score PDF export and Logic Pro handoff.
- **Infrastructure** — Hosted model inference, web deployment and the Safari–Logic bridge.

Built on my existing score editor, Music Transformer, sounds and rhythm patterns.
[Hackathon contributions](../HACKATHON.md).

## Why Muse Spark

Notes → chords · 640 reference slots

| Model | Exact chord match |
|---|---:|
| My local analyzer | 77.8% |
| **Meta Muse Spark** | **89.5%** |

**11.7 percentage points higher exact agreement.**

This benchmark predates the current Import workflow. [Evidence](https://github.com/PearlLeeStudio/TheArtist-DAW/blob/6ed1b50914c78c205ee7aabdde924c648caf292d/README.md#evidence).

## Meta open weights on Baseten

Second ear uses **Meta Muse Spark Open, served by Baseten**, to choose among chord candidates.

In the same 60 candidate reviews, Muse Spark Open on Baseten chose the same candidate
as Muse Spark 1.3 in **52 of 60** cases.
[Comparison results](../experiments/review_eval/summary.md).

Second ear's result identifies the actual provider and model:
`baseten meta-models/muse-spark-open-1026`, with a request ID and cost.

## Closing

Less setup. More time to make your music.

Put the app, GitHub and model links in the video description.

## Project context

TheArtist connects score analysis, harmonic revision and accompaniment to reduce
preparation before a DAW session. Reuse the extracted harmony, compare alternatives
and continue with editable Harmony, Bass and Drums tracks.

The workflow focuses on harmony and accompaniment. Melody writing and further
production remain with the musician in the DAW; the source melody is not exported
as an editable track.
