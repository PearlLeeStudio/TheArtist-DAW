import type { Chord, ImportConfidence, ImportMeasureSource, Song } from '../models/types';
import { LOCAL_SCORE_ONLY_MESSAGE, LOCAL_SCORE_RECOVERY_MESSAGE, parseImportedChord } from './scoreImport.ts';
import type { ScoreImportResponse } from './scoreImport.ts';

/**
 * What a background Meta reading adds to a score that already opened from
 * the local reader: Review marks on bars where the two readings disagree,
 * and chords for bars the local reader left empty and the musician has not
 * touched. Chords the musician can already see are never replaced.
 */

export interface ImportReviewFlag {
  index: number;
  review: string;
  confidence: ImportConfidence;
}

export interface ImportReviewFill {
  index: number;
  chords: [Chord | null, Chord | null];
  source: Partial<ImportMeasureSource>;
}

export interface ImportReviewPlan {
  flags: ImportReviewFlag[];
  fills: ImportReviewFill[];
  /** One line for the band above the staff. */
  summary: string;
}

/** A fixed status avoids copying reader prose into the retained project. */
const reviewText = 'Check against the original: the readings differ.';

const bars = (count: number) => `${count} ${count === 1 ? 'bar' : 'bars'}`;

export function planImportReview(song: Song, verified: ScoreImportResponse): ImportReviewPlan {
  const check = verified.verification;
  const sources = song.importSource?.measures ?? [];
  if (!check) return { flags: [], fills: [], summary: 'The check returned no comparison.' };
  if (check.status === 'local_only' || check.status === 'local_fallback') {
    return { flags: [], fills: [], summary: check.status === 'local_only'
      ? LOCAL_SCORE_ONLY_MESSAGE : LOCAL_SCORE_RECOVERY_MESSAGE };
  }
  if (check.status === 'unaligned') {
    return { flags: [], fills: [], summary: `The second reading found ${bars(check.metaMeasures)} where the score has ${bars(check.localMeasures)}; nothing was flagged.` };
  }
  if (check.status === 'local_unavailable') {
    return { flags: [], fills: [], summary: 'No local comparison was possible; review every bar against the source.' };
  }
  const flags: ImportReviewFlag[] = [];
  for (const index of check.disputedMeasures) {
    const measure = verified.measures[index];
    if (!measure || !song.measures[index] || !sources[index]) continue;
    flags.push({ index, review: reviewText, confidence: measure.confidence ?? 'low' });
  }
  const fills: ImportReviewFill[] = [];
  for (let index = 0; index < Math.min(song.measures.length, verified.measures.length, sources.length); index++) {
    const current = song.measures[index];
    const source = sources[index];
    const proposed = verified.measures[index];
    // Only bars still empty, not marked N.C. by the source or the musician, with a Meta reading of one or two symbols.
    if (!current.chords.every((chord) => chord === null) || source.originalNoChord || source.userNoChord) continue;
    if (proposed.analysisSource !== 'meta' || proposed.noChord || proposed.chords.length < 1 || proposed.chords.length > 2) continue;
    const parsed = proposed.chords.map((symbol) => parseImportedChord(symbol, song.key));
    if (parsed.some((chord) => chord === null)) continue;
    const first = parsed[0]!;
    const second = parsed[1] ?? { ...first, voicing: [...first.voicing], extensions: [...first.extensions] };
    fills.push({
      index,
      chords: [first, second],
      source: {
        chordBasis: proposed.chordBasis ?? 'inferred', confidence: proposed.confidence ?? 'low',
        evidence: '', originalChords: [...proposed.chords], analysisSource: 'meta',
        model: proposed.model ?? verified.model, requestId: proposed.requestId ?? verified.requestId,
        editorReview: 'Proposed from the original after import; the local reader had none.',
      },
    });
  }
  const parts = [];
  if (flags.length) parts.push(`${bars(flags.length)} flagged for review`);
  if (fills.length) parts.push(`${bars(fills.length)} filled where the local reader had no chord`);
  return { flags, fills, summary: parts.length ? `Checked against the original: ${parts.join(', ')}.` : 'Checked against the original: both readings agree.' };
}
