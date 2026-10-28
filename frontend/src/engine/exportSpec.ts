import type { Chord, PlaySettings, Song } from '../models/types';
import { resolveVoicingMode, sanitizePlaySettings } from './playSettings.ts';
import { generateGuitarVoicing, resolvePianoVoicing } from './voicingEngine.ts';
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

const OPEN_STRINGS = [40, 45, 50, 55, 59, 64];

export function exportChordSymbol(chord: Chord): string {
  const quality = chord.quality === 'maj' ? '' : chord.quality === 'min' ? 'm' : chord.quality;
  const extensions = chord.extensions.length ? `(${chord.extensions.join(',')})` : '';
  return `${chord.root}${quality}${extensions}${chord.bass ? `/${chord.bass}` : ''}`;
}

/** Snapshot the editor's actual voicings; later edits cannot change an in-flight export. */
export function buildExportSpec(song: Song, settings: PlaySettings): ExportSpec {
  if (!song.measures.length || song.measures.length > 512) throw new Error('Export supports 1–512 bars.');
  const sections = song.sections ?? [];
  if (sections.some((section) => section.pending)) throw new Error('Wait for section generation to finish before exporting.');
  if (sections.length > 128) throw new Error('Export supports up to 128 sections.');
  const sectionError = checkSectionRanges(sections, song.measures.length);
  if (sectionError) throw new Error(sectionError);
  const clean = sanitizePlaySettings(settings);
  const mode = resolveVoicingMode(clean, song.genre);
  const convert = (chord: Chord | null): ExportChord | null => {
    if (!chord) return null;
    const voicing = mode === 'guitar'
      ? generateGuitarVoicing(chord).flatMap((fret, i) => fret >= 0 ? [OPEN_STRINGS[i] + fret] : [])
      : [...resolvePianoVoicing(chord)];
    if (!voicing.length || voicing.length > 16 || voicing.some((note) => !Number.isInteger(note) || note < 0 || note > 127)) {
      throw new Error(`Cannot export the voicing for ${exportChordSymbol(chord)}.`);
    }
    return { symbol: exportChordSymbol(chord), voicing };
  };
  return {
    title: song.title.trim() || 'Untitled', bpm: song.bpm, key: song.key,
    timeSignature: [...song.timeSignature], genre: song.genre,
    measures: song.measures.map((measure) => ({ chords: [convert(measure.chords[0]), convert(measure.chords[1])] })),
    sections: [...sections].sort((a, b) => a.startMeasure - b.startMeasure)
      .map((section) => ({ label: sectionDisplayLabel(section), startMeasure: section.startMeasure, length: section.length })),
    play: {
      harmonyOverride: clean.harmonyOverride, harmonyRhythmId: clean.harmonyRhythmId,
      bassEnabled: clean.bassEnabled, drumMode: clean.drumMode, drumPatternId: clean.drumPatternId,
      masterVolume: clean.masterVolume, harmonyVolume: clean.harmonyVolume,
      bassVolume: clean.bassVolume, drumVolume: clean.drumVolume,
    },
  };
}

export function safeExportFilename(title: string, extension: 'mid' | 'pdf'): string {
  // Preserve readable Unicode titles while excluding path separators and OS-reserved names.
  let stem = Array.from(title.normalize('NFKC'))
    .filter((char) => char.codePointAt(0)! >= 32 && char.codePointAt(0)! !== 127)
    .join('').replace(/[\\/:*?"<>|]/g, '-').replace(/\s+/g, ' ').replace(/^[. ]+|[. ]+$/g, '');
  stem = Array.from(stem).slice(0, 100).join('').replace(/[. ]+$/g, '') || 'Untitled';
  if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(stem)) stem = `_${stem}`;
  return `${stem}.${extension}`;
}

export function isLoopbackHostname(hostname: string): boolean {
  const host = hostname.toLowerCase();
  return host === 'localhost' || host === '::1' || host === '[::1]' ||
    /^127(?:\.(?:\d{1,3})){3}$/.test(host) && host.split('.').every((part) => Number(part) <= 255);
}

export async function exportResponseError(response: Response): Promise<Error> {
  let message = `Export failed (${response.status}).`;
  try {
    const body: unknown = await response.json();
    if (typeof body === 'object' && body !== null && 'detail' in body) {
      const detail = (body as { detail: unknown }).detail;
      if (typeof detail === 'string') message = detail;
      else if (Array.isArray(detail)) {
        const reasons = detail.flatMap((item) => typeof item === 'object' && item !== null &&
          'msg' in item && typeof item.msg === 'string' ? [item.msg] : []);
        if (reasons.length) message = reasons.join('; ');
      }
    }
  } catch { /* A non-JSON server error still gets a visible status. */ }
  return new Error(message);
}

export async function requestMidiExport(spec: ExportSpec, signal?: AbortSignal): Promise<Blob> {
  const controller = new AbortController();
  const cancel = () => controller.abort(signal?.reason);
  if (signal?.aborted) cancel();
  else signal?.addEventListener('abort', cancel, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; controller.abort(); }, 60_000);
  try {
    const response = await fetch('/api/export/midi', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(spec), signal: controller.signal,
    });
    if (!response.ok) throw await exportResponseError(response);
    const blob = await response.blob();
    const header = new Uint8Array(await blob.slice(0, 4).arrayBuffer());
    if (header.length !== 4 || String.fromCharCode(...header) !== 'MThd') {
      throw new Error('The server did not return a MIDI file.');
    }
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
