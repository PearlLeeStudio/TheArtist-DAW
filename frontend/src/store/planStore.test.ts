import { test } from 'node:test';
import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import type { Chord, Measure, SectionType, Song } from '../models/types.ts';
import type { PlanOptions, PlanSectionResult, PlanTrace } from '../engine/planClient.ts';

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
// stores read it while loading. songStore's autosave reaches the timers
// through window.
const storage = new Map<string, string>();
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
} });
Object.defineProperty(globalThis, 'window', { configurable: true, value: globalThis });

const { usePlanStore } = await import('./planStore.ts');
const { useSongStore } = await import('./songStore.ts');

const chord = (root: string, quality: string): Chord => ({ root, quality, extensions: [], romanNumeral: '', voicing: [] });
const measure = (index: number, chords: [Chord | null, Chord | null]): Measure => ({ id: `m${index}`, index, chords });
const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
const options: PlanOptions = { targetBars: 16, wantOutro: true, contrast: 'medium', planner: 'meta', modelKey: 'ft_f1' };
const call = (requestId: string) => ({
  step: 'plan_song' as const, attempt: 1, provider: 'meta', model: 'muse-spark-1.3', requestId, costUsd: 0.0027, latencyMs: 1800, effort: 'medium', ok: true,
});

/** A 2-bar verse sketch in C major with two empty bars after it. */
function sketchSong(): Song {
  return {
    id: 'sketch', title: 'Verse — 2 bars', key: 'C major', bpm: 110, genre: 'pop', timeSignature: [4, 4],
    measures: [
      measure(0, [chord('C', 'maj7'), chord('A', 'm7')]),
      measure(1, [chord('D', 'm7'), chord('G', '7')]),
      measure(2, [null, null]),
      measure(3, [null, null]),
    ],
    sections: [{ id: 'verse', type: 'verse', startMeasure: 0, length: 2 }],
    autoTitle: true,
  };
}

function sectionResult(index: number, sectionType: SectionType, startMeasure: number, bars: number, extra: Partial<PlanSectionResult> = {}): PlanSectionResult {
  const chords: Record<string, [string, string]> = {};
  for (let m = startMeasure; m < startMeasure + bars; m++) chords[String(m)] = m % 2 === 0 ? ['Fmaj7', 'G7'] : ['Em7', 'Am7'];
  return {
    sectionType, title: `${sectionType} — ${bars} bars`, startMeasure, bars, chordCount: bars * 2,
    suggestions: [{ label: 'Option A', chords }], source: 'ai', modelUsed: 'ft_f1',
    cadence: 'authentic', rulesSlots: [bars * 2 - 2, bars * 2 - 1], reason: 'Lift', cites: [], regenerated: false,
    ...extra,
  };
}

function trace(overrides: Partial<PlanTrace> = {}): PlanTrace {
  return {
    status: 'ok', planner: 'meta', genre: 'pop', key: 'C major', bpm: 110, timeSignature: [4, 4], plan: { sections: [] },
    validation: [{ attempt: 1, ok: true, errors: [] }], sections: [], judge: [], calls: [], spendUsd: 0, reservedUsd: 0,
    elapsedMs: 20700, metaMs: 0, generationMs: 0, error: null, ...overrides,
  };
}

function streamResponse(parts: string[]): Response {
  const encoder = new TextEncoder();
  return new Response(new ReadableStream({
    start(controller) {
      for (const part of parts) controller.enqueue(encoder.encode(part));
      controller.close();
    },
  }), { headers: { 'Content-Type': 'text/event-stream' } });
}

/** A chorus of 8 bars and an outro of 6 after the 2-bar sketch: 16 bars. */
function completedRun(planner: 'meta' | 'rules' = 'meta') {
  const sections = [sectionResult(0, 'chorus', 2, 8), sectionResult(1, 'outro', 10, 6, { cadence: 'plagal', rulesSlots: [0, 10, 11] })];
  const final = trace({ planner, sections, calls: planner === 'meta' ? [call('req_1'), { ...call('req_2'), step: 'judge' }] : [],
    spendUsd: planner === 'meta' ? 0.0054 : 0 });
  const callFrame = planner === 'meta' ? { call: call('req_1') } : {};
  return [
    frame('plan', { attempt: 1, source: planner, plan: { sections: [] }, ...callFrame, t_ms: 1800 }),
    frame('validate', { attempt: 1, ok: true, errors: [], t_ms: 1801 }),
    frame('generate_section', { index: 0, ...sections[0], t_ms: 5000 }),
    frame('generate_section', { index: 1, ...sections[1], t_ms: 8000 }),
    ...(planner === 'meta' ? [frame('judge', { attempt: 1, decision: 'accept', targets: [], report: [], provider: 'meta', model: 'muse-spark-1.3',
      requestId: 'req_2', costUsd: 0.0027, latencyMs: 900, t_ms: 9000 })] : []),
    frame('complete', final),
  ];
}

function chipSummary() {
  return usePlanStore.getState().chips.map((chip) => [chip.label, chip.badge, chip.note, chip.ok]);
}

test('a run lands nothing until Apply, which appends the sections after the sketch; Undo restores the exact score', async (t) => {
  useSongStore.getState().setSong(sketchSong());
  const before = structuredClone(useSongStore.getState().song);
  const fetchMock = t.mock.method(globalThis, 'fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    assert.equal(input, '/api/plan/song/stream');
    const body = JSON.parse(String(init?.body));
    assert.equal(body.measures.length, 2);
    assert.deepEqual(body.measures[1].roman, ['ii7', 'V7']);
    assert.deepEqual(body.sections, [{ type: 'verse', start: 0, length: 2, label: null }]);
    assert.equal(body.targetBars, 16);
    assert.equal(body.planner, 'meta');
    assert.equal(body.modelKey, 'ft_f1');
    return streamResponse(completedRun());
  });

  await usePlanStore.getState().startPlan(options);
  const done = usePlanStore.getState();
  assert.equal(fetchMock.mock.callCount(), 1);
  assert.equal(done.status, 'done');
  assert.equal(done.planner, 'meta');
  assert.deepEqual(chipSummary(), [
    ['plan', 'Muse Spark plan', null, true],
    ['validate ok', null, null, true],
    ['Chorus · 8 bars', 'own model', 'cadence: rules (2)', true],
    ['Outro · 6 bars', 'own model', 'cadence: rules (3)', true],
    ['judge: accept', null, null, true],
  ]);
  assert.deepEqual(done.chips.map((chip) => chip.requestId), ['req_1', null, null, null, 'req_2']);
  assert.equal(done.spendUsd, 0.0054);
  assert.equal(done.sections.length, 2);
  assert.equal(done.applied, false);
  assert.deepEqual(useSongStore.getState().song, before);

  usePlanStore.getState().applyPlan();
  const song = useSongStore.getState().song;
  assert.equal(usePlanStore.getState().applied, true);
  assert.deepEqual(usePlanStore.getState().snapshot, before);
  assert.equal(song.measures.length, 16);
  assert.deepEqual(song.measures.slice(0, 2), before.measures.slice(0, 2));
  assert.deepEqual((song.sections ?? []).map((s) => [s.type, s.startMeasure, s.length, s.pending]),
    [['verse', 0, 2, undefined], ['chorus', 2, 8, undefined], ['outro', 10, 6, undefined]]);
  assert.equal(song.title, 'Verse–Chorus–Outro');
  const first = song.measures[2].chords[0];
  assert.equal(first?.root, 'F');
  assert.equal(first?.quality, 'maj7');
  assert.equal(first?.romanNumeral, 'IVmaj7');
  assert.ok((first?.voicing.length ?? 0) > 0);
  assert.deepEqual(song.measures[15].chords.map((c) => c && `${c.root}${c.quality}`), ['Em7', 'Am7']);
  // Apply is idempotent: a second call changes nothing.
  usePlanStore.getState().applyPlan();
  assert.equal(useSongStore.getState().song.measures.length, 16);

  usePlanStore.getState().undoPlan();
  assert.deepEqual(useSongStore.getState().song, before);
  assert.equal(usePlanStore.getState().applied, false);
  assert.equal(usePlanStore.getState().snapshot, null);
  // The band stays after Undo, so the sections can be applied again.
  assert.equal(usePlanStore.getState().status, 'done');
  assert.equal(JSON.parse(usePlanStore.getState().exportTrace() ?? 'null')?.status, 'ok');
  usePlanStore.getState().dismiss();
  assert.equal(usePlanStore.getState().status, 'idle');
});

test('a run that fails on the server shows a red chip with the spend so far and leaves the song untouched', async (t) => {
  useSongStore.getState().setSong(sketchSong());
  const before = structuredClone(useSongStore.getState().song);
  const failed = trace({ status: 'error', calls: [call('req_1'), { ...call('req_2'), step: 'judge', ok: false }], spendUsd: 0.0054,
    error: { kind: 'timeout', message: 'read timed out', requestId: 'req_2' } });
  t.mock.method(globalThis, 'fetch', async () => streamResponse([
    frame('plan', { attempt: 1, source: 'meta', plan: { sections: [] }, call: call('req_1'), t_ms: 1800 }),
    frame('validate', { attempt: 1, ok: false, errors: [{ code: 'total_bars', section: null, message: 'the planned bars make 28, not 32' }], t_ms: 1801 }),
    frame('error', failed),
  ]));
  await usePlanStore.getState().startPlan(options);
  const state = usePlanStore.getState();
  assert.equal(state.status, 'failed');
  assert.equal(state.error, 'read timed out');
  assert.equal(state.spendUsd, 0.0054);
  assert.deepEqual(chipSummary(), [
    ['plan', 'Muse Spark plan', null, true],
    ['validate failed (1)', null, null, false],
    ['failed: timeout', null, null, false],
  ]);
  assert.equal(state.chips[2].requestId, 'req_2');
  assert.equal(state.chips[1].message, 'total_bars: the planned bars make 28, not 32');
  assert.deepEqual(useSongStore.getState().song, before);
  usePlanStore.getState().applyPlan();
  assert.deepEqual(useSongStore.getState().song, before);
  assert.equal(usePlanStore.getState().applied, false);
  assert.equal(JSON.parse(usePlanStore.getState().exportTrace() ?? 'null')?.error?.kind, 'timeout');
  usePlanStore.getState().dismiss();
});

test('an unreachable server and a request the client refuses both fail without a trace', async (t) => {
  useSongStore.getState().setSong(sketchSong());
  const before = structuredClone(useSongStore.getState().song);
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch'); });
  await usePlanStore.getState().startPlan(options);
  assert.equal(usePlanStore.getState().status, 'failed');
  assert.match(usePlanStore.getState().error ?? '', /Could not reach the server/);
  assert.deepEqual(chipSummary(), [['failed', null, null, false]]);
  assert.equal(usePlanStore.getState().exportTrace(), null);

  useSongStore.getState().setGenre(null);
  await usePlanStore.getState().startPlan(options);
  assert.equal(usePlanStore.getState().status, 'failed');
  assert.match(usePlanStore.getState().error ?? '', /Pick a genre/);
  assert.deepEqual(useSongStore.getState().song, { ...before, genre: null });
  usePlanStore.getState().dismiss();
});

test('cancelling aborts the request, hides the band and leaves the song untouched', async (t) => {
  useSongStore.getState().setSong(sketchSong());
  const before = structuredClone(useSongStore.getState().song);
  let signal: AbortSignal | undefined;
  t.mock.method(globalThis, 'fetch', (_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    signal = init?.signal ?? undefined;
    signal?.addEventListener('abort', () => reject(signal?.reason), { once: true });
  }));
  const run = usePlanStore.getState().startPlan(options);
  assert.equal(usePlanStore.getState().status, 'running');
  usePlanStore.getState().dismiss();
  assert.equal(signal?.aborted, true);
  await run;
  assert.equal(usePlanStore.getState().status, 'idle');
  assert.deepEqual(usePlanStore.getState().chips, []);
  assert.deepEqual(useSongStore.getState().song, before);
});

test('the rules planner is labelled rules on the plan chip and the sections keep their own source', async (t) => {
  useSongStore.getState().setSong(sketchSong());
  t.mock.method(globalThis, 'fetch', async (_input: RequestInfo | URL, init?: RequestInit) => {
    assert.equal(JSON.parse(String(init?.body)).planner, 'rules');
    return streamResponse(completedRun('rules'));
  });
  await usePlanStore.getState().startPlan({ ...options, planner: 'rules' });
  assert.equal(usePlanStore.getState().status, 'done');
  assert.equal(usePlanStore.getState().planner, 'rules');
  assert.deepEqual(chipSummary(), [
    ['plan', 'rules', null, true],
    ['validate ok', null, null, true],
    ['Chorus · 8 bars', 'own model', 'cadence: rules (2)', true],
    ['Outro · 6 bars', 'own model', 'cadence: rules (3)', true],
  ]);
  assert.equal(usePlanStore.getState().spendUsd, 0);
  usePlanStore.getState().dismiss();
});

test('a section the backend\'s rule-based generator answered is labelled rules, and a regeneration replaces its entry', async (t) => {
  useSongStore.getState().setSong(sketchSong());
  const sections = [sectionResult(0, 'chorus', 2, 8, { source: 'rules', modelUsed: null }), sectionResult(1, 'outro', 10, 6)];
  const regenerated = sectionResult(1, 'outro', 10, 6, { regenerated: true });
  t.mock.method(globalThis, 'fetch', async () => streamResponse([
    frame('plan', { attempt: 1, source: 'meta', plan: { sections: [] }, call: call('req_1'), t_ms: 1 }),
    frame('validate', { attempt: 1, ok: true, errors: [], t_ms: 2 }),
    frame('generate_section', { index: 0, ...sections[0], t_ms: 3 }),
    frame('generate_section', { index: 1, ...sections[1], t_ms: 4 }),
    frame('judge', { attempt: 1, decision: 'regenerate', targets: [{ section: 1, reason: 'repeats the chorus' }], report: [],
      provider: 'meta', model: 'muse-spark-1.3', requestId: 'req_2', costUsd: 0.0027, latencyMs: 900, t_ms: 5 }),
    frame('generate_section', { index: 1, ...regenerated, t_ms: 6 }),
    frame('judge', { attempt: 2, decision: 'accept', targets: [], report: [], provider: 'meta', model: 'muse-spark-1.3',
      requestId: 'req_3', costUsd: 0.0027, latencyMs: 900, t_ms: 7 }),
    frame('complete', trace({ sections: [sections[0], regenerated], spendUsd: 0.0081 })),
  ]));
  await usePlanStore.getState().startPlan(options);
  assert.deepEqual(chipSummary().slice(2), [
    ['Chorus · 8 bars', 'rules', 'cadence: rules (2)', true],
    ['Outro · 6 bars', 'own model', 'cadence: rules (2)', true],
    ['judge: regenerate (1)', null, null, true],
    ['Outro · 6 bars · regenerated', 'own model', 'cadence: rules (2)', true],
    ['judge: accept', null, null, true],
  ]);
  assert.equal(usePlanStore.getState().sections.length, 2);
  assert.equal(usePlanStore.getState().sections[1].regenerated, true);
  usePlanStore.getState().dismiss();
});

test('a replaced song drops the run, while Undo\'s own replacement keeps it', async (t) => {
  useSongStore.getState().setSong(sketchSong());
  t.mock.method(globalThis, 'fetch', async () => streamResponse(completedRun()));
  await usePlanStore.getState().startPlan(options);
  usePlanStore.getState().applyPlan();
  usePlanStore.getState().undoPlan();
  assert.equal(usePlanStore.getState().status, 'done');
  useSongStore.getState().clearSong();
  assert.equal(usePlanStore.getState().status, 'idle');
});
