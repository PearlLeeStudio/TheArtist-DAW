/**
 * Storage adapter for saved sessions. The whole MyPage feature talks to
 * this module, never to localStorage directly — so when v2 wants
 * IndexedDB / Supabase, only this file changes.
 *
 * Schema versioning: a top-level `{ version, sessions }` envelope so a
 * future migration can detect the old shape and upgrade in place. The
 * same envelope shape is used for the JSON file format produced by
 * Export / consumed by Import — no separate schema there.
 */
import type { SavedSession } from '../models/types';
import { isSectionType } from '../engine/songForm.ts';

const STORAGE_KEY = 'theartist-sessions';
export const SCHEMA_VERSION = 1;

export interface Envelope {
  version: number;
  sessions: SavedSession[];
  exportedAt?: number;  // present only on file exports, ignored when reading from localStorage
}

export function loadAll(): SavedSession[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Envelope;
    if (!parsed || parsed.version !== SCHEMA_VERSION || !Array.isArray(parsed.sessions)) {
      return [];
    }
    return parsed.sessions.filter(isValidSession);
  } catch {
    return [];
  }
}

export function saveAll(sessions: SavedSession[]): void {
  const envelope: Envelope = { version: SCHEMA_VERSION, sessions };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(envelope));
  } catch {
    throw new Error('This browser could not save the project. Storage may be full or disabled. Your current score is still open.');
  }
}

function record(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function validSong(value: unknown): boolean {
  if (!record(value) || typeof value.id !== 'string' || typeof value.title !== 'string' ||
      typeof value.key !== 'string' || !(value.genre === null || typeof value.genre === 'string') ||
      typeof value.bpm !== 'number' || !Number.isFinite(value.bpm) || value.bpm < 20 || value.bpm > 300) return false;
  const ts = value.timeSignature;
  if (!Array.isArray(ts) || ts.length !== 2 || !Number.isInteger(ts[0]) || ts[0] < 1 || ts[0] > 32 ||
      ![1, 2, 4, 8, 16, 32].includes(ts[1])) return false;
  if (!Array.isArray(value.measures) || value.measures.length > 4096) return false;
  const measureIds = new Set<string>();
  for (const measure of value.measures) {
    if (!record(measure) || typeof measure.id !== 'string' || measureIds.has(measure.id) ||
        !Number.isInteger(measure.index) || !Array.isArray(measure.chords) || measure.chords.length !== 2) return false;
    measureIds.add(measure.id);
    for (const chord of measure.chords) {
      if (chord === null) continue;
      if (!record(chord) || typeof chord.root !== 'string' || typeof chord.quality !== 'string' ||
          typeof chord.romanNumeral !== 'string' || (chord.bass !== undefined && typeof chord.bass !== 'string') ||
          !Array.isArray(chord.voicing) || chord.voicing.length > 32 ||
          !chord.voicing.every((n) => Number.isInteger(n) && n >= 0 && n <= 127) ||
          !Array.isArray(chord.extensions) || !chord.extensions.every((e) => typeof e === 'string')) return false;
    }
  }
  if (value.sections !== undefined) {
    if (!Array.isArray(value.sections)) return false;
    const ranges: Array<{ start: number; end: number }> = [];
    const ids = new Set<string>();
    for (const section of value.sections) {
      if (!record(section) || typeof section.id !== 'string' || ids.has(section.id) ||
          !(section.type === null || isSectionType(section.type)) ||
          typeof section.startMeasure !== 'number' || !Number.isInteger(section.startMeasure) || section.startMeasure < 0 ||
          typeof section.length !== 'number' || !Number.isInteger(section.length) || section.length < 1 ||
          section.startMeasure + section.length > value.measures.length ||
          (section.label !== undefined && typeof section.label !== 'string')) return false;
      ids.add(section.id);
      ranges.push({ start: section.startMeasure, end: section.startMeasure + section.length });
    }
    ranges.sort((a, b) => a.start - b.start);
    if (ranges.some((r, i) => i > 0 && r.start < ranges[i - 1].end)) return false;
  }
  return true;
}

/** Validate a parsed object as a SavedSession. Reject silently rather
 *  than throwing — bad entries from a foreign export are skipped, not
 *  fatal. */
function isValidSession(x: unknown): x is SavedSession {
  if (typeof x !== 'object' || x === null) return false;
  const s = x as Record<string, unknown>;
  return (
    typeof s.id === 'string' &&
    typeof s.name === 'string' &&
    typeof s.createdAt === 'number' && Number.isFinite(s.createdAt) &&
    typeof s.starred === 'boolean' &&
    validSong(s.song) &&
    record(s.generation) && typeof s.generation.model === 'string' &&
    (s.generation.genre === null || typeof s.generation.genre === 'string')
  );
}

/** Serialize all sessions as a JSON string for file download. Wraps the
 *  envelope with `exportedAt` so the receiving side can show provenance. */
export function serializeForExport(sessions: SavedSession[]): string {
  const envelope: Envelope = {
    version: SCHEMA_VERSION,
    sessions,
    exportedAt: Date.now(),
  };
  return JSON.stringify(envelope, null, 2);
}

export interface ImportResult {
  added: number;       // freshly imported (no id collision)
  renamed: number;     // imported with a regenerated id (existing id collided)
  skipped: number;     // failed validation
}

/** Parse a JSON file's text content and merge its sessions into the
 *  existing list. Collisions on `id` get a fresh UUID so both copies
 *  survive — users can prune duplicates manually. Returns counts so
 *  the UI can show a confirmation. Throws on parse / version errors. */
export function mergeImport(
  existing: SavedSession[],
  jsonText: string,
): { merged: SavedSession[]; result: ImportResult } {
  const parsed = JSON.parse(jsonText) as Envelope;
  if (!parsed || parsed.version !== SCHEMA_VERSION || !Array.isArray(parsed.sessions)) {
    throw new Error(`Unsupported file format (expected version ${SCHEMA_VERSION})`);
  }

  const existingIds = new Set(existing.map((s) => s.id));
  const result: ImportResult = { added: 0, renamed: 0, skipped: 0 };
  const incoming: SavedSession[] = [];

  for (const raw of parsed.sessions) {
    if (!isValidSession(raw)) {
      result.skipped += 1;
      continue;
    }
    if (existingIds.has(raw.id)) {
      const id = crypto.randomUUID();
      incoming.push({ ...raw, id });
      existingIds.add(id);
      result.renamed += 1;
    } else {
      incoming.push(raw);
      existingIds.add(raw.id);
      result.added += 1;
    }
  }

  // Newest-first: imports go on top, but preserve their internal order.
  return { merged: [...incoming, ...existing], result };
}
