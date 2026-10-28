import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildImportedSong, createScoreImportDraft, readScoreImportResponse, validateScoreImportDraft } from './scoreImport.ts';

test('a real printed-score Meta response passes review and reaches the score with key-relative Roman analysis', () => {
  const evidence = JSON.parse(readFileSync(new URL('../../../experiments/meta/printed_import_review_smoke.json', import.meta.url), 'utf8'));
  assert.equal(evidence.chords_match, true);
  const recognized = readScoreImportResponse(evidence.result, 'chord_symbols');
  const draft = createScoreImportDraft(recognized, 'score-import.png');
  assert.equal(validateScoreImportDraft(draft).valid, true);
  let identity = 0;
  const song = buildImportedSong(draft, () => `evidence-${++identity}`);
  assert.equal(song.key, 'C major');
  assert.deepEqual(song.measures.map((bar) => bar.chords.map((chord) => chord?.romanNumeral)), [
    ['Imaj7', 'vi7'], ['ii7', 'V7'], ['IVmaj7', 'V7'], ['iii7', 'vi7'],
  ]);
  assert.equal(song.importSource?.mode, 'chord_symbols');
  assert.equal(song.importSource?.requestId, evidence.result.requestId);
});
