import { create } from 'zustand';
import type { Song, Measure, Chord, SlotAddress, SectionType, SongSection } from '../models/types';
import { calculateRomanNumeral } from '../engine/romanNumeral';
import { generatePianoVoicing } from '../engine/voicingEngine';
import { NOTE_VALUES, VALUE_TO_FLAT_NAME } from '../engine/constants';
import { stopPlayback } from '../engine/playback';
import { setCurrentDrumPattern } from '../engine/drums';
import {
  DEFAULT_SONG_TITLE,
  MAX_SECTION_BARS,
  sectionAt,
  sectionPlacement,
  withAutoTitle,
  withSongFormDefaults,
} from '../engine/songForm';

/**
 * If playback is active, stop it and return state patches that clear the
 * playback flags. Used to halt audio whenever the user edits the score or
 * any setting — the running music would no longer reflect what's on screen.
 */
function interruptIfPlaying(state: { isPlaying: boolean }): {
  isPlaying: false;
  playbackPosition: null;
} | Record<string, never> {
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

export type Instrument = 'piano' | 'guitar';

/** Display-mode tag for the voicing card (keyboard vs fretboard).
 * Auto-derived in VoicingViewer from the active harmony instrument's
 * family (`acoustic_guitar_*`/`electric_guitar_*` → 'guitar', otherwise
 * → 'piano'). The playback engine consults this to pick voicing math
 * (guitar fretboard mapping vs piano voicing). 'vocal' was removed
 * 2026-05-10 along with the melody track. */

interface SongState {
  song: Song;
  /** Bumped by every song replacement (clearSong, setSong). A loaded
   *  session keeps the id of the song it was saved from, so song.id cannot
   *  tell a replacement from an edit; listeners compare this instead. */
  songEpoch: number;
  selectedSlots: SlotAddress[];
  playbackPosition: { measureIndex: number; slotIndex: 0 | 1 } | null;
  isPlaying: boolean;
  instrument: Instrument;
  midiCandidates: Chord[];
  drumPatternId: number | null;  // null = no drums; 1..6 = pattern id
  /** User-picked override for the genre's auto-resolved harmony GM
   *  instrument name. `null` means "use the genre default" (table in
   *  instruments.ts). Pearl 2026-05-10 — surfaced in VoicingViewer's
   *  override grid so the user can A/B different timbres without changing
   *  the genre. Bass intentionally has no override (Pearl: "let me pick
   *  bass for you"). Melody layer dropped — variety lives here now via
   *  per-instrument harmony swap. Voyager API never reads this. */
  harmonyOverride: string | null;

  // Actions
  /** A user edit — also turns the automatic (section-derived) title off. */
  setTitle: (title: string) => void;
  setBpm: (bpm: number) => void;
  setKey: (key: string) => void;
  setTimeSignature: (ts: [number, number]) => void;
  setGenre: (genre: string | null) => void;
  selectSlot: (slot: SlotAddress | null) => void;
  selectSlotRange: (from: SlotAddress, to: SlotAddress) => void;
  setChord: (address: SlotAddress, chord: Chord | null) => void;
  /** Several slots in one song update (applying an A/B/C suggestion). */
  setChords: (updates: Array<{ address: SlotAddress; chord: Chord | null }>) => void;
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
  setPlaybackPosition: (pos: { measureIndex: number; slotIndex: 0 | 1 } | null) => void;
  setIsPlaying: (playing: boolean) => void;
  resetPlayback: () => void;
  recalculateRomanNumerals: () => void;
  setInstrument: (instrument: Instrument) => void;
  setMidiCandidates: (chords: Chord[]) => void;
  setDrumPatternId: (id: number | null) => void;
  setHarmonyOverride: (name: string | null) => void;
}

const DRUM_STORAGE_KEY = 'theartist-drum-pattern';

function loadDrumPattern(): number | null {
  try {
    const raw = localStorage.getItem(DRUM_STORAGE_KEY);
    if (raw === null) return null;
    if (raw === 'null') return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : null;
  } catch {
    return null;
  }
}

export const useSongStore = create<SongState>((set, get) => ({
  song: loadFromStorage() || createInitialSong(),
  songEpoch: 0,
  selectedSlots: [],
  playbackPosition: null,
  isPlaying: false,
  instrument: 'piano' as Instrument,
  midiCandidates: [],
  drumPatternId: (() => {
    const id = loadDrumPattern();
    setCurrentDrumPattern(id);
    return id;
  })(),
  harmonyOverride: null,

  setTitle: (title) => set((state) => ({
    song: { ...state.song, title, autoTitle: false },
  })),

  setBpm: (bpm) => {
    const clamped = Math.max(20, Math.min(300, bpm));
    set((state) => ({
      ...interruptIfPlaying(state),
      song: { ...state.song, bpm: clamped },
    }));
  },

  setTimeSignature: (ts) => set((state) => ({
    ...interruptIfPlaying(state),
    song: { ...state.song, timeSignature: ts },
  })),

  setKey: (key) => {
    set((state) => {
      const interrupt = interruptIfPlaying(state);
      const oldKeyRoot = state.song.key.split(' ')[0];
      const newKeyRoot = key.split(' ')[0];
      const oldSemi = NOTE_VALUES[oldKeyRoot] ?? 0;
      const newSemi = NOTE_VALUES[newKeyRoot] ?? 0;
      const semitoneShift = (newSemi - oldSemi + 12) % 12;

      const updatedSong = { ...state.song, key };
      const measures = updatedSong.measures.map(m => {
        const newChords = m.chords.map(chord => {
          if (!chord) return null;
          let transposedRoot = chord.root;
          if (semitoneShift !== 0) {
            const rootSemi = NOTE_VALUES[chord.root];
            if (rootSemi !== undefined) {
              transposedRoot = VALUE_TO_FLAT_NAME[(rootSemi + semitoneShift) % 12];
            }
          }
          const transposed = {
            ...chord,
            root: transposedRoot,
            bass: chord.bass
              ? VALUE_TO_FLAT_NAME[(NOTE_VALUES[chord.bass]! + semitoneShift) % 12]
              : undefined,
          };
          return {
            ...transposed,
            romanNumeral: calculateRomanNumeral(transposed, key),
            voicing: generatePianoVoicing(transposed),
          };
        }) as [Chord | null, Chord | null];
        return { ...m, chords: newChords };
      });
      return { ...interrupt, song: { ...updatedSong, measures } };
    });
  },

  setGenre: (genre) => set((state) => ({
    ...interruptIfPlaying(state),
    song: { ...state.song, genre },
    // VoicingViewer auto-derives `instrument` (piano vs guitar) from the
    // genre's harmony Soundfont family — leave it alone here. Pearl 2026-05-10.
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

  setChords: (updates) => set((state) => {
    if (updates.length === 0) return {};
    const byMeasure = new Map<number, Array<{ address: SlotAddress; chord: Chord | null }>>();
    for (const update of updates) {
      const list = byMeasure.get(update.address.measureIndex) ?? [];
      list.push(update);
      byMeasure.set(update.address.measureIndex, list);
    }
    const measures = state.song.measures.map((m, mi) => {
      const list = byMeasure.get(mi);
      if (!list) return m;
      const newChords = [...m.chords] as [Chord | null, Chord | null];
      for (const { address, chord } of list) {
        newChords[address.slotIndex] = chord ? analyzeChord(chord, state.song.key) : null;
      }
      return { ...m, chords: newChords };
    });
    return { ...interruptIfPlaying(state), song: { ...state.song, measures } };
  }),

  addMeasures: (count = 4) => set((state) => {
    const currentLength = state.song.measures.length;
    const newMeasures = Array.from({ length: count }, (_, i) => createMeasure(currentLength + i));
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
      const currentLength = state.song.measures.length;
      const added = Array.from({ length: measuresToAdd }, (_, i) => createMeasure(currentLength + i));
      const sections = [...(state.song.sections ?? []), section]
        .sort((a, b) => a.startMeasure - b.startMeasure);
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
    let end = state.song.measures.length;
    if (trimToLength !== undefined) {
      while (
        end > Math.max(0, trimToLength) &&
        !state.song.measures[end - 1].chords.some(Boolean) &&
        !sectionAt({ sections }, end - 1)
      ) {
        end--;
      }
    }
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
    // Reset store-held transient view state too. Component-local state
    // (MidiStatus suggestions, …) reacts to the new song.id via its own
    // useEffect; generationStore drops its suggestions on the songEpoch bump.
    // The fresh song has no sections and an automatic title again.
    set((state) => ({
      song: createInitialSong(),
      songEpoch: state.songEpoch + 1,
      selectedSlots: [],
      playbackPosition: null,
      isPlaying: false,
      midiCandidates: [],
    }));
  },

  setSong: (song) => {
    stopPlayback();
    set((state) => ({
      // Sessions saved before song-form sections existed lack those fields.
      song: withSongFormDefaults(structuredClone(song)),
      // A replacement even when the session kept the working song's id.
      songEpoch: state.songEpoch + 1,
      selectedSlots: [],
      playbackPosition: null,
      isPlaying: false,
      midiCandidates: [],
    }));
  },

  setPlaybackPosition: (pos) => set({ playbackPosition: pos }),

  setIsPlaying: (playing) => set({ isPlaying: playing }),

  resetPlayback: () => {
    stopPlayback();
    set({ isPlaying: false, playbackPosition: null });
  },

  setInstrument: (instrument) => set(() => ({
    // Live instrument swap during playback is supported — the playback engine
    // reads `currentInstrument` global at note-trigger time (see playback.ts
    // ~line 204). VoicingViewer mirrors the new instrument into the engine
    // via setCurrentInstrument(), so the next scheduled note picks it up.
    // No interruptIfPlaying — Pearl 2026-05-09: switching piano/guitar/vocal
    // mid-playback should swap timbre, not stop the song.
    instrument,
  })),

  setMidiCandidates: (chords) => set({ midiCandidates: chords }),

  setDrumPatternId: (id) => {
    setCurrentDrumPattern(id);
    try {
      localStorage.setItem(DRUM_STORAGE_KEY, id === null ? 'null' : String(id));
    } catch {
      // ignore
    }
    set({ drumPatternId: id });
  },

  setHarmonyOverride: (name) => set({ harmonyOverride: name }),

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
