import { test } from 'node:test';
import assert from 'node:assert/strict';
import { planImportReview } from './importReview.ts';
import { parseChordName } from './chordParser.ts';
import type { ScoreImportResponse } from './scoreImport.ts';
import type { ImportMeasureSource, Song } from '../models/types.ts';

function source(patch: Partial<ImportMeasureSource> = {}): ImportMeasureSource {
  return { chordBasis: 'printed', confidence: 'high', evidence: '', originalChords: ['C'], analysisSource: 'local', model: null, requestId: null, ...patch };
}

/** Bar 1 printed C, bar 2 empty (unread), bar 3 inferred Dm7, bar 4 explicit N.C., bar 5 empty but the musician chose N.C. */
function importedSong(): Song {
  const chord = (name: string) => parseChordName(name)!;
  return {
    id: 's', title: 'Imported', bpm: 80, key: 'C major', genre: null, timeSignature: [4, 4], sections: [],
    measures: [
      { id: 'm0', index: 0, chords: [chord('C'), chord('C')] },
      { id: 'm1', index: 1, chords: [null, null] },
      { id: 'm2', index: 2, chords: [chord('Dm7'), chord('Dm7')] },
      { id: 'm3', index: 3, chords: [null, null] },
      { id: 'm4', index: 4, chords: [null, null] },
    ],
    importSource: { filename: 'score.pdf', model: null, requestId: null, analysisSource: 'local', measures: [
      source(), source({ chordBasis: 'unreadable', confidence: 'low', originalChords: [] }),
      source({ chordBasis: 'inferred', confidence: 'medium', originalChords: ['Dm7'] }),
      source({ originalChords: [], originalNoChord: true }), source({ originalChords: [], userNoChord: true }),
    ] },
  };
}

function verified(patch: Partial<ScoreImportResponse> = {}): ScoreImportResponse {
  const bar = (chords: string[], extra: Record<string, unknown> = {}) =>
    ({ chords, sourceLabel: 'bar', needsReview: false, note: '', analysisSource: 'meta', model: 'muse-spark-1.3', requestId: 'req-9', ...extra });
  return {
    title: 'Imported', key: 'C major', timeSignature: [4, 4], warnings: [], sections: [], model: 'muse-spark-1.3', requestId: 'req-9',
    analysisSource: 'mixed', mode: 'infer_harmony',
    measures: [
      bar(['C'], { analysisSource: 'local', model: null, requestId: null }),
      bar(['G7'], { chordBasis: 'inferred', confidence: 'medium', note: 'Dominant from the melody notes.' }),
      bar(['Dm7'], { needsReview: true, confidence: 'low', note: 'Local/Meta comparison: chord readings differ. Meta read Fmaj7.' }),
      bar([], { noChord: true }),
      bar(['Am7']),
    ],
    verification: { status: 'compared', localMeasures: 5, metaMeasures: 5, comparedMeasures: 5, disputedMeasures: [2], notes: [] },
    ...patch,
  } as ScoreImportResponse;
}

test('a compared reading flags disputed bars and fills only untouched empty bars that are not N.C.', () => {
  const plan = planImportReview(importedSong(), verified());
  assert.deepEqual(plan.flags, [{ index: 2, review: 'Check against the original: chord readings differ.', confidence: 'low' }]);
  assert.equal(plan.fills.length, 1);
  assert.equal(plan.fills[0].index, 1);
  assert.deepEqual(plan.fills[0].chords.map((c) => c?.root + c?.quality), ['G7', 'G7']);
  assert.equal(plan.fills[0].source.analysisSource, 'meta');
  assert.equal(plan.fills[0].source.requestId, 'req-9');
  assert.match(plan.fills[0].source.editorReview ?? '', /Proposed from the original/);
  assert.equal(plan.summary, 'Checked against the original: 1 bar flagged for review, 1 bar filled where the local reader had no chord.');
});

test('unparseable, long or missing Meta proposals leave a bar empty, and agreement says so', () => {
  const song = importedSong();
  const odd = verified();
  odd.measures[1] = { ...odd.measures[1], chords: ['Gxx7'] };
  assert.equal(planImportReview(song, odd).fills.length, 0);
  const three = verified();
  three.measures[1] = { ...three.measures[1], chords: ['G7', 'C', 'F'] };
  assert.equal(planImportReview(song, three).fills.length, 0);
  const agree = verified({ verification: { status: 'compared', localMeasures: 5, metaMeasures: 5, comparedMeasures: 5, disputedMeasures: [], notes: [] } });
  agree.measures[1] = { ...agree.measures[1], chords: [] };
  const plan = planImportReview(song, agree);
  assert.deepEqual(plan.flags, []);
  assert.equal(plan.summary, 'Checked against the original: both readings agree.');
});

test('skipped, unaligned and local-only outcomes change nothing on the staff', () => {
  const song = importedSong();
  for (const [verification, expected] of [
    [{ status: 'local_only', localMeasures: 5, metaMeasures: 0, comparedMeasures: 0, disputedMeasures: [], notes: ['Meta reads at most 128 bars.'] }, /at most 128/],
    [{ status: 'local_fallback', localMeasures: 5, metaMeasures: 0, comparedMeasures: 0, disputedMeasures: [], notes: [] }, /skipped/],
    [{ status: 'unaligned', localMeasures: 5, metaMeasures: 4, comparedMeasures: 0, disputedMeasures: [0, 1, 2, 3, 4], notes: [] }, /4 bars where the score has 5 bars/],
  ] as const) {
    const plan = planImportReview(song, verified({ verification: { ...verification, disputedMeasures: [...verification.disputedMeasures], notes: [...verification.notes] } }));
    assert.deepEqual(plan.flags, []);
    assert.deepEqual(plan.fills, []);
    assert.match(plan.summary, expected);
  }
  assert.match(planImportReview(song, verified({ verification: null })).summary, /no comparison/);
});
