/**
 * Song-form sections: the vocabulary shared with the backend
 * (backend/app/models/sections.py — keep the two lists identical) plus the
 * pure helpers the stores and the score view use to title, place and look
 * up sections.
 *
 * Type-only imports on purpose: `node --test` runs songForm.test.ts against
 * this file directly, without a bundler.
 */
import type { Song, SongSection, SectionType } from '../models/types';

export type SectionGroup = 'common' | 'instrumental' | 'jazz';

export interface SectionInfo {
  label: string;
  group: SectionGroup;
  /** Chord count the "Build from Song Form" dialog starts from. */
  defaultChords: number;
}

export const SECTION_INFO: Record<SectionType, SectionInfo> = {
  intro:       { label: 'Intro',       group: 'common',       defaultChords: 8 },
  verse:       { label: 'Verse',       group: 'common',       defaultChords: 16 },
  pre_chorus:  { label: 'Pre-Chorus',  group: 'common',       defaultChords: 8 },
  chorus:      { label: 'Chorus',      group: 'common',       defaultChords: 16 },
  post_chorus: { label: 'Post-Chorus', group: 'common',       defaultChords: 8 },
  bridge:      { label: 'Bridge',      group: 'common',       defaultChords: 16 },
  outro:       { label: 'Outro',       group: 'common',       defaultChords: 8 },
  interlude:   { label: 'Interlude',   group: 'instrumental', defaultChords: 8 },
  solo:        { label: 'Solo',        group: 'instrumental', defaultChords: 16 },
  breakdown:   { label: 'Breakdown',   group: 'instrumental', defaultChords: 16 },
  drop:        { label: 'Drop',        group: 'instrumental', defaultChords: 16 },
  vamp:        { label: 'Vamp',        group: 'instrumental', defaultChords: 4 },
  turnaround:  { label: 'Turnaround',  group: 'instrumental', defaultChords: 4 },
  tag:         { label: 'Tag',         group: 'instrumental', defaultChords: 8 },
  head:        { label: 'Head',        group: 'jazz',         defaultChords: 64 },
  a_section:   { label: 'A Section',   group: 'jazz',         defaultChords: 16 },
  b_section:   { label: 'B Section',   group: 'jazz',         defaultChords: 16 },
};

/** Every section id, in dropdown order. */
export const SECTION_TYPES = Object.keys(SECTION_INFO) as SectionType[];

/** Dropdown <optgroup>s, in order. */
export const SECTION_GROUPS: ReadonlyArray<{ id: SectionGroup; label: string }> = [
  { id: 'common', label: 'Common' },
  { id: 'instrumental', label: 'Instrumental' },
  { id: 'jazz', label: 'Jazz' },
];

/** The editor has two chord slots per measure. */
export const CHORDS_PER_BAR = 2;
/** Cap on one generate request on every path: 128 chords = 64 bars. */
export const MAX_SECTION_CHORDS = 128;
export const MAX_SECTION_BARS = MAX_SECTION_CHORDS / CHORDS_PER_BAR;

/** Title of a song with no sections that nobody has named. */
export const DEFAULT_SONG_TITLE = 'Untitled';
/** autoTitle lists at most this many section labels, then an ellipsis. */
const AUTO_TITLE_MAX_LABELS = 6;

export function isSectionType(value: unknown): value is SectionType {
  return typeof value === 'string' && Object.hasOwn(SECTION_INFO, value);
}

export function sectionLabel(type: SectionType): string {
  return SECTION_INFO[type].label;
}

export function sectionsInGroup(group: SectionGroup): SectionType[] {
  return SECTION_TYPES.filter((type) => SECTION_INFO[type].group === group);
}

export function barsForChords(chordCount: number): number {
  return Math.ceil(chordCount / CHORDS_PER_BAR);
}

/** Single-section title, e.g. 'Chorus — 8 bars' (em dash, as the backend writes it). */
export function sectionTitle(type: SectionType, bars: number): string {
  return `${sectionLabel(type)} — ${bars} ${bars === 1 ? 'bar' : 'bars'}`;
}

/**
 * Title of a song built from sections. One section gives its sectionTitle;
 * several give their labels in song order joined by en dashes, without
 * spaces ('Intro–Verse–Chorus'), at most six labels and then an ellipsis.
 * No sections gives DEFAULT_SONG_TITLE.
 */
export function autoTitle(sections: readonly SongSection[]): string {
  if (sections.length === 0) return DEFAULT_SONG_TITLE;
  const ordered = [...sections].sort((a, b) => a.startMeasure - b.startMeasure);
  if (ordered.length === 1) return sectionTitle(ordered[0].type, ordered[0].length);
  const labels = ordered.slice(0, AUTO_TITLE_MAX_LABELS).map((s) => sectionLabel(s.type));
  // U+2013 en dash between labels, U+2026 ellipsis when some are left out.
  return labels.join('–') + (ordered.length > AUTO_TITLE_MAX_LABELS ? '…' : '');
}

/** While the song's title is automatic, recompute it from its sections. */
export function withAutoTitle(song: Song): Song {
  return song.autoTitle ? { ...song, title: autoTitle(song.sections ?? []) } : song;
}

/**
 * Where a new section of `bars` measures goes: right after the last measure
 * that has any chord or belongs to a section (measure 0 on an empty song),
 * and how many measures must be appended for it to fit.
 */
export function sectionPlacement(
  song: Pick<Song, 'measures' | 'sections'>,
  bars: number,
): { startMeasure: number; measuresToAdd: number } {
  let lastUsed = -1;
  song.measures.forEach((measure, i) => {
    if (measure.chords.some(Boolean)) lastUsed = i;
  });
  for (const section of song.sections ?? []) {
    lastUsed = Math.max(lastUsed, section.startMeasure + section.length - 1);
  }
  const startMeasure = lastUsed + 1;
  return {
    startMeasure,
    measuresToAdd: Math.max(0, startMeasure + bars - song.measures.length),
  };
}

/** The section covering `measureIndex`, or null. */
export function sectionAt(
  song: Pick<Song, 'sections'>,
  measureIndex: number,
): SongSection | null {
  return (song.sections ?? []).find(
    (s) => measureIndex >= s.startMeasure && measureIndex < s.startMeasure + s.length,
  ) ?? null;
}

/** The section that contains every one of `measureIndices`, or null. */
export function sectionContaining(
  song: Pick<Song, 'sections'>,
  measureIndices: readonly number[],
): SongSection | null {
  if (measureIndices.length === 0) return null;
  const section = sectionAt(song, Math.min(...measureIndices));
  if (!section) return null;
  return Math.max(...measureIndices) < section.startMeasure + section.length ? section : null;
}

function isValidSection(value: unknown): value is SongSection {
  if (typeof value !== 'object' || value === null) return false;
  const s = value as Record<string, unknown>;
  return (
    typeof s.id === 'string' &&
    isSectionType(s.type) &&
    Number.isInteger(s.startMeasure) && (s.startMeasure as number) >= 0 &&
    Number.isInteger(s.length) && (s.length as number) >= 1
  );
}

/** Measures appended for a pending section; 0 when the record is unreadable. */
function addedMeasures(section: SongSection): number {
  const count = section.pending?.addedMeasures;
  return typeof count === 'number' && count > 0 ? Math.floor(count) : 0;
}

/**
 * Take back a placement whose generation never finished (the page was
 * reloaded or closed while "New from Song Form" ran): drop the pending
 * sections and the measures appended only for them, i.e. at most
 * `addedMeasures` trailing measures that have no chord and no other
 * section. An automatic title then stops naming them.
 */
function withoutPendingSections(song: Song): Song {
  const all = song.sections ?? [];
  const sections = all.filter((s) => !s.pending);
  if (sections.length === all.length) return song;
  const added = all.reduce((sum, s) => sum + addedMeasures(s), 0);
  const floor = Math.max(0, song.measures.length - added);
  let end = song.measures.length;
  while (
    end > floor &&
    !song.measures[end - 1].chords.some(Boolean) &&
    !sectionAt({ sections }, end - 1)
  ) {
    end--;
  }
  return withAutoTitle({ ...song, measures: song.measures.slice(0, end), sections });
}

/**
 * Fill in the song-form fields that songs saved before sections existed
 * lack: no sections, and an automatic title only when the title was never
 * set ('' or 'Untitled'). A section still pending when the song was saved
 * is taken back (see withoutPendingSections).
 */
export function withSongFormDefaults(song: Song): Song {
  const sections = Array.isArray(song.sections) ? song.sections.filter(isValidSection) : [];
  const title = (song.title ?? '').trim();
  const auto = typeof song.autoTitle === 'boolean'
    ? song.autoTitle
    : title === '' || title === DEFAULT_SONG_TITLE;
  return withoutPendingSections({ ...song, sections, autoTitle: auto });
}

export type ChordCountCheck =
  | { ok: true; count: number; bars: number }
  | { ok: false; message: string };

/** Validate the dialog's chord-count text: an even whole number, 2..128. */
export function checkChordCount(text: string): ChordCountCheck {
  const trimmed = text.trim();
  if (!/^\d+$/.test(trimmed)) {
    return { ok: false, message: `Enter an even number from ${CHORDS_PER_BAR} to ${MAX_SECTION_CHORDS}` };
  }
  const count = Number(trimmed);
  if (count < CHORDS_PER_BAR || count > MAX_SECTION_CHORDS) {
    return {
      ok: false,
      message: `Use ${CHORDS_PER_BAR} to ${MAX_SECTION_CHORDS} chords (up to ${MAX_SECTION_BARS} bars)`,
    };
  }
  if (count % CHORDS_PER_BAR !== 0) {
    return { ok: false, message: `Use an even number (${CHORDS_PER_BAR} chords per bar)` };
  }
  return { ok: true, count, bars: count / CHORDS_PER_BAR };
}

/** Live hint for a chord count, e.g. '16 chords = 8 bars'. */
export function chordCountSummary(count: number): string {
  const bars = barsForChords(count);
  return `${count} chords = ${bars} ${bars === 1 ? 'bar' : 'bars'}`;
}
