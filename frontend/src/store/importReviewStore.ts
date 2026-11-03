import { create } from 'zustand';
import { useSongStore } from './songStore';
import { analyzeScoreFile } from '../engine/scoreImportClient';
import type { AnalyzeScoreOptions } from '../engine/scoreImportClient';
import { planImportReview } from '../engine/importReview';
import { beginTiming } from '../engine/experienceTiming';
import type { ScoreImportEngine, ScoreImportResponse, ScoreMime } from '../engine/scoreImport';
import type { ScoreImportMode } from '../models/types';

/**
 * The Meta reading that follows an instant local import. The score is already
 * on the staff; this store runs the verified reading of the same file in the
 * background and, when it returns, marks disputed bars and fills bars the
 * local reader left empty. A replaced song discards the review.
 */

export type ImportReviewPhase = 'idle' | 'running' | 'done' | 'failed';

export interface ImportReviewState {
  phase: ImportReviewPhase;
  /** The imported song the review belongs to. */
  songEpoch: number | null;
  filename: string;
  /** Reader stage while running. */
  label: string;
  /** Outcome line once done or failed. */
  summary: string;
  /** Bars marked for review, in score order. */
  flagged: number[];
  filled: number;
  requestId: string | null;
  /** meta: Meta read the original and the check ran. local: the local reader stood in (Meta
   *  unavailable, or skipped for a long score). null: no comparison, or the check failed. */
  outcome: 'meta' | 'local' | null;
  /** The Meta model that read the original, for the band. */
  model: string | null;
  start: (file: File, mimeType: ScoreMime, songEpoch: number) => void;
  cancel: () => void;
  dismiss: () => void;
}

export type ScoreAnalyzer = (file: File, mimeType: ScoreMime, engine: ScoreImportEngine, mode: ScoreImportMode,
  options?: AnalyzeScoreOptions) => Promise<ScoreImportResponse>;

const idle = { phase: 'idle' as const, songEpoch: null, filename: '', label: '', summary: '', flagged: [], filled: 0, requestId: null,
  outcome: null, model: null };

export function createImportReviewStore(analyze: ScoreAnalyzer = analyzeScoreFile) {
  let controller: AbortController | null = null;
  const store = create<ImportReviewState>((set, get) => ({
    ...idle,
    start: (file, mimeType, songEpoch) => {
      controller?.abort();
      const own = new AbortController();
      controller = own;
      // Pass the File directly to the active request; never keep it or its name in store state.
      set({ ...idle, phase: 'running', songEpoch, label: 'Checking the imported score against the original…' });
      const finish = beginTiming('import.review', 'verified-background');
      analyze(file, mimeType, 'verified', 'infer_harmony', {
        signal: own.signal,
        onStatus: (label) => { if (controller === own) set({ label }); },
      }).then((verified) => {
        if (controller !== own) return;
        controller = null;
        const songs = useSongStore.getState();
        if (songs.songEpoch !== songEpoch) { set({ ...idle }); return; }
        const plan = planImportReview(songs.song, verified);
        songs.applyImportReview(songEpoch, plan);
        finish();
        const status = verified.verification?.status ?? null;
        const outcome: ImportReviewState['outcome'] = status === null ? null
          : status === 'local_only' || status === 'local_fallback' ? 'local' : 'meta';
        set({ phase: 'done', summary: plan.summary, flagged: plan.flags.map((flag) => flag.index),
          filled: plan.fills.length, requestId: verified.requestId ?? null, label: '',
          outcome, model: outcome === 'meta' ? verified.model ?? null : null });
      }).catch((error: unknown) => {
        if (controller !== own) return;
        controller = null;
        if (own.signal.aborted) { finish('cancelled'); set({ ...idle }); return; }
        finish('error');
        set({ phase: 'failed', label: '',
          summary: `The check against the original did not finish: ${error instanceof Error ? error.message : 'the request failed'}` });
      });
    },
    cancel: () => {
      controller?.abort();
      controller = null;
      if (get().phase !== 'idle') set({ ...idle });
    },
    dismiss: () => { if (get().phase !== 'running') set({ ...idle }); },
  }));
  // The review belongs to one imported song; replacing the song ends it.
  useSongStore.subscribe((current, previous) => {
    if (current.songEpoch !== previous.songEpoch && store.getState().phase !== 'idle') store.getState().cancel();
  });
  return store;
}

export const useImportReviewStore = createImportReviewStore();
