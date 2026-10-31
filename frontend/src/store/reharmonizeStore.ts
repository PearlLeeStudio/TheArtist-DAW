import { create } from 'zustand';
import { useSongStore } from './songStore';
import { useGenerationStore } from './generationStore';
import { emptyReharmState, reharmActions } from '../engine/reharmonizeSession';
import type { ReharmState } from '../engine/reharmonizeSession';

export const useReharmonizeStore = create<ReharmState>((set, get) => ({
  ...emptyReharmState,
  ...reharmActions({
    read: () => useSongStore.getState(),
    stop: () => useSongStore.getState().resetPlayback(),
    write: updates => useSongStore.getState().setChords(updates, { preserveAnalysis: true }),
    clearGeneration: () => useGenerationStore.getState().clearSuggestions(),
  }, get, set),
}));

useSongStore.subscribe((current, previous) => {
  if (current.songEpoch !== previous.songEpoch) useReharmonizeStore.getState().close();
});
