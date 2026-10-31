import type { Song, SlotAddress } from '../models/types.ts';
import { captureGenerationComparison, matchesCapturedRange } from './generationComparison.ts';
import type { GenerationComparison, TargetChord } from './generationComparison.ts';
import { reharmFingerprint, reharmSelectionError, reharmTargets, reharmUpdates, requestReharmonization } from './reharmonize.ts';
import type { ReharmMode, ReharmResult } from './reharmonize.ts';

export interface ReharmState {
  loading: boolean;
  error: string | null;
  result: ReharmResult | null;
  comparison: GenerationComparison | null;
  applied: GenerationComparison | null;
  active: number | null;
  originalKey: string | null;
  expectedFingerprint: string | null;
  run: (modelKey: string, maxChanges: 1 | 2, mode: ReharmMode) => Promise<void>;
  preview: (index: number | null) => void;
  close: () => void;
}
export const emptyReharmState = {
  loading: false, error: null, result: null, comparison: null, applied: null,
  active: null, originalKey: null, expectedFingerprint: null,
};
interface Host {
  read: () => { song: Song; songEpoch: number; selectedSlots: SlotAddress[] };
  stop: () => void;
  write: (updates: TargetChord[]) => void;
  clearGeneration: () => void;
}

/** Editor-independent lifecycle, shared by the UI store and transition tests. */
export function reharmActions(host: Host, get: () => ReharmState, set: (patch: Partial<ReharmState>) => void,
  requestCandidates = requestReharmonization): Pick<ReharmState, 'run' | 'preview' | 'close'> {
  let request: AbortController | null = null;
  return {
    run: async (modelKey, maxChanges, mode) => {
      const { song, songEpoch, selectedSlots } = host.read();
      const problem = reharmSelectionError(song, selectedSlots);
      if (problem) { set({ error: problem }); return; }
      const targets = reharmTargets(song, selectedSlots);
      request?.abort();
      const controller = new AbortController();
      request = controller;
      const comparison = captureGenerationComparison(song, targets, songEpoch);
      const fingerprint = reharmFingerprint(song);
      host.clearGeneration();
      set({ ...emptyReharmState, loading: true, comparison, applied: comparison,
        originalKey: song.key, expectedFingerprint: fingerprint });
      try {
        const result = await requestCandidates(song, targets, maxChanges, mode, modelKey, controller.signal);
        if (request !== controller) return;
        const current = host.read();
        if (current.songEpoch !== songEpoch || reharmFingerprint(current.song) !== fingerprint) {
          throw new Error('The score changed during the search. Generate fresh candidates for this passage.');
        }
        set({ result, loading: false });
      } catch (error) {
        if (request === controller) set({ loading: false, error: error instanceof Error ? error.message : 'Reharmonization failed.' });
      }
    },
    preview: index => {
      const state = get();
      const { song, songEpoch } = host.read();
      if (!state.comparison || !state.applied || state.loading || (index !== null && !state.result?.candidates[index])) return;
      if (!matchesCapturedRange(state.applied, song, songEpoch)) {
        set({ error: 'This passage was edited. Generate fresh candidates to keep those edits.' });
        return;
      }
      const stale = reharmFingerprint(song) !== state.expectedFingerprint;
      if (index !== null && stale) {
        set({ error: 'The surrounding score changed. Restore the original or generate fresh candidates.' });
        return;
      }
      if (song.key !== state.originalKey) {
        set({ error: 'The key changed. Generate fresh candidates for the new key.' });
        return;
      }
      host.stop();
      host.write(reharmUpdates(state.comparison, song, songEpoch,
        index === null ? undefined : state.result!.candidates[index]));
      const current = host.read();
      set({ active: index, error: stale ? 'Original restored. Generate again to use the changed context.' : null,
        applied: captureGenerationComparison(current.song, state.comparison.original.map(c => c.address), current.songEpoch),
        expectedFingerprint: stale ? state.expectedFingerprint : reharmFingerprint(current.song) });
      // All three alternatives stay available, including after A→B→A and Original.
    },
    close: () => { request?.abort(); request = null; set(emptyReharmState); },
  };
}
