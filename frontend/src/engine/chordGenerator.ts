import type { Chord, Measure, Song, SlotAddress, SectionType } from '../models/types';
import { NOTE_VALUES, VALUE_TO_FLAT_NAME, MAJOR_SCALE_INTERVALS, MINOR_SCALE_INTERVALS } from './constants';
import { parseChordName, chordToString } from './chordParser';
import { readSSEFrames } from './sseStream';

export interface TheoryExplanation {
  chord_a: string;
  chord_b: string;
  concept: string;
  explanation: string;
  chapter: string;
  section: string;
  page_start: number;
  page_end: number;
}

export interface Suggestion {
  label: string;
  chords: Record<string, [string, string]>;
  explanations?: TheoryExplanation[] | null;
}

/** Who answered: 'rules' = the model was unavailable and the backend's
 *  rule-based generator answered; 'offline' = the backend could not be
 *  used and the local random fallback answered. */
export type SuggestionSource = 'ai' | 'rules' | 'ai+rules' | 'offline';

export interface GenerateResult {
  suggestions: Suggestion[];
  source: SuggestionSource | null;
}

/** Body of POST /api/generate/section(/stream). */
export interface SectionGenerateParams {
  song: Song;
  sectionType: SectionType;
  /** Even, 2..128 (two chord slots per measure). */
  chordCount: number;
  /** First measure of the new section; the measures before it go as context. */
  startMeasure: number;
  modelKey?: string | null;
}

/** Result of /api/generate/section(/stream). `suggestions[i].chords` is keyed
 *  by absolute measure index, startMeasure .. startMeasure + bars - 1. */
export interface SectionGenerateResponse {
  sectionType: SectionType;
  title: string;
  startMeasure: number;
  bars: number;
  chordCount: number;
  suggestions: Suggestion[];
  source: 'ai' | 'rules';
  modelUsed: string | null;
  elapsed_ms?: number;
}

const GENRE_QUALITIES: Record<string, string[]> = {
  jazz:         ['maj7', 'm7', '7', 'm7b5', 'dim7', '9', 'm9', '13', '6', 'mMaj7', 'sus4', '11'],
  pop:          ['maj', 'min', '7', 'sus4', 'sus2', 'add9', 'maj7', 'm7'],
  blues:        ['7', '9', 'm7', '13', 'dim', 'maj'],
  bossa:        ['maj7', 'm7', '7', '6', 'm6', 'dim7', '9', 'maj9'],
  'bossa nova': ['maj7', 'm7', '7', '6', 'm6', 'dim7', '9', 'maj9'],
  default:      ['maj', 'min', '7', 'maj7', 'm7', 'dim', 'aug', 'sus4'],
};

function pickRandom<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function getDiatonicRoots(keyRoot: string, isMinor: boolean): string[] {
  const rootVal = NOTE_VALUES[keyRoot] ?? 0;
  const intervals = isMinor ? MINOR_SCALE_INTERVALS : MAJOR_SCALE_INTERVALS;
  return intervals.map(i => VALUE_TO_FLAT_NAME[(rootVal + i) % 12]);
}

/**
 * Local random fallback — used when backend is unreachable.
 */
export function generateRandomChords(
  slots: SlotAddress[],
  key: string,
  genre: string | null,
): Map<string, Chord> {
  const qualities = GENRE_QUALITIES[genre ?? ''] ?? GENRE_QUALITIES.default;
  const keyRoot = key.split(' ')[0];
  const diatonicRoots = getDiatonicRoots(keyRoot, key.includes('minor'));

  const result = new Map<string, Chord>();
  for (const slot of slots) {
    const root = Math.random() < 0.7 ? pickRandom(diatonicRoots) : pickRandom(VALUE_TO_FLAT_NAME);
    result.set(`${slot.measureIndex}-${slot.slotIndex}`, {
      root,
      quality: pickRandom(qualities),
      romanNumeral: '',
      voicing: [],
      extensions: [],
    });
  }
  return result;
}

/** Live progress update from the streaming generate endpoint. */
export type GeneratePhase =
  | { name: 'model_load'; label: string }
  | { name: 'composing'; label: string; step: number; total: number; creativity: string }
  | { name: 'ranking'; label: string }
  | { name: 'voicing'; label: string }
  | { name: 'explaining'; label: string }
  | { name: 'complete'; label: string };

function _contextMeasures(measures: Measure[]) {
  return measures.map((m, i) => ({
    measure: i,
    chords: m.chords.map(c => c ? chordToString(c) : null),
  }));
}

/** Request fields shared by every generate endpoint. bpm is an int on the
 *  backend, and SongSettings accepts decimals. */
function _songFields(song: Song) {
  return {
    key: song.key,
    bpm: Math.round(song.bpm),
    genre: song.genre,
    timeSignature: song.timeSignature,
  };
}

function _buildBody(
  song: Song,
  selectedSlots: SlotAddress[],
  sectionType: SectionType | null,
  modelKey?: string,
) {
  const selectedMeasures = [...new Set(selectedSlots.map(s => s.measureIndex))];
  return {
    ..._songFields(song),
    context: _contextMeasures(song.measures),
    selectedMeasures,
    sectionType,
    modelKey,
  };
}

function _toSource(value: unknown): SuggestionSource | null {
  return value === 'ai' || value === 'rules' || value === 'ai+rules' ? value : null;
}

/**
 * Readable text for an error `detail` from the backend: a plain string
 * (HTTPException, SSE 'error' event) or FastAPI's 422 list of
 * `{ loc, msg }` validation errors, e.g. "chordCount: Input should be
 * less than or equal to 128".
 */
function _formatErrorDetail(detail: unknown): string | null {
  if (typeof detail === 'string') return detail.trim() || null;
  if (!Array.isArray(detail)) return null;
  const parts = detail.map((item) => {
    if (typeof item === 'string') return item;
    if (typeof item !== 'object' || item === null) return '';
    const { loc, msg } = item as { loc?: unknown; msg?: unknown };
    const field = Array.isArray(loc) ? loc.filter((p) => p !== 'body').join('.') : '';
    const text = typeof msg === 'string' ? msg : '';
    return field && text ? `${field}: ${text}` : text;
  }).filter(Boolean);
  return parts.length > 0 ? parts.join('; ') : null;
}

async function _describeHttpError(res: Response): Promise<string> {
  let detail: string | null = null;
  try {
    const body = (await res.json()) as { detail?: unknown; error?: unknown } | null;
    detail = _formatErrorDetail(body?.detail) ?? _formatErrorDetail(body?.error);
  } catch {
    // not a JSON body
  }
  if (detail) return detail;
  return res.status >= 500
    ? `Server error (HTTP ${res.status})`
    : `Request failed (HTTP ${res.status})`;
}

function _offlineFallback(song: Song, selectedSlots: SlotAddress[]): Suggestion[] {
  const selectedMeasures = [...new Set(selectedSlots.map(s => s.measureIndex))];
  const fallback = generateRandomChords(selectedSlots, song.key, song.genre);
  const chords: Record<string, [string, string]> = {};
  for (const mIdx of selectedMeasures) {
    const s0 = fallback.get(`${mIdx}-0`);
    const s1 = fallback.get(`${mIdx}-1`);
    chords[String(mIdx)] = [
      s0 ? chordToString(s0) : 'Cmaj7',
      s1 ? chordToString(s1) : 'Cmaj7',
    ];
  }
  return [{ label: 'Random (offline)', chords }];
}

/**
 * Call backend /api/generate/stream and stream progress events to `onPhase`
 * while yielding the final suggestions. Falls back to local random generation
 * on network / parse error. When `onPhase` is omitted, behaves identically
 * to the non-streaming path (just discards events).
 *
 * `sectionType` is sent as given — null means no song-form rules.
 */
export async function generateChords(
  song: Song,
  selectedSlots: SlotAddress[],
  sectionType: SectionType | null,
  modelKey?: string,
  onPhase?: (phase: GeneratePhase) => void,
): Promise<GenerateResult> {
  const body = _buildBody(song, selectedSlots, sectionType, modelKey);
  try {
    const res = await fetch('/api/generate/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`API error: ${res.status}`);

    let final: GenerateResult | null = null;
    for await (const { event, data } of readSSEFrames<Record<string, unknown>>(res)) {
      if (event === 'result') {
        const sugs = (data as { suggestions?: unknown }).suggestions;
        if (!Array.isArray(sugs)) throw new Error('Invalid result payload');
        final = { suggestions: sugs as Suggestion[], source: _toSource(data.source) };
      } else if (event === 'error') {
        throw new Error(_formatErrorDetail(data.detail) || 'stream error');
      } else if (onPhase) {
        onPhase({ name: event, ...data } as GeneratePhase);
      }
    }

    if (!final) throw new Error('Stream closed without result event');
    return final;
  } catch (err) {
    console.warn('Chord generation failed, using fallback:', err);
    return { suggestions: _offlineFallback(song, selectedSlots), source: 'offline' };
  }
}

/**
 * Generate a new song-form section: POST /api/generate/section/stream with
 * the measures before `startMeasure` as context, forward phase events to
 * `onPhase`, and resolve with the server's SectionGenerateResponse.
 *
 * No offline fallback here: a non-2xx response (FastAPI 422 included), an
 * 'error' event or a stream that ends without a result rejects with the
 * server's message. Aborting `signal` rejects with the AbortError.
 */
export async function generateSection(
  params: SectionGenerateParams,
  onPhase?: (phase: GeneratePhase) => void,
  signal?: AbortSignal,
): Promise<SectionGenerateResponse> {
  const { song, sectionType, chordCount, startMeasure, modelKey } = params;
  const body = {
    ..._songFields(song),
    sectionType,
    chordCount,
    context: _contextMeasures(song.measures.slice(0, startMeasure)),
    modelKey: modelKey ?? null,
  };

  let res: Response;
  try {
    res = await fetch('/api/generate/section/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (signal?.aborted) throw err;
    throw new Error('Could not reach the server', { cause: err });
  }
  if (!res.ok) throw new Error(await _describeHttpError(res));

  let result: SectionGenerateResponse | null = null;
  for await (const { event, data } of readSSEFrames<Record<string, unknown>>(res)) {
    if (event === 'result') {
      if (!Array.isArray(data.suggestions)) throw new Error('The server sent an invalid section result');
      result = data as unknown as SectionGenerateResponse;
    } else if (event === 'error') {
      throw new Error(_formatErrorDetail(data.detail) ?? 'The server reported an error');
    } else if (onPhase) {
      onPhase({ name: event, ...data } as GeneratePhase);
    }
  }
  if (!result) throw new Error('The stream ended without a result');
  return result;
}

/**
 * Parse a suggestion's chord names into Chord objects and apply to slots.
 */
export function parseSuggestionChords(
  suggestion: Suggestion,
): Map<string, Chord> {
  const result = new Map<string, Chord>();
  for (const [mIdx, [name0, name1]] of Object.entries(suggestion.chords)) {
    const c0 = parseChordName(name0);
    const c1 = parseChordName(name1);
    if (c0) result.set(`${mIdx}-0`, c0);
    if (c1) result.set(`${mIdx}-1`, c1);
  }
  return result;
}
