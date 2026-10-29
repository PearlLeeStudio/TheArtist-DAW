import type { Chord, PlaySettings, Song, SongSection } from '../models/types';
import { resolveVoicingMode, sanitizePlaySettings } from './playSettings.ts';
import type { VoicingMode } from './playSettings.ts';
import { guitarVoicingNotes, resolvePianoVoicing } from './voicingEngine.ts';
import { checkSectionRanges, sectionDisplayLabel } from './songForm.ts';

export interface ExportChord { symbol: string; voicing: number[] }
export interface ExportSpec {
  title: string;
  bpm: number;
  key: string;
  timeSignature: [number, number];
  genre: string | null;
  measures: { chords: [ExportChord | null, ExportChord | null] }[];
  sections: { label: string; startMeasure: number; length: number }[];
  play: Omit<PlaySettings, 'visualMode'>;
}

// The backend's ExportSpec limits (backend/app/models/export.py).
const MAX_EXPORT_BARS = 512;
const MAX_EXPORT_SECTIONS = 128;
const MAX_VOICING_NOTES = 16;
const MAX_MIDI_NOTE = 127;

/** How long the backend may take to render a MIDI file. */
const MIDI_EXPORT_TIMEOUT_MS = 60_000;
/** The chunk id every Standard MIDI File starts with. */
const MIDI_FILE_HEADER = 'MThd';

const WINDOWS_RESERVED_NAME = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i;
const MAX_FILENAME_STEM_CHARS = 100;
const LOOPBACK_NAMES = new Set(['localhost', '::1', '[::1]']);

export function exportChordSymbol(chord: Chord): string {
  const quality = chord.quality === 'maj' ? '' : chord.quality === 'min' ? 'm' : chord.quality;
  const extensions = chord.extensions.length ? `(${chord.extensions.join(',')})` : '';
  const bass = chord.bass ? `/${chord.bass}` : '';
  return `${chord.root}${quality}${extensions}${bass}`;
}

/** The backend takes 1–16 whole MIDI note numbers per chord. */
function isExportableVoicing(voicing: number[]): boolean {
  return voicing.length > 0 && voicing.length <= MAX_VOICING_NOTES &&
    voicing.every((note) => Number.isInteger(note) && note >= 0 && note <= MAX_MIDI_NOTE);
}

/** One chord slot with the notes the editor plays for it in `voicingMode`. */
function exportChord(chord: Chord | null, voicingMode: VoicingMode): ExportChord | null {
  if (!chord) return null;
  // A copy: the piano voicing may be the chord's own stored array.
  const voicing = voicingMode === 'guitar' ? guitarVoicingNotes(chord) : [...resolvePianoVoicing(chord)];
  if (!isExportableVoicing(voicing)) {
    throw new Error(`Cannot export the voicing for ${exportChordSymbol(chord)}.`);
  }
  return { symbol: exportChordSymbol(chord), voicing };
}

/** Throws the reason the song cannot be exported (yet), if there is one. */
function assertExportable(song: Song, sections: SongSection[]): void {
  if (!song.measures.length || song.measures.length > MAX_EXPORT_BARS) {
    throw new Error(`Export supports 1–${MAX_EXPORT_BARS} bars.`);
  }
  if (sections.some((section) => section.pending)) throw new Error('Wait for section generation to finish before exporting.');
  if (sections.length > MAX_EXPORT_SECTIONS) throw new Error(`Export supports up to ${MAX_EXPORT_SECTIONS} sections.`);
  const sectionError = checkSectionRanges(sections, song.measures.length);
  if (sectionError) throw new Error(sectionError);
}

/** The Play settings sent with the export. visualMode is not part of the
 *  wire format: it only decides the voicings. */
function exportPlaySettings(settings: PlaySettings): ExportSpec['play'] {
  return {
    harmonyOverride: settings.harmonyOverride,
    harmonyRhythmId: settings.harmonyRhythmId,
    bassEnabled: settings.bassEnabled,
    drumMode: settings.drumMode,
    drumPatternId: settings.drumPatternId,
    masterVolume: settings.masterVolume,
    harmonyVolume: settings.harmonyVolume,
    bassVolume: settings.bassVolume,
    drumVolume: settings.drumVolume,
  };
}

/** Snapshot the editor's actual voicings; later edits cannot change an in-flight export. */
export function buildExportSpec(song: Song, settings: PlaySettings): ExportSpec {
  const sections = song.sections ?? [];
  assertExportable(song, sections);
  const playSettings = sanitizePlaySettings(settings);
  const voicingMode = resolveVoicingMode(playSettings, song.genre);
  return {
    title: song.title.trim() || 'Untitled',
    bpm: song.bpm,
    key: song.key,
    timeSignature: [...song.timeSignature],
    genre: song.genre,
    measures: song.measures.map((measure) => ({
      chords: [exportChord(measure.chords[0], voicingMode), exportChord(measure.chords[1], voicingMode)],
    })),
    sections: [...sections]
      .sort((a, b) => a.startMeasure - b.startMeasure)
      .map((section) => ({ label: sectionDisplayLabel(section), startMeasure: section.startMeasure, length: section.length })),
    play: exportPlaySettings(playSettings),
  };
}

/** Not an ASCII control character (U+0000–U+001F, U+007F). */
function isNotAsciiControl(char: string): boolean {
  const code = char.codePointAt(0)!;
  return code >= 32 && code !== 127;
}

export function safeExportFilename(title: string, extension: 'mid' | 'pdf'): string {
  // Preserve readable Unicode titles while excluding path separators and OS-reserved names.
  const cleaned = Array.from(title.normalize('NFKC'))
    .filter(isNotAsciiControl)
    .join('')
    .replace(/[\\/:*?"<>|]/g, '-')
    .replace(/\s+/g, ' ')
    .replace(/^[. ]+|[. ]+$/g, '');
  // Cut by code point so no surrogate pair is split, then trim the new end.
  let stem = Array.from(cleaned).slice(0, MAX_FILENAME_STEM_CHARS).join('').replace(/[. ]+$/g, '') || 'Untitled';
  if (WINDOWS_RESERVED_NAME.test(stem)) stem = `_${stem}`;
  return `${stem}.${extension}`;
}

/** 127.x.y.z with every part at most 255. */
function isIpv4Loopback(host: string): boolean {
  return /^127(?:\.(?:\d{1,3})){3}$/.test(host) && host.split('.').every((part) => Number(part) <= 255);
}

export function isLoopbackHostname(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return LOOPBACK_NAMES.has(host) || isIpv4Loopback(host);
}

/** The message in a FastAPI error body: `detail` itself, or the joined
 *  `msg`s of a validation-error list; null when there is none. */
function errorDetail(body: unknown): string | null {
  if (typeof body !== 'object' || body === null || !('detail' in body)) return null;
  const detail = body.detail;
  if (typeof detail === 'string') return detail;
  if (!Array.isArray(detail)) return null;
  const reasons = detail.flatMap((item) => typeof item === 'object' && item !== null &&
    'msg' in item && typeof item.msg === 'string' ? [item.msg] : []);
  return reasons.length ? reasons.join('; ') : null;
}

export async function exportResponseError(response: Response): Promise<Error> {
  let message = `Export failed (${response.status}).`;
  try {
    message = errorDetail(await response.json()) ?? message;
  } catch { /* A non-JSON server error still gets a visible status. */ }
  return new Error(message);
}

function isMidiFileHeader(bytes: Uint8Array): boolean {
  return bytes.length === MIDI_FILE_HEADER.length && String.fromCharCode(...bytes) === MIDI_FILE_HEADER;
}

export async function requestMidiExport(spec: ExportSpec, signal?: AbortSignal): Promise<Blob> {
  const controller = new AbortController();
  const cancel = () => controller.abort(signal?.reason);
  if (signal?.aborted) cancel();
  else signal?.addEventListener('abort', cancel, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, MIDI_EXPORT_TIMEOUT_MS);
  try {
    const response = await fetch('/api/export/midi', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(spec), signal: controller.signal,
    });
    if (!response.ok) throw await exportResponseError(response);
    const blob = await response.blob();
    const header = new Uint8Array(await blob.slice(0, MIDI_FILE_HEADER.length).arrayBuffer());
    if (!isMidiFileHeader(header)) throw new Error('The server did not return a MIDI file.');
    return blob;
  } catch (error) {
    if (timedOut) throw new Error('MIDI export timed out. Please try again.', { cause: error });
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener('abort', cancel);
  }
}

export function downloadExportBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.append(anchor);
  try { anchor.click(); } finally {
    anchor.remove();
    // Safari needs the URL to remain alive until it starts the download.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
