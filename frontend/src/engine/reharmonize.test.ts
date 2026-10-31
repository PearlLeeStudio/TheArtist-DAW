import { test } from 'node:test';
import assert from 'node:assert/strict';
import type { Song } from '../models/types.ts';
import { parseChordName } from './chordParser.ts';
import { reharmSymbol, validateReharmResult } from './reharmonize.ts';
import type { ReharmCandidate, ReharmResult } from './reharmonize.ts';
import { emptyReharmState, reharmActions } from './reharmonizeSession.ts';
import type { ReharmState } from './reharmonizeSession.ts';

const slots = [{ measureIndex: 1, slotIndex: 0 as const }, { measureIndex: 1, slotIndex: 1 as const }];
function score(): Song {
  return { id: 'one', title: 'Song', key: 'C major', timeSignature: [4, 4], bpm: 80, genre: null,
    measures: [['Cmaj7', 'Am7'], ['Dm7', 'G7'], ['Cmaj7', 'Cmaj7']].map((chords, index) => ({
      id: `bar-${index}`, index, chords: chords.map(c => ({ ...parseChordName(c)!, voicing: [48, 55, 60], romanNumeral: 'saved' })) as Song['measures'][0]['chords'],
    })) };
}
function candidate(id: string, slotIndex: 0 | 1, after: string): ReharmCandidate {
  return { id, family: 'common_tones', changes: [{ address: { measureIndex: 1, slotIndex },
    before: slotIndex === 0 ? 'Dm7' : 'G7', after, commonTones: 2, modes: ['dorian'] }],
  pitchDistance: .5, originalPitchDistance: .8, bassMotion: 2, originalBassMotion: 3, mathScore: 1, modelScore: -2 };
}
function result(): ReharmResult {
  return { candidates: [candidate('a', 1, 'Db7'), candidate('b', 0, 'Fm7'), candidate('c', 1, 'G9')],
    modelUsed: 'Music Transformer', metaModel: 'muse-spark-1.3', contextMeasures: [0, 1, 2] };
}
function harness(requester: () => Promise<ReharmResult> = async () => result()) {
  let song = score();
  let epoch = 1;
  let writes = 0;
  let stops = 0;
  let state: ReharmState;
  const actions = reharmActions({
    read: () => ({ song, songEpoch: epoch, selectedSlots: slots }),
    stop: () => { stops++; },
    clearGeneration: () => undefined,
    write: updates => {
      writes++;
      song = { ...song, measures: song.measures.map((m, index) => {
        const chords = [...m.chords] as typeof m.chords;
        for (const u of updates) if (u.address.measureIndex === index) chords[u.address.slotIndex] = u.chord;
        return { ...m, chords };
      }) };
    },
  }, () => state, patch => { state = { ...state, ...patch }; }, requester);
  state = { ...emptyReharmState, ...actions };
  return { actions, state: () => state, song: () => song, writes: () => writes, stops: () => stops,
    edit: (edit: (s: Song) => void) => { song = structuredClone(song); edit(song); },
    replace: () => { song = score(); epoch++; actions.close(); } };
}

test('request offers three candidates without changing the score; A/B/A/Original all remain available', async () => {
  const h = harness();
  const original = structuredClone(h.song());
  await h.actions.run('ft_f1', 1, 'auto');
  assert.equal(h.writes(), 0);
  const choices = h.state().result;
  h.actions.preview(0);
  assert.equal(reharmSymbol(h.song().measures[1].chords[1]!), 'Db7');
  h.actions.preview(1);
  assert.deepEqual(h.song().measures[1].chords[1], original.measures[1].chords[1]);
  assert.equal(reharmSymbol(h.song().measures[1].chords[0]!), 'Fm7');
  h.actions.preview(0);
  assert.deepEqual(h.song().measures[1].chords[0], original.measures[1].chords[0]);
  h.actions.preview(null);
  assert.deepEqual(h.song(), original);
  assert.equal(h.state().result, choices);
  assert.equal(h.state().result?.candidates.length, 3);
  assert.equal(h.stops(), 4);
});

test('closing comparison keeps the chosen score, with no automatic disappearance on preview', async () => {
  const h = harness();
  await h.actions.run('ft_f1', 1, 'auto');
  h.actions.preview(2);
  assert.equal(h.state().result?.candidates.length, 3);
  const chosen = structuredClone(h.song());
  h.actions.close();
  assert.equal(h.state().result, null);
  assert.deepEqual(h.song(), chosen);
});

test('outside edits block stale candidates but original restores without touching the outside edit', async () => {
  const h = harness();
  const original = structuredClone(h.song());
  await h.actions.run('ft_f1', 1, 'auto');
  h.actions.preview(0);
  h.edit(s => { s.measures[2].chords[0] = parseChordName('Ab'); });
  h.actions.preview(1);
  assert.equal(h.writes(), 1);
  assert.match(h.state().error!, /surrounding/);
  h.actions.preview(null);
  assert.deepEqual(h.song().measures[1], original.measures[1]);
  assert.equal(reharmSymbol(h.song().measures[2].chords[0]!), 'Ab');
  assert.equal(h.state().result?.candidates.length, 3);
});

test('target edits are never overwritten by a stale comparison', async () => {
  const h = harness();
  await h.actions.run('ft_f1', 1, 'auto');
  h.actions.preview(0);
  h.edit(s => { s.measures[1].chords[1] = parseChordName('E7'); });
  h.actions.preview(null);
  assert.equal(reharmSymbol(h.song().measures[1].chords[1]!), 'E7');
  assert.equal(h.writes(), 1);
});

test('late completion after a replaced song cannot reopen or edit it', async () => {
  let resolve!: (r: ReharmResult) => void;
  const h = harness(() => new Promise(r => { resolve = r; }));
  const pending = h.actions.run('ft_f1', 1, 'auto');
  h.replace();
  resolve(result());
  await pending;
  assert.equal(h.state().result, null);
  assert.equal(h.writes(), 0);
});

test('an edit while a request runs rejects the result without mutating that edit', async () => {
  let resolve!: (r: ReharmResult) => void;
  const h = harness(() => new Promise(r => { resolve = r; }));
  const pending = h.actions.run('ft_f1', 1, 'auto');
  h.edit(s => { s.measures[0].chords[0] = parseChordName('E7'); });
  resolve(result());
  await pending;
  assert.equal(h.state().result, null);
  assert.match(h.state().error!, /score changed/);
  assert.equal(h.writes(), 0);
});

test('reject malformed, duplicate, excess, out-of-selection and mismatched-origin patches as a whole', () => {
  assert.equal(validateReharmResult(result(), score(), slots, 1).candidates.length, 3);
  for (const mutate of [
    (r: ReharmResult) => { r.candidates[0].changes[0].address.measureIndex = 0; },
    (r: ReharmResult) => { r.candidates[0].changes[0].before = 'wrong'; },
    (r: ReharmResult) => { r.candidates[0].changes.push(r.candidates[1].changes[0]); },
    (r: ReharmResult) => { r.candidates[1] = structuredClone(r.candidates[0]); },
    (r: ReharmResult) => { r.candidates[0].modelScore = NaN; },
  ]) {
    const r = result(); mutate(r);
    assert.throws(() => validateReharmResult(r, score(), slots, 1), /invalid reharmonization/);
  }
});

test('manual tension and explicit bass are preserved in the search request symbol', () => {
  assert.equal(reharmSymbol({ ...parseChordName('G7/B')!, extensions: ['b9'] }), 'G7(b9)/B');
});
