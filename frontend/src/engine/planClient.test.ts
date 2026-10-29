import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { Chord, Measure, SectionType, Song } from '../models/types.ts';
import {
  availableTargetBars,
  buildPlanRequest,
  fetchMetaCapability,
  planBlocker,
  runPlan,
  sketchBars,
  type PlanEvent,
  type PlanOptions,
  type PlanSectionResult,
  type PlanTrace,
} from './planClient.ts';

// Node's own localStorage wants a storage file and warns without one; the
// session id (metaSession.ts) is kept here.
const storage = new Map<string, string>();
Object.defineProperty(globalThis, 'localStorage', { configurable: true, value: {
  getItem: (key: string) => storage.get(key) ?? null,
  setItem: (key: string, value: string) => { storage.set(key, value); },
} });

const chord = (root: string, quality: string): Chord => ({ root, quality, extensions: [], romanNumeral: '', voicing: [] });
const measure = (index: number, chords: [Chord | null, Chord | null]): Measure => ({ id: `m${index}`, index, chords });

// A 3-bar pop sketch in C major with a verse and an unnamed region, then an
// empty trailing bar that is not part of the sketch.
const song: Song = {
  id: 'sketch', title: 'Sketch', key: 'C major', bpm: 110.4, genre: 'pop', timeSignature: [4, 4],
  measures: [
    measure(0, [chord('C', 'maj7'), chord('A', 'm7')]),
    measure(1, [chord('D', 'm7'), { ...chord('G', '7'), bass: 'B' }]),
    measure(2, [chord('C', 'maj'), null]),
    measure(3, [null, null]),
  ],
  sections: [
    { id: 'tail', type: null, label: ' tail ', startMeasure: 2, length: 1 },
    { id: 'verse', type: 'verse', startMeasure: 0, length: 2 },
  ],
};
const options: PlanOptions = { targetBars: 32, wantOutro: true, contrast: 'medium', planner: 'meta', modelKey: 'ft_f1' };

// The backend tests' sample run (tests/test_planner.py, tests/test_plan_api.py)
const VALID_PLAN = { sections: [
  { type: 'chorus', bars: 8, cadence: 'authentic', reason: 'Lift after the ii-V in bars 1 and 3', cites: [{ bar: 1, roman: 'V7' }] },
  { type: 'verse', bars: 8, cadence: 'half', reason: 'Second verse, left open', cites: [] },
  { type: 'outro', bars: 8, cadence: 'plagal', reason: 'IV-I close like bar 6', cites: [{ bar: 6, roman: 'IVmaj7' }] },
] };
const call = (attempt: number, requestId: string, ok = true) => ({
  step: 'plan_song' as const, attempt, provider: 'meta', model: 'muse-spark-1.3', requestId, costUsd: 0.0027, latencyMs: 1800, effort: 'medium', ok,
});
const frame = (event: string, data: unknown) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;

function sectionResult(index: number, sectionType: SectionType, startMeasure: number, bars: number, extra: Partial<PlanSectionResult> = {}) {
  const chords: Record<string, [string, string]> = {};
  for (let m = startMeasure; m < startMeasure + bars; m++) chords[String(m)] = m % 2 === 0 ? ['Cmaj7', 'Am7'] : ['Dm7', 'G7'];
  return {
    index, sectionType, title: `${sectionType} — ${bars} bars`, startMeasure, bars, chordCount: bars * 2,
    suggestions: [{ label: 'Option A', chords }], source: 'ai', modelUsed: 'ft_f1',
    cadence: 'authentic', rulesSlots: [bars * 2 - 2, bars * 2 - 1], reason: 'Lift', cites: [], regenerated: false, t_ms: 100 * (index + 1),
    ...extra,
  };
}

function trace(overrides: Partial<PlanTrace> = {}): PlanTrace {
  return {
    status: 'ok', planner: 'meta', genre: 'pop', key: 'C major', bpm: 110, timeSignature: [4, 4], plan: VALID_PLAN,
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

test('the request carries the sketch up to its last used bar with the staff Roman numerals, null slots and locked sections', () => {
  const before = structuredClone(song);
  assert.equal(sketchBars(song), 3);
  const request = buildPlanRequest(song, options);
  assert.deepEqual(request, {
    genre: 'pop', key: 'C major', timeSignature: [4, 4], bpm: 110,
    measures: [
      { index: 0, chords: ['Cmaj7', 'Am7'], roman: ['Imaj7', 'vi7'] },
      { index: 1, chords: ['Dm7', 'G7/B'], roman: ['ii7', 'V7'] },
      { index: 2, chords: ['C', null], roman: ['I', null] },
    ],
    sections: [
      { type: 'verse', start: 0, length: 2, label: null },
      { type: null, start: 2, length: 1, label: 'tail' },
    ],
    targetBars: 32, wantOutro: true, contrast: 'medium', planner: 'meta', modelKey: 'ft_f1',
  });
  assert.deepEqual(song, before);
});

test('an empty score sends no sketch, and a song saved with the old bossa nova genre is sent as bossa', () => {
  const empty: Song = { ...song, genre: 'bossa nova', measures: [measure(0, [null, null]), measure(1, [null, null])], sections: [] };
  const request = buildPlanRequest(empty, { ...options, planner: 'rules', modelKey: null });
  assert.equal(sketchBars(empty), 0);
  assert.deepEqual(request.measures, []);
  assert.equal(request.genre, 'bossa');
  assert.equal(request.planner, 'rules');
  assert.equal(request.modelKey, null);
});

test('no genre, a target that leaves no room and a sketch too long to plan are refused before any request', () => {
  assert.match(planBlocker({ ...song, genre: null }) ?? '', /Pick a genre/);
  assert.throws(() => buildPlanRequest({ ...song, genre: null }, options), /Pick a genre/);
  assert.equal(planBlocker(song), null);
  assert.deepEqual(availableTargetBars(3), [16, 32, 48, 64]);
  assert.deepEqual(availableTargetBars(15), [32, 48, 64]);
  assert.deepEqual(availableTargetBars(63), []);
  const fifteenBars: Song = { ...song, sections: [{ id: 'long', type: 'verse', startMeasure: 0, length: 15 }],
    measures: Array.from({ length: 15 }, (_, i) => measure(i, [null, null])) };
  assert.throws(() => buildPlanRequest(fifteenBars, { ...options, targetBars: 16 }), /at least 17 bars/);
  const tooLong: Song = { ...song, sections: [{ id: 'long', type: 'verse', startMeasure: 0, length: 63 }],
    measures: Array.from({ length: 63 }, (_, i) => measure(i, [null, null])) };
  assert.match(planBlocker(tooLong) ?? '', /already uses 63 bars/);
});

test('a fragmented stream yields the typed events in run order and resolves with the complete trace', async (t) => {
  const final = trace({
    sections: [0, 1, 2].map((i) => sectionResult(i, 'chorus', 8 + 8 * i, 8)) as unknown as PlanSectionResult[],
    calls: [call(1, 'req_1'), call(2, 'req_2'), { ...call(1, 'req_3'), step: 'judge', effort: 'low' }], spendUsd: 0.0081,
  });
  const wire =
    frame('plan', { attempt: 1, source: 'meta', plan: VALID_PLAN, call: call(1, 'req_1'), t_ms: 1800 }) +
    frame('validate', { attempt: 1, ok: false, errors: [
      { code: 'total_bars', section: null, message: 'the sketch\'s 8 bars plus the planned 20 bars make 28, not targetBars 32' },
      { code: 'final_cadence', section: 1, message: 'the last section ends with half; the song must land on authentic or plagal' },
    ], t_ms: 1801 }) +
    frame('revise', { attempt: 2, source: 'meta', plan: VALID_PLAN, call: call(2, 'req_2'), t_ms: 3600 }) +
    frame('validate', { attempt: 2, ok: true, errors: [], t_ms: 3601 }) +
    frame('generate_section', sectionResult(0, 'chorus', 8, 8)) +
    frame('generate_section', sectionResult(1, 'verse', 16, 8, { cadence: 'half', rulesSlots: [15] })) +
    frame('generate_section', sectionResult(2, 'outro', 24, 8, { cadence: 'plagal' })) +
    frame('judge', { attempt: 1, decision: 'accept', targets: [], report: [], provider: 'meta', model: 'muse-spark-1.3',
      requestId: 'req_3', costUsd: 0.0027, latencyMs: 900, t_ms: 9000 }) +
    frame('heartbeat', { t_ms: 9001 }) +
    frame('complete', final);
  const fetchMock = t.mock.method(globalThis, 'fetch', async (input: RequestInfo | URL, init?: RequestInit) => {
    assert.equal(input, '/api/plan/song/stream');
    assert.equal(init?.method, 'POST');
    assert.equal(JSON.parse(String(init?.body)).targetBars, 32);
    return streamResponse([wire.slice(0, 23), wire.slice(23, 140), wire.slice(140, 700), wire.slice(700)]);
  });
  const events: PlanEvent[] = [];
  const result = await runPlan(buildPlanRequest(song, options), { onEvent: (event) => events.push(event) });
  assert.equal(fetchMock.mock.callCount(), 1);
  assert.deepEqual(events.map((e) => e.event),
    ['plan', 'validate', 'revise', 'validate', 'generate_section', 'generate_section', 'generate_section', 'judge', 'complete']);
  const [plan, validate, revise, , first, second] = events;
  assert.equal(plan.event, 'plan');
  if (plan.event !== 'plan') return;
  assert.equal(plan.data.call?.requestId, 'req_1');
  assert.equal(plan.data.plan.sections[0].type, 'chorus');
  assert.equal(validate.event, 'validate');
  if (validate.event !== 'validate') return;
  assert.equal(validate.data.ok, false);
  assert.deepEqual(validate.data.errors.map((issue) => issue.code), ['total_bars', 'final_cadence']);
  assert.equal(revise.event, 'revise');
  if (revise.event !== 'revise') return;
  assert.equal(revise.data.attempt, 2);
  assert.equal(first.event, 'generate_section');
  if (first.event !== 'generate_section') return;
  assert.equal(first.data.index, 0);
  assert.deepEqual(first.data.rulesSlots, [14, 15]);
  assert.deepEqual(first.data.suggestions[0].chords['8'], ['Cmaj7', 'Am7']);
  if (second.event !== 'generate_section') return;
  assert.deepEqual(second.data.rulesSlots, [15]);
  assert.deepEqual(result, final);
  assert.equal(result.status, 'ok');
  assert.equal(result.calls.length, 3);
});

test('a run that failed on the server resolves with its error trace, so the spend and request ids stay visible', async (t) => {
  const failed = trace({ status: 'error', calls: [call(1, 'req_1'), { ...call(1, 'req_2', false), step: 'judge' }], spendUsd: 0.0054,
    error: { kind: 'timeout', message: 'read timed out', requestId: 'req_2' } });
  t.mock.method(globalThis, 'fetch', async () => streamResponse([
    frame('plan', { attempt: 1, source: 'meta', plan: VALID_PLAN, call: call(1, 'req_1'), t_ms: 1800 }),
    frame('validate', { attempt: 1, ok: true, errors: [], t_ms: 1801 }),
    frame('error', failed),
  ]));
  const events: string[] = [];
  const result = await runPlan(buildPlanRequest(song, options), { onEvent: (event) => events.push(event.event) });
  assert.deepEqual(events, ['plan', 'validate', 'error']);
  assert.equal(result.status, 'error');
  assert.equal(result.error?.kind, 'timeout');
  assert.equal(result.spendUsd, 0.0054);
});

test('an error frame without a trace rejects with the server message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => streamResponse([frame('error', { detail: 'Song planning failed' })]));
  await assert.rejects(runPlan(buildPlanRequest(song, options)), /Song planning failed/);
});

test('every run sends the browser\'s session id, and a 429 shows the server\'s detail with its reset time', async (t) => {
  const sent: Headers[] = [];
  const mock = t.mock.method(globalThis, 'fetch', async (_input: RequestInfo | URL, init?: RequestInit) => {
    sent.push(new Headers(init?.headers));
    return streamResponse([frame('complete', trace())]);
  });
  await runPlan(buildPlanRequest(song, options));
  await runPlan(buildPlanRequest(song, options));
  const [first, second] = sent.map((headers) => headers.get('X-TheArtist-Session'));
  assert.match(first ?? '', /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/);
  assert.equal(second, first);
  assert.equal(storage.get('theartist-meta-session'), first);
  assert.equal(sent[0].get('Content-Type'), 'application/json');
  mock.mock.restore();
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    detail: 'This session\'s daily Meta allowance is used up: $0.95 admitted today + this request\'s worst case $0.10 '
      + 'would pass $1.00. Allowances reset at 00:00 UTC.',
  }), { status: 429, headers: { 'Content-Type': 'application/json', 'Retry-After': '3600' } }));
  await assert.rejects(runPlan(buildPlanRequest(song, options)), /allowance is used up: .* Allowances reset at 00:00 UTC\.$/);
});

test('HTTP errors keep the backend validation message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({
    detail: [{ loc: ['body', 'targetBars'], msg: 'Input should be 16, 32, 48 or 64' }],
  }), { status: 422 }));
  await assert.rejects(runPlan(buildPlanRequest(song, options)), /targetBars: Input should be 16, 32, 48 or 64/);
});

test('HTTP failures without JSON show their status', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => new Response('Backend unavailable', { status: 503 }));
  await assert.rejects(runPlan(buildPlanRequest(song, options)), /Server error \(HTTP 503\)/);
});

test('a disconnected backend rejects as unreachable', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('Failed to fetch'); });
  await assert.rejects(runPlan(buildPlanRequest(song, options)), /Could not reach the server/);
});

test('a stream that ends after progress rejects without a trace', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => streamResponse([
    frame('plan', { attempt: 1, source: 'rules', plan: VALID_PLAN, t_ms: 2 }), frame('validate', { attempt: 1, ok: true, errors: [], t_ms: 3 }),
  ]));
  await assert.rejects(runPlan(buildPlanRequest(song, options)), /ended without a result/);
});

test('an invalid section result or terminal frame rejects instead of looking like a plan', async (t) => {
  for (const [event, payload] of [
    ['generate_section', { index: 0, suggestions: 'none' }],
    ['complete', { status: 'ok' }],
    ['judge', { decision: 'maybe' }],
  ] as const) {
    const mock = t.mock.method(globalThis, 'fetch', async () => streamResponse([frame(event, payload)]));
    await assert.rejects(runPlan(buildPlanRequest(song, options)), /invalid/);
    mock.mock.restore();
  }
});

test('aborting the signal rejects with the AbortError itself', async (t) => {
  const controller = new AbortController();
  t.mock.method(globalThis, 'fetch', (_input: RequestInfo | URL, init?: RequestInit) => new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener('abort', () => reject(init.signal?.reason), { once: true });
  }));
  const pending = runPlan(buildPlanRequest(song, options), { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, (err: unknown) => err instanceof Error && err.name === 'AbortError');
});

test('the Meta capability is read from the capabilities envelope', async (t) => {
  const mock = t.mock.method(globalThis, 'fetch', async (input: RequestInfo | URL) => {
    assert.equal(input, '/api/capabilities');
    return new Response(JSON.stringify({ schemaVersion: '1.0', data: { meta: { enabled: false, configured: true, provider: 'meta', model: 'muse-spark-1.3' } } }));
  });
  assert.deepEqual(await fetchMetaCapability(), { enabled: false, configured: true });
  mock.mock.restore();
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify({ schemaVersion: '1.0', data: { tools: [] } })));
  await assert.rejects(fetchMetaCapability(), /did not report its Meta capability/);
});
