# TheArtist Chords — Logic Pro Scripter plugin

A DAW-side client of the shared music service: the editor's arrangement
(voicings, comping rhythm, swing, bass line, mixer-independent) exported as a
[Scripter](https://support.apple.com/guide/logicpro/use-the-scripter-plug-in-lgcecc16550/mac)
MIDI FX script that plays inside Logic Pro and follows Logic's transport.
It is generated from the same `ExportSpec` and note placement as the MIDI
export (`backend/app/services/smf_export.py`), so what Logic plays is what
Play and the `.mid` file play.

## Use it

1. In the editor, **Export ▸ Logic Scripter script** (or `POST /api/export/scripter`
   with an `ExportSpec`). You get `<title>.theartist.js`.
2. In Logic Pro, on a software-instrument track: **MIDI FX ▸ Scripter ▸ Open Script
   in Editor**, replace the editor's text with the file, press **Run Script**, then
   close the editor. Save it as a Scripter preset if you want to reuse it.
3. Press Play. The chords start at **Start bar** (default bar 1) and stop with the
   transport; locating and cycling retrigger correctly; notes you play on the track
   pass through.

Parameters: **Start bar**, **Transpose** (±12), **Harmony** / **Bass** on-off,
**Velocity %**, **Loop song**, and **Beat unit** (Logic's ruler counts the
meter's denominator as one beat; switch to *Quarter note* only if a non-4/4
song drifts in your Logic version).

## What it is not

- No network: the script carries its notes. Regenerate the file after editing
  the score.
- No drums: Logic's own drummer or the exported `.mid` cover that; the script
  plays harmony and bass.
- No native AU/VST3 yet. That plugin (JUCE, host transport and project
  insertion) is a separate build that needs CMake and a JUCE checkout; this
  Scripter client needs nothing but Logic.

## Tests

`plugin/logic-scripter/test/scripter-host.mjs` is a stand-in for the documented
Scripter API (timing info, parameters, NoteOn/NoteOff, Trace). The test drives
the script through play, stop, locate, cycle wrap, loop, transpose, 6/8 and
pass-through:

```
bash scripts/dev.sh frontend-test plugin/logic-scripter/test/theartist_chords.test.mjs
```

(`node --test` on that file from a checkout.) The mock is not Logic; the real
check is step 3 above.
