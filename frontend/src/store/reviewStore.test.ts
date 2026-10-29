import { test } from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import type { Chord, Measure, SlotAddress, Song } from '../models/types.ts';
import type { Suggestion } from '../engine/chordGenerator.ts';
import type { ReviewResult } from './reviewStore.ts';

// The stores import their modules without extensions (Vite resolves them),
// and songStore reaches the Web Audio stack through engine/playback. Resolve
// `.ts` for the relative imports under src/ and stand in for playback with
// the three no-ops songStore uses, so the stores load without a bundler.
const SRC_URL = new URL('../', import.meta.url).href;
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (context.parentURL?.startsWith(SRC_URL) && /^\.\.?\//.test(specifier) && !/\.\w+$/.test(specifier)) {
      specifier += '.ts';
    }
    return nextResolve(specifier, context);
  },
  load(url, context, nextLoad) {
    if (url === `${SRC_URL}engine/playback.ts`) {
      return {
        format: 'module',
        shortCircuit: true,
        source: 'export function cancelPendingStart() {}\nexport function setLiveBpm() {}\nexport function stopPlayback() {}\n',
      };
    }
    return nextLoad(url, context);
  },
});
// Node's own localStorage wants a storage file and warns without one; the
// stores read it while loading, and the session id is kept here. songStore's
// autosave reaches the timers through window.
const storage = new Map<string, string>();
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
} });
Object.defineProperty(globalThis, 'window', { configurable: true, value: globalThis });

const { buildReviewRequest, reasonFact, rulesSlotCount, useReviewStore } = await import('./reviewStore.ts');
const { useGenerationStore } = await import('./generationStore.ts');
const { useSongStore } = await import('./songStore.ts');
const { captureGenerationComparison } = await import('../engine/generationComparison.ts');

const chord = (root: string, quality: string, bass?: string): Chord =>
  ({ root, quality, bass, extensions: [], romanNumeral: '', voicing: [] });
const measure = (index: number, chords: [Chord | null, Chord | null]): Measure => ({ id: `m${index}`, index, chords });

/** A 2-bar verse, then a 2-bar chorus the A/B/C list was generated for, then two empty bars. */
function chorusSong(): Song {
  return {
    id: 'review', title: 'Verse–Chorus', key: 'C major', bpm: 100, genre: 'pop', timeSignature: [4, 4],
    measures: [
      measure(0, [chord('C', 'maj7'), chord('A', 'm7')]),
      measure(1, [chord('F', 'maj7'), chord('G', '7')]),
      measure(2, [chord('C', 'maj7'), chord('A', 'm7')]),
      measure(3, [{ ...chord('D', 'm7'), extensions: ['9'] }, chord('G', '7')]),
      measure(4, [null, null]),
      measure(5, [null, null]),
    ],
    sections: [
      { id: 'verse', type: 'verse', startMeasure: 0, length: 2 },
      { id: 'chorus', type: 'chorus', startMeasure: 2, length: 2 },
    ],
  };
}

// The run targeted the chorus from its second slot: slot 2.0 is not the request's
const TARGET: SlotAddress[] = [{ measureIndex: 2, slotIndex: 1 }, { measureIndex: 3, slotIndex: 0 }, { measureIndex: 3, slotIndex: 1 }];
const SUGGESTIONS: Suggestion[] = [
  { label: 'Option A — F1 (conservative)', chords: { 2: ['Cmaj7', 'Am7'], 3: ['Dm7', 'G7'] } },
  { label: 'Option B — F1 (balanced)', chords: { 2: ['Em7', 'Ab7'], 3: ['Dm7/F', 'G7'] } },
  { label: 'Option C — F1 (creative)', chords: { 2: ['Cmaj', 'Amin'], 3: ['Bb7', 'Cmaj'] } },
];
const RESULT: ReviewResult = {
  choice: 'C',
  reasons: [
    { fact: 'r1Roughness=0.48', factName: 'r1Roughness', value: 0.48, claim: 'The smoothest of the three.', confirmed: true, analyzerValue: 0.484 },
    { fact: 'changedSlots=1', factName: 'changedSlots', value: 1, claim: 'It keeps the original.', confirmed: false, analyzerValue: 3 },
  ],
  facts: [
    { label: 'A', outOfKeyRatio: 0, changedSlots: 1, repetitionVsPrevious: 0.75, r1Roughness: 0.745, rulesSlots: [2, 3] },
    { label: 'B', outOfKeyRatio: 0.25, changedSlots: 2, repetitionVsPrevious: 0.5, r1Roughness: 0.831, rulesSlots: [2, 3] },
    { label: 'C', outOfKeyRatio: 0.25, changedSlots: 3, repetitionVsPrevious: 0.25, r1Roughness: 0.484, rulesSlots: [2, 3] },
  ],
  provider: 'meta', model: 'muse-spark-1.3', requestId: 'req_1', costUsd: 0.0027, latencyMs: 1800, source: 'judge',
};

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

/** The chorus list on screen, as a finished Generate leaves it. */
function showList(sectionChoice: 'auto' | 'bridge' = 'auto'): void {
  useSongStore.getState().setSong(chorusSong());
  const { song, songEpoch } = useSongStore.getState();
  useGenerationStore.setState({
    suggestions: SUGGESTIONS, targetSlots: TARGET, comparison: captureGenerationComparison(song, TARGET, songEpoch),
    source: 'ai', showSuggestions: true, activeSuggestionIdx: null, loading: false, generateSectionType: sectionChoice,
  });
}

test('the request is the list as Apply would write it, with the previous section from the same offset', () => {
  const song = chorusSong();
  const request = buildReviewRequest(song, SUGGESTIONS, captureGenerationComparison(song, TARGET, 0), 'auto');
  assert.deepEqual(request, {
    key: 'C major', genre: 'pop', sectionType: 'chorus',
    // Slot 2.0 keeps the score's Cmaj7 under every candidate; the staff writes 'Cmaj' as C and 'Amin' as Am
    original: [['Cmaj7', 'Am7'], ['Dm7(9)', 'G7']],
    candidates: [
      { label: 'A', chords: [['Cmaj7', 'Am7'], ['Dm7', 'G7']] },
      { label: 'B', chords: [['Cmaj7', 'Ab7'], ['Dm7/F', 'G7']] },
      { label: 'C', chords: [['Cmaj7', 'Am'], ['Bb7', 'C']] },
    ],
    previousSection: [['Cmaj7', 'Am7'], ['Fmaj7', 'G7']],
  });
  // The chorus's second bar compares with the verse's second bar; an explicit pick wins over the section
  const secondBar: SlotAddress[] = [{ measureIndex: 3, slotIndex: 0 }, { measureIndex: 3, slotIndex: 1 }];
  const later = buildReviewRequest(song, SUGGESTIONS, captureGenerationComparison(song, secondBar, 0), 'bridge');
  assert.equal(later.sectionType, 'bridge');
  assert.deepEqual(later.previousSection, [['Fmaj7', 'G7']]);
  assert.deepEqual(later.candidates[1].chords, [['Dm7/F', 'G7']]);
  // A New-from-Song-Form list was generated for its placed section, whatever the dropdown says
  const placed = captureGenerationComparison(song, TARGET, 0, 'section');
  assert.equal(buildReviewRequest(song, SUGGESTIONS, placed, 'bridge').sectionType, 'chorus');
  // Bars outside any section: no rules under Auto and nothing to repeat
  const loose = { ...song, sections: [] };
  const plain = buildReviewRequest(loose, SUGGESTIONS, captureGenerationComparison(loose, TARGET, 0), 'auto');
  assert.equal(plain.sectionType, null);
  assert.equal(plain.previousSection, null);
});

test('a review posts the list with the session id and keeps the judge\'s verified answer', async (t) => {
  showList();
  const expected = buildReviewRequest(useSongStore.getState().song, SUGGESTIONS, useGenerationStore.getState().comparison!, 'auto');
  const fetchMock = t.mock.method(globalThis, 'fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    assert.equal(input, '/api/review/candidates');
    assert.equal(init?.method, 'POST');
    const headers = new Headers(init?.headers);
    assert.match(headers.get('X-TheArtist-Session') ?? '', /^[0-9a-f-]{36}$/);
    assert.equal(headers.get('X-TheArtist-Session'), storage.get('theartist-meta-session'));
    assert.deepEqual(JSON.parse(String(init?.body)), expected);
    return json(RESULT);
  });
  const run = useReviewStore.getState().runReview();
  assert.equal(useReviewStore.getState().loading, true);
  await run;
  const state = useReviewStore.getState();
  assert.equal(fetchMock.mock.callCount(), 1);
  assert.deepEqual(state.result, RESULT);
  assert.deepEqual(state.request, expected);
  assert.equal(state.loading, false);
  assert.equal(state.error, null);
  // A confirmed fact shows the analyzer's value and its rank; a model statement the judge's own value
  assert.deepEqual(RESULT.reasons.map((reason) => reasonFact(RESULT, reason)), ['roughness 0.484, lowest', 'changed slots 1']);
  assert.equal(rulesSlotCount(RESULT), 2);
  assert.equal(reasonFact({ ...RESULT, choice: 'A' }, { ...RESULT.reasons[1], confirmed: true }), 'changed slots 3, fewest');
  assert.equal(reasonFact(RESULT, { ...RESULT.reasons[0], factName: 'outOfKeyRatio', analyzerValue: 0.25 }), 'out-of-key 0.25');
  // Nothing was applied
  assert.equal(useGenerationStore.getState().activeSuggestionIdx, null);
  assert.equal(useSongStore.getState().song.measures[2].chords[1]?.quality, 'm7');
});

test('a failed review shows the server\'s detail with its request id and spend; a 429 its reset time', async (t) => {
  showList();
  const mock = t.mock.method(globalThis, 'fetch', async () => json({
    detail: 'meta (muse-spark-1.3) did not answer within 30s',
    error: { kind: 'timeout', message: 'meta (muse-spark-1.3) did not answer within 30s', requestId: 'req_9' },
    provider: 'meta', model: 'muse-spark-1.3', costUsd: 0.00552, latencyMs: 30000,
  }, 504));
  await useReviewStore.getState().runReview();
  assert.equal(useReviewStore.getState().error,
    'Second ear failed: meta (muse-spark-1.3) did not answer within 30s · request req_9 · $0.0055');
  assert.equal(useReviewStore.getState().result, null);
  assert.equal(useReviewStore.getState().loading, false);
  mock.mock.restore();

  const limited = t.mock.method(globalThis, 'fetch', async () => json({ detail: 'This session\'s daily Meta allowance is used '
    + 'up: $0.99 admitted today + this request\'s worst case $0.03 would pass $1.00. Allowances reset at 00:00 UTC.' }, 429));
  await useReviewStore.getState().runReview();
  assert.match(useReviewStore.getState().error ?? '', /^Second ear failed: This session's daily Meta allowance .* reset at 00:00 UTC\.$/);
  limited.mock.restore();

  const gateway = t.mock.method(globalThis, 'fetch', async () => new Response('Bad gateway', { status: 502 }));
  await useReviewStore.getState().runReview();
  assert.equal(useReviewStore.getState().error, 'Second ear failed: Server error (HTTP 502)');
  gateway.mock.restore();

  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch'); });
  await useReviewStore.getState().runReview();
  assert.match(useReviewStore.getState().error ?? '', /Could not reach the server/);
  assert.equal(useReviewStore.getState().result, null);
});

test('new suggestions, Keep current version and a replaced song drop the review; a late answer is ignored', async (t) => {
  showList();
  t.mock.method(globalThis, 'fetch', async () => json(RESULT));
  await useReviewStore.getState().runReview();
  assert.notEqual(useReviewStore.getState().result, null);
  useGenerationStore.setState({ suggestions: [...SUGGESTIONS] });  // a new run's list
  assert.deepEqual(
    [useReviewStore.getState().result, useReviewStore.getState().request, useReviewStore.getState().loading],
    [null, null, false]);

  await useReviewStore.getState().runReview();
  useGenerationStore.getState().clearSuggestions();  // Keep current version
  assert.equal(useReviewStore.getState().result, null);

  showList();
  await useReviewStore.getState().runReview();
  useSongStore.getState().clearSong();
  assert.equal(useReviewStore.getState().result, null);

  // A review still in flight when the list changes is aborted and its answer dropped
  showList();
  let signal: AbortSignal | undefined;
  t.mock.method(globalThis, 'fetch', (_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    signal = init?.signal ?? undefined;
    signal?.addEventListener('abort', () => reject(signal?.reason), { once: true });
  }));
  const pending = useReviewStore.getState().runReview();
  assert.equal(useReviewStore.getState().loading, true);
  useGenerationStore.setState({ suggestions: [...SUGGESTIONS] });
  assert.equal(signal?.aborted, true);
  await pending;
  assert.deepEqual([useReviewStore.getState().loading, useReviewStore.getState().error, useReviewStore.getState().result],
    [false, null, null]);
});

test('no review runs without a comparison, for one candidate or while a generation is in flight', async (t) => {
  const fetchMock = t.mock.method(globalThis, 'fetch', async () => json(RESULT));
  showList();
  useGenerationStore.setState({ loading: true });
  await useReviewStore.getState().runReview();
  useGenerationStore.setState({ loading: false, suggestions: SUGGESTIONS.slice(0, 1) });
  await useReviewStore.getState().runReview();
  useGenerationStore.setState({ suggestions: SUGGESTIONS, comparison: null });
  await useReviewStore.getState().runReview();
  assert.equal(fetchMock.mock.callCount(), 0);
  assert.equal(useReviewStore.getState().loading, false);
});
