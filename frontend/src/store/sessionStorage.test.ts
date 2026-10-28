import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { SavedSession } from '../models/types.ts';
import { DEFAULT_PLAY_SETTINGS, enginePlayConfig, playSettingsFromSession } from '../engine/playSettings.ts';
import { mergeImport, serializeForExport, saveAll, loadAll } from './sessionStorage.ts';

test('bad project files cannot replace valid working data or crash the score renderer', () => {
  const malformed = {
    id: 'bad', name: 'Bad', createdAt: 0, starred: false,
    song: {}, generation: { model: 'ft_f1', genre: null },
  };
  const { merged, result } = mergeImport([], JSON.stringify({ version: 1, sessions: [malformed] }));
  assert.deepEqual(merged, []);
  assert.equal(result.skipped, 1);
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

test('project file roundtrip retains real chords, uncertain sections, source and a muted part', () => {
  const result = mergeImport([], serializeForExport([importedProject]));
  assert.deepEqual(result.merged[0], importedProject);
});

test('note-derived source proposals and evidence survive browser save/reload and project file roundtrip', () => {
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
    assert.deepEqual(mergeImport([], serializeForExport(loadAll())).merged[0].song.importSource, project.song.importSource);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'localStorage', descriptor);
    else Reflect.deleteProperty(globalThis, 'localStorage');
  }
});

test('foreign projects with invalid or disguised inferred provenance are skipped', () => {
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
    const { result, merged } = mergeImport([], JSON.stringify({ version: 1, sessions: [project] }));
    assert.equal(result.skipped, 1);
    assert.deepEqual(merged, []);
  }
});

test('an invalid arrangement cache is discarded while the score and settings survive', () => {
  const result = mergeImport([], JSON.stringify({ version: 1, sessions: [
    { ...importedProject, arrangement: { bassPattern: null } },
  ] }));
  assert.equal(result.result.added, 1);
  assert.equal(result.merged[0].arrangement, undefined);
  assert.deepEqual(result.merged[0].song, importedProject.song);
});

test('duplicate IDs inside one project file receive independent identities', () => {
  const result = mergeImport([], serializeForExport([importedProject, importedProject]));
  assert.deepEqual(result.result, { added: 1, renamed: 1, skipped: 0 });
  assert.notEqual(result.merged[0].id, result.merged[1].id);
});

test('session export/import keeps independent controller levels, including a muted part', () => {
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
  const { merged, result } = mergeImport([], serializeForExport([session]));
  assert.deepEqual(result, { added: 1, renamed: 0, skipped: 0 });
  assert.deepEqual(merged[0].generation, session.generation);
  const config = enginePlayConfig(playSettingsFromSession(merged[0].generation), merged[0].song.genre);
  assert.deepEqual(
    [config.masterVolume, config.harmonyVolume, config.bassVolume, config.drumVolume],
    [0.8, 0.65, 0, 0.25],
  );
});
