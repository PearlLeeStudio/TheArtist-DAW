# Demo copy

## Creator

JinJu Lee · PearlLeeStudio

## Project

**TheArtist**

From score/chord editor to AI reharmonization agent.

## Demo captions

### Import

Import a score PDF as editable chords.

The song keeps its length and sections, so every chord is chosen inside the form.

### Player

Redesigned the player and refined the playback experience.

### Reharmonize

Reharmonize up to four chords, with three alternatives to compare.

Muse Spark decides what to search and calls the search tools.

My Music Transformer scores each change; Muse Spark offers three alternatives.

Run details show the Meta model, tool calls, request IDs, cost and time.

Compare and combine the alternatives. Apply the changes you want to keep.

### Score PDF export

Export the harmonic score as a PDF.

### Logic Pro export

Open Harmony, Bass and Drums in Logic Pro as editable MIDI.

## Built for this hackathon

- **Muse Spark 1.3** — Score reading, song-form planning and tool-driven reharmonization.
- **Muse Spark Open on Baseten** — Candidate review.
- **Workflow** — Score import, redesigned player UX, score PDF export and Logic Pro handoff.
- **Infrastructure** — Hosted model inference, web deployment and the Safari–Logic bridge.

## Model evidence

On a 640-slot notes-to-chords benchmark, Muse Spark matched 89.5% of the reference
chords; my local analyzer matched 77.8%.

This benchmark predates the current Import workflow. [Evidence](../README.md#evidence).

## Closing

Less setup. More time to make your music.

artist-daw.pearlleestudio.co
