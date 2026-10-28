import type { Chord, SectionType, Song } from '../models/types.ts';
import { parseChordName } from './chordParser.ts';
import { ROOTS } from './constants.ts';
import { calculateRomanNumeral } from './romanNumeral.ts';
import { isSectionType } from './songForm.ts';
import { generatePianoVoicing, QUALITY_INTERVALS } from './voicingEngine.ts';

export const MAX_SCORE_IMPORT_BYTES = 8 * 1024 * 1024;
export const MAX_SCORE_IMPORT_MEASURES = 128;
export const IMPORT_TIME_SIGNATURES = ['4/4', '3/4', '6/8', '2/4', '5/4', '7/8'] as const;
export type ScoreMime = 'image/png' | 'image/jpeg' | 'image/webp' | 'application/pdf';

export interface ScoreImportResponse {
  title: string;
  key: string | null;
  timeSignature: [number, number] | null;
  measures: Array<{ chords: string[]; sourceLabel: string; needsReview: boolean; note: string }>;
  sections: Array<{
    section: SectionType | null;
    label: string;
    startMeasure: number;
    length: number;
    basis: 'explicit' | 'inferred';
    note: string;
  }>;
  warnings: string[];
  model: string;
  requestId: string | null;
}

export interface ImportMeasureDraft {
  /** Kept even when the editable chord text is corrected. */
  originalChords: string[];
  chordText: string;
  sourceLabel: string;
  needsReview: boolean;
  note: string;
}

export interface ImportSectionDraft {
  type: SectionType | null;
  label: string;
  /** Inclusive, one-based bar numbers as editable text. */
  startBar: string;
  endBar: string;
  origin: 'explicit' | 'inferred' | 'manual';
  note: string;
}

export interface ScoreImportDraft {
  filename: string;
  title: string;
  key: string;
  timeSignature: string;
  bpm: string;
  measures: ImportMeasureDraft[];
  sections: ImportSectionDraft[];
  warnings: string[];
  model: string;
  requestId: string | null;
}

const EXTENSION_MIMES: Record<string, ScoreMime> = {
  png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp', pdf: 'application/pdf',
};

/** Check extension, reported MIME and magic bytes before previewing or sending. */
export function checkScoreFile(
  file: { name: string; type: string; size: number },
  header: Uint8Array,
): { ok: true; mimeType: ScoreMime } | { ok: false; message: string } {
  if (file.size <= 0) return { ok: false, message: 'The selected file is empty.' };
  if (file.size > MAX_SCORE_IMPORT_BYTES) return { ok: false, message: 'Choose a file no larger than 8 MiB.' };
  const extension = file.name.split('.').at(-1)?.toLowerCase() ?? '';
  const expected = EXTENSION_MIMES[extension];
  if (!expected) return { ok: false, message: 'Choose a PNG, JPEG, WebP or PDF file.' };
  if (file.type && file.type.toLowerCase() !== expected) {
    return { ok: false, message: 'The file type and filename extension do not match.' };
  }
  const starts = (bytes: number[]) => bytes.every((byte, i) => header[i] === byte);
  const actual: ScoreMime | null =
    starts([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]) ? 'image/png'
      : starts([0xff, 0xd8, 0xff]) ? 'image/jpeg'
        : starts([0x25, 0x50, 0x44, 0x46, 0x2d]) ? 'application/pdf'
          : starts([0x52, 0x49, 0x46, 0x46]) &&
            [0x57, 0x45, 0x42, 0x50].every((byte, i) => header[i + 8] === byte) ? 'image/webp' : null;
  if (actual !== expected) return { ok: false, message: 'The file contents do not match its image or PDF type.' };
  return { ok: true, mimeType: actual };
}

const object = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);
const text = (value: unknown, max: number): value is string => typeof value === 'string' && value.length <= max;

/** An unexpected API response is an error, never a partly successful import. */
export function readScoreImportResponse(raw: unknown): ScoreImportResponse {
  const invalid = () => { throw new Error('The recognition response was incomplete or invalid. Please try again.'); };
  if (!object(raw)) return invalid();
  const meter = raw.timeSignature;
  const validMeter = meter === null || (Array.isArray(meter) && meter.length === 2 &&
    Number.isInteger(meter[0]) && meter[0] >= 1 && meter[0] <= 32 && [1, 2, 4, 8, 16, 32].includes(meter[1]));
  if (!text(raw.title, 120) || !(raw.key === null || text(raw.key, 40)) || !validMeter ||
      !text(raw.model, 200) || raw.model.trim() === '' || !(raw.requestId === null || text(raw.requestId, 200)) ||
      !Array.isArray(raw.measures) || raw.measures.length > MAX_SCORE_IMPORT_MEASURES ||
      !Array.isArray(raw.sections) || raw.sections.length > 64 ||
      !Array.isArray(raw.warnings) || raw.warnings.length > 32 || !raw.warnings.every((v) => text(v, 400))) return invalid();
  for (const measure of raw.measures) {
    if (!object(measure) || !Array.isArray(measure.chords) || measure.chords.length > 16 ||
        !measure.chords.every((v) => text(v, 120)) || !text(measure.sourceLabel, 80) ||
        typeof measure.needsReview !== 'boolean' || !text(measure.note, 400)) return invalid();
  }
  for (const section of raw.sections) {
    if (!object(section) || !(section.section === null || isSectionType(section.section)) ||
        !text(section.label, 80) || !text(section.note, 400) ||
        !Number.isInteger(section.startMeasure) || !Number.isInteger(section.length) ||
        !['explicit', 'inferred'].includes(section.basis as string)) return invalid();
  }
  return raw as unknown as ScoreImportResponse;
}

export function createScoreImportDraft(response: ScoreImportResponse, filename: string): ScoreImportDraft {
  return {
    filename,
    title: response.title || filename.replace(/\.[^.]+$/, ''),
    key: response.key ?? '',
    timeSignature: response.timeSignature?.join('/') ?? '',
    bpm: '80',
    measures: response.measures.map((measure) => ({
      ...measure,
      originalChords: [...measure.chords],
      chordText: measure.chords.join(' '),
    })),
    sections: response.sections.map((section) => ({
      type: section.section,
      label: section.label,
      startBar: String(section.startMeasure + 1),
      endBar: String(section.startMeasure + section.length),
      origin: section.basis,
      note: section.note,
    })),
    warnings: [...response.warnings],
    model: response.model,
    requestId: response.requestId,
  };
}

/** Deliberately stricter than manual chord entry: no unknown suffix may
 *  silently fall back to a major triad, and parenthesized extensions are
 *  not supported by the voicing engine. The original text stays in review. */
export function parseImportedChord(symbol: string, key: string): Chord | null {
  const normalized = symbol.trim().replaceAll('♯', '#').replaceAll('♭', 'b');
  if (!/^[A-G](?:#|b)?[^\s/()]*(?:\/[A-G](?:#|b)?)?$/.test(normalized)) return null;
  const chord = parseChordName(normalized);
  if (!chord || chord.extensions.length !== 0 || !Object.hasOwn(QUALITY_INTERVALS, chord.quality)) return null;
  return { ...chord, voicing: generatePianoVoicing(chord), romanNumeral: calculateRomanNumeral(chord, key) };
}

function normalizedKey(value: string): string | null {
  const match = value.trim().replaceAll('♯', '#').replaceAll('♭', 'b').match(/^([A-G](?:#|b)?)\s+(major|minor)$/i);
  if (!match) return null;
  const root = match[1][0].toUpperCase() + match[1].slice(1);
  return ROOTS.includes(root) ? `${root} ${match[2].toLowerCase()}` : null;
}

export interface ScoreImportValidation {
  valid: boolean;
  errors: string[];
  measureErrors: string[];
  sectionErrors: string[];
  singleChordBars: number;
}

export function validateScoreImportDraft(draft: ScoreImportDraft): ScoreImportValidation {
  const errors: string[] = [];
  if (!draft.title.trim() || draft.title.trim().length > 120) errors.push('Enter a title of 1–120 characters.');
  const key = normalizedKey(draft.key);
  if (!key) errors.push('Choose a key, such as C major or A minor.');
  if (!(IMPORT_TIME_SIGNATURES as readonly string[]).includes(draft.timeSignature)) errors.push('Choose one of the time signatures supported by the editor.');
  if (!/^\d+$/.test(draft.bpm) || Number(draft.bpm) < 20 || Number(draft.bpm) > 300) errors.push('Playback tempo must be a whole number from 20 to 300 BPM.');
  if (draft.measures.length === 0 || draft.measures.length > MAX_SCORE_IMPORT_MEASURES) errors.push('The score must contain 1–128 measures.');
  if (draft.sections.length > 64) errors.push('The score can contain at most 64 sections.');

  let singleChordBars = 0;
  const measureErrors = draft.measures.map((measure) => {
    const symbols = measure.chordText.trim().split(/\s+/).filter(Boolean);
    if (symbols.length < 1 || symbols.length > 2) return 'Enter one or two chord symbols, separated by a space.';
    const unsupported = symbols.filter((symbol) => !parseImportedChord(symbol, key ?? 'C major'));
    if (unsupported.length) return `Unsupported or unreadable chord: ${unsupported.join(', ')}. Correct it before importing.`;
    if (symbols.length === 1) singleChordBars++;
    return '';
  });

  const sectionErrors = draft.sections.map((section) => {
    if (!section.label.trim() || section.label.trim().length > 80) return 'Enter a section name of 1–80 characters.';
    if (section.type !== null && !isSectionType(section.type)) return 'Choose a section type or Unknown.';
    if (!/^\d+$/.test(section.startBar) || !/^\d+$/.test(section.endBar)) return 'Enter whole bar numbers.';
    const start = Number(section.startBar);
    const end = Number(section.endBar);
    if (start < 1 || end < start || end > draft.measures.length) return `Use a range within bars 1–${draft.measures.length}.`;
    return '';
  });
  const occupied = new Map<number, number>();
  draft.sections.forEach((section, i) => {
    if (sectionErrors[i]) return;
    for (let bar = Number(section.startBar); bar <= Number(section.endBar); bar++) {
      const other = occupied.get(bar);
      if (other !== undefined) {
        sectionErrors[i] = `Overlaps section ${other + 1} at bar ${bar}.`;
        sectionErrors[other] = `Overlaps section ${i + 1} at bar ${bar}.`;
      } else occupied.set(bar, i);
    }
  });
  return { valid: errors.length === 0 && !measureErrors.some(Boolean) && !sectionErrors.some(Boolean), errors, measureErrors, sectionErrors, singleChordBars };
}

/** Called only after review and explicit confirmation. Source bytes and
 *  preview URLs are never included in the Song or its saved session. */
export function buildImportedSong(draft: ScoreImportDraft, makeId: () => string = () => crypto.randomUUID()): Song {
  const validation = validateScoreImportDraft(draft);
  if (!validation.valid) throw new Error('Correct the highlighted measures and sections before importing.');
  const key = normalizedKey(draft.key)!;
  const meter = draft.timeSignature.split('/').map(Number) as [number, number];
  return {
    id: makeId(),
    title: draft.title.trim(),
    key,
    bpm: Number(draft.bpm),
    genre: null,
    timeSignature: meter,
    autoTitle: false,
    measures: draft.measures.map((measure, index) => {
      const symbols = measure.chordText.trim().split(/\s+/);
      return {
        id: makeId(),
        index,
        chords: [parseImportedChord(symbols[0], key)!, parseImportedChord(symbols[1] ?? symbols[0], key)!],
      };
    }),
    sections: draft.sections.map((section) => ({
      id: makeId(),
      type: section.type,
      label: section.label.trim(),
      startMeasure: Number(section.startBar) - 1,
      length: Number(section.endBar) - Number(section.startBar) + 1,
      origin: section.origin,
    })).sort((a, b) => a.startMeasure - b.startMeasure),
    importSource: { filename: draft.filename, model: draft.model, requestId: draft.requestId },
  };
}
