# Demo copy

## Creator

JinJu Lee · PearlLeeStudio

## Project

**TheArtist**

From score/chord editor to AI reharmonization agent.

## Timeline and English captions

The original timing is retained as a reference. [English SRT](demo-subtitles.en.srt)
matches this table; `<br>` marks a line break. The contribution and Baseten card copy
below can be included in the closing section when the final cut is assembled.

| Time | Scene | Caption |
|---|---|---|
| 00:00–00:04 | Creator and project | JinJu Lee · PearlLeeStudio<br>TheArtist |
| 00:04–00:08 | Project introduction | From score/chord editor<br>to AI reharmonization agent. |
| 00:08–00:18 | Import | Import a score PDF as editable chords.<br>The local reader opens it right away. |
| 00:18–00:23 | Imported harmony | The song keeps its length and sections,<br>so every chord is chosen inside the form. |
| 00:23–00:28 | Player UX | Redesigned player, refined playback UX.<br>Switch parts and set the mix. |
| 00:28–00:44 | Instrument and rhythm comparison | No captions; arrangement playback. |
| 00:44–00:54 | Passage selection and search | Reharmonize agent: up to four chords,<br>three alternatives to compare. |
| 00:54–01:00.5 | Tool search | Muse Spark decides what to search<br>and calls the search tools. |
| 01:00.5–01:07 | Context scoring | My model scores each change in context;<br>Muse Spark offers three that differ. |
| 01:07–01:14 | Run details: model, tool calls and request IDs | Live Meta calls: muse-spark-1.3,<br>request IDs, cost and time. |
| 01:14–01:21 | Combine and Apply | Compare and combine the alternatives.<br>Apply the changes you want to keep. |
| 01:21–01:45 | Revised arrangement playback | No captions; revised arrangement playback. |
| 01:45–01:54 | Score PDF export, then editable Harmony, Bass and Drums in Logic Pro | Export a score PDF, then open<br>editable MIDI tracks in Logic Pro. |
| 01:54–01:58.5 | Muse Spark comparison table | Why Muse Spark: reading chords from notes,<br>it matched 89.5%; my local analyzer 77.8%. |
| 01:58.5–02:02.7 | Closing cover | Less setup. More time to make your music.<br>artist-daw.pearlleestudio.co |

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

This benchmark predates the current Import workflow. [Evidence](../README.md#evidence).

## Meta open weights on Baseten

Second ear uses **Meta Muse Spark Open, served by Baseten**, to choose among chord candidates.

In the same 60 candidate reviews, Muse Spark Open on Baseten chose the same candidate
as Muse Spark 1.3 in **52 of 60** cases.
[Comparison results](../experiments/review_eval/summary.md).

Second ear's result identifies the actual provider and model:
`baseten meta-models/muse-spark-open-1026`, with a request ID and cost.

## Closing

Less setup. More time to make your music.

artist-daw.pearlleestudio.co

## Project context

TheArtist connects score analysis, harmonic revision and accompaniment to reduce
preparation before a DAW session. Reuse the extracted harmony, compare alternatives
and continue with editable Harmony, Bass and Drums tracks.

The workflow focuses on harmony and accompaniment. Melody writing and further
production remain with the musician in the DAW; the source melody is not exported
as an editable track.
