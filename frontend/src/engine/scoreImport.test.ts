import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  MAX_SCORE_IMPORT_BYTES,
  buildImportedSong,
  buildScoreImportForEditor,
  checkScoreFile,
  createScoreImportDraft,
  importMeasureRomanPreview,
  metaAssistSummary,
  scoreImportReadyStatus,
  scoreImportRequestBody,
  parseImportedChord,
  readScoreImportResponse,
  validateScoreImportDraft,
  validateScoreImportForEditor,
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
  assert.throws(() => readScoreImportResponse({ ...response(), measures: Array(513).fill(response().measures[0]) }));
  assert.throws(() => readScoreImportResponse({ ...response(), sections: [{ ...response().sections[0], section: 'made_up' }] }));
});

test('import chord parser rejects unsupported qualities rather than using major fallback', () => {
  for (const symbol of ['C7alt', 'C7(b9)', 'C6/9', 'C/Gb/Ab', 'Cxyz', 'N.C.', '%', 'H7']) {
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
    filename: 'chart.pdf', model: 'muse-spark-1.3', requestId: 'request-test', mode: 'chord_symbols', analysisSource: 'meta',
    measures: [
      { chordBasis: 'printed', confidence: 'high', evidence: '', originalChords: ['Cmaj7'], sourceMeasureIndex: 0, analysisSource: 'meta', model: 'muse-spark-1.3', requestId: null, notes: [], writtenNotes: [], bassNotes: [], originalNoChord: false, userNoChord: false, timeSignature: null },
      { chordBasis: 'printed', confidence: 'high', evidence: '', originalChords: ['Dm7', 'G7'], sourceMeasureIndex: 1, analysisSource: 'meta', model: 'muse-spark-1.3', requestId: null, notes: [], writtenNotes: [], bassNotes: [], originalNoChord: false, userNoChord: false, timeSignature: null },
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

test('opening a score draft preserves unresolved, unsupported and longer source bars for later editing', () => {
  const draft = createScoreImportDraft(response({ sections: [], measures: [
    { chords: ['Cmaj7'], sourceLabel: 'bar 1', needsReview: false, note: '' },
    { chords: [], sourceLabel: 'bar 2', needsReview: true, note: 'Unreadable notes.', chordBasis: 'unreadable', confidence: 'low' },
    { chords: ['C7alt', 'G7'], sourceLabel: 'bar 3', needsReview: true, note: 'Correct the first symbol.' },
    { chords: ['C', 'F', 'G7'], sourceLabel: 'bar 4', needsReview: true, note: 'Three changes.' },
    { chords: [], noChord: true, sourceLabel: 'bar 5', needsReview: false, note: '' },
  ] }), 'draft.pdf');
  assert.equal(validateScoreImportDraft(draft).valid, false);
  assert.equal(validateScoreImportForEditor(draft).valid, true);
  const song = buildScoreImportForEditor(draft);
  assert.equal(song.measures.length, 5);
  assert.equal(song.measures[0].chords[0]?.romanNumeral, 'Imaj7');
  assert.deepEqual(song.measures[1].chords, [null, null]);
  assert.equal(song.measures[2].chords[0], null);
  assert.equal(song.measures[2].chords[1]?.root, 'G');
  assert.deepEqual(song.measures[3].chords, [null, null]);
  assert.deepEqual(song.measures[4].chords, [null, null]);
  const source = song.importSource!.measures!;
  assert.equal(source[1].originalNoChord, false);
  assert.equal(source[1].userNoChord, false);
  assert.match(source[1].editorReview!, /No chord was determined/);
  assert.match(source[2].editorReview!, /need correction/);
  assert.deepEqual(source[3].originalChords, ['C', 'F', 'G7']);
  assert.match(source[3].editorReview!, /3 source changes are preserved/);
  assert.equal(source[4].originalNoChord, true);
  assert.equal(source[4].editorReview, undefined);
  assert.deepEqual(JSON.parse(JSON.stringify(song)).importSource, song.importSource);
});

test('opening unresolved score drafts still requires usable project metadata and section bounds', () => {
  const draft = createScoreImportDraft(response({ sections: [], measures: [{ chords: [], sourceLabel: '', needsReview: true, note: '' }] }), 'draft.pdf');
  for (const patch of [{ key: '' }, { timeSignature: '' }, { bpm: '0' }, { title: '' }, { sections: [{ type: null, label: 'Part', startBar: '1', endBar: '2', origin: 'manual' as const, note: '' }] }]) {
    const invalid = { ...draft, ...patch };
    assert.equal(validateScoreImportForEditor(invalid).valid, false);
    assert.throws(() => buildScoreImportForEditor(invalid));
  }
});

test('opening a valid score in the editor preserves the strict import result exactly', () => {
  const draft = createScoreImportDraft(response(), 'chart.pdf');
  const ids = () => { let next = 0; return () => `id-${next++}`; };
  assert.deepEqual(buildScoreImportForEditor(draft, ids()), buildImportedSong(draft, ids()));
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
    sourceMeasureIndex: 0, analysisSource: 'meta', model: 'muse-spark-1.3', requestId: null, notes: [], writtenNotes: [], bassNotes: [], originalNoChord: false, userNoChord: false, timeSignature: null,
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

test('score import requests use local code until external assistance is explicitly selected', () => {
  assert.deepEqual(scoreImportRequestBody('chart.pdf', 'application/pdf', 'bytes', 'chord_symbols'), {
    filename: 'chart.pdf', mimeType: 'application/pdf', dataBase64: 'bytes', mode: 'chord_symbols', engine: 'local',
  });
  assert.equal(scoreImportRequestBody('notes.pdf', 'application/pdf', 'bytes', 'infer_harmony', true).engine, 'auto');
});

test('local analysis accepts a null model, real pitch evidence and source meters without inventing an API request', () => {
  const parsed = readScoreImportResponse(response({ analysisSource: 'local', model: null, requestId: null, mode: 'infer_harmony', sections: [], measures: [
    { chords: ['C', 'G7'], sourceLabel: 'Bar 1', chordBasis: 'inferred', confidence: 'high', needsReview: true, note: 'C E G over C; G B D F over G.', notes: ['C4', 'E4', 'G4', 'G3', 'B3', 'D4', 'F4'], bassNotes: ['C3', 'G2'], timeSignature: [2, 4] },
  ] }), 'infer_harmony', 'local');
  const draft = createScoreImportDraft(parsed, 'local.pdf');
  const imported = buildImportedSong(draft);
  assert.equal(imported.importSource?.analysisSource, 'local');
  assert.equal(imported.importSource?.model, null);
  assert.equal(imported.importSource?.requestId, null);
  assert.deepEqual(imported.importSource?.measures?.[0].notes, parsed.measures[0].notes);
  assert.deepEqual(imported.importSource?.measures?.[0].bassNotes, ['C3', 'G2']);
  assert.deepEqual(imported.importSource?.measures?.[0].timeSignature, [2, 4]);
  assert.deepEqual(imported.measures[0].chords.map((chord) => chord?.romanNumeral), ['I', 'V7']);
});

test('mixed interpretation retains each passage source and request and is rejected for local-only requests', () => {
  const raw = response({ analysisSource: 'mixed', mode: 'infer_harmony', sections: [], measures: [
    { chords: ['C'], sourceLabel: '', chordBasis: 'inferred', confidence: 'high', needsReview: true, note: 'C E G visible.', notes: ['C4', 'E4', 'G4'], analysisSource: 'local' },
    { chords: ['Dm'], sourceLabel: '', chordBasis: 'inferred', confidence: 'medium', needsReview: true, note: 'D F A support a D minor interpretation.', notes: ['D4', 'F4', 'A4'], analysisSource: 'meta', requestId: 'bounded-request' },
  ] });
  assert.throws(() => readScoreImportResponse(raw, 'infer_harmony', 'local'));
  const draft = createScoreImportDraft(readScoreImportResponse(raw, 'infer_harmony', 'auto'), 'mixed.pdf');
  assert.equal(draft.measures[0].analysisSource, 'local');
  assert.equal(draft.measures[1].analysisSource, 'meta');
  assert.equal(buildImportedSong(draft).importSource?.measures?.[1].requestId, 'bounded-request');
  assert.throws(() => readScoreImportResponse({ ...raw, measures: [{ ...raw.measures[0], analysisSource: undefined }] }, 'infer_harmony'));
});

test('the Meta assist summary separates proposals from empty answers and keeps every request id', () => {
  const meta = { chords: ['Dm'], sourceLabel: '', chordBasis: 'inferred' as const, confidence: 'medium' as const, needsReview: true, note: 'D F A.', notes: ['D4', 'F4', 'A4'], analysisSource: 'meta' as const };
  const raw = response({ analysisSource: 'mixed', mode: 'infer_harmony', sections: [], measures: [
    { chords: ['C'], sourceLabel: '', chordBasis: 'inferred', confidence: 'high', needsReview: true, note: 'C E G.', notes: ['C4', 'E4', 'G4'], analysisSource: 'local' },
    { ...meta, requestId: 'req-b' },
    { ...meta, requestId: 'req-a' },
    { ...meta, chords: [], chordBasis: 'unreadable', confidence: 'low', requestId: 'req-b' },
  ] });
  const draft = createScoreImportDraft(readScoreImportResponse(raw, 'infer_harmony', 'auto'), 'mixed.pdf');
  assert.deepEqual(metaAssistSummary(draft), { bars: 3, proposedBars: 2, unresolvedBars: 1, unreviewedBars: 1, requestIds: ['req-b', 'req-a'] });
  assert.match(scoreImportReadyStatus(draft, true), /analyzed 3 bars and proposed chords for 2/);
  assert.match(scoreImportReadyStatus(draft, true), /1 bar remains unresolved/);
  assert.match(scoreImportReadyStatus(draft, true), /req-b, req-a/);
  const local = createScoreImportDraft(readScoreImportResponse(response({ analysisSource: 'local', model: null, requestId: null, mode: 'infer_harmony', sections: [], measures: [
    { chords: ['C'], sourceLabel: '', chordBasis: 'printed', confidence: 'high', needsReview: false, note: 'Printed C.', notes: ['C4', 'E4', 'G4'] },
  ] }), 'infer_harmony', 'auto'), 'local.pdf');
  assert.deepEqual(metaAssistSummary(local), { bars: 0, proposedBars: 0, unresolvedBars: 0, unreviewedBars: 0, requestIds: [] });
  assert.match(scoreImportReadyStatus(local, true), /local reader resolved every bar/);
});

test('assisted import does not claim local success for unresolved bars that could not be sent to Meta', () => {
  const local = createScoreImportDraft(readScoreImportResponse(response({
    analysisSource: 'local', model: null, requestId: null, mode: 'infer_harmony', sections: [], measures: [
      { chords: [], sourceLabel: '', chordBasis: 'unreadable', confidence: 'low', needsReview: true, note: 'No supported notes to send.', notes: [] },
      { chords: [], sourceLabel: '', chordBasis: 'printed', confidence: 'high', needsReview: false, note: 'Printed N.C.', noChord: true },
    ],
  }), 'infer_harmony', 'auto'), 'local.pdf');
  assert.deepEqual(metaAssistSummary(local), { bars: 0, proposedBars: 0, unresolvedBars: 1, unreviewedBars: 1, requestIds: [] });
  assert.match(scoreImportReadyStatus(local, true), /Meta was not called. 1 bar remains unresolved/);
  assert.doesNotMatch(scoreImportReadyStatus(local, true), /resolved every bar/);
  assert.equal(scoreImportReadyStatus(local, false), 'Ready to review.');
});

test('automatic form proposals reach editable sections without claiming no Meta call when printed chords needed none', () => {
  const raw = response({
    mode: 'infer_harmony', analysisSource: 'mixed', requestId: 'req-form',
    formAnalysis: { model: 'muse-spark-1.3', requestId: 'req-form', sectionsProposed: 1 },
    measures: [{ chords: ['C'], sourceLabel: '', chordBasis: 'printed', confidence: 'high', needsReview: false,
      note: '', analysisSource: 'local' }],
    sections: [{ section: 'intro', label: 'Intro', startMeasure: 0, length: 1, basis: 'inferred', note: 'An opening tonic phrase.' }],
  });
  const draft = createScoreImportDraft(readScoreImportResponse(raw, 'infer_harmony', 'auto'), 'source.pdf');
  assert.match(scoreImportReadyStatus(draft, 'auto'), /Form: 1 inferred sections/);
  assert.match(scoreImportReadyStatus(draft, 'auto'), /req-form/);
  assert.doesNotMatch(scoreImportReadyStatus(draft, 'auto'), /Meta was not called/);
  const song = buildScoreImportForEditor(draft);
  assert.equal(song.sections[0].type, 'intro');
  assert.equal(song.sections[0].origin, 'inferred');
  assert.equal(song.importSource?.requestId, 'req-form');
  assert.equal(scoreImportRequestBody('source.png', 'image/png', 'bytes', 'infer_harmony', 'meta').engine, 'meta');
  assert.throws(() => readScoreImportResponse(raw, 'infer_harmony', 'meta'));
  assert.throws(() => readScoreImportResponse({ ...raw, formAnalysis: { ...raw.formAnalysis, sectionsProposed: -1 } }, 'infer_harmony', 'auto'));
});

test('actual rests import as empty slots while unresolved bars require an explicit user N.C. choice', () => {
  const draft = createScoreImportDraft(readScoreImportResponse(response({ analysisSource: 'local', model: null, requestId: null, mode: 'infer_harmony', sections: [], measures: [
    { chords: [], sourceLabel: '', chordBasis: 'printed', confidence: 'high', needsReview: false, note: 'Printed N.C.', noChord: true },
    { chords: [], sourceLabel: '', chordBasis: 'unreadable', confidence: 'low', needsReview: true, note: 'No complete chord could be determined.', notes: ['D4'] },
  ] }), 'infer_harmony', 'local'), 'rests.pdf');
  assert.equal(draft.measures[0].chordText, 'N.C.');
  assert.equal(draft.measures[1].chordText, '');
  assert.equal(validateScoreImportDraft(draft).valid, false);
  draft.measures[1].chordText = 'N.C.';
  const imported = buildImportedSong(draft);
  assert.deepEqual(imported.measures.map((measure) => measure.chords), [[null, null], [null, null]]);
  assert.equal(imported.importSource?.measures?.[0].originalNoChord, true);
  assert.equal(imported.importSource?.measures?.[0].userNoChord, false);
  assert.equal(imported.importSource?.measures?.[1].originalNoChord, false);
  assert.equal(imported.importSource?.measures?.[1].userNoChord, true);
  assert.equal(imported.importSource?.measures?.[1].chordBasis, 'unreadable');
});

test('all source changes have a Roman preview but more than two require an explicit editor selection', () => {
  const draft = createScoreImportDraft(response({ sections: [], measures: [
    { chords: ['C', 'Am', 'Dm', 'G7'], sourceLabel: '', needsReview: true, note: 'Four written changes.' },
  ] }), 'changes.pdf');
  assert.equal(importMeasureRomanPreview(draft.measures[0].chordText, draft.key), 'I · vi · ii · V7');
  assert.match(validateScoreImportDraft(draft).measureErrors[0], /4 changes.*Choose at most two/);
  assert.throws(() => buildImportedSong(draft));
  draft.measures[0].chordText = 'C G7';
  assert.deepEqual(buildImportedSong(draft).importSource?.measures?.[0].originalChords, ['C', 'Am', 'Dm', 'G7']);
});

test('512-bar code analysis is supported without shortening or losing source bar indexes', () => {
  const draft = createScoreImportDraft(readScoreImportResponse(response({ analysisSource: 'local', model: null, requestId: null, sections: [], measures: Array.from({ length: 512 }, (_, index) => ({
    chords: [], sourceLabel: `Bar ${index + 1}`, needsReview: false, note: 'Written rest.', noChord: true,
  })) }), 'chord_symbols', 'local'), 'long.pdf');
  const imported = buildImportedSong(draft);
  assert.equal(imported.measures.length, 512);
  assert.equal(imported.importSource?.measures?.[511].sourceMeasureIndex, 511);
  assert.deepEqual(imported.measures[511].chords, [null, null]);
});

test('malformed local evidence, source attribution and no-chord contradictions fail validation', () => {
  const raw = response({ analysisSource: 'local', model: null, requestId: null });
  assert.throws(() => readScoreImportResponse({ ...raw, model: 'not-a-local-model' }, 'chord_symbols', 'local'));
  assert.throws(() => readScoreImportResponse(response(), 'chord_symbols', 'local'));
  for (const patch of [
    { notes: [3] }, { bassNotes: ['C3', null] }, { timeSignature: [2, 3] },
    { noChord: true }, { analysisSource: 'meta' }, { requestId: 'external-request' },
  ]) {
    assert.throws(() => readScoreImportResponse({ ...raw, measures: [{ ...raw.measures[0], ...patch }] }, 'chord_symbols', 'local'));
  }
});

test('augmented seventh aliases use their actual pitches and Roman suffix, including a written slash bass', () => {
  for (const symbol of ['Eaug7', 'E+7', 'E7#5']) {
    const chord = parseImportedChord(symbol, 'G major')!;
    assert.equal(chord.quality, 'aug7', symbol);
    assert.equal(chord.romanNumeral, 'VI+7', symbol);
    assert.deepEqual(chord.voicing.map((note) => note % 12), [4, 8, 0, 2], symbol);
  }
  const slash = parseImportedChord('Eaug7/B#', 'G major')!;
  assert.equal(slash.bass, 'B#');
  assert.equal(slash.voicing[0] % 12, 0);
  assert.equal(slash.romanNumeral, 'VI+7');
  assert.equal(parseImportedChord('Cb', 'Cb major')?.romanNumeral, 'I');
  assert.equal(parseImportedChord('E#', 'C# major')?.romanNumeral, 'III');
});

test('original vector-PDF evidence reaches the editor as local tonic analysis without a model or external request', () => {
  const fixtures = [
    new URL('../../../experiments/local/vector-score-c.json', import.meta.url),
    new URL('../../../experiments/local/vector-score-f.json', import.meta.url),
  ];
  for (const file of fixtures) {
    const fixture = JSON.parse(readFileSync(file, 'utf8'));
    assert.equal(fixture.synthetic_fixture, true);
    const parsed = readScoreImportResponse(fixture.result, 'infer_harmony', 'local');
    const draft = createScoreImportDraft(parsed, 'original-vector-fixture.pdf');
    const imported = buildImportedSong(draft);
    assert.equal(imported.key, fixture.expected_key);
    assert.deepEqual(imported.measures[0].chords.map((chord) => chord?.romanNumeral), ['I', 'I']);
    assert.equal(imported.importSource?.analysisSource, 'local');
    assert.equal(imported.importSource?.model, null);
    assert.equal(imported.importSource?.requestId, null);
    assert.deepEqual(imported.importSource?.measures?.[0].originalChords, fixture.expected_chords);
    assert.deepEqual(imported.importSource?.measures?.[0].notes, fixture.result.measures[0].notes);
    assert.deepEqual(imported.importSource?.measures?.[0].bassNotes, fixture.result.measures[0].bassNotes);
    assert.equal(imported.importSource?.measures?.[0].originalNoChord, false);
    assert.deepEqual(imported.importSource?.measures?.[0].timeSignature, fixture.result.measures[0].timeSignature);
  }
});
