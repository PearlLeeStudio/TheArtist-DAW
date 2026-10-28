/**
 * GenerationStore — UI-side state for the Generate panel.
 *
 * Lives outside songStore because these settings travel with the
 * generate engine, not with the song.
 *
 * Holds:
 *   - modelKey: persisted to localStorage so non-Generate UI (staff-header
 *     Save button) can bundle the current model into a session preset.
 *   - In-flight generation state (loading / phase / suggestions / etc.) —
 *     hoisted out of ChordActions component-local useState so the request
 *     keeps running and its result lands even when the user navigates
 *     away (Play tab, MyPage, etc.) before generate completes. Pearl
 *     2026-05-10: previously this state died on ChordActions unmount,
 *     losing the result.
 *   - targetSlots: the slots the current suggestions were generated for.
 *     applySuggestion writes exactly those, wherever the selection is now.
 *   - requestId: every run takes a new one, and a response that arrives
 *     after a newer run started (or after the song was replaced) is dropped.
 */
import { create } from 'zustand';
import type { Song, SlotAddress, SectionType } from '../models/types';
import {
  generateChords,
  generateSection,
  parseSuggestionChords,
  type GeneratePhase,
  type Suggestion,
  type SuggestionSource,
} from '../engine/chordGenerator';
import type { SavedSession } from '../models/types';
import { CHORDS_PER_BAR, MAX_SECTION_CHORDS } from '../engine/songForm';
import { useSongStore } from './songStore';

const STORAGE_KEY = 'theartist-generation';
const DEFAULT_MODEL = 'ft_f1';  // Pearl 2026-05-09 — F1 (pop-preserving baseline)

/** How a runSectionGenerate call ended, for the dialog that started it. */
export type SectionRunResult =
  | { status: 'done' }
  | { status: 'failed'; message: string }
  | { status: 'cancelled' };

interface GenerationState {
  // Persisted: model selection
  modelKey: string;
  setModelKey: (key: string) => void;

  /** Section sent by the drag-path Generate. 'auto' = the type of the song
   *  section that contains the whole selection, else no song-form rules. */
  generateSectionType: SectionType | 'auto';
  setGenerateSectionType: (choice: SectionType | 'auto') => void;

  // Ephemeral: in-flight generation state
  loading: boolean;
  phase: GeneratePhase | null;
  suggestions: Suggestion[];
  /** Slots the current suggestions were generated for. */
  targetSlots: SlotAddress[];
  /** Who answered the current suggestions; 'rules' = the model was
   *  unavailable and the backend's rule-based generator answered. */
  source: SuggestionSource | null;
  /** Checkpoint that produced the current suggestions, when the server says. */
  modelUsed: string | null;
  showSuggestions: boolean;
  /** Index of the suggestion currently applied to the score (so the user
   *  can hop A/B/C without re-running). null = none picked yet. */
  activeSuggestionIdx: number | null;
  /** Id of the newest run; results of older runs are ignored. */
  requestId: number;

  // Actions on suggestion display
  setSuggestions: (s: Suggestion[]) => void;
  setShowSuggestions: (b: boolean) => void;
  setActiveSuggestionIdx: (i: number | null) => void;
  clearSuggestions: () => void;
  /** Write suggestion `index` into targetSlots and mark it active. */
  applySuggestion: (index: number) => void;

  // Generate orchestration — owns the async lifecycle so navigation
  // doesn't kill in-flight generation.
  runGenerate: (
    song: Song,
    selectedSlots: SlotAddress[],
    modelKey: string,
    sectionType: SectionType | null,
  ) => Promise<void>;
  runFavoriteGenerate: (
    song: Song,
    selectedSlots: SlotAddress[],
    starredSessions: SavedSession[],
    sectionType: SectionType | null,
  ) => Promise<void>;
  /** "New from Song Form": place the section after the last used measure,
   *  generate it, keep the A/B/C suggestions, apply A and select the new
   *  measures. On failure or cancel the placement is taken back and the
   *  previous A/B/C list shows again. */
  runSectionGenerate: (request: {
    sectionType: SectionType;
    chordCount: number;
  }) => Promise<SectionRunResult>;
  /** Abort the in-flight section request, undo its placement and show the
   *  A/B/C list it hid again. */
  cancelSectionGenerate: () => void;
}

function load(): { modelKey: string } {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { modelKey: DEFAULT_MODEL };
    const parsed = JSON.parse(raw);
    return { modelKey: typeof parsed?.modelKey === 'string' ? parsed.modelKey : DEFAULT_MODEL };
  } catch {
    return { modelKey: DEFAULT_MODEL };
  }
}

function persist(state: { modelKey: string }): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

/** Both slots of every measure in [start, start + count). */
function slotsForMeasures(start: number, count: number): SlotAddress[] {
  const slots: SlotAddress[] = [];
  for (let m = start; m < start + count; m++) {
    slots.push({ measureIndex: m, slotIndex: 0 }, { measureIndex: m, slotIndex: 1 });
  }
  return slots;
}

/** The A/B/C list as it was before beginRequest hid it. */
type ListView = Pick<GenerationState, 'targetSlots' | 'showSuggestions' | 'activeSuggestionIdx'>;

/** The in-flight section request: its fetch, how to take its placed
 *  section back off the staff, and the A/B/C list it hid. Module-level
 *  because it is not UI state. */
let pendingSection: {
  controller: AbortController;
  rollback: () => void;
  hiddenList: ListView;
} | null = null;

function dropPendingSection(rollback: boolean): void {
  const pending = pendingSection;
  if (!pending) return;
  pendingSection = null;
  pending.controller.abort();
  if (rollback) pending.rollback();
}

export const useGenerationStore = create<GenerationState>((set, get) => {
  /** Start a run: supersede whatever was in flight and return its id. */
  const beginRequest = (): number => {
    dropPendingSection(true);
    const requestId = get().requestId + 1;
    set({
      requestId,
      loading: true,
      phase: null,
      showSuggestions: false,
      activeSuggestionIdx: null,
    });
    return requestId;
  };
  const isCurrent = (requestId: number) => get().requestId === requestId;
  const onPhaseFor = (requestId: number) => (phase: GeneratePhase) => {
    if (isCurrent(requestId)) set({ phase });
  };
  const finish = (requestId: number) => {
    if (isCurrent(requestId)) set({ loading: false, phase: null });
  };
  /** After a section run that did not land, show the A/B/C list it hid
   *  again, unless those suggestions were replaced meanwhile. */
  const restoreList = (list: ListView) => {
    if (get().targetSlots !== list.targetSlots) return;
    set({ showSuggestions: list.showSuggestions, activeSuggestionIdx: list.activeSuggestionIdx });
  };

  return {
    modelKey: load().modelKey,
    setModelKey: (key) => {
      set({ modelKey: key });
      persist({ modelKey: key });
    },

    generateSectionType: 'auto',
    setGenerateSectionType: (generateSectionType) => set({ generateSectionType }),

    loading: false,
    phase: null,
    suggestions: [],
    targetSlots: [],
    source: null,
    modelUsed: null,
    showSuggestions: false,
    activeSuggestionIdx: null,
    requestId: 0,

    setSuggestions: (suggestions) => set({ suggestions }),
    setShowSuggestions: (showSuggestions) => set({ showSuggestions }),
    setActiveSuggestionIdx: (activeSuggestionIdx) => set({ activeSuggestionIdx }),
    clearSuggestions: () =>
      set({
        suggestions: [],
        targetSlots: [],
        source: null,
        modelUsed: null,
        showSuggestions: false,
        activeSuggestionIdx: null,
      }),

    applySuggestion: (index) => {
      const { suggestions, targetSlots } = get();
      const suggestion = suggestions[index];
      if (!suggestion) return;
      // Backend works at measure granularity (selectedMeasures = [5] returns
      // both slot 0 and slot 1 for that measure), but a drag selection is
      // slot-level. Write only the slots this generation targeted so other
      // slots (and any chord they already had) stay intact.
      const chordMap = parseSuggestionChords(suggestion);
      const updates = targetSlots.flatMap((address) => {
        const chord = chordMap.get(`${address.measureIndex}-${address.slotIndex}`);
        return chord ? [{ address, chord }] : [];
      });
      useSongStore.getState().setChords(updates);
      // Keep the panel open so the user can A/B/C between candidates.
      // Re-applying the active one is cheap and idempotent.
      set({ activeSuggestionIdx: index });
    },

    runGenerate: async (song, selectedSlots, modelKey, sectionType) => {
      if (selectedSlots.length === 0) return;
      const requestId = beginRequest();
      const targetSlots = selectedSlots.map((s) => ({ ...s }));
      try {
        const { suggestions, source } = await generateChords(
          song,
          selectedSlots,
          sectionType,
          modelKey,
          onPhaseFor(requestId),
        );
        if (!isCurrent(requestId)) return;
        set({ suggestions, source, modelUsed: null, targetSlots, showSuggestions: true });
      } finally {
        finish(requestId);
      }
    },

    runFavoriteGenerate: async (song, selectedSlots, starredSessions, sectionType) => {
      if (selectedSlots.length === 0 || starredSessions.length === 0) return;
      const requestId = beginRequest();
      const targetSlots = selectedSlots.map((s) => ({ ...s }));
      try {
        const calls = starredSessions.map((s) =>
          generateChords(song, selectedSlots, sectionType, s.generation.model).then(({ suggestions, source }) => {
            const top = suggestions[0];
            if (!top) return null;
            return { suggestion: { ...top, label: `${s.name} — ${top.label}` }, source };
          }),
        );
        const settled = await Promise.all(calls);
        if (!isCurrent(requestId)) return;
        const results = settled.filter((r): r is NonNullable<typeof r> => r !== null);
        // One note for the whole list when every preset fell back to the
        // rule-based generator; otherwise mark just the ones that did.
        const allRules = results.length > 0 && results.every((r) => r.source === 'rules');
        const merged = results.map(({ suggestion, source }) =>
          !allRules && source === 'rules'
            ? { ...suggestion, label: `${suggestion.label} (rule-based)` }
            : suggestion,
        );
        set({
          suggestions: merged,
          source: allRules ? 'rules' : null,
          modelUsed: null,
          targetSlots,
          showSuggestions: true,
        });
      } finally {
        finish(requestId);
      }
    },

    runSectionGenerate: async ({ sectionType, chordCount }) => {
      if (
        !Number.isInteger(chordCount) ||
        chordCount < CHORDS_PER_BAR ||
        chordCount > MAX_SECTION_CHORDS ||
        chordCount % CHORDS_PER_BAR !== 0
      ) {
        return {
          status: 'failed',
          message: `Use an even number of chords from ${CHORDS_PER_BAR} to ${MAX_SECTION_CHORDS}`,
        };
      }
      // beginRequest hides the A/B/C list; remember it so a run that does
      // not land can show it again (restoreList).
      const before = get();
      const hiddenList: ListView = {
        targetSlots: before.targetSlots,
        showSuggestions: before.showSuggestions,
        activeSuggestionIdx: before.activeSuggestionIdx,
      };
      const requestId = beginRequest();
      const songState = useSongStore.getState();
      const songEpoch = songState.songEpoch;
      const measuresBefore = songState.song.measures.length;
      const section = songState.placeSection(sectionType, chordCount / CHORDS_PER_BAR);
      const song = useSongStore.getState().song;
      const targetSlots = slotsForMeasures(section.startMeasure, section.length);
      const pending = {
        controller: new AbortController(),
        rollback: () => {
          const current = useSongStore.getState();
          if (current.songEpoch === songEpoch) current.removeSection(section.id, measuresBefore);
        },
        hiddenList,
      };
      pendingSection = pending;

      let message: string;
      try {
        const res = await generateSection(
          {
            song,
            sectionType,
            chordCount,
            startMeasure: section.startMeasure,
            modelKey: get().modelKey,
          },
          onPhaseFor(requestId),
          pending.controller.signal,
        );
        // Cancelled, superseded or the song was replaced meanwhile: whoever
        // did that already took the placement back (or the song is gone).
        if (pendingSection !== pending) return { status: 'cancelled' };
        pendingSection = null;
        if (res.suggestions.length > 0) {
          // Its chords land now, so a reload keeps the section.
          useSongStore.getState().commitSection(section.id);
          set({
            suggestions: res.suggestions,
            targetSlots,
            source: res.source ?? null,
            modelUsed: res.modelUsed ?? null,
            showSuggestions: true,
            loading: false,
            phase: null,
          });
          get().applySuggestion(0);
          useSongStore.getState().selectSlotRange(targetSlots[0], targetSlots[targetSlots.length - 1]);
          return { status: 'done' };
        }
        message = 'The server returned no suggestions';
      } catch (err) {
        if (pendingSection !== pending) return { status: 'cancelled' };
        pendingSection = null;
        message = err instanceof Error ? err.message : String(err);
      }
      pending.rollback();
      finish(requestId);
      restoreList(hiddenList);
      return { status: 'failed', message };
    },

    cancelSectionGenerate: () => {
      const pending = pendingSection;
      if (!pending) return;
      dropPendingSection(true);
      set((state) => ({ requestId: state.requestId + 1, loading: false, phase: null }));
      restoreList(pending.hiddenList);
    },
  };
});

// A replaced song (Initialize, MyPage Load) makes the suggestions and any
// in-flight request meaningless. Drop them here rather than in a component,
// so it also happens while the Generate panel is not mounted. Keyed on
// songEpoch, not song.id: a loaded session keeps the id of the song it was
// saved from, and its chords are not the ones the suggestions were made for.
useSongStore.subscribe((state, prev) => {
  if (state.songEpoch === prev.songEpoch) return;
  dropPendingSection(false);
  useGenerationStore.setState((s) => ({
    requestId: s.requestId + 1,
    loading: false,
    phase: null,
    suggestions: [],
    targetSlots: [],
    source: null,
    modelUsed: null,
    showSuggestions: false,
    activeSuggestionIdx: null,
  }));
});
