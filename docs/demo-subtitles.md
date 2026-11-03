# Hackathon demo subtitles

Subtitle edit plan for the existing [1:51 hackathon video](https://youtu.be/Xw3BwB64Jt0).
The [English SRT](demo-subtitles.en.srt) follows the same plan. Align cue edges to
the cuts in the editing project; the two listening passages intentionally have
no captions.

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
| 00:08–00:12 | Import | Import a score.<br>Start with an editable chord sketch. |
| 00:12–00:18 | Local opening and Meta check | Your chord sketch opens right away.<br>Meta starts a background check. |
| 00:18–00:23 | Harmonic workspace | Work on harmony without displaying<br>the original score. |
| 00:23–00:28 | Accompaniment controls | Choose instruments, rhythms and drums.<br>Hear the arrangement take shape. |
| 00:28–00:44 | Instrument and rhythm comparison | No captions; let the arrangement play. |
| 00:44–00:49 | Passage selection | Select the passage<br>you want to reharmonize. |
| 00:49–00:54 | Change limit and search | Change up to four chords.<br>Compare three alternatives. |
| 00:54–01:00 | Search in progress | Muse Spark uses tools to search<br>for harmonic alternatives. |
| 01:00–01:07 | Context scoring | My Music Transformer scores each<br>against the surrounding chords. |
| 01:07–01:14 | Combine and Apply | Compare and combine the alternatives.<br>Apply the changes you want to keep. |
| 01:14–01:19 | Revised passage | Hear your revised harmony<br>in the same arrangement. |
| 01:19–01:38 | Revised arrangement playback | No captions; let the revised arrangement play. |
| 01:38–01:42 | Export menu | Export a chord chart<br>or editable MIDI parts. |
| 01:42–01:47 | Logic Pro tracks | Continue with Harmony, Bass and Drums<br>in your own DAW. |
| 01:47–01:51.2 | Closing cover | Less setup.<br>More time to make your music. |

## Editing notes

- Replace the old burned-in captions in the editing project. Adding an SRT on
  top of the exported video will not remove those existing words.
- Keep captions to two lines, with one consistent size and high contrast. Avoid
  covering chord symbols, candidate cards or DAW tracks.
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
