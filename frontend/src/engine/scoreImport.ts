import type { Chord, SectionType, Song, ScoreImportMode, ImportedChordBasis, ImportConfidence, ScoreAnalysisSource } from '../models/types.ts';
import { parseChordName } from './chordParser.ts';
import { normalizeKeySignature } from './keySignatures.ts';
import { calculateRomanNumeral } from './romanNumeral.ts';
import { isSectionType } from './songForm.ts';
import { generatePianoVoicing, QUALITY_INTERVALS } from './voicingEngine.ts';

export const MAX_SCORE_IMPORT_BYTES = 8 * 1024 * 1024;
export const MAX_SCORE_IMPORT_MEASURES = 512;
export const IMPORT_TIME_SIGNATURES = ['4/4', '3/4', '6/8', '2/4', '5/4', '7/8'] as const;
export type ScoreMime = 'image/png' | 'image/jpeg' | 'image/webp' | 'application/pdf';
export type ScoreImportEngine = 'local' | 'meta' | 'auto';

interface ScoreMeasureAnalysis {
  notes?: string[];
  writtenNotes?: string[];
  bassNotes?: string[];
  noChord?: boolean;
  timeSignature?: [number, number] | null;
  analysisSource?: 'local' | 'meta' | null;
  model?: string | null;
  requestId?: string | null;
}

export interface ScoreImportResponse {
  mode?: ScoreImportMode;
  analysisSource?: ScoreAnalysisSource;
  title: string;
  key: string | null;
  timeSignature: [number, number] | null;
  measures: Array<ScoreMeasureAnalysis & { chords: string[]; sourceLabel: string; needsReview: boolean; note: string; chordBasis?: ImportedChordBasis; confidence?: ImportConfidence }>;
  sections: Array<{
    section: SectionType | null;
    label: string;
    startMeasure: number;
    length: number;
    basis: 'explicit' | 'inferred';
    note: string;
  }>;
  warnings: string[];
  model: string | null;
  requestId: string | null;
}

export interface ImportMeasureDraft {
  /** Kept even when the editable chord text is corrected. */
  originalChords: string[];
  chordText: string;
  sourceLabel: string;
  needsReview: boolean;
  note: string;
  chordBasis: ImportedChordBasis;
  confidence: ImportConfidence;
  sourceMeasureIndex: number;
  analysisSource: 'local' | 'meta';
  model: string | null;
  requestId: string | null;
  notes: string[];
  writtenNotes: string[];
  bassNotes: string[];
  originalNoChord: boolean;
  timeSignature: [number, number] | null;
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
  mode: ScoreImportMode;
  analysisSource: ScoreAnalysisSource;
  filename: string;
  title: string;
  key: string;
  timeSignature: string;
  bpm: string;
  measures: ImportMeasureDraft[];
  sections: ImportSectionDraft[];
  warnings: string[];
  model: string | null;
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
const validMeter = (meter: unknown): boolean => meter === null || (Array.isArray(meter) && meter.length === 2 &&
  Number.isInteger(meter[0]) && meter[0] >= 1 && meter[0] <= 32 && [1, 2, 4, 8, 16, 32].includes(meter[1]));

/** Local is the default. External processing requires the caller's explicit choice. */
export function scoreImportRequestBody(filename: string, mimeType: ScoreMime, dataBase64: string, mode: ScoreImportMode, allowMeta = false) {
  return { filename, mimeType, dataBase64, mode, engine: (allowMeta ? 'auto' : 'local') as ScoreImportEngine };
}

export function isNoChordText(value: string): boolean {
  return /^N\.?C\.?$/i.test(value.trim());
}

/** An unexpected API response is an error, never a partly successful import. */
export function readScoreImportResponse(raw: unknown, expectedMode: ScoreImportMode = 'chord_symbols', expectedEngine: ScoreImportEngine = 'auto'): ScoreImportResponse {
  const invalid = () => { throw new Error('The recognition response was incomplete or invalid. Please try again.'); };
  if (!object(raw)) return invalid();
  const mode = raw.mode ?? 'chord_symbols';
  if (!['chord_symbols', 'infer_harmony'].includes(mode as string) || mode !== expectedMode) return invalid();
  const analysisSource = raw.analysisSource ?? 'meta';
  if (!['local', 'meta', 'mixed'].includes(analysisSource as string) || (expectedEngine === 'local' && analysisSource !== 'local')) return invalid();
  if (!text(raw.title, 120) || !(raw.key === null || text(raw.key, 40)) || !validMeter(raw.timeSignature) ||
      !(analysisSource === 'local' ? raw.model === null && raw.requestId === null : text(raw.model, 200) && raw.model.trim() !== '') ||
      !(raw.requestId === null || text(raw.requestId, 200)) ||
      !Array.isArray(raw.measures) || raw.measures.length > MAX_SCORE_IMPORT_MEASURES ||
      !Array.isArray(raw.sections) || raw.sections.length > 64 ||
      !Array.isArray(raw.warnings) || raw.warnings.length > 32 || !raw.warnings.every((v) => text(v, 400))) return invalid();
  const measures: ScoreImportResponse['measures'] = [];
  for (const measure of raw.measures) {
    if (!object(measure) || !Array.isArray(measure.chords) || measure.chords.length > 16 ||
        !measure.chords.every((v) => text(v, 120) && v.trim() !== '') || !text(measure.sourceLabel, 80) ||
        typeof measure.needsReview !== 'boolean' || !text(measure.note, 400)) return invalid();
    const chordBasis = measure.chordBasis ?? 'printed';
    const confidence = measure.confidence ?? 'high';
    const noChord = measure.noChord ?? false;
    const notes = measure.notes ?? [];
    const writtenNotes = measure.writtenNotes ?? [];
    const bassNotes = measure.bassNotes ?? [];
    const timeSignature = measure.timeSignature ?? null;
    const measureSource = measure.analysisSource ?? (analysisSource === 'mixed' ? null : analysisSource);
    const model = measure.model ?? (measureSource === 'local' ? null : raw.model);
    const requestId = measure.requestId ?? null;
    if ((mode === 'infer_harmony' && (measure.chordBasis === undefined || measure.confidence === undefined)) ||
        !['printed', 'inferred', 'unreadable'].includes(chordBasis as string) ||
        !['high', 'medium', 'low'].includes(confidence as string) ||
        typeof noChord !== 'boolean' || (noChord && measure.chords.length !== 0) ||
        !Array.isArray(notes) || notes.length > 128 || !notes.every((v) => text(v, 80)) ||
        !Array.isArray(writtenNotes) || writtenNotes.length > 128 || !writtenNotes.every((v) => text(v, 80)) ||
        !Array.isArray(bassNotes) || bassNotes.length > 128 || !bassNotes.every((v) => text(v, 80)) ||
        !validMeter(timeSignature) || !['local', 'meta'].includes(measureSource as string) ||
        (analysisSource !== 'mixed' && measureSource !== analysisSource) ||
        !(measureSource === 'local' ? model === null : text(model, 200) && model.trim() !== '') ||
        !(requestId === null || text(requestId, 200)) || (measureSource === 'local' && requestId !== null) ||
        (chordBasis === 'inferred' && (mode !== 'infer_harmony' || !measure.needsReview || !measure.note.trim())) ||
        (confidence === 'low' && !measure.needsReview) ||
        (chordBasis === 'unreadable' && (noChord || measure.chords.length !== 0 || confidence !== 'low' || !measure.needsReview))) return invalid();
    measures.push({ ...measure, chordBasis, confidence, noChord, notes, writtenNotes, bassNotes, timeSignature, analysisSource: measureSource, model, requestId } as ScoreImportResponse['measures'][number]);
  }
  for (const section of raw.sections) {
    if (!object(section) || !(section.section === null || isSectionType(section.section)) ||
        !text(section.label, 80) || !text(section.note, 400) ||
        !Number.isInteger(section.startMeasure) || !Number.isInteger(section.length) ||
        !['explicit', 'inferred'].includes(section.basis as string)) return invalid();
  }
  return { ...raw, mode, analysisSource, measures } as unknown as ScoreImportResponse;
}

export function createScoreImportDraft(response: ScoreImportResponse, filename: string): ScoreImportDraft {
  return {
    mode: response.mode ?? 'chord_symbols',
    analysisSource: response.analysisSource ?? 'meta',
    filename,
    title: response.title || filename.replace(/\.[^.]+$/, ''),
    key: response.key ?? '',
    timeSignature: response.timeSignature?.join('/') ?? '',
    bpm: '80',
    measures: response.measures.map((measure, index) => ({
      ...measure,
      chordBasis: measure.chordBasis ?? 'printed',
      confidence: measure.confidence ?? 'high',
      sourceMeasureIndex: index,
      analysisSource: measure.analysisSource ?? (response.analysisSource === 'local' ? 'local' : 'meta'),
      model: measure.model ?? ((measure.analysisSource ?? response.analysisSource) === 'local' ? null : response.model),
      requestId: measure.requestId ?? null,
      notes: [...(measure.notes ?? [])],
      writtenNotes: [...(measure.writtenNotes ?? [])],
      bassNotes: [...(measure.bassNotes ?? [])],
      originalNoChord: measure.noChord ?? false,
      timeSignature: measure.timeSignature ? [...measure.timeSignature] as [number, number] : null,
      originalChords: [...measure.chords],
      chordText: measure.noChord ? 'N.C.' : measure.chords.join(' '),
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

/** Analyze the edited symbols against the selected review key, without transposing them. */
export function importMeasureRomanPreview(chordText: string, keyText: string): string | null {
  const key = normalizeKeySignature(keyText);
  if (!key) return null;
  if (isNoChordText(chordText)) return 'N.C.';
  const symbols = chordText.trim().split(/\s+/).filter(Boolean);
  if (symbols.length < 1 || symbols.length > 16) return null;
  const chords = symbols.map((symbol) => parseImportedChord(symbol, key));
  if (chords.some((chord) => chord === null)) return null;
  return chords.map((chord) => chord!.romanNumeral).join(' · ');
}

export interface ScoreImportValidation {
  valid: boolean;
  errors: string[];
  measureErrors: string[];
  sectionErrors: string[];
  singleChordBars: number;
}

function validateScoreImport(draft: ScoreImportDraft, reviewChords: boolean): ScoreImportValidation {
  const errors: string[] = [];
  if (!draft.title.trim() || draft.title.trim().length > 120) errors.push('Enter a title of 1–120 characters.');
  const key = normalizeKeySignature(draft.key);
  if (!key) errors.push('Choose one of the 30 standard major/minor keys (up to seven sharps or flats). Correct unsupported keys manually before importing.');
  if (!(IMPORT_TIME_SIGNATURES as readonly string[]).includes(draft.timeSignature)) errors.push('Choose one of the time signatures supported by the editor.');
  if (!/^\d+$/.test(draft.bpm) || Number(draft.bpm) < 20 || Number(draft.bpm) > 300) errors.push('Playback tempo must be a whole number from 20 to 300 BPM.');
  if (draft.measures.length === 0 || draft.measures.length > MAX_SCORE_IMPORT_MEASURES) errors.push('The score must contain 1–512 measures.');
  if (draft.sections.length > 64) errors.push('The score can contain at most 64 sections.');

  let singleChordBars = 0;
  const measureErrors = reviewChords ? draft.measures.map((measure) => {
    if (isNoChordText(measure.chordText)) return '';
    const symbols = measure.chordText.trim().split(/\s+/).filter(Boolean);
    if (symbols.length > 2) return `${symbols.length} changes were kept in the analysis. Choose at most two chords for the editor's equal slots; no changes are dropped automatically.`;
    if (symbols.length === 0) return 'Enter one or two chords, or explicitly enter N.C. to leave this bar without harmony.';
    const unsupported = symbols.filter((symbol) => !parseImportedChord(symbol, key ?? 'C major'));
    if (unsupported.length) return `Unsupported or unreadable chord: ${unsupported.join(', ')}. Correct it before importing.`;
    if (symbols.length === 1) singleChordBars++;
    return '';
  }) : [];

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

/** Chord correction belongs to the score view. Only project metadata blocks
 *  opening a draft there; unresolved source material remains attached. */
export function validateScoreImportForEditor(draft: ScoreImportDraft): ScoreImportValidation {
  return validateScoreImport(draft, false);
}

export function validateScoreImportDraft(draft: ScoreImportDraft): ScoreImportValidation {
  return validateScoreImport(draft, true);
}

function pendingMeasureReview(measure: ImportMeasureDraft, key: string): string | undefined {
  if (isNoChordText(measure.chordText)) return undefined;
  const symbols = measure.chordText.trim().split(/\s+/).filter(Boolean);
  if (!symbols.length) return 'No chord was determined. Choose a chord in the score view.';
  if (symbols.length > 2) return `${symbols.length} source changes are preserved. Place the desired changes in the editor's two chord slots.`;
  if (symbols.some((symbol) => !parseImportedChord(symbol, key))) return 'Some source chord symbols need correction in the score view.';
  return undefined;
}

function importedMeasureChords(measure: ImportMeasureDraft, key: string): [Chord | null, Chord | null] {
  const symbols = measure.chordText.trim().split(/\s+/).filter(Boolean);
  // Do not turn an unresolved bar into N.C., invent a chord, or silently choose
  // two out of a longer progression. All source symbols stay in importSource.
  if (isNoChordText(measure.chordText) || symbols.length === 0 || symbols.length > 2) return [null, null];
  return [parseImportedChord(symbols[0], key), parseImportedChord(symbols[1] ?? symbols[0], key)];
}

/** Strict conversion remains available for callers that finish chord review. */
export function buildImportedSong(draft: ScoreImportDraft, makeId: () => string = () => crypto.randomUUID()): Song {
  return buildScoreImport(draft, makeId, false);
}

/** Open the analysis as an editable score, retaining unfinished chord reading. */
export function buildScoreImportForEditor(draft: ScoreImportDraft, makeId: () => string = () => crypto.randomUUID()): Song {
  return buildScoreImport(draft, makeId, true);
}

/** Source bytes and preview URLs are never included in the saved Song. */
function buildScoreImport(draft: ScoreImportDraft, makeId: () => string, deferChordReview: boolean): Song {
  const validation = deferChordReview ? validateScoreImportForEditor(draft) : validateScoreImportDraft(draft);
  if (!validation.valid) throw new Error(deferChordReview
    ? 'Correct the highlighted project fields and sections before importing.'
    : 'Correct the highlighted measures and sections before importing.');
  const key = normalizeKeySignature(draft.key)!;
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
      return {
        id: makeId(),
        index,
        chords: importedMeasureChords(measure, key),
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
    importSource: {
      filename: draft.filename, model: draft.model, requestId: draft.requestId, mode: draft.mode,
      analysisSource: draft.analysisSource,
      measures: draft.measures.map((measure) => ({
        chordBasis: measure.chordBasis, confidence: measure.confidence,
        evidence: measure.note, originalChords: [...measure.originalChords],
        sourceMeasureIndex: measure.sourceMeasureIndex, analysisSource: measure.analysisSource, model: measure.model, requestId: measure.requestId,
        notes: [...measure.notes], writtenNotes: [...measure.writtenNotes], bassNotes: [...measure.bassNotes], originalNoChord: measure.originalNoChord,
        userNoChord: isNoChordText(measure.chordText) && !measure.originalNoChord,
        timeSignature: measure.timeSignature ? [...measure.timeSignature] as [number, number] : null,
        ...(deferChordReview && pendingMeasureReview(measure, key) ? { editorReview: pendingMeasureReview(measure, key) } : {}),
      })),
    },
  };
}
