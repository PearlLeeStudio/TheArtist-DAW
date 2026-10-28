import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_SCORE_IMPORT_BYTES,
  buildImportedSong,
  checkScoreFile,
  createScoreImportDraft,
  parseImportedChord,
  readScoreImportResponse,
  validateScoreImportDraft,
} from './scoreImport.ts';
import type { ScoreImportResponse } from './scoreImport.ts';

const response = (patch: Partial<ScoreImportResponse> = {}): ScoreImportResponse => ({
  title: 'Paper sketch',
  key: 'C major',
  timeSignature: [4, 4],
  measures: [
    { chords: ['Cmaj7'], sourceLabel: 'Page 1, bar 1', needsReview: false, note: '' },
    { chords: ['Dm7', 'G7'], sourceLabel: 'Page 1, bar 2', needsReview: false, note: '' },
  ],
  sections: [{ section: 'verse', label: 'Verse', startMeasure: 0, length: 2, basis: 'inferred', note: 'No printed section label.' }],
  warnings: [],
  model: 'muse-spark-1.3',
  requestId: 'request-test',
  ...patch,
});

test('file validation matches extension, MIME, magic bytes and the 8 MiB limit', () => {
  const png = new Uint8Array([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  assert.deepEqual(checkScoreFile({ name: 'score.PNG', type: 'image/png', size: MAX_SCORE_IMPORT_BYTES }, png), { ok: true, mimeType: 'image/png' });
  assert.deepEqual(checkScoreFile({ name: 'score.png', type: '', size: 10 }, png), { ok: true, mimeType: 'image/png' });
  assert.equal(checkScoreFile({ name: 'score.png', type: 'image/png', size: MAX_SCORE_IMPORT_BYTES + 1 }, png).ok, false);
  assert.equal(checkScoreFile({ name: 'score.png', type: 'image/jpeg', size: 10 }, png).ok, false);
  assert.equal(checkScoreFile({ name: 'score.pdf', type: 'application/pdf', size: 10 }, png).ok, false);
  assert.equal(checkScoreFile({ name: 'score.svg', type: 'image/svg+xml', size: 10 }, png).ok, false);
  assert.equal(checkScoreFile({ name: 'score.png', type: 'image/png', size: 0 }, png).ok, false);
  assert.deepEqual(checkScoreFile({ name: 'score.pdf', type: 'application/pdf', size: 20 }, new TextEncoder().encode('%PDF-1.7')), { ok: true, mimeType: 'application/pdf' });
  assert.deepEqual(checkScoreFile({ name: 'score.jpeg', type: 'image/jpeg', size: 20 }, new Uint8Array([0xff, 0xd8, 0xff])), { ok: true, mimeType: 'image/jpeg' });
  assert.deepEqual(checkScoreFile({ name: 'score.webp', type: 'image/webp', size: 20 }, new TextEncoder().encode('RIFFxxxxWEBP')), { ok: true, mimeType: 'image/webp' });
});

test('recognition response keeps unresolved symbols and section ranges for review', () => {
  const raw = response({
    measures: [{ chords: ['?', 'C7alt', 'G13'], sourceLabel: 'Printed bar 9', needsReview: true, note: 'Three changes were detected.' }],
    sections: [{ section: null, label: 'Part X', startMeasure: 9, length: 4, basis: 'explicit', note: '' }],
  });
  const parsed = readScoreImportResponse(raw);
  assert.deepEqual(parsed.measures[0].chords, ['?', 'C7alt', 'G13']);
  const draft = createScoreImportDraft(parsed, 'original.pdf');
  assert.deepEqual(draft.measures[0].originalChords, ['?', 'C7alt', 'G13']);
  assert.equal(draft.sections[0].startBar, '10');
  assert.equal(draft.sections[0].endBar, '13');
  assert.equal(validateScoreImportDraft(draft).valid, false);
});

test('invalid or oversized recognition structures fail instead of dropping data', () => {
  assert.throws(() => readScoreImportResponse(null));
  assert.throws(() => readScoreImportResponse({ ...response(), model: '' }));
  assert.throws(() => readScoreImportResponse({ ...response(), warnings: ['ok', 3] }));
  assert.throws(() => readScoreImportResponse({ ...response(), timeSignature: [4, 3] }));
  assert.throws(() => readScoreImportResponse({ ...response(), measures: Array(129).fill(response().measures[0]) }));
  assert.throws(() => readScoreImportResponse({ ...response(), sections: [{ ...response().sections[0], section: 'made_up' }] }));
});

test('import chord parser rejects unsupported qualities rather than using major fallback', () => {
  for (const symbol of ['C7alt', 'C7(b9)', 'C6/9', 'C/Gb/Ab', 'Cxyz', 'N.C.', '%', 'C/E#', 'H7']) {
    assert.equal(parseImportedChord(symbol, 'C major'), null, symbol);
  }
  assert.equal(parseImportedChord('Cmajor', 'C major')?.quality, 'maj');
  assert.equal(parseImportedChord('Bø7', 'C major')?.quality, 'm7b5');
  assert.equal(parseImportedChord('B♭maj7/D', 'C major')?.root, 'Bb');
  const slash = parseImportedChord('F/C', 'C major')!;
  assert.equal(slash.bass, 'C');
  assert.equal(slash.voicing[0] % 12, 0);
  assert.notEqual(slash.romanNumeral, '');
});

test('single chords fill both slots, two chords stay distinct and imports get fresh IDs', () => {
  const draft = createScoreImportDraft(response(), 'chart.pdf');
  let nextId = 0;
  const song = buildImportedSong(draft, () => `new-${nextId++}`);
  assert.equal(song.autoTitle, false);
  assert.equal(song.measures[0].chords[0]?.quality, 'maj7');
  assert.deepEqual(song.measures[0].chords[0], song.measures[0].chords[1]);
  assert.notEqual(song.measures[0].chords[0], song.measures[0].chords[1]);
  assert.equal(song.measures[1].chords[0]?.root, 'D');
  assert.equal(song.measures[1].chords[1]?.root, 'G');
  assert.equal(new Set([song.id, ...song.measures.map((m) => m.id), ...song.sections!.map((s) => s.id)]).size, 4);
  assert.deepEqual(song.importSource, { filename: 'chart.pdf', model: 'muse-spark-1.3', requestId: 'request-test' });
  assert.equal(JSON.stringify(song).includes('dataBase64'), false);
  assert.equal(JSON.stringify(song).includes('previewUrl'), false);
});

test('zero, three and unreadable chords block load until corrected without erasing originals', () => {
  for (const chords of [[], ['C', 'F', 'G'], ['C7alt']]) {
    const draft = createScoreImportDraft(response({ measures: [{ chords, sourceLabel: '', needsReview: true, note: '' }], sections: [] }), 'chart.png');
    assert.equal(validateScoreImportDraft(draft).valid, false);
    assert.throws(() => buildImportedSong(draft));
    draft.measures[0].chordText = 'C G7';
    assert.equal(validateScoreImportDraft(draft).valid, true);
    assert.deepEqual(draft.measures[0].originalChords, chords);
  }
});

test('unknown key or unsupported meter requires an explicit correction', () => {
  const draft = createScoreImportDraft(response({ key: null, timeSignature: [9, 8] }), 'chart.png');
  assert.equal(draft.key, '');
  assert.equal(draft.timeSignature, '9/8');
  assert.equal(validateScoreImportDraft(draft).valid, false);
  draft.key = 'D minor';
  draft.timeSignature = '3/4';
  assert.equal(validateScoreImportDraft(draft).valid, true);
  assert.deepEqual(buildImportedSong(draft).timeSignature, [3, 4]);
});

test('section edits retain inferred provenance; unknown and manual types are supported', () => {
  const draft = createScoreImportDraft(response(), 'chart.pdf');
  draft.sections[0].label = 'Opening';
  draft.sections[0].type = null;
  draft.sections[0].endBar = '1';
  draft.sections.push({ type: 'chorus', label: 'Hook', startBar: '2', endBar: '2', origin: 'manual', note: '' });
  const song = buildImportedSong(draft);
  assert.equal(song.sections![0].origin, 'inferred');
  assert.equal(song.sections![0].type, null);
  assert.equal(song.sections![0].label, 'Opening');
  assert.equal(song.sections![1].origin, 'manual');
  assert.equal(song.sections![1].startMeasure, 1);
});

test('section overlaps, reversed ranges and out-of-score bars block import', () => {
  const draft = createScoreImportDraft(response(), 'chart.pdf');
  draft.sections.push({ ...draft.sections[0], label: 'Chorus', startBar: '2', endBar: '2' });
  const overlap = validateScoreImportDraft(draft);
  assert.equal(overlap.valid, false);
  assert.ok(overlap.sectionErrors.every(Boolean));
  draft.sections = [{ ...draft.sections[0], startBar: '2', endBar: '1' }];
  assert.equal(validateScoreImportDraft(draft).valid, false);
  draft.sections[0].startBar = '0';
  draft.sections[0].endBar = '3';
  assert.equal(validateScoreImportDraft(draft).valid, false);
});
