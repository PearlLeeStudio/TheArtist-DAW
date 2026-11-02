import type { Chord, Song, SlotAddress } from '../models/types.ts';
import { parseChordName } from './chordParser.ts';
import { calculateRomanNumeral } from './romanNumeral.ts';
import { generatePianoVoicing } from './voicingEngine.ts';
import { comparisonUpdates, slotKey } from './generationComparison.ts';
import type { GenerationComparison } from './generationComparison.ts';
import { postJson } from './httpClient.ts';
import { metaHeaders } from './metaSession.ts';

export const REHARM_MODES = ['auto', 'ionian', 'dorian', 'phrygian', 'lydian', 'mixolydian', 'aeolian', 'locrian'] as const;
export type ReharmMode = typeof REHARM_MODES[number];
export const REHARM_CHANGE_LIMITS = [1, 2, 3, 4] as const;
export type ReharmChangeLimit = typeof REHARM_CHANGE_LIMITS[number];
export interface ReharmCandidate {
  id: string;
  family: 'common_tones' | 'modal' | 'dominant';
  changes: { address: SlotAddress; before: string; after: string; commonTones: number; modes: string[]; conventions?: string[] }[];
  pitchDistance: number;
  originalPitchDistance: number;
  bassMotion: number;
  originalBassMotion: number;
  mathScore: number;
  conventionScore?: number;
  modelScore: number;
}
/** Why the server picked the three without Meta: switched off, no key, paused, or the Meta allowance used up. */
export type ReharmMetaUnavailable = 'disabled' | 'unconfigured' | 'paused' | 'limit';
const REHARM_META_UNAVAILABLE: Record<ReharmMetaUnavailable, string> = {
  disabled: 'Meta is off on this server',
  unconfigured: 'No Meta key is configured on this server',
  paused: 'Meta is paused on this server',
  limit: 'The Meta allowance is used up for today',
};
export interface ReharmResult {
  candidates: ReharmCandidate[];
  modelUsed: string;
  contextMeasures: number[];
  /** 'not used' when the three were picked without Meta. */
  metaModel: string;
  modelApproximations?: { address: SlotAddress; original: string; scoredAs: string }[];
  /** The Meta call record of this search, listed under Run details. */
  requestIds?: string[];
  costUsd?: number;
  toolCalls?: string[];
  /** meta (or absent, from an older server): Meta chose the three. local: the server picked the best
   *  Music Transformer score of each substitution family because Meta could not take the request. */
  selection?: 'meta' | 'local';
  metaUnavailable?: ReharmMetaUnavailable | null;
}

/** The visible note of a result picked without Meta; null when Meta chose it. */
export function reharmLocalNote(result: ReharmResult): string | null {
  if (result.selection !== 'local') return null;
  const why = result.metaUnavailable ? REHARM_META_UNAVAILABLE[result.metaUnavailable] : 'Meta was not available';
  return `${why}, so the best-scoring alternative of each substitution family was picked without Meta.`;
}

/** Include manually added tensions; unsupported combinations must fail rather than disappear. */
export function reharmSymbol(chord: Chord): string {
  const quality = chord.quality === 'maj' ? '' : chord.quality === 'min' ? 'm' : chord.quality;
  return `${chord.root}${quality}${chord.extensions.length ? `(${chord.extensions.join(',')})` : ''}${chord.bass ? `/${chord.bass}` : ''}`;
}

/** Score content identity; transport, mixer, title and cursor edits do not invalidate a comparison. */
export function reharmFingerprint(song: Song): string {
  return JSON.stringify([song.id, song.key, song.timeSignature, song.measures.map(m => [m.id, m.chords])]);
}

/** Dragged passages can include empty half-bars; only written chords are targets. */
export function reharmTargets(song: Song, slots: SlotAddress[]): SlotAddress[] {
  return slots.filter(s => !!song.measures[s.measureIndex]?.chords[s.slotIndex]);
}

export function reharmSelectionError(song: Song, slots: SlotAddress[]): string | null {
  if (!slots.length) return 'Select a passage on the score to explore substitutes.';
  if (slots.some(s => !song.measures[s.measureIndex] || ![0, 1].includes(s.slotIndex))) {
    return 'The selected passage changed. Select it again on the score.';
  }
  if (slots.length > 16 || Math.max(...slots.map(s => s.measureIndex)) - Math.min(...slots.map(s => s.measureIndex)) >= 8) {
    return 'Select a passage spanning at most eight measures.';
  }
  if (!reharmTargets(song, slots).length) {
    return 'This selection has no chord symbols yet. Add or generate chords before reharmonizing.';
  }
  return null;
}

/** Validate every patch before any of the three choices can touch the score. */
export function validateReharmResult(value: unknown, song: Song, slots: SlotAddress[], maxChanges: number): ReharmResult {
  const result = value as ReharmResult | null;
  const fail = () => { throw new Error('The server returned invalid reharmonization candidates. The score was kept.'); };
  if (!result || !Array.isArray(result.candidates) || result.candidates.length !== 3 ||
      typeof result.modelUsed !== 'string' || typeof result.metaModel !== 'string' ||
      !Array.isArray(result.contextMeasures) || !result.contextMeasures.every(Number.isInteger)) return fail();
  if (result.modelApproximations !== undefined && (!Array.isArray(result.modelApproximations) ||
      !result.modelApproximations.every(a => a && typeof a.original === 'string' && typeof a.scoredAs === 'string' &&
        Number.isInteger(a.address?.measureIndex) && [0, 1].includes(a.address?.slotIndex)))) return fail();
  const strings = (list: unknown) => Array.isArray(list) && list.every(item => typeof item === 'string');
  if ((result.requestIds !== undefined && !strings(result.requestIds)) ||
      (result.toolCalls !== undefined && !strings(result.toolCalls)) ||
      (result.costUsd !== undefined && !(Number.isFinite(result.costUsd) && result.costUsd >= 0))) return fail();
  if ((result.selection !== undefined && result.selection !== 'meta' && result.selection !== 'local') ||
      (result.metaUnavailable !== undefined && result.metaUnavailable !== null &&
        !Object.hasOwn(REHARM_META_UNAVAILABLE, result.metaUnavailable))) return fail();
  const allowed = new Set(slots.map(slotKey));
  const ids = new Set<string>();
  const signatures = new Set<string>();
  for (const candidate of result.candidates) {
    if (!candidate || typeof candidate.id !== 'string' || !candidate.id || ids.has(candidate.id) ||
        !['common_tones', 'modal', 'dominant'].includes(candidate.family) ||
        !Array.isArray(candidate.changes) || candidate.changes.length < 1 || candidate.changes.length > maxChanges ||
        ![candidate.pitchDistance, candidate.originalPitchDistance, candidate.bassMotion,
          candidate.originalBassMotion, candidate.mathScore, candidate.modelScore].every(Number.isFinite)) return fail();
    ids.add(candidate.id);
    if (candidate.conventionScore !== undefined && !Number.isFinite(candidate.conventionScore)) return fail();
    const changed = new Set<string>();
    for (const change of candidate.changes) {
      if (!change?.address || !Number.isInteger(change.address.measureIndex) || ![0, 1].includes(change.address.slotIndex)) return fail();
      const address = slotKey(change.address);
      const original = song.measures[change.address.measureIndex]?.chords[change.address.slotIndex];
      if (!allowed.has(address) || changed.has(address) || !original || change.before !== reharmSymbol(original) ||
          typeof change.after !== 'string' || change.after === change.before || !parseChordName(change.after) ||
          !Number.isInteger(change.commonTones) || change.commonTones < 0 ||
          !Array.isArray(change.modes) || !change.modes.every(m => typeof m === 'string') ||
          (change.conventions !== undefined && (!Array.isArray(change.conventions) ||
            !change.conventions.every(reason => typeof reason === 'string' && reason.length <= 100)))) return fail();
      changed.add(address);
    }
    const signature = candidate.changes.map(c => `${slotKey(c.address)}:${c.after}`).sort().join(';');
    if (signatures.has(signature)) return fail();
    signatures.add(signature);
  }
  return result;
}

/** Run details for a finished search: Meta's tool calls (or the pick made without Meta), the scoring
 *  model, then request ids, cost and time. */
export function reharmRunDetails(result: ReharmResult, elapsedMs: number | null): string[] {
  const calls = result.toolCalls?.length ? result.toolCalls.join(' → ') : 'tool calls not reported';
  const record = [
    result.requestIds?.length ? result.requestIds.join(', ') : null,
    result.costUsd === undefined ? null : `$${result.costUsd.toFixed(4)}`,
    elapsedMs === null ? null : `${(elapsedMs / 1000).toFixed(1)} s`,
  ].filter((part): part is string => part !== null);
  const local = result.selection === 'local';
  return [
    ...(local
      ? ['Picked without Meta: the best context score of each substitution family',
        ...(result.toolCalls?.length ? [`Meta search before it stopped · ${calls}`] : [])]
      : [`Meta ${result.metaModel} · ${calls}`]),
    `Scored against the surrounding bars by ${result.modelUsed}`,
    ...(record.length ? [record.join(' · ')] : []),
  ];
}

/** Bars sent on each side of the passage: the search and the model read at most
 *  eight, so this covers them with a margin while a 512-bar score stays small. */
export const REHARM_CONTEXT_REACH = 16;

/** The bars around the selected passage, with their score measure numbers, so a
 *  long imported score is not sent whole; the backend accepts any consecutive window. */
export function reharmContext(song: Song, slots: SlotAddress[]) {
  const measures = slots.map(s => s.measureIndex);
  const first = Math.max(0, Math.min(...measures) - REHARM_CONTEXT_REACH);
  const last = Math.min(song.measures.length - 1, Math.max(...measures) + REHARM_CONTEXT_REACH);
  return song.measures.slice(first, last + 1).map((m, offset) =>
    ({ measure: first + offset, chords: m.chords.map(c => c ? reharmSymbol(c) : null) }));
}

export async function requestReharmonization(song: Song, slots: SlotAddress[], maxChanges: ReharmChangeLimit,
  mode: ReharmMode, modelKey: string, signal: AbortSignal): Promise<ReharmResult> {
  const problem = reharmSelectionError(song, slots);
  if (problem) throw new Error(problem);
  const targets = reharmTargets(song, slots);
  const deadline = AbortSignal.timeout(110_000);
  try {
    const response = await postJson('/api/reharmonize', {
      key: song.key, timeSignature: song.timeSignature, modelKey, maxChanges, mode,
      selectedSlots: targets,
      context: reharmContext(song, targets),
    }, { signal: AbortSignal.any([signal, deadline]), headers: metaHeaders() });
    return validateReharmResult(await response.json(), song, targets, maxChanges);
  } catch (error) {
    if (deadline.aborted && !signal.aborted) {
      throw new Error('The reharmonization search exceeded 110 seconds. Your score is unchanged. Please try again.', { cause: error });
    }
    throw error;
  }
}

/** Toggle an entire alternative; the newest selection replaces overlapping alternatives. */
export function toggleReharmSelection(selected: readonly number[], index: number, candidates: ReharmCandidate[]): number[] {
  if (selected.includes(index)) return selected.filter(i => i !== index);
  const slots = new Set(candidates[index].changes.map(change => slotKey(change.address)));
  return [...selected.filter(i => !candidates[i].changes.some(change => slots.has(slotKey(change.address)))), index].sort();
}

/** Selected alternatives always start from Origin, including untouched voicings. */
export function reharmUpdates(comparison: GenerationComparison, song: Song, epoch: number, candidates: ReharmCandidate[] = []) {
  const changes = candidates.flatMap(candidate => candidate.changes);
  if (new Set(changes.map(c => slotKey(c.address))).size !== changes.length) {
    throw new Error('Choose only one alternative for each chord position.');
  }
  const replacements = new Map(changes.map(change => {
    const chord = parseChordName(change.after);
    if (!chord) throw new Error('The candidate contains an unreadable chord.');
    return [slotKey(change.address), {
      ...chord, romanNumeral: calculateRomanNumeral(chord, song.key), voicing: generatePianoVoicing(chord),
    }];
  }));
  return comparisonUpdates(comparison, song, epoch, replacements);
}
