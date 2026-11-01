import { test } from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import type { Song } from '../models/types.ts';
import { parseChordName } from '../engine/chordParser.ts';
import { reharmSymbol } from '../engine/reharmonize.ts';
import type { ReharmResult } from '../engine/reharmonize.ts';

const SRC_URL = new URL('../', import.meta.url).href;
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.startsWith(SRC_URL) && /^\.\.?\//.test(specifier) && !/\.\w+$/.test(specifier)) specifier += '.ts';
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url === `${SRC_URL}engine/playback.ts`) return { format: 'module', shortCircuit: true,
      source: 'export function cancelPendingStart() {}\nexport function setLiveBpm() {}\nexport function stopPlayback() {}' };
    return nextLoad(url, context);
  },
});
const storage = new Map<string, string>();
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
} });
let nextTimer = 0;
const timers = new Map<number, () => void>();
Object.defineProperty(globalThis, 'window', { configurable: true, value: {
  setTimeout: (callback: () => void) => { timers.set(++nextTimer, callback); return nextTimer; },
  clearTimeout: (id: number) => timers.delete(id),
} });
const { useSongStore } = await import('./songStore.ts');
const { useReharmonizeStore } = await import('./reharmonizeStore.ts');
const editor = () => useSongStore.getState();
const reharm = () => useReharmonizeStore.getState();
const fixture: Song = { id: 'reharm-store', title: 'Test passage', bpm: 80, key: 'C major',
  genre: null, timeSignature: [4, 4], sections: [], autoTitle: false,
  measures: [['Dm7', 'G7'], ['Cmaj7', 'Am7']].map((chords, index) => ({ id: `bar-${index}`, index,
    chords: chords.map(parseChordName) as Song['measures'][0]['chords'] })),
};
const response: ReharmResult = { modelUsed: 'Music Transformer', metaModel: 'muse-spark-1.3', contextMeasures: [0, 1],
  candidates: ['Db7', 'Fm7', 'G9'].map((after, index) => ({ id: String(index), family: 'common_tones',
    changes: [{ address: { measureIndex: 0, slotIndex: index === 1 ? 0 : 1 },
      before: index === 1 ? 'Dm7' : 'G7', after, commonTones: 2, modes: [] }],
    pitchDistance: .5, originalPitchDistance: .8, bassMotion: 2, originalBassMotion: 3, mathScore: 1, modelScore: -2 })),
};
function saved(): Song {
  for (const [id, callback] of timers) { timers.delete(id); callback(); }
  return JSON.parse(storage.get('theartist-song')!);
}
function symbols(song: Song, measure = 0) { return song.measures[measure].chords.map(c => c && reharmSymbol(c)); }

test('real stores autosave the last Apply, retain manual edits, and cancel only pending previews', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  editor().setSong(fixture);
  editor().selectSlotRange({ measureIndex: 0, slotIndex: 0 }, { measureIndex: 0, slotIndex: 1 });
  await reharm().run('ft_f1', 1, 'auto');
  reharm().preview(0);
  reharm().preview(1);
  assert.deepEqual(symbols(editor().song), ['Fm7', 'Db7']);
  assert.deepEqual(symbols(saved()), ['Dm7', 'G7']);
  reharm().apply();
  assert.deepEqual(symbols(saved()), ['Fm7', 'Db7']);
  reharm().preview(2);
  editor().setChord({ measureIndex: 1, slotIndex: 0 }, parseChordName('Ab'));
  assert.deepEqual(symbols(saved()), ['Fm7', 'Db7']);
  assert.equal(symbols(saved(), 1)[0], 'Ab');
  reharm().close();
  assert.deepEqual(symbols(editor().song), ['Fm7', 'Db7']);
  assert.equal(symbols(editor().song, 1)[0], 'Ab');
  assert.equal(editor().chordPreview, null);
});

test('replacing a song clears previews without reentrant rollback into the replacement', async t => {
  t.mock.method(globalThis, 'fetch', async () => Response.json(response));
  editor().setSong(fixture);
  editor().selectSlotRange({ measureIndex: 0, slotIndex: 0 }, { measureIndex: 0, slotIndex: 1 });
  await reharm().run('ft_f1', 1, 'auto');
  reharm().preview(0);
  editor().setSong(fixture);
  assert.equal(editor().chordPreview, null);
  assert.equal(reharm().comparison, null);
  assert.deepEqual(symbols(editor().song), ['Dm7', 'G7']);
  assert.deepEqual(symbols(saved()), ['Dm7', 'G7']);
});
