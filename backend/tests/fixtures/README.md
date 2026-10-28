# Score import fixture

`score-import.png` is an original synthetic chord chart made for this project,
distributed under the repository's MIT license. It contains no third-party
score image, melody, lyrics, or personal data.

Expected written order, two chord symbols per measure:

| Section | Measure | Chords |
|---|---|---|
| Verse | 1 | Cmaj7, Am7 |
| Verse | 2 | Dm7, G7 |
| Chorus | 3 | Fmaj7, G7 |
| Chorus | 4 | Em7, Am7 |

Key: C major. Meter: 4/4. The real Muse Spark extraction is recorded in
[`score_import_smoke.json`](../../../experiments/meta/score_import_smoke.json).
All eight symbols, four measures and both explicit sections matched. One simple
PNG is not an accuracy benchmark for complex scores or PDF documents.

`notes-only.png` is an original four-bar bass-clef whole-note fixture under the
same MIT license. It prints a C-major key and 4/4 meter but no chord symbols.
The sonorities in written order are C3/E3/G3, A2/C3/E3, D3/F3/A3 and
G2/B2/D3/F3, corresponding to C, Am, Dm and G7 (I, vi, ii, V7).
The real-call records include unsuccessful interpretations; they must not be
presented as proof of exact optical music recognition or accuracy on user scores.

`vector-score-c.pdf` and `vector-score-f.pdf` are original single-bar vector PDFs
with a self-authored Type3 music font and ToUnicode mapping; no third-party font
or score data is embedded. They contain C4/E4/G4 in treble clef and F2/A2/C3 in
bass clef, respectively. The latter also changes scale, position, key signature
and meter. `tests/vector_score_fixture.py` generates both. Local PDF parsing,
key/chord inference and Roman I are tested without any API call. Results are in
`experiments/local/` and cover these simple fixtures, not arbitrary optical notation.
