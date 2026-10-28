import type { Chord } from '../models/types';
import { NOTE_VALUES, NOTE_NAMES } from './constants.ts';

// Intervals relative to root for each chord quality.
//
// Voicings are capped at 4 notes — that's how jazz pianists actually
// play these on the keyboard. For 5+ note tension chords (9/11/13 and
// their alterations), the conventional drop is the 5th (and the 9th
// for 11/13 chords), keeping root–3rd–7th–tension. This matches the
// "텐션 코드도 결국 4개 누르는" reality without throwing the tension
// away.
//
// Triads (3 notes) and basic 7-chords (4 notes) pass through unchanged.
export const QUALITY_INTERVALS: Record<string, number[]> = {
  // Triads — 3 notes
  'maj':    [0, 4, 7],
  'min':    [0, 3, 7],
  'dim':    [0, 3, 6],
  'aug':    [0, 4, 8],
  'sus2':   [0, 2, 7],
  'sus4':   [0, 5, 7],

  // 7-chords / 6-chords — 4 notes
  '7':      [0, 4, 7, 10],
  'maj7':   [0, 4, 7, 11],
  'm7':     [0, 3, 7, 10],
  'aug7':   [0, 4, 8, 10],
  'dim7':   [0, 3, 6, 9],
  'm7b5':   [0, 3, 6, 10],
  '6':      [0, 4, 7, 9],
  'm6':     [0, 3, 7, 9],
  'mMaj7':  [0, 3, 7, 11],
  'add9':   [0, 4, 7, 14],   // already 4-note (root, 3rd, 5th, 9th)

  // Extended (≥9th) — drop 5th, keep tension. 4 notes.
  '9':      [0, 4, 10, 14],   // root–3–b7–9
  'm9':     [0, 3, 10, 14],   // root–b3–b7–9
  'maj9':   [0, 4, 11, 14],   // root–3–maj7–9

  // Doubly-extended (11th, 13th) — drop 5th AND 9th; keep root–3–b7–top
  '11':     [0, 4, 10, 17],
  'm11':    [0, 3, 10, 17],
  '13':     [0, 4, 10, 21],
  'm13':    [0, 3, 10, 21],

  // Altered dominants — drop 5th, keep alteration
  '7b9':    [0, 4, 10, 13],
  '7#9':    [0, 4, 10, 15],
  '7#11':   [0, 4, 10, 18],
  '7b13':   [0, 4, 10, 20],
};

/** Slash bass as a pitch class, or null when the chord has none (or it is the root). */
function slashBassPc(chord: Chord): number | null {
  if (!chord.bass) return null;
  const bass = NOTE_VALUES[chord.bass];
  const root = NOTE_VALUES[chord.root];
  if (bass === undefined || root === undefined || bass === root) return null;
  return bass;
}

/** Root-position stack from the root in octave 3 (the voicing before slash basses were honoured). */
export function rootPositionVoicing(chord: Chord): number[] {
  const rootValue = NOTE_VALUES[chord.root];
  if (rootValue === undefined) return [];

  const intervals = QUALITY_INTERVALS[chord.quality] || QUALITY_INTERVALS['maj'];
  const baseMidi = 48 + rootValue;
  return intervals.map(interval => baseMidi + interval);
}

// Slash chords put the named bass at the bottom. When the bass is a chord
// tone the chord is inverted (F/C = C F A, C/E = E G C); otherwise the bass
// goes under the root-position chord (F/G = G | F A C), dropping the 5th of
// a 4-note chord so the voicing stays within the 4-note cap plus the bass.
export function generatePianoVoicing(chord: Chord): number[] {
  const voicing = rootPositionVoicing(chord);
  const bass = slashBassPc(chord);
  if (voicing.length === 0 || bass === null) return voicing;

  if (voicing.some(m => m % 12 === bass)) {
    const inverted = [...voicing];
    // tensions reach up to a 13th, so a note may need two octave moves
    for (let i = 0; i < voicing.length * 2 && inverted[0] % 12 !== bass; i++) {
      inverted.push(inverted.shift()! + 12);
      inverted.sort((a, b) => a - b);
    }
    return inverted[0] >= 60 ? inverted.map(m => m - 12) : inverted;
  }

  const fifth = voicing[0] + 7;
  const upper = voicing.length >= 4 && voicing.includes(fifth) ? voicing.filter(m => m !== fifth) : voicing;
  let bassMidi = upper[0] - 1;
  while (bassMidi % 12 !== bass) bassMidi--;
  return [bassMidi, ...upper];
}

/** The chord's stored voicing, except an empty one or a slash chord still stored in root
 *  position (saved before slash basses were honoured); those are recomputed. A voicing
 *  played in from a MIDI keyboard is never root-position-only for a slash chord, so it stays. */
export function resolvePianoVoicing(chord: Chord): number[] {
  const stored = chord.voicing ?? [];
  if (stored.length === 0) return generatePianoVoicing(chord);
  if (slashBassPc(chord) !== null) {
    const legacy = rootPositionVoicing(chord);
    if (legacy.length === stored.length && legacy.every((m, i) => m === stored[i])) {
      return generatePianoVoicing(chord);
    }
  }
  return stored;
}

const OPEN_STRINGS = [40, 45, 50, 55, 59, 64]; // E A D G B E

export function generateGuitarVoicing(chord: Chord): number[] {
  const rootValue = NOTE_VALUES[chord.root];
  if (rootValue === undefined) return [-1, -1, -1, -1, -1, -1];

  const intervals = QUALITY_INTERVALS[chord.quality] || QUALITY_INTERVALS['maj'];
  const chordNotes = new Set(intervals.map(i => (rootValue + i) % 12));

  // Slash chord: the named bass goes on the lowest string that reaches it
  // within the first five frets (F/C = x33211, C/E = 032010, G/B = x20003);
  // strings below it are muted and the rest take the lowest-fret chord tone.
  const bass = slashBassPc(chord);
  if (bass !== null) {
    const bassString = OPEN_STRINGS.findIndex(open => {
      for (let fret = 0; fret <= 5; fret++) if ((open + fret) % 12 === bass) return true;
      return false;
    });
    if (bassString >= 0) {
      return OPEN_STRINGS.map((open, i) => {
        if (i < bassString) return -1;
        for (let fret = 0; fret <= 5; fret++) {
          const note = (open + fret) % 12;
          if (i === bassString ? note === bass : chordNotes.has(note)) return fret;
        }
        return -1;
      });
    }
  }

  const frets: number[] = [];
  for (const openMidi of OPEN_STRINGS) {
    let bestFret = -1;
    for (let fret = 0; fret <= 5; fret++) {
      const note = (openMidi + fret) % 12;
      if (chordNotes.has(note)) {
        bestFret = fret;
        break; // prefer lowest fret
      }
    }
    frets.push(bestFret);
  }

  // Ensure root is in the bass — mute strings below the lowest root occurrence
  let rootStringIndex = -1;
  for (let i = 0; i < frets.length; i++) {
    if (frets[i] >= 0) {
      const note = (OPEN_STRINGS[i] + frets[i]) % 12;
      if (note === rootValue) {
        rootStringIndex = i;
        break;
      }
    }
  }

  if (rootStringIndex > 0) {
    // Mute strings below the root
    for (let i = 0; i < rootStringIndex; i++) {
      frets[i] = -1;
    }
  }
  // If no root found, keep all voiced strings (don't mute everything)

  return frets;
}

export function midiToNoteName(midi: number): string {
  const octave = Math.floor(midi / 12) - 1;
  return NOTE_NAMES[midi % 12] + octave;
}
