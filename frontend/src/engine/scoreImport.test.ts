import { test } from 'node:test';
import assert from 'node:assert/strict';
import {
  MAX_SCORE_IMPORT_BYTES,
  buildImportedSong,
  checkScoreFile,
  createScoreImportDraft,
  importMeasureRomanPreview,
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
  assert.deepEqual(song.importSource, {
    filename: 'chart.pdf', model: 'muse-spark-1.3', requestId: 'request-test', mode: 'chord_symbols',
    measures: [
      { chordBasis: 'printed', confidence: 'high', evidence: '', originalChords: ['Cmaj7'] },
      { chordBasis: 'printed', confidence: 'high', evidence: '', originalChords: ['Dm7', 'G7'] },
    ],
  });
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

test('legacy symbol responses default to printed high confidence without changing their source text', () => {
  const parsed = readScoreImportResponse(response());
  assert.equal(parsed.mode, 'chord_symbols');
  assert.equal(parsed.measures[0].chordBasis, 'printed');
  assert.equal(parsed.measures[0].confidence, 'high');
  const draft = createScoreImportDraft(parsed, 'legacy.png');
  assert.equal(draft.mode, 'chord_symbols');
  assert.deepEqual(draft.measures[0].originalChords, ['Cmaj7']);
});

test('note analysis requires the requested mode to match and keeps the inferred draft evidence after correction', () => {
  const raw = response({ mode: 'infer_harmony', measures: [
    { chords: ['Am', 'E7'], sourceLabel: 'Bass staff, bar 1', needsReview: true, note: 'Visible bass A then E; C natural supports minor.', chordBasis: 'inferred', confidence: 'medium' },
  ], sections: [] });
  assert.throws(() => readScoreImportResponse(raw));
  assert.throws(() => readScoreImportResponse(response(), 'infer_harmony'));
  const draft = createScoreImportDraft(readScoreImportResponse(raw, 'infer_harmony'), 'notes.pdf');
  assert.equal(draft.mode, 'infer_harmony');
  assert.equal(draft.measures[0].needsReview, true);
  assert.equal(draft.measures[0].chordBasis, 'inferred');
  assert.equal(draft.measures[0].confidence, 'medium');
  draft.key = 'A minor';
  draft.measures[0].chordText = 'Am Dm';
  const song = buildImportedSong(draft);
  assert.deepEqual(song.measures[0].chords.map((chord) => chord?.romanNumeral), ['i', 'iv']);
  assert.deepEqual(song.importSource?.measures?.[0], {
    chordBasis: 'inferred', confidence: 'medium', evidence: raw.measures[0].note, originalChords: ['Am', 'E7'],
  });
  draft.measures[0].originalChords[0] = 'C';
  assert.equal(song.importSource?.measures?.[0].originalChords[0], 'Am');
});

test('invalid note-analysis provenance cannot silently become a reviewed chord score', () => {
  const base = { chords: ['C'], sourceLabel: '', needsReview: true, note: 'C E G notes visible.', chordBasis: 'inferred', confidence: 'medium' };
  for (const patch of [
    { chordBasis: 'guessed' }, { confidence: 'certain' }, { needsReview: false }, { note: '' },
    { chordBasis: 'unreadable', confidence: 'low' },
    { chordBasis: 'printed', confidence: 'low', needsReview: false },
  ]) {
    assert.throws(() => readScoreImportResponse({ ...response(), mode: 'infer_harmony', measures: [{ ...base, ...patch }] }, 'infer_harmony'));
  }
  assert.throws(() => readScoreImportResponse({ ...response(), mode: 'chord_symbols', measures: [base] }));
  assert.throws(() => readScoreImportResponse({ ...response(), mode: 'other' }));
  assert.throws(() => readScoreImportResponse({ ...response(), mode: 'infer_harmony' }, 'infer_harmony'));
});

test('unreadable note bars stay empty and block import until the user supplies a chord', () => {
  const draft = createScoreImportDraft(readScoreImportResponse(response({ mode: 'infer_harmony', measures: [
    { chords: [], sourceLabel: 'Bar 1', needsReview: true, note: 'Bass notes are obscured.', chordBasis: 'unreadable', confidence: 'low' },
  ], sections: [] }), 'infer_harmony'), 'blurred.png');
  assert.equal(validateScoreImportDraft(draft).valid, false);
  assert.throws(() => buildImportedSong(draft));
  draft.measures[0].chordText = 'C';
  assert.equal(validateScoreImportDraft(draft).valid, true);
  assert.equal(buildImportedSong(draft).importSource?.measures?.[0].chordBasis, 'unreadable');
});

test('review key changes reanalyze fixed symbols, and both printed and inferred imports use the same Roman engine', () => {
  assert.equal(importMeasureRomanPreview('C Am', 'C major'), 'I · vi');
  assert.equal(importMeasureRomanPreview('G7', 'C major'), 'V7');
  assert.equal(importMeasureRomanPreview('C Am', 'G major'), 'IV · ii');
  assert.equal(importMeasureRomanPreview('Am E7', 'A minor'), 'i · V7');
  assert.equal(importMeasureRomanPreview('C7alt', 'C major'), null);
  assert.equal(importMeasureRomanPreview('C', ''), null);
  for (const mode of ['chord_symbols', 'infer_harmony'] as const) {
    const draft = createScoreImportDraft(response({ mode, measures: [
      { chords: ['C', 'Am'], sourceLabel: '', needsReview: mode === 'infer_harmony', note: 'C E G and A C E visible.', chordBasis: mode === 'infer_harmony' ? 'inferred' : 'printed', confidence: 'high' },
      { chords: ['G7'], sourceLabel: '', needsReview: mode === 'infer_harmony', note: 'G B D F visible.', chordBasis: mode === 'infer_harmony' ? 'inferred' : 'printed', confidence: 'high' },
    ] }), 'roman.png');
    const original = JSON.stringify(draft.measures.map((measure) => measure.originalChords));
    assert.deepEqual(buildImportedSong(draft).measures.flatMap((measure) => measure.chords.map((chord) => chord?.romanNumeral)), ['I', 'vi', 'V7', 'V7']);
    draft.key = 'G major';
    assert.deepEqual(buildImportedSong(draft).measures[0].chords.map((chord) => chord?.romanNumeral), ['IV', 'ii']);
    assert.equal(JSON.stringify(draft.measures.map((measure) => measure.originalChords)), original);
  }
});
