import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { SavedSession } from '../models/types.ts';
import { DEFAULT_PLAY_SETTINGS, enginePlayConfig, playSettingsFromSession } from '../engine/playSettings.ts';
import { mergeImport, serializeForExport, saveAll } from './sessionStorage.ts';

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
