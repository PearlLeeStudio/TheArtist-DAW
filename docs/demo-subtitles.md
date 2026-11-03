# Hackathon demo subtitles

Subtitle edit plan for the existing [1:51 hackathon video](https://youtu.be/Xw3BwB64Jt0).
The [English SRT](demo-subtitles.en.srt) follows this nine-cue plan. Align cue
edges to the cuts in the editing project. The two listening passages intentionally
have no captions, leaving the viewer time to follow the harmony and the controls.

## What the story communicates

TheArtist connects score analysis, harmonic revision and accompaniment to reduce
preparation before a DAW session. The musician can reuse the extracted harmony
instead of entering it again, compare alternatives and continue with editable
Harmony, Bass and Drums tracks.

Melody editing and reproduction of the source melody as an editable track were
deliberately excluded from this workflow from the outset. The product focuses
on harmonic choices and accompaniment; melody writing and further production
remain with the musician in the DAW. This is an intentional scope choice, not an
unfinished melody feature. Respecting the source does not mean the tool grants
permission to arrange or redistribute protected material.

The opening distinguishes the existing Music Transformer from the Meta-powered
tools added for the hackathon. During Reharmonize, Muse Spark searches with tools
and the Music Transformer scores candidates against neighboring harmony. The
musician chooses and applies the changes.

## English captions and placement

`<br>` marks a line break. Times are cue placements within the existing edit.

| Time | Scene | Caption |
|---|---|---|
| 00:00–00:08 | Opening cover and file selection | This hackathon adds Meta-powered tools<br>on top of my existing Music Transformer. |
| 00:08–00:18 | Import and background check | Import a score as editable chords.<br>Meta starts a background check. |
| 00:18–00:23 | Harmonic workspace | Work on harmony without displaying<br>the original score. |
| 00:23–00:28 | Accompaniment controls | Choose instruments, rhythms and drums.<br>Hear the arrangement take shape. |
| 00:28–00:44 | Instrument and rhythm comparison | No captions; let the arrangement play. |
| 00:44–00:54 | Passage selection and search | Reharmonize up to four chords.<br>Compare three alternatives. |
| 00:54–01:07 | Tool search and context scoring | Muse Spark uses tools to search.<br>My model scores each in context. |
| 01:07–01:14 | Combine and Apply | Compare and combine the alternatives.<br>Apply the changes you want to keep. |
| 01:14–01:38 | Revised arrangement playback | No captions; let the revised arrangement play. |
| 01:38–01:47 | Export menu and Logic Pro tracks | Export Harmony, Bass and Drums.<br>Keep editing in your DAW. |
| 01:47–01:51.2 | Closing cover | Less setup.<br>More time to make your music. |

## Editing notes

- Replace the old burned-in captions in the editing project. Adding an SRT on
  top of the exported video will not remove those existing words.
- Keep captions to two lines, with one consistent size and high contrast. Avoid
  covering chord symbols, candidate cards or DAW tracks.
- Use the nine cues as scene-level explanations. The visible controls already
  show selection, Play and Apply, so they do not each need a separate instruction.
- Replace the old claim that Muse Spark has already read and checked every bar
  with the ongoing background-check wording above. The visible local-recovery
  message stays: **Meta reading was unavailable. The local reader recovered this
  score.** Reharmonize's separate Meta search is described in its own scene.
- Source respect is expressed through the harmonic scope and the original score
  staying off-screen. Do not turn this into a copyright guarantee or a claim that
  source melody is copied into the output.
- The application's source-discard policy was added after this recording. It is
  documented in the [README](../README.md) and
  [source-handling guide](score-analysis.md#source-handling-and-retention), rather
  than presented as a newly demonstrated action in this footage.
- The closing states the preparation-time benefit without an unmeasured numeric
  speedup or a claim of universal musical superiority.
