import { create } from 'zustand';
import type { Song, Measure, Chord, SlotAddress, SectionType, SongSection } from '../models/types';
import type { TargetChord } from '../engine/generationComparison';
import { calculateRomanNumeral } from '../engine/romanNumeral';
import { generatePianoVoicing } from '../engine/voicingEngine';
import { transposeSongKey } from '../engine/songTranspose';
import { cancelPendingStart, setLiveBpm, stopPlayback } from '../engine/playback';
import {
  DEFAULT_SONG_TITLE,
  MAX_SECTION_BARS,
  checkSectionRanges,
  sectionAt,
  sectionPlacement,
  withAutoTitle,
  withSongFormDefaults,
} from '../engine/songForm';

/**
 * If playback is active, stop it and return state patches that clear the
 * playback flags. Used to halt audio whenever the user edits the score or
 * any setting — the running music would no longer reflect what's on screen.
 * A play still loading its samples is called off too, for the same reason.
 */
function interruptIfPlaying(state: { isPlaying: boolean }): {
  isPlaying: false;
  playbackPosition: null;
} | Record<string, never> {
  cancelPendingStart();
  if (!state.isPlaying) return {};
  stopPlayback();
  return { isPlaying: false, playbackPosition: null };
}

function createMeasure(index: number): Measure {
  return {
    id: crypto.randomUUID(),
    index,
    chords: [null, null],
  };
}

/** `count` empty measures numbered from `firstIndex`. */
function createMeasures(firstIndex: number, count: number): Measure[] {
  return Array.from({ length: count }, (_, i) => createMeasure(firstIndex + i));
}

function createInitialSong(): Song {
  return {
    id: crypto.randomUUID(),
    title: DEFAULT_SONG_TITLE,
    bpm: 80,
    key: 'C major',
    genre: null,
    timeSignature: [4, 4],
    measures: [
      createMeasure(0),
      createMeasure(1),
      createMeasure(2),
      createMeasure(3),
    ],
    sections: [],
    autoTitle: true,
  };
}

/** Roman numeral + default voicing for a chord about to land in a slot. */
function analyzeChord(chord: Chord, key: string): Chord {
  return {
    ...chord,
    romanNumeral: calculateRomanNumeral(chord, key),
    voicing: chord.voicing.length > 0 ? chord.voicing : generatePianoVoicing(chord),
  };
}

/** The tempo range setBpm and setBpmLive clamp to. SongSettings' BPM input
 *  and the Play panel's BPM fader (ControllerPane) offer the same 20..300,
 *  and sessionStorage rejects a saved project outside it: keep them in step. */
const MIN_BPM = 20;
const MAX_BPM = 300;

function clampBpm(bpm: number): number {
  return Math.max(MIN_BPM, Math.min(MAX_BPM, bpm));
}

/** setChords' updates per measure index, each list in the given order. */
function groupByMeasure(updates: TargetChord[]): Map<number, TargetChord[]> {
  const byMeasure = new Map<number, TargetChord[]>();
  for (const update of updates) {
    const list = byMeasure.get(update.address.measureIndex) ?? [];
    list.push(update);
    byMeasure.set(update.address.measureIndex, list);
  }
  return byMeasure;
}

function byStartMeasure(a: SongSection, b: SongSection): number {
  return a.startMeasure - b.startMeasure;
}

/** The song's length once the empty measures outside every section are
 *  dropped from its end, never going below `minLength`. */
function lengthWithoutEmptyTail(measures: Measure[], sections: SongSection[], minLength: number): number {
  let end = measures.length;
  while (
    end > Math.max(0, minLength) &&
    !measures[end - 1].chords.some(Boolean) &&
    !sectionAt({ sections }, end - 1)
  ) {
    end--;
  }
  return end;
}

const STORAGE_KEY = 'theartist-song';
const AUTOSAVE_DEBOUNCE_MS = 500;

function loadFromStorage(): Song | null {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    // Songs autosaved before song-form sections existed lack those fields.
    if (data) return withSongFormDefaults(JSON.parse(data));
  } catch {
    // ignore
  }
  return null;
}

function saveToStorage(song: Song): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(song));
}

function slotToLinear(slot: SlotAddress): number {
  return slot.measureIndex * 2 + slot.slotIndex;
}

function linearToSlot(linear: number): SlotAddress {
  return { measureIndex: Math.floor(linear / 2), slotIndex: (linear % 2) as 0 | 1 };
}

/** Build a sorted range of SlotAddresses between two endpoints (inclusive) */
function buildSlotRange(a: SlotAddress, b: SlotAddress): SlotAddress[] {
  const la = slotToLinear(a);
  const lb = slotToLinear(b);
  const min = Math.min(la, lb);
  const max = Math.max(la, lb);
  const result: SlotAddress[] = [];
  for (let i = min; i <= max; i++) {
    result.push(linearToSlot(i));
  }
  return result;
}

export function isSlotInList(slot: SlotAddress, list: SlotAddress[]): boolean {
  return list.some(s => s.measureIndex === slot.measureIndex && s.slotIndex === slot.slotIndex);
}

interface SongState {
  song: Song;
  /** Bumped by every song replacement (clearSong, setSong). A loaded
   *  session keeps the id of the song it was saved from, so song.id cannot
   *  tell a replacement from an edit; listeners compare this instead. */
  songEpoch: number;
  selectedSlots: SlotAddress[];
  playbackPosition: { measureIndex: number; slotIndex: 0 | 1 } | null;
  isPlaying: boolean;
  midiCandidates: Chord[];
  /** The song the last import replaced, for undoImport; any other song
   *  replacement clears it. */
  previousImportSong: Song | null;

  // Actions
  /** A user edit — also turns the automatic (section-derived) title off. */
  setTitle: (title: string) => void;
  setBpm: (bpm: number) => void;
  /** Change the tempo without stopping playback (the Play panel's BPM
   *  fader): the running Transport speeds up or slows down in place. */
  setBpmLive: (bpm: number) => void;
  setKey: (key: string) => void;
  setTimeSignature: (ts: [number, number]) => void;
  setGenre: (genre: string | null) => void;
  selectSlot: (slot: SlotAddress | null) => void;
  selectSlotRange: (from: SlotAddress, to: SlotAddress) => void;
  setChord: (address: SlotAddress, chord: Chord | null) => void;
  /** Several slots in one song update (applying an A/B/C suggestion).
   *  `preserveAnalysis` writes copies of the chords as given (restoring
   *  captured originals) instead of running analyzeChord on them. */
  setChords: (updates: TargetChord[], options?: { preserveAnalysis?: boolean }) => void;
  addMeasures: (count?: number) => void;
  /** Record a song-form section of `bars` measures right after the last
   *  used measure (see sectionPlacement), appending measures only as
   *  needed. Returns the new section, which stays pending (a reload drops
   *  it) until commitSection keeps it or removeSection takes it back. */
  placeSection: (type: SectionType, bars: number) => SongSection;
  /** Keep a placed section once its chords have landed: it is no longer
   *  pending, so it survives a reload. */
  commitSection: (id: string) => void;
  /** Drop a section record; with `trimToLength`, also drop the empty,
   *  section-free measures at the end of the song down to that length
   *  (undoes a placeSection whose generation failed or was cancelled). */
  removeSection: (id: string, trimToLength?: number) => void;
  clearSong: () => void;
  /** Replace the active song outright. Used by MyPage "Load" to bring a
   *  saved session into the staff. Stops playback and clears
   *  selection / live-MIDI state to match. */
  setSong: (song: Song) => void;
  /** setSong for an imported score, keeping the replaced song for undoImport. */
  importSong: (song: Song) => void;
  /** Bring back the song the last import replaced, if any. */
  undoImport: () => void;
  /** Replace the section list (kept sorted by start measure). Returns
   *  checkSectionRanges' message, changing nothing, when the sections do
   *  not fit the song; null once applied. */
  setSections: (sections: SongSection[]) => string | null;
  setPlaybackPosition: (pos: { measureIndex: number; slotIndex: 0 | 1 } | null) => void;
  setIsPlaying: (playing: boolean) => void;
  resetPlayback: () => void;
  recalculateRomanNumerals: () => void;
  setMidiCandidates: (chords: Chord[]) => void;
}

/**
 * Store fields for a song that replaces the current one (clearSong,
 * setSong): a new songEpoch, and no selection, playback, live-MIDI
 * candidates or import undo left over from the old song. Listeners reset
 * their own song-bound state on the epoch bump (generationStore drops its
 * suggestions, useMidiCapture its captured notes).
 */
function songReplacement(song: Song, previousEpoch: number): Partial<SongState> {
  return {
    song,
    songEpoch: previousEpoch + 1,
    selectedSlots: [],
    playbackPosition: null,
    isPlaying: false,
    midiCandidates: [],
    previousImportSong: null,
  };
}

export const useSongStore = create<SongState>((set, get) => ({
  song: loadFromStorage() || createInitialSong(),
  songEpoch: 0,
  selectedSlots: [],
  playbackPosition: null,
  isPlaying: false,
  midiCandidates: [],
  previousImportSong: null,

  setTitle: (title) => set((state) => ({
    song: { ...state.song, title, autoTitle: false },
  })),

  setBpm: (bpm) => {
    const clamped = clampBpm(bpm);
    set((state) => ({
      ...interruptIfPlaying(state),
      song: { ...state.song, bpm: clamped },
    }));
  },

  setBpmLive: (bpm) => {
    const clamped = clampBpm(Math.round(bpm));
    // Transport events sit at musical positions, so retiming them in place
    // keeps a running (or paused) playback in step with the new tempo.
    setLiveBpm(clamped);
    set((state) => ({ song: { ...state.song, bpm: clamped } }));
  },

  setTimeSignature: (ts) => set((state) => ({
    ...interruptIfPlaying(state),
    song: { ...state.song, timeSignature: ts },
  })),

  setKey: (key) => {
    set((state) => ({
      ...interruptIfPlaying(state),
      song: transposeSongKey(state.song, key),
    }));
  },

  setGenre: (genre) => set((state) => ({
    ...interruptIfPlaying(state),
    song: { ...state.song, genre },
    // playStore re-resolves the genre's Auto instrument, rhythm, voicing
    // and drums for the engine on this change.
  })),

  selectSlot: (slot) => set({ selectedSlots: slot ? [slot] : [] }),

  selectSlotRange: (from, to) => set({ selectedSlots: buildSlotRange(from, to) }),

  setChord: (address, chord) => set((state) => {
    const measures = state.song.measures.map((m, mi) => {
      if (mi !== address.measureIndex) return m;
      const newChords = [...m.chords] as [Chord | null, Chord | null];
      newChords[address.slotIndex] = chord ? analyzeChord(chord, state.song.key) : null;
      return { ...m, chords: newChords };
    });
    const newSong = { ...state.song, measures };
    return { ...interruptIfPlaying(state), song: newSong };
  }),

  setChords: (updates, options) => set((state) => {
    if (updates.length === 0) return {};
    const updatesByMeasure = groupByMeasure(updates);
    const slotChord = (chord: Chord) =>
      options?.preserveAnalysis ? structuredClone(chord) : analyzeChord(chord, state.song.key);
    const measures = state.song.measures.map((m, mi) => {
      const measureUpdates = updatesByMeasure.get(mi);
      if (!measureUpdates) return m;
      const newChords = [...m.chords] as [Chord | null, Chord | null];
      for (const { address, chord } of measureUpdates) {
        newChords[address.slotIndex] = chord ? slotChord(chord) : null;
      }
      return { ...m, chords: newChords };
    });
    return { ...interruptIfPlaying(state), song: { ...state.song, measures } };
  }),

  addMeasures: (count = 4) => set((state) => {
    const newMeasures = createMeasures(state.song.measures.length, count);
    return {
      ...interruptIfPlaying(state),
      song: {
        ...state.song,
        measures: [...state.song.measures, ...newMeasures],
      },
    };
  }),

  placeSection: (type, bars) => {
    const length = Math.min(MAX_SECTION_BARS, Math.max(1, Math.floor(bars)));
    const { startMeasure, measuresToAdd } = sectionPlacement(get().song, length);
    const section: SongSection = {
      id: crypto.randomUUID(),
      type,
      startMeasure,
      length,
      pending: { addedMeasures: measuresToAdd },
    };
    set((state) => {
      const added = createMeasures(state.song.measures.length, measuresToAdd);
      const sections = [...(state.song.sections ?? []), section].sort(byStartMeasure);
      return {
        ...interruptIfPlaying(state),
        song: withAutoTitle({
          ...state.song,
          measures: [...state.song.measures, ...added],
          sections,
        }),
      };
    });
    return section;
  },

  commitSection: (id) => set((state) => {
    const current = state.song.sections ?? [];
    if (!current.some((s) => s.id === id && s.pending)) return {};
    const sections = current.map((s) => {
      if (s.id !== id) return s;
      const kept = { ...s };
      delete kept.pending;
      return kept;
    });
    return { song: { ...state.song, sections } };
  }),

  removeSection: (id, trimToLength) => set((state) => {
    const current = state.song.sections ?? [];
    const sections = current.filter((s) => s.id !== id);
    if (sections.length === current.length) return {};
    const end = trimToLength === undefined
      ? state.song.measures.length
      : lengthWithoutEmptyTail(state.song.measures, sections, trimToLength);
    const measures = end < state.song.measures.length
      ? state.song.measures.slice(0, end)
      : state.song.measures;
    return {
      ...interruptIfPlaying(state),
      song: withAutoTitle({ ...state.song, measures, sections }),
      selectedSlots: state.selectedSlots.filter((s) => s.measureIndex < measures.length),
    };
  }),

  clearSong: () => {
    // Always force-stop playback on full clear — user intent is "reset everything"
    stopPlayback();
    // The fresh song has no sections and an automatic title again.
    set((state) => songReplacement(createInitialSong(), state.songEpoch));
  },

  setSong: (song) => {
    stopPlayback();
    // Sessions saved before song-form sections existed lack those fields.
    set((state) => songReplacement(withSongFormDefaults(structuredClone(song)), state.songEpoch));
  },

  importSong: (song) => {
    const previous = structuredClone(get().song);
    get().setSong(song);
    set({ previousImportSong: previous });
  },

  undoImport: () => {
    const previous = get().previousImportSong;
    if (previous) get().setSong(previous);
  },

  setSections: (sections) => {
    const error = checkSectionRanges(sections, get().song.measures.length);
    if (error) return error;
    set((state) => ({
      song: withAutoTitle({ ...state.song, sections: structuredClone(sections).sort(byStartMeasure) }),
    }));
    return null;
  },

  setPlaybackPosition: (pos) => set({ playbackPosition: pos }),

  setIsPlaying: (playing) => set({ isPlaying: playing }),

  resetPlayback: () => {
    stopPlayback();
    set({ isPlaying: false, playbackPosition: null });
  },

  setMidiCandidates: (chords) => set({ midiCandidates: chords }),

  recalculateRomanNumerals: () => set((state) => {
    const measures = state.song.measures.map(m => {
      const newChords = m.chords.map(chord => {
        if (!chord) return null;
        return {
          ...chord,
          romanNumeral: calculateRomanNumeral(chord, state.song.key),
        };
      }) as [Chord | null, Chord | null];
      return { ...m, chords: newChords };
    });
    return { song: { ...state.song, measures } };
  }),
}));

// Debounced autosave: every change to `song` writes to localStorage after
// AUTOSAVE_DEBOUNCE_MS of quiet. Means a refresh always recovers the
// in-progress score even though the explicit Save button does something
// else now (sessionStore.add — see Layout.tsx).
let _autosaveTimer: number | null = null;
useSongStore.subscribe((state, prev) => {
  if (state.song === prev.song) return;
  if (_autosaveTimer !== null) window.clearTimeout(_autosaveTimer);
  _autosaveTimer = window.setTimeout(() => {
    saveToStorage(state.song);
    _autosaveTimer = null;
  }, AUTOSAVE_DEBOUNCE_MS);
});
