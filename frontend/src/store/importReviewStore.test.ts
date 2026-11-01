import { test } from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { parseChordName } from '../engine/chordParser.ts';
import type { ScoreImportResponse } from '../engine/scoreImport.ts';
import type { Song } from '../models/types.ts';

const SRC_URL = new URL('../', import.meta.url).href;
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.startsWith(SRC_URL) && /^\.\.?\//.test(specifier) && !/\.\w+$/.test(specifier)) specifier += '.ts';
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url === `${SRC_URL}engine/playback.ts`) {
      return { format: 'module', shortCircuit: true,
        source: 'export function cancelPendingStart() {}\nexport function setLiveBpm() {}\nexport function stopPlayback() {}\n' };
    }
    return nextLoad(url, context);
  },
});
const storage = new Map<string, string>();
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
} });
Object.defineProperty(globalThis, 'window', { configurable: true, value: globalThis });

const { useSongStore } = await import('./songStore.ts');
const { createImportReviewStore } = await import('./importReviewStore.ts');

function imported(): Song {
  const chord = (name: string) => parseChordName(name)!;
  return {
    id: 'imported', title: 'Imported', bpm: 80, key: 'C major', genre: null, timeSignature: [4, 4], sections: [],
    measures: [
      { id: 'a', index: 0, chords: [chord('C'), chord('C')] },
      { id: 'b', index: 1, chords: [null, null] },
      { id: 'c', index: 2, chords: [chord('Dm7'), chord('Dm7')] },
    ],
    importSource: { filename: 'score.pdf', model: null, requestId: null, analysisSource: 'local', measures: [
      { chordBasis: 'printed', confidence: 'high', evidence: '', originalChords: ['C'], analysisSource: 'local', model: null, requestId: null },
      { chordBasis: 'unreadable', confidence: 'low', evidence: '', originalChords: [], analysisSource: 'local', model: null, requestId: null },
      { chordBasis: 'inferred', confidence: 'medium', evidence: '', originalChords: ['Dm7'], analysisSource: 'local', model: null, requestId: null },
    ] },
  };
}

function verifiedReading(): ScoreImportResponse {
  const bar = (chords: string[], extra: Record<string, unknown> = {}) =>
    ({ chords, sourceLabel: 'bar', needsReview: false, note: '', analysisSource: 'meta', model: 'muse-spark-1.3', requestId: 'req-1', ...extra });
  return {
    title: 'Imported', key: 'C major', timeSignature: [4, 4], warnings: [], sections: [], model: 'muse-spark-1.3', requestId: 'req-1',
    analysisSource: 'mixed', mode: 'infer_harmony',
    measures: [bar(['C'], { analysisSource: 'local', model: null, requestId: null }), bar(['G7']),
      bar(['Dm7'], { confidence: 'low', note: 'Local/Meta comparison: chord readings differ. Meta read Fmaj7.' })],
    verification: { status: 'compared', localMeasures: 3, metaMeasures: 3, comparedMeasures: 3, disputedMeasures: [2], notes: [] },
  } as ScoreImportResponse;
}

const file = new File(['%PDF-'], 'score.pdf', { type: 'application/pdf' });
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

test('a finished review marks disputed bars, fills the untouched empty bar and reports the request', async () => {
  useSongStore.getState().importSong(imported());
  const epoch = useSongStore.getState().songEpoch;
  const statuses: string[] = [];
  const store = createImportReviewStore(async (_file, _mime, engine, mode, options) => {
    assert.equal(engine, 'verified');
    assert.equal(mode, 'infer_harmony');
    options?.onStatus?.('Meta is reading…');
    return verifiedReading();
  });
  store.subscribe((state) => statuses.push(state.phase + ':' + (state.label || state.summary)));
  store.getState().start(file, 'application/pdf', epoch);
  assert.equal(store.getState().phase, 'running');
  await settle();
  const state = store.getState();
  assert.equal(state.phase, 'done');
  assert.deepEqual(state.flagged, [2]);
  assert.equal(state.filled, 1);
  assert.equal(state.requestId, 'req-1');
  assert.match(state.summary, /1 bar flagged.*1 bar filled/);
  const song = useSongStore.getState().song;
  assert.equal(song.measures[1].chords[0]?.root, 'G');
  assert.equal(song.measures[1].chords[0]?.romanNumeral, 'V7');
  assert.equal(song.importSource?.measures?.[1].analysisSource, 'meta');
  assert.equal(song.importSource?.measures?.[2].editorReview, 'Meta review: chord readings differ.');
  assert.equal(song.importSource?.analysisSource, 'mixed');
  assert.equal(useSongStore.getState().editHistory.length, 1, 'a fill is one undo step');
  assert.ok(statuses.includes('running:Meta is reading…'));
  store.getState().dismiss();
  assert.equal(store.getState().phase, 'idle');
});

test('a bar the musician filled meanwhile is kept, and a replaced song discards the review', async () => {
  useSongStore.getState().importSong(imported());
  const epoch = useSongStore.getState().songEpoch;
  let release: (value: ScoreImportResponse) => void = () => {};
  const store = createImportReviewStore(() => new Promise((resolve) => { release = resolve; }));
  store.getState().start(file, 'application/pdf', epoch);
  useSongStore.getState().setChord({ measureIndex: 1, slotIndex: 0 }, parseChordName('Em7')!);
  release(verifiedReading());
  await settle();
  assert.equal(store.getState().phase, 'done');
  assert.equal(store.getState().filled, 0, 'the musician\'s Em7 is not replaced');
  assert.equal(useSongStore.getState().song.measures[1].chords[0]?.root, 'E');

  const again = createImportReviewStore(() => new Promise((resolve) => { release = resolve; }));
  again.getState().start(file, 'application/pdf', useSongStore.getState().songEpoch);
  useSongStore.getState().clearSong();
  assert.equal(again.getState().phase, 'idle', 'replacing the song cancels the review');
  release(verifiedReading());
  await settle();
  assert.equal(again.getState().phase, 'idle');
  assert.equal(useSongStore.getState().song.importSource, undefined);
});

test('failures and cancellation are visible without touching the score', async () => {
  useSongStore.getState().importSong(imported());
  const epoch = useSongStore.getState().songEpoch;
  const failing = createImportReviewStore(async () => { throw new Error('Meta did not finish within the time limit.'); });
  failing.getState().start(file, 'application/pdf', epoch);
  await settle();
  assert.equal(failing.getState().phase, 'failed');
  assert.match(failing.getState().summary, /Meta review unavailable: Meta did not finish/);
  assert.equal(useSongStore.getState().song.measures[1].chords[0], null);
  const cancelled = createImportReviewStore((_f, _m, _e, _mode, options) => new Promise((_resolve, reject) => {
    options?.signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')));
  }));
  cancelled.getState().start(file, 'application/pdf', epoch);
  cancelled.getState().cancel();
  await settle();
  assert.equal(cancelled.getState().phase, 'idle');
});
