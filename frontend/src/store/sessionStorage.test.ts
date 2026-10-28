import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { SavedSession } from '../models/types.ts';
import { DEFAULT_PLAY_SETTINGS, enginePlayConfig, playSettingsFromSession } from '../engine/playSettings.ts';
import { saveAll, loadAll } from './sessionStorage.ts';
import { readScoreImportResponse, createScoreImportDraft, buildImportedSong, buildScoreImportForEditor } from '../engine/scoreImport.ts';

function withStoredProjects<T>(sessions: unknown[], run: () => T): T {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  let stored = JSON.stringify({ version: 1, sessions });
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    setItem(_key: string, value: string) { stored = value; }, getItem() { return stored; },
  } });
  try { return run(); }
  finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
    else Reflect.deleteProperty(globalThis, 'localStorage');
  }
}

function reloadProjects(sessions: unknown[]): SavedSession[] {
  return withStoredProjects(sessions, () => loadAll());
}

function roundTripProjects(sessions: SavedSession[]): SavedSession[] {
  return withStoredProjects([], () => {
    saveAll(sessions);
    return loadAll();
  });
}

test('invalid saved projects are skipped while valid neighboring projects remain available', () => {
  const malformed = {
    id: 'bad', name: 'Bad', createdAt: 0, starred: false,
    song: {}, generation: { model: 'ft_f1', genre: null },
  };
  assert.deepEqual(reloadProjects([malformed, importedProject]), [importedProject]);
});

test('storage failure is reported to the caller instead of pretending the project was saved', () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: { setItem() { throw new Error('quota'); } } });
  try { assert.throws(() => saveAll([]), /could not save/); }
  finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
    else Reflect.deleteProperty(globalThis, 'localStorage');
  }
});

const importedProject: SavedSession = {
  id: 'imported-project', name: '봄의 변형', createdAt: 0, starred: true,
  song: {
    id: 'imported-score', title: '봄의 변형', key: 'C major', genre: 'jazz', bpm: 90, timeSignature: [6, 8], autoTitle: false,
    measures: [{ id: 'bar-1', index: 0, chords: [
      { root: 'F', quality: 'maj', bass: 'C', romanNumeral: 'IV', voicing: [48, 53, 57], extensions: [] }, null,
    ] }],
    sections: [{ id: 'region-1', type: null, label: 'Repeated region', origin: 'inferred', startMeasure: 0, length: 1 }],
    importSource: { filename: 'score.pdf', model: 'muse-spark-1.3', requestId: 'sample-request' },
  },
  generation: { model: 'ft_f1', genre: 'jazz', ...DEFAULT_PLAY_SETTINGS, bassVolume: 0 },
  arrangement: { bassPattern: [0, 2], bassInstrument: 'contrabass', beatsPerMeasure: 6 },
};

test('browser save and reload retain real chords, uncertain sections, source and a muted part', () => {
  assert.deepEqual(roundTripProjects([importedProject])[0], importedProject);
});

test('note-derived source proposals and evidence survive browser save and reload', () => {
  const project = structuredClone(importedProject);
  project.song.importSource = {
    filename: 'notes.pdf', model: 'muse-spark-1.3', requestId: 'notes-request', mode: 'infer_harmony',
    measures: [{ chordBasis: 'inferred', confidence: 'medium', evidence: 'Bass C and notes E G visible.', originalChords: ['C'] }],
  };
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  let stored = '';
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    setItem(_key: string, value: string) { stored = value; }, getItem() { return stored; },
  } });
  try {
    saveAll([project]);
    assert.deepEqual(loadAll()[0].song.importSource, project.song.importSource);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
    else Reflect.deleteProperty(globalThis, 'localStorage');
  }
});

test('saved projects with invalid or disguised inferred provenance are skipped', () => {
  const validSource = {
    filename: 'notes.pdf', model: 'muse-spark-1.3', requestId: null, mode: 'infer_harmony',
    measures: [{ chordBasis: 'inferred', confidence: 'medium', evidence: 'A C E visible.', originalChords: ['Am'] }],
  };
  for (const source of [
    { ...validSource, mode: 'unknown' }, { ...validSource, measures: undefined },
    { ...validSource, mode: 'chord_symbols' }, { ...validSource, measures: [{ ...validSource.measures[0], evidence: '' }] },
    { ...validSource, measures: [{ ...validSource.measures[0], confidence: 'certain' }] },
    { ...validSource, measures: [{ ...validSource.measures[0], originalChords: [3] }] },
  ]) {
    const project = { ...importedProject, song: { ...importedProject.song, importSource: source } };
    assert.deepEqual(reloadProjects([project]), []);
  }
});

test('local and mixed source evidence including rests and explicit empty choices survives browser reload', () => {
  const project = structuredClone(importedProject);
  project.song.importSource = {
    filename: 'analysis.pdf', mode: 'infer_harmony', analysisSource: 'mixed', model: 'muse-spark-1.3', requestId: 'batch-request',
    measures: [
      { chordBasis: 'inferred', confidence: 'high', evidence: 'C E G over C.', originalChords: ['C'], sourceMeasureIndex: 0, analysisSource: 'local', model: null, requestId: null, notes: ['C4', 'E4', 'G4'], bassNotes: ['C3'], originalNoChord: false, userNoChord: true, timeSignature: [2, 4] },
      { chordBasis: 'inferred', confidence: 'medium', evidence: 'D F A supports D minor.', originalChords: ['Dm'], sourceMeasureIndex: 1, analysisSource: 'meta', model: 'muse-spark-1.3', requestId: 'passage-request', notes: ['D4', 'F4', 'A4'], bassNotes: ['D3'], originalNoChord: false, userNoChord: false, timeSignature: [4, 4] },
    ],
  };
  assert.deepEqual(roundTripProjects([project])[0].song.importSource, project.song.importSource);
  project.song.importSource.analysisSource = 'local';
  project.song.importSource.model = null;
  project.song.importSource.requestId = null;
  project.song.importSource.measures = [project.song.importSource.measures![0]];
  assert.deepEqual(roundTripProjects([project])[0].song.importSource, project.song.importSource);
});

test('unresolved editor imports retain every source symbol and their review reason through browser reload', () => {
  const response = readScoreImportResponse({
    title: 'Unfinished import', key: 'C major', timeSignature: [4, 4], sections: [], warnings: [],
    analysisSource: 'local', model: null, requestId: null, mode: 'chord_symbols',
    measures: [
      { chords: [], sourceLabel: 'Bar 1', needsReview: true, chordBasis: 'unreadable', confidence: 'low',
        note: 'No supported chord was read.', noChord: false },
      { chords: ['C', 'F', 'G7'], sourceLabel: 'Bar 2', needsReview: true, chordBasis: 'printed', confidence: 'high',
        note: 'Three printed changes in one measure.', noChord: false },
    ],
  }, 'chord_symbols', 'local');
  const song = buildScoreImportForEditor(createScoreImportDraft(response, 'unfinished.pdf'));
  const project = { ...structuredClone(importedProject), song };
  const source = song.importSource!;
  assert.ok(source.measures!.every((measure) => measure.editorReview));
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  let stored = '';
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    setItem(_key: string, value: string) { stored = value; }, getItem() { return stored; },
  } });
  try {
    saveAll([project]);
    const reloaded = loadAll();
    const restored = reloaded[0];
    assert.deepEqual(restored.song.importSource, source);
    assert.deepEqual(restored.song.measures.map((measure) => measure.chords), [[null, null], [null, null]]);
    assert.deepEqual(restored.song.importSource!.measures!.map((measure) => measure.originalChords), [[], ['C', 'F', 'G7']]);
    assert.ok(restored.song.importSource!.measures!.every((measure) => measure.originalNoChord === false && measure.userNoChord === false));
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
    else Reflect.deleteProperty(globalThis, 'localStorage');
  }
  for (const editorReview of [7, 'x'.repeat(401)]) {
    const invalid = { ...project, song: { ...project.song, importSource: {
      ...source, measures: [{ ...source.measures![0], editorReview }],
    } } };
    assert.deepEqual(reloadProjects([invalid]), []);
  }
});

test('ottava written and sounding pitches remain distinct through import and browser save/load', () => {
  const response = readScoreImportResponse({
    title: 'Octave instruction', key: 'C major', timeSignature: [4, 4], sections: [], warnings: [],
    analysisSource: 'local', model: null, requestId: null, mode: 'infer_harmony',
    measures: [{ chords: ['C'], sourceLabel: 'Bar 1', needsReview: true, chordBasis: 'inferred', confidence: 'medium',
      note: 'A bounded 8va instruction raises the written note by one octave.', writtenNotes: ['C6'], notes: ['C7'], bassNotes: ['C7'] }],
  }, 'infer_harmony', 'local');
  const song = buildImportedSong(createScoreImportDraft(response, 'octave.pdf'));
  const project = { ...structuredClone(importedProject), song };
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
  let stored = '';
  Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
    setItem(_key: string, value: string) { stored = value; }, getItem() { return stored; },
  } });
  try {
    saveAll([project]);
    const source = loadAll()[0].song.importSource?.measures?.[0];
    assert.deepEqual(source?.writtenNotes, ['C6']);
    assert.deepEqual(source?.notes, ['C7']);
    assert.deepEqual(loadAll()[0].song.importSource, song.importSource);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
    else Reflect.deleteProperty(globalThis, 'localStorage');
  }
});

test('an invalid arrangement cache is discarded while the score and settings survive', () => {
  const restored = reloadProjects([
    { ...importedProject, arrangement: { bassPattern: null } },
  ]);
  assert.equal(restored.length, 1);
  assert.equal(restored[0].arrangement, undefined);
  assert.deepEqual(restored[0].song, importedProject.song);
});

test('session browser persistence keeps independent controller levels, including a muted part', () => {
  const session: SavedSession = {
    id: 'controller-session',
    name: 'Quiet bass mix',
    createdAt: 0,
    starred: false,
    song: {
      id: 'controller-song',
      title: 'Quiet bass mix',
      key: 'C major',
      genre: 'pop',
      bpm: 80,
      timeSignature: [4, 4],
      measures: [],
    },
    generation: {
      model: 'ft_f1',
      genre: 'pop',
      ...DEFAULT_PLAY_SETTINGS,
      masterVolume: 0.8,
      harmonyVolume: 0.65,
      bassVolume: 0,
      drumVolume: 0.25,
    },
  };
  const [restored] = roundTripProjects([session]);
  assert.deepEqual(restored.generation, session.generation);
  const config = enginePlayConfig(playSettingsFromSession(restored.generation), restored.song.genre);
  assert.deepEqual(
    [config.masterVolume, config.harmonyVolume, config.bassVolume, config.drumVolume],
    [0.8, 0.65, 0, 0.25],
  );
});
