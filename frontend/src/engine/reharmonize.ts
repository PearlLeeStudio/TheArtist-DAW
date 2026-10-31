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
export interface ReharmCandidate {
  id: string;
  family: 'common_tones' | 'modal' | 'dominant';
  changes: { address: SlotAddress; before: string; after: string; commonTones: number; modes: string[] }[];
  pitchDistance: number;
  originalPitchDistance: number;
  bassMotion: number;
  originalBassMotion: number;
  mathScore: number;
  modelScore: number;
}
export interface ReharmResult {
  candidates: ReharmCandidate[];
  modelUsed: string;
  contextMeasures: number[];
  metaModel: string;
}

/** Include manually added tensions; unsupported combinations must fail rather than disappear. */
export function reharmSymbol(chord: Chord): string {
  const quality = chord.quality === 'maj' ? '' : chord.quality === 'min' ? 'm' : chord.quality;
  return `${chord.root}${quality}${chord.extensions.length ? `(${chord.extensions.join('')})` : ''}${chord.bass ? `/${chord.bass}` : ''}`;
}

/** Score content identity; transport, mixer, title and cursor edits do not invalidate a comparison. */
export function reharmFingerprint(song: Song): string {
  return JSON.stringify([song.id, song.key, song.timeSignature, song.measures.map(m => [m.id, m.chords])]);
}

export function reharmSelectionError(song: Song, slots: SlotAddress[]): string | null {
  if (!slots.length || slots.some(s => !song.measures[s.measureIndex]?.chords[s.slotIndex])) {
    return 'Select existing chords on the score to explore substitutes.';
  }
  if (slots.length > 16 || Math.max(...slots.map(s => s.measureIndex)) - Math.min(...slots.map(s => s.measureIndex)) >= 8) {
    return 'Select a passage spanning at most eight measures.';
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
    const changed = new Set<string>();
    for (const change of candidate.changes) {
      if (!change?.address || !Number.isInteger(change.address.measureIndex) || ![0, 1].includes(change.address.slotIndex)) return fail();
      const address = slotKey(change.address);
      const original = song.measures[change.address.measureIndex]?.chords[change.address.slotIndex];
      if (!allowed.has(address) || changed.has(address) || !original || change.before !== reharmSymbol(original) ||
          typeof change.after !== 'string' || change.after === change.before || !parseChordName(change.after) ||
          !Number.isInteger(change.commonTones) || change.commonTones < 0 ||
          !Array.isArray(change.modes) || !change.modes.every(m => typeof m === 'string')) return fail();
      changed.add(address);
    }
    const signature = candidate.changes.map(c => `${slotKey(c.address)}:${c.after}`).sort().join(';');
    if (signatures.has(signature)) return fail();
    signatures.add(signature);
  }
  return result;
}

export async function requestReharmonization(song: Song, slots: SlotAddress[], maxChanges: 1 | 2,
  mode: ReharmMode, modelKey: string, signal: AbortSignal): Promise<ReharmResult> {
  const response = await postJson('/api/reharmonize', {
    key: song.key, timeSignature: song.timeSignature, modelKey, maxChanges, mode,
    selectedSlots: slots,
    context: song.measures.map((m, measure) => ({ measure, chords: m.chords.map(c => c ? reharmSymbol(c) : null) })),
  }, { signal, headers: metaHeaders() });
  return validateReharmResult(await response.json(), song, slots, maxChanges);
}

/** A/B/C always starts from the captured original, including untouched voicings. */
export function reharmUpdates(comparison: GenerationComparison, song: Song, epoch: number, candidate?: ReharmCandidate) {
  const replacements = new Map(candidate?.changes.map(change => {
    const chord = parseChordName(change.after);
    if (!chord) throw new Error('The candidate contains an unreadable chord.');
    return [slotKey(change.address), {
      ...chord, romanNumeral: calculateRomanNumeral(chord, song.key), voicing: generatePianoVoicing(chord),
    }];
  }));
  return comparisonUpdates(comparison, song, epoch, replacements);
}
