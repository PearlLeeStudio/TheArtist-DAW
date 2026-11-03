# Hackathon demo subtitles

Subtitle plan for the [hackathon video](https://youtu.be/Xw3BwB64Jt0), re-cut from the
existing 1:51 recording. The [English SRT](demo-subtitles.en.srt) follows this thirteen-cue
plan. Align cue edges to the cuts in the editing project. The two listening passages
intentionally have no captions, leaving the viewer time to follow the harmony and the
controls.

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

Every feature the video demonstrates was built during the event: Import, the Play
panel with its mixer and corrected playback timing, Reharmonize and the DAW export to
Logic Pro ([HACKATHON.md](../HACKATHON.md)). What existed before is named once, on the
opening card: the score editor, the sound, rhythm and drum-pattern content that the
Play panel plays, and the Music Transformer. The same card says once that everything
shown next was built this week, so later captions name the feature without a "new"
label. During Reharmonize, Muse Spark searches with tools and the Music
Transformer scores candidates against neighboring harmony; Run details then show the
live Meta calls. The musician chooses and applies the changes.

## English captions and placement

`<br>` marks a line break. Times are placements in the re-cut, which is 2:02.7 long:
the existing 1:51.2 edit plus a 7 s Run details insert after the search and a 4.5 s
result card before the closing. If the cut differs, shift the later cues by the same
amount.

| Time | Scene | Caption |
|---|---|---|
| 00:00–00:04 | Opening | Before this week: my score editor,<br>its sounds and rhythms, my chord model. |
| 00:04–00:08 | Opening | New this week: everything shown next.<br>Muse Spark drives the Reharmonize agent. |
| 00:08–00:18 | Import | Import a score PDF as editable chords.<br>The local reader opens it right away. |
| 00:18–00:23 | Background Meta check completed | Muse Spark finishes its background check.<br>A confirmation appears above the score. |
| 00:23–00:28 | Play panel | Play panel: switch parts, set the mix.<br>Hear the arrangement take shape. |
| 00:28–00:44 | Instrument and rhythm comparison | No captions; let the arrangement play. |
| 00:44–00:54 | Passage selection and search | Reharmonize agent: up to four chords,<br>three alternatives to compare. |
| 00:54–01:00.5 | Tool search | Muse Spark decides what to search<br>and calls the search tools. |
| 01:00.5–01:07 | Context scoring | My existing model scores each change;<br>Muse Spark offers three that differ. |
| 01:07–01:14 | Run details (new insert) | Live Meta calls: muse-spark-1.3,<br>request ids, cost and time. |
| 01:14–01:21 | Combine and Apply | Compare and combine the alternatives.<br>Apply the changes you want to keep. |
| 01:21–01:45 | Revised arrangement playback | No captions; let the revised arrangement play. |
| 01:45–01:54 | Export menu and Logic Pro tracks | DAW export: Harmony, Bass and Drums<br>open in Logic Pro as editable MIDI. |
| 01:54–01:58.5 | Result card (new insert) | Why Muse Spark: reading chords from notes,<br>it matched 89.5%; my local analyzer 77.8%. |
| 01:58.5–02:02.7 | Closing cover | Less setup. More time to make your music.<br>artist-daw.pearlleestudio.co |

## Editing notes

- Replace the old burned-in captions in the editing project. Adding an SRT on
  top of the exported video will not remove those existing words.
- Keep captions to two lines, with one consistent size and high contrast. Avoid
  covering chord symbols, candidate cards or DAW tracks. Every line is at most 42
  characters, so a caption never wraps past two lines on screen. The opening card and
  the 13 s search scene are split into two cues each to stay within that limit.
- Use the cues as scene-level explanations. The visible controls already show
  selection, Play and Apply, so they do not each need a separate instruction.
- **Import scene.** During the recording the Meta read failed, so the footage shows the
  app's notice **Meta reading was unavailable. The local reader recovered this score.**
  The notice stays in the product (a failed Meta call is reported, never hidden behind a
  fallback that looks like success), but it does not belong in the demo. Either cover or
  cut those frames in the edit and keep the caption as written (the local reader does
  open the score first), or re-record the 10 s Import scene with Use Meta model on and
  Meta working, cut the wait, and change the second caption line to
  `Muse Spark checks the reading bar by bar.`
- **Play panel scene.** The panel, its part switches, the four faders and the timing
  fixes are event work (HACKATHON.md rows 6, 8, 13 and 24–26). The 31 sounds, the
  genre comping rhythms and the drum patterns it plays existed before; the opening
  card names them. The timing fixes are not visible on screen, so the caption does
  not claim them.
- **Run details insert (optional).** One short screen capture, not a new take of the
  demo: run one Reharmonize on the live site, expand Run details while the three cards
  are open and zoom until the model ID and a request id can be read. The cost and time
  are the values on screen, not values from this plan. Without the insert, delete its
  cue and move every later cue 7 s earlier.
- **Result card.** One measured reason for Muse Spark, shown over the last Logic
  frame, dimmed. It comes from the 640-slot notes-to-chords comparison in the README
  Evidence, which predates the current Import flow, so the card sits apart from the
  Import scene and does not describe the Import checkbox. No other numbers are shown.
- Source respect is expressed through the harmonic scope and the original score
  staying off-screen. Do not turn this into a copyright guarantee or a claim that
  source melody is copied into the output.
- The application's source-discard policy was added after this recording. It is
  documented in the [README](../README.md) and
  [source-handling guide](score-analysis.md#source-handling-and-retention), rather
  than presented as a newly demonstrated action in this footage.
- The closing states the preparation-time benefit without an unmeasured numeric
  speedup or a claim of universal musical superiority.
